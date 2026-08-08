"""``LevelsDialog`` — the Tools → Levels… live-preview dialog (plan 05-06).

UI-SPEC surface 25 (PROJ-04, D-12/D-14): three control rows over the current
page image —

- **Black point** — ``QSlider`` + ``QSpinBox``, range 0…255, default **0**.
- **White point** — ``QSlider`` + ``QSpinBox``, range 0…255, default **255**.
- **Gamma** — ``QSlider`` (log-scaled) + ``QDoubleSpinBox``, range
  **0.10…4.00**, default **1.00**, singleStep **±0.01** (UI-SPEC spacing
  exception).

The dialog is a **collector + preview driver** (RESEARCH §Pitfall 3 separation
— the LoadTranslationsDialog template): it never mutates models. Every control
change calls ``preview_callback(current_values)`` so the MainWindow can
re-render the canvas through the capture-suppressed preview path; ``[Cancel]``
``reject()``s and ``[Apply]`` stores ``result_values = current_values`` and
``accept()``s. NO undo pushes originate here (Pitfall 9 — the preview is a
silent display mutation; the caller restores on Cancel and pushes ONE entry
on Apply).

**White > black cross-clamp (T-05-07, UI-SPEC surface 25):** the white
control's minimum follows ``black + 1`` and the black control's maximum
follows ``white - 1`` — one mechanism — so the preview can never receive an
inverted map (``image_ops.levels_lut`` has the math-level backstop too).
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

# Dark QSS for the dialog (UI-SPEC §Color tokens — mirrors the
# LoadTranslationsDialog / InspectorPanel QSS). Extends the shared block with
# spinbox + slider rules so the new controls read as part of the dark UI.
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QSpinBox, QDoubleSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
    padding: 1px 4px;
}
QSlider::groove:horizontal {
    background: #3a3a42;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #00d4ff;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #00d4ff; border-radius: 2px; }
QPushButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 4px 12px;
    color: #e8e8ea;
}
QPushButton:hover { background: #34343c; }
QPushButton:default { border: 1px solid #00d4ff; }
"""


class LevelsDialog(QDialog):
    """Collect ``(black, white, gamma)`` for the Levels flow (D-12/D-14).

    Pure collector + preview driver: the MainWindow owns the page image
    (detached with ``.copy()`` before the dialog opens — Pitfall 2), passes a
    ``preview_callback`` that re-renders the canvas with the current values,
    and decides what Cancel (silent exact restore) and Apply (one image-only
    undo entry) mean. The dialog itself pushes NOTHING (Pitfall 9).
    """

    # Gamma log-slider mapping (UI-SPEC surface 25 range 0.10..4.00).
    GAMMA_MIN = 0.10
    GAMMA_MAX = 4.00
    GAMMA_STEPS = 1000

    def __init__(
        self,
        parent=None,
        page_image=None,
        preview_callback=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Levels")
        self.setObjectName("levels_dialog")
        self.setModal(True)

        # The caller's detached pre-dialog image (restore/apply base — kept
        # for the collector contract; the caller's closure uses it).
        self._page_image = page_image
        self.preview_callback = preview_callback
        self._updating = False
        # Result carrier (read by the MainWindow after exec() == Accepted).
        self.result_values: tuple[int, int, float] = (0, 255, 1.0)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        form = QFormLayout()

        # Black point: slider + spinbox, 0..255, default 0.
        self.black_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.black_slider.setRange(0, 255)
        self.black_slider.setValue(0)
        self.black_spin = QSpinBox(self)
        self.black_spin.setRange(0, 255)
        self.black_spin.setValue(0)
        form.addRow("Black point:", self._row(self.black_slider, self.black_spin))

        # White point: slider + spinbox, 0..255, default 255.
        self.white_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.white_slider.setRange(0, 255)
        self.white_slider.setValue(255)
        self.white_spin = QSpinBox(self)
        self.white_spin.setRange(0, 255)
        self.white_spin.setValue(255)
        form.addRow("White point:", self._row(self.white_slider, self.white_spin))

        # Gamma: log-scaled slider + double spinbox, 0.10..4.00, default 1.00.
        self.gamma_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.gamma_slider.setRange(0, self.GAMMA_STEPS)
        self.gamma_slider.setValue(self._gamma_to_slider(1.00))
        self.gamma_spin = QDoubleSpinBox(self)
        self.gamma_spin.setRange(self.GAMMA_MIN, self.GAMMA_MAX)
        self.gamma_spin.setDecimals(2)
        self.gamma_spin.setSingleStep(0.01)
        self.gamma_spin.setValue(1.00)
        form.addRow("Gamma:", self._row(self.gamma_slider, self.gamma_spin))
        root.addLayout(form)

        # [Cancel] [Apply] (Apply default, accent border per the QSS pattern).
        buttons = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("Apply", self)
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.apply_btn)
        root.addLayout(buttons)

        self.setStyleSheet(_DIALOG_QSS)

        # Widget wiring: slider <-> spin sync per row (Qt's setValue does not
        # re-emit for identical values, so no loops) + the shared refresh.
        self.black_spin.valueChanged.connect(self.black_slider.setValue)
        self.black_slider.valueChanged.connect(self.black_spin.setValue)
        self.white_spin.valueChanged.connect(self.white_slider.setValue)
        self.white_slider.valueChanged.connect(self.white_spin.setValue)
        self.gamma_spin.valueChanged.connect(self._on_gamma_spin_changed)
        self.gamma_slider.valueChanged.connect(self._on_gamma_slider_changed)
        for widget in (
            self.black_spin,
            self.white_spin,
            self.gamma_spin,
        ):
            widget.valueChanged.connect(self._refresh)

        # Apply the initial white>black cross-clamp (white min = black+1,
        # black max = white-1) once; the preview fires with the defaults.
        self._refresh()

    # ------------------------------------------------------------ structure
    def _row(self, slider: QSlider, spin) -> QHBoxLayout:
        """A slider + spinbox row (spin right-aligned after a stretch)."""
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(spin)
        return row

    # -------------------------------------------------------------- gamma map
    def _gamma_to_slider(self, gamma: float) -> int:
        """Map a linear gamma value onto the log-scaled slider position."""
        span = math.log(self.GAMMA_MAX) - math.log(self.GAMMA_MIN)
        t = (math.log(gamma) - math.log(self.GAMMA_MIN)) / span
        return int(round(t * self.GAMMA_STEPS))

    def _slider_to_gamma(self, t: int) -> float:
        """Map a log-scaled slider position back to a linear gamma value."""
        span = math.log(self.GAMMA_MAX) - math.log(self.GAMMA_MIN)
        g = math.exp(math.log(self.GAMMA_MIN) + span * t / self.GAMMA_STEPS)
        return round(g, 2)

    def _on_gamma_slider_changed(self, t: int) -> None:
        """Sync the gamma spinbox from the log-scaled slider."""
        self.gamma_spin.setValue(self._slider_to_gamma(t))

    def _on_gamma_spin_changed(self, g: float) -> None:
        """Sync the log-scaled slider from the gamma spinbox."""
        self.gamma_slider.setValue(self._gamma_to_slider(g))

    # ---------------------------------------------------------------- driver
    def _refresh(self) -> None:
        """Apply the white>black cross-clamp and drive the live preview.

        Runs on every control change. The clamp (T-05-07, UI-SPEC surface
        25) is ONE mechanism: the white control's minimum follows black+1
        and the black control's maximum follows white-1, so the preview can
        never receive white <= black. ``_updating`` guards the clamp's own
        value adjustments from re-entering (the sync connections still run —
        they are direct setValue links, not _refresh calls).
        """
        if self._updating:
            return
        self._updating = True
        try:
            black = self.black_spin.value()
            white = self.white_spin.value()
            self.white_slider.setMinimum(black + 1)
            self.white_spin.setMinimum(black + 1)
            self.black_slider.setMaximum(white - 1)
            self.black_spin.setMaximum(white - 1)
        finally:
            self._updating = False
        if self.preview_callback is not None:
            self.preview_callback(self._current_values())

    def _current_values(self) -> tuple[int, int, float]:
        """The collector payload: ``(black, white, gamma)``."""
        return (
            self.black_spin.value(),
            self.white_spin.value(),
            self.gamma_spin.value(),
        )

    def _on_apply(self) -> None:
        """Store the collected values and accept (no image mutation here)."""
        self.result_values = self._current_values()
        self.accept()

"""``CropDialog`` — the Edit → Crop… numeric dialog (plan 05-07).

UI-SPEC surface 24b (PROJ-04, D-11): a modal ``QDialog`` styled per the
``_DIALOG_QSS`` pattern (LoadTranslationsDialog) with four ``QSpinBox`` rows
— **X** (0…W−1), **Y** (0…H−1), **Width** (1…W−x, bounds recomputed when X
changes), **Height** (1…H−y, recomputed when Y changes) — initialized to the
FULL current page bounds (x=0, y=0, w=W, h=H — never empty; UI-consideration
E3 coverage). Buttons **[Cancel] [Apply]** (Apply default, accent-border per
the QSS pattern). No live canvas preview (the numeric dialog is the
precision path; the Crop tool is the visual path).

The dialog is a **pure collector** (RESEARCH Pitfall 3 — the
LoadTranslationsDialog template): it never mutates models. ``[Apply]``
stores ``result_values = (x, y, w, h)`` and ``accept()``s; the MainWindow
runs the crop apply path. **Apply-time re-validation** (T-05-17, defense in
depth): out-of-range values are corrected IN PLACE against the page bounds
and the dialog STAYS OPEN — guards programmatic edges only (the spinbox
ranges make invalid user input impossible).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

# Dark QSS for the dialog (UI-SPEC §Color tokens — the LoadTranslationsDialog /
# Levels/Resize dialog pattern; spinbox + button rules only — the crop form
# has no sliders).
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
    padding: 1px 4px;
}
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


class CropDialog(QDialog):
    """Collect ``(x, y, w, h)`` for the crop flow (D-11, UI-SPEC surface 24b).

    Pure collector: the MainWindow owns the page (passes its dims), decides
    what Apply means (``_apply_crop`` — the shared apply path with the
    canvas tool), and reads ``result_values`` after ``exec() == Accepted``.
    The dialog itself mutates nothing but its own spinboxes.
    """

    def __init__(
        self,
        parent=None,
        page_w: int = 1,
        page_h: int = 1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crop")
        self.setObjectName("crop_dialog")
        self.setModal(True)

        # Page bounds: the re-validation authority. The spinbox ranges are
        # derived from these (and may be widened programmatically — the
        # apply gate ALWAYS compares against the page bounds).
        self._page_w = max(1, int(page_w))
        self._page_h = max(1, int(page_h))
        # Result carrier (read by the MainWindow after exec() == Accepted).
        # Initialized to the full page bounds — never empty (E3 coverage).
        self.result_values: tuple[int, int, int, int] = (
            0,
            0,
            self._page_w,
            self._page_h,
        )

        root = QVBoxLayout(self)
        root.setSpacing(8)
        form = QFormLayout()

        # X 0..W-1, Y 0..H-1 — the crop origin.
        self.x_spin = QSpinBox(self)
        self.x_spin.setRange(0, max(0, self._page_w - 1))
        self.x_spin.setValue(0)
        self.y_spin = QSpinBox(self)
        self.y_spin.setRange(0, max(0, self._page_h - 1))
        self.y_spin.setValue(0)
        # Width 1..W-x (recomputed when X changes), Height 1..H-y (analog).
        self.w_spin = QSpinBox(self)
        self.w_spin.setRange(1, self._page_w)
        self.w_spin.setValue(self._page_w)
        self.h_spin = QSpinBox(self)
        self.h_spin.setRange(1, self._page_h)
        self.h_spin.setValue(self._page_h)

        form.addRow("X:", self.x_spin)
        form.addRow("Y:", self.y_spin)
        form.addRow("Width:", self.w_spin)
        form.addRow("Height:", self.h_spin)
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

        # Live range recompute (UI-consideration partial E3): the Width range
        # follows W−x, the Height range follows H−y.
        self.x_spin.valueChanged.connect(self._recompute_ranges)
        self.y_spin.valueChanged.connect(self._recompute_ranges)
        self._recompute_ranges()

    # ------------------------------------------------------------ structure
    def _recompute_ranges(self) -> None:
        """Recompute Width max = W−x and Height max = H−y from the origins.

        QSpinBox clamps the current value when the maximum shrinks, so a
        stale Width larger than W−x is corrected live (Qt's own clamp — the
        dialog can never present an out-of-page crop through the widgets).
        """
        x = self.x_spin.value()
        y = self.y_spin.value()
        self.w_spin.setMaximum(max(1, self._page_w - x))
        self.h_spin.setMaximum(max(1, self._page_h - y))

    # ---------------------------------------------------------------- apply
    def _on_apply(self) -> None:
        """Re-validate against the PAGE bounds; collect + accept when valid.

        T-05-17 defense in depth: the spinbox ranges make invalid USER input
        impossible; this gate guards programmatic edges. Out-of-range values
        are corrected IN PLACE and the dialog STAYS OPEN (the corrected
        values are visible) — nothing is applied, nothing is accepted.
        """
        x = self.x_spin.value()
        y = self.y_spin.value()
        w = self.w_spin.value()
        h = self.h_spin.value()
        cx = min(max(x, 0), self._page_w - 1)
        cy = min(max(y, 0), self._page_h - 1)
        cw = min(max(w, 1), self._page_w - cx)
        ch = min(max(h, 1), self._page_h - cy)
        if (cx, cy, cw, ch) != (x, y, w, h):
            self.x_spin.setValue(cx)
            self.y_spin.setValue(cy)
            self.w_spin.setValue(cw)
            self.h_spin.setValue(ch)
            return  # corrected in place — the dialog stays open
        self.result_values = (cx, cy, cw, ch)
        self.accept()

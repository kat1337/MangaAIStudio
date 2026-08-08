"""``ResizeDialog`` — the Tools → Resize… dialog (plan 05-06, UI-SPEC 26).

PROJ-04 (D-13/D-14/D-15/D-17/D-18) — three control rows over the current page
dims:

- **Width / Height** — ``QSpinBox`` pairs, range **1…100000 px**, initialized
  to the current page dims.
- **Unit toggle** — ``QComboBox``: **"pixels"** (default) / **"percent"**
  (percent range 1…1000, applied to the corresponding current dimension).
- **Aspect lock** — ``QCheckBox`` **"Maintain aspect ratio"**, checked by
  default (D-13). Locked: editing the dominant field recomputes the other
  (rounded, >= 1); unlocked: independent.
- **Live result label** — a muted line **"Result: {w} × {h} px"** updating on
  every change (in % mode it shows the resulting pixels, not the percent).

Pure collector (the LoadTranslationsDialog template — RESEARCH §Pitfall 3):
the dialog never mutates the canvas. ``[Cancel]`` ``reject()``s; ``[Apply]``
stores ``result_values = (new_w, new_h)`` (resolved PIXELS) and ``accept()``s.
The MainWindow runs the resize (``image_ops.resize_page`` / ``resize_boxes``),
pushes ONE geometry undo entry, re-baselines Show Original (D-14) and marks
``geometry_altered`` (D-22).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

# Dark QSS for the dialog (UI-SPEC §Color tokens — the shared block).
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QLabel#resultLabel { color: #9a9aa2; }
QSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
    padding: 1px 4px;
}
QComboBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
}
QComboBox QAbstractItemView {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    color: #e8e8ea;
    selection-background-color: #00d4ff;
    selection-color: #0b0b0e;
}
QCheckBox { color: #e8e8ea; }
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


class ResizeDialog(QDialog):
    """Collect ``(new_w, new_h)`` (resolved pixels) for the Resize flow.

    Pure collector: the MainWindow owns the canvas state and the resize
    apply. The dialog owns the number-format contract (UI-SPEC surface 26) —
    ranges, the px/% toggle, the aspect lock, and the live result label.
    """

    # UI-SPEC surface 26 ranges: 1..100000 px, 1..1000 percent.
    MIN_PX = 1
    MAX_PX = 100000
    MIN_PCT = 1
    MAX_PCT = 1000

    def __init__(
        self,
        parent=None,
        current_w: int = 1,
        current_h: int = 1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resize")
        self.setObjectName("resize_dialog")
        self.setModal(True)

        # The current page dims (the % base and the aspect-ratio source).
        self._cur_w = max(self.MIN_PX, int(current_w))
        self._cur_h = max(self.MIN_PX, int(current_h))
        self._updating = False
        # Result carrier (read by the MainWindow after exec() == Accepted).
        self.result_values: tuple[int, int] = (self._cur_w, self._cur_h)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        form = QFormLayout()

        # Width / Height pairs, initialized to the current page dims.
        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(self.MIN_PX, self.MAX_PX)
        self.width_spin.setValue(self._cur_w)
        self.height_spin = QSpinBox(self)
        self.height_spin.setRange(self.MIN_PX, self.MAX_PX)
        self.height_spin.setValue(self._cur_h)
        form.addRow("Width:", self.width_spin)
        form.addRow("Height:", self.height_spin)

        # Unit toggle: "pixels" (default) / "percent".
        self.unit_combo = QComboBox(self)
        self.unit_combo.addItems(["pixels", "percent"])
        form.addRow("Units:", self.unit_combo)

        # Aspect lock (D-13): checked by default.
        self.aspect_check = QCheckBox("Maintain aspect ratio", self)
        self.aspect_check.setChecked(True)
        form.addRow("", self.aspect_check)

        # Live result label (muted; in % mode it shows the resulting pixels).
        self.result_label = QLabel("", self)
        self.result_label.setObjectName("resultLabel")
        form.addRow("Result:", self.result_label)

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

        self.width_spin.valueChanged.connect(lambda _v: self._recompute("w"))
        self.height_spin.valueChanged.connect(lambda _v: self._recompute("h"))
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        self.aspect_check.toggled.connect(lambda _c: self._recompute("w"))

        self._recompute("w")  # initial result label

    # ---------------------------------------------------------------- driver
    def _result_pixels(self) -> tuple[int, int]:
        """Resolve the current control values to final pixel dims.

        In px mode the spinboxes ARE pixels; in % mode each value is the
        percent of the corresponding CURRENT dimension (rounded int, >= 1 —
        UI-SPEC surface 26).
        """
        if self.unit_combo.currentIndex() == 1:  # percent
            w = max(1, int(round(self._cur_w * self.width_spin.value() / 100)))
            h = max(1, int(round(self._cur_h * self.height_spin.value() / 100)))
            return w, h
        return self.width_spin.value(), self.height_spin.value()

    def _recompute(self, edited: str) -> None:
        """Apply the aspect lock + refresh the live result label.

        Locked (D-13): editing the dominant field recomputes the other —
        px mode scales by the current aspect ratio, % mode keeps both
        percents equal (they apply to the same current dims, so equal
        percents preserve the ratio). Both paths round and clamp to >= 1.
        ``_updating`` guards the recompute's own setValue from re-entering.
        """
        if self._updating:
            return
        self._updating = True
        try:
            if self.aspect_check.isChecked():
                if self.unit_combo.currentIndex() == 1:  # percent
                    if edited == "w":
                        self.height_spin.setValue(self.width_spin.value())
                    else:
                        self.width_spin.setValue(self.height_spin.value())
                else:  # pixels
                    if edited == "w":
                        w = self.width_spin.value()
                        self.height_spin.setValue(
                            max(1, int(round(w * self._cur_h / self._cur_w)))
                        )
                    else:
                        h = self.height_spin.value()
                        self.width_spin.setValue(
                            max(1, int(round(h * self._cur_w / self._cur_h)))
                        )
        finally:
            self._updating = False
        self._update_result_label()

    def _on_unit_changed(self, index: int) -> None:
        """Toggle px/% keeping the current RESULT stable (values convert).

        Switching units re-ranges the spinboxes and converts the values so
        the result label does not jump: px -> the percent reproducing the
        current pixels; % -> the pixels reproducing the current percents.
        """
        if self._updating:
            return
        self._updating = True
        try:
            w = self.width_spin.value()
            h = self.height_spin.value()
            if index == 1:  # to percent
                self.width_spin.setRange(self.MIN_PCT, self.MAX_PCT)
                self.height_spin.setRange(self.MIN_PCT, self.MAX_PCT)
                self.width_spin.setValue(max(1, int(round(w * 100 / self._cur_w))))
                self.height_spin.setValue(max(1, int(round(h * 100 / self._cur_h))))
            else:  # to pixels
                self.width_spin.setRange(self.MIN_PX, self.MAX_PX)
                self.height_spin.setRange(self.MIN_PX, self.MAX_PX)
                self.width_spin.setValue(max(1, int(round(self._cur_w * w / 100))))
                self.height_spin.setValue(max(1, int(round(self._cur_h * h / 100))))
        finally:
            self._updating = False
        self._update_result_label()

    def _update_result_label(self) -> None:
        """Refresh the muted 'Result: {w} × {h} px' label (always pixels)."""
        w, h = self._result_pixels()
        self.result_label.setText(f"Result: {w} \u00d7 {h} px")

    def _on_apply(self) -> None:
        """Store the resolved pixel dims and accept (no canvas mutation)."""
        self.result_values = self._result_pixels()
        self.accept()

"""Section bodies for the unified side panel: Brush + Detection settings.

Phase 9 plan 09-02 (D-03): the ToolsPanel's tool row relocated to the
vertical ``ToolsStrip`` in plan 09-01; this module now provides the two
remaining section BODIES that MainWindow embeds inside ``CollapsibleSection``
wrappers in the unified "Panel" dock:

- :class:`BrushBody` — the brush-size label + slider/spinbox row (UI-SPEC
  surface 6: QSlider (1-300) + QSpinBox (1-300), label
  ``"Brush size: {n} px"``, default 40 px, slider<->spinbox sync).
- :class:`DetectionSettingsBody` — the full Phase 8 detection-settings form
  (UI-SPEC §36): Detect Boxes toggle + dilation radius slider/spinbox mirror
  + std-dev threshold + max-inpaint size + the seven next-detect fit params.

Signal survival contract (09-UI-SPEC §38): every relocated control keeps its
existing signal EXACTLY — ``brush_size_changed``, ``detect_boxes_changed``,
``dilation_changed``, ``std_dev_threshold_changed``, ``masker_params_changed``
— because tests emit them directly off the widget and MainWindow wires them
to its commit handlers. The slider↔spinbox blockSignals mirror pairs moved
verbatim (never rewritten during relocation).

Per D-10 this is patterned after MangaCleaner_GPU ``frontend/widgets.py``
``BrushSlider`` (reference-only per D-12 — no LICENSE, cannot be vendored;
reimplemented with a synced ``QSlider``+``QSpinBox`` pair per UI-SPEC surface
6, which contracts the spinbox MangaCleaner_GPU omits).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from manga_ai_studio.core.mask_editor import (
    DEFAULT_BRUSH_SIZE,
    MAX_BRUSH_SIZE,
    MIN_BRUSH_SIZE,
)

# Dark QSS shared by the two section bodies (the _TOOLS_QSS tokens — bg
# #2d2d33, border #3a3a42, fg #e8e8ea). The checked-tool accent rule is gone
# with the tool row (the strip owns the active-tool highlight now).
_BODY_QSS = """
QLabel { color: #e8e8ea; }
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
QSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 1px 4px;
    color: #e8e8ea;
}
QDoubleSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 1px 4px;
    color: #e8e8ea;
}
QCheckBox {
    color: #e8e8ea;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
}
"""


class BrushBody(QWidget):
    """The Brush section body: label + slider + spinbox (moved verbatim).

    Signal:
        - ``brush_size_changed(int)`` — emitted when the brush size changes
          (slider or spinbox), exactly once per user change.
    """

    # Emitted when the brush size changes (slider or spinbox).
    brush_size_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("brush_body")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.brush_label = QLabel(f"Brush size: {DEFAULT_BRUSH_SIZE} px")
        lay.addWidget(self.brush_label)

        brush_row = QHBoxLayout()
        brush_row.setSpacing(4)  # xs (4px) slider<->spinbox gap (UI-SPEC §Spacing)
        self.brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setMinimum(MIN_BRUSH_SIZE)
        self.brush_slider.setMaximum(MAX_BRUSH_SIZE)
        self.brush_slider.setValue(DEFAULT_BRUSH_SIZE)

        self.brush_spinbox = QSpinBox()
        self.brush_spinbox.setMinimum(MIN_BRUSH_SIZE)
        self.brush_spinbox.setMaximum(MAX_BRUSH_SIZE)
        self.brush_spinbox.setValue(DEFAULT_BRUSH_SIZE)
        self.brush_spinbox.setSuffix(" px")

        # Slider <-> spinbox sync. blockSignals guards against recursion
        # (slider.valueChanged -> spinbox.setValue -> spinbox.valueChanged ->
        # slider.setValue ...). We mirror each to the other and emit once.
        self.brush_slider.valueChanged.connect(self._on_slider_changed)
        self.brush_spinbox.valueChanged.connect(self._on_spinbox_changed)

        brush_row.addWidget(self.brush_slider, 1)
        brush_row.addWidget(self.brush_spinbox)
        lay.addLayout(brush_row)

        self.setStyleSheet(_BODY_QSS)

    # ----------------------------------------------------------- brush size
    def _on_slider_changed(self, value: int) -> None:
        # Mirror to spinbox without recursion, update label, emit.
        self.brush_label.setText(f"Brush size: {value} px")
        was = self.brush_spinbox.blockSignals(True)
        self.brush_spinbox.setValue(value)
        self.brush_spinbox.blockSignals(was)
        self.brush_size_changed.emit(value)

    def _on_spinbox_changed(self, value: int) -> None:
        self.brush_label.setText(f"Brush size: {value} px")
        was = self.brush_slider.blockSignals(True)
        self.brush_slider.setValue(value)
        self.brush_slider.blockSignals(was)
        self.brush_size_changed.emit(value)

    def set_brush_size(self, value: int) -> None:
        """Programmatically set the brush size (keeps slider/spinbox in sync)."""
        was_s = self.brush_slider.blockSignals(True)
        was_sb = self.brush_spinbox.blockSignals(True)
        self.brush_slider.setValue(value)
        self.brush_spinbox.setValue(value)
        self.brush_slider.blockSignals(was_s)
        self.brush_spinbox.blockSignals(was_sb)
        self.brush_label.setText(f"Brush size: {value} px")


class DetectionSettingsBody(QWidget):
    """The Detection-settings section body (Phase 8 UI-SPEC §36, moved verbatim).

    Signals:
        - ``detect_boxes_changed(bool)`` — Detect Boxes toggle flipped (D-05).
        - ``dilation_changed(int)`` — dilation radius changed (D-06, LIVE).
        - ``std_dev_threshold_changed(float)`` — gate threshold changed
          (D-12, LIVE).
        - ``masker_params_changed()`` — any of the seven next-detect fit
          params changed (one persist + apply-next-detect fate, UI-SPEC §36).

    The section chrome (divider + header) is supplied by the wrapping
    ``CollapsibleSection``; this body carries only the control form.
    Tooltips are verbatim from the 08-UI-SPEC Copywriting table (which adapts
    the vendored ``MaskerConfig`` INI comments and appends the live/next-
    detect clauses — A12).
    """

    # Phase 8 detection-settings signals (plan 08-05, UI-SPEC surface 36).
    detect_boxes_changed = Signal(bool)
    dilation_changed = Signal(int)
    std_dev_threshold_changed = Signal(float)
    masker_params_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("detection_settings_body")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        form = QFormLayout()
        form.setVerticalSpacing(6)  # the Inspector form rhythm (UI-SPEC §36)
        lay.addLayout(form)

        # 1. Detect Boxes (D-05) — relocated from the Tools menu (A8); the
        # checkbox is the single user-facing control. Default checked (A1).
        self.detect_checkbox = QCheckBox("Detect Boxes", self)
        self.detect_checkbox.setChecked(True)
        self.detect_checkbox.setToolTip(
            "When on, Detect Text creates editable text boxes and keeps only"
            " detected text inside them in the mask. Off: the full heatmap"
            " goes into the mask (original behavior)."
        )
        self.detect_checkbox.toggled.connect(self.detect_boxes_changed)
        form.addRow(self.detect_checkbox)

        # 2. Dilation radius (D-06/D-09) — slider + spinbox mirror (the brush-row
        # blockSignals pattern). LIVE: re-dilates the current page.
        radius_tip = (
            "Grow auto-detected masks by this many pixels so the edges of"
            " letters are covered (default 2). Applies to detected masks"
            " only — hand-painted strokes are never dilated. Changing it"
            " re-dilates the current page immediately."
        )
        self.dilation_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.dilation_slider.setMinimum(0)
        self.dilation_slider.setMaximum(10)
        self.dilation_slider.setValue(2)
        self.dilation_slider.setToolTip(radius_tip)
        self.dilation_spinbox = QSpinBox(self)
        self.dilation_spinbox.setMinimum(0)
        self.dilation_spinbox.setMaximum(10)
        self.dilation_spinbox.setValue(2)
        self.dilation_spinbox.setSuffix(" px")
        self.dilation_spinbox.setToolTip(radius_tip)
        self.dilation_slider.valueChanged.connect(self._on_dilation_slider_changed)
        self.dilation_spinbox.valueChanged.connect(self._on_dilation_spinbox_changed)
        radius_row = QHBoxLayout()
        radius_row.setSpacing(4)  # xs (4px) slider<->spinbox gap
        radius_row.addWidget(self.dilation_slider, 1)
        radius_row.addWidget(self.dilation_spinbox)
        form.addRow("Dilation radius", radius_row)

        # 3. Std-dev threshold (D-06/D-12 — 08.1 Pitfall 5 inversion) — LIVE: border colors update live.
        self.std_dev_threshold_spin = QDoubleSpinBox(self)
        self.std_dev_threshold_spin.setMinimum(0)
        self.std_dev_threshold_spin.setMaximum(100)
        self.std_dev_threshold_spin.setSingleStep(0.5)
        self.std_dev_threshold_spin.setDecimals(1)
        self.std_dev_threshold_spin.setValue(15)
        self.std_dev_threshold_spin.setToolTip(
            "Color variation along this box's detected mask edge. At or below this is color-filled "
            "(solid border); above is AI-inpainted (solid). \"Fill\"/\"Never\" overrides fill/skip. "
            "Borders update live."
        )
        self.std_dev_threshold_spin.valueChanged.connect(
            self.std_dev_threshold_changed
        )
        form.addRow("Std-dev threshold", self.std_dev_threshold_spin)

        # 3b. Max LaMa input size (08.1 D-05) — user-capped patch size, persisted via profile INI.
        self.max_inpaint_spin = QSpinBox(self)
        self.max_inpaint_spin.setRange(512, 8192)
        self.max_inpaint_spin.setValue(2048)
        self.max_inpaint_spin.setSuffix(" px")
        self.max_inpaint_spin.setToolTip(
            "Maximum LaMa input size (largest side). Larger pages are patched; caps memory."
        )
        self.max_inpaint_spin.valueChanged.connect(self._on_fit_param_changed)
        form.addRow("Max inpaint size", self.max_inpaint_spin)

        # 4-10. The seven next-detect fit params (D-06) — they share ONE
        # persist + apply-next-detect fate (one signal, UI-SPEC §36).
        self.growth_step_spin = QSpinBox(self)
        self.growth_step_spin.setRange(0, 20)
        self.growth_step_spin.setValue(2)
        self.growth_step_spin.setSuffix(" px")
        self.growth_step_spin.setToolTip(
            "Number of pixels to grow candidate masks by each step. Smaller"
            " values are more accurate but slower. Applies on the next Detect"
            " Text."
        )
        self.growth_step_spin.valueChanged.connect(self._on_fit_param_changed)
        form.addRow("Growth step", self.growth_step_spin)

        self.growth_steps_spin = QSpinBox(self)
        self.growth_steps_spin.setRange(0, 50)
        self.growth_steps_spin.setValue(11)
        self.growth_steps_spin.setToolTip(
            "Number of growth steps to try. Higher values try more, larger"
            " masks, limited by the box size. Applies on the next Detect Text."
        )
        self.growth_steps_spin.valueChanged.connect(self._on_fit_param_changed)
        form.addRow("Growth steps", self.growth_steps_spin)

        self.min_thickness_spin = QSpinBox(self)
        self.min_thickness_spin.setRange(0, 50)
        self.min_thickness_spin.setValue(4)
        self.min_thickness_spin.setSuffix(" px")
        self.min_thickness_spin.setToolTip(
            "Minimum mask thickness — prevents very thin masks around text that"
            " only has an outline. Applies on the next Detect Text."
        )
        self.min_thickness_spin.valueChanged.connect(self._on_fit_param_changed)
        form.addRow("Min thickness", self.min_thickness_spin)

        self.off_white_spin = QSpinBox(self)
        self.off_white_spin.setRange(0, 255)
        self.off_white_spin.setValue(240)
        self.off_white_spin.setToolTip(
            "Pixels along a mask edge lighter than this are treated as pure"
            " white, so slightly off-white bubble backgrounds don't count as"
            " color variation. 0 (black) to 255 (pure white). Applies on the"
            " next Detect Text."
        )
        self.off_white_spin.valueChanged.connect(self._on_fit_param_changed)
        form.addRow("Off-white threshold", self.off_white_spin)

        self.improvement_spin = QDoubleSpinBox(self)
        self.improvement_spin.setRange(0, 1)
        self.improvement_spin.setSingleStep(0.01)
        self.improvement_spin.setDecimals(2)
        self.improvement_spin.setValue(0.10)
        self.improvement_spin.setToolTip(
            "How much a larger candidate mask must improve the edge variation"
            " to be preferred. Higher values favor smaller masks. Applies on"
            " the next Detect Text."
        )
        self.improvement_spin.valueChanged.connect(self._on_fit_param_changed)
        form.addRow("Improvement threshold", self.improvement_spin)

        self.allow_colored_check = QCheckBox("Allow colored masks", self)
        self.allow_colored_check.setChecked(True)  # vendored default
        self.allow_colored_check.setToolTip(
            "Let masks sit on any solid color, not only white, black, or gray."
            " Applies on the next Detect Text."
        )
        self.allow_colored_check.toggled.connect(self._on_fit_param_changed)
        form.addRow(self.allow_colored_check)

        self.fast_selection_check = QCheckBox("Fast mask selection", self)
        self.fast_selection_check.setChecked(False)  # vendored default
        self.fast_selection_check.setToolTip(
            "Pick the first good-enough mask instead of always searching for"
            " the best one. Faster, but may miss a slightly better fit."
            " Applies on the next Detect Text."
        )
        self.fast_selection_check.toggled.connect(self._on_fit_param_changed)
        form.addRow(self.fast_selection_check)

        self.setStyleSheet(_BODY_QSS)

    # The radius mirror emits ONE dilation_changed per user change — the mirror
    # write uses blockSignals (the brush-row pattern).
    def _on_dilation_slider_changed(self, value: int) -> None:
        was = self.dilation_spinbox.blockSignals(True)
        self.dilation_spinbox.setValue(value)
        self.dilation_spinbox.blockSignals(was)
        self.dilation_changed.emit(value)

    def _on_dilation_spinbox_changed(self, value: int) -> None:
        was = self.dilation_slider.blockSignals(True)
        self.dilation_slider.setValue(value)
        self.dilation_slider.blockSignals(was)
        self.dilation_changed.emit(value)

    def _on_fit_param_changed(self, *args) -> None:
        """Any of the seven next-detect controls changed — one shared signal."""
        self.masker_params_changed.emit()

    def masker_values(self) -> dict:
        """Read the fit params + max inpaint size as a profile-field-keyed dict.

        Keys match ``MaskerConfig`` field names so MainWindow's
        ``_on_masker_params_changed`` can ``setattr`` them onto
        ``profile.masker`` directly (plan 08-05, 08.1-03 D-05).
        """
        return {
            "mask_growth_step_pixels": self.growth_step_spin.value(),
            "mask_growth_steps": self.growth_steps_spin.value(),
            "min_mask_thickness": self.min_thickness_spin.value(),
            "off_white_max_threshold": self.off_white_spin.value(),
            "mask_improvement_threshold": self.improvement_spin.value(),
            "allow_colored_masks": self.allow_colored_check.isChecked(),
            "mask_selection_fast": self.fast_selection_check.isChecked(),
            "max_inpaint_resolution": self.max_inpaint_spin.value(),
        }

    def set_masker_values(self, masker_conf, detect_boxes: bool) -> None:
        """Programmatically populate the section from a MaskerConfig (D-10).

        Runs with blockSignals so a startup/load population never re-emits
        (the ``set_brush_size`` precedent) — MainWindow loads the persisted
        profile values at startup via this method without a save-back. Values
        are range-clamped at the widget level (T-08-09: invalid values are
        unreachable).
        """
        widgets = [
            self.dilation_slider,
            self.dilation_spinbox,
            self.std_dev_threshold_spin,
            self.max_inpaint_spin,
            self.growth_step_spin,
            self.growth_steps_spin,
            self.min_thickness_spin,
            self.off_white_spin,
            self.improvement_spin,
            self.allow_colored_check,
            self.fast_selection_check,
            self.detect_checkbox,
        ]
        prev = [w.blockSignals(True) for w in widgets]
        try:
            self.dilation_slider.setValue(masker_conf.mask_dilation_radius)
            self.dilation_spinbox.setValue(masker_conf.mask_dilation_radius)
            self.std_dev_threshold_spin.setValue(
                masker_conf.mask_max_standard_deviation
            )
            try:
                _max_val = int(getattr(masker_conf, "max_inpaint_resolution", 2048))
            except (TypeError, ValueError):
                _max_val = 2048
            self.max_inpaint_spin.setValue(_max_val)
            self.growth_step_spin.setValue(masker_conf.mask_growth_step_pixels)
            self.growth_steps_spin.setValue(masker_conf.mask_growth_steps)
            self.min_thickness_spin.setValue(masker_conf.min_mask_thickness)
            self.off_white_spin.setValue(masker_conf.off_white_max_threshold)
            self.improvement_spin.setValue(
                masker_conf.mask_improvement_threshold
            )
            self.allow_colored_check.setChecked(masker_conf.allow_colored_masks)
            self.fast_selection_check.setChecked(masker_conf.mask_selection_fast)
            self.detect_checkbox.setChecked(detect_boxes)
        finally:
            for widget, was in zip(widgets, prev):
                widget.blockSignals(was)


# Backwards-compat note: the old ``ToolsPanel`` class (tool row + these two
# bodies in one dock widget) was dissolved by plan 09-02 Task 2 — the tool
# row lives on ``ToolsStrip`` (plan 09-01) and the bodies above are embedded
# directly into the unified panel's CollapsibleSections.

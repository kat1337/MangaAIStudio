"""ToolsPanel — the 6-tool mask-editing panel + brush-size control.

Per D-10 this is our own reimplementation patterned after MangaCleaner_GPU
``frontend/widgets.py`` ``ToolGroup`` + ``BrushSlider`` (lines 21-88) —
reference-only per D-12 (the MangaCleaner_GPU binary distribution carries no
LICENSE, so it is all-rights-reserved and cannot be vendored). We reimplement
with a ``QActionGroup`` (exclusive checkable QActions rendered as
``QToolButton``s) plus a synced ``QSlider``+``QSpinBox`` brush-size pair,
per UI-SPEC surface 6 (which contracts the spinbox that MangaCleaner_GPU
omits).

UI-SPEC surface 6 contracts:
    - 6 exclusive tools: Move/Pan (V), Brush (B), Rectangle (R), Lasso (L),
      Eraser (E), Crop (G — the 6th tool, D-11; no brush-size row for crop).
      Active tool highlighted with accent ``#00d4ff`` (accent reserved use #1).
    - Brush size: ``QSlider`` (1-300) + ``QSpinBox`` (1-300), label
      ``"Brush size: {n} px"``, default 40 px.
    - Slider<->spinbox stay in sync; either emits ``brush_size_changed``.

Signals:
    - ``tool_changed(ToolMode)`` — emitted when an exclusive tool is checked.
    - ``brush_size_changed(int)`` — emitted when the brush size changes.
    - ``detect_boxes_changed(bool)`` — Detect Boxes toggle flipped (D-05).
    - ``dilation_changed(int)`` — dilation radius changed (D-06, LIVE).
    - ``std_dev_threshold_changed(float)`` — gate threshold changed (D-12, LIVE).
    - ``masker_params_changed()`` — any of the seven next-detect fit params
      changed (they share one persist + apply-next-detect fate; UI-SPEC §36).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from manga_ai_studio.core.mask_editor import (
    DEFAULT_BRUSH_SIZE,
    MAX_BRUSH_SIZE,
    MIN_BRUSH_SIZE,
    ToolMode,
)

# Dark QSS for the Tools panel (UI-SPEC §Color tokens). The checked tool button
# shows the accent active-tool highlight (#00d4ff 1px border on #2d2d33 — accent
# reserved use #1).
_TOOLS_QSS = """
QToolButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 3px;
    padding: 6px;
    color: #e8e8ea;
}
QToolButton:hover {
    border: 1px solid #5a5a64;
}
QToolButton:checked {
    background: #2d2d33;
    border: 1px solid #00d4ff;
}
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
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
#_detection_divider {
    background: #3a3a42;
}
#_detection_section_header {
    color: #9a9aa2;
    font-weight: 600;
    font-size: 12px;
}
"""


class ToolsPanel(QWidget):
    """The Tools dock panel: 6 exclusive tool buttons + brush-size control."""

    # Emitted when the user selects a different tool (the active QAction
    # becomes checked). Carries the matching ToolMode.
    tool_changed = Signal(object)
    # Emitted when the brush size changes (slider or spinbox).
    brush_size_changed = Signal(int)
    # Phase 8 detection-settings section (plan 08-05, UI-SPEC surface 36).
    detect_boxes_changed = Signal(bool)
    dilation_changed = Signal(int)
    std_dev_threshold_changed = Signal(float)
    masker_params_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tools_panel")

        # Panel shell: a vertical-only QScrollArea wrap (UI-SPEC §36 A11 —
        # "the dock never clips at 1024x720", A11 in the Resolved Assumptions).
        # The tool row + brush row stay pinned at the top of the scroll
        # content; the detection-settings section below them scrolls out of
        # view instead of being clipped on short windows.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.body_scroll = QScrollArea(self)
        self.body_scroll.setObjectName("tools_body_scroll")
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.body_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        # Frame-less: the scroll area must not draw chrome around the panel.
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        # sm (8px) contents margins + sm spacing (UI-SPEC §Spacing).
        self.body_layout.setContentsMargins(8, 8, 8, 8)
        self.body_layout.setSpacing(8)
        self.body_scroll.setWidget(body)
        root.addWidget(self.body_scroll)

        # ---- Tool row: 6 exclusive checkable QToolButtons ----
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        # Build the 6 actions. Text doubles as the tooltip; QToolButton renders
        # icon-only (UI-SPEC toolbar/dock icon style).
        self.action_move = self._make_tool_action(
            "Move/Pan", "Move/Pan tool (V)", ToolMode.MOVE, checked=True
        )
        self.action_brush = self._make_tool_action(
            "Brush",
            "Brush tool (B) — paints under text boxes; hold Alt to select or"
            " move a box.",
            ToolMode.BRUSH,
        )
        self.action_rectangle = self._make_tool_action(
            "Rectangle",
            "Rectangle tool (R) — paints under text boxes; hold Alt to select"
            " or move a box.",
            ToolMode.RECTANGLE,
        )
        self.action_lasso = self._make_tool_action(
            "Lasso",
            "Lasso tool (L) — paints under text boxes; hold Alt to select or"
            " move a box.",
            ToolMode.LASSO,
        )
        self.action_eraser = self._make_tool_action(
            "Eraser",
            "Eraser tool (E) — paints under text boxes; hold Alt to select or"
            " move a box.",
            ToolMode.ERASER,
        )
        # The 6th tool (D-11, plan 05-07): Crop defines a crop rect via an
        # armed drag (Enter applies, Esc cancels — UI-SPEC §Copywriting crop
        # tool row). No brush-size row (UI-SPEC surface 6 — crop needs no
        # size control).
        self.action_crop = self._make_tool_action(
            "Crop",
            "Crop tool (G): drag a rectangle on the page, Enter applies,"
            " Esc cancels.",
            ToolMode.CROP,
        )

        # QAction -> ToolMode lookup for the triggered slot.
        self._action_to_tool: dict[QAction, ToolMode] = {
            self.action_move: ToolMode.MOVE,
            self.action_brush: ToolMode.BRUSH,
            self.action_rectangle: ToolMode.RECTANGLE,
            self.action_lasso: ToolMode.LASSO,
            self.action_eraser: ToolMode.ERASER,
            self.action_crop: ToolMode.CROP,
        }
        # Connect each action's toggled signal so tool_changed fires whether the
        # action is activated by a click, a menu, a shortcut, or a programmatic
        # setChecked(True). The group's triggered signal only fires on user
        # activation, missing programmatic changes (e.g. set_active_tool).
        for act in self._action_to_tool:
            act.toggled.connect(self._on_action_toggled)

        # Render each action as an icon-only, checkable QToolButton in a row.
        tool_row = QHBoxLayout()
        tool_row.setSpacing(4)  # xs (4px) gap between buttons
        self.tool_buttons: list[QToolButton] = []
        for action in (
            self.action_move,
            self.action_brush,
            self.action_rectangle,
            self.action_lasso,
            self.action_eraser,
            self.action_crop,
        ):
            btn = QToolButton(self)
            btn.setDefaultAction(action)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            # Text label as accessible name (no icon assets bundled in Phase 1;
            # the text shows through QToolButton's tooltip).
            btn.setText(action.text())
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.tool_buttons.append(btn)
            tool_row.addWidget(btn)
        self.body_layout.addLayout(tool_row)

        # ---- Brush size: label + slider + spinbox ----
        self.brush_label = QLabel(f"Brush size: {DEFAULT_BRUSH_SIZE} px")
        self.body_layout.addWidget(self.brush_label)

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
        self.body_layout.addLayout(brush_row)

        self.body_layout.addStretch(1)

        # ---- Detection settings section (Phase 8, UI-SPEC surface 36) ----
        self._build_detection_settings_section()

        self.setStyleSheet(_TOOLS_QSS)

    # ------------------------------------------------------------- tool row
    def _make_tool_action(
        self,
        text: str,
        tooltip: str,
        tool: ToolMode,
        *,
        checked: bool = False,
    ) -> QAction:
        act = QAction(text, self)
        act.setToolTip(tooltip)
        act.setStatusTip(tooltip)
        act.setCheckable(True)
        act.setChecked(checked)
        act.setData(tool)
        self.tool_group.addAction(act)
        return act

    def _on_tool_triggered(self, action: QAction) -> None:
        """Emit tool_changed for the newly-checked tool (group.triggered path)."""
        tool = self._action_to_tool.get(action)
        if tool is not None:
            self.tool_changed.emit(tool)

    def _on_action_toggled(self, checked: bool) -> None:
        """Emit tool_changed when an action becomes checked (toggled path).

        Handles both user clicks (which also fire ``triggered``) and programmatic
        ``setChecked(True)`` calls (which only fire ``toggled``). Only emits on
        the transition to checked so a single selection produces one emission.
        """
        if not checked:
            return
        # Identify which action toggled via the sender().
        sender = self.sender()
        tool = self._action_to_tool.get(sender) if sender is not None else None
        if tool is not None:
            self.tool_changed.emit(tool)

    def set_active_tool(self, tool: ToolMode) -> None:
        """Programmatically check the tool's action (keeps panel in sync).

        The matching action is checked AND every other action is explicitly
        unchecked: ``blockSignals`` around ``setChecked`` would otherwise
        suppress the QActionGroup's exclusive unchecking (a Qt behavior —
        the group reacts to the action event, which blocked signals swallow),
        leaving the previous tool checked and ``active_tool()`` reporting
        the wrong tool (plan 05-07, the 6th-tool exclusivity contract).
        Signals stay blocked so no ``tool_changed`` re-emission happens when
        the change originates from outside the panel (e.g. the Tools menu or
        a keyboard shortcut) — the caller already knows the new tool.
        """
        for act, mode in self._action_to_tool.items():
            if mode == tool:
                was = act.blockSignals(True)
                act.setChecked(True)
                act.blockSignals(was)
            elif act.isChecked():
                was = act.blockSignals(True)
                act.setChecked(False)
                act.blockSignals(was)

    def active_tool(self) -> ToolMode:
        """Return the currently-checked tool's ToolMode."""
        for act, mode in self._action_to_tool.items():
            if act.isChecked():
                return mode
        return ToolMode.MOVE

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

    # ------------------------------------- detection settings (Phase 8)
    def _build_detection_settings_section(self) -> None:
        """Build the "Detection settings" section (UI-SPEC surface 36, D-05/D-06).

        Layout: 1px ``#3a3a42`` divider, 12px Semibold muted header (the Phase
        7 Style-header precedent), then ``QFormLayout`` rows (spacing 6px) with
        the relocated Detect Boxes toggle + the nine masker parameters. The two
        LIVE controls (dilation radius, std-dev threshold) emit their own
        signals; the seven fit params share one ``masker_params_changed`` fate.
        Tooltips are verbatim from the 08-UI-SPEC Copywriting table (which
        adapts the vendored ``MaskerConfig`` INI comments and appends the
        live/next-detect clauses — A12).
        """
        body = self.body_layout

        # 1px #3a3a42 divider above the header (UI-SPEC §36 section gap).
        divider = QFrame(self)
        divider.setObjectName("_detection_divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        body.addWidget(divider)

        section_header = QLabel("Detection settings")
        section_header.setObjectName("_detection_section_header")
        body.addWidget(section_header)

        form = QFormLayout()
        form.setVerticalSpacing(6)  # the Inspector form rhythm (UI-SPEC §36)
        body.addLayout(form)

        # 1. Detect Boxes (D-05) — relocated from the Tools menu (A8); the dock
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
        # blockSignals pattern, :275-288). LIVE: re-dilates the current page.
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

    # The radius mirror emits ONE dilation_changed per user change — the mirror
    # write uses blockSignals (the brush-row :275-288 pattern).
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
        (the ``set_brush_size`` :290-298 precedent) — MainWindow loads the
        persisted profile values at startup via this method without a
        save-back. Values are range-clamped at the widget level (T-08-09:
        invalid values are unreachable).
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

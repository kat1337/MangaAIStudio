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
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
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
"""


class ToolsPanel(QWidget):
    """The Tools dock panel: 6 exclusive tool buttons + brush-size control."""

    # Emitted when the user selects a different tool (the active QAction
    # becomes checked). Carries the matching ToolMode.
    tool_changed = Signal(object)
    # Emitted when the brush size changes (slider or spinbox).
    brush_size_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tools_panel")

        root = QVBoxLayout(self)
        # sm (8px) contents margins + sm spacing (UI-SPEC §Spacing).
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- Tool row: 6 exclusive checkable QToolButtons ----
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        # Build the 6 actions. Text doubles as the tooltip; QToolButton renders
        # icon-only (UI-SPEC toolbar/dock icon style).
        self.action_move = self._make_tool_action(
            "Move/Pan", "Move/Pan tool (V)", ToolMode.MOVE, checked=True
        )
        self.action_brush = self._make_tool_action(
            "Brush", "Brush tool (B)", ToolMode.BRUSH
        )
        self.action_rectangle = self._make_tool_action(
            "Rectangle", "Rectangle tool (R)", ToolMode.RECTANGLE
        )
        self.action_lasso = self._make_tool_action(
            "Lasso", "Lasso tool (L)", ToolMode.LASSO
        )
        self.action_eraser = self._make_tool_action(
            "Eraser", "Eraser tool (E)", ToolMode.ERASER
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
        root.addLayout(tool_row)

        # ---- Brush size: label + slider + spinbox ----
        self.brush_label = QLabel(f"Brush size: {DEFAULT_BRUSH_SIZE} px")
        root.addWidget(self.brush_label)

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
        root.addLayout(brush_row)

        root.addStretch(1)
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

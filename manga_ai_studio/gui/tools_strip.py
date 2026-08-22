"""ToolsStrip — vertical icon-only tool strip between the Pages dock and canvas.

Phase 9 plan 09-01 (UI-03 as corrected by D-05, D-04/D-06): the 6 exclusive
mask tools + Detect Text + Inpaint relocate off the top toolbar into a small
icon-only vertical strip embedded in the central widget, giving the window
left→right order **Pages | strip | canvas | side panel**.

Placement constraint (probe-verified, RESEARCH Pattern 2): a QMainWindow
left-area toolbar is laid out OUTSIDE the dock columns and ``setCorner()``
cannot change that — so this strip is NEVER added via ``addToolBar``. The
MainWindow embeds it as the first item of a horizontal container wrapping the
canvas.

Active-tool sync (WR-02 / 06 D-10 contract): the strip owns its own six
checkable QActions inside ONE exclusive ``QActionGroup`` that holds EXACTLY
those six actions. Each action's ``toggled`` connects to a checked-only
handler emitting ``tool_changed`` once per selection (the proven
ToolsPanel tool-row machinery relocated verbatim). The standalone WINDOW
``action_tool_*`` actions stay outside the group and are driven explicitly by
``MainWindow.set_active_tool``'s blockSignals loop — never connect both
``triggered`` and ``toggled``.

Detect Text / Inpaint are plain NON-checkable default-action buttons bound to
the WINDOW actions (``setDefaultAction``), so their enabled/running-state
gating from ``_refresh_action_states`` is inherited free.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QToolBar, QToolButton

from manga_ai_studio.core.mask_editor import ToolMode

# Module-relative icon directory (D-06). NEVER resolve icons relative to the
# CWD or any user-controlled input — only repo-bundled files under the gui
# package reach QIcon (threat T-09a-01).
_ICONS = Path(__file__).parent / "assets" / "icons"

# Bundled SVG stem per tool mode (all under _ICONS).
_TOOL_ICONS: dict[ToolMode, str] = {
    ToolMode.MOVE: "move",
    ToolMode.BRUSH: "brush",
    ToolMode.RECTANGLE: "rectangle",
    ToolMode.LASSO: "lasso",
    ToolMode.ERASER: "eraser",
    ToolMode.CROP: "crop",
}

# Strip button geometry (09-UI-SPEC §Spacing exceptions): 44px strip width,
# 36×36 square hit targets, 20px icon render size.
_STRIP_WIDTH = 44
_BTN_SIZE = 36
_ICON_SIZE = 20

# Dark QSS for the strip (09-UI-SPEC §Color): unchecked buttons flat on
# Secondary #2d2d33 with a 1px #3a3a42 border; the CHECKED button carries the
# accent active-tool highlight (#00d4ff 1px border — accent reserved use #1).
# The icon glyph stays neutral; the border IS the highlight.
_STRIP_QSS = """
QToolButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 3px;
    padding: 2px;
}
QToolButton:hover {
    background: #34343c;
    border: 1px solid #5a5a64;
}
QToolButton:checked {
    background: #2d2d33;
    border: 1px solid #00d4ff;
}
QToolButton:disabled {
    background: #25252b;
}
QToolBar {
    background: #232328;
    border: none;
    spacing: 2px;
}
"""


def _icon(name: str) -> QIcon:
    """Load a bundled strip SVG icon by name (module-relative resolution).

    Icons resolve ONLY from ``_ICONS`` (``Path(__file__).parent / "assets" /
    "icons"``) inside the gui package — never CWD-relative (Pitfall 6: null
    QIcon under pytest/workdir differences) and never user-controlled paths.
    """
    return QIcon(str(_ICONS / f"{name}.svg"))


class ToolsStrip(QToolBar):
    """Vertical icon-only strip: 6 exclusive tools + divider + Detect/Inpaint."""

    # Emitted when the user selects a different tool (the active strip QAction
    # becomes checked). Carries the matching ToolMode.
    tool_changed = Signal(object)

    def __init__(
        self,
        action_detect_text: QAction,
        action_inpaint: QAction,
        parent=None,
    ) -> None:
        super().__init__("Tools", parent)
        self.setObjectName("tools_strip")
        self.setOrientation(Qt.Orientation.Vertical)
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self.setFixedWidth(_STRIP_WIDTH)

        # ---- The strip's OWN six exclusive tool actions ----
        # Relocated verbatim from ToolsPanel's tool row (tools_panel.py:173-254,
        # plan 09-01 Task 1): one exclusive QActionGroup holding EXACTLY these
        # six actions, checked-only toggled emission.
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        self.action_move = self._make_tool_action(
            "Move/Pan", "Move/Pan tool (V)", ToolMode.MOVE, checked=True
        )
        # The brush-family tooltips carry the D-15 Alt clause verbatim (the
        # old ToolsPanel row's copy — relocated here with the row, plan 09-02).
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
        # Crop tooltip per UI-SPEC §Copywriting (inherited Phase 5 copy).
        self.action_crop = self._make_tool_action(
            "Crop",
            "Crop tool (G): drag a rectangle on the page, Enter applies,"
            " Esc cancels.",
            ToolMode.CROP,
        )

        # QAction -> ToolMode lookup for the toggled slot.
        self._action_to_tool: dict[QAction, ToolMode] = {
            self.action_move: ToolMode.MOVE,
            self.action_brush: ToolMode.BRUSH,
            self.action_rectangle: ToolMode.RECTANGLE,
            self.action_lasso: ToolMode.LASSO,
            self.action_eraser: ToolMode.ERASER,
            self.action_crop: ToolMode.CROP,
        }
        # Connect each action's toggled signal so tool_changed fires whether
        # the action is activated by a click or a programmatic setChecked(True).
        # The group's triggered signal only fires on user activation, missing
        # programmatic changes (e.g. set_active_tool) — keep exactly ONE
        # emission path (the checked-only toggled handler below).
        for act in self._action_to_tool:
            act.toggled.connect(self._on_action_toggled)

        # ---- Buttons: 6 checkable tool buttons (icon-only, D-06) ----
        # The icons live on the strip-owned actions (see _make_tool_action);
        # the buttons inherit them via setDefaultAction.
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
            btn.setCheckable(True)
            btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
            self.addWidget(btn)

        # ---- D-04 divider between the tool group and Detect/Inpaint ----
        self.addSeparator()

        # ---- Detect Text + Inpaint: plain non-checkable buttons mirroring
        # the WINDOW actions, so enablement/running-state gating from
        # _refresh_action_states follows automatically (default-action
        # tracking — no manual gating mirrors).
        #
        # The window actions are shared state holders (Tools menu) — their
        # icons must stay null (icons cover the strip only). Because a
        # default-action button re-syncs its icon FROM the action on every
        # action change (enabled/disabled flips included), each button
        # re-asserts its bundled icon on the action's `changed` signal.
        self.btn_detect = QToolButton(self)
        self.btn_detect.setDefaultAction(action_detect_text)
        self.btn_detect.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        self._bind_shared_action_icon(self.btn_detect, "detect-text")
        self.addWidget(self.btn_detect)

        self.btn_inpaint = QToolButton(self)
        self.btn_inpaint.setDefaultAction(action_inpaint)
        self.btn_inpaint.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        self._bind_shared_action_icon(self.btn_inpaint, "inpaint")
        self.addWidget(self.btn_inpaint)

        self.setStyleSheet(_STRIP_QSS)

    def _bind_shared_action_icon(self, btn: QToolButton, name: str) -> None:
        """Keep ``btn``'s bundled icon across the mirrored action's changes.

        QIcon re-assertion is idempotent (same module-relative path); the
        connected lambda never mutates the shared window action itself.
        """
        icon = _icon(name)
        btn.setIcon(icon)
        btn.defaultAction().changed.connect(lambda btn=btn, icon=icon: btn.setIcon(icon))

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
        # D-06: the icon lives ON the action (strip-private, rendered nowhere
        # else). A QToolButton bound via setDefaultAction re-syncs its icon
        # FROM the action whenever the action changes state (e.g. is
        # disabled) — a button-side-only icon would be wiped to null by that
        # sync, so the action itself must carry it.
        act.setIcon(_icon(_TOOL_ICONS[tool]))
        self.tool_group.addAction(act)
        return act

    def _on_action_toggled(self, checked: bool) -> None:
        """Emit tool_changed when an action becomes checked (toggled path).

        Handles both user clicks and programmatic ``setChecked(True)`` calls.
        Only emits on the transition to checked so a single selection produces
        exactly one emission (WR-02 single-emission contract).
        """
        if not checked:
            return
        # Identify which action toggled via the sender().
        sender = self.sender()
        tool = self._action_to_tool.get(sender) if sender is not None else None
        if tool is not None:
            self.tool_changed.emit(tool)

    def set_active_tool(self, tool: ToolMode) -> None:
        """Programmatically check the tool's action (keeps strip in sync).

        The matching action is checked AND every other action is explicitly
        unchecked: ``blockSignals`` around ``setChecked`` would otherwise
        suppress the QActionGroup's exclusive unchecking (a Qt behavior),
        leaving the previous tool checked and ``active_tool()`` reporting
        the wrong tool. Signals stay blocked so no ``tool_changed``
        re-emission happens when the change originates from outside the strip
        (e.g. a keyboard shortcut or the Tools menu) — the caller already
        knows the new tool.
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

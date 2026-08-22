"""Tests for the vertical tools strip (Phase 9, plan 09-01 — UI-03/D-04/D-05).

The strip is a vertical icon-only column embedded in the central widget,
positioned BETWEEN the Pages dock and the canvas (D-05: left→right window
order is Pages | strip | canvas | side panel). It holds exactly 8 buttons
top→bottom per D-04: Move/Pan (V), Brush (B), Rectangle (R), Lasso (L),
Eraser (E), Crop (G), then a visual divider, then Detect Text (D) and
Inpaint (C).

Contract guarded here (06 D-10 / WR-02): strip tool buttons are exclusive,
exactly ONE ``tool_changed`` emission fires per selection from every entry
path, and the Detect/Inpaint strip buttons mirror the WINDOW actions
(``setDefaultAction`` identity) so enablement gating is inherited free.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.mask_editor import ToolMode  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from manga_ai_studio.gui.tools_strip import ToolsStrip  # noqa: E402


def _window(qtbot, tmp_path) -> MainWindow:
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _strip_btn(strip: ToolsStrip, action) -> QToolButton:
    """Return the strip QToolButton whose defaultAction IS ``action``."""
    return next(
        btn
        for btn in strip.findChildren(QToolButton)
        if btn.defaultAction() is action
    )


# ---------------------------------------------------------------------------
# D-05 geometry: Pages | strip | canvas ordering by window x-coordinates
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_strip_sits_between_pages_dock_and_canvas(qtbot, tmp_path) -> None:
    """The strip's window-x sits strictly between the Pages dock's right edge
    and the canvas's left edge (D-05; probe-verified central-container
    embedding — NOT addToolBar on a left toolbar area)."""
    window = _window(qtbot, tmp_path)
    window.show()
    QApplication.processEvents()

    def win_x(widget) -> int:
        return widget.mapTo(window, QPoint(0, 0)).x()

    dock_pages_right = win_x(window.dock_pages) + window.dock_pages.width()
    strip_x = win_x(window.tools_strip)
    canvas_x = win_x(window.canvas)

    assert dock_pages_right <= strip_x, (
        f"strip x={strip_x} must not sit LEFT of the Pages dock "
        f"(right edge {dock_pages_right}) — addToolBar regression"
    )
    assert strip_x < canvas_x, (
        f"strip x={strip_x} must sit strictly LEFT of the canvas (x={canvas_x})"
    )


# ---------------------------------------------------------------------------
# D-04 membership: 8 buttons, exclusive group of exactly 6 tool actions
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_strip_membership_and_exclusivity(qtbot, tmp_path) -> None:
    """8 buttons total; the exclusive group holds EXACTLY the strip's own six
    tool actions (window action_tool_* stay standalone)."""
    window = _window(qtbot, tmp_path)
    strip = window.tools_strip

    buttons = [
        b
        for b in strip.findChildren(QToolButton)
        # QToolBar auto-creates an internal extension-popup button — not ours.
        if b.objectName() != "qt_toolbar_ext_button"
    ]
    assert len(buttons) == 8

    actions = strip.tool_group.actions()
    assert len(actions) == 6
    assert strip.tool_group.isExclusive()
    for act in actions:
        assert act.isCheckable()

    expected_modes = {
        ToolMode.MOVE,
        ToolMode.BRUSH,
        ToolMode.RECTANGLE,
        ToolMode.LASSO,
        ToolMode.ERASER,
        ToolMode.CROP,
    }
    assert {act.data() for act in actions} == expected_modes

    # The strip owns its own actions — the window actions are NOT members.
    for window_action in (
        window.action_tool_move,
        window.action_tool_brush,
        window.action_tool_rectangle,
        window.action_tool_lasso,
        window.action_tool_eraser,
        window.action_tool_crop,
    ):
        assert window_action not in actions
        assert window_action.actionGroup() is None

    # Move is checked initially (the default tool).
    assert strip.active_tool() == ToolMode.MOVE
    assert strip.action_move.isChecked()

    # Checking Brush unchecks Move (exclusive group).
    strip.action_brush.setChecked(True)
    assert not strip.action_move.isChecked()
    assert strip.active_tool() == ToolMode.BRUSH


@pytest.mark.gui
def test_strip_divider_between_crop_and_detect(qtbot, tmp_path) -> None:
    """Exactly one separator sits between the crop button and the Detect Text
    button (D-04: divider separating Detect/Inpaint from the tool group)."""
    window = _window(qtbot, tmp_path)
    strip = window.tools_strip

    acts = strip.actions()
    sep_indices = [i for i, a in enumerate(acts) if a.isSeparator()]
    assert len(sep_indices) == 1

    sep_idx = sep_indices[0]
    before = [a.defaultWidget() for a in acts[:sep_idx]]
    after = [a.defaultWidget() for a in acts[sep_idx + 1 :]]

    # Six tool buttons above the divider...
    assert len(before) == 6
    tool_buttons = [
        b
        for b in before
        if isinstance(b, QToolButton) and b.defaultAction() is strip.action_crop
    ]
    assert len(tool_buttons) == 1  # crop is the LAST button above the divider
    assert before[-1].defaultAction() is strip.action_crop

    # ...and the Detect/Inpaint buttons below it.
    assert len(after) == 2
    assert after[0].defaultAction() is window.action_detect_text
    assert after[1].defaultAction() is window.action_inpaint


# ---------------------------------------------------------------------------
# WR-02 single-emission contract from every entry path
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_strip_single_emission_per_selection(qtbot, tmp_path) -> None:
    """Checking a strip action emits tool_changed EXACTLY once with the new
    ToolMode; a programmatic set_active_tool emits ZERO additional signals."""
    window = _window(qtbot, tmp_path)
    strip = window.tools_strip

    emitted: list[ToolMode] = []
    strip.tool_changed.connect(lambda t: emitted.append(t))

    with qtbot.waitSignal(strip.tool_changed, timeout=1000) as blocker:
        strip.action_brush.setChecked(True)
    assert blocker.args == [ToolMode.BRUSH]
    assert emitted == [ToolMode.BRUSH]

    # The click path drove the canvas + window actions through set_active_tool.
    assert window.canvas.current_tool == ToolMode.BRUSH
    assert window.action_tool_brush.isChecked()
    assert window.action_tool_move.isChecked() is False

    # Programmatic path: syncs everywhere but emits NOTHING.
    window.set_active_tool(ToolMode.MOVE)
    QApplication.processEvents()
    assert emitted == [ToolMode.BRUSH]
    assert strip.active_tool() == ToolMode.MOVE
    assert window.action_tool_move.isChecked()


# ---------------------------------------------------------------------------
# Detect/Inpaint strip buttons mirror the WINDOW actions
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_detect_inpaint_buttons_mirror_window_actions(qtbot, tmp_path) -> None:
    """The Detect/Inpaint strip buttons' defaultAction identity-equals the
    window actions, and both start disabled with no page open (gating is
    inherited free via _refresh_action_states)."""
    window = _window(qtbot, tmp_path)
    strip = window.tools_strip

    detect_btn = _strip_btn(strip, window.action_detect_text)
    inpaint_btn = _strip_btn(strip, window.action_inpaint)

    assert detect_btn.defaultAction() is window.action_detect_text
    assert inpaint_btn.defaultAction() is window.action_inpaint

    # Plain non-checkable default-action buttons.
    assert detect_btn.defaultAction().isCheckable() is False
    assert inpaint_btn.defaultAction().isCheckable() is False

    # Fresh window: no page open -> both disabled (inherited gating).
    assert window.action_detect_text.isEnabled() is False
    assert window.action_inpaint.isEnabled() is False


# ---------------------------------------------------------------------------
# D-06 icon assets: 8 bundled module-relative SVGs, non-null QIcon
# ---------------------------------------------------------------------------

_ICON_NAMES = [
    "move",
    "brush",
    "rectangle",
    "lasso",
    "eraser",
    "crop",
    "detect-text",
    "inpaint",
]


@pytest.mark.gui
def test_strip_icons_bundled_and_non_null(qtbot, tmp_path) -> None:
    """All 8 buttons carry a non-null QIcon loaded from the module-relative
    assets directory (offscreen-safe — no pixel assertions, RESEARCH A5)."""
    from pathlib import Path

    from manga_ai_studio.gui import tools_strip as ts_module

    # The icon directory constant derives from the MODULE file location —
    # never the CWD (Pitfall 6 / threat T-09a-01 path containment).
    assert ts_module._ICONS == Path(ts_module.__file__).parent / "assets" / "icons"

    for name in _ICON_NAMES:
        path = ts_module._ICONS / f"{name}.svg"
        assert path.is_file(), f"missing bundled icon {name}.svg"
        assert not ts_module._icon(name).isNull(), f"null QIcon for {name}.svg"

    # Every strip button renders a non-null icon.
    window = _window(qtbot, tmp_path)
    strip = window.tools_strip
    for btn in strip.findChildren(QToolButton):
        if btn.objectName() == "qt_toolbar_ext_button":
            continue
        assert not btn.icon().isNull()


# ---------------------------------------------------------------------------
# D-07: the shrunken top toolbar
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_top_toolbar_shrunk_to_d07_contents(qtbot, tmp_path) -> None:
    """The top toolbar holds exactly the D-07 set — the 6 tool buttons, Detect
    Text, and Inpaint have LEFT it (they live on the strip now). The QAction
    objects themselves survive with their shortcuts (state/gating holders)."""
    window = _window(qtbot, tmp_path)

    widget_actions = [a for a in window.toolbar.actions() if not a.isSeparator()]
    # Plain actions render themselves; the Preview button was added as a
    # WIDGET (widgetForAction resolves it).
    plain_actions = [
        a
        for a in widget_actions
        if window.toolbar.widgetForAction(a) is not window.btn_preview_hold
    ]
    assert plain_actions == [
        window.action_open_folder,
        window.action_fit_to_window,
        window.action_actual_size,
        window.action_zoom_out,
        window.action_zoom_in,
        window.action_undo,
        window.action_redo,
        window.action_toggle_mask_overlay,
    ]

    # Preview (hold) is the only added WIDGET on the toolbar.
    assert window.toolbar.widgetForAction(
        [a for a in widget_actions if a not in plain_actions][0]
    ) is window.btn_preview_hold

    # Every removed entry is absent from the top toolbar's action list.
    for removed in (
        window.action_detect_text,
        window.action_inpaint,
        window.action_tool_move,
        window.action_tool_brush,
        window.action_tool_rectangle,
        window.action_tool_lasso,
        window.action_tool_eraser,
        window.action_tool_crop,
    ):
        assert removed not in widget_actions

    # The QActions remain alive as state holders with their shortcuts intact.
    from PySide6.QtGui import QKeySequence

    assert window.action_detect_text.shortcut() == QKeySequence("D")
    assert window.action_inpaint.shortcut() == QKeySequence("C")
    for action in (
        window.action_tool_move,
        window.action_tool_brush,
        window.action_tool_rectangle,
        window.action_tool_lasso,
        window.action_tool_eraser,
        window.action_tool_crop,
    ):
        assert action.isCheckable()


def test_strip_icon_assets_art_direction(tmp_path) -> None:
    """Each bundled SVG declares a 24x24 viewBox and strokes in #e8e8ea."""
    import re

    from manga_ai_studio.gui import tools_strip as ts_module

    for name in _ICON_NAMES:
        text = (ts_module._ICONS / f"{name}.svg").read_text(encoding="utf-8")
        assert 'viewBox="0 0 24 24"' in text, name
        assert "#e8e8ea" in text, name
        assert 'fill="none"' in text, name

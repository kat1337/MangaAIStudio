"""GUI tests for the Canvas Crop tool + numeric Crop… dialog (plan 05-07, PROJ-04).

Covers the 6th-tool surface (Task 1), the armed-rect state machine + dim-out
overlay (Task 2, TRACER), and the crop apply path (drop/clip + count flash +
one undo) + the numeric ``CropDialog`` (Task 3) against the real ``MainWindow``
(pytest-qt) with ``tmp_path`` fixture pages.

The crop gesture contract (UI-SPEC surface 24a): drag defines a crop rect
(CrossCursor, dim-out at rgba(0,0,0,0.45) z=880, cyan dashed border z=900,
8x8 scene-px minimum — smaller drags are no-ops); the rect stays ARMED after
release until Enter applies / Esc cancels; box interaction is unchanged while
the tool is active. The apply path funnels through ``_apply_geometry_op``
(plan 05-06) with ``core.image_ops.crop_page_with_boxes`` (plan 05-02): exact
slices, dropped-box count in the flash, ONE geometry undo entry.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image as PILImage
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsRectItem, QToolButton

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.box_model import USER, PageBox
from manga_ai_studio.core.mask_editor import ToolMode
from manga_ai_studio.gui.main_window import MainWindow
from manga_ai_studio.gui.tools_panel import ToolsPanel
from panelcleaner.structures import Box


# ---------------------------------------------------------------- helpers

def _window_with_page(qtbot, tmp_path, size=(60, 40)) -> MainWindow:
    """A MainWindow with one real page open (the canvas shows the page)."""
    folder = tmp_path / "chapter"
    folder.mkdir(parents=True, exist_ok=True)
    w, h = size
    PILImage.new("RGB", (w, h), color=(40, 80, 120)).save(folder / "page_01.png")
    pm = ProfileManager(tmp_path / "config")
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(folder)
    QApplication.processEvents()
    return window


def _drag_crop(window: MainWindow, p1, p2) -> None:
    """Drive a REAL Qt left-drag from scene ``p1`` to scene ``p2`` (viewport coords
    derived via ``mapFromScene`` so the events land at the desired scene pixels —
    the established test-event discipline)."""
    canvas = window.canvas
    vp = canvas.viewport()
    v1 = canvas.mapFromScene(QPointF(*p1))
    v2 = canvas.mapFromScene(QPointF(*p2))
    QTest.mousePress(
        vp,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(v1.x()), int(v1.y())),
    )
    QTest.mouseMove(vp, QPoint(int(v2.x()), int(v2.y())))
    QTest.mouseRelease(
        vp,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(v2.x()), int(v2.y())),
    )
    QApplication.processEvents()


def _dim_items(window: MainWindow) -> list:
    """The live crop dim-out overlay items (z=880 rects) on the canvas scene."""
    return [
        item
        for item in window.canvas.scene().items()
        if isinstance(item, QGraphicsRectItem) and item.zValue() == 880
    ]


def _seed_box(window: MainWindow, box: Box) -> PageBox:
    """Seed one user box (suppressed — no undo push)."""
    pb = PageBox(box=box, origin=USER)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pb], [])
    finally:
        window._suppress_boxes_push = False
    return pb


# ===========================================================================
# Task 1 — the 6th exclusive tool: panel button + Tools-menu action + G
# ===========================================================================

@pytest.mark.gui
def test_crop_is_sixth_exclusive_tool(qtbot) -> None:
    """ToolsPanel exposes a Crop action in the exclusive group (D-11).

    The action carries data == ToolMode.CROP and sits LAST in the group
    (after Eraser); activating it deactivates Brush and vice versa
    (QActionGroup exclusivity), and the panel emits ``tool_changed`` with the
    right ToolMode on each activation.
    """
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    crop_action = panel.action_crop
    assert crop_action.data() == ToolMode.CROP
    assert crop_action.actionGroup() is panel.tool_group

    tools = [panel._action_to_tool[a] for a in panel.tool_group.actions()]
    assert tools == [
        ToolMode.MOVE,
        ToolMode.BRUSH,
        ToolMode.RECTANGLE,
        ToolMode.LASSO,
        ToolMode.ERASER,
        ToolMode.CROP,
    ]

    emitted: list = []
    panel.tool_changed.connect(emitted.append)

    panel.action_crop.setChecked(True)
    assert panel.active_tool() == ToolMode.CROP
    assert panel.action_brush.isChecked() is False  # crop deactivated brush
    assert emitted[-1] == ToolMode.CROP

    panel.action_brush.setChecked(True)
    assert panel.action_crop.isChecked() is False  # ...and vice versa
    assert panel.active_tool() == ToolMode.BRUSH
    assert emitted[-1] == ToolMode.BRUSH


@pytest.mark.gui
def test_crop_action_in_tools_menu(qtbot, tmp_path) -> None:
    """The Tools-menu Crop action exists with the same data and wires end-to-end.

    Triggering it activates the tool everywhere (canvas + ToolsPanel,
    exclusive with the other tools); the G shortcut (window-level QShortcut,
    focus-robust per the V/B/R/L/E pattern) drives the same path. The toolbar
    carries a Crop button bound to the same action (data == ToolMode.CROP).
    """
    window = _window_with_page(qtbot, tmp_path)
    menu_action = window.action_tool_crop
    assert menu_action.data() == ToolMode.CROP
    assert "Enter applies" in menu_action.toolTip()

    # The toolbar button for Crop is wired to the same action.
    crop_btn = next(
        (
            btn
            for btn in window.toolbar.findChildren(QToolButton)
            if btn.defaultAction() is not None
            and btn.defaultAction().data() == ToolMode.CROP
        ),
        None,
    )
    assert crop_btn is not None

    # Triggering the menu action activates the tool everywhere.
    menu_action.trigger()
    QApplication.processEvents()
    assert window.canvas.current_tool == ToolMode.CROP
    assert window.tools_panel.active_tool() == ToolMode.CROP

    # Shortcut G triggers the same path (QShortcut registered on the window).
    window.set_active_tool(ToolMode.BRUSH)
    assert window.canvas.current_tool == ToolMode.BRUSH
    shortcut = next(
        sc for sc in window.findChildren(QShortcut) if sc.key().toString() == "G"
    )
    shortcut.activated.emit()
    QApplication.processEvents()
    assert window.canvas.current_tool == ToolMode.CROP
    assert window.tools_panel.active_tool() == ToolMode.CROP

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
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontInfo, QKeyEvent, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsRectItem, QToolButton

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.box_model import USER, PageBox
from manga_ai_studio.core.mask_editor import (
    ToolMode,
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.gui.crop_dialog import CropDialog
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


def _crop_ready(window: MainWindow) -> None:
    """Activate the Crop tool at 100% zoom.

    zoom_reset() makes the scene<->viewport round trip EXACT (the canvas
    auto-fits at page load — at the fractional fit zoom, QTest's int
    viewport delivery drifts the delivered scene rect, the documented 05-09
    artifact). The crop state machine is zoom-independent, so 100% keeps the
    geometry assertions exact.
    """
    window.set_active_tool(ToolMode.CROP)
    window.canvas.zoom_reset()
    QApplication.processEvents()


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


def _press_and_release(window: MainWindow, scene_pos) -> None:
    """A plain left press+release at a scene position (no move)."""
    canvas = window.canvas
    vp = canvas.viewport()
    v = canvas.mapFromScene(QPointF(*scene_pos))
    QTest.mousePress(
        vp,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(v.x()), int(v.y())),
    )
    QTest.mouseRelease(
        vp,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(v.x()), int(v.y())),
    )
    QApplication.processEvents()


def _key(window: MainWindow, key) -> None:
    """Deliver a raw keyPress to the canvas (the established test discipline —
    real delivery is intercepted by the window-level Esc/Ctrl+Z QShortcuts)."""
    canvas = window.canvas
    ev = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(ev)


def _preview_rect(window: MainWindow) -> QRectF | None:
    """The preview_item path as a rect (None when the path is empty)."""
    path = window.canvas.preview_item.path()
    if path.isEmpty():
        return None
    return path.boundingRect()


def _seed_box(window: MainWindow, box: Box) -> PageBox:
    """Seed one user box (suppressed — no undo push)."""
    pb = PageBox(box=box, origin=USER)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pb], [])
    finally:
        window._suppress_boxes_push = False
    return pb


def _seed_mask(window: MainWindow) -> np.ndarray:
    """Seed a binary mask (10:20 x 30:50) — returns the mask array."""
    img = window.canvas.get_image_numpy()
    h, w = img.shape[:2]
    mask_bin = np.zeros((h, w), dtype=np.uint8)
    mask_bin[10:20, 30:50] = 255
    window.canvas.set_mask(numpy_binary_to_mask_qimage(mask_bin))
    return mask_bin


def _seed_three_boxes(window: MainWindow) -> list[PageBox]:
    """Seed the D-16 scenario: one inside, one fully outside, one partial.

    All relative to the (10, 10, 100, 80) crop used by the apply tests:
    - inside  (10, 10, 30, 20)  -> kept, translated (0, 0, 20, 10)
    - outside (150, 120, 180, 150) -> dropped (fully outside)
    - partial (80, 60, 140, 120) -> clipped to (80, 60, 110, 90) ->
      translated (70, 50, 100, 80)
    """
    boxes = [
        PageBox(box=Box(10, 10, 30, 20), origin=USER),
        PageBox(box=Box(150, 120, 180, 150), origin=USER),
        PageBox(box=Box(80, 60, 140, 120), origin=USER),
    ]
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes(boxes, [])
    finally:
        window._suppress_boxes_push = False
    return boxes


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
def test_toolbar_buttons_track_active_tool(qtbot, tmp_path) -> None:
    """D-10 RED gate: toolbar tool buttons highlight the active tool on every
    entry path (programmatic set_active_tool, V/B/R/L/E/G shortcut, Tools-menu
    trigger), in sync with the ToolsPanel's active tool.

    The six window tool actions must be checkable members of the ToolsPanel's
    exclusive QActionGroup: the group's exclusivity unchecks the previous tool
    and the dock + toolbar always agree (UI-SPEC surface 31 / E3). Fails on
    the pre-fix code — a non-checkable action makes ``setChecked`` a no-op
    (QToolButton mirrors its default action's checkable state).
    """
    window = _window_with_page(qtbot, tmp_path)

    def toolbar_btn(mode: ToolMode) -> QToolButton:
        return next(
            btn
            for btn in window.toolbar.findChildren(QToolButton)
            if btn.defaultAction() is not None
            and btn.defaultAction().data() == mode
        )

    def checked_tools() -> list:
        return [
            btn.defaultAction().data()
            for btn in window.toolbar.findChildren(QToolButton)
            if btn.defaultAction() is not None
            and btn.defaultAction().data() is not None
            and btn.isChecked()
        ]

    # Test 4 (group membership): every window tool action lives in the
    # ToolsPanel's exclusive group.
    for action in (
        window.action_tool_move,
        window.action_tool_brush,
        window.action_tool_rectangle,
        window.action_tool_lasso,
        window.action_tool_eraser,
        window.action_tool_crop,
    ):
        assert action.actionGroup() is window.tools_panel.tool_group

    # Test 1 (programmatic path): set_active_tool checks the matching toolbar
    # button and unchecks the rest.
    window.set_active_tool(ToolMode.BRUSH)
    QApplication.processEvents()
    assert toolbar_btn(ToolMode.BRUSH).isChecked()
    assert checked_tools() == [ToolMode.BRUSH]
    # Test 5 (sync): the dock's active tool matches the toolbar's checked tool.
    assert window.tools_panel.active_tool() == ToolMode.BRUSH

    # Test 2 (shortcut path): the V QShortcut drives the same sync.
    shortcut = next(
        sc for sc in window.findChildren(QShortcut) if sc.key().toString() == "V"
    )
    shortcut.activated.emit()
    QApplication.processEvents()
    assert toolbar_btn(ToolMode.MOVE).isChecked()
    assert checked_tools() == [ToolMode.MOVE]
    assert window.tools_panel.active_tool() == ToolMode.MOVE

    # Test 3 (menu path): the Tools-menu Crop action triggers the same sync.
    window.action_tool_crop.trigger()
    QApplication.processEvents()
    assert toolbar_btn(ToolMode.CROP).isChecked()
    assert checked_tools() == [ToolMode.CROP]
    assert window.tools_panel.active_tool() == ToolMode.CROP


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


# ===========================================================================
# Task 2 (TRACER) — armed-rect state machine + dim-out overlay
# ===========================================================================

@pytest.mark.gui
def test_drag_arms_rect_enter_applies_esc_cancels(qtbot, tmp_path) -> None:
    """The TRACER gesture contract (UI-SPEC surface 24a): drag -> the rect
    stays ARMED after release (dim + preview persist); Enter applies (emits
    ``crop_committed`` with the armed scene rect, armed state cleared, tool
    STAYS active); Esc instead cancels (items removed, no signal, tool still
    active)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    _crop_ready(window)
    canvas = window.canvas
    emitted: list = []
    canvas.crop_committed.connect(emitted.append)

    # Drag 10,10 -> 110,90: the rect arms on release (dim + preview persist).
    _drag_crop(window, (10, 10), (110, 90))
    assert canvas._crop_rect == QRectF(10, 10, 100, 80)
    assert len(_dim_items(window)) == 4  # 4 composited dim rects, z=880
    assert all(item.zValue() == 880 for item in _dim_items(window))
    assert _preview_rect(window) == QRectF(10, 10, 100, 80)  # cyan border

    # Enter applies: crop_committed carries the armed scene rect; the armed
    # state clears; the Crop tool stays active.
    _key(window, Qt.Key.Key_Return)
    assert emitted == [QRectF(10, 10, 100, 80)]
    assert canvas._crop_rect is None
    assert _dim_items(window) == []
    assert _preview_rect(window) is None
    assert canvas.current_tool == ToolMode.CROP

    # Drag again, then Esc cancels: items removed, NO signal, tool stays.
    _drag_crop(window, (30, 30), (80, 70))
    assert canvas._crop_rect == QRectF(30, 30, 50, 40)
    assert len(_dim_items(window)) == 4
    _key(window, Qt.Key.Key_Escape)
    assert canvas._crop_rect is None
    assert _dim_items(window) == []
    assert _preview_rect(window) is None
    assert emitted == [QRectF(10, 10, 100, 80)]  # no extra emission
    assert canvas.current_tool == ToolMode.CROP


@pytest.mark.gui
def test_small_drag_noop(qtbot, tmp_path) -> None:
    """A <8x8 drag produces no armed rect, no overlay, no preview, no signal
    (UI-SPEC §Spacing exceptions + RESEARCH Pitfall 10)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    _crop_ready(window)
    canvas = window.canvas
    emitted: list = []
    canvas.crop_committed.connect(emitted.append)

    _drag_crop(window, (10, 10), (15, 15))  # 5x5 — below the 8x8 minimum
    assert canvas._crop_rect is None
    assert _dim_items(window) == []
    assert _preview_rect(window) is None

    _key(window, Qt.Key.Key_Return)  # Enter on nothing: no signal
    assert emitted == []
    _key(window, Qt.Key.Key_Escape)  # Esc on nothing: no crash, still active
    assert canvas.current_tool == ToolMode.CROP


@pytest.mark.gui
def test_dim_outlayers_geometry(qtbot, tmp_path) -> None:
    """The 4 dim rects composite EXACTLY the outside-of-crop region: union ==
    page minus the crop rect inflated by the 1px inset, pairwise
    non-overlapping, each within the page, fill rgba(0,0,0,0.45), z=880
    (UI-SPEC surface 24a + §Spacing exceptions)."""
    window = _window_with_page(qtbot, tmp_path, size=(100, 80))
    _crop_ready(window)

    _drag_crop(window, (10, 10), (60, 50))  # crop 50x40 at (10,10)
    items = _dim_items(window)
    assert len(items) == 4
    for item in items:
        assert item.zValue() == 880
        assert item.brush().color() == QColor(0, 0, 0, int(255 * 0.45))
        r = item.rect()
        assert r.left() >= 0 and r.top() >= 0
        assert r.right() <= 100 and r.bottom() <= 80

    # Union area == page minus crop inflated by the 1px inset (moat).
    page_area = 100 * 80
    inset = QRectF(10, 10, 50, 40).adjusted(-1, -1, 1, 1)
    expected_area = page_area - inset.width() * inset.height()
    union_area = sum(item.rect().width() * item.rect().height() for item in items)
    assert union_area == expected_area
    # Pairwise non-overlap (boundaries may touch — moat edges meet exactly).
    rects = [item.rect() for item in items]
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            inter = a.intersected(b)
            assert inter.width() <= 0 or inter.height() <= 0, (a, b)
    # The crop interior is NOT dimmed; a far page corner IS dimmed.
    assert not any(r.contains(QPointF(35, 30)) for r in rects)
    assert any(r.contains(QPointF(2, 2)) for r in rects)
    # The 1px moat around the crop edge is NOT dimmed.
    assert not any(r.contains(QPointF(9.5, 10.5)) for r in rects)
    assert not any(r.contains(QPointF(60.5, 50.5)) for r in rects)


@pytest.mark.gui
def test_box_press_still_selects(qtbot, tmp_path) -> None:
    """Pressing on a box while the Crop tool is active selects/moves it — the
    crop drag starts only on EMPTY canvas (UI-SPEC surface 24a, D-07)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    _seed_box(window, Box(20, 20, 80, 80))
    _crop_ready(window)
    canvas = window.canvas
    item = canvas._box_items[0]

    # Press on the box body: selects, does NOT start a crop.
    _press_and_release(window, (50, 50))
    assert item.isSelected() is True
    assert canvas._crop_drag_active is False
    assert canvas._crop_rect is None

    # Drag from the box body: MOVES the box (not a crop drag).
    _drag_crop(window, (50, 50), (70, 70))
    assert item.rect().topLeft() == QPointF(40, 40)
    assert canvas._crop_rect is None
    assert _dim_items(window) == []


@pytest.mark.gui
def test_clamp_to_page(qtbot, tmp_path) -> None:
    """Dragging beyond the page clamps the crop rect to the page bounds
    (UI-SPEC §UI Considerations overflow — no container overflow)."""
    window = _window_with_page(qtbot, tmp_path, size=(100, 80))
    _crop_ready(window)

    _drag_crop(window, (90, 70), (200, 120))
    assert window.canvas._crop_rect == QRectF(90, 70, 10, 10)
    # The crop touches the right + bottom page edges: only the top + left
    # dims exist (nothing to dim beyond the edges) — their union still
    # covers the page minus the (page-clamped) inflated crop exactly.
    items = _dim_items(window)
    assert 0 < len(items) <= 4
    union_area = sum(item.rect().width() * item.rect().height() for item in items)
    inset = QRectF(90, 70, 10, 10).adjusted(-1, -1, 1, 1).intersected(
        QRectF(0, 0, 100, 80)
    )
    assert union_area == 100 * 80 - inset.width() * inset.height()


@pytest.mark.gui
def test_tool_switch_clears_armed_crop(qtbot, tmp_path) -> None:
    """Switching AWAY from the Crop tool removes the armed rect + overlay
    (the armed state belongs to the active Crop session — switching tools is
    the exit, UI-SPEC surface 24a)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    _crop_ready(window)
    canvas = window.canvas

    _drag_crop(window, (10, 10), (110, 90))
    assert canvas._crop_rect is not None
    assert len(_dim_items(window)) == 4

    window.set_active_tool(ToolMode.BRUSH)
    assert canvas._crop_rect is None
    assert _dim_items(window) == []
    assert _preview_rect(window) is None
    # Enter after the switch: no crop is applied (nothing armed).
    emitted: list = []
    canvas.crop_committed.connect(emitted.append)
    _key(window, Qt.Key.Key_Return)
    assert emitted == []


# ===========================================================================
# Task 3 — crop apply (drop/clip + count flash + one undo) + Crop… dialog
# ===========================================================================

@pytest.mark.gui
def test_crop_apply_drop_clip_count(qtbot, tmp_path) -> None:
    """_apply_crop(10, 10, 100, 80) on a 200x160 page with 3 boxes (D-16):
    image + mask are the EXACT slices; the inside box translates; the
    fully-outside box is GONE; the partial box is clipped (bbox); the
    dropped count feeds the status flash; ONE geometry undo entry; one
    Ctrl+Z restores ALL THREE incl. the dropped box; geometry_altered True
    (D-22)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    pre = window.canvas.get_image_numpy().copy()
    mask_bin = _seed_mask(window)
    _seed_three_boxes(window)

    window._apply_crop(10, 10, 100, 80)
    QApplication.processEvents()

    # Image + mask: exact slices (D-18).
    now = window.canvas.get_image_numpy()
    assert np.array_equal(now, pre[10:90, 10:110])
    assert np.array_equal(mask_to_numpy_binary(window.canvas.get_mask()), mask_bin[10:90, 10:110])

    # Boxes: inside translated, outside dropped, partial clipped (D-16).
    kept = window.canvas.boxes_snapshot()
    assert [pb.box.as_tuple for pb in kept] == [
        (0, 0, 20, 10),  # inside, translated by (-10, -10)
        (70, 50, 100, 80),  # partial, clipped to the crop rect
    ]

    # Dropped-count flash (UI-SPEC §Copywriting crop row).
    assert (
        "Cropped. 1 box(es) were outside the crop and removed \u2014"
        " press Ctrl+Z to restore." in window.status_bar_left.text()
    )

    # ONE geometry undo entry across the three stores.
    hist = window.history
    stamps = {
        "image": hist._image_undo[-1][0],
        "mask": hist._mask_undo[-1][0],
        "boxes": hist._boxes_undo[-1][0],
    }
    assert stamps["image"] == stamps["mask"] == stamps["boxes"]
    assert len(hist._image_undo) == 1

    # geometry_altered True (D-22).
    assert window.image_files[0].geometry_altered is True

    # ONE Ctrl+Z restores ALL THREE incl. the dropped box.
    window.on_undo()
    QApplication.processEvents()
    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    assert np.array_equal(mask_to_numpy_binary(window.canvas.get_mask()), mask_bin)
    restored = window.canvas.boxes_snapshot()
    assert [pb.box.as_tuple for pb in restored] == [
        (10, 10, 30, 20),
        (150, 120, 180, 150),
        (80, 60, 140, 120),
    ]


@pytest.mark.gui
def test_crop_dialog_font_14px(qtbot) -> None:
    """D-12 typography: CropDialog's base font renders at 14px Body — dialog
    field values and labels (UI-SPEC typography table row)."""
    dlg = CropDialog(page_w=200, page_h=160)
    qtbot.addWidget(dlg)
    assert QFontInfo(dlg.font()).pixelSize() == 14


@pytest.mark.gui
def test_crop_dialog_contract(qtbot) -> None:
    """CropDialog opens at the FULL page bounds with live W−x / H−y recompute
    and apply-time re-validation (UI-SPEC surface 24b, E3 partial coverage):
    editing X to 50 recomputes the Width max to W−50; an out-of-range
    programmatic value keeps the dialog OPEN with corrected values; a valid
    Apply collects (x, y, w, h) and accepts."""
    dlg = CropDialog(page_w=200, page_h=160)
    qtbot.addWidget(dlg)

    # Opens at the full page bounds — never empty.
    assert dlg.x_spin.value() == 0
    assert dlg.y_spin.value() == 0
    assert dlg.w_spin.value() == 200
    assert dlg.h_spin.value() == 160
    assert dlg.x_spin.maximum() == 199
    assert dlg.y_spin.maximum() == 159

    # Editing X recomputes the Width range: W−x.
    dlg.x_spin.setValue(50)
    assert dlg.w_spin.maximum() == 150
    dlg.y_spin.setValue(60)
    assert dlg.h_spin.maximum() == 100

    # Out-of-range programmatic value (spinbox range widened — user input can
    # never exceed it): Apply corrects IN PLACE and the dialog stays open.
    dlg.w_spin.setRange(1, 5000)
    dlg.w_spin.setValue(5000)
    dlg.apply_btn.click()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert dlg.w_spin.value() == 150  # corrected to W−x

    # A valid Apply collects the values and accepts.
    dlg.apply_btn.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.result_values == (50, 60, 150, 100)


@pytest.mark.gui
def test_crop_dialog_apply_end_to_end(qtbot, tmp_path, monkeypatch) -> None:
    """Edit -> Crop… Apply runs the SAME crop semantics as the tool path
    (image/mask slices, drop/clip, count flash, ONE entry)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    pre = window.canvas.get_image_numpy().copy()
    mask_bin = _seed_mask(window)
    _seed_three_boxes(window)

    def _fake_exec(dlg):
        dlg.result_values = (10, 10, 100, 80)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CropDialog, "exec", _fake_exec)
    window._on_crop_dialog()
    QApplication.processEvents()

    assert np.array_equal(window.canvas.get_image_numpy(), pre[10:90, 10:110])
    kept = window.canvas.boxes_snapshot()
    assert [pb.box.as_tuple for pb in kept] == [(0, 0, 20, 10), (70, 50, 100, 80)]
    assert (
        "Cropped. 1 box(es) were outside the crop and removed" in window.status_bar_left.text()
    )
    assert window.history._image_undo[-1][0] == window.history._boxes_undo[-1][0]
    assert window.image_files[0].geometry_altered is True


@pytest.mark.gui
def test_crop_degenerate_noop(qtbot, tmp_path) -> None:
    """A degenerate _apply_crop (w=0 or out-of-bounds) is a SILENT no-op:
    no change, no undo entry, no crash (T-05-17)."""
    window = _window_with_page(qtbot, tmp_path, size=(200, 160))
    pre = window.canvas.get_image_numpy().copy()
    _seed_mask(window)
    _seed_three_boxes(window)

    window._apply_crop(0, 0, 0, 0)  # zero width
    window._apply_crop(0, 0, 500, 100)  # beyond the page
    window._apply_crop(-5, 0, 50, 50)  # negative origin
    QApplication.processEvents()

    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    assert not window.history.can_undo()
    assert window.image_files[0].geometry_altered is False
    assert [pb.box.as_tuple for pb in window.canvas.boxes_snapshot()] == [
        (10, 10, 30, 20),
        (150, 120, 180, 150),
        (80, 60, 140, 120),
    ]

"""GUI tests for the Phase 3 text-box interaction layer (plan 03-03).

Mirrors the ``tests/test_gui_canvas.py`` header (``pytest.importorskip`` +
``qtbot`` fixture + ``@pytest.mark.gui``). Two layers of tests:

- **Component-level** (Task 1): ``BoxItem`` + ``CornerHandle`` in isolation on a
  minimal ``QGraphicsScene`` — origin hues, selection-driven pen/fill, handle
  visibility tracking selection, ``current_box()`` int materialization (Pitfall 6).
- **Dispatch/integration** (Task 2): the full ``EditorCanvas`` box hit-test
  dispatch — select single (D-08), move, resize corner clamp (D-06), delete
  silent (D-12), Alt+drag create (D-13), hidden layer no hit (Pitfall 5),
  boxes_snapshot detached (Pitfall 3).

These tests need a display; on headless CI they skip via ``importorskip``.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401  (mirrors test_gui_canvas header)

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QTransform  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QGraphicsScene,
    QMessageBox,
)

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.core.mask_editor import ToolMode  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.box_item import BoxItem, CornerHandle  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.inline_editor import InlineEditor  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _solid_pixmap(size: int, color: QColor) -> "QImage":  # type: ignore[name-defined]
    """Build a solid-color QPixmap of the given size (mirrors test_gui_canvas)."""
    from PySide6.QtGui import QPixmap

    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


def _scene_with_box(pagebox: PageBox) -> tuple[QGraphicsScene, BoxItem]:
    """Build a minimal scene owning a BoxItem (selection needs scene membership)."""
    scene = QGraphicsScene()
    item = BoxItem(pagebox)
    scene.addItem(item)
    return scene, item


# ===========================================================================
# Task 1 — component-level BoxItem / CornerHandle tests (RED gate)
# ===========================================================================


@pytest.mark.gui
def test_boxitem_detected_pen_is_green(qtbot) -> None:
    """A detected-origin BoxItem has pen color #5fd068 (D-09)."""
    pb = PageBox(box=Box(10, 20, 110, 220), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    assert item.pen().color().name().lower() == "#5fd068"


@pytest.mark.gui
def test_boxitem_user_pen_is_amber(qtbot) -> None:
    """A user-origin BoxItem has pen color #f5a623 (D-09)."""
    pb = PageBox(box=Box(10, 20, 110, 220), origin=USER)
    _scene, item = _scene_with_box(pb)
    assert item.pen().color().name().lower() == "#f5a623"


@pytest.mark.gui
def test_boxitem_rect_matches_pagebox_xywh(qtbot) -> None:
    """BoxItem(pagebox) renders a QRectF(x, y, w, h) from Box.as_tuple_xywh (D-05)."""
    pb = PageBox(box=Box(10, 20, 110, 220), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    r = item.rect()
    # Box(10,20,110,220) -> as_tuple_xywh = (10, 20, 100, 200)
    assert (int(r.x()), int(r.y()), int(r.width()), int(r.height())) == (10, 20, 100, 200)


@pytest.mark.gui
def test_boxitem_z_value_is_100(qtbot) -> None:
    """BoxItem sits at z=100 (above mask_item, below preview_item z=900 — UI-SPEC §Z-order)."""
    pb = PageBox(box=Box(0, 0, 50, 50), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    assert item.zValue() == 100


@pytest.mark.gui
def test_boxitem_unselected_pen_width_is_2(qtbot) -> None:
    """An unselected BoxItem has a 2px pen (UI-SPEC §12c)."""
    pb = PageBox(box=Box(0, 0, 50, 50), origin=USER)
    _scene, item = _scene_with_box(pb)
    assert item.isSelected() is False
    assert int(item.pen().width()) == 2


@pytest.mark.gui
def test_boxitem_unselected_has_no_brush(qtbot) -> None:
    """An unselected BoxItem has NoBrush (transparent fill — UI-SPEC §12a)."""
    pb = PageBox(box=Box(0, 0, 50, 50), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
def test_boxitem_selected_pen_width_is_3_and_tinted_brush(qtbot) -> None:
    """Selecting a BoxItem thickens the pen to 3px and applies a hue-tinted fill (UI-SPEC §12c)."""
    scene = QGraphicsScene()
    pb = PageBox(box=Box(0, 0, 50, 50), origin=DETECTED)
    item = BoxItem(pb)
    scene.addItem(item)
    # setSelected only takes effect on an item in a scene; clear then select.
    scene.clearSelection()
    item.setSelected(True)
    assert item.isSelected() is True
    assert int(item.pen().width()) == 3
    assert item.brush().style() != Qt.BrushStyle.NoBrush
    # The tint is the same hue as the border (green for detected) at ~0.12 alpha.
    brush_color = item.brush().color()
    assert brush_color.name().lower() == "#5fd068"
    # alpha 31 ~= 0.12 (UI-SPEC §12a "rgba(hue, 0.12)").
    assert 25 <= brush_color.alpha() <= 40


@pytest.mark.gui
def test_boxitem_has_four_corner_handles(qtbot) -> None:
    """A BoxItem carries exactly 4 CornerHandle children TL/TR/BL/BR."""
    pb = PageBox(box=Box(0, 0, 100, 100), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    handles = [c for c in item.childItems() if isinstance(c, CornerHandle)]
    assert len(handles) == 4
    corners = {h.corner for h in handles}
    assert corners == {"TL", "TR", "BL", "BR"}


@pytest.mark.gui
def test_corner_handle_is_8x8_and_ignores_transform(qtbot) -> None:
    """CornerHandles are 8x8 viewport px with ItemIgnoresTransformations (UI-SPEC §12b)."""
    from PySide6.QtWidgets import QGraphicsItem

    pb = PageBox(box=Box(0, 0, 100, 100), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    handles = [c for c in item.childItems() if isinstance(c, CornerHandle)]
    for h in handles:
        assert int(h.rect().width()) == 8
        assert int(h.rect().height()) == 8
        assert h.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations


@pytest.mark.gui
def test_corner_handle_z_value_is_150(qtbot) -> None:
    """CornerHandles sit at z=150 (above the box border at z=100 — UI-SPEC §Z-order)."""
    pb = PageBox(box=Box(0, 0, 100, 100), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    handles = [c for c in item.childItems() if isinstance(c, CornerHandle)]
    for h in handles:
        assert h.zValue() == 150


@pytest.mark.gui
def test_corner_handle_diagonal_cursors(qtbot) -> None:
    """TL/BR handles use SizeFDiagCursor; TR/BL use SizeBDiagCursor (UI-SPEC §12b)."""
    pb = PageBox(box=Box(0, 0, 100, 100), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    handles = {h.corner: h for h in item.childItems() if isinstance(h, CornerHandle)}
    assert handles["TL"].cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    assert handles["BR"].cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    assert handles["TR"].cursor().shape() == Qt.CursorShape.SizeBDiagCursor
    assert handles["BL"].cursor().shape() == Qt.CursorShape.SizeBDiagCursor


@pytest.mark.gui
def test_handles_visible_only_when_selected(qtbot) -> None:
    """CornerHandles are visible ONLY on the selected box (D-08 single-select)."""
    scene = QGraphicsScene()
    pb = PageBox(box=Box(0, 0, 100, 100), origin=DETECTED)
    item = BoxItem(pb)
    scene.addItem(item)

    handles = [c for c in item.childItems() if isinstance(c, CornerHandle)]
    # Unselected -> all handles hidden.
    scene.clearSelection()
    assert item.isSelected() is False
    for h in handles:
        assert h.isVisible() is False

    # Selected -> all handles shown.
    item.setSelected(True)
    assert item.isSelected() is True
    for h in handles:
        assert h.isVisible() is True


@pytest.mark.gui
def test_boxitem_current_box_materializes_ints(qtbot) -> None:
    """current_box() returns a fresh vendored Box with int coords from the live rect (Pitfall 6)."""
    pb = PageBox(box=Box(10, 20, 110, 220), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    box = item.current_box()
    assert isinstance(box, Box)
    assert (box.x1, box.y1, box.x2, box.y2) == (10, 20, 110, 220)
    # All coords must be ints (Pitfall 6 — int at the Box<->QRectF boundary).
    for coord in (box.x1, box.y1, box.x2, box.y2):
        assert isinstance(coord, int)


@pytest.mark.gui
def test_boxitem_current_box_is_detached_from_rect(qtbot) -> None:
    """Mutating the BoxItem rect AFTER current_box() does not change the returned Box (Pitfall 6)."""
    pb = PageBox(box=Box(10, 20, 110, 220), origin=DETECTED)
    _scene, item = _scene_with_box(pb)
    box = item.current_box()
    captured_x2 = box.x2
    # Now move the rect.
    item.setRect(QRectF(10, 20, 200, 200))
    # The previously-materialized box must be unchanged (fresh materialization).
    assert box.x2 == captured_x2


@pytest.mark.gui
def test_boxitem_composes_pagebox_not_subclasses_box(qtbot) -> None:
    """BoxItem composes a PageBox; it is NOT a vendored Box subclass (D-14 anti-pattern)."""
    pb = PageBox(box=Box(0, 0, 10, 10), origin=USER)
    _scene, item = _scene_with_box(pb)
    assert isinstance(item.pagebox, PageBox)
    assert not isinstance(item, Box)


# ===========================================================================
# Task 2 — dispatch / integration tests against a real EditorCanvas (RED gate)
# ===========================================================================
#
# These exercise the box hit-test dispatch slotted into EditorCanvas between the
# pan branch and the mask-tool branch (UI-SPEC §12d), plus the create/move/
# resize/delete interactions. The helpers mirror test_gui_canvas.py's
# _press/_move/_release (map scene coords back to viewport coords).


def _canvas_with_image_and_boxes(qtbot, size: int = 200) -> EditorCanvas:
    """Build a shown canvas with an image + the box layer visible + boxes_enabled.

    Mirrors test_gui_canvas._canvas_with_image but larger so a box + a corner
    handle don't collide with the image edge during resize-drag assertions.
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 400)
    canvas.set_image(_solid_pixmap(size, QColor("white")))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    return canvas


def _press_at(
    canvas: EditorCanvas, sx: float, sy: float, *, alt: bool = False
) -> QMouseEvent:
    """Build a left-button mouse-press whose viewport coords map to scene (sx, sy)."""
    vp = canvas.mapFromScene(QPointF(sx, sy))
    mods = Qt.KeyboardModifier.AltModifier if alt else Qt.KeyboardModifier.NoModifier
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        mods,
    )


def _move_at(canvas: EditorCanvas, sx: float, sy: float) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(vp),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release_at(canvas: EditorCanvas, sx: float, sy: float) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _dblclick_at(canvas: EditorCanvas, sx: float, sy: float) -> QMouseEvent:
    """Build a left-button DOUBLE-click whose viewport coords map to scene (sx, sy).

    Delivered directly to ``canvas.mouseDoubleClickEvent`` (synthesizing Qt's
    full press-release-press-release-dblclick sequence is flaky; the handler
    is the contract under test).
    """
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _add_user_box(canvas: EditorCanvas, box: Box) -> BoxItem:
    """Add a single user-origin box to the canvas layer and return the item."""
    canvas.set_boxes(user_pageboxes=[PageBox(box=box, origin=USER)], detected_pageboxes=[])
    return canvas._box_items[-1]


@pytest.mark.gui
def test_canvas_has_box_layer_and_hint(qtbot) -> None:
    """EditorCanvas constructs a box_layer (z=100) + empty_box_hint (z=850)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    assert canvas.box_layer is not None
    assert canvas.box_layer.zValue() == 100
    assert canvas.empty_box_hint is not None
    assert canvas.empty_box_hint.zValue() == 850
    # boxes_modified signal exists (mirrors mask_modified).
    assert hasattr(canvas, "boxes_modified")


@pytest.mark.gui
def test_canvas_empty_box_hint_visible_when_no_boxes(qtbot) -> None:
    """The empty-box hint shows when the layer is visible and zero boxes exist (§12f)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes([], [])
    assert canvas.has_boxes() is False
    # Layer visible + no boxes -> hint shown.
    assert canvas.box_layer.isVisible() is True
    assert canvas.empty_box_hint.isVisible() is True


@pytest.mark.gui
def test_select_single_box_deselects_others(qtbot) -> None:
    """A left-click on a box body selects it and deselects any other (D-08)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b = canvas._box_items
    assert a is not b

    # Click the center of box A.
    canvas.mousePressEvent(_press_at(canvas, 35, 35))
    assert a.isSelected() is True
    assert b.isSelected() is False

    # Click the center of box B -> B selected, A deselected.
    canvas.mousePressEvent(_press_at(canvas, 130, 130))
    assert b.isSelected() is True
    assert a.isSelected() is False


@pytest.mark.gui
def test_move_box_drag(qtbot) -> None:
    """Press on a box body + move + release moves the box rect (D-08 move)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _add_user_box(canvas, Box(20, 20, 80, 80))
    orig_x = item.rect().x()

    canvas.mousePressEvent(_press_at(canvas, 50, 50))  # center of box
    canvas.mouseMoveEvent(_move_at(canvas, 100, 100))
    canvas.mouseReleaseEvent(_release_at(canvas, 100, 100))

    # The box moved to the right + down.
    assert item.rect().x() > orig_x


@pytest.mark.gui
def test_box_drag_ignores_brush_cursor_overlay(qtbot) -> None:
    """The topmost brush cursor must not swallow a press on a box body."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _add_user_box(canvas, Box(20, 20, 80, 80))

    # Real pointer tracking places cursor_item at the press point.  It has a
    # higher z-value than the box, which used to make scene.itemAt() return the
    # cursor instead of the box and leave the interaction unarmed.
    canvas.mouseMoveEvent(_move_at(canvas, 50, 50))
    canvas.mousePressEvent(_press_at(canvas, 50, 50))
    canvas.mouseMoveEvent(_move_at(canvas, 100, 100))
    canvas.mouseReleaseEvent(_release_at(canvas, 100, 100))

    assert item.rect().x() > 20


@pytest.mark.gui
def test_resize_drag_ignores_brush_cursor_overlay(qtbot) -> None:
    """The brush cursor must not hide a selected corner handle from dispatch."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _add_user_box(canvas, Box(50, 50, 150, 150))
    item.setSelected(True)

    canvas.mouseMoveEvent(_move_at(canvas, 150, 150))
    canvas.mousePressEvent(_press_at(canvas, 150, 150))
    assert canvas._resizing_box is item
    canvas.mouseMoveEvent(_move_at(canvas, 180, 180))
    canvas.mouseReleaseEvent(_release_at(canvas, 180, 180))

    assert item.rect().width() > 100
    assert item.rect().height() > 100


@pytest.mark.gui
def test_resize_corner_clamps_to_min(qtbot) -> None:
    """Dragging a corner to collapse clamps the final rect to >= 8x8 scene px (D-06)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    # A box from (50,50) to (150,150) — 100x100.
    item = _add_user_box(canvas, Box(50, 50, 150, 150))
    item.setSelected(True)

    # The BR handle of a 100x100 box sits at scene (150,150). Drag it up-left
    # toward the TL corner to collapse the box, then release.
    canvas.mousePressEvent(_press_at(canvas, 150, 150))  # on the BR handle
    canvas.mouseMoveEvent(_move_at(canvas, 55, 55))  # near TL -> collapse
    canvas.mouseReleaseEvent(_release_at(canvas, 55, 55))

    r = item.rect()
    assert r.width() >= 8, f"width {r.width()} below 8px min"
    assert r.height() >= 8, f"height {r.height()} below 8px min"


@pytest.mark.gui
def test_delete_selected_box_silent(qtbot) -> None:
    """Delete key removes the selected box from _box_items and emits boxes_modified (D-12)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    canvas = _canvas_with_image_and_boxes(qtbot)
    _add_user_box(canvas, Box(20, 20, 80, 80))
    assert canvas.box_count() == 1

    emitted: list[None] = []
    canvas.boxes_modified.connect(lambda _before: emitted.append(None))

    # Select the box first (Delete only acts on the selected box).
    canvas.mousePressEvent(_press_at(canvas, 50, 50))
    assert canvas._box_items[0].isSelected() is True

    # Send Delete.
    del_key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(del_key)

    assert canvas.box_count() == 0
    assert len(canvas._box_items) == 0
    assert len(emitted) >= 1  # boxes_modified fired


@pytest.mark.gui
def test_alt_drag_creates_user_box(qtbot) -> None:
    """Alt + left-drag on empty canvas >= 8x8 creates a user BoxItem, selected (D-13)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    assert canvas.box_count() == 0

    # Alt+press on empty canvas, drag, release.
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
    canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))

    assert canvas.box_count() == 1
    new_item = canvas._box_items[0]
    assert new_item.pagebox.origin == USER
    assert new_item.isSelected() is True
    r = new_item.rect()
    assert r.width() >= 8 and r.height() >= 8


@pytest.mark.gui
def test_alt_drag_too_small_is_noop(qtbot) -> None:
    """An Alt+drag < 8x8 scene px creates no box (D-06/D-13 min on create-release)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 32, 32))  # 2x2 — below the 8x8 min
    canvas.mouseReleaseEvent(_release_at(canvas, 32, 32))
    assert canvas.box_count() == 0


@pytest.mark.gui
def test_create_preview_is_amber_dashed(qtbot) -> None:
    """During an Alt+drag box-create, the preview_item pen is amber dashed (UI-SPEC §12e)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
    pen = canvas.preview_item.pen()
    c = pen.color()
    # Amber create-preview: QColor(245, 166, 35, 200).
    assert (c.red(), c.green(), c.blue()) == (245, 166, 35)
    assert pen.style() == Qt.PenStyle.DashLine
    canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))


@pytest.mark.gui
def test_hidden_layer_no_box_hit_falls_through_to_mask(qtbot) -> None:
    """With the box layer hidden, a click where a box was paints mask (Pitfall 5)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    _add_user_box(canvas, Box(20, 20, 100, 100))
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(10)

    # Hide the box layer (Shift+M toggle). Hidden = not interactable.
    canvas.set_box_overlay_visible(False)
    assert canvas.box_layer.isVisible() is False

    # Before: the mask under the box center is transparent.
    assert canvas.get_mask().pixelColor(50, 50).alpha() == 0

    # A left-click + tiny drag where the box was must paint mask, not select.
    canvas.mousePressEvent(_press_at(canvas, 50, 50))
    canvas.mouseMoveEvent(_move_at(canvas, 55, 55))
    canvas.mouseReleaseEvent(_release_at(canvas, 55, 55))

    # Mask was painted (fall-through to the mask-tool branch worked).
    assert canvas.get_mask().pixelColor(52, 52).alpha() > 0
    # No box got selected (boxes disabled — Pitfall 5 belt-and-suspenders).
    assert all(not it.isSelected() for it in canvas._box_items)


@pytest.mark.gui
def test_boxes_snapshot_detached(qtbot) -> None:
    """boxes_snapshot() returns fresh Boxes; mutating a BoxItem after does not change them (Pitfall 3)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    _add_user_box(canvas, Box(10, 10, 110, 110))
    snapshot = canvas.boxes_snapshot()
    assert len(snapshot) == 1
    captured = snapshot[0].box.as_tuple
    assert captured == (10, 10, 110, 110)

    # Mutate the live BoxItem's rect AFTER the snapshot.
    from PySide6.QtCore import QRectF

    canvas._box_items[0].setRect(QRectF(500, 500, 600, 600))
    # The snapshot list must be unchanged (detachment — Pitfall 3).
    assert snapshot[0].box.as_tuple == captured


@pytest.mark.gui
def test_boxes_snapshot_returns_pageboxes(qtbot) -> None:
    """boxes_snapshot() returns PageBox instances (the D-15 seam — .origin/.payload)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[PageBox(box=Box(10, 10, 50, 50), origin=USER, payload="p")],
        detected_pageboxes=[PageBox(box=Box(60, 60, 100, 100), origin=DETECTED)],
    )
    snap = canvas.boxes_snapshot()
    assert len(snap) == 2
    assert all(isinstance(p, PageBox) for p in snap)
    origins = {p.origin for p in snap}
    assert origins == {USER, DETECTED}


@pytest.mark.gui
def test_box_origin_counts(qtbot) -> None:
    """box_origin_counts() returns (detected, user) for the status-bar copy."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(0, 0, 20, 20), origin=USER),
            PageBox(box=Box(0, 0, 20, 20), origin=USER),
        ],
        detected_pageboxes=[PageBox(box=Box(0, 0, 20, 20), origin=DETECTED)],
    )
    detected, user = canvas.box_origin_counts()
    assert detected == 1
    assert user == 2


@pytest.mark.gui
def test_esc_deselects_box(qtbot) -> None:
    """Esc deselects the current box (UI-SPEC §12c / keyboard shortcut table)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _add_user_box(canvas, Box(20, 20, 80, 80))
    canvas.mousePressEvent(_press_at(canvas, 50, 50))
    assert item.isSelected() is True

    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(esc)
    assert item.isSelected() is False


@pytest.mark.gui
def test_mask_painting_still_works_with_box_layer_visible(qtbot) -> None:
    """Regression: with the box layer VISIBLE (no boxes), mask painting still works (fall-through)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(12)
    assert canvas.box_layer.isVisible() is True
    assert canvas.box_count() == 0  # empty layer — clicks fall through to mask

    canvas.mousePressEvent(_press_at(canvas, 50, 50))
    canvas.mouseMoveEvent(_move_at(canvas, 80, 50))
    canvas.mouseReleaseEvent(_release_at(canvas, 80, 50))

    assert canvas.get_mask().pixelColor(65, 50).alpha() > 0


# ===========================================================================
# Plan 03-06 — UAT test 2 hit-target regression (RED gate)
# ===========================================================================
#
# UAT test 2 diagnosed (03-UAT.md): the 8x8 viewport-px CornerHandle is centred
# ON the box corner, so ~half of it sits outside the box (reads as background/
# pixmap -> no-op) and the inner half overlaps the BoxItem body (-> triggers a
# move, not a resize). scene.itemAt returns a CornerHandle only in a ~6x6 central
# pocket; +-6px offsets return the BoxItem/pixmap. The fix is to enlarge ONLY the
# hit shape (not the painted handle) via CornerHandle.shape(). These tests
# exercise the SAME scene.itemAt(scene_pos, QTransform()) path the canvas uses
# (canvas.py:860), so a green here proves the production dispatch reaches the
# resize affordance on real off-centre clicks.


@pytest.mark.gui
def test_corner_handle_hit_target_covers_offset_zone(qtbot) -> None:
    """A selected box's corner is hittable within +-5px of the handle centre (UAT test 2).

    Before the fix these offset points return a BoxItem (or the pixmap) because
    the default 8x8 shape only covers the exact-centre pocket. The probe
    exercises ``scene.itemAt(scene_pos, QTransform())`` — the exact path
    ``canvas.py:860`` uses at 1:1 zoom (``self.transform()`` is identity at
    zoom 1.0), so green here means production dispatch reaches the resize
    affordance.
    """
    # Box(100,100,300,300) -> scene rect (100,100)-(300,300). BR corner = (300,300).
    _scene, item = _scene_with_box(PageBox(box=Box(100, 100, 300, 300), origin=DETECTED))
    # Selection makes the CornerHandle children visible + hittable (D-08).
    _scene.clearSelection()
    item.setSelected(True)
    br = item.handles["BR"]

    # Sanity: the painted visible handle is still 8x8 (UI-SPEC §12b) — the fix
    # must NOT change the painted geometry, only the invisible hit shape.
    assert int(br.rect().width()) == 8 and int(br.rect().height()) == 8

    # 1) Exact handle centre (the central pocket) STILL returns a CornerHandle.
    #    This already works today; the fix must not regress it.
    assert isinstance(_scene.itemAt(QPointF(300, 300), QTransform()), CornerHandle)

    # 2) The OFFSET zone (+-5px from the exact corner) now returns a CornerHandle.
    #    RED before the fix: these return the BoxItem (or the pixmap), because the
    #    default 8x8 shape only covers the central pocket.
    offset_probes = [
        QPointF(305, 305),
        QPointF(295, 295),
        QPointF(305, 295),
        QPointF(295, 305),
    ]
    for probe in offset_probes:
        hit = _scene.itemAt(probe, QTransform())
        assert isinstance(
            hit, CornerHandle
        ), f"offset probe {probe.x()},{probe.y()} did not hit a CornerHandle (got {type(hit).__name__})"

    # 3) The box BODY (centre, ~100px from any corner) is NOT swallowed by the
    #    enlarged handle hit shape — a click there must still select/move the box,
    #    not resize it (T-03-06-02 mitigation).
    body_hit = _scene.itemAt(QPointF(200, 200), QTransform())
    assert isinstance(body_hit, BoxItem)
    assert not isinstance(body_hit, CornerHandle)


# ===========================================================================
# Plan 03 post-UAT-reverify: BoxItem.ItemIsMovable regression (UAT re-test 1+4)
# ===========================================================================
#
# UAT re-test 1 (resize does nothing) + re-test 4 (moved box resets across a
# page round-trip) share ONE root cause: ``BoxItem`` set ``ItemIsMovable``
# (box_item.py:30). ``ItemIsMovable`` is BOTH redundant (the canvas owns the
# box move itself via ``_moving_box`` -> ``setRect`` + ``_sync_handles``,
# canvas.py:925-935; and resize via ``_advance_resize`` -> ``setRect``,
# canvas.py:1372-1405) AND harmful: Qt's scene-level item-move machinery moves
# the item by changing ``pos()`` (NOT ``rect()``). For a ``QGraphicsRectItem``
# ``pos()`` and ``rect()`` are INDEPENDENT geometry channels, so
# ``current_box()`` (which reads ``self.rect()``) materializes the STALE
# pre-move rect — the moved position is visible on screen (Qt draws at
# ``pos + rect``) but invisible to the snapshot, and the persisted
# ``ImageFile.boxes`` carry the original position, resetting across a page
# round-trip. The same flag also lets the scene's move steal a corner resize
# drag (the parent ``BoxItem`` moves instead of ``_advance_resize`` running).
#
# PROOF (reproduced offscreen): a BoxItem with rect=(10,10,30,30)+pos=(0,0);
# after setPos(40,40) (what Qt's ItemIsMovable does), pos()=(40,40) but rect()
# is STILL (10,10,30,30), and current_box() returns the stale (10,10,40,40).
#
# TEST-GAP NOTE (why these tests are the regression that did not exist before):
# the prior GUI tests called ``_begin_resize``/``_advance_resize``/``setRect``
# DIRECTLY, which bypasses Qt's scene event delivery — so they passed while the
# live app failed. The strongest feasible approximation is to drive the
# interactions through REAL Qt event delivery (``QTest.mousePress/Move/Release``
# on the viewport, the same primitive pytest-qt's ``qtbot.mousePress`` wraps)
# so the ``ItemIsMovable`` flag actually participates in event resolution. In
# offscreen Qt the canvas's ``mousePressEvent`` accepts box-interaction presses
# and returns before ``super().mousePressEvent()`` (so the scene's grabber stays
# clear and the flag is inert for the resize/move themselves); nonetheless these
# tests lock the contract that (a) the flag is absent (the exact one-line fix),
# (b) the pos()/rect() channels never diverge for a moved box, and (c) a
# corner-drag and a body-drag driven through real events both land geometry on
# ``rect()`` (the channel persistence reads). If a future change re-adds the
# flag OR routes moves through ``pos()``, ``current_box()`` would diverge and
# these tests would catch it.


def _drive_real_corner_resize(
    qtbot, canvas: EditorCanvas, item: BoxItem, from_scene: tuple[float, float], to_scene: tuple[float, float]
) -> None:
    """Drive a REAL Qt corner-handle resize via ``QTest.mousePress/Move/Release``
    on the canvas viewport (the same primitive ``qtbot.mousePress`` wraps).

    Maps scene coords to viewport coords and delivers the full press/move/
    release sequence through Qt's real event machinery so the
    ``ItemIsMovable``/selection flags actually participate in resolution.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    vp = canvas.viewport()
    vp_from = canvas.mapFromScene(QPointF(*from_scene))
    vp_to = canvas.mapFromScene(QPointF(*to_scene))
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(vp_from.x(), vp_from.y()))
    QTest.mouseMove(vp, QPoint(vp_to.x(), vp_to.y()))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(vp_to.x(), vp_to.y()))
    QApplication.processEvents()


def _drive_real_body_move(
    qtbot, canvas: EditorCanvas, item: BoxItem, from_scene: tuple[float, float], to_scene: tuple[float, float]
) -> None:
    """Drive a REAL Qt body-drag move via ``QTest.mousePress/Move/Release`` on
    the canvas viewport (real event delivery, NOT a direct ``setRect``).

    The ``item`` arg is retained for parity with the resize helper + future
    assertion convenience; the move resolves the box via the scene hit-test at
    ``from_scene`` (which the canvas dispatch routes to ``_select_and_begin_move``).
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    vp = canvas.viewport()
    vp_from = canvas.mapFromScene(QPointF(*from_scene))
    vp_to = canvas.mapFromScene(QPointF(*to_scene))
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(vp_from.x(), vp_from.y()))
    QApplication.processEvents()
    QTest.mouseMove(vp, QPoint(vp_to.x(), vp_to.y()))
    QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(vp_to.x(), vp_to.y()))
    QApplication.processEvents()


@pytest.mark.gui
def test_boxitem_pos_and_rect_do_not_diverge_after_move(qtbot) -> None:
    """REGRESSION (UAT re-test 4 heart): after a box move, ``pos()`` and
    ``rect()`` must NOT diverge — ``current_box()`` must reflect the moved
    position.

    This is the proven defect: with ``ItemIsMovable`` set, a Qt move changes
    ``pos()`` but leaves ``rect()`` at the original, so ``current_box()``
    (which reads ``self.rect()``) materializes the STALE pre-move rect. PROVEN
    offscreen: rect=(10,10,30,30)+pos=(0,0); after setPos(40,40), pos()=(40,40)
    but rect() is still (10,10,30,30) and current_box() returns (10,10,40,40).
    The canvas moves via ``_moving_box`` -> ``setRect`` (so this holds today),
    but this test locks the invariant: ``pos()`` stays at the origin AND
    ``current_box()`` equals the on-screen position, so any future change that
    routes moves through ``pos()`` (re-adding ``ItemIsMovable`` or a manual
    ``setPos``) is caught immediately.
    """
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _add_user_box(canvas, Box(20, 20, 80, 80))  # scene rect (20,20)-(80,80)

    # Drive a real body-drag move through Qt event delivery (NOT setRect).
    _drive_real_body_move(qtbot, canvas, item, (50.0, 50.0), (100.0, 100.0))

    # The move channel must be setRect (pos stays at origin) — NOT Qt's pos().
    assert item.pos().x() == 0.0 and item.pos().y() == 0.0, (
        "pos() must stay at the origin: the canvas moves the box via setRect "
        "(canvas.py:934), NOT via Qt's ItemIsMovable pos()-based move. A "
        "non-origin pos() means the move went through pos() (the UAT re-test 4 "
        "defect channel) and current_box() will diverge from the screen."
    )
    # current_box() must reflect the MOVED position (the snapshot channel).
    moved = item.current_box()
    assert (moved.x1, moved.y1) == (70, 70), (
        f"current_box() must reflect the moved position (70,70); got "
        f"({moved.x1},{moved.y1}). If it returns the ORIGINAL (20,20), the "
        f"move went through pos() (invisible to rect()) — UAT re-test 4."
    )
    assert (moved.x2, moved.y2) == (130, 130)


@pytest.mark.gui
def test_corner_resize_via_real_qtest_events_changes_rect(qtbot) -> None:
    """REGRESSION (UAT re-test 1): a corner-handle drag driven through REAL Qt
    event delivery (``QTest.mousePress/Move/Release`` on the viewport) must
    change the BoxItem's ``rect()``.

    The prior tests called ``_begin_resize``/``_advance_resize`` directly,
    bypassing Qt's scene event delivery — so they passed while the live app's
    resize did nothing (the documented defect: ``ItemIsMovable`` let the
    scene's move machinery steal the drag). This test drives the FULL press/
    move/release sequence through ``QTest`` (the same primitive pytest-qt's
    ``qtbot.mousePress`` wraps) so the ``ItemIsMovable`` flag participates in
    event resolution. With the flag removed the canvas's ``_advance_resize``
    path owns the drag and ``rect()`` changes; the test locks that contract.

    (In offscreen Qt the canvas's ``mousePressEvent`` accepts box presses and
    returns before ``super().mousePressEvent()``, so the scene's grabber stays
    clear and the resize is owned by ``_advance_resize`` regardless of the
    flag; the live-app failure under hardware input is the behavior this test
    guards against regressing.)
    """
    canvas = _canvas_with_image_and_boxes(qtbot)
    # Box (50,50)-(150,150); BR corner at scene (150,150).
    item = _add_user_box(canvas, Box(50, 50, 150, 150))
    item.setSelected(True)
    QApplication.processEvents()

    rect_before = QRectF(item.rect())
    # Drag the BR corner out to (180,180) -> box grows to (50,50)-(180,180).
    _drive_real_corner_resize(qtbot, canvas, item, (150.0, 150.0), (180.0, 180.0))

    rect_after = QRectF(item.rect())
    assert rect_after != rect_before, (
        "A real corner-handle drag must change the BoxItem rect() — the canvas "
        "mousePressEvent -> _begin_resize -> _advance_resize -> setRect path "
        "must own the drag (UAT re-test 1: 'box does not resize')."
    )
    # The TL corner is anchored; only the BR edge moved (width+height grew).
    assert int(rect_after.x()) == 50 and int(rect_after.y()) == 50, (
        "the opposite (TL) corner must stay anchored during a BR resize"
    )
    assert rect_after.width() > rect_before.width() and rect_after.height() > rect_before.height()


@pytest.mark.gui
def test_corner_resize_via_real_events_works_at_high_zoom(qtbot) -> None:
    """REGRESSION (UAT re-test 1, debug box-resize-move): a corner-handle drag
    driven through REAL Qt event delivery must arm RESIZE (not MOVE) and change
    the BoxItem's ``rect()`` at HIGH zoom (>= 3.5), not just at zoom 1.0.

    Root cause reproduced via real-event delivery: the prior
    ``mousePressEvent`` passed ``self.transform()`` (the view zoom) as the 2nd
    argument to ``QGraphicsScene.itemAt(scene_pos, transform)``. At zoom >= ~3.5
    that made Qt's BSP coarse pass return the parent ``BoxItem`` instead of the
    child ``CornerHandle`` at the corner, so the press armed a MOVE
    (``_select_and_begin_move``) where the user expected a RESIZE — dragging then
    moved the box near the corner, perceived as "resize does nothing". This
    passed at zoom 1.0 (which is why the sibling test above and the whole
    260-green suite missed it) and only failed live, where users zoom in to
    inspect/fix OCR boxes.

    The fix: pass the IDENTITY transform (``QTransform()``) to ``itemAt`` so the
    topmost item by z (handle z=150 > box z=100) wins at every zoom. This test
    locks that contract at zoom 4.0 — it FAILS on the pre-fix code (armed MOVE)
    and PASSES after. Compliant with the debug session's TRAP #4: it drives
    ``QTest.mousePress/Move/Release`` on the viewport (real Qt event delivery),
    NOT a direct ``_begin_resize``/``_advance_resize`` call.
    """
    from PySide6.QtGui import QTransform

    canvas = _canvas_with_image_and_boxes(qtbot)
    # Zoom in to 4.0 (beyond the ~3.5 threshold where the bug manifested).
    canvas.zoom_factor = 4.0
    canvas.setTransform(QTransform().scale(4.0, 4.0))
    QApplication.processEvents()
    # Box (50,50)-(150,150); BR corner at scene (150,150).
    item = _add_user_box(canvas, Box(50, 50, 150, 150))
    item.setSelected(True)
    QApplication.processEvents()

    rect_before = QRectF(item.rect())
    # Drag the BR corner out to (180,180) -> box should grow to (50,50)-(180,180).
    _drive_real_corner_resize(qtbot, canvas, item, (150.0, 150.0), (180.0, 180.0))

    # The resize MUST have armed (not a move). If itemAt returned the parent
    # BoxItem, _moving_box would be set instead and rect() would be unchanged
    # (the drag would be a no-op move of a few px near the corner).
    assert canvas._resizing_box is None and canvas._moving_box is None, (
        "drag completed: both flags should be cleared on release"
    )
    rect_after = QRectF(item.rect())
    assert rect_after != rect_before, (
        "A real corner-handle drag at zoom 4.0 must change the BoxItem rect() — "
        "if this fails, scene.itemAt is returning the parent BoxItem instead of "
        "the CornerHandle at high zoom (UAT re-test 1). Check that mousePressEvent "
        "passes the IDENTITY transform to itemAt, not self.transform()."
    )
    assert int(rect_after.x()) == 50 and int(rect_after.y()) == 50, (
        "the opposite (TL) corner must stay anchored during a BR resize at zoom"
    )
    assert rect_after.width() > rect_before.width() and rect_after.height() > rect_before.height()


@pytest.mark.gui
def test_moved_box_via_real_events_persists_round_trip(qtbot, tmp_path) -> None:
    """REGRESSION (UAT re-test 4): a box moved via REAL Qt event delivery
    (``QTest`` press/move/release on the viewport — NOT a direct ``setRect``)
    must persist its MOVED position across a page round-trip.

    Historical root cause: the 03-07 executor's probe passed because it
    simulated the move via ``setRect`` (updates ``rect()``); the live app moved
    through Qt's ``ItemIsMovable`` (updates ``pos()``), which diverges from
    ``rect()`` — so ``boxes_snapshot()`` materialized the stale rect and the
    persisted boxes carried the original position. The flag was removed in
    03-07; the canvas now owns the move via ``_moving_box`` -> ``setRect``
    (canvas.py:1013-1025).

    MEASURED root cause of the pre-05-09 deterministic 1px failure (NOT a
    canvas defect): PySide6's ``QTest`` and ``mapFromScene`` deliver INT
    viewport coordinates while the MainWindow canvas fit-to-window transform is
    FRACTIONAL in the pytest environment (measured scale 0.18333, viewport
    1188x1037; standalone runs at scale 0.2 land exactly at (70,70,130,130)).
    The int truncation of fractional viewport coords loses ~0.91 scene px, so a
    nominal 50px scene drag is delivered ~0.9px short (delta 49.09 -> box at
    (69,69,129,129)); the canvas applies the delivered delta EXACTLY
    (canvas.py:1013-1025) — this is a TEST-side sub-pixel truncation artifact.

    The assertions below are therefore TRUNCATION-TOLERANT (moved ~50px within
    a bounded 45..50 band, T-05-21) while still failing on the real UAT re-test
    4 defect: a pos()/rect() divergence leaves rect() at the ORIGINAL
    (20,20,80,80) -> delivered delta 0 -> the range check fails. The
    round-trip assertion anchors on the ACTUALLY-moved position (``moved_now``)
    so the real regression contract — persisted == moved — is checked exactly,
    environment-independent.
    """
    from manga_ai_studio.gui.main_window import MainWindow

    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    # Two real PNG pages so the round-trip can navigate A -> B -> A.
    from PIL import Image as PILImage

    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    PILImage.new("RGB", (120, 120), color=(200, 200, 200)).save(page_a)
    PILImage.new("RGB", (120, 120), color=(180, 180, 180)).save(page_b)
    window._load_folder(tmp_path)
    assert window._current_page_index() == 0
    window.show()
    window.canvas.viewport().setFocus(Qt.FocusReason.MouseFocusReason)
    QApplication.processEvents()

    # Seed one user box at scene (20,20)-(80,80) — center at (50,50).
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([PageBox(box=Box(20, 20, 80, 80), origin=USER)], [])
    finally:
        window._suppress_boxes_push = False
    item = window.canvas._box_items[0]
    QApplication.processEvents()

    # Drive a real body-drag move (50,50) -> (100,100): the box lands at
    # (70,70)-(130,130) minus the ~1px QTest int-truncation at the fractional
    # fit scale (delivered delta ~49.09 -> ~(69,69,129,129)).
    _drive_real_body_move(qtbot, window.canvas, item, (50.0, 50.0), (100.0, 100.0))
    moved_now = item.current_box().as_tuple
    # moved_now is a (x1,y1,x2,y2) TUPLE — assert on indices. The box started
    # at (20,20,80,80); a nominal 50px drag is delivered ~0.9px short by the
    # int-truncating QTest/mapFromScene delivery chain (see docstring).
    assert moved_now[0] != 20 or moved_now[1] != 20, (
        f"precondition: the real-event move must move the box at all; got "
        f"{moved_now}. A pos()-routed move leaves rect() at the ORIGINAL "
        f"(20,20,80,80) — the UAT re-test 4 defect."
    )
    assert moved_now[0] - 20 == moved_now[1] - 20, (
        f"precondition: the drag was (50,50)->(100,100) so the delivered scene "
        f"delta must be axis-symmetric; got {moved_now} (dx={moved_now[0] - 20}, "
        f"dy={moved_now[1] - 20})."
    )
    assert 45 <= moved_now[0] - 20 <= 50, (
        f"precondition: the box must have moved ~50px; got dx={moved_now[0] - 20} "
        f"({moved_now}). The ~0.9px measured truncation at the fractional fit "
        f"scale allows 45..50; a move through pos() yields 0 and fails here."
    )
    assert moved_now[2] - moved_now[0] == 60 and moved_now[3] - moved_now[1] == 60, (
        f"precondition: the 60x60 shape must be preserved by a move; got "
        f"{moved_now} (a move never changes width/height; a resize bug would "
        f"fail here)."
    )

    # Round-trip A -> B -> A through the REAL on_page_selected seam.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    assert not window.canvas.has_boxes()
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)

    restored = window.canvas.boxes_snapshot()
    assert len(restored) == 1, f"the box must survive the round-trip; got {len(restored)}"
    assert restored[0].box.as_tuple == moved_now, (
        "UAT re-test 4: the MOVED position must persist across the round-trip "
        f"(persisted {restored[0].box.as_tuple} != moved {moved_now}). If the "
        "restored box is the ORIGINAL (20,20,80,80), the move was visible on "
        "screen (pos+rect) but the snapshot materialized the stale rect() — "
        "the ItemIsMovable root cause."
    )


# ===========================================================================
# Plan 04-04 Task 1 — BoxItem text overlay (z=120) + bubble badge (z=140)
# ===========================================================================
#
# Phase 4 "boxes become display objects" (D-09): each BoxItem gains a persistent
# translucent outlined text overlay (QGraphicsTextItem child, z=120) showing the
# current-focus text (translation when present, else recognized — D-10) and a
# bubble-number badge (QGraphicsRectItem + digit, z=140, ItemIgnoresTransformations,
# constant viewport-px). The overlay is PLAIN text (ASVS V5 — no setHtml on OCR
# output) styled via QTextCharFormat.setTextOutline (RESEARCH Pattern 3, single
# API). set_text_overlay_visible(False) is the independent visibility layer the
# Toggle Text Overlay action (T, D-12) drives — independent of the box-layer
# toggle (Shift+M) and the mask toggle (M).

# Module constants the implementation must add (UI-SPEC §Z-order). Importing
# them by name proves they exist; the import fails before Task 1 GREEN.
from manga_ai_studio.gui.box_item import (  # noqa: E402
    _BADGE_Z,
    _TEXT_OVERLAY_Z,
)


def _pagebox_with_text(recognized: str = "", translation: str = "") -> PageBox:
    """Build a DETECTED PageBox carrying recognized text and/or a translation.

    Uses the centralized setters (set_recognized_text / set_translation) so the
    payload-None guard + .text/.translation slots are exercised — the same path
    the Inspector + inline editor take (Plan 04/05).
    """
    pb = PageBox(box=Box(20, 20, 220, 120), origin=DETECTED)
    if recognized:
        pb.set_recognized_text(recognized)
    if translation:
        pb.set_translation(translation)
    return pb


@pytest.mark.gui
def test_text_overlay_z_constant_is_120() -> None:
    """The text overlay z-order constant is 120 (UI-SPEC §Z-order, RESEARCH Pitfall 7)."""
    assert _TEXT_OVERLAY_Z == 120


@pytest.mark.gui
def test_badge_z_constant_is_140() -> None:
    """The bubble-badge z-order constant is 140 (above overlay z=120, below handles z=150)."""
    assert _BADGE_Z == 140


@pytest.mark.gui
def test_text_overlay_child_exists_and_hidden_by_default(qtbot) -> None:
    """A BoxItem carries a _text_overlay QGraphicsTextItem child (z=120), hidden by default."""
    from PySide6.QtWidgets import QGraphicsTextItem

    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    # refresh_text_overlay is what shows it; a fresh box with text should show it.
    item.refresh_text_overlay()
    assert hasattr(item, "_text_overlay")
    assert isinstance(item._text_overlay, QGraphicsTextItem)
    assert item._text_overlay.zValue() == 120


@pytest.mark.gui
def test_text_overlay_shows_recognized_when_no_translation(qtbot) -> None:
    """A box with recognized text 'hello' and no translation renders 'hello' (D-10)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is True
    assert item._text_overlay.toPlainText() == "hello"


@pytest.mark.gui
def test_text_overlay_current_focus_rule_translation_wins(qtbot) -> None:
    """The same box with translation 'hola' renders 'hola' (D-10 current-focus: translation wins)."""
    pb = _pagebox_with_text(recognized="hello", translation="hola")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.toPlainText() == "hola"


@pytest.mark.gui
def test_text_overlay_hidden_when_no_recognized_text(qtbot) -> None:
    """A box with no recognized text renders no text child (overlay hidden)."""
    pb = PageBox(box=Box(20, 20, 100, 80), origin=DETECTED)  # payload=None
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is False


@pytest.mark.gui
def test_text_overlay_document_is_plain_not_rich(qtbot) -> None:
    """The overlay document is PLAIN text (ASVS V5 — never setHtml on OCR output, T-4-07)."""
    pb = _pagebox_with_text(recognized="<script>alert(1)</script>")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    # Plain text: toPlainText echoes the literal string; no rich-text flag set.
    assert item._text_overlay.toPlainText() == "<script>alert(1)</script>"
    # QTextDocument.isModified not relevant; the contract is the API used.
    # setPlainText does NOT enable rich text. The document's default is plain.
    assert item._text_overlay.document().isEmpty() is False


@pytest.mark.gui
def test_text_overlay_uses_outlined_text_format(qtbot) -> None:
    """The overlay glyphs carry a setTextOutline pen (RESEARCH Pattern 3 single API)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    cursor = item._text_overlay.textCursor()
    cursor.select(__import__("PySide6").QtGui.QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    # The outline pen is set (2px dark matte per UI-SPEC §Color text-overlay outline).
    pen = fmt.textOutline()
    assert pen.style() != Qt.PenStyle.NoPen
    assert pen.widthF() >= 1.0


# -- UAT test 1 gap closure (plan 04-08): overlay geometry tracking (RC-1) --
# The overlay child must track the box through the canvas geometry paths. The
# canvas moves/resizes boxes via setRect + _sync_handles (canvas.py:1022-1023,
# 1597-1598, 1618-1619) on every drag-move and corner-resize, so the RC-1 fix
# splits a setPos-ONLY _reposition_text_overlay() out of refresh_text_overlay()
# and calls it from _sync_handles. Pre-fix the overlay stayed at its pre-move
# scene position (debug session 04-01 measured intersection 0.0 after a move).


@pytest.mark.gui
def test_text_overlay_tracks_box_after_setrect_move(qtbot) -> None:
    """After setRect(move) + _sync_handles the overlay sits INSIDE the moved box (RC-1).

    Matches the debug probe exactly: pre-fix the overlay sceneBoundingRect stays
    at the pre-move (23,23,217,30) while the box moves to (149,149,202,102) —
    a 0.0 intersection. Post-fix the overlay topLeft tracks the box's new
    topLeft (pen width 2/2 + 2px inset = 3px).
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    # Precondition: overlay inset at (23,23) inside box (20,20,220,120).
    tl0 = item._text_overlay.sceneBoundingRect().topLeft()
    assert tl0.x() == pytest.approx(23.0, abs=0.01)
    assert tl0.y() == pytest.approx(23.0, abs=0.01)
    item.setRect(QRectF(150, 150, 200, 100))
    item._sync_handles()
    tl = item._text_overlay.sceneBoundingRect().topLeft()
    assert tl.x() == pytest.approx(153.0, abs=0.01)
    assert tl.y() == pytest.approx(153.0, abs=0.01)


@pytest.mark.gui
def test_text_overlay_tracks_box_after_tl_edge_resize(qtbot) -> None:
    """After a TL-edge setRect resize + _sync_handles the overlay is INSIDE the box (RC-1).

    A TL/BL/TR-edge resize moves the box's top-left corner, which pre-fix left
    the overlay detached at the old position (the debug's containment proxy:
    sceneBoundingRect intersection must be non-empty).
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.setRect(QRectF(60, 40, 180, 90))
    item._sync_handles()
    tl = item._text_overlay.sceneBoundingRect().topLeft()
    assert tl.x() == pytest.approx(63.0, abs=0.01)
    assert tl.y() == pytest.approx(43.0, abs=0.01)
    assert (
        item._text_overlay.sceneBoundingRect().intersects(item.sceneBoundingRect())
        is True
    )


@pytest.mark.gui
def test_text_overlay_reposition_does_not_rebuild_document(qtbot) -> None:
    """_sync_handles repositions the overlay WITHOUT rebuilding its document (RC-1).

    The canvas calls _sync_handles on EVERY mouseMoveEvent during a drag, so the
    reposition must be setPos-only — a full refresh_text_overlay (setPlainText +
    document rebuild) per mousemove would be wasteful. The rendered text must
    survive the move unchanged.
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.setRect(QRectF(150, 150, 200, 100))
    item._sync_handles()
    assert item._text_overlay.toPlainText() == "hello"


# -- UAT test 1 gap closure (plan 04-08): zoom clamp + outline (RC-2/RC-3) --
# UI-SPEC §16 mandates a [10,28] viewport-px font clamp + a legibility outline.
# Pre-fix the font was flat 14 scene px (4-7 device px at the default
# fit-to-window zoom ~0.3-0.5) and the 2px outline was scene-px (sub-pixel AA'd
# away below 100%: 2710 -> 260 -> 0 dark pixels at 1.0/0.5/0.25 zoom — debug
# session 04-01). Fix: scene font = clamp(14*zoom, 10, 28)/zoom, outline =
# 2/zoom scene px (constant 2 viewport px), re-applied from the stored
# _overlay_zoom via apply_overlay_zoom() on every zoom_changed emission.


@pytest.mark.gui
@pytest.mark.parametrize(
    "zoom,expected_point",
    [
        (0.5, 20.0),
        (1.0, 14.0),
        (4.0, 7.0),
    ],
)
def test_text_overlay_font_clamp_scales_with_zoom(qtbot, zoom, expected_point) -> None:
    """apply_overlay_zoom re-derives the font so the RENDERED px stays in [10,28] (RC-2).

    UI-SPEC §16: the scene font is clamp(14*zoom, 10, 28)/zoom, so the rendered
    viewport-px size clamp(14*zoom, 10, 28) stays within [10, 28] at every zoom.
    Pre-fix the font stayed 14 scene px at every zoom (no clamp implemented).
    The former zoom-0.25/40.0 case moved to the 04-09 section: at 0.25 zoom the
    clamped 40pt font wraps "hello" to two lines (265-280px > inner width 194),
    so the 04-09 fit loop (below the clamp, to the 5 vp floor) replaces that
    clamp-only outcome — see test_text_overlay_fit_loop_reduces_below_clamp_floor_at_low_zoom.
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(zoom)
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() == pytest.approx(expected_point, abs=0.1)
    assert 10.0 <= fmt.font().pointSizeF() * zoom <= 28.0


@pytest.mark.gui
@pytest.mark.parametrize(
    "zoom,expected_width",
    [
        (0.25, 8.0),
        (0.5, 4.0),
        (1.0, 2.0),
        (4.0, 0.5),
    ],
)
def test_text_overlay_outline_width_scales_with_zoom(qtbot, zoom, expected_width) -> None:
    """apply_overlay_zoom keeps the outline a constant 2 VIEWPORT px (RC-3).

    The outline pen is 2/zoom scene px so it renders 2 device px at any zoom.
    The scene-px reading (fixed 2 scene px) goes sub-pixel below 100% — the
    debug session measured 0 dark outline pixels at 0.25 zoom ("just looks
    white"). Pre-fix the outline stayed 2 scene px at every zoom.
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(zoom)
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    pen = fmt.textOutline()
    assert pen.widthF() == pytest.approx(expected_width, abs=0.01)
    assert pen.widthF() * zoom == pytest.approx(2.0, abs=0.01)


@pytest.mark.gui
def test_text_overlay_zoom_style_survives_content_refresh(qtbot) -> None:
    """A content refresh (no zoom arg) reuses the STORED zoom style (RC-2/RC-3).

    Inspector/OCR/inline-edit commits call refresh_text_overlay() without a
    zoom argument; the style must come from the stored _overlay_zoom so a
    content refresh never resets the font clamp/outline back to the zoom-1
    style.
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(0.5)
    pb.set_translation("hola")  # content change -> current focus flips
    item.refresh_text_overlay()
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() == pytest.approx(20.0, abs=0.1)
    assert fmt.textOutline().widthF() == pytest.approx(4.0, abs=0.01)


@pytest.mark.gui
def test_zoom_changed_reapplies_overlay_style_canvas(qtbot) -> None:
    """The canvas zoom_changed slot forwards its zoom to the overlay style (RC-2/RC-3).

    _on_zoom_changed_reposition_handles previously DISCARDED its zoom argument
    (a leading-underscore parameter) and only repositioned handles — the
    overlay style never re-derived from the new zoom. fit_to_window /
    zoom_reset / wheel zoom all emit zoom_changed (canvas.py:820/827/851), so
    this single slot covers every zoom path incl. the default fit-to-window.
    """
    canvas = _canvas_with_image_and_boxes(qtbot)
    pb = _pagebox_with_text(recognized="hello")
    canvas.set_boxes(user_pageboxes=[], detected_pageboxes=[pb])
    item = canvas._box_items[0]
    assert item._text_overlay.toPlainText() == "hello"
    canvas._on_zoom_changed_reposition_handles(0.5)
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() == pytest.approx(20.0, abs=0.1)
    assert fmt.textOutline().widthF() == pytest.approx(4.0, abs=0.01)
    # The overlay must stay inside the box rect after the zoom re-apply.
    assert (
        item._text_overlay.sceneBoundingRect().intersects(item.sceneBoundingRect())
        is True
    )


# -- UAT test 1 gap closure round 2 (plan 04-09): overlay fit-in-box --
# The UAT test-1 truth "text overlay adapts to box size: overlay text wraps/fits
# INSIDE the box rect (no horizontal overshoot), sized legibly relative to the
# box" — the user's report "it's still a bit small and it overshoots the box,
# renders horizontally — it should try to fit in the box and kind of adapt the
# text to the size of the text box". Root causes: refresh_text_overlay never
# called setTextWidth (single unwrapped horizontal line) and the font was a
# fixed 14 viewport-px base regardless of box size. Fix contract: wrap at the
# box inner width + box-adaptive base (14 x min(box_w, box_h)/100 viewport px,
# clamped [10,28] — the clamp bounds the BASE) + a bounded shrink-to-fit loop
# (max 12 steps of 0.9, hard floor 5 vp checked at loop top) so the text
# "tries to fit" the box height; a resize COMMIT re-wraps/re-fits once per drag.


@pytest.mark.gui
def test_text_overlay_wraps_long_text_to_box_width(qtbot) -> None:
    """Long overlay text WRAPS at the box inner width — no horizontal overshoot.

    The reference box (20,20,220,120) has a 200-wide rect; unselected pen 2 ->
    inset 3 -> inner width 194. Pre-fix no setTextWidth meant the document laid
    out on ONE line (~5700 px wide on the exec platform, >25x the box width).
    The text is 60 words ("word " x 59 + "word") so no trailing space is lost
    to Qt's document trailing-whitespace trimming.
    """
    pb = _pagebox_with_text(recognized="word " * 59 + "word")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.textWidth() == pytest.approx(194.0, abs=0.01)
    assert item._text_overlay.document().size().width() == pytest.approx(
        194.0, abs=0.01
    )
    assert (
        item._text_overlay.sceneBoundingRect().right()
        <= item.sceneBoundingRect().right() + 1.5
    )
    assert item._text_overlay.toPlainText() == "word " * 59 + "word"


@pytest.mark.gui
@pytest.mark.parametrize(
    "box,expected_font",
    [
        # Box is (x1, y1, x2, y2): (20,20,220,120) -> 200x100 rect, min dim 100
        # -> base 14 (the §16 reference box).
        (Box(20, 20, 220, 120), 14.0),
        # (20,20,220,170) -> 200x150 rect, min dim 150 -> base 21.0.
        (Box(20, 20, 220, 170), 21.0),
        # (20,20,320,320) -> 300x300 rect, min dim 300 -> base 42 -> clamped 28.
        (Box(20, 20, 320, 320), 28.0),
    ],
)
def test_text_overlay_font_adapts_to_box_size(qtbot, box, expected_font) -> None:
    """The overlay font is BOX-ADAPTIVE: 14 x min(box_w, box_h)/100, clamped [10,28].

    "hello" fits on one line at every size here (no shrink interference:
    ~95px at 14pt, ~145px at 21pt, ~200px at 28pt — all < the 194/294 inner
    widths). Pre-fix the font was 14.0 for every box regardless of size.
    """
    pb = PageBox(box=box, origin=DETECTED)
    pb.set_recognized_text("hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() == pytest.approx(expected_font, abs=0.1)
    # At zoom 1.0 the rendered size is the box-adaptive base within [10, 28].
    assert 10.0 <= fmt.font().pointSizeF() * 1.0 <= 28.0


@pytest.mark.gui
def test_text_overlay_shrinks_to_fit_box_height(qtbot) -> None:
    """Wrapped text that exceeds the box height shrinks (bounded) to fit inside.

    "word " x 40 wraps at 194 and the base 14 vp font needs ~8 lines — exceeds
    the inner height 94, so the fit loop reduces the RENDERED font (below the
    [10,28] clamp if needed, never below the 5 vp floor). The overlay rect must
    stay CONTAINED in the box rect and the wrap width must survive the loop.
    """
    pb = _pagebox_with_text(recognized="word " * 40)
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay_rect = item._text_overlay.sceneBoundingRect()
    box_rect = item.sceneBoundingRect()
    assert overlay_rect.right() <= box_rect.right() + 1.5
    assert overlay_rect.bottom() <= box_rect.bottom() + 1.5
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() < 14.0  # the shrink loop engaged
    assert item._text_overlay.document().size().width() == pytest.approx(
        194.0, abs=0.01
    )  # wrap preserved through the loop


@pytest.mark.gui
def test_resize_commit_rewraps_overlay_text_canvas(qtbot) -> None:
    """A resize COMMIT re-wraps/re-fits the overlay to the final rect (once per drag).

    _commit_resize must refresh the overlay after _sync_handles. Pre-fix the
    overlay kept the stale reference-box layout (194-wide doc at font 14) after
    a resize to (20,20,320,200): textWidth 194 != 314 and font 14 != 28.
    """
    canvas = _canvas_with_image_and_boxes(qtbot)
    pb = _pagebox_with_text(recognized="hello")
    canvas.set_boxes(user_pageboxes=[], detected_pageboxes=[pb])
    item = canvas._box_items[0]
    canvas._resizing_box = item
    canvas._resize_start_rect = QRectF(item.rect())
    canvas._boxes_interaction_start_snapshot = []
    item.setRect(QRectF(20, 20, 320, 200))
    canvas._commit_resize()
    # 320 - 2x inset 3 -> inner width 314; min dim 200 -> base 28 (no shrink:
    # "hello" is one line at 28pt within inner height 194).
    assert item._text_overlay.textWidth() == pytest.approx(314.0, abs=0.01)
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() == pytest.approx(28.0, abs=0.1)


@pytest.mark.gui
def test_text_overlay_fit_loop_reduces_below_clamp_floor_at_low_zoom(qtbot) -> None:
    """At low zoom the fit loop operates BELOW the [10,28] clamp, never below 5 vp.

    At zoom 0.25 the clamped font is 40pt; "hello world" lays out wider than
    the inner width 194 -> wraps -> the wrapped height exceeds the inner
    height 94, so the clamp-only outcome is unreachable and the fit outcome
    replaces it: the loop shrinks the RENDERED font below the clamp down toward
    the 5 vp floor and the overlay stays CONTAINED in the box. Measured on the
    exec platform: ~26.24pt -> 6.56 vp (assertions stay range-based per the
    plan — the exact landing depends on the font metrics of the platform).
    This is the case REMOVED from the 04-08 clamp test (plan 04-09).
    """
    pb = _pagebox_with_text(recognized="hello world")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(0.25)
    from PySide6.QtGui import QTextCursor

    cursor = item._text_overlay.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = cursor.charFormat()
    assert fmt.font().pointSizeF() < 40.0  # shrink engaged
    assert 5.0 <= fmt.font().pointSizeF() * 0.25 < 10.0  # below clamp, above floor
    overlay_rect = item._text_overlay.sceneBoundingRect()
    box_rect = item.sceneBoundingRect()
    assert overlay_rect.right() <= box_rect.right() + 1.5
    assert overlay_rect.bottom() <= box_rect.bottom() + 1.5


@pytest.mark.gui
def test_set_text_overlay_visible_false_hides_only_text(qtbot) -> None:
    """set_text_overlay_visible(False) hides the text child but the box border stays visible.

    This is the independent visibility layer D-12 contracts: the text toggle
    affects ONLY the text children, not the box border or handles.
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is True
    # The box itself is visible (it is in a scene).
    assert item.isVisible() is True

    item.set_text_overlay_visible(False)
    assert item._text_overlay.isVisible() is False
    # The box border + handles are unaffected (box still visible).
    assert item.isVisible() is True


@pytest.mark.gui
def test_set_text_overlay_visible_true_reshows_text(qtbot) -> None:
    """Toggling back to visible re-shows the text child (round-trip)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.set_text_overlay_visible(False)
    assert item._text_overlay.isVisible() is False
    item.set_text_overlay_visible(True)
    assert item._text_overlay.isVisible() is True


@pytest.mark.gui
def test_refresh_text_overlay_rerenders_after_text_change(qtbot) -> None:
    """After a set_translation call, refresh_text_overlay re-renders the current-focus text."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.toPlainText() == "hello"
    # Now set a translation — current focus flips to translation.
    pb.set_translation("hola")
    item.refresh_text_overlay()
    assert item._text_overlay.toPlainText() == "hola"


# --- bubble badge (z=140, ItemIgnoresTransformations, TL-outside) ---


@pytest.mark.gui
def test_badge_hidden_when_bubble_no_is_none(qtbot) -> None:
    """A box with bubble_no=None renders no badge (hidden by default)."""
    pb = _pagebox_with_text(recognized="hello")
    assert pb.bubble_no is None
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()
    assert item._badge.isVisible() is False


@pytest.mark.gui
def test_badge_shows_bubble_no_when_set(qtbot) -> None:
    """The badge shows the pagebox.bubble_no when set; positioned TL-outside the box."""
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = 3
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()
    assert item._badge.isVisible() is True
    # The badge is positioned TL-outside: its scene x < box left, y < box top.
    badge_pos = item._badge.scenePos()
    box_left = item.rect().left()
    box_top = item.rect().top()
    assert badge_pos.x() < box_left, (
        f"badge x {badge_pos.x()} must be LEFT of the box (TL-outside, UI-SPEC §17); "
        f"box left is {box_left}"
    )
    assert badge_pos.y() < box_top, (
        f"badge y {badge_pos.y()} must be ABOVE the box (TL-outside, UI-SPEC §17); "
        f"box top is {box_top}"
    )


@pytest.mark.gui
def test_badge_ignores_transformations(qtbot) -> None:
    """The badge (and its digit) use ItemIgnoresTransformations (constant viewport-px)."""
    from PySide6.QtWidgets import QGraphicsItem

    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = 1
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()
    assert item._badge.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    # The digit child also ignores transformations.
    digit = item._badge_digit
    assert digit.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations


@pytest.mark.gui
def test_badge_manual_override_amber_border(qtbot) -> None:
    """A manual_override badge gets a 2px amber (#f5a623) border; auto badges get matte (D-16)."""
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = 5
    pb.manual_override = True
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()
    pen = item._badge.pen()
    assert pen.color().name().lower() == "#f5a623", (
        f"manual_override badge pen must be amber #f5a623; got {pen.color().name()}"
    )
    assert pen.widthF() >= 1.5  # 2px

    # Auto badge (manual_override False) gets the matte outline #0b0b0e.
    pb2 = _pagebox_with_text(recognized="hi")
    pb2.bubble_no = 2
    pb2.manual_override = False
    _scene2, item2 = _scene_with_box(pb2)
    item2.refresh_badge()
    pen2 = item2._badge.pen()
    assert pen2.color().name().lower() == "#0b0b0e", (
        f"auto badge pen must be matte #0b0b0e; got {pen2.color().name()}"
    )


@pytest.mark.gui
def test_badge_digit_shows_bubble_number(qtbot) -> None:
    """The badge's digit child shows str(bubble_no)."""
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = 42
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()
    assert item._badge_digit.toPlainText() == "42"


# -- UAT test 4 gap closure round 3 (plan 04-10): badge digit-fit sizing --
# The badge was a FIXED 20x14 rect with the digit at a hardcoded (3,-1): the
# 14px-tall badge clipped the ~19px-tall glyph (the user's "top half only")
# and multi-digit numbers overflowed the 20px width. The 04-10 fix measures
# the digit's tight glyph line box (document margin 0) after setPlainText,
# resizes the badge rect to digit_w + 2x4 / digit_h + 2x2 padding, re-centers
# the digit, and uses the ACTUAL badge size for the TL-outside placement + the
# edge-flip decision. Assertions derive from the MEASURED digit rect (per the
# plan's note: the badge-size pixel values are platform-font-dependent — the
# plan-reference platform measures 16x19 per digit -> 24x23/40x23/56x23
# badges; this platform measures 9.45x19 -> 17.45x23/26.9x23/36.36x23 — the
# CONTRACT, digit + 4px/2px padding with full containment, is font-agnostic).


@pytest.mark.gui
@pytest.mark.parametrize("number", [3, 12, 123], ids=["1-digit", "2-digit", "3-digit"])
def test_badge_rect_sizes_to_digit(qtbot, number) -> None:
    """The badge rect is DIGIT-SIZED: measured glyph line box + 4px/2px padding.

    FAILS pre-fix: the badge rect is the fixed 20x14 and the digit (margin-4
    inflated rect, pos (3,-1)) overflows it — the local rect is NOT contained
    (right > 20, bottom > 14), the user's "top half only" clipping, and the
    digit is not re-centered.
    """
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = number
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()

    digit = item._badge_digit
    dw = digit.boundingRect().width()
    dh = digit.boundingRect().height()
    # Contract: badge = digit glyph line box + 4px/side horizontal + 2px/side
    # vertical padding (plan 04-10). Derived from the measured rect so the
    # assertion holds on any platform font.
    bw = dw + 2.0 * 4.0
    bh = dh + 2.0 * 2.0

    r = item._badge.rect()
    assert r.x() == pytest.approx(0.0, abs=0.01)
    assert r.y() == pytest.approx(0.0, abs=0.01)
    assert r.width() == pytest.approx(bw, abs=0.01)
    assert r.height() == pytest.approx(bh, abs=0.01)

    # Measurement basis: the tight glyph line box (document margin 0), so the
    # default QTextDocument margin (4.0) cannot inflate the badge.
    assert digit.document().documentMargin() == pytest.approx(0.0)

    # The digit's LOCAL rect is fully contained in the badge rect (no
    # top/bottom/right clipping at any digit count).
    digit_local = QRectF(digit.pos(), digit.boundingRect().size())
    badge_rect = QRectF(0.0, 0.0, r.width(), r.height())
    assert digit_local.left() >= 0.0, f"digit left {digit_local.left()} must not clip"
    assert digit_local.top() >= 0.0, f"digit top {digit_local.top()} must not clip"
    assert digit_local.right() <= badge_rect.right(), (
        f"digit right {digit_local.right()} must fit inside badge width {badge_rect.right()}"
    )
    assert digit_local.bottom() <= badge_rect.bottom(), (
        f"digit bottom {digit_local.bottom()} must fit inside badge height {badge_rect.bottom()}"
    )

    # The digit is re-centered from the MEASURED digit size.
    assert digit.pos().x() == pytest.approx((r.width() - dw) / 2.0, abs=0.01)
    assert digit.pos().y() == pytest.approx((r.height() - dh) / 2.0, abs=0.01)


@pytest.mark.gui
@pytest.mark.parametrize("number", [3, 12], ids=["1-digit", "2-digit"])
def test_badge_tl_outside_uses_actual_badge_size(qtbot, number) -> None:
    """The TL-outside placement uses the ACTUAL badge size (badge + 2px offset).

    FAILS pre-fix with the plan's reference platform values: the fixed 20x14
    constants place the badge at (-3,3) regardless of the digit (probe platform
    reference: 24x23 at (-7,-6), 40x23 at (-23,-6)). On THIS platform the
    measured digits give 17.45x23 at (-0.45,-6) and 26.9x23 at (-9.9,-6), so
    the per-case assertion derives the expected position from the ACTUAL badge
    rect — the RED gate for the fixed-size bug lives in
    test_badge_tl_outside_tracks_size_across_digits (which the per-case
    contract complements).
    """
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = number
    _scene, item = _scene_with_box(pb)
    item.refresh_badge()

    # Precondition: the reference box's scene rect (2px unselected pen).
    sbr = item.sceneBoundingRect()
    assert sbr.left() == pytest.approx(19.0, abs=0.01)
    assert sbr.top() == pytest.approx(19.0, abs=0.01)

    # The badge sits exactly badge_w+2 / badge_h+2 TL-outside its box,
    # computed from the ACTUAL (just-measured) badge rect.
    r = item._badge.rect()
    pos = item._badge.scenePos()
    assert pos.x() == pytest.approx(sbr.left() - r.width() - 2.0, abs=0.01), (
        f"badge x {pos.x()} must be sceneBoundingRect.left() - badge_w - 2"
    )
    assert pos.y() == pytest.approx(sbr.top() - r.height() - 2.0, abs=0.01), (
        f"badge y {pos.y()} must be sceneBoundingRect.top() - badge_h - 2"
    )
    # The badge remains TL-outside the box's scene rect.
    assert pos.x() < sbr.left()
    assert pos.y() < sbr.top()


@pytest.mark.gui
def test_badge_tl_outside_tracks_size_across_digits(qtbot) -> None:
    """The badge tracks its size: the multi-digit badge sits FURTHER TL.

    FAILS pre-fix: the fixed 20x14 constants place BOTH badges at (-3,3) — a
    multi-digit badge does not track its own size (the ordering assertion
    fails RED). Post-fix the 2-digit badge is offset further left by exactly
    its extra width.
    """
    pb3 = _pagebox_with_text(recognized="hello")
    pb3.bubble_no = 3
    _scene3, item3 = _scene_with_box(pb3)
    item3.refresh_badge()

    pb12 = _pagebox_with_text(recognized="hello")
    pb12.bubble_no = 12
    _scene12, item12 = _scene_with_box(pb12)
    item12.refresh_badge()

    assert item12._badge.scenePos().x() < item3._badge.scenePos().x(), (
        "the multi-digit badge must sit further TL than the single-digit badge"
    )
    # The gap is the SAME 2px for both (placement = actual size + 2px).
    sbr = item3.sceneBoundingRect()
    for item in (item3, item12):
        r = item._badge.rect()
        pos = item._badge.scenePos()
        gap_x = sbr.left() - pos.x() - r.width()
        gap_y = sbr.top() - pos.y() - r.height()
        assert gap_x == pytest.approx(2.0, abs=0.01)
        assert gap_y == pytest.approx(2.0, abs=0.01)


@pytest.mark.gui
def test_badge_edge_flip_uses_actual_size(qtbot) -> None:
    """The edge-flip uses the ACTUAL badge size and the digit stays contained.

    A box at (0,0,50,50) in a 1000x1000 scene: sceneBoundingRect is
    (-1,-1,52,52) (2px pen); the outside candidate (actual badge size) would
    clip off the page TL edge, so the badge flips INSIDE at (1,1). FAILS
    pre-fix on the containment half: the digit ('12' at margin 4, pos (3,-1))
    overflows the fixed 20x14 badge even though the (size-independent)
    inside-flip inset lands at (1,1) either way.
    """
    pb = PageBox(box=Box(0, 0, 50, 50), origin=DETECTED)  # the page TL corner
    pb.bubble_no = 12
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 1000.0, 1000.0)  # the page bounds (pre-add)
    item = BoxItem(pb)
    scene.addItem(item)
    item.refresh_badge()

    sbr = item.sceneBoundingRect()
    assert sbr.left() == pytest.approx(-1.0, abs=0.01)
    assert sbr.top() == pytest.approx(-1.0, abs=0.01)

    # The outside candidate would clip -> flipped inside-top-left (inset 2px).
    pos = item._badge.scenePos()
    assert pos.x() == pytest.approx(1.0, abs=0.01)
    assert pos.y() == pytest.approx(1.0, abs=0.01)

    # The badge is the ACTUAL digit-sized rect and the digit is fully contained.
    digit = item._badge_digit
    r = item._badge.rect()
    assert r.width() == pytest.approx(digit.boundingRect().width() + 2.0 * 4.0, abs=0.01)
    assert r.height() == pytest.approx(digit.boundingRect().height() + 2.0 * 2.0, abs=0.01)
    digit_local = QRectF(digit.pos(), digit.boundingRect().size())
    assert digit_local.left() >= 0.0
    assert digit_local.top() >= 0.0
    assert digit_local.right() <= r.width()
    assert digit_local.bottom() <= r.height()


# ===========================================================================
# Plan 04-04 Task 2 — InspectorPanel dock + Toggle Text Overlay (T)
# ===========================================================================
#
# The InspectorPanel (D-08) is a new QWidget surfaced in a QDockWidget tabbed
# with Tools. It shows both text fields (Recognized + Translation) + the bubble
# number + origin/language/vertical metadata for the selected box. Edits commit
# through the Plan 01 setters (set_recognized_text_edited for manual recognized
# edits, set_translation for translation) and the panel emits typed Signals the
# MainWindow wires to the actual pagebox mutation + boxes_modified push. The
# Toggle Text Overlay action (T, D-12) is an independent third visibility layer
# on the canvas (independent of M mask and Shift+M box).

from manga_ai_studio.gui.inspector_panel import InspectorPanel  # noqa: E402


def _make_inspector(qtbot) -> InspectorPanel:
    """Build an InspectorPanel added to qtbot (so it can parent widgets)."""
    panel = InspectorPanel()
    qtbot.addWidget(panel)
    return panel


@pytest.mark.gui
def test_inspector_panel_constructs(qtbot) -> None:
    """InspectorPanel is a QWidget with the expected field widgets (UI-SPEC §18)."""
    from PySide6.QtWidgets import QCheckBox, QLabel, QSpinBox, QTextEdit

    panel = _make_inspector(qtbot)
    assert panel.objectName() == "inspector_panel"
    assert isinstance(panel.bubble_spin, QSpinBox)
    assert isinstance(panel.origin_label, QLabel)
    assert isinstance(panel.recognized_edit, QTextEdit)
    assert isinstance(panel.translation_edit, QTextEdit)
    assert isinstance(panel.language_label, QLabel)
    assert isinstance(panel.vertical_check, QCheckBox)


@pytest.mark.gui
def test_inspector_panel_has_class_scope_signals(qtbot) -> None:
    """InspectorPanel declares translation_changed/recognized_edited/bubble_no_changed Signals."""
    panel = _make_inspector(qtbot)
    # Class-scope Signal descriptors exist on the type.
    assert hasattr(type(panel), "translation_changed")
    assert hasattr(type(panel), "recognized_edited")
    assert hasattr(type(panel), "bubble_no_changed")
    assert hasattr(type(panel), "vertical_changed")


@pytest.mark.gui
def test_inspector_empty_state_disables_fields(qtbot) -> None:
    """With no box selected the Inspector shows empty-state copy + disables fields."""
    panel = _make_inspector(qtbot)
    panel.clear()
    assert panel.bubble_spin.isEnabled() is False
    assert panel.recognized_edit.isEnabled() is False
    assert panel.translation_edit.isEnabled() is False
    assert panel.vertical_check.isEnabled() is False


@pytest.mark.gui
def test_inspector_load_box_populates_fields(qtbot) -> None:
    """load_box populates bubble_no/origin/recognized/translation/language/vertical from the pagebox."""
    pb = _pagebox_with_text(recognized="hello", translation="hola")
    pb.bubble_no = 7
    pb.payload.language = "ja"
    pb.payload.vertical = True

    panel = _make_inspector(qtbot)
    panel.load_box(pb)

    assert panel.bubble_spin.value() == 7
    assert panel.bubble_spin.isEnabled() is True
    assert "Detected" in panel.origin_label.text()  # DETECTED origin
    assert panel.recognized_edit.toPlainText() == "hello"
    assert panel.translation_edit.toPlainText() == "hola"
    assert panel.language_label.text() == "ja"
    assert panel.vertical_check.isChecked() is True


@pytest.mark.gui
def test_inspector_load_box_blocks_signals_during_populate(qtbot) -> None:
    """load_box does not re-emit its change signals while populating (no spurious commits)."""
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = 3

    panel = _make_inspector(qtbot)
    fired: list = []
    panel.recognized_edited.connect(lambda t: fired.append(("rec", t)))
    panel.translation_changed.connect(lambda t: fired.append(("tr", t)))
    panel.bubble_no_changed.connect(lambda n: fired.append(("bub", n)))

    panel.load_box(pb)
    assert fired == [], f"load_box must not emit change signals during populate; got {fired}"


@pytest.mark.gui
def test_inspector_recognized_edit_emits_recognized_edited(qtbot) -> None:
    """Editing the Recognized field emits recognized_edited(text) via connect_commit_handlers."""
    panel = _make_inspector(qtbot)
    captured: list[str] = []
    panel.connect_commit_handlers(
        on_recognized=captured.append,
        on_translation=lambda _t: None,
        on_bubble=lambda _n: None,
        on_vertical=lambda _v: None,
    )
    pb = _pagebox_with_text(recognized="hello")
    panel.load_box(pb)
    panel.recognized_edit.setPlainText("corrected")
    panel._commit_recognized()
    assert captured == ["corrected"]


@pytest.mark.gui
def test_inspector_translation_edit_emits_translation_changed(qtbot) -> None:
    """Editing the Translation field emits translation_changed(text) on commit."""
    panel = _make_inspector(qtbot)
    captured: list[str] = []
    panel.connect_commit_handlers(
        on_recognized=lambda _t: None,
        on_translation=captured.append,
        on_bubble=lambda _n: None,
        on_vertical=lambda _v: None,
    )
    pb = _pagebox_with_text(recognized="hello")
    panel.load_box(pb)
    panel.translation_edit.setPlainText("hola")
    panel._commit_translation()
    assert captured == ["hola"]


@pytest.mark.gui
def test_inspector_bubble_spin_emits_bubble_no_changed(qtbot) -> None:
    """The Bubble # QSpinBox emits bubble_no_changed(int) on value change."""
    panel = _make_inspector(qtbot)
    captured: list[int] = []
    panel.connect_commit_handlers(
        on_recognized=lambda _t: None,
        on_translation=lambda _t: None,
        on_bubble=captured.append,
        on_vertical=lambda _v: None,
    )
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = 1
    panel.load_box(pb)
    panel.bubble_spin.setValue(9)
    # editingFinished fires on focus-loss/Enter (the real commit path), NOT on
    # a programmatic setValue (Qt by design). Emit it to simulate the focus-loss
    # the real UI produces when the user tabs away from the spinbox.
    panel.bubble_spin.editingFinished.emit()
    assert captured == [9]


@pytest.mark.gui
def test_inspector_vertical_check_emits_vertical_changed(qtbot) -> None:
    """The Vertical checkbox emits vertical_changed(bool) on toggle."""
    panel = _make_inspector(qtbot)
    captured: list[bool] = []
    panel.connect_commit_handlers(
        on_recognized=lambda _t: None,
        on_translation=lambda _t: None,
        on_bubble=lambda _n: None,
        on_vertical=captured.append,
    )
    pb = _pagebox_with_text(recognized="hello")
    panel.load_box(pb)  # vertical defaults False
    panel.vertical_check.setChecked(True)
    assert captured == [True]


@pytest.mark.gui
def test_inspector_bubble_spin_range_is_bounded(qtbot) -> None:
    """The Bubble # QSpinBox is bounded (0..9999) per T-4-08 tampering
    mitigation — 0 is the unset sentinel (displayed as an em dash, plan 04-10)."""
    panel = _make_inspector(qtbot)
    assert panel.bubble_spin.minimum() == 0
    assert panel.bubble_spin.maximum() == 9999


@pytest.mark.gui
def test_inspector_origin_label_hue_colored(qtbot) -> None:
    """The Origin label is hue-colored: green for detected, amber for user (UI-SPEC §18)."""
    panel = _make_inspector(qtbot)
    # Detected -> green hue in the stylesheet.
    pb_det = _pagebox_with_text(recognized="hi")
    panel.load_box(pb_det)
    det_ss = panel.origin_label.styleSheet()
    assert "5fd068" in det_ss.lower() or "green" in det_ss.lower()

    # User -> amber hue.
    pb_usr = PageBox(box=Box(10, 10, 100, 100), origin=USER)
    pb_usr.set_recognized_text("hi")
    panel.load_box(pb_usr)
    usr_ss = panel.origin_label.styleSheet()
    assert "f5a623" in usr_ss.lower() or "amber" in usr_ss.lower()


@pytest.mark.gui
def test_inspector_unchanged_focus_cycle_is_noop(qtbot) -> None:
    """WR-01: focus-out commits with NO value change are silent no-ops — no
    recognized_edited/translation_changed/bubble_no_changed emission (which
    would flip edited=True on an unedited box, pin manual_override on a box
    that never had a bubble number, and push a no-op BOXES snapshot)."""
    panel = _make_inspector(qtbot)
    captured: dict[str, list] = {"r": [], "t": [], "b": []}
    panel.connect_commit_handlers(
        on_recognized=captured["r"].append,
        on_translation=captured["t"].append,
        on_bubble=captured["b"].append,
        on_vertical=lambda _v: None,
    )
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = None  # the spin displays 0 — the unset sentinel — for None
    panel.load_box(pb)

    # Click in + click away with zero typing on every field.
    panel._commit_recognized()
    panel._commit_translation()
    panel.bubble_spin.editingFinished.emit()
    assert captured["r"] == []
    assert captured["t"] == []
    assert captured["b"] == []

    # The same unchanged focus cycle on a box WITH a bubble number is a no-op too.
    pb.bubble_no = 3
    panel.load_box(pb)
    panel.bubble_spin.editingFinished.emit()
    assert captured["b"] == []


@pytest.mark.gui
def test_inspector_bubble_changed_commit_still_emits(qtbot) -> None:
    """WR-01: a REAL bubble-value change still commits — only unchanged focus
    cycles are no-ops (a manual bubble # must still pin manual_override)."""
    panel = _make_inspector(qtbot)
    captured: list[int] = []
    panel.connect_commit_handlers(
        on_recognized=lambda _t: None,
        on_translation=lambda _t: None,
        on_bubble=captured.append,
        on_vertical=lambda _v: None,
    )
    pb = _pagebox_with_text(recognized="hello")
    pb.bubble_no = None  # displays 0 — the unset sentinel; changing it to 7 is a real manual edit
    panel.load_box(pb)
    panel.bubble_spin.setValue(7)
    panel.bubble_spin.editingFinished.emit()
    assert captured == [7]


@pytest.mark.gui
def test_inspector_unchanged_commit_is_noop_end_to_end(qtbot, tmp_path) -> None:
    """WR-01 end-to-end: an Inspector focus cycle with no edit must NOT flip
    edited=True, pin manual_override, or push a BOXES undo entry — the D-04
    confirm-prompt / D-16 preserve-manual / no-op-undo consequences."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 50, 60)])[0]
    item.pagebox.set_recognized_text("hello")
    item.setSelected(True)
    QApplication.processEvents()
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    # The panel displays the box (as the selection follower would)…
    window.inspector_panel.load_box(item.pagebox)
    # …and the user clicks in + away without typing.
    window.inspector_panel._commit_recognized()
    assert emitted == [], "an unchanged commit must not push a BOXES snapshot"
    assert item.pagebox.edited is False, "an unchanged commit must not flip D-04"

    # Same for the bubble spinbox: no value change -> no manual_override pin.
    assert item.pagebox.bubble_no is None
    window.inspector_panel.bubble_spin.editingFinished.emit()
    assert emitted == []
    assert item.pagebox.manual_override is False


# -- UAT test 6 gap closure round 3 (plan 04-10): bubble # 1 manually
# -- assignable (0-sentinel)
# The spinbox range was 1..9999 with bubble_no=None displayed as value 1, so
# the WR-01 guard (number != _loaded_bubble) dropped a user-entered 1 as an
# "unchanged focus cycle" — bubble 1 could never be assigned manually. The
# fix: 0 is the UNSET sentinel (setRange(0, 9999) + setSpecialValueText em
# dash); load_box maps None -> 0; the handler maps a 0 commit to
# bubble_no=None + manual_override=False (clearing is not an override).


@pytest.mark.gui
def test_inspector_bubble_spin_unset_sentinel(qtbot) -> None:
    """The unset sentinel is 0: range 0..9999, initial value 0, em-dash display.

    FAILS pre-fix: minimum() == 1 and a fresh panel's text() at value 0 is '1'
    (the phantom unset display). Post-fix: value 0 renders the setSpecialValueText
    em dash, value 1 renders '1' (probe-verified on PySide6 6.10.1).
    """
    panel = _make_inspector(qtbot)
    assert panel.bubble_spin.minimum() == 0
    assert panel.bubble_spin.maximum() == 9999
    assert panel.bubble_spin.value() == 0
    assert panel.bubble_spin.text() == "\u2014"  # the em dash (unset state)
    # A real value shows its digits (the special text is display-only).
    panel.bubble_spin.setValue(1)
    assert panel.bubble_spin.text() == "1"


@pytest.mark.gui
def test_inspector_bubble_1_commit_assigns_unset_box(qtbot) -> None:
    """Entering 1 + Enter on an unset box commits bubble_no_changed(1).

    FAILS pre-fix: the WR-01 guard drops it (1 == _loaded_bubble 1, the unset
    placeholder) -> captured == [] — the exact UAT test-6 bug. Post-fix:
    1 != the 0 sentinel, so the commit fires.
    """
    panel = _make_inspector(qtbot)
    captured: list[int] = []
    panel.connect_commit_handlers(
        on_recognized=lambda _t: None,
        on_translation=lambda _t: None,
        on_bubble=captured.append,
        on_vertical=lambda _v: None,
    )
    pb = _pagebox_with_text(recognized="hello")  # bubble_no=None (unset)
    panel.load_box(pb)
    panel.bubble_spin.setValue(1)
    panel.bubble_spin.editingFinished.emit()
    assert captured == [1]


@pytest.mark.gui
def test_inspector_bubble_1_assigned_and_cleared_end_to_end(qtbot, tmp_path) -> None:
    """End-to-end: bubble # 1 assigns bubble_no=1 + manual_override=True (the
    D-16 amber badge, UAT test-6 truth); committing 0 clears (bubble_no=None,
    manual_override=False — unset is not an override).

    FAILS pre-fix on the assignment half: bubble_no stays None (the guard
    drops 1) — no badge. The clear half needs the new sentinel handler.
    """
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 50, 60)])[0]
    item.setSelected(True)
    QApplication.processEvents()

    # Assignment: entering 1 + Enter on the unset box.
    window.inspector_panel.load_box(item.pagebox)
    assert item.pagebox.bubble_no is None
    window.inspector_panel.bubble_spin.setValue(1)
    window.inspector_panel.bubble_spin.editingFinished.emit()
    QApplication.processEvents()
    assert item.pagebox.bubble_no == 1
    assert item.pagebox.manual_override is True  # D-16 pin
    assert item._badge_digit.toPlainText() == "1"  # refreshed amber badge

    # Clearing: reload shows 1; committing 0 clears the number.
    window.inspector_panel.load_box(item.pagebox)
    assert window.inspector_panel.bubble_spin.value() == 1
    window.inspector_panel.bubble_spin.setValue(0)
    window.inspector_panel.bubble_spin.editingFinished.emit()
    QApplication.processEvents()
    assert item.pagebox.bubble_no is None
    assert item.pagebox.manual_override is False


@pytest.mark.gui
def test_inspector_commit_undo_restores_pre_edit_text(qtbot, tmp_path) -> None:
    """CR-01 regression: an Inspector commit must push a PRE-edit snapshot with
    DETACHED payloads — undo restores the pre-edit text, not the post-edit text
    (Pitfall 8 push-side; mirrors test_inline_editor_commit_emits_boxes_modified_with_before_state).

    Without the detach in ``_inspector_commit_pre``, the snapshot PageBoxes
    share the live TextBlock, the commit handler mutates it in place, and the
    push-time ``PageBox.copy()`` (which runs AFTER the mutation) captures the
    NEW text — so Ctrl+Z would restore the post-edit text (a no-op undo)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 50, 60)])[0]
    item.pagebox.set_recognized_text("before")
    item.setSelected(True)
    QApplication.processEvents()

    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    window._on_inspector_recognized_committed("after")
    assert item.pagebox.payload.text == "after"
    # The pushed BEFORE snapshot must carry the pre-edit text + a detached
    # payload (the load-translations/inline-editor push contract).
    assert len(emitted) == 1
    before = emitted[0]
    assert before[0].payload.text == "before"
    assert before[0].payload is not item.pagebox.payload

    # Full undo round-trip: Ctrl+Z restores the pre-edit text.
    window.on_undo()
    QApplication.processEvents()
    restored = window.canvas._box_items[0].pagebox
    assert restored.payload.text == "before", (
        "undo of an Inspector commit must restore the PRE-edit text; a no-op "
        "undo (aliased snapshot) would restore 'after'"
    )


@pytest.mark.gui
def test_inspector_refreshes_after_inline_editor_commit(qtbot, tmp_path) -> None:
    """WR-05: after an inline-edit commit the Inspector must display the NEW
    text — the box stays selected while editing (UI-SPEC §15), so the
    always-present view (D-08) must follow the commit without a selection
    change (it previously went stale until the next selection)."""
    from manga_ai_studio.gui.inline_editor import InlineEditor

    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 50, 60)])[0]
    item.pagebox.set_recognized_text("old")
    item.setSelected(True)
    QApplication.processEvents()
    window.inspector_panel.load_box(item.pagebox)
    assert window.inspector_panel.recognized_edit.toPlainText() == "old"

    # Double-click style inline edit -> commit (the REAL inline-editor path).
    editor = InlineEditor(window.canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("new text")
    editor.commit()
    QApplication.processEvents()

    assert item.pagebox.payload.text == "new text"
    # The Inspector must show the committed text with NO selection change
    # (the box is still the selected one after the commit).
    assert item.isSelected() is True
    assert window.inspector_panel.recognized_edit.toPlainText() == "new text"


# ===========================================================================
# Task 1 — InlineEditor (QGraphicsProxyWidget + QTextEdit) + BoxItem edit-mode
# hooks (plan 04-05 RED gate). Tests reference the plan-04-05 contract before
# the implementation exists: the module import above fails at collection, the
# RED gate.
# ===========================================================================


def _editor_box(canvas: EditorCanvas, text: str = "hello", origin: str = USER) -> BoxItem:
    """Add a text-carrying box to the canvas layer and return the item.

    The text is written via the OCR-write setter (``set_recognized_text``,
    edited=False) so D-04 tests can assert the manual-edit path flips it.
    """
    item = _add_user_box(canvas, Box(30, 30, 130, 130))
    item.pagebox.set_recognized_text(text)
    return item


@pytest.mark.gui
def test_inline_editor_proxy_created_on_scene_z1100_hidden(qtbot) -> None:
    """The InlineEditor owns a QGraphicsProxyWidget parented to the SCENE (not
    the box — UI-SPEC §15 anti-pattern), z=1100 (above the cursor z=1000), hidden."""
    from PySide6.QtWidgets import QGraphicsProxyWidget

    canvas = _canvas_with_image_and_boxes(qtbot)
    editor = InlineEditor(canvas)
    assert isinstance(editor._proxy, QGraphicsProxyWidget)
    assert editor._proxy.scene() is canvas.scene()
    assert editor._proxy.zValue() == 1100
    assert editor._proxy.isVisible() is False
    assert editor.is_active() is False


@pytest.mark.gui
def test_inline_editor_enter_shows_proxy_populated_and_positioned(qtbot) -> None:
    """enter(box_item) shows the proxy at the box rect inset 2px, populated with
    the current-focus text (recognized when no translation — D-08)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="こんにちは")
    editor = InlineEditor(canvas)
    editor.enter(item)
    assert editor.is_active() is True
    assert editor._proxy.isVisible() is True
    assert editor._focus_field == "recognized"
    assert editor._text_edit.toPlainText() == "こんにちは"
    rect = item.sceneBoundingRect()
    tl = editor._proxy.sceneBoundingRect().topLeft()
    assert abs(tl.x() - (rect.left() + 2)) < 0.5
    assert abs(tl.y() - (rect.top() + 2)) < 0.5
    assert editor._proxy.sceneBoundingRect().width() == pytest.approx(rect.width() - 4, abs=1.0)


@pytest.mark.gui
def test_inline_editor_focus_rule_translation_wins(qtbot) -> None:
    """D-08 current-focus rule: once a translation exists, the editor edits the
    TRANSLATION, not the recognized text."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="recognized text")
    item.pagebox.set_translation("translated text")
    editor = InlineEditor(canvas)
    editor.enter(item)
    assert editor._focus_field == "translation"
    assert editor._text_edit.toPlainText() == "translated text"


@pytest.mark.gui
def test_inline_editor_enter_empty_box_opens_empty(qtbot) -> None:
    """A box with no text (payload None) still opens the editor with empty text
    (the payload-None guard keeps the edit session safe — checker W1)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _add_user_box(canvas, Box(30, 30, 130, 130))  # payload None
    editor = InlineEditor(canvas)
    editor.enter(item)
    assert editor.is_active() is True
    assert editor._focus_field == "recognized"
    assert editor._text_edit.toPlainText() == ""


@pytest.mark.gui
def test_inline_editor_enter_commits_previous_box_first(qtbot) -> None:
    """One editor instance at a time (§15): entering a DIFFERENT box commits the
    previous edit first (safer than discarding the user's work)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    a = _editor_box(canvas, text="before", origin=USER)
    b = _add_user_box(canvas, Box(60, 60, 160, 160))
    b.pagebox.set_recognized_text("b")
    editor = InlineEditor(canvas)
    editor.enter(a)
    editor._text_edit.setPlainText("after")
    editor.enter(b)
    assert editor._active_box_item is b
    assert a.pagebox.payload.text == "after"
    assert a.pagebox.edited is True  # the auto-commit of A used the manual-edit setter


@pytest.mark.gui
def test_inline_editor_enter_reenabling_same_box_keeps_uncommitted_text(qtbot) -> None:
    """Re-entering the SAME box just re-focuses — uncommitted text is preserved."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("typed but not committed")
    editor.enter(item)
    assert editor._text_edit.toPlainText() == "typed but not committed"


@pytest.mark.gui
def test_inline_editor_enter_sets_box_edit_mode(qtbot) -> None:
    """While the editor is active the box's move/resize interaction is disabled
    (D-07) — enter() flips the BoxItem edit-mode flag."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="hello")
    editor = InlineEditor(canvas)
    editor.enter(item)
    assert item._edit_mode is True
    editor.commit()
    assert item._edit_mode is False


@pytest.mark.gui
def test_inline_editor_commit_translation_writes_set_translation(qtbot) -> None:
    """Enter commits the focus field: translation focus -> pagebox.set_translation
    (the D-13 MT seam). The edited flag is NOT touched by a translation commit."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="recognized")
    item.pagebox.set_translation("old translation")
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("new translation")
    editor.commit()
    assert item.pagebox.payload.translation == "new translation"
    assert item.pagebox.edited is False  # translation commit does not set D-04
    assert editor.is_active() is False
    assert editor._proxy.isVisible() is False
    assert item._edit_mode is False


@pytest.mark.gui
def test_inline_editor_commit_recognized_sets_edited_true(qtbot) -> None:
    """Recognized-focus commit -> pagebox.set_recognized_text_edited (D-04):
    writes payload.text AND sets edited=True so a re-OCR must confirm (T-4-09)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="old text")
    assert item.pagebox.edited is False  # OCR-write path
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("corrected text")
    editor.commit()
    assert item.pagebox.payload.text == "corrected text"
    assert item.pagebox.edited is True


@pytest.mark.gui
def test_inline_editor_recognized_commit_routes_through_edited_setter(qtbot, monkeypatch) -> None:
    """The recognized-focus commit calls the CENTRALIZED manual-edit setter
    (Plan 01) — never set_recognized_text (OCR path) and never a direct
    payload.text write (bypasses the payload-None guard)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="old")
    calls: list[str] = []
    orig = item.pagebox.set_recognized_text_edited
    monkeypatch.setattr(item.pagebox, "set_recognized_text_edited", lambda t: calls.append(t) or orig(t))
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("edited text")
    editor.commit()
    assert calls == ["edited text"]
    assert item.pagebox.payload.text == "edited text"
    assert item.pagebox.edited is True


@pytest.mark.gui
def test_inline_editor_commit_emits_boxes_modified_with_before_state(qtbot) -> None:
    """A real edit pushes a BOXES snapshot with the PRE-edit text (CR-01 pre-state
    contract) — undo restores the pre-edit text, not the post-edit text (Pitfall 8)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("after")
    editor.commit()
    assert len(captured) == 1
    before = captured[0]
    assert len(before) == 1
    assert before[0].payload.text == "before"  # snapshot-time text, NOT "after"
    assert item.pagebox.payload.text == "after"


@pytest.mark.gui
def test_inline_editor_commit_noop_when_unchanged(qtbot) -> None:
    """Committing without edits is a silent no-op: no boxes_modified push, just hide."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="unchanged")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor.commit()
    assert len(captured) == 0
    assert editor.is_active() is False
    assert item.pagebox.payload.text == "unchanged"


@pytest.mark.gui
def test_inline_editor_cancel_discards_no_emit(qtbot) -> None:
    """Esc/cancel discards edits since entry: no model write, no snapshot push (D-05)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("discarded")
    editor.cancel()
    assert len(captured) == 0
    assert editor.is_active() is False
    assert item.pagebox.payload.text == "before"
    assert item._edit_mode is False


@pytest.mark.gui
def test_inline_editor_enter_key_commits(qtbot) -> None:
    """Bare Enter (no modifier) commits the edit (UI-SPEC §15)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("via enter")
    key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    editor._text_edit.keyPressEvent(key)
    assert item.pagebox.payload.text == "via enter"
    assert editor.is_active() is False


@pytest.mark.gui
def test_inline_editor_shift_enter_inserts_newline(qtbot) -> None:
    """Shift+Enter inserts a newline (standard QTextEdit convention) — does NOT commit."""
    from PySide6.QtGui import QTextCursor

    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.moveCursor(QTextCursor.MoveOperation.End)
    key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    editor._text_edit.keyPressEvent(key)
    assert editor._text_edit.toPlainText() == "before\n"
    assert editor.is_active() is True  # still editing


@pytest.mark.gui
def test_inline_editor_esc_key_cancels(qtbot) -> None:
    """Esc inside the editor cancels: no snapshot push, text unchanged (D-05)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("discard me")
    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    editor._text_edit.keyPressEvent(esc)
    assert len(captured) == 0
    assert editor.is_active() is False
    assert item.pagebox.payload.text == "before"


@pytest.mark.gui
def test_inline_editor_commit_refreshes_text_overlay(qtbot) -> None:
    """After a commit the BoxItem text overlay re-renders the new text (the
    overlay shows the current-focus text — the canvas reflects the edit at once)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    editor = InlineEditor(canvas)
    editor.enter(item)
    editor._text_edit.setPlainText("after")
    editor.commit()
    assert item._text_overlay.toPlainText() == "after"


@pytest.mark.gui
def test_inline_editor_proxy_reused_across_sessions(qtbot) -> None:
    """Only ONE proxy exists: enter/commit/enter reuses the same instance (UI-SPEC §15)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    a = _editor_box(canvas, text="a")
    b = _add_user_box(canvas, Box(60, 60, 160, 160))
    b.pagebox.set_recognized_text("b")
    editor = InlineEditor(canvas)
    proxy = editor._proxy
    editor.enter(a)
    editor.commit()
    editor.enter(b)
    assert editor._proxy is proxy


@pytest.mark.gui
def test_boxitem_enter_exit_edit_mode_wrappers(qtbot) -> None:
    """BoxItem exposes enter_edit_mode/exit_edit_mode/set_edit_mode — the hooks
    the canvas/InlineEditor use to disable move/resize while editing (D-07)."""
    scene = QGraphicsScene()
    pb = PageBox(box=Box(0, 0, 50, 50), origin=USER)
    item = BoxItem(pb)
    scene.addItem(item)
    assert hasattr(item, "enter_edit_mode")
    assert hasattr(item, "exit_edit_mode")
    assert item._edit_mode is False
    item.enter_edit_mode()
    assert item._edit_mode is True
    item.exit_edit_mode()
    assert item._edit_mode is False


@pytest.mark.gui
def test_boxitem_set_edit_mode_toggles_handle_interactivity(qtbot) -> None:
    """set_edit_mode(True) makes the corner handles non-interactive (they stay
    VISIBLE — the box is still selected — but cannot arm a resize, §15)."""
    scene = QGraphicsScene()
    pb = PageBox(box=Box(0, 0, 50, 50), origin=USER)
    item = BoxItem(pb)
    scene.addItem(item)
    rest = {c: h.acceptedMouseButtons() for c, h in item.handles.items()}
    item.set_edit_mode(True)
    for h in item.handles.values():
        assert h.acceptedMouseButtons() == Qt.MouseButton.NoButton
    item.set_edit_mode(False)
    for c, h in item.handles.items():
        assert h.acceptedMouseButtons() == rest[c]


# ===========================================================================
# Task 2 — canvas double-click dispatch + inline-editor-active guard
# (plan 04-05 RED gate). Tests reference canvas._inline_editor + the
# mouseDoubleClickEvent/guard contract before the canvas changes exist.
# ===========================================================================


@pytest.mark.gui
def test_canvas_double_click_box_opens_inline_editor(qtbot) -> None:
    """Double-click over a BoxItem (box layer visible) opens the inline editor
    with the box's current-focus text (D-05)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="hello")
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    editor = canvas._inline_editor
    assert editor.is_active() is True
    assert editor._active_box_item is item
    assert editor._text_edit.toPlainText() == "hello"
    assert item.isSelected() is True  # double-click also selects (UI-SPEC §15)


@pytest.mark.gui
def test_canvas_double_click_empty_canvas_noop(qtbot) -> None:
    """Double-click over empty canvas does NOT open the editor."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    _editor_box(canvas, text="hello")  # box at 30..130; click far away
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 180, 180))
    assert canvas._inline_editor.is_active() is False


@pytest.mark.gui
def test_canvas_double_click_hidden_box_layer_noop(qtbot) -> None:
    """Double-click with the box layer hidden does NOT open the editor (Pitfall 5:
    a hidden layer skips box interaction entirely)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    _editor_box(canvas, text="hello")
    canvas.set_box_overlay_visible(False)
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    assert canvas._inline_editor.is_active() is False


@pytest.mark.gui
def test_canvas_click_away_commits_inline_editor(qtbot) -> None:
    """Click-away (a press OUTSIDE the editor proxy) commits the edit + consumes
    the event — no move/resize/select dispatch runs (RESEARCH Pitfall 3, §15)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    editor = canvas._inline_editor
    assert editor.is_active() is True
    editor._text_edit.setPlainText("after")
    # Press at empty canvas (180,180 is outside the box rect 30..130).
    canvas.mousePressEvent(_press_at(canvas, 180, 180))
    assert editor.is_active() is False
    assert item.pagebox.payload.text == "after"
    assert item.pagebox.edited is True  # D-04 manual-edit path
    assert len(captured) == 1  # one BOXES push from the commit
    # The event was consumed — the click did NOT deselect the box.
    assert item.isSelected() is True


@pytest.mark.gui
def test_canvas_click_inside_editor_does_not_commit(qtbot) -> None:
    """A press INSIDE the editor proxy goes to the widget (super()) — the edit
    session stays open, the box does not move (D-07)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    editor = canvas._inline_editor
    canvas.mousePressEvent(_press_at(canvas, 70, 70))  # inside the proxy
    assert editor.is_active() is True
    assert item.pagebox.payload.text == "before"
    assert len(captured) == 0
    assert canvas._moving_box is None  # no move armed


@pytest.mark.gui
def test_canvas_esc_cancels_inline_editor_keeps_box_selected(qtbot) -> None:
    """Esc while editing cancels (no snapshot push) AND does NOT fall through to
    box-deselect — the box stays selected (UI-SPEC §Shortcuts priority)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    captured: list[list] = []
    canvas.boxes_modified.connect(captured.append)
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    editor = canvas._inline_editor
    editor._text_edit.setPlainText("changed")
    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(esc)
    assert editor.is_active() is False
    assert len(captured) == 0
    assert item.pagebox.payload.text == "before"
    assert item.isSelected() is True  # NOT deselected (editor-scoped Esc)


@pytest.mark.gui
def test_canvas_edit_mode_drag_inside_editor_does_not_move_box(qtbot) -> None:
    """A drag that starts inside the editor selects text in the QTextEdit — the
    box does NOT move (D-07: edit mode disables move/resize)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="hello")
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    editor = canvas._inline_editor
    start_rect = QRectF(item.rect())
    canvas.mousePressEvent(_press_at(canvas, 60, 60))  # inside proxy
    canvas.mouseMoveEvent(_move_at(canvas, 90, 60))
    canvas.mouseReleaseEvent(_release_at(canvas, 90, 60))
    assert item.rect() == start_rect  # box did NOT move
    assert editor.is_active() is True  # still editing


@pytest.mark.gui
def test_canvas_f2_opens_inline_editor_on_selected_box(qtbot) -> None:
    """F2 with a box selected opens the inline editor (UI-SPEC §Shortcuts — the
    keyboard alternative to double-click)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="hello")
    canvas.mousePressEvent(_press_at(canvas, 60, 60))  # select
    assert item.isSelected() is True
    f2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F2, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(f2)
    assert canvas._inline_editor.is_active() is True
    assert canvas._inline_editor._active_box_item is item


@pytest.mark.gui
def test_canvas_f2_without_selection_noop(qtbot) -> None:
    """F2 with no box selected does nothing (no editor opens)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    f2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F2, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(f2)
    assert canvas._inline_editor.is_active() is False


@pytest.mark.gui
def test_canvas_set_boxes_commits_active_inline_editor(qtbot) -> None:
    """Rebuilding the box layer (page switch / detection / restore) commits any
    active edit first — a stale editor never dangles over a removed box."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="before")
    canvas.mouseDoubleClickEvent(_dblclick_at(canvas, 60, 60))
    editor = canvas._inline_editor
    assert editor.is_active() is True
    editor._text_edit.setPlainText("after")
    canvas.set_boxes(user_pageboxes=[], detected_pageboxes=[])
    assert editor.is_active() is False
    assert item.pagebox.payload.text == "after"
    assert item.pagebox.edited is True


# ===========================================================================
# Plan 04-06 Task 1 — OCR dispatcher (Worker + _op_running + status-bar
# progress + D-04 confirm gates + first-run UX) — TDD RED gate
# ===========================================================================
#
# The dispatcher mirrors the detect_text / _run_detection_task /
# _resolve_detection_model_path cluster (main_window.py). All tests use a
# MOCKED model via monkeypatched backend_factory so the ~450MB manga-ocr
# model is never downloaded in CI; the real-model integration test is
# skip-gated on is_ocr_downloaded() (04-03 convention).


class _FakeOCRModel:
    """Duck-typed TorchOCRModel stand-in: records load/recognize calls and
    returns a fixed recognition string (no torch / manga_ocr needed)."""

    def __init__(self, text: str = "認識テキスト"):
        self.text = text
        self.load_calls: list = []
        self.recognize_calls: list = []

    def load(self, model_path, device="auto") -> None:
        self.load_calls.append((model_path, device))

    def recognize(self, image) -> str:
        self.recognize_calls.append(image)
        return self.text


def _window_with_page(qtbot, tmp_path, size: int = 120) -> MainWindow:
    """Build a shown MainWindow with one real PNG page loaded (mirrors
    test_moved_box_via_real_events_persists_round_trip's setup)."""
    from PIL import Image as PILImage

    page = tmp_path / "page.png"
    PILImage.new("RGB", (size, size), color=(200, 200, 200)).save(page)
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(tmp_path)
    window.show()
    QApplication.processEvents()
    return window


def _add_user_box_window(window: MainWindow, box: Box) -> BoxItem:
    """Seed one user box on the window's canvas without a history push."""
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([PageBox(box=box, origin=USER)], [])
    finally:
        window._suppress_boxes_push = False
    return window.canvas._box_items[0]


def _seed_boxes_window(window: MainWindow, boxes: list) -> list:
    """Seed N user boxes in ONE set_boxes call (no history push, plan 04-07).

    set_boxes REBUILDS the layer, so repeated single-box calls would replace
    the previous box; the multi-box variants (auto-number, batch translation
    apply) need all boxes present in one layer.
    """
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([PageBox(box=b, origin=USER) for b in boxes], [])
    finally:
        window._suppress_boxes_push = False
    return list(window.canvas._box_items)


@pytest.mark.gui
def test_run_ocr_selected_dispatches_worker_not_inline(qtbot, tmp_path, monkeypatch) -> None:
    """run_ocr_selected dispatches a Worker (async — T-4-11) and writes the
    recognized text via set_recognized_text (edited=False) when it finishes."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.setSelected(True)
    fake = _FakeOCRModel("認識")
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: fake,
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)
    window.run_ocr_selected()
    # The worker was DISPATCHED, not called inline on the GUI thread (T-4-11).
    assert window._op_running is True
    assert fake.recognize_calls == []
    assert "Recognizing text" in window.status_bar_left.text()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert fake.load_calls  # the worker loaded the model
    assert item.pagebox.payload.text == "認識"
    assert item.pagebox.edited is False  # OCR-write path (D-04)


@pytest.mark.gui
def test_run_ocr_selected_emits_boxes_modified_with_before_state(qtbot, tmp_path, monkeypatch) -> None:
    """OCR finish pushes a BOXES snapshot whose payload is the PRE-OCR text
    (CR-01 before-state + Pitfall-8 detach), not the overwritten text."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.pagebox.set_recognized_text("旧")  # raw OCR text (edited=False)
    item.setSelected(True)
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: _FakeOCRModel("新"),
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)
    window.run_ocr_selected()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert item.pagebox.payload.text == "新"
    assert emitted, "OCR finish must emit boxes_modified (BOXES undo push)"
    before = emitted[0]
    assert len(before) == 1
    assert before[0].payload.text == "旧"  # undo restores the pre-OCR text


@pytest.mark.gui
def test_reocr_confirms_when_edited(qtbot, tmp_path, monkeypatch) -> None:
    """D-04 gate: an edited=True box + Cancel -> no OCR runs, text unchanged."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.pagebox.set_recognized_text_edited("手編集")  # edited=True
    item.setSelected(True)
    confirmed: list[bool] = []

    def _cancel() -> bool:
        confirmed.append(True)
        return False

    monkeypatch.setattr(window, "_confirm_reocr", _cancel)
    factory_calls: list[str] = []

    def _fake_factory(kind, backend):
        factory_calls.append(kind)
        return _FakeOCRModel()

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _fake_factory)
    window.run_ocr_selected()
    assert confirmed == [True]  # the D-04 dialog was shown
    assert factory_calls == []  # Cancel -> no worker, no model resolution
    assert window._op_running is False
    assert item.pagebox.payload.text == "手編集"  # untouched


@pytest.mark.gui
def test_reocr_silent_when_raw(qtbot, tmp_path, monkeypatch) -> None:
    """D-04 gate: an edited=False box is overwritten SILENTLY (no dialog)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.pagebox.set_recognized_text("raw")
    item.setSelected(True)

    def _must_not_confirm() -> bool:
        raise AssertionError("D-04 dialog must NOT fire for edited=False text")

    monkeypatch.setattr(window, "_confirm_reocr", _must_not_confirm)
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: _FakeOCRModel("新"),
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)
    window.run_ocr_selected()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert item.pagebox.payload.text == "新"
    assert item.pagebox.edited is False


@pytest.mark.gui
def test_run_ocr_selected_gated_when_op_running(qtbot, tmp_path, monkeypatch) -> None:
    """T-4-14: no second dispatch while another async op runs."""
    window = _window_with_page(qtbot, tmp_path)
    _add_user_box_window(window, Box(10, 10, 60, 60))
    window.canvas._box_items[0].setSelected(True)
    window._op_running = True

    def _must_not_factory(kind, backend):
        raise AssertionError("backend_factory must not be called while _op_running")

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _must_not_factory)
    window.run_ocr_selected()  # must be a no-op
    assert window._op_running is True  # untouched


@pytest.mark.gui
def test_run_ocr_selected_noop_without_selection(qtbot, tmp_path, monkeypatch) -> None:
    """Run OCR requires exactly one selected box (D-01)."""
    window = _window_with_page(qtbot, tmp_path)
    _add_user_box_window(window, Box(10, 10, 60, 60))  # exists but NOT selected

    def _must_not_factory(kind, backend):
        raise AssertionError("backend_factory must not be called without a selection")

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _must_not_factory)
    window.run_ocr_selected()
    assert window._op_running is False


@pytest.mark.gui
def test_run_ocr_selected_shows_loading_ocr_model_on_first_run(qtbot, tmp_path, monkeypatch) -> None:
    """Pitfall 6: an uncached model shows the 'Loading OCR model…' first-run
    UX (indeterminate progress) before the worker starts the ~450MB download."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.setSelected(True)
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: False)
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: _FakeOCRModel("x"),
    )
    window.run_ocr_selected()
    assert "Loading OCR model" in window.status_bar_left.text()
    assert window.progress_bar.maximum() == 0  # indeterminate range (0, 0)
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)


@pytest.mark.gui
def test_run_ocr_all_fills_empty_boxes(qtbot, tmp_path, monkeypatch) -> None:
    """D-03: OCR All fills every text-empty box; boxes that already carry
    text are untouched (one model load, sequential per-box)."""
    window = _window_with_page(qtbot, tmp_path)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes(
            [
                PageBox(box=Box(10, 10, 40, 40), origin=USER),
                PageBox(box=Box(50, 10, 90, 40), origin=USER),
                PageBox(box=Box(10, 50, 40, 90), origin=USER),
            ],
            [],
        )
    finally:
        window._suppress_boxes_push = False
    with_text, empty_a, empty_b = window.canvas._box_items
    with_text.pagebox.set_recognized_text("既存")
    fake = _FakeOCRModel("新テキスト")
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: fake,
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)
    window.run_ocr_all()
    assert window._op_running is True
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert fake.load_calls  # exactly one model load for the whole batch
    assert empty_a.pagebox.payload.text == "新テキスト"
    assert empty_b.pagebox.payload.text == "新テキスト"
    assert with_text.pagebox.payload.text == "既存"  # untouched (D-03 fill-only)
    assert "2 boxes recognized" in window.status_bar_left.text()


@pytest.mark.gui
def test_run_ocr_all_gate_confirms_when_edited_boxes_exist(qtbot, tmp_path, monkeypatch) -> None:
    """D-04 batch gate: edited boxes on the page -> confirm with the count;
    Cancel aborts the whole batch."""
    window = _window_with_page(qtbot, tmp_path)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes(
            [
                PageBox(box=Box(10, 10, 40, 40), origin=USER),
                PageBox(box=Box(50, 10, 90, 40), origin=USER),
            ],
            [],
        )
    finally:
        window._suppress_boxes_push = False
    edited_item, empty_item = window.canvas._box_items
    edited_item.pagebox.set_recognized_text_edited("手編集")
    counts: list[int] = []

    def _cancel(count: int) -> bool:
        counts.append(count)
        return False

    monkeypatch.setattr(window, "_confirm_reocr_all", _cancel)
    factory_calls: list[str] = []

    def _fake_factory(kind, backend):
        factory_calls.append(kind)
        return _FakeOCRModel()

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _fake_factory)
    window.run_ocr_all()
    assert counts == [1]  # the batch gate names the edited-box count
    assert factory_calls == []
    assert window._op_running is False
    assert empty_item.pagebox.payload is None  # nothing was filled


@pytest.mark.gui
def test_run_ocr_all_noop_when_no_empty_boxes(qtbot, tmp_path, monkeypatch) -> None:
    """D-03: a page whose every box already has text -> no dispatch."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.pagebox.set_recognized_text("already")

    def _must_not_factory(kind, backend):
        raise AssertionError("no dispatch expected when every box has text")

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _must_not_factory)
    window.run_ocr_all()
    assert window._op_running is False


@pytest.mark.gui
def test_run_ocr_all_gated_when_op_running(qtbot, tmp_path, monkeypatch) -> None:
    """T-4-14: OCR All is gated by _op_running like every other model op."""
    window = _window_with_page(qtbot, tmp_path)
    _add_user_box_window(window, Box(10, 10, 60, 60))
    window._op_running = True

    def _must_not_factory(kind, backend):
        raise AssertionError("backend_factory must not be called while _op_running")

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _must_not_factory)
    window.run_ocr_all()
    assert window._op_running is True


@pytest.mark.gui
def test_resolve_ocr_model_path_cache_checks(qtbot, tmp_path, monkeypatch) -> None:
    """T-4-13 (CR-11): _resolve_ocr_model_path consults is_ocr_downloaded
    before returning the HF cache dir (no re-download per session)."""
    window = _window_with_page(qtbot, tmp_path)
    checks: list[str] = []
    monkeypatch.setattr(
        "panelcleaner.model_downloader.get_ocr_model_directory",
        lambda: Path("C:/fake/hf/models--kha-white--manga-ocr-base"),
    )
    monkeypatch.setattr(
        "panelcleaner.model_downloader.is_ocr_downloaded",
        lambda: (checks.append("is_ocr_downloaded") or True),
    )
    resolved = window._resolve_ocr_model_path()
    assert resolved == Path("C:/fake/hf/models--kha-white--manga-ocr-base")
    assert checks == ["is_ocr_downloaded"]


@pytest.mark.gui
def test_run_ocr_selected_error_shows_chip_and_dialog(qtbot, tmp_path, monkeypatch) -> None:
    """_on_ocr_error: worker failure -> #7a1f1f chip + friendly dialog
    (T-01-08 mirror); _op_running clears via the always-fires cleanup."""
    from PySide6.QtWidgets import QMessageBox

    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    item.setSelected(True)

    class _BoomModel(_FakeOCRModel):
        def load(self, model_path, device="auto") -> None:
            raise RuntimeError("simulated model load failure")

    dialogs: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: dialogs.append(f"{title}|{text}"),
    )
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: _BoomModel(),
    )
    window.run_ocr_selected()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert window.error_chip.isVisible()
    assert window.error_chip.text() == "OCR model error"
    assert dialogs and dialogs[0].startswith("Couldn't load the OCR model.")


@pytest.mark.gui
def test_run_ocr_selected_real_model_end_to_end(qtbot, tmp_path) -> None:
    """INTEGRATION MARKER (skip-gated): with the manga-ocr HF cache populated,
    run the REAL model through the full dispatcher. CI forces no ~450MB
    download: skipped when is_ocr_downloaded() is False (04-03 convention)."""
    from panelcleaner.model_downloader import is_ocr_downloaded

    if not is_ocr_downloaded():
        pytest.skip("manga-ocr model not cached — no ~450MB download in CI")
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(20, 20, 100, 100))
    item.setSelected(True)
    window.run_ocr_selected()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=120000)
    assert isinstance(item.pagebox.payload.text, str)
    assert item.pagebox.edited is False


# ===========================================================================
# Plan 04-06 Task 2 — Text menu (Run OCR / OCR All Ctrl+R) + auto-OCR hook
# on canvas._commit_create (D-01) — TDD RED gate
# ===========================================================================


@pytest.mark.gui
def test_alt_drag_draw_release_emits_ocr_requested(qtbot) -> None:
    """D-01: Alt+drag draw-release emits ocr_requested with the new BoxItem
    (the MainWindow-subscribed auto-OCR seam)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    requested: list = []
    canvas.ocr_requested.connect(lambda item: requested.append(item))
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
    canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))
    assert canvas.box_count() == 1
    assert len(requested) == 1
    assert requested[0] is canvas._box_items[0]


@pytest.mark.gui
def test_alt_drag_too_small_emits_no_ocr_requested(qtbot) -> None:
    """UI-SPEC §14: a < 8x8 draw (Phase 3 no-op threshold) never triggers
    auto-OCR."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    requested: list = []
    canvas.ocr_requested.connect(lambda item: requested.append(item))
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 32, 32))  # 2x2 — below the 8x8 min
    canvas.mouseReleaseEvent(_release_at(canvas, 32, 32))
    assert canvas.box_count() == 0
    assert requested == []


@pytest.mark.gui
def test_text_menu_has_run_ocr_and_ocr_all_entries(qtbot, tmp_path) -> None:
    """UI-SPEC §Surface 1: the Text menu (between View and Tools) carries
    Run OCR + OCR All Boxes (Ctrl+R)."""
    window = _window_with_page(qtbot, tmp_path)
    # Hold strong references to the menubar actions: QAction wrappers from
    # actions() are temporary, and dropping the wrapper can take the child
    # QMenu's wrapper with it (PySide6 wrapper-lifetime).
    actions = window.menuBar().actions()
    menus = [a.text() for a in actions if a.menu() is not None]
    assert "&Text" in menus
    # Recommended order File / Edit / View / Text / Tools / Help.
    assert menus.index("&Text") == menus.index("&View") + 1
    assert menus.index("&Text") == menus.index("&Tools") - 1
    text_action = next(a for a in actions if a.text() == "&Text")
    text_menu = text_action.menu()
    texts = [a.text() for a in text_menu.actions()]
    assert "Run OCR" in texts
    assert "OCR All Boxes" in texts
    assert window.action_ocr_all.shortcut().toString() == "Ctrl+R"


@pytest.mark.gui
def test_action_run_ocr_enabled_only_with_selection(qtbot, tmp_path) -> None:
    """Run OCR is enabled iff exactly one box is selected AND no async op runs."""
    window = _window_with_page(qtbot, tmp_path)
    window._refresh_action_states()
    assert window.action_run_ocr.isEnabled() is False  # no boxes yet
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    window._refresh_action_states()
    assert window.action_run_ocr.isEnabled() is False  # box exists, not selected
    item.setSelected(True)
    window._refresh_action_states()
    assert window.action_run_ocr.isEnabled() is True
    window._op_running = True
    window._refresh_action_states()
    assert window.action_run_ocr.isEnabled() is False  # async-op gate


@pytest.mark.gui
def test_action_ocr_all_enabled_with_boxes(qtbot, tmp_path) -> None:
    """OCR All Boxes is enabled iff >= 1 box exists AND no async op runs."""
    window = _window_with_page(qtbot, tmp_path)
    window._refresh_action_states()
    assert window.action_ocr_all.isEnabled() is False  # no boxes
    _add_user_box_window(window, Box(10, 10, 60, 60))
    window._refresh_action_states()
    assert window.action_ocr_all.isEnabled() is True
    window._op_running = True
    window._refresh_action_states()
    assert window.action_ocr_all.isEnabled() is False


@pytest.mark.gui
def test_ctrl_r_shortcut_triggers_ocr_all(qtbot, tmp_path, monkeypatch) -> None:
    """UI-SPEC §Shortcuts: the OCR All action carries Ctrl+R and triggering
    it runs the real run_ocr_all dispatch (fills a text-empty box).

    Triggering the QAction is the same path Qt's shortcut system uses
    (action shortcuts emit ``triggered``); asserting the full dispatch (not
    an instance-monkeypatched method — signal connections capture the bound
    method at connect time) proves the wiring end-to-end."""
    window = _window_with_page(qtbot, tmp_path)
    _add_user_box_window(window, Box(10, 10, 60, 60))
    fake = _FakeOCRModel("新")
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: fake,
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)
    assert window.action_ocr_all.shortcut().toString() == "Ctrl+R"
    window._refresh_action_states()  # the action must be enabled to trigger
    assert window.action_ocr_all.isEnabled() is True
    window.action_ocr_all.trigger()
    assert window._op_running is True  # the action dispatched the worker
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert window.canvas._box_items[0].pagebox.payload.text == "新"


@pytest.mark.gui
def test_on_canvas_ocr_requested_dispatches_single_box_worker(qtbot, tmp_path, monkeypatch) -> None:
    """D-01 auto-OCR hook end-to-end: a real Alt+drag on the window's canvas
    emits ocr_requested -> MainWindow dispatches the worker -> the box
    arrives with recognized text (off the GUI thread, T-4-11)."""
    window = _window_with_page(qtbot, tmp_path)
    fake = _FakeOCRModel("自動")
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: fake,
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)
    canvas = window.canvas
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
    canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))
    assert canvas.box_count() == 1
    item = canvas._box_items[0]
    assert item.isSelected() is True
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert item.pagebox.payload.text == "自動"
    assert item.pagebox.edited is False


@pytest.mark.gui
def test_on_canvas_ocr_requested_skipped_when_op_running(qtbot, tmp_path, monkeypatch) -> None:
    """T-4-14: auto-OCR is silently skipped while another async op runs
    (no worker pileup on rapid draws)."""
    window = _window_with_page(qtbot, tmp_path)
    window._op_running = True
    factory_calls: list[str] = []

    def _fake_factory(kind, backend):
        factory_calls.append(kind)
        return _FakeOCRModel()

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _fake_factory)
    item = _add_user_box_window(window, Box(10, 10, 60, 60))
    window._on_canvas_ocr_requested(item)
    assert factory_calls == []
    assert window._op_running is True  # untouched


# ===========================================================================
# Plan 04-07 Task 1 — Load Translations dialog + apply (RED gate)
# ===========================================================================


@pytest.mark.gui
def test_load_translations_dialog_has_contracted_widgets(qtbot) -> None:
    """D-17/UI-SPEC §20: the dialog carries a page QComboBox (current page
    default), a mono QPlainTextEdit paste area with the contracted placeholder,
    a 'Load from File…' button, and [Cancel] [Apply]."""
    from PySide6.QtWidgets import QComboBox, QPlainTextEdit, QPushButton

    from manga_ai_studio.gui.load_translations_dialog import LoadTranslationsDialog

    dlg = LoadTranslationsDialog(
        parent=None, page_names=["page_a.png", "page_b.png"], current_page_index=1
    )
    qtbot.addWidget(dlg)
    assert isinstance(dlg.page_combo, QComboBox)
    assert dlg.page_combo.count() == 2
    assert dlg.page_combo.currentIndex() == 1  # current page default
    assert isinstance(dlg.paste_edit, QPlainTextEdit)
    assert "Paste your translation list here" in dlg.paste_edit.placeholderText()
    assert "[1]: first translated line" in dlg.paste_edit.placeholderText()
    assert isinstance(dlg.load_file_btn, QPushButton)
    assert dlg.load_file_btn.text() == "Load from File\u2026"
    assert isinstance(dlg.apply_btn, QPushButton)
    assert dlg.apply_btn.text() == "Apply"
    assert isinstance(dlg.cancel_btn, QPushButton)
    assert dlg.cancel_btn.text() == "Cancel"
    assert dlg.windowTitle() == "Load Translations"
    assert dlg.objectName() == "load_translations_dialog"
    # Mono font for the line-oriented paste format (UI-SPEC typography).
    assert dlg.paste_edit.font().family().lower() in ("consolas", "cascadia mono")


@pytest.mark.gui
def test_load_translations_dialog_apply_returns_text_and_page(qtbot) -> None:
    """RESEARCH §Pitfall 3 separation: the dialog only COLLECTS (text,
    page_index) via accept() — it never parses or mutates boxes."""
    from manga_ai_studio.gui.load_translations_dialog import LoadTranslationsDialog

    dlg = LoadTranslationsDialog(page_names=["a.png", "b.png"], current_page_index=0)
    qtbot.addWidget(dlg)
    dlg.paste_edit.setPlainText("[1]: hello\n[2]: world")
    dlg.page_combo.setCurrentIndex(1)
    dlg._on_apply()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_text() == "[1]: hello\n[2]: world"
    assert dlg.get_page_index() == 1


@pytest.mark.gui
def test_load_translations_dialog_load_file_populates_paste_area(qtbot, tmp_path, monkeypatch) -> None:
    """D-17 file front-end: a *.txt selected via QFileDialog loads into the
    paste area (UTF-8) so the user reviews before Apply."""
    from PySide6.QtWidgets import QFileDialog

    from manga_ai_studio.gui.load_translations_dialog import LoadTranslationsDialog

    dlg = LoadTranslationsDialog(page_names=["a.png"])
    qtbot.addWidget(dlg)
    f = tmp_path / "translations.txt"
    f.write_text("[1]: first\n[2]: second\n", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(f), "Text files (*.txt)")),
    )
    dlg._on_load_file()
    assert dlg.paste_edit.toPlainText() == "[1]: first\n[2]: second\n"


@pytest.mark.gui
def test_load_translations_dialog_load_file_error_dialog(qtbot, tmp_path, monkeypatch) -> None:
    """T-4-16/UI-SPEC §Copywriting: an unreadable/non-UTF-8 file shows the
    "Couldn't read '{filename}'." error dialog — no crash."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from manga_ai_studio.gui.load_translations_dialog import LoadTranslationsDialog

    dlg = LoadTranslationsDialog(page_names=["a.png"])
    qtbot.addWidget(dlg)
    f = tmp_path / "corrupt.txt"
    f.write_bytes(b"\xff\xfe\x00\x81garbage")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(f), "Text files (*.txt)")),
    )
    shown: list = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda parent, title, body: shown.append((title, body))),
    )
    dlg._on_load_file()
    assert shown, "the file-read error must surface a dialog"
    assert "Couldn't read 'corrupt.txt'." in shown[0][0]
    assert "The file may be corrupt or in an unsupported format." in shown[0][1]
    assert dlg.paste_edit.toPlainText() == ""  # nothing loaded


@pytest.mark.gui
def test_apply_translations_fills_set_translation_on_matched_boxes(qtbot, tmp_path, monkeypatch) -> None:
    """D-17: pasted "[1]: …\n[2]: …" + Apply fills set_translation on the
    bubble-1 and bubble-2 boxes (the D-13 MT seam)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 50, 60), Box(10, 80, 50, 120), Box(80, 20, 120, 60)]
    )
    items[0].pagebox.bubble_no = 1
    items[1].pagebox.bubble_no = 2
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    window._apply_translations("[1]: hello\n[2]: world", 0)
    assert items[0].pagebox.payload.translation == "hello"
    assert items[1].pagebox.payload.translation == "world"
    # Unmatched box untouched: no payload was ever created for it.
    assert items[2].pagebox.payload is None


@pytest.mark.gui
def test_apply_translations_shows_report_dialog(qtbot, tmp_path, monkeypatch) -> None:
    """D-15/D-17: after Apply the parser-result report shows the applied count."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(window, [Box(10, 20, 50, 60), Box(10, 80, 50, 120)])
    items[0].pagebox.bubble_no = 1
    items[1].pagebox.bubble_no = 2
    reports: list = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda parent, title, body: reports.append((title, body))),
    )
    window._apply_translations("[1]: first\n[2]: second", 0)
    assert reports, "the parser-result report must show on Apply"
    assert reports[0][0] == "Load Translations"
    assert "Applied 2 translation(s) to page 1." in reports[0][1]


@pytest.mark.gui
def test_apply_translations_reports_unmatched_and_skipped(qtbot, tmp_path, monkeypatch) -> None:
    """UI-SPEC §Copywriting: unmatched bubble numbers + unparseable/SFX lines
    are reported in ONE skipped total — no per-line modal, no crash (ASVS V5)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(window, [Box(10, 20, 50, 60)])
    items[0].pagebox.bubble_no = 1
    reports: list = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda parent, title, body: reports.append((title, body))),
    )
    # [99] unmatched bubble + [SFX -3] recognized-but-skipped = 2 skipped lines.
    window._apply_translations("[1]: ok\n[99]: no match\n[SFX -3]: *boom*", 0)
    assert reports, "the parser-result report must show on Apply"
    assert "Applied 1 translation(s) to page 1." in reports[0][1]
    assert "2 line(s) did not match a bubble number and were skipped." in reports[0][1]


@pytest.mark.gui
def test_apply_translations_no_matches_copy(qtbot, tmp_path, monkeypatch) -> None:
    """UI-SPEC §Copywriting: zero applied -> the no-matches path copy."""
    window = _window_with_page(qtbot, tmp_path)
    _seed_boxes_window(window, [Box(10, 20, 50, 60)])  # no bubble numbers
    reports: list = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda parent, title, body: reports.append((title, body))),
    )
    window._apply_translations("[42]: nothing matches", 0)
    assert reports
    assert "No lines matched any bubble number on page 1." in reports[0][1]
    assert "Text \u2192 Auto-Number" in reports[0][1]


@pytest.mark.gui
def test_apply_translations_never_visited_page_no_crash(qtbot, tmp_path, monkeypatch) -> None:
    """WR-04: Load Translations onto a never-visited page (ImageFile.boxes is
    None until on_page_selected populates it) must show the clean no-match
    report, not crash into the spurious error dialog ('NoneType' not iterable)."""
    from PIL import Image as PILImage

    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    PILImage.new("RGB", (120, 120), color=(200, 200, 200)).save(page_a)
    PILImage.new("RGB", (120, 120), color=(180, 180, 180)).save(page_b)
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    # Load the two-page folder: page 1 (index 0) auto-selects; page 2's
    # ImageFile.boxes stays None (the WR-04 crash precondition).
    window._load_folder(tmp_path)
    assert len(window.image_files) == 2
    assert window._current_page_index() == 0
    assert window.image_files[1].boxes is None

    reports: list = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda parent, title, body: reports.append((title, body))),
    )
    crashed: list = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *a: crashed.append(a)),
    )
    window._apply_translations("[1]: hola", 1)  # target page 2 (index 1)
    assert crashed == [], "a never-visited target page must not hit the error dialog"
    assert reports, "the no-match report must be shown instead of the error dialog"
    assert "No lines matched any bubble number on page 2." in reports[0][1]


@pytest.mark.gui
def test_apply_translations_emits_one_boxes_modified(qtbot, tmp_path, monkeypatch) -> None:
    """UI-SPEC §20: the batch apply pushes ONE BOXES snapshot (batch undo
    entry) whose payloads carry the PRE-apply translation state."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window,
        [Box(10, 20, 50, 60), Box(10, 80, 50, 120), Box(80, 20, 120, 60)],
    )
    for i, it in enumerate(items, start=1):
        it.pagebox.bubble_no = i
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    window._apply_translations("[1]: a\n[2]: b\n[3]: c", 0)
    assert len(emitted) == 1, "the batch apply must push exactly ONE BOXES entry"
    # Before-state: no translation was written to the snapshot payloads.
    assert all(pb.payload is None for pb in emitted[0])
    assert all(it.pagebox.payload.translation is not None for it in items)


@pytest.mark.gui
def test_action_load_translations_enabled_with_page(qtbot, tmp_path) -> None:
    """Text -> Load Translations… is enabled iff a page is open AND no async
    op is running (refresh in _refresh_action_states)."""
    window = _window_with_page(qtbot, tmp_path)
    window._refresh_action_states()
    assert window.action_load_translations.isEnabled() is True  # page open
    window._op_running = True
    window._refresh_action_states()
    assert window.action_load_translations.isEnabled() is False


@pytest.mark.gui
def test_text_menu_has_load_translations_entry(qtbot, tmp_path) -> None:
    """UI-SPEC §Surface 1: the Text menu carries 'Load Translations…'."""
    window = _window_with_page(qtbot, tmp_path)
    actions = window.menuBar().actions()
    text_action = next(a for a in actions if a.text() == "&Text")
    text_menu = text_action.menu()
    texts = [a.text() for a in text_menu.actions()]
    assert "Load Translations\u2026" in texts
    assert window.action_load_translations.text() == "Load Translations\u2026"


# ===========================================================================
# Plan 04-07 Task 2 — Auto-Number RTL/LTR + preserve-manual (RED gate)
# ===========================================================================


@pytest.mark.gui
def test_auto_number_rtl_assigns_right_to_left(qtbot, tmp_path) -> None:
    """D-15/D-16: Auto-Number RTL (Manga) assigns 1..N right-to-left,
    top-to-bottom (XY-Cut column order — rightmost column first)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window,
        [
            Box(10, 20, 50, 60),  # left column, top (cx 30)
            Box(10, 80, 50, 120),  # left column, bottom (cx 30)
            Box(80, 20, 120, 60),  # right column, top (cx 100)
            Box(80, 80, 120, 120),  # right column, bottom (cx 100)
        ],
    )
    window._auto_number(rtl=True)
    nums = [it.pagebox.bubble_no for it in items]
    # Right column (cx 100) first: top->bottom 1, 2; then left column 3, 4.
    assert nums == [3, 4, 1, 2]


@pytest.mark.gui
def test_auto_number_ltr_assigns_left_to_right(qtbot, tmp_path) -> None:
    """D-15/D-16: Auto-Number LTR (Manhwa) assigns 1..N left-to-right,
    top-to-bottom (leftmost column first)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window,
        [
            Box(10, 20, 50, 60),  # left column, top (cx 30)
            Box(10, 80, 50, 120),  # left column, bottom (cx 30)
            Box(80, 20, 120, 60),  # right column, top (cx 100)
            Box(80, 80, 120, 120),  # right column, bottom (cx 100)
        ],
    )
    window._auto_number(rtl=False)
    nums = [it.pagebox.bubble_no for it in items]
    assert nums == [1, 2, 3, 4]


@pytest.mark.gui
def test_auto_number_preserves_manual_override(qtbot, tmp_path) -> None:
    """D-16 preserve-manual conflict policy: a manual_override box KEEPS its
    bubble_no across re-auto (amber override flag intact); the auto sequence
    leaves a gap where the manual number collides (T-4-17)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window,
        [
            Box(10, 20, 50, 60),  # left column, top (cx 30)
            Box(10, 80, 50, 120),  # left column, bottom (cx 30)
            Box(80, 20, 120, 60),  # right column, top (cx 100)
        ],
    )
    items[2].pagebox.bubble_no = 5
    items[2].pagebox.manual_override = True
    window._auto_number(rtl=True)
    # RTL: right column first — the manual box is skipped, then left column
    # gets 1, 2 (the sequence leaves the gap at 5).
    assert items[0].pagebox.bubble_no == 1
    assert items[1].pagebox.bubble_no == 2
    assert items[2].pagebox.bubble_no == 5  # preserved, not renumbered
    assert items[2].pagebox.manual_override is True  # flag intact
    assert items[0].pagebox.manual_override is False  # auto boxes stay auto


@pytest.mark.gui
def test_auto_number_emits_one_boxes_modified(qtbot, tmp_path) -> None:
    """UI-SPEC §20: the page-level auto-number pushes ONE batch BOXES entry
    whose snapshot carries the PRE-numbering bubble state."""
    window = _window_with_page(qtbot, tmp_path)
    _seed_boxes_window(
        window,
        [
            Box(10, 20, 50, 60),
            Box(10, 80, 50, 120),
            Box(80, 20, 120, 60),
            Box(80, 80, 120, 120),
        ],
    )
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    window._auto_number(rtl=True)
    assert len(emitted) == 1, "the batch auto-number must push exactly ONE entry"
    # Before-state: no bubble numbers assigned in the snapshot.
    assert all(pb.bubble_no is None for pb in emitted[0])


@pytest.mark.gui
def test_auto_number_empty_page_noop(qtbot, tmp_path) -> None:
    """An empty page (no boxes) is a no-op: no emit, no status change."""
    window = _window_with_page(qtbot, tmp_path)
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    window._auto_number(rtl=True)
    assert emitted == []
    assert window.status_bar_left.text() == "No page open" or "boxes" not in window.status_bar_left.text()


@pytest.mark.gui
def test_auto_number_refreshes_badges(qtbot, tmp_path) -> None:
    """After auto-number every BoxItem badge shows its new number (D-15)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 50, 60), Box(10, 80, 50, 120)]
    )
    window._auto_number(rtl=True)
    assert items[0]._badge_digit.toPlainText() == "1"
    assert items[1]._badge_digit.toPlainText() == "2"
    assert items[0]._badge.isVisible()
    assert items[1]._badge.isVisible()


@pytest.mark.gui
def test_auto_number_shows_status_transient(qtbot, tmp_path) -> None:
    """UI-SPEC §Copywriting: 'Numbered {n} boxes (RTL/TB).' / '(LTR/TB).'."""
    window = _window_with_page(qtbot, tmp_path)
    _seed_boxes_window(
        window, [Box(10, 20, 50, 60), Box(10, 80, 50, 120)]
    )
    window._auto_number(rtl=True)
    assert window.status_bar_left.text() == "Numbered 2 boxes (RTL/TB)."
    window._auto_number(rtl=False)
    assert window.status_bar_left.text() == "Numbered 2 boxes (LTR/TB)."


@pytest.mark.gui
def test_action_auto_number_enabled_only_with_boxes(qtbot, tmp_path) -> None:
    """Auto-Number RTL/LTR are enabled iff >= 1 box AND no async op runs."""
    window = _window_with_page(qtbot, tmp_path)
    window._refresh_action_states()
    assert window.action_auto_number_rtl.isEnabled() is False  # no boxes
    assert window.action_auto_number_ltr.isEnabled() is False
    _add_user_box_window(window, Box(10, 10, 60, 60))
    window._refresh_action_states()
    assert window.action_auto_number_rtl.isEnabled() is True
    assert window.action_auto_number_ltr.isEnabled() is True
    window._op_running = True
    window._refresh_action_states()
    assert window.action_auto_number_rtl.isEnabled() is False
    assert window.action_auto_number_ltr.isEnabled() is False


@pytest.mark.gui
def test_text_menu_has_auto_number_submenu(qtbot, tmp_path) -> None:
    """UI-SPEC §Surface 1: Text -> Auto-Number -> RTL (Manga) / LTR (Manhwa)
    submenu sits between the OCR actions and Load Translations…."""
    window = _window_with_page(qtbot, tmp_path)
    actions = window.menuBar().actions()
    text_action = next(a for a in actions if a.text() == "&Text")
    text_menu = text_action.menu()
    texts = [a.text() for a in text_menu.actions()]
    assert "Auto-Number" in texts
    assert "Load Translations\u2026" in texts
    # Auto-Number comes before Load Translations… in the menu.
    assert texts.index("Auto-Number") < texts.index("Load Translations\u2026")
    auto_action = next(a for a in text_menu.actions() if a.text() == "Auto-Number")
    auto_menu = auto_action.menu()
    sub = [a.text() for a in auto_menu.actions()]
    assert "RTL (Manga)" in sub
    assert "LTR (Manhwa)" in sub

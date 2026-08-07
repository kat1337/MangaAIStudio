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
    QGraphicsScene,
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

    The 03-07 executor's probe passed because it simulated the move via
    ``setRect`` (updates ``rect()``); the live app moves through Qt's
    ``ItemIsMovable`` (updates ``pos()``), which diverges from ``rect()`` — so
    ``boxes_snapshot()`` materializes the stale rect and the persisted boxes
    carry the original position. This test drives the move through REAL Qt
    events (the closest offscreen approximation to the live path), then drives
    the real ``on_page_selected`` round-trip, and asserts the restored box is
    at the MOVED position, not the original.
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

    # Drive a real body-drag move (50,50) -> (100,100): box lands at (70,70)-(130,130).
    _drive_real_body_move(qtbot, window.canvas, item, (50.0, 50.0), (100.0, 100.0))
    moved_now = item.current_box().as_tuple
    assert moved_now == (70, 70, 130, 130), (
        f"precondition: the real-event move must land the box at (70,70,130,130); "
        f"got {moved_now} (if this is the original (20,20,80,80) the move went "
        f"through pos() — the UAT re-test 4 defect)."
    )

    # Round-trip A -> B -> A through the REAL on_page_selected seam.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    assert not window.canvas.has_boxes()
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)

    restored = window.canvas.boxes_snapshot()
    assert len(restored) == 1, f"the box must survive the round-trip; got {len(restored)}"
    assert restored[0].box.as_tuple == (70, 70, 130, 130), (
        "UAT re-test 4: the MOVED position (70,70,130,130) must persist across "
        f"the round-trip; got {restored[0].box.as_tuple}. If this is the ORIGINAL "
        "(20,20,80,80), the move was visible on screen (pos+rect) but the snapshot "
        "materialized the stale rect() — the ItemIsMovable root cause."
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
    """The Bubble # QSpinBox is bounded (1..9999) per T-4-08 tampering mitigation."""
    panel = _make_inspector(qtbot)
    assert panel.bubble_spin.minimum() == 1
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
    menus = [a.text() for a in window.menuBar().actions() if a.menu() is not None]
    assert "&Text" in menus
    # Recommended order File / Edit / View / Text / Tools / Help.
    assert menus.index("&Text") == menus.index("&View") + 1
    assert menus.index("&Text") == menus.index("&Tools") - 1
    text_menu = next(
        a.menu() for a in window.menuBar().actions() if a.text() == "&Text"
    )
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
    """UI-SPEC §Shortcuts: Ctrl+R fires run_ocr_all."""
    window = _window_with_page(qtbot, tmp_path)
    called: list[str] = []
    monkeypatch.setattr(window, "run_ocr_all", lambda: called.append("run_ocr_all"))
    assert window.action_ocr_all.shortcut().toString() == "Ctrl+R"
    window.action_ocr_all.trigger()
    assert called == ["run_ocr_all"]


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

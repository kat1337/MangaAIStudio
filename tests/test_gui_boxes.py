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
from PySide6.QtGui import QColor, QImage, QMouseEvent, QTransform  # noqa: E402
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

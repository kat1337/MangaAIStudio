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

import weakref
from pathlib import Path  # noqa: F401  (mirrors test_gui_canvas header)

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QPoint, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFontInfo,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QGraphicsScene,
    QMessageBox,
)

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.core.mask_editor import ToolMode  # noqa: E402
from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.box_item import BoxItem, CornerHandle  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.inline_editor import InlineEditor  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from manga_ai_studio.gui.text_renderer import layout  # noqa: E402


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
    canvas: EditorCanvas,
    sx: float,
    sy: float,
    *,
    alt: bool = False,
    ctrl: bool = False,
) -> QMouseEvent:
    """Build a left-button mouse-press whose viewport coords map to scene (sx, sy).

    quick-260907-m4u: ``ctrl`` ORs ControlModifier in (mirroring the ``alt``
    param) so the Ctrl+click copy dispatch is drivable; existing call sites
    are unchanged (both default False).
    """
    vp = canvas.mapFromScene(QPointF(sx, sy))
    mods = Qt.KeyboardModifier.NoModifier
    if alt:
        mods |= Qt.KeyboardModifier.AltModifier
    if ctrl:
        mods |= Qt.KeyboardModifier.ControlModifier
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
# quick-260824-t64 Task 2 — constant screen-size corner grab zones
# ===========================================================================
# The canvas hit-test queries items(scene_pos, ..., QTransform()) with an
# IDENTITY transform, so the old fixed 18-unit hit rect was 18 SCENE px — only
# ~4.5 screen px at 25% zoom ("handles hard to grab when zoomed out"). The fix
# divides the hit rect by the live zoom so the zone stays ~18 VIEWPORT px at
# any zoom, uniform across all four corners (probe found NO code-level BL
# asymmetry — the badge/affordance sit TL/TR-OUTSIDE by design).


@pytest.mark.gui
@pytest.mark.parametrize("zoom", [0.25, 1.0, 4.0])
@pytest.mark.parametrize("corner", ["TL", "TR", "BL", "BR"])
def test_corner_handle_hit_zone_constant_in_viewport_px(qtbot, corner, zoom) -> None:
    """Every corner's effective viewport-px hit-zone width is ~_HANDLE_HIT_SIZE
    at any zoom — including explicit bottom-left cases (the reported pain)."""
    from manga_ai_studio.gui.box_item import _HANDLE_HIT_SIZE

    scene, item = _scene_with_box(PageBox(box=Box(100, 100, 300, 300), origin=DETECTED))
    scene.clearSelection()
    item.setSelected(True)
    # Propagation seam: apply_overlay_zoom forwards to every handle.
    item.apply_overlay_zoom(zoom)

    handle = item.handles[corner]
    assert handle._hit_zoom == zoom

    # The zoom-divided rect: width * zoom ≈ 18 viewport px (+-1 rounding).
    hit_rect = handle.boundingRect()
    assert hit_rect.width() * zoom == pytest.approx(_HANDLE_HIT_SIZE, abs=1.0)
    assert hit_rect.height() * zoom == pytest.approx(_HANDLE_HIT_SIZE, abs=1.0)

    # shape() and boundingRect() MUST stay identical (03-06 lesson: boundingRect
    # gates the coarse BSP pass).
    assert handle.shape().boundingRect() == hit_rect

    # The VISIBLE painted handle stays 8x8 (UI-SPEC §12b).
    assert int(handle.rect().width()) == 8 and int(handle.rect().height()) == 8

    # BL sanity probe at low zoom: a point inside the widened zone around the
    # BL corner hits the handle via the real scene.itemAt identity path. The
    # probe anchors on the handle's TRUE corner — local (4/zoom, 4/zoom) since
    # quick-260909-fa9 divides the reposition offset AND the hit-rect centre
    # by the zoom (mapToScene is a pure translation by pos here) — not
    # sceneBoundingRect(), whose pen-width inflation would push the probe
    # outside the zone.
    if corner == "BL":
        corner_pt = handle.mapToScene(QPointF(4.0 / zoom, 4.0 / zoom))
        half = (_HANDLE_HIT_SIZE / zoom) / 2.0
        probe = corner_pt + QPointF(half - 1, half - 1)
        hit = scene.itemAt(probe, QTransform())
        assert isinstance(hit, CornerHandle)


@pytest.mark.gui
def test_corner_handle_set_hit_zoom_guards_and_bsp_refresh(qtbot) -> None:
    """set_hit_zoom guards non-positive to 1.0 and no-ops on an unchanged value."""
    _scene, item = _scene_with_box(PageBox(box=Box(100, 100, 300, 300), origin=DETECTED))
    handle = item.handles["TL"]
    handle.set_hit_zoom(0.25)
    assert handle._hit_zoom == 0.25
    handle.set_hit_zoom(-3)  # non-positive -> guarded to 1.0
    assert handle._hit_zoom == 1.0
    handle.set_hit_zoom(0)  # ditto
    assert handle._hit_zoom == 1.0
    handle.set_hit_zoom(2.0)
    assert handle._hit_zoom == 2.0


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
# outlined text overlay child (z=120) showing the current-focus text (translation
# when present, else recognized — D-10) and a bubble-number badge (z=140,
# ItemIgnoresTransformations, constant viewport-px). Phase 7 (D-01, plan 07-01
# Task 2) REPLACES the translucent QGraphicsTextItem overlay (UI-SPEC surface
# 34 supersedes surface 16) with the renderer-driven OPAQUE TypesetOverlayItem:
# the same gui/text_renderer layout+paint functions the bake uses (canvas ≡
# bake), the flat per-box TextStyle (defaults when the box has none), and the
# [10,28]-clamped box-adaptive Auto-fit base at SCENE px (D-15). The T toggle
# (D-12), box-visibility inheritance, and the setPos-only reposition (RC-1)
# contracts are unchanged. set_text_overlay_visible(False) is the independent
# visibility layer the Toggle Text Overlay action (T, D-12) drives — independent
# of the box-layer toggle (Shift+M) and the mask toggle (M).

# Module constants the implementation must add (UI-SPEC §Z-order). Importing
# them by name proves they exist; the import fails before Task 2 GREEN.
from manga_ai_studio.gui.box_item import (  # noqa: E402
    _BADGE_Z,
    _TEXT_OVERLAY_Z,
    TypesetOverlayItem,
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
    """A BoxItem carries a renderer-driven TypesetOverlayItem child (z=120)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    # refresh_text_overlay is what shows it; a fresh box with text should show it.
    item.refresh_text_overlay()
    assert hasattr(item, "_text_overlay")
    assert isinstance(item._text_overlay, TypesetOverlayItem)
    assert item._text_overlay.zValue() == 120


@pytest.mark.gui
def test_text_overlay_shows_recognized_when_no_translation(qtbot) -> None:
    """A box with recognized text 'hello' and no translation renders 'hello' (D-10)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is True
    assert item._text_overlay.text() == "hello"


@pytest.mark.gui
def test_text_overlay_current_focus_rule_translation_wins(qtbot) -> None:
    """The same box with translation 'hola' renders 'hola' (D-10 current-focus: translation wins)."""
    pb = _pagebox_with_text(recognized="hello", translation="hola")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.text() == "hola"


@pytest.mark.gui
def test_text_overlay_hidden_when_no_recognized_text(qtbot) -> None:
    """A box with no recognized text renders no text child (overlay hidden)."""
    pb = PageBox(box=Box(20, 20, 100, 80), origin=DETECTED)  # payload=None
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is False


@pytest.mark.gui
def test_text_overlay_renders_literal_plain_text(qtbot) -> None:
    """The overlay carries the LITERAL string — plain-text rendering only
    (ASVS V5 — the shared renderer never rich-texts OCR/translation content)."""
    pb = _pagebox_with_text(recognized="<script>alert(1)</script>")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    # The rendered current-focus text echoes the literal string (no HTML parse).
    assert item._text_overlay.text() == "<script>alert(1)</script>"
    assert item._text_overlay.isVisible() is True


@pytest.mark.gui
def test_text_overlay_renders_through_shared_renderer(qtbot) -> None:
    """The overlay renders through the SHARED renderer (layout + pixmap cache)
    with the flat per-box TextStyle (default: black fill, outline disabled —
    quick task 260822-347)."""
    from manga_ai_studio.core.text_style import TextStyle

    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    # The renderer ran: a layout result + a cached pixmap exist.
    assert item._text_overlay.layout_result is not None
    assert item._text_overlay.layout_result.text == "hello"
    assert item._text_overlay.pixmap() is not None
    # The flat style defaults: black fill; the 2px stroke width is retained
    # as the enable-time default but the outline ships DISABLED.
    assert TextStyle().outline["width_px"] == 2.0
    assert TextStyle().outline["enabled"] is False


@pytest.mark.gui
def test_text_overlay_pixmap_matches_bake_at_scene_position(qtbot) -> None:
    """CR-01 (D-01): the overlay pixmap rendered at its scene position shows
    the SAME glyphs the bake paints for a box at a NON-ZERO position.

    ``set_content`` must cancel ``renderer.paint``'s ``origin`` translate (net
    zero), or the ink lands outside a pixmap sized to the ink rect — a fully
    blank overlay (empirically: alpha max 0 for a box at (40,30)). This
    asserts PIXMAP CONTENT, not bounding-rect deltas, so the regression
    cannot recur silently.
    """
    import numpy as np

    from PySide6.QtGui import QPainter

    from manga_ai_studio.core.text_style import TextStyle
    from manga_ai_studio.gui.text_renderer import (
        bake_typeset_page,
        numpy_to_qimage,
        qimage_to_numpy,
    )

    # Deterministic fixed-size style (left/top, outline+effects off) so the
    # fill pixels are observable — mirrors tests/test_core/test_typeset_bake.
    style = TextStyle(
        font_size_px=12.0,
        auto_fit=False,
        align_h="left",
        align_v="top",
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 2.0},
    )
    page = np.full((200, 300, 3), (30, 40, 50), dtype=np.uint8)
    # A NON-ZERO box position — the CR-01 trigger (a (0,0) box only clipped a
    # sliver and passed the old bounding-rect-delta tests).
    pb = PageBox(box=Box(40, 30, 140, 90), origin=DETECTED, style=style)
    pb.set_translation("Hello")

    baked = bake_typeset_page(page, [pb])

    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay = item._text_overlay
    assert overlay.pixmap() is not None
    # The pixmap itself must carry ink (the old double-counted origin left it
    # fully transparent).
    pm = overlay.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    alpha = np.frombuffer(bytes(pm.bits()), dtype=np.uint8).reshape(
        pm.height(), pm.width(), 4
    )[..., 3]
    assert alpha.max() > 0, (
        "the overlay pixmap must contain ink — the origin double-count "
        "clipped it outside the pixmap (CR-01)"
    )
    # The ink must fill a substantial part of the pixmap (the pixmap is sized
    # to the ink rect, so the glyphs are most of it — a displaced/clipped
    # sliver would not).
    assert (alpha > 0).mean() > 0.1, (
        "the overlay pixmap must be mostly glyph ink, not a clipped sliver"
    )

    # Composite the pixmap at its scene position (the BoxItem sits at scene
    # (0,0), so overlay.pos() IS the scene position) and compare against the
    # bake — D-01 canvas ≡ bake. The comparison is EXACT on the OPAQUE glyph
    # interior (no blending / antialias-phase differences there); the
    # translucent edge pixels are excluded because the premultiplied pixmap
    # cache and the direct page paint can rasterize coverage with a different
    # sub-pixel phase by design.
    qimg = numpy_to_qimage(page).copy()
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(overlay.pos(), overlay.pixmap())
    painter.end()
    canvas_arr = qimage_to_numpy(qimg)

    pos = overlay.pos()
    pi, pj = int(round(pos.x())), int(round(pos.y()))
    opaque = alpha == 255
    assert opaque.any(), "the glyph interior must be opaque (D-01)"
    oy, ox = np.nonzero(opaque)
    assert np.array_equal(
        canvas_arr[oy + pj, ox + pi], baked[oy + pj, ox + pi]
    ), (
        "opaque glyph pixels composited at the scene position must match the "
        "bake exactly (D-01 — canvas ≡ bake; a re-broken origin offset "
        "displaces the ink)"
    )


# -- Plan 07-08 (G-07-5): align_v applies to horizontal text on the canvas --
# The renderer computes the align_v dy correctly (layout() rides it on
# result.origin.y), but TypesetOverlayItem.set_content CANCELS result.origin in
# full and re-derives _ink_offset from the doc-local ink rect — the dy is
# dropped on canvas (the bake keeps it -> canvas != bake for align_v != top).
# The fix adds the box-relative origin delta back into _ink_offset.y
# (dy = origin.y - box.y - inset); the vertical path's origin carries no dy so
# the term is exactly 0 there. All existing equivalence tests used align_v="top"
# (dy = 0) — the blind spot these tests close. Manual sizes (font_size_px set,
# auto_fit False) keep the geometry independent of the plan 07-10 grow-to-fit
# change.


def _overlay_align_v_pixel_equals_bake(
    align_v: str, align_h: str = "left"
) -> tuple[bool, str]:
    """Composite the overlay pixmap at its scene position onto a page QImage
    and compare the OPAQUE glyph pixels against ``bake_typeset_page``.

    Returns ``(ok, reason)`` — the D-01 canvas≡bake check at the OVERLAY level
    (the renderer-level twin test_canvas_style_paint_equals_bake_pixels never
    instantiates the overlay, so it cannot catch the set_content dy drop).
    """
    import numpy as np

    from PySide6.QtGui import QPainter

    from manga_ai_studio.core.text_style import TextStyle
    from manga_ai_studio.gui.text_renderer import (
        bake_typeset_page,
        numpy_to_qimage,
        qimage_to_numpy,
    )

    style = TextStyle(
        font_size_px=14.0,
        auto_fit=False,
        align_h=align_h,
        align_v=align_v,
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 2.0},
    )
    page = np.full((200, 300, 3), (30, 40, 50), dtype=np.uint8)
    pb = PageBox(box=Box(40, 30, 140, 90), origin=DETECTED, style=style)
    pb.set_translation("Hello")

    baked = bake_typeset_page(page, [pb])

    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay = item._text_overlay
    assert overlay.pixmap() is not None
    pm = overlay.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    alpha = np.frombuffer(bytes(pm.bits()), dtype=np.uint8).reshape(
        pm.height(), pm.width(), 4
    )[..., 3]

    qimg = numpy_to_qimage(page).copy()
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(overlay.pos(), overlay.pixmap())
    painter.end()
    canvas_arr = qimage_to_numpy(qimg)

    pos = overlay.pos()
    pi, pj = int(round(pos.x())), int(round(pos.y()))
    opaque = alpha == 255
    if not opaque.any():
        return False, "the overlay pixmap must carry opaque glyph interior pixels"
    oy, ox = np.nonzero(opaque)
    if not np.array_equal(canvas_arr[oy + pj, ox + pi], baked[oy + pj, ox + pi]):
        return (
            False,
            "opaque overlay pixels composited at the scene position differ "
            "from the bake — the align_v dy was dropped by set_content "
            "(G-07-5: canvas shows top-aligned, bake paints "
            f"{align_v}-aligned)",
        )
    return True, ""


@pytest.mark.gui
def test_overlay_align_v_preserves_dy(qtbot) -> None:
    """G-07-5 unit contract: ``_ink_offset.y()`` carries the layout's own
    align_v origin delta.

    ``bottom`` -> ``_ink_offset.y() == ink.top() - pad + dy`` with
    ``dy = origin.y - box.y - inset > 0``; ``top`` -> ``dy == 0`` (the
    historical, blind-spot case); the vertical (tategaki) path -> the layout
    origin carries NO dy, so the term is exactly 0 (no behavior change).
    RED before the fix: the bottom/middle cases equal the top-case value (the
    dy is dropped by set_content's origin-cancel).

    quick-260826-09m: ``_ink_offset`` now derives from the MEASURED painted
    bounding box, so it differs from the legacy analytic formula by a
    per-layout glyph-delta constant. That delta depends only on the laid-out
    glyphs (NOT on align_v — the scratch mapping cancels ``origin``), so the
    dy contract is asserted RELATIVE to the same-mode dy==0 reference:
    ``offset(case) - offset(reference) == dy(case)`` exactly.
    """
    from manga_ai_studio.core.text_style import TextStyle
    from manga_ai_studio.gui.text_renderer import (
        _OVERLAY_INSET,
        effect_padding,
        layout as renderer_layout,
    )

    cases = [
        # (align_v, vertical, expect_dy_zero)
        ("bottom", False, False),
        ("middle", False, False),
        ("top", False, True),
        ("bottom", True, True),  # vertical origin carries no dy
    ]
    # Same-mode dy==0 reference offsets (the measured glyph-delta baseline).
    ref_offset: dict[bool, float] = {}
    rendered: list[tuple[str, bool, bool, float, float]] = []
    for align_v, vertical, expect_dy_zero in cases:
        style = TextStyle(
            font_size_px=14.0,
            auto_fit=False,
            align_h="left",
            align_v=align_v,
            vertical=vertical,
            outline={"enabled": False, "color": "#0b0b0e", "width_px": 2.0},
        )
        pb = PageBox(box=Box(40, 30, 140, 90), origin=DETECTED, style=style)
        pb.set_translation("Hello")
        _scene, item = _scene_with_box(pb)
        item.refresh_text_overlay()
        overlay = item._text_overlay

        # The reference: the layout's OWN origin delta (the renderer contract
        # the overlay must preserve through the origin-cancel).
        result = renderer_layout("Hello", style, item.rect(), vertical=vertical)
        pad = effect_padding(style)
        dy = result.origin.y() - item.rect().y() - _OVERLAY_INSET

        assert dy == pytest.approx(0.0, abs=1e-6) if expect_dy_zero else dy > 0.0, (
            f"precondition: align_v={align_v!r} vertical={vertical} must yield "
            f"dy={dy} ({'zero — the blind-spot case' if expect_dy_zero else 'non-zero — the G-07-5 case'})"
        )
        rendered.append(
            (align_v, vertical, expect_dy_zero, dy, overlay._ink_offset.y())
        )
        if expect_dy_zero:
            ref_offset[vertical] = overlay._ink_offset.y()
    for align_v, vertical, expect_dy_zero, dy, offset_y in rendered:
        if expect_dy_zero:
            continue
        ref = ref_offset[False]
        assert (
            offset_y - ref == pytest.approx(dy, abs=1e-6)
        ), (
            f"align_v={align_v!r}: _ink_offset.y() must carry the layout "
            f"dy ({dy}) above the dy==0 reference ({ref}); got "
            f"{offset_y} — set_content's origin-cancel dropped "
            "the align_v dy (G-07-5)"
        )


@pytest.mark.gui
def test_overlay_align_v_bottom_and_middle_equals_bake_pixels(qtbot) -> None:
    """G-07-5 pixel contract (D-01): for align_v=bottom AND middle the overlay
    composited at its scene position matches the bake in the ink region.

    The historical equivalence tests all used align_v="top" (dy=0) — the blind
    spot that let the set_content dy drop through. RED before the fix: the
    overlay ink sits at the box top while the bake paints bottom/middle.
    """
    ok, reason = _overlay_align_v_pixel_equals_bake("bottom")
    assert ok, f"align_v=bottom: {reason}"
    ok, reason = _overlay_align_v_pixel_equals_bake("middle")
    assert ok, f"align_v=middle: {reason}"


@pytest.mark.gui
@pytest.mark.parametrize(
    "align_h,align_v",
    [
        (h, v)
        for v in ("top", "middle", "bottom")
        for h in ("left", "center", "right")
    ],
)
def test_overlay_align_v_matrix_equals_bake(qtbot, align_h, align_v) -> None:
    """The full 3x3 align_v x align_h equivalence matrix at the OVERLAY level.

    Pins canvas ≡ bake for EVERY combo the style model supports, at MANUAL
    sizes (so the plan 07-10 grow-to-fit change cannot perturb the rendered
    geometry): the top x left/center/right rows are the historical dy=0 cases;
    the middle/bottom rows are the new non-zero-dy cases that the plan 07-08
    fix carries. A regression on either side of the dy contract (canvas or
    bake) trips one of these combos.
    """
    ok, reason = _overlay_align_v_pixel_equals_bake(align_v, align_h=align_h)
    assert ok, f"align_h={align_h!r} align_v={align_v!r}: {reason}"


# -- UAT test 1 gap closure (plan 04-08): overlay geometry tracking (RC-1) --
# The overlay child must track the box through the canvas geometry paths. The
# canvas moves/resizes boxes via setRect + _sync_handles (canvas.py:1022-1023,
# 1597-1598, 1618-1619) on every drag-move and corner-resize, so the RC-1 fix
# splits a setPos-ONLY _reposition_text_overlay() out of refresh_text_overlay()
# and calls it from _sync_handles. The plan 07-01 overlay keeps this discipline
# (refresh_position is setPos-only; the cached pixmap/layout never re-renders
# during a drag).


@pytest.mark.gui
def test_text_overlay_tracks_box_after_setrect_move(qtbot) -> None:
    """After setRect(move) + _sync_handles the overlay sits INSIDE the moved box (RC-1).

    The overlay top-left tracks the box's new top-left by the SAME delta
    (renderer inset 2 + the cached ink offset — scene-px, zoom-independent).
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    tl0 = item._text_overlay.sceneBoundingRect().topLeft()
    item.setRect(QRectF(150, 150, 200, 100))
    item._sync_handles()
    tl = item._text_overlay.sceneBoundingRect().topLeft()
    assert tl.x() - tl0.x() == pytest.approx(130.0, abs=0.01)
    assert tl.y() - tl0.y() == pytest.approx(130.0, abs=0.01)


@pytest.mark.gui
def test_text_overlay_tracks_box_after_tl_edge_resize(qtbot) -> None:
    """After a TL-edge setRect resize + _sync_handles the overlay is INSIDE the box (RC-1).

    A TL/BL/TR-edge resize moves the box's top-left corner; the overlay follows
    by the same delta and stays inside the box (containment proxy).
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    tl0 = item._text_overlay.sceneBoundingRect().topLeft()
    item.setRect(QRectF(60, 40, 180, 90))
    item._sync_handles()
    tl = item._text_overlay.sceneBoundingRect().topLeft()
    assert tl.x() - tl0.x() == pytest.approx(40.0, abs=0.01)
    assert tl.y() - tl0.y() == pytest.approx(20.0, abs=0.01)
    assert (
        item._text_overlay.sceneBoundingRect().intersects(item.sceneBoundingRect())
        is True
    )


@pytest.mark.gui
def test_text_overlay_reposition_does_not_rebuild_document(qtbot) -> None:
    """_sync_handles repositions the overlay WITHOUT re-layouting (RC-1).

    The canvas calls _sync_handles on EVERY mouseMoveEvent during a drag, so
    the reposition must be setPos-only — the cached layout result must be the
    SAME object (a full refresh_text_overlay per mousemove is prohibited).
    The rendered text survives the move unchanged.
    """
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    cached = item._text_overlay.layout_result
    assert cached is not None
    item.setRect(QRectF(150, 150, 200, 100))
    item._sync_handles()
    assert item._text_overlay.layout_result is cached, (
        "a reposition must never re-layout (the cached layout survives)"
    )
    assert item._text_overlay.text() == "hello"


# -- UAT test 1 gap closure (plan 04-08): zoom + outline (RC-2/RC-3) --
# UI-SPEC §16 mandated a [10,28] viewport-px font clamp + a legibility outline.
# Phase 7 SUPERSEDES the viewport-px contract for OPAQUE text (RESEARCH Pattern
# 1 note, D-01): the style's font size is SCENE px and the outline width is the
# style's SCENE-px width — the overlay renders at the style size and scales
# with the canvas zoom like the artwork itself (WYSIWYG canvas ≡ bake). A zoom
# change therefore does NOT re-derive the style (the [10,28] clamp + 2/zoom
# outline are gone; the clamp survives only inside the renderer's Auto-fit
# base computation at scene px).


@pytest.mark.gui
@pytest.mark.parametrize("zoom", [0.5, 1.0, 4.0])
def test_text_overlay_size_is_zoom_independent_scene_px(qtbot, zoom) -> None:
    """apply_overlay_zoom does NOT re-derive the style: the rendered size stays
    the scene-px Auto-fit result for the reference box at every zoom — which
    now GROWS above the 14 px base (G-07-4: the clamp is not a hard max)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    expected = layout("hello", TextStyle(), QRectF(20, 20, 200, 100)).used_font_size_px
    assert expected > 14.0, "the reference box must grow above the 14 px base"
    item.apply_overlay_zoom(zoom)
    assert item._text_overlay.layout_result.used_font_size_px == pytest.approx(
        expected, abs=0.1
    )


@pytest.mark.gui
def test_text_overlay_outline_width_is_scene_px(qtbot) -> None:
    """The outline width is the style's SCENE-px width (2px default) — the
    constant-2-viewport-px 2/zoom outline is superseded (D-01)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(0.5)
    outline = item.pagebox.style.outline if item.pagebox.style is not None else None
    if outline is None:
        from manga_ai_studio.core.text_style import TextStyle

        outline = TextStyle().outline
    assert outline["width_px"] == 2.0  # scene px — zoom-independent


@pytest.mark.gui
def test_text_overlay_content_refresh_keeps_scene_px_style(qtbot) -> None:
    """A content refresh (no zoom arg) keeps the scene-px style — a content
    refresh never resets the size (the viewport-px clamp is gone)."""
    pb = _pagebox_with_text(recognized="hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(0.5)
    pb.set_translation("hola")  # content change -> current focus flips
    item.refresh_text_overlay()
    expected = layout("hola", TextStyle(), QRectF(20, 20, 200, 100)).used_font_size_px
    assert expected > 14.0, "the refreshed text must re-fit and grow (G-07-4)"
    assert item._text_overlay.layout_result.used_font_size_px == pytest.approx(
        expected, abs=0.1
    )
    assert item._text_overlay.text() == "hola"


@pytest.mark.gui
def test_zoom_changed_reapplies_overlay_style_canvas(qtbot) -> None:
    """The canvas zoom_changed slot forwards its zoom to the overlay; the
    scene-px overlay stays inside the box rect (D-01 WYSIWYG)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    pb = _pagebox_with_text(recognized="hello")
    canvas.set_boxes(user_pageboxes=[], detected_pageboxes=[pb])
    item = canvas._box_items[0]
    assert item._text_overlay.text() == "hello"
    expected = layout("hello", TextStyle(), QRectF(20, 20, 200, 100)).used_font_size_px
    assert expected > 14.0, "the reference box must grow above the 14 px base"
    canvas._on_zoom_changed_reposition_handles(0.5)
    assert item._text_overlay.layout_result.used_font_size_px == pytest.approx(
        expected, abs=0.1
    )
    # The overlay must stay inside the box rect after the zoom re-apply.
    assert (
        item._text_overlay.sceneBoundingRect().intersects(item.sceneBoundingRect())
        is True
    )


# -- UAT test 1 gap closure round 2 (plan 04-09): overlay fit-in-box --
# The 04-09 machinery (box-adaptive base, [10,28] clamp, bounded shrink to the
# 5 vp floor) is preserved as the AUTO-FIT mode (D-15) inside the shared
# renderer at SCENE px; the overlay renders whatever the renderer lays out.
# A resize COMMIT re-wraps/re-fits once per drag (the per-mousemove path stays
# setPos-only).


@pytest.mark.gui
def test_text_overlay_wraps_long_text_to_box_width(qtbot) -> None:
    """Long overlay text WRAPS at the box inner width — no horizontal overshoot.

    The reference box (20,20,220,120) has a 200-wide rect; the renderer's
    inner width is 200 - 2x2 = 196. The text is 60 words ("word " x 59 +
    "word") so no trailing space is lost to trailing-whitespace trimming.
    """
    pb = _pagebox_with_text(recognized="word " * 59 + "word")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    result = item._text_overlay.layout_result
    assert result is not None
    assert len(result.line_rects) >= 2, "long text must wrap into multiple lines"
    assert (
        item._text_overlay.sceneBoundingRect().right()
        <= item.sceneBoundingRect().right() + 1.5
    )
    assert item._text_overlay.text() == "word " * 59 + "word"


@pytest.mark.gui
@pytest.mark.parametrize(
    "box,base",
    [
        # Box is (x1, y1, x2, y2): (20,20,220,120) -> 200x100 rect, min dim 100
        # -> base 14 (the UI-SPEC reference box).
        (Box(20, 20, 220, 120), 14.0),
        # (20,20,220,170) -> 200x150 rect, min dim 150 -> base 21.0.
        (Box(20, 20, 220, 170), 21.0),
        # (20,20,320,320) -> 300x300 rect, min dim 300 -> base 42 -> clamped 28.
        (Box(20, 20, 320, 320), 28.0),
    ],
)
def test_text_overlay_font_adapts_to_box_size(qtbot, box, base) -> None:
    """The Auto-fit font is BOX-ADAPTIVE AND grows to fill (G-07-4): short
    text renders ABOVE the 14 x min(box_w, box_h)/100 base (the [10,28] clamp
    is the STARTING point, not a hard max), bounded by the per-box growth cap
    min(inner_w, inner_h) at SCENE px (the 04-09 machinery preserved inside
    the shared renderer)."""
    pb = PageBox(box=box, origin=DETECTED)
    pb.set_recognized_text("hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    used = item._text_overlay.layout_result.used_font_size_px
    inner_w = max(1.0, box.x2 - box.x1 - 4.0)
    inner_h = max(1.0, box.y2 - box.y1 - 4.0)
    assert used > base, "short text must grow above the box-adaptive base"
    assert used <= min(inner_w, inner_h) + 1e-6, (
        "growth is capped at min(inner_w, inner_h)"
    )
    assert item._text_overlay.layout_result.overflow is False


@pytest.mark.gui
def test_text_overlay_shrinks_to_fit_box_height(qtbot) -> None:
    """Wrapped text that exceeds the box height shrinks (bounded) to fit inside.

    "word " x 40 wraps at the inner width and the base 14 font needs ~8 lines —
    exceeds the inner height 94, so the Auto-fit loop reduces the RENDERED
    font (below the [10,28] clamp if needed, never below the 5 px floor). The
    overlay rect must stay CONTAINED in the box rect.
    """
    pb = _pagebox_with_text(recognized="word " * 40)
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay_rect = item._text_overlay.sceneBoundingRect()
    box_rect = item.sceneBoundingRect()
    assert overlay_rect.right() <= box_rect.right() + 1.5
    assert overlay_rect.bottom() <= box_rect.bottom() + 1.5
    assert item._text_overlay.layout_result.used_font_size_px < 14.0, (
        "the shrink loop must have engaged"
    )


@pytest.mark.gui
def test_resize_commit_rewraps_overlay_text_canvas(qtbot) -> None:
    """A resize COMMIT re-wraps/re-fits the overlay to the final rect (once per drag).

    _commit_resize must refresh the overlay after _sync_handles: after a
    resize to (20,20,320,200) the Auto-fit result grows past the old 28 px
    clamp (min dim 200 -> base 28, then grow-while-fits, G-07-4) — the
    stale reference-box layout must be gone.
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
    # min dim 200 -> base 28, then growth: "hello" is one line at 28+ px
    # within the inner height, so the size exceeds the old 28 px clamp.
    used = item._text_overlay.layout_result.used_font_size_px
    assert used > 28.0, "the resize commit must re-fit beyond the old clamp max"
    assert used <= min(296.0, 176.0) + 1e-6, (
        "growth is capped at min(inner_w, inner_h)"
    )
    assert item._text_overlay.layout_result.overflow is False


@pytest.mark.gui
def test_text_overlay_fit_loop_reduces_below_clamp_floor_at_scene_px(qtbot) -> None:
    """The Auto-fit loop operates BELOW the [10,28] clamp, never below the 5 px
    floor, at SCENE px (the viewport-px zoom dependence is gone — D-01).

    A very long text in a narrow box needs more than the 10px clamp provides;
    the loop shrinks the rendered font below 10 down toward the 5 px floor and
    the overlay stays CONTAINED in the box (the 04-09 outcome, zoom-independent
    at scene px).
    """
    pb = PageBox(box=Box(20, 20, 120, 220), origin=DETECTED)
    pb.set_recognized_text("word " * 100)
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    item.apply_overlay_zoom(0.25)  # zoom must NOT affect the scene-px size
    used = item._text_overlay.layout_result.used_font_size_px
    assert used < 10.0  # shrink engaged, below the base clamp
    assert used >= 5.0  # never below the floor
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
    assert item._text_overlay.text() == "hello"
    # Now set a translation — current focus flips to translation.
    pb.set_translation("hola")
    item.refresh_text_overlay()
    assert item._text_overlay.text() == "hola"


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
    """load_box populates bubble_no/origin/recognized/translation/language
    from the pagebox; the vertical checkbox reads the per-box STYLE flag
    (G-07-1 — style.vertical, not the export-metadata payload flag)."""
    from manga_ai_studio.core.text_style import TextStyle

    pb = _pagebox_with_text(recognized="hello", translation="hola")
    pb.bubble_no = 7
    pb.payload.language = "ja"
    pb.style = TextStyle(vertical=True)

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


# ---- quick-260822-vk7: text-edit-session probe + Inspector reload guard


@pytest.mark.gui
def test_is_text_edit_active_false_without_focus(qtbot) -> None:
    """is_text_edit_active() is False on a fresh populated panel (no field focused)."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pagebox_with_text(recognized="hello", translation="hola"))
    assert panel.is_text_edit_active() is False


@pytest.mark.gui
def test_is_text_edit_active_true_when_field_focused(qtbot) -> None:
    """Focusing either _CommitTextEdit field flips the probe True (D-04
    symmetry: recognized and translation are equally exposed)."""
    panel = _make_inspector(qtbot)
    panel.show()
    qtbot.waitExposed(panel)
    panel.load_box(_pagebox_with_text(recognized="hello", translation="hola"))
    panel.translation_edit.setFocus()
    QApplication.processEvents()
    assert panel.is_text_edit_active() is True
    panel.recognized_edit.setFocus()
    QApplication.processEvents()
    assert panel.is_text_edit_active() is True


@pytest.mark.gui
def test_selection_follower_reload_skipped_while_translation_focused(
    qtbot, tmp_path, monkeypatch
) -> None:
    """quick-260822-vk7 Task 1: with translation_edit focused, a reload via
    _on_canvas_selection_changed is SKIPPED (load_box never lands mid-edit);
    once focus leaves the field the guard releases and the follower resyncs
    (load_box runs again)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    item.setSelected(True)
    QApplication.processEvents()
    panel = window.inspector_panel

    # Recorder around the REAL load_box.
    load_calls: list = []
    real_load = panel.load_box
    monkeypatch.setattr(
        panel,
        "load_box",
        lambda pb, **kw: (load_calls.append(pb), real_load(pb, **kw)),
    )
    load_calls.clear()  # drop the initial selection-follow populate

    panel.translation_edit.setFocus()
    QApplication.processEvents()
    assert panel.is_text_edit_active() is True
    panel.translation_edit.insertPlainText("typed mid-edit")

    # The reload attempt while focused -> suppressed, typed text untouched.
    window._on_canvas_selection_changed()
    assert load_calls == [], "load_box must NOT land mid-edit"
    assert panel.translation_edit.toPlainText().endswith("typed mid-edit")

    # Focus-out releases the guard: the commit chain itself reloads the panel
    # (_inspector_commit_post -> load_box + the boxes_modified follower) and
    # any further reload also lands — the guard is gone either way.
    panel.translation_edit.clearFocus()
    QApplication.processEvents()
    assert len(load_calls) >= 1, "the guard must release after focus-out"
    window._on_canvas_selection_changed()
    assert len(load_calls) >= 2, "subsequent reloads land normally again"


@pytest.mark.gui
def test_boxes_modified_reload_does_not_clobber_focused_translation(
    qtbot, tmp_path
) -> None:
    """quick-260822-vk7 Task 1 (end-to-end shape): the OCR-finished chain
    (_on_ocr_finished -> canvas.boxes_modified -> _on_boxes_modified ->
    _on_canvas_selection_changed -> load_box) must NOT clobber the typed
    translation while the field holds focus."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    item.setSelected(True)
    QApplication.processEvents()
    panel = window.inspector_panel
    panel.translation_edit.setFocus()
    QApplication.processEvents()
    panel.translation_edit.insertPlainText("my translation")
    # Drive the same emission _on_ocr_finished performs after writing text.
    window.canvas.boxes_modified.emit(window.canvas.boxes_snapshot())
    assert panel.translation_edit.toPlainText().endswith("my translation")


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
    assert item._text_overlay.text() == "after"


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


# ===========================================================================
# quick-260824-t64 Task 1 — zoom-compensated inline editor font
# ===========================================================================
# The QGraphicsProxyWidget does NOT ignore transformations, so a fixed 14px
# font scales WITH the view transform: at 25% zoom the editor text renders at
# ~3.5 screen px (unreadable on big pages). The fix compensates inversely in
# enter(): scene px = base / zoom, floored at the base and capped at 64.
# pixelSize is the ONLY exact assertion (Phase 6 A4 discipline — never pointSize).


@pytest.mark.gui
@pytest.mark.parametrize(
    ("zoom", "expected"),
    [
        pytest.param(0.25, 56, id="zoom-out-0.25"),  # round(14/0.25) = 56
        pytest.param(1.0, 14, id="zoom-1.0-unchanged"),  # floor: exactly today's size
        pytest.param(0.1, 64, id="extreme-zoom-out-capped"),  # round(140) -> cap 64
    ],
)
def test_inline_editor_font_zoom_compensated(qtbot, zoom, expected) -> None:
    """The editor's font pixel size compensates for canvas zoom: base/zoom,
    floored at the 14px base (zoom >= 100% unchanged), capped at 64 scene px."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    item = _editor_box(canvas, text="hello")
    # Set the live zoom the way the canvas does (zoom() sets the attribute +
    # transform; the editor only reads the zoom_factor attribute).
    canvas.zoom_factor = zoom
    editor = InlineEditor(canvas)
    editor.enter(item)
    info = QFontInfo(editor._text_edit.font())
    assert info.pixelSize() == expected


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
def test_alt_drag_draw_release_emits_no_ocr_requested(qtbot) -> None:
    """D-01 (quick-260822-gnq, revised quick-260824-pqn): Alt+drag
    draw-release NEVER emits ocr_requested — a new box is only marked
    geometry-stale via the boxes_modified commit; running OCR is manual-only
    (the corner affordance). The ocr_requested signal stays declared; a
    draw-and-release must emit boxes_modified and zero OCR requests."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    requested: list = []
    canvas.ocr_requested.connect(lambda item: requested.append(item))
    modified: list = []
    canvas.boxes_modified.connect(lambda snap: modified.append(snap))
    canvas.mousePressEvent(_press_at(canvas, 30, 30, alt=True))
    canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
    canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))
    assert canvas.box_count() == 1
    assert requested == []  # no instant dispatch — manual re-detect only
    assert len(modified) == 1  # the commit still flows (marks the box stale)


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
def test_load_translations_dialog_font_14px(qtbot) -> None:
    """D-12 typography: LoadTranslationsDialog's base font renders at 14px
    Body — dialog field values and labels (UI-SPEC typography table row).
    The paste area's mono exception (Consolas 10) is preserved, not asserted
    away."""
    from manga_ai_studio.gui.load_translations_dialog import LoadTranslationsDialog

    dlg = LoadTranslationsDialog(page_names=["a.png"])
    qtbot.addWidget(dlg)
    assert QFontInfo(dlg.font()).pixelSize() == 14


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


# ===========================================================================
# Plan 07-02 (D-08/D-09) — multi-select: selection mechanics (Task 1)
# ===========================================================================
# Shift+click toggles membership without clearing others; a plain click keeps
# the Phase 3 single-select; clicking empty canvas clears ALL then falls
# through to the mask-tool dispatch; Esc deselects all; Ctrl+A (Edit ->
# Select All Boxes) selects every box. These tests drive the REAL canvas
# dispatch (mousePressEvent / keyPressEvent), not direct setSelected calls.


def _shift_press_at(canvas: EditorCanvas, sx: float, sy: float) -> QMouseEvent:
    """Build a left-button SHIFT+press (the multi-select toggle) at (sx, sy)."""
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
    )


@pytest.mark.gui
def test_multi_select_shift_toggle(qtbot) -> None:
    """Shift+click ADDS a box without clearing others; a second Shift+click on
    the same box removes ONLY it (D-08, plan 07-02; UI-SPEC surface 32)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b = canvas._box_items

    # Plain click selects A (Phase 3 single-select).
    canvas.mousePressEvent(_press_at(canvas, 35, 35))
    assert a.isSelected() is True
    assert b.isSelected() is False

    # Shift+click B -> B joins; A survives (len(selectedItems()) grows).
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))
    assert len(canvas._scene.selectedItems()) == 2
    assert a.isSelected() is True
    assert b.isSelected() is True

    # Shift+click B again -> only B removed.
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))
    assert len(canvas._scene.selectedItems()) == 1
    assert a.isSelected() is True
    assert b.isSelected() is False


@pytest.mark.gui
def test_multi_select_plain_click_clears_others(qtbot) -> None:
    """A PLAIN click on an UNSELECTED box clears the rest and selects only
    that box — the multi-select model's N=1 case stays Phase 3-identical
    (D-08). A plain click on an already-selected member keeps the group (the
    D-09 group-arm path), so this test clicks an unselected box."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
            PageBox(box=Box(200, 200, 260, 260), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b, c = canvas._box_items

    canvas.mousePressEvent(_shift_press_at(canvas, 35, 35))
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))
    assert len(canvas._scene.selectedItems()) == 2

    # Plain click on UNSELECTED box C -> only C (the multi-selection
    # collapses to N=1).
    canvas.mousePressEvent(_press_at(canvas, 230, 230))
    assert len(canvas._scene.selectedItems()) == 1
    assert c.isSelected() is True
    assert a.isSelected() is False
    assert b.isSelected() is False


@pytest.mark.gui
def test_empty_click_clears_all(qtbot) -> None:
    """Clicking EMPTY canvas (no Alt) clears the WHOLE selection AND still
    falls through to the mask-tool dispatch (UI-SPEC surface 32 + §12d)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b = canvas._box_items
    canvas.mousePressEvent(_shift_press_at(canvas, 35, 35))
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))
    assert len(canvas._scene.selectedItems()) == 2

    # Brush tool + empty-canvas click: selection clears AND the mask paints.
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(12)
    canvas.mousePressEvent(_press_at(canvas, 300, 300))  # empty area
    assert len(canvas._scene.selectedItems()) == 0
    assert a.isSelected() is False and b.isSelected() is False
    assert canvas.get_mask().pixelColor(300, 300).alpha() > 0, (
        "empty-canvas click must still fall through to the mask-tool dispatch"
    )


@pytest.mark.gui
def test_select_all_boxes(qtbot, tmp_path) -> None:
    """Ctrl+A selects EVERY box; the action is disabled with zero boxes and
    during a running async op (D-08, plan 07-02; T-07-05 single binding)."""
    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    _seed_boxes_window(
        window,
        [Box(10, 10, 60, 60), Box(100, 100, 160, 160), Box(200, 200, 260, 260)],
    )
    window._refresh_action_states()
    assert window.action_select_all_boxes.isEnabled() is True
    assert window.action_select_all_boxes.shortcut().toString() == "Ctrl+A"

    # Trigger through the ACTION (the menu/shortcut path), not a direct call.
    window.action_select_all_boxes.trigger()
    assert len(canvas._scene.selectedItems()) == 3

    # Gate: zero boxes -> disabled.
    canvas.set_boxes(user_pageboxes=[], detected_pageboxes=[])
    window._refresh_action_states()
    assert window.action_select_all_boxes.isEnabled() is False

    # Gate: async op running -> disabled even with boxes present.
    _seed_boxes_window(window, [Box(10, 10, 60, 60)])
    window._op_running = True
    window._refresh_action_states()
    assert window.action_select_all_boxes.isEnabled() is False


@pytest.mark.gui
def test_esc_deselects_all(qtbot) -> None:
    """Esc clears the WHOLE multi-selection (no inline editor active) — the
    single-select Esc behavior extends to N>1 (D-08, plan 07-02)."""
    from PySide6.QtGui import QKeyEvent

    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b = canvas._box_items
    canvas.mousePressEvent(_shift_press_at(canvas, 35, 35))
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))
    assert len(canvas._scene.selectedItems()) == 2

    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(esc)
    assert len(canvas._scene.selectedItems()) == 0
    assert a.isSelected() is False and b.isSelected() is False


# ===========================================================================
# Plan 07-02 (D-09) — grouped move + grouped delete (Task 2)
# ===========================================================================
# Dragging ANY member of a multi-selection moves the whole group by the same
# delta with ONE arm-time boxes snapshot (one Ctrl+Z restores the group);
# Delete removes ALL selected boxes silently with one pre-delete snapshot.
# The group op names the undo flash ("Moved {n} boxes" / "Deleted {n} boxes").
# NOTE: these tests drive REAL Qt event delivery (QTest.mousePress/Move/
# Release — the _drive_real_body_move pattern) because the synthetic
# QMouseEvent helpers report button()=NoButton on release, which never enters
# the move-COMMIT branch (the emit gate). The real path is the committed
# production interaction (canvas.py mouseReleaseEvent).


def _drive_real_body_drag(
    canvas: EditorCanvas, from_scene: tuple[float, float], to_scene: tuple[float, float]
) -> None:
    """Drive a REAL Qt press/move/release body drag on the canvas viewport.

    ``from_scene`` must land on a SELECTED box member (the group arm keeps the
    selection; a plain press on a member of a multi-selection does NOT clear
    it). Mirrors ``_drive_real_body_move`` but stays canvas-only (no qtbot).
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
def test_group_move_one_undo(qtbot, tmp_path) -> None:
    """Drag one selected member -> ALL selected rects shift by the SAME delta;
    the history holds exactly ONE boxes entry; one undo() restores every
    pre-move rect (D-09; RESEARCH Common Operation 6; T-07-06)."""
    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    items = _seed_boxes_window(
        window,
        [Box(10, 10, 60, 60), Box(100, 100, 160, 160), Box(200, 200, 260, 260)],
    )
    a, b, c = items
    canvas.select_all_boxes()
    assert len(canvas._scene.selectedItems()) == 3
    pre = [QRectF(it.rect()) for it in items]

    # Drag the FIRST member (35,35) -> (75,65) through REAL event delivery.
    _drive_real_body_drag(canvas, (35.0, 35.0), (75.0, 65.0))

    # EVERY selected box moved by the SAME delivered delta (QTest truncates
    # sub-pixels at the fractional fit scale, so assert the group property,
    # not the nominal delta).
    dx = a.rect().x() - pre[0].x()
    dy = a.rect().y() - pre[0].y()
    assert (dx, dy) != (0, 0), "the drag must actually move the group"
    for i, it in enumerate(items):
        assert it.rect().x() == pre[i].x() + dx
        assert it.rect().y() == pre[i].y() + dy
    # The boxes stack holds exactly ONE entry for the whole group op.
    assert len(window.history._boxes_undo) == 1
    # The op-name flash fired.
    assert window.status_bar_left.text() == "Moved 3 boxes \u2014 press Ctrl+Z to undo."

    # ONE undo restores every pre-move rect. The restore REBUILDS the layer
    # (set_boxes), so re-fetch the items — the pre-drag references are stale.
    window.on_undo()
    QApplication.processEvents()
    restored_items = list(canvas._box_items)
    assert len(restored_items) == 3
    for i, it in enumerate(restored_items):
        assert it.rect() == pre[i], (
            "one Ctrl+Z must restore the WHOLE group (single BOXES snapshot)"
        )
    # The undo flash carries the recorded op name (06-WR-01 pattern).
    assert window.status_bar_left.text() == "Undo: Moved 3 boxes"


@pytest.mark.gui
def test_group_delete_one_undo(qtbot, tmp_path) -> None:
    """Delete with a multi-selection removes ALL selected boxes SILENTLY (no
    dialog) with ONE pre-delete snapshot; one undo restores the full set
    (D-09/D-12; T-07-06)."""
    from PySide6.QtGui import QKeyEvent

    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    items = _seed_boxes_window(
        window,
        [Box(10, 10, 60, 60), Box(100, 100, 160, 160), Box(200, 200, 260, 260)],
    )
    pre_boxes = [it.current_box() for it in items]
    canvas.select_all_boxes()
    assert len(canvas._scene.selectedItems()) == 3

    # Drive Delete through the real key handler.
    del_key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    canvas.keyPressEvent(del_key)

    assert canvas.box_count() == 0
    assert len(window.history._boxes_undo) == 1
    assert window.status_bar_left.text() == (
        "Deleted 3 boxes \u2014 press Ctrl+Z to restore."
    )

    # One undo restores the full set (same boxes).
    window.on_undo()
    QApplication.processEvents()
    assert canvas.box_count() == 3
    restored = [it.current_box() for it in canvas._box_items]
    assert {(b.x1, b.y1, b.x2, b.y2) for b in restored} == {
        (b.x1, b.y1, b.x2, b.y2) for b in pre_boxes
    }


@pytest.mark.gui
def test_group_move_no_relayout(qtbot, tmp_path, monkeypatch) -> None:
    """A group drag never re-layouts text: the reposition path is setPos-only
    (RC-1) — zero renderer layout invocations during the drag (the
    layout-cache-hit regression lock, plan-07 must_haves)."""
    import manga_ai_studio.gui.box_item as box_item_mod

    calls: list = []
    real_layout = box_item_mod.renderer_layout

    def counting_layout(*args, **kwargs):
        calls.append(1)
        return real_layout(*args, **kwargs)

    monkeypatch.setattr(box_item_mod, "renderer_layout", counting_layout)

    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    items = _seed_boxes_window(
        window,
        [Box(10, 10, 60, 60), Box(100, 100, 160, 160), Box(200, 200, 260, 260)],
    )
    # Give the boxes text so the overlay WOULD render if a re-layout happened.
    for it in items:
        it.pagebox.set_recognized_text("hello")
        it.refresh_text_overlay()
    assert len(calls) >= 1  # the initial overlay renders DID layout
    calls.clear()

    canvas.select_all_boxes()
    _drive_real_body_drag(canvas, (35.0, 35.0), (75.0, 65.0))

    assert calls == [], (
        "group drag must be reposition-only (setRect + _sync_handles) - "
        "zero renderer layout invocations (RC-1)"
    )


@pytest.mark.gui
def test_group_move_no_drag_no_op(qtbot, tmp_path) -> None:
    """A click WITHOUT a drag on a multi-selection member emits NO
    boxes_modified (WR-04 no-drag gate extends to the group form) - no spurious
    BOXES entry."""
    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    _seed_boxes_window(
        window,
        [Box(10, 10, 60, 60), Box(100, 100, 160, 160), Box(200, 200, 260, 260)],
    )
    canvas.select_all_boxes()

    emitted: list = []
    canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    vp = canvas.viewport()
    press_at = canvas.mapFromScene(QPointF(35, 35))
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(press_at.x(), press_at.y()))
    QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(press_at.x(), press_at.y()))
    QApplication.processEvents()

    assert emitted == [], "a click-without-drag must not emit boxes_modified"
    assert len(window.history._boxes_undo) == 0


# ===========================================================================
# Plan 07-02 (D-09) — N-selected affordance + primary-only handles + resize gate
# (Task 3)
# ===========================================================================
# Every selected box shows the 3px selected border + hue tint; corner handles
# render on the PRIMARY (last-clicked) box only; a CornerHandle press inside a
# multi-selection is a no-op (resize stays single-box); removing the primary
# promotes the last-selected remaining member (UI-SPEC surface 32).


def _visible_handle_count(item: BoxItem) -> int:
    return sum(1 for h in item.handles.values() if h.isVisible())


@pytest.mark.gui
def test_multi_select_affordance_primary_handles(qtbot) -> None:
    """N>1: EVERY selected box shows the 3px selected border; exactly ONE box
    (the primary) shows corner handles (UI-SPEC surface 32 affordance table)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
            PageBox(box=Box(200, 200, 260, 260), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b, c = canvas._box_items

    canvas.mousePressEvent(_press_at(canvas, 35, 35))  # primary = A
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))  # primary = B
    canvas.mousePressEvent(_shift_press_at(canvas, 230, 230))  # primary = C

    # Selected border on ALL three members (3px pen).
    for it in (a, b, c):
        assert it.isSelected() is True
        assert int(it.pen().width()) == 3

    # Corner handles on the PRIMARY box only.
    assert canvas._primary_box is c
    assert _visible_handle_count(c) == 4
    assert _visible_handle_count(a) == 0
    assert _visible_handle_count(b) == 0


@pytest.mark.gui
def test_resize_single_box_only(qtbot) -> None:
    """A CornerHandle press while N>1 boxes are selected is a NO-OP (no group
    resize — RESEARCH Open Q6); with exactly one selected the Phase 3 resize
    still works."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b = canvas._box_items
    pre_a = QRectF(a.rect())
    pre_b = QRectF(b.rect())

    # Multi-selection: press A's SE corner-handle OFFSET zone (the +-5px hit
    # shape OUTSIDE the box body, per test_corner_handle_hit_target) + drag ->
    # nothing resizes (the single-box gate makes the arm a no-op).
    canvas.mousePressEvent(_shift_press_at(canvas, 35, 35))
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))
    assert len(canvas._scene.selectedItems()) == 2
    canvas.mousePressEvent(_press_at(canvas, 64, 64))  # A's BR handle offset zone
    canvas.mouseMoveEvent(_move_at(canvas, 80, 80))
    canvas.mouseReleaseEvent(_release_at(canvas, 80, 80))
    assert a.rect() == pre_a and b.rect() == pre_b, (
        "corner-handle drag with a multi-selection must be a no-op (single-box resize)"
    )

    # Exactly one selected: the Phase 3 resize path still works.
    canvas.mousePressEvent(_press_at(canvas, 130, 130))  # plain click -> B only
    assert len(canvas._scene.selectedItems()) == 1
    canvas.mousePressEvent(_press_at(canvas, 164, 164))  # B's BR handle offset zone
    canvas.mouseMoveEvent(_move_at(canvas, 180, 180))
    canvas.mouseReleaseEvent(_release_at(canvas, 180, 180))
    assert b.rect().width() > pre_b.width() and b.rect().height() > pre_b.height()
    assert a.rect() == pre_a  # untouched


@pytest.mark.gui
def test_primary_removal_promotes(qtbot) -> None:
    """Shift+clicking the PRIMARY off promotes the last-selected remaining
    member to primary — its handles show (UI-SPEC surface 32)."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_boxes(
        user_pageboxes=[
            PageBox(box=Box(10, 10, 60, 60), origin=USER),
            PageBox(box=Box(100, 100, 160, 160), origin=USER),
            PageBox(box=Box(200, 200, 260, 260), origin=USER),
        ],
        detected_pageboxes=[],
    )
    a, b, c = canvas._box_items

    canvas.mousePressEvent(_press_at(canvas, 35, 35))  # primary = A
    canvas.mousePressEvent(_shift_press_at(canvas, 130, 130))  # primary = B
    canvas.mousePressEvent(_shift_press_at(canvas, 230, 230))  # primary = C
    assert canvas._primary_box is c

    # Toggle the primary (C) off -> B (the last selected) is promoted.
    canvas.mousePressEvent(_shift_press_at(canvas, 230, 230))
    assert c.isSelected() is False
    assert canvas._primary_box is b
    assert _visible_handle_count(b) == 4
    assert _visible_handle_count(a) == 0


# ===========================================================================
# Plan 07-05 Task 3 — live vertical checkbox (D-13) + font-size actions (D-16)
# + the atomic vertical-flag OR (canvas overlay == bake)
# ===========================================================================


@pytest.mark.gui
def test_vertical_checkbox_live(qtbot, tmp_path, monkeypatch) -> None:
    """G-07-1: toggling the Inspector Vertical checkbox writes STYLE.vertical
    and flips the overlay's layout mode (tategaki <-> horizontal) — a toggle
    must RE-RENDER, not just write metadata (Pitfall 9); the bake renders the
    same vertical layout (the shared single-flag expression); the 'Coming
    soon' tooltip is gone."""
    from manga_ai_studio.gui import text_renderer as tr_module
    from manga_ai_studio.gui.text_renderer import bake_typeset_page

    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 80, 80)])[0]
    item.pagebox.set_translation("こんにちは")
    item.refresh_text_overlay()  # the overlay renders after the box gains text
    item.setSelected(True)
    QApplication.processEvents()

    # Horizontal by default (the overlay's cached layout has no vertical
    # placements).
    assert item._text_overlay.layout_result.vertical_placements == []

    # Toggle ON via the live checkbox -> style.vertical True + re-render.
    window.inspector_panel.vertical_check.setChecked(True)
    QApplication.processEvents()
    assert item.pagebox.style.vertical is True
    assert item._text_overlay.layout_result.vertical_placements, (
        "the overlay must re-render vertically after the toggle (Pitfall 9)"
    )

    # Toggle back -> horizontal again.
    window.inspector_panel.vertical_check.setChecked(False)
    QApplication.processEvents()
    assert item.pagebox.style.vertical is False
    assert item._text_overlay.layout_result.vertical_placements == []

    # The tooltip holds the D-13 copy (no 'Coming soon').
    tip = window.inspector_panel.vertical_check.toolTip()
    assert "Coming soon" not in tip
    assert "tategaki" in tip

    # The bake renders the box vertically too — the SAME single-flag
    # expression (spy text_renderer.layout: bake_typeset_page calls it by
    # module name, box_item's renderer_layout alias stays untouched).
    window.inspector_panel.vertical_check.setChecked(True)
    QApplication.processEvents()
    captured: list[bool] = []
    original_layout = tr_module.layout

    def _spy_layout(text, style, rect, vertical=False):
        captured.append(bool(vertical))
        return original_layout(text, style, rect, vertical=vertical)

    monkeypatch.setattr(tr_module, "layout", _spy_layout)
    import numpy as np

    page = np.full((120, 120, 3), 200, dtype=np.uint8)
    bake_typeset_page(page, window.canvas.boxes_snapshot())
    assert captured, "the bake must call the shared layout"
    assert all(captured), "the bake must render a vertical box vertically (D-13)"


@pytest.mark.gui
def test_vertical_toggle_writes_style_and_never_constructs_payload(
    qtbot, tmp_path
) -> None:
    """G-07-1/WR-01: toggling Vertical on a payload-None (never-OCR'd user)
    box writes style.vertical — the toggle NEVER constructs the payload (the
    payload stays None; no side-effect mutation beyond the user's intent).
    ONE Ctrl+Z restores the pre-toggle style (None — defaults again)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 80, 80)])[0]
    assert item.pagebox.payload is None  # a never-OCR'd user box
    item.setSelected(True)
    QApplication.processEvents()

    window.inspector_panel.vertical_check.setChecked(True)
    QApplication.processEvents()
    assert item.pagebox.payload is None, (
        "the vertical toggle must never construct the payload (G-07-1)"
    )
    assert item.pagebox.style is not None
    assert item.pagebox.style.vertical is True

    # ONE Ctrl+Z restores the pre-toggle state (style None — defaults again).
    window.on_undo()
    QApplication.processEvents()
    assert window.canvas._box_items[0].pagebox.style is None, (
        "undo must restore the pre-toggle style-None state (G-07-1)"
    )


@pytest.mark.gui
def test_preflagged_box_renders_horizontal_by_default(
    qtbot, tmp_path, monkeypatch
) -> None:
    """G-07-1: a CTD pre-flagged box (payload.vertical=True) renders
    HORIZONTAL by default — payload.vertical is pure export metadata, never a
    render instruction; the render flag is bool(style.vertical) ONLY. The
    bake agrees: bake_typeset_page captures vertical=False in the layout spy
    (the shared single-flag expression; box_item's renderer_layout alias is
    untouched so the overlay stays on the real layout)."""
    from manga_ai_studio.gui import text_renderer as tr_module
    from manga_ai_studio.gui.text_renderer import bake_typeset_page

    window = _window_with_page(qtbot, tmp_path)
    pb = PageBox(box=Box(10, 20, 80, 80), origin=DETECTED)
    pb.set_recognized_text("日本語テスト")
    pb.payload.vertical = True
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pb], [])
    finally:
        window._suppress_boxes_push = False
    item = window.canvas._box_items[0]
    assert item.pagebox.style is None  # default style
    assert item._text_overlay.layout_result.vertical_placements == [], (
        "a payload.vertical box renders HORIZONTAL by default — the detector "
        "metadata never flips rendering (G-07-1)"
    )

    # The bake renders the same preflagged box HORIZONTALLY.
    captured: list[bool] = []
    original_layout = tr_module.layout

    def _spy_layout(text, style, rect, vertical=False):
        captured.append(bool(vertical))
        return original_layout(text, style, rect, vertical=vertical)

    monkeypatch.setattr(tr_module, "layout", _spy_layout)
    import numpy as np

    page = np.full((120, 120, 3), 200, dtype=np.uint8)
    bake_typeset_page(page, window.canvas.boxes_snapshot())
    assert captured, "the bake must call the shared layout"
    assert not any(captured), (
        "a preflagged box with style None bakes HORIZONTAL — payload.vertical "
        "is metadata, not a render instruction (G-07-1)"
    )


@pytest.mark.gui
def test_size_plus_minus_actions(qtbot, tmp_path) -> None:
    """D-16: Ctrl+] / Ctrl+[ each bound exactly once (CR-14 single-binding);
    the ±1 px delta applies to EVERY selected box with exactly ONE BOXES
    entry per action (one Ctrl+Z reverses the whole commit)."""
    from PySide6.QtGui import QAction

    from manga_ai_studio.core.text_style import TextStyle

    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 60, 60), Box(80, 20, 60, 60)]
    )
    for it in items:
        it.pagebox.style = TextStyle(auto_fit=False, font_size_px=10.0)

    # Single-binding discipline (T-07-12): each sequence appears on exactly
    # ONE action in the window's action map.
    plus = [
        a for a in window.findChildren(QAction)
        if a.shortcut().toString() == "Ctrl+]"
    ]
    minus = [
        a for a in window.findChildren(QAction)
        if a.shortcut().toString() == "Ctrl+["
    ]
    assert len(plus) == 1, "Ctrl+] must be bound exactly once"
    assert len(minus) == 1, "Ctrl+[ must be bound exactly once"

    items[0].setSelected(True)
    items[1].setSelected(True)
    QApplication.processEvents()

    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    window._on_font_size_delta(1)
    QApplication.processEvents()
    assert items[0].pagebox.style.font_size_px == 11.0
    assert items[1].pagebox.style.font_size_px == 11.0
    assert len(emitted) == 1, "one font-size action = one BOXES entry"
    before = emitted[0]
    assert before[0].style.font_size_px == 10.0
    assert before[1].style.font_size_px == 10.0

    window._on_font_size_delta(-1)
    QApplication.processEvents()
    assert items[0].pagebox.style.font_size_px == 10.0
    assert items[1].pagebox.style.font_size_px == 10.0
    assert len(emitted) == 2


@pytest.mark.gui
def test_size_action_converts_auto_fit(qtbot, tmp_path) -> None:
    """A11: a size +/- action on an Auto-fit box converts it to MANUAL at its
    current rendered size first, then applies the ±1 px delta; the manual
    floor is 1 px."""
    from manga_ai_studio.core.text_style import TextStyle

    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(10, 20, 80, 80)])[0]
    item.pagebox.set_translation("Auto-fit text")
    item.setSelected(True)
    QApplication.processEvents()

    style = item.pagebox.style if item.pagebox.style is not None else TextStyle()
    assert style.auto_fit is True
    rendered = window._style_rendered_size(item)

    window._on_font_size_delta(1)
    QApplication.processEvents()
    after = item.pagebox.style
    assert after.auto_fit is False
    assert after.font_size_px == rendered + 1.0, (
        "the converted manual size must equal the rendered auto-fit size + 1 (A11)"
    )

    # The floor: decreasing a 1px manual box stays at 1.
    item.pagebox.style = TextStyle(auto_fit=False, font_size_px=1.0)
    window._on_font_size_delta(-1)
    QApplication.processEvents()
    assert item.pagebox.style.font_size_px == 1.0


# ===========================================================================
# Plan 07-06 — G-07-6 Ctrl+Z teardown UAF (graveyard lifetime contract)
# ===========================================================================
#
# G-07-6 (07-UAT blocker): Ctrl+Z after a style commit natively crashes the
# app (0xC0000409). Root cause: style commits queue scene UpdateRequests that
# reference the overlay items (TypesetOverlayItem.set_content -> self.update()),
# then on_undo -> apply_undo_boxes -> set_boxes removes every BoxItem and drops
# the LAST Python refs synchronously mid-event-loop -> shiboken deletes the C++
# items while pending updates still reference them -> the next flush dispatches
# paint() to a freed TypesetOverlayItem -> pure-virtual call -> abort.
#
# The suite never caught it because every test helper HOLDS the item wrappers
# (e.g. _seed_boxes_window returns the list), deferring C++ deletion to window
# teardown. These regressions deliberately drop ALL wrapper refs before
# on_undo()/Delete — mirroring the app lifetime — and pin the graveyard
# contract with weakrefs: removed wrappers must stay ALIVE through the pending
# update flush and die only after the next event-loop iteration.


@pytest.mark.gui
def test_undo_style_commit_with_dropped_refs_no_crash(qtbot, tmp_path) -> None:
    """G-07-6 regression: Ctrl+Z after a style commit must NOT drop the last
    BoxItem refs synchronously inside on_undo (the teardown UAF).

    Mirrors the app lifetime: style-commit a multi-selection (queues overlay
    updates), drop EVERY wrapper ref except the canvas's own ``_box_items``,
    then ``on_undo()`` WITHOUT an event-loop flush. The graveyard must hold
    the removed wrappers through the pending UpdateRequest flush (weakrefs
    ALIVE); the FOLLOWING ``processEvents()`` releases them (weakrefs DEAD).
    The rebuild restores the exact pre-commit snapshot.
    """
    from manga_ai_studio.core.text_style import TextStyle

    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 60, 60), Box(80, 20, 60, 60)]
    )
    items[0].pagebox.style = TextStyle(color="#ff0000")
    items[1].pagebox.style = TextStyle(color="#0000ff")
    items[0].setSelected(True)
    items[1].setSelected(True)
    QApplication.processEvents()

    # ONE style commit (queues overlay updates per selected box — the UAF
    # precondition) + ONE BOXES snapshot pushed. The commit emits the
    # canonical HexArgb spelling (quick-260909-nj9 normalization).
    window.inspector_panel._commit_style_color("#00ff00")
    QApplication.processEvents()
    assert items[0].pagebox.style.color == "#ff00ff00"
    assert items[1].pagebox.style.color == "#ff00ff00"

    # App lifetime: capture weakrefs, then drop EVERY wrapper ref — the
    # canvas's _box_items becomes the only strong reference (what the app's
    # undo path sees at Ctrl+Z time).
    wrs = [weakref.ref(it) for it in items]
    del items

    # Ctrl+Z WITHOUT an event-loop flush. Pre-fix, set_boxes drops _box_items
    # synchronously -> the wrappers die INSIDE on_undo (RED — the exact
    # teardown the crash diagnosis describes). The graveyard fix holds them.
    window.on_undo()
    assert all(wr() is not None for wr in wrs), (
        "removed BoxItems must stay alive through the pending update flush "
        "(graveyard contract) - set_boxes must not drop the last refs "
        "synchronously mid-event-loop"
    )

    # The next event-loop iteration flushes the queued updates (painting live
    # items) and then fires the graveyard release timer -> wrappers die.
    QApplication.processEvents()
    assert all(wr() is None for wr in wrs), (
        "the graveyard must release removed wrappers after the update flush "
        "(next event-loop iteration)"
    )

    # The rebuild restored the exact pre-commit snapshot (detached styles).
    restored = [it.pagebox for it in window.canvas._box_items]
    assert len(restored) == 2
    assert restored[0].style.color == "#ff0000"
    assert restored[1].style.color == "#0000ff"


@pytest.mark.gui
def test_delete_with_dropped_refs_no_crash(qtbot, tmp_path) -> None:
    """G-07-6 delete-path variant: Delete after a style commit must retire the
    removed item through the SAME graveyard (no second drop-the-last-ref site).

    Style-commit a box (queues overlay updates), drop every wrapper ref, drive
    the real Delete key handler — the weakref must be ALIVE immediately after
    (the graveyard holds the item through the pending flush) and DEAD after
    ``processEvents()``. One undo restores the box to the pre-delete state.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from manga_ai_studio.core.text_style import TextStyle

    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    items = _seed_boxes_window(window, [Box(10, 20, 80, 80)])
    item = items[0]
    item.pagebox.style = TextStyle(color="#ff0000")
    item.setSelected(True)
    QApplication.processEvents()

    # Style commit (queues overlay updates — the UAF precondition). The
    # commit emits the canonical HexArgb spelling (quick-260909-nj9).
    window.inspector_panel._commit_style_color("#00ff00")
    QApplication.processEvents()
    assert item.pagebox.style.color == "#ff00ff00"

    # Drop EVERY wrapper ref except the canvas's _box_items.
    wr = weakref.ref(item)
    del items, item

    # Delete key without a flush: pre-fix the wrapper dies when the key
    # handler returns (synchronous last-ref drop); the fix retires it to the
    # graveyard -> alive.
    del_key = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
    )
    canvas.keyPressEvent(del_key)
    assert wr() is not None, (
        "the deleted item must stay alive through the pending update flush "
        "(graveyard contract) - _remove_box must not drop the last ref "
        "synchronously"
    )

    # Next event-loop iteration: updates flushed on live items, then the
    # graveyard release timer drops the wrapper.
    QApplication.processEvents()
    assert wr() is None, "the graveyard must release the deleted item post-flush"

    # One undo restores the box to the PRE-DELETE state (the committed style).
    window.on_undo()
    QApplication.processEvents()
    assert canvas.box_count() == 1
    restored = canvas._box_items[0].pagebox
    assert restored.style.color == "#ff00ff00"


@pytest.mark.gui
def test_graveyard_release_against_invalidated_wrapper_safe(
    qtbot, tmp_path
) -> None:
    """WR-03 (07-REVIEW-GAPS): the graveyard release timer can fire against
    a canvas wrapper whose C++ object was deleted at teardown (a box removal
    followed by window close in the same event-loop iteration). The
    ``Shiboken.isValid`` guard (the paint-path belt-and-suspenders pattern,
    box_item.py) must skip the release instead of raising ``RuntimeError``
    from inside the event loop — and must leave the dead wrapper's state
    untouched (the alive path below still drains normally)."""
    from PySide6 import Shiboken
    from PySide6.QtCore import QTimer

    window = _window_with_page(qtbot, tmp_path)
    canvas = window.canvas
    items = _seed_boxes_window(window, [Box(10, 20, 60, 60)])
    del items

    # A pending graveyard batch: retire a box WITHOUT letting the timer fire.
    canvas._retire_boxes([canvas._box_items[0]])
    assert canvas._graveyard_pending is True
    assert len(canvas._box_graveyard) == 1

    # Teardown: the canvas's C++ object is deleted by its QObject parent
    # chain — the Python wrapper survives but is invalidated; the pending
    # singleShot(0) will fire against it on the next event-loop iteration.
    Shiboken.delete(canvas)
    assert Shiboken.isValid(canvas) is False

    # The direct callback must no-op — not raise — and must leave the dead
    # wrapper's attributes untouched (the release is skipped entirely).
    canvas._release_graveyard()
    assert canvas._graveyard_pending is True
    assert len(canvas._box_graveyard) == 1

    # The timer path (the exact WR-03 shape): firing the 0ms timer against
    # the invalidated wrapper raises no RuntimeError from the event loop.
    QTimer.singleShot(0, canvas._release_graveyard)
    QApplication.processEvents()

    # The alive path is unchanged: a fresh canvas drains the graveyard on
    # the next event-loop iteration (the 07-06 lifetime contract). The real
    # removal site (``_remove_box``) drops the item from the scene + list
    # and retires it — the graveyard holds the last ref through the flush.
    window2 = _window_with_page(qtbot, tmp_path)
    canvas2 = window2.canvas
    items2 = _seed_boxes_window(window2, [Box(10, 20, 60, 60)])
    wr = weakref.ref(items2[0])
    del items2
    canvas2._remove_box(canvas2._box_items[0])
    assert wr() is not None, "the graveyard holds the removed wrapper"
    QApplication.processEvents()
    assert wr() is None, (
        "the graveyard must still release wrappers on the alive path (WR-03)"
    )


# ===========================================================================
# quick-260822-gnq — regression guards for the cleaning-canvas bugs:
# (1) move/touch no longer nukes + re-runs detection (per-box re-run
#     affordance + geometry-stale marking; quick-260824-pqn removed the
#     stationary-grace auto-dispatch — re-detect is manual-only);
# (2) scrolling leaves no phantom brush strokes;
# (3) Move/Pan shows no brush-dot cursor.
# All tests are hermetic: the dispatch/refit engines are stubbed at the
# MainWindow seam — never a model load, never network.
# ===========================================================================


def _stub_engines(window: MainWindow, monkeypatch) -> tuple[list, list]:
    """Stub _refit_changed_boxes + _dispatch_ocr_for_box with recorders.

    Returns ``(refit_calls, ocr_calls)``; each entry is the before-snapshot /
    BoxItem argument respectively. The instance-attribute stub intercepts
    both direct calls and the internal self.* dispatch in
    ``_redetect_single_box``.
    """
    refit_calls: list = []
    ocr_calls: list = []
    monkeypatch.setattr(
        window, "_refit_changed_boxes", lambda before: refit_calls.append(before)
    )
    monkeypatch.setattr(
        window, "_dispatch_ocr_for_box", lambda item: ocr_calls.append(item)
    )
    return refit_calls, ocr_calls


def _commit_move(window: MainWindow, item, dx: float, dy: float) -> None:
    """Move ``item`` and run the REAL commit flow (setRect + boxes_modified)."""
    canvas = window.canvas
    before = canvas.boxes_snapshot()
    r = item.rect()
    item.setRect(r.translated(dx, dy))
    item._sync_handles()
    canvas.boxes_modified.emit(before)


@pytest.mark.gui
def test_move_commit_does_not_refit(qtbot, tmp_path, monkeypatch) -> None:
    """Guard 1a: a committed box move emits boxes_modified but performs ZERO
    refit work — the sentinel recorder sees no call and the box is marked
    geometry-stale instead (quick-260822-gnq annoyance core)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    refit_calls, _ocr = _stub_engines(window, monkeypatch)
    modified: list = []
    window.canvas.boxes_modified.connect(lambda snap: modified.append(snap))

    # A REAL drag through the canvas move path.
    canvas = window.canvas
    canvas.mousePressEvent(_press_at(canvas, 40, 50))  # inside the box body
    canvas.mouseMoveEvent(_move_at(canvas, 60, 70))
    canvas.mouseReleaseEvent(_release_at(canvas, 60, 70))

    assert len(modified) == 1, "the commit must emit boxes_modified"
    assert refit_calls == [], "move commit must NOT trigger any refit"
    assert item.geometry_stale is True, "moved box must be marked stale"


@pytest.mark.gui
def test_commit_move_marks_stale_starts_nothing(qtbot, tmp_path, monkeypatch) -> None:
    """quick-260824-pqn replacement for the grace-dispatch battery: a
    committed box move marks the item geometry-stale and dispatches NOTHING
    — no timer exists to fire, so even after processing events the refit/OCR
    recorders stay empty."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    refit_calls, ocr_calls = _stub_engines(window, monkeypatch)

    _commit_move(window, item, 20, 0)
    assert item.geometry_stale is True
    # Advance the event loop well past any legacy grace window: with the
    # timer machinery removed there is nothing left to dispatch.
    qtbot.wait(150)
    QApplication.processEvents()
    assert refit_calls == [] and ocr_calls == []


@pytest.mark.gui
def test_redetect_click_noop_when_not_stale(qtbot, tmp_path, monkeypatch) -> None:
    """quick-260824-pqn: the corner re-detect affordance fires only when the
    bubble exists AND is geometry-stale — a click on a fresh/non-moved box
    is a no-op (no refit, no OCR)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    refit_calls, ocr_calls = _stub_engines(window, monkeypatch)

    assert item.geometry_stale is False
    window.canvas.box_redetect_requested.emit(item)
    QApplication.processEvents()
    assert refit_calls == [] and ocr_calls == []
    assert item.geometry_stale is False


@pytest.mark.gui
def test_redetect_click_runs_when_stale(qtbot, tmp_path, monkeypatch) -> None:
    """quick-260824-pqn: on a geometry-stale bubble the affordance click runs
    exactly ONE OCR dispatch (plus the refit leg) and clears the stale
    marker."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    refit_calls, ocr_calls = _stub_engines(window, monkeypatch)

    _commit_move(window, item, 20, 0)
    assert item.geometry_stale is True
    window.canvas.box_redetect_requested.emit(item)
    QApplication.processEvents()
    assert len(refit_calls) == 1
    assert len(ocr_calls) == 1
    assert item.geometry_stale is False


# ---- quick-260822-vk7 deferral tests REMOVED (quick-260824-pqn): with the
# stationary-grace timer gone there is nothing to defer — typing/editing
# never triggers detection work by construction.


@pytest.mark.gui
def test_redetect_affordance_click_refits_with_current_geometry(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Guard 1e: invoking the corner re-run affordance dispatches OCR with
    the box's POST-move geometry (current_box()), never the birth
    pagebox.box (STATE.md Phase 08 follow-up)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    refit_calls: list = []
    # Stub ONLY the refit engine — the REAL dispatch engine runs so we can
    # inspect the Box that crosses the thread boundary.
    monkeypatch.setattr(
        window, "_refit_changed_boxes", lambda before: refit_calls.append(before)
    )

    # Real dispatch engine, but a recorded worker task so we can inspect the
    # Box that crosses the thread boundary (backend/model fully faked).
    ocr_boxes: list = []

    def fake_task(image_path, box_xyxy, model, box_id=None,
                  progress_callback=None, abort_flag=None):
        ocr_boxes.append((box_xyxy, box_id))
        return {"text": "現", "box_id": box_id}

    monkeypatch.setattr(window, "_run_ocr_task", fake_task)
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: object(),
    )
    monkeypatch.setattr("panelcleaner.model_downloader.is_ocr_downloaded", lambda: True)

    birth = item.pagebox.box.as_tuple
    _commit_move(window, item, 30, 10)
    moved_now = item.current_box().as_tuple
    assert moved_now != birth

    # The affordance click path: emit the CANVAS-level signal with the item.
    window.canvas.box_redetect_requested.emit(item)
    qtbot.waitUntil(lambda: len(ocr_boxes) == 1, timeout=5000)
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert len(refit_calls) == 1
    box, routing_id = ocr_boxes[0]
    assert box.as_tuple == moved_now, "OCR must receive POST-move geometry"
    assert box.as_tuple != birth
    assert routing_id == id(item.pagebox), "routing id must be id(pagebox)"
    assert item.geometry_stale is False


@pytest.mark.gui
def test_edited_box_not_reocred_on_redetect(qtbot, tmp_path, monkeypatch) -> None:
    """Guard 1f (T-QG-03): a moved box carrying hand-edited recognized text
    gets its fit refreshed but its OCR leg SKIPPED — silent overwrite is
    reserved for raw/never-recognized text. quick-260824-pqn: the trigger is
    the manual affordance click (the grace auto-dispatch no longer exists)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _add_user_box_window(window, Box(10, 20, 80, 80))
    item.pagebox.set_recognized_text_edited("手書き")
    refit_calls, ocr_calls = _stub_engines(window, monkeypatch)

    _commit_move(window, item, 15, 0)  # marks the box stale
    assert item.geometry_stale is True
    window.canvas.box_redetect_requested.emit(item)
    QApplication.processEvents()
    assert len(refit_calls) == 1, "the fit refresh still runs"
    assert ocr_calls == [], "edited text must never be silently re-OCRed"
    assert item.geometry_stale is False


@pytest.mark.gui
def test_cursor_hidden_for_move_and_crop_visible_for_paint_tools(qtbot) -> None:
    """Guards 2+3 (cursor): set_tool across ALL six ToolModes — cursor_item
    visibility matches membership in {BRUSH, RECTANGLE, LASSO, ERASER, RESTORE}."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    paint_tools = {
        ToolMode.BRUSH,
        ToolMode.RECTANGLE,
        ToolMode.LASSO,
        ToolMode.ERASER,
        ToolMode.RESTORE,  # the 7th tool (quick-260828-l3l) shows the circle
    }
    for tool in ToolMode:
        canvas.set_tool(tool)
        expected = tool in paint_tools
        assert canvas.cursor_item.isVisible() is expected, (
            f"cursor visibility wrong for {tool}"
        )


@pytest.mark.gui
def test_no_ghost_after_undo_and_scroll(qtbot) -> None:
    """Guard 2 (ghost): after painting a stroke and undoing it via
    apply_undo_mask, a wheel scroll AND a Ctrl+wheel zoom leave NO residual
    stroke pixels in the viewport grab. FullViewportUpdate is the structural
    guarantee — asserted alongside."""
    from manga_ai_studio.core.mask_editor import paint_mask_stroke
    from manga_ai_studio.core.mask_planes import MaskPlanesSnapshot

    canvas = _canvas_with_image_and_boxes(qtbot, size=200)
    from PySide6.QtWidgets import QGraphicsView

    assert (
        canvas.viewportUpdateMode()
        == QGraphicsView.ViewportUpdateMode.FullViewportUpdate
    )

    # Paint a stroke programmatically into the displayed mask.
    canvas.set_tool(ToolMode.BRUSH)
    paint_mask_stroke(
        canvas.get_mask(), QPointF(100, 100), QPointF(115, 100),
        canvas.brush_size, False,
    )
    canvas.update_mask_display()
    QApplication.processEvents()

    # Sanity: the stroke IS visible before the undo (red tint drops G/B).
    pre = QColor(canvas.viewport().grab().toImage().pixel(
        canvas.mapFromScene(QPointF(107, 100))
    ))
    assert pre.green() < 200 and pre.blue() < 200, "stroke should be visible"

    # Restore a CLEAN plane snapshot via the real undo application path
    # (quick-260907-sni: the snapshot value is the packed triple — zeros
    # packed manual/erase + dims).
    import numpy as np

    n_packed = (200 * 200 + 7) // 8
    canvas.apply_undo_mask(
        MaskPlanesSnapshot(
            manual_packed=np.zeros(n_packed, dtype=np.uint8),
            erase_packed=np.zeros(n_packed, dtype=np.uint8),
            auto_packed=None,
            dims=(200, 200),
        )
    )

    def _wheel(angle: int, ctrl: bool) -> None:
        vp = canvas.mapFromScene(QPointF(107, 100))
        mods = (
            Qt.KeyboardModifier.ControlModifier if ctrl
            else Qt.KeyboardModifier.NoModifier
        )
        ev = QWheelEvent(
            QPointF(vp),
            QPointF(canvas.mapToGlobal(vp)),
            QPoint(0, 0),
            QPoint(0, angle),
            Qt.MouseButton.NoButton,
            mods,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        canvas.wheelEvent(ev)
        QApplication.processEvents()

    # Plain scroll down/up + Ctrl+wheel zoom in/out; after each, the stroke
    # center pixel must show NO mask-overlay red (no resurrected ghost).
    for ctrl in (False, True):
        for angle in (-120, 120):
            _wheel(angle, ctrl=ctrl)
            px = QColor(canvas.viewport().grab().toImage().pixel(
                canvas.mapFromScene(QPointF(107, 100))
            ))
            assert px.green() > 200 and px.blue() > 200, (
                f"ghost stroke pixels visible after wheel (ctrl={ctrl}, "
                f"angle={angle})"
            )


# ===========================================================================
# quick-260907-m4u — Ctrl+click a bubble (Move tool) copies its DETECTED text
# ===========================================================================
#
# The canvas extracts and emits (copy_text_requested(str)); MainWindow owns
# the clipboard (gui/ocr_grab.py:19 discipline). These tests cover the canvas
# side: the detected_text helper + the Ctrl branch in mousePressEvent's
# non-paint box arm. Every other interaction must stay byte-identical.


def _copy_test_canvas(qtbot, pb: PageBox):
    """Canvas with one user box added via the real set_boxes seam + MOVE active."""
    canvas = _canvas_with_image_and_boxes(qtbot)
    canvas.set_tool(ToolMode.MOVE)
    canvas.set_boxes(user_pageboxes=[pb], detected_pageboxes=[])
    QApplication.processEvents()
    return canvas, canvas._box_items[-1]


@pytest.mark.gui
def test_detected_text_reads_recognized_text_only(qtbot) -> None:
    """detected_text: recognized text ONLY — translation is NEVER read."""
    from manga_ai_studio.gui.text_renderer import detected_text

    # Recognized str text comes back verbatim.
    pb = PageBox(box=Box(10, 10, 60, 60), origin=USER)
    pb.set_recognized_text("\u30cf\u30ed\u30fc")
    assert detected_text(pb) == "\u30cf\u30ed\u30fc"

    # Never-OCR'd box (payload None) -> "".
    assert detected_text(PageBox(box=Box(0, 0, 10, 10), origin=USER)) == ""

    # List-shaped payload.text -> join+strip (current_focus_text's defensive shape).
    pb_list = PageBox(box=Box(0, 0, 10, 10), origin=USER)
    pb_list._ensure_payload()
    pb_list.payload.text = ["a", "b"]
    assert detected_text(pb_list) == "ab"

    # Translation set but recognized text empty -> "" (translation never leaks).
    pb_tr = PageBox(box=Box(0, 0, 10, 10), origin=USER)
    pb_tr.set_translation("\u7ffb\u8a33")
    assert detected_text(pb_tr) == ""
    # Whitespace-only recognized text strips to "".
    pb_ws = PageBox(box=Box(0, 0, 10, 10), origin=USER)
    pb_ws.set_recognized_text("   ")
    assert detected_text(pb_ws) == ""


@pytest.mark.gui
def test_ctrl_click_move_copies_detected_text(qtbot) -> None:
    """Ctrl+click (MOVE) on an OCR'd box emits copy_text_requested with the
    exact recognized text; the box is selected and NO move drag is armed."""
    pb = PageBox(box=Box(10, 10, 60, 60), origin=USER)
    pb.set_recognized_text("copied text")
    canvas, item = _copy_test_canvas(qtbot, pb)

    emitted: list[str] = []
    canvas.copy_text_requested.connect(emitted.append)

    canvas.mousePressEvent(_press_at(canvas, 40, 40, ctrl=True))
    QApplication.processEvents()

    assert emitted == ["copied text"]
    assert item.isSelected() is True
    assert canvas._moving_box is None

    canvas.mouseReleaseEvent(_release_at(canvas, 40, 40))


@pytest.mark.gui
def test_ctrl_click_move_wins_over_shift(qtbot) -> None:
    """Ctrl wins over Shift on the Move-tool box arm: Ctrl+Shift+click copies
    (the Shift-toggle branch never runs)."""
    pb = PageBox(box=Box(10, 10, 60, 60), origin=USER)
    pb.set_recognized_text("copied text")
    canvas, item = _copy_test_canvas(qtbot, pb)

    emitted: list[str] = []
    canvas.copy_text_requested.connect(emitted.append)

    vp = canvas.mapFromScene(QPointF(40, 40))
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    canvas.mousePressEvent(ev)
    QApplication.processEvents()

    assert emitted == ["copied text"]
    assert item.isSelected() is True
    assert canvas._moving_box is None

    canvas.mouseReleaseEvent(_release_at(canvas, 40, 40))


@pytest.mark.gui
def test_ctrl_click_move_on_payload_none_box_emits_empty(qtbot) -> None:
    """Ctrl+click (MOVE) on a never-OCR'd box emits copy_text_requested("")
    — the canvas stays dumb; the receiver decides empty feedback."""
    canvas, item = _copy_test_canvas(
        qtbot, PageBox(box=Box(10, 10, 60, 60), origin=USER)
    )

    emitted: list[str] = []
    canvas.copy_text_requested.connect(emitted.append)

    canvas.mousePressEvent(_press_at(canvas, 40, 40, ctrl=True))
    QApplication.processEvents()

    assert emitted == [""]
    assert item.isSelected() is True
    assert canvas._moving_box is None

    canvas.mouseReleaseEvent(_release_at(canvas, 40, 40))


@pytest.mark.gui
def test_plain_click_move_arms_drag_and_emits_nothing(qtbot) -> None:
    """Today's behavior intact: a plain click (no Ctrl) under MOVE emits
    nothing and arms the move drag."""
    pb = PageBox(box=Box(10, 10, 60, 60), origin=USER)
    pb.set_recognized_text("copied text")
    canvas, item = _copy_test_canvas(qtbot, pb)

    emitted: list[str] = []
    canvas.copy_text_requested.connect(emitted.append)

    canvas.mousePressEvent(_press_at(canvas, 40, 40))
    QApplication.processEvents()

    assert emitted == []
    assert canvas._moving_box is item
    assert item.isSelected() is True

    canvas.mouseReleaseEvent(_release_at(canvas, 40, 40))


@pytest.mark.gui
def test_ctrl_click_on_corner_handle_never_copies(qtbot) -> None:
    """A CornerHandle hit is a resize gesture, NOT a copy — the Ctrl branch
    only fires on the BoxItem arm."""
    pb = PageBox(box=Box(10, 10, 60, 60), origin=USER)
    pb.set_recognized_text("copied text")
    canvas, item = _copy_test_canvas(qtbot, pb)

    # Select first so the corner handles are visible.
    canvas.mousePressEvent(_press_at(canvas, 40, 40))
    canvas.mouseReleaseEvent(_release_at(canvas, 40, 40))
    QApplication.processEvents()
    assert item.isSelected() is True

    emitted: list[str] = []
    canvas.copy_text_requested.connect(emitted.append)

    canvas.mousePressEvent(_press_at(canvas, 10, 10, ctrl=True))
    QApplication.processEvents()

    assert emitted == []
    assert canvas._resizing_box is not None

    canvas.mouseReleaseEvent(_release_at(canvas, 10, 10))


@pytest.mark.gui
def test_ctrl_click_under_paint_tool_emits_nothing(qtbot) -> None:
    """MASK-06 preserved: under a paint tool (RECTANGLE) Ctrl+click still
    paints — the box branch falls through and NOTHING is emitted."""
    pb = PageBox(box=Box(10, 10, 60, 60), origin=USER)
    pb.set_recognized_text("copied text")
    canvas, _item = _copy_test_canvas(qtbot, pb)
    canvas.set_tool(ToolMode.RECTANGLE)

    emitted: list[str] = []
    canvas.copy_text_requested.connect(emitted.append)

    canvas.mousePressEvent(_press_at(canvas, 40, 40, ctrl=True))
    QApplication.processEvents()

    assert emitted == []
    assert canvas._moving_box is None

    canvas.mouseReleaseEvent(_release_at(canvas, 40, 40))



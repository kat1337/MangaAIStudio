"""GUI tests for the textbox-overlay bug fixes (quick-260909-fa9).

Three bugs, one battery:

- **BUG-1 (zoom-adaptive border):** the border pen width is compensated by the
  live zoom (``_zoom_pen_width``) so the ON-SCREEN thickness stays ~2 viewport
  px unselected / ~3 selected at every zoom — clearly visible when zoomed out,
  proportionally thinner on screen when zoomed in.
- **BUG-2 (corner-exact anchoring):** the ``ItemIgnoresTransformations``
  decorations (corner handles, rotation handle, re-detect button, badge) anchor
  their device-px offsets through ``offset / zoom`` so they sit EXACTLY on
  their box corners at every zoom, and boxes created at a non-1 canvas zoom are
  seeded with that zoom at registration.
- **BUG-3 (arrow-key nudge):** with the Move (V) tool active, arrow keys nudge
  every selected box 1 scene px per press (key-repeat keeps nudging), with ONE
  ``boxes_modified`` emission per burst carrying the BEFORE-burst snapshot.

Mirrors the ``tests/test_gui_boxes.py`` header (``pytest.importorskip`` +
``qtbot`` fixture + ``@pytest.mark.gui``). These tests need a display; on
headless CI they skip via ``importorskip``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QTransform  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.core.mask_editor import ToolMode  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.box_item import (  # noqa: E402
    _BADGE_OFFSET,
    _HANDLE_HIT_SIZE,
    _HANDLE_SIZE,
    _INPAINT_DASH_PATTERN,
    _REDETECT_OFFSET,
    _REDETECT_SIZE,
    _ROTATE_ABOVE_TL,
    _ROTATE_SIZE,
    _handle_hit_rect,
    BoxItem,
    CornerHandle,
)
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402


def _scene_with_box(pagebox: PageBox) -> tuple[QGraphicsScene, BoxItem]:
    """Build a minimal scene owning a BoxItem (selection needs scene membership).

    Mirrors tests/test_gui_boxes.py:65.
    """
    scene = QGraphicsScene()
    item = BoxItem(pagebox)
    scene.addItem(item)
    return scene, item


def _select(scene: QGraphicsScene, item: BoxItem) -> None:
    """Select ``item`` in its scene (selection needs scene membership)."""
    scene.clearSelection()
    item.setSelected(True)
    assert item.isSelected() is True


def _apply_zoom_and_sync(item: BoxItem, zoom: float) -> None:
    """The canvas zoom-slot sequence: store the zoom, then re-sync decorations.

    ``EditorCanvas._on_zoom_changed_reposition_handles`` calls
    ``apply_overlay_zoom(zoom)`` BEFORE ``_sync_handles`` — reposition consumes
    the STORED zoom, so the item-level mirror must keep the same order.
    """
    item.apply_overlay_zoom(zoom)
    item._sync_handles()


def _canvas_with_image(qtbot, size: int = 200) -> EditorCanvas:
    """Build a shown canvas with an image (the test_gui_boxes.py:263 shape)."""
    from PySide6.QtGui import QColor, QImage, QPixmap

    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 400)
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    canvas.set_image(QPixmap.fromImage(img))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    return canvas


def _press_at(canvas: EditorCanvas, x: int, y: int, modifier=Qt.KeyboardModifier.NoModifier):
    """Synthesize a left mouse press at VIEWPORT coords (x, y)."""
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(x, y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifier,
    )


def _key(event_type: QEvent.Type, key: Qt.Key, auto_repeat: bool = False) -> QKeyEvent:
    """Synthesize a QKeyEvent (the tests/test_gui_boxes.py:487 precedent)."""
    return QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier, "", auto_repeat, 1)


# ===========================================================================
# BUG-1 — zoom-adaptive border pen (Task 1)
# ===========================================================================


@pytest.mark.gui
class TestZoomPenWidthHelper:
    """The module helper: scene width = base / zoom, guarded + capped."""

    def test_zoom_out_multiplies_scene_width(self) -> None:
        from manga_ai_studio.gui.box_item import _zoom_pen_width

        assert _zoom_pen_width(2.0, 0.25) == pytest.approx(8.0)
        assert _zoom_pen_width(3.0, 0.25) == pytest.approx(12.0)

    def test_zoom_in_divides_scene_width(self) -> None:
        from manga_ai_studio.gui.box_item import _zoom_pen_width

        assert _zoom_pen_width(2.0, 4.0) == pytest.approx(0.5)

    def test_zoom_one_is_identity(self) -> None:
        from manga_ai_studio.gui.box_item import _zoom_pen_width

        assert _zoom_pen_width(2.0, 1.0) == pytest.approx(2.0)
        assert _zoom_pen_width(3.0, 1.0) == pytest.approx(3.0)

    def test_non_positive_zoom_falls_back_to_zoom_one(self) -> None:
        from manga_ai_studio.gui.box_item import _zoom_pen_width

        assert _zoom_pen_width(2.0, 0) == pytest.approx(2.0)
        assert _zoom_pen_width(2.0, -3.0) == pytest.approx(2.0)
        assert _zoom_pen_width(3.0, 0) == pytest.approx(3.0)

    def test_degenerate_zoom_in_cap(self) -> None:
        from manga_ai_studio.gui.box_item import _PEN_MAX_SCENE_WIDTH, _zoom_pen_width

        # 2 / 100 scene px at MAX_ZOOM would be the constant on-screen minimum
        # — but the helper CAPS the scene width so an absurd zoom-out input
        # (e.g. 0.001) cannot balloon the pen to 2000 scene px.
        assert _zoom_pen_width(2.0, 0.001) == pytest.approx(_PEN_MAX_SCENE_WIDTH)


@pytest.mark.gui
def test_unselected_pen_compensates_after_apply_overlay_zoom(qtbot) -> None:
    """An unselected box's pen re-derives through the stored zoom."""
    _scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=DETECTED))
    item.apply_overlay_zoom(0.25)
    assert item.pen().widthF() == pytest.approx(8.0)
    item.apply_overlay_zoom(4.0)
    assert item.pen().widthF() == pytest.approx(0.5)


@pytest.mark.gui
def test_selected_pen_compensates_after_apply_overlay_zoom(qtbot) -> None:
    """A selected box's pen re-derives through the stored zoom (3 vp px)."""
    scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=DETECTED))
    _select(scene, item)
    item.apply_overlay_zoom(0.25)
    assert item.pen().widthF() == pytest.approx(12.0)


@pytest.mark.gui
@pytest.mark.parametrize("zoom", [0.25, 0.5, 1.0, 2.0, 4.0])
def test_unselected_on_screen_thickness_invariant(qtbot, zoom) -> None:
    """On-screen thickness = pen().widthF() * zoom stays ~2 vp px at any zoom."""
    _scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=DETECTED))
    item.apply_overlay_zoom(zoom)
    assert item.pen().widthF() * zoom == pytest.approx(2.0, abs=0.25)


@pytest.mark.gui
@pytest.mark.parametrize("zoom", [0.25, 0.5, 1.0, 2.0, 4.0])
def test_selected_on_screen_thickness_invariant(qtbot, zoom) -> None:
    """On-screen thickness = pen().widthF() * zoom stays ~3 vp px at any zoom."""
    scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=DETECTED))
    _select(scene, item)
    item.apply_overlay_zoom(zoom)
    assert item.pen().widthF() * zoom == pytest.approx(3.0, abs=0.25)


@pytest.mark.gui
def test_dashed_inpaint_state_keeps_dash_pattern_while_width_compensates(qtbot) -> None:
    """A dashed ("never") border keeps the fixed [6.0, 4.0] dash pattern —
    Qt dash units are multiples of the pen width, so the dash automatically
    rides the compensated width."""
    _scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=DETECTED))
    item.set_inpaint_state("never")
    item.apply_overlay_zoom(0.25)
    assert item.pen().dashPattern() == _INPAINT_DASH_PATTERN
    assert item.pen().widthF() == pytest.approx(8.0)


@pytest.mark.gui
def test_pen_width_at_default_zoom_is_byte_identical(qtbot) -> None:
    """The zoom-1.0 result stays exactly 2/3 (D-BUG1: the existing suite must
    pass unchanged)."""
    scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=DETECTED))
    assert item.pen().widthF() == pytest.approx(2.0)
    _select(scene, item)
    assert item.pen().widthF() == pytest.approx(3.0)


# ===========================================================================
# BUG-2 — corner-exact anchoring for handles / buttons / badge at every zoom
# (Task 2)
# ===========================================================================

_ZOOMS = [0.25, 0.5, 1.0, 2.0, 4.0]


def _corner_point(rect: QRectF, corner: str) -> QPointF:
    return {
        "TL": rect.topLeft(),
        "TR": rect.topRight(),
        "BL": rect.bottomLeft(),
        "BR": rect.bottomRight(),
    }[corner]


@pytest.mark.gui
@pytest.mark.parametrize("zoom", _ZOOMS)
@pytest.mark.parametrize("corner", ["TL", "TR", "BL", "BR"])
def test_corner_handle_anchored_on_corner_at_every_zoom(qtbot, corner, zoom) -> None:
    """Every corner handle's scenePos equals corner - 4/zoom per axis, and its
    hit-zone CENTER maps back onto the exact corner (BUG-2)."""
    scene, item = _scene_with_box(PageBox(box=Box(100, 80, 300, 260), origin=DETECTED))
    _select(scene, item)
    _apply_zoom_and_sync(item, zoom)

    rect = item.rect()
    handle = item.handles[corner]
    half = _HANDLE_SIZE / 2.0 / zoom
    corner_pt = _corner_point(rect, corner)
    pos = handle.scenePos()
    assert pos.x() == pytest.approx(corner_pt.x() - half, abs=1e-6)
    assert pos.y() == pytest.approx(corner_pt.y() - half, abs=1e-6)

    # The zoom-divided hit zone stays centred on the TRUE scene corner: the
    # local hit-rect centre maps through the handle's transform back onto the
    # corner point.
    hit_center_scene = handle.mapToScene(_handle_hit_rect(zoom).center())
    assert hit_center_scene.x() == pytest.approx(corner_pt.x(), abs=1e-6)
    assert hit_center_scene.y() == pytest.approx(corner_pt.y(), abs=1e-6)


@pytest.mark.gui
@pytest.mark.parametrize("zoom", _ZOOMS)
def test_handle_hit_rect_center_moves_with_zoom(qtbot, zoom) -> None:
    """The hit-rect centre is local (4/zoom, 4/zoom) — not (4, 4) — while the
    width*zoom contract stays ~_HANDLE_HIT_SIZE viewport px (260824-t64)."""
    r = _handle_hit_rect(zoom)
    assert r.width() * zoom == pytest.approx(_HANDLE_HIT_SIZE, abs=1.0)
    c = r.center()
    assert c.x() == pytest.approx(_HANDLE_SIZE / 2.0 / zoom, abs=1e-6)
    assert c.y() == pytest.approx(_HANDLE_SIZE / 2.0 / zoom, abs=1e-6)


@pytest.mark.gui
@pytest.mark.parametrize("zoom", _ZOOMS)
def test_rotation_handle_anchored_above_tl_at_every_zoom(qtbot, zoom) -> None:
    """The rotation handle's pos equals (left - 5/zoom, top - 23/zoom); its
    CENTER sits exactly 18 viewport px above the TL corner (BUG-2)."""
    scene, item = _scene_with_box(PageBox(box=Box(100, 80, 300, 260), origin=USER))
    _select(scene, item)
    _apply_zoom_and_sync(item, zoom)

    rect = item.rect()
    rh = item._rotation_handle
    pos = rh.scenePos()
    assert pos.x() == pytest.approx(rect.left() - _ROTATE_SIZE / 2.0 / zoom, abs=1e-6)
    assert pos.y() == pytest.approx(
        rect.top() - (_ROTATE_ABOVE_TL + _ROTATE_SIZE / 2.0) / zoom, abs=1e-6
    )
    # On-screen (viewport-px) center: (pos + half) * zoom = corner + (0, -18).
    vx = pos.x() * zoom + _ROTATE_SIZE / 2.0
    vy = pos.y() * zoom + _ROTATE_SIZE / 2.0
    assert vx == pytest.approx(rect.left() * zoom, abs=1e-6)
    assert vy == pytest.approx(rect.top() * zoom - _ROTATE_ABOVE_TL, abs=1e-6)


@pytest.mark.gui
def test_rotation_handle_anchor_byte_identical_at_zoom_one(qtbot) -> None:
    """At z=1 the rotation anchor equals today's fixed values exactly."""
    scene, item = _scene_with_box(PageBox(box=Box(100, 80, 300, 260), origin=USER))
    _select(scene, item)
    _apply_zoom_and_sync(item, 1.0)
    rect = item.rect()
    pos = item._rotation_handle.scenePos()
    assert pos.x() == pytest.approx(rect.left() - 5.0, abs=1e-9)
    assert pos.y() == pytest.approx(rect.top() - 23.0, abs=1e-9)


@pytest.mark.gui
@pytest.mark.parametrize("zoom", _ZOOMS)
def test_redetect_handle_anchored_outside_tr_at_every_zoom(qtbot, zoom) -> None:
    """The re-detect button's pos equals (right + 2/zoom, top - 12/zoom); its
    LEFT edge sits exactly 2 viewport px outside the TR corner (BUG-2)."""
    scene, item = _scene_with_box(PageBox(box=Box(100, 80, 300, 260), origin=USER))
    _select(scene, item)
    _apply_zoom_and_sync(item, zoom)

    rect = item.rect()
    rh = item._redetect
    pos = rh.scenePos()
    assert pos.x() == pytest.approx(rect.right() + _REDETECT_OFFSET / zoom, abs=1e-6)
    assert pos.y() == pytest.approx(
        rect.top() - (_REDETECT_SIZE + _REDETECT_OFFSET) / zoom, abs=1e-6
    )
    # On-screen left edge: pos.x * zoom = right*zoom + 2 viewport px outside.
    assert pos.x() * zoom == pytest.approx(rect.right() * zoom + _REDETECT_OFFSET, abs=1e-6)


@pytest.mark.gui
def test_redetect_handle_anchor_byte_identical_at_zoom_one(qtbot) -> None:
    """At z=1 the re-detect anchor equals today's fixed values exactly."""
    scene, item = _scene_with_box(PageBox(box=Box(100, 80, 300, 260), origin=USER))
    _select(scene, item)
    _apply_zoom_and_sync(item, 1.0)
    rect = item.rect()
    pos = item._redetect.scenePos()
    assert pos.x() == pytest.approx(rect.right() + 2.0, abs=1e-9)
    assert pos.y() == pytest.approx(rect.top() - 12.0, abs=1e-9)


@pytest.mark.gui
@pytest.mark.parametrize("zoom", [0.25, 0.5, 1.0, 2.0])
def test_badge_anchored_tl_outside_at_every_zoom(qtbot, zoom) -> None:
    """The badge sits (badge_w + 2)/zoom scene px left of the scene rect — a
    2-viewport-px gap at any zoom (BUG-2). The scene carries an explicit
    sceneRect (the production canvas sets it to the image bounds; an
    auto-computed one would include the badge itself and flip the edge case)."""
    # Far enough from the page TL that the TL-outside branch is exercised at
    # the lowest zoom (a box near the corner legitimately edge-flips inside).
    pb = PageBox(box=Box(300, 300, 300, 260), origin=DETECTED)
    pb.bubble_no = 5
    scene, item = _scene_with_box(pb)
    scene.setSceneRect(0.0, 0.0, 1000.0, 1000.0)
    _select(scene, item)
    _apply_zoom_and_sync(item, zoom)

    sbr = item.sceneBoundingRect()
    bw = item._badge.rect().width()
    bh = item._badge.rect().height()
    pos = item._badge.scenePos()
    assert pos.x() == pytest.approx(sbr.left() - (bw + _BADGE_OFFSET) / zoom, abs=1e-6)
    assert pos.y() == pytest.approx(sbr.top() - (bh + _BADGE_OFFSET) / zoom, abs=1e-6)
    # On-screen gap: the badge ignores transformations, so its DEVICE-px right
    # edge is pos.x*zoom + bw (bw does NOT scale) — the gap to the scene rect's
    # rendered left edge is exactly 2 viewport px.
    gap = sbr.left() * zoom - (pos.x() * zoom + bw)
    assert gap == pytest.approx(_BADGE_OFFSET, abs=1e-6)


@pytest.mark.gui
def test_badge_edge_flip_anchored_inside_at_every_zoom(qtbot) -> None:
    """The edge-flip inside branch divides its 2px inset by the zoom too."""
    pb = PageBox(box=Box(0, 0, 50, 50), origin=DETECTED)  # the page TL corner
    pb.bubble_no = 12
    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, 1000.0, 1000.0)
    item = BoxItem(pb)
    scene.addItem(item)
    item.setSelected(True)
    _apply_zoom_and_sync(item, 0.25)

    sbr = item.sceneBoundingRect()
    pos = item._badge.scenePos()
    # The outside candidate would clip -> flipped inside-top-left.
    assert pos.x() == pytest.approx(sbr.left() + _BADGE_OFFSET / 0.25, abs=1e-6)
    assert pos.y() == pytest.approx(sbr.top() + _BADGE_OFFSET / 0.25, abs=1e-6)


@pytest.mark.gui
def test_box_created_at_non_one_canvas_zoom_is_seeded(qtbot) -> None:
    """A canvas held at zoom 0.25 that runs set_boxes produces items seeded
    with the live zoom (pen 8.0 scene px) — the fit-to-window drift fix."""
    canvas = _canvas_with_image(qtbot)
    canvas.zoom_factor = 0.25
    canvas.setTransform(QTransform().scale(0.25, 0.25))
    canvas.set_boxes(
        user_pageboxes=[PageBox(box=Box(20, 20, 100, 100), origin=USER)],
        detected_pageboxes=[],
    )
    item = canvas._box_items[0]
    assert item._overlay_zoom == pytest.approx(0.25)
    assert item.pen().widthF() == pytest.approx(8.0)


@pytest.mark.gui
def test_zoom_changed_slot_applies_zoom_before_syncing_handles(qtbot) -> None:
    """``_on_zoom_changed_reposition_handles`` leaves every handle anchored per
    the zoom-divided formulas (the slot applies zoom BEFORE _sync_handles)."""
    canvas = _canvas_with_image(qtbot)
    canvas.set_boxes(
        user_pageboxes=[PageBox(box=Box(20, 20, 100, 100), origin=USER)],
        detected_pageboxes=[],
    )
    item = canvas._box_items[0]
    canvas._scene.clearSelection()
    item.setSelected(True)

    zoom = 0.5
    canvas._on_zoom_changed_reposition_handles(zoom)
    assert item._overlay_zoom == pytest.approx(zoom)

    rect = item.rect()
    half = _HANDLE_SIZE / 2.0 / zoom
    for corner, pt in (
        ("TL", rect.topLeft()),
        ("TR", rect.topRight()),
        ("BL", rect.bottomLeft()),
        ("BR", rect.bottomRight()),
    ):
        pos = item.handles[corner].scenePos()
        assert pos.x() == pytest.approx(pt.x() - half, abs=1e-6), corner
        assert pos.y() == pytest.approx(pt.y() - half, abs=1e-6), corner
    rh = item._rotation_handle
    assert rh.scenePos().y() == pytest.approx(
        rect.top() - (_ROTATE_ABOVE_TL + _ROTATE_SIZE / 2.0) / zoom, abs=1e-6
    )


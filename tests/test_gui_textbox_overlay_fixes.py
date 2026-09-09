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
    _HANDLE_HIT_SIZE,
    _HANDLE_SIZE,
    _INPAINT_DASH_PATTERN,
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

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
from PySide6.QtGui import QColor, QImage, QMouseEvent  # noqa: E402
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

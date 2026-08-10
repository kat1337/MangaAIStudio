"""GUI tests for the Curves dialog + CurveWidget (plan 06-04, PROJ-04).

Covers UI-SPEC surface 30 (D-01…D-08) against the real widgets (pytest-qt):

- CurveWidget (Task 1): paint smoke, click-add at the mapped coordinate,
  drag clamps (x strictly between neighbors, y in [0,255], endpoints y-only),
  double-click-delete (never endpoints), arrow-key nudge (±1 / Shift=±10),
  Tab / Shift+Tab selection cycling, `setMinimumSize(280, 240)`.
- CurvesDialog (Task 2): defaults (0/255/1.00, Linear, RGB), black/white
  slider↔endpoint sync with the white>black cross-clamp, In/Out spin ranges,
  gamma↔midpoint sync (A3), Apply stores ``result_values``, Cancel never
  stores, 14px Body typography (D-12), preview fires on control changes.
- Presets + channels + histogram + preview driver (Task 3): preset replace +
  stay-editable (D-05), per-channel independence (D-06), histogram computed
  ONCE at open (D-08), byte-exact composed preview vs ``image_ops.curves_page``
  (A1), verbatim UI-SPEC copy, ``_refresh`` is the single preview driver.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFontInfo, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from manga_ai_studio.core.image_ops import curves_page
from manga_ai_studio.gui.curves_dialog import CurveWidget

# A2 preset coordinates (RESEARCH A2, locked in 06-UI-SPEC surface 30).
S_CURVE = [(0, 0), (64, 40), (192, 215), (255, 255)]
BRIGHTEN = [(0, 0), (128, 150), (255, 255)]
DARKEN = [(0, 0), (128, 105), (255, 255)]


# ---------------------------------------------------------------- helpers

def _make_image(size=(24, 18)) -> np.ndarray:
    """A small deterministic gradient RGB page (for preview/histogram)."""
    h, w = size
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = (xx * 255 // max(w - 1, 1)).astype(np.uint8)
    img[..., 1] = (yy * 255 // max(h - 1, 1)).astype(np.uint8)
    img[..., 2] = 120
    return img


def _point_pos(widget: CurveWidget, x: int, y: int) -> QPoint:
    """Widget-space position of a unit-space (x, y) coordinate."""
    pt = widget.unit_to_widget(x, y)
    return QPoint(round(pt.x()), round(pt.y()))


def _drag_to(widget: CurveWidget, start_xy, end_xy) -> None:
    """Press at ``start_xy``, move to ``end_xy`` (unit coords), release.

    The move is delivered as an explicit ``QMouseEvent`` (bulletproof across
    Qt versions — ``QTest.mouseMove``'s event synthesis is not relied on).
    """
    start = _point_pos(widget, *start_xy)
    end = _point_pos(widget, *end_xy)
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=start)
    QApplication.processEvents()
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(end),
        widget.mapToGlobal(end),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, move)
    QApplication.processEvents()
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=end)
    QApplication.processEvents()


def _make_dialog(qtbot, img=None, callback=None) -> CurvesDialog:
    dlg = CurvesDialog(page_image=img, preview_callback=callback)
    qtbot.addWidget(dlg)
    return dlg


# ===========================================================================
# Task 1 (TRACER) — CurveWidget
# ===========================================================================

@pytest.mark.gui
def test_widget_paint_smoke(qtbot) -> None:
    """The widget paints without error and ships at the 280x240 minimum."""
    w = CurveWidget()
    qtbot.addWidget(w)
    assert w.minimumSize().width() == 280
    assert w.minimumSize().height() == 240
    w.resize(320, 280)
    w.show()
    QApplication.processEvents()
    w.grab()  # forces a full paintEvent — a paint crash fails here
    assert w._points == [(0, 0), (255, 255)]


@pytest.mark.gui
def test_widget_paint_with_histogram(qtbot) -> None:
    """paintEvent renders the histogram bars when ``_histogram`` is set."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    w._histogram = np.arange(256, dtype=np.float64)
    w.show()
    QApplication.processEvents()
    w.grab()


@pytest.mark.gui
def test_click_adds_point_at_mapped_coordinate_and_selects(qtbot) -> None:
    """Click on the grid adds a point at (input, output) and selects it."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    selected: list[int] = []
    w.point_selected.connect(selected.append)
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=_point_pos(w, 128, 100))
    assert w._points == [(0, 0), (128, 100), (255, 255)]
    assert w._selected == 1
    assert selected[-1] == 1


@pytest.mark.gui
def test_click_at_occupied_x_updates_y_last_wins(qtbot) -> None:
    """Clicking at an occupied x updates that point's y (LUT last-wins)."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    w._points = list(BRIGHTEN)  # (128, 150) interior point
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=_point_pos(w, 128, 90))
    assert w._points == [(0, 0), (128, 90), (255, 255)]
    assert len(w._points) == 3  # no duplicate x


@pytest.mark.gui
def test_drag_moves_point_with_clamps(qtbot) -> None:
    """Drag clamps x strictly between neighbors and y to [0,255]."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    w._points = list(S_CURVE)
    w._selected = 1  # (64, 40); neighbors at x=0 and x=192
    _drag_to(w, (64, 40), (400, -100))  # far beyond the right neighbor/top
    assert w._points[1] == (191, 0)  # x capped at 192-1, y capped at 0
    _drag_to(w, (191, 0), (-50, 400))  # far beyond the left neighbor/bottom
    assert w._points[1] == (1, 255)  # x floored at 0+1, y capped at 255
    assert w._points[0] == (0, 0)  # neighbors untouched
    assert w._points[2] == (192, 215)


@pytest.mark.gui
def test_double_click_deletes_interior_but_never_endpoints(qtbot) -> None:
    """Double-click deletes an interior point; endpoints are undeletable."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    w._points = list(S_CURVE)
    w._selected = 1
    QTest.mouseDClick(w, Qt.MouseButton.LeftButton, pos=_point_pos(w, 64, 40))
    assert len(w._points) == 3
    assert (64, 40) not in w._points
    QTest.mouseDClick(w, Qt.MouseButton.LeftButton, pos=_point_pos(w, 0, 0))
    assert len(w._points) == 3  # endpoint survives
    assert w._points[0] == (0, 0)


@pytest.mark.gui
def test_arrow_keys_nudge_selected_point(qtbot) -> None:
    """Arrows nudge the selected point ±1; Shift = ±10 (D-07)."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    w._points = list(BRIGHTEN)
    w._selected = 1
    QTest.keyClick(w, Qt.Key.Key_Right)
    assert w._points[1] == (129, 150)
    QTest.keyClick(w, Qt.Key.Key_Left)
    assert w._points[1] == (128, 150)
    QTest.keyClick(w, Qt.Key.Key_Up)
    assert w._points[1] == (128, 151)
    QTest.keyClick(w, Qt.Key.Key_Down)
    assert w._points[1] == (128, 150)
    QTest.keyClick(w, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert w._points[1] == (118, 150)  # Shift = ±10
    QTest.keyClick(w, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert w._points[1] == (128, 150)


@pytest.mark.gui
def test_tab_cycles_selection(qtbot) -> None:
    """Tab / Shift+Tab cycle point selection (endpoints included)."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    w._points = list(S_CURVE)
    w._selected = 0
    QTest.keyClick(w, Qt.Key.Key_Tab)
    assert w._selected == 1
    QTest.keyClick(w, Qt.Key.Key_Tab)
    assert w._selected == 2
    QTest.keyClick(w, Qt.Key.Key_Tab)
    assert w._selected == 3  # endpoints included
    QTest.keyClick(w, Qt.Key.Key_Tab)
    assert w._selected == 0  # wraps
    QTest.keyClick(w, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert w._selected == 3  # backwards


@pytest.mark.gui
def test_endpoint_drag_changes_only_y(qtbot) -> None:
    """Endpoints are fixed at x=0/255 — draggable only along their edge."""
    w = CurveWidget()
    qtbot.addWidget(w)
    w.resize(320, 280)
    _drag_to(w, (0, 0), (100, 200))
    assert w._points[0] == (0, 200)  # x stays 0, y follows the drag
    assert w._points[1] == (255, 255)
    _drag_to(w, (255, 255), (0, 50))
    assert w._points[-1] == (255, 50)  # x stays 255

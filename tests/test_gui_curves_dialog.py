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
from PIL import Image as PILImage
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFontInfo, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.box_model import USER, PageBox
from manga_ai_studio.core.image_ops import curves_page
from manga_ai_studio.core.mask_editor import (
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.gui.curves_dialog import CurveWidget, CurvesDialog
from manga_ai_studio.gui.main_window import MainWindow
from panelcleaner.structures import Box

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


def _seed_mask_and_box(window: MainWindow) -> tuple[np.ndarray, PageBox]:
    """Seed a binary mask + one user box (suppressed — no undo push)."""
    img = window.canvas.get_image_numpy()
    h, w = img.shape[:2]
    mask_bin = np.zeros((h, w), dtype=np.uint8)
    mask_bin[10:20, 30:50] = 255
    window.canvas.set_mask(numpy_binary_to_mask_qimage(mask_bin))
    box = PageBox(box=Box(30, 10, 50, 20), origin=USER)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([box], [])
    finally:
        window._suppress_boxes_push = False
    return mask_bin, box


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


# ===========================================================================
# Task 2 — CurvesDialog collector: defaults, sync, spins, gamma, apply
# ===========================================================================

@pytest.mark.gui
def test_dialog_defaults(qtbot) -> None:
    """The dialog opens at 0/255/1.00, Linear, RGB — In/Out at the point."""
    dlg = _make_dialog(qtbot)
    assert dlg.black_spin.value() == 0
    assert dlg.white_spin.value() == 255
    assert dlg.gamma_spin.value() == 1.00
    assert dlg._current_channel == "RGB"
    # Linear curve with 0 interior points (must-have: defaults contract).
    assert dlg.curve_widget._points == [(0, 0), (255, 255)]
    # In/Out track the selected point — the left endpoint: In disabled at 0.
    assert dlg._selected == 0
    assert not dlg.in_spin.isEnabled()
    assert dlg.in_spin.value() == 0
    assert dlg.out_spin.value() == 0
    assert dlg.channel_buttons["RGB"].isChecked()


@pytest.mark.gui
def test_dialog_font_14px(qtbot) -> None:
    """D-12: the Curves dialog ships at 14px Body from birth (A4)."""
    dlg = _make_dialog(qtbot)
    assert QFontInfo(dlg.font()).pixelSize() == 14


@pytest.mark.gui
def test_black_slider_moves_left_endpoint_with_clamp(qtbot) -> None:
    """Black row -> left endpoint y; white min follows black+1 (T-05-07)."""
    dlg = _make_dialog(qtbot)
    dlg.black_spin.setValue(200)
    assert dlg.curve_widget._points[0] == (0, 200)
    assert dlg.white_spin.minimum() == 201  # white min follows black+1
    dlg.white_spin.setValue(250)
    assert dlg.curve_widget._points[-1] == (255, 250)
    assert dlg.black_spin.maximum() == 249  # black max follows white-1
    # A white value below black+1 clamps up — the map can never invert.
    dlg.white_spin.setValue(100)
    assert dlg.white_spin.value() == 201
    assert dlg.curve_widget._points[-1] == (255, 201)


@pytest.mark.gui
def test_curve_endpoint_cross_clamp_no_inversion(qtbot) -> None:
    """Curve-driven endpoint inversion clamps on the curve itself.

    Dragging the black endpoint past white-1 (via the widget path) caps it —
    the same T-05-07 mirror the slider side applies.
    """
    dlg = _make_dialog(qtbot)
    dlg.curve_widget._points = [(0, 200), (255, 100)]  # inverted endpoints
    dlg.curve_widget.points_changed.emit()
    assert dlg.curve_widget._points[0][1] <= dlg.curve_widget._points[-1][1] - 1
    assert dlg.black_spin.value() <= dlg.white_spin.value() - 1
    assert dlg.white_spin.minimum() == dlg.black_spin.value() + 1


@pytest.mark.gui
def test_in_spin_range_respects_neighbors(qtbot) -> None:
    """In range = [prev_x+1, next_x-1]; endpoints disable it (D-04)."""
    dlg = _make_dialog(qtbot)
    dlg.curve_widget._points = list(S_CURVE)
    dlg._selected = 1  # (64, 40): neighbors at x=0 and x=192
    dlg._refresh()
    assert dlg.in_spin.minimum() == 1
    assert dlg.in_spin.maximum() == 191
    assert dlg.in_spin.value() == 64
    assert dlg.in_spin.isEnabled()
    dlg.in_spin.setValue(100)
    assert dlg.curve_widget._points[1] == (100, 40)
    # Selecting an endpoint disables In (x fixed at 0/255).
    dlg._selected = 0
    dlg._refresh()
    assert not dlg.in_spin.isEnabled()
    assert dlg.in_spin.value() == 0


@pytest.mark.gui
def test_out_spin_range_and_drives_selected_point(qtbot) -> None:
    """Out range is 0..255 and drives the selected point's y."""
    dlg = _make_dialog(qtbot)
    assert dlg.out_spin.minimum() == 0
    assert dlg.out_spin.maximum() == 255
    dlg.curve_widget._points = list(BRIGHTEN)
    dlg._selected = 1
    dlg._refresh()
    dlg.out_spin.setValue(180)
    assert dlg.curve_widget._points[1] == (128, 180)
    # The Out spin also drives an endpoint's y (endpoints drag y-only).
    dlg._selected = 0
    dlg._refresh()
    dlg.out_spin.setValue(60)
    assert dlg.curve_widget._points[0] == (0, 60)


@pytest.mark.gui
def test_gamma_100_matches_midpoint_and_backmaps(qtbot) -> None:
    """Gamma 1.00 <-> midpoint 128; dragging the midpoint back-maps (A3)."""
    dlg = _make_dialog(qtbot)
    # Defaults: the diagonal's sampled output at input 128 is 128.
    assert dlg._sample_output(dlg.curve_widget._points, 128) == pytest.approx(128)
    assert dlg.gamma_spin.value() == 1.00
    # A (128, 150) midpoint back-maps gamma = ln(0.5)/ln(150/255).
    dlg.curve_widget._points = list(BRIGHTEN)
    dlg._refresh()
    expected = math.log(0.5) / math.log(150 / 255.0)
    assert dlg.gamma_spin.value() == pytest.approx(round(expected, 2), abs=0.01)


@pytest.mark.gui
def test_gamma_change_injects_midpoint_point(qtbot) -> None:
    """Setting gamma injects/moves the (128, y) point (D-03/A3)."""
    dlg = _make_dialog(qtbot)
    assert dlg.curve_widget._points == [(0, 0), (255, 255)]  # 0 interior
    dlg.gamma_spin.setValue(2.0)
    y = int(round(255.0 * 0.5 ** (1.0 / 2.0)))  # 180
    assert dlg.curve_widget._points == [(0, 0), (128, y), (255, 255)]
    # Setting it again moves the existing point (no duplicate x=128).
    dlg.gamma_spin.setValue(3.0)
    y3 = int(round(255.0 * 0.5 ** (1.0 / 3.0)))
    assert dlg.curve_widget._points == [(0, 0), (128, y3), (255, 255)]


@pytest.mark.gui
def test_on_apply_stores_result_values_and_accepts(qtbot, monkeypatch) -> None:
    """Apply stores the detached (master, channels) state and accepts."""
    dlg = _make_dialog(qtbot)
    accepted: list = []
    monkeypatch.setattr(dlg, "accept", lambda: accepted.append(True))
    dlg.black_spin.setValue(50)
    QTest.mouseClick(dlg.apply_btn, Qt.MouseButton.LeftButton)
    assert accepted == [True]
    master, channels = dlg.result_values
    assert master == [(0, 50), (255, 255)]
    assert channels["RGB"] == [(0, 50), (255, 255)]
    assert channels["R"] == [(0, 0), (255, 255)]
    # Detached copies (Pitfall 2): later edits cannot poison the payload.
    assert dlg.result_values[0] is not dlg._channel_points["RGB"]
    assert dlg.result_values[1]["RGB"] is not dlg._channel_points["RGB"]


@pytest.mark.gui
def test_reject_does_not_store(qtbot) -> None:
    """Cancel rejects and never stores the collected state."""
    dlg = _make_dialog(qtbot)
    dlg.black_spin.setValue(100)
    QTest.mouseClick(dlg.cancel_btn, Qt.MouseButton.LeftButton)
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert dlg.result_values[0] == [(0, 0), (255, 255)]  # untouched default


@pytest.mark.gui
def test_preview_fires_on_control_changes(qtbot) -> None:
    """Every control change fires the preview with the composed payload."""
    img = _make_image()
    calls: list = []
    dlg = _make_dialog(qtbot, img=img, callback=calls.append)
    baseline = len(calls)  # the constructor fires once with the defaults
    assert baseline >= 1
    dlg.black_spin.setValue(50)
    dlg.gamma_spin.setValue(1.5)
    dlg.curve_widget._points = list(S_CURVE)
    dlg.curve_widget.points_changed.emit()
    assert len(calls) > baseline
    for payload in calls:
        assert payload.shape == img.shape
        assert payload.dtype == np.uint8


# ===========================================================================
# Task 3 — presets, channel switcher, histogram, preview composition driver
# ===========================================================================

@pytest.mark.gui
def test_preset_replaces_points_and_stays_editable(qtbot) -> None:
    """A preset click replaces the current channel's points (D-05/A2)."""
    dlg = _make_dialog(qtbot)
    QTest.mouseClick(dlg.preset_buttons["S-curve"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == S_CURVE
    assert dlg._channel_points["RGB"] == S_CURVE
    # Presets are editable starting points: a real drag moves the point.
    _drag_to(dlg.curve_widget, (64, 40), (64, 90))
    assert dlg.curve_widget._points[1] == (64, 90)
    # Linear restores the pure diagonal.
    QTest.mouseClick(dlg.preset_buttons["Linear"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == [(0, 0), (255, 255)]
    QTest.mouseClick(dlg.preset_buttons["Brighten"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == BRIGHTEN
    QTest.mouseClick(dlg.preset_buttons["Darken"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == DARKEN


@pytest.mark.gui
def test_channel_switcher_preserves_per_channel_edits(qtbot) -> None:
    """Channels edit independent point sets; switching preserves them."""
    dlg = _make_dialog(qtbot)
    QTest.mouseClick(dlg.channel_buttons["R"], Qt.MouseButton.LeftButton)
    QTest.mouseClick(dlg.preset_buttons["S-curve"], Qt.MouseButton.LeftButton)
    assert dlg._current_channel == "R"
    assert dlg.curve_widget._points == S_CURVE
    QTest.mouseClick(dlg.channel_buttons["G"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == [(0, 0), (255, 255)]  # G untouched
    QTest.mouseClick(dlg.channel_buttons["R"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == S_CURVE  # R preserved
    QTest.mouseClick(dlg.channel_buttons["RGB"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._points == [(0, 0), (255, 255)]  # master untouched


@pytest.mark.gui
def test_histogram_computed_once_at_open(qtbot) -> None:
    """D-08: the histogram is computed ONCE; editing never recomputes."""
    img = _make_image()
    dlg = _make_dialog(qtbot, img=img)
    assert dlg._histograms["RGB"] is not None
    assert dlg._histograms["R"] is not None
    stored = dlg._histograms["RGB"]
    assert stored.shape == (256,)
    assert dlg.curve_widget._histogram is stored
    # Editing (point drag + slider + gamma) leaves the stored array intact.
    dlg.curve_widget._points = list(S_CURVE)
    dlg._refresh()
    dlg.black_spin.setValue(50)
    dlg.gamma_spin.setValue(1.5)
    assert dlg._histograms["RGB"] is stored
    assert np.array_equal(dlg._histograms["RGB"], stored)
    # No page image -> histogram unset (the widget paints without it).
    dlg2 = _make_dialog(qtbot)
    assert dlg2._histograms["RGB"] is None
    assert dlg2.curve_widget._histogram is None


@pytest.mark.gui
def test_channel_switch_updates_widget_histogram(qtbot) -> None:
    """Channel switch loads the matching precomputed histogram (A7)."""
    img = _make_image()
    dlg = _make_dialog(qtbot, img=img)
    assert dlg.curve_widget._histogram is dlg._histograms["RGB"]
    QTest.mouseClick(dlg.channel_buttons["B"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._histogram is dlg._histograms["B"]
    QTest.mouseClick(dlg.channel_buttons["RGB"], Qt.MouseButton.LeftButton)
    assert dlg.curve_widget._histogram is dlg._histograms["RGB"]


@pytest.mark.gui
def test_preview_byte_exact_vs_curves_page(qtbot) -> None:
    """The preview payload is byte-exact curves_page composition (A1)."""
    img = _make_image()
    calls: list = []
    dlg = _make_dialog(qtbot, img=img, callback=calls.append)
    dlg.curve_widget._points = list(S_CURVE)  # master S-curve
    dlg._channel_points["R"] = list(BRIGHTEN)  # R channel brighten
    dlg._refresh()
    expected = curves_page(
        img,
        list(S_CURVE),
        {"R": list(BRIGHTEN), "G": [(0, 0), (255, 255)], "B": [(0, 0), (255, 255)]},
    )
    assert np.array_equal(calls[-1], expected)


@pytest.mark.gui
def test_preset_and_channel_copy_verbatim(qtbot) -> None:
    """UI-SPEC surface 30 copy strings match verbatim (D-05/D-06)."""
    dlg = _make_dialog(qtbot)
    expected_tooltips = {
        "Linear": "Reset the curve to a straight line.",
        "S-curve": "Add contrast — classic S-curve.",
        "Brighten": "Brighten midtones.",
        "Darken": "Darken midtones.",
    }
    for name, tip in expected_tooltips.items():
        assert dlg.preset_buttons[name].toolTip() == tip
    for name in ("RGB", "R", "G", "B"):
        assert dlg.channel_buttons[name].text() == name
    assert dlg.channel_group.exclusive()


@pytest.mark.gui
def test_refresh_is_single_preview_driver(qtbot) -> None:
    """Every control path funnels into _refresh; no other call sites."""
    img = _make_image()
    calls: list = []
    dlg = _make_dialog(qtbot, img=img, callback=calls.append)
    baseline = len(calls)
    dlg.black_spin.setValue(40)
    dlg.gamma_spin.setValue(1.4)
    QTest.mouseClick(dlg.preset_buttons["Darken"], Qt.MouseButton.LeftButton)
    QTest.mouseClick(dlg.channel_buttons["R"], Qt.MouseButton.LeftButton)
    assert len(calls) > baseline
    for payload in calls:
        assert payload.shape == img.shape
        assert payload.dtype == np.uint8
    import inspect

    src = inspect.getsource(CurvesDialog)
    # Only _preview calls the callback (its single call site in the file).
    assert src.count("preview_callback(") == 1


# ===========================================================================
# Plan 06-05 — MainWindow wiring: lifecycle tests migrated from the Levels
# suite (D-01 supersession): apply-one-entry + b376f8a restore semantics,
# cancel-restores-exactly, preview no-baseline-poison, defaults/clamp, and
# the Tools ▸ Image menu surface rename.
# ===========================================================================

@pytest.mark.gui
def test_curves_action_in_tools_menu(qtbot, tmp_path) -> None:
    """Tools ▸ Image shows 'Curves…' — the Levels slot is renamed (D-01)."""
    window = _window_with_page(qtbot, tmp_path)
    assert window.action_curves.text() == "Curves\u2026"
    # PySide6 wrapper-lifetime quirk: hold the top-level action wrappers
    # while resolving the menu, or the C++ QMenus vanish with the temps.
    menu_actions = window.menuBar().actions()
    menus = [a.menu() for a in menu_actions]
    tools_menu = next(m for m in menus if m is not None and m.title() == "&Tools")
    assert window.action_curves in tools_menu.actions()
    # The Levels action/surface is gone — replaced, not appended.
    assert not hasattr(window, "action_levels")
    assert not any(a.text() == "Levels\u2026" for a in tools_menu.actions())


@pytest.mark.gui
def test_curves_defaults_and_clamp(qtbot) -> None:
    """CurvesDialog opens at 0/255/1.00 with the white>black cross-clamp.

    Dragging black to 200 moves white's minimum to 201, and the preview
    callback never receives an inverted curve (T-05-07 — no inverted map).
    """
    calls: list = []
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    dlg = CurvesDialog(page_image=img, preview_callback=lambda v: calls.append(v))
    qtbot.addWidget(dlg)

    assert dlg.black_spin.value() == 0
    assert dlg.white_spin.value() == 255
    assert dlg.gamma_spin.value() == 1.00

    dlg.black_spin.setValue(200)
    assert dlg.white_spin.minimum() == 201  # white min follows black+1
    dlg.black_spin.setValue(254)
    assert dlg.white_spin.minimum() == 255
    dlg.white_spin.setValue(100)  # white below black+1 -> clamped up
    assert dlg.black_spin.maximum() == dlg.white_spin.value() - 1
    assert dlg.black_spin.value() <= dlg.white_spin.value() - 1

    # The preview ran; every payload is a valid composed image.
    assert calls, "preview callback never fired"
    for payload in calls:
        assert payload.shape == (10, 10, 3)
        assert payload.dtype == np.uint8
    # The cross-clamp holds on the curve state itself (T-05-07).
    assert dlg.curve_widget._points[0][1] < dlg.curve_widget._points[-1][1]


@pytest.mark.gui
def test_curves_cancel_restores_exactly(qtbot, tmp_path, monkeypatch) -> None:
    """Cancel restores the pre-dialog image byte-identical with zero entries.

    Dragging the controls during the dialog mutates the canvas (live preview,
    no pushes — Pitfall 9); Cancel re-displays the detached base silently:
    no undo entry, no status flash (UI-SPEC surface 30).
    """
    window = _window_with_page(qtbot, tmp_path)
    pre = window.canvas.get_image_numpy().copy()

    def _fake_exec(dlg):
        dlg.black_spin.setValue(120)  # preview mutates the canvas
        dlg.white_spin.setValue(200)
        dlg.gamma_spin.setValue(1.7)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(CurvesDialog, "exec", _fake_exec)
    window._on_curves()
    QApplication.processEvents()

    assert np.array_equal(window.canvas.get_image_numpy(), pre)  # exact restore
    assert not window.history.can_undo()  # no undo entry was pushed
    assert window.status_bar_left.text() != "Curves applied."  # no flash


@pytest.mark.gui
def test_curves_apply_pushes_one_entry(qtbot, tmp_path, monkeypatch) -> None:
    """Apply commits the previewed state: ONE image-only entry (D-15).

    Curves is geometry-free: masks and boxes are untouched, the image entry
    is the only store pushed, geometry_altered stays False, the status
    flash fires, and Show Original re-baselines to the post-curves image
    (D-14).

    Restore semantics (b376f8a ordering, UI-review FLAG): the live preview
    mutates the canvas mid-dialog, so Apply MUST capture the TRUE pre-op
    image (the detached pre-dialog base) as the undo before-state — not the
    last preview frame. ONE Ctrl+Z after Apply must restore the pre-dialog
    image byte-identical and leave the geometry undo stack empty.
    """
    window = _window_with_page(qtbot, tmp_path)
    pre = window.canvas.get_image_numpy().copy()
    mask_bin, _box = _seed_mask_and_box(window)

    def _fake_exec(dlg):
        # A real user drags the curve: each change fires the live preview,
        # mutating the canvas (Pitfall 9 — no pushes). The final preview
        # leaves the canvas showing the curved state.
        dlg.curve_widget._points = list(BRIGHTEN)
        dlg._refresh()
        dlg.result_values = (
            list(dlg._channel_points["RGB"]),
            {ch: list(pts) for ch, pts in dlg._channel_points.items()},
        )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CurvesDialog, "exec", _fake_exec)
    window._on_curves()
    QApplication.processEvents()

    expected = curves_page(
        pre,
        list(BRIGHTEN),
        {"R": [(0, 0), (255, 255)], "G": [(0, 0), (255, 255)], "B": [(0, 0), (255, 255)]},
    )
    assert np.array_equal(window.canvas.get_image_numpy(), expected)
    # Geometry-free: mask + boxes untouched.
    assert np.array_equal(mask_to_numpy_binary(window.canvas.get_mask()), mask_bin)
    assert window.canvas.boxes_snapshot()[0].box.as_tuple == (30, 10, 50, 20)
    # ONE image-only entry — the mask/boxes stores are untouched.
    assert len(window.history._image_undo) == 1
    assert len(window.history._mask_undo) == 0
    assert len(window.history._boxes_undo) == 0
    assert window.image_files[0].geometry_altered is False
    assert "Curves applied." in window.status_bar_left.text()
    # Show Original shows the POST-curves image (D-14 re-baseline).
    assert np.array_equal(window.canvas._original_image_numpy, expected)

    # Restore semantics: the undo before-state is the PRE-DIALOG image (the
    # previews above mutated the canvas — without the b376f8a ordering, the
    # before-state equals the post-op state and Ctrl+Z is a no-op).
    window.on_undo()
    QApplication.processEvents()
    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    # The single geometry entry was consumed: the stack is empty again.
    assert not window.history.can_undo()


@pytest.mark.gui
def test_curves_preview_no_baseline_poison(qtbot, tmp_path, monkeypatch) -> None:
    """The live preview never re-baselines Show Original (Pitfall 5/9).

    The capture-suppressed preview path keeps the pre-dialog image as the
    D-14 "original"; after Cancel, Show Original still shows the pre-dialog
    image even though the canvas was mutated by previews.
    """
    window = _window_with_page(qtbot, tmp_path)
    pre = window.canvas.get_image_numpy().copy()
    window.canvas.rebaseline_original()  # honest pre-dialog baseline
    assert np.array_equal(window.canvas._original_image_numpy, pre)

    preview_seen: dict = {}

    def _fake_exec(dlg):
        dlg.black_spin.setValue(60)  # preview mutates the canvas mid-dialog
        preview_seen["mid"] = window.canvas.get_image_numpy().copy()
        dlg.gamma_spin.setValue(2.0)
        dlg.white_spin.setValue(180)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(CurvesDialog, "exec", _fake_exec)
    window._on_curves()
    QApplication.processEvents()

    # The preview ran mid-dialog (canvas mutated) but never touched the
    # baseline; Cancel restored the pre-dialog image exactly (Pitfall 5/9).
    assert not np.array_equal(preview_seen["mid"], pre)
    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    assert np.array_equal(window.canvas._original_image_numpy, pre)
    window.canvas.show_original(True)
    assert np.array_equal(window.canvas.get_image_numpy(), pre)

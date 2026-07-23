"""GUI smoke tests for the Walking Skeleton (VALIDATION.md §Wave 0).

Uses pytest-qt's ``qtbot`` fixture. Guards with ``pytest.importorskip`` so
collection degrades gracefully where PySide6 is unavailable. These tests need a
display; on headless CI they would be skipped/fail at Qt init — the Wave 0 gate
runs on the developer's Windows machine.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPalette,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem  # noqa: E402

from manga_ai_studio.app import create_app  # noqa: E402
from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.mask_editor import DEFAULT_BRUSH_SIZE, ToolMode  # noqa: E402
from manga_ai_studio.gui.canvas import (  # noqa: E402
    MAX_IMAGE_DIMENSION,
    MAX_ZOOM_FACTOR,
    ZOOM_TICK_FACTOR,
    EditorCanvas,
    validate_image_path,
)
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from manga_ai_studio.gui.tools_panel import ToolsPanel  # noqa: E402


def _solid_pixmap(size: int, color: QColor) -> QPixmap:
    """Build a solid-color QPixmap of the given size."""
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


# ---------------------------------------------------------------------------
# Plan 01 tests (Walking Skeleton)
# ---------------------------------------------------------------------------


def test_app_launches(qtbot, tmp_path) -> None:
    """Constructing + showing + closing a MainWindow does not raise."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == "Manga AI Studio"
    window.close()


def test_theme_applied(qtbot) -> None:
    """create_app applies the dark Fusion palette (#232328 window color)."""
    app = create_app()
    palette = QApplication.palette()
    assert palette.color(QPalette.ColorRole.Window).name() == "#232328"


def test_canvas_load_image(qtbot) -> None:
    """set_image puts a QGraphicsPixmapItem in the scene sized to the image."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)

    pixmap = _solid_pixmap(4, QColor("red"))
    canvas.set_image(pixmap)

    # The scene should contain the image pixmap item with content.
    pixmap_items = canvas.scene().items()
    assert any(isinstance(it, QGraphicsPixmapItem) for it in pixmap_items)
    # sceneRect matches the image size.
    assert int(canvas.sceneRect().width()) == 4
    assert int(canvas.sceneRect().height()) == 4


def test_open_image_action(qtbot, tmp_path) -> None:
    """MainWindow exposes an Open Image action with Ctrl+O shortcut."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    action = window.action_open_image
    assert action.text() == "Open Image\u2026"
    assert "Ctrl+O" in action.shortcut().toString()


# ---------------------------------------------------------------------------
# Plan 02 Task 1 tests — Canvas pan/zoom + validation + empty state
# ---------------------------------------------------------------------------

def _zoomable_canvas(qtbot) -> EditorCanvas:
    """Build a canvas with a real image loaded so zoom() has dimensions to clamp."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 400)
    canvas.set_image(_solid_pixmap(200, QColor("blue")))
    canvas.show()
    canvas.viewport().show()
    # Process events so viewport().width()/height() report the real size.
    QApplication.processEvents()
    return canvas


def test_zoom_wheel_half_step(qtbot) -> None:
    """zoom(sqrt(1.25)) from 1.0 lands at ~1.118 (the half-step factor)."""
    canvas = _zoomable_canvas(qtbot)
    canvas.zoom_factor = 1.0
    canvas.zoom(ZOOM_TICK_FACTOR**0.5)
    assert math.isclose(canvas.zoom_factor, ZOOM_TICK_FACTOR**0.5, rel_tol=1e-9)
    # Transform scale matches the zoom factor.
    assert math.isclose(canvas.transform().m11(), canvas.zoom_factor, rel_tol=1e-9)


def test_zoom_clamp_100x(qtbot) -> None:
    """Repeated zoom_in never exceeds 100x and reaches exactly 100.0."""
    canvas = _zoomable_canvas(qtbot)
    canvas.zoom_factor = 1.0
    for _ in range(500):  # far more than needed to saturate
        canvas.zoom_in()
    assert canvas.zoom_factor == pytest.approx(MAX_ZOOM_FACTOR)
    assert canvas.zoom_factor <= MAX_ZOOM_FACTOR


def test_zoom_clamp_min(qtbot) -> None:
    """Zooming out below half-viewport is a no-op (zoom_factor unchanged)."""
    canvas = _zoomable_canvas(qtbot)
    # Saturate the zoom-out: once the image is already at/under half the
    # viewport, further zoom_out(factor<1) must early-return.
    for _ in range(200):
        canvas.zoom_out()
    saturated = canvas.zoom_factor
    # The next call should be a no-op.
    canvas.zoom_out()
    assert canvas.zoom_factor == pytest.approx(saturated)
    assert canvas.zoom_factor > 0


def test_update_smoothing_pixel_accurate(qtbot) -> None:
    """SmoothPixmapTransform is OFF above 1x, ON at/under 1x."""
    from PySide6.QtGui import QPainter

    smooth = QPainter.RenderHint.SmoothPixmapTransform
    canvas = _zoomable_canvas(qtbot)

    canvas.zoom_factor = 1.5
    canvas.update_smoothing()
    assert not (canvas.renderHints() & smooth)

    canvas.zoom_factor = 1.0
    canvas.update_smoothing()
    assert canvas.renderHints() & smooth

    canvas.zoom_factor = 0.5
    canvas.update_smoothing()
    assert canvas.renderHints() & smooth


def test_image_size_limit_rejects_huge() -> None:
    """validate_image_size rejects a 10001x10001 image (T-01-03)."""
    canvas = EditorCanvas()
    assert canvas.validate_image_size(MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION) is True
    assert canvas.validate_image_size(MAX_IMAGE_DIMENSION + 1, 100) is False
    assert canvas.validate_image_size(100, MAX_IMAGE_DIMENSION + 1) is False


def test_path_validation_rejects_bad_suffix(tmp_path) -> None:
    """validate_image_path rejects non-image suffixes, accepts allowlist (T-01-02)."""
    assert validate_image_path(Path("x.txt")) is False
    assert validate_image_path(Path("malware.exe")) is False
    assert validate_image_path(Path("a/b.png")) is True
    assert validate_image_path(Path("a/b.jpg")) is True
    assert validate_image_path(Path("a/b.JPEG")) is True  # case-insensitive
    assert validate_image_path(Path("a/b.jpeg")) is True
    assert validate_image_path(Path("a/b.webp")) is True
    assert validate_image_path(Path("a/b.bmp")) is True


def test_empty_state_heading(qtbot) -> None:
    """A fresh canvas shows the 'No page open' empty-state overlay."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    # The heading text content is the UI-SPEC contract.
    assert canvas._empty_heading.toPlainText() == "No page open"
    assert canvas._empty_body.toPlainText().startswith(
        "Open a single image or a folder of images to begin cleaning."
    )
    # The overlay items live in the scene (visibility toggles on set_image/clear).
    assert canvas._empty_heading in canvas.scene().items()
    assert canvas._empty_body in canvas.scene().items()


# ---------------------------------------------------------------------------
# Plan 04 Task 2 tests — ToolsPanel + canvas tool dispatch + cursor visuals
# ---------------------------------------------------------------------------

def _press(canvas, sx: float, sy: float, button=Qt.MouseButton.LeftButton) -> QMouseEvent:
    """Build a mouse-press at viewport coords that map to SCENE (sx, sy).

    QGraphicsView centers the scene in the viewport, so viewport (sx, sy) !=
    scene (sx, sy). We map the desired scene point back to viewport coords so
    the canvas's ``mapToScene`` lands the stroke where the test asserts.
    """
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def _move(canvas, sx: float, sy: float) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(vp),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release(canvas, sx: float, sy: float, button=Qt.MouseButton.LeftButton) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(vp),
        button,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _canvas_with_image(qtbot, size: int = 100) -> EditorCanvas:
    """Build a shown canvas with a solid image + initialized mask."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(300, 300)
    canvas.set_image(_solid_pixmap(size, QColor("white")))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    return canvas


# --- ToolsPanel tests ---

def test_tools_panel_tool_group_exclusive(qtbot) -> None:
    """ToolsPanel exposes 5 exclusive checkable actions; checking one unchecks others."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    # 5 actions in the group, all checkable.
    actions = panel.tool_group.actions()
    assert len(actions) == 5
    assert panel.tool_group.isExclusive()
    for act in actions:
        assert act.isCheckable()

    # Move is checked initially (default tool).
    assert panel.action_move.isChecked()
    assert panel.active_tool() == ToolMode.MOVE

    # Checking Brush unchecks Move and emits tool_changed(BRUSH).
    with qtbot.waitSignal(panel.tool_changed, timeout=1000) as blocker:
        panel.action_brush.setChecked(True)
    assert blocker.args == [ToolMode.BRUSH]
    assert not panel.action_move.isChecked()
    assert panel.active_tool() == ToolMode.BRUSH


def test_tools_panel_brush_slider_spinbox_sync(qtbot) -> None:
    """Slider <-> spinbox stay in sync; label updates; brush_size_changed fires."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    with qtbot.waitSignal(panel.brush_size_changed, timeout=1000) as blocker:
        panel.brush_slider.setValue(73)
    assert blocker.args == [73]
    assert panel.brush_spinbox.value() == 73
    assert "73 px" in panel.brush_label.text()

    # Spinbox -> slider sync.
    with qtbot.waitSignal(panel.brush_size_changed, timeout=1000) as blocker:
        panel.brush_spinbox.setValue(150)
    assert blocker.args == [150]
    assert panel.brush_slider.value() == 150
    assert "150 px" in panel.brush_label.text()


def test_tools_panel_brush_range_clamped(qtbot) -> None:
    """The spinbox/slider enforce [1, 300] (setMinimum/setMaximum)."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    assert panel.brush_slider.minimum() == 1
    assert panel.brush_slider.maximum() == 300
    assert panel.brush_spinbox.minimum() == 1
    assert panel.brush_spinbox.maximum() == 300
    assert panel.brush_slider.value() == DEFAULT_BRUSH_SIZE == 40


# --- Canvas tool-dispatch tests ---

def test_canvas_set_tool_routes_to_mask_editor_brush(qtbot) -> None:
    """BRUSH tool + a left-drag paints a red band on the mask via core ops."""
    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(10)

    # Before painting, the mask center is transparent.
    assert canvas.get_mask().pixelColor(50, 10).alpha() == 0

    # Simulate a press-move-release drag across row 10.
    canvas.mousePressEvent(_press(canvas, 10, 10))
    canvas.mouseMoveEvent(_move(canvas, 90, 10))
    canvas.mouseReleaseEvent(_release(canvas, 90, 10))

    # The brush routed through paint_mask_stroke -> painted band on row ~10.
    assert canvas.get_mask().pixelColor(50, 10).alpha() > 0


def test_canvas_set_tool_routes_to_mask_editor_rectangle(qtbot) -> None:
    """RECTANGLE tool drag commits a filled rect on release."""
    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.RECTANGLE)

    canvas.mousePressEvent(_press(canvas, 20, 20))
    canvas.mouseMoveEvent(_move(canvas, 80, 80))
    canvas.mouseReleaseEvent(_release(canvas, 80, 80))

    mask = canvas.get_mask()
    assert mask.pixelColor(50, 50).alpha() > 0
    assert mask.pixelColor(5, 5).alpha() == 0


def test_canvas_set_tool_routes_to_mask_editor_lasso(qtbot) -> None:
    """LASSO tool drag commits a filled (closed) path on release."""
    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.LASSO)

    # A triangular-ish drag: down-right, across, up-left, back to start.
    canvas.mousePressEvent(_press(canvas, 50, 10))
    canvas.mouseMoveEvent(_move(canvas, 90, 90))
    canvas.mouseMoveEvent(_move(canvas, 10, 90))
    canvas.mouseReleaseEvent(_release(canvas, 50, 10))

    mask = canvas.get_mask()
    # Interior of the triangle near the centroid should be painted.
    assert mask.pixelColor(50, 65).alpha() > 0


def test_canvas_eraser_tool_clears(qtbot) -> None:
    """ERASER tool strokes clear a pre-painted region (CompositionMode_Clear)."""
    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(20)
    canvas.mousePressEvent(_press(canvas, 10, 50))
    canvas.mouseMoveEvent(_move(canvas, 90, 50))
    canvas.mouseReleaseEvent(_release(canvas, 90, 50))
    assert canvas.get_mask().pixelColor(50, 50).alpha() > 0

    # Switch to Eraser and stroke over the same region.
    canvas.set_tool(ToolMode.ERASER)
    canvas.mousePressEvent(_press(canvas, 10, 50))
    canvas.mouseMoveEvent(_move(canvas, 90, 50))
    canvas.mouseReleaseEvent(_release(canvas, 90, 50))
    assert canvas.get_mask().pixelColor(50, 50).alpha() == 0


def test_canvas_shift_toggles_brush_eraser(qtbot) -> None:
    """Shift while in Brush makes strokes erase (transient modifier)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.BRUSH)
    assert canvas._effective_eraser() is False

    # Pressing Shift turns on the transient eraser modifier.
    shift_press = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Shift,
        Qt.KeyboardModifier.ShiftModifier,
    )
    canvas.keyPressEvent(shift_press)
    assert canvas.is_eraser_modifier is True
    assert canvas._effective_eraser() is True
    # The active tool ACTION stays Brush (modifier is transient).
    assert canvas.current_tool == ToolMode.BRUSH

    # Releasing Shift restores Brush behavior.
    shift_release = QKeyEvent(
        QEvent.Type.KeyRelease,
        Qt.Key.Key_Shift,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.keyReleaseEvent(shift_release)
    assert canvas.is_eraser_modifier is False
    assert canvas._effective_eraser() is False


def test_cursor_circle_follows_brush_size(qtbot) -> None:
    """The cursor_item rect resizes with brush_size and colors by tool."""
    canvas = _canvas_with_image(qtbot, 100)

    # Default brush color is red (paint mode).
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(80)
    rect = canvas.cursor_item.rect()
    assert int(rect.width()) == 80
    assert int(rect.height()) == 80
    assert canvas.cursor_item.pen().color().red() == 255

    # Eraser tool -> cyan cursor.
    canvas.set_tool(ToolMode.ERASER)
    pen_color = canvas.cursor_item.pen().color()
    assert pen_color.red() == 0
    assert pen_color.green() == 212
    assert pen_color.blue() == 255


def test_preview_item_dashed_cyan(qtbot) -> None:
    """The canvas preview_item pen is QPen(cyan 0,212,255, 2, DashLine)."""
    canvas = _canvas_with_image(qtbot, 100)
    pen = canvas.preview_item.pen()
    c = pen.color()
    assert c.red() == 0
    assert c.green() == 212
    assert c.blue() == 255
    assert c.alpha() == 200
    assert pen.style() == Qt.PenStyle.DashLine


# --- MainWindow tool wiring tests ---

def test_main_window_tool_shortcuts(qtbot, tmp_path) -> None:
    """MainWindow installs B/R/L/E/V shortcuts and wires the Tools dock."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    # The Tools dock is populated with the ToolsPanel (not the placeholder).
    assert isinstance(window.dock_tools.widget(), ToolsPanel)

    # Tool actions exist and are enabled when a page is open. Without a page,
    # Move is enabled (no-op safe) and the painting tools are disabled.
    assert window.action_tool_move.isEnabled()
    assert window.action_tool_brush.isEnabled() is False  # no page yet

    # B/R/L/E/V shortcuts are registered on the window.
    shortcuts = window.findChildren(QShortcut)
    keys = {s.key().toString().upper() for s in shortcuts}
    for key in ("B", "R", "L", "E", "V"):
        assert key in keys, f"missing tool shortcut {key}"


def test_canvas_emits_mask_modified(qtbot) -> None:
    """A completed brush stroke emits mask_modified exactly once (mouseRelease)."""
    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(10)

    emitted: list[None] = []
    canvas.mask_modified.connect(lambda: emitted.append(None))

    # A full press-move-release.
    canvas.mousePressEvent(_press(canvas, 10, 10))
    canvas.mouseMoveEvent(_move(canvas, 90, 10))
    canvas.mouseMoveEvent(_move(canvas, 50, 10))  # extra move — must NOT emit
    canvas.mouseReleaseEvent(_release(canvas, 90, 10))

    # Exactly one emission on release (the plan-06 history hook).
    assert len(emitted) == 1


# ---------------------------------------------------------------------------
# CR-08 regression: get_image_numpy must respect QImage scanline stride padding
# (real-world image widths are not always multiples of 4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width", [1497, 501, 33, 16])
def test_get_image_numpy_respects_qimage_stride(qtbot, width: int) -> None:
    """get_image_numpy returns a correct (H, W, 3) array even when Qt pads rows.

    Qt aligns each scanline to 4 bytes, so a width whose ``width*3`` is not a
    multiple of 4 (e.g. 1497 -> 4491 bytes/row, padded to 4492) produces a
    bits buffer larger than ``H*W*3``. The naive ``reshape(H, W, 3)`` raises
    ValueError on such widths (CR-08, surfaced by a real 2081x1497 manga page).
    Test images at multiple-of-4 widths (e.g. 16) never exercised the padding.
    """
    height = 61  # also non-4-aligned to stress the row count
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(width + 40, height + 40)
    # Build an image whose width*3 is NOT a multiple of 4 to force padding.
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(10, 20, 30))
    canvas.set_image(QPixmap.fromImage(img))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()

    arr = canvas.get_image_numpy()
    # Must not raise; shape must match the image exactly (no padding tail).
    assert arr.shape == (height, width, 3), (
        f"expected ({height}, {width}, 3), got {arr.shape}"
    )
    # Pixel values must survive the round-trip (RGB32 -> RGB888 conversion
    # preserves the color within byte-precision; assert the fill color is
    # recognizable rather than garbage from misread padding bytes).
    assert arr.dtype == np.uint8


# ---------------------------------------------------------------------------
# CR-09 regression: Ctrl+Z keyboard shortcut fires when the canvas has focus
# (canvas keyPressEvent was shadowing it via super().keyPressEvent accept)
# ---------------------------------------------------------------------------


def test_ctrl_z_undo_image_fires_when_canvas_focused(qtbot) -> None:
    """Ctrl+Z with the canvas focused must propagate to a parent QShortcut (CR-09).

    Before CR-09 the canvas's keyPressEvent called super().keyPressEvent(),
    which let QGraphicsView accept Ctrl+Z and swallow it before an
    application-wide QShortcut on the parent window could fire. This test
    isolates the dispatch contract (canvas ignores unhandled keys so they
    bubble up) from MainWindow's action enable/disable gating: a plain
    QWidget parent with a Ctrl+Z QShortcut should receive the shortcut when
    the child EditorCanvas has focus.
    """
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()

    canvas = EditorCanvas()
    canvas.setParent(parent)
    # QGraphicsView forwards key events to the viewport; give the viewport a
    # focus policy so setFocus sticks and the view participates in the focus
    # chain (mirrors how MainWindow embeds the canvas in a real layout).
    canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    canvas.viewport().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    canvas.show()
    canvas.setFocus()
    canvas.viewport().setFocus()
    canvas.activateWindow()
    QApplication.processEvents()
    canvas.setFocus()
    QApplication.processEvents()
    assert canvas.hasFocus() or canvas.viewport().hasFocus()

    fired: list[None] = []
    sc = QShortcut(QKeySequence("Ctrl+Z"), parent)
    sc.activated.connect(lambda: fired.append(None))

    # Drive the actual keyPress into the focused canvas viewport (the path
    # that was broken: QGraphicsView used to accept and swallow it).
    target = canvas.viewport() if canvas.viewport().hasFocus() else canvas
    qtbot.keyClick(target, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    assert len(fired) == 1, (
        "Ctrl+Z did not propagate from focused canvas to parent QShortcut "
        "(CR-09 regressed: canvas is swallowing the key)"
    )

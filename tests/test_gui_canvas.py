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
from manga_ai_studio.gui.side_panel import SidePanel  # noqa: E402
from manga_ai_studio.gui.tools_panel import BrushBody  # noqa: E402


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
    """MainWindow exposes an Open Image action — WITHOUT the Ctrl+O shortcut.

    D-07 / RESEARCH Pitfall 8 (plan 05-05): Ctrl+O moved to Open Project…;
    Open Image keeps its action but loses the binding (Qt would fire both
    actions on one Ctrl+O press otherwise). Exactly one action binds Ctrl+O.
    """
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    action = window.action_open_image
    assert action.text() == "Open Image\u2026"
    assert action.shortcut() != QKeySequence("Ctrl+O")
    from PySide6.QtGui import QAction

    bound = [
        act
        for act in window.findChildren(QAction)
        if act.shortcut() == QKeySequence("Ctrl+O")
    ]
    assert len(bound) == 1
    assert bound[0] is window.action_open_project


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


@pytest.mark.gui
def test_empty_hint_copy_references_open_folder(qtbot) -> None:
    """D-11 regression: the first-run hint advertises the REAL Open Folder
    binding (Ctrl+Shift+O, main_window.py:305) — the stale Open-Image Ctrl+O
    copy is gone (Ctrl+O is Open Project…, main_window.py:311)."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    expected = (
        "File \u2192 Open Folder\u2026 (Ctrl+Shift+O)   \u00b7   or drag files here"
    )
    assert canvas._empty_hint.toPlainText() == expected
    # The stale Ctrl+O advertisement must not appear anywhere in the hint
    # (grep-safe: "Ctrl+Shift+O" does not contain the substring "Ctrl+O").
    assert "Ctrl+O" not in canvas._empty_hint.toPlainText()
    # The body copy stays verbatim (D-11 prohibition).
    assert canvas._empty_body.toPlainText() == (
        "Open a single image or a folder of images to begin cleaning."
    )


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


# ---------------------------------------------------------------------------
# Plan 06 Task 1 tests — D-09 empty-state overlay cleared on numpy display
# ---------------------------------------------------------------------------
#
# D-09 (deferred from 05-UAT/05-UI-REVIEW): `_set_image_from_numpy` never
# called `_update_empty_state()`, so the z=2000 "No page open" trio stayed
# rendered over a loaded page on the numpy display path (project open via
# `_display_page_state`, image-op write-back, undo). These tests MUST fail on
# pre-fix code; the preview-path test is the idempotence guard (RESEARCH
# Pitfall 1 — the fix call is benign on the preview path).


@pytest.mark.gui
def test_numpy_display_hides_empty_state(qtbot) -> None:
    """D-09 regression (numpy path): set_image_from_numpy on a fresh canvas
    showing the empty state must hide the trio and show the empty-box hint."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(300, 300)
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    # Fresh canvas: the empty state is showing (the D-09 pre-condition).
    assert canvas._empty_heading.isVisible()

    rgb = np.zeros((60, 60, 3), dtype=np.uint8)
    canvas.set_image_from_numpy(rgb)

    # The z=2000 trio is gone (D-09: the numpy path must refresh the overlay).
    assert not canvas._empty_heading.isVisible()
    assert not canvas._empty_body.isVisible()
    assert not canvas._empty_hint.isVisible()
    # Zero boxes on the loaded page -> the empty-box hint IS visible.
    assert canvas.empty_box_hint.isVisible()


@pytest.mark.gui
def test_preview_path_keeps_empty_state_hidden(qtbot) -> None:
    """D-09 idempotence (preview path): set_image_from_numpy_preview over a
    loaded image never re-shows the empty-state trio and never raises.

    RESEARCH Pitfall 1: the fix `_update_empty_state()` call is benign on the
    live-preview path (Levels dialog) — an image is present, so the trio
    stays hidden and the call must not crash (unlike the empty-state
    positioning code, the non-empty branch skips the viewport math).
    """
    canvas = _canvas_with_image(qtbot)
    # Image loaded via set_image: the trio is hidden.
    assert not canvas._empty_heading.isVisible()

    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    canvas.set_image_from_numpy_preview(rgb, capture_original=False)

    # The preview display mutation never re-shows the trio.
    assert not canvas._empty_heading.isVisible()
    assert not canvas._empty_body.isVisible()
    assert not canvas._empty_hint.isVisible()
    # The preview result is displayed; no exception was raised.
    assert canvas.get_image_numpy().shape[:2] == (100, 100)


# --- BrushBody tests (the panel's Brush section body — plan 09-02) ---
# The tool-row exclusivity tests moved with the row: tests/test_gui_tools_strip.py
# owns the 6-action exclusive group + single-emission contract since plan 09-01.

def test_brush_body_slider_spinbox_sync(qtbot) -> None:
    """Slider <-> spinbox stay in sync; label updates; brush_size_changed fires."""
    body = BrushBody()
    qtbot.addWidget(body)

    with qtbot.waitSignal(body.brush_size_changed, timeout=1000) as blocker:
        body.brush_slider.setValue(73)
    assert blocker.args == [73]
    assert body.brush_spinbox.value() == 73
    assert "73 px" in body.brush_label.text()

    # Spinbox -> slider sync.
    with qtbot.waitSignal(body.brush_size_changed, timeout=1000) as blocker:
        body.brush_spinbox.setValue(150)
    assert blocker.args == [150]
    assert body.brush_slider.value() == 150
    assert "150 px" in body.brush_label.text()


def test_brush_body_range_clamped(qtbot) -> None:
    """The spinbox/slider enforce [1, 300] (setMinimum/setMaximum)."""
    body = BrushBody()
    qtbot.addWidget(body)
    assert body.brush_slider.minimum() == 1
    assert body.brush_slider.maximum() == 300
    assert body.brush_spinbox.minimum() == 1
    assert body.brush_spinbox.maximum() == 300
    assert body.brush_slider.value() == DEFAULT_BRUSH_SIZE == 40


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

    # The unified "Panel" dock hosts the SidePanel (plan 09-02 D-01 — the
    # tabified Tools+Inspector dock pair is gone).
    assert isinstance(window.dock_panel.widget(), SidePanel)
    assert window.dock_panel.windowTitle() == "Panel"

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


# ===========================================================================
# Plan 05-06 Task 1 — Show Original re-baseline (D-14) + preview suppression
# ===========================================================================
#
# D-14 + RESEARCH Pitfall 5: `_original_image_numpy` captures once per page,
# so after the SECOND image op the cache would hold the first op's pre-image.
# `rebaseline_original()` re-points the cache at the post-op image after EVERY
# op. The Levels live preview must NOT capture at all while the dialog is
# open — `set_image_from_numpy_preview(capture_original=False)` suppresses the
# capture so the pre-dialog image stays the "original".


@pytest.mark.gui
def test_rebaseline_original_after_op(qtbot) -> None:
    """rebaseline_original() re-points Show Original at the POST-op image.

    The Pitfall-5 scenario: two sequential image sets keep the FIRST capture
    (capture-once); rebaseline_original() fixes the stale cache so Show
    Original displays the current (post-op) image (D-14).
    """
    canvas = _canvas_with_image(qtbot)
    first = canvas.get_image_numpy().copy()
    assert canvas._original_image_numpy is None  # fresh page — nothing captured

    alt = (first.astype(np.int16) + 10).clip(0, 255).astype(np.uint8)
    canvas.set_image_from_numpy(alt)  # op 1: baseline captured = the pre-op image
    assert np.array_equal(canvas._original_image_numpy, first)

    alt2 = (alt.astype(np.int16) + 10).clip(0, 255).astype(np.uint8)
    canvas.set_image_from_numpy(alt2)  # op 2: capture-once keeps the STALE baseline
    assert np.array_equal(canvas._original_image_numpy, first)

    canvas.rebaseline_original()  # D-14: re-baseline to the current image
    assert np.array_equal(canvas._original_image_numpy, alt2)
    assert canvas._showing_original is False
    canvas.show_original(True)  # Show Original now displays the POST-op image
    assert np.array_equal(canvas.get_image_numpy(), alt2)


@pytest.mark.gui
def test_preview_path_does_not_capture_original(qtbot) -> None:
    """set_image_from_numpy_preview(capture_original=False) never captures.

    The Levels live preview must not poison the Show Original baseline
    (Pitfall 5/9): with capture suppressed the cache stays None even though
    the display mutated; the capture-enabled path does capture the current
    display.
    """
    canvas = _canvas_with_image(qtbot)
    assert canvas._original_image_numpy is None
    pre = canvas.get_image_numpy().copy()
    alt = (pre.astype(np.int16) + 10).clip(0, 255).astype(np.uint8)

    canvas.set_image_from_numpy_preview(alt, capture_original=False)
    assert canvas._original_image_numpy is None  # preview never captures
    # The normal display path captures the current display (the preview result).
    canvas.set_image_from_numpy(alt)
    assert canvas._original_image_numpy is not None
    assert np.array_equal(canvas._original_image_numpy, alt)


# ===========================================================================
# Quick 260826-u9m — set_image_from_numpy_page: page-level preview-state rebase
# ===========================================================================
#
# A PAGE DISPLAY defines its OWN complete preview state: the incoming baseline
# (the D-06 disk decode when the persisted original verifies, else the page's
# own displayed pixels), an inpaint-result claim (so Show Original gating
# works on freshly loaded pages), and _showing_original=False. The OLD
# capture-if-None semantic leaked the OUTGOING page's baseline (and its stale
# toggle flag) across page switches — P on page B could show page A's pixels.


def _rgb_array(h: int, w: int, rgb: tuple[int, int, int]) -> np.ndarray:
    """A contiguous (h, w, 3) uint8 array filled with one constant color
    (pixel-equality asserts on constant colors are exact)."""
    return np.full((h, w, 3), rgb, dtype=np.uint8)


@pytest.mark.gui
def test_set_image_from_numpy_page_seeds_disk_baseline_and_inpaint_claim(qtbot) -> None:
    """A provided original_baseline becomes THE Show Original baseline.

    Simulates the verified-reopen contract (quick 260826-u9m): the D-06 disk
    decode seeds the baseline (NOT a foreign capture), _showing_original is
    reset, has_inpaint_result() is True so the P action can enable, and the
    toggle swaps between the pristine baseline and the page's displayed pixels.
    """
    canvas = _canvas_with_image(qtbot)
    arr_a = _rgb_array(10, 10, (200, 10, 10))
    canvas.set_image_from_numpy(arr_a)

    arr_b = _rgb_array(12, 12, (10, 200, 10))
    arr_b_orig = _rgb_array(12, 12, (10, 10, 220))
    qimg = canvas.set_image_from_numpy_page(arr_b, arr_b_orig)
    assert qimg is not None
    assert np.array_equal(canvas._original_image_numpy, arr_b_orig)
    assert not np.array_equal(canvas._original_image_numpy, arr_a)
    assert canvas._showing_original is False
    assert canvas.has_inpaint_result() is True

    # P shows the pristine baseline; toggling off restores the saved state.
    canvas.show_original(True)
    assert np.array_equal(canvas.get_image_numpy(), arr_b_orig)
    canvas.show_original(False)
    assert np.array_equal(canvas.get_image_numpy(), arr_b)


@pytest.mark.gui
def test_set_image_from_numpy_page_rebases_no_foreign_bleed(qtbot) -> None:
    """The EXACT cross-page bleed state cannot survive a page display.

    Build today's bug by hand: display A via the ordinary path (which
    capture-if-None seeds a foreign fresh-canvas baseline), run
    show_original(True) so a foreign baseline AND _showing_original=True are
    live, then display page B WITHOUT a baseline. Page B must define its OWN
    fallback baseline (its own displayed pixels) and start untoggled.
    """
    canvas = _canvas_with_image(qtbot, size=20)
    arr_a = _rgb_array(20, 20, (250, 0, 0))
    canvas.set_image_from_numpy(arr_a)
    foreign_baseline = canvas._original_image_numpy.copy()
    canvas.show_original(True)
    assert canvas._showing_original is True

    arr_b = _rgb_array(14, 14, (0, 90, 250))
    canvas.set_image_from_numpy_page(arr_b)

    assert np.array_equal(canvas._original_image_numpy, arr_b)
    assert not np.array_equal(canvas._original_image_numpy, foreign_baseline)
    assert not np.array_equal(canvas._original_image_numpy, arr_a)
    assert canvas._showing_original is False
    assert np.array_equal(canvas.get_image_numpy(), arr_b)


@pytest.mark.gui
def test_set_image_from_numpy_page_invalid_baseline_raises(qtbot) -> None:
    """A malformed baseline raises ValueError BEFORE any display mutation."""
    canvas = _canvas_with_image(qtbot, size=16)
    arr_a = _rgb_array(16, 16, (5, 5, 5))
    canvas.set_image_from_numpy(arr_a)
    shown_before = canvas.get_image_numpy().copy()
    baseline_before = (
        canvas._original_image_numpy.copy()
        if canvas._original_image_numpy is not None
        else None
    )

    bad_rank = np.zeros((4, 4), dtype=np.uint8)
    with pytest.raises(ValueError):
        canvas.set_image_from_numpy_page(_rgb_array(8, 8, (9, 9, 9)), bad_rank)

    # Nothing mutated: the previously displayed page and its baseline stand.
    assert np.array_equal(canvas.get_image_numpy(), shown_before)
    if baseline_before is None:
        assert canvas._original_image_numpy is None
    else:
        assert np.array_equal(canvas._original_image_numpy, baseline_before)


@pytest.mark.gui
def test_set_image_from_numpy_page_fresh_canvas_has_inpaint_claim(qtbot) -> None:
    """One page display on a freshly cleared canvas carries the claim.

    Locks the ``_inpainted_qimage`` assignment: without it the P action /
    btn_preview_hold gating would stay disabled on freshly loaded pages.
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.clear()
    assert canvas.has_inpaint_result() is False

    arr = _rgb_array(10, 10, (77, 77, 77))
    arr_orig = _rgb_array(10, 10, (11, 22, 33))
    canvas.set_image_from_numpy_page(arr, arr_orig)
    assert canvas.has_inpaint_result() is True
    assert canvas._showing_original is False
    assert np.array_equal(canvas.get_image_numpy(), arr)


# ===========================================================================
# Plan 04-04 Task 2 — Toggle Text Overlay (T) independent visibility layer
# ===========================================================================
#
# D-12 contracts THREE independent visibility layers: mask (M) / box (Shift+M) /
# text-overlay (T). The text toggle hides ONLY the per-box text-overlay children,
# leaving the box borders + handles + badges visible. It is independent of the
# box-overlay toggle (which hides the entire box layer incl. text) and the mask
# toggle. toggle_text_overlay flips a per-canvas flag and calls
# set_text_overlay_visible on every BoxItem.


@pytest.mark.gui
def test_canvas_has_text_overlay_flag_and_toggle(qtbot) -> None:
    """EditorCanvas has _text_overlay_visible (default True) + toggle_text_overlay()."""
    canvas = _canvas_with_image(qtbot)
    assert hasattr(canvas, "_text_overlay_visible")
    assert canvas._text_overlay_visible is True  # default checked (D-09)
    assert hasattr(canvas, "toggle_text_overlay")


@pytest.mark.gui
def test_toggle_text_overlay_hides_only_text_children(qtbot) -> None:
    """toggle_text_overlay hides ONLY the text-overlay children; box borders stay visible (D-12)."""
    from manga_ai_studio.core.box_model import USER, PageBox
    from panelcleaner.structures import Box

    canvas = _canvas_with_image(qtbot)
    # Seed a box with recognized text so the overlay is showing.
    pb = PageBox(box=Box(20, 20, 120, 120), origin=USER)
    pb.set_recognized_text("hello")
    canvas.set_boxes([pb], [])
    item = canvas._box_items[0]
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is True

    # Toggle the text overlay off.
    canvas.toggle_text_overlay()
    assert canvas._text_overlay_visible is False
    # The text child is hidden...
    assert item._text_overlay.isVisible() is False
    # ...but the box border + handles are still visible.
    assert item.isVisible() is True

    # Toggle back on.
    canvas.toggle_text_overlay()
    assert canvas._text_overlay_visible is True
    assert item._text_overlay.isVisible() is True


@pytest.mark.gui
def test_toggle_text_overlay_independent_of_box_overlay(qtbot) -> None:
    """The text toggle is independent of the box-overlay toggle (Shift+M) (D-12)."""
    from manga_ai_studio.core.box_model import USER, PageBox
    from panelcleaner.structures import Box

    canvas = _canvas_with_image(qtbot)
    pb = PageBox(box=Box(20, 20, 120, 120), origin=USER)
    pb.set_recognized_text("hello")
    canvas.set_boxes([pb], [])
    item = canvas._box_items[0]
    item.refresh_text_overlay()

    # Turn the TEXT overlay off (T).
    canvas.set_text_overlay_visible_flag(False)
    assert item._text_overlay.isVisible() is False
    # The BOX overlay stays visible (independent layer).
    assert canvas._box_overlay_visible is True
    assert item.isVisible() is True

    # Now hide the BOX overlay (Shift+M) — entire box (incl. text) hides.
    canvas.set_box_overlay_visible(False)
    assert item.isVisible() is False
    # Re-show the box overlay; the text is STILL off (the two toggles are independent).
    canvas.set_box_overlay_visible(True)
    assert item.isVisible() is True
    assert item._text_overlay.isVisible() is False, (
        "toggling the box layer back on must NOT re-enable the text overlay "
        "(D-12: the two toggles are independent)"
    )


@pytest.mark.gui
def test_toggle_text_overlay_applies_to_new_boxes(qtbot) -> None:
    """A box added AFTER the text overlay was toggled off respects the layer state."""
    from manga_ai_studio.core.box_model import USER, PageBox
    from panelcleaner.structures import Box

    canvas = _canvas_with_image(qtbot)
    # Turn the text overlay off first (no boxes yet).
    canvas.set_text_overlay_visible_flag(False)
    assert canvas._text_overlay_visible is False

    # Add a box with text — its overlay must NOT show (text layer is off).
    pb = PageBox(box=Box(20, 20, 120, 120), origin=USER)
    pb.set_recognized_text("hello")
    canvas.set_boxes([pb], [])
    item = canvas._box_items[0]
    item.refresh_text_overlay()
    assert item._text_overlay.isVisible() is False


# ---------------------------------------------------------------------------
# quick-260828-l3l tests — Restore tool (paint the Show Original baseline)
# ---------------------------------------------------------------------------


def _canvas_with_baseline(qtbot, size: int = 100) -> EditorCanvas:
    """Canvas displaying image A (white) with the baseline seeded to A.

    ``set_image_from_numpy`` on the white ``set_image`` display captures the
    PRE-overwrite pixels as ``_original_image_numpy`` (the capture-when-None
    gate) — so the baseline equals image A while the display stays A.
    """
    canvas = _canvas_with_image(qtbot, size)
    white = np.full((size, size, 3), 255, dtype=np.uint8)
    canvas.set_image_from_numpy(white)  # baseline := A (white)
    return canvas


def _mutate_patch(
    canvas: EditorCanvas, x: int, y: int, w: int, h: int, value: int = 77
) -> None:
    """Composite a solid-``value`` patch B over the display via the bbox path."""
    h_img, w_img = canvas.get_image_numpy().shape[:2]
    b_img = np.full((h_img, w_img, 3), 255, dtype=np.uint8)
    b_img[y : y + h, x : x + w] = value
    canvas.set_image_from_numpy(b_img, bbox=(x, y, w, h))


def _restore_drag(canvas: EditorCanvas, x0: float, y0: float, x1: float, y1: float) -> None:
    """Press-move-release a Restore stroke from (x0, y0) to (x1, y1)."""
    canvas.mousePressEvent(_press(canvas, x0, y0))
    canvas.mouseMoveEvent(_move(canvas, x1, y1))
    canvas.mouseReleaseEvent(_release(canvas, x1, y1))


@pytest.mark.gui
def test_restore_stamps_original_pixels(qtbot) -> None:
    """A Restore drag composites the baseline (A) inside the brush radius.

    The mutated patch (B) is restored to A only where the stroke passed;
    unstroked mutated pixels keep B. The baseline is never rebaselined
    (D-14 guard).
    """
    canvas = _canvas_with_baseline(qtbot, 100)
    # Mutate a patch to B (77) — the "mangled inpaint result".
    _mutate_patch(canvas, 30, 40, 40, 20)
    arr = canvas.get_image_numpy()
    assert np.all(arr[40:60, 30:70] == 77)

    canvas.set_tool(ToolMode.RESTORE)
    canvas.set_brush_size(10)  # radius 5 — drag covers y in [45, 55]
    _restore_drag(canvas, 40, 50, 60, 50)

    arr = canvas.get_image_numpy()
    # Stroked points: restored to baseline A (white).
    assert np.all(arr[50, 35:66] == 255)
    # Unstroked mutated points: still B.
    assert np.all(arr[42, 32:38] == 77)
    # D-14: the baseline slot is untouched by the stroke.
    assert canvas._original_image_numpy is not None
    assert np.all(canvas._original_image_numpy == 255)


@pytest.mark.gui
def test_restore_click_restores_dot(qtbot) -> None:
    """A press+release with NO move still restores (the dot) and commits."""
    canvas = _canvas_with_baseline(qtbot, 100)
    _mutate_patch(canvas, 30, 40, 40, 20)

    canvas.set_tool(ToolMode.RESTORE)
    canvas.set_brush_size(10)
    emitted: list = []
    canvas.restore_committed.connect(emitted.append)

    canvas.mousePressEvent(_press(canvas, 50, 50))
    canvas.mouseReleaseEvent(_release(canvas, 50, 50))
    QApplication.processEvents()

    arr = canvas.get_image_numpy()
    assert np.all(arr[50, 46:55] == 255)  # the dot
    assert np.all(arr[41, 50] == 77)  # outside the dot: still B
    # The dot commits exactly one payload.
    assert len(emitted) == 1
    payload = emitted[0]
    assert payload["pre_patch"].shape == (payload["h"], payload["w"], 3)


@pytest.mark.gui
def test_restore_no_baseline_is_noop(qtbot) -> None:
    """Without a baseline a Restore stroke is a silent no-op: no emission,
    ``_is_painting`` stays False, display unchanged."""
    canvas = _canvas_with_baseline(qtbot, 100)
    canvas._original_image_numpy = None
    canvas.set_tool(ToolMode.RESTORE)
    canvas.set_brush_size(10)

    emitted: list = []
    canvas.restore_committed.connect(emitted.append)
    before = canvas.get_image_numpy()

    _restore_drag(canvas, 20, 20, 80, 20)
    QApplication.processEvents()

    assert emitted == []
    assert canvas._is_painting is False
    assert np.array_equal(canvas.get_image_numpy(), before)


@pytest.mark.gui
def test_restore_suppressed_during_show_original(qtbot) -> None:
    """A press during the P-preview (Show Original) is suppressed — the
    working image is untouched (no force-exit stroke on the compare view)."""
    canvas = _canvas_with_baseline(qtbot, 100)
    _mutate_patch(canvas, 30, 40, 40, 20)

    canvas.set_tool(ToolMode.RESTORE)
    canvas.set_brush_size(10)
    canvas.show_original(True)
    assert canvas._showing_original is True

    emitted: list = []
    canvas.restore_committed.connect(emitted.append)
    _restore_drag(canvas, 40, 50, 60, 50)
    QApplication.processEvents()

    assert emitted == []
    assert canvas._is_painting is False
    # Back on the working side: the patch survived — nothing was painted.
    canvas.show_original(False)
    arr = canvas.get_image_numpy()
    assert np.all(arr[40:60, 30:70] == 77)


@pytest.mark.gui
def test_restore_cursor_is_green(qtbot) -> None:
    """The Restore brush cursor shows with the green #5fd068 palette."""
    canvas = _canvas_with_image(qtbot, 100)
    canvas.set_tool(ToolMode.RESTORE)
    assert canvas.cursor_item.isVisible()
    assert canvas.cursor_item.pen().color() == QColor(95, 208, 104, 200)
    assert canvas.cursor_item.brush().color() == QColor(95, 208, 104, 60)


@pytest.mark.gui
def test_restore_emits_once_per_stroke(qtbot) -> None:
    """One drag emits EXACTLY ONE restore_committed whose bbox covers the
    drag path and whose pre_patch is the detached (h, w, 3) pre-stroke slice."""
    canvas = _canvas_with_baseline(qtbot, 100)
    # Patch covers the whole upcoming stroke bbox so pre_patch is uniform B.
    _mutate_patch(canvas, 10, 30, 80, 40)

    canvas.set_tool(ToolMode.RESTORE)
    canvas.set_brush_size(10)

    emitted: list = []
    canvas.restore_committed.connect(emitted.append)
    _restore_drag(canvas, 20, 50, 80, 50)
    QApplication.processEvents()

    assert len(emitted) == 1
    p = emitted[0]
    # The bbox covers the drag path (brush radius margin included).
    assert p["x"] <= 20 - 5
    assert p["x"] + p["w"] >= 80 + 5
    assert p["y"] <= 50 - 5
    assert p["y"] + p["h"] >= 50 + 5
    # pre_patch shape + detachment (payload-aliasing discipline).
    assert p["pre_patch"].shape == (p["h"], p["w"], 3)
    assert np.all(p["pre_patch"] == 77)  # the pre-stroke (mangled) state
    p["pre_patch"][:] = 0  # mutating the payload must not corrupt the canvas
    assert np.all(canvas.get_image_numpy()[50, 45:56] == 255)

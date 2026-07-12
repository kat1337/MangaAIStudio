"""GUI smoke tests for the Walking Skeleton (VALIDATION.md §Wave 0).

Uses pytest-qt's ``qtbot`` fixture. Guards with ``pytest.importorskip`` so
collection degrades gracefully where PySide6 is unavailable. These tests need a
display; on headless CI they would be skipped/fail at Qt init — the Wave 0 gate
runs on the developer's Windows machine.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage, QPalette, QPixmap  # noqa: E402
from PySide6.QtWidgets import QGraphicsPixmapItem, QApplication  # noqa: E402

from manga_ai_studio.app import create_app  # noqa: E402
from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.canvas import (  # noqa: E402
    MAX_IMAGE_DIMENSION,
    MAX_ZOOM_FACTOR,
    ZOOM_TICK_FACTOR,
    EditorCanvas,
    validate_image_path,
)
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


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


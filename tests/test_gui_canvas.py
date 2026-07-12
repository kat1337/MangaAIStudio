"""GUI smoke tests for the Walking Skeleton (VALIDATION.md §Wave 0).

Uses pytest-qt's ``qtbot`` fixture. Guards with ``pytest.importorskip`` so
collection degrades gracefully where PySide6 is unavailable. These tests need a
display; on headless CI they would be skipped/fail at Qt init — the Wave 0 gate
runs on the developer's Windows machine.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage, QPalette, QPixmap  # noqa: E402
from PySide6.QtWidgets import QGraphicsPixmapItem, QApplication  # noqa: E402

from manga_ai_studio.app import create_app  # noqa: E402
from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _solid_pixmap(size: int, color: QColor) -> QPixmap:
    """Build a solid-color QPixmap of the given size."""
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


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

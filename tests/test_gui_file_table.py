"""FileTable + MainWindow integration tests (VALIDATION.md plan 02 rows 47-48).

Uses pytest-qt's ``qtbot`` fixture. Guards with ``pytest.importorskip`` so
collection degrades gracefully where PySide6 is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.file_table import FileTable  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _write_png(path: Path, size: int = 8, color: str = "blue") -> Path:
    """Write a small solid PNG at ``path`` and return it."""
    img = QImage(size, size, QImage.Format.Format_RGB32)
    from PySide6.QtGui import QColor

    img.fill(QColor(color))
    img.save(str(path), "PNG")
    return path


@pytest.fixture()
def folder_of_pages(tmp_path: Path) -> Path:
    """Build a temp folder with 3 pages named out of lexical order."""
    for name in ("page2.png", "page10.png", "page1.png"):
        _write_png(tmp_path / name)
    return tmp_path


# ---------------------------------------------------------------------------
# FileTable tests
# ---------------------------------------------------------------------------

def test_load_folder_populates(qtbot, folder_of_pages: Path) -> None:
    """set_pages creates one row per path, natural-sorted (page1, page2, page10)."""
    table = FileTable()
    qtbot.addWidget(table)

    paths = [p for p in folder_of_pages.iterdir() if p.suffix == ".png"]
    table.set_pages(paths)

    assert table.model().rowCount() == 3
    # Natural sort: page1 < page2 < page10 (NOT page1, page10, page2).
    row0_text = table.model().item(0).text()
    row1_text = table.model().item(1).text()
    row2_text = table.model().item(2).text()
    assert row0_text.startswith("page1.png")
    assert row1_text.startswith("page2.png")
    assert row2_text.startswith("page10.png")


def test_navigation_click_emits_signal(qtbot, folder_of_pages: Path) -> None:
    """Selecting a row emits file_clicked(Path) with that row's natural-sorted path."""
    table = FileTable()
    qtbot.addWidget(table)

    paths = [p for p in folder_of_pages.iterdir() if p.suffix == ".png"]
    table.set_pages(paths)

    received: list[Path] = []
    table.file_clicked.connect(lambda p: received.append(p))

    # Select the first row (page1.png after natural sort).
    table.setCurrentIndex(table.model().index(0, 0))
    with qtbot.waitSignal(table.file_clicked, timeout=1000):
        # Click is emitted by FileTable.clicked; force it via the model index.
        table.clicked.emit(table.model().index(0, 0))

    assert received, "file_clicked was not emitted"
    assert received[0].name == "page1.png"
    # current_path agrees with the selection.
    assert table.current_path() is not None
    assert table.current_path().name == "page1.png"


def test_thumbnail_64(qtbot, folder_of_pages: Path) -> None:
    """Each row's decoration is a pixmap within 64x64 (letterboxed)."""
    table = FileTable()
    qtbot.addWidget(table)

    paths = [p for p in folder_of_pages.iterdir() if p.suffix == ".png"]
    table.set_pages(paths)

    item = table.model().item(0)
    icon = item.icon()
    sizes = icon.availableSizes()
    assert sizes, "thumbnail icon has no sizes"
    # Every available size fits within the 64x64 icon area.
    for sz in sizes:
        assert sz.width() <= 64
        assert sz.height() <= 64


def test_current_row_highlight(qtbot) -> None:
    """The FileTable QSS carries the accent selected-row style."""
    table = FileTable()
    qtbot.addWidget(table)
    qss = table.styleSheet()
    assert "rgba(0, 212, 255, 0.18)" in qss
    assert "#00d4ff" in qss
    # The selected-row left border is the accent.
    assert "border-left: 2px solid #00d4ff" in qss


# ---------------------------------------------------------------------------
# MainWindow tests
# ---------------------------------------------------------------------------

def test_open_folder_action(qtbot, tmp_path: Path) -> None:
    """MainWindow exposes an Open Folder action with Ctrl+Shift+O."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    action = window.action_open_folder
    assert action.text() == "Open Folder\u2026"
    assert "Ctrl+Shift+O" in action.shortcut().toString()


def test_drop_images_signal(qtbot, folder_of_pages: Path) -> None:
    """Dropping mimedata with image urls emits files_dropped(list[Path])."""
    table = FileTable()
    qtbot.addWidget(table)

    received: list[list] = []
    table.files_dropped.connect(lambda paths: received.append(paths))

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    urls = [
        QUrl.fromLocalFile(str(folder_of_pages / "page1.png")),
        QUrl.fromLocalFile(str(folder_of_pages / "page2.png")),
    ]
    mime = QMimeData()
    mime.setUrls(urls)

    # Synthesize a drop event. We construct it with a no-op device pixel data
    # because dropEvent only reads mimeData().urls() in our implementation.
    drop = QDropEvent(QPointF(0, 0), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.dropEvent(drop)

    assert received, "files_dropped was not emitted"
    paths = received[0]
    assert all(isinstance(p, Path) for p in paths)
    assert len(paths) == 2
    names = {p.name for p in paths}
    assert "page1.png" in names
    assert "page2.png" in names


def test_status_bar_page_progress(qtbot, folder_of_pages: Path) -> None:
    """After loading N pages and selecting index i, status reads 'Page {i+1} / {N}'."""
    pm = ProfileManager(folder_of_pages)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    # Load the folder directly via the same path open_folder uses.
    window._load_folder(folder_of_pages)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()

    # _set_pages auto-selects page 1 -> status should read "Page 1 / 3".
    assert window.status_bar_right.text() == "Page 1 / 3"

    # Now select index 1 (page2.png) and confirm the status updates.
    second = folder_of_pages / "page2.png"
    window.file_table.select_path(second)
    window.on_page_selected(second)
    QApplication.processEvents()
    assert window.status_bar_right.text() == "Page 2 / 3"

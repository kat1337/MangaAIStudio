"""GUI tests for the project-persistence session layer (plan 05-05, PROJ-01).

Covers Save Project… / Open Project… (D-07/D-08/D-09) against the real
``MainWindow`` (pytest-qt) with ``tmp_path`` fixture folders:
- Task 1: the Save-side tracer — folder write, clean-session flash, action
  gating, the Ctrl+O remap, and the dirty-``*`` title.
- Task 2: the Open-side session rebuild — D-11-seam restore, per-page
  embedded ``current_image`` population, chapter-climb (D-09), corrupt-file
  isolation, and the D-06 missing-original navigation fallback.
- Task 3: the Unsaved Changes gate, Recent Projects (QSettings), and the
  ``_op_running`` action gating.

All QSettings access is isolated to a throwaway INI file per test — the
tests must never touch the user's real registry settings.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.project_io import load_project
from manga_ai_studio.gui.main_window import MainWindow


# ---------------------------------------------------------------- helpers

def _make_pages(folder: Path, count: int = 2, size: int = 60) -> list[Path]:
    """Create ``count`` real PNG pages in ``folder``; return their paths."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        p = folder / f"page_{i + 1:02d}.png"
        PILImage.new("RGB", (size, size), color=(30 * (i + 1), 60, 90)).save(p)
        paths.append(p)
    return paths


def _make_window(qtbot, tmp_path, folder: Path | None = None, size: int = 60) -> MainWindow:
    """Build a MainWindow; when ``folder`` is given, open it as a session."""
    if folder is not None:
        _make_pages(folder, size=size)
    pm = ProfileManager(tmp_path / "config")
    window = MainWindow(pm)
    qtbot.addWidget(window)
    if folder is not None:
        window._load_folder(folder)
        QApplication.processEvents()
    window.show()
    QApplication.processEvents()
    return window


def _isolate_settings(window: MainWindow, tmp_path: Path, monkeypatch) -> None:
    """Point the window's QSettings at a throwaway INI (never the real one)."""
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(
        window,
        "_settings",
        lambda: QSettings(str(ini), QSettings.Format.IniFormat),
    )


def _stub_dir_dialog(monkeypatch, target: Path | None) -> list:
    """Stub QFileDialog.getExistingDirectory to return ``target`` (None =
    cancel). Returns the call list for assertion."""
    calls: list = []

    def _fake(*a, **k):
        calls.append((a, k))
        return None if target is None else str(target)

    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(_fake)
    )
    return calls


def _stub_open_dialog(monkeypatch, target: Path | None) -> list:
    """Stub QFileDialog.getOpenFileName to return ``(target, "")``."""
    calls: list = []

    def _fake(*a, **k):
        calls.append((a, k))
        return ("", "") if target is None else (str(target), "")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(_fake))
    return calls


def _save_as(window: MainWindow, target_dir: Path, monkeypatch) -> None:
    """Run the Save As flow with the folder dialog stubbed to ``target_dir``."""
    _stub_dir_dialog(monkeypatch, target_dir)
    window._save_project(force_as=True)
    QApplication.processEvents()


def _dirty(window: MainWindow) -> None:
    """Mark the session dirty through a real mutation signal (mask stroke)."""
    window.canvas.mask_modified.emit()
    QApplication.processEvents()


def _find_action(window: MainWindow, text: str):
    """Return the first QAction with ``text`` across the window."""
    from PySide6.QtGui import QAction

    for act in window.findChildren(QAction):
        if act.text() == text:
            return act
    return None


# ------------------------------------------------------------- Task 1 tests

@pytest.mark.gui
def test_save_disabled_with_no_page(qtbot, tmp_path) -> None:
    """Fresh MainWindow -> Save Project… / Save Project As… are disabled."""
    window = _make_window(qtbot, tmp_path)
    assert not window.action_save_project.isEnabled()
    assert not window.action_save_project_as.isEnabled()


@pytest.mark.gui
def test_save_project_writes_project_folder(qtbot, tmp_path, monkeypatch) -> None:
    """Save Project… writes a .mas-project folder: manifest + per-page files,
    in sidebar order; dirty state clears and the status flash shows."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    # Dirty the session (mask stroke mutation signal).
    _dirty(window)
    assert window._session_dirty()

    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)

    assert (project_dir / "manifest.json").is_file()
    mas_files = sorted(p.name for p in project_dir.glob("*.mas"))
    assert mas_files == ["page_01.mas", "page_02.mas"]
    # Manifest page order matches the sidebar order.
    manifest = load_project(project_dir / "manifest.json")
    assert [p["name"] for p in manifest["pages"]] == ["page_01", "page_02"]
    assert window._project_dir == project_dir
    assert not window._session_dirty()
    assert "Saved project" in window.status_bar_left.text()


@pytest.mark.gui
def test_save_clean_session_no_changes_flash(qtbot, tmp_path, monkeypatch) -> None:
    """A clean session: Save Project… flashes 'No changes to save.' and
    writes nothing (the folder dialog is never shown)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    calls = _stub_dir_dialog(monkeypatch, tmp_path / "never.mas-project")

    window._save_project()
    QApplication.processEvents()

    assert "No changes to save." in window.status_bar_left.text()
    assert calls == []  # no folder dialog -> no folder written
    assert not (tmp_path / "never.mas-project").exists()
    assert window._project_dir is None


@pytest.mark.gui
def test_ctrl_o_opens_project_not_image(qtbot, tmp_path) -> None:
    """EXACTLY ONE action binds Ctrl+O — Open Project… (Pitfall 8 / D-07)."""
    window = _make_window(qtbot, tmp_path)
    from PySide6.QtGui import QAction

    bound = [
        act
        for act in window.findChildren(QAction)
        if act.shortcut() == QKeySequence("Ctrl+O")
    ]
    assert len(bound) == 1
    assert bound[0] is window.action_open_project
    # Open Image keeps its action but lost the binding.
    assert window.action_open_image.shortcut() != QKeySequence("Ctrl+O")


@pytest.mark.gui
def test_dirty_title_suffix(qtbot, tmp_path, monkeypatch) -> None:
    """A mutation appends '*' as the LAST title character; save clears it."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    assert window.windowTitle() == "Manga AI Studio \u2014 page_01.png"
    assert not window.windowTitle().endswith("*")

    _dirty(window)
    assert window.windowTitle().endswith("*")
    assert window.windowTitle() == "Manga AI Studio \u2014 page_01.png*"

    _save_as(window, tmp_path / "chapter.mas-project", monkeypatch)
    assert not window.windowTitle().endswith("*")
    assert window.windowTitle() == "Manga AI Studio \u2014 chapter \u2014 page_01.png"

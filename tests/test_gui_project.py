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


def _save_as(
    window: MainWindow, target_dir: Path, monkeypatch, isolate_settings: bool = True
) -> None:
    """Run the Save As flow with the folder dialog stubbed to ``target_dir``.

    QSettings are isolated to a throwaway INI so a save's
    ``_add_recent_project`` never touches the user's real registry settings
    (``isolate_settings=False`` keeps an already-isolated store, e.g. for
    multi-save Recent Projects tests).
    """
    _stub_dir_dialog(monkeypatch, target_dir)
    if isolate_settings:
        _isolate_settings_any(window, monkeypatch)
    window._save_project(force_as=True)
    QApplication.processEvents()


def _isolate_settings_any(window: MainWindow, monkeypatch) -> None:
    """Point the window's QSettings at a throwaway INI (never the real one)."""
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".ini")
    os.close(fd)
    monkeypatch.setattr(
        window,
        "_settings",
        lambda: QSettings(path, QSettings.Format.IniFormat),
    )


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


def _stub_messagebox_exec(monkeypatch, role=None, capture: list | None = None):
    """Stub QMessageBox.exec to click the button with ``role`` (None = Esc /
    no button, simulating cancel). Records each shown dialog's windowTitle
    into ``capture`` when given."""

    def _exec(self, *a, **k):
        if capture is not None:
            capture.append(self.windowTitle())
        if role is not None:
            for btn in self.buttons():
                if self.buttonRole(btn) == role:
                    self.clickedButton = lambda *a2, **k2: btn
                    return QMessageBox.DialogCode.Accepted
        self.clickedButton = lambda *a2, **k2: None
        return QMessageBox.DialogCode.Rejected

    monkeypatch.setattr(QMessageBox, "exec", _exec)


def _capture_critical(monkeypatch) -> list:
    """Capture QMessageBox.critical calls; return [(title, text), ...]."""
    captured: list = []

    def _fake(parent, title, text, *a, **k):
        captured.append((title, text))
        return None

    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.QMessageBox.critical", _fake
    )
    return captured


def _capture_warning(monkeypatch) -> list:
    """Capture QMessageBox.warning calls; return [(title, text), ...]."""
    captured: list = []

    def _fake(parent, title, text, *a, **k):
        captured.append((title, text))
        return None

    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.QMessageBox.warning", _fake
    )
    return captured


def _seed_mask_content(window: MainWindow) -> None:
    """Paint a full red mask on the canvas (real painted content)."""
    mask = QImage(60, 60, QImage.Format.Format_ARGB32)
    mask.fill(QColor(255, 0, 0, 255))
    window.canvas.set_mask(mask)


def _seed_boxes_with_text(window: MainWindow) -> None:
    """Seed one user box with a TextBlock payload (text + translation)."""
    from manga_ai_studio.core.box_model import USER, PageBox
    from panelcleaner.comic_text_detector.utils.textblock import TextBlock
    from panelcleaner.structures import Box

    tb = TextBlock(
        [5, 5, 40, 20],
        lines=[[[5, 5], [40, 5], [40, 20], [5, 20]]],
        vertical=False,
        language="ja",
    )
    tb.text = "hello"
    tb.translation = "\u3053\u3093\u306b\u3061\u306f"  # こんにちは
    pb = PageBox(box=Box(5, 5, 40, 20), origin=USER, payload=tb)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pb], [])
    finally:
        window._suppress_boxes_push = False


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


# ------------------------------------------------------------- Task 2 tests

@pytest.mark.gui
def test_open_project_restores_session(qtbot, tmp_path, monkeypatch) -> None:
    """Save a 2-page session, reopen it: sidebar order, mask, boxes (incl.
    text/translation), title, and fresh undo history are all restored."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _seed_mask_content(window)
    _seed_boxes_with_text(window)
    _dirty(window)

    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)

    # Reopen in a fresh window via the manifest path.
    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()

    assert [imf.path.name for imf in window2.image_files] == [
        "page_01.png",
        "page_02.png",
    ]
    assert window2._project_dir == project_dir
    assert window2._project_name == "chapter"
    assert window2.windowTitle() == (
        "Manga AI Studio \u2014 chapter \u2014 page_01.png"
    )
    # Mask restored with content (D-11 seam).
    assert window2.image_files[0].mask is not None
    assert window2.image_files[0].has_mask_content()
    # Boxes round-trip incl. text + translation.
    assert window2.image_files[0].boxes is not None
    restored = window2.image_files[0].boxes[0]
    assert restored.payload.text == "hello"
    assert restored.payload.translation == "\u3053\u3093\u306b\u3061\u306f"
    # D-05: fresh undo history on reopen.
    assert not window2.history.can_undo()
    # The canvas shows the first page's image.
    assert window2.canvas.get_image_numpy().shape[:2] == (60, 60)


@pytest.mark.gui
def test_open_project_populates_all_current_images(qtbot, tmp_path, monkeypatch) -> None:
    """BOTH pages get their embedded image decoded into current_image — incl.
    the non-displayed second page whose original was deleted (the 05-08 batch
    dims fallback); the open-status flash notes the missing original."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)

    # Delete page 2's original AFTER saving (D-06 missing-original state).
    (chapter / "page_02.png").unlink()

    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()

    for imf in window2.image_files:
        assert imf.current_image is not None
        assert imf.current_image.shape[:2] == (60, 60)
    assert not window2.image_files[1].original_verified
    assert "Original file not found" in window2.status_bar_left.text()


@pytest.mark.gui
def test_open_page_mas_with_sibling_prompt(qtbot, tmp_path, monkeypatch) -> None:
    """A page .mas with a sibling manifest pops the Chapter Detected prompt:
    Open Page Only loads one page; Open Project loads the chapter; Esc
    cancels the action entirely (previous session untouched)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)
    page_mas = project_dir / "page_01.mas"
    assert page_mas.is_file()

    # --- [Open Page Only] -> single-page standalone session ---
    titles: list = []
    _stub_messagebox_exec(monkeypatch, role=QMessageBox.ButtonRole.RejectRole, capture=titles)
    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, page_mas)
    window2._open_project()
    QApplication.processEvents()
    assert "Chapter Detected" in titles
    assert len(window2.image_files) == 1
    assert window2.image_files[0].current_image is not None

    # --- [Open Project] -> the chapter loads via the manifest ---
    titles.clear()
    _stub_messagebox_exec(monkeypatch, role=QMessageBox.ButtonRole.AcceptRole, capture=titles)
    window3 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, page_mas)
    window3._open_project()
    QApplication.processEvents()
    assert len(window3.image_files) == 2
    assert window3._project_name == "chapter"

    # --- Esc (no button clicked) -> action cancelled, session untouched ---
    _stub_messagebox_exec(monkeypatch, role=None, capture=titles)
    window4 = _make_window(qtbot, tmp_path, folder=chapter)
    before = list(window4.image_files)
    _stub_open_dialog(monkeypatch, page_mas)
    window4._open_project()
    QApplication.processEvents()
    assert [imf.path for imf in window4.image_files] == [
        imf.path for imf in before
    ]


@pytest.mark.gui
def test_open_corrupt_project_keeps_session(qtbot, tmp_path, monkeypatch) -> None:
    """A corrupt manifest -> critical dialog with the corrupt-project copy;
    the previous session is byte-identical (no partial load)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    before = [imf.path for imf in window.image_files]

    corrupt_dir = tmp_path / "bad.mas-project"
    corrupt_dir.mkdir(exist_ok=True)
    (corrupt_dir / "manifest.json").write_text("this is not json {", encoding="utf-8")

    captured = _capture_critical(monkeypatch)
    _stub_open_dialog(monkeypatch, corrupt_dir / "manifest.json")
    window._open_project()
    QApplication.processEvents()

    assert captured and "Couldn't open" in captured[0][0]
    assert "corrupt or from a newer version" in captured[0][1]
    assert [imf.path for imf in window.image_files] == before
    assert window.canvas.get_image_numpy().shape[:2] == (60, 60)


@pytest.mark.gui
def test_open_verified_original_flag(qtbot, tmp_path, monkeypatch) -> None:
    """D-06 both branches: original exists + sha256 matches -> True and the
    original renders; original deleted -> False and the EMBEDDED image
    renders (the canvas numpy equals the modified save-time image)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    # Replace the canvas image with a modified version BEFORE saving so the
    # embedded image differs from the source (proves which one renders).
    alt = np.zeros((60, 60, 3), dtype=np.uint8)
    alt[:, :, 0] = 200
    alt[:, :, 1] = 40
    window.canvas.set_image_from_numpy(alt.copy())
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)

    # Original present + matching -> verified True. The first page displays
    # the EMBEDDED image at open (D-05 resume contract); NAVIGATING back to
    # the page renders the SAVED in-memory state (current_image — the CR-01
    # D-05 "resume exactly where you left off" contract). The re-verified
    # original stays the Show-Original base and the fallback for pages never
    # loaded into memory; it is NOT re-displayed on navigation (the pre-CR-01
    # behavior reloaded the pre-save disk image and silently dropped the
    # saved edits from view).
    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()
    assert window2.image_files[0].original_verified is True
    assert np.array_equal(window2.canvas.get_image_numpy(), alt)  # embedded
    window2.file_table.select_path(window2.image_files[1].path)
    window2.on_page_selected(window2.image_files[1].path)
    window2.file_table.select_path(window2.image_files[0].path)
    window2.on_page_selected(window2.image_files[0].path)
    shown = window2.canvas.get_image_numpy()
    assert np.array_equal(shown, alt)  # the saved in-memory state (CR-01) —
    # NOT a re-load of the pre-save disk original
    assert window2.image_files[0].original_verified is True  # D-06 flag intact

    # Original deleted -> verified False, embedded image renders.
    (chapter / "page_01.png").unlink()
    window3 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window3._open_project()
    QApplication.processEvents()
    assert window3.image_files[0].original_verified is False
    assert np.array_equal(window3.canvas.get_image_numpy(), alt)
    assert "Original file not found" in window3.status_bar_left.text()


@pytest.mark.gui
def test_page_navigation_uses_embedded_image_for_missing_original(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Navigating to a missing-original page renders its EMBEDDED image and
    never shows the 'Couldn't open file' warning (the D-06/D-08 resume
    contract — the placeholder path never reaches set_image_from_path)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)
    (chapter / "page_02.png").unlink()  # page 2's original goes missing

    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()
    second = window2.image_files[1]
    assert not second.original_verified

    warnings = _capture_warning(monkeypatch)
    # The exact _set_pages sidebar-selection entry: select_path then
    # on_page_selected with the incoming (placeholder) path.
    window2.file_table.select_path(second.path)
    window2.on_page_selected(second.path)
    QApplication.processEvents()

    # The embedded image rendered (dims match the page) — not an error.
    assert window2.canvas.get_image_numpy().shape[:2] == (60, 60)
    assert warnings == []  # no "Couldn't open file" dialog (D-06)


# ------------------------------------------------------------- Task 3 tests

@pytest.mark.gui
def test_folder_open_sets_original_verified(qtbot, tmp_path) -> None:
    """A normal folder-open session: every ImageFile.original_verified is
    True (D-06 normal-open wiring — Show Original is valid)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    assert len(window.image_files) == 2
    assert all(imf.original_verified for imf in window.image_files)


@pytest.mark.gui
def test_menu_gating_during_op(qtbot, tmp_path) -> None:
    """While _op_running: Save Project… / Save Project As… / Open Project…
    are disabled; they re-enable when the op finishes."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    assert window.action_save_project.isEnabled()
    assert window.action_save_project_as.isEnabled()
    assert window.action_open_project.isEnabled()

    window._op_running = True
    window._refresh_action_states()
    assert not window.action_save_project.isEnabled()
    assert not window.action_save_project_as.isEnabled()
    assert not window.action_open_project.isEnabled()

    window._op_running = False
    window._refresh_action_states()
    assert window.action_save_project.isEnabled()
    assert window.action_open_project.isEnabled()


@pytest.mark.gui
def test_unsaved_changes_prompt_save_discard_cancel(qtbot, tmp_path, monkeypatch) -> None:
    """Dirty session + Quit / spontaneous window close -> the Unsaved
    Changes prompt appears EXACTLY ONCE and one button click resolves it:
    Discard proceeds, Cancel aborts, Save saves (Save As… first) then
    proceeds; a clean session closes without prompting."""
    chapter = tmp_path / "chapter"

    # --- Discard proceeds with the close ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    titles: list = []
    _dirty(window)
    _stub_messagebox_exec(monkeypatch, role=QMessageBox.ButtonRole.DestructiveRole, capture=titles)
    window._on_quit()  # the D-07 Quit path (gate -> programmatic close)
    assert titles == ["Unsaved Changes"]  # prompted exactly once
    assert not window.isVisible()

    # --- Cancel aborts the close ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    titles.clear()
    _dirty(window)
    _stub_messagebox_exec(monkeypatch, role=QMessageBox.ButtonRole.RejectRole, capture=titles)
    window._on_quit()
    assert titles == ["Unsaved Changes"]
    assert window.isVisible()  # close aborted

    # --- Save runs Save As… (no project path yet), then the close proceeds ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _isolate_settings(window, tmp_path, monkeypatch)  # the Save path writes
    titles.clear()
    _dirty(window)
    _stub_messagebox_exec(monkeypatch, role=QMessageBox.ButtonRole.AcceptRole, capture=titles)
    _stub_dir_dialog(monkeypatch, tmp_path / "chapter.mas-project")
    window._on_quit()
    assert titles == ["Unsaved Changes"]
    assert not window.isVisible()
    assert window._project_dir == tmp_path / "chapter.mas-project"
    assert not window._session_dirty()

    # --- Clean session: no prompt, close proceeds ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    titles.clear()
    _stub_messagebox_exec(monkeypatch, role=None, capture=titles)
    window._on_quit()
    assert titles == []
    assert not window.isVisible()

    # --- Spontaneous (window-manager X) close runs the same single gate ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    titles.clear()
    _dirty(window)
    from PySide6.QtGui import QCloseEvent

    monkeypatch.setattr(QCloseEvent, "spontaneous", lambda self: True)
    _stub_messagebox_exec(monkeypatch, role=QMessageBox.ButtonRole.RejectRole, capture=titles)
    window.close()
    assert titles == ["Unsaved Changes"]  # exactly one prompt
    assert window.isVisible()  # Cancel aborted the close

    # --- Programmatic close (host teardown / non-spontaneous) NEVER prompts ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    titles.clear()
    _dirty(window)
    monkeypatch.setattr(QCloseEvent, "spontaneous", lambda self: False)
    _stub_messagebox_exec(monkeypatch, role=None, capture=titles)
    window.close()
    assert titles == []  # no dialog for programmatic closes


@pytest.mark.gui
def test_recent_projects_menu(qtbot, tmp_path, monkeypatch) -> None:
    """Recent Projects: 'Project — {folder-name}' entries with full-path
    tooltips, capped at 8 across 9 saves, Clear Menu empties it, and a fresh
    QSettings shows the disabled 'No recent projects yet.' empty item."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _isolate_settings(window, tmp_path, monkeypatch)
    # The submenu was populated at construction from the real settings;
    # rebuild it from the isolated store.
    window._refresh_recent_projects_menu()

    # Fresh settings -> the empty-state item.
    def entry_actions():
        acts = []
        for act in window.recent_projects_menu.actions():
            if act.property("recent_project"):
                acts.append(act)
        return acts

    assert [a.text() for a in entry_actions()] == []

    # 9 saves to 9 different dirs -> capped at 8, newest first. The isolated
    # settings store must persist across saves (no re-isolation).
    for i in range(9):
        _dirty(window)
        _save_as(window, tmp_path / f"chapter{i}.mas-project", monkeypatch, isolate_settings=False)
    entries = entry_actions()
    assert len(entries) == 8
    assert entries[0].text() == "Project \u2014 chapter8.mas-project"
    assert entries[0].toolTip() == str(tmp_path / "chapter8.mas-project")
    assert entries[-1].text() == "Project \u2014 chapter1.mas-project"
    # chapter0 dropped off (oldest).
    assert all("chapter0" not in e.toolTip() for e in entries)

    # Clear Menu empties the list -> empty-state item returns.
    window.action_clear_recent_projects.trigger()
    QApplication.processEvents()
    assert entry_actions() == []
    assert any(
        a.text() == "No recent projects yet." and not a.isEnabled()
        for a in window.recent_projects_menu.actions()
    )


# ===========================================================================
# Plan 05-06 Task 3 — Show Original gating (surface 29, D-06/D-14)
# ===========================================================================

@pytest.mark.gui
def test_show_original_gating(qtbot, tmp_path, monkeypatch) -> None:
    """Surface 29 (D-06): Show Original is disabled with the not-found tooltip
    when the current page's original is unverified (a .mas-loaded page whose
    source failed the checksum); a folder-open page keeps the inherited
    gating; after an image op on the folder page Show Original shows the
    post-op image (D-14 re-baseline)."""
    chapter = tmp_path / "chapter"

    # --- .mas-loaded page with original_verified False -> disabled + tooltip ---
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)
    (chapter / "page_01.png").unlink()  # original goes missing -> unverified

    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()
    assert window2.image_files[0].original_verified is False
    assert not window2.action_show_original.isEnabled()
    assert (
        window2.action_show_original.toolTip()
        == "Show Original (P) — original file not found."
    )

    # --- folder-open page: inherited gating + post-op re-baseline (D-14) ---
    window3 = _make_window(qtbot, tmp_path, folder=tmp_path / "chapter2")
    assert window3.image_files[0].original_verified is True
    # No inpaint result yet -> the action follows has_inpaint (disabled), with
    # the inherited tooltip (NOT the not-found copy).
    assert not window3.action_show_original.isEnabled()
    assert "original file not found" not in window3.action_show_original.toolTip().lower()
    # An image op re-baselines the cache and enables the toggle (set_image
    # ran -> has_inpaint_result True; _apply_geometry_op refreshes states).
    window3._rotate_page(-1)
    QApplication.processEvents()
    now = window3.canvas.get_image_numpy()
    assert window3.action_show_original.isEnabled()
    assert "original file not found" not in window3.action_show_original.toolTip().lower()
    assert len(window3.history._image_undo) == 1  # the op really applied
    assert np.array_equal(window3.canvas._original_image_numpy, now)
    window3.canvas.show_original(True)
    assert np.array_equal(window3.canvas.get_image_numpy(), now)


# ===========================================================================
# Plan 05-10 — G-05-1/G-05-2 gap closure (UAT test 1 CR-01 repro)
# ===========================================================================
# G-05-1: QAction.triggered emits the checked bool as its first argument;
# the pre-fix wiring landed it in _open_project's manifest_path slot and
# crashed at selected.name with AttributeError. These tests drive the REAL
# signal path (action.trigger()) so the pre-fix crash propagates out of the
# call and fails the test.
# G-05-2: the Save As folder dialog must open at an EXISTING default
# <chapter>.mas-project folder (the native dialog refuses a non-existent
# default and silently falls back to the album root), and a cancelled or
# redirected Save As must leave no stray self-created folder behind.

@pytest.mark.gui
def test_open_project_trigger_loads_session(qtbot, tmp_path, monkeypatch) -> None:
    """G-05-1 regression: ``action_open_project.trigger()`` (the real
    QAction.triggered signal path — menu click / Ctrl+O) loads the stubbed
    manifest session with NO exception. The pre-fix wiring injected the
    checked bool into the manifest_path slot, so ``selected`` was ``False``
    and ``selected.name`` raised AttributeError: 'bool' object has no
    attribute 'name' (main_window.py:2065)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)

    # A FRESH window on the open side; the dialog returns the manifest path.
    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2.action_open_project.trigger()
    QApplication.processEvents()

    # Session state matches the dialog-path open (D-08/D-09).
    assert [imf.path.name for imf in window2.image_files] == [
        "page_01.png",
        "page_02.png",
    ]
    assert window2._project_dir == project_dir
    assert window2._project_name == "chapter"


@pytest.mark.gui
def test_save_project_trigger_saves_in_place(qtbot, tmp_path, monkeypatch) -> None:
    """G-05-1 wiring-contract guard: ``action_save_project.trigger()`` with
    an existing project dir saves IN PLACE — the folder dialog is never
    shown (captured calls == []) and the write lands in the recorded dir.
    Guards against a future change silently flipping the save into Save-As
    mode (the triggered bool would otherwise land in ``force_as``)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch)
    assert window._project_dir == project_dir

    # Dirty again; capture (and stub) the folder dialog — it must NOT open.
    _dirty(window)
    calls = _stub_dir_dialog(monkeypatch, project_dir)
    window.action_save_project.trigger()
    QApplication.processEvents()

    assert calls == []  # no Save-As dialog for an in-place save
    assert window._project_dir == project_dir
    assert (project_dir / "manifest.json").is_file()
    assert not window._session_dirty()  # the in-place save wrote + cleared


@pytest.mark.gui
def test_save_as_default_dir_precreated(qtbot, tmp_path, monkeypatch) -> None:
    """G-05-2 regression: ``_choose_project_dir`` pre-creates the default
    ``<chapter>.mas-project`` folder BEFORE the dialog — the captured dir
    argument (positional index 2 of the QFileDialog.getExistingDirectory
    call) must be an EXISTING directory. The native dialog refuses a
    non-existent default and silently falls back to the source parent,
    which is exactly how saves leaked into the album root (D-02
    violation)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    # The computed default for a 2-page chapter session (D-02):
    # <source-parent>/<chapter-name>.mas-project.
    default = chapter / "chapter.mas-project"
    calls = _stub_dir_dialog(monkeypatch, default)

    picked = window._choose_project_dir()

    assert picked == default
    assert len(calls) == 1
    assert Path(calls[0][0][2]).is_dir()  # the dialog default EXISTS
    assert calls[0][0][2] == str(default)


@pytest.mark.gui
def test_save_as_cancel_cleanup(qtbot, tmp_path, monkeypatch) -> None:
    """G-05-2: cancelling the dialog removes the self-created empty default
    folder — a cancelled Save As leaves NO stray ``.mas-project`` folder
    behind."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    default = chapter / "chapter.mas-project"
    _stub_dir_dialog(monkeypatch, None)  # cancel

    picked = window._choose_project_dir()

    assert picked is None
    assert not default.exists()  # the pre-created stray folder was removed


@pytest.mark.gui
def test_save_as_different_pick_cleanup(qtbot, tmp_path, monkeypatch) -> None:
    """G-05-2: picking a DIFFERENT folder removes the stray self-created
    default and returns the user's pick (the default pick itself keeps the
    folder — the save populates it)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    default = chapter / "chapter.mas-project"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    _stub_dir_dialog(monkeypatch, elsewhere)

    picked = window._choose_project_dir()

    assert picked == elsewhere
    assert not default.exists()  # the stray pre-created default was removed

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


def _wait_save_done(qtbot, window: MainWindow, timeout_ms: int = 20000) -> None:
    """Block until a dispatched async save fully lands (quick-260826-vhh).

    Save completion runs queued on the main thread via WorkerSignals;
    waiting for ``_op_running`` to drop guarantees the dirty flags / title /
    status reflect the finished save before assertions run.
    """
    qtbot.waitUntil(lambda: not window._op_running, timeout=timeout_ms)
    QApplication.processEvents()


def _save_as(
    window: MainWindow,
    target_dir: Path,
    monkeypatch,
    isolate_settings: bool = True,
    qtbot=None,
) -> None:
    """Run the Save As flow with the folder dialog stubbed to ``target_dir``.

    QSettings are isolated to a throwaway INI so a save's
    ``_add_recent_project`` never touches the user's real registry settings
    (``isolate_settings=False`` keeps an already-isolated store, e.g. for
    multi-save Recent Projects tests).

    quick-260826-vhh: saves are NON-BLOCKING — pass ``qtbot`` (every test
    has it) to block until the dispatched save fully lands; without it the
    call returns after dispatch and assertions race the worker.
    """
    _stub_dir_dialog(monkeypatch, target_dir)
    if isolate_settings:
        _isolate_settings_any(window, monkeypatch)
    window._save_project(force_as=True)
    if qtbot is not None:
        _wait_save_done(qtbot, window)
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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

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

    _save_as(window, tmp_path / "chapter.mas-project", monkeypatch, qtbot=qtbot)
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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

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
def test_project_open_hides_empty_state_trio(qtbot, tmp_path, monkeypatch) -> None:
    """D-09 regression (project-open numpy path): reopening a saved session
    must hide the z=2000 empty-state trio over the loaded page, and show the
    empty-box hint on a box-less page (UI-SPEC E2).

    The project-open path runs ``_display_page_state`` ->
    ``canvas.set_image_from_numpy`` — the ONLY display path that missed the
    ``_update_empty_state()`` call. This test MUST fail on pre-fix code (the
    trio stays visible over the loaded page).
    """
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    # Fresh window starts on the empty state (the D-09 pre-condition).
    window2 = _make_window(qtbot, tmp_path)
    assert window2.canvas._empty_heading.isVisible()
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()

    canvas = window2.canvas
    # D-09: the empty-state trio must not persist over the loaded page.
    assert not canvas._empty_heading.isVisible()
    assert not canvas._empty_body.isVisible()
    assert not canvas._empty_hint.isVisible()
    # Zero boxes on the reopened page -> the empty-box hint IS visible.
    assert canvas.empty_box_hint.isVisible()


@pytest.mark.gui
def test_open_project_populates_all_current_images(qtbot, tmp_path, monkeypatch) -> None:
    """BOTH pages get their embedded image decoded into current_image — incl.
    the non-displayed second page whose original was deleted (the 05-08 batch
    dims fallback); the open-status flash notes the missing original."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)
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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)
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
    # quick-260826-vhh: the gate's Save leg returns after DISPATCH (True =
    # accepted+running); the close proceeds and the async save lands
    # independently. Wait for the completion before asserting the state.
    _wait_save_done(qtbot, window)
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
        _save_as(
            window,
            tmp_path / f"chapter{i}.mas-project",
            monkeypatch,
            isolate_settings=False,
            qtbot=qtbot,
        )
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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)
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
# Quick 260826-u9m — Show Original references the D-06 ORIGINAL ON DISK
# ===========================================================================
#
# Before this fix, Show Original's baseline was seeded by capture-if-None
# from the SAVED embedded image — so after Save Project + reopen, P showed
# the already-inpainted/edited result as the "original". Now the verified
# D-06 disk reference is decoded lazily per displayed page; unverified /
# unreadable / dims-mismatched pages keep today's fallback; and a page
# switch can never inherit a foreign baseline or stale toggle flag.


def _seed_two_tone(
    path: Path, top: tuple[int, int, int], bottom: tuple[int, int, int],
    size: int = 60,
) -> np.ndarray:
    """Overwrite ``path`` with a non-uniform two-band PNG and return the
    pristine pixels.

    The shared ``_make_pages`` fixtures produce SOLID-color pages — on those,
    flipud/crop edits are pixel identities and every baseline-vs-display
    assertion degenerates. Two horizontal bands keep flipud a REAL change
    while staying deterministic.
    """
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    arr[: size // 2] = top
    arr[size // 2 :] = bottom
    PILImage.fromarray(arr).save(path)
    return arr


@pytest.mark.gui
def test_show_original_uses_persisted_original_after_reopen(
    qtbot, tmp_path, monkeypatch
) -> None:
    """After Save Project + reopen, P shows the PRISTINE ON-DISK original.

    The saved embed carries an EDITED page (flipud — dims-preserving); the
    reopened session must decode original.json's verified file for the Show
    Original baseline while still DISPLAYING the edited embed, and the
    toggle restores the saved state when switched off.
    """
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    page_01 = chapter / "page_01.png"
    pristine = _seed_two_tone(page_01, (200, 40, 40), (30, 60, 90))

    # Simulate an edit on the current page: flip preserves the 60x60 dims.
    # Both slots are set so the save-side current-page flush stays consistent.
    edited = np.flipud(pristine).copy()
    window.image_files[0].current_image = edited
    window.canvas.set_image_from_numpy(edited)
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    # Reopen through the stubbed manifest dialog (test_show_original_gating pattern).
    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()

    assert window2.image_files[0].original_verified is True
    # The baseline is the PRISTINE DISK pixels — never the flipped embed.
    assert np.array_equal(window2.canvas._original_image_numpy, pristine)
    assert not np.array_equal(window2.canvas._original_image_numpy, edited)
    # The display itself still resumes exactly where the save left off.
    assert np.array_equal(window2.canvas.get_image_numpy(), edited)
    # Verified ref + inpaint claim -> the P action is enabled and toggling
    # swaps between the pristine disk pixels and the saved state.
    act = window2.action_show_original
    assert act.isEnabled()
    window2.canvas.show_original(True)
    assert np.array_equal(window2.canvas.get_image_numpy(), pristine)
    window2.canvas.show_original(False)
    assert np.array_equal(window2.canvas.get_image_numpy(), edited)


@pytest.mark.gui
def test_show_original_dims_mismatch_falls_back_to_embedded(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A geometry-altered page's pristine file mismatches the embed dims:
    the disk reference degrades to the in-memory fallback (the embed) and
    open/navigation raise nothing (the dims guard, not a crash)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    page_01 = chapter / "page_01.png"
    pristine = _seed_two_tone(page_01, (250, 200, 10), (10, 90, 250))
    cropped = pristine[:, :40].copy()  # square pristine vs 60x40 crop

    # Display the crop through the real seam and recompose the composite at
    # the cropped dims (validate_meta requires mask dims == image dims).
    window.image_files[0].current_image = cropped
    window.canvas.set_image_from_numpy(cropped)
    window.canvas.recompose_mask()
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()
    imf0 = window2.image_files[0]
    # Sanity: the crop really persisted into the embed.
    assert imf0.current_image.shape[:2] == (60, 40)
    assert imf0.original_verified is True

    # The dims guard rejected the pristine disk decode -> the fallback
    # baseline IS the cropped embed. No exception reached this line.
    assert np.array_equal(window2.canvas._original_image_numpy, cropped)
    assert np.array_equal(window2.canvas.get_image_numpy(), cropped)
    # The gating contract is unchanged: the action stays enabled.
    assert window2.action_show_original.isEnabled()


@pytest.mark.gui
def test_page_switch_seeds_baseline_per_page_no_bleed(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Each page's baseline comes from ITS OWN pristine file — a page switch
    never carries the outgoing page's baseline or a stale toggle flag
    (end-to-end lock of the cross-page bleed fix)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    page_01, page_02 = chapter / "page_01.png", chapter / "page_02.png"
    # Non-uniform per-page fixtures (see _seed_two_tone): distinct across
    # pages AND genuinely altered by the flipud edits.
    p1_pristine = _seed_two_tone(page_01, (180, 20, 20), (20, 60, 220))
    p2_pristine = _seed_two_tone(page_02, (10, 140, 30), (240, 200, 10))
    assert not np.array_equal(p1_pristine, p2_pristine)  # distinct per-page colors

    # Give each page its own distinct edited embed before saving.
    p1_edit = np.flipud(p1_pristine).copy()
    p2_edit = np.fliplr(p2_pristine).copy()
    window.image_files[0].current_image = p1_edit
    window.canvas.set_image_from_numpy(p1_edit)  # page 1 is current: flush-consistent
    window.image_files[1].current_image = p2_edit  # non-current: survives untouched
    _dirty(window)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    window2 = _make_window(qtbot, tmp_path)
    _stub_open_dialog(monkeypatch, project_dir / "manifest.json")
    window2._open_project()
    QApplication.processEvents()
    # Page 1 opened first: its pristine file seeds the baseline.
    assert np.array_equal(window2.canvas._original_image_numpy, p1_pristine)

    # Navigate to page 2 through the REAL seam (sidebar selection entry).
    second = window2.image_files[1]
    window2.file_table.select_path(second.path)
    window2.on_page_selected(second.path)
    QApplication.processEvents()

    assert np.array_equal(window2.canvas._original_image_numpy, p2_pristine)
    assert not np.array_equal(window2.canvas._original_image_numpy, p1_pristine)
    assert window2.canvas._showing_original is False
    assert np.array_equal(window2.canvas.get_image_numpy(), p2_edit)


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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

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
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)
    assert window._project_dir == project_dir

    # Dirty again; capture (and stub) the folder dialog — it must NOT open.
    _dirty(window)
    calls = _stub_dir_dialog(monkeypatch, project_dir)
    window.action_save_project.trigger()
    _wait_save_done(qtbot, window)

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

    picked, created = window._choose_project_dir()

    assert picked == default
    assert created is True  # WR-01: the created flag reaches the caller
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

    picked, created = window._choose_project_dir()

    assert picked is None
    assert created is True  # the dialog was offered the pre-created default
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

    picked, created = window._choose_project_dir()

    assert picked == elsewhere
    assert created is True  # the stray default was self-created -> removed
    assert not default.exists()  # the stray pre-created default was removed


@pytest.mark.gui
def test_save_as_abort_removes_stray_default(qtbot, tmp_path, monkeypatch) -> None:
    """WR-01 regression: when the dialog accepts the pre-created default
    folder and the save then aborts BEFORE writing (duplicate page stems),
    the empty self-created ``.mas-project`` folder must be removed — a
    failed Save As leaves no stray empty folder behind (plan 05-10
    must-have)."""
    chapter = tmp_path / "chapter"
    chapter.mkdir(exist_ok=True)
    # Two pages sharing the stem ``page`` (page.png + page.jpg) -> the
    # duplicate-stem abort fires after the dialog, before any write.
    PILImage.new("RGB", (60, 60), color=(30, 60, 90)).save(chapter / "page.png")
    PILImage.new("RGB", (60, 60), color=(30, 60, 90)).save(chapter / "page.jpg")
    window = _make_window(qtbot, tmp_path)
    window._load_folder(chapter)
    QApplication.processEvents()
    assert [imf.path.stem for imf in window.image_files] == ["page", "page"]

    default = chapter / "chapter.mas-project"
    _stub_dir_dialog(monkeypatch, default)  # pick the pre-created default
    criticals = _capture_critical(monkeypatch)

    saved = window._save_project(force_as=True)
    QApplication.processEvents()

    assert saved is False  # the save aborted on the duplicate stems
    assert criticals  # the save-failure dialog was shown
    assert not default.exists()  # WR-01: the stray empty folder was removed


# ------------------------------------------------- quick-260824-pqn tests

@pytest.mark.gui
def test_save_with_detected_numpy_payload_writes_files(
    qtbot, tmp_path, monkeypatch
) -> None:
    """quick-260824-pqn end-to-end: saving a session whose page carries a
    DETECTED-style payload (a TextBlock whose lines are raw numpy int32
    polygons, exactly what the vendored detector produces) writes
    manifest.json + .mas into the chosen folder — before the fix this raised
    TypeError inside ``build_page_entries`` and PySide6 swallowed it in the
    Qt slot (silent empty folder)."""
    from manga_ai_studio.core.box_model import PageBox
    from panelcleaner.comic_text_detector.utils.textblock import TextBlock
    from panelcleaner.structures import Box

    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)

    tb = TextBlock(
        [5, 5, 40, 20],
        [np.array([[5, 5], [40, 5], [40, 20], [5, 20]], dtype=np.int32)],
    )
    tb.text = ""
    tb.translation = ""
    tb.font_size = -1
    pb = PageBox(box=Box(5, 5, 40, 20), origin="detected", payload=tb)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pb], [])
    finally:
        window._suppress_boxes_push = False
    _dirty(window)

    project_dir = tmp_path / "detected.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    assert (project_dir / "manifest.json").is_file()
    assert sorted(p.name for p in project_dir.glob("*.mas")) == [
        "page_01.mas",
        "page_02.mas",
    ]
    manifest = load_project(project_dir / "manifest.json")
    assert [p["name"] for p in manifest["pages"]] == ["page_01", "page_02"]
    assert not window._session_dirty()


@pytest.mark.gui
def test_save_write_phase_exception_shows_dialog_and_cleans_stray(
    qtbot, tmp_path, monkeypatch
) -> None:
    """T-QKN-02/T-QKN-03 (quick-260826-vhh adaptation): an UNEXPECTED
    exception during the save's WRITE phase (serialization now runs on the
    pooled Worker) reaches the main thread through the typed error signal,
    surfaces the T-05-12 failure dialog, and removes the stray self-created
    default folder — it must never die silently. The DISPATCH itself still
    reports True per the async contract (preparation succeeded); False
    remains reserved for preparation failures."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)  # a real edit so "flags untouched" is observable

    def _boom(*a, **k):
        raise RuntimeError("simulated write-phase crash")

    monkeypatch.setattr(
        "manga_ai_studio.core.project_io.build_page_entries", _boom
    )
    default = chapter / "chapter.mas-project"
    _stub_dir_dialog(monkeypatch, default)  # pick the pre-created default
    criticals = _capture_critical(monkeypatch)

    saved = window._save_project(force_as=True)
    _wait_save_done(qtbot, window)

    assert saved is True  # dispatch accepted; the FAILURE arrived async
    assert criticals
    assert criticals[0][0].startswith("Couldn't save")
    assert not default.exists()  # WR-01: stray empty folder cleaned up
    # Failure keeps the session recoverable: flags untouched.
    assert window._session_dirty()


@pytest.mark.gui
def test_cross_session_swap_does_not_bleed_planes_into_new_list(
    qtbot, tmp_path, monkeypatch
) -> None:
    """quick 260826-1by (T-Q1B-01/03): replacing a session over a live canvas
    must retire ``_last_page_index`` BEFORE the fresh ImageFile list is
    observable and can never land outgoing-canvas plane blobs of the wrong
    length on the new session's pages (no wrong-dims mask corruption by a
    page switch after a session swap)."""
    folder_a = tmp_path / "a"
    window = _make_window(qtbot, tmp_path, folder=folder_a, size=60)
    _isolate_settings(window, tmp_path, monkeypatch)

    # Navigate to page 2 and paint real mask content onto it.
    page2 = window.image_files[1].path
    window.file_table.select_path(page2)
    window.on_page_selected(page2)
    QApplication.processEvents()
    assert window._last_page_index == 1
    _seed_mask_content(window)

    # Observe the seam index DURING the swap: _set_pages re-selects the
    # first page AFTER retiring the outgoing index, so the value seen at
    # that moment is the contamination gate.
    observed: list = []
    orig_select = window.file_table.select_path

    def _spy_select(path):
        observed.append(window._last_page_index)
        orig_select(path)

    monkeypatch.setattr(window.file_table, "select_path", _spy_select)

    # Replace the session with different-sized pages (seam called directly,
    # like an Open Folder over a live project session would).
    folder_b = tmp_path / "b"
    paths_b = _make_pages(folder_b, count=2, size=90)
    window._set_pages(paths_b)
    QApplication.processEvents()

    assert observed[-1] is None  # swap retired the outgoing index first
    required = (90 * 90 + 7) // 8
    for imf in window.image_files:
        for slot_name in ("auto_mask", "mask_manual", "mask_erase"):
            blob = getattr(imf, slot_name)
            assert blob is None or len(blob) == required, (
                f"{imf.path.name}.{slot_name} has foreign-length blob"
                f" ({len(blob)} bytes, expected {required})"
            )
        m = imf.mask
        assert m is None or m.isNull() or (m.height(), m.width()) == (90, 90)


@pytest.mark.gui
def test_outgoing_persistence_dims_guard_skips_mismatched_write(
    qtbot, tmp_path, monkeypatch
) -> None:
    """quick 260826-1by (T-Q1B-01): a stale seam index pointing at an
    ImageFile whose page dims differ from the live canvas planes must write
    NOTHING into that ImageFile (slots unchanged) while navigation itself
    still completes normally."""
    folder = tmp_path / "guard"
    window = _make_window(qtbot, tmp_path, folder=folder, size=60)
    _isolate_settings(window, tmp_path, monkeypatch)

    stale = window.image_files[1]
    stale.current_image = np.zeros((90, 90, 3), dtype=np.uint8)
    sentinel_auto = np.arange(17, dtype=np.uint8)
    sentinel_manual = np.arange(23, dtype=np.uint8)
    sentinel_erase = np.arange(31, dtype=np.uint8)
    stale.auto_mask = sentinel_auto.copy()
    stale.mask_manual = sentinel_manual.copy()
    stale.mask_erase = sentinel_erase.copy()

    # Canvas planes are 60x60 while the stale target's page is 90x90.
    _seed_mask_content(window)
    window._last_page_index = 1
    window.file_table.select_path(window.image_files[0].path)
    window.on_page_selected(window.image_files[0].path)
    QApplication.processEvents()

    np.testing.assert_array_equal(stale.auto_mask, sentinel_auto)
    np.testing.assert_array_equal(stale.mask_manual, sentinel_manual)
    np.testing.assert_array_equal(stale.mask_erase, sentinel_erase)
    assert stale.boxes is None
    # Navigation completed: the incoming page shows on the canvas.
    img = window.canvas.get_image_numpy()
    assert img is not None and img.shape[:2] == (60, 60)


@pytest.mark.gui
def test_corrupt_plane_blob_restores_degraded_with_boxes_intact(
    qtbot, tmp_path, monkeypatch
) -> None:
    """quick 260826-1by (T-Q1B-02): a corrupt/wrong-dims packed auto blob
    degrades to "no plane" inside _display_page_state — no ValueError
    propagates out of the display path and a valid text-boxes payload still
    restores onto the canvas."""
    from manga_ai_studio.core.box_model import USER, PageBox
    from manga_ai_studio.core.mask_planes import pack_binary
    from panelcleaner.structures import Box

    folder = tmp_path / "corrupt"
    window = _make_window(qtbot, tmp_path, folder=folder, size=60)
    _isolate_settings(window, tmp_path, monkeypatch)

    imf = window.image_files[0]
    imf.current_image = np.zeros((60, 60, 3), dtype=np.uint8)
    imf.auto_mask = pack_binary(np.zeros((40, 40), dtype=np.uint8))  # len 200 != 450
    pb = PageBox(box=Box(5, 5, 40, 20), origin=USER)
    imf.boxes = [pb]

    # Must NOT raise despite the blob length not fitting 60x60.
    window._display_page_state(imf)
    QApplication.processEvents()

    assert window.canvas.has_boxes() is True  # boxes/text restoration intact
    assert window.canvas._auto_bin is None  # corrupt plane contributed nothing


# ===========================================================================
# quick-260826-vhh — incremental dirty-only saves (synchronous core)
# ===========================================================================


def _open_three_page_session(qtbot, tmp_path, chapter_name: str = "chapter"):
    """A 3-page chapter session open in a MainWindow (house fixture shape)."""
    chapter = tmp_path / chapter_name
    _make_pages(chapter, count=3)
    window = _make_window(qtbot, tmp_path)
    window._load_folder(chapter)
    QApplication.processEvents()
    return chapter, window


def _dirty_page_idx(window: MainWindow, idx: int, add_box: bool = True) -> None:
    """Mark ONE page dirty with a real content change (an extra user box)."""
    from manga_ai_studio.core.box_model import PageBox
    from panelcleaner.structures import Box

    imf = window.image_files[idx]
    if add_box:
        imf.boxes = list(imf.boxes or []) + [
            PageBox(box=Box(5, 5, 40, 20), origin="user")
        ]
    imf.dirty = True


@pytest.mark.gui
def test_incremental_save_rewrites_only_the_dirty_page(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A repeat save after editing ONLY page 2 leaves pages 1/3 byte-
    identical on disk, rewrites page 2's .mas, and the manifest still lists
    all three pages in sidebar order."""
    chapter, window = _open_three_page_session(qtbot, tmp_path)

    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)
    b1 = (project_dir / "page_01.mas").read_bytes()
    b2 = (project_dir / "page_02.mas").read_bytes()
    b3 = (project_dir / "page_03.mas").read_bytes()

    _dirty_page_idx(window, 1)
    window._save_project()
    _wait_save_done(qtbot, window)

    manifest = load_project(project_dir / "manifest.json")
    assert [p["name"] for p in manifest["pages"]] == [
        "page_01",
        "page_02",
        "page_03",
    ]
    # Clean pages: BYTE-IDENTICAL (never decoded/re-encoded/rewritten).
    assert (project_dir / "page_01.mas").read_bytes() == b1
    assert (project_dir / "page_03.mas").read_bytes() == b3
    # The edited page changed.
    assert (project_dir / "page_02.mas").read_bytes() != b2
    assert not window._session_dirty()


@pytest.mark.gui
def test_incremental_save_builds_only_eligible_pages(
    qtbot, tmp_path, monkeypatch
) -> None:
    """The second save calls ``build_page_entries`` exactly ONCE (the edited
    page only) — clean pages are never hashed/encoded/compressed — and the
    transient reports both totals (N pages, M written)."""
    import manga_ai_studio.core.project_io as pio_mod

    chapter, window = _open_three_page_session(qtbot, tmp_path)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    calls = {"n": 0}
    real = pio_mod.build_page_entries

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(pio_mod, "build_page_entries", _counting)

    _dirty_page_idx(window, 1)
    window._save_project()
    _wait_save_done(qtbot, window)

    assert calls["n"] == 1
    assert (
        "Saved project 'chapter' (3 pages, 1 written)"
        in window.status_bar_left.text()
    )


@pytest.mark.gui
def test_missing_mas_page_is_resurrected_by_clean_save(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Deleting a page's .mas from a saved project makes the NEXT clean save
    rebuild EXACTLY that page (missing-file eligibility) while the untouched
    pages stay byte-identical — a clean session with everything present still
    flashes 'No changes to save.'"""
    chapter, window = _open_three_page_session(qtbot, tmp_path)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)
    b1 = (project_dir / "page_01.mas").read_bytes()
    b2 = (project_dir / "page_02.mas").read_bytes()

    # Clean session, nothing missing -> the legacy flash.
    window._save_project()
    QApplication.processEvents()
    assert "No changes to save." in window.status_bar_left.text()

    (project_dir / "page_03.mas").unlink()

    import manga_ai_studio.core.project_io as pio_mod

    calls = {"n": 0}
    real = pio_mod.build_page_entries

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(pio_mod, "build_page_entries", _counting)
    window._save_project()
    _wait_save_done(qtbot, window)

    assert calls["n"] == 1  # only the missing page was rebuilt
    assert (project_dir / "page_03.mas").is_file()
    assert (project_dir / "page_01.mas").read_bytes() == b1
    assert (project_dir / "page_02.mas").read_bytes() == b2
    manifest = load_project(project_dir / "manifest.json")
    assert len(manifest["pages"]) == 3


@pytest.mark.gui
def test_save_as_rewrites_every_page(qtbot, tmp_path, monkeypatch) -> None:
    """force_as coverage: Save As… writes EVERY page into the fresh folder
    (legacy full-save semantics), even pages whose .mas exists elsewhere."""
    import manga_ai_studio.core.project_io as pio_mod

    chapter, window = _open_three_page_session(qtbot, tmp_path)
    first_dir = tmp_path / "chapter.mas-project"
    _save_as(window, first_dir, monkeypatch, qtbot=qtbot)

    calls = {"n": 0}
    real = pio_mod.build_page_entries

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(pio_mod, "build_page_entries", _counting)

    second_dir = tmp_path / "copy.mas-project"
    _save_as(window, second_dir, monkeypatch, isolate_settings=False, qtbot=qtbot)

    assert calls["n"] == 3  # every page rebuilt on Save As…
    assert sorted(p.name for p in second_dir.glob("*.mas")) == [
        "page_01.mas",
        "page_02.mas",
        "page_03.mas",
    ]
    assert window._project_dir == second_dir
    assert not window._session_dirty()


@pytest.mark.gui
def test_duplicate_stem_among_clean_pages_still_aborts_pre_write(
    qtbot, tmp_path, monkeypatch
) -> None:
    """WR-03 tightened scope: a duplicate stem pair trips the guard over the
    FULL session stem list even when only ONE of the colliding pair is
    eligible — nothing is written and the dirty flags stay intact."""
    chapter = tmp_path / "dupes"
    chapter.mkdir(exist_ok=True)
    PILImage.new("RGB", (60, 60), color=(30, 60, 90)).save(chapter / "dup.png")
    PILImage.new("RGB", (60, 60), color=(90, 30, 60)).save(chapter / "dup.jpg")
    PILImage.new("RGB", (60, 60), color=(10, 10, 10)).save(chapter / "solo.png")

    window = _make_window(qtbot, tmp_path)
    window._load_folder(chapter)
    QApplication.processEvents()
    # Mark exactly ONE of the colliding pair dirty.
    idx = next(i for i, imf in enumerate(window.image_files) if imf.path.stem == "dup")
    _dirty_page_idx(window, idx, add_box=False)

    default = chapter / "dupes.mas-project"
    _stub_dir_dialog(monkeypatch, default)
    criticals = _capture_critical(monkeypatch)

    saved = window._save_project(force_as=True)
    QApplication.processEvents()

    assert saved is False
    assert criticals, "the duplicate-stem failure dialog was shown"
    assert "share the same file name" in criticals[0][1]
    assert not default.exists()  # aborted BEFORE any write -> stray removed
    assert window.image_files[idx].dirty is True  # flags untouched


@pytest.mark.gui
def test_eligible_page_without_source_aborts_whole_save(
    qtbot, tmp_path, monkeypatch
) -> None:
    """WR-02 (quick-260826-vhh): an ELIGIBLE page whose image source cannot
    be resolved aborts the ENTIRE save before writing anything — the other
    pages' edits must not be persisted while the broken page's dirty flag
    would have been cleared by the success tail."""
    chapter, window = _open_three_page_session(qtbot, tmp_path)
    # A second page edited AND unresolvable: rename its path to a file
    # that does not exist anywhere beside the sources.
    ghost = window.image_files[1]
    assert ghost.current_image is None  # never navigated to it
    ghost.path = chapter / "ghost.png"
    _dirty_page_idx(window, 1, add_box=False)

    default = chapter / "chapter.mas-project"
    _stub_dir_dialog(monkeypatch, default)
    criticals = _capture_critical(monkeypatch)

    saved = window._save_project(force_as=True)
    QApplication.processEvents()

    assert saved is False
    assert criticals
    assert criticals[0][0].startswith("Couldn't save 'chapter'.")
    assert "No page could be read for saving." in criticals[0][1]
    assert not any(default.glob("*.mas"))  # NOTHING was written
    assert window.image_files[1].dirty is True


# ===========================================================================
# quick-260826-vhh — non-blocking async save + race-safe dirty handling
# ===========================================================================


@pytest.mark.gui
def test_async_save_returns_immediately_and_races_are_serial_guarded(
    qtbot, tmp_path, monkeypatch
) -> None:
    """T-QHH-01/T-QHH-02: Ctrl+S dispatches and returns while the worker
    writes; pages edited DURING the save keep their dirty flags after
    completion (the serial bumped), while a page untouched since dispatch
    clears."""
    chapter, window = _open_three_page_session(qtbot, tmp_path)
    project_dir = tmp_path / "chapter.mas-project"
    _save_as(window, project_dir, monkeypatch, qtbot=qtbot)

    # Two eligible pages for the second save.
    _dirty_page_idx(window, 0, add_box=False)
    _dirty_page_idx(window, 1, add_box=False)

    import threading

    started = threading.Event()
    release = threading.Event()
    real_task = window._run_save_task

    def slow_task(payloads, pdir_, nm_, stems_):
        started.set()
        release.wait(timeout=15)
        return real_task(payloads, pdir_, nm_, stems_)

    monkeypatch.setattr(window, "_run_save_task", slow_task)
    returned = []
    returned.append(window._save_project())
    assert returned == [True]
    assert window._op_running  # the save is RUNNING (responsiveness)
    assert "Saving" in window.status_bar_left.text()
    qtbot.waitUntil(started.is_set, timeout=10000)

    # Mid-save edits: page 1 is RE-edited (serial re-bump); page 2 gets its
    # FIRST edit via the documented mutator pattern (direct flag + bump —
    # exactly what _set_session_dirty does beyond navigation).
    window._bump_page_serial(1)
    window.image_files[2].dirty = True
    window._bump_page_serial(2)

    release.set()
    _wait_save_done(qtbot, window)

    assert not window._op_running
    assert window.image_files[0].dirty is False   # unchanged since dispatch -> cleared
    assert window.image_files[1].dirty is True    # re-dirtied mid-save -> kept
    assert window.image_files[2].dirty is True    # first edit landed mid-save -> kept
    # The in-flight write still produced a valid manifest listing all pages.
    manifest = load_project(project_dir / "manifest.json")
    assert len(manifest["pages"]) == 3


@pytest.mark.gui
def test_async_save_completion_bails_on_swapped_session(
    qtbot, tmp_path, monkeypatch
) -> None:
    """T-QHH-03: replacing image_files wholesale (+ generation bump) during a
    running save makes the completion BAIL without touching the new session;
    the worker's disk artifacts remain internally consistent."""
    from manga_ai_studio.core.image_file import ImageFile

    chapter, window = _open_three_page_session(qtbot, tmp_path)
    default = chapter / "chapter.mas-project"
    gen_before = window._session_generation

    import threading

    started = threading.Event()
    release = threading.Event()
    real_task = window._run_save_task

    def slow_task(payloads, pdir_, nm_, stems_):
        started.set()
        release.wait(timeout=15)
        return real_task(payloads, pdir_, nm_, stems_)

    monkeypatch.setattr(window, "_run_save_task", slow_task)
    _stub_dir_dialog(monkeypatch, default)
    assert window._save_project(force_as=True) is True
    qtbot.waitUntil(started.is_set, timeout=10000)

    # Swap the session OUT under the running save.
    new_imfs = [ImageFile(path=window.image_files[0].path, original_verified=True)]
    new_imfs[0].dirty = True
    window.image_files = new_imfs
    window._session_generation = gen_before + 1

    release.set()
    _wait_save_done(qtbot, window)

    # The new session's flags are untouched by the stale completion...
    assert window.image_files[0].dirty is True
    assert window._project_dir is None  # ...and its bookkeeping never ran
    # ...while the worker's writes stayed internally consistent on disk.
    manifest = load_project(default / "manifest.json")
    assert len(manifest["pages"]) == 3


@pytest.mark.gui
def test_async_save_failure_keeps_flags_and_cleans_stray(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Worker-phase OSError: the T-05-12 critical copy fires, ZERO dirty
    flags are cleared (the session stays fully recoverable), and the stray
    self-created default folder is removed."""

    chapter, window = _open_three_page_session(qtbot, tmp_path)
    _dirty_page_idx(window, 0)
    _dirty_page_idx(window, 1)

    def _boom(*a, **k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(
        "manga_ai_studio.core.project_io.save_project_incremental", _boom
    )
    default = chapter / "chapter.mas-project"
    _stub_dir_dialog(monkeypatch, default)
    criticals = _capture_critical(monkeypatch)

    saved = window._save_project(force_as=True)
    _wait_save_done(qtbot, window)

    assert saved is True  # dispatch succeeded; the FAILURE arrived async
    assert criticals
    assert criticals[0][0] == "Couldn't save 'chapter'."
    assert (
        criticals[0][1]
        == "Check that the folder is writable and see the log for details."
    )
    assert not default.exists()  # WR-01 stray-folder cleanup honored
    assert window._session_dirty()  # ALL flags intact (T-05-12 contract)
    assert window.image_files[0].dirty and window.image_files[1].dirty


# --------------------- quick-260907-l3w: Open Folder project detection router


def _make_project_on_disk(
    qtbot, tmp_path, monkeypatch, project_dir: Path, count: int = 2
) -> Path:
    """Build a REAL on-disk project at ``project_dir`` via the established
    recipe: seed a window session from a page folder, then Save As.

    The seed folder is named ``chapter`` so the save-side name derivation
    (source-folder name) writes ``name: "chapter"`` into the manifest —
    matching the established recipes in this file."""
    pages = tmp_path / "chapter"
    _make_pages(pages, count=count)
    seed = _make_window(qtbot, tmp_path, folder=pages)
    _dirty(seed)
    _save_as(seed, project_dir, monkeypatch, qtbot=qtbot)
    assert (project_dir / "manifest.json").is_file()
    return project_dir


@pytest.mark.gui
def test_open_folder_on_project_dir_loads_project_session(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Open Folder on a directory that IS a project loads the full project
    session — the identical end state to Open Project (project identity,
    page count, per-page embedded images, restored title)."""
    project_dir = _make_project_on_disk(
        qtbot, tmp_path, monkeypatch, tmp_path / "chapter.mas-project"
    )
    window = _make_window(qtbot, tmp_path)
    _stub_dir_dialog(monkeypatch, project_dir)
    window.open_folder()
    QApplication.processEvents()

    assert window._project_dir == project_dir
    assert window._project_name == "chapter"
    assert len(window.image_files) == 2
    for imf in window.image_files:
        assert imf.current_image is not None
        assert imf.current_image.shape[:2] == (60, 60)
    assert window.windowTitle() == (
        "Manga AI Studio \u2014 chapter \u2014 page_01.png"
    )


@pytest.mark.gui
def test_open_folder_on_parent_of_project_loads_subdir_project(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Open Folder on a directory CONTAINING a project subdir loads THAT
    subdir's project session (one-level containment detection)."""
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / "notes.txt").write_text("loose file", encoding="utf-8")
    project_dir = _make_project_on_disk(
        qtbot, tmp_path, monkeypatch, outer / "chapter.mas-project"
    )
    window = _make_window(qtbot, tmp_path)
    _stub_dir_dialog(monkeypatch, outer)
    window.open_folder()
    QApplication.processEvents()

    assert window._project_dir == project_dir == outer / "chapter.mas-project"
    assert window._project_name == "chapter"
    assert len(window.image_files) == 2


@pytest.mark.gui
def test_open_folder_corrupt_manifest_keeps_session_no_gate(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Open Folder on a dir whose manifest.json is corrupt -> the
    corrupt-project critical fires, the current session is untouched, and
    the Unsaved Changes gate did NOT consume a prompt first (detection
    precedes gating)."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    before = [imf.path for imf in window.image_files]

    corrupt_dir = tmp_path / "bad.mas-project"
    corrupt_dir.mkdir()
    (corrupt_dir / "manifest.json").write_text(
        "this is not json {", encoding="utf-8"
    )

    captured = _capture_critical(monkeypatch)
    titles: list = []
    _stub_messagebox_exec(monkeypatch, role=None, capture=titles)
    _stub_dir_dialog(monkeypatch, corrupt_dir)
    window.open_folder()
    QApplication.processEvents()

    assert captured and "Couldn't open" in captured[0][0]
    assert "corrupt or from a newer version" in captured[0][1]
    assert "Unsaved Changes" not in titles  # detection precedes gating
    assert [imf.path for imf in window.image_files] == before
    assert window._session_dirty()  # the dirty page survived untouched
    assert window._project_dir is None
    assert window.canvas.get_image_numpy().shape[:2] == (60, 60)


@pytest.mark.gui
def test_open_folder_gate_runs_exactly_once(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Dirty session + Open Folder on a valid project dir -> EXACTLY ONE
    Unsaved Changes prompt for the whole action (the router delegates to
    _load_project_session whose internal D-07 gate is the one and only
    gate — no double-prompt)."""
    project_dir = _make_project_on_disk(
        qtbot, tmp_path, monkeypatch, tmp_path / "chapter.mas-project"
    )
    window = _make_window(qtbot, tmp_path, folder=tmp_path / "session-pages")
    _dirty(window)
    titles: list = []
    _stub_messagebox_exec(
        monkeypatch,
        role=QMessageBox.ButtonRole.DestructiveRole,  # Discard
        capture=titles,
    )
    _stub_dir_dialog(monkeypatch, project_dir)
    window.open_folder()
    QApplication.processEvents()

    assert titles == ["Unsaved Changes"]  # exactly one prompt, no double-gate
    assert window._project_dir == project_dir
    assert len(window.image_files) == 2


@pytest.mark.gui
def test_open_folder_plain_images_unchanged(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A plain images folder via open_folder keeps today's behavior:
    sidebar populated natsorted, project identity reset, original_verified."""
    folder = tmp_path / "plain"
    _make_pages(folder, count=2)
    window = _make_window(qtbot, tmp_path)
    _stub_dir_dialog(monkeypatch, folder)
    window.open_folder()
    QApplication.processEvents()

    assert window._project_dir is None
    assert [imf.path.name for imf in window.image_files] == [
        "page_01.png",
        "page_02.png",
    ]
    assert all(imf.original_verified for imf in window.image_files)


@pytest.mark.gui
def test_folder_drop_reroutes_through_detection(
    qtbot, tmp_path, monkeypatch
) -> None:
    """_on_folder_dropped delegates to the router: dropping a PROJECT
    folder loads the project session (identical detection to Open Folder);
    the file-drop path (_on_files_dropped) stays untouched."""
    project_dir = _make_project_on_disk(
        qtbot, tmp_path, monkeypatch, tmp_path / "chapter.mas-project"
    )
    window = _make_window(qtbot, tmp_path)
    window._on_folder_dropped(project_dir)
    QApplication.processEvents()
    assert window._project_dir == project_dir
    assert len(window.image_files) == 2

    # File drops keep the direct _set_pages route (no project detection).
    plain = tmp_path / "plain"
    _make_pages(plain, count=1)
    window._on_files_dropped([plain / "page_01.png"])
    QApplication.processEvents()
    assert [imf.path.name for imf in window.image_files] == ["page_01.png"]
    assert window._project_dir is None


# ----------------- quick-260907-l3w: _load_folder loads .mas page files


def _project_minus_manifest(
    qtbot, tmp_path, monkeypatch, project_dir: Path
) -> Path:
    """A saved project folder with its manifest.json deleted — a flat folder
    of self-contained page ``.mas`` files (the plan's fixture shape)."""
    _make_project_on_disk(qtbot, tmp_path, monkeypatch, project_dir)
    (project_dir / "manifest.json").unlink()
    return project_dir


@pytest.mark.gui
def test_open_folder_of_mas_pages_loads_session_without_manifest(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A folder of .mas page files WITHOUT manifest.json (a saved project
    whose manifest was deleted) loads ALL pages as one session: embedded
    images present on every page, folder identity reset (CR-02/T-Q3L-03),
    first page displayed, dirty flags cleared."""
    project_dir = _project_minus_manifest(
        qtbot, tmp_path, monkeypatch, tmp_path / "chapter.mas-project"
    )
    window = _make_window(qtbot, tmp_path)
    _stub_dir_dialog(monkeypatch, project_dir)
    window.open_folder()
    QApplication.processEvents()

    assert len(window.image_files) == 2
    for imf in window.image_files:
        assert imf.current_image is not None
        assert imf.current_image.shape[:2] == (60, 60)
    assert window._project_dir is None
    assert window._project_name is None
    assert not any(imf.dirty for imf in window.image_files)
    # The first page (.mas-backed) displays via its embedded state.
    assert window.canvas.get_image_numpy().shape[:2] == (60, 60)


@pytest.mark.gui
def test_open_folder_mixed_images_and_mas_one_session(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A mixed folder (plain .png + page .mas files) loads ONE natsorted
    session containing both kinds; the first page displays correctly
    whether it is image-backed (on_page_selected lazy path) or .mas-backed
    (_display_page_state embedded path)."""
    project_dir = _project_minus_manifest(
        qtbot, tmp_path, monkeypatch, tmp_path / "chapter.mas-project"
    )

    # --- first page image-backed: the extra sorts before the .mas pages ---
    extra_a = project_dir / "aaa_extra.png"
    PILImage.new("RGB", (60, 60), color=(10, 10, 10)).save(extra_a)
    window = _make_window(qtbot, tmp_path)
    _stub_dir_dialog(monkeypatch, project_dir)
    window.open_folder()
    QApplication.processEvents()
    names = [imf.path.name for imf in window.image_files]
    assert names == ["aaa_extra.png", "page_01.png", "page_02.png"]
    # The .mas-backed pages carry decoded embedded images; the image-backed
    # first page displays via the lazy on_page_selected path.
    assert window.image_files[0].current_image is None  # not yet lazy-loaded
    assert window.image_files[1].current_image is not None
    assert window.image_files[2].current_image is not None
    assert window._project_dir is None
    assert window.canvas.get_image_numpy().shape[:2] == (60, 60)

    # --- first page .mas-backed: delete page_01's original so its path
    # falls back to the .mas INSIDE the opened folder, which natsorts
    # before the image-backed extras' sibling group ordering (all
    # folder-local files share the chapter.mas-project prefix; within it
    # "page_01.mas" sorts before "zzz_extra.png").
    extra_z = project_dir / "zzz_extra.png"
    PILImage.new("RGB", (60, 60), color=(10, 10, 10)).save(extra_z)
    Path(tmp_path / "chapter" / "page_01.png").unlink()
    window2 = _make_window(qtbot, tmp_path)
    _stub_dir_dialog(monkeypatch, project_dir)
    window2.open_folder()
    QApplication.processEvents()
    names2 = [imf.path.name for imf in window2.image_files]
    assert names2 == [
        "aaa_extra.png",
        "page_01.mas",
        "zzz_extra.png",
        "page_02.png",
    ]
    # The FIRST page is .mas-backed: it carries its embedded image and the
    # canvas displays it via the _display_page_state path.
    assert window2.image_files[1].path.name == "page_01.mas"
    assert window2.image_files[1].current_image is not None
    # The image-backed pages stay lazily unloaded (current_image None).
    assert window2.image_files[0].current_image is None
    assert window2.image_files[2].current_image is None
    # page_02's original still verifies -> its path stays the original ref
    # and its embedded image is present.
    assert window2.image_files[3].path.name == "page_02.png"
    assert window2.image_files[3].current_image is not None
    assert window2.canvas.get_image_numpy().shape[:2] == (60, 60)


@pytest.mark.gui
def test_open_folder_corrupt_mas_aborts_whole_open(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A corrupt .mas (garbage bytes) among valid content -> the
    corrupt-project critical fires, the gate ran exactly once, and the
    session is untouched — the build-before-swap is all-or-nothing."""
    chapter = tmp_path / "chapter"
    window = _make_window(qtbot, tmp_path, folder=chapter)
    _dirty(window)
    before = [imf.path for imf in window.image_files]

    folder = tmp_path / "mixed"
    folder.mkdir()
    PILImage.new("RGB", (60, 60), color=(5, 5, 5)).save(folder / "ok_page.png")
    (folder / "broken.mas").write_bytes(b"this is not a mas container")

    captured = _capture_critical(monkeypatch)
    titles: list = []
    _stub_messagebox_exec(
        monkeypatch,
        role=QMessageBox.ButtonRole.DestructiveRole,  # Discard
        capture=titles,
    )
    _stub_dir_dialog(monkeypatch, folder)
    window.open_folder()
    QApplication.processEvents()

    assert captured and "Couldn't open" in captured[0][0]
    assert "corrupt or from a newer version" in captured[0][1]
    assert titles == ["Unsaved Changes"]  # gate-once holds on the abort path
    assert [imf.path for imf in window.image_files] == before
    assert window._session_dirty()  # no partial swap, flags untouched
    assert window._project_dir is None
    assert window.canvas.get_image_numpy().shape[:2] == (60, 60)

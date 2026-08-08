"""GUI tests for the ``_ocr.json`` export wiring (plan 05-08, PROJ-03, D-21/D-22).

Task 1 (TRACER): the single-page Export OCR JSON… path (Text menu,
Ctrl+Shift+E) against the real ``MainWindow`` (pytest-qt) with ``tmp_path``
fixture pages — the D-22 default Save As target (pristine -> sidecar beside
the source; geometry-altered -> ``cleaned/``), the D-19 JSON shape on disk
(matching the core tests), zero-box exports, the save-failure critical
dialog, and the action gating.

Task 2: the Batch Export OCR JSON path (Batch menu) — Worker dispatch over
the Phase 2 batch machinery (``_op_running`` + ``_batch_active`` + progress
surface + Cancel), per-page D-22 placement, mixed-failure reporting, and the
gating while another batch runs.

The batch tests run the REAL ``batch_export_ocr`` (model-free, fast) on a
QThreadPool worker — no adapters are faked; failures are injected by
conflicting filesystem state, and the cancel test holds the worker via a
blocking ``write_page_ocr_json`` until the abort flag flips (the
``test_cancel_batch_updates_status_bar`` pattern from test_gui_batch.py).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PIL import Image as PILImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core import ocr_export  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, PageBox  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from panelcleaner.comic_text_detector.utils.textblock import TextBlock  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


# ---------------------------------------------------------------- helpers

def _make_window(qtbot, tmp_path: Path) -> MainWindow:
    """Build a MainWindow wired to a profile manager in tmp_path."""
    pm = ProfileManager(tmp_path / "config")
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _write_pages(folder: Path, n_pages: int, size: int = 16) -> None:
    """Write ``n_pages`` solid-color pages named page_01..page_N into folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, n_pages + 1):
        PILImage.new("RGB", (size, size), color=(40 * i % 255, 80, 120)).save(
            folder / f"page_{i:02d}.png"
        )


def _load_folder_session(
    qtbot, tmp_path: Path, n_pages: int = 3, size: int = 16
) -> tuple[MainWindow, Path]:
    """A folder session of ``n_pages`` solid-color pages (page_01..page_N).

    Returns ``(window, folder)``; the first page is auto-selected/displayed
    (``_set_pages`` selects + loads page 1).
    """
    folder = tmp_path / "chapter"
    _write_pages(folder, n_pages, size)
    window = _make_window(qtbot, tmp_path)
    window._load_folder(folder)
    QApplication.processEvents()
    return window, folder


def _seed_box_on_canvas(
    window: MainWindow, box=Box(2, 2, 12, 12), text: str = "First line\nSecond line"
) -> None:
    """Place one DETECTED box (with a 2-line payload) on the current page.

    Suppresses the BOXES undo push (the ``_suppress_boxes_push`` guard
    pattern from test_gui_image_dialogs.py) so the session stays clean.
    """
    payload = TextBlock(
        [2, 2, 12, 12],
        lines=[
            [[2, 2], [12, 2], [12, 6], [2, 6]],
            [[2, 8], [12, 8], [12, 12], [2, 12]],
        ],
        text=text,
        vertical=False,
        translation="Two lines of dialogue",
    )
    pagebox = PageBox(box=box, origin=DETECTED, payload=payload, bubble_no=3)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pagebox], [])
    finally:
        window._suppress_boxes_push = False


def _stub_save_dialog(monkeypatch, return_path: str, captured: list) -> None:
    """Route QFileDialog.getSaveFileName to a fixed result, recording the
    default-target argument (args[2]) so tests can assert the D-22 default."""

    def _fake_get_save_file_name(*args, **kwargs):
        captured.append(args[2] if len(args) > 2 else "")
        return (return_path, "OCR JSON (*_ocr.json)")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", _fake_get_save_file_name)


# ===========================================================================
# Task 1 (TRACER) — Export OCR JSON… single page end-to-end
# ===========================================================================


@pytest.mark.gui
def test_export_single_pristine_page(qtbot, tmp_path, monkeypatch) -> None:
    """The TRACER contract: Save As dialog (D-22 default) -> D-19 JSON written
    NEXT TO the source page as {stem}_ocr.json -> success flash.

    The JSON carries version "1", the CURRENT canvas dims, and the seeded
    box's text/translation/bubble_no/origin + per-line entries (the shape the
    core tests pin on ``build_page_ocr_json`` — here asserted on DISK).
    """
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=1)
    _seed_box_on_canvas(window)
    assert window.canvas.box_count() == 1, "precondition: box seeded"
    canvas_dims = window.canvas.get_image_numpy().shape[:2]

    default_arg: list = []
    target = folder / "page_01_ocr.json"
    _stub_save_dialog(monkeypatch, return_path=str(target), captured=default_arg)

    window._export_ocr_json()
    QApplication.processEvents()

    # The dialog's default was the D-22 pristine target (sidecar beside the
    # source) and the file landed there.
    assert default_arg == [str(folder / "page_01_ocr.json")]
    assert target.is_file(), "the D-22 sidecar must exist next to the source"

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["version"] == "1"
    assert data["img_width"] == canvas_dims[1]  # CURRENT canvas dims (D-22)
    assert data["img_height"] == canvas_dims[0]
    blk = data["blocks"][0]
    assert blk["box"] == [2, 2, 12, 12]
    assert blk["text"] == "First line\nSecond line"
    assert blk["translation"] == "Two lines of dialogue"
    assert blk["bubble_no"] == 3
    assert blk["origin"] == DETECTED == "detected"
    assert [entry["text"] for entry in blk["lines"]] == ["First line", "Second line"]

    # Success flash: transient single-page copy (page 1, 1-indexed).
    assert "Exported OCR JSON for page 1." in window.status_bar_left.text()


@pytest.mark.gui
def test_export_single_altered_page_default_dir(qtbot, tmp_path, monkeypatch) -> None:
    """D-22: a geometry-altered page's dialog DEFAULT is inside cleaned/
    (created if missing), and the user's override wins over the default."""
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=1)
    _seed_box_on_canvas(window)
    window.image_files[0].geometry_altered = True

    default_arg: list = []
    override = tmp_path / "custom" / "out_ocr.json"
    _stub_save_dialog(monkeypatch, return_path=str(override), captured=default_arg)

    window._export_ocr_json()
    QApplication.processEvents()

    # The dialog's default target points INTO cleaned/ (the D-22 rule), with
    # the same sidecar name.
    assert default_arg == [str(folder / "cleaned" / "page_01_ocr.json")]
    # The user override wins: the JSON lands at the custom path (its parent
    # is created by write_page_ocr_json's mkdir).
    assert override.is_file()
    data = json.loads(override.read_text(encoding="utf-8"))
    assert data["blocks"][0]["text"] == "First line\nSecond line"


@pytest.mark.gui
def test_export_zero_box_page(qtbot, tmp_path, monkeypatch) -> None:
    """A zero-box page exports WITHOUT a gate or confirm (empty blocks[])."""
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=1)
    assert window.canvas.box_count() == 0, "precondition: no boxes"

    target = folder / "page_01_ocr.json"
    _stub_save_dialog(monkeypatch, return_path=str(target), captured=[])

    window._export_ocr_json()
    QApplication.processEvents()

    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["blocks"] == []
    assert "Exported OCR JSON for page 1." in window.status_bar_left.text()


@pytest.mark.gui
def test_export_write_failure_dialog(qtbot, tmp_path, monkeypatch) -> None:
    """An unwritable target shows the save-failure critical dialog (T-05-12
    copy) without crashing."""
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=1)
    _seed_box_on_canvas(window)

    # Block the target's parent with a FILE named "cleaned": the D-22 mkdir
    # (parents=True, exist_ok=True) raises FileExistsError (an OSError) — the
    # same write-failure class the user hits on a read-only folder.
    blocker = folder / "cleaned"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    default_arg: list = []
    _stub_save_dialog(
        monkeypatch, return_path=str(folder / "cleaned" / "page_01_ocr.json"),
        captured=default_arg,
    )

    dialogs: list = []

    def _record_critical(parent, title, text):  # noqa: ARG001
        dialogs.append((title, text))

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    window._export_ocr_json()  # must NOT raise
    QApplication.processEvents()

    assert len(dialogs) == 1, "the write failure must surface ONE critical dialog"
    title, text = dialogs[0]
    assert "Couldn't save 'page_01_ocr.json'." in title
    assert "writable" in text
    # No success flash — the write did not happen.
    assert "Exported OCR JSON" not in window.status_bar_left.text()


@pytest.mark.gui
def test_export_action_gating(qtbot, tmp_path) -> None:
    """Export OCR JSON… is disabled with no page open and while _op_running."""
    window = _make_window(qtbot, tmp_path)
    assert window.action_export_ocr_json.isEnabled() is False, (
        "no page open -> action must be disabled"
    )

    folder = tmp_path / "chapter"
    _write_pages(folder, n_pages=1)
    window._load_folder(folder)
    QApplication.processEvents()
    assert window.action_export_ocr_json.isEnabled() is True, (
        "page open -> action must be enabled"
    )

    window._op_running = True
    window._refresh_action_states()
    assert window.action_export_ocr_json.isEnabled() is False, (
        "async op running -> action must be disabled"
    )

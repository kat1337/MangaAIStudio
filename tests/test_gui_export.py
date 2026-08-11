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


# ===========================================================================
# Plan 07-01 Task 2 — Export Typeset… (Ctrl+Shift+B): the D-01/D-02 bake
# ===========================================================================


@pytest.mark.gui
def test_typeset_export_action(qtbot, tmp_path, monkeypatch) -> None:
    """File -> Export Typeset… writes the D-03 sidecar with the styled text.

    The seeded box carries a translation ("Hi") styled at a fixed 10 px with
    the outline OFF (so the OPAQUE fill pixels are observable): the baked PNG
    decodes with fill-colored pixels inside the box rect (D-01) while the
    page outside the box keeps the source pixels (no chrome, no drift). The
    dialog's default is the D-03 pristine target ({stem}_typeset.png beside
    the source).
    """
    import numpy as np

    from manga_ai_studio.core.text_style import TextStyle

    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=1)
    # A box sized so the text FITS inside (no unclipped overflow reaching the
    # outside-unchanged assertion region).
    payload = TextBlock(
        [2, 2, 62, 22],
        lines=[[[2, 2], [62, 2], [62, 22], [2, 22]]],
        text="Hi",
        vertical=False,
        translation="Hi",
    )
    style = TextStyle(
        font_size_px=10.0,
        auto_fit=False,
        align_h="left",
        align_v="top",
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 2.0},
    )
    pagebox = PageBox(box=Box(2, 2, 62, 22), origin=DETECTED, payload=payload, style=style)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([pagebox], [])
    finally:
        window._suppress_boxes_push = False

    default_arg: list = []
    target = folder / "page_01_typeset.png"
    _stub_save_dialog(monkeypatch, return_path=str(target), captured=default_arg)

    window._on_export_typeset()
    QApplication.processEvents()

    # The dialog defaulted to the D-03 pristine sidecar next to the source.
    assert default_arg == [str(folder / "page_01_typeset.png")]
    assert target.is_file(), "the D-03 sidecar must exist next to the source"

    with PILImage.open(target) as im:
        baked = np.array(im)
    # The page is a 16x16 solid (40, 80, 120); the box is (2,2,62,22).
    fill = np.array([232, 232, 234])  # the default opaque fill (UI-SPEC A1)
    box_region = baked[2:22, 2:62]
    assert ((box_region == fill).all(axis=2)).any(), (
        "opaque fill-colored glyph pixels must exist inside the box rect"
    )
    # Outside the box the page keeps the source pixels (no chrome, no drift).
    assert (baked[:2] == np.array([40, 80, 120])).all()
    assert (baked[22:] == np.array([40, 80, 120])).all()
    assert (baked[2:22, :2] == np.array([40, 80, 120])).all()
    assert (baked[2:22, 62:] == np.array([40, 80, 120])).all()

    # Success flash (UI-SPEC copy: "Typeset exported -> {filename}").
    assert f"Typeset exported \u2192 {target.name}" in window.status_bar_left.text()


@pytest.mark.gui
def test_typeset_export_failure_dialog_leaves_canvas_untouched(
    qtbot, tmp_path, monkeypatch
) -> None:
    """An unwritable bake target shows the save-failure critical dialog and
    the canvas image object is unchanged (np.array_equal before/after)."""
    import numpy as np

    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=1)
    _seed_box_on_canvas(window)
    before = window.canvas.get_image_numpy().copy()

    # Block the cleaned/ target with a FILE named "cleaned": the D-03 mkdir
    # (inside save_image_optimized) raises FileExistsError — an OSError.
    blocker = folder / "cleaned"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    _stub_save_dialog(
        monkeypatch,
        return_path=str(folder / "cleaned" / "page_01_typeset.png"),
        captured=[],
    )
    dialogs: list = []

    def _record_critical(parent, title, text):  # noqa: ARG001
        dialogs.append((title, text))

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    window._on_export_typeset()  # must NOT raise
    QApplication.processEvents()

    assert len(dialogs) == 1, "the write failure must surface ONE critical dialog"
    title, text = dialogs[0]
    assert "Couldn't save 'page_01_typeset.png'." in title
    assert "writable" in text
    # The canvas image object is unchanged (the bake works on a detached copy).
    assert np.array_equal(window.canvas.get_image_numpy(), before)
    # No success flash — the write did not happen.
    assert "Typeset exported" not in window.status_bar_left.text()


@pytest.mark.gui
def test_typeset_export_action_gating(qtbot, tmp_path) -> None:
    """Export Typeset… is disabled with no page open and while _op_running."""
    window = _make_window(qtbot, tmp_path)
    assert window.action_export_typeset.isEnabled() is False, (
        "no page open -> action must be disabled"
    )

    folder = tmp_path / "chapter"
    _write_pages(folder, n_pages=1)
    window._load_folder(folder)
    QApplication.processEvents()
    assert window.action_export_typeset.isEnabled() is True, (
        "page open -> action must be enabled"
    )

    window._op_running = True
    window._refresh_action_states()
    assert window.action_export_typeset.isEnabled() is False, (
        "async op running -> action must be disabled"
    )


# ===========================================================================
# Task 2 — Batch Export OCR JSON: Worker dispatch + progress + Cancel +
# mixed-result copy (runs the REAL batch_export_ocr on a QThreadPool worker)
# ===========================================================================


@pytest.mark.gui
def test_batch_export_writes_all_pages(qtbot, tmp_path) -> None:
    """The batch writes every page with per-page D-22 placement + dims.

    3-page session with page 2 geometry-altered: 3 JSON files total — 2
    sidecars beside their sources + 1 inside cleaned/ (created if missing);
    each parses with the current dims; the completion flash shows the ok
    count.
    """
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=3)
    _seed_box_on_canvas(window)  # box on the current page (page 1)
    window.image_files[1].geometry_altered = True  # page 2 -> cleaned/

    window.action_batch_export_ocr.trigger()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    sidecar_1 = folder / "page_01_ocr.json"
    sidecar_3 = folder / "page_03_ocr.json"
    cleaned_out = folder / "cleaned" / "page_02_ocr.json"
    assert sidecar_1.is_file(), "pristine page 1 -> sidecar beside the source"
    assert cleaned_out.is_file(), "altered page 2 -> cleaned/ (created)"
    assert sidecar_3.is_file(), "pristine page 3 -> sidecar beside the source"

    canvas_dims = window.canvas.get_image_numpy().shape[:2]
    for path, expected_dims in (
        (sidecar_1, canvas_dims),  # current page: dims from the canvas
        (cleaned_out, (16, 16)),  # non-current: source dims (16x16 page)
        (sidecar_3, (16, 16)),
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == "1"
        assert data["img_width"] == expected_dims[1]
        assert data["img_height"] == expected_dims[0]
    # The current page's box made it into its own JSON only.
    assert len(json.loads(sidecar_1.read_text(encoding="utf-8"))["blocks"]) == 1
    assert json.loads(cleaned_out.read_text(encoding="utf-8"))["blocks"] == []

    # Completion flash: the clean-run copy with the ok count.
    assert "Exported OCR JSON for 3 page(s)." in window.status_bar_left.text()
    assert "failed" not in window.status_bar_left.text()


@pytest.mark.gui
def test_batch_export_mixed_failure_count(qtbot, tmp_path) -> None:
    """A page that fails mid-batch is isolated: the completion flash carries
    the failure count, the other files still write, and no modal opens."""
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=3)
    window.image_files[1].geometry_altered = True  # page 2's target = cleaned/

    # Sabotage page 2's D-22 target: a FILE named "cleaned" blocks the mkdir
    # (FileExistsError, an OSError) -> that page fails through the REAL
    # per-page isolation path; pages 1 + 3 (sidecars) are unaffected.
    blocker = folder / "cleaned"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")

    window.action_batch_export_ocr.trigger()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    assert (folder / "page_01_ocr.json").is_file()
    assert (folder / "page_03_ocr.json").is_file()
    assert blocker.exists() and blocker.read_text(
        encoding="utf-8"
    ) == "i am a file, not a directory", "the sabotaged target stays untouched"

    # Completion flash: the mixed-run copy carries the failure count (the
    # batch path never opens a modal — per-page isolation, D-04).
    status = window.status_bar_left.text()
    assert "Exported OCR JSON for 2 page(s)." in status
    assert "1 page(s) failed \u2014 see the log." in status


@pytest.mark.gui
def test_batch_export_cancel(qtbot, tmp_path, monkeypatch) -> None:
    """Cancel mid-batch: partial files written, "Cancelled" status, no crash,
    _op_running cleared after (the Phase 2 Cancel Batch path)."""
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=3)

    # Capture the worker-injected abort flag so the blocking write wrapper can
    # hold the worker until cancel flips it (test_gui_batch.py's cancel-test
    # pattern).
    captured: dict = {}
    real_batch = ocr_export.batch_export_ocr

    def _recording_batch(pages, progress_callback=None, abort_flag=None):
        captured["abort_flag"] = abort_flag
        return real_batch(pages, progress_callback=progress_callback,
                          abort_flag=abort_flag)

    monkeypatch.setattr(ocr_export, "batch_export_ocr", _recording_batch)

    real_write = ocr_export.write_page_ocr_json

    def _blocking_write(*args, **kwargs):
        result = real_write(*args, **kwargs)  # page 1's file lands for real
        flag = captured.get("abort_flag")
        if flag is not None:
            for _ in range(400):  # hold the worker until cancel flips the flag
                if flag.get():
                    break
                time.sleep(0.005)
        return result

    monkeypatch.setattr(ocr_export, "write_page_ocr_json", _blocking_write)

    window.action_batch_export_ocr.trigger()
    # Page 1's JSON existing means the worker is now holding in the wrapper.
    qtbot.waitUntil(
        lambda: (folder / "page_01_ocr.json").exists(), timeout=5000
    )
    window._cancel_batch()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # Partial work: page 1 wrote; pages 2/3 never started (abort at loop top).
    assert (folder / "page_01_ocr.json").is_file()
    assert not (folder / "page_02_ocr.json").exists()
    assert not (folder / "page_03_ocr.json").exists()
    # Bug B pattern: the stale per-page progress text is gone; "Cancelled".
    assert "Cancelled" in window.status_bar_left.text()
    assert "Exporting OCR JSON" not in window.status_bar_left.text()
    assert window._op_running is False and window._batch_active is False


@pytest.mark.gui
def test_batch_export_gating_and_progress(qtbot, tmp_path) -> None:
    """The batch action is disabled while another batch runs; the progress
    handler renders {done}/{total} and the determinate bar advances."""
    window, folder = _load_folder_session(qtbot, tmp_path, n_pages=3)
    assert window.action_batch_export_ocr.isEnabled() is True

    window.action_batch_export_ocr.trigger()
    # Synchronous at dispatch: the batch is live -> the action re-disables
    # (the _batch_active gate), and the single-page export also blocks.
    assert window.action_batch_export_ocr.isEnabled() is False, (
        "the batch action must be disabled while a batch runs (_batch_active)"
    )
    assert window.action_export_ocr_json.isEnabled() is False, (
        "Export OCR JSON… must be disabled while a batch runs (_op_running)"
    )

    # The progress handler renders the UI-SPEC {done}/{total} copy + the
    # determinate bar advances (invoked directly — the queued worker signal
    # is racy to capture, the test_gui_batch.py precedent).
    window._batch_ocr_total = 3
    window._on_batch_ocr_export_progress((33, "page_02.png"))
    status = window.status_bar_left.text()
    assert "Exporting OCR JSON\u2026" in status
    assert "1/3" in status and "page_02.png" in status
    assert window.progress_bar.value() == 33

    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert window.action_batch_export_ocr.isEnabled() is True, (
        "the batch action must re-enable after the batch finishes"
    )

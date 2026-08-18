"""GUI tests for the Phase 2 per-page mask persistence (D-11 / FLOW-03).

This is the Phase 2 FLOW-03 (D-11) GUI wiring suite: the load-bearing data-model
change that makes the two-stage batch workflow possible. Phase 1's canvas holds
ONE mask for the *current* page in ``EditorCanvas._mask``, and
``MainWindow.on_page_selected -> reset_history`` discards canvas state on every
page switch. Plan 02-02 lifts mask state onto ``ImageFile.mask`` (whose slot
already exists but was unused for persistence) and saves/restores it at the
``on_page_selected`` boundary so that Batch Detect (Plan 03) can store one mask
per page and Batch Clean (Plan 03) can read them all back.

The three tests here lock the contract:

* ``test_on_page_selected_persists_outgoing_mask`` — navigating FROM a page
  with a painted mask leaves that page's ``ImageFile.mask`` non-None (the
  OUTGOING save side of the seam).
* ``test_mask_survives_navigation`` — navigating away and BACK restores the
  page's mask onto the canvas (the INCOMING restore side of the seam).
* ``test_mask_persistence_uses_copy`` — Pitfall-2 regression guard: mutating
  the canvas mask AFTER persistence must NOT retroactively alter the stored
  ``ImageFile.mask``. The boundary ``.copy()`` (mirroring the Phase 1
  ``test_inpaint_result_display_uses_copy`` discipline) detaches the buffer.

The helpers below are copied VERBATIM from
``tests/test_inpainting/test_inpaint_gui.py`` (lines 43-83) — they are public
test infra and copying keeps the suite self-contained (the Phase 1 convention
is that each test module owns its helpers).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PIL import Image  # noqa: E402

from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QFileDialog  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core import batch_runner  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, USER  # noqa: E402
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary  # noqa: E402
from manga_ai_studio.core.mask_planes import unpack_binary  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (copied from tests/test_inpainting/test_inpaint_gui.py:43-83)
# ---------------------------------------------------------------------------


def _make_window(qtbot, tmp_path):
    """Build a MainWindow wired to a profile manager in tmp_path."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _open_page(window: MainWindow, tmp_path: Path, size: int = 16) -> Path:
    """Open a solid-white page into the window so the canvas has an image."""
    img_path = tmp_path / "page.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    return img_path


def _paint_mask_on_canvas(canvas: EditorCanvas) -> None:
    """Paint a small mask region (a 4x4 block) onto the canvas via set_mask.

    Uses the same path as detection: a grayscale QImage with non-zero pixels.
    """
    mask = QImage(canvas.image_item.pixmap().size(), QImage.Format.Format_Grayscale8)
    mask.fill(0)
    from PySide6.QtGui import QPainter

    painter = QPainter(mask)
    painter.setPen(QColor(255, 255, 255))
    # Paint a 4x4 region at (4,4)-(7,7).
    for x in range(4, 8):
        for y in range(4, 8):
            painter.drawPoint(x, y)
    painter.end()
    canvas.set_mask(mask)


def _load_two_pages(window: MainWindow, tmp_path: Path, size: int = 16) -> tuple[Path, Path]:
    """Load a folder of two PNG pages into ``window.image_files``.

    Drives the same multi-page navigation path Batch Detect/Clean will use:
    write two pages, call ``window._load_folder(tmp_path)`` so the sidebar
    populates two entries, then ``_set_pages`` auto-selects page_a (the first
    page). Subsequent navigation uses
    ``file_table.select_path(path)`` + ``on_page_selected(path)`` (the
    sequence ``_set_pages`` itself uses at main_window.py:555-556).
    """
    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(page_a))
    img.save(str(page_b))
    window._load_folder(tmp_path)
    return page_a, page_b


# ---------------------------------------------------------------------------
# Test 1: OUTGOING persistence (D-11 seam step 1)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_on_page_selected_persists_outgoing_mask(qtbot, tmp_path) -> None:
    """Painting a mask on page 1 then selecting page 2 persists page 1's mask.

    Behavior: on_page_selected captures the OUTGOING page's canvas mask into
    ImageFile.mask BEFORE the page switch. After navigating to page 2, page 1's
    ImageFile.mask must be non-None (the D-11 seam step 1).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    # Page a is the auto-selected first page (verify).
    assert window._current_page_index() == 0

    # Paint a mask on page_a via the canvas.
    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask must be set"

    # Navigate to page_b via the same call sequence _set_pages uses.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)

    # The OUTGOING page (index 0, page_a) must have its mask persisted.
    assert window.image_files[0].mask is not None, (
        "outgoing page's ImageFile.mask must be non-None after navigation"
    )
    # Sanity: the new current page is page_b.
    assert window._current_page_index() == 1


# ---------------------------------------------------------------------------
# Test 2: INCOMING restore (D-11 seam step 4) — the survival crux
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_mask_survives_navigation(qtbot, tmp_path) -> None:
    """Detect/paint on page 1, navigate to page 2 and back; mask survives.

    Behavior: after navigating away from page 1 then back, page 1's
    ImageFile.mask is non-None AND the canvas has the mask restored on it
    (canvas.has_mask() True) — the D-11 seam step 4 (INCOMING restore).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask must be set"

    # Navigate away to page_b, then back to page_a.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)

    # The persisted mask survived on page 1's ImageFile.
    assert window.image_files[0].mask is not None, (
        "page 1's ImageFile.mask must survive a round-trip navigation"
    )
    # The INCOMING mask was restored onto the canvas (D-11 seam step 4).
    assert window.canvas.has_mask() is True, (
        "the canvas must have the mask restored after returning to page 1"
    )


# ---------------------------------------------------------------------------
# Test 3: Pitfall-2 regression guard (.copy() at the boundary)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_mask_persistence_uses_copy(qtbot, tmp_path) -> None:
    """Mutating the canvas after persistence does NOT alter ImageFile.mask.

    Regression guard (Pitfall 2 / RESEARCH §Shared Pattern 5): the boundary
    ``.copy()`` detaches the persisted mask from the live canvas buffer. After
    navigating away (which persists page_a's mask) and back, re-painting the
    canvas differently must NOT retroactively change the stored ImageFile.mask.
    Mirrors the Phase 1 ``test_inpaint_result_display_uses_copy`` discipline.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask must be set"

    # Persist page_a's mask by navigating away.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    assert window.image_files[0].mask is not None, (
        "precondition: page_a mask must have persisted"
    )

    # Snapshot the persisted mask BEFORE further mutation.
    saved_bytes = mask_to_numpy_binary(window.image_files[0].mask).tobytes()

    # Navigate back to page_a and CLEAR the canvas mask (a different content).
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)
    # Overwrite the canvas with a DIFFERENT mask (all-zero via clear or re-fill).
    window.canvas.clear_mask()

    # The stored ImageFile.mask must be byte-identical to the snapshot — the
    # boundary .copy() detached it so post-persistence canvas mutation cannot
    # reach back through the shared buffer.
    after_bytes = mask_to_numpy_binary(window.image_files[0].mask).tobytes()
    assert after_bytes == saved_bytes, (
        "Pitfall-2 regression: mutating the canvas after persistence altered "
        "the stored ImageFile.mask — the boundary .copy() is missing."
    )


# ===========================================================================
# Plan 02-04: UI-wiring tests (PROJ-02 Export + D-08 op_running + Pitfall 7)
#
# The three tests below extend this suite with the Phase 2 Plan 04 contract:
# Export Page writes the DISPLAYED canvas image (not a re-clean), the batch
# dispatch sets _op_running (disabling the model actions + navigation), and
# _on_batch_cleanup unconditionally clears _op_running so the editor is never
# stuck disabled.
# ===========================================================================


def _apply_inpaint_result(window: MainWindow, fill: int = 200) -> None:
    """Composite a known non-original RGB result onto the canvas.

    Mirrors the Phase 1 inpaint-result path (``canvas.set_image_from_numpy``)
    so the displayed image is a distinct, recognizable value the export test
    can later compare against. Used so we do NOT need to run the real LaMa
    adapter (Pitfall 5 — export must not be a re-clean).
    """
    src = window.canvas.get_image_numpy()
    assert src is not None, "precondition: a page must be open"
    result_rgb = np.full(src.shape, fill, dtype=np.uint8)
    window.canvas.set_image_from_numpy(result_rgb)


# ---------------------------------------------------------------------------
# Test 4: Export writes the DISPLAYED image, not a re-clean (PROJ-02 / Pitfall 5)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_export_writes_displayed_image(qtbot, tmp_path, monkeypatch) -> None:
    """Export Page writes canvas.get_image_numpy() to the chosen path.

    Behavior (PROJ-02 / Pitfall 5): Export writes the DISPLAYED canvas image
    via save_image_optimized — it does NOT call the detect or inpaint models
    (export is not a re-clean). The exported file's pixels match the displayed
    canvas, and a fake adapter injected into the window's model-resolution
    path is never invoked.
    """
    window = _make_window(qtbot, tmp_path)
    page_path = _open_page(window, tmp_path)

    # Establish a displayed inpaint result so the canvas shows a non-original
    # image (fill=200) distinguishable from the solid-white source page.
    _apply_inpaint_result(window, fill=200)
    displayed = window.canvas.get_image_numpy()
    assert displayed is not None, "precondition: canvas must show an image"

    # Sentinel fakes: if export_page erroneously re-runs a model, these would
    # be invoked. They record any call so the assertion catches a re-clean.
    detect_calls: list = []
    inpaint_calls: list = []

    class _RecordingDetector:
        def load(self, *a, **k):
            pass

        def detect(self, image):  # noqa: D401
            detect_calls.append(image)
            raise AssertionError("export_page must NOT call the detection model")

    class _RecordingInpainter:
        def load(self, *a, **k):
            pass

        def inpaint(self, image_rgb, mask_binary):  # noqa: D401
            inpaint_calls.append((image_rgb, mask_binary))
            raise AssertionError("export_page must NOT call the inpaint model")

    # Inject the recording adapters at the factory the window resolves through
    # (mirrors test_inpaint_gui.py's backend_factory monkeypatch).
    def _fake_factory(kind, backend):  # noqa: ARG001
        if kind == "detection":
            return _RecordingDetector()
        if kind == "inpainting":
            return _RecordingInpainter()
        raise AssertionError(f"unexpected factory kind: {kind}")

    monkeypatch.setattr("manga_ai_studio.gui.main_window.backend_factory", _fake_factory)

    # Route the Save dialog to a fixed path so export_page writes there.
    export_path = tmp_path / "exported.png"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(export_path), "PNG (*.png)"),
    )

    # The method under test does not exist yet (RED). Once implemented it must
    # write the displayed image and return without touching any model.
    window.export_page()

    # PROJ-02: the file was written.
    assert export_path.exists(), "export_page must write the chosen PNG path"

    # Pitfall 5: no model was called (export is not a re-clean).
    assert detect_calls == [], "export_page must NOT call the detection model"
    assert inpaint_calls == [], "export_page must NOT call the inpaint model"

    # The exported pixels match the DISPLAYED canvas (not a re-clean). Load the
    # file via PIL and compare against the canvas numpy the export read.
    from PIL import Image

    with Image.open(export_path) as out:
        exported_rgb = np.array(out.convert("RGB"))
    assert exported_rgb.shape == displayed.shape
    np.testing.assert_array_equal(
        exported_rgb,
        displayed,
        "export must write the DISPLAYED canvas image, not a re-clean",
    )


# ---------------------------------------------------------------------------
# Test 5: batch dispatch sets _op_running + disables model actions (D-08)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_batch_sets_op_running(qtbot, tmp_path, monkeypatch) -> None:
    """Dispatching a batch sets _op_running and disables Detect/Inpaint (D-08).

    Behavior (D-08): while a batch Worker is dispatched, ``_op_running`` is True
    and the detect/inpaint/batch actions report ``isEnabled() == False``.
    """
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)
    assert len(window.image_files) == 2, "precondition: folder must have 2 pages"

    # Replace the batch entry point with a fake that records the call and
    # returns the Plan 03 summary shape, so the dispatch never loads real
    # torch models. The fake blocks briefly so _op_running is observable True
    # while the worker runs.
    import time

    recorded: list = []

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        recorded.append((pages, cleaned_dir))
        time.sleep(0.1)
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    # Dispatch the batch (the public menu handler delegates to _dispatch_batch).
    window.batch_detect()

    # D-08 gate: _op_running is True and the model actions are disabled.
    assert window._op_running is True, "_op_running must be True while a batch runs"
    assert window.action_detect_text.isEnabled() is False, (
        "Detect Text must be disabled while a batch runs (D-08)"
    )
    assert window.action_inpaint.isEnabled() is False, (
        "Inpaint must be disabled while a batch runs (D-08)"
    )

    # Wait for the worker to finish so the test does not leak a running thread.
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)
    assert recorded, "the batch entry point must have been dispatched"


# ---------------------------------------------------------------------------
# Test 6: _op_running cleared after batch (Pitfall 7 — no stuck-disabled state)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_op_running_cleared_after_batch(qtbot, tmp_path, monkeypatch) -> None:
    """After the batch finishes, _op_running is False and actions re-enable.

    Behavior (Pitfall 7): the finished/aborted handler unconditionally clears
    ``_op_running`` so the editor is never stuck disabled. After the worker
    completes, ``_op_running`` is False AND the model actions are re-enabled.
    """
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)

    def _fake_batch_clean(pages, inp_model_path, inp_backend, cleaned_dir, progress_callback=None, abort_flag=None):  # noqa: ARG001
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_clean", _fake_batch_clean)

    window.batch_clean()

    # Wait for the finished handler to clear _op_running (Pitfall 7).
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    assert window._op_running is False, (
        "_op_running must be False after the batch finishes (Pitfall 7)"
    )
    assert window.action_detect_text.isEnabled() is True, (
        "Detect Text must re-enable after the batch finishes (Pitfall 7)"
    )


# ===========================================================================
# Plan 02-04 checkpoint-rework: regression tests for the 4 user-reported bugs.
#
# The plan's blocking human-verify checkpoint was tested and returned four
# defects. Each test below reproduces the user-reported behavior with a
# failing-test-first regression guard. All four are headless (fake adapters,
# no torch); they drive the same MainWindow batch-dispatch path the user
# clicked through.
#
#   Bug A — wrong status-bar label during Batch Detect ("Cleaning" shown).
#   Bug B — cancel does not update the status-bar text (stuck "Inpainting N%").
#   Bug C — post-batch canvas not refreshed after Batch Clean (no cleaned image
#           shown, mask overlay not cleared).
#   Bug D — batch ignores the user's in-canvas mask edits AND the current page
#           appears unprocessed (D-02 "edits are sacred" + D-11 contract).
# ===========================================================================


def _status_text(window: MainWindow) -> str:
    """Return the current left status-bar text (trimmed of the ellipsis etc)."""
    return window.status_bar_left.text()


@pytest.mark.gui
def test_batch_detect_status_label_says_detecting(qtbot, tmp_path, monkeypatch) -> None:
    """Bug A: Batch Detect progress status must say "Detecting", not "Cleaning".

    Behavior: ``_on_batch_progress`` is mode-aware. During Batch Detect the
    status bar must read like "Detecting N% - page" (NOT the hardcoded
    "Cleaning N% - page"). Regression for the user report "when doing batch
    detect the bottom bar says cleaning instead".

    The test drives the real dispatch to confirm ``_batch_mode`` is set to
    "detect" by ``_dispatch_batch``, then calls ``_on_batch_progress``
    directly (the progress signal is queued across the worker/GUI thread
    boundary, making it racy to capture via a signal spy — but the handler is
    a pure GUI-thread mutation we can invoke directly to assert the label).
    """
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)
    assert len(window.image_files) == 2

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    window.batch_detect()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # _dispatch_batch must have recorded the mode so _on_batch_progress can
    # render a mode-aware verb. (After cleanup _batch_mode is reset to None,
    # so re-establish it the way the dispatch does to exercise the handler.)
    window._batch_mode = "detect"
    window._on_batch_progress((0, "page_a.png"))
    detect_text = _status_text(window)
    assert "Detect" in detect_text and "Cleaning" not in detect_text, (
        f"Batch Detect progress status must say 'Detecting', got: {detect_text!r}"
    )

    # The other modes render their own verbs.
    window._batch_mode = "clean"
    window._on_batch_progress((0, "page_a.png"))
    assert "Cleaning" in _status_text(window), (
        f"Batch Clean progress status must say 'Cleaning', got: {_status_text(window)!r}"
    )

    window._batch_mode = "detect_and_clean"
    window._on_batch_progress((0, "page_a.png"))
    combined = _status_text(window)
    assert "Detecting" in combined and "Cleaning" in combined, (
        f"Batch Detect+Clean progress status must combine the verbs, got: {combined!r}"
    )


@pytest.mark.gui
def test_cancel_batch_updates_status_bar(qtbot, tmp_path, monkeypatch) -> None:
    """Bug B: cancelling a batch must update the status-bar text.

    Behavior: when the user cancels, the status bar must stop showing the
    stale "Inpainting N%"/"Cleaning N%" text and indicate cancellation.
    Regression for the user report "the inpainting x% text at the bottom
    remains, should change to cancelled when cancelled".
    """
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)

    blocker = qtbot.waitSignal(window.batch_abort_requested, timeout=5000)

    # A fake clean that BLOCKS until cancel flips the abort flag, so the
    # "Inpainting N%" status is live when _cancel_batch runs.
    def _fake_batch_clean(pages, inp_model_path, inp_backend, cleaned_dir, progress_callback=None, abort_flag=None):  # noqa: ARG001
        if progress_callback is not None:
            progress_callback.emit((42, pages[0].path.name))
        # Spin until the abort flag flips (cancel pressed) then return a
        # partial summary (mimicking the between-pages abort path).
        if abort_flag is not None:
            import time

            for _ in range(200):
                if abort_flag.get():
                    break
                time.sleep(0.01)
        return {"ok": 0, "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_clean", _fake_batch_clean)

    window.batch_clean()
    # Wait for the progress emission so the "Cleaning 42%" text is set.
    qtbot.waitUntil(lambda: "42" in _status_text(window), timeout=5000)

    # Cancel while the batch is mid-run.
    window._cancel_batch()
    blocker.wait()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    status = _status_text(window)
    assert "Cancel" in status, (
        f"status bar must indicate cancellation, got: {status!r}"
    )
    # The stale progress percent must no longer be the headline status.
    assert "42%" not in status, (
        f"stale progress percent must not remain after cancel, got: {status!r}"
    )


@pytest.mark.gui
def test_batch_clean_refreshes_current_page_canvas(qtbot, tmp_path, monkeypatch) -> None:
    """Bug C: Batch Clean must refresh the current page's canvas on completion.

    Behavior: after a clean-containing batch finishes, the currently-displayed
    page must reflect the cleaned output (its mask overlay cleared and its
    image updated) — the same refresh a single-page Inpaint performs in
    ``_on_inpaint_finished``. Regression for the user report "with batch
    clean, it returns to the folder but does not clean the mask or load the
    cleaned images into the app the same way a normal clean would".
    """
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0, "precondition: page_a is current"

    # Establish a mask on the canvas for page_a (mimics a detected mask the
    # clean will consume). Persist it onto ImageFile.mask so the fake clean's
    # has_mask_content gate passes.
    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: canvas mask present"

    # A distinct cleaned fill value so we can tell the refreshed canvas from
    # the original solid-white page.
    cleaned_fill = 123

    def _fake_batch_clean(pages, inp_model_path, inp_backend, cleaned_dir, progress_callback=None, abort_flag=None):  # noqa: ARG001
        # Simulate the cleaning pipeline: write a known cleaned file into
        # cleaned_dir for every page (the real loop writes via
        # save_image_optimized). page_a's file uses cleaned_fill so the
        # post-batch refresh is observable.
        import numpy as np
        from PIL import Image

        cleaned_dir.mkdir(parents=True, exist_ok=True)
        for page in pages:
            out = cleaned_dir / page.path.name
            arr = np.full((16, 16, 3), cleaned_fill, dtype=np.uint8)
            Image.fromarray(arr, mode="RGB").save(out)
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_clean", _fake_batch_clean)

    before_pixels = window.canvas.get_image_numpy()
    assert before_pixels is not None, "precondition: canvas has an image"

    window.batch_clean()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # The canvas must now show the cleaned page: its mean pixel value must
    # match cleaned_fill (the original was solid white = 255).
    after_pixels = window.canvas.get_image_numpy()
    assert after_pixels is not None, "canvas must still have an image after batch"
    assert abs(float(after_pixels.mean()) - cleaned_fill) < 2, (
        "Batch Clean must refresh the current page's canvas to the cleaned "
        f"output (expected mean ~{cleaned_fill}, got {after_pixels.mean():.1f})"
    )

    # The consumed mask overlay must be cleared (mirrors _on_inpaint_finished
    # CR-16): a red overlay must not sit on the now-cleaned page.
    assert window.canvas.has_mask() is False or not window.canvas.has_mask_content(), (
        "the consumed mask overlay must be cleared after Batch Clean refresh"
    )


@pytest.mark.gui
def test_batch_clean_uses_current_canvas_mask_edits(qtbot, tmp_path, monkeypatch) -> None:
    """Bug D: Batch Clean must flush + use the user's current in-canvas mask.

    Behavior (D-02 "edits are sacred" + D-11 contract): when the user edits
    the mask on the canvas of the CURRENT page (e.g. erases part of it) and
    then runs Batch Clean WITHOUT navigating away, the batch must use the
    EDITED canvas mask — not the stale ``ImageFile.mask`` last persisted on
    navigation. ``_dispatch_batch`` must flush the current page's canvas mask
    into its ``ImageFile.mask`` before handing the pages to batch_clean.

    Regression for the user report: "going to another page and erasing part
    of the mask, then doing batch clean it will ignore the changes to the
    mask".
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    # 1. Paint a mask on page_a, navigate to page_b then back to page_a so the
    #    D-11 seam persists page_a's mask onto ImageFile.mask (the "detected"
    #    baseline the user is about to edit).
    _paint_mask_on_canvas(window.canvas)
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)
    assert window.image_files[0].has_mask_content() is True, (
        "precondition: page_a has a persisted mask"
    )
    persisted_mask_nonzero = int(
        mask_to_numpy_binary(window.image_files[0].mask).sum()
    )
    assert persisted_mask_nonzero > 0, "precondition: persisted mask has content"

    # 2. The user ERASES the entire mask on the canvas (the "edit"). The
    #    canvas now reports no mask CONTENT, but ImageFile.mask still holds
    #    the OLD detected mask because navigation (the only flush trigger)
    #    did not fire. clear_mask() fills transparent in place — has_mask()
    #    stays True (QImage still exists) but has_mask_content() goes False.
    window.canvas.clear_mask()
    assert window.canvas.has_mask_content() is False, (
        "precondition: canvas mask content erased"
    )
    assert window.image_files[0].has_mask_content() is True, (
        "precondition: ImageFile.mask still holds the stale detected mask "
        "(the only flush trigger is on_page_selected, which never fired)"
    )

    # 3. A fake inpainter records the mask it receives for page_a. If the
    #    flush-before-dispatch fix is present, the recorded mask is EMPTY
    #    (mirrors the erased canvas) -> batch_clean's D-03 gate then
    #    passthroughs the page and the inpainter is never called. If the fix
    #    is absent, the stale persisted mask is read and the inpainter runs.
    received_masks: list = []

    def _fake_batch_clean(pages, inp_model_path, inp_backend, cleaned_dir, progress_callback=None, abort_flag=None):  # noqa: ARG001
        # Call the REAL _run_batch_task so the D-03 gate + mask read execute
        # against the ImageFile.mask state _dispatch_batch hands it. This
        # makes the regression test exercise the actual read path.
        from manga_ai_studio.core.batch_runner import _run_batch_task

        class _RecordingInpainter:
            def load(self, *a, **k):
                pass

            def inpaint(self, image_rgb, mask_binary):
                received_masks.append(mask_binary)
                import numpy as np

                return np.full(image_rgb.shape, 7, dtype=np.uint8)

        return _run_batch_task(
            pages,
            mode="clean",
            det_model=None,
            inp_model=_RecordingInpainter(),
            cleaned_dir=cleaned_dir,
            progress_callback=progress_callback,
            abort_flag=abort_flag,
        )

    monkeypatch.setattr(batch_runner, "batch_clean", _fake_batch_clean)

    # Do NOT navigate away — the user ran Batch Clean directly from page_a.
    window.batch_clean()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # The user's edit (erased mask) must be honored: page_a's ImageFile.mask
    # was flushed from the canvas before dispatch, so its mask is now empty
    # -> the D-03 gate passthroughs page_a -> the inpainter is NEVER called
    # for page_a. (If the stale persisted mask were read, the inpainter would
    # be called once and received_masks would be non-empty.)
    assert received_masks == [], (
        "Batch Clean must flush + honor the user's current canvas mask edit "
        "(erased mask). The inpainter was called with the stale persisted "
        f"mask: {received_masks!r}"
    )
    # And ImageFile.mask for page_a must now reflect the erased (empty) state.
    assert window.image_files[0].has_mask_content() is False, (
        "page_a's ImageFile.mask must be flushed to the erased canvas state "
        "before batch dispatch (D-02 edits are sacred)"
    )


# ===========================================================================
# Plan 02-04 D1: detect-only batch must restore the current page's detected
# mask onto the canvas (and the detection must survive a round-trip).
#
# Regression for the user re-test report: "batch detection will detect pages
# N+1 on, skipping current page and pages before that." The detection loop
# correctly writes ImageFile.mask for EVERY page (verified); the root cause is
# a canvas/data-model DESYNC on the current page plus an erasure cascade on
# backwards navigation:
#   - After a detect-ONLY batch, _refresh_current_page_after_batch (written for
#     the Bug C clean-containing fix) UNCONDITIONALLY cleared the canvas mask
#     overlay, so the current page showed NO mask even though its
#     ImageFile.mask had been correctly detected.
#   - The D-11 seam then snapshotted that empty canvas back onto the OUTGOING
#     page's ImageFile.mask on the next navigation, silently erasing the
#     detected mask of the page being left ("skipping current page and pages
#     before").
# The fix makes the refresh mode-aware: for a clean-containing batch keep the
# Bug C behavior (reload cleaned image + clear consumed overlay); for a
# detect-only batch RESTORE the just-detected ImageFile.mask onto the canvas
# so the data model + canvas stay in sync (mirroring the D-11 seam step 4).
# ===========================================================================


@pytest.mark.gui
def test_batch_detect_restores_current_page_mask_on_canvas(qtbot, tmp_path, monkeypatch) -> None:
    """Bug D1: a detect-only batch leaves the current page's detected mask visible.

    Behavior: after a Batch Detect finishes, the current page's just-detected
    ``ImageFile.mask`` must be RESTORED onto the canvas (mirroring the D-11
    seam step 4), NOT cleared. The detection loop correctly writes
    ``ImageFile.mask`` for every page; the bug was that the post-batch refresh
    unconditionally cleared the canvas overlay (a Bug C fix that is correct for
    clean-containing batches but wrong for detect-only batches).

    Regression for the user re-test report "batch detection will detect pages
    N+1 on, skipping current page and pages before that" — the visible symptom
    of the current page showing no mask after a detect batch.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0, "precondition: page_a is current"
    # page_a starts with NO mask (never detected).
    assert window.canvas.has_mask_content() is False, (
        "precondition: canvas has no mask content before detect"
    )

    # A fake detector that returns a KNOWN non-empty mask for every page (the
    # real CTD returns a grayscale heatmap; a small block of 255s suffices to
    # exercise the persistence + restore path). We drive the REAL
    # _run_batch_task so the detection write (page.mask = ...) executes against
    # the actual ImageFile state, exactly like the Bug D test does for clean.
    detected_block_value = 255

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        import numpy as np

        from manga_ai_studio.core.batch_runner import _run_batch_task

        class _FakeDetector:
            def load(self, *a, **k):
                pass

            def detect(self, image_bgr):  # noqa: ARG002
                h, w = 16, 16
                mask = np.zeros((h, w), dtype=np.uint8)
                mask[2:6, 2:6] = detected_block_value  # a 4x4 detected block
                # D-04 (plan 08-09): the loop builds boxes from the blk_list —
                # return a full-page box so the derived mask keeps content.
                return mask, [SimpleNamespace(xyxy=[0, 0, w, h])]

        return _run_batch_task(
            pages,
            mode="detect",
            det_model=_FakeDetector(),
            inp_model=None,
            cleaned_dir=cleaned_dir,
            masker_conf=masker_conf,
            progress_callback=progress_callback,
            abort_flag=abort_flag,
        )

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    window.batch_detect()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # The data model was correctly written by the loop for the current page.
    assert window.image_files[0].has_mask_content() is True, (
        "the detection loop must have written page_a's mask to ImageFile.mask"
    )

    # Bug D1: the canvas must REFLECT that detected mask (not be cleared). The
    # current bug leaves the canvas with no mask content even though the data
    # model holds the detection.
    assert window.canvas.has_mask_content() is True, (
        "after a detect-only batch the current page's detected mask must be "
        "restored onto the canvas (Bug D1: canvas must not be cleared for a "
        "detect-only batch)"
    )
    # And the canvas mask content must match the detected block (sanity: it is
    # the SAME mask the loop wrote, not some other/stale content).
    canvas_mask_np = mask_to_numpy_binary(window.canvas.get_mask())
    detected_nonzero = int(canvas_mask_np.sum())
    assert detected_nonzero > 0, (
        "the canvas mask must carry the detected content (non-zero pixels)"
    )


@pytest.mark.gui
def test_batch_detect_mask_survives_backwards_navigation(qtbot, tmp_path, monkeypatch) -> None:
    """Bug D1 cascade: a detected mask survives a backwards navigation round-trip.

    Behavior: the erasure cascade described in the user report is gone. After a
    detect-only batch the detected masks must survive navigating to another
    page and back — the D-11 seam must NOT overwrite a page's detected
    ImageFile.mask with an empty (desynced) canvas mask. This holds because the
    post-batch refresh now RESTORES the detected mask onto the canvas, so the
    seam's OUTGOING snapshot (step 1) captures the real mask instead of an
    empty buffer.

    Regression for "skipping current page and pages before that" — each
    backwards navigation previously erased the detected mask of the page being
    left.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0, "precondition: page_a is current"

    detected_block_value = 255

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        import numpy as np

        from manga_ai_studio.core.batch_runner import _run_batch_task

        class _FakeDetector:
            def load(self, *a, **k):
                pass

            def detect(self, image_bgr):  # noqa: ARG002
                h, w = 16, 16
                mask = np.zeros((h, w), dtype=np.uint8)
                mask[2:6, 2:6] = detected_block_value
                return mask, [SimpleNamespace(xyxy=[0, 0, w, h])]

        return _run_batch_task(
            pages,
            mode="detect",
            det_model=_FakeDetector(),
            inp_model=None,
            cleaned_dir=cleaned_dir,
            masker_conf=masker_conf,
            progress_callback=progress_callback,
            abort_flag=abort_flag,
        )

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    window.batch_detect()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # Both pages were detected.
    assert window.image_files[0].has_mask_content() is True
    assert window.image_files[1].has_mask_content() is True

    # Snapshot page_a's detected mask content BEFORE the cascade navigation.
    page_a_before = mask_to_numpy_binary(window.image_files[0].mask).tobytes()

    # Navigate to page_b then back to page_a — the path that previously erased
    # the detected mask of the page being left.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)

    # page_a's detected mask must be byte-identical (the cascade is gone).
    page_a_after = mask_to_numpy_binary(window.image_files[0].mask).tobytes()
    assert page_a_after == page_a_before, (
        "Bug D1 cascade: page_a's detected mask was altered by a backwards "
        "navigation round-trip — the post-batch canvas desync let the D-11 "
        "seam overwrite the detected mask with an empty canvas buffer."
    )
    # And the canvas must show the restored mask on page_a after returning.
    assert window.canvas.has_mask_content() is True, (
        "after returning to page_a the canvas must show the detected mask"
    )


# ---------------------------------------------------------------------------
# UAT test 1 gap closure round 2 (plan 04-09): menu bar structure
# ---------------------------------------------------------------------------
# The user's report: "recent files and batch are ahead of File and Edit, it
# should be Recent files, File, and then batch" — Recent Files and Batch must
# be File SUBMENUS only, never top-level menubar entries. Pre-fix the two
# submenus were constructed via menuBar().addMenu(...) (main_window.py:269/292)
# which appends their menuActions to the MENUBAR action list; the later
# file_menu.addMenu re-parents the QMenu but Qt does NOT remove the action
# from the menubar — so they appeared top-level AHEAD of File AND as File
# submenus. Fix: standalone QMenu construction (QMenu(title, self)).


@pytest.mark.gui
def test_menubar_top_level_has_only_the_six_core_menus(qtbot, tmp_path) -> None:
    """The menubar top-level shows exactly File, Edit, View, Text, Tools, Help."""
    window = _make_window(qtbot, tmp_path)
    # Hold strong references: QAction wrappers from actions() are temporary
    # (test_gui_boxes.py:2694 precedent).
    actions = window.menuBar().actions()
    assert [a.text() for a in actions] == [
        "&File",
        "&Edit",
        "&View",
        "&Text",
        "&Tools",
        "&Help",
    ]


@pytest.mark.gui
def test_recent_and_batch_menus_are_file_submenus_not_top_level(qtbot, tmp_path) -> None:
    """Recent Files + Batch menuActions live in the File menu, NOT the menubar."""
    window = _make_window(qtbot, tmp_path)
    actions = window.menuBar().actions()
    file_menu = next(a for a in actions if a.text() == "&File").menu()
    recent_action = window.recent_menu.menuAction()
    batch_action = window.batch_menu.menuAction()
    # Both submenus ARE File-menu entries…
    assert recent_action in file_menu.actions()
    assert batch_action in file_menu.actions()
    # …and are NOT top-level menubar entries (pre-fix they were — the user's
    # exact report: "Recent Files and Batch ahead of File and Edit").
    assert recent_action not in actions
    assert batch_action not in actions


@pytest.mark.gui
def test_file_menu_internal_order(qtbot, tmp_path) -> None:
    """The File menu order (UI-SPEC surface 21, plan 05-05 + plan 07-01): Open
    Image, Open Folder, sep, Open Project, Recent Projects, Recent Files, sep,
    Save Project, Save Project As, sep, Export Page, Export Typeset, Batch,
    sep, Quit."""
    window = _make_window(qtbot, tmp_path)
    actions = window.menuBar().actions()
    file_menu = next(a for a in actions if a.text() == "&File").menu()
    file_actions = file_menu.actions()
    assert [a.text() for a in file_actions if not a.isSeparator()] == [
        "Open Image\u2026",
        "Open Folder\u2026",
        "Open Project\u2026",
        "Recent Projects",
        "Recent Files",
        "Save Project\u2026",
        "Save Project As\u2026",
        "Export Page\u2026",
        "Export Typeset\u2026",
        "Batch",
        "Quit",
    ]
    assert [i for i, a in enumerate(file_actions) if a.isSeparator()] == [2, 6, 9, 13]


# ---------------------------------------------------------------------------
# UAT test 1 gap closure round 2 (plan 04-09): toolbar open action
# ---------------------------------------------------------------------------
# The user's report: "on the small bar under there with tools, it should have
# open folder instead of open image" — the toolbar's open action is Open
# Folder (Ctrl+Shift+O, the manga-workflow default); Open Image stays in the
# File menu (Ctrl+O). Pre-fix main_window.py:617 added action_open_image to
# the toolbar.


@pytest.mark.gui
def test_toolbar_first_action_is_open_folder(qtbot, tmp_path) -> None:
    """The toolbar's first action IS Open Folder (Ctrl+Shift+O), not Open Image."""
    window = _make_window(qtbot, tmp_path)
    toolbar_actions = window.toolbar.actions()
    first = toolbar_actions[0]
    assert first is window.action_open_folder
    assert first.text() == "Open Folder\u2026"
    assert first.shortcut() == QKeySequence("Ctrl+Shift+O")
    assert window.action_open_folder is not window.action_open_image


@pytest.mark.gui
def test_open_image_remains_in_file_menu_not_toolbar(qtbot, tmp_path) -> None:
    """Open Image stays in the File menu (Ctrl+O) and is NOT on the toolbar."""
    window = _make_window(qtbot, tmp_path)
    actions = window.menuBar().actions()
    file_menu = next(a for a in actions if a.text() == "&File").menu()
    assert window.action_open_image in file_menu.actions()
    assert window.action_open_image not in window.toolbar.actions()


@pytest.mark.gui
def test_toolbar_open_folder_triggered_opens_folder(qtbot, tmp_path, monkeypatch) -> None:
    """Triggering the toolbar's first action runs open_folder (not open_image).

    The dialog must be stubbed: open_folder calls the modal
    QFileDialog.getExistingDirectory synchronously — returning "" makes it
    return early (main_window.py:832-834), so trigger() never blocks. Without
    the stub this test would hang on the native modal dialog.
    """
    window = _make_window(qtbot, tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    fired: list[bool] = []
    window.action_open_folder.triggered.connect(lambda: fired.append(True))
    window.action_open_folder.trigger()
    assert fired == [True]


# ===========================================================================
# Phase 8 (plan 08-09): batch dispatch supplies the profile masker conf +
# mode-aware post-batch refresh extended to boxes/planes/states
#
# D-04 adopt-the-rule in the GUI layer: _dispatch_batch threads the profile
# MaskerConfig into the detect-mode worker args, and after a detect-only batch
# the current page's canvas must restore the persisted boxes (under the
# _suppress_boxes_push guard — RESEARCH §5 item 5: batch is headless, so the
# 03-04 D-04 replace gate does NOT apply), the packed auto plane, and the
# per-box border states (the 02-04 Bug-D-family desync lesson). Clean mode is
# unchanged (reload + clear).
# ===========================================================================


@pytest.mark.gui
def test_batch_detect_dispatch_passes_profile_masker_conf(qtbot, tmp_path, monkeypatch) -> None:
    """Bug root: _dispatch_batch("detect") hands the profile's MaskerConfig
    (with the CURRENT radius) to the worker args — the worker derives the
    constrained mask from it (mask_dilation_radius + the masker fit params)."""
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)

    captured: dict = {}

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        captured["masker_conf"] = masker_conf
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    window.batch_detect()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # The worker received the profile's live MaskerConfig (same object —
    # detection-time params are read from current_profile.masker).
    assert "masker_conf" in captured
    assert captured["masker_conf"] is window.profile_manager.config.current_profile.masker
    assert captured["masker_conf"].mask_dilation_radius == 2  # the default radius


@pytest.mark.gui
def test_batch_detect_and_clean_dispatch_passes_profile_masker_conf(qtbot, tmp_path, monkeypatch) -> None:
    """The one-shot detect_and_clean dispatches the profile masker conf too."""
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)

    captured: dict = {}

    def _fake_batch_detect_and_clean(pages, det_model_path, inp_model_path, det_backend, inp_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        captured["masker_conf"] = masker_conf
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_detect_and_clean", _fake_batch_detect_and_clean)

    window.batch_detect_and_clean()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    assert "masker_conf" in captured
    assert captured["masker_conf"] is window.profile_manager.config.current_profile.masker


@pytest.mark.gui
def test_batch_detect_refresh_restores_boxes_auto_plane_and_borders(qtbot, tmp_path, monkeypatch) -> None:
    """After a detect-only batch, _refresh_current_page_after_batch("detect")
    restores the CURRENT page's boxes onto the canvas (set_boxes under the
    _suppress_boxes_push guard — no history push), the composite mask equals
    the persisted auto plane, and the border states render from the per-box
    fields via refresh_box_inpaint_states (no current-page desync — the 02-04
    Bug-D family lesson)."""
    window = _make_window(qtbot, tmp_path)
    _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0, "precondition: page_a is current"
    assert window.canvas.has_boxes() is False, "precondition: no boxes yet"

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, masker_conf, progress_callback=None, abort_flag=None):  # noqa: ARG001
        import numpy as np

        from manga_ai_studio.core.batch_runner import _run_batch_task

        class _FakeDetector:
            def load(self, *a, **k):
                pass

            def detect(self, image_bgr):  # noqa: ARG002
                h, w = image_bgr.shape[:2]
                mask = np.zeros((h, w), dtype=np.uint8)
                mask[2:6, 2:6] = 255  # in-box content (full-page box)
                return mask, [SimpleNamespace(xyxy=[0, 0, w, h])]

        # The REAL constrained detect path (D-04) — persists page.boxes +
        # auto_mask exactly like production.
        return _run_batch_task(
            pages,
            mode="detect",
            det_model=_FakeDetector(),
            inp_model=None,
            cleaned_dir=cleaned_dir,
            masker_conf=masker_conf,
            progress_callback=progress_callback,
            abort_flag=abort_flag,
        )

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    window.batch_detect()
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    # The loop persisted the current page's boxes + packed auto plane.
    imf = window.image_files[0]
    assert imf.boxes is not None and len(imf.boxes) == 1
    assert imf.boxes[0].origin == DETECTED
    assert imf.boxes[0].mask is not None  # fit data survived the worker
    assert imf.auto_mask is not None

    # The refresh restored the boxes onto the canvas (same PageBox instances).
    assert len(window.canvas._box_items) == 1
    restored_item = window.canvas._box_items[0]
    assert restored_item.pagebox is imf.boxes[0]
    # The restore ran under the suppression guard: no BOXES history push.
    assert window._suppress_boxes_push is False  # guard restored
    assert window.history.can_undo_boxes() is False

    # The composite mask equals the persisted auto plane (unpacked at the
    # page dims — the D-04 content contract restored to the canvas).
    canvas_binary = mask_to_numpy_binary(window.canvas.get_mask())
    auto = unpack_binary(imf.auto_mask, 16, 16)
    assert np.array_equal(canvas_binary, auto)

    # Border states render from the per-box fields (refresh_box_inpaint_states).
    threshold = (
        window.profile_manager.config.current_profile.masker
        .mask_max_standard_deviation
    )
    expected_state = restored_item.pagebox.inpaint_state(threshold)
    assert expected_state == "will_inpaint"  # std 0 <= gate, content present
    assert restored_item._inpaint_state == expected_state

    # Manual/erase planes are empty for batch pages (no strokes) — the auto
    # plane alone drives the composite.
    assert imf.mask_manual is None and imf.mask_erase is None


@pytest.mark.gui
def test_batch_clean_refresh_branch_unchanged(qtbot, tmp_path) -> None:
    """The clean-mode refresh branch is UNCHANGED by the Phase 8 extension:
    it still reloads the cleaned output + clears the consumed mask overlay."""
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)

    # A distinct cleaned fill so the refreshed canvas is distinguishable from
    # the original solid-white page.
    cleaned_dir = page_a.parent / "cleaned"
    cleaned_dir.mkdir(exist_ok=True)
    arr = np.full((16, 16, 3), 123, dtype=np.uint8)
    Image.fromarray(arr, mode="RGB").save(cleaned_dir / page_a.name)
    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask overlay present"

    window._refresh_current_page_after_batch("clean")

    # Reloaded the cleaned page (mean ~123, not the original 255)…
    after = window.canvas.get_image_numpy()
    assert after is not None
    assert abs(float(after.mean()) - 123) < 2
    # …and cleared the consumed mask overlay.
    assert window.canvas.has_mask_content() is False

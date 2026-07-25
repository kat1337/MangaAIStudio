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

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QFileDialog  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core import batch_runner  # noqa: E402
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary  # noqa: E402
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

    def _fake_batch_detect(pages, det_model_path, det_backend, cleaned_dir, progress_callback=None, abort_flag=None):  # noqa: ARG001
        recorded.append((pages, cleaned_dir))
        time.sleep(0.1)
        return {"ok": len(pages), "failed": [], "total": len(pages)}

    monkeypatch.setattr(batch_runner, "batch_detect", _fake_batch_detect)

    # Dispatch the batch (the method does not exist yet — RED).
    window._run_batch_detect()

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

    window._run_batch_clean()

    # Wait for the finished handler to clear _op_running (Pitfall 7).
    qtbot.waitUntil(lambda: window._op_running is False, timeout=5000)

    assert window._op_running is False, (
        "_op_running must be False after the batch finishes (Pitfall 7)"
    )
    assert window.action_detect_text.isEnabled() is True, (
        "Detect Text must re-enable after the batch finishes (Pitfall 7)"
    )

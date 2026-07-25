"""Integration tests for the Phase 2 FLOW-03 batch driver (plan 02-03).

These tests are the TDD contract for ``manga_ai_studio.core.batch_runner``: the
three entry points (``batch_detect``, ``batch_clean``, ``batch_detect_and_clean``)
drive a single page-loop task fn ``_run_batch_task`` that (D-05) reuses the
Phase 1 adapters + Worker/Abort machinery, (Pitfall 3) loads each model ONCE,
(D-03) skips LaMa + copies the original through for empty masks, (D-04) isolates
per-page failures, (D-09) aborts only between pages, (D-07) writes only into a
``cleaned/`` subdir, and (D-10) emits per-page progress.

The suite runs headless with the shared fake adapters in
``tests/test_core/conftest.py`` — NO torch, NO model weights, NO Qt event loop.
``RecordingSignal`` stands in for the Worker's ``progress`` signal; a real
``SharableFlag`` (from ``worker_thread.py``) provides the abort primitive so
``test_abort_between_pages`` exercises the exact production cancel path.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from manga_ai_studio.core.image_file import ImageFile
from manga_ai_studio.core.mask_editor import numpy_binary_to_mask_qimage

# These imports will FAIL (RED) until Task 2 lands batch_runner.py.
from manga_ai_studio.core.batch_runner import (  # noqa: E402
    batch_clean,
    batch_detect,
    batch_detect_and_clean,
)
from manga_ai_studio.gui.worker_thread import Abort, SharableFlag  # noqa: E402

from tests.test_core.conftest import (  # noqa: E402
    FakeDetectionModel,
    FakeInpaintModel,
    RecordingSignal,
    install_fakes,
    make_pages,
)


# ---------------------------------------------------------------------------
# Test 1: detect_and_clean one-shot writes cleaned/ for every page
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_batch_detect_and_clean(tmp_path, monkeypatch) -> None:
    """detect_and_clean calls detect on all 3 pages, inpaints pages with mask
    content, and writes ``cleaned/pageN.<ext>`` for every page; returns
    ``{ok: 3, failed: [], total: 3}`` (D-01 + D-04).

    Behavior 1: a 3-page batch in detect_and_clean mode produces 3 outputs.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=3)
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    summary = batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=cleaned,
        progress_callback=None,
        abort_flag=None,
    )

    assert summary == {"ok": 3, "failed": [], "total": 3}
    assert len(det.calls) == 3
    # Every page has detected mask content -> every page is inpainted.
    assert len(inp.calls) == 3
    for i in range(3):
        assert (cleaned / f"page{i + 1}.png").is_file()


# ---------------------------------------------------------------------------
# Test 2: empty/None mask is skipped (D-03 passthrough)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_batch_clean_skips_empty_mask(tmp_path, monkeypatch) -> None:
    """A page whose mask is empty/None is NOT passed to the inpaint model; the
    original is copied through via ``passthrough_original`` (D-03).

    Behavior 2: the fake inpaint model's call list does not include that page.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=2)
    # page1: a mask WITH content; page2: mask left None (never detected).
    mask_with_content = numpy_binary_to_mask_qimage(_small_mask())
    pages[0].mask = mask_with_content
    # pages[1].mask stays None -> has_mask_content() is False -> passthrough.
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    summary = batch_clean(
        pages,
        inp_model_path=Path("fake_inp.pt"),
        inp_backend="torch",
        cleaned_dir=cleaned,
        progress_callback=None,
        abort_flag=None,
    )

    # Both pages produce output, but only page1 was inpainted.
    assert summary == {"ok": 2, "failed": [], "total": 2}
    assert len(inp.calls) == 1
    # page2 (empty mask) was copied through unchanged; page1 was re-encoded.
    assert (cleaned / "page1.png").is_file()
    assert (cleaned / "page2.png").is_file()


# ---------------------------------------------------------------------------
# Test 3: per-page failure is non-fatal (D-04)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_per_page_failure_continues(tmp_path, monkeypatch) -> None:
    """One page raises during detect; the batch continues, the failed page is
    listed in ``summary.failed``, and the other pages still produce output (D-04).

    Behavior 3: a single bad page does not stop the rest.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=3)
    cleaned = src / "cleaned"

    # FakeDetectionModel raises on its 2nd detect call (page2).
    det = FakeDetectionModel(fail_on_call=2)
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    summary = batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=cleaned,
        progress_callback=None,
        abort_flag=None,
    )

    assert summary["total"] == 3
    assert summary["ok"] == 2
    assert len(summary["failed"]) == 1
    failed_path, failed_msg = summary["failed"][0]
    assert Path(failed_path).name == "page2.png"
    assert "injected detect failure" in failed_msg
    # page1 + page3 still produced output; page2 did not.
    assert (cleaned / "page1.png").is_file()
    assert not (cleaned / "page2.png").is_file()
    assert (cleaned / "page3.png").is_file()


# ---------------------------------------------------------------------------
# Test 4: abort between pages (D-09 + Pitfall 4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_abort_between_pages(tmp_path, monkeypatch) -> None:
    """Setting the abort_flag after page 1 causes ``Abort`` to be raised before
    page 2 starts; page 1's output exists and page 2's does not (D-09 + Pitfall
    4: no half-written file).

    Behavior 4: cancel lands strictly between pages.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=2)
    cleaned = src / "cleaned"

    abort = SharableFlag(False)
    # Flip the shared flag after the first detect so the NEXT loop-top check
    # raises Abort (the loop checks abort ONLY at the top, never mid-page).
    det = FakeDetectionModel(set_flag_after=1, flag=abort)
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    with pytest.raises(Abort):
        batch_detect_and_clean(
            pages,
            det_model_path=Path("fake_det.pt"),
            inp_model_path=Path("fake_inp.pt"),
            det_backend="torch",
            inp_backend="torch",
            cleaned_dir=cleaned,
            progress_callback=None,
            abort_flag=abort,
        )

    # page1 completed before the abort; page2 never started.
    assert (cleaned / "page1.png").is_file()
    assert not (cleaned / "page2.png").is_file()


# ---------------------------------------------------------------------------
# Test 5: outputs land only in cleaned/ (D-07 + T-02-03 name guard)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_output_to_cleaned_subdir(tmp_path, monkeypatch) -> None:
    """Every output lands in ``source.parent / "cleaned"`` with the original
    filename; nothing is written to ``source.parent`` directly (D-07 + T-02-03
    name guard).

    Behavior 5: the loop writes only into the cleaned subdir.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=3)
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=cleaned,
        progress_callback=None,
        abort_flag=None,
    )

    # All outputs are inside cleaned/.
    outputs = {p.name for p in cleaned.iterdir()}
    assert outputs == {"page1.png", "page2.png", "page3.png"}
    # No stray outputs in the source folder (only the original page PNGs).
    src_entries = {p.name for p in src.iterdir() if p.is_file()}
    assert src_entries == {"page1.png", "page2.png", "page3.png"}
    # The name guard rejects anything other than cleaned/.
    with pytest.raises(ValueError):
        batch_detect_and_clean(
            pages,
            det_model_path=Path("fake_det.pt"),
            inp_model_path=Path("fake_inp.pt"),
            det_backend="torch",
            inp_backend="torch",
            cleaned_dir=src / "not_cleaned",  # T-02-03 defense-in-depth
            progress_callback=None,
            abort_flag=None,
        )


# ---------------------------------------------------------------------------
# Test 6: per-page progress (D-10)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_progress_per_page(tmp_path, monkeypatch) -> None:
    """``progress_callback`` receives a ``(percent, page_name)`` tuple per page
    (D-10).

    Behavior 6: progress is emitted once per page.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=3)
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    progress = RecordingSignal()
    batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=cleaned,
        progress_callback=progress,
        abort_flag=None,
    )

    assert len(progress.calls) == 3
    for i, payload in enumerate(progress.calls):
        assert isinstance(payload, tuple) and len(payload) == 2
        percent, page_name = payload
        assert isinstance(percent, int)
        assert page_name == f"page{i + 1}.png"
    # page 1 is at 0% (before processing), page 3 is at int(2/3*100)=66%.
    assert progress.calls[0][0] == 0
    assert progress.calls[2][0] == 66


# ---------------------------------------------------------------------------
# Test 7: models loaded once (Pitfall 3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_loaded_once(tmp_path, monkeypatch) -> None:
    """``FakeDetectionModel.load`` and ``FakeInpaintModel.load`` are each called
    exactly once for a 3-page batch (Pitfall 3: load ONCE per batch, never per
    page).

    Behavior 7: a 30-page batch does not re-download 80MB/200MB models.
    """
    src = tmp_path / "chapter"
    pages = make_pages(src, count=3)
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=cleaned,
        progress_callback=None,
        abort_flag=None,
    )

    assert det.load_calls == 1
    assert inp.load_calls == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _small_mask() -> np.ndarray:
    """A small binary mask array with a painted region (4x4 -> center 255)."""
    m = np.zeros((4, 4), dtype=np.uint8)
    m[1:3, 1:3] = 255
    return m

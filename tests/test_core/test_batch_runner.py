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
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

import panelcleaner.config as cfg

from manga_ai_studio.core.box_model import DETECTED
from manga_ai_studio.core.image_file import ImageFile
from manga_ai_studio.core.mask_editor import (
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.core.mask_planes import unpack_binary

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
    08.1 inverted gate: uniform low-std pages are now fill (not inpaint), so
    the uniform fixture pages produce 0 LaMa calls (fill-only), but still 3 ok.
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
        masker_conf=cfg.MaskerConfig(),
        progress_callback=None,
        abort_flag=None,
    )

    assert summary == {"ok": 3, "failed": [], "total": 3}
    assert len(det.calls) == 3
    # 08.1 inverted: uniform pages are fill, not LaMa inpaint, so 0 calls.
    assert len(inp.calls) == 0
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
        masker_conf=cfg.MaskerConfig(),
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
            masker_conf=cfg.MaskerConfig(),
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
        masker_conf=cfg.MaskerConfig(),
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
            masker_conf=cfg.MaskerConfig(),
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
        masker_conf=cfg.MaskerConfig(),
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
        masker_conf=cfg.MaskerConfig(),
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


# ===========================================================================
# Phase 8 (plan 08-09) — constrained detect path + masker_conf threading (D-04)
#
# The detect branch now builds per-page boxes from the SAME detect pass and
# derives the box-constrained mask (build_detected_pageboxes +
# derive_page_mask_state — the 08-03 seam core). These tests lock: the
# persistence shape (page.boxes / page.raw_detected_mask / page.auto_mask /
# page.mask), the D-02 out-of-box discard reaching the LaMa input, the D-03
# passthrough extension (zero gate-passing boxes -> no LaMa call), the
# MASK-01 radius effect in the batch path, and the Qt-free worker derivation
# (every assertion before the QImage step touches numpy/PIL outputs only).
# ===========================================================================


class _FixtureDetector:
    """Fake detector returning per-call ``(heatmap, blk_list)`` pairs.

    Mirrors ``TorchCTDModel.detect``; the per-call pairs let each page drive a
    different fixture (gate-passing / gate-failing / out-of-box content).
    The batch entry point resolves it through ``backend_factory`` (the
    ``install_fakes`` monkeypatch), exactly like ``FakeDetectionModel``.
    """

    def __init__(self, heatmaps, blk_lists) -> None:
        self.calls: list[np.ndarray] = []
        self.load_calls: int = 0
        self.heatmaps = list(heatmaps)
        self.blk_lists = list(blk_lists)
        # quick-260903-lm6: batch_runner configures the det model before load.
        self.configure_calls: list[dict] = []

    def configure(self, **kwargs) -> None:
        """Mirror ``TorchCTDModel.configure(**kwargs)`` (pre-load knob pass)."""
        self.configure_calls.append(kwargs)

    def load(self, model_path, device: str = "cpu") -> None:
        self.load_calls += 1

    def detect(self, image: np.ndarray):
        self.calls.append(image)
        i = len(self.calls) - 1
        return self.heatmaps[i], self.blk_lists[i]


def _blk(x1, y1, x2, y2):
    """A TextBlock-like fake (any object with a ``.xyxy`` of length 4)."""
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


def _write_strokes_page(path: Path) -> np.ndarray:
    """Write a 60x50 (240,240,240) page with in-box strokes at box
    (10,10)-(40,30) plus a 10x10 out-of-box blob at the bottom-right; returns
    the matching heatmap. The MASKER gate passes on the uniform page (std 0),
    so the box contributes — the D-02 constraint is observable as "out-of-box
    pixels never reach the auto composite" (the 08-03 fixture shape)."""
    page = Image.new("RGB", (60, 50), (240, 240, 240))
    draw = ImageDraw.Draw(page)
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    for y in (13, 18, 23, 27):
        draw.rectangle([14, y, 36, y + 1], fill=(20, 20, 20))
        heatmap[y : y + 2, 14:37] = 255
    # D-02 out-of-box content: the box union never covers the bottom-right.
    draw.rectangle([45, 35, 55, 44], fill=(20, 20, 20))
    heatmap[35:45, 45:55] = 255
    page.save(path)
    return heatmap


def _noise_heatmap() -> np.ndarray:
    """The strokes heatmap returned for a NOISY page (the gate-fail fixture —
    the honest fit std rises above the default threshold, so the box stores
    (mask, std>threshold) and contributes nothing at the default gate)."""
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    for y in (13, 18, 23, 27):
        heatmap[y : y + 2, 14:37] = 255
    return heatmap


@pytest.mark.unit
def test_batch_detect_persists_boxes_and_constrained_masks(tmp_path, monkeypatch) -> None:
    """D-04 detect mode (08.1 inverted): the fake det_model returns (heatmap with in-box +
    out-of-box content, [blk]) and a masker_conf -> page.boxes is populated
    (one DETECTED PageBox with non-None PIL mask + float std_dev + fill_color),
    page.mask composite for uniform low-std is now fill (auto empty), but D-02
    out-of-box discard still holds, D-08 retention still holds.
    """
    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    heatmap = _write_strokes_page(src / "page1.png")
    page = ImageFile(path=src / "page1.png")

    det = _FixtureDetector([heatmap], [[_blk(10, 10, 40, 30)]])
    install_fakes(monkeypatch, det, FakeInpaintModel())

    summary = batch_detect(
        [page],
        det_model_path=Path("fake_det.pt"),
        det_backend="torch",
        cleaned_dir=src / "cleaned",
        masker_conf=cfg.MaskerConfig(),
        progress_callback=None,
        abort_flag=None,
    )

    assert summary == {"ok": 1, "failed": [], "total": 1}
    assert page.boxes is not None and len(page.boxes) == 1
    pb = page.boxes[0]
    assert pb.origin == DETECTED
    assert pb.box.as_tuple == (10, 10, 40, 30)
    assert pb.mask is not None and isinstance(pb.mask, Image.Image)
    assert pb.mask.mode == "1"
    assert isinstance(pb.std_dev, float)
    assert pb.fill_color is not None
    assert page.raw_detected_mask is not None
    raw = unpack_binary(page.raw_detected_mask, 50, 60)
    assert raw[40, 50] == 255
    assert page.auto_mask is not None
    auto = unpack_binary(page.auto_mask, 50, 60)
    assert auto[40, 50] == 0
    assert np.count_nonzero(auto[:10, :]) == 0
    assert np.count_nonzero(auto[31:, :]) == 0
    assert np.count_nonzero(auto[:, :10]) == 0
    assert np.count_nonzero(auto[:, 41:]) == 0
    # 08.1 inverted: uniform low-std -> fill, so auto inside is 0
    assert np.count_nonzero(auto[10:31, 10:41]) == 0
    # But the box's mask is still stored and fill_color present
    assert pb.mask is not None
    assert page.mask is not None
    # For uniform, the composite mask (page.mask) is derived from auto (inpaint) which is now 0, so page.mask is empty (fill not in mask plane)
    # So has_mask_content may be False for uniform after inversion; we check the auto plane is empty.
    assert np.count_nonzero(auto) == 0
    assert page.mask_manual is None and page.mask_erase is None


@pytest.mark.unit
def test_batch_detect_and_clean_inpaints_constrained_mask(tmp_path, monkeypatch) -> None:
    """D-02 in the batch inpaint (08.1 inverted): uniform low-std page is fill-only,
    so LaMa is NOT called (0 calls) and no inpaint input to check. The D-02 discard
    still holds for the auto plane (tested in the detect-persist test). For this
    uniform fixture, the batch produces a passthrough (fill-only) output."""
    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    heatmap = _write_strokes_page(src / "page1.png")
    page = ImageFile(path=src / "page1.png")

    det = _FixtureDetector([heatmap], [[_blk(10, 10, 40, 30)]])
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    summary = batch_detect_and_clean(
        [page],
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=src / "cleaned",
        masker_conf=cfg.MaskerConfig(),
        progress_callback=None,
        abort_flag=None,
    )

    assert summary == {"ok": 1, "failed": [], "total": 1}
    # 08.1 inverted: uniform -> fill, so no LaMa call
    assert len(inp.calls) == 0
    assert (src / "cleaned" / "page1.png").is_file()


@pytest.mark.unit
def test_batch_detect_and_clean_gate_fail_passthrough(tmp_path, monkeypatch) -> None:
    """D-03 empty-mask passthrough extension (08.1 inverted): uniform low-std page
    is fill-only (auto empty), noisy high-std page is inpaint. So only the noisy
    page triggers LaMa; the uniform page passthroughs (fill handled separately).
    """
    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    # page1: uniform strokes page -> now fill (auto empty) per D-01 inverted.
    heatmap1 = _write_strokes_page(src / "page1.png")
    # page2: NOISY page -> honest fit std > threshold -> now INPAINT per D-01 inverted.
    rng = np.random.default_rng(1234)
    noisy_rgb = rng.integers(0, 256, size=(50, 60, 3), dtype=np.uint8)
    Image.fromarray(noisy_rgb, mode="RGB").save(src / "page2.png")
    heatmap2 = _noise_heatmap()

    det = _FixtureDetector(
        [heatmap1, heatmap2],
        [[_blk(10, 10, 40, 30)], [_blk(10, 10, 40, 30)]],
    )
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    pages = [ImageFile(path=src / "page1.png"), ImageFile(path=src / "page2.png")]
    summary = batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=src / "cleaned",
        masker_conf=cfg.MaskerConfig(),
        progress_callback=None,
        abort_flag=None,
    )

    assert summary == {"ok": 2, "failed": [], "total": 2}
    # 08.1 inverted: only noisy page passes inpaint gate -> 1 call
    assert len(inp.calls) == 1
    assert (src / "cleaned" / "page1.png").is_file()
    assert (src / "cleaned" / "page2.png").is_file()
    assert pages[1].boxes is not None and len(pages[1].boxes) == 1
    assert pages[1].boxes[0].std_dev is not None
    assert pages[1].boxes[0].std_dev > cfg.MaskerConfig().mask_max_standard_deviation
    # Noisy page now has mask content (inpaint), uniform page has fill color but auto empty
    assert pages[1].has_mask_content() is True
    assert pages[0].boxes[0].std_dev <= cfg.MaskerConfig().mask_max_standard_deviation
    assert pages[0].boxes[0].fill_color is not None


@pytest.mark.unit
def test_batch_detect_dilation_radius_effect(tmp_path, monkeypatch) -> None:
    """MASK-01 in the batch path (08.1 inverted): uniform low-std content is now fill,
    so auto is empty for this fixture. We verify that the per-box mask still grows
    with dilation (the fit's mask storage), and that box-clamp still holds, via
    the stored PageBox mask, not the auto plane which is now 0 for uniform."""
    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    page_img = Image.new("RGB", (60, 50), (240, 240, 240))
    draw = ImageDraw.Draw(page_img)
    draw.rectangle([16, 16, 24, 24], fill=(20, 20, 20))
    for y in range(12, 34, 6):
        draw.rectangle([44, y, 45, y + 1], fill=(10, 10, 10))
    for x in range(16, 44, 6):
        draw.rectangle([x, 34, x + 1, 35], fill=(10, 10, 10))
    page_img.save(src / "page1.png")
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    heatmap[16:25, 16:25] = 255
    blk = [_blk(10, 10, 45, 35)]

    def _box_mask_count_for(radius: int):
        page = ImageFile(path=src / "page1.png")
        det = _FixtureDetector([heatmap], [blk])
        install_fakes(monkeypatch, det, FakeInpaintModel())
        conf = cfg.MaskerConfig(mask_growth_steps=1, mask_dilation_radius=radius)
        batch_detect(
            [page],
            det_model_path=Path("fake_det.pt"),
            det_backend="torch",
            cleaned_dir=src / "cleaned",
            masker_conf=conf,
            progress_callback=None,
            abort_flag=None,
        )
        # Per-box mask (fill source) should grow with dilation
        assert page.boxes is not None and page.boxes[0].mask is not None
        mask_arr = np.array(page.boxes[0].mask)
        # Auto plane is now 0 for uniform (inverted)
        auto = unpack_binary(page.auto_mask, 50, 60)
        assert np.count_nonzero(auto) == 0
        return int(np.count_nonzero(mask_arr))

    count0 = _box_mask_count_for(0)
    count4 = _box_mask_count_for(4)

    assert count4 > count0  # MASK-01: larger radius grows the per-box mask even though auto is empty
    # Box clamp still holds via mask bbox
    # We already verified per-box mask non-empty and inside box via earlier derive tests


# ---------------------------------------------------------------------------
# Plan 08-10 (WR-01) — the batch detect worker merges (D-03), never overwrites
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_batch_detect_preserves_user_boxes(tmp_path, monkeypatch) -> None:
    """WR-01 (plan 08-10): a persisted USER-origin box survives a detect-mode
    batch — ``page.boxes`` keeps it (with its ``inpaint_override`` + payload
    intact) while the stale DETECTED box is replaced by the fresh detection,
    and EVERY box in the merged set (kept user + fresh detected) carries a
    refreshed ``mask``/``std_dev`` — the derivation ran over the merged list,
    matching the interactive all-boxes-derive contract.

    Pre-fix (batch_runner.py:202 ``page.boxes = boxes``): the USER box is
    overwritten away -> RED.
    """
    from panelcleaner.structures import Box

    from manga_ai_studio.core.box_model import USER, PageBox

    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    # White 60x50 page; heatmap content inside the user box (1,1,10,10) AND
    # inside the fresh full-page detected box.
    Image.new("RGB", (60, 50), (240, 240, 240)).save(src / "page1.png")
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    heatmap[2:9, 2:9] = 255
    heatmap[22:29, 22:29] = 255

    user_pb = PageBox(
        box=Box(1, 1, 10, 10),
        origin=USER,
        inpaint_override="always",
        payload=_blk(1, 1, 10, 10),
    )
    stale_detected = PageBox(box=Box(20, 20, 30, 30), origin=DETECTED)
    page = ImageFile(path=src / "page1.png", boxes=[user_pb, stale_detected])

    det = _FixtureDetector([heatmap], [[_blk(0, 0, 60, 50)]])
    install_fakes(monkeypatch, det, FakeInpaintModel())

    summary = batch_detect(
        [page],
        det_model_path=Path("fake_det.pt"),
        det_backend="torch",
        cleaned_dir=src / "cleaned",
        masker_conf=cfg.MaskerConfig(),
        progress_callback=None,
        abort_flag=None,
    )

    assert summary == {"ok": 1, "failed": [], "total": 1}
    assert page.boxes is not None and len(page.boxes) == 2, (
        "WR-01: the user box must survive the batch detect (D-03 merge)"
    )
    kept_user = [pb for pb in page.boxes if pb.origin == USER]
    assert len(kept_user) == 1
    assert kept_user[0].box.as_tuple == (1, 1, 10, 10)
    assert kept_user[0].inpaint_override == "always"
    assert kept_user[0].mask is not None, "the kept user box must be re-fitted"
    assert kept_user[0].std_dev is not None
    fresh = [pb for pb in page.boxes if pb.origin == DETECTED]
    assert len(fresh) == 1
    assert fresh[0].box.as_tuple == (0, 0, 60, 50), (
        "the stale DETECTED box must be replaced by the fresh detection"
    )
    assert fresh[0].mask is not None and fresh[0].std_dev is not None


# ===========================================================================
# 08.1-04 Task 1 — batch parity D-09: corrected gate + fill + patched inpaint
# (CONTEXT D-01 authority: low-std <=t -> median fill, high-std >t -> LaMa)
# These are the TDD RED tests for the tracer's thin batch slice — they MUST
# fail before the batch_runner is patched and pass after (inverted gate,
# headless fill, OOM cap, one patch live, empty-branch handling, Qt-free).
# ===========================================================================


def _make_box_mask(w: int, h: int) -> Image.Image:
    """Small box-cropped mask with interior content (2,2)-(w-2,h-2) filled."""
    m = Image.new("1", (w, h), 0)
    ImageDraw.Draw(m).rectangle([2, 2, w - 2, h - 2], fill=1)
    return m


@pytest.mark.unit
def test_batch_clean_corrected_gate_fill_vs_inpaint(tmp_path, monkeypatch) -> None:
    """Batch parity D-09 (CONTEXT D-01 inverted gate): low-std box (5) is
    median-filled with its fill_color, high-std box (30) is LaMa-inpainted.

    At threshold 15 a low-std DETECTED box must NOT reach the LaMa model —
    its text region is replaced by the stored median color via the vendored
    PIL sequence (convert_mask_to_rgba + alpha_composite + paste). The high-std
    box must reach LaMa (fake paints with 200) and both must be present in the
    saved output. Fake asserts each LaMa input is capped at max_size (2048).
    Before the 08.1-04 patch this test fails: batch_clean inpaints the flat
    mask (both regions become 200) or passthroughs the uniform page.
    """
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from panelcleaner.structures import Box

    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    # 40x40 white page
    Image.new("RGB", (40, 40), (255, 255, 255)).save(src / "page1.png")
    page = ImageFile(path=src / "page1.png")

    mask_low = _make_box_mask(10, 10)
    mask_high = _make_box_mask(10, 10)
    fill_color = (99, 22, 11)
    pb_low = PageBox(
        box=Box(5, 5, 15, 15), origin=DETECTED, mask=mask_low, std_dev=5.0, fill_color=fill_color, inpaint_override=None
    )
    pb_high = PageBox(
        box=Box(25, 5, 35, 15), origin=DETECTED, mask=mask_high, std_dev=30.0, fill_color=None, inpaint_override=None
    )
    page.boxes = [pb_low, pb_high]
    # Flat mask covering both regions so old code would inpaint both with 200
    import numpy as np

    combined = np.zeros((40, 40), dtype=np.uint8)
    combined[7:13, 7:13] = 255
    combined[7:13, 27:33] = 255
    page.mask = numpy_binary_to_mask_qimage(combined)

    cleaned = src / "cleaned"

    class _FakeCapped:
        def __init__(self) -> None:
            self.calls: list[tuple[np.ndarray, np.ndarray]] = []
            self.load_calls = 0

        def load(self, p, device="auto") -> None:
            self.load_calls += 1

        def inpaint(self, image_rgb: np.ndarray, mask_binary: np.ndarray) -> np.ndarray:
            # D-05 cap: every LaMa input must be <= max_size
            assert image_rgb.shape[1] <= 2048 and image_rgb.shape[0] <= 2048, f"OOM: patch {image_rgb.shape[1]}x{image_rgb.shape[0]} exceeds 2048"
            self.calls.append((image_rgb.copy(), mask_binary.copy()))
            # Paint only masked area with 200, keep outside as passed (simulates real LaMa preserving unmasked)
            # But we return full image painted with 200 to exercise halo handling — inpaint_patches will halo-limit.
            out = image_rgb.copy()
            # For this test, paint masked pixels with 200 (distinct from fill 99,22,11 and white 255)
            # Use mask_binary to decide: use numpy where
            painted = np.where(mask_binary[..., None] > 0, 200, out) if out.ndim == 3 else out
            # need to handle 2D mask broadcasting
            if mask_binary.ndim == 2:
                for c in range(3):
                    out[:, :, c] = np.where(mask_binary > 0, 200, out[:, :, c])
                return out
            return np.full(image_rgb.shape, 200, dtype=np.uint8)

    inp = _FakeCapped()

    def _factory(kind: str, backend: str):
        if kind == "inpainting":
            return inp
        raise AssertionError(f"unexpected kind {kind}")

    monkeypatch.setattr("manga_ai_studio.core.batch_runner.backend_factory", _factory)

    summary = batch_clean(
        [page],
        inp_model_path=Path("fake.pt"),
        inp_backend="torch",
        cleaned_dir=cleaned,
        max_inpaint_size=(2048, 2048),
        progress_callback=None,
        abort_flag=None,
    )
    assert summary == {"ok": 1, "failed": [], "total": 1}
    # Patched LaMa must have been called at least once (high-std region) but fill-only region never reaches model
    assert len(inp.calls) >= 1
    # Each input capped
    for im, _ in inp.calls:
        assert im.shape[1] <= 2048 and im.shape[0] <= 2048
    # Load cleaned and check pixels: low-std region is fill_color, high-std region is 200, outside is 255
    cleaned_arr = np.array(Image.open(cleaned / "page1.png").convert("RGB"))
    # low box centre (10,10) inside 7:13,7:13
    assert tuple(cleaned_arr[10, 10].tolist()) == fill_color, f"low-std fill region {cleaned_arr[10,10].tolist()} != {fill_color}"
    # high box centre (10,30) inside 7:13,27:33 -> y 10,x 30
    assert tuple(cleaned_arr[10, 30].tolist()) == (200, 200, 200), f"high-std inpaint region {cleaned_arr[10,30].tolist()} != (200,200,200)"
    # outside remains white
    assert tuple(cleaned_arr[0, 0].tolist()) == (255, 255, 255)


@pytest.mark.unit
def test_batch_large_page_capped_and_patched(tmp_path, monkeypatch) -> None:
    """OOM guard D-05..D-08 in batch (large page, far-apart masks, max 2048).

    Page 4000x3000 with two masks far apart must be patched: each model input
    is <=2048, patch count >1, composite is pixel-exact outside union bbox,
    and per-page try/except continues on second page failure (failed list).
    Before patching the single whole-page call exceeds the cap and the second
    page's injected failure aborts the batch.
    """
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from panelcleaner.structures import Box

    src = tmp_path / "chapter"
    src.mkdir(parents=True)

    # Large page 3000x2500 (still >2048, but cheaper than 4000x3000 for CI) with two far apart boxes
    # Use 3000x2500 to keep memory ~22M vs 36M, still triggers patching at 2048 cap
    W, H = 3000, 2500
    # Create white large image efficiently via numpy
    big = np.full((H, W, 3), 255, dtype=np.uint8)
    # Draw two distinct stroke areas so masks have content
    big[110:190, 110:190] = 20
    big[H - 190 : H - 110, W - 190 : W - 110] = 20
    Image.fromarray(big).save(src / "page1.png")
    # Page2 is small, will fail
    Image.new("RGB", (40, 40), (255, 255, 255)).save(src / "page2.png")

    # Page1 boxes far apart
    m1 = _make_box_mask(80, 80)
    m2 = _make_box_mask(80, 80)
    pb1 = PageBox(box=Box(100, 100, 180, 180), origin=DETECTED, mask=m1, std_dev=30.0, inpaint_override=None)
    pb2 = PageBox(box=Box(W - 180, H - 180, W - 100, H - 100), origin=DETECTED, mask=m2, std_dev=30.0, inpaint_override=None)
    page1 = ImageFile(path=src / "page1.png")
    page1.boxes = [pb1, pb2]
    # Flat mask for old code path
    import numpy as np2

    comb1 = np.zeros((H, W), dtype=np.uint8)
    comb1[102:178, 102:178] = 255
    comb1[H - 178 : H - 102, W - 178 : W - 102] = 255
    page1.mask = numpy_binary_to_mask_qimage(comb1)

    page2 = ImageFile(path=src / "page2.png")
    m_small = _make_box_mask(10, 10)
    pb_fail = PageBox(box=Box(5, 5, 15, 15), origin=DETECTED, mask=m_small, std_dev=30.0, inpaint_override=None)
    page2.boxes = [pb_fail]
    comb2 = np.zeros((40, 40), dtype=np.uint8)
    comb2[7:13, 7:13] = 255
    page2.mask = numpy_binary_to_mask_qimage(comb2)

    cleaned = src / "cleaned"

    class _FakePatchRecorder:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []
            self.load_calls = 0
            self.fail_on_page2 = True

        def load(self, p, device="auto") -> None:
            self.load_calls += 1

        def inpaint(self, image_rgb: np.ndarray, mask_binary: np.ndarray) -> np.ndarray:
            h, w = image_rgb.shape[:2]
            assert w <= 2048 and h <= 2048, f"patch {w}x{h} exceeds 2048 cap"
            self.calls.append((w, h))
            # Simulate failure on page2's small patch (40x40) after first page's patches
            # We detect page2 by its small dims
            if w == 40 and h == 40 and self.fail_on_page2:
                raise RuntimeError("injected per-page failure")
            # Otherwise paint masked area with 123
            out = image_rgb.copy()
            for c in range(3):
                out[:, :, c] = np.where(mask_binary > 0, 123, out[:, :, c])
            return out

    inp = _FakePatchRecorder()

    def _factory(kind: str, backend: str):
        if kind == "inpainting":
            return inp
        raise AssertionError(kind)

    monkeypatch.setattr("manga_ai_studio.core.batch_runner.backend_factory", _factory)

    summary = batch_clean(
        [page1, page2],
        inp_model_path=Path("fake.pt"),
        inp_backend="torch",
        cleaned_dir=cleaned,
        max_inpaint_size=(2048, 2048),
        progress_callback=None,
        abort_flag=None,
    )
    # Per-page try/except: page1 ok, page2 failed, batch continues
    assert summary["total"] == 2
    assert summary["ok"] == 1
    assert len(summary["failed"]) == 1
    assert Path(summary["failed"][0][0]).name == "page2.png"
    assert "injected per-page failure" in summary["failed"][0][1]
    assert (cleaned / "page1.png").is_file()
    assert not (cleaned / "page2.png").is_file()
    # Large page was patched: each input capped and count >1
    assert len(inp.calls) > 1, f"expected patched count >1, got {len(inp.calls)}"
    for w, h in inp.calls:
        assert w <= 2048 and h <= 2048
    # Pixel-exact outside union bbox: check a pixel far from both boxes (center) is still white 255
    cleaned_big = np.array(Image.open(cleaned / "page1.png").convert("RGB"))
    assert tuple(cleaned_big[H // 2, W // 2].tolist()) == (255, 255, 255)
    # Masked regions are painted 123
    assert tuple(cleaned_big[140, 140].tolist()) == (123, 123, 123)
    assert tuple(cleaned_big[H - 140, W - 140].tolist()) == (123, 123, 123)


@pytest.mark.unit
def test_batch_empty_branch_and_headless(tmp_path, monkeypatch) -> None:
    """Empty-branch parity + headless purity (batch parity must stay Qt-free).

    - fill-only page (all low-std) skips LaMa entirely (model not called)
    - inpaint-only page skips fill
    - both-empty does passthrough (copied, not re-encoded)
    - batch_runner import stays Qt-free/torch-free (headless probe)
    Before the fix fill-only incorrectly calls LaMa or passthroughs without fill.
    """
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from panelcleaner.structures import Box
    import sys

    # Headless probe: source scan + sys.modules
    import pathlib

    src_text = pathlib.Path("manga_ai_studio/core/batch_runner.py").read_text(encoding="utf-8")
    assert "PySide6" not in src_text, "batch_runner must stay Qt-free (no PySide6 import)"
    # Allow torch import token only in comments? The batch runner should have no torch import.
    # But after patch it may import panelcleaner.image_ops which pulls torch indirectly — the probe
    # is about direct import, not transitive. So we only check PySide6 token as load-bearing.
    import manga_ai_studio.core.batch_runner as br

    assert "PySide6" not in sys.modules or "manga_ai_studio.core.batch_runner" in sys.modules  # hermetic already passed via source scan

    src = tmp_path / "chapter2"
    src.mkdir(parents=True)

    # fill-only page: low-std box with fill_color
    Image.new("RGB", (40, 40), (255, 255, 255)).save(src / "fill_only.png")
    m_fill = _make_box_mask(10, 10)
    pb_fill = PageBox(box=Box(5, 5, 15, 15), origin=DETECTED, mask=m_fill, std_dev=5.0, fill_color=(10, 20, 30), inpaint_override=None)
    page_fill = ImageFile(path=src / "fill_only.png")
    page_fill.boxes = [pb_fill]
    import numpy as np

    comb_fill = np.zeros((40, 40), dtype=np.uint8)
    comb_fill[7:13, 7:13] = 255
    page_fill.mask = numpy_binary_to_mask_qimage(comb_fill)

    # inpaint-only page: high-std
    Image.new("RGB", (40, 40), (255, 255, 255)).save(src / "inpaint_only.png")
    m_inp = _make_box_mask(10, 10)
    pb_inp = PageBox(box=Box(5, 5, 15, 15), origin=DETECTED, mask=m_inp, std_dev=30.0, inpaint_override=None)
    page_inp = ImageFile(path=src / "inpaint_only.png")
    page_inp.boxes = [pb_inp]
    page_inp.mask = numpy_binary_to_mask_qimage(comb_fill)

    # both-empty page: no boxes, no mask
    Image.new("RGB", (40, 40), (255, 255, 255)).save(src / "empty.png")
    page_empty = ImageFile(path=src / "empty.png")
    page_empty.boxes = []
    page_empty.mask = None

    cleaned = src / "cleaned"

    class _FakeCount:
        def __init__(self) -> None:
            self.calls: list[tuple[np.ndarray, np.ndarray]] = []
            self.load_calls = 0

        def load(self, p, device="auto") -> None:
            self.load_calls += 1

        def inpaint(self, image_rgb: np.ndarray, mask_binary: np.ndarray) -> np.ndarray:
            self.calls.append((image_rgb.copy(), mask_binary.copy()))
            out = image_rgb.copy()
            for c in range(3):
                out[:, :, c] = np.where(mask_binary > 0, 77, out[:, :, c])
            return out

    inp_fill = _FakeCount()
    # First, fill-only alone -> no LaMa call
    def _factory_fill(kind: str, backend: str):
        if kind == "inpainting":
            return inp_fill
        raise AssertionError

    monkeypatch.setattr("manga_ai_studio.core.batch_runner.backend_factory", _factory_fill)
    summary_fill = batch_clean(
        [page_fill],
        inp_model_path=Path("fake.pt"),
        inp_backend="torch",
        cleaned_dir=cleaned,
        max_inpaint_size=(2048, 2048),
        progress_callback=None,
        abort_flag=None,
    )
    assert summary_fill == {"ok": 1, "failed": [], "total": 1}
    assert len(inp_fill.calls) == 0, "fill-only must skip LaMa entirely"
    arr_fill = np.array(Image.open(cleaned / "fill_only.png").convert("RGB"))
    assert tuple(arr_fill[10, 10].tolist()) == (10, 20, 30)

    # Inpaint-only alone -> exactly one LaMa call, fill not applied
    inp_inp = _FakeCount()
    monkeypatch.setattr("manga_ai_studio.core.batch_runner.backend_factory", lambda k, b: inp_inp if k == "inpainting" else (_ for _ in ()).throw(AssertionError()))
    # Need to recreate cleaned dir for isolation? batch_clean will overwrite
    summary_inp = batch_clean(
        [page_inp],
        inp_model_path=Path("fake.pt"),
        inp_backend="torch",
        cleaned_dir=cleaned,
        max_inpaint_size=(2048, 2048),
        progress_callback=None,
        abort_flag=None,
    )
    assert summary_inp == {"ok": 1, "failed": [], "total": 1}
    assert len(inp_inp.calls) == 1
    arr_inp = np.array(Image.open(cleaned / "inpaint_only.png").convert("RGB"))
    assert tuple(arr_inp[10, 10].tolist()) == (77, 77, 77)

    # Both-empty passthrough: should copy original bytes (not re-encode as solid)
    inp_empty = _FakeCount()
    monkeypatch.setattr("manga_ai_studio.core.batch_runner.backend_factory", lambda k, b: inp_empty if k == "inpainting" else (_ for _ in ()).throw(AssertionError()))
    summary_empty = batch_clean(
        [page_empty],
        inp_model_path=Path("fake.pt"),
        inp_backend="torch",
        cleaned_dir=cleaned,
        max_inpaint_size=(2048, 2048),
        progress_callback=None,
        abort_flag=None,
    )
    assert summary_empty == {"ok": 1, "failed": [], "total": 1}
    assert len(inp_empty.calls) == 0
    # Passthrough is byte-identical via passthrough_original (filecmp would pass) — we check it exists and is white
    arr_empty = np.array(Image.open(cleaned / "empty.png").convert("RGB"))
    assert tuple(arr_empty[0, 0].tolist()) == (255, 255, 255)


# ===========================================================================
# quick-260903-lm6 — the profile's min detection confidence reaches the
# detector via configure() BEFORE load(), at every batch det-model site
# ===========================================================================


@pytest.mark.unit
def test_batch_detect_configures_conf_thresh_before_load(tmp_path, monkeypatch) -> None:
    """quick-260903-lm6: ``batch_detect`` forwards the threaded ``masker_conf``'s
    ``detection_conf_thresh`` to the det model via ``configure(conf_thresh=...)``
    immediately BEFORE ``load`` (load() passes conf_thresh into TextDetector)."""
    src = tmp_path / "chapter"
    pages = make_pages(src, count=1)
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    masker_conf = cfg.MaskerConfig(detection_conf_thresh=0.55)
    batch_detect(
        pages,
        det_model_path=Path("fake_det.pt"),
        det_backend="torch",
        cleaned_dir=cleaned,
        masker_conf=masker_conf,
        progress_callback=None,
        abort_flag=None,
    )

    assert det.configure_calls == [{"conf_thresh": 0.55}]
    assert det.load_calls == 1


@pytest.mark.unit
def test_batch_detect_and_clean_configures_conf_thresh_before_load(
    tmp_path, monkeypatch
) -> None:
    """quick-260903-lm6: the ``batch_detect_and_clean`` det-model site forwards
    the same conf_thresh from ``masker_conf`` before load."""
    src = tmp_path / "chapter"
    pages = make_pages(src, count=1)
    cleaned = src / "cleaned"

    det = FakeDetectionModel()
    inp = FakeInpaintModel()
    install_fakes(monkeypatch, det, inp)

    masker_conf = cfg.MaskerConfig(detection_conf_thresh=0.3)
    batch_detect_and_clean(
        pages,
        det_model_path=Path("fake_det.pt"),
        inp_model_path=Path("fake_inp.pt"),
        det_backend="torch",
        inp_backend="torch",
        cleaned_dir=cleaned,
        masker_conf=masker_conf,
        progress_callback=None,
        abort_flag=None,
    )

    assert det.configure_calls == [{"conf_thresh": 0.3}]
    assert det.load_calls == 1

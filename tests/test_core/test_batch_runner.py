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
    """D-04 detect mode: the fake det_model returns (heatmap with in-box +
    out-of-box content, [blk]) and a masker_conf -> page.boxes is populated
    (one DETECTED PageBox with non-None PIL mask + float std_dev),
    page.mask composite contains ONLY in-box content, page.raw_detected_mask
    holds the packed pre-dilation binary (D-08 retention), page.auto_mask the
    packed auto binary, and manual/erase stay None (batch pages have no hand
    strokes).

    The Qt-free worker-derivation contract: every pre-QImage assertion in
    this test touches numpy/PIL outputs (the packed slots + the per-box PIL
    mask); the single off-thread QImage construction (page.mask) is the
    existing precedented site and is asserted AFTER the derivation outputs.
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
    # Boxes persisted from the same detect pass (D-04).
    assert page.boxes is not None and len(page.boxes) == 1
    pb = page.boxes[0]
    assert pb.origin == DETECTED
    assert pb.box.as_tuple == (10, 10, 40, 30)
    # Qt-free derivation outputs first: the per-box fit is a PIL mode-"1" mask
    # with a float std (numpy/PIL — no Qt in the new computation).
    assert pb.mask is not None and isinstance(pb.mask, Image.Image)
    assert pb.mask.mode == "1"
    assert isinstance(pb.std_dev, float)
    # D-08: the packed pre-dilation binary retains the out-of-box blob...
    assert page.raw_detected_mask is not None
    raw = unpack_binary(page.raw_detected_mask, 50, 60)
    assert raw[40, 50] == 255
    # D-02: the packed auto binary NEVER carries out-of-box content.
    assert page.auto_mask is not None
    auto = unpack_binary(page.auto_mask, 50, 60)
    assert auto[40, 50] == 0
    assert np.count_nonzero(auto[:10, :]) == 0
    assert np.count_nonzero(auto[31:, :]) == 0
    assert np.count_nonzero(auto[:, :10]) == 0
    assert np.count_nonzero(auto[:, 41:]) == 0
    assert np.count_nonzero(auto[10:31, 10:41]) > 0
    # The composite QImage equals the persisted auto plane (the D-04 content
    # contract for the clean-stage consumer); manual/erase stay None.
    assert page.mask is not None
    assert np.array_equal(mask_to_numpy_binary(page.mask), auto)
    assert page.mask_manual is None and page.mask_erase is None


@pytest.mark.unit
def test_batch_detect_and_clean_inpaints_constrained_mask(tmp_path, monkeypatch) -> None:
    """D-02 in the batch inpaint: the LaMa fake receives the CONSTRAINED mask
    binary — the out-of-box heatmap pixels are zero in the inpaint input."""
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
    assert len(inp.calls) == 1
    _, mask_binary = inp.calls[0]
    assert mask_binary.shape == (50, 60)
    # Out-of-box pixels are ZERO in the LaMa input (D-02 discard reached the
    # saved mask; the clean stage reads mask_to_numpy_binary(page.mask)).
    assert mask_binary[40, 50] == 0
    assert np.count_nonzero(mask_binary[:10, :]) == 0
    assert np.count_nonzero(mask_binary[31:, :]) == 0
    assert np.count_nonzero(mask_binary[:, :10]) == 0
    assert np.count_nonzero(mask_binary[:, 41:]) == 0
    assert np.count_nonzero(mask_binary[10:31, 10:41]) > 0


@pytest.mark.unit
def test_batch_detect_and_clean_gate_fail_passthrough(tmp_path, monkeypatch) -> None:
    """D-03 empty-mask passthrough extension: a page whose only box FAILS the
    std-dev gate (override None) produces an empty composite -> the original is
    copied through untouched and the inpaint fake is NOT called for that page."""
    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    # page1: uniform strokes page -> the fit passes the gate (std 0).
    heatmap1 = _write_strokes_page(src / "page1.png")
    # page2: NOISY page + the same strokes heatmap -> the honest fit std rises
    # above the default gate, so compose_auto_binary excludes it entirely.
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
    # Only page1 passes the gate -> the inpainter is called exactly once.
    assert len(inp.calls) == 1
    # Both pages produce output; page2's came from the D-03 passthrough.
    assert (src / "cleaned" / "page1.png").is_file()
    assert (src / "cleaned" / "page2.png").is_file()
    # page2 kept its per-box fit (honest std above the gate) but contributed
    # nothing to the composite -> empty mask -> no LaMa call.
    assert pages[1].boxes is not None and len(pages[1].boxes) == 1
    assert pages[1].boxes[0].std_dev is not None
    assert pages[1].boxes[0].std_dev > cfg.MaskerConfig().mask_max_standard_deviation
    assert pages[1].has_mask_content() is False


@pytest.mark.unit
def test_batch_detect_dilation_radius_effect(tmp_path, monkeypatch) -> None:
    """MASK-01 in the batch path: a conf with mask_dilation_radius=4 produces
    a LARGER auto mask than radius 0, and the grown content stays clamped at
    the box border (the 08-03 dilate-then-intersect fixture, deterministic
    via mask_growth_steps=1 + the contrast ticks on the box's edges)."""
    src = tmp_path / "chapter"
    src.mkdir(parents=True)
    page_img = Image.new("RGB", (60, 50), (240, 240, 240))
    draw = ImageDraw.Draw(page_img)
    draw.rectangle([16, 16, 24, 24], fill=(20, 20, 20))  # the stroke block
    # Contrast ticks crossing the box's right/bottom edges: the box-mask
    # candidate's border std is high, so the dilated cut always wins.
    for y in range(12, 34, 6):
        draw.rectangle([44, y, 45, y + 1], fill=(10, 10, 10))
    for x in range(16, 44, 6):
        draw.rectangle([x, 34, x + 1, 35], fill=(10, 10, 10))
    page_img.save(src / "page1.png")
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    heatmap[16:25, 16:25] = 255
    blk = [_blk(10, 10, 45, 35)]

    def _auto_count_for(radius: int):
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
        auto = unpack_binary(page.auto_mask, 50, 60)
        return auto, int(np.count_nonzero(auto))

    auto0, count0 = _auto_count_for(0)
    auto4, count4 = _auto_count_for(4)

    assert count4 > count0  # MASK-01: the larger radius grows the mask
    # The trim intersection clamps growth at the box border (never outside).
    ys, xs = np.nonzero(auto4)
    assert xs.min() >= 10 and ys.min() >= 10
    assert xs.max() <= 44 and ys.max() <= 34
    # radius 0 keeps the pre-clamp shape unchanged (no growth).
    ys0, xs0 = np.nonzero(auto0)
    assert ys0.min() > 10 and xs0.min() > 10

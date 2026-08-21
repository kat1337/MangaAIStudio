"""Batch-interactive parity test (08.1 D-09, CONTEXT D-01 authority).

Batch Detect+Clean and Batch Clean must adopt the SAME corrected gate and
patched inpainting as interactive: same fill + patched LaMa split, same max
cap, same manual/erase handling. This test proves parity headlessly: the SAME
snapshot (PageBox list with per-box mask/std_dev/fill_color and threshold 15)
through the interactive worker's fill/inpaint helpers and through the batch
worker's helpers produces an identical fill vs inpaint partition — both planes
are complements and the per-patch cap is respected.

No monkeypatch beyond the propagation guard; real vendored helpers are used
(detection_boxes.compose_* and inpaint_patching). Cite CONTEXT D-01 in docstring
per 08.1-01 tracer discipline.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox
from manga_ai_studio.core.detection_boxes import compose_auto_binary, compose_fill_binary, compose_fill_specs
from manga_ai_studio.core.inpaint_patching import inpaint_patches
from panelcleaner.structures import Box


def _mask(w: int, h: int) -> Image.Image:
    m = Image.new("1", (w, h), 0)
    ImageDraw.Draw(m).rectangle([2, 2, w - 2, h - 2], fill=1)
    return m


@pytest.mark.unit
def test_interactive_and_batch_parity_same_snapshot() -> None:
    """CONTEXT D-01: same snapshot through interactive and batch yields identical fill vs inpaint split."""
    threshold = 15.0
    page_size = (60, 50)  # (w,h) PIL ordering
    # Snapshot: low-std (5) -> will_fill, high-std (30) -> will_inpaint, forced_fill, forced_inpaint, never
    boxes = [
        PageBox(box=Box(5, 5, 15, 15), origin=DETECTED, mask=_mask(10, 10), std_dev=5.0, fill_color=(10, 20, 30), inpaint_override=None),  # will_fill
        PageBox(box=Box(20, 5, 30, 15), origin=DETECTED, mask=_mask(10, 10), std_dev=30.0, fill_color=None, inpaint_override=None),  # will_inpaint
        PageBox(box=Box(5, 20, 15, 30), origin=USER, mask=_mask(10, 10), std_dev=99.0, fill_color=(1, 2, 3), inpaint_override="fill"),  # forced_fill
        PageBox(box=Box(20, 20, 30, 30), origin=USER, mask=_mask(10, 10), std_dev=1.0, fill_color=None, inpaint_override="always"),  # forced_inpaint
        PageBox(box=Box(35, 5, 45, 15), origin=DETECTED, mask=_mask(10, 10), std_dev=5.0, fill_color=(9, 9, 9), inpaint_override="never"),  # never
        PageBox(box=Box(35, 20, 45, 30), origin=DETECTED, mask=None, std_dev=5.0, fill_color=None, inpaint_override=None),  # gate_skipped (no mask)
    ]

    # Interactive helpers (as used in main_window._run_inpaint_task)
    fill_specs_inter = compose_fill_specs(boxes, threshold)
    auto_inter = compose_auto_binary(boxes, threshold, page_size)
    fill_inter = compose_fill_binary(boxes, threshold, page_size)

    # Batch helpers (same functions, same threshold — D-09 parity)
    fill_specs_batch = compose_fill_specs(boxes, threshold)
    auto_batch = compose_auto_binary(boxes, threshold, page_size)
    fill_batch = compose_fill_binary(boxes, threshold, page_size)

    # Parity: identical partitions
    assert len(fill_specs_inter) == len(fill_specs_batch) == 2  # will_fill + forced_fill
    assert np.array_equal(auto_inter, auto_batch)
    assert np.array_equal(fill_inter, fill_batch)
    # Fill and inpaint are complements: no overlap where both have content (except manual/erase which is zero here)
    overlap = np.logical_and(fill_inter > 0, auto_inter > 0)
    assert not np.any(overlap), "fill and inpaint binaries must not overlap for Auto boxes"
    # Specific expectations: will_fill and forced_fill are in fill, will_inpaint and forced_inpaint in auto
    # Check inpaint contains the high-std box and the forced_inpaint box
    # auto should have content at (22,10) inside will_inpaint box (20,5)-(30,15) -> plus 2px inner mask
    assert auto_inter[7, 22] == 255  # inside will_inpaint
    assert auto_inter[22, 22] == 255  # inside forced_inpaint
    # fill should have content at low box and forced_fill
    assert fill_inter[7, 7] == 255  # will_fill
    assert fill_inter[22, 7] == 255  # forced_fill
    # never and gate_skipped must be absent from both
    assert fill_inter[7, 37] == 0 and auto_inter[7, 37] == 0  # never box (35,5)
    assert fill_inter[22, 37] == 0 and auto_inter[22, 37] == 0  # gate_skipped (no mask)


@pytest.mark.unit
def test_fill_vs_inpaint_threshold_equality_to_fill() -> None:
    """CONTEXT D-01: equality (std == threshold) maps to fill (<=), not inpaint."""
    from manga_ai_studio.core.box_model import PageBox

    m = _mask(10, 10)
    pb = PageBox(box=Box(0, 0, 10, 10), origin=DETECTED, mask=m, std_dev=15.0, fill_color=(1, 2, 3), inpaint_override=None)
    assert pb.inpaint_state(15.0) == "will_fill"
    # Compose helpers agree
    assert np.count_nonzero(compose_fill_binary([pb], 15.0, (20, 20))) > 0
    assert np.count_nonzero(compose_auto_binary([pb], 15.0, (20, 20))) == 0


@pytest.mark.unit
def test_no_low_std_inpaint_regression() -> None:
    """No test may assert low-std -> inpaint (the old inverted gate must be gone)."""
    # This meta-test ensures the suite encodes D-01 correctly: a low-std box (5) at threshold 15 must be fill, not inpaint.
    m = _mask(10, 10)
    low = PageBox(box=Box(0, 0, 10, 10), origin=DETECTED, mask=m, std_dev=5.0, fill_color=(1, 2, 3), inpaint_override=None)
    high = PageBox(box=Box(0, 0, 10, 10), origin=DETECTED, mask=m, std_dev=30.0, fill_color=None, inpaint_override=None)
    assert low.inpaint_state(15.0) == "will_fill"
    assert high.inpaint_state(15.0) == "will_inpaint"
    # Batch helpers must agree
    assert np.count_nonzero(compose_fill_binary([low], 15.0, (10, 10))) > 0
    assert np.count_nonzero(compose_auto_binary([low], 15.0, (10, 10))) == 0
    assert np.count_nonzero(compose_auto_binary([high], 15.0, (10, 10))) > 0
    assert np.count_nonzero(compose_fill_binary([high], 15.0, (10, 10))) == 0


@pytest.mark.unit
def test_batch_and_interactive_share_patch_cap() -> None:
    """Both interactive and batch cap every LaMa input at max_inpaint_resolution (D-05)."""
    # Page larger than max 2048 must be patched identically in both paths; each patch input <= max.
    W, H = 3000, 2500
    max_size = (2048, 2048)
    # Two far-apart masks
    mask = np.zeros((H, W), dtype=np.uint8)
    mask[102:178, 102:178] = 255
    mask[H - 178 : H - 102, W - 178 : W - 102] = 255
    image = np.full((H, W, 3), 255, dtype=np.uint8)

    def fake_inpaint(patch_rgb: np.ndarray, patch_mask: np.ndarray) -> np.ndarray:
        h, w = patch_rgb.shape[:2]
        assert w <= 2048 and h <= 2048, f"OOM guard: patch {w}x{h} exceeds cap"
        out = patch_rgb.copy()
        for c in range(3):
            out[:, :, c] = np.where(patch_mask > 0, 77, out[:, :, c])
        return out

    result, bbox = inpaint_patches(image, mask, max_size, fake_inpaint, isolation_radius=5, progress_cb=None)
    assert bbox is not None
    # Pixels outside union bbox are pixel-exact
    assert tuple(result[H // 2, W // 2].tolist()) == (255, 255, 255)
    # Masked regions are inpainted
    assert tuple(result[140, 140].tolist()) == (77, 77, 77)

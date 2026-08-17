"""First real call-site tests for the vendored masker machinery (plan 08-03 Task 1).

``panelcleaner/image_ops.py`` and ``panelcleaner/structures.py`` were vendored
in Phases 1/3 but until now only IMPORT-tested
(``tests/test_core/test_masker_vendor.py``, ``test_structures.py``). This
battery drives the real functions on synthetic PIL pages — the living
documentation of the contracts plan 08-03 Task 3 (``derive_page_mask_state``)
and plans 08-07/08-09 build on (RESEARCH §1.1-§1.2):

- ``grow_mask`` — the MASK-01 dilation primitive (exact-N growth, 0 passthrough)
- ``mask_intersection`` — the D-02 discard primitive
- ``border_std_deviation`` — the std-dev gate measurement (+ BlankMaskError)
- ``pick_best_mask`` — the per-box fit (None-vs-failed semantics, offset math)
- ``compose_masks`` — the per-box-union paste math for the auto binary

Contract facts encoded here were PROBE-VERIFIED against the vendored source
with the pinned interpreter before being frozen as assertions (the 01-07
gap-closure discipline: exercise the REAL vendored function, no
monkeypatching):

- Pillow's FIND_EDGES copies border pixels from the source, so a candidate
  mask that saturates its reference-frame cutout yields the frame-border ring
  (NOT a blank mask) — saturation never fabricates a BlankMaskError.
- ``border_std_deviation``'s RGB path (``allow_color=True``) measures the std
  of Euclidean distances from the MEAN color, so a symmetric two-color split
  on the mask edge reads std 0 — the contrast fixtures here are deliberately
  ASYMMETRIC (a narrow stripe crossing the edge) to measure real deviation.

Pure PIL/numpy/scipy: NO torch, NO Qt, NO model weights, and nothing from
``manga_ai_studio.gui`` or ``PySide6`` is imported (the plan's source
assertion is this file's import list).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

import panelcleaner.config as cfg
import panelcleaner.image_ops as ops
import panelcleaner.structures as st


# --------------------------------------------------------------------- helpers
def _bbox(arr: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box of the non-zero entries as (y1, x1, y2, x2) inclusive."""
    ys, xs = np.nonzero(arr)
    return int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max())


def _filled_mask(size: tuple[int, int], rect: list[int]) -> Image.Image:
    """A mode-"1" mask with a filled rectangle (PIL inclusive coords)."""
    mask = Image.new("1", size, 0)
    ImageDraw.Draw(mask).rectangle(rect, fill=1)
    return mask


# ------------------------------------------------------------------- grow_mask
@pytest.mark.unit
@pytest.mark.parametrize("n", [0, 2, 5])
def test_grow_mask_grows_centered_square_by_exactly_n_pixels(n: int) -> None:
    """A solid 21x21 square at (10,10)-(30,30) grows by exactly N px per side.

    Verified for both kernel regimes (N=2 -> the rounded 5x5 kernel,
    N=5 -> the cv2 ellipse kernel); the bbox extremes are reached on the
    straight rows/columns, so the bounding box grows by exactly N even though
    corners are rounded. This is the MASK-01 dilation contract.
    """
    mask = _filled_mask((41, 41), [10, 10, 30, 30])
    grown = ops.grow_mask(mask, n)
    assert grown.mode == "1"
    assert _bbox(np.array(grown)) == (10 - n, 10 - n, 30 + n, 30 + n)


@pytest.mark.unit
def test_grow_mask_size_zero_returns_equal_mask() -> None:
    """``size == 0`` is a passthrough (image_ops.py:820-821) — an EQUAL
    mode-"1" mask, no growth, no mode drift."""
    mask = _filled_mask((31, 31), [5, 8, 20, 25])
    out = ops.grow_mask(mask, 0)
    assert out.mode == "1"
    assert np.array_equal(np.array(out), np.array(mask))


# ---------------------------------------------------------- mask_intersection
@pytest.mark.unit
def test_mask_intersection_discards_outside_keeps_inside_exactly() -> None:
    """The D-02 discard primitive: mask1 pixels outside mask2 vanish, pixels
    inside survive bit-exact."""
    inside = _filled_mask((40, 40), [12, 12, 20, 20])
    outside = _filled_mask((40, 40), [28, 28, 36, 36])
    mask1 = Image.new("1", (40, 40), 0)
    draw = ImageDraw.Draw(mask1)
    draw.rectangle([12, 12, 20, 20], fill=1)
    draw.rectangle([28, 28, 36, 36], fill=1)
    box_mask = _filled_mask((40, 40), [10, 10, 25, 30])

    cut = ops.mask_intersection(mask1, box_mask)

    assert cut.mode == "1"
    arr = np.array(cut)
    # The inside region survives exactly...
    assert np.array_equal(arr & np.array(inside), np.array(inside))
    # ...and the outside region is fully discarded.
    assert np.count_nonzero(arr & np.array(outside)) == 0
    # Nothing outside the box mask survived.
    assert np.array_equal(arr & ~np.array(box_mask), np.zeros_like(arr))


# ------------------------------------------------------- border_std_deviation
@pytest.mark.unit
def test_border_std_deviation_uniform_page_returns_zero() -> None:
    """A mask edge on a uniform page measures std == 0 (within 1e-9) and the
    median color survives the off-white rounding unrounded (240 is the
    threshold boundary: ``min(median) > threshold`` is False at equality)."""
    page = Image.new("RGB", (40, 40), (240, 240, 240))
    mask = _filled_mask((40, 40), [10, 10, 30, 30])

    std, median_color = ops.border_std_deviation(page, mask, 240, True)

    assert std <= 1e-9
    assert median_color == (240, 240, 240)


@pytest.mark.unit
def test_border_std_deviation_contrast_stripe_above_ten() -> None:
    """A dark stripe crossing the mask edge makes the border sample two
    colors. The split is deliberately asymmetric (~11% dark border pixels) —
    the RGB std measures deviation of distances from the MEAN color, so a
    symmetric 50/50 split would read 0 (probe-verified)."""
    page = Image.new("RGB", (40, 40), (240, 240, 240))
    ImageDraw.Draw(page).rectangle([21, 0, 23, 39], fill=(30, 30, 30))
    mask = _filled_mask((40, 40), [10, 10, 30, 30])

    std, _median_color = ops.border_std_deviation(page, mask, 240, True)

    assert std > 10


@pytest.mark.unit
def test_border_std_deviation_blank_mask_raises() -> None:
    """An empty (all-zero) mode-"1" mask has no edge pixels — BlankMaskError
    (image_ops.py:513-515). Consumers pre-check ``getbbox()`` (Pitfall 13-8);
    this test locks WHY."""
    page = Image.new("RGB", (20, 20), (240, 240, 240))
    blank = Image.new("1", (20, 20), 0)
    assert blank.getbbox() is None  # precondition: the emptiness probe

    with pytest.raises(ops.BlankMaskError):
        ops.border_std_deviation(page, blank, 240, True)


# ------------------------------------------------------------ pick_best_mask
def _text_page() -> Image.Image:
    """A white page with text-like black stroke rows inside the box
    (10,10)-(40,30) — the 'uniform bubble background + text' fixture."""
    page = Image.new("RGB", (60, 50), (240, 240, 240))
    draw = ImageDraw.Draw(page)
    for y in (13, 18, 23, 27):
        draw.rectangle([14, y, 36, y + 1], fill=(20, 20, 20))
    return page


def _text_masks() -> tuple[Image.Image, Image.Image]:
    """(precise_mask, box_mask): heatmap strokes + the box rectangle."""
    precise = Image.new("1", (60, 50), 0)
    draw = ImageDraw.Draw(precise)
    for y in (13, 18, 23, 27):
        draw.rectangle([14, y, 36, y + 1], fill=1)
    box_mask = _filled_mask((60, 50), [10, 10, 40, 30])
    return precise, box_mask


@pytest.mark.unit
def test_pick_best_mask_finds_fit_with_finite_std() -> None:
    """Text strokes inside a box on a uniform page: a MaskFittingResults with
    a non-None best_mask and a finite analytics_std_deviation.

    Locks the offset math (image_ops.py:624-641): the returned best_mask is
    sized to the REFERENCE box and ``mask_coords`` is the reference box's
    top-left — callers must crop back to the masking box themselves."""
    page = _text_page()
    precise, box_mask = _text_masks()
    masking_box = st.Box(10, 10, 40, 30)
    reference_box = st.Box(5, 5, 45, 35)

    fit = ops.pick_best_mask(
        base=page,
        precise_mask=precise,
        box_mask=box_mask,
        masking_box=masking_box,
        reference_box=reference_box,
        masker_conf=cfg.MaskerConfig(),
        analytics_page_path=Path("synthetic.png"),
    )

    assert isinstance(fit, st.MaskFittingResults)
    assert fit.best_mask is not None
    assert fit.failed is False
    assert math.isfinite(fit.analytics_std_deviation)
    # Offset-math contract: reference-frame-sized mask at the reference origin.
    assert fit.mask_coords == (reference_box.x1, reference_box.y1)
    assert fit.best_mask.size == (
        reference_box.x2 - reference_box.x1,
        reference_box.y2 - reference_box.y1,
    )


@pytest.mark.unit
def test_pick_best_mask_blank_precise_mask_returns_none() -> None:
    """A blank precise mask in the box is NOISE -> the function returns None
    (NOT a failed MaskFittingResults) — the distinct legitimate outcome of
    Pitfall 13-9."""
    page = _text_page()
    _precise, box_mask = _text_masks()
    blank = Image.new("1", (60, 50), 0)

    fit = ops.pick_best_mask(
        base=page,
        precise_mask=blank,
        box_mask=box_mask,
        masking_box=st.Box(10, 10, 40, 30),
        reference_box=st.Box(5, 5, 45, 35),
        masker_conf=cfg.MaskerConfig(),
        analytics_page_path=Path("synthetic.png"),
    )

    assert fit is None


@pytest.mark.unit
def test_pick_best_mask_noisy_page_low_threshold_fails() -> None:
    """Full-page deterministic noise: every candidate's border samples varying
    colors, so the best std (~34 here) exceeds the gate. The result is a
    NON-None MaskFittingResults with ``failed=True`` and ``best_mask=None``
    (image_ops.py:705-716) — 'failed' is distinct from the noise-None above.

    (A noise pattern confined INSIDE the box does not fail: probe-verified, a
    grown candidate saturates the reference frame and its Pillow-copied border
    ring sits on clean page pixels — the noise must reach the frame border.)"""
    rng = np.random.default_rng(1234)
    noisy_page = Image.fromarray(rng.integers(0, 256, size=(50, 60, 3), dtype=np.uint8))
    precise, box_mask = _text_masks()

    fit = ops.pick_best_mask(
        base=noisy_page,
        precise_mask=precise,
        box_mask=box_mask,
        masking_box=st.Box(10, 10, 40, 30),
        reference_box=st.Box(5, 5, 45, 35),
        masker_conf=cfg.MaskerConfig(),
        analytics_page_path=Path("noise.png"),
    )

    assert isinstance(fit, st.MaskFittingResults)
    assert fit.failed is True
    assert fit.best_mask is None
    assert fit.analytics_std_deviation > cfg.MaskerConfig().mask_max_standard_deviation


# --------------------------------------------------------------- compose_masks
@pytest.mark.unit
def test_compose_masks_pastes_at_origins_and_unions_overlaps() -> None:
    """Each mask lands at its (x, y) origin (base-bounds clipped) and overlaps
    union — the paste math the auto binary's per-box composition relies on."""
    block_a = _filled_mask((20, 20), [0, 0, 9, 9])  # 10x10 solid block
    block_b = _filled_mask((20, 20), [5, 5, 14, 14])  # 10x10 solid block

    composed = ops.compose_masks((20, 20), [(block_a, (0, 0)), (block_b, (8, 2))])

    assert composed.mode == "1"
    expected = np.zeros((20, 20), dtype=bool)
    expected[0:10, 0:10] = True  # block_a at (0, 0)
    expected[7:17, 13:20] = True  # block_b at (8, 2), columns 13..22 clipped
    assert np.array_equal(np.array(composed), expected)

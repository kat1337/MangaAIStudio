"""Tests for ``manga_ai_studio/core/detection_boxes.py`` (plan 08-03).

The detection->mask seam core: the headless extraction of the V5 box-build
loop (plan 08-03 Task 2 — ``build_detected_pageboxes``, extracted from
``MainWindow._build_detected_boxes`` Step 2, main_window.py:4085-4121) and
the pure mask-derivation primitives (plan 08-03 Task 3 —
``derive_page_mask_state`` / ``compose_auto_binary`` / ``dilate_auto_mask``,
the vendored masker.py:63-104 call sequence adapted per RESEARCH §1.4).

Both consumers — the GUI seam (plan 08-07) and the batch loop (plan 08-09) —
call THESE functions; nothing here imports Qt, torch, or the GUI (the module
is headless by construction, locked by test below).

Synthetic pages: uniform PIL fill + ImageDraw rectangles for text-like
strokes and contrast ticks; heatmaps as numpy (H, W) uint8 arrays — the exact
shapes the detection worker returns (``_run_detection_task`` -> ``{"mask":
mask_refined, "blocks": blk_list}``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

import panelcleaner.config as cfg
import panelcleaner.structures as st

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox


def _blk(x1, y1, x2, y2):
    """A TextBlock-like fake (any object with a ``.xyxy`` of length 4)."""
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


def _bbox(arr: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box of the non-zero entries as (y1, x1, y2, x2) inclusive."""
    ys, xs = np.nonzero(arr)
    return int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max())


# ===========================================================================
# Task 2 — build_detected_pageboxes (headless extraction of the V5 loop)
# ===========================================================================
@pytest.mark.unit
def test_build_detected_pageboxes_clamps_drops_and_tags_detected() -> None:
    """In-bounds entries pass with int-coerced coords; out-of-bounds entries
    are per-edge clamped to [0, img_w]/[0, img_h]; zero-area survivors of the
    clamp are dropped; every kept box is origin DETECTED with its payload
    preserved untouched (the V5 contract, main_window.py:4085-4121)."""
    from manga_ai_studio.core.detection_boxes import build_detected_pageboxes

    in_bounds = _blk(10.0, 10.0, 40.0, 30.0)  # floats -> int coercion
    out_of_bounds = _blk(-5, 20, 50, 45)  # negative x1, x2 beyond img_w
    inverted = _blk(30, 5, 28, 20)  # x2 < x1 pre-clamp
    zero_area_post_clamp = _blk(48, 10, 55, 30)  # clamps to x1 == x2 == img_w

    result = build_detected_pageboxes(
        [in_bounds, out_of_bounds, inverted, zero_area_post_clamp], 45, 50
    )

    assert [pb.box.as_tuple for pb in result] == [(10, 10, 40, 30), (0, 20, 45, 45)]
    assert all(pb.origin == DETECTED for pb in result)
    assert all(isinstance(pb.box, st.Box) for pb in result)
    # The payload is the TextBlock itself, preserved untouched (Phase 4/5
    # OCR + export consume it).
    assert result[0].payload is in_bounds
    assert result[1].payload is out_of_bounds


@pytest.mark.unit
def test_build_detected_pageboxes_style_follows_default_family() -> None:
    """``default_family=None`` -> style None (the renderer's own defaults
    apply); a family -> a default TextStyle on EVERY kept box (the G-07-3
    contract carried over from the GUI loop)."""
    from manga_ai_studio.core.detection_boxes import build_detected_pageboxes

    blks = [_blk(5, 5, 25, 20), _blk(-10, -10, 0, 0)]  # second clamps to zero area

    no_style = build_detected_pageboxes(blks, 100, 80)
    assert len(no_style) == 1
    assert no_style[0].style is None

    with_style = build_detected_pageboxes(blks, 100, 80, default_family="Arial")
    assert len(with_style) == 1
    assert with_style[0].style is not None
    assert with_style[0].style.font_family == "Arial"


@pytest.mark.unit
def test_detection_boxes_module_is_headless() -> None:
    """Source-level purity lock: the module imports nothing from Qt, torch,
    or the GUI layer — the batch worker (plan 08-09) imports it off-thread."""
    source = Path("manga_ai_studio/core/detection_boxes.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("PySide6", "QtWidgets", "QtCore", "QtGui", "torch", "gui."):
        assert forbidden not in source, f"detection_boxes.py must not reference {forbidden}"

    import subprocess
    import textwrap

    # Runtime proof in a HERMETIC subprocess (order-independent — the suite
    # may have already imported the GUI package into this process): importing
    # the module cold must not pull anything from the GUI layer.
    probe = textwrap.dedent(
        """
        import sys
        import manga_ai_studio.core.detection_boxes
        gui = [m for m in sys.modules if m.startswith("manga_ai_studio.gui")]
        if gui:
            print("GUI modules pulled:", gui, file=sys.stderr)
            raise SystemExit(1)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, f"import pulled GUI modules: {result.stderr}"


# ===========================================================================
# Task 3 — the seam primitives (derive / compose / dilate)
# ===========================================================================
def _uniform_page_with_strokes() -> tuple[np.ndarray, np.ndarray]:
    """(image_rgb, heatmap): a white 60x50 page with text-like strokes inside
    the box (10,10)-(40,30), and a matching heatmap."""
    page = Image.new("RGB", (60, 50), (240, 240, 240))
    draw = ImageDraw.Draw(page)
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    for y in (13, 18, 23, 27):
        draw.rectangle([14, y, 36, y + 1], fill=(20, 20, 20))
        heatmap[y : y + 2, 14:37] = 255
    return np.array(page), heatmap


def _page_bbox(mask_or_arr) -> tuple[int, int, int, int]:
    """Page-coordinate bbox of a stored per-box mode-"1" mask pasted at its
    box origin, or of an auto binary directly (as (y1, x1, y2, x2))."""
    arr = np.asarray(mask_or_arr)
    return _bbox(arr)


@pytest.mark.unit
def test_derive_discards_out_of_box_heatmap_content() -> None:
    """D-02/MASK-05: heatmap content outside the union of all boxes NEVER
    enters the auto binary — it is retained in raw_binary (D-08) but cut away
    before fitting/composition."""
    from manga_ai_studio.core.detection_boxes import derive_page_mask_state

    image_rgb, heatmap = _uniform_page_with_strokes()
    # A detected-text blob OUTSIDE every box (bottom-right corner).
    heatmap[35:45, 45:55] = 255
    boxes = [PageBox(box=st.Box(10, 10, 40, 30), origin=DETECTED)]

    result = derive_page_mask_state(image_rgb, heatmap, boxes, cfg.MaskerConfig(), 0)

    # Retained pre-dilation binary carries the out-of-box blob...
    assert result.raw_binary[40, 50] == 255
    # ...the constrained auto binary never does.
    assert result.auto_binary[40, 50] == 0
    # Auto content lives ONLY inside the box union.
    assert np.count_nonzero(result.auto_binary[0:10, :]) == 0
    assert np.count_nonzero(result.auto_binary[31:, :]) == 0
    assert np.count_nonzero(result.auto_binary[:, 0:10]) == 0
    assert np.count_nonzero(result.auto_binary[:, 41:]) == 0
    assert np.count_nonzero(result.auto_binary[10:31, 10:41]) > 0


@pytest.mark.unit
def test_derive_dilation_grows_but_never_exits_the_box() -> None:
    """MASK-01 via dilate-then-intersect: radius 3 grows the auto content by
    ~3 px on unclamped sides and is CLIPPED exactly at the box border where it
    would exit; radius 0 leaves it unchanged. The stored per-box mask and the
    composed auto binary agree.

    ``mask_growth_steps=1`` makes the winner deterministic: the single growth
    candidate (dilated cut + min_thickness) beats the box-mask candidate,
    whose border crosses the contrast ticks drawn on the box's right/bottom
    edges (probe-verified selection)."""
    from manga_ai_studio.core.detection_boxes import derive_page_mask_state

    page = Image.new("RGB", (60, 50), (240, 240, 240))
    draw = ImageDraw.Draw(page)
    draw.rectangle([16, 16, 24, 24], fill=(20, 20, 20))  # the stroke block
    # Contrast ticks crossing the box's right/bottom edges: the box-mask
    # candidate's border std is high, so it never wins the selection.
    for y in range(12, 34, 6):
        draw.rectangle([44, y, 45, y + 1], fill=(10, 10, 10))
    for x in range(16, 44, 6):
        draw.rectangle([x, 34, x + 1, 35], fill=(10, 10, 10))
    heatmap = np.zeros((50, 60), dtype=np.uint8)
    heatmap[16:25, 16:25] = 255
    boxes = [PageBox(box=st.Box(10, 10, 45, 35), origin=DETECTED)]
    conf = cfg.MaskerConfig(mask_growth_steps=1)

    r0 = derive_page_mask_state(np.array(page), heatmap, boxes, conf, 0)
    r3 = derive_page_mask_state(np.array(page), heatmap, boxes, conf, 3)

    # Radius 0: the stroke grown by min_thickness (4) — unchanged by dilation.
    assert _page_bbox(r0.auto_binary) == (12, 12, 28, 28)
    # Radius 3: +3 px on the unclamped sides (28 -> 31), CLIPPED at the box
    # border on the clamped sides (12 -> 10 == the box edge, never past it).
    assert _page_bbox(r3.auto_binary) == (10, 10, 31, 31)
    # The stored per-box mask agrees with the composition.
    assert boxes[0].mask is not None
    local = _bbox(np.array(boxes[0].mask))
    assert (local[0] + 10, local[1] + 10, local[2] + 10, local[3] + 10) == (10, 10, 31, 31)
    # Dilation applies to detected content only and the pre-dilation binary is
    # returned for retention (D-07/D-08): raw_binary is identical at both radii.
    assert np.array_equal(r0.raw_binary, r3.raw_binary)
    assert np.count_nonzero(r3.raw_binary) == 9 * 9  # the raw stroke, undilated


@pytest.mark.unit
def test_derive_per_box_fits_store_gate_lifted() -> None:
    """Per-box fits: a uniform-region box stores mask+std; a box with no
    heatmap content stores (None, None) — the noise outcome; a textured box
    STILL stores its mask with an honest std ABOVE the threshold (the fit ran
    gate-lifted — P-5: threshold changes never re-fit) and consequently does
    NOT contribute to the auto binary at that threshold."""
    from manga_ai_studio.core.detection_boxes import (
        BoxMaskFit,
        derive_page_mask_state,
    )

    image_rgb, heatmap = _uniform_page_with_strokes()
    box_a = PageBox(box=st.Box(10, 10, 40, 30), origin=DETECTED)  # strokes
    box_b = PageBox(box=st.Box(45, 5, 58, 20), origin=DETECTED)  # no content

    result = derive_page_mask_state(image_rgb, heatmap, [box_a, box_b], cfg.MaskerConfig(), 0)

    assert set(result.fits) == {id(box_a), id(box_b)}
    # Uniform box: stored fit with a finite, gate-passing std.
    assert result.fits[id(box_a)].mask is not None
    assert box_a.mask is not None
    assert box_a.std_dev is not None and np.isfinite(box_a.std_dev)
    assert box_a.std_dev <= cfg.MaskerConfig().mask_max_standard_deviation
    # Empty box: the noise outcome (None, None) — never an exception.
    assert result.fits[id(box_b)] == BoxMaskFit(None, None)
    assert box_b.mask is None and box_b.std_dev is None

    # Textured page: the fit still stores a mask (gate-lifted) with an honest
    # std above the default gate, so the box contributes nothing at threshold.
    rng = np.random.default_rng(1234)
    noisy_rgb = rng.integers(0, 256, size=(50, 60, 3), dtype=np.uint8)
    noisy_box = PageBox(box=st.Box(10, 10, 40, 30), origin=DETECTED)
    noisy = derive_page_mask_state(noisy_rgb, heatmap, [noisy_box], cfg.MaskerConfig(), 0)
    assert noisy.fits[id(noisy_box)].mask is not None
    assert noisy_box.std_dev is not None
    assert noisy_box.std_dev > cfg.MaskerConfig().mask_max_standard_deviation
    assert np.count_nonzero(noisy.auto_binary) == 0  # gate excludes it entirely


@pytest.mark.unit
def test_compose_auto_binary_gate_matrix() -> None:
    """Pure recomposition from STORED per-box masks: Auto+under-threshold
    contributes; "always" contributes regardless of std; "never" and mask-None
    contribute nothing — and raising the threshold admits the above-threshold
    box WITHOUT any re-fitting (the same stored masks recompose differently)."""
    from manga_ai_studio.core.detection_boxes import compose_auto_binary

    def _box(x1, override, std_dev, with_mask=True):
        box = st.Box(x1, 0, x1 + 10, 10)
        pb = PageBox(box=box, origin=DETECTED, std_dev=std_dev, inpaint_override=override)
        if with_mask:
            pb.mask = Image.new("1", (10, 10), 1)  # fully content
        return pb

    boxes = [
        _box(0, None, 5.0),  # auto, under threshold
        _box(10, None, 30.0),  # auto, ABOVE threshold
        _box(20, "always", 30.0),  # forced despite high std
        _box(30, "never", 1.0),  # demoted despite passing gate
        _box(40, None, 1.0, with_mask=False),  # no stored mask
    ]

    at_15 = compose_auto_binary(boxes, threshold=15.0, page_size=(50, 10))
    assert np.count_nonzero(at_15[:, 0:10]) > 0  # auto under threshold
    assert np.count_nonzero(at_15[:, 10:20]) == 0  # above threshold excluded
    assert np.count_nonzero(at_15[:, 20:30]) > 0  # "always" forces
    assert np.count_nonzero(at_15[:, 30:50]) == 0  # "never" + mask-None

    # Threshold change = pure recomposition of the SAME stored masks.
    at_50 = compose_auto_binary(boxes, threshold=50.0, page_size=(50, 10))
    assert np.count_nonzero(at_50[:, 10:20]) > 0  # now admitted, no re-fit


@pytest.mark.unit
def test_derive_zero_boxes_empty_auto_and_dilate_auto_mask() -> None:
    """Boxes-mode with zero boxes discards EVERYTHING (auto binary empty,
    raw heatmap retained); ``dilate_auto_mask`` is the mask-only-mode path —
    plain grow-by-r on the raw binary (D-03 keeps the full heatmap, MASK-01
    still applies)."""
    from manga_ai_studio.core.detection_boxes import (
        derive_page_mask_state,
        dilate_auto_mask,
    )

    image_rgb, heatmap = _uniform_page_with_strokes()

    result = derive_page_mask_state(image_rgb, heatmap, [], cfg.MaskerConfig(), 2)

    assert result.auto_binary.shape == (50, 60)
    assert np.count_nonzero(result.auto_binary) == 0
    assert np.count_nonzero(result.raw_binary) > 0  # D-08 retention intact

    raw = np.zeros((50, 60), dtype=np.uint8)
    raw[20:30, 20:30] = 255
    grown = dilate_auto_mask(raw, 2)
    assert grown.dtype == np.uint8
    assert _bbox(grown) == (18, 18, 31, 31)  # +2 on every side
    assert np.array_equal(dilate_auto_mask(raw, 0), raw)  # radius 0 unchanged


@pytest.mark.unit
def test_derive_fits_user_origin_boxes_identically() -> None:
    """All boxes certify: a USER PageBox over heatmap content is fitted
    identically to a detected one (same union, same fit)."""
    from manga_ai_studio.core.detection_boxes import derive_page_mask_state

    image_rgb, heatmap = _uniform_page_with_strokes()
    user_box = PageBox(box=st.Box(10, 10, 40, 30), origin=USER)

    result = derive_page_mask_state(image_rgb, heatmap, [user_box], cfg.MaskerConfig(), 0)

    assert result.fits[id(user_box)].mask is not None
    assert user_box.mask is not None
    assert user_box.std_dev is not None and np.isfinite(user_box.std_dev)
    assert np.count_nonzero(result.auto_binary) > 0


# ===========================================================================
# Plan 08-10 (WR-01) — the headless D-03 merge for the batch detect path
# ===========================================================================


@pytest.mark.unit
def test_merge_page_boxes_keeps_user_replaces_detected() -> None:
    """WR-01 (plan 08-10): ``merge_page_boxes_for_detect`` applies the
    interactive D-03 replace-detected-keep-user rule headlessly — every
    USER-origin box survives with its payload/style/inpaint_override/geometry
    intact (object identity preserved — the caller's ``derive_page_mask_state``
    mutates the returned list in place), every DETECTED-origin box is replaced
    by the fresh detected list, and the result is ``[kept user boxes] +
    list(fresh_detected)``."""
    from manga_ai_studio.core.detection_boxes import merge_page_boxes_for_detect

    payload = _blk(5, 5, 25, 20)
    user_box = PageBox(
        box=st.Box(1, 1, 10, 10),
        origin=USER,
        inpaint_override="never",
        payload=payload,
    )
    stale_detected = PageBox(box=st.Box(20, 20, 30, 30), origin=DETECTED)
    fresh_detected = [PageBox(box=st.Box(40, 40, 55, 48), origin=DETECTED)]

    merged = merge_page_boxes_for_detect([user_box, stale_detected], fresh_detected)

    assert len(merged) == 2
    # The USER box object itself survives (identity — the derive mutates it).
    assert merged[0] is user_box
    assert merged[0].origin == USER
    assert merged[0].box.as_tuple == (1, 1, 10, 10)
    assert merged[0].inpaint_override == "never"
    assert merged[0].payload is payload
    # The stale DETECTED box is replaced by the fresh detection.
    assert stale_detected not in merged
    assert merged[1].origin == DETECTED
    assert merged[1].box.as_tuple == (40, 40, 55, 48)

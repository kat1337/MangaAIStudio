"""The detection->mask seam core (plan 08-03) — pure, headless, numpy/PIL only.

This module owns the headless half of the Phase 8 detection seam: the exact
extraction of the V5 box-build loop from ``MainWindow._build_detected_boxes``
Step 2 (main_window.py:4085-4121) so that BOTH consumers — the interactive
handler (plan 08-07) and the batch loop (plan 08-09) — share one
implementation (RESEARCH §5.1 pure-function extraction precedent, the 05-08
ExportPage pattern). The interactive handler keeps its D-03/D-04 gate wrapper
and rewires its loop body to call :func:`build_detected_pageboxes` (08-07).

V5 input validation (T-03-06 / T-08-04): model-produced ``blk_list``
coordinates are UNTRUSTED. Every box passes the ``textblock_to_box`` int
coercion, a per-edge clamp to the image rect, and the zero-area drop — no
geometry derived from model output escapes this boundary, and page dims are
validated strictly (a float dim would silently produce float clamps).

Plan 08-03 Task 3 adds the mask-derivation seam primitives
(:func:`derive_page_mask_state`, :func:`compose_auto_binary`,
:func:`dilate_auto_mask`) below — the vendored masker call sequence
(panelcleaner/masker.py:63-104) adapted per RESEARCH §1.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import attrs
import numpy as np
from loguru import logger
from PIL import Image, ImageDraw

import panelcleaner.config as cfg
import panelcleaner.image_ops as ops
import panelcleaner.structures as st

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox, textblock_to_box
from manga_ai_studio.core.text_style import default_style


def build_detected_pageboxes(
    blk_list, img_w: int, img_h: int, default_family: str | None = None
) -> list[PageBox]:
    """Build origin-DETECTED ``PageBox``es from a model ``blk_list`` (V5).

    The exact extraction of the V5 loop from
    ``MainWindow._build_detected_boxes`` Step 2 (main_window.py:4085-4121):

    - per blk: ``textblock_to_box(blk)`` int coercion (the single V5 boundary,
      plan 03-01),
    - per-edge clamp ``min(max(coord, 0), img_w / img_h)`` into a fresh
      vendored ``Box`` (model xyxy is untrusted — T-03-06),
    - drop boxes with ``clamped.x2 <= clamped.x1 or clamped.y2 <= clamped.y1``
      (zero area after clamping),
    - ``PageBox(box=clamped, origin=DETECTED, payload=blk,
      style=default_style(default_family) if default_family else None)``.

    Args:
        blk_list: TextBlock-like objects (each needs a ``.xyxy`` of length 4).
        img_w: Page width in pixels (strict int — T-08-04: dims size the clamp
            bounds; a float would leak float coordinates into the geometry).
        img_h: Page height in pixels (strict int).
        default_family: The saved default font family (G-07-3). ``None`` (or
            empty) -> ``style`` stays ``None`` and the renderer's own
            ``TextStyle()`` defaults apply.

    Returns:
        The valid clamped ``PageBox``es, in ``blk_list`` order.

    Raises:
        ValueError: If ``img_w``/``img_h`` are not ints.
    """
    if not isinstance(img_w, int) or not isinstance(img_h, int):
        raise ValueError(
            f"img_w/img_h must be int, got {type(img_w).__name__}/"
            f"{type(img_h).__name__}"
        )

    detected_pageboxes: list[PageBox] = []
    for blk in blk_list:
        box = textblock_to_box(blk)  # int coercion (plan 03-01, pure)
        clamped = st.Box(
            min(max(box.x1, 0), img_w),
            min(max(box.y1, 0), img_h),
            min(max(box.x2, 0), img_w),
            min(max(box.y2, 0), img_h),
        )
        # V5 drop: non-positive area after clamping -> drop, never trust.
        if clamped.x2 <= clamped.x1 or clamped.y2 <= clamped.y1:
            logger.debug(
                f"dropped zero-area detected box "
                f"({box.as_tuple} -> {clamped.as_tuple} after clamp)"
            )
            continue
        # quick-260903-lm6: normalize the detector confidence. Real confs
        # (0..1) pass through; the -1.0 scattered sentinel and any missing
        # attr normalize to None. The upstream default prob=1 would land as
        # 1.0 under this locked range rule — acceptable; our group_output
        # deviation sites guarantee YOLO and scattered blocks never carry
        # the default.
        raw = getattr(blk, "prob", None)
        confidence = float(raw) if raw is not None and 0.0 <= float(raw) <= 1.0 else None
        # payload = the TextBlock, preserved untouched for OCR + export.
        # origin DETECTED so re-detect can replace it (D-03).
        detected_pageboxes.append(
                PageBox(
                    box=clamped,
                    origin=DETECTED,
                    payload=blk,
                    style=default_style(default_family) if default_family else None,
                    confidence=confidence,
                )
            )
    return detected_pageboxes


def merge_page_boxes_for_detect(
    existing: Sequence[PageBox], fresh_detected: Sequence[PageBox]
) -> list[PageBox]:
    """The headless D-03 merge: keep USER boxes, replace DETECTED ones.

    Plan 08-10 (WR-01): applies the interactive D-03 replace-detected-keep-user
    rule (:func:`MainWindow._build_detected_boxes`, main_window.py:4594-4613)
    headlessly so the batch detect worker (plan 08-09, batch_runner.py) can
    never overwrite a page's persisted USER-origin boxes — including their
    per-box D-15 seam state (``inpaint_override``) and payload/style/geometry.

    Every existing box whose ``origin == USER`` is kept AS-IS (object identity
    preserved — the caller's :func:`derive_page_mask_state` mutates the
    returned list in place, which is the interactive contract; the derive
    refills the D-15 seam fields), every DETECTED-origin box is replaced by
    ``fresh_detected``, and the result is ``[kept user boxes] +
    list(fresh_detected)``. Qt-free by construction (the worker thread imports
    this module — see :func:`build_detected_pageboxes`).

    Args:
        existing: The page's current boxes (``ImageFile.boxes`` — may be None).
        fresh_detected: The boxes just built from the current detect pass.

    Returns:
        The merged list (kept user boxes first, then the fresh detected boxes).
    """
    user_pageboxes = [pb for pb in (existing or []) if pb.origin == USER]
    return user_pageboxes + list(fresh_detected)


# ---------------------------------------------------------------------------
# Plan 08-03 Task 3 — the mask-derivation seam primitives
# ---------------------------------------------------------------------------
# Unlike ``build_detected_pageboxes`` (which reads no pixels), the functions
# below touch image memory and MUTATE the live ``PageBox`` list in place,
# writing the D-15 seam fields (``mask``/``std_dev``). The callers (the 08-07
# interactive handler and the 08-09 batch loop) pass the boxes they already
# own, so ``id(pagebox)`` is the stable ``fits`` key within one
# object-lifetime (the D-10 undo identity convention, box_model.py).

_ANALYTICS_FALLBACK_PATH = Path("<page>")


@dataclass
class BoxMaskFit:
    """The per-box outcome of one gate-lifted fit (plan 08-03, P-5).

    ``mask`` is the box-CROPPED mode-"1" PIL image stored on ``PageBox.mask``
    (the 08-01 storage convention: content = non-zero pixels, so ``getbbox()``
    is the emptiness probe); ``std_dev`` is the HONEST measured border
    standard deviation — the std-dev gate is applied DOWNSTREAM by
    :func:`compose_auto_binary` / ``PageBox.inpaint_state``, never inside the
    fit, so a threshold change never re-fits.

    ``median_color`` is the fit-time median fill color from
    ``MaskFittingResults.median_color`` (off-white rounding baked at
    panelcleaner/image_ops.py:535). Stored at fit time on the fit and on
    ``PageBox.fill_color`` — never recomputed at inpaint time.
    """

    mask: Image.Image | None
    std_dev: float | None
    median_color: tuple[int, int, int] | None = None


@dataclass
class PageMaskDerivation:
    """Output of :func:`derive_page_mask_state`.

    ``raw_binary`` is the PRE-dilation thresholded heatmap binary (D-08
    retention data — re-dilate recomputes the auto plane from it);
    ``auto_binary`` is the box-constrained, gate-composed binary (the exact
    input 08-07 feeds to ``canvas.set_auto_binary``); ``fits`` carries the
    per-box fit outcomes keyed by ``id(pagebox)``.
    """

    raw_binary: np.ndarray
    auto_binary: np.ndarray
    fits: dict[int, BoxMaskFit]


def _uint8_binary_to_pil1(binary: np.ndarray) -> Image.Image:
    """Threshold an (H, W) 0/255 uint8 binary to a mode-"1" PIL mask.

    Pitfall 13-7: the conversion uses an EXPLICIT threshold followed by
    ``convert("1", dither=Image.NONE)`` — a dithered convert would invent
    mask pixels (masker.py:72 pattern).
    """
    arr = np.where(np.asarray(binary) > 0, 255, 0).astype(np.uint8)
    return Image.fromarray(arr).convert("1", dither=Image.NONE)


def _pil1_to_uint8(mask: Image.Image) -> np.ndarray:
    """Convert a mode-"1" PIL mask to an (H, W) 0/255 uint8 binary (the
    pack_binary / canvas.set_auto_binary convention)."""
    return np.where(np.array(mask), np.uint8(255), np.uint8(0)).astype(np.uint8)


def derive_page_mask_state(
    image_rgb: np.ndarray,
    heatmap: np.ndarray,
    boxes: list[PageBox],
    masker_conf: cfg.MaskerConfig,
    dilation_radius: int,
    analytics_page_path: Path | None = None,
) -> PageMaskDerivation:
    """Derive the box-constrained auto binary + per-box fitted masks.

    The vendored masker call sequence (panelcleaner/masker.py:63-104) adapted
    per RESEARCH §1.4 + the D-02/D-07/D-08/MASK-05 constraints — pure
    PIL/numpy (main-thread-safe, no model, no worker):

    1. **Binarize** the heatmap: ``np.where(heatmap > 0, 255, 0)`` ->
       PIL -> ``.convert("1", dither=Image.NONE)`` (Pitfall 13-7). This
       PRE-dilation binary is returned as ``raw_binary`` (D-08 retention).
    2. **Dilate** the detected content by ``dilation_radius`` (MASK-01;
       radius <= 0 no-ops — T-08-01b). Dilation applies to DETECTED content
       only (D-07): the function never sees manual strokes.
    3. Build the **box union** of ALL boxes (user + detected — every box
       certifies) as a mode-"1" PIL mask.
    4. **Dilate-then-intersect** (MASK-05 literal): ``cut =
       mask_intersection(dilated, box_union)`` — auto content can never exit
       a box (D-02 discard + box-border clamp in one step).
    5. **Per-box gate-lifted fit** (P-5 / Q1-Fork-A): ``pick_best_mask``
       with ``mask_max_standard_deviation`` evolved to 1e9, so ``best_mask``
       and the HONEST measured std are ALWAYS stored while the gate is applied
       downstream. A blank mask inside the box (noise, Pitfall 13-9) or a box
       with no detected content (Pitfall 13-8 pre-check: ``cut`` cropped to
       the box has ``getbbox() is None``) stores ``BoxMaskFit(None, None)``.
       The fitted mask, sized to the reference box, is cropped back to the
       masking box (``fit.mask_coords`` origin math at image_ops.py:624-641)
       and stored on ``PageBox.mask`` / ``PageBox.std_dev`` + ``fits``.
    6. **Compose** the auto binary from the CONTRIBUTING boxes via
       :func:`compose_auto_binary` (called, not duplicated) with the honest
       ``masker_conf.mask_max_standard_deviation`` gate.

    Args:
        image_rgb: The page as an (H, W, 3) uint8 RGB array.
        heatmap: The CTD heatmap as an (H, W) uint8 array. Content = any
            non-zero pixel (explicit threshold — T-08-04).
        boxes: The live pageboxes to fit (mutated in place: ``mask``/``std_dev``).
        masker_conf: The active vendored ``MaskerConfig``.
        dilation_radius: The MASK-01 detection-time dilation radius in px.
        analytics_page_path: Optional path only used in the vendored noise
            log line; a safe fallback is used when None.

    Returns:
        The ``PageMaskDerivation`` (raw_binary, auto_binary, fits).

    Raises:
        ValueError: If the heatmap is not an (H, W) array matching
            ``image_rgb``'s first two dims (no allocation sized from
            unvalidated dims — T-08-04).
    """
    image_rgb = np.asarray(image_rgb)
    heatmap = np.asarray(heatmap)
    if heatmap.ndim != 2 or heatmap.shape != image_rgb.shape[:2]:
        raise ValueError(
            f"heatmap shape {heatmap.shape} must match image_rgb dims "
            f"{image_rgb.shape[:2]} (2D)"
        )
    height, width = heatmap.shape
    page_size = (width, height)  # PIL size ordering
    page_pil = Image.fromarray(image_rgb)

    # (1) Binarize + retain the raw (pre-dilation) binary — D-08.
    detected = _uint8_binary_to_pil1(heatmap)
    raw_binary = _pil1_to_uint8(detected)

    # (2) MASK-01 dilation on DETECTED content only (D-07).
    dilated = ops.grow_mask(detected, dilation_radius) if dilation_radius > 0 else detected

    # (3) Union of ALL boxes (user + detected — all boxes certify).
    box_union = Image.new("1", page_size, 0)
    draw = ImageDraw.Draw(box_union)
    for pb in boxes:
        draw.rectangle(pb.box.as_tuple, fill=1)

    # (4) Dilate-then-intersect — D-02 discard + box-border clamp (MASK-05).
    cut = ops.mask_intersection(dilated, box_union)

    # (5) Per-box gate-lifted fits.
    fitting_conf = attrs.evolve(masker_conf, mask_max_standard_deviation=1e9)
    fits: dict[int, BoxMaskFit] = {}
    for pb in boxes:
        fits[id(pb)] = _fit_one_box(
            page_pil,
            cut,
            box_union,
            pb,
            fitting_conf,
            masker_conf,
            page_size,
            analytics_page_path,
        )

    # (6) Compose from the contributing boxes (pure recomposition).
    auto_binary = compose_auto_binary(
        boxes, float(masker_conf.mask_max_standard_deviation), page_size
    )
    return PageMaskDerivation(raw_binary=raw_binary, auto_binary=auto_binary, fits=fits)


def _fit_one_box(
    page_pil: Image.Image,
    cut: Image.Image,
    box_union: Image.Image,
    pb: PageBox,
    fitting_conf: cfg.MaskerConfig,
    masker_conf: cfg.MaskerConfig,
    page_size: tuple[int, int],
    analytics_page_path: Path | None,
) -> BoxMaskFit:
    """Run one gate-lifted fit and store the box-cropped mask + honest std.

    Pitfall 13-8 pre-check: a box the cut does not touch has NO detected
    content — it maps to ``(None, None)`` (the noise outcome), never a
    ``BlankMaskError`` surface from ``border_std_deviation``.
    """
    if cut.crop(pb.box.as_tuple).getbbox() is None:
        pb.mask, pb.std_dev = None, None
        pb.fill_color = None
        return BoxMaskFit(None, None, None)

    reference_box = pb.box.pad(
        masker_conf.mask_growth_step_pixels * masker_conf.mask_growth_steps, page_size
    )
    fit = ops.pick_best_mask(
        base=page_pil,
        precise_mask=cut,
        box_mask=box_union,
        masking_box=pb.box,
        reference_box=reference_box,
        masker_conf=fitting_conf,
        analytics_page_path=analytics_page_path or _ANALYTICS_FALLBACK_PATH,
    )
    if fit is None or fit.best_mask is None:
        # Even on failed fits (std too high), PanelCleaner returns median_color
        # for the best candidate — preserve it as fill source for forced cases.
        median = None
        if fit is not None and getattr(fit, "median_color", None) is not None:
            try:
                median = tuple(int(c) for c in fit.median_color)  # type: ignore[arg-type]
                if len(median) != 3:
                    median = None
            except Exception:
                median = None
        pb.mask, pb.std_dev = None, None
        pb.fill_color = median
        return BoxMaskFit(None, None, median)

    # Crop the reference-frame-sized best_mask back to the masking box
    # (offset math at image_ops.py:624-641 — mask_coords is the reference
    # top-left, so translate pb.box into reference coordinates).
    box_in_reference = st.Box(
        pb.box.x1 - reference_box.x1,
        pb.box.y1 - reference_box.y1,
        pb.box.x2 - reference_box.x1,
        pb.box.y2 - reference_box.y1,
    )
    box_mask = ops.cut_out_mask(fit.best_mask, box_in_reference)
    std_dev = float(fit.analytics_std_deviation)
    median_color = None
    if getattr(fit, "median_color", None) is not None:
        try:
            median_color = tuple(int(c) for c in fit.median_color)  # type: ignore[arg-type]
            if len(median_color) != 3:
                median_color = None
        except Exception:
            median_color = None
    pb.mask, pb.std_dev = box_mask, std_dev
    pb.fill_color = median_color
    return BoxMaskFit(box_mask, std_dev, median_color)


def compose_auto_binary(
    boxes: list[PageBox], threshold: float, page_size: tuple[int, int]
) -> np.ndarray:
    """Recompose the auto binary purely from the STORED per-box masks.

    Inverted per 08.1 D-01: the std-dev gate now routes uniform (low-std)
    boxes to the FILL plane and complex (high-std) boxes to INPAINT. So
    auto now means "will_inpaint" (std > threshold) not "will_fill".

    The gate/override logic (this is exactly what threshold changes and
    override flips call — NO fitting ever happens here):

    - ``inpaint_override == "always"`` contributes regardless of std_dev (forced_inpaint),
    - ``inpaint_override == "fill"`` never contributes to auto (it is fill-only),
    - ``inpaint_override == "never"`` contributes to NEITHER plane,
    - ``inpaint_override is None`` (Auto) contributes if ``std_dev`` is not
      None AND ``std_dev > threshold`` AND the stored mask has content,
    - any box with ``mask`` None (or an empty mask) contributes nothing.

    Args:
        boxes: The pageboxes (their ``mask``/``std_dev``/``inpaint_override``
            must already be populated by a fit / user state).
        threshold: The current std-dev gate (``mask_max_standard_deviation``).
        page_size: The page size as ``(w, h)`` (PIL ordering).

    Returns:
        The auto inpaint binary as an ``(H, W)`` 0/255 uint8 array.
    """
    contributing: list[PageBox] = []
    for pb in boxes:
        if pb.inpaint_override == "never":
            continue
        if pb.inpaint_override == "fill":
            continue
        # quick-260904-wn0: the emptiness + fit-freshness predicate lives in
        # ONE place — PageBox._has_auto_mask_content (intentional cross-module
        # use within manga_ai_studio.core) — so a resize-stale mask can never
        # be composed at the current box origin.
        if not pb._has_auto_mask_content():
            continue
        if pb.inpaint_override == "always":
            contributing.append(pb)
        elif pb.inpaint_override is None and pb.std_dev is not None and pb.std_dev > threshold:
            contributing.append(pb)
    composed = ops.compose_masks(
        tuple(page_size), [(pb.mask, (pb.box.x1, pb.box.y1)) for pb in contributing]
    )
    return _pil1_to_uint8(composed)


def compose_fill_binary(
    boxes: list[PageBox], threshold: float, page_size: tuple[int, int]
) -> np.ndarray:
    """Recompose the FILL binary purely from the STORED per-box masks (08.1 D-01).

    Complement of :func:`compose_auto_binary` for the median-color fill pass:
    - ``inpaint_override == "fill"`` contributes regardless of std_dev (forced_fill),
    - ``inpaint_override == "always"`` never contributes to fill (it is inpaint-only),
    - ``inpaint_override == "never"`` contributes to NEITHER plane,
    - ``inpaint_override is None`` (Auto) contributes if ``std_dev`` is not
      None AND ``std_dev <= threshold`` AND the stored mask has content,
    - empty masks excluded.

    Returns:
        The fill binary as an ``(H, W)`` 0/255 uint8 array.
    """
    contributing: list[PageBox] = []
    for pb in boxes:
        if pb.inpaint_override == "never":
            continue
        if pb.inpaint_override == "always":
            continue
        # quick-260904-wn0: same single-site predicate — resize-stale masks
        # never reach the fill binary either.
        if not pb._has_auto_mask_content():
            continue
        if pb.inpaint_override == "fill":
            contributing.append(pb)
        elif pb.inpaint_override is None and pb.std_dev is not None and pb.std_dev <= threshold:
            contributing.append(pb)
    composed = ops.compose_masks(
        tuple(page_size), [(pb.mask, (pb.box.x1, pb.box.y1)) for pb in contributing]
    )
    return _pil1_to_uint8(composed)


def compose_fill_specs(
    boxes: list[PageBox], threshold: float
) -> list[tuple[Image.Image, tuple[int, int, int], tuple[int, int]]]:
    """Return per-box fill specs (mask, color, (x,y)) for the fill pass.

    Same gate as :func:`compose_fill_binary` but returns the list consumed by
    the worker's PIL ``convert_mask_to_rgba`` → ``alpha_composite`` → ``paste``
    sequence (panelcleaner/masker.py:104,138 pattern). Boxes without a
    ``fill_color`` are skipped (they have no proven color to fill with).
    """
    specs: list[tuple[Image.Image, tuple[int, int, int], tuple[int, int]]] = []
    for pb in boxes:
        if pb.inpaint_override == "never" or pb.inpaint_override == "always":
            continue
        # quick-260904-wn0: same single-site predicate — a resized box's
        # stale fit-time mask must not be returned as a fill spec at the
        # CURRENT box origin (the flat median-color corner-fill bug).
        if not pb._has_auto_mask_content():
            continue
        is_fill = False
        if pb.inpaint_override == "fill":
            is_fill = True
        elif pb.inpaint_override is None and pb.std_dev is not None and pb.std_dev <= threshold:
            is_fill = True
        if not is_fill:
            continue
        if pb.fill_color is None:
            continue
        specs.append((pb.mask, pb.fill_color, (pb.box.x1, pb.box.y1)))
    return specs


def dilate_auto_mask(raw_binary: np.ndarray, radius: int) -> np.ndarray:
    """The mask-only-mode path (D-03): dilate the FULL raw binary by radius.

    Detect Boxes mode OFF keeps the full heatmap as the auto layer (no box
    constraint — the function never sees boxes), but MASK-01 still applies:
    the conservative CTD heatmap's letter edges get the dilation. Radius <= 0
    returns the input unchanged (T-08-01b).
    """
    detected = _uint8_binary_to_pil1(raw_binary)
    if radius > 0:
        detected = ops.grow_mask(detected, radius)
    return _pil1_to_uint8(detected)

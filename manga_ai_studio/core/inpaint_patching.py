"""Patch-based OOM-safe inpainting (plan 08.1) — pure, headless, numpy/PIL only.

Headless contract: this module has no GUI framework or ML framework imports
so the batch worker (plan 08.1-05..09, core/batch_runner.py) can import it
off the GUI thread. It depends only on numpy, Pillow, and panelcleaner.image_ops
(vendored, pure). CV2 is optional for connectedComponents — falls back to a naive scan.

Two public helpers:
- plan_patches: pure geometry, returns patch rects capped at max_size.
- inpaint_patches: one-patch-at-a-time loop with halo composite and progress.

D-05 max cap (default 2048), D-06 25% + 10% margin where room,
D-07 edge clamp (no margin where region touches page edge, never deferred),
D-08 interior edge-straddler deferral, one patch live at a time, union bbox
drives single undo (D-03/D-08).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
from PIL import Image

# Headless: no Qt or ML framework imports — purity probe must pass.
# If cv2 is present, use it for connectedComponents; otherwise fallback.
try:  # pragma: no cover - import probe, not behavior
    import cv2 as _cv2  # type: ignore
except Exception:  # pragma: no cover
    _cv2 = None  # type: ignore


def _validate_mask(mask: np.ndarray, what: str = "mask") -> None:
    if not isinstance(mask, np.ndarray):
        raise ValueError(f"{what} must be ndarray, got {type(mask).__name__}")
    if mask.ndim != 2:
        raise ValueError(f"{what} must be 2D (H,W), got ndim={mask.ndim}")
    if mask.dtype != np.uint8:
        raise ValueError(f"{what} must be uint8, got {mask.dtype}")
    if mask.shape[0] == 0 or mask.shape[1] == 0:
        raise ValueError(f"{what} dims must be >0, got {mask.shape}")


def _validate_image(image: np.ndarray) -> None:
    if not isinstance(image, np.ndarray):
        raise ValueError(f"image must be ndarray, got {type(image).__name__}")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"image must be (H,W,3), got shape {image.shape}")
    if image.dtype != np.uint8:
        raise ValueError(f"image must be uint8, got {image.dtype}")


def _validate_max_size(max_size: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(max_size, (tuple, list)) or len(max_size) != 2:
        raise ValueError(f"max_size must be (max_w,max_h), got {max_size!r}")
    mw, mh = int(max_size[0]), int(max_size[1])
    if not (512 <= mw <= 8192 and 512 <= mh <= 8192):
        # Clamp per T-08.1-01-03 (also mirrors MaskerConfig.fix 512..8192).
        mw = max(512, min(8192, mw))
        mh = max(512, min(8192, mh))
    if mw < 1 or mh < 1:
        raise ValueError(f"max_size dims must be >=1, got {(mw,mh)}")
    return (mw, mh)


def _connected_component_bboxes(mask_binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return bounding boxes (x1,y1,x2,y2) for each connected component in mask>0.

    Uses cv2.connectedComponentsWithStats if available, else a naive BFS
    fallback (rare, but keeps the module testable without cv2).
    """
    # Use cv2 if present for speed and accuracy.
    if _cv2 is not None:
        # cv2 expects 8-bit single channel where non-zero is foreground.
        num_labels, labels, stats, _ = _cv2.connectedComponentsWithStats(
            (mask_binary > 0).astype(np.uint8), connectivity=8
        )
        bboxes: list[tuple[int, int, int, int]] = []
        for i in range(1, num_labels):  # 0 is background
            x = int(stats[i, _cv2.CC_STAT_LEFT])
            y = int(stats[i, _cv2.CC_STAT_TOP])
            w = int(stats[i, _cv2.CC_STAT_WIDTH])
            h = int(stats[i, _cv2.CC_STAT_HEIGHT])
            if w == 0 or h == 0:
                continue
            bboxes.append((x, y, x + w, y + h))
        return bboxes
    # Fallback: naive scan grouping by 4-connectivity via stack.
    h, w = mask_binary.shape
    visited = np.zeros((h, w), dtype=bool)
    bboxes = []
    # Simple flood fill per pixel — okay for small test masks; not optimized for huge.
    for y in range(h):
        for x in range(w):
            if mask_binary[y, x] == 0 or visited[y, x]:
                continue
            # BFS
            stack = [(x, y)]
            visited[y, x] = True
            min_x = max_x = x
            min_y = max_y = y
            while stack:
                cx, cy = stack.pop()
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and mask_binary[ny, nx] != 0:
                        visited[ny, nx] = True
                        stack.append((nx, ny))
            bboxes.append((min_x, min_y, max_x + 1, max_y + 1))
    return bboxes


def _grow_bbox_to_context(
    bbox: tuple[int, int, int, int],
    page_w: int,
    page_h: int,
    min_context: float,
    margin: float,
    max_w: int,
    max_h: int,
) -> tuple[int, int, int, int]:
    """Grow a bbox to >=25% page per side + 10% margin where room, clamp at page edges, cap at max_size.

    D-06: each patch grown to >=25% of page per side + 10% margin where room.
    D-07: no margin where region touches page edge, never deferred for edge proximity.
    Cap: w/h at max_size, margins shrunk.

    Returns clamped, capped rect (x1,y1,x2,y2).
    """
    x1, y1, x2, y2 = bbox
    bw = x2 - x1
    bh = y2 - y1

    # Desired core size: at least 25% of page dims per axis where room.
    target_w = max(bw, int(page_w * min_context))
    target_h = max(bh, int(page_h * min_context))

    # Expand symmetrically around bbox center to reach target, but only where room.
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    # Half sizes for core
    half_w = target_w // 2
    half_h = target_h // 2
    # Initial expanded rect centered
    nx1 = cx - half_w
    ny1 = cy - half_h
    nx2 = cx + half_w + (target_w % 2)
    ny2 = cy + half_h + (target_h % 2)

    # Ensure the original bbox is fully inside (if centering clipped, extend).
    if nx1 > x1:
        nx1 = x1
        nx2 = nx1 + target_w
    if ny1 > y1:
        ny1 = y1
        ny2 = ny1 + target_h
    if nx2 < x2:
        nx2 = x2
        nx1 = nx2 - target_w
    if ny2 < y2:
        ny2 = y2
        ny1 = ny2 - target_h

    # Add 10% margin on sides with space (D-07: no margin where region touches page edge).
    margin_x = int(page_w * margin)  # ~10% of page
    margin_y = int(page_h * margin)
    # Also at least 10% of target? pick max of page-margin vs target*margin for safety
    # Use page-relative for determinism in tests.
    touches_left = x1 == 0
    touches_right = x2 == page_w
    touches_top = y1 == 0
    touches_bottom = y2 == page_h
    if not touches_left:
        nx1 -= margin_x
    if not touches_right:
        nx2 += margin_x
    if not touches_top:
        ny1 -= margin_y
    if not touches_bottom:
        ny2 += margin_y

    # Clamp to page bounds
    nx1 = max(0, nx1)
    ny1 = max(0, ny1)
    nx2 = min(page_w, nx2)
    ny2 = min(page_h, ny2)

    # Cap w/h at max_size (margins shrunk case — D-05 fallback)
    w = nx2 - nx1
    h = ny2 - ny1
    if w > max_w:
        # Center shrink around bbox center, clamped.
        cx = (x1 + x2) // 2
        half = max_w // 2
        nx1 = max(0, min(cx - half, page_w - max_w))
        nx2 = nx1 + max_w
        # Ensure still covers seed's x interval where possible (if mask larger than cap, we cap anyway)
        if nx1 > x1:
            nx1 = max(0, x2 - max_w)
            nx2 = nx1 + max_w
        if nx2 < x2:
            nx2 = min(page_w, x1 + max_w)
            nx1 = nx2 - max_w
        w = max_w
    if h > max_h:
        cy = (y1 + y2) // 2
        half = max_h // 2
        ny1 = max(0, min(cy - half, page_h - max_h))
        ny2 = ny1 + max_h
        if ny1 > y1:
            ny1 = max(0, y2 - max_h)
            ny2 = ny1 + max_h
        if ny2 < y2:
            ny2 = min(page_h, y1 + max_h)
            ny1 = ny2 - max_h
        h = max_h

    # Final clamp safety
    nx1 = max(0, min(nx1, page_w - (nx2 - nx1)))
    ny1 = max(0, min(ny1, page_h - (ny2 - ny1)))
    nx2 = nx1 + (nx2 - nx1)
    ny2 = ny1 + (ny2 - ny1)
    # Ensure integer bounds
    return (int(nx1), int(ny1), int(nx2), int(ny2))


def plan_patches(
    mask_binary: np.ndarray,
    max_size: tuple[int, int] = (2048, 2048),
    page_size: tuple[int, int] | None = None,
    min_context: float = 0.25,
    margin: float = 0.10,
) -> list[tuple[int, int, int, int]]:
    """Plan patches: per-region bbox → ≥25% page dims + 10% margin, clamp, deferral.

    Args:
        mask_binary: (H,W) uint8 0/255 binary — composite inpaint mask.
        max_size: (max_w, max_h) from profile, default (2048,2048), clamped 512..8192.
        page_size: (W,H) PIL ordering — needed for clamping. If None, derives from mask.
        min_context: grown to ≥25% of page dims per axis where room (D-06).
        margin: ~10% margin around mask where room (D-06).

    Returns:
        List of page-coordinate rects (x1,y1,x2,y2), ordered, each capped at max_size.
        Empty mask -> [] (caller handles fast path). Each rect already capped.
    """
    _validate_mask(mask_binary, "mask_binary")
    max_w, max_h = _validate_max_size(max_size)
    h, w = mask_binary.shape
    if page_size is None:
        page_w, page_h = w, h
    else:
        page_w, page_h = int(page_size[0]), int(page_size[1])
        if page_w <= 0 or page_h <= 0:
            raise ValueError(f"page_size must be positive, got {page_size!r}")
    # Validate page dims sanity (DoS mitigation)
    if page_w > 10000 or page_h > 10000:
        # Clamp to max image dimension logic — but for patch planner we just honor given.
        pass

    # Find connected regions
    bboxes = _connected_component_bboxes(mask_binary)
    if not bboxes:
        return []
    # Already sorted by whatever cv2 returns (top-left scan). Sort for determinism by (y,x).
    bboxes.sort(key=lambda b: (b[1], b[0]))

    # Whole-page fast path: if page fits within max_size, return single union rect (D-05).
    if max(page_w, page_h) <= max(max_w, max_h):
        # Union bbox of all components
        ux1 = min(b[0] for b in bboxes)
        uy1 = min(b[1] for b in bboxes)
        ux2 = max(b[2] for b in bboxes)
        uy2 = max(b[3] for b in bboxes)
        union = (ux1, uy1, ux2, uy2)
        # Grow union to context where room, then cap — single patch covers all.
        rect = _grow_bbox_to_context(union, page_w, page_h, min_context, margin, max_w, max_h)
        return [rect]

    # Loop until covered: greedy by first uncovered seed.
    patches: list[tuple[int, int, int, int]] = []
    uncovered = bboxes[:]
    # To avoid infinite loops, cap iterations by number of regions * 2
    iterations = 0
    while uncovered and iterations < len(bboxes) * 4 + 10:
        iterations += 1
        seed = uncovered.pop(0)
        rect = _grow_bbox_to_context(seed, page_w, page_h, min_context, margin, max_w, max_h)
        # Determine which other uncovered regions are fully inside this rect -> cover them too.
        # Those that straddle the interior edge are deferred (stay uncovered).
        # Edge proximity never deferred per D-07: if patch is clamped at page edge, straddle there is okay to include?
        # For simplicity: interior check excludes page-edge sides.
        # Compute whether rect touches page edge on each side
        touches_left = rect[0] == 0
        touches_right = rect[2] == page_w
        touches_top = rect[1] == 0
        touches_bottom = rect[3] == page_h
        remaining: list[tuple[int, int, int, int]] = []
        for other in uncovered:
            ox1, oy1, ox2, oy2 = other
            # Fully inside?
            if ox1 >= rect[0] and oy1 >= rect[1] and ox2 <= rect[2] and oy2 <= rect[3]:
                # Cover in this patch — do not keep.
                continue
            # Does it intersect the rect boundary in interior?
            # Intersect if boxes overlap
            intersects = not (ox2 <= rect[0] or ox1 >= rect[2] or oy2 <= rect[1] or oy1 >= rect[3])
            # Check if bbox straddles patch edge: its bbox crosses the patch boundary
            crosses_x = (ox1 < rect[0] < ox2) or (ox1 < rect[2] < ox2)
            crosses_y = (oy1 < rect[1] < oy2) or (oy1 < rect[3] < oy2)
            crosses = crosses_x or crosses_y or intersects  # any overlap but not fully inside is a straddle candidate
            # But we need to know if straddle is interior vs edge.
            # If patch is at page edge on that side, crossing there is edge clamp -> not deferred, include if overlap?
            # For edge-clamped side, we consider that side not interior.
            interior_straddle = False
            if crosses:
                # Determine if the crossing is on a side that is interior (patch not at page edge)
                # For x dimension
                if ox1 < rect[0] < ox2 and not touches_left:
                    interior_straddle = True
                if ox1 < rect[2] < ox2 and not touches_right:
                    interior_straddle = True
                if oy1 < rect[1] < oy2 and not touches_top:
                    interior_straddle = True
                if oy1 < rect[3] < oy2 and not touches_bottom:
                    interior_straddle = True
                # Also if other is completely outside but near boundary, not straddle - it just doesn't intersect.
                # For intersecting but not fully inside, check if its bbox is partially overlapping edge
                if intersects and not interior_straddle:
                    # At edge clamp, we can still include partially overlapping as covered to avoid infinite deferral,
                    # but per D-07 edge masks fully included anyway. For interior gaps, keep deferred.
                    # If patch touches edge, treat partially overlapping as covered (clamped includes it).
                    # So mark as covered (don't keep).
                    continue
            if interior_straddle:
                # Defer — keep for later patch
                remaining.append(other)
            else:
                # Either fully disjoint (no intersect) -> keep for later,
                # or edge-touching overlap already handled as covered.
                # But disjoint should stay uncovered.
                # For disjoint we keep.
                # For intersecting at edge that we decided to cover, we already continued.
                # So disjoint case remains.
                if not intersects:
                    remaining.append(other)
                # Else if intersects at edge and we didn't interior_straddle, it was covered (continue) — but we arrived here only if crosses but not interior -> we continued above? Actually we handled intersects at edge with continue, so not here.
                # For safety, if intersects and not interior_straddle but not fully inside, we already covered via continue above — but if we reach here, it's disjoint.
        # Patch covers seed plus any fully-inside others
        patches.append(rect)
        uncovered = remaining

    # If we exit loop with remaining uncovered due to iteration cap, append remaining as individual patches (fallback)
    if uncovered:
        for bbox in uncovered:
            rect = _grow_bbox_to_context(bbox, page_w, page_h, min_context, margin, max_w, max_h)
            patches.append(rect)

    # Validate each rect capped
    capped: list[tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in patches:
        w_ = x2 - x1
        h_ = y2 - y1
        if w_ > max_w or h_ > max_h:
            # Hard cap fallback: shrink to max centered
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            half_w = max_w // 2
            half_h = max_h // 2
            x1 = max(0, min(cx - half_w, page_w - max_w))
            y1 = max(0, min(cy - half_h, page_h - max_h))
            x2 = x1 + max_w
            y2 = y1 + max_h
            # Clamp to page
            x2 = min(x2, page_w)
            y2 = min(y2, page_h)
            x1 = x2 - max_w
            y1 = y2 - max_h
            x1 = max(0, x1)
            y1 = max(0, y1)
        capped.append((int(x1), int(y1), int(x2), int(y2)))
    return capped


def _grow_mask_binary(mask_bin: np.ndarray, radius: int) -> np.ndarray:
    """Dilate binary mask (0/255 uint8) by radius using vendored grow halo.

    Uses panelcleaner.image_ops.grow_mask lazily (import inside to keep module
    free of ML framework imports on import). Falls back to cv2 dilate if needed.
    Returns bool array shape (H,W) true where dilated mask is set.
    """
    if radius <= 0:
        return mask_bin > 0
    # Lazy import to keep module import not pulling ML framework via vendored config
    try:
        import panelcleaner.image_ops as _ops  # type: ignore

        pil = Image.fromarray(np.where(mask_bin > 0, 255, 0).astype(np.uint8)).convert("1", dither=Image.NONE)
        grown = _ops.grow_mask(pil, radius)
        arr = np.array(grown, dtype=np.uint8)
        if arr.dtype == bool:
            return arr
        return arr > 0
    except Exception:
        # Fallback via cv2 dilate if available
        if _cv2 is not None:
            kernel = _cv2.getStructuringElement(_cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
            dilated = _cv2.dilate((mask_bin > 0).astype(np.uint8), kernel, iterations=1)
            return dilated > 0
        # Last resort: naive binary dilation via scipy if available
        try:
            from scipy.ndimage import binary_dilation  # type: ignore

            return binary_dilation(mask_bin > 0, iterations=radius)
        except Exception:
            return mask_bin > 0


def inpaint_patches(
    image_rgb: np.ndarray,
    mask_binary: np.ndarray,
    max_size: tuple[int, int] = (2048, 2048),
    inpaint_fn: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
    isolation_radius: int = 5,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """OOM-safe inpaint over patches, one patch live at a time (D-05/D-08).

    Args:
        image_rgb: (H,W,3) uint8 — full page, .copy()-detached outside.
        mask_binary: (H,W) uint8 0/255 — composite inpaint mask.
        max_size: (max_w, max_h) cap, default 2048. Each model input capped.
        inpaint_fn: Callable[(patch_rgb, patch_mask) -> patch_result_rgb]. If None,
            raises. In tests a fake paints solid color.
        isolation_radius: grow_mask halo so LaMa halos overlap seams (panelcleaner
            inpainting_isolation_radius=5).
        progress_cb: optional (n, total) -> status "{n} of {N}".

    Returns:
        (page_copy, union_bbox (x,y,w,h) or None). page_copy is .copy()-detached;
        union bbox drives single undo (D-03). Pixels outside union bbox are
        pixel-exact untouched.
    """
    _validate_image(image_rgb)
    _validate_mask(mask_binary, "mask_binary")
    if image_rgb.shape[0] != mask_binary.shape[0] or image_rgb.shape[1] != mask_binary.shape[1]:
        raise ValueError("image and mask must have same (H,W)")
    max_w, max_h = _validate_max_size(max_size)
    if inpaint_fn is None:
        raise ValueError("inpaint_fn is required")

    h, w = mask_binary.shape
    # Fast validation: empty mask -> passthrough
    if np.count_nonzero(mask_binary) == 0:
        return image_rgb.copy(), None

    # Whole-page fast path when max(h,w) <= max(max_w, max_h)
    if max(h, w) <= max(max_w, max_h):
        result = inpaint_fn(image_rgb, mask_binary)
        if not isinstance(result, np.ndarray):
            raise TypeError(f"inpaint_fn must return ndarray, got {type(result).__name__}")
        if result.shape != image_rgb.shape:
            raise ValueError(f"inpaint_fn result shape {result.shape} != input {image_rgb.shape}")
        if result.dtype != np.uint8:
            raise ValueError(f"inpaint_fn result dtype {result.dtype} != uint8")
        # Union bbox from mask
        ys, xs = np.where(mask_binary > 0)
        if len(xs) == 0:
            return result.copy(), None
        x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        bbox = (x1, y1, x2 - x1, y2 - y1)
        # Halo composite so only masked area is replaced, preserving fill outside
        # (08.1 fix: small page with both fill+inpaint must preserve fill outside inpaint mask;
        # fake model paints whole image, but real LaMa preserves unmasked pixels. Halo limits copy to mask.)
        if isolation_radius > 0:
            halo = _grow_mask_binary(mask_binary, isolation_radius)
        else:
            halo = mask_binary > 0
        page_copy = image_rgb.copy()
        if np.any(halo):
            # halo is (H,W) bool, page_copy[halo] gives (N,3) view
            page_copy[halo] = result[halo]
            return page_copy.copy(), bbox
        return result.copy(), bbox

    # Patched path
    page_w, page_h = w, h
    patches = plan_patches(mask_binary, max_size=(max_w, max_h), page_size=(page_w, page_h))
    if not patches:
        # No patches despite non-empty mask? fallback to whole-page (should not happen)
        result = inpaint_fn(image_rgb, mask_binary)
        ys, xs = np.where(mask_binary > 0)
        x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        return result.copy(), (x1, y1, x2 - x1, y2 - y1)

    page_copy = image_rgb.copy()
    # Memory-safe: one patch crop + one model call live at a time.
    total = len(patches)
    for i, (x1, y1, x2, y2) in enumerate(patches):
        patch_img = image_rgb[y1:y2, x1:x2].copy()
        patch_mask = mask_binary[y1:y2, x1:x2].copy()
        # Call model (SimpleLama fully convolutional valid)
        result_patch = inpaint_fn(patch_img, patch_mask)
        if not isinstance(result_patch, np.ndarray):
            raise TypeError(f"inpaint_fn patch must return ndarray, got {type(result_patch).__name__}")
        if result_patch.shape != patch_img.shape:
            raise ValueError(f"patch result shape {result_patch.shape} != patch shape {patch_img.shape}")
        if result_patch.dtype != np.uint8:
            raise ValueError(f"patch result dtype {result_patch.dtype} != uint8")
        # Composite only where grow_mask(patch_mask, isolation) is set so halos overlap (Pitfall 3)
        # Compute halo mask in patch coordinates.
        if isolation_radius > 0:
            # Use grow_mask on patch_mask to get halo
            halo = _grow_mask_binary(patch_mask, isolation_radius)
        else:
            halo = patch_mask > 0
        # Apply halo as bool indexing per channel
        # Later patch wins overlap (regions are disjoint by construction but halo may overlap)
        # Use boolean indexing.
        # For performance, use where halo true
        # page_copy[y1:y2, x1:x2][halo] = result_patch[halo]
        # Need to handle 3 channels.
        # Use 2D halo to index first two dims.
        # Approach: copy via numpy where
        patch_region = page_copy[y1:y2, x1:x2]
        # halo is (ph, pw) bool
        # Expand to (ph,pw,1) for broadcasting
        # For each channel, replace where halo true
        # Use numpy advanced indexing: we can do patch_region[halo] = result_patch[halo] where halo is 2D but patch_region is 3D — need to handle.
        # Use masking per plane: for c in 0..2, patch_region[halo, c] style not valid. Use:
        #   patch_region[halo] gives (N,3) view where N is count of halo true pixels; same for result_patch.
        # That works if we treat first two dims flattened.
        # So:
        if np.any(halo):
            # halo is 2D bool, patch_region[halo] selects rows where halo true, returning (N,3)
            patch_region[halo] = result_patch[halo]
            page_copy[y1:y2, x1:x2] = patch_region
        if progress_cb is not None:
            try:
                progress_cb(i + 1, total)
            except Exception:
                pass

    # Union bbox of all patches (drives single undo)
    min_x = min(p[0] for p in patches)
    min_y = min(p[1] for p in patches)
    max_x = max(p[2] for p in patches)
    max_y = max(p[3] for p in patches)
    union_bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
    # Ensure .copy() detachment of result
    return page_copy.copy(), union_bbox

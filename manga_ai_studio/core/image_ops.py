"""Pure pixel + geometry math for page image ops (plan 05-02, PROJ-04).

Per D-10 the Qt EVENT DISPATCH lives in ``gui/canvas.py``; this module holds
only pure functions of ``(numpy arrays, list[PageBox])`` so
``tests/test_core/test_image_ops.py`` can exercise every transform headless —
no QWidget, no display, safe to call from the apply path (plans 05-06/05-07)
and from any worker thread. This module owns ALL pixel and geometry math for
rotate / crop / resize / levels / curves; the GUI owns interaction only.

The mask boundary (D-18): inputs and outputs use the BINARY mask form
``(H, W)`` uint8 (0/255) produced by ``mask_editor.mask_to_numpy_binary`` and
consumed by ``mask_editor.numpy_binary_to_mask_qimage`` — this module never
sees a QImage and never re-implements the mask bridges.

Data invariants (CONTEXT D-15/D-17/D-18; RESEARCH Pitfall 2/3):
- Geometry transforms (rotate/crop/resize) carry the mask AND every box's
  bbox AND ``TextBlock.lines`` quad polygons along with the page image
  (D-15/D-17); levels is geometry-free — pixels only, mask/boxes untouched.
- Every transform returns ``.copy()``-detached arrays (Pitfall 2).
- Every box transform builds a NEW ``PageBox`` with a fresh ``TextBlock``
  and a fresh ``lines`` list; the inputs — the vendored ``@frozen`` ``Box``
  and the caller's ``payload.lines`` — are NEVER mutated (Pitfall 3), so the
  results are safe to push onto the undo stacks (plan 05-04) before the GUI
  applies them.
- Rotation convention (Pitfall 4): ONE convention for image, mask, and
  geometry — ``k=-1`` = 90° CW, ``k=1`` = 90° CCW, ``k=2`` = 180°
  (``np.rot90`` semantics; the box math mirrors it: CW ``(x,y) -> (h-1-y, x)``,
  CCW ``(x,y) -> (y, w-1-x)``, 180 ``(x,y) -> (w-1-x, h-1-y)``).

Security:
    - Every public transform validates its inputs BEFORE any work
      (image_io.py:65-72 discipline): image ``(H,W,3)`` uint8, mask ``(H,W)``
      uint8, matching dims — a malformed or oversized array raises ValueError
      before numpy/PIL allocation (T-05-06 DoS mitigation; page dims are
      additionally capped by ``MAX_IMAGE_DIMENSION`` at load, canvas.py:79).
    - ``levels_lut`` guarantees a monotone non-decreasing LUT even for
      ``white <= black`` (T-05-07) — no inverted map can ever render.
    - No in-place mutation paths exist (T-05-08): every box/line transform
      returns fresh objects; ``test_rotate_transforms_all`` locks the
      originals-untouched contract.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from manga_ai_studio.core.box_model import PageBox
from panelcleaner.comic_text_detector.utils.textblock import TextBlock
from panelcleaner.structures import Box


def _validate_image_mask(image_rgb: np.ndarray, mask_bin: np.ndarray) -> None:
    """Validate the (H,W,3) uint8 image + (H,W) uint8 binary-mask pair.

    Mirrors the input-validation-before-work discipline of
    ``core/image_io.py`` (T-02-01 boundary); every public page transform
    calls this first so malformed/oversized arrays raise ValueError before
    any numpy/PIL allocation (T-05-06).
    """
    if (
        image_rgb.ndim != 3
        or image_rgb.shape[2] != 3
        or image_rgb.dtype != np.uint8
    ):
        raise ValueError("expected (H,W,3) uint8 RGB")
    if mask_bin.ndim != 2 or mask_bin.dtype != np.uint8:
        raise ValueError("expected (H,W) uint8 binary mask")
    if mask_bin.shape[0] != image_rgb.shape[0] or mask_bin.shape[1] != image_rgb.shape[1]:
        raise ValueError("mask and image must have the same (H, W)")


# ---------------------------------------------------------------------------
# Rotation (TRACER op, plan 05-02 Task 1) — D-10 90° steps, D-15/D-17 geometry
# ---------------------------------------------------------------------------


def _rotate_point(x: int, y: int, w: int, h: int, k: int) -> tuple[int, int]:
    """Rotate a single point 90°*k around the ``(w, h)`` page origin (D-10).

    One convention for image, mask, AND geometry (RESEARCH Pitfall 4), derived
    from ``np.rot90`` semantics with the origin at the top-left:
        k=-1 (90° CW):   (h-1-y, x)
        k=1  (90° CCW):  (y, w-1-x)
        k=2  (180°):     (w-1-x, h-1-y)
        else:            identity
    ``w``/``h`` are the PRE-rotation image dims.
    """
    if k == -1:
        return h - 1 - y, x
    if k == 1:
        return y, w - 1 - x
    if k == 2:
        return w - 1 - x, h - 1 - y
    return x, y


def transform_box(box: Box, w: int, h: int, k: int) -> Box:
    """Rotate a ``Box`` bbox by 90°*k and normalize the corner order.

    Rotating an axis-aligned rect maps its corners onto corners of the
    rotated rect; the result is normalized back to ``(min, min, max, max)``
    x/y order. Builds a NEW ``@frozen`` ``Box`` — the input is NEVER mutated
    (D-14 composition discipline; Pitfall 3).
    """
    x1, y1, x2, y2 = box.as_tuple
    nx1, ny1 = _rotate_point(x1, y1, w, h, k)
    nx2, ny2 = _rotate_point(x2, y2, w, h, k)
    return Box(min(nx1, nx2), min(ny1, ny2), max(nx1, nx2), max(ny1, ny2))


def transform_lines(lines: list, w: int, h: int, k: int) -> list:
    """Rotate each ``TextBlock.lines`` quad (4 points) by 90°*k — D-17.

    Returns a NEW list of NEW quads; the input list and its quads are NEVER
    touched in place (Pitfall 3 — no in-place path exists; grepped by the
    plan's acceptance gate). ``None`` lines (a never-examined TextBlock)
    become ``[]``.
    """
    if lines is None:
        return []
    return [
        [list(_rotate_point(px, py, w, h, k)) for px, py in quad] for quad in lines
    ]


def transform_box_payload(pagebox: PageBox, w: int, h: int, k: int) -> PageBox:
    """Rotate one ``PageBox`` into a fresh box + payload (D-15/D-17/D-18).

    The returned ``PageBox`` carries the transformed bbox and, when a payload
    exists, a fresh ``TextBlock`` whose ``xyxy`` matches the new bbox and
    whose ``lines`` are the transformed quads. ``vertical``/``language``/
    ``font_size``/``text``/``translation`` are copied (text may be a str OR a
    list — whichever it is, it is copied, never joined); the Phase 4 peer
    fields ``edited``/``bubble_no``/``manual_override`` ride along unchanged.
    A payload-None box produces a payload-None PageBox with the transformed
    box. The input PageBox and its payload are NEVER mutated — the fresh
    objects are undo-snapshot-safe (Pitfall 3).
    """
    new_box = transform_box(pagebox.box, w, h, k)
    payload = pagebox.payload
    if payload is None:
        return PageBox(box=new_box, origin=pagebox.origin)
    text = payload.text
    if isinstance(text, list):
        text = list(text)
    fresh = TextBlock(
        xyxy=list(new_box.as_tuple),
        lines=transform_lines(payload.lines, w, h, k),
        vertical=payload.vertical,
        language=payload.language,
        font_size=payload.font_size,
        text=text,
        translation=payload.translation,
    )
    return PageBox(
        box=new_box,
        origin=pagebox.origin,
        payload=fresh,
        edited=pagebox.edited,
        bubble_no=pagebox.bubble_no,
        manual_override=pagebox.manual_override,
    )


def rotate_page(
    image_rgb: np.ndarray, mask_bin: np.ndarray, k: int
) -> tuple[np.ndarray, np.ndarray]:
    """Rotate the page image + binary mask by 90°*k — pixel-exact (D-18).

    ``np.rot90`` with the ONE convention (k=-1 CW, 1 CCW, 2 180) on BOTH the
    image and the mask keeps them in the same coordinate frame; the trailing
    ``.copy()`` detaches the results from numpy's rotated views (Pitfall 2).
    Validates ``(H,W,3)`` uint8 / ``(H,W)`` uint8 before the op.
    """
    _validate_image_mask(image_rgb, mask_bin)
    return np.rot90(image_rgb, k=k).copy(), np.rot90(mask_bin, k=k).copy()


def rotate_boxes(boxes: list[PageBox], w: int, h: int, k: int) -> list[PageBox]:
    """Rotate every box (bbox + line quads) by 90°*k — D-15/D-17.

    ``w``/``h`` are the PRE-rotation image dims; each rotated box's quad math
    uses them (matches ``rotate_page``'s coordinate frame).
    """
    return [transform_box_payload(pb, w, h, k) for pb in boxes]


# ---------------------------------------------------------------------------
# Crop (plan 05-02 Task 2) — D-11 exact slice + D-16 drop/clip policy
# ---------------------------------------------------------------------------


def crop_page(
    image_rgb: np.ndarray, mask_bin: np.ndarray, x: int, y: int, w: int, h: int
) -> tuple[np.ndarray, np.ndarray]:
    """Crop the page to ``(x, y, w, h)`` — an exact slice (D-18, Pitfall 2).

    ``x``/``y`` are the crop origin in pre-crop page coordinates; ``w``/``h``
    the crop size. Validates ``(H,W,3)`` uint8 / ``(H,W)`` uint8 and that the
    crop rect is in-range (ints, x/y >= 0, w/h >= 1, fully inside the page)
    BEFORE slicing; ValueError otherwise (image_io.py:65-72 discipline).
    """
    _validate_image_mask(image_rgb, mask_bin)
    for name, value in (("x", x), ("y", y), ("w", w), ("h", h)):
        if not isinstance(value, int):
            raise ValueError(f"crop {name} must be an int, got {type(value).__name__}")
    h_img, w_img = image_rgb.shape[:2]
    if x < 0 or y < 0 or w < 1 or h < 1:
        raise ValueError("crop rect must satisfy x>=0, y>=0, w>=1, h>=1")
    if x + w > w_img or y + h > h_img:
        raise ValueError("crop rect must lie inside the page (H,W) dims")
    return (
        image_rgb[y : y + h, x : x + w].copy(),
        mask_bin[y : y + h, x : x + w].copy(),
    )


def _clip_quad(quad: list, x: int, y: int, w: int, h: int) -> list | None:
    """Clamp a line quad to the crop rect ``[x, x+w] x [y, y+h]`` (D-16).

    Each point's coordinates are clamped to the rect edges — partially
    outside quads CLIP, their points clamp to the new page boundary. If the
    clamped quad is degenerate (zero width or zero height — the quad lies
    fully outside the rect or only touches its edge), ``None`` is returned
    and the caller drops the quad. Never mutates the input quad.
    """
    x2, y2 = x + w, y + h
    clamped = [[max(x, min(x2, px)), max(y, min(y2, py))] for px, py in quad]
    xs = [p[0] for p in clamped]
    ys = [p[1] for p in clamped]
    if max(xs) == min(xs) or max(ys) == min(ys):
        return None
    return clamped


def _clip_box(pagebox: PageBox, x: int, y: int, w: int, h: int) -> PageBox | None:
    """Clip one box (bbox AND line quads) to the crop rect — D-16.

    The bbox is intersected with the crop rect; a zero-area or empty
    intersection (fully outside, or only touching the edge) returns ``None``
    — the caller DROPS the box and counts it. A kept box gets a fresh
    ``PageBox`` (fresh ``@frozen`` ``Box`` + fresh ``TextBlock`` when a
    payload exists) in POST-crop page coordinates: the bbox and every line
    quad are translated by ``(-x, -y)`` and the quads are clamped to
    ``[0, w] x [0, h]``. Line quads that clip to nothing are removed. The
    input PageBox/payload/lines are NEVER mutated (Pitfall 3); the D-15 seam
    (``mask``/``std_dev``) stays ``None``.
    """
    bx1, by1, bx2, by2 = pagebox.box.as_tuple
    nx1 = max(bx1, x)
    ny1 = max(by1, y)
    nx2 = min(bx2, x + w)
    ny2 = min(by2, y + h)
    if nx2 <= nx1 or ny2 <= ny1:
        return None
    # Post-crop page coordinates: translate the intersection by (-x, -y).
    tx1, ty1, tx2, ty2 = nx1 - x, ny1 - y, nx2 - x, ny2 - y
    new_box = Box(tx1, ty1, tx2, ty2)
    payload = pagebox.payload
    if payload is None:
        return PageBox(box=new_box, origin=pagebox.origin)
    new_lines = []
    for quad in payload.lines:
        clipped = _clip_quad(quad, x, y, w, h)
        if clipped is None:
            continue
        new_lines.append(
            [[max(0, min(w, px - x)), max(0, min(h, py - y))] for px, py in clipped]
        )
    text = payload.text
    if isinstance(text, list):
        text = list(text)
    fresh = TextBlock(
        xyxy=list(new_box.as_tuple),
        lines=new_lines,
        vertical=payload.vertical,
        language=payload.language,
        font_size=payload.font_size,
        text=text,
        translation=payload.translation,
    )
    return PageBox(
        box=new_box,
        origin=pagebox.origin,
        payload=fresh,
        edited=pagebox.edited,
        bubble_no=pagebox.bubble_no,
        manual_override=pagebox.manual_override,
    )


def crop_boxes(
    boxes: list[PageBox], x: int, y: int, w: int, h: int
) -> tuple[list[PageBox], int]:
    """Apply the D-16 drop/clip policy to every box.

    Returns ``(kept_boxes, dropped_count)`` — ``dropped_count`` is the number
    of fully-outside boxes removed (reported in the status bar by the GUI
    apply path; RESEARCH Pitfall 10).
    """
    kept: list[PageBox] = []
    dropped = 0
    for pb in boxes:
        clipped = _clip_box(pb, x, y, w, h)
        if clipped is None:
            dropped += 1
        else:
            kept.append(clipped)
    return kept, dropped


def crop_page_with_boxes(
    image_rgb: np.ndarray,
    mask_bin: np.ndarray,
    boxes: list[PageBox],
    x: int,
    y: int,
    w: int,
    h: int,
) -> tuple[np.ndarray, np.ndarray, list[PageBox], int]:
    """The one-call crop apply seam for the GUI (plan 05-07): crop the image
    + mask and apply the D-16 drop/clip policy in one call.

    Returns ``(image_c, mask_c, kept_boxes, dropped_count)``.
    """
    img_c, msk_c = crop_page(image_rgb, mask_bin, x, y, w, h)
    kept, dropped = crop_boxes(boxes, x, y, w, h)
    return img_c, msk_c, kept, dropped


# ---------------------------------------------------------------------------
# Resize (plan 05-02 Task 3) — D-13 dialog range, A8 LANCZOS/NEAREST, D-18
# ---------------------------------------------------------------------------

# Resize dimension bounds (UI-SPEC surface 26: Resize ranges 1..100000).
MIN_RESIZE_DIM = 1
MAX_RESIZE_DIM = 100000


def resize_page(
    image_rgb: np.ndarray, mask_bin: np.ndarray, new_w: int, new_h: int
) -> tuple[np.ndarray, np.ndarray]:
    """Resize the page: image LANCZOS, mask NEAREST — no soft alpha drift
    (D-18, A8). The binary mask stays strictly 0/255 — never interpolated
    grays. Validates ``(H,W,3)``/``(H,W)`` and ``new_w``/``new_h`` ints in
    ``[1, 100000]`` (UI-SPEC surface 26) before any PIL work (T-05-06).
    """
    _validate_image_mask(image_rgb, mask_bin)
    for name, value in (("new_w", new_w), ("new_h", new_h)):
        if not isinstance(value, int):
            raise ValueError(f"resize {name} must be an int, got {type(value).__name__}")
        if not MIN_RESIZE_DIM <= value <= MAX_RESIZE_DIM:
            raise ValueError(
                f"resize {name} must be within [{MIN_RESIZE_DIM}, {MAX_RESIZE_DIM}]"
            )
    img = np.asarray(
        Image.fromarray(image_rgb, "RGB").resize(
            (new_w, new_h), Image.Resampling.LANCZOS
        )
    ).copy()
    msk = np.asarray(
        Image.fromarray(mask_bin, "L").resize(
            (new_w, new_h), Image.Resampling.NEAREST
        )
    ).copy()
    return img, msk


def resize_boxes(
    boxes: list[PageBox], w: int, h: int, new_w: int, new_h: int
) -> list[PageBox]:
    """Scale every box (bbox + line quads) to the new page dims — D-15/D-17.

    Scale factors ``(new_w/w, new_h/h)``; every coordinate is rounded via
    ``int(round(coord * scale))`` (Pitfall 6 int discipline) and the bbox is
    re-normalized. ``w``/``h`` are the PRE-resize image dims. Fresh
    ``PageBox``/``TextBlock`` per box — inputs never mutated (Pitfall 3).
    """
    if not isinstance(w, int) or not isinstance(h, int) or w < 1 or h < 1:
        raise ValueError("resize pre-dims w/h must be positive ints")
    sx = new_w / w
    sy = new_h / h

    def _scale_point(px: int, py: int) -> tuple[int, int]:
        return int(round(px * sx)), int(round(py * sy))

    out: list[PageBox] = []
    for pb in boxes:
        x1, y1, x2, y2 = pb.box.as_tuple
        nx1, ny1 = _scale_point(x1, y1)
        nx2, ny2 = _scale_point(x2, y2)
        new_box = Box(min(nx1, nx2), min(ny1, ny2), max(nx1, nx2), max(ny1, ny2))
        payload = pb.payload
        if payload is None:
            out.append(PageBox(box=new_box, origin=pb.origin))
            continue
        new_lines = [
            [list(_scale_point(px, py)) for px, py in quad] for quad in payload.lines
        ]
        text = payload.text
        if isinstance(text, list):
            text = list(text)
        fresh = TextBlock(
            xyxy=list(new_box.as_tuple),
            lines=new_lines,
            vertical=payload.vertical,
            language=payload.language,
            font_size=payload.font_size,
            text=text,
            translation=payload.translation,
        )
        out.append(
            PageBox(
                box=new_box,
                origin=pb.origin,
                payload=fresh,
                edited=pb.edited,
                bubble_no=pb.bubble_no,
                manual_override=pb.manual_override,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Levels (plan 05-02 Task 3) — D-12 numpy LUT, geometry-free (D-15)
# ---------------------------------------------------------------------------


def levels_lut(black: int, white: int, gamma: float) -> np.ndarray:
    """Build the 256-entry uint8 levels lookup table (D-12, RESEARCH Pattern 4).

    ``lut[v]`` maps input value ``v`` to its output: ``(v - black) /
    max(white - black, 1)`` clipped to ``[0, 1]``, gamma-corrected with
    ``**(1/gamma)``, scaled to ``[0, 255]``. 256 entries — NEVER the 768-entry
    PIL ``point()`` form (Pitfall 1; the numpy path is byte-identical and
    simpler). The white>black clamp (T-05-07, UI-SPEC surface 25): the range
    is internally normalized to ``[min(black, white), max(black, white)]`` so
    the LUT is ALWAYS monotone non-decreasing — an inverted map can never
    render, even when ``white <= black``. ``gamma`` must be > 0.
    """
    if not isinstance(gamma, (int, float)) or gamma <= 0:
        raise ValueError("gamma must be a positive number")
    lo = min(black, white)
    hi = max(black, white)
    lut = np.arange(256, dtype=np.float64)
    lut = (lut - lo) / max(hi - lo, 1)
    lut = np.clip(lut, 0.0, 1.0) ** (1.0 / gamma)
    return (lut * 255.0).round().astype(np.uint8)


def levels_page(
    image_rgb: np.ndarray, black: int, white: int, gamma: float
) -> np.ndarray:
    """Apply levels to the page pixels — geometry-free by design (D-15).

    Only the image is touched: the mask and boxes are NOT arguments and NOT
    transformed (a levels edit is pixels-only). ``levels_lut(...)[image_rgb]``
    is a fancy-index per-channel LUT apply (RESEARCH Pattern 4); the trailing
    ``.copy()`` detaches the result (Pitfall 2). Validates ``(H,W,3)`` uint8.
    """
    # levels is image-only: validate the image shape without a mask argument.
    if (
        image_rgb.ndim != 3
        or image_rgb.shape[2] != 3
        or image_rgb.dtype != np.uint8
    ):
        raise ValueError("expected (H,W,3) uint8 RGB")
    return levels_lut(black, white, gamma)[image_rgb].copy()


# ---------------------------------------------------------------------------
# Curves (plan 06-01, PROJ-04 "curves" half) — D-04/D-06 curve LUT math
# ---------------------------------------------------------------------------


def curve_lut(points: list[tuple[int, int]]) -> np.ndarray:
    """Build a 256-entry uint8 curve lookup table (D-04/D-06, PROJ-04 curves).

    ``lut[v]`` maps input value ``v`` to the piecewise-linear interpolation
    of the control points (Photoshop convention). Backstop (T-05-07
    discipline, the same guarantee ``levels_lut`` documents): the points are
    sorted by x, duplicate x kept LAST-WINS, x and y clipped to [0,255], and
    the (0,0)/(255,255) endpoints default in when absent — a degenerate point
    set can never produce NaN, an out-of-range index, or a silently-wrong
    map; interior non-monotone shapes remain legal (D-04 allows them).
    Returns a detached uint8 array.
    """
    clipped = [
        (max(0, min(255, int(x))), max(0, min(255, int(y)))) for x, y in points
    ]
    last_wins: dict[int, int] = {}
    for x, y in sorted(clipped, key=lambda p: p[0]):
        last_wins[x] = y
    xs = list(last_wins.keys())
    ys = [last_wins[x] for x in xs]
    if not xs or xs[0] != 0:
        xs.insert(0, 0)
        ys.insert(0, 0)
    if xs[-1] != 255:
        xs.append(255)
        ys.append(255)
    lut = np.interp(np.arange(256), xs, ys)
    return np.clip(np.round(lut), 0, 255).astype(np.uint8)


def curves_page(
    image_rgb: np.ndarray,
    master_points: list[tuple[int, int]],
    channel_points: dict[str, list[tuple[int, int]]],
) -> np.ndarray:
    """Apply master + per-channel curves to the page pixels — geometry-free
    by design (D-15): only the image is touched, mask and boxes are NOT
    arguments. Composition (A1, PROJ-04): the master LUT applies to ALL
    channels first, then each per-channel LUT applies to its plane AFTER the
    master (``out_c = channel_lut_c[master_lut[v]]``). Validates (H,W,3)
    uint8 (ValueError otherwise, the ``levels_page`` message); the trailing
    ``.copy()`` detaches the result (Pitfall 2).
    """
    if (
        image_rgb.ndim != 3
        or image_rgb.shape[2] != 3
        or image_rgb.dtype != np.uint8
    ):
        raise ValueError("expected (H,W,3) uint8 RGB")
    master = curve_lut(master_points)
    out = master[image_rgb]
    for ch, idx in (("R", 0), ("G", 1), ("B", 2)):
        pts = channel_points.get(ch)
        if pts:
            out[..., idx] = curve_lut(pts)[out[..., idx]]
    return out.copy()

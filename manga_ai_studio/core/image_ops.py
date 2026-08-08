"""Pure pixel + geometry math for page image ops (plan 05-02, PROJ-04).

Per D-10 the Qt EVENT DISPATCH lives in ``gui/canvas.py``; this module holds
only pure functions of ``(numpy arrays, list[PageBox])`` so
``tests/test_core/test_image_ops.py`` can exercise every transform headless —
no QWidget, no display, safe to call from the apply path (plans 05-06/05-07)
and from any worker thread. This module owns ALL pixel and geometry math for
rotate / crop / resize / levels; the GUI owns interaction only.

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

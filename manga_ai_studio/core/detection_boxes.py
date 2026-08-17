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

from loguru import logger

import panelcleaner.structures as st

from manga_ai_studio.core.box_model import DETECTED, PageBox, textblock_to_box
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
        # payload = the TextBlock, preserved untouched for OCR + export.
        # origin DETECTED so re-detect can replace it (D-03).
        detected_pageboxes.append(
            PageBox(
                box=clamped,
                origin=DETECTED,
                payload=blk,
                style=default_style(default_family) if default_family else None,
            )
        )
    return detected_pageboxes

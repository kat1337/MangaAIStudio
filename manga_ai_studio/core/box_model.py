"""``PageBox`` — the Phase 3 origin-tagged box data model + the V5 input
validator (plan 03-01 Task 2, D-14/D-15).

This module is the single shape consumed by the GUI layer (``BoxItem`` in
plan 03-03), the persistence layer (``ImageFile.boxes``), and the undo layer
(BOXES snapshots in plan 03-02). It is pure Python (no Qt) so it is
headless-testable and importable by both the GUI and the worker threads.

Design decisions honored (CONTEXT D-14 / D-15 / Claude's Discretion):

- D-14 (anti-pattern): ``PageBox`` COMPOSES a vendored ``Box``; it does NOT
  subclass it. The vendored ``Box`` must stay near-verbatim (mutable additions
  would break upstream diffability and the ``@frozen`` immutability
  guarantee). Origin/identity layer on top via composition.

- D-15 (selective-inpaint seam): ``PageBox`` carries ``mask=None`` and
  ``std_dev=None`` defaults. These are the D-15 seam — populated by a LATER
  inpaint phase via ``image_ops.pick_best_mask`` (which fills ``mask`` from a
  ``MaskFittingResults.best_mask``) and ``image_ops.border_std_deviation``
  (which fills ``std_dev``). Phase 3 leaves them ``None`` so the seam is
  OPEN (plan-for-it), not closed; a later phase fills them without rework.

- D-03 (origin discriminator): ``DETECTED`` / ``USER`` are module-level
  string constants — the single source of truth so the GUI, persistence, and
  undo layers all agree on the spelling.

- D-10 (undo identity): stable identity for undo comes from Python object
  identity of the ``PageBox`` instance (``id(pagebox)``), not a mutable
  ``box_id`` field. The vendored ``Box`` is ``@frozen`` (immutable) so it is
  safe to share by reference across snapshots.

V5 (input validation): ``textblock_to_box`` is the single coercion boundary
that turns a model-produced ``TextBlock.xyxy`` (untrusted) into a vendored
``Box`` with int coordinates. Bounds-clamping against the image rect happens
at the CALLER in plan 03-04 (this function does not know image dims).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from panelcleaner.structures import Box

# D-03 origin discriminator — module-level string constants. Single source of
# truth so the GUI (BoxItem), persistence (ImageFile.boxes), and undo (BOXES
# snapshots) layers all agree on the spelling.
DETECTED = "detected"
USER = "user"


@dataclass
class PageBox:
    """A text box on a page, tagged with its origin and carrying the D-15 seam.

    Attributes:
        box: The vendored frozen bbox (x1, y1, x2, y2). Immutable, safe to
            share by reference across undo snapshots (D-10).
        origin: ``DETECTED`` (model output) or ``USER`` (manually drawn). The
            D-03 discriminator that lets re-detect keep user boxes and
            replace detected ones.
        payload: The source ``TextBlock`` for Phase 4/5 OCR/export. ``None``
            for user boxes (they carry no TextBlock until OCR runs).
        mask: D-15 seam (DEFERRED). Per-box mask, populated by a LATER inpaint
            phase via ``image_ops.pick_best_mask``. **``None`` in Phase 3** —
            the seam is open, not closed.
        std_dev: D-15 seam (DEFERRED). Per-box border standard-deviation,
            populated by a later phase via ``image_ops.border_std_deviation``.
            **``None`` in Phase 3** — the seam is open, not closed.

    D-15 seam note: ``mask`` and ``std_dev`` are ``None`` in Phase 3 by
    design. A later selective-inpaint phase fills them per box against the
    page image + mask, with no rework to this dataclass or its consumers.
    """

    box: Box
    origin: str
    payload: Optional[object] = None
    mask: Optional[object] = None  # D-15 seam: per-box mask (DEFERRED — later phase)
    std_dev: Optional[float] = None  # D-15 seam: per-box std-dev (DEFERRED)


def textblock_to_box(blk) -> Box:
    """Coerce a model-produced ``TextBlock``'s ``xyxy`` into a vendored ``Box``.

    This is the single V5 input-validation boundary: model output is treated
    as untrusted (ASVS V5). ``TextBlock.xyxy`` is ``[int, int, int, int]``
    per ``panelcleaner/comic_text_detector/utils/textblock.py:50``, but we
    coerce via ``int()`` to defend against float/str drift from the model.

    Bounds-clamping against the image rect happens at the CALLER in plan 03-04
    — this function does not know the image dimensions, so it only guarantees
    int coordinates, not that the box lies inside the page.

    Pure: no Qt, no image access. Headless-testable with a duck-typed fake
    TextBlock (any object with a ``.xyxy`` attribute of length 4).

    Args:
        blk: A TextBlock-like object with a ``.xyxy`` attribute
            ``[x1, y1, x2, y2]``.

    Returns:
        A vendored ``Box(int(x1), int(y1), int(x2), int(y2))``.
    """
    x1, y1, x2, y2 = blk.xyxy
    return Box(int(x1), int(y1), int(x2), int(y2))

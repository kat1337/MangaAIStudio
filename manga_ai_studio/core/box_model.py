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

import copy as _copy
from dataclasses import dataclass, replace
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
        edited: Phase 4 (D-04 re-OCR gate). ``True`` once recognized text is
            manually edited; ``False`` after an OCR write. Peer field, NOT
            derived (derived-from-diff is fragile if OCR reproduces an edit).
            Travels in the BOXES snapshot (Pitfall 1).
        bubble_no: Phase 4 (D-15/D-16 reading-order number). ``None`` until
            reading order is assigned.
        manual_override: Phase 4 (D-16). ``True`` when the user hand-set a
            field that a page-level re-auto must preserve.

    D-15 seam note: ``mask`` and ``std_dev`` are ``None`` in Phase 3 by
    design. A later selective-inpaint phase fills them per box against the
    page image + mask, with no rework to this dataclass or its consumers.
    """

    box: Box
    origin: str
    payload: Optional[object] = None
    mask: Optional[object] = None  # D-15 seam: per-box mask (DEFERRED — later phase)
    std_dev: Optional[float] = None  # D-15 seam: per-box std-dev (DEFERRED)
    # Phase 4 peer fields (NOT derived — they survive undo + page-switch when
    # carried by boxes_snapshot; RESEARCH Pitfall 1).
    edited: bool = False  # D-04 re-OCR gate
    bubble_no: Optional[int] = None  # D-15/D-16 reading-order number
    manual_override: bool = False  # D-16 preserve-manual conflict policy

    # --------------------------------------------------------- text setters
    def _ensure_payload(self) -> None:
        """Lazily construct a ``TextBlock`` for a user box (payload is None
        until OCR runs). The xyxy is read from ``self.box`` via its
        ``as_tuple`` accessor (the x1y1x2y2 form). This is the SINGLE
        centralized payload-None guard so the Inspector / manual edit on a
        never-OCR'd box is safe (checker W1). Do NOT mutate the vendored Box
        (D-14 anti-pattern).
        """
        if self.payload is None:
            from panelcleaner.comic_text_detector.utils.textblock import TextBlock

            x1, y1, x2, y2 = self.box.as_tuple
            self.payload = TextBlock([x1, y1, x2, y2])

    def set_recognized_text(self, text: str) -> None:
        """Write OCR-recognized text (the OCR-write path).

        Stores ``payload.text`` as a str (RESEARCH Open Q 6 — str for
        unambiguous editor semantics; list conversion deferred to Phase 5
        export) and resets ``edited = False``. A silent re-OCR (D-04) applies
        to text written this way: subsequent "Run OCR" overwrites it without
        a confirm prompt.
        """
        self._ensure_payload()
        self.payload.text = text
        self.edited = False

    def set_recognized_text_edited(self, text: str) -> None:
        """Write a MANUAL recognized-text edit (the manual-edit path, D-04).

        Same payload-None guard + ``payload.text`` write as
        :meth:`set_recognized_text`, but sets ``edited = True`` so a
        subsequent re-OCR must prompt the user. This is the SINGLE
        centralized entry point for manual recognized-text edits (Inspector
        recognized-field edit + inline editor recognized-focus edit) so the
        payload-None guard is not bypassed and D-04 ``edited=True`` semantics
        are consistent. Plans 04/05 call this instead of writing
        ``payload.text`` directly.
        """
        self._ensure_payload()
        self.payload.text = text
        self.edited = True

    def set_translation(self, text: str) -> None:
        """Write the translation (the D-13 MT seam).

        Stores ``payload.translation`` (the TextBlock slot —
        textblock.py:68). Same payload-None guard as the recognized-text
        setters. This is the seam a future MTModel adapter calls; Phase 4
        wires the manual-translation entry points through it.
        """
        self._ensure_payload()
        self.payload.translation = text

    def has_recognized_text(self) -> bool:
        """Return ``True`` if the box carries non-empty recognized text.

        ``False`` for ``payload=None`` or empty text. ``TextBlock.text`` may
        be a str OR a list (textblock.py:65) — both shapes are handled:
        a list is joined and stripped before the truthiness check.
        """
        if self.payload is None:
            return False
        t = self.payload.text
        if isinstance(t, list):
            t = "".join(str(s) for s in t).strip()
        return bool(t)

    # ------------------------------------------------------------ undo seam
    def copy(self) -> "PageBox":
        """Return a NEW ``PageBox`` with a detached payload (RESEARCH Pitfall 8).

        Uses ``dataclasses.replace`` to clone the dataclass with a
        ``copy.copy`` (shallow) of the payload. Shallow-copy is sufficient
        because Phase 4 only mutates ``.text`` / ``.translation`` (top-level
        attributes) on the payload (RESEARCH Assumption A3). The vendored
        ``Box`` is ``@frozen`` so sharing it by reference is safe (D-10) — it
        is NOT copied. This detachment is what makes ``boxes_snapshot()`` +
        the BOXES undo stack restore the snapshot-time text instead of the
        live (post-edit) text.
        """
        return replace(self, payload=_copy.copy(self.payload))


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

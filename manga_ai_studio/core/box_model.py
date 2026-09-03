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

from manga_ai_studio.core.text_style import TextStyle

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
        mask: D-15 seam. Per-box mask — a box-cropped mode-"1" PIL image,
            POPULATED by Phase 8 (``derive_page_mask_state``, plan 08-03,
            via the vendored masker machinery). ``None`` until a per-box fit
            runs (fresh/legacy boxes).
        std_dev: D-15 seam. Per-box border standard-deviation, POPULATED by
            Phase 8's per-box fit (the honest measured value; the gate is
            applied downstream). ``None`` until a fit runs.
        edited: Phase 4 (D-04 re-OCR gate). ``True`` once recognized text is
            manually edited; ``False`` after an OCR write. Peer field, NOT
            derived (derived-from-diff is fragile if OCR reproduces an edit).
            Travels in the BOXES snapshot (Pitfall 1).
        bubble_no: Phase 4 (D-15/D-16 reading-order number). ``None`` until
            reading order is assigned.
        manual_override: Phase 4 (D-16). ``True`` when the user hand-set a
            field that a page-level re-auto must preserve.
        style: Phase 7 (D-06 flat per-box typesetting style). The composed
            ``TextStyle`` — ``None`` means the renderers fall back to the
            defaults (fresh/legacy boxes). NEVER mutated in place: every
            style change assigns a fresh instance via ``dataclasses.replace``
            (RESEARCH Pitfall 1). ``copy()`` detaches it (Pitfall 8).
        inpaint_override: Phase 8 (D-14 tri-state encoding). Per-box inpaint
            decision: ``None`` = Auto (the std-dev gate decides), ``"always"``
            = force inpaint, ``"never"`` = skip. NOT ``manual_override`` —
            that name is TAKEN by the Phase 4 reading-order pin above.

    D-15 seam note: ``mask`` and ``std_dev`` default to ``None``; Phase 8
    (plan 08-03) POPULATES them per box against the page image + mask, with
    no rework to this dataclass or its consumers.
    """

    box: Box
    origin: str
    payload: Optional[object] = None
    mask: Optional[object] = None  # D-15 seam: per-box box-cropped mode-"1" mask (Phase 8 populates)
    std_dev: Optional[float] = None  # D-15 seam: per-box border std-dev (Phase 8 populates)
    # Phase 4 peer fields (NOT derived — they survive undo + page-switch when
    # carried by boxes_snapshot; RESEARCH Pitfall 1).
    edited: bool = False  # D-04 re-OCR gate
    bubble_no: Optional[int] = None  # D-15/D-16 reading-order number
    manual_override: bool = False  # D-16 preserve-manual conflict policy
    # Phase 7 (D-06): flat per-box typesetting style. None = renderers use
    # the TextStyle defaults. Composes (D-14 — the vendored Box/TextBlock
    # stay untouched); copy() detaches it (Pitfall 8).
    style: Optional[TextStyle] = None
    # Phase 8 (D-14 tri-state encoding): per-box inpaint decision. None =
    # Auto (std-dev gate decides), "always" = force inpaint, "never" = skip.
    # NOT manual_override — that name is TAKEN by the Phase 4 reading-order
    # pin above (RESEARCH Q3).
    inpaint_override: Optional[str] = None
    # Phase 08.1 (D-04 quad-state + fill_color): per-box median fill color.
    # Populated at fit time from MaskFittingResults.median_color (off-white
    # rounding baked at panelcleaner/image_ops.py:535). None until fitted.
    # Carried through boxes_snapshot, geometry-op invalidation, and .mas
    # persistence. Tuple is immutable — copy() shares by ref.
    fill_color: Optional[tuple[int, int, int]] = None
    # quick-260903-lm6: detector confidence in [0, 1]; None = unknown
    # (user-drawn, scattered, or legacy box). Populated by
    # build_detected_pageboxes; copy() uses dataclasses.replace, so this
    # plain field survives undo snapshots automatically.
    confidence: Optional[float] = None

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

    # ------------------------------------------------- inpaint state (Phase 8)
    def _has_auto_mask_content(self) -> bool:
        """Return ``True`` iff the box carries non-empty AUTO mask content.

        ``self.mask`` is a box-cropped mode-"1" PIL image (the plan 08-03
        storage convention: content = the non-zero pixels), so ``getbbox()``
        is the emptiness probe — the same check the vendored
        ``pick_best_mask`` applies to a precise mask (panelcleaner
        image_ops.py). An all-zero (empty) mask reports ``getbbox() is
        None`` and fails this check.
        """
        return self.mask is not None and self.mask.getbbox() is not None

    def inpaint_state(self, threshold: float) -> str:
        """Derive the border-state contract state (08-UI-SPEC §Color + 08.1 D-01/D-04).

        A pure function of own fields + ``threshold`` (the
        ``has_recognized_text`` shape — headless-testable, no UI logic).
        Returns exactly one of:

        - ``"forced_inpaint"``: ``inpaint_override == "always"`` — forced LaMa.
        - ``"forced_fill"``: ``inpaint_override == "fill"`` — forced median fill.
        - ``"never"``: ``inpaint_override == "never"`` — leave text entirely.
        - ``"will_inpaint"``: Auto AND ``std_dev`` is not None AND
          ``std_dev > threshold`` AND the box has auto mask content — complex
          box, gate passes for inpaint (D-01 inverted).
        - ``"will_fill"``: Auto AND ``std_dev`` is not None AND
          ``std_dev <= threshold`` AND the box has auto mask content — uniform
          box, gate passes for fill (D-01 inverted).
        - ``"gate_skipped"``: everything else (no fit data yet, or no auto
          mask content — noise box).

        This is the SINGLE derivation site: ``BoxItem.set_inpaint_state``
        (plan 08-06) and ``refresh_box_inpaint_states`` (plan 08-07) consume
        it; the logic is not duplicated elsewhere.

        Backward compat: callers comparing to ``"forced"`` should migrate to
        ``"forced_inpaint"``; this implementation still returns
        ``"forced_inpaint"`` for ``"always"`` so GUI checks for ``"forced"``
        will miss it until their next plan (headless tracer proves the new
        vocabulary headlessly).
        """
        if self.inpaint_override == "always":
            return "forced_inpaint"
        if self.inpaint_override == "fill":
            return "forced_fill"
        if self.inpaint_override == "never":
            return "never"
        if not self._has_auto_mask_content() or self.std_dev is None:
            return "gate_skipped"
        if self.std_dev <= threshold:
            return "will_fill"
        return "will_inpaint"

    # ------------------------------------------------------------ undo seam
    def copy(self) -> "PageBox":
        """Return a NEW ``PageBox`` with detached payload, style AND mask
        (Pitfall 8).

        Uses ``dataclasses.replace`` to clone the dataclass with
        ``copy.copy`` (shallow) of the payload and the style. Shallow-copy is
        sufficient because Phase 4 only mutates ``.text`` / ``.translation``
        (top-level attributes) on the payload (RESEARCH Assumption A3) and
        Phase 7 NEVER mutates a ``TextStyle`` in place (every change assigns
        a fresh instance via ``dataclasses.replace``). The Phase 8 per-box
        ``mask`` is a MUTABLE PIL image, so it is detached too — without
        that, a BOXES undo would restore post-edit masks (the 04-05 lesson
        applied to the new field). The vendored ``Box`` is ``@frozen`` so
        sharing it by reference is safe (D-10) — it is NOT copied. This
        detachment is what makes ``boxes_snapshot()`` + the BOXES undo stack
        restore the snapshot-time text, style, AND mask instead of the live
        (post-edit) ones.
        """
        return replace(
            self,
            payload=_copy.copy(self.payload),
            style=_copy.copy(self.style),
            mask=_copy.copy(self.mask) if self.mask is not None else None,
            fill_color=self.fill_color,
        )


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

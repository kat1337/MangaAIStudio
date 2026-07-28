"""HistoryManager — the three-stack undo/redo engine with a unified timeline
(FLOW-02, UI-SPEC surface 8, Phase 3 D-10/D-11).

Reimplemented patterned after MangaCleaner_GPU ``utils/history.py`` (D-12
reference-only: the MangaCleaner_GPU binary distribution carries no LICENSE, so
it is all-rights-reserved and cannot be vendored). The push/pop shape is
preserved, but the buffer-lifetime discipline is stricter: every push AND every
pop enforces ``.copy()`` / snapshot materialization so the history never holds
a reference to the live canvas mask/image/boxes (RESEARCH Pitfall 2 + 3;
PATTERNS.md §Shared Pattern 1 + 5).

Three logical stacks (Phase 1 contracted 2 — MASK + IMAGE; Phase 3 D-10 adds
the 3rd BOXES stack; STATE.md "two logical stacks not four" extended to "three
not seven" — BOXES is ONE stack, op-type lives inside each record's metadata):
- MASK stack: full ``QImage`` snapshots of the editable mask, one per completed
  stroke (the ``canvas.mask_modified`` signal from plan 04 is the push hook).
- IMAGE stack: ``(x, y, patch)`` tuples where ``patch`` is the numpy array of
  the inpainted region (plan 05's ``_on_inpaint_finished`` already calls
  ``push_image_action``).
- BOXES stack (Phase 3): per-page ``list[(box, origin, payload)]`` snapshots of
  the text-box set (plan 03-03's ``canvas.boxes_snapshot()`` is the push hook).

Phase 1 stores full snapshots per entry (RESEARCH Open Question 3 — snapshot
vs incremental). The default ``limit=20`` matches MangaCleaner_GPU
``Config.MAX_HISTORY``; the oldest entry is dropped on overflow (T-01-16 DoS
mitigation).

Unified timeline (Phase 3 D-11): a single Ctrl+Z pops the most-recent entry
across all three stores. To compare timestamps across stores of different
shapes, Phase 3 widens Phase 1's bare entry values to ``(stamp, value)`` where
``stamp`` is a monotonic integer from ``self._seq`` (RESEARCH Pitfall 4 —
wall-clock ``time.monotonic`` / ``time.time`` would skew across threads and
produce wrong pop order). The per-type pop methods are preserved; the unified
``undo()`` / ``redo()`` delegate to them.

Security:
    - Every push and pop enforces ``.copy()`` / fresh-snapshot materialization
      on the values that cross the trust boundary (canvas <-> history stack).
      The regression guards ``test_mask_snapshot_is_copied`` (push detachment),
      ``test_mask_pop_returns_copy`` (pop detachment), and
      ``test_boxes_snapshot_is_detached`` (Phase 3 BOXES push detachment —
      Pitfall 3) lock this — RESEARCH Pitfall 2 + 3 applied to the undo path
      (T-01-11c, T-03-02).
    - The monotonic ``_seq`` stamp gives a deterministic total order across
      threads (Pitfall 4) so the unified pop never reorders history under
      thread-scheduling jitter (T-03-03).
    - The configurable ``limit`` bounds total memory (T-01-16).
"""

from __future__ import annotations

from typing import List, Tuple, Union

import numpy as np
from PySide6.QtGui import QImage

# A single image-stack entry's value: (x, y, patch) where patch is an
# (H, W, 3) uint8 numpy array of the inpainted region (plan 05).
ImageAction = Tuple[int, int, np.ndarray]

# A single boxes-snapshot entry's value: list of (box, origin, payload) tuples.
# The BOXES stack is generic over the snapshot shape — `box` is the vendored
# frozen ``Box`` (immutable, safe to share by reference), `origin` a string
# ('detected'/'manual'), `payload` the caller-attached metadata dict (op-type,
# OCR text — D-10: op-type lives in metadata, NOT in separate per-type lists).
BoxesSnapshot = List[Tuple]

# Per-entry cap on each stack (MangaCleaner_GPU Config.MAX_HISTORY). The oldest
# entry is dropped on overflow (T-01-16).
DEFAULT_HISTORY_LIMIT = 20


class HistoryManager:
    """Three-stack undo/redo engine (MASK + IMAGE + BOXES), each with its own
    redo list, plus a unified-timeline pop across all three stores.

    Internal layout (6 lists representing 3 logical stacks per UI-SPEC surface
    8 + Phase 3 D-10/D-11; BOXES is ONE logical stack — op-type lives inside
    each record's metadata, not as separate per-op-type lists):
    - ``_mask_undo`` / ``_mask_redo``: ``(stamp, QImage)`` snapshots of the mask.
    - ``_image_undo`` / ``_image_redo``: ``(stamp, (x, y, patch_np))`` tuples.
    - ``_boxes_undo`` / ``_boxes_redo``: ``(stamp, snapshot_list)`` tuples.

    Every entry carries a monotonic integer ``stamp`` from ``self._seq``
    (Pitfall 4 — NOT wall-clock). The unified ``undo()`` / ``redo()`` compare
    the tail stamps of all three non-empty undo/redo lists and pop the store
    with the most-recent stamp, delegating to the matching per-type pop method.

    Buffer lifetime (RESEARCH Pitfall 2 + 3; PATTERNS.md §Shared Pattern 1):
    ``.copy()`` on every mask/image push AND pop; fresh-snapshot materialization
    on every boxes push. The history never aliases the caller's QImage/numpy/
    boxes list. The regression guards ``test_mask_snapshot_is_copied`` (push),
    ``test_mask_pop_returns_copy`` (pop), and ``test_boxes_snapshot_is_detached``
    (Phase 3 BOXES push) lock this.
    """

    def __init__(self, limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        self.limit = int(limit)
        # Monotonic integer stamp counter (Pitfall 4 — NOT wall-clock). Every
        # push stamps its entry so the unified-timeline pop can compare
        # timestamps across all three stores.
        self._seq: int = 0
        # Phase 1's MASK + IMAGE stacks (Phase 3 widens each entry to
        # (stamp, value) so the unified pop can order across stores).
        self._mask_undo: list[tuple[int, QImage]] = []
        self._mask_redo: list[tuple[int, QImage]] = []
        self._image_undo: list[tuple[int, ImageAction]] = []
        self._image_redo: list[tuple[int, ImageAction]] = []
        # Phase 3 D-10 — the third BOXES stack (ONE logical stack).
        self._boxes_undo: list[tuple[int, BoxesSnapshot]] = []
        self._boxes_redo: list[tuple[int, BoxesSnapshot]] = []

    def _stamp(self) -> int:
        """Return the next monotonic integer stamp (Pitfall 4).

        Wall-clock (``time.monotonic`` / ``time.time``) skews across threads
        and would produce wrong pop order under the GIL's release/reacquire
        scheduling; a per-instance integer counter gives a deterministic total
        order that is immune to thread-scheduling jitter.
        """
        self._seq += 1
        return self._seq

    # ---------------------------------------------------------- mask stack
    def push_mask_state(self, mask_qimage: QImage) -> None:
        """Push a mask snapshot onto the mask undo stack.

        The ``.copy()`` detaches from the live canvas mask (RESEARCH Pitfall 2;
        ``test_mask_snapshot_is_copied`` is the regression guard). A new edit
        invalidates the redo branch (``test_mask_push_clears_redo``). The
        oldest entry is dropped on overflow (T-01-16). Phase 3 widens the entry
        shape to ``(stamp, QImage)`` (Pitfall 4) so the unified pop can order
        across stores.
        """
        self._mask_undo.append((self._stamp(), mask_qimage.copy()))
        self._mask_redo.clear()
        if len(self._mask_undo) > self.limit:
            self._mask_undo.pop(0)

    def pop_mask_undo(self, current_mask: QImage) -> QImage | None:
        """Pop the previous mask snapshot, stashing the current for redo.

        Returns ``None`` when the undo stack is empty. The returned snapshot is
        ``.copy()``-detached from the internal list so subsequent pushes/pops
        cannot mutate it (``test_mask_pop_returns_copy`` is the regression
        guard). The current mask is captured (``.copy()``) into the redo stack
        so a redo reverses the undo. Phase 3: the ``(stamp, value)`` unwrap is
        internal — callers still receive a bare ``QImage``.
        """
        if not self._mask_undo:
            return None
        _stamp, previous = self._mask_undo.pop()
        self._mask_redo.append((self._stamp(), current_mask.copy()))
        return previous.copy()

    def pop_mask_redo(self, current_mask: QImage) -> QImage | None:
        """Pop the next mask snapshot (reverses :meth:`pop_mask_undo`).

        The current mask is captured (``.copy()``) into the undo stack so a
        subsequent undo reverses the redo. The returned snapshot is
        ``.copy()``-detached from the internal list. Phase 3: the
        ``(stamp, value)`` unwrap is internal.
        """
        if not self._mask_redo:
            return None
        _stamp, next_state = self._mask_redo.pop()
        self._mask_undo.append((self._stamp(), current_mask.copy()))
        return next_state.copy()

    # -------------------------------------------------------- image stack
    def push_image_action(self, x: int, y: int, patch: np.ndarray) -> None:
        """Push an ``(x, y, patch)`` image action onto the image undo stack.

        ``patch`` is the numpy array of the inpainted region (the original
        pre-inpaint patch, captured by the caller before compositing). The
        ``.copy()`` detaches from the caller's array (RESEARCH Pitfall 2 for
        numpy). A new edit invalidates the redo branch. The oldest entry is
        dropped on overflow (T-01-16). Phase 3 widens the entry shape to
        ``(stamp, (x, y, patch))`` (Pitfall 4).
        """
        self._image_undo.append(
            (self._stamp(), (int(x), int(y), patch.copy()))
        )
        self._image_redo.clear()
        if len(self._image_undo) > self.limit:
            self._image_undo.pop(0)

    def pop_image_undo(
        self, current_img: np.ndarray
    ) -> Union[ImageAction, None]:
        """Pop the previous image patch, stashing the current region for redo.

        Returns ``None`` when the undo stack is empty. The current image's
        region is captured (``.copy()``) into the redo stack so a redo reverses
        the undo (MangaCleaner_GPU ``history.py:593-595`` pattern). The
        returned patch is ``.copy()``-detached from the internal list
        (``test_image_undo_swaps_current_into_redo`` is the regression guard).
        Phase 3: the ``(stamp, value)`` unwrap is internal.
        """
        if not self._image_undo:
            return None
        _stamp, (x, y, patch) = self._image_undo.pop()
        h, w = patch.shape[:2]
        redo_patch = current_img[y : y + h, x : x + w].copy()
        self._image_redo.append((self._stamp(), (x, y, redo_patch)))
        return (x, y, patch.copy())

    def pop_image_redo(
        self, current_img: np.ndarray
    ) -> Union[ImageAction, None]:
        """Pop the next image patch (reverses :meth:`pop_image_undo`).

        The current image's region is captured (``.copy()``) into the undo
        stack so a subsequent undo reverses the redo. The returned patch is
        ``.copy()``-detached from the internal list. Phase 3: the
        ``(stamp, value)`` unwrap is internal.
        """
        if not self._image_redo:
            return None
        _stamp, (x, y, patch) = self._image_redo.pop()
        h, w = patch.shape[:2]
        undo_patch = current_img[y : y + h, x : x + w].copy()
        self._image_undo.append((self._stamp(), (x, y, undo_patch)))
        return (x, y, patch.copy())

    # --------------------------------------------------------- boxes stack
    @staticmethod
    def _materialize_snapshot(boxes: list) -> list:
        """Build a fresh, detached snapshot list from ``boxes`` (Pitfall 3).

        Each item is rebuilt as a fresh tuple whose mutable members are
        shallow-copied (``.copy()`` where available) so the snapshot never
        aliases the caller's list or its items. The BoxItem's QRectF mutates
        live during drag; storing a reference would alias and the history
        would silently track the drag instead of the snapshot at push-time.

        Shape-agnostic: items may be tuples of any arity (the BOXES stack is
        generic over the snapshot shape — D-10). Non-tuple items (e.g. bare
        Box) are copied if mutable, else shared (the vendored Box is @frozen).
        """
        snap = []
        for item in boxes:
            if isinstance(item, tuple):
                snap.append(
                    tuple(
                        m.copy() if hasattr(m, "copy") else m for m in item
                    )
                )
            else:
                snap.append(item.copy() if hasattr(item, "copy") else item)
        return snap

    def push_boxes_state(self, boxes: list) -> None:
        """Push a boxes-list snapshot onto the boxes undo stack (Phase 3 D-10).

        The snapshot MUST materialize a fresh tuple per item from its CURRENT
        state at push-time (RESEARCH Pitfall 3 — the BoxItem's QRectF mutates
        live during drag; storing a reference would alias and the history would
        silently track the drag instead of the snapshot at push-time). The
        caller (``canvas.boxes_snapshot()`` in plan 03-03) is responsible for
        reading each ``BoxItem.rect()`` -> ``Box(int(...), ...)`` at snapshot
        time (Pitfall 6 — round to int at every Box<->QRectF boundary); this
        method detaches the snapshot from the caller's list AND from the
        caller's mutable sub-objects.

        BOXES is ONE logical stack (D-10 / STATE.md "two logical stacks not
        four" extended to "three not seven") — op-type (create/move/resize/
        delete) lives inside each record's metadata at the CALLER's discretion,
        NOT as separate per-op-type lists.

        A new push invalidates the redo branch. The oldest entry is dropped on
        overflow (T-01-16). Phase 3 widens the entry shape to
        ``(stamp, snapshot_list)`` (Pitfall 4).
        """
        self._boxes_undo.append((self._stamp(), self._materialize_snapshot(boxes)))
        self._boxes_redo.clear()
        if len(self._boxes_undo) > self.limit:
            self._boxes_undo.pop(0)

    def pop_boxes_undo(
        self, current_boxes: list
    ) -> Union[BoxesSnapshot, None]:
        """Pop the previous boxes snapshot, stashing the current for redo.

        Returns ``None`` when the undo stack is empty. The current boxes list
        is captured (a fresh snapshot, mirroring ``push_boxes_state``'s Pitfall
        3 detachment) into the redo stack so a redo reverses the undo. The
        returned snapshot is a fresh copy so subsequent pushes/pops cannot
        mutate it.
        """
        if not self._boxes_undo:
            return None
        _stamp, previous = self._boxes_undo.pop()
        # Stash a fresh snapshot of the current boxes into the redo branch.
        self._boxes_redo.append(
            (self._stamp(), self._materialize_snapshot(current_boxes))
        )
        # Return a fresh copy of the popped snapshot (defensive detachment so
        # the caller's mutation cannot reach the internal list).
        return self._materialize_snapshot(previous)

    def pop_boxes_redo(
        self, current_boxes: list
    ) -> Union[BoxesSnapshot, None]:
        """Pop the next boxes snapshot (reverses :meth:`pop_boxes_undo`).

        The current boxes list is captured (a fresh snapshot) into the undo
        stack so a subsequent undo reverses the redo. The returned snapshot is
        a fresh copy.
        """
        if not self._boxes_redo:
            return None
        _stamp, next_state = self._boxes_redo.pop()
        self._boxes_undo.append(
            (self._stamp(), self._materialize_snapshot(current_boxes))
        )
        return self._materialize_snapshot(next_state)

    # -------------------------------------------------- unified timeline
    def undo(
        self,
        current_mask: QImage,
        current_img: np.ndarray,
        current_boxes: list,
    ):
        """Unified-timeline pop (D-11): pop the most-recent entry across all
        three stores.

        Builds candidates from the tail stamps of all three non-empty undo
        lists, picks the max-stamp kind, delegates to the matching per-type pop
        method, and returns ``(kind, value)`` — or ``None`` when all three undo
        lists are empty (``test_unified_undo_all_empty_returns_none``). The
        ``kind`` in the return tells the caller (the UI collapse in plan 03-05)
        which stack was popped so it can apply the value to the right canvas
        slot and show "Undo: {op}" feedback (T-03-03 repudiation mitigation).

        The monotonic integer stamps give a deterministic total order (Pitfall
        4) immune to thread-scheduling jitter.
        """
        candidates = []
        if self._mask_undo:
            candidates.append(("mask", self._mask_undo[-1][0]))
        if self._image_undo:
            candidates.append(("image", self._image_undo[-1][0]))
        if self._boxes_undo:
            candidates.append(("boxes", self._boxes_undo[-1][0]))
        if not candidates:
            return None
        kind = max(candidates, key=lambda c: c[1])[0]
        if kind == "mask":
            return ("mask", self.pop_mask_undo(current_mask))
        if kind == "image":
            return ("image", self.pop_image_undo(current_img))
        return ("boxes", self.pop_boxes_undo(current_boxes))

    def redo(
        self,
        current_mask: QImage,
        current_img: np.ndarray,
        current_boxes: list,
    ):
        """Unified-timeline redo (D-11): pop the most-recent entry across all
        three REDO stores. Mirrors :meth:`undo` across the redo lists.
        """
        candidates = []
        if self._mask_redo:
            candidates.append(("mask", self._mask_redo[-1][0]))
        if self._image_redo:
            candidates.append(("image", self._image_redo[-1][0]))
        if self._boxes_redo:
            candidates.append(("boxes", self._boxes_redo[-1][0]))
        if not candidates:
            return None
        kind = max(candidates, key=lambda c: c[1])[0]
        if kind == "mask":
            return ("mask", self.pop_mask_redo(current_mask))
        if kind == "image":
            return ("image", self.pop_image_redo(current_img))
        return ("boxes", self.pop_boxes_redo(current_boxes))

    # ------------------------------------------------------------- flags
    def can_undo_mask(self) -> bool:
        """True iff the mask undo stack has at least one entry."""
        return len(self._mask_undo) > 0

    def can_redo_mask(self) -> bool:
        """True iff the mask redo stack has at least one entry."""
        return len(self._mask_redo) > 0

    def can_undo_image(self) -> bool:
        """True iff the image undo stack has at least one entry."""
        return len(self._image_undo) > 0

    def can_redo_image(self) -> bool:
        """True iff the image redo stack has at least one entry."""
        return len(self._image_redo) > 0

    def can_undo_boxes(self) -> bool:
        """True iff the boxes undo stack has at least one entry (Phase 3)."""
        return len(self._boxes_undo) > 0

    def can_redo_boxes(self) -> bool:
        """True iff the boxes redo stack has at least one entry (Phase 3)."""
        return len(self._boxes_redo) > 0

    def can_undo(self) -> bool:
        """True iff ANY of the three undo lists is non-empty (unified, D-11)."""
        return (
            bool(self._mask_undo)
            or bool(self._image_undo)
            or bool(self._boxes_undo)
        )

    def can_redo(self) -> bool:
        """True iff ANY of the three redo lists is non-empty (unified, D-11)."""
        return (
            bool(self._mask_redo)
            or bool(self._image_redo)
            or bool(self._boxes_redo)
        )

    # ------------------------------------------------------------- reset
    def clear(self) -> None:
        """Empty all SIX internal lists (called on page change).

        A fresh ``HistoryManager`` per page keeps undo from crossing page
        boundaries (UI-SPEC surface 8; ``test_clear_resets_all`` +
        ``test_clear_resets_all_six_lists`` guards). Phase 3 extends clear to
        the two BOXES lists (D-10).
        """
        self._mask_undo.clear()
        self._mask_redo.clear()
        self._image_undo.clear()
        self._image_redo.clear()
        self._boxes_undo.clear()
        self._boxes_redo.clear()

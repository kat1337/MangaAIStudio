"""HistoryManager — the two-stack undo/redo engine (FLOW-02, UI-SPEC surface 8).

Reimplemented patterned after MangaCleaner_GPU ``utils/history.py`` (D-12
reference-only: the MangaCleaner_GPU binary distribution carries no LICENSE, so
it is all-rights-reserved and cannot be vendored). The push/pop shape is
preserved (4 internal lists representing 2 logical stacks — MASK and IMAGE —
each with an undo and a redo list), but the buffer-lifetime discipline is
stricter: every push AND every pop enforces ``.copy()`` detachment so the
history never holds a reference to the live canvas mask/image (RESEARCH Pitfall
2; PATTERNS.md §Shared Pattern 5).

Two logical stacks (UI-SPEC surface 8 contracts exactly 2; do not add a 3rd):
- MASK stack: full ``QImage`` snapshots of the editable mask, one per completed
  stroke (the ``canvas.mask_modified`` signal from plan 04 is the push hook).
- IMAGE stack: ``(x, y, patch)`` tuples where ``patch`` is the numpy array of
  the inpainted region (plan 05's ``_on_inpaint_finished`` already calls
  ``push_image_action``).

Phase 1 stores full snapshots per entry (RESEARCH Open Question 3 — snapshot
vs incremental). The default ``limit=20`` matches MangaCleaner_GPU
``Config.MAX_HISTORY``; the oldest entry is dropped on overflow (T-01-16 DoS
mitigation).

Security:
    - Every push and pop enforces ``.copy()`` on the QImage/numpy values that
      cross the trust boundary (canvas <-> history stack). The two regression
      guards ``test_mask_snapshot_is_copied`` (push detachment) and
      ``test_mask_pop_returns_copy`` (pop detachment) lock this — RESEARCH
      Pitfall 2 applied to the undo path (T-01-11c).
    - The configurable ``limit`` bounds total memory (T-01-16).
"""

from __future__ import annotations

from typing import Tuple, Union

import numpy as np
from PySide6.QtGui import QImage

# A single image-stack entry: (x, y, patch) where patch is an (H, W, 3) uint8
# numpy array of the inpainted region (plan 05).
ImageAction = Tuple[int, int, np.ndarray]

# Per-entry cap on the mask and image stacks (MangaCleaner_GPU
# Config.MAX_HISTORY). The oldest entry is dropped on overflow (T-01-16).
DEFAULT_HISTORY_LIMIT = 20


class HistoryManager:
    """Two-stack undo/redo engine (MASK + IMAGE), each with its own redo list.

    Internal layout (4 lists representing 2 logical stacks per UI-SPEC surface
    8; the layout matches MangaCleaner_GPU ``utils/history.py`` — do not add a
    3rd/4th logical stack):
    - ``_mask_undo`` / ``_mask_redo``: full ``QImage`` snapshots of the mask.
    - ``_image_undo`` / ``_image_redo``: ``(x, y, patch_np)`` tuples.

    Buffer lifetime (RESEARCH Pitfall 2; PATTERNS.md §Shared Pattern 5):
    ``.copy()`` on every push AND every pop — the history never aliases the
    caller's QImage/numpy. The two regression guards
    ``test_mask_snapshot_is_copied`` (push) and ``test_mask_pop_returns_copy``
    (pop) lock this.
    """

    def __init__(self, limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        self.limit = int(limit)
        self._mask_undo: list[QImage] = []
        self._mask_redo: list[QImage] = []
        self._image_undo: list[ImageAction] = []
        self._image_redo: list[ImageAction] = []

    # ---------------------------------------------------------- mask stack
    def push_mask_state(self, mask_qimage: QImage) -> None:
        """Push a mask snapshot onto the mask undo stack.

        The ``.copy()`` detaches from the live canvas mask (RESEARCH Pitfall 2;
        ``test_mask_snapshot_is_copied`` is the regression guard). A new edit
        invalidates the redo branch (``test_mask_push_clears_redo``). The
        oldest entry is dropped on overflow (T-01-16).
        """
        self._mask_undo.append(mask_qimage.copy())
        self._mask_redo.clear()
        if len(self._mask_undo) > self.limit:
            self._mask_undo.pop(0)

    def pop_mask_undo(self, current_mask: QImage) -> QImage | None:
        """Pop the previous mask snapshot, stashing the current for redo.

        Returns ``None`` when the undo stack is empty. The returned snapshot is
        ``.copy()``-detached from the internal list so subsequent pushes/pops
        cannot mutate it (``test_mask_pop_returns_copy`` is the regression
        guard). The current mask is captured (``.copy()``) into the redo stack
        so a redo reverses the undo.
        """
        if not self._mask_undo:
            return None
        previous = self._mask_undo.pop()
        self._mask_redo.append(current_mask.copy())
        return previous.copy()

    def pop_mask_redo(self, current_mask: QImage) -> QImage | None:
        """Pop the next mask snapshot (reverses :meth:`pop_mask_undo`).

        The current mask is captured (``.copy()``) into the undo stack so a
        subsequent undo reverses the redo. The returned snapshot is
        ``.copy()``-detached from the internal list.
        """
        if not self._mask_redo:
            return None
        next_state = self._mask_redo.pop()
        self._mask_undo.append(current_mask.copy())
        return next_state.copy()

    # -------------------------------------------------------- image stack
    def push_image_action(self, x: int, y: int, patch: np.ndarray) -> None:
        """Push an ``(x, y, patch)`` image action onto the image undo stack.

        ``patch`` is the numpy array of the inpainted region (the original
        pre-inpaint patch, captured by the caller before compositing). The
        ``.copy()`` detaches from the caller's array (RESEARCH Pitfall 2 for
        numpy). A new edit invalidates the redo branch. The oldest entry is
        dropped on overflow (T-01-16).
        """
        self._image_undo.append((int(x), int(y), patch.copy()))
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
        """
        if not self._image_undo:
            return None
        x, y, patch = self._image_undo.pop()
        h, w = patch.shape[:2]
        redo_patch = current_img[y : y + h, x : x + w].copy()
        self._image_redo.append((x, y, redo_patch))
        return (x, y, patch.copy())

    def pop_image_redo(
        self, current_img: np.ndarray
    ) -> Union[ImageAction, None]:
        """Pop the next image patch (reverses :meth:`pop_image_undo`).

        The current image's region is captured (``.copy()``) into the undo
        stack so a subsequent undo reverses the redo. The returned patch is
        ``.copy()``-detached from the internal list.
        """
        if not self._image_redo:
            return None
        x, y, patch = self._image_redo.pop()
        h, w = patch.shape[:2]
        undo_patch = current_img[y : y + h, x : x + w].copy()
        self._image_undo.append((x, y, undo_patch))
        return (x, y, patch.copy())

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

    # ------------------------------------------------------------- reset
    def clear(self) -> None:
        """Empty all four internal lists (called on page change).

        A fresh ``HistoryManager`` per page keeps undo from crossing page
        boundaries (UI-SPEC surface 8; ``test_clear_resets_all`` guard).
        """
        self._mask_undo.clear()
        self._mask_redo.clear()
        self._image_undo.clear()
        self._image_redo.clear()

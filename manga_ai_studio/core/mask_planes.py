"""Three-plane mask model helpers (plan 08-02, RESEARCH §2.2 Option B).

The Phase 8 canvas composes its displayed/LaMa/persisted mask from three
planes — a DERIVED auto binary (never painted into), a manual-stroke QImage,
and an erase-ledger QImage — so that:

- hand strokes always inpaint (D-01 — the manual plane is unconditional),
- detected content is discardable/re-dilatable without touching strokes
  (D-02/D-07/D-08 — only the auto plane is derived/replaced),
- an eraser's effect survives recomposition (the ledger is subtracted from
  every composite: ``composite = (manual | auto) & ~erase``).

This module holds the numpy-only pack/unpack primitives plus the
``MaskPlanesSnapshot`` value type shared by the canvas, the MainWindow mask
push hook, and the HistoryManager MASK stack (values are
``.copy()``-duck-typed — the history mechanics are unchanged; plan 08-02
Task 2).

Qt-free at runtime (RESEARCH Pitfall 13-12): the QImage annotations resolve
lazily under ``from __future__ import annotations`` and the import is guarded
by ``TYPE_CHECKING``, so the worker/batch path (numpy-only) can import the
pack/unpack helpers without pulling Qt.

Security:
    - ``unpack_binary`` (T-08-02, tampering): the packed blob is untrusted
      once it crosses a persistence boundary (``.mas`` load, plan 08-04). The
      blob length is validated against the caller-declared ``(h, w)`` — a
      crafted short (or padded) blob raises ``ValueError`` instead of being
      silently mis-shaped into a wrong-dimension mask.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # Qt-free at runtime (worker path imports this module)
    from PySide6.QtGui import QImage


def pack_binary(arr: np.ndarray) -> np.ndarray:
    """Pack an ``(H, W)`` uint8 binary mask (0/255) to 1 bit per pixel.

    Returns a 1-D ``uint8`` array of ``ceil(H*W/8)`` bytes
    (RESEARCH §2.3 — ~H*W/8 bytes per page, the retention shape for the
    raw detected mask and the per-page plane slots). Any non-zero entry
    packs as a set bit, so 0/1 and 0/255 conventions both round-trip.
    """
    if arr.ndim != 2:
        raise ValueError(f"expected 2D binary mask, got {arr.ndim}D")
    if arr.dtype != np.uint8:
        raise ValueError(f"expected uint8 binary mask, got {arr.dtype}")
    return np.packbits(arr > 0)


def unpack_binary(packed: np.ndarray, h: int, w: int) -> np.ndarray:
    """Unpack a :func:`pack_binary` blob back to an ``(h, w)`` 0/255 ``uint8``.

    T-08-02 mitigation: the blob is sliced to exactly ``h*w`` bits and
    reshaped against the CALLER-DECLARED dims. A blob whose byte length does
    not equal ``ceil(h*w/8)`` — short (truncated) or long (padded/crafted) —
    raises ``ValueError`` rather than silently mis-shaping. Plan 08-04's
    load side cross-checks blob length against the container's meta dims
    BEFORE calling this; this guard is the in-depth backstop.
    """
    required = (h * w + 7) // 8
    if len(packed) != required:
        raise ValueError(
            f"packed mask blob length {len(packed)} does not match the "
            f"declared {h}x{w} dims (expected {required} bytes)"
        )
    bits = np.unpackbits(packed)[: h * w]
    return (bits.reshape(h, w) * np.uint8(255)).copy()


@dataclass
class MaskPlanesSnapshot:
    """An immutable-by-convention snapshot of the three mask planes.

    Fields:
        manual: the manual-stroke plane QImage (page-sized ARGB32-family;
            alpha > 0 == painted).
        erase: the erase-ledger plane QImage (RED marks — erased pixels,
            never CompositionMode_Clear; the ledger SUBTRACTS on recompose).
        auto_packed: the derived auto binary, ``pack_binary``-packed (1-D
            uint8), or ``None`` when the page has no auto content.

    ``copy()`` (Pitfall 2 discipline — the HistoryManager MASK stack and the
    MainWindow push hook rely on it, duck-typed like the Phase 1 QImage
    values) returns a new snapshot whose QImages and packed array are
    detached from the originals.
    """

    manual: "QImage"
    erase: "QImage"
    auto_packed: np.ndarray | None = None

    def copy(self) -> "MaskPlanesSnapshot":
        """Return a fully detached copy of all three planes."""
        return MaskPlanesSnapshot(
            manual=self.manual.copy(),
            erase=self.erase.copy(),
            auto_packed=self.auto_packed.copy() if self.auto_packed is not None else None,
        )

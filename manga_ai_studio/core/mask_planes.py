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

quick-260907-sni (F3/S1 history slimming): the snapshot stores the manual and
erase planes as 1-bit PACKED arrays (~H*W/8 bytes each) + the page ``dims``,
not as page-sized ARGB32 QImages (4HW each). The representation is LOSSLESS
for these planes because both are binary — alpha>0 == painted, and
``mask_editor.mask_to_numpy_binary`` already thresholds them — so one history
entry shrinks ~32x (~2 x 4HW + HW/8 -> 3 x HW/8 bytes; at 35 MP ~280 MB ->
~13 MB per entry, the difference between a ~1 GB and a tens-of-MB per-page
history).

Qt-free at runtime (RESEARCH Pitfall 13-12): every field is a numpy array or
a tuple, so the worker/batch path (numpy-only) can import the pack/unpack
helpers without pulling Qt.

Security:
    - ``unpack_binary`` (T-08-02, tampering): the packed blob is untrusted
      once it crosses a persistence boundary (``.mas`` load, plan 08-04). The
      blob length is validated against the caller-declared ``(h, w)`` — a
      crafted short (or padded) blob raises ``ValueError`` instead of being
      silently mis-shaped into a wrong-dimension mask. The snapshot restore
      path shares this guard (``mask_editor.packed_to_mask_qimage``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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

    Fields (quick-260907-sni packed representation):
        manual_packed: the manual-stroke plane as a 1-bit packed 1-D uint8
            array of ``ceil(h*w/8)`` bytes (alpha>0 == painted — lossless
            for the binary plane; ~HW/8 bytes vs 4HW ARGB32).
        erase_packed: the erase-ledger plane, packed the same way (RED marks
            — erased pixels, never CompositionMode_Clear; the ledger
            SUBTRACTS on recompose).
        auto_packed: the derived auto binary, ``pack_binary``-packed (1-D
            uint8), or ``None`` when the page has no auto content.
        dims: the ``(h, w)`` page dims the packed blobs were built from —
            the restore-side key for :func:`unpack_binary` (whose
            ceil(h*w/8) length check is the in-depth backstop, T-08-02).

    ``copy()`` (Pitfall 2 discipline — the HistoryManager MASK stack and the
    MainWindow push hook rely on it, duck-typed like the Phase 1 QImage
    values) returns a new snapshot whose packed arrays are detached from the
    originals.
    """

    manual_packed: np.ndarray
    erase_packed: np.ndarray
    auto_packed: np.ndarray | None = None
    dims: tuple[int, int] = (0, 0)

    def copy(self) -> "MaskPlanesSnapshot":
        """Return a fully detached copy of all three packed planes."""
        return MaskPlanesSnapshot(
            manual_packed=self.manual_packed.copy(),
            erase_packed=self.erase_packed.copy(),
            auto_packed=self.auto_packed.copy() if self.auto_packed is not None else None,
            dims=self.dims,
        )

"""Image output writer — adapted from PanelCleaner (GPL v3, D-12).

Source: ``pcleaner/image_export.py:save_optimized`` (PanelCleaner, GPL v3).
This module adapts that function for Manga AI Studio: it takes a numpy
``(H, W, 3)`` uint8 RGB array (the canonical result format produced by the
LaMa inpainting adapter and the canvas) instead of a ``Path | Image``, writes
it through PIL with format-specific optimization kwargs, and preserves the
original's mode + DPI when an ``original=`` source of the matching format is
supplied.

It also provides ``passthrough_original``, the D-03 empty-mask branch: when a
batch page has no detected text, the page is copied through unchanged via
``shutil.copy2`` rather than re-encoded through PIL (which risks quality loss
and metadata stripping per the Phase 2 RESEARCH "Don't Hand-Roll" note).

Thread-safety / dependency contract (RESEARCH "Architectural Responsibility
Map: Image output writing -> Core I/O"): this module imports ONLY stdlib +
numpy + Pillow — no Qt, no torch, no models — so it is safe to call from
a worker thread and unit-testable headless.

Licensing: Manga AI Studio is a derivative of PanelCleaner (GPL v3); this
adapted code is therefore GPL v3 and must carry that attribution in all
distributions.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image

# Map the lowercased output suffix to the PIL format constant. Trimmed from
# PanelCleaner image_export.py:18-29 to the Phase 1 open-dialog filter set
# (*.png *.jpg *.jpeg *.webp *.bmp) — tiff/tif/dib/jp2/ppm are dropped.
_SUFFIX_TO_FORMAT: dict[str, str] = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
}


def save_image_optimized(
    image_rgb: np.ndarray, path: Path, original: Path | None = None
) -> None:
    """Write a numpy ``(H, W, 3)`` uint8 RGB array to ``path`` via PIL.

    Format-specific kwargs come straight from PanelCleaner
    ``image_export.py:65-80``: PNG uses ``compress_level=9``; JPEG uses
    ``quality=95`` and ``progressive=True``; all formats set ``optimize=True``.

    When ``original`` is supplied AND its format matches the output suffix,
    the output's mode and DPI are taken from the original so metadata is
    carried over. A malformed / unreadable original is tolerated — the page
    is simply saved without metadata preservation (T-02-03 mitigation).

    :param image_rgb: ``(H, W, 3)`` uint8 RGB array.
    :param path: Destination path; the suffix selects the output format.
    :param original: Optional source path to read mode + DPI from.
    :raises ValueError: if ``image_rgb`` is not ``(H, W, 3)`` uint8.
    """
    # Validate input BEFORE any file is opened/written (mirrors
    # canvas.py:set_image_from_numpy input validation; T-02-01 boundary).
    if (
        image_rgb.ndim != 3
        or image_rgb.shape[2] != 3
        or image_rgb.dtype != np.uint8
    ):
        raise ValueError("expected (H,W,3) uint8 RGB")

    pil = Image.fromarray(image_rgb, mode="RGB")

    mode = None
    dpi = None
    if original is not None and _SUFFIX_TO_FORMAT.get(original.suffix.lower()):
        # T-02-03: a crafted original could carry malformed metadata; the
        # try/except degrades to saving without metadata preservation rather
        # than crashing the writer.
        try:
            with Image.open(original) as orig:
                if _SUFFIX_TO_FORMAT[original.suffix.lower()] == orig.format:
                    mode = orig.mode
                    dpi = orig.info.get("dpi")
        except (OSError, ValueError):
            pass

    if mode is not None:
        pil = pil.convert(mode)

    # Format-specific kwargs (PanelCleaner image_export.py:65-72).
    kwargs: dict = {"optimize": True}
    suf = path.suffix.lower()
    if suf == ".png":
        kwargs["compress_level"] = 9
    elif suf in (".jpg", ".jpeg"):
        kwargs["quality"] = 95
        kwargs["progressive"] = True

    if dpi is not None:
        kwargs["dpi"] = dpi

    path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(path, **kwargs)


def passthrough_original(original: Path, cleaned_dir: Path) -> Path:
    """Copy an unreadable-for-inpaint page through unchanged (D-03).

    Used by the batch loop when a page has no detected text: rather than
    decoding + re-encoding through PIL (quality loss, metadata stripping),
    the source bytes AND metadata are copied verbatim with ``shutil.copy2``.

    :param original: Source file path.
    :param cleaned_dir: Destination ``cleaned/`` directory (created if absent).
    :return: The destination path (``cleaned_dir / original.name``).
    """
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    dest = cleaned_dir / original.name
    # D-03: copy2 preserves bytes AND mtime AND metadata — do NOT re-encode.
    shutil.copy2(original, dest)
    return dest

"""Tests for the image output writer ``core/image_io.py`` (plan 02-01).

This is the Phase 2 PROJ-02 (Export cleaned raws) + FLOW-03 (D-03 empty-mask
passthrough) output-writer suite. ``save_image_optimized`` is the single
numpy -> PIL -> file write path reused by both the single-page Export dialog
(Plan 04) and the batch ``cleaned/`` write loop (Plan 03). It is adapted from
PanelCleaner ``pcleaner/image_export.py:save_optimized`` (GPL v3, D-12).

``passthrough_original`` is the D-03 empty-mask branch: when a batch page has
no detected text, its bytes + metadata are copied through unchanged via
``shutil.copy2`` (no re-encode through PIL, which would risk quality loss and
metadata stripping per RESEARCH "Don't Hand-Roll").

These tests are pure stdlib + numpy + PIL; they carry the ``unit`` marker and
require NO Qt and NO model weights (RESEARCH "Architectural Responsibility
Map: Image output writing -> Core I/O").
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from manga_ai_studio.core.image_io import passthrough_original, save_image_optimized


def _rgb_4x4() -> np.ndarray:
    """A 4x4x3 uint8 RGB test image (mirrors test_lama_adapter fixture shape)."""
    return np.full((4, 4, 3), 200, dtype=np.uint8)


@pytest.mark.unit
def test_save_png_kwargs(tmp_path: Path) -> None:
    """save_image_optimized writes a PNG when the suffix is .png.

    Re-opening the output reports format PNG.
    """
    out = tmp_path / "out.png"
    save_image_optimized(_rgb_4x4(), out)
    with Image.open(out) as im:
        assert im.format == "PNG"


@pytest.mark.unit
def test_save_jpg_kwargs(tmp_path: Path) -> None:
    """save_image_optimized writes a JPEG when the suffix is .jpg/.jpeg.

    Re-opening the output reports format JPEG.
    """
    out = tmp_path / "out.jpg"
    save_image_optimized(_rgb_4x4(), out)
    with Image.open(out) as im:
        assert im.format == "JPEG"


@pytest.mark.unit
def test_preserves_dpi_mode(tmp_path: Path) -> None:
    """When ``original=`` is a same-format image, DPI is preserved on save.

    The original PNG is written with dpi=(300, 300); the output re-opened
    reports the same dpi tuple (PIL normalizes dpi values to float).
    """
    orig = tmp_path / "orig.png"
    Image.fromarray(_rgb_4x4()).save(orig, dpi=(300, 300))
    out = tmp_path / "out.png"
    save_image_optimized(_rgb_4x4(), out, original=orig)
    with Image.open(out) as im:
        assert im.info.get("dpi") == (300.0, 300.0)


@pytest.mark.unit
def test_passthrough_copy2(tmp_path: Path) -> None:
    """passthrough_original copies bytes + metadata via shutil.copy2.

    The cleaned copy exists, has identical bytes (shutil.cmp True), and the
    same mtime as the source (copy2 preserves mtime).
    """
    src = tmp_path / "src.png"
    Image.fromarray(_rgb_4x4()).save(src)
    cleaned = tmp_path / "cleaned"
    dest = passthrough_original(src, cleaned)
    assert dest == cleaned / "src.png"
    assert (cleaned / "src.png").exists()
    assert shutil.cmp(src, cleaned / "src.png") is True
    assert os.stat(src).st_mtime == os.stat(cleaned / "src.png").st_mtime


@pytest.mark.unit
def test_rejects_non_rgb_input(tmp_path: Path) -> None:
    """save_image_optimized raises ValueError on non-(H,W,3) uint8 RGB input.

    A 2-D array, a 4-channel array, and a float64 array are all rejected
    before any file is written.
    """
    bad_inputs = [
        np.zeros((4, 4), dtype=np.uint8),  # 2-D, no channel axis
        np.zeros((4, 4, 4), dtype=np.uint8),  # 4 channels
        np.zeros((4, 4, 3), dtype=np.float64),  # wrong dtype
    ]
    for arr in bad_inputs:
        with pytest.raises(ValueError):
            save_image_optimized(arr, tmp_path / "bad.png")

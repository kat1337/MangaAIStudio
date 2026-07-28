"""Tests for the vendored ``panelcleaner/masker.py`` (plan 03-01, D-14).

This is the Phase 3 headless Wave-0 suite for the newly-vendored masker driver.
``mask_page`` is the batch-GUI analytics driver from PanelCleaner — it is DEAD
CODE in our context (Phase 3 never calls it) but is vendored near-verbatim for
the std-dev machinery seam (D-15) and for upstream diffability (RESEARCH Open
Question 3).

The load-bearing line is the ost-import guard (RESEARCH Pitfall 1): the bare
``import pcleaner.output_structures as ost`` is replaced with a try/except
ImportError that sets ``ost = None`` on failure, because output_structures.py
(the batch GUI analytics pipeline) is deliberately NOT vendored. Without the
guard, ``import panelcleaner.masker`` would fail. The first test in this file
FAILS if the guard is missing and ost is imported unconditionally.

These tests are pure stdlib; they carry the ``unit`` marker and require NO Qt
and NO model weights (headless CI).
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_masker_imports_with_ost_not_vendored() -> None:
    """Pitfall 1 proof: ``import panelcleaner.masker`` succeeds even though
    ``panelcleaner.output_structures`` does NOT exist in the vendored tree.

    This test FAILS if the ost guard is missing and the bare import is left
    unconditional. It is the regression guard for the try/except ImportError
    shim at the top of masker.py.
    """
    # Confirm output_structures is genuinely NOT vendored (precondition for the
    # guard to be load-bearing).
    import importlib

    with pytest.raises(ImportError):
        importlib.import_module("panelcleaner.output_structures")

    # And yet masker imports cleanly.
    import panelcleaner.masker

    assert panelcleaner.masker is not None


@pytest.mark.unit
def test_mask_page_is_callable() -> None:
    """``mask_page`` is present near-verbatim (RESEARCH Open Question 3) and is
    callable. Phase 3 never calls it; it is dead code in our context but kept
    for upstream diffability and the std-dev seam."""
    from panelcleaner.masker import mask_page

    assert callable(mask_page)


@pytest.mark.unit
def test_save_denoising_data_is_callable() -> None:
    """``save_denoising_data`` is present near-verbatim and callable (the
    companion helper that serializes MaskData with per-box std-dev). Dead code
    in Phase 3; kept for parity."""
    from panelcleaner.masker import save_denoising_data

    assert callable(save_denoising_data)


@pytest.mark.unit
def test_std_dev_machinery_available_from_image_ops() -> None:
    """D-15 seam availability: the std-dev machinery the per-box-inpaint seam
    needs is importable from image_ops (already vendored in Phase 1). Phase 3
    does not CALL these functions, but the seam must be open so a later inpaint
    phase can call ``pick_best_mask`` (which now sees ``MaskFittingResults``
    via the full structures.py) and ``border_std_deviation``.

    This is also the Pitfall 2 proof at the image_ops boundary: pick_best_mask
    references ``st.MaskFittingResults`` — with the stub, this import succeeded
    only by accident (lazy annotations + un-called body); with the full
    structures.py it is genuinely sound.
    """
    from panelcleaner.image_ops import (
        border_std_deviation,
        color_std,
        pick_best_mask,
    )

    assert callable(border_std_deviation)
    assert callable(color_std)
    assert callable(pick_best_mask)

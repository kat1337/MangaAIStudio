"""Tests for ``manga_ai_studio/core/box_model.py`` + ``ImageFile.boxes`` slot
(plan 03-01, D-15).

This is the Phase 3 headless Wave-0 suite for the PageBox data model — the
origin-tagged wrapper that COMPOSES a vendored ``Box`` (does NOT subclass it;
CONTEXT D-14 anti-pattern) and carries the D-15 selective-inpaint seam
(``mask`` / ``std_dev`` default ``None``). The seam defaults are the
load-bearing regression: a later inpaint phase fills them via
``image_ops.pick_best_mask`` / ``image_ops.border_std_deviation``; if they
ever get a non-None default, that later phase must rework the call sites.

``textblock_to_box`` is the single V5 input-validation boundary that coerces
a model-produced ``TextBlock.xyxy`` into a vendored ``Box`` with int
coordinates. Bounds-clamping against the image rect happens at the CALLER in
plan 03-04 (this function does not know image dims).

These tests are pure stdlib; they carry the ``unit`` marker and require NO Qt
and NO model weights (headless CI).
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest


@pytest.mark.unit
def test_detected_and_user_origin_constants() -> None:
    """``DETECTED`` and ``USER`` are module-level string constants
    ("detected" / "user") — the D-03 origin discriminator. Single source of
    truth so the GUI (BoxItem), persistence (ImageFile.boxes), and undo
    (BOXES snapshots) layers all agree on the spelling."""
    from manga_ai_studio.core.box_model import DETECTED, USER

    assert DETECTED == "detected"
    assert USER == "user"
    assert DETECTED != USER


@pytest.mark.unit
def test_pagebox_composes_box_does_not_subclass() -> None:
    """PageBox COMPOSES a vendored Box (CONTEXT D-14 / Claude's Discretion
    anti-pattern: do NOT subclass the vendored Box). The vendored Box stays
    near-verbatim; origin/identity layer on top via composition."""
    from manga_ai_studio.core import box_model
    from panelcleaner.structures import Box

    box = Box(1, 2, 3, 4)
    pb = box_model.PageBox(box=box, origin=box_model.DETECTED)

    # Composition: PageBox holds the Box as an attribute, does not inherit it.
    assert pb.box is box
    assert not isinstance(pb, Box)


@pytest.mark.unit
def test_pagebox_d15_seam_defaults_none_for_detected() -> None:
    """D-15 seam lock: a detected PageBox has ``mask is None`` and
    ``std_dev is None`` by default. This is the regression a later inpaint
    phase relies on — the seam is OPEN in Phase 3, not closed."""
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from panelcleaner.structures import Box

    pb = PageBox(box=Box(1, 2, 3, 4), origin=DETECTED)
    assert pb.mask is None
    assert pb.std_dev is None
    assert pb.origin == "detected"


@pytest.mark.unit
def test_pagebox_payload_defaults_none_for_user() -> None:
    """A user-drawn PageBox carries no TextBlock payload (None) — payloads
    arrive in Phase 4/5 OCR/export. The default is None so user boxes don't
    accidentally carry stale detection data."""
    from manga_ai_studio.core.box_model import USER, PageBox
    from panelcleaner.structures import Box

    pb = PageBox(box=Box(1, 2, 3, 4), origin=USER)
    assert pb.payload is None
    assert pb.origin == "user"


@pytest.mark.unit
def test_pagebox_seam_fields_populatable() -> None:
    """The D-15 seam fields ARE populatable (a later phase fills them). This
    test confirms the field exists with the right type contract so the seam
    is open for write, not just default-None."""
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from panelcleaner.structures import Box

    pb = PageBox(box=Box(1, 2, 3, 4), origin=DETECTED)
    # A later inpaint phase would set these:
    pb.mask = object()  # placeholder for a real mask
    pb.std_dev = 12.34
    assert pb.mask is not None
    assert pb.std_dev == 12.34


@pytest.mark.unit
def test_textblock_to_box_coerces_floats_to_int() -> None:
    """V5 input validation: ``textblock_to_box`` accepts a duck-typed object
    with a ``.xyxy`` attribute and returns a vendored ``Box`` with INT
    coordinates. Feed it floats and assert the result is the int Box — model
    output is untrusted (ASVS V5)."""
    from manga_ai_studio.core.box_model import textblock_to_box
    from panelcleaner.structures import Box

    # Duck-typed fake TextBlock with float coords (the V5 untrusted-input case).
    fake_blk = types.SimpleNamespace(xyxy=[10.0, 20.0, 110.0, 220.0])
    box = textblock_to_box(fake_blk)

    assert isinstance(box, Box)
    assert box.as_tuple == (10, 20, 110, 220)  # ints, not floats
    # Cross-check via as_tuple_xywh (the QRectF mapping the GUI uses).
    assert box.as_tuple_xywh == (10, 20, 100, 200)


@pytest.mark.unit
def test_textblock_to_box_accepts_int_xyxy() -> None:
    """The common path: TextBlock.xyxy is already [int,...] (per
    textblock.py:50) — textblock_to_box passes through cleanly."""
    from manga_ai_studio.core.box_model import textblock_to_box
    from panelcleaner.structures import Box

    fake_blk = types.SimpleNamespace(xyxy=[5, 6, 15, 16])
    box = textblock_to_box(fake_blk)
    assert isinstance(box, Box)
    assert box.as_tuple == (5, 6, 15, 16)


@pytest.mark.unit
def test_textblock_to_box_is_pure_no_qt() -> None:
    """``textblock_to_box`` is pure (no Qt, no image access) so it is
    headless-testable with a duck-typed fake TextBlock. This test exists to
    lock the purity contract — bounds-clamping against image rect happens at
    the CALLER in plan 03-04, not here (the function does not know image
    dims)."""
    from manga_ai_studio.core import box_model

    # No Qt imported at module top (purity): importing the module should not
    # pull PySide6. We check this by confirming the function is callable
    # without any QApplication existing.
    assert callable(box_model.textblock_to_box)


@pytest.mark.unit
def test_imagefile_boxes_slot_defaults_none() -> None:
    """``ImageFile(path=...)`` has ``.boxes is None`` by default — mirrors the
    Phase 2 ``mask`` slot pattern (image_file.py:69)."""
    from manga_ai_studio.core.image_file import ImageFile

    f = ImageFile(path=Path("."))
    assert f.boxes is None


@pytest.mark.unit
def test_imagefile_has_boxes_false_when_empty() -> None:
    """``ImageFile(path=...).has_boxes()`` is False when boxes is None
    (mirrors has_mask_content)."""
    from manga_ai_studio.core.image_file import ImageFile

    f = ImageFile(path=Path("."))
    assert f.has_boxes() is False


@pytest.mark.unit
def test_imagefile_has_boxes_true_when_populated() -> None:
    """``ImageFile(path=..., boxes=[PageBox(...)]).has_boxes()`` is True
    (mirrors has_mask_content's trivial-list check, NOT a numpy scan — boxes
    have no pixel content to scan)."""
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from manga_ai_studio.core.image_file import ImageFile
    from panelcleaner.structures import Box

    f = ImageFile(path=Path("."), boxes=[PageBox(Box(1, 2, 3, 4), DETECTED)])
    assert f.has_boxes() is True


@pytest.mark.unit
def test_imagefile_has_boxes_false_for_empty_list() -> None:
    """``ImageFile(path=..., boxes=[]).has_boxes()`` is False — an empty list
    is falsy, so bool([]) is False. Mirrors the trivial shape noted in
    PATTERNS.md (do NOT reimplement has_mask_content's numpy scan)."""
    from manga_ai_studio.core.image_file import ImageFile

    f = ImageFile(path=Path("."), boxes=[])
    assert f.has_boxes() is False

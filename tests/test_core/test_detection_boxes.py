"""Tests for ``manga_ai_studio/core/detection_boxes.py`` (plan 08-03).

The detection->mask seam core: the headless extraction of the V5 box-build
loop (plan 08-03 Task 2 — ``build_detected_pageboxes``, extracted from
``MainWindow._build_detected_boxes`` Step 2, main_window.py:4085-4121) and
the pure mask-derivation primitives (plan 08-03 Task 3 —
``derive_page_mask_state`` / ``compose_auto_binary`` / ``dilate_auto_mask``,
the vendored masker.py:63-104 call sequence adapted per RESEARCH §1.4).

Both consumers — the GUI seam (plan 08-07) and the batch loop (plan 08-09) —
call THESE functions; nothing here imports Qt, torch, or the GUI (the module
is headless by construction, locked by test below).

Synthetic pages: uniform PIL fill + ImageDraw rectangles for text-like
strokes and contrast ticks; heatmaps as numpy (H, W) uint8 arrays — the exact
shapes the detection worker returns (``_run_detection_task`` -> ``{"mask":
mask_refined, "blocks": blk_list}``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

import panelcleaner.config as cfg
import panelcleaner.structures as st

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox


def _blk(x1, y1, x2, y2):
    """A TextBlock-like fake (any object with a ``.xyxy`` of length 4)."""
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


# ===========================================================================
# Task 2 — build_detected_pageboxes (headless extraction of the V5 loop)
# ===========================================================================
@pytest.mark.unit
def test_build_detected_pageboxes_clamps_drops_and_tags_detected() -> None:
    """In-bounds entries pass with int-coerced coords; out-of-bounds entries
    are per-edge clamped to [0, img_w]/[0, img_h]; zero-area survivors of the
    clamp are dropped; every kept box is origin DETECTED with its payload
    preserved untouched (the V5 contract, main_window.py:4085-4121)."""
    from manga_ai_studio.core.detection_boxes import build_detected_pageboxes

    in_bounds = _blk(10.0, 10.0, 40.0, 30.0)  # floats -> int coercion
    out_of_bounds = _blk(-5, 20, 50, 45)  # negative x1, x2 beyond img_w
    inverted = _blk(30, 5, 28, 20)  # x2 < x1 pre-clamp
    zero_area_post_clamp = _blk(48, 10, 55, 30)  # clamps to x1 == x2 == img_w

    result = build_detected_pageboxes(
        [in_bounds, out_of_bounds, inverted, zero_area_post_clamp], 45, 50
    )

    assert [pb.box.as_tuple for pb in result] == [(10, 10, 40, 30), (0, 20, 45, 45)]
    assert all(pb.origin == DETECTED for pb in result)
    assert all(isinstance(pb.box, st.Box) for pb in result)
    # The payload is the TextBlock itself, preserved untouched (Phase 4/5
    # OCR + export consume it).
    assert result[0].payload is in_bounds
    assert result[1].payload is out_of_bounds


@pytest.mark.unit
def test_build_detected_pageboxes_style_follows_default_family() -> None:
    """``default_family=None`` -> style None (the renderer's own defaults
    apply); a family -> a default TextStyle on EVERY kept box (the G-07-3
    contract carried over from the GUI loop)."""
    from manga_ai_studio.core.detection_boxes import build_detected_pageboxes

    blks = [_blk(5, 5, 25, 20), _blk(-10, -10, 0, 0)]  # second clamps to zero area

    no_style = build_detected_pageboxes(blks, 100, 80)
    assert len(no_style) == 1
    assert no_style[0].style is None

    with_style = build_detected_pageboxes(blks, 100, 80, default_family="Arial")
    assert len(with_style) == 1
    assert with_style[0].style is not None
    assert with_style[0].style.font_family == "Arial"


@pytest.mark.unit
def test_detection_boxes_module_is_headless() -> None:
    """Source-level purity lock: the module imports nothing from Qt, torch,
    or the GUI layer — the batch worker (plan 08-09) imports it off-thread."""
    source = Path("manga_ai_studio/core/detection_boxes.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("PySide6", "QtWidgets", "QtCore", "QtGui", "torch", "gui."):
        assert forbidden not in source, f"detection_boxes.py must not reference {forbidden}"

    import manga_ai_studio.core.detection_boxes  # noqa: F401

    assert "manga_ai_studio.gui" not in sys.modules

"""Bake compositor tests (plan 07-01 Task 1) — the ``bake_typeset_page``
D-04 content rule (translation else recognized else nothing), the Pitfall 2
detachment discipline, the D-03 sidecar placement, and the PROJ-02 writer
contract (``save_image_optimized``: PNG compress_level=9 + DPI preserved).

The bake is the disk twin of the canvas overlay — both go through the shared
``gui/text_renderer`` functions (D-01 single visual truth).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from manga_ai_studio.core.box_model import DETECTED, PageBox  # noqa: E402
from manga_ai_studio.core.image_io import save_image_optimized  # noqa: E402
from manga_ai_studio.core.ocr_export import default_typeset_path  # noqa: E402
from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from manga_ai_studio.gui.text_renderer import bake_typeset_page  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

# The default fill (UI-SPEC A1) as an RGB tuple — opaque (D-01).
_FILL_RGB = (232, 232, 234)
# A deterministic fixed-size style for pixel probes (no auto-fit variability).
_FIXED_STYLE = TextStyle(
    font_size_px=8.0, auto_fit=False, align_h="left", align_v="top"
)


def _page(size: int = 16, color=(30, 40, 50)) -> np.ndarray:
    """A solid-color (H, W, 3) uint8 page."""
    return np.full((size, size, 3), color, dtype=np.uint8)


def _box_with_text(
    recognized: str = "", translation: str = "", style: TextStyle | None = None
) -> PageBox:
    pb = PageBox(
        box=Box(2, 2, 12, 12), origin=DETECTED, style=style or _FIXED_STYLE
    )
    if recognized:
        pb.set_recognized_text(recognized)
    if translation:
        pb.set_translation(translation)
    return pb


# ---------------------------------------------------------------------------
# Test 6 — bake content (D-04 current-focus rule)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bake_renders_translation_when_present(qapp) -> None:
    """A box with BOTH texts bakes the translation (D-04 current-focus rule)."""
    page = _page()
    trans_box = _box_with_text(recognized="RECOG", translation="TRANS")
    baked = bake_typeset_page(page, [trans_box])

    # The translation was used: identical pixels to a recognized-only render
    # of the same string ("TRANS").
    recog_only = bake_typeset_page(page, [_box_with_text(recognized="TRANS")])
    assert np.array_equal(baked, recog_only), (
        "the bake must render the translation, not the recognized text"
    )
    # The text pixels landed inside the box rect; the page outside is intact.
    region = baked[2:12, 2:12]
    assert region is not None
    outside = np.concatenate(
        [baked[:2].reshape(-1, 3), baked[12:].reshape(-1, 3),
         baked[2:12, :2].reshape(-1, 3), baked[2:12, 12:].reshape(-1, 3)]
    )
    assert (outside == page[:2].reshape(-1, 3)[0]).all(), (
        "pixels outside the box must keep the source color (no chrome)"
    )


@pytest.mark.unit
def test_bake_renders_recognized_when_no_translation(qapp) -> None:
    """A box with recognized text only bakes the recognized text (D-04)."""
    page = _page()
    baked = bake_typeset_page(page, [_box_with_text(recognized="TRANS")])
    # Opaque fill pixels (the default #e8e8ea) exist inside the box rect.
    region = baked[2:12, 2:12]
    assert ((region == _FILL_RGB).all(axis=2)).any(), (
        "opaque fill-colored glyph pixels must exist inside the box rect"
    )
    # The page changed inside the box...
    assert not np.array_equal(region, page[2:12, 2:12])
    # ...and stayed identical outside it.
    assert np.array_equal(baked[:2], page[:2])
    assert np.array_equal(baked[12:], page[12:])


@pytest.mark.unit
def test_bake_leaves_page_unchanged_when_no_box_has_text(qapp) -> None:
    """Boxes with neither translation nor recognized text bake NOTHING (D-04)."""
    page = _page()
    empty_box = _box_with_text()  # payload None — no text at all
    baked = bake_typeset_page(page, [empty_box])
    assert np.array_equal(baked, page), (
        "an empty box must leave the baked page byte-identical to the source"
    )


@pytest.mark.unit
def test_bake_result_does_not_share_memory_with_input(qapp) -> None:
    """The baked result is a detached copy — never aliases the input (Pitfall 2)."""
    page = _page()
    baked = bake_typeset_page(page, [_box_with_text(recognized="TRANS")])
    assert not np.shares_memory(baked, page)
    # Mutating the result must not touch the input page.
    baked[:] = 0
    assert not np.array_equal(page, baked)


# ---------------------------------------------------------------------------
# Test 7 — D-03 placement + the PROJ-02 writer contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_typeset_path_pristine_sidecar(tmp_path) -> None:
    """Pristine page -> {stem}_typeset.png NEXT TO the source (D-03 / D-22 mirror)."""
    page_path = tmp_path / "page_01.png"
    dest = default_typeset_path(page_path, geometry_altered=False)
    assert dest.name == "page_01_typeset.png"
    assert dest.parent == tmp_path


@pytest.mark.unit
def test_default_typeset_path_geometry_altered_cleaned(tmp_path) -> None:
    """Geometry-altered page -> {stem}_typeset.png inside cleaned/ (created if missing)."""
    page_path = tmp_path / "page_01.png"
    dest = default_typeset_path(page_path, geometry_altered=True)
    assert dest.name == "page_01_typeset.png"
    assert dest.parent == tmp_path / "cleaned"


@pytest.mark.unit
def test_writer_contract_png_compress_level_9_and_dpi(tmp_path, monkeypatch) -> None:
    """save_image_optimized writes PNG at compress_level=9 with DPI preserved
    (within the Phase 2 one-DPI tolerance) from the source page."""
    src = tmp_path / "src.png"
    PILImage.new("RGB", (8, 8), color=(10, 20, 30)).save(src, dpi=(300, 300))

    captured: dict = {}
    real_save = PILImage.Image.save

    def _capture_save(self, *args, **kwargs):
        captured.update(kwargs)
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(PILImage.Image, "save", _capture_save)

    arr = _page(8, color=(10, 20, 30))
    dest = tmp_path / "out.png"
    save_image_optimized(arr, dest, original=src)

    assert captured.get("compress_level") == 9, "PNG must be written at compress_level=9"
    with PILImage.open(dest) as im:
        dpi = im.info.get("dpi")
    assert dpi is not None, "the output must carry the source DPI"
    assert abs(dpi[0] - 300) <= 1 and abs(dpi[1] - 300) <= 1, (
        "DPI must be preserved within the Phase 2 one-unit tolerance"
    )


@pytest.mark.unit
def test_placement_writes_sidecar_through_writer(tmp_path) -> None:
    """The full placement rule: bake -> default_typeset_path -> save_image_optimized
    lands {stem}_typeset.png in cleaned/ (created) for a geometry-altered page."""
    src_dir = tmp_path / "chapter"
    src_dir.mkdir()
    page_path = src_dir / "page_01.png"
    PILImage.new("RGB", (12, 12), color=(30, 40, 50)).save(page_path)

    dest = default_typeset_path(page_path, geometry_altered=True)
    page = _page(12)
    baked = bake_typeset_page(page, [_box_with_text(recognized="TRANS")])
    save_image_optimized(baked, dest, original=page_path)

    assert dest.is_file(), "the cleaned/ sidecar must exist after the write"
    with PILImage.open(dest) as im:
        assert im.size == (12, 12)

"""Tests for the ``.mas`` project container + PageBox mapping (plan 05-01).

Wave 1 of PROJ-01 (Save full page state as a ``.mas`` project file and
reopen to resume): ``core/project_io.py`` is the headless serialization core
— the LZMA2 (FORMAT_XZ) page-file container (D-04), the PageBox<->JSON
mapping (D-03/D-17 with the D-15 seam), and untrusted-file validation
(T-05-01 / T-05-02).

These tests are pure stdlib + numpy + PIL; they carry the ``unit`` marker
and require NO Qt and NO model weights (the module contract mirrors
``core/image_io.py`` — worker-safe, headless-testable).
"""

from __future__ import annotations

import json
import os
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from manga_ai_studio.core.box_model import PageBox, USER
from manga_ai_studio.core.project_io import (
    _MAGIC,
    ProjectFormatError,
    build_page_entries,
    json_to_pagebox,
    load_page_file,
    load_project,
    pagebox_to_json,
    parse_page_entries,
    save_page_file,
    save_project,
)
from manga_ai_studio.core.text_style import TextStyle
from panelcleaner.comic_text_detector.utils.textblock import TextBlock
from panelcleaner.structures import Box


@pytest.mark.unit
def test_page_file_round_trip(tmp_path: Path) -> None:
    """save_page_file -> load_page_file returns entries byte-for-byte.

    meta.json / original.json are UTF-8 JSON; image.png and mask.bin carry
    non-trivial binary payloads (mask.bin = 64 KiB of urandom) that must
    survive the LZMA2 round-trip exactly.
    """
    entries = {
        "meta.json": json.dumps(
            {"version": 1, "img": {"w": 800, "h": 1200}, "boxes": []}
        ).encode("utf-8"),
        "image.png": b"\x89PNG\r\n\x1a\n" + os.urandom(4096),
        "mask.bin": os.urandom(65536),
        "original.json": json.dumps(
            {"path": "page_001.png", "sha256": "ab" * 32}
        ).encode("utf-8"),
    }
    page_file = tmp_path / "page_001.mas"
    save_page_file(page_file, entries)
    assert load_page_file(page_file) == entries


@pytest.mark.unit
def test_pagebox_json_round_trip() -> None:
    """A full PageBox (multi-line text, 2 line quads, all peer fields)
    survives pagebox_to_json -> json_to_pagebox with equal fields.
    """
    lines = [
        [[12, 24], [190, 24], [190, 54], [12, 54]],
        [[12, 60], [190, 60], [190, 90], [12, 90]],
    ]
    payload = TextBlock(
        [10, 20, 200, 300],
        lines=lines,
        vertical=True,
        language="ja",
        font_size=14,
        text="First line\nSecond line",
        translation="Line one\nLine two",
    )
    pb = PageBox(
        box=Box(10, 20, 200, 300),
        origin=USER,
        payload=payload,
        edited=True,
        bubble_no=3,
        manual_override=True,
    )

    out = json_to_pagebox(pagebox_to_json(pb))
    assert out.box.as_tuple == (10, 20, 200, 300)
    assert out.origin == USER
    assert out.edited is True
    assert out.bubble_no == 3
    assert out.manual_override is True
    p = out.payload
    assert p is not None
    assert p.text == "First line\nSecond line"
    assert p.translation == "Line one\nLine two"
    assert p.vertical is True
    assert p.language == "ja"
    assert p.font_size == 14
    assert p.xyxy == [10, 20, 200, 300]
    assert len(p.lines) == 2
    for expected, actual in zip(payload.lines, p.lines):
        assert actual == expected  # element-wise equality
    # D-15 seam: mask/std_dev are never serialized, always None on load.
    assert out.mask is None
    assert out.std_dev is None


@pytest.mark.unit
def test_style_field_round_trip() -> None:
    """A non-default style survives pagebox_to_json -> json_to_pagebox (D-07).

    Field-wise equality (never identity): the restored style equals the
    source field-by-field — font family/flags/size, alignment, the effect
    dicts — and is a NEW instance (the .mas load never aliases a live style,
    Pitfall 8 discipline).
    """
    style = TextStyle(
        font_family="Yu Gothic UI",
        bold=True,
        italic=False,
        font_size_px=22.0,
        auto_fit=False,
        color="#ff6b6b",
        align_h="right",
        align_v="top",
        vertical=True,
        outline={"enabled": True, "color": "#111111", "width_px": 3.0},
        glow={"enabled": True, "color": "#ffff00", "radius_px": 8.0, "opacity": 0.5},
        shadow={
            "enabled": True, "color": "#000000", "radius_px": 5.0,
            "dx": 3.0, "dy": 4.0, "opacity": 0.7,
        },
    )
    pb = PageBox(
        box=Box(10, 20, 200, 300),
        origin=USER,
        payload=None,
        edited=True,
        bubble_no=3,
        manual_override=True,
        style=style,
    )

    out = json_to_pagebox(pagebox_to_json(pb))
    assert out.style is not None
    assert out.style is not style  # a fresh instance, never identity
    assert out.style.font_family == "Yu Gothic UI"
    assert out.style.bold is True
    assert out.style.italic is False
    assert out.style.font_size_px == 22.0
    assert out.style.auto_fit is False
    assert out.style.color == "#ff6b6b"
    assert out.style.align_h == "right"
    assert out.style.align_v == "top"
    assert out.style.vertical is True
    assert out.style.outline == {"enabled": True, "color": "#111111", "width_px": 3.0}
    assert out.style.glow == {
        "enabled": True, "color": "#ffff00", "radius_px": 8.0, "opacity": 0.5,
    }
    assert out.style.shadow == {
        "enabled": True, "color": "#000000", "radius_px": 5.0,
        "dx": 3.0, "dy": 4.0, "opacity": 0.7,
    }


@pytest.mark.unit
def test_legacy_mas_without_style_loads_with_defaults() -> None:
    """A Phase 5-shape pagebox dict (NO style key) loads with the default
    style (Pitfall 8).

    Old .mas files predate the D-07 style field: "style" is an OPTIONAL load
    key — absent -> ``TextStyle()`` defaults, never ProjectFormatError.
    """
    legacy = {
        "box": [0, 0, 100, 40],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    out = json_to_pagebox(legacy)
    assert out.style == TextStyle()


@pytest.mark.unit
def test_style_none_round_trip() -> None:
    """A style-None box writes "style": None and reloads with the DEFAULT
    style (json null round-trip).

    The projection is explicit about a missing style, and the load side
    treats it exactly like an absent key (Pitfall 8).
    """
    pb = PageBox(box=Box(0, 0, 10, 10), origin=USER, payload=None, style=None)
    d = pagebox_to_json(pb)
    assert d["style"] is None
    out = json_to_pagebox(d)
    assert out.style == TextStyle()


@pytest.mark.unit
def test_style_v5_clamped_on_load() -> None:
    """Crafted style values clamp on load — never reach the renderer raw
    (T-07-09, the V5 coercion boundary).

    width_px 300 -> 256, opacity 1.5 -> 1.0 (the ``TextStyle.from_dict``
    bounds); font_size_px 300 stays (within the 1..1024 range).
    """
    crafted = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
        "style": {
            "font_size_px": 300,
            "auto_fit": False,
            "outline": {"enabled": True, "color": "#0b0b0e", "width_px": 300},
            "glow": {"enabled": True, "color": "#ffffff", "radius_px": 4.0, "opacity": 1.5},
        },
    }
    out = json_to_pagebox(crafted)
    s = out.style
    assert s is not None
    assert s.font_size_px == 300.0
    assert s.outline["width_px"] == 256.0
    assert s.glow["opacity"] == 1.0


@pytest.mark.unit
def test_required_keys_unchanged() -> None:
    """The required-key validation is untouched: a pagebox dict missing
    "box" still raises ProjectFormatError (style never joins the required
    key set — it stays optional, Pitfall 8).
    """
    with pytest.raises(ProjectFormatError):
        json_to_pagebox(
            {
                "origin": USER,
                "edited": False,
                "bubble_no": None,
                "manual_override": False,
                "payload": None,
            }
        )


@pytest.mark.unit
def test_bad_magic_rejected(tmp_path: Path) -> None:
    """A file with a wrong 4-byte prefix raises ProjectFormatError."""
    page_file = tmp_path / "bad.mas"
    page_file.write_bytes(b"XXXX" + os.urandom(64))
    with pytest.raises(ProjectFormatError):
        load_page_file(page_file)


@pytest.mark.unit
def test_malformed_entry_table_rejected(tmp_path: Path) -> None:
    """Every malformed-entry case raises ProjectFormatError — never a raw
    struct.error / IndexError escapes load_page_file (T-05-01).
    """
    # 1. Truncated header: magic present but the version/count uint32 pair
    #    (8 bytes after the magic) is cut off.
    page_file = tmp_path / "truncated.mas"
    page_file.write_bytes(_MAGIC + b"\x01\x00")
    with pytest.raises(ProjectFormatError):
        load_page_file(page_file)

    # 2. Entry count claiming more entries than the blob holds.
    page_file = tmp_path / "overcount.mas"
    page_file.write_bytes(_MAGIC + struct.pack("<II", 1, 5))
    with pytest.raises(ProjectFormatError):
        load_page_file(page_file)

    # 3. Garbage length prefix that overruns the remaining bytes.
    page_file = tmp_path / "overrun.mas"
    page_file.write_bytes(
        _MAGIC + struct.pack("<II", 1, 1) + struct.pack("<HQ", 100, 1000) + b"\x00" * 5
    )
    with pytest.raises(ProjectFormatError):
        load_page_file(page_file)


@pytest.mark.unit
def test_manifest_round_trip(tmp_path: Path) -> None:
    """save_project -> load_project preserves page order + names (UTF-8).

    The chapter name is non-ASCII (``章 1``) — the manifest must be written
    and read as UTF-8 so it round-trips exactly.
    """
    project_dir = tmp_path / "chapter-01.mas-project"
    manifest_path = save_project(
        project_dir,
        "\u7ae0 1",
        [("page_001", {"meta.json": b"{}"}), ("page_002", {"meta.json": b"{}"})],
    )
    manifest = load_project(manifest_path)
    assert manifest["name"] == "\u7ae0 1"
    assert [p["name"] for p in manifest["pages"]] == ["page_001", "page_002"]
    assert [p["file"] for p in manifest["pages"]] == [
        "page_001.mas",
        "page_002.mas",
    ]
    # The manifest file itself is UTF-8 (not ASCII-escaped).
    assert "\u7ae0" in manifest_path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_non_destructive_overwrite(tmp_path: Path) -> None:
    """Re-saving a project replaces only owned files (D-02).

    A foreign ``notes.txt`` sitting next to the project files must survive
    the re-save byte-for-byte while the owned ``manifest.json`` + ``.mas``
    files are rewritten.
    """
    project_dir = tmp_path / "chapter-01.mas-project"
    save_project(project_dir, "ch1", [("page_001", {"meta.json": b"{a:1}"})])
    first_mas = (project_dir / "page_001.mas").read_bytes()
    foreign = project_dir / "notes.txt"
    foreign.write_text("do not delete", encoding="utf-8")

    save_project(project_dir, "ch1", [("page_001", {"meta.json": b"{b:2}"})])

    assert foreign.read_text(encoding="utf-8") == "do not delete"
    assert (project_dir / "page_001.mas").read_bytes() != first_mas
    assert (project_dir / "page_001.mas").exists()
    assert (project_dir / "manifest.json").exists()


@pytest.mark.unit
def test_save_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mid-save failure never corrupts the existing project files.

    Held-out atomic backstop: ``os.replace`` is made to fail on the third
    write (manifest.json + the first page succeed; the second page's write
    is interrupted). Every pre-existing file must remain byte-identical —
    the temp-file scheme never corrupts the target.
    """
    from manga_ai_studio.core import project_io

    project_dir = tmp_path / "chapter-01.mas-project"
    entries_a = {"meta.json": json.dumps({"v": 1}).encode("utf-8")}
    entries_b = {"meta.json": json.dumps({"v": 2}).encode("utf-8")}
    save_project(
        project_dir, "ch1", [("page_a", entries_a), ("page_b", entries_b)]
    )
    before = {p.name: p.read_bytes() for p in sorted(project_dir.iterdir())}

    real_replace = os.replace
    calls = {"n": 0}

    def interrupted_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:  # page_b.mas replace — simulated mid-write failure
            raise OSError("simulated interrupted write")
        return real_replace(src, dst)

    monkeypatch.setattr(project_io.os, "replace", interrupted_replace)

    with pytest.raises(OSError):
        save_project(
            project_dir, "ch1", [("page_a", entries_a), ("page_b", entries_b)]
        )

    after = {p.name: p.read_bytes() for p in sorted(project_dir.iterdir())}
    assert after == before


@pytest.mark.unit
def test_page_entries_round_trip(tmp_path: Path) -> None:
    """build_page_entries -> save -> load -> parse_page_entries round-trips
    the page projection (image dims, mask reshape, original ref).
    """
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    mask = np.full((20, 30), 255, dtype=np.uint8)
    orig = tmp_path / "page_001.png"
    entries = build_page_entries(
        {
            "boxes": [],
            "image_rgb": image,
            "mask_bin": mask,
            "geometry_altered": True,
            "original_path": orig,
            "original_sha256": "ab" * 32,
        }
    )
    page_file = tmp_path / "page_001.mas"
    save_page_file(page_file, entries)
    parsed = parse_page_entries(load_page_file(page_file))

    assert parsed["meta"]["img"] == {"w": 30, "h": 20}
    assert parsed["meta"]["mask"] == {"h": 20, "w": 30}
    assert parsed["meta"]["geometry_altered"] is True
    assert parsed["meta"]["original"] == {
        "path": str(orig),
        "sha256": "ab" * 32,
    }
    assert parsed["original"] == {"path": str(orig), "sha256": "ab" * 32}
    assert parsed["mask"] is not None
    assert parsed["mask"].shape == (20, 30)
    assert parsed["mask"].dtype == np.uint8
    assert parsed["mask"][5, 5] == 255
    with Image.open(BytesIO(parsed["image_png"])) as im:
        assert im.size == (30, 20)
        assert im.format == "PNG"


@pytest.mark.unit
def test_image_file_flags_default() -> None:
    """ImageFile defaults: original_verified False, geometry_altered False."""
    from manga_ai_studio.core.image_file import ImageFile

    image_file = ImageFile(path=Path("page_001.png"))
    assert image_file.original_verified is False
    assert image_file.geometry_altered is False


@pytest.mark.unit
def test_save_image_bytes_round_trip() -> None:
    """save_image_bytes encodes PNG bytes that decode back to the same dims."""
    from manga_ai_studio.core.image_io import save_image_bytes

    arr = np.full((7, 9, 3), 128, dtype=np.uint8)
    data = save_image_bytes(arr)
    with Image.open(BytesIO(data)) as im:
        assert im.size == (9, 7)  # (w, h) — dims preserved
        assert im.format == "PNG"


@pytest.mark.unit
def test_original_checksum_rule(tmp_path: Path) -> None:
    """D-06: verify_original is True only on resolve + suffix + sha256 match.

    All four sub-cases: matching checksum -> True; wrong checksum at the
    same path -> False; missing path -> False; an existing file with a
    non-image suffix -> False (T-05-03 — the ref never opens arbitrary
    files).
    """
    from manga_ai_studio.core.project_io import sha256_file, verify_original

    img = tmp_path / "page_001.png"
    Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8)).save(img)
    digest = sha256_file(img)

    assert verify_original(str(img), digest) is True
    assert verify_original(str(img), "0" * 64) is False
    assert verify_original(str(tmp_path / "gone.png"), digest) is False

    txt = tmp_path / "note.txt"
    txt.write_text("not an image", encoding="utf-8")
    assert verify_original(str(txt), sha256_file(txt)) is False


@pytest.mark.unit
def test_sibling_manifest_detection(tmp_path: Path) -> None:
    """D-09: sibling manifest found / not found / corrupt.

    A valid sibling manifest.json next to a page .mas is returned; with no
    sibling the answer is None; a sibling that exists but is malformed
    raises ProjectFormatError (never silently opens the page standalone).
    """
    from manga_ai_studio.core.project_io import find_sibling_manifest

    page = tmp_path / "page_001.mas"
    save_page_file(page, {"meta.json": b"{}"})

    # no sibling manifest -> None
    assert find_sibling_manifest(page) is None

    # valid sibling manifest -> returned
    manifest_path = save_project(tmp_path, "ch1", [("page_001", {"meta.json": b"{}"})])
    assert find_sibling_manifest(page) == manifest_path

    # sibling present but malformed -> ProjectFormatError
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ProjectFormatError):
        find_sibling_manifest(page)


@pytest.mark.unit
def test_d15_seam_preserved() -> None:
    """D-15 seam: mask/std_dev are never serialized, always None on load.

    A PageBox with mask/std_dev set to non-None objects must serialize
    WITHOUT those keys in the dict, and json_to_pagebox must yield None for
    both.
    """
    pb = PageBox(box=Box(0, 0, 10, 10), origin=USER, mask=object(), std_dev=0.5)
    d = pagebox_to_json(pb)
    assert "mask" not in d
    assert "std_dev" not in d
    out = json_to_pagebox(d)
    assert out.mask is None
    assert out.std_dev is None
    assert out.origin == USER


@pytest.mark.unit
def test_meta_validation() -> None:
    """Untrusted meta.json is rejected: oversized/non-int dims, mismatched
    mask dims, non-bool geometry_altered (T-05-02 / T-05-04)."""
    from manga_ai_studio.core.project_io import validate_meta

    # a well-formed meta passes
    validate_meta(
        {
            "version": 1,
            "img": {"w": 800, "h": 1200},
            "mask": {"h": 1200, "w": 800},
            "geometry_altered": False,
            "boxes": [],
        }
    )

    # img dims beyond MAX_IMAGE_DIMENSION (10000) -> rejected
    with pytest.raises(ProjectFormatError):
        validate_meta({"img": {"w": 10001, "h": 100}})
    # non-int img dims -> rejected
    with pytest.raises(ProjectFormatError):
        validate_meta({"img": {"w": "wide", "h": 100}})
    # mask dims != img dims -> rejected
    with pytest.raises(ProjectFormatError):
        validate_meta({"img": {"w": 800, "h": 1200}, "mask": {"h": 10, "w": 10}})
    # geometry_altered non-bool -> rejected
    with pytest.raises(ProjectFormatError):
        validate_meta({"img": {"w": 800, "h": 1200}, "geometry_altered": "yes"})
    # missing img -> rejected
    with pytest.raises(ProjectFormatError):
        validate_meta({"boxes": []})


@pytest.mark.unit
def test_oversized_chapter_rejected(tmp_path: Path) -> None:
    """A manifest with 1001 pages is an oversized-chapter DoS signal
    (T-05-04) and is rejected with ProjectFormatError."""
    project_dir = tmp_path / "big.mas-project"
    project_dir.mkdir()
    manifest = {
        "version": 1,
        "name": "big",
        "pages": [
            {"name": f"p{i:04d}", "file": f"p{i:04d}.mas"} for i in range(1001)
        ],
    }
    manifest_path = project_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProjectFormatError):
        load_project(manifest_path)

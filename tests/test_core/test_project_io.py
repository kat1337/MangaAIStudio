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

import base64
import json
import os
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from manga_ai_studio.core.box_model import PageBox, USER
from manga_ai_studio.core.mask_planes import pack_binary, unpack_binary
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
    # Phase 8 (plan 08-04): this pagebox has NO seam fields set, so the
    # optional keys serialize as null and restore as None.
    assert out.mask is None
    assert out.std_dev is None


@pytest.mark.unit
def test_detected_payload_numpy_lines_round_trip() -> None:
    """quick-260824-pqn: a REAL detected payload — a TextBlock whose ``lines``
    are raw numpy int32 polygons exactly as ``group_output`` appends them
    (vendored textblock.py:468/474) — survives ``pagebox_to_json`` +
    ``json.dumps`` and round-trips with plain-int line coordinates.

    Before the fix this raised ``TypeError: Object of type ndarray is not
    JSON serializable`` inside ``build_page_entries``, which silently killed
    Save Project inside the Qt slot (empty folder, no error UI).
    """
    payload = TextBlock(
        [10, 10, 100, 100],
        [np.array([[1, 2], [3, 4], [5, 6], [7, 8]], dtype=np.int32)],
    )
    payload.text = "hello"
    payload.translation = "world"
    payload.font_size = 14
    pb = PageBox(box=Box(10, 10, 100, 100), origin="detected", payload=payload)

    d = pagebox_to_json(pb)
    serialized = json.dumps(d, ensure_ascii=False)  # must NOT raise TypeError
    out = json_to_pagebox(json.loads(serialized))
    assert out.payload is not None
    assert out.payload.lines == [[[1, 2], [3, 4], [5, 6], [7, 8]]]
    assert all(isinstance(v, int) for quad in out.payload.lines for pt in quad for v in pt)
    assert out.payload.text == "hello"
    assert out.payload.translation == "world"
    assert out.payload.font_size == 14


@pytest.mark.unit
def test_detected_payload_edge_cases_json_safe() -> None:
    """quick-260824-pqn edge cases: empty ``lines`` serialize as [];
    non-int numerics (np.float64 coordinates) coerce to plain ints per the
    existing load-side contract; a payload-less PageBox serializes
    ``payload: null`` unchanged."""
    # Empty lines.
    tb_empty = TextBlock([0, 0, 10, 10], [])
    pb_empty = PageBox(box=Box(0, 0, 10, 10), origin="detected", payload=tb_empty)
    d_empty = pagebox_to_json(pb_empty)
    assert d_empty["payload"]["lines"] == []
    json.dumps(d_empty, ensure_ascii=False)

    # np.float64 coordinates coerce to int.
    tb_float = TextBlock(
        [np.float64(1), np.float64(2), np.float64(50), np.float64(60)],
        [
            np.array(
                [[1.5, 2.5], [3.5, 4.5], [5.5, 6.5], [7.5, 8.5]],
                dtype=np.float64,
            )
        ],
    )
    pb_float = PageBox(box=Box(1, 2, 50, 60), origin="detected", payload=tb_float)
    d_float = pagebox_to_json(pb_float)
    json.dumps(d_float, ensure_ascii=False)
    assert all(isinstance(v, int) for v in d_float["payload"]["xyxy"])
    assert all(
        isinstance(v, int)
        for quad in d_float["payload"]["lines"]
        for pt in quad
        for v in pt
    )

    # Payload None unchanged.
    pb_none = PageBox(box=Box(0, 0, 10, 10), origin=USER, payload=None)
    assert pagebox_to_json(pb_none)["payload"] is None


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
def test_phase8_seam_fields_round_trip() -> None:
    """A PageBox carrying std_dev, inpaint_override, and a box-cropped
    mode-"1" mask survives pagebox_to_json -> json_to_pagebox (plan 08-04).

    The mask rebuilds with equal size and matching binary content (the
    np.array equality — the D-15 seam closes through persistence).
    """
    mask = Image.new("1", (20, 10), 0)
    ImageDraw.Draw(mask).rectangle([2, 2, 18, 8], fill=1)  # filled region
    pb = PageBox(
        box=Box(5, 5, 25, 15),  # box w=20, h=10 matches the mask crop
        origin=USER,
        payload=None,
        std_dev=12.3,
        inpaint_override="never",
        mask=mask,
    )
    d = pagebox_to_json(pb)
    assert d["std_dev"] == 12.3
    assert d["inpaint_override"] == "never"
    assert d["mask"]  # a non-empty base64 PNG str, not None

    out = json_to_pagebox(d)
    assert out.std_dev == 12.3
    assert out.inpaint_override == "never"
    assert out.mask is not None
    assert out.mask.size == (20, 10)  # equal-size — box dims
    assert out.mask.mode == "1"
    assert np.array_equal(np.array(out.mask), np.array(mask))


@pytest.mark.unit
def test_legacy_pagebox_without_phase8_keys_loads_defaults() -> None:
    """A Phase 5/7-shape pagebox dict (NO std_dev/inpaint_override/mask keys)
    loads clean with all three None (the no-version-bump optional-key pattern).

    Clone of ``test_legacy_mas_without_style_loads_with_defaults`` applied to
    the three Phase 8 keys.
    """
    legacy = {
        "box": [0, 0, 100, 40],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "style": None,
        "payload": None,
    }
    out = json_to_pagebox(legacy)
    assert out.std_dev is None
    assert out.inpaint_override is None
    assert out.mask is None
    assert out.style == TextStyle()  # existing D-07 default behavior unchanged


@pytest.mark.unit
def test_invalid_inpaint_override_rejected() -> None:
    """An inpaint_override not in {"always","never","fill"} raises ProjectFormatError,
    matching the format-version rejection stance (T-08-08 enum validation + 08.1 D-04).

    None (Auto) and "fill"/"always"/"never" pass; any other string is structural garbage.
    """
    base = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**base, "inpaint_override": "sometimes"})
    # None (null/Auto) loads clean
    out = json_to_pagebox({**base, "inpaint_override": None})
    assert out.inpaint_override is None
    # 08.1: "fill" loads clean (quad-state)
    out2 = json_to_pagebox({**base, "inpaint_override": "fill"})
    assert out2.inpaint_override == "fill"
    out3 = json_to_pagebox({**base, "inpaint_override": "always"})
    assert out3.inpaint_override == "always"


@pytest.mark.unit
def test_invalid_std_dev_rejected() -> None:
    """A non-numeric std_dev raises ProjectFormatError via float coercion
    (T-08-08 — NaN/std garbage never enters the border-state derivation)."""
    base = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**base, "std_dev": "abc"})
    # a numeric str / number loads
    out = json_to_pagebox({**base, "std_dev": 12.3})
    assert out.std_dev == 12.3


@pytest.mark.unit
def test_per_box_mask_size_mismatch_loads_sanitized() -> None:
    """A per-box mask whose decoded PNG size does not match the box's (w, h)
    is a STALE mask (box resized after fit) — it decodes fine but no longer
    fits the geometry, so the loader sanitizes it to ``mask=None`` and nulls
    the fit-derived ``std_dev``/``fill_color`` together (quick-260825-u9q —
    the old T-08-06 hard reject made such projects unloadable). Decode-level
    garbage still raises (see test_per_box_mask_garbage_rejected)."""
    tiny = Image.new("1", (4, 4), 0)
    buf = BytesIO()
    tiny.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    base = {  # box is 100x40, but the mask decodes to 4x4 — stale
        "box": [0, 0, 100, 40],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    out = json_to_pagebox(
        {
            **base,
            "mask": b64,
            "std_dev": 12.3,
            "fill_color": [1, 2, 3],
        }
    )
    assert out.mask is None
    assert out.std_dev is None
    assert out.fill_color is None

    # The MATCHING-size case keeps returning a real mode-"1" image.
    fitted = Image.new("1", (100, 40), 0)
    buf2 = BytesIO()
    fitted.save(buf2, format="PNG")
    b64_fitted = base64.b64encode(buf2.getvalue()).decode("ascii")
    out2 = json_to_pagebox({**base, "mask": b64_fitted})
    assert out2.mask is not None
    assert out2.mask.mode == "1"
    assert out2.mask.size == (100, 40)


@pytest.mark.unit
def test_stale_mask_after_resize_user_scenario_loads() -> None:
    """The exact user scenario (quick-260825-u9q): a box was FITTED
    (mask sized to its box, std_dev + fill_color measured) and THEN resized
    before saving. pagebox_to_json serializes both verbatim; the loader must
    sanitize the stale trio (mask/std_dev/fill_color -> None) instead of
    raising ProjectFormatError, while preserving inpaint_override (user
    intent) and style/payload untouched."""
    pb = PageBox(
        box=Box(0, 0, 100, 40),
        origin=USER,
        payload=TextBlock([0, 0, 100, 40], lines=[], language="unknown"),
        edited=False,
        bubble_no=None,
        manual_override=False,
        style=TextStyle(),
        std_dev=12.5,
        inpaint_override="always",
        mask=Image.new("1", (100, 40), 0),
        fill_color=(10, 20, 30),
    )
    d = pagebox_to_json(pb)
    # Simulate the post-fit resize: new geometry, stale mask dims.
    d["box"] = [0, 0, 80, 60]

    out = json_to_pagebox(d)  # MUST NOT raise ProjectFormatError
    assert out.box.as_tuple == (0, 0, 80, 60)
    assert out.mask is None
    assert out.std_dev is None
    assert out.fill_color is None
    # User intent survives; style/payload untouched.
    assert out.inpaint_override == "always"
    assert out.style is not None and isinstance(out.style, TextStyle)
    assert out.payload is not None


@pytest.mark.unit
def test_per_box_mask_garbage_rejected() -> None:
    """A mask value that is not a decryptable/valid PNG raises
    ProjectFormatError, never a raw binascii/PIL exception (T-08-06 decode
    hardening — the T-05-01 pattern)."""
    base = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    # not valid base64 at all
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**base, "mask": "!!!not-base64!!!%%"})
    # valid base64 but not a PNG
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**base, "mask": base64.b64encode(b"not a png").decode("ascii")})


@pytest.mark.unit
def test_save_side_stale_mask_serializes_null() -> None:
    """Save-side guard (quick-260825-u9q): pagebox_to_json on a live
    PageBox whose mask.size != box dims emits mask/std_dev/fill_color as
    null (the fit-derived trio dies together) so a resized-after-fit box
    can never produce an unloadable file; inpaint_override/style/payload
    emit normally. A matching-size mask still serializes to base64."""
    stale = PageBox(
        box=Box(0, 0, 80, 60),
        origin=USER,
        payload=None,
        edited=False,
        bubble_no=None,
        manual_override=False,
        style=TextStyle(),
        std_dev=12.5,
        inpaint_override="always",
        mask=Image.new("1", (100, 40), 0),  # fitted at old geometry
        fill_color=(10, 20, 30),
    )
    d = pagebox_to_json(stale)
    assert d["mask"] is None
    assert d["std_dev"] is None
    assert d["fill_color"] is None
    # User intent and non-fit fields survive verbatim.
    assert d["inpaint_override"] == "always"
    assert d["style"] == TextStyle().to_dict()
    assert d["payload"] is None

    # Happy case: matching-size mask serializes to a non-null base64 PNG.
    fresh = PageBox(
        box=Box(0, 0, 100, 40),
        origin=USER,
        payload=None,
        edited=False,
        bubble_no=None,
        manual_override=False,
        style=None,
        std_dev=9.1,
        inpaint_override=None,
        mask=Image.new("1", (100, 40), 0),
        fill_color=(4, 5, 6),
    )
    d2 = pagebox_to_json(fresh)
    assert isinstance(d2["mask"], str)
    assert base64.b64decode(d2["mask"])[:8] == b"\x89PNG\r\n\x1a\n"
    assert d2["std_dev"] == 9.1
    assert d2["fill_color"] == [4, 5, 6]


@pytest.mark.unit
def test_build_page_entries_writes_optional_plane_entries() -> None:
    """build_page_entries with raw/auto/manual/erase binaries writes the four
    optional plane entries; without them a legacy-shaped state writes none."""
    image = np.zeros((20, 30, 3), dtype=np.uint8)

    def _binary(y0, y1, x0, x1):
        arr = np.zeros((20, 30), dtype=np.uint8)
        arr[y0:y1, x0:x1] = 255
        return arr

    raw = _binary(1, 5, 2, 9)
    auto = _binary(3, 8, 4, 12)
    manual = _binary(5, 11, 6, 15)
    erase = _binary(7, 13, 8, 18)

    entries = build_page_entries(
        {
            "boxes": [],
            "image_rgb": image,
            "mask_bin": None,
            "raw_binary": raw,
            "auto_binary": auto,
            "manual_binary": manual,
            "erase_binary": erase,
        }
    )
    for name in (
        "rawmask.bin",
        "automask.bin",
        "manualmask.bin",
        "erasemask.bin",
    ):
        assert name in entries
    assert entries["rawmask.bin"] == pack_binary(raw).tobytes()
    assert entries["automask.bin"] == pack_binary(auto).tobytes()
    assert entries["manualmask.bin"] == pack_binary(manual).tobytes()
    assert entries["erasemask.bin"] == pack_binary(erase).tobytes()

    # legacy-shaped state (no plane binaries) writes none of the four.
    legacy = build_page_entries({"boxes": [], "image_rgb": image, "mask_bin": None})
    for name in (
        "rawmask.bin",
        "automask.bin",
        "manualmask.bin",
        "erasemask.bin",
    ):
        assert name not in legacy


@pytest.mark.unit
def test_parse_page_entries_plane_round_trip(tmp_path: Path) -> None:
    """parse_page_entries on a container WITH the four entries returns the
    four packed arrays whose unpacked content matches what was packed; a
    container WITHOUT them returns None for all four (legacy project)."""
    image = np.zeros((20, 30, 3), dtype=np.uint8)

    def _binary(y0, y1, x0, x1):
        arr = np.zeros((20, 30), dtype=np.uint8)
        arr[y0:y1, x0:x1] = 255
        return arr

    raw = _binary(1, 5, 2, 9)
    auto = _binary(3, 8, 4, 12)
    manual = _binary(5, 11, 6, 15)
    erase = _binary(7, 13, 8, 18)

    entries = build_page_entries(
        {
            "boxes": [],
            "image_rgb": image,
            "mask_bin": None,
            "raw_binary": raw,
            "auto_binary": auto,
            "manual_binary": manual,
            "erase_binary": erase,
        }
    )
    page_file = tmp_path / "page_001.mas"
    save_page_file(page_file, entries)
    parsed = parse_page_entries(load_page_file(page_file))

    for key, expected in (
        ("raw_packed", raw),
        ("auto_packed", auto),
        ("manual_packed", manual),
        ("erase_packed", erase),
    ):
        packed = parsed[key]
        assert packed is not None
        assert unpack_binary(packed, 20, 30).tolist() == expected.tolist()

    # Legacy container without the entries -> None for all four.
    legacy_entries = build_page_entries(
        {"boxes": [], "image_rgb": image, "mask_bin": None}
    )
    legacy_file = tmp_path / "legacy.mas"
    save_page_file(legacy_file, legacy_entries)
    parsed_legacy = parse_page_entries(load_page_file(legacy_file))
    assert parsed_legacy["raw_packed"] is None
    assert parsed_legacy["auto_packed"] is None
    assert parsed_legacy["manual_packed"] is None
    assert parsed_legacy["erase_packed"] is None


@pytest.mark.unit
def test_crafted_plane_blob_length_rejected(tmp_path: Path) -> None:
    """A crafted rawmask.bin whose byte length does not equal ceil(h*w/8) for
    the declared dims raises ProjectFormatError (T-08-07) — a short/long
    blob is a format error, never a mis-shaped array."""
    image = np.zeros((20, 30, 3), dtype=np.uint8)  # ceil(600/8) == 75 bytes
    entries = build_page_entries(
        {"boxes": [], "image_rgb": image, "mask_bin": None}
    )
    entries["rawmask.bin"] = bytes(74)  # one byte short
    page_file = tmp_path / "crafted.mas"
    save_page_file(page_file, entries)
    with pytest.raises(ProjectFormatError):
        parse_page_entries(load_page_file(page_file))

    entries2 = build_page_entries(
        {"boxes": [], "image_rgb": image, "mask_bin": None}
    )
    entries2["rawmask.bin"] = bytes(76)  # one byte long
    page_file2 = tmp_path / "crafted2.mas"
    save_page_file(page_file2, entries2)
    with pytest.raises(ProjectFormatError):
        parse_page_entries(load_page_file(page_file2))


@pytest.mark.unit
def test_page_entries_full_round_trip_with_seam_and_planes(tmp_path: Path) -> None:
    """The plan's end-to-end save -> load round-trip: a page with boxes
    (mask/std_dev/inpaint_override) AND the four plane binaries rebuilds
    everything equal — the D-15 seam closes through persistence."""
    image = np.zeros((20, 30, 3), dtype=np.uint8)

    mask = Image.new("1", (20, 10), 0)
    ImageDraw.Draw(mask).rectangle([2, 2, 18, 8], fill=1)
    pb = PageBox(
        box=Box(5, 5, 25, 15),  # box-cropped mask dims (20, 10)
        origin=USER,
        payload=None,
        std_dev=12.3,
        inpaint_override="never",
        mask=mask,
    )

    def _binary(y0, y1, x0, x1):
        arr = np.zeros((20, 30), dtype=np.uint8)
        arr[y0:y1, x0:x1] = 255
        return arr

    raw = _binary(1, 5, 2, 9)
    auto = _binary(3, 8, 4, 12)
    manual = _binary(5, 11, 6, 15)
    erase = _binary(7, 13, 8, 18)

    entries = build_page_entries(
        {
            "boxes": [pb],
            "image_rgb": image,
            "mask_bin": None,
            "raw_binary": raw,
            "auto_binary": auto,
            "manual_binary": manual,
            "erase_binary": erase,
        }
    )
    page_file = tmp_path / "page_001.mas"
    save_page_file(page_file, entries)
    parsed = parse_page_entries(load_page_file(page_file))

    # Boxes rebuild with every Phase 8 seam field equal.
    boxes = [json_to_pagebox(bd) for bd in parsed["meta"]["boxes"]]
    assert len(boxes) == 1
    out = boxes[0]
    assert out.std_dev == 12.3
    assert out.inpaint_override == "never"
    assert out.mask is not None
    assert out.mask.size == (20, 10)
    assert np.array_equal(np.array(out.mask), np.array(mask))

    # Planes rebuild equal.
    for key, expected in (
        ("raw_packed", raw),
        ("auto_packed", auto),
        ("manual_packed", manual),
        ("erase_packed", erase),
    ):
        assert unpack_binary(parsed[key], 20, 30).tolist() == expected.tolist()


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
def test_d15_seam_superseded_by_phase8() -> None:
    """Phase 8 supersedes the Phase 5/7 'never writes mask/std_dev' D-15 seam
    contract: the fields are now serialized as JSON keys (None when unset)
    and round-trip back to None.

    A PageBox with unset seam fields must serialize ``"std_dev"`` /
    ``"inpaint_override"`` / ``"mask"`` all as explicit null, and
    json_to_pagebox must rebuild all three as None.
    """
    pb = PageBox(box=Box(0, 0, 10, 10), origin=USER, mask=None, std_dev=None)
    d = pagebox_to_json(pb)
    assert d["std_dev"] is None
    assert d["inpaint_override"] is None
    assert d["mask"] is None
    out = json_to_pagebox(d)
    assert out.mask is None
    assert out.std_dev is None
    assert out.inpaint_override is None
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


@pytest.mark.unit
def test_fill_and_fill_color_round_trip() -> None:
    """08.1: PageBox with inpaint_override fill and fill_color (128,200,50)
    serializes fill_color as [128,200,50] and loads back equal; legacy file
    without fill_color loads with fill_color None; old vocab always/never still loads."""
    from manga_ai_studio.core.project_io import pagebox_to_json, json_to_pagebox

    pb = PageBox(
        box=Box(0, 0, 10, 10),
        origin=USER,
        payload=None,
        inpaint_override="fill",
        fill_color=(128, 200, 50),
    )
    d = pagebox_to_json(pb)
    assert d["inpaint_override"] == "fill"
    assert d["fill_color"] == [128, 200, 50]
    out = json_to_pagebox(d)
    assert out.inpaint_override == "fill"
    assert out.fill_color == (128, 200, 50)

    # Legacy without fill_color key loads with None
    legacy = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
        "inpaint_override": None,
    }
    out_legacy = json_to_pagebox(legacy)
    assert out_legacy.fill_color is None
    assert out_legacy.inpaint_override is None

    # Old vocab still loads
    for val in ("always", "never"):
        out_old = json_to_pagebox({**legacy, "inpaint_override": val})
        assert out_old.inpaint_override == val

    # Invalid fill_color rejected
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**legacy, "fill_color": [1, 2]})
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**legacy, "fill_color": [256, 0, 0]})
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**legacy, "fill_color": "bad"})


@pytest.mark.unit
def test_pagebox_copy_detaches_mask_preserves_fill_color() -> None:
    """08.1 tracer truth: PageBox copy detaches mask PIL image while fill_color tuple preserved by value."""
    from manga_ai_studio.core.box_model import DETECTED, PageBox
    from PIL import Image

    m = Image.new("1", (4, 4), 0)
    m.putpixel((1, 1), 1)
    pb = PageBox(box=Box(0, 0, 10, 10), origin=DETECTED, mask=m, fill_color=(10, 20, 30))
    clone = pb.copy()
    assert clone.mask is not pb.mask
    assert clone.fill_color == (10, 20, 30)
    pb.fill_color = (1, 1, 1)
    assert clone.fill_color == (10, 20, 30)
    pb.mask.putpixel((2, 2), 1)
    assert clone.mask.getpixel((2, 2)) == 0


@pytest.mark.unit
def test_confidence_round_trip() -> None:
    """quick-260903-lm6: a PageBox carrying confidence=0.87 serializes the
    float and loads it back equal; confidence=None serializes null and loads
    back None."""
    from manga_ai_studio.core.project_io import pagebox_to_json, json_to_pagebox

    pb = PageBox(box=Box(0, 0, 10, 10), origin=USER, payload=None, confidence=0.87)
    d = pagebox_to_json(pb)
    assert d["confidence"] == 0.87
    out = json_to_pagebox(d)
    assert out.confidence == 0.87

    pb_none = PageBox(box=Box(0, 0, 10, 10), origin=USER, payload=None, confidence=None)
    d_none = pagebox_to_json(pb_none)
    assert d_none["confidence"] is None
    out_none = json_to_pagebox(d_none)
    assert out_none.confidence is None


@pytest.mark.unit
def test_legacy_pagebox_without_confidence_loads_none() -> None:
    """quick-260903-lm6: a legacy .mas pagebox dict with no "confidence" key
    loads clean with confidence None."""
    from manga_ai_studio.core.project_io import json_to_pagebox

    legacy = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    out = json_to_pagebox(legacy)
    assert out.confidence is None


@pytest.mark.unit
def test_invalid_confidence_rejected() -> None:
    """quick-260903-lm6: a non-numeric confidence raises ProjectFormatError
    via float coercion (the std_dev precedent)."""
    from manga_ai_studio.core.project_io import json_to_pagebox

    base = {
        "box": [0, 0, 10, 10],
        "origin": USER,
        "edited": False,
        "bubble_no": None,
        "manual_override": False,
        "payload": None,
    }
    with pytest.raises(ProjectFormatError):
        json_to_pagebox({**base, "confidence": "high"})
    # a numeric value loads
    out = json_to_pagebox({**base, "confidence": 0.42})
    assert out.confidence == 0.42

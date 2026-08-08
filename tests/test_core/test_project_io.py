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
from pathlib import Path

import pytest

from manga_ai_studio.core.box_model import PageBox, USER
from manga_ai_studio.core.project_io import (
    _MAGIC,
    ProjectFormatError,
    json_to_pagebox,
    load_page_file,
    pagebox_to_json,
    save_page_file,
)
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

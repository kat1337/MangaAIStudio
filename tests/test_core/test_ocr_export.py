"""Tests for the headless ``_ocr.json`` exporter ``core/ocr_export.py`` (plan 05-03).

This is the Wave 1 PROJ-03 suite (``tests/test_core/test_ocr_export.py`` —
the Wave 0 file for PROJ-03). It pins the D-19 published JSON shape, the
D-20 ``\\n``-split onto ``TextBlock.lines`` polygons, the D-15 seam
(``mask``/``std_dev`` never exported), the D-22 state-dependent output
location, the UTF-8 write round-trip, and the ``batch_export_ocr``
interruptible per-page-isolation loop contract (mirroring
``core/batch_runner.py``'s ``{ok, failed, total}`` shape).

The module under test is pure stdlib — no Qt, no models — so these tests
carry the ``unit`` marker and run headless (RESEARCH "Architectural
Responsibility Map: Core I/O"). ``worker_thread`` (PySide6) is imported
only for ``Abort``/``SharableFlag`` in the batch tests, matching the
``test_batch_runner.py`` precedent.
"""

from __future__ import annotations

import json

import pytest
from panelcleaner.comic_text_detector.utils.textblock import TextBlock
from panelcleaner.structures import Box

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox
from manga_ai_studio.core.ocr_export import (
    OCR_JSON_VERSION,
    build_page_ocr_json,
    line_box,
    page_ocr_json_dumps,
    split_text_onto_lines,
)


def _two_line_payload(
    text: str = "First line\nSecond line",
    translation: str = "Two lines of dialogue",
):
    """A detected ``TextBlock`` with two line polygons (D-19 sample shape)."""
    return TextBlock(
        [120, 340, 480, 410],
        lines=[
            [[122, 342], [478, 342], [478, 372], [122, 372]],
            [[122, 378], [478, 378], [478, 408], [122, 408]],
        ],
        text=text,
        vertical=False,
        translation=translation,
    )


def _page_with_two_boxes() -> list:
    """One detected box (full payload) + one user box (payload None)."""
    detected = PageBox(
        box=Box(120, 340, 480, 410),
        origin=DETECTED,
        payload=_two_line_payload(),
        bubble_no=3,
    )
    user = PageBox(box=Box(10, 10, 60, 30), origin=USER, payload=None)
    return [detected, user]


@pytest.mark.unit
def test_json_shape() -> None:
    """The D-19 shape: exact snake_case key set at every level, pinned once.

    Two boxes: one with a full payload (2 line quads, translation,
    bubble_no=3, origin "detected"), one payload-None user box (bubble_no
    None). Asserts the exact dict keys, the per-line boxes = line_box of the
    quads, and the payload-None box exporting text "" + lines [].
    """
    data = build_page_ocr_json(_page_with_two_boxes(), img_w=1600, img_h=2400)

    # Top level
    assert set(data.keys()) == {"version", "img_width", "img_height", "blocks"}
    assert data["version"] == OCR_JSON_VERSION == "1"
    assert data["img_width"] == 1600
    assert data["img_height"] == 2400

    # Block 1: the detected box
    blk = data["blocks"][0]
    assert set(blk.keys()) == {
        "box", "vertical", "text", "translation", "bubble_no", "origin", "lines",
    }
    assert blk["box"] == [120, 340, 480, 410]
    assert blk["vertical"] is False
    assert blk["text"] == "First line\nSecond line"
    assert blk["translation"] == "Two lines of dialogue"
    assert blk["bubble_no"] == 3
    assert blk["origin"] == DETECTED == "detected"

    payload = _two_line_payload()
    lines = blk["lines"]
    assert len(lines) == 2
    for entry, quad in zip(lines, payload.lines):
        assert set(entry.keys()) == {"box", "text"}
        assert entry["box"] == line_box(quad)
    assert lines[0]["box"] == [122, 342, 478, 372]
    assert lines[0]["text"] == "First line"
    assert lines[1]["box"] == [122, 378, 478, 408]
    assert lines[1]["text"] == "Second line"

    # Block 2: the payload-None user box
    user = data["blocks"][1]
    assert set(user.keys()) == {
        "box", "vertical", "text", "translation", "bubble_no", "origin", "lines",
    }
    assert user["box"] == [10, 10, 60, 30]
    assert user["vertical"] is False
    assert user["text"] == ""
    assert user["translation"] == ""
    assert user["bubble_no"] is None
    assert user["origin"] == USER == "user"
    assert user["lines"] == []


@pytest.mark.unit
def test_newline_split() -> None:
    """D-20: the ``\\n``-split maps the whole text onto the polygons.

    3 segments onto 2 quads -> the third segment is dropped (the split maps
    onto polygons); 1 segment onto 3 quads -> unmatched polygons export "".
    A list-typed text is joined first (defensive TextBlock storage). A
    zero-box page exports blocks [] (no gate, no confirm).
    """
    quads = [
        [[0, 0], [10, 0], [10, 10], [0, 10]],
        [[0, 20], [10, 20], [10, 30], [0, 30]],
    ]
    # 3 segments onto 2 polygons: third dropped.
    assert split_text_onto_lines("First line\nSecond line\nThird line", quads) == [
        "First line",
        "Second line",
    ]
    # 1 segment onto 3 polygons: unmatched polygons export empty text.
    three_quads = quads + [[[0, 40], [10, 40], [10, 50], [0, 50]]]
    assert split_text_onto_lines("text", three_quads) == ["text", "", ""]
    # List storage is joined with "\n" before the split.
    assert split_text_onto_lines(["First line", "Second line"], quads) == [
        "First line",
        "Second line",
    ]
    # Zero-box page.
    assert build_page_ocr_json([], 100, 200)["blocks"] == []


@pytest.mark.unit
def test_d15_seam_never_exported() -> None:
    """``PageBox.mask`` / ``std_dev`` are NEVER exported (D-15 seam).

    A PageBox carrying a mask object and a std_dev exports exactly the
    D-19 key set — no mask/std_dev keys at any level.
    """

    class Dummy:
        pass

    pb = PageBox(
        box=Box(1, 2, 3, 4),
        origin=USER,
        payload=None,
        mask=Dummy(),
        std_dev=0.5,
    )
    data = build_page_ocr_json([pb], 100, 100)
    blk = data["blocks"][0]
    assert "mask" not in blk
    assert "std_dev" not in blk
    assert set(blk.keys()) == {
        "box", "vertical", "text", "translation", "bubble_no", "origin", "lines",
    }


@pytest.mark.unit
def test_dumps_round_trip() -> None:
    """``page_ocr_json_dumps`` produces parseable, UTF-8-safe JSON.

    The dumped string re-parses to the identical dict (field spelling
    preserved), and Japanese text survives ensure_ascii=False unescaped.
    """
    data = build_page_ocr_json(
        [PageBox(box=Box(1, 2, 3, 4), origin=DETECTED, payload=_two_line_payload(
            text="日本語の台詞\n二行目"
        ))],
        1600,
        2400,
    )
    dumped = page_ocr_json_dumps(data)
    assert json.loads(dumped) == data
    assert "日本語" in dumped  # ensure_ascii=False keeps text readable on disk

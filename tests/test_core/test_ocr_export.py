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

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from panelcleaner.comic_text_detector.utils.textblock import TextBlock  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.core.ocr_export import (  # noqa: E402
    OCR_JSON_VERSION,
    ExportPage,
    TypesetPage,
    batch_export_ocr,
    batch_export_typeset,
    build_page_ocr_json,
    default_ocr_json_path,
    default_typeset_path,
    line_box,
    ocr_json_target_dir,
    page_ocr_json_dumps,
    split_text_onto_lines,
    write_page_ocr_json,
)
from manga_ai_studio.core.text_style import TextStyle  # noqa: E402


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
    assert data["version"] == OCR_JSON_VERSION == "2"
    assert data["img_width"] == 1600
    assert data["img_height"] == 2400

    # Block 1: the detected box
    blk = data["blocks"][0]
    assert set(blk.keys()) == {
        "box", "vertical", "text", "translation", "bubble_no", "origin",
        "style", "lines",
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
        "box", "vertical", "text", "translation", "bubble_no", "origin",
        "style", "lines",
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
        "box", "vertical", "text", "translation", "bubble_no", "origin",
        "style", "lines",
    }


@pytest.mark.unit
def test_bare_marker_payload_degrades_not_crashes() -> None:
    """WR-03: a non-``TextBlock`` payload (e.g. a bare marker str — the suite
    builds ``PageBox(payload="p")``) must DEGRADE in the export, mirroring
    ``gui/text_renderer.current_focus_text``'s ``getattr`` contract — never an
    ``AttributeError`` in the export worker."""
    pb = PageBox(box=Box(1, 2, 3, 4), origin=USER, payload="bare-marker")
    data = build_page_ocr_json([pb], 100, 100)
    blk = data["blocks"][0]
    assert blk["vertical"] is False
    assert blk["text"] == ""
    assert blk["translation"] == ""
    assert blk["lines"] == []
    # The D-19 block still carries the box's own real fields.
    assert blk["box"] == [1, 2, 3, 4]
    assert blk["origin"] == USER


@pytest.mark.unit
def test_style_block_shape() -> None:
    """The D-07 style block: "style" at BLOCK level with the to_dict spelling.

    Pins the exact block JSON — the D-19 keys (box/vertical/text/translation/
    bubble_no/origin/lines) unchanged, plus the block-level "style" entry
    equal to ``TextStyle.to_dict()`` of the same box (Pitfall 6 — ONE
    spelling; per-box flat style, D-06).
    """
    style = TextStyle(
        font_family="Yu Gothic UI",
        font_size_px=22.0,
        auto_fit=False,
        color="#ff6b6b",
        outline={"enabled": True, "color": "#0b0b0e", "width_px": 3.0},
    )
    pb = PageBox(
        box=Box(120, 340, 480, 410),
        origin=DETECTED,
        payload=_two_line_payload(),
        bubble_no=3,
        style=style,
    )
    data = build_page_ocr_json([pb], img_w=1600, img_h=2400)
    assert data["blocks"][0] == {
        "box": [120, 340, 480, 410],
        "vertical": False,
        "text": "First line\nSecond line",
        "translation": "Two lines of dialogue",
        "bubble_no": 3,
        "origin": DETECTED,
        "style": style.to_dict(),
        "lines": [
            {"box": [122, 342, 478, 372], "text": "First line"},
            {"box": [122, 378, 478, 408], "text": "Second line"},
        ],
    }


@pytest.mark.unit
def test_version_is_task2_decision() -> None:
    """The emitted "version" equals the Task 2 checkpoint decision ("2").

    D-07 one-way: the bump signals the style block's presence to downstream
    consumers (Option A — explicit published-contract extension, RESEARCH A5).
    """
    data = build_page_ocr_json(_page_with_two_boxes(), img_w=100, img_h=100)
    assert data["version"] == "2"
    assert OCR_JSON_VERSION == "2"


@pytest.mark.unit
def test_style_none_block() -> None:
    """A style-None box emits "style": None in its block (D-07 json null).

    The projection is explicit about a missing style; the D-19 key set is
    otherwise unchanged.
    """
    pb = PageBox(box=Box(10, 10, 60, 30), origin=USER, payload=None, style=None)
    data = build_page_ocr_json([pb], img_w=100, img_h=100)
    blk = data["blocks"][0]
    assert blk["style"] is None
    assert set(blk.keys()) == {
        "box", "vertical", "text", "translation", "bubble_no", "origin",
        "style", "lines",
    }


@pytest.mark.unit
def test_style_block_one_spelling() -> None:
    """The block's style dict is byte-equal to ``TextStyle.to_dict()``.

    Pitfall 6: the writer MUST call ``to_dict()`` — no hand-built dict at
    the call site, so the .mas writer and the _ocr.json writer can never
    drift (one dict builder under test).
    """
    style = TextStyle(
        font_family="Yu Gothic UI",
        bold=True,
        font_size_px=22.0,
        auto_fit=False,
        glow={"enabled": True, "color": "#ffff00", "radius_px": 8.0, "opacity": 0.5},
    )
    pb = PageBox(box=Box(1, 2, 3, 4), origin=USER, payload=None, style=style)
    data = build_page_ocr_json([pb], img_w=100, img_h=100)
    assert data["blocks"][0]["style"] == style.to_dict()


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


# ---------------------------------------------------------------------------
# Task 2: D-22 location rule + write_page_ocr_json + batch_export_ocr
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_d22_location_rule(tmp_path: Path) -> None:
    """D-22: pristine -> sidecar beside the source; altered -> cleaned/.

    A pristine page exports to ``source_dir / <stem>_ocr.json``; a
    geometry-altered page exports to ``<source>/cleaned/`` (directory
    created if missing); ``chapter-01/page-03.png`` altered lands in
    ``chapter-01/cleaned/page-03_ocr.json``.
    """
    src = tmp_path / "chapter-01"
    src.mkdir(parents=True)
    page = src / "page-03.png"

    # Pristine: sidecar next to the source.
    assert ocr_json_target_dir(src, geometry_altered=False) == src
    assert default_ocr_json_path(page, geometry_altered=False) == src / "page-03_ocr.json"

    # Altered: cleaned/ sibling (created if missing).
    assert ocr_json_target_dir(src, geometry_altered=True) == src / "cleaned"
    assert default_ocr_json_path(page, geometry_altered=True) == src / "cleaned" / "page-03_ocr.json"

    # write_page_ocr_json creates the target dir and writes the sidecar.
    boxes = [PageBox(box=Box(120, 340, 480, 410), origin=DETECTED, payload=_two_line_payload())]
    written = write_page_ocr_json(boxes, 1600, 2400, page, geometry_altered=True)
    assert written == src / "cleaned" / "page-03_ocr.json"
    assert written.is_file()
    # Path override bypasses the D-22 rule (GUI Save As dialog).
    override = tmp_path / "elsewhere" / "custom.json"
    written_override = write_page_ocr_json(
        boxes, 1600, 2400, page, geometry_altered=False, path_override=override
    )
    assert written_override == override
    assert override.is_file()


@pytest.mark.unit
def test_write_round_trip_utf8(tmp_path: Path) -> None:
    """UTF-8 file write: Japanese text survives the round-trip exactly.

    ``write_page_ocr_json`` with a Japanese payload -> file bytes decode as
    UTF-8 and ``json.loads`` yields ``blocks[0]["text"]`` equal to the
    source (T-05-10 probe encoding truth).
    """
    jp = "日本語の台詞\n二行目"
    boxes = [
        PageBox(
            box=Box(1, 2, 100, 50),
            origin=DETECTED,
            payload=TextBlock(
                [1, 2, 100, 50],
                lines=[[[2, 3], [99, 3], [99, 20], [2, 20]]],
                text=jp,
                vertical=True,
                translation="Japanese dialogue",
            ),
        )
    ]
    page = tmp_path / "page.png"
    written = write_page_ocr_json(boxes, 100, 200, page, geometry_altered=False)
    raw = written.read_bytes()
    assert raw.decode("utf-8")  # decodes cleanly as UTF-8
    data = json.loads(raw.decode("utf-8"))
    assert data["blocks"][0]["text"] == jp
    assert data["blocks"][0]["translation"] == "Japanese dialogue"
    assert data["blocks"][0]["vertical"] is True


def _export_pages(tmp_path: Path, count: int = 3):
    """Three pristine ``ExportPage``s with a single payload box each."""
    pages = []
    for i in range(count):
        page_path = tmp_path / f"page{i + 1}.png"
        pages.append(
            ExportPage(
                path=page_path,
                boxes=[
                    PageBox(
                        box=Box(0, 0, 10, 10),
                        origin=DETECTED,
                        payload=_two_line_payload(f"text {i + 1}"),
                    )
                ],
                img_w=100,
                img_h=200,
                geometry_altered=False,
            )
        )
    return pages


@pytest.mark.unit
def test_batch_export_ocr_isolates_failures(tmp_path: Path) -> None:
    """D-04 batch contract: {ok, failed, total} exact; loop-top abort.

    3 pages, one with an invalid page path (a FILE where the target
    directory would be) that raises at write -> {"ok": 2, "failed": 1,
    "total": 3}, the two good JSON files exist, and the failure is recorded
    with the page stem. With the abort flag set after page 1's emit, the
    batch raises ``Abort`` before writing any further page (loop-top
    ordering proven: page 1 completed).
    """
    pages = _export_pages(tmp_path)

    # Make page 2's write fail: its source dir is a FILE, so mkdir raises.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    pages[1].path = blocker / "page2.png"

    summary = batch_export_ocr(pages)
    # Failure recorded with the page stem in the path tuple.
    assert len(summary["failed"]) == 1
    failed_path, failed_msg = summary["failed"][0]
    assert failed_path.name == "page2.png"
    assert isinstance(failed_msg, str) and failed_msg
    assert summary["ok"] == 2
    assert summary["total"] == 3

    # The two good pages produced their sidecars; the failing one did not.
    assert (tmp_path / "page1_ocr.json").is_file()
    assert not (tmp_path / "page2_ocr.json").exists()
    assert (tmp_path / "page3_ocr.json").is_file()

    # Loop-top abort: flip the flag on the FIRST progress emit. Page 1
    # completes (flag set mid-page is not consulted until the next top).
    from manga_ai_studio.gui.worker_thread import Abort, SharableFlag

    flag = SharableFlag(False)

    class _FlagSetter:
        """Signal-shaped progress callback that flips the flag on emit."""

        def emit(self, payload) -> None:
            flag.set(True)

    fresh = _export_pages(tmp_path / "fresh")
    with pytest.raises(Abort):
        batch_export_ocr(fresh, progress_callback=_FlagSetter(), abort_flag=flag)
    assert (tmp_path / "fresh" / "page1_ocr.json").is_file()
    assert not (tmp_path / "fresh" / "page2_ocr.json").exists()


@pytest.mark.unit
def test_batch_progress_emits(tmp_path: Path) -> None:
    """Per-page progress: (percent, page_name) pairs, first = page 1.

    Mirrors the batch_runner D-10 shape: one emit per page at the loop top,
    percent computed as ``int(i / total * 100)``.
    """
    from manga_ai_studio.gui.worker_thread import Abort, SharableFlag

    pages = _export_pages(tmp_path, count=3)

    class _Recorder:
        """Signal-shaped progress recorder (mirrors conftest.RecordingSignal)."""

        def __init__(self) -> None:
            self.calls: list = []

        def emit(self, payload) -> None:
            self.calls.append(payload)

    recorder = _Recorder()
    summary = batch_export_ocr(
        pages, progress_callback=recorder, abort_flag=SharableFlag(False)
    )
    assert summary["ok"] == 3
    emitted = recorder.calls
    assert [name for _, name in emitted] == ["page1.png", "page2.png", "page3.png"]
    assert emitted[0] == (0, "page1.png")  # first emit has the first page's name
    assert emitted[1] == (33, "page2.png")
    assert emitted[2] == (66, "page3.png")


# ---------------------------------------------------------------------------
# quick-260828-k4q Task 2: TypesetPage + batch_export_typeset
# (the real loop called directly — no Worker; bake needs Qt, hence the
# module-level importorskip guard above)
# ---------------------------------------------------------------------------


def _typeset_items(tmp_path: Path, count: int = 3, size: int = 16) -> list:
    """``count`` pristine ``TypesetPage``s with real page pixels + no boxes.

    A zero-box bake is an identity composite — placement/pixels come from the
    page itself, which is all these tests need to observe on disk.
    """
    items = []
    for i in range(count):
        page_path = tmp_path / f"page{i + 1}.png"
        items.append(
            TypesetPage(
                path=page_path,
                image=np.full((size, size, 3), (30 * i + 10, 80, 120), dtype=np.uint8),
                boxes=[],
                dest=default_typeset_path(page_path, geometry_altered=False),
            )
        )
    return items


@pytest.mark.unit
def test_batch_export_typeset_writes_all_pages(tmp_path: Path) -> None:
    """3 real-baked items -> 3 ``{stem}_typeset.png`` sidecars at the
    ``default_typeset_path`` locations; the ``{"ok", "failed", "total"}``
    contract shape comes back exact."""
    items = _typeset_items(tmp_path, count=3)

    summary = batch_export_typeset(items)

    assert summary == {"ok": 3, "failed": [], "total": 3}
    for item in items:
        assert item.dest.is_file(), f"{item.dest.name} must be written"
        assert item.dest.name == f"{item.path.stem}_typeset.png"


@pytest.mark.unit
def test_batch_export_typeset_none_image_is_failure(tmp_path: Path) -> None:
    """A ``None``-image page lands in ``failed`` with (path, message); the
    other two pages still write (per-page failure isolation, D-04)."""
    items = _typeset_items(tmp_path, count=3)
    items[1].image = None

    summary = batch_export_typeset(items)

    assert summary["ok"] == 2
    assert summary["total"] == 3
    assert len(summary["failed"]) == 1
    failed_path, message = summary["failed"][0]
    assert failed_path == items[1].path
    assert "no image source" in message
    assert items[0].dest.is_file()
    assert items[2].dest.is_file()
    assert not items[1].dest.exists(), "the failed page writes nothing"


@pytest.mark.unit
def test_batch_export_typeset_save_conflict_is_failure(tmp_path: Path) -> None:
    """A pre-existing DIRECTORY at one ``dest`` -> the OSError lands in
    ``failed`` and ok counts the rest (conflicting-filesystem-state
    injection — never a faked loop)."""
    items = _typeset_items(tmp_path, count=3)
    items[1].dest.mkdir(parents=True)  # a directory where the sidecar lands

    summary = batch_export_typeset(items)

    assert summary["ok"] == 2
    assert len(summary["failed"]) == 1
    failed_path, message = summary["failed"][0]
    assert failed_path == items[1].path
    assert isinstance(message, str) and message
    assert items[0].dest.is_file()
    assert items[2].dest.is_file()


@pytest.mark.unit
def test_batch_export_typeset_progress_shape(tmp_path: Path) -> None:
    """D-10 shape: one (percent, page_name) emit per page at the loop top.

    percent = ``int(i / total * 100)`` — the batch_export_ocr formula (the
    existing test_batch_progress_emits asserts 0/33/66 for 3 items); the
    plan-prose (50, 100) pair contradicted its own pinned formula.
    """
    items = _typeset_items(tmp_path, count=3)

    class _Recorder:
        """Signal-shaped progress recorder (mirrors the batch_ocr tests)."""

        def __init__(self) -> None:
            self.calls: list = []

        def emit(self, payload) -> None:
            self.calls.append(payload)

    recorder = _Recorder()
    summary = batch_export_typeset(items, progress_callback=recorder)
    assert summary["ok"] == 3
    assert recorder.calls == [
        (0, "page1.png"),
        (33, "page2.png"),
        (66, "page3.png"),
    ]


@pytest.mark.unit
def test_batch_export_typeset_abort_exact_exception(tmp_path: Path) -> None:
    """A set ``SharableFlag`` raises the EXACT ``worker_thread.Abort`` at the
    loop top BEFORE any file is written (no sidecars exist after)."""
    from manga_ai_studio.gui.worker_thread import Abort, SharableFlag

    items = _typeset_items(tmp_path / "fresh", count=3)

    with pytest.raises(Abort):
        batch_export_typeset(items, abort_flag=SharableFlag(True))

    for item in items:
        assert not item.dest.exists(), "abort at loop top writes nothing"

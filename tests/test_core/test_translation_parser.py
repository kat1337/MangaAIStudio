"""Tests for ``manga_ai_studio/core/translation_parser.py`` (plan 04-02 Task 1).

This is the Phase 4 headless unit suite for the translation parser — the
pure-stdlib module that ingests the typesetting-tool ``[N]: text`` /
``[SFX -N]: *text*`` format (CONTEXT D-15), matches by page-global bubble
number (D-18), and fills ``set_translation`` on the matching boxes.

Decoupling: these tests do NOT import ``PageBox``. ``apply_translations`` keys
off duck-typed boxes exposing ``.bubble_no`` and a ``.set_translation`` method,
so a tiny ``FakeBox`` stands in for the real model (this plan does not depend
on Plan 01 landing; the real PageBox now provides those attributes too).

Security: ASVS V5 (strict anchored regex, skip + report malformed, never crash)
and V7 (parser errors reported not raised) are the load-bearing controls —
``parse_translations`` must NEVER raise on any input.

These tests are pure stdlib; they carry the ``unit`` marker and require NO Qt
and NO model weights (headless CI).
"""

from __future__ import annotations

import types

import pytest


class FakeBox:
    """Duck-typed stand-in for a ``PageBox`` — exposes the two attributes
    ``apply_translations`` reads (``bubble_no`` + ``set_translation``) WITHOUT
    importing PageBox, decoupling this plan from the model layer (Plan 01)."""

    def __init__(self, bubble_no):
        self.bubble_no = bubble_no
        self.set_translation_calls = []

    def set_translation(self, text):
        self.set_translation_calls.append(text)


# ---------------------------------------------------------------------------
# Regex contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bubble_re_matches_number_and_text() -> None:
    """``BUBBLE_RE`` matches ``[1]: hello world`` and captures group(1)="1",
    group(2)="hello world" — the numeric-bubble line shape (D-15)."""
    from manga_ai_studio.core.translation_parser import BUBBLE_RE

    m = BUBBLE_RE.match("[1]: hello world")
    assert m is not None
    assert m.group(1) == "1"
    assert m.group(2) == "hello world"


@pytest.mark.unit
def test_bubble_re_matches_empty_text() -> None:
    """``BUBBLE_RE`` matches ``[12]:`` with EMPTY text — group(2)="". An empty
    translation bubble is still a valid match (D-15 empty-text bubble)."""
    from manga_ai_studio.core.translation_parser import BUBBLE_RE

    m = BUBBLE_RE.match("[12]:")
    assert m is not None
    assert m.group(1) == "12"
    assert m.group(2) == ""


@pytest.mark.unit
def test_sfx_re_matches_sfx_line() -> None:
    """``SFX_RE`` matches ``[SFX -3]: *bang*`` — the SFX line shape. SFX lines
    are RECOGNIZED by the parser but NOT counted as a bubble match (D-15(d)):
    they increment the skipped counter, they are never returned in matches."""
    from manga_ai_studio.core.translation_parser import SFX_RE

    assert SFX_RE.match("[SFX -3]: *bang*") is not None
    assert SFX_RE.match("[SFX -42]: *boom*") is not None


# ---------------------------------------------------------------------------
# parse_translations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_translations_basic_sfx_skipped_blank_ignored() -> None:
    """The headline contract from the plan ``must_haves``:
    ``parse_translations('[1]: hello\\n[SFX -3]: *bang*\\n[2]: world\\n\\n[3]:')``
    returns ``({1:'hello', 2:'world', 3:''}, 1)`` — the SFX line counts as
    skipped (1), the blank line is ignored silently, the empty-text bubble 3
    is still matched."""
    from manga_ai_studio.core.translation_parser import parse_translations

    matches, skipped = parse_translations(
        "[1]: hello\n[SFX -3]: *bang*\n[2]: world\n\n[3]:"
    )
    assert matches == {1: "hello", 2: "world", 3: ""}
    assert skipped == 1


@pytest.mark.unit
def test_parse_translations_garbage_all_skipped_no_exception() -> None:
    """ASVS V5: garbage input — every non-blank unparseable line counts as
    skipped, NO exception. ``parse_translations("random text\\nno brackets")``
    returns ``({}, 2)``."""
    from manga_ai_studio.core.translation_parser import parse_translations

    matches, skipped = parse_translations("random text\nno brackets")
    assert matches == {}
    assert skipped == 2


@pytest.mark.unit
def test_parse_translations_blank_only_returns_empty_zero() -> None:
    """Blank/whitespace-only input yields no matches and zero skipped."""
    from manga_ai_studio.core.translation_parser import parse_translations

    assert parse_translations("") == ({}, 0)
    assert parse_translations("\n  \n\t\n") == ({}, 0)


@pytest.mark.unit
def test_parse_translations_multi_page_markers_skipped_silently() -> None:
    """D-17 multi-page file front-end: a block with ``Page 2:`` markers MERGES
    across markers (the marker carries no translation). Marker lines are
    skipped SILENTLY (they do NOT count toward the skipped counter — they are
    structural, not malformed)."""
    from manga_ai_studio.core.translation_parser import parse_translations

    text = "Page 1:\n[1]: alpha\nPage 2:\n[2]: beta\n[3]: gamma"
    matches, skipped = parse_translations(text)
    assert matches == {1: "alpha", 2: "beta", 3: "gamma"}
    assert skipped == 0


@pytest.mark.unit
def test_parse_translations_unparseable_marker_counts_as_skipped() -> None:
    """A line that LOOKS like a page marker but is malformed (e.g. extra junk)
    is NOT a structural marker — it counts as skipped but does NOT crash
    (ASVS V5/V7). The parser never raises."""
    from manga_ai_studio.core.translation_parser import parse_translations

    # "Page 2 junk" is not a valid page marker (no trailing colon structure),
    # so it is unparseable -> skipped. It must not crash.
    matches, skipped = parse_translations("Page 2 junk\n[1]: ok")
    assert matches == {1: "ok"}
    assert skipped == 1


@pytest.mark.unit
def test_parse_translations_never_raises_on_weird_input() -> None:
    """ASVS V5/V7 hard guard: ``parse_translations`` NEVER raises on any input
    — large paste, weird unicode, binary-ish. It returns ``({}, n)`` for
    fully-garbage input. This is the DoS-surface control (threat T-4-03)."""
    from manga_ai_studio.core.translation_parser import parse_translations

    # Weird unicode.
    matches, skipped = parse_translations("こんにちは世界\n[SFX -1]: *音*")
    assert skipped == 2  # neither matches BUBBLE_RE
    assert matches == {}

    # Binary-ish / control chars — no exception.
    matches2, skipped2 = parse_translations("\x00\x01[1]:\x02 boom\x00")
    assert isinstance(matches2, dict)
    assert isinstance(skipped2, int)

    # Large paste of garbage — no exception, completes.
    big = "\n".join(f"garbage line {i}" for i in range(2000))
    matches3, skipped3 = parse_translations(big)
    assert matches3 == {}
    assert skipped3 == 2000

    # Non-string input must not raise either (it is coerced / handled).
    result = parse_translations(None)  # type: ignore[arg-type]
    assert result == ({}, 0)


@pytest.mark.unit
def test_parse_translations_strips_whitespace() -> None:
    """Leading/trailing whitespace on a bubble line is stripped before the
    text is stored, and leading whitespace before the bracket is tolerated."""
    from manga_ai_studio.core.translation_parser import parse_translations

    matches, skipped = parse_translations("  [1]:   spaced text   \n[2]:a")
    assert matches == {1: "spaced text", 2: "a"}
    assert skipped == 0


# ---------------------------------------------------------------------------
# apply_translations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_translations_matches_and_reports_counts() -> None:
    """``apply_translations({1:'a', 2:'b', 99:'z'}, [FakeBox(1), FakeBox(2)])``
    returns ``(2, 1)`` — 2 applied, 1 unmatched (bubble 99 has no box). Each
    matched box.set_translation was called with the right text."""
    from manga_ai_studio.core.translation_parser import apply_translations

    b1 = FakeBox(1)
    b2 = FakeBox(2)
    applied, unmatched = apply_translations(
        {1: "a", 2: "b", 99: "z"}, [b1, b2]
    )
    assert applied == 2
    assert unmatched == 1
    assert b1.set_translation_calls == ["a"]
    assert b2.set_translation_calls == ["b"]


@pytest.mark.unit
def test_apply_translations_skips_none_bubble_no_silently() -> None:
    """A box whose ``bubble_no`` is None is NEVER matched — it is skipped
    SILENTLY and does NOT count as unmatched (unmatched counts a translation
    that found no box; a None-bubble box simply isn't a candidate)."""
    from manga_ai_studio.core.translation_parser import apply_translations

    b_none = FakeBox(None)
    b1 = FakeBox(1)
    applied, unmatched = apply_translations({1: "x", 5: "y"}, [b_none, b1])
    assert applied == 1
    assert unmatched == 1  # only bubble 5 is unmatched
    assert b_none.set_translation_calls == []
    assert b1.set_translation_calls == ["x"]


@pytest.mark.unit
def test_apply_translations_empty_inputs() -> None:
    """Empty matches or empty boxes are no-ops returning ``(0, 0)`` /
    ``(0, n)`` without error."""
    from manga_ai_studio.core.translation_parser import apply_translations

    assert apply_translations({}, [FakeBox(1)]) == (0, 0)
    assert apply_translations({1: "a"}, []) == (0, 1)


@pytest.mark.unit
def test_apply_translations_accepts_page_no_kwarg() -> None:
    """``apply_translations`` accepts an optional ``page_no`` kwarg (the
    multi-page file-import front-end passes the target page). The kwarg is
    accepted and does not change the match logic in this plan."""
    from manga_ai_studio.core.translation_parser import apply_translations

    b1 = FakeBox(1)
    applied, unmatched = apply_translations({1: "x"}, [b1], page_no=2)
    assert (applied, unmatched) == (1, 0)
    assert b1.set_translation_calls == ["x"]


# ---------------------------------------------------------------------------
# Purity contract (headless, no Qt)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_translation_parser_is_pure_no_qt() -> None:
    """The module is pure stdlib (no Qt) so it is headless-testable and CI
    safe. Importing it must not require a QApplication."""
    from manga_ai_studio.core import translation_parser

    assert callable(translation_parser.parse_translations)
    assert callable(translation_parser.apply_translations)

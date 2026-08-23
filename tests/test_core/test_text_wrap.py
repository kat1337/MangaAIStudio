"""Unit tests for core/text_wrap.py — the Qt-free line breaker
(quick-260822-wvf Task 1).

The breaker owns line breaking for the shared typeset renderer: a
whitespace tokenizer with punctuation/contraction gluing ("atoms") plus an
O(n^2) Knuth-Plass-lite DP that balances lines and penalizes orphan/widow
one-atom lines. Pure pytest — no QApplication, no Qt imports: ``break_lines``
takes a ``Callable[[str], float]`` width measurer, so tests use a
deterministic fixed-width-per-char lambda.
"""

from __future__ import annotations

import pytest

from manga_ai_studio.core import text_wrap
from manga_ai_studio.core.text_wrap import break_lines, tokenize_atoms

# Deterministic measurer: every char (including spaces) is 10 px wide.
CHAR_W = 10.0


def _measure(s: str) -> float:
    return len(s) * CHAR_W


# ---------------------------------------------------------------------------
# tokenize_atoms — contractions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tokenize_keeps_contraction_whole() -> None:
    """An apostrophe between two letters never splits: can't stays one atom."""
    assert tokenize_atoms("I can't go") == ["I", "can't", "go"]


@pytest.mark.unit
def test_tokenize_apostrophe_variants() -> None:
    """All five apostrophe variants between letters stay inside the atom."""
    # Variants: ' U+0027, ’ U+2019, ‘ U+2018, ‛ U+201B, ʼ U+02BC.
    for ap in ("'", "\u2019", "\u2018", "\u201B", "\u02BC"):
        text = f"I can{ap}t go"
        assert tokenize_atoms(text) == ["I", f"can{ap}t", "go"], (
            f"apostrophe variant {ap!r} must not split the contraction"
        )


@pytest.mark.unit
def test_tokenize_rock_n_roll_stays_three_atoms() -> None:
    """'rock 'n' roll' splits on whitespace into exactly three atoms."""
    assert tokenize_atoms("rock 'n' roll") == ["rock", "'n'", "roll"]


# ---------------------------------------------------------------------------
# tokenize_atoms — punctuation gluing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tokenize_trailing_punct_glues_left() -> None:
    """A space-separated trailing punctuation mark glues to the preceding
    atom: 'Are you free ?' -> ['Are', 'you', 'free ?']."""
    assert tokenize_atoms("Are you free ?") == ["Are", "you", "free ?"]


@pytest.mark.unit
def test_tokenize_trailing_punct_set() -> None:
    """The full trailing-glue set: ? ! . , ... : ; ' \" ” ’ ) ] % and the
    fullwidth CJK variants ？！。，… (RESEARCH pitfall 6)."""
    trailing = "? ! . , \u2026 : ; ' \" \u201d \u2019 ) ] % \uff1f\uff01\u3002\uff0c\u2026"
    for p in trailing.split(" "):
        atoms = tokenize_atoms(f"word {p}")
        assert atoms == [f"word {p}"], (
            f"trailing punctuation {p!r} must glue to the preceding atom"
        )


@pytest.mark.unit
def test_tokenize_leading_open_punct_glues_right() -> None:
    """Leading open punctuation glues to the following atom: '( yes' is one
    atom '(yes'; covers ( [ { \" “ « ¿ ¡."""
    leading = "( [ { \" \u201c \u00ab \u00bf \u00a1"
    for p in leading.split(" "):
        atoms = tokenize_atoms(f"{p} yes")
        assert atoms == [f"{p}yes"], (
            f"leading open punctuation {p!r} must glue to the following atom"
        )
    assert tokenize_atoms("(yes") == ["(yes"]


# ---------------------------------------------------------------------------
# break_lines — punctuation never starts a line
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_break_never_starts_line_with_punctuation() -> None:
    """'Are you free ?' in a narrow box: the glued 'free ?' atom wraps whole
    — no line ever starts with '?'."""
    lines = break_lines("Are you free ?", _measure, 80.0)
    assert len(lines) >= 2, "narrow box must wrap"
    for line in lines:
        assert not line.startswith("?"), f"line {line!r} starts with punctuation"
    assert " ".join(lines) == "Are you free ?"


# ---------------------------------------------------------------------------
# break_lines — DP balancing (orphan / widow penalties)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dp_balances_no_one_word_last_line() -> None:
    """Four equal 2-char words that fit exactly 2-per-line (width 50: two
    words + one space = 20+10+20): the balanced 2+2 split beats greedy
    variants leaving a one-word last line (orphan penalty)."""
    words = ["aa", "bb", "cc", "dd"]
    lines = break_lines(words, _measure, 50.0)
    assert lines == ["aa bb", "cc dd"], (
        f"expected the balanced 2+2 split, got {lines!r}"
    )
    assert len(lines[-1].split()) > 1, "no one-word orphan last line"


@pytest.mark.unit
def test_dp_avoids_widow_first_line() -> None:
    """Words where a balanced split exists: the DP must not open with a
    one-word first line (widow penalty) when 2+2 fits.

    'aaaa'(40) 'bb'(20) 'cc'(20) 'dd'(20), width 110:
      [aaaa bb cc][dd]  -> orphan
      [aaaa][bb cc dd]  -> widow
      [aaaa bb][cc dd]  -> balanced (chosen)
    """
    words = ["aaaa", "bb", "cc", "dd"]
    lines = break_lines(words, _measure, 110.0)
    assert lines == ["aaaa bb", "cc dd"], (
        f"expected the balanced split, got {lines!r}"
    )
    assert len(lines[0].split()) > 1, "no one-word widow first line"


@pytest.mark.unit
def test_single_word_renders_as_one_line() -> None:
    """A whole-text single word is that one line (no orphan penalty for the
    only line, n == 1)."""
    assert break_lines("hello", _measure, 60.0) == ["hello"]


@pytest.mark.unit
def test_last_line_raggedness_free_and_penalties_soft() -> None:
    """A short last line is free (raggedness 0); when the ONLY feasible
    layout leaves a one-atom last line, break_lines still returns it —
    penalties are soft, never infeasible."""
    # Three 2-char words (20 px each), width 45: 'aa bb' = 50 > 45, so every
    # word gets its own line; the last line is a 1-atom orphan by necessity.
    lines = break_lines(["aa", "bb", "cc"], _measure, 45.0)
    assert lines == ["aa", "bb", "cc"]


# ---------------------------------------------------------------------------
# break_lines — oversized-atom char-split fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_oversized_atom_char_splits() -> None:
    """A 10-char atom in a width that fits only 4 chars is char-split —
    every emitted line fits within width (per the measurer)."""
    lines = break_lines("abcdefghij", _measure, 45.0)
    assert len(lines) >= 2
    for line in lines:
        assert _measure(line) <= 45.0 + 1e-9, (
            f"line {line!r} ({_measure(line)} px) overflows width 45"
        )
    assert "".join(lines) == "abcdefghij"


@pytest.mark.unit
def test_long_cjk_run_char_splits() -> None:
    """A long no-space CJK run splits so no line overflows (the
    WrapAtWordBoundaryOrAnywhere safety net replacement)."""
    text = "\u3042" * 20  # 20 hiragana, 200 px at CHAR_W
    lines = break_lines(text, _measure, 50.0)
    assert len(lines) >= 4
    for line in lines:
        assert _measure(line) <= 50.0 + 1e-9
    assert "".join(lines) == text


# ---------------------------------------------------------------------------
# break_lines — degenerate inputs + API shape
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_and_whitespace_only_text() -> None:
    """Empty / whitespace-only text yields no lines."""
    assert break_lines("", _measure, 100.0) == []
    assert break_lines("   \t\n  ", _measure, 100.0) == []


@pytest.mark.unit
def test_accepts_pre_tokenized_atoms() -> None:
    """break_lines accepts pre-tokenized atoms (the renderer may tokenize
    once and re-break per candidate size)."""
    lines = break_lines(["Are", "you", "free", "?"], _measure, 80.0)
    assert lines == ["Are you", "free ?"]


@pytest.mark.unit
def test_every_atom_preserved_in_order() -> None:
    """The joined lines reproduce the atom sequence (nothing dropped or
    reordered) for a mixed sentence."""
    text = "Hey ( wait ) for me , okay ? Yes !"
    lines = break_lines(text, _measure, 120.0)
    expected = " ".join(tokenize_atoms(text))
    assert lines and " ".join(lines) == expected


@pytest.mark.unit
def test_qt_free_module() -> None:
    """core/text_wrap.py imports with ZERO Qt references (headless gate)."""
    import inspect

    src = inspect.getsource(text_wrap)
    for token in ("PySide6", "QTextOption", "QFontMetrics", "QApplication"):
        assert token not in src, f"text_wrap.py must not reference {token}"


# ---------------------------------------------------------------------------
# OOM regression (quick-260822-wvf follow-up): a glyph wider than the box
# (kept whole by _split_oversized) used to leave best[j]=INF and
# prev_line_len[j]=0 — the DP reconstruction spun forever appending empty
# lines (unbounded memory, the full-suite 19GB OOM). Must terminate.
# ---------------------------------------------------------------------------


def test_break_lines_terminates_when_single_glyph_exceeds_width() -> None:
    lines = break_lines(
        "WWWW",
        measure=lambda s: len(s) * 100.0,
        width=50.0,
        eps=1.0,
    )
    assert lines == ["W", "W", "W", "W"]


def test_break_lines_mixed_normal_and_oversized_glyphs() -> None:
    # Normal words fit; the oversized glyph gets its own line each time.
    atoms = ["hi", "there", "X", "ok"]
    widths = {"h": 10.0, "i": 10.0, " ": 5.0}
    def measure(s: str) -> float:
        if s == "X":
            return 500.0
        return sum(widths.get(ch, 10.0) for ch in s)
    lines = break_lines(atoms, measure=measure, width=100.0, eps=1.0)
    assert all(isinstance(ln, str) for ln in lines)
    assert "".join(lines).replace(" ", "").replace("X", "") == "hithereok"

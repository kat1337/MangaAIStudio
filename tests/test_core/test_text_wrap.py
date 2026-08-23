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


# ---------------------------------------------------------------------------
# Hard-newline preservation (quick-260822-wvf follow-up): explicit \n in the
# translation field is AUTHOR INTENT — paragraphs wrap independently and are
# never merged; blank lines survive verbatim.
# ---------------------------------------------------------------------------


def test_break_lines_preserves_manual_newlines() -> None:
    lines = break_lines(
        "Ah!\nIt's Sukoya-san",
        measure=lambda s: len(s) * 10.0,
        width=1000.0,  # everything would fit merged — must NOT merge
    )
    assert lines == ["Ah!", "It's Sukoya-san"]


def test_break_lines_wraps_each_paragraph_independently() -> None:
    lines = break_lines(
        "one two\nthree four five",
        measure=lambda s: len(s) * 10.0,
        width=70.0,  # fits 7 chars per line
    )
    assert lines[0] == "one two"  # paragraph 1 untouched by para 2's length
    assert all(ln for ln in lines)


def test_break_lines_preserves_blank_lines() -> None:
    lines = break_lines(
        "top\n\nbottom",
        measure=lambda s: len(s) * 10.0,
        width=1000.0,
    )
    assert lines == ["top", "", "bottom"]


# ===========================================================================
# Standards-grade breaker (quick-260823-hge Task 1): UAX #14 atoms via
# uniseg + pyphen Latin hyphenation + the split_latin signal via
# break_lines_ex(). Fallback degradation tests force the lazy-import miss
# through sys.modules so the module NEVER crashes when uniseg/pyphen are
# absent — mirroring the project's manga-ocr lazy-import pattern.
# ===========================================================================


def _measure_ex(s: str) -> float:
    return len(s) * CHAR_W


# ---------------------------------------------------------------------------
# tokenize_atoms — UAX #14 boundaries (uniseg)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tokenize_uax14_hello_world() -> None:
    """uniseg derives one break after the space: 'Hello, world.' keeps its
    comma attached and yields exactly two atoms."""
    assert tokenize_atoms("Hello, world.") == ["Hello,", "world."]


@pytest.mark.unit
def test_tokenize_herta_stays_one_atom() -> None:
    """'Herta!' is ONE atom under UAX #14 — no break before '!'."""
    assert tokenize_atoms("Herta!") == ["Herta!"]


@pytest.mark.unit
def test_tokenize_japanese_kinsoku() -> None:
    """Japanese wraps between ideographs/clauses; kinsoku shori holds — no
    atom ever STARTS with closing punctuation 、 。 ？！."""
    text = "あい、うえ、お。"
    atoms = tokenize_atoms(text)
    assert atoms, "CJK text must tokenize"
    assert "".join(atoms) == text, "tokenization must not drop characters"
    for atom in atoms:
        assert not atom.startswith(("、", "。", "？", "！")), (
            f"atom {atom!r} starts with closing punctuation (kinsoku violated)"
        )


@pytest.mark.unit
def test_tokenize_japanese_mixed_with_latin() -> None:
    """A mixed run still never splits inside a Latin word: 'Herta!' rides
    whole through a Japanese sentence."""
    atoms = tokenize_atoms("それはHerta!の話")
    joined = "".join(atoms)
    assert "Herta!" in atoms or any(
        "Herta!" in a for a in atoms
    ), f"Herta! must stay whole, got {atoms!r}"
    assert joined.replace(" ", "") == "それはHerta!の話"


@pytest.mark.unit
def test_glue_pass_composes_after_uniseg() -> None:
    """The existing glue passes run AFTER uniseg tokenization (idempotent):
    author-space gluing ('free ?') still works."""
    assert tokenize_atoms("Are you free ?") == ["Are", "you", "free ?"]


@pytest.mark.unit
def test_fallback_uniseg_missing_degrades_to_split() -> None:
    """When uniseg.linebreak cannot be imported (forced via sys.modules),
    tokenize_atoms degrades to whitespace .split() — never raises."""
    import sys

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(sys.modules, "uniseg.linebreak", None)  # ImportError
    monkeypatch.setitem(sys.modules, "uniseg", None)
    try:
        assert text_wrap.tokenize_atoms("hello world") == ["hello", "world"]
        # Glue passes still compose on the fallback path.
        assert text_wrap.tokenize_atoms("Are you free ?") == ["Are", "you", "free ?"]
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# Oversized Latin atoms — pyphen hyphenation + split_latin signal
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_oversized_latin_hyphenates_at_dictionary_point() -> None:
    """'Herta!' wider than the box hyphenates at its dictionary point:
    'Her-' / 'ta!' with the dash MEASURED as part of the first segment;
    split_latin=True."""
    lines, split_latin = text_wrap.break_lines_ex(
        "Herta!", _measure_ex, 55.0, eps=1.0, lang="en_US"
    )
    assert lines == ["Her-", "ta!"], (
        f"expected the pyphen split Her-/ta!, got {lines!r}"
    )
    assert split_latin is True
    for line in lines:
        assert _measure_ex(line) <= 56.0, f"line {line!r} overflows width"


@pytest.mark.unit
def test_hyphen_dash_measured_not_assumed() -> None:
    """The dash is measured with the SAME measurer: with a measurer where
    '-' is wide, no prefix+'-' fits and the atom falls back to char-split."""
    def wide_dash(s: str) -> float:
        return sum(100.0 if ch == "-" else 10.0 for ch in s)

    lines, split_latin = text_wrap.break_lines_ex(
        "simple", wide_dash, 45.0, eps=1.0, lang="en_US"
    )
    # 'sim-' measures 10+10+10+100=130 > 46 — hyphenation can't fit, so the
    # last-resort char-split fires (no dash anywhere).
    assert split_latin is True
    assert all("-" not in ln for ln in lines), f"dash emitted anyway: {lines!r}"


@pytest.mark.unit
def test_all_caps_short_word_skips_hyphenation() -> None:
    """Short ALL-CAPS words (<= _ALL_CAPS_NO_HYPHEN_MAX_LEN letters) skip
    pyphen even when a fitting dictionary point exists (comic convention):
    CRYPTO has the CRYP|TO point that WOULD fit at 55 px — yet no dash."""

    assert len("CRYPTO") <= text_wrap._ALL_CAPS_NO_HYPHEN_MAX_LEN
    lines, split_latin = text_wrap.break_lines_ex(
        "CRYPTO", _measure_ex, 55.0, eps=1.0, lang="en_US"
    )
    assert all("-" not in ln for ln in lines), (
        f"short ALL-CAPS word was hyphenated: {lines!r}"
    )
    assert "".join(lines) == "CRYPTO"
    assert split_latin is True


@pytest.mark.unit
def test_cjk_run_char_split_sets_no_latin_flag() -> None:
    """An oversized CJK run char-splits exactly as before but does NOT set
    split_latin — CJK wrapping is legitimate, not a fit failure."""
    text = "\u3042" * 20
    lines, split_latin = text_wrap.break_lines_ex(text, _measure_ex, 50.0)
    assert len(lines) >= 4
    assert "".join(lines) == text
    assert split_latin is False


@pytest.mark.unit
def test_url_atom_never_gets_a_dash() -> None:
    """URL-like atoms keep the raw per-char fill (no misleading dashes)."""
    url = "https://example.com/verylongpathname"
    lines, split_latin = text_wrap.break_lines_ex(url, _measure_ex, 60.0)
    assert len(lines) >= 2
    assert all(not ln.endswith("-") for ln in lines), f"dashed URL: {lines!r}"
    assert "".join(lines) == url


@pytest.mark.unit
def test_break_lines_wrapper_discards_flag_and_accepts_lang() -> None:
    """break_lines stays a thin wrapper returning lines only (back-compat);
    both entry points accept the lang keyword."""
    assert text_wrap.break_lines("Herta!", _measure_ex, 55.0, lang="en_US") == [
        "Her-",
        "ta!",
    ]


@pytest.mark.unit
def test_fallback_pyphen_missing_char_splits_latin() -> None:
    """When pyphen cannot be imported (forced via sys.modules), an oversized
    Latin atom falls back to the char-split safety net — graceful, no crash."""
    import sys

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(sys.modules, "pyphen", None)  # forces ImportError
    try:
        lines, split_latin = text_wrap.break_lines_ex(
            "Herta!", _measure_ex, 55.0, eps=1.0, lang="en_US"
        )
        assert lines and "".join(lines) == "Herta!"
        assert split_latin is True
    finally:
        monkeypatch.undo()


@pytest.mark.unit
def test_fallback_unknown_lang_skips_hyphenation() -> None:
    """An unknown hyphenation language degrades to the char-split net (the
    language_fallback/KeyError guard) instead of raising."""
    lines, split_latin = text_wrap.break_lines_ex(
        "Herta!", _measure_ex, 55.0, eps=1.0, lang="xx_XX"
    )
    assert lines and "".join(lines).replace("-", "") == "Herta!"
    assert split_latin is True


@pytest.mark.unit
def test_no_import_time_import_error() -> None:
    """The module imports cleanly regardless — lazy imports inside functions
    mean neither uniseg nor pyphen is required at import time."""
    import importlib
    import sys

    assert "uniseg" not in sys.modules or True  # informational only
    mod = importlib.import_module("manga_ai_studio.core.text_wrap")
    assert callable(mod.tokenize_atoms)
    assert callable(mod.break_lines)
    assert callable(mod.break_lines_ex)


@pytest.mark.unit
def test_kinsoku_in_broken_lines() -> None:
    """End-to-end kinsoku: narrow-box Japanese wrap never starts a line with
    、。？！ (the DP consumes UAX #14 atoms)."""
    text = "これはテストです。本当に、動きますか？"
    lines, split_latin = text_wrap.break_lines_ex(text, _measure_ex, 60.0)
    assert len(lines) >= 2
    for line in lines:
        assert not line.startswith(("、", "。", "？", "！")), (
            f"line {line!r} starts with closing punctuation"
        )

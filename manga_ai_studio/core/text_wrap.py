"""Qt-free line breaking for the shared typeset renderer
(quick-260822-wvf Task 1).

Why this exists: Qt's ``WrapAtWordBoundaryOrAnywhere`` is a greedy engine —
it produces orphan fragments like ``can / 't`` (break-anywhere fallback on
apostrophes), ``Are / you / free / ?`` (a space before punctuation is a
legitimate break opportunity to the greedy filler), and one-word ragged
lines with no balance control. The renderer (``gui/text_renderer.py``)
now owns the breaks: it tokenizes text into unbreakable ATOMS here, then
solves an O(n^2) Knuth-Plass-lite DP for the line assignment, and renders
the pre-broken lines as explicit ``\\n`` in a NoWrap document.

Atom rules (RESEARCH §1, extended quick-260823-hge):

- ATOM UNITS derive from UAX #14 line-break opportunities
  (:mod:`uniseg`, lazy import): breaks between CJK ideographs, never
  before 、。？！ closing punctuation (kinsoku shori built in), and a
  Latin word like ``Herta!`` stays ONE atom. Each boundary segment is
  stripped and whitespace-split, so space-separated Latin text keeps its
  author spacing through the glue passes below; when uniseg is absent
  the module degrades to whitespace splitting — never an ImportError.
- TRAILING punctuation glues LEFTWARD onto the preceding atom
  (``? ! . , … : ; ' " ” ’ ) ] %`` plus the fullwidth CJK set
  ``？！。，…``) — ``free ?`` becomes one atom, so no committed line can
  ever start with ``?``. The glue passes run AFTER uniseg tokenization
  and are idempotent on already-glued units.
- LEADING open punctuation glues RIGHTWARD onto the following atom
  (``( [ { " “ « ¿ ¡``) — ``( yes`` becomes one ``(yes`` atom (openers
  chains like ``(( yes`` absorb fully).
- OVERSIZED Latin atoms (measuring wider than the available width) are
  HYPHENATED at pyphen dictionary points — the longest prefix whose
  measured width (prefix + ``-``, dash measured with the same measurer)
  fits — recursing on the suffix. Short ALL-CAPS words are exempt
  (comic convention). When hyphenation is unavailable (pyphen missing,
  unknown language, no fitting point) the greedy per-char fill remains
  the LAST-RESORT safety net for Latin too.
- Oversized NON-Latin atoms (a long CJK run) keep the raw per-char fill
  verbatim — that is legitimate wrapping, not a fit failure. URL-shaped
  atoms also skip the dash (a hyphen would misrepresent the URL).
- :func:`break_lines_ex` reports whether any LATIN word had to be broken
  (hyphenated or char-split) as ``split_latin`` — the auto-fit loop in
  ``gui/text_renderer.py`` treats such a candidate as NOT fitting and
  shrinks the font instead (break-before-shrink ordering fix,
  quick-260823-hge). CJK splits never set the flag.

The DP (RESEARCH §2): ``best[j] = min over i<j of best[i] + cost(i, j)``
with ``cost = raggedness² + demerits``; raggedness = ``width − line_width``
(0 on the final line — a short last line is free); an infeasible line
(wider than ``width + eps``) costs infinity; penalties add ORPHAN when the
last line has exactly one atom (and n > 1), WIDOW when the first line has
one atom, and PER_LINE per line emitted (fewer, fuller lines preferred).
Penalties are soft — when the only feasible layout leaves a one-atom last
line, that layout is still returned.

T-QW-02 mitigation: bubble text is tens of atoms and O(n^2) DP is
negligible there; past :data:`MAX_ATOMS_FOR_DP` the module falls back to a
greedy fill (same atom rules, no balancing) so pathological inputs stay
linear-ish instead of quadratic.

Pure stdlib + optional uniseg/pyphen (lazy, function-local imports) —
ZERO Qt imports (headless-testable; locked by a test). Neither uniseg
nor pyphen is required at import time; both degrade gracefully.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# Tunable demerits (plain floats — RESEARCH A2: textbook Knuth-Plass shape,
# values chosen so structural penalties dominate any raggedness² term at
# comic-bubble widths)
# ---------------------------------------------------------------------------
#: Last line with exactly one atom while more atoms exist (n > 1).
ORPHAN_PENALTY = 1_000_000.0
#: First line with exactly one atom while more atoms exist (n > 1).
WIDOW_PENALTY = 500_000.0
#: Charged per emitted line — prefers fewer, fuller lines (comic-lettering
#: convention: few words per line, but never one-word lines).
PER_LINE_COST = 1.0
#: Charged for an infeasible line (wider than ``width + eps``) — dominates
#: every raggedness/penalty term so feasible layouts win whenever they exist,
#: while an unavoidable oversized glyph still yields a layout.
INFEASIBLE_COST = 1_000_000_000.0
#: Defensive cap (T-QW-02): beyond this many atoms the DP is skipped in
#: favour of a greedy fill — bubble text is tens of atoms, never thousands.
MAX_ATOMS_FOR_DP = 2000

#: Short ALL-CAPS Latin words are never hyphenated (comic-lettering
#: convention — acronyms/caps shouts read better char-split than dashed);
#: quick-260823-hge Task 1.
_ALL_CAPS_NO_HYPHEN_MAX_LEN = 6

#: CJK code-point blocks (quick-260823-hge): a simple script scan used to
#: classify oversized atoms. Anything containing one of these is NOT a
#: Latin word — its char-split is legitimate wrapping, not a poison signal.
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x2E80, 0x2EFF),  # CJK Radicals Supplement
    (0x3000, 0x303F),  # CJK Symbols and Punctuation
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0xFF01, 0xFF60),  # Fullwidth Forms
    (0x1B000, 0x1B001),  # Kana Supplements
    (0x20000, 0x2FA1F),  # CJK Extensions B-F + Compat Supplement
)

#: URL-shaped runs are protected as ONE atom through tokenization — UAX #14
#: would shatter them at ``:`` ``/`` ``.`` delimiters and pyphen would dash
#: the fragments (quick-260823-hge; RESEARCH lists URLs under the no-dash
#: greedy fill).
_URL_RE = re.compile(r"(?:https?://|www\.)\S+")

#: Trailing punctuation glued LEFTWARD (ASCII + typographic + fullwidth CJK,
#: RESEARCH pitfall 6).
_TRAILING_GLUE = frozenset("?!.,\u2026:;'\"\u201d\u2019)]%\uff1f\uff01\u3002\uff0c")
#: Leading open punctuation glued RIGHTWARD.
_LEADING_GLUE = frozenset("([{\"\u201c\u00ab\u00bf\u00a1")


def _opens(atom: str) -> bool:
    """True while ``atom`` consists purely of open punctuation (still
    expecting its closer — absorb the next token)."""
    return bool(atom) and all(ch in _LEADING_GLUE for ch in atom)


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


#: Apostrophe variants that may sit INSIDE an atom between two letters
#: (contractions survive whitespace-only splitting by construction; this set
#: guards the gluing pass below).
_APOSTROPHES = frozenset("'\u2019\u2018\u201B\u02BC")


def _is_contraction_fragment(token: str) -> bool:
    """True for contraction-like atoms such as ``'n'``, ``’tis``, ``‘em``:
    the token OPENS with an apostrophe variant and carries letters — it is
    its own atom and must never glue leftward onto the preceding word
    (``rock 'n' roll`` stays three atoms), unlike a lone closing quote."""
    return (
        bool(token)
        and token[0] in _APOSTROPHES
        and any(_is_word_char(ch) for ch in token[1:])
    )


def _absorb_leading(pairs: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """Pass 1 — leading open punctuation glues rightward
    ("(" + "yes" -> "(yes"; chains like "(( yes" absorb fully). Operates on
    ``(atom, space_before)`` pairs; a merged atom keeps the FIRST token's
    space provenance."""
    out: list[tuple[str, bool]] = []
    i = 0
    n = len(pairs)
    while i < n:
        tok, sp = pairs[i]
        while _opens(tok) and i + 1 < n:
            i += 1
            tok += pairs[i][0]
        out.append((tok, sp))
        i += 1
    return out


def _glue_trailing(pairs: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """Pass 2 — trailing punctuation glues leftward ("free" + "?" ->
    "free ?", keeping the source's separating space so the measured/rendered
    spacing matches the author's intent). A contraction-like fragment
    (``'n'``) is its own atom and never absorbs. Operates on
    ``(atom, space_before)`` pairs; the surviving atom keeps the LEFT
    atom's provenance."""
    glued: list[tuple[str, bool]] = []
    for tok, sp in pairs:
        if (
            glued
            and tok
            and tok[0] in _TRAILING_GLUE
            and not _is_contraction_fragment(tok)
        ):
            prev_tok, prev_sp = glued[-1]
            glued[-1] = (prev_tok + " " + tok, prev_sp)
        else:
            glued.append((tok, sp))
    return glued


def _pairs_from_uniseg(s: str, a: int, b: int, out: list[tuple[str, bool]]) -> None:
    """Append ``(atom, space_before)`` pairs for ``s[a:b]`` using UAX #14
    break opportunities (positions are GLOBAL offsets into ``s`` so the
    first sub-token's adjacency reads the real preceding character)."""
    try:
        from uniseg.linebreak import line_break_boundaries
    except ImportError:
        for k, tok in enumerate(s[a:b].split()):
            sp = (a > 0 and s[a - 1].isspace()) if k == 0 else True
            out.append((tok, sp))
        return
    bnds = [a, *(a + p for p in line_break_boundaries(s[a:b]))]
    if bnds[-1] != b:
        bnds.append(b)
    for lo, hi in zip(bnds, bnds[1:]):
        seg_tokens = s[lo:hi].split()
        # uniseg units carry trailing whitespace — strip via .split()
        # (RESEARCH pitfall 1); inner sub-tokens were space-separated.
        for k, tok in enumerate(seg_tokens):
            sp = (lo > 0 and s[lo - 1].isspace()) if k == 0 else True
            out.append((tok, sp))


def _tokenize_pairs(text: str) -> list[tuple[str, bool]]:
    """Whitespace-free atom units with space provenance
    (quick-260823-hge Stage A).

    UAX #14 boundaries (lazy uniseg import) slice the text; each segment is
    stripped and whitespace-split. Every atom carries ``space_before`` —
    True when whitespace separated it from its neighbour in the SOURCE —
    so the DP joins atoms with their original spacing instead of injecting
    spaces into no-space scripts (Japanese wraps BETWEEN ideographs, never
    with a rendered gap). URL-shaped runs are protected as one atom.
    On ImportError the fallback is plain whitespace splitting.
    """
    s = text.strip()
    if not s:
        return []
    pairs: list[tuple[str, bool]] = []
    pos = 0
    for m in _URL_RE.finditer(s):
        if m.start() > pos:
            _pairs_from_uniseg(s, pos, m.start(), pairs)
        pairs.append((m.group(), m.start() > 0 and s[m.start() - 1].isspace()))
        pos = m.end()
    if pos < len(s):
        _pairs_from_uniseg(s, pos, len(s), pairs)
    return pairs


def tokenize_atoms(text: str) -> list[str]:
    """Split ``text`` into unbreakable ATOMS (RESEARCH §1 + quick-260823-hge).

    Units derive from UAX #14 break opportunities when :mod:`uniseg` is
    importable (whitespace splitting otherwise), then leading-open-
    punctuation tokens glue rightward and trailing-punctuation tokens
    glue leftward (keeping the separating space — ``"free ?"`` glues to
    ``"free ?"`` verbatim). An apostrophe between two letters NEVER
    splits a contraction (all variants ``' ’ ‘ ‛ ʼ`` — UAX #14 agrees),
    and ``rock 'n' roll`` stays three atoms. Japanese wraps between
    ideographs with kinsoku respected. Empty / whitespace-only input
    yields ``[]``.
    """
    raw = _tokenize_pairs(text)
    if not raw:
        return []
    return [atom for atom, _ in _glue_trailing(_absorb_leading(raw))]


def _has_cjk(s: str) -> bool:
    """True when ``s`` contains any CJK-block code point."""
    return any(lo <= ord(ch) <= hi for ch in s for lo, hi in _CJK_RANGES)


def _is_latin_atom(atom: str) -> bool:
    """True for a Latin-script atom: ASCII letters present, no CJK runs
    (quick-260823-hge Stage B classification)."""
    return any("a" <= c <= "z" or "A" <= c <= "Z" for c in atom) and not _has_cjk(
        atom
    )


def _looks_like_url(atom: str) -> bool:
    """URL-shaped atoms keep the raw per-char fill — a hyphen would
    misrepresent the address (quick-260823-hge; RESEARCH lists URLs under
    the no-dash greedy fill)."""
    lowered = atom.lower()
    return "://" in lowered or lowered.startswith("www.")


def _is_short_all_caps(atom: str) -> bool:
    """Short ALL-CAPS Latin words skip pyphen hyphenation (comic-lettering
    convention; :data:`_ALL_CAPS_NO_HYPHEN_MAX_LEN`)."""
    letters = [c for c in atom if c.isalpha()]
    return (
        bool(letters)
        and len(atom) <= _ALL_CAPS_NO_HYPHEN_MAX_LEN
        and all(c.isupper() for c in letters)
    )


_HYPHEN_DICTS: dict[str, object] = {}


def _hyphen_dict(lang: str):
    """Lazily build + cache a :class:`pyphen.Pyphen` dictionary.

    Returns ``None`` when pyphen is missing or the language is unknown
    (guarded via ``language_fallback`` try/except) — the caller then uses
    the char-split safety net. Lazy import: pyphen is NEVER required at
    module import time.
    """
    if lang in _HYPHEN_DICTS:
        return _HYPHEN_DICTS[lang]
    dic = None
    try:
        import pyphen
    except ImportError:
        pyphen = None
    if pyphen is not None:
        try:
            dic = pyphen.Pyphen(lang=pyphen.language_fallback(lang))
        except Exception:  # unknown language — degrade gracefully
            dic = None
    _HYPHEN_DICTS[lang] = dic
    return dic


def _char_split_fill(
    atom: str,
    measure: Callable[[str], float],
    width: float,
    eps: float,
) -> list[str]:
    """Greedy per-char fill (the last-resort oversized-atom net). Uses the
    same measurer the DP uses, so the emitted pieces are feasible by
    construction (a single glyph wider than the width is kept whole —
    unavoidable, and reported via the layout's overflow flag upstream)."""
    pieces: list[str] = []
    cur = ""
    for ch in atom:
        trial = cur + ch
        if cur and measure(trial) > width + eps:
            pieces.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        pieces.append(cur)
    return pieces


def _split_oversized(
    atoms: list[tuple[str, bool]],
    measure: Callable[[str], float],
    width: float,
    eps: float,
    lang: str = "en_US",
) -> tuple[list[tuple[str, bool]], bool]:
    """Handle atoms wider than ``width + eps`` (quick-260823-hge Stage B).

    A LATIN atom first tries pyphen hyphenation at its dictionary points:
    the LONGEST prefix whose measured width (prefix + ``-``, dash measured
    with the SAME measurer — never assumed glyph widths) fits, emitted as
    ``prefix-`` with the suffix handled recursively. Short ALL-CAPS words
    and URL-shaped atoms skip the dash path. Non-Latin atoms (CJK runs)
    and every hyphenation-unavailable case fall back to the raw per-char
    fill verbatim.

    Returns ``((atom, space_before) pairs, split_latin)`` where
    ``split_latin`` is True only when a LATIN word was broken (hyphenated
    or char-split) — CJK splits are legitimate wrapping, not a fit-failure
    signal. Continuation pieces inherit no space (they continue the same
    word).
    """
    out: list[tuple[str, bool]] = []
    split_latin = False
    for atom, sp in atoms:
        if measure(atom) <= width + eps or len(atom) == 1:
            out.append((atom, sp))
            continue
        hyphenatable = (
            _is_latin_atom(atom)
            and not _looks_like_url(atom)
            and not _is_short_all_caps(atom)
        )
        best_prefix = ""
        if hyphenatable:
            dic = _hyphen_dict(lang)
            if dic is not None:
                for prefix, suffix in dic.iterate(atom):
                    if (
                        prefix
                        and suffix
                        and len(prefix) > len(best_prefix)
                        and measure(prefix + "-") <= width + eps
                    ):
                        best_prefix = prefix
        if best_prefix:
            # Breaking a Latin word at a hyphenation point IS a Latin break.
            out.append((best_prefix + "-", sp))
            split_latin = True
            # Recurse on the suffix through the same rules (it may still be
            # oversized; always strictly shorter, so this terminates).
            sub_pairs, sub_split = _split_oversized(
                [(atom[len(best_prefix) :], False)], measure, width, eps, lang
            )
            out.extend(sub_pairs)
            split_latin = split_latin or sub_split
        else:
            pieces = _char_split_fill(atom, measure, width, eps)
            for k, piece in enumerate(pieces):
                out.append((piece, sp if k == 0 else False))
            if _is_latin_atom(atom):
                split_latin = True
    return out, split_latin


def _join_line(
    atoms: list[str], spaces: list[bool], i: int, j: int
) -> str:
    """atoms[i:j] joined with their SOURCE spacing — a single space where
    the author wrote one, nothing between UAX #14-glued units (no-space
    scripts never render an injected gap)."""
    parts = [atoms[i]]
    for k in range(i + 1, j):
        parts.append((" " if spaces[k] else "") + atoms[k])
    return "".join(parts)


def _dp_break(
    atoms: list[str],
    spaces: list[bool],
    widths: list[float],
    space_w: float,
    width: float,
    eps: float,
) -> list[str]:
    """Knuth-Plass-lite O(n^2) DP (RESEARCH §2). Returns the chosen lines."""
    n = len(atoms)
    prefix = [0.0] * (n + 1)
    for i, w in enumerate(widths):
        prefix[i + 1] = prefix[i] + w
    # Prefix count of space-separated atoms — spaces[0] is always False, so
    # the separators INSIDE atoms[i:j] are exactly sp_prefix[j]-sp_prefix[i+1].
    sp_prefix = [0] * (n + 1)
    for i, s in enumerate(spaces):
        sp_prefix[i + 1] = sp_prefix[i] + (1 if s else 0)

    def span_width(i: int, j: int) -> float:
        return prefix[j] - prefix[i] + space_w * (sp_prefix[j] - sp_prefix[i + 1])

    INF = float("inf")
    best = [INF] * (n + 1)
    best[0] = 0.0
    prev_line_len = [0] * (n + 1)  # atom count of the line ENDING at j

    for j in range(1, n + 1):
        # Shrink the line from the left; span width grows as i decreases,
        # so stop at the first infeasible span. The i == j - 1 (single-atom)
        # candidate is ALWAYS costed, even when infeasible — a glyph wider
        # than the box (kept whole by _split_oversized) would otherwise
        # leave best[j] / prev_line_len[j] unset and the reconstruction
        # below would spin forever on k == 0 (unbounded memory).
        i = j - 1
        while True:
            lw = span_width(i, j)
            feasible = lw <= width + eps
            cost = best[i]
            if j != n and feasible:
                cost += (width - lw) ** 2
            cost += PER_LINE_COST + (INFEASIBLE_COST if not feasible else 0.0)
            if (j - i) == 1 and n > 1:
                if j == n:
                    cost += ORPHAN_PENALTY
                if i == 0:
                    cost += WIDOW_PENALTY
            if cost < best[j]:
                best[j] = cost
                prev_line_len[j] = j - i
            if not feasible or i == 0:
                break
            i -= 1
    lines: list[str] = []
    j = n
    while j > 0:
        k = prev_line_len[j]
        if k <= 0:  # defensive: never spin (k is always >= 1 post-fix)
            k = 1
        lines.append(_join_line(atoms, spaces, j - k, j))
        j -= k
    lines.reverse()
    return lines


def _greedy_break(
    atoms: list[str],
    spaces: list[bool],
    widths: list[float],
    space_w: float,
    width: float,
    eps: float,
) -> list[str]:
    """Greedy fill fallback (T-QW-02 cap): same feasibility, no balancing."""
    lines: list[str] = []
    cur_start = 0
    cur_w = 0.0
    have_cur = False
    for idx, (atom, w) in enumerate(zip(atoms, widths)):
        extra = w if not have_cur else w + (space_w if spaces[idx] else 0.0)
        if have_cur and cur_w + extra > width + eps:
            lines.append(_join_line(atoms, spaces, cur_start, idx))
            cur_start, cur_w, have_cur = idx, w, True
        else:
            cur_w += extra
            have_cur = True
    if have_cur:
        lines.append(_join_line(atoms, spaces, cur_start, len(atoms)))
    return lines


def break_lines_ex(
    atoms_or_text: str | Iterable[str],
    measure: Callable[[str], float],
    width: float,
    *,
    eps: float = 1.0,
    lang: str = "en_US",
) -> tuple[list[str], bool]:
    """Break text into balanced lines, reporting Latin word-breaks.

    The full-fidelity entry point (quick-260823-hge): identical line
    output to :func:`break_lines`, plus ``split_latin`` — True when any
    LATIN word had to be broken to fit the width (hyphenated at a pyphen
    point or char-split as last resort). CJK char-splits do NOT set the
    flag. The auto-fit loop in ``gui/text_renderer.py`` treats a
    ``split_latin`` candidate as NOT fitting and shrinks the font instead
    (a layout that had to break a Latin word is a failed fit, not a
    result).

    Args:
        atoms_or_text: Raw text (tokenized via :func:`tokenize_atoms`) or
            pre-tokenized atoms.
        measure: A ``Callable[[str], float]`` width measurer.
        width: Available line width in px.
        eps: Feasibility slack in px.
        lang: Hyphenation language (BCP-47-ish, e.g. ``"en_US"``); unknown
            languages degrade to the char-split safety net.

    Returns:
        ``(lines, split_latin)`` — lines exactly as :func:`break_lines`
        would emit them.
    """
    if isinstance(atoms_or_text, str):
        if not atoms_or_text.strip():
            return [], False
        if "\n" in atoms_or_text:
            out: list[str] = []
            split_latin = False
            for para in atoms_or_text.split("\n"):
                para_lines, para_split = _break_paragraph(
                    para, measure, width, eps, lang
                )
                out.extend(para_lines)
                split_latin = split_latin or para_split
            return out, split_latin
        return _break_paragraph(atoms_or_text, measure, width, eps, lang)
    # Pre-tokenized input gets the same glue passes (idempotent on
    # already-glued atoms) so a bare "?" atom can never start a line
    # even when the caller skipped tokenize_atoms. Provenance defaults to
    # space-separated (the historical join contract for caller-provided
    # atom lists).
    provided = [(a, k > 0) for k, a in enumerate(atoms_or_text) if a]
    pairs = _glue_trailing(_absorb_leading(provided))
    return _break_atom_list(pairs, measure, width, eps, lang)


def break_lines(
    atoms_or_text: str | Iterable[str],
    measure: Callable[[str], float],
    width: float,
    *,
    eps: float = 1.0,
    lang: str = "en_US",
) -> list[str]:
    """Break text into balanced lines that each fit ``width``.

    Thin back-compat wrapper over :func:`break_lines_ex` discarding the
    ``split_latin`` flag (every existing call site/test keeps working).

    Args:
        atoms_or_text: Raw text (tokenized via :func:`tokenize_atoms`) or
            pre-tokenized atoms (the renderer tokenizes once and re-breaks
            per auto-fit candidate size).
        measure: A ``Callable[[str], float]`` width measurer (Qt-free — the
            caller supplies the render font's ``horizontalAdvance``,
            measured at the SAME rounded pixel size the document renders
            at).
        width: Available line width in px.
        eps: Feasibility slack in px (~1.0 default — outline ink extends
            beyond the advance, RESEARCH pitfall 2).
        lang: Hyphenation language (quick-260823-hge).

    Returns:
        The broken lines (atoms joined with their source spacing). Empty /
        whitespace-only input yields ``[]``. Every emitted line measures
        ``<= width + eps`` (oversized atoms are hyphenated or char-split
        first); the assignment minimizes raggedness² + demerits with soft
        orphan/widow/per-line penalties.

    HARD NEWLINES: when given raw text, explicit ``\\n`` breaks are
    AUTHOR INTENT — each source line is wrapped independently and never
    merged with its neighbours (an empty source line yields an empty
    output line, preserving blank lines).
    """
    lines, _ = break_lines_ex(atoms_or_text, measure, width, eps=eps, lang=lang)
    return lines


def _break_paragraph(
    para: str, measure, width: float, eps: float, lang: str = "en_US"
) -> tuple[list[str], bool]:
    """Wrap one hard-line paragraph (no ``\\n`` inside)."""
    pairs = _glue_trailing(_absorb_leading(_tokenize_pairs(para)))
    if not pairs:
        return [""], False  # blank source line preserved verbatim
    return _break_atom_list(pairs, measure, width, eps, lang)


def _break_atom_list(
    pairs: list[tuple[str, bool]], measure, width: float, eps: float, lang: str = "en_US"
) -> tuple[list[str], bool]:
    """Shared atom pipeline: oversized handling -> DP/greedy -> joined lines."""
    pairs, split_latin = _split_oversized(pairs, measure, width, eps, lang)
    atoms = [a for a, _ in pairs]
    spaces = [s for _, s in pairs]
    widths = [measure(a) for a in atoms]
    space_w = max(0.0, measure(" "))

    if len(atoms) > MAX_ATOMS_FOR_DP:
        lines = _greedy_break(atoms, spaces, widths, space_w, width, eps)
    else:
        lines = _dp_break(atoms, spaces, widths, space_w, width, eps)

    return [ln for ln in lines if ln], split_latin


__all__ = [
    "ORPHAN_PENALTY",
    "WIDOW_PENALTY",
    "PER_LINE_COST",
    "INFEASIBLE_COST",
    "MAX_ATOMS_FOR_DP",
    "_ALL_CAPS_NO_HYPHEN_MAX_LEN",
    "tokenize_atoms",
    "break_lines",
    "break_lines_ex",
]

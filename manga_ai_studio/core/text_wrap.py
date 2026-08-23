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

Atom rules (RESEARCH §1):

- Split on whitespace ONLY. A space-separated string therefore keeps an
  apostrophe between two letters inside its atom by construction —
  contractions survive whole (``can't``, all five variants
  ``' ’ ‘ ‛ ʼ``), and ``rock 'n' roll`` stays three atoms.
- TRAILING punctuation glues LEFTWARD onto the preceding atom
  (``? ! . , … : ; ' " ” ’ ) ] %`` plus the fullwidth CJK set
  ``？！。，…``) — ``free ?`` becomes one atom, so no committed line can
  ever start with ``?``.
- LEADING open punctuation glues RIGHTWARD onto the following atom
  (``( [ { " “ « ¿ ¡``) — ``( yes`` becomes one ``(yes`` atom (openers
  chains like ``(( yes`` absorb fully).
- Oversized atoms (a long CJK run, a URL — anything measuring wider than
  the available width) are char-split by :func:`break_lines` so every
  emitted line fits. This replaces the greedy engine's
  break-anywhere safety net for no-space scripts.

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

Pure stdlib + typing — ZERO Qt imports (headless-testable; locked by a
test).
"""

from __future__ import annotations

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
#: Defensive cap (T-QW-02): beyond this many atoms the DP is skipped in
#: favour of a greedy fill — bubble text is tens of atoms, never thousands.
MAX_ATOMS_FOR_DP = 2000

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


def _absorb_leading(atoms: list[str]) -> list[str]:
    """Pass 1 — leading open punctuation glues rightward
    ("(" + "yes" -> "(yes"; chains like "(( yes" absorb fully)."""
    out: list[str] = []
    i = 0
    n = len(atoms)
    while i < n:
        tok = atoms[i]
        while _opens(tok) and i + 1 < n:
            i += 1
            tok += atoms[i]
        out.append(tok)
        i += 1
    return out


def _glue_trailing(atoms: list[str]) -> list[str]:
    """Pass 2 — trailing punctuation glues leftward ("free" + "?" ->
    "free ?", keeping the source's separating space so the measured/rendered
    spacing matches the author's intent). A contraction-like fragment
    (``'n'``) is its own atom and never absorbs."""
    glued: list[str] = []
    for tok in atoms:
        if (
            glued
            and tok
            and tok[0] in _TRAILING_GLUE
            and not _is_contraction_fragment(tok)
        ):
            glued[-1] += " " + tok
        else:
            glued.append(tok)
    return glued


def tokenize_atoms(text: str) -> list[str]:
    """Split ``text`` into unbreakable ATOMS (RESEARCH §1).

    Whitespace splits; then leading-open-punctuation tokens glue rightward
    and trailing-punctuation tokens glue leftward (keeping the separating
    space — ``"free ?"`` glues to ``"free ?"`` verbatim). Because splitting
    is whitespace-only, an apostrophe between two letters NEVER splits a
    contraction (all variants ``' ’ ‘ ‛ ʼ``), and ``rock 'n' roll`` stays
    three atoms. Empty / whitespace-only input yields ``[]``.
    """
    raw = text.split()
    if not raw:
        return []
    return _glue_trailing(_absorb_leading(raw))


def _split_oversized(
    atoms: list[str],
    measure: Callable[[str], float],
    width: float,
    eps: float,
) -> list[str]:
    """Char-split any atom wider than ``width + eps`` (the oversized-atom
    safety net for CJK runs / URLs). Greedy per-char fill using the same
    measurer the DP uses, so the emitted pieces are feasible by
    construction (a single glyph wider than the width is kept whole —
    unavoidable, and reported via the layout's overflow flag upstream).
    """
    out: list[str] = []
    for atom in atoms:
        if measure(atom) <= width + eps or len(atom) == 1:
            out.append(atom)
            continue
        cur = ""
        for ch in atom:
            trial = cur + ch
            if cur and measure(trial) > width + eps:
                out.append(cur)
                cur = ch
            else:
                cur = trial
        if cur:
            out.append(cur)
    return out


def _dp_break(
    atoms: list[str],
    widths: list[float],
    space_w: float,
    width: float,
    eps: float,
) -> list[list[str]]:
    """Knuth-Plass-lite O(n^2) DP (RESEARCH §2). Returns the chosen lines."""
    n = len(atoms)
    prefix = [0.0] * (n + 1)
    for i, w in enumerate(widths):
        prefix[i + 1] = prefix[i] + w

    def span_width(i: int, j: int) -> float:
        # atoms[i:j] joined by single spaces.
        return prefix[j] - prefix[i] + space_w * (j - i - 1)

    INF = float("inf")
    best = [INF] * (n + 1)
    best[0] = 0.0
    prev_line_len = [0] * (n + 1)  # atom count of the line ENDING at j

    for j in range(1, n + 1):
        # Shrink the line from the left; span width grows as i decreases,
        # so stop at the first infeasible span.
        i = j - 1
        while i >= 0:
            lw = span_width(i, j)
            if lw > width + eps:
                break
            cost = best[i]
            if j != n:
                cost += (width - lw) ** 2
            cost += PER_LINE_COST
            if (j - i) == 1 and n > 1:
                if j == n:
                    cost += ORPHAN_PENALTY
                if i == 0:
                    cost += WIDOW_PENALTY
            if cost < best[j]:
                best[j] = cost
                prev_line_len[j] = j - i
            i -= 1

    # Every single-atom line is feasible post-split, so best[n] < INF.
    lines: list[list[str]] = []
    j = n
    while j > 0:
        k = prev_line_len[j]
        lines.append(atoms[j - k : j])
        j -= k
    lines.reverse()
    return lines


def _greedy_break(
    atoms: list[str],
    widths: list[float],
    space_w: float,
    width: float,
    eps: float,
) -> list[list[str]]:
    """Greedy fill fallback (T-QW-02 cap): same feasibility, no balancing."""
    lines: list[list[str]] = []
    cur: list[str] = []
    cur_w = 0.0
    for atom, w in zip(atoms, widths):
        extra = w if not cur else w + space_w
        if cur and cur_w + extra > width + eps:
            lines.append(cur)
            cur, cur_w = [atom], w
        else:
            cur.append(atom)
            cur_w += extra
    if cur:
        lines.append(cur)
    return lines


def break_lines(
    atoms_or_text: str | Iterable[str],
    measure: Callable[[str], float],
    width: float,
    *,
    eps: float = 1.0,
) -> list[str]:
    """Break text into balanced lines that each fit ``width``.

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

    Returns:
        The broken lines (atoms joined by single spaces). Empty /
        whitespace-only input yields ``[]``. Every emitted line measures
        ``<= width + eps`` (oversized atoms are char-split first); the
        assignment minimizes raggedness² + demerits with soft
        orphan/widow/per-line penalties.
    """
    if isinstance(atoms_or_text, str):
        atoms = tokenize_atoms(atoms_or_text)
    else:
        # Pre-tokenized input gets the same glue passes (idempotent on
        # already-glued atoms) so a bare "?" atom can never start a line
        # even when the caller skipped tokenize_atoms.
        provided = [a for a in atoms_or_text if a]
        atoms = _glue_trailing(_absorb_leading(provided))
    if not atoms:
        return []

    atoms = _split_oversized(atoms, measure, width, eps)
    widths = [measure(a) for a in atoms]
    space_w = max(0.0, measure(" "))

    if len(atoms) > MAX_ATOMS_FOR_DP:
        groups = _greedy_break(atoms, widths, space_w, width, eps)
    else:
        groups = _dp_break(atoms, widths, space_w, width, eps)

    return [" ".join(g) for g in groups if g]


__all__ = [
    "ORPHAN_PENALTY",
    "WIDOW_PENALTY",
    "PER_LINE_COST",
    "MAX_ATOMS_FOR_DP",
    "tokenize_atoms",
    "break_lines",
]

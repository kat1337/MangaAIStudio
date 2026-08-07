"""Translation parser for the Phase 4 TEXT-05 subsystem.

Ingests the typesetting-tool ``[N]: text`` / ``[SFX -N]: *text*`` format
(CONTEXT D-15), matches translations to boxes by their page-global bubble
number (D-18), and fills ``set_translation`` on the matching boxes.

This module is the pure-Python algorithm substrate beneath the GUI "Load
Translations" flow (plan 04-07). Building it first as a standalone, headless,
stdlib-only module means plan 04-07 is pure glue — no parsing/matching logic
in the GUI layer (RESEARCH "Don't Hand-Roll": the format is line-oriented and
simple; a focused regex + a dict match is the proven approach).

Consumer contract (the duck-typed attributes this module reads on a box):
- ``box.bubble_no``    — the page-global number to match against (PageBox field,
  plan 04-01; ``None`` boxes are never candidates).
- ``box.set_translation(text)`` — the D-13 MT seam setter (PageBox method,
  plan 04-01). It writes ``payload.translation``.

Because the contract is duck-typed, this module does NOT import PageBox — it
works with any object exposing those two attributes, which keeps it headless
and decoupled from the model layer.

Security (ASVS V5 / V7, threat T-4-03 DoS):
- ``parse_translations`` uses a strict anchored regex ``^\\[(\\d+)\\]:\\s*(.*)$``.
- SFX lines, page markers, and any unparseable line are SKIPPED + REPORTED via
  the skipped counter — never raised.
- The whole parse body is defensive: a malformed input (including a non-str
  argument or binary-ish content) yields ``({}, n)`` rather than an exception.
"""

from __future__ import annotations

import re
from typing import Optional

# Numeric bubble lines:  ``[1]: text``  — capturing (number, text). Empty text
# (``[12]:``) is still a valid match (D-15 empty-text bubble). The text is
# stripped before storage by ``parse_translations``.
BUBBLE_RE = re.compile(r"^\[(\d+)\]:\s*(.*)$")

# SFX lines (recognized but NEVER matched in v1):  ``[SFX -3]: *text*``
# (D-15(d)). These increment the skipped counter; they are not returned in the
# matches dict.
SFX_RE = re.compile(r"^\[SFX\s+-\d+\]:\s*\*.*\*$")

# Multi-page file marker (D-17 file-import front-end):  ``Page 2:``
# Matched lines are skipped SILENTLY (the marker carries no translation — it is
# structural, not malformed), so they do NOT count toward the skipped counter.
PAGE_MARKER_RE = re.compile(r"^Page\s+\d+\s*:", re.IGNORECASE)


def parse_translations(text: str) -> "tuple[dict[int, str], int]":
    """Parse a typesetting-tool-format translation block.

    Returns ``(matches, skipped_count)`` where ``matches`` maps
    ``bubble_no -> translation``.

    Per-line behavior (CONTEXT D-15):
    - Blank / whitespace-only line → ignored (not counted).
    - ``PAGE_MARKER_RE`` line (``Page N:``) → ignored silently (structural
      marker; not counted as skipped — it is not malformed).
    - ``BUBBLE_RE`` line (``[N]: text``) → ``matches[int(N)] = text.strip()``.
      An empty-text bubble (``[N]:``) is still matched with ``""``.
    - Any other line (SFX or unparseable garbage) → ``skipped += 1``.

    ASVS V5 / V7 (threat T-4-03): this function NEVER raises on any input
    (large paste, weird unicode, binary-ish, non-str argument). A fully-garbage
    input yields ``({}, n)``. A non-str / falsy ``text`` is coerced safely.
    """
    try:
        if not isinstance(text, str):
            if text is None:
                return ({}, 0)
            text = str(text)
    except Exception:
        return ({}, 0)

    matches: "dict[int, str]" = {}
    skipped = 0

    try:
        lines = text.splitlines()
    except Exception:
        return ({}, 0)

    for raw_line in lines:
        try:
            line = raw_line.strip()
        except Exception:
            skipped += 1
            continue

        if not line:
            continue  # blank line — ignore silently
        if PAGE_MARKER_RE.match(line):
            continue  # structural page marker — skip silently (not malformed)

        m = BUBBLE_RE.match(line)
        if m:
            try:
                num = int(m.group(1))
            except (ValueError, TypeError):
                skipped += 1
                continue
            text_val = m.group(2).strip() if m.group(2) is not None else ""
            matches[num] = text_val
        else:
            # SFX line or anything else unparseable — recognized but skipped
            # (D-15(d)); count toward the report so the caller can surface it.
            skipped += 1

    return (matches, skipped)


def apply_translations(
    matches: "dict[int, str]",
    boxes: list,
    page_no: Optional[int] = None,
) -> "tuple[int, int]":
    """Fill ``set_translation`` on boxes whose ``bubble_no`` matches.

    Args:
        matches: ``{bubble_no: translation}`` dict (from ``parse_translations``).
        boxes: list of duck-typed boxes (each exposes ``.bubble_no`` and
            ``.set_translation(text)`` — see the module docstring). A box whose
            ``bubble_no`` is ``None`` is NEVER a candidate (skipped silently).
        page_no: optional target page number for the multi-page file-import
            front-end (D-17). Accepted for forward-compatibility; it does not
            change the match logic in this plan.

    Returns:
        ``(applied, unmatched)`` counts. ``applied`` is the number of
        translations written to a matching box; ``unmatched`` is the number of
        translations whose bubble number had no matching box.
    """
    # Index boxes by bubble_no, excluding None-bubble boxes (they are never
    # candidates). The first box seen for a given number wins (matches dict
    # semantics: at most one translation per number).
    box_by_no: "dict[object, object]" = {}
    for b in boxes:
        try:
            no = getattr(b, "bubble_no", None)
        except Exception:
            no = None
        if no is None:
            continue
        if no not in box_by_no:
            box_by_no[no] = b

    applied = 0
    unmatched = 0
    for num, text in matches.items():
        box = box_by_no.get(num)
        if box is not None:
            try:
                box.set_translation(text)
            except Exception:
                # A box setter failure is reported, not raised (ASVS V7).
                unmatched += 1
                continue
            applied += 1
        else:
            unmatched += 1

    return (applied, unmatched)

---
phase: 04-ocr-recognition-text-editing
plan: 02
subsystem: core-utilities (translation parser + reading-order algorithm)
tags: [ocr, text-editing, translation, reading-order, xy-cut, tdd, headless]
requires:
  - Phase 04 Plan 01 PageBox Phase 4 fields (bubble_no, set_translation, manual_override) — provided, but NOT a hard dependency (modules are duck-typed)
provides:
  - manga_ai_studio.core.translation_parser.BUBBLE_RE (compiled regex ^\[(\d+)\]:\s*(.*)$)
  - manga_ai_studio.core.translation_parser.SFX_RE (compiled regex for [SFX -N]: *text*)
  - manga_ai_studio.core.translation_parser.PAGE_MARKER_RE (multi-page file marker Page N:)
  - manga_ai_studio.core.translation_parser.parse_translations(text) -> (dict[int,str], int)
  - manga_ai_studio.core.translation_parser.apply_translations(matches, boxes, page_no=None) -> (applied, unmatched)
  - manga_ai_studio.core.reading_order.reading_order(box_centers_xy, rtl) -> list[int]
  - manga_ai_studio.core.reading_order.assign_bubble_numbers(boxes, rtl=True) -> int
affects:
  - manga_ai_studio/core/translation_parser.py
  - manga_ai_studio/core/reading_order.py
tech-stack:
  added: []
  patterns:
    - strict anchored regex + skip-and-report for untrusted line-oriented text (ASVS V5/V7)
    - XY-Cut column-bucketing with page-geometry-derived tolerance (median inter-center-x gap, not fixed px)
    - duck-typed box contract (.bubble_no / .set_translation / .box.center / .manual_override) decoupling utilities from PageBox
key-files:
  created:
    - manga_ai_studio/core/translation_parser.py
    - manga_ai_studio/core/reading_order.py
    - tests/test_core/test_translation_parser.py
    - tests/test_core/test_reading_order.py
  modified: []
decisions:
  - parse_translations treats Page-marker lines (Page N:) as STRUCTURAL (skipped silently, not counted toward skipped) while SFX + genuinely malformed lines count as skipped — markers carry no translation, they are not malformed input
  - apply_translations matches first-box-wins per bubble_no (dict semantics: at most one translation per number); None-bubble boxes are never candidates and do not count as unmatched
  - reading_order column tolerance = median inter-center-x gap floored to 40px (RESEARCH Pattern 4 line 367 gap-based, NOT median-box-width — gap-based is the recommended default and more robust against real pages than the A2 width alternative)
  - reading_order column clustering walks sorted-unique center-x values starting a new cluster when the gap exceeds tol (simple, deterministic, no dependency on page pixel dims)
  - assign_bubble_numbers reads center via getattr(b, 'box', b).center — accepts both a PageBox (composes a Box) and a bare vendored Box (panelcleaner/structures.py:81 center property)
  - manual_override boxes keep BOTH their bubble_no AND their flag across assign_bubble_numbers (D-16 preserve-manual, threat T-4-04); auto-numbered boxes get manual_override=False
  - parser never raises (ASVS V5/V7 — T-4-03 DoS guard): non-str/None coerced to empty, malformed lines skip+count, box setter failures report-not-raise
metrics:
  duration: 5 min
  completed: 2026-08-06
  tasks: 2
  files: 4
status: complete
---

# Phase 04 Plan 02: Translation Parser + Reading-Order Algorithm Summary

Built the two pure-Python Phase 4 utility modules HEADLESSLY as TDD: the translation parser (D-15/D-17/D-18 — `[N]: text` / `[SFX -N]: *text*` regex ingestion, page-global bubble-number matching, `set_translation` fill, never-raises) and the reading-order algorithm (D-15/D-16 — XY-Cut column-bucketing + per-column top-to-bottom sort, RTL manga / LTR manhwa, preserve-manual conflict policy). Both are pure stdlib (no Qt, no model weights) and duck-typed off `.bubble_no` / `.set_translation` / `.box.center` / `.manual_override` so they land as headless unit tests independent of the PageBox model layer — plan 04-07 (Load Translations dialog + Auto-Number menu wiring) is now pure glue.

## What Was Built

### Task 1 — translation_parser.py — regex parser + bubble-number matcher (TDD)

`manga_ai_studio/core/translation_parser.py`:

- **Three module-level compiled regexes:**
  - `BUBBLE_RE = re.compile(r"^\[(\d+)\]:\s*(.*)$")` — captures `(number, text)`. Empty text (`[12]:`) is still a valid match.
  - `SFX_RE = re.compile(r"^\[SFX\s+-\d+\]:\s*\*.*\*$")` — recognized but NEVER matched in v1 (D-15(d)).
  - `PAGE_MARKER_RE = re.compile(r"^Page\s+\d+\s*:", re.IGNORECASE)` — D-17 multi-page file marker; matched lines are skipped SILENTLY (structural, not malformed).
- **`parse_translations(text) -> (dict[int, str], int)`** — iterates `text.splitlines()`: blank lines ignored, page-marker lines skipped silently (not counted), `BUBBLE_RE` matches stored as `matches[int(num)] = text.strip()`, everything else (SFX or garbage) increments `skipped`. Returns `(matches, skipped)`. The whole body is defensive (ASVS V5/V7, T-4-03 DoS guard): non-str/`None` arguments are coerced to `({}, 0)`, malformed lines skip+count, **never raises**.
- **`apply_translations(matches, boxes, page_no=None) -> (applied, unmatched)`** — builds `box_by_no` over boxes whose `bubble_no` is not None (first-box-wins per number), then for each translation: if a matching box exists call `box.set_translation(text)` and `applied += 1`, else `unmatched += 1`. Boxes with `bubble_no is None` are never candidates and do NOT count as unmatched. The optional `page_no` kwarg is accepted for the D-17 file-import front-end forward-compatibility. Box setter failures are reported not raised (V7).

### Task 2 — reading_order.py — XY-Cut RTL/LTR + preserve-manual (TDD)

`manga_ai_studio/core/reading_order.py`:

- **`reading_order(box_centers_xy, rtl) -> list[int]`** — XY-Cut column-bucketing + per-column sort:
  - `n <= 1` returns `list(range(n))` (edge cases: single box `[0]`, zero boxes `[]`).
  - Column tolerance derived from the page's OWN geometry: `col_tol = max(40.0, median inter-center-x gap)` over sorted unique x values (RESEARCH Pattern 4 line 367 gap-based, NOT median-box-width — the recommended default and more robust than the A2 width alternative). The 40px floor keeps near-coincident layouts from fragmenting.
  - Cluster the sorted-unique center-x values: start a new column cluster when the gap to the previous cluster-start exceeds `col_tol` (simple, deterministic, no page-pixel-dim dependency).
  - Bucket each box into its column, carrying `(cy, cx, index)`.
  - Order columns via `sorted(columns.keys(), reverse=rtl)` — the single-line RTL (manga, rightmost first) / LTR (manhwa, leftmost first) switch.
  - Within each column, sort by center-y ascending (top-to-bottom).
  - The result is always a permutation of `range(n)`.
- **`assign_bubble_numbers(boxes, rtl=True) -> int`** — reads each box's center off `getattr(b, 'box', b).center` (the duck-typed vendored-Box accessor; PageBox composes a Box whose `.center` returns `((x1+x2)//2, (y1+y2)//2)` per panelcleaner/structures.py:81). Computes `order = reading_order(centers, rtl)`, then walks it: boxes with `manual_override=True` are SKIPPED (they keep their existing `bubble_no` AND their flag — D-16 preserve-manual, threat T-4-04), non-overridden boxes get `bubble_no = next_no` (1..N) and `manual_override = False`. Returns the count of auto-numbered boxes. Empty list is a no-op returning 0. A box without a usable center is pushed off-page (`inf, inf`) so it sorts last but still counts (V7 reported-not-raised discipline).

## Verification

```
python -m pytest tests/test_core/test_translation_parser.py tests/test_core/test_reading_order.py -q
# 30 passed

python -m pytest tests/ -q
# 306 passed, 1 failed (PRE-EXISTING — see Deviations)
```

Acceptance criteria verified for both modules:
- Both importable (`python -c "from ... import ..." → ok`).
- translation_parser.py: 1 stdlib `import re`, 0 Qt imports.
- reading_order.py: 0 Qt imports, `reverse=rtl` switch present (line 123).
- `parse_translations_never_raises_on_weird_input` passes (T-4-03 DoS guard).
- `manual_override_preserved` passes (T-4-04 tampering guard).

## Deviations from Plan

None — the plan executed exactly as written. Both modules follow the PATTERNS.md pure-module header (CONTEXT D-15 citation, `from __future__ import annotations`, stdlib-only imports, `@pytest.mark.unit`-compatible) and the RESEARCH §Code Examples regex/algorithm contract verbatim.

One implementation-detail confirmation (not a plan deviation — the plan explicitly delegated the choice to the executor):
- **Column-tolerance derivation**: the plan's `<action>` noted "use median GAP, not median width (RESEARCH Pattern 4 line 367... gap-based is the recommended default)". Implemented median inter-center-x gap floored to 40px, matching the plan's recommended default.

No auth gates. No architectural changes (Rule 4). No auto-fixes (Rules 1-3) — both modules were green on first implementation pass.

## Known Stubs

None. Both modules are fully implemented; no placeholder text/TODO/FIXME in any new code path. The `page_no` kwarg on `apply_translations` is accepted and documented but does not change match logic in this plan — that is by design (the D-17 file-import front-end is plan 04-07; this plan's contract is the `(applied, unmatched)` tuple + skipped count the GUI reads).

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): a real-event body-drag move lands a box at `(69,69,129,129)` instead of the asserted `(70,70,130,130)` — a 1px drag-coordinate rounding difference. Verified failing identically against pristine pre-04-01 source (commit `210a178`) in plan 04-01. It is a GUI drag-simulation rounding issue that does NOT exercise `translation_parser` or `reading_order` (pure-stdlib headless modules with no GUI/drag code path). Re-confirmed failing in this plan's full-suite run (`1 failed, 306 passed`). Logged to `.planning/phases/04-ocr-recognition-text-editing/deferred-items.md`; not fixed.

## TDD Gate Compliance

Plan frontmatter `type: tdd`. Gate sequence observed (separate RED `test(...)` commit then GREEN `feat(...)` commit per task):

- **Task 1**: RED `738273e` — `test(04-02): add failing tests for translation_parser` (15 failing tests, ImportError before the module existed). GREEN `2782480` — `feat(04-02): implement translation_parser (parse + apply)` (15/15 passing). RED failure confirmed before implementation.
- **Task 2**: RED `c567c86` — `test(04-02): add failing tests for reading_order` (15 failing tests, ImportError). GREEN `cba67fa` — `feat(04-02): implement reading_order (XY-Cut RTL/LTR + preserve-manual)` (15/15 passing). RED failure confirmed before implementation.

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — implementations were clean on first pass.

## Self-Check: PASSED

Created files:
- FOUND: manga_ai_studio/core/translation_parser.py
- FOUND: manga_ai_studio/core/reading_order.py
- FOUND: tests/test_core/test_translation_parser.py
- FOUND: tests/test_core/test_reading_order.py

Commits:
- FOUND: 738273e (test(04-02): add failing tests for translation_parser)
- FOUND: 2782480 (feat(04-02): implement translation_parser)
- FOUND: c567c86 (test(04-02): add failing tests for reading_order)
- FOUND: cba67fa (feat(04-02): implement reading_order)

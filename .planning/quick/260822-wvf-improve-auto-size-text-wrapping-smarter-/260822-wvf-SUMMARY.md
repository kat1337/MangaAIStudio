---
task: quick-260822-wvf
status: complete
completed: 2026-08-23
---

# Quick Task 260822-wvf Summary: Smarter auto-size text wrapping

## What Was Done

Owned line breaking for typeset text (research → plan → 3 tasks), replacing Qt's greedy
`WrapAtWordBoundaryOrAnywhere` engine with a tokenizer + Knuth-Plass-lite DP that eliminates
orphan breaks like `can / 't`, `don' / t`, and `Are / you / free / ?`.

### Commits
- `f260083` test(quick-260822-wvf): failing tests for Qt-free line breaker (tokenize_atoms + break_lines)
- `7d9f488` feat(quick-260822-wvf): Qt-free line breaker — tokenize_atoms + Knuth-Plass-lite break_lines
- `d7a4fea` feat(quick-260822-wvf): wire owned line breaking into layout() — both paths, NoWrap documents
- `bf8091f` fix(quick-260822-wvf): DP reconstruction hang/OOM when a glyph exceeds box width *(orchestrator-applied)*

### Implementation
1. **Task 1** — New Qt-free `core/text_wrap.py`: `tokenize_atoms()` (whitespace-only splitting keeps
   contractions whole across all apostrophe variants; trailing punctuation glues leftward incl. CJK
   fullwidth set; leading openers glue rightward) + `break_lines()` O(n²) DP with orphan/widow/
   per-line penalties, char-split oversized-atom fallback, greedy fallback past 2000 atoms.
2. **Task 2** — `gui/text_renderer.py`: `_build_document` gained a wrap kwarg; both manual and
   auto-fit paths pre-break lines at the same rounded pixelSize via `QFontMetricsF.horizontalAdvance`,
   render as explicit `\n` in NoWrap documents. `_line_rects` now iterates ALL blocks. Vertical mode
   untouched. Live overlay and bake/export share the seam (D-01 consistency).
3. **Task 3** — Regression tests lock the three reported bad cases; full suite green.

### OOM Incident (executor interrupted; orchestrator-completed)
The executor's full-suite run OOM'd (19GB observed by user). Root cause found and fixed in `bf8091f`:
in `_dp_break`, a single glyph wider than `width + eps` (kept whole by `_split_oversized`) left
`best[j] = INF` / `prev_line_len[j] = 0`, so DP reconstruction spun forever appending empty lines.
Fix: single-atom candidates are always costed (with `INFEASIBLE_COST` dominating), reconstruction
has a defensive k==0 guard. Repro: `tests/test_gui_export.py::test_batch_export_writes_all_pages`
(aborted >10GB before; 0.7GB peak after).

## Verification
- Full suite: **1063 passed, 0 failed**, peak RAM 3.07GB (pinned interpreter).
- Targeted: test_text_wrap 19 passed; test_gui_export 12 passed.

## Deviations
- SUMMARY written by orchestrator (executor session interrupted twice mid-run).
- `INFEASIBLE_COST` constant added beyond plan scope (OOM fix).

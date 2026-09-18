---
task: quick-260823-hge
status: complete
completed: 2026-08-23
---

# Quick Task 260823-hge Summary: Standards-grade line breaker (uniseg + pyphen)

## What Was Done

Replaced hand-rolled wrapping heuristics with standards-based Unicode line breaking,
following user-requested online research of open-source tools. Key insight from research:
no manga typesetter has anything worth porting (all plain greedy); adopt `uniseg` +
`pyphen` instead.

### Commits
- `e7a54d3` test(quick-260823-hge): failing UAX #14 / pyphen hyphenation / split_latin breaker tests
- `f53f1af` feat(quick-260823-hge): standards-grade core breaker — uniseg UAX #14 atoms, pyphen hyphenation, split_latin signal
- `83b53b6` test(quick-260823-hge): failing auto-fit ordering regressions
- `4fa6489` feat(quick-260823-hge): auto-fit rejects Latin-split candidates before shrinking to the floor
- `a28b5cd` test(quick-260823-hge): drop cached hyphen dicts in pyphen-missing fallback test

### Implementation
1. **Task 1 — Core breaker** (`core/text_wrap.py`): atom derivation now on uniseg UAX #14
   boundaries (correct CJK per-glyph breaks with kinsoku shori; existing punctuation-glue
   passes composed on top). Latin words that must break use pyphen dictionary hyphenation
   points with a measured "-" appended; ALL-CAPS short words exempt; char-split demoted to
   last resort for genuinely unbreakable runs (CJK handled by UAX #14, URLs etc.).
   New `break_lines_ex() -> (lines, split_latin)`; `break_lines()` back-compat wrapper.
   Lazy imports with graceful ImportError fallbacks (manga-ocr pattern); both packages in
   pyproject.toml.
2. **Task 2 — Ordering-bug fix** (`gui/text_renderer.py`): the "Herta!" → "Hert/a!" bug was
   an ORDERING bug — `_split_oversized` split any oversized atom and the auto-fit fit-test
   (vertical-only) accepted the split candidate as fitting before the font ever shrank.
   Now `layout()`'s auto-fit loop rejects candidates whose break required splitting a Latin
   word (`AND NOT split_latin`) and shrinks toward the floor instead; manual path keeps its
   honest vertical overflow report.
3. Dependencies installed into the pinned pyenv 3.14.2 env and declared in pyproject.toml.

## Verification
- Targeted: test_text_wrap + test_typeset_layout + test_gui_export = 78 passed.
- Full suite: **1087 passed, 0 failed**, peak RAM 2.94GB (pinned interpreter).

## Deviations
- Executor session went unresponsive twice mid-run; orchestrator completed the tail
  (committed the final one-line test fix `a28b5cd`, ran verification, wrote this summary).
- Killed one stray 3GB python process left behind by an interrupted executor run.

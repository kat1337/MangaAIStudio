---
phase: quick
plan: 260825-u9q
subsystem: core/project-io
tags: [project-persistence, masks, stale-mask, sanitization, tdd]
requires:
  - T-08-06 per-box mask size cross-check (plan 08-04)
  - D-15 seam fields mask/std_dev/fill_color in pagebox_to_json/json_to_pagebox
provides:
  - stale-tolerant load path (_pagebox_mask_from_json returns None on size mismatch, logs warning)
  - coherent std_dev/fill_color nulling when a mask value decoded stale
  - save-side guard so a resized-after-fit box can never serialize an unloadable file
affects: [main_window project-open path, clipboard paste path (both inherit via json_to_pagebox), save path]
tech-stack:
  added: []
  patterns: [sanitize-dont-reject for decodable-but-stale data, fit-derived-trio-dies-together]
key-files:
  created: []
  modified:
    - manga_ai_studio/core/project_io.py
    - tests/test_core/test_project_io.py
decisions:
  - "Decode-level garbage still raises ProjectFormatError byte-identically — only the SIZE-MISMATCH branch softened (T-QKN-01 kept)"
  - "std_dev/fill_color nulled together with a stale mask (measured against different geometry = meaningless); inpaint_override survives as user intent"
  - "loguru warning names both sizes on every drop (T-QKN-03 observability)"
metrics:
  duration: ~25 min
  completed: 2026-08-25
status: complete
actuals:
  tokens: 2500   # chars/4 over the realized diff (179 insertions / 23 deletions across 2 files)
  tasks: 2
  commits: 3
---

# Quick Task 260825-u9q: Fix Project Load Failure for Valid v1 Manifests Summary

**One-liner:** Stale per-box masks (box resized after fit) now load sanitized to `mask/std_dev/fill_color = None` instead of raising `ProjectFormatError`, and `pagebox_to_json` refuses to serialize stale masks so future saves are always loadable.

## What Was Built

### Task 1 — Load-side stale-mask sanitization (TDD)

**RED** (`1b43a18`): two failing tests encoding the exact user scenario.
- Test A (`test_stale_mask_after_resize_user_scenario_loads`): fitted PageBox (box `[0,0,100,40]`, mode-"1" mask 100x40, `std_dev=12.5`, `fill_color=(10,20,30)`, override `"always"`) serialized via `pagebox_to_json`, then box overridden to `[0,0,80,60]`. Asserted `json_to_pagebox` succeeds with all three fit fields None + override/style/payload preserved. Failed with `ProjectFormatError` before the fix.
- Test B (rewrote `test_per_box_mask_size_mismatch_rejected` → `test_per_box_mask_size_mismatch_loads_sanitized`): crafted 4x4-PNG-vs-100x40-box dict loads with all three None; matching-size case still returns a real mode-"1" image.

**GREEN** (`41ae865`) in `manga_ai_studio/core/project_io.py`:
- `_pagebox_mask_from_json`: decode try/except wrap left byte-identical (binascii/PIL garbage still raises); the size-mismatch branch now logs a loguru warning naming both sizes (T-QKN-03) and returns `None`. Docstring documents the stale-tolerant contract.
- `json_to_pagebox`: captures `mask_raw`; when a mask VALUE was present but decoded to None (stale), forces `std_dev = None` and `fill_color = None` before constructing the PageBox. The float-coercion, fill-color triple validation, and override enum blocks untouched (they run earlier and stay authoritative).

### Task 2 — Save-side stale-mask guard

RED test first (`test_save_side_stale_mask_serializes_null`, failed with the stale mask serializing to base64), then GREEN (`5d95d07`):
- `pagebox_to_json`: computes `mask_stale = pb.mask is not None and pb.mask.size != (box_w, box_h)`; when stale emits `"mask": None, "std_dev": None, "fill_color": None` — mirroring the load-side semantics exactly. Override/style/payload emitted verbatim; matching-size masks serialize exactly as before.

## Real-Project Verification (constraint requirement)

Loaded the actual affected project headlessly via the pinned interpreter:

```
C:\Users\Stella\Downloads\[Yumobi] Sukoya-san to Seifuku Ecchi! (Sukoya Kana) [Digital]\[Yumobi] Sukoya-san to Seifuku Ecchi! (Sukoya Kana) [Digital].mas-project
```

- `load_project(manifest.json)` OK — version 1, 24 pages
- All 24 pages through `load_page_file` + `parse_page_entries` — zero exceptions
- 30 boxes decoded via `json_to_pagebox` — zero exceptions
- **23 stale masks detected and sanitized to None**, each with the loguru warning naming both sizes (e.g. `mask size (409, 1340) does not match the box dims 740x1815`)
- **RESULT: zero exceptions** — this exact file previously died with `ProjectFormatError: per-box mask size ... does not match the box dims`

The 23/30 stale ratio matches the root cause: quick-260822-gnq made refit manual-only, so any resize of a fitted box left its mask at old cropped dims while the saver serialized both verbatim.

## Verification

| Check | Result |
|-------|--------|
| tests/test_core/test_project_io.py | 36 passed |
| Full suite (pinned interpreter) | **1140 passed**, 0 failed (1138 baseline + new tests) |
| Real affected project headless load | 24 pages / 30 boxes / 23 stale masks sanitized / 0 exceptions |

## Deviations from Plan

None — plan executed exactly as written.

## Auth Gates

None occurred.

## Known Stubs

None.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 RED | 1b43a18 | test(quick-260825-u9q): add failing stale-mask sanitization tests |
| 1 GREEN | 41ae865 | feat(quick-260825-u9q): stale masks load sanitized instead of rejecting the project |
| 2 | 5d95d07 | feat(quick-260825-u9q): save-side stale-mask guard + full-suite green |

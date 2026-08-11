---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 04
subsystem: typesetting (TRAN-02)
tags: [typesetting, persistence, d07, ocr-export, mas-serialization]
requires: [phase-05-export, plan-07-01]
provides: [style-persistence, ocr-json-style-block]
affects: [box-model, project-io, ocr-export, gui-export]
tech-stack:
  added: []
  patterns: [TextStyle.to_dict as the SINGLE dict spelling shared by both writers (Pitfall 6); optional-key load + from_dict V5 coercion on every read path (Pitfall 8)]
key-files:
  created: []
  modified:
    - manga_ai_studio/core/project_io.py
    - manga_ai_studio/core/ocr_export.py
    - tests/test_core/test_project_io.py
    - tests/test_core/test_ocr_export.py
    - tests/test_gui_export.py
decisions:
  - "OCR_JSON_VERSION bumped \"1\" -> \"2\" (Task 2 checkpoint, Option A): the D-07 style block extends the published D-19 contract, and the bump signals the extension explicitly so downstream consumers can branch on the version to detect style presence (RESEARCH A5). One-way door resolved by the human."
  - "\"style\" is an OPTIONAL .mas load key: legacy Phase 5 files without it load with TextStyle() defaults, never ProjectFormatError (Pitfall 8); a \"style\": null round-trips to the default style, not None."
  - "Block-level style placement in _ocr.json (never line level) — per-box flat style (D-06), matching the block's existing box/vertical/text shape."
metrics:
  duration: ~45m
  completed: 2026-08-11
status: complete
actuals:
  tokens: 4081    # chars/4 over the realized diff (16,325 chars: 5 commits, +321/-22 lines)
  tasks: 3        # tasks executed (1 auto-tdd, 1 checkpoint:decision, 1 auto-tdd)
  commits: 5      # cf3e0f2, 3bd32a2, 4880784, dc7879c, b44f88e
---

# Phase 7 Plan 4: Persist per-box style — .mas page-field + _ocr.json block-level style (D-07)

**One-liner:** the per-box `TextStyle` joins both published projections — `pagebox_to_json`/`json_to_pagebox` (`.mas`) and `build_page_ocr_json` (`_ocr.json`) — backward-compatible (legacy files load with defaults), one dict spelling under test, V5-coerced on load, with `OCR_JSON_VERSION` bumped to `"2"` by the human Task 2 checkpoint (the D-19 one-way contract extension).

## What Was Built

- **`core/project_io.py` (MOD)** — `pagebox_to_json` emits `"style": pb.style.to_dict() if pb.style is not None else None` (the D-15 seam discipline — style is the new projected field, mask/std_dev still never written); `json_to_pagebox` reads the OPTIONAL `"style"` key AFTER the byte-identical required-key validation and builds `style = TextStyle.from_dict(d.get("style"))` — absent/`null` → `TextStyle()` defaults (Pitfall 8: legacy Phase 5 `.mas` files keep loading), crafted dicts clamp through the V5 boundary (width_px 300→256, opacity 1.5→1.0 — T-07-09), never reaching the renderer raw.
- **`core/ocr_export.py` (MOD)** — `build_page_ocr_json`'s block dict gains `"style": pagebox.style.to_dict() if pagebox.style is not None else None` at BLOCK level (never line level — D-06 flat per-box style); `OCR_JSON_VERSION` bumped `"1"` → `"2"` (Task 2 checkpoint Option A); module docstring D-19 example + version comment updated. The batch path emits it too (single builder).
- **`tests/test_core/test_project_io.py` (extended)** — `test_style_field_round_trip` (field-wise equality, never identity), `test_legacy_mas_without_style_loads_with_defaults` (Pitfall 8), `test_style_none_round_trip` (json null → defaults), `test_style_v5_clamped_on_load` (T-07-09), `test_required_keys_unchanged` (validation lock).
- **`tests/test_core/test_ocr_export.py` (extended)** — `test_style_block_shape` (exact block JSON pin incl. `"style"`), `test_version_is_task2_decision` (`"2"`), `test_style_none_block` (null + key set), `test_style_block_one_spelling` (byte-equal to `TextStyle.to_dict()` — Pitfall 6); existing key-set assertions extended.
- **`tests/test_gui_export.py` (extended)** — the two on-disk D-19 version pins (`test_export_single_pristine_page`, `test_batch_export_writes_all_pages`) updated `"1"` → `"2"`.

## Tasks Executed

| Task | Name | Result |
|------|------|--------|
| 1 (auto, tdd) | .mas style field — write projection + optional-key load + legacy defaults | RED (4 new tests fail; required-keys lock passes) → GREEN (20/20 pass); full suite 665 passed |
| 2 (checkpoint:decision, gate=blocking) | OCR_JSON_VERSION policy (D-07 one-way door) | Human selected **Option A — bump to "2"**; implemented + pinned under test; full suite 665 passed |
| 3 (auto, tdd) | _ocr.json style block at block level + version per decision | RED (3 style-block tests fail; version test already green) → GREEN (12/12 pass); full suite 669 passed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Plan-driven test contract update] `test_gui_export.py` pinned the D-19 version `"1"` on disk**
- **Found during:** Task 2 (full suite run after the bump)
- **Issue:** The checkpoint context anticipated updating `test_ocr_export.py`'s version assertions, but two GUI tests also asserted the published version on disk (`test_export_single_pristine_page:147`, `test_batch_export_writes_all_pages:437`) — the `"1"` → `"2"` bump broke them. They are the same D-19 contract pins, asserted at the file-write layer.
- **Fix:** Updated both assertions to `"2"` with a comment referencing the Task 2 decision; the tracer test's docstring updated to match.
- **Files modified:** `tests/test_gui_export.py`
- **Commit:** 4880784 (Task 2)

## Key Decisions

- **OCR_JSON_VERSION = "2" (Task 2 checkpoint, human-selected Option A).** The D-07 style block extends the published D-19 shape; bumping signals the extension explicitly so consumers can branch on the version to detect style presence (RESEARCH A5 recommended; D-19 one-way door resolved before the writer changed). The D-19 key set (box/vertical/text/translation/bubble_no/origin/lines) is otherwise unchanged.
- **`"style"` stays OUT of the required-key set** — it is read via `d.get("style")` and `TextStyle.from_dict` (None/absent → defaults). `test_required_keys_unchanged` locks the validation byte-identical.
- **One dict spelling everywhere** — both writers call `TextStyle.to_dict()`; `test_style_block_one_spelling` + `test_style_block_shape` pin it (Pitfall 6); grep gate confirms exactly two writers in `core/`.

## Verification

- `pytest tests/test_core/test_project_io.py tests/test_core/test_ocr_export.py -q` → **32 passed**
- Full suite `pytest -q` → **669 passed, 0 failed** (665 prior state + 4 new Task 3 tests)
- Grep gate: `rg '"style"' manga_ai_studio/core/` → exactly two writers (project_io.py:197 `pb.style.to_dict()`, ocr_export.py:179 `pagebox.style.to_dict()`), both calling `to_dict()` — the remaining hits are comments/docstrings
- TDD gate compliance: RED `test(...)` commits (cf3e0f2, dc7879c) precede GREEN `feat(...)` commits (3bd32a2, b44f88e)

## Threat Surface

The changes map 1:1 onto the plan's threat model — no NEW surface beyond it:

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-07-09 (Tampering/DoS — crafted style dict on load) | mitigate | `TextStyle.from_dict` type-checks + clamps on every read path (project_io `json_to_pagebox`); optional key degrades to defaults, never a crash; `test_style_v5_clamped_on_load` locks width_px 300→256 / opacity 1.5→1.0 |
| T-07-10 (Tampering — spelling drift) | mitigate | ONE spelling (`TextStyle.to_dict()`) in both writers, pinned by `test_style_block_shape` + `test_style_block_one_spelling`; version policy fixed by the human Task 2 decision |

No threat flags.

## Known Stubs

None. The `_ocr.json` style block is written on every export (single builder — batch path included); `.mas` loads with defaults when style is absent by design (backward compatibility, not a stub).

## Self-Check

- [x] `manga_ai_studio/core/project_io.py` — `"style"` writer + optional reader present
- [x] `manga_ai_studio/core/ocr_export.py` — block-level `"style"` + `OCR_JSON_VERSION = "2"`
- [x] Tests exist: `test_style_field_round_trip`, `test_legacy_mas_without_style_loads_with_defaults`, `test_style_v5_clamped_on_load`, `test_required_keys_unchanged`, `test_style_block_shape`, `test_version_is_task2_decision`, `test_style_none_block`, `test_style_block_one_spelling`
- [x] Commits exist: cf3e0f2, 3bd32a2, 4880784, dc7879c, b44f88e (`git log`)
- [x] Full suite green (669 passed)

## Self-Check: PASSED

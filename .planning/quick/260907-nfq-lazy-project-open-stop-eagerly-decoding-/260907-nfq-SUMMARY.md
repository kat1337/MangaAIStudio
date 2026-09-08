---
phase: quick-260907-nfq
plan: 01
status: complete
subsystem: core-persistence + gui-session
tags: [lazy-loading, oom, project-io, memory, batch, export]
requires: []
provides:
  - "Selective .mas container decompression (load_page_file names=)"
  - "parse_page_meta (meta-only head of parse_page_entries)"
  - "ImageFile.source_mas / embedded_size lazy slots"
  - "MainWindow._materialize_page_state gap-fill seam (visit full tier / batch light tier / save PREPARE full tier)"
  - "_page_image_source source-.mas embedded-pixel tier"
affects:
  - "Project open memory: O(1 pages) pixel residency instead of O(page count)"
tech-stack:
  added: []
  patterns:
    - "Selective container decompression (table walk skips unrequested LZMA blobs)"
    - "Gap-fill materialization (never overwrites non-None slots)"
    - "Meta-only open with pre-swap displayed-page materialization (corruption gate preserved)"
key-files:
  created: []
  modified:
    - manga_ai_studio/core/project_io.py
    - manga_ai_studio/core/image_file.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_project_io.py
    - tests/test_gui_project.py
    - tests/test_gui_batch.py
decisions:
  - "Lazy open keeps the build-before-swap corruption gate: every page's meta head is parsed+validated before the session swap; only blob-level corruption defers (page 0 fully materializes pre-swap — corrupt-first-page dialog preserved)"
  - "Gap-fill materialization: batch-detect writes and D-11 outgoing flushes always win over disk state — _materialize_page_state fills ONLY still-None slots"
  - "Light-tier composite rule: the legacy flat mask restores for batch clean only when the page has no plane entries; plane-carrying pages recompose"
  - "Save fidelity by non-action: untouched pages' .mas files are never rewritten (byte-identical); eligible lazy pages materialize from their source .mas, never the pristine original; materialization failure = WR-02 whole-save abort"
  - "Folder sessions and single-.mas opens stay eager through _build_image_file_from_parsed (keeps every existing folder-session save test byte-identical)"
metrics:
  duration: ~2h 45m (includes one harness-timeout resume)
  completed: 2026-09-08
  tasks: 3
  commits: 5
actuals:
  tokens: 59000
  tasks: 3
  commits: 5
---

# Quick Task 260907-nfq — Lazy project open: stop eagerly decoding every page — Summary

**Lazy project open with gap-fill materialization:** project open now decompresses only `meta.json`/`original.json` per page and decodes pixels for the displayed first page only; every other page is a lazy `ImageFile` (source-`.mas` back-pointer + embedded meta dims + eager boxes) materialized on demand at page visit, batch dispatch (mask state only), and save PREPARE — cutting open-time retained pixel memory from O(pages) to O(1 page).

## What Was Built

### Task 1 — Core layer (commit 6e2090f)
- `load_page_file(path, names=None)` (`manga_ai_studio/core/project_io.py`): selective decompression — the entry table still walks in full (name/length sanity + version/magic checks byte-identical), unrequested blobs advance `off` but are never handed to `lzma.decompress` and are omitted from the result; `MAX_ENTRY_DECOMPRESSED` still bounds every decompression that happens; a requested-but-corrupt entry still raises `ProjectFormatError`.
- `parse_page_meta(entries)`: exactly the head of `parse_page_entries` (require meta.json → json decode → isinstance-dict → `validate_meta` → optional original.json) returning `{"meta", "original"}`; `parse_page_entries` refactored to start from it — zero behavior change to the full parse.
- `ImageFile` (`manga_ai_studio/core/image_file.py`): new `source_mas: Path | None` + `embedded_size: tuple[int, int] | None` slots (None defaults); `current_image` docstring rewritten to the lazy contract.

### Task 2 — Lazy open + visit seam + save round-trip (commits e5a4afb RED, 4a00a88 GREEN)
- `_load_project_session` meta loop: `load_page_file(page, names=_LAZY_OPEN_ENTRY_NAMES)` → `parse_page_meta` → `_build_lazy_image_file` (D-06 original ref + verified flag, `geometry_altered`, eager boxes via `json_to_pagebox`, `embedded_size`, `source_mas`; pixels/mask/planes None). Every meta is parsed before the swap — the structural corruption gate is intact.
- Page 0 fully materializes BEFORE the swap (`_materialize_page_state(..., want_pixels=True)`; failure raises `ProjectFormatError` → the existing corrupt-project dialog) — corrupt-first-page all-or-nothing preserved.
- `_materialize_page_state(imf, idx, want_pixels)`: re-reads `imf.source_mas`, full `parse_page_entries` + `_decode_embedded_image`; gap-fills ONLY still-None slots (each plane individually, `current_image` only when `want_pixels`, composite `mask` when `want_pixels` OR no plane entries); `ProjectFormatError`/`OSError` → logged warning + False; never touches dirty/boxes/flags; GUI-thread only (T-QHH-01).
- `on_page_selected`: materialize step after incoming-page resolution, before the Step-3 branch — success takes the embedded branch (the placeholder path NEVER reaches `set_image_from_path`, the 05-05 rule); failure degrades via the existing path-fallback UX.
- `_save_project` PREPARE: eligible lazy pages materialize inside the payload loop; failure appends to `unresolved_names` and skips the page → the WR-02 whole-save abort (no silent pristine-pixel embed).
- `_build_image_file_from_parsed` refactored onto extracted module-level `_decode_embedded_image` (embedded PNG decode + CR-03 bomb wrap + WR-6 dims cross-check) and `_resolve_original_ref` (D-06 block) — folder sessions and single-`.mas` opens stay eager through it.

### Task 3 — Batch + export seams (commits e373e3b RED, ab6ae4a GREEN)
- `_dispatch_batch` light tier (after the Bug-D flush, before args build): never-visited lazy pages light-materialize (mask planes + legacy composite only, no pixels) on the GUI thread; False is non-fatal (per-page failure isolation).
- `_page_image_source` tier 2: `source_mas` → load + parse + `_decode_embedded_image` inside try/except falling through to the existing chain; tier order documented (current_image authoritative → source .mas → cleaned → path → None).
- `_dispatch_batch_ocr_export`: `elif imf.embedded_size is not None` arm — geometry-altered lazy pages export exact meta dims instead of the on-disk original's.

## Test Results (pinned interpreter: `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`)

| Suite | Result |
|---|---|
| Task 1 verify: `tests/test_core/test_project_io.py` | 52 passed (8 new; RED first: 7 failed) |
| Task 2 verify: `test_gui_project.py` + `test_project_io.py` | 143 passed incl. `test_gui_detection_boxes.py` (RED first: 7 failed, 2 pins) |
| Task 3 verify: `test_gui_batch.py` + `test_gui_project.py` | 82 passed (RED first: 3 failed) |
| Full suite | **1322 passed, 0 failed** (3:05) — strict superset of the 1303 baseline (+8 +8 +3 new, 1:1 rewrites); the known Qt viewport-grab flake did not fire |

Constraint #1 (save pixel loss) is pinned three ways: zero-visit Save As round-trip compares per-page embedded pixels/planes/boxes exactly against the original containers (strict for never-visited pages); the portable embedded-only variant (originals deleted) round-trips exactly; a missing lazy `.mas` at save aborts the whole save via the WR-02 dialog.

## Deviations from Plan

1. **[Rule 3 — blocking-fixture fix, Task 1]** The corrupt-blob fixtures must be crafted at the container level (`_pack_entry` records + correct header count): `save_page_file` LZMA-compresses whatever payload it is handed, so a garbage "payload" would have been a valid compressed stream. Test-side only.
2. **[Execution note, Task 2]** The plan placed save-PREPARE materialization in a separate pass "before the payload loop"; implemented at the top of that same payload loop (after `snapshot_serials`, same location) with `continue` on failure — behavior identical (materialize → on failure `unresolved_names` + WR-02 abort), one pass instead of two.
3. **[Contract-change rewrites, Task 2]** Two pre-existing tests pinned the eager contract and were rewritten to the lazy contract: `test_open_project_populates_all_current_images` → `test_open_project_lazy_open_contract` (per plan) and `test_open_folder_on_project_dir_loads_project_session` (l3w router test in the same plan-listed file) now asserts only the displayed page holds pixels.
4. **[Test-fidelity calibration, Task 2]** The zero-visit round-trip compares the DISPLAYED page's plane entries by content rather than presence: reopening any project normalizes the flushed transparent composite into explicit zeros `automask.bin`/`mask.bin` entries (pre-existing eager-flow behavior, semantically equal); and meta-boxes style is compared through a null↔`TextStyle()`-defaults normalizer (the documented `json_to_pagebox` D-07 contract). Never-visited pages are compared strictly.

No authentication gates. No CLAUDE.md/AGENTS.md conflicts (AGENTS.md's pinned interpreter was used for every pytest run). No stubs introduced; all `<verify>` commands ran green.

## TDD Gate Compliance

Type `tdd` per task: each task has a `test(...)` commit (RED) followed by a `feat(...)` commit (GREEN) — 6e2090f follows a RED run verified in-session (Task 1's RED committed together with GREEN after a fixture correction, failures shown in the log above), e5a4afb→4a00a88 and e373e3b→ab6ae4a are explicit RED→GREEN pairs.

## Threat Model Follow-Through

- T-nfq-01/T-nfq-02: `parse_page_meta` is a strict subset of `parse_page_entries`' validation; selective decompression shrinks the decompressed-blob surface (unrequested blobs never decompressed; memlimit still applies to requested ones).
- T-nfq-03: deferred blob corruption surfaces as the corrupt-project dialog (page 0 at open), the path-fallback UX (visit), or the WR-02 unresolved abort (save) — all covered by tests (`test_corrupt_first_page_aborts_open`, `test_corrupt_later_page_opens_then_degrades_on_visit`, `test_save_with_missing_lazy_mas_aborts`).
- T-nfq-04: materialization warnings log page names/indices only.

No new trust surface outside the plan's register.

## Out of Scope (untouched, per plan)

F2 (LRU eviction), F3 (history slimming), F4/F5 (churn), F6 (save-payload slimming), `_load_folder`/`_load_single_page_mas` laziness (stay eager through `_build_image_file_from_parsed`), thumbnail decoding, RSS instrumentation.

## Self-Check: PASSED

- Files exist: `manga_ai_studio/core/project_io.py`, `manga_ai_studio/core/image_file.py`, `manga_ai_studio/gui/main_window.py`, `tests/test_core/test_project_io.py`, `tests/test_gui_project.py`, `tests/test_gui_batch.py` — all modified and committed.
- Commits verified in `git log`: 6e2090f, e5a4afb, 4a00a88, e373e3b, ab6ae4a.
- Full suite exit 0: 1322 passed, 0 failed (`/tmp/full_suite.log`).

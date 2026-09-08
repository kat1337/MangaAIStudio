---
phase: quick-260907-nfq
verified: 2026-09-08T01:33:57Z
status: human_needed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Quick Task 260907-nfq — Lazy project open — Verification Report

**Task Goal:** Stop eagerly decoding every page's embedded image, mask, and planes at project load; materialize on demand (page visit, batch iteration, save) so a 25-page high-res (~35 MP/page) project no longer jumps to >6 GB RAM at open, with ZERO save-pixel-loss regression (never-visited lazy pages round-trip byte-faithfully).
**Verified:** 2026-09-08T01:33:57Z
**Status:** human_needed (all 7 must-haves verified in code + tests; 1 real-world confirmation remains)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (PLAN must_haves.frontmatter — the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Open decodes pixels for ONLY the displayed first page; other pages lazy with meta-derived state; open-time pixel memory O(1 pages) | ✓ VERIFIED | `_load_project_session` meta-only loop (`main_window.py:3851-3864`, `load_page_file(..., names=_LAZY_OPEN_ENTRY_NAMES)` + `parse_page_meta`); `_build_lazy_image_file` (:3589-3627) leaves `current_image`/`mask`/4 plane slots None while setting `source_mas`, `embedded_size`, eager boxes, D-06 flag. Residency probe in `test_open_project_lazy_open_contract` (tests/test_gui_project.py:410) asserts `populated == [0]` — passing. |
| 2 | First page still displays immediately at open (embedded image + planes/composite + boxes) — open behavior unchanged | ✓ VERIFIED | Pre-swap `self._materialize_page_state(page_files[0], 0, want_pixels=True)` (:3873-3877) then `_display_page_state(page_files[0])` (:3890, unchanged code). Contract test asserts canvas shows the 60×60 embedded image at open. |
| 3 | First navigation materializes a never-visited page identically; the placeholder path NEVER reaches `set_image_from_path` on success (05-05 rule) | ✓ VERIFIED | `on_page_selected` materialize step (:2460-2471) runs before the Step-3 branch; success takes the embedded `set_image_from_numpy_page` branch (:2484-2487). `test_lazy_visit_materializes_page_identically` (:2115) green — pixel-equal to a fresh project_io decode. |
| 4 | Save never loses pixels: zero-visit Save As round-trip; portable embedded-only round-trip; missing/corrupt source `.mas` at save aborts whole save via WR-02 (never silent pristine-pixel embed) | ✓ VERIFIED | PREPARE materialization of eligible lazy pages (:3100-3114) → failure appends to `unresolved_names` → WR-02 whole-save abort (:3185-3196, before Worker dispatch — nothing written); `_page_image_source` tier 2 = source-`.mas` embedded extraction (:2951-2962, never the pristine original). Tests green: `test_zero_visit_save_as_round_trip` (:2154, np.array_equal per-page), `test_portable_project_save_as_round_trip` (:2224), `test_save_with_missing_lazy_mas_aborts` (:2249 — asserts `saved is False`, dialog shown, ZERO `.mas` written), `test_lazy_incremental_save_untouched_mas_bytes_identical` (:2278 — byte-identical untouched `.mas`). |
| 5 | Batch detect/clean dispatch light-materializes never-visited pages' mask planes WITHOUT materializing pixels | ✓ VERIFIED | `_dispatch_batch` light tier (:8436-8444): `want_pixels=False` for `source_mas`-set, `current_image is None` pages, on the GUI thread; non-fatal False. `test_batch_clean_dispatch_light_materializes_lazy_planes` (tests/test_gui_batch.py:1242) asserts planes present AND `current_image is None` at the worker — green. |
| 6 | Batch OCR export dims for lazy pages from `embedded_size` (exact for geometry-altered pages); typeset export renders lazy pages from embedded pixels | ✓ VERIFIED | OCR-export `elif imf.embedded_size is not None` arm (:8089-8093); typeset resolves via `_page_image_source` tier 2. Tests green: `test_batch_ocr_export_uses_embedded_dims_for_lazy_pages` (:1303), `test_batch_typeset_export_gets_embedded_pixels_for_lazy_pages` (:1358). |
| 7 | Boxes/flags/thumbnails stay eager; per-page history reset guards hold; full suite green under pinned interpreter incl. the rewritten eager-open test | ✓ VERIFIED | Boxes parsed eagerly in `_build_lazy_image_file` (:3617-3620); `test_lazy_visit_state_round_trip_no_bleed` (:2312) green pins the 260826-1by guards; `test_open_project_lazy_open_contract` is the 1:1 rewrite and is green. Full suite under `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`: 1320 and 1321 passed across two runs — the 1-2 failures are the PRE-EXISTING Qt viewport-grab flake (see Full-Suite note below), proven failing at the pre-task commit. |

**Score:** 7/7 truths verified (0 present-but-behavior-unverified — every invariant above is exercised by a named passing test)

### Full-Suite Note (flake triage — not a regression)

SUMMARY claimed "1322 passed, 0 failed". My runs:

| Run | Command (pinned interpreter) | Result |
|---|---|---|
| Task 1 verify | `pytest tests/test_core/test_project_io.py -q` | 52 passed (0.96s) |
| Task 2 verify | `pytest tests/test_gui_project.py tests/test_core/test_project_io.py -q` | 109 passed (23.8s) |
| Task 3 verify | `pytest tests/test_gui_batch.py tests/test_gui_project.py -q` | 82 passed (27.9s) |
| Full suite #1 | `pytest -q` | 1320 passed, 2 failed (2:15) |
| Full suite #2 | `pytest -q` | 1321 passed, 1 failed (4:15) |

The two failures are NOT regressions of this task:

1. `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` — viewport pixel-grab assertion (`green < 200`, got 206) on a bare canvas; touches none of this task's code paths. Fails 3/3 in isolation AND in its file run at the PRE-TASK commit `ea6469a` (verified in a temp worktree). This is exactly the "known Qt viewport-grab flake" class the SUMMARY references (it happened not to fire during the executor's run; it fired during mine).
2. `tests/test_gui_ocr_grab.py::test_canvas_copy_text_requested_wired_to_handler` — passes in isolation at HEAD; failed only in full-suite ordering (order-dependent Qt signal test). Passed in full-suite run #2.

Conclusion: the lazy-open/save/batch changes are regression-free; the suite is green modulo a documented pre-existing flake class unrelated to this task.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `manga_ai_studio/core/project_io.py` | Selective `names` decompression in `load_page_file`; `parse_page_meta`; `parse_page_entries` reuses its head | ✓ VERIFIED | `load_page_file(path, names=None)` skips `lzma.decompress` for unrequested entries while walking the full table (:148-215); `parse_page_meta` (:738-772); `parse_page_entries` starts from `parse_page_meta(entries)` (:800-802). Wired: consumed by the open loop and by the full-parse battery. |
| `manga_ai_studio/core/image_file.py` | `source_mas` + `embedded_size` slots; lazy `current_image` docstring | ✓ VERIFIED | Fields at :130-131 with None defaults; docstring rewritten to the lazy contract (:81-100). Wired: consumed at main_window.py:2469/2951/3109/8089/8443. |
| `manga_ai_studio/gui/main_window.py` | `_decode_embedded_image`, `_resolve_original_ref`, `_build_lazy_image_file`, `_materialize_page_state`, meta-only open loop + pre-swap page-0, visit seam, save PREPARE, batch light tier, OCR dims tier | ✓ VERIFIED | All present (:141, :144, :175, :3589, :3629, :3851-3877, :2466-2471, :3100-3114, :8436-8444, :8089-8093). Gap-fill semantics verified in code: fills ONLY still-None slots (:3672-3689), never touches dirty/boxes/flags. |
| `tests/test_core/test_project_io.py` | Selective-decompression + parse_page_meta battery | ✓ VERIFIED | 8 new tests (:1328-1428+) incl. the corrupt-unrequested-blob non-decompression probe (:1366). 52 passed. |
| `tests/test_gui_project.py` | Lazy-open contract battery | ✓ VERIFIED | 9 new/rewritten lazy tests (:410, :2115, :2154, :2224, :2249, :2278, :2312, :2351, :2383) — corrupt-first-page abort and corrupt-later-page-degrade included. All green. |
| `tests/test_gui_batch.py` | Batch light-materialization + export seam tests | ✓ VERIFIED | 3 tests (:1242, :1303, :1358) — all green. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `_load_project_session` meta loop | `ImageFile.source_mas` | `_build_lazy_image_file(parsed, page_path, ...)` (:3626) | ✓ WIRED | Back-pointer is the page container path; no consumer re-derives it. |
| `source_mas` | `_materialize_page_state` | `imf.source_mas` re-read (:3660-3664) | ✓ WIRED | Consumed by visit (:2471), save PREPARE (:3110), batch dispatch (:8443). |
| `source_mas` | `_page_image_source` tier 2 | load + parse + `_decode_embedded_image` (:2951-2962) | ✓ WIRED | Try/except falls through to cleaned → path → None on failure. |
| `on_page_selected` Step 3 | materialized `current_image` | branch on `imf.current_image is not None` after materialize (:2466-2487) | ✓ WIRED | Reuses existing D-11 restore steps; zero new restore logic; placeholder never auto-loads on success. |
| Corruption gate | pre-swap all-or-nothing | meta parse of ALL pages (:3851-3864) + page-0 full materialization raising `ProjectFormatError` (:3873-3877) | ✓ WIRED | `test_corrupt_first_page_aborts_open` (:2351) + `test_open_corrupt_project_keeps_session` (:501) green. |
| Save format | unchanged entry shape | full tier fills composite `mask` when `want_pixels` (:3685-3687); `_page_plane_keys` path untouched | ✓ WIRED | Pinned by `test_zero_visit_save_as_round_trip` (strict per-page entry comparison) + incremental byte-fidelity test. |

### Data-Flow Trace (Level 4)

Not applicable in the UI-rendering sense — these are state-management seams. The equivalent check (do real decoded bytes flow through the seams?) is covered exactly by the round-trip tests: zero-visit Save As reopen compares per-page embedded pixels, planes, and boxes against the ORIGINAL containers (`np.array_equal` / strict entry comparison) — never-visited pages compared strictly. No hardcoded/empty data sources found in any new code path.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Core battery | `pytest tests/test_core/test_project_io.py -q` | 52 passed | ✓ PASS |
| Lazy open/visit/save battery | `pytest tests/test_gui_project.py tests/test_core/test_project_io.py -q` | 109 passed | ✓ PASS |
| Batch/export seam battery | `pytest tests/test_gui_batch.py tests/test_gui_project.py -q` | 82 passed | ✓ PASS |
| Full-suite regression sweep | `pytest -q` (×2) | 1320 / 1321 passed; failures = pre-existing flake (fails at baseline commit ea6469a too) | ✓ PASS (modulo pre-existing flake) |

Named behavioral tests confirmed present and passing inside the green file runs: residency probe (`populated == [0]`), zero-visit round-trip, portable round-trip, missing-`.mas` WR-02 abort (asserts NOTHING written), incremental byte-fidelity, visit/undo no-bleed, corrupt-first-page abort, corrupt-later-page degrade, batch light tier, OCR embedded dims, typeset embedded pixels.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| quick-260907-nfq | 260907-nfq-PLAN.md | Lazy project open with zero save-pixel loss | ✓ SATISFIED | All 7 must-have truths verified above. No `.planning/REQUIREMENTS.md` mapping exists (quick task); no orphaned requirement IDs. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No TBD/FIXME/XXX/HACK debt markers in any of the 6 modified files | — | — |
| (none) | — | No stubs/placeholders: every new function is a full implementation (selective decompression, gap-fill materializer, tier-2 extraction) | — | — |

Commits verified in git: 6e2090f, e5a4afb, 4a00a88, e373e3b, ab6ae4a (RED→GREEN pairs for Tasks 2 and 3; Task 1 combined). Working tree source matches HEAD ab6ae4a.

### Out of Scope (explicitly NOT gaps)

Per the plan's scope guard, these remain open RAM concerns for FUTURE tasks and were not part of this goal: F2 LRU eviction, F3 history slimming, F4/F5 recompose/restore churn, F6 save-payload slimming, `_load_folder`/single-`.mas` laziness (still eager by design — keeps folder-session save tests byte-identical), thumbnail decode churn, RSS instrumentation. The climb-to-18GB during sustained editing (OOM map S1/S2) is a separate concern from this task's open-baseline goal.

### Human Verification Required

### 1. Real-project open memory + first-visit visual sanity

**Test:** Open the real 25-page high-res (~35 MP/page) project in the app (via `start.bat`). Watch RAM at open (Task Manager / Process Explorer). Then click through 3-4 never-visited pages in the sidebar (including one with saved mask strokes) and back.
**Expected:** RAM at open stays near the app baseline + ~1 page of pixels (hundreds of MB, not >6 GB). Each visited page renders its embedded image, mask/planes, and boxes exactly as before the lazy change; no "Couldn't open file" dialog on any healthy page.
**Why human:** The O(1)-residency mechanism is test-pinned (`populated == [0]`), but the >6 GB → not outcome on the user's actual project is a real-world RSS observation. GUI launch is forbidden in verification, and RSS instrumentation was explicitly scoped out of this task (OOM map F7), so no automated RSS probe exists.

### Gaps Summary

None. All 7 must-have truths are verified in code and exercised by passing named tests; all artifacts exist, are substantive, and are wired; the corruption gates, save-abort honesty, and byte-fidelity contracts are pinned by tests. The two full-suite failures encountered are a pre-existing Qt viewport-grab flake proven present at the pre-task commit (ea6469a), not a regression. One real-world confirmation (open-memory observation on the actual 25-page project) remains and is routed to human verification.

---

_Verified: 2026-09-08T01:33:57Z_
_Verifier: ZCode (gsd-verifier)_

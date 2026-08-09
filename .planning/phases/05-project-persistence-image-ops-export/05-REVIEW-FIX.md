---
phase: 05-project-persistence-image-ops-export
fixed_at: 2026-08-08T12:30:00Z
review_path: .planning/phases/05-project-persistence-image-ops-export/05-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-08-08T12:30:00Z
**Source review:** `.planning/phases/05-project-persistence-image-ops-export/05-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (3 critical, 6 warning — fix_scope `critical_warning`; the 4 Info findings are out of scope)
- Fixed: 9
- Skipped: 0

## Fixed Issues

### CR-01: Image edits on non-current pages are lost on navigation and on project save (D-05/D-15 contract break)

**Files modified:** `manga_ai_studio/gui/main_window.py`, `tests/test_gui_project.py`
**Commit:** `d849b23` (source), `21e84a7` (test contract update)
**Applied fix:** (a) `_apply_geometry_op` now writes the post-op image back into `ImageFile.current_image` (`new_image.copy()`, Pitfall-2 detached) after the canvas write-back; `_on_inpaint_finished` reads the composited full image back from the canvas (`get_image_numpy()`, detached) after `set_image_from_numpy(bbox=...)` — reading back is required because the bbox path composites only the masked region and `result_rgb` alone is not the displayed state. A companion flush in `_apply_undo_result` (image kind) keeps `current_image` authoritative after Ctrl+Z/redo so an undone op is never resurrected by navigation/save. (b) `on_page_selected` Step 3 now prefers `imf.current_image` when present (the authoritative D-05 state; disk `set_image_from_path` is the fallback for pages never loaded into memory — the D-06 missing-original case is subsumed since embedded images populate `current_image`). (c) `_page_image_source` returns `imf.current_image` first for EVERY page (the `_last_page_index` special-case is gone), so a save after editing page 2 embeds the post-op image.
**Status:** `fixed: requires human verification` — this is coordinated state-handling logic (three coupled sites plus the undo companion); Tier 1/2 verification (syntax + full suite) passed, but a manual pass over the rotate→navigate→save repro from the review is recommended before the phase ships.

### CR-02: Open Folder / Open Image leaves stale project identity — Ctrl+S silently overwrites the previous project

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `4178b69`
**Applied fix:** `_set_pages` (the shared entry for Open Image / Open Folder / `_load_folder` / `_open_single_image` / drag-drop) now resets `self._project_dir = None` and `self._project_name = None` when it rebuilds the session. Project loads (`_load_project_session`, `_load_single_page_mas`) set their own identity and never route through `_set_pages`, so their dir/name are untouched.

### CR-03: Corrupt `.mas` mask entry escapes the ProjectFormatError boundary and crashes the app

**Files modified:** `manga_ai_studio/core/project_io.py`, `manga_ai_studio/gui/main_window.py`
**Commit:** `7382c2f`
**Applied fix:** `parse_page_entries` now checks `len(mask_bytes) == mask_h * mask_w` before reshaping and raises `ProjectFormatError` on mismatch (the dims are guaranteed ints in range by `validate_meta`'s `_coerce_int`), so a crafted mask blob surfaces the corrupt-project dialog instead of an unhandled numpy `ValueError`. In `_build_image_file_from_parsed`, `Image.DecompressionBombError` was added to the caught exceptions and converted to `ProjectFormatError` (the second uncaught crash path the review noted).

### WR-01: Unsaved-Changes gate proceeds after a failed Save when a project dir already exists

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `7e15a50`
**Applied fix:** `_save_project` now returns `bool` — `False` on abort (no page open, cancelled folder dialog, `OSError` save failure, and the WR-02/WR-03 aborts added later), `True` on success or when there was nothing to save. `_confirm_discard_changes` keys the gate on the result: `return self._save_project()`. A failed save with a pre-existing project dir now aborts the session-replacing action instead of discarding the unsaved edits.

### WR-02: All-pages-skipped save "succeeds" with an empty manifest and clears the dirty flags

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `39e2e5f`
**Applied fix:** `_save_project` aborts with the save-failure dialog (error log to loguru) when `not page_files` — before anything is written — and returns `False`, so the dirty flags stay untouched and the session remains recoverable. The 0-page-manifest silent success path is gone.

### WR-03: Duplicate page stems silently collide on save — one `.mas` overwrites the other

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `aed9b33`
**Applied fix:** `_save_project` detects duplicate stems in the assembled `page_files` (before writing anything) and surfaces a save error listing the colliding stems (e.g. `page.png` + `page.jpg`), returning `False` so dirty flags stay set.

### WR-04: Show Original (D-06) gating goes stale after page navigation

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `9d0c0f3`
**Applied fix:** `on_page_selected` now calls `_refresh_action_states()` after `self._last_page_index` is flipped to the incoming page. The tail's earlier `_refresh_status_bar()` ran with the stale outgoing index, so the D-06 Show Original gating (read from `_last_page_index`) followed the outgoing page; the refresh after the flip makes it follow the incoming page.

### WR-05: Identity resize marks the page geometry-altered and pushes a no-op undo entry

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `9414c62`
**Applied fix:** `_on_resize` returns early when `(new_w, new_h) == (w_img, h_img)` — unchanged dims (100% percent mode, or re-typing the current dims) no longer push an undo entry, re-baseline Show Original, or flip `geometry_altered` (which would have moved the D-22 `_ocr.json` export to `cleaned/` for a page with no geometry change).

### WR-06: `meta.json` image dims are never cross-checked against the actual embedded PNG

**Files modified:** `manga_ai_studio/gui/main_window.py`
**Commit:** `9289d90`
**Applied fix:** `_build_image_file_from_parsed` compares the decoded PNG dims (`imf.current_image.shape[:2]`) against the declared `meta.img` w/h and raises `ProjectFormatError` on mismatch — a crafted 100x100-declared container carrying a 10000x10000 PNG is rejected instead of displaying a mask misaligned with the image and exporting inconsistent dims. Note: this now rejects previously-accepted files whose declared dims lie; that is the intended untrusted-input hardening (T-05-02).

## Verification

- Per-finding Tier 1 (re-read of every edited site) and Tier 2 (`ast.parse` syntax check on `main_window.py` / `project_io.py` / the updated test) passed for all 9 findings.
- Full test suite: `python.exe -m pytest tests -q` → **546 passed, 0 failed, 3 warnings** (pre-existing `huggingface_hub` `resume_download` FutureWarning, unrelated to this phase).
- One existing test (`test_gui_project.py::test_open_verified_original_flag`) asserted the pre-fix behavior the review explicitly flagged as the CR-01 bug (navigation re-loads the pre-save disk original). It was updated to the CR-01 D-05 in-memory-state contract and passes (commit `21e84a7`).
- **Where the gates ran:** the main checkout. `workflow.use_worktrees` is `false` in `.planning/config.json`, so no worktree was created and all edits, commits, and the pytest run happened in the main checkout (results reproducible from the current tree).

---

_Fixed: 2026-08-08T12:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_

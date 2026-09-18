---
phase: 05-project-persistence-image-ops-export
verified: 2026-08-08T22:45:00Z
status: passed
score: 53/53 must-haves verified (3 ROADMAP success criteria + 50 plan truths)
behavior_unverified: 0
overrides_applied: 0
gaps: []
behavior_unverified_items: []
human_verification:

  - test: "Repro the CR-01 review scenario in the live app: open a multi-page folder, rotate page 2 (Tools -> Rotate 90 CW), navigate to page 3, navigate back to page 2, then Save Project. and reopen the project."
    expected: "Page 2 reopens with the ROTATED image and matching box geometry (the D-05 in-memory-state contract) — the post-op image was embedded, not the pre-op disk original."
    why_human: "CR-01 is coordinated state-handling across three coupled sites (apply path, navigation, save-side source) plus the undo companion. Tier-1 code inspection + the updated test suite (test_open_verified_original_flag now asserts the new contract; 546/546 green) prove the wiring; only a real multi-page walk-through can confirm the visual repro from 05-REVIEW.md is closed."

  - test: "MVP goal-format decision: the phase is Mode: mvp but the ROADMAP goal is NOT in user-story format ('As a [role], I want to…, so that…') — `gsd-tools query user-story.validate` returned false."
    expected: "Developer decides: run `/gsd mvp-phase 5` to reformat the goal (preferred per verify-mvp-mode.md), or accept the deviation. Phases 01-04 share the identical goal phrasing and were verified as passed against their Success Criteria — this report follows that established precedent."
    why_human: "Format-guard resolution is a project-level decision, not something the verifier can unilaterally accept; the substantive verification is unaffected either way."
---

# Phase 5: Project Persistence, Image Ops & Export — Verification Report

**Phase Goal:** User can save and resume full project state, apply basic image operations, and export OCR/box data for downstream tools — turning the editor into a resumable, interoperable workspace.
**Verified:** 2026-08-08
**Status:** human_needed (all 53/53 must-haves verified with behavioral evidence; 2 human items: CR-01 end-to-end repro + MVP goal-format decision)
**Re-verification:** No — initial verification

## MVP Mode Note (discrepancy surfaced)

The phase has `**Mode:** mvp` in ROADMAP.md, but the goal is **not** in user-story format. `gsd-tools query user-story.validate` returned `false` for the goal string. Per `verify-mvp-mode.md`, the verifier surfaces this and asks the user to run `/gsd mvp-phase 5` to reformat. **Established project precedent:** phases 01–04 are all `Mode: mvp` with the identical "User can…" goal phrasing and were verified `passed` against their ROADMAP Success Criteria — this report follows that precedent and verifies the Success Criteria contract (the non-negotiable roadmap contract per the verifier process Step 2a). The format decision is routed to the developer in Human Verification item 2. No User Flow Coverage section is fabricated against a goal that is not a literal user story.

## Verification Method

Goal-backward: the 3 ROADMAP Success Criteria are the phase contract; the 50 must-have truths from the 9 plan frontmatters (05-01..05-09) add plan-specific detail. Each truth was verified by direct codebase inspection (module reads, grep wiring traces, git history) — SUMMARY claims were treated as unverified until code evidence matched. Behavior-dependent truths (round-trips, atomicity, undo invariants, cancel semantics, key bindings) were confirmed by the **full test suite run in this verification: 546 passed, 0 failed, 3 warnings in 58.3s** (`python.exe -m pytest -q`, Python 3.14.2) — plan-time baseline was 462 collected / 461 passed / 1 failed, so the 05-09 remediation plus all new tests landed and the suite is green.

Git history confirms all phase commits present (05-01..05-09 task + fix commits, incl. code-review CR-01..CR-03 and WR-01..WR-06 fixes).

## Goal Achievement — ROADMAP Success Criteria

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | User can save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work | ✓ VERIFIED | `core/project_io.py` (LZMA2 container `_MAGIC`/`_FORMAT_VERSION`, `save_page_file`/`load_page_file`, `pagebox_to_json`/`json_to_pagebox`, `build_page_entries`/`parse_page_entries`, `save_project`/`load_project`, D-06 `verify_original`, D-09 `find_sibling_manifest`, `validate_meta`); `main_window.py` `_save_project`/`_save_project_as`/`_open_project`/`_load_project_session`/`_load_single_page_mas`/`_confirm_discard_changes`/Recent Projects (max 8, QSettings); `ImageFile.current_image`/`original_verified`/`geometry_altered`; all round-trip + GUI tests green (test_page_file_round_trip, test_open_project_restores_session, test_unsaved_changes_prompt_save_discard_cancel, …) |
| 2 | User can export OCR/box data as a mokuro-style `_ocr.json` file per page for use in downstream tools | ✓ VERIFIED | `core/ocr_export.py` (D-19 `build_page_ocr_json`, D-20 `split_text_onto_lines`, D-22 `ocr_json_target_dir`/`default_ocr_json_path`, `write_page_ocr_json`, `batch_export_ocr` with abort + per-page isolation); `main_window.py` `_export_ocr_json` (Ctrl+Shift+E) + `_dispatch_batch_ocr_export`/`_on_batch_ocr_export_finished` (Worker + progress + Cancel); tests green (test_json_shape, test_newline_split, test_d22_location_rule, test_batch_export_cancel, test_batch_export_mixed_failure_count, …) |
| 3 | User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize | ✓ VERIFIED | `core/image_ops.py` (rotate_page/rotate_boxes, crop_page/crop_boxes/crop_page_with_boxes, resize_page/resize_boxes LANCZOS/NEAREST, levels_lut/levels_page with white>black clamp); `history_manager.py` `push_geometry_state` + unified `undo()`/`redo()` (one Ctrl+Z reverses image+mask+boxes); GUI apply path `_apply_geometry_op` + `_rotate_page`/`_on_levels`/`_on_resize`/`_apply_crop`; Crop 6th tool (ToolMode.CROP, G shortcut, armed-rect + z=880 dim-out, Enter/Esc); Levels/Resize/Crop dialogs; tests green (test_rotate_90cw_end_to_end, test_levels_cancel_restores_exactly, test_crop_apply_drop_clip_count, test_resize_apply_end_to_end, test_geometry_undo_reverses_all_three, …) |

## Plan Truths (50/50)

### Plan 05-01 — .mas serialization core (PROJ-01)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `.mas` page files round-trip: PageBox (box/origin/edited/bubble_no/manual_override + TextBlock text/translation/lines/vertical/language/font_size) survives save→load; mask/std_dev stay None (D-15) | ✓ VERIFIED | `pagebox_to_json`/`json_to_pagebox` (project_io.py:182-271) — hand-picked fields, V5 int coercion, fresh frozen Box; `test_pagebox_json_round_trip` + `test_page_file_round_trip` in green suite |
| 2 | All JSON content written and read as UTF-8 | ✓ VERIFIED | `ensure_ascii=False` + `.encode("utf-8")` in build_page_entries/save_project (project_io.py:316-356); `load_project` opens `encoding="utf-8"`; `test_manifest_round_trip` (non-ASCII name) green |
| 3 | Re-save overwrites only owned manifest.json + per-page .mas; foreign content never deleted (D-02) | ✓ VERIFIED | `save_project` writes only `manifest.json` + `<stem>.mas`; `test_non_destructive_overwrite` green |
| 4 | Save interrupted mid-write cannot corrupt the existing project (atomic temp + os.replace) — held-out | ✓ VERIFIED | `_atomic_write_bytes` (project_io.py:105-122) + BaseException cleanup; `test_save_is_atomic` green (backstop) |
| 5 | Load rejects corrupt/newer-version input with ProjectFormatError (bad magic, memlimit breach, oversized dims); ints coerced; no partial session | ✓ VERIFIED | `load_page_file` wraps struct/IndexError/Unicode/LZMAError → ProjectFormatError + `memlimit=512MiB`; `validate_meta` dims ≤ 10000 + mask-dims cross-check; `load_project` version + MAX_PROJECT_PAGES; `test_bad_magic_rejected`, `test_malformed_entry_table_rejected`, `test_meta_validation`, `test_oversized_chapter_rejected` all green |
| 6 | D-06: original verified iff path resolves with image suffix AND sha256 matches → `original_verified=True`; else False | ✓ VERIFIED | `verify_original` (resolve-before-suffix + chunked sha256, never raises); `_build_image_file_from_parsed` sets flag; `test_original_checksum_rule` green |
| 7 | Page .mas with sibling manifest.json detectable via find_sibling_manifest (D-09) | ✓ VERIFIED | `find_sibling_manifest` (validates manifest, raises ProjectFormatError on corrupt sibling); `test_sibling_manifest_detection` green |

### Plan 05-02 — core/image_ops.py (PROJ-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Rotate 90° CW/CCW/180° pixel-exact for image + binary mask (np.rot90 k=-1/1/2) and transforms every box bbox AND TextBlock.lines polygon | ✓ VERIFIED | `rotate_page`/`rotate_boxes`/`transform_box`/`transform_lines` (image_ops.py:166-186, one convention); `test_rotate_transforms_all` green |
| 2 | 90° rotations compose: two 180° = identity; transforms never mutate frozen Box or caller's line lists | ✓ VERIFIED | Fresh Box/TextBlock per transform, no in-place paths; `test_rotate_composes_identity` + originals-untouched contract green |
| 3 | Crop exact slice; fully-outside boxes dropped (count returned), partial clipped — bbox AND lines | ✓ VERIFIED | `crop_page`/`crop_boxes`/`crop_page_with_boxes` + `_clip_box`/`_clip_quad` (D-16); `test_crop_drop_and_clip`, `test_crop_zero_area_dropped` green |
| 4 | Resize LANCZOS image / NEAREST mask; boxes scaled to int coords; levels: 256-entry numpy LUT, white>black clamped (never inverted) | ✓ VERIFIED | `resize_page`/`resize_boxes` (int(round()), 1..100000 bounds); `levels_lut` (lo/hi normalization → monotone LUT); `test_resize_and_levels` green |
| 5 | Every transform returns `.copy()`-detached arrays | ✓ VERIFIED | `.copy()` at every return; input-validation-before-work discipline documented + tested |

### Plan 05-03 — core/ocr_export.py (PROJ-03)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | D-19 snake_case shape: version/img_width/img_height/blocks[] with box/vertical/text/translation/bubble_no/origin + lines[] per-line box+text | ✓ VERIFIED | `build_page_ocr_json` (ocr_export.py:121-182); `test_json_shape` green |
| 2 | D-20: whole-text split by \n onto lines polygons; unmatched polygons empty text; zero-box pages export empty blocks[] | ✓ VERIFIED | `split_text_onto_lines`; `test_newline_split` + `test_export_zero_box_page` green |
| 3 | D-22: pristine → sidecar <stem>_ocr.json beside source; geometry-altered → <source>/cleaned/, created if missing | ✓ VERIFIED | `ocr_json_target_dir`/`default_ocr_json_path` + `mkdir(parents=True)`; `test_d22_location_rule` + `test_export_single_altered_page_default_dir` green |
| 4 | Batch interruptible via abort flag (loop-top only); per-page independent writes; per-page failures isolated → {ok, failed, total} | ✓ VERIFIED | `batch_export_ocr` (loop-top abort check, per-page try/except, lazy Abort import for exact Worker identity); `test_batch_export_ocr_isolates_failures`, `test_batch_progress_emits`, `test_batch_export_cancel` green |
| 5 | Exported coordinates + img dims always describe CURRENT page state; mask/std_dev never exported (D-15) | ✓ VERIFIED | Dims int-validated; exporter reads PageBox fields only; `test_d15_seam_never_exported` green |

### Plan 05-04 — geometry-op undo record (PROJ-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | One Ctrl+Z reverses image+mask+boxes: push_geometry_state stamps ALL THREE with ONE stamp; undo()/redo() pop every store whose tail stamp equals max, return list[(kind, value)] | ✓ VERIFIED | `push_geometry_state` (history_manager.py:402-448) + unified `undo()`/`redo()` (451-541) with group-stash redo; `test_geometry_push_stamps_all_stores`, `test_geometry_undo_reverses_all_three`, `test_geometry_redo_restores_all_three` green |
| 2 | Every image op pushes exactly ONE geometry entry — no double-push, no empty entries | ✓ VERIFIED | `_suppress_boxes_push` guard + single `push_geometry_state` per op; `test_levels_apply_pushes_one_entry` + `test_geometry_push_omits_none_stores` green |
| 3 | Ordinary single-store pushes/pops behave exactly as before | ✓ VERIFIED | Per-type push/pop methods untouched (same shapes, stamp-widened); full suite green (all Phase 1/3 history tests pass) |
| 4 | MainWindow.on_undo/on_redo apply the list in kind order and flash 'Undo: {op}'/'Redo: {op}'; op-name set extends with rotate/crop/levels/resize | ✓ VERIFIED | `_record_geometry_op_name` + list-apply in on_undo/on_redo; op-name set extended |
| 5 | IMAGE side of geometry entry is a full-frame patch at (0,0) — pop_image_undo's machinery handles it | ✓ VERIFIED | `push_geometry_state` stores `(0,0,image_patch.copy())`; pop_image_undo full-frame branch (history_manager.py:247-249) |

### Plan 05-05 — Save/Open Project session (PROJ-01)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Save Project. (Ctrl+S) / Save Project As. (Ctrl+Shift+S) / Open Project. (Ctrl+O) in File menu; Open Image. no longer binds Ctrl+O | ✓ VERIFIED | Shortcuts at main_window.py:311/334/344; `action_open_image` has NO setShortcut (full setShortcut audit); `test_ctrl_o_opens_project_not_image` green |
| 2 | Save Project. disabled with no page; clean session flashes no-changes and writes nothing | ✓ VERIFIED | `_save_project` early-returns False when no page; clean-session branch flashes; `test_save_disabled_with_no_page`, `test_save_clean_session_no_changes_flash` green |
| 3 | Dirty tracking: any page mutation marks session dirty; title appends *; Save clears dirty | ✓ VERIFIED | `_set_session_dirty`/`_update_title`/`imf.dirty=False` loop; `test_dirty_title_suffix` green |
| 4 | Unsaved Changes [Save][Discard][Cancel] on Quit, close, Open Project., Open Image., Open Folder. when dirty | ✓ VERIFIED | `_confirm_discard_changes` (main_window.py:2236-2273) + WR-01 fix keys gate on save RESULT; `test_unsaved_changes_prompt_save_discard_cancel` green |
| 5 | Recent Projects submenu: empty item, full-path tooltips, max 8, QSettings-persisted, Clear Menu | ✓ VERIFIED | `MAX_RECENT_PROJECTS=8`, `_recent_projects`/`_add_recent_project`/`_refresh_recent_projects_menu` + "No recent projects yet." placeholder; `test_recent_projects_menu` green |
| 6 | Open Project. rebuilds session from manifest: sidebar order, masks/boxes/text restored, EVERY page's embedded image decoded into current_image, fresh undo history, originals re-found via path+sha256; missing-original navigation renders embedded image without error | ✓ VERIFIED | `_load_project_session` (session swap after full build, `reset_history`, missing-original count in status); `_build_image_file_from_parsed` + CR-01 current_image preference in on_page_selected Step 3 + `_page_image_source`; `test_open_project_restores_session`, `test_open_project_populates_all_current_images`, `test_page_navigation_uses_embedded_image_for_missing_original`, `test_open_verified_original_flag` (updated to CR-01 contract) green |
| 7 | Page .mas with sibling manifest pops Chapter Detected (Open Project / Open Page Only; Esc cancels); corrupt/missing manifest errors and never mutates current session | ✓ VERIFIED | `_open_project` routing + `_confirm_chapter_climb` (hidden Esc button); `test_open_page_mas_with_sibling_prompt`, `test_open_corrupt_project_keeps_session` green |
| 8 | Menu actions gate on _op_running | ✓ VERIFIED | `_refresh_action_states` gating + `_op_running` checks at entry points; `test_menu_gating_during_op` green |

### Plan 05-06 — image-op GUI apply path (PROJ-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Rotate applies silently: image+mask+boxes transform together, ONE geometry undo entry, Show Original re-baselines, status flashes | ✓ VERIFIED | `_rotate_page` → `_apply_geometry_op` (write-back + `push_geometry_state` + `rebaseline_original` + flash); `test_rotate_90cw_end_to_end` green |
| 2 | Levels dialog: black 0 / white 255 / gamma 1.00 defaults; live in-place preview; Cancel restores exactly with no undo entry; Apply pushes ONE image entry and re-baselines; white>black clamped | ✓ VERIFIED | `levels_dialog.py` (ranges 0..255, gamma 0.10..4.00 log-slider, cross-clamp) + `_on_levels` (preview via capture-suppressed path, cancel `set_image_from_numpy(base.copy())`); `test_levels_defaults_and_clamp`, `test_levels_cancel_restores_exactly`, `test_levels_apply_pushes_one_entry`, `test_levels_preview_no_baseline_poison` green |
| 3 | Resize dialog: 1..100000 px init to current dims, aspect lock checked by default, px/% toggle, live Result label; apply = LANCZOS/NEAREST + scaled boxes, one undo entry | ✓ VERIFIED | `resize_dialog.py` (MAX_PX=100000, percent mode, aspect lock) + `_on_resize`; `test_resize_dialog_contract`, `test_resize_apply_end_to_end` green |
| 4 | Levels is geometry-free; geometry_altered set ONLY by crop/rotate/resize — never levels | ✓ VERIFIED | `_apply_geometry_op(geometry=False)` for levels vs True for rotate/resize/crop; A4 honored |
| 5 | Show Original (P): disabled with tooltip when .mas-loaded without verified original; enabled otherwise; _original_image_numpy re-baselines after EVERY op | ✓ VERIFIED | `_refresh_action_states` D-06 gating (main_window.py:972-987) + `rebaseline_original` (canvas.py:698-707); WR-04 post-navigation refresh present; `test_show_original_gating` green |
| 6 | Image-op actions gated: enabled iff ≥1 page open AND no async op; levels live preview never pushes undo entries | ✓ VERIFIED | `_refresh_action_states` page_open/`_op_running` gates; preview path `set_image_from_numpy_preview(capture_original=False)` |

### Plan 05-07 — crop surface (PROJ-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Crop is the 6th exclusive tool: ToolMode.CROP, ToolsPanel button after Eraser, shortcut G, active-tool highlight, Tools-menu action in exclusive group | ✓ VERIFIED | `ToolMode.CROP` (mask_editor.py:73), ToolsPanel `action_crop` (G), `action_tool_crop` in menu; `test_crop_is_sixth_exclusive_tool`, `test_crop_action_in_tools_menu` green |
| 2 | Crop-tool drag defines rect with CrossCursor; outside dims via z=880 overlay rgba(0,0,0,0.45); rect border reuses cyan dashed preview pen; <8x8 scene px is a no-op | ✓ VERIFIED | canvas.py `CROP_DIM_Z = 880` + `_CROP_DIM_COLOR = QColor(0,0,0,114)` + 4-rect compositing + MIN_BOX_SIZE reuse; `test_dim_outlayers_geometry`, `test_small_drag_noop` green |
| 3 | Rect stays armed after release (drag-then-decide): Enter applies, Esc cancels, box hit-testing preserved while active | ✓ VERIFIED | `_crop_rect` armed state machine + `keyPressEvent` (Key_Return/Key_Enter → `_apply_armed_crop`, Key_Escape → `_clear_crop_state`); `test_drag_arms_rect_enter_applies_esc_cancels`, `test_box_press_still_selects`, `test_tool_switch_clears_armed_crop` green |
| 4 | Apply crops image+mask as exact slices, drops fully-outside boxes with count flash, clips partial (bbox AND lines), ONE geometry undo entry, re-baselines, marks geometry_altered | ✓ VERIFIED | `_on_crop_committed`/`_apply_crop` → `crop_page_with_boxes` + dropped-count flash copy; `test_crop_apply_drop_clip_count` green |
| 5 | Crop. dialog: X/Y/W/H spinboxes init to full page bounds; Width range 1..W-x recomputed on X change; apply-time re-validation keeps dialog open | ✓ VERIFIED | `crop_dialog.py` (recomputed bounds + T-05-17 re-validation, stays open on invalid); `test_crop_dialog_contract`, `test_crop_dialog_apply_end_to_end`, `test_crop_degenerate_noop` green |

### Plan 05-08 — OCR JSON export GUI (PROJ-03)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Export OCR JSON. (Ctrl+Shift+E, Text menu after Load Translations.): Save As with *_ocr.json filter, default {stem}_ocr.json, D-22 default dir; success flash; write failure shows save-failure dialog | ✓ VERIFIED | `_export_ocr_json` (flush seam, D-22 default via `default_ocr_json_path`, OSError → critical dialog); `test_export_single_pristine_page`, `test_export_single_altered_page_default_dir`, `test_export_write_failure_dialog` green |
| 2 | Batch Export OCR JSON (Batch menu): Worker + _op_running/_batch_active + phase-2 progress surface + Cancel Batch; per-page D-22 placement; completion flash n/m with failure count; no per-page modals | ✓ VERIFIED | `_dispatch_batch_ocr_export` (partial + Worker + abort_signal + progress bar + Cancel) + `_on_batch_ocr_export_finished`; `test_batch_export_writes_all_pages`, `test_batch_export_mixed_failure_count`, `test_batch_export_cancel`, `test_batch_export_gating_and_progress` green |
| 3 | Both surfaces exist and are distinct (single-page dialog vs batch action) with distinct feedback | ✓ VERIFIED | Two separate actions (`action_export_ocr_json`, `action_batch_export_ocr`) + distinct status copies |
| 4 | Zero-box pages export without gate/confirm (empty blocks[]); exports describe CURRENT page state | ✓ VERIFIED | `test_export_zero_box_page` green; dims read from canvas after flush (D-22) |
| 5 | Save-side flush runs before both exports | ✓ VERIFIED | `_snapshot_current_page()` at the top of both `_export_ocr_json` and `_dispatch_batch_ocr_export` (+ mask flush in batch); Pitfall 7 honored |

### Plan 05-09 — test regression fix (PROJ-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | test_moved_box_via_real_events_persists_round_trip passes deterministically in every environment | ✓ VERIFIED | Test rewritten to anchor on delivered move position with truncation tolerance (docstring documents measured root cause); full suite green (test collected + passed in the 546) |
| 2 | Regression value preserved: pos()/rect() divergence still fails the precondition | ✓ VERIFIED | Precondition asserts the box MOVED via rect() ~50px (45..50 band) — a divergence leaves rect() at original → fails |
| 3 | No production code changes | ✓ VERIFIED | Git history: 05-09 commits touch only `tests/test_gui_boxes.py` (b8ed530 test-fix commit; production canvas math verified exact) |
| 4 | Full suite 462/462 (baseline was 462/461+1) | ✓ VERIFIED | Suite now 546 passed / 0 failed (more tests than baseline — all 05-01..05-08 tests added) |

## Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `manga_ai_studio/core/project_io.py` | .mas container + manifest + PageBox map + D-06/D-09 + validation | ✓ VERIFIED | 579 lines, all 20 planned symbols present incl. `ProjectFormatError`, `memlimit`, CR-03 mask-length check |
| `manga_ai_studio/core/image_ops.py` | rotate/crop/resize/levels + geometry transforms | ✓ VERIFIED | 470 lines, all planned functions, no-Qt contract honored |
| `manga_ai_studio/core/ocr_export.py` | D-19 shape + D-20 split + D-22 + batch loop | ✓ VERIFIED | 354 lines, all planned functions; Worker kwargs contract (last-two) honored |
| `manga_ai_studio/core/history_manager.py` | push_geometry_state + list-returning undo/redo | ✓ VERIFIED | Stamp-shared triple push + unified pop, per-type methods untouched |
| `manga_ai_studio/core/image_file.py` | original_verified + geometry_altered (+ current_image) | ✓ VERIFIED | Fields at lines 97-101 with documented semantics |
| `manga_ai_studio/core/image_io.py` | save_image_bytes in-memory PNG encoder | ✓ VERIFIED | compress_level=9, (H,W,3) uint8 validation |
| `manga_ai_studio/gui/main_window.py` | save/open session + image-op orchestration + export wiring | ✓ VERIFIED | All 21 planned method symbols present and wired to menu actions/shortcuts |
| `manga_ai_studio/gui/levels_dialog.py` | Levels dialog | ✓ VERIFIED | Defaults/live preview/cross-clamp |
| `manga_ai_studio/gui/resize_dialog.py` | Resize dialog | ✓ VERIFIED | 1..100000, aspect lock, px/% toggle |
| `manga_ai_studio/gui/crop_dialog.py` | numeric crop dialog | ✓ VERIFIED | X/Y/W/H spinboxes + re-validation |
| `manga_ai_studio/gui/tools_panel.py` + `core/mask_editor.py` | 6th Crop tool | ✓ VERIFIED | ToolMode.CROP + panel button + G shortcut |
| `manga_ai_studio/gui/canvas.py` | crop state machine + rebaseline_original + preview path | ✓ VERIFIED | Armed-rect, z=880 dim-out, Enter/Esc, capture-suppressed preview |
| Tests: `test_core/test_project_io.py`, `test_core/test_image_ops.py`, `test_core/test_ocr_export.py`, `test_history.py`, `test_gui_project.py`, `test_gui_image_dialogs.py`, `test_gui_crop_tool.py`, `test_gui_export.py`, `test_gui_boxes.py` | Behavioral coverage for every truth | ✓ VERIFIED | All collected + passing in the full suite run (546 passed) |

## Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `main_window._save_project` | `core/project_io.save_project/build_page_entries` | `_page_image_source` (current_image-first, CR-01) + `sha256_file` | WIRED | Only disk boundary; WR-01/02/03 aborts return False |
| `main_window._open_project` | `core/project_io.load_project/load_page_file/parse_page_entries/find_sibling_manifest` | `_build_image_file_from_parsed` | WIRED | Session swap only after full build; corrupt → critical dialog, session untouched |
| `main_window._apply_geometry_op` | `core/image_ops` | `transform_fn` closures + `set_image_from_numpy/set_mask/set_boxes` under `_suppress_boxes_push` | WIRED | One `push_geometry_state` per op; `rebaseline_original` after |
| `history.push_geometry_state` | `undo()/redo()` | shared monotonic `_stamp()` + max-tail-stamp match | WIRED | One Ctrl+Z reverses image+mask+boxes; group-stash redo |
| `main_window._export_ocr_json`/`_dispatch_batch_ocr_export` | `core/ocr_export` | `_snapshot_current_page()` flush seam (Pitfall 7) | WIRED | Exports describe live canvas; Worker auto-injects last-two kwargs |
| `canvas` (crop tool) | `main_window._apply_crop` | `crop_committed` signal → `crop_page_with_boxes` | WIRED | Scene rect → int pixels, degenerate no-op guard |
| `ImageFile.geometry_altered` | `ocr_export.ocr_json_target_dir` | D-22 flag per page | WIRED | Pristine → sidecar; altered → cleaned/ |
| `mask_editor.mask_to_numpy_binary` | `image_ops` transforms | binary form only (D-18) | WIRED | `numpy_binary_to_mask_qimage` on write-back |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `_load_project_session` | `page_files`/`ImageFile`s | `parse_page_entries` → embedded PNG decode → `current_image` (D-08) | Yes — per-page image/mask/boxes/text from the container | ✓ FLOWING |
| `_save_project` | `page_files` | `_page_image_source` (current_image → cleaned/ → source fallback) | Yes — real per-page state, not static | ✓ FLOWING |
| `_export_ocr_json` | `boxes`/`img_w/img_h` | flushed `ImageFile.boxes` + canvas dims | Yes — live state, D-22 current-state rule | ✓ FLOWING |
| `_apply_geometry_op` | `new_image/new_mask_bin/new_boxes` | `image_ops` pure transforms of captured canvas state | Yes — real math, `.copy()`-detached | ✓ FLOWING |
| `batch_export_ocr` | `ExportPage` list | per-page projection (canvas dims / current_image / PIL source) | Yes — real per-page data with D-22 placement | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full test suite (all phase tests incl. behavior-dependent invariants) | `python.exe -m pytest -q` | 546 passed, 0 failed, 3 warnings (58.3s) | ✓ PASS |
| Geometry-undo invariant (one Ctrl+Z reverses all three stores) | In suite: `test_geometry_undo_reverses_all_three` | Collected + passed | ✓ PASS |
| Atomic-save backstop (interrupted write leaves prior project intact) | In suite: `test_save_is_atomic` | Collected + passed | ✓ PASS |
| .mas/PageBox round-trip fidelity | In suite: `test_page_file_round_trip`, `test_pagebox_json_round_trip` | Collected + passed | ✓ PASS |
| D-19 JSON shape + D-20 \n-split + D-22 placement | In suite: `test_json_shape`, `test_newline_split`, `test_d22_location_rule` | Collected + passed | ✓ PASS |
| Rotate composition identity + transform immutability | In suite: `test_rotate_composes_identity`, `test_rotate_transforms_all` | Collected + passed | ✓ PASS |
| Batch OCR cancel + failure isolation | In suite: `test_batch_export_cancel`, `test_batch_export_ocr_isolates_failures` | Collected + passed | ✓ PASS |
| Ctrl+O opens Project not Image; Save/Open shortcuts | In suite: `test_ctrl_o_opens_project_not_image` | Collected + passed | ✓ PASS |
| Crop armed-rect Enter/Esc + drop/clip count | In suite: `test_drag_arms_rect_enter_applies_esc_cancels`, `test_crop_apply_drop_clip_count` | Collected + passed | ✓ PASS |
| 05-09 move-round-trip regression | In suite: `test_moved_box_via_real_events_persists_round_trip` | Collected + passed (deterministic, anchored on delivered position) | ✓ PASS |

## Probe Execution

No probe scripts (`scripts/*/tests/probe-*.sh`) were declared in any PLAN/SUMMARY for this phase; the phase's verification contract was pytest-driven (per-plan `<verify>` commands + full-suite criteria). Step 7c: N/A.

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| PROJ-01 | 05-01, 05-05 | User can save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work | ✓ SATISFIED | project_io.py + session GUI (15/15 truths green; tests listed above) |
| PROJ-03 | 05-03, 05-08 | User can export OCR/box data as a mokuro-style `_ocr.json` file per page for use in downstream tools | ✓ SATISFIED | ocr_export.py + export GUI (10/10 truths green) |
| PROJ-04 | 05-02, 05-04, 05-06, 05-07, 05-09 | User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize | ✓ SATISFIED | image_ops.py + history + GUI apply paths + crop tool + test fix (25/25 truths green) |

**Orphaned-requirement check:** REQUIREMENTS.md maps exactly PROJ-01, PROJ-03, PROJ-04 to Phase 5; all three appear in plan `requirements:` frontmatter. No orphaned requirements. (PROJ-02/FLOW-01/FLOW-03 map to other phases — not this phase's scope.)

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/HACK markers in any phase-modified file | — | None — debt-marker gate clean |
| `main_window.py` | 1752/2401 | `placeholder = QAction(...)` | ℹ️ Info | Required behavior — "(empty)" Recent Files + "No recent projects yet." menu items, not stubs |
| `deferred-items.md` | — | Pre-existing toolbar tool-button highlight never functional (plan 04 artifact) | ℹ️ Info | Out of scope for 05-07 (documented deferral, owning plan = any future toolbar/tool plan); does not affect this phase's must-haves — crop accent-highlight contract lives on the ToolsPanel and is tested |

## Human Verification Required

### 1. CR-01 end-to-end repro (rotate → navigate → save)

**Test:** Open a multi-page folder. Rotate page 2 (Tools → Rotate → 90° CW). Navigate to page 3, then back to page 2. Save Project. Close and reopen the project.
**Expected:** Page 2 reopens with the ROTATED image and matching box geometry (D-05 in-memory-state contract) — the post-op image embedded, not the pre-op disk original.
**Why human:** CR-01 (05-REVIEW.md) is coordinated state-handling across three coupled sites (apply write-back, navigation Step 3, save-side `_page_image_source`) plus the undo companion. The automated portion is verified: code inspection confirms all three sites, the suite is green (546/546), and `test_open_verified_original_flag` was updated (commit `21e84a7`) to assert the new contract — but 05-REVIEW-FIX.md explicitly marks this finding `requires human verification`, and only a real multi-page walk-through can confirm the visual repro is closed.

### 2. MVP goal-format decision

**Test:** Decide how to handle the `Mode: mvp` + non-user-story goal discrepancy (see MVP Mode Note above).
**Expected:** Either run `/gsd mvp-phase 5` to reformat the ROADMAP goal into a user story, or explicitly accept the deviation (phases 01–04 precedent).
**Why human:** Format-guard resolution is a project-level decision; the substantive verification is unaffected either way.

## Gaps Summary

No gaps found. All 53 must-haves (3 ROADMAP Success Criteria + 50 plan truths) verified against the codebase with behavioral evidence (full suite 546 passed / 0 failed; targeted tests for every behavior-dependent invariant — round-trips, atomicity, one-press geometry undo, batch cancel/isolation, D-19/D-20/D-22 contract, key bindings, armed-rect state machine). All 9 code-review findings (CR-01..03, WR-01..06) verified fixed in code; CR-01 additionally routed to human verification per its own fix report. All user decisions D-01..D-22 from 05-CONTEXT.md honored in the implementation.

**Status is `human_needed`** — not because any must-have failed, but because (1) the CR-01 fix is explicitly marked `requires human verification` and the end-to-end repro needs a human walk-through, and (2) the MVP goal-format discrepancy requires a developer decision. Automated verification is complete and green.

---

_Verified: 2026-08-08_
_Verifier: the agent (gsd-verifier)_

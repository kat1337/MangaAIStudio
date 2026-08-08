---
phase: 04-ocr-recognition-text-editing
verified: 2026-08-06T00:00:00Z
status: passed
score: 20/20 must-haves verified (3 ROADMAP success criteria + 17 gap-closure truths from plans 04-08/09/10; the prior 12 truths regression-confirmed by the full green suite)
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 12/12 truths verified
  gaps_closed:
    - "Text overlay follows box geometry (UAT test 1) — fixed by plan 04-08 (RC-1 setPos-only reposition; RC-2 zoom clamp; RC-3 2-viewport-px outline); user confirmed 'the text now moves with the boxes and scales'"
    - "Text overlay adapts to box size: wrap/fit-in-box + menu-bar structure (Recent/Batch as File submenus) + toolbar Open Folder (UAT test 1 round 2) — fixed by plan 04-09; UAT test 1 re-verified pass"
    - "Bubble badge fits its number (UAT test 4) — fixed by plan 04-10 (digit-sized badge); UAT test 4 re-verified pass"
    - "Bubble # 1 manually assignable (UAT test 6) — fixed by plan 04-10 (0-sentinel); UAT test 6 re-verified pass"
  gaps_remaining: []
  regressions: []
gaps: []
behavior_unverified_items: []
acknowledged_deferral:
  - truth: "Auto-Number RTL (Manga) assigns reading order correctly on complex manga layouts (UAT test 5)"
    status: user_scope_deferral
    reason: "User explicitly deferred this as a scope decision, not a defect: manhwa LTR works; manga RTL misorders complex layouts (XY-Cut insufficient for side-by-side top panels / wide top panels). User: 'just log this since this is a bigger issue than we can fix right now'. Recorded in 04-UAT.md with deferred: true and a future 'draw panel' feature note (candidate for a future phase: panel segmentation + reading-order rework). Not a must-have failure; NOT re-listed as pending human verification."
---

# Phase 4: OCR Recognition & Text Editing — Verification Report (REFRESH)

**Phase Goal:** User can recognize text in boxes (auto-detected regions or manually drawn), correct OCR mistakes, and add manual translations — the core differentiator no existing tool offers interactively.
**Verified:** 2026-08-06
**Status:** passed — must-haves verified, UAT complete (6/7 pass + 1 user-scope deferral), full suite green (461 passed, 1 pre-existing flake deselected)
**Re-verification:** Yes — refresh of a stale report that predated gap-closure plans 04-08/09/10 and the completed UAT

## Verification Method

This refresh re-verifies (a) the 3 ROADMAP success criteria (the phase contract), (b) the 17 gap-closure must-have truths from plans 04-08/09/10 that landed after the stale file, and (c) regression-checks the prior 12 truths against the current codebase. The 7 human-verification items in the stale file were all exercised in the completed UAT (6 passed, 1 user-deferred) and are closed by 04-UAT.md — the authoritative record.

Evidence gathered by direct codebase inspection (not SUMMARY claims):
- Git history: all gap-closure commits present (04-08: 44d395c/d3c967f/0ceef08/dd2f09a; 04-09: 8a8ceec/84e3eca/1f98ddc/355b602/dcef7f7/47212e8; 04-10: fcddc09/3b7ca6f/4fcebd2/f400073; UAT: af93866..b586278).
- Code-level verification of every gap-closure artifact in box_item.py / canvas.py / main_window.py / inspector_panel.py.
- Behavioral test runs (below), including the full suite: **461 passed, 1 deselected, 0 failed** (`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` — pre-existing 1px Qt drag-rounding flake, confirmed pre-existing from Phase 3, out of scope).

## Goal Achievement — ROADMAP Success Criteria

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | User can draw a rectangle on the page and run manga-ocr on just that region to create a box with recognized text (for boxes the auto-detector missed) (TEXT-02) | ✓ VERIFIED | canvas `_commit_create` emits `ocr_requested` after draw-release; `_dispatch_ocr_for_box` → Worker → `_run_ocr_task` crops by box xyxy + `TorchOCRModel.recognize` (numpy→PIL→str); result via `set_recognized_text`. Behavioral tests pass: `test_alt_drag_draw_release_emits_ocr_requested` (ran, PASS), `test_run_ocr_selected_real_model_end_to_end` (real cached model, ran in prior suite), `test_run_ocr_selected_dispatches_worker_not_inline`. UAT test 2 (real-model OCR e2e incl. D-04 dialogs, progress, error UX) — **pass** |
| 2 | User can edit the recognized OCR text inline in a box to correct recognition mistakes (TEXT-04) | ✓ VERIFIED | `mouseDoubleClickEvent` opens `InlineEditor` (QGraphicsProxyWidget+QTextEdit); Enter/click-away commits via `set_recognized_text_edited` (edited=True), Esc cancels (box stays selected), edit-mode disables move/resize, F2 trigger, translation-wins focus rule. Behavioral tests pass: `test_canvas_double_click_box_opens_inline_editor` (ran, PASS), `test_inline_editor_commit_recognized_sets_edited_true` (ran, PASS). UAT test 3 (inline editor + Japanese IME) — **pass** |
| 3 | User can add a manual translation as a second text field per box (clean seam for future machine translation) (TEXT-05) | ✓ VERIFIED | `set_translation` on PageBox (box_model.py:140); Inspector translation commit; inline-editor translation-focus commit; Load Translations paste/file apply (`_apply_translations`, parser `[N]:`/SFX matching); overlay current-focus rule (translation wins). Behavioral tests pass: `test_inline_editor_commit_translation_writes_set_translation` (ran, PASS), `test_apply_translations_fills_set_translation_on_matched_boxes` (ran, PASS). UAT test 6 (paste/file/report/error UX; bubble-1 re-verified after 04-10) — **pass** |

## Gap-Closure Truths (Plans 04-08/09/10 — the new material since the stale file)

### Plan 04-08 — overlay geometry tracking + zoom legibility (UAT test 1)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Moving a box (setRect move path) leaves the overlay text INSIDE the moved box rect at the inset position | ✓ VERIFIED | `_reposition_text_overlay()` setPos-only method (box_item.py:566) called from `_sync_handles` (box_item.py:434) — the canvas moves via setRect + `_sync_handles` on every drag-mousemove. `test_text_overlay_tracks_box_after_setrect_move` — ran, PASS |
| 2 | A TL/BL/TR-edge resize leaves the overlay INSIDE the resized rect at the inset position | ✓ VERIFIED | Same sync path on resize (canvas `_commit_resize` → `_sync_handles`). `test_text_overlay_tracks_box_after_tl_edge_resize` — ran, PASS (also `test_text_overlay_reposition_does_not_rebuild_document` locks the setPos-only contract, in suite) |
| 3 | On zoom change the overlay stays inside the box, rendered size within [10,28] viewport px, outline constant 2 viewport px | ✓ VERIFIED | `apply_overlay_zoom(zoom)` (box_item.py:591) + `_overlay_zoom` stored style; canvas `_on_zoom_changed_reposition_handles` forwards zoom (canvas.py:1462 `item.apply_overlay_zoom(zoom)`); wheel/zoom_reset/fit_to_window all emit zoom_changed. `test_text_overlay_font_clamp_scales_with_zoom` + `test_text_overlay_outline_width_scales_with_zoom` (parametrized 0.25/0.5/1.0/4.0) — in full suite, PASS |
| 4 | A content refresh (translation/recognized edit) at non-100% zoom keeps the zoom-applied font clamp and outline width | ✓ VERIFIED | Stored `_overlay_zoom` reused by every content-refresh path. `test_text_overlay_zoom_style_survives_content_refresh` — in suite, PASS |
| 5 | The existing GUI suite stays green (no regressions beyond the pre-existing deselected flake) | ✓ VERIFIED | Full suite run: 461 passed, 1 deselected, 0 failed |

### Plan 04-09 — overlay fit-in-box + menu structure + toolbar (UAT test 1 round 2)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 6 | Long recognized/translation text renders WRAPPED inside the box rect — no horizontal overshoot | ✓ VERIFIED | `refresh_text_overlay` sets `setTextWidth(inner_w)` (box_item.py:521) with `inner_w = rect width - 2x inset` (max(1.0) floored). `test_text_overlay_wraps_long_text_to_box_width` — ran, PASS (also `test_text_overlay_shrinks_to_fit_box_height` — ran, PASS) |
| 7 | The overlay font ADAPTS to the box size: base = 14 x min(box_w,box_h)/100 viewport px, clamped [10,28], bounded shrink-to-fit loop (max 12 x 0.9, 5 vp floor at loop top) | ✓ VERIFIED | Constants `_OVERLAY_BOX_REF_DIM=100.0`, `_OVERLAY_FIT_MAX_ITERS=12`, `_OVERLAY_FIT_STEP=0.9`, `_OVERLAY_FIT_FLOOR_VP=5.0` (box_item.py:116-119) + fit loop at 545-559; shared `_overlay_inset()` formula (582). `test_text_overlay_font_adapts_to_box_size` (parametrized) + `test_text_overlay_fit_loop_reduces_below_clamp_floor_at_low_zoom` — in suite, PASS |
| 8 | A resized box re-wraps/re-fits its overlay at resize COMMIT (once per drag, never per-mousemove) | ✓ VERIFIED | `_commit_resize` calls `item.refresh_text_overlay()` after `_sync_handles` (canvas.py:1633); per-mousemove `_advance_resize` path stays setPos-only (RC-1 discipline). `test_resize_commit_rewraps_overlay_text_canvas` — ran, PASS |
| 9 | Menu bar top-level shows exactly File, Edit, View, Text, Tools, Help — Recent Files and Batch ONLY as File submenus | ✓ VERIFIED | `self.recent_menu = QMenu("Recent Files", self)` (main_window.py:273) and `self.batch_menu = QMenu("Batch", self)` (299) standalone children; menubar factory `addMenu` calls remain only for the six core menus (grep-verified: no Recent/Batch in menubar action list). `test_menubar_top_level_has_only_the_six_core_menus` + `test_recent_and_batch_menus_are_file_submenus_not_top_level` — ran, PASS |
| 10 | The toolbar's first action is Open Folder (Ctrl+Shift+O); Open Image stays in the File menu | ✓ VERIFIED | `self.toolbar.addAction(self.action_open_folder)` (main_window.py:626); no toolbar add of `action_open_image` (grep count 0). `test_toolbar_first_action_is_open_folder` + `test_open_image_remains_in_file_menu_not_toolbar` + `test_toolbar_open_folder_triggered_opens_folder` — ran, PASS |

### Plan 04-10 — digit-sized badge + bubble-1 0-sentinel (UAT tests 4 + 6)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 11 | The bubble badge FITS its number: digit glyph measured after setPlainText (document margin 0), badge resized to digit + 4px/side x digit + 2px/side, digit re-centered and fully contained at any zoom | ✓ VERIFIED | `_BADGE_PAD_W=4.0`/`_BADGE_PAD_H=2.0` (box_item.py:131-132) replace the fixed 20x14 constants (grep `_BADGE_W|_BADGE_H` == 0 across the whole file); `setDocumentMargin(0.0)` (374); measurement `_badge_digit.boundingRect()` (636) → `setRect(0.0,0.0,bw,bh)` (644) → centering; ItemIgnoresTransformations keeps both constant viewport px. `test_badge_rect_sizes_to_digit` (parametrized) — ran, PASS |
| 12 | The badge stays TL-outside with the same 2px offset computed from the ACTUAL badge size; edge-flip intact | ✓ VERIFIED | Placement reads the actual rect (bw/bh locals, one source of truth); edge-flip uses the same size. `test_badge_tl_outside_uses_actual_badge_size` + `test_badge_tl_outside_tracks_size_across_digits` + `test_badge_edge_flip_uses_actual_size` — in suite, PASS |
| 13 | Bubble # 1 is manually assignable: unset box (spinbox '—') entering 1 commits bubble_no_changed(1) → pagebox.bubble_no=1 AND manual_override=True (D-16 amber badge) | ✓ VERIFIED | 0-sentinel: `setRange(0, 9999)` + `setSpecialValueText("\u2014")` (inspector_panel.py:173-174); `load_box` maps None→0 (229); `_loaded_bubble = 0` (212, 289); handler branch `if number == 0:` (main_window.py:1427) else assign+pin. `test_inspector_bubble_1_commit_assigns_unset_box` + `test_inspector_bubble_1_assigned_and_cleared_end_to_end` — ran, PASS (end-to-end incl. badge digit text '1') |
| 14 | Clearing works symmetrically: committing 0 sets bubble_no=None and manual_override=False; spinbox shows '—' for unset, never a phantom '1' | ✓ VERIFIED | Same tests cover the clear half (bubble_no None, no override pin); `setSpecialValueText` display contract in `test_inspector_bubble_spin_unset_sentinel` — in suite, PASS |
| 15 | WR-01 preserved: unchanged focus cycles stay silent no-ops (0 vs 0, n vs n); only REAL changes commit | ✓ VERIFIED | Guard comparison `number != _loaded_bubble` unchanged; retained WR-01 tests pass: `test_inspector_unchanged_focus_cycle_is_noop`, `test_inspector_unchanged_commit_is_noop_end_to_end`, `test_inspector_bubble_changed_commit_still_emits` — in suite, PASS |
| 16 | The full suite stays green with only the pre-existing flake deselected | ✓ VERIFIED | Full suite run: 461 passed (451 baseline + 10 new), 1 deselected, 0 failed |

## Regression Status of the Prior 12 Truths

The stale report's 12 truths (PageBox fields/setters + payload-detaching copy; translation_parser + reading_order pure modules; TorchOCRModel + vendored MangaOcr + factory; BoxItem overlay/badge rendering; Inspector dock; InlineEditor semantics; OCR dispatcher + D-04 gate; Load Translations + Auto-Number batch pushes; CR-01 + WR-01..05 review fixes) were regression-checked against the current codebase:

- Core modules present and substantive: `box_model.py` (all 6 setters/copy at lines 111-166), `translation_parser.py` (BUBBLE_RE/SFX_RE/PAGE_MARKER_RE, never raises), `reading_order.py` (XY-Cut + preserve-manual), `torch_impl.py` (TorchOCRModel lazy load, numpy→PIL), `factory.py` ('ocr'→torch), vendored `panelcleaner/ocr/ocr_mangaocr.py`, `inline_editor.py` (commit/cancel/is_active), `load_translations_dialog.py` (paste + file, dialog stays pure).
- All 8 review-fix regression tests (CR-01 payload detach, WR-01 no-op guards, WR-02 cluster walk, WR-03 thresh forwarding, WR-04 `.boxes or []`, WR-05 inspector reload) still in the suite — full suite green confirms no regressions from the gap-closure work (the 04-09 menu/toolbar and 04-10 badge/sentinel changes landed in the same files and are covered by their own tests).

## UAT Closure (authoritative record: 04-UAT.md)

| UAT Item | Result | Notes |
|----------|--------|-------|
| 1. Text overlay legibility on real artwork | **pass** | After 04-08 (tracking/zoom clamp/outline) + 04-09 (fit-in-box, menu, toolbar) fixes — user confirmed 'text now moves with the boxes and scales' |
| 2. Real-model OCR end-to-end on a manga page | **pass** | Auto-OCR on draw, Run OCR, OCR All progress, D-04 dialogs, error UX |
| 3. Inline editor on real artwork + Japanese IME | **pass** | Commit/cancel/click-away/F2/focus rule/IME |
| 4. Inspector + badge on real artwork | **pass** | Badge sizing re-verified after 04-10 digit-sized fix |
| 5. Auto-Number RTL/LTR + preserve-manual + batch undo | **skipped** | USER SCOPE DECISION — deferred (see acknowledged_deferral frontmatter); not a defect, not a must-have failure |
| 6. Load Translations paste + file + report + error UX | **pass** | Bubble-1 sentinel re-verified after 04-10 — 'bubble 1 now assigns' |
| 7. Vertical-metadata toggle fallback | **pass** | Flag preserved, editor horizontal, no crash |

All 7 human-verification items from the stale VERIFICATION.md were exercised in UAT: 6 passed, 1 deferred by explicit user decision. No manual item remains genuinely untested, so none are re-listed as pending human verification.

## Behavioral Spot-Checks (run during this verification)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Overlay tracks box after setRect move + TL-edge resize (04-08 RC-1) | `pytest tests/test_gui_boxes.py::test_text_overlay_tracks_box_after_setrect_move tests/test_gui_boxes.py::test_text_overlay_tracks_box_after_tl_edge_resize` | 9 passed (with 7 other named tests below) | ✓ PASS |
| Overlay wrap + shrink-to-fit + resize-commit rewrap (04-09) | `pytest ...::test_text_overlay_wraps_long_text_to_box_width ...::test_text_overlay_shrinks_to_fit_box_height ...::test_resize_commit_rewraps_overlay_text_canvas` | PASS | ✓ PASS |
| Badge digit-fit (04-10) | `pytest ...::test_badge_rect_sizes_to_digit` | PASS | ✓ PASS |
| Bubble-1 assign + clear end-to-end (04-10) | `pytest ...::test_inspector_bubble_1_assigned_and_cleared_end_to_end` | PASS | ✓ PASS |
| Menubar six-core-only + File-submenu membership (04-09) | `pytest tests/test_gui_batch.py::test_menubar_top_level_has_only_the_six_core_menus ...::test_recent_and_batch_menus_are_file_submenus_not_top_level` | PASS | ✓ PASS |
| Toolbar first action Open Folder (04-09) | `pytest ...::test_toolbar_first_action_is_open_folder` | PASS | ✓ PASS |
| Core goal behaviors: draw→OCR request, double-click editor, commit edited=True, translation commit, translations apply (SC 1-3) | `pytest ...::test_alt_drag_draw_release_emits_ocr_requested ...::test_canvas_double_click_box_opens_inline_editor ...::test_inline_editor_commit_recognized_sets_edited_true ...::test_inline_editor_commit_translation_writes_set_translation ...::test_apply_translations_fills_set_translation_on_matched_boxes` | 8 passed | ✓ PASS |
| Full suite regression | `python -m pytest tests/ -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` | **461 passed, 1 deselected, 0 failed** (53s) | ✓ PASS |

## Anti-Patterns Scan

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| Phase-4 files (box_item, canvas, main_window, inspector_panel, box_model, reading_order, translation_parser, torch_impl, factory, inline_editor, load_translations_dialog) | TBD/FIXME/XXX | none found | 0 matches — no unresolved debt markers |
| `tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` | Pre-existing flake (1px Qt drag rounding) | ℹ️ Info | Confirmed pre-existing from Phase 3; documented in deferred-items.md; deselected in all runs; out of scope |
| Manga RTL reading-order misordering on complex layouts | Deferred by user scope decision | ℹ️ Info | Documented in 04-UAT.md test 5 + acknowledged_deferral; candidate for a future phase ('draw panel' feature note) |

## Requirements Coverage

| Requirement | Description | Plans | Status | Evidence |
| ----------- | ----------- | ----- | ------ | -------- |
| TEXT-02 | User can draw a rectangle and run manga-ocr on just that region to create a box with recognized text | 04-03 (adapter), 04-06 (dispatcher + auto-OCR on draw) | ✓ SATISFIED | SC 1 verified; UAT test 2 pass; REQUIREMENTS.md line 89 marks Complete |
| TEXT-04 | User can edit the recognized OCR text inline in a box to correct recognition mistakes | 04-01, 04-04, 04-05, 04-08, 04-09 | ✓ SATISFIED | SC 2 verified; UAT test 3 pass; REQUIREMENTS.md line 91 Complete |
| TEXT-05 | User can add a manual translation as a second text field per box | 04-01, 04-02, 04-04, 04-07, 04-10 | ✓ SATISFIED | SC 3 verified; UAT test 6 pass; REQUIREMENTS.md line 92 Complete |

All requirement IDs declared across the 10 PLAN frontmatters (TEXT-02 x2, TEXT-04 x5, TEXT-05 x5) are accounted for and map exactly to the phase requirement set. No orphaned requirements.

## MVP-Mode Format Discrepancy (carried forward, already flagged to the user)

ROADMAP.md marks Phase 4 `mode: mvp` but the goal is not in user-story format (`gsd-tools query user-story.validate` returns false). Documented discrepancy, already flagged; `/gsd mvp-phase 4` recommended before the NEXT phase's UAT. Standard goal-backward verification used here (per 01-VERIFICATION.md precedent).

## Acknowledged Deferral (NOT a gap)

- **UAT test 5 — Auto-Number RTL (Manga) reading order on complex layouts:** deferred by the user's explicit scope decision ("just log this since this is a bigger issue than we can fix right now"). Manhwa LTR works; manga RTL misorders complex layouts (XY-Cut insufficient). Recorded in 04-UAT.md with `deferred: true`; candidate for a future phase (panel segmentation + 'draw panel' tool + reading-order rework). Not counted as a must-have failure; excluded from human_verification because it was already user-tested and deliberately deferred.

## Gaps Summary

No blocking gaps. All must-haves verified, all UAT-tested behaviors pass, one documented user-scope deferral (reading-order quality on complex manga layouts) is acknowledged for a future phase. The pre-existing GUI flake remains deselected and out of scope.

---

_Verified: 2026-08-06_
_Verifier: Claude (gsd-verifier, refresh re-verification)_

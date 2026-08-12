---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
verified: 2026-08-12T05:22:48Z
status: passed
score: 44/46 must-haves verified
behavior_unverified: 2 # Backstop truths (verification: backstop) — present + wired, real-font visual behavior not exercised by any test; detailed in behavior_unverified_items and human_verification (UAT re-run covers them)
overrides_applied: 0
re_verification: # Previous VERIFICATION.md existed (status: human_needed, 34/36) BEFORE the gap-closure plans; the 07-UAT.md run then found 7 gaps (G-07-1..G-07-7), fixed by plans 07-06..07-12 + 3 code-review warnings (WR-01..WR-03)
  previous_status: human_needed
  previous_score: 34/36
  gaps_closed:
    - "G-07-1 (major): horizontal-by-default render + upright-stacked Roman in vertical mode (render flag = bool(style.vertical) ONLY at all three render sites; _ASCII_UPRIGHT classification split) — closed by plan 07-07"
    - "G-07-2 (minor): font dropdown contains-match search ('Wild Words' finds 'CC Wild Words') via QSortFilterProxyModel — closed by plan 07-12"
    - "G-07-3 (major): selectable app default font (QSettings 'defaultFontFamily' + default_style() factory + Set as Default Font + both new-box creation sites) — closed by plan 07-11"
    - "G-07-4 (minor): Auto-fit grows short text to fill the box (grow-while-fits capped at min(inner_w, inner_h); shrink/floor paths byte-identical; both orientations) — closed by plan 07-10"
    - "G-07-5 (major): align_v applies to horizontal text on the canvas (overlay dy term restored; overlay-level canvas ≡ bake 3x3 matrix) — closed by plan 07-08"
    - "G-07-6 (blocker): Ctrl+Z native crash 0xC0000409 — box graveyard (QTimer.singleShot(0) release) + Shiboken.isValid paint guard + refs-dropped regressions — closed by plan 07-06"
    - "G-07-7 (major): Mixed align state overridable in multi-select (item-preserving combos, per-axis Mixed→None, _replace_align consumer) — closed by plan 07-09"
    - "WR-01 (warning): QFontComboBox free-typed text never commits (findText membership gate in _emit_style_font_if_changed + _on_default_font_clicked) — fixed 25ee1d3"
    - "WR-02 (warning): re-picking the Mixed sentinel on both axes pushes no undo entry (both-None skip in _emit_style_align_if_changed) — fixed 9095ca1"
    - "WR-03 (warning): graveyard release timer safe against an invalidated canvas at teardown (Shiboken.isValid guard in _release_graveyard) — fixed 2fc2d9c"
  gaps_remaining: []
  regressions: []
behavior_unverified_items: # Emitted because behavior_unverified = 2 — survives into the UAT re-run routing regardless of overall status
  - truth: "vertical boxes render upright CJK glyphs in RTL columns with upright-stacked Latin/numbers"
    test: "UAT test 1 re-run: open a real manga page, draw a box, check the Vertical checkbox (D-13), enter CJK + Latin text, view at 100%/150%/200%; also confirm an OCR-detected-vertical box renders horizontal by default"
    expected: "CJK glyphs upright, columns top-to-bottom flowing right-to-left from the box's top-right inner edge, Latin letters/digits stacked UPRIGHT one above the other (G-07-1 user override) on a real CJK font; horizontal-by-default for every box regardless of detected orientation"
    why_human: "Backstop truth (07-03 backstops / UI-SPEC E5 backstop row): classification/geometry is test-locked via Qt fallback fonts (test_vertical_classification, test_vertical_rotated_advance, test_preflagged_box_renders_horizontal_by_default pass), but the real-CJK-font visual rendering correctness is a held-out end-of-phase visual gate that no automated test exercises"
  - truth: "effects look clean and the canvas stays fluid while dragging a selected box"
    test: "UAT test 2 re-run: enable glow/shadow/outline on a selected box, drag it around the canvas, zoom 100%/150%/200%, verify the halo renders without clipping and the drag stays fluid; also re-check Auto-fit grows short text to fill large boxes (G-07-4) and align V works on horizontal text (G-07-5)"
    expected: "Halos render cleanly (no clipping on canvas or bake); no per-mousemove performance regression (RC-1 reposition stays setPos-only; T-07-13)"
    why_human: "Backstop truth (07-03 backstops / UI-SPEC E3 backstop row): effect pixel correctness, grow-to-fit, and align_v geometry ARE test-locked (test_typeset_effects.py, test_auto_fit_grows_short_text_to_fit, test_overlay_align_v_matrix_equals_bake pass) but the 'looks clean / stays fluid' judgment is human"
human_verification: # Kept per developer directive — the genuine visual/backstop items remain human gates, routed to the UAT re-run (gsd-verify-work); UAT tests 4 and 5 already PASSED and are recorded as such
  - test: "Real-CJK-font tategaki visual check (backstop BS1 — D-11/D-13) — UAT test 1 re-run after G-07-1"
    expected: "A box with Vertical checked renders upright CJK glyphs in top-to-bottom columns flowing right-to-left from the box's top-right inner edge, with Latin letters and digits stacked UPRIGHT one above the other (the G-07-1 user override) — on a REAL CJK font; boxes render horizontal by default regardless of detected orientation"
    why_human: "Backstop truth (verification: backstop, reason insufficient_spec) — the geometry/classification is now test-locked (test_preflagged_box_renders_horizontal_by_default, test_vertical_classification, test_vertical_rotated_advance pass); the visual correctness bar on real fonts remains a held-out end-of-phase gate (UI-SPEC E5 backstop row)"
  - test: "Effects visual quality + canvas fluidity while dragging (backstop BS2 — D-14) — UAT test 2 re-run after G-07-4"
    expected: "Outline/glow/shadow render cleanly and legibly at 100%/150%/200% DPI; Auto-fit now grows short text to fill large boxes (G-07-4); align V works with horizontal text (G-07-5); canvas stays fluid while dragging a selected box (no per-mousemove re-layout — RC-1)"
    why_human: "Backstop truth (verification: backstop) — effect pixels + grow-to-fit + align_v are test-locked (test_typeset_effects.py, test_auto_fit_grows_short_text_to_fit, test_overlay_align_v_matrix_equals_bake pass), but 'looks clean / stays fluid' is a human visual + performance judgment"
  - test: "Inspector styling session with a real font + color (07-05 end-of-phase human gate) — UAT test 3 re-run after G-07-6/G-07-7"
    expected: "Ctrl+Z never crashes (graveyard fix); a multi-select with differing align shows Mixed AND allows overriding each axis (G-07-7); one Ctrl+Z reverses each commit ('Undo: style change' / 'Undo: font size' flashes)"
    why_human: "GUI interaction + visual appearance cannot be fully verified programmatically; the crash fix and Mixed-override behavior ARE test-locked (test_undo_style_commit_with_dropped_refs_no_crash, test_mixed_align_override_commits_per_axis pass)"
  - test: "Bake WYSIWYG at 100% (07-05 end-of-phase human gate — D-01)"
    expected: "File ▸ Export Typeset… (Ctrl+Shift+B) produces a PNG sidecar whose styled text matches the canvas at zoom 100% exactly (position, font, size, color, effects, vertical mode)"
    why_human: "RESOLVED by UAT test 4 (result: pass). Recorded for continuity — the equivalence remains pixel-test-locked (test_canvas_style_paint_equals_bake_pixels, test_text_overlay_pixmap_matches_bake_at_scene_position, test_overlay_align_v_matrix_equals_bake pass)"
  - test: "Prohibition review — 4 must_haves.prohibitions (descriptor-less)"
    expected: "RESOLVED by UAT test 5 (result: pass — human confirmed the LLM-judge verdicts acceptable): P1 no setHtml/rich-text (docstring-only mentions); P2 TextStyle never mutated in place / snapshots detach / Mixed sentinel never persists; P3 vertical never whole-block rotated / bake composites text only onto detached copy; P4 group/style ops push exactly ONE BOXES snapshot / reposition setPos-only"
    why_human: "Prohibitions carried no statement/status/verification descriptor; per ADR-550 D3 they must not be silently absorbed into a passed verdict — human review happened in UAT test 5 and passed"
---

# Phase 7: Typesetting (TRAN-02) — Render Translated Text into the Page — Verification Report (RE-VERIFICATION after gap closure)

**Phase Goal:** User can typeset translated text into the page with full styling controls — font selection, style, size, color, alignment, and effects — producing renderable output rather than Phase 4's translucent review overlay.
**Verified:** 2026-08-12T05:22:48Z
**Status:** passed
**Re-verification:** Yes — previous VERIFICATION.md (human_needed, 34/36) predated the UAT; 7 UAT gaps (G-07-1..G-07-7) fixed by plans 07-06..07-12, 3 code-review warnings (WR-01..WR-03) fixed after review, all regression-locked.

## Goal Achievement

### Observable Truths

Original 34 truths re-checked against the codebase (full-suite 717-pass run covers every one). Truths whose CONTRACT changed under gap closure are re-worded to the new contract — the change was user-directed via UAT, not a regression. Ten new truths (G-07-1..G-07-7 + WR-01..WR-03) added. The two backstops remain behavior-unverified human gates.

| #   | Truth     | Status | Evidence |
| --- | --------- | ------ | -------- |
| 1   | Fresh box renders OPAQUE typeset text on canvas (default TextStyle, Liberation Sans, #e8e8ea fill, 2px #0b0b0e outline); `_OVERLAY_FILL/_OVERLAY_OUTLINE/_OVERLAY_FONT` gone from box_item.py (D-01) | ✓ VERIFIED | `TypesetOverlayItem` (box_item.py:295-408) renders through shared renderer; `rg _OVERLAY_FILL\|_OVERLAY_OUTLINE\|_OVERLAY_FONT` → no matches; defaults in text_style.py:32-43; `test_text_overlay_pixmap_matches_bake_at_scene_position` passes |
| 2   | Export Typeset… (Ctrl+Shift+B) bakes current page (detached) with styled text via the SAME renderer as canvas — canvas ≡ bake; D-04 content rule (translation else recognized else nothing) | ✓ VERIFIED | `action_export_typeset` (main_window.py:416-422), `_on_export_typeset` (5033-5096); `current_focus_text` (text_renderer.py:232); all 6 bake/export equivalence tests pass |
| 3   | Sidecar lands beside source when pristine, `cleaned/` when geometry-altered (D-03); written by `save_image_optimized` (PNG 9 / JPG 95, DPI preserved) | ✓ VERIFIED | `default_typeset_path` via `ocr_json_target_dir` (ocr_export.py); 4 placement/writer tests pass |
| 4   | Auto-fit: box-adaptive base 14×min(w,h)/100 [10,28] as STARTING target — text GROWS while it fits (step 1.1) capped at min(inner_w, inner_h), 12-iteration bound, 5px floor at loop top, shrink path byte-identical for never-fitting text; BOTH orientations (D-15 + G-07-4) | ✓ VERIFIED | layout() auto-fit (text_renderer.py:536-556, `_OVERLAY_FIT_GROW_STEP` 94, grow at 512/599) + `_vertical_fit_size`; `test_auto_fit_grows_short_text_to_fit`, `test_auto_fit_shrinks_wrapped_text_to_fit`, `test_auto_fit_floor_terminates_for_huge_text`, `test_auto_fit_fits_long_text_within_loop_budget`, `test_vertical_auto_fit` all pass (07-10 re-contract) |
| 5   | Bake failure surfaces "Couldn't save '{filename}'." QMessageBox::Critical, never mutates canvas | ✓ VERIFIED | main_window.py:5085-5095; `test_typeset_export_failure_dialog_leaves_canvas_untouched` passes |
| 6   | PageBox.copy() detaches style; canvas.boxes_snapshot() forwards style | ✓ VERIFIED | box_model.py:191-192, canvas.py:1779; detachment tests pass |
| 7   | TextStyle.to_dict()/from_dict() round-trip; V5 clamps, unknown keys ignored, None → defaults | ✓ VERIFIED | text_style.py:144-216; 14 test_text_style.py tests pass |
| 8   | Layout reports overflow; paint() never clips (unclipped WYSIWYG) | ✓ VERIFIED | layout() overflow flag + no-clip paint; overflow tests pass |
| 9   | Shift+click toggles membership; plain click clears others; empty-canvas click clears all + mask fall-through; Esc deselects all (D-08) | ✓ VERIFIED | canvas.py multi-select; 4 tests pass |
| 10  | Edit ▸ Select All Boxes (Ctrl+A) selects every box; gated on ≥1 box AND no async op | ✓ VERIFIED | main_window.py:509-518, gate 1173; `test_select_all_boxes` passes |
| 11  | Dragging any selected box moves the group by same delta; ONE arm-time snapshot; ONE boxes_modified emission; "Moved {n} boxes" flash (D-09) | ✓ VERIFIED | `_group_move` (canvas.py:255, 1155-1220); `test_group_move_one_undo` passes |
| 12  | Delete with multi-selection removes ALL selected silently, ONE pre-delete snapshot, "Deleted {n} boxes" flash | ✓ VERIFIED | group delete path (now routed through graveyard, see T-38); `test_group_delete_one_undo` passes |
| 13  | Affordance: 3px border + tint on ALL selected; handles on PRIMARY only; resize single-box (D-09) | ✓ VERIFIED | `_sync_handles(primary=...)`, resize gate canvas.py:1046; 3 tests pass |
| 14  | Group move never re-layouts during drag — reposition setPos-only (RC-1) | ✓ VERIFIED | `refresh_position` setPos-only (box_item.py:398-408); `test_group_move_no_relayout` passes |
| 15  | layout_vertical per-char: Han/Kana + vertical punctuation UPRIGHT; Latin letters/digits UPRIGHT one above the other (G-07-1 user override of the W3C rotated convention); halfwidth ASCII punctuation + brackets/dashes rotate 90°; RTL columns, wrap at inner_h, 1em columns, per-char centering (D-11 + G-07-1) | ✓ VERIFIED | `_ASCII_UPRIGHT` (text_renderer.py:118) subtracted from `_ASCII_ROTATE` (123); `char_rotates` (159); `test_vertical_classification` + `test_vertical_rotated_advance` re-asserted to upright-Latin contract, pass |
| 16  | Vertical paint rotates ONLY classified runs (translate+rotate(90)+drawText), never whole block; vertical Auto-fit via column count (A8) | ✓ VERIFIED | `_paint_vertical` (677); no whole-block rotate; `rg addText` → docstring-only |
| 17  | Glow = silhouette alpha → numpy stack blur → colorize → DestinationOver at zero offset; shadow = same pass at dx/dy; skip when disabled (D-14) | ✓ VERIFIED | `_draw_effects` (747), `_blur_alpha`/`_colorize_alpha` (834-849); 3 effect tests pass |
| 18  | Effect padding expands bounding rect; allocation BOUNDED — oversize degrades to no-glow + loguru warning, never OOM (T-07-07) | ✓ VERIFIED | `effect_padding` (158-185), `_EFFECT_MAX_DIMENSION`/`_EFFECT_MAX_PIXELS`; 2 tests pass |
| 19  | Effects compose with BOTH orientations through one shared pass (D-01) | ✓ VERIFIED | single `_draw_effects`; `test_effects_vertical_composition` passes |
| 20  | .mas projection preserves full TextStyle: pagebox_to_json writes "style" (to_dict), json_to_pagebox restores (D-07) | ✓ VERIFIED | project_io.py:197/240; `test_style_field_round_trip` passes |
| 21  | Legacy .mas WITHOUT style loads with defaults — optional key, never ProjectFormatError (Pitfall 8) | ✓ VERIFIED | project_io.py:236-240; legacy-load tests pass |
| 22  | _ocr.json block-level "style" via SAME to_dict spelling; D-19 shape otherwise unchanged (Pitfall 6) | ✓ VERIFIED | ocr_export.py:190-191; `test_style_block_one_spelling` (byte-equal) passes; exactly two to_dict writers |
| 23  | OCR_JSON_VERSION pinned by test per Task-2 checkpoint decision | ✓ VERIFIED | ocr_export.py:74 `"2"`; `test_version_is_task2_decision` passes |
| 24  | Load-side V5 coercion on every read path — crafted style blocks clamp, never reach renderer raw | ✓ VERIFIED | `TextStyle.from_dict` V5 boundary; `test_style_v5_clamped_on_load` passes |
| 25  | Inspector Style section (D-05): header+divider, Font QFontComboBox, Style QComboBox, Size QSpinBox 0..200 "Auto" + Auto-fit checkbox, Color 24×24 swatch, Align/Align V, Outline/Glow/Shadow rows; QSS tokens + WR-01 no-op guards | ✓ VERIFIED | inspector_panel.py:367-450, signals 277-283; styling tests pass |
| 26  | Empty state: whole panel disables with extended copy "Select a text box to edit its text, translation, and style." | ✓ VERIFIED | `_EMPTY_STATE` (159); `test_empty_state_disables_styling` passes |
| 27  | Common-value/Mixed (D-10): "Mixed" combos/spin/split swatch/tri-state checkboxes; per-box text fields disable at N>1; hint "Style edits apply to all {n} selected boxes."; ONE override → ALL selected, ONE snapshot + ONE refresh; sentinel never persists (Pitfall 7) | ✓ VERIFIED | `load_multi_selection` (570-710), sentinel guards; `test_mixed_state_presented`, `test_style_commit_applies_to_all`, `test_mixed_sentinel_never_persists`, `test_multi_text_fields_disabled`, `test_hint_label_count`, `test_mixed_effect_value_commit_preserves_per_box_enabled` pass |
| 28   | Uniform selections show real values, never Mixed | ✓ VERIFIED | `load_box` (727-746); `test_style_commit_signal_fires` + styling tests |
| 29  | Vertical checkbox LIVE (D-13 + G-07-1): tooltip replaced; checkbox reads/writes `style.vertical` ONLY (never payload — payload stays None on never-OCR'd boxes); render flag = `bool(style.vertical)` shared by overlay AND bake AND size probe; inline editor stays horizontal (D-12) | ✓ VERIFIED | style.vertical reads/writes at inspector_panel.py:608/772; single-expression flag at box_item.py:698, text_renderer.py:1030, main_window.py:3118 (no OR-with-payload anywhere); `_ensure_payload` gone from main_window (only core/box_model.py model-level lazy construction remains); `test_vertical_checkbox_live`, `test_vertical_toggle_writes_style_and_never_constructs_payload`, `test_vertical_preflagged_box_renders_vertical` pass |
| 30  | Increase/Decrease Font Size (D-16): Ctrl+] / Ctrl+[, ±1px, Auto-fit→manual conversion at rendered size (A11), applies to ALL selected in ONE snapshot, "font size" op name, gated | ✓ VERIFIED | main_window.py:713-731, 3140-3181; `test_size_plus_minus_actions`, `test_size_action_converts_auto_fit` pass; single bindings |
| 31  | Every style commit (incl. vertical toggle) pushes ONE BOXES snapshot with recorded op name "style change" — one Ctrl+Z reverses (D-10/surface 13) | ✓ VERIFIED | `set_pending_boxes_op_name("style change")`; `_undo_op_label` (3290-3293); `test_style_commit_applies_to_all` passes |
| 32  | Manual-size overflow wraps at inner width and renders UNCLIPPED on both canvas and bake (clipped only at page edge) | ✓ VERIFIED | manual path + no-clip paint; `test_overflow_paints_unclipped_below_rect` passes |
| FA1 | Empty-text boxes render nothing and bake nothing (D-04; probe edge: empty input) | ✓ VERIFIED | early-return on empty (box_item.py:366-371); `test_bake_leaves_page_unchanged_when_no_box_has_text` passes |
| FA2 | Text length/width math on Unicode code points, never bytes (probe edge: encoding) | ✓ VERIFIED | Python str indexing; `test_vertical_code_point_indexing` passes |
| 33  | G-07-1: ALL boxes render horizontal by default — a detector-flagged vertical box (`payload.vertical=True`, style None) renders HORIZONTAL; vertical mode renders Roman upright one letter above the other | ✓ VERIFIED | `test_preflagged_box_renders_horizontal_by_default` (renamed + bake spy asserting `vertical=False`), `test_vertical_toggle_writes_style_and_never_constructs_payload` pass; `rg payload.vertical` in gui/ → comment-only (remaining reads are geometry/export metadata in core: image_ops.py:150/277/407, project_io.py:201) |
| 34  | G-07-2: Font dropdown contains/substring search — typing a substring filters installed families (case-insensitive, `QRegularExpression.escape`d), 'Wild Words' surfaces 'CC Wild Words'; filter is display-only (selection never drifts, no spurious commits); clears on load | ✓ VERIFIED | `_font_proxy` QSortFilterProxyModel (inspector_panel.py:409-417, source reparented), single `setFilterRegularExpression` site (1213), signals-blocked restore (1219-1223), clear-on-load; `test_font_filter_contains_match`, `test_font_filter_contains_match_scenario` pass |
| 35  | G-07-3: User can select a default font (Set as Default Font) — persisted under QSettings 'defaultFontFamily'; new user-drawn AND detected boxes born with the saved family; no saved key keeps `style None` (renderer defaults); existing boxes never re-styled | ✓ VERIFIED | `default_style()` Qt-free factory (text_style.py:55-66); reader main_window.py:1897 + writer 3193 + `default_font_requested` signal (inspector_panel.py:299, 1225-1240 with findText gate); `new_box_style_provider` seam (canvas.py:232/2193-2194) wired at main_window.py:136-137; detected boxes main_window.py:3968; tests: `test_default_style_none_uses_default_family`, `test_default_style_explicit_family_overrides_only_family`, `test_set_as_default_button_emits_family`, `test_set_as_default_writes_key_and_flashes_status`, `test_new_user_box_uses_saved_default_family`, `test_new_user_box_keeps_style_none_without_key`, `test_detected_boxes_use_saved_default_family`, `test_detected_boxes_keep_style_none_without_key` pass |
| 36  | G-07-4: Auto-fit grows short text to fill the box (beyond the old 28px clamp) in BOTH orientations — 'hello' in a 300×300 box renders > base, capped at min(inner_w, inner_h); never-fitting text keeps the byte-identical 12×0.9 shrink + 5px floor | ✓ VERIFIED | grow-while-fits-with-cap (text_renderer.py:487-516 horizontal, :599 vertical); `test_auto_fit_grows_short_text_to_fit`, `test_auto_fit_uses_box_adaptive_base` (range assertions), `test_vertical_auto_fit` (5 CJK chars 14→19px), shrink/floor/budget tests UNCHANGED and green; overlay twins updated to grow contract (deviation 5414fa2) |
| 37  | G-07-5: align_v applies to horizontal text on the canvas — overlay re-adds the layout's box-relative origin dy (`dy = origin.y - box.y - inset`); canvas ≡ bake across the full 3×3 align matrix; vertical path dy == 0 (unchanged) | ✓ VERIFIED | box_item.py:417 dy term (single grep match); CR-01 origin-cancel translate byte-unchanged (b0cc53c); `test_overlay_align_v_preserves_dy` (RED-proven pre-fix: 0.0 vs 40.0), `test_overlay_align_v_bottom_and_middle_equals_bake_pixels`, `test_overlay_align_v_matrix_equals_bake` (3×3 pixel matrix), `test_bake_align_v_bottom_places_ink_below_top` pass |
| 38  | G-07-6: Ctrl+Z (undo) and Delete NEVER crash — removed BoxItems retire to a graveyard released only via `QTimer.singleShot(0)` after the pending scene UpdateRequest flush; `TypesetOverlayItem.paint` no-ops on shiboken-deleted wrappers; every removal site (set_boxes, _remove_box, multi-select Delete) routes through the graveyard; undo semantics unchanged | ✓ VERIFIED | `_retire_boxes` (canvas.py:1660) + `_release_graveyard` (1675) + `_graveyard_pending` flag; `QTimer.singleShot(0` exactly 1 real site (1673); removal sites 1508/1733/2241; `Shiboken.isValid(self)` paint guard (box_item.py:344); BEHAVIORAL: `test_undo_style_commit_with_dropped_refs_no_crash` + `test_delete_with_dropped_refs_no_crash` assert weakrefs ALIVE through the pending flush and DEAD only after `processEvents()` (RED-proven pre-fix); `test_group_delete_one_undo`/`test_style_commit_applies_to_all` pin unchanged undo semantics |
| 39  | G-07-7: Mixed align state overridable in multi-select — align combos keep real items under a leading 'Mixed' entry; per-axis Mixed→None translation at commit; `_replace_align` preserves each box's untouched axis; one snapshot; sentinel never persists | ✓ VERIFIED | item-preserving loads (inspector_panel.py:747/758), `_emit_style_align_if_changed` per-axis (1287-1311), `Signal(object, object)`; `_replace_align` (main_window.py:3085) + rewired consumer (3176); `test_mixed_align_keeps_real_items_and_maps_sentinel`, `test_mixed_align_override_commits_per_axis` (one snapshot + one Ctrl+Z) pass |
| 40  | WR-01: QFontComboBox free-typed text NEVER commits — font commits (and Set-as-Default) gated on real installed-family membership (`findText`), so per-keystroke `currentTextChanged` cannot push undo entries or persist garbage families | ✓ VERIFIED | findText gates (inspector_panel.py:1191-1192, 1238-1239); `test_font_free_text_never_commits` passes (typing "Ari"/garbage commits nothing; exact installed-family match commits once) |
| 41  | WR-02: Re-picking the Mixed sentinel on both axes pushes NO undo entry — a both-None commit carries nothing to apply and is skipped at the emit boundary | ✓ VERIFIED | both-None skip (inspector_panel.py:1309-1310); `test_align_sentinel_repick_after_commit_no_op` passes; per-axis real changes still commit |
| 42  | WR-03: Graveyard release timer is safe against an invalidated canvas at teardown — `_release_graveyard` no-ops on shiboken-deleted wrappers (no RuntimeError from the event loop) | ✓ VERIFIED | `if not Shiboken.isValid(self): return` (canvas.py:1690, with Shiboken import); `test_graveyard_release_against_invalidated_wrapper_safe` passes (RED-proven pre-fix) |
| BS1 | vertical boxes render upright CJK glyphs in RTL columns with upright-stacked Latin/numbers | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Classification/geometry test-locked via Qt fallback fonts (T-15/T-33 tests pass); real-CJK-font visual correctness is a backstop → abstains (insufficient_spec) → human verification item #1 (UAT test 1 re-run) |
| BS2 | effects look clean and the canvas stays fluid while dragging a selected box | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Effect pixels + grow-to-fit + align_v test-locked; visual quality + fluidity is a backstop → abstains (insufficient_spec) → human verification item #2 (UAT test 2 re-run) |

**Score:** 44/46 truths verified (32 original truths + 2 flagged assumptions + 7 UAT gap truths + 3 review-fix truths); 2 backstops present + wired but behavior-unverified → human gates.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `manga_ai_studio/core/text_style.py` | TextStyle dataclass + to_dict/from_dict + default_style() factory | ✓ VERIFIED | 216+ lines; `default_style` Qt-free (stdlib-only imports, G-07-3); V5 clamps; single serialization spelling |
| `manga_ai_studio/gui/text_renderer.py` | layout + paint + bake_typeset_page + current_focus_text (+ vertical + effects + grow-to-fit) | ✓ VERIFIED | `_ASCII_UPRIGHT` split (G-07-1), grow-while-fits-with-cap both loops (G-07-4), `bool(style.vertical)` bake flag; no setHtml/addText call sites |
| `manga_ai_studio/core/ocr_export.py` | default_typeset_path + block-level style + OCR_JSON_VERSION "2" | ✓ VERIFIED | Unchanged by gap closure |
| `manga_ai_studio/core/box_model.py` | PageBox.style + copy() detachment | ✓ VERIFIED | Unchanged by gap closure |
| `manga_ai_studio/gui/box_item.py` | renderer-driven opaque overlay child + align_v dy + Shiboken paint guard | ✓ VERIFIED | dy term (417), `Shiboken.isValid(self)` paint guard (344), `bool(style.vertical)` (698) |
| `manga_ai_studio/gui/canvas.py` | multi-select state + boxes_snapshot + box graveyard + default-style provider seam | ✓ VERIFIED | `_retire_boxes`/`_release_graveyard` (1660-1693, WR-03 guard), 3 removal sites, `new_box_style_provider` (232/2193), `_commit_create` applies provider |
| `manga_ai_studio/gui/main_window.py` | export typeset + select-all + size actions + style commit routing + per-axis align + default-font chain | ✓ VERIFIED | `_replace_align` (3085), `_default_font_family`/writer (1897/3193), provider wiring (136), `bool(style.vertical)` (3118) |
| `manga_ai_studio/gui/inspector_panel.py` | Style section + Mixed logic + live vertical + font filter + Set-as-Default + WR-01/WR-02 guards | ✓ VERIFIED | `_font_proxy` (409-417), findText gates (1191/1238), both-None skip (1309), item-preserving align combos (747/758), `default_font_requested` (299) |
| `manga_ai_studio/core/project_io.py` | "style" write + optional read | ✓ VERIFIED | Unchanged by gap closure |
| Tests (13 files) | 5 original new test files + extended; gap-closure regressions in test_gui_boxes.py / test_gui_inspector_styling.py / test_core/test_typeset_layout.py / test_gui_detection_boxes.py | ✓ VERIFIED | All present and substantive; **717 full-suite tests pass, 0 failed** (687 original + 30 gap-closure/review-fix additions — count arithmetic verified: 689→701→703→704→712→714→717) |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| BoxItem overlay | bake compositor | ONE shared renderer path; vertical flag = `bool(style.vertical)` at BOTH sites (G-07-1) | ✓ WIRED — `test_canvas_style_paint_equals_bake_pixels`, `test_text_overlay_pixmap_matches_bake_at_scene_position`, `test_overlay_align_v_matrix_equals_bake` |
| Overlay set_content | layout result origin | `dy = result.origin.y() - box_rect.y() - _OVERLAY_INSET` (box_item.py:417) — overlay re-adds exactly what layout encoded | ✓ WIRED — `test_overlay_align_v_preserves_dy` + pixel matrix |
| canvas.boxes_snapshot() | PageBox.style | `style=item.pagebox.style` (canvas.py:1779) | ✓ WIRED — `test_pop_boxes_undo_restores_pre_edit_style` |
| BoxItem removal sites | deferred deletion | `_retire_boxes` (set_boxes:1733, _remove_box:2241, group Delete:1508) → graveyard → `QTimer.singleShot(0)` release | ✓ WIRED — refs-dropped regressions + WR-03 invalidated-wrapper test |
| Inspector align combos | main_window `_replace_align` | per-axis Mixed→None via `Signal(object, object)`; `_replace_align` skips None axes per box | ✓ WIRED — `test_mixed_align_override_commits_per_axis` |
| Inspector Set-as-Default | QSettings 'defaultFontFamily' | `default_font_requested` signal (299) → writer (main_window.py:3193) | ✓ WIRED — `test_set_as_default_writes_key_and_flashes_status` |
| QSettings reader | new-box creation sites | `new_box_style_provider` seam (canvas) + `_build_detected_boxes` style application (main_window.py:3968) | ✓ WIRED — `test_new_user_box_uses_saved_default_family`, `test_detected_boxes_use_saved_default_family` |
| Font filter line edit | font combo view | `_font_proxy` QSortFilterProxyModel over combo's own model (source reparented), single `setFilterRegularExpression` site | ✓ WIRED — `test_font_filter_contains_match` (+ scenario pin) |
| TextStyle.to_dict | project_io + ocr_export writers | Single spelling, both call `to_dict()` | ✓ WIRED — `test_style_block_one_spelling` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| TypesetOverlayItem pixmap | text/style/box_rect | PageBox.payload + PageBox.style (now via `bool(style.vertical)`) | ✓ — real translation text + non-default styles; align_v dy flows through `_ink_offset` | ✓ FLOWING |
| bake_typeset_page output | page_np + boxes | canvas.get_image_numpy() + imf.boxes | ✓ — D-04 skip rule; align_v matrix pins parity | ✓ FLOWING |
| Inspector Style section | style values | Selected PageBox.style objects (style.vertical for the checkbox) | ✓ — uniform/Mixed population; default family flows from QSettings → provider → new boxes | ✓ FLOWING |
| Auto-fit rendered size | font_size_px | layout() grow-while-fits result (shared by overlay, bake, size probe) | ✓ — deterministic, range-locked per box | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite (definitive regression — includes every gap-closure and review-fix regression) | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` | **717 passed, 0 failed** in 107s (3 deprecation warnings only) | ✓ PASS |
| G-07-6 refs-dropped + WR-03 graveyard lifetime (event-loop ordering invariant) | `pytest test_gui_boxes.py -k "dropped_refs or graveyard_release" -q` | 3 passed (included in 717) | ✓ PASS |
| G-07-1 vertical contract (horizontal-by-default, upright Roman) | `pytest test_gui_boxes.py -k "preflagged_box_renders_horizontal or vertical_toggle_writes_style" -q` + `test_vertical_classification` + `test_vertical_rotated_advance` | all passed (included in 717) | ✓ PASS |
| G-07-5 align_v canvas≡bake | `pytest test_gui_boxes.py -k "overlay_align_v" -q` + `test_bake_align_v_bottom_places_ink_below_top` | 5 passed (included in 717) | ✓ PASS |
| G-07-4 grow-to-fit + byte-identical shrink | `pytest test_typeset_layout.py -k "auto_fit" -q` | all passed (included in 717) | ✓ PASS |
| G-07-3 default font chain | `test_default_style_*` + `test_set_as_default_*` + `test_new_user_box_*` + `test_detected_boxes_*` | 8 passed (included in 717) | ✓ PASS |
| G-07-2 font contains-search on real font DB (266 families) | `test_font_filter_contains_match*` | 2 passed (included in 717) | ✓ PASS |
| G-07-7 + WR-01/WR-02 align/font commit discipline | `test_mixed_align_*` + `test_align_sentinel_repick_after_commit_no_op` + `test_font_free_text_never_commits` | 4 passed (included in 717) | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files exist in the repo. The gap-closure plans' probes were pytest-based (RED gates: `a703f37` align_v dy, `d3604c0` refs-dropped, `0841914` grow-to-fit, `97ad8d8` font filter, `caba263` default font, `8fe9076` Mixed align; WR fixes' RED→GREEN proven per 07-REVIEW-FIX.md) — all re-confirmed GREEN inside the 717-pass run above. Commit evidence: all 24 gap-closure commits present in `git log` (verified by hash enumeration).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| TRAN-02 | All 12 plans (07-01..07-12) | User can render translated text into the page (basic typesetting: font, size, color) — v2 deferred line in REQUIREMENTS.md, explicitly pulled into Phase 7 by ROADMAP | ✓ SATISFIED | Full styling surface (font family/style + contains-search + default font, size + Auto-fit grow, color, H/V alignment incl. Mixed override, outline/glow/shadow effects, vertical tategaki with upright Roman), opaque canvas rendering + bake export (D-01), persistence (D-07), crash-free undo. Phase goal scope fully delivered and the 7 UAT gaps closed with regression tests |

No orphaned requirements: ROADMAP Phase 7 maps only TRAN-02, and every plan declares TRAN-02 in its `requirements:` frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX` markers in any phase-modified source OR test file (canvas.py, box_item.py, inspector_panel.py, main_window.py, text_renderer.py, text_style.py + 4 touched test files grep-clean) | — | None |
| — | — | `setHtml` / `QPainterPath.addText` appear only in docstrings documenting the crash deviation | ℹ️ Info | None — no call sites (prohibition P1 upheld) |
| `deferred-items.md` | 3-17 | Latent TextOverlayItem paint UAF — **structurally closed** by the G-07-6 graveyard + `Shiboken.isValid` paint guard (exactly the mitigation the deferred item recommended); the file's "Status: open" header was not updated | ℹ️ Info | None — the fix is in code and regression-locked (`test_undo_style_commit_with_dropped_refs_no_crash`, `test_delete_with_dropped_refs_no_crash`, `test_graveyard_release_against_invalidated_wrapper_safe`); doc-only staleness |
| — | — | Empty/placeholder implementations (`return null`, hardcoded empties) | — | None found; `_EMPTY_STATE`, `new_box_style_provider = None`, and 1×1 pre-render pixmap are legitimate by-design states |

### Human Verification Required

All items below are the DOCUMENTED human gates from the prior verification; none are new. UAT tests 4 and 5 already passed. Items 1-3 carry automated evidence for their fixes and await visual re-confirmation (UAT re-run). Developer directive for this re-verification: status `passed` is valid because every automated-checkable must-have verifies and ONLY these documented human items remain.

1. **Real-CJK-font tategaki visual check (backstop BS1 — UAT test 1 re-run)** — see `behavior_unverified_items[0]`. Expected: horizontal by default for every box; Vertical checked renders upright CJK in RTL columns from the top-right inner edge, Latin/digits stacked UPRIGHT one above the other, on a real CJK font.
2. **Effects visual quality + canvas fluidity while dragging (backstop BS2 — UAT test 2 re-run)** — see `behavior_unverified_items[1]`. Expected: clean halos at 100/150/200%, Auto-fit grows text to fill, align V works on horizontal text, no per-mousemove regression.
3. **Inspector styling session (07-05 end-of-phase gate — UAT test 3 re-run)** — Ctrl+Z never crashes; Mixed align overridable per axis; one Ctrl+Z per commit; Set-as-Default font persists; font filter finds fonts by substring.
4. **Bake WYSIWYG at 100% (07-05 gate)** — RESOLVED: UAT test 4 passed (result recorded in 07-UAT.md).
5. **Prohibition review (4 descriptor-less must_haves.prohibitions)** — RESOLVED: UAT test 5 passed (human confirmed the non-authoritative LLM-judge verdicts acceptable).

### Gaps Summary

**No gaps.** All 7 UAT gaps (G-07-1..G-07-7, incl. the G-07-6 blocker) and all 3 code-review warnings (WR-01..WR-03) are closed with automated evidence — each fix is present in the codebase (verified by grep/read, not just SUMMARY claims), each has a named passing regression test (many RED-proven per the plans' TDD gates), and the full suite run on the pinned interpreter reports **717 passed, 0 failed** (exactly the count claimed by 07-REVIEW-FIX.md; the arithmetic 687→689→701→703→704→712→714→717 is consistent). The G-07-6 event-loop ordering invariant is behaviorally exercised (weakref-alive-through-flush assertions with real `processEvents()`), so it is VERIFIED, not merely present. No new regressions found: the original 34 truths still hold, with 4 re-worded to the user-directed contract changes (auto-fit growth, upright Roman, style-driven vertical checkbox). The two backstops remain the only non-verified truths and are the documented human gates routed to the UAT re-run.

**Status rationale:** `passed` per the developer's explicit directive for this re-verification — every automated-checkable must-have verifies (44/46; the 2 non-verified are the documented `verification: backstop` truths) and only the documented human items remain (all 5 listed above were covered by the UAT; 2 resolved as passed, 3 carry test-locked fixes awaiting visual re-confirmation).

---

_Verified: 2026-08-12T05:22:48Z_
_Verifier: the agent (gsd-verifier)_
_Re-verification: yes — after gap-closure plans 07-06..07-12 and review fixes WR-01..WR-03_

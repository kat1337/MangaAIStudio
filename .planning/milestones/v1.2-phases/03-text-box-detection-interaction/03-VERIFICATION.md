---
phase: 03-text-box-detection-interaction
verified: 2026-08-04T03:55:00Z
status: passed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  mode: post_uat
  previous_verified: 2026-07-29T16:45:00Z
  note: "Re-verified 2026-08-04 after post-gap-closure cursor-overlay fix + user live UAT. The 4 human_verification items below were confirmed by the user in 03-UAT-REVERIFY.md (4/4 pass). status canonicalized human_needed -> passed per verify-work complete_session (zero UAT issues)."
human_verification:
  - test: "Launch app, open a manga chapter text page, press D (Detect Text) with Detect Boxes on. Confirm green boxes appear over detected text regions and overlay auto-toggles on."
    expected: "Green (#5fd068) BoxItems render over each detected text region; box overlay action auto-checks; mask also appears (Phase 1)."
    why_human: "Real CTD model detection quality + visual green-border legibility on real artwork cannot be asserted by the offscreen GUI suite (which uses a FakeDetectionModel and asserts hex values, not visual correctness)."
  - test: "Alt+left-drag on empty canvas to draw a user box; move it; resize each of the 4 corner handles; press Delete; press Esc to deselect."
    expected: "Amber (#f5a623) dashed preview during drag; amber border + 3px selected stroke + tinted fill + 4 corner handles (8x8 viewport px) on the new box; fluent move; corner resize clamps at ~8x8 scene px; Delete removes instantly with no dialog (D-12); Esc deselects."
    why_human: "Tactile feel, cursor shapes (SizeFDiagCursor/SizeBDiagCursor), and amber legibility against varying artwork regions are perception judgments grep/tests cannot make."
  - test: "On a page with a mask stroke + a box move + an inpaint, press Ctrl+Z three times. Confirm ops reverse in chronological order (inpaint -> box move -> mask edit) and the status bar flashes 'Undo: {op}' transiently."
    expected: "Unified-timeline pop across MASK/IMAGE/BOXES; status bar shows 'Undo: inpaint' / 'Undo: box move' / 'Undo: mask edit' for ~3s each."
    why_human: "Real-time interleaved undo ordering across live ops on running app — a state-transition sequence the per-test GUI suite exercises against synthetic state, not against a real mask/inpaint pipeline."
  - test: "Detect boxes on page 1; Alt+drag a user box; delete a detected box. Switch to page 2. Switch back to page 1. Confirm all box work survived. Then delete a box and press Ctrl+Z to confirm it recovers (D-12 safety)."
    expected: "All box edits (user box, deletions, detected boxes) persist across the page round-trip; Ctrl+Z after a silent delete restores the box."
    why_human: "Persistence round-trip on real multi-page navigation + Ctrl+Z recoverability of a deleted box are runtime behaviors requiring the live app (synthetic round-trip is covered by tests; real artwork + real CTD output is not)."
behavior_unverified_items:
  - truth: "Box edits (create/move/resize/delete) push BOXES snapshots and the unified Ctrl+Z round-trips through undo/redo"
    test: "Move a box, press Ctrl+Z, confirm it returns; press Ctrl+Shift+Z, confirm redo restores it."
    expected: "Box move undone then redone without timeline corruption."
    why_human: "The CR-01 regression tests (test_box_edit_is_undoable, test_box_restore_does_not_repush) prove the wiring end-to-end against synthetic state; the live app on real artwork with interleaved mask/inpaint ops is the human confirmation."
  - truth: "Re-detect replaces detected boxes but preserves user boxes (D-03)"
    test: "Draw an amber user box; run Detect; confirm the user box survives and detected boxes are replaced."
    expected: "User box persists; detected boxes refreshed."
    why_human: "test_redetect_replaces_detected_keeps_user covers the synthetic path; real CTD output quality on real artwork is a human judgment."
  - truth: "Hidden box overlay disables hit-testing (Pitfall 5) — left-click where a hidden box was paints mask"
    test: "Toggle overlay off (Shift+M); left-click where a box was; confirm mask paints, no box selected."
    expected: "Mask painting works; no box selected."
    why_human: "test_hidden_layer_no_box_hit_falls_through_to_mask covers synthetic; real mask-tool feel on running app is human."
  - truth: "Deleted box is silently removed and Ctrl+Z recovers it (D-12 safety)"
    test: "Select a box, press Delete, press Ctrl+Z; confirm the box reappears."
    expected: "Box vanishes instantly (no dialog); Ctrl+Z restores it."
    why_human: "test_delete_selected_box_silent + test_box_edit_is_undoable cover the wiring; the live recoverability on running app is the human confirmation."
---

# Phase 3: Text Box Detection & Interaction — Verification Report

**Phase Goal:** User can detect text boxes as first-class editable objects (not pixel masks) and correct detection errors by selecting, moving, resizing, and deleting boxes on the canvas, with per-page persistence and a unified undo over mask/image/box ops.
**Verified:** 2026-08-04T03:55:00Z
**Status:** passed
**Re-verification:** Yes — canonicalized from `human_needed` → `passed` on 2026-08-04 after the 4 deferred human-verification items were confirmed by user live UAT (03-UAT-REVERIFY.md, 4/4 pass) and a post-gap-closure fix (brush cursor overlay root cause; see .planning/debug/resolved/box-resize-move.md).

## Goal Achievement

The phase goal is structurally achieved in code: TEXT-01 (detect → editable boxes) and TEXT-03 (select/move/resize/delete) are delivered by real, tested implementations, plus the two cross-cutting supports (per-page persistence + unified undo collapse). The CR-01 BLOCKER from code review (box edits were never pushed to the undo stack) is RESOLVED — verified by reading the wiring and by running the two dedicated regression tests. The deferred human-verification items (visual detection quality, real-artwork legibility, live interleaved undo feel) were confirmed by user live UAT on 2026-08-04 (03-UAT-REVERIFY.md 4/4 pass), so the overall status is `passed`.

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | TEXT-01: running text-box detection creates editable text-box objects (not a pixel mask) | ✓ VERIFIED | `main_window.py:1538-1540` `_on_detection_finished` reads `result["blocks"]` and, when `action_detect_boxes_mode.isChecked()`, calls `_build_detected_boxes(blk_list)`. `_build_detected_boxes` (1544-1641) coerces xyxy via `textblock_to_box`, bounds-clamps to image rect, drops zero-area, builds `PageBox(origin=DETECTED, payload=blk)`, rebuilds the layer via `set_boxes`, auto-shows overlay, and pushes a BOXES snapshot. `test_builds_boxes_when_mode_on` + 11 sibling tests pass. The worker is byte-identical to Phase 1 (blocks were already in the result dict). |
| 2 | TEXT-01: Detect Boxes mode toggle gates box creation (D-01); off = Phase 1 mask-only | ✓ VERIFIED | `main_window.py:386-389` `action_detect_boxes_mode` checkable QAction default-checked; `main_window.py:1538` gates the build branch. `test_no_boxes_when_mode_off` + `test_detect_boxes_mode_action_exists_and_defaults_checked` pass. |
| 3 | TEXT-01: V5 input validation — model xyxy coerced, bounds-clamped, zero-area dropped (untrusted) | ✓ VERIFIED | `main_window.py:1581-1594` clamp via `min(max(...))` against img_w/img_h, drop on `x2<=x1 or y2<=y1` with debug log. `test_v5_clamps_out_of_range_xyxy`, `test_v5_drops_zero_area_after_clamp`, `test_v5_clamps_negative_origin_to_zero` all pass. |
| 4 | TEXT-01: D-03 re-detect replaces detected, keeps user; D-04 confirm gate before replacing | ✓ VERIFIED | `main_window.py:1568-1571` D-04 gate fires when ≥1 DETECTED box exists; `_confirm_replace_boxes` (1643+) mirrors mask gate. `main_window.py:1611-1612,1620` user boxes preserved + detected replaced. `test_redetect_replaces_detected_keeps_user`, `test_redetect_confirm_gate_cancel_aborts`, `test_confirm_gate_skipped_when_no_detected_boxes` pass. |
| 5 | TEXT-03: select / move / resize / delete boxes on the canvas (D-05/D-06/D-07/D-08/D-12/D-13) | ✓ VERIFIED | `box_item.py` BoxItem(QGraphicsRectItem) z=100, origin-coloured pen (#5fd068/#f5a623), 2px/3px selection, tinted brush; 4 CornerHandle z=150, 8x8 viewport px, ItemIgnoresTransformations, SizeFDiag/SizeBDiag cursors. `canvas.py:855-873` dispatch order pan→box→mask with fall-through; Delete/Esc handlers (1059-1065). `test_gui_boxes.py` 28 tests pass (select/move/resize-clamp/delete-silent/alt-drag-create/hidden-layer/snapshot-detached). |
| 6 | Unified undo over mask/image/box ops (D-10/D-11); box edits are undoable (CR-01 resolved) | ✓ VERIFIED | `history_manager.py`: 3 stacks + monotonic `_seq` stamps (no wall-clock — Pitfall 4 honored, verified by grep), `push_boxes_state`/`pop_boxes_undo/redo`, unified `undo()/redo()` returning `(kind, value)`, `can_undo/can_redo` union, `clear()` over 6 lists. CR-01 fix: `main_window.py:1019` `boxes_modified.connect(self._on_boxes_modified)`; `_on_boxes_modified` (1065) pushes; `_suppress_boxes_push` guard (1088) wraps all 3 restore sites (apply_undo_boxes 1198, _build_detected_boxes 1618, on_page_selected 834). `test_box_edit_is_undoable` + `test_box_restore_does_not_repush` pass — proving undo round-trips and restores do not re-push (WR-05 closed). |
| 7 | Per-page box persistence (Phase 2 D-11 mirror) | ✓ VERIFIED | `main_window.py:743,768-770` Step 1 outgoing save uses `_last_page_index` + `canvas.boxes_snapshot()`; `main_window.py:821-836` Step 4 incoming restore via `set_boxes` with origin split; page-switch calls `reset_history`→`clear()` over 6 lists. `test_box_persistence_round_trip`, `test_box_persistence_uses_copy`, `test_outgoing_index_uses_last_page_index`, `test_page_switch_resets_boxes_stack` pass. |
| 8 | Surface 13 undo collapse: 2 toolbar buttons / 2 menu items / unified Ctrl+Z; Alt+Z removed; orphaned strings fixed | ✓ VERIFIED | `grep -c "Alt+Z" main_window.py` == 0 (no shortcut, no tooltip, no dialog string). No `action_undo_mask`/`action_redo_mask`/`on_undo_mask`/`on_redo_mask` remain (grep == 0). `on_undo`/`on_redo` (1131/1151) call `history.undo/redo` and route `(kind,value)` to `apply_undo_{mask,image,boxes}`; transient `"Undo: {op}"`/`"Redo: {op}"` feedback (1148/1162). Both orphaned strings fixed: `main_window.py:1326` ("You can undo with Ctrl+Z.") and `:1718` ("undo is available via Ctrl+Z."). `test_toolbar_collapsed_to_two_buttons`, `test_mask_undo_shortcut_removed`, `test_mask_undo_actions_and_methods_removed`, `test_orphaned_strings_fixed` pass. |

**Score:** 8/8 truths verified (4 present-but-behavior-unverified on the live-app path — see Human Verification).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `panelcleaner/structures.py` | full vendored ~749 lines, GPL v3, Box/BoxType/MaskFittingResults/MaskData/MaskerData/PageData | ✓ VERIFIED | 764 lines; full surface imports cleanly (smoke verified); `json.loads` only, no eval/pickle; no security hazards. |
| `panelcleaner/masker.py` | vendored ~151 lines, ost-import guarded (Pitfall 1) | ✓ VERIFIED | 178 lines; ost guard present (line 35-37, `ost = None` confirmed at runtime); `mask_page` dead code; `json.loads` only. |
| `manga_ai_studio/core/box_model.py` | PageBox dataclass + textblock_to_box + DETECTED/USER; D-15 seam (mask/std_dev default None) | ✓ VERIFIED | 106 lines; PageBox composes (not subclasses) Box; D-15 seam defaults-None verified by smoke; docstring surfaces D-15 explicitly. |
| `manga_ai_studio/core/image_file.py` | boxes slot + has_boxes | ✓ VERIFIED | boxes slot + has_boxes() verified (smoke); mirrors Phase 2 mask slot. |
| `manga_ai_studio/core/history_manager.py` | 3 stacks + unified timeline + monotonic stamps | ✓ VERIFIED | All methods present (grep); no wall-clock calls (Pitfall 4 honored); unified smoke passes. |
| `manga_ai_studio/gui/box_item.py` | BoxItem + CornerHandle (D-05/D-06/D-09) | ✓ VERIFIED | All UI-SPEC §12 specifiers present (grep); 28 component tests pass. |
| `manga_ai_studio/gui/canvas.py` | box layer + hit-test dispatch + create/move/resize/delete + boxes_modified + boxes_snapshot + set_boxes + toggle | ✓ VERIFIED | All wiring present (grep); dispatch order verified by reading 840-873. |
| `manga_ai_studio/gui/main_window.py` | _on_detection_finished, _build_detected_boxes, mode toggle, _confirm_replace_boxes, on_page_selected boxes seam, on_undo/on_redo, apply_undo_boxes, Alt+Z removed, strings fixed, CR-01 wiring | ✓ VERIFIED | All extensions present and wired (grep + read); CR-01 fix empirically confirmed. |
| Test files (7) | structures/masker_vendor/box_model/history_boxes/test_history (updated)/test_gui_boxes/test_gui_detection_boxes/test_box_persistence | ✓ VERIFIED | All exist; 115 Phase 3 tests pass. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `_on_detection_finished` | `result["blocks"]` (blk_list) | `main_window.py:1538-1540` reads result["blocks"], gated by mode | ✓ WIRED | Phase 1 discard replaced; worker unchanged. |
| `boxes_modified` signal | `_on_boxes_modified` → `push_boxes_state` | `main_window.py:1019` connect + `_on_boxes_modified` (1065) | ✓ WIRED | CR-01 fix confirmed; `_suppress_boxes_push` guard wraps all 3 restore sites. |
| `on_undo`/`on_redo` | `history.undo/redo` → `apply_undo_{mask,image,boxes}` | `main_window.py:1131-1180` | ✓ WIRED | Unified pop + (kind,value) routing; status feedback. |
| `on_page_selected` Step 1/Step 4 | `image_files[idx].boxes` save/restore | `main_window.py:768-770` (outgoing) + `821-836` (incoming) | ✓ WIRED | `_last_page_index` for outgoing; origin split on restore; reset_history clears BOXES. |
| `box_item.current_box()` → `boxes_snapshot()` → `push_boxes_state` | fresh int Box materialization (Pitfall 3/6) | `box_item.py:268` + `canvas.py:1230` | ✓ WIRED | Detached snapshot regression (`test_boxes_snapshot_detached`) passes. |
| Hit-test dispatch pan→box→mask fall-through | `canvas.py:855-873` | ✓ WIRED | Order verified by reading; `test_mask_painting_still_works_with_box_layer_visible` passes. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `BoxItem` (canvas box layer) | `pagebox` (box/origin/payload) | `_build_detected_boxes` PageBox build from `blk.xyxy` (real model TextBlocks) | Yes — payload is the live TextBlock | ✓ FLOWING |
| `boxes_snapshot()` return | `list[PageBox]` | `box_item.current_box()` per item (fresh int Box from live rect) | Yes — materialized from live rects | ✓ FLOWING |
| `ImageFile.boxes` (persistence) | `list[PageBox]` | `canvas.boxes_snapshot()` on page-leave | Yes — real canvas state | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Vendored structures/masker + foundation imports | `python _verify_smoke.py` (json.loads/Box/PageBox/unified pop) | All 6 smoke assertions pass; `ost = None` confirmed | ✓ PASS |
| Full test suite (offscreen Qt) | `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` | 248 passed in 4.18s | ✓ PASS |
| Phase 3 test subset (8 files) | `pytest tests/test_core/test_{structures,masker_vendor,box_model,history_boxes}.py tests/test_history.py tests/test_gui_boxes.py tests/test_gui_detection_boxes.py tests/test_box_persistence.py -v` | 115 passed | ✓ PASS |
| CR-01 regression (undo wiring + no-repush) | `pytest tests/test_box_persistence.py::test_box_edit_is_undoable tests/test_box_persistence.py::test_box_restore_does_not_repush tests/test_core/test_history_boxes.py -q` | 16 passed | ✓ PASS |

### Probe Execution

Step 7c SKIPPED — this phase declares no probe scripts (`scripts/*/tests/probe-*.sh` do not exist; phase is not a migration/tooling phase). The phase's runnable checks are the pytest suite (run above) per VALIDATION.md.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| TEXT-01 | 03-01, 03-04, 03-05 | User can run text-box detection across a page to create editable text-box objects (not a pixel mask) | ✓ SATISFIED | `_build_detected_boxes` + mode toggle + V5 + D-03/D-04 + persistence + undo. Marked Complete in REQUIREMENTS.md (line 88); traceability confirmed against code. |
| TEXT-03 | 03-02, 03-03, 03-05 | User can select, move, resize, and delete text boxes on the canvas to correct detection errors | ✓ SATISFIED | BoxItem + CornerHandle + canvas dispatch + Delete/Esc + Alt+drag create + unified undo over box edits. Marked Complete in REQUIREMENTS.md (line 90); traceability confirmed against code. |

No orphaned requirements (REQUIREMENTS.md maps only TEXT-01 and TEXT-03 to Phase 3; both are claimed by plans and satisfied).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `main_window.py` (via history_manager pop_mask_undo line 153) | — | WR-01: `current_mask.copy()` would crash if `on_undo` fires with `_mask_undo` non-empty but `canvas.has_mask()` False (None.copy()) | ℹ️ Info (open warning) | Latent crash path; pre-existing Phase 1 debt, not introduced by Phase 3. `apply_undo_mask` has a None/isNull guard (canvas.py:485) but `pop_mask_undo`'s `current_mask.copy()` precedes it. Not a goal-blocker; surfaced for awareness. |
| `main_window.py:1570` (D-04 gate) | — | WR-02: mask-replace gate and box-replace gate are non-atomic (mask already replaced before box gate can cancel) | ℹ️ Info (open warning) | Advisory; the box gate can be cancelled after the mask already changed (recoverable via Ctrl+Z). Not a goal-blocker. |
| `canvas.py:1330` (`_begin_resize`) | — | WR-03: `assert isinstance(item, BoxItem)` unguarded; stripped under `python -O` | ℹ️ Info (open warning) | Advisory; orphaned handle edge case. Not exercised in tests; not a goal-blocker. |
| `canvas.py:967-971` (move-commit) | — | WR-04: a plain select-click (no drag) emits `boxes_modified`, pushing a redundant no-op BOXES snapshot | ℹ️ Info (open warning) | Advisory; consumes a history slot on a no-op select. Not a goal-blocker. |
| `canvas.py:1152-1189` (`set_boxes`) | — | WR-06: `set_boxes` does not reset `_moving_box`/`_resizing_box`/`_creating_box` — dangling refs if called mid-drag | ℹ️ Info (open warning) | Advisory; only manifests on a signal-driven mid-drag rebuild. Not a goal-blocker. |
| Production files (all 8) | — | TBD/FIXME/XXX/PLACEHOLDER scan | ✓ NONE | No debt markers in any Phase 3 production file (grep returned 0). |

**Open warnings disposition:** The 5 open warnings from `03-REVIEW.md` (WR-01, WR-02, WR-03, WR-04, WR-06) are advisory robustness/quality items. None block the phase goal (TEXT-01/TEXT-03 + persistence + unified undo are all delivered and tested). The reviewer's BLOCKER (CR-01) + its coupled WR-05 are RESOLVED (commits 2dd7a9b test-first, ad7b19d fix) and the orchestrator's deviation scrutiny (before-state push convention) is corroborated by the regression tests. These warnings are surfaced for future-phase cleanup, not as verification blockers.

### Security Surface (vendored files — D-14)

Corroborates the code reviewer's audit:

| Check | Result | Evidence |
| --- | --- | --- |
| `eval` / `exec` / `pickle` / `compile` in vendored files | ✓ NONE | grep returned 0 across `panelcleaner/masker.py` + `panelcleaner/structures.py` |
| Only deserialization primitive | `json.loads` | `structures.py:205,669` (JSON attribute parsing); `masker.py` none |
| `os.system` / `subprocess` / `shell=True` / `__import__` | ✓ NONE | grep returned 0 |
| ost-import guard (Pitfall 1) | ✓ PRESENT | `masker.py:35-37` try/except, `ost = None` confirmed at runtime |
| `mask_page` dead code | ✓ CONFIRMED | Never called by `manga_ai_studio/` (grep); reviewer's "dead code" claim corroborated |
| License compatibility (GPL v3 → GPL v3) | ✓ HONORED | D-12 vendoring header present per acceptance criteria |

**security hook verdict:** PASS (no halt). The vendored `structures.py` + `masker.py` are security-safe.

### Nyquist Coverage (validate-phase hook)

`03-VALIDATION.md` (status: draft, nyquist_compliant: true) defines a per-task verification map covering all 5 plans × 8 tasks mapped to TEXT-01/TEXT-03, with automated pytest commands for each. Wave 0 headless stubs created; 3 GUI test files created inline via TDD in their own waves (deviation noted, sampling continuity held). All 248 tests green.

**nyquist hook verdict:** PASS (no halt). Coverage is well-defined and the suite is green.

### Human Verification Required

The automated suite (248 green, including 16 CR-01 regression tests) verifies the wiring and mechanics against synthetic state with `FakeDetectionModel`. The following require human confirmation on the running app with real artwork and the real CTD model — these are the deferred end-of-phase checkpoints from plans 03-03, 03-04, 03-05 (auto-approved under `auto_advance=true` + `human_verify_mode=end-of-phase`):

### 1. Detection quality + green-border legibility on real artwork
**Test:** Launch app, open a manga chapter text page, press D (Detect Text) with Detect Boxes on. Confirm green boxes appear over detected text regions and overlay auto-toggles on.
**Expected:** Green (#5fd068) BoxItems render over each detected text region; box overlay action auto-checks; mask also appears (Phase 1). Note any false positives/negatives.
**Why human:** Real CTD model detection quality + visual green-border legibility on real artwork cannot be asserted by the offscreen GUI suite (which uses a FakeDetectionModel and asserts hex values, not visual correctness).

### 2. Box interaction tactile feel + amber legibility
**Test:** Alt+left-drag on empty canvas to draw a user box; move it; resize each of the 4 corner handles; press Delete; press Esc to deselect.
**Expected:** Amber (#f5a623) dashed preview during drag; amber border + 3px selected stroke + tinted fill + 4 corner handles (8x8 viewport px) on the new box; fluent move; corner resize clamps at ~8x8 scene px; Delete removes instantly with no dialog (D-12); Esc deselects; SizeFDiagCursor on TL/BR, SizeBDiagCursor on TR/BL.
**Why human:** Tactile feel, cursor shapes, and amber legibility against varying artwork regions are perception judgments grep/tests cannot make.

### 3. Unified undo ordering across interleaved ops on live app
**Test:** On a page with a mask stroke + a box move + an inpaint, press Ctrl+Z three times. Confirm ops reverse in chronological order and the status bar flashes "Undo: {op}" transiently.
**Expected:** Unified-timeline pop across MASK/IMAGE/BOXES; status bar shows "Undo: inpaint" / "Undo: box move" / "Undo: mask edit" for ~3s each.
**Why human:** Real-time interleaved undo ordering across live ops on running app — a state-transition sequence the per-test GUI suite exercises against synthetic state, not against a real mask/inpaint pipeline.

### 4. Persistence round-trip + Ctrl+Z recoverability of deleted box on live app
**Test:** Detect boxes on page 1; Alt+drag a user box; delete a detected box. Switch to page 2. Switch back to page 1. Confirm all box work survived. Then delete a box and press Ctrl+Z to confirm it recovers (D-12 safety).
**Expected:** All box edits (user box, deletions, detected boxes) persist across the page round-trip; Ctrl+Z after a silent delete restores the box.
**Why human:** Persistence round-trip on real multi-page navigation + Ctrl+Z recoverability of a deleted box are runtime behaviors requiring the live app.

### Gaps Summary

**No structural gaps.** All 8 must-have truths are verified in code, all 9 required artifacts are substantive and wired, all 6 key links are wired, TEXT-01 and TEXT-03 are satisfied by real implementations (not just marked complete), the CR-01 BLOCKER is resolved (commits 2dd7a9b test-first, ad7b19d fix; orchestrator deviation scrutiny corroborated), and the vendored security surface is clean. The 5 open warnings from code review are advisory and do not block the phase goal.

The phase is `passed` (canonicalized from `human_needed` on 2026-08-04). The deferred end-of-phase human checkpoints (plans 03-03/04/05) — real-artwork detection quality, green/amber legibility, live interleaved undo feel, and persistence round-trip on real navigation — were confirmed by user live UAT (03-UAT-REVERIFY.md 4/4 pass). A post-gap-closure fix for two live-only box-interaction bugs (brush cursor overlay swallowed the hit-test) is documented in .planning/debug/resolved/box-resize-move.md and regression-guarded.

---

_Verified: 2026-08-04T03:55:00Z (re-verified; initial 2026-07-29T16:45:00Z)_
_Verifier: Claude (gsd-verifier) + user live UAT_

---
phase: 08-masker-selective-inpaint
verified: 2026-08-19T00:45:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:

    - "User can run selective per-box inpainting that inpaints only the detected text masks inside boxes (SC-2) — the composite mask LaMa consumes is correct (CR-01/CR-03/CR-04 closed)"
    - "User can override the auto decision per box — force inpaint / skip inpainting it (SC-3) — the override's mask effect is correct post-move (CR-01 shared root cause closed)"
    - "Hand-painted strokes always survive re-detection (the D-01 layered-mask contract underpinning SC-2/SC-4) — CR-02 closed"
  gaps_remaining: []
  regressions: []
gaps: []
human_verification:

  - test: "Borders (inpaint state pens) legible on real artwork at working zooms (08-06 D2)"
    expected: "The 4-state border (will-inpaint solid / gate-skipped dashed / never / forced) is distinguishable from artwork and box handles at typical zoom levels"
    why_human: "Visual legibility of colored/dashed pens against arbitrary artwork cannot be asserted programmatically"

  - test: "Detection-settings dock renders correctly at the 1024x720 minimum window size (08-05 D5)"
    expected: "All detection controls (threshold row, Inpaint override combo, dilation slider) are reachable and unclipped at 1024x720"
    why_human: "Qt dock layout at a specific window size needs a real display session"

  - test: "Batch quality on a real chapter + re-dilate slider latency (08-09 verification note)"
    expected: "Batch Detect + Clean on a real multi-page chapter produces inpaint quality matching the interactive path; the dilation slider re-derives without perceptible lag"
    why_human: "Requires a real model run and subjective quality/latency judgment"

  - test: "Moved-box + override flow (08-10 verification §6): detect a page, move a box, commit 'Never' via the Inspector override"
    expected: "The box's mask content is removed from the composite at the box's CURRENT position (not the pre-move origin); committing 'Always' joins content at the current position; the border states follow"
    why_human: "End-to-end visual confirmation of the fixed post-move override recompose on a live session"
---

# Phase 8: Masker & Selective Inpaint — Re-Verification Report (after gap closure)

**Phase Goal:** User can grow auto-detected masks to cover letter edges the conservative CTD heatmap leaves unmasked, and selectively inpaint only the text masks inside boxes whose region is uniform enough (low std-deviation) — preserving complex artwork instead of inpainting whole boxes — with per-box visibility and override. This activates the deferred cleaning-track seams (01-UAT dilation + Phase 3 decision D-15).
**Verified:** 2026-08-19T00:45:00Z
**Status:** human_needed (all truths verified; 4 human-only UAT checks pending)
**Re-verification:** Yes — after gap closure (plan 08-10 + review fixes 47e2ea6/ef3d44d/566daa1)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can set a mask dilation radius (N px) that grows auto-detected text masks so letter edges get covered (SC-1) | ✓ VERIFIED | Unchanged since initial verification: `MaskerConfig.mask_dilation_radius: Pixels = 2` (panelcleaner/config.py:569) + INI export (:642) + guarded import (:672); dilate-then-intersect growth locked by `test_derive_dilation_grows_but_never_exits_the_box`; full suite green (879/879, re-run this verification). The mode-ON re-derive path now also carries the WR-03 zero-boxes + WR-02 no-fit guards (main_window.py:3141-3165). |
| 2 | User can run selective per-box inpainting — box-constrained, std-deviation-gated, preserving complex artwork (SC-2) | ✓ VERIFIED | **Re-verified after CR-01/CR-03/CR-04 closure.** All three recompose consumers compose from `canvas.boxes_snapshot()` (current geometry at call-time, never stale birth `pagebox.box`): `_on_std_dev_threshold_changed` (main_window.py:3079-3097), `_rederive_auto_layer` mode-ON (:3141-3167), `_recompose_boxes_auto_plane` (:3790-3804). Threshold slot carries the no-fit guard `if not any(pb.mask is not None for pb in current_boxes): return` (:3090-3091 — byte-mirror of the sibling). Mode-ON re-derive carries BOTH the WR-03 zero-boxes guard `if not boxes: return` (:3146-3147) and the WR-02 no-fit guard (:3164-3165). `_apply_geometry_op` invalidates `auto_mask` + `raw_detected_mask` on geometry ops (:1368-1369 — review-fix WR-02). **Behavioral probes (all PASS on the fixed code):** `test_recompose_after_move_uses_live_geometry` — content stays at moved rect (25,15,49,44), never jumps back to birth (5,5,29,34); `test_threshold_tweak_after_invalidation_does_not_wipe_auto_plane` — plane byte-unchanged after tweak; `test_rotate_then_dilate_nudge_keeps_auto_plane` — rotate 180° + dilation nudge retains plane content. |
| 3 | User can see per box whether it was selectively inpainted and override the auto decision (SC-3) | ✓ VERIFIED | **Re-verified after CR-01 closure.** Indicator half unchanged (24-test matrix + 13 inspector override tests pass in the 879-green suite). Override mask effect post-move: `_on_inspector_inpaint_committed` (:3747-3766) sets the override, emits `boxes_modified`, then calls `_recompose_boxes_auto_plane` which composes from `boxes_snapshot()` (:3790) — the same snapshot-as-geometry machinery the CR-01 probe behaviorally verified — so Never/Always land at the box's current position. Commit mechanics locked by `test_override_commit_never_removes_content_and_pushes_one_entry`, `test_override_commit_always_joins_gate_skipped_content`, `test_override_commit_multi_select_one_entry_and_undo_restores_composite`. End-to-end moved-box + override visual flow remains a human UAT check (below). |
| 4 | User can paint mask under text boxes — paint tools pass through box items (SC-4) | ✓ VERIFIED | Unchanged: `PAINT_TOOLS` frozenset (canvas.py:98) + Alt-gated box branch; 10 dispatch tests pass within the 879-green full suite. |
| 5 | D-15 seam (PageBox.mask/std_dev) populated by vendored masker machinery and round-trips .mas save/load (SC-5) | ✓ VERIFIED | Unchanged: derive_page_mask_state + compose_auto_binary intact (detection_boxes.py); project_io round-trip tests green in the 879-green suite. Batch worker now additionally refreshes the merged set's fits (`derive_page_mask_state(image_rgb, mask_refined, merged, ...)` — batch_runner.py:194-200). |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified — every behavior-dependent truth is exercised by a passing probe or test)

### Deferred Items

None. The two open ledger items (`deferred-items.md`) are not roadmap-deferred gaps:

- `test_run_ocr_selected_dispatches_worker_not_inline` flakiness — pre-existing test-timing sensitivity, full suite currently green (879/879 including it).
- "Deleting a detected box does not recompose" — logged open item, out of 08-10 scope, explicitly noted in 08-10-SUMMARY.md as unchanged; not claimed by any later phase's success criteria.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| manga_ai_studio/gui/canvas.py `consume_mask_display()` | clears manual + erase + auto planes signal-silently | ✓ VERIFIED | :686-714 — fills manual/erase transparent, `_auto_bin = None`, recomposes; NEVER emits `mask_modified` (CR-16 2-stack contract documented at :700-702); no-page fallback = display-only clear (:704-710) |
| manga_ai_studio/gui/canvas.py `set_auto_binary()` | replaces ONLY the auto plane | ✓ VERIFIED | :551-580 — strict (H,W) uint8 dims guard (:570-578), stores `.copy()`, signal-silent (no `mask_modified`) |
| manga_ai_studio/gui/canvas.py `boxes_snapshot()` | carries mask/std_dev/inpaint_override + current rects | ✓ VERIFIED | :2141-2196 — materializes `BoxItem.current_box()` int geometry at call-time + forwards D-15 seam fields (:2169-2194), mask `.copy()`-detached |
| manga_ai_studio/core/detection_boxes.py `merge_page_boxes_for_detect()` | headless D-03 merge | ✓ VERIFIED | :109-136 — keeps USER boxes as-is (identity preserved), replaces DETECTED, Qt-free (headless worker contract documented) |
| manga_ai_studio/core/batch_runner.py detect branch | merged derivation + `page.boxes = merged` | ✓ VERIFIED | :193 `merged = merge_page_boxes_for_detect(page.boxes, boxes)`; :194-200 derive over merged; :209 `page.boxes = merged` (never `page.boxes = boxes`) |
| manga_ai_studio/gui/main_window.py detection-batch refresh | auto-only restore | ✓ VERIFIED | `_refresh_current_page_after_batch("detect")` uses `set_auto_binary(auto_bin)` (:6488-6492), not `set_planes(empty, empty, ...)` |
| manga_ai_studio/gui/main_window.py consumption sites | both call consume_mask_display | ✓ VERIFIED | Inpaint finish :5050; batch-clean refresh :6512 |
| manga_ai_studio/gui/main_window.py batch dirty marking | result + cancel/abort paths | ✓ VERIFIED | `_on_batch_finished` :6282-6285 (detect/detect_and_clean + ok>0); `_on_batch_cleanup` :6351-6354 (cancel/abort — review-fix WR-01, conservative over-dirty) |
| manga_ai_studio/gui/main_window.py `_apply_geometry_op` | invalidates stale raw + derived auto | ✓ VERIFIED | :1357-1369 — geometry ops clear `auto_mask` + `raw_detected_mask` (:1368-1369, review-fix WR-02) |
| tests/test_gui_gap_closure.py | 8 GUI probes | ✓ VERIFIED | **8 passed** (re-run this verification): moved-box recompose, no-fit wipe guard, consume clears planes + no resurrection, detect-batch preserves manual/erase, clean refresh clears planes, detect-batch dirty, cancel-batch dirty, rotate→dilate plane retention |
| Headless merge suites | 2 new tests | ✓ VERIFIED | `test_merge_page_boxes_keeps_user_replaces_detected` (test_detection_boxes.py:344) + `test_batch_detect_preserves_user_boxes` (test_batch_runner.py:653) — **2 passed** (re-run) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `_on_std_dev_threshold_changed` | `compose_auto_binary` | `boxes_snapshot()` at :3079 + no-fit guard :3090 | ✓ WIRED | CR-03 probe-locked (plane byte-unchanged after invalidation + tweak) |
| `_rederive_auto_layer` (mode-ON) | `derive_page_mask_state` | `boxes_snapshot()` at :3141 → snapshot list → live write-back :3155-3157 | ✓ WIRED | WR-03 zero-boxes + WR-02 no-fit guards in place; rotate probe-locked |
| `_recompose_boxes_auto_plane` | `compose_auto_binary` | `boxes_snapshot()` at :3790 | ✓ WIRED | Override commit post-move lands at current rect (snapshot geometry) |
| detect-mode batch refresh | `set_auto_binary` | :6488-6492 | ✓ WIRED | CR-02 probe-locked — manual/erase survive, auto == batch result |
| inpaint finish / batch-clean refresh | `consume_mask_display` | :5050 / :6512 → canvas.py:686 | ✓ WIRED | CR-04 probe-locked — no resurrect on recompose |
| batch worker | derive over merged + persist | :193-209 | ✓ WIRED | WR-01 probe-locked — user box survives with override + refreshed fits |
| `_on_batch_finished` / `_on_batch_cleanup` | `ImageFile.dirty` | :6282-6285 / :6351-6354 | ✓ WIRED | WR-02 + cancel-path probe-locked (title `*` asserted) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `_on_std_dev_threshold_changed` | `current_boxes` | `canvas.boxes_snapshot()` — live rects from `BoxItem.current_box()` + stored fits | Yes — snapshot materializes current rects, not birth `.box` | ✓ FLOWING |
| `_recompose_boxes_auto_plane` | `current_boxes` | `canvas.boxes_snapshot()` | Yes — same snapshot source | ✓ FLOWING |
| `_rederive_auto_layer` | `raw` | `imf.raw_detected_mask` unpacked — **invalidated by geometry ops** (:1368-1369) so never stale/misaligned | Yes — raw dims guard :3127 + invalidation backstop | ✓ FLOWING |
| batch worker | `merged` | `merge_page_boxes_for_detect(page.boxes, boxes)` | Yes — USER boxes flow through with identity, DETECTED replaced | ✓ FLOWING |

### Behavioral Spot-Checks (probes re-run this verification)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| CR-01 moved-box recompose | `pytest tests/test_gui_gap_closure.py::test_recompose_after_move_uses_live_geometry` | content stays at moved rect (25,15,49,44) after threshold change | ✓ PASS |
| CR-03 no-wipe guard | `pytest ...::test_threshold_tweak_after_invalidation_does_not_wipe_auto_plane` | auto plane byte-unchanged after tweak | ✓ PASS |
| CR-04 consume + no-resurrect | `pytest ...::test_consume_mask_display_clears_planes_and_no_resurrection` | 3 planes cleared, no mask_modified, recompose stays content-free | ✓ PASS |
| CR-02 detect-batch stroke survival | `pytest ...::test_detect_batch_refresh_preserves_manual_and_erase` | manual/erase preserved, auto == batch binary | ✓ PASS |
| WR-01 cancel dirty | `pytest ...::test_detect_batch_cancel_marks_pages_dirty` | all pages dirty + title `*`; clean-mode cancel stays clean | ✓ PASS |
| WR-02 rotate→dilate retention | `pytest ...::test_rotate_then_dilate_nudge_keeps_auto_plane` | raw/auto invalidated post-rotate; re-derive keeps content | ✓ PASS |
| WR-01 headless merge | `pytest test_core/test_detection_boxes.py::test_merge_page_boxes_keeps_user_replaces_detected` | USER box identity + override preserved, stale DETECTED replaced | ✓ PASS |
| WR-01 batch preserve | `pytest test_core/test_batch_runner.py::test_batch_detect_preserves_user_boxes` | user box survives `page.boxes` with "always" override + fresh fits | ✓ PASS |
| Full regression | `pytest -q` (whole workspace suite) | **879 passed, 0 failed** (baseline 869 + 10 new: 8 GUI + 2 headless), 3 pre-existing HF warnings | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| tests/test_gui_gap_closure.py (8 probes) | `pytest tests/test_gui_gap_closure.py -q` | **8 passed** in 21.3s | PASS |
| Headless merge probes (2) | `pytest test_core/test_detection_boxes.py::... test_core/test_batch_runner.py::... -q` | **2 passed** in 2.5s | PASS |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|---------------------|----------|----------|
| MASK-01 | 08-01,02,03,05,07,09,10 | Dilation radius grows auto masks | ✓ SATISFIED | SC-1 verified (config.py:569/642/672; re-derive path guarded); dilate-then-intersect test green |
| MASK-02 | 08-01..05,07,09,10 | Selective per-box std-dev-gated inpaint (D-15 seam) | ✓ SATISFIED | SC-2 re-verified — CR-01/CR-03/CR-04 closed with passing probes; composite correct in reachable flows |
| MASK-03 | 08-01,04,06,08,10 | Per-box indicator + override | ✓ SATISFIED | SC-3 re-verified — indicator + override commit correct; snapshot-based recompose lands post-move |
| MASK-05 | 08-02,03,07,09,10 | Box-constrained inpainting | ✓ SATISFIED | dilate-then-intersect + out-of-box discard locked; batch worker derives over merged set via same seam core |
| MASK-06 | 08-02 | Paint under text boxes | ✓ SATISFIED | SC-4 verified (PAINT_TOOLS dispatch, 10 tests green in full suite) |

No orphaned requirements: all 5 phase IDs are claimed by plans 08-01..08-10. MASK-04 is explicitly out of scope (v2) per ROADMAP.md and REQUIREMENTS.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | No TBD/FIXME/XXX/PLACEHOLDER markers in any phase-modified file (re-grepped this verification); no stub/empty implementations; no console.log-only handlers |

The two open ledger items in `deferred-items.md` (intermittent OCR test flake — full suite currently green; delete-does-not-recompose — out of 08-10 scope) are documented, not new anti-patterns.

### Human Verification Required

Every automated check passes (5/5 truths, 879/879 suite). Four human-only UAT items from the verification context remain unexecuted — they cannot be automated (visual judgment, real model runs, live-session interaction):

1. **Border legibility at working zooms** — Test: view borders (inpaint state pens) on real artwork. Expected: 4 border states distinguishable from artwork at typical zoom. Why human: visual contrast against arbitrary artwork.
2. **Detection-settings dock at 1024x720** — Test: resize window to 1024x720. Expected: detection controls reachable/unclipped. Why human: Qt dock layout needs a real display session.
3. **Batch quality on a real chapter + re-dilate latency** — Test: run Batch Detect/Clean on a real chapter; drag the dilation slider. Expected: interactive-quality inpaint; no perceptible re-derive lag. Why human: real model run + subjective judgment.
4. **Moved-box + override UAT flow** — Test: detect a page, move a box, commit "Never" via Inspector override. Expected: content removed at the box's CURRENT position (not pre-move origin). Why human: end-to-end visual confirmation of the CR-01 fix on a live session.

### Gaps Summary

**No gaps remain.** All three previously-failed truths (SC-2 composite correctness, SC-3 override effect post-move, D-01 hand-strokes-survive-re-detection) are re-verified VERIFIED with code evidence at file:line and probe evidence from the 08-10 gap-closure suite (8 GUI probes + 2 headless merge tests, all re-run and passing this verification). The four Critical (CR-01..CR-04) and two Warning (WR-01, WR-02) defects plus the WR-03 bonus guard are closed; the two code-review warnings (cancel-path dirty marking, stale-raw invalidation) were fixed by review commits ef3d44d/566daa1 and are probe-locked. The full workspace suite re-run confirms 879 passed, 0 failed — no 08-01..08-09 behavior regressed.

Status is `human_needed` (not `passed`) purely because the four human-only UAT checks from the phase's own verification plan cannot be executed by this verifier — the codebase itself fully satisfies the phase goal.

---

_Verified: 2026-08-19T00:45:00Z_
_Verifier: the agent (gsd-verifier)_

---
phase: 08-masker-selective-inpaint
verified: 2026-08-18T11:05:00Z
status: gaps_found
score: 3/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "User can run selective per-box inpainting that inpaints only the detected text masks inside boxes (SC-2) — the composite mask LaMa consumes is correct"
    status: failed
    reason: >-
      CR-01 (reproduced by probe): after Detect + box move, any threshold/radius
      change or override commit recomposes the auto plane from LIVE PageBox objects
      whose .box is birth geometry (never re-materialized after move/resize — zero
      `pagebox.box =` assignment sites exist), so the stored mask is pasted at the
      pre-move origin and LaMa inpaints the wrong region. Probe: content at
      (25,15,49,44) after move, jumped back to (5,5,29,34) after one threshold
      change. Compounding: CR-03 (reproduced) — `_on_std_dev_threshold_changed`
      lacks the `any(pb.mask is not None)` guard its sibling
      `_recompose_boxes_auto_plane` has, so after a geometry op (which invalidates
      per-box masks per the deliberate 08-01 policy while the auto plane keeps the
      transformed content) a threshold tweak composes an empty binary and silently
      wipes the whole auto plane (probe: content bbox None after one tweak).
      CR-04 (code-confirmed): inpaint/batch-clean consumption clears only the
      display composite, not the three planes — the consumed overlay resurrects on
      the next stroke/undo/page switch and a re-run of Inpaint re-processes the
      cleaned region.
    artifacts:
      - path: manga_ai_studio/gui/main_window.py
        issue: "_on_std_dev_threshold_changed (:3064), _rederive_auto_layer (:3112), _recompose_boxes_auto_plane (:3730) read stale live pagebox.box; _refit_changed_boxes (:3418-3420) writes back mask/std_dev without the fitted box; threshold slot missing no-fit guard; consumption sites :4990-4993 / :6420-6423 clear display only"
    missing:
      - "Re-materialize live geometry at commit time (write fitted.box onto live pageboxes in _refit_changed_boxes + move/resize commit) or make every recompose consumer use canvas.boxes_snapshot() instead of live pageboxes"
      - "Add the `any(pb.mask is not None)` no-fit guard to _on_std_dev_threshold_changed (mirror _recompose_boxes_auto_plane :3733) and the zero-boxes guard to _rederive_auto_layer mode-ON (WR-03 sibling)"
      - "Clear all three planes signal-silently at mask-consumption sites (e.g. a consume_mask_display() canvas method) so the consumed overlay cannot resurrect"
  - truth: "User can override the auto decision per box — force inpaint / skip inpainting it (SC-3) — the override's mask effect is correct"
    status: failed
    reason: >-
      Same root cause CR-01: the override commit path calls
      _recompose_boxes_auto_plane, which composes from stale live pagebox.box.
      After a box move, committing Never leaves the box's content pasted at its
      pre-move origin (not removed from where it sits) and Always joins content at
      the wrong location. The indicator half (border states) and the Inspector
      combo/grouped-commit/one-Ctrl+Z all work and are test-locked; only the
      mask-effect half is corrupted post-move. CR-04 additionally makes the
      "was it inpainted" state unreliable across a consumption/resurrection cycle.
    artifacts:
      - path: manga_ai_studio/gui/main_window.py
        issue: "_recompose_boxes_auto_plane (:3730) and _on_inspector_inpaint_committed (:3691) recompose from live pageboxes with stale .box"
    missing:
      - "Fix shares gap 1's remedy — the override recompose must read current geometry (snapshot-based compose or refreshed pagebox.box)"
  - truth: "Hand-painted strokes always survive re-detection (the D-01 layered-mask contract underpinning SC-2/SC-4)"
    status: failed
    reason: >-
      CR-02 (code-confirmed): `_refresh_current_page_after_batch("detect")` restores
      the current page via `canvas.set_planes(empty_manual, empty_erase, auto_bin)`
      with EXPLICITLY empty manual/erase planes. The dispatch-time flush
      (`_flush_current_canvas_mask_to_data_model` :6133-6164) persists only the flat
      composite, so the current page's live stroke planes exist nowhere else —
      running Batch -> Detect from a page with hand-painted strokes wipes them (and
      the erase ledger) with no undo entry, and the next outgoing flush packs the
      now-empty planes back into the ImageFile slots. The interactive
      _on_detection_finished honors the contract (set_auto_binary replaces only the
      auto plane); the batch refresh violates it.
    artifacts:
      - path: manga_ai_studio/gui/main_window.py
        issue: "detect-mode batch refresh :6392-6401 passes explicitly-empty manual/erase planes to set_planes"
    missing:
      - "Replace only the AUTO plane in the detect-mode batch refresh (set_auto_binary from the unpacked imf.auto_mask), leaving live manual/erase planes untouched"
deferred: []
---

# Phase 8: Masker & Selective Inpaint — Verification Report

**Phase Goal:** User can grow auto-detected masks to cover letter edges the conservative CTD heatmap leaves unmasked, and selectively inpaint only the text masks inside boxes whose region is uniform enough (low std-deviation) — preserving complex artwork instead of inpainting whole boxes — with per-box visibility and override. This activates the deferred cleaning-track seams (01-UAT dilation + Phase 3 decision D-15).
**Verified:** 2026-08-18T11:05:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can set a mask dilation radius (N px) that grows auto-detected text masks so letter edges get covered (SC-1) | ✓ VERIFIED | `MaskerConfig.mask_dilation_radius: Pixels = 2` (panelcleaner/config.py:569) with INI export (:642) + guarded import (:672); startup `load_profile("default")` (__main__.py:36); ToolsPanel slider/spin with `dilation_changed` signal + live `_on_dilation_changed` -> `_rederive_auto_layer` (main_window.py:3032-3119); dilate-then-intersect growth locked by `test_derive_dilation_grows_but_never_exits_the_box`; mode-OFF full-heatmap path + batch radius threading (`test_batch_detect_dilation_radius_effect`). All pass. Caveat: after a box move the mode-ON re-derive shares gap 1's stale-geometry defect — see Gaps. |
| 2 | User can run selective per-box inpainting — box-constrained, std-deviation-gated, preserving complex artwork (SC-2) | ✗ FAILED | Machinery fully present and test-green at birth positions (`derive_page_mask_state` gate-lifted fits, `compose_auto_binary` gate matrix, D-02 out-of-box discard, 25+32 tests pass), BUT three critical defects break the behavior in reachable flows: CR-01 misplaced composite after box move (PROBE-REPRODUCED), CR-03 silent auto-plane wipe after geometry op + threshold tweak (PROBE-REPRODUCED), CR-04 consumed overlay resurrection (code-confirmed). The misplaced/lost composite is exactly what LaMa consumes. |
| 3 | User can see per box whether it was selectively inpainted and override the auto decision (SC-3) | ✗ FAILED | Indicator half VERIFIED: `PageBox.inpaint_state` single derivation (box_model.py:199-230), `BoxItem.set_inpaint_state` 4-state pen matrix (box_item.py:623), 24-test matrix passes; Inspector Auto/Always/Never combo + Mixed sentinel + one-Ctrl+Z grouped commit (tests/test_gui_inspector_override.py, 13 pass). Override half FAILED post-move: `_recompose_boxes_auto_plane` composes from stale `pagebox.box` — Never/Always apply mask content at the pre-move location. |
| 4 | User can paint mask under text boxes — paint tools pass through box items (SC-4) | ✓ VERIFIED | `PAINT_TOOLS` frozenset (canvas.py:98) + Alt-gated box branch (canvas.py:1270-1315): no-Alt paint press falls through bodies AND handles; Alt+click/drag selects/moves/creates; crop branch and double-click unchanged. 10 dispatch tests pass (test_gui_mask_planes.py). |
| 5 | D-15 seam (PageBox.mask/std_dev) populated by vendored masker machinery and round-trips .mas save/load (SC-5) | ✓ VERIFIED | `derive_page_mask_state` calls vendored `pick_best_mask` gate-lifted (attrs.evolve 1e9) + stores honest std (detection_boxes.py:254-323); `pagebox_to_json` emits std_dev/inpaint_override/base64-PNG mask (project_io.py:228-230) with hardened decode + size cross-check; four optional plane entries rawmask/automask/manualmask/erasemask.bin (:462-465, :655-658); save-loop `_page_plane_keys` (main_window.py:2147) + load-side `set_planes` restore (:2610-2661). Round-trip + legacy-compat tests pass. |

**Score:** 3/5 truths verified

### Probe Execution (behavioral spot-checks)

| Check | Command | Result | Status |
|-------|---------|--------|--------|
| CR-01 reproduction (move + threshold change) | temp pytest probe driving `_on_detection_finished` -> setRect move -> `boxes_modified.emit` -> `_on_std_dev_threshold_changed(50.0)` | content bbox (25,15,49,44) after move, **(5,5,29,34)** after threshold — jumped back to pre-move origin | ✗ FAIL (defect confirmed) |
| CR-03 reproduction (invalidated masks + threshold change) | temp pytest probe: detect, set pb.mask=None (08-01 geometry-op policy), verify auto plane has content, then `_on_std_dev_threshold_changed(15.5)` | content present before tweak, **None** after — whole auto plane wiped | ✗ FAIL (defect confirmed) |
| Seam-core suite | pytest tests/test_core/test_detection_boxes.py test_masker_machinery.py test_masker_config_roundtrip.py | 25 passed | ✓ PASS |
| Canvas planes + inspector override | pytest tests/test_gui_mask_planes.py tests/test_gui_inspector_override.py | 41 passed | ✓ PASS |
| Detection seam GUI suite | pytest tests/test_gui_detection_boxes.py | 32 passed | ✓ PASS |

Probe file was deleted after the run; the two reproduction outputs above are the recorded evidence. The full suite (869 passed per orchestrator) is consistent with these results — the existing tests never combine a move with a subsequent threshold/override change, which is why the suite stays green while the defect is reachable.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| manga_ai_studio/core/box_model.py | inpaint_override + inpaint_state + copy() mask detach | ✓ VERIFIED | :115 field, :199-230 method (4-value matrix), :255 mask detach |
| panelcleaner/config.py | mask_dilation_radius field + INI lines | ✓ VERIFIED | :569, :642, :672 |
| manga_ai_studio/core/image_ops.py | 6 rebuild sites carry override+style, invalidate mask/std_dev | ✓ VERIFIED | 6/6 sites confirmed by grep (:156-:477) |
| manga_ai_studio/core/mask_planes.py | pack/unpack + MaskPlanesSnapshot | ✓ VERIFIED | module exists, length-validated unpack |
| manga_ai_studio/gui/canvas.py | three-plane model + PAINT_TOOLS dispatch | ✓ VERIFIED | :373-375 planes, :582 recompose, :1291-1315 dispatch |
| manga_ai_studio/core/detection_boxes.py | seam primitives, headless | ✓ VERIFIED | all 5 symbols, dither=NONE, no Qt imports |
| manga_ai_studio/core/project_io.py | std_dev/inpaint_override/mask keys + 4 plane entries | ✓ VERIFIED | :228-230, :462-465, :655-658 |
| manga_ai_studio/gui/tools_panel.py | Detection settings section + 4 signals | ✓ VERIFIED | :135-138 signals, :285+ section, QScrollArea wrap |
| manga_ai_studio/gui/box_item.py | set_inpaint_state + state pens | ✓ VERIFIED | :623, greys #e8e8ea/#9a9aa2, dash [6,4] |
| manga_ai_studio/gui/main_window.py | seam, refresh, live slots, save/load, batch wiring | ⚠️ PRESENT WITH CRITICAL DEFECTS | all symbols exist (:3032-:3119, :3355, :3691, :3712, :4453, :4741, :2147, :6289) but 4 Critical findings (see Gaps) |
| manga_ai_studio/core/batch_runner.py | constrained detect path + masker_conf | ✓ VERIFIED | :187-208 |
| manga_ai_studio/gui/inspector_panel.py | Inpaint combo + Std dev row + signal | ✓ VERIFIED | :311, :365-379 |
| 7 new test files | exist and pass | ✓ VERIFIED | 98 phase tests pass in spot-checks |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| _on_detection_finished | derive_page_mask_state | direct call | ✓ WIRED | main_window.py:4520 |
| tools_panel.dilation_changed | _on_dilation_changed -> _rederive_auto_layer | signal connect | ✓ WIRED (with gap-1 caveat) | :3032-3045 |
| refresh_box_inpaint_states | PageBox.inpaint_state -> BoxItem.set_inpaint_state | single derivation | ✓ WIRED | :4757-4758 |
| Inspector commit | compose_auto_binary -> set_auto_binary | _recompose_boxes_auto_plane | ⚠️ WIRED BUT CORRUPT POST-MOVE | stale pagebox.box (gap 1) |
| save-loop | _page_plane_keys -> build_page_entries | dict keys | ✓ WIRED | :2147-2174 |
| batch loop | build_detected_pageboxes + derive_page_mask_state | same 08-03 core | ✓ WIRED | batch_runner.py:187-188 |
| _end_paint | recompose_mask -> mask_modified.emit | ordering | ✓ WIRED | canvas.py:1608-1610 |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|---------------------|----------|
| MASK-01 | 08-01,02,03,05,07,09 | Dilation radius grows auto masks | ✓ SATISFIED | SC-1 verified |
| MASK-02 | 08-01..05,07,09 | Selective per-box std-dev-gated inpaint (D-15 seam) | ✗ GAPS | SC-2 failed — CR-01/03/04 (interactive correctness in reachable flows) |
| MASK-03 | 08-01,04,06,08 | Per-box indicator + override | ✗ GAPS | SC-3 override effect corrupt post-move (CR-01); indicator verified |
| MASK-05 | 08-02,03,07,09 | Box-constrained inpainting | ✓ SATISFIED | dilate-then-intersect + out-of-box discard locked by tests; batch adopts the same core |
| MASK-06 | 08-02 | Paint under text boxes | ✓ SATISFIED | SC-4 verified |

No orphaned requirements: all 5 phase IDs are claimed by plans. MASK-04 is explicitly out of scope (v2) per ROADMAP and REQUIREMENTS.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| main_window.py | 3064-3072 | Missing no-fit guard (inconsistent with sibling :3733) — silent data wipe | 🛑 Blocker | CR-03 |
| main_window.py | 6392-6401 | Explicitly-empty planes wipe user strokes on batch-detect refresh | 🛑 Blocker | CR-02 |
| main_window.py | 4990-4993, 6420-6423 | Consumption clears display only; planes resurrect consumed overlay | 🛑 Blocker | CR-04 |
| main_window.py | 3064/3112/3730/3418 | Live pagebox reads where snapshot required (stale birth geometry) | 🛑 Blocker | CR-01 |
| batch_runner.py | 202 | `page.boxes = boxes` overwrites persisted USER boxes (no D-03 merge in worker) | ⚠️ Warning | WR-01 — user data loss on batch detect (non-current pages) |
| main_window.py | (batch cleanup) | Detect-mode batch never marks pages dirty — close loses detected boxes silently | ⚠️ Warning | WR-02 |
| main_window.py | 3111-3117 | _rederive_auto_layer mode-ON lacks zero-boxes guard (inconsistent with threshold slot) | ⚠️ Warning | WR-03 — radius nudge can wipe a mode-OFF layer after mode switch |
| tools_panel.py | 586-627 | set_masker_values clamps out-of-range profile values silently (UI/profile desync) | ⚠️ Warning | WR-04 |
| (deferred-items.md) | — | Deleting a detected box does not recompose (auto content lingers until next §37 trigger) | ⚠️ Warning | Logged open in the phase ledger (commit adbd44e); same recompose-trigger family as gap 1 |

No TBD/FIXME/XXX debt markers in any phase-modified file. All 40 phase commits verified in git log (test feat docs triplets for 08-01..08-09).

### Gaps Summary

The phase built everything it planned — every symbol, artifact, and wiring in all 9 plans exists, and the 869-test suite is green. The headless core (detection_boxes.py, mask_planes.py, project_io.py) is well-guarded and test-locked. But the goal-backward check fails: **the composite mask that LaMa consumes is incorrect in reachable user flows**, so "user can selectively inpaint only the detected text masks inside boxes" does not reliably hold.

Four Critical defects (all confirmed against the actual code; CR-01 and CR-03 additionally reproduced by throwaway probe):

1. **CR-01 — stale geometry (root cause of both SC-2 and SC-3 failures).** The canvas never re-materializes `item.pagebox.box` after a move/resize (only `setRect`; geometry materialization lives solely inside `boxes_snapshot()`). Three live recompose consumers (`_on_std_dev_threshold_changed`, `_rederive_auto_layer`, `_recompose_boxes_auto_plane`) and the write-back in `_refit_changed_boxes` read the stale live pageboxes, so after Detect -> move a box, the next threshold/radius change or Inpaint override commit pastes the box's mask at its pre-move origin. The misplaced composite is what Inpaint (C) feeds LaMa — wrong-region inpainting. Probe evidence: content bbox moved from (25,15,49,44) back to (5,5,29,34) on a single threshold change.
2. **CR-03 — silent auto-plane wipe.** The threshold slot lacks the `any(pb.mask is not None)` guard its sibling has; after a geometry op (which deliberately invalidates per-box masks), any threshold tweak composes an empty binary and destroys the transformed auto plane — non-undoable (the slot pushes no history). Probe evidence: content bbox None after one tweak.
3. **CR-04 — consumed overlay resurrection.** Post-inpaint/batch-clean consumption clears only the display composite, not the three planes; the next stroke/undo/page-switch recompose rebuilds the consumed overlay, and a re-run of Inpaint re-processes the already-cleaned region — the exact regression the pre-Phase-8 CR-16 fix existed to prevent.
4. **CR-02 — batch detect wipes hand strokes on the current page.** The detect-mode batch restore passes explicitly-empty manual/erase planes while the dispatch flush persisted only the flat composite, so strokes (and the erase ledger) are destroyed with no undo — violating the D-01 "hand strokes always survive re-detection" contract the interactive path honors.

The four fixes are localized (one guard, one set_planes→set_auto_binary swap, one plane-clearing helper, one geometry re-materialization) and none invalidate the phase's architecture.

**Post-fix UAT items (human checks once gaps close):** border-state legibility on real artwork at working zooms (08-06 D2), Detection-settings dock rendering at 1024x720 (08-05 D5), batch output quality on a real chapter + re-dilate slider latency (08-09 verification note), and the moved-box + override flow from this report (move a box, commit Never, confirm the content is removed at the box's current position).

---

_Verified: 2026-08-18T11:05:00Z_
_Verifier: Claude (gsd-verifier)_

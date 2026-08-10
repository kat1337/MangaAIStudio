---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
verified: 2026-08-10T02:00:00Z
status: gaps_found
score: 24/28 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Show Original re-baselines to the post-curves image after Apply (D-14) and is never re-baselined by live previews mid-dialog"
    status: failed
    reason: "CR-01 (phase code review, 06-REVIEW.md, status issues_found): the Cancel path restores via the capture-ENABLED set_image_from_numpy(base.copy()) (main_window.py:1274). On a fresh page _original_image_numpy is None, so the capture at canvas.py:742-743 stores the LAST PREVIEW FRAME (curve-distorted) as the 'original'; canvas.py:769 sets _inpainted_qimage unconditionally, so has_inpaint_result() turns True with no inpaint ever run. Probe-verified: after open+preview+Cancel on a fresh page, _original_image_numpy == the curved preview frame (not None, not the pre-dialog image) and has_inpaint_result() == True. The phase's own regression test masks this: test_curves_preview_no_baseline_poison calls canvas.rebaseline_original() before opening the dialog (IN-01)."
    artifacts:
      - path: "manga_ai_studio/gui/main_window.py"
        issue: "line 1274 Cancel restore uses set_image_from_numpy (capture-enabled) instead of the capture-suppressed preview path + rebaseline_original()"
      - path: "manga_ai_studio/gui/canvas.py"
        issue: "line 769 _inpainted_qimage = qimg is set unconditionally — the preview path claims an inpaint result"
      - path: "tests/test_gui_curves_dialog.py"
        issue: "test_curves_preview_no_baseline_poison pre-baselines (line 726) so the fresh-page _original_image_numpy is None scenario is never exercised"
    missing:
      - "Cancel restore via set_image_from_numpy_preview(base.copy(), capture_original=False) + canvas.rebaseline_original()"
      - "Gate _inpainted_qimage on capture_original in _set_image_from_numpy"
      - "Regression test variant without the pre-baseline asserting _original_image_numpy stays None and has_inpaint_result() stays False after Cancel"
  - truth: "Exactly one checkable window tool action is checked at all times (exclusive QActionGroup); the toolbar buttons mirror their default action's checked state on every entry path"
    status: failed
    reason: "WR-02 (phase code review): the six WINDOW tool actions were added to the ToolsPanel's exclusive QActionGroup which already holds the panel's six actions — 12 mirrored actions in one exclusive group. The mirror contract breaks on the most common entry path, a dock-button click: probe-verified with the real MainWindow — after clicking the dock's Rectangle button, the panel's own action ends up UNCHECKED (dock button loses its highlight), the window action + toolbar button checked, and tools_panel.active_tool() falls back to ToolMode.MOVE. The enumerated tested paths (shortcut/menu/programmatic set_active_tool) pass; the dock-click path desyncs."
    artifacts:
      - path: "manga_ai_studio/gui/main_window.py"
        issue: "lines 715-769: window tool actions joined tools_panel.tool_group (the panel's own exclusive group) — dual mirror actions fight the group's exclusivity on dock clicks"
      - path: "tests/test_gui_crop_tool.py"
        issue: "test_toolbar_buttons_track_active_tool covers programmatic/shortcut/menu paths only — never a dock-button click"
    missing:
      - "WR-02 fix: keep the window actions checkable but OUTSIDE the panel's exclusive group (explicit sync via set_active_tool + toolbar loop), or share ONE action set between dock and toolbar"
      - "Dock-click regression test asserting panel action checked + active_tool() == clicked tool + toolbar mirror"
  - truth: "The undo/redo flash op-name set is ('rotate', 'crop', 'curves', 'resize') — 'levels' replaced, not appended"
    status: failed
    reason: "WR-01 (phase code review): the _undo_op_label set literal is exactly ('rotate','crop','curves','resize') and contains no 'levels', but _undo_op_label_for_result (main_window.py:2927-2941) only consults the recorded op name when the pop result has >1 element. A curves apply pushes an image-ONLY geometry record (mask/boxes None), so the pop is a single-element list and resolves via _undo_op_label('image') -> 'inpaint'. Probe-verified: Ctrl+Z after a curves apply flashes 'Undo: inpaint' instead of 'Undo: curves' — the UI-SPEC surface 28 copy contract this phase extended with 'curves' is not honored at runtime; the existing lifecycle tests assert the restored image but never the flash text."
    artifacts:
      - path: "manga_ai_studio/gui/main_window.py"
        issue: "_undo_op_label_for_result single-entry branch never uses _last_geometry_op_name"
      - path: "tests/test_gui_curves_dialog.py"
        issue: "test_curves_apply_pushes_one_entry asserts the image/stack but not the undo flash text"
    missing:
      - "WR-01 fix: prefer _last_geometry_op_name for a full-frame (0,0) single image entry"
      - "Flash-text assertion in the curves lifecycle test ('Undo: curves' / 'Redo: curves')"
human_verification:
  - test: "Open the Curves dialog (Tools > Curves...), drag a point and release; then check drag fluidity and grid/handle legibility at 150% and 200% Windows DPI scaling"
    expected: "Curve drags track the cursor smoothly (no lag/stutter), the 64/16 gridlines, diagonal, 2px accent curve, and 8x8/10x10 handles remain legible and correctly scaled at both DPI settings"
    why_human: "Visual/kinesthetic contract — UI-SPEC surface 30 backstop (06-03 backstop '14px dialog fields stay 14px-rendered at 150%/200% DPI' and 06-04 backstop 'curve drags are fluid and the grid/handles remain legible at all supported DPI settings' are verification: backstop = non-inferable from code; the phase explicitly held both for the end-of-phase UAT gate"
behavior_unverified_items: []
deferred: []
---

# Phase 6: Refinement & Polish — Verification Report

**Phase Goal:** User gets a polished, consistent editor — deferred v1.1 bugs fixed (empty-state overlay on project open, toolbar active-tool highlight, stale Ctrl+O hint copy, dialog typography) and a full draggable curve editor replacing the Levels dialog's fixed black/white/gamma controls.
**Verified:** 2026-08-10T02:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

The full curve editor is landed end-to-end: headless LUT math (`curve_lut`/`curves_page`), the `CurveWidget` + `CurvesDialog` surface, and the MainWindow wiring (`Curves…` action, preview→apply→undo lifecycle) with `levels_dialog.py` deleted. All four deferred fixes are in with RED-GREEN regression tests. Full suite: **597 passed, 0 failed** (matches the claimed re-baseline exactly). However, the phase's own code review (06-REVIEW.md, `issues_found`) found one Critical and two Warning defects, **none of which were fixed** (the review report `9ea21f1` is the last commit). All three are probe-verified live in this verification — two violate phase must-have truths (CR-01, WR-02) and one violates the phase's extended undo-flash copy contract (WR-01).

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | curve_lut returns a 256-entry uint8 LUT; Linear (no interior points) is byte-identical to np.arange(256) | ✓ VERIFIED | image_ops.py:478-505; test_curve_lut_linear_is_identity passed |
| 2 | Degenerate point set (dup x, out-of-range y) never produces NaN/out-of-range/inverted map (T-05-07 backstop: sort, dedupe last-wins, clip, np.interp, round, astype) | ✓ VERIFIED | test_curve_lut_degenerate_backstop passed (np.isfinite + [0,255] + uint8 asserts) |
| 3 | curve_lut is pure; double application is deterministic curve-of-curve composition (idempotency probe) | ✓ VERIFIED | test_curve_lut_and_page_idempotent passed |
| 4 | curves_page validates (H,W,3) uint8, applies master then per-channel AFTER master (A1: out_c = ch_lut[master_lut[v]]), returns detached .copy() | ✓ VERIFIED | image_ops.py:508-533; test_curves_page_channel_after_master_order / validation_and_detach passed |
| 5 | After ANY image display path the empty-state trio (z=2000) is hidden — never persists over a loaded page | ✓ VERIFIED | canvas.py:777 `_update_empty_state()` in `_set_image_from_numpy` (shared impl); test_project_open_hides_empty_state_trio + test_numpy_display_hides_empty_state + test_preview_path_keeps_empty_state_hidden passed |
| 6 | Empty-box hint (z=850) visible on zero-box pages; hidden with boxes | ✓ VERIFIED | `_update_empty_state` → `_refresh_empty_box_hint`; test_project_open_hides_empty_state_trio asserts empty_box_hint.isVisible() |
| 7 | First-run hint copy is 'File → Open Folder… (Ctrl+Shift+O) · or drag files here'; stale Ctrl+O advertisement gone | ✓ VERIFIED | canvas.py:283 exact string; `rg "Ctrl\+O" canvas.py` = no match (gate passes); test_empty_hint_copy_references_open_folder passed |
| 8 | Empty-state body text 'Open a single image or a folder of images to begin cleaning.' stays verbatim | ✓ VERIFIED | canvas.py body untouched; test_empty_state_heading passes |
| 9 | Exactly one checkable window tool action is checked at all times; toolbar mirrors on every entry path (shortcut/menu/programmatic) | ✗ FAILED | WR-02: dock-button click desyncs — probe-verified: after dock Rectangle click, panel action UNCHECKED (dock loses highlight), window action + toolbar checked, `active_tool()` falls back to MOVE; the 12-action exclusive group (6 window + 6 panel) fights itself. Enumerated paths pass (test_toolbar_buttons_track_active_tool) |
| 10 | Toolbar and Tools dock always show the same active tool | ✗ FAILED | Same WR-02 root cause; probe: dock shows no highlight while toolbar shows Rectangle — dock/toolbar disagree after a dock click |
| 11 | The false group-membership comment at _make_tool_toolbar_button is corrected | ✓ VERIFIED | main_window.py:3123-3132 docstring now states the checkable-action-in-group mechanism truthfully |
| 12 | Dialog field values/labels at 14px Body on Resize, Crop, LoadTranslations; Curves ships 14px from birth | ✓ VERIFIED | setPixelSize(14) in all four dialogs (resize:102, load_translations:104, crop:78, curves_dialog:473); QFontInfo pixelSize==14 tests pass; Consolas 10 paste_edit exception preserved (:127) |
| 13 | Curves dialog opens at defaults: Linear (0 interior), endpoints (0,0)/(255,255), gamma 1.00, RGB, In/Out at selected point | ✓ VERIFIED | curves_dialog.py:460-469; test_dialog_defaults passed |
| 14 | Every curve/slider/gamma/channel/preset change fires ONE preview_callback with the composed LUT result | ✓ VERIFIED | single call site curves_dialog.py:821 in `_preview`; test_preview_fires_on_control_changes + test_refresh_is_single_preview_driver passed |
| 15 | No control state can diverge from the curve: black↔left/white↔right bidirectional sync with cross-clamp, gamma↔midpoint sync, _updating-guarded | ✓ VERIFIED | test_black_slider_moves_left_endpoint_with_clamp, test_curve_endpoint_cross_clamp_no_inversion, test_gamma_100_matches_midpoint_and_backmaps, test_gamma_change_injects_midpoint_point passed |
| 16 | Channel state independent: RGB/R/G/B edit separate point sets; preview composes master then per-channel (A1) | ✓ VERIFIED | test_channel_switcher_preserves_per_channel_edits, test_preview_byte_exact_vs_curves_page passed |
| 17 | No interaction can produce an out-of-range point: clamps to [0,255]², x-order preserved, endpoints x-fixed, In range [prev+1, next−1] | ✓ VERIFIED | test_drag_moves_point_with_clamps, test_in_spin_range_respects_neighbors, test_curve_endpoint_cross_clamp_no_inversion passed |
| 18 | Widget handles 0 and N interior points uniformly; endpoints never deletable; exactly one point selected at a time (Tab cycles) | ✓ VERIFIED | test_double_click_deletes_interior_but_never_endpoints, test_tab_cycles_selection passed |
| 19 | Keyboard story (D-07): arrows nudge ±1 (Shift ±10), Tab/Shift+Tab cycle, In/Out spins drive the selected point | ✓ VERIFIED | test_arrow_keys_nudge_selected_point, test_tab_cycles_selection passed |
| 20 | Histogram (D-08) computed ONCE at open from the detached page_image; never recomputed during editing | ✓ VERIFIED | curves_dialog.py:443-457 (once, from .copy()); test_histogram_computed_once_at_open (array identity locked) passed |
| 21 | Tools ▸ Image shows 'Curves…'; the Levels dialog-opening action is gone (D-01 rename) | ✓ VERIFIED | main_window.py:809 action_curves "Curves…" + surface-30 tooltip; test_curves_action_in_tools_menu passed; `not hasattr(window, 'action_levels')`; no stale refs anywhere in manga_ai_studio/ or tests/ |
| 22 | Apply commits ONE image-only undo entry via _apply_geometry_op('curves', geometry=False, ...) with flash 'Curves applied.'; geometry_altered NOT set; masks/boxes untouched | ✓ VERIFIED | main_window.py:1289-1291; test_curves_apply_pushes_one_entry: byte-exact curves_page output, len(_image_undo)==1, _mask_undo/_boxes_undo==0, geometry_altered False, flash asserted |
| 23 | Cancel restores the pre-dialog image byte-identical with zero undo entries | ✓ VERIFIED | test_curves_cancel_restores_exactly: np.array_equal, not can_undo(), no flash |
| 24 | b376f8a restore-before-Apply ordering preserved: detached base re-displayed BEFORE _apply_geometry_op, so Ctrl+Z restores the true pre-dialog image byte-identical and leaves the stack empty | ✓ VERIFIED | main_window.py:1284 set_image_from_numpy(base.copy()) precedes _apply_geometry_op; test_curves_apply_pushes_one_entry asserts on_undo() → pre-dialog byte-identical + empty stack |
| 25 | Show Original re-baselines to the post-curves image after Apply (D-14) and is never re-baselined by live previews mid-dialog | ✗ FAILED | CR-01: post-Apply re-baseline works (asserted), but the fresh-page Cancel path poisons the baseline — probe-verified: `_original_image_numpy` ends as the LAST PREVIEW FRAME (not None, not the pre-dialog image) and `has_inpaint_result()` == True with no inpaint run. After Apply the re-baseline works (asserted) |
| 26 | The undo/redo flash op-name set is ('rotate', 'crop', 'curves', 'resize') — 'levels' replaced, not appended | ✗ FAILED | The tuple literal is exactly right (main_window.py:2905), but WR-01: the runtime resolution mislabels a curves undo — probe-verified Ctrl+Z after a curves apply flashes 'Undo: inpaint' (single-entry pop never consults _last_geometry_op_name) |
| 27 | Curve ops run on the GUI thread: the _op_running gate blocks re-entry during apply | ✓ VERIFIED | main_window.py:1256 gate kept verbatim from the Levels slot |
| 28 | gui/levels_dialog.py deleted after migration; levels_lut/levels_page and their tests stay (the endpoint-math model) | ✓ VERIFIED | levels_dialog.py absent (Test-Path False); levels_lut/levels_page at image_ops.py:431-470 untouched; levels tests pass in the 17-test module run |

**Score:** 24/28 truths verified (4 failed — all three probe-verified against the phase's own review findings)

### Deferred Items

None — no failed truth is addressed by a later milestone phase (Phase 7 is the typesetting toolbar, unrelated).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | --------- | ------ | ------- |
| `manga_ai_studio/core/image_ops.py` | curve_lut + curves_page | ✓ VERIFIED | :478-533, backstop + A1 order, levels math untouched |
| `manga_ai_studio/gui/curves_dialog.py` | CurveWidget + CurvesDialog | ✓ VERIFIED | NEW, 829 lines; signals, paint/mouse/keyboard, presets, channels, histogram, single preview driver, 14px |
| `manga_ai_studio/gui/canvas.py` | D-09 call + D-11 copy | ✓ VERIFIED | _update_empty_state() at :777; hint at :283 |
| `manga_ai_studio/gui/main_window.py` | action_curves/_on_curves, checkable tool actions, gating list | ✓ VERIFIED (with WR-01/WR-02 defects) | :809-815, :1244-1291, :1103-1110, :715-769 |
| `manga_ai_studio/gui/crop_dialog.py` / `resize_dialog.py` / `load_translations_dialog.py` | 14px base font | ✓ VERIFIED | setPixelSize(14) in each __init__ |
| `manga_ai_studio/gui/levels_dialog.py` | DELETED | ✓ VERIFIED | file absent; zero stale references in manga_ai_studio/ + tests/ |
| `tests/test_core/test_image_ops.py` | 9 curve tests | ✓ VERIFIED | all pass (module: 17 passed) |
| `tests/test_gui_curves_dialog.py` | widget + dialog + lifecycle tests | ✓ VERIFIED | 32 tests incl. migrated lifecycle; single preview driver asserted via inspect |
| `tests/test_gui_canvas.py` / `test_gui_project.py` | D-09/D-11 regressions | ✓ VERIFIED | 3 + 1 tests, all pass |
| `tests/test_gui_crop_tool.py` / `test_gui_image_dialogs.py` / `test_gui_boxes.py` | D-10 RED gate + typography tests | ✓ VERIFIED (dock path uncovered) | test_toolbar_buttons_track_active_tool passes for 3 paths; dock-click path uncovered (WR-02) |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| _on_curves (main_window.py:1244) | _apply_geometry_op('curves', geometry=False) | :1284 restore-before-Apply → :1289 call | ✓ WIRED | b376f8a ordering in place; one entry, no geometry flag |
| CurvesDialog.result_values | image_ops.curves_page | _transform closure :1286-1287 | ✓ WIRED | (master, channels) unpacked once after Accepted |
| curves_dialog preview driver | canvas.set_image_from_numpy_preview(capture_original=False) | :1267-1269 lambda | ✓ WIRED | capture-suppressed; CR-01 defect is the CANCEL restore path, not this link |
| CurveWidget points_changed/point_selected | dialog._refresh → _preview | :588-589 connects | ✓ WIRED | single preview_callback call site (:821) |
| set_active_tool (window) | toolbar btn.setChecked(True) | :3153-3158 | ⚠️ PARTIAL | works for shortcut/menu/programmatic; dock-click path desyncs (WR-02) |
| _update_empty_state | _refresh_empty_box_hint | canvas.py:777 → 1568 | ✓ WIRED | trio + box hint consistent on all display paths |
| action_curves | Tools ▸ Image menu | :841 addAction + gating :1107 | ✓ WIRED | test_curves_action_in_tools_menu passes |
| main_window | curves_dialog (lazy import) | :1258 | ✓ WIRED | LevelsDialog import gone everywhere |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| curves_page preview payload | composed = curves_page(page_image, master, channels) | image_ops.curves_page on the detached base | Yes — byte-exact vs test-computed curves_page (test_preview_byte_exact_vs_curves_page) | ✓ FLOWING |
| CurveWidget._histogram | np.histogram(luminance/plane, 256, (0,256)) | computed ONCE in __init__ from page_image.copy() | Yes — real pixel histogram; identity locked | ✓ FLOWING |
| result_values | (master_points, channel_points) | collector state at Apply; detached copies | Yes — drives the applied curves_page transform | ✓ FLOWING |
| Undo before-state | pre-dialog base | base.copy() captured at :1260-1263, re-displayed at :1284 | Yes — Ctrl+Z restores true pre-dialog image (asserted) | ✓ FLOWING |
| Show Original baseline | _original_image_numpy | capture at canvas.py:742-743 | ✗ POISONED on fresh-page Cancel — stores the last preview frame (CR-01 probe) | ✗ HOLLOW_PROP path |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full workspace suite | `python -m pytest -q` | 597 passed, 0 failed (58.7s) | ✓ PASS — matches claimed re-baseline |
| Headless curve math | `python -m pytest tests/test_core/test_image_ops.py -q` | 17 passed (8 baseline + 9 new) | ✓ PASS |
| CR-01: fresh-page open→preview→Cancel | probe test (temp file, then removed) | `_original_image_numpy` = last preview frame (not None, ≠ pre-dialog), `has_inpaint_result()` = True | ✗ FAIL — defect confirmed live |
| WR-01: Ctrl+Z flash after curves apply | probe test (temp file, then removed) | status flash = `'Undo: inpaint'` | ✗ FAIL — mislabeled |
| WR-02: dock Rectangle-button click | probe test (temp file, then removed) | panel action unchecked, toolbar checked, `active_tool()` = MOVE | ✗ FAIL — highlight desync |

### Probe Execution

No probe scripts declared in the phase plans (the 06-01 "idempotency probe" is a unit test, executed above). The CR-01/WR-01/WR-02 probes above were run by the verifier in its own process (temp test files, removed after execution; working tree left clean).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PROJ-04 | 06-01, 06-04, 06-05 | User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize (curves half) | ✓ SATISFIED (with polish defects in gaps) | curve_lut/curves_page + CurveWidget/CurvesDialog + _on_curves end-to-end; apply/undo/cancel verified by migrated lifecycle tests; defects CR-01/WR-01/WR-02 tracked in gaps |
| D-09 (deferral, no REQ-ID) | 06-02 | Empty-state overlay cleared on the numpy display path | ✓ SATISFIED | canvas.py:777 + 3 regression tests |
| D-11 (deferral, no REQ-ID) | 06-02 | Hint copy references Open Folder (Ctrl+Shift+O) | ✓ SATISFIED | canvas.py:283 exact + grep gate clean |
| D-10 (deferral, no REQ-ID) | 06-03 | Toolbar active-tool highlight | ✗ PARTIAL | checkable actions + group membership done; dock-click entry path desyncs (WR-02) |
| D-12 (deferral, no REQ-ID) | 06-03 | Dialog typography 14px Body | ✓ SATISFIED | all four dialogs 14px + tests; Consolas exception kept |

No orphaned requirements: the ROADMAP notes the deferrals have no REQ-IDs and all four are claimed by plans 06-02/06-03. PROJ-04 is claimed by the three curves plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| manga_ai_studio/gui/main_window.py | 1274 | CR-01: Cancel restore uses the capture-enabled path (baseline poisoning on fresh pages) | 🛑 Critical (from 06-REVIEW.md; probe-confirmed) | Show Original shows the curve-distorted frame as "original" on fresh pages after open→cancel; Preview-hold enabled with no inpaint |
| manga_ai_studio/gui/main_window.py | 715-769 | WR-02: 12 mirrored actions in ONE exclusive QActionGroup | ⚠️ Warning (probe-confirmed) | Dock-button clicks desync dock/toolbar highlights; active_tool() reports the wrong tool |
| manga_ai_studio/gui/main_window.py | 2927-2941 | WR-01: single-entry pop never consults _last_geometry_op_name | ⚠️ Warning (probe-confirmed) | Ctrl+Z after Curves flashes "Undo: inpaint" — copy-contract violation |
| tests/test_gui_curves_dialog.py | 726 | IN-01: test pre-baselines, masking the CR-01 fresh-page path | ℹ️ Info | The regression suite passes while the defect is live |
| manga_ai_studio/gui/curves_dialog.py | 297-301 | IN-02: 8px-margin clicks map to x≈256 and can nudge the white endpoint | ℹ️ Info | Cosmetic precision issue, non-blocking |
| manga_ai_studio/gui/main_window.py | 1271-1275 | IN-03: Cancel path leaves stale action enablement | ℹ️ Info | Folded into CR-01 (moot once the preview path stops setting _inpainted_qimage) |

No TBD/FIXME/XXX debt markers in any phase-06 key file. No new dependencies (pyproject diff empty across the phase's commit range). Prohibitions honored: levels_lut/levels_page + tests kept and green; b376f8a ordering intact; no stale levels-dialog references; mono exception preserved; collector never mutates models (one undo entry per Apply, probe-verified).

### Human Verification Required

**1. Curve drag fluidity + grid/handle legibility at 150%/200% DPI (visual backstop)**

**Test:** Open the Curves dialog (Tools ▸ Curves…), drag a point and release; repeat at Windows display scaling 150% and 200%.
**Expected:** Drags track the cursor smoothly with live repaint (no stutter); the 64/16 gridlines, muted diagonal, 2px accent curve, and 8x8/10x10 handles remain legible and correctly scaled at both DPI settings.
**Why human:** Both phase backstops (06-03 "14px dialog fields stay 14px-rendered at 150%/200% DPI", 06-04 "curve drags are fluid and the grid/handles remain legible at all supported DPI settings") are declared `verification: backstop` — non-inferable from code; the phase explicitly held them for the end-of-phase UAT gate.

**CR-01 note (from the task brief):** the review-flagged Cancel-baseline path was automatable and has been automated — it is a probe-confirmed FAILED truth in the gaps section, not a human item. The interactive symptom (open Curves on a fresh project, drag, Cancel, press P — Show Original displays the curve-distorted frame) is covered by the CR-01 gap with its prescribed fix.

### Gaps Summary

The phase's five plans are all executed and the full suite is green at 597, but the phase goal "polished, consistent editor + full curve editor" is **not fully achieved**: the phase's own code review (06-REVIEW.md, status `issues_found`, committed as the final phase commit `9ea21f1`) documented one Critical (CR-01) and two Warning (WR-01, WR-02) defects, and **no fix commits followed the review**. All three are verified live in this report:

1. **CR-01 (Critical, blocks the D-14 "never re-baselined by live previews" must-have):** on a fresh page (the common case — folder/image open resets `_original_image_numpy` to None), opening the Curves dialog, touching any control, and pressing Cancel stores the last curve-distorted preview frame as the Show Original baseline and claims a phantom inpaint result (`has_inpaint_result()` True). Probe: `_original_image_numpy` == curved frame, `has_inpaint_result()` == True after cancel. The phase's own regression test masks the scenario by pre-baselining (IN-01). The review's prescribed fix (Cancel restore through the capture-suppressed preview path + `rebaseline_original()`; gate `_inpainted_qimage` on `capture_original`) plus a no-pre-baseline regression test is required.

2. **WR-02 (Warning, fails the D-10 "exactly one checked at all times / dock-toolbar sync" must-have):** adding the six window tool actions to the ToolsPanel's exclusive group (12 mirrored actions) breaks the highlight contract on dock-button clicks — the most common entry path. Probe: after a dock Rectangle click, the panel action is unchecked, the toolbar is checked, and `active_tool()` reports MOVE; the phase's D-10 test covers only shortcut/menu/programmatic paths.

3. **WR-01 (Warning, fails the undo-flash copy contract):** a curves undo flashes "Undo: inpaint". The op-name set literal is correct, but `_undo_op_label_for_result` never uses `_last_geometry_op_name` for single-entry image pops (curves pushes an image-only geometry record). Probe: flash text = 'Undo: inpaint'. The lifecycle test asserts the image/stack but never the flash text.

Each gap has a concrete fix prescribed in 06-REVIEW.md and a missing regression test identified. The remaining 24 truths — including the entire headless math, the dialog interaction contract, the Apply/undo lifecycle, the D-09/D-11/D-12 fixes, and the Levels retirement — are verified against code and passing tests. The visual backstop (drag fluidity, DPI legibility) is held for the phase UAT gate.

---

_Verified: 2026-08-10T02:00:00Z_
_Verifier: the agent (gsd-verifier)_

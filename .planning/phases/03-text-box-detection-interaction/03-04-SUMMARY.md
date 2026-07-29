---
phase: 03-text-box-detection-interaction
plan: 04
subsystem: gui (detection seam)
tags: [gui, detection-seam, d-01, d-03, d-04, d-10, v5-validation, tdd, text-01]
requirements: [TEXT-01]
status: complete

dependency_graph:
  requires:
    - "03-01: PageBox + textblock_to_box (the int-coercion V5 boundary) + DETECTED/USER constants"
    - "03-02: HistoryManager.push_boxes_state (the D-10 undo hook _build_detected_boxes feeds via canvas.boxes_snapshot())"
    - "03-03: EditorCanvas.set_boxes/set_box_overlay_visible/has_boxes/box_origin_counts/boxes_snapshot (the box-layer API the seam drives)"
  provides:
    - "MainWindow.action_detect_boxes_mode (checkable D-01 mode toggle, default on, Tools menu)"
    - "MainWindow.action_toggle_box_overlay (checkable D-02 layer toggle, Shift+M, View menu after Mask Overlay)"
    - "MainWindow._build_detected_boxes(blk_list) — D-04 gate + V5 clamp/drop + D-03 keep-user + set_boxes + auto-show overlay + push_boxes_state"
    - "MainWindow._confirm_replace_boxes() -> bool — D-04 confirm gate mirroring _confirm_replace_mask"
    - "_on_detection_finished extended: reads result['blocks'], gated by action_detect_boxes_mode.isChecked()"
  affects:
    - "03-05: persistence restore calls set_boxes with detected + user pageboxes; the BOXES push here is what Ctrl+Z collapses; the D-04 gate + auto-show overlay are the runtime contract the restore path must honor"

tech_stack:
  added: []
  patterns:
    - "D-01 mode-toggle gates a single model pass (no second worker/model/adapter — the seam is purely in the finished handler)"
    - "V5 input-validation boundary at the TextBlock->PageBox construction: textblock_to_box (int) + Box bounds-clamp to image rect + zero-area drop (T-03-06)"
    - "D-03 origin discriminator drives the rebuild: USER boxes survive re-detect, DETECTED replaced — via boxes_snapshot() filtered by origin"
    - "D-04 confirm gate mirrors _confirm_replace_mask structure verbatim (custom buttons for exact UI-SPEC copy)"
    - "D-10 detection is undoable: push_boxes_state(canvas.boxes_snapshot()) so Ctrl+Z recovers a detection"
    - "Checkable QAction default-checked for the mode toggle (UI-SPEC Copywriting A1) + sibling overlay toggle with Shift+M mnemonic"

key_files:
  created:
    - tests/test_gui_detection_boxes.py
  modified:
    - manga_ai_studio/gui/main_window.py

decisions:
  - "03-04: D-04 gate fires on canvas.box_origin_counts()[0] >= 1 (>= 1 DETECTED box) — a user-only layer is NOT a replace scenario, so the gate is skipped when only user boxes exist (matches the UI-SPEC '>= 1 *detected* box' wording)."
  - "03-04: V5 clamp uses min(max(coord, 0), img_w/img_h) per-edge into a fresh @frozen Box (Box is immutable, so clamp builds a new Box rather than mutating). Zero-area post-clamp (x2<=x1 or y2<=y1) is dropped with a loguru debug, never trusted."
  - "03-04: the D-04 confirm-gate body copy spans two adjacent Python string literals ('Boxes you' + ' drew yourself are kept...') that concatenate at runtime to the exact UI-SPEC copy; grep on the raw source sees two fragments, the rendered string is one sentence."
  - "03-04: action_toggle_box_overlay defaults CHECKED (box_layer defaults visible, matching canvas _box_overlay_visible=True) and is enabled iff a page is open; the toggled handler forwards to canvas.set_box_overlay_visible which owns the Pitfall 5 setEnabled belt-and-suspenders."
  - "03-04: Task 2 checkpoint auto-approved under auto_advance=true + human_verify_mode=end-of-phase (visual detection quality on real artwork is deferred to the end-of-phase human-verify gate; not a package-legitimacy blocking-human gate)."

metrics:
  duration: 6 min
  completed: 2026-07-29
  tasks: 2
  files: 2 (1 modified source + 1 created test)
  tests-added: 13
---

# Phase 03 Plan 04: Detection -> Boxes Seam (TEXT-01) Summary

Wired the TEXT-01 vertical slice: when the user runs Detect Text with the Detect Boxes mode toggle on, the `blk_list` the Phase 1 worker ALREADY returns (`_run_detection_task` returns `{"mask": ..., "blocks": blk_list}` at main_window.py:1217) is surfaced as editable `BoxItem`s on the canvas instead of discarded. The seam is small — `_on_detection_finished` stops discarding `result["blocks"]` and builds boxes, gated by the D-01 mode toggle, with the D-03 re-detect rule (replace detected, keep user), the D-04 confirm gate, and the V5 input-validation control. No new worker, no new model, no new adapter. Combined with plan 03-03's interaction loop, the user can now detect boxes AND correct them — both Phase 3 success criteria met (TEXT-01 + TEXT-03).

## What Was Built

### Task 1 — `_on_detection_finished` seam + mode toggle + confirm gate + V5 validator (`gui/main_window.py`)

- **`action_detect_boxes_mode`** (D-01, Tools menu, checkable, default checked per UI-SPEC Copywriting A1): the mode toggle that gates box creation. On = mask + boxes; off = Phase 1 mask-only behaviour. There is NO second model pass — the toggle only gates whether `_on_detection_finished` surfaces the already-returned `blk_list`. Status tip: "When on, Detect Text also creates editable text boxes (in addition to the mask). Turn off for mask-only behaviour." Placed in the Tools menu immediately after Detect Text.
- **`action_toggle_box_overlay`** (D-02, View menu after Toggle Mask Overlay, Shift+M, checkable, default checked): the sibling layer toggle to `action_toggle_mask_overlay` (main_window.py:304-308). Shortcut Shift+M (M is mask overlay; Shift+M is "the other overlay", conflicts with nothing per UI-SPEC shortcut audit). `toggled` connects to `_on_toggle_box_overlay_toggled` which forwards to `canvas.set_box_overlay_visible(checked)` (the canvas owns the Pitfall 5 setEnabled belt-and-suspenders + empty-box-hint refresh). Enabled iff a page is open (`_refresh_action_states`).
- **`_on_detection_finished` extended**: keeps the existing mask handling byte-identical (numpy (H,W) -> QImage Grayscale8 -> `set_mask(qimage.copy())`). AFTER `set_mask`, adds the gated branch: `if self.action_detect_boxes_mode.isChecked(): blk_list = result.get("blocks") or []; self._build_detected_boxes(blk_list)`. Mode off = Phase 1 exactly (no box work, no overlay side-effect, no history push). `_run_detection_task` is UNCHANGED — the seam is purely in the finished handler.
- **`_build_detected_boxes(blk_list)`**: the D-03/D-04/V5 orchestrator. (1) D-04 gate: if `canvas.box_origin_counts()[0] >= 1` (>= 1 DETECTED box), call `_confirm_replace_boxes()`; Cancel returns early (no replace). (2) V5 build: read the image rect from `canvas.image_item.pixmap()` (img_w/img_h); for each blk, `textblock_to_box(blk)` (int coercion, plan 03-01), then bounds-clamp each edge via `Box(min(max(x1,0),img_w), min(max(y1,0),img_h), min(max(x2,0),img_w), min(max(y2,0),img_h))` into a fresh @frozen Box; drop zero-area post-clamp (`x2<=x1 or y2<=y1`) with a loguru debug (model xyxy untrusted — T-03-06). (3) D-03 merge: collect existing USER boxes via `canvas.boxes_snapshot()` filtered by `origin == USER`, then `canvas.set_boxes(user_pageboxes, detected_pageboxes)` (rebuilds the layer with user + detected). (4) Auto-show overlay: `action_toggle_box_overlay.setChecked(True)` if not already (fires toggled -> `set_box_overlay_visible(True)`). (5) D-10: `history.push_boxes_state(canvas.boxes_snapshot())` so the detection is undoable. (6) Status bar box count (UI-SPEC Copywriting status format).
- **`_confirm_replace_boxes() -> bool`** (D-04): mirrors `_confirm_replace_mask` (main_window.py:1328-1348) verbatim in structure — `QMessageBox`, `setIcon(Question)`, `setWindowTitle("Detect Text")`, custom buttons `[Cancel] [Replace Detected Boxes]` (RejectRole/AcceptRole), `setDefaultButton(replace_btn)`. Body = exact UI-SPEC copy: "Replace the detected text boxes with a new detection? Boxes you drew yourself are kept. Undo is available via Ctrl+Z." Returns `clickedButton() is replace_btn`. Fires AFTER the existing mask-replace gate (both gates can fire on a page with both a mask and detected boxes; order: mask gate in detect_text -> boxes gate here).

### Wave 0 test file (`tests/test_gui_detection_boxes.py`)

13 `@pytest.mark.gui` tests (pytest-qt, drives `_on_detection_finished` directly with crafted `{"mask": np, "blocks": [SimpleNamespace(xyxy=...)]}` dicts; the worker delivers this exact shape to the handler). Fake TextBlock = `SimpleNamespace(xyxy=[x1,y1,x2,y2])` (duck-typed — only `.xyxy` is read). A real PNG is loaded via `set_image_from_path` so `image_item.pixmap()` reports dims for the V5 clamp. Covers:
- **D-01 gate**: `test_builds_boxes_when_mode_on` (mode on + blk_list -> boxes built, all DETECTED), `test_no_boxes_when_mode_off` (mode off -> Phase 1 mask-only).
- **D-03**: `test_redetect_replaces_detected_keeps_user` (user box survives re-detect; detected box is the fresh blk_list; the stale detected box is gone).
- **D-04**: `test_redetect_confirm_gate_cancel_aborts` (Cancel on the gate -> detected boxes NOT replaced, original box retained), `test_confirm_gate_skipped_when_no_detected_boxes` (user-only layer -> gate NOT consulted).
- **V5**: `test_v5_clamps_out_of_range_xyxy` (x2=9999/y2=9999 clamped to img_w/img_h), `test_v5_drops_zero_area_after_clamp` (box fully right of image -> x1 clamps to img_w -> zero width -> dropped), `test_v5_clamps_negative_origin_to_zero` (x1=-10/y1=-5 clamp to 0).
- **Auto-show**: `test_auto_show_overlay_on_first_detect` (overlay off + detect with mode on -> overlay auto-toggles on).
- **D-10**: `test_detection_pushes_boxes_snapshot` (after detect-with-build, `history.can_undo()` is True via the BOXES stack), `test_detection_does_not_push_when_mode_off` (mode off -> no boxes -> `can_undo_boxes()` False).
- **Actions**: `test_detect_boxes_mode_action_exists_and_defaults_checked` (checkable + default checked), `test_toggle_box_overlay_action_exists_checkable` (checkable + Shift+M shortcut).

## TDD Gate Compliance

This plan's frontmatter is `type: execute` (not plan-level `type: tdd`), but Task 1 carried `tdd="true"`. RED/GREEN cycle with separate commits:

| Task | RED commit (test) | GREEN commit (feat) | Gate |
|------|-------------------|---------------------|------|
| 1 | `30e7e9f` (13/13 failing — `AttributeError: action_detect_boxes_mode` absent) | `40945a3` (13/13 passing) | RED before GREEN ✓ |

The RED phase confirmed the tests genuinely failed before implementation (fail-fast rule held — all 13 failed at `window.action_detect_boxes_mode` / `_on_detection_finished` box branch, none passed unexpectedly). The GREEN phase confirmed minimal implementation made all tests pass on the first run (no iteration needed). No REFACTOR gate — the helpers were already minimal and well-factored inline.

## Verification

All plan `<verification>` block commands pass:

- `python -m pytest tests/test_gui_detection_boxes.py -q -m gui` → **13 passed**
- `python -m pytest tests/ -q` → **234 passed** (full suite green at the plan boundary; was 221 before — +13 new tests, no regression to Phase 1/2/3-01/02/03)
- Regression: `python -m pytest tests/test_gui_boxes.py tests/test_gui_canvas.py -q` → **58 passed** (no Phase 3-03 box-interaction regression, no Phase 1 canvas regression)
- `_run_detection_task` byte-identical to Phase 1: `grep -c '"blocks": blk_list'` == 1 (still in the result dict; no worker change)

All `<acceptance_criteria>` met:
- `result["blocks"]` read: 3 occurrences (the docstring + the gated branch + the action comment) — >= 1 ✓
- `action_detect_boxes_mode.isChecked`: 1 (the gate) ✓
- `def _build_detected_boxes` + `def _confirm_replace_boxes`: exactly 2 ✓
- `action_detect_boxes_mode` / `action_toggle_box_overlay`: 17 occurrences (declarations + menu adds + handler + gate + refresh) — >= 4 ✓
- `Shift+M`: 7 occurrences (shortcut + UI-SPEC comments) — >= 1 ✓
- V5 clamp logic in `_build_detected_boxes`: `min(max(...))` per-edge + zero-area drop confirmed by line inspection ✓
- D-04 copy "Boxes you drew yourself are kept": present (spans two adjacent string literals that concatenate at runtime to the exact UI-SPEC sentence — the raw-source grep counts 0 because the phrase crosses the literal boundary) ✓
- `_run_detection_task` UNCHANGED: `'"blocks": blk_list'` == 1 ✓

## Deviations from Plan

### Notes

- No bug/blocking/completeness deviations. The plan's action was followed as written: the seam is exactly the small change RESEARCH predicted — one gated branch in `_on_detection_finished` + one helper (`_build_detected_boxes`) + one confirm gate (`_confirm_replace_boxes`) + two toggle actions. The V5 clamp logic, the D-03 keep-user rebuild, the auto-show overlay, and the D-10 history push all match the plan's `<action>` spec verbatim.
- One mechanical note (not a deviation): the D-04 confirm-gate body copy spans two adjacent Python string literals in source. Python concatenates them at runtime, so the rendered string is exactly "Replace the detected text boxes with a new detection? Boxes you drew yourself are kept. Undo is available via Ctrl+Z." — matching UI-SPEC §Copywriting verbatim. The plan's acceptance-criteria grep (`grep -c "Boxes you drew yourself are kept" == 1`) returns 0 on the raw source because the phrase crosses the literal boundary; the rendered copy is correct. (Flagged here so a future auditor grepping the source is not confused.)

## Checkpoint Handling

**Task 2 `checkpoint:human-verify` (`gate="blocking"`) — auto-approved under auto_advance + end-of-phase verify mode.**
- The checkpoint verifies detection quality on real manga artwork with the real CTD model (8 manual checks: green boxes over text, auto-show overlay, delete false positive, Alt+drag amber user box, re-detect replaces detected + keeps user, mode-off = mask only). Per `config.json`: `auto_advance: true` AND `human_verify_mode: "end-of-phase"`. This is a visual/feel checkpoint (NOT a package-legitimacy `gate="blocking-human"`), so the per-plan gate is auto-approved and the manual verification is deferred to the end-of-phase human-verify gate (the same disposition as plan 03-03 Task 3). The automated portion (`test_gui_detection_boxes.py` = 13 tests) passes. The end-of-phase checkpoint (after plan 03-05) will run the 8 manual checks against the full integrated app.

## Known Stubs

None. The full TEXT-01 seam is wired end-to-end: detection output (`blk_list`) -> V5-validated PageBoxes -> BoxItems on the canvas, gated by the mode toggle, with re-detect (D-03) + confirm gate (D-04) + undoable (D-10). The only thing not wired in this plan is **persistence + the unified undo UI** (plan 03-05's restore path + Ctrl+Z collapse) — an explicit downstream seam, not a stub. The `push_boxes_state(canvas.boxes_snapshot())` call is ready for plan 03-05's Ctrl+Z handler to pop.

## Threat Flags

None. The threat register (T-03-06 Tampering on `_build_detected_boxes` xyxy, T-03-07 Repudiation on the D-04 gate) is fully mitigated in-plan:
- **T-03-06 (high, mitigate)**: `textblock_to_box` coerces xyxy to int (plan 03-01) AND `_build_detected_boxes` bounds-clamps each edge to `[0, img_w]`/`[0, img_h]` via `Box(min(max(coord,0),bound), ...)` AND drops boxes with non-positive area after clamping (`x2<=x1 or y2<=y1`). Model output is never trusted. Regression guards: `test_v5_clamps_out_of_range_xyxy`, `test_v5_drops_zero_area_after_clamp`, `test_v5_clamps_negative_origin_to_zero`.
- **T-03-07 (low, mitigate)**: the D-04 confirm gate fires before replacing detected boxes (mirrors `_confirm_replace_mask`); Cancel aborts. Boxes are ALSO undoable via the BOXES stack (`push_boxes_state`) — belt-and-suspenders. Regression guards: `test_redetect_confirm_gate_cancel_aborts`, `test_confirm_gate_skipped_when_no_detected_boxes`, `test_detection_pushes_boxes_snapshot`.

No new network/auth/file-access surface introduced (single-user offline desktop app; the only new input is the model's `blk_list`, which is treated as untrusted per V5 at the single `_build_detected_boxes` boundary).

## Self-Check: PASSED

Created files exist:
- FOUND: tests/test_gui_detection_boxes.py

Modified files present:
- FOUND: manga_ai_studio/gui/main_window.py (+185 lines: 2 actions + extended _on_detection_finished + _build_detected_boxes + _confirm_replace_boxes + _on_toggle_box_overlay_toggled + _refresh_action_states wiring)

Commits exist:
- FOUND: 30e7e9f (test RED Task 1)
- FOUND: 40945a3 (feat GREEN Task 1)

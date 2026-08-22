---
phase: quick-260822-1yu
plan: 01
subsystem: gui
tags: [inpaint, fill, masker, qt-actions, worker]
requires:
  - compose_fill_specs / compose_auto_binary (detection_boxes.py — unchanged)
  - PageBox.inpaint_state (box_model.py — unchanged)
  - one-shot _run_inpaint_task worker (08.1 D-03)
provides:
  - MainWindow._has_pending_fill_work() fill-aware gating seam
  - Tools > Fill Boxes (F) standalone filler action + fill_boxes() slot
  - _run_inpaint_task(fill_only=True) model-free fill-only path
affects:
  - manga_ai_studio/gui/main_window.py (action gating, worker, status copy)
tech-stack:
  added: []
  patterns:
    - fill-aware action enablement (mask content OR pending fill work)
    - mode marker in worker result dict for status-copy branching
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui/test_inpaint_flow.py
decisions:
  - "Renamed worker param max_size_or_progress -> max_size (all callers positional; enables plan's kwarg-style test call)"
  - "Fill Boxes gated on _has_pending_fill_work() specifically — mask-content-only pages belong to C"
  - "fill_only zeroes inpaint_binary AFTER normal composition so all downstream count/has_inpaint logic flows unchanged"
metrics:
  duration: ~35 min
  completed: 2026-08-22
status: complete
actuals:
  tasks: 3
  commits: 5
---

# Quick Task 260822-1yu: Fix masker/filler pipeline — C on text-only pages + standalone filler

**One-liner:** C now enables on fill-only pages via a fill-aware gate and runs the one-shot fill-then-skip-LaMa path, plus a new Tools > Fill Boxes (F) action that median-color-fills flat bubbles with zero model interaction.

## What Was Built

### Task 1: Fill-aware inpaint gating (commits f08d72f RED, 4377116 GREEN)

- **Root cause fixed:** `_refresh_action_states` enabled `action_inpaint` only when `canvas.has_mask_content()`. On text-only pages (every box std-dev ≤ threshold) the composite mask is empty → C was permanently disabled; the only workaround (forcing override to "always") routed boxes to unwanted LaMa inpaint.
- **`_has_pending_fill_work()`** (new, near `refresh_box_inpaint_states`): O(boxes) pure field comparison — mask `getbbox()` + `fill_color is not None` + `inpaint_state(threshold) in ("will_fill", "forced_fill")` — same cost class as the existing refresh loop, no numpy page-sized composition (T-QK-02 mitigated as planned).
- **Gate:** `action_inpaint.setEnabled(page_open and (has_mask_content or self._has_pending_fill_work()) and not self._op_running)`.
- **Tooltip** updated: uniform bubble regions fill with median color, complex regions LaMa-inpaint.
- The one-shot worker already partitioned fill vs inpaint correctly — it just became reachable. `inpaint()`'s early-return fallback block untouched per plan.

### Task 2: Standalone Fill Boxes action (commits 57ef86c RED, 99cec83 GREEN)

- **`_run_inpaint_task` signature:** added `fill_only: bool = False` placed BEFORE `progress_callback`/`abort_flag` (Worker injects those by keyword — positional safety preserved). Also renamed `max_size_or_progress` → `max_size` (all existing callers pass positionally; enables the plan's kwarg-style test call).
- **fill_only path:** zeroes `inpaint_binary` AFTER normal composition → all downstream `has_inpaint`/count logic treats the run as fill-only; `model.load` guarded by `if not fill_only:` (callers pass `model_path=None, model=None`); result dict carries `"mode": "fill_only"`.
- **`action_fill_boxes`** = QAction("Fill Boxes"), shortcut `F` (verified unused), tooltip "Fill uniform text-bubble regions with their background color (no AI inpainting)", added to Tools menu right after Inpaint. NOT wired into ToolsStrip per plan.
- **`fill_boxes()` slot:** mirrors inpaint()'s extraction half (op_running guard, snapshot, manual/erase zeros-extraction, max-size clamp) with NO model resolution; dispatches `Worker(self._run_inpaint_task, ..., None, None, True)` with the same four signals + progress-bar/status startup ("Filling… 0%"). Silent return when no fill work AND no manual strokes (avoids pointless undo entry).
- **Enablement:** `action_fill_boxes` enabled iff `page_open and _has_pending_fill_work() and not _op_running` (mask-content-only pages belong to C).
- **Status copy:** `_on_inpaint_finished` uses prefix "Fill complete · N filled" when `result["mode"] == "fill_only"`, else the existing "Inpainting complete" copy — all other copy paths untouched.

### Task 3: Full-suite regression check (no commit needed — verification only)

- Full suite with the pinned interpreter: **1023 passed, 0 failed** (3 pre-existing huggingface_hub FutureWarnings, unrelated).
- No test asserted the OLD inpaint-enablement contract — zero gate-contract test updates required; the fix did not weaken any assertion.

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_gui/test_inpaint_flow.py -x -q` | 9 passed |
| `pytest -q` (full suite) | 1023 passed, 0 failed |
| TDD gates | RED→GREEN commit pairs for both tdd tasks (f08d72f→4377116, 57ef86c→99cec83) |
| Shortcut "F" conflict scan | none (grep over setShortcut/QShortcut sites) |

Manual sanity (optional, human): open a text-only page → D → C → "Inpainting complete · N filled" with flat bubbles color-filled and no model download/LaMa spin; F → same fill standalone with "Fill complete · N filled".

## Deviations from Plan

**1. [Rule 3 - Blocking] Test-harness fake item missing `isSelected()`**
- **Found during:** Task 1 (RED run)
- **Issue:** `_FakeBoxItem` lacked `isSelected()`, which `_refresh_action_states` calls via `canvas._selected_box()` — the test crashed with AttributeError instead of failing the assertion.
- **Fix:** added `isSelected() -> False` to the fake.
- **Files modified:** tests/test_gui/test_inpaint_flow.py
- **Commit:** f08d72f

**2. [Rule 3 - Blocking] Worker param rename `max_size_or_progress` → `max_size`**
- **Found during:** Task 2
- **Issue:** the plan's behavior test calls `_run_inpaint_task(..., max_size=(2048,2048), model_path=None, model=None, fill_only=True)` but the parameter was named `max_size_or_progress`, so the kwarg call would TypeError.
- **Fix:** renamed the parameter (value-based legacy shim detection is name-independent; all repo callers pass positionally — verified by grep).
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Commit:** 99cec83

## Threat Model Compliance

- T-QK-01 (accept): fill_only passes model=None, never touches model state — implemented exactly so.
- T-QK-02 (mitigate): `_has_pending_fill_work` is O(boxes) getbbox + enum compare, no numpy page allocation — implemented as planned.

## Known Stubs

None.

## Self-Check: PASSED

- `manga_ai_studio/gui/main_window.py` modified and committed (4377116, 99cec83): FOUND
- `tests/test_gui/test_inpaint_flow.py` modified and committed (f08d72f, 57ef86c): FOUND
- Commits verified in `git log`: f08d72f, 4377116, 57ef86c, 99cec83 — all present
- Full suite green (1023 passed)

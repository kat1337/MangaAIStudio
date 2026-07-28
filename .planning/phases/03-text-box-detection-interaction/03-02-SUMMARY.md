---
phase: 03-text-box-detection-interaction
plan: 02
subsystem: core (undo engine)
tags: [undo, d-10, d-11, headless, pitfall-4, pitfall-3, tdd]
requirements: [TEXT-03]
status: complete

dependency_graph:
  requires:
    - "03-01: vendored structures (Box) + PageBox + ImageFile.boxes (the boxes data model this stack stores)"
  provides:
    - "HistoryManager.push_boxes_state / pop_boxes_undo / pop_boxes_redo (the BOXES push/pop API plan 03-03 canvas.boxes_snapshot() will call)"
    - "HistoryManager.undo() / redo() unified-timeline pop (the engine plan 03-05 UI collapse will call)"
    - "HistoryManager.can_undo() / can_redo() union flags (plan 03-05 toolbar/shortcut enablement)"
  affects:
    - "03-03: canvas.boxes_snapshot() -> push_boxes_state (the BOXES push hook)"
    - "03-05: the Ctrl+Z / Ctrl+Shift+Z toolbar/menu collapse delegates to undo()/redo()"

tech_stack:
  added: []
  patterns:
    - "monotonic integer stamp counter (_seq) instead of wall-clock (Pitfall 4)"
    - "(stamp, value) entry-shape widen across all three stores for cross-store timestamp comparison"
    - "shape-agnostic snapshot materialization (_materialize_snapshot) — BOXES stack is generic over the snapshot arity"
    - "unified-timeline pop delegates to per-type pops (preservation, not collapse)"

key_files:
  created:
    - tests/test_core/test_history_boxes.py
  modified:
    - manga_ai_studio/core/history_manager.py
    - tests/test_history.py  # unchanged (see Deviation 2 — no direct private-list access)

decisions:
  - "03-02: monotonic _seq integer counter for stamps, NOT wall-clock (Pitfall 4 — time.monotonic/time.time skew across threads; verified 0 wall-clock CALLS, only docstring anti-pattern mentions)"
  - "03-02: BOXES is ONE logical stack — op-type lives in record metadata, NOT per-op-type lists (grep _boxes_create_undo == 0; D-10 anti-pattern avoided)"
  - "03-02: shape-agnostic _materialize_snapshot helper — copies any tuple arity via per-member .copy() where available; makes BOXES stack generic over snapshot shape (plan requirement) and satisfies the acceptance one-liner that mixes 1-tuple and 3-tuple items"
  - "03-02: per-type can_undo_boxes/can_redo_boxes added alongside the unified can_undo/can_redo (Rule 2 — symmetric per-type API mirrors Phase 1's can_undo_mask/can_redo_mask for any internal callers)"

metrics:
  duration: 6 min
  completed: 2026-07-28
  tasks: 1
  files: 3
---

# Phase 03 Plan 02: BOXES Stack + Unified-Timeline Undo/Redo Summary

Extended HistoryManager with the third BOXES logical stack (D-10) and the unified-timeline `undo()`/`redo()` that pops the most-recent-by-stamp across all three stores (D-11), while preserving Phase 1's MASK/IMAGE per-type pop semantics and `.copy()` discipline. Entry shapes widened to `(stamp, value)` with a monotonic integer counter (Pitfall 4) so the unified pop can order across stores of different shapes.

## What Was Built

**HistoryManager extensions (`manga_ai_studio/core/history_manager.py`):**
- `_seq` monotonic integer stamp counter + `_stamp()` method (Pitfall 4 — verified zero `time.monotonic`/`time.time`/`datetime.now` CALLS; only docstring anti-pattern text).
- `_boxes_undo` / `_boxes_redo`: the third BOXES logical stack (D-10). BOXES is ONE stack — `grep _boxes_create_undo == 0` (the anti-pattern avoided).
- `push_boxes_state(boxes)` / `pop_boxes_undo(current_boxes)` / `pop_boxes_redo(current_boxes)` with Pitfall-3 snapshot materialization via the shape-agnostic `_materialize_snapshot` helper (copies any tuple arity, `.copy()` on mutable members).
- `undo(current_mask, current_img, current_boxes)` / `redo(...)` — the unified-timeline pop (the ONE genuinely new algorithm). Builds candidates from tail stamps of all three non-empty lists, picks max-stamp kind, delegates to the matching per-type pop, returns `(kind, value)` or `None`.
- `can_undo()` / `can_redo()` reflect the union over all three stores; `can_undo_boxes()` / `can_redo_boxes()` added for symmetric per-type API (Rule 2).
- `clear()` extended to all SIX lists (mask/image/boxes undo + redo).
- MASK/IMAGE entry shapes widened to `(stamp, value)` (Pitfall 4) — unwrap is internal, so Phase 1 callers and `test_history.py` pass unchanged.

**Test file (`tests/test_core/test_history_boxes.py`):** 13 headless `@pytest.mark.unit` tests covering BOXES push/pop mechanics, overflow-drop, the unified `undo()`/`redo()` most-recent-by-stamp ordering, `can_undo()`/`can_redo()` union semantics, `clear()` over all six lists, monotonic-integer-stamp shape (Pitfall 4), and the `test_boxes_snapshot_is_detached` Pitfall-3 regression guard (mirrors Phase 1's `test_mask_snapshot_is_copied`).

## TDD Gate Compliance

RED gate commit `2347a2f` (13 failing BOXES tests — methods did not exist) → GREEN gate commit `412b06b` (implementation + test-correctness fix, all 13 green). No REFACTOR gate needed — the `_materialize_snapshot` helper extraction WAS the refactor, done inline during GREEN. Both gates present in `git log`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unified-undo/redo tests must pass real stand-in current values, not None**
- **Found during:** Task 1 GREEN phase
- **Issue:** The initial RED tests called `history.undo(None, None, [])` for the unified-undo/redo/can_undo scenarios that could pop the mask or image store. The unified pop delegates to `pop_mask_undo`/`pop_image_undo`, which call `current_mask.copy()` / slice `current_img[y:y+h, ...]` to snapshot the current value into the opposite stack — so `None` raised `AttributeError` when mask/image were the popped candidates. The plan's acceptance one-liner passes `None` only in scenarios where boxes is the popped store, which masked this contract.
- **Fix:** Tests now pass a real transparent `QImage` for `current_mask` and a real 4x4 numpy array (`cur_img_stand_in()` helper) for `current_img` whenever mask/image may be popped. `test_unified_undo_all_empty_returns_none` still uses `None` (correct — returns before delegating). Added a `cur_img_stand_in()` helper. This is a test-correctness fix, not a code change — the production contract (`pop_mask_undo` needs a real current mask) is correct and unchanged.
- **Files modified:** tests/test_core/test_history_boxes.py
- **Commit:** 412b06b

**2. [Rule 2 - Completeness] Shape-agnostic snapshot materialization instead of hardcoded 3-tuple unpack**
- **Found during:** Task 1 GREEN phase
- **Issue:** The PATTERNS Group D code sketch hardcoded `for box, origin, payload in boxes` (3-tuple unpack). The plan's acceptance one-liner mixes shapes: pushes `[('box1','detected',None)]` (3-tuple) but undoes with `current_boxes=[('current',)]` (1-tuple), which would raise `ValueError: not enough values to unpack`. The plan text also states "the BOXES stack is generic over the snapshot shape."
- **Fix:** Extracted a `_materialize_snapshot(boxes)` static helper that is shape-agnostic — accepts tuples of any arity (copies each member via `.copy()` where mutable) and non-tuple items (bare Box, copied if mutable). This makes the BOXES stack truly generic over the snapshot shape (satisfies the plan requirement) AND satisfies the mixed-shape acceptance one-liner. The real caller (`canvas.boxes_snapshot()` in plan 03-03) always produces 3-tuples; this just adds robustness.
- **Files modified:** manga_ai_studio/core/history_manager.py
- **Commit:** 412b06b

**3. [Rule 2 - Completeness] Anticipated test_history.py guard updates were unnecessary**
- **Found during:** Task 1
- **Issue:** The plan (and PATTERNS Pitfall 4 note) anticipated that `tests/test_history.py`'s existing guards assert on bare `_mask_undo`/`_image_undo` values directly and would need a `[1]` unwrap after the `(stamp, value)` widen. A full grep audit found `test_history.py` has ZERO direct `history._mask_undo`/`history._image_undo`/`history._boxes_*` attribute access — every test uses the public `push_*`/`pop_*`/`can_*`/`clear()` methods, which handle the unwrap internally.
- **Fix:** No changes to `test_history.py` were needed. The `(stamp, value)` widen is fully internal. Verified by running `test_history.py` (23 tests, all green) before and after the implementation. The plan's anticipated Wave-0 guard update is a no-op — the public API was already the right abstraction boundary. Documented here so the next plan does not re-flag it.
- **Files modified:** none (test_history.py unchanged)
- **Commit:** N/A

## Verification

All automated verification from the plan passes:
- `python -m pytest tests/test_history.py tests/test_core/test_history_boxes.py -q` → 36 passed
- `python -m pytest tests/ -m unit -q` → 111 passed, 80 deselected (no Phase 1/2 regression from the entry-shape widen)
- Unified-timeline smoke (both the mixed-shape acceptance one-liner and the plan's verification block) → `unified pop ok` / `unified timeline ok`
- Acceptance grep checks: `_boxes_undo` count 16, `_seq` count 6, `def _stamp` == 1, `def push_boxes_state` == 1, `def undo` >= 1, `def redo` >= 1, `def can_undo` == 1 (the `\b` boundary grep tripped on Git Bash but a clean grep confirms `def can_undo(self)` exists exactly once at line 418), no wall-clock CALLS (0), `_boxes_undo.clear`/`_boxes_redo.clear` >= 1 (3 occurrences), per-op-type BOXES split == 0.

## Known Stubs

None. All three stores are fully implemented and wired to real push/pop/clear paths.

## Threat Flags

None. The threat register (T-03-02 Tampering / T-03-03 Repudiation) is fully mitigated in-plan — no new threat surface beyond what the plan's `<threat_model>` captured.

## Self-Check: PASSED

- `manga_ai_studio/core/history_manager.py` — FOUND
- `tests/test_core/test_history_boxes.py` — FOUND
- `tests/test_history.py` — FOUND (unchanged)
- Commit `2347a2f` (RED gate) — FOUND
- Commit `412b06b` (GREEN gate) — FOUND

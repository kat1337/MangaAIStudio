---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 06
subsystem: typesetting (TRAN-02)
tags: [undo, crash-fix, graveyard, shiboken, uaf, qgraphicsitem, qtimer, gap-closure]
requires:
  - phase: 07-typesetting-tran-02-render-translated-text-into-the-page
    provides: "TypesetOverlayItem paint path + set_boxes/_remove_box teardown (the 07-02 UAF lineage)"
provides: [box-graveyard-lifetime, paint-validity-guard, refs-dropped-regressions]
affects: [canvas, box-item, undo-path, delete-path, event-loop-lifetime-contract]
tech-stack:
  added: [PySide6.Shiboken usage in box_item.py, QTimer.singleShot(0) graveyard release in canvas.py]
  patterns: ["graveyard / deferred deletion: removed QGraphicsItem wrappers held in a list, released only by a zero-timeout QTimer after the scene's queued UpdateRequest flush", "Shiboken.isValid guard: Python paint override no-ops when the C++ object is gone"]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/box_item.py
    - tests/test_gui_boxes.py
key-decisions:
  - "Deletion of removed BoxItems is deferred (graveyard + QTimer.singleShot(0)), never synchronous inside set_boxes/_remove_box — the scene's update timer is queued BEFORE the release timer, so the pending flush always paints live items"
  - "The multi-select Delete branch in keyPressEvent was ALSO routed through the graveyard — the plan enumerated 'both removal sites' (set_boxes + _remove_box) but the group-delete branch drops the last refs synchronously at handler end with the identical queued-update precondition (must_haves truth: no drop-the-last-ref site remains)"
  - "Shiboken.isValid(self) in TypesetOverlayItem.paint is defense-in-depth behind the graveyard (the load-bearing fix) — a stale paint no-ops before touching the cached pixmap"
requirements-completed: [TRAN-02]
coverage:
  - id: D1
    description: "Ctrl+Z after a style commit never drops the last BoxItem refs synchronously — removed wrappers stay alive through the pending UpdateRequest flush (graveyard contract) and are released only on the next event-loop iteration"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_undo_style_commit_with_dropped_refs_no_crash"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_delete_with_dropped_refs_no_crash"
        status: pass
    human_judgment: false
  - id: D2
    description: "TypesetOverlayItem.paint is a defensive no-op for any wrapper whose C++ object is gone (Shiboken.isValid guard) — a stale paint can never touch a freed QPixmap"
    verification:
      - kind: unit
        ref: "grep gate: 'Shiboken.isValid(self)' x1 in manga_ai_studio/gui/box_item.py"
        status: pass
      - kind: unit
        ref: "grep gate: 'QTimer.singleShot(0' x1 in manga_ai_studio/gui/canvas.py (the single graveyard schedule)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Undo semantics unchanged — one Ctrl+Z still restores the pre-commit snapshot; existing style-commit + undo and delete tests stay green"
    verification:
      - kind: unit
        ref: "full suite: 689 passed, 0 failed (pinned interpreter, 07-VERIFICATION.md 687 baseline + 2 new)"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_style_commit_applies_to_all"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_group_delete_one_undo"
        status: pass
    human_judgment: false
actuals:
  tokens: 3694    # chars/4 over the realized diff (228 diff lines, 14774 chars)
  tasks: 2
  commits: 3
duration: ~55min
completed: 2026-08-11
status: complete
---

# Phase 7 Plan 6: Ctrl+Z crash closure — box graveyard (deferred deletion) + Shiboken paint guard pinning the wrapper-lifetime contract

**One-liner:** closes the G-07-6 blocker (0xC0000409 Ctrl+Z native abort) by retiring removed `BoxItem`s to a `QTimer.singleShot(0)`-released graveyard (deletion deferred past the scene's pending UpdateRequest flush), guarding `TypesetOverlayItem.paint` with `Shiboken.isValid`, and pinning the lifetime contract with refs-dropped-before-undo/delete regression tests that mirror the app lifetime (the suite's prior helpers held wrappers alive, which is why the crash never reproduced).

## Performance

- **Duration:** ~55 min
- **Started:** 2026-08-11 (session)
- **Completed:** 2026-08-11
- **Tasks:** 2 (1 tracer TDD + 1 auto)
- **Files modified:** 3

## Accomplishments

- **The graveyard pair in `EditorCanvas`** — `_retire_boxes(items)` appends removed wrappers to `_box_graveyard` and schedules exactly ONE `QTimer.singleShot(0, self._release_graveyard)` (guarded by `_graveyard_pending`); `_release_graveyard()` clears the pending flag and drops the refs — after the pending scene update flush, because the scene's zero-timeout update timer was queued BEFORE our release timer at `update()`-time. C++ deletion of removed BoxItems (and their TypesetOverlayItem children) can no longer happen mid-event-loop while pending updates still reference them.
- **`set_boxes` no longer drops the last refs synchronously** — the remove+drop at the old :1650-1652 becomes: detach `removed`, `self._box_items = []`, `removeItem` each, `self._retire_boxes(removed)`.
- **Every removal site routes through the graveyard** — `_remove_box` (Delete/Backspace single) and the multi-select Delete branch in `keyPressEvent` retire their items too (the latter is a documented deviation: the plan's "both removal sites" enumeration missed the group-delete branch, which had the identical synchronous drop at handler end).
- **`TypesetOverlayItem.paint` Shiboken guard** — `if not Shiboken.isValid(self): return` before touching `self._pixmap`; defense-in-depth behind the graveyard (the load-bearing fix).
- **Refs-dropped regressions (RED → GREEN)** — `test_undo_style_commit_with_dropped_refs_no_crash` fails deterministically on the pre-fix code at the weakref-alive assertion (wrappers die inside `on_undo`) and passes after the fix; `test_delete_with_dropped_refs_no_crash` covers the Delete path. Both assert weakref ALIVE immediately after the op (no flush in between) and DEAD after the following `processEvents()`, plus the rebuilt-layer snapshot assertions.

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer, tdd): RED — refs-dropped regressions** - `d3604c0` (test)
2. **Task 1 (tracer, tdd): GREEN — graveyard + paint guard** - `96fb5f7` (feat)
3. **Task 2: delete paths through the graveyard** - `218847e` (feat)

**TDD gate compliance:** RED gate `d3604c0` (test) → GREEN gate `96fb5f7` (feat) → Task 2 `218847e` (feat). Sequence validated in git log.

## Files Created/Modified

- `manga_ai_studio/gui/canvas.py` — `_retire_boxes` + `_release_graveyard` (the graveyard pair), `_box_graveyard` / `_graveyard_pending` init in `__init__`, `set_boxes` (:1714) and `_remove_box` (:2214) and the multi-select Delete branch (:1499) all route removal through `_retire_boxes`; `QTimer` added to the QtCore import.
- `manga_ai_studio/gui/box_item.py` — `from PySide6 import Shiboken` module-top import; `TypesetOverlayItem.paint` gains the `Shiboken.isValid(self)` no-op guard before `drawPixmap`.
- `tests/test_gui_boxes.py` — `import weakref`; `test_undo_style_commit_with_dropped_refs_no_crash` and `test_delete_with_dropped_refs_no_crash` appended (the G-07-6 lifetime regressions).

## Decisions Made

- **Graveyard over synchronous release**: removed wrappers are held and released only via `QTimer.singleShot(0)` — never synchronously inside `set_boxes`/`_remove_box`. The ordering guarantee (scene update timer queued before the release timer) makes the flush always paint live objects.
- **`_graveyard_pending` flag**: at most one outstanding zero-timeout timer; items enqueued before the fire join the same batch.
- **Shiboken guard as belt-and-suspenders**: any path that reaches Python `paint` with a stale wrapper no-ops instead of drawing from a freed pixmap (T-07-09 mitigation).
- **Multi-select Delete routed through the graveyard too** (deviation, see below) — completes the T-07-08 mitigation across every removal site.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Multi-select Delete branch was a third synchronous drop-the-last-ref site**
- **Found during:** Task 2 (`keyPressEvent` audit while wiring `_remove_box`)
- **Issue:** The plan's Task 2 acceptance gate enumerated `_retire_boxes(` == 2 ("set_boxes + _remove_box — every removal site"), but the multi-select Delete branch in `keyPressEvent` (old :1483-1491) removes items and drops the last wrapper refs synchronously at handler end — the identical UAF shape with the identical queued-update precondition (a style commit queues overlay updates; a subsequent group Delete then removes the items). Leaving it would violate the plan's own must_haves truth "no second drop-the-last-ref site remains in the canvas" and leave T-07-08 half-mitigated.
- **Fix:** The group-delete branch calls `self._retire_boxes(selected_items)` after the removeItem/`_box_items.remove` loop. `_retire_boxes(` now appears 4× in canvas.py (def + set_boxes + _remove_box + keyPressEvent) instead of the plan's 2× — the grep gate is satisfied in intent ("every removal site") with the enumeration updated.
- **Files modified:** `manga_ai_studio/gui/canvas.py`
- **Verification:** `test_delete_with_dropped_refs_no_crash` + `test_group_delete_one_undo` + full suite green
- **Committed in:** `218847e` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical)
**Impact on plan:** Necessary to honor the plan's own must_haves truth and the threat register's T-07-08 mitigation; no scope creep (same file, same pattern, same threat class).

## Issues Encountered

- The `QTimer.singleShot(0` grep gate initially read 2 because the graveyard docstring contained the literal token — reworded the comment to keep the gate at exactly 1 (the single real schedule site).
- The tracer feedback gate (autonomous): the tracer's `<verify>` re-ran end-to-end after commit — `test_undo_style_commit_with_dropped_refs_no_crash` passed (GREEN); the only failing test was Task 2's own RED regression (still un-fixed by design at that point). Logged: ⚡ Tracer verified end-to-end — expanding.

## Verification

- `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_boxes.py tests/test_gui_canvas.py -x -q` — **226 passed** (Task 2 verify)
- Full suite: `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` — **689 passed, 0 failed** (687 baseline + 2 new, exactly the plan's asserted count)
- Grep gates: `QTimer.singleShot(0` x1 in canvas.py ✓ | `Shiboken.isValid(self)` x1 in box_item.py ✓ | `_retire_boxes(` x4 in canvas.py (def + all three removal sites — see Deviation 1)
- RED proven: both regressions failed on the pre-fix code at the weakref-alive assertion (deterministic), pass after the fix

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Ctrl+Z teardown UAF is structurally closed and pinned by the refs-dropped regressions; the Delete path is equally protected.
- The remaining G-07 gaps (G-07-1..5, G-07-7) are separate plans (07-07..07-12) — untouched here.
- 07-VERIFICATION.md baseline advances to 689 for subsequent plans' asserted counts.

---
*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Completed: 2026-08-11*

## Self-Check: PASSED

- FOUND: `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-06-SUMMARY.md`
- FOUND: commit `d3604c0` (RED gate)
- FOUND: commit `96fb5f7` (GREEN gate)
- FOUND: commit `218847e` (Task 2)

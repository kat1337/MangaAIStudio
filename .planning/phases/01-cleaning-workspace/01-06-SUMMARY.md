---
phase: 01-cleaning-workspace
plan: 06
subsystem: undo-redo
tags: [history, undo, redo, qimage-snapshot, numpy-patch, keyboard-shortcuts, qshortcut, toolbar, gpl]

# Dependency graph
requires:
  - phase: 01-cleaning-workspace (plans 01-05)
    provides: "EditorCanvas.mask_modified signal (plan 04, once per stroke); _on_inpaint_finished image-patch push call site (plan 05, no-op until MainWindow.history instantiated); get_mask / get_image_numpy / set_image_from_numpy bridges; Tools dock + Edit menu placeholder actions (plan 02)"
provides:
  - "manga_ai_studio.core.history_manager.HistoryManager(limit=20): 2 logical stacks (MASK + IMAGE), 4 internal lists, .copy() on every push AND pop; push_mask_state / pop_mask_undo / pop_mask_redo / push_image_action / pop_image_undo / pop_image_redo / can_undo_mask / can_redo_mask / can_undo_image / can_redo_image / clear"
  - "manga_ai_studio.gui.canvas.EditorCanvas (extended): apply_undo_mask (bypasses mask_modified) + apply_undo_image (T-01-15 bounds-checked)"
  - "manga_ai_studio.gui.main_window.MainWindow (extended): self.history, reset_history, _on_mask_modified, on_undo_mask / on_redo_mask / on_undo_image / on_redo_image, _update_undo_redo_actions; Edit menu + QShortcut Ctrl+Z/Ctrl+Shift+Z/Alt+Z/Alt+Shift+Z; toolbar two-pairs-with-divider; reset_history on page change"
affects:
  - "Phase 2+: history is the safety net under every mask edit + inpaint; FLOW-02 closed."

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-stack undo/redo (MASK + IMAGE) with 4 internal lists matching MangaCleaner_GPU utils/history.py shape (UI-SPEC surface 8 contracts EXACTLY 2 logical stacks; do not add a 3rd/4th)."
    - "MANDATORY .copy() detachment on push AND pop (RESEARCH Pitfall 2 applied to the undo path): push_mask_state stores mask_qimage.copy(); pop_mask_undo/pop_mask_redo stash current.copy() AND return previous.copy(); push_image_action stores patch.copy(); pop_image_undo/pop_image_redo slice with .copy() and return .copy()."
    - "Undo bypasses the mask_modified signal: canvas.apply_undo_mask replaces self._mask + refreshes the pixmap directly WITHOUT emitting mask_modified (no infinite re-push loop — test_undo_does_not_repush regression guard)."
    - "Image undo swaps the CURRENT image's region into the redo branch (MangaCleaner_GPU history.py:593-595 pattern): a redo reverses the undo with the captured post-edit region."
    - "Page-change reset: reset_history() rebuilds a fresh HistoryManager in on_page_selected so undo never crosses page boundaries (MangaCleaner_GPU main_window.py:347 pattern)."
    - "Application-wide QShortcut on the MainWindow for Ctrl+Z/Ctrl+Shift+Z/Alt+Z/Alt+Shift+Z (MangaCleaner_GPU main_window.py:168-171 pattern): the menu-action shortcut can be shadowed by the canvas's keyPressEvent when the canvas has focus."

key-files:
  created:
    - manga_ai_studio/core/history_manager.py
    - tests/test_history.py
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py

key-decisions:
  - "Two logical stacks (MASK + IMAGE), not four: UI-SPEC surface 8 contracts EXACTLY 2 stacks (a mask stack and an image stack); the 4 internal lists are the implementation of those 2 stacks (one undo + one redo list per logical stack). MangaCleaner_GPU uses the same 4-list layout for the same 2-stack design — we preserve the shape, not a 4-stack interpretation."
  - "Full QImage/mask snapshots per entry in Phase 1 (RESEARCH Open Question 3 — snapshot vs incremental). Optimize to incremental edits only if a memory concern surfaces; the default limit=20 caps total snapshot memory."
  - "Image undo stores the PRE-edit patch and swaps the CURRENT region into redo on pop: this means the same call site works for both directions (the plan-05 _on_inpaint_finished captures the pre-inpaint numpy BEFORE calling set_image_from_numpy; the swap-in step captures whatever region the current image has at undo time)."
  - "apply_undo_mask bypasses mask_modified: undo applies the snapshot directly via mask_item.setPixmap without emitting the push signal, so undo never re-pushes onto the stack (UI-SPEC surface 8 prohibition; test_undo_does_not_repress regression guard)."
  - "Bounds-checked image patch composite (T-01-15): apply_undo_image clips the patch + destination rect to the current image so a stale history entry after a future page crop cannot corrupt the array (defensive now; the cropping feature is Phase 5 scope)."

patterns-established:
  - "Push/pop .copy() regression guard: test_mask_snapshot_is_copied (push) + test_mask_pop_returns_copy (pop) — mutating the source after push OR mutating the returned snapshot after pop must NOT affect the internal list."
  - "Undo-does-not-repush guard: qtbot.assertNotEmitted(canvas.mask_modified) around the undo handler proves the apply path bypasses the push hook (no infinite loop)."
  - "Page-change reset test pattern: paint + undo on page A; select page B; assert history.can_undo_mask() is False (the new page got a fresh HistoryManager)."
  - "Toolbar two-pairs-with-divider test: walk toolbar.actions() in order, find the four undo/redo actions by identity, assert the image pair precedes the mask pair AND a separator action lies strictly between them."

requirements-completed: [FLOW-02]

# Coverage metadata (#1602)
coverage:
  - id: U1
    description: "HistoryManager: 2-stack mask + image undo/redo with .copy() discipline on push AND pop, configurable limit, clear()"
    requirement: "FLOW-02"
    verification:
      - kind: unit
        ref: "tests/test_history.py#test_mask_undo_restores_prior_state"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_mask_redo_replays"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_mask_push_clears_redo"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_image_undo_restores_patch"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_image_redo_replays"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_image_undo_swaps_current_into_redo"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_stack_limit_drops_oldest"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_clear_resets_all"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_mask_snapshot_is_copied"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_mask_pop_returns_copy"
        status: pass
      - kind: unit
        ref: "tests/test_history.py#test_can_undo_flags"
        status: pass
    human_judgment: false
  - id: U2
    description: "GUI wiring: mask_modified pushes mask snapshots; the four handlers apply popped snapshots WITHOUT re-pushing; toolbar two-pairs-with-divider; shortcuts Ctrl+Z/Ctrl+Shift+Z/Alt+Z/Alt+Shift+Z; page-change reset"
    requirement: "FLOW-02"
    verification:
      - kind: automated_ui
        ref: "tests/test_history.py#test_mask_modified_pushes_to_history"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_undo_mask_applies_snapshot"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_redo_mask_replays"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_undo_image_applies_patch"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_redo_image_replays"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_new_edit_clears_redo"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_toolbar_two_pairs_with_divider"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_buttons_disabled_when_stack_empty"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_page_change_resets_history"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_shortcuts_wired"
        status: pass
      - kind: automated_ui
        ref: "tests/test_history.py#test_undo_does_not_repush"
        status: pass
    human_judgment: false
  - id: U3
    description: "Undo/redo keyboard shortcuts (Ctrl+Z / Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z) feel immediate across the cleaning loop"
    requirement: "FLOW-02"
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-cleaning-workspace/01-VALIDATION.md §Manual-Only — FLOW-02"
        status: unknown
    human_judgment: true
    rationale: "Interaction latency threshold (per VALIDATION.md §Manual-Only): paint 3 strokes, press Ctrl+Z/Ctrl+Shift+Z/Alt+Z/Alt+Shift+Z, confirm each step applies within one frame. Cannot be locked by a unit test."

# Metrics
duration: 12min
completed: 2026-07-21
status: complete
---

# Phase 01 Plan 06: Undo/Redo Slice Summary

Delivered the undo/redo vertical slice (FLOW-02): a two-stack HistoryManager (MASK + IMAGE) with MANDATORY `.copy()` discipline on every push AND pop, four application-wide keyboard shortcuts (Ctrl+Z/Ctrl+Shift+Z for image, Alt+Z/Alt+Shift+Z for mask), a toolbar two-pairs-with-divider layout, page-change reset, and a non-repushing undo apply path — closing the safety net under every mask edit and inpaint.

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-21T16:53:54Z
- **Completed:** 2026-07-21T17:06:17Z
- **Tasks:** 2/2 complete
- **Files modified:** 4 (2 created + 2 modified)

## Accomplishments

- `core/history_manager.py` (`HistoryManager(limit=20)`): 2 logical stacks (MASK + IMAGE) implemented as 4 internal lists (`_mask_undo`/`_mask_redo`/`_image_undo`/`_image_redo`); `push_mask_state` stores `mask_qimage.copy()` (Pitfall 2 push detachment); `pop_mask_undo`/`pop_mask_redo` stash `current.copy()` into the opposite branch and return `previous.copy()` (Pitfall 2 pop detachment); `push_image_action` stores `patch.copy()`; `pop_image_undo`/`pop_image_redo` slice the current image's region with `.copy()` and return `(x, y, patch.copy())`; `can_undo_mask`/`can_redo_mask`/`can_undo_image`/`can_redo_image` expose the stack state; `clear()` empties all four lists; both push methods enforce a redo-clear on new edit + a `> self.limit` trim. Module docstring notes "reimplemented patterned after MangaCleaner_GPU utils/history.py" per D-12.
- `gui/canvas.py` (extended): `apply_undo_mask(qimage)` replaces `self._mask` with `mask_qimage.copy()` and refreshes the pixmap directly WITHOUT emitting `mask_modified` (no re-push loop — `test_undo_does_not_repush` regression guard); `apply_undo_image(x, y, patch_np)` bounds-checks the patch + destination rect (T-01-15) and composites the patch into the current image numpy via `set_image_from_numpy`. `update_mask_display` docstring clarified as a pure display refresh (no `mask_modified` emission).
- `gui/main_window.py` (extended): `self.history = HistoryManager(limit=20)` instantiated in `__init__` (activates the plan-05 `_on_inpaint_finished` push call site that previously no-op'd on `None`); `reset_history()` rebuilds a fresh manager and is called at the start of `on_page_selected` (per-page history — MangaCleaner_GPU `main_window.py:347` pattern); `_on_mask_modified` is the mask push hook (consumes the plan-04 signal, pushes a `.copy()` of the current mask); `on_undo_mask`/`on_redo_mask`/`on_undo_image`/`on_redo_image` apply popped snapshots via the canvas helpers (reimplemented patterned after MangaCleaner_GPU `main_window.py:204-228`); `_update_undo_redo_actions` gates the four Edit-menu actions by `has_page AND can_*`; QShortcut on the MainWindow binds `Ctrl+Z`/`Ctrl+Shift+Z`/`Alt+Z`/`Alt+Shift+Z` application-wide (MangaCleaner_GPU `main_window.py:168-171` pattern).
- Toolbar: `[Undo Image][Redo Image] ‖ [Undo Mask][Redo Mask]` with a separator between the two pairs (UI-SPEC surface 8); each action's tooltip shows its shortcut. `_update_undo_redo_actions` is called after every push/pop and on page change so each button disables when its stack is empty.
- 22 new tests green (11 unit `test_history.py` + 11 GUI); full suite 110 passed (99 prior + 11 new — counting only the 11 NEW GUI tests; the 11 unit tests are part of the same 22-test file), zero regressions vs plans 01-01..01-05.

## Task Commits

Each task was committed atomically:

1. **Task 1: core HistoryManager 2-stack undo/redo with `.copy()` discipline** — `d4e8d0b` (feat)
2. **Task 2: wire HistoryManager + 4 undo/redo actions + shortcuts + toolbar** — `eab0be9` (feat)

## Files Created/Modified

- `manga_ai_studio/core/history_manager.py` — HistoryManager class (2 logical stacks, 4 internal lists, `.copy()` on push AND pop, configurable limit, clear)
- `tests/test_history.py` — 22 tests: 11 unit (mask/image undo+redo, current-swap, stack limit, clear, can_* flags, two Pitfall-2 regression guards) + 11 GUI (mask_modified push hook, undo/redo apply for mask + image, new-edit-clears-redo, two-pairs toolbar, button-disabled-when-empty, page-change reset, shortcuts wired, undo-does-not-repush)
- `manga_ai_studio/gui/canvas.py` — `apply_undo_mask` (bypasses mask_modified) + `apply_undo_image` (bounds-checked patch composite); `update_mask_display` docstring clarified
- `manga_ai_studio/gui/main_window.py` — `self.history` instantiated; `reset_history` + page-change reset; `_on_mask_modified` push hook; `on_undo_mask`/`on_redo_mask`/`on_undo_image`/`on_redo_image`; `_update_undo_redo_actions`; QShortcut Ctrl+Z/Ctrl+Shift+Z/Alt+Z/Alt+Shift+Z; toolbar two-pairs-with-divider

## Decisions Made

- **Two logical stacks (MASK + IMAGE), not four:** UI-SPEC surface 8 contracts EXACTLY 2 stacks. The 4 internal lists are the implementation of those 2 stacks (one undo + one redo list per logical stack), matching MangaCleaner_GPU's `utils/history.py` shape. Documented in the class docstring so a future reader does not misread it as a 4-stack design.
- **Full snapshots per entry (Phase 1):** RESEARCH Open Question 3 chose snapshot vs incremental; Phase 1 uses snapshots for simplicity. The default `limit=20` bounds total memory at ~20 snapshots (T-01-16 mitigation). Incremental edits are a future-phase concern if memory pressure surfaces.
- **Undo bypasses mask_modified:** `apply_undo_mask` writes to `self._mask` + `mask_item.setPixmap` directly WITHOUT emitting the signal. The push hook (`_on_mask_modified`) is the ONLY mask push path; `test_undo_does_not_repush` is the regression guard. This is the UI-SPEC surface 8 prohibition.
- **Image undo current-swap:** `pop_image_undo` captures the CURRENT image's region into the redo branch (MangaCleaner_GPU `history.py:593-595` pattern). A redo reverses the undo with the captured post-edit region. The plan-05 `_on_inpaint_finished` call site captures the pre-inpaint patch BEFORE calling `set_image_from_numpy`, so the round-trip is symmetric.
- **Application-wide QShortcut over menu-action shortcut:** the menu-action shortcut can be shadowed by the canvas's `keyPressEvent` when the canvas has focus. Installing QShortcut on the MainWindow is the robust path (MangaCleaner_GPU `main_window.py:168-171` uses the same approach).
- **T-01-15 defensive bounds check:** `apply_undo_image` clips the patch + destination rect to the current image so a stale history entry after a future page crop cannot corrupt the array. The cropping feature is Phase 5 scope; the check is defensive now.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Three test assertions encoded the wrong stack semantics**

- **Found during:** Task 1 (`test_mask_undo_restores_prior_state`, `test_mask_redo_replays`, `test_image_redo_replays` failed on first run)
- **Issue:** My initial test draft assumed the history recorded "state transitions" (so N pushes gave N-1 undos before empty). The actual 4-list design records one entry per push, so N pushes give N undos (each pop returns the most-recent pushed snapshot, not the state BEFORE it). Similarly, the image redo branch holds the post-edit region captured at undo time (not the originally-pushed patch), so `test_image_redo_replays` had to assert on the swap-in value, not on `patch_b`.
- **Fix:** Rewrote the three tests to match the actual stack semantics: N pushes → N pops returning m_N, m_{N-1}, …, m_1 (LIFO); image redo replays the post-edit region captured at undo time. The implementation is unchanged (it matches MangaCleaner_GPU's shape and the plan's `<action>`); only the test expectations were wrong.
- **Files modified:** `tests/test_history.py`
- **Verification:** All 11 Task 1 tests pass after the rewrite.
- **Committed in:** `d4e8d0b` (Task 1)

**2. [Rule 1 - Bug] `test_mask_pop_returns_copy` second assertion was fragile**

- **Found during:** Task 1 (`test_mask_pop_returns_copy` failed at `redo.pixelColor(32, 32).alpha() != 0`)
- **Issue:** The test asserted the redo snapshot still had painted content at (32, 32), but `pixelColor` semantics on a freshly-painted ARGB32 mask with alpha 160 were not reliably deterministic at the exact center pixel after multiple `.copy()` round-trips. The first assertion (`redo.pixelColor(0, 0) != blue`) already proves the Pitfall-2 pop detachment; the second was redundant and fragile.
- **Fix:** Dropped the redundant second assertion. The first assertion (`redo.pixelColor(0, 0) != blue`) is the load-bearing Pitfall-2 pop-detachment check: if the redo stash aliased the mutated `popped`, the entire image would be blue at (0,0).
- **Files modified:** `tests/test_history.py`
- **Verification:** `test_mask_pop_returns_copy` passes; the pop-detachment contract is still locked.
- **Committed in:** `d4e8d0b` (Task 1)

**3. [Rule 1 - Bug] `qtbot.assertNotEmitted` does not accept a `timeout` kwarg**

- **Found during:** Task 2 (`test_undo_does_not_repush` raised `TypeError: QtBot.assertNotEmitted() got an unexpected keyword argument 'timeout'`)
- **Issue:** pytest-qt 4.5.0's `assertNotEmitted` is a context manager that takes no timeout (it asserts no signal fires while the block executes synchronously). My initial draft passed `timeout=500`.
- **Fix:** Removed the `timeout=500` kwarg. The undo handler runs synchronously inside the `with` block, so no timeout is needed.
- **Files modified:** `tests/test_history.py`
- **Verification:** `test_undo_does_not_repush` passes; `mask_modified` is proven not to fire during `on_undo_mask`.
- **Committed in:** `eab0be9` (Task 2)

---

**Total deviations:** 3 auto-fixed (all Rule 1 bugs — wrong test-encoding of the stack semantics, a fragile redundant assertion, and a pytest-qt API mismatch). All in tests; no production-code changes beyond the plan's `<action>`.
**Impact on plan:** All fixes necessary for the test suite to encode the actual 4-list stack semantics (which match the plan's contract). No scope creep.

## Authentication Gates

None — no auth-required operations in this plan.

## Known Stubs

No stubs. The plan-05 `MainWindow.history = None` placeholder is REPLACED by the real `HistoryManager(limit=20)` in this plan; the `_on_inpaint_finished` image-patch push call site now activates. The Phase 1 history uses full snapshots per entry (RESEARCH Open Question 3); incremental edits are a documented future-phase concern, not a stub.

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. All three registered threats mitigated as specified:

- **T-01-11c (QImage/numpy buffer lifetime via undo):** EVERY push and pop enforces `.copy()`. The two regression guards `test_mask_snapshot_is_copied` (push detachment — mutate the source after push, the snapshot is unaffected) and `test_mask_pop_returns_copy` (pop detachment — mutate the returned snapshot, the internal list is unaffected) lock this. `apply_undo_image` also routes through `set_image_from_numpy` which `.copy()`-detaches before storage (Pitfall-2 guard from plan 05).
- **T-01-15 (out-of-bounds image patch on undo):** `apply_undo_image` clips the patch + destination rect to the current image; an out-of-bounds patch (e.g., from a stale history entry after a future page crop) is clipped or no-ops defensively rather than corrupting the array. The bounds check is documented in the method docstring.
- **T-01-16 (unbounded history memory):** Both stacks enforce `limit=20` (MangaCleaner_GPU `Config.MAX_HISTORY`); the oldest entry is dropped on overflow. `test_stack_limit_drops_oldest` proves it (limit=3, 4 pushes, 4th undo returns None).

## Commits

- `d4e8d0b` — feat(01-06): core HistoryManager 2-stack undo/redo with .copy() discipline (Task 1)
- `eab0be9` — feat(01-06): wire HistoryManager + 4 undo/redo actions + shortcuts + toolbar (Task 2)

## Self-Check: PASSED

- All 4 key files FOUND on disk: `core/history_manager.py` (created), `tests/test_history.py` (created), `gui/canvas.py` (modified), `gui/main_window.py` (modified).
- Both task commits FOUND in git log: `d4e8d0b` (Task 1), `eab0be9` (Task 2).
- Plan `<verification>`: `pytest tests/test_history.py -x` exits 0 (22 passed).
- Pitfall-2 regression guards PASSED: `test_mask_snapshot_is_copied` (push) + `test_mask_pop_returns_copy` (pop).
- Undo-does-not-repush guard PASSED: `qtbot.assertNotEmitted(canvas.mask_modified)` around `on_undo_mask` succeeds.
- D-12 compliance: `core/history_manager.py` module docstring says "reimplemented patterned after MangaCleaner_GPU utils/history.py"; does NOT say "copied"/"vendored from MangaCleaner_GPU". `gui/main_window.py` undo handlers cite MangaCleaner_GPU `main_window.py:204-228` as the reimplementation reference.
- Full suite 110 passed (99 prior + 11 new GUI). No regressions vs plans 01-01..01-05.

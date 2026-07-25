---
phase: 02-cleaning-output-batch
plan: 02
subsystem: gui-state
tags: [mask-persistence, d-11, page-navigation, data-model, pyqt, tdd, pitfall-2]
requires:
  - Phase 1 EditorCanvas mask layer (set_mask/get_mask/has_mask/has_mask_content)
  - Phase 1 mask_to_numpy_binary serializer (core/mask_editor.py)
  - ImageFile.mask slot (core/image_file.py — already present, unused for persistence)
provides:
  - ImageFile.has_mask_content (D-03 mask-content gate for the data-model slot, consumed by Plan 03 Batch Clean)
  - MainWindow._last_page_index field + on_page_selected 4-step D-11 seam (save outgoing -> reset_history -> set_image -> restore incoming)
  - tests/test_gui_batch.py (the Phase 2 FLOW-03 GUI wiring suite — helpers + 3 mask-persistence tests)
affects:
  - Plan 02-03 (Batch Detect writes per-page masks into ImageFile.mask; Batch Clean reads them back via has_mask_content — both depend on this seam)
  - Plan 02-04 (MUST NOT re-declare MainWindow._last_page_index; adds the T-02-05 navigation-disable while _op_running)
tech-stack:
  added: []
  patterns:
    - "OUTGOING index captured via a stored field, NOT _current_page_index() — select_path mutates current_path BEFORE on_page_selected runs (PATTERNS file 4a)"
    - ".copy() at every ImageFile.mask <-> canvas buffer boundary (Pitfall 2 / T-02-04)"
    - "has_mask_content reuses mask_to_numpy_binary — no hand-rolled alpha scan (RESEARCH §Code Examples)"
    - "4-step on_page_selected seam: save outgoing -> reset_history -> set_image -> restore incoming"
key-files:
  created:
    - tests/test_gui_batch.py
  modified:
    - manga_ai_studio/core/image_file.py
    - manga_ai_studio/gui/main_window.py
decisions:
  - "OUTGOING page index is read from a stored _last_page_index field, NOT _current_page_index(): file_table.select_path (called in _set_pages line 555) mutates current_path BEFORE on_page_selected (line 556) runs, so _current_page_index() already returns the INCOMING page by the time the seam needs the OUTGOING one (PATTERNS file 4a note)."
  - "Boundary .copy() is applied at BOTH the OUTGOING save (canvas.get_mask().copy()) AND the INCOMING restore (image_file.mask.copy() into set_mask) — belt-and-suspenders, since set_mask also copies internally at canvas.py:305; the OUTGOING .copy() is the load-bearing one and what test_mask_persistence_uses_copy asserts on."
  - "has_mask_content imports mask_to_numpy_binary INSIDE the method (lazy) rather than at module top — keeps the dataclass module import-light and avoids circular-import risk if mask_editor ever needs image_file later."
  - "The T-02-05 write/write race mitigation (disable page-switch while _op_running) is explicitly deferred to Plan 04 — it touches file_table interaction which is not in this plan's files_modified. A code comment flags the deferral inside on_page_selected."
  - "_last_page_index is assigned at the END of on_page_selected (after the restore) so the NEXT navigation captures THIS page as its outgoing snapshot."
metrics:
  duration: 4 min
  completed: 2026-07-25
  tasks: 2
  files: 3
status: complete
---

# Phase 02 Plan 02: Per-Page Mask Persistence (D-11) Summary

Lifted mask state out of the Phase 1 canvas (which held one mask for the current page only and discarded it on every page switch) onto `ImageFile.mask` via a 4-step `on_page_selected` seam, making masks survive page navigation — the central data-model change that makes the two-stage detect → review → clean batch workflow possible (FLOW-03 / D-11).

## What Was Built

**`manga_ai_studio/core/image_file.py`** (modified) — added the D-03/D-11 mask-content gate on the data model:

- `ImageFile.has_mask_content(self) -> bool`: returns `False` when `self.mask is None or self.mask.isNull()`, else `bool(mask_to_numpy_binary(self.mask).any())`. Reuses the Phase 1 serializer exactly (no hand-rolled alpha scan — `.any()` appears exactly once in the module, inside this method; no `constBits`). Imports `mask_to_numpy_binary` lazily inside the method to keep the dataclass module import-light. Mirrors `EditorCanvas.has_mask_content` (canvas.py:348) but operates on the persisted slot rather than the live canvas buffer. Consumed by Plan 03 Batch Clean's D-03 empty-mask gate.

**`manga_ai_studio/gui/main_window.py`** (modified) — the D-11 seam:

- `MainWindow._last_page_index: int | None` instance field, initialized to `None` in `__init__`. Captures the OUTGOING page index for the next `on_page_selected` call. The load-bearing insight: `_set_pages` calls `file_table.select_path(...)` (line 555) BEFORE `on_page_selected(...)` (line 556), so by the time `on_page_selected` runs, `_current_page_index()` already returns the INCOMING page — the OUTGOING index MUST come from this stored field.
- `MainWindow.on_page_selected` rewritten as the 4-step seam:
  1. **Persist OUTGOING** — `outgoing_idx = self._last_page_index`; if it is in range and `canvas.has_mask()` is True, `self.image_files[outgoing_idx].mask = self.canvas.get_mask().copy()` (MANDATORY `.copy()` — Pitfall 2 / T-02-04).
  2. **`reset_history()`** — unchanged from plan 06; undo stays per-page (only the mask is lifted out).
  3. **`set_image_from_path(path)`** — unchanged; on failure shows the "Couldn't open file" warning and returns.
  4. **Restore INCOMING** — `incoming_idx = self._current_page_index()` (now correct, current_path is the incoming page); if it is in range and the persisted mask is non-None/non-null, `self.canvas.set_mask(self.image_files[incoming_idx].mask.copy())` (boundary `.copy()` is belt-and-suspenders; set_mask also copies at canvas.py:305).
  5. Unchanged tail (`setWindowTitle`, `fit_to_window`, `_add_recent_file`, `_refresh_status_bar`), followed by `self._last_page_index = self._current_page_index()` so the NEXT navigation captures THIS page as outgoing. A comment flags the T-02-05 race-disable deferral to Plan 04.

**`tests/test_gui_batch.py`** (new) — the Phase 2 FLOW-03 (D-11) GUI wiring suite. Copies the Phase 1 helpers `_make_window` / `_open_page` / `_paint_mask_on_canvas` verbatim from `tests/test_inpainting/test_inpaint_gui.py:43-83` (per PATTERNS file 7), adds a `_load_two_pages` helper for multi-page navigation, and defines 3 `@pytest.mark.gui` tests:
- `test_on_page_selected_persists_outgoing_mask` — paint mask on page_a, navigate to page_b, assert `image_files[0].mask is not None` (seam step 1).
- `test_mask_survives_navigation` — paint mask on page_a, navigate to page_b and back to page_a, assert `image_files[0].mask is not None` AND `canvas.has_mask()` is True (seam step 4 — the crux).
- `test_mask_persistence_uses_copy` — Pitfall-2 regression guard: paint mask on page_a, navigate away (persisting), snapshot the stored bytes, navigate back and `clear_mask()` the canvas, assert the stored `image_files[0].mask` bytes are byte-identical to the snapshot.

## Task Results

| Task | Name | Commit | Key Files |
| ---- | ---- | ------ | --------- |
| 1 | Create test_gui_batch.py test suite (RED) | 95bdd29 | tests/test_gui_batch.py |
| 2 | Implement ImageFile.has_mask_content + on_page_selected D-11 seam (GREEN) | 22029fc | manga_ai_studio/core/image_file.py, manga_ai_studio/gui/main_window.py |

## Verification

- `python -m pytest tests/test_gui_batch.py -x` → **3 passed** (RED before Task 2: `assert None is not None` on the outgoing mask).
- `python -m pytest tests/test_inpainting/test_inpaint_gui.py -x` → **16 passed** (no Phase 1 regression — single-page mask handling unchanged when `ImageFile.mask` stays None).
- `python -m pytest tests/` → **140 passed** (full suite green).
- Acceptance grep checks all satisfied: `def has_mask_content` at image_file.py:93; `mask_to_numpy_binary` reused at image_file.py:110; `.any()` appears exactly once (line 110, inside has_mask_content) with no `constBits`; `_last_page_index` has 5 occurrences (init + outgoing read + tail write + 2 docstring/comment mentions); `get_mask().copy()` OUTGOING save at main_window.py:623; `.mask.copy()` INCOMING restore at main_window.py:652.

## TDD Gate Compliance

- RED gate: `test(02-02): add failing GUI suite for D-11 mask persistence` (95bdd29) — suite was RED via `AssertionError: outgoing page's ImageFile.mask must be non-None after navigation`.
- GREEN gate: `feat(02-02): persist per-page masks across navigation (D-11 seam)` (22029fc) — all 3 new tests green, Phase 1 GUI suite still green.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed (the test helpers copied verbatim from Phase 1 worked without modification, and the seam implementation matched the plan's step-by-step action precisely). No architectural deviations (Rule 4); no auth gates.

## Known Stubs

None. Both implementation edits are fully realized: `has_mask_content` returns a real boolean computed from `mask_to_numpy_binary`, and the `on_page_selected` seam saves and restores masks through the `ImageFile.mask` slot with the mandated `.copy()` discipline at every boundary.

## Threat Flags

None. The implemented seam introduces no security surface beyond what the plan's `<threat_model>` enumerated. T-02-04 (buffer aliasing / Pitfall 2) is mitigated by the boundary `.copy()` at both the OUTGOING save and the INCOMING restore, regression-guarded by `test_mask_persistence_uses_copy`. T-02-05 (concurrent write/write during batch) is mitigated by deferral: this plan implements the GUI-thread write only and adds a code comment flagging that Plan 04 will disable page-switch while `_op_running`; no concurrent write is possible until Plan 04 wires the batch worker. No new network endpoints, auth paths, or trust-boundary schema changes were introduced.

## Self-Check: PASSED

- [x] `tests/test_gui_batch.py` exists (FOUND)
- [x] `manga_ai_studio/core/image_file.py` modified (FOUND — has_mask_content at line 93)
- [x] `manga_ai_studio/gui/main_window.py` modified (FOUND — _last_page_index at line 97, on_page_selected seam at lines 568-667)
- [x] Commit 95bdd29 exists in git log (FOUND)
- [x] Commit 22029fc exists in git log (FOUND)

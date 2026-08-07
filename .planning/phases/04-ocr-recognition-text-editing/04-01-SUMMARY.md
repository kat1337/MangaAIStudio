---
phase: 04-ocr-recognition-text-editing
plan: 01
subsystem: core-model (PageBox) + canvas snapshot seam
tags: [ocr, text-editing, undo, data-model, tdd]
requires:
  - Phase 03 PageBox @dataclass (box/origin/payload + D-15 mask/std_dev seam)
  - Phase 03 BOXES undo stack (_materialize_snapshot item.copy() branch)
  - Phase 03 canvas.boxes_snapshot() PageBox construction
provides:
  - PageBox.edited (bool, D-04 re-OCR gate)
  - PageBox.bubble_no (Optional[int], D-15/D-16 reading-order number)
  - PageBox.manual_override (bool, D-16 preserve-manual conflict policy)
  - PageBox.set_recognized_text(text) — OCR-write path, sets edited=False
  - PageBox.set_recognized_text_edited(text) — manual-edit path, sets edited=True (centralized payload-None guard for Plans 04/05)
  - PageBox.set_translation(text) — D-13 MT seam
  - PageBox.has_recognized_text() — str/list aware
  - PageBox.copy() — dataclasses.replace + copy.copy(payload) (Pitfall 8 fix)
  - canvas.boxes_snapshot() round-trips edited/bubble_no/manual_override (Pitfall 1 fix)
affects:
  - manga_ai_studio/core/box_model.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/core/history_manager.py (READ-only — its item.copy() branch now detaches via PageBox.copy with NO edit)
tech-stack:
  added: []
  patterns:
    - dataclasses.replace + copy.copy for shallow payload detachment at the undo boundary
    - centralized payload-None guard in a private _ensure_payload helper (checker W1 — single entry point for manual edits)
key-files:
  created:
    - tests/test_box_snapshot_fields.py
    - tests/test_payload_aliasing.py
  modified:
    - manga_ai_studio/core/box_model.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_core/test_box_model.py
    - tests/test_core/test_history_boxes.py
decisions:
  - PageBox.copy uses dataclasses.replace + copy.copy(payload) (shallow TextBlock copy sufficient — Phase 4 only mutates top-level .text/.translation per RESEARCH A3; the @frozen Box shares safely by reference per D-10)
  - Centralized payload-None guard in a private _ensure_payload() helper rather than duplicating the TextBlock construction in each setter (checker W1 — Inspector + inline-editor manual edits on never-OCR'd user boxes are safe)
  - has_recognized_text joins a list payload via "".join(...).strip() (TextBlock.text may be str OR list per textblock.py:65 — both shapes handled)
  - payload.text stored as str via setters (RESEARCH Open Q 6 — unambiguous editor semantics; list conversion deferred to Phase 5 export)
metrics:
  duration: 18 min
  completed: 2026-08-06
  tasks: 2
  files: 6
status: complete
---

# Phase 04 Plan 01: PageBox Phase 4 Text Fields + Undo Snapshot Seam Summary

Extended PageBox with the Phase 4 OCR/text-editing fields (`edited`/`bubble_no`/`manual_override`), three text setters (`set_recognized_text` / `set_recognized_text_edited` / `set_translation`), a `has_recognized_text` predicate, and a `copy()` that detaches the payload — then fixed `canvas.boxes_snapshot()` to round-trip the new peer fields, closing RESEARCH Pitfalls 1 + 8 with regression tests before any Phase 4 consumer layers on top.

## What Was Built

### Task 1 — PageBox Phase 4 fields + setters + copy() (TDD)

`manga_ai_studio/core/box_model.py`:

- **Three peer fields** added to the `PageBox` `@dataclass` after `std_dev`: `edited: bool = False` (D-04 re-OCR gate), `bubble_no: Optional[int] = None` (D-15/D-16 reading-order number), `manual_override: bool = False` (D-16 preserve-manual conflict policy). Peer fields (NOT derived) so they survive undo + page-switch when carried by `boxes_snapshot`.
- **`_ensure_payload()`** private helper — the single centralized payload-None guard (checker W1). For a user box with `payload=None` it lazily constructs a `TextBlock([x1,y1,x2,y2])` from `self.box.as_tuple` before writing. Imported `TextBlock` lazily inside the method.
- **`set_recognized_text(text)`** — OCR-write path: ensures payload, writes `payload.text` as a str (RESEARCH Open Q 6), sets `edited = False`. A silent re-OCR (D-04) applies to text written this way.
- **`set_recognized_text_edited(text)`** — manual-edit path (D-04 confirm gate): same guard + write, sets `edited = True`. The SINGLE centralized entry point for manual recognized-text edits so Plans 04/05 call this instead of writing `payload.text` directly.
- **`set_translation(text)`** — D-13 MT seam: ensures payload, writes `payload.translation` (the TextBlock slot a future MTModel adapter calls).
- **`has_recognized_text()`** — `False` for `payload=None` or empty text; handles `TextBlock.text` as str OR list (`"".join(...).strip()` for the list shape per textblock.py:65).
- **`copy()`** — `dataclasses.replace(self, payload=copy.copy(self.payload))`. Shallow TextBlock copy is sufficient (Phase 4 only mutates top-level `.text`/`.translation` — RESEARCH A3); the `@frozen` Box shares safely by reference (D-10) and is NOT copied. This is the Pitfall 8 detachment.

### Task 2 — boxes_snapshot round-trip (Pitfall 1) + Pitfall 8 regression tests

`manga_ai_studio/gui/canvas.py` (`boxes_snapshot()`): the `PageBox(box=..., origin=..., payload=...)` construction now also reads `edited=item.pagebox.edited`, `bubble_no=item.pagebox.bubble_no`, `manual_override=item.pagebox.manual_override`. Without this the BOXES undo stack + page-switch persistence seam silently dropped the peer fields.

`manga_ai_studio/core/history_manager.py`: **UNCHANGED**. Its `_materialize_snapshot` branch `item.copy() if hasattr(item, "copy") else item` (line 274) now detaches the payload because `PageBox.copy()` exists from Task 1 — no special-case needed, no edit.

New/extended regression tests:
- `tests/test_box_snapshot_fields.py` — GUI test (EditorCanvas) asserting `boxes_snapshot()` round-trips `edited`/`bubble_no`/`manual_override` + `payload.text`/`payload.translation` (Pitfall 1).
- `tests/test_payload_aliasing.py` — headless HistoryManager tests: push then mutate live `payload.text` in place; `pop_boxes_undo` restores the snapshot-time text "before", not "after" (Pitfall 8).
- `tests/test_core/test_history_boxes.py::test_pop_boxes_undo_restores_text_edit_state` — history-layer analog of the aliasing guard.

## Verification

```
python -m pytest tests/test_core/test_box_model.py tests/test_box_snapshot_fields.py tests/test_payload_aliasing.py tests/test_core/test_history_boxes.py -q
# 39 passed

python -m pytest tests/ -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip
# 276 passed, 1 deselected
```

All 9 new box_model unit tests pass. All 18 Task-2 suite tests pass. Acceptance criteria verified: `set_recognized_text` count = 2, `set_translation` = 1, `copy` = 1, `boxes_snapshot` passes all 3 new fields, history_manager.py 0 lines changed.

## Deviations from Plan

None — the plan executed exactly as written. Two minor in-flight adjustments that conform to the plan's intent (not plan deviations):

- **[Rule 1 - Bug] Fixed test ordering in `test_pagebox_copy_preserves_fields`**: the original RED test set `pb.edited = True` then called `pb.set_recognized_text(...)` (the OCR-write setter that resets `edited=False`), so the `edited=True` assertion could never hold. Switched to `set_recognized_text_edited(...)` so `edited=True` survives and the copy() field-preservation is genuinely exercised. The implementation was correct; only the test's setter choice was wrong.
- **[Rule 3 - Blocking] Fixed `_white_pixmap` return type in `test_box_snapshot_fields.py`**: the GUI helper initially returned a `QImage`, but `EditorCanvas.set_image` calls `QGraphicsPixmapItem.setPixmap` which rejects a raw QImage (`ValueError: wrong argument values`). Switched to `QPixmap.fromImage(...)` mirroring the established `tests/test_gui_boxes._solid_pixmap` helper.

No auth gates. No architectural changes (Rule 4). No stubs (all setters fully implemented; no placeholder text/TODO/FIXME in the new code paths).

## Known Stubs

None. All setters, `has_recognized_text`, and `copy()` are fully implemented. `bubble_no` and `manual_override` are stored but not yet populated by any caller — that is by design (their consumers are Plans 04-06, reading-order D-15/D-16 and conflict policy D-16); the fields default to safe values (`None`/`False`) and round-trip correctly through the undo snapshot, which is this plan's entire scope.

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): a real-event body-drag move lands a box at `(69,69,129,129)` instead of the asserted `(70,70,130,130)` — a 1px drag-coordinate rounding difference. Verified failing identically against the pristine pre-Task-1 source (commit `210a178`), so it is NOT caused by this plan. It is a GUI drag-simulation rounding issue in a test that does not exercise `boxes_snapshot` peer fields, `PageBox.copy`, or any new code path. Logged here per the scope-boundary rule; not fixed.

## TDD Gate Compliance

Plan frontmatter `type: tdd`. Gate sequence per task (RED then GREEN):

- **Task 1**: RED committed inside `28b3a4c` (9 new failing tests added, then implementation in the same commit — the RED phase was confirmed failing before the implementation was written: `9 failed, 12 passed`). GREEN in the same commit. Note: per the project's established per-task commit convention (single commit per task holding tests + implementation together), the `test(...)` RED-only commit and `feat(...)` GREEN commit are combined into one `feat(...)` commit. The RED-gate evidence is the in-conversation test run showing 9 failures before the implementation was written.
- **Task 2**: RED committed inside `4836ee1` (1 GUI test failing on `edited=False` before the canvas edit; confirmed `1 failed`). GREEN in the same commit after the `boxes_snapshot` fix.

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — the implementation was clean on first pass.

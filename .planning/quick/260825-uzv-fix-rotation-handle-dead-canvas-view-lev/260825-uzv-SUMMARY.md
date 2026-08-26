---
phase: quick-260825-uzv
plan: 01
subsystem: gui-canvas
tags: [rotation, sfx-editing, mouse-dispatch, regression-tests]
requires: [quick-260824-viq rotation state machine (_begin_rotation/_advance_rotation/_commit_rotation)]
provides: [RotationHandle-aware view-level press dispatch (_topmost_box_hit)]
affects: [EditorCanvas.mousePressEvent box branch, Alt-gated paint carve-out]
tech-stack:
  added: []
  patterns: [press-dispatch hit-test helper mirroring _box_item_at with one added isinstance branch]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_sfx_editing.py
decisions:
  - New _topmost_box_hit helper instead of widening _box_item_at — the double-click contract (visual-only exclusion) is preserved byte-identical
  - Dispatch calls _begin_rotation directly (mirrors how _begin_resize bypasses the handle's own press handler); the hook closure adds only a weakref hop
  - RotationHandle carve-out placed in BOTH the non-paint branch and the Alt-gated paint sub-branch (D-15 consistency)
metrics:
  duration: ~14 min
  completed: 2026-08-26
status: complete
actuals:
  tokens: 46000
  tasks: 2
  commits: 2
---

# Quick Task 260825-uzv: Fix Rotation Handle Dead Canvas View-Level Press — Summary

**One-liner:** View-level press dispatch now recognizes a visible RotationHandle via a new `_topmost_box_hit` helper before any selection-clear, so pressing/dragging the rotate circle arms and commits `style.rotation_deg` in both Move and Alt+paint modes.

## What Was Built

- **`_topmost_box_hit(scene_pos)`** (`canvas.py`, beside `_box_item_at`): verbatim copy of `_box_item_at`'s identity-transform z-ordered query plus one added `isinstance(candidate, RotationHandle)` match. `_box_item_at` itself untouched — its docstring now points readers at the new helper; `mouseDoubleClickEvent` keeps its visual-only contract.
- **Non-paint branch:** a RotationHandle press resolves the parent BoxItem (isinstance assert, mirroring `_begin_resize`) and calls `_begin_rotation(parent_item, scene_pos)` + accept + return BEFORE the empty-canvas `_clear_selection()` fall-through that previously killed the handle.
- **Alt-gated paint sub-branch:** identical carve-out beside the CornerHandle branch (D-15) so Alt+BRUSH on the circle rotates instead of starting a create-box drag.
- **Untouched by design:** no-Alt paint fall-through (MASK-06), §12d empty-canvas selection-clear, inline-editor guard in `_begin_rotation`, RedetectHandle handling.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Dispatch-path regression tests (RED) | 6d848ec | tests/test_gui_sfx_editing.py |
| 2 | RotationHandle-aware press dispatch (GREEN) | 36cbd30 | manga_ai_studio/gui/canvas.py |

## Verification

- RED gate: Test 1 (handle press arms rotation) and Test 3 (Alt+BRUSH parity) failed pre-fix reproducing the reported symptom; Test 2 (empty-canvas still clears) passed.
- GREEN gate: all three dispatch tests pass through the REAL `canvas.mousePressEvent` entry point with synthetic QMouseEvents anchored on delivered state (`_rotating_box`, `isSelected`, committed `rotation_deg`).
- File verify: `pytest tests/test_gui_sfx_editing.py tests/test_gui_boxes.py -q` → **248 passed**.
- Full suite: `pytest -q` → **1143 passed, 0 failed** (baseline 1138 + new dispatch tests).

## Deviations from Plan

None — plan executed exactly as written. One mid-task editor slip (an edit briefly dropped the `if self.current_tool in PAINT_TOOLS:` line) was caught and restored before verification; net diff contains only the planned changes.

Note: `test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` failed once during the two-file verify run but passed on both old code and new code in repeated isolation runs (5/5) and in the final verify — a render-timing flake in a viewport pixel-grab test, unrelated to this change (out of scope per the scope boundary).

## Known Stubs

None.

## Threat Flags

None — local desktop GUI event routing only; no new network/auth/file surface (T-QZV-01 accepted as planned).

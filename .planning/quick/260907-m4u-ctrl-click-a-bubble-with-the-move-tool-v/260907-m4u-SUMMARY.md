---
phase: quick-260907-m4u
plan: 01
subsystem: gui
tags: [clipboard, ctrl-click, move-tool, detected-text, canvas-dispatch, ocr]
requires: [text_renderer.current_focus_text, PageBox.payload (TextBlock), canvas.ocr_requested emitter precedent, MainWindow._on_ocr_grab_finished, MASK-06 paint-tool dispatch]
provides: [text_renderer.detected_text(pb), EditorCanvas.copy_text_requested Signal(str), MainWindow._on_box_text_copy_requested, Move-tool Ctrl+click copy interaction]
affects: [EditorCanvas.mousePressEvent non-paint BoxItem arm, Move tool tooltip (tools_strip), OS clipboard]
tech-stack:
  added: []
  patterns: [dumb-emitter canvas signal (ocr_grab.py:19 discipline), handler-mirrors-_on_ocr_grab_finished empty-rule, defensive payload read shaped on current_focus_text]
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/text_renderer.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/tools_strip.py
    - tests/test_gui_boxes.py
    - tests/test_gui_ocr_grab.py
decisions:
  - "detected_text(pb) reads ONLY payload.text — never falls back to translation (the user asked for the DETECTED text; current_focus_text stays the D-04 display rule with translation preferred)"
  - "The signal carries the text EVEN WHEN EMPTY — the canvas stays dumb and MainWindow decides the empty feedback ('No text recognized'), exact grab-handler parity"
  - "Ctrl branch sits BEFORE the Shift check in the BoxItem arm — Ctrl wins over Shift on a Move-tool box press; proven by the Ctrl+Shift battery case"
  - "CornerHandle/RotationHandle hits never copy (they return before the BoxItem arm) — battery-locked with a Ctrl+click-on-handle case asserting resize armed, zero emissions"
  - "Select-without-drag on copy: if not item.isSelected(): _deselect_box() + setSelected(True); _moving_box stays None — battery-locked"
metrics:
  duration: ~13 min
  completed: 2026-09-07
  tasks: 3
  commits: 4
actuals:
  tokens: 4700
  tasks: 3
  commits: 4
status: complete
---

# Quick Task 260907-m4u — Ctrl+click a bubble with the Move tool copies its detected text Summary

With the Move tool (V) active, Ctrl+left-click on a bubble copies that bubble's OCR-recognized (DETECTED) text to the OS clipboard and flashes "Copied N chars to clipboard"; empty-text boxes write nothing and show "No text recognized" — the canvas emits, MainWindow owns the clipboard.

## Tasks Completed

| Task | Name | Commits | Files |
| ---- | ---- | ------- | ----- |
| 1 | Canvas dispatch — detected_text helper + copy_text_requested signal + Ctrl branch | aad0279 (RED), cf32b89 (GREEN) | manga_ai_studio/gui/text_renderer.py, manga_ai_studio/gui/canvas.py, tests/test_gui_boxes.py |
| 2 | MainWindow wiring — clipboard handler + connection + Move tooltip | 96272b3 (RED), be7cf11 (GREEN) | manga_ai_studio/gui/main_window.py, manga_ai_studio/gui/tools_strip.py, tests/test_gui_ocr_grab.py |
| 3 | Full-suite regression run (pinned interpreter) | (run-only, no commit) | tests/ |

## What Was Built

**Task 1 — Canvas side.** `detected_text(pb)` in text_renderer.py directly after `current_focus_text`: same defensive shape (None payload → "", missing attr → "", list → join+strip, else `str().strip()`) but reading ONLY `payload.text` — translation is never read. `EditorCanvas.copy_text_requested = Signal(str)` declared beside the other canvas signals with the dumb-emitter docstring (never touches the OS clipboard). The dispatch branch sits inside `mousePressEvent`'s non-paint `isinstance(item, BoxItem)` arm BEFORE the Shift check, gated on `current_tool == ToolMode.MOVE` AND ControlModifier: select-without-drag (`_deselect_box()` + `setSelected(True)` when unselected), `emit(detected_text(item.pagebox))`, accept+return. `_press_at` gained a keyword-only `ctrl` param (call sites unchanged).

**Task 2 — MainWindow side.** `_on_box_text_copy_requested(text)` beside `_on_ocr_grab_finished`, mirroring it verbatim in structure: empty/whitespace → `status_bar_left.setText("No text recognized")`, NO clipboard write; non-empty → `QGuiApplication.clipboard().setText(text)` + `_show_transient_status(f"Copied {len(text)} chars to clipboard")`. Docstring records the deliberate OS-clipboard carve-out (in-app Ctrl+C/V box-duplication scoping) and the ocr_grab.py:19 dumb-emitter discipline. Connected beside the other canvas signal subscriptions. The Move tool tooltip becomes "Move/Pan tool (V) — Ctrl+click a bubble to copy its detected text." (brush-family Alt-clause pattern).

**Task 3 — Full-suite regression:** 1303 passed, 0 failed (see Verification).

## Verification Results

- Task 1 (RED): 7 new tests failed on the missing signal/helper; (GREEN): `tests/test_gui_boxes.py` 234 passed + 1 known flake (see below) — all 7 new battery cases green, pre-existing dispatch untouched
- Task 2 (RED): 3 new tests failed (no handler / no connection); (GREEN): `tests/test_gui_ocr_grab.py` + `tests/test_gui_boxes.py` + `tests/test_gui_tools_strip.py` = **282 passed, 0 failed**
- Task 3: full suite `pytest -q` = **1303 passed, 0 failed** in 3:55 (baseline 1293 total + 10 new tests; even the known flake passed this run)

**Known pre-existing flake (not a regression):** during the Task 1 GREEN run, `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` failed once (viewport-grab pixel 206 vs 200 threshold — the Qt viewport-grab flake documented at baseline e1c0c43). It passes in isolation and passed in the later Task 2 and Task 3 runs. Tolerated per the baseline contract.

## Behavior Battery (Task 1 + Task 2, 10 new tests)

- `detected_text`: recognized str verbatim ("ハロー"), payload-None → "", list `["a","b"]` → "ab", translation-set-but-empty → "" (never leaks), whitespace-only → ""
- Ctrl+click (MOVE) on OCR'd box: emits exactly "copied text", box selected, `_moving_box` stays None (no drag armed)
- Ctrl+Shift+click: Ctrl wins over Shift (emits; toggle never runs)
- Ctrl+click on payload-None box: emits ""
- Plain click (no Ctrl): emits nothing, arms the move drag (today's behavior intact)
- Ctrl+click on CornerHandle: no emission, resize armed (handles are gestures, never copies)
- Ctrl+click under RECTANGLE (paint tool): no emission (MASK-06 — Alt stays the sole box modifier there)
- Handler: non-empty → real OS clipboard + transient status; ""/whitespace → sentinel survives + "No text recognized"; signal emission alone drives the clipboard (wiring proof)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Model Notes

- T-m4u-01 (Information Disclosure, low, accept): clipboard write lands in `_on_box_text_copy_requested` exactly as planned — same exposure class as the OCR Grab copy; no new trust boundary.
- T-m4u-02 (Tampering, low, mitigate): the dispatch branch is strictly gated on `ToolMode.MOVE` + ControlModifier inside the existing BoxItem arm; the Task 1 battery proves plain-click/Shift/handle/paint dispatch byte-identical (5 regression cases in the 10-test battery).

## Self-Check: PASSED

- All 4 commits present on master (aad0279, cf32b89, 96272b3, be7cf11); verified via `git log`.
- All 6 modified files present in the working tree; full suite green (1303 passed).

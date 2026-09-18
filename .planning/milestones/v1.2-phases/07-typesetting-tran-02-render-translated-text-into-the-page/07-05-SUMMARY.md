---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 05
subsystem: ui (typesetting — TRAN-02)
tags: [inspector, styling, mixed-state, tategaki, font-size-actions, d05, d10, d13, d16]
requires: [07-01 (TextStyle + renderer + overlay + bake), 07-02 (multi-select), 07-03 (vertical path + effects), 07-04 (style persistence)]
provides: [inspector-style-section, common-value-mixed, live-vertical-toggle, font-size-actions, canvas-bake-vertical-or]
affects: [inspector-panel, main-window, box-item, text-renderer, canvas]
tech-stack:
  added: []
  patterns:
    - "One class-scope Signal per commit-able control + WR-01 no-op guard (Shared Pattern 10) — extended to the D-05 styling section"
    - "The D-10 Mixed sentinel never leaves the widget layer (Pitfall 7 / T-07-11): every guard drops PartiallyChecked / 'Mixed' / sentinel-0 before emitting; commits always carry real values"
    - "ONE style commit = ONE before-snapshot + ONE overlay refresh + ONE boxes_modified emission with a recorded op name (06-WR-01 — 'style change' / 'font size')"
    - "The render vertical flag OR (style.vertical | payload.vertical) shared VERBATIM by box_item.refresh_text_overlay and bake_typeset_page — atomic canvas == bake flip (D-13, Pitfall 9)"
key-files:
  created:
    - tests/test_gui_inspector_styling.py
  modified:
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/text_renderer.py
    - tests/test_gui_boxes.py
decisions:
  - "The size spin 0 sentinel is dual-purpose per state: 'Auto' special text for a uniform box (D-15), 'Mixed' special text for a differing selection — the same widget value 0 never commits from the Mixed state (a no-op focus cycle on the sentinel is dropped) so the sentinel cannot persist (Pitfall 7)"
  - "A Mixed effect row's interaction falls back to the effect DEFAULTS for the fields the user did not explicitly change (enabling a mixed outline row writes the default 2px/#0b0b0e, not the sentinel 0) — the sentinel never becomes a style value"
  - "The vertical checkbox writes payload.vertical ONLY (the plan letter — the OR expression picks it up); style.vertical stays the model's own flag. The bake/overlay OR is the single source of the render mode"
  - "The size +/- actions convert an Auto-fit box to MANUAL at renderer.layout's used_font_size_px (rounded — A11); the converted size is deterministic so a test can precompute it"
  - "Style commits record the pending op name 'style change'/'font size' (06-WR-01) — the Ctrl+Z flash reads 'Undo: style change'; a side effect is the same transient commit flash the group ops already produce"
status: complete
metrics:
  duration: ~2.5h
  completed: 2026-08-11
  tests: 682 passed (669 prior + 13 new: 9 styling + 4 boxes)
actuals:
  tokens: 26345    # chars/4 over the realized diff (105,380 chars: 1918 added + 46 removed lines)
  tasks: 3
  commits: 3       # a20ca03, 1f28464, b8f8ee0 (plus this docs commit)
---

# Phase 7 Plan 5: Inspector Style section — common-value/Mixed styling, live Vertical checkbox, and font-size actions Summary

**One-liner:** the phase's user-facing styling surface — the Inspector's D-05 **Style section** (font family/style, size + Auto-fit, color, H/V alignment, outline/glow/shadow effects) with the D-10 **common-value/"Mixed" behavior** for multi-select (one override applies to ALL selected with ONE undoable snapshot, the sentinel never persists), the **live Vertical text checkbox** (D-13) that flips canvas AND bake to the 07-03 tategaki path atomically, and the **Increase/Decrease Font Size actions** (D-16, Ctrl+] / Ctrl+[) with Auto-fit→manual conversion.

## What Was Built

- **`gui/inspector_panel.py` (MOD, +900)** — the D-05 Style section below the text fields: "Style" 12px semibold muted header + 1px divider; **Font** (`QFontComboBox`, default Liberation Sans), **Style** (per-family `QComboBox` from `QFontDatabase.styles`, repopulated on font change), **Size** (`QSpinBox` 0..200 with the "Auto" sentinel at 0) + **Auto-fit** `QCheckBox` (checked → spin 0/disabled; unchecked → spin enabled at the current rendered size rounded), **Color** (24×24 swatch `QToolButton` → `QColorDialog`, the D-10 split `#e8e8ea`/`#9a9aa2` fill when mixed), **Align / Align V** combos, and **Outline / Glow / Shadow** rows (enable checkbox + 24×24 swatch + spin 0..10 / 0..20 / 0..10; a disabled checkbox greys the row). Seven new class-scope Signals (`style_font_changed`, `style_font_style_changed`, `style_size_changed`, `style_auto_fit_changed`, `style_color_changed`, `style_align_changed`, `style_effect_changed`) all WR-01-gated. **`load_multi_selection`** — the D-10 common-value/Mixed layer: combo "Mixed" entries, size-spin "Mixed" special text, split swatch, tri-state checkboxes (auto-fit/effects/vertical), per-box text fields disabled at N>1, the muted "Style edits apply to all {n} selected boxes." hint, extended empty-state copy. The vertical checkbox is LIVE (D-13 copy tooltip, `stateChanged` wiring with a tri-state guard).
- **`gui/main_window.py` (MOD, +336)** — `_inspector_style_commit` routes every styling signal through ONE apply-to-all commit: ONE before-snapshot (`boxes_snapshot()` with style forwarding), apply to EVERY selected `PageBox` via `dataclasses.replace` (fresh `TextStyle` — Pitfall 1), op name **"style change"** (new `canvas.set_pending_boxes_op_name`, 06-WR-01), ONE overlay refresh + ONE `boxes_modified` emit + multi-aware panel reload. `_on_canvas_selection_changed` is multi-aware (single → `load_box` with the overlay's rendered-size hint; N>1 → `load_multi_selection`). `_on_inspector_vertical_committed` applies `payload.vertical` to ALL selected with the same one-snapshot discipline. **`action_increase_font_size` (Ctrl+]) / `action_decrease_font_size` (Ctrl+[)** in the Text-menu Typesetting section after Load Translations…; `_on_font_size_delta` converts an Auto-fit box to MANUAL at its current rendered size first (A11), then ±1 px (floor 1), one snapshot, op name **"font size"**; `_refresh_action_states` gates (page_open + box_selected + not _op_running); `_undo_op_label` gains both op names.
- **`gui/box_item.py` (MOD)** — `refresh_text_overlay` computes `vertical = bool(style.vertical or payload.vertical)` — the SAME OR expression the bake uses, so a toggle flips canvas and bake atomically (Pitfall 9). `TypesetOverlayItem.set_content` pads the cached pixmap by `renderer.effect_padding(style)` (the 07-03 handoff — glow/shadow halos no longer clip on canvas; bake never clipped, now canvas ≡ bake).
- **`gui/text_renderer.py` (MOD)** — `bake_typeset_page` uses the same per-box OR expression (atomic canvas ≡ bake vertical flip, D-13).
- **`gui/canvas.py` (MOD, +10)** — `set_pending_boxes_op_name` (the 06-WR-01 setter pair for `take_pending_boxes_op_name`).
- **`tests/test_gui_inspector_styling.py` (NEW, 9 tests)** + **`tests/test_gui_boxes.py` (extended, +4)** — the full Task 1/2/3 battery below.

## Tasks Executed

| Task | Name | Result |
|------|------|--------|
| 1 (auto) | Inspector Style section — widgets, signals, QSS, empty-state (D-05) | 4 new styling tests pass; all 181 pre-existing box/inspector tests stay green |
| 2 (auto) | Mixed common-value state + apply-to-all commit routing (D-10, Pitfall 7) | 5 new Mixed tests pass; ONE emission / ONE Ctrl+Z per commit verified end-to-end; sentinel never persists |
| 3 (auto) | Live vertical checkbox + Size +/- actions + atomic vertical-flag wiring (D-13/D-16) | 4 new box tests pass; full suite **682 passed, 0 failed** (669 baseline + 13) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The vendored `TextBlock` is FALSY — a truthiness payload check silently dropped the vertical flag**
- **Found during:** Task 3 (the new vertical tests failed: a `payload.vertical=True` box rendered horizontal)
- **Issue:** the plan's OR expression spelling (`pb.payload.vertical if pb.payload else False`) treats the payload PRESENCE as truthiness — but the vendored `TextBlock` defines `__len__` and is falsy, so `if pb.payload` evaluated False even when a payload existed, and the vertical flag was dropped. Probed: `bool(payload)` → False with `payload.vertical` → True.
- **Fix:** the presence check is `is not None` (+ `getattr(..., "vertical", False)` so a bare marker payload — a string, per `test_boxes_snapshot_returns_pageboxes` — stays defensive) in all three OR sites (box_item, bake, `_style_rendered_size`). Documented in the bake docstring.
- **Files modified:** `manga_ai_studio/gui/box_item.py`, `manga_ai_studio/gui/text_renderer.py`, `manga_ai_studio/gui/main_window.py`
- **Commit:** b8f8ee0

**2. [Plan-driven test calibration] The panel-level commit tests needed post-commit reloads (the MainWindow's real cycle)**
- **Found during:** Task 1/2 test authoring
- **Issue:** the panel is a FOLLOWER — the WR-01 loaded-memory only reflects the applied state after the MainWindow reloads the panel post-commit. Panel-level tests that fired two no-op focus cycles without a reload saw the guard legitimately re-emit (the panel still held the OLD loaded values).
- **Fix:** the tests simulate the real reload (`load_box` with the applied style) between commits — matching the production selection-follower cycle; the WR-01 no-op assertions then hold.
- **Files modified:** `tests/test_gui_inspector_styling.py`
- **Committed in:** a20ca03, 1f28464

## Key Decisions

- **The size-spin 0 sentinel is state-dependent display** ("Auto" uniform / "Mixed" differing) and the same 0 NEVER commits from the Mixed state — the sentinel cannot persist (Pitfall 7, locked by `test_mixed_sentinel_never_persists`).
- **Mixed effect rows default the untouched fields** on interaction (enable-with-defaults) so a commit always carries real values.
- **The vertical toggle writes `payload.vertical` only** (plan letter); the OR expression is the single render-mode source read by both outputs — no divergence window (D-13).
- **`style change` / `font size` recorded op names** (06-WR-01) give the Ctrl+Z flash its name; the commit also flashes the transient status (the group-op mechanism's side effect).
- **Auto-fit→manual conversion uses `renderer.layout`'s rounded `used_font_size_px`** (A11) — deterministic, so the size-action tests precompute it.

## Verification

- `pytest tests/test_gui_inspector_styling.py tests/test_gui_boxes.py -q` → **194 passed**
- Full suite `pytest -q` → **682 passed, 0 failed** (600 baseline at phase start → 669 after plans 01-04 → 682 with this plan's 13 new)
- Grep gates: `rg "Coming soon" manga_ai_studio/gui/inspector_panel.py` → nothing (the D-13 tooltip is gone); `Ctrl+Shift+B`, `Ctrl+]`, `Ctrl+[` each appear exactly once in the main_window shortcut map (CR-14 single-binding, T-07-12)
- TDD gate: n/a — plan 07-05 is `type: execute` (no tdd tasks)

## Threat Surface

The changed files map onto the plan's threat model — no NEW surface beyond it:

| Threat ID | Disposition | Outcome |
|-----------|-------------|---------|
| T-07-11 (Tampering — Mixed commit path) | mitigate | The sentinel never leaves the widget layer: every guard drops PartiallyChecked / "Mixed" / sentinel-0 before emitting; commits carry real values applied via `dataclasses.replace` (never in-place); `test_mixed_sentinel_never_persists` walks every style's `to_dict()` |
| T-07-12 (Spoofing UI — Ctrl+] / Ctrl+[ / Ctrl+Shift+B) | mitigate | Conflict audit verified free (Ctrl+- is zoom-out); `test_size_plus_minus_actions` asserts each sequence on exactly ONE action |
| T-07-13 (DoS — per-mousemove style/effect re-render) | mitigate | Reposition stays setPos-only (RC-1, unchanged); the canvas overlay now pads by `effect_padding` at render time — no per-mousemove work added |

No threat flags.

## Known Stubs

None — every control is wired to its data source and exercised by the 13 new tests. The vertical OR is probed with a real CJK string (upright placements) on both the overlay and the bake; the effect halos render through the 07-03 passes already under pixel test.

## Self-Check

- [x] `tests/test_gui_inspector_styling.py` exists (9 tests)
- [x] `manga_ai_studio/gui/inspector_panel.py` — Style section + `load_multi_selection` + live vertical tooltip
- [x] `manga_ai_studio/gui/main_window.py` — `_inspector_style_commit` + size actions + gates
- [x] Commits a20ca03, 1f28464, b8f8ee0 exist (`git log --oneline -4`)
- [x] Full suite green (682 passed)

## Self-Check: PASSED

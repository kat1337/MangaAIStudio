---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 09
subsystem: ui
tags: [inspector, multi-select, mixed-sentinel, align, pyside6]

# Dependency graph
requires:
  - phase: 07-07
    provides: vertical render contract (align_v dy overlay ink offset, canvas≡bake matrix)
  - phase: 07-05
    provides: Inspector Style section + D-10 Mixed layer + ONE-snapshot _inspector_style_commit
  - phase: 07-REVIEW
    provides: WR-02 _effect_payload None-sentinel model + _replace_effect per-key preservation
provides:
  - Item-preserving Mixed align combos (leading "Mixed" + real options selectable)
  - Per-axis Mixed→None commit mapping with per-axis WR-01 no-op guard
  - Per-axis _replace_align consumer preserving untouched axes per box
affects: [verify-work UAT routing for G-07-7, future inspector styling plans, gsd-verify-work]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 3155 # chars/4 over the realized diff (12,620 chars — 3 files, 167+/10-)
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-axis sentinel→None commit: the presentation 'Mixed' entry maps to None at the commit boundary and the consumer preserves None axes per box (the WR-02 _effect_payload/_replace_effect mirror, extended from per-key to per-axis)"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_inspector_styling.py

key-decisions:
  - "Mixed align combos keep the real items under a leading 'Mixed' entry (the old items-replaced-with-['Mixed'] presentation is gone) — the override is always pickable"
  - "Mixed→None translation happens at the emit boundary, per axis; _replace_align skips None axes so each box keeps its own untouched-axis value"
  - "style_align_changed relaxed Signal(str, str) → Signal(object, object) so the None payloads pass through the typed Qt signal"

patterns-established:
  - "Sentinel-presentation rule (G-07-7 extension of WR-02): a per-axis 'Mixed' sentinel never suppresses the other axis's real change, maps to None on commit, and the consumer's None-skip preserves per-box values"

requirements-completed: [TRAN-02]

coverage:
  - id: D1
    description: "Item-preserving Mixed align presentation + per-axis Mixed→None commit mapping with per-axis WR-01 no-op guard"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_mixed_align_keeps_real_items_and_maps_sentinel"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_mixed_state_presented"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_styling.py#test_style_commit_signal_fires"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-axis _replace_align consumer: one BOXES snapshot per commit, untouched axis preserved per box, one Ctrl+Z restores both boxes, sentinel never persists into any TextStyle"
    requirement: TRAN-02
    verification:
      - kind: integration
        ref: "tests/test_gui_inspector_styling.py#test_mixed_align_override_commits_per_axis"
        status: pass
    human_judgment: false

# Metrics
duration: 38min
completed: 2026-08-12
status: complete
---

# Phase 07 Plan 09: Mixed Align State Overridable in Multi-Select (G-07-7) Summary

**Item-preserving Mixed align combos (leading "Mixed" + real options stay selectable), per-axis Mixed→None commit mapping with a per-axis WR-01 no-op guard, and a per-axis `_replace_align` consumer that preserves each box's untouched axis — the WR-02 effect pattern mirrored for alignment.**

## Performance

- **Duration:** ~38 min
- **Started:** 2026-08-12T03:00:00Z (approx.)
- **Completed:** 2026-08-12T03:37:02Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- A differing align axis now loads as `["Mixed", <real items>]` with Mixed current — the user can override Mixed because Top/Middle/Bottom (and Left/Center/Right) stay selectable; the uniform case keeps the plain real-item list with no Mixed entry (single-select behavior byte-identical).
- `_emit_style_align_if_changed` translates each axis independently: `"Mixed"` → `None` (the untouched sentinel) and a real change on one combo fires even while the other combo still shows Mixed — the old either-axis-Mixed swallow is gone. The WR-01 no-op guard is per-axis: an unchanged focus cycle (current == loaded on both axes) still emits nothing.
- `style_align_changed` relaxed to `Signal(object, object)` so None payloads pass through the typed Qt signal.
- New `_replace_align(pb, *, align_h=None, align_v=None)` consumer: builds the changes dict from non-None axes only and delegates to `_replace_style` (fresh TextStyle via `dataclasses.replace`, Pitfall 1); a both-None call is a defensive no-op. `_on_inspector_style_align_committed` routes through it — the old both-axes `_replace_style(align_h=h, align_v=v)` overwrite is replaced.
- One style commit = ONE BOXES snapshot + ONE overlay refresh; one Ctrl+Z restores both boxes' pre-commit aligns (detached snapshot styles).

## Task Commits

Each task was committed atomically:

1. **Task 1: RED-GREEN — item-preserving Mixed align combos + sentinel→None commit mapping** — `8fe9076` (test: RED gate), `63525ed` (feat: GREEN)
2. **Task 2: per-axis _replace_align consumer + the Mixed-override commit test (one snapshot)** — `7a5ce05` (feat)

## Files Created/Modified

- `manga_ai_studio/gui/inspector_panel.py` — `load_multi_selection` align loads (`["Mixed", "Left", "Center", "Right"]` / `["Mixed", "Top", "Middle", "Bottom"]` when differing; plain real items when uniform); `_emit_style_align_if_changed` per-axis Mixed→None translation + per-axis WR-01 guard; `style_align_changed = Signal(object, object)`
- `manga_ai_studio/gui/main_window.py` — `_replace_align` (per-axis, None = untouched) + `_on_inspector_style_align_committed` rewired through it
- `tests/test_gui_inspector_styling.py` — `test_mixed_align_keeps_real_items_and_maps_sentinel` (panel-level) + `test_mixed_align_override_commits_per_axis` (window-level)

## Decisions Made

- Mirror the WR-02 pattern (per the plan's assumption_delta no-change decision): the None-sentinel model that already works for effect rows applies to the align combos per axis. No new assumptions about the style model.
- The Mixed→None translation lives at the panel's emit boundary (per-axis), and the preservation lives at the consumer (`_replace_align` None-skip) — the sentinel never reaches a `TextStyle` (Pitfall 7; T-07-14 mitigated).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Suite-count re-baseline (not a deviation):** the plan's `<verification>` asserted 693 passed (687 baseline from 07-VERIFICATION.md + 2 new), but 07-VERIFICATION.md predates the 07-07/07-08 test additions — the pre-existing suite was 701 at execution time. Full suite result: **703 passed, 0 failed** (701 + the 2 new tests). All other plan assertions held: affected-module runs (test_gui_inspector_styling.py + test_gui_boxes.py) 213 passed; grep gates `"Mixed", "Left"` == 1, `"Mixed", "Top"` == 1, `def _replace_align` == 1.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-07-7 (major) closed: the UAT repro "align V doesn't allow me to override, it just says mixed" is covered end-to-end by `test_mixed_align_override_commits_per_axis`.
- The leading-Mixed item list + per-axis None-skip is the canonical pattern for any future per-axis multi-select control (e.g. per-box effect sub-fields).
- Remaining open gaps from 07-UAT.md: G-07-1..G-07-6 (own plans), G-07-6 (Ctrl+Z crash, blocker) handled in its own debug/plan flow.

---
*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Completed: 2026-08-12*

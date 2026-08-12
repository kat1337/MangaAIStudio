---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 11
subsystem: ui
tags: [qsettings, textstyle, font, qt, gsd-gap-closure]

# Dependency graph
requires:
  - phase: 07-typesetting-tran-02-render-translated-text-into-the-page
    provides: 07-09 (TextStyle model, Inspector styling section, QSettings _settings() convention)
provides:
  - "App-level default font: QSettings 'defaultFontFamily' key + Qt-free default_style() factory"
  - "New user-drawn and detected boxes born with the saved default family"
  - "Set as Default Font affordance in the Inspector Font row"
affects: [verify-work (G-07-3 UAT), future settings-UI phases]

actuals:
  tokens: 4050  # chars/4 over the realized diff (plan estimated 19500 — over-estimate, confidence was low)
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provider-callable seam for canvas creation sites (canvas stays Qt-free of QSettings — the is-primary-owner weakref precedent)"
    - "Empty-family contract: '' -> None -> renderer TextStyle() defaults at both creation sites"
    - "Recents QSettings convention reused (single _settings() accessor) — no second QSettings store"

key-files:
  created: []
  modified:
    - manga_ai_studio/core/text_style.py
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_core/test_text_style.py
    - tests/test_gui_inspector_styling.py
    - tests/test_gui_detection_boxes.py

key-decisions:
  - "The Set-as-Default affordance emits the panel's own class-scope Signal (default_font_requested) — no connect_commit_handlers extension needed; MainWindow connects directly in _wire_history_actions"
  - "The Mixed sentinel never leaves the widget layer: a Set-as-Default click while the Font combo shows 'Mixed' emits nothing (Pitfall 7)"
  - "canvas.new_box_style_provider is a Callable[[], TextStyle | None] set by MainWindow — the canvas stays Qt-free of QSettings (T-07-19: no second QSettings accessor)"

requirements-completed: [TRAN-02]

# Coverage metadata — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "default_style() factory in core/text_style.py — Qt-free, None/empty -> DEFAULT_FONT_FAMILY, explicit family overrides only font_family"
    requirement: TRAN-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_text_style.py#test_default_style_none_uses_default_family"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_text_style.py#test_default_style_explicit_family_overrides_only_family"
        status: pass
    human_judgment: false
  - id: D2
    description: "Set-as-Default Font affordance in the Inspector Font row + MainWindow handler persisting QSettings 'defaultFontFamily' with transient status"
    requirement: TRAN-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_inspector_styling.py#test_set_as_default_button_emits_family"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_inspector_styling.py#test_set_as_default_writes_key_and_flashes_status"
        status: pass
    human_judgment: false
  - id: D3
    description: "New user-drawn boxes born with the saved default family via canvas.new_box_style_provider; no saved family -> style stays None (renderer defaults)"
    requirement: TRAN-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_inspector_styling.py#test_new_user_box_uses_saved_default_family"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_inspector_styling.py#test_new_user_box_keeps_style_none_without_key"
        status: pass
    human_judgment: false
  - id: D4
    description: "Newly detected boxes (mocked-detection seam) born with the saved default family; no saved family -> style None (unchanged behavior)"
    requirement: TRAN-02
    verification:
      - kind: automated_ui
        ref: "tests/test_gui_detection_boxes.py#test_detected_boxes_use_saved_default_family"
        status: pass
      - kind: automated_ui
        ref: "tests/test_gui_detection_boxes.py#test_detected_boxes_keep_style_none_without_key"
        status: pass
    human_judgment: false

# Metrics
duration: 26min
completed: 2026-08-11
status: complete
---

# Phase 07 Plan 11: Selectable Default Font (G-07-3) Summary

**A persistent app-level default font: QSettings 'defaultFontFamily' written by a Set-as-Default Inspector button, read through a Qt-free `default_style()` factory, and applied to new user-drawn and detected boxes — no saved family keeps `style None` so the renderer's Liberation Sans defaults apply and existing boxes are never re-styled.**

## Performance

- **Duration:** ~26 min
- **Started:** 2026-08-11T22:58:00-05:00
- **Completed:** 2026-08-11T23:24:00-05:00
- **Tasks:** 2 (both TDD: RED -> GREEN commits)
- **Files modified:** 7

## Accomplishments

- `default_style(font_family: str | None = None) -> TextStyle` factory in `core/text_style.py` — pure Python (no Qt import added; grep-verified), `None`/empty -> `DEFAULT_FONT_FAMILY`, an explicit family overrides ONLY `font_family` (every other field equals the `TextStyle()` defaults).
- QSettings persistence chain: `_default_font_family()` reader (`str(self._settings().value("defaultFontFamily", "") or "")` — the T-07-18 coercion) + `_on_inspector_default_font_requested(family)` writer with transient status, sharing the recents' `_settings()` store (the convention is reused, not duplicated).
- Set as Default Font QToolButton on the Inspector Font row (tooltip "Use this font for new boxes", QSS-token consistent, empty-state gated). Emits the new class-scope `default_font_requested = Signal(str)` with the CURRENT combo family; a click while the combo shows "Mixed" emits nothing (Pitfall 7).
- `canvas.new_box_style_provider` callable seam (None default); `_commit_create` applies it to new user PageBoxes. MainWindow wires it to `default_style(self._default_font_family())` with the empty-family -> None contract. The canvas stays Qt-free of QSettings (T-07-19).
- `_build_detected_boxes` constructs detected PageBoxes with `style=default_style(fam) if fam else None` — the same empty-family contract.
- No-key contract proven: with no saved family, new user boxes AND detected boxes keep `style is None` — the existing box tests pass UNCHANGED; existing boxes are never re-styled (D-06 flat per-box).
- Full suite: **712 passed, 0 failed** (704 baseline + 8 new tests; plan predicted ~4 at a 687 baseline that 07-10 had already moved to 704).

## Task Commits

Each task was committed atomically (TDD RED -> GREEN):

1. **Task 1: default_style() factory + QSettings chain + Set-as-Default affordance**
   - `caba263` (test) — factory + affordance/persistence tests
   - `0c2782d` (feat) — factory, panel signal+button, reader/writer+status, panel wiring
2. **Task 2: apply the default at both new-box creation sites**
   - `26b7a46` (test) — user-box + detected-box application tests
   - `08a3b26` (feat) — canvas provider seam + `_commit_create` + `_build_detected_boxes`

## Files Created/Modified

- `manga_ai_studio/core/text_style.py` — `default_style()` Qt-free factory near `DEFAULT_FONT_FAMILY`
- `manga_ai_studio/gui/inspector_panel.py` — `default_font_requested = Signal(str)`, `default_font_button` on the Font row, `_on_default_font_clicked` (Mixed guard), empty-state gate entry
- `manga_ai_studio/gui/main_window.py` — `_default_font_family()` reader, `_on_inspector_default_font_requested()` writer+status, signal wiring in `_wire_history_actions`, canvas provider wiring in `__init__`, `_build_detected_boxes` style application
- `manga_ai_studio/gui/canvas.py` — `new_box_style_provider` attribute (None default) + `_commit_create` applies it
- `tests/test_core/test_text_style.py` — 2 factory tests
- `tests/test_gui_inspector_styling.py` — `_isolate_settings` + Alt+drag event helpers, 4 tests (affordance emit, persistence+status, user-box with key, user-box no key)
- `tests/test_gui_detection_boxes.py` — `_isolate_settings` helper, 2 tests (detected with key, detected no key)

## Decisions Made

- **Panel-owned signal emission (no `connect_commit_handlers` extension):** the Set-as-Default button connects internally to `_on_default_font_clicked` which emits the class-scope signal; MainWindow connects directly in `_wire_history_actions` beside `connect_commit_handlers`. Keeps the affordance self-contained (a button click is an explicit action, not a WR-01 commit-on-focus-loss control).
- **Provider-callable seam for the canvas** (the is-primary-owner precedent): `new_box_style_provider` is set by MainWindow after construction; the canvas never touches QSettings (prohibition + T-07-19).
- **Empty-family -> None contract at BOTH creation sites:** `''` never reaches the factory from the creation paths — `style=None` keeps today's behavior and keeps the existing box tests byte-identical.
- **T-07-18 mitigation honored:** the family is bounded at the QFontComboBox family list and coerced `str(... or "")` on read; the Mixed sentinel is blocked at the panel.

## Deviations from Plan

**None - plan executed exactly as written** (2 tasks, both TDD with RED-gate commits, all acceptance gates hit).

Notes that are not deviations:
- Test-count baseline: the plan's "687 + ~4 = 698" assumed the 07-VERIFICATION baseline; plan 07-10 had already moved the suite to 704. This plan added 8 tests -> 712. Same plan-shaped work, later baseline.
- Task 2's no-key application assertions pass pre-fix by design (they pin today's behavior — the no-key contract is a regression guard, not a RED gate; the key-present paths carried the RED).

## Issues Encountered

- **My test helper mis-copied the canonical release event** (button/buttons swapped in `_release_at`): the synthetic `QMouseEvent(MouseButtonRelease, ..., NoButton, LeftButton, ...)` yields `event.button() == NoButton`, so the canvas's `mouseReleaseEvent` skipped the `_commit_create` branch and no box was created (`_creating_box` stayed True). Diagnosed by instrumenting a copy of the canonical `test_alt_drag_creates_user_box`; fixed by matching the canonical helper exactly (`button=LeftButton, buttons=NoButton`). No production code involved.
- The scratch probe script hit the known G-07-6 native teardown abort (0xC0000409) at process exit — the same latent UAF the graveyard fix addresses; irrelevant to test results (pytest handles teardown ordering).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-07-3 closed: the user can select a default font (Inspector -> Set as Default Font) and every new user-drawn or detected box is born with it; fresh-install behavior is unchanged (no key -> renderer defaults).
- The `default_font_requested` signal + `_default_font_family()` reader are the seam a future settings UI can reuse (a settings dialog would replace the minimal Inspector affordance without touching the persistence chain).
- Remaining phase-7 gaps still open: G-07-1 (vertical/Latin upright), G-07-2 (font dropdown substring search), G-07-5 (align_v on horizontal), G-07-6 (Ctrl+Z crash), G-07-7 (Mixed align override). (G-07-4 auto-fit grow was completed by plan 07-10.)

## Self-Check: PASSED

- SUMMARY.md exists at `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-11-SUMMARY.md`
- Commits present: `caba263` (T1 RED), `0c2782d` (T1 GREEN), `26b7a46` (T2 RED), `08a3b26` (T2 GREEN)
- Grep gates: `def default_style` x1 (text_style.py); `"defaultFontFamily"` x2 (main_window.py); `new_box_style_provider` x3 (canvas.py); `default_style(` x2 (main_window.py)
- Qt-free gate: text_style.py imports = stdlib only (`__future__`, `dataclasses`)
- Full suite: 712 passed, 0 failed (pinned interpreter)

---

*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Plan 11 (G-07-3) completed: 2026-08-11*

---
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
plan: 02
subsystem: ui
tags: [gui, canvas, empty-state, copy, regression-tests, pytest-qt, deferred-fix]

# Dependency graph
requires:
  - phase: 05-project-persistence-image-ops-export
    provides: project-open numpy display path (_display_page_state -> set_image_from_numpy), Ctrl+O/Open Project re-binding, Open Folder Ctrl+Shift+O binding
provides:
  - D-09: empty-state overlay (z=2000 trio) cleared on every image display path incl. the numpy path (project open, image-op write-back, undo)
  - D-11: first-run hint copy rewritten to the real Open Folder (Ctrl+Shift+O) binding; stale Open-Image shortcut advertisement gone from canvas.py
affects: [07-typesetting, phase verification/UAT, UI reviews]

# Actuals (#2632) — pairs with the plan's estimate (22000 low-confidence) to calibrate.
# Scale: estimateTokens = chars/4 over the realized diff. Never a harness token count.
actuals:
  tokens: 2158
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RED-GREEN regression at the real bug site: test must fail on pre-fix code (project-open numpy path drives the actual _display_page_state seam, no monkeypatch)"
    - "Idempotence guard pattern: a fix call shared across paths gets a benign-call test (preview path) so the shared-impl placement is locked"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_canvas.py
    - tests/test_gui_project.py

key-decisions:
  - "D-09 fix placed inside _set_image_from_numpy (the shared implementation) rather than the public set_image_from_numpy wrapper — one call covers the preview path idempotently (plan's verbatim prescription)"
  - "Test 3 (preview path) is an idempotence guard that passes both pre- and post-fix by design — the RED gate is carried by tests 1+2 (project-open + numpy paths)"

patterns-established:
  - "Empty-state refresh contract: _update_empty_state() runs at the end of every image display path (set_image, set_image_from_numpy/_set_image_from_numpy, clear) — the trio + empty-box hint visibility is always consistent with image presence"

requirements-completed: [D-09, D-11]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "D-09 — empty-state overlay (heading/body/hint trio, z=2000) never persists over a loaded page on the numpy display path; empty-box hint (z=850) shows on zero-box pages"
    requirement: D-09
    verification:
      - kind: integration
        ref: tests/test_gui_project.py#test_project_open_hides_empty_state_trio
        status: pass
      - kind: unit
        ref: tests/test_gui_canvas.py#test_numpy_display_hides_empty_state
        status: pass
      - kind: unit
        ref: tests/test_gui_canvas.py#test_preview_path_keeps_empty_state_hidden
        status: pass
    human_judgment: false
  - id: D2
    description: "D-11 — first-run hint copy is 'File → Open Folder… (Ctrl+Shift+O) · or drag files here' (exact, incl. 3-space padding); 'Ctrl+O' absent from canvas.py; body/heading copy untouched"
    requirement: D-11
    verification:
      - kind: unit
        ref: tests/test_gui_canvas.py#test_empty_hint_copy_references_open_folder
        status: pass
      - kind: other
        ref: "grep gate: ! grep -Fq 'Ctrl+O' manga_ai_studio/gui/canvas.py (exit 1 = no matches)"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-08-09
status: complete
---

# Phase 06 Plan 02: Empty-State Overlay + Hint Copy Fixes Summary

**D-09 empty-state overlay cleared on the numpy display path (project open / image-op write-back / undo) via a one-line `_update_empty_state()` call in `_set_image_from_numpy`, with RED-GREEN regression tests at the real bug site; D-11 hint copy rewritten to the real Open Folder (Ctrl+Shift+O) binding, stale Open-Image shortcut advertisement removed from canvas.py**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-09T16:04:00Z
- **Completed:** 2026-08-09T16:19:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- **D-09 closed:** `_set_image_from_numpy` (canvas.py:710-767) now calls `_update_empty_state()` before returning — the D-09 verbatim prescription at the shared-impl bug site. The z=2000 "No page open" trio never persists over a loaded page on ANY display path: `set_image`, `set_image_from_path`, `set_image_from_numpy` (project open via `_display_page_state`, image-op write-back, undo), and the live-preview path (idempotent, RESEARCH Pitfall 1).
- **D-11 closed:** the first-run hint at canvas.py:278 is now `"File → Open Folder… (Ctrl+Shift+O) · or drag files here"` — matching the locked UI-SPEC §Copywriting row and the real bindings (Open Folder Ctrl+Shift+O at main_window.py:305; Ctrl+O is Open Project… at main_window.py:311). Heading/body copy, fonts, and accent color untouched; body text stays verbatim.
- **RED-GREEN regression contract honored:** 2 of 3 new tests failed on pre-fix code (project-open trio + numpy trio) and all 3 pass post-fix; the preview-path test is the idempotence guard (passes both sides by design).

## Task Commits

Each task was committed atomically:

1. **Task 1: D-09 — empty-state overlay cleared on the numpy display path (RED-GREEN)**
   - `b54b48e` (test): add D-09 empty-state overlay regression tests (RED) — test_project_open_hides_empty_state_trio + test_numpy_display_hides_empty_state failed pre-fix, test_preview_path_keeps_empty_state_hidden passed (guard)
   - `63b200f` (feat): clear empty-state overlay on numpy display paths (D-09) — one `self._update_empty_state()` call in `_set_image_from_numpy`
2. **Task 2: D-11 — hint copy references the real Open Folder binding**
   - `0517d55` (fix): hint copy rewritten to UI-SPEC locked wording + test_empty_hint_copy_references_open_folder regression test

**Plan metadata:** (pending final docs commit)

## Files Created/Modified

- `manga_ai_studio/gui/canvas.py` - `_set_image_from_numpy` gains `self._update_empty_state()` before the final return (D-09, +8 lines incl. D-09 comment); `_empty_hint` text at :278 rewritten to the locked Open Folder copy (D-11, comment avoids the literal "Ctrl+O" substring so the file-level grep gate stays clean)
- `tests/test_gui_canvas.py` - +3 tests: test_numpy_display_hides_empty_state, test_preview_path_keeps_empty_state_hidden, test_empty_hint_copy_references_open_folder (+~77 lines incl. section header)
- `tests/test_gui_project.py` - +1 test: test_project_open_hides_empty_state_trio (drives the real save→reopen project flow, +26 lines)

## Decisions Made

- **Fix placement (D-09):** the call goes inside `_set_image_from_numpy` — the shared implementation both public wrappers route through — per the plan's verbatim prescription. This covers the preview path (Levels live preview) idempotently without touching `set_image_from_numpy_preview`, and keeps the fix to one line.
- **Test 3 semantics:** `test_preview_path_keeps_empty_state_hidden` is the RESEARCH Pitfall 1 idempotence guard — it passes on pre-fix code too (the trio is already hidden after `set_image`). The RED gate is carried by tests 1+2, which assert the actual regression (trio persists on the numpy path). This matches the plan's acceptance criteria exactly.
- **Comment wording (D-11):** the D-11 comment in canvas.py explains the stale copy without the literal substring "Ctrl+O" — the acceptance-criteria grep gate (`! grep -Fq 'Ctrl+O' canvas.py`) is file-level, and a comment containing the stale string would trip it.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- None. The only wrinkle was the D-11 comment wording tripping the plan's own file-level grep gate during verification — resolved by rephrasing the comment (documented as a decision above, no behavior change).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Both 05-UAT/05-UI-REVIEW deferrals D-09 and D-11 are closed with RED-GREEN regression tests at the real bug sites.
- 60/60 tests green across test_gui_project.py + test_gui_canvas.py (56 pre-plan + 4 new).
- Phase 06 continues with plans 06-03/06-04/06-05 (toolbar active-tool highlight, dialog typography, full curve editor integration).

---

*Phase: 06-refinement-polish-deferred-fixes-full-curve-editor*
*Completed: 2026-08-09*

## Self-Check: PASSED

- SUMMARY.md exists on disk ✓
- Commits verified in git log: b54b48e (RED), 63b200f (GREEN), 0517d55 (D-11 fix) ✓

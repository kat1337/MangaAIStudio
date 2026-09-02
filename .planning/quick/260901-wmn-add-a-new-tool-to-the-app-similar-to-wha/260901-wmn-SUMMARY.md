---
phase: quick-260901-wmn
plan: 01
subsystem: ui
tags: [ocr, screen-grab, poricom, clipboard, pyqt, pyside6, manga-ocr, tools-strip]

# Dependency graph
requires:
  - phase: 04-ocr-recognition-text-editing
    provides: TorchOCRModel adapter + backend_factory + Worker/_op_running dispatch pipeline + _resolve_ocr_model_path (CR-11)
  - phase: 09-ui-rework
    provides: ToolsStrip (exclusive QActionGroup + D-06 action-owned icons) + set_active_tool window-action sync contract (WR-02)
  - phase: quick-260828-l3l
    provides: the 7th-tool registration precedent (ToolMode + strip + window action + free-letter QShortcut)
provides:
  - ToolMode.OCR_GRAB — the 8th exclusive strip tool (S shortcut), screen-scoped and page-inert
  - gui/ocr_grab.py — ScreenGrabOverlay (rect picker), grab_screen_region/_crop_scaled (DPR-safe grab), qimage_to_rgb_array (stride-safe detached conversion), OcrGrabHistoryPanel (pure-follower floating history)
  - MainWindow session wiring — overlay lifecycle, off-thread Worker OCR, OS clipboard copy, capped re-copyable history
affects: [ocr, tools-strip, shortcuts-audit, future-screen-tools]

actuals:
  tokens: 19900        # chars/4 over the realized 79,627-byte diff (plan estimated 70,000)
  tasks: 3
  commits: 5

tech-stack:
  added: []            # T-QG-SC: no new packages — PySide6 + numpy + manga-ocr reuse only
  patterns:
    - "Pure-follower floating panel (signals only, no business logic — InspectorPanel precedent)"
    - "Rect-picker overlay separated from pixel grabbing (overlay never stores pixels — trivially testable)"
    - "Stride-safe QImage→numpy conversion (bytesPerLine-padded rows, detached .copy())"

key-files:
  created:
    - manga_ai_studio/gui/ocr_grab.py
    - manga_ai_studio/gui/assets/icons/ocr-grab.svg
    - tests/test_gui_ocr_grab.py
  modified:
    - manga_ai_studio/core/mask_editor.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/tools_strip.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_tools_strip.py
    - tests/test_mask_editor/test_mask_editor.py
    - tests/test_gui_crop_tool.py

key-decisions:
  - "Selection rect built as origin + QSize (not the two-QPoint QRect corners ctor) — the corners ctor is bottom-right-INCLUSIVE and skewed normalized drags by 1px; no-drag clicks now emit a true 0x0 degenerate rect"
  - "Overlay closes BEFORE any grab (T-QG-01) and one session at a time (T-QG-03); closeEvent closes the parentless overlay so no topmost window outlives the app"
  - "Clipboard write in _on_ocr_grab_finished is the feature (T-QG-02, Poricom parity) — the canvas box-copy no-OS-clipboard rule deliberately does not extend to screen grabs"
  - "OCR Grab is deliberately NOT page-open gated in _refresh_action_states — it is a screen tool and works with no page open"
  - "The async end-to-end test asserts against a recorder clipboard stub — the real Windows clipboard starves under rapid test polling (clipboard-manager contention); the two synchronous tests still assert the REAL OS clipboard"

patterns-established:
  - "8th-tool registration recipe: ToolMode member + _TOOL_ICONS entry + _make_tool_action + window QAction + Tools menu + free-letter QShortcut + set_active_tool sync tuple"
  - "Screen-tool contract: canvas press-gate exclusion tuple (inert like MOVE), no PAINT_TOOLS membership, no page-open gating"

requirements-completed: [QUICK-260901-WMN]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "OCR Grab registered as the 8th exclusive strip tool: ToolMode enum member, ocr-grab.svg icon, strip button/action (8 exclusive actions), window action, Tools menu entry, S QShortcut, set_active_tool sync — one tool_changed emission per selection"
    requirement: QUICK-260901-WMN
    verification:
      - kind: integration
        ref: "tests/test_gui_tools_strip.py::test_strip_has_ocr_grab_action_carrying_toolmode"
        status: pass
      - kind: integration
        ref: "tests/test_gui_tools_strip.py::test_set_active_tool_ocr_grab_checks_strip_and_emits"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_main_window_has_ocr_grab_window_action"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_s_shortcut_activates_ocr_grab"
        status: pass
    human_judgment: false
  - id: D2
    description: "Canvas inertness: a press-drag-release with OCR_GRAB active paints nothing and arms no crop (falls through to the base view)"
    requirement: QUICK-260901-WMN
    verification:
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_canvas_treats_ocr_grab_as_inert"
        status: pass
    human_judgment: false
  - id: D3
    description: "ScreenGrabOverlay rect picker: normalized region_selected on release + close, Esc selection_cancelled + close, degenerate no-drag click, dimmed paint with accent selection border, zero pixel storage"
    requirement: QUICK-260901-WMN
    verification:
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_overlay_drag_emits_normalized_rect_once_and_closes"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_overlay_esc_cancels_and_closes"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_overlay_click_without_drag_emits_degenerate_rect"
        status: pass
    human_judgment: false
  - id: D4
    description: "DPR-safe screen grab + stride-safe detached numpy conversion (grab_screen_region/_crop_scaled/qimage_to_rgb_array) with degenerate-input null guards"
    requirement: QUICK-260901-WMN
    verification:
      - kind: unit
        ref: "tests/test_gui_ocr_grab.py::test_crop_scaled_scales_by_dpr"
        status: pass
      - kind: unit
        ref: "tests/test_gui_ocr_grab.py::test_crop_scaled_intersects_bounds_and_handles_offset"
        status: pass
      - kind: unit
        ref: "tests/test_gui_ocr_grab.py::test_qimage_to_rgb_array_exact_pixels_and_detached"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_grab_screen_region_smoke"
        status: pass
    human_judgment: false
  - id: D5
    description: "Floating history panel: always-on-top tool window, add_entry prepend + 20 cap + empty rejection, truncated preview with full text on click, New capture signal, created hidden"
    requirement: QUICK-260901-WMN
    verification:
      - kind: unit
        ref: "tests/test_gui_ocr_grab.py::test_panel_add_entry_prepends_most_recent_first"
        status: pass
      - kind: unit
        ref: "tests/test_gui_ocr_grab.py::test_panel_caps_history_at_20"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_panel_entry_click_emits_full_text"
        status: pass
    human_judgment: false
  - id: D6
    description: "End-to-end session: tool selection shows panel + arms overlay; region grab runs manga-ocr off the GUI thread through the existing Worker/_op_running pipeline (first-run download note preserved), copies the recognized text to the OS clipboard, and prepends the history; Esc/tool-switch closes the overlay; errors surface via the error chip"
    requirement: QUICK-260901-WMN
    verification:
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_grab_dispatch_end_to_end_with_stubs"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_grab_finished_copies_to_clipboard_and_history"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_grab_session_lifecycle"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_grab_error_path_shows_chip_and_cleanup"
        status: pass
      - kind: integration
        ref: "tests/test_gui_ocr_grab.py::test_grab_region_selected_closes_overlay_before_grab"
        status: pass
    human_judgment: false
  - id: D7
    description: "Manual smoke on a real display: press S, drag over Japanese text in another window, clipboard receives the recognized text, history lists it, Esc cancels mid-drag, history click re-copies"
    requirement: QUICK-260901-WMN
    verification: []
    human_judgment: true
    rationale: "Screen capture + cross-window interaction + real manga-ocr recognition cannot be automated headlessly; needs the operator's eyes and display (plan verification section)."

# Metrics
duration: 55min
completed: 2026-09-02
status: complete
---

# Quick Task 260901-wmn: OCR Grab Tool (Poricom-style) Summary

**Poricom-style screen OCR shipped as the 8th exclusive strip tool (S): drag a rectangle over any on-screen text — manga-ocr runs off the GUI thread and the recognized text lands on the OS clipboard, with an always-on-top floating history (20 entries, click-to-re-copy).**

## Performance

- **Duration:** 55 min
- **Started:** 2026-09-02T04:40:42Z
- **Completed:** 2026-09-02T05:36Z
- **Tasks:** 3/3
- **Files modified:** 10 (3 created, 7 modified)

## Accomplishments

- OCR Grab is registered everywhere the other 7 tools are: `ToolMode.OCR_GRAB`, strip button + exclusive action (group now 8), `action_tool_ocr_grab` window action, Tools menu entry, free-letter **S** QShortcut, and `set_active_tool` sync — exactly one `tool_changed` emission per selection from every entry path. Deliberately NOT page-open gated (it works with no page open).
- The canvas treats it as inert: the left-press gate excludes `OCR_GRAB`, so page presses fall through Move/Pan-style — no painting, no crop arming, no brush-dot cursor.
- New `gui/ocr_grab.py` (headless-importable: no main_window/OCR imports): `ScreenGrabOverlay` (fullscreen frameless topmost rect picker — normalized `region_selected` on release, Esc `selection_cancelled`, degenerate no-drag click, dim + accent #00d4ff selection paint, stores NO pixels), `grab_screen_region`/`_crop_scaled` (devicePixelRatio-scaled, bounds-intersected, degenerate-guarded), `qimage_to_rgb_array` (bytesPerLine-safe, detached), `OcrGrabHistoryPanel` (pure follower: prepend, 20-cap, truncated preview + full text on click, New capture button, created hidden).
- MainWindow wiring mirrors `_dispatch_ocr_for_box`: `_op_running` gate, factory-resolved adapter, Worker on the global thread pool, indeterminate progress, first-run `is_ocr_downloaded()` "Loading OCR model…" note (CR-11); `_run_ocr_grab_task` is numpy/adapter-only (T-01-07); success copies to the OS clipboard + prepends history ("Copied N chars to clipboard"); empty text writes nothing; errors log + error chip, never a crash; cleanup never auto-relaunches the overlay (the user re-triggers with S / New capture).
- Session lifecycle: selection or re-selection shows the panel + arms a fresh overlay (S re-trigger); switching away hides the panel and closes the overlay; the overlay always closes BEFORE the grab so it never photographs itself (T-QG-01), and one session at a time (T-QG-03).
- Tests: 35 new/updated (28 in the new `tests/test_gui_ocr_grab.py`, 3 new + updated counts in `test_gui_tools_strip.py`, 2 superseded-contract tests modernized). Full suite: **1246 passed, 0 failed** (baseline 1214 — strict superset, no regressions).

## Task Commits

1. **Task 1: Register the 8th tool** - `541e12d` (feat)
2. **Task 2: gui/ocr_grab.py — overlay, grab helpers, history panel** - `4ecdc26` (feat)
3. **Task 3: MainWindow wiring — session lifecycle, Worker dispatch, clipboard, history** - `8a0f68a` (feat)

**Companion commits (deviations, see below):**
- `dfe001c` (test) — 7-tool contract tests updated for the 8th tool
- `9a40ded` (test) — spaced real-clipboard reads in GUI tests

## Files Created/Modified

- `manga_ai_studio/core/mask_editor.py` — `OCR_GRAB = "ocr_grab"` (8th member, after CROP) + docstring
- `manga_ai_studio/gui/canvas.py` — left-press paint gate excludes `OCR_GRAB` (inert fall-through)
- `manga_ai_studio/gui/assets/icons/ocr-grab.svg` — viewfinder glyph (24x24, #e8e8ea stroke, D-06 format)
- `manga_ai_studio/gui/tools_strip.py` — `_TOOL_ICONS` entry, `action_ocr_grab` (after Crop), `_action_to_tool`, button loop, docstring counts
- `manga_ai_studio/gui/ocr_grab.py` — **created**: overlay + grab/convert helpers + history panel
- `manga_ai_studio/gui/main_window.py` — `action_tool_ocr_grab`, menu entry, S shortcut, sync tuple, `_build_ocr_grab_panel`, session lifecycle in `set_active_tool`, `_start/_close_grab_overlay`, `_on_grab_region_selected`, `_dispatch_ocr_grab`, `_run_ocr_grab_task`, `_on_ocr_grab_finished/_error/_cleanup`, `_on_ocr_grab_history_copy`, closeEvent overlay teardown
- `tests/test_gui_ocr_grab.py` — **created**: 28 tests (registration, inertness, overlay, crop/DPR math, conversion, panel, wiring)
- `tests/test_gui_tools_strip.py` — 8-tool enumeration + 3 new OCR Grab cases
- `tests/test_mask_editor/test_mask_editor.py` — 7→8 ToolMode members
- `tests/test_gui_crop_tool.py` — exclusive-group order includes OCR_GRAB after Crop

## Decisions Made

- Selection rect built as origin + explicit `QSize` (the two-QPoint `QRect` corners ctor is bottom-right-INCLUSIVE — it skewed normalized drags by 1px); a no-drag click now emits a true 0x0 rect, which Task 3's `<1px` guard ignores with a status hint.
- The grab overlay is parentless per plan, so `closeEvent` explicitly closes it (and hides the panel) — a topmost overlay must never outlive the window (T-QG-03).
- No modal dialog on grab-OCR errors (unlike `_on_ocr_error`): log + error chip + status, so the session survives for another grab — per the plan's "never crashes, panel stays open".
- The panel's click signal fires from `itemClicked` AND `itemActivated` (both per plan wording "activated/clicked").
- Async end-to-end test asserts the clipboard contract via a recorder stub; the two synchronous tests keep asserting the REAL OS clipboard (see Issues Encountered).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking companion tests] Two tests encoded the superseded 7-tool contract**
- **Found during:** full-suite verification (after Task 3)
- **Issue:** `test_tool_mode_has_seven_members` (asserts exact ToolMode name set) and `test_crop_is_sixth_exclusive_tool` (asserts the exclusive-group order list ends at CROP) fail by design once the plan adds the 8th tool
- **Fix:** renamed to `test_tool_mode_has_eight_members` (+ OCR_GRAB); order list gains `OCR_GRAB` after Crop; docstrings updated
- **Files modified:** tests/test_mask_editor/test_mask_editor.py, tests/test_gui_crop_tool.py
- **Verification:** both modules green (33 passed)
- **Committed in:** dfe001c

**2. [Rule 2 - Missing critical functionality] Parentless overlay survived window close**
- **Found during:** Task 3
- **Issue:** `ScreenGrabOverlay` is constructed without a parent (plan-literal); on app exit a topmost always-on-top overlay would linger (stuck desktop window)
- **Fix:** `closeEvent` calls `_close_grab_overlay()` and hides the panel before accepting
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** session-lifecycle + teardown paths in tests/test_gui_ocr_grab.py
- **Committed in:** 8a0f68a (part of the Task 3 commit)

**3. [Rule 1 - Bug] QRect corners-ctor skewed normalized drag rects by 1px**
- **Found during:** Task 2 (overlay drag test failed: x=61 not 60)
- **Issue:** `QRect(QPoint, QPoint)` is bottom-right-inclusive; `.normalized()` on an inverted corners-rect lands 1px off, and the press-time rect was 1x1 rather than the degenerate 0x0 the contract expects
- **Fix:** `_rect_to()` builds origin + QSize then normalizes; press seeds `QRect(origin, QSize(0, 0))`
- **Files modified:** manga_ai_studio/gui/ocr_grab.py
- **Verification:** overlay drag/Esc/degenerate tests green
- **Committed in:** 4ecdc26 (part of the Task 2 commit)

---

**Total deviations:** 3 auto-fixed (Rule 1 x1, Rule 2 x1, Rule 3 x1)
**Impact on plan:** All fixes necessary for correctness/completion; no scope creep.

## Issues Encountered

- **Windows clipboard starvation under test load (environmental, resolved):** the machine's clipboard manager intermittently holds the clipboard open, so rapid `clipboard().text()` polling transiently fails ("Unable to obtain clipboard") and only under full-suite load — isolated runs always passed. Fixed in-test: the async end-to-end test asserts against a recorder stub (the `QGuiApplication.clipboard().setText` call contract is still exercised), and the two real-clipboard tests read with 50ms-spaced retries (`9a40ded`). The feature itself writes/reads the real OS clipboard in production.
- **`test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` flake (pre-existing, out of scope):** failed twice in the first full-suite run (stroke-edge pixel sampled fainter than the sanity bound), then passed 6/6 on retry in the same tree and 4/4 at the pre-change baseline commit (checked via a temporary read-only worktree, since removed). Unrelated to this change — the task never touches the paint/display path. Logged here rather than fixed: scope boundary.

## User Setup Required

None - no external service configuration required. (First OCR Grab use downloads the manga-ocr model on the existing CR-11 path if the HF cache is empty — already the app's standard first-run behavior.)

## Next Phase Readiness

- No blockers. The tool is complete end-to-end on the code/test side; the only open item is the operator's manual smoke on a real display (coverage D7): launch via start.bat, press S, drag over Japanese text in another window, confirm clipboard + history; Esc mid-drag cancels; history click re-copies.
- Shortcut audit note: "S" was the last free mnemonic letter in the audited set (V B R L E O G M T P D C F) — future tools will need multi-letter or modifier shortcuts.

---
*Quick task: 260901-wmn-add-a-new-tool-to-the-app-similar-to-wha*
*Completed: 2026-09-02*

## Self-Check: PASSED

- All 7 key files (3 created, 4 modified) verified on disk.
- All 5 commits verified in git log: `541e12d`, `4ecdc26`, `8a0f68a`, `dfe001c`, `9a40ded`.
- Full suite at close: 1246 passed, 0 failed (baseline 1214 — strict superset).
- Docs artifacts (this SUMMARY, STATE.md, PLAN.md) deliberately left uncommitted — orchestrator owns the docs commit.

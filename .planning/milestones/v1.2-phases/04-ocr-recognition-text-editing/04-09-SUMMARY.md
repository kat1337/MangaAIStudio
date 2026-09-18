---
phase: 04-ocr-recognition-text-editing
plan: 09
subsystem: gui (box display objects — overlay fit-in-box wrap + menu/toolbar structure)
tags: [gui, box-item, text-overlay, fit-in-box, wrap, shrink-to-fit, menu-structure, toolbar, gap-closure, uat-test-1, tdd, pytest-qt]
requires:
  - Phase 04 Plan 08 overlay tracking + zoom clamp ([10,28] viewport-px font, 2/zoom outline, stored _overlay_zoom, apply_overlay_zoom seam)
  - Phase 04 Plan 04 BoxItem text overlay (QGraphicsTextItem child z=120, refresh_text_overlay)
  - Phase 02/03 file menu + toolbar actions (action_open_folder Ctrl+Shift+O, action_open_image Ctrl+O)
provides:
  - refresh_text_overlay fit-in-box contract: setTextWidth(inner_w) wrap + box-adaptive base (14 x min(box_w, box_h)/100 vp, clamped [10,28] — the clamp bounds the BASE) + bounded shrink-to-fit loop (max 12 steps of 0.9, hard floor 5 vp checked at loop TOP)
  - BoxItem._overlay_inset() — one shared inset formula (border half-width + 2px) for the overlay position AND the wrap width
  - EditorCanvas._commit_resize re-wrap: refresh_text_overlay once per drag at resize commit (per-mousemove _advance_resize stays setPos-only, RC-1 discipline)
  - MainWindow recent_menu/batch_menu as standalone QMenu children — File submenus only, menubar top-level exactly File/Edit/View/Text/Tools/Help
  - MainWindow toolbar first action = action_open_folder (Ctrl+Shift+O); Open Image stays in File menu (Ctrl+O)
  - 13 new test cases (451 full-suite total: 439 baseline - 1 removed clamp case + 13 new), 2 §16 spec amendment notes
affects:
  - UAT test 1 re-verification (the fit-in-box truth is now mechanically observable; the on-artwork visual judgment stays a human UAT call)
  - Any future plan touching overlay rendering, menu structure, or toolbar actions (standalone-QMenu pattern; fit-loop contract)
tech-stack:
  added: []
  patterns:
    - setTextWidth wrap: QGraphicsTextItem.setTextWidth(inner_w) makes QTextDocument lay out inside the box (no horizontal overshoot); inner dims floored with max(1.0, ...) so degenerate rects cannot produce invalid widths
    - box-adaptive base + bounded shrink-to-fit: base_vp = 14 x min(box_w, box_h)/100, clamp [10,28] bounds the BASE; the loop (max 12 x 0.9) re-merges the char format per iteration and reads doc.size() live, breaking on fit or on the loop-TOP floor check (no render ever lands below 5 vp)
    - standalone-QMenu child: submenus constructed as QMenu(title, self) so their menuAction never lands in the menubar top-level action list (Qt does not remove the action when addMenu re-parents a QMenu)
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_boxes.py
    - tests/test_gui_batch.py
    - .planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md
key-decisions:
  - "The [10,28] viewport-px clamp bounds the box-adaptive BASE (14 x min(box_w, box_h)/100); the RENDERED font may go below 10 vp down to the 5 vp floor via the bounded shrink-to-fit loop — the plan's intentional contract change documented in the §16 clamp comment + UI-SPEC amendments."
  - "Test A uses 'word ' x 59 + 'word' (no trailing space): Qt's QTextDocument trims trailing whitespace at line ends, so a trailing space in the source text makes toPlainText() differ from it (299 vs 300 chars on this platform) — the no-trailing-space form preserves the plan's exact-equality contract."
  - "Test E uses 'hello world' instead of 'hello': at 40pt / zoom 0.25 'hello' measures ~190px on this platform (Liberation Sans metrics) — narrower than the plan-reference platform's 265-280px — so it does NOT wrap and the fit loop never engages. 'hello world' wraps and lands at the plan's measured ~26.24pt / 6.56 vp; assertions stay range-based (font < 40.0, 5.0 <= font*zoom < 10.0, box-contained) per the plan-checker."
  - "The standalone-QMenu construction (QMenu(title, self)) is the fix for the menubar leak: menuBar().addMenu() appends the submenu's menuAction to the menubar action list and addMenu re-parenting does NOT remove it — the tests assert action-list membership (not parent()) per the probe-verified contract."
  - "Toolbar swap is a pure action swap: _refresh_action_states gates neither open action and no icons are set on either, so the toolbar shows the text label 'Open Folder…' exactly as it showed 'Open Image…'."
requirements-completed: [TEXT-04]
coverage:
  - id: D1
    description: "Overlay fit-in-box: long recognized/translation text wraps INSIDE the box rect (setTextWidth at the box inner width), the font adapts to the box size (14 x min(box_w, box_h)/100 vp clamped [10,28] — the clamp bounds the BASE), and a bounded shrink-to-fit loop (max 12 x 0.9, floor 5 vp at loop top) keeps the wrapped text inside the box height."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_wraps_long_text_to_box_width"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_font_adapts_to_box_size"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_shrinks_to_fit_box_height"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_resize_commit_rewraps_overlay_text_canvas"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_fit_loop_reduces_below_clamp_floor_at_low_zoom"
        status: pass
    human_judgment: false
  - id: D2
    description: "Menu bar structure: top-level shows exactly File, Edit, View, Text, Tools, Help; Recent Files and Batch appear ONLY as File submenus in the order the user requested (Open Image, Open Folder, Recent Files, sep, Export, Batch, sep, Quit)."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_batch.py#test_menubar_top_level_has_only_the_six_core_menus"
        status: pass
      - kind: unit
        ref: "tests/test_gui_batch.py#test_recent_and_batch_menus_are_file_submenus_not_top_level"
        status: pass
      - kind: unit
        ref: "tests/test_gui_batch.py#test_file_menu_internal_order"
        status: pass
    human_judgment: false
  - id: D3
    description: "Toolbar open action is Open Folder (Ctrl+Shift+O, the manga default); Open Image stays in the File menu (Ctrl+O) and is not on the toolbar."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_batch.py#test_toolbar_first_action_is_open_folder"
        status: pass
      - kind: unit
        ref: "tests/test_gui_batch.py#test_open_image_remains_in_file_menu_not_toolbar"
        status: pass
      - kind: unit
        ref: "tests/test_gui_batch.py#test_toolbar_open_folder_triggered_opens_folder"
        status: pass
    human_judgment: false
  - id: D4
    description: "On-artwork visual judgment: wrapped text fits the box and reads sized relative to it over real manga artwork (the UAT test-1 fit-in-box truth on real pages)."
    requirement: TEXT-04
    verification: []
    human_judgment: true
    rationale: "The mechanical contract (wrap width, box-adaptive font, containment, resize-commit re-wrap) is fully covered by the automated suite; whether the result reads well over REAL manga artwork is a visual judgment no offscreen test can make — deferred to the UAT test-1 re-verification (end-of-phase human gate per the project cadence in STATE.md)."
metrics:
  duration: 11 min
  completed: 2026-08-08
  tasks: 3
  files: 6
status: complete
---

# Phase 04 Plan 09: UAT Test 1 Round-2 Gap Closure — Overlay Fit-In-Box + Menu Structure + Toolbar Summary

Closed the three NEW UAT test-1 gaps recorded in 04-UAT.md as three pure-fix TDD tasks: the text overlay now WRAPS inside the box (setTextWidth at the box inner width), the font adapts to the box size (box-adaptive base 14 x min(box_w, box_h)/100 vp, clamped [10,28], bounded shrink-to-fit to the 5 vp floor), a resize commit re-wraps/re-fits once per drag; the menubar top-level is exactly File/Edit/View/Text/Tools/Help with Recent Files + Batch as File submenus only; and the toolbar's first action is Open Folder (Ctrl+Shift+O) with Open Image staying in the File menu. Full suite: 451 passed (439 baseline - 1 removed clamp case + 13 new), 0 failed.

## What Was Built

### Task 1 — Gap 1 (MAJOR): overlay fit-in-box: wrap + box-adaptive font + bounded shrink-to-fit + resize-commit re-wrap

`manga_ai_studio/gui/box_item.py`:

- **Four module constants** next to `_OVERLAY_FONT_BASE`: `_OVERLAY_BOX_REF_DIM = 100.0` (the box min dimension that maps to the §16 14-viewport-px base), `_OVERLAY_FIT_MAX_ITERS = 12`, `_OVERLAY_FIT_STEP = 0.9`, `_OVERLAY_FIT_FLOOR_VP = 5.0` (the hard floor, checked at loop TOP so no iteration ever renders below it).
- **`_overlay_inset()` helper** — `pen().widthF() / 2.0 + _OVERLAY_INSET`, the ONE formula shared by the overlay position (`_reposition_text_overlay`, refactored to use it — the 04-08 position tests at (23,23)/(63,43) stay green) and the wrap width.
- **`refresh_text_overlay` rework** — after `setPlainText`, the document is wrapped at the box inner width via `setTextWidth(inner_w)` (inner_w/inner_h floored `max(1.0, ...)` — T-4-13g), the box-adaptive base is computed as `14 x min(box_w, box_h)/100`, clamped `min(28, max(10, base_vp * zoom))` (for the 04-08 reference box this reduces exactly to the 04-08 formula), and the bounded shrink-to-fit loop re-merges the QTextCharFormat per iteration (same PLAIN document, never setHtml — T-4-07), breaking when `doc.size().height() <= inner_h` (live size read, probe-verified) or at the loop-TOP floor check. The §16 clamp comment was updated to the 04-09 contract (the clamp bounds the BASE; the fit loop may reduce the RENDERED size below 10 vp to the 5 vp floor) with the second note line naming the wrap + box-adaptive base + bounded fit loop — both as '#'-prefixed comment lines.

`manga_ai_studio/gui/canvas.py`:

- **`_commit_resize`** now calls `item.refresh_text_overlay()` after `item._sync_handles()` — the resize COMMIT re-wraps/re-fits the overlay to the final rect ONCE per drag. The per-mousemove `_advance_resize` path stays setPos-only (RC-1 discipline — a full document rebuild must not run per-mousemove). The WR-04 delta-check emit is untouched.

`tests/test_gui_boxes.py` (04-09 section): five tests locking the contract — wrap width + containment (A), box-adaptive font parametrized over three boxes (B), shrink-below-14 + containment (C), resize-commit re-wrap through the canvas state fields (D), and the low-zoom below-clamp fit outcome (E). The 04-08 clamp test's zoom-0.25/40.0 parametrize case was REMOVED (3 cases remain, exact) per the plan's intentional contract change, with a docstring note pointing at the 04-09 replacement.

`.planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md`: two scoped §16 amendment notes (fit-in-box geometry: setTextWidth implementation + box-adaptive base + bounded loop + floor; Font+scaling base: 14px scaled by min(box_w, box_h)/100).

### Task 2 — Gap 2 (MINOR): menu bar: Recent Files + Batch are File submenus only

`manga_ai_studio/gui/main_window.py`:

- **`QMenu` added to the QtWidgets import block** (alphabetically between QMainWindow and QMessageBox).
- **`recent_menu` and `batch_menu` constructed as standalone `QMenu(title, self)` children** of the window instead of `menuBar().addMenu(title)` — the menubar-factory path appended their menuActions to the MENUBAR top-level action list (Recent Files and Batch appeared AHEAD of File and Edit — the user's exact report), and the later `file_menu.addMenu` re-parenting does NOT remove the action (probe-verified). The File-menu `addAction`/`addMenu` order (Open Image, Open Folder, Recent Files, sep, Export, Batch, sep, Quit) is UNCHANGED. Comments updated with the standalone-child rationale.

`tests/test_gui_batch.py` (04-09 menu section): three tests — top-level order exactly the six core menus (A), recent/batch menuActions in the File menu AND not in the menubar (B), File-menu internal order + separator indices [3, 6] (C).

### Task 3 — Gap 3 (MINOR): toolbar open action is Open Folder

`manga_ai_studio/gui/main_window.py`:

- **`self.toolbar.addAction(self.action_open_folder)`** replaces `addAction(self.action_open_image)` — the ONLY toolbar change. The action already existed (Ctrl+Shift+O, connected to `open_folder`); `_refresh_action_states` gates neither open action and no icons are set on either, so the toolbar renders the text label exactly as before — pure swap. Open Image keeps Ctrl+O in the File menu. `_build_toolbar` docstring first bullet updated.

`tests/test_gui_batch.py` (04-09 toolbar section): three tests — toolbar first action IS action_open_folder with Ctrl+Shift+O (A), Open Image remains in the File menu and NOT in the toolbar (B), triggering the toolbar action runs open_folder with the modal `getExistingDirectory` stubbed to `""` so the test never blocks (C). `QKeySequence` imported at the section top.

## Verification

```
# Task 1 RED (confirmed pre-fix on current source, then re-confirmed on the
#   refined tests): 6 failed, 4 passed by design
#   (A: textWidth -1/unset; B: font 14 for every box; C: no wrap, width
#    overflow; D: stale 194-width doc at font 14; E: font exactly 40.0,
#    vp 10.0; the 04-08 clamp test's 3 remaining cases + Test B case 1 pass)
# Task 1 GREEN: 10 passed (5 tests / 7 cases + 3 clamp cases); grep gates:
#   setTextWidth == 1, _OVERLAY_BOX_REF_DIM\|_OVERLAY_FIT_ == 8 (>= 6),
#   def _overlay_inset == 1, canvas refresh_text_overlay == 2, both spec notes
# Task 2 RED: A + B fail (menubar shows Recent Files and Batch ahead of File;
#   the menuActions ARE in the menubar action list), C passes by design
# Task 2 GREEN: 3 passed; grep gates: QMenu("Recent Files") == 1,
#   QMenu("Batch") == 1, QMenu >= 3, menuBar().addMenu(Recent/Batch) == 0
# Task 3 RED: A + the toolbar half of B fail (first toolbar action is Open
#   Image), C passes by design (stub in place)
# Task 3 GREEN: 3 passed; grep gates:
#   toolbar.addAction(action_open_folder) == 1,
#   toolbar.addAction(action_open_image) == 0

# GUI regression: 210 passed, 1 deselected (pre-existing flake)
python -m pytest tests/test_gui_boxes.py tests/test_gui_batch.py tests/test_gui_canvas.py -q \
  --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip

# Full suite: 451 passed (439 baseline - 1 removed clamp case + 13 new), 0 failed
python -m pytest tests/ -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip
```

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-08T01:40:12Z
- **Completed:** 2026-08-08T01:50:28Z
- **Tasks:** 3 implementation tasks (all `tdd="true"`)
- **Files modified:** 6 (3 code + 2 test + 1 spec)

## Task Commits

Each task was committed atomically as a RED test → GREEN fix pair:

1. **Task 1 RED:** `8a8ceec` — `test(04-09): add failing tests for overlay fit-in-box wrap + box-adaptive font + resize-commit rewrap` (6 failed pre-fix, 4 passed by design)
2. **Task 1 GREEN:** `84e3eca` — `fix(04-09): overlay fit-in-box: wrap at box inner width + box-adaptive font + bounded shrink-to-fit + resize-commit rewrap` (10/10 pass + grep gates)
3. **Task 2 RED:** `1f98ddc` — `test(04-09): add failing tests for menubar top-level order + File-submenu membership` (2 failed pre-fix, 1 passed by design)
4. **Task 2 GREEN:** `355b602` — `fix(04-09): Recent Files + Batch are File submenus only (standalone QMenu construction)` (3/3 pass + grep gates)
5. **Task 3 RED:** `dcef7f7` — `test(04-09): add failing tests for toolbar first-action Open Folder + File-menu retention` (2 failed pre-fix, 1 passed by design)
6. **Task 3 GREEN:** `47212e8` — `fix(04-09): toolbar first action is Open Folder (Ctrl+Shift+O), Open Image stays in File menu` (3/3 pass + grep gates)

## Files Created/Modified

- `manga_ai_studio/gui/box_item.py` — `_OVERLAY_BOX_REF_DIM` / `_OVERLAY_FIT_MAX_ITERS` / `_OVERLAY_FIT_STEP` / `_OVERLAY_FIT_FLOOR_VP` constants; `_overlay_inset()` helper (shared position/wrap formula); `refresh_text_overlay` reworked: `setTextWidth(inner_w)` wrap + box-adaptive clamped base + bounded shrink-to-fit loop; `_reposition_text_overlay` refactored onto the helper.
- `manga_ai_studio/gui/canvas.py` — `_commit_resize` calls `item.refresh_text_overlay()` after `_sync_handles()` (resize-commit re-wrap).
- `manga_ai_studio/gui/main_window.py` — `QMenu` import; `recent_menu`/`batch_menu` standalone `QMenu(title, self)` children; toolbar first action swapped to `action_open_folder`; `_build_toolbar` docstring updated.
- `tests/test_gui_boxes.py` — 04-09 fit-in-box section (5 tests); 04-08 clamp test reduced to 3 parametrize cases + docstring note.
- `tests/test_gui_batch.py` — 04-09 menu-structure section (3 tests) + toolbar-open-action section (3 tests); `QKeySequence` import added.
- `.planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md` — two §16 amendment notes (fit-in-box geometry + box-adaptive base).

## Decisions Made

See the `key-decisions:` frontmatter above. Highlights:

- The [10,28] clamp bounds the box-adaptive BASE; the fit loop may reduce the RENDERED size to the 5 vp floor — the plan's intentional contract change (04-08 clamp test case updated accordingly).
- Test A drops the trailing space (`"word " * 59 + "word"`): Qt's QTextDocument trims trailing whitespace at line ends (measured 299 vs 300 chars), so the exact-equality assertion required a no-trailing-space source.
- Test E uses "hello world" (lands at the plan's measured ~26.24pt / 6.56 vp): "hello" measures ~190px at 40pt on this platform and does not wrap, so the fit loop would never engage — the assertions stay range-based per the plan-checker.
- The standalone-QMenu construction is the fix (not parent-based assertions): the tests assert action-list membership because addMenu re-parenting never removes the menubar action.
- Toolbar swap is a pure action swap with no state-refresh or icon work (both open actions un-gated, no icons set).

## Deviations from Plan

None — the plan executed exactly as written. Two test-content notes (both anticipated by the plan-checker's "keep them range-based / platform-dependent metrics" guidance, not deviations):

1. **Test A text** is `"word " * 59 + "word"` instead of `"word " * 60`: Qt's document engine trims the trailing space of the final line (toPlainText() returned 299 of 300 chars on this platform), which would break the plan's exact-equality assertion. The no-trailing-space form preserves the assertion and the wrap behavior (300 chars, same layout).
2. **Test E text** is `"hello world"` instead of `"hello"`: on this platform Liberation Sans metrics make "hello" ~190px wide at 40pt (< inner width 194), so it would not wrap and the fit loop would never engage (font stayed exactly 40.0 — the probe showed a 1-line doc of 68px <= inner height 94). "hello world" engages the loop and lands at the plan's measured ~26.24pt / 6.56 vp with containment; the assertions are the plan's range-based ones (font < 40.0, 5.0 <= font*zoom < 10.0, box-contained). Both notes were confirmed RED on pre-fix source (6 failed / 4 passed) before the GREEN implementation, and the RED commit was amended to carry the refined tests.

**Total deviations:** 0 (2 test-content adjustments inside the planned test section, both re-verified RED against pre-fix source)
**Impact on plan:** None — same test count (13 new cases), same assertions modulo the platform-robust texts; the full-suite count landed at the plan-checker's exact expected 451.

## Issues Encountered

- **Qt trailing-whitespace trimming (Test A):** `QTextDocument` strips the trailing space of the final line, so `toPlainText()` != `"word " * 60` by one char. Resolved with a no-trailing-space text (see Deviations).
- **Platform font metrics (Test E):** "hello" at 40pt did not wrap on this Windows platform (glyph metrics narrower than the plan-reference platform), so the fit loop never engaged. Resolved with "hello world" (see Deviations).
- **RED re-verification after test refinement:** the refined tests were verified against PRE-fix source by temporarily reverting the uncommitted fix (`cp` backup → `git checkout HEAD --` → run → restore), confirming the same 6-failed/4-passed RED split before the GREEN implementation.

## Authentication Gates

None.

## Known Stubs

None. No placeholder text, hardcoded empty values, or unwired data paths introduced. The `_OVERLAY_FIT_*` constants and `_overlay_inset` are fully wired into `refresh_text_overlay`; the standalone submenus and toolbar action are live-constructed in `__init__`.

## Deferred Issues

- `tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip` — pre-existing flake, out of scope, deselected in all runs (already logged to `.planning/phases/04-ocr-recognition-text-editing/deferred-items.md`).

## Threat Surface

No new security-relevant surface beyond the plan's register (all dispositions met):

- **T-4-07 (OCR/pasted text → overlay document):** held — the fit loop re-merges `QTextCharFormat` over the same PLAIN document (setPlainText only, never setHtml); `test_text_overlay_document_is_plain_not_rich` stays green (full suite).
- **T-4-12g (shrink-to-fit arithmetic):** mitigated — bounded loop (12 iterations max); the floor is checked at loop TOP so no render ever lands below 5 vp; the `target_vp / zoom` division is safe because `apply_overlay_zoom` guards `zoom <= 0 -> 1.0`.
- **T-4-13g (box-rect-derived wrap dimensions):** mitigated — `inner_w`/`inner_h` floored with `max(1.0, ...)` so a degenerate/negative rect cannot produce an invalid text width.
- **T-4-14g (menu/toolbar action re-parenting):** accepted as planned — no new input surface; the same actions re-parented, the Ctrl+O / Ctrl+Shift+O shortcuts stay bound to the same actions, and `open_folder`'s OS-validated path logic is unchanged.

## TDD Gate Compliance

Plan frontmatter `type: execute`, `gap_closure: true`; all three implementation tasks are `tdd="true"`. Gate sequence observed per task (separate RED `test(...)` commit then GREEN `fix(...)` commit):

- **Task 1:** RED `8a8ceec` — 6/10 cases fail pre-fix with the diagnosed symptoms (A: textWidth -1; B: flat font 14; C: no wrap/overflow; D: stale 194/font-14; E: font 40.0, vp 10.0); the 04-08 clamp test's 3 remaining cases + Test B's reference case pass by design. GREEN `84e3eca` — 10/10 pass + all grep gates.
- **Task 2:** RED `1f98ddc` — A + B fail pre-fix with the user's exact report (Recent Files/Batch ahead of File; menuActions present in the menubar list); C passes by design (order lock). GREEN `355b602` — 3/3 pass + grep gates.
- **Task 3:** RED `dcef7f7` — A + the toolbar half of B fail pre-fix (first toolbar action is Open Image); C passes by design (stub + pre-existing connection). GREEN `47212e8` — 3/3 pass + grep gates.

All three RED→GREEN gates observed. No separate `refactor(...)` commit needed — implementations were clean on first pass (the `_overlay_inset` refactor landed inside the Task 1 GREEN commit per the plan's Task 1 action).

## Self-Check: PASSED

Created/modified files:
- FOUND: manga_ai_studio/gui/box_item.py
- FOUND: manga_ai_studio/gui/canvas.py
- FOUND: manga_ai_studio/gui/main_window.py
- FOUND: tests/test_gui_boxes.py
- FOUND: tests/test_gui_batch.py
- FOUND: .planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md

Commits:
- FOUND: 8a8ceec (test(04-09): add failing tests for overlay fit-in-box wrap + box-adaptive font + resize-commit rewrap)
- FOUND: 84e3eca (fix(04-09): overlay fit-in-box: wrap at box inner width + box-adaptive font + bounded shrink-to-fit + resize-commit rewrap)
- FOUND: 1f98ddc (test(04-09): add failing tests for menubar top-level order + File-submenu membership)
- FOUND: 355b602 (fix(04-09): Recent Files + Batch are File submenus only (standalone QMenu construction))
- FOUND: dcef7f7 (test(04-09): add failing tests for toolbar first-action Open Folder + File-menu retention)
- FOUND: 47212e8 (fix(04-09): toolbar first action is Open Folder (Ctrl+Shift+O), Open Image stays in File menu)

## Next Phase Readiness

- UAT test 1's mechanical contract is fully closed: overlay wraps/fits INSIDE the box (no horizontal overshoot), the font adapts to the box size within the [10,28] clamp with a bounded shrink-to-fit floor, resize commits re-wrap once per drag, the menubar shows exactly the six core menus with Recent Files + Batch as File submenus, and the toolbar's open action is Open Folder — ready for the UAT re-test on real artwork (the visual fit-in-box judgment, D4).
- The fit-loop seam (`refresh_text_overlay` + the `_OVERLAY_FIT_*` constants) is the single adaptation point for future text-surface work; the standalone-QMenu pattern is the precedent for any future submenu that must stay out of the menubar top level.

---
*Phase: 04-ocr-recognition-text-editing*
*Completed: 2026-08-08*

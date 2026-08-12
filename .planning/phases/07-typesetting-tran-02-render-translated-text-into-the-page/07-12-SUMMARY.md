---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
plan: 12
subsystem: ui
tags: [font, qfontcombobox, qsortfilterproxymodel, qt, gsd-gap-closure]

# Dependency graph
requires:
  - phase: 07-typesetting-tran-02-render-translated-text-into-the-page
    provides: 07-11 (Font row with Set-as-Default button, styling-section empty-state gate)
provides:
  - "Contains/substring search for the font dropdown: 'Wild Words' now finds 'CC Wild Words' (G-07-2)"
  - "QSortFilterProxyModel pattern for a filtered QFontComboBox view — the source family list stays intact"
affects: [verify-work (G-07-2 UAT), future font-picker improvements]

actuals:
  tokens: 2950  # chars/4 over the realized diff (plan estimated 15000 — over-estimate, low confidence)
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "QSortFilterProxyModel over a QFontComboBox's own model with the source reparented to the proxy BEFORE combo.setModel (QComboBox deletes its previously-owned model — the plain wiring destroys the source and empties the dropdown)"
    - "blockSignals + loaded-family restore around every proxy update: filter row-churn moves the combo's current index (a spurious currentTextChanged on every keystroke would commit a wrong font)"
    - "QRegularExpression.escape on every keystroke — user filter text is a literal substring, never regex syntax (ASVS V5 / T-07-20)"

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/inspector_panel.py
    - tests/test_gui_inspector_styling.py

key-decisions:
  - "Keep the plan's primary mechanism (proxy over the combo's own model) with a two-line ownership fix: `_font_source.setParent(self._font_proxy)` before `font_combo.setModel(proxy)` — the probe proved the literal wiring deletes the source (empty dropdown), NOT the documented delegate fallback"
  - "Selection-preservation guard in `_on_font_filter_changed`: combo signals blocked during the proxy update + the loaded family (or 'Mixed' sentinel) restored to the display — filter churn can never re-emit currentTextChanged with a different family"
  - "No popup-refresh wiring needed: the combo's view model IS the proxy and updates live (probe-verified) — Task 2's conditional 'if the popup needs showPopup()...' did not trigger"
  - "The filter is cleared on clear()/load_box/load_multi_selection (textChanged -> the single setFilterRegularExpression site resets to the full list) — it can never leak into a load"

requirements-completed: [TRAN-02]

# Metrics
duration: 38min
completed: 2026-08-11
status: complete
---

# Phase 07 Plan 12: Font Dropdown Contains Search (G-07-2) Summary

**G-07-2 closed: the font dropdown now has a contains/substring search — a 'Filter fonts…' QLineEdit above the Font row drives a QSortFilterProxyModel (case-insensitive, escaped-regex, column 0) over the QFontComboBox's own model, so typing 'Wild Words' surfaces 'CC Wild Words' — while the source family list, the 'Mixed' load path, and the 07-11 Set-as-Default button stay untouched.**

## Performance

- **Duration:** ~38 min
- **Tasks:** 2 (Task 1 TDD: RED -> GREEN commits; Task 2 auto)
- **Commits:** 3 (1 RED test + 2 feat)
- **Files modified:** 2

## Accomplishments

- `font_filter_edit` — a 'Filter fonts…' QLineEdit (clear button, tooltip, dark-theme QSS tokens incl. the `:disabled` state) added directly above the Font row in the styling section.
- `_font_proxy` — a `QSortFilterProxyModel` (case-insensitive, filter column 0) whose SOURCE is the QFontComboBox's own model. The source is reparented to the proxy **before** `font_combo.setModel(proxy)` — the probe showed the literal plan wiring makes QComboBox's setModel delete its previously-owned model, destroying the proxy's source (0 rows, empty dropdown). With the reparent, the source stays intact (266 families on this machine, `full == len(QFontDatabase.families())` pinned by test).
- `_on_font_filter_changed` — `textChanged` -> `setFilterRegularExpression(QRegularExpression(QRegularExpression.escape(text), CaseInsensitiveOption))` — the single `setFilterRegularExpression` call site (grep gate == 1). The combo's signals are blocked around the update and the loaded family / 'Mixed' sentinel is restored to the display: the proxy's row churn would otherwise move the combo's current index and re-emit `currentTextChanged` with a DIFFERENT family — a spurious font commit on every keystroke (probe-verified: filter-away sets currentText `''`, then position-drift shows row 0 `'8514oem'`).
- Filter clearing in `clear()` / `load_box` / `load_multi_selection` (the clear emits `textChanged("")` -> the proxy resets to the full list) — the filter never leaks into a load; the 'Mixed' sentinel load path and `setCurrentText` for any family keep working through the proxy (probe + tests).
- The filter joins `_set_fields_enabled` — disabled in the empty state, enabled with a selection, exactly like the other styling controls.
- Popup verification: the combo's popup view model IS the proxy and reflects the filter live — no `showPopup()`-refresh wiring was needed (Task 2's conditional).
- Full suite: **714 passed, 0 failed** (712 baseline from 07-11 + 2 new tests; the plan's "687 + ~2 = 700" assumed the older 07-VERIFICATION baseline).

## Task Commits

Each task committed atomically:

1. **Task 1: RED-GREEN — contains-match filter + proxy model**
   - `97ad8d8` (test) — `test_font_filter_contains_match` (RED gate: fails pre-fix with no filter widget)
   - `32a0e34` (feat) — filter QLineEdit + QSS, proxy wiring with the source-reparent fix, escaped-regex handler with the selection-preservation guard, clear-on-load
2. **Task 2: interaction polish + the 'CC Wild Words' scenario pin**
   - `975da5e` (feat) — filter joins the empty-state gate; `test_font_filter_contains_match_scenario` (trailing-word query surfaces its multi-word family, popup view = proxy, selection never drifts, load clears a stale filter)

## Files Created/Modified

- `manga_ai_studio/gui/inspector_panel.py` — `font_filter_edit`, `_font_proxy`, `_on_font_filter_changed`, QLineEdit QSS tokens, filter-clearing in `clear()`/`load_box`/`load_multi_selection`, `_set_fields_enabled` entry, QtCore/QtWidgets import extensions
- `tests/test_gui_inspector_styling.py` — 2 new tests (contains-match RED gate; user-report scenario + first-class-control behavior)

## Decisions Made

- **Primary mechanism kept with an ownership fix, not the fallback:** the plan's documented fallback (find-as-you-type on the native model) was only for a proxy that breaks the preview delegate — the probe showed the real failure is worse: `combo.setModel(proxy)` deletes the source (empty dropdown). Reparenting the source to the proxy first preserves the exact plan mechanism (proxy over the QFontComboBox's own model; roles pass through identically — FontRole is `None` on this stack both with and without the proxy, so rendering is byte-identical).
- **Selection-preservation guard (Rule 2 — correctness):** without `blockSignals` + display-restore, typing in the filter box commits font changes to the selected box (currentTextChanged re-emission via index drift). The guard keeps the filter display-only; commits fire only on an active row pick.
- **Single filter-reset site:** load-path clearing goes through the line-edit's `textChanged` (no second `setFilterRegularExpression` call) — keeps the grep gate at exactly 1 and the reset logic in one place.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] The literal proxy wiring empties the dropdown**
- **Found during:** Task 1 probe (before implementation)
- **Issue:** `QComboBox.setModel` deletes the model the combo previously owned (its internal family list). `font_combo.setModel(self._font_proxy)` therefore destroyed the proxy's source — probe showed `proxy.rowCount() == 0` even with an empty filter (empty dropdown), and `setCurrentText` assertions became vacuous.
- **Fix:** reparent the source to the proxy first (`_font_source.setParent(self._font_proxy)`) so the ownership-delete skips it — the combo only deletes models it parents. Two lines; the plan's primary mechanism survives as designed.
- **Files modified:** `manga_ai_studio/gui/inspector_panel.py`
- **Commit:** `32a0e34`

**2. [Rule 2 - Missing critical functionality] Selection-drift guard against spurious font commits**
- **Found during:** Task 1 probe
- **Issue:** filter row-churn moves the combo's current index (rows above the selection disappear -> index -1 or position drift to a different row) and re-emits `currentTextChanged` with a DIFFERENT family — typing in the filter would commit a font change to the selected box on every keystroke (probe: `currentText` became `''`, then `'8514oem'` after clear).
- **Fix:** in `_on_font_filter_changed`, block the combo's signals around the proxy update and restore the loaded family (or 'Mixed') to the display. Filtering is now display-only; commits fire only on an active pick.
- **Files modified:** `manga_ai_studio/gui/inspector_panel.py`
- **Commit:** `32a0e34`

Notes that are not deviations:
- **QLineEdit QSS tokens did not exist** in `_INSPECTOR_QSS` despite the plan's "tokens already exist" note — added them (dark bg/border + `:disabled`) so the filter matches the panel theme.
- **No popup-refresh wiring:** the plan's "if the popup needs `combo.showPopup()` after a filter change to refresh the view, wire that" did not trigger — the popup view's model is the proxy and updates live (probe-verified).
- **Test-count baseline:** the plan's "687 + ~2 = 700" assumed the 07-VERIFICATION baseline; 07-10/07-11 had already moved the suite to 712. This plan added 2 tests -> 714.
- The fallback documented in the plan was NOT used (its trigger — the proxy breaking the preview delegate — never occurred; roles pass through unchanged).

## Threat Flags

None — the only new surface (filter input -> regex filter expression) is the plan's own T-07-20/T-07-21 register entries, mitigated as specified: `QRegularExpression.escape` on every keystroke (2 call sites, grep gate >= 1), the view-level proxy never mutates the source, and the clear button + load-time clearing guarantee the filter can never wedge the dropdown.

## Issues Encountered

- The offscreen Qt platform plugin returns an EMPTY font database (`QFontDatabase.families() == []`) on this stack — probes and the new tests must run on the default (windows) platform, which the suite already uses (266 families). No production impact; noted for future font-DB-driven tests.
- `QFontDatabaseModel` / `QFontComboBoxModel` are not importable from PySide6 6.10.1 (`ImportError` on both QtGui and QtWidgets) — the combo's internal model (exposed as `QStringListModel`) is the only viable source, which is what the plan prescribed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-07-2 closed: typing any part of a font name filters the dropdown to contains-matches (case-insensitive, escaped, restorable); the 'Wild Words' -> 'CC Wild Words' shape is pinned by test on the real font DB.
- The Set-as-Default button (07-11) is unaffected (reads `currentText`; its tests pass unchanged); the 'Mixed' multi-select load path and per-family commit paths are unbroken (existing styling + boxes modules pass UNCHANGED).
- Remaining phase-7 gaps still open: G-07-1 (vertical/Latin upright), G-07-5 (align_v on horizontal), G-07-6 (Ctrl+Z crash), G-07-7 (Mixed align override). (G-07-3 default font by 07-11; G-07-4 auto-fit grow by 07-10.)

## Self-Check: PASSED

- SUMMARY.md exists at `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-12-SUMMARY.md`
- Commits present: `97ad8d8` (T1 RED), `32a0e34` (T1 GREEN), `975da5e` (T2 feat)
- Grep gates: `setFilterRegularExpression` x1; `QRegularExpression.escape` x2 (>= 1) in `inspector_panel.py`
- Full suite: 714 passed, 0 failed (pinned interpreter, default platform)

---

*Phase: 07-typesetting-tran-02-render-translated-text-into-the-page*
*Plan 12 (G-07-2) completed: 2026-08-11*

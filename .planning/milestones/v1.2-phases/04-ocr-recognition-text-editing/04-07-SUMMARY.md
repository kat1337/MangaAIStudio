---
phase: 04-ocr-recognition-text-editing
plan: 07
subsystem: gui (Load Translations dialog + Auto-Number menu + parser-result report)
tags: [ocr, text-editing, manga-ocr, gui, qt, qdialog, translation-parser, reading-order, tdd, pytest-qt, d-15, d-16, d-17, d-18]
requires:
  - Phase 04 Plan 01 PageBox fields (bubble_no / manual_override) + set_translation (the D-13 MT seam)
  - Phase 04 Plan 02 translation_parser (parse_translations / apply_translations) + reading_order (assign_bubble_numbers with preserve-manual conflict policy)
  - Phase 04 Plan 04 BoxItem refresh_text_overlay / refresh_badge (incl. the manual-override amber border) + InspectorPanel bubble # commit (sets manual_override=True)
  - Phase 04 Plan 06 _build_text_menu (Text menu between View and Tools) + _refresh_action_states + _show_transient_status + Pitfall-8 detach pattern
provides:
  - manga_ai_studio.gui.load_translations_dialog.LoadTranslationsDialog(QDialog) — paste + file-import front-ends; returns (text, page_index); never parses/mutates boxes (RESEARCH §Pitfall 3 separation)
  - MainWindow._open_load_translations() / _apply_translations(text, page_index) / _show_translation_report(applied, skipped_total, page_no) — Plan 02 parser glue + ONE batch BOXES snapshot + parser-result report
  - MainWindow._auto_number(rtl) / _auto_number_rtl() / _auto_number_ltr() — Plan 02 assign_bubble_numbers glue + badge refresh + ONE batch BOXES entry + "Numbered {n} boxes (RTL/TB)/(LTR/TB)." transient
  - Text menu additions: Auto-Number submenu (RTL (Manga) / LTR (Manhwa)) + Load Translations… action
affects:
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/load_translations_dialog.py
  - tests/test_gui_boxes.py
tech-stack:
  added: []
  patterns:
    - Pure-collector QDialog (RESEARCH §Pitfall 3 separation): the dialog stores (paste text, page index) and accept()s; the MainWindow runs parse + apply + report — no box mutation inside the dialog
    - Both Load Translations and Auto-Number capture a CR-01 before-state boxes_snapshot() and emit boxes_modified ONCE (UI-SPEC §20 batch-undo entry); the apply path detaches each snapshot payload via copy.copy BEFORE the setter mutation (Pitfall-8 push-side, the 04-05/04-06 pattern)
    - No algorithm logic in the GUI: the dialog + handlers call the Plan 02 pure-Python modules verbatim (strict regex parser, XY-Cut reading order, preserve-manual policy)
    - QFileDialog.getOpenFileName user-chosen *.txt + open(path, "r", encoding="utf-8") + OSError/UnicodeDecodeError -> "Couldn't read '{filename}'." (threat T-4-16; UI-SPEC §Copywriting)
    - Parser-result report = non-modal informational QMessageBox (ASVS V5 soft-skip: unmatched bubble numbers + unparseable/SFX lines combine into one user-facing skipped total; zero applied -> the no-matches path copy)
    - Dark QSS dialog mirroring the InspectorPanel/ToolsPanel tokens (#232328/#2d2d33/#3a3a42/#e8e8ea, accent-default Apply button)
key-files:
  created:
    - manga_ai_studio/gui/load_translations_dialog.py
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_boxes.py
key-decisions:
  - "Dialog is a PURE COLLECTOR (RESEARCH §Pitfall 3): _on_apply stores result_text/result_page_index and accept()s; _open_load_translations hands them to _apply_translations which runs parse_translations + apply_translations, refreshes overlays/badges, and pushes ONE batch BOXES snapshot (UI-SPEC §20)."
  - "Non-current pages (multi-page files, 'Page N:' markers) apply to ImageFile.boxes in place WITHOUT a BOXES push — the undo stack is per-page (reset_history on page switch), so pushing another page's snapshot onto the current page's stack would corrupt undo. The plan's 'push ONE snapshot' must-have applies to the current-page apply (where the user sees the result); non-current applies surface when the user navigates there."
  - "The parser-result report combines unmatched + skipped into ONE user-facing skipped total ('{unmatched + skipped} line(s) did not match...') per the UI-SPEC copy's single-skipped-total shape; the report's page number is 1-indexed (matches the status-bar 'Page {n} / {total}' convention)."
  - "_auto_number emits boxes_modified ONLY when count > 0 — an all-manual-override page is a no-op edit, and a no-op undo entry would make Ctrl+Z restore nothing (the plan's emit recipe is followed for the real case; count==0 skips the empty entry)."
  - "_auto_number returns None per the plan signature; the status transient fires with the actual count ('Numbered 0 boxes (RTL/TB).' for an all-manual page)."
  - "Load Translations… action is enabled with just an open page (no box requirement) — a boxless page reports the no-matches copy; Auto-Number actions require >= 1 box (mirrors action_ocr_all gating)."
  - "Task 3 checkpoint auto-approved under auto_advance=true + human_verify_mode=end-of-phase (gate='blocking', NOT blocking-human/package-legitimacy) — the established project cadence (plans 03-03/03-04/04-04/04-05/04-06 identical); the 9 manual checks (real manga page) defer to the end-of-phase UAT gate."
requirements-completed: [TEXT-05]
coverage:
  - id: D1
    description: "LoadTranslationsDialog (paste + file-import front-ends): QComboBox page selector (current page default), mono QPlainTextEdit paste area with the UI-SPEC placeholder, 'Load from File…' (QFileDialog *.txt, UTF-8 read into the paste area, OSError/UnicodeDecodeError -> 'Couldn't read '{filename}'.' error dialog), [Cancel] [Apply]; returns (text, page_index) via accept() without parsing or mutating boxes (RESEARCH §Pitfall 3 separation)."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_load_translations_dialog_has_contracted_widgets"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_load_translations_dialog_apply_returns_text_and_page"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_load_translations_dialog_load_file_populates_paste_area"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_load_translations_dialog_load_file_error_dialog"
        status: pass
    human_judgment: false
  - id: D2
    description: "MainWindow._open_load_translations/_apply_translations: runs Plan 02 parse_translations + apply_translations, fills set_translation on matched boxes (D-13 MT seam), refreshes overlays/badges, pushes ONE batch BOXES snapshot (UI-SPEC §20, Pitfall-8 detach), shows the parser-result report ('Applied N translation(s) to page X. M line(s) did not match...' / no-matches copy), file-read errors handled; Text menu 'Load Translations…' entry enabled iff page open + no op running."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_apply_translations_fills_set_translation_on_matched_boxes"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_apply_translations_shows_report_dialog"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_apply_translations_reports_unmatched_and_skipped"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_apply_translations_no_matches_copy"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_apply_translations_emits_one_boxes_modified"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_action_load_translations_enabled_with_page"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_menu_has_load_translations_entry"
        status: pass
    human_judgment: false
  - id: D3
    description: "Auto-Number menu actions: Text -> Auto-Number -> RTL (Manga) / LTR (Manhwa) call Plan 02 assign_bubble_numbers (rtl=True/False), refresh every BoxItem badge (new numbers + manual-override amber borders), push ONE batch BOXES entry, show the 'Numbered {n} boxes (RTL/TB)/(LTR/TB).' transient; preserve-manual conflict policy keeps manual_override boxes' numbers across re-auto with visible gaps (T-4-17); empty page no-op; actions enabled iff >= 1 box + no op running."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_rtl_assigns_right_to_left"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_ltr_assigns_left_to_right"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_preserves_manual_override"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_emits_one_boxes_modified"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_empty_page_noop"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_refreshes_badges"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_auto_number_shows_status_transient"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_action_auto_number_enabled_only_with_boxes"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_menu_has_auto_number_submenu"
        status: pass
    human_judgment: false
  - id: D4
    description: "End-of-phase human checkpoint (D-15/D-16/D-17): Auto-Number RTL/LTR ordering, batch undo, manual-override preservation, Load Translations paste + file + report, error UX on a real manga page."
    verification: []
    human_judgment: true
    rationale: "The automated pytest-qt suite covers the parser mechanics + reading-order algorithm + GUI wiring; the live feel of reading-order ordering / parser matching / override preservation against real manga artwork is the end-of-phase UAT gate. Auto-approved under auto_advance=true + human_verify_mode=end-of-phase (gate='blocking', not blocking-human/package-legitimacy) — the established project cadence."
metrics:
  duration: 7 min
  completed: 2026-08-07
  tasks: 2
  files: 3
status: complete
---

# Phase 04 Plan 07: Load Translations + Auto-Number Summary

Completed the TEXT-05 subsystem (D-15/D-16/D-17/D-18) as pure GUI glue over the Plan 02 pure-Python modules: the **LoadTranslationsDialog** (paste + file-import front-ends sharing `translation_parser`) with the parser-result report, and the **Auto-Number menu** (RTL Manga / LTR Manhwa via `reading_order.assign_bubble_numbers` with the preserve-manual conflict policy). Both flows push ONE batch BOXES snapshot (UI-SPEC §20 batch undo), refresh the BoxItem overlays/badges, and leave every algorithm decision in the Plan 02 modules — no parsing/reading-order logic in the GUI. The Text menu is now complete: Run OCR / OCR All Boxes (Ctrl+R) / Auto-Number ▸ RTL (Manga) + LTR (Manhwa) / Load Translations…. All tests green (135 passed in test_gui_boxes.py, 1 pre-existing deferred deselected; full suite 418 passed + 1 pre-existing deferred failure).

## What Was Built

### Task 1 — LoadTranslationsDialog + apply (TDD)

`manga_ai_studio/gui/load_translations_dialog.py` (NEW):

- **`LoadTranslationsDialog(QDialog)`** — the D-17 two-front-end dialog per UI-SPEC §20: a `QComboBox` page selector (default: current page; lists all open pages by name), a mono-font (`Consolas` 10) `QPlainTextEdit` paste area with the UI-SPEC placeholder copy ("Paste your translation list here, one line per box: [1]: … [SFX -3]: *sound effect*"), a "Load from File…" button, and **[Cancel] [Apply]**. Dark QSS mirroring the InspectorPanel/ToolsPanel tokens; `objectName("load_translations_dialog")`; window title "Load Translations".
- **`_on_load_file()`** — `QFileDialog.getOpenFileName(self, "Load Translations", "", "Text files (*.txt)")` (user-chosen path — no traversal surface, T-4-16); `open(path, "r", encoding="utf-8")` reads into the paste area so the user reviews before Apply; `OSError`/`UnicodeDecodeError` → `logger.error` + the UI-SPEC "Couldn't read '{filename}'." / "The file may be corrupt or in an unsupported format." dialog (Phase 1 file-unreadable copy pattern).
- **`_on_apply()`** — PURE COLLECTOR (RESEARCH §Pitfall 3 separation): stores `result_text`/`result_page_index` and `accept()`s. The dialog NEVER parses or mutates boxes; `get_text()` / `get_page_index()` hand the payload to the MainWindow.

`manga_ai_studio/gui/main_window.py`:

- **`_open_load_translations()`** — gathers page names from `self.image_files`, constructs the dialog with the current page index, and on `exec() == Accepted` calls `_apply_translations(dlg.get_text(), dlg.get_page_index())`.
- **`_apply_translations(text, page_index)`** — the Plan 02 parser glue: `parse_translations` → `(matches, skipped)`; current-page apply goes through the live BoxItems with a CR-01 before-state `boxes_snapshot()` (Pitfall-8 payload detach via `copy.copy` per payload before the setter mutation — the 04-05/04-06 pattern), `apply_translations` → `(applied, unmatched)`, overlay + badge refresh on every box, then ONE `boxes_modified.emit(before)` (UI-SPEC §20 batch entry). Non-current pages (multi-page files with "Page N:" markers) apply to `ImageFile.boxes` in place — the canvas refresh happens on navigation. ASVS V7 belt-and-suspenders: the whole parse/apply is try/except'd → `logger.error` + "Couldn't apply translations — see the log."
- **`_show_translation_report(applied, skipped_total, page_no)`** — non-modal informational report (UI-SPEC §Copywriting): success body "Applied {applied} translation(s) to page {n}. {unmatched + skipped} line(s) did not match a bubble number and were skipped." (the two skip sources combine into ONE user-facing total); `applied == 0` → the no-matches path copy ("No lines matched any bubble number on page {n}. Check that the bubble numbers in your text match the numbers on the canvas (Text → Auto-Number)."). No per-line modal (ASVS V5).
- **Text menu** — `action_load_translations` ("Load Translations…", UI-SPEC tooltip copy) after a separator; enabled iff a page is open AND no op running (`_refresh_action_states`).

### Task 2 — Auto-Number RTL/LTR + preserve-manual (TDD)

`manga_ai_studio/gui/main_window.py`:

- **`_auto_number(rtl)`** — Plan 02 glue: `from manga_ai_studio.core.reading_order import assign_bubble_numbers`; boxes = `[it.pagebox for it in self.canvas._box_items]`; empty page → no-op; CR-01 before-state `boxes_snapshot()` (fresh PageBoxes — bubble_no detached by construction, no payload mutation so no Pitfall-8 detach needed); `count = assign_bubble_numbers(boxes, rtl=rtl)`; on `count > 0` refresh EVERY badge (`refresh_badge` — new numbers + the manual-override amber borders) and emit `boxes_modified(before)` ONCE (UI-SPEC §20 batch entry); status-bar transient via the existing `_show_transient_status`: "Numbered {n} boxes (RTL/TB)." / "(LTR/TB)." (reverts to the box-count line after ~3 s).
- **`_auto_number_rtl()` / `_auto_number_ltr()`** — thin `rtl=True/False` wrappers.
- **Auto-Number submenu** in `_build_text_menu` — `text_menu.addMenu("Auto-Number")` with `action_auto_number_rtl` ("RTL (Manga)") + `action_auto_number_ltr` ("LTR (Manhwa)"), UI-SPEC tooltip copy, placed between the OCR actions and Load Translations…. Enabled iff a page is open with >= 1 box AND no op running (mirrors `action_ocr_all` gating).
- The preserve-manual conflict policy (D-16, T-4-17) and the XY-Cut ordering (D-15/D-18) both live in the Plan 02 `reading_order` module — verified end-to-end by the GUI tests (a manual-override box keeps its number + amber flag across re-auto while the sequence leaves a visible gap).

### Task 3 — Checkpoint:human-verify (auto-approved)

Config `auto_advance: true` + `human_verify_mode: end-of-phase`; the checkpoint is `gate="blocking"` (NOT `blocking-human`, NOT package-legitimacy) → auto-approved per the established project cadence (plans 03-03/03-04/04-04/04-05/04-06 identical). The automated portion is green (`test_gui_boxes.py` 135 passed, 1 deselected — the pre-existing deferred test). The 9 manual checks (RTL/LTR ordering on a real manga page, batch undo/redo, manual-override preservation, parser matching + report, file import, error UX) defer to the end-of-phase UAT gate.

## Verification

```
python -m pytest tests/test_gui_boxes.py -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip
# 135 passed, 1 deselected  (126 prior + 20 new: 11 Task 1 + 9 Task 2)

python -m pytest tests/test_gui_boxes.py -x -q -k "apply_translations or load_translations or text_menu_has_load or action_load_translations"
# 11 passed (Task 1 RED/GREEN gate)

python -m pytest tests/test_gui_boxes.py -x -q -k "auto_number or text_menu_has_auto_number or action_auto_number"
# 9 passed (Task 2 RED/GREEN gate)

python -m pytest tests/ -q
# 418 passed, 1 failed (PRE-EXISTING — see Deferred Issues)
```

Acceptance criteria verified (all grep counts exact):
- Task 1: `class LoadTranslationsDialog` = 1; `QPlainTextEdit|QFileDialog|QComboBox` = 13 (>= 3); `def _open_load_translations|def _apply_translations` = 2; `from manga_ai_studio.core.translation_parser import` = 1 (>= 1); `action_load_translations` = 6 (>= 2). Paste "[1]: hello\n[2]: world" + Apply fills `set_translation` on bubbles 1/2 PASS; report shows on Apply PASS; unmatched numbers reported (no crash) PASS; ONE `boxes_modified` emit for the batch PASS; file-read error dialog PASS.
- Task 2: `def _auto_number\b|def _auto_number_rtl|def _auto_number_ltr` = 3; `from manga_ai_studio.core.reading_order import` = 1 (>= 1); `action_auto_number_rtl|action_auto_number_ltr` = 12 (>= 2); `addMenu("Auto-Number")` = 1. RTL assigns 1..N right-to-left top-to-bottom PASS; LTR left-to-right PASS; manual_override box keeps its number across re-auto PASS; ONE `boxes_modified` emit PASS; empty-page no-op PASS; badges refreshed PASS; status transients PASS; action enable-states PASS.

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-07T20:44:02Z
- **Completed:** 2026-08-07T20:50:47Z
- **Tasks:** 2 implementation tasks (Task 3 checkpoint auto-approved under end-of-phase verify mode)
- **Files modified:** 3 (1 created, 2 modified; tests extended by 20 tests)

## Task Commits

Each task was committed atomically (RED `test(...)` commit → GREEN `feat(...)` commit per the project's per-task TDD convention):

1. **Task 1 RED:** `e303480` (test) — add failing tests for Load Translations dialog + apply; 11 failed (ModuleNotFoundError for the new dialog module + AttributeError: no `_apply_translations`/`action_load_translations`)
2. **Task 1 GREEN:** `bb7835f` (feat) — implement LoadTranslationsDialog (paste + file-import) + Text menu Load Translations… apply (TDD); 11/11 new tests pass (1 test-side assertion fix landed inside GREEN: the unmatched box's payload is `None`, not `.translation`)
3. **Task 2 RED:** `3eac846` (test) — add failing tests for Auto-Number RTL/LTR + preserve-manual; 9 failed (AttributeError: no `_auto_number` + menu/action AssertionErrors)
4. **Task 2 GREEN:** `cbdf033` (feat) — implement Auto-Number RTL (Manga) / LTR (Manhwa) + preserve-manual via reading_order (TDD); 9/9 new tests pass
5. **Docs commit:** (after this SUMMARY) — completes the plan

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified

- `manga_ai_studio/gui/load_translations_dialog.py` (NEW) — `LoadTranslationsDialog` (page combo + mono paste area + Load from File… + Cancel/Apply), `_on_load_file` (QFileDialog *.txt, UTF-8 read, error dialog), `_on_apply` (pure collector), `get_text`/`get_page_index` accessors, dark QSS.
- `manga_ai_studio/gui/main_window.py` — `_open_load_translations` / `_apply_translations` / `_show_translation_report` + `_auto_number` / `_auto_number_rtl` / `_auto_number_ltr` + `action_load_translations` + Auto-Number submenu (`action_auto_number_rtl`/`action_auto_number_ltr`) in `_build_text_menu` + `_refresh_action_states` additions + `QDialog`/`LoadTranslationsDialog` imports.
- `tests/test_gui_boxes.py` — `_seed_boxes_window` helper + 20 new tests (11 Task 1 + 9 Task 2).

## Decisions Made

See the `decisions:` frontmatter for the full list. Highlights:

- The dialog is a PURE COLLECTOR (RESEARCH §Pitfall 3): it returns `(text, page_index)`; the MainWindow runs the parser, applies, refreshes, and reports — no box mutation in the dialog.
- Non-current-page applies target `ImageFile.boxes` in place WITHOUT a BOXES push (the undo stack is per-page — `reset_history` on page switch — so a cross-page snapshot would corrupt undo). The one-batch-entry contract is honored on the current page.
- One user-facing "skipped" total (unmatched + unparseable/SFX) per the UI-SPEC copy shape; the report's page number is 1-indexed.
- `_auto_number` emits `boxes_modified` only when `count > 0` (an all-manual page is a no-op edit — no empty undo entries).
- Checkpoint Task 3 auto-approved under `auto_advance=true` + `human_verify_mode=end-of-phase`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Unmatched-box test assertion touched a None payload**
- **Found during:** Task 1 GREEN (first test run — `test_apply_translations_fills_set_translation_on_matched_boxes` failed)
- **Issue:** the plan's recipe-driven test asserted `items[2].pagebox.payload.translation is None` for the unmatched box, but an unmatched box never gets a payload created (`set_translation` → `_ensure_payload` is only called on a match) — `payload` itself is `None`, so `.translation` raised `AttributeError`. The implementation was correct; the assertion assumed a payload existed.
- **Fix:** the test now asserts `items[2].pagebox.payload is None` — the stronger "never touched" statement (no payload was even created).
- **Files modified:** `tests/test_gui_boxes.py`
- **Committed in:** `bb7835f` (Task 1 GREEN)

**2. [Plan artifact - snapshot scope] Non-current-page apply pushes no BOXES entry**
- The plan's must_haves ("both push ONE BOXES snapshot") and its action recipe ("apply to the ImageFile.boxes at that index without refreshing the canvas") conflict for non-current pages. The undo stack is per-page (`reset_history` on page switch — UI-SPEC surface 8), so a snapshot of another page's boxes pushed onto the current page's stack would restore the WRONG page's boxes on Ctrl+Z. Implemented the action recipe: current-page apply pushes the one batch entry; non-current applies are in-place with no push (the canvas refresh happens on navigation). Documented for the verifier.

**3. [Plan artifact - emit scope] Auto-Number emits only when count > 0**
- The plan recipe emits `boxes_modified` unconditionally after `assign_bubble_numbers`; with an all-manual-override page, count == 0 and nothing changed — an unconditional emit would push an empty no-op undo entry. `_auto_number` emits only on `count > 0` and still shows the "Numbered 0 boxes (…)" transient (the no-op case is honest). The tests assert ONE emit for the real batch case.

**Total deviations:** 1 test-side fix (Rule 3) + 2 documented plan artifacts. No architectural changes (Rule 4), no auth gates, no package installs.

## Authentication Gates

None. The Load Translations file-import reads only user-chosen files via `QFileDialog` (no network, no credentials); the Auto-Number flow is fully local.

## Known Stubs

None that block the plan goal. The parser's `page_no` parameter is accepted but does not change match logic (forward-compat per Plan 02 — intentional). The dialog's multi-page file markers ("Page N:") are consumed by the Plan 02 `PAGE_MARKER_RE` (silent structural skip); the file front-end applies to ALL open pages via the page selector — the user picks the target page after loading the file into the paste area (executor's documented choice from the plan's "loads into the paste area OR applies directly" option).

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): 1px real-event drag-coordinate rounding. Re-confirmed failing in this plan's full-suite run (`1 failed, 418 passed`); verified against pristine pre-04-01 source in plans 04-01..04-06. Logged in deferred-items.md; not fixed.
- **Inspector commit path payload aliasing (04-04, Pitfall 8 push-side)** — still open; the new plan-07 apply path applies the proven 04-05 detach pattern, so the aliasing remains confined to the 04-04 Inspector handlers. Logged in deferred-items.md; out of scope.

## Threat Surface

No new security-relevant surface beyond the plan's `<threat_model>` — the dialog, apply path, and auto-number handlers add no endpoints, no auth paths, and no new file-access patterns beyond the contracted user-chosen `QFileDialog` read:

- **T-4-15 (DoS — oversized paste / weird unicode):** the paste text goes straight to the Plan 02 strict anchored-regex parser, which skips + counts malformed lines and never raises (ASVS V5/V7); the MainWindow additionally wraps parse + apply in try/except with a friendly dialog (belt-and-suspenders). `test_apply_translations_reports_unmatched_and_skipped` + the parser's Plan-02 never-raises tests.
- **T-4-16 (Tampering — file-import path traversal):** the path comes only from `QFileDialog.getOpenFileName` (user-chosen); read with `open(path, "r", encoding="utf-8")`; `OSError`/`UnicodeDecodeError` caught → friendly dialog. `test_load_translations_dialog_load_file_error_dialog`.
- **T-4-17 (Tampering — auto-number overwriting manual overrides):** `assign_bubble_numbers` (Plan 02) skips `manual_override` boxes (preserve-manual policy) — the flag and number survive re-auto. `test_auto_number_preserves_manual_override`.

## TDD Gate Compliance

Plan frontmatter `type: execute`; both implementation tasks are `tdd="true"`. Gate sequence observed per task (separate RED `test(...)` commit then GREEN `feat(...)` commit):

- **Task 1:** RED `e303480` — 11 new tests failed (ModuleNotFoundError for `load_translations_dialog` + AttributeError for `_apply_translations`/`action_load_translations` — confirmed failing before implementation). GREEN `bb7835f` — all 11 pass.
- **Task 2:** RED `3eac846` — 9 new tests failed (AttributeError for `_auto_number` + menu/action AssertionErrors — confirmed failing before implementation). GREEN `cbdf033` — all 9 pass.

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — the single test-side fix landed inside the Task 1 GREEN commit.

## Self-Check: PASSED

Modified files:
- FOUND: manga_ai_studio/gui/load_translations_dialog.py
- FOUND: manga_ai_studio/gui/main_window.py
- FOUND: tests/test_gui_boxes.py

Commits:
- FOUND: e303480 (test(04-07): add failing tests for Load Translations dialog + apply (load_translations) (TDD))
- FOUND: bb7835f (feat(04-07): implement LoadTranslationsDialog (paste + file-import) + Text menu Load Translations… apply (TDD))
- FOUND: 3eac846 (test(04-07): add failing tests for Auto-Number RTL/LTR + preserve-manual (auto_number) (TDD))
- FOUND: cbdf033 (feat(04-07): implement Auto-Number RTL (Manga) / LTR (Manhwa) + preserve-manual via reading_order (TDD))

## Next Phase Readiness

- TEXT-05's three delivery paths are all wired: manual typing in the Inspector (04-04), paste/import via the Load Translations parser (D-15/D-17), and the reading-order auto-number + manual-override subsystem the parser keys off (D-15/D-16/D-18). The page-global bubble numbers (D-18) render on the BoxItem badges with the amber manual-override border.
- The Text menu is complete (Run OCR / OCR All Boxes Ctrl+R / Auto-Number ▸ RTL (Manga) + LTR (Manhwa) / Load Translations…), all actions gated on `_op_running`, all writes land through the Plan 01 setters into the same PageBox fields the undo layer snapshots (edited/bubble_no/manual_override travel in the BOXES snapshots).
- Phase 4 is now fully implemented (plans 04-01..04-07). Phase 5's `_ocr.json` export reads the same `payload.text` / `payload.translation` fields this phase fills; the end-of-phase UAT gate (VALIDATION.md) covers the deferred manual checks from plans 04-04/04-05/04-06/04-07.

---
*Phase: 04-ocr-recognition-text-editing*
*Completed: 2026-08-07*

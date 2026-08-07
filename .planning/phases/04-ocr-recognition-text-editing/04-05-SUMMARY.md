---
phase: 04-ocr-recognition-text-editing
plan: 05
subsystem: gui (inline text editor overlay)
tags: [ocr, text-editing, gui, qt, qgraphicsview, qgraphicsproxywidget, qtextedit, tdd, pytest-qt, ime, inline-editing]
requires:
  - Phase 04 Plan 01 PageBox Phase 4 setters (set_recognized_text_edited D-04 edited=True / set_translation / has_recognized_text / copy() payload detach)
  - Phase 04 Plan 04 BoxItem text overlay (z=120) + badge (z=140) + refresh_text_overlay / refresh_badge (the display objects the commit refreshes)
  - Phase 04 Plan 04 InspectorPanel (the secondary edit home for the non-focus field; the vertical checkbox is the D-06 no-op seam)
  - Phase 03 EditorCanvas boxes_modified signal + boxes_snapshot() (CR-01 pre-state push contract) + _box_item_at hit-test + box-layer dispatch
provides:
  - manga_ai_studio.gui.inline_editor.InlineEditor (owns QGraphicsProxyWidget(QTextEdit), z=1100, scene-parented; enter/commit/cancel/is_active/proxy_scene_rect)
  - manga_ai_studio.gui.inline_editor._EditorTextEdit (Enter commits, Shift+Enter newline, Esc cancels; PLAIN text ASVS V5)
  - manga_ai_studio.gui.box_item.BoxItem.enter_edit_mode() / exit_edit_mode() / set_edit_mode(bool) (D-07 move/resize disable; handles non-interactive while editing)
  - manga_ai_studio.gui.canvas.EditorCanvas.mouseDoubleClickEvent (double-click box -> select + open editor)
  - manga_ai_studio.gui.canvas.EditorCanvas._inline_editor instance + inline-editor-active guard at the TOP of mousePressEvent (RESEARCH Pitfall 3 — click-away commit, inside-press pass-through)
  - Esc-while-editing cancel (highest priority, box stays selected) + F2 keyboard trigger
  - EditorCanvas._commit_inline_editor_if_active() seam at the top of set_boxes (stale editor never dangles)
affects:
  - manga_ai_studio/gui/inline_editor.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - tests/test_gui_boxes.py
tech-stack:
  added: []
  patterns:
    - QGraphicsProxyWidget(QTextEdit) scene-parented transient overlay (UI-SPEC §15 — first proxy widget in the project; parent to the SCENE never the BoxItem)
    - inline-editor-active guard as the FIRST branch of mousePressEvent (RESEARCH Pitfall 3 — commit-on-click-away by scene-rect hit-test, not Qt focus-out signaling)
    - keyPressEvent overrides on the embedded QTextEdit for editor-scoped commit/cancel keys (Enter/Shift+Enter/Esc)
    - CR-01 pre-state snapshot push with push-side payload detach (Pitfall 8: _materialize_snapshot copies at push-time, AFTER the in-place setter mutation)
    - BoxItem edit-mode flag + handle mouse-acceptance toggle (D-07 belt-and-suspenders under the canvas guard)
key-files:
  created:
    - manga_ai_studio/gui/inline_editor.py
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_boxes.py
decisions:
  - InlineEditor takes the CANVAS (not the bare scene) at construction — the commit path needs canvas.boxes_snapshot() + canvas.boxes_modified.emit; the scene is reached via canvas.scene(). Superset of the plan's "takes the scene reference".
  - The proxy z-order constant is the literal call setZValue(1100) (the plan's acceptance grep) rather than a named constant — one usage site, plan action text verbatim.
  - enter() on a DIFFERENT active box commits the previous edit first (the plan's "committing is safer" pick); re-entering the SAME box re-focuses without discarding uncommitted text.
  - commit() captures the CR-01 BEFORE snapshot and detaches each snapshot payload via copy.copy BEFORE the in-place setter mutation — _materialize_snapshot (history_manager) copies at push-time which runs AFTER the mutation; without the detach, undo would restore the post-edit text (Pitfall 8 push-side, the Inspector path's latent aliasing avoided here).
  - mouseDoubleClickEvent also selects the double-clicked box before opening the editor (UI-SPEC §15 "the box stays selected" contract holds when entering via double-click).
  - Task 3 checkpoint:human-verify auto-approved under auto_advance=true + human_verify_mode=end-of-phase (not gate=blocking-human, not package-legitimacy) — the 9 manual checks (tactile feel, IME, click-away on real artwork) defer to the end-of-phase UAT gate, mirroring plans 03-03/03-04/04-04.
actuals:
  tokens: 20000
  tasks: 2
  commits: 4
requirements-completed: [TEXT-04]
coverage:
  - id: D1
    description: "Double-clicking a box opens a transient QGraphicsProxyWidget(QTextEdit) overlay positioned/sized on the box rect inset 2px (D-05/D-07) — scene-parented (NOT the box, §15 anti-pattern), z=1100 above the cursor, one reused instance."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_proxy_created_on_scene_z1100_hidden"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_enter_shows_proxy_populated_and_positioned"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_canvas_double_click_box_opens_inline_editor"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_canvas_double_click_empty_canvas_noop"
        status: pass
    human_judgment: true
    rationale: "The overlay's ON-PAGE feel (editor framed by the box border on real artwork, IME candidates — RESEARCH Pitfall 3's human-verify gate) is a tactile judgment the pytest-qt suite cannot make; deferred to the end-of-phase UAT gate."
  - id: D2
    description: "The inline editor edits the current-focus field per D-08: translation when present (non-empty payload.translation), else recognized text."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_focus_rule_translation_wins"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_enter_empty_box_opens_empty"
        status: pass
    human_judgment: false
  - id: D3
    description: "Enter or click-away commits via the PageBox setter (translation -> set_translation; recognized -> set_recognized_text_edited, the Plan 01 manual-edit setter) and pushes a BOXES snapshot (CR-01 pre-state); Esc cancels with no push (D-05). Shift+Enter inserts a newline."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_commit_translation_writes_set_translation"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_commit_recognized_sets_edited_true"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_recognized_commit_routes_through_edited_setter"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_commit_emits_boxes_modified_with_before_state"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_cancel_discards_no_emit"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_canvas_click_away_commits_inline_editor"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_canvas_esc_cancels_inline_editor_keeps_box_selected"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_enter_key_commits"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_shift_enter_inserts_newline"
        status: pass
    human_judgment: true
    rationale: "Click-away commit on a REAL press sequence (the guard firing before any other dispatch under live interaction, RESEARCH Pitfall 3) is exercised by synthesized events here; the tactile confirmation is the end-of-phase UAT gate."
  - id: D4
    description: "While the inline editor is active, single-click/move/resize are disabled (D-07): the mousePressEvent guard is the FIRST branch (inside-press -> widget, outside-press -> commit+consume); the BoxItem edit-mode flag + handle mouse-acceptance toggle are the item-level belt-and-suspenders."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_canvas_click_inside_editor_does_not_commit"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_canvas_edit_mode_drag_inside_editor_does_not_move_box"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_enter_sets_box_edit_mode"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_boxitem_set_edit_mode_toggles_handle_interactivity"
        status: pass
    human_judgment: false
  - id: D5
    description: "The edited flag is set True on recognized-field commit (D-04) via set_recognized_text_edited so re-OCR confirms before overwrite (T-4-09)."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_commit_recognized_sets_edited_true"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_recognized_commit_routes_through_edited_setter"
        status: pass
    human_judgment: false
  - id: D6
    description: "Vertical editing is a v1 no-op fallback (RESEARCH Pitfall 5): payload.vertical preserved as export metadata (Inspector checkbox, plan 04), the editor always renders horizontal — no rotation, no crash."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inline_editor_enter_shows_proxy_populated_and_positioned"
        status: pass
    human_judgment: false
    rationale: "The fallback is 'the editor renders horizontal always' — the absence of vertical behavior is the design; the plan-04 Inspector vertical checkbox (payload.vertical metadata) is the documented seam, already shipped and tested in 04-04."
metrics:
  duration: 22 min
  completed: 2026-08-07
  tasks: 2
  files: 4
status: complete
---

# Phase 04 Plan 05: Inline Text Editor (QGraphicsProxyWidget + QTextEdit) Summary

Delivered TEXT-04's primary edit surface as TDD: double-click (or F2) a box opens a transient `QGraphicsProxyWidget(QTextEdit)` overlay ON the box rect (inset 2px so the origin-coloured border stays visible), editing the D-08 current-focus field (translation when present, else recognized). Bare Enter or click-away commits via the PageBox setter and pushes a CR-01 before-state BOXES snapshot; Esc cancels with no push; Shift+Enter inserts a newline. While active, move/resize are disabled (D-07) by the inline-editor-active guard — the FIRST branch of `mousePressEvent` (RESEARCH Pitfall 3) — plus the BoxItem edit-mode flag. The D-04 `edited` flag is set True on recognized-field manual commits through the Plan 01 `set_recognized_text_edited` setter, so re-OCR must confirm before overwriting a manual correction (T-4-09). Vertical editing ships as the documented horizontal-only v1 fallback (RESEARCH Pitfall 5).

## What Was Built

### Task 1 — InlineEditor (QGraphicsProxyWidget + QTextEdit) + BoxItem edit-mode hooks (TDD)

`manga_ai_studio/gui/inline_editor.py` (NEW):

- **`InlineEditor`** — NOT itself a QGraphicsItem; it OWNS a `QGraphicsProxyWidget` **parented to the canvas SCENE** (the §15 CRITICAL anti-pattern: never parent to the BoxItem — parenting would inherit the box's transform and break the editor's coordinate system). One instance per canvas, reused + repositioned per edit session (§15 — never two editors on screen). `setZValue(1100)` (UI-SPEC §Z-order: above the brush cursor z=1000); hidden until `enter()`.
- **`_EditorTextEdit(QTextEdit)`** — the editor-scoped key semantics: bare `Enter`/`Key_Enter` commits (consumed — Qt's default inserts a newline in some configs), `Shift+Enter` inserts a newline (standard QTextEdit convention), `Esc` cancels. `setAcceptRichText(False)` (ASVS V5 — PLAIN text on OCR output, T-4-07 discipline). Chrome per §15: `#2d2d33` bg / `#e8e8ea` text / 3px `#0b0b0e` frame / 14px Liberation Sans via QSS.
- **`enter(box_item)`** — computes the D-08 focus field (`translation` when `payload.translation` is non-empty, else `recognized`), populates the QTextEdit with the focus text (str/list-aware; defensive getattr against non-TextBlock payloads), positions the proxy at `sceneBoundingRect().topLeft() + 2` and sizes it `w-4 × h-4` (the border stays visible around the editor), shows + focuses it, and flips the box's edit mode on (D-07). One-instance rule: entering a DIFFERENT box while active commits the previous edit first (the plan's "committing is safer" pick); re-entering the SAME box just re-focuses (uncommitted text preserved).
- **`commit()`** — no-op when inactive; unchanged text is a silent no-op (hide, no push). A real edit captures the CR-01 **before** snapshot, **detaches each snapshot payload via `copy.copy` BEFORE the in-place setter mutation** (Pitfall 8 push-side: `_materialize_snapshot` copies at push-time, which runs AFTER this mutation — without the detach, undo would restore the post-edit text), then writes the focus field: translation → `pagebox.set_translation` (D-13 MT seam, `edited` untouched); recognized → `pagebox.set_recognized_text_edited` (the Plan 01 CENTRALIZED manual-edit setter — writes `payload.text` + sets `edited=True` with the payload-None guard; NEVER `set_recognized_text` / direct payload write). Refreshes `refresh_text_overlay()` + `refresh_badge()`, emits `boxes_modified(before)` (the same undo seam every box edit uses), tears down.
- **`cancel()`** — hide, restore edit mode, clear session; NO `boxes_modified` emit (D-05).
- **`is_active()` / `proxy_scene_rect()`** — the canvas guard's contract: active-state + the scene-rect hit-test for "is the click inside the editor?" (RESEARCH Pitfall 3).

`manga_ai_studio/gui/box_item.py`:

- **`enter_edit_mode()` / `exit_edit_mode()` / `set_edit_mode(active)`** — the D-07 item-level disable. `set_edit_mode(True)` stores `_edit_mode` and drops each CornerHandle's mouse acceptance (`NoButton`) — the handles stay VISIBLE (the box is still selected, §15) but cannot arm a resize; `set_edit_mode(False)` restores the construction-time acceptance (`_handle_rest_buttons`). The canvas dispatch guard is the PRIMARY disable; this is belt-and-suspenders.

### Task 2 — Canvas double-click dispatch + inline-editor-active guard (TDD)

`manga_ai_studio/gui/canvas.py`:

- **`EditorCanvas._inline_editor = InlineEditor(self)`** — constructed after `setScene` so the proxy parents to the scene. (Constructor takes the CANVAS, not the bare scene — commit needs `boxes_snapshot()` + `boxes_modified`; superset of the plan's wording.)
- **`mousePressEvent` guard — the FIRST branch** (RESEARCH Pitfall 3 contract, before pan/box/mask dispatch): if `_inline_editor.is_active()`: a press INSIDE `proxy_scene_rect()` → `super().mousePressEvent(event)` (the QTextEdit gets the click); a press OUTSIDE → `commit()` (click-away, same path as Enter). Either way the event is consumed — **no move/resize/select can start while editing (D-07)**. The guard never relies on Qt focus-out signaling (the documented QGraphicsProxyWidget focus/IME quirk).
- **`mouseDoubleClickEvent` (NEW — none existed)** — box layer visible + left button: `_box_item_at` hit-test → selects the box (UI-SPEC §15 "the box stays selected") + `enter(box_item)`; empty canvas / hidden layer / non-left → `super()`; while the editor is already active → `super()` (word-select inside the QTextEdit, never a re-entry).
- **Esc priority** (UI-SPEC §Shortcuts): editor active → `cancel()` + consume FIRST (box stays selected); else Phase 3 deselect; Phase 2 batch-cancel stays in MainWindow.
- **F2 trigger**: a box selected and not editing → `enter(selected_box)` (the keyboard alternative to double-click).
- **`_commit_inline_editor_if_active()`** at the top of `set_boxes` — page switch / detection / restore all rebuild the layer here; a stale editor never dangles over a removed box (mirrors the brush-stroke-commits-on-page-switch discipline).

### Task 3 — Checkpoint:human-verify (auto-approved)

Config `auto_advance: true` + `human_verify_mode: end-of-phase`; the checkpoint is `gate="blocking"` (NOT `blocking-human`, NOT package-legitimacy) → auto-approved per the established project cadence (plans 03-03/03-04/04-04 identical). The automated portion (`test_gui_boxes.py` minus the pre-existing deferred test) is green; the 9 manual checks (overlay-on-box feel, IME candidates, click-away commit, edit-mode drag, F2, focus rule on a real edit session) are deferred to the end-of-phase UAT gate — RESEARCH Pitfall 3 names exactly that gate as the IME test site.

## Verification

```
python -m pytest tests/test_gui_boxes.py -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip
# 93 passed, 1 deselected

python -m pytest tests/ -q
# 376 passed, 1 failed (PRE-EXISTING — see Deferred Issues)
```

Acceptance criteria verified (all grep counts exact):
- Task 1: `test -f inline_editor.py` (PASS), `class InlineEditor` (1), `QGraphicsProxyWidget` (5), `def enter|commit|cancel|is_active` (4), `setZValue(1100)` (1), `def enter_edit_mode|exit_edit_mode|set_edit_mode` box_item (3).
- Task 2: `def mouseDoubleClickEvent` (1), `_inline_editor` (14 >= 3), the guard is the first check of `mousePressEvent` (verified by reading — precedes the pan branch), `Key_F2` (1).
- Test-level: Enter commits via `set_translation` (translation focus) PASS; Esc cancels with no emit PASS; recognized-field manual edit calls `set_recognized_text_edited` + sets `edited=True` PASS (D-04/T-4-09); double-click opens the editor PASS; click-away commits PASS; Esc keeps the box selected PASS; edit-mode drag does not move the box PASS.

## Performance

- **Duration:** 22 min
- **Started:** 2026-08-07T20:04:54Z
- **Completed:** 2026-08-07T20:27:00Z
- **Tasks:** 2 implementation tasks (Task 3 checkpoint auto-approved under end-of-phase verify mode)
- **Files modified:** 4 (1 created, 3 modified)

## Task Commits

Each task was committed atomically (RED test → GREEN implementation per the project's per-task TDD convention):

1. **Task 1 RED:** `7804cdb` (test) — add failing tests for InlineEditor (QGraphicsProxyWidget + QTextEdit) + BoxItem edit-mode hooks
2. **Task 1 GREEN:** `980b14c` (feat) — implement InlineEditor (QGraphicsProxyWidget + QTextEdit) + BoxItem edit-mode hooks (TDD)
3. **Task 2 RED:** `2bc2817` (test) — add failing tests for canvas double-click dispatch + inline-editor-active guard
4. **Task 2 GREEN:** `406795a` (feat) — implement canvas double-click entry + inline-editor-active guard (TDD)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified

- `manga_ai_studio/gui/inline_editor.py` (NEW) — the §15 inline editor: `InlineEditor` + `_EditorTextEdit`, scene-parented proxy z=1100, enter/commit/cancel/is_active/proxy_scene_rect, D-08 focus rule, D-04 edited-setter commit path, CR-01 pre-state push with push-side payload detach.
- `manga_ai_studio/gui/box_item.py` — `enter_edit_mode`/`exit_edit_mode`/`set_edit_mode` + `_edit_mode` + `_handle_rest_buttons` (D-07 item-level disable).
- `manga_ai_studio/gui/canvas.py` — `_inline_editor` instance, mousePressEvent inline-editor-active guard (first branch), `mouseDoubleClickEvent`, Esc-priority extension, F2 handler, `_commit_inline_editor_if_active` seam in `set_boxes`.
- `tests/test_gui_boxes.py` — 20 Task 1 + 10 Task 2 tests (30 new).

## Decisions Made

See the `decisions:` frontmatter for the full list. Highlights:

- InlineEditor takes the canvas (not the bare scene) — commit needs `boxes_snapshot()` + `boxes_modified.emit`; superset of the plan's constructor wording.
- `setZValue(1100)` literal (the acceptance grep) rather than a named constant — one usage site, plan action text verbatim.
- enter() on a different active box commits the previous edit first; re-entering the same box re-focuses without discarding uncommitted text.
- commit() detaches the before-snapshot payloads (`copy.copy`) BEFORE the in-place setter mutation — `_materialize_snapshot` copies at push-time (after the mutation), so without the detach undo would restore the post-edit text (Pitfall 8 push-side).
- `mouseDoubleClickEvent` selects the box before opening the editor (UI-SPEC §15's "box stays selected" holds for the double-click entry path).
- Task 3 checkpoint auto-approved under `auto_advance=true` + `human_verify_mode=end-of-phase`.

## Deviations from Plan

None — the plan executed exactly as written (modulo the two in-flight picks the plan delegated to the executor: canvas-constructor and enter()-commit-first, both documented in Decisions). One Rule-2 correctness hardening:

### Auto-fixed Issues

**1. [Rule 2 - Correctness] Before-snapshot payload detach in commit() (Pitfall 8 push-side)**
- **Found during:** Task 1 GREEN (design review of the commit path against history_manager `_materialize_snapshot`)
- **Issue:** the plan's literal recipe — "capture `boxes_snapshot()` (CR-01 pre-state) → mutate via setter → `boxes_modified.emit(before)`" — has an aliasing hole: `boxes_snapshot()` shares the live TextBlock by reference, the setters mutate it in place, and `_materialize_snapshot` copies each snapshot item via `PageBox.copy()` at PUSH-time, which runs AFTER the mutation. The pushed "before" payload would carry the NEW text, so Ctrl+Z would restore a no-op. (The 04-04 Inspector commit path has the same latent aliasing; it is out of this plan's scope — logged to deferred-items.md.)
- **Fix:** `commit()` detaches each before-snapshot payload (`pb.payload = copy.copy(pb.payload)`) immediately after capture and before the setter mutation, so the push-time copy sees the true pre-edit text.
- **Files modified:** `manga_ai_studio/gui/inline_editor.py`
- **Verification:** `test_inline_editor_commit_emits_boxes_modified_with_before_state` — asserts the `boxes_modified` payload's `payload.text` is the pre-edit "before" while the live pagebox holds "after".
- **Committed in:** `980b14c` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Focus-text read followed the wrong field during translation focus**
- **Found during:** Task 1 GREEN (first test run — `test_inline_editor_focus_rule_translation_wins` failed)
- **Issue:** the initial `_current_focus_text` helper read `payload.text` unconditionally, so a translation-focus session populated the editor with the recognized text instead of the translation.
- **Fix:** `_current_focus_text` became an instance method reading `self._focus_field`: translation focus → `payload.translation`; recognized focus → `payload.text` (str/list-aware, getattr-defensive).
- **Files modified:** `manga_ai_studio/gui/inline_editor.py`
- **Verification:** `test_inline_editor_focus_rule_translation_wins` green.
- **Committed in:** `980b14c` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 2 correctness hardening + 1 Rule 1 bug fix — both within the Task 1 files, no scope creep). No architectural changes (Rule 4), no auth gates, no package installs.

## Authentication Gates

None.

## Known Stubs

None that block the plan goal. The vertical edit mode is an INTENTIONAL v1 no-op (RESEARCH Pitfall 5): `payload.vertical` is preserved as export metadata via the plan-04 Inspector checkbox ("Coming soon" tooltip) and the editor always renders horizontal — the plan's `must_haves` contract, not a placeholder. No placeholder text/TODO/FIXME in any new code path.

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): a real-event body-drag move lands a box at `(69,69,129,129)` instead of the asserted `(70,70,130,130)` — a 1px drag-coordinate rounding difference. Verified failing identically against pristine pre-04-01 source (commit `210a178`) in plans 04-01..04-04; re-confirmed in this plan's full-suite run (`1 failed, 376 passed`). It is a GUI drag-simulation rounding issue that does not exercise the inline editor or any new code path (no drag path is touched: the editor's own drag-disable is asserted by `test_canvas_edit_mode_drag_inside_editor_does_not_move_box`). Already logged to `.planning/phases/04-ocr-recognition-text-editing/deferred-items.md`; not fixed.
- **NEW: Inspector commit path payload aliasing (04-04)**: `_inspector_commit_pre` captures the before-snapshot sharing the live TextBlock reference, and the commit handlers mutate it in place before `boxes_modified.emit` — the same Pitfall-8 push-side aliasing this plan fixed in the inline editor. Out of scope (04-04 code, not touched by this plan's files beyond the shared seam); the fix pattern is proven here and documented for the verifier. Logged to deferred-items.md.

## Threat Surface

No new security-relevant surface beyond the plan's `<threat_model>`. Both trust boundaries are mitigated exactly as designed:

- **T-4-09 (Tampering — commit fails to set edited=True):** recognized-field commits route through `PageBox.set_recognized_text_edited` (the Plan 01 centralized setter — writes `payload.text` + `edited=True` with the payload-None guard). Guarded by `test_inline_editor_commit_recognized_sets_edited_true` + `test_inline_editor_recognized_commit_routes_through_edited_setter` (monkeypatch proves the setter, not a direct write). The translation path uses `set_translation` (D-13 seam, `edited` untouched by design).
- **T-4-10 (DoS/UX — QGraphicsProxyWidget focus loss; click-away doesn't commit):** the canvas `mousePressEvent` guard checks inline-editor-active FIRST and commits on outside-click via the `proxy_scene_rect()` hit-test — it does NOT rely on Qt focus-out signaling alone. Guarded by `test_canvas_click_away_commits_inline_editor` + `test_canvas_click_inside_editor_does_not_commit`. IME/copy-paste on a real Japanese edit session remains the end-of-phase human gate (RESEARCH Pitfall 3 names exactly that).
- The editor document is PLAIN text (`setAcceptRichText(False)` + `setPlainText` only) — the T-4-07 XSS-equivalent mitigation is inherited from the plan-04 overlay discipline.

## TDD Gate Compliance

Plan frontmatter `type: execute`; both implementation tasks are `tdd="true"`. Gate sequence observed per task (separate RED `test(...)` commit then GREEN `feat(...)` commit):

- **Task 1:** RED `7804cdb` — `test(04-05): add failing tests for InlineEditor ...` (collection `ModuleNotFoundError: No module named 'manga_ai_studio.gui.inline_editor'` — confirmed failing before implementation). GREEN `980b14c` — `feat(04-05): implement InlineEditor ...` (20/20 new tests passing).
- **Task 2:** RED `2bc2817` — `test(04-05): add failing tests for canvas double-click dispatch ...` (first test fails on `AttributeError: 'EditorCanvas' object has no attribute '_inline_editor'` — confirmed failing before implementation). GREEN `406795a` — `feat(04-05): implement canvas double-click entry + inline-editor-active guard (TDD)` (10/10 new tests passing).

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — the two in-flight fixes (focus-text read, snapshot detach) landed inside the GREEN commit.

## Self-Check: PASSED

Created/modified files:
- FOUND: manga_ai_studio/gui/inline_editor.py
- FOUND: manga_ai_studio/gui/box_item.py
- FOUND: manga_ai_studio/gui/canvas.py
- FOUND: tests/test_gui_boxes.py

Commits:
- FOUND: 7804cdb (test(04-05): add failing tests for InlineEditor (QGraphicsProxyWidget + QTextEdit) + BoxItem edit-mode hooks)
- FOUND: 980b14c (feat(04-05): implement InlineEditor (QGraphicsProxyWidget + QTextEdit) + BoxItem edit-mode hooks (TDD))
- FOUND: 2bc2817 (test(04-05): add failing tests for canvas double-click dispatch + inline-editor-active guard)
- FOUND: 406795a (feat(04-05): implement canvas double-click entry + inline-editor-active guard (TDD))

## Next Phase Readiness

- TEXT-04's inline edit surface is complete: double-click/F2 → edit current-focus field → Enter/click-away commits (D-04 edited=True, BOXES undo), Esc cancels, D-07 edit-mode disable. The Inspector (04-04) remains the secondary home for the non-focus field; the two surfaces share the Plan 01 setters + the CR-01 push seam.
- Plan 06 (OCR) fills the recognized text the inline editor edits — the editor already works against already-populated boxes (verified via the Inspector flow the checkpoint describes).
- The `_commit_inline_editor_if_active` seam means the OCR/persistence paths that rebuild the box layer (page switch, detection, restore) can never collide with a dangling editor.
- The end-of-phase UAT gate carries the human-verify items from this plan's checkpoint: overlay-on-box feel, Japanese IME candidates inside the proxy, click-away on a real press sequence, F2, and the D-08 focus rule on a live box.

---
*Phase: 04-ocr-recognition-text-editing*
*Completed: 2026-08-07*

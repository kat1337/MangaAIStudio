---
phase: quick-260824-pqn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/project_io.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/inspector_panel.py
  - tests/test_core/test_project_io.py
  - tests/test_gui_project.py
  - tests/test_gui_boxes.py
  - tests/test_gui_detection_boxes.py
  - tests/test_gui_gap_closure.py
autonomous: true
requirements: [quick-260824-pqn]
estimate:
  tokens: 70000
  raw_tokens: 35000
  tasks: 3
  confidence: med
must_haves:
  truths:
    - Saving a session whose pages carry REAL detected boxes (vendored TextBlock payloads with numpy line polygons) writes manifest.json + <stem>.mas files into the chosen folder — no silent empty folder.
    - Any exception during the save pre-write phase surfaces the T-05-12 failure dialog (+ stray default-folder cleanup) instead of dying silently in the Qt slot.
    - Moving/resizing a bubble marks it geometry-stale (amber corner affordance) and NOTHING auto-runs after an idle delay — no grace timer exists.
    - The corner re-detect affordance only fires when the bubble exists AND is geometry-stale (moved/resized); clicks on non-stale bubbles are no-ops.
    - Editing text / typing never triggers detection work (the vk7 deferral reason disappears with the timer).
  artifacts:
    - manga_ai_studio/core/project_io.py — JSON-safe pagebox_to_json payload serialization
    - manga_ai_studio/gui/main_window.py — grace machinery removed; redetect gated on geometry_stale
    - tests/test_gui_boxes.py — grace tests replaced by stale-gate/no-auto-dispatch tests
  key_links:
    - boxes_modified commit -> _mark_geometry_changed (marks stale ONLY; no timer arm)
    - canvas.box_redetect_requested -> _on_box_redetect_requested gated on item.geometry_stale
    - build_page_entries meta.json json.dumps -> pagebox_to_json plain-list lines/xyxy
---

<objective>
Fix two user-reported issues:

1. **Save Project writes nothing:** `pagebox_to_json` serializes a detected payload's
   `lines` verbatim — the vendored detector produces numpy int32 polygons
   (`group_output` appends raw ndarray rows at textblock.py:468/474), so
   `json.dumps` inside `build_page_entries` raises `TypeError: Object of type
   ndarray is not JSON serializable`. That raise happens in `_save_project`'s
   page-build loop OUTSIDE the `except OSError`, so PySide6 swallows it in the
   slot: the dialog-accepted folder stays empty (only G-05-2's pre-created
   default exists) with NO error UI. PROBE-CONFIRMED with the pinned interpreter.
2. **Bubble re-detection:** remove the stationary-grace period + counter
   (`STATIONARY_GRACE_MS`, `_stationary_timer`, `_on_stationary_grace_timeout`,
   the vk7 edit-session deferral) entirely. Manual re-detection (corner
   affordance) is ONLY allowed when a bubble already exists AND was moved or
   resized (`geometry_stale`). No automatic trigger paths remain.

Purpose: users lose work thinking Save succeeded; the ~5 s surprise refit+OCR
freeze while typing is gone now that manual re-detection exists.
Output: fixed serialization + guarded save; grace-free stale-affordance flow;
updated test suite green under the pinned interpreter.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@C:/Src/Manga AI Studio/manga_ai_studio/core/project_io.py (pagebox_to_json L205-245, json_to_pagebox L248-378, build_page_entries L420-493)
@C:/Src/Manga AI Studio/manga_ai_studio/gui/main_window.py (_save_project L2462-2608, grace block L122-128, L159-167, L3601-3610, L3690-3797)
@C:/Src/Manga AI Studio/manga_ai_studio/gui/canvas.py (L195-208 signal decl, L2466-2500 emit sites, L2585-2660 boxes_modified docs)
@C:/Src/Manga AI Studio/manga_ai_studio/gui/box_item.py (geometry_stale property L628, L738-756, affordance docstring L744)
@C:/Src/Manga AI Studio/AGENTS.md (pinned interpreter)

Key facts established during investigation:
- Load side (`json_to_pagebox` L346-362) ALREADY coerces lines into plain int
  lists — the fix is save-side only; round-trip shape is preserved by design.
- `json_to_pagebox` rebuilds TextBlock WITHOUT numpy — loaded projects save
  fine; only freshly DETECTED boxes crash. This is why simple GUI save tests pass.
- `TextBlock.xyxy` may carry non-int numerics; `font_size` is int(round(...))
  upstream but coerce defensively anyway.
- `_redetect_single_box` (main_window L3772+) clears `item.geometry_stale = False`
  then calls `_refit_changed_boxes` — that engine and the amber affordance STAY;
  only the timer paths die.
- `box_interaction_started` (canvas L208, emits L2468/2488/2499) exists solely
  to stop the grace timer — remove signal + emits + the MainWindow connection.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Make detected-box payloads JSON-safe + surface save failures loudly</name>
  <files>manga_ai_studio/core/project_io.py, tests/test_core/test_project_io.py, manga_ai_studio/gui/main_window.py, tests/test_gui_project.py</files>
  <behavior>
    - RED first (tests/test_core/test_project_io.py): build a PageBox whose payload is a REAL vendored TextBlock constructed like group_output does — `TextBlock([10,10,100,100], [np.array([[1,2],[3,4],[5,6],[7,8]], dtype=np.int32)])` — run `pagebox_to_json` + `json.dumps(..., ensure_ascii=False)`; today this raises TypeError (probe-confirmed). Assert it succeeds AND `json_to_pagebox` round-trips: payload.lines == [[[1,2],[3,4],[5,6],[7,8]]] as plain ints, text/translation/font_size survive.
    - Edge cases: payload.lines empty list serializes as []; np.float64 coordinates coerce to int per the existing load-side contract; payload None unchanged.
  </behavior>
  <action>
    1. In `pagebox_to_json` (project_io.py L236-244): serialize every payload field as JSON-safe plain data — xyxy via `[int(v) for v in payload.xyxy]`; lines via nested list comprehension coercing each point coordinate with `int(v)` (handles ndarray quads AND plain-list quads); vertical via `bool(...)`; font_size via `int(payload.font_size)` wrapped so a non-numeric falls back to -1; language/text/translation via `str(...)`. Do NOT touch json_to_pagebox — its coercion already accepts both forms.
    2. Defense-in-depth in `_save_project` (main_window.py): wrap the pre-write phase (the `_snapshot_current_page()` call through the `page_files` build loop, L2490-2541) in try/except Exception — on failure log with loguru `logger.error(..., exc_info=True)`, show the SAME QMessageBox.critical save-failure copy ("Couldn't save '{name}'." / generic check-log copy), discard the stray created_default dir (WR-01 pattern), return False. Keep the existing duplicate-stem / empty-page_files / OSError branches exactly as they are (they have bespoke copy); the new catch is for UNEXPECTED exceptions so the silent-empty-folder symptom class is dead.
    3. GUI regression (tests/test_gui_project.py): a save where a page carries a detected-style payload (numpy-lines TextBlock) writes manifest.json + .mas into the monkeypatched folder (would fail before Task 1's step 1 — keep it as the end-to-end guard).
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_project_io.py tests/test_gui_project.py -q</automated>
  </verify>
  <done>json.dumps(pagebox_to_json(detected-style PageBox)) succeeds headless; round-trip preserves lines as plain ints; a simulated mid-build exception shows the failure dialog + cleans the stray folder; all existing project tests stay green.</done>
</task>

<task type="auto">
  <name>Task 2: Remove the stationary-grace machinery; gate manual re-detect on geometry_stale</name>
  <files>manga_ai_studio/gui/main_window.py, manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/inspector_panel.py</files>
  <action>
    Production changes, no behavior beyond the two rules:
    1. main_window.py: delete the `STATIONARY_GRACE_MS` constant (L122-128), the `_stationary_timer` construction + `box_interaction_started.connect(self._stationary_timer.stop)` (L159-167), `_mark_geometry_changed`'s timer arm (keep the method and its geometry_stale marking loop — just drop the `changed` flag's `timer.start` tail; the flag becomes unnecessary), `_on_stationary_grace_timeout` (L3725-3758) ENTIRELY (including the vk7 edit-session deferral — with no timer there is nothing to defer; typing is naturally safe), and the now-unused QTimer import if nothing else uses it.
    2. main_window.py `_on_box_redetect_requested` (L3760): add the staleness gate — return early unless `getattr(box_item, "geometry_stale", False)` (bubble exists AND moved/resized). Update its docstring: manual-only, stale-gated, no auto path.
    3. canvas.py: remove the `box_interaction_started` Signal declaration (L195-208 comment block included), its three `.emit()` calls (L2468, L2488, L2499 — leave the surrounding drag handlers byte-identical otherwise), and refresh the stale doc mentions at L2592-2660 (boxes_modified emission no longer "arms" anything — it feeds `_mark_geometry_changed` staleness marking only).
    4. box_item.py L744 + inspector_panel.py L598: reword docstrings/comments that reference the stationary grace — the affordance now reads "appears while the box is geometry-stale (moved/resized); click to re-run detection+OCR".
    Preserve: `geometry_stale` property/setter + `_redetect.setVisible` (box_item L628-756), `_refit_changed_boxes`, `_redetect_single_box` (its stale-clear + OCR leg), the D-04 edited-text OCR skip.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_canvas.py tests/test_gui_detection_boxes.py -q && rg -c "STATIONARY_GRACE_MS|_stationary_timer|_on_stationary_grace_timeout|box_interaction_started" manga_ai_studio/gui/main_window.py manga_ai_studio/gui/canvas.py; if ($LASTEXITCODE -eq 0) { throw "grace identifiers still present" } else { "grace machinery fully removed" }</automated>
  </verify>
  <done>No grace identifier remains in gui sources; committing a box move sets geometry_stale and starts nothing; clicking the affordance on a non-stale bubble does nothing; on a stale bubble it refits + dispatches OCR once.</done>
</task>

<task type="auto">
  <name>Task 3: Overhaul grace tests -> stale-gate tests; full suite green</name>
  <files>tests/test_gui_boxes.py, tests/test_gui_detection_boxes.py, tests/test_gui_gap_closure.py</files>
  <action>
    1. tests/test_gui_boxes.py: DELETE the grace-era tests (test_alt_drag_draw_release_defers_ocr_to_grace ~L3434, test_on_canvas_create_dispatches_single_box_worker_after_grace ~L3548, the stationary-grace battery ~L5002-5070 — test_stationary_grace_dispatches_once / test_drag_cancels_pending_grace / test_create_defers_detection_to_grace — and ALL quick-260822-vk7 deferral tests ~L5071-5230). Their premises are removed behavior.
       REPLACE with: (a) test_commit_move_marks_stale_starts_nothing — commit a move, assert item.geometry_stale True and NO worker dispatched after processing events (no timer to fire); (b) test_redetect_click_noop_when_not_stale — emit box_redetect_requested for a fresh/non-moved item, assert no refit/OCR; (c) test_redetect_click_runs_when_stale — mark stale (or commit a real move), click, assert exactly one OCR dispatch + stale cleared.
    2. tests/test_gui_detection_boxes.py L733/L788 + tests/test_gui_gap_closure.py: update the two comment/assertion spots referencing the stationary grace to the stale-affordance wording (check surrounding assertions still hold — the explicit re-detect path semantics are unchanged).
    3. Full suite under the pinned interpreter (baseline 552 passed at Phase 5 close, grown since): confirm zero failures.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q</automated>
  </verify>
  <done>Full suite passes with the pinned interpreter; every removed grace test is replaced by its stale-gate counterpart; rg for "stationary" in tests returns only historical-decision prose, no live assertions.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| model->payload | Detector output (untrusted) lands verbatim in PageBox.payload and is serialized to disk |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QKN-01 | Tampering | pagebox_to_json payload fields | low | mitigate | int()/bool()/str() coercion of model-produced values — garbage numerics become plain ints, never leak into manifest JSON |
| T-QKN-02 | Denial of Service | _save_project pre-write phase | medium | mitigate | unexpected exceptions surface the failure dialog + stray-folder cleanup instead of a silent Qt-slot swallow |
| T-QKN-03 | Repudiation | silent save failure | medium | mitigate | loguru logger.error with exc_info on every save-abort path |
</threat_model>

<verification>
- Probe scenario from planning (numpy-lines TextBlock payload) saves successfully end-to-end.
- No grace/timer identifiers in gui sources; full pinned-interpreter suite green.
</verification>

<success_criteria>
1. Save Project with detected boxes persists manifest.json + .mas files; failures are loud.
2. Zero automatic re-detection paths: moving/resizing only marks stale; the corner affordance is the sole trigger and requires moved-or-resized state.
3. Full test suite green under C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe.
</success_criteria>

<output>
Create .planning/quick/260824-pqn-fix-bubble-re-detection-remove-grace-per/260824-pqn-SUMMARY.md when done
</output>

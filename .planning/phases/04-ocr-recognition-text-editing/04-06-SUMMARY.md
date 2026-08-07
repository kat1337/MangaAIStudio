---
phase: 04-ocr-recognition-text-editing
plan: 06
subsystem: gui (OCR dispatcher + Text menu + auto-OCR hook)
tags: [ocr, text-editing, manga-ocr, gui, qt, qthreadpool, worker, tdd, pytest-qt, d-04, cr-11]
requires:
  - Phase 04 Plan 01 PageBox setters (set_recognized_text OCR-write edited=False / has_recognized_text / edited flag) + boxes_snapshot peer-field round-trip
  - Phase 04 Plan 03 TorchOCRModel adapter (lazy MangaOcr load, recognize(numpy)->str) + backend_factory('ocr','torch') resolution
  - Phase 04 Plan 04 BoxItem text overlay + badge (refresh_text_overlay / refresh_badge) + InspectorPanel commit path (edited=True)
  - Phase 04 Plan 05 InlineEditor + canvas inline-editor-active guard
  - Phase 1/2 Worker(QRunnable) + _op_running + status-bar-progress pattern (detect_text cluster in main_window.py)
  - panelcleaner.model_downloader get_ocr_model_directory / is_ocr_downloaded (CR-11 cache-check)
provides:
  - MainWindow.run_ocr_selected() / run_ocr_all() / _dispatch_ocr_for_box(box_item) / _on_canvas_ocr_requested(box_item)
  - MainWindow._run_ocr_task / _run_ocr_all_task (Worker tasks, box_id-identified results)
  - MainWindow._on_ocr_finished / _on_ocr_all_finished / _on_ocr_progress / _on_ocr_error / _on_ocr_cleanup
  - MainWindow._resolve_ocr_model_path() (CR-11 cache-check) + _ocr_backend() (D-14 torch default)
  - MainWindow._confirm_reocr() / _confirm_reocr_all(count) (D-04 single + batch gates)
  - EditorCanvas.ocr_requested = Signal(object) + _commit_create emit (D-01 auto-OCR seam)
  - _build_text_menu() with action_run_ocr + action_ocr_all (Ctrl+R) between View and Tools
affects:
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/canvas.py
  - tests/test_gui_boxes.py
tech-stack:
  added: []
  patterns:
    - Worker(QRunnable) + _op_running gate + status-bar progress mirroring the detect_text cluster verbatim (RESEARCH Pattern 2) — indeterminate (0,0) for single-box, determinate 0..100 for OCR All
    - box_id identity via id(frozen Box) crossing the thread boundary (same object on both sides; never a Qt object in the worker — RESEARCH Pitfall 3)
    - CR-01 before-state BOXES snapshot with Pitfall-8 push-side payload detach (copy.copy per payload BEFORE the in-place setter mutation — the 04-05 fix pattern applied to the new OCR write path)
    - D-04 gates: silent overwrite when edited=False, confirm dialog when edited=True (single + batch with count)
    - Pitfall 6 first-run UX: "Loading OCR model…" + indeterminate progress BEFORE the worker starts the ~450MB download
    - canvas signal seam for auto-OCR (ocr_requested) — the model call never runs on the GUI thread
key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - manga_ai_studio/gui/canvas.py
    - tests/test_gui_boxes.py
decisions:
  - OCR All (D-03) dispatches over TEXT-EMPTY boxes only (the plan's action recipe: empty_boxes list, none->return, empty-only dispatch); the D-04 batch gate fires when any edited box exists (count named in the dialog, UI-SPEC copy verbatim). The plan-internal copy/behavior tension ("will overwrite those edits" vs fill-only dispatch) is documented — the plan's must_haves ("fills every text-empty box") + action recipe are followed literally.
  - Box lookup across the worker boundary uses id(box.pagebox.box) (single) / id(pagebox) (batch) — the frozen Box/PageBox is the SAME object on both sides, so identity is stable; no Qt object crosses into the worker (RESEARCH Pitfall 3). The plan offered box_id OR index; identity was picked and used consistently.
  - _on_ocr_finished/_on_ocr_all_finished capture the before-snapshot and detach each payload via copy.copy BEFORE the setter mutation — the 04-05 Pitfall-8 fix applied to the new OCR write path (without it, undo after an OCR overwrite would restore the post-OCR text).
  - One boxes_modified emit per OCR All batch (UI-SPEC §20 batch-undo pattern) with the single before-state captured at finish-time; single-box OCR emits once.
  - The vendored Box accessor is as_tuple (x1,y1,x2,y2) — RESEARCH's as_tuple_xyxy_prefer_x1y1x2y2 does not exist in the vendored structures.py.
  - _op_running is cleared ONLY in _on_ocr_cleanup (finished always fires — Pitfall 7), mirroring detection; _on_ocr_error leaves it to the cleanup.
  - Checkpoint Task 3 auto-approved under auto_advance=true + human_verify_mode=end-of-phase (gate="blocking", NOT blocking-human/package-legitimacy) — the established project cadence (plans 03-03/03-04/04-04/04-05 identical); the 8 manual checks (real manga page, D-04 live gates, first-run download UX) defer to the end-of-phase UAT gate.
actuals:
  tokens: 30000
  tasks: 2
  commits: 5
requirements-completed: [TEXT-02]
coverage:
  - id: D1
    description: "OCR dispatcher mirrors detect_text exactly: Worker(QRunnable) + _op_running gate + status-bar progress; _run_ocr_task crops the region by box xyxy (.copy() — Pitfall 2), resolves the model path, model.load once, returns {text: str, box_id}."
    requirement: TEXT-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_selected_dispatches_worker_not_inline"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_selected_emits_boxes_modified_with_before_state"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_selected_error_shows_chip_and_dialog"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_selected_real_model_end_to_end"
        status: pass
  - id: D2
    description: "D-04 re-OCR gates: silent overwrite when edited=False, confirm dialog when edited=True (single-box _confirm_reocr + batch _confirm_reocr_all with count)."
    requirement: TEXT-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_reocr_confirms_when_edited"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_reocr_silent_when_raw"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_all_gate_confirms_when_edited_boxes_exist"
        status: pass
  - id: D3
    description: "OCR All Boxes (Ctrl+R) fills every text-empty box on the page: one model load, sequential per-box, determinate progress + 'OCR All… {done}/{total} · box N' status; ONE batch BOXES push."
    requirement: TEXT-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_all_fills_empty_boxes"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_all_noop_when_no_empty_boxes"
        status: pass
  - id: D4
    description: "First-run UX (Pitfall 6): 'Loading OCR model…' + indeterminate progress before the worker starts the ~450MB download; _resolve_ocr_model_path CR-11 cache-checks via is_ocr_downloaded (no re-download per session, T-4-13)."
    requirement: TEXT-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_run_ocr_selected_shows_loading_ocr_model_on_first_run"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_resolve_ocr_model_path_cache_checks"
        status: pass
  - id: D5
    description: "Text menu between View and Tools with Run OCR (enabled iff one box selected + no op) + OCR All Boxes Ctrl+R (enabled iff >=1 box + no op); action enable-states refresh via _refresh_action_states."
    requirement: TEXT-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_menu_has_run_ocr_and_ocr_all_entries"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_action_run_ocr_enabled_only_with_selection"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_action_ocr_all_enabled_with_boxes"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_ctrl_r_shortcut_triggers_ocr_all"
        status: pass
  - id: D6
    description: "D-01 auto-OCR hook: canvas._commit_create emits ocr_requested(BoxItem) on Alt+drag draw-release (>= 8x8 only); MainWindow._on_canvas_ocr_requested dispatches the single-box worker (gated on _op_running — T-4-14); the box arrives with recognized text."
    requirement: TEXT-02
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_alt_drag_draw_release_emits_ocr_requested"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_alt_drag_too_small_emits_no_ocr_requested"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_on_canvas_ocr_requested_dispatches_single_box_worker"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_on_canvas_ocr_requested_skipped_when_op_running"
        status: pass
    human_judgment: true
    rationale: "The live feel of auto-OCR on draw-release against real manga artwork (speed, download UX) is the end-of-phase UAT gate; the dispatcher logic is fully automated."
metrics:
  duration: 13 min
  completed: 2026-08-07
  tasks: 2
  files: 3
status: complete
---

# Phase 04 Plan 06: OCR Dispatcher + Text Menu + Auto-OCR Hook Summary

Wired TEXT-02's OCR execution end-to-end as TDD: the OCR dispatcher cluster in MainWindow mirrors the `detect_text` Worker(QRunnable) + `_op_running` + status-bar-progress pattern verbatim (RESEARCH Pattern 2) — single-box "Run OCR" (D-01) with indeterminate progress, "OCR All Boxes" (Ctrl+R, D-03) with determinate 0..100 progress and per-box "OCR All… {done}/{total} · box N" status, the D-04 re-OCR confirm gates (silent overwrite when `edited=False`, confirm dialog when `edited=True` — single + batch with count), the first-run "Loading OCR model…" UX (Pitfall 6) before the worker starts the ~450MB download, and the CR-11 cache-check `_resolve_ocr_model_path` (no re-download per session). The new Text menu (between View and Tools) carries Run OCR + OCR All Boxes; the canvas `_commit_create` seam emits a new `ocr_requested` signal so Alt+drag draw-release auto-runs OCR on the freshly-drawn box (D-01) off the GUI thread. Every OCR write goes through `set_recognized_text` (edited=False), refreshes the BoxItem overlay + badge, and pushes a CR-01 before-state BOXES snapshot with Pitfall-8 payload detach. All dispatcher tests use a mocked model; the real-model integration test is skip-gated on `is_ocr_downloaded()` and passes on this machine (model cached).

## What Was Built

### Task 1 — OCR dispatcher cluster (TDD)

`manga_ai_studio/gui/main_window.py` (OCR section inserted after the inpaint cluster):

- **`run_ocr_selected()`** — gates on `_op_running`; requires the single selected box (`canvas._selected_box()`); fires the D-04 gate (`has_recognized_text() and edited` → `_confirm_reocr()`, Cancel aborts); delegates to `_dispatch_ocr_for_box`.
- **`_dispatch_ocr_for_box(box_item)`** — the shared single-box dispatch (used by Run OCR AND the D-01 auto-OCR hook): `backend_factory("ocr", self._ocr_backend())`, `Worker(self._run_ocr_task, path, box_item.pagebox.box, model)` (the frozen Box is a plain object — never a Qt object in the worker, Pitfall 3), result/error/finished wiring, `_op_running=True`, indeterminate `progress_bar.setRange(0, 0)`, "Recognizing text… box N", and the Pitfall 6 first-run "Loading OCR model…" override when `is_ocr_downloaded()` is False.
- **`_run_ocr_task(image_path, box_xyxy, model, ...)`** — cv2.imdecode(np.fromfile) (the CR-17 path), `x1,y1,x2,y2 = box_xyxy.as_tuple` (the vendored Box accessor — RESEARCH's `as_tuple_xyxy_prefer_x1y1x2y2` does not exist in `structures.py`), `region = image[y1:y2, x1:x2].copy()` (Pitfall 2), `_resolve_ocr_model_path()`, `model.load(model_path, device="auto")` (MangaOcr singleton — load-once per session, T-4-06), returns `{"text": str, "box_id": id(box_xyxy)}`.
- **`run_ocr_all()`** — gates on `_op_running`; collects text-empty boxes (`not has_recognized_text()`; none → return); D-04 batch gate (`edited_count` → `_confirm_reocr_all(count)`, Cancel aborts the whole batch); dispatches `_run_ocr_all_task` over the empty boxes with `box_ids = [id(it.pagebox) ...]`; determinate progress; "OCR All… 0/N" then per-box updates.
- **`_run_ocr_all_task(image_path, box_xyxys, box_ids, model, ...)`** — ONE image read + ONE `model.load` (Pitfall 3), sequential per-box recognize, abort-checked BETWEEN boxes (`abort_flag.get()`, Phase 2 D-09 pattern), progress `(percent, "i/N · box i")` per box, returns the `{box_id, text}` result list.
- **`_on_ocr_finished(result)`** — finds the BoxItem by `id(it.pagebox.box) == box_id`; captures the CR-01 before-snapshot + **detaches each payload via `copy.copy` BEFORE the mutation** (Pitfall 8 push-side — the 04-05 fix; without it, undo after an OCR overwrite would restore the post-OCR text); `set_recognized_text(result["text"])` (edited=False, D-04); `refresh_text_overlay()` + `refresh_badge()`; one `boxes_modified.emit(before)`; transient "OCR complete · 1 box recognized" (the existing `_show_transient_status` ~3 s revert).
- **`_on_ocr_all_finished(results)`** — ONE batch `boxes_modified` emit with the single before-state (UI-SPEC §20 batch-undo), skips vanished boxes, "OCR complete · N boxes recognized".
- **`_on_ocr_progress(payload)`** — `progress_bar.setValue(percent)` + "OCR All… {label}" (the UI-SPEC "{done}/{total} · box N" shape).
- **`_on_ocr_error(worker_error)`** — `logger.error` full traceback (T-01-08), `#7a1f1f` chip "OCR model error", the UI-SPEC friendly `QMessageBox.critical` ("Couldn't load the OCR model." + network/~450MB copy), "OCR failed" status.
- **`_on_ocr_cleanup(_args)`** — `_op_running=False`, hide progress, refresh states (connected to `finished`, which Worker.run's finally ALWAYS emits — Pitfall 7).
- **`_resolve_ocr_model_path()`** — lazy `from panelcleaner.model_downloader import get_ocr_model_directory, is_ocr_downloaded`; `if is_ocr_downloaded(): return cache_dir` (CR-11 short-circuit, T-4-13); returns the cache dir either way — the actual fetch happens inside `TorchOCRModel.load` → `MangaOcr.initialize_model()` in the worker (Pitfall 6).
- **`_ocr_backend()`** — profile `ocr_backend` attribute default `"torch"` (D-14; ONNX raises NotImplementedError in the factory — designed-in hook).
- **`_confirm_reocr()` / `_confirm_reocr_all(count)`** — mirror `_confirm_replace_boxes` verbatim (custom buttons `[Cancel] [Re-run OCR]` / `[Cancel] [Re-run OCR on All]`, UI-SPEC §Copywriting D-04 bodies, window title "Run OCR").

### Task 2 — Text menu + auto-OCR hook (TDD)

`manga_ai_studio/gui/canvas.py`:

- **`ocr_requested = Signal(object)`** — class-scope, alongside `boxes_modified` (plan 04-06, D-01 seam).
- **`_commit_create`** — after `item.setSelected(True)` and BEFORE the boxes_modified emit, `self.ocr_requested.emit(item)`. The < 8x8 no-op returns earlier, so a real box always emits (UI-SPEC §14). The pre-create `boxes_modified` emit is UNCHANGED — the OCR is a separate op that pushes its own BOXES entry on finish.

`manga_ai_studio/gui/main_window.py`:

- **`self.canvas.ocr_requested.connect(self._on_canvas_ocr_requested)`** — wired right after canvas construction in `__init__`.
- **`_on_canvas_ocr_requested(box_item)`** — gates on `_op_running` (silently skipped when another op runs — T-4-14, no worker pileup); no D-04 gate (a fresh box has no text — silent overwrite semantics correct); dispatches via the shared `_dispatch_ocr_for_box`.
- **`_build_text_menu()`** — `&Text` menu between View and Tools (File/Edit/View/Text/Tools/Help, UI-SPEC §Surface 1): `action_run_ocr` ("Run OCR", status tip, → `run_ocr_selected`) + `action_ocr_all` ("OCR All Boxes", `QKeySequence("Ctrl+R")`, UI-SPEC tooltip copy, → `run_ocr_all`). Both disabled by default; Plan 07 adds Auto-Number + Load Translations to this menu.
- **`_refresh_action_states()`** — `action_run_ocr` enabled iff `page_open and box_selected and not _op_running`; `action_ocr_all` enabled iff `page_open and box_count() > 0 and not _op_running`. Ctrl+R confirmed free (UI-SPEC §Shortcuts audit — only Ctrl+Return exists in the Inspector, no collision).

### Task 3 — Checkpoint:human-verify (auto-approved)

Config `auto_advance: true` + `human_verify_mode: end-of-phase`; the checkpoint is `gate="blocking"` (NOT `blocking-human`, NOT package-legitimacy) → auto-approved per the established project cadence (plans 03-03/03-04/04-04/04-05 identical). The automated portion is green (`test_gui_boxes.py` 115 passed, 1 deselected — the pre-existing deferred test; the real-model integration test RAN on this machine's cached HF model and passed). The 8 manual checks (auto-OCR on real manga artwork, first-run ~450MB download UX, Run OCR on detected boxes, OCR All progress, D-04 single + batch gates on live edits, error UX) defer to the end-of-phase UAT gate — VALIDATION.md names these as manual-only verifications.

## Verification

```
python -m pytest tests/test_gui_boxes.py -q --deselect tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip
# 115 passed, 1 deselected  (93 prior + 22 new OCR/menu/auto-OCR tests)

python -m pytest tests/test_gui_boxes.py -x -q -k "ocr or reocr"
# 14 passed (dispatcher RED/GREEN gate)

python -m pytest tests/ -q
# 398 passed, 1 failed (PRE-EXISTING — see Deferred Issues)
```

Acceptance criteria verified (all grep counts exact):
- Task 1: `def run_ocr_selected|run_ocr_all|_run_ocr_task|_run_ocr_all_task` = 4; `def _on_ocr_finished|_on_ocr_error|_on_ocr_cleanup` = 3 (>= 2); `def _resolve_ocr_model_path` = 1; `def _confirm_reocr` = 2 (>= 1); `is_ocr_downloaded` = 8 (>= 1, CR-11); `backend_factory("ocr"` = 2 (>= 1); "Loading OCR model" = 3 (>= 1, Pitfall 6).
- Task 2: `def _build_text_menu` = 1; `action_run_ocr|action_ocr_all` = 13 (>= 4); `QKeySequence("Ctrl+R")` = 1; `ocr_requested` in canvas.py = 2 (>= 2, Signal + emit); `_on_canvas_ocr_requested` = 2 (>= 2, connect + handler).
- Test-level: mocked-model dispatch writes `set_recognized_text` + emits `boxes_modified` PASS; D-04 edited=True + Cancel → no OCR PASS; edited=False silent overwrite (no dialog) PASS; worker dispatched not inline PASS; cache-check called PASS; Alt+drag emits `ocr_requested` PASS; Text menu entries PASS; Run OCR disabled without selection PASS; Ctrl+R dispatches PASS; real-model end-to-end PASS (cached model).

## Performance

- **Duration:** 13 min
- **Started:** 2026-08-07T20:24:07Z
- **Completed:** 2026-08-07T20:36:55Z
- **Tasks:** 2 implementation tasks (Task 3 checkpoint auto-approved under end-of-phase verify mode)
- **Files modified:** 3 (2 modified, 1 test file extended)

## Task Commits

Each task was committed atomically (RED `test(...)` commit → GREEN `feat(...)` commit per the project's per-task TDD convention):

1. **Task 1 RED:** `1c89945` (test) — add failing tests for OCR dispatcher (Worker + D-04 gates + first-run UX); 14 failed at collection (AttributeError — no `run_ocr_selected`/`run_ocr_all`/`_resolve_ocr_model_path`)
2. **Task 1 GREEN:** `8d998e4` (feat) — implement OCR dispatcher (Worker + _op_running + D-04 gates + first-run UX) (TDD); 14/14 new tests pass
3. **Task 2 RED:** `2c71ab8` (test) — add failing tests for Text menu + auto-OCR hook (ocr_requested); 8 failed (AttributeError — no signal/actions/handler)
4. **Task 2 GREEN:** `0b800a5` (feat) — implement Text menu (Run OCR / OCR All Ctrl+R) + auto-OCR hook on _commit_create (TDD); 8/8 new tests pass
5. **Docs commit:** (after this SUMMARY) — completes the plan

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` — OCR dispatcher cluster (run_ocr_selected/_dispatch_ocr_for_box/_run_ocr_task/run_ocr_all/_run_ocr_all_task/_on_ocr_finished/_on_ocr_all_finished/_on_ocr_progress/_on_ocr_error/_on_ocr_cleanup/_resolve_ocr_model_path/_ocr_backend/_confirm_reocr/_confirm_reocr_all/_on_canvas_ocr_requested) + `_build_text_menu` + `_refresh_action_states` OCR actions + `ocr_requested` connect + `import copy`.
- `manga_ai_studio/gui/canvas.py` — `ocr_requested = Signal(object)` + `_commit_create` emit (D-01 seam, before the boxes_modified emit).
- `tests/test_gui_boxes.py` — 22 new tests (14 Task 1 dispatcher + 8 Task 2 menu/auto-OCR), incl. the skip-gated real-model integration marker.

## Decisions Made

See the `decisions:` frontmatter for the full list. Highlights:

- OCR All dispatches over TEXT-EMPTY boxes only (the plan's action recipe followed literally); the D-04 batch gate fires when any edited box exists and names the count. The plan-internal tension between the UI-SPEC batch copy ("will overwrite those edits") and the fill-only dispatch recipe is documented — the plan's must_haves + action recipe win; the copy is contracted verbatim.
- Box identity via `id()` of the frozen Box/PageBox (same object across the thread boundary) — no Qt object ever enters the worker (Pitfall 3).
- Pitfall-8 payload detach applied to the NEW OCR write path (`copy.copy` per before-snapshot payload before the in-place setter mutation) — the 04-05 fix pattern; the 04-04 Inspector path's latent aliasing remains logged as deferred.
- One `boxes_modified` emit per OCR All batch (UI-SPEC §20); single-box emits once.
- `_op_running` cleared only in `_on_ocr_cleanup` (finished always fires — Pitfall 7), mirroring detection exactly.
- Task 3 checkpoint auto-approved under `auto_advance=true` + `human_verify_mode=end-of-phase`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness] Pitfall-8 payload detach in the OCR before-snapshot**
- **Found during:** Task 1 GREEN (design review of `_on_ocr_finished` against the 04-05 precedent)
- **Issue:** the plan's recipe — "capture pre-state via canvas.boxes_snapshot() and emit boxes_modified" — has the same aliasing hole the 04-05 summary documented for the Inspector path: `boxes_snapshot()` shares the live TextBlock by reference, the setter mutates `payload.text` in place, and the history's `_materialize_snapshot` copies at PUSH-time (after the mutation) — undo would restore the post-OCR text.
- **Fix:** both `_on_ocr_finished` and `_on_ocr_all_finished` detach each before-snapshot payload (`pb.payload = copy.copy(pb.payload)`) immediately after capture and before any setter mutation — the proven 04-05 pattern.
- **Files modified:** `manga_ai_studio/gui/main_window.py`
- **Verification:** `test_run_ocr_selected_emits_boxes_modified_with_before_state` — asserts the emitted snapshot's payload.text is the pre-OCR "旧" while the live pagebox holds "新".
- **Committed in:** `8d998e4` (Task 1 GREEN)

**2. [Rule 3 - Blocking] Ctrl+R test could not intercept the action via instance monkeypatch**
- **Found during:** Task 2 GREEN (first test run — `test_ctrl_r_shortcut_triggers_ocr_all` failed)
- **Issue:** the initial test monkeypatched `window.run_ocr_all` on the instance, but Qt signal connections capture the BOUND METHOD at connect time (`self.action_ocr_all.triggered.connect(self.run_ocr_all)` in `_build_text_menu`), so triggering the action still invoked the original method.
- **Fix:** rewrote the test to trigger the real dispatch (mocked model): seed a box, `action_ocr_all.trigger()` → assert `_op_running` + the box fills. This is a stronger end-to-end assertion of the Ctrl+R path (action shortcuts emit `triggered`).
- **Files modified:** `tests/test_gui_boxes.py`
- **Committed in:** `0b800a5` (Task 2 GREEN — test fix landed with the implementation commit)

**3. [Rule 3 - Blocking] Menu test hit a PySide6 wrapper-lifetime RuntimeError**
- **Found during:** Task 2 GREEN (first test run — `test_text_menu_has_run_ocr_and_ocr_all_entries` failed)
- **Issue:** `next(a.menu() for a in window.menuBar().actions() ...)` returned a QMenu whose wrapper was torn down with the temporary QAction wrapper ("Internal C++ object already deleted" at `text_menu.actions()`).
- **Fix:** the test holds strong references to the menubar action wrappers before extracting the menu (and derives the menu from a kept QAction reference).
- **Files modified:** `tests/test_gui_boxes.py`
- **Committed in:** `0b800a5`

**4. [Plan artifact - RESEARCH accessor] `as_tuple_xyxy_prefer_x1y1x2y2` does not exist**
- The RESEARCH Pattern 2 example references a Box accessor that the vendored `structures.py` does not have. The vendored `Box.as_tuple` returns `(x1, y1, x2, y2)` (verified in `panelcleaner/structures.py:50-52`) — used instead. Behavior identical; documented so the RESEARCH reference is not re-followed blindly.

**5. [Plan artifact - OCR All scope] fill-only dispatch vs batch-gate copy**
- The plan's Task-1 action recipe (empty-box dispatch, none→return, edited-count gate) is implemented literally; the UI-SPEC D-04 batch body ("will overwrite those edits") is rendered verbatim as contracted. The tension is a plan-level artifact (three plan sections agree on fill-only; the gate copy implies overwrite). Documented for the verifier; if batch overwrite of edited boxes is desired, it is a one-line scope change in `run_ocr_all` (dispatch over all boxes instead of empty ones).

**Total deviations:** 2 Rule-2/Rule-3 auto-fixes + 2 test-side fixes + 2 documented plan artifacts. No architectural changes (Rule 4), no auth gates, no package installs.

## Authentication Gates

None. (The first-run ~450MB HF model download is a network fetch inside the worker — not an auth gate; `HF_HUB_CACHE` is the only env knob, already at its default on this machine.)

## Known Stubs

None that block the plan goal. The ONNX OCR backend branch raises `NotImplementedError` in the factory (D-14 designed-in hook, "wired for the future" per plan) — intentional, not a stub. No placeholder text/TODO/FIXME in any new code path.

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): 1px real-event drag-coordinate rounding (`(69,69,129,129)` vs `(70,70,130,130)`). Re-confirmed failing in this plan's full-suite run (`1 failed, 398 passed`); verified against pristine pre-04-01 source in plans 04-01..04-05. Logged in deferred-items.md; not fixed.
- **Inspector commit path payload aliasing (04-04, Pitfall 8 push-side)** — still open; the OCR write path (this plan) applies the proven 04-05 detach pattern, so the aliasing is now confined to the 04-04 Inspector handlers. Logged in deferred-items.md; out of scope (04-04 code).

## Threat Surface

No new security-relevant surface beyond the plan's `<threat_model>`. All four OCR threats mitigated as designed:

- **T-4-11 (DoS — OCR on the GUI thread):** every OCR run dispatches via `Worker(QRunnable)` + `QThreadPool`; `_resolve_ocr_model_path` + `model.load` run inside the worker. `test_run_ocr_selected_dispatches_worker_not_inline` asserts the dispatch (worker not yet run when `run_ocr_selected` returns; `recognize_calls == []`).
- **T-4-12 (Tampering — D-04 gate bypass):** `run_ocr_selected` checks `has_recognized_text() and edited` before dispatch; `_confirm_reocr` / `_confirm_reocr_all` fire when `edited=True`. `test_reocr_confirms_when_edited` (Cancel → no OCR) + `test_reocr_silent_when_raw` (dialog must not fire) + the batch-count gate test.
- **T-4-13 (DoS — ~450MB re-download per session):** `_resolve_ocr_model_path` short-circuits via `is_ocr_downloaded()` (CR-11). `test_resolve_ocr_model_path_cache_checks` asserts the check is called.
- **T-4-14 (DoS — worker pileup):** `_op_running` gate at the top of `run_ocr_selected` / `run_ocr_all` / `_on_canvas_ocr_requested`; auto-OCR on rapid draws is skipped silently. Gated-when-running tests for both entry points + the auto-OCR hook.
- Model output remains untrusted plain text written through the Plan 01 setter and rendered by the Plan 04 PLAIN-text overlay (ASVS V5 inherited — no new surface).

## TDD Gate Compliance

Plan frontmatter `type: execute`; both implementation tasks are `tdd="true"`. Gate sequence observed per task (separate RED `test(...)` commit then GREEN `feat(...)` commit):

- **Task 1:** RED `1c89945` — 14 new tests failed at collection (`AttributeError: 'MainWindow' object has no attribute 'run_ocr_selected'` etc. — confirmed failing before implementation). GREEN `8d998e4` — all 14 pass (incl. the real-model end-to-end test, which ran on this machine's cached HF model).
- **Task 2:** RED `2c71ab8` — 8 new tests failed at collection (`AttributeError: 'EditorCanvas' object has no attribute 'ocr_requested'` / no `action_run_ocr` / no `_on_canvas_ocr_requested` — confirmed failing before implementation). GREEN `0b800a5` — all 8 pass.

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — the two in-flight fixes (payload detach, test rewrites) landed inside the GREEN commits.

## Self-Check: PASSED

Modified files:
- FOUND: manga_ai_studio/gui/main_window.py
- FOUND: manga_ai_studio/gui/canvas.py
- FOUND: tests/test_gui_boxes.py

Commits:
- FOUND: 1c89945 (test(04-06): add failing tests for OCR dispatcher (Worker + D-04 gates + first-run UX))
- FOUND: 8d998e4 (feat(04-06): implement OCR dispatcher (Worker + _op_running + D-04 gates + first-run UX) (TDD))
- FOUND: 2c71ab8 (test(04-06): add failing tests for Text menu + auto-OCR hook (ocr_requested))
- FOUND: 0b800a5 (feat(04-06): implement Text menu (Run OCR / OCR All Ctrl+R) + auto-OCR hook on _commit_create (TDD))

## Next Phase Readiness

- TEXT-02's OCR surface is complete: Alt+drag draw-release auto-runs manga-ocr on the new box (D-01), Text → Run OCR fills the selected box (with the D-04 edited-flag gate), Text → OCR All Boxes (Ctrl+R) fills every text-empty box with one model load + progress (D-03), and the first-run download shows the "Loading OCR model…" UX (Pitfall 6) with a CR-11 cache-check.
- OCR results land through `set_recognized_text` (edited=False) into the same PageBox fields the Inspector (04-04) and inline editor (04-05) edit via `set_recognized_text_edited` (edited=True) — the D-04 gate now protects those manual corrections end-to-end.
- Plan 07 consumes this surface: Auto-Number (reading order over the now-recognized boxes) + Load Translations join the Text menu; Phase 5's `_ocr.json` export reads the same fields.

---
*Phase: 04-ocr-recognition-text-editing*
*Completed: 2026-08-07*

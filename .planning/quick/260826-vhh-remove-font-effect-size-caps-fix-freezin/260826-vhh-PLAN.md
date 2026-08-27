---
phase: quick-260826-vhh
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/gui/text_renderer.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/core/text_style.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/core/project_io.py
  - tests/test_core/test_text_renderer.py
  - tests/test_core/test_text_style.py
  - tests/test_gui_inspector_styling.py
  - tests/test_gui_project.py
autonomous: true
requirements: [QUICK-CAPS-FREEFORM, QUICK-SAVE-INCREMENTAL]
user_setup: []

estimate:
  tokens: 145000
  raw_tokens: 110000
  tasks: 3
  confidence: med

must_haves:
  truths:
    - "Auto-fit resolves font sizes ABOVE the legacy ~80px plateau whenever the box allows: growth continues until the fit predicate fails or target reaches min(inner_w, inner_h)"
    - "The never-fits shrink path is behaviorally unchanged (12 x 0.9 from the [10,28] base, 5px floor checked at the loop top); manual-size rendering and its overflow reporting are untouched"
    - "Outline/glow/shadow UI spins span 0..256 px, exactly matching the TextStyle model clamp; font-size (1024) and spacing (64/256) ranges untouched; TextStyle.from_dict/to_dict round-trip intact"
    - "Repeat Ctrl+S after editing only some pages rebuilds and rewrites ONLY the changed pages' .mas files (plus the manifest); clean pages whose .mas exists are never decoded, hashed, re-encoded, or rewritten"
    - "First-ever save and Save As write every page; the duplicate-stem (WR-03) and unresolvable-source (WR-02) guards still abort before any write with their existing user copy"
    - "During save the GUI thread stays responsive (entry-building + disk writing run on Worker(QRunnable), file/save actions gated by _op_running); Ctrl+S on a 1-page change completes without a multi-second freeze"
    - "Edits made WHILE a background save runs are not lost: pages re-dirtied mid-save keep dirty=True after success; save failure leaves ALL dirty flags intact (T-05-12) and surfaces the existing failure copy"
  artifacts:
    - manga_ai_studio/gui/text_renderer.py (_vertical_fit_size + horizontal fit loop in layout(): split shrink budget from unbounded-to-grow_cap growth)
    - manga_ai_studio/gui/inspector_panel.py (effect row ranges driven by the model constant; updated docstrings/comments)
    - manga_ai_studio/core/text_style.py (public EFFECT_GEOM_MAX alongside the existing public bounds block)
    - manga_ai_studio/core/project_io.py (incremental save helper: manifest lists ALL pages, only submitted pages' .mas rewritten)
    - manga_ai_studio/gui/main_window.py (_save_project split into main-thread snapshot/eligibility + Worker-dispatched build/write; per-page edit serials; op lifecycle handlers)
    - tests/test_core/test_text_renderer.py + tests/test_gui_inspector_styling.py + tests/test_gui_project.py (regression coverage for all truths above)
  key_links:
    - "Inspector spin ranges -> TextStyle coercion boundary: one shared EFFECT_GEOM_MAX constant, so UI == model forever"
    - "Eligibility rule (imf.dirty OR missing <stem>.mas) -> the .mas write set -> which dirty flags the success handler clears"
    - "_set_session_dirty increments a per-page serial -> serial captured at dispatch -> success clears a flag only when the serial is unchanged"
---

<objective>
Three fixes shipped together under one "remove artificial limits, save intelligently" theme:

(A) Auto-fit font size stops stalling near ~80px — the shared 12-iteration loop bounded growth at 28 x 1.1^11; growth now continues until the text genuinely no longer fits or the inner box dimension is reached (big SFX text). The starting-target clamp [10,28], the 12 x 0.9 shrink path, the 5px loop-top floor, and manual-size overflow reporting are all preserved exactly.

(B) Effect geometry caps removed at the UI: outline/glow/shadow spins widen from 0..10 / 0..20 / 0..10 to 0..256, driven directly by the TextStyle model constant so UI == model permanently. Big SFX strokes/glows/shadows become possible; garbage inputs still can't reach the model (V5 clamp unchanged).

(C) Chapter save stops freezing the UI: incremental dirty-only saves (rebuild+rewrite only pages marked dirty or missing their .mas; skip hashing/encoding/clean pages entirely) plus async execution (immutable payload snapshot on the GUI thread, then entry-building + LZMA compression + disk writes on a Worker(QRunnable) with _op_running gating, busy feedback, and race-safe flag clearing via per-page edit serials).

Purpose: The user hits the 80px wall constantly when typesetting SFX and loses seconds of interactivity on every Ctrl+S regardless of how little changed.
Output: Modified sources above + focused regression tests; full suite green under the pinned interpreter.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@manga_ai_studio/gui/text_renderer.py
  # Auto-fit constants ~85-102 (_OVERLAY_FIT_MAX_ITERS/_OVERLAY_FIT_STEP/_OVERLAY_FIT_GROW_STEP/_BASE_CLAMP_*, note _OVERLAY_FIT_FLOOR_PX checked at loop TOP)
@tests/test_gui_project.py
  # Save/load suites incl. WR-01 stray-folder cases (~992-1085), dialog-mock patterns (monkeypatch QMessageBox)
@manga_ai_studio/core/project_io.py
  # _atomic_write_bytes (~114-131), save_page_file (~134-143), build_page_entries (~495-568), save_project (~571-603), sha256_file (~763)
@manga_ai_studio/gui/worker_thread.py
  # Worker(QRunnable)/WorkerSignals contract: task fn touches only numpy/Python + emits; Qt mutation in main-thread handlers ONLY
@AGENTS.md
  # THE pinned interpreter for every pytest invocation in this plan
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GUI thread -> QThreadPool worker | Save payloads (numpy arrays, PageBox copies, stems) cross threads; only plain data may cross |
| Untrusted .mas/.json -> TextStyle.from_dict | V5 coercion boundary (unchanged this task) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QHH-01 | Tampering | Box/styles mutated on GUI thread while Worker serializes them | high | mitigate | Immutable snapshot before dispatch: ndarray .copy(), PageBox.copy(), mask_to_numpy_binary on main thread; worker receives frozen payloads only |
| T-QHH-02 | Availability | Lost-change window: success handler clearing flags for pages edited mid-save | high | mitigate | Per-page edit serial captured at dispatch; clear a flag only when its serial is unchanged at completion |
| T-QHH-03 | Availability | Stale completion applying titles/flags to a swapped session | medium | mitigate | Session-generation token captured at dispatch; mismatched completion logs and bails (disk artifacts stay valid) |
| T-QHH-04 | DoS | Garbage huge effect radii persisted via hand-edited .mas | low | accept | V5 _EFFECT_GEOM_MAX clamp retained; UI cannot produce out-of-range values; absurd hand-edits clamp silently (documented behavior) |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Remove the auto-fit growth plateau + widen effect ranges to the model bound</name>
  <files>manga_ai_studio/gui/text_renderer.py, manga_ai_studio/core/text_style.py, manga_ai_studio/gui/inspector_panel.py</files>
  <read_first>
manga_ai_studio/gui/text_renderer.py lines 85-110 (constants), 578-620 (_vertical_fit_size — the full loop), 650-750 (layout(): manual path AND the horizontal auto-fit loop — read the entire loop body before editing; it ends shortly after the shown growth branch);
manga_ai_studio/core/text_style.py lines 48-63 (bounds block: _EFFECT_GEOM_MAX private vs ROTATION_MAX/CHAR_SPACING_MAX/LINE_SPACING_MAX public) and 105-129 (_coerce_effect usage site);
manga_ai_studio/gui/inspector_panel.py lines 52-64 (Security docstring bullets documenting the old ranges), 502-525 (spacing rows citing the V5-clamps-matching pattern), 544-571 (the effect-row loop with hardcoded (0,10)/(0,20)/(0,10));
tests/test_core/test_text_renderer.py (find existing auto-fit/growth assertions first — grep for auto_fit, fit, grow), tests/test_core/test_text_style.py (round-trip/clamp test shapes), tests/test_gui_inspector_styling.py (how the panel is instantiated/asserted in tests)
  </read_first>
  <action>
PART A — text_renderer.py. There is NO literal 80 constant; the plateau comes from _OVERLAY_FIT_MAX_ITERS (12) serving BOTH directions: growth starts at the clamped base 28 and multiplies by _OVERLAY_FIT_GROW_STEP (1.1) once per loop turn, so a big box exhausts 12 turns near 28 x 1.1^11 (~80px) while still fitting. Fix BOTH loops (vertical `_vertical_fit_size` and the horizontal inline loop inside `layout()`) by splitting the shared budget into a dedicated shrink allowance, keeping the growth direction genuinely bounded only by `grow_cap`:

Restructure each loop to this shape (NO fenced code will carry over — express as prose): initialize `shrink_budget = _OVERLAY_FIT_MAX_ITERS`; loop indefinitely; FIRST statement of the body keeps the existing floor check verbatim (break when target <= _OVERLAY_FIT_FLOOR_PX). On a FITTING probe: keep the last-fitting candidate exactly as today (vertical: size/fit_held; horizontal: doc/size/overflow/fit_held), break when target >= grow_cap - _EPS, else target = min(grow_cap, target * _OVERLAY_FIT_GROW_STEP). On a FAILING probe AFTER a held fit: break (unchanged). On a failing probe with no held fit: perform today's exact else-branch bookkeeping (size/overflow assignments, target *= _OVERLAY_FIT_STEP), then decrement shrink_budget and break when it reaches 0. Using a `while True:` with this structure reproduces the never-fits endpoint byte-for-byte (today's range(12) exhaustion lands on the same final size) while letting a still-fitting text grow arbitrarily until grow_cap.

Do NOT touch: the [10,28] base clamp as the STARTING target (UI-SPEC A2/G-07-4 contract — explicitly confirmed intentional), _OVERLAY_FIT_FLOOR_PX location (loop top), the fit predicates (including the horizontal split-Latin-means-failed-fit rule from quick-260823-hge), _FONT_SIZE_MAX (manual-size clamp only — auto-fit may legitimately exceed it now), overflow reporting for manual sizes, and _OVERLAY_FIT_MAX_ITERS's new meaning as the SHRINK budget. Update the three docstrings/comments that describe the growth as capped/bounded (module constant comment block ~94-97 already says "bounded shrink loop" — now accurate; refresh `_vertical_fit_size`'s docstring ~581-591, layout()'s auto-fit comment ~687-690, and any module-docstring mention stating total-iteration bounding — grep "12" / "bound" / "cap" in the file to catch stragglers). Note in the docstring why no extra safety bound is added: iterations are ceil(log(grow_cap/start)/log(1.1)) — dozens at most for any realistic scene box, each cheap relative to a paint.

PART B — text_style.py + inspector_panel.py, moved TOGETHER so UI and model never disagree. In text_style.py, promote the effect bound into the EXISTING public constants block (~line 54-61): declare `EFFECT_GEOM_MAX = 256.0` beside LINE_SPACING_MAX (docstring line echoing the neighbors' rationale — generous sanity ceiling, larger is garbage not intent), and switch `_coerce_effect` (~line 123) plus the `_EFFECT_GEOM_MAX` definition site to consume it (remove the private underscore spelling entirely so only one symbol exists; update the class from_dict docstring wording only if it names the private name). Model CLAMP BEHAVIOR IS UNCHANGED — the 0..256 coerced range already exists; only the naming goes public.

In inspector_panel.py: import EFFECT_GEOM_MAX from core.text_style; drive the effect-row loop's ranges from it — all three keys become (0, int(EFFECT_GEOM_MAX)). _EFFECT_DEFAULT_VALUES defaults stay exactly as they are. Then update every stale-range sentence: the Security docstring bullet ~60-63 ("outline 0..10, glow 0..20, shadow 0..10") gains a note that effect width/radius spans 0..256 matching the TextStyle V5 clamp (a big SFX stroke/glow is intent, not garbage), the inline comment above the effect-row loop ~544-547 likewise; grep the file for "0..10", "glow 0..20", and similar range spellings to catch tooltips or comments. Size spin (0..1024, 0=Auto sentinel) and spacing ranges (0..64 / 0..256) stay untouched — the request covers outline/glow/shadow only.

Renderer consumption needs NO change: text_renderer/paint path already honors width_px/radius_px verbatim with no secondary cap.

Tests (mirror each suite's existing fixture style): in tests/test_core/test_text_renderer.py add (1) big-box growth: construct a tall/large inner box whose fit predicate holds broadly (e.g., short text, wide inner_w/inner_h) and assert the returned size exceeds the legacy plateau (> 90 scene-px — ideally approaching grow_cap minus the growth-step granularity; pick assertions robust to Qt metric jitter using generous windows like >= 100, <= grow_cap) and overflow False; include one VERTICAL-mode twin. (2) plateau regression became-generous: same-shaped assertion that growth does NOT stop early merely due to iteration count — implicitly covered by (1)'s lower bound; make it explicit with a size class only reachable past the old cap. (3) shrink-path equivalence: tiny box forces the never-fits path — assert the chosen size equals the legacy endpoint derived from 28 * 0.9**11 and respects the 5px floor logic (compute expected inline in the test rather than hardcoding a magic number). In tests/test_core/test_text_style.py add: EFFECT_GEOM_MAX exported and _coerce_effect/from_dict still clamp width_px/radius_px to it (e.g., 999 -> 256, non-numeric -> default) and round-trip a 256.0 radius through to_dict/from_dict unchanged. In tests/test_gui_inspector_styling.py add: instantiate the panel and assert each effect spin's range is (0, int(EFFECT_GEOM_MAX)) and that committing a 256 glow radius through the panel's commit path lands in the resulting TextStyle un-re-clamped (== 256). Run everything through the pinned interpreter from AGENTS.md.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_renderer.py tests/test_core/test_text_style.py tests/test_gui_inspector_styling.py tests/test_gui_canvas.py -q</automated>
  </verify>
  <done>Big-box auto-fit resolves well past the old ~80px ceiling (both orientations) while small-box/never-fits behavior and manual sizing are bit-identical to today; the three effect spins accept up to 256 with defaults unchanged; all pre-existing renderer/style/inspector/canvas tests pass untouched.</done>
</task>

<task type="auto">
  <name>Task 2: Incremental dirty-only save core (synchronous)</name>
  <files>manga_ai_studio/core/project_io.py, manga_ai_studio/gui/main_window.py, tests/test_gui_project.py</files>
  <read_first>
manga_ai_studio/gui/main_window.py lines 2329-2405 (_session_dirty/_update_title/_set_session_dirty/_snapshot_current_page), 2440-2540 (_discard_stray_project_dir tail + _page_image_source), 2540-2718 (_save_project family end to end — the loop being restructured sits at ~2601-2633, guards at ~2646-2685, success tail ~2702-2711), 720-800 region for context on action wiring;
manga_ai_studio/core/project_io.py lines 103-205 (_pack_entry/_atomic_write_bytes/save_page_file/load_page_file), 495-655 (build_page_entries + save_project + load_project);
tests/test_gui_project.py test_save_project_writes_project_folder (~232), the WR-01 cluster (~992-1160), test_unsaved_changes_prompt_save_discard_cancel (~597), and the dialog-monkeypatch helpers those use;
grep main_window.py for "\.dirty = True" to enumerate every dirty-marking site (canvas signal handler ~2360-2376 plus batch paths ~7391/~7460)
  </read_first>
  <action>
Goal: a repeat save touching one page stops rebuilding all the others. Keep the WHOLE flow synchronous in this task (async lands in Task 3); the freeze shrinks here because the dominant cost (per-page decode/hash/PNG-encode/LZMA) simply stops happening for clean pages.

project_io.py — add `save_project_incremental(project_dir, project_name, rebuilt_pages: list[tuple[str, dict[str, bytes]]], all_stems: list[str]) -> Path`: identical folder/atomicity/non-destructive-overwrite rules as save_project (D-02), manifest content identical in shape (version/name/pages with "name"+"file" for EVERY entry in all_stems order), but `save_page_file` runs ONLY for the tuples in rebuilt_pages; every other listed `<stem>.mas` on disk is left byte-identical. Implementation: extract nothing from save_project — a standalone sibling function that mirrors its body minus the unfiltered page loop is cleaner than parameterizing (leave save_project untouched: its own tests and external callers stay valid). Docstring states the incremental contract explicitly: callers MUST guarantee each all_stems entry either appears in rebuilt_pages or already has a resolvable .mas beside the manifest.

main_window.py — rework the `_save_project` middle section: after project_dir is resolved (dialog included — ORDER MATTERS: the existence checks below need the final directory), classify every page first: eligible = `imf.dirty` OR NOT `(project_dir / f"{imf.path.stem}.mas").is_file()`. Force_as and first-ever saves fall out naturally (nothing exists yet, so everything is eligible). Then build `page_files` ONLY from eligible pages, moving the original_sha computation INSIDE that branch (sha256_file stays per-rebuilt-page only — never for skipped pages). Keep `_snapshot_current_page()` where it is. Guards, adapted minimally: the duplicate-stem (WR-03) check runs over the FULL stem list of the session (all pages, including skipped) BEFORE any write, unchanged in behavior and copy; the WR-02 guard becomes: every ELIGIBLE page must resolve an image source — abort with the existing save-failure copy (listing offending page names in the log as today) when one doesn't, dirty flags untouched, stray-folder cleanup honored via created_default exactly as now. A degenerate corner falls out of the math and deserves a defensive branch anyway: eligible set empty while the session claims dirtiness and force_as is False cannot happen (dirty IS the eligibility trigger) — if it somehow does, log loudly and proceed with manifest-only rewrite rather than masking a state-machine bug. The success tail switches to `save_project_incremental`, passing all_stems in `self.image_files` order; transient status reports both totals, e.g. Saved project 'X' (N pages, M written). Flags still clear for ALL pages here (synchronous truthfulness: whatever was on screen was just serialized). Signature/return semantics untouched this task — `_save_project(force_as=False) -> bool` means completed, as today.

Defensive detail worth spec-ing now because Task 3 leans on it: derive a tiny helper on the MainWindow, e.g. `_eligible_save_pages(project_dir) -> list[int]`, returning indices needing rebuild; `_save_project` consumes it so Task 3 reuses the exact classification instead of duplicating logic.

Tests in tests/test_gui_project.py, reusing the file's established window/dialog fixtures and tmp project trees: (1) single-page delta: save a 3-page chapter, mutate ONLY page 2's boxes (set its dirty flag plus a real content change), save again — assert manifest lists 3 pages in order, page 1 and 3 .mas bytes are UNCHANGED compared to snapshots taken after the first save, and page 2's .mas differs; (2) clean-pages-cost-nothing: count `build_page_entries` calls across the second save via monkeypatch wrapping — eligible pages only (guards against accidentally hashing/encoding clean pages later); (3) resurrect-missing-page: delete page 3's .mas from an already-saved project, save cleanly with NO edits — save succeeds and page 3 is rewritten (missing-file eligibility) while pages 1/2 stay untouched; (4) Save As into a fresh dir rewrites everything (force_as coverage); (5) pre-existing WR-01/WR-03-flavored failures still abort before ANY .mas write with flags intact (duplicate stems among CLEAN pages must still trip the guard — a stem collision where only one of the colliding pair is dirty). All async-sensitive assertions unnecessary this task — these tests may remain synchronous; Task 3 adapts whichever start blocking.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_project.py tests/test_core -q</automated>
  </verify>
  <done>A second save after a one-page edit performs build_page_entries exactly once for that page, leaves every other .mas byte-identical, still rewrites the full manifest; WR-02/WR-03 aborts keep their copy and dirty-flag safety; the entire pre-existing save/load suite passes.</done>
</task>

<task type="auto">
  <name>Task 3: Non-blocking async save with race-safe dirty-flag handling</name>
  <files>manga_ai_studio/gui/main_window.py, manga_ai_studio/core/project_io.py, tests/test_gui_project.py</files>
  <read_first>
manga_ai_studio/gui/main_window.py — the detect flow as THE template: ~4800-4870 (guard, Worker construction, signal connects, _op_running=True, progress bar show, QThreadPool dispatch) and its paired handlers (_on_detection_progress/result/error/cleanup ~5200-5240 incl. the _op_running=False + _refresh_action_states tail); inpaint finished handler ~5974-6020 for the heavier completion pattern; _refresh_action_states gating lines ~1337-1425 (note action_save_project/_as at ~1349-1350 ALREADY key on _op_running — free lockout); open-project _op_running rejection ~2719-2760; grep "image_files = " for every session-swap site and "closeEvent" for shutdown gating;
manga_ai_studio/core/project_io.py — save_project_incremental signature as Task 2 delivered it; mask_to_numpy_binary import site in main_window (used at ~2609-2611);
tests/test_gui_project.py — test_menu_gating_during_op (~575) for the gating-test pattern; the exception-dialog tests (~1130+) for QMessageBox.monkeypatch style; any existing qtbot.waitUntil usage in the suite to mirror waits
  </read_first>
  <action>
Split `_save_project` along the seam Task 2 created into a main-thread PREPARE phase and a Worker-executed WRITE phase, then land results back on the Qt main thread via WorkerSignals — reusing gui/worker_thread.Worker verbatim (QThreadPool.globalInstance().start, setAutoDelete(True), connect progress/result/error/finished exactly like detect_text). One approach, specified concretely (the immutable-snapshot variant with serial verification — do NOT swap for a different design):

PREPARE (GUI thread, fast enough to stay interactive — hundreds of ms at worst vs today's seconds): everything Task 2 does UP TO dispatch — guards, early returns, dialog, name derivation, eligibility via _eligible_save_pages, duplicate-stem check, WR-02 source resolution — but the per-page payload capture now FREEZES state instead of sharing live structures: image source via _page_image_source(idx).copy(); mask via mask_to_numpy_binary(imf.mask) when present (QImage-touching work NEVER enters the worker); plane binaries via the existing _page_plane_keys feed, each array copied; boxes as fresh detached copies ([b.copy() for b in imf.boxes] when set); stems and metadata as plain values. Compute NOTHING expensive here — no sha256, no PNG encoding, no LZMA. Also capture two tokens: snapshot_serials = {idx: self._page_edit_serials[idx] for each eligible idx} and session_gen = self._session_generation.

DIRTY-SERIAL INFRASTRUCTURE: add `self._page_edit_serials` (int->int, defaulting 0) and `self._session_generation` (int, 0) to __init__ (~line 174 area, beside _op_running). Increment the page's serial inside _set_session_dirty right after marking dirty. Route the OTHER direct-marking sites (batch paths found by the Task-1 grep for ".dirty = True") through _set_session_dirty or a tiny shared mutator so serial counting has ONE choke point — audit each site: suppression-guard interactions matter (_suppress_boxes_push early-return skips the bump correctly). Bump _session_generation at every site that REPLACES self.image_files (open project/session load/page-close/single-page loads); grep-driven, mechanical.

WRITE PHASE (Worker fn `_run_save_task`, runs off-thread touching ONLY its arguments + project_io): for each payload compute original_sha256 (for its own source-path), call build_page_entries, collect (stem, entries); then ONE call to save_project_incremental(project_dir, name, rebuilt, all_stems). Raise on OSError/ProjectFormatError naturally — Worker converts exceptions to the error signal carrying WorkerError. Optional progress emission per completed page drives the existing progress bar read-only (indeterminate-friendly: prefer a busy "Saving…" status bar label over percent math — chapters finish in well under a minute; simplest is NO progress connection, just indeterminate bar + status text, matching how brief this is).

COMPLETION HANDLERS (main thread): `_on_save_finished(result)` (result signal) — bail with a debug log when session_gen != self._session_generation (T-QHH-03; nothing UI-side is touched, the on-disk artifacts remain internally consistent). Otherwise, per eligible idx: clear imf.dirty ONLY IF snapshot_serials[idx] == self._page_edit_serials[idx] (a mid-save edit re-bumped the serial; that page stays dirty and rides the NEXT save — T-QHH-02, the no-lost-changes invariant); then record project_dir/name, _add_recent_project, _update_title, transient status with both counts (reuse Task 2's phrasing), _op_running=False, _refresh_action_states(), progress bar hidden. `_on_save_error(worker_error)` (error signal) — log the traceback from the WorkerError payload, surface the EXISTING T-05-12 critical copy (Couldn't save '{name}'. / writable-folder text) with created_default stray-folder cleanup exactly as the synchronous path did, touch ZERO dirty flags (failure keeps the session recoverable), reset _op_running/progress/action states. Route BOTH tails through one small `_finish_save_op()` reset helper so no path forgets the bar/actions. ALSO connect `finished` to tolerate Worker RuntimeError shutdown races per the vendored contract.

INTEGRATION CONTRACTS: `_save_project` keeps its name/signature; its documented meaning becomes: True = nothing-to-do OR save accepted and running (preparation succeeded, work dispatched), False = aborted or failed during preparation (dialog cancel, WR-02/WR-03, unexpected exception — all still detected synchronously, so the Unsaved-Changes gate and chapter-climb callers keep their correctness property: False still blocks destructive successors). Read the _confirm_discard_changes call sites and confirm the Proceed-while-saving consequence is guarded by _op_running (Open Project/New Folder/etc. reject at their _op_running sentinels — verified at ~1351/~2734). Close behavior: whatever closeEvent does for detect/inpaint ops must cover a running save identically — if it prompts/postpones, a saving window gets the same treatment (wire the minimal gate if absent; mid-quit worker death is prevented by the SAME mechanism as other ops, and _atomic_write_bytes already makes any interrupted write corruption-free as backstop). _save_project_as needs no change. Mid-op re-entrancy is free: the slot opens with the standard `if self._op_running: return`.

TEST ADAPTATION + NEW COVERAGE (qtbot): flip Task 2's immediate-state assertions to `qtbot.waitUntil(lambda: not win._op_running)` guards before asserting (enumerate the affected saves in the file — the new ones from Task 2 plus pre-existing synchronous expectations like test_save_project_writes_project_folder and the trigger tests ~966-1085; minimal diff per test, assertions themselves stand). New tests: (1) responsiveness/race: monkeypatch-slow the worker fn entry (wrap _run_save_task to call the original after a small Event-wait or processEvents pump), trigger Ctrl+S, while running mark ANOTHER page dirty via _set_session_dirty, waitUntil finished — that page keeps dirty=True, the originally-edited page clears, title/status correct; repeat variant re-dirtying the SAME page mid-save (serial bump) — its flag survives. (2) generation guard: dispatch a save, replace self.image_files wholesale WITH a bumped _session_generation before completion lands, assert completion bails without touching the new session's flags (worker still wrote files — assert on disk). (3) failure path: monkeypatch project_io.save_page_file (or save_project_incremental) to raise OSError; waitUntil not _op_running; flags ALL still True, critical-dialog mock fired with the standing copy, stray folder cleaned when created_default applied. (4) gating already covered by test_menu_gating_during_op — extend its expectations to include action_save_project disabled during ANY op if not already asserted.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_project.py tests/test_gui_canvas.py tests/test_core -q</automated>
  </verify>
  <done>Ctrl+S returns control immediately (progress shows Saving…, menus gate via _op_running); a full-suite pass proves no behavioral drift in non-save areas; mid-save edits survive with flags intact; failure and cancelled-dialog paths leave the session exactly as actionable as before; full suite 1169-pass baseline maintained (plus new tests).</done>
</task>

</tasks>

<verification>
Run the complete suite with the pinned interpreter as the final gate:
& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q
Baseline expectation: 1169 passed before this task; the delta is strictly additive test wins, zero regressions. Manual smoke for the feel-level requirement (freeze elimination) belongs in the SUMMARY notes for the orchestrator, not a blocking gate: launch via start.bat, open a multi-page chapter, edit one translation, Ctrl+S — typing/canvas interaction should stay responsive and a second Ctrl+S moments later should flash quickly.
</verification>

<success_criteria>
- Auto-fit sizes exceed the former ~80px plateau whenever the box permits, in horizontal AND vertical modes, with shrink/floor/manual behavior provably unchanged
- Outline/glow/shadow spin maxima read from EFFECT_GEOM_MAX (single shared constant; UI == model by construction)
- Only dirty/missing .mas pages are decoded, hashed, encoded, compressed, or written on repeat saves; the manifest always describes the full session
- Saves execute off the GUI thread behind the app's standard Worker/_op_running pattern with busy feedback and lockout parity with detect/inpaint
- Every failure path preserves dirty flags and existing user-facing copy; every success path is race-correct against concurrent edits and session swaps
</success_criteria>

<output>
Create .planning/quick/260826-vhh-remove-font-effect-size-caps-fix-freezin/260826-vhh-SUMMARY.md when done
</output>

---
phase: quick-260826-vhh
plan: 01
status: complete
subsystem: typesetting-save
tags: [auto-fit, font-size, effect-ranges, incremental-save, async-worker, race-safety, dirty-tracking]
requires:
  - project_io.save_project / _atomic_write_bytes (D-02 atomicity)
  - gui/worker_thread.Worker(QRunnable) + WorkerSignals contract
  - TextStyle V5 coercion boundary (effect geometry 0..256)
  - ImageFile.dirty D-07 dirty tracking + _op_running action lockout
provides:
  - Unbounded-to-grow_cap auto-fit growth in both orientations (legacy ~80px plateau removed)
  - TextStyle.EFFECT_GEOM_MAX public constant shared by model clamp AND Inspector spins
  - project_io.save_project_incremental (full manifest, rebuilt-subset .mas writes)
  - MainWindow._eligible_save_pages / _bump_page_serial / _session_generation race tokens
  - Non-blocking Ctrl+S behind the standard Worker/_op_running pattern
affects: [chapter save UX, SFX typesetting fidelity, inspector styling]
key-files:
  created:
    - none
  modified:
    - manga_ai_studio/gui/text_renderer.py
    - manga_ai_studio/core/text_style.py
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/core/project_io.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_core/test_text_renderer.py
    - tests/test_core/test_text_style.py
    - tests/test_gui_inspector_styling.py
    - tests/test_gui_project.py
decisions:
  - "Shrink budget split: _OVERLAY_FIT_MAX_ITERS(12) re-scoped to SHRINK-only; growth bounded solely by grow_cap=min(inner_w, inner_h); never-fits endpoint verified byte-equal to legacy 28 x 0.9**11"
  - "EFFECT_GEOM_MAX promoted to the existing PUBLIC bounds block; private underscore spelling deleted so UI == model by construction (one symbol)"
  - "Eligibility rule = imf.dirty OR missing <stem>.mas; force_as keeps full-rewrite Save As semantics; clean-session 'No changes' flash only fires when every listed .mas is present (missing .mas resurrects)"
  - "WR-02 tightened: an ELIGIBLE page with no resolvable source aborts the whole save pre-write (legacy skip-and-continue could clear its flag while unsaved)"
  - "RECEIVER-CONTEXT RULE (probed): cross-thread queued signal delivery to receiver-less lambdas/partials on an auto-deleting pooled Worker is silently dropped -- save completions use bound-method handlers reading a per-dispatch _save_op_ctx stored on the window"
  - "Async return contract: True = nothing-to-do OR dispatched-running; False reserved for preparation failures so the Unsaved-Changes gate property survives"
metrics:
  duration: ~59 min
  completed: 2026-08-27
estimate:
  tokens: 145000
  tasks: 3
actuals:
  tokens: ~20000   # chars/4 over realized diff (~1350 insertions / ~215 deletions across 9 files)
  tasks: 3
  commits: 3
---

# Quick Task 260826-vhh Summary — Font cap removal + smart non-blocking saves

Three fixes under one theme: auto-fit grows until it genuinely stops fitting (no more ~80px SFX wall), outline/glow/shadow spins read the model's own 256 bound, and Ctrl+S became incremental and off-thread (only edited pages are rebuilt and the GUI thread never blocks).

## Tasks

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | Remove auto-fit growth plateau + widen effect ranges to model bound | 7597d36 | done |
| 2 | Incremental dirty-only save core (synchronous) | 0579f9a | done |
| 3 | Non-blocking async save with race-safe dirty handling | 41efbd1 | done |

## What changed

**(A) Auto-fit plateau removed** — both fit loops (`_vertical_fit_size` and the horizontal inline loop in `layout()`) restructured as `while True` with a dedicated `shrink_budget`: fitting probes now grow by 1.1x without any iteration ceiling until the fit predicate fails or `min(inner_w, inner_h)` is reached. The never-fits shrink path (12 x 0.9 from the [10,28] start, 5px floor at loop top) kept byte-equivalent endpoints; manual sizing/overflow untouched.

**(B) Effect caps lifted at the UI only where intent exists** — `TextStyle.EFFECT_GEOM_MAX = 256.0` is now the single public symbol consumed by `_coerce_effect` and all three Inspector spins (`0..int(EFFECT_GEOM_MAX)`). Defaults (outline 2 / glow 4 / shadow 2) unchanged; size 0..1024 and spacing ranges untouched.

**(C) Smart saves** — `save_project_incremental()` mirrors `save_project`'s atomicity but runs `save_page_file` only for submitted pages while the manifest lists every stem. `_save_project` PREPAREs on the GUI thread (guards, dialog, eligibility via `_eligible_save_pages`, T-QHH-01 frozen payloads: ndarray/PageBox copies) then dispatches one Worker for sha256+build+write behind an indeterminate "Saving…" bar with `_op_running` gating parity to detect/inpaint. Completion clears each eligible page's flag ONLY if its edit serial (`_page_edit_serials`, bumped through `_set_session_dirty` + both batch loops) is unchanged since dispatch (T-QHH-02) and the session generation token matches (T-QHH-03). Failure keeps ALL flags, shows the standing T-05-12 copy, cleans stray folders.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Async completion signals silently dropped (receiver-less connections)**
- **Found during:** Task 3 (first GREEN run — worker wrote files but flags/title/recents never updated)
- **Issue:** `worker.signals.result.connect(lambda ...)` / partial-style connections deliver cross-thread queued calls via the SENDER context; the pooled Worker is auto-deleted when `run()` returns, so those deliveries vanish nondeterministically. Probed empirically (dispatch/cleanup fired; result handler never ran).
- **Fix:** Per-dispatch tokens moved onto `self._save_op_ctx`; handlers rewired as plain bound methods of the living window (matches every vendored handler). Documented inline as the RECEIVER-CONTEXT RULE.
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Commit:** 41efbd1

**2. [Plan-letter fix] Defensive empty-payload corner**
- Initial Task-2 edit accidentally left the unreachable empty-payload branch ABORTING instead of the plan's "log loudly and proceed manifest-only"; corrected during the Task-3 rewrite.

### Test-adaptation deviations (documented, not behavioral drift)

- `test_save_pre_write_exception_shows_dialog_and_cleans_stray` rescoped/released as `test_save_write_phase_exception_shows_dialog_and_cleans_stray`: with serialization moving to the Worker, that crash class arrives via the typed error signal asynchronously (dispatch still True per contract). Dialog-copy + stray-folder-cleanup regression value preserved.
- Save suite gained `_wait_save_done(qtbot)` + `qtbot=` kwarg on the `_save_as` helper — completion-state assertions now wait deterministically (plan-mandated adaptation).
- Build-count assertions patched AFTER the first waited save where the counter must exclude first-save work.

## Deferred Issues / Out of Scope

- **PRE-EXISTING FAILURE (unrelated, evidence-backed):** `tests/test_gui_boxes.py::test_no_ghost_after_undo_and_scroll` fails identically in a clean checkout of pre-Task-3 HEAD `0579f9a` (and in isolation, reproducibly). Confirmed not caused by this task; NOT fixed here per scope boundary. Needs its own diagnostic pass.
- **Manual smoke (feel-level)** deferred per plan to the orchestrator/user: launch via `start.bat`, multi-page chapter, edit one translation, Ctrl+S — typing/canvas should stay responsive; second Ctrl+S moments later flashes quickly.

## Verification

| Gate | Command (pinned interpreter) | Result |
|------|------------------------------|--------|
| Task 1 | pytest test_text_renderer test_text_style test_gui_inspector_styling test_gui_canvas (+test_typeset_layout) | 131 passed |
| Task 2 | pytest test_gui_project tests/test_core | 385 passed |
| Task 3 | pytest test_gui_project test_gui_canvas tests/test_core | 428 passed |
| Final | pytest -q (full suite) | 1185 collected: **1184 passed**, 1 failed (pre-existing boxes ghost test above) |

New tests added: 15 (renderer 3 incl. vertical twin + computed-endpoint shrink equivalence; style 2 incl. boundary round-trip; inspector 2 incl. 256-through-commit; project GUI 10 incl. byte-identical clean pages, build-once counting, missing-.mas resurrection, Save As full rewrite, dup-stem-among-clean abort, eligible-unresolvable whole-save abort, dispatch responsiveness, same-page/mid-save serial races, generation-swap bail, OSError failure trio).

## Threat mitigations delivered

- T-QHH-01 immutable snapshot (ndarray `.copy()`, detached PageBoxes, planes unpacked main-thread; nothing Qt crosses into the worker)
- T-QHH-02 per-page edit serials → no lost-change window
- T-QHH-03 session-generation bail → stale completions never touch a swapped-in session
- T-QHH-04 accepted: V5 clamp retained verbatim; UI cannot produce out-of-range values anymore either

## Self-Check: PASSED

- Commits exist: 7597d36, 0579f9a, 41efbd1 (verified via git log)
- All 9 modified files present in working tree & committed state
- Full-suite run executed post-commit via pinned interpreter

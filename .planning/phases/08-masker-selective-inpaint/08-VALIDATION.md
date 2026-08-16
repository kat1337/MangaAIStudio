---
phase: 8
slug: masker-selective-inpaint
status: ready
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-15
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-qt (PySide6 GUI tests, headless-capable) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/<file> -x -q` |
| **Full suite command** | `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` |
| **Estimated runtime** | ~2 minutes (717-test baseline) |

> **Interpreter pin (AGENTS.md):** always use the pinned project interpreter above; bare `python`/`pytest` on PATH resolves to an unrelated venv.
> **Command shorthand:** `pytest <args>` in the map below means the pinned-interpreter full command above.

---

## Sampling Rate

- **After every task commit:** Run the quick command on the touched test files
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~120 seconds (full suite)

---

## Per-Task Verification Map

All 21 tasks across 9 plans. Every task carries an `<automated>` verify (Nyquist 8a-8d satisfied); no task depends on a pre-existing Wave 0 stub — each new test file is created by its own task's TDD cycle (behavior block written before implementation).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-T1 | 08-01 | 1 | MASK-03 | — | `inpaint_state` pure matrix (override tri-state + std-dev gate + mask-content check) | unit | `pytest tests/test_core/test_box_model.py -q` | ✅ existing | ⬜ pending |
| 08-01-T2 | 08-01 | 1 | MASK-01 | T-08-01 | Radius loads only via typed `try_to_load` coercion; garbage INI falls back to defaults | unit | `pytest tests/test_core/test_masker_config_roundtrip.py -q` | new (TDD in-task) | ⬜ pending |
| 08-01-T3 | 08-01 | 1 | MASK-02 | — | Geometry rebuilds invalidate mask/std_dev (stale fits never reused after rotate/crop/resize) | unit | `pytest tests/test_core/test_image_ops.py -q` | ✅ existing | ⬜ pending |
| 08-02-T1 | 08-02 | 1 | MASK-01, MASK-05 | T-08-02 | Plane recompose `(manual\|auto) & ~erase`; erase ledger never resurrects across re-dilate | gui | `pytest tests/test_gui_mask_planes.py -q` | new (TDD in-task) | ⬜ pending |
| 08-02-T2 | 08-02 | 1 | MASK-01, MASK-02 | — | Plane-aware undo + D-11 page-switch round-trip with `.copy()` boundaries | gui | `pytest tests/test_gui_mask_planes.py tests/test_box_persistence.py tests/test_gui_project.py -q` | mixed (new + 2 existing) | ⬜ pending |
| 08-02-T3 | 08-02 | 1 | MASK-06 | T-08-03 | Dispatch carve-out is modifier-routing only; crop + double-click branches byte-identical | gui | `pytest tests/test_gui_mask_planes.py -q` | in-plan (from T1) | ⬜ pending |
| 08-03-T1 | 08-03 | 2 | MASK-02 | — | Vendored machinery battery: grow exactness, intersection discard, BlankMaskError, pick_best_mask semantics | unit | `pytest tests/test_core/test_masker_machinery.py -q` | new (TDD in-task) | ⬜ pending |
| 08-03-T2 | 08-03 | 2 | MASK-02 | T-08-04 | V5 int-coercion + per-edge clamp + zero-area drop on untrusted blk coords | unit | `pytest tests/test_core/test_detection_boxes.py -q` | new (TDD in-task) | ⬜ pending |
| 08-03-T3 | 08-03 | 2 | MASK-01, MASK-02, MASK-05 | T-08-04, T-08-05 | Discard-at-seam (dilate-then-∩) + gate-lifted fits; box-bounded fitting cost | unit | `pytest tests/test_core/test_detection_boxes.py tests/test_core/test_masker_machinery.py -q` | in-plan (from T2) | ⬜ pending |
| 08-04-T1 | 08-04 | 2 | MASK-02, MASK-03 | T-08-06, T-08-08 | Untrusted per-box decode fully wrapped → ProjectFormatError; decoded size cross-checked vs box dims | unit | `pytest tests/test_core/test_project_io.py -q` | ✅ existing | ⬜ pending |
| 08-04-T2 | 08-04 | 2 | MASK-02, MASK-03 | T-08-07 | Packed plane blob length cross-checked (ceil(h·w/8)) before unpack | unit | `pytest tests/test_core/test_project_io.py -q` | ✅ existing | ⬜ pending |
| 08-05-T1 | 08-05 | 2 | MASK-01 | T-08-09 | Widget-level range clamps (invalid values unreachable); programmatic population never emits | gui | `pytest tests/test_gui_detection_settings.py -q` | new (TDD in-task) | ⬜ pending |
| 08-05-T2 | 08-05 | 2 | MASK-01, MASK-02 | T-08-10 | Save-through guarded (read-only config dir logs a warning, never crashes) | gui | `pytest tests/test_gui_detection_settings.py -q` | in-plan (from T1) | ⬜ pending |
| 08-06-T1 | 08-06 | 2 | MASK-03 | T-08-11 | Border state derived from the same pure fn that gates mask contribution (cannot disagree) | gui | `pytest tests/test_gui_border_states.py -q` | new (TDD in-task) | ⬜ pending |
| 08-07-T1 | 08-07 | 3 | MASK-01, MASK-02, MASK-05 | T-08-12 | D-04 gate runs BEFORE any mask/box mutation; result dict consumed via V5 clamps only | gui | `pytest tests/test_gui_detection_boxes.py -q` | ✅ existing (extended) | ⬜ pending |
| 08-07-T2 | 08-07 | 3 | MASK-02 | T-08-13 | Refit restricted to geometry-changed/new boxes, commit-time only, no-op without raw mask | gui | `pytest tests/test_gui_detection_boxes.py tests/test_gui_boxes.py -q` | ✅ existing | ⬜ pending |
| 08-07-T3 | 08-07 | 3 | MASK-01, MASK-02 | T-08-13, T-08-14 | Restore consumes only 08-04-validated packed blobs; .mas round-trip driven through the real save path (save-loop plane keys exercised) | gui | `pytest tests/test_gui_detection_boxes.py -q` | ✅ existing (extended) | ⬜ pending |
| 08-08-T1 | 08-08 | 4 | MASK-03 | — | Mixed sentinel never commits (widget layer only); loaded-memory guard blocks spurious commits | gui | `pytest tests/test_gui_inspector_override.py -q` | new (TDD in-task) | ⬜ pending |
| 08-08-T2 | 08-08 | 4 | MASK-03 | T-08-15 | Every override change is ONE named, reversible undo unit (single snapshot incl. multi-box) | gui | `pytest tests/test_gui_inspector_override.py -q` | in-plan (from T1) | ⬜ pending |
| 08-09-T1 | 08-09 | 5 | MASK-01, MASK-02, MASK-05 | T-08-16, T-08-17 | Worker derivation PIL/numpy only (Qt-free); allocation sized from decoded image shape only | unit | `pytest tests/test_core/test_batch_runner.py -q` | ✅ existing (extended) | ⬜ pending |
| 08-09-T2 | 08-09 | 5 | MASK-01, MASK-02, MASK-05 | — | Post-batch restore under the suppression guard (no current-page desync); clean mode unchanged | unit+gui | `pytest tests/test_core/test_batch_runner.py -q` | ✅ existing (extended) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*File Exists: ✅ existing suite file · "new (TDD in-task)" = created by the task itself, behavior-first · "in-plan (from Tn)" = created by an earlier task of the same plan.*

---

## Wave 0 Requirements

- [x] Test stubs for the masker-seam call site (first real call-site tests — the vendored machinery is currently only import-tested) — **satisfied in-task by 08-03 Task 1** (tests/test_core/test_masker_machinery.py, TDD: behavior block precedes implementation)
- [x] Extension of the `_on_detection_finished` direct-drive harness (`tests/test_gui_detection_boxes.py:47-88` pattern) for the new constrained-mask build — **satisfied in-task by 08-07 Task 1** (extends the existing file; no stub needed)

*No separate Wave 0 exists: every new test file is created by the same task that implements the behavior (21/21 tasks carry `<automated>` verify with an in-reach test target). Existing infrastructure (pytest, pytest-qt, pinned interpreter) otherwise covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Border state colors legible on real artwork | MASK-03 | Visual judgment on real manga pages | Open a detected page; verify will-inpaint / gate-skipped / forced / never states are distinguishable at a glance |
| Paint-under-boxes gesture feel | MASK-06 | Modifier-gesture ergonomics | With Brush active, paint across a box; Alt+click select, Alt+drag move, double-click editor |
| Dilation radius visual adequacy | MASK-01 | Letter-edge coverage quality on real scans | Detect with radius 0 vs 2 vs 5; verify letter edges get covered without eating artwork |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (21/21; no MISSING references — each new test file is created by its own task)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has one)
- [x] Wave 0 covers all MISSING references (none remain — see Wave 0 section)
- [x] No watch-mode flags
- [x] Feedback latency < 120s (quick commands target single files; full suite ~2 min)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-approved at plan revision 1 (2026-08-15) — map populated from the 9 plan files (21 tasks); executor maintains the Status column during execution.

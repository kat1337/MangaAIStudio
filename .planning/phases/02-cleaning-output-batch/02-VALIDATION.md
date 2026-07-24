---
phase: 2
slug: cleaning-output-batch
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-23
approved: 2026-07-23
---

> **Wave 0 model (in-plan TDD).** This phase creates its test files via in-plan TDD: each plan's Task 1 is the RED test (the Wave 0 stub), and Task 2 is the GREEN implementation. Every implementation task has an automated verify that runs a test created by the preceding task in the same plan, and there are zero `<automated>MISSING</automated>` references. The "Wave 0 Requirements" checklist below maps to those Task-1 RED tests.

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-qt (`pytest.ini` `qt_api = pyside6`, verified Phase 1) |
| **Config file** | `pytest.ini` (markers `unit`/`gui`; `testpaths = tests`) |
| **Quick run command** | `pytest tests/test_core/ -x` (backend logic — image_io + batch_runner with fake adapters; no GUI, no models) |
| **Full suite command** | `pytest` (full suite incl. GUI smoke tests via pytest-qt) |
| **Estimated runtime** | ~15-25 seconds (quick); ~40-60 seconds (full) |
| **Fake-adapter pattern** | `tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama` (records calls, returns a PIL image, no torch/weights) — extend to FakeDetectionModel/FakeInpaintModel |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_core/ -x`
- **After every plan wave:** Run `pytest`
- **Before `/gsd-verify-work`:** Full suite must be green + manual smoke (open a real chapter folder, run Batch Detect+Clean, confirm `cleaned/` outputs visually)
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Task IDs are provisional (assigned by the planner). The map below reflects the requirement→test→command bindings the RESEARCH Validation Architecture derived; the planner will fill in the final `02-NN-PLAN.md` task numbers and waves.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 (mask persistence) | 1 | FLOW-03 (D-11) | T-02-04 / — | Mask `.copy()`-detached before crossing into `ImageFile.mask` (Pitfall 2) | gui | `pytest tests/test_gui_batch.py::test_mask_survives_navigation -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | FLOW-03 (D-11) | — | N/A | gui | `pytest tests/test_gui_batch.py::test_mask_persistence_uses_copy -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | FLOW-03 (D-11) | — | N/A | gui | `pytest tests/test_gui_batch.py::test_batch_detect_persists_masks -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 (batch runner) | 2 | FLOW-03 (D-03) | — | Empty-mask page copies original through (not skipped) | integration | `pytest tests/test_core/test_batch_runner.py::test_batch_clean_skips_empty_mask -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | FLOW-03 | — | N/A | integration | `pytest tests/test_core/test_batch_runner.py::test_batch_detect_and_clean -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | FLOW-03 (D-04) | T-02-02 | Per-page failure non-fatal; failed pages skipped+logged, batch continues, summary returned | integration | `pytest tests/test_core/test_batch_runner.py::test_per_page_failure_continues -x` | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 2 | FLOW-03 (D-09) | T-02-01 | Abort checked between pages only; stops cleanly after current page; no half-written output | integration | `pytest tests/test_core/test_batch_runner.py::test_abort_between_pages -x` | ❌ W0 | ⬜ pending |
| 02-02-05 | 02 | 2 | FLOW-03 (D-07) | T-02-03 | Output written to `cleaned/` subdir only; never to `source.parent` directly | integration | `pytest tests/test_core/test_batch_runner.py::test_output_to_cleaned_subdir -x` | ❌ W0 | ⬜ pending |
| 02-02-06 | 02 | 2 | FLOW-03 (D-10) | — | Progress emits per-page count + name ("Cleaning page 12/30 — name.jpg") | integration | `pytest tests/test_core/test_batch_runner.py::test_progress_per_page -x` | ❌ W0 | ⬜ pending |
| 02-02-07 | 02 | 2 | FLOW-03 (Pitfall 3) | — | Model loaded ONCE before the loop (not per-page) | integration | `pytest tests/test_core/test_batch_runner.py::test_model_loaded_once -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 (image_io) | 2 | PROJ-02 | — | PNG saved with compress_level=9, optimize=True | unit | `pytest tests/test_core/test_image_io.py::test_save_png_kwargs -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | PROJ-02 | — | JPG saved with quality=95, progressive=True | unit | `pytest tests/test_core/test_image_io.py::test_save_jpg_kwargs -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | PROJ-02 | — | Preserves original DPI/mode when output format matches | unit | `pytest tests/test_core/test_image_io.py::test_preserves_dpi_mode -x` | ❌ W0 | ⬜ pending |
| 02-03-04 | 03 | 2 | FLOW-03 (D-03) | — | Empty-mask/no-text page: `shutil.copy2` byte-exact passthrough | unit | `pytest tests/test_core/test_image_io.py::test_passthrough_copy2 -x` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 (UI wiring) | 3 | PROJ-02 | T-02-05 | Export Page writes the DISPLAYED canvas image (not a re-clean); save path via `getSaveFileName` | gui | `pytest tests/test_gui_batch.py::test_export_writes_displayed_image -x` | ❌ W0 | ⬜ pending |
| 02-04-02 | 04 | 3 | FLOW-03 (D-08) | — | Batch sets `_op_running`; detect/inpaint/batch actions disabled during run | gui | `pytest tests/test_gui_batch.py::test_batch_sets_op_running -x` | ❌ W0 | ⬜ pending |
| 02-04-03 | 04 | 3 | FLOW-03 (Pitfall 7) | — | `_op_running` cleared on batch finish/abort/error (no stuck-disabled state) | gui | `pytest tests/test_gui_batch.py::test_op_running_cleared_after_batch -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> These map to each plan's Task 1 (RED test) under the in-plan TDD model — see the frontmatter note.

- [x] `tests/test_core/test_image_io.py` — stubs for PROJ-02 (PNG/JPG kwargs, DPI/mode) + FLOW-03 D-03 (copy2 passthrough) → **02-01-PLAN.md Task 1**
- [x] `tests/test_core/test_batch_runner.py` — stubs for FLOW-03 batch loop with fake adapters (FakeCTD/FakeLama recording calls), abort-between-pages, per-page failure, model-loaded-once, output-to-cleaned/ → **02-03-PLAN.md Task 1**
- [x] `tests/test_gui_batch.py` — stubs for PROJ-02 Export action + FLOW-03 GUI wiring (mask persistence, `_op_running` gate, progress signals) via pytest-qt → **02-02-PLAN.md Task 1** + **02-04-PLAN.md Task 1**
- [x] Fake-adapter fixtures — extend `FakeSimpleLama` pattern to `FakeDetectionModel`/`FakeInpaintModel` (same `detect`/`inpaint` signatures); shared fixture in `tests/test_core/conftest.py` → **02-03-PLAN.md Task 1**
- [x] Framework install: none needed (pytest/pytest-qt/pytest-mock declared + present from Phase 1)

*Existing infrastructure covers framework + fixtures; test files + fake adapters are created via each plan's Task 1 (RED).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Batch Detect+Clean on a real chapter produces visually-clean `cleaned/` outputs | FLOW-03 | Requires real CTD + LaMa model weights (~280MB) and a real manga chapter; model-dependent visual quality is not unit-testable | Open a real chapter folder; run Tools → Batch Detect+Clean; open `cleaned/`; confirm each page has text removed + artwork restored; confirm no-text pages are byte-identical to source |
| Cancel button halts a long batch and already-written pages persist | FLOW-03 (D-09) | Timing-dependent on real model load; needs a multi-page run long enough to interrupt mid-batch | Start a Batch Detect+Clean on a 5+ page folder; click Cancel during page 2-3; confirm the run stops after the current page and `cleaned/` contains the pages completed before cancel |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (via in-plan TDD Task 1 per plan)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-23 (post plan-checker `VERIFICATION PASSED`; companion-artifact bookkeeping reconciled)

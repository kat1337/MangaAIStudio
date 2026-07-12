---
phase: 1
slug: cleaning-workspace
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-12
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

Derived from the Validation Architecture section of `01-RESEARCH.md` (lines 873–914) and the threat patterns in the Security Domain section (lines 916–940).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (with pytest-qt for GUI tests) |
| **Config file** | pytest.ini (to be created in Wave 0) |
| **Quick run command** | `pytest tests/test_core/ -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~30–60 seconds (backend logic tests quick; GUI smoke tests slower) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_core/ -x` (backend logic tests, no GUI)
- **After every plan wave:** Run `pytest` (full suite including GUI smoke tests)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Task IDs are provisional — they follow the planned 6-plan structure (`01-0{1..6}-PLAN.md`). Task numbers within each plan will be filled in by the executor once PLAN.md task IDs are known. Threat refs cross-reference the Security Domain table in `01-RESEARCH.md` (line 930).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-* | 01 | 1 | (scaffolding) | T-1 path traversal / model tampering | Config & model adapter base classes validate paths and model checksums on load | unit | `pytest tests/test_core/ -x` | ❌ W0 | ⬜ pending |
| 01-02-* | 02 | 1 | CLEAN-01, FLOW-01 | T-1 path traversal / DoS via large image | Canvas enforces image size limits; file paths validated via Path.resolve() | integration/smoke | `pytest tests/test_gui_canvas.py::test_load_image -x` | ❌ W0 | ⬜ pending |
| 01-02-* | 02 | 1 | CLEAN-01, FLOW-01 | T-1 path traversal | Folder open validates each path; sidebar shows only resolved paths | integration/smoke | `pytest tests/test_gui_file_table.py::test_load_folder -x` | ❌ W0 | ⬜ pending |
| 01-02-* | 02 | 1 | FLOW-01 | — | Page navigation via sidebar selects correct page | integration/smoke | `pytest tests/test_gui_file_table.py::test_navigation -x` | ❌ W0 | ⬜ pending |
| 01-03-* | 03 | 2 | CLEAN-02 | T-2 model weight tampering | CTD adapter verifies model checksums on load; uses known-good model paths | integration | `pytest tests/test_detection.py::test_ctd_detect -x` | ❌ W0 | ⬜ pending |
| 01-04-* | 04 | 2 | CLEAN-03 | — | Brush paint produces correct mask deltas | integration | `pytest tests/test_mask_editor.py::test_brush_paint -x` | ❌ W0 | ⬜ pending |
| 01-04-* | 04 | 2 | CLEAN-04 | — | Rectangle tool fills expected region | integration | `pytest tests/test_mask_editor.py::test_rect_paint -x` | ❌ W0 | ⬜ pending |
| 01-04-* | 04 | 2 | CLEAN-05 | — | Eraser removes mask within bounds | integration | `pytest tests/test_mask_editor.py::test_eraser -x` | ❌ W0 | ⬜ pending |
| 01-05-* | 05 | 2 | CLEAN-06 | T-2 model weight tampering | LaMa inpainting runs on mask; model path validated | integration | `pytest tests/test_inpainting.py::test_lama_inpaint -x` | ❌ W0 | ⬜ pending |
| 01-06-* | 06 | 3 | FLOW-02 | — | Undo restores prior mask state | integration | `pytest tests/test_history.py::test_mask_undo -x` | ❌ W0 | ⬜ pending |
| 01-06-* | 06 | 3 | FLOW-02 | — | Redo replays a previously undone mask op | integration | `pytest tests/test_history.py::test_mask_redo -x` | ❌ W0 | ⬜ pending |
| 01-06-* | 06 | 3 | FLOW-02 | — | Undo restores prior image (inpainting) state | integration | `pytest tests/test_history.py::test_image_undo -x` | ❌ W0 | ⬜ pending |
| 01-06-* | 06 | 3 | FLOW-02 | — | Redo replays a previously undone image op | integration | `pytest tests/test_history.py::test_image_redo -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test files are missing on the empty codebase — Wave 0 (the first plan's scaffolding task, 01-01) must establish the test infrastructure before downstream plans can sample feedback:

- [ ] `tests/conftest.py` — shared fixtures (sample images, test config, mock models)
- [ ] `tests/test_core/` — core backend tests (model adapters, config loading)
- [ ] `tests/test_detection/` — CTD detection tests
- [ ] `tests/test_inpainting/` — LaMa inpainting tests
- [ ] `tests/test_mask_editor/` — mask editing tests
- [ ] `tests/test_gui_canvas.py` — canvas smoke tests
- [ ] `tests/test_gui_file_table.py` — file table tests
- [ ] `tests/test_history.py` — undo/redo tests
- [ ] `pytest.ini` — pytest configuration (pytest-qt plugin, test paths)
- [ ] Framework install: `pip install pytest pytest-qt pytest-mock` — required for GUI testing

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pan/zoom canvas feels responsive at 100%–800% zoom | CLEAN-01 | Perceptual latency, not a binary state | Open a 2000×3000 page; ctrl+scroll to zoom 100%→800%→100%; drag to pan; confirm no perceptible stutter |
| Brush stroke follows cursor smoothly across mask overlay | CLEAN-03 | Continuous-input feel, anti-aliasing visual | Select brush tool, set size 30px, paint a curve across the page; confirm stroke tracks cursor with no gaps |
| Undo/redo keyboard shortcuts (Ctrl+Z / Ctrl+Shift+Z) feel immediate | FLOW-02 | Interaction latency threshold | Paint 3 strokes, press Ctrl+Z three times, Ctrl+Shift+Z three times; confirm each step applies within one frame |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

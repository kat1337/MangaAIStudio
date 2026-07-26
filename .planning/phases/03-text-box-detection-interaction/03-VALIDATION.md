---
phase: 3
slug: text-box-detection-interaction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-25
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from `03-RESEARCH.md` §"Validation Architecture". The per-task map
> (§Per-Task Verification Map) is populated once plans exist; the test
> infrastructure and Wave 0 requirements below are fixed from the existing
> repo (pytest + pytest-qt + PySide6, same as Phases 1/2).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-qt (PySide6 `qt_api = pyside6`, per `pytest.ini`) |
| **Config file** | `pytest.ini` (existing — `testpaths = tests`, markers `unit` / `gui`) |
| **Quick run command** | `python -m pytest tests/ -m unit -q` (headless, no Qt display needed) |
| **Full suite command** | `python -m pytest tests/ -q` (includes `gui` markers — needs a display / offscreen platform) |
| **Estimated runtime** | ~30–60 seconds (Phase 2's suite was ~15–40s; Phase 3 adds BoxItem + HistoryManager tests) |

**Display note:** GUI tests (`-m gui`) need `QT_QPA_PLATFORM=offscreen` on headless CI or a real display locally — same as Phase 1/2's `test_gui_canvas.py` / `test_gui_batch.py`.

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -m unit -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Populated by the planner (each plan's tasks get a row). Requirements TEXT-01
> (detection → boxes) and TEXT-03 (select/move/resize/delete) must each map to
> at least one automated test. The Researcher's Validation Architecture names
> these target test files (carry them into the plan tasks):

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _(planner fills)_ | _ | _ | TEXT-01 | — | detection result must not execute untrusted box data | unit | `python -m pytest tests/test_core/<new>_test.py -q` | ❌ W0 | ⬜ pending |
| _(planner fills)_ | _ | _ | TEXT-03 | — | box edits are undoable (BOXES stack) | unit + gui | `python -m pytest tests/test_history.py tests/test_gui_<box>.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

The phase introduces new test files. Wave 0 (first plan, first wave) must create stubs so the sampling loop has targets:

- [ ] `tests/test_core/test_structures.py` — stubs for the vendored `Box` model (REQ coverage: TEXT-01 box-object creation; `Box.as_tuple_xywh` → `QRectF` mapping)
- [ ] `tests/test_core/test_masker_vendor.py` — stubs for the vendored `masker.py` (std-deviation seam; the `output_structures` import is stubbed per RESEARCH Pitfall 1)
- [ ] `tests/test_core/test_box_model.py` — stubs for the origin-tagged `PageBox` wrapper (D-03 detected/user; D-15 seam `(Box, mask, std_dev)`)
- [ ] `tests/test_core/test_history_boxes.py` — stubs for the 3rd BOXES stack + unified-timeline pop (D-10/D-11; RESEARCH Pitfall 4 — timestamp widening)
- [ ] `tests/test_gui_boxes.py` — stubs for BoxItem selection/move/resize/delete/create (pytest-qt, `-m gui`); mirrors `tests/test_gui_canvas.py`
- [ ] `tests/test_box_persistence.py` — stubs for per-page box persistence (mirrors Phase 2 T-02-04 mask-persistence seam)

*Wave 0 = the first plan of the phase creates these stubs alongside the vendored/model code so subsequent tasks always have a target.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Detected-vs-user box color distinction reads correctly on real artwork | TEXT-03 (D-09) | Color perception on varied manga artwork is subjective; automated tests assert hex values, not legibility | Load a chapter page, run Detect (mode on), confirm green boxes appear; Alt+drag to create a user box, confirm amber; verify both stay distinguishable over dark + light artwork regions |
| Corner-handle resize grab feel at 100% / 200% Windows scaling | TEXT-03 (D-06) | Hit-target ergonomics + `ItemIgnoresTransformations` behavior across DPI is tactile | At 100% and 200% display scaling, select a box, drag each of the 4 corner handles, confirm the grab target is reachable and resize is fluent |
| Unified Ctrl+Z pop order feels right across mask/image/box ops | TEXT-03 (D-11) | Undo-ordering expectations are subjective; automated tests assert the timeline, not the feel | Do a mask paint → a box move → an inpaint, then Ctrl+Z three times; confirm the ops reverse in chronological order and the status-bar "Undo: {op}" message names each correctly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (set to `approved YYYY-MM-DD` once the planner fills the per-task map and Wave 0 is confirmed)

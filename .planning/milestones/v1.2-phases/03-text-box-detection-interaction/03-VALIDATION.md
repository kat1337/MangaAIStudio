---
phase: 3
slug: text-box-detection-interaction
status: draft
nyquist_compliant: true
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

Populated from the 5 plans' `<verify><automated>` blocks (gsd-plan-checker W-01 fix). Requirements TEXT-01 (detection → boxes) and TEXT-03 (select/move/resize/delete) each map to multiple automated tests.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 03-01 | 1 | TEXT-01 | T-03-06 (V5) | vendored code imports cleanly; ost-import guarded (Pitfall 1) | unit | `python -m pytest tests/test_core/test_structures.py tests/test_core/test_masker_vendor.py -q` | ❌ W0 | ⬜ pending |
| 03-01-T2 | 03-01 | 1 | TEXT-01 | T-03-06 (V5) | textblock_to_box coerces model xyxy to ints (untrusted boundary) | unit | `python -m pytest tests/test_core/test_box_model.py -q` | ❌ W0 | ⬜ pending |
| 03-02-T1 | 03-02 | 1 | TEXT-03 | — | BOXES stack + unified-timeline pop; Phase 1 test_history.py guards widened to (stamp, value) (Pitfall 4) | unit | `python -m pytest tests/test_history.py tests/test_core/test_history_boxes.py -q` | ❌ W0 | ⬜ pending |
| 03-03-T1 | 03-03 | 2 | TEXT-03 | — | BoxItem + CornerHandle render + selection state (D-05/D-06/D-09) | gui | `python -m pytest tests/test_gui_boxes.py -q -m gui` | ❌ W0 | ⬜ pending |
| 03-03-T2 | 03-03 | 2 | TEXT-03 | — | box layer hit-test dispatch + create/move/resize/delete (D-07/D-08/D-12/D-13) | gui | `python -m pytest tests/test_gui_boxes.py -q -m gui` | ❌ (inline TDD Wave 2) | ⬜ pending |
| 03-04-T1 | 03-04 | 3 | TEXT-01 | T-03-06 (V5) | `_on_detection_finished` builds boxes from `result["blocks"]`; xyxy bounds-clamped against image rect | gui | `python -m pytest tests/test_gui_detection_boxes.py -q -m gui` | ❌ (inline TDD Wave 3) | ⬜ pending |
| 03-05-T1 | 03-05 | 4 | TEXT-01, TEXT-03 | — | per-page box persistence, `.copy()` both boundaries (Phase 2 D-11 mirror) | gui | `python -m pytest tests/test_box_persistence.py -q -m gui` | ❌ (inline TDD Wave 4) | ⬜ pending |
| 03-05-T2 | 03-05 | 4 | TEXT-01, TEXT-03 | — | Surface 13 undo collapse; Alt+Z removed; orphaned strings at main_window.py:1104 + :1342 fixed | gui | `python -m pytest tests/test_box_persistence.py -q -m gui` | ✅ (existing) | ⬜ pending |

**File-exists legend:** ❌ W0 = Wave 0 stub created in Wave 1; ❌ (inline TDD) = created via TDD in the task's own wave (deviation from "all stubs in Wave 0" — acceptable: Nyquist sampling continuity is met because every impl task carries `<automated>` verify).

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

The phase introduces new test files. Wave 0 (Wave 1 plans 03-01 + 03-02) creates the headless-core stubs so the sampling loop has targets from the start; the 3 GUI test files are created inline via TDD in their own waves (deviation noted in the per-task map — sampling continuity still holds).

- [x] `tests/test_core/test_structures.py` — stubs for the vendored `Box` model (REQ coverage: TEXT-01 box-object creation; `Box.as_tuple_xywh` → `QRectF` mapping) — Wave 1 / plan 03-01 Task 1
- [x] `tests/test_core/test_masker_vendor.py` — stubs for the vendored `masker.py` (std-deviation seam; the `output_structures` import is stubbed per RESEARCH Pitfall 1) — Wave 1 / plan 03-01 Task 1
- [x] `tests/test_core/test_box_model.py` — stubs for the origin-tagged `PageBox` wrapper (D-03 detected/user; D-15 seam `(Box, mask, std_dev)`) — Wave 1 / plan 03-01 Task 2
- [x] `tests/test_core/test_history_boxes.py` — stubs for the 3rd BOXES stack + unified-timeline pop (D-10/D-11; RESEARCH Pitfall 4 — timestamp widening) — Wave 1 / plan 03-02 Task 1
- [ ] `tests/test_gui_boxes.py` — stubs for BoxItem selection/move/resize/delete/create (pytest-qt, `-m gui`); mirrors `tests/test_gui_canvas.py` — created inline via TDD in Wave 2 / plan 03-03
- [ ] `tests/test_gui_detection_boxes.py` — detection → boxes GUI test — created inline via TDD in Wave 3 / plan 03-04
- [ ] `tests/test_box_persistence.py` — stubs for per-page box persistence (mirrors Phase 2 T-02-04 mask-persistence seam) — created inline via TDD in Wave 4 / plan 03-05

*Headless core stubs land in Wave 1 (the foundation plans 03-01/03-02); the 3 GUI test files land inline via TDD in the waves that build the GUI they test. The Phase 1 `test_history.py` guard update (Pitfall 4) is a Wave 1 task in plan 03-02 — an existing-file edit, not a new stub.*

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

**Approval:** approved 2026-07-27 (per-task map populated from plans 03-01..03-05 `<verify>` blocks after gsd-plan-checker verification PASSED; Wave 0 headless-core stubs confirmed in Wave 1 plans)

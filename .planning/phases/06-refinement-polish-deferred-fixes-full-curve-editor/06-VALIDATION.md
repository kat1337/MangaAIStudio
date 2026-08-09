---
phase: 6
slug: refinement-polish-deferred-fixes-full-curve-editor
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-09
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-qt (PySide6 6.10.1); baseline 552 passed / 0 failed at Phase 5 close |
| **Config file** | none — standard pytest.ini-less layout; GUI tests marked `@pytest.mark.gui` |
| **Quick run command** | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_curves_dialog.py -x -q` |
| **Full suite command** | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/<touched> -x -q`
- **After every plan wave:** Run `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | PROJ-04 (curves math) | T-06-01 / — | LUT values clipped 0..255 uint8; no NaN/garbage entries | unit | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_image_ops.py -x` | ✅ / ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | PROJ-04 (composition) | T-06-01 / — | `.copy()` detach; validation errors | unit | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_image_ops.py -x` | ✅ / ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | PROJ-04 (dialog) | T-06-02 / — | endpoint clamps; point x-order preservation | GUI (pytest-qt) | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_curves_dialog.py -x` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | PROJ-04 (lifecycle) | T-06-03 / — | restore-before-Apply ordering; ONE undo entry | GUI e2e | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_curves_dialog.py -x` | ❌ W0 | ⬜ pending |
| TBD | 03 | 1 | D-09 | — | empty-state trio hidden after numpy display path | GUI regression | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_project.py tests/test_gui_canvas.py -x` | ✅ / ❌ W0 | ⬜ pending |
| TBD | 03 | 1 | D-10 | — | active toolbar button checked, others unchecked | GUI regression | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_crop_tool.py tests/test_gui_tools.py -x` | ✅ / ❌ W0 | ⬜ pending |
| TBD | 03 | 1 | D-11 | — | hint copy lacks "Ctrl+O" | unit/regression | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_canvas.py -x` | ✅ / ❌ W0 | ⬜ pending |
| TBD | 03 | 1 | D-12 | — | dialog font 14px | GUI regression | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_image_dialogs.py tests/test_gui_curves_dialog.py -x` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_gui_curves_dialog.py` — NEW: dialog contract + e2e lifecycle tests (Levels tests migrate from `test_gui_image_dialogs.py`; `_fake_exec` monkeypatch shape at :218-226 is the template)
- [ ] `tests/test_core/test_image_ops.py` — EXTEND: `curve_lut` / `curves_page` unit tests
- [ ] `tests/test_gui_project.py` / `test_gui_canvas.py` — EXTEND: D-09 numpy-path regression (`_display_page_state` project-open path)
- [ ] `tests/test_gui_crop_tool.py` — EXTEND: D-10 checked-state regression (RED-gate; existing test at :227 asserts `defaultAction().data()`, not `isChecked()`)
- [ ] No framework install needed — pytest/pytest-qt already in suite

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Curve-drag feel and live preview responsiveness | PROJ-04 | Visual/kinesthetic — automated tests cannot judge drag ergonomics | Open Curves dialog, drag points, observe smooth preview updates |
| Toolbar active-tool highlight visual | D-10 | Visual gate | Press V/B/R/L/E/G shortcuts, confirm highlight follows active tool |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

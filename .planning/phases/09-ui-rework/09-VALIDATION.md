---
phase: 9
slug: ui-rework
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-21
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pinned interpreter: `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`) |
| **Config file** | `pytest.ini` / `pyproject.toml` (repo root) |
| **Quick run command** | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/<changed-file>.py -x -q` |
| **Full suite command** | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` |
| **Estimated runtime** | ~60–120 seconds full suite (GUI tests via pytest-qt) |

---

## Sampling Rate

- **After every task commit:** Run the quick command scoped to the task's test file(s)
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (seeded — filled by validate-phase §6 after plans exist) | | | UI-01..UI-05 | — | N/A | GUI/unit | `python -m pytest tests/test_gui_*.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_gui_side_panel.py` — stubs for the collapsible-section panel (UI-01/UI-02/UI-04)
- [ ] `tests/test_gui_tools_strip.py` — stubs for the vertical tools strip (UI-03)
- [ ] `tests/test_gui_edit_section.py` — stubs for the Edit section (UI-05)

*Exact stub set finalized by the planner per plan files_modified.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Icon legibility at strip size on dark QSS | UI-03 | Visual judgment | Open app, inspect the 8 strip buttons at 100% zoom |
| Collapse/expand feel + persistence across restart | UI-01 | Interaction feel + QSettings persistence | Toggle sections, restart app, verify states restored |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

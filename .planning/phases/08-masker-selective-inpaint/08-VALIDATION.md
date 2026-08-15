---
phase: 8
slug: masker-selective-inpaint
status: draft
nyquist_compliant: false
wave_0_complete: false
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

---

## Sampling Rate

- **After every task commit:** Run the quick command on the touched test files
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~120 seconds (full suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | MASK-01..06 | — | N/A (offline desktop app; no untrusted input surfaces beyond image files) | TBD at planning | `pinned-python -m pytest …` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Test stubs for the masker-seam call site (first real call-site tests — the vendored machinery is currently only import-tested)
- [ ] Extension of the `_on_detection_finished` direct-drive harness (`tests/test_gui_detection_boxes.py:47-88` pattern) for the new constrained-mask build

*Existing infrastructure (pytest, pytest-qt, pinned interpreter) otherwise covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Border state colors legible on real artwork | MASK-03 | Visual judgment on real manga pages | Open a detected page; verify will-inpaint / gate-skipped / forced / never states are distinguishable at a glance |
| Paint-under-boxes gesture feel | MASK-06 | Modifier-gesture ergonomics | With Brush active, paint across a box; Alt+click select, Alt+drag move, double-click editor |
| Dilation radius visual adequacy | MASK-01 | Letter-edge coverage quality on real scans | Detect with radius 0 vs 2 vs 5; verify letter edges get covered without eating artwork |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

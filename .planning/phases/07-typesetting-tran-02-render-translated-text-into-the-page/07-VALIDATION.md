---
phase: 7
slug: typesetting-tran-02-render-translated-text-into-the-page
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-10
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest tests/test_core -q` |
| **Full suite command** | `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest -q` |
| **Estimated runtime** | ~60 seconds (baseline 552 tests at Phase 5 close) |

---

## Sampling Rate

- **After every task commit:** Run `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest tests/test_core -q`
- **After every plan wave:** Run `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner during plan creation) | | | TRAN-02 | T-07-01 / — | Plain-text rendering only — no rich-text injection of untrusted OCR/translation text | unit | `pytest tests/test_core -q` | ✅ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_core/test_text_style.py` — stubs for TRAN-02 (style dataclass + serialization round-trip)
- [ ] `tests/test_core/test_text_renderer.py` — stubs for tategaki layout + bake compositing
- [ ] Existing infrastructure covers GUI interactions (pytest-qt) — see RESEARCH.md Validation Architecture

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-CJK-font tategaki visual correctness (upright glyphs, RTL columns, Latin rotation) | TRAN-02 (D-11) | Font rendering requires a real CJK font and visual inspection — no headless font setup | Open a page with `vertical=True` box; type Japanese; verify upright glyphs top-to-bottom, columns flow right-to-left |
| Bake output visual parity with canvas | TRAN-02 (D-01) | WYSIWYG check requires human eyes on artwork | Set styling, Ctrl+E-style bake export; open the `_typeset` sidecar and compare with canvas look |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

---
phase: 4
slug: ocr-recognition-text-editing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-05
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `04-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (already in dev env from Phases 1-3) |
| **Config file** | `pyproject.toml` (or `pytest.ini` — confirm at Wave 0) |
| **Quick run command** | `python -m pytest -x -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~15-40 seconds (OCR model NOT loaded in unit tests; integration tests gate on model availability) |

> **Note:** manga-ocr/transformers is already installed in the dev env (verified in RESEARCH.md). OCR-dependent tests must skip gracefully when the model is not cached (`@pytest.mark.skipif(not _model_available(), reason="manga-ocr not cached")`) — do not force a ~450MB download in CI.

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest -x -q`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

> Filled by the planner/executor as PLAN.md tasks are created. Each task row ties a task ID to its requirement, threat reference, secure behavior, test type, automated command, and existence status.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _to be filled from PLAN.md tasks_ | | | | | | | | | |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Per RESEARCH.md Pitfalls 1 & 8, the two load-bearing persistence gaps (`canvas.boxes_snapshot()` dropping new fields; `TextBlock` payload aliasing across snapshots) should get **early regression tests** so the rest of the phase can rely on the seam. Other Wave 0 stubs:

- [ ] `tests/test_box_snapshot_fields.py` — regression: `boxes_snapshot()` round-trips `edited`, `bubble_no`, `manual_override`, `payload.text`, `payload.translation` (catches Pitfall 1 before feature work layers on top).
- [ ] `tests/test_payload_aliasing.py` — regression: committing a BOXES snapshot does NOT alias the `payload` TextBlock (catches Pitfall 8).
- [ ] `tests/test_reading_order.py` — stubs for the XY-Cut column-bucketing + per-column top-to-bottom sort (RTL column-order reversal for manga, LTR for manhwa).
- [ ] `tests/test_translation_parser.py` — stubs for `[N]: text` / `[SFX -N]: *text*` parsing + bubble-number matching + unmatched-number reporting.
- [ ] `tests/test_torch_ocr_model.py` — stubs for `TorchOCRModel` (numpy→PIL conversion, singleton load, recognize→str); gate on model availability.
- [ ] `tests/conftest.py` — extend with `_model_available()` helper + shared fixtures (existing from Phases 1-3).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Inline editor overlay appears on box double-click, positioned/sized on the box rect; Enter/click-away commits, Esc cancels | TEXT-04 | Qt transient-widget geometry + event dispatch is GUI-behavioral | 1. Open a page with boxes. 2. Double-click a box. 3. Confirm QTextEdit overlay appears on the box. 4. Type, Enter → text persists; reopen → shows edited text. 5. Repeat, Esc → no change. |
| Translucent text overlay (white text + dark outline) readable over varied artwork, art visible underneath | TEXT-04 / TEXT-05 | Visual legibility on real manga artwork | 1. OCR several boxes. 2. Toggle Text Overlay on. 3. Confirm white+outline text over art, art visible beneath. 4. Zoom in/out — text scales legibly. |
| Vertical-metadata toggle preserves `payload.vertical` without changing editor mode (v1 fallback) | TEXT-02 | Fallback per RESEARCH: vertical editing not feasible in v1 | 1. OCR a vertical-manga box. 2. Confirm `payload.vertical=True` in the box model (sidebar shows flag) while the editor stays horizontal. |
| "OCR All Boxes on Page" (Ctrl+R) progress + status-bar feedback; skips edited boxes with confirm | TEXT-02 | Worker-thread GUI feedback + modal confirm | 1. Page with mixed empty/edited boxes. 2. Ctrl+R. 3. Progress in status bar; empty boxes fill; edited boxes trigger confirm dialog. |

*Automated tests cover: reading-order algorithm, parser regex/matching, OCR adapter shape, snapshot persistence, undo entries. GUI/visual behaviors above are manual.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

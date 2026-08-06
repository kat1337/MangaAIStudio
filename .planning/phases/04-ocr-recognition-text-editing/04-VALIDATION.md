---
phase: 4
slug: ocr-recognition-text-editing
status: approved
nyquist_compliant: true
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
| 4-01-T1 | 01 | 1 | TEXT-04/05 | T-4-01 | PageBox.copy() detaches payload (no undo aliasing); set_recognized_text_edited centralizes the payload-None guard | unit | `python -m pytest tests/test_core/test_box_model.py -x -q` | ❌ W0 | ⬜ pending |
| 4-01-T2 | 01 | 1 | TEXT-04/05 | T-4-02 | boxes_snapshot() round-trips edited/bubble_no/manual_override (no silent edit loss) | unit | `python -m pytest tests/test_box_snapshot_fields.py tests/test_payload_aliasing.py tests/test_core/test_history_boxes.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-T1 | 02 | 1 | TEXT-05 | T-4-03 | parser validates `[N]:` format; rejects malformed input without crashing | unit | `python -m pytest tests/test_core/test_translation_parser.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-T2 | 02 | 1 | TEXT-05 | T-4-04 | reading_order preserves manual overrides on re-auto (no silent override) | unit | `python -m pytest tests/test_core/test_reading_order.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-T1 | 03 | 1 | TEXT-02 | T-4-05 | MangaOcr singleton load-once; no repeated model fetch | unit | `python -c "from panelcleaner.ocr.ocr_mangaocr import MangaOcr; assert MangaOcr._instance is None; print('ok')"` | ❌ W0 | ⬜ pending |
| 4-03-T2 | 03 | 1 | TEXT-02 | T-4-06 | TorchOCRModel numpy→PIL→str; skips gracefully if model not cached | unit | `python -m pytest tests/test_core/test_torch_ocr_model.py tests/test_core/test_adapters.py -x -q` | ❌ W0 | ⬜ pending |
| 4-04-T1 | 04 | 2 | TEXT-04/05 | T-4-07 | text overlay z=120/badge z=140 — no visual collision with handles | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "text_overlay or badge or current_focus"` | ✅ | ⬜ pending |
| 4-04-T2 | 04 | 2 | TEXT-04/05 | T-4-08 | Toggle Text Overlay (T) independent of M/Shift+M; Inspector commits via set_recognized_text_edited | gui | `python -m pytest tests/test_gui_boxes.py tests/test_gui_canvas.py -x -q` | ✅ | ⬜ pending |
| 4-05-T1 | 05 | 3 | TEXT-04 | T-4-09 | inline editor recognized-focus commit sets edited=True via set_recognized_text_edited | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "inline_editor"` | ✅ | ⬜ pending |
| 4-05-T2 | 05 | 3 | TEXT-04 | T-4-10 | canvas mousePressEvent guard checks inline-editor-active FIRST (no focus-drop DoS) | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "double_click or inline or commit_on_click_away or esc_cancel"` | ✅ | ⬜ pending |
| 4-06-T1 | 06 | 4 | TEXT-02 | T-4-11/12 | re-OCR confirms on edited=True (D-04); Worker+_op_running prevents concurrent heavy model calls | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "ocr or reocr"` | ✅ | ⬜ pending |
| 4-06-T2 | 06 | 4 | TEXT-02 | T-4-13/14 | auto-OCR on _commit_create (D-01); Ctrl+R OCR All; CR-11 model-path cache-check | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "text_menu or auto_ocr or ctrl_r"` | ✅ | ⬜ pending |
| 4-07-T1 | 07 | 5 | TEXT-05 | T-4-15 | LoadTranslationsDialog parser-apply reports unmatched numbers (no silent drop) | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "load_translations or parser_apply"` | ✅ | ⬜ pending |
| 4-07-T2 | 07 | 5 | TEXT-05 | T-4-16/17 | Auto-Number preserve-manual; page-global numbering (panels ignored) | gui | `python -m pytest tests/test_gui_boxes.py -x -q -k "auto_number or reading_order_apply or preserve_manual"` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*File Exists: ❌ W0 = created in Wave 0 (Plan 01/02/03); ✅ = extends existing `tests/test_gui_boxes.py` / `tests/test_gui_canvas.py`*

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (14/14 tasks verified above; Wave 1 plans create their test files in Wave 0)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has a targeted pytest run)
- [x] Wave 0 covers all MISSING references (Plan 01/02/03 create `test_box_model`/`test_box_snapshot_fields`/`test_payload_aliasing`/`test_history_boxes`/`test_translation_parser`/`test_reading_order`/`test_torch_ocr_model`/`test_adapters` in Wave 1 before later waves consume them)
- [x] No watch-mode flags (all verify commands are one-shot `-x -q` runs)
- [x] Feedback latency < 30s (targeted `-k` filtered pytest runs; no OCR model load in unit tests)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-05

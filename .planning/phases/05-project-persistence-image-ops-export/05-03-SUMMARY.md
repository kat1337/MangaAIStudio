---
phase: 05-project-persistence-image-ops-export
plan: 03
subsystem: core
tags: [ocr-export, json-contract, batch, worker-contract, wave-1]
requires: [plan 03-01 (PageBox/TextBlock state), plan 02-03 (batch loop contract)]
provides:
  - "manga_ai_studio/core/ocr_export.py — headless _ocr.json exporter for plan 05-08 Worker dispatch"
  - "D-19 published JSON shape pinned under test (downstream typesetting contract)"
affects: [plan 05-08 (Batch Export OCR JSON GUI), downstream typesetting tools]
tech-stack:
  added: [stdlib only (json, os, pathlib, dataclasses) + loguru; zero new deps]
  patterns:
    - "image_io.py pure-module template (dependency contract docstring, validate-before-work)"
    - "batch_runner.py loop shape (abort at loop top only, per-page isolation, {ok,failed,total})"
    - "lazy function-body import of worker_thread.Abort (module-top graph stays Qt-free, exception identity preserved)"
key-files:
  created:
    - manga_ai_studio/core/ocr_export.py
    - tests/test_core/test_ocr_export.py
    - .planning/phases/05-project-persistence-image-ops-export/deferred-items.md
  modified: []
decisions:
  - "ExportPage dataclass (path/boxes/img_w/img_h/geometry_altered) chosen as the batch input shape — model-free projection so the exporter stays pure and 05-08 can build it from boxes_snapshot() + canvas dims"
  - "Atomic write via temp file + os.replace (same directory) so a crash never leaves a half-written _ocr.json"
  - "Abort lazy-imported inside batch_export_ocr (function body) — the plan's recommended option over a local Abort subclass"
  - "img_w/img_h strict isinstance(int) validation raising ValueError (T-05-02); no silent float/str coercion"
status: complete
estimate:
  tokens: 18000
  tasks: 2
actuals:
  tokens: 7142          # chars/4 over the realized 2-commit diff (28569 chars)
  tasks: 2              # tasks completed
  commits: 2            # task commits; +1 final docs commit
metrics:
  duration: "~45 min"
  completed_date: "2026-08-08"
---

# Phase 05 Plan 03: Headless _ocr.json Exporter (D-19/D-20/D-22) Summary

Wave 1 of PROJ-03: `core/ocr_export.py` pins the D-19 published `_ocr.json`
shape (mokuro vocabulary + our fields + per-line `lines[]`), the D-20
`\n`-split onto `TextBlock.lines` polygons, the D-22 state-dependent output
location (pristine → source sidecar; altered → `cleaned/`), and the
interruptible `batch_export_ocr(pages, progress_callback=None,
abort_flag=None) -> {"ok", "failed", "total"}` loop ready for Worker
dispatch in plan 05-08. Pure projection of `PageBox`/`TextBlock` state —
no models, no Qt imports at module top.

## Key Deliverables

- **`build_page_ocr_json`** — the D-19 dict: `version`/"1",
  `img_width`/`img_height` (int-validated, ValueError on non-int),
  `blocks[]` with `box`/`vertical`/`text`/`translation`/`bubble_no`/`origin`/
  `lines[]`; per-line `{"box": line_box(quad), "text": segment}`; payload-None
  boxes export text `""` + `lines []`; zero-box pages export `"blocks": []`;
  `PageBox.mask`/`std_dev` NEVER exported (D-15 seam).
- **`split_text_onto_lines`** — D-20: whole-text `\n`-split mapped onto
  polygons (line N gets segment N; unmatched polygons `""`; extra segments
  dropped); list-typed text joined first (defensive TextBlock storage).
- **`write_page_ocr_json`** — D-22 target dir + `path_override` (Save As),
  `mkdir(parents=True, exist_ok=True)`, UTF-8 encode, atomic temp+`os.replace`.
- **`batch_export_ocr`** — batch_runner-mirror: abort at loop top ONLY,
  per-page progress `(percent, name)`, per-page try/except isolation (D-04),
  `{ok, failed, total}` summary; `Abort` lazy-imported inside the function
  (exact worker_thread identity preserved; Worker's `except Abort` routes
  cancel to `aborted`); T-05-05 logs only page stems.

## Verification

- `pytest tests/test_core/test_ocr_export.py`: **8 passed** (after both tasks)
- Full suite: **492 passed / 1 failed** — the sole failure is the pre-existing
  `test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`
  (off-by-one in Qt event simulation; untouched by this plan; plan 05-09 owns
  it — documented in `deferred-items.md`). Baseline at plan time was 462
  collected/461 passed/1 failed; the same pre-existing file.
- Acceptance: `OCR_JSON_VERSION == "1"` import check passes; `grep -c
  "def batch_export_ocr"` == 1; `grep -c "abort_flag"` == 4 (>= 2); module
  import graph loads no `manga_ai_studio.gui` module (the only PySide6 in
  the process comes transitively from vendored `panelcleaner/helpers.py`,
  pre-existing and identical for `box_model.py`).

## Deviations from Plan

None material — plan executed as written. Minor note: the plan's artifact
list said "6 test functions" while the task list enumerates 7; **8** tests
were written (one extra: `test_dumps_round_trip`, asserting
`page_ocr_json_dumps` round-trips identically and keeps Japanese unescaped —
a natural T-05-10 pin). No auto-fixes were required beyond two test-side
adjustments to match the signal-shaped `progress_callback.emit(...)` contract
(plain-function callbacks cannot be passed — the Worker contract requires an
`.emit()` object, same as conftest's `RecordingSignal`).

### Out-of-Scope Discoveries (logged, not fixed)

- `tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`
  fails (69,69,129,129 vs expected 70,70,130,130) — pre-existing, owned by
  plan 05-09. Logged to `deferred-items.md`.
- `tests/test_gui_boxes.py::test_run_ocr_selected_dispatches_worker_not_inline`
  failed once in the full suite but passes in isolation — test-ordering
  flake, same file, same owner. Logged to `deferred-items.md`.

## Decisions Made

1. **`ExportPage` dataclass** as the batch input shape (recommended option):
   keeps the exporter model-free; plan 05-08 builds it from
   `boxes_snapshot()` + canvas dims.
2. **Atomic temp+`os.replace`** for every `_ocr.json` write (same-directory
   temp file) — crash never leaves a half-written contract file.
3. **Strict `isinstance(img_w, int)` validation** raising ValueError —
   "int-coerce ... ValueError on non-int" read strictly (T-05-02 discipline;
   silent float truncation would export coordinates that lie about the page).
4. **Lazy function-body `Abort` import** — the plan's recommended option;
   module-top import graph stays free of our GUI modules.

## Known Stubs

None — all 10 planned functions implemented and under test; no TODOs,
placeholders, or empty-mock data in the created files (stub scan clean).

## Threat Flags

None — the module adds disk-write surface (`_ocr.json` writes + `cleaned/`
creation) which is exactly the surface the plan's threat model already
covers (T-05-09 loop bounds, T-05-10 ensure_ascii=False + UTF-8 + no
hand-rolled JSON, T-05-05 stem-only logging, T-05-SC zero new packages).

## Self-Check: PASSED

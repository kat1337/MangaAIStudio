---
phase: 03-text-box-detection-interaction
plan: 01
subsystem: core (data-model + vendored PanelCleaner slice)
tags: [vendoring, data-model, d-14, d-15, headless, tdd]
requires:
  - "panelcleaner.image_ops (Phase 1 vendored — pick_best_mask/border_std_deviation/color_std)"
  - "panelcleaner.config / .data / .ocr.supported_languages / .helpers (Phase 1 vendored)"
provides:
  - "panelcleaner.structures full surface (Box, BoxType, MaskFittingResults, MaskData, MaskerData, PageData)"
  - "panelcleaner.masker (mask_page + save_denoising_data — dead code, std-dev seam doc)"
  - "manga_ai_studio.core.box_model.PageBox (origin-tagged wrapper, D-15 seam open)"
  - "manga_ai_studio.core.box_model.textblock_to_box (V5 int-coercion boundary)"
  - "manga_ai_studio.core.box_model.DETECTED / USER (origin constants)"
  - "manga_ai_studio.core.image_file.ImageFile.boxes slot + has_boxes()"
affects:
  - "03-03 BoxItem (consumes PageBox + Box.as_tuple_xywh for QRectF)"
  - "03-04 detection seam (consumes textblock_to_box + DETECTED origin)"
  - "03-05 persistence (consumes ImageFile.boxes slot + has_boxes)"
  - "later selective-inpaint phase (consumes PageBox.mask/std_dev seam — D-15)"
tech-stack:
  added: []
  patterns:
    - "D-12 vendoring discipline (GPL v3 -> GPL v3, SPDX header, pcleaner. -> panelcleaner. rewrite)"
    - "ost-import try/except guard (Pitfall 1 — optional dep shim)"
    - "composition-over-subclassing for vendored @frozen Box (D-14 anti-pattern)"
    - "TYPE_CHECKING deferred import for forward-ref field annotation"
key-files:
  created:
    - panelcleaner/masker.py
    - manga_ai_studio/core/box_model.py
    - tests/test_core/test_structures.py
    - tests/test_core/test_masker_vendor.py
    - tests/test_core/test_box_model.py
  modified:
    - panelcleaner/structures.py
    - manga_ai_studio/core/image_file.py
decisions:
  - "Rewrote all 5 pcleaner. references in vendored structures.py to panelcleaner. (4 imports + 1 body ref to pcleaner.data at the visualize() font_path call) — the body ref is inside dead code in our context but D-12 discipline requires the qualified name match the vendored module so the file is self-consistent."
  - "Deferred PageBox import in image_file.py via TYPE_CHECKING (rather than the plan's suggested direct import) to keep the GUI layer's ImageFile construction cycle-safe at import time. The boxes field annotation is a forward-ref string under from __future__ import annotations, so no runtime import is needed."
  - "TDD per-task RED/GREEN split (4 commits total) rather than a single feat commit — both tasks were tdd=true."
metrics:
  duration: 10 min
  completed: 2026-07-28
  tasks: 2
  files: 7 (2 modified + 5 created)
  tests-added: 34 (22 Wave-0 unit + the foundation is purely additive)
status: complete
---

# Phase 03 Plan 01: Text-Box Data-Model Foundation (vendored structures + masker + PageBox) Summary

Laid the headless data-model foundation for Phase 3: vendored PanelCleaner's full `structures.py` + `masker.py` near-verbatim (D-14), created the `PageBox` origin-tagged wrapper with the D-15 selective-inpaint seam open (mask/std_dev default None), and extended `ImageFile` with a `boxes` slot mirroring Phase 2's `mask` slot. The `textblock_to_box` V5 input validator is the single coercion boundary that turns model-produced `TextBlock.xyxy` into a vendored `Box` with int coordinates.

## What Was Built

### Task 1 — Vendored structures.py (full) + ost-guarded masker.py (D-14)

- **`panelcleaner/structures.py`** (replaced 18-line stub → 764 lines): full upstream PanelCleaner `pcleaner/structures.py` near-verbatim with the D-12 vendoring header (SPDX GPL-3.0-or-later + "imports rewritten pcleaner. -> panelcleaner." note). Exposes the complete surface: `Box` (frozen, `as_tuple`/`as_tuple_xywh`/`__contains__`/`area`/`center`/`merge`/`overlaps`/`overlaps_center`/`pad`/`right_pad`/`scale`/`translate`), `BoxType` enum (BOX/EXTENDED_BOX/MERGED_EXT_BOX/REFERENCE_BOX), and the batch structs `PageData`, `MaskData`, `MaskerData`, `MaskFittingResults`, `InpainterData`, plus OCR/inpaint analytics. **Closes Pitfall 2**: `image_ops.pick_best_mask` constructs `st.MaskFittingResults(...)` at `image_ops.py:706,717` and the stub defined nothing.
- **`panelcleaner/masker.py`** (NEW, 178 lines): vendored near-verbatim from upstream `pcleaner/masker.py`. The `ost` import is guarded via `try/except ImportError` setting `ost = None` on failure (Pitfall 1) since `panelcleaner.output_structures` (batch GUI analytics) is deliberately NOT vendored. `mask_page` + `save_denoising_data` are dead code in our context; kept near-verbatim for the D-15 std-dev seam documentation + upstream diffability (RESEARCH Open Q 3).
- All 5 `pcleaner.` references in `structures.py` rewritten to `panelcleaner.` (4 imports + the `pcleaner.data` qualified name inside the dead `PageData.visualize()` font_path call). All 3 imports in `masker.py` rewritten.

### Task 2 — PageBox model (D-15 seam) + textblock_to_box + ImageFile.boxes slot

- **`manga_ai_studio/core/box_model.py`** (NEW, 106 lines):
  - `DETECTED = "detected"` / `USER = "user"` module-level constants (D-03 origin discriminator — single source of truth).
  - `PageBox` dataclass that **COMPOSES** a vendored `Box` (does NOT subclass — D-14 anti-pattern). Fields: `box: Box`, `origin: str`, `payload: Optional[object] = None`, `mask: Optional[object] = None` (D-15 seam), `std_dev: Optional[float] = None` (D-15 seam). Docstring explicitly states mask+std_dev are None in Phase 3 and are the D-15 plan-for-it seam.
  - `textblock_to_box(blk) -> Box`: the single V5 input-validation boundary — coerces `blk.xyxy` to `Box(int(x1), int(y1), int(x2), int(y2))`. Pure (no Qt, no image access); bounds-clamping at the caller in plan 03-04.
- **`manga_ai_studio/core/image_file.py`** (MODIFY): added `boxes: list["PageBox"] | None = None` field after `mask` (mirrors the Phase 2 mask slot, D-11) + `has_boxes() -> bool: return bool(self.boxes)` (trivial truthiness check — boxes have no pixel content to scan). `PageBox` import deferred via `TYPE_CHECKING`. Documented as per-page, in-memory only (PROJ-01 `.mas` save is Phase 5).

### Wave 0 test files (headless, `@pytest.mark.unit`)

- **`tests/test_core/test_structures.py`** (10 tests): full-surface import smoke (Pitfall 2 regression), `Box.as_tuple_xywh` QRectF mapping, `Box.as_tuple` xyxy, `Box.__contains__` hit-test (interior + inclusive corners + outside), `BoxType` enum values, `pick_best_mask` no-longer-AttributeError proof.
- **`tests/test_core/test_masker_vendor.py`** (5 tests, one shared with image_ops): masker imports with `output_structures` NOT vendored (Pitfall 1 guard proof — FAILS if the guard is missing), `mask_page`/`save_denoising_data` callable, std-dev machinery (`border_std_deviation`/`color_std`/`pick_best_mask`) available from image_ops (D-15 seam).
- **`tests/test_core/test_box_model.py`** (12 tests): DETECTED/USER constants, PageBox composes-not-subclasses Box, D-15 seam defaults-None lock for detected, payload None for user, seam fields populatable, `textblock_to_box` float→int coercion + int passthrough + purity, ImageFile.boxes defaults None, `has_boxes()` false/true/empty-list.

## Verification

All plan `<verification>` block commands pass:

- `python -m pytest tests/test_core/test_structures.py tests/test_core/test_masker_vendor.py tests/test_core/test_box_model.py -q` → **22 passed**
- `python -c "from panelcleaner.structures import Box; from panelcleaner.masker import mask_page; from manga_ai_studio.core.box_model import PageBox, textblock_to_box; from manga_ai_studio.core.image_file import ImageFile; print('foundation imports ok')"` → prints `foundation imports ok`
- The 4 RESEARCH §Vendoring smoke commands all print `ok` (structures / masker / std-dev machinery / Box geometry).
- `python -m pytest tests/ -m unit -q` → **98 passed, 80 deselected** (no regression to Phase 1/2 headless tests — the HistoryManager entry-shape widen is plan 03-02, not this plan).

All `<acceptance_criteria>` for both tasks met (line counts, grep counts, smoke commands, GPL headers, "imports rewritten" notes, `class PageBox(Box)` == 0 anti-pattern guard).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rewrote 5th pcleaner. reference in vendored structures.py body (not just the 4 imports)**
- **Found during:** Task 1 (vendoring structures.py)
- **Issue:** The plan's action said "Rewrite the four upstream imports" but the upstream `structures.py:275` contains a 5th `pcleaner.` reference inside the `PageData.visualize()` method body: `hp.resource_path(pcleaner.data, "LiberationSans-Regular.ttf")`. This is a qualified module name (not via an import alias), so it would not be rewritten by editing the import lines. Per D-12 discipline ("imports rewritten pcleaner. -> panelcleaner."), ALL `pcleaner.` references must be rewritten for the vendored module to be self-consistent.
- **Fix:** Rewrote line 275's `pcleaner.data` → `panelcleaner.data`. The `visualize()` method is dead code in our context (Phase 3 never calls it), but rewriting keeps the file internally consistent and matches the D-12 vendoring header note.
- **Files modified:** panelcleaner/structures.py
- **Commit:** 1c1c184

**2. [Rule 2 - Correctness] Deferred PageBox import in image_file.py via TYPE_CHECKING (instead of the plan's suggested direct import)**
- **Found during:** Task 2 (extending image_file.py)
- **Issue:** The plan's action said "a direct `from manga_ai_studio.core.box_model import PageBox` is fine" because PageBox imports only from panelcleaner.structures (no cycle risk). However, importing PageBox at module top in image_file.py pulls panelcleaner.structures (which imports PIL/attrs/loguru + panelcleaner.config/helpers) into the import-time closure of image_file.py — which is itself imported by the GUI layer at QApplication construction. While not a true cycle, deferring the import is strictly safer and avoids any ordering sensitivity.
- **Fix:** Used `from typing import TYPE_CHECKING` + `if TYPE_CHECKING: from manga_ai_studio.core.box_model import PageBox`. The `boxes` field annotation is a forward-reference string (`list["PageBox"]`) that resolves lazily under the existing `from __future__ import annotations`. Runtime behavior is identical; import-time cost is reduced.
- **Files modified:** manga_ai_studio/core/image_file.py
- **Commit:** 9ac01bc

### Notes
- No auth gates, no checkpoints (Pattern A fully autonomous — confirmed by `grep "type=\"checkpoint"` returning nothing).
- The stale `panelcleaner/__pycache__/structures.cpython-314.pyc` (the old stub's bytecode) is auto-invalidated by Python's mtime check on next import — no manual cleanup needed (proven by the smoke commands succeeding against the fresh module).

## TDD Gate Compliance

This plan's frontmatter is `type: execute` (not `type: tdd` at the plan level), but both tasks carried `tdd="true"`. I followed the per-task RED/GREEN cycle with separate commits:

| Task | RED commit (test) | GREEN commit (feat) | Gate |
|------|-------------------|---------------------|------|
| 1 | `26bbea4` (9/10 failing) | `1c1c184` (10/10 passing) | RED before GREEN ✓ |
| 2 | `7c283ab` (12/12 failing) | `9ac01bc` (12/12 passing) | RED before GREEN ✓ |

Both RED phases confirmed the tests genuinely failed before implementation (the fail-fast rule held — no test passed unexpectedly during RED). Both GREEN phases confirmed minimal implementation made all tests pass. No REFACTOR phase needed (the implementations were already minimal).

## Known Stubs

None. The vendored `masker.mask_page` / `save_denoising_data` are dead code in Phase 3 by design (the ost guard makes `ost = None` and Phase 3 never calls them) — they are NOT stubs, they are near-verbatim upstream code kept for the D-15 seam documentation and upstream diffability. The `PageBox.mask` / `PageBox.std_dev` fields default to `None` by design (D-15 seam — intentionally deferred, documented in the dataclass docstring, and locked by `test_pagebox_d15_seam_defaults_none_for_detected`).

## Self-Check: PASSED

Created files exist:
- FOUND: panelcleaner/masker.py
- FOUND: manga_ai_studio/core/box_model.py
- FOUND: tests/test_core/test_structures.py
- FOUND: tests/test_core/test_masker_vendor.py
- FOUND: tests/test_core/test_box_model.py

Modified files present:
- FOUND: panelcleaner/structures.py (764 lines, full surface)
- FOUND: manga_ai_studio/core/image_file.py (boxes slot + has_boxes)

Commits exist:
- FOUND: 26bbea4 (test RED Task 1)
- FOUND: 1c1c184 (feat GREEN Task 1)
- FOUND: 7c283ab (test RED Task 2)
- FOUND: 9ac01bc (feat GREEN Task 2)

---
phase: 02-cleaning-output-batch
plan: 01
subsystem: core-io
tags: [image-output, png, jpg, dpi, passthrough, panelcleaner-adaptation, tdd]
requires:
  - Phase 1 runtime (Pillow, NumPy) — already present
provides:
  - save_image_optimized (numpy->PIL->file write primitive for Plan 03 batch + Plan 04 export)
  - passthrough_original (D-03 empty-mask copy-through for Plan 03 batch loop)
  - _SUFFIX_TO_FORMAT (module-level format map)
affects:
  - Plan 02-03 (batch cleaned/ writes call both functions)
  - Plan 02-04 (Export Page dialog calls save_image_optimized)
tech-stack:
  added: []
  patterns:
    - "numpy (H,W,3) uint8 RGB -> PIL -> file single write path"
    - "shutil.copy2 bytes+metadata passthrough (no re-encode)"
    - "GPL v3 adaptation header (D-12)"
    - "pure stdlib+numpy+PIL module (no Qt/torch) — thread-safe, headless"
key-files:
  created:
    - manga_ai_studio/core/image_io.py
    - tests/test_core/test_image_io.py
  modified: []
decisions:
  - "PNG stores DPI as integer pixels-per-meter, so 300 DPI round-trips to 299.9994 — assert within 1 DPI rather than exact equality"
  - "Use filecmp.cmp (not the nonexistent shutil.cmp) for byte comparison in the passthrough test"
  - "Module imports only stdlib+numpy+PIL so it is thread-safe and unit-testable headless (RESEARCH Arch Responsibility Map)"
metrics:
  duration: 5 min
  completed: 2026-07-25
  tasks: 2
  files: 2
status: complete
---

# Phase 02 Plan 01: Image Output Writer Summary

Adapted PanelCleaner's `save_optimized` into a pure numpy→PIL→file output writer (`save_image_optimized`) plus the D-03 empty-mask `shutil.copy2` passthrough, landing the GUI-free, model-free output primitive that Plans 03 (batch) and 04 (export) build on.

## What Was Built

**`manga_ai_studio/core/image_io.py`** (new) — the single numpy→PIL→file write path for Phase 2:

- `save_image_optimized(image_rgb, path, original=None)`: validates input is `(H,W,3)` uint8 (raises `ValueError` otherwise, before any file write), builds a PIL RGB image, preserves mode+DPI from a same-format `original` (wrapped in `try/except (OSError, ValueError)` so a malformed original degrades gracefully — T-02-03), and applies format-specific kwargs from PanelCleaner `image_export.py:65-72` (PNG `compress_level=9`; JPG `quality=95` + `progressive=True`; `optimize=True` always). Creates parent dirs then saves.
- `passthrough_original(original, cleaned_dir)`: the D-03 empty-mask branch — `mkdir(parents=True)` then `shutil.copy2` (preserves bytes + mtime + metadata, no re-encode through PIL). Returns the destination path.
- `_SUFFIX_TO_FORMAT`: module-level dict trimmed to the Phase 1 open-dialog set (`.jpg/.jpeg`→JPEG, `.png`→PNG, `.webp`→WEBP, `.bmp`→BMP; tiff/tif/dib/jp2/ppm dropped).
- Carries the GPL v3 / D-12 adaptation header; imports NO Qt, NO torch (PySide6 grep count = 0).

**`tests/test_core/test_image_io.py`** (new) — 5 `@pytest.mark.unit` tests:
`test_save_png_kwargs`, `test_save_jpg_kwargs`, `test_preserves_dpi_mode`, `test_passthrough_copy2`, `test_rejects_non_rgb_input`.

## Task Results

| Task | Name | Commit | Key Files |
| ---- | ---- | ------ | --------- |
| 1 | Create test_image_io.py test suite (RED) | ff536d9 | tests/test_core/test_image_io.py |
| 2 | Implement core/image_io.py to pass the suite (GREEN) | b69cd21 | manga_ai_studio/core/image_io.py, tests/test_core/test_image_io.py |

## Verification

- `python -m pytest tests/test_core/test_image_io.py` → **5 passed**.
- `python -m pytest tests/test_core/` (VALIDATION quick-run) → **9 passed** (4 existing + 5 new).
- `python -c "from manga_ai_studio.core.image_io import save_image_optimized, passthrough_original"` → succeeds, no Qt/torch side effects.
- Acceptance grep checks all satisfied: `compress_level = 9`, `quality = 95`, `progressive = True`, one `shutil.copy2` line in `passthrough_original`, the `ValueError` input-validation raise, the GPL attribution header, and `grep -ci PySide6` = 0.

## TDD Gate Compliance

- RED gate: `test(02-01): add failing test suite for image output writer` (ff536d9) — suite was RED via `ModuleNotFoundError: No module named 'manga_ai_studio.core.image_io'`.
- GREEN gate: `feat(02-01): implement image output writer to pass the suite` (b69cd21) — all 5 tests green after implementation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PNG DPI round-trip assertion too strict**
- **Found during:** Task 2 (GREEN)
- **Issue:** The plan's behavior specified `assert im.info.get("dpi") == (300.0, 300.0)`, asserting PIL normalizes to exact float 300.0. But PNG stores DPI as integer pixels-per-meter internally, so 300 DPI round-trips to `299.9994`. The implementation correctly preserves DPI (identical to PanelCleaner's behavior); the exact-equality assertion was brittle.
- **Fix:** Asserted `abs(v - 300.0) < 1.0` for both tuple values — verifies DPI is genuinely preserved while tolerating PNG's integer-ppm quantization. Verified the round-trip value with an isolated PIL test.
- **Files modified:** tests/test_core/test_image_io.py
- **Commit:** b69cd21

**2. [Rule 1 - Bug] Used nonexistent `shutil.cmp` instead of `filecmp.cmp`**
- **Found during:** Task 2 (GREEN)
- **Issue:** The plan's behavior/action specified `shutil.cmp(src, dest)` for byte comparison. `shutil` has no `cmp` attribute in Python — the stdlib byte-comparison function is `filecmp.cmp`. The test raised `AttributeError: module 'shutil' has no attribute 'cmp'`.
- **Fix:** Imported `filecmp` and used `filecmp.cmp(src, dest)`. Confirmed `filecmp.cmp` is the correct stdlib function.
- **Files modified:** tests/test_core/test_image_io.py
- **Commit:** b69cd21

No architectural deviations (Rule 4); no auth gates; both fixes are test-only corrections to planner errors discovered while reaching GREEN. The implementation matches the PanelCleaner reference exactly.

## Known Stubs

None. The module is fully implemented — both functions are real, tested primitives.

## Threat Flags

None. The implemented module introduces no security surface beyond what the plan's `<threat_model>` enumerated: the numpy→filesystem write (T-02-01/T-02-02, mitigated by OS-validated/derived paths in caller plans) and the original-metadata read (T-02-03, mitigated by the `try/except (OSError, ValueError)` wrapper). No new network endpoints, auth paths, file access patterns, or trust-boundary schema changes were introduced.

## Self-Check: PASSED

- [x] `manga_ai_studio/core/image_io.py` exists (FOUND)
- [x] `tests/test_core/test_image_io.py` exists (FOUND)
- [x] Commit ff536d9 exists in git log (FOUND)
- [x] Commit b69cd21 exists in git log (FOUND)

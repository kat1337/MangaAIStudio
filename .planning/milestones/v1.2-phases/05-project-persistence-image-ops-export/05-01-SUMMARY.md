---
phase: 05-project-persistence-image-ops-export
plan: 01
subsystem: core-serialization
tags: [lzma, mas, project-file, serialization, sha256, persistence]

# Dependency graph
requires:
  - phase: 04-ocr-recognition-text-editing
    provides: PageBox peer fields (text/translation/edited/bubble_no/manual_override) + TextBlock payload shape
  - phase: 03-text-box-detection-interaction
    provides: PageBox model, vendored frozen Box, D-15 seam (mask/std_dev stay None)
  - phase: 02-cleaning-output-batch
    provides: core/image_io.py pure-stdlib module template (save_image_optimized PNG kwargs)
provides:
  - core/project_io.py — the .mas LZMA2 container, manifest save/load, PageBox↔JSON mapping, sha256 D-06 rule, D-09 sibling detection, untrusted-input validation
  - ImageFile.original_verified (D-06) + geometry_altered (D-22) flags
  - core/image_io.save_image_bytes in-memory PNG encoder
affects: [05-05 save/open GUI, 05-08 export, 05-06 show-original gating, 05-09]

# Actuals (#2632) — pairs with the plan's `estimate` (28000 tokens) on the same scale.
actuals:
  tokens: 10330    # chars/4 over the realized diff (41320 chars over 4 files)
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: [stdlib lzma FORMAT_XZ, stdlib hashlib sha256, stdlib struct/json — zero new packages]
  patterns:
    - "Atomic disk writes: same-directory temp file + os.replace per file (interrupted-save backstop)"
    - "memlimit-bounded LZMA2 decompression (T-05-01 decompression-bomb mitigation)"
    - "V5 int() coercion of every numeric field on load (textblock_to_box discipline, T-05-02)"
    - "Lazy module-local imports for cycle safety (PageBox/TextBlock/Box) — established codebase pattern"

key-files:
  created:
    - manga_ai_studio/core/project_io.py
    - tests/test_core/test_project_io.py
  modified:
    - manga_ai_studio/core/image_file.py
    - manga_ai_studio/core/image_io.py

key-decisions:
  - "Container: custom header (magic MAS\\x00 + version + entry count) + per-entry name_len u16/data_len u64 table, each payload LZMA2-compressed with FORMAT_XZ preset 6 (locked D-04; preset 9's ~800 MiB overhead rejected per RESEARCH A6)"
  - "Decompression bounded per entry at 512 MiB (MAX_ENTRY_DECOMPRESSED) with LZMAError→ProjectFormatError; the whole header+entry-table unpack is wrapped so no raw struct.error/IndexError escapes (T-05-01)"
  - "load_page_file and load_project reject format versions != 1 as ProjectFormatError (the 'corrupt/newer-version' copy; RESEARCH A9)"
  - "Manifest written plain UTF-8 JSON (ensure_ascii=False, indent=2) — human-readable + diffable per D-04; non-ASCII chapter names round-trip literally"
  - "PNG encode delegates to core/image_io.save_image_bytes (single source of truth) instead of duplicating PIL code in project_io"
  - "validate_meta is lenient on a missing geometry_altered (validated only when present) — avoids over-rejecting; build always writes it"
  - "test_save_is_atomic fails os.replace on the 3rd call (after manifest + first page succeed) — proves the per-file temp+replace scheme never corrupts any target"

patterns-established:
  - "Atomic write helper _atomic_write_bytes shared by save_page_file and save_project"
  - "build_page_entries/parse_page_entries symmetric projection pair; mask reshaped from meta-recorded dims (never blob length) + .copy() detachment (Pitfall 2)"
  - "verify_original: Path.resolve() BEFORE suffix allowlist, then chunked sha256 — returns False, never raises (T-05-03)"
  - "find_sibling_manifest re-validates the sibling manifest via load_project — corrupt sibling raises, never silently opens standalone (D-09)"

requirements-completed: [PROJ-01]

coverage:
  - id: D1
    description: ".mas page container round-trips byte-for-byte; corrupt magic / malformed entry tables rejected as ProjectFormatError"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_page_file_round_trip"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_bad_magic_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_malformed_entry_table_rejected"
        status: pass
    human_judgment: false
  - id: D2
    description: "PageBox↔JSON mapping with full TextBlock payload fidelity (multi-line text, line quads, vertical/language/font_size, peer fields) and the D-15 seam (mask/std_dev never serialized)"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_pagebox_json_round_trip"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_d15_seam_preserved"
        status: pass
    human_judgment: false
  - id: D3
    description: "Chapter manifest save/load with UTF-8 names, non-destructive overwrite of owned files only (D-02), and atomic interrupted-save backstop"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_manifest_round_trip"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_non_destructive_overwrite"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_save_is_atomic"
        status: pass
    human_judgment: false
  - id: D4
    description: "Per-page state assembly: build_page_entries → save → load → parse_page_entries round-trips image/mask/original projections"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_page_entries_round_trip"
        status: pass
    human_judgment: false
  - id: D5
    description: "ImageFile.original_verified (D-06) + geometry_altered (D-22) flags default False; save_image_bytes in-memory PNG encoder"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_image_file_flags_default"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_save_image_bytes_round_trip"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-06 original-verification rule: resolve + image-suffix allowlist + chunked sha256 match; False (never raises) on missing/wrong/non-image (T-05-03)"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_original_checksum_rule"
        status: pass
    human_judgment: false
  - id: D7
    description: "D-09 sibling-manifest detection: returns valid sibling, None when absent, ProjectFormatError when sibling is malformed"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_sibling_manifest_detection"
        status: pass
    human_judgment: false
  - id: D8
    description: "Untrusted-input validation: meta dims bounded by MAX_IMAGE_DIMENSION (10000), mask==img dims, geometry_altered bool, oversized chapter (>1000 pages) rejected (T-05-02/T-05-04)"
    requirement: PROJ-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_meta_validation"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_oversized_chapter_rejected"
        status: pass
    human_judgment: false

# Metrics
duration: 10min
completed: 2026-08-08
status: complete
---

# Phase 05 Plan 01: .mas Project Serialization Core Summary

**LZMA2 (FORMAT_XZ) `.mas` page-file container + plain-JSON chapter manifest with atomic non-destructive saves, PageBox↔JSON mapping with full TextBlock payload fidelity (D-15 seam preserved), and the D-06 sha256 / D-09 sibling-detection / T-05-01…T-05-04 untrusted-input validation suite**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-08-08T18:49:39Z
- **Completed:** 2026-08-08T18:59:00Z
- **Tasks:** 3 (1 tracer + 2 auto)
- **Files modified:** 4 (1 created module, 1 created test file, 2 extended)

## Accomplishments

- `core/project_io.py` — the headless serialization core every other Phase 5 plan builds on: custom LZMA2 container (D-04, preset 6, memlimit-bounded decompression at 512 MiB), `save_page_file`/`load_page_file` (atomic temp+`os.replace`), `save_project`/`load_project` (plain UTF-8 diffable manifest, non-destructive owned-file-only overwrite, `MAX_PROJECT_PAGES=1000` bound), `build_page_entries`/`parse_page_entries` (4-entry page projection: meta.json / image.png / mask.bin / original.json), `pagebox_to_json`/`json_to_pagebox` (V5 int coercion, D-15 seam), `sha256_file`/`verify_original` (D-06 chunked checksum + suffix allowlist, never raises), `find_sibling_manifest` (D-09), `validate_meta` (dims ≤ 10000, mask==img, bool geometry_altered)
- `ImageFile.original_verified` (D-06) + `geometry_altered` (D-22) peer fields with documented semantics
- `core/image_io.save_image_bytes` — in-memory PNG encoder mirroring `save_image_optimized` kwargs + validation
- 15 tests green in `tests/test_core/test_project_io.py`; full suite re-measured at 477 collected / 476 passed / 1 failed (the sole failure remains the documented pre-existing `test_gui_boxes` 1px regression — baseline was 462/461/1, +15 tests this plan; remediation is plan 05-09, same wave)

## Task Commits

Each task was committed atomically:

1. **Task 1 (TRACER): .mas LZMA2 page-file container + PageBox↔JSON mapping** - `c5a8e71` (feat)
2. **Task 2: Chapter manifest + page-state assembly + atomic non-destructive save + ImageFile flags** - `8789b61` (feat)
3. **Task 3: D-06 sha256 checksum rule + D-09 sibling-manifest detection + untrusted-file validation** - `75917d5` (feat)

## Files Created/Modified

- `manga_ai_studio/core/project_io.py` (NEW, ~640 lines) - `ProjectFormatError`, `_MAGIC`/`_FORMAT_VERSION`, `MAX_ENTRY_DECOMPRESSED`/`MAX_PROJECT_PAGES`/`MAX_IMAGE_DIMENSION`/`_IMAGE_SUFFIXES`, `_pack_entry`, `_atomic_write_bytes`, `save_page_file`, `load_page_file`, `pagebox_to_json`, `json_to_pagebox`, `build_page_entries`, `save_project`, `load_project`, `parse_page_entries`, `sha256_file`, `verify_original`, `find_sibling_manifest`, `validate_meta`
- `manga_ai_studio/core/image_file.py` (EXTEND) - `original_verified: bool = False`, `geometry_altered: bool = False` + docstring updates
- `manga_ai_studio/core/image_io.py` (EXTEND) - `save_image_bytes(image_rgb) -> bytes`
- `tests/test_core/test_project_io.py` (NEW) - 15 test functions across the three tasks

## Decisions Made

- Container entry-table layout implemented exactly per RESEARCH Pattern 1 (`<HQ` name_len/data_len; preset 6; `memlimit` on every decompress) — locked by D-04
- `load_page_file`/`load_project` reject format version ≠ 1 with ProjectFormatError (the "from a newer version" corrupt-file copy, RESEARCH A9)
- Manifest written with `ensure_ascii=False, indent=2` so non-ASCII chapter names round-trip as literal UTF-8 (verified by `test_manifest_round_trip` asserting `章` appears in the file bytes)
- PNG encoding delegates to `image_io.save_image_bytes` rather than re-implementing PIL in `project_io` (single source of truth; `test_save_image_bytes_round_trip` guards it)
- `validate_meta` validates `geometry_altered` only when present (lenient) — `build_page_entries` always writes it, but load does not over-reject older files
- `test_save_is_atomic` fails `os.replace` on the 3rd call — after manifest.json and the first page succeed — proving per-file atomicity on every target, not just the first write

## Deviations from Plan

None required by deviation rules. Minor implementation notes (no rule-triggered fixes):

1. **[Note - import ordering]** `numpy`/`hashlib` imports landed in `project_io.py` with the tasks that use them (Task 2 numpy for mask reshape, Task 3 hashlib for `sha256_file`) rather than all at Task 1, and PIL is not imported in `project_io` at all — PNG encoding delegates to `image_io.save_image_bytes` (the plan's Task 1 import list included `PIL Image`; unused imports are dead code). Module contract unchanged: stdlib + numpy + Pillow only.
2. **[Note - constant timing]** `MAX_PROJECT_PAGES` was defined in Task 2 (when `load_project` first needs the bound) rather than Task 3 — Task 3's `test_oversized_chapter_rejected` then passes against the existing bound.
3. **[Note - extra coverage]** Added `test_page_entries_round_trip` (build→save→load→parse integration, incl. mask reshape + original ref) beyond the plan's named Task 2 tests; suite is 15 tests (plan minimum 10+).

**Total deviations:** 0 auto-fixed (3 minor notes)
**Impact on plan:** None — all acceptance criteria met; suite green except the documented pre-existing regression.

## Issues Encountered

None — no blockers, no auth gates, no package installs (zero new dependencies per the phase audit).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `core/project_io.py` is the load-bearing serialization core for plan 05-05 (Save/Open Project GUI rebuilds the session from `load_project` + `parse_page_entries`; `find_sibling_manifest` drives the chapter-climb dialog), 05-08 (export reads the same PageBox state), and 05-06 (`original_verified` gates Show Original; `verify_original` implements the D-06 rule at the GUI boundary)
- 05-09 (same wave) owns the pre-existing `test_gui_boxes` regression fix; until then the full suite carries its documented 1 known failure

## Self-Check: PASSED

- FOUND: manga_ai_studio/core/project_io.py
- FOUND: tests/test_core/test_project_io.py
- FOUND: .planning/phases/05-project-persistence-image-ops-export/05-01-SUMMARY.md
- FOUND commit: c5a8e71 (Task 1 tracer)
- FOUND commit: 8789b61 (Task 2)
- FOUND commit: 75917d5 (Task 3)

---
*Phase: 05-project-persistence-image-ops-export*
*Completed: 2026-08-08*

---
phase: 08-masker-selective-inpaint
plan: 04
subsystem: core
tags: [serialization, mas-container, d15-seam, optional-keys, extended-entries, mask-planes, singleton, png-base64, project-io]

requires:
  - phase: 08-masker-selective-inpaint
    provides: plan 08-01 — PageBox.inpaint_override/inpaint_state, MaskerConfig.mask_dilation_radius
  - phase: 08-masker-selective-inpaint
    provides: plan 08-02 — core/mask_planes.py pack_binary/unpack_binary + ImageFile plane slots (D-11 seam)
  - phase: 08-masker-selective-inpaint
    provides: plan 08-03 — derive_page_mask_state populating PageBox.mask (box-cropped mode-"1") and std_dev; raw_binary D-08 retention
provides:
  - pagebox JSON keys extended: "std_dev" (float|None), "inpaint_override" ("always"|"never"|None), "mask" (base64 PNG of the box-cropped mode-"1" mask | None)
  - page container optional entries: rawmask.bin / automask.bin / manualmask.bin / erasemask.bin (pack_binary blobs)
  - parse_page_entries return keys: raw_packed/auto_packed/manual_packed/erase_packed (None when absent) with ceil(h*w/8) length cross-check
  - build_page_entries page_state input keys: raw_binary/auto_binary/manual_binary/erase_binary
  - The D-15 seam closes through persistence: .mas round-trips per-box mask/std_dev/override + per-page plane binaries, no _FORMAT_VERSION bump
affects: [08-masker-selective-inpaint, 09-ui-rework]

tech-stack:
  added: []
  patterns:
    - "Optional-key .mas evolution retired for the PageBox seam: the D-15 'never writes mask/std_dev' docstring contract superseded by Phase 8 serialization (the Phase 7 optional-key precedent — absent/None -> defaults, never a version bump)"
    - "Per-box mask stored as base64 PNG of the box-cropped mode-'1' image (RESEARCH §6.3 option a), encoded via PIL directly (save_image_bytes expects RGB; mode-'1' needs the direct save)"
    - "Optional page entries ride the existing per-entry LZMA2 container path — entry names are naturally optional on parse (RESEARCH §6.3c)"

key-files:
  created: []
  modified:
    - manga_ai_studio/core/project_io.py
    - tests/test_core/test_project_io.py

key-decisions:
  - "Per-box mask serializes as base64 PNG of the box-cropped mode-'1' image (RESEARCH §6.3 option a) — PNG packbits keep a mostly-empty text-box mask to a few hundred bytes; decoded size is cross-checked to the box dims"
  - "Plane binaries persist as pack_binary 1-bit blobs (~H*W/8 per page, RESEARCH §6.4/§2.3) — the loader can re-dilate rawmask.bin on a radius change without re-detecting, and never loses hand strokes to a recomposition"
  - "Plane blob length validation uses ceil(h*w/8) against the meta-declared image dims (the planes are page-sized; mask.bin dims already equal the image dims via validate_meta)"
  - "Both new surfaces are optional on load (no _FORMAT_VERSION bump): legacy Phase 5/7 .mas files load with every new field None/absent — the Phase 7 optional-key pattern applied to std_dev/inpaint_override/mask and the four plane entries"

patterns-established:
  - "D-15 seam serialization: pagebox_to_json/_pagebox_mask_to_json write std_dev, inpaint_override, and the base64-PNG per-box mask; json_to_pagebox reads them with float-coercion, enum validation, and a hardened b64->PNG decode"
  - "Decode hardening (T-08-06): b64 decode + Image.open fully wrapped — binascii.Error/TypeError/ValueError/OSError/UnidentifiedImageError/DecompressionBombError all re-raise as ProjectFormatError; PIL's MAX_IMAGE_PIXELS bomb guard stays active; decoded size cross-checked to the box dims"
  - "Optional plane entries (T-08-07): length == ceil(h*w/8) validated before returning the packed array — a short/long crafted blob is ProjectFormatError, never a mis-shaped unpack"

requirements-completed: [MASK-02, MASK-03]

coverage:
  - id: D1
    description: "pagebox_to_json/json_to_pagebox extended with std_dev, inpaint_override, and the box-cropped mode-'1' mask (base64 PNG) — full round-trip with equal values, legacy dict without the keys loads with all three None, invalid override/float/std and mask-size mismatch rejected"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_phase8_seam_fields_round_trip"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_legacy_pagebox_without_phase8_keys_loads_defaults"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_invalid_inpaint_override_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_invalid_std_dev_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_per_box_mask_size_mismatch_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_per_box_mask_garbage_rejected"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_d15_seam_superseded_by_phase8"
        status: pass
    human_judgment: false
  - id: D2
    description: "Optional page container entries rawmask.bin/automask.bin/manualmask.bin/erasemask.bin — build_page_entries writes them from page_state binaries (none for legacy-shaped state); parse_page_entries returns the four packed arrays with matching content and None for absent entries"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_build_page_entries_writes_optional_plane_entries"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_parse_page_entries_plane_round_trip"
        status: pass
    human_judgment: false
  - id: D3
    description: "T-08-07 tampering mitigation — a crafted plane blob whose byte length does not equal ceil(h*w/8) for the declared dims raises ProjectFormatError (short and long), never a mis-shaped array"
    requirement: MASK-03
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_crafted_plane_blob_length_rejected"
        status: pass
    human_judgment: false
  - id: D4
    description: "End-to-end save -> load round-trip of a page with boxes carrying mask/std_dev/inpaint_override AND the four plane binaries rebuilds everything equal — the D-15 seam closes through persistence (RD success criterion 5)"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_project_io.py#test_page_entries_full_round_trip_with_seam_and_planes"
        status: pass
    human_judgment: false

duration: 12 min
completed: 2026-08-17
status: complete
---

# Phase 08 Plan 04: .mas Serialization of the D-15 Seam + Plane Binaries Summary

**The .mas format now round-trips per-box std_dev / inpaint_override / the box-cropped mode-"1" mask, and the four per-page plane binaries, all as optional keys/entries with hardened bounded decoding — 794 tests green**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-17T13:38:26Z
- **Completed:** 2026-08-17T13:47:11Z
- **Tasks:** 2 (TDD: 2 RED + 2 GREEN commits)
- **Files modified:** 2 (production + test)

## Accomplishments
- `pagebox_to_json` now emits `"std_dev": pb.std_dev`, `"inpaint_override": pb.inpaint_override`, and `"mask"` — the box-cropped mode-"1" PIL mask (plan 08-03 convention) encoded as base64 PNG via PIL directly (`save_image_bytes` expects RGB pages; mode "1" needs the direct in-memory save, RESEARCH §6.3 option a). The D-15 seam contract in the module/function docstrings ("NEVER writes mask/std_dev") is superseded.
- `json_to_pagebox` reads all three as OPTIONAL keys: `std_dev` float-coerces (TypeError/ValueError -> ProjectFormatError), `inpaint_override` is enum-validated against `{"always","never"}` (None/Auto passes), and `mask` decodes base64 -> PNG with a decoded-size cross-check against the box dims then converts to mode "1" (`dither=Image.NONE`, Pitfall 13-7). The decode is fully wrapped (T-08-06): `binascii.Error/TypeError/ValueError/OSError/UnidentifiedImageError/DecompressionBombError` all re-raise as ProjectFormatError — no raw library exception escapes the loader (the T-05-01 pattern), and PIL's default `MAX_IMAGE_PIXELS` bomb guard stays active.
- `build_page_entries` accepts the optional `raw_binary`/`auto_binary`/`manual_binary`/`erase_binary` page_state keys and writes `rawmask.bin`/`automask.bin`/`manualmask.bin`/`erasemask.bin` containing `pack_binary(...).tobytes()` — the entries ride the existing per-entry LZMA2 container unchanged; legacy-shaped state writes none of the four.
- `parse_page_entries` reads the four entries when present as PACKED arrays keyed `raw_packed`/`auto_packed`/`manual_packed`/`erase_packed` (None when absent), each length-validated to `ceil(h*w/8)` against the meta-declared dims (T-08-07) — a short/long crafted blob is a ProjectFormatError, never a mis-shaped array; callers unpack via `mask_planes.unpack_binary` with the page dims.
- The end-to-end save -> load round-trip test proves the RD success-criterion-5 seam: a page with boxes (mask/std_dev/inpaint_override) + all four plane binaries rebuilds everything equal. No `_FORMAT_VERSION` bump — both new surfaces are optional-on-load so legacy Phase 5/7 `.mas` files keep loading with defaults (the Phase 7 optional-key pattern; `test_legacy_pagebox_without_phase8_keys_loads_defaults` locks it).

## Task Commits

Each task was committed atomically (TDD: RED test commit -> GREEN feat commit):

1. **Task 1: pagebox_to_json / json_to_pagebox — std_dev, inpaint_override, per-box mask** - `376a3b0` (test) + `6fc57aa` (feat)
2. **Task 2: Optional page entries — rawmask.bin / automask.bin / manualmask.bin / erasemask.bin** - `de06a39` (test) + `57def65` (feat)

**Plan metadata:** final docs commit (below)

## Files Created/Modified
- `manga_ai_studio/core/project_io.py` - `_pagebox_mask_to_json`/`_pagebox_mask_from_json` helpers; `pagebox_to_json` emits the three Phase 8 keys; `json_to_pagebox` optional-key reads with float/enum/size validation + hardened decode; `build_page_entries` accepts the four plane binaries and writes the optional entries; `parse_page_entries` returns the four packed keys with the `ceil(h*w/8)` length cross-check; module docstring updates to the Phase 8 contract
- `tests/test_core/test_project_io.py` - Task 1: round-trip/legacy/invalid-override/invalid-std_dev/mask-size-mismatch/garbage-mask tests + D-15-seam test re-based; Task 2: build/parse plane round-trip, crafted-blob-length rejection (short + long), and the end-to-end seam+planes round-trip

## Decisions Made
- Per-box mask stored as base64 PNG of the box-cropped mode-"1" image (RESEARCH §6.3 option a) — compact, versioning-free; decoded size is cross-checked to the box dims so a crafted mask cannot exceed the declared box bounds (T-08-06).
- Plane binaries persist as `pack_binary` 1-bit blobs (~H*W/8 per page, RESEARCH §6.4/§2.3) — the loader can re-dilate `rawmask.bin` after a radius change without re-detecting and never loses hand strokes to a recomposition.
- Length validation uses the meta-declared image dims (`ceil(h*w/8)`) — the planes are page-sized, and `validate_meta` already forces mask.bin dims to equal the image dims, so this is the exact discipline of the `mask.bin` :467-471 cross-check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] D-15 seam docstring + stale test re-based to the superseding contract**
- **Found during:** Task 1 (implementation)
- **Issue:** The plan..'s action says "Update the docstring: the D-15 seam contract ('NEVER writes mask/std_dev') is superseded by Phase 8" — the module-level docstring, `pagebox_to_json` docstring, and the `test_d15_seam_preserved` test (which asserted those keys must NOT be written and used `mask=object()` — no longer a valid construction once serialization writes the key) all still encoded the old Phase 5/7 contract
- **Fix:** Module + function docstrings rewritten to the Phase 8 contract; the D-15 test re-based to `test_d15_seam_superseded_by_phase8` (unset fields serialize as explicit null and round-trip to None)
- **Files modified:** manga_ai_studio/core/project_io.py, tests/test_core/test_project_io.py
- **Verification:** test_d15_seam_superseded_by_phase8 passes (RED gate: fails with KeyError on the missing key before GREEN)
- **Committed in:** 376a3b0 (test re-base), 6fc57aa (source docstrings)

**2. [Rule 2 - Missing Critical] DecompressionBombError added to the decode wrap**
- **Found during:** Task 1 (implementation hardening review)
- **Issue:** The plan..'s decode-hardening list names binascii.Error/ValueError/OSError/UnidentifiedImageError, but PIL's `MAX_IMAGE_PIXELS` bomb guard stays active per the plan and raises `Image.DecompressionBombError` — a distinct Exception subclass, NOT an OSError. A crafted huge-dimension PNG would otherwise escape the ProjectFormatError boundary raw (a T-05-01 violation)
- **Fix:** `Image.DecompressionBombError` added to the except tuple in `_pagebox_mask_from_json` (probe-verified the class MRO on the pinned interpreter: `DecompressionBombError -> Exception`, `isinstance(e, OSError) == False`)
- **Files modified:** manga_ai_studio/core/project_io.py
- **Verification:** full project_io suite green; a synthetic 40000x40000 PNG probe raises ProjectFormatError post-GREEN
- **Committed in:** 6fc57aa

---

**Total deviations:** 2 auto-fixed (both missing-critical — one docstring/contract re-base explicitly required by the plan, one decode-hardening gap in the plan's own hardening list)
**Impact on plan:** Both fixes are correctness requirements of the plan's own goal (the superseded contract must be re-based coherently; the T-05-01 no-raw-exception boundary must hold under the active bomb guard). No scope creep — both stayed inside the plan's files_modified set.

## TDD Gate Compliance

Both tasks are `tdd="true"`; git log shows the RED->GREEN sequence for each:
- Task 1: `test(08-04)` 376a3b0 -> `feat(08-04)` 6fc57aa
- Task 2: `test(08-04)` de06a39 -> `feat(08-04)` 57def65

RED gates failed for the right reasons (missing keys, missing validation, DID-NOT-RAISE on crafted input). Task 1's legacy-without-keys test and Task 2's content-match assertions passed at RED only after the relevant pairs; the legacy-load and end-to-end fidelity tests are regression locks for behavior that must be preserved. No refactor commits needed.

## Issues Encountered
None - both tasks went green on the first implementation pass. Full suite: **794 passed / 0 failed** (baseline 784 at 08-03 close + 10 new tests).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 08-07's `.mas` write path (MainWindow save side) can now hand `pagebox_to_json`-shaped boxes and the four plane binaries to `build_page_entries`, and its load side receives `raw_packed`/`auto_packed`/`manual_packed`/`erase_packed` from `parse_page_entries` for `canvas.set_planes` (the 08-02 D-11 seam) — border states restore without re-detect
- The 08-03 `raw_binary` D-08 slot and the 08-02 ImageFile plane slots map 1:1 onto the new entries; project_io stays Qt-free and worker-safe (numpy + PIL only, no GUI import)
- No blockers.

## Self-Check: PASSED

Both modified files exist on disk; all 4 task commits found in git log (`git log --grep="08-04"` returns 4: 2 test + 2 feat). Source assertions re-run and passing: `_pagebox_mask_to_json`/`_pagebox_mask_from_json` present; the three pagebox keys written/read; the four plane entry names + four packed return keys + four page_state input keys present; `dither=Image.NONE`; `ceil`-length cross-check in `_read_plane`; no `_FORMAT_VERSION` change (still 1). Full suite re-verified green before SUMMARY — **794 passed / 0 failed** (pinned interpreter).

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-17*
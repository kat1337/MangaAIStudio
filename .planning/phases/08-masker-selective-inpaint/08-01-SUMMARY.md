---
phase: 08-masker-selective-inpaint
plan: 01
subsystem: core
tags: [pagebox, inpaint-override, masker-config, dilation-radius, ini-roundtrip, geometry-ops, dataclass]

requires:
  - phase: 03-text-box-detection-interaction
    provides: PageBox data model with the D-15 mask/std_dev seam and origin tagging
  - phase: 05-project-persistence-image-ops-export
    provides: core/image_ops.py geometry transforms with explicit PageBox rebuild field lists
  - phase: 01-cleaning-workspace
    provides: vendored panelcleaner config system (Profile/ConfigUpdater INI) + ProfileManager
provides:
  - PageBox.inpaint_override tri-state field (None=Auto / "always" / "never")
  - PageBox.inpaint_state(threshold) single derivation site (forced/never/will_inpaint/gate_skipped)
  - PageBox.copy() mask detachment (Pitfall 8)
  - MaskerConfig.mask_dilation_radius (Pixels = 2) with INI export/import round-trip
  - Startup load_profile("default") applying the persisted profile to config.current_profile
  - Geometry-op field policy: rotate/crop/resize carry inpaint_override + style, invalidate mask/std_dev
affects: [08-masker-selective-inpaint, 09-ui-rework]

tech-stack:
  added: []
  patterns:
    - "Tri-state override encoding on a dataclass field (None=Auto, 'always'/'never') distinct from an existing bool pin field"
    - "Vendored-config field addition with marked in-place deviation comment + try_to_load guarded import (INI fallback to default on missing key)"
    - "Geometry-rebuild explicit field lists must name every carried field — unnamed fields are silently dropped (Pitfall 13-6 policy test)"

key-files:
  created:
    - tests/test_core/test_masker_config_roundtrip.py
  modified:
    - manga_ai_studio/core/box_model.py
    - panelcleaner/config.py
    - manga_ai_studio/__main__.py
    - manga_ai_studio/config/profile_manager.py
    - manga_ai_studio/core/image_ops.py
    - tests/test_core/test_box_model.py
    - tests/test_core/test_image_ops.py

key-decisions:
  - "inpaint_state(threshold) is the SINGLE derivation site (BoxItem 08-06 and refresh_box_inpaint_states 08-07 consume it; logic not duplicated)"
  - "Empty auto-mask = getbbox() is None on the box-cropped mode-'1' PIL image (content = non-zero pixels, the 08-03 storage convention); the plan's 'all-white' parenthetical contradicts real PIL semantics and was corrected test-side"
  - "ProfileManager.load_profile applies the loaded profile to config.current_profile (MainWindow's read path) — without it the startup load is a discarded return value (Rule 2 deviation; profile_manager.py joined the files list)"
  - "Geometry ops carry override+style on ALL SIX constructor sites (payload + payload-None per transform) — the payload-None user-box paths drop fields identically"
  - "mask_dilation_radius rides the vendored try_to_load typed-coercion path: missing/garbage key falls back to default 2 (T-08-01 mitigated as planned)"

patterns-established:
  - "Vendored MaskerConfig additions carry a 'Manga AI Studio addition' comment at the field (03-01 qualified-name discipline, RESEARCH 4.2 option a)"
  - "INI export comments double as canonical tooltip text (D-06/D-12) — the ToolsPanel slider (08-05) reuses them verbatim"

requirements-completed: [MASK-01, MASK-02, MASK-03]

coverage:
  - id: D1
    description: "PageBox.inpaint_override tri-state field + copy() PIL-mask detachment + std_dev/override carry through copy"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_box_model.py#test_pagebox_inpaint_override_default_and_roundtrip"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_box_model.py#test_pagebox_copy_detaches_mask_and_preserves_seam_fields"
        status: pass
    human_judgment: false
  - id: D2
    description: "PageBox.inpaint_state(threshold) pure derivation returning exactly forced/never/will_inpaint/gate_skipped per the 08-UI-SPEC border-state contract"
    requirement: MASK-02
    verification:
      - kind: unit
        ref: "tests/test_core/test_box_model.py#test_inpaint_state_matrix"
        status: pass
    human_judgment: false
  - id: D3
    description: "MaskerConfig.mask_dilation_radius default 2 with full INI round-trip, missing-key fallback, and startup load applying the persisted profile to config.current_profile"
    requirement: MASK-01
    verification:
      - kind: unit
        ref: "tests/test_core/test_masker_config_roundtrip.py#test_mask_dilation_radius_default_is_two"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_masker_config_roundtrip.py#test_mask_dilation_radius_round_trips_through_ini"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_masker_config_roundtrip.py#test_ini_without_radius_key_falls_back_to_default"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_masker_config_roundtrip.py#test_startup_load_profile_applies_to_current_profile"
        status: pass
    human_judgment: false
  - id: D4
    description: "Geometry-op field policy: rotate/crop/resize carry inpaint_override + style (both payload and payload-None paths) and invalidate per-box mask/std_dev"
    requirement: MASK-03
    verification:
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_geometry_transforms_carry_inpaint_override_and_style"
        status: pass
      - kind: unit
        ref: "tests/test_core/test_image_ops.py#test_geometry_transforms_invalidate_mask_and_std_dev"
        status: pass
    human_judgment: false

duration: 11 min
completed: 2026-08-16
status: complete
---

# Phase 08 Plan 01: Masker Selective Inpaint Foundations Summary

**PageBox tri-state inpaint override + pure border-state derivation, MaskerConfig dilation radius (default 2) with INI round-trip and startup profile load, and the geometry-op carry/invalidate field policy — 736 tests green**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-16T17:49:23Z
- **Completed:** 2026-08-16T18:00:14Z
- **Tasks:** 3 (TDD: 3 RED + 3 GREEN commits)
- **Files modified:** 8

## Accomplishments
- PageBox carries the D-14 tri-state `inpaint_override` (None=Auto / "always" / "never") and exposes `inpaint_state(threshold)` — the single headless derivation of the 08-UI-SPEC border-state contract returning forced / never / will_inpaint / gate_skipped, with `_has_auto_mask_content()` as the getbbox-based emptiness probe
- `PageBox.copy()` now detaches the mutable PIL mask (Pitfall 8) alongside payload and style, so BOXES undo restores snapshot-time masks
- The vendored MaskerConfig gained `mask_dilation_radius: Pixels = 2` (marked Manga AI Studio addition) with an export block whose comment doubles as the canonical tooltip text and a guarded `try_to_load` import — a PanelCleaner-authored INI without the key loads the default 2
- `__main__.py` loads the persisted "default" profile at startup (OSError-guarded, logs and continues) and `ProfileManager.load_profile` applies it to `config.current_profile` — closing the RESEARCH §4.1 gap so D-10 persistence actually reaches the MainWindow
- All six geometry rebuild sites (rotate/crop/resize × payload/payload-None) now carry `inpaint_override` + `style` and deliberately reset `mask`/`std_dev` to None — closing the field-drop trap (Pitfall 13-6) and the live Phase 7 latent style drop in the same edit

## Task Commits

Each task was committed atomically (TDD: RED test commit → GREEN feat commit):

1. **Task 1: PageBox inpaint_override field + inpaint_state() + copy() detachment** - `7c397c6` (test) + `6687f1c` (feat)
2. **Task 2: MaskerConfig.mask_dilation_radius + INI round-trip + startup profile load** - `37f1495` (test) + `73688fb` (feat)
3. **Task 3: Geometry-op field policy — carry inpaint_override + style, invalidate mask/std_dev** - `85d2b93` (test) + `c63a441` (feat)

**Plan metadata:** final docs commit (below)

## Files Created/Modified
- `manga_ai_studio/core/box_model.py` - inpaint_override field, inpaint_state() + _has_auto_mask_content(), copy() mask detachment, D-15 docs updated to Phase-8-populated
- `panelcleaner/config.py` - MaskerConfig.mask_dilation_radius field + export_to_conf INI block + import_from_conf try_to_load line
- `manga_ai_studio/__main__.py` - startup load_profile("default") guarded by try/except OSError with loguru logging
- `manga_ai_studio/config/profile_manager.py` - load_profile assigns the loaded profile to config.current_profile (Rule 2 deviation)
- `manga_ai_studio/core/image_ops.py` - six PageBox rebuild sites carry override+style and invalidate mask/std_dev; policy docstrings
- `tests/test_core/test_box_model.py` - override round-trip, state matrix, copy-detachment tests
- `tests/test_core/test_masker_config_roundtrip.py` - NEW: default/round-trip/missing-key/startup-apply tests
- `tests/test_core/test_image_ops.py` - parametrized carry/invalidate tests over rotate/crop/resize × payload/no-payload

## Decisions Made
- `inpaint_state(threshold)` kept as the SINGLE derivation site with the four-value return set locked by the matrix test — plans 08-06/08-07 consume, never duplicate
- Empty auto-mask defined as `getbbox() is None` on the box-cropped mode-"1" PIL image (content = non-zero pixels) — matching the vendored pick_best_mask emptiness probe and the 08-03 storage convention
- Geometry invalidation chosen over mask-transforming (RESEARCH §6.5 option b): override is user intent and cheap to carry; a rotated std-dev/border relation is genuinely stale
- No `fix()` clamp added for mask_dilation_radius: consumers treat radius > 0 else no-op (T-08-01b accept), and the typed try_to_load coercion already guards the INI parse surface

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] ProfileManager.load_profile applies the loaded profile**
- **Found during:** Task 2 (startup profile load)
- **Issue:** The plan's `__main__.py` action says "call profile_manager.load_profile('default')" and its behavior test asserts `config.current_profile.masker.mask_dilation_radius == 7` after the call — but `load_profile` only returned the Profile without touching `self.config`, so the startup call would be a discarded return value and MainWindow (which reads `profile_manager.config.current_profile`) would keep defaults forever
- **Fix:** `load_profile` now assigns `self.config.current_profile = profile` before returning (return contract unchanged); docstring documents why
- **Files modified:** manga_ai_studio/config/profile_manager.py (not in the plan's files_modified list)
- **Verification:** test_startup_load_profile_applies_to_current_profile passes; existing test_config.py round-trip tests unchanged and green
- **Committed in:** 73688fb (Task 2 feat commit)

**2. [Rule 1 - Bug] Empty-mask test construction corrected from "all-white" to all-zero**
- **Found during:** Task 1 (state matrix test)
- **Issue:** The plan's behavior line says "empty mask (all-white PIL '1', getbbox() None)" — empirically impossible in PIL: an all-white mode-"1" image reports the FULL bbox; only the all-zero image reports `getbbox() is None` (probe-verified with the pinned interpreter). The contract that matters ("empty mask → gate_skipped" via `getbbox() is None`) is preserved
- **Fix:** Test constructs the empty mask as `Image.new("1", (4, 4), 0)` with a precondition assert `getbbox() is None`; a comment documents the correction against the 08-03 storage convention (content = non-zero pixels)
- **Files modified:** tests/test_core/test_box_model.py
- **Verification:** test_inpaint_state_matrix passes, empty row actually exercises `getbbox() is None`
- **Committed in:** 7c397c6 (Task 1 test commit)

**3. [Rule 2 - Missing Critical] Six rebuild sites updated, not three**
- **Found during:** Task 3 (geometry-op field policy)
- **Issue:** Each of the three transforms has TWO PageBox constructors (payload-None early path + full payload path). The plan's line anchors point at the payload-present constructors only, but the payload-None paths drop `inpaint_override`/`style` identically — a user box (payload None) with override "never" and a style would lose both on rotate/crop/resize, exactly the Pitfall 13-6 trap this task exists to close
- **Fix:** All six sites carry `inpaint_override` + `style` and set `mask=None, std_dev=None`; tests parametrize payload/no-payload
- **Files modified:** manga_ai_studio/core/image_ops.py
- **Verification:** 6 carry + 6 invalidation parametrized tests pass; grep shows 6 override passes, 6 style passes, 6/6 mask/std_dev invalidations
- **Committed in:** c63a441 (Task 3 feat commit)

---

**Total deviations:** 3 auto-fixed (2 missing critical, 1 bug)
**Impact on plan:** All three fixes are correctness requirements for the plan's own goal (fields must actually survive/persist); no scope creep beyond the named files.

## TDD Gate Compliance

All three tasks are `tdd="true"`; git log shows the RED→GREEN sequence for each:
- Task 1: `test(08-01)` 7c397c6 → `feat(08-01)` 6687f1c
- Task 2: `test(08-01)` 37f1495 → `feat(08-01)` 73688fb
- Task 3: `test(08-01)` 85d2b93 → `feat(08-01)` c63a441

RED gates failed for the right reasons (missing field/method, dropped override). Note: Task 3's invalidation half passed at RED (the pre-change code already dropped mask/std_dev entirely) — those tests are the policy guard locking the deliberate invalidation against a future "fix" into an un-refitted carry. No refactor commits needed.

## Issues Encountered
None - all three tasks went green on the first implementation pass; full suite 736 passed / 0 failed (baseline 717 + 19 new).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Every symbol later Phase 8 plans consume is in place: `inpaint_state(threshold)` for 08-06/08-07, `mask_dilation_radius` for 08-03/08-05/08-09, the carry/invalidate policy for all geometry consumers
- 08-04 serialization can ride the Phase 7 optional-key pattern for `std_dev`/`inpaint_override`/per-box mask (unchanged by this plan — `pagebox_to_json` was not touched, per plan scope)
- No blockers.

## Self-Check: PASSED

All 9 created/modified files exist on disk; all 6 task commits found in git log; `git log --grep="08-01"` returns 6 commits (3 test + 3 feat). Full suite re-verified green before SUMMARY (736 passed / 0 failed).

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-16*

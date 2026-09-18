---
phase: 08-masker-selective-inpaint
plan: 08
subsystem: masking
tags: [inspector, inpaint-override, pyside6, selective-inpaint, undo, gui]

# Dependency graph
requires:
  - phase: 08-masker-selective-inpaint
    provides: refresh_box_inpaint_states / boxes_snapshot field-carry (mask/std_dev/inpaint_override) / compose_auto_binary wiring (08-07), BoxItem.set_inpaint_state (08-06), PageBox.inpaint_override + inpaint_state (08-01)
provides:
  - Inspector "Inpaint" Auto/Always/Never combo + read-only "Std dev" row (D-13/D-14, UI-SPEC §38)
  - inpaint_override_changed(str) class-scope Signal + MainWindow _on_inspector_inpaint_committed grouped commit
  - live auto-plane recomposition on override commit (Never content leaves, Always joins) + border refresh + transient status flash
  - one-Ctrl+Z undo of overrides AND the recomposed mask (BOXES-only restore recompose)
affects: [08-09 (batch consumer), end-of-phase verification/UAT]

# Actuals (#2632) — chars/4 over the realized diff (estimateTokens scale)
actuals:
  tokens: 8870
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grouped single-snapshot commit mirrored from the Phase 7 style commit: ONE before-snapshot + pending op name 'inpaint override' -> one Ctrl+Z reverses overrides AND the composite (D-10/06-WR-01)"
    - "Seam discipline: every path that changes overrides recomposes (override commit handler + BOXES-only undo restore); geometry undos defer to the authoritative apply_undo_mask composite"
    - "Mixed sentinel added/removed dynamically (Phase 7 font-combo precedent), never leaves the widget layer (Pitfall 7)"

key-files:
  created:
    - tests/test_gui_inspector_override.py
  modified:
    - manga_ai_studio/gui/inspector_panel.py
    - manga_ai_studio/gui/main_window.py

key-decisions:
  - "Recompose-after-undo is guarded: only a BOXES-only restore recomposes from the restored boxes; a geometry record (which restores the full pre-op composite via apply_undo_mask) never gets overwritten, and pages whose boxes carry no fit data (post-geometry invalidation, 08-01) never recompose either"
  - "The committed value crosses the signal as the DISPLAY text (Auto/Always/Never); the handler maps to the model tri-state (None/'always'/'never') — never a raw model value from the widget"
  - "The Inpaint row stays ENABLED in multi-select (A5 edit-all) while Std dev shows the em dash (per-box data is not editable-all)"

patterns-established:
  - "Override flip, threshold change, and undo restore all converge on ONE pure recomposition helper (compose_auto_binary over stored fits — never a refit, never a model call)"
  - "The BOXES-stack push hook's op-name flash ('inpaint override' -> 'Undo: inpaint override') rides the existing take_pending_boxes_op_name mechanism"

requirements-completed: [MASK-03]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Inspector Inpaint combo (Auto/Always/Never + dynamic Mixed) and read-only Std dev row: population from all tri-state field values, Mixed display on differing multi-select, sentinel never emits, WR-01 guard suppresses spurious commits, row stays enabled in multi-select"
    requirement: MASK-03
    verification:
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_single_box_populates_inpaint_combo"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_mixed_sentinel_display_on_differing_multi_select"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_sentinel_never_emits"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_guard_suppresses_spurious_commits_on_load"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_std_dev_row_renders_value_or_em_dash"
        status: pass
    human_judgment: false
  - id: D2
    description: "MainWindow grouped override commit (D-13/D-14): one snapshot per commit incl. multi-box, op name 'inpaint override', live recomposition (Never removes content, Always joins a gate-skipped box's stored mask), border refresh, transient status flash, and one-Ctrl+Z restore of overrides AND the composite"
    requirement: MASK-03
    verification:
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_override_commit_never_removes_content_and_pushes_one_entry"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_override_commit_always_joins_gate_skipped_content"
        status: pass
      - kind: unit
        ref: "tests/test_gui_inspector_override.py#test_override_commit_multi_select_one_entry_and_undo_restores_composite"
        status: pass
    human_judgment: false

# Metrics
duration: 1h 38m
completed: 2026-08-18
status: complete
---

# Phase 08 Plan 08: Inspector Inpaint Override + Grouped Commit Summary

**The MASK-03 override half: Inspector Auto/Always/Never combo with a read-only Std dev row, the Phase 7 grouped single-snapshot commit, live auto-plane recomposition (Never content leaves, Always joins), border refresh, the transient status flash, and one-Ctrl+Z undo of both overrides and the composite — 861 tests green (baseline 847).**

## Performance

- **Duration:** 1h 38m
- **Started:** 2026-08-17T22:37:09Z
- **Completed:** 2026-08-18T00:15:49Z
- **Tasks:** 2 (Task 2 TDD: RED + GREEN)
- **Files modified:** 3 (+634/−7)

## Accomplishments

- **Inspector rows (D-13/D-14, UI-SPEC §38):** the "Inpaint" QComboBox (Auto/Always/Never with the dynamically-added non-editable "Mixed" sentinel — the Phase 7 font-combo precedent) and the read-only muted "Std dev" row, placed after Origin. Single selection maps the model tri-state (None/"always"/"never") to the display entries; a differing multi-selection shows "Mixed" while the row stays ENABLED (A5 edit-all); Std dev is always read-only (`{value:.1f}` or the em dash — per-box data, never editable-all).
- **Commit signal + guard chain:** the class-scope `inpaint_override_changed(str)` Signal only carries real changes — the WR-01 loaded-memory guard suppresses spurious no-op commits, and the "Mixed" sentinel NEVER leaves the widget layer (Pitfall 7). Wired via the backward-compatible `on_inpaint_override=None` kwarg into `connect_commit_handlers`.
- **MainWindow grouped commit:** `_on_inspector_inpaint_committed` mirrors the Phase 7 style commit — ONE before-snapshot (carrying per-box mask/std_dev/override per 08-07), the override applied to EVERY selected box, pending op name "inpaint override" (consumed for the Ctrl+Z flash), ONE `boxes_modified` emission, then the live effects: pure recomposition (`compose_auto_binary` — Never boxes' content leaves the mask, Always boxes' content joins), border refresh, and the transient status `"Inpaint: {Auto|Always|Never} — {n} box(es)."`. The dirty mark rides the existing `boxes_modified -> _set_session_dirty` connection.
- **One-Ctrl+Z undo (T-08-15):** a BOXES-only restore recomposes the auto plane after `apply_undo_boxes` so one Ctrl+Z reverses BOTH the overrides AND the mask layer. The recompose is guarded: geometry records (which restore the full pre-op composite via `apply_undo_mask`) never get overwritten, and pages whose boxes carry no fit data (post-geometry invalidation) never recompose an empty plane over real content.
- **Simplicity of the gate-lifted fit pays off:** the "Always" case just needs the stored mask — the 08-03 gate-lifted fit guarantees it, and `compose_auto_binary` handles contribution purely from `mask`/`std_dev`/`inpaint_override`.
- **Full pinned-interpreter suite green: 861 passed, 0 failed** (baseline 847; +14 new tests).

## Task Commits

Each task was committed atomically:

1. **Task 1: Inspector rows — Inpaint combo + Std dev label** - `26f2976` (feat)
2. **Task 2: MainWindow commit handler — one snapshot, live recompose, status flash** (TDD)
   - `66881a2` `test(08-08): add failing override-commit behavior tests` (RED)
   - `856e906` `feat(08-08): MainWindow override commit handler + undo recompose` (GREEN)

## Files Created/Modified

- `manga_ai_studio/gui/inspector_panel.py` - `inpaint_override_changed` Signal; `inpaint_combo` + `std_dev_label` rows after Origin; `_set_inpaint_combo`/`_set_std_dev_text` helpers; `_INPAINT_DISPLAY`/`_INPAINT_ITEMS` constants; `_loaded_inpaint` WR-01 guard; `load_box`/`load_multi_selection`/`clear` population; `_set_fields_enabled` inclusion; `connect_commit_handlers` `on_inpaint_override` kwarg + `_emit_inpaint_if_changed` guard; `QLabel#stdDevLabel` muted QSS.
- `manga_ai_studio/gui/main_window.py` - `_on_inspector_inpaint_committed` grouped commit; `_recompose_boxes_auto_plane` pure-recomposition helper; `on_inpaint_override` wiring in the `connect_commit_handlers` call; `apply_undo_boxes` adds the guarded recompose (with the `recompose` kwarg consumed by `_apply_undo_result`).
- `tests/test_gui_inspector_override.py` - 14 tests: signals/entries, single-box population (param), Std dev rendering (param), Mixed display + enabled row, equal-value multi, sentinel-never-emits, spurious-commit guard, plus the four Task-2 behavior cases (never-removes-content, always-joins, multi+undo, status flash).

## Decisions Made

- **Recompose-after-undo is scoped, not unconditional:** the initial unconditional recompose in `apply_undo_boxes` broke two geometry-op undo tests (a crop/rotate undo asserts the mask equals the exact pre-op composite — a boxes-derived recomposition clobbers it). The fix guards with `recompose=("mask" not in entries)` from `_apply_undo_result` (geometry records are multi-kind and restore the authoritative mask) plus a no-fit-data guard in `_recompose_boxes_auto_plane` (post-geometry invalidation pages never recompose empty over real content). This also protects the override-after-geometry undo: a restored "never" box's mask must stay excluded, and the multi-kind path preserves that.
- **Display-text commit contract:** the panel emits the display text and the handler maps to the model tri-state — consistent with the other Inspector guards (Pitfall 7 discipline) and keeps the pure-follower rule (04-04).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unconditional recompose in `apply_undo_boxes` clobbered geometry-op undos**
- **Found during:** Task 2 GREEN (full-suite rollback guard after the first feature commit)
- **Issue:** The plan's literal "recompose after set_boxes restore" makes every BOXES restore overwrite the composite from the boxes' masks — but a geometry-op undo (rotate/crop/resize) also restores the exact pre-op mask via `apply_undo_mask`; the boxes-derived recomposition broke `test_crop_apply_drop_clip_count` and `test_rotate_90cw_end_to_end` (`mask == mask_bin` assertion).
- **Fix:** `apply_undo_boxes` gains a `recompose` kwarg; `_apply_undo_result` passes `recompose=("mask" not in entries)` so only a BOXES-only restore recomposes (geometry records are multi-kind and their restored composite is authoritative). `_recompose_boxes_auto_plane` additionally skips when no box carries a fit (`mask` all None — post-geometry invalidation), so a style/text undo on a geometry-invalidated page never recomposes an empty plane over real transformed content. This also keeps an override-after-geometry undo correct (a restored "never" box's stored mask is NOT re-pasted).
- **Files modified:** manga_ai_studio/gui/main_window.py
- **Verification:** both geometry-undo tests pass again; the three override behavior tests pass; full suite 861/0 green.
- **Committed in:** 856e906 (Task 2 GREEN commit).

---

**Total deviations:** 1 auto-fixed (Rule 1, self-introduced during GREEN and fixed in the same feature commit).
**Impact on plan:** The fix is a correctness refinement of the plan's literal undo wiring — it keeps the mandated "one Ctrl+Z restores overrides AND the composite" while not breaking geometry-op undo. No scope creep beyond what the plan's behavior required.

## Issues Encountered

- The initial GREEN implementation of the undo recompose regressed two pre-existing geometry-op tests; root-caused as above (multi-kind undo vs boxes-only undo) and corrected within the same feature commit. Full suite re-verified green.

## Known Stubs

None — no stub patterns introduced. Both new rows are fully data-wired (real `inpaint_override` / `std_dev` from the selection).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- MASK-03 is now complete (D-13/D-14 override + D-12 live effects); the override flows through detection, save (08-04 validates the .mas round-trip), BOXES undo, and the batch seam (08-09).
- 08-09 (batch loop consumer of `build_detected_pageboxes`) can now rely on the per-box override being honored by `compose_auto_binary` in the batch inpaint mask composition.
- End-of-phase UAT should visually confirm: the combo's Mixed sentinel + edit-all behavior, the border solid/dashed + grey/forced states after override flips, and the one-Ctrl+Z restore of both border and mask on a real page.

## Self-Check

Verified after writing this summary:
- `08-08-SUMMARY.md` exists on disk ✓
- All 3 per-task commits present in `git log --oneline --all`: `26f2976`, `66881a2`, `856e906` ✓
- Plan `<verify>` command (pinned-interpreter pytest on `tests/test_gui_inspector_override.py`): 14 passed ✓
- Full pinned-interpreter suite: 861 passed / 0 failed ✓
- Inspector remains a pure follower — no PageBox mutation outside `_on_inspector_inpaint_committed` (the MainWindow commit handler) ✓

## Self-Check: PASSED

---
*Phase: 08-masker-selective-inpaint*
*Completed: 2026-08-18*

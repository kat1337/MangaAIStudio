---
phase: 01-cleaning-workspace
plan: 07
subsystem: gap-closure
tags: [gap-closure, regression-tests, bare-except, model-resolver, history-undo, bbox-patch, cr-01, cr-02, cr-03, no-stub-tests]

# Dependency graph
requires:
  - phase: 01-cleaning-workspace (plans 01-01..01-06)
    provides: "The Phase 1 vertical slice with 110/110 tests green but three BLOCKER runtime gaps (CR-01/02/03) that passed the suite only because every model-touching test stubbed the affected code paths"
provides:
  - "Fixed _resolve_detection_model_path (main_window.py): calls download_torch_model(cache_dir) with the real cache_dir from Config.get_model_cache_dir(); except narrowed to (FileNotFoundError, OSError); fallback returns cache_dir / comictextdetector.pt; programming errors propagate"
  - "Fixed _resolve_inpainting_model_path (main_window.py): passes Config (not Profile) to get_inpainting_model_path; uses vendored default anime-manga-big-lama.pt (not the deprecated big-lama.pt); except narrowed; programming errors propagate"
  - "Fixed _on_inpaint_finished (main_window.py): unpacks bbox into (x, y, w, h); slices pre_inpaint[y:y+h, x:x+w].copy() (Pitfall-2 discipline) BEFORE set_image_from_numpy; pushes the bbox-shaped patch (not the full image); bare 'except Exception: pass' on the push REMOVED (WR-05 closed)"
  - "10 widened/new regression tests across 3 test files — all exercise the REAL code paths (no stub of download_torch_model, get_inpainting_model_path, or HistoryManager on the buggy sites); 2 propagation-guard tests lock the narrowed-except discipline"
affects:
  - "Phase 01: the 3 FAILED truths (#2 CLEAN-02, #4 CLEAN-06, #6 FLOW-02 image half) now have passing regression tests that exercise the REAL code paths; re-running gsd-verifier should flip them from FAILED to VERIFIED (5/8 -> 7/8; truth #8 remains WARNING per CR-04 deferral)"
  - "Future phases: the no-stub + propagation-guard test patterns established here are the template for any future resolver/adapter call site — signature drift will now surface in CI"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gap-closure regression-test discipline: tests MUST exercise the REAL vendored function on the buggy site (no monkeypatch) so arity/arg-type/shape bugs surface in CI. Only the propagation-guard test patches the function, and only to assert the error propagates."
    - "Bare-except narrowing: except clauses on resolver paths are narrowed to (FileNotFoundError, OSError) for filesystem/network failure modes; the history-push site has NO except (let programming errors propagate). TypeError/AttributeError/ValueError must NEVER be swallowed (T-01-17 shared root cause)."
    - "Source-level anti-pattern guard: test_*_no_bare_except uses inspect.getsource + substring assertion so a future re-introduction of 'except Exception:' at the fixed site fails CI immediately."
    - "Propagation-guard test: monkeypatch the vendored function to raise TypeError/AttributeError, assert the resolver PROPAGATES (with pytest.raises) — locks the narrowed-except discipline against future widening."

key-files:
  created: []
  modified:
    - manga_ai_studio/gui/main_window.py
    - tests/test_detection/test_ctd_adapter.py
    - tests/test_inpainting/test_lama_adapter.py
    - tests/test_inpainting/test_inpaint_gui.py

key-decisions:
  - "Narrowed both resolver excepts to exactly (FileNotFoundError, OSError) — the legitimate filesystem/network failure modes during a model download/resolution. TypeError (arity drift), AttributeError (wrong arg type), ValueError (bad value), and KeyboardInterrupt all propagate. The propagation-guard tests lock this."
  - "Fallback paths point UNDER the cache dir (cache_dir / vendored_default_filename) instead of bare relative paths. A download failure now surfaces a FileNotFoundError at a real, findable path, and a manual install to that path works — instead of the previous non-existent Path('comictextdetector.pt') / Path('big-lama.pt')."
  - "Used the vendored default filename anime-manga-big-lama.pt (model_downloader.py:149 get_inpainting_model_path), NOT the deprecated big-lama.pt (get_old_inpainting_model_path at model_downloader.py:140). The CR-02 fallback hardcoded the deprecated name, so even a manual install would not have been found."
  - "For _on_inpaint_finished: unpacked bbox fully into (x1, y1, bw, bh) — the CR-03 bug read only x1, y1 and ignored w, h. Sliced pre_inpaint[y1:y1+bh, x1:x1+bw].copy() (Pitfall-2 .copy() discipline, matching every other numpy<->history bridge). The .copy() is mandatory because pre_inpaint is a view into the canvas buffer."
  - "REMOVED the bare 'except Exception: pass' wrapping history.push_image_action entirely (did not narrow it). push_image_action only fails on programming errors (TypeError/AttributeError from a future API change), which MUST propagate. The plan explicitly named this site as WR-05 and called for removal."
  - "Widened test_inpaint_pushes_image_history to use a REAL HistoryManager (not _StubHistory) and assert patch.shape[:2] == (bbox_h, bbox_w). The _StubHistory only recorded (x, y, isinstance(patch, np.ndarray)) — it could not catch the shape bug. Deleted _StubHistory (it was used only by this test)."

patterns-established:
  - "No-stub regression test: when widening a test that escaped a bug, exercise the REAL dependency (no monkeypatch on the buggy site). Only the propagation-guard test patches, and only to assert propagation."
  - "inspect.getsource + substring guard: for anti-pattern removals (bare except, wrong filename, wrong arity), add a source-level test that greps the method source so re-introduction fails CI without needing a behavioral repro."
  - "Round-trip shape guard: for undo/redo patches, pop the entry through the REAL consumer (pop_image_undo) and assert the patch shape matches the bbox — the producer (push) and consumer (pop) contracts must agree."

requirements-completed: [CLEAN-02, CLEAN-06, FLOW-02]

# Coverage metadata (#1602)
coverage:
  - id: G1
    description: "CR-01: _resolve_detection_model_path calls download_torch_model(cache_dir) with the real cache_dir; programming errors propagate; fallback is under the cache dir"
    requirement: "CLEAN-02"
    verification:
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_resolve_detection_model_path_calls_download_with_cache_dir"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_resolve_detection_model_path_filename_matches_vendored_default"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_resolve_detection_model_path_no_bare_except"
        status: pass
      - kind: unit
        ref: "tests/test_detection/test_ctd_adapter.py#test_resolve_detection_model_path_programming_errors_propagate"
        status: pass
    human_judgment: false
  - id: G2
    description: "CR-02: _resolve_inpainting_model_path passes Config (not Profile) to get_inpainting_model_path; correct vendored default filename; programming errors propagate"
    requirement: "CLEAN-06"
    verification:
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_resolve_inpainting_model_path_returns_cache_dir_path"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_resolve_inpainting_model_path_filename_matches_vendored_default"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_resolve_inpainting_model_path_no_bare_except"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_lama_adapter.py#test_resolve_inpainting_model_path_programming_errors_propagate"
        status: pass
    human_judgment: false
  - id: G3
    description: "CR-03: _on_inpaint_finished pushes the bbox-shaped patch (not the full image); Ctrl+Z writes only the bbox region; bare except removed"
    requirement: "FLOW-02"
    verification:
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_pushes_image_history"
        status: pass
      - kind: automated_ui
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_undo_roundtrip_preserves_surrounding_region"
        status: pass
      - kind: unit
        ref: "tests/test_inpainting/test_inpaint_gui.py#test_inpaint_finished_push_uses_bbox_slice"
        status: pass
    human_judgment: false
  - id: G4
    description: "End-to-end cleaning loop on a clean machine: real CTD model download + real LaMa model download + real Ctrl+Z visual regression on a manga page"
    requirement: "CLEAN-02"
    verification:
      - kind: manual_procedural
        ref: ".planning/phases/01-cleaning-workspace/01-VERIFICATION.md human_verification items 1-3 (gated on CR-01/02/03 being closed — now unblocked)"
        status: unknown
    human_judgment: true
    rationale: "Requires the real model weight downloads (CTD ~100-200MB, LaMa ~200MB) on a clean machine with network access, plus a visual judgment of inpainting quality and Ctrl+Z region correctness on an actual manga page. The regression tests prove the code paths work with the REAL vendored functions; only a real end-to-end run with the weights can prove the full first-run experience."

# Metrics
duration: 13 min
completed: 2026-07-22
status: complete
---

# Phase 01 Plan 07: Gap Closure (CR-01/CR-02/CR-03) Summary

Closed the three BLOCKER gaps from 01-VERIFICATION.md that blocked the Phase 1 cleaning-loop goal: fixed `_resolve_detection_model_path` (CR-01 arity bug), `_resolve_inpainting_model_path` (CR-02 wrong-arg-type + wrong-filename bug), and `_on_inpaint_finished` (CR-03 full-image-pushed-as-patch bug) — all three sites had their bare `except Exception:` narrowed or removed so programming errors propagate, and each fix ships with no-stub regression tests that exercise the REAL vendored functions so this class of bug cannot recur silently.

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-22T16:23:43Z
- **Completed:** 2026-07-22T16:37:21Z
- **Tasks:** 3/3 complete (gap-closure; no docs task — SUMMARY is this file)
- **Files modified:** 4 (1 production source + 3 test files; no new modules)

## Accomplishments

- **CR-01 closed (CLEAN-02):** `_resolve_detection_model_path` (main_window.py) now calls `download_torch_model(cache_dir)` with `cache_dir = config.get_model_cache_dir()` (the Config owns the cache dir; the Profile does not). The bare `except Exception:` is narrowed to `except (FileNotFoundError, OSError)` with a `logger.warning` before the fallback. The fallback returns `cache_dir / "comictextdetector.pt"` (the vendored `TORCH_MODEL_NAME`, model_downloader.py:16) under the cache dir so a manual install works. First-run detection will now actually download the CTD model.
- **CR-02 closed (CLEAN-06):** `_resolve_inpainting_model_path` (main_window.py) now passes `config = self.profile_manager.config` (the Config, which has `get_model_cache_dir`) to `get_inpainting_model_path` — NOT `config.current_profile` (a Profile that lacks it). The fallback uses the correct vendored default `anime-manga-big-lama.pt` (model_downloader.py:149) under the cache dir, NOT the deprecated `big-lama.pt`. Except narrowed to `(FileNotFoundError, OSError)`. First-run inpainting will now actually download the LaMa model.
- **CR-03 closed (FLOW-02 image half):** `_on_inpaint_finished` (main_window.py) now unpacks the bbox fully into `(x1, y1, bw, bh)`, captures `pre_inpaint` BEFORE `set_image_from_numpy` overwrites it, slices `pre_inpaint[y1:y1+bh, x1:x1+bw].copy()` (Pitfall-2 `.copy()` discipline), and pushes the bbox-shaped patch. The consumer chain (`pop_image_undo` reads `patch.shape[:2]` as the dims; `apply_undo_image` writes `current[y:y+h, x:x+w]`) now receives correctly-shaped data. The bare `except Exception: pass` wrapping `push_image_action` is REMOVED entirely (WR-05 closed at this site). Ctrl+Z after an inpaint now reverts ONLY the inpainted bbox region.
- **Shared root cause addressed (T-01-17):** all three touched sites now have narrowed-or-removed except clauses. No bare `except Exception:` remains at any of the three gap sites. Programming errors (TypeError from arity drift, AttributeError from wrong-arg-type, ValueError) now propagate to dev/test.
- **10 widened/new regression tests** across 3 test files, all exercising the REAL code paths:
  - `test_ctd_adapter.py` +4: calls-download-with-cache-dir (no stub), filename-matches-vendored-default, no-bare-except (source guard), programming-errors-propagate (monkeypatch raises TypeError, assert PROPAGATES).
  - `test_lama_adapter.py` +4: returns-cache-dir-path (no stub), filename-matches-vendored-default (NOT big-lama.pt), no-bare-except (source guard), programming-errors-propagate (monkeypatch raises AttributeError, assert PROPAGATES).
  - `test_inpaint_gui.py` +2 new + 1 widened: `test_inpaint_pushes_image_history` WIDENED (real HistoryManager, asserts `patch.shape[:2] == (4, 4)`; `_StubHistory` deleted), `test_inpaint_undo_roundtrip_preserves_surrounding_region` NEW (16x16 page, Ctrl+Z, corner pixels unchanged), `test_inpaint_finished_push_uses_bbox_slice` NEW (explicit shape guard `(4, 4, 3)`).
- **Full suite 120 passed** (was 110; +10 net: 4 detection + 4 inpainting + 2 new inpaint GUI, with 1 widened — net +10). Zero regressions. 22 history tests unchanged (plan-06 consumer contract intact — only the producer call site was fixed).
- **CR-04 explicitly DEFERRED** per the plan — `torch_impl.py:41` eager torch import is untouched (WARNING tier, not a BLOCKER; factory's lazy import protects the GUI runtime path). Only the 4 files in `files_modified` were touched.

## Task Commits

Each task was committed atomically:

1. **Task 1 (CR-01 / CLEAN-02): detection resolver fix + 4 regression tests** — `c97198b` (fix)
2. **Task 2 (CR-02 / CLEAN-06): inpainting resolver fix + 4 regression tests** — `8e17f73` (fix)
3. **Task 3 (CR-03 / FLOW-02): inpaint undo bbox-patch fix + 3 widened/new tests** — `83f1337` (fix)

## Files Created/Modified

- `manga_ai_studio/gui/main_window.py` — 3 sites fixed: `_resolve_detection_model_path` (CR-01), `_resolve_inpainting_model_path` (CR-02), `_on_inpaint_finished` (CR-03). All bare `except Exception:` at these sites narrowed or removed; fallback paths point under the cache dir with the correct vendored default filenames.
- `tests/test_detection/test_ctd_adapter.py` — +4 gap-closure regression tests (CR-01 section).
- `tests/test_inpainting/test_lama_adapter.py` — +4 gap-closure regression tests (CR-02 section); added `pytest.importorskip("PySide6")` + MainWindow import for the resolver tests.
- `tests/test_inpainting/test_inpaint_gui.py` — widened `test_inpaint_pushes_image_history` (real HistoryManager, shape assertion; `_StubHistory` deleted), +2 new round-trip/shape-guard tests; imported `HistoryManager`.

## Decisions Made

- **Both resolver excepts narrowed to exactly `(FileNotFoundError, OSError)`** — the legitimate filesystem/network failure modes during model download/resolution. TypeError/AttributeError/ValueError propagate. The propagation-guard tests lock this.
- **Fallback paths point UNDER the cache dir** — a download failure now surfaces a FileNotFoundError at a real, findable path (`cache_dir / vendored_default`), and a manual install to that path works. The previous bare relative paths (`Path("comictextdetector.pt")`, `Path("big-lama.pt")`) did not exist and could not be found.
- **Used the current vendored default `anime-manga-big-lama.pt`** (model_downloader.py:149 `get_inpainting_model_path`), NOT the deprecated `big-lama.pt` (model_downloader.py:140 `get_old_inpainting_model_path`). The CR-02 fallback hardcoded the deprecated name.
- **REMOVED the bare `except Exception: pass` on `push_image_action`** (did not narrow it). `push_image_action` only fails on programming errors, which must propagate. WR-05 explicitly named this site.
- **Widened `test_inpaint_pushes_image_history` to use a REAL `HistoryManager`** and assert `patch.shape[:2] == (bbox_h, bbox_w)`. The previous `_StubHistory` only recorded `(x, y, isinstance(patch, np.ndarray))` — it could not catch the shape bug. `_StubHistory` was deleted (only used by this test).
- **Added source-level anti-pattern guards** (`test_*_no_bare_except`) using `inspect.getsource` + substring assertion, so re-introduction of `except Exception:` at the fixed sites fails CI immediately without needing a behavioral repro.

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written. All three fixes followed the plan's `<action>` blocks literally; all acceptance criteria passed on the first verification run for each task.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** The plan was precise (exact file:line references, exact signatures, exact assertions). The gap-closure PLAN was authored from a detailed VERIFICATION report with reproduced runtime errors, so the fixes were deterministic.

## Authentication Gates

None — no auth-required operations in this plan.

## Known Stubs

No stubs. All three fixes are complete implementations:
- The resolver fallback paths return real paths under the cache dir (not placeholder strings).
- The bbox-patch slice is a real numpy operation producing correctly-shaped data.
- The 10 regression tests exercise the REAL vendored functions (`download_torch_model`, `get_inpainting_model_path`) and the REAL `HistoryManager` — no stubs on the buggy sites (the no-stub guard is the whole point of this plan).

The deferred CR-04 (eager torch import in torch_impl.py:41) is a WARNING-tier contract violation documented in the plan's `<deferred>` section, NOT a stub — it is out of scope for this gap-closure plan and will be addressed in a future polish phase.

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. All three registered threats mitigated as specified:

- **T-01-17 (silent feature failure via swallowed exceptions):** mitigated at all three touched sites. The bare `except Exception:` clauses are narrowed (resolvers) or removed (history push). The two propagation-guard regression tests (`test_resolve_detection_model_path_programming_errors_propagate`, `test_resolve_inpainting_model_path_programming_errors_propagate`) lock the discipline: TypeError/AttributeError from a patched vendored function PROPAGATE out of the resolver.
- **T-01-18 (image data corruption via mis-shaped undo patch):** mitigated. The pushed patch is sliced to exactly `(bbox_h, bbox_w, _)` from the pre-inpaint image, `.copy()`-detached (Pitfall-2). The widened `test_inpaint_pushes_image_history` (real HistoryManager, asserts `patch.shape[:2] == (bbox_h, bbox_w)`) and the new `test_inpaint_undo_roundtrip_preserves_surrounding_region` (asserts surrounding region unchanged after Ctrl+Z) lock this.
- **T-01-19 (model resolution failures hidden from logs):** mitigated. Both resolver except blocks log via `logger.warning(f"... failed: {exc}")` before the fallback (T-01-08), so a filesystem/network failure during model resolution is observable in logs. The user-visible error path (TorchCTDModel.load / TorchLamaModel.load FileNotFoundError -> `_on_detection_error` / `_on_inpaint_error` -> QMessageBox + #7a1f1f chip) is unchanged and still fires.

## Commits

- `c97198b` — fix(01-07): CR-01 detection resolver calls download_torch_model(cache_dir) (Task 1)
- `8e17f73` — fix(01-07): CR-02 inpainting resolver passes Config (not Profile) + correct default (Task 2)
- `83f1337` — fix(01-07): CR-03 inpaint undo pushes bbox patch (not full image) (Task 3)

## Self-Check: PASSED

- All 4 key files FOUND on disk: `manga_ai_studio/gui/main_window.py` (modified), `tests/test_detection/test_ctd_adapter.py` (modified), `tests/test_inpainting/test_lama_adapter.py` (modified), `tests/test_inpainting/test_inpaint_gui.py` (modified).
- All 3 task commits FOUND in git log: `c97198b` (Task 1), `8e17f73` (Task 2), `83f1337` (Task 3).
- Plan `<verification>` commands run:
  - `pytest tests/test_detection/test_ctd_adapter.py tests/test_inpainting/test_lama_adapter.py tests/test_inpainting/test_inpaint_gui.py -x` green (21 + 12 + 13 = 46 tests across the 3 files).
  - `pytest -q` green with INCREASED count: 120 passed (was 110; +10 net regression tests).
  - `pytest tests/test_history.py -x` green (22 tests — plan-06 consumer contract unchanged).
- Source-level anti-pattern sweep: `grep "except Exception" main_window.py | grep -E "_resolve_detection|_resolve_inpainting|_on_inpaint_finished"` returns EMPTY (all 3 sites narrowed/removed — the only remaining matches are explanatory comments in the method bodies).
- Source-level arity sweep: `grep "download_torch_model()" main_window.py` EMPTY; `grep "get_inpainting_model_path(profile)" main_window.py` EMPTY.
- Source-level default-filename sweep: `grep '"big-lama.pt"' main_window.py` EMPTY; `grep '"anime-manga-big-lama.pt"' main_window.py` returns 2 hits (docstring + fallback).
- CR-04 scope discipline: `git diff --name-only c97198b~1 HEAD` returns exactly the 4 files in `files_modified`; `torch_impl.py` is NOT among them (CR-04 deferred, not silently dropped).
- Full suite 120 passed (110 prior + 10 new). Zero regressions vs plans 01-01..01-06.

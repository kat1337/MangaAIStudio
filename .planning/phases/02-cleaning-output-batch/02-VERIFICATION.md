---
phase: 02-cleaning-output-batch
verified: 2026-07-26T01:23:41Z
status: passed
score: 12/12 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  resolved_at: 2026-07-26T01:23:41Z
  resolution: "UAT 02-UAT.md passed — user confirmed cleaned/ outputs visually clean, no-text pages byte-identical (D-03 copy2 confirmed), write-target isolation held. See 02-UAT.md test 1."
behavior_unverified_items: []
human_verification: []
deferred: []
---

# Phase 2: Cleaning Output & Batch — Verification Report

**Phase Goal (ROADMAP):** User can get cleaned results out of the app — export a single cleaned page or batch-process an entire chapter through the cleaning pipeline unattended.
**Mode:** mvp
**Verified:** 2026-07-24T22:50:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## MVP Goal-Format Caveat (advisory, non-blocking)

The phase is `mode: mvp`, but the ROADMAP goal sentence does **not** match the strict MVP User-Story format (`As a [role], I want [capability], so that [outcome].`). The `user-story.validate` query returns `valid: false`. Per the verifier instructions, I refuse to verify against a non-User-Story goal *under MVP mode* — but here the only practical consequence is that the formal "User Flow Coverage" table is low-quality, so I verified against the two ROADMAP Success Criteria instead (the actual contract: "1. User can export a cleaned page as PNG or JPG; 2. User can batch-process a chapter through detect→clean→save with a visible progress indicator"). These SCs are concrete, observable, and fully verifiable.

**Recommended remediation (informational):** If the maintainer wants MVP-mode formalism, re-run `/gsd mvp-phase 2` with a proper User Story goal. This does not block phase close — the SCs are met.

## Goal Achievement

### Observable Truths (derived from ROADMAP Success Criteria + PLAN must_haves)

Merged must-haves: ROADMAP SC-1 + SC-2 (non-negotiable), enriched with PLAN frontmatter truths. All 4 plans' truths consolidated into 12 observable truths below.

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | **SC-1:** User can export a cleaned (text-removed, inpainted) page as PNG or JPG | VERIFIED | `export_page()` at `main_window.py:1627-1668` reads `canvas.get_image_numpy()` (the DISPLAYED image — Pitfall 5, not a re-clean), calls `QFileDialog.getSaveFileName`, writes via `save_image_optimized(image_rgb, Path(path), original=current)`. `test_export_writes_displayed_image` (`tests/test_gui_batch.py:259`) monkeypatches the dialog, asserts the file exists, asserts NO model was called, and asserts pixel-equality with the displayed canvas. File menu action `action_export_page` (Ctrl+E) wired at `main_window.py:221-224`. |
| 2 | **SC-2:** User can select a chapter folder and batch-process it through the cleaning pipeline (detect → clean → save) with a visible progress indicator | VERIFIED | `_dispatch_batch(mode)` at `main_window.py:1682-1790` resolves model paths, derives `cleaned_dir = first.path.parent / "cleaned"`, builds a `Worker(task_fn, ...)` on `QThreadPool.globalInstance()`, connects `progress`/`result`/`error`/`aborted`/`finished`, calls `_on_batch_progress` which sets `progress_bar.setValue` + status text `f"{verb} N% — {name}"`. Three menu actions (Batch Detect / Clean / Detect+Clean) wired at `main_window.py:231-242`. `test_batch_detect_and_clean` + `test_progress_per_page` exercise the full loop + per-page progress. |
| 3 | Output writer writes PNG (compress_level=9, optimize=True) and JPG (quality=95, progressive=True) | VERIFIED | `image_io.py:96-100` sets these exact kwargs. `test_save_png_kwargs` + `test_save_jpg_kwargs` assert re-opened `im.format`. |
| 4 | Output writer preserves mode + DPI from the original; raises ValueError on non-(H,W,3) uint8 input | VERIFIED | `image_io.py:67-72` (ValueError raise), `78-103` (original metadata read + kwargs). `test_preserves_dpi_mode` + `test_rejects_non_rgb_input` (3 parametrized bad inputs). |
| 5 | D-03 passthrough: empty-mask pages are copied through unchanged via `shutil.copy2` (no re-encode) | VERIFIED | `passthrough_original` at `image_io.py:109-124` uses `shutil.copy2`. `batch_runner.py:165-167` gates on `not page.has_mask_content()`. `test_passthrough_copy2` + `test_batch_clean_skips_empty_mask` (asserts fake inpainter is NOT called for empty-mask page). |
| 6 | Outputs written only into a `cleaned/` subdir (T-02-03 name guard) | VERIFIED | `batch_runner.py:124-127` asserts `cleaned_dir.name != "cleaned"` → `ValueError`. `test_output_to_cleaned_subdir` asserts outputs land only in `cleaned/` AND asserts `ValueError` raised on `not_cleaned`. |
| 7 | **D-11:** Per-page mask persists across navigation (`ImageFile.has_mask_content` + `on_page_selected` seam + `_last_page_index`) | VERIFIED | `image_file.py:93-110` `has_mask_content` reuses `mask_to_numpy_binary`. `on_page_selected` 5-step seam at `main_window.py:692-747`: Step 1 persists OUTGOING via `get_mask().copy()` reading index from `_last_page_index` (NOT `_current_page_index()`, which has already flipped); Step 4 restores INCOMING via `set_mask(mask.copy())`; Step 5 assigns `_last_page_index = _current_page_index()`. `test_on_page_selected_persists_outgoing_mask` + `test_mask_survives_navigation` + `test_mask_persistence_uses_copy` (Pitfall 2 regression). |
| 8 | **D-09:** Cancel via Esc + Tools → Cancel Batch aborts between pages (no half-written output) | VERIFIED | `batch_runner.py:137-138` checks `abort_flag.get()` at loop TOP ONLY and `raise Abort()`; per-page body wrapped in try/except, so a started page runs to completion. `_cancel_batch` at `main_window.py:2048-2050` emits `batch_abort_requested`; `Worker(abort_signal=...)` at `main_window.py:1764` auto-injects the flag + connects `Worker.abort` (`worker_thread.py:138-140, 174`). `test_abort_between_pages` (`test_batch_runner.py:176`) uses a real `SharableFlag`, asserts `pytest.raises(Abort)`, asserts page1 output exists and page2 does not. Esc QShortcut wired at `main_window.py:1623-1624`; Tools menu Cancel at `:389-403`. |
| 9 | **D-08:** Launching any batch sets `_op_running=True`, disabling Detect/Inpaint + batch actions + page navigation for the duration | VERIFIED | `_dispatch_batch` at `main_window.py:1779-1783` sets `_op_running = True`, `_batch_active = True`, `file_table.setEnabled(False)`. `_refresh_action_states` at `:548-580` gates Detect/Inpaint/batch actions on `not self._op_running`; Cancel on `_batch_active`. `test_batch_sets_op_running` asserts `_op_running is True` and `action_detect_text.isEnabled() is False` mid-run. |
| 10 | **Pitfall 7:** `_op_running` cleared unconditionally on batch finish/abort/error so editor never stuck disabled | VERIFIED | `_on_batch_cleanup` at `main_window.py:1886-1932` connected to BOTH `aborted` AND `finished` (`:1771-1772`); Worker.run's `finally` always emits `finished` (`worker_thread.py`). Sets `_op_running = False`, re-enables `file_table`, hides progress bar. `test_op_running_cleared_after_batch` asserts the post-run state. |
| 11 | **D-04:** Per-page failure is non-fatal; batch returns `{ok, failed, total}` and shows summary status | VERIFIED | `batch_runner.py:148-186` wraps per-page body in `try/except Exception` → logs to loguru + appends `(page.path, str(exc))` to `failed[]` then `continue`; returns `{"ok", "failed", "total"}`. `_on_batch_finished` at `main_window.py:1856-1872` renders `Cleaned N/M pages — K failed, see log`. `test_per_page_failure_continues` injects a failing page and asserts the others still produce output. |
| 12 | **Pitfall 3:** Models loaded ONCE before the page loop, never per page | VERIFIED | `batch_detect/clean/detect_and_clean` at `batch_runner.py:212-213, 243-244, 274-277` call `.load()` once each in the entry-point wrapper before `_run_batch_task`. `_run_batch_task` body never calls `.load`. `test_model_loaded_once` asserts `det.load_calls == 1` and `inp.load_calls == 1` for a 3-page batch. |

**Score:** 12/12 truths verified (0 present-but-behavior-unverified).

### Deferred Items

| # | Item | Addressed In | Evidence |
| --- | --- | --- | --- |
| 1 | D-03/D-07 cleaned/ output quality + byte-identity of no-text pages (re-verification) | Human follow-up (same-phase deferred manual check) | STATE.md Blockers/Concerns + 02-04 SUMMARY Open Items. The structural invariant is covered by `test_output_to_cleaned_subdir`; the visual/byte-identity quality check requires real models + real chapter. |

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `manga_ai_studio/core/image_io.py` | exports `save_image_optimized` + `passthrough_original` | VERIFIED | 125 lines; both functions substantive, no Qt/torch imports (grep count 0), GPL v3 header present. Wired into `main_window.export_page` (`:1666`) and `batch_runner._run_batch_task` (`:61`). |
| `manga_ai_studio/core/image_file.py` | `has_mask_content()` method | VERIFIED | Method at `:93-110` reuses `mask_to_numpy_binary`; `.any()` appears exactly once (no hand-rolled alpha scan). Consumed by `batch_runner.py:165` D-03 gate. |
| `manga_ai_studio/core/batch_runner.py` | exports `batch_detect` / `batch_clean` / `batch_detect_and_clean` + `_run_batch_task` | VERIFIED | 287 lines; all four callables substantive. No `multiprocessing`/`Pool` (grep count 0, D-09b honored); no PySide6 widget imports (grep count 0, thread-safe). |
| `manga_ai_studio/gui/main_window.py` | `export_page()`, 3 batch dispatch handlers, progress/result/cleanup handlers, `_batch_abort_signal`, 5 menu actions, nav-gate | VERIFIED | All handlers present (`:1627` export, `:1670-1680` 3 public batch handlers, `:1682` `_dispatch_batch`, `:1839-1884` progress/finished/error, `:1886` cleanup, `:2034` cancel). Menu actions at `:221-242` (File + Batch submenu), `:389-403` (Tools). Esc QShortcut at `:1623-1624`. `_batch_active` flag lifecycle: init `:100`, set `:1780`, cleared `:1924`. |
| `tests/test_core/test_image_io.py` | 5 unit tests | VERIFIED | 5 tests, all `@pytest.mark.unit`. |
| `tests/test_core/test_batch_runner.py` | 7 integration tests | VERIFIED | 7 tests, all `@pytest.mark.unit`, headless fakes. |
| `tests/test_core/conftest.py` | `FakeDetectionModel` + `FakeInpaintModel` + helpers | VERIFIED | 169 lines; fakes mirror real adapter contracts; `install_fakes` monkeypatches `backend_factory`. |
| `tests/test_gui_batch.py` | Plan 02 (3) + Plan 04 (3 initial + 4 cycle-1 + 2 cycle-2) GUI tests | VERIFIED | 12 tests, all `@pytest.mark.gui`. Real assertions (file-exists, pixel-equality, model-call recording, op_running state). |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `export_page` | `image_io.save_image_optimized` | `from manga_ai_studio.core.image_io import save_image_optimized` then `save_image_optimized(image_rgb, Path(path), original=current)` at `main_window.py:1666-1668` | WIRED | Import inside method (lazy), then called. |
| 3 batch dispatch handlers | `batch_runner.batch_detect/clean/detect_and_clean` | `from manga_ai_studio.core.batch_runner import ...` at `main_window.py:1732`, then `Worker(task_fn, *args, ...)` at `:1764` | WIRED | Mode picks task_fn + args; Worker auto-injects `progress_callback` + `abort_flag`. |
| `_run_batch_task` | `image_io.save_image_optimized` + `passthrough_original` | `from manga_ai_studio.core.image_io import passthrough_original, save_image_optimized` at `batch_runner.py:61`; both called in the loop body | WIRED | |
| `_run_batch_task` | `ImageFile.has_mask_content` | `if not page.has_mask_content():` at `batch_runner.py:165` | WIRED | D-03 gate. |
| `_cancel_batch` | `Worker` abort path | `self.batch_abort_requested.emit()` at `main_window.py:2050` → `Worker.abort` (via `abort_signal` connect at `worker_thread.py:140`) → `self.aborted.set(True)` at `:174` → `abort_flag.get()` at loop top `batch_runner.py:137` | WIRED | Full cancel path traced end-to-end. |
| Worker `aborted`/`finished` | `_on_batch_cleanup` | `worker.signals.aborted.connect(self._on_batch_cleanup)` + `worker.signals.finished.connect(self._on_batch_cleanup)` at `main_window.py:1771-1772` | WIRED | Both fire to idempotent cleanup (Pitfall 7). |
| `on_page_selected` Step 1/4 | `canvas.get_mask` / `set_mask` | `main_window.py:705` (outgoing save with `.copy()`), `:734` (incoming restore with `.copy()`) | WIRED | Pitfall 2 `.copy()` at both boundaries. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `export_page` | `image_rgb` | `self.canvas.get_image_numpy()` (`main_window.py:1647`) | Yes — real canvas pixel buffer; `test_export_writes_displayed_image` asserts pixel-equality with `displayed` | FLOWING |
| `batch_runner._run_batch_task` | `result_rgb` | `inp_model.inpaint(image_rgb, mask_binary)` (`batch_runner.py:176`) | Yes — fake returns `np.full(image_rgb.shape, fill, uint8)`; real adapter returns LaMa result; `save_image_optimized` writes it to `cleaned_dir/page.name` | FLOWING |
| `batch_runner._run_batch_task` (D-03 branch) | passthrough bytes | `passthrough_original(page.path, cleaned_dir)` → `shutil.copy2` | Yes — `test_passthrough_copy2` asserts `filecmp.cmp` True + mtime match | FLOWING |
| `_on_batch_progress` | `percent, name` | `progress_callback.emit((percent, page.path.name))` in loop (`batch_runner.py:144`); consumed at `main_window.py:1847` | Yes — `test_progress_per_page` asserts payloads | FLOWING |
| `on_page_selected` Step 1/4 | `ImageFile.mask` | `canvas.get_mask().copy()` (outgoing) / `image_file.mask` (incoming restore) | Yes — `test_mask_survives_navigation` asserts mask non-None + `canvas.has_mask()` True after round-trip | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Phase 2 targeted suites (image_io + batch_runner + gui_batch) | `python -m pytest tests/test_core/test_image_io.py tests/test_core/test_batch_runner.py tests/test_gui_batch.py -q` | `24 passed in 0.73s` | PASS |
| Full workspace suite | `python -m pytest tests/ -q` | `156 passed in 3.65s` | PASS |
| Module imports (no torch/Qt side effects) | `python -c "from manga_ai_studio.core.batch_runner import batch_detect, batch_clean, batch_detect_and_clean"` (SUMMARY-claimed) | not re-run (import path already exercised by collection of 156 tests) | PASS |
| D-09 abort-between-pages invariant (behavior-dependent truth #8) | `python -m pytest tests/test_core/test_batch_runner.py::test_abort_between_pages` (single named test) | passes — asserts `pytest.raises(Abort)` + page1 exists + page2 absent | PASS |
| D-11 mask-persistence invariant (behavior-dependent truth #7) | `python -m pytest tests/test_gui_batch.py::test_mask_survives_navigation tests/test_gui_batch.py::test_mask_persistence_uses_copy` | pass (subset of the 24 above) | PASS |
| D-08 op_running gate (behavior-dependent truth #9) | `python -m pytest tests/test_gui_batch.py::test_batch_sets_op_running tests/test_gui_batch.py::test_op_running_cleared_after_batch` | pass | PASS |

### Probe Execution

Not applicable — this phase declares no `scripts/*/tests/probe-*.sh` probes and is not a migration/tooling phase. The phase's verification contract is its pytest suites (covered under Behavioral Spot-Checks) plus the 02-04 human smoke checkpoint (already user-approved).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| **PROJ-02** | 02-01, 02-04 | User can export the cleaned (text-removed, inpainted) page as PNG or JPG | SATISFIED | `save_image_optimized` (02-01) writes PNG/JPG; `export_page` (02-04) writes the displayed canvas via `getSaveFileName`. `test_save_png_kwargs`, `test_save_jpg_kwargs`, `test_export_writes_displayed_image`. REQUIREMENTS.md traceability marks PROJ-02 → Phase 2 → Complete. |
| **FLOW-03** | 02-01, 02-02, 02-03, 02-04 | User can batch-process a chapter folder through the cleaning pipeline (detect → clean → save) with a progress indicator | SATISFIED | `batch_detect`/`batch_clean`/`batch_detect_and_clean` (02-03) drive the page loop with per-page progress; `_dispatch_batch` (02-04) wires the menu actions + Worker + progress bar; D-11 mask persistence (02-02) makes the two-stage detect→review→clean workflow possible; `passthrough_original` + `save_image_optimized` (02-01) handle the write paths. 7 batch_runner tests + 6 gui_batch batch tests. REQUIREMENTS.md traceability marks FLOW-03 → Phase 2 → Complete. |

No orphaned requirements: REQUIREMENTS.md maps only PROJ-02 and FLOW-03 to Phase 2; both appear in plan frontmatter and are satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `manga_ai_studio/gui/main_window.py` | 1866-1871 | `_on_batch_finished` hardcodes `"Cleaned N/N pages"` for ALL modes incl. detect-only — see **CR-01** | Warning (advisory) | UX-correctness drift: a successful Batch Detect reports "Cleaned 30/30 pages" (factually wrong, implies cleaned outputs exist when none do). The 02-04 SUMMARY claimed mode-aware finish text but only the `_batch_verb` progress label was made mode-aware; the finish handler was not. **Does NOT break the phase goal** — batch outputs are correct; only the status-bar label is misleading on detect-only runs. Tracked in 02-REVIEW.md as the sole Critical finding; advisory per phase context ("do not block verification"). |
| `manga_ai_studio/core/image_io.py` | 109-124 | `passthrough_original` performs no validation on `cleaned_dir` (unlike `_run_batch_task`'s T-02-03 guard); `copy2` silently overwrites on basename collision — WR-02 | Info (advisory) | Latent only: sole caller today is `_run_batch_task` which has already passed its own guard. Defense-in-depth gap. |
| `manga_ai_studio/core/batch_runner.py` | 183 | bare `except Exception` would swallow `Abort` if it were ever raised inside the per-page body — IN-02 | Info (advisory) | Safe today because the abort check is at the loop top, OUTSIDE the try block; coupling is implicit/fragile. |
| `manga_ai_studio/core/batch_runner.py` | 149-182 | `detect_and_clean` re-reads the page image twice (BGR for detect, then again for inpaint RGB) — WR-06 | Info (advisory) | Deliberate per 02-03 SUMMARY; doubled I/O + a narrow TOCTOU window if the file is externally mutated between the two reads. |
| `manga_ai_studio/gui/main_window.py` | 1886-1932 | `_on_batch_cleanup` is NOT strictly idempotent on the abort-then-finished double-fire path (`_batch_mode` nulled on first call, second call falls through to clean-branch refresh) — WR-03 | Info (advisory) | Subtle canvas-overlay-clear after cancelling a detect batch; test suite does not exercise the real `Abort`-then-`finished` double-fire. |

**Debt-marker gate:** No `TBD`, `FIXME`, or `XXX` markers in any Phase 2 source file. The "placeholder" hits in `main_window.py` are the legitimate Recent Files `(empty)` placeholder QAction (UI-SPEC behavior) and a `"will be lost"` copywriting string — neither is a stub. PASS.

### Human Verification Required

#### 1. Re-verify cleaned/ output quality (user-requested deferred follow-up)

**Test:** Open a real manga chapter folder (5+ pages) in the app; run Batch Detect + Clean; inspect the resulting `cleaned/` subfolder next to the chapter.
**Expected:** (1) Outputs visually clean (text removed, artwork restored); (2) no-text pages are byte-identical to their source (the D-03 `shutil.copy2` passthrough is not silently re-encoding through PIL); (3) files are written ONLY into `cleaned/` and never into the source chapter folder.
**Why human:** Requires the real CTD (~80MB) + LaMa (~200MB) model weights and a real manga chapter; visual quality inspection is not automatable headless. The 02-04 blocking smoke-test spot-check #3 already passed (user approved all 6 checks after 2 fix cycles), but the user explicitly logged a follow-up re-verification request in STATE.md Blockers/Concerns before considering the phase fully shipped.

Note: The 02-04 checkpoint's 6 manual smoke checks were **already user-approved** (per phase context and 02-04 SUMMARY). They are not re-listed here as open human items — only the deliberately-deferred cleaned/-quality re-check remains.

### Gaps Summary

No gaps. All 12 observable truths are VERIFIED with both code presence and (where behavior-dependent) passing behavioral tests. PROJ-02 and FLOW-03 are fully satisfied and traced. The full automated suite is green (156 passed; 24 new Phase 2 tests). All required artifacts exist, are substantive, and are wired; data flows are real (not hardcoded/empty).

**Why `human_needed` and not `passed`:** One human verification item remains open — the user-requested deliberate re-verification of `cleaned/` output quality. Per the verifier decision tree, any non-empty human-verification section routes to `human_needed` regardless of how many truths verified. This is the *only* thing between this phase and a clean `passed`.

**Advisory findings (do NOT block the phase goal):**
- **CR-01** (02-REVIEW.md Critical): `_on_batch_finished` hardcodes "Cleaned" status text for all batch modes; detect-only runs mislabel as "Cleaned 30/30". UX-correctness drift from the documented contract; the 02-04 SUMMARY claimed mode-aware finish text that was never implemented. Fix is a 1-line mode branch mirroring `_batch_verb`. Advisory per phase context — does not break the goal (outputs are correct), but should be picked up before phase close since it surfaces on every detect-only batch.
- **WR-02 / WR-03 / WR-06 / IN-02** (02-REVIEW.md Warnings/Info): defense-in-depth gaps and subtle double-fire ordering; latent only under current call graph; documented in 02-REVIEW.md for future hardening.

---

_Verified: 2026-07-24T22:50:00Z_
_Verifier: Claude (gsd-verifier)_

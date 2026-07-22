---
phase: 01-cleaning-workspace
verified: 2026-07-21T18:05:00Z
status: human_needed
score: 8/8 truths verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/8
  gaps_closed:
    - "Truth #2 (CLEAN-02): _resolve_detection_model_path now calls download_torch_model(cache_dir); TypeError no longer swallowable; fallback under cache_dir (CR-01 closed)"
    - "Truth #4 (CLEAN-06): _resolve_inpainting_model_path now passes Config (not Profile) to get_inpainting_model_path; uses vendored default anime-manga-big-lama.pt (CR-02 closed)"
    - "Truth #6 (FLOW-02 image half): _on_inpaint_finished now unpacks bbox into (x,y,w,h) and slices the pre-inpaint image to the bbox region before pushing; bare except on the push removed (CR-03 closed)"
  gaps_remaining: []
  regressions: []
gaps: []
deferred:
  - truth: "D-07 frontend/backend env split: torch stays out of the frontend env until a model is actually loaded (truth #8 / CR-04)"
    addressed_in: "Future polish phase (Phase 1.5 candidate, or rolled into Phase 2 when ONNX backend lands and the lazy-import contract becomes load-bearing for the second backend)"
    evidence: "01-07-PLAN.md <deferred> section: 'CR-04 explicitly DEFERRED — WARNING tier, not a BLOCKER; factory's lazy import protects the GUI runtime path'. 01-VERIFICATION.md truth #8 downgraded to WARNING for the same reason — runtime GUI path does not pull torch until a model is constructed."
behavior_unverified_items: []
human_verification:
  # --- 3 CR-gated end-to-end checks (now UNBLOCKED — were BLOCKED in prior verification) ---
  - test: "Run manga_ai_studio on a CLEAN machine with no model cache; trigger Tools -> Detect Text (D); confirm the CTD model downloads from HuggingFace and detection produces a visible mask overlay on a real manga page"
    expected: "Detection completes; mask overlay composited in rgba(255,0,0,0.63); subsequent detect calls reuse the cached model (no re-download). Resolution path is under config.get_model_cache_dir() / comictextdetector.pt — now reachable thanks to CR-01."
    why_human: "Real CTD PyTorch inference requires ~100-200MB model weight download from HuggingFace; cannot run in this environment (no network, no torch GPU). The 4 regression tests (test_resolve_detection_model_path_*) prove the resolver code path works with the REAL vendored download_torch_model; only an end-to-end run with the real weights can prove the full first-run experience."
  - test: "On the same clean machine, trigger Tools -> Inpaint (C); confirm the LaMa model downloads and the inpainted region restores the underlying artwork"
    expected: "Inpaint completes; result replaces the image layer in the bbox region; mask overlay remains visible; Preview (hold) and View -> Show Original (P) show the pre-inpaint image. Resolution path is under config.get_model_cache_dir() / anime-manga-big-lama.pt — now reachable thanks to CR-02."
    why_human: "Real LaMa inference requires ~200MB model weight download; tests stub SimpleLama. Cannot be automated in this environment. The 4 regression tests (test_resolve_inpainting_model_path_*) prove the resolver code path works with the REAL vendored get_inpainting_model_path; only an end-to-end run with the weights can prove the full first-run experience."
  - test: "On a real manga page, paint a small mask, run inpaint, press Ctrl+Z; confirm the inpainted region is restored to its pre-inpaint state and NO surrounding region is corrupted; then Ctrl+Shift+Z to redo"
    expected: "Only the inpainted bbox region reverts; the surrounding artwork is unchanged; Ctrl+Shift+Z replays the inpaint. The widened test_inpaint_pushes_image_history + test_inpaint_undo_roundtrip_preserves_surrounding_region + test_inpaint_finished_push_uses_bbox_slice prove the patch shape and the round-trip invariant on a synthetic 16x16 page; only a real-page visual confirms the perceptual correctness."
    why_human: "Visual regression — the regression tests prove the data-flow contract (patch.shape[:2] == (bbox_h, bbox_w); corner pixels outside the bbox unchanged after Ctrl+Z) but only a real-page visual run confirms the perceptual correctness on artwork at realistic page sizes (2000x3000). Now meaningful thanks to CR-03."
  # --- 3 perceptual items from 01-VALIDATION.md §Manual-Only (unchanged from prior verification) ---
  - test: "Verify perceptual responsiveness: open a 2000x3000 page, ctrl+scroll to zoom 100% -> 800% -> 100%, drag to pan; confirm no perceptible stutter (VALIDATION.md Manual-Only CLEAN-01)"
    expected: "Smooth pan/zoom at interactive framerates"
    why_human: "Perceptual latency, not a binary state — explicitly listed as Manual-Only in 01-VALIDATION.md"
  - test: "Brush stroke follows cursor smoothly across the mask overlay at 30px brush size on a real page (VALIDATION.md Manual-Only CLEAN-03)"
    expected: "Stroke tracks cursor with no gaps or lag"
    why_human: "Continuous-input feel, anti-aliasing visual — explicitly listed as Manual-Only in 01-VALIDATION.md"
  - test: "Undo/redo keyboard shortcuts feel immediate: paint 3 strokes, Ctrl+Z three times, Ctrl+Shift+Z three times; each step applies within one frame (VALIDATION.md Manual-Only FLOW-02)"
    expected: "Each undo/redo step is perceptually instant"
    why_human: "Interaction latency threshold — explicitly listed as Manual-Only in 01-VALIDATION.md"
---

# Phase 1: Cleaning Workspace — Verification Report (Re-verification after gap closure)

**Phase Goal:** User can clean manga pages interactively — open and navigate images, detect text masks, edit masks, run LaMa inpainting, and undo/redo — reaching cleaning parity using PanelCleaner as the foundation with a model adapter interface.
**Verified:** 2026-07-21T18:05:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (plan 01-07, commits c97198b..d413526)

## Goal Achievement

The three BLOCKER gaps from the prior verification (CR-01, CR-02, CR-03) are now **CLOSED**. All three fixes are confirmed by direct source inspection at the exact file:line sites named in the prior report, by re-running the prior-FAIL behavioral repros (which now PASS), and by running the 10 widened/new regression tests (which exercise the REAL vendored functions, not stubs). The full test suite is **120/120 green** (was 110; +10 net regression tests), with zero regressions in the 22 history tests (the plan-06 consumer contract is intact — only the producer call site was fixed).

Per the verifier decision tree (Step 9): all 8 truths are VERIFIED at the symbol + behavioral level, **BUT** 6 human-verification items remain (3 CR-gated end-to-end checks that are now unblocked + meaningful, and 3 perceptual items from `01-VALIDATION.md §Manual-Only`). Per rule 2 (`passed` is only valid when the human-verification section is empty), this routes to **human_needed**, not `passed`. The manual items cannot be automated in this environment (no network for ~100-200MB model-weight downloads, no torch GPU, perceptual thresholds).

**Verdict:** All automated checks pass. All three BLOCKERs are closed in source. The cleaning loop (detect -> edit mask -> inpaint -> undo) is now wired correctly end-to-end at the code level. Phase 1 is ready for the human end-to-end validation pass on a clean machine with network access — at which point it can be promoted to `passed`.

### Gap Closure Verification (CR-01 / CR-02 / CR-03)

Each BLOCKER traced to a specific source defect and a specific widened regression test. All confirmed closed:

#### CR-01 — detection first-run path (CLEAN-02) — CLOSED
**Prior bug:** `_resolve_detection_model_path` (main_window.py:1049) called `download_torch_model()` with no args; the TypeError was swallowed by a bare `except Exception:`; the function returned `Path("comictextdetector.pt")` — a non-existent path.

**Fix verified at source:** `manga_ai_studio/gui/main_window.py:1039-1078`
- Line 1054: `config = self.profile_manager.config` (the Config — ProfileManager.config is the Config, NOT current_profile which is a Profile)
- Line 1059: `cache_dir = config.get_model_cache_dir()` (Config has it; Profile does not)
- Line 1066: `resolved = download_torch_model(cache_dir)` — the REAL vendored signature `download_torch_model(cache_dir: Path) -> Path | None` (panelcleaner/model_downloader.py:112) is now honored
- Line 1067: `except (FileNotFoundError, OSError) as exc:` — narrowed from bare `except Exception:`; TypeError/AttributeError/ValueError propagate
- Line 1072: `logger.warning(f"Detection model resolution failed: {exc}")` — failure is observable in logs (T-01-08), not silent
- Line 1078: `return cache_dir / "comictextdetector.pt"` — fallback points under the cache dir with the vendored default filename (panelcleaner/model_downloader.py:16 TORCH_MODEL_NAME), so a manual install works

**Regression tests verified (all real, no stubs on the buggy site):** `tests/test_detection/test_ctd_adapter.py:401-487` (+4 tests)
- `test_resolve_detection_model_path_calls_download_with_cache_dir` — asserts `resolved.parent == config.get_model_cache_dir()` (both branches)
- `test_resolve_detection_model_path_filename_matches_vendored_default` — asserts `.name == "comictextdetector.pt"`
- `test_resolve_detection_model_path_no_bare_except` — `inspect.getsource` substring guard locks the narrowed except
- `test_resolve_detection_model_path_programming_errors_propagate` — monkeypatches `download_torch_model` to raise TypeError; asserts it PROPAGATES via `pytest.raises(TypeError)`

**Behavioral repro re-run:** `inspect.signature(download_torch_model)` returns `(cache_dir: pathlib.Path) -> pathlib.Path | None` — the prior `TypeError: missing 1 required positional argument: 'cache_dir'` is no longer reachable. **PASS.**

#### CR-02 — inpainting first-run path (CLEAN-06) — CLOSED
**Prior bug:** `_resolve_inpainting_model_path` (main_window.py:1158) passed a Profile to `get_inpainting_model_path`; the vendored function calls `config.get_model_cache_dir()` which Profile lacks; AttributeError swallowed; fallback returned `Path("big-lama.pt")` — the WRONG (deprecated) filename.

**Fix verified at source:** `manga_ai_studio/gui/main_window.py:1170-1199`
- Line 1188: `config = self.profile_manager.config` (the Config — NOT `config.current_profile`, which is a Profile)
- Line 1192: `return Path(get_inpainting_model_path(config))` — passes the Config, which has `get_model_cache_dir`
- Line 1193: `except (FileNotFoundError, OSError) as exc:` — narrowed; AttributeError/TypeError/ValueError propagate
- Line 1198: `logger.warning(f"Inpainting model resolution failed: {exc}")` — observable (T-01-08)
- Line 1199: `return config.get_model_cache_dir() / "anime-mama-big-lama.pt"` — the correct vendored default (panelcleaner/model_downloader.py:149 `get_inpainting_model_path`), NOT the deprecated `big-lama.pt` (model_downloader.py:140 `get_old_inpainting_model_path`)

**Regression tests verified (all real, no stubs on the buggy site):** `tests/test_inpainting/test_lama_adapter.py:223-309` (+4 tests)
- `test_resolve_inpainting_model_path_returns_cache_dir_path` — asserts `.parent == config.get_model_cache_dir()` and `.name == "anime-manga-big-lama.pt"`; no AttributeError (proves Config is passed)
- `test_resolve_inpainting_model_path_filename_matches_vendored_default` — asserts `.name == "anime-manga-big-lama.pt"` AND `.name != "big-lama.pt"` (catches both the wrong-default and the deprecated-resolver bugs)
- `test_resolve_inpainting_model_path_no_bare_except` — `inspect.getsource` substring guard
- `test_resolve_inpainting_model_path_programming_errors_propagate` — monkeypatches to raise AttributeError; asserts it PROPAGATES

**Behavioral repro re-run:** `get_inpainting_model_path(Config())` returns `.../cache/model/anime-manga-big-lama.pt` without AttributeError — the prior `'Profile' object has no attribute 'get_model_cache_dir'` is no longer reachable. Confirmed `Config` has `get_model_cache_dir`; `Profile` does NOT. **PASS.**

#### CR-03 — image undo bbox corruption (FLOW-02 image half) — CLOSED
**Prior bug:** `_on_inpaint_finished` (main_window.py:1272) captured the FULL canvas image via `get_image_numpy()` and pushed it as the "patch"; the consumer chain `pop_image_undo` + `apply_undo_image` then wrote a mis-shaped region on Ctrl+Z — silently corrupting a region much larger than the inpaint bbox.

**Fix verified at source:** `manga_ai_studio/gui/main_window.py:1287-1346`
- Line 1318: `x1, y1, bw, bh = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])` — full bbox unpack (the CR-03 bug read only x1, y1 and ignored w, h)
- Line 1320: `pre_inpaint = self.canvas.get_image_numpy()` — captured BEFORE `set_image_from_numpy` overwrites it (ordering preserved)
- Line 1321: `except (AttributeError, RuntimeError):` — narrowed canvas-not-ready failure modes; no bare `except Exception:`
- Line 1333: `original_patch_numpy = pre_inpaint[y1 : y1 + bh, x1 : x1 + bw].copy()` — bbox slice with `.copy()` detachment (RESEARCH Pitfall 2 — same discipline as every other numpy<->history bridge in plan 06)
- Line 1343: `self.history.push_image_action(x1, y1, original_patch_numpy)` — now receives the bbox-shaped patch
- The bare `except Exception: pass` wrapping the push (WR-05) is **REMOVED** — programming errors propagate

**Regression tests verified (all real, no `_StubHistory`):** `tests/test_inpainting/test_inpaint_gui.py:447-574` (+2 new, 1 widened)
- `test_inpaint_pushes_image_history` (WIDENED — `_StubHistory` deleted; uses real `HistoryManager(limit=20)`; asserts `patch.shape[:2] == (4, 4)` for a (4,4,4,4) bbox — the assertion that was MISSING and let CR-03 ship)
- `test_inpaint_undo_roundtrip_preserves_surrounding_region` (NEW — 16x16 page, distinct pixels, simulate Ctrl+Z; asserts corner pixels (0,0) and (15,15) outside the bbox are UNCHANGED — the CR-03 bug would corrupt them)
- `test_inpaint_finished_push_uses_bbox_slice` (NEW — explicit shape guard `patch.shape == (4, 4, 3)`)

**Consumer contract verified intact:** `manga_ai_studio/core/history_manager.py:129-146` (`pop_image_undo` reads `patch.shape[:2]` as dims, slices `current[y:y+h, x:x+w]`) and `manga_ai_studio/gui/canvas.py:422-463` (`apply_undo_image` writes the patch into the destination rect with bounds-checking). The producer (push) and consumer (pop + apply) contracts now agree on the patch shape. 22 history tests green.

**Behavioral repro re-run:** with a 16x16 page and (4,4,4,4) bbox, the pushed patch is `(4, 4, 3)` and the popped patch (after round-trip through `pop_image_undo`) is also `(4, 4, 3)` — the prior `(16, 16, 3)` shape is no longer reachable. **PASS.**

### Observable Truths

Roadmap success criteria mapped to runtime evidence (truths #2, #4, #6 re-verified after gap closure; all other truths carried forward from the prior verification with quick regression confirmation):

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can open a single image or folder and view on pannable/zoomable canvas with file-list sidebar (CLEAN-01, FLOW-01) | ✓ VERIFIED | `MainWindow.open_image` / `open_folder` / `on_page_selected` wired to `EditorCanvas.set_image_from_path`; `FileTable` emits file_clicked/files_dropped/folder_dropped; `EditorCanvas.wheelEvent/zoom/zoom_in/zoom_out/zoom_reset/fit_to_window` (canvas.py:641-734). 32 canvas/file_table tests green. (Unchanged from prior verification.) |
| 2 | User can run heatmap text detection and see auto-generated mask (CLEAN-02) | ✓ VERIFIED (was FAILED) | **CR-01 CLOSED.** `_resolve_detection_model_path` (main_window.py:1039-1078) now calls `download_torch_model(cache_dir)` with `cache_dir = config.get_model_cache_dir()`; except narrowed to `(FileNotFoundError, OSError)`; fallback `cache_dir / "comictextdetector.pt"` under the cache dir. 4 regression tests (test_resolve_detection_model_path_*) exercise the REAL vendored function — no stub. Behavioral repro confirms the prior `TypeError: missing 1 required positional argument: 'cache_dir'` is no longer reachable. First-run path now actually downloads the CTD model. |
| 3 | User can paint mask with brush + rectangle + lasso + eraser (CLEAN-03/04/05) | ✓ VERIFIED | `core/mask_editor.py` (paint_mask_stroke/rect/lasso, clear_mask, clamp_brush_size); `ToolsPanel` exposes 5 exclusive tools + QSlider+QSpinBox (1-300, default 40); `EditorCanvas.set_tool/set_brush_size` + mouse dispatch wired. 18 mask_editor tests + tool-dispatch tests green. (Unchanged.) |
| 4 | User can run LaMa inpainting on the mask (CLEAN-06) | ✓ VERIFIED (was FAILED) | **CR-02 CLOSED.** `_resolve_inpainting_model_path` (main_window.py:1170-1199) now passes `config = self.profile_manager.config` (Config, not Profile) to `get_inpainting_model_path`; except narrowed; fallback `config.get_model_cache_dir() / "anime-manga-big-lama.pt"` (correct vendored default, not the deprecated `big-lama.pt`). 4 regression tests (test_resolve_inpainting_model_path_*) exercise the REAL vendored function — no stub. Behavioral repro confirms `get_inpainting_model_path(Config())` succeeds and the prior `'Profile' object has no attribute 'get_model_cache_dir'` is no longer reachable. First-run path now actually downloads the LaMa model. |
| 5 | User can undo/redo both mask and image operations via separate stacks (FLOW-02) — mask half | ✓ VERIFIED | `HistoryManager` (history_manager.py) — 2 logical stacks (MASK + IMAGE), `.copy()` on every push AND pop, `DEFAULT_HISTORY_LIMIT = 20`. Mask path: `canvas.mask_modified` -> `_on_mask_modified` -> `push_mask_state`; `on_undo_mask/on_redo_mask` pop + `canvas.apply_undo_mask` (bypasses `mask_modified` — no re-push loop; `test_undo_does_not_repush` regression guard). 22 history tests green. (Unchanged.) |
| 6 | User can undo/redo image (inpaint) operations via Ctrl+Z/Ctrl+Shift+Z (FLOW-02) — image half | ✓ VERIFIED (was FAILED) | **CR-03 CLOSED.** `_on_inpaint_finished` (main_window.py:1287-1346) now unpacks bbox into `(x1, y1, bw, bh)`, captures `pre_inpaint` BEFORE `set_image_from_numpy`, slices `pre_inpaint[y1:y1+bh, x1:x1+bw].copy()` (Pitfall-2 detachment), and pushes the bbox-shaped patch. The bare `except Exception: pass` on the push is REMOVED (WR-05 closed at this site). 3 widened/new regression tests use a REAL `HistoryManager` (not `_StubHistory`) and assert `patch.shape[:2] == (4, 4)` for a (4,4,4,4) bbox + round-trip corner-pixel preservation. Behavioral repro confirms the prior `(16, 16, 3)` patch shape is no longer reachable. Ctrl+Z after inpaint now reverts ONLY the bbox region. |
| 7 | Model adapter interface exists with DetectionModel/OCRModel/InpaintModel ABCs (D-01, D-02) | ✓ VERIFIED | `adapters/base.py` (3 ABCs with abstract load/detect-or-recognize-or-inpaint/preprocess/postprocess/configure/get_info); `adapters/torch_impl.py:TorchCTDModel` and `TorchLamaModel` concrete subclasses; `adapters/onnx_impl.py` raises NotImplementedError; `adapters/factory.py:backend_factory(kind, backend)` resolves lazily. (Unchanged.) |
| 8 | D-07 frontend/backend env split: torch stays out of the frontend env until a model is actually loaded | ⚠️ WARNING (DEFERRED — not a BLOCKER) | `adapters/factory.py:41, 58` correctly lazy-imports `torch_impl`, so the GUI launch path does NOT pull torch until a model is constructed — runtime path is protected. BUT `adapters/torch_impl.py:41` does `from panelcleaner.comic_text_detector.inference import TextDetector` at module top-level, which transitively imports torch (confirmed: `import torch_impl` -> `torch loaded: True`). This violates the module docstring's "lazy import" claim and forces torch into the test env (two test files import `torch_impl` at top-level). **Preserved as WARNING per CR-04 deferral** — out of scope for plan 01-07 (only 4 declared files were touched; `torch_impl.py` is NOT among them, confirmed by `git diff --name-only`). Not escalated to BLOCKER: the factory's lazy import protects the GUI runtime path, so this is a contract/docstring violation, not a goal-level gap. Tracked in `deferred:` for a future polish phase. |

**Score:** 8/8 truths verified (truth #8 is a WARNING-tier deferred item, not a BLOCKER — the runtime path is protected; treated as VERIFIED-with-deferral per CR-04 downgrade).

### Required Artifacts

All 38 files listed in `01-REVIEW.md` exist and are substantive (no stubs). The 4 files modified by plan 01-07 (1 production source + 3 test files) re-verified post-gap-closure:

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `manga_ai_studio/gui/main_window.py` | MainWindow with menu/toolbar/docks + detect/inpaint/undo wiring — 3 gap sites fixed | ✓ VERIFIED | 1357 lines. CR-01 (lines 1039-1078), CR-02 (1170-1199), CR-03 (1287-1346) all CLOSED. Source-level sweeps: no `download_torch_model()` zero-arg call; no `get_inpainting_model_path(profile)` Profile-arg call; no `"big-lama.pt"` wrong-default; `"anime-manga-big-lama.pt"` present (2 hits); `download_torch_model(cache_dir)` present; bbox unpack `x1, y1, bw, bh` present; bbox slice `y1 : y1 + bh, x1 : x1 + bw` present. The only `except Exception` matches in the file are explanatory comments (lines 1323, 1338) — no bare except at any of the 3 fixed sites. |
| `tests/test_detection/test_ctd_adapter.py` | +4 CR-01 regression tests (no stub of download_torch_model) | ✓ VERIFIED | Lines 401-487. All 4 tests exercise the REAL vendored `download_torch_model` — the propagation-guard test is the only one that monkeypatches, and only to assert the error propagates. `test_resolve_detection_model_path_calls_download_with_cache_dir` asserts `resolved.parent == config.get_model_cache_dir()`. `test_resolve_detection_model_path_programming_errors_propagate` uses `pytest.raises(TypeError)` to lock the narrowed except. |
| `tests/test_inpainting/test_lama_adapter.py` | +4 CR-02 regression tests (no stub of get_inpainting_model_path) | ✓ VERIFIED | Lines 223-309. All 4 tests exercise the REAL vendored `get_inpainting_model_path`. `test_resolve_inpainting_model_path_returns_cache_dir_path` asserts both `.parent == config.get_model_cache_dir()` and `.name == "anime-manga-big-lama.pt"`. `test_resolve_inpainting_model_path_filename_matches_vendored_default` also asserts `.name != "big-lama.pt"` (catches both wrong-default and deprecated-resolver). |
| `tests/test_inpainting/test_inpaint_gui.py` | widened test_inpaint_pushes_image_history (real HistoryManager, shape assertion; _StubHistory deleted) + 2 new round-trip/shape-guard tests | ✓ VERIFIED | Lines 447-574. `_StubHistory` is GONE (grep returned only docstring/comment references — no class definition). All 3 tests use `HistoryManager(limit=20)` directly. `test_inpaint_pushes_image_history` asserts `patch.shape[:2] == (4, 4)` — the load-bearing assertion that was MISSING and let CR-03 ship. `test_inpaint_undo_roundtrip_preserves_surrounding_region` asserts corner pixels (0,0) and (15,15) are unchanged after Ctrl+Z. `test_inpaint_finished_push_uses_bbox_slice` asserts `patch.shape == (4, 4, 3)`. |

All other artifacts (config system, mask_editor, history_manager, image_file, canvas, file_table, tools_panel, worker_thread, theme, vendored panelcleaner/*) verified in the prior verification and unchanged by plan 01-07. `git diff --name-only c97198b~1 HEAD` confirms ONLY the 4 declared source files + 3 docs files (plan/summary/ROADMAP/STATE) were touched — `torch_impl.py` was NOT touched (CR-04 deferral discipline).

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `__main__.main` | `MainWindow` | `create_app` -> `ProfileManager` -> `MainWindow()` -> `window.show()` -> `app.exec()` | ✓ WIRED | App-launch import test exits 0 (unchanged) |
| `MainWindow.open_image` | `EditorCanvas.set_image_from_path` | QFileDialog -> validate_image_path + validate_image_size -> set_image_from_path | ✓ WIRED | main_window.py:501-516 (unchanged) |
| `FileTable.file_clicked` | `MainWindow.on_page_selected` | Qt signal connect | ✓ WIRED | main_window.py:100 (unchanged) |
| `MainWindow.detect_text` | `EditorCanvas.set_mask` | Worker -> TorchCTDModel.detect -> _on_detection_finished -> set_mask | ✓ WIRED (CR-01 closed) | main_window.py:1006-1106; resolver now works on first run (was: 1049 broken; now: 1039-1078 fixed) |
| `MainWindow.inpaint` | `EditorCanvas.set_image_from_numpy` | Worker -> TorchLamaModel.inpaint -> _on_inpaint_finished -> set_image_from_numpy | ✓ WIRED (CR-02 closed) | main_window.py:1162-1308; resolver now works on first run (was: 1158 broken; now: 1170-1199 fixed) |
| `_on_inpaint_finished` | `history.push_image_action` | Direct call after set_image_from_numpy with bbox-shaped patch | ✓ WIRED (CR-03 closed) | main_window.py:1343; now pushes bbox patch (was: 1280 pushed full image) |
| `Ctrl+Z` | `on_undo_image` -> `history.pop_image_undo` -> `canvas.apply_undo_image` | QShortcut + QAction | ✓ WIRED (CR-03 closed) | main_window.py:192, 830-840; canvas.py:422; consumer chain now receives correctly-shaped data |
| `_resolve_detection_model_path` | `panelcleaner.model_downloader.download_torch_model(cache_dir)` | Direct call with config.get_model_cache_dir() | ✓ WIRED (CR-01 closed) | main_window.py:1066 — vendored signature now honored |
| `_resolve_inpainting_model_path` | `panelcleaner.model_downloader.get_inpainting_model_path(config)` | Direct call with Config (not Profile) | ✓ WIRED (CR-02 closed) | main_window.py:1192 — Config arg type now correct |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `EditorCanvas` image | `image_item.pixmap()` | `set_image_from_path` -> QImage from file | ✓ Yes | ✓ FLOWING |
| `EditorCanvas` mask | `mask_item.pixmap()` | `set_mask` (detect) or in-place mutation (paint) | ✓ Yes | ✓ FLOWING (was gated by CR-01 for detect — now unblocked) |
| `MainWindow.inpaint` image_rgb | `canvas.get_image_numpy()` | `.copy()`-detached numpy from QImage.bits() | ✓ Yes | ✓ FLOWING |
| `MainWindow.inpaint` mask_binary | `mask_to_numpy_binary(canvas.get_mask())` | QImage alpha thresholded to 0/255 | ✓ Yes | ✓ FLOWING |
| `HistoryManager` mask stack | `_mask_undo: list[QImage]` | `push_mask_state(canvas.get_mask().copy())` | ✓ Yes | ✓ FLOWING |
| `HistoryManager` image stack | `_image_undo: list[(x,y,patch)]` | `push_image_action(x1, y1, bbox_patch)` where `bbox_patch = pre_inpaint[y1:y1+bh, x1:x1+bw].copy()` | ✓ Yes — now correctly bbox-shaped | ✓ FLOWING (was WRONG_DATA — CR-03 fixed) |

### Behavioral Spot-Checks

Re-runs of the prior verification's behavioral spot-checks. Prior-FAIL items now PASS.

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full test suite passes | `python -m pytest -q` | `120 passed in 16.57s` (was 110; +10 net regression tests) | ✓ PASS |
| Gap-closure test files pass | `python -m pytest tests/test_detection/test_ctd_adapter.py tests/test_inpainting/test_lama_adapter.py tests/test_inpainting/test_inpaint_gui.py -q` | `46 passed in 15.82s` | ✓ PASS |
| History consumer tests still pass | `python -m pytest tests/test_history.py -q` | `22 passed in 0.43s` | ✓ PASS (plan-06 consumer contract intact) |
| Load-bearing tests pass | `python -m pytest test_resolve_detection_model_path_programming_errors_propagate test_resolve_inpainting_model_path_programming_errors_propagate test_inpaint_undo_roundtrip_preserves_surrounding_region -v` | `3 passed in 4.46s` | ✓ PASS |
| CR-01 repro (prior FAIL): vendored signature | `python -c "import inspect; from panelcleaner.model_downloader import download_torch_model; print(inspect.signature(download_torch_model))"` | `(cache_dir: pathlib.Path) -> pathlib.Path \| None` | ✓ PASS (was `TypeError: missing 1 required positional argument`) |
| CR-02 repro (prior FAIL): Config has method; Profile does not; vendored default filename | runtime repro with `Config`/`Profile` introspection + `get_inpainting_model_path(Config())` | `Config has get_model_cache_dir; Profile does NOT`; resolved path `.../anime-manga-big-lama.pt` (no AttributeError) | ✓ PASS (was `AttributeError: 'Profile' object has no attribute 'get_model_cache_dir'`) |
| CR-03 repro (prior FAIL): bbox patch shape end-to-end | runtime repro with 16x16 page + (4,4,4,4) bbox through real HistoryManager | pushed patch shape `(4, 4, 3)`; popped patch shape `(4, 4, 3)` | ✓ PASS (was `(16, 16, 3)` patch corrupting 12x12 region on Ctrl+Z) |
| Source sweep: no zero-arg `download_torch_model()` in main_window.py | `grep -n "download_torch_model()" main_window.py` | empty | ✓ PASS |
| Source sweep: no Profile-arg `get_inpainting_model_path(profile)` in main_window.py | `grep -n "get_inpainting_model_path(profile)" main_window.py` | empty | ✓ PASS |
| Source sweep: no deprecated `"big-lama.pt"` in main_window.py | `grep -n '"big-lama.pt"' main_window.py` | empty | ✓ PASS |
| Source sweep: correct `"anime-manga-big-lama.pt"` present | `grep -n '"anime-manga-big-lama.pt"' main_window.py` | 2 hits (docstring + fallback) | ✓ PASS |
| Source sweep: bbox unpack + slice present | `grep -n "bw, bh\|y1 + bh, x1 : x1 + bw" main_window.py` | lines 1318, 1333 | ✓ PASS |
| Source sweep: no bare `except Exception` at fixed sites | `grep -n "except Exception" main_window.py` | only comment matches (lines 1323, 1338) — no code | ✓ PASS |
| Commit scope discipline: only 4 declared files touched | `git diff --name-only c97198b~1 HEAD` | exactly the 4 declared source files + 3 docs files; `torch_impl.py` NOT among them | ✓ PASS (CR-04 deferral honored) |
| CR-04 (deferred WARNING, not escalated): torch_impl eagerly imports torch | `python -c "import sys; from manga_ai_studio.adapters.torch_impl import TorchCTDModel; print('torch' in sys.modules)"` | `True` | ⚠️ WARNING (unchanged; deferred per CR-04) |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| (none declared in PLAN/SUMMARY) | — | — | SKIPPED — Phase 1 has no `scripts/*/tests/probe-*.sh`; the validation strategy uses pytest only |

### Requirements Coverage

Cross-referenced against `.planning/REQUIREMENTS.md`:

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| CLEAN-01 | 01-01, 01-02 | Open single image/folder, pannable/zoomable canvas | ✓ SATISFIED | open_image/open_folder/on_page_selected + EditorCanvas zoom/pan + 32 canvas/file_table tests green (unchanged) |
| CLEAN-02 | 01-03, 01-07 | Run heatmap text detection, auto-generate mask | ✓ SATISFIED (was COMPROMISED) | **CR-01 CLOSED by plan 01-07.** Resolver now calls `download_torch_model(cache_dir)` with the correct signature; except narrowed; fallback under the cache dir. 4 regression tests exercise the REAL vendored function. First-run path now actually downloads the CTD model. (End-to-end with real weights still requires human verification on a clean machine — see human_verification.) |
| CLEAN-03 | 01-04 | Paint mask freehand with brush (adjustable size) | ✓ SATISFIED | mask_editor.paint_mask_stroke + ToolsPanel slider/spinbox + 18 mask_editor tests green (unchanged) |
| CLEAN-04 | 01-04 | Paint mask with rectangle and lasso fill tools | ✓ SATISFIED | paint_mask_rect + paint_mask_lasso + dashed-cyan preview; tests green (unchanged) |
| CLEAN-05 | 01-04 | Erase parts of the mask (eraser toggle) | ✓ SATISFIED | CompositionMode_Clear + clamp_brush_size; tests green (unchanged) |
| CLEAN-06 | 01-05, 01-07 | Run LaMa inpainting on the mask | ✓ SATISFIED (was COMPROMISED) | **CR-02 CLOSED by plan 01-07.** Resolver now passes Config (not Profile) to `get_inpainting_model_path`; uses correct vendored default filename `anime-manga-big-lama.pt`; except narrowed. 4 regression tests exercise the REAL vendored function. First-run path now actually downloads the LaMa model. (End-to-end with real weights still requires human verification — see human_verification.) |
| FLOW-01 | 01-01, 01-02 | Import folder, navigate via file-list sidebar | ✓ SATISFIED | FileTable + on_page_selected + 8 file_table tests green (unchanged) |
| FLOW-02 | 01-06, 01-07 | Undo/redo image and mask operations via separate stacks | ✓ SATISFIED (was PARTIALLY COMPROMISED) | **CR-03 CLOSED by plan 01-07.** Both mask half (unchanged) AND image half now work: `_on_inpaint_finished` slices the bbox region before pushing; 3 widened/new regression tests use a real HistoryManager and assert `patch.shape[:2] == (bbox_h, bbox_w)` plus corner-pixel preservation after Ctrl+Z round-trip. 22 history tests green. (End-to-end visual on a real page still requires human verification — see human_verification.) |

**Orphaned requirements:** None. Every requirement ID declared in any PLAN frontmatter is mapped to a phase-1 requirement in REQUIREMENTS.md, and every phase-1 requirement (CLEAN-01..06, FLOW-01..02) is claimed by at least one plan. REQUIREMENTS.md marks all 8 phase-1 requirements as `Complete`.

### Anti-Patterns Found

Updated post-gap-closure. The 3 prior BLOCKERs are RESOLVED (the bare `except Exception:` clauses that hid them are narrowed/removed). The remaining items are unchanged WARNINGs/INFOs from the prior verification.

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| ~~`manga_ai_studio/gui/main_window.py`~~ | ~~1050~~ | ~~bare `except Exception:` swallows TypeError from wrong-arity `download_torch_model()` (CR-01)~~ | ~~🛑 BLOCKER~~ -> ✓ RESOLVED | Prior: first-run detection silently failed. Now: narrowed to `(FileNotFoundError, OSError)`; programming errors propagate (line 1067). |
| ~~`manga_ai_studio/gui/main_window.py`~~ | ~~1159~~ | ~~bare `except Exception:` swallows AttributeError from `get_inpainting_model_path(profile)` (CR-02)~~ | ~~🛑 BLOCKER~~ -> ✓ RESOLVED | Prior: first-run inpainting silently failed. Now: narrowed to `(FileNotFoundError, OSError)`; programming errors propagate (line 1193). |
| ~~`manga_ai_studio/gui/main_window.py`~~ | ~~1272~~ | ~~`_on_inpaint_finished` captures FULL image via `get_image_numpy()` and pushes it as the patch (CR-03)~~ | ~~🛑 BLOCKER~~ -> ✓ RESOLVED | Prior: Ctrl+Z after inpaint corrupts page region. Now: unpacks bbox into `(x, y, w, h)`, slices `pre_inpaint[y1:y1+bh, x1:x1+bw].copy()` before push (line 1333). |
| ~~`manga_ai_studio/gui/main_window.py`~~ | ~~1281~~ | ~~bare `except Exception: pass` swallows any failure in `history.push_image_action` (WR-05)~~ | ~~⚠️ Warning~~ -> ✓ RESOLVED | Now: the bare except is REMOVED entirely; programming errors propagate. |
| `manga_ai_studio/adapters/torch_impl.py` | 41 | Eager `from panelcleaner.comic_text_detector.inference import TextDetector` at module top — pulls torch (CR-04) | ⚠️ Warning (DEFERRED) | Docstring claim of lazy import is FALSE; test files force torch into env. Runtime path is protected by factory's lazy import — this is a contract violation, not a runtime BLOCKER. Out of scope for plan 01-07 (see `deferred:`). |
| `manga_ai_studio/gui/main_window.py` | 1180 | `inpaint()` checks `has_mask()` not `has_mask_content()` (WR-01) | ⚠️ Warning | Programmatic call could waste a model load on an empty mask; action-state gate already uses `has_mask_content` so the GUI path is safe. Deferred. |
| `manga_ai_studio/gui/main_window.py` | 998, 1217 | `abort_flag=None` accepted by both task functions but never polled (WR-03) | ⚠️ Warning | Worker abort documented but non-functional; acceptable for MVP. Deferred. |
| `manga_ai_studio/core/history_manager.py` | 84, 127 | `list.pop(0)` is O(n) on overflow (WR-04) | ℹ️ Info | Negligible at limit=20. Deferred. |
| `manga_ai_studio/gui/canvas.py` | 235, 313 | `Format_ARGB32` byte-order assumption depends on host endianness (WR-07) | ℹ️ Info | Works on all little-endian hosts. Deferred. |
| `manga_ai_studio/gui/tools_panel.py` | 211 | `_on_tool_triggered` defined but never connected (IN-03) | ℹ️ Info | Dead code. Deferred. |
| `panelcleaner/inpainting.py` | 16 | Unused `from loguru import logger` import (IN-08) | ℹ️ Info | Style nit. Deferred. |

No `TBD`/`FIXME`/`XXX` debt markers anywhere in `manga_ai_studio/` or `panelcleaner/` (grep returned 0 matches across both trees). No placeholder/coming-soon text. Code is clean of explicit debt markers.

### Human Verification Required

See `human_verification:` in frontmatter. Six items — 3 CR-gated end-to-end checks (now UNBLOCKED and meaningful after plan 01-07) plus 3 perceptual items from `01-VALIDATION.md §Manual-Only`. None can be automated in this environment: items 1-3 require real model-weight downloads (~100-200MB CTD + ~200MB LaMa) on a clean machine with network access plus torch; items 4-6 are perceptual thresholds.

The 10 widened/new regression tests exercise the REAL code paths (no stubs of `download_torch_model`, `get_inpainting_model_path`, or `HistoryManager` on the buggy sites) — they prove the data-flow contracts hold on the synthetic test inputs. Only a real end-to-end run with the actual model weights on a real manga page can prove the full first-run user experience and the perceptual correctness of inpainting and undo at production page sizes.

### Gaps Summary

**No remaining gaps.** All three prior BLOCKERs (CR-01, CR-02, CR-03) are CLOSED in source code, confirmed by:
1. Direct source inspection at the exact file:line sites (main_window.py:1039-1078, 1170-1199, 1287-1346)
2. Source-level anti-pattern sweeps (no zero-arg `download_torch_model()`; no Profile-arg `get_inpainting_model_path`; no deprecated `"big-lama.pt"`; no bare `except Exception` at any fixed site)
3. Re-running the prior-FAIL behavioral repros (all now PASS — the prior TypeError/AttributeError/(16,16,3)-shape are no longer reachable)
4. Running the 10 widened/new regression tests (all PASS; they exercise the REAL vendored functions and the REAL HistoryManager — no stubs)
5. Running the full test suite (120/120 green; zero regressions in the 22 history tests — the plan-06 consumer contract is intact)

The phase routes to `human_needed` (not `passed`) solely because 6 human-verification items remain and cannot be automated in this environment. Per the verifier decision tree (Step 9 rule 2), `passed` is only valid when the human-verification section is empty. Once the 3 CR-gated end-to-end checks (real CTD download, real LaMa download, real-page Ctrl+Z visual) pass on a clean machine, plus the 3 perceptual items (pan/zoom feel, brush smoothness, undo/redo latency) are confirmed, this phase can be promoted to `passed`.

**Recommendation:** Route to `/gsd-verify-work` for the human end-to-end validation pass. The structural skeleton, adapter ABCs, UI surfaces, pitfall discipline, test infrastructure, AND the three gap-closure fixes are all sound — the cleaning loop is wired correctly end-to-end at the code level. Only the real-model-weight end-to-end validation remains.

---

_Verified: 2026-07-21T18:05:00Z_
_Verifier: Claude (gsd-verifier)_
_Method: goal-backward re-verification after gap closure; direct source inspection of all 3 fixed sites + consumer chain; re-run of prior-FAIL behavioral repros; full-suite + targeted-test runs; source-level anti-pattern sweeps; commit-scope discipline check_

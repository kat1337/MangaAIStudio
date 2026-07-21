---
phase: 01-cleaning-workspace
reviewed: 2026-07-21T00:00:00Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - manga_ai_studio/__init__.py
  - manga_ai_studio/__main__.py
  - manga_ai_studio/app.py
  - manga_ai_studio/config/__init__.py
  - manga_ai_studio/config/profile_manager.py
  - manga_ai_studio/adapters/__init__.py
  - manga_ai_studio/adapters/base.py
  - manga_ai_studio/adapters/onnx_impl.py
  - manga_ai_studio/adapters/torch_impl.py
  - manga_ai_studio/adapters/factory.py
  - manga_ai_studio/core/__init__.py
  - manga_ai_studio/core/image_file.py
  - manga_ai_studio/core/mask_editor.py
  - manga_ai_studio/core/history_manager.py
  - manga_ai_studio/gui/__init__.py
  - manga_ai_studio/gui/theme.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/file_table.py
  - manga_ai_studio/gui/tools_panel.py
  - manga_ai_studio/gui/worker_thread.py
  - tests/conftest.py
  - tests/__init__.py
  - tests/test_core/__init__.py
  - tests/test_core/test_adapters.py
  - tests/test_core/test_config.py
  - tests/test_detection/__init__.py
  - tests/test_detection/test_ctd_adapter.py
  - tests/test_gui_canvas.py
  - tests/test_gui_file_table.py
  - tests/test_history.py
  - tests/test_inpainting/__init__.py
  - tests/test_inpainting/test_inpaint_gui.py
  - tests/test_inpainting/test_lama_adapter.py
  - tests/test_mask_editor/__init__.py
  - tests/test_mask_editor/test_mask_editor.py
  - panelcleaner/inpainting.py
  - panelcleaner/structures.py
findings:
  critical: 4
  warning: 7
  info: 8
  total: 19
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-07-21
**Depth:** standard
**Files Reviewed:** 38 (Tier A: 36 + Tier B: 2)
**Status:** issues_found

## Summary

Reviewed the Phase 1 "Cleaning Workspace" delivery at standard depth — all 36 Tier A files plus the 2 Tier B minimal-vendor trims. The vendored Tier C `panelcleaner/**` tree was reviewed for integration concerns only (not style/clarity).

The Phase 1 work demonstrates strong defense-in-depth on its stated pitfall patterns — the `.copy()` buffer-detachment discipline (RESEARCH Pitfall 2), the 3-tuple contract for `TextDetector.__call__`, and the no-re-emit contract on `apply_undo_mask` are all correctly implemented and regression-guarded by tests. The pure-function extraction in `core/mask_editor.py` and `core/history_manager.py` is clean and testable.

However, four **Critical** defects slip past the test suite:

1. Both `_resolve_detection_model_path` and `_resolve_inpainting_model_path` in `gui/main_window.py` call vendored `panelcleaner` functions with **wrong arity / wrong argument type**. The calls raise inside a bare `except Exception:` that swallows the error and returns a fake path, so the first-run experience silently never downloads the models. Detection and inpainting will fail with "Model not found" while the actual bug (TypeError / AttributeError) is hidden.
2. The image-undo history hook in `_on_inpaint_finished` pushes the **full page image** as the `patch` argument while passing the bbox's `(x1, y1)` as the patch offset. `HistoryManager.pop_image_undo` then reads the patch's `shape[:2]` as patch dimensions and slices `current[y : y + H_full, x : x + W_full]` — silently corrupting a 12x12 (or larger) region of the page on Ctrl+Z after an inpaint.
3. `adapters/torch_impl.py` claims `torch` is imported lazily inside `load()` (D-07 frontend/backend split), but the module top-level does `from panelcleaner.comic_text_detector.inference import TextDetector` — and `inference.py` itself does `import torch` at module top-level. Importing `torch_impl` (which `tests/test_lama_adapter.py:26` and `tests/test_detection/test_ctd_adapter.py:22` both do) eagerly imports torch, contradicting the docstring and breaking the main_env / torch_env split claim.

Several **Warnings** round out the report: the `inpaint()` entry point gates on `has_mask()` rather than `has_mask_content()` (the action state uses the latter, creating an inconsistency that lets a programmatic call through); `apply_undo_image`/`set_image_from_numpy` are silent on out-of-bounds bbox values; the worker `abort_flag` infrastructure is wired but never actually polled by either task function; `pop(0)` on the history stacks is O(n) (acceptable at limit=20 but worth flagging if the limit grows); and a handful of unused imports / dead branches.

---

## Critical Issues

### CR-01: Detection model path resolver calls `download_torch_model()` with the wrong arity, swallowed by bare except

**File:** `manga_ai_studio/gui/main_window.py:1042-1053`
**Issue:**
`_resolve_detection_model_path` does:

```python
from panelcleaner.model_downloader import download_torch_model
...
return Path(download_torch_model())  # WRONG: download_torch_model(cache_dir)
```

The vendored signature (`panelcleaner/model_downloader.py:112`) is `def download_torch_model(cache_dir: Path) -> Path | None`. Calling it with no arguments raises `TypeError: download_torch_model() missing 1 required positional argument: 'cache_dir'`. Verified by direct call:

```
$ python3 -c "from panelcleaner.model_downloader import download_torch_model; download_torch_model()"
TypeError: download_torch_model() missing 1 required positional argument: 'cache_dir'
```

The bare `except Exception:` at line 1050 swallows this and returns `Path("comictextdetector.pt")` — a path that does not exist on disk. The downstream `TorchCTDModel.load` then raises `FileNotFoundError("Model not found: comictextdetector.pt")`, which the user sees as "Detection model error" with no hint that the actual cause was the wrong call signature. **First-run detection silently never downloads the model.**

Additionally: `download_torch_model` returns `Path | None` (None on download failure), and `Path(None)` itself raises `TypeError`. So even with the arity fixed, a download failure would crash inside the `Path(...)` wrapper.

**Fix:**
```python
def _resolve_detection_model_path(self) -> Path:
    try:
        profile = self.profile_manager.config.current_profile
        configured = profile.text_detector.model_path
        if configured:
            return Path(configured)
        cache_dir = self.profile_manager.config.get_model_cache_dir()
        from panelcleaner.model_downloader import download_torch_model
        downloaded = download_torch_model(cache_dir)
        if downloaded is None:
            raise FileNotFoundError("Torch model download failed")
        return Path(downloaded)
    except FileNotFoundError:
        raise  # let the real FileNotFoundError propagate to TorchCTDModel.load
    except Exception as exc:
        logger.error(f"Detection model path resolution failed: {exc}")
        return Path("comictextdetector.pt")
```

Note: `get_model_cache_dir()` lives on `Config` (config.py:1174), not on `Profile`, so use `self.profile_manager.config.get_model_cache_dir()`. Also remove the bare `except Exception:` that masks the underlying bug — let `FileNotFoundError` propagate.

---

### CR-02: Inpainting model path resolver passes a `Profile` where `Config` is required, swallowed by bare except

**File:** `manga_ai_studio/gui/main_window.py:1154-1160`
**Issue:**
`_resolve_inpainting_model_path` does:

```python
profile = self.profile_manager.config.current_profile
return Path(get_inpainting_model_path(profile))  # WRONG: expects a Config
```

The vendored signature (`panelcleaner/model_downloader.py:143-149`) is `def get_inpainting_model_path(config) -> Path: return config.get_model_cache_dir() / "anime-manga-big-lama.pt"`. The function calls `config.get_model_cache_dir()`, which is defined on `Config` (config.py:1174), NOT on `Profile`. Passing a `Profile` raises `AttributeError: 'Profile' object has no attribute 'get_model_cache_dir'`.

The bare `except Exception:` at line 1159 swallows this and returns `Path("big-lama.pt")` — a non-existent path. **First-run inpainting silently never downloads the model.** Same shape of bug as CR-01.

Additionally note the fallback filename `big-lama.pt` does not match the vendored default `anime-manga-big-lama.pt` (model_downloader.py:149), so even if the user manually placed a model in the cache dir, the fallback would not find it.

**Fix:**
```python
def _resolve_inpainting_model_path(self) -> Path:
    try:
        config = self.profile_manager.config  # Config has get_model_cache_dir()
        from panelcleaner.model_downloader import get_inpainting_model_path
        return Path(get_inpainting_model_path(config))
    except Exception as exc:
        logger.error(f"Inpainting model path resolution failed: {exc}")
        # Match the actual vendored default filename so a manual install works.
        from panelcleaner.model_downloader import get_inpainting_model_path
        return Path(get_inpainting_model_path(self.profile_manager.config))
```

Same recommendation as CR-01: log the actual exception, narrow the `except`, and propagate `FileNotFoundError` rather than masking the underlying failure.

---

### CR-03: Image-undo pushes the FULL page as the patch, corrupting a larger region on Ctrl+Z

**File:** `manga_ai_studio/gui/main_window.py:1268-1282`
**Issue:**
`_on_inpaint_finished` does:

```python
original_patch_numpy = None
if self.history is not None and bbox is not None:
    x1, y1 = int(bbox[0]), int(bbox[1])
    try:
        original_patch_numpy = self.canvas.get_image_numpy()  # FULL image (H, W, 3)
    except Exception:
        original_patch_numpy = None

self.canvas.set_image_from_numpy(result_rgb, bbox=bbox)

if self.history is not None and bbox is not None and original_patch_numpy is not None:
    try:
        self.history.push_image_action(x1, y1, original_patch_numpy)  # pushes FULL image
    except Exception:
        pass
```

`original_patch_numpy` is the **entire page** (e.g. `(16, 16, 3)` or `(2000, 3000, 3)`), not the bbox sub-region. It is then passed to `push_image_action(x1, y1, patch)` with `x1, y1` = the bbox's top-left offset (e.g. 4, 4).

When `HistoryManager.pop_image_undo(current_img)` is later invoked (Ctrl+Z), it does:

```python
x, y, patch = self._image_undo.pop()
h, w = patch.shape[:2]        # reads the FULL image dims (e.g. 16, 16 or 2000, 3000)
redo_patch = current_img[y : y + h, x : x + w].copy()  # slices [4:20, 4:20] - OOB silent truncation
return (x, y, patch.copy())   # returns the FULL image masquerading as a patch at (4, 4)
```

Then `canvas.apply_undo_image(4, 4, full_image)` does:

```python
x0 = max(0, 4); y0 = max(0, 4)
x1 = min(w_img, 4 + pw); y1 = min(h_img, 4 + ph)  # destination rect [4:20, 4:20] clamped to image
sub = patch_np[0:12, 0:12]   # WRONG source sub-rect — top-left 12x12 of the FULL image
current[y0:y1, x0:x1] = sub  # writes pre-inpaint data into a 12x12 region
```

**Effect:** the undo "restores" the wrong region — it writes the top-left 12x12 (or `(H-4) x (W-4)`) of the pre-inpaint image into the bottom-right region starting at the bbox's offset, NOT the actual inpainted bbox. On a real 2000x3000 manga page with a small inpaint bbox at (100, 200, 50, 30), Ctrl+Z corrupts a 1900x2900 region with the wrong source data.

The existing test `test_inpaint_pushes_image_history` only stubs `history` with a fake that records the call — it never asserts the patch shape matches `bbox[2:]`. So the bug is not caught.

**Fix:**
```python
original_patch_numpy = None
if self.history is not None and bbox is not None:
    x, y, w, h = (int(v) for v in bbox)
    try:
        full = self.canvas.get_image_numpy()
        if full is not None:
            # Capture ONLY the bbox region — what was on the canvas before inpaint.
            original_patch_numpy = full[y : y + h, x : x + w].copy()
    except Exception:
        original_patch_numpy = None

self.canvas.set_image_from_numpy(result_rgb, bbox=bbox)

if self.history is not None and bbox is not None and original_patch_numpy is not None:
    x, y, _, _ = (int(v) for v in bbox)
    try:
        self.history.push_image_action(x, y, original_patch_numpy)
    except Exception as exc:
        logger.error(f"history.push_image_action failed: {exc}")
```

Also widen the regression test (`test_inpaint_pushes_image_history`) to assert `patch.shape[:2] == (bbox_h, bbox_w)`.

---

### CR-04: `torch_impl.py` eagerly imports torch at module top, contradicting its own lazy-import claim (D-07)

**File:** `manga_ai_studio/adapters/torch_impl.py:41-42`
**Issue:**
The module docstring (lines 5-7) claims:

> ``torch`` is imported **lazily inside load()** so this module is importable in the main_env without the torch dependency installed (D-07 frontend/backend split).

But the module top-level imports:

```python
from panelcleaner.comic_text_detector.inference import TextDetector
from panelcleaner.comic_text_detector.utils.textmask import REFINEMASK_ANNOTATION
```

And `panelcleaner/comic_text_detector/inference.py:8` does `import torch` at **module top-level**. So importing `torch_impl` transitively imports torch. Verified directly:

```
$ python3 -c "import sys; before=set(sys.modules); from manga_ai_studio.adapters.torch_impl import TorchCTDModel; print('torch loaded:', 'torch' in set(sys.modules)-before)"
torch loaded: True
```

This breaks the D-07 frontend/backend split claim: the frontend env (PySide6 + numpy only) cannot import `torch_impl` without torch installed. The factory correctly lazy-imports `torch_impl`, so the runtime path from the GUI is safe — but:

1. The docstring is false; future maintainers will trust it.
2. `tests/test_detection/test_ctd_adapter.py:22` and `tests/test_lama_adapter.py:26` import `torch_impl` directly at module top-level, forcing torch into the test environment regardless of whether the test is mocking torch.
3. The `adapters/__init__.py:12` line `from manga_ai_studio.adapters.base import ...` and the factory's structure suggest the package was designed for torch-optional import, which is not honored.

**Fix:**
Defer the `TextDetector` import into `load()` (it is only needed to construct the detector). `REFINEMASK_ANNOTATION` is just an int constant — re-declare it locally or import it from a torch-free path.

```python
# Module top-level — no torch pull.
from manga_ai_studio.adapters.base import DetectionModel, InpaintModel

# REFINEMASK_ANNOTATION is `1` per panelcleaner/comic_text_detector/utils/textmask.py:15.
# Re-declare locally to avoid the transitive `inference -> torch` import.
REFINEMASK_ANNOTATION = 1

class TorchCTDModel(DetectionModel):
    def load(self, model_path, device="cpu"):
        ...
        # Lazy import (D-07) — torch + TextDetector pulled here, not at module import.
        from panelcleaner.comic_text_detector.inference import TextDetector
        self.detector = TextDetector(...)
```

If preserving the import path for type-checking is desired, gate it behind `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from panelcleaner.comic_text_detector.inference import TextDetector
```

---

## Warnings

### WR-01: `inpaint()` entry point checks `has_mask()` instead of `has_mask_content()`

**File:** `manga_ai_studio/gui/main_window.py:1180`
**Issue:**
The action-gating logic in `_refresh_action_states` (line 471) correctly requires `has_mask_content` (the cheap alpha-scan) before enabling the Inpaint action. But the `inpaint()` method itself only checks `has_mask()`:

```python
def inpaint(self) -> None:
    if self._op_running:
        return
    path = self.file_table.current_path()
    if path is None:
        return
    if not self.canvas.has_mask():
        return
    # ... proceeds to extract mask_binary and dispatch worker
```

`has_mask()` is True for any mask QImage (including the fresh transparent initialization after `set_image`). If `inpaint()` is invoked programmatically (or via the `C` shortcut while the action is incorrectly enabled, e.g. during a race with `_op_running` clearing), the worker is dispatched with an all-zero mask and `compute_mask_bbox` returns `None`. The downstream `set_image_from_numpy(result_rgb, bbox=None)` replaces the whole image rather than compositing a region, and `push_image_action` is skipped — so the user gets no undo for a wasted model load.

**Fix:**
```python
if not self.canvas.has_mask_content():
    return
```

Mirror the action-state gate. Defense-in-depth: the action is already disabled, but a programmatic call (e.g. test, future scripting hook) should not waste a model load.

---

### WR-02: `set_image_from_numpy` and `apply_undo_image` silently truncate out-of-bounds bbox/patch without warning

**File:** `manga_ai_studio/gui/canvas.py:531-536, 451-461`
**Issue:**
In `set_image_from_numpy`, the bbox compositing step does:

```python
x, y, w, h = bbox
base = self._original_image_numpy
if base is not None and base.shape[:2] == (rgb.shape[0], rgb.shape[1]):
    base = base.copy()
    base[y : y + h, x : x + w] = rgb[y : y + h, x : x + w]  # silent OOB truncation
    full_rgb = base
```

If `bbox = (x, y, w, h)` with `x + w > base.shape[1]` or `y + h > base.shape[0]`, numpy silently truncates the slice. The assignment's LHS and RHS end up different sizes only if `rgb` is also different — otherwise the same truncation applies to both sides and the write succeeds with a smaller-than-expected region. No error, no log. A future caller (e.g. a "inpaint selection" feature) that passes a stale bbox after the canvas image was resized will silently lose data.

Similarly in `apply_undo_image` (canvas.py:451-461), the bounds check clips to the image rect but does not log when clipping happens — a stale history entry after a page crop silently mis-composites.

**Fix:**
Add a cheap bounds check that logs (or raises) when the bbox/patch exceeds the image:

```python
H, W = base.shape[:2]
if x < 0 or y < 0 or x + w > W or y + h > H:
    logger.warning(f"bbox {bbox} out of bounds for image {(H, W)}; truncating")
base[y : y + h, x : x + w] = rgb[y : y + h, x : x + w]
```

For an MVP this is acceptable as long as the only caller (`_on_inpaint_finished`) constructs the bbox from `compute_mask_bbox` over the same image — but the contract should be explicit.

---

### WR-03: Worker tasks accept `abort_flag` but never poll it; abort is documented but non-functional

**File:** `manga_ai_studio/gui/main_window.py:998-1037, 1210-1237`
**Issue:**
Both `_run_detection_task` and `_run_inpaint_task` declare `abort_flag=None` in their signatures (lines 1003 and 1217) — but neither function ever checks `abort_flag.get()` or raises `Abort`. The `Worker.__init__` only injects `abort_flag` into kwargs if an `abort_signal` is passed (worker_thread.py:138), and neither `detect_text()` nor `inpaint()` passes an `abort_signal`. So:

1. The `abort_flag` parameter is always `None` in practice.
2. Even if it were wired, neither task would actually abort.

This is a documentation/contract mismatch: the worker infrastructure (and the `_run_*_task` docstring comments about T-01-07 abort) suggests abort is supported, but it is not.

**Fix (minimal — defer real abort to a later phase):**
Either (a) remove `abort_flag=None` from both task signatures and the docstring claims about abort, or (b) add the missing checks at each progress emission point:

```python
if abort_flag is not None and abort_flag.get():
    raise Abort()
```

plus pass `abort_signal=some_signal` in the `Worker(...)` constructor and wire a UI button to emit it. Option (a) is the MVP-appropriate fix.

---

### WR-04: `HistoryManager` uses `list.pop(0)` to drop the oldest entry — O(n) shift on every overflow

**File:** `manga_ai_studio/core/history_manager.py:84, 127`
**Issue:**
Both `push_mask_state` and `push_image_action` do:

```python
self._mask_undo.append(mask_qimage.copy())
self._mask_redo.clear()
if len(self._mask_undo) > self.limit:
    self._mask_undo.pop(0)  # O(n) — shifts every remaining element
```

`list.pop(0)` is O(n). At the default `limit=20` this is negligible, but if the limit is raised (e.g. to 100 in a future "Power user" profile), every push after saturation does an O(100) shift. Out of v1 performance scope per the review rules, but flagging because it is a one-line fix to a real (if minor) cost and the test `test_stack_limit_drops_oldest` exercises this exact path.

**Fix:**
Use `collections.deque(maxlen=limit)` instead of `list`, which drops the oldest entry automatically in O(1):

```python
from collections import deque
self._mask_undo: deque[QImage] = deque(maxlen=limit)
# ... append() auto-drops the oldest when full; remove the manual pop(0) check.
```

If preserving list semantics for tests, the existing code is acceptable for `limit=20`.

---

### WR-05: `_on_inpaint_finished` wraps `push_image_action` in bare `except Exception: pass` — swallows real bugs

**File:** `manga_ai_studio/gui/main_window.py:1278-1282`
**Issue:**
```python
if self.history is not None and bbox is not None and original_patch_numpy is not None:
    try:
        self.history.push_image_action(x1, y1, original_patch_numpy)
    except Exception:
        pass
```

A bare `except Exception: pass` with no log swallows any failure in the history push — including the data-corruption bug in CR-03 (which does not raise, but a future fix that adds shape validation would). Same anti-pattern in CR-01/CR-02. The docstring for `_on_inpaint_finished` says "Phase 1 no-ops this (`self.history is None`)" — but the code now unconditionally wires history, so the comment is stale and the bare except hides real errors.

**Fix:**
```python
try:
    self.history.push_image_action(x1, y1, original_patch_numpy)
except Exception as exc:
    logger.error(f"History push failed (undo may be unavailable): {exc}")
```

At minimum log the failure; ideally narrow to the expected exceptions.

---

### WR-06: `_make_recent_opener` lambda captures `path` correctly, but `_make_tool_toolbar_button` / `set_active_tool` may leave stale checked state

**File:** `manga_ai_studio/gui/main_window.py:892-910`
**Issue:**
`set_active_tool` syncs the toolbar buttons by matching `act.data() == tool`. But the toolbar also contains non-tool `QToolButton`s created via `addWidget(self._make_tool_toolbar_button(...))`. The `findChildren(QToolButton)` call in `set_active_tool` finds all of them, including the preview-hold button. The loop correctly skips them because their `defaultAction()` returns None or a non-tool action, but the `btn.setChecked(True)` call only runs for matching actions — other tool buttons are never explicitly unchecked. If the action group's exclusivity is broken (e.g. by a future addition of a non-exclusive checkable tool button), stale checked state could persist.

The code currently works because `QActionGroup.setExclusive(True)` handles unchecking — but the loop relies on a side effect rather than explicitly unchecking.

**Fix:**
Either (a) add an explicit `else: btn.setChecked(False)` branch for clarity, or (b) document that the action group's exclusivity is the contract that keeps this correct.

---

### WR-07: `EditorCanvas.set_image` initializes mask as `Format_ARGB32` but `set_mask` rebuilds it as `Format_ARGB32` with BGRA byte ordering — format drift

**File:** `manga_ai_studio/gui/canvas.py:235, 313, 328`
**Issue:**
`set_image` (line 235) initializes `self._mask` as `QImage.Format.Format_ARGB32` filled with `Qt.GlobalColor.transparent`. Then `set_mask` (line 313) does `mask_qimage.convertToFormat(QImage.Format.Format_ARGB32)` and reads `arr[:, :, 2] > 0` (R channel in BGRA byte order) — relying on Qt's little-endian ARGB32 == BGRA byte order.

On a big-endian system (rare but supported by Qt), ARGB32 byte order is actually A,R,G,B in memory, so `arr[:, :, 2]` would be the B channel, not R. The code's `mask_pixels = arr[:, :, 2] > 0` and `out[mask_pixels] = [0, 0, 255, 160]` comments call out "BGRA byte order" which is little-endian-specific.

In practice this works on Windows / x86 / Apple Silicon (all little-endian), and the test suite passes there. But the dependency on host endianness is undocumented and would silently break on a big-endian Qt build.

**Fix:**
Either (a) use `Format_RGBA8888` (which has explicit byte order R,G,B,A regardless of host endianness, as `mask_to_numpy_binary` already does) consistently, or (b) document the little-endian assumption in a constant and assert at startup:

```python
import sys
assert sys.byteorder == "little", "ARGB32 byte-order assumptions require little-endian host"
```

---

## Info

### IN-01: Unused imports in `gui/main_window.py`

**File:** `manga_ai_studio/gui/main_window.py:37, 53`
**Issue:**
- Line 37: `QImage` is imported but only used in `_on_detection_finished` (which re-imports `numpy` rather than `QImage` — `QImage` is actually used at line 1080, so this one is fine).
- Line 53: `mask_to_numpy_binary` is used at line 1187 (fine).
- Line 33: `import numpy as np` is at module top, but `_on_detection_finished` does `import numpy as np` again locally (line 1072). Redundant.
- Line 399: `from PySide6.QtGui import QFont` is inside `_build_status_bar` (local import) while `QFont` is already used at line 165-172 in `canvas.py` — but for `main_window.py` this is a local function-scoped import that could be hoisted.

These are style nits; behavior is correct.

**Fix:** Hoist function-local imports to module top where the import is always reached; remove the redundant `import numpy as np` at line 1072.

---

### IN-02: `_on_detection_progress` accepts a payload of unknown shape without validating it came from the worker

**File:** `manga_ai_studio/gui/main_window.py:1055-1062`
**Issue:**
```python
def _on_detection_progress(self, payload) -> None:
    if isinstance(payload, tuple) and len(payload) == 2:
        percent, message = payload
    else:
        return
    ...
```

The early-return on malformed payload is correct defense, but `message` is bound and never used (the status bar uses `int(percent)` only). Minor: either use the message in the status bar copy or remove it from the unpack.

**Fix:**
```python
percent, _message = payload
self.progress_bar.setValue(int(percent))
self.status_bar_left.setText(f"Detecting text… {int(percent)}%")
```

Use `_message` prefix to signal "intentionally unused", or actually surface it in the status bar.

---

### IN-03: `ToolsPanel._on_tool_triggered` is defined but never connected

**File:** `manga_ai_studio/gui/tools_panel.py:211-215`
**Issue:**
`_on_tool_triggered` is a method on `ToolsPanel` but is never wired to `self.tool_group.triggered`. The active emission path is `_on_action_toggled` (line 217), which is connected per-action at line 138-139. `_on_tool_triggered` is dead code.

**Fix:** Remove `_on_tool_triggered` (lines 211-215) since `_on_action_toggled` covers both user clicks and programmatic `setChecked(True)` calls.

---

### IN-04: `EditorCanvas._disable_qimage_allocation_limit()` runs at module import — global side effect

**File:** `manga_ai_studio/gui/canvas.py:77-86`
**Issue:**
```python
def _disable_qimage_allocation_limit() -> None:
    QImageReader.setAllocationLimit(0)

# Apply once at import time
_disable_qimage_allocation_limit()
```

This is a **process-global** side effect: any test or downstream code that imports `manga_ai_studio.gui.canvas` disables Qt's 128MB allocation cap for the entire process. The function is called once at module top, which is fine for the application, but in a test suite that mixes Manga AI Studio imports with other Qt code (or with tests that deliberately want the allocation cap), this is surprising global state.

The behavior is intentional (UI-SPEC surface 2 large-image safety) and well-documented, so this is informational only — not a bug.

**Fix (optional):** If isolation is desired, move the call into `EditorCanvas.__init__` or `app.create_app`, gated by a flag, so import alone does not mutate global Qt state.

---

### IN-05: `_on_show_original_toggled` toggles via `action.toggled`, but `action_show_original` is also checkable — double signal path possible

**File:** `manga_ai_studio/gui/main_window.py:247, 1310-1318`
**Issue:**
`action_show_original` is `setCheckable(True)` and its `toggled` signal is connected to `_on_show_original_toggled`. The Preview (hold) button (`btn_preview_hold`) also calls `canvas.show_original(True/False)` directly via `pressed`/`released`. If the user holds Preview while the sticky P action is also toggled, the two paths race — releasing Preview calls `show_original(False)` even though the sticky toggle is still checked.

Not a bug per se (the canvas just follows the most recent call), but the two controls can get out of sync visually. The action's checked state is not updated when the hold button drives `show_original(False)`.

**Fix:** Either (a) disable the sticky action while the hold button is pressed, or (b) when `show_original(False)` is called from the hold-release, also uncheck the sticky action. Acceptable as-is for MVP.

---

### IN-06: `tests/test_detection/test_ctd_adapter.py:156` imports `QMessageBox` but never uses it

**File:** `tests/test_detection/test_ctd_adapter.py:160`
**Issue:**
Line 160: `from PySide6.QtWidgets import QMessageBox  # noqa: E402`. Never referenced in any test in this file. Dead import.

**Fix:** Remove the unused import.

---

### IN-07: `ProfileManager.profile_to_config` docstring contradicts the implementation

**File:** `manga_ai_studio/config/profile_manager.py:51-68`
**Issue:**
The docstring says:
> ``Config.from_config_updater`` (config.py:1310) is NOT the right tool here — it parses a full application ``config.ini``...

But the implementation simply does:

```python
config = Config()
config.current_profile = profile
return config
```

The `Config()` default constructor may not initialize `default_torch_model_path` / `default_cv2_model_path` correctly, and downstream `get_model_cache_dir()` may return a path that doesn't exist. This is fine for Phase 1's profile round-trip tests (which only assert `current_profile`), but any code that calls `config.get_model_cache_dir()` on the result (e.g. CR-01 / CR-02 fixes) needs the Config to be fully initialized.

**Fix:** Either document that the returned `Config` has default model paths (so callers must call `Config.load_profile` or set them explicitly), or initialize them from the profile here.

---

### IN-08: `panelcleaner/inpainting.py` (Tier B) imports `loguru.logger` but never uses it

**File:** `panelcleaner/inpainting.py:16`
**Issue:**
Line 16: `from loguru import logger`. Never referenced in the trimmed 51-line file. The original PanelCleaner `inpainting.py` uses logger elsewhere; the trim dropped those uses but kept the import.

**Fix:** Remove the unused import (line 16). Confirms the trim is otherwise faithful to the upstream contract — the `__init__` and `__call__` shape matches `TorchLamaModel`'s claims exactly.

---

## Notes on the documented pitfall patterns

The context asked me to specifically verify six pitfall patterns. Findings:

1. **Pitfall 2 (numpy ↔ QImage buffer aliasing):** Correctly handled at every bridge site. `mask_to_numpy_binary`, `numpy_binary_to_mask_qimage`, `set_mask`, `set_image_from_numpy`, `show_original`, `get_image_numpy`, and both history push/pop paths all enforce `.copy()` detachment. Regression guards `test_numpy_extract_copies_buffer`, `test_mask_snapshot_is_copied`, `test_mask_pop_returns_copy`, `test_inpaint_result_display_uses_copy` lock the discipline. **No defects.**

2. **3-tuple contract:** Verified at source (`panelcleaner/comic_text_detector/inference.py:210` returns `mask, mask_refined, blk_list`). `TorchCTDModel.detect` (torch_impl.py:124) unpacks exactly 3 targets with `refine_mode=REFINEMASK_ANNOTATION, keep_undetected_mask=True`. Regression guard `test_3_tuple_unpack_contract` locks it. **No defects.**

3. **PySide6 vs PyQt5 drift:** The codebase correctly handles `constBits()` returning memoryview (canvas.py:317, 363, 490; mask_editor.py:183), uses `QActionGroup.toggled` per-action rather than `triggered` (tools_panel.py:138 — though see IN-03 about the dead `_on_tool_triggered`), uses `mapToScene(QPoint)` via `.toPoint()` (canvas.py:829), and uses custom QMessageBox buttons rather than the missing `Replace` standard member (main_window.py:1124-1128). The `setTransformationAnchor(ViewportAnchor.AnchorUnderMouse)` enum path is also correct. **No new drift detected.**

4. **Async Worker infrastructure:** Worker(QRunnable) is correctly structured; the `RuntimeError` catch for deleted-during-shutdown signals is preserved (worker_thread.py:166). However, see **WR-03** — abort_flag is documented but never polled by either task.

5. **History snapshot discipline:** `HistoryManager` correctly `.copy()`s on push AND pop. `apply_undo_mask` correctly does NOT re-emit `mask_modified` (regression guard `test_undo_does_not_repush` locks this). However, see **CR-03** — the IMAGE history push stores the wrong data (full image instead of bbox patch).

6. **Path validation:** `validate_image_path` correctly resolves + suffix-allowlists; `validate_image_size` enforces the 10000x10000 cap; drag-drop filters through `validate_image_path` again. Model paths are validated with `is_file()` before backend construction (T-01-04 / T-01-04b). However, see **CR-01 / CR-02** — the resolver functions upstream of those guards are broken.

---

_Reviewed: 2026-07-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---
phase: 05-project-persistence-image-ops-export
reviewed: 2026-08-08T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - manga_ai_studio/core/project_io.py
  - manga_ai_studio/core/image_ops.py
  - manga_ai_studio/core/ocr_export.py
  - manga_ai_studio/core/history_manager.py
  - manga_ai_studio/core/image_file.py
  - manga_ai_studio/core/image_io.py
  - manga_ai_studio/core/mask_editor.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/tools_panel.py
  - manga_ai_studio/gui/levels_dialog.py
  - manga_ai_studio/gui/resize_dialog.py
  - manga_ai_studio/gui/crop_dialog.py
findings:
  critical: 3
  warning: 6
  info: 4
  total: 13
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-08-08T00:00:00Z
**Depth:** standard
**Files Reviewed:** 13 (production source; the 14 test files were spot-checked for scenario coverage)
**Status:** issues_found

## Summary

Reviewed the full Phase 5 implementation: the `.mas` LZMA2 container + PageBox mapping (`project_io.py`), the pixel/geometry transform module (`image_ops.py`), the D-19/D-20/D-22 `_ocr.json` exporter (`ocr_export.py`), the stamp-shared geometry undo records (`history_manager.py`), and the GUI session/apply layers (`main_window.py`, `canvas.py`, dialogs, `tools_panel.py`).

The container format, the untrusted-input validation on the disk boundary, the geometry transform math, and the stamp-shared triple-stack undo are well executed and internally consistent. However, three BLOCKER-grade defects undermine the phase's core contract ("resume exactly where you left off", D-05/D-15):

1. **Image edits on non-current pages are silently lost** — the post-op image is never written back into `ImageFile.current_image`, navigation re-loads the pre-op image from disk, and `_page_image_source` prefers disk sources over the in-memory state at save time. Rotate/crop/resize/levels/inpaint on any page that is then navigated away from produces a saved project containing the pre-op image with post-op boxes — misaligned geometry and lost work.
2. **Open Folder / Open Image does not clear the project identity** — after working in a project, opening a folder and pressing Ctrl+S silently overwrites the previous project folder.
3. **A corrupt/crafted `.mas` mask entry crashes the app** instead of surfacing the corrupt-project dialog — the mask reshape raises a raw `ValueError` that escapes the `ProjectFormatError` boundary.

## Critical Issues

### CR-01: Image edits on non-current pages are lost on navigation and on project save (D-05/D-15 contract break)

**File:** `manga_ai_studio/gui/main_window.py:1122, 1135, 1514-1541, 1565-1583, 1845-1855`

**Issue:** Three coordinated gaps make every image op (rotate/crop/resize/levels AND inpaint) evaporate for any page that is not the current page at save/navigation time:

1. `_apply_geometry_op` calls `_snapshot_current_page()` at line 1122 — which writes the **pre-op** canvas into `ImageFile.current_image` — and never updates `current_image` with the post-op image after the `set_image_from_numpy(new_image)` write-back at line 1135. `_on_inpaint_finished` (line 3589) likewise never updates `current_image`.
2. `on_page_selected` (Step 1/1b, lines 1514-1541) persists only the outgoing page's **mask and boxes** — never the canvas image. On return to the page, Step 3 (lines 1565-1583) falls into `set_image_from_path(path)` for verified originals, i.e. the **pre-op** disk image is displayed again (for folder sessions the op is permanently gone from view; undo history was reset at Step 2).
3. `_page_image_source` (lines 1845-1855) prefers `cleaned/<name>` and then the raw source file over `ImageFile.current_image` for non-current pages — so a save after rotating page 2 and navigating to page 3 embeds the **pre-rotation** image (and `geometry_altered=True` plus post-op boxes are stored against it — reload shows boxes misaligned with the image).

Repro: open a folder, rotate page 2, click page 3, click page 2 → the rotation is gone. Or: rotate page 2, click page 3, Ctrl+S, reopen → page 2's saved image is the original, boxes misaligned. This breaks the phase's primary requirement (PROJ-01 "resume exactly where you left off" and D-15 "geometry ops are lossless to prior work").

**Fix:** (a) after the write-back, refresh the model: in `_apply_geometry_op` add `idx = self._current_page_index(); if idx is not None: self.image_files[idx].current_image = new_image.copy()` (same in `_on_inpaint_finished` after `set_image_from_numpy`); (b) in `on_page_selected` Step 3, prefer `imf.current_image` when it is not `None` (it is the authoritative current state — a disk re-load must be the fallback, not the primary path); (c) in `_page_image_source`, return `imf.current_image` first when present:
```python
imf = self.image_files[idx]
if imf.current_image is not None:
    return imf.current_image
cleaned = imf.path.parent / "cleaned" / imf.path.name
if cleaned.is_file():
    return np.asarray(Image.open(cleaned).convert("RGB")).copy()
if imf.path.is_file():
    return np.asarray(Image.open(imf.path).convert("RGB")).copy()
return None
```

### CR-02: Open Folder / Open Image leaves stale project identity — Ctrl+S silently overwrites the previous project

**File:** `manga_ai_studio/gui/main_window.py:1449-1470` (`_set_pages`); compare `2243-2244` (`_load_single_page_mas` clears them)

**Issue:** `_set_pages` (used by `open_image`, `open_folder`, `_load_folder`, `_open_single_image`) rebuilds `self.image_files` but never resets `self._project_dir` / `self._project_name`. Only `_load_single_page_mas` clears them (lines 2243-2244). Consequence: open Project A → Open Folder B (the Unsaved-Changes gate is skipped when A is clean) → Ctrl+S → `_save_project` (lines 1878-1891) reuses the stale `self._project_dir` (A's folder) and stale `self._project_name` (A's name) and **overwrites Project A's manifest + same-stem `.mas` files with folder B's pages** — silent data loss of project A.

**Fix:** reset the project identity whenever a non-project session is established:
```python
def _set_pages(self, paths: list[Path]) -> None:
    ...
    self.image_files = [ImageFile(path=p, original_verified=True) for p in ordered]
    self._project_dir = None
    self._project_name = None
    ...
```

### CR-03: Corrupt `.mas` mask entry escapes the ProjectFormatError boundary and crashes the app

**File:** `manga_ai_studio/core/project_io.py:447-449`; `manga_ai_studio/gui/main_window.py:2004-2014`

**Issue:** `parse_page_entries` reshapes `mask.bin` via `np.frombuffer(mask_bytes, dtype=np.uint8).reshape(int(mask_meta["h"]), int(mask_meta["w"]))` without checking that `len(mask_bytes) == h * w`. `validate_meta` validates the declared dims against each other and `MAX_IMAGE_DIMENSION`, but never against the blob length. A crafted or corrupted `.mas` whose `mask.bin` length does not match its declared dims raises a raw `ValueError` ("cannot reshape array of size N into shape (h,w)"). `parse_page_entries` converts only JSON decode errors (lines 430-433); `_open_project` catches only `(ProjectFormatError, OSError)` (line 2004). The `ValueError` therefore propagates out of the Qt event handler as an unhandled exception → application crash — precisely the failure mode T-05-01..T-05-04 exist to prevent ("every malformed-input failure surfaces as ProjectFormatError"). (A PIL `DecompressionBombError` on a huge embedded PNG is a second uncaught path, though the 512 MiB decompress memlimit bounds it in practice.)

**Fix:**
```python
mask_h = int(mask_meta["h"])
mask_w = int(mask_meta["w"])
if len(mask_bytes) != mask_h * mask_w:
    raise ProjectFormatError(
        f"mask.bin length {len(mask_bytes)} does not match declared "
        f"dims {mask_h}x{mask_w}"
    )
mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(mask_h, mask_w).copy()
```
and in `_build_image_file_from_parsed` also convert `Image.DecompressionBombError` to `ProjectFormatError`.

## Warnings

### WR-01: Unsaved-Changes gate proceeds after a failed Save when a project dir already exists

**File:** `manga_ai_studio/gui/main_window.py:2163-2167`

**Issue:** The Save branch of `_confirm_discard_changes` does `self._save_project(); return self._project_dir is not None`. If the session already has a project dir (a previous save succeeded) and the current save **fails** (disk full, unwritable), `_project_dir` is still non-None → the method returns True → the session is replaced and the unsaved edits are lost, despite the failure dialog.

**Fix:** make `_save_project` return a success bool and key the gate on it:
```python
if clicked is save_btn:
    return self._save_project()  # False on failure/abort
```

### WR-02: All-pages-skipped save "succeeds" with an empty manifest and clears the dirty flags

**File:** `manga_ai_studio/gui/main_window.py:1893-1948`

**Issue:** When every page's image source is unresolvable (`_page_image_source` returns None for all — e.g. originals deleted before a folder session's first save), `page_files` is empty, `save_project` writes a 0-page manifest, all `dirty` flags are cleared, and the status flashes "Saved project 'name' (0 pages)." Reopening that project fails with "project contains no pages" — the user believes the session was saved; it is gone.

**Fix:** abort with an error dialog when `not page_files` (before writing), and leave the dirty flags untouched.

### WR-03: Duplicate page stems silently collide on save — one `.mas` overwrites the other

**File:** `manga_ai_studio/gui/main_window.py:1911-1925`; `manga_ai_studio/core/project_io.py:358-359`

**Issue:** A folder containing `page.png` and `page.jpg` produces two entries with stem `page`; `save_project` writes both to `page.mas` (second overwrites the first) and the manifest lists two pages pointing at the same file. On reload both pages show the same image.

**Fix:** detect duplicate stems in `_save_project` before writing and surface a save error listing the colliding pages.

### WR-04: Show Original (D-06) gating goes stale after page navigation

**File:** `manga_ai_studio/gui/main_window.py:1648-1659`

**Issue:** `on_page_selected`'s tail never calls `_refresh_action_states`. Navigating from a page with a verified original to a page with an unverified original (portable `.mas` project, D-06) leaves `action_show_original` in the previous page's enabled state — the option D-06 requires greyed-out stays active (and shows the embedded image, a no-op toggle).

**Fix:** call `self._refresh_action_states()` at the end of `on_page_selected`.

### WR-05: Identity resize marks the page geometry-altered and pushes a no-op undo entry

**File:** `manga_ai_studio/gui/main_window.py:1262-1281`

**Issue:** Applying the resize dialog with unchanged dims (e.g. 100% in percent mode, or typing the current dims) still runs the full op: pushes an IMAGE-stack undo entry, re-baselines Show Original, and sets `ImageFile.geometry_altered = True` — which flips the D-22 `_ocr.json` export location from a sidecar to `cleaned/` for a page with no actual geometry change.

**Fix:** no-op when `(new_w, new_h) == (w_img, h_img)`:
```python
if (new_w, new_h) == (w_img, h_img):
    return
```

### WR-06: `meta.json` image dims are never cross-checked against the actual embedded PNG

**File:** `manga_ai_studio/core/project_io.py:425-458`; `manga_ai_studio/gui/main_window.py:2095-2105`

**Issue:** `validate_meta` validates the declared `img`/`mask` dims against each other and the 10000 cap, but the decoded `image.png` is never compared to the declared dims. A crafted file declaring 100x100 with a 10000x10000 PNG passes validation; the mask is reshaped to 100x100 and the canvas displays 10000x10000 — the restored mask is misaligned with the displayed image (and `img_width`/`img_height` in the exported `_ocr.json` come from the canvas while the mask bbox coordinates come from the model — inconsistent output).

**Fix:** in `_build_image_file_from_parsed` (or `parse_page_entries`), compare the decoded PNG dims to `meta["img"]` and raise `ProjectFormatError` on mismatch.

## Info

### IN-01: Dead code — `ToolsPanel._on_tool_triggered`

**File:** `manga_ai_studio/gui/tools_panel.py:223-227`

The `_on_tool_triggered` slot is never connected (`QActionGroup.triggered` is not wired; only the per-action `toggled` path at line 150 is). Either connect it or remove it.

### IN-02: `_coerce_int` accepts booleans

**File:** `manga_ai_studio/core/project_io.py:79-91`

`int(True)` == 1, so a JSON `true` in an integer field (e.g. `img.w`) silently becomes a 1px dimension instead of being rejected as type confusion. Guard with `isinstance(value, bool)` first for strictness (the box_model V5 discipline this function claims to mirror).

### IN-03: `json_to_pagebox` does not validate quad point counts or `text`/`translation` types

**File:** `manga_ai_studio/core/project_io.py:246-261`

Line quads are accepted with any point count (`[[x,y],[x2,y2]]` passes) and `text`/`translation` are not type-checked. A non-str/non-list `text` from a crafted file survives load and crashes at export time (`_payload_text` returns it unchanged, then `text.split("\n")` in `split_text_onto_lines` raises `AttributeError` — note the list-join at ocr_export.py:89-92 covers lists but not other types).

### IN-04: Batch OCR export progress never reaches 100%

**File:** `manga_ai_studio/core/ocr_export.py:337`

`int(i / total * 100)` for the last page yields `int((total-1)/total*100)` (e.g. 66 for 3 pages) — the progress bar stalls below 100% on completion. Use `int((i + 1) / total * 100)` (cosmetic; the completion status text is correct).

---

_Reviewed: 2026-08-08T00:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_

**Status: issues_found — 3 critical, 6 warnings, 4 info. The three critical defects (non-current-page image-state loss, stale project identity overwriting projects on Ctrl+S, and the uncaught reshape crash on corrupt `.mas` input) must be fixed before this phase ships.**

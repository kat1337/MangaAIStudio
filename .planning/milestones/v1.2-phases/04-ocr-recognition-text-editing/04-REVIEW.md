---
phase: 04-ocr-recognition-text-editing
reviewed: 2026-08-06T12:00:00Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - manga_ai_studio/adapters/factory.py
  - manga_ai_studio/adapters/torch_impl.py
  - manga_ai_studio/core/box_model.py
  - manga_ai_studio/core/reading_order.py
  - manga_ai_studio/core/translation_parser.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/inline_editor.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/load_translations_dialog.py
  - manga_ai_studio/gui/main_window.py
  - panelcleaner/ocr/ocr_mangaocr.py
  - tests/test_box_snapshot_fields.py
  - tests/test_core/test_adapters.py
  - tests/test_core/test_box_model.py
  - tests/test_core/test_history_boxes.py
  - tests/test_core/test_reading_order.py
  - tests/test_core/test_torch_ocr_model.py
  - tests/test_core/test_translation_parser.py
  - tests/test_detection/test_ctd_adapter.py
  - tests/test_gui_boxes.py
  - tests/test_gui_canvas.py
  - tests/test_payload_aliasing.py
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-08-06T12:00:00Z
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

Reviewed the Phase 4 OCR Recognition & Text Editing implementation: the PageBox text setters + payload-detaching `copy()` (box_model.py), the translation parser and XY-Cut reading-order algorithm (translation_parser.py, reading_order.py), the OCR/CTD/LaMa adapters and factory (torch_impl.py, factory.py, ocr_mangaocr.py), the BoxItem text overlay + bubble badge (box_item.py), the InlineEditor proxy (inline_editor.py), the InspectorPanel dock (inspector_panel.py), the LoadTranslationsDialog (load_translations_dialog.py), and the MainWindow OCR dispatcher / Text menu / Auto-Number wiring (main_window.py), plus the accompanying test suites.

The architecture is disciplined: payload-detach-before-mutate (Pitfall 8) is correctly applied at the inline-editor, OCR-finish, and Load-Translations commit sites; the duck-typed pure-python parser/algorithm modules are well isolated and headless-testable; threading discipline (worker touches only numpy, Qt mutation on main thread) is consistent. The test coverage for the new features is thorough.

One critical defect was found: the **Inspector commit path is the one mutation site that skips the Pitfall-8 payload detach** (which every sibling commit path performs), so undo of Inspector text/translation/vertical edits restores the post-edit state — a no-op undo. Five warnings cover spurious no-op Inspector commits, an XY-Cut cluster-fragmentation flaw, dead CTD threshold configuration, a None-boxes crash path in Load Translations, and an Inspector/inline-editor display desync.

## Critical Issues

### CR-01: Inspector commit pushes an aliased pre-edit snapshot — undo of Inspector edits is a no-op

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:1331-1343` (`_inspector_commit_pre`) and the commit handlers at 1360-1410

**Issue:** `_inspector_commit_pre` captures `boxes_snapshot()` but does **not** detach the payloads. `boxes_snapshot()` shares the live `TextBlock` payload by reference (canvas.py:1412), and `_on_inspector_recognized_committed` / `_on_inspector_translation_committed` / `_on_inspector_vertical_committed` then mutate that shared payload **in place** (`set_recognized_text_edited` / `set_translation` / `payload.vertical`) **before** `boxes_modified.emit(before)` reaches `_on_boxes_modified` → `history.push_boxes_state`. `HistoryManager._materialize_snapshot` runs `PageBox.copy()` at push time (history_manager.py:252-275), i.e. AFTER the mutation, so the stored snapshot captures the NEW text. Ctrl+Z therefore restores the post-edit text — a no-op undo that silently corrupts the undo contract for the primary text-editing surface.

This is exactly the Pitfall-8 push-side trap the codebase documents and guards everywhere else:
- `InlineEditor.commit` explicitly detaches: `for pb in before: if pb.payload is not None: pb.payload = _copy.copy(pb.payload)` (inline_editor.py:209-212).
- `_on_ocr_finished` (main_window.py:2614-2617) and `_on_ocr_all_finished` (2636-2639) detach.
- `_apply_translations` (2828-2831) detaches.

The Inspector path is the only commit site missing the detach, and no test exercises Inspector-commit undo (the Pitfall-8 tests cover push-time and the inline editor only).

**Fix:** Add the same detach loop to `_inspector_commit_pre`:

```python
def _inspector_commit_pre(self) -> "BoxItem | None":
    item = self.canvas._selected_box()
    if item is None:
        return None
    before = self.canvas.boxes_snapshot()
    for pb in before:
        if pb.payload is not None:
            pb.payload = copy.copy(pb.payload)  # Pitfall 8 — detach BEFORE the in-place setter mutation
    self._boxes_interaction_start_snapshot = before
    return item
```

## Warnings

### WR-01: Unchanged Inspector field focus-cycles still commit — spurious `edited=True`, accidental manual-override pinning, and no-op undo pushes

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\inspector_panel.py:114-126` and `315-317`; `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:1383-1396`

**Issue:** Neither `_CommitTextEdit.focusOutEvent` nor the `bubble_spin.editingFinished` wiring detects whether the value actually changed (the inline editor has such a check — `changed = new_text != self._entry_text`). Consequences:

1. Clicking into the Recognized field and clicking away with zero typing calls `set_recognized_text_edited(same_text)` → flips `edited=True` on a box the user never edited → the next Run OCR spuriously fires the D-04 "This box has text you edited" confirm prompt.
2. Every such focus cycle also pushes a no-op BOXES snapshot (stack pollution; undo pops a "restore to identical state" entry).
3. Clicking the Bubble # spinbox without changing it fires `editingFinished` → `_on_inspector_bubble_committed` writes `bubble_no` **and** `manual_override=True` — a box that never had a bubble number (load_box displays 1 for None) becomes pinned bubble 1 / manual-override, so Auto-Number will permanently skip it (D-16 preserve-manual engaged by accident).

**Fix:** Track the value loaded at `load_box` time (like InlineEditor's `_entry_text`) and skip the commit when unchanged. For the spinbox: only treat a commit as "manual" when `value != loaded_value`.

### WR-02: XY-Cut cluster walk measures gaps against the previous cluster START, not the previous box — spurious column fragmentation

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\core\reading_order.py:106-111`

**Issue:** The cluster walk does `if x - cluster_edges[-1] > col_tol: cluster_edges.append(x)` — each candidate x is compared to the previous **cluster start**, not the previous element. When a column's boxes cumulatively span more than `tol` (while every consecutive gap is `<= tol`), the column fragments into spurious columns. Repro: centers `[(0, 0), (39, 1), (78, 2)]` → gaps [39, 39], median 39 → `col_tol = max(40, 39) = 40`. Every consecutive gap (39) is within tol, so all three belong to ONE column, but the walk compares 78 against the cluster start 0 (78 > 40) → new edge at 78 → columns {0,39} and {78}. Real manga columns with 3+ stacked bubbles near the tolerance boundary will mis-split, producing wrong bubble-number sequences. (The docstring's "gap to the previous" reads as previous element.)

**Fix:** Track the previous element, not the previous cluster start:

```python
prev = unique_xs[0]
for x in unique_xs[1:]:
    if x - prev > col_tol:
        cluster_edges.append(x)
    prev = x
```

### WR-03: `TorchCTDModel.configure` stores `conf_thresh`/`nms_thresh` but `load()` never applies them

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\adapters\torch_impl.py:141-154` (configure) and `97-102` (load)

**Issue:** `configure()` accepts and stores `input_size`, `conf_thresh`, `nms_thresh`, and `act`, and the docstring promises "Applied on the next load()". `load()` passes only `input_size`, `device`, and `act` to `TextDetector` — `conf_thresh` and `nms_thresh` are silently dropped. Verified against the vendored constructor (`panelcleaner/comic_text_detector/inference.py:134-141`), which explicitly accepts `nms_thresh` and `conf_thresh` and uses them in `postprocess_yolo`. The adapter's contract is broken for two of its four knobs — dead configuration with a false docstring, and the app can never tune detection thresholds.

**Fix:**
```python
self.detector = TextDetector(
    model_path=str(model_path),
    input_size=self._input_size,
    device=self.device,
    act=self._act,
    conf_thresh=self._conf_thresh,
    nms_thresh=self._nms_thresh,
)
```

### WR-04: Load Translations onto a never-visited page crashes into a spurious error dialog

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:2852-2867`

**Issue:** The non-current-page branch calls `apply_translations(matches, self.image_files[page_index].boxes, ...)`. `ImageFile.boxes` defaults to `None` (locked by `test_imagefile_boxes_slot_defaults_none`) and is only populated when the page was visited (on_page_selected Step 1b). With a multi-page folder where the user only visited page 1, targeting page 2 (or later) in the dialog passes `None` into `apply_translations`, whose `for b in boxes:` raises `TypeError: 'NoneType' object is not iterable` — caught by the broad `except Exception` and surfaced as "Couldn't apply translations — see the log." instead of the clean no-match report.

**Fix:**
```python
applied, unmatched = apply_translations(
    matches,
    self.image_files[page_index].boxes or [],
    page_no=page_index,
)
```

### WR-05: Inspector fields go stale after an inline-editor commit

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\inline_editor.py:192-225`; `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:1287-1313`

**Issue:** `InlineEditor.commit()` refreshes the BoxItem overlay + badge and emits `boxes_modified`, but nothing reloads the Inspector. The Inspector is the D-08 "always-present view of both fields" and shows the same box (the box stays selected while editing, UI-SPEC §15), so after a double-click → inline edit → click-away, the Inspector still displays the pre-edit recognized/translation text until the selection changes. The display object and the property panel disagree about the same pagebox.

**Fix:** After an inline-edit commit (or generally in `_on_boxes_modified`), re-populate the Inspector from the still-selected box: `self.inspector_panel.load_box(item.pagebox)` when `self.canvas._selected_box()` is not None. `load_box` blocks signals during population, so no commit loop is possible.

## Info

### IN-01: Vertical commit silently drops the write and pushes a no-op entry when `payload is None`

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:1398-1410`

**Issue:** For a never-OCR'd user box (`payload is None`), `_on_inspector_vertical_committed` skips the write but still calls `_inspector_commit_post`, which pushes a BOXES snapshot the user can undo (restoring an identical state). Either route the vertical flag through a payload-ensuring setter or skip the push when nothing was written.

### IN-02: OCR crop is not bounds-clamped against the image

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:2469-2472` and `2568-2569`

**Issue:** `region = image[y1:y2, x1:x2].copy()` relies on numpy's silent slice clamping. A user box drawn partially outside the page is silently truncated (wrong OCR context); a box fully outside the image yields an empty region that manga-ocr may reject, surfacing as a model error dialog. Clamp `x1/y1/x2/y2` to `[0, w]`/`[0, h]` and skip boxes with an empty clamped region (mirrors the detection path's V5 clamp at `_build_detected_boxes`).

### IN-03: `_current_focus_text` is duplicated between BoxItem and InlineEditor

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\box_item.py:569-595` and `C:\Src\Manga AI Studio\manga_ai_studio\gui\inline_editor.py:245-263`

**Issue:** The D-10 focus-text read (translation-wins, str/list-aware, payload-None safe) is implemented twice with slightly different strip behavior (BoxItem strips the joined list, InlineEditor does not). A drift risk for the single most load-bearing display rule; consider one shared helper on `PageBox` (e.g. `current_focus_text()`).

### IN-04: `_run_ocr_all_task` lacks the image-read guard `_run_ocr_task` has

**File:** `C:\Src\Manga AI Studio\manga_ai_studio\gui\main_window.py:2555-2559`

**Issue:** The single-box task wraps `cv2.imdecode(np.fromfile(...))` in `try/except (OSError, ValueError)`; the batch task does not. Both paths surface as WorkerError anyway, but the asymmetry is gratuitous — mirror the guard.

---

_Reviewed: 2026-08-06T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

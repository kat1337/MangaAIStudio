---
phase: "01"
plan: "02"
subsystem: image-viewer
tags: [gui, canvas, pan-zoom, file-table, navigation, drag-drop, security]
requires:
  - "manga_ai_studio.gui.canvas.EditorCanvas (plan 01 skeleton)"
  - "manga_ai_studio.gui.main_window.MainWindow (plan 01 skeleton)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\gui\\image_viewer.py (pan/zoom mechanics, GPL vendored)"
  - "C:\\Src\\PanelCleaner\\pcleaner\\gui\\file_table.py (natsort + icon-size reference, GPL vendored)"
  - "C:\\Users\\Stella\\Downloads\\MangaCleaner_GPU\\_internal\\src\\frontend\\widgets.py (QListView shape, reference-only D-12)"
provides:
  - "manga_ai_studio.gui.canvas.EditorCanvas (extended): wheelEvent, zoom(factor), zoom_in(wheel), zoom_out(wheel), zoom_reset/actual_size, zoom_fit/fit_to_window, update_smoothing, pan (middle-mouse + Space+drag), zoom_changed Signal(float), ZOOM_TICK_FACTOR=1.25, validate_image_size, validate_image_path (module fn), set_image_from_path, empty-state overlay"
  - "manga_ai_studio.core.image_file.ImageFile dataclass (path/thumbnail/mask/dirty) + load_thumbnail (64px letterboxed) + clear_mask"
  - "manga_ai_studio.core package (created in this plan; plan 01 only shipped manga_ai_studio/{config,adapters,gui})"
  - "manga_ai_studio.gui.file_table.FileTable(QListView): set_pages, current_path, select_path, signals file_clicked/files_dropped/folder_dropped, empty-state placeholder, accent QSS"
  - "manga_ai_studio.gui.main_window.MainWindow (extended): full menu bar (File/Edit/View/Tools/Help), toolbar, dock_pages/dock_tools, 3-field status bar, open_folder (Ctrl+Shift+O), on_page_selected, recent files (QSettings), About dialog"
affects:
  - "plan 03 (detection) wires action_detect_text + the worker dispatch onto this MainWindow shell"
  - "plan 04 (mask editing) wires the Tools dock (currently a placeholder QLabel) and the mask painting onto EditorCanvas; consumes ImageFile.mask"
  - "plan 05 (inpaint) wires action_inpaint + Show Original (P) + preview-toggle"
  - "plan 06 (undo/redo) wires the Edit menu undo/redo actions (currently disabled) and consumes ImageFile.dirty"
  - "core.image_file.ImageFile.thumbnail path proves out the 64px letterbox the sidebar depends on"
tech-stack:
  added:
    - "natsort 8.4.0 (runtime dep declared in plan 01 pyproject.toml; first use in this plan: gui/file_table.py natural-sort)"
  patterns:
    - "Pan/zoom mechanics adapted near-verbatim from PanelCleaner image_viewer.py (GPL, D-12 vendored): ZOOM_TICK_FACTOR half-step wheel, 100x max / half-viewport min clamp, AnchorUnderMouse, update_smoothing pixel-accurate toggle at 1x"
    - "FileTable is our own reimplementation patterned after MangaCleaner_GPU widgets.py:FileListWidget (D-12 reference-only — no LICENSE in the binary distribution, all-rights-reserved; never vendored)"
    - "QImage.copy() buffer-detach on every QImage(path) load (RESEARCH Pitfall 2) — applied in both set_image_from_path and ImageFile.load_thumbnail"
    - "Centralized path validation: validate_image_path (resolve + suffix allowlist) gates every file-open surface (open_image, open_folder scan, drag-drop, recent files) — single chokepoint for T-01-02"
    - "QStandardItemModel-backed QListView with UserRole carrying the Path — keeps the sidebar's source-of-truth separate from display text"
key-files:
  created:
    - manga_ai_studio/core/__init__.py
    - manga_ai_studio/core/image_file.py
    - manga_ai_studio/gui/file_table.py
    - tests/test_gui_file_table.py
  modified:
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_canvas.py
key-decisions:
  - "EditorCanvas stores scene as self._scene (kept from plan 01 deviation #3); new empty-state overlay items also live in the same scene at z=2000"
  - "image_files is natural-sorted in MainWindow._set_pages to match the sidebar's display order — index lookups in _current_page_index depend on this consistency"
  - "FileTable uses QStandardItemModel + QListView (not QListWidget); the plan explicitly contracts QListView with QListView.ListMode, setViewMode, setMovement, setResizeMode"
  - "Drag-drop is handled by the FileTable sidebar only (surface 3/4); no MainWindow-level drop handlers to avoid double-handling"
  - "MAX_ZOOM_FACTOR = 100.0 and MAX_IMAGE_DIMENSION = 10000 named as module constants (single source of truth) rather than inlined magic numbers"
requirements-completed:
  - CLEAN-01
  - FLOW-01
coverage:
  - deliverable: "Ctrl+wheel half-step zoom (sqrt(1.25)) with 100x max / half-viewport min clamp"
    verification:
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_zoom_wheel_half_step"
        status: pass
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_zoom_clamp_100x"
        status: pass
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_zoom_clamp_min"
        status: pass
    human_judgment: false
  - deliverable: "update_smoothing pixel-accurate toggle (SmoothPixmapTransform off >1x, on <=1x)"
    verification:
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_update_smoothing_pixel_accurate"
        status: pass
    human_judgment: false
  - deliverable: "Image size limit (10000x10000 cap) and path validation (resolve + suffix allowlist)"
    verification:
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_image_size_limit_rejects_huge"
        status: pass
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_path_validation_rejects_bad_suffix"
        status: pass
    human_judgment: false
  - deliverable: "Empty-state overlay ('No page open' heading + body + accent hint)"
    verification:
      - kind: tests
        ref: "tests/test_gui_canvas.py#test_empty_state_heading"
        status: pass
    human_judgment: false
  - deliverable: "Pan via middle-mouse or Space+left-drag (UI-SPEC surface 2)"
    verification: []
    human_judgment: true
    rationale: "Pan mechanics (mousePressEvent/mouseMoveEvent/mouseReleaseEvent + Space tracking) are implemented per spec but not unit-tested — continuous-input feel is a manual verification per VALIDATION.md Manual-Only."
  - deliverable: "FileTable natural-sort populate (page1, page2, page10) with 64x64 thumbnails and accent QSS"
    verification:
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_load_folder_populates"
        status: pass
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_thumbnail_64"
        status: pass
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_current_row_highlight"
        status: pass
    human_judgment: false
  - deliverable: "Sidebar click navigation emits file_clicked(Path)"
    verification:
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_navigation_click_emits_signal"
        status: pass
    human_judgment: false
  - deliverable: "Open Folder action (Ctrl+Shift+O) + drag-drop signals (T-01-05)"
    verification:
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_open_folder_action"
        status: pass
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_drop_images_signal"
        status: pass
    human_judgment: false
  - deliverable: "Status bar page progress 'Page {i+1} / {N}'"
    verification:
      - kind: tests
        ref: "tests/test_gui_file_table.py#test_status_bar_page_progress"
        status: pass
    human_judgment: false
  - deliverable: "Full MainWindow shell (menus/toolbar/docks/status bar) per UI-SPEC surface 1"
    verification: []
    human_judgment: true
    rationale: "Menu/toolbar/dock presence is asserted via source grep acceptance criteria; visual layout adequacy is a manual verification deferred to /gsd-verify-work."
metrics:
  duration: "12 min"
  completed: "2026-07-12"
  tasks: 2
  files: 7
  tests: 14
status: complete
---

# Phase 01 Plan 02: Image Viewer Slice Summary

Delivered the full image-viewer vertical slice: a Ctrl+wheel half-step zoomable / pannable canvas (mechanics adapted near-verbatim from PanelCleaner `image_viewer.py` under GPL D-12), a FileTable `QListView` sidebar (our own reimplementation patterned after MangaCleaner_GPU's `widgets.py` — reference-only per D-12) with natural-sorted 64px-thumbnail rows and accent-highlighted selection, an Open Folder (Ctrl+Shift+O) + drag-drop workflow, and the complete MainWindow shell (File/Edit/View/Tools/Help menus, toolbar, Pages+Tools docks, 3-field status bar). Path validation (`resolve` + suffix allowlist, T-01-02) and a 10000x10000 image-size cap (T-01-03) gate every open path.

## What Was Built

**Canvas (Task 1 — `gui/canvas.py` extended):**
- `ZOOM_TICK_FACTOR = 1.25` constant; `wheelEvent` routes Ctrl+wheel to half-step zoom (`sqrt(1.25)`), Shift+wheel to horizontal scroll, else default vertical pan — all adapted from `image_viewer.py:125-142`.
- `zoom(factor)`, `zoom_in(wheel=False)`, `zoom_out(wheel=False)` with the 100x max clamp (`min(zoom_factor * factor, MAX_ZOOM_FACTOR)`) and half-viewport min clamp (no-op when `proposed_width < view_width/2 and proposed_height < view_height/2 and factor < 1`).
- `update_smoothing()` toggles `SmoothPixmapTransform` off above 1x (pixel-accurate) and on at/under 1x — `image_viewer.py:116`.
- `zoom_reset()` / `actual_size()` (Ctrl+1), `zoom_fit()` alias for the existing `fit_to_window()` (now also syncs `zoom_factor` from the resulting transform).
- Pan: `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` for middle-mouse OR Space+left-drag (UI-SPEC surface 2); `keyPressEvent`/`keyReleaseEvent` track Space with OpenHandCursor/ClosedHandCursor.
- `zoom_changed = Signal(float)` emitted on every zoom change; MainWindow wires it to the status bar center field.
- Empty-state overlay: three `QGraphicsTextItem`s (heading "No page open" 16px semibold muted, body 14px muted, hint 12px accent `#00d4ff`), z=2000, toggled by `_update_empty_state()` on `set_image`/`clear`.
- Security: module-level `validate_image_path(path)` (`Path.resolve()` + suffix allowlist `{png,jpg,jpeg,webp,bmp}`) and `validate_image_size(w, h)` (10000 cap); `set_image_from_path(path)` validates both, `.copy()`-detaches the `QImage(path)` buffer (RESEARCH Pitfall 2), returns False on any failure so MainWindow shows the UI-SPEC "file unreadable" dialog.

**ImageFile data model (Task 1 — `core/image_file.py`, `core/` package created):**
- `@dataclass ImageFile(path: Path, thumbnail: QPixmap | None = None, mask: QImage | None = None, dirty: bool = False)` — role-match of PanelCleaner `gui/image_file.py:ImageFile` per PATTERNS.md, minimal triad.
- `load_thumbnail(size=64)` loads via `QImage`, `.copy()`-detaches, scales aspect-preserved into a 64x64 `QPixmap` letterboxed on `#2d2d33` (UI-SPEC surface 3). `clear_mask()` drops the mask slot.
- `core/` package did not exist after plan 01; created `core/__init__.py` here.

**FileTable sidebar (Task 2 — `gui/file_table.py`):**
- `class FileTable(QListView)` — our own reimplementation patterned after MangaCleaner_GPU `widgets.py:FileListWidget` (D-12 reference-only; docstring says exactly that, no "copied/vendored from MangaCleaner" wording). `ListMode`, `Static` movement, `Adjust` resize, `setIconSize(QSize(64, 64))`, uniform item sizes.
- QSS carries the accent selected-row style: `rgba(0, 212, 255, 0.18)` background + `2px solid #00d4ff` left border on `::item:selected` (UI-SPEC surface 3 + §Color).
- `QStandardItemModel`-backed; each row carries decoration (64x64 letterboxed thumbnail via `ImageFile.load_thumbnail`), display (filename + 1-indexed page number), and UserRole (the resolved Path).
- Natural-sort via `from natsort import natsorted` (natsort is a runtime dep declared in plan 01's pyproject.toml — not re-declared, pyproject untouched).
- Signals `file_clicked = Signal(Path)`, `files_dropped = Signal(list)`, `folder_dropped = Signal(Path)`. `dragEnterEvent`/`dragMoveEvent`/`dropEvent` accept URL-carrying drops; `dropEvent` takes only `url.toLocalFile()`, re-validates each via `validate_image_path` (T-01-05 path-injection mitigation), emits `folder_dropped` for a single directory drop or `files_dropped` for image files. No remote URL fetching.
- Empty-state placeholder QLabel "No pages loaded — open a folder (Ctrl+Shift+O)." shown when the model is empty (UI-SPEC surface 3 empty).

**MainWindow shell (Task 2 — `gui/main_window.py` extended):**
- Full menu bar (UI-SPEC surface 1): File (Open Image Ctrl+O, Open Folder Ctrl+Shift+O, Recent Files submenu max 8 via QSettings, Quit Ctrl+Q), Edit (Undo/Redo Image/Mask + Clear Mask — all disabled, plan 06), View (Fit Ctrl+0, Actual Size Ctrl+1, Zoom In Ctrl++, Zoom Out Ctrl+-, Toggle Mask Overlay M [disabled plan 03/04], Show Original P [disabled plan 05], Toggle Sidebar/Tools), Tools (Detect Text D, Inpaint C, Move V, Brush B, Rectangle R, Lasso L, Eraser E — disabled until plans 03/04/05), Help (About with version + GPL v3 notice).
- Single top toolbar: Open | (sep) | Fit / 100% / Zoom Out / Zoom In | (sep) | Toggle Mask Overlay. Other sections added by their plans.
- Docks: `dock_pages` (Pages, LeftDockWidgetArea, holds the FileTable) and `dock_tools` (Tools, RightDockWidgetArea, placeholder QLabel until plan 04). Both user-movable/closable.
- 3-field status bar: left (operation/status), center (zoom %, Consolas mono, wired to `canvas.zoom_changed`), right (page progress "Page {n} / {total}").
- `open_folder()` (Ctrl+Shift+O): `QFileDialog.getExistingDirectory` → flat non-recursive scan via `Path.iterdir` + `is_file` + `validate_image_path` → `_set_pages` → auto-select + load page 1.
- `on_page_selected(path)`: routes through `canvas.set_image_from_path` (with size+path validation and `.copy()` discipline), updates window title, status bar, recent files.
- Recent Files via `QSettings("MangaAIStudio")` key `recentFiles`, max 8, re-validated on open; Clear Menu action.
- `_set_pages` natural-sorts paths before building `ImageFile`s so the window's ordering matches the sidebar's (see deviation #1).

## Verification Results

- `pytest tests/test_gui_canvas.py -x` → **11 passed** (4 plan-01 + 7 plan-02 Task 1)
- `pytest tests/test_gui_file_table.py tests/test_gui_canvas.py -x` (plan `<verification>`) → **18 passed**
- Full suite `pytest -q` → **22 passed** (8 plan-01 + 14 plan-02); no regressions
- Acceptance criteria: all source-grep criteria pass (ZOOM_TICK_FACTOR, wheelEvent, zoom clamp, update_smoothing, validate_image_size/path, zoom_changed Signal, empty-state text, ImageFile fields, FileTable QListView + QSS + signals, MainWindow menus/docks/status bar, D-12 docstring wording)
- Manual-only (per VALIDATION.md): pan/zoom responsiveness at 100%–800% on a 2000x3000 page — deferred to `/gsd-verify-work`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MainWindow image_files order did not match sidebar's natural-sorted order**
- **Found during:** Task 2 (`test_status_bar_page_progress` failed on first run: selected page2.png reported "Page 3 / 3" instead of "Page 2 / 3")
- **Issue:** `_set_pages` built `self.image_files` from the candidate list in `Path.iterdir` (filesystem) order, while `FileTable.set_pages` natural-sorts for display. `_current_page_index` searched `image_files` by path, so when the user selected `page2.png` (displayed at row 1), the index lookup found it at filesystem-order position 2 — desyncing the status bar page number from the sidebar row.
- **Fix:** `_set_pages` now natural-sorts the paths (`natsorted(paths, key=lambda p: str(p))`) before building `ImageFile`s, so the window's internal ordering matches the sidebar's displayed order. Index lookups are now consistent.
- **Files modified:** `manga_ai_studio/gui/main_window.py`
- **Verification:** `test_status_bar_page_progress` now passes ("Page 1 / 3" → select page2 → "Page 2 / 3")
- **Commit:** 6176465

**2. [Rule 2 - Missing critical functionality] FileTable empty-state placeholder missing**
- **Found during:** Task 2 acceptance-criteria grep (criterion: "No pages loaded" appears in the file_table placeholder or main window empty state)
- **Issue:** UI-SPEC surface 3 contracts an empty state "No pages loaded — open a folder (Ctrl+Shift+O)." but the initial FileTable implementation rendered nothing when the model was empty. QListView has no built-in placeholder text in Qt6.
- **Fix:** Added a child `QLabel` overlay (`self._placeholder`) with the UI-SPEC copy, shown when `model.rowCount() == 0`, kept centered over the viewport via `resizeEvent`. `WA_TransparentForMouseEvents` so it never blocks drag-drop.
- **Files modified:** `manga_ai_studio/gui/file_table.py`
- **Verification:** acceptance criterion grep now finds "No pages loaded"; full suite still 22/22 green
- **Commit:** 6176465

**3. [Rule 1 - Bug] test_update_smoothing used non-existent testRenderHint API**
- **Found during:** Task 1 test run (`AttributeError: 'EditorCanvas' object has no attribute 'testRenderHint'`)
- **Issue:** The first test draft called `canvas.testRenderHint(QPainter.RenderHint.SmoothPixmapTransform)` — that method does not exist on `QGraphicsView` in PySide6. The correct API is to read `canvas.renderHints()` and AND it with the flag.
- **Fix:** Test now asserts `canvas.renderHints() & QPainter.RenderHint.SmoothPixmapTransform` (truthy when set, falsy when cleared).
- **Files modified:** `tests/test_gui_canvas.py`
- **Verification:** `test_update_smoothing_pixel_accurate` passes
- **Commit:** c016922

### Architectural Changes
None — all deviations were Rule 1 bug fixes and one Rule 2 missing-critical (the contracted empty state) within the planned files.

## Authentication Gates
None — no auth-required operations in this plan.

## Known Stubs

This plan intentionally ships disabled actions whose backing logic lands in later plans (contracted placeholders, not gaps):

| Stub | File | Line | Reason | Resolved By |
|------|------|------|--------|-------------|
| Edit menu Undo/Redo Image/Mask + Clear Mask actions all `setEnabled(False)` | `gui/main_window.py` | `_build_edit_menu` | FLOW-02 undo/redo history manager is plan 06; mask clearing is plan 04. Actions exist with correct shortcuts (Ctrl+Z/Ctrl+Shift+Z/Alt+Z/Alt+Shift+Z) so the menu structure is in place. | Plan 01-04 (Clear Mask), Plan 01-06 (undo/redo) |
| Tools menu Detect Text (D) `setEnabled(False)` | `gui/main_window.py` | `_build_tools_menu` | CLEAN-02 text detection + the worker dispatch are plan 03. | Plan 01-03 |
| Tools menu Inpaint (C) `setEnabled(False)` | `gui/main_window.py` | `_build_tools_menu` | CLEAN-06 LaMa inpainting is plan 05. | Plan 01-05 |
| Tools menu mask tools (Move V, Brush B, Rectangle R, Lasso L, Eraser E) all `setEnabled(False)` | `gui/main_window.py` | `_build_tools_menu` | CLEAN-03/04/05 mask editing is plan 04. | Plan 01-04 |
| View menu Toggle Mask Overlay (M) `setEnabled(False)` | `gui/main_window.py` | `_build_view_menu` | Depends on a mask layer existing (plan 04). | Plan 01-04 |
| View menu Show Original (P) `setEnabled(False)` | `gui/main_window.py` | `_build_view_menu` | Inpaint preview-toggle is plan 05. | Plan 01-05 |
| `dock_tools` holds a placeholder QLabel | `gui/main_window.py` | `_build_docks` | The real Tools panel (brush size slider, tool buttons) is plan 04. | Plan 01-04 |
| `EditorCanvas.mask_item` initialized transparent, no painting | `gui/canvas.py` | `set_image` | Mask painting (brush/rect/lasso/eraser) is plan 04 (carried from plan 01-01 SUMMARY). | Plan 01-04 |

No stubs that block this plan's goal (open/navigate/pan/zoom a folder of images end-to-end).

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. All four registered threats mitigated as specified:
- T-01-02 (path traversal): `validate_image_path` (resolve + suffix allowlist) gates `open_folder` scan, drag-drop `dropEvent`, and recent-files open — single chokepoint in `gui/canvas.py`.
- T-01-03 (large image DoS): `validate_image_size` (10000x10000 cap) in `set_image_from_path`; `QImageReader.setAllocationLimit(0)` from plan 01 still applies for Qt's internal cap.
- T-01-05 (drag-drop path injection): `FileTable.dropEvent` takes only `url.toLocalFile()`, filters via `validate_image_path`, ignores non-local/non-file URLs; no remote fetching.
- T-01-06 (filename display injection): filenames displayed via `QStandardItem.setText` (Qt does not interpret HTML in item text by default) and `QLabel.setText`; no `setHtml`/`setRichText` on user-controlled strings.

## Commits

- `c016922` — feat(01-02): canvas pan/zoom + validation + empty state + ImageFile (Task 1)
- `6176465` — feat(01-02): FileTable sidebar + folder open workflow + drag-drop + MainWindow shell (Task 2)

## Self-Check: PASSED

- All 7 key files FOUND on disk: `core/__init__.py`, `core/image_file.py`, `gui/file_table.py`, `tests/test_gui_file_table.py` (created); `gui/canvas.py`, `gui/main_window.py`, `tests/test_gui_canvas.py` (modified).
- Both task commits FOUND in git log: `c016922` (Task 1), `6176465` (Task 2).
- Plan `<verification>` command `pytest tests/test_gui_canvas.py tests/test_gui_file_table.py -x` exits 0 (18 passed).
- Full suite green (22/22). No regressions vs plan 01's 8 tests.

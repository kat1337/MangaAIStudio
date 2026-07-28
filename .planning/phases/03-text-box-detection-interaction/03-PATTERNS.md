# Phase 3: Text Box Detection & Interaction - Pattern Map

**Mapped:** 2026-07-27
**Files analyzed:** 10 (4 new source, 5 modified source, 1 confirmed-unchanged, 6 new tests)
**Analogs found:** 10 / 10 (every file has a concrete in-repo analog)

> All line numbers verified against the working tree on 2026-07-27. "Analog"
> for a self-extended file means "the existing region of that same file the new
> code slots into / mirrors" — the planner copies the excerpt's shape, not the
> bytes verbatim.

---

## File Classification

Grouped by role (the planner requested grouping). Match quality: **exact** =
same role + same data flow in the same stack; **role-match** = same role,
different specific shape; **self-extend** = the new code is an additive change
to the listed file itself.

### Vendored (D-14 — near-verbatim GPL v3 → GPL v3)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `panelcleaner/structures.py` (replace 18-line stub) | model (vendored dataclass + enum) | transform | `panelcleaner/image_ops.py:1-13` (the D-12 vendoring header) + `C:\Src\PanelCleaner\pcleaner\structures.py` (source) | exact |
| `panelcleaner/masker.py` (new vendored) | service (vendored driver) | batch / file-I/O | `panelcleaner/image_ops.py:1-13` header + `panelcleaner/comic_text_detector/inference.py:1-16` (vendored driver w/ rewritten imports) | exact |

### Model (core/ — pure Python, headless-testable)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `manga_ai_studio/core/box_model.py` (NEW) | model (origin-tagged wrapper + D-15 seam) | transform | `manga_ai_studio/core/image_file.py:54-110` (`ImageFile` dataclass + `has_mask_content`) + `manga_ai_studio/core/mask_editor.py:56-69` (`ToolMode` enum) | role-match |
| `manga_ai_studio/core/image_file.py` (MODIFY — add `boxes` slot) | model (per-page page state) | state | itself (`mask` slot at `image_file.py:69`) | self-extend |

### GUI (Qt Graphics View — component / event-driven)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `manga_ai_studio/gui/box_item.py` (NEW) | component (`QGraphicsRectItem` subclass) | event-driven | `manga_ai_studio/gui/canvas.py:129-149, 758-895` (layered QGraphicsItems + mouse dispatch + preview_item) | exact |
| `manga_ai_studio/gui/canvas.py` (MODIFY — box layer + hit-test dispatch) | component (`QGraphicsView`) | event-driven | itself (`canvas.py:120-225` scene setup, `758-895` dispatch) | self-extend |
| `manga_ai_studio/gui/main_window.py` (MODIFY — detection seam + View menu + confirm gate + undo collapse) | controller (signal/worker wiring) | request-response | itself (`main_window.py:1122-1303` detect, `653-747` page seam, `1328-1348` confirm gate, `920-1043` undo wiring) | self-extend |
| `manga_ai_studio/gui/tools_panel.py` (CONFIRM no change per D-07) | component | event-driven | itself | self (no-op) |

### Persistence + Undo (core/ — per-page state + 3rd stack)

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `manga_ai_studio/core/history_manager.py` (MODIFY — BOXES stack + unified timeline) | service (undo engine) | state / stack | itself (`history_manager.py:49-192` 2-stack push/pop/reset) | self-extend |

### Tests (Wave 0 stubs per VALIDATION.md)

| New Test File | Role | Data Flow | Closest Analog | Match |
|---------------|------|-----------|----------------|-------|
| `tests/test_core/test_structures.py` | test (unit, headless) | transform | `tests/test_core/test_image_io.py:1-45` (pure-numpy unit test header) + `tests/test_core/conftest.py` (fixture shape) | exact |
| `tests/test_core/test_masker_vendor.py` | test (unit, headless) | import-smoke | `tests/test_core/test_image_io.py:1-45` | role-match |
| `tests/test_core/test_box_model.py` | test (unit, headless) | state | `tests/test_core/test_image_io.py:1-45` | role-match |
| `tests/test_core/test_history_boxes.py` | test (unit, headless) | state / stack | `tests/test_history.py:1-90` (HistoryManager tests + `_transparent_mask`/`_painted_mask` helpers) | exact |
| `tests/test_gui_boxes.py` | test (GUI, pytest-qt) | event-driven | `tests/test_gui_canvas.py:1-58` (qtbot fixture + `_solid_pixmap` helper + `pytest.importorskip`) | exact |
| `tests/test_box_persistence.py` | test (GUI, pytest-qt) | state / file-I/O seam | `tests/test_history.py` + Phase 2 `test_mask_persistence_uses_copy` (the `.copy()`-at-both-boundaries regression guard) | exact |

---

## Pattern Assignments

### Group A — Vendored (D-14)

---

### `panelcleaner/structures.py` (model, vendored dataclass + enum)

**Analog:** the D-12 vendoring header already shipped in `panelcleaner/image_ops.py` lines 1-13; the SOURCE is `C:\Src\PanelCleaner\pcleaner\structures.py` (750 lines).

**Vendoring header to copy** (`panelcleaner/image_ops.py:1-7`):
```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored near-verbatim from PanelCleaner pcleaner/structures.py (GPL v3) per
# CONTEXT.md D-12. Imports rewritten pcleaner. -> panelcleaner.
```

**Source imports to rewrite** (`C:\Src\PanelCleaner\pcleaner\structures.py:1-15`):
```python
import json
from enum import Enum, auto
from importlib import resources
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from attrs import frozen, define
from loguru import logger

import pcleaner.config as cfg       # rewrite -> panelcleaner.config
import pcleaner.data                # rewrite -> panelcleaner.data   (already vendored)
import pcleaner.ocr.supported_languages as osl   # -> panelcleaner.ocr.supported_languages (vendored)
import pcleaner.helpers as hp       # -> panelcleaner.helpers (vendored, 335 lines)
```
All four `panelcleaner.*` targets resolve in the vendored tree (verified in RESEARCH §Standard Stack + Runtime State Inventory). `attrs`/`PIL`/`loguru` are env-present.

**`Box` class to consume verbatim** (`C:\Src\PanelCleaner\pcleaner\structures.py:24-145`):
```python
@frozen
class Box:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2

    @property
    def as_tuple_xywh(self) -> tuple[int, int, int, int]:
        # QRect expects (x1, y1, width, height)   <-- maps directly to QRectF(x, y, w, h)
        return self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1

    def __contains__(self, point: tuple[int, int]) -> bool:
        x, y = point
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
```
Plus `BoxType` enum (lines 17-22: `BOX=0`/`EXTENDED_BOX=1`/`MERGED_EXT_BOX=2`/`REFERENCE_BOX=3`) and the batch structs `PageData` (148), `MaskData`, `MaskFittingResults` (564-600, carries `analytics_std_deviation` + `mask_box` — the D-15 seam types). **Do NOT mutate `Box`** — origin/identity layer on top per D-14 Claude's Discretion (see `core/box_model.py` below).

**Verification command** (RESEARCH §Vendoring verification):
```bash
python -c "from panelcleaner.structures import Box, BoxType, MaskFittingResults, MaskData, PageData; print('ok')"
```

---

### `panelcleaner/masker.py` (service, vendored driver)

**Analog:** the vendored-driver shape of `panelcleaner/comic_text_detector/inference.py:1-16` (imports rewritten, GPL v3 header implied) + the D-12 header from `image_ops.py:1-7`. SOURCE: `C:\Src\PanelCleaner\pcleaner\masker.py` (151 lines).

**Source imports to rewrite + the ONE stub site (RESEARCH Pitfall 1)** (`C:\Src\PanelCleaner\pcleaner\masker.py:1-10, 28`):
```python
from pathlib import Path
from typing import Sequence
from PIL import Image
from loguru import logger

import pcleaner.image_ops as ops          # -> panelcleaner.image_ops   (vendored, 1158 lines)
import pcleaner.structures as st          # -> panelcleaner.structures  (full version per file above)
import pcleaner.output_structures as ost  # NOT vendored — STUB THIS (Pitfall 1)

# ... inside mask_page (line 28):
path_gen = ost.OutputPathGenerator(original_path, m_data.cache_dir, m_data.json_path)
```

**The ost-stub pattern** (Pitfall 1 — guard the import; Phase 3 does not call `mask_page`):
```python
try:
    import panelcleaner.output_structures as ost
except ImportError:  # output_structures.py is the batch GUI analytics pipeline — NOT vendored
    ost = None  # mask_page() is dead code in our context; the std-dev seam uses image_ops directly
```
RESEARCH Open Question 3 recommends keeping `mask_page` verbatim with this guard (near-verbatim is easier to diff upstream than a carved file; `ost = None` is harmless). The std-dev machinery the D-15 seam needs lives in `image_ops.py` (`border_std_deviation` line 483, `color_std` 464, `pick_best_mask` 568) — already vendored Phase 1 — NOT in `masker.py`.

**Verification command** (Pitfall 1 guard works):
```bash
python -c "import panelcleaner.masker; print('masker ok')"
python -c "from panelcleaner.image_ops import border_std_deviation, color_std, pick_best_mask; print('std-dev ok')"
```

---

### Group B — Model (core/)

---

### `manga_ai_studio/core/box_model.py` (model, NEW — origin-tagging wrapper + D-15 seam)

**Analogs:** `core/image_file.py:54-110` (the `@dataclass` page-state shape) + `core/mask_editor.py:56-69` (an enum + module-level constants pattern).

**Dataclass shape to mirror** (`core/image_file.py:54-70`):
```python
@dataclass
class ImageFile:
    """A single page loaded into the workspace."""
    path: Path
    thumbnail: QPixmap | None = None
    mask: QImage | None = None          # <-- the slot `boxes` mirrors
    dirty: bool = False
```

**The target shape** (RESEARCH §Code Examples — the D-15 `(Box, mask, std_dev)` seam):
```python
from dataclasses import dataclass
from typing import Optional
from panelcleaner.structures import Box  # vendored, immutable — do NOT subclass+mutate

@dataclass
class PageBox:
    """Phase 3 box data model. The D-15 seam: mask + std_dev are None in
    Phase 3 (populated by a LATER inpaint phase via image_ops.pick_best_mask)."""
    box: Box                                  # vendored, frozen
    origin: str                               # "detected" | "user"  (D-03)
    payload: Optional[object] = None          # TextBlock for Phase 4/5; None for user boxes
    mask: Optional[object] = None             # D-15 seam (DEFERRED)
    std_dev: Optional[float] = None           # D-15 seam (DEFERRED)
```
**Anti-pattern (CONTEXT D-14 / Claude's Discretion):** do NOT subclass `Box` and add `origin`; the vendored `Box` must stay near-verbatim. `PageBox` *composes* a `Box`, doesn't inherit it. Stable identity for undo (D-10) comes from Python object identity of the `PageBox` instance OR an explicit `box_id` field the planner adds — NOT by mutating `Box`.

**Validation pattern** (V5 input validation — coerce `TextBlock.xyxy` ints at the boundary):
```python
def textblock_to_box(blk) -> Box:
    x1, y1, x2, y2 = blk.xyxy          # ints per textblock.py:50
    return Box(int(x1), int(y1), int(x2), int(y2))   # coerce; clamp to image bounds in caller
```

---

### `manga_ai_studio/core/image_file.py` (model, MODIFY — add `boxes` slot)

**Analog:** itself — the existing `mask` slot + `has_mask_content` at `image_file.py:69, 93-110`.

**The slot to mirror** (`image_file.py:67-70`):
```python
    path: Path
    thumbnail: QPixmap | None = None
    mask: QImage | None = None
    dirty: bool = False
```

**The new slot** (CONTEXT Claude's Discretion — RESEARCH Open Q 4 recommends `list[PageBox]`):
```python
    boxes: list["PageBox"] | None = None   # mirrors mask slot; per-page, in-memory only (no disk serialization in Phase 3)
```

**The content-check pattern to mirror** (`image_file.py:93-110` — `has_mask_content`):
```python
    def has_mask_content(self) -> bool:
        if self.mask is None or self.mask.isNull():
            return False
        from manga_ai_studio.core.mask_editor import mask_to_numpy_binary
        return bool(mask_to_numpy_binary(self.mask).any())
```
The boxes analog is trivial: `def has_boxes(self) -> bool: return bool(self.boxes)`. The D-03 origin split needs: keep `user` boxes on re-detect, replace `detected` — the `origin` field on each `PageBox` is the discriminator (no separate lists).

---

### Group C — GUI (Qt Graphics View)

---

### `manga_ai_studio/gui/box_item.py` (component, NEW — `QGraphicsRectItem` subclass + 4 corner handles)

**PRIMARY analog:** `gui/canvas.py` — the existing layered `QGraphicsItem` setup, the `_scene_pos` sub-pixel mapping, and the mouse-event dispatch. The `BoxItem` class slots directly into this scene as another layered item.

**Layered-item setup to mirror** (`canvas.py:129-149`):
```python
self.image_item = QGraphicsPixmapItem()
self.mask_item = QGraphicsPixmapItem()
self._scene.addItem(self.image_item)
self._scene.addItem(self.mask_item)

self.preview_item = QGraphicsPathItem()
self.preview_item.setPen(QPen(QColor(0, 212, 255, 200), 2, Qt.PenStyle.DashLine))  # cyan
self.preview_item.setZValue(900)
self._scene.addItem(self.preview_item)

self.cursor_item = QGraphicsEllipseItem()
self.cursor_item.setZValue(1000)
self._scene.addItem(self.cursor_item)
```
Phase 3 adds: box layer at z=100, corner handles at z=150, empty-box-hint `QGraphicsTextItem` at z=850 (UI-SPEC §Z-order). The box layer is a `QGraphicsItemGroup` (or parent-less item set) toggled via `setVisible(bool)` — mirror `mask_item.setVisible()` at `canvas.py:335-336`.

**Sub-pixel scene mapping to reuse** (`canvas.py:840-848` — `_scene_pos`):
```python
def _scene_pos(self, event) -> QPointF:
    return QPointF(self.mapToScene(event.position().toPoint()))
```
`BoxItem` resize/move math uses this same mapping for cursor→box-corner.

**Mouse-event dispatch to extend** (`canvas.py:758-785` — the branch to slot box hit-testing BEFORE):
```python
def mousePressEvent(self, event) -> None:
    middle = event.button() == Qt.MouseButton.MiddleButton
    space_left = self._space_held and event.button() == Qt.MouseButton.LeftButton
    if middle or space_left:                       # 1. Pan (highest priority — unchanged)
        self._panning = True
        ...
        return
    # 2. [NEW D-07] box layer visible? -> box hit-test FIRST (see Pattern 3 below)
    if (
        event.button() == Qt.MouseButton.LeftButton
        and self.current_tool != ToolMode.MOVE     # 3. existing mask-tool branch (UNCHANGED)
        and self._mask is not None
        and not self._mask.isNull()
    ):
        self._begin_paint(event); event.accept(); return
    super().mousePressEvent(event)
```

**Flags pattern** (UI-SPEC §12a — `canvas.py`'s items don't set these, but Qt's native selection/move is the analog):
```python
self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
              | QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
              | QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
```

**Pen/brush color pattern** — mirror `canvas.py:632-640` (`_update_cursor_visuals` switches color by mode):
```python
# canvas.py:632-640 (the hue-by-mode precedent)
if self._effective_eraser():
    pen = QPen(QColor(0, 212, 255, 200), 1)     # cyan
else:
    pen = QPen(QColor(255, 0, 0, 200), 1)       # red
```
`BoxItem._apply_origin_pen` mirrors this with `#5fd068` (detected) / `#f5a623` (user) and 2px/3px width by selection (UI-SPEC §Color + Spacing exceptions).

**BoxItem skeleton** (RESEARCH §Pattern 1 — copy verbatim, it is already concrete):
```python
class BoxItem(QGraphicsRectItem):
    def __init__(self, box: Box, origin: str, payload=None):
        x, y, w, h = box.as_tuple_xywh        # Box -> QRectF (structures.py:39)
        super().__init__(QRectF(x, y, w, h))
        self.box = box                        # vendored Box (immutable bbox)
        self.origin = origin                  # "detected" | "user" (D-03)
        self.payload = payload                # TextBlock for Phase 4/5; None for user boxes
        self.setZValue(100)                   # above mask_item, below preview_item
        self.setFlags(ItemIsSelectable | ItemIsMovable | ItemSendsGeometryChanges)
        self.handles = [CornerHandle(c, self) for c in ("TL","TR","BL","BR")]
        self._apply_origin_pen()
        self._sync_handles()
```

---

### `manga_ai_studio/gui/canvas.py` (component, MODIFY — box layer + hit-test dispatch + create/delete)

**Analog:** itself. Every Phase 3 change slots into an existing region documented above. Concretely:

1. **Constructor** (`canvas.py:120-225`): add `box_layer` (`QGraphicsItemGroup`, z=100), `empty_box_hint` (`QGraphicsTextItem`, z=850) after `preview_item`/`cursor_item` setup. Mirror the empty-state text pattern at `canvas.py:153-173`.
2. **`mousePressEvent`** (`canvas.py:758-785`): insert the box hit-test branch (UI-SPEC §12d) between the pan branch and the mask-tool branch.
3. **`mouseMoveEvent`** (`canvas.py:787-813`): add resize-drag + create-drag advance alongside `_advance_paint`.
4. **`mouseReleaseEvent`** (`canvas.py:815-837`): add resize/create commit alongside `_end_paint` — and emit a `boxes_modified` signal (mirror `mask_modified` at `canvas.py:118`).
5. **`keyPressEvent`** (`canvas.py:898-932`): add `Delete` (silent delete selected box, D-12) + `Esc` (deselect). Keep the `event.ignore()` fall-through (CR-09 — undo shortcuts must reach MainWindow).
6. **`zoom_changed` signal** (`canvas.py:114`): already emitted; `CornerHandle._sync_handles` subscribes so 8×8 viewport-px handles reposition on zoom.

**Pattern 3 — the box hit-test dispatch** (RESEARCH §Pattern 3, slotted into `canvas.py:758`):
```python
def mousePressEvent(self, event) -> None:
    # 1. Pan (unchanged)
    if middle or space_left: ...; return
    # 2. [NEW D-07] box layer visible -> box hit-test first
    if self.box_layer.isVisible() and event.button() == Qt.MouseButton.LeftButton:
        scene_pos = self._scene_pos(event)
        item = self._scene.itemAt(scene_pos, self.transform())
        if isinstance(item, CornerHandle):
            self._begin_resize(item, scene_pos); event.accept(); return
        if isinstance(item, BoxItem):
            self._select_and_begin_move(item, scene_pos); event.accept(); return
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:       # D-13 Alt+drag create
            self._begin_create_box(scene_pos); event.accept(); return
        self._deselect_box()   # fall through to mask tools
    # 3. (existing) mask-tool branch
    ...
```
**Pitfall 5 guard (UI-SPEC §11):** the `if self.box_layer.isVisible()` check is load-bearing — `setVisible(False)` does not always disable Qt hit-testing. As belt-and-suspenders also `box_item.setEnabled(False)` on hide.

**Create-drag preview pattern** — reuse `preview_item` (z=900) recolored amber (`canvas.py:140-145` is the cyan setup; recolor for box-create per UI-SPEC §12e):
```python
# During Alt+drag create, swap the preview pen to amber dashed:
QPen(QColor(245, 166, 35, 200), 2, Qt.PenStyle.DashLine)   # amber, not cyan
```
Clear on release: `self.preview_item.setPath(QPainterPath())` (mirror `canvas.py:893`).

---

### `manga_ai_studio/gui/main_window.py` (controller, MODIFY — 6 distinct seams)

**Analog:** itself — Phase 3 wires 6 seams, each mirroring an existing pattern in this same file.

**Seam 1 — `_on_detection_finished` stop discarding `blk_list`** (`main_window.py:1284-1303`):
```python
def _on_detection_finished(self, result) -> None:
    import numpy as np
    mask = result["mask"]                           # Phase 1 (kept)
    ...
    self.canvas.set_mask(qimage.copy())
    # [NEW D-01/D-03] if Detect Boxes mode on: build BoxItems from result["blocks"]
    #   result["blocks"] is ALREADY in the dict (main_window.py:1217) — Phase 1 discards it.
```
The worker already returns `{"mask": mask_refined, "blocks": blk_list}` (`main_window.py:1217`) — NO worker change. The 3-tuple unpack is at `adapters/torch_impl.py:124` (verified).

**Seam 2 — `_confirm_replace_mask` confirm-gate pattern (D-04 mirror)** (`main_window.py:1328-1348`):
```python
def _confirm_replace_mask(self) -> bool:
    box = QMessageBox(self)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Detect Text")
    box.setText(
        "Replace the current mask with a new detection? Your manual edits"
        " will be lost \u2014 undo is available via mask undo (Alt+Z)."
    )
    cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    replace_btn = box.addButton("Replace Mask", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(replace_btn)
    box.exec()
    return box.clickedButton() is replace_btn
```
D-04 mirrors this verbatim in structure: title "Detect Text", body "Replace the detected text boxes with a new detection? Boxes you drew yourself are kept. Undo is available via Ctrl+Z.", buttons `[Cancel] [Replace Detected Boxes]` (UI-SPEC §Copywriting). Fires AFTER the mask gate if a mask is also present.

**Seam 3 — `on_page_selected` 5-step persistence seam (Phase 2 D-11 mirror)** (`main_window.py:653-747`):
```python
# Step 1 (persist OUTGOING) — main_window.py:695-705
outgoing_idx = self._last_page_index
if (outgoing_idx is not None and 0 <= outgoing_idx < len(self.image_files)
        and self.canvas.has_mask()):
    self.image_files[outgoing_idx].mask = self.canvas.get_mask().copy()   # MANDATORY .copy()
# [NEW] if self.canvas.has_boxes():
#         self.image_files[outgoing_idx].boxes = self.canvas.boxes_snapshot()   # detaches (Pitfall 3)

# Step 2: self.reset_history()   (main_window.py:708 — will reset all 3 stacks)

# Step 4 (restore INCOMING) — main_window.py:724-734
incoming_idx = self._current_page_index()
if (incoming_idx is not None and ... and self.image_files[incoming_idx].mask is not None
        and not self.image_files[incoming_idx].mask.isNull()):
    self.canvas.set_mask(self.image_files[incoming_idx].mask.copy())   # boundary .copy()
# [NEW] if self.image_files[incoming_idx].boxes:
#         self.canvas.set_boxes([b for b in self.image_files[incoming_idx].boxes])   # .copy()-detach
```
The OUTGOING index MUST come from `self._last_page_index` (NOT `_current_page_index()` — it has already flipped; documented `main_window.py:663-672`).

**Seam 4 — View menu + Tools menu + toolbar wiring** (`main_window.py:286-335` view menu, `337-403` tools menu, `443-459` toolbar undo section):
- `action_toggle_box_overlay` mirrors `action_toggle_mask_overlay` at `main_window.py:304-308` (checkable, `Shift+M`, enabled iff page open).
- `action_detect_boxes_mode` (D-01) mirrors the checkable-action pattern — add to Tools menu; default checked (UI-SPEC §Copywriting A1).
- Place `Toggle Box Overlay` immediately AFTER `Toggle Mask Overlay` in `_build_view_menu` (sibling layer toggles, `main_window.py:331`).

**Seam 5 — Undo collapse (Surface 13)** (`main_window.py:263-284` edit menu, `449-457` toolbar undo section, `920-942` shortcuts):
```python
# Existing (REMOVE in Phase 3):
(QKeySequence("Alt+Z"), self.on_undo_mask),           # main_window.py:925
(QKeySequence("Alt+Shift+Z"), self.on_redo_mask),     # main_window.py:926
self.action_undo_mask = QAction("Undo Mask", self)    # main_window.py:269
edit_menu.addAction(self.action_undo_mask)             # main_window.py:281
self.toolbar.addAction(self.action_undo_mask)          # main_window.py:456
```
Replace with unified `Ctrl+Z`/`Ctrl+Shift+Z` over the merged timeline (D-11). The 4-button toolbar collapses to 2 (`[Undo][Redo]`); the 4 edit-menu items collapse to 2.

**Seam 6 — Two orphaned `Alt+Z` strings (UI-SPEC §Copywriting PLANNER TODO)** — string-level edits:
- `main_window.py:1103-1104`: `" (Alt+Z)."` → `" (Ctrl+Z)."` (Clear Mask confirm)
- `main_window.py:1342`: `"undo is available via mask undo (Alt+Z)."` → `"undo is available via Ctrl+Z."` (Replace Mask confirm)

---

### `manga_ai_studio/gui/tools_panel.py` (component, CONFIRM no change per D-07)

**Analog:** itself. D-07 is explicit: no 6th tool in the `QActionGroup` (`tools_panel.py:105-124`). Box selection/move is tool-agnostic (boxes always interactive when the layer is visible). The create-box gesture is `Alt+drag` on the canvas (D-13), not a panel control. **Expected outcome: zero source edits.** The planner's task is "confirm D-07 holds" — a read-only verification, not a modification.

---

### Group D — Undo (core/)

---

### `manga_ai_studio/core/history_manager.py` (service, MODIFY — BOXES stack + unified timeline)

**Analog:** itself — the 2-stack push/pop/reset API at `history_manager.py:49-192`.

**The 2-stack shape to extend** (`history_manager.py:65-84`):
```python
def __init__(self, limit: int = DEFAULT_HISTORY_LIMIT) -> None:
    self.limit = int(limit)
    self._mask_undo: list[QImage] = []
    self._mask_redo: list[QImage] = []
    self._image_undo: list[ImageAction] = []
    self._image_redo: list[ImageAction] = []
```

**The `.copy()` push/pop discipline to replicate for BOXES** (`history_manager.py:81, 99, 112`):
```python
def push_mask_state(self, mask_qimage: QImage) -> None:
    self._mask_undo.append(mask_qimage.copy())     # <-- .copy() on push
    self._mask_redo.clear()
    if len(self._mask_undo) > self.limit:
        self._mask_undo.pop(0)

def pop_mask_undo(self, current_mask: QImage) -> QImage | None:
    if not self._mask_undo:
        return None
    previous = self._mask_undo.pop()
    self._mask_redo.append(current_mask.copy())    # <-- .copy() on the redo stash
    return previous.copy()                         # <-- .copy() on the return
```

**Pitfall 4 (RESEARCH) — widen Phase 1's TWO store entry shapes to `(stamp, value)`** so the unified timeline can compare timestamps across all three stores. Today (`history_manager.py:81, 124`):
```python
self._mask_undo.append(mask_qimage.copy())                       # bare QImage
self._image_undo.append((int(x), int(y), patch.copy()))          # bare (x,y,patch)
```
Phase 3 wraps each entry as `(stamp, value)`:
```python
self._mask_undo.append((self._stamp(), mask_qimage.copy()))             # (stamp, QImage)
self._image_undo.append((self._stamp(), (int(x), int(y), patch.copy())))# (stamp, (x,y,patch))
self._boxes_undo.append((self._stamp(), boxes_snapshot))                # (stamp, list[PageBox])
```
This is a **mechanical change to the four existing push/pop methods** (`push_mask_state`, `pop_mask_undo`, `pop_mask_redo`, `push_image_action`, `pop_image_undo`, `pop_image_redo`) — wrap/unwrap the stamp. The push/pop SEMANTICS are unchanged; only the container shape widens. **`tests/test_history.py`'s existing guards assert on the bare values and MUST be updated to unpack `(stamp, value)`** (flagged as a Wave 0 task).

**Pitfall 3 (RESEARCH) — the BOXES snapshot must materialize fresh `Box` tuples, NOT alias live `BoxItem`s:**
```python
def push_boxes_state(self, boxes: list) -> None:
    # Materialize a fresh Box per item from its CURRENT QRectF at push-time
    # (the BoxItem's QRectF mutates live during drag; a reference would alias).
    snap = [(
        b.box,                                    # vendored Box is @frozen — safe to share
        b.origin,
        b.payload,
    ) for b in boxes]
    self._boxes_undo.append((self._stamp(), snap))
    self._boxes_redo.clear()
    if len(self._boxes_undo) > self.limit:
        self._boxes_undo.pop(0)
```
The caller (`canvas.boxes_snapshot()`) must read each `BoxItem.rect()` → `Box(int(r.x()), int(r.y()), int(r.x()+r.width()), int(r.y()+r.height()))` at snapshot time (Pitfall 6 — round to int at every Box↔QRectF boundary). Regression guard: `test_boxes_snapshot_is_detached` (mirrors `test_mask_snapshot_is_copied`).

**The unified-timeline pop (the ONE genuinely new algorithm)** (RESEARCH §Pattern 2):
```python
def undo(self, current_mask, current_img, current_boxes):
    """Unified pop (D-11): most-recent-by-stamp across all three stores."""
    candidates = []
    if self._mask_undo:   candidates.append(("mask",  self._mask_undo[-1][0]))
    if self._image_undo:  candidates.append(("image", self._image_undo[-1][0]))
    if self._boxes_undo:  candidates.append(("boxes", self._boxes_undo[-1][0]))
    if not candidates:
        return None
    kind = max(candidates, key=lambda c: c[1])[0]
    if kind == "mask":  return ("mask",  self.pop_mask_undo(current_mask))
    if kind == "image": return ("image", self.pop_image_undo(current_img))
    return ("boxes", self.pop_boxes_undo(current_boxes))
```
Use a **monotonic integer counter** (`self._seq += 1`), NOT wall-clock (time skew across threads — Pitfall 4). Phase 1's per-type pop methods stay; the unified pop delegates to them.

**The `clear()` reset to extend** (`history_manager.py:183-192`) — add the two BOXES lists:
```python
def clear(self) -> None:
    self._mask_undo.clear(); self._mask_redo.clear()
    self._image_undo.clear(); self._image_redo.clear()
    self._boxes_undo.clear(); self._boxes_redo.clear()   # [NEW]
```

**Anti-pattern (CONTEXT D-10 / STATE.md "two logical stacks not four"):** BOXES is ONE logical stack, not split per-op-type (create/move/resize/delete). Op-type lives inside each record's metadata, not as separate lists.

---

## Shared Patterns (cross-cutting — apply to ALL relevant Phase 3 files)

### Shared Pattern 1 — `.copy()` buffer discipline (Phase 1 Pitfall 2 / RESEARCH Pitfall 2 + 3)

**Source:** every numpy↔QImage and numpy↔history bridge in `canvas.py` + `history_manager.py`. **Apply to:** `box_model.py` (Box↔QRectF int-coercion), `image_file.py` (`boxes` slot save/restore), `canvas.py` (`boxes_snapshot`), `history_manager.py` (BOXES push/pop).

The load-bearing call sites the box paths must mirror:
```python
# canvas.py:270  set_image_from_path — detach load buffer
image = image.copy()
# canvas.py:305  set_mask — detach incoming numpy/shared buffer
mask_qimage = mask_qimage.copy()
# canvas.py:329  set_mask — detach the built tinted array before it becomes a pixmap
tinted = tinted.copy()
# canvas.py:507  get_image_numpy — detach numpy from QImage before qimg GCs
return arr.copy()
# canvas.py:563  set_image_from_numpy — detach QImage from numpy buffer before storage (the CRITICAL one)
qimg = qimg.copy()
# canvas.py:417  apply_undo_mask — detach from history's internal list
self._mask = mask_qimage.copy()
# history_manager.py:81,99,112,124,146,163 — .copy() on EVERY push AND pop
```
For BOXES specifically (Pitfall 3): the snapshot must materialize fresh `Box(int(...), ...)` tuples from each `BoxItem.rect()` at push-time — a live `BoxItem` reference would mutate mid-drag. The regression guard `test_boxes_snapshot_is_detached` mirrors `test_mask_snapshot_is_copied`.

### Shared Pattern 2 — Per-page persistence seam (Phase 2 D-11 / T-02-04)

**Source:** `main_window.py:653-747` (`on_page_selected` 5-step). **Apply to:** `image_file.py` (`boxes` slot), `main_window.py` (extend Step 1 + Step 4), `test_box_persistence.py`.

The exact 5-step shape (extracted above under Seam 3). The belt-and-suspenders `.copy()` at BOTH boundaries (outgoing save + incoming restore) is what `test_mask_persistence_uses_copy` asserts on — `test_box_persistence_uses_copy` mirrors it. For boxes the detach is "materialize fresh `Box` tuples" (Shared Pattern 1) rather than `QImage.copy()`.

### Shared Pattern 3 — QGraphicsScene layered-item + dispatch

**Source:** `canvas.py:120-225` (constructor scene setup) + `canvas.py:758-837` (mouse events). **Apply to:** `box_item.py` (the new layered items), `canvas.py` (the box hit-test slot).

The z-order stack (UI-SPEC §Z-order) is an additive superset of the existing one: image(0) → mask(0) → **box layer(100, NEW)** → **handles(150, NEW)** → **empty-box-hint(850, NEW)** → preview(900) → cursor(1000) → empty-state(2000). The mouse dispatch slots the box branch between pan and the mask-tool branch (Pattern 3 under `box_item.py` above).

### Shared Pattern 4 — Confirm-gate dialog (`QMessageBox` custom buttons)

**Source:** `main_window.py:1328-1348` (`_confirm_replace_mask`) + `main_window.py:1093-1110` (`_confirm_clear_mask`). **Apply to:** `main_window.py` (`_confirm_replace_boxes` for D-04).

Copy the structure verbatim — custom `[Cancel] [Verb Noun]` buttons (Qt has no "Replace"/"Clear" standard member), `setDefaultButton`, `box.exec()`, return `clickedButton() is verb_btn`. Body copy names the action, states what is kept/lost, names the recovery path (Ctrl+Z) — UI-SPEC §Copywriting locks the exact strings.

### Shared Pattern 5 — Worker(QRunnable) async dispatch (unchanged from Phase 1)

**Source:** `main_window.py:1122-1163` (`detect_text`) + `main_window.py:1165-1217` (`_run_detection_task`). **Apply to:** NO new worker — Phase 3 boxes ride on the EXISTING detect worker (`result["blocks"]` is already in the dict at `main_window.py:1217`). The thread-safety contract (T-01-07): worker touches only numpy/Python; Qt mutation only in main-thread `_on_detection_finished` (where BoxItems are built — safe).

### Shared Pattern 6 — Test scaffolding

**Source:** `tests/conftest.py` (top-level `pytest.importorskip("PySide6")` + `profile_manager` fixture), `tests/test_core/conftest.py` (fake adapters), `pytest.ini` (`qt_api=pyside6`, `unit`/`gui` markers). **Apply to:** all 6 new test files.

- **Headless unit tests** (`test_structures.py`, `test_masker_vendor.py`, `test_box_model.py`, `test_history_boxes.py`): copy `tests/test_core/test_image_io.py:1-45` header — `from __future__ import annotations`, `@pytest.mark.unit`, pure numpy/stdlib, NO qtbot fixture. Headless CI runs these.
- **GUI tests** (`test_gui_boxes.py`, `test_box_persistence.py`): copy `tests/test_gui_canvas.py:1-58` header — `pytest.importorskip("PySide6")`, `qtbot` fixture, construct `MainWindow(profile_manager)` via the shared fixture, synthesize `QMouseEvent`s. Marked `@pytest.mark.gui`.
- **Fake-detection adapter** (`tests/test_core/conftest.py:FakeDetectionModel`): for `test_gui_boxes.py` / the detection-seam tests, reuse this fake — it already returns `(mask, blk_list)`. Extend it to return a non-empty `blk_list` of fake `TextBlock`s for the box-build path.

---

## No Analog Found

None. Every Phase 3 file has a concrete in-repo analog:
- The two vendored files → the Phase 1 D-12 vendoring header in `image_ops.py` + the upstream PanelCleaner source.
- The new `box_item.py` + `box_model.py` → `canvas.py` + `image_file.py` + `mask_editor.py`.
- The 5 modified files → themselves (additive changes mirroring existing regions).
- The 6 test files → `test_history.py` / `test_gui_canvas.py` / `test_image_io.py` / `conftest.py`.

The ONE genuinely new algorithmic piece is the unified-timeline pop in `history_manager.py` (RESEARCH §Pattern 2) — but even that delegates to the existing per-type pop methods, so its analog is the same file's `pop_mask_undo`/`pop_image_undo`.

---

## Metadata

**Analog search scope:** `manga_ai_studio/` (core/, gui/, adapters/), `panelcleaner/` (vendored tree), `C:\Src\PanelCleaner\pcleaner\` (upstream GPL v3 source), `tests/` (test_core/, top-level), `pytest.ini`.

**Files scanned (read in full or via targeted ranges):**
- Full read: `history_manager.py` (192), `image_file.py` (110), `mask_editor.py` (207), `tools_panel.py` (275), `canvas.py` (977), `panelcleaner/structures.py` stub (17), test analogs (`test_history.py`, `test_gui_canvas.py`, `test_image_io.py`, both `conftest.py`), `pytest.ini`, PanelCleaner upstream `structures.py` head + `masker.py` imports.
- Targeted ranges (file > 2000 lines): `main_window.py` ranges 80-239, 260-459, 645-764, 920-1079, 1090-1217, 1294-1349, 1505-1604 (all non-overlapping).

**Pattern extraction date:** 2026-07-27

**Cross-references for the planner:**
- RESEARCH.md §Pattern 1 (BoxItem skeleton), §Pattern 2 (unified-timeline pop), §Pattern 3 (hit-test dispatch) — these are already concrete; PATTERNS.md locates their analogs and adds the `.copy()`/dispatch/confirm-gate call sites the planner's action steps need.
- 03-UI-SPEC.md §Z-order, §12a-12g (BoxItem spec), §13 (undo collapse), §Copywriting (confirm-gate strings + the two orphaned Alt+Z PLANNER TODOs at `main_window.py:1104, 1342`).
- Pitfalls 1-6 (RESEARCH §Common Pitfalls) map to: ost-stub (file 2), full-structures-required (file 1), snapshot-detach (file 7 + Shared Pattern 1), stamp-widen (file 7), hidden-layer-hit-test (file 5), int-at-QRectF-boundary (file 3 + file 7).

# Phase 4: OCR Recognition & Text Editing - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 15 (7 new + 8 modified)
**Analogs found:** 15 / 15 (every file has at least a role-match analog; the inline-editor proxy and vertical-editor have no exact codebase analog and lean on RESEARCH.md + UI-SPEC)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `manga_ai_studio/adapters/torch_impl.py` (+`TorchOCRModel`) | adapter / model | request-response (numpy→str) | `adapters/torch_impl.py` `TorchLamaModel` (lines 166-281) | **exact** |
| `panelcleaner/ocr/ocr_mangaocr.py` (NEW vendored) | utility / wrapper | request-response (singleton) | `../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py` (vendor reference) + existing `panelcleaner/ocr/supported_languages.py` (already vendored) | **exact** (near-verbatim vendor) |
| `manga_ai_studio/gui/inspector_panel.py` (NEW) | component / dock | request-response (property follower) | `gui/tools_panel.py` `ToolsPanel(QWidget)` + `gui/main_window.py:200-221` `_build_docks` | **exact** (dock+panel) |
| `manga_ai_studio/gui/inline_editor.py` (NEW, or within `box_item.py`) | component / overlay | request-response (transient edit) | `gui/box_item.py` `CornerHandle` (child QGraphicsItem pattern) + UI-SPEC §15 (`QGraphicsProxyWidget`) | **role-match** (proxy has no codebase analog) |
| `manga_ai_studio/gui/load_translations_dialog.py` (NEW) | component / dialog | file-I/O + transform | `gui/main_window.py:1711-1792` `_confirm_replace_boxes`/`_confirm_replace_mask` (QDialog pattern) | **role-match** |
| `manga_ai_studio/core/translation_parser.py` (NEW) | utility / parser | transform (string→dict→apply) | `core/box_model.py` (pure-stdlib module) + PanelCleaner `parsers.py` `ParseError` pattern (NOT its format) | **role-match** |
| `manga_ai_studio/core/reading_order.py` (NEW) | utility / algorithm | transform (geometry→permutation) | `core/box_model.py` (pure-stdlib, headless-testable) | **role-match** |
| `manga_ai_studio/adapters/factory.py` (MOD) | config / factory | request-response | existing `backend_factory("detection")` block (`factory.py:37-48`) | **exact** |
| `manga_ai_studio/adapters/base.py` (MOD) | config / ABC | n/a (signature confirm) | existing `OCRModel` ABC (`base.py:71-96`) | **exact** (already exists) |
| `manga_ai_studio/core/box_model.py` (MOD) | model | CRUD | existing `PageBox` + D-15 seam (`box_model.py:52-81`) | **exact** |
| `manga_ai_studio/gui/box_item.py` (MOD) | component | request-response (render + interaction) | existing `BoxItem` + `CornerHandle` (`box_item.py:126-372`) | **exact** |
| `manga_ai_studio/gui/canvas.py` (MOD) | component / controller | request-response + event-driven | existing `_commit_create` (canvas.py:1487), `boxes_snapshot` (1276), `_box_item_at` (1337), `set_box_overlay_visible` | **exact** |
| `manga_ai_studio/gui/main_window.py` (MOD) | controller | request-response (async dispatch) | `detect_text`/`_run_detection_task`/`_resolve_detection_model_path` (`main_window.py:1404-1555`), `_build_menus` (224), `_build_docks` (200) | **exact** |
| `manga_ai_studio/core/history_manager.py` (MOD) | model / undo stack | event-driven (snapshots) | existing `_materialize_snapshot` (252) + `push_boxes_state` (277) | **exact** |
| `manga_ai_studio/core/image_file.py` (MOD) | model | file-I/O (per-page slot) | existing `boxes` slot (`image_file.py:75`) + `mask` slot (74) | **exact** |

## Pattern Assignments

### `manga_ai_studio/adapters/torch_impl.py` (+ `TorchOCRModel`) (adapter, request-response)

**Analog:** existing `TorchLamaModel` in the SAME file (`adapters/torch_impl.py:166-281`). This is the single best analog — `TorchOCRModel.recognize(numpy) → str` mirrors `TorchLamaModel.inpaint(numpy, mask) → numpy` shape-for-shape (lazy-import in `load()`, path validation before import, numpy→PIL round-trip, plain Python return). RESEARCH §Pattern 1 (lines 257-284) locks this.

**Class skeleton pattern** (`torch_impl.py:166-200`):
```python
class TorchLamaModel(InpaintModel):
    """LaMa inpainting PyTorch backend (D-01/D-02; CLEAN-06).  ..."""

    def __init__(self, config=None) -> None:
        self.config = config
        self.model = None          # the singleton wrapper instance
        self.model_path = None

    def load(self, model_path: Path, device: str = "cpu") -> None:
        # Validate the path BEFORE the heavy import (T-01-04b)
        ...
        # Lazy import (D-07): keep module importable without the heavy dep.
        from simple_lama_inpainting import SimpleLama  # noqa: WPS433
        self.model = SimpleLama()
        self.model_path = model_path
```
Copy this skeleton; swap the ABC base (`OCRModel`), the lazy import (`from panelcleaner.ocr.ocr_mangaocr import MangaOcr`), and call `MangaOcr().initialize_model()`.

**numpy→PIL round-trip pattern** (`torch_impl.py:245-246`) — this is the load-bearing line for Pitfall 2 (manga-ocr accepts `PIL.Image`, NOT numpy):
```python
pil_image = Image.fromarray(image, mode="RGB")
pil_mask = Image.fromarray(mask_binary, mode="L")
...
result_pil = self.model(pil_image, pil_mask)
```
`TorchOCRModel.recognize` does the one-line variant: `pil_image = Image.fromarray(image, mode="RGB"); return self.model(pil_image)  # → str`.

**preprocess/postprocess/get_info/configure stubs** (`torch_impl.py:256-280`) — copy verbatim shape (return-input-unchanged / return-metadata-dict). RESEARCH §Pattern 1 gives the exact `TorchOCRModel` body.

**Error pattern:** "Model not loaded — call load() before ..." guard (`torch_impl.py:237`). Keep it identical.

---

### `panelcleaner/ocr/ocr_mangaocr.py` (NEW vendored) (utility / singleton wrapper)

**Analog (vendor reference):** `../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py` (43 lines, GPL v3). Vendor near-verbatim per D-14 / Phase 1 D-12 (GPL v3 → GPL v3). The full source is the contract (RESEARCH §Code Examples, lines 493-525):

```python
# Source: ../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py (GPL v3)
from pathlib import Path
from loguru import logger
from manga_ocr import MangaOcr as MangaOcrModel
from PIL import Image
import pcleaner.ocr.supported_languages as osl   # → re-path to panelcleaner.ocr.supported_languages

class MangaOcr:
    _instance = None
    _model = None
    _init_args = ((), {})

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            logger.info("Creating the MangaOcr instance")
            cls._instance = super(MangaOcr, cls).__new__(cls)
            cls._instance._model = None
            cls._instance._init_args = (args, kwargs)
        return cls._instance

    def __init__(self, *args, **kwargs):
        pass  # deferred to initialize_model()

    def initialize_model(self, *args, **kwargs):
        if self._model is None:
            if args or kwargs:
                self._model = MangaOcrModel(*args, **kwargs)
            else:
                init_args = self._init_args
                self._model = MangaOcrModel(*init_args[0], **init_args[1])
        return self._model

    def __call__(self, img_or_path: Image.Image | Path | str, **kwargs) -> str:
        model = self.initialize_model()
        return model(img_or_path)
```
**Vendor re-path note:** the upstream `import pcleaner.ocr.supported_languages as osl` → re-path to `import panelcleaner.ocr.supported_languages as osl` (the vendored dir is `panelcleaner/`, and `supported_languages.py` is ALREADY vendored there — confirmed `panelcleaner/ocr/supported_languages.py` exists). The `langs()` staticmethod may be dropped if Phase 4 doesn't surface it (D-14: no config UI in v1).

**Placement:** `panelcleaner/ocr/ocr_mangaocr.py` (next to the already-vendored `supported_languages.py`), NOT a new `manga_ai_studio/ocr/` dir — keeps the GPL v3 vendored boundary clean and matches the existing `panelcleaner/comic_text_detector/...` + `panelcleaner/inpainting.py` vendoring layout.

---

### `manga_ai_studio/gui/inspector_panel.py` (component / dock, request-response)

**Analog:** `gui/tools_panel.py` `ToolsPanel(QWidget)` (lines 86-275) — same role (a QWidget with typed `Signal`s, dark QSS, consumed by a `QDockWidget` in `main_window`). PLUS the dock-instantiation pattern in `gui/main_window.py:200-221`.

**Widget skeleton pattern** (`tools_panel.py:86-102`):
```python
class ToolsPanel(QWidget):
    """The Tools dock panel: 5 exclusive tool buttons + brush-size control."""

    tool_changed = Signal(object)        # typed signals at class scope
    brush_size_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tools_panel")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)   # sm margins (UI-SPEC §Spacing)
        root.setSpacing(8)
        ...
        self.setStyleSheet(_TOOLS_QSS)
```
`InspectorPanel` mirrors this: class-scope `Signal`s (e.g. `translation_changed(str)`, `recognized_edited(str)`, `bubble_no_changed(int)`), a `QFormLayout`/`QVBoxLayout` root, the dark QSS. Add `QTextEdit`/`QLineEdit` for the two text fields + `QSpinBox` (bubble number) + read-only `QLabel`s (origin/language/vertical).

**Dark QSS pattern** (`tools_panel.py:49-83`) — copy the `#2d2d33` surface / `#3a3a42` border / `#e8e8ea` text / `#00d4ff` accent tokens verbatim. Reuse for `QTextEdit`/`QSpinBox` (already in the QSS for the brush spinbox).

**Dock instantiation pattern** (`main_window.py:213-221`):
```python
# Tools dock -> ToolsPanel (plan 04: the 5-tool panel + brush slider).
self.dock_tools = QDockWidget("Tools", self)
self.dock_tools.setObjectName("dock_tools")
self.dock_tools.setAllowedAreas(
    Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
)
self.tools_panel = ToolsPanel()
self.dock_tools.setWidget(self.tools_panel)
self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_tools)
```
Copy this block for the Inspector dock (UI-SPEC §Surface — right dock, sibling of Tools). Rename objectName/widget/area per UI-SPEC.

**Selection-follower pattern:** Inspector reads/writes the selected `PageBox`. Get the selected box via `canvas._selected_box()` (canvas.py:1330-1335) — same call the move/resize state machine uses. Edits commit through the box-model setters (see `box_model.py` assignment), NOT by direct payload mutation.

---

### `manga_ai_studio/gui/inline_editor.py` (component / overlay, request-response)

**Analog (closest):** `gui/box_item.py` `CornerHandle` (lines 126-230) — the existing child-`QGraphicsItem`-with-`ItemIgnoresTransformations` + z-order pattern. The editor itself uses `QGraphicsProxyWidget(QTextEdit)` per UI-SPEC §15, which has NO codebase analog (first proxy widget in the project) — lean on RESEARCH §Pattern 3 + UI-SPEC §15.

**Child-item z-order + flags pattern** (`box_item.py:142-162`):
```python
class CornerHandle(QGraphicsRectItem):
    def __init__(self, corner: str, parent: "BoxItem") -> None:
        super().__init__(0, 0, _HANDLE_SIZE, _HANDLE_SIZE, parent)
        self.corner = corner
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(_HANDLE_Z)   # = 150
        ...
        self.setVisible(False)      # hidden until parent selected
```
**Z-order contract** (UI-SPEC §Z-order, RESEARCH Pitfall 7): text overlay z=120, bubble badge z=140, handles z=150 (existing `_HANDLE_Z`), inline editor proxy z=1100 (above cursor z=1000). Use these constants.

**CRITICAL anti-pattern** (RESEARCH Pitfall 3, UI-SPEC §15): parent the editor proxy to the SCENE, NOT the BoxItem — parenting to the box inherits its transform and breaks the editor coordinate system. Position it via `proxy.setPos(box_item.sceneBoundingRect().topLeft())` + `proxy.setWidget(...)` with a `QTextEdit` sized to the box rect in scene coords.

**Visibility/event-dispatch pattern:** the editor is transient (appears on double-click, disappears on commit/cancel). Mirror `CornerHandle`'s `setVisible(False)` default + the canvas dispatch check. RESEARCH §Pitfall 3: the canvas mouse-press dispatch MUST check "is the inline editor active? is the click outside it?" BEFORE any other dispatch (before the existing `_box_item_at` hit-test at canvas.py:1337).

**Commit/cancel seam:** commit writes through the box-model setter (`set_recognized_text` / `set_translation` — see `box_model.py` assignment) and pushes a BOXES snapshot via `canvas.boxes_modified.emit(self.boxes_snapshot())` (same emission point as `_commit_create` at canvas.py:1517 and `_remove_box` at 1533). Esc cancels with no emission.

**No codebase analog for:** `QGraphicsProxyWidget` focus/IME handling (RESEARCH §Pitfall 3) and the vertical-edit toggle (RESEARCH §Pitfall 5 — ship as a no-op fallback per UI-SPEC; do NOT hand-roll vertical CJK layout).

---

### `manga_ai_studio/gui/load_translations_dialog.py` (component / dialog, file-I/O + transform)

**Analog (dialog structure):** `gui/main_window.py:1711-1792` `_confirm_replace_boxes` / `_confirm_replace_mask` — the project's QDialog pattern (custom buttons, `exec()`, return bool/result). PLUS `_resolve_detection_model_path`-adjacent `QFileDialog` usage (the `export_page` action at main_window.py:258-261 uses `QFileDialog.getSaveFileName`; the import variant is `QFileDialog.getOpenFileName`).

**QDialog pattern** (`main_window.py:1711-1737`):
```python
def _confirm_replace_boxes(self) -> bool:
    box = QMessageBox(self)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Detect Text")
    box.setText("Replace the detected text boxes ...")
    cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    replace_btn = box.addButton("Replace Detected Boxes", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(replace_btn)
    box.exec()
    return box.clickedButton() is replace_btn
```
For `LoadTranslationsDialog` use a `QDialog` (not `QMessageBox`) since it needs a `QPlainTextEdit` paste area + a page picker + Apply/Cancel. Same custom-button + `exec()` shape; return `(matches_dict, page_no)` or `None`.

**File-read pattern** (RESEARCH §Security V12): open with `open(path, "r", encoding="utf-8")`; catch `OSError`/`UnicodeDecodeError` → user-friendly "Couldn't read '{filename}'" dialog (mirror the `_on_detection_error` error UX at main_window.py:1749-1764: traceback to loguru, friendly copy in the dialog). File-select via `QFileDialog.getOpenFileName(self, "Load Translations", "", "Text files (*.txt)")`.

**Apply seam:** the dialog does NOT mutate boxes directly — it returns the parsed matches and the MainWindow applies them through `translation_parser.apply_translations(...)` + pushes ONE BOXES snapshot (RESEARCH Open Question 4: one batch undo entry, not one-per-box). Mirror the single-snapshot push at `_commit_create` (canvas.py:1517).

---

### `manga_ai_studio/core/translation_parser.py` (utility / parser, transform)

**Analog (module shape):** `core/box_model.py` — pure stdlib, headless-testable, no Qt, module-level constants + small functions. PanelCleaner's `parsers.py` is a DIFFERENT format (CSV with file-path headers — RESEARCH §Don't Hand-Roll, line 404) and is NOT directly reusable, but its `ParseError`/error-code enum pattern is worth mirroring for the report UX.

**Pure-module pattern** (`box_model.py:38-49`):
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
# NO Qt imports. Headless-testable (pytest -m unit).
```
Follow the same header: module docstring citing CONTEXT D-15, `from __future__ import annotations`, stdlib-only imports, `@pytest.mark.unit`-compatible.

**Regex + match contract** (RESEARCH §Code Examples, lines 570-614 — the exact contract):
```python
import re
BUBBLE_RE = re.compile(r"^\[(\d+)\]:\s*(.*)$")      # [1]: text
SFX_RE     = re.compile(r"^\[SFX\s+-\d+\]:\s*\*.*\*$")  # [SFX -3]: *text* (recognized, NOT matched — D-15(d))

def parse_translations(text: str) -> tuple[dict[int, str], int]:
    """Returns (matches, skipped_count). SFX + unparseable lines count as skipped."""
    ...

def apply_translations(matches: dict[int, str], boxes: list, page_no=None) -> tuple[int, int]:
    """Fill set_translation() on boxes whose bubble_no matches. Returns (applied, unmatched)."""
    box_by_no = {b.bubble_no: b for b in boxes if b.bubble_no is not None}
    ...
```
Copy these signatures verbatim. `apply_translations` keys off `box.bubble_no` (the new PageBox field — see `box_model.py` assignment) and calls `box.set_translation(text)` (the MT seam, D-13).

**Error handling pattern:** parser NEVER raises on malformed input (ASVS V5 — skip + report). Return the `(applied, unmatched)` counts so the caller (MainWindow) can show a `QMessageBox` with "Applied N translations; M lines had no matching bubble." Mirror `_confirm_replace_boxes` (main_window.py:1711) for the report-dialog shape.

---

### `manga_ai_studio/core/reading_order.py` (utility / algorithm, transform)

**Analog (module shape):** `core/box_model.py` (pure-stdlib, headless-testable geometry). No existing geometry-algorithm module — this is the first. RESEARCH §Pattern 4 (lines 349-383) gives the XY-Cut algorithm verbatim.

**Pure-module pattern:** same header as `translation_parser.py` (above) — `from __future__ import annotations`, stdlib only (`statistics`, `re` not needed), `@pytest.mark.unit`-compatible.

**Algorithm contract** (RESEARCH §Pattern 4):
```python
def reading_order(box_centers_xy: list[tuple[float, float]], rtl: bool) -> list[int]:
    """Return indices that sort box_centers_xy into reading order.
    XY-Cut: detect column gaps by center-x clustering (tol derived from median box width),
    bucket each box into a column, sort within-column top-to-bottom by center-y,
    order columns LTR (manhwa) or RTL (manga).
    """
```
Input: `list[(cx, cy)]` per box (compute centers from `box.as_tuple_xywh` — see `box_item.py:256` `Box.as_tuple_xywh` for the accessor; center = `(x + w/2, y + h/2)`). Output: a permutation of `range(n)` — the caller assigns `bubble_no = i+1` for `i` in the permutation.

**RTL reversal:** `ordered_cols = sorted(columns.keys(), reverse=rtl)` — the single-line RTL/LTR switch (RESEARCH §Pattern 4 line 376).

**Threshold derivation (RESEARCH Assumption A2, MEDIUM risk):** derive `col_tol` from the page's OWN box geometry (median box width), NOT a fixed pixel constant — fixed tolerances are fragile across page sizes. The end-of-phase human-verify gate picks the final threshold against real pages.

---

### `manga_ai_studio/adapters/factory.py` (MOD — config / factory)

**Analog:** the EXISTING `backend_factory("detection")` block in the SAME file (`factory.py:37-48`) and `backend_factory("inpainting")` (`factory.py:53-60`). The stub to replace is `factory.py:50-51`.

**Replace this** (`factory.py:50-51`):
```python
if kind == "ocr":
    raise NotImplementedError("OCR adapter lands in Phase 4")
```
**With this** (mirror the detection block at 37-43):
```python
if kind == "ocr":
    if backend == "torch":
        # Lazy import: manga-ocr/transformers are only needed when an OCR
        # model is actually constructed, not when the factory is imported (D-07).
        from manga_ai_studio.adapters.torch_impl import TorchOCRModel
        return TorchOCRModel()
    if backend == "onnx":
        # D-14 hook: designed-in, not built-out. ONNXOCRModel lands in a future phase.
        raise NotImplementedError("ONNX OCR backend lands in a future phase")
    raise ValueError(f"Unknown backend: {kind}/{backend}")
```
**Imports pattern** (`factory.py:19`): `from manga_ai_studio.adapters.base import DetectionModel, InpaintModel, OCRModel` — already imports `OCRModel`; the OCRModel is referenced in the return type union (`factory.py:22`) so the signature needs NO change.

---

### `manga_ai_studio/adapters/base.py` (MOD — ABC, signature confirm)

**Analog:** the EXISTING `OCRModel` ABC (`base.py:71-96`). It is ALREADY the seam — likely NO change needed. The abstract methods:
```python
class OCRModel(ABC):
    @abstractmethod
    def load(self, model_path: Path, device: str = "cpu") -> None: ...
    @abstractmethod
    def recognize(self, image: np.ndarray) -> str: ...   # ← the contract TorchOCRModel implements
    @abstractmethod
    def preprocess(self, image: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def postprocess(self, model_output) -> str: ...
    @abstractmethod
    def configure(self, **kwargs) -> None: ...
    @abstractmethod
    def get_info(self) -> dict: ...
```
**Confirm only:** verify `recognize(self, image: np.ndarray) -> str` matches `TorchOCRModel.recognize` exactly (RESEARCH §Pitfall 2 — the ABC takes numpy, the adapter does the numpy→PIL conversion internally; the ABC signature stays numpy). No edit unless the planner adds config hooks (D-14 — model/language/backend hooks "designed-in, not built-out"; these can stay in `configure(**kwargs)`).

---

### `manga_ai_studio/core/box_model.py` (MOD — model, CRUD)

**Analog:** the EXISTING `PageBox` dataclass + the D-15 seam pattern (`box_model.py:52-81`). Phase 4 adds fields via the SAME composition discipline (D-14 anti-pattern: layer on `PageBox`, do NOT touch the vendored `Box`).

**Existing field pattern** (`box_model.py:76-80`) — copy the shape for new fields:
```python
@dataclass
class PageBox:
    box: Box
    origin: str
    payload: Optional[object] = None
    mask: Optional[object] = None       # D-15 seam (DEFERRED — later phase)
    std_dev: Optional[float] = None     # D-15 seam (DEFERRED)
```
**Add (RESEARCH §Recommended Project Structure, RESEARCH Open Question 2 + 6):**
```python
    edited: bool = False                              # D-04 re-OCR gate (peer field, NOT derived)
    bubble_no: Optional[int] = None                   # D-15/D-16 reading-order number
    manual_override: bool = False                     # D-16 — sticks on page-level re-auto

    def set_translation(self, text: str) -> None:     # D-13 — the MT seam (TRAN-01 v2 calls this)
        ...

    def set_recognized_text(self, text: str) -> None: # RESEARCH Open Q 6 — store str on payload.text
        ...                                            # sets edited=False (OCR write resets the flag)
```
**`edited` flag home** (RESEARCH Open Question 2, RECOMMENDED on PageBox): a peer `bool`, NOT derived-from-diff (fragile if OCR reproduces an edit), NOT on payload (mixes concerns). Set `True` by inline-editor/Inspector commit, `False` by OCR write.

**`payload.text` storage** (RESEARCH Open Question 6, RECOMMENDED str via setter): `TextBlock.text` defaults to `[]` and `get_text()` joins it (textblock.py:65, 203-206). Store a STR via `set_recognized_text(str)` for unambiguous editor semantics; convert to list at Phase 5 export if needed.

**`set_translation` body:** writes `self.payload.translation = text` (the TextBlock slot — textblock.py:68). If `payload is None` (user box pre-OCR), create a `TextBlock` first (the Phase 3 contract: user boxes carry `payload=None` until OCR — `box_model.py:63`, `_commit_create` canvas.py:1505).

---

### `manga_ai_studio/gui/box_item.py` (MOD — component, render + interaction)

**Analog:** the EXISTING `BoxItem` + `CornerHandle` in the SAME file (`box_item.py:126-372`). Phase 4 adds THREE child items (text overlay, bubble badge, inline-editor-entry hook) + the vertical flag, all mirroring the `CornerHandle` child-item pattern.

**Child-item construction pattern** (`box_item.py:142-162`, `BoxItem.__init__` at 271-273):
```python
self.handles: dict[str, CornerHandle] = {
    c: CornerHandle(c, self) for c in ("TL", "TR", "BL", "BR")
}
```
Add the text overlay + bubble badge as children in `BoxItem.__init__` (same `parent=self` pattern). Z-order: overlay z=120, badge z=140 (RESEARCH Pitfall 7, UI-SPEC §Z-order); both below handles z=150 (`_HANDLE_Z`).

**`ItemIgnoresTransformations` + constant viewport-px pattern** (`box_item.py:145-150`) — copy for the bubble badge (constant viewport-px number, like the 8x8 handle):
```python
self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
self.setZValue(_BADGE_Z)  # = 140
```

**Outlined-text overlay pattern** (RESEARCH §Pattern 3, lines 323-347) — the single-API `QTextCharFormat.setTextOutline(QPen)` on a `QGraphicsTextItem`:
```python
fmt = QTextCharFormat()
fmt.setFont(font)
outline_pen = QPen(QColor.fromRgbF(11/255, 11/255, 14/255, 0.92), 2)  # 2px dark matte
fmt.setTextOutline(outline_pen)
fmt.setForeground(QBrush(QColor.fromRgbF(232/255, 232/255, 234/255, 0.85)))  # translucent fill
cursor = QTextCursor(doc); cursor.insertText(text, fmt)
```
Render the "current focus" text (D-10: translation if present, else recognized). Keep the document PLAIN text (ASVS V5 — no `setHtml` on OCR output).

**Selection-sync pattern** (`box_item.py:312-352` `itemChange`/`_apply_look_for`/`_sync_handles_for_state`) — extend `_sync_handles` (297-310) to also reposition the badge + refresh the overlay on selection/geometry change. Mirror the `_apply_look_for(selected)` shape.

**Double-click entry hook:** `BoxItem` does NOT override `mouseDoubleClickEvent` today (confirmed — grep found none in canvas.py). The canvas owns event dispatch (see `canvas.py` assignment); `BoxItem` exposes an `enter_edit_mode()` / `exit_edit_mode()` method the canvas calls. Do NOT add `ItemIsMovable` confusion (existing comment box_item.py:244-251).

**`current_box()` materialization** (`box_item.py:355-372`) — UNCHANGED; the snapshot path still reads `rect()` → `Box(int(...))`.

---

### `manga_ai_studio/gui/canvas.py` (MOD — component/controller, request-response + event-driven)

**Analog:** the EXISTING methods in the SAME file. Four distinct hooks, each with its own analog.

**Hook 1 — auto-OCR on `_commit_create`** (`canvas.py:1487-1517`). Append the OCR call after the empty-user-box commit. The existing `_commit_create` builds `PageBox(payload=None)` (1502-1506) and emits `boxes_modified` (1517). Phase 4: after `item.setSelected(True)` (1513), trigger OCR (emit a new `ocr_requested.emit(item)` signal OR call a MainWindow-injected callback — RESEARCH §Pattern 2 routes the actual model call through MainWindow's Worker). DO NOT run manga-ocr on the GUI thread (RESEARCH §Pitfall 6, T-01-07).

**Hook 2 — `boxes_snapshot()` MUST carry new fields** (`canvas.py:1276-1286`, RESEARCH §Pitfall 1 — LOAD-BEARING). Current code DROPS the new fields:
```python
# CURRENT (drops edited/bubble_no/manual_override):
snapshots.append(PageBox(box=fresh_box, origin=item.pagebox.origin, payload=item.pagebox.payload))
```
**Replace with** (RESEARCH §Pitfall 1, lines 429-437):
```python
snapshots.append(PageBox(
    box=fresh_box,
    origin=item.pagebox.origin,
    payload=item.pagebox.payload,                  # TextBlock — carries .text/.translation
    edited=item.pagebox.edited,                    # NEW
    bubble_no=item.pagebox.bubble_no,              # NEW
    manual_override=item.pagebox.manual_override,  # NEW
))
```
**ALSO address Pitfall 8** (payload aliasing): `payload=item.pagebox.payload` passes the SAME TextBlock object by reference. If a text edit mutates `payload.text` in place, undo restores the CURRENT text. Fix: on every text/translation commit, REPLACE `pagebox.payload` with a shallow-copied TextBlock carrying the new text (RESEARCH §Pitfall 8 option (a) — cleanest, matches the "fresh materialization at boundaries" discipline). Regression tests: `test_boxes_snapshot_carries_phase4_fields`, `test_text_edit_undo_restores_previous_text`.

**Hook 3 — double-click → edit-mode dispatch.** Add `mouseDoubleClickEvent` (NONE exists today — confirmed). Pattern: mirror the existing `mousePressEvent` hit-test (`_box_item_at` at canvas.py:1337-1359) — on double-click over a `BoxItem`, call `item.enter_edit_mode()` (see `box_item.py` assignment). The inline-editor-active guard (RESEARCH §Pitfall 3) goes at the TOP of `mousePressEvent` (836): "if inline editor active and click outside it → commit + consume."

**Hook 4 — Toggle Text Overlay** (D-12). Mirror the EXISTING `toggle_mask_overlay` (canvas.py:418-419) + `set_box_overlay_visible` patterns (the box-overlay toggle referenced at main_window.py:1739-1747). Three independent visibility layers; the text-overlay toggle flips a per-item child visibility (the overlay child from `box_item.py`), independent of `mask_item.isVisible()` and `_box_overlay_visible`. Keybinding distinct from `M`/`Shift+M` (RESEARCH Claude's Discretion — `T` recommended, UI-SPEC §Surface).

**Layer/z-order anchors** (canvas.py:166-188): `mask_item` (166), `preview_item` z=900 (180), box items z=100 (264 in box_item.py). Text overlay z=120 / badge z=140 sit between box border (100) and preview (900) — consistent with the existing stack.

---

### `manga_ai_studio/gui/main_window.py` (MOD — controller, request-response async dispatch)

**Analog:** the EXISTING `detect_text` + `_run_detection_task` + `_resolve_detection_model_path` + `_on_detection_finished` + `_on_detection_error` + `_on_detection_cleanup` cluster (`main_window.py:1404-1770`). This is the EXACT template for `_run_ocr_task` / `_run_ocr_all_task` / `_resolve_ocr_model_path` (RESEARCH §Pattern 2).

**Dispatcher pattern** (`main_window.py:1404-1445`):
```python
def detect_text(self) -> None:
    if self._op_running:           # ← the gate (reuse verbatim)
        return
    path = self.file_table.current_path()
    if path is None:
        return
    if self.canvas.has_mask() and not self._confirm_replace_mask():   # ← confirm gate (D-04 mirrors this)
        return
    model = backend_factory("detection", self._detection_backend())  # ← swap "detection"→"ocr"
    worker = Worker(self._run_detection_task, path, model)
    worker.signals.progress.connect(self._on_detection_progress)
    worker.signals.result.connect(self._on_detection_finished)
    worker.signals.error.connect(self._on_detection_error)
    worker.signals.finished.connect(self._on_detection_cleanup)
    worker.setAutoDelete(True)
    self._op_running = True
    self._refresh_action_states()
    self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0); self.progress_bar.show()
    self.status_bar_left.setText("Detecting text… 0%")
    QThreadPool.globalInstance().start(worker)
```
`run_ocr_selected` / `run_ocr_all` copy this block; the D-04 confirm gate (`_confirm_reocr` — mirror `_confirm_replace_boxes` at 1711) replaces the `_confirm_replace_mask` gate, firing when `box.edited is True`.

**Worker-task pattern** (`main_window.py:1447-1499`):
```python
def _run_detection_task(self, image_path, model, progress_callback=None, abort_flag=None) -> dict:
    import cv2, numpy as np   # lazy
    image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    ...
    model_path = self._resolve_detection_model_path()
    model.load(model_path, device="auto")
    mask_refined, blk_list = model.detect(image)
    return {"mask": mask_refined, "blocks": blk_list}
```
`_run_ocr_task` mirrors this: crop the region by `box_xyxy` (`region = image[y1:y2, x1:x2].copy()` — Pitfall 2 clean copy), `model.recognize(region)` → `{"text": str}`. `_run_ocr_all_task` loops over the page's text-empty boxes (D-03), one model load, sequential per-box, status-bar progress (Phase 2 D-10 pattern).

**Model-path resolution pattern** (`main_window.py:1501-1555`, the CR-11 cache-check):
```python
def _resolve_detection_model_path(self) -> Path:
    config = self.profile_manager.config
    configured = profile.text_detector.model_path
    if configured:
        return Path(configured)
    cache_dir = config.get_model_cache_dir()
    expected = cache_dir / "comictextdetector.pt"
    if expected.is_file():      # CR-11: short-circuit — do NOT re-download
        return expected
    ...
```
`_resolve_ocr_model_path` mirrors this but delegates to the vendored `get_ocr_model_directory()` / `is_ocr_downloaded()` (`panelcleaner/model_downloader.py:251-268`, already vendored — confirmed). RESEARCH §Code Examples (lines 618-634) gives the exact body. The cache dir is `HF_HUB_CACHE/models--kha-white--manga-ocr-base/` (`model_downloader.py:20` `OCR_DIR_NAME`).

**Result-handler pattern** (`main_window.py:1566-1592` `_on_detection_finished`): mutate Qt only here (T-01-07). For OCR: write `box.set_recognized_text(result["text"])` (sets `edited=False`), refresh the `BoxItem` overlay, push a BOXES snapshot, clear `_op_running`. The first-run ~450MB download shows "Loading OCR model…" indeterminate progress BEFORE the worker starts (RESEARCH §Pitfall 6 — mirror Phase 1 model-load UX).

**Error UX pattern** (`main_window.py:1749-1764` `_on_detection_error`): full traceback to `logger.error(...)`, friendly copy in `QMessageBox.critical(...)` + persistent `#7a1f1f` error chip. Copy verbatim for `_on_ocr_error`.

**Menu pattern** (`main_window.py:224-230` `_build_menus` + `_build_*_menu`): add `_build_text_menu()` between View and Tools (RESEARCH Open Question 5). Each action follows the `action_detect_text` shape (`main_window.py:609`: `page_open and not self._op_running`). Actions: "Run OCR", "OCR All Boxes on Page (Ctrl+R)", "Auto-Number RTL (Manga)", "Auto-Number LTR (Manhwa)", "Load Translations…".

**Dock instantiation** (`main_window.py:200-221` `_build_docks`) — see `inspector_panel.py` assignment. Add the Inspector dock here.

---

### `manga_ai_studio/core/history_manager.py` (MOD — model / undo stack, event-driven)

**Analog:** the EXISTING `_materialize_snapshot` (`history_manager.py:252-275`) + `push_boxes_state` (277-302) + `pop_boxes_undo`/`pop_boxes_redo` (304-341). The BOXES stack is generic over the snapshot shape (D-10 — "BOXES is ONE logical stack; op-type lives in record metadata"). Phase 4's richer `PageBox` (with `edited`/`bubble_no`/`manual_override` + mutated `payload.text`/`.translation`) rides the SAME stack — NO new stack.

**`_materialize_snapshot` shape-agnosticism** (`history_manager.py:261-275`):
```python
# Shape-agnostic: items may be tuples of any arity (the BOXES stack is
# generic over the snapshot shape — D-10). Non-tuple items (e.g. bare
# Box) are copied if mutable, else shared (the vendored Box is @frozen).
for item in boxes:
    if isinstance(item, tuple):
        snap.append(tuple(m.copy() if hasattr(m, "copy") else m for m in item))
    else:
        snap.append(item.copy() if hasattr(item, "copy") else item)
```
**Phase 4 items are `PageBox` dataclass instances (NOT tuples)** — the `else` branch applies. `PageBox` has NO `.copy()` method (it's a plain `@dataclass`), so `_materialize_snapshot` will SHARE the reference (`item.copy() if hasattr(item, "copy") else item` → returns `item` itself). This is the Pitfall 8 aliasing vector at the HISTORY layer.

**Fix options (RESEARCH §Pitfall 8):**
- (a) Add a `.copy()` to `PageBox` (via `@dataclass` + `copy.deepcopy`, or `dataclasses.replace`) that deep-copies `payload` (TextBlock) — then `_materialize_snapshot`'s `hasattr(m, "copy")` branch detaches correctly. This is the lowest-friction fix and makes the existing `_materialize_snapshot` work unmodified.
- (b) OR: have `canvas.boxes_snapshot()` construct fresh `PageBox` instances with fresh `payload` (shallow-copied TextBlock) — the snapshot boundary already rebuilds `PageBox` (canvas.py:1280), so replacing `payload=item.pagebox.payload` with a copied TextBlock fixes both Pitfall 1 and Pitfall 8 at the canvas boundary.

**Recommended:** option (a) — add `PageBox.copy()` returning `dataclasses.replace(self, payload=copy.copy(self.payload))` so the history-layer detachment is robust regardless of caller. Verify with `test_boxes_snapshot_is_detached` (existing, history_manager.py:41) + the new `test_text_edit_undo_restores_previous_text`.

**No new push/pop methods** — `push_boxes_state` / `pop_boxes_undo` / `pop_boxes_redo` are unchanged; the richer payload flows through them transparently (D-10).

---

### `manga_ai_studio/core/image_file.py` (MOD — model / per-page slot, file-I/O)

**Analog:** the EXISTING `boxes` slot (`image_file.py:75`) + the `mask` slot (74) — the Phase 2 D-11 per-page persistence seam. Phase 4 text/translation/bubble-no ride INSIDE `boxes` (on the `PageBox.payload` + the new `PageBox` fields), so NO new slot is needed.

**Existing slot pattern** (`image_file.py:72-76`):
```python
path: Path
thumbnail: QPixmap | None = None
mask: QImage | None = None
boxes: list["PageBox"] | None = None    # ← text/translation ride inside here
dirty: bool = False
```
**Verify-only task** (RESEARCH §Pitfall 1 + CONTEXT §Integration Points): the page-switch round-trip is `ImageFile.boxes = canvas.boxes_snapshot()` (main_window.py:788, per CONTEXT canonical_refs) on page-leave and `canvas.set_boxes(image_file.boxes)` (canvas.py:1183) on page-enter. Since Phase 4 fields are on `PageBox` (carried by the snapshot — IF Hook 2 above is applied), they round-trip automatically. Regression test: `test_text_persists_across_page_switch` (extend `tests/test_box_persistence.py`).

**`has_boxes()` pattern** (`image_file.py:118-131`) — the existing content check; a `has_text()`/`has_translations()` helper MAY be added if the MainWindow status bar wants text/translation counts (CONTEXT mentions `box_origin_counts()` extending to text counts — main_window.py:1302 + canvas.py:1252). Mirror the trivial `bool(self.boxes)` shape.

**`.copy()` discipline** (RESEARCH Pitfall 2): text/translation are immutable Python `str` (safe to share); `bubble_no` is `Optional[int]` (immutable); `payload` (TextBlock) is the ONE mutable that needs detachment — handled by the `PageBox.copy()` fix in the `history_manager.py` assignment (the same fix covers the persistence boundary, since `ImageFile.boxes = canvas.boxes_snapshot()` reuses the snapshot path).

---

## Shared Patterns

### Async model dispatch (Worker + QThreadPool + _op_running gate)
**Source:** `gui/main_window.py:1404-1445` (`detect_text`) + `gui/worker_thread.py:86-175` (`Worker`)
**Apply to:** `_run_ocr_task` (single-box OCR), `_run_ocr_all_task` (page-loop OCR), and any future heavy model call.
```python
if self._op_running: return
model = backend_factory("ocr", self._ocr_backend())
worker = Worker(self._run_ocr_task, path, box_xyxy, model)
worker.signals.progress.connect(self._on_ocr_progress)
worker.signals.result.connect(self._on_ocr_finished)
worker.signals.error.connect(self._on_ocr_error)
worker.signals.finished.connect(self._on_ocr_cleanup)
self._op_running = True
QThreadPool.globalInstance().start(worker)
```
manga-ocr is a heavy model call (first-run ~450MB download + per-call inference) — MUST run off the GUI thread (RESEARCH §Pitfall 6, T-01-07). One model load per session (singleton — the vendored `MangaOcr` is load-once; RESEARCH §Anti-Patterns line 391).

### Confirm-gate before destructive replace
**Source:** `gui/main_window.py:1711-1737` (`_confirm_replace_boxes`) + `1772-1792` (`_confirm_replace_mask`)
**Apply to:** D-04 re-OCR confirm (`_confirm_reocr` — fires when `box.edited is True`), page-level re-auto-number conflict (D-16, RESEARCH Open Q 3 — preserve manual overrides).
```python
box = QMessageBox(self)
box.setIcon(QMessageBox.Icon.Question)
box.setWindowTitle("...")
box.setText("...")
cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
replace_btn = box.addButton("Replace ...", QMessageBox.ButtonRole.AcceptRole)
box.setDefaultButton(replace_btn); box.exec()
return box.clickedButton() is replace_btn
```
Silent overwrite when `box.edited is False` mirrors Phase 3 D-03/D-12 (RESEARCH §Pitfall 4).

### BOXES-snapshot push (single source of truth for undo)
**Source:** `gui/canvas.py:1517` (`_commit_create`), `1533` (`_remove_box`), `1204` (`set_boxes`); `core/history_manager.py:277` (`push_boxes_state`)
**Apply to:** every text/translation/bubble-number commit (inline editor, Inspector, parser apply, auto-number) pushes ONE BOXES snapshot via `canvas.boxes_modified.emit(self.boxes_snapshot())`.
```python
# CR-01 fix: capture BEFORE the mutation; emit the PRE-state for undo.
before = self.boxes_snapshot()
# ... mutate pagebox / boxes ...
self.boxes_modified.emit(before)   # or emit current-state per the existing convention
```
Parser apply = ONE batch entry (RESEARCH Open Question 4), not one-per-box.

### numpy→PIL round-trip at the adapter boundary
**Source:** `adapters/torch_impl.py:245-246` (`TorchLamaModel.inpaint`)
**Apply to:** `TorchOCRModel.recognize` (the ONLY new adapter method).
```python
pil_image = Image.fromarray(image, mode="RGB")
return self.model(pil_image)   # manga-ocr accepts PIL.Image, NOT numpy (Pitfall 2)
```
The region passed IN (cropped from the page numpy) must be a clean `.copy()` if held (Pitfall 2); the recognized str is immutable and safe.

### Model-path resolution with cache-check (CR-11)
**Source:** `gui/main_window.py:1501-1555` (`_resolve_detection_model_path`); `panelcleaner/model_downloader.py:251-268` (`get_ocr_model_directory`/`is_ocr_downloaded`)
**Apply to:** `_resolve_ocr_model_path`.
```python
cache_dir = ...                       # HF_HUB_CACHE
expected = cache_dir / "models--kha-white--manga-ocr-base"
if is_ocr_downloaded():               # CR-11: short-circuit — do NOT re-download ~450MB
    return get_ocr_model_directory()
# First run: the MangaOcr singleton's initialize_model() does the actual fetch
# (inside the Worker, off the GUI thread — Pitfall 6).
```
Programming errors (`TypeError`/`AttributeError`/`ValueError`) PROPAGATE (CR-01); filesystem/network errors (`FileNotFoundError`/`OSError`) log + fall back (T-01-08).

### Error UX (traceback to loguru, friendly copy in dialog)
**Source:** `gui/main_window.py:1749-1764` (`_on_detection_error`)
**Apply to:** `_on_ocr_error` (model load / inference failure), Load-Translations file-read error, parser report.
```python
logger.error(f"OCR failed: {worker_error}")     # full traceback → loguru (T-01-08)
self.error_chip.setText("OCR model error"); self.error_chip.show()
QMessageBox.critical(self, "Couldn't load the OCR model.",
    "Check that the model is present ... see the log for details.")
```
Parser errors are REPORTED (counts in a dialog), never raised (ASVS V5/V7).

### Pure-stdlib headless-testable core module
**Source:** `core/box_model.py:38-49` (module header) + `tests/test_core/test_box_model.py:1-55` (test shape)
**Apply to:** `core/translation_parser.py`, `core/reading_order.py` (both NEW pure-Python modules).
```python
from __future__ import annotations
from dataclasses import dataclass
# NO Qt imports. Headless-testable (pytest -m unit, no display needed).
```
Tests: `@pytest.mark.unit`, lazy `from manga_ai_studio.core.X import Y` inside the test fn (matches `test_box_model.py:35`), duck-typed fakes (no real model/Qt).

## No Analog Found

| File | Role | Data Flow | Reason | Fallback |
|------|------|-----------|--------|----------|
| `QGraphicsProxyWidget(QTextEdit)` inline editor (within `gui/inline_editor.py` or `box_item.py`) | component / overlay | request-response | First proxy widget in the project; no existing `QGraphicsProxyWidget` usage. Focus/IME handling has documented quirks (RESEARCH §Pitfall 3). | RESEARCH §Pattern 3 + UI-SPEC §15 (locks the proxy choice); `CornerHandle` (`box_item.py:126-230`) for the child-item/z-order pattern. Test IME at the end-of-phase human gate. |
| Vertical-text editing (D-06 toggle) | component / overlay | n/a | Qt's rich-text engine does NOT implement CSS `writing-mode: vertical-rl`; no codebase analog AND no clean Qt path (RESEARCH §Pitfall 5). | Ship the UI-SPEC fallback: horizontal editor always; `payload.vertical` preserved as export metadata; the per-box vertical toggle is a v1 no-op with a "coming soon" tooltip. Do NOT hand-roll vertical CJK layout in Phase 4. |
| Translation-parser format | utility / parser | transform | PanelCleaner's `parsers.py` handles a DIFFERENT format (CSV with file-path headers) and is NOT reusable (RESEARCH §Don't Hand-Roll line 404). | RESEARCH §Code Examples (lines 570-614) gives the exact regex + matcher contract. The format is simple and line-oriented. |

## Metadata

**Analog search scope:**
- `manga_ai_studio/adapters/` (base.py, factory.py, torch_impl.py, onnx_impl.py)
- `manga_ai_studio/core/` (box_model.py, history_manager.py, image_file.py, mask_editor.py, batch_runner.py)
- `manga_ai_studio/gui/` (canvas.py, box_item.py, main_window.py, tools_panel.py, file_table.py, worker_thread.py)
- `panelcleaner/` (vendored: model_downloader.py, ocr/supported_languages.py, comic_text_detector/utils/textblock.py)
- `../PanelCleaner/pcleaner/ocr/` (upstream vendor reference: ocr_mangaocr.py, ocr.py, parsers.py)
- `tests/test_core/` (test_adapters.py, test_box_model.py, test_history_boxes.py — test-shape analogs)

**Files scanned:** 18 source files + 4 upstream vendor refs + 3 test files
**Pattern extraction date:** 2026-08-05
**Key verified facts (load-bearing for the planner):**
- `OCRModel` ABC ALREADY exists (`base.py:71-96`) with `recognize(image: np.ndarray) → str` — signature matches; likely NO base.py edit.
- `backend_factory("ocr")` stub at `factory.py:50-51` — replace with the `TorchOCRModel` resolution (mirror the detection block at 37-43).
- `boxes_snapshot()` at `canvas.py:1276-1286` DROPS the new fields — MUST extend (Pitfall 1, load-bearing).
- `_materialize_snapshot` at `history_manager.py:261-275` shares non-tuple items without `.copy()` — `PageBox` needs a `.copy()` (Pitfall 8, load-bearing).
- Vendored `panelcleaner/model_downloader.py:251-268` (`get_ocr_model_directory`/`is_ocr_downloaded`) ALREADY exists — `_resolve_ocr_model_path` delegates to it (no new download logic).
- Vendored `panelcleaner/ocr/supported_languages.py` ALREADY exists — `ocr_mangaocr.py` vendors next to it.
- No `mouseDoubleClickEvent` exists in `canvas.py` — Phase 4 adds it.
- No `QGraphicsProxyWidget` usage anywhere in the codebase — first-of-its-kind (lean on RESEARCH §Pattern 3 + UI-SPEC §15).

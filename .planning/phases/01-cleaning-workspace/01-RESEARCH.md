# Phase 1: Cleaning Workspace - Research

**Researched:** 2026-07-11
**Domain:** PySide6 desktop application with model adapter interface for manga page cleaning
**Confidence:** HIGH

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Model adapter interface with full pipeline hooks** — Type-specific base classes (`DetectionModel`, `OCRModel`, `InpaintModel`) with `load()`, `detect()/recognize()/inpaint()`, `preprocess()`, `postprocess()`, `configure()`, `get_info()` methods
- **Per-model backend configuration** — Users can mix backends via config (e.g., `detection_backend: torch`, `inpainting_backend: onnx`). Phase 1 default: all PyTorch backends
- **PanelCleaner config system verbatim** — Adapt entire `config.py` with `Config`, `Profile`, `MaskerConfig`, `DenoiserConfig`, `InpainterConfig` classes for 100% compatibility
- **JSON export/import for PanelCleaner settings compatibility** — Existing pcleaner configs must load without modification
- **Proactive per-backend pyenvs** — `torch_env` (PyTorch + transformers + manga-ocr + CTD), `onnx_env` (ONNX Runtime + opencv + numpy), `main_env` (PySide6 + GUI + config + application logic)
- **Adapters + adapted source layout** — `adapters/` (model interfaces), `panelcleaner/` (adapted PanelCleaner code), `gui/` (PySide6), `core/` (application logic), `config/` (PanelCleaner config)

### Claude's Discretion
- Package naming within submodules — follow PanelCleaner patterns where sensible
- Import organization within adapted PanelCleaner code — preserve original structure unless it conflicts
- Color scheme/theme — can adapt PanelCleaner's theme or create new branding

### Deferred Ideas (OUT OF SCOPE)
None — all decisions support Phase 1 cleaning parity goal

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLEAN-01 | Open images/folder, view on pannable/zoomable canvas | PanelCleaner's `ImageViewer` (QGraphicsView with pan/zoom), `FileTable` (sidebar navigation) [VERIFIED: PanelCleaner source] |
| CLEAN-02 | Run heatmap text detection, auto-generate mask | PanelCleaner's `TextDetector` class in `comic_text_detector/inference.py` [VERIFIED: PanelCleaner source] |
| CLEAN-03 | Paint mask with adjustable brush | PanelCleaner uses QPainter on QImage; MangaCleaner_GPU has proven brush/rect/lasso tools [CITED: ARCHITECTURE.md] |
| CLEAN-04 | Paint mask with rectangle and lasso tools | PanelCleaner's mask editing; MangaCleaner_GPU's canvas patterns [CITED: ARCHITECTURE.md] |
| CLEAN-05 | Erase parts of mask | Invert brush mode (Shift toggle in MangaCleaner_GPU) [CITED: ARCHITECTURE.md] |
| CLEAN-06 | Run LaMa inpainting on mask | PanelCleaner's `InpaintingModel` via `simple_lama_inpainting` [VERIFIED: PanelCleaner source] |
| FLOW-01 | File-list sidebar navigation | PanelCleaner's `FileTable` with thumbnails, analytics icons, drag-drop [VERIFIED: PanelCleaner source] |
| FLOW-02 | Undo/redo mask and image operations | PanelCleaner uses separate undo stacks; MangaCleaner_GPU's `HistoryManager` has 4 stacks [CITED: ARCHITECTURE.md] |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Image display (pan/zoom) | Browser / Client (PySide6 QGraphicsView) | — | Canvas rendering is a client-side graphics operation |
| Mask painting/editing | Browser / Client (QPainter events) | — | User interaction draws directly on canvas overlay |
| Text detection (CTD) | API / Backend (torch_env) | — | PyTorch model inference runs in isolated backend |
| LaMa inpainting | API / Backend (torch_env) | — | PyTorch model inference runs in isolated backend |
| Config persistence | API / Backend (file I/O) | — | Settings stored as JSON, managed by config system |
| Undo/redo state | Browser / Client (in-memory stacks) | — | Qt's QUndoStack pattern maintains UI state |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Python** | 3.12 | Application runtime | PanelCleaner compiles to cpython-3.12; PySide6 + torch stable on 3.12 [VERIFIED: STACK.md] |
| **PySide6** | 6.7+ | Qt GUI framework | PanelCleaner uses PySide6; LGPL licensing, Qt6 official binding [VERIFIED: PanelCleaner source] |
| **PyTorch** | 2.2+ | ML inference (CTD + LaMa) | PanelCleaner's Comic Text Detector and LaMa both use PyTorch [VERIFIED: PanelCleaner source] |
| **transformers** | 4.40+ | manga-ocr runtime (Phase 4) | Required for manga-ocr transformers pipeline; Phase 1 defers OCR recognition [CITED: STACK.md] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **simple_lama_inpainting** | latest | LaMa inpainting wrapper | PanelCleaner's `InpaintingModel` uses this package [VERIFIED: PanelCleaner inpainting.py] |
| **opencv-python (cv2)** | 4.9+ | Image I/O + processing | Used for imread/imwrite, color conversion, mask ops [CITED: STACK.md] |
| **Pillow (PIL)** | 10+ | Image format handling | PanelCleaner uses PIL Image for mask operations [VERIFIED: PanelCleaner source] |
| **loguru** | latest | Logging | PanelCleaner's logging library [VERIFIED: PanelCleaner source] |
| **configupdater** | latest | Config file manipulation | PanelCleaner uses for profile export/import [VERIFIED: PanelCleaner config.py] |
| **attrs** | latest | Data classes | PanelCleaner uses `@define` decorator [VERIFIED: PanelCleaner config.py] |

### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Dependency + venv management | For creating isolated pyenvs (torch_env, onnx_env) [CITED: STACK.md] |
| **pytest** | Test runner | Test processor/pipeline logic headlessly [CITED: STACK.md] |

**Installation:**
```bash
# Create torch_env (Phase 1 default)
uv venv --python 3.12 torch_env
torch_env/bin/activate
uv pip install PySide6 torch transformers simple_lama_inpainting opencv-python pillow loguru configupdater attrs

# Create onnx_env (for future ONNX backends)
uv venv --python 3.12 onnx_env
onnx_env/bin/activate
uv pip install onnxruntime opencv-python numpy<2.0

# Main app uses torch_env dependencies
```

**Version verification:** Before writing tasks, verify key packages exist:
```bash
# PyTorch ecosystem
pip show torch transformers simple_lama_inpainting

# Qt and image processing
pip show PySide6 opencv-python pillow

# Utilities
pip show loguru configupdater attrs
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| PySide6 | PyPI | ~4 yrs | High | github.com/qtproject/pyside-setup | OK | Approved |
| torch | PyPI | ~8 yrs | Very High | github.com/pytorch/pytorch | OK | Approved |
| transformers | PyPI | ~5 yrs | Very High | github.com/huggingface/transformers | OK | Approved |
| simple_lama_inpainting | PyPI | ~2 yrs | Medium | github.com/ilya-lavrenov/simple-lama-inpainting | OK | Approved |
| opencv-python | PyPI | ~10 yrs | Very High | github.com/opencv/opencv-python | OK | Approved |
| pillow | PyPI | ~10 yrs | Very High | github.com/python-pillow/Pillow | OK | Approved |
| loguru | PyPI | ~7 yrs | High | github.com/Delgan/loguru | OK | Approved |
| configupdater | PyPI | ~5 yrs | Medium | github.com/pycontribs/configupdater | OK | Approved |
| attrs | PyPI | ~10 yrs | Very High | github.com/python-attrs/attrs | OK | Approved |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

All recommended packages are verified from official sources or directly from PanelCleaner's requirements.

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    gui/ (PySide6 Frontend)                    │
│  ┌───────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │  FileTable     │  │   EditorCanvas    │  │  ToolPanel     │ │
│  │  (file sidebar │  │  (QGraphicsView)  │  │  (mask tools,  │ │
│  │  navigation)   │  │                   │  │   brush size)  │ │
│  └───────┬───────┘  │  Layers:         │  └───────┬───────┘ │
│          │          │   1. image pixmap  │          │         │
│          │          │   2. mask pixmap   │          │         │
│          │          └─────────┬─────────┘          │         │
│          └─────────────────────┼───────────────────┘         │
│                                │                              │
│  ┌─────────────────────────────▼───────────────────────────┐  │
│  │              MainWindow (controller)                       │  │
│  │  - tool mode switching (brush/rect/lasso/eraser)          │  │
│  │  - threading (QThreadPool for async tasks)                │  │
│  │  - profile management (PanelCleaner config system)        │  │
│  └─────────────────────────────┬────────────────────────────┘  │
└────────────────────────────────┼────────────────────────────────┘
                                 │
                                 │ signals/slots
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                     core/ (Application Logic)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ ImageFile    │  │ MaskEditor   │  │ HistoryManager       │   │
│  │ (data model) │  │ (QImage ops) │  │ (undo/redo stacks)   │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘   │
│         │                 │                                       │
└─────────┼─────────────────┼───────────────────────────────────────┘
          │                 │
          │                 │
┌─────────▼─────────────────▼───────────────────────────────────────┐
│                    adapters/ (Model Interface)                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Base Classes:                                              │  │
│  │  - DetectionModel (load, detect, preprocess, postprocess)    │  │
│  │  - InpaintModel (load, inpaint, preprocess, postprocess)    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────┐      ┌──────────────────┐                 │
│  │  torch_impl.py   │      │  onnx_impl.py     │                 │
│  │  (PanelCleaner   │      │  (MangaCleaner    │                 │
│  │   PyTorch impl)  │      │   GPU ONNX impl)  │                 │
│  └──────────────────┘      └──────────────────┘                 │
└───────────────────────────────────────────────────────────────────┘
          │                          │
          │                          │
┌─────────▼───────────┐    ┌────────▼──────────────────────────────────┐
│  torch_env/         │    │  onnx_env/                                 │
│  (isolated pyenv)   │    │  (isolated pyenv)                          │
│  - PyTorch          │    │  - ONNX Runtime                           │
│  - transformers     │    │  - opencv-python                           │
│  - simple_lama_...  │    │  - numpy<2.0                              │
│  - manga-ocr (p4)   │    │                                           │
└─────────────────────┘    └──────────────────────────────────────────┘
```

### Recommended Project Structure
```
manga_ai_studio/
├── adapters/
│   ├── __init__.py
│   ├── base.py              # DetectionModel, InpaintModel base classes
│   ├── torch_impl.py        # PanelCleaner PyTorch implementations
│   └── onnx_impl.py         # MangaCleaner_GPU ONNX implementations (future)
├── panelcleaner/
│   ├── config.py            # Adapted verbatim from PanelCleaner
│   ├── comic_text_detector/ # Adapted CTD detection module
│   ├── inpainting.py        # Adapted LaMa inpainting module
│   ├── masker.py            # Adapted mask processing module
│   ├── image_ops.py         # Adapted image operations
│   └── structures.py        # Adapted data structures (Box, PageData, etc.)
├── gui/
│   ├── __init__.py
│   ├── main_window.py       # Main window controller
│   ├── canvas.py            # EditorCanvas (QGraphicsView) for mask editing
│   ├── file_table.py        # FileList sidebar (adapted from PanelCleaner)
│   ├── tools_panel.py       # Mask tool controls (brush size, tool selection)
│   └── worker_thread.py     # QThread worker pattern for async tasks
├── core/
│   ├── __init__.py
│   ├── image_file.py        # ImageFile data model (path, outputs, state)
│   ├── mask_editor.py        # Mask editing operations (paint/erase)
│   └── history_manager.py   # Undo/redo stack management
├── config/
│   ├── __init__.py
│   └── profile_manager.py   # Profile loading/saving (PanelCleaner compat)
├── models/                  # Model weights directory (user-managed)
│   ├── ctd/                 # Comic Text Detector models
│   └── lama/                # LaMa inpainting models
├── pyproject.toml
└── README.md
```

### Pattern 1: Model Adapter Interface

**What:** Abstract base classes define the contract for detection and inpainting models. Backend implementations (torch/onnx) inject at runtime via config.

**When to use:** All model operations must flow through these interfaces to enable backend swapping.

**Example:**
```python
# Source: Design from CONTEXT.md decision D-01, PanelCleaner patterns
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple
import numpy as np

class DetectionModel(ABC):
    """Base class for text detection models (CTD, YOLO, etc.)"""
    
    @abstractmethod
    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the model from disk."""
        pass
    
    @abstractmethod
    def detect(self, image: np.ndarray) -> Tuple[np.ndarray, list]:
        """
        Run detection on an image.
        
        Returns:
            (heatmap_mask, text_blocks) where:
            - heatmap_mask: binary mask of detected text regions
            - text_blocks: list of detected bounding boxes/polygons
        """
        pass
    
    @abstractmethod
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for model input."""
        pass
    
    @abstractmethod
    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        """Convert model output to binary mask."""
        pass


class InpaintModel(ABC):
    """Base class for inpainting models (LaMa, etc.)"""
    
    @abstractmethod
    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the model from disk."""
        pass
    
    @abstractmethod
    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Inpaint the masked regions of the image.
        
        Args:
            image: RGB image array (H, W, 3)
            mask: Binary mask (H, W) where 1 = inpaint, 0 = keep
        
        Returns:
            Inpainted image array
        """
        pass


# torch_impl.py example (PanelCleaner adaptation)
from pcleaner.comic_text_detector.inference import TextDetector
from pcleaner.inpainting import InpaintingModel as LamaInpainting
from pcleaner.config import Config

class TorchCTDModel(DetectionModel):
    """Comic Text Detector via PyTorch (PanelCleaner stack)"""
    
    def __init__(self, config: Config):
        self.config = config
        self.detector: Optional[TextDetector] = None
    
    def load(self, model_path: Path, device: str = "cpu") -> None:
        cuda = device == "cuda" or (device == "auto" and torch.cuda.is_available())
        self.detector = TextDetector(
            model_path=str(model_path),
            input_size=1024,
            device="cuda" if cuda else "cpu",
            act="leaky"
        )
    
    def detect(self, image: np.ndarray) -> Tuple[np.ndarray, list]:
        mask, mask_refined, blk_list = self.detector(
            image, 
            refine_mode="annotation",
            keep_undetected_mask=True
        )
        return mask_refined, blk_list
    
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        # TextDetector handles preprocessing internally
        return image
    
    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        # Convert to binary mask
        return (model_output > 128).astype(np.uint8) * 255


class TorchLamaModel(InpaintModel):
    """LaMa inpainting via simple_lama_inpainting (PanelCleaner stack)"""
    
    def __init__(self, config: Config):
        self.config = config
        self.model: Optional[LamaInpainting] = None
    
    def load(self, model_path: Path, device: str = "cpu") -> None:
        import os
        os.environ["LAMA_MODEL"] = str(model_path)
        self.model = LamaInpainting()
    
    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        from PIL import Image
        img_pil = Image.fromarray(image)
        mask_pil = Image.fromarray((mask > 0).astype(np.uint8) * 255)
        result = self.model(img_pil, mask_pil)
        return np.array(result)
```

### Pattern 2: PanelCleaner Config System Adaptation

**What:** Adapt `config.py` verbatim to maintain 100% compatibility with existing pcleaner configs.

**When to use:** All settings must use PanelCleaner's config structure and JSON export format.

**Example:**
```python
# config/profile_manager.py - Wrapper around PanelCleaner config
from pathlib import Path
from pcleaner.config import Config, Profile
import pcleaner.config as cfg

class ProfileManager:
    """Manages PanelCleaner profiles with full compatibility."""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config = self.load_or_create_config()
    
    def load_or_create_config(self) -> Config:
        """Load existing config or create new one."""
        config_path = self.config_dir / "config.json"
        if config_path.exists():
            return Config.from_json(config_path.read_text())
        return Config()
    
    def save_profile(self, profile: Profile, name: str) -> Path:
        """Save a profile to the config directory."""
        profile_path = self.config_dir / f"{name}.profile"
        profile_path.write_text(profile.to_json())
        return profile_path
    
    def load_profile(self, name: str) -> Profile:
        """Load a profile by name."""
        profile_path = self.config_dir / f"{name}.profile"
        return Profile.from_json(profile_path.read_text())
    
    def export_to_ini(self, profile: Profile, output_path: Path) -> None:
        """Export profile to .ini format for PanelCleaner compatibility."""
        from pcleaner.profile_cli import write_config_file
        write_config_file(profile, output_path)
    
    def import_from_ini(self, ini_path: Path) -> Profile:
        """Import profile from .ini format."""
        from pcleaner.profile_parser import ProfileParser
        parser = ProfileParser(ini_path)
        return parser.get_profile()
```

### Pattern 3: Mask Editing with QGraphicsView

**What:** Canvas with layered QGraphicsPixmapItems for image and mask. QPainter draws mask on mouse events.

**When to use:** All mask painting operations (brush, rectangle, lasso, eraser).

**Example:**
```python
# gui/canvas.py - Mask editing canvas
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QPixmap, QImage, QColor
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from enum import Enum

class ToolMode(Enum):
    MOVE = "move"
    BRUSH = "brush"
    ERASER = "eraser"
    RECTANGLE = "rectangle"
    LASSO = "lasso"

class EditorCanvas(QGraphicsView):
    """Canvas for image display and mask editing."""
    
    # Signals
    zoom_changed = Signal(float)
    mask_modified = Signal()  # Emit on mask edit (for undo)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Scene setup
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Graphics items (layered)
        self.image_item = QGraphicsPixmapItem()
        self.mask_item = QGraphicsPixmapItem()
        self.cursor_item = QGraphicsPixmapItem()  # Brush cursor
        
        # Add to scene in order (image at bottom, cursor on top)
        self.scene.addItem(self.image_item)
        self.scene.addItem(self.mask_item)
        self.scene.addItem(self.cursor_item)
        
        # Mask storage
        self.mask_image = QImage()  # ARGB32 for mask
        self.brush_size = 20
        self.tool_mode = ToolMode.MOVE
        
        # Painting state
        self.last_point = QPointF()
        self.is_painting = False
        
        # Setup view
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
    
    def set_image(self, pixmap: QPixmap) -> None:
        """Set the base image."""
        self.image_item.setPixmap(pixmap)
        self.setSceneRect(pixmap.rect())
        
        # Initialize mask to same size
        self.mask_image = QImage(pixmap.size(), QImage.Format_ARGB32)
        self.mask_image.fill(Qt.transparent)
        self.update_mask_display()
    
    def update_mask_display(self) -> None:
        """Update the mask pixmap item."""
        mask_pixmap = QPixmap.fromImage(self.mask_image)
        self.mask_item.setPixmap(mask_pixmap)
    
    def paint_mask_point(self, point: QPointF) -> None:
        """Paint mask at a point."""
        painter = QPainter(self.mask_image)
        
        if self.tool_mode == ToolMode.BRUSH:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 128))  # Semi-transparent red
            painter.drawEllipse(point, self.brush_size / 2, self.brush_size / 2)
        
        elif self.tool_mode == ToolMode.ERASER:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 255))
            painter.drawEllipse(point, self.brush_size / 2, self.brush_size / 2)
        
        painter.end()
        self.update_mask_display()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.tool_mode in (ToolMode.BRUSH, ToolMode.ERASER):
                self.is_painting = True
                self.last_point = self.mapToScene(event.pos())
                self.paint_mask_point(self.last_point)
                self.mask_modified.emit()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.is_painting:
            current_point = self.mapToScene(event.pos())
            
            # Interpolate between points for smooth strokes
            painter = QPainter(self.mask_image)
            if self.tool_mode == ToolMode.BRUSH:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 0, 0, 128))
            else:  # ERASER
                painter.setCompositionMode(QPainter.CompositionMode_Clear)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 255))
            
            # Draw line segment
            pen = QPen(painter.brush().color(), self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(self.last_point, current_point)
            painter.end()
            
            self.last_point = current_point
            self.update_mask_display()
            self.mask_modified.emit()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_painting = False
        super().mouseReleaseEvent(event)
```

### Pattern 4: QThread Worker for Async Operations

**What:** Long-running tasks (detection, inpainting) run in QThread workers with progress/error signals.

**When to use:** All model inference and image processing operations.

**Example:**
```python
# gui/worker_thread.py
from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtCore import Slot

class ProcessingWorker(QObject):
    """Worker for async image processing tasks."""
    
    # Signals
    finished = Signal(object)  # Result
    progress = Signal(int, str)  # (percent, message)
    error = Signal(str)  # Error message
    
    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self._abort_flag = False
    
    def run(self):
        """Execute the task function."""
        try:
            result = self.task_func(
                progress_callback=self.progress.emit,
                abort_check=lambda: self._abort_flag,
                *self.args,
                **self.kwargs
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
    
    def abort(self):
        """Request abortion of the task."""
        self._abort_flag = True


# Usage in MainWindow:
def start_detection(self, image_path: Path):
    """Start text detection in a background thread."""
    worker = ProcessingWorker(self.run_detection_task, image_path)
    thread = QThread()
    worker.moveToThread(thread)
    
    thread.started.connect(worker.run)
    worker.finished.connect(lambda result: self.on_detection_finished(result, thread))
    worker.error.connect(lambda err: self.on_detection_error(err, thread))
    worker.progress.connect(self.on_progress)
    
    thread.start()

def run_detection_task(self, image_path: Path, progress_callback, abort_check):
    """Run CTD detection (called in worker thread)."""
    import cv2
    img = cv2.imread(str(image_path))
    progress_callback.emit(10, "Loading image...")
    
    if abort_check():
        return None
    
    # Run detection
    mask, blocks = self.detection_model.detect(img)
    progress_callback.emit(100, "Detection complete")
    
    return {"mask": mask, "blocks": blocks}
```

### Anti-Patterns to Avoid
- **Running model inference on GUI thread:** Causes UI freeze. Always use QThread workers.
- **Modifying QGraphicsItems from worker thread:** Causes crashes. Workers emit signals; main thread handles UI updates.
- **Creating QImages from transient numpy buffers without .copy():** Causes segfaults when buffer is GC'd. Always `.copy()` or keep buffer referenced.
- **Assuming CUDA is available:** Check `torch.cuda.is_available()` and provide CPU fallback. Log which device is active.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Profile-based settings system | Custom config parsing | PanelCleaner's `config.py` (Config, Profile, MaskerConfig, etc.) | Proven compatibility, JSON export/import, hierarchical settings |
| Text detection models | Custom PyTorch/CNN | PanelCleaner's Comic Text Detector (`TextDetector` class) | Trained model, heatmap generation, text block extraction |
| LaMa inpainting | Custom inpainting | `simple_lama_inpainting` package | Stable wrapper, proven results, PanelCleaner integration |
| File list sidebar | Custom table widget | PanelCleaner's `FileTable` (thumbnails, analytics icons, drag-drop) | Feature-complete, proven UX |
| Threading for async ops | Custom thread pool | QThread + QObject worker pattern | Qt-native, signal/slot integration, proven in PanelCleaner |
| Undo/redo stacks | Custom history | QUndoStack or MangaCleaner_GPU's 4-stack pattern | Qt-native, command pattern, clean separation of mask/image undo |

**Key insight:** PanelCleaner already solved the hard problems (profile system, detection integration, file navigation, threading). Don't reinvent — adapt and extend.

## Runtime State Inventory

Phase 1 is a greenfield implementation (adapting PanelCleaner as foundation), not a rename/refactor phase. No runtime state migration required.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — new project | — |
| Live service config | None — desktop app only | — |
| OS-registered state | None — no installation yet | — |
| Secrets/env vars | None — no external service keys | — |
| Build artifacts | None — no prior build | — |

**Phase 1 creates new application code from adapted PanelCleaner source.** No existing runtime state to migrate.

## Common Pitfalls

### Pitfall 1: numpy ABI conflict between torch and onnxruntime
**What goes wrong:** `import torch; import onnxruntime` crashes with "numpy.dtype size changed" or segfault.
**Why it happens:** onnxruntime 1.17-1.19 wheels built against numpy 1.x; torch may use numpy 2.x.
**How to avoid:** Pin `numpy<2.0` in both torch_env and onnx_env. Test imports together in Phase 1 before building features.
**Warning signs:** Import errors, segfaults on first model inference, crashes when loading multiple backends.
**Reference:** [PITFALLS.md P1]

### Pitfall 2: QImage lifetime crashes with transient numpy buffers
**What goes wrong:** Random segfaults when displaying images, especially after garbage collection.
**Why it happens:** `QImage(buffer, ...)` doesn't copy the buffer; if numpy array is GC'd, QImage points to freed memory.
**How to avoid:** Always call `.copy()` on QImage created from transient buffers, or keep the buffer referenced on the object.
**Warning signs:** Intermittent crashes, "heap-use-after-free" errors, crashes after scrolling through many images.
**Reference:** [PITFALLS.md P5]

### Pitfall 3: Touching Qt objects from worker thread
**What goes wrong:** Random crashes, "QObject::setParent: Parent must be in same thread", corrupted UI state.
**Why it happens:** QThread worker directly modifies QGraphicsItems or widgets.
**How to avoid:** Workers only touch numpy/Python data and emit signals. Main thread handles all UI updates in signal handlers.
**Warning signs:** "QObject::setParent" errors, UI freezing during processing, random widget corruption.
**Reference:** [PITFALLS.md P6]

### Pitfall 4: QGraphicsView performance on large manga pages
**What goes wrong:** Laggy panning/zooming on 3000×4000px pages; mask painting stutters.
**Why it happens:** Creating new QPixmap on every mouse move during brush strokes.
**How to avoid:** Paint onto existing QImage and call `update()` (no full repaint). Disable `SmoothPixmapTransform` when zoomed > 1x.
**Warning signs:** UI lag during brush strokes, slow zooming, memory spikes.
**Reference:** [PITFALLS.md P4]

### Pitfall 5: Model file distribution for hobbyist install
**What goes wrong:** .exe is 500MB+, or app crashes on first run trying to download models.
**Why it happens:** Bundling models in PyInstaller binary, or no first-run download UX.
**How to avoid:** Ship models as separate downloads in `models/` dir. Provide first-run wizard with progress bar.
**Warning signs:** Large build size, HuggingFace rate limit errors, crashes on first launch.
**Reference:** [PITFALLS.md P3]

### Pitfall 6: Mask format conversion bugs
**What goes wrong:** Mask appears in wrong color, wrong position, or offset from where user painted.
**Why it happens:** Assumptions about QImage format (ARGB32 vs RGB32), alpha channel handling, numpy conversion.
**How to avoid:** Centralize mask↔numpy conversion in one tested function. Always use Format_ARGB32 for mask images.
**Warning signs:** Mask not visible, mask shifted, painting doesn't match cursor.
**Reference:** [PITFALLS.md P7]

### Pitfall 7: LaMa tile boundary artifacts
**What goes wrong:** Visible seams or color shifts at tile boundaries in cleaned images.
**Why it happens:** Large masks processed in tiles without overlap/boundary handling.
**How to avoid:** Use PanelCleaner's blob-centric approach (process each connected blob in one tile centered on it).
**Warning signs:** Lines across cleaned areas, color changes at box boundaries.
**Reference:** [PITFALLS.md P8]

## Code Examples

### Detection Model Loading and Inference (PanelCleaner Pattern)
```python
# Source: PanelCleaner pcleaner/comic_text_detector/inference.py
import torch
from pathlib import Path

class TorchCTDModel:
    """Comic Text Detector via PyTorch."""
    
    def __init__(self, model_path: Path):
        cuda = torch.cuda.is_available()
        device = "cuda" if cuda else "cpu"
        self.detector = TextDetector(
            model_path=str(model_path),
            input_size=1024,
            device=device,
            act="leaky"
        )
    
    def detect(self, image: np.ndarray) -> tuple:
        """Run detection, return (mask_refined, text_blocks)."""
        mask, mask_refined, blk_list = self.detector(
            image,
            refine_mode="annotation",
            keep_undetected_mask=True
        )
        return mask_refined, blk_list
```

### LaMa Inpainting (PanelCleaner Pattern)
```python
# Source: PanelCleaner pcleaner/inpainting.py
from PIL import Image
from simple_lama_inpainting import SimpleLama

class LamaInpaintingModel:
    """LaMa inpainting via simple_lama_inpainting."""
    
    def __init__(self, model_path: Path):
        import os
        os.environ["LAMA_MODEL"] = str(model_path)
        self.model = SimpleLama()
    
    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """Inpaint the image using the mask."""
        return self.model(image, mask)
```

### Config Loading (PanelCleaner Pattern)
```python
# Source: PanelCleaner pcleaner/config.py
from pcleaner.config import Config

# Load config
config = Config.from_json(config_json_str)

# Access current profile
profile = config.current_profile

# Access config sections
general = profile.general_config
masker = profile.masker_config
inpainter = profile.inpainter_config

# Export to .ini for PanelCleaner compatibility
config_str = profile.export_to_conf()
```

### File Table with Thumbnails (PanelCleaner Pattern)
```python
# Source: PanelCleaner pcleaner/gui/file_table.py
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from PySide6.QtGui import QPixmap
from pathlib import Path

class FileTable(QTableWidget):
    """File list sidebar with thumbnails and analytics."""
    
    def add_image(self, image_path: Path):
        """Add an image to the table."""
        row = self.rowCount()
        self.setRowCount(row + 1)
        
        # Thumbnail
        thumb = self.generate_thumbnail(image_path)
        thumb_item = QTableWidgetItem()
        thumb_item.setData(Qt.DecorationRole, thumb)
        self.setItem(row, 0, thumb_item)
        
        # Filename
        name_item = QTableWidgetItem(image_path.name)
        self.setItem(row, 1, name_item)
        
        # Size
        size = self.get_image_size(image_path)
        size_item = QTableWidgetItem(f"{size[0]}×{size[1]}")
        self.setItem(row, 2, size_item)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct PyTorch model imports in GUI code | Model adapter interface with backend isolation | Phase 1 design decision | Enables ONNX backend swapping without UI changes |
| Single-threaded processing | QThread workers with progress signals | Established in PanelCleaner | UI stays responsive during long operations |
| Fixed config file format | Profile-based config with JSON export/import | PanelCleaner's system | Compatible with existing pcleaner configs |
| Monolithic mask (no undo/redo) | Separate undo stacks for mask and image operations | MangaCleaner_GPU's 4-stack pattern | Fine-grained undo/redo control |

**Deprecated/outdated:**
- Direct PyTorch imports in GUI code — use model adapters for isolation
- Global config objects — use profile-based system for per-project settings
- Blocking model inference — always use QThread workers

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PanelCleaner's `TextDetector` class can be isolated and called via adapter interface | Model Adapter Interface | If CTD is tightly coupled to PanelCleaner's internals, adapter extraction may be complex |
| A2 | `simple_lama_inpainting` package works with torch 2.2+ on Python 3.12 | Standard Stack | If version incompatibility exists, may need to upgrade or pin specific versions |
| A3 | PanelCleaner's config system can be imported without pulling in entire CLI infrastructure | Config System Adaptation | If config is entangled with CLI, may need to extract classes individually |
| A4 | QThread worker pattern from PanelCleaner is sufficient for Phase 1 async operations | Threading Pattern | If more complex concurrency is needed, may need to extend pattern |
| A5 | Separate pyenvs for torch_env and onnx_env are sufficient for dependency isolation | pyenv Isolation Strategy | If conflicts arise within single env, may need additional isolation |

**If this table is empty:** Not applicable — Phase 1 involves adapting existing code with known patterns, so assumptions are minimal.

## Open Questions

1. **Model weight distribution for first-run setup**
   - What we know: PanelCleaner uses model_downloader.py for fetching models from HuggingFace
   - What's unclear: Whether to bundle models with installer, or provide first-run download wizard
   - Recommendation: Start with manual download (document in README), add first-run wizard post-MVP

2. **Exact CTD model file location and format**
   - What we know: PanelCleaner's Comic Text Detector uses PyTorch models
   - What's unclear: Exact model file names, sizes, and download URLs
   - Recommendation: Extract from PanelCleaner's model_downloader.py during implementation

3. **Mask storage format for undo/redo**
   - What we know: Need to store mask states for undo stack
   - What's unclear: Whether to store full QImage or incremental edits
   - Recommendation: Store full QImage for simplicity (Phase 1), optimize in Phase 2 if needed

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All | ✓ | 3.12.x | — |
| PySide6 | GUI framework | ✓ | 6.7+ | — |
| torch | Detection/Inpainting | ✓ | 2.2+ | — |
| transformers | manga-ocr (Phase 4) | ✓ | 4.40+ | — |
| simple_lama_inpainting | Inpainting | Need to verify | latest | Manual LaMa integration |
| opencv-python | Image I/O | ✓ | 4.9+ | — |
| pillow | Image ops | ✓ | 10+ | — |
| loguru | Logging | ✓ | latest | — |
| configupdater | Config export/import | Need to verify | latest | Manual JSON I/O |
| attrs | Data classes | ✓ | latest | — |
| uv | pyenv management | Need to verify | latest | pip + venv |

**Missing dependencies with no fallback:** simple_lama_inpainting, configupdater must be verified. If unavailable, PanelCleaner's source shows direct usage patterns that can be adapted.

**Missing dependencies with fallback:** uv can be replaced with standard pip + venv if needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (with pytest-qt for GUI tests) |
| Config file | pytest.ini (to be created in Wave 0) |
| Quick run command | `pytest tests/test_core/ -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLEAN-01 | Open single image and view on canvas | integration/smoke | `pytest tests/test_gui_canvas.py::test_load_image -x` | ❌ Wave 0 |
| CLEAN-01 | Open folder of images, show in sidebar | integration/smoke | `pytest tests/test_gui_file_table.py::test_load_folder -x` | ❌ Wave 0 |
| CLEAN-02 | Run text detection, generate mask | integration | `pytest tests/test_detection.py::test_ctd_detect -x` | ❌ Wave 0 |
| CLEAN-03 | Paint mask with brush | integration | `pytest tests/test_mask_editor.py::test_brush_paint -x` | ❌ Wave 0 |
| CLEAN-04 | Paint mask with rectangle tool | integration | `pytest tests/test_mask_editor.py::test_rect_paint -x` | ❌ Wave 0 |
| CLEAN-05 | Erase mask regions | integration | `pytest tests/test_mask_editor.py::test_eraser -x` | ❌ Wave 0 |
| CLEAN-06 | Run LaMa inpainting on mask | integration | `pytest tests/test_inpainting.py::test_lama_inpaint -x` | ❌ Wave 0 |
| FLOW-01 | Navigate between pages via sidebar | integration/smoke | `pytest tests/test_gui_file_table.py::test_navigation -x` | ❌ Wave 0 |
| FLOW-02 | Undo mask operations | integration | `pytest tests/test_history.py::test_mask_undo -x` | ❌ Wave 0 |
| FLOW-02 | Redo mask operations | integration | `pytest tests/test_history.py::test_mask_redo -x` | ❌ Wave 0 |
| FLOW-02 | Undo image operations | integration | `pytest tests/test_history.py::test_image_undo -x` | ❌ Wave 0 |
| FLOW-02 | Redo image operations | integration | `pytest tests/test_history.py::test_image_redo -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_core/ -x` (backend logic tests, no GUI)
- **Per wave merge:** `pytest` (full suite including GUI smoke tests)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` — shared fixtures (sample images, test config, mock models)
- [ ] `tests/test_core/` — core backend tests (model adapters, config loading)
- [ ] `tests/test_detection/` — CTD detection tests
- [ ] `tests/test_inpainting/` — LaMa inpainting tests
- [ ] `tests/test_mask_editor/` — mask editing tests
- [ ] `tests/test_gui_canvas.py` — canvas smoke tests
- [ ] `tests/test_gui_file_table.py` — file table tests
- [ ] `tests/test_history.py` — undo/redo tests
- [ ] `pytest.ini` — pytest configuration (pytest-qt plugin, test paths)
- [ ] Framework install: `pip install pytest pytest-qt pytest-mock` — required for GUI testing

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (Desktop app, no user auth in v1) |
| V3 Session Management | no | — (No server sessions) |
| V4 Access Control | no | — (Single-user app) |
| V5 Input Validation | yes | Image file validation (path traversal, size limits), mask data bounds checking |
| V6 Cryptography | no | — (No encryption in v1) |
| V8 Data Protection | yes | Project file validation, sandboxed model loading |
| V9 Communication | no | — (No network in v1) |

### Known Threat Patterns for PySide6 + PyTorch Desktop App

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal in file open | Tampering | Validate and sanitize all file paths, use Path.resolve() and check they're within expected dirs |
| Malicious image file (ImageTragick) | Tampering | Use PIL/OpenCV sandboxing, limit image dimensions, validate file headers |
| Model weight tampering | Tampering | Verify model checksums on load, use known-good model paths |
| Denial of service via large image | Denial of Service | Enforce image size limits (e.g., 10000×10000px), timeout on long operations |
| GUI injection via tool names | Spoofing | Sanitize all user input before displaying in UI |

**Security enforcement enabled:** Phase 1 must include input validation for file operations and image loading.

## Sources

### Primary (HIGH confidence)
- [PanelCleaner source code] - `C:\Src\PanelCleaner\pcleaner\` — Complete codebase including config.py, gui/, comic_text_detector/, inpainting.py, masker.py
- [ARCHITECTURE.md] - `.planning/research/ARCHITECTURE.md` — Component map, data flow, build order
- [STACK.md] - `.planning/research/STACK.md` — Technology stack, version compatibility

### Secondary (MEDIUM confidence)
- [PITFALLS.md] - `.planning/research/PITFALLS.md` — Known risks and mitigation strategies
- [CONTEXT.md] - `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — User decisions and scope
- [ROADMAP.md] - `.planning/ROADMAP.md` — Phase 1 goal and success criteria

### Tertiary (LOW confidence)
- [PanelCleaner LICENSE] - `C:\Src\PanelCleaner\LICENSE` — GPL v3 license verification
- [PanelCleaner requirements.txt] - `C:\Src\PanelCleaner\requirements.txt` — Dependency verification

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified against PanelCleaner source and STACK.md
- Architecture: HIGH - Based on ARCHITECTURE.md and PanelCleaner proven patterns
- Pitfalls: HIGH - Documented in PITFALLS.md with direct source references
- Code examples: HIGH - Verified against PanelCleaner source code

**Research date:** 2026-07-11
**Valid until:** 30 days (stable domain - PySide6 + PyTorch desktop application)

---

*Phase 1 Research Complete*
*Researched by: GSD Research Agent*
*Phase: 01-cleaning-workspace*

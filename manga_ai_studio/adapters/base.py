"""Abstract base classes for model adapters (D-01).

Type-specific base classes with full pipeline hooks:

- ``DetectionModel``  -> ``load``, ``detect``, ``preprocess``, ``postprocess``, ``configure``, ``get_info``
- ``OCRModel``        -> ``load``, ``recognize``, ``preprocess``, ``postprocess``, ``configure``, ``get_info``
- ``InpaintModel``    -> ``load``, ``inpaint``, ``preprocess``, ``postprocess``, ``configure``, ``get_info``

Concrete implementations (``adapters/torch_impl.py`` for PanelCleaner PyTorch
models, ``adapters/onnx_impl.py`` for future ONNX backends) subclass these ABCs.
All model operations in the application flow through these interfaces so that
backends can be swapped via config (D-02 / D-03) without touching call sites.

Import ordering follows PanelCleaner's project convention:
stdlib -> third-party (numpy) -> ``panelcleaner.*`` / local modules.
"""

from __future__ import annotations

# stdlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple

# third-party
import numpy as np


class DetectionModel(ABC):
    """Abstract base class for text detection models (e.g. Comic Text Detector).

    A detection model produces a heatmap/binary mask of detected text regions
    plus a list of detected text blocks (bounding boxes / polygons).
    """

    @abstractmethod
    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the model from disk. Concrete implementations MUST verify model
        integrity (e.g. checksum) on load per the RESEARCH security domain."""

    @abstractmethod
    def detect(self, image: np.ndarray) -> Tuple[np.ndarray, list]:
        """Run detection on an image.

        Args:
            image: input image array.

        Returns:
            ``(heatmap_mask, text_blocks)`` where ``heatmap_mask`` is a binary
            mask of detected text regions and ``text_blocks`` is a list of
            detected bounding boxes / polygons.
        """

    @abstractmethod
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess an image for model input."""

    @abstractmethod
    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        """Convert raw model output into a binary mask."""

    @abstractmethod
    def configure(self, **kwargs) -> None:
        """Apply runtime configuration (e.g. thresholds, input size)."""

    @abstractmethod
    def get_info(self) -> dict:
        """Return model metadata (backend, device, version, etc.)."""


class OCRModel(ABC):
    """Abstract base class for OCR models (e.g. manga-ocr)."""

    @abstractmethod
    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the model from disk."""

    @abstractmethod
    def recognize(self, image: np.ndarray) -> str:
        """Recognize text in an image region, returning the recognized string."""

    @abstractmethod
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess an image for model input."""

    @abstractmethod
    def postprocess(self, model_output) -> str:
        """Convert raw model output into recognized text."""

    @abstractmethod
    def configure(self, **kwargs) -> None:
        """Apply runtime configuration."""

    @abstractmethod
    def get_info(self) -> dict:
        """Return model metadata."""


class InpaintModel(ABC):
    """Abstract base class for inpainting models (e.g. LaMa)."""

    @abstractmethod
    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the model from disk. Concrete implementations MUST verify model
        integrity (e.g. checksum) on load per the RESEARCH security domain."""

    @abstractmethod
    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Inpaint the masked regions of an image.

        Args:
            image: RGB image array (H, W, 3).
            mask: binary mask (H, W) where 1 = inpaint, 0 = keep.

        Returns:
            Inpainted image array.
        """

    @abstractmethod
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess an image for model input."""

    @abstractmethod
    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        """Convert raw model output into an image array."""

    @abstractmethod
    def configure(self, **kwargs) -> None:
        """Apply runtime configuration."""

    @abstractmethod
    def get_info(self) -> dict:
        """Return model metadata."""

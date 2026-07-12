"""ONNX Runtime backend stubs (D-03 / D-09).

These classes implement the D-01 adapter contract against the ONNX Runtime API
shape, but the ONNX backend is a **future optional add-on** (MangaCleaner_GPU
models). Phase 1 ships no concrete ONNX loader: ``load()`` raises
``NotImplementedError`` so the adapter interface stays honest for D-02 (the
``*_backend: onnx`` config keys resolve to a real class) without pulling
``onnxruntime`` into the Phase 1 dependency set.

The class bodies reference the ONNX Runtime session/provider shape documented
in PATTERNS.md §adapters/onnx_impl.py (provider auto-detection, sequential
execution mode, ``enable_mem_pattern = False``) so a future phase only needs to
replace the ``raise NotImplementedError`` lines with real ``ort`` calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np

from manga_ai_studio.adapters.base import DetectionModel, InpaintModel

_NOT_IMPLEMENTED_MSG = (
    "ONNX backend lands in a future phase; use torch_impl. "
    "The ONNX adapter contract is in place (D-03/D-09) but no model is loaded "
    "in Phase 1."
)


class OnnxDetectionModel(DetectionModel):
    """ONNX Runtime text-detection backend (stub).

    Reference shape (reimplemented, not copied — D-12): provider auto-detection
    of CUDA vs CPU, sequential execution mode, ``enable_mem_pattern = False``.
    """

    def load(self, model_path: Path, device: str = "cpu") -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def detect(self, image: np.ndarray) -> Tuple[np.ndarray, list]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def configure(self, **kwargs) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def get_info(self) -> dict:
        return {"backend": "onnx", "status": "stub (NotImplementedError on load)"}


class OnnxInpaintModel(InpaintModel):
    """ONNX Runtime LaMa inpainting backend (stub)."""

    def load(self, model_path: Path, device: str = "cpu") -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def configure(self, **kwargs) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    def get_info(self) -> dict:
        return {"backend": "onnx", "status": "stub (NotImplementedError on load)"}

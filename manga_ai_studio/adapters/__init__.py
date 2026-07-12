"""Model adapter interfaces.

Abstract base classes (D-01) defining the contract for detection, OCR, and
inpainting models. Concrete backends (``torch_impl``, ``onnx_impl``) inject at
runtime via config (D-02): ``detection_backend``, ``ocr_backend``,
``inpainting_backend``.

Never import model libraries (torch, onnxruntime, etc.) outside the concrete
backend modules — all model operations flow through these interfaces (D-03).
"""

from manga_ai_studio.adapters.base import DetectionModel, InpaintModel, OCRModel

__all__ = ["DetectionModel", "OCRModel", "InpaintModel"]

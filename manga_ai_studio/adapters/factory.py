"""Backend factory — config-driven adapter resolution (D-02).

Resolves a concrete adapter (``DetectionModel`` / ``OCRModel`` /
``InpaintModel``) from a ``(kind, backend)`` pair so call sites never import a
backend class directly. Concrete classes are imported **lazily inside the
function bodies** to avoid pulling torch/onnxruntime when the factory is
imported (D-07 frontend/backend split).

Backend selection keys (CONTEXT.md §Specific Ideas):
    - ``detection_backend``  -> ``backend_factory("detection", value)``
    - ``ocr_backend``        -> ``backend_factory("ocr", value)``
    - ``inpainting_backend`` -> ``backend_factory("inpainting", value)``

Phase 1 default for every kind is ``"torch"`` (D-02).
"""

from __future__ import annotations

from manga_ai_studio.adapters.base import DetectionModel, InpaintModel, OCRModel


def backend_factory(kind: str, backend: str) -> DetectionModel | OCRModel | InpaintModel:
    """Resolve a concrete adapter for ``(kind, backend)``.

    Args:
        kind: one of ``"detection"``, ``"ocr"``, ``"inpainting"``.
        backend: one of ``"torch"``, ``"onnx"``.

    Returns:
        A concrete adapter instance (not yet loaded — call ``load()``).

    Raises:
        ValueError: unrecognized ``(kind, backend)`` combination.
        NotImplementedError: a backend that is contracted but not yet
            implemented in this phase (e.g. OCR, torch-inpainting).
    """
    if kind == "detection":
        if backend == "torch":
            # Lazy import: torch is only needed when a torch model is actually
            # constructed, not when the factory is imported (D-07).
            from manga_ai_studio.adapters.torch_impl import TorchCTDModel

            return TorchCTDModel()
        if backend == "onnx":
            from manga_ai_studio.adapters.onnx_impl import OnnxDetectionModel

            return OnnxDetectionModel()
        raise ValueError(f"Unknown backend: {kind}/{backend}")

    if kind == "ocr":
        if backend == "torch":
            # Lazy import: manga-ocr/transformers are only needed when an OCR
            # model is actually constructed, not when the factory is imported
            # (D-07). Plan 04-03 implements TorchOCRModel.
            from manga_ai_studio.adapters.torch_impl import TorchOCRModel

            return TorchOCRModel()
        if backend == "onnx":
            # D-14 hook: designed-in, not built-out. ONNXOCRModel lands in a
            # future phase.
            raise NotImplementedError("ONNX OCR backend lands in a future phase")
        raise ValueError(f"Unknown backend: {kind}/{backend}")

    if kind == "inpainting":
        if backend == "torch":
            # Lazy import: simple_lama_inpainting / torch are only needed when
            # an inpaint model is actually constructed, not when the factory is
            # imported (D-07). Plan 05 implements TorchLamaModel.
            from manga_ai_studio.adapters.torch_impl import TorchLamaModel

            return TorchLamaModel()
        if backend == "onnx":
            from manga_ai_studio.adapters.onnx_impl import OnnxInpaintModel

            return OnnxInpaintModel()
        raise ValueError(f"Unknown backend: {kind}/{backend}")

    raise ValueError(f"Unknown backend: {kind}/{backend}")

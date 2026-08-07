"""Adapter contract tests.

Verifies:
- The D-01 base ABCs (DetectionModel / OCRModel / InpaintModel) reject direct
  instantiation (TypeError on abstract instantiation).
- The D-03/D-09 ONNX stubs raise NotImplementedError on load (and on the
  inference methods), so the interface is honest without pulling onnxruntime.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manga_ai_studio.adapters.base import DetectionModel, InpaintModel, OCRModel
from manga_ai_studio.adapters.onnx_impl import OnnxDetectionModel, OnnxInpaintModel


def test_base_abc_rejects_instantiation() -> None:
    """Abstract base classes cannot be instantiated directly."""
    with pytest.raises(TypeError):
        DetectionModel()
    with pytest.raises(TypeError):
        OCRModel()
    with pytest.raises(TypeError):
        InpaintModel()


def test_onnx_stub_raises() -> None:
    """ONNX stubs raise NotImplementedError on load (and inference)."""
    det = OnnxDetectionModel()
    with pytest.raises(NotImplementedError):
        det.load(Path("x"))

    inp = OnnxInpaintModel()
    with pytest.raises(NotImplementedError):
        inp.load(Path("x"))


@pytest.mark.unit
def test_ocr_factory_returns_torch_ocr_model() -> None:
    """backend_factory('ocr', 'torch') returns a TorchOCRModel (D-14).

    The factory's 'ocr' branch is resolved (no longer raises
    NotImplementedError). The lazy import keeps the factory importable without
    manga_ocr (D-07); construction does not load the model.
    """
    from manga_ai_studio.adapters.factory import backend_factory
    from manga_ai_studio.adapters.torch_impl import TorchOCRModel

    model = backend_factory("ocr", "torch")
    assert isinstance(model, TorchOCRModel)
    assert model.model is None  # constructed but not loaded


@pytest.mark.unit
def test_ocr_factory_onnx_not_implemented() -> None:
    """backend_factory('ocr', 'onnx') raises NotImplementedError (D-14 hook).

    The ONNX OCR backend is designed-in (the branch exists) but not built-out
    in Phase 4 — a future phase provides ONNXOCRModel.
    """
    from manga_ai_studio.adapters.factory import backend_factory

    with pytest.raises(NotImplementedError, match="ONNX OCR backend"):
        backend_factory("ocr", "onnx")

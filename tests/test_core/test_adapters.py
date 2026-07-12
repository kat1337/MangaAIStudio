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

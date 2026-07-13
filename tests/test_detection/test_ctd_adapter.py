"""Tests for the CTD detection adapter and backend factory (plan 01-03 Task 1).

These tests guard the load-bearing contract: ``TorchCTDModel.detect`` MUST
unpack the ``TextDetector.__call__`` return as a **3-tuple**
``(mask, mask_refined, blk_list)`` (inference.py:210), NOT the 5-tuple claimed
in CONTEXT.md/RESEARCH.md. A 5-target unpack would raise ``ValueError``.

The tests use ``unittest.mock`` / monkeypatching so they run without torch
model weights in CI. ``torch`` is only imported lazily inside
``TorchCTDModel.load`` — the adapter module is importable without it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from manga_ai_studio.adapters.factory import backend_factory
from manga_ai_studio.adapters.torch_impl import TorchCTDModel


@pytest.mark.unit
def test_3_tuple_unpack_contract() -> None:
    """detect() unpacks exactly 3 values and returns (mask_refined, blk_list).

    Regression guard against the 5-tuple mistake (CONTEXT.md/RESEARCH.md claim
    a 5-tuple; verified source at inference.py:210 returns a 3-tuple). A fake
    detector returning a 3-tuple must flow through detect() cleanly.
    """
    model = TorchCTDModel()
    # Fake detector whose __call__ returns the VERIFIED 3-tuple.
    fake_mask = np.zeros((4, 4), dtype=np.uint8)
    fake_mask_refined = np.zeros((4, 4), dtype=np.uint8)
    fake_blk_list = ["blk1"]
    model.detector = MagicMock(return_value=(fake_mask, fake_mask_refined, fake_blk_list))

    mask_refined, blk_list = model.detect(np.zeros((4, 4, 3), dtype=np.uint8))

    assert blk_list == ["blk1"]
    np.testing.assert_array_equal(mask_refined, fake_mask_refined)


@pytest.mark.unit
def test_detect_raises_when_not_loaded() -> None:
    """detect() before load() raises RuntimeError (guard against None detector)."""
    model = TorchCTDModel()
    with pytest.raises(RuntimeError, match="Model not loaded"):
        model.detect(np.zeros((4, 4, 3), dtype=np.uint8))


@pytest.mark.unit
def test_load_missing_model_raises_file_not_found(tmp_path: Path) -> None:
    """load() raises FileNotFoundError before any torch import (T-01-04).

    The model path is validated BEFORE constructing TextDetector so a missing
    model surfaces a clear FileNotFoundError rather than a cryptic torch error.
    """
    model = TorchCTDModel()
    missing = tmp_path / "nonexistent.pt"
    with pytest.raises(FileNotFoundError, match="Model not found"):
        model.load(missing)
    # The detector must remain None — load failed before construction.
    assert model.detector is None


@pytest.mark.unit
def test_factory_torch_detection() -> None:
    """backend_factory('detection', 'torch') returns a TorchCTDModel."""
    model = backend_factory("detection", "torch")
    assert isinstance(model, TorchCTDModel)
    assert model.get_info()["backend"] == "torch"


@pytest.mark.unit
def test_factory_onnx_detection_raises_on_load(tmp_path: Path) -> None:
    """backend_factory('detection', 'onnx') -> OnnxDetectionModel; load raises."""
    from manga_ai_studio.adapters.onnx_impl import OnnxDetectionModel

    model = backend_factory("detection", "onnx")
    assert isinstance(model, OnnxDetectionModel)
    with pytest.raises(NotImplementedError):
        model.load(tmp_path / "x.onnx")


@pytest.mark.unit
def test_factory_unknown_raises() -> None:
    """backend_factory rejects an unrecognized backend with ValueError."""
    with pytest.raises(ValueError, match="Unknown backend"):
        backend_factory("detection", "wat")
    with pytest.raises(ValueError, match="Unknown backend"):
        backend_factory("inpainting", "wat")
    with pytest.raises(ValueError, match="Unknown backend"):
        backend_factory("nope", "torch")


@pytest.mark.unit
def test_factory_ocr_not_implemented() -> None:
    """OCR adapter is contracted but lands in Phase 4."""
    with pytest.raises(NotImplementedError, match="Phase 4"):
        backend_factory("ocr", "torch")


@pytest.mark.unit
def test_factory_inpainting_torch_not_implemented() -> None:
    """Inpainting torch adapter lands in plan 05."""
    with pytest.raises(NotImplementedError, match="plan 05"):
        backend_factory("inpainting", "torch")


@pytest.mark.unit
def test_get_info_defaults() -> None:
    """get_info reports the torch backend defaults before load."""
    model = TorchCTDModel()
    info = model.get_info()
    assert info == {
        "backend": "torch",
        "device": "cpu",
        "model": "comic_text_detector",
        "input_size": 1024,
    }


@pytest.mark.unit
def test_configure_stores_overrides() -> None:
    """configure() captures overrides applied on the next load()."""
    model = TorchCTDModel()
    model.configure(input_size=2048, act="relu")
    assert model._input_size == 2048
    assert model._act == "relu"


@pytest.mark.unit
def test_postprocess_thresholds_mask() -> None:
    """postprocess binarizes a heatmap at 128 (RESEARCH Pattern 1)."""
    model = TorchCTDModel()
    heatmap = np.array([[0, 128, 200, 255]], dtype=np.uint8)
    binary = model.postprocess(heatmap)
    assert binary.tolist() == [[0, 0, 255, 255]]

"""Tests for the LaMa inpainting adapter and backend factory (plan 01-05 Task 1).

These tests guard the load-bearing contract: ``TorchLamaModel.inpaint`` MUST
convert numpy image/mask -> PIL, delegate to SimpleLama exactly once, and
return a numpy RGB array cropped to the input size (inpainting.py:30-37
size-reclamp). ``load`` MUST validate the model path BEFORE importing
``simple_lama_inpainting`` (T-01-04b) and set ``os.environ["LAMA_MODEL"]``.

The tests use ``unittest.mock`` / monkeypatching so they run WITHOUT torch or
LaMa model weights in CI. ``simple_lama_inpainting`` is only imported lazily
inside ``TorchLamaModel.load`` — the adapter module is importable without it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from manga_ai_studio.adapters.factory import backend_factory
from manga_ai_studio.adapters.torch_impl import TorchLamaModel


class FakeSimpleLama:
    """A fake SimpleLama that records its call args and returns a PIL image.

    ``size`` controls the returned image size (default = match the input). Used
    to assert the size-reclamp (inpainting.py:34-37) and the binary-mask
    contract without a real LaMa model.
    """

    def __init__(self, size: tuple[int, int] | None = None) -> None:
        self.calls: list[tuple[Image.Image, Image.Image]] = []
        self._size = size

    def __call__(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        self.calls.append((image, mask))
        w, h = self._size if self._size is not None else image.size
        # Return a solid-color RGB image of the requested size.
        out = Image.new("RGB", (w, h), (10, 20, 30))
        return out


def _rgb_4x4() -> np.ndarray:
    """A 4x4x3 uint8 RGB test image."""
    return np.full((4, 4, 3), 200, dtype=np.uint8)


def _mask_4x4() -> np.ndarray:
    """A 4x4 uint8 binary mask with a painted center."""
    m = np.zeros((4, 4), dtype=np.uint8)
    m[1:3, 1:3] = 255
    return m


@pytest.mark.unit
def test_lama_load_missing_model_raises(tmp_path: Path, monkeypatch) -> None:
    """load() raises FileNotFoundError BEFORE any simple_lama import (T-01-04b).

    A guard module that raises on import is installed under
    ``simple_lama_inpainting`` so the test proves the path check short-circuits
    before SimpleLama is constructed.
    """
    # Make importing simple_lama_inpainting raise — proves load() does not reach it.
    import types

    def _explode_import(*a, **k):
        raise AssertionError("simple_lama_inpainting must not be imported before the path check")

    fake_module = types.ModuleType("simple_lama_inpainting")
    # __import__ side-effect: if load() reaches the lazy import, this trips.
    monkeypatch.setitem(sys.modules, "simple_lama_inpainting", fake_module)
    # Also patch __import__ so the `from simple_lama_inpainting import SimpleLama`
    # line trips the assertion if it is reached.
    real_import = __import__

    def _guard_import(name, *args, **kwargs):
        if name == "simple_lama_inpainting":
            raise AssertionError("simple_lama_inpainting imported before path check")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _guard_import)

    model = TorchLamaModel()
    missing = tmp_path / "nonexistent.pt"
    with pytest.raises(FileNotFoundError, match="Model not found"):
        model.load(missing)
    # The model must remain None — load failed before SimpleLama construction.
    assert model.model is None
    assert model.model_path is None


@pytest.mark.unit
def test_lama_inpaint_wraps_simple_lama() -> None:
    """inpaint() delegates to SimpleLama once and returns a numpy RGB array."""
    model = TorchLamaModel()
    fake = FakeSimpleLama()
    model.model = fake  # skip load(); inject the fake directly

    rgb = _rgb_4x4()
    mask = _mask_4x4()
    result = model.inpaint(rgb, mask)

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.uint8
    assert result.shape == (4, 4, 3)
    # SimpleLama was called exactly once with PIL image + PIL mask.
    assert len(fake.calls) == 1
    pil_image, pil_mask = fake.calls[0]
    assert isinstance(pil_image, Image.Image)
    assert isinstance(pil_mask, Image.Image)


@pytest.mark.unit
def test_lama_inpaint_crops_to_input_size() -> None:
    """A larger-than-input result is cropped to the input (H, W)."""
    model = TorchLamaModel()
    fake = FakeSimpleLama(size=(8, 8))  # returns 8x8 even though input is 4x4
    model.model = fake

    result = model.inpaint(_rgb_4x4(), _mask_4x4())
    assert result.shape == (4, 4, 3)


@pytest.mark.unit
def test_lama_inpaint_passes_binary_mask() -> None:
    """The mask handed to SimpleLama is mode 'L' with extrema (0, 255)."""
    model = TorchLamaModel()
    fake = FakeSimpleLama()
    model.model = fake

    model.inpaint(_rgb_4x4(), _mask_4x4())
    _pil_image, pil_mask = fake.calls[0]
    assert pil_mask.mode == "L"
    assert pil_mask.getextrema() == (0, 255)


@pytest.mark.unit
def test_lama_inpaint_raises_when_not_loaded() -> None:
    """inpaint() before load() raises RuntimeError."""
    model = TorchLamaModel()
    with pytest.raises(RuntimeError, match="Model not loaded"):
        model.inpaint(_rgb_4x4(), _mask_4x4())


@pytest.mark.unit
def test_lama_load_sets_env_var(tmp_path: Path, monkeypatch) -> None:
    """After a successful load, os.environ['LAMA_MODEL'] == str(model_path).

    Uses a fake SimpleLama injected via sys.modules so no torch is needed.
    """
    import types

    fake_module = types.ModuleType("simple_lama_inpainting")
    fake_module.SimpleLama = lambda: FakeSimpleLama()
    monkeypatch.setitem(sys.modules, "simple_lama_inpainting", fake_module)

    # Create an empty temp file so is_file() is True.
    model_file = tmp_path / "big-lama.pt"
    model_file.write_bytes(b"")

    # Clean up the env var before the test so we assert the load set it.
    monkeypatch.delenv("LAMA_MODEL", raising=False)

    model = TorchLamaModel()
    model.load(model_file)

    assert os.environ.get("LAMA_MODEL") == str(model_file)
    assert model.model is not None
    assert model.model_path == model_file


@pytest.mark.unit
def test_factory_inpainting_torch() -> None:
    """backend_factory('inpainting', 'torch') returns a TorchLamaModel."""
    model = backend_factory("inpainting", "torch")
    assert isinstance(model, TorchLamaModel)
    assert model.get_info()["backend"] == "torch"
    assert model.get_info()["model"] == "big-lama"


@pytest.mark.unit
def test_factory_inpainting_onnx_raises_on_load(tmp_path: Path) -> None:
    """backend_factory('inpainting', 'onnx') -> OnnxInpaintModel; load raises."""
    from manga_ai_studio.adapters.onnx_impl import OnnxInpaintModel

    model = backend_factory("inpainting", "onnx")
    assert isinstance(model, OnnxInpaintModel)
    with pytest.raises(NotImplementedError):
        model.load(tmp_path / "x.onnx")

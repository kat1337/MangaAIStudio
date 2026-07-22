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


# ---------------------------------------------------------------------------
# Plan 01-07 Task 2 — Gap-closure regression tests (CR-02 / CLEAN-06)
#
# The original lama tests stubbed SimpleLama but never exercised the
# model-path resolver, so CR-02 (passing a Profile to get_inpainting_model_path,
# which expects a Config; AttributeError swallowed by bare `except Exception:`;
# fallback to the WRONG filename big-lama.pt) shipped green. These tests call
# the REAL get_inpainting_model_path (no monkeypatch on it) so future arg-type
# drift surfaces in CI.
# ---------------------------------------------------------------------------

pytest.importorskip("PySide6")  # noqa: E402 — MainWindow needs Qt

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _make_window(qtbot, tmp_path):
    """Build a MainWindow wired to a profile manager in tmp_path."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


@pytest.mark.unit
def test_resolve_inpainting_model_path_returns_cache_dir_path(qtbot, tmp_path) -> None:
    """CR-02: the resolver delegates to ``get_inpainting_model_path(config)``.

    The returned path's parent MUST equal ``config.get_model_cache_dir()`` and
    the filename MUST be the vendored default. No AttributeError is raised —
    proving the Config (not the Profile) is passed. The CR-02 bug passed
    ``config.current_profile`` (a Profile, lacking get_model_cache_dir) to the
    vendored function; the AttributeError was swallowed by the bare except.

    No-stub guard: this test does NOT monkeypatch ``get_inpainting_model_path``
    — the REAL vendored function is exercised.
    """
    window = _make_window(qtbot, tmp_path)
    cache_dir = window.profile_manager.config.get_model_cache_dir()

    resolved = window._resolve_inpainting_model_path()

    assert resolved.parent == cache_dir, (
        f"resolver must return a path under cache_dir {cache_dir}, got {resolved.parent}"
    )
    assert resolved.name == "anime-manga-big-lama.pt"


@pytest.mark.unit
def test_resolve_inpainting_model_path_filename_matches_vendored_default(
    qtbot, tmp_path
) -> None:
    """CR-02: the resolver returns the vendored default filename.

    Catches BOTH the original wrong-default bug (``big-lama.pt``, which is the
    DEPRECATED ``get_old_inpainting_model_path`` default) AND confirms the
    resolver delegates to the current vendored ``get_inpainting_model_path``
    (model_downloader.py:143-149 -> ``anime-manga-big-lama.pt``).
    """
    window = _make_window(qtbot, tmp_path)

    resolved = window._resolve_inpainting_model_path()

    assert resolved.name == "anime-manga-big-lama.pt", (
        f"resolver filename must match vendored default, got {resolved.name!r}"
    )
    assert resolved.name != "big-lama.pt"  # the wrong, deprecated default


@pytest.mark.unit
def test_resolve_inpainting_model_path_no_bare_except(qtbot, tmp_path) -> None:
    """CR-02 anti-pattern guard: no bare ``except Exception:`` in the resolver.

    The narrowed except must be ``(FileNotFoundError, OSError)`` so
    AttributeError/TypeError/ValueError propagate (signature drift surfaces).
    """
    import inspect

    from manga_ai_studio.gui.main_window import MainWindow

    source = inspect.getsource(MainWindow._resolve_inpainting_model_path)
    assert "except Exception" not in source, (
        "_resolve_inpainting_model_path must not have a bare `except Exception:` "
        "(CR-02 root cause). Narrow to (FileNotFoundError, OSError)."
    )
    assert "except (FileNotFoundError, OSError)" in source


@pytest.mark.unit
def test_resolve_inpainting_model_path_programming_errors_propagate(
    qtbot, tmp_path, monkeypatch
) -> None:
    """CR-02 propagation guard: AttributeError from arg-type drift MUST propagate.

    Simulates a future signature change in ``get_inpainting_model_path`` by
    patching it to raise ``AttributeError`` (the exact error CR-02 produced
    when a Profile was passed). The narrowed except (FileNotFoundError,
    OSError) must NOT catch it — programming errors propagate to dev/test.
    """
    window = _make_window(qtbot, tmp_path)

    def _raise_attrerror(_config):
        raise AttributeError("simulated signature drift")

    monkeypatch.setattr(
        "panelcleaner.model_downloader.get_inpainting_model_path", _raise_attrerror
    )

    with pytest.raises(AttributeError, match="simulated signature drift"):
        window._resolve_inpainting_model_path()

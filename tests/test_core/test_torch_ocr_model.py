"""Tests for the TorchOCRModel adapter (plan 04-03 Task 2).

These tests guard the load-bearing contract for the OCR adapter (D-14 /
TEXT-02):

- ``TorchOCRModel`` mirrors ``TorchLamaModel``'s shape (lazy-import in
  ``load()``, numpy->PIL round-trip in ``recognize()``, plain ``str`` return,
  "Model not loaded" guard) — RESEARCH §Pattern 1.
- The numpy->PIL conversion is the load-bearing detail (Pitfall 2:
  manga-ocr's ``__call__`` accepts ``PIL.Image``, NOT numpy). Passing numpy
  straight through raises ``ValueError`` at OCR time.
- The heavy ``manga_ocr`` import is lazy inside ``load()`` so the adapter
  module is importable without it (D-07).

The unit tests inject a ``FakeMangaOcr`` (a callable returning a canned str)
via monkeypatching the ``MangaOcr`` symbol resolved inside ``load()``, so they
run without the ~450MB HF model in CI. A separate integration test (skip-gated
on ``is_ocr_downloaded()``) exercises the real model end-to-end when cached.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from manga_ai_studio.adapters.torch_impl import TorchOCRModel


def _install_fake_mangaocr(monkeypatch, canned_text: str = "こんにちは"):
    """Install a FakeMangaOcr singleton wrapper into torch_impl's load() path.

    ``TorchOCRModel.load`` does ``from panelcleaner.ocr.ocr_mangaocr import
    MangaOcr``. We patch the class in the vendored module so the lazy import
    resolves to our fake. The fake's instances are callable returning the
    canned text, and ``initialize_model`` records that it was invoked.
    """
    calls = {"initialize": 0}

    class _FakeInstance:
        def __init__(self, *args, **kwargs):
            self._canned = canned_text

        def initialize_model(self, *args, **kwargs):
            calls["initialize"] += 1
            return self

        def __call__(self, img):
            # Record the received image object for the PIL-conversion assertion.
            calls["last_img"] = img
            return self._canned

    class FakeMangaOcr:
        def __new__(cls, *args, **kwargs):
            return _FakeInstance(*args, **kwargs)

    import panelcleaner.ocr.ocr_mangaocr as mod

    monkeypatch.setattr(mod, "MangaOcr", FakeMangaOcr)
    return calls


@pytest.mark.unit
def test_load_lazy_imports_model(monkeypatch, tmp_path: Path) -> None:
    """load() constructs the MangaOcr singleton and calls initialize_model().

    The lazy import lives inside load() (D-07). After load() the model attr is
    a callable wrapper whose initialize_model was invoked (triggers the
    first-run HF download inside the worker, not at module import).
    """
    calls = _install_fake_mangaocr(monkeypatch)
    adapter = TorchOCRModel()
    assert adapter.model is None  # not loaded yet

    adapter.load(model_path=tmp_path)

    assert adapter.model is not None
    assert calls["initialize"] == 1


@pytest.mark.unit
def test_recognize_converts_numpy_to_pil(monkeypatch, tmp_path: Path) -> None:
    """recognize() does Image.fromarray(image, mode='RGB') before the model call.

    Pitfall 2: manga-ocr accepts PIL.Image, NOT numpy. The adapter MUST convert
    via PIL.Image.fromarray with mode='RGB' (mirror TorchLamaModel.inpaint).
    """
    _install_fake_mangaocr(monkeypatch)
    adapter = TorchOCRModel()
    adapter.load(model_path=tmp_path)

    captured = {}

    def fake_fromarray(arr, mode=None):
        captured["arr"] = arr
        captured["mode"] = mode
        # Return a stand-in PIL image object (the fake model just records it).
        return ("PIL_IMAGE", arr)

    import manga_ai_studio.adapters.torch_impl as ti

    monkeypatch.setattr(ti.Image, "fromarray", fake_fromarray)

    image = np.zeros((4, 4, 3), dtype=np.uint8)
    adapter.recognize(image)

    assert captured["mode"] == "RGB"
    np.testing.assert_array_equal(captured["arr"], image)


@pytest.mark.unit
def test_recognize_returns_str(monkeypatch, tmp_path: Path) -> None:
    """recognize() returns the plain str from the model call (not numpy)."""
    canned = "テスト文字"
    _install_fake_mangaocr(monkeypatch, canned_text=canned)
    adapter = TorchOCRModel()
    adapter.load(model_path=tmp_path)

    result = adapter.recognize(np.zeros((4, 4, 3), dtype=np.uint8))

    assert isinstance(result, str)
    assert result == canned


@pytest.mark.unit
def test_recognize_raises_when_not_loaded() -> None:
    """recognize() before load() raises RuntimeError (mirror TorchLamaModel)."""
    adapter = TorchOCRModel()
    with pytest.raises(RuntimeError, match="Model not loaded"):
        adapter.recognize(np.zeros((4, 4, 3), dtype=np.uint8))


@pytest.mark.unit
def test_module_imports_without_manga_ocr() -> None:
    """The adapter module is importable without manga_ocr (D-07 lazy import).

    The heavy ``from manga_ocr import MangaOcr`` is paid inside load(), not at
    module import time. Verified in an ISOLATED subprocess that blocks
    ``manga_ocr`` via a meta-path finder, then imports torch_impl — a
    subprocess is used (rather than in-process ``importlib.reload``) because
    reloading rebinds the adapter classes and poisons ``isinstance`` checks
    for sibling factory tests sharing the same process.
    """
    import os
    import subprocess
    import sys

    code = (
        "import sys, importlib.abc\n"
        "class _Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'manga_ocr' or name.startswith('manga_ocr.'):\n"
        "            raise ImportError('manga_ocr blocked for D-07 test')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Block())\n"
        "import manga_ai_studio.adapters.torch_impl as ti\n"
        "assert hasattr(ti, 'TorchOCRModel'), 'TorchOCRModel missing'\n"
        "print('torch_impl imports without manga_ocr')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    assert result.returncode == 0, (
        f"torch_impl import failed without manga_ocr:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "torch_impl imports without manga_ocr" in result.stdout


@pytest.mark.unit
def test_load_constructs_via_panelcleaner_module(monkeypatch, tmp_path: Path) -> None:
    """load() resolves MangaOcr from panelcleaner.ocr.ocr_mangaocr (D-07 seam).

    Guards that the lazy import path is the vendored singleton wrapper, not the
    bare manga_ocr.MangaOcrModel (which would bypass the singleton + load-once
    semantics — T-4-06 DoS mitigation).
    """
    import panelcleaner.ocr.ocr_mangaocr as ocrmod

    constructed = {"count": 0}

    real_new = ocrmod.MangaOcr.__new__

    def spy_new(cls, *args, **kwargs):
        constructed["count"] += 1
        return real_new(cls, *args, **kwargs)

    monkeypatch.setattr(ocrmod.MangaOcr, "__new__", spy_new)
    # initialize_model would trigger the real ~450MB load; stub it out on the
    # instance via a class-level patch.
    monkeypatch.setattr(ocrmod.MangaOcr, "initialize_model", lambda self, *a, **k: self)

    adapter = TorchOCRModel()
    adapter.load(model_path=tmp_path)

    assert constructed["count"] == 1
    assert isinstance(adapter.model, ocrmod.MangaOcr)


# --- Integration test (skip-gated on real model availability) -----------------


def _ocr_model_available() -> bool:
    """True when the kha-white/manga-ocr-base HF cache directory exists."""
    try:
        import panelcleaner.model_downloader as md
    except Exception:  # pragma: no cover - dep missing in CI
        return False
    try:
        return bool(md.is_ocr_downloaded())
    except Exception:  # pragma: no cover
        return False


@pytest.mark.integration
def test_recognize_real_model_end_to_end(tmp_path: Path) -> None:
    """End-to-end OCR: load() the real manga-ocr model, recognize a white image.

    Skip-gated on is_ocr_downloaded() so CI does NOT force the ~450MB download.
    Runs locally when the model is cached. Asserts the round-trip returns a str
    (the recognized text for a blank white page is typically an empty string,
    which is still a valid str result — the contract is the type, not content).
    """
    if not _ocr_model_available():
        pytest.skip("manga-ocr model not cached (is_ocr_downloaded() is False)")

    from manga_ai_studio.adapters.torch_impl import TorchOCRModel

    adapter = TorchOCRModel()
    adapter.load(model_path=tmp_path)

    # A solid white 64x64 RGB region: model returns a (possibly empty) str.
    white = np.full((64, 64, 3), 255, dtype=np.uint8)
    result = adapter.recognize(white)

    assert isinstance(result, str)

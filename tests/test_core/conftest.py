"""Shared fake adapters + helpers for the Plan 02-03 batch_runner suite.

Defines ``FakeDetectionModel`` and ``FakeInpaintModel`` mirroring the real
``adapters/torch_impl.py`` contracts (``TorchCTDModel.detect`` returns
``(mask_refined, blk_list)``; ``TorchLamaModel.inpaint(image_rgb, mask_binary)``
returns an ``(H, W, 3)`` uint8 RGB array) so ``tests/test_core/test_batch_runner.py``
can exercise the page loop WITHOUT torch, WITHOUT model weights, and WITHOUT
the GUI. This extends the Phase 1 fake-adapter pattern
(``tests/test_inpainting/test_lama_adapter.py:FakeSimpleLama`` and
``tests/test_inpainting/test_inpaint_gui.py:_FakeInpaintModel``) to BOTH
adapters and adds hooks for the per-page-failure and abort-between-pages tests.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from manga_ai_studio.core.image_file import ImageFile


class FakeDetectionModel:
    """Fake detection adapter mirroring ``TorchCTDModel``.

    ``detect(image)`` records the input and returns ``(mask, [])`` where ``mask``
    is an ``(H, W)`` uint8 array with a small region set to 255 so the persisted
    mask reports ``has_mask_content() == True``. Two test hooks:

    - ``fail_on_call`` (int): when ``len(self.calls) == fail_on_call``, ``detect``
      raises ``RuntimeError`` — used by ``test_per_page_failure_continues``.
    - ``set_flag_after`` / ``flag``: when the Nth detect call lands and ``flag``
      is set, the shared abort flag is flipped — used by
      ``test_abort_between_pages`` (cancel between pages, D-09).

    Mirrors the real contract: ``load(self, model_path, device="cpu")`` and
    ``detect(self, image) -> (mask_refined, blk_list)``.
    """

    def __init__(
        self,
        fail_on_call: int | None = None,
        set_flag_after: int | None = None,
        flag=None,
    ) -> None:
        self.calls: list[np.ndarray] = []
        self.load_calls: int = 0
        self.loaded_path = None
        self.fail_on_call = fail_on_call
        self.set_flag_after = set_flag_after
        self._flag = flag
        # quick-260903-lm6: the real adapters accept configure(**kwargs)
        # before load(); batch_runner forwards the profile's min confidence
        # through it, so the fake records the kwargs for assertions.
        self.configure_calls: list[dict] = []

    def configure(self, **kwargs) -> None:
        """Mirror ``TorchCTDModel.configure(**kwargs)`` (pre-load knob pass)."""
        self.configure_calls.append(kwargs)

    def load(self, model_path, device: str = "cpu") -> None:
        """Mirror ``TorchCTDModel.load(model_path, device="auto")``."""
        self.load_calls += 1
        self.loaded_path = model_path

    def detect(self, image: np.ndarray):
        """Mirror ``TorchCTDModel.detect(image) -> (mask_refined, blk_list)``."""
        self.calls.append(image)
        # Per-page-failure injection (D-04 test hook).
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError("injected detect failure for per-page test")
        # Abort-between-pages injection (D-09 test hook): flip the shared flag
        # after the Nth page so the NEXT loop-top check raises Abort.
        if self.set_flag_after is not None and self._flag is not None:
            if len(self.calls) >= self.set_flag_after:
                self._flag.set(True)
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[1:3, 1:3] = 255  # a small detected region -> has_mask_content True
        # D-04 (plan 08-09): the detect loop NO LONGER discards the blk_list —
        # it builds boxes via build_detected_pageboxes and constrains the mask
        # to box interiors. Return a full-page detected box so the derived
        # mask keeps content (an empty blk_list would derive an empty mask and
        # the D-03 gate would passthrough every page, gutting the pre-Phase-8
        # batch behavior these contracts lock).
        h, w = image.shape[:2]
        return mask, [SimpleNamespace(xyxy=[0, 0, w, h])]


class FakeInpaintModel:
    """Fake inpaint adapter mirroring ``TorchLamaModel``.

    ``inpaint(image_rgb, mask_binary)`` records the inputs and returns a solid
    ``(H, W, 3)`` uint8 RGB array filled with ``fill``. Mirrors the real
    contract: ``load(self, model_path)`` (device accepted for ABC compat) and
    ``inpaint(self, image_rgb, mask_binary) -> result_rgb``.
    """

    def __init__(self, fill: int = 7) -> None:
        self.fill = fill
        self.calls: list[tuple[np.ndarray, np.ndarray]] = []
        self.load_calls: int = 0
        self.loaded_path = None

    def load(self, model_path, device: str = "cpu") -> None:
        """Mirror ``TorchLamaModel.load(model_path, device="cpu")``."""
        self.load_calls += 1
        self.loaded_path = model_path

    def inpaint(self, image_rgb: np.ndarray, mask_binary: np.ndarray) -> np.ndarray:
        """Mirror ``TorchLamaModel.inpaint(image_rgb, mask_binary) -> result_rgb``."""
        self.calls.append((image_rgb, mask_binary))
        return np.full(image_rgb.shape, self.fill, dtype=np.uint8)


@pytest.fixture()
def fake_adapters():
    """Return a fresh ``(FakeDetectionModel, FakeInpaintModel)`` pair.

    Injected into the entry points by monkeypatching
    ``manga_ai_studio.core.batch_runner.backend_factory`` to dispatch on ``kind``
    (detection -> det, inpainting -> inp), mirroring the Phase 1 GUI test pattern
    (``test_inpaint_gui.py`` monkeypatches
    ``manga_ai_studio.gui.main_window.backend_factory``).
    """
    return FakeDetectionModel(), FakeInpaintModel()


class RecordingSignal:
    """Minimal stand-in for a Qt ``Signal`` exposing ``.emit(payload)``.

    The batch loop calls ``progress_callback.emit((percent, page_name))`` per
    page (D-10). In production ``progress_callback`` is the Worker's
    ``WorkerSignals.progress`` signal; in tests this recorder captures every
    emitted payload so the suite can assert per-page progress without a Qt
    event loop.
    """

    def __init__(self) -> None:
        self.calls: list = []

    def emit(self, payload) -> None:
        self.calls.append(payload)


def make_pages(src_dir: Path, count: int = 3, size: tuple[int, int] = (8, 8)):
    """Write ``count`` small white PNGs into ``src_dir`` and return ``ImageFile``s.

    Real PNG files (not in-memory arrays) so the loop's
    ``cv2.imdecode(np.fromfile(...))`` read path (CR-17) works exactly as it
    does in production. Each page starts with ``mask=None``; tests that need a
    persisted mask (e.g. ``test_batch_clean_skips_empty_mask``) set it
    explicitly via ``numpy_binary_to_mask_qimage``.
    """
    src_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    arr = np.full((size[0], size[1], 3), 255, dtype=np.uint8)
    for i in range(count):
        p = src_dir / f"page{i + 1}.png"
        Image.fromarray(arr, mode="RGB").save(p)
        pages.append(ImageFile(path=p))
    return pages


def install_fakes(monkeypatch, det, inp):
    """Monkeypatch ``batch_runner.backend_factory`` to return the fake pair.

    Dispatches on ``kind``: ``"detection"`` -> ``det``, ``"inpainting"`` -> ``inp``.
    Returns ``None``; the fakes are the same instances the test holds references
    to, so post-run assertions on ``*.calls`` / ``*.load_calls`` reflect what
    the loop actually did.
    """

    def _factory(kind: str, backend: str):
        if kind == "detection":
            return det
        if kind == "inpainting":
            return inp
        raise ValueError(f"unexpected kind in fake factory: {kind}")

    monkeypatch.setattr(
        "manga_ai_studio.core.batch_runner.backend_factory", _factory
    )

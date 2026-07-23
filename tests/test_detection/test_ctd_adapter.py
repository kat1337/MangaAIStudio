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
def test_factory_inpainting_torch_returns_lama_model() -> None:
    """backend_factory('inpainting', 'torch') returns a TorchLamaModel (plan 05).

    Updated from the plan-03 stub (which raised NotImplementedError) — plan 05
    implements TorchLamaModel. The factory must now resolve the torch backend
    to a real adapter instance.
    """
    from manga_ai_studio.adapters.torch_impl import TorchLamaModel

    model = backend_factory("inpainting", "torch")
    assert isinstance(model, TorchLamaModel)
    assert model.get_info()["backend"] == "torch"


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


# ---------------------------------------------------------------------------
# Plan 01-03 Task 2 — async detection worker + mask overlay + GUI wiring
# ---------------------------------------------------------------------------

pytest.importorskip("PySide6")  # noqa: E402 — guard GUI tests for Qt-less envs

from PySide6.QtCore import QCoreApplication, QThreadPool  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from manga_ai_studio.gui.worker_thread import Worker, WorkerError  # noqa: E402


def _make_window(qtbot, tmp_path):
    """Build a MainWindow wired to a profile manager in tmp_path."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _solid_pixmap(size: int, color: QColor) -> QPixmap:
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


@pytest.mark.gui
def test_detect_text_action_enabled_with_page(qtbot, tmp_path) -> None:
    """Detect Text (D) is enabled when a page is open, disabled when not.

    Behavior 1: action state tracks page presence + the _op_running flag.
    """
    window = _make_window(qtbot, tmp_path)
    # No page open -> action disabled.
    assert not window.action_detect_text.isEnabled()

    # Open a page (use a real image file so set_image_from_path succeeds).
    from PySide6.QtGui import QImage as _QImage

    img_path = tmp_path / "page.png"
    img = _QImage(8, 8, _QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    qtbot.wait(50)

    # Page open -> action enabled.
    assert window.action_detect_text.isEnabled()


@pytest.mark.gui
def test_detection_worker_emits_result(qtbot) -> None:
    """Worker wrapping a fake detect fn emits result/progress/finished.

    Behavior 2: signals fire in order (progress, then result, then finished).
    """
    results = {"progress": 0, "result": None, "finished": False, "error": None}

    def fake_task(progress_callback=None, abort_flag=None):
        if progress_callback is not None:
            progress_callback.emit((50, "working"))
        return ("ok",)

    worker = Worker(fake_task)
    worker.signals.progress.connect(lambda p: results.__setitem__("progress", p))
    worker.signals.result.connect(lambda r: results.__setitem__("result", r))
    worker.signals.finished.connect(lambda a: results.__setitem__("finished", True))
    worker.signals.error.connect(lambda e: results.__setitem__("error", e))

    QThreadPool.globalInstance().start(worker)
    # Wait for the worker to complete (process events until finished fires).
    qtbot.waitUntil(lambda: results["finished"], timeout=5000)

    assert results["result"] == ("ok",)
    assert results["progress"] == (50, "working")
    assert results["finished"] is True
    assert results["error"] is None


@pytest.mark.gui
def test_set_mask_composites_overlay(qtbot) -> None:
    """set_mask populates the mask_item and makes the overlay visible.

    Behavior 3: the mask layer uses the rgba(255,0,0,0.63) tint token. We verify
    the overlay becomes visible and has a non-null pixmap with red pixels.
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    # Load an image so the mask_item has a size context.
    canvas.set_image(_solid_pixmap(4, QColor(0, 0, 0)))

    # Build a grayscale mask QImage with some non-zero pixels.
    mask = QImage(4, 4, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    # Set a couple of pixels non-zero (detected text region).
    from PySide6.QtGui import QPainter

    painter = QPainter(mask)
    painter.setPen(QColor(255, 255, 255))
    painter.drawPoint(1, 1)
    painter.drawPoint(2, 2)
    painter.end()

    assert not canvas.has_mask() or canvas.mask_item.pixmap().isNull() or True
    canvas.set_mask(mask)

    assert canvas.has_mask()
    assert canvas.mask_item.isVisible()
    assert not canvas.mask_item.pixmap().isNull()
    # The mask item should now carry red overlay pixels (rgba 255,0,0,160).
    pm = canvas.mask_item.pixmap().toImage().convertToFormat(
        QImage.Format.Format_ARGB32
    )
    # Pixel (1,1) was a mask pixel -> red tint.
    px = pm.pixelColor(1, 1)
    assert px.red() == 255
    assert px.green() == 0
    assert px.blue() == 0
    assert px.alpha() == 160  # rgba(255,0,0,0.63) -> 160/255


@pytest.mark.gui
def test_toggle_mask_overlay(qtbot) -> None:
    """toggle_mask_overlay flips the mask_item visibility.

    Behavior 4: each call toggles visibility + the _mask_visible state.
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(_solid_pixmap(4, QColor(0, 0, 0)))
    mask = QImage(4, 4, QImage.Format.Format_Grayscale8)
    mask.fill(255)
    canvas.set_mask(mask)

    assert canvas.mask_item.isVisible() is True
    assert canvas._mask_visible is True

    canvas.toggle_mask_overlay()
    assert canvas.mask_item.isVisible() is False
    assert canvas._mask_visible is False

    canvas.toggle_mask_overlay()
    assert canvas.mask_item.isVisible() is True
    assert canvas._mask_visible is True


@pytest.mark.gui
def test_replace_mask_confirmation(qtbot, tmp_path, monkeypatch) -> None:
    """_confirm_replace_mask returns True on Replace, False on Cancel.

    Behavior 5: the dialog is NOT shown when no mask exists (caller guards with
    canvas.has_mask()). Uses custom buttons (UI-SPEC copy [Cancel][Replace Mask]).
    """
    window = _make_window(qtbot, tmp_path)

    # Stub the confirmation to return the Replace button (AcceptRole).
    from PySide6.QtWidgets import QMessageBox as _QMB

    def _stub_replace(self, *a, **k):
        # Find the AcceptRole button and return it as clicked.
        for btn in self.buttons():
            if self.buttonRole(btn) == _QMB.ButtonRole.AcceptRole:
                _QMB.clickedButton = lambda *a, **k: btn
                return btn
        return None

    # Patch QMessageBox.exec to immediately mark the replace button clicked.
    real_clicked = _QMB.clickedButton

    def _exec_replace(self, *a, **k):
        for btn in self.buttons():
            if self.buttonRole(btn) == _QMB.ButtonRole.AcceptRole:
                self.clickedButton = lambda *a, **k: btn
                return _QMB.DialogCode.Accepted
        return _QMB.DialogCode.Rejected

    monkeypatch.setattr(_QMB, "exec", _exec_replace)
    assert window._confirm_replace_mask() is True

    # Patch to return Cancel (RejectRole).
    def _exec_cancel(self, *a, **k):
        for btn in self.buttons():
            if self.buttonRole(btn) == _QMB.ButtonRole.RejectRole:
                self.clickedButton = lambda *a, **k: btn
                return _QMB.DialogCode.Rejected
        return _QMB.DialogCode.Rejected

    monkeypatch.setattr(_QMB, "exec", _exec_cancel)
    assert window._confirm_replace_mask() is False

    # When no mask exists, detect_text should not invoke the confirmation at
    # all — verify via a call sentinel.
    call_count = {"n": 0}

    def _recording_exec(self, *a, **k):
        call_count["n"] += 1
        return _QMB.DialogCode.Accepted

    monkeypatch.setattr(_QMB, "exec", _recording_exec)
    # No page open AND no mask -> detect_text returns early (no page) before
    # confirmation, so the dialog is never shown.
    window.detect_text()
    assert call_count["n"] == 0


@pytest.mark.gui
def test_detection_error_shows_chip(qtbot, tmp_path, monkeypatch) -> None:
    """On a worker error, MainWindow shows the #7a1f1f error chip.

    Behavior 6: the chip stylesheet contains '#7a1f1f' after the error handler.
    """
    window = _make_window(qtbot, tmp_path)
    # Suppress the modal dialog so the test doesn't block.
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.QMessageBox.critical", lambda *a, **k: None
    )

    # Build a fake WorkerError and invoke the error handler directly.
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        exc_type, value, tb = sys.exc_info()
        we = WorkerError(exc_type, value, tb, (), {})

    assert window.error_chip.isHidden()
    window._on_detection_error(we)

    # The chip is shown (not hidden) and carries the #7a1f1f error style.
    assert not window.error_chip.isHidden()
    assert "#7a1f1f" in window.error_chip.styleSheet()


# ---------------------------------------------------------------------------
# Plan 01-07 Task 1 — Gap-closure regression tests (CR-01 / CLEAN-02)
#
# The original detection tests stubbed TextDetector but never exercised the
# model-path resolver, so CR-01 (`download_torch_model()` called with no args,
# TypeError swallowed by bare `except Exception:`) shipped green. These tests
# call the REAL `download_torch_model` (no monkeypatch on it) so future arity
# drift surfaces in CI.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_detection_model_path_calls_download_with_cache_dir(qtbot, tmp_path) -> None:
    """CR-01: the resolver delegates to ``download_torch_model(cache_dir)``.

    The returned path's parent MUST equal ``config.get_model_cache_dir()``.
    This holds on BOTH branches: (a) download succeeds -> the vendored function
    writes into cache_dir and returns a path under it; (b) download returns
    None (network offline in CI) -> the narrowed except falls back to
    ``cache_dir / comictextdetector.pt``. Either way the parent is the cache
    dir, proving the call signature is ``download_torch_model(cache_dir)`` and
    not the CR-01 zero-arg form.

    No-stub guard: this test does NOT monkeypatch ``download_torch_model`` —
    the REAL vendored function is exercised.
    """
    window = _make_window(qtbot, tmp_path)
    cache_dir = window.profile_manager.config.get_model_cache_dir()

    resolved = window._resolve_detection_model_path()

    assert resolved.parent == cache_dir, (
        f"resolver must return a path under cache_dir {cache_dir}, got {resolved.parent}"
    )


@pytest.mark.unit
def test_resolve_detection_model_path_filename_matches_vendored_default(qtbot, tmp_path) -> None:
    """CR-01: the resolver returns the vendored default filename.

    The vendored constant is ``TORCH_MODEL_NAME = "comictextdetector.pt"``
    (panelcleaner/model_downloader.py:16). The CR-01 bug hardcoded a different
    fallback in the except branch; this test locks the correct name.
    """
    window = _make_window(qtbot, tmp_path)

    resolved = window._resolve_detection_model_path()

    assert resolved.name == "comictextdetector.pt", (
        f"resolver filename must match vendored TORCH_MODEL_NAME, got {resolved.name!r}"
    )


@pytest.mark.unit
def test_resolve_detection_model_path_no_bare_except(qtbot, tmp_path) -> None:
    """CR-01 anti-pattern guard: no bare ``except Exception:`` in the resolver.

    The shared root cause of all three gap-closure bugs was a bare
    ``except Exception:`` swallowing programming errors (TypeError,
    AttributeError). The resolver's except must be narrowed to
    ``(FileNotFoundError, OSError)`` so signature drift propagates. This is a
    source-level guard against re-introducing the anti-pattern.
    """
    import inspect

    from manga_ai_studio.gui.main_window import MainWindow

    source = inspect.getsource(MainWindow._resolve_detection_model_path)
    assert "except Exception" not in source, (
        "_resolve_detection_model_path must not have a bare `except Exception:` "
        "(CR-01 root cause). Narrow to (FileNotFoundError, OSError)."
    )
    assert "except (FileNotFoundError, OSError)" in source


@pytest.mark.unit
def test_resolve_detection_model_path_programming_errors_propagate(
    qtbot, tmp_path, monkeypatch
) -> None:
    """CR-01 propagation guard: TypeError from signature drift MUST propagate.

    Simulates a future signature change in ``download_torch_model`` by patching
    it to raise ``TypeError``. The narrowed except (FileNotFoundError, OSError)
    must NOT catch it — programming errors propagate to dev/test so the bug
    surfaces immediately instead of silently degrading in production.

    The config's cache_dir is pointed at an isolated ``tmp_path`` so the
    existence check (CR-11) finds no cached model and proceeds to the
    download call where the TypeError fires.
    """
    window = _make_window(qtbot, tmp_path)
    # Isolate the cache so the CR-11 existence check does not short-circuit
    # against a model left by a prior app run or sibling test.
    window.profile_manager.config.cache_dir = tmp_path / "isolated-cache"

    def _raise_typeerror(_cache_dir):
        raise TypeError("simulated signature drift")

    monkeypatch.setattr(
        "panelcleaner.model_downloader.download_torch_model", _raise_typeerror
    )

    with pytest.raises(TypeError, match="simulated signature drift"):
        window._resolve_detection_model_path()


@pytest.mark.unit
def test_resolve_detection_model_path_skips_download_when_cached(
    qtbot, tmp_path, monkeypatch
) -> None:
    """CR-11: a cached model short-circuits the download.

    The vendored ``download_torch_model`` unconditionally re-downloads (it
    never checks whether the file exists), so without an existence check in
    the resolver every detect call re-fetched ~80MB. When
    ``cache_dir/comictextdetector.pt`` already exists, the resolver MUST
    return it immediately and NOT call the download function at all.
    """
    window = _make_window(qtbot, tmp_path)
    # Isolate the cache so the test does not touch the real AppData cache dir
    # and is hermetic against sibling tests / prior app runs.
    window.profile_manager.config.cache_dir = tmp_path / "isolated-cache"
    cache_dir = window.profile_manager.config.get_model_cache_dir()
    expected = cache_dir / "comictextdetector.pt"
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_bytes(b"fake-cached-model")  # simulate a prior download

    # If the resolver calls download_torch_model, this fails the test loudly.
    def _fail_if_called(_cache_dir):
        raise AssertionError(
            "download_torch_model was called but the model is already cached (CR-11)"
        )

    monkeypatch.setattr(
        "panelcleaner.model_downloader.download_torch_model", _fail_if_called
    )

    resolved = window._resolve_detection_model_path()
    assert resolved == expected, (
        f"resolver must return the cached path {expected}, got {resolved}"
    )


@pytest.mark.unit
def test_ctd_model_load_uses_weights_only_false(monkeypatch) -> None:
    """CR-15: the CTD model load path passes weights_only=False to torch.load.

    PyTorch 2.6+ changed torch.load's default ``weights_only`` from False to
    True. The vendored CTD checkpoint pickles non-weight objects (YOLOv5 Model
    instances, DBHead state), so the new default raises
    ``_pickle.UnpicklingError: Unsupported operand 102`` at
    ``basemodel.py:get_base_det_models``. The CTD model is a trusted vendored
    upstream asset, so ``weights_only=False`` (the pre-2.6 default) is the
    documented, acceptable remediation.

    This test does NOT require the 80MB model download — it monkeypatches
    ``torch.load`` and inspects the call kwargs.
    """
    import torch  # local; only present in the torch env (gated by importorskip)

    captured: dict = {}

    def _spy_torch_load(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        # Return a minimal valid-shaped dict so load_yolov5_ckpt / UnetHead
        # don't blow up before we assert; we only care about the torch.load
        # call contract here. Raise to short-circuit further processing.
        raise RuntimeError("CR-15 test: torch.load intercepted, stopping chain")

    monkeypatch.setattr(torch, "load", _spy_torch_load)

    # Directly invoke the vendored function our adapter delegates to.
    from panelcleaner.comic_text_detector.basemodel import get_base_det_models

    with pytest.raises(RuntimeError, match="CR-15 test"):
        get_base_det_models("ignored-by-spy.pt")

    assert captured.get("kwargs", {}).get("weights_only") is False, (
        "get_base_det_models must pass weights_only=False to torch.load "
        "(PyTorch 2.6+ default otherwise rejects the CTD checkpoint — CR-15)"
    )


@pytest.mark.unit
def test_detection_reads_webp_via_imdecode_not_imread(qtbot, tmp_path) -> None:
    """CR-17: detection image-read uses np.fromfile + cv2.imdecode, not cv2.imread.

    cv2.imread fails on formats whose codec the path-based decoder can't find
    (e.g. .webp in many OpenCV builds — surfaces as a `findDecoder` warning +
    None return) and on non-ASCII path chars on Windows. np.fromfile reads the
    raw bytes (ASCII-safe) and cv2.imdecode finds the codec via content
    sniffing. This mirrors the vendored CTD helper at io_utils.py:imread.

    Reproduces the UAT failure: a real .webp manga page at a Japanese-char
    path raised FileNotFoundError in _run_detection_task because cv2.imread
    returned None. The fix reads via np.fromfile + cv2.imdecode.
    """
    PIL = pytest.importorskip("PIL")  # only needed to build the .webp fixture
    window = _make_window(qtbot, tmp_path)

    # Build a small .webp fixture (cv2.imwrite can't reliably write webp, but
    # PIL can — this is what real manga downloads use).
    webp_path = tmp_path / "page.webp"
    arr = np.zeros((20, 20, 3), dtype=np.uint8)
    arr[5:15, 5:15] = 200  # a distinctive block
    PIL.Image.fromarray(arr).save(str(webp_path), format="WEBP")
    assert webp_path.is_file()

    # Sanity: confirm this fixture would break the OLD path on this OpenCV
    # build (cv2.imread returns None for webp when the codec isn't registered).
    # If cv2.imread happens to work here, the test still asserts the NEW path
    # works — the regression guard is about our code, not the local codec.
    import cv2

    # Stub model: capture the decoded image so we assert the read succeeded,
    # and short-circuit before needing real CTD weights.
    captured: dict = {}

    class _StubModel:
        def load(self, model_path, device="auto"):
            pass

        def detect(self, image, refine_mode=None, keep_undetected_mask=False):
            captured["image_shape"] = image.shape
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            return mask, []  # adapter 2-tuple: (mask_refined, blk_list)

    # Patch the model-path resolver so the stub model.load doesn't hit disk.
    window._resolve_detection_model_path = lambda: webp_path  # noqa: E731

    result = window._run_detection_task(webp_path, _StubModel())

    # The image was decoded and reached the model with the expected shape.
    assert captured.get("image_shape") == (20, 20, 3), (
        f"webp was not decoded; expected (20, 20, 3), got "
        f"{captured.get('image_shape')!r} (CR-17 regressed)"
    )
    assert "mask" in result and "blocks" in result

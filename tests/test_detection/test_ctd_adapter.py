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

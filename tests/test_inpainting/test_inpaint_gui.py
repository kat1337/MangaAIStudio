"""GUI tests for the LaMa inpaint worker wiring + result display (plan 01-05 Task 2).

Guards the load-bearing contract: every numpy<->QImage bridge in the inpaint
result-display path MANDATES ``.copy()`` detachment (RESEARCH Pitfall 2,
PATTERNS.md §Shared Pattern 5). The MangaCleaner_GPU
``main_window.py:on_task_finished`` (lines 234-258) is the BUGGY reference —
line 245 builds ``QImage(rgba.data, ...)`` without ``.copy()``, causing
intermittent segfaults when the numpy buffer is garbage-collected before the
QImage is consumed. The regression guard ``test_inpaint_result_display_uses_copy``
locks the fix: mutating the source numpy array after the QImage is stored must
NOT change the displayed image.

The tests use ``unittest.mock`` / monkeypatching + a fake adapter so they run
WITHOUT torch or SimpleLama model weights in CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThreadPool  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow, compute_mask_bbox  # noqa: E402
from manga_ai_studio.gui.worker_thread import Worker, WorkerError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _open_page(window: MainWindow, tmp_path: Path, size: int = 16) -> Path:
    """Open a solid-white page into the window so the canvas has an image."""
    img_path = tmp_path / "page.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    return img_path


def _paint_mask_on_canvas(canvas: EditorCanvas) -> None:
    """Paint a small mask region (a 4x4 block) onto the canvas via set_mask.

    Uses the same path as detection: a grayscale QImage with non-zero pixels.
    """
    mask = QImage(canvas.image_item.pixmap().size(), QImage.Format.Format_Grayscale8)
    mask.fill(0)
    from PySide6.QtGui import QPainter

    painter = QPainter(mask)
    painter.setPen(QColor(255, 255, 255))
    # Paint a 4x4 region at (4,4)-(7,7).
    for x in range(4, 8):
        for y in range(4, 8):
            painter.drawPoint(x, y)
    painter.end()
    canvas.set_mask(mask)


class _FakeInpaintModel:
    """Fake inpaint adapter: records calls, returns a known RGB array.

    Mimics the TorchLamaModel.inpaint contract: takes (image_rgb, mask_binary)
    numpy arrays, returns an (H, W, 3) uint8 RGB array. The returned array is
    a DISTINCT buffer the test can later mutate to prove the canvas detached
    its QImage copy.
    """

    def __init__(self, fill_value: int = 7) -> None:
        self.fill_value = fill_value
        self.calls = []
        # Hold a reference to the returned array so the test can mutate it.
        self.last_returned: np.ndarray | None = None

    def load(self, model_path, device: str = "cpu") -> None:
        self.loaded_path = model_path

    def inpaint(self, image_rgb: np.ndarray, mask_binary: np.ndarray) -> np.ndarray:
        self.calls.append(
            {
                "image": image_rgb,
                "mask": mask_binary,
                "image_is_ndarray": isinstance(image_rgb, np.ndarray),
                "mask_is_ndarray": isinstance(mask_binary, np.ndarray),
            }
        )
        out = np.full(image_rgb.shape, self.fill_value, dtype=np.uint8)
        self.last_returned = out
        return out


# ---------------------------------------------------------------------------
# Test 1: action gating
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_action_disabled_without_mask(qtbot, tmp_path) -> None:
    """Inpaint (C) is disabled when no mask is present, enabled when one is.

    Behavior 1: action state tracks page presence + mask presence + _op_running.
    """
    window = _make_window(qtbot, tmp_path)

    # No page open -> action disabled.
    assert not window.action_inpaint.isEnabled()

    # Open a page -> still disabled (no mask).
    _open_page(window, tmp_path)
    assert window.action_inpaint.isEnabled() is False

    # Paint a mask -> enabled.
    _paint_mask_on_canvas(window.canvas)
    # mask_modified is connected to _refresh_action_states (plan 05 wiring).
    window._refresh_action_states()
    assert window.action_inpaint.isEnabled() is True

    # Simulate an async op running -> disabled again.
    window._op_running = True
    window._refresh_action_states()
    assert window.action_inpaint.isEnabled() is False


# ---------------------------------------------------------------------------
# Test 2: worker dispatch (no Qt touched in the task)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_worker_dispatches_adapter(qtbot, tmp_path, monkeypatch) -> None:
    """The inpaint task calls the adapter with numpy arrays and returns a dict.

    Behavior 2: the worker task touches ONLY numpy + the model (no Qt objects).
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    _paint_mask_on_canvas(window.canvas)

    fake = _FakeInpaintModel()
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: fake,
    )

    # Extract the same inputs the GUI thread would extract.
    image_rgb = window.canvas.get_image_numpy()
    mask_binary = np.zeros((image_rgb.shape[0], image_rgb.shape[1]), dtype=np.uint8)
    mask_binary[4:8, 4:8] = 255

    # Run the task function directly (synchronous) — no QThreadPool needed to
    # prove the task contract.
    result = window._run_inpaint_task(image_rgb, mask_binary, Path("fake.pt"), fake)

    assert isinstance(result, dict)
    assert "image" in result and "bbox" in result
    assert isinstance(result["image"], np.ndarray)
    assert result["image"].shape == image_rgb.shape
    # The adapter was called with numpy arrays (NOT QImage/QPixmap).
    assert len(fake.calls) == 1
    assert fake.calls[0]["image_is_ndarray"] is True
    assert fake.calls[0]["mask_is_ndarray"] is True


# ---------------------------------------------------------------------------
# Test 3: Pitfall-2 regression guard (.copy() discipline)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_result_display_uses_copy(qtbot) -> None:
    """The stored QImage is detached from the numpy buffer (RESEARCH Pitfall 2).

    Behavior 3 / regression guard: after set_image_from_numpy, mutating the
    source numpy array must NOT change the displayed image. This is the
    MangaCleaner_GPU main_window.py:245 fix (which omitted .copy()).
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(_solid_pixmap(8, QColor(0, 0, 0)))

    # Source numpy array the worker would return.
    src = np.full((8, 8, 3), 100, dtype=np.uint8)
    canvas.set_image_from_numpy(src)

    # Snapshot the displayed pixels BEFORE mutation.
    pix_before = canvas.image_item.pixmap().toImage()

    # Mutate the source array (simulating numpy GC + reuse of the buffer).
    src[:] = 250

    # Snapshot AFTER mutation.
    pix_after = canvas.image_item.pixmap().toImage()

    # The displayed image must be UNCHANGED (the .copy() detached the buffer).
    assert pix_before.pixel(0, 0) == pix_after.pixel(0, 0), (
        "Pitfall-2 regression: mutating the source numpy changed the displayed"
        " QImage — .copy() detachment is missing."
    )
    # The stored pixel should be the original fill (100), not the mutation (250).
    r = (pix_before.pixel(0, 0) >> 16) & 0xFF
    assert r == 100, f"expected original fill 100, got {r}"


# ---------------------------------------------------------------------------
# Test 4: result replaces image layer; mask stays visible
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_replaces_image_layer(qtbot) -> None:
    """After set_image_from_numpy, the image differs + has_inpaint_result is True.

    Behavior 4: the mask overlay remains visible (UI-SPEC surface 7).
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(_solid_pixmap(8, QColor(0, 0, 0)))
    # Establish a mask so we can prove it stays visible.
    mask = QImage(8, 8, QImage.Format.Format_Grayscale8)
    mask.fill(255)
    canvas.set_mask(mask)
    assert canvas.mask_item.isVisible()

    original_pixel = canvas.image_item.pixmap().toImage().pixel(0, 0)
    result_rgb = np.full((8, 8, 3), 200, dtype=np.uint8)
    canvas.set_image_from_numpy(result_rgb)
    new_pixel = canvas.image_item.pixmap().toImage().pixel(0, 0)

    assert new_pixel != original_pixel
    assert canvas.has_inpaint_result() is True
    # Mask overlay must remain visible after inpaint (UI-SPEC surface 7).
    assert canvas.mask_item.isVisible() is True


# ---------------------------------------------------------------------------
# Test 5: progress status bar
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_progress_status_bar(qtbot, tmp_path) -> None:
    """During the worker run, status bar reads 'Inpainting… N%' (UI-SPEC §Copy).

    Behavior 5: the 3px progress bar updates and the status-bar left field
    carries the 'Inpainting…' copy.
    """
    window = _make_window(qtbot, tmp_path)

    # Drive the progress handler directly (the worker signal would do this).
    window._on_inpaint_progress((42, "working"))

    assert "42" in window.status_bar_left.text()
    assert "Inpainting" in window.status_bar_left.text()
    assert window.progress_bar.value() == 42


# ---------------------------------------------------------------------------
# Test 6: error chip + critical dialog
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_error_chip(qtbot, tmp_path, monkeypatch) -> None:
    """On a worker error, MainWindow shows the #7a1f1f chip + critical dialog.

    Behavior 6: the dialog copy contains 'Couldn't load the inpainting model.'
    (UI-SPEC §Copywriting).
    """
    window = _make_window(qtbot, tmp_path)

    # Capture the critical dialog text without showing a modal.
    captured = {}

    def _capture_critical(parent, title, text, *a, **k):
        captured["title"] = title
        captured["text"] = text
        return None

    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.QMessageBox.critical", _capture_critical
    )

    # Build a fake WorkerError.
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        exc_type, value, tb = sys.exc_info()
        we = WorkerError(exc_type, value, tb, (), {})

    assert window.error_chip.isHidden()
    window._on_inpaint_error(we)

    assert not window.error_chip.isHidden()
    assert "#7a1f1f" in window.error_chip.styleSheet()
    # The title carries the UI-SPEC §Copywriting copy; the body is the guidance.
    assert "Couldn't load the inpainting model." in captured["title"]
    assert "models/" in captured["text"]


# ---------------------------------------------------------------------------
# Test 7: preview hold button
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_preview_hold_button(qtbot) -> None:
    """The 'Preview (hold)' button swaps original<->inpainted on press/release.

    Behavior 7: btn_preview_hold exists; show_original(True) sets the flag and
    swaps the pixmap to the original; show_original(False) restores the result.
    """
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.set_image(_solid_pixmap(8, QColor(10, 20, 30)))

    # No inpaint result yet -> show_original is a safe no-op on either side.
    canvas.show_original(True)
    assert canvas._showing_original is True
    canvas.show_original(False)
    assert canvas._showing_original is False

    # Now stage an inpaint result so the swap has both sides.
    result_rgb = np.full((8, 8, 3), 200, dtype=np.uint8)
    canvas.set_image_from_numpy(result_rgb)
    inpainted_pix = canvas.image_item.pixmap().toImage().pixel(0, 0)

    # Press: show the original.
    canvas.show_original(True)
    assert canvas._showing_original is True
    original_pix = canvas.image_item.pixmap().toImage().pixel(0, 0)
    # The original pixel differs from the inpainted pixel.
    assert original_pix != inpainted_pix

    # Release: restore the inpainted result.
    canvas.show_original(False)
    assert canvas._showing_original is False
    restored_pix = canvas.image_item.pixmap().toImage().pixel(0, 0)
    assert restored_pix == inpainted_pix


# ---------------------------------------------------------------------------
# Test 8: sticky P toggle
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_preview_sticky_p(qtbot, tmp_path) -> None:
    """View -> Show Original (P) is checkable + toggles show_original.

    Behavior 8: first activation -> show_original(True); second -> False.
    """
    window = _make_window(qtbot, tmp_path)

    assert window.action_show_original.isCheckable()

    calls = []
    window.canvas.show_original = lambda show: calls.append(show)  # type: ignore

    window.action_show_original.setChecked(True)
    assert calls[-1] is True

    window.action_show_original.setChecked(False)
    assert calls[-1] is False


# ---------------------------------------------------------------------------
# Test 9: no confirmation dialog (inpaint is non-destructive)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_no_confirmation_dialog(qtbot, tmp_path, monkeypatch) -> None:
    """Triggering Inpaint does NOT show a confirmation dialog.

    Behavior 9: inpaint is non-destructive (UI-SPEC §Copywriting) — unlike
    detect_text (which confirms Replace Mask), inpaint never calls
    QMessageBox.question.
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    _paint_mask_on_canvas(window.canvas)

    question_calls = []
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.QMessageBox.question",
        lambda *a, **k: question_calls.append(1),
    )
    # Also suppress the worker dispatch so the test doesn't block on a real
    # SimpleLama load — patch the factory to return a fake that errors fast.
    fake = _FakeInpaintModel()
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.backend_factory",
        lambda kind, backend: fake,
    )
    # Patch QThreadPool.start to a no-op so no real worker runs.
    monkeypatch.setattr(
        "manga_ai_studio.gui.main_window.QThreadPool.globalInstance",
        lambda: _NoStartPool(),
    )

    window.inpaint()
    assert question_calls == [], (
        "inpaint() must not invoke QMessageBox.question — it is non-destructive"
    )


class _NoStartPool:
    """A stub QThreadPool whose start() is a no-op (prevents real worker runs)."""

    def start(self, worker, priority=0):
        return None


# ---------------------------------------------------------------------------
# Test 10: image-patch push to history (plan 06 hook)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_inpaint_pushes_image_history(qtbot, tmp_path, monkeypatch) -> None:
    """_on_inpaint_finished pushes the inpainted patch onto the history stack.

    Behavior 10: when self.history is wired, push_image_action is called with
    (x, y, patch_numpy). Phase 1 wires the call site; plan 06 implements the
    real HistoryManager.
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    _paint_mask_on_canvas(window.canvas)

    pushes = []

    class _StubHistory:
        def push_image_action(self, x, y, patch):
            pushes.append((x, y, patch))

    window.history = _StubHistory()

    # Build a known inpaint result + bbox that lands inside the page.
    image_rgb = window.canvas.get_image_numpy()
    result_rgb = np.full(image_rgb.shape, 123, dtype=np.uint8)
    bbox = (4, 4, 4, 4)  # x, y, w, h matching _paint_mask_on_canvas

    window._on_inpaint_finished({"image": result_rgb, "bbox": bbox})

    assert len(pushes) == 1, "history.push_image_action was not called"
    x, y, patch = pushes[0]
    assert x == 4 and y == 4
    assert isinstance(patch, np.ndarray)


# ---------------------------------------------------------------------------
# Bonus: compute_mask_bbox unit contract (pure numpy, no Qt)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_mask_bbox_returns_xywh() -> None:
    """compute_mask_bbox returns (x, y, w, h) for a painted region or None."""
    mask = np.zeros((10, 10), dtype=np.uint8)
    assert compute_mask_bbox(mask) is None

    mask[3:6, 4:7] = 255  # rows 3-5, cols 4-6 -> w=3, h=3
    bbox = compute_mask_bbox(mask)
    assert bbox == (4, 3, 3, 3)

    # Empty / None inputs are safe.
    assert compute_mask_bbox(None) is None
    empty = np.zeros((0, 0), dtype=np.uint8)
    assert compute_mask_bbox(empty) is None

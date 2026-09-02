"""Tests for the OCR Grab tool (quick-260901-wmn) — the 8th strip tool.

Poricom-style screen-grab OCR: selecting the tool arms a fullscreen
selection overlay; dragging a rectangle over ANY on-screen text captures
it, runs manga-ocr off the GUI thread, and copies the recognized text to
the OS clipboard. A small always-on-top floating history window (visible
while the tool is active) lists recent detections; clicking an entry
re-copies it.

Coverage map:
- Task 1 (registration): ToolMode.OCR_GRAB + window action + Tools menu +
  S shortcut + canvas inertness.
- Task 2 (module): ScreenGrabOverlay rubber-band/Esc, grab helpers
  (DPR-safe crop math + detached numpy conversion), OcrGrabHistoryPanel.
- Task 3 (wiring): MainWindow session lifecycle + Worker OCR dispatch +
  clipboard copy + history updates.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QShortcut,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QListWidget,
    QMenu,
    QPushButton,
)

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.mask_editor import ToolMode  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _window(qtbot, tmp_path) -> MainWindow:
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _solid_pixmap(size: int, color: QColor):
    """Build a solid-color QPixmap of the given size (canvas test helper)."""
    from PySide6.QtGui import QPixmap

    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


def _press(canvas, sx: float, sy: float, button=Qt.MouseButton.LeftButton) -> QMouseEvent:
    """Build a mouse-press at viewport coords that map to SCENE (sx, sy)."""
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def _move(canvas, sx: float, sy: float) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(vp),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release(canvas, sx: float, sy: float, button=Qt.MouseButton.LeftButton) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(vp),
        button,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _canvas_with_image(qtbot, size: int = 100) -> EditorCanvas:
    """Build a shown canvas with a solid image + initialized mask."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(300, 300)
    canvas.set_image(_solid_pixmap(size, QColor("white")))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    return canvas


# ---------------------------------------------------------------------------
# Task 1: the 8th tool registration
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_toolmode_ocr_grab_exists_and_stringifies() -> None:
    """ToolMode.OCR_GRAB is the 8th member and its value is "ocr_grab"."""
    assert ToolMode.OCR_GRAB.value == "ocr_grab"
    # 8 exclusive tools total.
    assert len(ToolMode) == 8
    # Screen tool comes last, after the canvas-geometry tools.
    assert list(ToolMode)[-1] is ToolMode.OCR_GRAB


@pytest.mark.gui
def test_main_window_has_ocr_grab_window_action(qtbot, tmp_path) -> None:
    """MainWindow exposes action_tool_ocr_grab: checkable, lives in the Tools
    menu, and triggering it selects the tool everywhere (strip + window)."""
    window = _window(qtbot, tmp_path)
    action = window.action_tool_ocr_grab

    assert action.isCheckable()
    assert action.data() == ToolMode.OCR_GRAB

    # Lives in the Tools menu.
    tools_menu = next(
        m for m in window.menuBar().findChildren(QMenu) if m.title() == "&Tools"
    )
    assert action in tools_menu.actions()

    # Triggering it drives set_active_tool: the strip and the window action
    # follow (this test runs BEFORE Task 3 exists — no session logic needed).
    action.trigger()
    QApplication.processEvents()
    assert window.tools_strip.active_tool() == ToolMode.OCR_GRAB
    assert action.isChecked()
    assert window.canvas.current_tool == ToolMode.OCR_GRAB


@pytest.mark.gui
def test_s_shortcut_activates_ocr_grab(qtbot, tmp_path) -> None:
    """The S QShortcut on the window activates OCR Grab (mirrors the
    test_main_window_tool_shortcuts registration audit)."""
    window = _window(qtbot, tmp_path)

    shortcuts = window.findChildren(QShortcut)
    keys = {s.key().toString().upper() for s in shortcuts}
    for key in ("V", "B", "R", "L", "E", "O", "G", "S"):
        assert key in keys, f"missing tool shortcut {key}"

    s_shortcut = next(
        s for s in shortcuts if s.key().toString().upper() == "S"
    )
    s_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.canvas.current_tool == ToolMode.OCR_GRAB
    assert window.tools_strip.active_tool() == ToolMode.OCR_GRAB
    assert window.action_tool_ocr_grab.isChecked()


@pytest.mark.gui
def test_canvas_treats_ocr_grab_as_inert(qtbot) -> None:
    """With OCR_GRAB active a left press+release on the page paints NOTHING
    and arms NO crop drag — the press falls through to the base view
    (Move/Pan-style inert behavior)."""
    canvas = _canvas_with_image(qtbot, 100)
    assert canvas.has_mask()  # the paint gate needs a mask to trip

    canvas.set_tool(ToolMode.OCR_GRAB)
    QApplication.processEvents()

    # No brush-circle cursor for non-PAINT_TOOLS.
    assert canvas.current_tool == ToolMode.OCR_GRAB

    # A full press-move-release paints nothing and arms nothing.
    canvas.mousePressEvent(_press(canvas, 10, 10))
    canvas.mouseMoveEvent(_move(canvas, 90, 80))
    canvas.mouseReleaseEvent(_release(canvas, 90, 80))
    QApplication.processEvents()

    assert canvas._is_painting is False
    assert canvas._crop_drag_active is False
    assert canvas._crop_rect is None
    assert canvas.has_mask_content() is False  # mask bytes unchanged

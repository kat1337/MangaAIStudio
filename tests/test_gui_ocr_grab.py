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
    QPainter,
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
    # follow. (Post-Task-3 the selection also starts a grab session — the
    # switch back to MOVE at the end closes it.)
    action.trigger()
    QApplication.processEvents()
    assert window.tools_strip.active_tool() == ToolMode.OCR_GRAB
    assert action.isChecked()
    assert window.canvas.current_tool == ToolMode.OCR_GRAB

    # Switch away: the session tears down (panel hidden, overlay closed).
    window.set_active_tool(ToolMode.MOVE)
    QApplication.processEvents()
    assert window.ocr_grab_panel.isVisible() is False
    assert window._ocr_grab_overlay is None


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

    # Session teardown on switch-away (post-Task-3 the shortcut starts a
    # live grab session).
    window.set_active_tool(ToolMode.MOVE)
    QApplication.processEvents()
    assert window._ocr_grab_overlay is None


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


# ---------------------------------------------------------------------------
# Task 2: ScreenGrabOverlay (rect picker)
# ---------------------------------------------------------------------------


def _overlay(qtbot):
    """Build (shown) a grab overlay for the primary screen."""
    from manga_ai_studio.gui.ocr_grab import ScreenGrabOverlay

    screen = QApplication.primaryScreen()
    overlay = ScreenGrabOverlay(screen)
    qtbot.addWidget(overlay)
    overlay.show()
    QApplication.processEvents()
    return overlay


def _raw_mouse(widget, etype: QEvent.Type, x: float, y: float, button) -> QMouseEvent:
    """Synthetic mouse event at widget-LOCAL coords (5-arg ctor pattern)."""
    return QMouseEvent(etype, QPointF(x, y), button, button,
                       Qt.KeyboardModifier.NoModifier)


@pytest.mark.gui
def test_overlay_drag_emits_normalized_rect_once_and_closes(qtbot) -> None:
    """Press/move/release emits EXACTLY one region_selected carrying the
    normalized rect (negative drags normalized to positive w/h) and the
    overlay closes."""
    overlay = _overlay(qtbot)
    assert overlay.isVisible()

    selected: list[QRect] = []
    overlay.region_selected.connect(selected.append)

    # Right-to-left, bottom-up drag -> must normalize.
    overlay.mousePressEvent(_raw_mouse(
        overlay, QEvent.Type.MouseButtonPress, 200, 150,
        Qt.MouseButton.LeftButton))
    overlay.mouseMoveEvent(_raw_mouse(
        overlay, QEvent.Type.MouseMove, 60, 90, Qt.MouseButton.NoButton))
    overlay.mouseReleaseEvent(_raw_mouse(
        overlay, QEvent.Type.MouseButtonRelease, 60, 90,
        Qt.MouseButton.LeftButton))
    QApplication.processEvents()

    assert len(selected) == 1
    rect = selected[0]
    assert rect.width() > 0 and rect.height() > 0  # normalized
    assert (rect.x(), rect.y()) == (60, 90)
    assert (rect.width(), rect.height()) == (140, 60)
    assert overlay.isVisible() is False  # closed after release


@pytest.mark.gui
def test_overlay_esc_cancels_and_closes(qtbot) -> None:
    """An Esc keypress emits selection_cancelled (no region_selected) and
    closes the overlay."""
    overlay = _overlay(qtbot)

    cancelled: list[bool] = []
    selected: list[QRect] = []
    overlay.selection_cancelled.connect(lambda: cancelled.append(True))
    overlay.region_selected.connect(selected.append)

    overlay.mousePressEvent(_raw_mouse(
        overlay, QEvent.Type.MouseButtonPress, 10, 10,
        Qt.MouseButton.LeftButton))
    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                    Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(esc)
    QApplication.processEvents()

    assert cancelled == [True]
    assert selected == []
    assert overlay.isVisible() is False


@pytest.mark.gui
def test_overlay_click_without_drag_emits_degenerate_rect(qtbot) -> None:
    """A click without a drag emits the degenerate origin rect — the caller
    decides (MainWindow ignores <1px)."""
    overlay = _overlay(qtbot)

    selected: list[QRect] = []
    overlay.region_selected.connect(selected.append)

    overlay.mousePressEvent(_raw_mouse(
        overlay, QEvent.Type.MouseButtonPress, 50, 60,
        Qt.MouseButton.LeftButton))
    overlay.mouseReleaseEvent(_raw_mouse(
        overlay, QEvent.Type.MouseButtonRelease, 50, 60,
        Qt.MouseButton.LeftButton))
    QApplication.processEvents()

    assert len(selected) == 1
    assert selected[0].width() == 0 and selected[0].height() == 0
    assert overlay.isVisible() is False


@pytest.mark.gui
def test_overlay_geometries_match_screen_and_stores_no_pixels(qtbot) -> None:
    """The overlay covers its screen's geometry and never stores grabbed
    pixels (rect picker only — no image/pixmap members)."""
    from manga_ai_studio.gui.ocr_grab import ScreenGrabOverlay

    screen = QApplication.primaryScreen()
    overlay = ScreenGrabOverlay(screen)
    qtbot.addWidget(overlay)

    assert overlay.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert overlay.windowFlags() & Qt.WindowType.Tool
    assert overlay.geometry() == screen.geometry()
    # Rect-picker contract: no pixel storage attributes on the instance.
    for forbidden in ("_image", "_pixmap", "_grab", "_pixels"):
        assert not hasattr(overlay, forbidden)


@pytest.mark.gui
def test_overlay_renders_without_dim_veil_when_idle(qtbot) -> None:
    """Poricom parity: NO dim veil — an idle overlay renders at most the
    invisible 1/255 hit-test anchor (Windows per-pixel hit-testing makes a
    fully transparent window CLICK-THROUGH: the drag never reaches it).
    Alpha must stay imperceptible (<= 1/255), never the old 90/255 veil."""
    overlay = _overlay(qtbot)
    image = overlay.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    xs = list(range(0, image.width(), 64)) + [image.width() - 1]
    ys = list(range(0, image.height(), 64)) + [image.height() - 1]
    too_opaque = [
        (x, y)
        for y in ys
        for x in xs
        if image.pixelColor(x, y).alpha() > 1
    ]
    assert too_opaque == []


@pytest.mark.gui
def test_overlay_drag_paints_only_the_selection_border(qtbot) -> None:
    """Mid-drag the ONLY painted pixels above the hit-test anchor are the
    accent selection border — the selection interior and the rest of the
    screen stay imperceptible (no dim, no outside-darkening)."""
    overlay = _overlay(qtbot)

    overlay.mousePressEvent(_raw_mouse(
        overlay, QEvent.Type.MouseButtonPress, 100, 100,
        Qt.MouseButton.LeftButton))
    overlay.mouseMoveEvent(_raw_mouse(
        overlay, QEvent.Type.MouseMove, 200, 150, Qt.MouseButton.NoButton))
    # NO release — grab() renders the LIVE mid-drag paint synchronously.

    image = overlay.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)

    # The selection interior is untouched (anchor alpha at most)...
    for x, y in ((150, 125), (120, 110), (180, 140)):
        assert image.pixelColor(x, y).alpha() <= 1
    # ...and the screen far from the selection is untouched (no veil)...
    for x, y in ((10, 10), (300, 200), (400, 300)):
        assert image.pixelColor(x, y).alpha() <= 1
    # ...but the border IS stroked: scan a band around the top edge.
    border_hits = [
        (x, y)
        for x in range(105, 200, 5)
        for y in range(97, 104)
        if image.pixelColor(x, y).alpha() > 1
    ]
    assert border_hits, "selection border not painted while dragging"


# ---------------------------------------------------------------------------
# Task 2: grab + conversion helpers
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_crop_scaled_scales_by_dpr() -> None:
    """_crop_scaled multiplies x/y/w/h by the DPR: a 50x25 logical rect at
    dpr 2 crops the 100x50 device-pixel image fully."""
    from manga_ai_studio.gui.ocr_grab import _crop_scaled

    img = QImage(100, 50, QImage.Format.Format_RGB888)
    img.fill(QColor(10, 20, 30))

    out = _crop_scaled(img, QRect(0, 0, 50, 25), 2.0)
    assert not out.isNull()
    assert (out.width(), out.height()) == (100, 50)
    assert out.format() == QImage.Format.Format_RGB888


@pytest.mark.gui
def test_crop_scaled_intersects_bounds_and_handles_offset() -> None:
    """A selection extending past the image is clamped to the bounds; a
    1x dpr crop at an offset lands on the requested pixels."""
    from manga_ai_studio.gui.ocr_grab import _crop_scaled

    img = QImage(40, 20, QImage.Format.Format_RGB888)
    img.fill(QColor(0, 0, 0))
    # Paint a 10x10 red block at (5, 5).
    painter = QPainter(img)
    painter.fillRect(5, 5, 10, 10, QColor(255, 0, 0))
    painter.end()

    # 1x dpr, offset crop over the red block.
    out = _crop_scaled(img, QRect(5, 5, 10, 10), 1.0)
    assert (out.width(), out.height()) == (10, 10)
    c = out.pixelColor(0, 0)
    assert (c.red(), c.green(), c.blue()) == (255, 0, 0)

    # Rect extending past the right/bottom edges -> clamped to bounds.
    out2 = _crop_scaled(img, QRect(30, 10, 50, 50), 1.0)
    assert not out2.isNull()
    assert out2.width() == 10  # 40 - 30
    assert out2.height() == 10  # 20 - 10


@pytest.mark.gui
def test_crop_scaled_degenerate_inputs_return_null() -> None:
    """A null image or a <1px rect yields a null QImage (caller shows a
    hint, never a crash)."""
    from manga_ai_studio.gui.ocr_grab import _crop_scaled

    img = QImage(40, 20, QImage.Format.Format_RGB888)
    assert _crop_scaled(QImage(), QRect(0, 0, 10, 10), 1.0).isNull()
    assert _crop_scaled(img, QRect(0, 0, 0, 10), 1.0).isNull()
    assert _crop_scaled(img, QRect(0, 0, 10, 0), 1.0).isNull()


@pytest.mark.gui
def test_grab_screen_region_smoke(qtbot) -> None:
    """Live smoke: a 1x1 grab of the primary screen returns a non-null
    RGB888 QImage (no geometry assertions — screen content varies)."""
    from manga_ai_studio.gui.ocr_grab import grab_screen_region

    screen = QApplication.primaryScreen()
    out = grab_screen_region(screen, QRect(10, 10, 1, 1))
    assert not out.isNull()
    assert out.format() == QImage.Format.Format_RGB888


def test_qimage_to_rgb_array_exact_pixels_and_detached() -> None:
    """Stride-safe conversion: a padded-stride RGB888 image converts to the
    exact (h, w, 3) uint8 pixels, and mutating the array leaves the QImage
    untouched (detached — Pitfall 2 payload discipline)."""
    import numpy as np

    from manga_ai_studio.gui.ocr_grab import qimage_to_rgb_array

    # 3x2 RGB888: scanline is 9 bytes -> Qt pads to 12 (4-byte alignment).
    img = QImage(3, 2, QImage.Format.Format_RGB888)
    assert img.bytesPerLine() > img.width() * 3, "expected padded stride"
    colors = [
        QColor(255, 0, 0), QColor(0, 255, 0), QColor(0, 0, 255),
        QColor(255, 255, 0), QColor(255, 0, 255), QColor(0, 255, 255),
    ]
    for i, c in enumerate(colors):
        img.setPixelColor(i % 3, i // 3, c)

    arr = qimage_to_rgb_array(img)
    assert arr.shape == (2, 3, 3)
    assert arr.dtype == np.uint8
    expected = np.array(
        [
            [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
            [[255, 255, 0], [255, 0, 255], [0, 255, 255]],
        ],
        dtype=np.uint8,
    )
    assert (arr == expected).all()

    # Detached: mutating the array never mutates the QImage.
    arr[0, 0, 0] = 42
    c = img.pixelColor(0, 0)
    assert c.red() == 255


def test_qimage_to_rgb_array_null_image() -> None:
    """A null QImage converts to an empty (0, 0, 3) array — never a
    ValueError from reshaping a 0-byte buffer."""
    import numpy as np

    from manga_ai_studio.gui.ocr_grab import qimage_to_rgb_array

    arr = qimage_to_rgb_array(QImage())
    assert arr.shape == (0, 0, 3)
    assert arr.dtype == np.uint8


# ---------------------------------------------------------------------------
# Task 2: OcrGrabHistoryPanel (pure follower)
# ---------------------------------------------------------------------------


def _panel(qtbot):
    from manga_ai_studio.gui.ocr_grab import OcrGrabHistoryPanel

    panel = OcrGrabHistoryPanel()
    qtbot.addWidget(panel)
    return panel


@pytest.mark.gui
def test_panel_is_hidden_tool_window_by_default(qtbot) -> None:
    """The panel is a titled always-on-top Tool window, created hidden (it
    must never appear at startup) with a list, a capture button, and a hint
    label."""
    panel = _panel(qtbot)
    assert panel.windowFlags() & Qt.WindowType.Tool
    assert panel.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert panel.windowTitle() == "OCR Grab"
    assert panel.isVisible() is False  # created hidden
    assert panel.findChild(QListWidget) is not None
    assert panel.findChild(QPushButton) is not None
    assert panel.findChild(QPushButton).text() == "New capture"


@pytest.mark.gui
def test_panel_add_entry_prepends_most_recent_first(qtbot) -> None:
    """add_entry prepends (most recent first); entries() round-trips the
    full text; the display shows a truncated one-line preview."""
    panel = _panel(qtbot)
    panel.add_entry("first text")
    panel.add_entry("second text")

    assert panel.entries() == ["second text", "first text"]
    lst = panel.findChild(QListWidget)
    assert lst.item(0).text().startswith("second")
    assert lst.count() == 2


@pytest.mark.gui
def test_panel_caps_history_at_20(qtbot) -> None:
    """The list never exceeds MAX_HISTORY=20 — the OLDEST entries drop off
    the tail."""
    from manga_ai_studio.gui.ocr_grab import OcrGrabHistoryPanel

    panel = _panel(qtbot)
    for i in range(25):
        panel.add_entry(f"text {i}")

    assert panel.entries() == [f"text {i}" for i in range(24, 4, -1)]
    assert len(panel.entries()) == OcrGrabHistoryPanel.MAX_HISTORY == 20


@pytest.mark.gui
def test_panel_rejects_empty_whitespace_text(qtbot) -> None:
    """Empty or whitespace-only text never creates an entry."""
    panel = _panel(qtbot)
    panel.add_entry("")
    panel.add_entry("   \n\t ")
    assert panel.entries() == []


@pytest.mark.gui
def test_panel_entry_click_emits_full_text(qtbot) -> None:
    """Clicking an entry emits entry_copy_requested with the entry's FULL
    text (not the truncated preview)."""
    panel = _panel(qtbot)
    long_text = "word " * 30  # way past the ~40-char preview
    panel.add_entry(long_text)

    copied: list[str] = []
    panel.entry_copy_requested.connect(copied.append)

    lst = panel.findChild(QListWidget)
    assert lst.item(0).text() != long_text  # display IS truncated
    lst.itemClicked.emit(lst.item(0))

    assert copied == [long_text]


@pytest.mark.gui
def test_panel_capture_button_emits_capture_requested(qtbot) -> None:
    """The New capture button fires capture_requested."""
    panel = _panel(qtbot)
    fired: list[bool] = []
    panel.capture_requested.connect(lambda: fired.append(True))

    panel.findChild(QPushButton).click()
    assert fired == [True]


# ---------------------------------------------------------------------------
# Task 3: MainWindow wiring — clipboard, dispatch, lifecycle, errors
# ---------------------------------------------------------------------------


def _clear_clipboard(text: str) -> None:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.clipboard().setText(text)


def _clipboard_text() -> str:
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.clipboard().text()


def _clipboard_text_eventually(qtbot, expected: str, attempts: int = 20) -> bool:
    """Read the real OS clipboard with SPACED retries (50 ms apart).

    Rapid back-to-back polling of the Windows clipboard can transiently
    starve ("Unable to obtain clipboard" — the OS refuses the open while a
    clipboard manager holds it), so the read loop backs off between
    attempts instead of hammering. Returns True once the expected text is
    observed.
    """
    for _ in range(attempts):
        if _clipboard_text() == expected:
            return True
        qtbot.wait(50)
    return _clipboard_text() == expected


@pytest.mark.gui
def test_grab_finished_copies_to_clipboard_and_history(qtbot, tmp_path) -> None:
    """A successful result copies the text to the OS clipboard, prepends it
    to the history panel, and flashes a copied status. The history click
    path re-copies through the window handler."""
    window = _window(qtbot, tmp_path)
    _clear_clipboard("sentinel")

    window._on_ocr_grab_finished({"text": "テスト", "source": "screen_grab"})

    assert _clipboard_text_eventually(qtbot, "テスト")
    assert window.ocr_grab_panel.entries()[0] == "テスト"
    assert "copied" in window.status_bar_left.text().lower()

    # Empty/whitespace text: NO clipboard write, NO history entry.
    window._on_ocr_grab_finished({"text": "  \n ", "source": "screen_grab"})
    assert _clipboard_text_eventually(qtbot, "テスト")
    assert window.ocr_grab_panel.entries() == ["テスト"]
    assert "no text recognized" in window.status_bar_left.text().lower()


@pytest.mark.gui
def test_grab_history_click_recopies_older_entry(qtbot, tmp_path) -> None:
    """Two entries in the panel; activating the OLDER one re-copies the
    older text to the clipboard (add_entry prepends — most recent first)."""
    window = _window(qtbot, tmp_path)
    window.ocr_grab_panel.add_entry("older text")
    window.ocr_grab_panel.add_entry("newer text")  # prepended -> index 0
    _clear_clipboard("sentinel")

    lst = window.ocr_grab_panel.findChild(QListWidget)
    assert lst.item(0).data(Qt.ItemDataRole.UserRole) == "newer text"
    lst.itemClicked.emit(lst.item(1))  # index 1 = the older entry

    assert _clipboard_text_eventually(qtbot, "older text")
    assert "copied from history" in window.status_bar_left.text().lower()


@pytest.mark.gui
def test_grab_dispatch_end_to_end_with_stubs(qtbot, tmp_path, monkeypatch) -> None:
    """Full dispatch path with the model + grab + OS clipboard stubbed:
    region selection grabs (stub), converts, runs the (stubbed) Worker OCR
    off-thread, copies to the clipboard, records history, and clears
    _op_running. The clipboard is a recorder stub — rapid access to the REAL
    OS clipboard from an async test transiently starves on Windows
    ("Unable to obtain clipboard"); the synchronous clipboard behavior is
    covered by the handler/recopy tests against the real clipboard."""
    import manga_ai_studio.gui.main_window as mw_module

    class _FakeClipboard:
        def __init__(self) -> None:
            self._text = ""

        def setText(self, text: str) -> None:
            self._text = text

        def text(self) -> str:
            return self._text

    class _FakeGuiApp:
        _clip = _FakeClipboard()

        @classmethod
        def clipboard(cls) -> _FakeClipboard:
            return cls._clip

    window = _window(qtbot, tmp_path)
    # No overlay during selection — the dispatch test drives the handler
    # directly.
    monkeypatch.setattr(MainWindow, "_start_ocr_grab_session", lambda self: None)
    monkeypatch.setattr(
        MainWindow,
        "_run_ocr_grab_task",
        lambda self, region_arr, model, progress_callback=None, abort_flag=None: {
            "text": "スクリーン",
            "source": "screen_grab",
        },
    )
    synthetic = QImage(4, 4, QImage.Format.Format_RGB888)
    synthetic.fill(QColor(200, 200, 200))
    # The call site resolves the names in the main_window namespace (a
    # module-level `from ... import` — patch THERE, the module attr too for
    # belt and suspenders).
    monkeypatch.setattr(
        mw_module, "grab_screen_region", lambda screen, rect: synthetic
    )
    monkeypatch.setattr(mw_module, "QGuiApplication", _FakeGuiApp)
    import manga_ai_studio.gui.ocr_grab as og_module

    monkeypatch.setattr(
        og_module, "grab_screen_region", lambda screen, rect: synthetic
    )

    window.set_active_tool(ToolMode.OCR_GRAB)
    window._on_grab_region_selected(QRect(10, 10, 120, 40))

    # Wait on the IN-PROCESS conditions: finished-driven cleanup, the
    # clipboard write, and the history entry are all deterministic under the
    # event loop.
    qtbot.waitUntil(lambda: window._op_running is False, timeout=10000)
    assert _FakeGuiApp._clip.text() == "スクリーン"
    assert window.ocr_grab_panel.entries()[0] == "スクリーン"


@pytest.mark.gui
def test_grab_region_selected_closes_overlay_before_grab(qtbot, tmp_path, monkeypatch) -> None:
    """The overlay is closed (and the reference cleared) BEFORE the grab —
    it can never appear in its own capture; a degenerate rect skips the
    grab entirely with a status hint."""
    import manga_ai_studio.gui.main_window as mw_module

    window = _window(qtbot, tmp_path)
    grabbed: list = []

    class _FakeOverlay:
        def close(self) -> None:
            grabbed.append("closed")

    window._ocr_grab_overlay = _FakeOverlay()
    monkeypatch.setattr(
        mw_module,
        "grab_screen_region",
        lambda screen, rect: grabbed.append(rect) or QImage(),
    )

    # Degenerate rect: hint, NO grab, overlay still closed first.
    window._on_grab_region_selected(QRect(5, 5, 0, 0))
    assert grabbed == ["closed"]
    assert "drag a rectangle" in window.status_bar_left.text().lower()

    # Valid rect: grab happens AFTER the close.
    grabbed.clear()
    window._ocr_grab_overlay = _FakeOverlay()
    window._on_grab_region_selected(QRect(5, 5, 30, 10))
    assert grabbed[0] == "closed"  # close strictly before grab
    assert window._ocr_grab_overlay is None


@pytest.mark.gui
def test_grab_session_lifecycle(qtbot, tmp_path) -> None:
    """Selecting OCR Grab shows the panel + arms a live overlay; switching
    away hides the panel + closes the overlay; re-selecting starts a NEW
    overlay instance (the old one closed) — one session at a time."""
    window = _window(qtbot, tmp_path)

    window.set_active_tool(ToolMode.OCR_GRAB)
    QApplication.processEvents()
    assert window.ocr_grab_panel.isVisible()
    overlay1 = window._ocr_grab_overlay
    assert overlay1 is not None
    assert overlay1.isVisible()

    window.set_active_tool(ToolMode.MOVE)
    QApplication.processEvents()
    assert window.ocr_grab_panel.isVisible() is False
    assert window._ocr_grab_overlay is None
    assert overlay1.isVisible() is False

    # Re-selection starts a NEW overlay (the re-trigger path).
    window.set_active_tool(ToolMode.OCR_GRAB)
    QApplication.processEvents()
    overlay2 = window._ocr_grab_overlay
    assert overlay2 is not None
    assert overlay2 is not overlay1
    assert overlay1.isVisible() is False
    assert overlay2.isVisible()

    # Teardown for qtbot hygiene.
    window.set_active_tool(ToolMode.MOVE)
    QApplication.processEvents()
    assert window._ocr_grab_overlay is None


@pytest.mark.gui
def test_grab_dispatch_skipped_while_op_running(qtbot, tmp_path, monkeypatch) -> None:
    """The _op_running gate skips the dispatch with a status note (no worker
    pileup — the T-4-14 pattern) and never overwrites the clipboard."""
    window = _window(qtbot, tmp_path)
    window._op_running = True
    _clear_clipboard("sentinel")

    window._on_grab_region_selected(QRect(10, 10, 120, 40))

    assert _clipboard_text() == "sentinel"
    assert window._op_running is True
    assert "another operation" in window.status_bar_left.text().lower()


@pytest.mark.gui
def test_grab_error_path_shows_chip_and_cleanup(qtbot, tmp_path) -> None:
    """_on_ocr_grab_error logs + shows the error chip (no crash, no modal);
    the finished-driven cleanup clears _op_running afterwards."""
    import sys

    from manga_ai_studio.gui.worker_thread import WorkerError

    window = _window(qtbot, tmp_path)
    window.show()  # the error chip is a status-bar child — needs a shown window
    QApplication.processEvents()
    window._op_running = True
    try:
        raise RuntimeError("model exploded")
    except RuntimeError:
        worker_error = WorkerError(*sys.exc_info())

    window._on_ocr_grab_error(worker_error)
    assert window.error_chip.isVisible()
    assert window.error_chip.text() == "Screen OCR error"

    window._on_ocr_grab_cleanup((None, {}))
    assert window._op_running is False
    assert window.progress_bar.isVisible() is False


@pytest.mark.gui
def test_grab_capture_button_starts_new_session(qtbot, tmp_path) -> None:
    """The panel's New capture button goes through the window handler and
    re-arms a NEW overlay (one session at a time)."""
    window = _window(qtbot, tmp_path)
    window.set_active_tool(ToolMode.OCR_GRAB)
    QApplication.processEvents()
    overlay1 = window._ocr_grab_overlay

    window.ocr_grab_panel.capture_requested.emit()
    QApplication.processEvents()
    overlay2 = window._ocr_grab_overlay
    assert overlay2 is not overlay1
    assert overlay1.isVisible() is False
    assert overlay2.isVisible()

    window.set_active_tool(ToolMode.MOVE)  # teardown

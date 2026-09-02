"""OCR Grab building blocks (quick-260901-wmn) — the 8th tool's screen layer.

Poricom-style screen-grab OCR, split into pure pieces plus the floating
history window:

- :class:`ScreenGrabOverlay` — a fullscreen, topmost rubber-band RECT
  picker. It NEVER stores or returns grabbed pixels: it is only a rect
  picker (T-QG-01), which keeps it trivially testable offscreen.
- :func:`grab_screen_region` (+ the pure :func:`_crop_scaled` math) and
  :func:`qimage_to_rgb_array` — the DPI-aware screen grab and the
  stride-safe, detached numpy conversion (RESEARCH Pitfall 2 payload
  discipline; Windows scanlines are 4-byte-aligned so ``bytesPerLine`` may
  exceed ``width * 3`` — a naive flat reshape is wrong there).
- :class:`OcrGrabHistoryPanel` — the small always-on-top floating history
  window. A PURE FOLLOWER (the InspectorPanel precedent, plan 04-04): it
  holds NO clipboard/OCR business logic and only emits signals.

MainWindow (the only consumer) owns the session lifecycle: overlay ->
grab -> Worker OCR -> clipboard + history. There are deliberately NO
main_window or OCR/model imports here — the module stays importable
headless.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QScreen
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Dim veil over the whole screen while the grab overlay is up (subtle — the
# user must still READ the text underneath to aim the rectangle).
_DIM_COLOR = QColor(0, 0, 0, 90)
# Darker fill OUTSIDE the current selection so the kept region pops.
_OUTSIDE_COLOR = QColor(0, 0, 0, 120)
# Selection border in the strip-highlight accent token (#00d4ff).
_ACCENT_COLOR = QColor(0, 212, 255)

# History panel geometry + cap (plan contract: compact ~280x360, 20 entries).
_PANEL_WIDTH = 280
_PANEL_HEIGHT = 360
_PREVIEW_CHARS = 40


class ScreenGrabOverlay(QWidget):
    """Fullscreen screen-selection rubber-band overlay (Poricom-style).

    A frameless, always-on-top ``Qt.Tool`` window covering one screen's
    geometry. A left-drag defines the selection rect; release emits
    :attr:`region_selected` (normalized — a drag started right-to-left or
    bottom-up yields a positive w/h) and closes. Esc emits
    :attr:`selection_cancelled` and closes. A click without a drag emits a
    DEGENERATE rect — the caller decides what to do with it (MainWindow
    ignores <1px with a status hint).

    The overlay is shown via plain ``show()`` — never a modal ``exec()``
    (the history panel must stay interactive while the overlay is up).

    T-QG-01: the overlay never grabs, stores, or returns pixels. It closes
    BEFORE any grab happens (MainWindow-side ordering) so it can never
    photograph itself.
    """

    # Emitted on left-release with the normalized selection rect (screen
    # coordinates — the overlay's geometry IS the screen geometry).
    region_selected = Signal(QRect)
    # Emitted on Esc (user aborts the grab session's current overlay).
    selection_cancelled = Signal()

    def __init__(self, screen: QScreen, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._screen = screen
        self._drag_origin: QPoint | None = None
        self._dragging = False
        self._selection = QRect()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Fullscreen over the target screen (logical coordinates — Qt maps
        # the window onto that screen's device pixels itself).
        self.setGeometry(screen.geometry())

    # -------------------------------------------------------------- events
    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Left-press starts the rubber band from that point."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position().toPoint()
            self._dragging = True
            # 0x0 at the origin: a click without a drag releases a DEGENERATE
            # rect (the caller decides — MainWindow ignores <1px).
            self._selection = QRect(self._drag_origin, QSize(0, 0))
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Drag updates the live selection (normalized for painting)."""
        if self._dragging and self._drag_origin is not None:
            self._selection = self._rect_to(event.position().toPoint())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """Left-release emits the normalized rect and closes.

        A click without a drag emits the degenerate origin rect — the caller
        decides (MainWindow flashes a hint for <1px).
        """
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            rect = self._selection.normalized()
            self._dragging = False
            self._drag_origin = None
            self.region_selected.emit(rect)
            self.close()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Esc cancels the selection and closes."""
        if event.key() == Qt.Key.Key_Escape:
            self._dragging = False
            self._drag_origin = None
            self.selection_cancelled.emit()
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- private
    def _rect_to(self, point: QPoint) -> QRect:
        """Selection rect from the drag origin to ``point``, normalized.

        Built as origin + explicit QSize (NOT the two-QPoint corners
        constructor, which is bottom-right-INCLUSIVE and skews normalized
        drags by one pixel). A negative drag (right-to-left / bottom-up)
        normalizes to positive w/h.
        """
        return QRect(
            self._drag_origin,
            QSize(point.x() - self._drag_origin.x(), point.y() - self._drag_origin.y()),
        ).normalized()

    # -------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802
        """Dim the whole screen; outside the live selection darker; stroke
        the selection in the accent color. Nothing selected yet = plain dim."""
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), _DIM_COLOR)
            if self._dragging and not self._selection.isNull():
                sel = self._selection
                # Four rects covering everything OUTSIDE the selection.
                painter.fillRect(QRect(0, 0, self.width(), sel.top()), _OUTSIDE_COLOR)
                painter.fillRect(
                    QRect(0, sel.bottom() + 1, self.width(),
                          self.height() - sel.bottom() - 1),
                    _OUTSIDE_COLOR,
                )
                painter.fillRect(
                    QRect(0, sel.top(), sel.left(), sel.height()), _OUTSIDE_COLOR
                )
                painter.fillRect(
                    QRect(sel.right() + 1, sel.top(),
                          self.width() - sel.right() - 1, sel.height()),
                    _OUTSIDE_COLOR,
                )
                pen = QPen(_ACCENT_COLOR)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawRect(sel)
        finally:
            painter.end()


def _crop_scaled(image: QImage, rect: QRect, dpr: float) -> QImage:
    """Crop ``image`` at ``rect`` (logical px) scaled by ``dpr`` (pure math).

    Windows HiDPI: ``QScreen.grabWindow(0)`` returns DEVICE pixels while the
    overlay selection is in LOGICAL coordinates — the crop rect is therefore
    scaled by ``screen.devicePixelRatio()`` (x/y/w/h multiplied, rounded to
    ints) before cropping. The crop is intersected with the image bounds so
    an off-edge selection can never request a QPainter-out-of-range copy.
    Degenerate inputs (null image, <1px rect, empty intersection) return a
    null QImage — the caller shows a hint, never a crash.
    """
    if image.isNull() or rect.width() < 1 or rect.height() < 1:
        return QImage()
    x = round(rect.x() * dpr)
    y = round(rect.y() * dpr)
    w = round(rect.width() * dpr)
    h = round(rect.height() * dpr)
    bounds = QRect(0, 0, image.width(), image.height())
    crop = QRect(x, y, w, h).intersected(bounds)
    if crop.width() < 1 or crop.height() < 1:
        return QImage()
    # copy() first (detached, device-pixel crop), then normalize to RGB888
    # for the numpy conversion.
    return image.copy(crop).convertToFormat(QImage.Format.Format_RGB888)


def grab_screen_region(screen: QScreen, rect: QRect) -> QImage:
    """Grab ``rect`` (logical px) from ``screen`` and return an RGB QImage.

    ``QScreen.grabWindow(0)`` grabs that screen (the overlay is launched on
    ``MainWindow.screen()`` and has already closed — it can never appear in
    its own capture). The DPR math lives in :func:`_crop_scaled`. A
    degenerate rect returns a null QImage.
    """
    if rect.width() < 1 or rect.height() < 1:
        return QImage()
    pixmap = screen.grabWindow(0)
    return _crop_scaled(pixmap.toImage(), rect, screen.devicePixelRatio())


def qimage_to_rgb_array(image: QImage) -> np.ndarray:
    """Convert a Format_RGB888 QImage to a DETACHED (h, w, 3) uint8 array.

    Stride-safe (RESEARCH Pitfall 2): Qt pads scanlines to 4-byte alignment
    on Windows, so ``bytesPerLine()`` may exceed ``width * 3``. The buffer
    is reshaped to (h, bytesPerLine), sliced to w*3, then reshaped to
    (h, w, 3). ``.copy()`` detaches from the QImage's buffer so the array
    can cross the thread boundary while the QImage is garbage-collected.
    """
    h = image.height()
    w = image.width()
    if image.isNull() or h < 1 or w < 1:
        return np.zeros((0, 0, 3), dtype=np.uint8)
    stride = image.bytesPerLine()
    buf = np.frombuffer(image.constBits(), dtype=np.uint8)
    rows = buf.reshape(h, stride)
    return rows[:, : w * 3].reshape(h, w, 3).copy()


class OcrGrabHistoryPanel(QWidget):
    """Small always-on-top floating window listing recent OCR Grab results.

    PURE FOLLOWER (InspectorPanel precedent, plan 04-04): the panel never
    touches the clipboard and never runs OCR — it only appends entries and
    emits :attr:`capture_requested` (New capture button) and
    :attr:`entry_copy_requested(str)` (an entry was activated/clicked,
    carrying the entry's FULL text; the list shows a truncated one-line
    preview, the data role holds the whole string).

    Most recent first, capped at :attr:`MAX_HISTORY` (the tail drops off).
    MainWindow shows/hides it with tool selection; it is created hidden and
    must never appear at startup.
    """

    # New capture button pressed -> MainWindow starts a fresh grab session.
    capture_requested = Signal()
    # An entry was clicked/activated -> carries the entry's FULL text.
    entry_copy_requested = Signal(str)

    MAX_HISTORY = 20

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # A titled small tool window (frameless-free on purpose — the title
        # bar is how the user drags it out of the way), pinned above others
        # while the tool is active.
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("OCR Grab")
        self.setFixedSize(_PANEL_WIDTH, _PANEL_HEIGHT)

        self._list = QListWidget(self)
        self._list.setToolTip("Recent screen OCR results — most recent first.")
        self._list.itemClicked.connect(self._on_entry_clicked)
        self._list.itemActivated.connect(self._on_entry_clicked)

        self._capture_btn = QPushButton("New capture", self)
        self._capture_btn.setToolTip("Start a new screen grab (or press S).")
        self._capture_btn.clicked.connect(self.capture_requested.emit)

        hint = QLabel(
            "Click an entry to re-copy — S or New capture for another grab",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9a9aa2; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._capture_btn)
        layout.addWidget(self._list, 1)
        layout.addWidget(hint)

    # ------------------------------------------------------------- public
    def add_entry(self, text: str) -> None:
        """Prepend ``text`` (most recent first); cap at MAX_HISTORY.

        Empty/whitespace text is rejected silently (the finished handler
        already shows the "No text recognized" status). The item displays a
        truncated one-line preview; the full text rides the UserRole data.
        """
        if not text or not text.strip():
            return
        item = QListWidgetItem(self._preview(text))
        item.setData(Qt.ItemDataRole.UserRole, text)
        item.setToolTip(text)
        self._list.insertItem(0, item)
        while self._list.count() > self.MAX_HISTORY:
            self._list.takeItem(self._list.count() - 1)

    def entries(self) -> list[str]:
        """Return the full texts, most recent first (test accessor)."""
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
        ]

    # ------------------------------------------------------------ private
    @staticmethod
    def _preview(text: str) -> str:
        """One-line truncated preview: whitespace flattened, ~40 chars."""
        flat = " ".join(text.split())
        if len(flat) <= _PREVIEW_CHARS:
            return flat
        return flat[:_PREVIEW_CHARS] + "\u2026"

    def _on_entry_clicked(self, item: QListWidgetItem) -> None:
        """Entry activated/clicked -> emit its FULL text (re-copy path)."""
        self.entry_copy_requested.emit(item.data(Qt.ItemDataRole.UserRole))

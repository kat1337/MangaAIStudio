"""``CurveWidget`` + ``CurvesDialog`` — the Tools → Curves… dialog (plan 06-04).

UI-SPEC surface 30 (PROJ-04 curves, D-01…D-08): the full draggable curve
editor that replaces the Levels dialog. The custom ``CurveWidget`` draws the
256-unit grid (64-unit major / 16-unit minor gridlines), the muted diagonal
reference, the faint D-08 luminance histogram, the accent 2px curve polyline,
and the control-point handles (8x8 interior / 10x10 endpoints); it owns the
D-04 interaction (click-add, drag, double-click-delete, endpoints y-only) and
the D-07 keyboard story (arrows nudge ±1 / Shift=±10, Tab / Shift+Tab point
selection).

``CurvesDialog`` is a **collector + preview driver** (RESEARCH Pitfall 3/9 —
the LevelsDialog template): it never mutates models and no undo pushes
originate here. Every control change funnels into the single ``_refresh`` →
``_preview`` → ``preview_callback`` path (the capture-suppressed canvas
preview); ``[Cancel]`` ``reject()``s and ``[Apply]`` stores
``result_values = (master_points, channel_points)`` and ``accept()``s. The
curve is the single source of truth (D-02/D-03): the black/white quick-access
rows sync to the endpoints, the gamma row syncs to the curve's sampled output
at input 128 (A3), the In/Out spins drive the selected point, and everything
is cross-clamped (black max = white−1, white min = black+1; T-05-07
discipline) in ONE ``_updating``-guarded pass.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from manga_ai_studio.core import image_ops

# ---------------------------------------------------------------------------
# CurveWidget geometry constants (UI-SPEC surface 30 §Spacing)
# ---------------------------------------------------------------------------

_GRID_MAJOR = 64  # major gridline interval (units)
_GRID_MINOR = 16  # minor gridline interval (units)
_HIT_RADIUS = 10  # px point hit-test radius (click selects/drags within it)
_HANDLE_SIZE = 8  # interior point handle (px)
_ENDPOINT_SIZE = 10  # endpoint handle (px) — visually distinct
_PLOT_MARGIN = 8  # plot square inset from the widget edges (px)

# Dark QSS for the dialog (UI-SPEC §Color tokens — the LevelsDialog block
# extended with QToolButton (channel switcher accent checked state) + the
# Small muted helper labels ("Preset:" / "Channel:", 12px #9a9aa2)).
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QLabel#helper_label { font-size: 12px; color: #9a9aa2; }
QSpinBox, QDoubleSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
    padding: 1px 4px;
}
QSlider::groove:horizontal {
    background: #3a3a42;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #00d4ff;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #00d4ff; border-radius: 2px; }
QPushButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 4px 12px;
    color: #e8e8ea;
}
QPushButton:hover { background: #34343c; }
QPushButton:default { border: 1px solid #00d4ff; }
QToolButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 3px 10px;
    color: #9a9aa2;
}
QToolButton:hover { background: #34343c; }
QToolButton:checked { border: 1px solid #00d4ff; color: #00d4ff; }
"""


class CurveWidget(QWidget):
    """The custom QPainter curve control (D-04 click/drag/D-07 keyboard).

    Owns one point list (the dialog hands it the current channel's list by
    reference, so the dialog stays the single source of truth). Emits
    ``points_changed`` after every mutation and ``point_selected(int)`` when
    the selected point changes. All mutations clamp to [0,255]² with x-order
    preserved; endpoints are y-draggable only (T-06-05).
    """

    points_changed = Signal()
    point_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # D-07: the widget must accept keyboard focus for the full story.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._points: list[tuple[int, int]] = [(0, 0), (255, 255)]
        self._selected = 0
        self._histogram: np.ndarray | None = None
        self._dragging = False
        self.setMinimumSize(280, 240)

    # -------------------------------------------------------- geometry map
    def plot_rect(self) -> QRectF:
        """The square plot area — largest square in the widget minus 8px."""
        side = max(min(self.width(), self.height()) - 2 * _PLOT_MARGIN, 1)
        x = (self.width() - side) / 2.0
        y = (self.height() - side) / 2.0
        return QRectF(x, y, side, side)

    def unit_to_widget(self, x: int, y: int) -> QPointF:
        """Map unit-space [0,255]² to widget coords (y axis inverted)."""
        r = self.plot_rect()
        return QPointF(
            r.left() + x / 255.0 * r.width(),
            r.bottom() - y / 255.0 * r.height(),
        )

    def widget_to_unit(self, pos) -> tuple[int, int]:
        """Map a widget-space point to rounded unit coordinates."""
        r = self.plot_rect()
        ux = (pos.x() - r.left()) / r.width() * 255.0
        uy = (r.bottom() - pos.y()) / r.height() * 255.0
        return int(round(ux)), int(round(uy))

    # -------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.plot_rect()

        # Plot background + 1px border.
        p.fillRect(r, QColor("#0b0b0e"))
        p.setPen(QColor("#3a3a42"))
        p.drawRect(r)

        # Faint D-08 histogram bars behind the gridlines (0.14 alpha).
        if self._histogram is not None and self._histogram.size == 256:
            peak = float(self._histogram.max())
            if peak > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(232, 232, 234, 36))  # rgba(232,232,234,0.14)
                step = r.width() / 256.0
                for i, count in enumerate(self._histogram):
                    if count <= 0:
                        continue
                    h = max(1.0, count / peak * r.height())
                    p.drawRect(
                        QRectF(r.left() + i * step, r.bottom() - h, step, h)
                    )

        # Gridlines: minor 16-unit (reduced alpha), major 64-unit.
        minor = QColor("#3a3a42")
        minor.setAlpha(90)
        for u in range(1, 256):
            if u % _GRID_MAJOR == 0:
                p.setPen(QColor("#3a3a42"))
            elif u % _GRID_MINOR == 0:
                p.setPen(minor)
            else:
                continue
            frac = u / 255.0
            x = r.left() + frac * r.width()
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            y = r.bottom() - frac * r.height()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

        # Muted diagonal reference line (#9a9aa2).
        p.setPen(QColor("#9a9aa2"))
        p.drawLine(self.unit_to_widget(0, 0), self.unit_to_widget(255, 255))

        # Accent 2px curve polyline through the mapped points.
        if len(self._points) >= 2:
            path = QPainterPath()
            for i, (x, y) in enumerate(self._points):
                pt = self.unit_to_widget(x, y)
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            p.setPen(QPen(QColor("#00d4ff"), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # Handles: 8x8 interior, 10x10 endpoints; selected = accent outline.
        n = len(self._points)
        for i, (x, y) in enumerate(self._points):
            pt = self.unit_to_widget(x, y)
            size = _ENDPOINT_SIZE if i in (0, n - 1) else _HANDLE_SIZE
            half = size / 2.0
            rect = QRectF(pt.x() - half, pt.y() - half, size, size)
            if i == self._selected:
                p.setPen(QPen(QColor("#00d4ff"), 2.0))
            else:
                p.setPen(QColor("#3a3a42"))
            p.setBrush(QColor("#e8e8ea"))
            p.drawRect(rect)

    # -------------------------------------------------------- interaction
    def _hit_test(self, pos) -> int | None:
        """Index of the point within ``_HIT_RADIUS`` px of ``pos``, else None."""
        best: int | None = None
        best_d = _HIT_RADIUS
        for i, (x, y) in enumerate(self._points):
            pt = self.unit_to_widget(x, y)
            d = math.hypot(pos.x() - pt.x(), pos.y() - pt.y())
            if d <= best_d:
                best_d = d
                best = i
        return best

    def _clamp_move(self, index: int, x: int, y: int) -> tuple[int, int]:
        """Clamp a candidate (x, y) for point ``index`` (D-04, T-06-05).

        Endpoints move y-only (x fixed at 0/255); interior points keep x
        strictly between their neighbors and y in [0,255].
        """
        y = max(0, min(255, y))
        n = len(self._points)
        if index in (0, n - 1):
            return self._points[index][0], y
        lo = self._points[index - 1][0] + 1
        hi = self._points[index + 1][0] - 1
        return max(lo, min(hi, x)), y

    def _move_selected(self, x: int, y: int) -> None:
        """Move the selected point with clamps and repaint (no signal)."""
        nx, ny = self._clamp_move(self._selected, x, y)
        if nx != self._points[self._selected][0] or ny != self._points[
            self._selected
        ][1]:
            self._points[self._selected] = (nx, ny)
            self.update()

    def _add_point(self, x: int, y: int) -> int:
        """Add a point at (x, y) preserving x-order; returns its index.

        A click at an x that already holds a point updates that point's y
        instead (last-wins at add-time — matches the LUT backstop, UI-SPEC
        surface 30); the endpoints own x = 0/255, so a fresh point is always
        inserted strictly between neighbors. y clamps to [0,255].
        """
        y = max(0, min(255, y))
        x = max(0, min(255, x))
        pts = self._points
        for i, (px, _py) in enumerate(pts):
            if px == x:
                if pts[i][1] != y:
                    pts[i] = (px, y)
                    self.update()
                return i
        i = 0
        while i < len(pts) and pts[i][0] < x:
            i += 1
        pts.insert(i, (x, y))
        self.update()
        return i

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        idx = self._hit_test(pos)
        if idx is not None:
            self._selected = idx
            self._dragging = True
            self.point_selected.emit(idx)
            self.update()
        else:
            x, y = self.widget_to_unit(pos)
            self._selected = self._add_point(x, y)
            self._dragging = True
            self.points_changed.emit()
            self.point_selected.emit(self._selected)
            self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        x, y = self.widget_to_unit(event.position().toPoint())
        self._move_selected(x, y)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.points_changed.emit()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        idx = self._hit_test(event.position().toPoint())
        n = len(self._points)
        if idx is not None and idx not in (0, n - 1):
            del self._points[idx]
            self._selected = max(0, min(self._selected, len(self._points) - 1))
            self.points_changed.emit()
            self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        key = event.key()
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            step = (
                10
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                else 1
            )
            x, y = self._points[self._selected]
            if key == Qt.Key.Key_Left:
                x -= step
            elif key == Qt.Key.Key_Right:
                x += step
            elif key == Qt.Key.Key_Up:
                y += step
            else:
                y -= step
            before = self._points[self._selected]
            self._move_selected(x, y)
            if self._points[self._selected] != before:
                self.points_changed.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Tab:
            n = len(self._points)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._selected = (self._selected - 1) % n
            else:
                self._selected = (self._selected + 1) % n
            self.point_selected.emit(self._selected)
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

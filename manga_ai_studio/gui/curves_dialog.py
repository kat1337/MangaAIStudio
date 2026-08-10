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


class CurvesDialog(QDialog):
    """Collector + preview driver for the Curves flow (D-01…D-08, PROJ-04).

    The LevelsDialog shape (05-06) extended with the CurveWidget: preset row
    + channel switcher on top, black/white quick-access rows above the grid,
    gamma + In/Out below, [Cancel][Apply] at the bottom (UI-SPEC surface 30).

    Pure collector (RESEARCH Pitfall 3/9): the dialog never mutates models
    and no undo pushes originate here. The curve is the single source of
    truth (D-02/D-03) — every control change funnels into ONE
    ``_updating``-guarded ``_refresh`` that re-syncs every control from the
    current channel's points (with the white>black cross-clamp, T-05-07) and
    drives the composed preview through the single ``_preview`` driver.
    ``[Apply]`` stores ``result_values = (master_points, channel_points)``
    for the MainWindow (plan 06-05 ``_on_curves``).
    """

    # Gamma log-slider mapping (UI-SPEC surface 30 range 0.10..4.00) — the
    # LevelsDialog constants, reused verbatim per the plan contract.
    GAMMA_MIN = 0.10
    GAMMA_MAX = 4.00
    GAMMA_STEPS = 1000

    # D-05 preset starting points (RESEARCH A2, locked in 06-UI-SPEC:30).
    # Presets are fully editable afterwards — starting points, never locked.
    PRESETS = {
        "Linear": [(0, 0), (255, 255)],
        "S-curve": [(0, 0), (64, 40), (192, 215), (255, 255)],
        "Brighten": [(0, 0), (128, 150), (255, 255)],
        "Darken": [(0, 0), (128, 105), (255, 255)],
    }
    _PRESET_TOOLTIPS = {
        "Linear": "Reset the curve to a straight line.",
        "S-curve": "Add contrast — classic S-curve.",
        "Brighten": "Brighten midtones.",
        "Darken": "Darken midtones.",
    }
    CHANNELS = ("RGB", "R", "G", "B")

    def __init__(
        self,
        parent=None,
        page_image=None,
        preview_callback=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Curves")
        self.setObjectName("curves_dialog")
        self.setModal(True)

        # The caller's detached pre-dialog image (restore/apply base). The
        # preview composes from this base only (Pitfall 2/9).
        self._page_image = page_image
        self.preview_callback = preview_callback
        self._updating = False
        # True while _refresh back-maps the gamma spin (display mirror) —
        # suppresses the forward gamma handler so a back-map never
        # re-injects the (128, y) point (A3: inject on user gamma edits).
        self._gamma_syncing = False
        self._selected = 0
        self._current_channel = "RGB"
        # Per-channel point sets — the CurveWidget edits the current
        # channel's list by reference (D-06 channel independence).
        self._channel_points: dict[str, list[tuple[int, int]]] = {
            ch: [(0, 0), (255, 255)] for ch in self.CHANNELS
        }
        # Result carrier (read by the MainWindow after exec() == Accepted).
        self.result_values: tuple[
            list[tuple[int, int]], dict[str, list[tuple[int, int]]]
        ] = (
            list(self._channel_points["RGB"]),
            {ch: list(pts) for ch, pts in self._channel_points.items()},
        )

        # D-12: 14px Body base font from birth (A4 — assert pixelSize).
        base_font = QFont(self.font())
        base_font.setPixelSize(14)
        self.setFont(base_font)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ---- preset row (D-05) + channel switcher (D-06), top -----------
        top = QHBoxLayout()
        preset_label = QLabel("Preset:", self)
        preset_label.setObjectName("helper_label")
        top.addWidget(preset_label)
        self.preset_buttons: dict[str, QPushButton] = {}
        for name in self.PRESETS:
            btn = QPushButton(name, self)
            btn.setToolTip(self._PRESET_TOOLTIPS[name])
            self.preset_buttons[name] = btn
            top.addWidget(btn)
        top.addSpacing(12)
        channel_label = QLabel("Channel:", self)
        channel_label.setObjectName("helper_label")
        top.addWidget(channel_label)
        self.channel_buttons: dict[str, QToolButton] = {}
        self.channel_group = QButtonGroup(self)
        self.channel_group.setExclusive(True)
        for name in self.CHANNELS:
            btn = QToolButton(self)
            btn.setText(name)
            btn.setCheckable(True)
            self.channel_buttons[name] = btn
            self.channel_group.addButton(btn)
            top.addWidget(btn)
        self.channel_buttons["RGB"].setChecked(True)
        top.addStretch(1)
        root.addLayout(top)

        # ---- black/white quick-access rows (D-01: ABOVE the grid) -------
        form = QFormLayout()
        self.black_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.black_slider.setRange(0, 255)
        self.black_slider.setValue(0)
        self.black_spin = QSpinBox(self)
        self.black_spin.setRange(0, 255)
        self.black_spin.setValue(0)
        form.addRow("Black point:", self._row(self.black_slider, self.black_spin))

        self.white_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.white_slider.setRange(0, 255)
        self.white_slider.setValue(255)
        self.white_spin = QSpinBox(self)
        self.white_spin.setRange(0, 255)
        self.white_spin.setValue(255)
        form.addRow("White point:", self._row(self.white_slider, self.white_spin))
        root.addLayout(form)

        # ---- the curve grid (stretch) ------------------------------------
        self.curve_widget = CurveWidget(self)
        # Hand the widget the CURRENT channel's list by reference — widget
        # edits land directly in _channel_points (single source of truth).
        self.curve_widget._points = self._channel_points[self._current_channel]
        root.addWidget(self.curve_widget, 1)

        # ---- gamma + In/Out rows (below the grid) ------------------------
        form2 = QFormLayout()
        self.gamma_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.gamma_slider.setRange(0, self.GAMMA_STEPS)
        self.gamma_slider.setValue(self._gamma_to_slider(1.00))
        self.gamma_spin = QDoubleSpinBox(self)
        self.gamma_spin.setRange(self.GAMMA_MIN, self.GAMMA_MAX)
        self.gamma_spin.setDecimals(2)
        self.gamma_spin.setSingleStep(0.01)
        self.gamma_spin.setValue(1.00)
        form2.addRow("Gamma:", self._row(self.gamma_slider, self.gamma_spin))

        self.in_spin = QSpinBox(self)
        self.in_spin.setRange(0, 255)
        self.out_spin = QSpinBox(self)
        self.out_spin.setRange(0, 255)
        form2.addRow("In:", self.in_spin)
        form2.addRow("Out:", self.out_spin)
        root.addLayout(form2)

        # [Cancel] [Apply] (Apply default, accent border per the QSS).
        buttons = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("Apply", self)
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.apply_btn)
        root.addLayout(buttons)

        self.setStyleSheet(_DIALOG_QSS)

        # ---- widget wiring ------------------------------------------------
        # Black/white rows: slider <-> spin direct links (Qt does not re-emit
        # identical values) + the endpoint mutation through the spin's
        # valueChanged — every change funnels into ONE _refresh.
        self.black_spin.valueChanged.connect(self.black_slider.setValue)
        self.black_slider.valueChanged.connect(self.black_spin.setValue)
        self.black_spin.valueChanged.connect(self._on_black_changed)
        self.white_spin.valueChanged.connect(self.white_slider.setValue)
        self.white_slider.valueChanged.connect(self.white_spin.setValue)
        self.white_spin.valueChanged.connect(self._on_white_changed)
        # Gamma: log-scaled slider <-> spin (Levels verbatim) + midpoint
        # anchor injection through the spin's valueChanged.
        self.gamma_spin.valueChanged.connect(self._on_gamma_spin_changed)
        self.gamma_slider.valueChanged.connect(self._on_gamma_slider_changed)
        self.gamma_spin.valueChanged.connect(self._on_gamma_changed)
        # In/Out spins drive the selected point.
        self.in_spin.valueChanged.connect(self._on_in_changed)
        self.out_spin.valueChanged.connect(self._on_out_changed)
        # The widget's curve edits + selection changes -> the shared refresh.
        self.curve_widget.points_changed.connect(self._refresh)
        self.curve_widget.point_selected.connect(self._on_point_selected)

        # Apply the initial state once: clamps + preview with the defaults.
        self._refresh()

    # ------------------------------------------------------------ structure
    def _row(self, slider: QSlider, spin) -> QHBoxLayout:
        """A slider + spinbox row (spin right-aligned after a stretch)."""
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(spin)
        return row

    # -------------------------------------------------------------- gamma map
    def _gamma_to_slider(self, gamma: float) -> int:
        """Map a linear gamma value onto the log-scaled slider position."""
        span = math.log(self.GAMMA_MAX) - math.log(self.GAMMA_MIN)
        t = (math.log(gamma) - math.log(self.GAMMA_MIN)) / span
        return int(round(t * self.GAMMA_STEPS))

    def _slider_to_gamma(self, t: int) -> float:
        """Map a log-scaled slider position back to a linear gamma value."""
        span = math.log(self.GAMMA_MAX) - math.log(self.GAMMA_MIN)
        g = math.exp(math.log(self.GAMMA_MIN) + span * t / self.GAMMA_STEPS)
        return round(g, 2)

    def _on_gamma_slider_changed(self, t: int) -> None:
        """Sync the gamma spinbox from the log-scaled slider."""
        self.gamma_spin.setValue(self._slider_to_gamma(t))

    def _on_gamma_spin_changed(self, g: float) -> None:
        """Sync the log-scaled slider from the gamma spinbox."""
        self.gamma_slider.setValue(self._gamma_to_slider(g))

    # ------------------------------------------------------------- handlers
    def _on_black_changed(self, value: int) -> None:
        """The black row drives the left endpoint's y (input 0)."""
        self.curve_widget._points[0] = (0, value)
        self._refresh()

    def _on_white_changed(self, value: int) -> None:
        """The white row drives the right endpoint's y (input 255)."""
        self.curve_widget._points[-1] = (255, value)
        self._refresh()

    def _on_gamma_changed(self, g: float) -> None:
        """Position the (128, y) midpoint anchor (D-03/A3).

        Setting gamma injects or moves the point at input 128 with
        ``y = round(255 * 0.5^(1/g))`` — gamma 1.00 positions y = 128 (the
        diagonal). Suppressed while ``_refresh`` back-maps the spin (the
        back-map is a display mirror — the injection is forward-only).
        """
        if self._gamma_syncing:
            return
        y = int(round(255.0 * 0.5 ** (1.0 / g)))
        pts = self.curve_widget._points
        for i, (px, _py) in enumerate(pts):
            if px == 128:
                pts[i] = (128, y)
                break
        else:
            i = 0
            while i < len(pts) and pts[i][0] < 128:
                i += 1
            pts.insert(i, (128, y))
        self._refresh()

    def _on_in_changed(self, value: int) -> None:
        """The In spin drives the selected point's x (range-constrained)."""
        pts = self.curve_widget._points
        sel = min(self._selected, len(pts) - 1)
        if sel in (0, len(pts) - 1):
            return  # endpoints never move horizontally (D-04)
        pts[sel] = (value, pts[sel][1])
        self._refresh()

    def _on_out_changed(self, value: int) -> None:
        """The Out spin drives the selected point's y."""
        pts = self.curve_widget._points
        sel = min(self._selected, len(pts) - 1)
        pts[sel] = (pts[sel][0], value)
        self._refresh()

    def _on_point_selected(self, index: int) -> None:
        """The widget's selection change re-targets the In/Out spins."""
        self._selected = index
        self._refresh()

    # ---------------------------------------------------------------- driver
    def _refresh(self) -> None:
        """Sync every control from the curve — ONE guarded pass (D-02/D-03).

        Reads the current channel's points (the single source of truth),
        applies the white>black cross-clamp to the ENDPOINTS themselves
        (T-05-07: the mirror of the Levels clamp — black max = white−1,
        white min = black+1), syncs the black/white rows, back-maps gamma
        from the sampled output at input 128 (A3), re-targets the In/Out
        spins to the selected point (In range [prev_x+1, next_x−1], disabled
        for endpoints), then fires the composed preview through ``_preview``.
        ``_updating`` guards the clamp's own value adjustments from
        re-entering (the direct setValue links never recurse).
        """
        if self._updating:
            return
        self._updating = True
        try:
            # The widget is the single mutation surface; re-point the
            # channel dict at its list so the reference can never diverge.
            pts = self.curve_widget._points
            self._channel_points[self._current_channel] = pts
            # Cross-clamp on the curve state (the slider-side mirror):
            # black max = white−1 / white min = black+1 — endpoints can
            # never invert, so the preview can never receive an inverted map.
            black = max(0, min(254, pts[0][1]))
            white = max(1, min(255, pts[-1][1]))
            white = max(white, black + 1)
            black = min(black, white - 1)
            pts[0] = (0, black)
            pts[-1] = (255, white)

            # Black/white rows mirror the endpoints (spin min/max follow).
            self.white_slider.setMinimum(black + 1)
            self.white_spin.setMinimum(black + 1)
            self.black_slider.setMaximum(white - 1)
            self.black_spin.setMaximum(white - 1)
            self.black_spin.setValue(black)
            self.white_spin.setValue(white)

            # Gamma row: back-map from the sampled output at input 128
            # (display mirror only — the forward injection is suppressed).
            mid_out = self._sample_output(pts, 128)
            if 0 < mid_out < 255:
                raw = math.log(0.5) / math.log(mid_out / 255.0)
                if abs(raw - 1.0) < 0.01:
                    g = 1.00  # the diagonal back-maps to exactly 1.00 (A3)
                else:
                    g = round(raw, 2)
                if self.GAMMA_MIN <= g <= self.GAMMA_MAX:
                    self._gamma_syncing = True
                    try:
                        self.gamma_spin.setValue(g)
                    finally:
                        self._gamma_syncing = False

            # In/Out spins track the selected point (x-order preserved).
            sel = min(self._selected, len(pts) - 1)
            self.curve_widget._selected = sel
            x, y = pts[sel]
            if sel in (0, len(pts) - 1):
                self.in_spin.setEnabled(False)  # endpoints never move in x
                self.in_spin.setRange(x, x)
                self.in_spin.setValue(x)
            else:
                self.in_spin.setEnabled(True)
                self.in_spin.setRange(pts[sel - 1][0] + 1, pts[sel + 1][0] - 1)
                self.in_spin.setValue(x)
            self.out_spin.setValue(y)
            self.curve_widget.update()
        finally:
            self._updating = False
        self._preview()

    @staticmethod
    def _sample_output(points, x_in: int) -> float:
        """The curve's piecewise-linear output at ``x_in`` (A3 sampling).

        Always well-defined for any point set — the piecewise-linear
        interpolation makes gamma independent of whether an explicit (128,y)
        point exists.
        """
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return float(np.interp(x_in, xs, ys))

    def _preview(self) -> None:
        """The single preview driver: compose master→channel and fire.

        Only call site of ``preview_callback`` in this file — every control
        change funnels through ``_refresh`` into here (Task 3 gate). The
        composition is ``image_ops.curves_page`` (A1: per-channel LUTs
        applied after the master). No image, no callback -> no-op.
        """
        if self._page_image is None or self.preview_callback is None:
            return
        composed = image_ops.curves_page(
            self._page_image,
            self._channel_points["RGB"],
            {ch: self._channel_points[ch] for ch in ("R", "G", "B")},
        )
        self.preview_callback(composed)

    def _on_apply(self) -> None:
        """Store the collected curve state and accept (no mutation here)."""
        self.result_values = (
            list(self._channel_points["RGB"]),
            {ch: list(pts) for ch, pts in self._channel_points.items()},
        )
        self.accept()

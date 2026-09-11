"""``InspectorPanel`` — the Phase 4 text-edit / metadata panel (plan 04-04 Task 2).

This is the D-08 "always-present view of both fields + metadata" — since plan
09-02 it is the body of the **Typesetting** collapsible section inside the
unified right-side "Panel" dock (built in :meth:`MainWindow._build_docks`;
formerly the tabified "Inspector" QDockWidget — the UI-04 rename is
user-visible strings only, the class name stays). It surfaces,
for the currently-selected box:

- **Bubble #** — a bounded ``QSpinBox`` (0..9999 — 0 is the unset sentinel,
  displayed as an em dash) for the D-15/D-16 reading-order number. A manual
  value sets ``manual_override=True`` (D-16 — the amber badge
  border) so a page-level re-auto preserves the user's hand-set number.
- **Origin** — a read-only hue-colored ``QLabel`` (green detected / amber user —
  matches the canvas border, reusing the Phase 3 origin hues as text colour).
- **Recognized** — a multi-line ``QTextEdit`` for the OCR text. Commits route
  through the ``recognized_edited`` signal → the MainWindow calls
  :meth:`PageBox.set_recognized_text_edited` (the centralized manual-edit
  setter, D-04 ``edited=True``). NOT ``set_recognized_text`` (OCR-write, sets
  ``edited=False``) and NOT a direct ``payload.text`` write (bypasses the
  payload-None guard).
- **Translation** — a multi-line ``QTextEdit`` for the reader-facing text.
  Commits route through ``translation_changed`` →
  :meth:`PageBox.set_translation` (the D-13 MT seam).
- **Language** — a read-only ``QLabel`` (from ``payload.language``).
- **Vertical** — a ``QCheckBox`` reading/writing ``style.vertical`` (G-07-1:
  the per-box STYLE flag drives rendering; the payload's `vertical` field is
  pure export metadata the toggle never touches). LIVE since plan 07-05
  (D-13): toggling flips the canvas + bake to the renderer's tategaki path
  (Pitfall 9); in a multi-selection it becomes tri-state (indeterminate =
  mixed vertical flags, D-10).
- **Style section** (plan 07-05, D-05/D-06/D-10/D-14/D-15 — UI-SPEC surface
  33): the per-box styling controls BELOW the text fields — Font
  (``QFontComboBox``), Style (per-family ``QComboBox``), Size + Auto-fit
  (0..1024 ``QSpinBox`` with the "Auto" sentinel + a tri-state ``QCheckBox``),
  Fill (Solid | Gradient | Pattern — quick-260910-vej: a type selector with
  conditional Color B + Angle sub-rows for gradient, Image… + Scale sub-rows
  for pattern, an embedded-tile picker with the 4 MB cap warning, and the
  MAIN Color swatch previewing the REAL fill), Color (24x24 swatch
  ``QToolButton`` → ``QColorDialog``), Align / Align V
  combos, and the Outline / Glow / Shadow effect rows (enable checkbox +
  swatch + spin). Every control carries a class-scope Signal + a WR-01 no-op
  guard. In a MULTI-selection (D-10) the section shows the common-value /
  "Mixed" state: differing values display the Mixed sentinel per widget
  (combo "Mixed" entries, size-spin "Mixed" special text, split swatch,
  tri-state checkboxes) and ONE override applies to ALL selected boxes — the
  sentinel NEVER leaves the widget layer (RESEARCH Pitfall 7).

Mirrors :class:`manga_ai_studio.gui.tools_panel.ToolsPanel`'s shape (class-scope
``Signal`` declarations, ``QVBoxLayout`` root with sm margins, the dark QSS) per
04-PATTERNS.md (the ToolsPanel is THE analog). The panel is a *follower* — it
subscribes to the canvas selection (via the MainWindow) and edits commit through
callbacks the MainWindow supplies (so the pagebox mutation + ``boxes_modified``
push + overlay refresh all live in the MainWindow, not here).

Security:
    - Both ``QTextEdit`` fields render plain text only (the recognised field
      carries OCR output — ASVS V5, no HTML injection path via the panel).
    - The Bubble # ``QSpinBox`` is bounded 0..9999 (T-4-08 tampering mitigation
      — out-of-range values cannot reach ``pagebox.bubble_no``). 0 never
      reaches the model — the MainWindow handler maps the sentinel to
      ``bubble_no=None``, so ``pagebox.bubble_no`` only ever receives None or
      1..9999 (T-4-08 mitigation unchanged).
    - Style values leave the panel only as real values (the "Mixed" sentinel
      never crosses into a ``TextStyle`` — T-07-11 / RESEARCH Pitfall 7); the
      spinbox ranges clamp inputs at the UI: size 0..1024 with 0 = Auto, and
      effect width/radius 0..256 = ``EFFECT_GEOM_MAX`` from the TextStyle
      model itself (quick-260826-vhh — UI == model by construction; a big SFX
      stroke/glow is intent, not garbage, and garbage still cannot reach the
      model since the V5 coercion clamps to the same constant).
"""

from __future__ import annotations

import base64
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QRectF, Qt, QTimer, QRegularExpression, QSortFilterProxyModel, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFocusEvent,
    QFontDatabase,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from manga_ai_studio.core.box_model import DETECTED, USER
from manga_ai_studio.core.text_style import EFFECT_GEOM_MAX
from manga_ai_studio.core.text_style import FILL_TILE_MAX_BYTES
from manga_ai_studio.core.text_style import TextStyle
from manga_ai_studio.gui.text_renderer import _gradient_start_end

# Dark QSS for the Inspector panel (UI-SPEC §Color tokens — copied from the
# ToolsPanel _TOOLS_QSS so the panel sections share a look). Adds
# QTextEdit styling (the ToolsPanel has no text edit) reusing the same tokens.
# Plan 07-05 (D-05): the styling-section widgets (QFontComboBox/QComboBox/
# QToolButton swatch/QFrame divider/section header) join the same token set —
# #2d2d33 bg, #3a3a42 border, #e8e8ea fg, :disabled -> #25252b/#6a6a72.
_INSPECTOR_QSS = """
QLabel { color: #e8e8ea; }
QLabel#styleHeaderLabel { color: #9a9aa2; font-size: 12px; font-weight: 600; }
QLabel#stdDevLabel { color: #9a9aa2; }
QLabel#confidenceLabel { color: #9a9aa2; }
QTextEdit {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
}
QTextEdit:disabled {
    background: #25252b;
    color: #6a6a72;
}
QSpinBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 1px 4px;
    color: #e8e8ea;
}
QSpinBox:disabled {
    background: #25252b;
    color: #6a6a72;
}
QCheckBox { color: #e8e8ea; }
QCheckBox:disabled { color: #6a6a72; }
QLineEdit {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 1px 4px;
    color: #e8e8ea;
}
QLineEdit:disabled {
    background: #25252b;
    color: #6a6a72;
}
QFontComboBox, QComboBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 1px 4px;
    color: #e8e8ea;
}
QFontComboBox:disabled, QComboBox:disabled {
    background: #25252b;
    color: #6a6a72;
}
QComboBox QAbstractItemView {
    background: #2d2d33;
    color: #e8e8ea;
    border: 1px solid #3a3a42;
    selection-background-color: #3a3a42;
    selection-color: #e8e8ea;
}
QToolButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
}
QToolButton:disabled { background: #25252b; }
QFrame#styleDivider {
    background: #3a3a42;
    border: none;
    max-height: 1px;
}
"""

# Empty-state copy (UI-SPEC §Copywriting — shown when no box is selected).
# Plan 07-05 (D-05): the Phase 4 copy gains ", and style" — the styling
# section rides the same empty-state gate.
_EMPTY_STATE = "Select a text box to edit its text, translation, and style."
# Field placeholders (UI-SPEC §Copywriting — shown in the empty text fields).
_RECOGNIZED_PLACEHOLDER = (
    "No recognized text yet — run OCR (Text \u2192 Run OCR)."
)
_TRANSLATION_PLACEHOLDER = "No translation — type one, or use Load Translations\u2026."

# Origin hues reused as TEXT colour so the Inspector matches the canvas border
# (UI-SPEC §18). Module constants keep the hex in one place.
_ORIGIN_HUE_HEX = {DETECTED: "#5fd068", USER: "#f5a623"}
_ORIGIN_LABEL = {DETECTED: "Detected", USER: "User"}

# Inpaint override display strings <-> PageBox.inpaint_override model values
# (UI-SPEC §38 — 08.1 D-04 quad: Auto/Fill/Inpaint/Never; the model stores
# None/"fill"/"always"/"never" — "always" preserved for .mas compat, display
# label is Inpaint not Always).
_INPAINT_DISPLAY = {None: "Auto", "fill": "Fill", "always": "Inpaint", "never": "Never"}
# The Inpaint combo's canonical entry order (Auto default first).
_INPAINT_ITEMS = ["Auto", "Fill", "Inpaint", "Never"]

# Align display strings <-> TextStyle model values (UI-SPEC §33: the combos
# show Left/Center/Right and Top/Middle/Bottom; the model stores lowercase).
_ALIGN_H_DISPLAY = {"left": "Left", "center": "Center", "right": "Right"}
_ALIGN_V_DISPLAY = {"top": "Top", "middle": "Middle", "bottom": "Bottom"}
_ALIGN_H_TO_MODEL = {v: k for k, v in _ALIGN_H_DISPLAY.items()}
_ALIGN_V_TO_MODEL = {v: k for k, v in _ALIGN_V_DISPLAY.items()}

# (bold, italic) -> the QFontDatabase style-name display string.
_FONT_STYLE_NAME = {
    (False, False): "Regular",
    (False, True): "Italic",
    (True, False): "Bold",
    (True, True): "Bold Italic",
}

# Effect-row defaults (UI-SPEC §Color / §Spacing exceptions): outline width
# 2, glow radius 4, shadow offset 2 — the VALUES are the UI-SPEC defaults;
# the RANGES now span 0..int(EFFECT_GEOM_MAX) each (quick-260826-vhh — see
# the effect-row loop below). Colors = the semantic defaults. Used when a
# MIXED row's user interaction needs a real value where the sentinel sat
# (Pitfall 7 — a commit always carries real values).
_EFFECT_DEFAULT_COLORS = {"outline": "#ffffff", "glow": "#e8e8ea", "shadow": "#000000"}
_EFFECT_DEFAULT_VALUES = {"outline": 2, "glow": 4, "shadow": 2}

# Fill-row display strings <-> TextStyle.fill_type model values
# (quick-260910-vej; the inpaint/align combo conventions).
_FILL_ITEMS = ["Solid", "Gradient", "Pattern"]
_FILL_DISPLAY_TO_MODEL = {"Solid": "solid", "Gradient": "gradient", "Pattern": "pattern"}
_FILL_MODEL_TO_DISPLAY = {v: k for k, v in _FILL_DISPLAY_TO_MODEL.items()}


def _decode_preview_tile(b64) -> QImage | None:
    """A pattern tile's b64 payload as a preview ``QImage`` (``None`` on any
    failure — the preview degrades to the solid mode, never raises; the
    renderer's decode guard is the render-side authority, this is the
    swatch's cosmetic mirror)."""
    if not isinstance(b64, str) or not b64:
        return None
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:  # noqa: BLE001 — a garbage tile degrades, never raises
        return None
    if not raw:
        return None
    img = QImage.fromData(raw)
    return None if img.isNull() else img


def _norm_hex_a(color) -> str:
    """Normalize a hex color string to Qt's canonical lowercase HexArgb
    spelling (``#aarrggbb``) — quick-260909-nj9.

    A valid 7- or 9-char hex (``#RRGGBB`` / ``#AARRGGBB``) maps through
    ``QColor.name(HexArgb)``: the legacy opaque ``#ff0000`` normalizes to
    ``#ffff0000`` (alpha-preserving, alpha ``ff`` = opaque) and a sub-opaque
    spelling round-trips verbatim. ANYTHING else — invalid, malformed, a
    non-hex string, ``None`` — is returned UNCHANGED (the V5 tolerance:
    never invent, never reject). The WR-01 style-color guard compares BOTH
    sides through this helper so re-picking the loaded color in a different
    opaque spelling is still a no-op.
    """
    if isinstance(color, str) and color.startswith("#") and len(color) in (7, 9):
        parsed = QColor(color)
        if parsed.isValid():
            return parsed.name(QColor.NameFormat.HexArgb)
    return color


class _ColorSwatchButton(QToolButton):
    """A 24x24 color swatch (UI-SPEC §33 — the styling-section Color/effect rows).

    ``color`` is a hex string (#RRGGBB or #AARRGGBB — quick-260909-nj9) or
    ``None``. A sub-opaque ARGB color paints over a neutral 2-tone
    checkerboard so the transparency reads honestly (the fill composites
    over the greys instead of the widget background). ``None`` paints the
    D-10 MIXED split swatch (left ``#e8e8ea`` / right ``#9a9aa2``, 1px
    ``#3a3a42`` border — UI-SPEC §Color) — the sentinel NEVER leaves the
    widget layer (RESEARCH Pitfall 7): a commit only fires from the dialog
    path with a real color.

    quick-260910-vej (LOCKED UI decision — the swatch previews the REAL
    fill): the optional preview state extends the paint to the styled fill
    modes. ``preview_mode="gradient"`` paints a ``QLinearGradient`` ramp
    with the SAME angle semantics as the renderer (via the shared
    ``_gradient_start_end`` — one angle implementation) over the
    checkerboard when either stop is sub-opaque; ``preview_mode="pattern"``
    paints the tile ``QImage`` tiled over the checkerboard at Color A's
    alpha. ``preview_mode="solid"`` (the default) keeps today's paint
    byte-for-byte. The MAIN Color swatch previews all three modes; the
    Color B swatch stays a plain solid swatch.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color: str | None = None
        self.preview_mode: str = "solid"  # "solid" | "gradient" | "pattern"
        self.preview_color_b: str | None = None
        self.preview_angle: float = 90.0
        self.preview_tile: QImage | None = None
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose a color.")

    def _paint_checkerboard(self, painter: QPainter, rect: QRectF) -> None:
        """The neutral 2-tone checkerboard (quick-260909-nj9) under a
        sub-opaque fill so the alpha composites visibly."""
        cell = 4.0
        row = 0
        y = rect.top()
        while y < rect.bottom():
            h = min(cell, rect.bottom() - y)
            col = 0
            x = rect.left()
            while x < rect.right():
                w = min(cell, rect.right() - x)
                painter.fillRect(
                    QRectF(x, y, w, h),
                    QColor("#cccccc" if (row + col) % 2 == 0 else "#8a8a8a"),
                )
                x += w
                col += 1
            y += h
            row += 1

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        """Paint the solid fill (over a checkerboard when sub-opaque), the
        real-fill preview (gradient ramp / tiled pattern), or the Mixed
        split fill + the 1px border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.color is None:
            # The D-10 split swatch: left #e8e8ea / right #9a9aa2.
            mid = rect.left() + rect.width() / 2.0
            painter.fillRect(
                QRectF(rect.left(), rect.top(), mid - rect.left(), rect.height()),
                QColor("#e8e8ea"),
            )
            painter.fillRect(
                QRectF(mid, rect.top(), rect.right() - mid, rect.height()),
                QColor("#9a9aa2"),
            )
        elif self.preview_mode == "gradient":
            # quick-260910-vej: the REAL gradient preview — same angle
            # semantics as the renderer's fill brush (shared helper), over
            # the checkerboard when either stop is sub-opaque.
            color_a = QColor(self.color)
            color_b = QColor(self.preview_color_b or "#ffffff")
            if (color_a.isValid() and color_a.alpha() < 255) or (
                color_b.isValid() and color_b.alpha() < 255
            ):
                self._paint_checkerboard(painter, rect)
            start, end = _gradient_start_end(
                rect, float(self.preview_angle)
            )
            painter.fillRect(rect, _make_gradient_brush(start, end, color_a, color_b))
        elif self.preview_mode == "pattern" and self.preview_tile is not None:
            # quick-260910-vej: the REAL tile preview — tiled over the
            # checkerboard at Color A's alpha (the LOCKED single-opacity
            # rule; painter opacity composites the tile over the greys).
            self._paint_checkerboard(painter, rect)
            color_a = QColor(self.color)
            painter.save()
            if color_a.isValid() and color_a.alpha() < 255:
                painter.setOpacity(color_a.alpha() / 255.0)
            painter.fillRect(rect, _make_tile_brush(self.preview_tile))
            painter.restore()
        else:
            parsed = QColor(self.color)
            if parsed.isValid() and parsed.alpha() < 255:
                # quick-260909-nj9: honest transparency — a neutral 2-tone
                # checkerboard (~4x4 px, #cccccc/#8a8a8a) UNDER the fill so
                # the alpha composites visibly instead of vanishing into
                # the widget background. Opaque/legacy paths keep today's
                # paint exactly.
                self._paint_checkerboard(painter, rect)
            painter.fillRect(rect, parsed)
        painter.setPen(QPen(QColor("#3a3a42"), 1))
        painter.drawRect(rect)
        painter.end()


def _make_gradient_brush(start, end, color_a: QColor, color_b: QColor):
    """The swatch preview's gradient brush (renderer-equivalent stops)."""
    gradient = QLinearGradient(start, end)
    gradient.setColorAt(0.0, color_a)
    gradient.setColorAt(1.0, color_b)
    return gradient


def _make_tile_brush(tile: QImage):
    """The swatch preview's tiled-texture brush (Qt-native tiling)."""
    brush = QBrush(tile)
    brush.setStyle(Qt.BrushStyle.TexturePattern)
    return brush


class _CommitTextEdit(QTextEdit):
    """A ``QTextEdit`` that commits on focus-loss and Ctrl+Return (UI-SPEC §15).

    Standard Qt commit semantics: focus leaving the field OR Ctrl+Return /
    Ctrl+Enter fires :attr:`committed`. Plain ``Enter`` inserts a newline (the
    multi-line convention) rather than committing, so the user can type
    multi-line recognised text without an accidental commit. The MainWindow-
    supplied commit callbacks are wired to :attr:`committed` via
    :meth:`InspectorPanel.connect_commit_handlers`.
    """

    committed = Signal()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802 (Qt API)
        """Commit on focus-loss (the primary commit signal)."""
        super().focusOutEvent(event)
        self.committed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        """Ctrl+Return / Ctrl+Enter commits; Enter inserts a newline (multi-line)."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.committed.emit()
            return
        super().keyPressEvent(event)


class InspectorPanel(QWidget):
    """The Typesetting section body — text fields + metadata + the Style section.

    Class-scope ``Signal``s carry field edits out to the MainWindow (which owns
    the pagebox mutation + the ``boxes_modified`` BOXES-stack push + the overlay
    refresh). The panel itself never touches a ``PageBox`` directly — it is a
    pure follower/editor that emits the change and lets the MainWindow apply it.
    """

    # Field-change signals. The MainWindow connects these to its commit handlers.
    translation_changed = Signal(str)
    recognized_edited = Signal(str)
    bubble_no_changed = Signal(int)
    vertical_changed = Signal(bool)
    # Style-section signals (plan 07-05, D-05) — one per commit-able control.
    style_font_changed = Signal(str)
    style_font_style_changed = Signal(str)
    style_size_changed = Signal(int)  # 0 = the "Auto" sentinel (D-15)
    style_auto_fit_changed = Signal(bool)
    style_color_changed = Signal(str)
    # quick-260910-vej: the Fill row's commit signal — carries ONLY the
    # fields the user actually changed as a model-keyed dict, e.g.
    # {"fill_type": "gradient", "fill_color_b": "#ff0000", "fill_angle_deg":
    # 45.0} or {"fill_type": "pattern", "pattern_tile_b64": ...} (per-key
    # WR-01 guards; the "Mixed" sentinel never leaves the widget layer).
    style_fill_changed = Signal(dict)
    style_align_changed = Signal(object, object)  # (align_h, align_v) model values; None = untouched axis (G-07-7)
    style_effect_changed = Signal(str, dict)  # effect key + {enabled, color, value}
    # G-07-3 (plan 07-11): the Set-as-Default affordance's family emission —
    # MainWindow persists it under QSettings 'defaultFontFamily'.
    default_font_requested = Signal(str)
    # Plan 08-08 (D-13/D-14, UI-SPEC §38): the Inpaint override combo's commit
    # signal — carries the display text "Auto"/"Always"/"Never" (the "Mixed"
    # sentinel NEVER leaves the widget layer, Pitfall 7).
    inpaint_override_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector_panel")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)  # sm margins (UI-SPEC §Spacing)
        root.setSpacing(8)

        # The empty-state label shown when no box is selected (UI-SPEC §Copywriting).
        self.empty_label = QLabel(_EMPTY_STATE)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #9a9aa2;")
        root.addWidget(self.empty_label)

        # The D-10 multi-select hint (UI-SPEC §Copywriting — shown above the
        # form while N>1 boxes are selected; muted 12px).
        self.multi_hint_label = QLabel("")
        self.multi_hint_label.setWordWrap(True)
        self.multi_hint_label.setStyleSheet("color: #9a9aa2; font-size: 12px;")
        self.multi_hint_label.setVisible(False)
        root.addWidget(self.multi_hint_label)

        # The form fields (UI-SPEC §18). QFormLayout gives the label-on-left /
        # field-on-right rows.
        form = QFormLayout()
        form.setSpacing(6)

        # Bubble # — bounded 0..9999 (T-4-08 tampering mitigation). 0 is the
        # UNSET sentinel (probe: value 0 -> text() '\u2014', value 1 -> '1',
        # negative input clamps to 0; the special text is display-only — typing
        # still edits normally). Commit on editingFinished (focus-loss or
        # Enter — the standard QSpinBox signal).
        self.bubble_spin = QSpinBox()
        self.bubble_spin.setRange(0, 9999)
        self.bubble_spin.setSpecialValueText("\u2014")
        self.bubble_spin.setValue(0)
        form.addRow("Bubble #", self.bubble_spin)

        # Origin — read-only, hue-coloured on load_box.
        self.origin_label = QLabel("\u2014")  # em dash placeholder
        form.addRow("Origin", self.origin_label)

        # Inpaint override + Std dev (plan 08-08, D-13/D-14 — UI-SPEC §38):
        # the Auto/Always/Never tri-state combo + its read-only companion row,
        # placed after Origin (decision metadata before the content fields).
        # The combo is the Phase 7 font-combo precedent: a non-editable
        # "Mixed" sentinel entry is added/removed dynamically for a
        # multi-selection whose values differ, is NEVER committed (Pitfall 7 —
        # the sentinel never leaves the widget layer), and the row stays
        # ENABLED in multi-select (A5 — an edit-all flag, unlike the per-box
        # content fields). Std dev is read-only always (per-box data, not
        # editable-all).
        self.inpaint_combo = QComboBox()
        self.inpaint_combo.setToolTip(
            "Whether Inpaint (C) cleans this box's detected text: Auto uses "
            "the std-dev gate (solid border = will clean, dashed = skipped), "
            "Always forces it, Never skips it."
        )
        form.addRow("Inpaint", self.inpaint_combo)

        self.std_dev_label = QLabel("\u2014")  # em dash placeholder (muted)
        self.std_dev_label.setObjectName("stdDevLabel")
        self.std_dev_label.setToolTip(
            "Color variation along this box's detected mask edge. Skipped when "
            "above the Std-dev threshold (Panel \u2192 Detection settings)."
        )
        form.addRow("Std dev", self.std_dev_label)

        # quick-260903-lm6: the read-only per-box detector confidence row,
        # mirroring the Std dev row (muted label, em dash when unknown).
        self.confidence_label = QLabel("\u2014")  # em dash placeholder (muted)
        self.confidence_label.setObjectName("confidenceLabel")
        self.confidence_label.setToolTip(
            "Detector confidence reported for this box. \u2014 means unknown "
            "(user-drawn or legacy box)."
        )
        form.addRow("Confidence", self.confidence_label)

        # Recognized + Translation — multi-line commit-on-focus-loss text edits.
        self.recognized_edit = _CommitTextEdit()
        self.recognized_edit.setPlaceholderText(_RECOGNIZED_PLACEHOLDER)
        self.recognized_edit.setAcceptRichText(False)  # plain text only (ASVS V5)
        form.addRow("Recognized", self.recognized_edit)

        self.translation_edit = _CommitTextEdit()
        self.translation_edit.setPlaceholderText(_TRANSLATION_PLACEHOLDER)
        self.translation_edit.setAcceptRichText(False)
        form.addRow("Translation", self.translation_edit)

        # Language — read-only informational (D-14: no language picker in v1).
        self.language_label = QLabel("\u2014")
        form.addRow("Language", self.language_label)

        # Vertical — LIVE since plan 07-05 (D-13); G-07-1: the checkbox
        # reads/writes style.vertical (the payload's `vertical` field is pure
        # export metadata the toggle never touches) and the MainWindow
        # re-renders the canvas + bake through the renderer's tategaki path
        # (Pitfall 9 — a toggle must re-render, not just write metadata). The
        # Phase 4 placeholder tooltip is REPLACED (D-13 copy). In a
        # multi-selection the checkbox becomes tri-state (indeterminate =
        # mixed vertical flags, D-10).
        self.vertical_check = QCheckBox("Vertical text")
        self.vertical_check.setToolTip(
            "Render this box's text vertically, top-to-bottom (tategaki). "
            "Roman letters stack upright, one above the other."
        )
        form.addRow("", self.vertical_check)

        # ------------------------------------------------------- Style section
        # Plan 07-05 (D-05 — UI-SPEC surface 33): the styling controls BELOW
        # the existing text fields. Section header (12px semibold muted) +
        # 1px divider, then the rows. One class-scope signal per commit-able
        # control (Shared Pattern 10); every commit is WR-01-gated.
        self.style_header = QLabel("Style")
        self.style_header.setObjectName("styleHeaderLabel")
        root.addWidget(self.style_header)
        self.style_divider = QFrame()
        self.style_divider.setObjectName("styleDivider")
        self.style_divider.setFixedHeight(1)
        root.addWidget(self.style_divider)

        # Font — QFontComboBox (Don't-Hand-Roll: system fonts + native preview,
        # RESEARCH §Don't Hand-Roll). Default "Liberation Sans" = TextStyle().
        # G-07-3: the compact Set-as-Default QToolButton rides the same row —
        # it emits the CURRENT combo family so MainWindow can persist the
        # app-level default font (the user's 'select a default font' action).
        # G-07-2: the 'Filter fonts…' line-edit directly above the row
        # contains-filters the family list (the QFontComboBox's built-in
        # incremental search only matches from the START of a family name —
        # 'Wild Words' cannot find 'CC Wild Words'). The QSortFilterProxyModel
        # filters a VIEW of the combo's own model; the source family list
        # stays intact (QFontDatabase remains the single source). The combo's
        # internal model is reparented to the proxy FIRST — QComboBox.setModel
        # deletes the model it previously owned, and that delete would
        # otherwise destroy the proxy's source (an empty dropdown).
        self.font_combo = QFontComboBox()
        self.font_combo.setToolTip("Font family for the selected box(es).")
        self.font_filter_edit = QLineEdit()
        self.font_filter_edit.setPlaceholderText("Filter fonts\u2026")
        self.font_filter_edit.setClearButtonEnabled(True)
        self.font_filter_edit.setToolTip(
            "Type any part of a font name to filter the family list "
            "(case-insensitive)."
        )
        self._font_proxy = QSortFilterProxyModel(self)
        _font_source = self.font_combo.model()
        _font_source.setParent(self._font_proxy)
        self._font_proxy.setSourceModel(_font_source)
        self._font_proxy.setFilterKeyColumn(0)
        self._font_proxy.setFilterCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.font_combo.setModel(self._font_proxy)
        self.font_filter_edit.textChanged.connect(self._on_font_filter_changed)
        form.addRow(self.font_filter_edit)  # directly above the Font row
        self.default_font_button = QToolButton()
        self.default_font_button.setText("Set as Default Font")
        self.default_font_button.setToolTip("Use this font for new boxes")
        self.default_font_button.clicked.connect(self._on_default_font_clicked)
        font_row = QWidget()
        font_h = QHBoxLayout(font_row)
        font_h.setContentsMargins(0, 0, 0, 0)
        font_h.setSpacing(4)
        font_h.addWidget(self.font_combo, 1)
        font_h.addWidget(self.default_font_button)
        form.addRow("Font", font_row)

        # Style — a per-family QComboBox (Regular/Italic/Bold/Bold Italic as
        # the font provides; repopulated on Font change — D-05).
        self.style_combo = QComboBox()
        self.style_combo.setToolTip("Font style (weight + slant).")
        form.addRow("Style", self.style_combo)

        # Size + Auto-fit (D-15): 0..1024 with "Auto" at 0 (the bubble_spin
        # sentinel pattern; 0..1024 matches the TextStyle font_size_px clamp
        # in core/text_style.py — quick-260825-wfy). The Auto-fit checkbox
        # couples the spin: checked
        # -> 0/Auto + disabled; unchecked -> enabled with the current rendered
        # size (rounded) as the starting manual value (UI-SPEC §33).
        self.size_spin = QSpinBox()
        self.size_spin.setRange(0, 1024)
        self.size_spin.setSpecialValueText("Auto")
        self.size_spin.setValue(0)
        self.auto_fit_check = QCheckBox("Auto-fit")
        self.auto_fit_check.setToolTip(
            "Shrink the text to fit inside the box automatically (default)."
            " Uncheck to use a fixed size that may overflow."
        )
        size_row = QWidget()
        size_h = QHBoxLayout(size_row)
        size_h.setContentsMargins(0, 0, 0, 0)
        size_h.setSpacing(4)
        size_h.addWidget(self.size_spin, 1)
        size_h.addWidget(self.auto_fit_check)
        form.addRow("Size", size_row)

        # Spacing H / Spacing V (quick-260824-viq): horizontal character
        # separation and vertical line/column separation, riding
        # style.char_spacing_px / style.line_spacing_px through the SHARED
        # renderer (measurement == render). The ranges match the TextStyle
        # V5 clamps (-64..64 / -256..256 — negatives TIGHTEN, letting the
        # letters sit closer than the font's natural advance) so the UI can
        # never produce a value the model would clamp differently.
        self.char_spacing_spin = QSpinBox()
        self.char_spacing_spin.setRange(-64, 64)
        self.char_spacing_spin.setSuffix(" px")
        self.char_spacing_spin.setValue(0)
        self.char_spacing_spin.setToolTip(
            "Extra horizontal gap between characters."
            " Negative values pull them closer together."
        )
        form.addRow("Spacing H", self.char_spacing_spin)

        self.line_spacing_spin = QSpinBox()
        self.line_spacing_spin.setRange(-256, 256)
        self.line_spacing_spin.setSuffix(" px")
        self.line_spacing_spin.setValue(0)
        self.line_spacing_spin.setToolTip(
            "Extra vertical gap between lines (or between stacked "
            "characters in vertical text). Negative values pull "
            "them closer together."
        )
        form.addRow("Spacing V", self.line_spacing_spin)

        # Fill — the 3-way glyph-fill selector (quick-260910-vej): Solid |
        # Gradient | Pattern, riding the shared QBrush fill path (the
        # renderer's style_fill_brush). In a multi-selection whose fill
        # TYPES differ, the non-editable "Mixed" sentinel entry is prepended
        # dynamically (the inpaint-combo pattern; Pitfall 7 — never
        # committed). The conditional sub-rows below (Color B + Angle for
        # gradient, Image… + Scale for pattern) show/hide per type; the UI
        # ranges read the model's PUBLIC constants so UI == clamp by
        # construction (the EFFECT_GEOM_MAX precedent).
        self.fill_combo = QComboBox()
        self.fill_combo.addItems(list(_FILL_ITEMS))
        self.fill_combo.setToolTip(
            "Glyph fill type: Solid (a plain color), Gradient (a linear "
            "two-color ramp at an angle), or Pattern (a tiled image clipped "
            "to the glyphs)."
        )
        form.addRow("Fill", self.fill_combo)

        # Color — the 24x24 swatch -> QColorDialog (Don't-Hand-Roll). The
        # split fill (color None) is the D-10 Mixed presentation.
        # quick-260909-nj9: the picker offers transparency (the glyph fill
        # stores #AARRGGBB); the swatch shows sub-opaque fills over a
        # checkerboard. quick-260910-vej: this MAIN swatch previews the REAL
        # fill (gradient ramp / tiled pattern) via the swatch's preview
        # state.
        self.color_swatch = _ColorSwatchButton()
        self.color_swatch.setToolTip(
            "Glyph fill color — choose one (with optional transparency) "
            "to apply it to the selection."
        )
        form.addRow("Color", self.color_swatch)

        # Color B — the gradient's second stop (quick-260910-vej). An
        # alpha-capable swatch like the MAIN Color (white->transparent fades
        # ride the same #AARRGGBB discipline). Hidden unless Gradient.
        self.fill_color_b_swatch = _ColorSwatchButton()
        self.fill_color_b_swatch.setToolTip(
            "Gradient second color (Color B) — with optional transparency."
        )
        form.addRow("Color B", self.fill_color_b_swatch)

        # Angle — the gradient direction, CLOCKWISE degrees (0 = left->right,
        # 90 = top->bottom; Color A at the start) — the same semantics the
        # TextStyle.fill_angle_deg field documents and the renderer's brush
        # factory implements. 0..359 so the UI can never produce a value the
        # V5 clamp (0..360) treats differently. Hidden unless Gradient.
        self.fill_angle_spin = QSpinBox()
        self.fill_angle_spin.setRange(0, 359)
        self.fill_angle_spin.setSuffix("\u00b0")
        self.fill_angle_spin.setValue(90)
        self.fill_angle_spin.setToolTip(
            "Gradient direction in degrees (clockwise): 0 = left to right, "
            "90 = top to bottom. The first color starts at the ramp's start."
        )
        form.addRow("Angle", self.fill_angle_spin)

        # Image… — the pattern tile picker (quick-260910-vej). Reads the file
        # BYTES in the panel; the 4 MB FILL_TILE_MAX_BYTES cap (imported from
        # the model — one shared symbol) shows a warning dialog on oversize
        # and commits NOTHING. Hidden unless Pattern.
        self.fill_image_button = QToolButton()
        self.fill_image_button.setText("Image\u2026")
        self.fill_image_button.setToolTip(
            "Choose an image tile to fill the glyphs with (repeated and "
            "clipped to the text). Max 4 MB."
        )
        form.addRow("Image", self.fill_image_button)

        # Scale — the pattern tile's uniform zoom, 0.10..10.00 x (the model's
        # PATTERN_SCALE bounds). Hidden unless Pattern.
        self.fill_scale_spin = QDoubleSpinBox()
        self.fill_scale_spin.setRange(0.10, 10.00)
        self.fill_scale_spin.setDecimals(2)
        self.fill_scale_spin.setSingleStep(0.05)
        self.fill_scale_spin.setValue(1.00)
        self.fill_scale_spin.setSuffix("\u00d7")
        self.fill_scale_spin.setToolTip(
            "Zoom the pattern tile before tiling (0.10x .. 10.00x)."
        )
        form.addRow("Scale", self.fill_scale_spin)

        # The fill sub-rows' label widgets (hidden with the fields so the
        # QFormLayout row collapses cleanly).
        self._fill_sub_labels = {}
        for widget in (
            self.fill_color_b_swatch,
            self.fill_angle_spin,
            self.fill_image_button,
            self.fill_scale_spin,
        ):
            self._fill_sub_labels[widget] = form.labelForField(widget)

        # Align / Align V — H and V alignment combos (one signal pair:
        # style_align_changed(h, v); model values, UI-SPEC §33).
        self.align_combo = QComboBox()
        self.align_combo.addItems(["Left", "Center", "Right"])
        form.addRow("Align", self.align_combo)
        self.align_v_combo = QComboBox()
        self.align_v_combo.addItems(["Top", "Middle", "Bottom"])
        form.addRow("Align V", self.align_v_combo)

        # Outline / Glow / Shadow — one row each: enable QCheckBox + 24x24
        # swatch + QSpinBox. Ranges read straight from the TextStyle model
        # constant (quick-260826-vhh): every row spans 0..int(EFFECT_GEOM_MAX)
        # so the UI can never produce a value the V5 coercion clamps
        # differently — a big SFX stroke/glow is intent. A disabled checkbox
        # greys the row's swatch+spin (_apply_effect_row_state).
        self._effect_checks: dict[str, QCheckBox] = {}
        self._effect_swatches: dict[str, _ColorSwatchButton] = {}
        self._effect_spins: dict[str, QSpinBox] = {}
        for key in ("outline", "glow", "shadow"):
            check = QCheckBox()
            swatch = _ColorSwatchButton()
            spin = QSpinBox()
            spin.setRange(0, int(EFFECT_GEOM_MAX))
            spin.setValue(_EFFECT_DEFAULT_VALUES[key])
            row = QWidget()
            row_h = QHBoxLayout(row)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(4)
            row_h.addWidget(check)
            row_h.addWidget(swatch)
            row_h.addWidget(spin, 1)
            form.addRow(key.title(), row)
            self._effect_checks[key] = check
            self._effect_swatches[key] = swatch
            self._effect_spins[key] = spin

        root.addLayout(form)
        root.addStretch(1)
        self.setStyleSheet(_INSPECTOR_QSS)

        # WR-01: the values the fields displayed at load_box time — a commit
        # whose value is unchanged is a no-op (see _emit_*_if_changed). The
        # InlineEditor's ``_entry_text`` pattern (inline_editor.py:211).
        self._loaded_bubble = 0
        self._loaded_recognized = ""
        self._loaded_translation = ""
        # Styling-section loaded memory (plan 07-05). The style/effect/vertical
        # entries are None when the D-10 Mixed sentinel is displayed.
        self._loaded_style_font = ""
        self._loaded_style_font_style = ""
        self._loaded_style_bold = False
        self._loaded_style_italic = False
        self._loaded_style_size = 0
        self._style_size_mixed = False
        # quick-260824-viq: the spacing spins' WR-01 loaded memories.
        self._loaded_char_spacing = 0
        self._loaded_line_spacing = 0
        self._loaded_rendered_size: float | None = None
        self._loaded_style_auto_fit = False
        self._loaded_style_color: str | None = "#e8e8ea"
        # quick-260910-vej: the Fill row's WR-01 loaded memories. The display
        # (combo text) / numeric entries are None when the D-10 Mixed
        # sentinel is displayed; the tile memory is the LOADED b64 payload
        # (re-picking the same bytes is a no-op).
        self._loaded_style_fill_display = "Solid"
        self._loaded_style_fill_color_b: str | None = "#ffffff"
        self._loaded_style_fill_angle: float | None = 90.0
        self._loaded_style_pattern_scale: float | None = 1.0
        self._loaded_style_pattern_tile: str | None = None
        self._loaded_style_align_h = "Center"
        self._loaded_style_align_v = "Middle"
        self._loaded_effects: dict = {
            "outline": {"enabled": True, "color": "#ffffff", "value": 2},
            "glow": {"enabled": False, "color": "#e8e8ea", "value": 4},
            "shadow": {"enabled": False, "color": "#000000", "value": 2},
        }
        self._effect_mixed: dict = {
            "outline": False, "glow": False, "shadow": False,
        }
        self._loaded_vertical = False
        # Plan 08-08: the Inpaint combo's loaded-commit guard (WR-01 — a
        # currentIndexChanged whose value equals the loaded value is a no-op).
        self._loaded_inpaint = ""
        # Wired style callbacks (for the direct test hooks — the real commit
        # paths are the widget signals wired in connect_commit_handlers).
        self._cb_style_color = None
        self._cb_style_effect = None
        self._cb_style_size = None
        self._cb_style_fill = None
        # quick-260824-t64 Task 3: live Size commits. editingFinished only
        # fires on focus-loss/Enter — NOT per click of the up/down arrows or a
        # scroll-wheel step, which is why font-size changes only rendered
        # after clicking away. A short single-shot debounce coalesces rapid
        # valueChanged steps into one commit through the SAME seam as
        # editingFinished (_emit_style_size_if_changed: WR-01 + Mixed-sentinel
        # guards stay load-bearing; programmatic loads are silent via
        # blockSignals so they never start this timer).
        self._size_debounce = QTimer(self)
        self._size_debounce.setInterval(150)
        self._size_debounce.setSingleShot(True)
        self._size_debounce.timeout.connect(self._on_size_debounce_timeout)

        # Start in the empty state (no box selected).
        self.clear()

    # ------------------------------------------------------------- population
    def is_text_edit_active(self) -> bool:
        """True iff an in-progress commit-deferred edit session lives in one
        of the two ``_CommitTextEdit`` fields; external reloads must not land
        while this is True (quick-260822-vk7).

        The recognized + translation fields commit on focus-out only, so a
        ``load_box`` that lands mid-typing visibly wipes uncommitted
        keystrokes. The MainWindow consults this probe before every
        selection-follower reload.
        """
        return self.translation_edit.hasFocus() or self.recognized_edit.hasFocus()

    def load_box(self, pagebox, rendered_size_px: float | None = None) -> None:
        """Populate the fields from the given ``pagebox`` (the selection follower).

        ``rendered_size_px`` (plan 07-05): the box's CURRENT rendered font size
        (the renderer's auto-fit result, supplied by the MainWindow) — the
        starting manual value when the user unchecks Auto-fit (D-15/UI-SPEC §33).
        ``None`` falls back to the style's own size (or 0/Auto).

        Blocks all field signals during population so the ``setValue`` /
        ``setPlainText`` calls do NOT re-emit the change signals (which would
        spurious-commit the just-loaded values back onto the pagebox). Hue-
        colours the Origin label per the box origin.
        """
        # G-07-2: the font filter never leaks into a load — clearing it
        # emits textChanged -> the proxy resets to the FULL family list.
        self.font_filter_edit.clear()
        # Bubble # (None -> 0 as the unset sentinel; the field still enables).
        bubble = pagebox.bubble_no if pagebox.bubble_no is not None else 0
        was = self.bubble_spin.blockSignals(True)
        self.bubble_spin.setValue(bubble)
        self.bubble_spin.blockSignals(was)
        self._loaded_bubble = self.bubble_spin.value()  # WR-01 (spinbox guard)

        # Origin — hue-coloured label text (UI-SPEC §18).
        origin = pagebox.origin
        hue = _ORIGIN_HUE_HEX.get(origin, _ORIGIN_HUE_HEX[DETECTED])
        text = _ORIGIN_LABEL.get(origin, origin.capitalize())
        self.origin_label.setText(text)
        self.origin_label.setStyleSheet(f"color: {hue}; font-weight: 600;")

        # Inpaint override (plan 08-08) — the box's tri-state mapping
        # (None -> "Auto", "always" -> "Always", "never" -> "Never") with
        # blockSignals, then the WR-01 loaded-memory guard; Std dev shows the
        # box's computed value or the em dash (read-only).
        self._set_inpaint_combo(
            _INPAINT_DISPLAY.get(pagebox.inpaint_override, "Auto"), mixed=False
        )
        self._loaded_inpaint = self.inpaint_combo.currentText()
        self._set_std_dev_text(pagebox.std_dev)
        # quick-260903-lm6: the per-box detector confidence (percentage or em
        # dash); getattr tolerates PageBoxes from older call sites.
        self._set_confidence_text(getattr(pagebox, "confidence", None))

        # Recognized text (str/list aware — TextBlock.text may be a list).
        recognized = ""
        if pagebox.payload is not None:
            t = getattr(pagebox.payload, "text", None)
            if isinstance(t, list):
                recognized = "".join(str(s) for s in t).strip()
            elif t is not None:
                recognized = str(t).strip()
        was_r = self.recognized_edit.blockSignals(True)
        self.recognized_edit.setPlainText(recognized)
        self.recognized_edit.blockSignals(was_r)
        # WR-01: remember the displayed value (read back from the widget so
        # Qt text normalization cannot create a phantom diff) — a focus-out
        # commit that leaves it unchanged is a no-op.
        self._loaded_recognized = self.recognized_edit.toPlainText()

        # Translation.
        translation = ""
        if pagebox.payload is not None:
            tr = getattr(pagebox.payload, "translation", "") or ""
            translation = str(tr)
        was_t = self.translation_edit.blockSignals(True)
        self.translation_edit.setPlainText(translation)
        self.translation_edit.blockSignals(was_t)
        self._loaded_translation = self.translation_edit.toPlainText()

        # Language (payload — read-only label) + vertical (STYLE-driven,
        # G-07-1: the checkbox mirrors style.vertical; the payload's vertical
        # field is export metadata only).
        language = "unknown"
        if pagebox.payload is not None:
            language = str(getattr(pagebox.payload, "language", "unknown") or "unknown")
        vertical = bool(pagebox.style.vertical) if pagebox.style is not None else False
        self.language_label.setText(language)
        was_v = self.vertical_check.blockSignals(True)
        self.vertical_check.setTristate(False)
        self.vertical_check.setChecked(vertical)
        self.vertical_check.blockSignals(was_v)
        self._loaded_vertical = vertical

        # Style section (plan 07-05) — the box's flat per-box TextStyle
        # (defaults when the box has none — D-06; uniform values, never Mixed).
        style = pagebox.style if pagebox.style is not None else TextStyle()
        self._load_style_section(style, rendered_size_px)
        self.multi_hint_label.setVisible(False)

        # Enable all fields + hide the empty-state copy. Both gates: the
        # per-box fields (incl. the read-only Origin/Language labels — D-10
        # multi-select disables them) and the whole-panel empty gate.
        self._set_text_fields_enabled(True)
        self._set_fields_enabled(True)
        self._apply_auto_fit_spin_state()
        for key in self._effect_checks:
            self._apply_effect_row_state(key)
        self.empty_label.setVisible(False)

    def load_multi_selection(self, pageboxes) -> None:
        """D-10 common-value/Mixed population for a MULTI-selection.

        Computes the per-control value set across the selection: all equal ->
        the value; differing -> the Mixed sentinel per widget (combo "Mixed"
        entries, size-spin "Mixed" special text, split swatch, tri-state
        checkboxes). The sentinel NEVER leaves the widget layer (RESEARCH
        Pitfall 7): a commit only fires when the user actively changes a
        control and always carries a real value (T-07-11). Per-box text
        fields disable (per-box content, D-10) while the styling section +
        vertical checkbox stay ENABLED (edit-all); the muted hint shows the
        exact selection count.
        """
        # G-07-2: same as load_box — the filter never leaks into a
        # multi-selection load (the combo population sees the full list).
        self.font_filter_edit.clear()
        styles = [
            pb.style if pb.style is not None else TextStyle() for pb in pageboxes
        ]
        n = len(pageboxes)

        # Enable everything, then disable the per-box fields (D-10).
        self._set_fields_enabled(True)
        self._set_text_fields_enabled(False)
        self.multi_hint_label.setText(
            f"Style edits apply to all {n} selected boxes."
        )
        self.multi_hint_label.setVisible(True)
        self.empty_label.setVisible(False)

        self._loaded_rendered_size = None
        self._style_size_mixed = False
        self._effect_mixed = {k: False for k in self._effect_checks}

        # Font — all-equal -> the family; differing -> the "Mixed" entry.
        fonts = {s.font_family for s in styles}
        was = self.font_combo.blockSignals(True)
        if len(fonts) == 1:
            self.font_combo.setCurrentText(next(iter(fonts)))
            self._loaded_style_font = self.font_combo.currentText()
        else:
            self.font_combo.setCurrentText("Mixed")
            self._loaded_style_font = "Mixed"
        self.font_combo.blockSignals(was)

        # Style (bold/italic) — common-value rule on the display names.
        self._loaded_style_bold = False
        self._loaded_style_italic = False
        style_names = {
            _FONT_STYLE_NAME.get((bool(s.bold), bool(s.italic)), "Regular")
            for s in styles
        }
        if len(style_names) == 1:
            self._select_combo(
                self.style_combo, list(style_names), next(iter(style_names))
            )
            self._loaded_style_font_style = self.style_combo.currentText()
        else:
            self._select_combo(self.style_combo, ["Mixed"], "Mixed")
            self._loaded_style_font_style = "Mixed"

        # Size + Auto-fit — differing sizes OR auto-fit states -> Mixed.
        auto_fits = {bool(s.auto_fit) for s in styles}
        sizes = {
            int(round(float(s.font_size_px)))
            if (s.font_size_px is not None and not s.auto_fit)
            else 0
            for s in styles
        }
        was = self.auto_fit_check.blockSignals(True)
        if len(auto_fits) == 1:
            auto_fit = next(iter(auto_fits))
            self.auto_fit_check.setTristate(False)
            self.auto_fit_check.setChecked(auto_fit)
            self._loaded_style_auto_fit = auto_fit
        else:
            self.auto_fit_check.setTristate(True)
            self.auto_fit_check.setCheckState(Qt.CheckState.PartiallyChecked)
            self._loaded_style_auto_fit = None
        self.auto_fit_check.blockSignals(was)
        was = self.size_spin.blockSignals(True)
        if len(auto_fits) > 1 or len(sizes) > 1:
            self.size_spin.setSpecialValueText("Mixed")
            self.size_spin.setValue(0)
            self._style_size_mixed = True
            self._loaded_style_size = 0
        else:
            self.size_spin.setSpecialValueText("Auto")
            self.size_spin.setValue(next(iter(sizes)))
            self._loaded_style_size = self.size_spin.value()
        self.size_spin.blockSignals(was)

        # quick-260824-viq: the spacing spins load the PRIMARY box's values
        # with NO tri-state — a deliberate simplification for this task (a
        # commit applies to ALL selected boxes through _replace_style like
        # every other style row). The align/effect mixed-sentinel machinery
        # above is the upgrade path if per-axis Mixed is ever needed.
        primary = styles[0]
        was = self.char_spacing_spin.blockSignals(True)
        self.char_spacing_spin.setValue(
            int(round(float(getattr(primary, "char_spacing_px", 0.0) or 0.0)))
        )
        self.char_spacing_spin.blockSignals(was)
        self._loaded_char_spacing = self.char_spacing_spin.value()
        was = self.line_spacing_spin.blockSignals(True)
        self.line_spacing_spin.setValue(
            int(round(float(getattr(primary, "line_spacing_px", 0.0) or 0.0)))
        )
        self.line_spacing_spin.blockSignals(was)
        self._loaded_line_spacing = self.line_spacing_spin.value()

        # Color — all-equal -> solid swatch; differing -> the split swatch.
        colors = {s.color for s in styles}
        if len(colors) == 1:
            color = next(iter(colors))
            self._loaded_style_color = color
            self._set_swatch_color(self.color_swatch, color)
        else:
            self._loaded_style_color = None
            self._set_swatch_color(self.color_swatch, None)

        # Fill (quick-260910-vej) — per-field common-value rule. Differing
        # fill TYPES prepend the non-editable "Mixed" sentinel entry (never
        # committed, Pitfall 7) and HIDE the sub-rows (no single fill type
        # governs them); a single type with differing angle/scale/tile shows
        # the per-widget Mixed sentinel (spin special text / split swatch).
        fill_types = {s.fill_type for s in styles}
        if len(fill_types) == 1:
            display = _FILL_MODEL_TO_DISPLAY.get(next(iter(fill_types)), "Solid")
            self._select_combo(self.fill_combo, list(_FILL_ITEMS), display)
            self._loaded_style_fill_display = display
        else:
            self._select_combo(
                self.fill_combo, ["Mixed"] + list(_FILL_ITEMS), "Mixed"
            )
            self._loaded_style_fill_display = "Mixed"

        angles = {int(round(float(s.fill_angle_deg))) for s in styles}
        was = self.fill_angle_spin.blockSignals(True)
        if len(fill_types) == 1 and len(angles) == 1:
            self.fill_angle_spin.setSpecialValueText("")
            self.fill_angle_spin.setValue(next(iter(angles)))
            self._loaded_style_fill_angle = float(self.fill_angle_spin.value())
        else:
            self.fill_angle_spin.setSpecialValueText("Mixed")
            self.fill_angle_spin.setValue(0)
            self._loaded_style_fill_angle = None
        self.fill_angle_spin.blockSignals(was)

        scales = {round(float(s.pattern_scale), 2) for s in styles}
        was = self.fill_scale_spin.blockSignals(True)
        if len(fill_types) == 1 and len(scales) == 1:
            self.fill_scale_spin.setSpecialValueText("")
            self.fill_scale_spin.setValue(next(iter(scales)))
            self._loaded_style_pattern_scale = float(self.fill_scale_spin.value())
        else:
            self.fill_scale_spin.setSpecialValueText("Mixed")
            self.fill_scale_spin.setValue(0.10)  # the minimum shows "Mixed"
            self._loaded_style_pattern_scale = None
        self.fill_scale_spin.blockSignals(was)

        colors_b = {s.fill_color_b for s in styles}
        if len(fill_types) == 1 and len(colors_b) == 1:
            self._loaded_style_fill_color_b = next(iter(colors_b))
            self._set_swatch_color(self.fill_color_b_swatch, next(iter(colors_b)))
        else:
            self._loaded_style_fill_color_b = None
            self._set_swatch_color(self.fill_color_b_swatch, None)

        tiles = {s.pattern_tile_b64 for s in styles}
        if len(fill_types) == 1 and len(tiles) == 1:
            self._loaded_style_pattern_tile = next(iter(tiles))
        else:
            self._loaded_style_pattern_tile = None
        self._update_fill_image_button_tooltip(self._loaded_style_pattern_tile)

        self._apply_fill_preview(styles)
        self._update_fill_row_visibility()

        # Aligns. A differing axis shows the leading "Mixed" entry AND keeps
        # the real options selectable (G-07-7 — the override must be pickable);
        # a uniform axis shows the plain real-item list, never Mixed.
        aligns_h = {s.align_h for s in styles}
        aligns_v = {s.align_v for s in styles}
        if len(aligns_h) == 1:
            display = _ALIGN_H_DISPLAY.get(next(iter(aligns_h)), "Center")
            self._select_combo(
                self.align_combo, ["Left", "Center", "Right"], display
            )
            self._loaded_style_align_h = display
        else:
            self._select_combo(
                self.align_combo, ["Mixed", "Left", "Center", "Right"], "Mixed"
            )
            self._loaded_style_align_h = "Mixed"
        if len(aligns_v) == 1:
            display = _ALIGN_V_DISPLAY.get(next(iter(aligns_v)), "Middle")
            self._select_combo(
                self.align_v_combo, ["Top", "Middle", "Bottom"], display
            )
            self._loaded_style_align_v = display
        else:
            self._select_combo(
                self.align_v_combo, ["Mixed", "Top", "Middle", "Bottom"], "Mixed"
            )
            self._loaded_style_align_v = "Mixed"

        # Effects — per-row common-value; a differing row shows the tri-state
        # checkbox + split swatch + "Mixed" spin special text.
        for key in ("outline", "glow", "shadow"):
            self._load_effect_row_multi(key, styles)

        # Vertical checkbox — differing style.vertical flags -> tri-state
        # (D-10; G-07-1: the checkbox reads the per-box STYLE flag, not the
        # export-metadata payload flag — a style-None box reads False, so
        # bare-marker payloads stay safe without a getattr contract).
        verticals = {
            (pb.style.vertical if pb.style is not None else False)
            for pb in pageboxes
        }
        was = self.vertical_check.blockSignals(True)
        if len(verticals) == 1:
            vertical = next(iter(verticals))
            self.vertical_check.setTristate(False)
            self.vertical_check.setChecked(vertical)
            self._loaded_vertical = vertical
        else:
            self.vertical_check.setTristate(True)
            self.vertical_check.setCheckState(Qt.CheckState.PartiallyChecked)
            self._loaded_vertical = None
        self.vertical_check.blockSignals(was)

        # Inpaint override (plan 08-08, A5 — the row stays ENABLED in
        # multi-select as an edit-all flag): common value -> that value;
        # differing values -> the non-editable "Mixed" sentinel entry (added
        # dynamically, never committed — Pitfall 7). Std dev is per-box data
        # (not editable-all) -> always the em dash.
        overrides = {
            _INPAINT_DISPLAY.get(pb.inpaint_override, "Auto") for pb in pageboxes
        }
        if len(overrides) == 1:
            self._set_inpaint_combo(next(iter(overrides)), mixed=False)
        else:
            self._set_inpaint_combo("Mixed", mixed=True)
        self._loaded_inpaint = self.inpaint_combo.currentText()
        self._set_std_dev_text(None)
        # quick-260903-lm6: multi-selection is per-box-ambiguous -> the em dash
        # (the Std dev mirror — a stale single-box value must never linger).
        self._set_confidence_text(None)

        self._apply_auto_fit_spin_state()
        for key in self._effect_checks:
            self._apply_effect_row_state(key)

    # ----------------------------------------------- style-section population
    def _load_style_section(
        self, style: TextStyle, rendered_size_px: float | None = None
    ) -> None:
        """Populate the Style section from ONE box's flat TextStyle (D-06).

        Single-selection (or the empty-state reset): every control shows the
        box's real values — uniform, never Mixed. The Auto-fit checkbox
        couples the size spin (checked -> 0/disabled; unchecked -> the
        rendered-size hint as the manual start, D-15).
        """
        self._loaded_rendered_size = rendered_size_px
        self._style_size_mixed = False
        self._effect_mixed = {k: False for k in self._effect_checks}

        was = self.font_combo.blockSignals(True)
        self.font_combo.setCurrentText(style.font_family)
        self.font_combo.blockSignals(was)
        self._loaded_style_font = self.font_combo.currentText()

        self._loaded_style_bold = bool(style.bold)
        self._loaded_style_italic = bool(style.italic)
        self._refresh_style_combo(style.font_family, style.bold, style.italic)

        auto_fit = bool(style.auto_fit)
        was = self.auto_fit_check.blockSignals(True)
        self.auto_fit_check.setTristate(False)
        self.auto_fit_check.setChecked(auto_fit)
        self.auto_fit_check.blockSignals(was)
        self._loaded_style_auto_fit = auto_fit
        was = self.size_spin.blockSignals(True)
        self.size_spin.setSpecialValueText("Auto")
        if auto_fit or style.font_size_px is None:
            self.size_spin.setValue(0)
        else:
            self.size_spin.setValue(int(round(float(style.font_size_px))))
        self.size_spin.blockSignals(was)
        self._loaded_style_size = self.size_spin.value()

        # quick-260824-viq: the spacing spins (WR-01 loaded memory follows
        # the display; clear() resets both through this same path with the
        # default TextStyle).
        was = self.char_spacing_spin.blockSignals(True)
        self.char_spacing_spin.setValue(
            int(round(float(getattr(style, "char_spacing_px", 0.0) or 0.0)))
        )
        self.char_spacing_spin.blockSignals(was)
        self._loaded_char_spacing = self.char_spacing_spin.value()
        was = self.line_spacing_spin.blockSignals(True)
        self.line_spacing_spin.setValue(
            int(round(float(getattr(style, "line_spacing_px", 0.0) or 0.0)))
        )
        self.line_spacing_spin.blockSignals(was)
        self._loaded_line_spacing = self.line_spacing_spin.value()

        self._loaded_style_color = style.color
        self._set_swatch_color(self.color_swatch, style.color)

        # quick-260910-vej: the Fill row — type, conditional sub-controls,
        # and the MAIN swatch's real-fill preview state (uniform values,
        # never Mixed on the single path).
        display = _FILL_MODEL_TO_DISPLAY.get(style.fill_type, "Solid")
        self._select_combo(self.fill_combo, list(_FILL_ITEMS), display)
        self._loaded_style_fill_display = display
        self._loaded_style_fill_color_b = style.fill_color_b
        self._set_swatch_color(self.fill_color_b_swatch, style.fill_color_b)
        was = self.fill_angle_spin.blockSignals(True)
        self.fill_angle_spin.setSpecialValueText("")
        self.fill_angle_spin.setValue(
            max(0, min(359, int(round(float(style.fill_angle_deg)))))
        )
        self.fill_angle_spin.blockSignals(was)
        self._loaded_style_fill_angle = float(self.fill_angle_spin.value())
        was = self.fill_scale_spin.blockSignals(True)
        self.fill_scale_spin.setSpecialValueText("")
        self.fill_scale_spin.setValue(
            max(0.10, min(10.0, float(style.pattern_scale)))
        )
        self.fill_scale_spin.blockSignals(was)
        self._loaded_style_pattern_scale = float(self.fill_scale_spin.value())
        self._loaded_style_pattern_tile = style.pattern_tile_b64
        self._update_fill_image_button_tooltip(style.pattern_tile_b64)
        self._apply_fill_preview([style])
        self._update_fill_row_visibility()

        align_h = _ALIGN_H_DISPLAY.get(style.align_h, "Center")
        align_v = _ALIGN_V_DISPLAY.get(style.align_v, "Middle")
        self._select_combo(self.align_combo, ["Left", "Center", "Right"], align_h)
        self._loaded_style_align_h = align_h
        self._select_combo(self.align_v_combo, ["Top", "Middle", "Bottom"], align_v)
        self._loaded_style_align_v = align_v

        for key in ("outline", "glow", "shadow"):
            self._load_effect_row(key, getattr(style, key))

    def _load_effect_row(self, key: str, effect) -> None:
        """Populate ONE effect row from a real effect dict (uniform values)."""
        effect = effect if isinstance(effect, dict) else {}
        enabled = bool(effect.get("enabled", False))
        color = str(effect.get("color", _EFFECT_DEFAULT_COLORS[key]))
        if key == "outline":
            value = int(round(float(effect.get("width_px", 2.0) or 0.0)))
        elif key == "glow":
            value = int(round(float(effect.get("radius_px", 4.0) or 0.0)))
        else:
            value = int(round(float(effect.get("dx", 2.0) or 0.0)))
        check = self._effect_checks[key]
        was = check.blockSignals(True)
        check.setTristate(False)
        check.setChecked(enabled)
        check.blockSignals(was)
        self._set_swatch_color(self._effect_swatches[key], color)
        spin = self._effect_spins[key]
        was = spin.blockSignals(True)
        spin.setSpecialValueText("")
        spin.setValue(value)
        spin.blockSignals(was)
        self._loaded_effects[key] = {
            "enabled": enabled, "color": color, "value": value,
        }
        self._effect_mixed[key] = False
        self._apply_effect_row_state(key)

    def _load_effect_row_multi(self, key: str, styles: list) -> None:
        """Populate ONE effect row across a multi-selection (D-10 Mixed)."""

        def _effect_of(s) -> dict:
            e = getattr(s, key)
            return e if isinstance(e, dict) else {}

        enableds = {bool(_effect_of(s).get("enabled", False)) for s in styles}
        colors = {
            str(_effect_of(s).get("color", _EFFECT_DEFAULT_COLORS[key]))
            for s in styles
        }
        if key == "outline":
            values = {
                int(round(float(_effect_of(s).get("width_px", 2.0) or 0.0)))
                for s in styles
            }
        elif key == "glow":
            values = {
                int(round(float(_effect_of(s).get("radius_px", 4.0) or 0.0)))
                for s in styles
            }
        else:
            values = {
                int(round(float(_effect_of(s).get("dx", 2.0) or 0.0)))
                for s in styles
            }
        mixed = len(enableds) > 1 or len(colors) > 1 or len(values) > 1
        check = self._effect_checks[key]
        was = check.blockSignals(True)
        if mixed:
            check.setTristate(True)
            check.setCheckState(Qt.CheckState.PartiallyChecked)
        else:
            check.setTristate(False)
            check.setChecked(next(iter(enableds)))
        check.blockSignals(was)
        swatch = self._effect_swatches[key]
        if len(colors) == 1:
            self._set_swatch_color(swatch, next(iter(colors)))
        else:
            self._set_swatch_color(swatch, None)
        spin = self._effect_spins[key]
        was = spin.blockSignals(True)
        if mixed:
            spin.setSpecialValueText("Mixed")
            spin.setValue(0)
        else:
            spin.setSpecialValueText("")
            spin.setValue(next(iter(values)))
        spin.blockSignals(was)
        self._effect_mixed[key] = mixed
        self._loaded_effects[key] = {
            "enabled": None if mixed else next(iter(enableds)),
            "color": None if mixed else next(iter(colors)),
            "value": None if mixed else next(iter(values)),
        }
        self._apply_effect_row_state(key)

    # ------------------------------------------------- fill row (quick-260910-vej)
    def _update_fill_row_visibility(self) -> None:
        """Show/hide the fill sub-rows per the selected fill type (Gradient
        reveals Color B + Angle; Pattern reveals Image… + Scale). The
        QFormLayout label hides with the field so the row collapses."""
        display = self.fill_combo.currentText()
        show_gradient = display == "Gradient"
        show_pattern = display == "Pattern"
        for widget, show in (
            (self.fill_color_b_swatch, show_gradient),
            (self.fill_angle_spin, show_gradient),
            (self.fill_image_button, show_pattern),
            (self.fill_scale_spin, show_pattern),
        ):
            widget.setVisible(show)
            label = self._fill_sub_labels.get(widget)
            if label is not None:
                label.setVisible(show)

    def _update_fill_image_button_tooltip(self, tile_b64: str | None) -> None:
        """The Image… button's tooltip carries the loaded tile's decoded
        dimensions (or the mixed/absent state) — a cheap honest summary."""
        img = _decode_preview_tile(tile_b64)
        if img is not None:
            self.fill_image_button.setToolTip(
                f"Pattern tile loaded ({img.width()}x{img.height()} px). "
                "Click to choose another image."
            )
        elif tile_b64 is None and self._loaded_style_fill_display == "Mixed":
            self.fill_image_button.setToolTip(
                "Pattern tile differs across the selection."
            )
        else:
            self.fill_image_button.setToolTip(
                "Choose an image tile to fill the glyphs with (repeated and "
                "clipped to the text). Max 4 MB."
            )

    def _apply_fill_preview(self, styles: list) -> None:
        """Point the MAIN Color swatch's preview state at the REAL fill
        (LOCKED UI decision, quick-260910-vej): a gradient selection previews
        the ramp, a pattern selection the tiled tile; Mixed/uniform-solid
        states keep the solid/split paint. Cosmetic only — the renderer's
        brush factory is the render-side authority."""
        swatch = self.color_swatch
        swatch.preview_mode = "solid"
        swatch.preview_color_b = None
        swatch.preview_angle = 90.0
        swatch.preview_tile = None
        if styles:
            fill_types = {s.fill_type for s in styles}
            if fill_types == {"gradient"}:
                colors_b = {s.fill_color_b for s in styles}
                if len(colors_b) == 1:
                    swatch.preview_mode = "gradient"
                    swatch.preview_color_b = next(iter(colors_b))
                    swatch.preview_angle = float(styles[0].fill_angle_deg)
            elif fill_types == {"pattern"}:
                tiles = {s.pattern_tile_b64 for s in styles}
                if len(tiles) == 1:
                    tile = _decode_preview_tile(next(iter(tiles)))
                    if tile is not None:
                        swatch.preview_mode = "pattern"
                        swatch.preview_tile = tile
        swatch.update()

    def _emit_fill_type_if_changed(self) -> None:
        """The Fill combo commit — WR-01-gated; the "Mixed" sentinel NEVER
        leaves the widget layer (Pitfall 7). Also live-updates the sub-row
        visibility (idempotent with the post-commit panel reload)."""
        text = self.fill_combo.currentText()
        self._update_fill_row_visibility()
        if text == self._loaded_style_fill_display:
            return  # WR-01: an unchanged cycle is a no-op
        if text == "Mixed":
            return  # the sentinel never leaves the widget layer (Pitfall 7)
        self.style_fill_changed.emit({"fill_type": _FILL_DISPLAY_TO_MODEL[text]})

    def _emit_fill_angle_if_changed(self) -> None:
        """The gradient Angle commit — WR-01-gated (a Mixed-sentinel no-op
        cycle on a mixed selection drops)."""
        value = self.fill_angle_spin.value()
        if self._loaded_style_fill_angle is None and value == 0:
            return  # a no-op focus cycle on the "Mixed" sentinel (Pitfall 7)
        if value == self._loaded_style_fill_angle:
            return  # WR-01: an unchanged focus cycle is a no-op
        self.style_fill_changed.emit({"fill_angle_deg": float(value)})

    def _emit_pattern_scale_if_changed(self) -> None:
        """The pattern Scale commit — WR-01-gated (the Mixed sentinel sits at
        the spin's minimum, 0.10)."""
        value = self.fill_scale_spin.value()
        if self._loaded_style_pattern_scale is None and value <= 0.10 + 1e-9:
            return  # a no-op focus cycle on the "Mixed" sentinel (Pitfall 7)
        if value == self._loaded_style_pattern_scale:
            return  # WR-01: an unchanged focus cycle is a no-op
        self.style_fill_changed.emit({"pattern_scale": float(value)})

    def _pick_fill_color_b(self) -> None:
        """Open the alpha-capable ``QColorDialog`` for the gradient's Color B;
        commit on pick (WR-01-gated, alpha-aware — the ``_norm_hex_a``
        discipline so re-picking the loaded color in another opaque spelling
        is a no-op). ``ShowAlphaChannel`` + ``DontUseNativeDialog`` are
        REQUIRED on Windows (the native dialog has no alpha control — the
        quick-260909-nj9 lesson)."""
        seed = self.fill_color_b_swatch.color
        if seed is None or self._loaded_style_fill_color_b is None:
            seed = "#ffffff"
        color = QColorDialog.getColor(
            QColor(seed),
            self,
            "Select Gradient Color B",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
            | QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if color.isValid():
            hex_argb = color.name(QColor.NameFormat.HexArgb)
            if _norm_hex_a(hex_argb) != _norm_hex_a(
                self._loaded_style_fill_color_b
            ):
                self.style_fill_changed.emit({"fill_color_b": hex_argb})

    def _pick_pattern_tile(self) -> None:
        """Pick + embed the pattern tile file (quick-260910-vej).

        Reads the file BYTES in the panel; an oversized file (above the
        shared ``FILL_TILE_MAX_BYTES`` cap) shows the LOCKED warning dialog
        and commits NOTHING (reject/oversize are both silent no-ops). On
        accept the commit carries the fill-type switch too
        (``{"fill_type": "pattern", "pattern_tile_b64": ...}``). WR-01:
        re-picking a file whose bytes equal the loaded tile is a no-op —
        the decoded b64 is compared against the loaded memory.
        """
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Select Pattern Tile",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*)",
        )
        if not path:
            return  # cancelled — nothing happens
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            logger.warning("Pattern tile read failed for {}: {}", path, exc)
            QMessageBox.warning(
                self,
                "Pattern Tile",
                f"The tile could not be read:\n{exc}",
            )
            return
        if len(data) > FILL_TILE_MAX_BYTES:
            # The LOCKED oversize guard: a warning dialog, never a silent
            # truncate, never a corrupt save.
            QMessageBox.warning(
                self,
                "Pattern Tile Too Large",
                f"The selected image is {len(data) / (1024 * 1024):.1f} MB, "
                f"above the {FILL_TILE_MAX_BYTES // (1024 * 1024)} MB tile "
                "limit.\nUse a smaller tile.",
            )
            return
        b64 = base64.b64encode(data).decode("ascii")
        if b64 == self._loaded_style_pattern_tile:
            return  # WR-01: the same bytes are already loaded — no-op
        self._loaded_style_pattern_tile = b64
        self._update_fill_image_button_tooltip(b64)
        self.style_fill_changed.emit(
            {"fill_type": "pattern", "pattern_tile_b64": b64}
        )

    def _commit_style_fill(self, changes: dict) -> None:
        """Direct fill-commit hook (the real paths are the combo/angle/scale/
        swatch/tile-dialog signals wired in connect_commit_handlers)."""
        if changes:
            self.style_fill_changed.emit(changes)

    def _refresh_style_combo(self, family: str, bold: bool, italic: bool) -> None:
        """Repopulate the Style combo for ``family`` + select ``(bold, italic)``.

        ``QFontDatabase.styles`` is the per-family source (Regular/Italic/
        Bold/Bold Italic as the font provides — Don't-Hand-Roll).
        """
        items = list(QFontDatabase.styles(family)) or ["Regular"]
        wanted = _FONT_STYLE_NAME.get((bool(bold), bool(italic)), "Regular")
        self._select_combo(self.style_combo, items, wanted)
        self._loaded_style_font_style = self.style_combo.currentText()

    def _select_combo(self, combo, items: list, select: str) -> None:
        """Replace ``combo``'s items and select ``select`` (signals blocked)."""
        was = combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        idx = items.index(select) if select in items else 0
        combo.setCurrentIndex(idx)
        combo.blockSignals(was)

    def _set_inpaint_combo(self, select: str, mixed: bool) -> None:
        """Set the Inpaint combo's entries + selection (signals blocked).

        Plan 08-08 (D-13/D-14): the Phase 7 font-combo pattern — the entry set
        is exactly Auto/Always/Never, with the non-editable "Mixed" sentinel
        entry ADDED dynamically (prepended) when ``mixed`` is True and REMOVED
        otherwise. The sentinel NEVER leaves the widget layer (Pitfall 7 — the
        commit guard in :meth:`_emit_inpaint_if_changed` drops it).
        """
        items = ["Mixed"] + _INPAINT_ITEMS if mixed else list(_INPAINT_ITEMS)
        self._select_combo(self.inpaint_combo, items, select)

    def _set_std_dev_text(self, std_dev) -> None:
        """The read-only Std dev label: ``f"{value:.1f}"`` or the em dash.

        The muted ``#9a9aa2`` style comes from ``QLabel#stdDevLabel`` in the
        panel QSS (applied at construction).
        """
        if std_dev is None:
            self.std_dev_label.setText("\u2014")
        else:
            self.std_dev_label.setText(f"{float(std_dev):.1f}")

    def _set_confidence_text(self, conf) -> None:
        """The read-only Confidence label (quick-260903-lm6): ``f"{v:.0%}"``
        (0.87 -> "87%") or the em dash when unknown.

        The muted ``#9a9aa2`` style comes from ``QLabel#confidenceLabel`` in
        the panel QSS (applied at construction).
        """
        if conf is None:
            self.confidence_label.setText("\u2014")
        else:
            self.confidence_label.setText(f"{float(conf):.0%}")

    def _set_swatch_color(self, swatch: _ColorSwatchButton, color) -> None:
        """Set a swatch's color (``None`` = the D-10 split/Mixed fill)."""
        swatch.color = color
        swatch.update()

    def _apply_auto_fit_spin_state(self) -> None:
        """Couple the size spin to the Auto-fit checkbox (UI-SPEC §33, D-15).

        Checked -> spin 0/"Auto" + disabled; unchecked -> spin enabled with
        the current rendered size (rounded) as the starting manual value.
        """
        checked = self.auto_fit_check.checkState() == Qt.CheckState.Checked
        was = self.size_spin.blockSignals(True)
        if checked:
            self.size_spin.setValue(0)
            self.size_spin.setEnabled(False)
        else:
            self.size_spin.setEnabled(True)
            if (
                self.size_spin.value() == 0
                and self._loaded_rendered_size is not None
            ):
                self.size_spin.setValue(int(round(self._loaded_rendered_size)))
        self.size_spin.blockSignals(was)

    def _apply_effect_row_state(self, key: str) -> None:
        """A disabled effect checkbox greys the row's swatch+spin (UI-SPEC §33).

        A MIXED row (tri-state indeterminate) keeps the swatch+spin ENABLED so
        the user can override via them (D-10).
        """
        check = self._effect_checks[key]
        if check.checkState() == Qt.CheckState.PartiallyChecked:
            self._effect_swatches[key].setEnabled(True)
            self._effect_spins[key].setEnabled(True)
            return
        enabled = check.checkState() == Qt.CheckState.Checked
        self._effect_swatches[key].setEnabled(enabled)
        self._effect_spins[key].setEnabled(enabled)

    def clear(self) -> None:
        """Show the empty-state copy and disable all fields (no box selected).

        The styling section resets to the DEFAULT ``TextStyle`` so a stale
        selection (or the D-10 Mixed sentinel) never lingers into the next
        load (Pitfall 7 — the sentinel never survives a clear either).
        """
        # G-07-2: the font filter resets with the empty state (the clear
        # emits textChanged -> the proxy resets to the full family list).
        self.font_filter_edit.clear()
        self.empty_label.setVisible(True)
        self.multi_hint_label.setVisible(False)
        self._load_style_section(TextStyle())
        self._loaded_vertical = False
        self._set_fields_enabled(False)
        # WR-01: reset the loaded-value memory so a late focus-out commit after
        # a clear cannot fire (fields are disabled anyway — belt-and-suspenders).
        self._loaded_bubble = 0
        self._loaded_recognized = ""
        self._loaded_translation = ""
        # Clear the field values too so a stale selection does not linger.
        was = self.bubble_spin.blockSignals(True)
        self.bubble_spin.setValue(0)  # reset to the unset sentinel 0
        self.bubble_spin.blockSignals(was)
        was_r = self.recognized_edit.blockSignals(True)
        self.recognized_edit.clear()
        self.recognized_edit.blockSignals(was_r)
        was_t = self.translation_edit.blockSignals(True)
        self.translation_edit.clear()
        self.translation_edit.blockSignals(was_t)
        self.origin_label.setText("\u2014")
        self.origin_label.setStyleSheet("")
        self.language_label.setText("\u2014")
        # Plan 08-08: the Inpaint combo resets to Auto (no Mixed sentinel) and
        # Std dev to the em dash; the WR-01 guard follows the display.
        self._set_inpaint_combo("Auto", mixed=False)
        self._loaded_inpaint = self.inpaint_combo.currentText()
        self._set_std_dev_text(None)
        # quick-260903-lm6: the Confidence row resets to the em dash too.
        self._set_confidence_text(None)
        was_v = self.vertical_check.blockSignals(True)
        self.vertical_check.setTristate(False)
        self.vertical_check.setChecked(False)
        self.vertical_check.blockSignals(was_v)

    def _set_fields_enabled(self, enabled: bool) -> None:
        """Enable/disable every editable field (the empty-state gate)."""
        for w in (
            self.bubble_spin,
            self.recognized_edit,
            self.translation_edit,
            self.vertical_check,
            self.font_combo,
            self.font_filter_edit,
            self.default_font_button,
            self.style_combo,
            self.size_spin,
            self.auto_fit_check,
            self.char_spacing_spin,
            self.line_spacing_spin,
            self.color_swatch,
            self.fill_combo,
            self.fill_color_b_swatch,
            self.fill_angle_spin,
            self.fill_image_button,
            self.fill_scale_spin,
            self.align_combo,
            self.align_v_combo,
            self.inpaint_combo,
            self.std_dev_label,
            self.confidence_label,
            *self._effect_checks.values(),
            *self._effect_swatches.values(),
            *self._effect_spins.values(),
        ):
            w.setEnabled(enabled)

    def _set_text_fields_enabled(self, enabled: bool) -> None:
        """Enable/disable the PER-BOX content fields (D-10 — disabled at N>1).

        The styling section + vertical checkbox stay enabled in a
        multi-selection (edits ALL selected, D-10); only the per-box fields
        (Bubble #, Origin, Recognized, Translation, Language) follow this.
        """
        for w in (
            self.bubble_spin,
            self.origin_label,
            self.recognized_edit,
            self.translation_edit,
            self.language_label,
        ):
            w.setEnabled(enabled)

    # ------------------------------------------------------- commit wiring
    def connect_commit_handlers(
        self,
        on_recognized,
        on_translation,
        on_bubble,
        on_vertical,
        on_style_font=None,
        on_style_font_style=None,
        on_style_size=None,
        on_style_auto_fit=None,
        on_style_color=None,
        on_style_align=None,
        on_style_effect=None,
        on_style_char_spacing=None,
        on_style_line_spacing=None,
        on_style_fill=None,
        on_inpaint_override=None,
    ) -> None:
        """Wire each field's commit signal to the MainWindow-supplied callbacks.

        The MainWindow owns the pagebox mutation + ``boxes_modified`` push +
        overlay refresh; this method is the single point where the panel's
        change signals are routed to those callbacks. QTextEdits commit on
        focus-loss / Ctrl+Return (``_CommitTextEdit``); QSpinBox/QCheckBox on
        ``editingFinished`` / ``stateChanged``; combos on ``currentIndexChanged``
        (all WR-01-gated against the ``_loaded_*`` memory). The style-section
        callbacks are optional keyword args (the Phase 4 callers pass the
        first four only — backward compatible).
        """
        self.recognized_edit.committed.connect(
            lambda: self._emit_recognized_if_changed(on_recognized)
        )
        self.translation_edit.committed.connect(
            lambda: self._emit_translation_if_changed(on_translation)
        )
        self.bubble_spin.editingFinished.connect(
            lambda: self._emit_bubble_if_changed(on_bubble)
        )
        self.vertical_check.stateChanged.connect(
            lambda _state: self._commit_vertical(on_vertical)
        )

        # ---- Style section (D-05) — one commit signal per control.
        if on_style_font is not None:
            self.font_combo.currentTextChanged.connect(
                lambda family: self._on_font_widget_changed(family, on_style_font)
            )
        if on_style_font_style is not None:
            self.style_combo.currentTextChanged.connect(
                lambda name: self._emit_style_font_style_if_changed(
                    name, on_style_font_style
                )
            )
        if on_style_size is not None:
            self.size_spin.editingFinished.connect(
                lambda: self._emit_style_size_if_changed(on_style_size)
            )
            # quick-260824-t64 Task 3: ALSO commit live on valueChanged (the
            # up/down arrows + scroll wheel never fire editingFinished). The
            # debounce restarts per step; the timeout routes through the same
            # WR-01-gated emitter as editingFinished.
            self._cb_style_size = on_style_size
            self.size_spin.valueChanged.connect(
                lambda _value: self._size_debounce.start()
            )
        if on_style_auto_fit is not None:
            self.auto_fit_check.stateChanged.connect(
                lambda _s: self._commit_auto_fit(on_style_auto_fit)
            )
        # quick-260824-viq: the spacing spins commit on editingFinished with
        # the WR-01 emit-if-changed pattern (_emit_style_size_if_changed is
        # the template — an unchanged focus cycle is a no-op).
        if on_style_char_spacing is not None:
            self.char_spacing_spin.editingFinished.connect(
                lambda: self._emit_char_spacing_if_changed(on_style_char_spacing)
            )
        if on_style_line_spacing is not None:
            self.line_spacing_spin.editingFinished.connect(
                lambda: self._emit_line_spacing_if_changed(on_style_line_spacing)
            )
        if on_style_color is not None:
            self.color_swatch.clicked.connect(
                lambda: self._pick_style_color(on_style_color)
            )
            self._cb_style_color = on_style_color
        # quick-260910-vej: the Fill row's commit wiring — the class-scope
        # style_fill_changed signal carries the changed-fields dict to the
        # MainWindow callback, and the combo / Angle / Color B / Scale /
        # Image… emitters all route through it (each commit carries only the
        # fields the user actually changed).
        if on_style_fill is not None:
            self._cb_style_fill = on_style_fill
            self.style_fill_changed.connect(on_style_fill)
            self.fill_combo.currentIndexChanged.connect(
                lambda _i: self._emit_fill_type_if_changed()
            )
            self.fill_angle_spin.editingFinished.connect(
                self._emit_fill_angle_if_changed
            )
            self.fill_color_b_swatch.clicked.connect(self._pick_fill_color_b)
            self.fill_scale_spin.editingFinished.connect(
                self._emit_pattern_scale_if_changed
            )
            self.fill_image_button.clicked.connect(self._pick_pattern_tile)
        if on_style_align is not None:
            self.align_combo.currentIndexChanged.connect(
                lambda _i: self._emit_style_align_if_changed(on_style_align)
            )
            self.align_v_combo.currentIndexChanged.connect(
                lambda _i: self._emit_style_align_if_changed(on_style_align)
            )
        if on_style_effect is not None:
            self._cb_style_effect = on_style_effect
            for key in self._effect_checks:
                self._effect_checks[key].stateChanged.connect(
                    lambda _s, k=key: self._commit_effect_enabled(k, on_style_effect)
                )
                self._effect_swatches[key].clicked.connect(
                    lambda _c=False, k=key: self._pick_effect_color(k, on_style_effect)
                )
                self._effect_spins[key].editingFinished.connect(
                    lambda k=key: self._commit_effect_value(k, on_style_effect)
                )
        # Plan 08-08 (D-13/D-14): the Inpaint override combo commit (WR-01
        # gated — an unchanged focus cycle is a no-op; "Mixed" never commits).
        if on_inpaint_override is not None:
            self.inpaint_combo.currentIndexChanged.connect(
                lambda _i: self._emit_inpaint_if_changed(on_inpaint_override)
            )

    # -------------------------------------------------- no-op commit guards
    # WR-01: a focus-out / editingFinished commit whose field value equals the
    # value loaded at load_box time is a NO-OP — it must not flip the D-04
    # edited flag, pin ``manual_override``, or push a no-op BOXES snapshot
    # (the InlineEditor's ``changed = new_text != self._entry_text`` pattern).
    def _emit_recognized_if_changed(self, on_recognized) -> None:
        """Forward the recognized field's commit text only if it changed since load_box."""
        text = self.recognized_edit.toPlainText()
        if text != self._loaded_recognized:
            on_recognized(text)

    def _emit_translation_if_changed(self, on_translation) -> None:
        """Forward the translation field's commit text only if it changed since load_box."""
        text = self.translation_edit.toPlainText()
        if text != self._loaded_translation:
            on_translation(text)

    def _emit_inpaint_if_changed(self, on_inpaint_override) -> None:
        """Forward the Inpaint combo's value only on a REAL user change.

        WR-01: an unchanged commit (text == the loaded-memory guard) is a
        no-op. The "Mixed" sentinel — selectable in the widget (the A5 edit-all
        affordance keeps the real options pickable) — NEVER leaves the widget
        layer (Pitfall 7): committing it would push a before==after BOXES undo
        entry. Only "Auto"/"Fill"/"Inpaint"/"Never" carry a real override.
        """
        text = self.inpaint_combo.currentText()
        if text == self._loaded_inpaint:
            return  # WR-01: an unchanged focus cycle is a no-op
        if text == "Mixed":
            return  # the sentinel never leaves the widget layer (Pitfall 7)
        on_inpaint_override(text)

    def _emit_bubble_if_changed(self, on_bubble) -> None:
        """Forward the bubble-spin commit only if the value changed since load_box.

        The spinbox displays ``0`` (the em dash) for ``bubble_no=None``, so an
        unchanged focus cycle must not write bubble 1 / ``manual_override=True``
        (D-16 preserve-manual engaged by accident).
        """
        number = self.bubble_spin.value()
        if number != self._loaded_bubble:
            on_bubble(number)

    # ---- style-section guards (Pitfall 7 — the Mixed sentinel never leaves
    # ---- the widget layer; a commit fires only on an ACTIVE user change and
    # ---- always carries a real value).
    def _on_font_widget_changed(self, family: str, on_style_font) -> None:
        """Font-combo change: repopulate the Style combo + WR-01-gate the commit."""
        if family and family != "Mixed":
            self._refresh_style_combo(
                family, self._loaded_style_bold, self._loaded_style_italic
            )
        self._emit_style_font_if_changed(family, on_style_font)

    def _emit_style_font_if_changed(self, family: str, on_style_font) -> None:
        if not family or family == "Mixed":
            return  # the sentinel never leaves the widget layer (Pitfall 7)
        if self.font_combo.findText(family) == -1:
            return  # free-typed text is not a real family (T-07-18 / WR-01)
        if family != self._loaded_style_font:
            on_style_font(family)

    def _on_font_filter_changed(self, text: str) -> None:
        """G-07-2: the live contains-match filter on the font dropdown.

        ``text`` is escaped (``QRegularExpression.escape``) before it enters
        the filter expression — user input is a literal substring, never
        regex syntax (ASVS V5 / T-07-20). The proxy filters a VIEW of the
        combo's own model; the source family list is never mutated
        (Don't-Hand-Roll — QFontDatabase stays the single source).

        The combo's signals are blocked around the update: the proxy's row
        churn would otherwise move the combo's current index (rows above the
        selection disappear) and re-emit ``currentTextChanged`` with a
        DIFFERENT family — a spurious font commit on every keystroke. The
        loaded family (or the 'Mixed' sentinel) is then restored to the
        display so the selection never drifts while the user browses the
        filtered list; the real commit still fires when the user PICKS a row.
        """
        self._font_proxy.setFilterRegularExpression(
            QRegularExpression(
                QRegularExpression.escape(text),
                QRegularExpression.PatternOption.CaseInsensitiveOption,
            )
        )
        family = self._loaded_style_font
        if family:
            was = self.font_combo.blockSignals(True)
            self.font_combo.setCurrentText(family)
            self.font_combo.blockSignals(was)

    def _on_default_font_clicked(self) -> None:
        """G-07-3: emit ``default_font_requested`` with the CURRENT combo family.

        WR-01 (07-REVIEW-GAPS): the QFontComboBox is editable, so its line
        edit accepts FREE TEXT that is not a family in the list — the click
        commits only when the current text EXACTLY matches an installed
        family (the ``findText`` gate; T-07-18 "never free text"). The
        'Mixed' sentinel NEVER leaves the widget layer (Pitfall 7) — a click
        while the combo shows Mixed (multi-select with differing families)
        emits nothing.
        """
        family = self.font_combo.currentText()
        if family and family != "Mixed":
            if self.font_combo.findText(family) == -1:
                return  # free-typed text is not a real family (T-07-18)
            self.default_font_requested.emit(family)

    def _emit_style_font_style_if_changed(self, name: str, on_style_font_style) -> None:
        if name == "Mixed":
            return
        if name != self._loaded_style_font_style:
            on_style_font_style(name)

    def _on_size_debounce_timeout(self) -> None:
        """quick-260824-t64 Task 3: live Size commit after the debounce window.

        Routes through the SAME emitter as editingFinished so the WR-01
        loaded-value guard + Mixed-sentinel guard stay in force. The None
        guard mirrors ``_cb_style_color``: the timer exists from __init__ but
        the callback is only stored by connect_commit_handlers.
        """
        if self._cb_style_size is not None:
            self._emit_style_size_if_changed(self._cb_style_size)

    def _emit_style_size_if_changed(self, on_style_size) -> None:
        number = self.size_spin.value()
        if self._style_size_mixed and number == 0:
            return  # a no-op focus cycle on the "Mixed" sentinel (Pitfall 7)
        if number != self._loaded_style_size:
            on_style_size(number)

    def _emit_char_spacing_if_changed(self, commit) -> None:
        """WR-01 emit-if-changed for Spacing H (quick-260824-viq)."""
        value = self.char_spacing_spin.value()
        if value != self._loaded_char_spacing:
            commit(value)

    def _emit_line_spacing_if_changed(self, commit) -> None:
        """WR-01 emit-if-changed for Spacing V (quick-260824-viq)."""
        value = self.line_spacing_spin.value()
        if value != self._loaded_line_spacing:
            commit(value)

    def _commit_auto_fit(self, on_style_auto_fit) -> None:
        """Auto-fit checkbox commit: real state only (tri-state = sentinel)."""
        if self.auto_fit_check.checkState() == Qt.CheckState.PartiallyChecked:
            return  # the Mixed sentinel is display-only (Pitfall 7)
        real = self.auto_fit_check.isChecked()
        if self._loaded_style_auto_fit is None or real != self._loaded_style_auto_fit:
            on_style_auto_fit(real)
        self._apply_auto_fit_spin_state()

    def _commit_vertical(self, on_vertical) -> None:
        """Vertical-checkbox commit: real state only (tri-state = sentinel)."""
        if self.vertical_check.checkState() == Qt.CheckState.PartiallyChecked:
            return  # the Mixed sentinel is display-only (Pitfall 7)
        real = self.vertical_check.isChecked()
        if self._loaded_vertical is None or real != self._loaded_vertical:
            on_vertical(real)

    def _pick_style_color(self, on_style_color) -> None:
        """Open ``QColorDialog`` seeded with the current color; commit on pick.

        quick-260909-nj9: the dialog carries ``ShowAlphaChannel`` (Qt's
        alpha-control option) so the glyph fill can pick a transparency, and
        ``DontUseNativeDialog`` is REQUIRED (not cosmetic) — the Windows
        native color dialog has no alpha control, so the alpha option alone
        would silently show nothing. The seed ``QColor`` parses
        ``#AARRGGBB``, so the dialog opens at the stored alpha and its
        preview updates live while the slider drags; the canvas refreshes on
        the existing commit-on-pick cadence.
        """
        seed = self.color_swatch.color
        if seed is None or self._loaded_style_color is None:
            seed = "#e8e8ea"
        color = QColorDialog.getColor(
            QColor(seed),
            self,
            "Select Font Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
            | QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if color.isValid():
            self._emit_style_color_if_changed(
                color.name(QColor.NameFormat.HexArgb), on_style_color
            )

    def _emit_style_color_if_changed(self, color_hex: str, on_style_color) -> None:
        """WR-01 emit-if-changed for the glyph fill, ALPHA-AWARE
        (quick-260909-nj9): BOTH sides compare through ``_norm_hex_a`` so
        re-picking the loaded color in a different opaque spelling
        (``#ff0000`` vs ``#ffff0000``) is a no-op — never a spurious undo
        entry — and the emitted value is the canonical HexArgb form, so the
        model converges on one spelling without a load-time rewrite."""
        if not color_hex:
            return
        normalized = _norm_hex_a(color_hex)
        if normalized != _norm_hex_a(self._loaded_style_color):
            on_style_color(normalized)

    def _emit_style_align_if_changed(self, on_style_align) -> None:
        """Per-axis align commit: Mixed->None translation + per-axis WR-01 guard.

        G-07-7: a Mixed axis no longer suppresses the OTHER axis — each axis
        is translated independently (``"Mixed"`` -> ``None``, the untouched
        sentinel the consumer preserves per box — the ``_effect_payload``
        mirror), and the commit fires when ANY axis differs from its loaded
        display value. An unchanged focus cycle (current == loaded on both
        axes) is a WR-01 no-op.

        WR-02 (07-REVIEW-GAPS): a state that translates to ``(None, None)``
        — BOTH axes showing the Mixed sentinel against a loaded state that
        differs — carries NOTHING to apply (``_replace_align`` skips None
        axes); emitting it would still push a before==after BOXES undo entry
        + refresh, so it is skipped here.
        """
        h = self.align_combo.currentText()
        v = self.align_v_combo.currentText()
        if (h, v) == (self._loaded_style_align_h, self._loaded_style_align_v):
            return  # WR-01: an unchanged focus cycle is a no-op (per-axis)
        h_model = None if h == "Mixed" else _ALIGN_H_TO_MODEL[h]
        v_model = None if v == "Mixed" else _ALIGN_V_TO_MODEL[v]
        if h_model is None and v_model is None:
            return  # WR-02: a both-None commit carries nothing to apply
        on_style_align(h_model, v_model)

    def _commit_effect_enabled(self, key: str, on_style_effect) -> None:
        """Effect enable-checkbox commit: real state only (tri-state = sentinel)."""
        check = self._effect_checks[key]
        if check.checkState() == Qt.CheckState.PartiallyChecked:
            return
        real = check.checkState() == Qt.CheckState.Checked
        loaded = self._loaded_effects[key]
        if loaded["enabled"] is None or real != loaded["enabled"]:
            on_style_effect(key, self._effect_payload(key, enabled=real))
        self._apply_effect_row_state(key)

    def _commit_effect_value(self, key: str, on_style_effect) -> None:
        """Effect spin commit — WR-01-gated (a Mixed-sentinel no-op cycle drops)."""
        loaded = self._loaded_effects[key]
        value = self._effect_spins[key].value()
        if loaded["enabled"] is None and value == 0:
            return  # a no-op focus cycle on the "Mixed" sentinel (Pitfall 7)
        if loaded["value"] is not None and value == loaded["value"]:
            return  # WR-01: an unchanged focus cycle is a no-op
        on_style_effect(key, self._effect_payload(key, value=value))

    def _pick_effect_color(self, key: str, on_style_effect) -> None:
        """Open ``QColorDialog`` for ONE effect row's swatch; commit on pick.

        quick-260909-nj9 SCOPE DECISION: effect colors stay OPAQUE on
        purpose (HexRgb dialog, no ShowAlphaChannel) — each effect dict
        already owns its own opacity field (``TextStyle`` DEFAULT_GLOW /
        DEFAULT_SHADOW), so a second transparency control per row would be
        redundant. Alpha is the glyph-fill Color row ONLY; do not "fix"
        this asymmetry.
        """
        seed = self._effect_swatches[key].color or _EFFECT_DEFAULT_COLORS[key]
        color = QColorDialog.getColor(QColor(seed), self, f"Select {key.title()} Color")
        if color.isValid():
            self._commit_effect_color_inner(key, color.name(), on_style_effect)

    def _commit_effect_color_inner(
        self, key: str, color_hex: str, on_style_effect
    ) -> None:
        """WR-01-gated effect swatch commit (shared by the dialog + tests)."""
        if not color_hex:
            return
        loaded = self._loaded_effects[key]
        if loaded["color"] is not None and color_hex == loaded["color"]:
            return  # WR-01 no-op
        on_style_effect(key, self._effect_payload(key, color=color_hex))

    def _effect_payload(
        self, key: str, *, enabled=None, color=None, value=None
    ) -> dict:
        """The real effect commit dict from the row's current widgets.

        MIXED rows (loaded fields None) fall back to the effect defaults for
        the fields the user did NOT explicitly change (so a commit always
        carries real values — Pitfall 7); uniform rows use the widgets
        verbatim. The MainWindow maps ``value`` per key (outline width / glow
        radius / shadow offset).

        WR-02 (07-REVIEW): the ENABLED field is special-cased — a MIXED row's
        tri-state checkbox cannot express "leave enabled alone", so a
        value/color-only commit carries ``"enabled": None`` (the untouched
        sentinel) instead of the hardcoded ``True``. The commit consumer
        (``MainWindow._replace_effect``) then preserves each box's OWN enabled
        state instead of silently switching the effect on for every box. The
        sentinel never reaches a ``TextStyle`` (Pitfall 7 holds — see the
        consumer's None guard); explicit enabled commits always carry a bool.
        """
        loaded = self._loaded_effects[key]
        mixed = loaded["enabled"] is None  # any None field marks the row mixed
        return {
            "enabled": bool(enabled)
            if enabled is not None
            else (loaded["enabled"] if not mixed else None),
            "color": color
            if color is not None
            else (loaded["color"] if not mixed else _EFFECT_DEFAULT_COLORS[key]),
            "value": value
            if value is not None
            else (loaded["value"] if not mixed else _EFFECT_DEFAULT_VALUES[key]),
        }

    # Direct commit hooks the tests can drive (the real commit path is the
    # focus-loss / Ctrl+Return / editingFinished / dialog signal wired above;
    # these methods let tests fire a commit without synthesising a focus event
    # or opening a modal dialog).
    def _commit_recognized(self) -> None:
        self.recognized_edit.committed.emit()

    def _commit_translation(self) -> None:
        self.translation_edit.committed.emit()

    def _commit_style_color(self, color_hex: str) -> None:
        """Direct style-color commit hook (the real path is the swatch dialog)."""
        if self._cb_style_color is not None:
            self._emit_style_color_if_changed(color_hex, self._cb_style_color)

    def _commit_effect_color(self, key: str, color_hex: str) -> None:
        """Direct effect-color commit hook (the real path is the swatch dialog)."""
        if self._cb_style_effect is not None:
            self._commit_effect_color_inner(key, color_hex, self._cb_style_effect)

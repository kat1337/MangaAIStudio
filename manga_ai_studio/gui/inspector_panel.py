"""``InspectorPanel`` — the Phase 4 text-edit / metadata dock (plan 04-04 Task 2).

This is the D-08 "always-present view of both fields + metadata" — a
``QDockWidget`` "Inspector" (instantiated + tabbed with the Tools dock in
:meth:`MainWindow._build_docks`) whose body is this ``QWidget``. It surfaces,
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
- **Vertical** — a ``QCheckBox`` writing ``payload.vertical``. LIVE since plan
  07-05 (D-13): toggling flips the canvas + bake to the renderer's tategaki
  path (the Phase 4 placeholder tooltip is replaced with the D-13 copy); in a
  multi-selection it becomes tri-state (indeterminate = mixed vertical flags,
  D-10).
- **Style section** (plan 07-05, D-05/D-06/D-10/D-14/D-15 — UI-SPEC surface
  33): the per-box styling controls BELOW the text fields — Font
  (``QFontComboBox``), Style (per-family ``QComboBox``), Size + Auto-fit
  (0..200 ``QSpinBox`` with the "Auto" sentinel + a tri-state ``QCheckBox``),
  Color (24x24 swatch ``QToolButton`` → ``QColorDialog``), Align / Align V
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
      spinbox ranges clamp the effect geometry at the UI (V5 — outline 0..10,
      glow 0..20, shadow 0..10, size 0..200 with 0 = Auto).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFontDatabase,
    QKeyEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from manga_ai_studio.core.box_model import DETECTED, USER
from manga_ai_studio.core.text_style import TextStyle

# Dark QSS for the Inspector panel (UI-SPEC §Color tokens — copied from the
# ToolsPanel _TOOLS_QSS so the two right-side docks share a look). Adds
# QTextEdit styling (the ToolsPanel has no text edit) reusing the same tokens.
# Plan 07-05 (D-05): the styling-section widgets (QFontComboBox/QComboBox/
# QToolButton swatch/QFrame divider/section header) join the same token set —
# #2d2d33 bg, #3a3a42 border, #e8e8ea fg, :disabled -> #25252b/#6a6a72.
_INSPECTOR_QSS = """
QLabel { color: #e8e8ea; }
QLabel#styleHeaderLabel { color: #9a9aa2; font-size: 12px; font-weight: 600; }
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

# Effect-row defaults (UI-SPEC §Color / §Spacing exceptions): outline 0..10/2,
# glow 0..20/4, shadow 0..10/2; colors = the semantic defaults. Used when a
# MIXED row's user interaction needs a real value where the sentinel sat
# (Pitfall 7 — a commit always carries real values).
_EFFECT_DEFAULT_COLORS = {"outline": "#0b0b0e", "glow": "#e8e8ea", "shadow": "#000000"}
_EFFECT_DEFAULT_VALUES = {"outline": 2, "glow": 4, "shadow": 2}


class _ColorSwatchButton(QToolButton):
    """A 24x24 color swatch (UI-SPEC §33 — the styling-section Color/effect rows).

    ``color`` is a hex string or ``None``. ``None`` paints the D-10 MIXED
    split swatch (left ``#e8e8ea`` / right ``#9a9aa2``, 1px ``#3a3a42``
    border — UI-SPEC §Color) — the sentinel NEVER leaves the widget layer
    (RESEARCH Pitfall 7): a commit only fires from the dialog path with a
    real color.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color: str | None = None
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose a color.")

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        """Paint the solid fill or the Mixed split fill + the 1px border."""
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
        else:
            painter.fillRect(rect, QColor(self.color))
        painter.setPen(QPen(QColor("#3a3a42"), 1))
        painter.drawRect(rect)
        painter.end()


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
    """The Inspector dock body — text fields + metadata + the Style section.

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
    style_align_changed = Signal(str, str)  # (align_h, align_v) model values
    style_effect_changed = Signal(str, dict)  # effect key + {enabled, color, value}

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

        # Vertical — LIVE since plan 07-05 (D-13): toggling writes
        # payload.vertical AND the MainWindow re-renders the canvas + bake
        # through the renderer's tategaki path (Pitfall 9 — a toggle must
        # re-render, not just write metadata). The Phase 4 placeholder
        # tooltip is REPLACED (D-13 copy). In a multi-selection the checkbox
        # becomes tri-state (indeterminate = mixed vertical flags, D-10).
        self.vertical_check = QCheckBox("Vertical text")
        self.vertical_check.setToolTip(
            "Render this box's text vertically, top-to-bottom (tategaki)."
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
        self.font_combo = QFontComboBox()
        self.font_combo.setToolTip("Font family for the selected box(es).")
        form.addRow("Font", self.font_combo)

        # Style — a per-family QComboBox (Regular/Italic/Bold/Bold Italic as
        # the font provides; repopulated on Font change — D-05).
        self.style_combo = QComboBox()
        self.style_combo.setToolTip("Font style (weight + slant).")
        form.addRow("Style", self.style_combo)

        # Size + Auto-fit (D-15): 0..200 with "Auto" at 0 (the bubble_spin
        # sentinel pattern). The Auto-fit checkbox couples the spin: checked
        # -> 0/Auto + disabled; unchecked -> enabled with the current rendered
        # size (rounded) as the starting manual value (UI-SPEC §33).
        self.size_spin = QSpinBox()
        self.size_spin.setRange(0, 200)
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

        # Color — the 24x24 swatch -> QColorDialog (Don't-Hand-Roll). The
        # split fill (color None) is the D-10 Mixed presentation.
        self.color_swatch = _ColorSwatchButton()
        self.color_swatch.setToolTip(
            "Glyph fill color — choose one to apply it to the selection."
        )
        form.addRow("Color", self.color_swatch)

        # Align / Align V — H and V alignment combos (one signal pair:
        # style_align_changed(h, v); model values, UI-SPEC §33).
        self.align_combo = QComboBox()
        self.align_combo.addItems(["Left", "Center", "Right"])
        form.addRow("Align", self.align_combo)
        self.align_v_combo = QComboBox()
        self.align_v_combo.addItems(["Top", "Middle", "Bottom"])
        form.addRow("Align V", self.align_v_combo)

        # Outline / Glow / Shadow — one row each: enable QCheckBox + 24x24
        # swatch + QSpinBox (ranges per UI-SPEC §Spacing exceptions: outline
        # 0..10, glow 0..20, shadow 0..10). A disabled checkbox greys the
        # row's swatch+spin (_apply_effect_row_state).
        self._effect_checks: dict[str, QCheckBox] = {}
        self._effect_swatches: dict[str, _ColorSwatchButton] = {}
        self._effect_spins: dict[str, QSpinBox] = {}
        for key, (lo, hi) in (
            ("outline", (0, 10)),
            ("glow", (0, 20)),
            ("shadow", (0, 10)),
        ):
            check = QCheckBox()
            swatch = _ColorSwatchButton()
            spin = QSpinBox()
            spin.setRange(lo, hi)
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
        self._loaded_rendered_size: float | None = None
        self._loaded_style_auto_fit = False
        self._loaded_style_color: str | None = "#e8e8ea"
        self._loaded_style_align_h = "Center"
        self._loaded_style_align_v = "Middle"
        self._loaded_effects: dict = {
            "outline": {"enabled": True, "color": "#0b0b0e", "value": 2},
            "glow": {"enabled": False, "color": "#e8e8ea", "value": 4},
            "shadow": {"enabled": False, "color": "#000000", "value": 2},
        }
        self._effect_mixed: dict = {
            "outline": False, "glow": False, "shadow": False,
        }
        self._loaded_vertical = False
        # Wired style callbacks (for the direct test hooks — the real commit
        # paths are the widget signals wired in connect_commit_handlers).
        self._cb_style_color = None
        self._cb_style_effect = None

        # Start in the empty state (no box selected).
        self.clear()

    # ------------------------------------------------------------- population
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

        # Language + vertical.
        language = "unknown"
        vertical = False
        if pagebox.payload is not None:
            language = str(getattr(pagebox.payload, "language", "unknown") or "unknown")
            vertical = bool(getattr(pagebox.payload, "vertical", False))
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

        # Color — all-equal -> solid swatch; differing -> the split swatch.
        colors = {s.color for s in styles}
        if len(colors) == 1:
            color = next(iter(colors))
            self._loaded_style_color = color
            self._set_swatch_color(self.color_swatch, color)
        else:
            self._loaded_style_color = None
            self._set_swatch_color(self.color_swatch, None)

        # Aligns.
        aligns_h = {s.align_h for s in styles}
        aligns_v = {s.align_v for s in styles}
        if len(aligns_h) == 1:
            display = _ALIGN_H_DISPLAY.get(next(iter(aligns_h)), "Center")
            self._select_combo(
                self.align_combo, ["Left", "Center", "Right"], display
            )
            self._loaded_style_align_h = display
        else:
            self._select_combo(self.align_combo, ["Mixed"], "Mixed")
            self._loaded_style_align_h = "Mixed"
        if len(aligns_v) == 1:
            display = _ALIGN_V_DISPLAY.get(next(iter(aligns_v)), "Middle")
            self._select_combo(
                self.align_v_combo, ["Top", "Middle", "Bottom"], display
            )
            self._loaded_style_align_v = display
        else:
            self._select_combo(self.align_v_combo, ["Mixed"], "Mixed")
            self._loaded_style_align_v = "Mixed"

        # Effects — per-row common-value; a differing row shows the tri-state
        # checkbox + split swatch + "Mixed" spin special text.
        for key in ("outline", "glow", "shadow"):
            self._load_effect_row_multi(key, styles)

        # Vertical checkbox — differing vertical flags -> tri-state (D-10).
        verticals = {
            bool(pb.payload.vertical) if pb.payload is not None else False
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

        self._loaded_style_color = style.color
        self._set_swatch_color(self.color_swatch, style.color)

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
            self.style_combo,
            self.size_spin,
            self.auto_fit_check,
            self.color_swatch,
            self.align_combo,
            self.align_v_combo,
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
        if on_style_auto_fit is not None:
            self.auto_fit_check.stateChanged.connect(
                lambda _s: self._commit_auto_fit(on_style_auto_fit)
            )
        if on_style_color is not None:
            self.color_swatch.clicked.connect(
                lambda: self._pick_style_color(on_style_color)
            )
            self._cb_style_color = on_style_color
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
        if family != self._loaded_style_font:
            on_style_font(family)

    def _emit_style_font_style_if_changed(self, name: str, on_style_font_style) -> None:
        if name == "Mixed":
            return
        if name != self._loaded_style_font_style:
            on_style_font_style(name)

    def _emit_style_size_if_changed(self, on_style_size) -> None:
        number = self.size_spin.value()
        if self._style_size_mixed and number == 0:
            return  # a no-op focus cycle on the "Mixed" sentinel (Pitfall 7)
        if number != self._loaded_style_size:
            on_style_size(number)

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
        """Open ``QColorDialog`` seeded with the current color; commit on pick."""
        seed = self.color_swatch.color
        if seed is None or self._loaded_style_color is None:
            seed = "#e8e8ea"
        color = QColorDialog.getColor(QColor(seed), self, "Select Font Color")
        if color.isValid():
            self._emit_style_color_if_changed(color.name(), on_style_color)

    def _emit_style_color_if_changed(self, color_hex: str, on_style_color) -> None:
        if not color_hex:
            return
        if color_hex != self._loaded_style_color:
            on_style_color(color_hex)

    def _emit_style_align_if_changed(self, on_style_align) -> None:
        h = self.align_combo.currentText()
        v = self.align_v_combo.currentText()
        if h == "Mixed" or v == "Mixed":
            return  # the sentinel never leaves the widget layer (Pitfall 7)
        if (h, v) != (self._loaded_style_align_h, self._loaded_style_align_v):
            on_style_align(_ALIGN_H_TO_MODEL[h], _ALIGN_V_TO_MODEL[v])

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
        """Open ``QColorDialog`` for ONE effect row's swatch; commit on pick."""
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

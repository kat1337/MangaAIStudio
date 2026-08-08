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
- **Vertical** — a ``QCheckBox`` writing ``payload.vertical`` (export metadata).
  The editor-mode flip itself is a v1 no-op per RESEARCH Pitfall 5; the checkbox
  is the seam for the future typesetting phase.

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
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from manga_ai_studio.core.box_model import DETECTED, USER

# Dark QSS for the Inspector panel (UI-SPEC §Color tokens — copied from the
# ToolsPanel _TOOLS_QSS so the two right-side docks share a look). Adds
# QTextEdit styling (the ToolsPanel has no text edit) reusing the same tokens.
_INSPECTOR_QSS = """
QLabel { color: #e8e8ea; }
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
"""

# Empty-state copy (UI-SPEC §Copywriting — shown when no box is selected).
_EMPTY_STATE = "Select a text box to edit its text and translation."
# Field placeholders (UI-SPEC §Copywriting — shown in the empty text fields).
_RECOGNIZED_PLACEHOLDER = (
    "No recognized text yet — run OCR (Text \u2192 Run OCR)."
)
_TRANSLATION_PLACEHOLDER = "No translation — type one, or use Load Translations\u2026."

# Origin hues reused as TEXT colour so the Inspector matches the canvas border
# (UI-SPEC §18). Module constants keep the hex in one place.
_ORIGIN_HUE_HEX = {DETECTED: "#5fd068", USER: "#f5a623"}
_ORIGIN_LABEL = {DETECTED: "Detected", USER: "User"}


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
    """The Inspector dock body — both text fields + metadata for the selected box.

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

        # Vertical — D-06 per-box toggle (v1 no-op on the editor per RESEARCH
        # Pitfall 5; writes payload.vertical as export metadata).
        self.vertical_check = QCheckBox("Vertical text")
        self.vertical_check.setToolTip(
            "Coming soon — preserves the vertical flag for export."
        )
        form.addRow("", self.vertical_check)

        root.addLayout(form)
        root.addStretch(1)
        self.setStyleSheet(_INSPECTOR_QSS)

        # WR-01: the values the fields displayed at load_box time — a commit
        # whose value is unchanged is a no-op (see _emit_*_if_changed). The
        # InlineEditor's ``_entry_text`` pattern (inline_editor.py:211).
        self._loaded_bubble = 0
        self._loaded_recognized = ""
        self._loaded_translation = ""

        # Start in the empty state (no box selected).
        self.clear()

    # ------------------------------------------------------------- population
    def load_box(self, pagebox) -> None:
        """Populate the fields from the given ``pagebox`` (the selection follower).

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
        self.vertical_check.setChecked(vertical)
        self.vertical_check.blockSignals(was_v)

        # Enable all fields + hide the empty-state copy.
        self._set_fields_enabled(True)
        self.empty_label.setVisible(False)

    def clear(self) -> None:
        """Show the empty-state copy and disable all fields (no box selected)."""
        self.empty_label.setVisible(True)
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
        self.vertical_check.setChecked(False)
        self.vertical_check.blockSignals(was_v)

    def _set_fields_enabled(self, enabled: bool) -> None:
        """Enable/disable every editable field (the empty-state gate)."""
        for w in (
            self.bubble_spin,
            self.recognized_edit,
            self.translation_edit,
            self.vertical_check,
        ):
            w.setEnabled(enabled)

    # ------------------------------------------------------- commit wiring
    def connect_commit_handlers(
        self,
        on_recognized,
        on_translation,
        on_bubble,
        on_vertical,
    ) -> None:
        """Wire each field's commit signal to the MainWindow-supplied callbacks.

        The MainWindow owns the pagebox mutation + ``boxes_modified`` push +
        overlay refresh; this method is the single point where the panel's
        change signals are routed to those callbacks. QTextEdits commit on
        focus-loss / Ctrl+Return (``_CommitTextEdit``); QSpinBox/QCheckBox on
        ``editingFinished`` / ``toggled``.
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
        self.vertical_check.toggled.connect(on_vertical)

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

    # Direct commit hooks the tests can drive (the real commit path is the
    # focus-loss / Ctrl+Return / editingFinished signal wired above; these
    # methods let tests fire a commit without synthesising a focus event).
    def _commit_recognized(self) -> None:
        self.recognized_edit.committed.emit()

    def _commit_translation(self) -> None:
        self.translation_edit.committed.emit()

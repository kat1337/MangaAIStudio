"""``LoadTranslationsDialog`` — the D-17 paste + file-import front-ends for the
Load Translations flow (plan 04-07, TEXT-05).

Two front-ends share the Plan 02 parser core (``core.translation_parser``):

1. **Paste** — a ``QPlainTextEdit`` paste area (mono font, UI-SPEC placeholder
   copy) plus a ``QComboBox`` page selector (default: current page).
2. **File import** — a "Load from File…" button that opens ``QFileDialog``
   (``*.txt`` filter) and reads the file with ``open(path, "r",
   encoding="utf-8")`` into the paste area (UI-SPEC §20 lets the user review
   before Apply). On ``OSError``/``UnicodeDecodeError`` it shows the
   "Couldn't read '{filename}'." error dialog (UI-SPEC §Copywriting, threat
   T-4-16 — the file is user-chosen via the dialog, no programmatic path).

RESEARCH §Pitfall 3 separation (CONTEXT D-17): the dialog does NOT parse or
mutate boxes. Its job is to collect ``(text, page_index)`` and return
``Accepted`` — the MainWindow runs ``parse_translations`` +
``apply_translations``, pushes ONE batch BOXES snapshot (UI-SPEC §20), and
shows the parser-result report.

Security (ASVS V5 / V7, threat T-4-15/T-4-16): pasted/file text never reaches
a renderer or an eval — it is handed to the strict anchored-regex parser
(Plan 02) which skips + counts unparseable lines and never raises. The
file-read error path is user-friendly copy only (traceback to loguru).
"""

from __future__ import annotations

from loguru import logger
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

# Dark QSS for the dialog (UI-SPEC §Color tokens — mirrors the InspectorPanel /
# ToolsPanel QSS so the dialog reads as part of the dark UI). QComboBox needs
# the popup view styled separately (Fusion default popup is light).
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QPlainTextEdit, QComboBox {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
}
QComboBox QAbstractItemView {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    color: #e8e8ea;
    selection-background-color: #00d4ff;
    selection-color: #0b0b0e;
}
QPushButton {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    padding: 4px 12px;
    color: #e8e8ea;
}
QPushButton:hover { background: #34343c; }
QPushButton:default { border: 1px solid #00d4ff; }
"""

# UI-SPEC §20 placeholder copy (mono paste area — the format is line-oriented).
_PLACEHOLDER = (
    "Paste your translation list here, one line per box:\n"
    "[1]: first translated line\n"
    "[2]: second translated line\n"
    "[SFX -3]: *sound effect*"
)


class LoadTranslationsDialog(QDialog):
    """Collect ``(text, page_index)`` for the Load Translations flow (D-17).

    Pure collector: on Apply the dialog stores the paste text + the selected
    page index, then ``accept()``s. The MainWindow reads ``get_text()`` /
    ``get_page_index()`` and performs the parse + apply + report (RESEARCH
    §Pitfall 3 separation — no box mutation here).
    """

    def __init__(
        self,
        parent=None,
        page_names: "list[str]" = None,
        current_page_index: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Load Translations")
        self.setObjectName("load_translations_dialog")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Page selector (default: current page).
        form = QFormLayout()
        self.page_combo = QComboBox(self)
        for name in page_names or []:
            self.page_combo.addItem(name)
        if page_names:
            self.page_combo.setCurrentIndex(
                min(max(current_page_index, 0), len(page_names) - 1)
            )
        form.addRow("Page:", self.page_combo)
        root.addLayout(form)

        # Paste area (mono font — the format is line-oriented).
        self.paste_edit = QPlainTextEdit(self)
        self.paste_edit.setFont(QFont("Consolas", 10))
        self.paste_edit.setPlaceholderText(_PLACEHOLDER)
        self.paste_edit.setTabChangesFocus(True)
        root.addWidget(self.paste_edit)

        # File-import front-end (D-17): loads a *.txt into the paste area.
        file_row = QHBoxLayout()
        self.load_file_btn = QPushButton("Load from File\u2026", self)
        self.load_file_btn.clicked.connect(self._on_load_file)
        file_row.addWidget(self.load_file_btn)
        file_row.addStretch(1)
        root.addLayout(file_row)

        # [Cancel] [Apply].
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

        # Result carriers (read by the MainWindow after exec() == Accepted).
        self.result_text: str = ""
        self.result_page_index: int = 0

    # ----------------------------------------------------------- front-ends
    def _on_load_file(self) -> None:
        """D-17 file front-end: import a *.txt into the paste area (UTF-8).

        The path comes from ``QFileDialog.getOpenFileName`` (user-chosen, not
        programmatic — threat T-4-16 has no traversal surface). On
        ``OSError``/``UnicodeDecodeError`` shows the UI-SPEC
        "Couldn't read '{filename}'." copy (full traceback to loguru).
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Translations", "", "Text files (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as exc:
            logger.error(f"Couldn't read translation file: {exc}")
            filename = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            QMessageBox.critical(
                self,
                f"Couldn't read '{filename}'.",
                "The file may be corrupt or in an unsupported format.",
            )
            return
        self.paste_edit.setPlainText(content)

    def _on_apply(self) -> None:
        """Store the collected (text, page_index) and accept (no parsing)."""
        self.result_text = self.paste_edit.toPlainText()
        self.result_page_index = self.page_combo.currentIndex()
        self.accept()

    # ------------------------------------------------------------ accessors
    def get_text(self) -> str:
        """Return the paste-area text collected at Apply time."""
        return self.result_text

    def get_page_index(self) -> int:
        """Return the selected page index collected at Apply time."""
        return self.result_page_index

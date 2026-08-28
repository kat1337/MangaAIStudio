"""``PageSelectionDialog`` — the Batch → Export Typeset Pages… page picker
(quick-260828-k4q Task 1).

A MODAL, pure-collector ``QDialog`` (the ``ResizeDialog`` shape —
resize_dialog.py:77-158): one CHECKABLE row per page in file order, ALL
CHECKED by default (the user contract — "export all unless I uncheck"),
``Select All`` / ``Select None`` conveniences, and an Export button whose
enabled state tracks checked-count > 0.

The dialog NEVER mutates MainWindow state — ``selected_indices()`` (ascending
indices of the checked rows) is the ONLY result surface, read by the caller
after ``exec() == Accepted``. Row index == the caller's page index
(MainWindow passes names in ``image_files`` order, which is already
natural-sorted — decision 01-02).

The word-wrapped helper label discloses the output contract up front (the
"no Save As" disclosure): each page writes ``{stem}_typeset.png`` beside its
source (geometry-altered pages into ``cleaned/``), existing files
overwritten (T-K4Q-01 — the established D-03 overwrite behavior, disclosed).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

# Dark QSS for the dialog (per-file copy is the established convention —
# crop/curves/load_translations/resize each carry their own; UI-SPEC color
# tokens).
_DIALOG_QSS = """
QDialog { background: #232328; }
QLabel { color: #e8e8ea; }
QLabel#helperLabel { color: #9a9aa2; }
QListWidget {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 2px;
    color: #e8e8ea;
}
QListWidget::item { padding: 2px; }
QListWidget::item:selected {
    background: #00d4ff;
    color: #0b0b0e;
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


class PageSelectionDialog(QDialog):
    """Collect the checked page indices for a batch typeset export.

    Pure collector (the ResizeDialog/LoadTranslationsDialog template): the
    dialog owns ONLY the check-state UI; the MainWindow owns the pages, the
    projection, and the batch dispatch. No field is named ``result`` (it
    would shadow ``QDialog.result()`` — the 05-06 convention);
    ``selected_indices()`` is the method-style accessor (the CropDialog
    precedent).
    """

    def __init__(
        self,
        parent=None,
        page_names: list[str] = (),
    ) -> None:
        super().__init__(parent)
        # 14px Body base font (UI-SPEC typography, D-12): children inherit it
        # (none of the picker widgets set their own font).
        f = QFont()
        f.setPixelSize(14)
        self.setFont(f)
        self.setWindowTitle("Export Typeset Pages")
        self.setObjectName("page_select_dialog")
        self.setModal(True)

        # The page names in the caller's file order; row index == page index.
        self._page_names = list(page_names)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # The output-contract disclosure (word-wrapped, muted).
        self.helper_label = QLabel(
            "Each page is written as {stem}_typeset.png beside its source"
            " page (pages with altered geometry go to cleaned/). Existing"
            " files are overwritten.",
            self,
        )
        self.helper_label.setObjectName("helperLabel")
        self.helper_label.setWordWrap(True)
        root.addWidget(self.helper_label)

        # One checkable row per page, ALL CHECKED by default.
        self.page_list = QListWidget(self)
        for name in self._page_names:
            item = QListWidgetItem(name, self.page_list)
            item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            item.setCheckState(Qt.CheckState.Checked)
        root.addWidget(self.page_list, 1)

        # Select All / Select None (small conveniences for the deselect-some
        # flow). Bulk checks blockSignals so ONE recompute suffices.
        bulk = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All", self)
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn = QPushButton("Select None", self)
        self.select_none_btn.clicked.connect(self._select_none)
        bulk.addWidget(self.select_all_btn)
        bulk.addWidget(self.select_none_btn)
        bulk.addStretch(1)
        root.addLayout(bulk)

        # [Export] (AcceptRole, default — accent border per the QSS) /
        # [Cancel] (RejectRole). Export's enabled state tracks
        # checked-count > 0.
        buttons = QDialogButtonBox(self)
        self.export_btn = buttons.addButton(
            "Export", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.export_btn.setDefault(True)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.page_list.itemChanged.connect(lambda _item: self._update_export_enabled())
        self._update_export_enabled()  # initial state (empty list -> disabled)

        self.setStyleSheet(_DIALOG_QSS)

    # ---------------------------------------------------------------- reads
    def selected_indices(self) -> list[int]:
        """Ascending indices of the checked rows — the ONLY result surface.

        Row N corresponds to the Nth name passed to the constructor (the
        caller's page index in file order).
        """
        return [
            i
            for i in range(self.page_list.count())
            if self.page_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    # --------------------------------------------------------------- drivers
    def _checked_count(self) -> int:
        """The number of currently-checked rows."""
        return len(self.selected_indices())

    def _update_export_enabled(self) -> None:
        """Export is enabled iff at least one page is checked."""
        self.export_btn.setEnabled(self._checked_count() > 0)

    def _set_all_checked(self, checked: bool) -> None:
        """Bulk-set every row's check state, then ONE export recompute.

        ``blockSignals`` around the loop keeps the per-item ``itemChanged``
        emissions out (one recompute suffices — the plan contract).
        """
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.page_list.blockSignals(True)
        try:
            for i in range(self.page_list.count()):
                self.page_list.item(i).setCheckState(state)
        finally:
            self.page_list.blockSignals(False)
        self._update_export_enabled()

    def _select_all(self) -> None:
        """Check every row."""
        self._set_all_checked(True)

    def _select_none(self) -> None:
        """Uncheck every row (Export disables — nothing would be written)."""
        self._set_all_checked(False)

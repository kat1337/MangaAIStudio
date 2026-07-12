"""``FileTable`` — the file-list sidebar.

Our own reimplementation patterned after the ``QListView`` shape from
MangaCleaner_GPU ``frontend/widgets.py:FileListWidget`` (D-12 REFERENCE-ONLY —
that distribution carries no LICENSE, so its code is all-rights-reserved and
must NOT be vendored). The natural-sort usage and icon-size constant reference
come from PanelCleaner ``gui/file_table.py`` (GPL v3, vendored per D-12).

UI-SPEC §Surface 3 contract: ``QListView`` in ``ListMode``, single column, 80px
rows, 64x64 letterboxed thumbnails (aspect-preserved, padded on #2d2d33),
filename + 1-indexed page number, natural-sort, accent-highlighted current row
(``rgba(0,212,255,0.18)`` bg + 2px ``#00d4ff`` left border).

Signals:
    file_clicked(Path):    emitted on row click with that row's image path.
    files_dropped(list):   emitted when image files are dropped onto the view.
    folder_dropped(Path):  emitted when a single directory is dropped.
"""

from __future__ import annotations

from pathlib import Path

from natsort import natsorted
from PySide6.QtCore import QMimeData, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLabel, QListView

from manga_ai_studio.core.image_file import ImageFile, THUMBNAIL_SIZE
from manga_ai_studio.gui.canvas import validate_image_path

# UI-SPEC surface 3 row + highlight tokens (§Color, §Spacing).
_ROW_HEIGHT = 80
_FILE_TABLE_QSS = """
QListView {
    background: #2d2d33;
    border: none;
    outline: 0;
}
QListView::item {
    height: 80px;
    padding: 8px;
    border-left: 2px solid transparent;
    color: #e8e8ea;
}
QListView::item:selected {
    background: rgba(0, 212, 255, 0.18);
    border-left: 2px solid #00d4ff;
    color: #e8e8ea;
}
"""


class FileTable(QListView):
    """Sidebar showing the loaded pages with thumbnails and natural-sort."""

    file_clicked = Signal(Path)
    files_dropped = Signal(list)
    folder_dropped = Signal(Path)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # ListMode, static layout, uniform item sizes (UI-SPEC surface 3).
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QListView.SelectionBehavior.SelectRows)
        self.setDragDropMode(QListView.DragDropMode.DropOnly)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.setStyleSheet(_FILE_TABLE_QSS)

        self._model = QStandardItemModel(self)
        self.setModel(self._model)

        # Empty-state placeholder (UI-SPEC surface 3 empty: "No pages loaded —
        # open a folder (Ctrl+Shift+O)."). A QLabel overlay shown when the
        # model has no rows. QListView has no built-in placeholder text, so we
        # manage a child QLabel that is repainted over the viewport on resize.
        self._placeholder = QLabel(
            "No pages loaded \u2014 open a folder (Ctrl+Shift+O).", self
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #9a9aa2; font-size: 12px;")
        self._placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Click a row -> emit the path it carries.
        self.clicked.connect(self._on_clicked)
        self._update_placeholder()

    # ------------------------------------------------------------------ model
    def set_pages(self, paths: list[Path]) -> None:
        """Rebuild the list from ``paths`` (natural-sorted, thumbnailed).

        Each row carries:
            - decoration role: a 64x64 letterboxed thumbnail QPixmap
            - display role:    filename + 1-indexed page number (muted)
            - user role:       the resolved Path
        """
        self._model.clear()
        self._populate(paths)
        self._update_placeholder()

    def _populate(self, paths: list[Path]) -> None:
        ordered = natsorted(paths, key=lambda p: str(p))
        for index, path in enumerate(ordered, start=1):
            image_file = ImageFile(path=path)
            image_file.load_thumbnail(THUMBNAIL_SIZE)
            item = QStandardItem()
            # Display: filename + 1-indexed page number. The page number is
            # formatted as muted text via a tab separator so the filename stays
            # primary (UI-SPEC surface 3 row contract).
            item.setText(f"{path.name}\t\u00b7 {index}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
            if image_file.thumbnail is not None:
                item.setIcon(image_file.thumbnail)
            item.setData(path, Qt.ItemDataRole.UserRole)
            item.setEditable(False)
            # 80px row height (QSS also enforces this; set on item for safety).
            item.setSizeHint(QSize(0, _ROW_HEIGHT))
            self._model.appendRow(item)

    def current_path(self) -> Path | None:
        """Return the path carried by the currently-selected row, or None."""
        idx = self.currentIndex()
        if not idx.isValid():
            return None
        return self._model.data(idx, Qt.ItemDataRole.UserRole)

    def select_path(self, path: Path) -> None:
        """Select the row carrying ``path`` (used by MainWindow to sync)."""
        for row in range(self._model.rowCount()):
            idx = self._model.index(row, 0)
            if self._model.data(idx, Qt.ItemDataRole.UserRole) == path:
                self.setCurrentIndex(idx)
                return

    # ------------------------------------------------------------------ slots
    def _on_clicked(self, index: QModelIndex) -> None:
        path = self._model.data(index, Qt.ItemDataRole.UserRole)
        if isinstance(path, Path):
            self.file_clicked.emit(path)

    def _update_placeholder(self) -> None:
        """Show the empty-state placeholder when the model has no rows."""
        empty = self._model.rowCount() == 0
        self._placeholder.setVisible(empty)
        if empty:
            self._placeholder.setGeometry(self.viewport().rect())

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Keep the placeholder centered over the viewport on resize."""
        super().resizeEvent(event)
        if self._placeholder.isVisible():
            self._placeholder.setGeometry(self.viewport().rect())

    # --------------------------------------------------------------- drag-drop
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Accept the drag if it carries URLs (files/folders). T-01-05."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        """Accept moves that carry URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Inspect dropped URLs: one dir -> folder_dropped, else files_dropped.

        T-01-05 mitigation: only ``url.toLocalFile()`` is taken, then each path
        is re-validated via ``validate_image_path`` (resolve + suffix allowlist).
        Non-local / non-file URLs are ignored entirely — no remote fetching.
        """
        mime: QMimeData = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return

        local_paths: list[Path] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            local_paths.append(Path(url.toLocalFile()))

        if not local_paths:
            event.ignore()
            return

        # Exactly one dropped directory -> folder open.
        if len(local_paths) == 1 and local_paths[0].is_dir():
            self.folder_dropped.emit(local_paths[0])
            event.acceptProposedAction()
            return

        # Otherwise filter to supported images and emit as files.
        images = [p for p in local_paths if p.is_file() and validate_image_path(p)]
        if images:
            self.files_dropped.emit(images)
            event.acceptProposedAction()
        else:
            event.ignore()

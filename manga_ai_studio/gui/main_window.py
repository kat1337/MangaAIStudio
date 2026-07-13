"""MainWindow — the application controller.

Architecture adapted from PanelCleaner ``mainwindow_driver.py`` (GPL v3,
vendored-shape per D-12): the constructor receives a ``ProfileManager``,
builds a central ``EditorCanvas``, and wires the menu bar / actions. Plan 01
shipped the File -> Open Image (Ctrl+O) + View -> Fit to Window (Ctrl+0)
skeleton. Plan 02 adds the full menu bar (File/Edit/View/Tools/Help), the
single top toolbar, the Pages + Tools docks, the 3-field status bar, the
FileTable sidebar, the Open Folder workflow, and drag-drop routing. Plan 03
adds the Tools -> Detect Text (D) async detection workflow: the
``Worker(QRunnable)`` dispatch, replace-mask confirmation, the ``#7a1f1f``
error chip, and the mask-overlay toggle (M).

Security:
    - ``open_image`` (plan 01) uses ``QFileDialog.getOpenFileName`` (T-01-01
      OS-validated absolute path).
    - ``open_folder`` and the drop handlers route every candidate path through
      ``validate_image_path`` (T-01-02 resolve + suffix allowlist) before it
      reaches ``set_image_from_path``, which runs ``validate_image_size``
      (T-01-03 large-image cap).
    - Detection runs on a QThreadPool worker (T-01-07); the worker touches only
      numpy/Python and emits signals — all Qt mutation happens in main-thread
      signal handlers. Model access goes through the adapter only (no torch /
      TextDetector import here — RESEARCH §Don't Hand-Roll).
    - WorkerError tracebacks go to loguru, NOT the QMessageBox (T-01-08
      traceback-leak mitigation): the dialog shows only user-friendly copy.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from natsort import natsorted
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QToolBar,
    QToolButton,
)

from manga_ai_studio.adapters.factory import backend_factory
from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.image_file import ImageFile
from manga_ai_studio.core.mask_editor import DEFAULT_BRUSH_SIZE, ToolMode
from manga_ai_studio.gui.canvas import EditorCanvas, validate_image_path
from manga_ai_studio.gui.file_table import FileTable
from manga_ai_studio.gui.tools_panel import ToolsPanel
from manga_ai_studio.gui.worker_thread import Worker

# Maximum number of entries kept in the Recent Files submenu (UI-SPEC surface 1).
MAX_RECENT_FILES = 8
_QSETTINGS_ORG = "MangaAIStudio"
_QSETTINGS_APP = "MangaAIStudio"


class MainWindow(QMainWindow):
    """Top-level application window.

    A ``QMainWindow`` with a central ``EditorCanvas``, a Pages dock (left) and
    a Tools dock (right), a single top toolbar, a 3-field status bar, and the
    full menu bar per UI-SPEC surface 1.
    """

    def __init__(self, profile_manager: ProfileManager, parent=None) -> None:
        super().__init__(parent)
        self.profile_manager = profile_manager

        # Central canvas.
        self.canvas = EditorCanvas(self)
        self.setCentralWidget(self.canvas)

        # Track loaded pages + the index of the currently-shown page.
        self.image_files: list[ImageFile] = []

        # Async-op state: True while a detection/inpaint worker is running.
        # Actions that start an async op are disabled while this is set so the
        # user cannot start a second model op concurrently (UI-SPEC surface 9).
        self._op_running = False

        # Build child widgets, docks, menus, toolbar, status bar.
        self._build_docks()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()

        # Route FileTable signals.
        self.file_table.file_clicked.connect(self.on_page_selected)
        self.file_table.files_dropped.connect(self._on_files_dropped)
        self.file_table.folder_dropped.connect(self._on_folder_dropped)
        # Route canvas zoom changes to the status bar center field.
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        # Wire the plan-03 actions (Detect Text, Toggle Mask Overlay).
        self._wire_detection_actions()
        # Wire the plan-04 actions (ToolsPanel, tool shortcuts, Clear Mask).
        self._wire_tool_actions()

        # Note: drag-drop is handled by the FileTable sidebar (surface 3/4). The
        # FileTable emits files_dropped/folder_dropped, which this window routes
        # to _set_pages / _load_folder. No window-level drop handlers needed.

        # Window chrome (UI-SPEC surface 1).
        self.setWindowTitle("Manga AI Studio")
        self.setMinimumSize(1024, 720)
        self.resize(1440, 900)

        # Show the empty-state status on first paint.
        self._refresh_status_bar()

    # --------------------------------------------------------------- docks
    def _build_docks(self) -> None:
        """Build the Pages (left) and Tools (right) docks."""
        # Pages dock -> FileTable (UI-SPEC surface 3).
        self.dock_pages = QDockWidget("Pages", self)
        self.dock_pages.setObjectName("dock_pages")
        self.dock_pages.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.file_table = FileTable(self)
        self.dock_pages.setWidget(self.file_table)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_pages)

        # Tools dock -> ToolsPanel (plan 04: the 5-tool panel + brush slider).
        self.dock_tools = QDockWidget("Tools", self)
        self.dock_tools.setObjectName("dock_tools")
        self.dock_tools.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.tools_panel = ToolsPanel()
        self.dock_tools.setWidget(self.tools_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_tools)

    # ---------------------------------------------------------------- menus
    def _build_menus(self) -> None:
        """Build the full menu bar (UI-SPEC surface 1)."""
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_tools_menu()
        self._build_help_menu()

    def _build_file_menu(self) -> None:
        # Open Image (plan 01, kept).
        self.action_open_image = QAction("Open Image\u2026", self)
        self.action_open_image.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open_image.triggered.connect(self.open_image)

        # Open Folder (plan 02).
        self.action_open_folder = QAction("Open Folder\u2026", self)
        self.action_open_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.action_open_folder.triggered.connect(self.open_folder)

        # Recent Files submenu (max 8 via QSettings).
        self.recent_menu = self.menuBar().addMenu("Recent Files")
        self.action_clear_recent = QAction("Clear Menu", self)
        self.action_clear_recent.triggered.connect(self._clear_recent_files)
        self._refresh_recent_menu()

        # Quit (Ctrl+Q).
        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_quit.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_open_image)
        file_menu.addAction(self.action_open_folder)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

    def _build_edit_menu(self) -> None:
        # Plan 06 undo/redo placeholders — disabled until history lands.
        self.action_undo_image = QAction("Undo Image", self)
        self.action_undo_image.setShortcut(QKeySequence("Ctrl+Z"))
        self.action_undo_image.setEnabled(False)

        self.action_redo_image = QAction("Redo Image", self)
        self.action_redo_image.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.action_redo_image.setEnabled(False)

        self.action_undo_mask = QAction("Undo Mask", self)
        self.action_undo_mask.setShortcut(QKeySequence("Alt+Z"))
        self.action_undo_mask.setEnabled(False)

        self.action_redo_mask = QAction("Redo Mask", self)
        self.action_redo_mask.setShortcut(QKeySequence("Alt+Shift+Z"))
        self.action_redo_mask.setEnabled(False)

        self.action_clear_mask = QAction("Clear Mask\u2026", self)
        self.action_clear_mask.setEnabled(False)  # plan 04

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.action_undo_image)
        edit_menu.addAction(self.action_redo_image)
        edit_menu.addAction(self.action_undo_mask)
        edit_menu.addAction(self.action_redo_mask)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_clear_mask)

    def _build_view_menu(self) -> None:
        self.action_fit_to_window = QAction("Fit to Window", self)
        self.action_fit_to_window.setShortcut(QKeySequence("Ctrl+0"))
        self.action_fit_to_window.triggered.connect(self.canvas.fit_to_window)

        self.action_actual_size = QAction("Actual Size", self)
        self.action_actual_size.setShortcut(QKeySequence("Ctrl+1"))
        self.action_actual_size.triggered.connect(self.canvas.zoom_reset)

        self.action_zoom_in = QAction("Zoom In", self)
        self.action_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        self.action_zoom_in.triggered.connect(self.canvas.zoom_in)

        self.action_zoom_out = QAction("Zoom Out", self)
        self.action_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.action_zoom_out.triggered.connect(self.canvas.zoom_out)

        # Toggle Mask Overlay (M) — wired in plan 03 (mask overlay toggle).
        self.action_toggle_mask_overlay = QAction("Toggle Mask Overlay", self)
        self.action_toggle_mask_overlay.setShortcut(QKeySequence("M"))
        self.action_toggle_mask_overlay.triggered.connect(self.canvas.toggle_mask_overlay)
        # Enabled iff a mask exists (updated in _refresh_action_states).
        self.action_toggle_mask_overlay.setEnabled(False)

        # Show Original (P) — wired in plan 05.
        self.action_show_original = QAction("Show Original", self)
        self.action_show_original.setShortcut(QKeySequence("P"))
        self.action_show_original.setEnabled(False)

        # Toggle Sidebar / Tools (the docks).
        self.action_toggle_sidebar = QAction("Toggle Sidebar", self)
        self.action_toggle_sidebar.triggered.connect(self.dock_pages.toggleViewAction().trigger)

        self.action_toggle_tools = QAction("Toggle Tools", self)
        self.action_toggle_tools.triggered.connect(self.dock_tools.toggleViewAction().trigger)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.action_fit_to_window)
        view_menu.addAction(self.action_actual_size)
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_mask_overlay)
        view_menu.addAction(self.action_show_original)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_sidebar)
        view_menu.addAction(self.action_toggle_tools)

    def _build_tools_menu(self) -> None:
        # Detect Text (D) — wired in plan 03 (async CTD detection).
        self.action_detect_text = QAction("Detect Text", self)
        self.action_detect_text.setShortcut(QKeySequence("D"))
        self.action_detect_text.triggered.connect(self.detect_text)
        # Enabled iff a page is open and no async op is running.
        self.action_detect_text.setEnabled(False)

        # Inpaint (C) — disabled until plan 05.
        self.action_inpaint = QAction("Inpaint", self)
        self.action_inpaint.setShortcut(QKeySequence("C"))
        self.action_inpaint.setEnabled(False)

        # Tool selection (plan 04 mask tools — wired to ToolsPanel).
        # Shortcuts are installed via QShortcut in _wire_tool_actions so they
        # don't conflict with the ToolsPanel's own action shortcuts.
        # Each action's data() carries its ToolMode for toolbar-button sync.
        self.action_tool_move = QAction("Move/Pan", self)
        self.action_tool_move.setData(ToolMode.MOVE)
        self.action_tool_move.triggered.connect(lambda: self.set_active_tool(ToolMode.MOVE))

        self.action_tool_brush = QAction("Brush", self)
        self.action_tool_brush.setData(ToolMode.BRUSH)
        self.action_tool_brush.triggered.connect(
            lambda: self.set_active_tool(ToolMode.BRUSH)
        )

        self.action_tool_rectangle = QAction("Rectangle", self)
        self.action_tool_rectangle.setData(ToolMode.RECTANGLE)
        self.action_tool_rectangle.triggered.connect(
            lambda: self.set_active_tool(ToolMode.RECTANGLE)
        )

        self.action_tool_lasso = QAction("Lasso", self)
        self.action_tool_lasso.setData(ToolMode.LASSO)
        self.action_tool_lasso.triggered.connect(
            lambda: self.set_active_tool(ToolMode.LASSO)
        )

        self.action_tool_eraser = QAction("Eraser", self)
        self.action_tool_eraser.setData(ToolMode.ERASER)
        self.action_tool_eraser.triggered.connect(
            lambda: self.set_active_tool(ToolMode.ERASER)
        )

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.action_detect_text)
        tools_menu.addAction(self.action_inpaint)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_tool_move)
        tools_menu.addAction(self.action_tool_brush)
        tools_menu.addAction(self.action_tool_rectangle)
        tools_menu.addAction(self.action_tool_lasso)
        tools_menu.addAction(self.action_tool_eraser)

    def _build_help_menu(self) -> None:
        self.action_about = QAction("About", self)
        self.action_about.triggered.connect(self._on_about)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.action_about)

    # --------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> None:
        """Build the single top toolbar (UI-SPEC surface 1).

        Phase 1 ships: Open | (sep) | Fit / 100% / Zoom Out / Zoom In | (sep) |
        Toggle Mask Overlay. Other sections (Detect/Inpaint/Tools/Undo) are
        added by their plans.
        """
        self.toolbar = QToolBar("Main", self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.toolbar.addAction(self.action_open_image)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_fit_to_window)
        self.toolbar.addAction(self.action_actual_size)
        self.toolbar.addAction(self.action_zoom_out)
        self.toolbar.addAction(self.action_zoom_in)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_detect_text)
        self.toolbar.addSeparator()
        # Tool-buttons section (plan 04): checkable QToolButtons sharing the
        # ToolsPanel's QActionGroup so the toolbar and dock stay in sync
        # (UI-SPEC surface 1 toolbar layout).
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_move))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_brush))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_rectangle))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_lasso))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_eraser))
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_toggle_mask_overlay)

    # ------------------------------------------------------------- status bar
    def _build_status_bar(self) -> None:
        """3-field status bar (UI-SPEC surface 1): left/center/right + error chip."""
        self.status_bar_left = QLabel("")
        self.status_bar_center = QLabel("")
        self.status_bar_right = QLabel("")
        # Center field uses the mono font for coords + zoom (UI-SPEC typography).
        from PySide6.QtGui import QFont

        mono = QFont("Consolas", 10)
        self.status_bar_center.setFont(mono)

        for widget in (
            self.status_bar_left,
            self.status_bar_center,
            self.status_bar_right,
        ):
            widget.setStyleSheet("color: #e8e8ea; padding: 0 8px;")

        # Persistent error chip (UI-SPEC §Color error banner, surface 9).
        # Shown on model-load failure; hidden until then. Style mirrors
        # PanelCleaner's OOM banner (mainwindow_driver.py:2417) lightened to
        # the UI-SPEC #7a1f1f token.
        self.error_chip = QLabel("")
        self.error_chip.setStyleSheet(
            "background-color: #7a1f1f; color: #ffffff; padding: 2px 8px;"
            " border-radius: 2px;"
        )
        self.error_chip.hide()

        # Thin 3px determinate progress bar (UI-SPEC surface 5/9).
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        bar = self.statusBar()
        bar.addWidget(self.status_bar_left, 2)
        bar.addWidget(self.status_bar_center, 3)
        bar.addWidget(self.progress_bar)
        bar.addWidget(self.error_chip)
        bar.addPermanentWidget(self.status_bar_right, 1)

    def _refresh_status_bar(self) -> None:
        """Recompute the right field's 'Page {n} / {total}' text + action states."""
        total = len(self.image_files)
        current = self._current_page_index()
        if total == 0:
            self.status_bar_right.setText("")
            self.status_bar_left.setText("No page open")
            self._refresh_action_states()
            return
        # 1-indexed; current may be None when nothing is selected yet.
        n = (current + 1) if current is not None else 0
        self.status_bar_right.setText(f"Page {n} / {total}" if n else f"Page 0 / {total}")
        self._refresh_action_states()

    def _refresh_action_states(self) -> None:
        """Enable/disable actions that depend on page/async-op/mask state.

        - Detect Text (D): enabled iff a page is open AND no async op running.
        - Toggle Mask Overlay (M): enabled iff a mask exists on the canvas.
        - Mask tools (V/B/R/L/E): enabled iff a page is open (Move always
          enabled as a no-op-safe default).
        - Clear Mask: enabled iff a mask exists.
        """
        page_open = self._current_page_index() is not None
        has_mask = self.canvas.has_mask()
        self.action_detect_text.setEnabled(page_open and not self._op_running)
        self.action_toggle_mask_overlay.setEnabled(has_mask)
        self.action_clear_mask.setEnabled(has_mask)
        # The painting tools are usable only with a page open (they paint on
        # the mask layer, which is sized to the image). Move stays usable.
        self.action_tool_move.setEnabled(True)
        for act in (
            self.action_tool_brush,
            self.action_tool_rectangle,
            self.action_tool_lasso,
            self.action_tool_eraser,
        ):
            act.setEnabled(page_open)

    def _current_page_index(self) -> int | None:
        """Return the 0-indexed position of the path shown in the canvas."""
        path = self.file_table.current_path()
        if path is None:
            return None
        for i, imf in enumerate(self.image_files):
            if imf.path == path:
                return i
        return None

    # --------------------------------------------------------------- slots
    def open_image(self) -> None:
        """Open a single image file into the canvas via File -> Open Image.

        Uses ``QFileDialog.getOpenFileName`` (T-01-01 path-traversal mitigation)
        and routes through ``set_image_from_path`` which runs the size + suffix
        validators.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        self._open_single_image(Path(path))

    def open_folder(self) -> None:
        """Open a folder of images: scan (flat, non-recursive), sort, populate.

        UI-SPEC surface 4 Open Folder (Ctrl+Shift+O). Folder scan uses
        ``Path.iterdir`` + ``is_file`` + ``validate_image_path`` — symlink
        resolution is handled by ``Path.resolve()`` inside the validator.
        """
        directory = QFileDialog.getExistingDirectory(self, "Open Folder", "")
        if not directory:
            return
        self._load_folder(Path(directory))

    def _load_folder(self, directory: Path) -> None:
        """Scan ``directory`` for images and populate the FileTable."""
        if not directory.is_dir():
            return
        # Flat, non-recursive scan (UI-SPEC surface 4).
        candidates = [
            p
            for p in directory.iterdir()
            if p.is_file() and validate_image_path(p)
        ]
        self._set_pages(candidates)

    def _set_pages(self, paths: list[Path]) -> None:
        """Build ``ImageFile``s from ``paths`` and push them to the sidebar.

        The paths are natural-sorted before building ``ImageFile``s so the
        window's ordering matches the sidebar's displayed order — index lookups
        in :meth:`_current_page_index` rely on this consistency.
        """
        ordered = natsorted(paths, key=lambda p: str(p))
        self.image_files = [ImageFile(path=p) for p in ordered]
        self.file_table.set_pages([imf.path for imf in self.image_files])
        # Auto-select + load the first page (UI-SPEC: open folder shows page 1).
        if self.image_files:
            first = self.image_files[0]
            self.file_table.select_path(first.path)
            self.on_page_selected(first.path)
        else:
            self.status_bar_left.setText("No images found in folder")
        self._refresh_status_bar()

    def on_page_selected(self, path: Path) -> None:
        """Load ``path`` into the canvas and sync window title + status bar."""
        if not self.canvas.set_image_from_path(path):
            # UI-SPEC §Copywriting "file unreadable" dialog.
            QMessageBox.warning(
                self,
                "Couldn't open file",
                f"Couldn't open '{path.name}'.\nThe file may be corrupt or in an"
                " unsupported format.",
            )
            return
        self.setWindowTitle(f"Manga AI Studio \u2014 {path.name}")
        self.canvas.fit_to_window()
        self._add_recent_file(path)
        self._refresh_status_bar()

    def _open_single_image(self, path: Path) -> None:
        """Open one image as the sole page in the sidebar."""
        if not validate_image_path(path):
            QMessageBox.warning(
                self,
                "Couldn't open file",
                f"Couldn't open '{path.name}'.\nThe file may be in an unsupported"
                " format.",
            )
            return
        self._set_pages([path])

    # ---------------------------------------------------------- drag-drop
    def _on_files_dropped(self, paths: list[Path]) -> None:
        """FileTable dropped image files -> load them as the page list."""
        self._set_pages(paths)

    def _on_folder_dropped(self, directory: Path) -> None:
        """FileTable dropped a folder -> scan + load."""
        self._load_folder(directory)

    # ------------------------------------------------------------- recent
    def _settings(self):
        from PySide6.QtCore import QSettings

        return QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)

    def _recent_files(self) -> list[Path]:
        raw = self._settings().value("recentFiles", []) or []
        out: list[Path] = []
        for entry in raw:
            try:
                p = Path(entry)
            except (TypeError, ValueError):
                continue
            if validate_image_path(p):
                out.append(p)
        return out[:MAX_RECENT_FILES]

    def _add_recent_file(self, path: Path) -> None:
        current = [p for p in self._recent_files() if p != path]
        current.insert(0, path)
        self._settings().setValue(
            "recentFiles", [str(p) for p in current[:MAX_RECENT_FILES]]
        )
        self._refresh_recent_menu()

    def _clear_recent_files(self) -> None:
        self._settings().remove("recentFiles")
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        recents = self._recent_files()
        if not recents:
            placeholder = QAction("(empty)", self)
            placeholder.setEnabled(False)
            self.recent_menu.addAction(placeholder)
        else:
            for path in recents:
                act = QAction(path.name, self)
                act.triggered.connect(self._make_recent_opener(path))
                self.recent_menu.addAction(act)
        self.recent_menu.addSeparator()
        self.recent_menu.addAction(self.action_clear_recent)

    def _make_recent_opener(self, path: Path):
        def _open(_checked: bool = False) -> None:
            self._open_single_image(path)

        return _open

    # ------------------------------------------------------------- about
    def _on_about(self) -> None:
        """Help -> About: version + GPL v3 notice (UI-SPEC surface 1)."""
        from panelcleaner import __display_name__, __version__

        QMessageBox.about(
            self,
            "About Manga AI Studio",
            f"<h3>{__display_name__}</h3>"
            f"<p>Version {__version__}</p>"
            "<p>A manga scanlation workspace unifying page cleaning, OCR, and"
            " translation layout.</p>"
            "<p>Licensed under the GNU General Public License v3. Adapted from"
            " PanelCleaner (GPL v3).</p>",
        )

    # ------------------------------------------------------------- zoom sync
    def _on_zoom_changed(self, factor: float) -> None:
        """Update the status bar center field with the current zoom %."""
        self.status_bar_center.setText(f"{factor * 100:.0f}%")

    # ----------------------------------------------------- detection (plan 03)
    def _wire_detection_actions(self) -> None:
        """Connect plan-03 actions that need late-bound state.

        The Detect Text (D) and Toggle Mask Overlay (M) actions are created in
        the menu builders; their ``triggered`` signals are connected there. This
        method refreshes the enable/disable state now that the canvas exists.
        """
        self._refresh_action_states()

    # ------------------------------------------------------- tool panel (plan 04)
    def _wire_tool_actions(self) -> None:
        """Connect the ToolsPanel, tool shortcuts, and Clear Mask.

        - ToolsPanel.tool_changed -> set_active_tool -> canvas.set_tool
        - ToolsPanel.brush_size_changed -> canvas.set_brush_size
        - QShortcuts B/R/L/E/V (UI-SPEC §Keyboard) map to the 5 tools.
        - Clear Mask -> canvas.clear_mask (with the UI-SPEC confirmation in a
          follow-up; plan 04 wires the action, the destructive confirmation is
          part of the same flow).
        """
        self.tools_panel.tool_changed.connect(self.set_active_tool)
        self.tools_panel.brush_size_changed.connect(self.canvas.set_brush_size)
        # Default brush size so the canvas and panel agree on startup.
        self.canvas.set_brush_size(DEFAULT_BRUSH_SIZE)

        # Keyboard shortcuts (UI-SPEC §Keyboard surface 6). Installed on the
        # main window so they fire regardless of focus (as long as a child
        # widget doesn't consume them first). Reimplemented patterned after
        # MangaCleaner_GPU main_window.py:160-163 (D-12 reference-only).
        for key, tool in (
            ("V", ToolMode.MOVE),
            ("B", ToolMode.BRUSH),
            ("R", ToolMode.RECTANGLE),
            ("L", ToolMode.LASSO),
            ("E", ToolMode.ERASER),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda _t=tool: self.set_active_tool(_t))

        # Clear Mask (plan 04) — wired to the canvas.
        self.action_clear_mask.triggered.connect(self._on_clear_mask)
        self._refresh_action_states()

    def _make_tool_toolbar_button(self, action: QAction) -> QToolButton:
        """Build a checkable toolbar tool-button bound to ``action``.

        The buttons share the ToolsPanel's QActionGroup (passed implicitly via
        the action's group membership) so the toolbar and dock highlight the
        same active tool.
        """
        btn = QToolButton(self.toolbar)
        btn.setDefaultAction(action)
        btn.setCheckable(True)
        btn.setText(action.text())
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return btn

    def set_active_tool(self, tool: ToolMode) -> None:
        """Activate ``tool`` everywhere: ToolsPanel, toolbar, and canvas.

        Keeps the Tools dock, the toolbar tool-buttons, and the canvas in sync
        so a tool selected via menu, shortcut, or panel-button is reflected in
        all three (UI-SPEC surface 6).
        """
        self.canvas.set_tool(tool)
        # Sync the ToolsPanel (its actions drive the dock highlight) without
        # re-emitting tool_changed (the canvas is already updated).
        self.tools_panel.set_active_tool(tool)
        # Sync the toolbar buttons: the QActionGroup's checked action mirrors
        # the active tool. Match by data (the ToolMode stored on the action).
        for btn in self.toolbar.findChildren(QToolButton):
            act = btn.defaultAction()
            if act is not None and act.data() == tool:
                was = btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(was)

    def _on_clear_mask(self) -> None:
        """Edit -> Clear Mask: clear the canvas mask (destructive, plan 04).

        UI-SPEC §Copywriting mandates a [Cancel][Clear Mask] confirmation
        before clearing. The canvas.clear_mask call mutates the mask in place
        and emits mask_modified (consumed by plan 06 history).
        """
        if not self.canvas.has_mask():
            return
        if not self._confirm_clear_mask():
            return
        self.canvas.clear_mask()
        self._refresh_action_states()

    def _confirm_clear_mask(self) -> bool:
        """Show the Clear Mask confirmation (UI-SPEC §Copywriting destructive).

        Returns True only on Clear Mask; False on Cancel. Uses custom buttons
        so the UI-SPEC copy renders exactly (no Clear standard button member).
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Clear Mask")
        box.setText(
            "Clear the entire mask on this page? You can undo with mask undo"
            " (Alt+Z)."
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        clear_btn = box.addButton("Clear Mask", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(clear_btn)
        box.exec()
        return box.clickedButton() is clear_btn

    def _detection_backend(self) -> str:
        """Return the configured detection backend (D-02), default 'torch'."""
        try:
            profile = self.profile_manager.config.current_profile
            # PanelCleaner's TextDetectorConfig has no backend field; the
            # backend is an application-level concern. Default to torch (D-02).
            return getattr(profile, "detection_backend", "torch")
        except AttributeError:
            return "torch"

    def detect_text(self) -> None:
        """Run CTD text detection on the current page (Tools -> Detect Text, D).

        Async via ``Worker(QRunnable)`` on the global QThreadPool (RESEARCH
        Pitfall 3, T-01-07): the worker calls the adapter off the GUI thread;
        all Qt mutation happens in the main-thread signal handlers. Phase 1
        uses the D-09b in-process fallback (QThreadPool); the D-07/D-08
        subprocess split is deferred until a dependency conflict forces it.

        If a mask already exists, the "Replace the current mask" confirmation
        (UI-SPEC §Copywriting) is shown first.
        """
        if self._op_running:
            return
        path = self.file_table.current_path()
        if path is None:
            return

        # Replace-mask confirmation (UI-SPEC §Copywriting destructive re-detect).
        if self.canvas.has_mask() and not self._confirm_replace_mask():
            return

        # Resolve the adapter via the factory (D-02). torch is imported lazily
        # inside TorchCTDModel.load, so this import does not pull torch here.
        model = backend_factory("detection", self._detection_backend())

        # Build + dispatch the worker (PATTERNS.md §Shared Pattern 2).
        worker = Worker(self._run_detection_task, path, model)
        worker.signals.progress.connect(self._on_detection_progress)
        worker.signals.result.connect(self._on_detection_finished)
        worker.signals.error.connect(self._on_detection_error)
        worker.signals.finished.connect(self._on_detection_cleanup)
        worker.setAutoDelete(True)

        self._op_running = True
        self._refresh_action_states()
        self.error_chip.hide()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_bar_left.setText("Detecting text\u2026 0%")
        QThreadPool.globalInstance().start(worker)

    def _run_detection_task(
        self,
        image_path: Path,
        model,
        progress_callback=None,
        abort_flag=None,
    ) -> dict:
        """Worker task: load image, run detection, return mask + blocks.

        Runs on a QThreadPool thread — touches only numpy/Python and the
        adapter (T-01-07). Never touches Qt here. The adapter's ``detect``
        returns ``(mask_refined, blk_list)`` (the 3-tuple unpack lives inside
        ``TorchCTDModel.detect``).

        ``progress_callback``/``abort_flag`` are auto-injected by ``Worker``
        (worker_thread.py:97-124).
        """
        import cv2  # lazy import — keeps the main thread import-light

        if progress_callback is not None:
            progress_callback.emit((10, "Loading image\u2026"))
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")

        if progress_callback is not None:
            progress_callback.emit((30, "Loading model\u2026"))
        # model_path resolution: use the profile's configured path if set,
        # otherwise let the model_downloader fetch the default (plan 03 relies
        # on the PanelCleaner default path via model_downloader).
        model_path = self._resolve_detection_model_path()
        model.load(model_path, device="auto")

        if progress_callback is not None:
            progress_callback.emit((50, "Detecting text\u2026"))
        mask_refined, blk_list = model.detect(image)

        if progress_callback is not None:
            progress_callback.emit((90, "Compositing mask\u2026"))
        return {"mask": mask_refined, "blocks": blk_list}

    def _resolve_detection_model_path(self) -> Path:
        """Return the CTD model path from config, or the PanelCleaner default."""
        try:
            from panelcleaner.model_downloader import download_torch_model

            profile = self.profile_manager.config.current_profile
            configured = profile.text_detector.model_path
            if configured:
                return Path(configured)
            # Default: fetch via model_downloader (sha256-verified, T-01-04).
            return Path(download_torch_model())
        except Exception:
            # Let TorchCTDModel.load surface the FileNotFoundError (T-01-04)
            # if the model cannot be resolved.
            return Path("comictextdetector.pt")

    def _on_detection_progress(self, payload) -> None:
        """Update the status bar + progress bar (UI-SPEC surface 5/9)."""
        if isinstance(payload, tuple) and len(payload) == 2:
            percent, message = payload
        else:
            return
        self.progress_bar.setValue(int(percent))
        self.status_bar_left.setText(f"Detecting text\u2026 {int(percent)}%")

    def _on_detection_finished(self, result) -> None:
        """Composite the detected mask onto the canvas (main thread only).

        Converts the numpy heatmap (H, W) to a QImage, applies ``.copy()``
        buffer discipline (RESEARCH Pitfall 2), and hands it to
        ``EditorCanvas.set_mask`` which tints it with the rgba(255,0,0,0.63)
        overlay (UI-SPEC §Color).
        """
        import numpy as np

        mask = result["mask"]
        if mask is None:
            self.status_bar_left.setText("Detection complete (no mask)")
            return
        # numpy (H,W) uint8 -> QImage grayscale, copy-detached (Pitfall 2).
        h, w = mask.shape[:2]
        qimage = QImage(mask.data, w, h, w, QImage.Format.Format_Grayscale8)
        self.canvas.set_mask(qimage.copy())
        self.status_bar_left.setText("Detection complete")
        self._refresh_action_states()

    def _on_detection_error(self, worker_error) -> None:
        """Show the model-load error dialog + persistent #7a1f1f error chip.

        The full traceback goes to loguru (T-01-08); the QMessageBox shows only
        user-friendly copy (UI-SPEC §Copywriting model-load error).
        """
        logger.error(f"Detection failed: {worker_error}")
        self.error_chip.setText("Detection model error")
        self.error_chip.show()
        QMessageBox.critical(
            self,
            "Couldn't load the detection model.",
            "Check that the model files exist in the `models/` folder and see"
            " the log for details.",
        )
        self.status_bar_left.setText("Detection failed")

    def _on_detection_cleanup(self, _args) -> None:
        """Reset the async-op flag + progress UI after the worker finishes."""
        self._op_running = False
        self.progress_bar.hide()
        self._refresh_action_states()

    def _confirm_replace_mask(self) -> bool:
        """Show the replace-mask confirmation (UI-SPEC §Copywriting).

        Returns True only on Replace; False on Cancel. Caller guards: this is
        only invoked when ``canvas.has_mask()`` is True.

        Uses custom buttons so the UI-SPEC copy (``[Cancel] [Replace Mask]``)
        renders exactly — Qt's standard button set has no "Replace" member.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Detect Text")
        box.setText(
            "Replace the current mask with a new detection? Your manual edits"
            " will be lost \u2014 undo is available via mask undo (Alt+Z)."
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        replace_btn = box.addButton("Replace Mask", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(replace_btn)
        box.exec()
        return box.clickedButton() is replace_btn

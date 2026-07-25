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

import numpy as np
from loguru import logger
from natsort import natsorted
from PySide6.QtCore import Qt, QThreadPool, Signal
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
from manga_ai_studio.core.history_manager import HistoryManager
from manga_ai_studio.core.image_file import ImageFile
from manga_ai_studio.core.mask_editor import DEFAULT_BRUSH_SIZE, ToolMode, mask_to_numpy_binary
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

    # D-09 cancel affordance (plan 04): emitting this signal flips the running
    # batch Worker's ``SharableFlag`` via Worker.abort (worker_thread.py
    # abort_signal auto-injection). Must be a class-level Signal — PySide6
    # requires Signal to be defined on the class, not an instance.
    batch_abort_requested = Signal()

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

        # D-08/D-09 (plan 04): True specifically while a BATCH worker runs.
        # Distinct from ``_op_running`` so the Cancel Batch action can gate on
        # it alone (Cancel is only meaningful during a batch, not during a
        # single-page detect/inpaint). Cleared unconditionally in
        # ``_on_batch_cleanup`` (Pitfall 7).
        self._batch_active = False

        # Bug A (checkpoint rework): the current batch's mode ("detect" /
        # "clean" / "detect_and_clean") so ``_on_batch_progress`` can render
        # the mode-aware status label ("Detecting N%..." vs "Cleaning N%...")
        # instead of the previously hardcoded "Cleaning". Set in
        # ``_dispatch_batch``, cleared in ``_on_batch_cleanup``.
        self._batch_mode: str | None = None

        # Bug B (checkpoint rework): set True by ``_cancel_batch`` so the
        # cleanup handler renders a "Cancelled" status instead of leaving the
        # stale per-page progress text ("Cleaning N%"/"Inpainting N%"). Read
        # and cleared in ``_on_batch_cleanup``.
        self._batch_cancelled = False

        # D-11: the page index shown BEFORE the current select_path, used to
        # persist the OUTGOING page's mask at the on_page_selected boundary.
        # Because _set_pages (main_window.py:553-556) calls
        # file_table.select_path(first.path) BEFORE on_page_selected(first.path),
        # by the time on_page_selected runs, file_table.current_path() (and
        # therefore _current_page_index()) already return the INCOMING page —
        # so the OUTGOING index MUST come from this stored field, NOT from
        # _current_page_index() (PATTERNS.md file 4a note + RESEARCH Open Q2).
        self._last_page_index: int | None = None

        # Inpaint history hook (plan 06 wires the real HistoryManager here;
        # _on_inpaint_finished activates the push_image_action call site).
        self.history = HistoryManager(limit=20)

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
        # Wire the plan-06 actions (HistoryManager push hook + the four
        # undo/redo handlers + shortcuts + button-state refresh).
        self._wire_history_actions()
        # Wire the plan-04 batch actions (Esc -> Cancel Batch).
        self._wire_batch_actions()

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

        # Export Page (Ctrl+E) — plan 04 (PROJ-02): writes the DISPLAYED canvas
        # image (not a re-clean) to a user-chosen PNG/JPG path via
        # QFileDialog.getSaveFileName. The T-01-01 OS-validated-path sibling of
        # open_image's getOpenFileName (T-02-01 mitigation).
        self.action_export_page = QAction("Export Page\u2026", self)
        self.action_export_page.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_page.triggered.connect(self.export_page)
        self.action_export_page.setEnabled(False)

        # Batch submenu (FLOW-03 / D-01): the three batch actions operate on the
        # currently-open folder (D-06). All three dispatch the Plan 03 entry
        # points on a single Worker(QRunnable). Disabled until a folder is open
        # AND no async op is running (refreshed in _refresh_action_states).
        self.batch_menu = self.menuBar().addMenu("Batch")
        self.action_batch_detect = QAction("Batch Detect", self)
        self.action_batch_detect.triggered.connect(self.batch_detect)
        self.action_batch_detect.setEnabled(False)
        self.action_batch_clean = QAction("Batch Clean", self)
        self.action_batch_clean.triggered.connect(self.batch_clean)
        self.action_batch_clean.setEnabled(False)
        self.action_batch_detect_and_clean = QAction("Batch Detect + Clean", self)
        self.action_batch_detect_and_clean.triggered.connect(self.batch_detect_and_clean)
        self.action_batch_detect_and_clean.setEnabled(False)
        self.batch_menu.addAction(self.action_batch_detect)
        self.batch_menu.addAction(self.action_batch_clean)
        self.batch_menu.addAction(self.action_batch_detect_and_clean)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_open_image)
        file_menu.addAction(self.action_open_folder)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export_page)
        file_menu.addMenu(self.batch_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

    def _build_edit_menu(self) -> None:
        # Plan 06 undo/redo actions — disabled until their stack has content
        # (refreshed in _update_undo_redo_actions). Shortcuts are also installed
        # as QShortcut in _wire_history_actions so they fire regardless of focus
        # (MangaCleaner_GPU main_window.py:168-171 pattern, reimplemented).
        # NOTE: setShortcut is intentionally NOT called here — the focus-robust
        # QShortcut registrations in _wire_history_actions are the single
        # source for these key sequences. A duplicate setShortcut here would
        # trigger Qt's "Ambiguous shortcut overload" warning (CR-14).
        self.action_undo_image = QAction("Undo Image", self)
        self.action_undo_image.setEnabled(False)

        self.action_redo_image = QAction("Redo Image", self)
        self.action_redo_image.setEnabled(False)

        self.action_undo_mask = QAction("Undo Mask", self)
        self.action_undo_mask.setEnabled(False)

        self.action_redo_mask = QAction("Redo Mask", self)
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

        # Show Original (P) — wired in plan 05 (sticky before/after preview,
        # UI-SPEC surface 7). Checkable: toggling calls canvas.show_original.
        self.action_show_original = QAction("Show Original", self)
        self.action_show_original.setShortcut(QKeySequence("P"))
        self.action_show_original.setCheckable(True)
        self.action_show_original.toggled.connect(self._on_show_original_toggled)
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

        # Inpaint (C) — wired in plan 05 (async LaMa inpainting).
        self.action_inpaint = QAction("Inpaint", self)
        self.action_inpaint.setShortcut(QKeySequence("C"))
        self.action_inpaint.triggered.connect(self.inpaint)
        # Enabled iff a page is open AND a mask exists AND no async op is running
        # (UI-SPEC surface 7; _refresh_action_states gates this).
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

        # Cancel Batch (D-09) — plan 04: emits batch_abort_requested, which the
        # running Worker.abort consumes (worker_thread.py abort_signal wiring).
        # Disabled unless a batch is running (refreshed in _refresh_action_states).
        # Esc is the keyboard affordance (wired in _wire_batch_actions).
        self.action_cancel_batch = QAction("Cancel Batch", self)
        self.action_cancel_batch.triggered.connect(self._cancel_batch)
        self.action_cancel_batch.setEnabled(False)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.action_detect_text)
        tools_menu.addAction(self.action_inpaint)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_tool_move)
        tools_menu.addAction(self.action_tool_brush)
        tools_menu.addAction(self.action_tool_rectangle)
        tools_menu.addAction(self.action_tool_lasso)
        tools_menu.addAction(self.action_tool_eraser)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_cancel_batch)

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
        self.toolbar.addAction(self.action_inpaint)
        self.toolbar.addSeparator()
        # Tool-buttons section (plan 04): checkable QToolButtons sharing the
        # ToolsPanel's QActionGroup so the toolbar and dock stay in sync
        # (UI-SPEC surface 1 toolbar layout).
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_move))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_brush))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_rectangle))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_lasso))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_eraser))
        # Undo/redo two-pairs-with-divider section (plan 06, UI-SPEC surface 8):
        # [Undo Image][Redo Image] ‖ [Undo Mask][Redo Mask]. Each action carries
        # its shortcut in the tooltip. The two addSeparator() calls flank the
        # section; the inner addSeparator() divides the image pair from the mask
        # pair (the contract's "two pairs separated by a divider").
        self.toolbar.addSeparator()
        self.action_undo_image.setToolTip("Undo Image (Ctrl+Z)")
        self.action_redo_image.setToolTip("Redo Image (Ctrl+Shift+Z)")
        self.action_undo_mask.setToolTip("Undo Mask (Alt+Z)")
        self.action_redo_mask.setToolTip("Redo Mask (Alt+Shift+Z)")
        self.toolbar.addAction(self.action_undo_image)
        self.toolbar.addAction(self.action_redo_image)
        self.toolbar.addSeparator()  # the divider between the two pairs
        self.toolbar.addAction(self.action_undo_mask)
        self.toolbar.addAction(self.action_redo_mask)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_toggle_mask_overlay)
        # Preview (hold) button (plan 05, UI-SPEC surface 7): press and hold to
        # show the original pre-inpaint image; release to return to the result.
        # Disabled until an inpaint result exists.
        self.btn_preview_hold = QToolButton(self.toolbar)
        self.btn_preview_hold.setText("Preview (hold)")
        self.btn_preview_hold.setEnabled(False)
        self.btn_preview_hold.pressed.connect(lambda: self.canvas.show_original(True))
        self.btn_preview_hold.released.connect(lambda: self.canvas.show_original(False))
        self.toolbar.addWidget(self.btn_preview_hold)

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
        - Inpaint (C): enabled iff a page is open AND a mask exists AND no async
          op is running (UI-SPEC surface 7).
        - Toggle Mask Overlay (M): enabled iff a mask exists on the canvas.
        - Show Original (P) + Preview (hold): enabled iff an inpaint result is
          stored (UI-SPEC surface 7 before/after compare).
        - Mask tools (V/B/R/L/E): enabled iff a page is open (Move always
          enabled as a no-op-safe default).
        - Clear Mask: enabled iff a mask exists.
        """
        page_open = self._current_page_index() is not None
        has_mask = self.canvas.has_mask()
        # Inpaint requires actual mask CONTENT (not just an initialized
        # transparent mask) — running LaMa on an empty mask is a wasted model
        # load (UI-SPEC surface 7; plan 05 Task 2 behavior).
        has_mask_content = self.canvas.has_mask_content()
        self.action_detect_text.setEnabled(page_open and not self._op_running)
        self.action_inpaint.setEnabled(
            page_open and has_mask_content and not self._op_running
        )
        self.action_toggle_mask_overlay.setEnabled(has_mask)
        self.action_clear_mask.setEnabled(has_mask)
        has_inpaint = self.canvas.has_inpaint_result()
        self.action_show_original.setEnabled(has_inpaint)
        self.btn_preview_hold.setEnabled(has_inpaint)
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

        # Plan 04 batch/export actions. Export Page needs a page open and no
        # running async op. The three batch actions operate on the open folder
        # (D-06) and require no running async op (D-08 — a batch blocks the
        # editor). Cancel Batch is enabled ONLY while a batch is running
        # (D-09); it is meaningless otherwise.
        folder_open = bool(self.image_files)
        self.action_export_page.setEnabled(page_open and not self._op_running)
        self.action_batch_detect.setEnabled(folder_open and not self._op_running)
        self.action_batch_clean.setEnabled(folder_open and not self._op_running)
        self.action_batch_detect_and_clean.setEnabled(
            folder_open and not self._op_running
        )
        self.action_cancel_batch.setEnabled(self._batch_active)

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
        """Load ``path`` into the canvas and sync window title + status bar.

        D-11 per-page mask persistence seam (plan 02-02). The four-step
        sequence lifts mask state out of the canvas (which holds one mask for
        the *current* page) onto ``ImageFile.mask`` so masks survive page
        navigation. This is the load-bearing data-model change that makes the
        two-stage batch workflow possible: Batch Detect (Plan 03) stores one
        mask per page here; Batch Clean (Plan 03) reads them all back.

        Ordering (PATTERNS.md file 4a note): ``_set_pages`` (main_window.py:553-556)
        calls ``file_table.select_path(first.path)`` BEFORE
        ``on_page_selected(first.path)``, so by the time this method runs,
        ``file_table.current_path()`` (and therefore ``_current_page_index()``)
        already return the INCOMING page. The OUTGOING index MUST come from the
        stored ``self._last_page_index`` field — NOT from
        ``_current_page_index()`` (which has already flipped to the incoming
        page). Pitfall 2: every write into ``ImageFile.mask`` uses ``.copy()``
        to detach from the canvas buffer (the regression guard is
        ``test_mask_persistence_uses_copy``).

        Step 1 (persist OUTGOING): snapshot the current canvas mask (if any)
            into the OUTGOING page's ``ImageFile.mask`` via
            ``canvas.get_mask().copy()`` (MANDATORY .copy() — Pitfall 2).
        Step 2 (undo reset, unchanged): a fresh HistoryManager per page keeps
            undo from crossing page boundaries (test_page_change_resets_history).
            Only the mask is lifted out of the canvas; undo stays per-page.
        Step 3 (load the new page image, unchanged): set_image_from_path.
        Step 4 (restore INCOMING): if the INCOMING page's ``ImageFile.mask``
            has content, restore it onto the canvas via
            ``canvas.set_mask(image_file.mask.copy())`` (set_mask also copies
            internally at canvas.py:305, but the boundary .copy() is
            belt-and-suspenders and what the regression test asserts on).
        Step 5 (tail, unchanged): window title, fit-to-window, recent, status.

        Plan 04 disables page-switch while ``_op_running`` to avoid the D-11
        write race (RESEARCH Open Question Q2 / T-02-05); this plan implements
        the persistence seam only and must NOT add navigation-disabling logic.
        """
        # Step 1: persist the OUTGOING page's canvas mask into its ImageFile.mask.
        # The OUTGOING index is the stored _last_page_index (NOT
        # _current_page_index(), which has already flipped to the incoming page).
        outgoing_idx = self._last_page_index
        if (
            outgoing_idx is not None
            and 0 <= outgoing_idx < len(self.image_files)
            and self.canvas.has_mask()
        ):
            # MANDATORY .copy(): detaches the QImage from the live canvas buffer
            # so subsequent canvas mutation cannot reach back through the shared
            # buffer (Pitfall 2 / T-02-04, regression-guarded by
            # test_mask_persistence_uses_copy).
            self.image_files[outgoing_idx].mask = self.canvas.get_mask().copy()

        # Step 2: reset the per-page history (unchanged from plan 06).
        self.reset_history()

        # Step 3: load the new page image (unchanged).
        if not self.canvas.set_image_from_path(path):
            # UI-SPEC §Copywriting "file unreadable" dialog.
            QMessageBox.warning(
                self,
                "Couldn't open file",
                f"Couldn't open '{path.name}'.\nThe file may be corrupt or in an"
                " unsupported format.",
            )
            return

        # Step 4: restore the INCOMING page's persisted mask onto the canvas.
        # _current_page_index() now correctly returns the INCOMING index
        # (current_path was set to the incoming page by the preceding select_path).
        incoming_idx = self._current_page_index()
        if (
            incoming_idx is not None
            and 0 <= incoming_idx < len(self.image_files)
            and self.image_files[incoming_idx].mask is not None
            and not self.image_files[incoming_idx].mask.isNull()
        ):
            # The boundary .copy() is belt-and-suspenders (set_mask also copies
            # at canvas.py:305); it is what test_mask_persistence_uses_copy
            # asserts on for the INCOMING direction.
            self.canvas.set_mask(self.image_files[incoming_idx].mask.copy())

        # Step 5 (unchanged tail).
        self.setWindowTitle(f"Manga AI Studio \u2014 {path.name}")
        self.canvas.fit_to_window()
        self._add_recent_file(path)
        self._refresh_status_bar()

        # Record THIS page as the OUTGOING page for the NEXT navigation. Must
        # run AFTER the restore so a subsequent select_path→on_page_selected
        # captures this page's (now restored) state as its outgoing snapshot.
        # Plan 04 disables navigation while _op_running to avoid the D-11 write
        # race (RESEARCH Open Question Q2 / T-02-05).
        self._last_page_index = self._current_page_index()

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

        # Re-evaluate action states whenever the mask changes (plan 05: the
        # Inpaint (C) action gates on has_mask(), so it must refresh after each
        # brush/rect/lasso/erase stroke commits — UI-SPEC surface 7).
        self.canvas.mask_modified.connect(self._refresh_action_states)

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

    # ------------------------------------------------------ history (plan 06)
    def _wire_history_actions(self) -> None:
        """Connect the HistoryManager + the four undo/redo actions + shortcuts.

        Reimplemented patterned after MangaCleaner_GPU ``main_window.py:110``
        (mask_changed -> push_mask_state), ``168-171`` (QShortcut Ctrl+Z /
        Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z), and ``204-228`` (the four
        on_undo_image/on_redo_image/on_undo_mask/on_redo_mask handlers). D-12
        reference-only.

        The mask push hook: ``canvas.mask_modified`` (plan 04, once per
        completed stroke) triggers ``_on_mask_modified`` which pushes a
        ``.copy()`` of the current mask onto the mask undo stack. This is the
        ONLY mask push path; undo application (``canvas.apply_undo_mask``)
        bypasses ``mask_modified`` entirely so undo does not re-push
        (``test_undo_does_not_repush`` regression guard; UI-SPEC surface 8
        prohibition).
        """
        # Mask push hook: plan-04 mask_modified -> push a .copy() of the mask.
        self.canvas.mask_modified.connect(self._on_mask_modified)

        # Edit-menu actions -> the four handlers.
        self.action_undo_image.triggered.connect(self.on_undo_image)
        self.action_redo_image.triggered.connect(self.on_redo_image)
        self.action_undo_mask.triggered.connect(self.on_undo_mask)
        self.action_redo_mask.triggered.connect(self.on_redo_mask)

        # Application-wide QShortcuts (MangaCleaner_GPU main_window.py:168-171
        # pattern, reimplemented). The Edit-menu action shortcuts may be
        # shadowed by the canvas's keyPressEvent when the canvas has focus; the
        # QShortcut on the MainWindow is the robust path.
        for keys, slot in (
            (QKeySequence("Ctrl+Z"), self.on_undo_image),
            (QKeySequence("Ctrl+Shift+Z"), self.on_redo_image),
            (QKeySequence("Alt+Z"), self.on_undo_mask),
            (QKeySequence("Alt+Shift+Z"), self.on_redo_mask),
        ):
            sc = QShortcut(keys, self)
            sc.activated.connect(slot)

        self._update_undo_redo_actions()

    def reset_history(self) -> None:
        """Replace the HistoryManager with a fresh instance.

        Called on page change (``on_page_selected``) so undo never crosses
        page boundaries (UI-SPEC surface 8; MangaCleaner_GPU
        main_window.py:347 pattern — ``self.history = HistoryManager(...)`` on
        file open). Also refreshes the undo/redo button enable state.
        """
        self.history = HistoryManager(limit=20)
        self._update_undo_redo_actions()

    def _on_mask_modified(self) -> None:
        """Mask push hook: a stroke committed -> snapshot the current mask.

        ``push_mask_state`` ``.copy()``-detaches internally (Pitfall 2), so
        passing the live ``canvas.get_mask()`` here is safe. The hook is the
        ONLY mask push path; ``on_undo_mask`` applies snapshots via
        ``canvas.apply_undo_mask`` (no re-emission).
        """
        if self.history is None or not self.canvas.has_mask():
            return
        self.history.push_mask_state(self.canvas.get_mask())
        self._update_undo_redo_actions()

    def on_undo_mask(self) -> None:
        """Alt+Z — pop the previous mask snapshot and apply it.

        ``pop_mask_undo`` stashes the current mask into the redo branch and
        returns a ``.copy()``-detached snapshot; ``canvas.apply_undo_mask``
        replaces the editable mask WITHOUT emitting ``mask_modified`` (no
        re-push). Reimplemented patterned after MangaCleaner_GPU
        ``main_window.py:215-219``.
        """
        if self.history is None:
            return
        current = self.canvas.get_mask()
        if current is None:
            return
        prev = self.history.pop_mask_undo(current)
        if prev is not None:
            self.canvas.apply_undo_mask(prev)
        self._update_undo_redo_actions()

    def on_redo_mask(self) -> None:
        """Alt+Shift+Z — replay a previously-undone mask snapshot."""
        if self.history is None:
            return
        current = self.canvas.get_mask()
        if current is None:
            return
        nxt = self.history.pop_mask_redo(current)
        if nxt is not None:
            self.canvas.apply_undo_mask(nxt)
        self._update_undo_redo_actions()

    def on_undo_image(self) -> None:
        """Ctrl+Z — pop the previous image patch and composite it into the canvas.

        ``pop_image_undo`` swaps the current image's region into the redo branch
        and returns a ``.copy()``-detached ``(x, y, patch)``; the patch is the
        pre-inpaint content for that region. ``canvas.apply_undo_image`` writes
        it back into the displayed image. Reimplemented patterned after
        MangaCleaner_GPU ``main_window.py:204-208``.
        """
        if self.history is None:
            return
        current_img = self.canvas.get_image_numpy()
        if current_img is None:
            return
        result = self.history.pop_image_undo(current_img)
        if result is not None:
            x, y, patch = result
            self.canvas.apply_undo_image(x, y, patch)
        self._update_undo_redo_actions()

    def on_redo_image(self) -> None:
        """Ctrl+Shift+Z — re-apply a previously-undone image patch."""
        if self.history is None:
            return
        current_img = self.canvas.get_image_numpy()
        if current_img is None:
            return
        result = self.history.pop_image_redo(current_img)
        if result is not None:
            x, y, patch = result
            self.canvas.apply_undo_image(x, y, patch)
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self) -> None:
        """Enable/disable the four undo/redo actions by stack emptiness.

        Each action is enabled iff (a) a page is open AND (b) the matching
        ``can_*`` flag is True. Called after every push/pop and on page change
        (UI-SPEC surface 8: each button disabled when its stack is empty).
        """
        if not hasattr(self, "action_undo_image"):
            return  # not yet built (early init)
        has_page = self._current_page_index() is not None
        history_ready = self.history is not None
        self.action_undo_mask.setEnabled(
            has_page and history_ready and self.history.can_undo_mask()
        )
        self.action_redo_mask.setEnabled(
            has_page and history_ready and self.history.can_redo_mask()
        )
        self.action_undo_image.setEnabled(
            has_page and history_ready and self.history.can_undo_image()
        )
        self.action_redo_image.setEnabled(
            has_page and history_ready and self.history.can_redo_image()
        )

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
        import numpy as np

        if progress_callback is not None:
            progress_callback.emit((10, "Loading image\u2026"))
        # Use np.fromfile + cv2.imdecode (NOT cv2.imread): cv2.imread fails on
        # (a) formats whose codec the path-based decoder can't find (e.g. .webp
        # in many OpenCV builds — surfaces as a `findDecoder` warning + None
        # return), and (b) non-ASCII path characters on Windows. Reading the
        # file as raw bytes via numpy and decoding via imdecode handles both.
        # This mirrors the vendored CTD helper at
        # panelcleaner/comic_text_detector/utils/io_utils.py:imread (CR-17).
        try:
            image = cv2.imdecode(
                np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
            )
        except (OSError, ValueError) as exc:
            raise FileNotFoundError(f"Could not read image: {image_path}") from exc
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
        """Return the CTD model path, downloading it on first use only.

        Delegates to ``download_torch_model(cache_dir)`` where
        ``cache_dir = config.get_model_cache_dir()`` (model_downloader.py:112;
        the Config instance owns the cache dir, NOT the Profile). On
        filesystem/network failure (``FileNotFoundError`` / ``OSError``),
        returns ``cache_dir / comictextdetector.pt`` so ``TorchCTDModel.load``
        surfaces a meaningful ``FileNotFoundError`` (T-01-04) pointing at a
        real, findable path. Programming errors (``TypeError``,
        ``AttributeError``, ``ValueError``) PROPAGATE so signature drift and
        wrong-arg bugs surface in dev/test instead of silently degrading in
        production (CR-01 gap closure, regression-guarded by
        ``test_resolve_detection_model_path_programming_errors_propagate``).

        CR-11 (UAT gap closure): the vendored ``download_torch_model``
        unconditionally re-downloads — it never checks whether the file
        already exists in the cache. Without an existence check here, every
        detect call re-fetched the ~80MB CTD model even when it was already
        cached. We check the cache path first and short-circuit when the
        model is present (mirrors :meth:`_resolve_inpainting_model_path`).
        """
        config = self.profile_manager.config
        profile = config.current_profile
        configured = profile.text_detector.model_path
        if configured:
            return Path(configured)
        cache_dir = config.get_model_cache_dir()
        from panelcleaner.model_downloader import download_torch_model

        # If the model is already present (prior download, manual install, or
        # a copy from an upstream pcleaner install), return the existing path
        # immediately — no re-download. The vendored download_torch_model
        # would otherwise fetch 80MB on every detect call (CR-11).
        expected = cache_dir / "comictextdetector.pt"
        if expected.is_file():
            return expected

        # download_torch_model(cache_dir) -> Path | None (None on download
        # failure, e.g. network offline). Handle both: a real path on success,
        # or fall back to the vendored default filename under the cache dir.
        try:
            resolved = download_torch_model(cache_dir)
        except (FileNotFoundError, OSError) as exc:
            # Legitimate filesystem/network failure modes during a model
            # download (T-01-08). Log so the failure is observable in logs
            # rather than silent; the fallback path still lets a manual
            # install to cache_dir/comictextdetector.pt succeed.
            logger.warning(f"Detection model resolution failed: {exc}")
            resolved = None
        if resolved is not None:
            return Path(resolved)
        # Vendored default (model_downloader.py:16 TORCH_MODEL_NAME) under the
        # cache dir so TorchCTDModel.load surfaces a meaningful path.
        return expected

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

    # --------------------------------------------------------- inpaint (plan 05)
    def _inpainting_backend(self) -> str:
        """Return the configured inpainting backend (D-02), default 'torch'.

        Same shape as :meth:`_detection_backend`: the backend is an
        application-level concern; the profile carries an optional
        ``inpainting_backend`` attribute. Default torch -> TorchLamaModel
        (factory.py inpainting/torch branch).
        """
        try:
            profile = self.profile_manager.config.current_profile
            return getattr(profile, "inpainting_backend", "torch")
        except AttributeError:
            return "torch"

    def _resolve_inpainting_model_path(self) -> Path:
        """Return the LaMa model path, downloading it on first use if missing.

        Mirrors :meth:`_resolve_detection_model_path`: the vendored
        ``download_inpainting_model(cache_dir)`` actually fetches the ~200MB
        weights into ``config.get_model_cache_dir()`` and returns the path,
        while ``get_inpainting_model_path(config)`` only returns a path
        string (no download). Using the download function is required for
        the first-run UX to work (CR-10 UAT gap closure: CR-02 made the path
        correct but never triggered the download, so first-run inpaint raised
        ``FileNotFoundError`` at ``SimpleLama`` construction time).

        On filesystem/network failure (``FileNotFoundError`` / ``OSError``),
        returns the vendored default path under the cache dir so
        ``SimpleLama`` surfaces a meaningful ``FileNotFoundError`` pointing at
        a real, findable path (T-01-04). Programming errors
        (``AttributeError``, ``TypeError``, ``ValueError``) PROPAGATE so
        signature drift and wrong-arg bugs surface in dev/test
        (regression-guarded by
        ``test_resolve_inpainting_model_path_programming_errors_propagate``).
        """
        config = self.profile_manager.config
        cache_dir = config.get_model_cache_dir()
        from panelcleaner.model_downloader import (
            get_inpainting_model_path,
            download_inpainting_model,
        )

        # If the model is already present (prior download, manual install, or
        # a copy from an upstream pcleaner install), return the existing path
        # immediately — no re-download. This honors an existing 200MB file
        # without forcing a redundant fetch.
        expected = Path(get_inpainting_model_path(config))
        if expected.is_file():
            return expected

        # download_inpainting_model(cache_dir) -> Path | None (None on download
        # failure, e.g. network offline). Handle both: a real path on success,
        # or fall back to the vendored default filename under the cache dir.
        try:
            resolved = download_inpainting_model(cache_dir)
        except (FileNotFoundError, OSError) as exc:
            # Legitimate filesystem/network failure modes during a model
            # download (T-01-08). Log so the failure is observable in logs
            # rather than silent; the fallback path still lets a manual
            # install to cache_dir/anime-manga-big-lama.pt succeed.
            logger.warning(f"Inpainting model resolution failed: {exc}")
            resolved = None
        if resolved is not None:
            return Path(resolved)
        # Vendored default (model_downloader.py INPAINTING model filename)
        # under the cache dir so SimpleLama surfaces a meaningful path.
        return expected

    def inpaint(self) -> None:
        """Run LaMa inpainting on the current page + mask (Tools -> Inpaint, C).

        Async via ``Worker(QRunnable)`` (RESEARCH Pitfall 3, T-01-07): the GUI
        thread extracts the page RGB + the binary mask BEFORE dispatch (so the
        worker only touches numpy), then the worker calls the LaMa adapter off
        the GUI thread. All Qt mutation happens in the main-thread signal
        handlers. Phase 1 uses the D-09b in-process fallback (QThreadPool).

        Non-destructive: unlike :meth:`detect_text` there is no confirmation
        dialog (UI-SPEC §Copywriting — inpainting is reversible via image undo
        and never destroys the original).
        """
        if self._op_running:
            return
        path = self.file_table.current_path()
        if path is None:
            return
        if not self.canvas.has_mask():
            return

        # Extract the page + mask on the GUI thread (numpy arrays own their
        # buffers — safe to hand to the worker). Both bridge methods enforce
        # .copy() detachment (Pitfall 2, PATTERNS.md §Shared Pattern 5).
        image_rgb = self.canvas.get_image_numpy()
        mask_binary = mask_to_numpy_binary(self.canvas.get_mask())
        if image_rgb is None:
            return

        model_path = self._resolve_inpainting_model_path()
        model = backend_factory("inpainting", self._inpainting_backend())

        worker = Worker(self._run_inpaint_task, image_rgb, mask_binary, model_path, model)
        worker.signals.progress.connect(self._on_inpaint_progress)
        worker.signals.result.connect(self._on_inpaint_finished)
        worker.signals.error.connect(self._on_inpaint_error)
        worker.signals.finished.connect(self._on_inpaint_cleanup)
        worker.setAutoDelete(True)

        self._op_running = True
        self._refresh_action_states()
        self.error_chip.hide()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_bar_left.setText("Inpainting\u2026 0%")
        QThreadPool.globalInstance().start(worker)

    def _run_inpaint_task(
        self,
        image_rgb: np.ndarray,
        mask_binary: np.ndarray,
        model_path: Path,
        model,
        progress_callback=None,
        abort_flag=None,
    ) -> dict:
        """Worker task: load LaMa, run inpaint, return result + bbox.

        Runs on a QThreadPool thread — touches only numpy/Python and the
        adapter (T-01-07). Never touches Qt here. The adapter's ``inpaint``
        returns an ``(H, W, 3)`` uint8 RGB array (the size-reclamp crop is
        handled inside ``TorchLamaModel.inpaint``).
        """
        if progress_callback is not None:
            progress_callback.emit((20, "Loading model\u2026"))
        model.load(model_path)

        if progress_callback is not None:
            progress_callback.emit((50, "Inpainting\u2026"))
        result_rgb = model.inpaint(image_rgb, mask_binary)

        if progress_callback is not None:
            progress_callback.emit((90, "Compositing result\u2026"))
        bbox = compute_mask_bbox(mask_binary)
        return {"image": result_rgb, "bbox": bbox}

    def _on_inpaint_progress(self, payload) -> None:
        """Update the status bar + progress bar (UI-SPEC surface 5/9)."""
        if isinstance(payload, tuple) and len(payload) == 2:
            percent, _message = payload
        else:
            return
        self.progress_bar.setValue(int(percent))
        self.status_bar_left.setText(f"Inpainting\u2026 {int(percent)}%")

    def _on_inpaint_finished(self, result) -> None:
        """Display the inpainted result (main thread only).

        Hands the result RGB + the mask bbox to
        ``EditorCanvas.set_image_from_numpy``, which captures the pre-inpaint
        numpy (for the Preview toggle) and composites only the bbox region so
        unchanged artwork is preserved pixel-exact. QImage ``.copy()`` buffer
        discipline (RESEARCH Pitfall 2, PATTERNS.md §Shared Pattern 5) is
        enforced inside the canvas bridge.

        History hook: if ``self.history`` is wired (plan 06), pushes the
        bbox-shaped pre-inpaint patch (sliced from the pre-inpaint image
        BEFORE ``set_image_from_numpy`` overwrites it) so image-undo (Ctrl+Z)
        reverts just the inpainted region (CR-03 gap closure). The patch shape
        is exactly ``(bbox_h, bbox_w, _)`` — what ``pop_image_undo`` +
        ``apply_undo_image`` expect; pushing the FULL image (the CR-03 bug)
        caused ``apply_undo_image`` to write a mis-shaped region and silently
        corrupt the page on Ctrl+Z.
        """
        result_rgb = result["image"]
        bbox = result["bbox"]
        if result_rgb is None:
            self.status_bar_left.setText("Inpainting complete (no result)")
            return

        original_patch_numpy = None
        if self.history is not None and bbox is not None:
            # Unpack the full bbox (compute_mask_bbox returns (x, y, w, h)).
            # The CR-03 bug read only x1, y1 and ignored w, h, then pushed the
            # FULL image as the patch — pop_image_undo read its shape[:2] as
            # the patch dims and apply_undo_image wrote a mis-shaped region.
            x1, y1, bw, bh = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            try:
                pre_inpaint = self.canvas.get_image_numpy()
            except (AttributeError, RuntimeError):
                # Canvas-not-ready failure modes only. Do NOT use a bare
                # except Exception here — programming errors must propagate
                # (T-01-17 shared root cause).
                pre_inpaint = None
            if pre_inpaint is not None:
                # CR-03 fix: push the bbox region (not the full image) so
                # pop_image_undo + apply_undo_image write a correctly-shaped
                # region on Ctrl+Z. The .copy() is MANDATORY (pre_inpaint is
                # a view into the canvas buffer; the slice must be detached
                # before crossing into the HistoryManager — RESEARCH Pitfall 2,
                # same discipline as every other numpy<->history bridge).
                original_patch_numpy = pre_inpaint[y1 : y1 + bh, x1 : x1 + bw].copy()

        self.canvas.set_image_from_numpy(result_rgb, bbox=bbox)

        # CR-16 (UAT): the mask has been consumed by the inpaint. Clear it so
        # the red overlay does not sit on top of the now-inpainted region
        # (which would both look wrong and cause a subsequent inpaint to
        # re-process the already-cleaned area). Clear the mask internals
        # directly (fill + update_mask_display) rather than calling
        # clear_mask(), which emits mask_modified — that would push a
        # spurious mask-undo entry. The user's action was "inpaint", not
        # "paint a mask", so the mask-undo stack must not gain an entry for
        # the consumption.
        canvas_mask = self.canvas.get_mask()
        if canvas_mask is not None and not canvas_mask.isNull():
            canvas_mask.fill(Qt.GlobalColor.transparent)
            self.canvas.update_mask_display()

        if self.history is not None and bbox is not None and original_patch_numpy is not None:
            # No bare except Exception: pass here (WR-05 closed at this site).
            # history.push_image_action only fails on programming errors
            # (TypeError/AttributeError from a future API change), which MUST
            # propagate so the bug surfaces in dev/test instead of silently
            # corrupting the undo state.
            self.history.push_image_action(x1, y1, original_patch_numpy)

        self.status_bar_left.setText("Inpainting complete")
        self._refresh_action_states()

    def _on_inpaint_error(self, worker_error) -> None:
        """Show the model-load error dialog + persistent #7a1f1f error chip.

        Mirrors :meth:`_on_detection_error`: the full traceback goes to loguru
        (T-01-08); the QMessageBox shows only user-friendly copy (UI-SPEC
        §Copywriting model-load error).
        """
        logger.error(f"Inpainting failed: {worker_error}")
        self._show_error_chip("Inpainting model error")
        QMessageBox.critical(
            self,
            "Couldn't load the inpainting model.",
            "Check that the model files exist in the `models/` folder and see"
            " the log for details.",
        )
        self.status_bar_left.setText("Inpainting failed")

    def _on_inpaint_cleanup(self, _args) -> None:
        """Reset the async-op flag + progress UI after the worker finishes."""
        self._op_running = False
        self.progress_bar.hide()
        self._refresh_action_states()

    def _on_show_original_toggled(self, show: bool) -> None:
        """View -> Show Original (P): toggle the before/after preview.

        ``show=True`` displays the pre-inpaint image (captured by
        ``EditorCanvas.set_image_from_numpy``); ``show=False`` returns to the
        inpainted result. Disabled (via :meth:`_refresh_action_states`) until
        an inpaint result exists.
        """
        self.canvas.show_original(show)

    # ------------------------------------------------- batch + export (plan 04)
    def _wire_batch_actions(self) -> None:
        """Wire the Esc -> Cancel Batch shortcut (D-09 Open Question Q1 -> A4).

        Esc is the conventional cancel affordance; it is safe because
        ``_cancel_batch`` is guarded by ``if self._batch_active`` and so is a
        no-op when no batch runs (T-02-09). Patterned after the QShortcut
        registrations in ``_wire_tool_actions`` / ``_wire_history_actions``
        (installed on the main window so it fires regardless of focus).
        """
        esc = QShortcut(QKeySequence("Esc"), self)
        esc.activated.connect(self._cancel_batch)
        self._refresh_action_states()

    def export_page(self) -> None:
        """File -> Export Page (Ctrl+E) — write the DISPLAYED canvas image.

        PROJ-02 / Pitfall 5: export writes whatever the canvas currently
        shows (a cleaned/inpainted result, an edited page, or the original),
        NOT a re-clean or re-detect. No model is called — the displayed
        pixels are read via ``canvas.get_image_numpy`` and written through
        Plan 01's ``save_image_optimized``.

        The save path comes from ``QFileDialog.getSaveFileName`` (the
        T-01-01 OS-validated-path sibling of ``open_image``'s
        ``getOpenFileName``; T-02-01 mitigation). The output format is chosen
        by the path suffix; the original page is passed so its mode/DPI are
        preserved (Plan 01 metadata-preservation contract).
        """
        if self._op_running:
            return
        current = self.file_table.current_path()
        if current is None:
            return
        image_rgb = self.canvas.get_image_numpy()
        if image_rgb is None:
            return

        # Build the filter from the source page's suffix so the default is
        # format-preserving (PNG page -> PNG export by default). Mirror the
        # open_image getOpenFileName filter family.
        suffix = current.suffix.lower()
        if suffix == ".png":
            filt = "PNG (*.png)"
        elif suffix in (".jpg", ".jpeg"):
            filt = "JPEG (*.jpg *.jpeg)"
        else:
            filt = "PNG (*.png);;JPEG (*.jpg *.jpeg)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Page", str(current.name), filt
        )
        if not path:
            return
        from manga_ai_studio.core.image_io import save_image_optimized

        save_image_optimized(image_rgb, Path(path), original=current)

    def batch_detect(self) -> None:
        """File -> Batch -> Batch Detect: dispatch ``batch_detect`` (FLOW-03)."""
        self._dispatch_batch("detect")

    def batch_clean(self) -> None:
        """File -> Batch -> Batch Clean: dispatch ``batch_clean`` (FLOW-03)."""
        self._dispatch_batch("clean")

    def batch_detect_and_clean(self) -> None:
        """File -> Batch -> Batch Detect + Clean: one-shot dispatch (FLOW-03)."""
        self._dispatch_batch("detect_and_clean")

    def _dispatch_batch(self, mode: str) -> None:
        """Dispatch a single batch Worker on the global QThreadPool (FLOW-03).

        Shared by the three public handlers to avoid triplication. Resolves
        the model paths + backends via the existing helpers (the CR-10/CR-11
        cache short-circuits prevent re-downloading the ~80MB/200MB models),
        derives the output dir (D-07: ``first.path.parent / "cleaned"``,
        double-guarded by batch_runner's name assert), builds a Worker on the
        Plan 03 entry point, connects the progress/result/error/aborted/
        finished handlers, sets the D-08 op-running + navigation-disable
        state, and starts the worker.

        T-02-05 mitigation (Open Question Q2 -> A5): the FileTable is
        ``setEnabled(False)`` at dispatch so ``on_page_selected`` cannot fire
        during the run (preventing the concurrent write/write race on
        ``ImageFile.mask``). The canvas stays visible (read-only viewing per
        D-08). ``_on_batch_cleanup`` re-enables navigation unconditionally.

        Pitfall 7: ``finished`` is ALWAYS connected to ``_on_batch_cleanup``
        (Worker.run's ``finally`` always emits ``finished``) so cleanup
        always runs even on abort/error. ``aborted`` also routes to the same
        cleanup handler, which is idempotent.
        """
        if self._op_running:
            return
        if not self.image_files:
            return

        # Bug D (checkpoint rework / D-02 "edits are sacred" + D-11 contract):
        # the only place the canvas mask is normally flushed to ImageFile.mask
        # is ``on_page_selected`` (the D-11 seam). Dispatching a batch from the
        # current page WITHOUT first navigating away skips that flush, so the
        # batch would read the STALE ImageFile.mask and silently ignore the
        # user's in-canvas mask edits (erase/refine). Flush the current page's
        # canvas mask into its ImageFile.mask here, BEFORE handing the pages to
        # the batch entry point — the exact operation on_page_selected step 1
        # performs, with the same MANDATORY .copy() (Pitfall 2). batch_detect
        # then overwrites it with the freshly-detected mask; batch_clean reads
        # the user's edited mask. This is the cross-plan integration fix.
        self._flush_current_canvas_mask_to_data_model()

        # Resolve model paths + backends. The cache short-circuits inside the
        # _resolve_* helpers mean a 30-page batch does not re-download.
        first = self.image_files[0]
        cleaned_dir = first.path.parent / "cleaned"  # D-07
        det_backend = self._detection_backend()
        inp_backend = self._inpainting_backend()

        # Pick the Plan 03 entry point + args by mode (D-05: three entry
        # points; models load ONCE inside each wrapper — Pitfall 3).
        from manga_ai_studio.core.batch_runner import (
            batch_clean,
            batch_detect,
            batch_detect_and_clean,
        )

        if mode == "detect":
            task_fn = batch_detect
            det_path = self._resolve_detection_model_path()
            args = (list(self.image_files), det_path, det_backend, cleaned_dir)
        elif mode == "clean":
            task_fn = batch_clean
            inp_path = self._resolve_inpainting_model_path()
            args = (list(self.image_files), inp_path, inp_backend, cleaned_dir)
        elif mode == "detect_and_clean":
            task_fn = batch_detect_and_clean
            det_path = self._resolve_detection_model_path()
            inp_path = self._resolve_inpainting_model_path()
            args = (
                list(self.image_files),
                det_path,
                inp_path,
                det_backend,
                inp_backend,
                cleaned_dir,
            )
        else:  # pragma: no cover - defensive; the three handlers are the only callers
            raise ValueError(f"unknown batch mode: {mode}")

        # abort_signal auto-injects abort_flag + connects to Worker.abort
        # (worker_thread.py:138-140). Emitting batch_abort_requested flips the
        # flag the loop checks at each page boundary (D-09 / Pitfall 4).
        worker = Worker(task_fn, *args, abort_signal=self.batch_abort_requested)
        worker.signals.progress.connect(self._on_batch_progress)
        worker.signals.result.connect(self._on_batch_finished)
        worker.signals.error.connect(self._on_batch_error)
        # ALWAYS connect finished to cleanup (Pitfall 7 — Worker.run's finally
        # always emits finished, so cleanup always runs). aborted also routes
        # to the idempotent cleanup so a cancel still clears the gate.
        worker.signals.aborted.connect(self._on_batch_cleanup)
        worker.signals.finished.connect(self._on_batch_cleanup)
        worker.setAutoDelete(True)

        # D-08: a batch blocks the editor. Disable navigation (T-02-05 race
        # mitigation) and set the op-running flags. The canvas stays visible.
        # Bug A: record the mode so _on_batch_progress can render the
        # mode-aware label; reset the cancel flag.
        self._op_running = True
        self._batch_active = True
        self._batch_mode = mode
        self._batch_cancelled = False
        self.file_table.setEnabled(False)
        self._refresh_action_states()
        self.error_chip.hide()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_bar_left.setText(f"{self._batch_verb()}\u2026 0%")
        QThreadPool.globalInstance().start(worker)

    def _flush_current_canvas_mask_to_data_model(self) -> None:
        """Flush the current page's canvas mask into its ``ImageFile.mask``.

        Bug D (checkpoint rework): mirrors ``on_page_selected`` step 1 — the
        D-11 seam normally only persists the OUTGOING page's mask on
        navigation, but a batch dispatches FROM the current page without
        navigating, so the seam never fires. This flush closes that gap so
        the user's in-canvas mask edits (brush/erase) reach the batch instead
        of being silently dropped in favor of the stale persisted mask
        (D-02 "edits are sacred" + the D-11 contract).

        No-op when no page is open or the canvas has no editable mask. Uses
        the same MANDATORY ``.copy()`` boundary detach as the seam
        (Pitfall 2 / T-02-04). When the canvas mask has been cleared to fully
        transparent (the user erased it) the stored QImage is replaced with
        ``None`` so ``has_mask_content()`` reports False and the D-03 gate
        passthroughs the page unchanged.
        """
        idx = self._current_page_index()
        if idx is None or not (0 <= idx < len(self.image_files)):
            return
        if not self.canvas.has_mask():
            # No editable mask QImage exists (fresh page, never detected) —
            # leave ImageFile.mask as-is.
            return
        canvas_mask = self.canvas.get_mask()
        if canvas_mask is None or canvas_mask.isNull():
            return
        # Pitfall 2: detach from the live canvas buffer. on_page_selected's
        # identical .copy() is the load-bearing boundary the regression test
        # test_mask_persistence_uses_copy locks; mirror it here verbatim.
        self.image_files[idx].mask = canvas_mask.copy()

    def _batch_verb(self) -> str:
        """Return the mode-aware status-bar verb (Bug A).

        ``detect`` -> "Detecting"; ``clean`` -> "Cleaning";
        ``detect_and_clean`` -> "Detecting+Cleaning" (the staged/combined
        label). Falls back to "Cleaning" if the mode is unknown/None so the
        status is never blank.
        """
        if self._batch_mode == "detect":
            return "Detecting"
        if self._batch_mode == "detect_and_clean":
            return "Detecting+Cleaning"
        return "Cleaning"

    def _on_batch_progress(self, payload) -> None:
        """Update the status bar + progress bar per page (D-10, Bug A).

        Mirrors ``_on_detection_progress``/``_on_inpaint_progress``: the Plan
        03 loop emits ``(percent, page_name)`` at the top of each page. Bug A:
        the status verb is mode-aware (``_batch_verb``) instead of the
        previously hardcoded "Cleaning".
        """
        if isinstance(payload, tuple) and len(payload) == 2:
            percent, name = payload
        else:
            return
        self.progress_bar.setValue(int(percent))
        self.status_bar_left.setText(
            f"{self._batch_verb()}\u2026 {int(percent)}% \u2014 {name}"
        )

    def _on_batch_finished(self, summary) -> None:
        """Show the batch summary in the status bar (D-04).

        Reads the Plan 03 summary dict ``{"ok", "failed", "total"}`` and
        renders the UI-SPEC copy: a clean run reads "Cleaned N/N pages"; a run
        with failures reads "Cleaned N/M pages — K failed, see log".
        """
        ok = summary.get("ok", 0) if isinstance(summary, dict) else 0
        total = summary.get("total", 0) if isinstance(summary, dict) else 0
        failed = summary.get("failed", []) if isinstance(summary, dict) else []
        if failed:
            self.status_bar_left.setText(
                f"Cleaned {ok}/{total} pages \u2014 {len(failed)} failed, see log"
            )
        else:
            self.status_bar_left.setText(f"Cleaned {ok}/{total} pages")
        self._refresh_action_states()

    def _on_batch_error(self, worker_error) -> None:
        """Log the batch failure + show the error chip (T-01-08 mirror).

        Mirrors ``_on_detection_error``/``_on_inpaint_error``: the full
        ``WorkerError`` (traceback included) goes to loguru; the status bar
        shows user-friendly copy. ``_on_batch_cleanup`` (connected to
        ``finished``, which always fires) handles re-enabling the editor.
        """
        logger.error(f"Batch failed: {worker_error}")
        self._show_error_chip("Batch error")
        self.status_bar_left.setText("Batch failed")

    def _on_batch_cleanup(self, _args) -> None:
        """Unconditionally clear the batch state + re-enable the editor.

        Pitfall 7 (T-02-06): connected to BOTH ``aborted`` and ``finished``
        (Worker.run's ``finally`` always emits ``finished``), so the editor is
        never stuck disabled. Idempotent — setting the flags False twice and
        re-enabling the file table twice are both harmless, so a run that
        aborts (aborted -> cleanup) then emits finished (-> cleanup again) is
        safe.

        Bug B (checkpoint rework): if the user cancelled the batch, render a
        "Cancelled — ..." status (reflecting any partial work) instead of
        leaving the stale per-page progress text ("Cleaning N%"/"Inpainting
        N%") on screen. On a cancel ``_on_batch_finished`` (result) does NOT
        fire (the Worker emits ``aborted``, not ``result``), so this cleanup
        is the only place to write the post-cancel status. The cancel flag is
        cleared after rendering so the second idempotent cleanup call (from
        ``finished``) does not re-stamp the text.
        """
        cancelled = self._batch_cancelled
        # Bug C (checkpoint rework): for a clean-containing batch, refresh the
        # currently-displayed page so the user sees the cleaned result + a
        # cleared mask overlay without manually re-navigating — the same
        # refresh single-page Inpaint performs in ``_on_inpaint_finished``.
        # Skip on cancel/error so we never overwrite an error/cancel status.
        if not cancelled:
            self._refresh_current_page_after_batch()

        self._op_running = False
        self._batch_active = False
        self._batch_mode = None
        self.file_table.setEnabled(True)  # T-02-05: re-enable navigation
        self.progress_bar.hide()
        self._refresh_action_states()

        if cancelled:
            self.status_bar_left.setText(self._batch_cancelled_status_text())
            self._batch_cancelled = False

    def _batch_cancelled_status_text(self) -> str:
        """Render the post-cancel status (Bug B).

        Reflects partial work when the summary recorded how many pages were
        finished before the abort; otherwise a plain "Cancelled". ``_op_running``
        is still True at the moment this is called from cleanup's body? No — it
        was just cleared; the count comes from the last _on_batch_finished if
        it ran (it does NOT run on cancel), so we keep this simple and
        report "Cancelled" (the summary text, if any, was from a prior run and
        is stale). The key contract is that the stale progress percent no
        longer shows.
        """
        return "Cancelled"

    def _refresh_current_page_after_batch(self) -> None:
        """Refresh the current page's canvas after a batch finishes (Bug C).

        After a clean-containing batch the currently-displayed page must show
        the cleaned result with its mask overlay cleared — the same refresh
        single-page Inpaint performs in ``_on_inpaint_finished``. The batch
        writes cleaned files to ``cleaned_dir`` (D-07); reload the current
        page from there if present, otherwise leave it. Then clear the mask
        overlay so the red overlay does not sit on the now-cleaned page
        (mirrors the CR-16 fix in ``_on_inpaint_finished``).

        Careful with the D-11 seam (Plan 02-02): the mask is part of the
        per-page data model. Clearing the canvas overlay here does NOT touch
        ``ImageFile.mask`` — the consumed mask stays persisted on the data
        model so re-navigation still shows/clears it consistently. We only
        update the live canvas display.
        """
        current = self.file_table.current_path()
        if current is None:
            return
        # Look for the cleaned output for the current page (cleaned_dir is
        # source.parent / "cleaned", D-07). If present, reload the canvas
        # image from it so the user sees the cleaned result.
        cleaned = current.parent / "cleaned" / current.name
        if cleaned.exists():
            self.canvas.set_image_from_path(cleaned)
        # Clear the consumed mask overlay on the canvas (CR-16 mirror: a red
        # overlay on top of the now-cleaned region looks wrong and would
        # cause a re-clean to re-process the cleaned area). Mutate the mask
        # internals directly (fill + update_mask_display) rather than calling
        # clear_mask(), which would emit mask_modified and push a spurious
        # mask-undo entry — the user's action was "batch clean", not "paint".
        canvas_mask = self.canvas.get_mask()
        if canvas_mask is not None and not canvas_mask.isNull():
            canvas_mask.fill(Qt.GlobalColor.transparent)
            self.canvas.update_mask_display()

    def _cancel_batch(self) -> None:
        """Emit the batch abort signal (D-09) and mark the run cancelled (Bug B).

        Guarded by ``if self._batch_active`` so Esc is a no-op when no batch
        runs (T-02-09). Emitting ``batch_abort_requested`` flips the running
        Worker's ``SharableFlag`` (worker_thread.py abort_signal wiring); the
        loop checks it at the next page boundary and raises ``Abort`` -> the
        worker emits ``aborted`` -> ``_on_batch_cleanup`` clears the gate and
        renders the "Cancelled" status. No page is half-written
        (Pitfall 4 / T-02-06).

        Bug B: set ``_batch_cancelled`` so ``_on_batch_cleanup`` renders a
        "Cancelled" status instead of leaving the stale per-page progress text.
        """
        if self._batch_active:
            self._batch_cancelled = True
            self.batch_abort_requested.emit()

    def _show_error_chip(self, text: str) -> None:
        """Show the persistent #7a1f1f error chip with ``text`` (UI-SPEC §Color)."""
        self.error_chip.setText(text)
        self.error_chip.show()


def compute_mask_bbox(mask_binary: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return ``(x, y, w, h)`` of the painted region, or None if empty.

    Used by :meth:`MainWindow._run_inpaint_task` to pass the inpaint bbox to
    ``EditorCanvas.set_image_from_numpy`` (which unpacks ``(x, y, w, h)`` and
    composites only that region so unchanged artwork stays pixel-exact).
    ``np.where`` over the ``(H, W)`` binary mask finds the painted region's
    extent; width/height are derived as (max - min + 1). Pure numpy — safe to
    call on the worker thread (T-01-07).

    CR-12 (UAT gap closure): ``np.where`` returns indices in ROW-MAJOR order
    (sorted by row, then col within each row), so ``xs[0]``/``xs[-1]`` are the
    columns of the first/last nonzero PIXEL, not the global min/max column. For
    any non-rectangular mask (e.g. an L-shaped stroke), that yielded a tiny
    wrongly-positioned bbox. Use ``min()``/``max()`` over the index arrays.
    """
    if mask_binary is None or mask_binary.size == 0:
        return None
    ys, xs = np.where(mask_binary > 0)
    if ys.size == 0:
        return None
    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    return x1, y1, x2 - x1 + 1, y2 - y1 + 1

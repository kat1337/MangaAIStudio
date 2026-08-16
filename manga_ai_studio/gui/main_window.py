"""MainWindow — the application controller.

Architecture adapted from PanelCleaner ``mainwindow_driver.py`` (GPL v3,
vendored-shape per D-12): the constructor receives a ``ProfileManager``,
builds a central ``EditorCanvas``, and wires the menu bar / actions. Plan 01
shipped the File -> Open Image + View -> Fit to Window (Ctrl+0)
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

import copy
import math
from dataclasses import replace as dreplace
from functools import partial
from io import BytesIO
from pathlib import Path

import numpy as np
from loguru import logger
from natsort import natsorted
from PIL import Image
from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolBar,
    QToolButton,
)

from manga_ai_studio.adapters.factory import backend_factory
from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core import image_ops, project_io
from manga_ai_studio.core.box_model import (
    DETECTED,
    USER,
    PageBox,
    textblock_to_box,
)
from manga_ai_studio.core.history_manager import HistoryManager
from manga_ai_studio.core.image_file import ImageFile
from manga_ai_studio.core.mask_editor import (
    DEFAULT_BRUSH_SIZE,
    ToolMode,
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.core.text_style import TextStyle, default_style
from manga_ai_studio.gui.canvas import EditorCanvas, validate_image_path
from panelcleaner.structures import Box
from manga_ai_studio.gui.file_table import FileTable
from manga_ai_studio.gui.inspector_panel import InspectorPanel
from manga_ai_studio.gui.load_translations_dialog import LoadTranslationsDialog
from manga_ai_studio.gui.text_renderer import (
    current_focus_text,
    layout as renderer_layout,
)
from manga_ai_studio.gui.tools_panel import ToolsPanel
from manga_ai_studio.gui.worker_thread import Worker

# Maximum number of entries kept in the Recent Files submenu (UI-SPEC surface 1).
MAX_RECENT_FILES = 8
# Maximum number of entries kept in the Recent Projects submenu (D-07, plan
# 05-05 — mirrors Recent Files, UI-SPEC surface 21).
MAX_RECENT_PROJECTS = 8
# (bold, italic) flags per QFontDatabase style-name display string (D-05 —
# the Inspector Style-combo commits map the display name to the model flags).
_FONT_STYLE_FLAGS = {
    "Regular": (False, False),
    "Italic": (False, True),
    "Bold": (True, False),
    "Bold Italic": (True, True),
}
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
        # D-01 auto-OCR hook (plan 06): a user box created on Alt+drag
        # draw-release emits canvas.ocr_requested; MainWindow dispatches the
        # OCR worker. Connected right after construction (the canvas's
        # class-scope signal exists before any event can fire).
        self.canvas.ocr_requested.connect(self._on_canvas_ocr_requested)
        # G-07-3: new user-drawn boxes are born with the saved default
        # family. The provider returns None when no family is saved — a
        # no-key box keeps style None and the renderer's TextStyle() defaults
        # apply (matching today's behavior, so the existing box tests pass
        # UNCHANGED). D-06: existing boxes are never re-styled by this.
        self.canvas.new_box_style_provider = (
            lambda: default_style(self._default_font_family())
            if self._default_font_family()
            else None
        )

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
        # Plan 05-08: the page count of the running OCR-JSON batch — the
        # progress handler derives {done}/{total} from the worker's
        # (percent, name) emissions (batch_export_ocr emits per-page percent,
        # not a done count). 0 while no OCR batch runs.
        self._batch_ocr_total = 0

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

        # Plan 05-05 (PROJ-01 / D-07): the open project's ``<chapter>.mas-
        # project`` folder + manifest name, or None for an unsaved session.
        # ``_project_dir`` routes the first Save Project… into the Save As…
        # flow and drives the D-07 window-title format
        # ("Manga AI Studio — {project-name} — {page}*"); ``_project_name``
        # is the manifest ``name`` (the chapter/session name from
        # project_io.save_project).
        self._project_dir: Path | None = None
        self._project_name: str | None = None

        # Inpaint history hook (plan 06 wires the real HistoryManager here;
        # _on_inpaint_finished activates the push_image_action call site).
        self.history = HistoryManager(limit=20)

        # CR-01 / WR-05 (plan 03-05 fix): suppression guard for the BOXES push
        # hook. The box restore path (apply_undo_boxes) rebuilds the layer via
        # set_boxes, which emits boxes_modified — WITHOUT this guard, wiring
        # boxes_modified -> _on_boxes_modified would make every undo/redo
        # restore re-push the restored state and clear redo (timeline
        # corruption, the box analogue of mask's test_undo_does_not_repush).
        # Mirrors how the mask side avoids the trap: mask's restore path
        # (apply_undo_mask) does not emit at all, but set_boxes ALWAYS emits,
        # so the box side needs an explicit guard. Set True around restore /
        # detection set_boxes calls that push themselves explicitly.
        self._suppress_boxes_push = False

        # Plan 05-04 (PROJ-04 / UI-SPEC surface 28): the geometry-op apply
        # path (plan 05-06/05-07 `_apply_geometry_op`) records the op name
        # here via `_record_geometry_op_name` right before pushing its ONE
        # geometry undo entry. When the unified undo/redo pops a multi-kind
        # geometry record, the transient flashes "Undo: {op_name}" /
        # "Redo: {op_name}" (rotate|crop|curves|resize — the extended op-name
        # set). None = no geometry op pushed yet on this page.
        self._last_geometry_op_name: str | None = None

        # Plan 07-02 (D-09): the last GROUP-op name ("Moved {n} boxes" /
        # "Deleted {n} boxes") recorded at push time (consumed from
        # ``canvas.take_pending_boxes_op_name()`` in ``_on_boxes_modified``) so
        # the Ctrl+Z flash names the group op instead of the generic "box edit"
        # (the 06-WR-01 recorded-op-name pattern, scoped to the BOXES stack).
        # None = the last boxes push was an ordinary single-box op.
        self._last_boxes_op_name: str | None = None

        # Plan 03-08 (FLOW-02 regression / UAT test 3 addendum): per-page
        # before-state snapshot for the mask push hook. The mask side
        # historically pushed ONLY the after-state (``canvas.get_mask()`` post-
        # stroke) with no before-state, so undo returned the after-state itself
        # — a no-op that left the stroke on the canvas and, after an inpaint
        # interleaving, made the brush appear "stuck" on the 2nd Ctrl+Z. This
        # mirrors the IMAGE side's pre-edit push contract (``push_image_action``
        # "records the PRE-edit region so undo restores it") and plan 03-07's
        # BOXES before-state discipline: each mask stroke now pushes the mask
        # state as it was BEFORE the stroke began (= the after-state of the
        # previous stroke, or a clean baseline for the first stroke of the
        # session). ``_on_mask_modified`` fires AFTER the stroke is painted, so
        # the before-state is reconstructed as "the previous stroke's after-
        # state", tracked here and refreshed after each push. reset_history
        # clears it (fresh per page). None = "no prior stroke; the next stroke
        # seeds the clean baseline as its before-state".
        self._pre_stroke_mask: QImage | None = None

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

        # Inspector dock -> InspectorPanel (plan 04-04 Task 2, D-08). Tabbed
        # with the Tools dock (UI-SPEC §18) so the two right-side docks share the
        # right edge; the user toggles between them via the dock tab or drags to
        # undock. The Inspector becomes active when a box is selected (the
        # selection-follower below drives load_box on selection change).
        self.dock_inspector = QDockWidget("Inspector", self)
        self.dock_inspector.setObjectName("dock_inspector")
        self.dock_inspector.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.inspector_panel = InspectorPanel()
        self.dock_inspector.setWidget(self.inspector_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_inspector)
        self.tabifyDockWidget(self.dock_tools, self.dock_inspector)

    # ---------------------------------------------------------------- menus
    def _build_menus(self) -> None:
        """Build the full menu bar (UI-SPEC surface 1)."""
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_text_menu()
        self._build_tools_menu()
        self._build_help_menu()

    def _build_file_menu(self) -> None:
        # Open Image (plan 01, kept). NOTE (Pitfall 8 / D-07): the Ctrl+O
        # shortcut is REMOVED — Open Project… takes Ctrl+O; Qt would fire both
        # actions if Open Image kept the binding (UI-SPEC §Keyboard).
        self.action_open_image = QAction("Open Image\u2026", self)
        self.action_open_image.triggered.connect(self.open_image)

        # Open Folder (plan 02).
        self.action_open_folder = QAction("Open Folder\u2026", self)
        self.action_open_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.action_open_folder.triggered.connect(self.open_folder)

        # Open Project (plan 05, D-07): opens a chapter manifest OR a page
        # .mas (the D-09 climb, UI-SPEC surface 21/22). Ctrl+O per D-07.
        self.action_open_project = QAction("Open Project\u2026", self)
        self.action_open_project.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open_project.setToolTip(
            "Open a saved project (manifest.json or a page .mas file)."
        )
        # Wiring audit (G-05-1, plan 05-10): QAction.triggered ALWAYS emits
        # the checked bool as its first argument, so a parameterized slot
        # would misread it (the pre-fix connect crashed _open_project with
        # AttributeError at selected.name). The zero-arg lambda lets PySide6
        # drop the bool — the established in-file pattern (tool actions
        # 696-735, rotate actions 758-774). Audit of EVERY remaining
        # triggered.connect target: all are zero-arg methods, zero-arg
        # lambdas, or signal-to-signal (toggleViewAction().trigger at
        # 543/546); canvas.zoom_in/zoom_out accept wheel: bool = False and
        # are benign because triggered emits False == the default. Do NOT
        # add a _checked param to _open_project — the D-09 recent-opener
        # closures (2414) already absorb it.
        self.action_open_project.triggered.connect(lambda: self._open_project())
        self.action_open_project.setEnabled(False)

        # Recent Projects submenu (D-07, max 8 via QSettings). Mirrors the
        # Recent Files machinery exactly (standalone QMenu child of the
        # window — never the menubar factory — so its menuAction never lands
        # in the top-level action list). Structure wired in plan 05-05
        # Task 3; the submenu exists from the File-menu build.
        self.recent_projects_menu = QMenu("Recent Projects", self)
        self.action_clear_recent_projects = QAction("Clear Menu", self)
        self.action_clear_recent_projects.triggered.connect(
            self._clear_recent_projects
        )
        self._refresh_recent_projects_menu()

        # Save Project (D-07): writes the session as a <chapter>.mas-project/
        # folder. Disabled until a page is open (refreshed in
        # _refresh_action_states). Ctrl+S.
        self.action_save_project = QAction("Save Project\u2026", self)
        self.action_save_project.setShortcut(QKeySequence("Ctrl+S"))
        self.action_save_project.setToolTip(
            "Save the full page state (images, masks, boxes, text,"
            " translations) as a project (Ctrl+S)."
        )
        # Zero-arg lambda (G-05-1, plan 05-10): the triggered checked-bool
        # would otherwise land in _save_project's force_as param. Benign
        # today (emitted False == the default) but identical to the crash
        # class fixed at line 315 — closed the same way.
        self.action_save_project.triggered.connect(lambda: self._save_project())
        self.action_save_project.setEnabled(False)

        # Save Project As (D-07): choose the project folder first. Ctrl+Shift+S.
        self.action_save_project_as = QAction("Save Project As\u2026", self)
        self.action_save_project_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_project_as.triggered.connect(self._save_project_as)
        self.action_save_project_as.setEnabled(False)

        # Recent Files submenu (max 8 via QSettings). Created as a standalone
        # child of the window (never through the menu bar factory) so its
        # menuAction never lands in the menubar's top-level action list — the
        # File-menu addMenu below is the only home.
        self.recent_menu = QMenu("Recent Files", self)
        self.action_clear_recent = QAction("Clear Menu", self)
        self.action_clear_recent.triggered.connect(self._clear_recent_files)
        self._refresh_recent_menu()

        # Quit (Ctrl+Q).
        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_quit.triggered.connect(self._on_quit)

        # Export Page (Ctrl+E) — plan 04 (PROJ-02): writes the DISPLAYED canvas
        # image (not a re-clean) to a user-chosen PNG/JPG path via
        # QFileDialog.getSaveFileName. The T-01-01 OS-validated-path sibling of
        # open_image's getOpenFileName (T-02-01 mitigation).
        self.action_export_page = QAction("Export Page\u2026", self)
        self.action_export_page.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_page.triggered.connect(self.export_page)
        self.action_export_page.setEnabled(False)

        # Export Typeset… (Ctrl+Shift+B) — plan 07-01 (D-01/D-02): bakes the
        # typeset text (per-box current-focus content + flat TextStyle through
        # the SHARED renderer) into a copy of the current page image, written
        # via the PROJ-02 writer (save_image_optimized) to the D-03 sidecar.
        # The File-menu Export section sibling of Export Page (Export OCR JSON
        # lives in the Text menu); shortcut audit: Ctrl+E / Ctrl+Shift+E are
        # taken, Ctrl+Shift+B is free (UI-SPEC surface 35, Pitfall 4).
        self.action_export_typeset = QAction("Export Typeset\u2026", self)
        self.action_export_typeset.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self.action_export_typeset.setStatusTip(
            "Bake the typeset text into a copy of the page image (Ctrl+Shift+B)."
        )
        self.action_export_typeset.triggered.connect(self._on_export_typeset)
        self.action_export_typeset.setEnabled(False)

        # Batch submenu (FLOW-03 / D-01): the three batch actions operate on the
        # currently-open folder (D-06). All three dispatch the Plan 03 entry
        # points on a single Worker(QRunnable). Disabled until a folder is open
        # AND no async op is running (refreshed in _refresh_action_states).
        # Created as a standalone child of the window (never through the menu
        # bar factory) — a File submenu only; the three batch actions +
        # enablement are unchanged.
        self.batch_menu = QMenu("Batch", self)
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

        # Batch Export OCR JSON (D-21, plan 05-08): PROJ-03 batch export of
        # every open page's D-19 _ocr.json (fast, model-free). No ellipsis —
        # starts immediately, mirroring the three cleaning batch actions
        # (UI-SPEC §Copywriting). Per-page D-22 placement + the Phase 2 batch
        # progress surface (status-left + determinate bar + Cancel Batch).
        self.action_batch_export_ocr = QAction("Batch Export OCR JSON", self)
        self.action_batch_export_ocr.setStatusTip(
            "Export every page of the open folder as _ocr.json (fast, no"
            " models)."
        )
        self.action_batch_export_ocr.triggered.connect(
            self._dispatch_batch_ocr_export
        )
        # Enabled iff a folder is open AND no op is running AND no batch is
        # already running (refreshed in _refresh_action_states).
        self.action_batch_export_ocr.setEnabled(False)
        self.batch_menu.addAction(self.action_batch_export_ocr)

        # UI-SPEC surface 21 (executor-authoritative order): Open Image… /
        # Open Folder… / ─ / Open Project… / Recent Projects ▸ / Recent
        # Files ▸ / ─ / Save Project… / Save Project As… / ─ / Export
        # Page… / Batch ▸ / ─ / Quit.
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_open_image)
        file_menu.addAction(self.action_open_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.action_open_project)
        file_menu.addMenu(self.recent_projects_menu)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.action_save_project)
        file_menu.addAction(self.action_save_project_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export_page)
        file_menu.addAction(self.action_export_typeset)
        file_menu.addMenu(self.batch_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

    def _build_edit_menu(self) -> None:
        # Surface 13 (plan 03-05): the 4 Phase-1 undo/redo actions collapse to
        # 2 unified ones. Ctrl+Z pops the merged MASK/IMAGE/BOXES timeline
        # (plan 03-02's HistoryManager.undo); Ctrl+Shift+Z redoes. The Phase 1
        # mask-undo actions + items (the legacy Alt-modifier Z pair) are REMOVED
        # (subsumed by the unified Ctrl+Z).
        # Shortcuts are installed as QShortcut in _wire_history_actions so they
        # fire regardless of focus (MangaCleaner_GPU main_window.py:168-171
        # pattern, reimplemented). NOTE: setShortcut is intentionally NOT called
        # here — the focus-robust QShortcut registrations are the single source
        # for these key sequences. A duplicate setShortcut here would trigger
        # Qt's "Ambiguous shortcut overload" warning (CR-14).
        self.action_undo = QAction("Undo", self)
        self.action_undo.setEnabled(False)

        self.action_redo = QAction("Redo", self)
        self.action_redo.setEnabled(False)

        # Select All Boxes (D-08, plan 07-02): Ctrl+A selects every box on the
        # page (the multi-select foundation the Inspector bulk-styling section
        # consumes, plan 07-05). Shortcut verified free in the Phase 1-6 map
        # (UI-SPEC conflict audit, T-07-05); single binding per sequence (the
        # CR-14 discipline). Enabled iff a page is open AND >= 1 box exists AND
        # no async op is running (mirrors action_ocr_all's :1097-1099 shape) —
        # refreshed in _refresh_action_states.
        self.action_select_all_boxes = QAction("Select All Boxes", self)
        self.action_select_all_boxes.setShortcut(QKeySequence("Ctrl+A"))
        # G-05-1 (plan 05-10): the zero-arg lambda — QAction.triggered ALWAYS
        # emits the action's checked state as its first arg, so partials with
        # `checked` would make the call signature mismatch when the action is
        # unchecked.
        self.action_select_all_boxes.triggered.connect(
            lambda: self.canvas.select_all_boxes()
        )
        self.action_select_all_boxes.setEnabled(False)

        self.action_clear_mask = QAction("Clear Mask\u2026", self)
        self.action_clear_mask.setEnabled(False)  # plan 04

        # Crop… (D-11, plan 05-07): the numeric crop dialog (UI-SPEC surface
        # 24b). No shortcut — the canvas Crop tool is the gesture path; the
        # dialog is the precision path (menu-accelerable). Dialog-opening
        # ellipsis per §Copywriting.
        self.action_crop_dialog = QAction("Crop\u2026", self)
        self.action_crop_dialog.setToolTip(
            "Crop the page by exact coordinates (x, y, width, height)."
        )
        self.action_crop_dialog.triggered.connect(self._on_crop_dialog)
        self.action_crop_dialog.setEnabled(False)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_select_all_boxes)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_crop_dialog)
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

        # Toggle Box Overlay (Shift+M) — plan 03-04 D-02 layer toggle. Sibling
        # of Toggle Mask Overlay, placed immediately after it in the View menu
        # (UI-SPEC §11). Checkable; checked state mirrors the box layer
        # visibility (box_layer.isVisible()). Enabled iff a page is open
        # (refreshed in _refresh_action_states). Shortcut Shift+M — M is taken
        # by the mask overlay; Shift+M is the mnemonic "the other overlay" and
        # conflicts with nothing (UI-SPEC shortcut audit).
        self.action_toggle_box_overlay = QAction("Toggle Box Overlay", self)
        self.action_toggle_box_overlay.setShortcut(QKeySequence("Shift+M"))
        self.action_toggle_box_overlay.setCheckable(True)
        self.action_toggle_box_overlay.setChecked(True)  # layer defaults visible
        self.action_toggle_box_overlay.setStatusTip(
            "Show or hide the text-box layer (Shift+M). Hidden boxes are not"
            " interactable."
        )
        self.action_toggle_box_overlay.toggled.connect(
            self._on_toggle_box_overlay_toggled
        )
        self.action_toggle_box_overlay.setEnabled(False)

        # Toggle Text Overlay (T) — plan 04-04 D-12 third visibility layer.
        # Sibling of Toggle Mask Overlay (M) and Toggle Box Overlay (Shift+M);
        # the three overlays are independent. Checkable, default checked (D-09:
        # boxes become display objects, text renders by default). Shortcut T is
        # free (UI-SPEC §19 shortcut audit: M/Shift+M/B/R/L/E/V/D/C/P all taken,
        # T unused) — placed immediately after Toggle Box Overlay (UI-SPEC §19).
        self.action_toggle_text_overlay = QAction("Toggle Text Overlay", self)
        self.action_toggle_text_overlay.setShortcut(QKeySequence("T"))
        self.action_toggle_text_overlay.setCheckable(True)
        self.action_toggle_text_overlay.setChecked(True)  # text renders by default
        self.action_toggle_text_overlay.setStatusTip(
            "Show or hide the recognized/translation text on the canvas (T)."
            " Independent of mask (M) and box (Shift+M) overlays."
        )
        self.action_toggle_text_overlay.toggled.connect(
            self._on_toggle_text_overlay_toggled
        )
        self.action_toggle_text_overlay.setEnabled(False)

        # Show Original (P) — wired in plan 05 (sticky before/after preview,
        # UI-SPEC surface 7). Checkable: toggling calls canvas.show_original.
        self.action_show_original = QAction("Show Original", self)
        self.action_show_original.setShortcut(QKeySequence("P"))
        self.action_show_original.setCheckable(True)
        self.action_show_original.toggled.connect(self._on_show_original_toggled)
        self.action_show_original.setEnabled(False)

        # Toggle Sidebar / Tools / Inspector (the docks).
        self.action_toggle_sidebar = QAction("Toggle Sidebar", self)
        self.action_toggle_sidebar.triggered.connect(self.dock_pages.toggleViewAction().trigger)

        self.action_toggle_tools = QAction("Toggle Tools", self)
        self.action_toggle_tools.triggered.connect(self.dock_tools.toggleViewAction().trigger)

        self.action_toggle_inspector = QAction("Toggle Inspector", self)
        self.action_toggle_inspector.triggered.connect(
            self.dock_inspector.toggleViewAction().trigger
        )

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.action_fit_to_window)
        view_menu.addAction(self.action_actual_size)
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_mask_overlay)
        view_menu.addAction(self.action_toggle_box_overlay)
        view_menu.addAction(self.action_toggle_text_overlay)
        view_menu.addAction(self.action_show_original)
        view_menu.addSeparator()
        view_menu.addAction(self.action_toggle_sidebar)
        view_menu.addAction(self.action_toggle_tools)
        view_menu.addAction(self.action_toggle_inspector)

    def _build_text_menu(self) -> None:
        """Build the Text menu (UI-SPEC §Surface 1 — between View and Tools).

        Plan 06 ships Run OCR + OCR All Boxes (Ctrl+R). Plan 07 adds the
        Auto-Number submenu + Load Translations to this menu (the order
        File/Edit/View/Text/Tools/Help groups the text/OCR actions).
        """
        # Run OCR (D-01): recognize text in the single selected box.
        self.action_run_ocr = QAction("Run OCR", self)
        self.action_run_ocr.setStatusTip(
            "Recognize text in the selected box with manga-ocr."
        )
        self.action_run_ocr.triggered.connect(self.run_ocr_selected)
        # Enabled iff exactly one box is selected AND no async op is running
        # (refreshed in _refresh_action_states).
        self.action_run_ocr.setEnabled(False)

        # OCR All Boxes (D-03): fill every text-empty box on the page (Ctrl+R).
        self.action_ocr_all = QAction("OCR All Boxes", self)
        self.action_ocr_all.setShortcut(QKeySequence("Ctrl+R"))
        self.action_ocr_all.setStatusTip(
            "Recognize text in every text box on this page (Ctrl+R). Boxes"
            " you've already edited are kept unless you confirm."
        )
        self.action_ocr_all.triggered.connect(self.run_ocr_all)
        # Enabled iff >= 1 box exists on the page AND no async op is running
        # (refreshed in _refresh_action_states).
        self.action_ocr_all.setEnabled(False)

        text_menu = self.menuBar().addMenu("&Text")

        # Auto-Number submenu (D-15/D-16): assign page-global bubble numbers
        # 1..N in reading order via reading_order.assign_bubble_numbers (the
        # Plan 02 XY-Cut algorithm — no algorithm logic here).
        self.auto_number_menu = text_menu.addMenu("Auto-Number")
        self.action_auto_number_rtl = QAction("RTL (Manga)", self)
        self.action_auto_number_rtl.setStatusTip(
            "Number all boxes 1..N in right-to-left, top-to-bottom reading"
            " order (manga default)."
        )
        self.action_auto_number_rtl.triggered.connect(self._auto_number_rtl)
        self.action_auto_number_ltr = QAction("LTR (Manhwa)", self)
        self.action_auto_number_ltr.setStatusTip(
            "Number all boxes 1..N in left-to-right, top-to-bottom reading"
            " order (manhwa)."
        )
        self.action_auto_number_ltr.triggered.connect(self._auto_number_ltr)
        # Enabled iff >= 1 box exists AND no async op is running (refreshed in
        # _refresh_action_states — mirrors action_ocr_all gating).
        self.action_auto_number_rtl.setEnabled(False)
        self.action_auto_number_ltr.setEnabled(False)
        self.auto_number_menu.addAction(self.action_auto_number_rtl)
        self.auto_number_menu.addAction(self.action_auto_number_ltr)

        # Load Translations (D-17): paste/import a typesetting-tool-format
        # translation list and match it to bubble numbers.
        self.action_load_translations = QAction("Load Translations\u2026", self)
        self.action_load_translations.setStatusTip(
            "Paste or import a typesetting-tool-format translation list and"
            " match it to bubble numbers."
        )
        self.action_load_translations.triggered.connect(self._open_load_translations)
        # Enabled iff a page is open AND no async op is running (refreshed in
        # _refresh_action_states).
        self.action_load_translations.setEnabled(False)

        # Typesetting section (D-16, plan 07-05): Increase/Decrease Font Size
        # (Ctrl+] / Ctrl+[ — the UI-SPEC-locked bracket pair; Ctrl+- is taken
        # by zoom-out, Pitfall 4). Enabled iff >= 1 box selected AND no async
        # op is running (refreshed in _refresh_action_states). Zero-arg-lambda
        # triggered wiring (G-05-1).
        self.action_increase_font_size = QAction("Increase Font Size", self)
        self.action_increase_font_size.setShortcut(QKeySequence("Ctrl+]"))
        self.action_increase_font_size.setToolTip(
            "Increase the font size of the selected box(es) by 1 px (Ctrl+])."
        )
        self.action_increase_font_size.triggered.connect(
            lambda: self._on_font_size_delta(1)
        )
        self.action_increase_font_size.setEnabled(False)

        self.action_decrease_font_size = QAction("Decrease Font Size", self)
        self.action_decrease_font_size.setShortcut(QKeySequence("Ctrl+["))
        self.action_decrease_font_size.setToolTip(
            "Decrease the font size of the selected box(es) by 1 px (Ctrl+[)."
        )
        self.action_decrease_font_size.triggered.connect(
            lambda: self._on_font_size_delta(-1)
        )
        self.action_decrease_font_size.setEnabled(False)

        # Export OCR JSON (D-21, plan 05-08): PROJ-03 single-page export of
        # the CURRENT page's D-19 _ocr.json via a Save As dialog (UI-SPEC
        # surface 27). Shortcut: the Shift-modified E sequence — plain Ctrl+E
        # is Export Page; the Shift-modified one is distinct (UI-SPEC
        # §Keyboard Shortcut Reference). Default target follows D-22
        # (pristine -> sidecar beside the source; geometry-altered ->
        # cleaned/).
        self.action_export_ocr_json = QAction("Export OCR JSON\u2026", self)
        self.action_export_ocr_json.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.action_export_ocr_json.setStatusTip(
            "Export the current page's boxes and text as a mokuro-style"
            " _ocr.json for downstream typesetting tools."
        )
        self.action_export_ocr_json.triggered.connect(self._export_ocr_json)
        # Enabled iff a page is open AND no async op is running (refreshed in
        # _refresh_action_states).
        self.action_export_ocr_json.setEnabled(False)

        text_menu.addAction(self.action_run_ocr)
        text_menu.addAction(self.action_ocr_all)
        text_menu.addSeparator()
        text_menu.addMenu(self.auto_number_menu)
        text_menu.addSeparator()
        text_menu.addAction(self.action_load_translations)
        # Typesetting section (D-16) after Load Translations… (UI-SPEC §1).
        text_menu.addSeparator()
        text_menu.addAction(self.action_increase_font_size)
        text_menu.addAction(self.action_decrease_font_size)
        text_menu.addSeparator()
        text_menu.addAction(self.action_export_ocr_json)

    def _build_tools_menu(self) -> None:
        # Detect Text (D) — wired in plan 03 (async CTD detection).
        self.action_detect_text = QAction("Detect Text", self)
        self.action_detect_text.setShortcut(QKeySequence("D"))
        self.action_detect_text.triggered.connect(self.detect_text)
        # Enabled iff a page is open and no async op is running.
        self.action_detect_text.setEnabled(False)

        # Detect Boxes (D-01 mode toggle, plan 03-04). Checkable, default
        # checked (UI-SPEC §Copywriting A1). When on, Detect Text also creates
        # editable text boxes from the model's blk_list (in addition to the
        # mask); when off, Phase 1 behaviour is preserved (mask only). There is
        # NO second model pass — the toggle only gates whether _on_detection_
        # finished surfaces the already-returned blk_list (UI-SPEC surface 10).
        self.action_detect_boxes_mode = QAction("Detect Boxes", self)
        self.action_detect_boxes_mode.setCheckable(True)
        self.action_detect_boxes_mode.setChecked(True)  # default on (UI-SPEC A1)
        self.action_detect_boxes_mode.setStatusTip(
            "When on, Detect Text also creates editable text boxes (in addition"
            " to the mask). Turn off for mask-only behaviour."
        )

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
        # D-10 (WR-02): the actions are CHECKABLE but STANDALONE — deliberately
        # outside the ToolsPanel's exclusive QActionGroup (a 12-action
        # mirrored group fought itself on dock clicks). set_active_tool's
        # action-sync loop drives their checked state explicitly, and the
        # toolbar buttons mirror their default actions, so the toolbar stays
        # in sync with the dock.
        self.action_tool_move = QAction("Move/Pan", self)
        self.action_tool_move.setCheckable(True)
        self.action_tool_move.setData(ToolMode.MOVE)
        self.action_tool_move.triggered.connect(lambda: self.set_active_tool(ToolMode.MOVE))

        self.action_tool_brush = QAction("Brush", self)
        self.action_tool_brush.setCheckable(True)
        self.action_tool_brush.setData(ToolMode.BRUSH)
        self.action_tool_brush.triggered.connect(
            lambda: self.set_active_tool(ToolMode.BRUSH)
        )

        self.action_tool_rectangle = QAction("Rectangle", self)
        self.action_tool_rectangle.setCheckable(True)
        self.action_tool_rectangle.setData(ToolMode.RECTANGLE)
        self.action_tool_rectangle.triggered.connect(
            lambda: self.set_active_tool(ToolMode.RECTANGLE)
        )

        self.action_tool_lasso = QAction("Lasso", self)
        self.action_tool_lasso.setCheckable(True)
        self.action_tool_lasso.setData(ToolMode.LASSO)
        self.action_tool_lasso.triggered.connect(
            lambda: self.set_active_tool(ToolMode.LASSO)
        )

        self.action_tool_eraser = QAction("Eraser", self)
        self.action_tool_eraser.setCheckable(True)
        self.action_tool_eraser.setData(ToolMode.ERASER)
        self.action_tool_eraser.triggered.connect(
            lambda: self.set_active_tool(ToolMode.ERASER)
        )

        # The 6th tool (D-11, plan 05-07): Crop — same wiring as the other
        # tool actions (setData(ToolMode) + set_active_tool via lambda; the
        # toolbar button mirrors this standalone checkable action, and
        # set_active_tool's sync loop keeps the dock and toolbar in sync —
        # WR-02: the window actions are NOT members of the panel's exclusive
        # group). Tooltip per UI-SPEC §Copywriting crop tool row; shortcut G
        # is installed as a window-level QShortcut in _wire_tool_actions (the
        # established pattern — an action-level setShortcut would collide
        # with it, CR-14).
        self.action_tool_crop = QAction("Crop", self)
        self.action_tool_crop.setCheckable(True)
        self.action_tool_crop.setData(ToolMode.CROP)
        self.action_tool_crop.setToolTip(
            "Crop tool (G): drag a rectangle on the page, Enter applies,"
            " Esc cancels."
        )
        self.action_tool_crop.triggered.connect(
            lambda: self.set_active_tool(ToolMode.CROP)
        )

        # Cancel Batch (D-09) — plan 04: emits batch_abort_requested, which the
        # running Worker.abort consumes (worker_thread.py abort_signal wiring).
        # Disabled unless a batch is running (refreshed in _refresh_action_states).
        # Esc is the keyboard affordance (wired in _wire_batch_actions).
        self.action_cancel_batch = QAction("Cancel Batch", self)
        self.action_cancel_batch.triggered.connect(self._cancel_batch)
        self.action_cancel_batch.setEnabled(False)

        # Image section (plan 05-06/06-05, UI-SPEC surfaces 23/25/26/30):
        # Rotate ▸ (90° CW / 90° CCW / 180°), Curves…, Resize…. Rotate applies
        # SILENTLY (D-14 — no confirmation); Curves/Resize open dialogs.
        # All three are synchronous and enabled iff a page is open AND no
        # async op is running (gated in _refresh_action_states). No shortcuts
        # (menu-accelerable per UI-SPEC §Accessibility).
        self.action_rotate_cw = QAction("Rotate 90\u00b0 CW", self)
        self.action_rotate_cw.setToolTip(
            "Rotate the page 90\u00b0 clockwise. Masks and text boxes rotate"
            " with it. Undo via Ctrl+Z."
        )
        self.action_rotate_cw.triggered.connect(lambda: self._rotate_page(-1))
        self.action_rotate_cw.setEnabled(False)

        self.action_rotate_ccw = QAction("Rotate 90\u00b0 CCW", self)
        self.action_rotate_ccw.setToolTip(
            "Rotate the page 90\u00b0 counter-clockwise. Masks and text boxes"
            " rotate with it. Undo via Ctrl+Z."
        )
        self.action_rotate_ccw.triggered.connect(lambda: self._rotate_page(1))
        self.action_rotate_ccw.setEnabled(False)

        self.action_rotate_180 = QAction("Rotate 180\u00b0", self)
        self.action_rotate_180.setToolTip(
            "Rotate the page 180\u00b0. Masks and text boxes rotate with it."
            " Undo via Ctrl+Z."
        )
        self.action_rotate_180.triggered.connect(lambda: self._rotate_page(2))
        self.action_rotate_180.setEnabled(False)

        self.action_curves = QAction("Curves\u2026", self)
        self.action_curves.setToolTip(
            "Adjust tones with a draggable curve — presets, per-channel"
            " curves, and black/white/gamma quick controls, with live preview."
        )
        self.action_curves.triggered.connect(self._on_curves)
        self.action_curves.setEnabled(False)

        self.action_resize = QAction("Resize\u2026", self)
        self.action_resize.setToolTip(
            "Resize the page with an aspect-ratio lock. Masks and text boxes"
            " scale with it."
        )
        self.action_resize.triggered.connect(self._on_resize)
        self.action_resize.setEnabled(False)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.action_detect_text)
        tools_menu.addAction(self.action_detect_boxes_mode)
        tools_menu.addAction(self.action_inpaint)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_tool_move)
        tools_menu.addAction(self.action_tool_brush)
        tools_menu.addAction(self.action_tool_rectangle)
        tools_menu.addAction(self.action_tool_lasso)
        tools_menu.addAction(self.action_tool_eraser)
        tools_menu.addAction(self.action_tool_crop)
        tools_menu.addSeparator()
        rotate_menu = tools_menu.addMenu("Rotate")
        rotate_menu.addAction(self.action_rotate_cw)
        rotate_menu.addAction(self.action_rotate_ccw)
        rotate_menu.addAction(self.action_rotate_180)
        tools_menu.addAction(self.action_curves)
        tools_menu.addAction(self.action_resize)
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

        The toolbar's open action is Open Folder (Ctrl+Shift+O) — the
        phase-2 manga-workflow default (open a folder of pages); Open Image
        lives in the File menu. Rest: Fit / 100% / Zoom Out / Zoom
        In | (sep) | Toggle Mask Overlay. Other sections (Detect/Inpaint/
        Tools/Undo) are added by their plans.
        """
        self.toolbar = QToolBar("Main", self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.toolbar.addAction(self.action_open_folder)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_fit_to_window)
        self.toolbar.addAction(self.action_actual_size)
        self.toolbar.addAction(self.action_zoom_out)
        self.toolbar.addAction(self.action_zoom_in)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.action_detect_text)
        self.toolbar.addAction(self.action_inpaint)
        self.toolbar.addSeparator()
        # Tool-buttons section (plan 04): checkable QToolButtons mirroring
        # their default (window) actions — the standalone action_tool_* whose
        # checked state set_active_tool drives explicitly, so the toolbar and
        # dock stay in sync (WR-02, UI-SPEC surface 1 toolbar layout).
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_move))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_brush))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_rectangle))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_lasso))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_eraser))
        self.toolbar.addWidget(self._make_tool_toolbar_button(self.action_tool_crop))
        # Surface 13 (plan 03-05): the 4-button undo toolbar collapses to 2
        # ([Undo][Redo]). Ctrl+Z pops the merged MASK/IMAGE/BOXES timeline; the
        # Phase 1 image/mask pair + inner divider are gone. Tooltips name the
        # unified shortcut (UI-SPEC §13).
        self.toolbar.addSeparator()
        self.action_undo.setToolTip("Undo last action (Ctrl+Z)")
        self.action_redo.setToolTip("Redo last action (Ctrl+Shift+Z)")
        self.toolbar.addAction(self.action_undo)
        self.toolbar.addAction(self.action_redo)
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
        # Toggle Box Overlay (Shift+M): enabled iff a page is open (the box
        # layer belongs to a page; the toggle is meaningful only with one
        # loaded — UI-SPEC §11).
        self.action_toggle_box_overlay.setEnabled(page_open)
        has_inpaint = self.canvas.has_inpaint_result()
        # Surface 29 (D-06, plan 05-06): Show Original is disabled with the
        # not-found tooltip when the current page's original is unverified —
        # a .mas-loaded page whose source path/checksum failed (the embedded
        # image is the only base; UI-SPEC §Copywriting). Normal sessions
        # (original_verified True — set on folder/image open by plan 05-05)
        # keep the inherited has_inpaint gating. The current page is read
        # from the stored _last_page_index (the D-11 seam rule — never
        # _current_page_index mid-navigation).
        page_original_unverified = False
        gating_idx = self._last_page_index
        if (
            gating_idx is not None
            and 0 <= gating_idx < len(self.image_files)
            and not self.image_files[gating_idx].original_verified
        ):
            page_original_unverified = True
        if page_original_unverified:
            self.action_show_original.setEnabled(False)
            self.action_show_original.setToolTip(
                "Show Original (P) — original file not found."
            )
        else:
            self.action_show_original.setEnabled(has_inpaint)
            self.action_show_original.setToolTip("")
        self.btn_preview_hold.setEnabled(has_inpaint)
        # The painting tools are usable only with a page open (they paint on
        # the mask layer, which is sized to the image). Move stays usable.
        # The 6th tool (Crop, D-11) follows the same page-open gating.
        self.action_tool_move.setEnabled(True)
        for act in (
            self.action_tool_brush,
            self.action_tool_rectangle,
            self.action_tool_lasso,
            self.action_tool_eraser,
            self.action_tool_crop,
        ):
            act.setEnabled(page_open)

        # Plan 04 batch/export actions. Export Page needs a page open and no
        # running async op. The three batch actions operate on the open folder
        # (D-06) and require no running async op (D-08 — a batch blocks the
        # editor). Cancel Batch is enabled ONLY while a batch is running
        # (D-09); it is meaningless otherwise.
        folder_open = bool(self.image_files)
        self.action_export_page.setEnabled(page_open and not self._op_running)
        self.action_export_typeset.setEnabled(page_open and not self._op_running)
        self.action_batch_detect.setEnabled(folder_open and not self._op_running)
        self.action_batch_clean.setEnabled(folder_open and not self._op_running)
        self.action_batch_detect_and_clean.setEnabled(
            folder_open and not self._op_running
        )
        self.action_cancel_batch.setEnabled(self._batch_active)

        # Plan 05-05 (D-07): project-persistence actions. Save Project… /
        # Save Project As… need an open page AND no running async op; Open
        # Project… needs only no running op (it opens into any state).
        self.action_save_project.setEnabled(page_open and not self._op_running)
        self.action_save_project_as.setEnabled(page_open and not self._op_running)
        self.action_open_project.setEnabled(not self._op_running)
        # Recent Projects entries (flagged in _refresh_recent_projects_menu)
        # gate on _op_running only; the empty placeholder + Clear Menu stay
        # as-is.
        for act in self.recent_projects_menu.actions():
            if act.property("recent_project"):
                act.setEnabled(not self._op_running)

        # Plan 06 OCR actions. Run OCR is enabled iff exactly one box is
        # selected AND no async op is running (D-01 — mirrors detect_text's
        # `page_open and not self._op_running` plus the one-box-selected
        # check); OCR All Boxes iff >= 1 box exists AND no async op is
        # running (D-03).
        box_selected = self.canvas._selected_box() is not None
        self.action_run_ocr.setEnabled(
            page_open and box_selected and not self._op_running
        )
        # Font-size actions (D-16, plan 07-05): page open + >= 1 box selected
        # + no async op (UI-SPEC §1 gating — mirrors action_run_ocr's shape).
        self.action_increase_font_size.setEnabled(
            page_open and box_selected and not self._op_running
        )
        self.action_decrease_font_size.setEnabled(
            page_open and box_selected and not self._op_running
        )
        self.action_ocr_all.setEnabled(
            page_open and self.canvas.box_count() > 0 and not self._op_running
        )
        # Select All Boxes (D-08, plan 07-02): enabled iff a page is open AND
        # >= 1 box exists AND no async op is running (mirrors action_ocr_all's
        # gate shape above).
        self.action_select_all_boxes.setEnabled(
            page_open and self.canvas.box_count() > 0 and not self._op_running
        )
        # Plan 07: Load Translations needs only an open page + no running op
        # (a page with no boxes reports the no-matches copy); Auto-Number
        # needs >= 1 box (mirrors action_ocr_all gating).
        self.action_load_translations.setEnabled(
            page_open and not self._op_running
        )
        self.action_auto_number_rtl.setEnabled(
            page_open and self.canvas.box_count() > 0 and not self._op_running
        )
        self.action_auto_number_ltr.setEnabled(
            page_open and self.canvas.box_count() > 0 and not self._op_running
        )

        # Plan 05-08 (D-21): Export OCR JSON… needs a page open + no async op;
        # Batch Export OCR JSON needs a folder open + no op running + no batch
        # already running (the UI-SPEC §27 gate — _batch_active blocks a
        # second batch while one runs, mirroring the three cleaning batch
        # actions).
        self.action_export_ocr_json.setEnabled(
            page_open and not self._op_running
        )
        self.action_batch_export_ocr.setEnabled(
            folder_open and not self._op_running and not self._batch_active
        )

        # Plan 05-06/06-05 image ops (Tools -> Image section):
        # Rotate/Curves/Resize are enabled iff a page is open AND no async op
        # is running (UI-SPEC surfaces 23/25/26/30 gating — synchronous ops
        # must not interleave with a model worker).
        for act in (
            self.action_rotate_cw,
            self.action_rotate_ccw,
            self.action_rotate_180,
            self.action_curves,
            self.action_resize,
        ):
            act.setEnabled(page_open and not self._op_running)
        # Plan 05-07: the numeric Crop… dialog (Edit menu) — same gating as
        # the image ops (surface 24b, §21).
        self.action_crop_dialog.setEnabled(page_open and not self._op_running)

    # -------------------------------------------------- image ops (plan 05-06)
    # PROJ-04's GUI apply layer: Rotate / Curves / Resize all funnel through
    # _apply_geometry_op — the ONE place the image-op contract lives (one undo
    # entry, D-14 re-baseline, D-22 geometry flag). The pure pixel/geometry
    # math is core/image_ops (plan 05-02); this section owns the canvas
    # read/write bridges + the undo push (plan 05-04's push_geometry_state).
    # The crop apply path (plan 05-07) reuses this exact orchestration.

    def _apply_geometry_op(
        self,
        op_name: str,
        geometry: bool,
        transform_fn,
        flash: str = "",
    ) -> None:
        """Apply a synchronous image op end-to-end (plan 05-06, PROJ-04).

        1. Gate: >= 1 page open AND no async op running.
        2. Flush the live canvas state into the outgoing ImageFile
           (``_snapshot_current_page`` — the plan 05-05 save-side seam).
        3. Capture the PRE-op state: image (detached ``.copy()``), mask QImage
           (detached ``.copy()`` when one exists), boxes snapshot — the
           one-press undo record.
        4.          ``transform_fn()`` -> ``(new_image, new_mask_bin, new_boxes)``:
           the op's pure math (core/image_ops). A None mask/boxes means the op
           does NOT touch that layer (curves is geometry-free, D-15).
        5. Write back: ``set_image_from_numpy`` (the setter copies), the mask
           planes rebuilt from the transformed composite via
           ``canvas.set_planes`` when the op transformed an existing mask
           (plan 08-02 — the composite becomes the auto plane), and
           ``set_boxes`` (split by origin) UNDER the
           ``_suppress_boxes_push`` guard — the geometry undo entry is the ONLY
           record (one press per op, never two).
        6. Push ONE geometry undo entry (plan 05-04) and re-baseline Show
           Original (D-14): the post-op image is now the "original"; the pre-op
           image is recoverable only via Ctrl+Z.
        7. Mark ``ImageFile.geometry_altered`` for geometry ops (rotate/resize/
           crop per D-22; NEVER curves), dirty the session, flash the status
           copy (UI-SPEC §Copywriting), and refresh the action states.
        """
        if self._op_running or self._current_page_index() is None:
            return
        self._snapshot_current_page()
        pre_image = self.canvas.get_image_numpy()
        if pre_image is None:
            return
        pre_image = pre_image.copy()
        pre_mask = self.canvas.get_mask().copy() if self.canvas.has_mask() else None
        pre_boxes = self.canvas.boxes_snapshot()

        result = transform_fn()
        if result is None:
            return
        new_image, new_mask_bin, new_boxes = result

        self.canvas.set_image_from_numpy(new_image)
        transformed_mask = new_mask_bin is not None and pre_mask is not None
        transformed_boxes = new_boxes is not None
        if transformed_mask:
            # Phase 8 (plan 08-02, Rule 1 deviation): set_mask now replaces
            # the AUTO plane only, so the transformed composite can no longer
            # be routed through it — stale same-dims manual/erase planes
            # would corrupt the recompose (a rotate-180's stale ledger would
            # erase the wrong pixels). Rebuild ALL planes from the
            # transformed composite: manual/erase transparent, auto = the
            # composite (provenance collapses into the auto plane — the
            # 08-01 geometry-invalidation stance applied at the canvas level;
            # the displayed composite is pixel-identical to Phase 5).
            self.canvas.set_planes(None, None, new_mask_bin)
        if transformed_boxes:
            user_pbs = [pb for pb in new_boxes if pb.origin == USER]
            detected_pbs = [pb for pb in new_boxes if pb.origin == DETECTED]
            self._suppress_boxes_push = True
            try:
                self.canvas.set_boxes(user_pbs, detected_pbs)
            finally:
                self._suppress_boxes_push = False

        # CR-01 (D-05/D-15 contract): the write-back must land in the model.
        # ``_snapshot_current_page`` above captured the PRE-op image; without
        # this update, navigation and save embed the pre-op image for any
        # page that is not the current page at the time (rotate page 2 ->
        # switch to page 3 -> rotation lost / saved boxes misaligned).
        # ``.copy()`` detaches from the op's buffer (Pitfall 2).
        idx = self._current_page_index()
        if idx is not None and 0 <= idx < len(self.image_files):
            self.image_files[idx].current_image = new_image.copy()

        self._record_geometry_op_name(op_name)
        self.history.push_geometry_state(
            pre_image,
            mask_qimage=pre_mask if transformed_mask else None,
            boxes=pre_boxes if transformed_boxes else None,
        )
        self.canvas.rebaseline_original()
        idx = self._current_page_index()
        if geometry and idx is not None and 0 <= idx < len(self.image_files):
            self.image_files[idx].geometry_altered = True
        self._set_session_dirty()
        if flash:
            self._show_transient_status(flash)
        self._refresh_action_states()

    def _rotate_page(self, k: int) -> None:
        """Tools -> Rotate -> 90° CW / 90° CCW / 180° (UI-SPEC surface 23).

        Silent apply (D-14 — no confirmation): image + mask + boxes rotate
        together via ``image_ops.rotate_page`` / ``rotate_boxes`` with the ONE
        convention (k=-1 CW, k=1 CCW, k=2 180 — np.rot90 semantics), one undo
        entry, Show Original re-baselines, ``geometry_altered`` is set (D-22).
        The menu actions call ``_rotate_page(-1/1/2)``.
        """
        if self._op_running or self._current_page_index() is None:
            return
        flash = {
            -1: "Rotated 90\u00b0 CW.",
            1: "Rotated 90\u00b0 CCW.",
            2: "Rotated 180\u00b0.",
        }[k]

        def _transform():
            img = self.canvas.get_image_numpy()
            if img is None:
                return None
            mask = self.canvas.get_mask()
            if mask is not None:
                mask_bin = mask_to_numpy_binary(mask)
            else:
                mask_bin = np.zeros(img.shape[:2], dtype=np.uint8)
            new_img, new_mask = image_ops.rotate_page(img, mask_bin, k)
            h, w = img.shape[:2]
            new_boxes = image_ops.rotate_boxes(
                self.canvas.boxes_snapshot(), w, h, k
            )
            return new_img, new_mask, new_boxes

        self._apply_geometry_op(
            "rotate", geometry=True, transform_fn=_transform, flash=flash
        )

    def _on_curves(self) -> None:
        """Tools -> Curves… (plan 06-05, UI-SPEC surface 30): live preview.

        The pre-dialog image is detached with ``.copy()`` BEFORE the dialog
        opens (Pitfall 2 — the restore/apply base). The dialog is a collector
        + preview driver: every control change re-renders the canvas through
        the capture-suppressed preview path, so the Show Original baseline
        stays pristine (RESEARCH Pitfall 5/9 — the preview never pushes and
        never poisons). Cancel restores the base silently (no entry, no
        flash); Apply commits ONE image-only geometry-free entry (D-15: masks
        and boxes untouched, ``geometry_altered`` NOT set).
        """
        if self._op_running or self._current_page_index() is None:
            return
        from manga_ai_studio.gui.curves_dialog import CurvesDialog

        base = self.canvas.get_image_numpy()
        if base is None:
            return
        base = base.copy()
        dialog = CurvesDialog(
            self,
            page_image=base,
            preview_callback=lambda composed: self.canvas.set_image_from_numpy_preview(
                composed, capture_original=False
            ),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            # Cancel: restore the pre-dialog image exactly — silently (no
            # undo entry, no status flash — UI-SPEC surface 30). The restore
            # is capture-suppressed (CR-01, T-06-09): on a fresh page the
            # baseline is absent (_original_image_numpy is None — the
            # folder-load state), so a capture-enabled restore would store
            # the LAST PREVIEW FRAME as the Show Original baseline and claim
            # an inpaint result. No rebaseline_original() here either — the
            # honest D-14 baseline is established exclusively by
            # _apply_geometry_op's tail rebaseline on Apply.
            self.canvas.set_image_from_numpy_preview(base.copy(), capture_original=False)
            return
        master, channels = dialog.result_values

        # UI-review FLAG (surface 30/28): the dialog's live previews mutated
        # the canvas (Pitfall 9), so _apply_geometry_op's pre-capture would
        # see the LAST PREVIEW frame — the post-curves image — as the undo
        # "before", making Ctrl+Z a no-op. Restore the detached pre-dialog
        # base first (mirroring the Cancel path above) so the undo record's
        # before-state is the true pre-op image (b376f8a ordering). The
        # restore is capture-suppressed too (CR-01, T-06-09): on a fresh
        # page a capture-enabled restore would transiently store the last
        # preview frame; the post-Apply baseline is established exclusively
        # by _apply_geometry_op's tail rebaseline_original() (D-14).
        self.canvas.set_image_from_numpy_preview(base.copy(), capture_original=False)

        def _transform():
            return image_ops.curves_page(base, master, channels), None, None

        self._apply_geometry_op(
            "curves", geometry=False, transform_fn=_transform, flash="Curves applied."
        )

    def _on_resize(self) -> None:
        """Tools -> Resize… (plan 05-06, UI-SPEC surface 26): dialog apply.

        The dialog collects ``(new_w, new_h)`` (px or percent-resolved pixels);
        Apply resizes image LANCZOS / mask NEAREST (D-18, A8) with boxes
        scaled int, pushes ONE geometry entry, re-baselines Show Original
        (D-14), marks ``geometry_altered`` (D-22), and flashes the resized
        dims copy.
        """
        if self._op_running or self._current_page_index() is None:
            return
        from manga_ai_studio.gui.resize_dialog import ResizeDialog

        img = self.canvas.get_image_numpy()
        if img is None:
            return
        h_img, w_img = img.shape[:2]
        dialog = ResizeDialog(self, current_w=w_img, current_h=h_img)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_w, new_h = dialog.result_values

        # WR-05: an identity resize (unchanged dims — 100% in percent mode,
        # or typing the current dims) is a no-op: applying it would push an
        # IMAGE-stack undo entry, re-baseline Show Original, and flip
        # ImageFile.geometry_altered — which moves the D-22 _ocr.json export
        # to cleaned/ for a page with no actual geometry change.
        if (new_w, new_h) == (w_img, h_img):
            return

        def _transform():
            mask = self.canvas.get_mask()
            if mask is not None:
                mask_bin = mask_to_numpy_binary(mask)
            else:
                mask_bin = np.zeros(img.shape[:2], dtype=np.uint8)
            new_img, new_mask = image_ops.resize_page(img, mask_bin, new_w, new_h)
            new_boxes = image_ops.resize_boxes(
                self.canvas.boxes_snapshot(), w_img, h_img, new_w, new_h
            )
            return new_img, new_mask, new_boxes

        self._apply_geometry_op(
            "resize",
            geometry=True,
            transform_fn=_transform,
            flash=f"Resized to {new_w} \u00d7 {new_h}.",
        )

    # -------------------------------------------------- crop (plan 05-07, D-11)
    # Both crop entry points funnel here: the canvas Crop tool (armed rect +
    # Enter -> ``crop_committed``) and the numeric Crop… dialog (Edit menu).
    # ``_apply_crop`` is the D-16/D-18 contract: exact image + mask slices,
    # drop fully-outside boxes / clip partial ones (bbox AND line quads) via
    # the plan 05-02 core seam, dropped count in the status flash, ONE
    # geometry undo entry (via ``_apply_geometry_op``), Show Original
    # re-baseline (D-14), ``geometry_altered`` (D-22).
    def _on_crop_committed(self, scene_rect) -> None:
        """canvas.crop_committed -> ``_apply_crop`` (scene rect -> image pixels).

        The armed rect is in SCENE coordinates (floats); the apply path is
        integer-pixel: ``math.floor`` on each edge, clamped to the image dims
        — never beyond (the tool already clamps the rect to the page; the
        clamp here is belt-and-suspenders for programmatic callers).
        """
        img = self.canvas.get_image_numpy()
        if img is None:
            return
        h_img, w_img = img.shape[:2]
        x = max(0, min(w_img - 1, math.floor(scene_rect.x())))
        y = max(0, min(h_img - 1, math.floor(scene_rect.y())))
        x2 = max(x + 1, min(w_img, math.floor(scene_rect.right())))
        y2 = max(y + 1, min(h_img, math.floor(scene_rect.bottom())))
        self._apply_crop(x, y, x2 - x, y2 - y)

    def _apply_crop(self, x: int, y: int, w: int, h: int) -> None:
        """Apply a crop end-to-end (image + mask slice, drop/clip boxes).

        ``(x, y, w, h)`` are integer image pixels. A degenerate call (w < 1,
        h < 1, or any edge out of bounds) is a SILENT no-op (T-05-17) — the
        tool's 8x8 minimum and the dialog ranges make it near-impossible;
        the guard covers programmatic edges so a degenerate slice never
        reaches the core seam. The flash carries the dropped-box count copy
        when D-16 removed boxes.
        """
        if self._op_running or self._current_page_index() is None:
            return
        img = self.canvas.get_image_numpy()
        if img is None:
            return
        h_img, w_img = img.shape[:2]
        if (
            not isinstance(x, int)
            or not isinstance(y, int)
            or not isinstance(w, int)
            or not isinstance(h, int)
            or w < 1
            or h < 1
            or x < 0
            or y < 0
            or x + w > w_img
            or y + h > h_img
        ):
            return  # degenerate — silent no-op (T-05-17)

        state: dict = {"ran": False, "dropped": 0}

        def _transform():
            mask = self.canvas.get_mask()
            if mask is not None:
                mask_bin = mask_to_numpy_binary(mask)
            else:
                mask_bin = np.zeros(img.shape[:2], dtype=np.uint8)
            new_img, new_mask, kept_boxes, dropped = (
                image_ops.crop_page_with_boxes(
                    img, mask_bin, self.canvas.boxes_snapshot(), x, y, w, h
                )
            )
            state["ran"] = True
            state["dropped"] = dropped
            return new_img, new_mask, kept_boxes

        self._apply_geometry_op("crop", geometry=True, transform_fn=_transform)
        if not state["ran"]:
            return
        dropped = state["dropped"]
        if dropped > 0:
            flash = (
                f"Cropped. {dropped} box(es) were outside the crop and"
                " removed \u2014 press Ctrl+Z to restore."
            )
        else:
            flash = "Cropped."
        self._show_transient_status(flash)

    def _on_crop_dialog(self) -> None:
        """Edit -> Crop… (plan 05-07, UI-SPEC surface 24b): numeric crop.

        The dialog opens at the FULL current page bounds (x=0, y=0, w=W,
        h=H — never empty) with live W−x / H−y range recompute; Apply runs
        the same crop semantics as the canvas tool path via
        ``_apply_crop(*dialog.result_values)``.
        """
        if self._op_running or self._current_page_index() is None:
            return
        from manga_ai_studio.gui.crop_dialog import CropDialog

        img = self.canvas.get_image_numpy()
        if img is None:
            return
        h_img, w_img = img.shape[:2]
        dialog = CropDialog(self, page_w=w_img, page_h=h_img)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        x, y, w, h = dialog.result_values
        self._apply_crop(x, y, w, h)

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
        validators. The D-07 Unsaved Changes gate runs before the session is
        replaced (after the dialog — the file was already chosen).
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        if not self._confirm_discard_changes():
            return
        self._open_single_image(Path(path))

    def open_folder(self) -> None:
        """Open a folder of images: scan (flat, non-recursive), sort, populate.

        UI-SPEC surface 4 Open Folder (Ctrl+Shift+O). Folder scan uses
        ``Path.iterdir`` + ``is_file`` + ``validate_image_path`` — symlink
        resolution is handled by ``Path.resolve()`` inside the validator.
        The D-07 Unsaved Changes gate runs before the session is replaced.
        """
        directory = QFileDialog.getExistingDirectory(self, "Open Folder", "")
        if not directory:
            return
        if not self._confirm_discard_changes():
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

        CR-02: a non-project session (Open Image / Open Folder / drag-drop)
        resets the project identity (``_project_dir`` / ``_project_name``).
        Without this, opening a folder after working in a project left the
        stale dir/name behind and Ctrl+S silently overwrote the PREVIOUS
        project's manifest and ``.mas`` files with the new session's pages.
        Project loads (``_load_project_session`` / ``_load_single_page_mas``)
        set their own identity and never route through this method.
        """
        ordered = natsorted(paths, key=lambda p: str(p))
        # D-06 (plan 05-05): a normal image/folder open loads each page from
        # its own path, so Show Original is valid — every ImageFile starts
        # original_verified=True (consumed by plan 05-06's Show Original
        # gating; .mas-loaded pages set it per the checksum rule instead).
        self.image_files = [ImageFile(path=p, original_verified=True) for p in ordered]
        self._project_dir = None
        self._project_name = None
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

        # Step 1b (plan 03-05): persist the OUTGOING page's canvas boxes into its
        # ImageFile.boxes (the D-11 mirror of Phase 2's mask seam). boxes_snapshot()
        # (plan 03-03) already materializes a fresh ``PageBox(box=item.current_box(),
        # ...)`` per item at call-time — so the snapshot is detached from the live
        # BoxItems' QRectF rects by construction (Pitfall 3 + 6, T-03-08). NO
        # additional .copy() is needed on the boxes path (unlike QImage which
        # buffers alias; Box is @frozen and PageBox is a fresh dataclass per
        # item). The same OUTGOING index (_last_page_index) is reused — the
        # Phase 2 lesson applies identically (regression-guarded by
        # test_box_persistence_uses_copy + test_outgoing_index_uses_last_page_index).
        if (
            outgoing_idx is not None
            and 0 <= outgoing_idx < len(self.image_files)
            and self.canvas.has_boxes()
        ):
            self.image_files[outgoing_idx].boxes = self.canvas.boxes_snapshot()

        # Step 2: reset the per-page history (unchanged from plan 06).
        self.reset_history()

        # Step 3: load the new page image (with the D-06/D-08 missing-original
        # navigation fallback). ``incoming_idx`` is valid BEFORE this step:
        # the preceding ``select_path`` already flipped
        # ``file_table.current_path()`` to the incoming page, and the
        # placeholder path stored on the ImageFile equals it by construction.
        # CR-01: ``current_image`` is the AUTHORITATIVE in-memory state — the
        # D-05 "resume exactly where you left off" contract. It is populated
        # for every page at project load (D-08 embedded image), after every
        # image op / undo (plan 05-06 apply path), and by the save-side flush
        # (``_snapshot_current_page``). When present it is displayed directly
        # (a disk re-load is the fallback for pages never touched in memory —
        # a page whose canvas image was never captured). The D-06 rule is
        # subsumed: an unverified-original page with an embedded image has
        # ``current_image`` set, so the "Couldn't open file" warning is
        # correctly skipped for it (the placeholder path NEVER reaches
        # ``set_image_from_path``).
        incoming_idx = self._current_page_index()
        imf = (
            self.image_files[incoming_idx]
            if incoming_idx is not None and 0 <= incoming_idx < len(self.image_files)
            else None
        )
        if imf is not None and imf.current_image is not None:
            # Pitfall 2: the .copy() detaches the embedded numpy before the
            # QImage build (canvas.py:658-663); decode-time .convert("RGB")
            # already guarantees the (H,W,3) uint8 contract.
            self.canvas.set_image_from_numpy(imf.current_image.copy())
            if imf.mask is None or imf.mask.isNull():
                # The path-based load resets the mask to a fresh transparent
                # one (set_image); mirror it here so a stale overlay from the
                # outgoing page does not linger (Step 4 restores the incoming
                # mask when present).
                h, w = imf.current_image.shape[:2]
                empty = QImage(w, h, QImage.Format.Format_ARGB32)
                empty.fill(Qt.GlobalColor.transparent)
                self.canvas.set_mask(empty)
        else:
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

        # Step 4b (plan 03-05): restore the INCOMING page's persisted boxes onto
        # the canvas (the D-11 mirror of Phase 2's mask restore). set_boxes
        # rebuilds BoxItems from the pageboxes; origin is preserved per snapshot
        # (plan 03-03's boxes_snapshot captured .origin + .payload). Splitting by
        # origin here keeps set_boxes's (user, detected) signature stable.
        # The incoming boxes are already detached (snapshotted on the outgoing
        # side at Step 1b); a re-snapshot would be belt-and-suspenders but
        # unnecessary (PageBox.box is a @frozen Box, no aliasing risk).
        #
        # Unlike the mask (which set_image_from_path reinitializes to the new
        # image size), boxes are NOT tied to image dimensions, so they must be
        # explicitly cleared when the incoming page has none — otherwise the
        # OUTGOING page's boxes bleed through onto the incoming page (Rule 1 bug
        # caught by test_box_persistence_round_trip's page-B-has-no-boxes check).
        if incoming_idx is not None and 0 <= incoming_idx < len(self.image_files):
            incoming_imf = self.image_files[incoming_idx]
            # ImageFile.has_boxes() (plan 03-01) is the truthiness check on the
            # persisted slot — mirrors the canvas's has_boxes() API on the data
            # model side. Empty list = no boxes (the slot was either never set
            # or was cleared).
            incoming_boxes = incoming_imf.boxes if incoming_imf.has_boxes() else []
            user_pbs = [pb for pb in incoming_boxes if pb.origin == USER]
            detected_pbs = [pb for pb in incoming_boxes if pb.origin == DETECTED]
            # Always call set_boxes (even with empty lists) so stale boxes from
            # the outgoing page are cleared when the incoming page has none.
            #
            # WR-05 guard: this is a pure RESTORE (loading persisted boxes onto
            # the canvas on page-switch), not a user edit. set_boxes emits
            # boxes_modified; after the CR-01 fix that would push a spurious
            # BOXES snapshot (history was just reset at Step 2, so the restore
            # would seed an undo entry for a state the user never edited). The
            # mask analog (Step 4 set_mask) is silent; set_boxes is not, so the
            # box side suppresses. Mirrors apply_undo_boxes' guard.
            self._suppress_boxes_push = True
            try:
                self.canvas.set_boxes(user_pbs, detected_pbs)
            finally:
                self._suppress_boxes_push = False

        # Step 5 (unchanged tail; title via the D-07 format — plan 05-05).
        self._update_title()
        self.canvas.fit_to_window()
        self._add_recent_file(path)
        self._refresh_status_bar()

        # Record THIS page as the OUTGOING page for the NEXT navigation. Must
        # run AFTER the restore so a subsequent select_path→on_page_selected
        # captures this page's (now restored) state as its outgoing snapshot.
        # Plan 04 disables navigation while _op_running to avoid the D-11 write
        # race (RESEARCH Open Question Q2 / T-02-05).
        self._last_page_index = self._current_page_index()

        # WR-04: re-refresh the action states NOW. The tail's earlier
        # _refresh_status_bar ran BEFORE _last_page_index flipped, so the
        # D-06 Show Original gating (read from _last_page_index at
        # _refresh_action_states) still reflected the OUTGOING page — e.g.
        # navigating from a verified-original page to a portable .mas page
        # left Show Original enabled. Refreshing after the flip makes the
        # gating follow the incoming page.
        self._refresh_action_states()

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

    def _default_font_family(self) -> str:
        """Read the persisted app-level default font family (G-07-3, plan 07-11).

        Returns ``""`` when no family was ever saved — the empty-family
        contract: the new-box creation sites map an empty read -> ``None`` ->
        the renderer's ``TextStyle()`` defaults (Liberation Sans), keeping
        today's behavior on a fresh install. ``str(... or "")`` coercion on
        read (T-07-18): a garbage/absent value can never reach the factory.
        """
        return str(self._settings().value("defaultFontFamily", "") or "")

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

    # ------------------------------------------------ project session (plan 05-05)
    # Save Project… / Open Project… (PROJ-01 D-07/D-08/D-09): the resumable-
    # workspace session layer. Save flushes the live canvas state through the
    # Phase 2 D-11 seam into per-page ImageFile slots and hands them to
    # core/project_io (the ONLY disk boundary); Open rebuilds the session
    # from the manifest with D-06 original re-verification + the embedded
    # image as the D-08 fallback. Menu structure is executor-authoritative
    # per UI-SPEC surface 21.

    def _session_dirty(self) -> bool:
        """True iff ANY page carries unsaved edits (D-07 dirty tracking).

        Any page mutation since the last save marks the page's
        ``ImageFile.dirty`` (via :meth:`_set_session_dirty`); the window
        title appends ``*`` and the Unsaved Changes prompt fires on
        session-replacement actions while this is True.
        """
        return any(imf.dirty for imf in self.image_files)

    def _update_title(self) -> None:
        """Render the D-07 window title.

        ``Manga AI Studio — {project-name} — {page-filename}*`` with a
        project open, ``Manga AI Studio — {page-filename}*`` without; ``*``
        is the LAST character while the session is dirty (any page). Save
        clears the dirty state, so the suffix disappears.
        """
        if not self.image_files:
            self.setWindowTitle("Manga AI Studio")
            return
        page = self.file_table.current_path()
        page_name = page.name if page is not None else ""
        if self._project_name:
            base = f"Manga AI Studio \u2014 {self._project_name} \u2014 {page_name}"
        else:
            base = f"Manga AI Studio \u2014 {page_name}"
        if self._session_dirty():
            base += "*"
        self.setWindowTitle(base)

    def _set_session_dirty(self) -> None:
        """Mark the current page dirty + refresh the title (D-07).

        Connected to the current page's existing mutation signals
        (``canvas.mask_modified``, ``canvas.boxes_modified``) plus the
        inpaint-finish handler; the OCR + Inspector commit handlers emit
        ``boxes_modified`` so they ride the same connection. The restore
        paths (page navigation / undo / detection / apply_undo_boxes) set
        ``_suppress_boxes_push`` around their ``set_boxes`` calls, so the
        guard here keeps those non-edits from marking the session dirty.
        """
        if self._suppress_boxes_push:
            return
        idx = self._current_page_index()
        if idx is not None and 0 <= idx < len(self.image_files):
            self.image_files[idx].dirty = True
        self._update_title()

    def _snapshot_current_page(self) -> None:
        """Flush the live canvas state into the outgoing ImageFile (save side).

        Mirrors the Phase 2 D-11 seam (RESEARCH Common Operation 4): the
        OUTGOING index is the stored ``self._last_page_index`` — NEVER
        ``_current_page_index()`` (Pitfall 7 — ``select_path`` mutates
        ``current_path`` before ``on_page_selected`` runs). The mask write
        uses the MANDATORY ``.copy()`` boundary detach (Pitfall 2); boxes
        are detached by construction (``boxes_snapshot()`` materializes
        fresh PageBoxes); ``current_image`` is the canvas numpy (the D-05
        per-page current-image contract — resume exactly where you left off).
        """
        idx = self._last_page_index
        if idx is None or not (0 <= idx < len(self.image_files)):
            return
        if self.canvas.has_mask():
            self.image_files[idx].mask = self.canvas.get_mask().copy()
        self.image_files[idx].boxes = self.canvas.boxes_snapshot()
        image_np = self.canvas.get_image_numpy()
        if image_np is not None:
            self.image_files[idx].current_image = image_np

    def _choose_project_dir(self) -> tuple[Path | None, bool]:
        """The Save Project As… folder dialog (D-02).

        Defaults to ``<source-parent>/<chapter-name>.mas-project`` (the
        sibling-of-source convention), or ``<image-parent>/<image-stem>
        .mas-project`` for a single-image session. G-05-2 (plan 05-10): the
        default folder is PRE-CREATED before the dialog — the native dialog
        refuses a non-existent default and silently falls back to the source
        parent, which is exactly how saves leaked into the album root. A
        self-created default that ends up unused (cancel / different pick)
        is removed best-effort (``rmdir`` removes EMPTY directories only —
        the "only if created by us and left empty" guard); a pick equal to
        the default keeps it (the save populates it). On mkdir failure the
        dialog falls back to the source parent (the pre-fix behavior) and
        Save As stays functional on read-only parents.

        WR-01: returns ``(picked, created)`` — ``created`` reports whether
        THIS call pre-created the default folder, so ``_save_project`` can
        clean it up when the save aborts AFTER the dialog accepted the
        default (duplicate-stem / no-resolvable-source abort, save OSError)
        before anything was written. Returns ``(None, created)`` on cancel.
        """
        first = self.image_files[0]
        if len(self.image_files) == 1:
            default = first.path.parent / f"{first.path.stem}.mas-project"
        else:
            default = first.path.parent / f"{first.path.parent.name}.mas-project"
        created = False
        if not default.exists():
            try:
                default.mkdir(parents=True, exist_ok=True)
                created = True
            except OSError:
                logger.warning(
                    f"Save Project As: could not pre-create the default"
                    f" folder '{default}' — falling back to the source"
                    " parent as the dialog default"
                )
                default = first.path.parent
        directory = QFileDialog.getExistingDirectory(
            self, "Save Project As", str(default)
        )
        if not directory:
            if created:
                self._discard_stray_project_dir(default)
            return None, created
        picked = Path(directory)
        if picked != default and created:
            self._discard_stray_project_dir(default)
        return picked, created

    def _discard_stray_project_dir(self, folder: Path) -> None:
        """Best-effort cleanup of a self-created, unused project folder.

        G-05-2 (plan 05-10): ``_choose_project_dir`` pre-creates the default
        folder so the native dialog accepts it; when the dialog is cancelled
        or redirected elsewhere, the stray empty folder is removed. ``rmdir``
        only removes EMPTY directories, so a folder the user populated (or
        that pre-existed with content) is never touched; OSError is
        swallowed + debug-logged (cleanup is best-effort).
        """
        try:
            if folder.is_dir():
                folder.rmdir()
        except OSError:
            logger.debug(f"Could not remove stray project folder '{folder}'")

    def _page_image_source(self, idx: int) -> np.ndarray | None:
        """Resolve the per-page image to embed at save time (RESEARCH A3).

        CR-01: ``ImageFile.current_image`` is the AUTHORITATIVE state — it is
        refreshed by every image op / undo and by the save-side flush
        (``_snapshot_current_page``), so a non-current page that was edited
        embeds its POST-op image (the D-05 "resume exactly where you left
        off" contract). Pages never touched in memory (``current_image`` is
        None) fall back to ``cleaned/<stem>`` in their source dir when that
        file exists (the Phase 2 convention), else the source file at
        ``ImageFile.path``, else None (the page is skipped by the caller with
        a warning). Reads are ``.copy()``-detached (Pitfall 2). Returns None
        when no source exists at all.
        """
        imf = self.image_files[idx]
        if imf.current_image is not None:
            return imf.current_image
        cleaned = imf.path.parent / "cleaned" / imf.path.name
        if cleaned.is_file():
            return np.asarray(Image.open(cleaned).convert("RGB")).copy()
        if imf.path.is_file():
            return np.asarray(Image.open(imf.path).convert("RGB")).copy()
        return None

    def _save_project(self, force_as: bool = False) -> bool:
        """Save Project… (Ctrl+S) — write the session as a project folder.

        D-07/D-02 flow: no page open → no-op (the action is disabled too);
        a clean session flashes "No changes to save." and writes nothing;
        otherwise flush the current page, then save — routing through the
        Save As… folder dialog when ``force_as`` or the session has no
        project dir yet. The disk write is core's
        :func:`project_io.save_project` (the only disk boundary);
        an OSError surfaces the save-failure copy (T-05-12) and the in-memory
        session is untouched. On success: dirty cleared, project dir/name
        recorded, Recent Projects updated, title refreshed (no ``*``), and
        the "Saved project …" transient shows. WR-01: when the dialog
        accepted a folder this save pre-created, an abort before/at the
        write (duplicate stems, no resolvable page source, save OSError)
        removes the empty stray folder best-effort.

        :return: True when the project was written (or there was nothing to
            save); False when the save was aborted (cancelled folder dialog)
            or failed (WR-01: the Unsaved-Changes gate keys on this — a
            failed save must abort the session-replacing action, even when a
            project dir already exists from a previous save).
        """
        if self._current_page_index() is None:
            return False
        if not force_as and not self._session_dirty():
            self._show_transient_status("No changes to save.")
            return True
        self._snapshot_current_page()

        created_default = False
        project_dir = self._project_dir
        if project_dir is None or force_as:
            project_dir, created_default = self._choose_project_dir()
            if project_dir is None:
                return False  # dialog cancelled — nothing written, session untouched

        # Project name: keep an open project's name; derive for new sessions
        # (chapter = source-folder name; single-image session = image stem).
        if self._project_name is not None:
            name = self._project_name
        elif len(self.image_files) == 1:
            name = self.image_files[0].path.stem
        else:
            name = self.image_files[0].path.parent.name

        page_files: list[tuple[str, dict[str, bytes]]] = []
        for idx, imf in enumerate(self.image_files):
            image_rgb = self._page_image_source(idx)
            if image_rgb is None:
                logger.warning(
                    f"Save Project: page '{imf.path.name}' has no image source"
                    " — skipped"
                )
                continue
            mask_bin = None
            if imf.mask is not None and not imf.mask.isNull():
                mask_bin = mask_to_numpy_binary(imf.mask)
            original_sha = ""
            if imf.path.is_file():
                try:
                    original_sha = project_io.sha256_file(imf.path)
                except OSError:
                    original_sha = ""
            page_files.append(
                (
                    imf.path.stem,
                    project_io.build_page_entries(
                        {
                            "boxes": imf.boxes if imf.boxes is not None else [],
                            "image_rgb": image_rgb,
                            "mask_bin": mask_bin,
                            "geometry_altered": imf.geometry_altered,
                            "original_path": imf.path,
                            "original_sha256": original_sha,
                        }
                    ),
                )
            )

        # WR-03: duplicate stems (a folder with both ``page.png`` and
        # ``page.jpg``) would silently write both pages to the same
        # ``<stem>.mas`` — the second overwrites the first and the manifest
        # lists two pages pointing at one file. Surface a save error listing
        # the colliding stems BEFORE writing anything (the dirty flags stay
        # untouched).
        stems = [stem for stem, _ in page_files]
        if len(stems) != len(set(stems)):
            duplicates = sorted({s for s in stems if stems.count(s) > 1})
            logger.error(f"Save Project failed: duplicate page stems {duplicates}")
            QMessageBox.critical(
                self,
                f"Couldn't save '{name}'.",
                "Two or more pages share the same file name"
                f" ({', '.join(duplicates)}). Rename the source files so each"
                " page has a unique name, then save again.",
            )
            if created_default:
                self._discard_stray_project_dir(project_dir)
            return False

        # WR-02: every page's image source unresolvable (e.g. originals
        # deleted before a folder session's first save) would write a 0-page
        # manifest and then clear the dirty flags — the user believes the
        # session was saved, but reopening fails with "project contains no
        # pages". Abort with the save-failure copy BEFORE writing; the dirty
        # flags stay untouched so the session remains recoverable.
        if not page_files:
            logger.error(
                "Save Project failed: no page has a resolvable image source"
            )
            QMessageBox.critical(
                self,
                f"Couldn't save '{name}'.",
                "No page could be read for saving. Check that the source"
                " images still exist and see the log for details.",
            )
            if created_default:
                self._discard_stray_project_dir(project_dir)
            return False

        try:
            project_io.save_project(project_dir, name, page_files)
        except OSError as exc:
            # T-05-12: the save-failure copy; the traceback goes to loguru
            # (the in-memory session is untouched).
            logger.error(f"Save Project failed: {exc}", exc_info=True)
            QMessageBox.critical(
                self,
                f"Couldn't save '{name}'.",
                "Check that the folder is writable and see the log for details.",
            )
            if created_default:
                self._discard_stray_project_dir(project_dir)
            return False

        self._project_dir = project_dir
        self._project_name = name
        for imf in self.image_files:
            imf.dirty = False
        self._add_recent_project(project_dir)
        self._update_title()
        self._show_transient_status(
            f"Saved project '{name}' ({len(page_files)} pages)."
        )
        return True

    def _save_project_as(self) -> None:
        """Save Project As… (Ctrl+Shift+S): choose the folder, then save."""
        if self._current_page_index() is None:
            return
        self._save_project(force_as=True)

    def _open_project(self, manifest_path: Path | None = None) -> None:
        """Open Project… — the D-08/D-09 open flow (its shortcut key is the
        D-07-mandated one; per Pitfall 8 it binds here and nowhere else).

        Dialog (or a Recent Projects entry / chapter-climb caller) hands over
        a ``manifest.json`` or a page ``.mas``. Routing (D-09, UI-SPEC
        surface 21/22): a manifest rebuilds the session
        (:meth:`_load_project_session`); a page ``.mas`` with a sibling
        manifest pops the Chapter Detected prompt ([Open Project] loads the
        chapter, [Open Page Only] opens the page standalone, Esc cancels
        entirely); no sibling → the page opens standalone. Every failure
        (ProjectFormatError / OSError — corrupt or newer-version files)
        surfaces the corrupt-project copy (T-05-13) and the CURRENT session
        is never mutated — the new session is built fully before swapping.
        """
        if self._op_running:
            return
        if manifest_path is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Project",
                "",
                "Manga AI Studio Project (manifest.json *.mas)",
            )
            if not path:
                return
            selected = Path(path)
        else:
            selected = manifest_path
        try:
            if selected.name == "manifest.json":
                self._load_project_session(selected)
            elif selected.suffix.lower() == ".mas":
                sibling = project_io.find_sibling_manifest(selected)
                if sibling is not None:
                    choice = self._confirm_chapter_climb(selected, sibling)
                    if choice == "project":
                        self._load_project_session(sibling)
                    elif choice == "page":
                        self._load_single_page_mas(selected)
                    # None (Esc / close) → cancel the action entirely; the
                    # previous session stays untouched (UI-SPEC §22).
                else:
                    self._load_single_page_mas(selected)
            else:
                logger.warning(
                    f"Open Project: unsupported selection '{selected.name}'"
                )
        except (project_io.ProjectFormatError, OSError) as exc:
            # T-05-12/T-05-13: corrupt-project copy; the traceback goes to
            # loguru. The session-swap happens only after the full rebuild
            # succeeds, so the previous session is byte-identical here.
            logger.error(f"Open Project failed: {exc}", exc_info=True)
            QMessageBox.critical(
                self,
                f"Couldn't open '{selected.name}'.",
                "The project file may be corrupt or from a newer version of"
                " Manga AI Studio. No pages were changed.",
            )

    def _confirm_chapter_climb(
        self, page_path: Path, manifest_path: Path
    ) -> str | None:
        """D-09 'Chapter Detected' prompt for a page ``.mas`` with a sibling
        manifest (UI-SPEC surface 22 + §Copywriting).

        Returns ``"project"`` (load the chapter via the manifest),
        ``"page"`` (open the single page standalone), or ``None`` (Esc /
        window close — cancel the action ENTIRELY; Esc must never silently
        load the chapter OR the page, UI-SPEC §22). A hidden EscapeRole
        button absorbs Esc so ``clickedButton()`` is None on Escape.
        """
        data = project_io.load_project(manifest_path)  # re-validated (cheap)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Chapter Detected")
        box.setText(
            f"'{page_path.name}' is part of the project '{data['name']}'"
            f" ({len(data['pages'])} pages). Open the entire project instead?"
        )
        open_btn = box.addButton("Open Project", QMessageBox.ButtonRole.AcceptRole)
        page_btn = box.addButton(
            "Open Page Only", QMessageBox.ButtonRole.RejectRole
        )
        esc_btn = QPushButton("Cancel", box)
        # ActionRole = a non-special placement role; the ESCAPE binding comes
        # from setEscapeButton below (PySide6 exposes no ButtonRole.EscapeRole).
        box.addButton(esc_btn, QMessageBox.ButtonRole.ActionRole)
        esc_btn.hide()
        box.setEscapeButton(esc_btn)
        box.setDefaultButton(open_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_btn:
            return "project"
        if clicked is page_btn:
            return "page"
        return None

    def _build_image_file_from_parsed(
        self, parsed: dict, fallback_path: Path
    ) -> ImageFile:
        """Build an ``ImageFile`` from a page container's parsed entries.

        Shared by :meth:`_load_project_session` and
        :meth:`_load_single_page_mas`. The D-06 rule: ``path`` = the original
        ref when ``verify_original`` passes (sha256 match), else
        ``fallback_path`` — a placeholder with the original stem so the
        sidebar shows the right name; ``original_verified`` carries the D-06
        result. The mask restores via ``numpy_binary_to_mask_qimage`` (which
        ``.copy()``-detaches — Pitfall 2), boxes via ``json_to_pagebox``
        (the Phase 3 setter path, D-15 seam preserved), and the embedded
        ``image.png`` decodes into ``ImageFile.current_image`` for EVERY
        page — the D-08 dims source for non-current pages AND the D-06/D-08
        navigation fallback. A corrupt embedded blob raises
        ProjectFormatError (corrupt-project dialog at the caller).
        """
        original_ref = None
        original_verified = False
        original = parsed.get("original")
        if isinstance(original, dict) and original.get("path"):
            if project_io.verify_original(
                original["path"], original.get("sha256", "") or ""
            ):
                original_ref = Path(original["path"])
                original_verified = True
        if original_ref is None:
            original_ref = fallback_path
        imf = ImageFile(path=original_ref)
        imf.original_verified = original_verified
        imf.geometry_altered = bool(
            parsed["meta"].get("geometry_altered", False)
        )
        if parsed["mask"] is not None:
            imf.mask = numpy_binary_to_mask_qimage(parsed["mask"])
        imf.boxes = [
            project_io.json_to_pagebox(d)
            for d in parsed["meta"].get("boxes") or []
        ]
        try:
            # .convert("RGB") normalizes odd embedded blobs to the (H,W,3)
            # uint8 contract set_image_from_numpy enforces (canvas.py:631-634);
            # the .copy() detaches (Pitfall 2).
            imf.current_image = np.asarray(
                Image.open(BytesIO(parsed["image_png"])).convert("RGB")
            ).copy()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            # CR-03: a huge embedded PNG can also raise PIL's
            # DecompressionBombError (not an OSError/ValueError) — it must
            # surface as ProjectFormatError too, so _open_project's
            # (ProjectFormatError, OSError) handler shows the corrupt-project
            # dialog instead of an unhandled Qt-event exception (T-05-01).
            raise project_io.ProjectFormatError(
                f"corrupt embedded image: {exc}"
            ) from exc
        # WR-06: the declared ``meta.img`` dims must match the actual decoded
        # PNG. ``validate_meta`` cross-checks declared-vs-declared and the
        # MAX_IMAGE_DIMENSION cap but never the blob; a crafted file declaring
        # 100x100 with a 10000x10000 PNG would otherwise reshape the mask to
        # 100x100 while the canvas displays 10000x10000 — restored mask
        # misaligned with the displayed image, and exported _ocr.json dims
        # (canvas) inconsistent with the mask bbox coordinates (model). The
        # declared dims are ints by validate_meta's _coerce_int; the .get
        # defaults are belt-and-suspenders.
        img_meta = parsed["meta"].get("img") or {}
        declared_w = img_meta.get("w")
        declared_h = img_meta.get("h")
        actual_h, actual_w = imf.current_image.shape[:2]
        if declared_w != actual_w or declared_h != actual_h:
            raise project_io.ProjectFormatError(
                f"embedded image is {actual_w}x{actual_h} but meta.img"
                f" declares {declared_w}x{declared_h}"
            )
        return imf

    def _display_page_state(self, imf: ImageFile) -> None:
        """Display a page's embedded image + mask + boxes on the canvas (D-08).

        The load-side mirror of the D-11 seam: the embedded ``current_image``
        goes in via ``set_image_from_numpy`` (no re-decode — the D-05
        current-image contract), the mask via ``set_mask`` (empty transparent
        when the page has none — the stale overlay must not linger),
        and the boxes via ``set_boxes`` split by origin, with the
        ``_suppress_boxes_push`` guard (WR-05: a pure restore must not push).
        """
        self.canvas.set_image_from_numpy(imf.current_image.copy())
        if imf.mask is not None and not imf.mask.isNull():
            self.canvas.set_mask(imf.mask.copy())
        else:
            h, w = imf.current_image.shape[:2]
            empty = QImage(w, h, QImage.Format.Format_ARGB32)
            empty.fill(Qt.GlobalColor.transparent)
            self.canvas.set_mask(empty)
        user_pbs = [pb for pb in (imf.boxes or []) if pb.origin == USER]
        detected_pbs = [pb for pb in (imf.boxes or []) if pb.origin == DETECTED]
        self._suppress_boxes_push = True
        try:
            self.canvas.set_boxes(user_pbs, detected_pbs)
        finally:
            self._suppress_boxes_push = False

    def _confirm_discard_changes(self) -> bool:
        """The D-07 Unsaved Changes prompt: [Save] [Discard] [Cancel].

        Returns True when the caller may proceed (session clean, discarded,
        or saved); False = Cancel — abort the action. Runs on every
        session-replacement entry point (Quit, window close, Open
        Project…, Open Image…, Open Folder…) while any page is dirty.
        Save runs the normal save flow (Save As… first when the session has
        no project path); if the save is cancelled/fails the action aborts.
        """
        if not self._session_dirty():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unsaved Changes")
        box.setText(
            f"Save changes to '{self._project_name or 'this session'}' before"
            " continuing? Changes you don't save will be lost."
        )
        save_btn = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = box.addButton(
            "Discard", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return False
        if clicked is save_btn:
            # Save → the normal save flow (As… first when there is no path);
            # a cancelled folder dialog or failed write aborts the action.
            # WR-01: key the gate on the save RESULT, not on the project dir
            # existing — a save that fails while a project dir is already set
            # (disk full, unwritable) must still abort, never silently
            # discard the unsaved edits.
            return self._save_project()
        return True  # Discard — continue without saving

    def _load_project_session(self, manifest_path: Path) -> None:
        """Rebuild the session from a chapter manifest (D-08).

        The Unsaved-Changes gate runs first. Every page is parsed in
        manifest order into a fully-built ``ImageFile`` (mask/boxes/text/
        translation/geometry/current-image + the D-06 original verification)
        BEFORE anything is swapped — a corrupt file raises and the previous
        session stays byte-identical. On success: sidebar in manifest order,
        the first page displayed from its embedded image (D-05), fresh undo
        history (D-05), the project dir/name recorded, dirty cleared, and
        the open-status transient (with the missing-original append when any
        original failed verification).
        """
        if not self._confirm_discard_changes():
            return
        data = project_io.load_project(manifest_path)
        page_files: list[ImageFile] = []
        for page in data["pages"]:
            page_path = manifest_path.parent / page["file"]
            entries = project_io.load_page_file(page_path)
            parsed = project_io.parse_page_entries(entries)
            page_files.append(
                self._build_image_file_from_parsed(
                    parsed, manifest_path.parent / f"{page['name']}.mas"
                )
            )
        if not page_files:
            # E7 zero-one-many: a manifest with zero pages is corrupt.
            raise project_io.ProjectFormatError("project contains no pages")

        # ---- session swap (everything above succeeded) ----
        self.image_files = page_files
        self.file_table.set_pages([imf.path for imf in page_files])
        self.file_table.select_path(page_files[0].path)
        self._last_page_index = 0
        self._display_page_state(page_files[0])
        self.reset_history()  # D-05: fresh undo on reopen
        self._project_dir = manifest_path.parent
        self._project_name = data["name"]
        for imf in self.image_files:
            imf.dirty = False
        self._update_title()
        self.canvas.fit_to_window()
        self._refresh_status_bar()
        missing = sum(1 for imf in self.image_files if not imf.original_verified)
        status = (
            f"Opened project '{data['name']}' ({len(self.image_files)} pages)."
        )
        if missing:
            status += " Original file not found — using the saved image."
        self._show_transient_status(status)

    def _load_single_page_mas(self, path: Path) -> None:
        """Open a page ``.mas`` as a standalone 1-page session (D-09).

        The page behaves exactly like a normally opened image plus its
        restored mask/boxes/text; Show Original follows the D-06 checksum
        rule; Save Project… on it creates a single-page project (UI-SPEC
        surface 22). The Unsaved-Changes gate runs first.
        """
        if not self._confirm_discard_changes():
            return
        entries = project_io.load_page_file(path)
        parsed = project_io.parse_page_entries(entries)
        imf = self._build_image_file_from_parsed(parsed, path)

        # ---- session swap ----
        self.image_files = [imf]
        self.file_table.set_pages([imf.path])
        self.file_table.select_path(imf.path)
        self._last_page_index = 0
        self._display_page_state(imf)
        self.reset_history()
        self._project_dir = None
        self._project_name = None
        for imf_ in self.image_files:
            imf_.dirty = False
        self._update_title()
        self.canvas.fit_to_window()
        self._refresh_status_bar()

    # --------------------------------------------------- recent projects (D-07)
    def _recent_projects(self) -> list[Path]:
        """QSettings-persisted project dirs (key "recentProjects", max 8).

        Mirrors :meth:`_recent_files`: entries are path-validated and capped
        at ``MAX_RECENT_PROJECTS``. A stale entry whose folder no longer
        holds a ``manifest.json`` is dropped at refresh time (T-05-14
        accepted convenience data).
        """
        raw = self._settings().value("recentProjects", []) or []
        out: list[Path] = []
        for entry in raw:
            try:
                p = Path(entry)
            except (TypeError, ValueError):
                continue
            if (p / "manifest.json").is_file():
                out.append(p)
        return out[:MAX_RECENT_PROJECTS]

    def _add_recent_project(self, project_dir: Path) -> None:
        """Record ``project_dir`` at the top of the Recent Projects list."""
        current = [p for p in self._recent_projects() if p != project_dir]
        current.insert(0, project_dir)
        self._settings().setValue(
            "recentProjects", [str(p) for p in current[:MAX_RECENT_PROJECTS]]
        )
        self._refresh_recent_projects_menu()

    def _clear_recent_projects(self) -> None:
        self._settings().remove("recentProjects")
        self._refresh_recent_projects_menu()

    def _refresh_recent_projects_menu(self) -> None:
        """Rebuild the Recent Projects submenu (UI-SPEC surface 21).

        Empty list → the disabled "No recent projects yet." item; otherwise
        "Project — {folder-name}" entries with the full path in the tooltip,
        capped at 8, plus the always-present Clear Menu action. Entries are
        flagged with the ``recent_project`` property so
        ``_refresh_action_states`` can gate them during async ops.
        """
        self.recent_projects_menu.clear()
        recents = self._recent_projects()
        if not recents:
            placeholder = QAction("No recent projects yet.", self)
            placeholder.setEnabled(False)
            self.recent_projects_menu.addAction(placeholder)
        else:
            for proj in recents:
                act = QAction(f"Project \u2014 {proj.name}", self)
                act.setToolTip(str(proj))
                act.setProperty("recent_project", True)
                act.triggered.connect(self._make_recent_project_opener(proj))
                self.recent_projects_menu.addAction(act)
        self.recent_projects_menu.addSeparator()
        self.recent_projects_menu.addAction(self.action_clear_recent_projects)

    def _make_recent_project_opener(self, project_dir: Path):
        def _open(_checked: bool = False) -> None:
            # Bypass the file dialog; the manifest path routes straight into
            # the session rebuild (UI-SPEC surface 21).
            self._open_project(project_dir / "manifest.json")

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
        # Plan 05-07: the canvas Crop tool's Enter-apply signal funnels into
        # the shared crop apply path (_apply_crop -> _apply_geometry_op).
        self.canvas.crop_committed.connect(self._on_crop_committed)
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
        # G = Crop, the 6th tool (D-11, plan 05-07; free letter per the
        # UI-SPEC shortcut audit).
        for key, tool in (
            ("V", ToolMode.MOVE),
            ("B", ToolMode.BRUSH),
            ("R", ToolMode.RECTANGLE),
            ("L", ToolMode.LASSO),
            ("E", ToolMode.ERASER),
            ("G", ToolMode.CROP),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda _t=tool: self.set_active_tool(_t))

        # Clear Mask (plan 04) — wired to the canvas.
        self.action_clear_mask.triggered.connect(self._on_clear_mask)
        self._refresh_action_states()

    # ------------------------------------------------------ history (plan 06)
    def _wire_history_actions(self) -> None:
        """Connect the HistoryManager + the two unified undo/redo actions +
        shortcuts (Surface 13, plan 03-05).

        Reimplemented patterned after MangaCleaner_GPU ``main_window.py:110``
        (mask_changed -> push_mask_state) and ``168-171`` (QShortcut Ctrl+Z /
        Ctrl+Shift+Z). The Phase 1 four-action surface (image/mask split plus
        the legacy Alt-modifier Z pair) is GONE — Surface 13 collapses it to a
        single unified Ctrl+Z over the merged MASK/IMAGE/BOXES timeline
        (plan 03-02's HistoryManager.undo/redo). D-12 reference-only.

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
        # Boxes push hook (CR-01 fix): boxes_modified -> push a BOXES snapshot.
        # Sibling of the mask hook — mirrors _on_mask_modified / _on_boxes_modified.
        self.canvas.boxes_modified.connect(self._on_boxes_modified)

        # Plan 05-05 (D-07) dirty tracking: the SAME mutation signals mark
        # the session dirty (the plan-05-05 save layer). The OCR +
        # Inspector commit handlers emit boxes_modified, so this single
        # connection covers box/text/translation/bubble edits too; restore
        # paths are excluded via the _suppress_boxes_push guard inside
        # _set_session_dirty.
        self.canvas.mask_modified.connect(self._set_session_dirty)
        self.canvas.boxes_modified.connect(self._set_session_dirty)

        # Plan 04-04 Inspector wiring (D-08). The Inspector is a FOLLOWER — it
        # subscribes to the scene's selectionChanged so load_box fires on every
        # selection change, and its field-commit signals route to the commit
        # handlers that mutate the selected pagebox through the Plan 01 setters,
        # push a BOXES snapshot, and refresh the on-canvas overlay.
        self.canvas.scene().selectionChanged.connect(self._on_canvas_selection_changed)
        self.inspector_panel.connect_commit_handlers(
            on_recognized=self._on_inspector_recognized_committed,
            on_translation=self._on_inspector_translation_committed,
            on_bubble=self._on_inspector_bubble_committed,
            on_vertical=self._on_inspector_vertical_committed,
            # Plan 07-05 (D-05/D-10): the Style-section commits route through
            # the ONE apply-to-all snapshot machinery (D-10).
            on_style_font=self._on_inspector_style_font_committed,
            on_style_font_style=self._on_inspector_style_font_style_committed,
            on_style_size=self._on_inspector_style_size_committed,
            on_style_auto_fit=self._on_inspector_style_auto_fit_committed,
            on_style_color=self._on_inspector_style_color_committed,
            on_style_align=self._on_inspector_style_align_committed,
            on_style_effect=self._on_inspector_style_effect_committed,
        )
        # G-07-3 (plan 07-11): the Set-as-Default affordance -> the
        # 'defaultFontFamily' writer (the QSettings persistence chain).
        self.inspector_panel.default_font_requested.connect(
            self._on_inspector_default_font_requested
        )

        # Edit-menu actions -> the two unified handlers.
        self.action_undo.triggered.connect(self.on_undo)
        self.action_redo.triggered.connect(self.on_redo)

        # Application-wide QShortcuts (MangaCleaner_GPU main_window.py:168-171
        # pattern, reimplemented). The Edit-menu action shortcuts may be
        # shadowed by the canvas's keyPressEvent when the canvas has focus; the
        # QShortcut on the MainWindow is the robust path. Surface 13: the legacy
        # Alt-modifier Z mask-undo shortcuts are REMOVED (subsumed by the unified
        # Ctrl+Z); Ctrl+Z/Ctrl+Shift+Z are repointed to the unified
        # on_undo/on_redo handlers.
        for keys, slot in (
            (QKeySequence("Ctrl+Z"), self.on_undo),
            (QKeySequence("Ctrl+Shift+Z"), self.on_redo),
        ):
            sc = QShortcut(keys, self)
            sc.activated.connect(slot)

        self._update_undo_redo_actions()

    def reset_history(self) -> None:
        """Replace the HistoryManager with a fresh instance.

        Called on page change (``on_page_selected``) so undo never crosses
        page boundaries (UI-SPEC surface 8; MangaCleaner_GPU
        main_window.py:347 pattern — ``self.history = HistoryManager(...)`` on
        file open). Also refreshes the undo/redo button enable state. Clears
        the per-page mask-baseline-seeded sentinel (plan 03-08) so the first
        stroke of the new page re-seeds its clean baseline.
        """
        self.history = HistoryManager(limit=20)
        self._pre_stroke_mask = None
        self._update_undo_redo_actions()

    def _on_mask_modified(self) -> None:
        """Mask push hook: a stroke committed -> push the PRE-stroke state.

        ``push_mask_state`` ``.copy()``-detaches internally (Pitfall 2), so
        passing the live ``canvas.get_mask()`` here is safe. The hook is the
        ONLY mask push path; ``on_undo`` applies mask snapshots via
        ``canvas.apply_undo_mask`` (no re-emission).

        Plan 03-08 (FLOW-02 regression / UAT test 3 addendum): the push
        convention is the mask BEFORE-state (the state to restore to on undo),
        mirroring the IMAGE side's pre-edit push contract (each
        ``push_image_action`` "records the PRE-edit region so undo restores
        it") and plan 03-07's BOXES before-state discipline. The pre-fix code
        pushed the AFTER-state (``canvas.get_mask()`` post-stroke), which made
        ``pop_mask_undo`` return the after-state itself — a no-op that left the
        stroke on the canvas and, after an inpaint interleaving, made the brush
        appear "stuck" on the 2nd Ctrl+Z.

        The before-state of stroke N is the mask as it was BEFORE stroke N
        began = the after-state of stroke N-1. Because this hook fires AFTER
        the stroke is painted (canvas ``_end_paint`` paints then emits), the
        before-state cannot be read from ``canvas.get_mask()`` (that is the
        post-stroke state); instead it is reconstructed as the previous
        stroke's after-state, tracked in ``self._pre_stroke_mask``. For the
        FIRST stroke of a per-page session there is no previous after-state,
        so the before-state is a clean/empty mask of the current size/format
        (the user's mental model: "undo my brush work -> clean canvas"). After
        pushing the before-state, ``_pre_stroke_mask`` is refreshed to the
        current (post-stroke) mask so the next stroke's before-state is this
        stroke's after-state.

        Result: mask stack after stroke 1 = [clean]; undo pops clean -> stroke
        gone. After stroke 2 = [clean, after_1]; undo pops after_1 -> stroke 2
        gone; undo pops clean -> stroke 1 gone. This is exactly parallel to how
        plan 03-07 lets the first box edit push against the detection baseline.
        """
        if self.history is None or not self.canvas.has_mask():
            return
        current = self.canvas.get_mask()
        if self._pre_stroke_mask is None:
            # First stroke of the per-page session: the before-state is a clean
            # baseline (the canvas as it was before any stroke). Same size/
            # format as the live mask so apply_undo_mask can swap it in.
            before = QImage(current.size(), current.format())
            before.fill(Qt.GlobalColor.transparent)
        else:
            before = self._pre_stroke_mask
        self.history.push_mask_state(before)
        # Track this stroke's after-state as the next stroke's before-state.
        self._pre_stroke_mask = current.copy()
        self._update_undo_redo_actions()

    def _on_boxes_modified(self, before_snapshot) -> None:
        """Box-edit push hook (CR-01 fix): a box create/move/resize/delete
        committed -> push the PRE-edit snapshot onto the BOXES undo stack
        (Surface 13 / D-10).

        ``before_snapshot`` is the layer state the canvas captured BEFORE the
        mutation (passed as the ``boxes_modified`` payload). The history's pop
        returns the most-recently-pushed checkpoint (LIFO), so for the edit to
        be undoable in ONE Ctrl+Z the pushed snapshot must be the BEFORE state
        — the state to restore to (mirrors the image side's pre-edit push
        contract: history_manager "Each push records the PRE-edit region so
        undo restores it"). ``boxes_snapshot()`` already materializes fresh
        int-Box PageBoxes (Pitfall 3 + 6), so the payload is detached from the
        live BoxItems.

        Suppressed during an undo/redo restore and during detection's /
        page-switch's set_boxes (``apply_undo_boxes`` /
        ``_build_detected_boxes`` / ``on_page_selected`` set
        ``_suppress_boxes_push``) so a restore via set_boxes — which emits
        boxes_modified for the canvas-internal refresh — does NOT re-push and
        corrupt the redo stack. This is the box analogue of mask's
        ``test_undo_does_not_repush`` regression guard.
        """
        if self.history is None or self._suppress_boxes_push:
            return
        # Plan 07-02 (D-09): consume the pending group-op name BEFORE pushing
        # (06-WR-01 pattern — recorded at push time so the Ctrl+Z flash names
        # the group op). The group flash copy per UI-SPEC surface 32:
        # "Moved {n} boxes — press Ctrl+Z to undo." / "Deleted {n} boxes —
        # press Ctrl+Z to restore.". Single-box ops set no pending name, so
        # they stay silent (Phase 3) and keep the generic undo label.
        op_name = self.canvas.take_pending_boxes_op_name()
        if op_name is not None:
            self._last_boxes_op_name = op_name
            if op_name.startswith("Deleted"):
                self._show_transient_status(
                    f"{op_name} — press Ctrl+Z to restore."
                )
            else:
                self._show_transient_status(f"{op_name} — press Ctrl+Z to undo.")
        else:
            self._last_boxes_op_name = None
        self.history.push_boxes_state(before_snapshot)
        self._update_undo_redo_actions()
        # WR-05: keep the Inspector in sync — an inline-edit commit refreshes
        # the BoxItem overlay + badge but NOT the property panel, so the
        # always-present view (D-08) goes stale while the box stays selected.
        # Re-populate from the still-selected box (also covers canvas box
        # create/move/resize commits). load_box blocks signals during
        # population, so no commit loop is possible. Multi-aware since plan
        # 07-05 (D-10): a group move/style commit reloads the Mixed state.
        self._on_canvas_selection_changed()

    # ----------------------------------------------------- plan 04-04 Inspector
    def _on_canvas_selection_changed(self) -> None:
        """Inspector selection-follower (D-08/D-10): load the selection.

        Subscribed to the scene's ``selectionChanged``. A single selected box
        populates the panel from its pagebox (the Phase 4 behavior — the
        styling section shows the box's own flat style, D-06); a MULTI-
        selection (D-10) populates the common-value/Mixed state via
        ``load_multi_selection`` (per-box text fields disable; the styling
        section edits ALL selected); no selection shows the empty-state copy.
        The Inspector never drives canvas selection — it is a property-editor
        follower (UI-SPEC §18).
        """
        selected = self._selected_box_items()
        if not selected:
            self.inspector_panel.clear()
        elif len(selected) == 1:
            item = selected[0]
            self.inspector_panel.load_box(
                item.pagebox,
                rendered_size_px=self._overlay_rendered_size(item),
            )
        else:
            self.inspector_panel.load_multi_selection(
                [it.pagebox for it in selected]
            )

    def _overlay_rendered_size(self, item) -> float | None:
        """The item's cached renderer auto-fit size (the Auto-fit uncheck hint).

        ``used_font_size_px`` is the shared renderer's resolved size (the
        manual size or the auto-fit loop's final target) — the exact "current
        rendered size" D-15 wants as the manual-start value.
        """
        lr = item._text_overlay.layout_result
        if lr is not None and lr.used_font_size_px > 0:
            return float(lr.used_font_size_px)
        return None

    def _inspector_commit_pre(self) -> "BoxItem | None":
        """Capture the PRE-edit snapshot + the selected item for an Inspector commit.

        Returns the selected BoxItem, or None if no box is selected (a stale
        commit is dropped). Mirrors the box-side pre-edit push contract: the
        BOXES stack pops the most-recent checkpoint first, so the pushed
        snapshot must be the BEFORE state for a single-Ctrl+Z undo.

        CR-01: ``boxes_snapshot()`` materializes fresh int-Box PageBoxes but
        shares the live ``TextBlock`` payload by reference, and the commit
        handlers mutate that shared payload in place via the setters BEFORE
        ``boxes_modified`` reaches ``history.push_boxes_state`` (whose
        ``PageBox.copy()`` runs at push time — AFTER the mutation). Detach the
        payloads here so the pushed snapshot captures the PRE-edit text and
        undo restores it (Pitfall 8 push-side; mirrors ``InlineEditor.commit``
        and ``_apply_translations``).
        """
        item = self.canvas._selected_box()
        if item is None:
            return None
        before = self.canvas.boxes_snapshot()
        for pb in before:
            if pb.payload is not None:
                pb.payload = copy.copy(pb.payload)
        self._boxes_interaction_start_snapshot = before
        return item

    def _inspector_commit_post(self, item: "BoxItem") -> None:
        """Push the pre-edit snapshot, refresh the overlay + badge, re-load the panel.

        Called after every Inspector field commit. Emits ``boxes_modified`` with
        the BEFORE snapshot (captured in :meth:`_inspector_commit_pre`) so the
        BOXES-stack push hook records the state to restore to on undo; refreshes
        the BoxItem's text overlay + badge so the canvas reflects the edit
        immediately; and re-loads the Inspector so its fields stay in sync.
        """
        item.refresh_text_overlay()
        item.refresh_badge()
        # boxes_modified -> _on_boxes_modified pushes the BEFORE snapshot.
        self.canvas.boxes_modified.emit(self._boxes_interaction_start_snapshot)
        self.inspector_panel.load_box(item.pagebox)

    # ------------------------------------------- plan 07-05 style commits (D-10)
    # The D-05 styling signals route through ONE apply-to-all commit:
    # `_inspector_style_commit` captures ONE before-snapshot (the full
    # boxes_snapshot() — which forwards `style` into the fresh PageBoxes),
    # applies the change to EVERY selected PageBox via `dataclasses.replace`
    # (a FRESH TextStyle — never in-place mutation, Pitfall 1), records the
    # op name "style change" (06-WR-01), refreshes every selected overlay +
    # badge, emits `boxes_modified` ONCE, and re-loads the multi-aware panel.
    # One Ctrl+Z reverses the whole commit (D-10 / surface 13).

    def _selected_box_items(self) -> list:
        """Every selected BoxItem in canvas order (the D-10 target set)."""
        return [it for it in self.canvas._box_items if it.isSelected()]

    def _inspector_style_commit(self, apply_fn) -> None:
        """ONE style commit applied to EVERY selected box (D-10).

        ``apply_fn(item)`` mutates ``item.pagebox`` (via the style helpers
        below — always assigning a fresh ``TextStyle``). Captures ONE
        before-snapshot with DETACHED payloads (Pitfall 8 push-side), records
        the "style change" op name, refreshes each selected overlay exactly
        once, emits ``boxes_modified`` ONCE, and re-loads the panel
        (multi-aware — a Mixed selection reloads as the now-uniform values).
        """
        selected = self._selected_box_items()
        if not selected:
            return
        before = self.canvas.boxes_snapshot()
        for pb in before:
            if pb.payload is not None:
                pb.payload = copy.copy(pb.payload)
        self._boxes_interaction_start_snapshot = before
        for item in selected:
            apply_fn(item)
        self.canvas.set_pending_boxes_op_name("style change")
        for item in selected:
            item.refresh_text_overlay()
            item.refresh_badge()
        self.canvas.boxes_modified.emit(before)
        self._on_canvas_selection_changed()

    def _replace_style(self, pb, **changes) -> None:
        """Assign a FRESH ``TextStyle`` via ``dataclasses.replace`` (Pitfall 1)."""
        style = pb.style if pb.style is not None else TextStyle()
        pb.style = dreplace(style, **changes)

    def _replace_effect(self, pb, key: str, changes: dict) -> None:
        """Assign a fresh ``TextStyle`` with ONE effect dict replaced (Pitfall 1).

        WR-02 (07-REVIEW): ``changes["enabled"]`` may be ``None`` — the
        "leave enabled alone" sentinel a value/color-only commit on a MIXED
        effect row carries (the tri-state checkbox cannot express it). When
        None, each box's OWN enabled state is preserved instead of forcing
        every box to the same flag; the sentinel never lands in a ``TextStyle``
        (Pitfall 7).
        """
        style = pb.style if pb.style is not None else TextStyle()
        effect = dict(getattr(style, key))
        if changes.get("enabled") is not None:
            effect["enabled"] = bool(changes["enabled"])
        effect["color"] = str(changes["color"])
        value = float(changes["value"])
        if key == "outline":
            effect["width_px"] = value
        elif key == "glow":
            effect["radius_px"] = value
        else:  # shadow — the UI offset spin maps to radius + dx + dy
            effect["radius_px"] = value
            effect["dx"] = value
            effect["dy"] = value
        pb.style = dreplace(style, **{key: effect})

    def _replace_align(self, pb, *, align_h=None, align_v=None) -> None:
        """Assign a fresh ``TextStyle`` with ONLY the changed align axes (G-07-7).

        The align-Mixed override's commit carries ``None`` for an untouched
        axis (the panel's sentinel->None translation — the ``_effect_payload``
        mirror); ``None`` axes are SKIPPED so every box keeps its OWN value on
        that axis (the WR-02 ``_replace_effect`` per-key preservation model).
        A both-None call is a no-op (defensive — the panel's per-axis WR-01
        guard already prevents it).
        """
        changes: dict = {}
        if align_h is not None:
            changes["align_h"] = align_h
        if align_v is not None:
            changes["align_v"] = align_v
        if changes:
            self._replace_style(pb, **changes)

    def _style_rendered_size(self, item) -> float:
        """The box's CURRENT rendered font size (A11 — renderer.layout's
        auto-fit result; the box's own manual size when it has one)."""
        pb = item.pagebox
        style = pb.style if pb.style is not None else TextStyle()
        if style.font_size_px is not None and not style.auto_fit:
            return float(style.font_size_px)
        text = current_focus_text(pb)
        if not text:
            return 14.0  # the auto-fit base (nothing renders — the size is moot)
        # G-07-1: the render vertical flag is bool(style.vertical) ONLY —
        # payload.vertical is pure export metadata, never a render
        # instruction — the SAME single expression
        # box_item.refresh_text_overlay and text_renderer.bake_typeset_page
        # use (no divergence window).
        vertical = bool(style.vertical)
        result = renderer_layout(text, style, item.rect(), vertical=vertical)
        return float(result.used_font_size_px)

    def _on_inspector_style_font_committed(self, family: str) -> None:
        self._inspector_style_commit(
            lambda item: self._replace_style(item.pagebox, font_family=family)
        )

    def _on_inspector_style_font_style_committed(self, style_name: str) -> None:
        bold, italic = _FONT_STYLE_FLAGS.get(style_name, (False, False))
        self._inspector_style_commit(
            lambda item: self._replace_style(item.pagebox, bold=bold, italic=italic)
        )

    def _on_inspector_style_size_committed(self, size: int) -> None:
        if size <= 0:
            # 0 = the "Auto" sentinel (D-15): back to the fit-in-box mode.
            self._inspector_style_commit(
                lambda item: self._replace_style(
                    item.pagebox, auto_fit=True, font_size_px=None
                )
            )
        else:
            self._inspector_style_commit(
                lambda item: self._replace_style(
                    item.pagebox, auto_fit=False, font_size_px=float(size)
                )
            )

    def _on_inspector_style_auto_fit_committed(self, checked: bool) -> None:
        if checked:
            self._inspector_style_commit(
                lambda item: self._replace_style(
                    item.pagebox, auto_fit=True, font_size_px=None
                )
            )
        else:
            # The uncheck converts to MANUAL at the current rendered size
            # (A11 — the renderer's auto-fit result; D-15).
            self._inspector_style_commit(
                lambda item: self._replace_style(
                    item.pagebox,
                    auto_fit=False,
                    font_size_px=self._style_rendered_size(item),
                )
            )

    def _on_inspector_style_color_committed(self, color_hex: str) -> None:
        self._inspector_style_commit(
            lambda item: self._replace_style(item.pagebox, color=color_hex)
        )

    def _on_inspector_style_align_committed(self, h, v) -> None:
        # G-07-7: h/v are model values with None = the untouched axis on a
        # Mixed selection — _replace_align preserves each box's own value on
        # the None axes (never a both-axes overwrite).
        self._inspector_style_commit(
            lambda item: self._replace_align(item.pagebox, align_h=h, align_v=v)
        )

    def _on_inspector_style_effect_committed(self, key: str, changes: dict) -> None:
        self._inspector_style_commit(
            lambda item: self._replace_effect(item.pagebox, key, changes)
        )

    def _on_inspector_default_font_requested(self, family: str) -> None:
        """G-07-3: persist the Set-as-Default family + flash the status.

        The writer end of the 'defaultFontFamily' chain — the SAME
        ``_settings()`` store as the recents (the convention is reused, not
        duplicated). The family originates from the Inspector's QFontComboBox
        real family list, never free text (T-07-18). Existing boxes are never
        re-styled (D-06 flat per-box) — the default applies to NEW boxes only.
        """
        self._settings().setValue("defaultFontFamily", family)
        self._show_transient_status(f"Default font: {family}")

    # ------------------------------------------------- font-size actions (D-16)
    def _on_font_size_delta(self, delta: int) -> None:
        """Increase/Decrease Font Size (Ctrl+] / Ctrl+[, ±1 px — D-16).

        Applies the delta to EVERY selected box in ONE snapshot (op name
        "font size", 06-WR-01): ONE before-snapshot, ONE overlay refresh,
        ONE ``boxes_modified`` emission — one Ctrl+Z reverses the whole
        commit. An Auto-fit box FIRST converts to MANUAL at its current
        rendered size (A11 — ``renderer.layout``'s auto-fit result), then the
        delta applies (floor at 1 px). Every change assigns a FRESH
        ``TextStyle`` (Pitfall 1 — never in-place mutation).
        """
        if self._op_running or self._current_page_index() is None:
            return
        selected = self._selected_box_items()
        if not selected:
            return
        before = self.canvas.boxes_snapshot()
        for pb in before:
            if pb.payload is not None:
                pb.payload = copy.copy(pb.payload)
        self._boxes_interaction_start_snapshot = before
        for item in selected:
            style = (
                item.pagebox.style if item.pagebox.style is not None else TextStyle()
            )
            if style.auto_fit or style.font_size_px is None:
                # A11: convert to MANUAL at the current rendered size first.
                style = dreplace(
                    style,
                    auto_fit=False,
                    font_size_px=self._style_rendered_size(item),
                )
            current = float(style.font_size_px or 1.0)
            item.pagebox.style = dreplace(
                style, font_size_px=max(1.0, current + delta)
            )
        self.canvas.set_pending_boxes_op_name("font size")
        for item in selected:
            item.refresh_text_overlay()
            item.refresh_badge()
        self.canvas.boxes_modified.emit(before)
        self._on_canvas_selection_changed()

    def _on_inspector_recognized_committed(self, text: str) -> None:
        """Recognized-field commit -> set_recognized_text_edited (D-04, Plan 01 setter).

        Routes the manual edit through the CENTRALIZED manual-edit setter (sets
        ``edited=True`` so a re-OCR must prompt). NOT ``set_recognized_text``
        (OCR-write, ``edited=False``) and NOT a direct ``payload.text`` write
        (bypasses the payload-None guard). Safe on a never-OCR'd box (the
        setter lazily constructs the payload).
        """
        item = self._inspector_commit_pre()
        if item is None:
            return
        item.pagebox.set_recognized_text_edited(text)
        self._inspector_commit_post(item)

    def _on_inspector_translation_committed(self, text: str) -> None:
        """Translation-field commit -> set_translation (the D-13 MT seam, Plan 01 setter)."""
        item = self._inspector_commit_pre()
        if item is None:
            return
        item.pagebox.set_translation(text)
        self._inspector_commit_post(item)

    def _on_inspector_bubble_committed(self, number: int) -> None:
        """Bubble # commit -> write bubble_no + set manual_override=True (D-16).

        A manual bubble-number sets the manual-override flag so a page-level
        re-auto (Plan 04-07) preserves the user's hand-set number (the amber
        badge border). The bounded QSpinBox is 0..9999 (T-4-08) with 0 as the
        UNSET sentinel — a 0 commit CLEARS the number (bubble_no=None, no
        override pin: unset is not an override); 1..9999 assigns and pins
        manual_override (D-16 unchanged).
        """
        item = self._inspector_commit_pre()
        if item is None:
            return
        if number == 0:
            item.pagebox.bubble_no = None
            item.pagebox.manual_override = False
        else:
            item.pagebox.bubble_no = number
            item.pagebox.manual_override = True
        self._inspector_commit_post(item)

    def _on_inspector_vertical_committed(self, vertical: bool) -> None:
        """Vertical checkbox -> write ``style.vertical`` on EVERY selected box
        (G-07-1/D-10 — one commit, ONE snapshot) + re-render the overlays.

        The overlay + bake + size probe read the single ``bool(style.vertical)``
        flag (``box_item.refresh_text_overlay`` /
        ``text_renderer.bake_typeset_page`` / ``_style_rendered_size`` — the
        SAME expression, atomic canvas ≡ bake flip), so this commit switches
        the canvas + bake to the renderer's tategaki path immediately
        (Pitfall 9 — a toggle must re-render, not just write metadata).
        Records the "style change" op name (every style commit incl. the
        vertical toggle, D-10/surface 13).

        The toggle never touches the payload (G-07-1): a never-OCR'd box's
        payload stays None — the checkbox is a STYLE control, and the
        payload's `vertical` field is pure export metadata written only by
        the exporter/detector paths.
        """
        selected = self._selected_box_items()
        if not selected:
            return
        before = self.canvas.boxes_snapshot()
        for pb in before:
            if pb.payload is not None:
                pb.payload = copy.copy(pb.payload)
        self._boxes_interaction_start_snapshot = before
        for item in selected:
            self._replace_style(item.pagebox, vertical=vertical)
        self.canvas.set_pending_boxes_op_name("style change")
        for item in selected:
            item.refresh_text_overlay()
            item.refresh_badge()
        self.canvas.boxes_modified.emit(before)
        self._on_canvas_selection_changed()

    # ----------------------------------------------------- unified undo/redo
    # Surface 13 (plan 03-05): the unified Ctrl+Z / Ctrl+Shift+Z pop the
    # merged MASK/IMAGE/BOXES timeline (plan 03-02's HistoryManager.undo/redo)
    # and route the (kind, value) results to the matching apply methods. After
    # applying, the status bar shows a transient "Undo: {op}" / "Redo: {op}"
    # message naming the op type (UI-SPEC §Copywriting — the which-stack-was-
    # popped indication the unified timeline requires; T-03-09 mitigation).
    #
    # Plan 05-04 (PROJ-04 / UI-SPEC surface 28): undo()/redo() now return a
    # LIST of (kind, value) pairs — a geometry record (push_geometry_state)
    # pops image+mask+boxes together with ONE press, "never two"; the op-name
    # set extends with rotate/crop/curves/resize (06-05: 'levels' superseded).

    def _undo_op_label(self, kind_or_op: str) -> str:
        """Map the popped kind / geometry-op name to the §Copywriting op label.

        The Phase 3 set (mask edit / inpaint / box edit) extends with the four
        image-op names — rotate / crop / curves / resize — per the UI-SPEC
        surface 28 undo-feedback row (D-14), so a geometry-record undo flashes
        e.g. "Undo: rotate".

        Plan 07-02 (D-09): the group-op names ("Moved {n} boxes" / "Deleted
        {n} boxes") pass through verbatim — the recorded op name IS the label
        (surface 13 extended op set).
        """
        if kind_or_op.startswith(("Moved ", "Deleted ")):
            return kind_or_op
        if kind_or_op in ("style change", "font size"):
            # Plan 07-05 (D-10/D-16): the recorded style-op names ARE the
            # labels (surface 13 extended op set — "Undo: style change").
            return kind_or_op
        if kind_or_op in ("rotate", "crop", "curves", "resize"):
            return kind_or_op
        if kind_or_op == "mask":
            return "mask edit"
        if kind_or_op == "image":
            return "inpaint"
        if kind_or_op == "boxes":
            return "box edit"
        return "edit"

    def _record_geometry_op_name(self, op_name: str) -> None:
        """Record the most recent geometry-op name for the Undo/Redo flash.

        Called by the geometry-op apply path (plan 05-06/05-07
        ``_apply_geometry_op``) immediately before
        ``history.push_geometry_state(...)``. When the unified undo/redo pop
        returns a multi-kind geometry record, the transient flashes
        "Undo: {op_name}" / "Redo: {op_name}" — the extended op-name set
        (rotate|crop|curves|resize, UI-SPEC surface 28).
        """
        self._last_geometry_op_name = op_name

    def _undo_op_label_for_result(self, result) -> str:
        """Resolve the 'Undo: {op}'/'Redo: {op}' label for a pop result list.

        Plan 05-04: ``history.undo``/``redo`` return a LIST of (kind, value)
        pairs. A geometry record pops as a MULTI-kind list (image+mask+boxes
        share one stamp) — the op name was recorded at push time by the
        geometry apply path (``_record_geometry_op_name``). Ordinary
        single-store pops keep the Phase 3 kind-based labels.

        WR-01 (06-VERIFICATION truth 26 / UI-SPEC surface 28): a geometry-free
        op (``curves`` — D-15) pushes an IMAGE-ONLY record
        (``push_geometry_state`` stores the full-frame patch at (0, 0) with
        mask/boxes None), so its pop is a ONE-element list and the multi-kind
        branch above never fires. The single-entry image branch below therefore
        also prefers the recorded op name — but ONLY for full-frame (0, 0)
        entries, the geometry-record shape (history_manager.py:435). An
        ordinary bbox inpaint patch (non-origin, ``push_image_action``) keeps
        the kind-based 'inpaint' label even while a stale geometry-op name is
        recorded (T-06-11: the (0, 0) gate scopes the override).

        Accepted limitation: after TWO consecutive image-only geometry ops,
        the second undo labels by the LAST recorded op name (both pops are
        single (0, 0) image entries and ``_last_geometry_op_name`` holds the
        second op's name) — the stamp-based robust resolution is out of gap
        scope; the code review's minimal fix is the prescribed shape.
        """
        if len(result) > 1:
            return self._undo_op_label(
                self._last_geometry_op_name or "edit"
            )
        kind, value = result[0]
        if kind == "image" and self._last_geometry_op_name is not None:
            x, y, _patch = value
            if (x, y) == (0, 0):
                # Single-entry geometry record — curves pushes image-only, so
                # the (0,0) full-frame shape identifies it; prefer the
                # recorded op name over the kind-based 'inpaint' fallback.
                return self._undo_op_label(self._last_geometry_op_name)
        if kind == "boxes" and self._last_boxes_op_name is not None:
            # Plan 07-02 (D-09): a group move/delete pushes ONE ordinary
            # single-kind BOXES entry — prefer the recorded group-op name so
            # the flash reads "Undo: Moved 3 boxes" / "Undo: Deleted 2 boxes"
            # instead of the generic "box edit" (06-WR-01 pattern).
            return self._undo_op_label(self._last_boxes_op_name)
        return self._undo_op_label(kind)

    def _current_undo_state(self):
        """Gather the (current_mask, current_img, current_boxes) tuple the
        unified ``history.undo``/``redo`` consume.

        Returns ``(None, None, [])`` if no page is loaded — the unified pop
        will then return None (all stacks empty OR no current state to swap).
        """
        if self._current_page_index() is None:
            return None, None, []
        current_mask = self.canvas.get_mask() if self.canvas.has_mask() else None
        # image: only meaningful if the canvas has one; pop_image_undo slices
        # current_img[y:y+h, x:x+w] so a real array is required when image is
        # the popped candidate. Pass None when no image is loaded — the unified
        # pop returns None before delegating if image is empty (no entry to pop).
        current_img = self.canvas.get_image_numpy()
        current_boxes = (
            self.canvas.boxes_snapshot() if self.canvas.has_boxes() else []
        )
        return current_mask, current_img, current_boxes

    def on_undo(self) -> None:
        """Ctrl+Z — pop the most-recent entry (or geometry group) and apply.

        Surface 13 unified handler. Calls ``history.undo(...)`` which delegates
        to the matching per-type pops and returns a LIST of ``(kind, value)``
        pairs — one per store popped (plan 05-04: a geometry record pops
        image+mask+boxes together, "one press per op, never two"; ordinary
        edits pop a one-element list). Routes each ``kind`` to
        ``apply_undo_mask`` / ``apply_undo_image`` / ``apply_undo_boxes``.
        Emits the transient "Undo: {op}" status feedback.
        """
        if self.history is None:
            return
        current_mask, current_img, current_boxes = self._current_undo_state()
        result = self.history.undo(current_mask, current_img, current_boxes)
        if not result:
            self._update_undo_redo_actions()
            return
        self._apply_undo_result(result)
        self._show_transient_status(f"Undo: {self._undo_op_label_for_result(result)}")
        self._update_undo_redo_actions()

    def on_redo(self) -> None:
        """Ctrl+Shift+Z — redo the most-recently-undone entry (unified)."""
        if self.history is None:
            return
        current_mask, current_img, current_boxes = self._current_undo_state()
        result = self.history.redo(current_mask, current_img, current_boxes)
        if not result:
            self._update_undo_redo_actions()
            return
        self._apply_undo_result(result)
        self._show_transient_status(f"Redo: {self._undo_op_label_for_result(result)}")
        self._update_undo_redo_actions()

    def _apply_undo_result(self, result) -> None:
        """Route a LIST of (kind, value) pop results to the canvas applies.

        Plan 05-04: ``history.undo``/``redo`` return ``list[(kind, value)]`` —
        one entry per popped store (a geometry record pops image+mask+boxes
        together). Each kind applies exactly as before (apply_undo_image /
        apply_undo_mask / apply_undo_boxes — each refreshes its own canvas
        layer, so the whole op renders in one pass, never two), in
        image→mask→boxes order. Entries with a None value (empty-store guards)
        are skipped, as before.
        """
        entries = {kind: value for kind, value in result}
        for kind in ("image", "mask", "boxes"):
            value = entries.get(kind)
            if value is None:
                continue
            if kind == "image":
                # value is an (x, y, patch) tuple — a geometry entry is a
                # full-frame patch at (0, 0), bounds-checked by the canvas
                # (canvas.py:522-565 handles full-frame).
                x, y, patch = value
                self.canvas.apply_undo_image(x, y, patch)
                # CR-01 companion: undo changes the displayed image, so keep
                # ImageFile.current_image authoritative (the same write-back
                # rule as the op apply path) — otherwise navigation/save
                # after Ctrl+Z resurrects the undone state.
                idx = self._current_page_index()
                if idx is not None and 0 <= idx < len(self.image_files):
                    current_img = self.canvas.get_image_numpy()
                    if current_img is not None:
                        self.image_files[idx].current_image = current_img
            elif kind == "mask":
                # value is a QImage snapshot (or None if the stack was empty).
                self.canvas.apply_undo_mask(value)
            elif kind == "boxes":
                # value is a list of PageBox (or None).
                self.apply_undo_boxes(value)

    def apply_undo_boxes(self, boxes_snapshot_list) -> None:
        """Restore a boxes snapshot from the history (Surface 13 BOXES apply).

        Mirrors ``apply_undo_mask`` / ``apply_undo_image``: rebuilds the box
        layer from the snapshot via ``set_boxes``, splitting by origin (the
        snapshot preserved origin per item — plan 03-03's boxes_snapshot).

        WR-05 guard: ``set_boxes`` always emits ``boxes_modified`` (for the
        canvas-internal refresh). Because the BOXES push hook is now wired to
        ``boxes_modified`` (CR-01 fix), a restore would re-push the restored
        state and clear redo unless suppressed. The ``_suppress_boxes_push``
        guard wraps BOTH set_boxes calls (the empty-list restore and the
        split-origin restore) so a pop is a pure restore, never a push (the
        box analogue of mask's ``test_undo_does_not_repush``).
        """
        # Suppress the boxes_modified -> push hook for the duration of the
        # restore (set_boxes emits at its tail).
        self._suppress_boxes_push = True
        try:
            if not boxes_snapshot_list:
                # Empty snapshot = restore the empty-boxes state (clear layer).
                self.canvas.set_boxes([], [])
                return
            user_pbs = [pb for pb in boxes_snapshot_list if pb.origin == USER]
            detected_pbs = [pb for pb in boxes_snapshot_list if pb.origin == DETECTED]
            self.canvas.set_boxes(user_pbs, detected_pbs)
        finally:
            self._suppress_boxes_push = False

    def _show_transient_status(self, message: str) -> None:
        """Show ``message`` in status_bar_left for ~3 s, then revert to the
        idle status (UI-SPEC §Copywriting — transient undo/redo feedback).

        The revert target is the canonical box-count status (the same text
        ``_refresh_status_bar`` would render). A single QTimer is reused —
        each new transient message restarts it.
        """
        self.status_bar_left.setText(message)
        if not hasattr(self, "_status_revert_timer") or self._status_revert_timer is None:
            self._status_revert_timer = QTimer(self)
            self._status_revert_timer.setSingleShot(True)
            self._status_revert_timer.timeout.connect(self._revert_status_bar)
        # Capture the revert target NOW (before any later state change) so the
        # timer fires against the post-undo state, not whatever is current at
        # fire-time.
        self._status_revert_target = self._idle_status_text()
        self._status_revert_timer.start(3000)

    def _revert_status_bar(self) -> None:
        """Revert status_bar_left to the idle box-count status (QTimer slot)."""
        target = getattr(self, "_status_revert_target", None)
        if target is None:
            target = self._idle_status_text()
        self.status_bar_left.setText(target)

    def _idle_status_text(self) -> str:
        """Return the idle status-bar-left text (box count when a page is open
        with boxes; 'No page open' otherwise). Mirrors UI-SPEC §Copywriting."""
        if self._current_page_index() is None:
            return "No page open"
        if self.canvas.has_boxes():
            detected, user = self.canvas.box_origin_counts()
            return (
                f"{self.canvas.box_count()} boxes · {detected} detected,"
                f" {user} user"
            )
        return ""

    def _update_undo_redo_actions(self) -> None:
        """Enable/disable the two unified undo/redo actions by the UNION flags.

        Surface 13 (plan 03-05): each action is enabled iff (a) a page is open
        AND (b) the matching union flag (``can_undo``/``can_redo`` over all
        three stacks) is True. Called after every push/pop and on page change
        (UI-SPEC §13: each button disabled when ALL its stacks are empty).
        """
        if not hasattr(self, "action_undo"):
            return  # not yet built (early init)
        has_page = self._current_page_index() is not None
        history_ready = self.history is not None
        self.action_undo.setEnabled(
            has_page and history_ready and self.history.can_undo()
        )
        self.action_redo.setEnabled(
            has_page and history_ready and self.history.can_redo()
        )

    def _make_tool_toolbar_button(self, action: QAction) -> QToolButton:
        """Build a checkable toolbar tool-button bound to ``action``.

        The button's checked state mirrors its DEFAULT ACTION (QToolButton
        syncs its checkability to the action): the six window tool actions
        are standalone checkable-actions — outside the ToolsPanel's
        exclusive QActionGroup — whose checked state is driven explicitly by
        ``set_active_tool``'s action-sync loop (check the matching action,
        uncheck the other five), so the toolbar stays in sync with the Tools
        dock on every entry path (menu, shortcut, dock click, programmatic).
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

        The six WINDOW tool actions (``action_tool_*``) are standalone
        checkable actions — deliberately outside the ToolsPanel's
        exclusive QActionGroup (WR-02: a 12-action mirrored group fought
        itself on dock clicks). Their checked state is driven explicitly:
        check the matching action and uncheck the other five, with signals
        blocked so no toggled-driven re-emission happens. The toolbar
        QToolButtons mirror their default actions, so the buttons follow.
        """
        self.canvas.set_tool(tool)
        # Sync the ToolsPanel (its actions drive the dock highlight) without
        # re-emitting tool_changed (the canvas is already updated).
        self.tools_panel.set_active_tool(tool)
        # Sync the six window tool actions explicitly: check the matching
        # action and uncheck the other five (signals blocked — the group no
        # longer does this for the window actions).
        for act in (
            self.action_tool_move,
            self.action_tool_brush,
            self.action_tool_rectangle,
            self.action_tool_lasso,
            self.action_tool_eraser,
            self.action_tool_crop,
        ):
            was = act.blockSignals(True)
            act.setChecked(act.data() == tool)
            act.blockSignals(was)
        # Sync the toolbar buttons: the QToolButtons mirror their default
        # actions (the window actions just checked above). Match by data (the
        # ToolMode stored on the action).
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
            "Clear the entire mask on this page? You can undo with Ctrl+Z."
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

        Plan 03-04 TEXT-01 seam (the load-bearing one-line thread-through):
        Phase 1 discarded ``result["blocks"]``; Phase 3, when the Detect Boxes
        mode toggle (D-01) is on, surfaces it as editable ``BoxItem``s on the
        canvas. NO worker change, NO new model call, NO adapter change — the
        blk_list is ALREADY in the dict (``_run_detection_task`` returns
        ``{"mask": ..., "blocks": blk_list}`` at line ~1217). Mode off =
        Phase 1 behaviour preserved exactly (mask only, no box work).
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

        # D-01 mode-toggle gate: only build boxes when Detect Boxes is on. When
        # off, Phase 1 behaviour (mask only) is preserved exactly — no box
        # work, no overlay side-effects, no history push. result["blocks"] is
        # the blk_list the worker ALREADY returned (main_window.py:1217).
        if self.action_detect_boxes_mode.isChecked():
            blk_list = result.get("blocks") or []
            self._build_detected_boxes(blk_list)

        self._refresh_action_states()

    def _build_detected_boxes(self, blk_list) -> None:
        """Build detected PageBoxes from the model's blk_list (TEXT-01, plan 03-04).

        Implements the D-03 re-detect rule (replace detected, keep user), the
        D-04 confirm gate (fire before replacing detected boxes), and the V5
        input-validation control (model xyxy is bounds-clamped against the
        image rect and zero-area boxes are dropped — T-03-06).

        Sequence:
        1. D-04 gate: if >= 1 DETECTED box already exists, ask the user before
           replacing (mirrors _confirm_replace_mask). Cancel aborts (no build).
        2. V5 build: for each TextBlock, coerce to int via textblock_to_box,
           then bounds-clamp x1/x2 to [0, img_w] and y1/y2 to [0, img_h]. Drop
           any box with non-positive area after clamping (model output is
           untrusted — T-03-06).
        3. D-03 merge: collect the existing USER boxes from the canvas
           (they survive re-detect), then rebuild the layer via set_boxes with
           the user boxes + the fresh detected boxes.
        4. Auto-show the box overlay (the boxes the user asked for are visible).
        5. D-10 baseline (plan 03-07, UAT test 3): detection is a NON-undoable
           seeding event — it establishes the live box layer WITHOUT pushing a
           boxes undo entry. The first real user box edit pushes its before-
           snapshot against this baseline (mirrors how the initial mask presence
           from a detect is not individually undoable, only strokes are).
        """
        # Step 1 — D-04 confirm gate. Fires only when >= 1 DETECTED box exists
        # (a user-only layer is not a "replace detected" scenario). The mask
        # replace gate (detect_text) already ran before the worker started.
        detected_now, _user_now = self.canvas.box_origin_counts()
        if detected_now >= 1:
            if not self._confirm_replace_boxes():
                return  # Cancel — no replace (D-04)

        # Step 2 — V5 build. Bounds-clamp against the current image rect. Model
        # xyxy is UNTRUSTED (T-03-06): a negative/out-of-image/inverted xyxy is
        # clamped or dropped, never allowed to corrupt the canvas or crash Qt.
        pixmap = self.canvas.image_item.pixmap()
        img_w = pixmap.width()
        img_h = pixmap.height()
        # G-07-3: detected boxes are born with the saved default family —
        # an empty read -> None -> the renderer's TextStyle() defaults apply
        # (the same empty-family contract as the user-box provider).
        default_family = self._default_font_family()
        detected_pageboxes: list[PageBox] = []
        for blk in blk_list:
            box = textblock_to_box(blk)  # int coercion (plan 03-01, pure)
            clamped = Box(
                min(max(box.x1, 0), img_w),
                min(max(box.y1, 0), img_h),
                min(max(box.x2, 0), img_w),
                min(max(box.y2, 0), img_h),
            )
            # V5 drop: non-positive area after clamping -> drop, never trust.
            if clamped.x2 <= clamped.x1 or clamped.y2 <= clamped.y1:
                logger.debug(
                    f"dropped zero-area detected box "
                    f"({box.as_tuple} -> {clamped.as_tuple} after clamp)"
                )
                continue
            # payload = the TextBlock, preserved untouched for Phase 4/5 OCR
            # + Phase 5 export (CONTEXT). origin DETECTED so re-detect can
            # replace it (D-03).
            detected_pageboxes.append(
                PageBox(
                    box=clamped,
                    origin=DETECTED,
                    payload=blk,
                    style=default_style(default_family) if default_family else None,
                )
            )

        # Step 3 — D-03: keep USER boxes, replace detected. boxes_snapshot()
        # materializes fresh PageBoxes (Pitfall 3 detachment) so the rebuild
        # does not alias live BoxItems.
        #
        # The snapshot captured here is used ONLY to derive the USER boxes that
        # survive the re-detect (D-03). It is NOT pushed to history (see Step 5):
        # detection establishes a NON-undoable baseline (plan 03-07, UAT test 3).
        pre_detection_snapshot = self.canvas.boxes_snapshot()
        user_pageboxes = [pb for pb in pre_detection_snapshot if pb.origin == USER]
        #
        # WR-05 guard: set_boxes emits boxes_modified, which (after the CR-01
        # fix) would push a snapshot via _on_boxes_modified. Detection must seed
        # NO boxes undo entry (Step 5), so the Step 3 emission is suppressed.
        self._suppress_boxes_push = True
        try:
            self.canvas.set_boxes(user_pageboxes, detected_pageboxes)
        finally:
            self._suppress_boxes_push = False

        # Step 4 — auto-show the overlay on first detect (UI-SPEC surface 10).
        # setChecked fires the toggled signal -> set_box_overlay_visible(True).
        if not self.action_toggle_box_overlay.isChecked():
            self.action_toggle_box_overlay.setChecked(True)

        # Step 5 — D-10 baseline (plan 03-07, UAT test 3): detection is a
        # NON-undoable seeding event. It establishes the live box layer as the
        # implicit baseline; the FIRST real user box edit then pushes its
        # before-snapshot against that baseline (WR-04's delta-checks ensure
        # only real edits push). NO push happens here — the previous explicit
        # push of pre_detection_snapshot made the INITIAL detection undoable,
        # which was never desired mid-session: after [detect, move] the BOXES
        # stack held [0-box, 3-box]; undo#3 popped the 0-box pre-detection
        # entry -> restored [] -> ALL detected boxes vanished. This mirrors
        # how the initial mask presence from a detect is not individually
        # undoable, only subsequent strokes are. pre_detection_snapshot is
        # retained above only for the user_pageboxes derivation.
        self._update_undo_redo_actions()

        # Status-bar box count (UI-SPEC §Copywriting status — box count).
        detected, user = self.canvas.box_origin_counts()
        self.status_bar_left.setText(
            f"Detection complete · {self.canvas.box_count()} boxes"
            f" · {detected} detected, {user} user"
        )

    def _confirm_replace_boxes(self) -> bool:
        """Show the replace-detected-boxes confirmation (D-04, plan 03-04).

        Mirrors :meth:`_confirm_replace_mask` verbatim in structure. Returns
        True only on Replace Detected Boxes; False on Cancel. Caller guard:
        only invoked when ``canvas.box_origin_counts()[0] >= 1`` (>= 1
        DETECTED box exists). Fires AFTER the existing mask-replace gate if a
        mask is also present (the mask gate runs first in detect_text; both
        gates can fire on a page with both a mask and detected boxes).

        Uses custom buttons so the UI-SPEC §Copywriting body renders exactly
        — Qt's standard button set has no "Replace Detected Boxes" member.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Detect Text")
        box.setText(
            "Replace the detected text boxes with a new detection? Boxes you"
            " drew yourself are kept. Undo is available via Ctrl+Z."
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        replace_btn = box.addButton(
            "Replace Detected Boxes", QMessageBox.ButtonRole.AcceptRole
        )
        box.setDefaultButton(replace_btn)
        box.exec()
        return box.clickedButton() is replace_btn

    def _on_toggle_box_overlay_toggled(self, checked: bool) -> None:
        """View -> Toggle Box Overlay (Shift+M) handler (D-02, plan 03-04).

        Forwards to the canvas (which toggles per-item visibility + the
        box_layer sentinel + the empty-box hint). Hidden boxes are not
        interactable (Pitfall 5 — setEnabled belt-and-suspenders in the
        canvas). The canvas call refreshes the empty-box-hint visibility.
        """
        self.canvas.set_box_overlay_visible(checked)

    def _on_toggle_text_overlay_toggled(self, checked: bool) -> None:
        """View -> Toggle Text Overlay (T) handler (D-12, plan 04-04).

        Forwards to the canvas's text-overlay layer toggle — an INDEPENDENT
        visibility layer from the box overlay (Shift+M) and the mask overlay
        (M). Hiding the text layer hides ONLY the per-box text-overlay
        children; the box borders + handles + badges stay visible.
        """
        self.canvas.set_text_overlay_visible_flag(checked)

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
            " will be lost \u2014 undo is available via Ctrl+Z."
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

        # CR-01 (D-05/D-15 contract): persist the composite into the model so
        # navigation and project save embed the post-inpaint image. Reading
        # the canvas back is REQUIRED: ``set_image_from_numpy(bbox=...)``
        # composites only the masked region, so ``result_rgb`` alone is not
        # the full displayed state. ``get_image_numpy`` returns a detached
        # copy (Pitfall 2).
        idx = self._current_page_index()
        if idx is not None and 0 <= idx < len(self.image_files):
            composite = self.canvas.get_image_numpy()
            if composite is not None:
                self.image_files[idx].current_image = composite

        # D-07 (plan 05-05): the inpaint result is a page mutation — mark
        # the session dirty + refresh the title (the * suffix).
        self._set_session_dirty()

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

    # ------------------------------------------------------------ ocr (plan 06)
    def _ocr_backend(self) -> str:
        """Return the configured OCR backend (D-14), default 'torch'.

        Same shape as :meth:`_detection_backend`: the backend is an
        application-level concern; the profile carries an optional
        ``ocr_backend`` attribute. Default torch -> TorchOCRModel
        (factory.py ocr/torch branch). The ONNX branch raises
        ``NotImplementedError`` in the factory (D-14 designed-in hook,
        wired for the future).
        """
        try:
            profile = self.profile_manager.config.current_profile
            return getattr(profile, "ocr_backend", "torch")
        except AttributeError:
            return "torch"

    def _resolve_ocr_model_path(self) -> Path:
        """Return the manga-ocr HF cache dir, cache-checking before any fetch.

        manga-ocr resolves its own model from the HF cache
        (``models--kha-white--manga-ocr-base``) via the vendored MangaOcr
        singleton's ``initialize_model()``, so this returns the cache
        DIRECTORY (not a single weights file). Delegates to
        ``panelcleaner.model_downloader.get_ocr_model_directory`` /
        ``is_ocr_downloaded`` (model_downloader.py:251-268, already vendored).

        CR-11 (cache-check): ``is_ocr_downloaded()`` short-circuits when the
        model is present — the ~450MB first-run download is NOT re-fetched on
        every session (T-4-13). The actual fetch (when the cache is empty)
        happens inside ``TorchOCRModel.load`` -> ``MangaOcr.initialize_model()``,
        which runs INSIDE the Worker thread — off the GUI thread
        (RESEARCH Pitfall 6, T-01-07).
        """
        from panelcleaner.model_downloader import (
            get_ocr_model_directory,
            is_ocr_downloaded,
        )

        cache_dir = get_ocr_model_directory()
        # CR-11: short-circuit — do NOT re-download ~450MB when cached.
        if is_ocr_downloaded():
            return cache_dir
        # First run: the cache dir is still the model's home; the MangaOcr
        # singleton's initialize_model() (called by TorchOCRModel.load inside
        # the worker) performs the actual HF fetch off the GUI thread.
        return cache_dir

    def run_ocr_selected(self) -> None:
        """Run manga-ocr on the single selected box (Text -> Run OCR, D-01).

        Mirrors :meth:`detect_text`: the ``Worker(QRunnable)`` +
        ``_op_running`` gate + status-bar progress pattern (RESEARCH Pattern
        2, T-01-07). The D-04 re-OCR gate fires when the selected box's
        recognized text was hand-edited (``edited=True``): silent overwrite
        for raw OCR output, confirm dialog otherwise (Pitfall 4).
        """
        if self._op_running:
            return
        box_item = self.canvas._selected_box()
        if box_item is None:
            return
        # D-04 gate: confirm before overwriting a hand-edited recognition.
        if box_item.pagebox.has_recognized_text() and box_item.pagebox.edited:
            if not self._confirm_reocr():
                return
        self._dispatch_ocr_for_box(box_item)

    def _on_canvas_ocr_requested(self, box_item) -> None:
        """D-01 auto-OCR hook: a freshly-drawn user box triggers single-box OCR.

        Subscribed to ``canvas.ocr_requested`` (emitted by ``_commit_create``
        on Alt+drag draw-release). The D-04 gate does NOT apply here — a
        freshly-created box has no text (``edited=False``), so silent
        overwrite semantics are correct. Gated on ``_op_running``: if another
        op (e.g. a detection) is running, the auto-OCR is skipped silently to
        avoid worker pileup on rapid draws (T-4-14).
        """
        if self._op_running:
            return
        self._dispatch_ocr_for_box(box_item)

    def _dispatch_ocr_for_box(self, box_item) -> None:
        """Dispatch the single-box OCR worker (shared by Run OCR + auto-OCR D-01).

        Resolves the adapter via the factory (D-14; torch is imported lazily
        inside ``TorchOCRModel.load`` — no heavy import here), builds the
        Worker on :meth:`_run_ocr_task` passing the box's vendored frozen
        ``Box`` (a plain object — safe to cross threads, never a Qt object;
        RESEARCH Pitfall 3), and starts it on the global QThreadPool. Sets
        the first-run "Loading OCR model…" UX (Pitfall 6) before the worker
        starts the ~450MB download.
        """
        path = self.file_table.current_path()
        if path is None:
            return
        model = backend_factory("ocr", self._ocr_backend())

        worker = Worker(self._run_ocr_task, path, box_item.pagebox.box, model)
        worker.signals.result.connect(self._on_ocr_finished)
        worker.signals.error.connect(self._on_ocr_error)
        worker.signals.finished.connect(self._on_ocr_cleanup)
        worker.setAutoDelete(True)

        self._op_running = True
        self._refresh_action_states()
        self.error_chip.hide()
        # Indeterminate progress for single-box OCR (no %-subdivisions —
        # UI-SPEC §Copywriting).
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        box_index = self.canvas._box_items.index(box_item) + 1
        self.status_bar_left.setText(f"Recognizing text\u2026 box {box_index}")
        # Pitfall 6: the first-run ~450MB download shows the loading UX BEFORE
        # the worker starts it (the fetch itself runs off the GUI thread).
        from panelcleaner.model_downloader import is_ocr_downloaded

        if not is_ocr_downloaded():
            self.status_bar_left.setText("Loading OCR model\u2026")
        QThreadPool.globalInstance().start(worker)

    def _run_ocr_task(
        self,
        image_path: Path,
        box_xyxy,
        model,
        progress_callback=None,
        abort_flag=None,
    ) -> dict:
        """Worker task: crop the box region, run manga-ocr, return the text.

        Runs on a QThreadPool thread — touches only numpy/Python and the
        adapter (T-01-07). Never touches Qt here. ``box_xyxy`` is the box's
        vendored frozen ``Box``; the region crop is ``.copy()``-detached
        (Pitfall 2). Returns ``{"text": str, "box_id": id(box_xyxy)}`` — the
        box_id lets :meth:`_on_ocr_finished` find the right BoxItem (the
        frozen Box is the SAME object on both sides, so its identity is
        stable across the thread boundary).

        ``progress_callback``/``abort_flag`` are auto-injected by ``Worker``
        (worker_thread.py:97-124).
        """
        import cv2  # lazy import — keeps the main thread import-light
        import numpy as np

        try:
            image = cv2.imdecode(
                np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
            )
        except (OSError, ValueError) as exc:
            raise FileNotFoundError(f"Could not read image: {image_path}") from exc
        if image is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")
        x1, y1, x2, y2 = box_xyxy.as_tuple
        # Pitfall 2: clean copy of the cropped region (detached from the page
        # buffer before it crosses into the model).
        region = image[y1:y2, x1:x2].copy()
        model_path = self._resolve_ocr_model_path()
        model.load(model_path, device="auto")  # singleton — load-once per session
        return {"text": model.recognize(region), "box_id": id(box_xyxy)}

    def run_ocr_all(self) -> None:
        """Run manga-ocr on every text-empty box on the page (Text -> OCR All, D-03).

        Mirrors :meth:`detect_text` + the Phase 2 batch progress pattern: one
        Worker, one model load (Pitfall 3), sequential per-box recognition
        with determinate progress 0..100. The D-04 batch gate fires when any
        box on the page carries hand-edited text (the count is named in the
        dialog); Cancel aborts the whole batch.
        """
        if self._op_running:
            return
        empty_boxes = [
            it
            for it in self.canvas._box_items
            if not it.pagebox.has_recognized_text()
        ]
        if not empty_boxes:
            return
        # D-04 batch gate: edited boxes on the page -> confirm with the count.
        edited_count = sum(
            1
            for it in self.canvas._box_items
            if it.pagebox.has_recognized_text() and it.pagebox.edited
        )
        if edited_count and not self._confirm_reocr_all(edited_count):
            return

        path = self.file_table.current_path()
        if path is None:
            return
        model = backend_factory("ocr", self._ocr_backend())
        worker = Worker(
            self._run_ocr_all_task,
            path,
            [it.pagebox.box for it in empty_boxes],
            [id(it.pagebox) for it in empty_boxes],
            model,
        )
        worker.signals.progress.connect(self._on_ocr_progress)
        worker.signals.result.connect(self._on_ocr_all_finished)
        worker.signals.error.connect(self._on_ocr_error)
        worker.signals.finished.connect(self._on_ocr_cleanup)
        worker.setAutoDelete(True)

        self._op_running = True
        self._refresh_action_states()
        self.error_chip.hide()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_bar_left.setText(f"OCR All\u2026 0/{len(empty_boxes)}")
        # Pitfall 6: first-run loading UX before the worker starts.
        from panelcleaner.model_downloader import is_ocr_downloaded

        if not is_ocr_downloaded():
            self.status_bar_left.setText("Loading OCR model\u2026")
        QThreadPool.globalInstance().start(worker)

    def _run_ocr_all_task(
        self,
        image_path: Path,
        box_xyxys,
        box_ids,
        model,
        progress_callback=None,
        abort_flag=None,
    ) -> list:
        """Worker task: one model load, sequential per-box OCR over the page (D-03).

        Runs on a QThreadPool thread (T-01-07). ONE ``model.load`` for the
        whole batch (Pitfall 3), abort-checked BETWEEN boxes (Phase 2 D-09
        SharableFlag pattern — never mid-box), progress emitted per box with
        the UI-SPEC "OCR All… {done}/{total} · box N" label. Returns a list
        of ``{"box_id": int, "text": str}`` results.
        """
        import cv2  # lazy import — keeps the main thread import-light
        import numpy as np

        image = cv2.imdecode(
            np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")
        model_path = self._resolve_ocr_model_path()
        model.load(model_path, device="auto")  # ONE load for the batch (Pitfall 3)

        results: list[dict] = []
        total = len(box_xyxys)
        for i, (xyxy, bid) in enumerate(zip(box_xyxys, box_ids)):
            if abort_flag is not None and abort_flag.get():
                break  # D-09: abort between boxes, never mid-box
            x1, y1, x2, y2 = xyxy.as_tuple
            region = image[y1:y2, x1:x2].copy()  # Pitfall 2 clean copy
            text = model.recognize(region)
            results.append({"box_id": bid, "text": text})
            if progress_callback is not None:
                percent = (i + 1) * 100 // total if total else 100
                progress_callback.emit((percent, f"{i + 1}/{total} \u00b7 box {i + 1}"))
        return results

    def _on_ocr_progress(self, payload) -> None:
        """Update the status bar + progress bar during OCR All (D-03).

        Mirrors :meth:`_on_batch_progress`: the worker emits ``(percent,
        label)`` per box; the label carries the UI-SPEC
        "{done}/{total} · box N" shape.
        """
        if isinstance(payload, tuple) and len(payload) == 2:
            percent, label = payload
        else:
            return
        self.progress_bar.setValue(int(percent))
        self.status_bar_left.setText(f"OCR All\u2026 {label}")

    def _on_ocr_finished(self, result) -> None:
        """Write the recognized text back to the box (main thread only, T-01-07).

        Finds the BoxItem by ``box_id`` (the frozen Box identity the worker
        returned), writes ``set_recognized_text`` (the Plan 01 OCR-write
        setter — ``edited=False``, D-04 silent-overwrite semantics),
        refreshes the text overlay + badge, and pushes a CR-01 before-state
        BOXES snapshot.

        The before snapshot is captured BEFORE the write and each payload is
        shallow-detached (``copy.copy``) so the push-time materialization
        sees the true pre-OCR text (Pitfall 8 push-side — the 04-05 fix
        pattern; without the detach, undo would restore the post-OCR text).
        """
        box_id = result.get("box_id")
        item = next(
            (it for it in self.canvas._box_items if id(it.pagebox.box) == box_id),
            None,
        )
        if item is None:
            logger.warning("OCR finished for a box that no longer exists")
            return
        # CR-01: capture the PRE-OCR snapshot + detach payloads (Pitfall 8).
        before = self.canvas.boxes_snapshot()
        for pb in before:
            if pb.payload is not None:
                pb.payload = copy.copy(pb.payload)
        item.pagebox.set_recognized_text(result["text"])  # edited=False (D-04)
        item.refresh_text_overlay()
        item.refresh_badge()
        # boxes_modified -> _on_boxes_modified pushes the BEFORE snapshot.
        self.canvas.boxes_modified.emit(before)
        # Transient completion status (reverts to the box-count line ~3 s).
        self._show_transient_status("OCR complete \u00b7 1 box recognized")

    def _on_ocr_all_finished(self, results) -> None:
        """Write the batch results back to their boxes (main thread only, D-03).

        ONE CR-01 before-state BOXES snapshot for the whole batch (UI-SPEC
        §20 batch-undo pattern), captured BEFORE any write with payloads
        detached (Pitfall 8). Results whose box vanished mid-run are skipped.
        """
        if not results:
            self._show_transient_status("OCR complete \u00b7 0 boxes recognized")
            return
        before = self.canvas.boxes_snapshot()
        for pb in before:
            if pb.payload is not None:
                pb.payload = copy.copy(pb.payload)
        recognized = 0
        for result in results:
            item = next(
                (
                    it
                    for it in self.canvas._box_items
                    if id(it.pagebox) == result["box_id"]
                ),
                None,
            )
            if item is None:
                continue
            item.pagebox.set_recognized_text(result["text"])  # edited=False (D-04)
            item.refresh_text_overlay()
            item.refresh_badge()
            recognized += 1
        if recognized:
            self.canvas.boxes_modified.emit(before)
        self._show_transient_status(f"OCR complete \u00b7 {recognized} boxes recognized")

    def _on_ocr_error(self, worker_error) -> None:
        """Show the model-load error dialog + persistent #7a1f1f error chip.

        Mirrors :meth:`_on_detection_error` (T-01-08): the full traceback
        goes to loguru; the QMessageBox shows only user-friendly copy
        (UI-SPEC §Copywriting OCR model-load error). ``_op_running`` is
        cleared by :meth:`_on_ocr_cleanup` (``finished`` always fires —
        Pitfall 7).
        """
        logger.error(f"OCR failed: {worker_error}")
        self._show_error_chip("OCR model error")
        QMessageBox.critical(
            self,
            "Couldn't load the OCR model.",
            "The manga-ocr model files couldn't be loaded or downloaded."
            " Check your network connection (first run downloads ~450 MB)"
            " and see the log for details.",
        )
        self.status_bar_left.setText("OCR failed")

    def _on_ocr_cleanup(self, _args) -> None:
        """Reset the async-op flag + progress UI after the worker finishes.

        Connected to ``finished``, which ``Worker.run``'s ``finally`` ALWAYS
        emits (Pitfall 7), so ``_op_running`` clears even after an
        error/abort. The completion status set in the finished handler is
        left intact — the transient revert timer restores the box-count line.
        """
        self._op_running = False
        self.progress_bar.hide()
        self._refresh_action_states()

    def _confirm_reocr(self) -> bool:
        """Show the D-04 re-OCR confirmation (UI-SPEC §Copywriting).

        Mirrors :meth:`_confirm_replace_boxes` verbatim in structure.
        Returns True only on Re-run OCR; False on Cancel. Caller guard: only
        invoked when the selected box's recognized text is hand-edited
        (``edited=True``); raw OCR output is overwritten silently (D-04).
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Run OCR")
        box.setText(
            "This box has text you edited. Running OCR will overwrite your"
            " edit with a fresh recognition. Undo is available via Ctrl+Z."
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        rerun_btn = box.addButton("Re-run OCR", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(rerun_btn)
        box.exec()
        return box.clickedButton() is rerun_btn

    def _confirm_reocr_all(self, count: int) -> bool:
        """Show the D-04 batch re-OCR confirmation with the edited-box count.

        Mirrors :meth:`_confirm_reocr`; the body names the count (UI-SPEC
        §Copywriting D-04 batch gate). Returns True only on Re-run OCR on
        All; False on Cancel.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Run OCR")
        box.setText(
            f"{count} box(es) on this page have text you edited. Running OCR"
            " will overwrite those edits. Undo is available via Ctrl+Z."
        )
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        rerun_btn = box.addButton(
            "Re-run OCR on All", QMessageBox.ButtonRole.AcceptRole
        )
        box.setDefaultButton(rerun_btn)
        box.exec()
        return box.clickedButton() is rerun_btn

    def _auto_number(self, rtl: bool) -> None:
        """Assign page-global bubble numbers 1..N in reading order (D-15/D-16).

        Delegates to the Plan 02 ``reading_order.assign_bubble_numbers``
        (XY-Cut — no algorithm logic in the GUI). The preserve-manual conflict
        policy lives in the algorithm: ``manual_override`` boxes keep their
        number + flag and the auto sequence leaves a gap (T-4-17). Every
        BoxItem badge refreshes (new numbers + manual-override amber borders);
        the whole op pushes ONE batch BOXES snapshot (UI-SPEC §20) and shows
        the "Numbered {n} boxes (RTL/TB)." / "(LTR/TB)." transient. An empty
        page is a no-op.
        """
        from manga_ai_studio.core.reading_order import assign_bubble_numbers

        boxes = [it.pagebox for it in self.canvas._box_items]
        if not boxes:
            return
        # CR-01 before-state: the snapshot materializes fresh PageBoxes, so
        # its bubble_no fields are detached from the live boxes by
        # construction (no payload mutation here — no Pitfall-8 detach needed).
        before = self.canvas.boxes_snapshot()
        count = assign_bubble_numbers(boxes, rtl=rtl)
        if count:
            for it in self.canvas._box_items:
                it.refresh_badge()
            # ONE batch BOXES entry -> _on_boxes_modified pushes it.
            self.canvas.boxes_modified.emit(before)
        self._show_transient_status(
            f"Numbered {count} boxes ({'RTL/TB' if rtl else 'LTR/TB'})."
        )

    def _auto_number_rtl(self) -> None:
        """Text -> Auto-Number -> RTL (Manga): right-to-left reading order."""
        self._auto_number(rtl=True)

    def _auto_number_ltr(self) -> None:
        """Text -> Auto-Number -> LTR (Manhwa): left-to-right reading order."""
        self._auto_number(rtl=False)

    # ------------------------------------------------ load translations (plan 07)
    def _open_load_translations(self) -> None:
        """Text -> Load Translations…: show the paste/file-import dialog (D-17).

        Opens :class:`LoadTranslationsDialog` with the open pages by name and
        the current page pre-selected. On Accept, the collected ``(text,
        page_index)`` is handed to :meth:`_apply_translations` — the dialog
        never parses or mutates boxes itself (RESEARCH §Pitfall 3 separation).
        """
        if not self.image_files:
            return
        page_names = [imf.path.name for imf in self.image_files]
        current_index = self._current_page_index()
        if current_index is None:
            current_index = 0
        dlg = LoadTranslationsDialog(self, page_names, current_index)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._apply_translations(dlg.get_text(), dlg.get_page_index())

    def _apply_translations(self, text: str, page_index: int) -> None:
        """Apply a translation block to the page at ``page_index`` (D-17).

        Runs the Plan 02 parser core (``parse_translations`` +
        ``apply_translations`` — no parsing/matching logic in the GUI) and
        reports the parser-result counts. On the CURRENT page the apply goes
        through the live BoxItems, refreshes the overlays/badges, and pushes
        ONE batch BOXES snapshot (UI-SPEC §20 — the whole Load Translations
        op is one undo entry) with Pitfall-8 payload detach before the
        setter mutation. For non-current pages (multi-page files with
        "Page N:" markers, D-17) the apply targets ``ImageFile.boxes`` in
        place; the canvas refresh happens when the user navigates there.
        """
        if not self.image_files or not 0 <= page_index < len(self.image_files):
            return
        from manga_ai_studio.core.translation_parser import (
            apply_translations,
            parse_translations,
        )

        # ASVS V7 belt-and-suspenders: the Plan 02 parser never raises, but an
        # unexpected failure surfaces a friendly dialog, not a crash.
        try:
            matches, skipped = parse_translations(text)
        except Exception as exc:
            logger.error(f"Translation parse failed: {exc}")
            QMessageBox.critical(
                self, "Load Translations", "Couldn't apply translations — see the log."
            )
            return

        page_no = page_index + 1  # 1-indexed for the user-facing copy
        if page_index == self._current_page_index():
            boxes = [it.pagebox for it in self.canvas._box_items]
            # CR-01 before-state + Pitfall-8 detach (the 04-05/04-06 pattern).
            before = self.canvas.boxes_snapshot()
            for pb in before:
                if pb.payload is not None:
                    pb.payload = copy.copy(pb.payload)
            try:
                applied, unmatched = apply_translations(
                    matches, boxes, page_no=page_index
                )
            except Exception as exc:
                logger.error(f"Translation apply failed: {exc}")
                QMessageBox.critical(
                    self,
                    "Load Translations",
                    "Couldn't apply translations — see the log.",
                )
                return
            if applied:
                for it in self.canvas._box_items:
                    it.refresh_text_overlay()
                    it.refresh_badge()
                # ONE batch entry (UI-SPEC §20) -> _on_boxes_modified pushes it.
                self.canvas.boxes_modified.emit(before)
            self._show_translation_report(applied, unmatched + skipped, page_no)
        else:
            # Non-current page (multi-page file): apply in place; the canvas
            # refresh happens on navigation. No BOXES push — the undo stack is
            # per-page (reset_history on page switch).
            try:
                applied, unmatched = apply_translations(
                    # WR-04: ImageFile.boxes defaults to None until the page is
                    # visited (on_page_selected populates it) — pass [] so a
                    # never-visited target page reports the clean no-match copy
                    # instead of crashing on 'NoneType' not iterable.
                    matches,
                    self.image_files[page_index].boxes or [],
                    page_no=page_index,
                )
            except Exception as exc:
                logger.error(f"Translation apply failed: {exc}")
                QMessageBox.critical(
                    self,
                    "Load Translations",
                    "Couldn't apply translations — see the log.",
                )
                return
            self._show_translation_report(applied, unmatched + skipped, page_no)

    def _show_translation_report(self, applied: int, skipped_total: int, page_no: int) -> None:
        """Show the parser-result report (UI-SPEC §Copywriting, D-15/D-17).

        Informational, non-modal tone (ASVS V5 — unmatched lines are a soft
        skip, not an error): the success copy names the applied count + the
        combined skipped total (unmatched bubble numbers + unparseable/SFX
        lines); zero applied shows the no-matches path copy.
        """
        if applied == 0:
            body = (
                f"No lines matched any bubble number on page {page_no}. Check"
                " that the bubble numbers in your text match the numbers on"
                " the canvas (Text \u2192 Auto-Number)."
            )
        else:
            body = (
                f"Applied {applied} translation(s) to page {page_no}."
                f" {skipped_total} line(s) did not match a bubble number and"
                " were skipped."
            )
        QMessageBox.information(self, "Load Translations", body)

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

    def _export_ocr_json(self) -> None:
        """Text menu -> Export OCR JSON… (the Shift-modified E shortcut):
        write the CURRENT page's D-19 ``_ocr.json`` via the Save As dialog
        (UI-SPEC surface 27, D-21/D-22, PROJ-03).

        The flush seam runs FIRST (Pitfall 7): ``_snapshot_current_page()``
        writes the live canvas state (boxes + current-image + mask) into the
        outgoing ``ImageFile``, so the export always describes the CURRENT
        page state (D-22) — including boxes the user drew/edited since the
        last navigation. The current page is read from the stored
        ``_last_page_index`` (the D-11 seam rule — never ``_current_page_index``
        mid-navigation).

        The dialog's default target follows D-22 via
        ``default_ocr_json_path`` (pristine -> ``<stem>_ocr.json`` beside the
        source; geometry-altered -> ``cleaned/``); the user may override.
        Cancelling the dialog is a no-op. Write failures surface the
        save-failure critical dialog (the T-05-12 copy) with the traceback
        logged; success flashes the single-page copy (UI-SPEC §Copywriting,
        page number 1-indexed matching the status-bar convention).
        """
        if self._op_running:
            return
        idx = self._last_page_index
        if idx is None or not (0 <= idx < len(self.image_files)):
            return
        # Pitfall 7: flush BEFORE reading — the export must describe the live
        # canvas, not the last-navigation state.
        self._snapshot_current_page()
        imf = self.image_files[idx]
        page_path = imf.path
        boxes = imf.boxes if imf.boxes is not None else []
        # D-22: the dims describe the CURRENT page state — read them from the
        # just-flushed canvas, never from the source file.
        img_np = self.canvas.get_image_numpy()
        if img_np is None:
            return
        img_h, img_w = img_np.shape[:2]

        from manga_ai_studio.core.ocr_export import (
            default_ocr_json_path,
            write_page_ocr_json,
        )

        default_target = default_ocr_json_path(page_path, imf.geometry_altered)
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Export OCR JSON", str(default_target), "OCR JSON (*_ocr.json)"
        )
        if not chosen:
            return
        chosen_path = Path(chosen)
        try:
            write_page_ocr_json(
                boxes,
                img_w,
                img_h,
                page_path,
                imf.geometry_altered,
                path_override=chosen_path,
            )
        except OSError as exc:
            # T-05-12: the save-failure copy; the traceback goes to loguru.
            logger.error(f"Export OCR JSON failed: {exc}", exc_info=True)
            QMessageBox.critical(
                self,
                f"Couldn't save '{chosen_path.name}'.",
                "Check that the folder is writable and see the log for details.",
            )
            return
        self._show_transient_status(f"Exported OCR JSON for page {idx + 1}.")

    def _on_export_typeset(self) -> None:
        """File menu -> Export Typeset… (Ctrl+Shift+B): bake the typeset text
        into a copy of the CURRENT page image (D-01/D-02, plan 07-01 Task 2).

        Mirrors the OCR-JSON export's seam order: ``_op_running`` gate first,
        then the ``_snapshot_current_page()`` flush (Pitfall 7 — the bake
        must describe the live canvas, boxes included), then the page image
        read via ``canvas.get_image_numpy()`` (detached — Pitfall 2), then
        the Save As dialog defaulting to the D-03 sidecar path (pristine ->
        ``{stem}_typeset.png`` beside the source; geometry-altered ->
        ``cleaned/`` — the D-22 mirror).

        The compositor (``bake_typeset_page``) renders every box's current-
        focus text (D-04: translation else recognized; neither -> nothing)
        through the SAME renderer functions the canvas overlay uses — canvas
        ≡ bake (D-01); it works on a detached copy so the canvas is never
        mutated, and it draws text only (no chrome). The write goes through
        ``save_image_optimized`` (the PROJ-02 contract: PNG compress 9 /
        JPG quality 95, DPI preserved); failures surface the save-failure
        critical dialog (T-05-12 copy) and success flashes the UI-SPEC copy.
        """
        if self._op_running:
            return
        idx = self._last_page_index
        if idx is None or not (0 <= idx < len(self.image_files)):
            return
        # Pitfall 7: flush BEFORE reading — the bake must reflect the live
        # canvas (boxes drawn/edited since the last navigation).
        self._snapshot_current_page()
        imf = self.image_files[idx]
        page_path = imf.path
        image_np = self.canvas.get_image_numpy()
        if image_np is None:
            return
        boxes = imf.boxes if imf.boxes is not None else []

        from manga_ai_studio.core.image_io import save_image_optimized
        from manga_ai_studio.core.ocr_export import default_typeset_path
        from manga_ai_studio.gui.text_renderer import bake_typeset_page

        default_target = default_typeset_path(page_path, imf.geometry_altered)
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Export Typeset",
            str(default_target),
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)",
        )
        if not chosen:
            return
        chosen_path = Path(chosen)
        # Detached composite (Pitfall 2) — never the live canvas image.
        baked = bake_typeset_page(image_np, boxes)
        try:
            save_image_optimized(baked, chosen_path, original=page_path)
        except OSError as exc:
            # T-05-12: the save-failure copy; the traceback goes to loguru.
            logger.error(f"Export Typeset failed: {exc}", exc_info=True)
            QMessageBox.critical(
                self,
                f"Couldn't save '{chosen_path.name}'.",
                "Check that the folder is writable and see the log for details.",
            )
            return
        self._show_transient_status(f"Typeset exported → {chosen_path.name}")

    def _dispatch_batch_ocr_export(self) -> None:
        """Batch menu -> Batch Export OCR JSON: dispatch ``batch_export_ocr``
        on a single Worker (D-21, UI-SPEC surface 27 + §E6/E9 rows).

        Mirrors ``_dispatch_batch`` exactly (main_window.py's FLOW-03
        template): the flush seam runs BEFORE the pages are projected
        (Pitfall 7 — ``_snapshot_current_page`` + the Bug-D mask flush make
        the batch describe the live canvas), each page projects to an
        ``ExportPage`` (dims per page: the current page from the canvas, the
        others from the ``ImageFile``'s known current-image numpy when
        present, else the source-file dims via PIL), the Worker runs the
        model-free loop with ``abort_signal`` auto-injection, and the Phase 2
        batch surface drives the status/progress/Cancel machinery
        (``_op_running`` + ``_batch_active`` + determinate bar + Cancel Batch
        enablement).

        ``batch_export_ocr`` performs per-page failure isolation (D-04) and
        logs only page stems + error strings (T-05-05), so no per-page modal
        ever opens; the completion copy carries the failure count instead.
        """
        if self._op_running or self._batch_active:
            return
        if not self.image_files:
            return

        # Pitfall 7 flush seam: the D-11 seam only persists the outgoing page
        # on NAVIGATION; dispatching from the current page skips it. Flush the
        # canvas state (boxes + current image + mask) into the data model
        # BEFORE projecting the pages, so the export describes the live canvas.
        self._snapshot_current_page()
        self._flush_current_canvas_mask_to_data_model()

        from manga_ai_studio.core.ocr_export import ExportPage, batch_export_ocr

        current_idx = self._current_page_index()
        pages = []
        for i, imf in enumerate(self.image_files):
            if i == current_idx:
                img_np = self.canvas.get_image_numpy()
                if img_np is None:
                    return
                img_h, img_w = img_np.shape[:2]
            elif imf.current_image is not None:
                img_h, img_w = imf.current_image.shape[:2]
            else:
                # D-22: dims describe the CURRENT page state — for a never-
                # flushed page that is the source image's dims (read via PIL).
                with Image.open(imf.path) as src:
                    img_w, img_h = src.size
            pages.append(
                ExportPage(
                    path=imf.path,
                    boxes=imf.boxes if imf.boxes is not None else [],
                    img_w=img_w,
                    img_h=img_h,
                    geometry_altered=imf.geometry_altered,
                )
            )

        # The task fn is a partial over the projected pages; Worker injects
        # progress_callback + abort_flag as the last two kwargs
        # (worker_thread.py:103-140 — the batch_export_ocr contract).
        task_fn = partial(batch_export_ocr, pages)
        worker = Worker(task_fn, abort_signal=self.batch_abort_requested)
        worker.signals.progress.connect(self._on_batch_ocr_export_progress)
        worker.signals.result.connect(self._on_batch_ocr_export_finished)
        worker.signals.error.connect(self._on_batch_ocr_export_error)
        # Pitfall 7: finished ALWAYS fires (Worker.run's finally), so cleanup
        # always runs even on abort/error; aborted also routes to the same
        # idempotent cleanup handler.
        worker.signals.aborted.connect(self._on_batch_ocr_export_cleanup)
        worker.signals.finished.connect(self._on_batch_ocr_export_cleanup)
        worker.setAutoDelete(True)

        # D-08: the batch blocks the editor. Disable navigation (T-02-05 race
        # mitigation) + set the op-running flags; the canvas stays visible.
        self._op_running = True
        self._batch_active = True
        self._batch_ocr_total = len(pages)
        self._batch_cancelled = False
        self.file_table.setEnabled(False)
        self._refresh_action_states()
        self.error_chip.hide()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_bar_left.setText(f"Exporting OCR JSON\u2026 0/{len(pages)}")
        QThreadPool.globalInstance().start(worker)

    def _on_batch_ocr_export_progress(self, payload) -> None:
        """Update the status bar + progress bar per page (UI-SPEC §E9).

        The worker emits ``(percent, name)`` once per page
        (batch_export_ocr's D-10 shape); the {done}/{total} copy is derived
        from the percent against the dispatched page count.
        """
        if isinstance(payload, tuple) and len(payload) == 2:
            percent, name = payload
        else:
            return
        total = self._batch_ocr_total or 0
        done = round(int(percent) * total / 100) if total else 0
        self.progress_bar.setValue(int(percent))
        self.status_bar_left.setText(
            f"Exporting OCR JSON\u2026 {done}/{total} \u2014 {name}"
        )

    def _on_batch_ocr_export_finished(self, result: dict) -> None:
        """Flash the batch completion copy (UI-SPEC §Copywriting batch rows).

        Clean run: "Exported OCR JSON for {n} page(s)." Mixed run: the
        failure-count form appended. Per-page failures are ALREADY logged by
        ``batch_export_ocr`` (stems + error strings only — T-05-05), so the
        handler stays UI-only; no per-page modal (Phase 2 batch-report
        discipline).
        """
        ok = result.get("ok", 0) if isinstance(result, dict) else 0
        failed = result.get("failed", []) if isinstance(result, dict) else []
        if failed:
            self._show_transient_status(
                f"Exported OCR JSON for {ok} page(s)."
                f" {len(failed)} page(s) failed \u2014 see the log."
            )
        else:
            self._show_transient_status(f"Exported OCR JSON for {ok} page(s).")
        self._refresh_action_states()

    def _on_batch_ocr_export_error(self, worker_error) -> None:
        """Log the OCR-export batch failure + show the error chip (T-01-08
        mirror). The full ``WorkerError`` (traceback included) goes to loguru;
        ``_on_batch_ocr_export_cleanup`` (finished always fires) re-enables
        the editor.
        """
        logger.error(f"OCR batch export failed: {worker_error}")
        self._show_error_chip("Batch export error")
        self.status_bar_left.setText("Batch export failed")

    def _on_batch_ocr_export_cleanup(self, _args) -> None:
        """Unconditionally clear the OCR-export batch state (Pitfall 7).

        Connected to BOTH ``aborted`` and ``finished`` (Worker.run's
        ``finally`` always emits ``finished``), so the editor is never stuck
        disabled. On a cancel the ``aborted`` signal fires instead of
        ``result``, so this cleanup is the only place to render the
        "Cancelled" status (the Bug B pattern — the stale per-page progress
        text must not linger). The OCR-export batch mutates no canvas state,
        so there is no mode-aware post-batch refresh to run (unlike the
        cleaning batches).
        """
        cancelled = self._batch_cancelled
        self._op_running = False
        self._batch_active = False
        self._batch_ocr_total = 0
        self.file_table.setEnabled(True)  # T-02-05: re-enable navigation
        self.progress_bar.hide()
        self._refresh_action_states()
        if cancelled:
            self.status_bar_left.setText("Cancelled")
            self._batch_cancelled = False

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

        Bug D1 (checkpoint rework): capture the batch mode BEFORE it is reset
        below (``self._batch_mode = None``). ``_refresh_current_page_after_batch``
        is mode-aware (detect-only batches must RESTORE the detected mask onto
        the canvas; clean-containing batches must reload + clear it), so the
        mode must still be readable when the refresh runs. The refresh call
        stays before the reset by construction, but capturing the mode into a
        local makes the ordering dependency explicit and safe.
        """
        cancelled = self._batch_cancelled
        batch_mode = self._batch_mode
        # Bug C (checkpoint rework): for a clean-containing batch, refresh the
        # currently-displayed page so the user sees the cleaned result + a
        # cleared mask overlay without manually re-navigating — the same
        # refresh single-page Inpaint performs in ``_on_inpaint_finished``.
        # Skip on cancel/error so we never overwrite an error/cancel status.
        if not cancelled:
            self._refresh_current_page_after_batch(batch_mode)

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

    def _refresh_current_page_after_batch(self, batch_mode: str | None = None) -> None:
        """Refresh the current page's canvas after a batch finishes (Bug C, Bug D1).

        Mode-aware (Bug D1):

        * **Clean-containing batch** (``batch_mode`` is ``"clean"`` or
          ``"detect_and_clean"``): the currently-displayed page must show the
          cleaned result with its mask overlay CLEARED — the same refresh
          single-page Inpaint performs in ``_on_inpaint_finished`` (Bug C).
          The batch writes cleaned files to ``cleaned_dir`` (D-07); reload the
          current page from there if present, otherwise leave it. Then clear
          the consumed mask overlay so the red overlay does not sit on the
          now-cleaned page.
        * **Detect-only batch** (``batch_mode`` is ``"detect"``): there is no
          cleaned output to load, so do NOT clear the canvas. Instead RESTORE
          the current page's just-detected ``ImageFile.mask`` onto the canvas
          (mirroring the D-11 seam step 4 at ``on_page_selected``), so the user
          sees the detected mask and the data model + canvas stay in sync. If
          the page has no detected mask (``ImageFile.mask`` is None/empty),
          clear the canvas overlay (the page had no detected text).

        The mode distinction is load-bearing for Bug D1: the previous
        unconditional clear left the canvas desynced from the correctly-written
        ``ImageFile.mask`` after a detect batch, and the D-11 seam then
        snapshotted that empty canvas back onto the outgoing page on the next
        navigation — silently erasing detected masks on backwards navigation
        ("skipping current page and pages before that").

        Careful with the D-11 seam (Plan 02-02): the mask is part of the
        per-page data model. For the clean path, clearing the canvas overlay
        does NOT touch ``ImageFile.mask`` — the consumed mask stays persisted
        on the data model so re-navigation still shows/clears it consistently.
        We only update the live canvas display.
        """
        current = self.file_table.current_path()
        if current is None:
            return

        # --- Bug D1: detect-only branch — RESTORE the detected mask. ---------
        # No cleaned output exists for a detect-only batch, so the Bug C
        # reload+clear is wrong here: it would wipe the just-detected mask the
        # loop wrote onto ImageFile.mask, leaving the canvas desynced. Instead
        # mirror the D-11 seam step 4 (on_page_selected lines ~724-734) and
        # restore the current page's detected mask onto the canvas. The
        # boundary .copy() matches the seam (Pitfall 2). When the page had no
        # detected text (mask is None/empty), clear the overlay instead.
        if batch_mode == "detect":
            idx = self._current_page_index()
            if (
                idx is not None
                and 0 <= idx < len(self.image_files)
                and self.image_files[idx].mask is not None
                and not self.image_files[idx].mask.isNull()
                and self.image_files[idx].has_mask_content()
            ):
                # Restore the detected mask onto the canvas (D-11 seam step 4
                # mirror). set_mask copies internally (canvas.py:305); the
                # boundary .copy() is belt-and-suspenders and matches the seam.
                self.canvas.set_mask(self.image_files[idx].mask.copy())
            else:
                # Page had no detected text — ensure the overlay is clear so
                # the canvas matches the empty data-model mask.
                canvas_mask = self.canvas.get_mask()
                if canvas_mask is not None and not canvas_mask.isNull():
                    canvas_mask.fill(Qt.GlobalColor.transparent)
                    self.canvas.update_mask_display()
            return

        # --- Bug C: clean-containing branch — reload + clear consumed mask. --
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

    def _on_quit(self) -> None:
        """Quit (Ctrl+Q / File → Quit): the D-07 Unsaved Changes gate runs
        HERE, before the programmatic ``close()``.

        The gate lives at the action handler (not in closeEvent) because the
        ``close()`` it triggers is a programmatic, non-spontaneous close —
        closeEvent gates only window-manager closes (see :meth:`closeEvent`),
        so a programmatic close must consult the gate at its own call site.
        """
        if self._confirm_discard_changes():
            self.close()

    def closeEvent(self, event) -> None:
        """Window close (X / Alt+F4) -> the D-07 Unsaved Changes gate.

        Only SPONTANEOUS close events (initiated by the window manager) run
        the gate: a programmatic ``close()`` must not re-prompt — the Quit
        action is gated in :meth:`_on_quit`, and host/test teardown closes
        must not pop a modal dialog. Cancel aborts the close
        (``event.ignore()``); Save/Discard let it proceed.
        """
        if event.spontaneous() and not self._confirm_discard_changes():
            event.ignore()
            return
        event.accept()


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

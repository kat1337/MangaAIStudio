"""MainWindow — the application controller.

Architecture adapted from PanelCleaner ``mainwindow_driver.py`` (GPL v3,
vendored-shape per D-12): the constructor receives a ``ProfileManager``,
builds a central ``EditorCanvas``, and wires the menu bar / actions. The
skeleton ships File -> Open Image (Ctrl+O) and View -> Fit to Window (Ctrl+0);
detection/inpainting/tool-dispatch menus land in later plans.

T-01-01 mitigation (path traversal): ``QFileDialog.getOpenFileName`` returns an
absolute, OS-validated path; no user-typed path string is accepted here. Plan 02
adds ``Path.resolve()`` + suffix allowlist validation when folder/recent-files
opens land.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
)

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.gui.canvas import EditorCanvas


class MainWindow(QMainWindow):
    """Top-level application window.

    A ``QMainWindow`` with a central ``EditorCanvas``, a File menu, and a View
    menu. Holds a ``ProfileManager`` for settings access.
    """

    def __init__(self, profile_manager: ProfileManager, parent=None) -> None:
        super().__init__(parent)
        self.profile_manager = profile_manager

        # Central canvas.
        self.canvas = EditorCanvas(self)
        self.setCentralWidget(self.canvas)

        self._build_menus()

        # Window chrome (UI-SPEC surface 1).
        self.setWindowTitle("Manga AI Studio")
        self.setMinimumSize(1024, 720)
        self.resize(1440, 900)

    # ------------------------------------------------------------------ menus
    def _build_menus(self) -> None:
        # File menu.
        self.action_open_image = QAction("Open Image\u2026", self)
        self.action_open_image.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open_image.triggered.connect(self.open_image)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.action_open_image)

        # View menu.
        self.action_fit_to_window = QAction("Fit to Window", self)
        self.action_fit_to_window.setShortcut(QKeySequence("Ctrl+0"))
        self.action_fit_to_window.triggered.connect(self.canvas.fit_to_window)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.action_fit_to_window)

    # ------------------------------------------------------------------ slots
    def open_image(self) -> None:
        """Open a single image file into the canvas via File -> Open Image.

        Uses ``QFileDialog.getOpenFileName`` (T-01-01 path-traversal mitigation:
        OS-validated absolute path, no user-typed string). Loads via ``QImage``
        with a ``.copy()`` to detach the buffer (RESEARCH Pitfall 2), then sets
        it on the canvas and fits the view.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return

        image = QImage(path)
        if image.isNull():
            return
        # Detach the buffer so the pixel data is not tied to the transient load
        # (RESEARCH Pitfall 2 — QImage lifetime crashes).
        image = image.copy()
        pixmap = QPixmap.fromImage(image)

        self.canvas.set_image(pixmap)
        self.setWindowTitle(f"Manga AI Studio \u2014 {Path(path).name}")
        self.canvas.fit_to_window()

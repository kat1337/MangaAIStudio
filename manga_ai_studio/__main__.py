"""Application entry point.

Run with ``python -m manga_ai_studio``. Constructs the QApplication, builds a
ProfileManager rooted in the user's config directory, shows the MainWindow, and
enters the Qt event loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manga_ai_studio.app import create_app
from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.gui.main_window import MainWindow


def main() -> None:
    """Launch the Manga AI Studio application."""
    app = create_app(sys.argv)

    config_dir = Path.home() / ".manga_ai_studio"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_manager = ProfileManager(config_dir)

    window = MainWindow(profile_manager)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

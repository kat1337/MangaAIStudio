"""Application entry point.

Run with ``python -m manga_ai_studio``. Constructs the QApplication, builds a
ProfileManager rooted in the user's config directory, loads the persisted
"default" profile so D-10 config (e.g. the mask dilation radius) survives
restarts, shows the MainWindow, and enters the Qt event loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from manga_ai_studio import diagnostics
from manga_ai_studio.app import create_app
from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.gui.main_window import MainWindow


def main() -> None:
    """Launch the Manga AI Studio application."""
    # quick-260909-ke1: diagnostics FIRST, before anything else can fail — the
    # rotating file sink, the excepthooks and the faulthandler watchdog make a
    # crash or freeze self-reporting (mas.log / mas-hang.log), which is the
    # whole point: the app previously had no logs at all.
    log_path = diagnostics.install()

    app = create_app(sys.argv)
    diagnostics.install_qt_message_handler()
    diagnostics.heartbeat(app)
    # The user must always be able to find and paste the log path. Native
    # crashes additionally leave a minidump next to it (quick-260909-ke1).
    print(f"[manga-ai-studio] log file: {log_path}", file=sys.stderr)
    print(
        "[manga-ai-studio] native crashes leave a mas-<timestamp>.dmp minidump "
        "next to the log file",
        file=sys.stderr,
    )

    config_dir = Path.home() / ".manga_ai_studio"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_manager = ProfileManager(config_dir)

    # Startup profile load (RESEARCH §4.1 gap): apply the persisted "default"
    # profile to profile_manager.config.current_profile — the object the
    # MainWindow reads. Profile.load itself falls back to defaults on a
    # malformed INI (config.py:1031-1034); this guard only covers filesystem
    # errors, so a broken config dir degrades to defaults instead of
    # preventing launch.
    try:
        profile_manager.load_profile("default")
    except OSError:
        logger.exception("Failed to load the default profile; using defaults.")

    window = MainWindow(profile_manager)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

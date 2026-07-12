"""Shared pytest fixtures for Manga AI Studio.

Establishes the Wave 0 test infrastructure (VALIDATION.md §Wave 0 Requirements):
- ``pytest.importorskip("PySide6")`` so GUI-adjacent imports skip cleanly where
  PySide6 is unavailable (e.g. CI without Qt).
- ``default_profile`` / ``tmp_config_dir`` / ``profile_manager`` fixtures for
  config round-trip tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# GUI smoke tests (tests/test_gui_canvas.py) import PySide6; guard at module
# level so collection degrades gracefully on Qt-less environments.
pytest.importorskip("PySide6")

from panelcleaner.config import Profile  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402


@pytest.fixture()
def default_profile() -> Profile:
    """A fresh default PanelCleaner ``Profile``."""
    return Profile()


@pytest.fixture()
def tmp_config_dir(tmp_path: Path) -> Path:
    """An isolated writable directory for profile/config files."""
    return tmp_path


@pytest.fixture()
def profile_manager(tmp_config_dir: Path) -> ProfileManager:
    """A ``ProfileManager`` rooted in the per-test config directory."""
    return ProfileManager(tmp_config_dir)

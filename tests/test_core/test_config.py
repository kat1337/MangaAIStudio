"""Config round-trip tests for ProfileManager.

Verifies the vendored PanelCleaner config system persists profiles to INI
(``.profile`` files via ConfigUpdater, per D-05) and that a ``Profile`` can be
materialized into a ``Config`` via the ConfigUpdater round-trip.
"""

from __future__ import annotations

from pathlib import Path

from panelcleaner.config import Config, Profile


def test_profile_round_trip(profile_manager, tmp_config_dir: Path) -> None:
    """A default Profile round-trips through an INI .profile file."""
    profile = profile_manager.default_profile()
    saved_path = profile_manager.save_profile(profile, "default")

    assert saved_path == tmp_config_dir / "default.profile"
    assert saved_path.is_file()

    reloaded = profile_manager.load_profile("default")
    assert reloaded.general is not None


def test_profile_to_config(profile_manager) -> None:
    """profile_to_config returns a Config whose current_profile is the profile."""
    profile = profile_manager.default_profile()
    config = profile_manager.profile_to_config(profile)

    assert isinstance(config, Config)
    assert hasattr(config, "current_profile")
    assert config.current_profile is profile
    assert config.current_profile.general is not None

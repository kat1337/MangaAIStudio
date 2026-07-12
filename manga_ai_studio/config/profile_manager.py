"""ProfileManager — wrapper around the vendored PanelCleaner config system.

Per CONTEXT.md D-05 and D-06, settings persist via ConfigUpdater (INI-style
``.profile`` files), NOT JSON. This wrapper exposes the three load-bearing
operations the rest of the codebase needs:

- write a ``Profile`` to disk  -> ``Profile.safe_write(path)``  (config.py:974)
- read a ``Profile`` from disk -> ``Profile.load(path)``         (config.py:1015, classmethod)
- materialize a ``Profile`` into a ``Config`` -> ``Config.from_config_updater`` (config.py:1310)

Note: ``Profile.load`` swallows exceptions internally and returns a default
``Profile()`` on failure (config.py:1031-1034). We intentionally preserve that
behavior and do NOT add a try/except here.
"""

from __future__ import annotations

from pathlib import Path

from panelcleaner.config import Config, Profile


class ProfileManager:
    """Manages PanelCleaner profiles with full INI/ConfigUpdater compatibility."""

    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        # Default Config; per-profile state is loaded via load_profile().
        self.config = Config()

    def save_profile(self, profile: Profile, name: str) -> Path:
        """Save a profile as an INI ``.profile`` file (PanelCleaner-compatible).

        Uses ``Profile.safe_write`` (atomic temp-file + move), NOT ``Config.save``
        — ``save`` lives on ``Config`` (config.py:1217), not on ``Profile``.
        """
        profile_path = self.config_dir / f"{name}.profile"
        profile.safe_write(profile_path)
        return profile_path

    def load_profile(self, name: str) -> Profile:
        """Load a profile from an INI ``.profile`` file.

        ``Profile.load`` is a classmethod (config.py:1015). On any read failure
        it logs and returns a fresh default ``Profile()`` (config.py:1031-1034);
        we preserve that behavior and do not wrap it.
        """
        profile_path = self.config_dir / f"{name}.profile"
        return Profile.load(profile_path)

    def profile_to_config(self, profile: Profile) -> Config:
        """Materialize a ``Profile`` into a ``Config``.

        A ``Config`` (config.py:1066) holds application-level settings plus a
        ``current_profile`` attribute that IS a ``Profile``. The canonical way to
        attach a profile to a config is to build a default ``Config`` and assign
        the profile to ``current_profile`` — this mirrors ``Config.load_profile``
        (config.py:1395), which does exactly ``self.current_profile = Profile()``.

        Note: ``Config.from_config_updater`` (config.py:1310) is NOT the right
        tool here — it parses a full application ``config.ini`` (which must
        contain a ``Saved Profiles`` section, line 1328) and raises ``KeyError``
        when handed a bare ``Profile.bundle_config()`` output, which only carries
        the per-profile sections.
        """
        config = Config()
        config.current_profile = profile
        return config

    def default_profile(self) -> Profile:
        """Return a fresh ``Profile`` populated with PanelCleaner defaults."""
        return Profile()

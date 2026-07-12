"""Application configuration.

Wraps the vendored PanelCleaner config system (INI/ConfigUpdater per
CONTEXT.md D-05) so application code depends on ``ProfileManager`` rather than
the vendored classes directly.
"""

from manga_ai_studio.config.profile_manager import ProfileManager

__all__ = ["ProfileManager"]

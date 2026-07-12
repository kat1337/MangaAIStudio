"""Vendored PanelCleaner (GPL v3) source.

This package contains PanelCleaner source adapted near-verbatim under the
GPL v3. See the project README and LICENSE for licensing details.
"""

# These attributes are imported by the vendored cli_utils.py
# (``from panelcleaner import __display_name__, __version__, __program__``).
# Values match the upstream PanelCleaner package root so vendored logic that
# references them (e.g. config-path resolution, version strings) behaves
# identically.
__program__ = "panelcleaner"
__version__ = "2.11.11"
__display_name__ = "Panel Cleaner"

"""Dark Fusion theme for Manga AI Studio.

Per UI-SPEC §Design System, the dark ``QPalette`` is applied ONCE at startup
(not per-widget) via ``QApplication.setPalette(build_dark_palette())`` after
``QApplication.setStyle("Fusion")``. See PATTERNS.md §Shared Pattern 1.

Color tokens are grounded in UI-SPEC §Color and declared here so they are not
"re-invented" elsewhere. Dominant/secondary/accent follow a 60/30/10 split.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


# --- Design tokens (UI-SPEC §Color) -----------------------------------------
DOMINANT = QColor("#232328")        # main-window chrome background (60%)
CANVAS_MATTE = QColor("#0b0b0e")    # QGraphicsView viewport background
SECONDARY = QColor("#2d2d33")       # dock/sidebar/toolbar surfaces (30%)
DIVIDER = QColor("#3a3a42")         # 1px borders between chrome regions
ACCENT = QColor("#00d4ff")          # cyan — active tool / focus / progress (10%)
TEXT_PRIMARY = QColor("#e8e8ea")    # body/label text on dark surfaces
TEXT_MUTED = QColor("#9a9aa2")      # secondary metadata / disabled labels


def build_dark_palette() -> QPalette:
    """Build the dark Fusion QPalette (UI-SPEC §Color).

    Apply once at startup via ``QApplication.setPalette(build_dark_palette())``.
    """
    palette = QPalette()

    # Window chrome.
    palette.setColor(QPalette.Window, DOMINANT)
    palette.setColor(QPalette.WindowText, TEXT_PRIMARY)

    # Bases for input widgets / lists.
    palette.setColor(QPalette.Base, SECONDARY)
    palette.setColor(QPalette.AlternateBase, DOMINANT)

    # Text.
    palette.setColor(QPalette.Text, TEXT_PRIMARY)
    palette.setColor(QPalette.ButtonText, TEXT_PRIMARY)
    palette.setColor(QPalette.ToolTipBase, SECONDARY)
    palette.setColor(QPalette.ToolTipText, TEXT_PRIMARY)

    # Highlight / selection / focus (accent reserved use #2/#3).
    palette.setColor(QPalette.Highlight, ACCENT)
    palette.setColor(QPalette.HighlightedText, QColor("#0b0b0e"))

    # Buttons.
    palette.setColor(QPalette.Button, SECONDARY)
    palette.setColor(QPalette.ButtonText, TEXT_PRIMARY)

    # Brightness / disabled.
    palette.setColor(QPalette.BrightText, QColor("#ff0000"))
    palette.setColor(QPalette.PlaceholderText, TEXT_MUTED)
    palette.setColor(QPalette.Light, DIVIDER)
    palette.setColor(QPalette.Midlight, SECONDARY)
    palette.setColor(QPalette.Mid, DIVIDER)
    palette.setColor(QPalette.Dark, DOMINANT)
    palette.setColor(QPalette.Shadow, QColor("#000000"))
    disabled_text = TEXT_MUTED
    palette.setColor(QPalette.Disabled, QPalette.WindowText, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)

    return palette

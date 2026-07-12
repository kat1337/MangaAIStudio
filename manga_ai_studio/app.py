"""Application factory.

``create_app`` constructs the ``QApplication``, applies the mandatory Fusion
style and the dark palette (UI-SPEC §Design System), and returns the app. Kept
separate from ``__main__`` so tests can construct a fresh ``QApplication``
without invoking ``app.exec()``.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtWidgets import QApplication

from manga_ai_studio.gui.theme import build_dark_palette


def create_app(argv: Optional[Sequence[str]] = None) -> QApplication:
    """Construct a QApplication with the Fusion style and dark palette applied.

    Per UI-SPEC §Design System, ``QApplication.setStyle("Fusion")`` is mandatory
    (cross-platform consistent dark rendering), and the dark palette is applied
    once at startup.

    If a ``QApplication`` singleton already exists (e.g. pytest-qt created one
    for the test session, or ``create_app`` is called twice), it is reused so we
    never raise "Please destroy the QApplication singleton before creating a new
    QApplication instance." Style and palette are (re)applied to keep the
    contract honest.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else [])
    QApplication.setStyle("Fusion")
    QApplication.setPalette(build_dark_palette())
    return app

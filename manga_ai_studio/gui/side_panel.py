"""SidePanel — the unified right-side panel of collapsible sections (plan 09-02).

Phase 9 plan 09-02 (UI-01/UI-02/D-01/D-02): ONE right-side dock ("Panel")
whose body is a vertical stack of independently collapsible
:class:`CollapsibleSection` widgets in workflow order (Detection settings →
Brush → Typesetting → Edit), replacing the tabified ``dock_tools`` +
``dock_inspector`` pair.

Design contracts (09-UI-SPEC §38):

- **Independent collapse (UI-01):** each section is a custom header+body
  widget — a checkable ``QToolButton`` header row (▸/▾ arrow + title, the
  muted 12px-Semibold section-header token style) whose ``toggled`` shows or
  hides its body via plain ``setVisible``. NO animation (QPropertyAnimation
  on heights fights QScrollArea sizing) and NO QToolBox (single-current-item
  semantics violate the independence requirement).
- **Panel-body toggle (UI-02):** a chevron ``QToolButton`` at the very top of
  the panel collapses/expands the whole scroll-area body while the dock STAYS
  DOCKED — the toggle path never touches QMainWindow dock visibility.
- **One scroll wrap (A11 rule carried over):** exactly ONE vertical-only
  ``QScrollArea`` (``setWidgetResizable(True)``, horizontal scrollbar always
  off) wraps ALL sections — never per-section scroll areas.

Per-section collapse persistence (QSettings ``sidePanel/*Expanded`` keys,
D-02) is wired by MainWindow through each section's optional ``settings_key``
(Task 3); the chevron toggle itself is session-transient and NEVER persisted.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Dark QSS for the panel chrome (UI-SPEC §Color tokens; the section-header
# typography role: 12px/600/muted #9a9aa2, min-height 28px; dividers 1px
# #3a3a42). Applied by BOTH classes so a standalone CollapsibleSection (tests)
# renders identically to one inside a SidePanel.
_PANEL_QSS = """
QToolButton#_section_header {
    background: transparent;
    border: none;
    color: #9a9aa2;
    font-weight: 600;
    font-size: 12px;
    min-height: 28px;
    padding: 4px 2px;
    text-align: left;
}
QToolButton#_section_header:hover {
    color: #e8e8ea;
}
QToolButton#panel_chevron {
    background: transparent;
    border: none;
    border-bottom: 1px solid #3a3a42;
    color: #e8e8ea;
    font-weight: 600;
    font-size: 12px;
    min-height: 26px;
    padding: 4px 8px;
    text-align: left;
}
QToolButton#panel_chevron:hover {
    color: #00d4ff;
}
QFrame#_section_divider {
    background: #3a3a42;
    border: none;
    max-height: 1px;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
"""

# Chevron glyphs (UI-SPEC §38): ▾ expanded / ▸ collapsed. The panel title
# rides the same button so the header row reads as one control.
_EXPANDED_GLYPH = "\u25be"
_COLLAPSED_GLYPH = "\u25b8"

# Edit-section secondary chrome (UI-SPEC §40): flat buttons on the panel's
# Secondary token with a 1px #3a3a42 border, hover lightens to the existing
# #34343c token. Disabled greying is Qt-native — no extra QSS state needed.
_EDIT_QSS = """
QToolButton#edit_button {
    background: #2d2d33;
    border: 1px solid #3a3a42;
    border-radius: 3px;
    color: #e8e8ea;
    padding: 5px 8px;
    text-align: center;
}
QToolButton#edit_button:hover {
    background: #34343c;
}
"""


class CollapsibleSection(QWidget):
    """A checkable-header section whose body collapses via plain setVisible.

    Members per the plan artifact contract: ``header`` (checkable QToolButton
    carrying "▸/▾ {title}"), ``body`` (the relocated content widget, e.g. the
    InspectorPanel for Typesetting), and an optional ``settings_key`` that
    Task 3's QSettings persistence writes on every user toggle.
    """

    def __init__(
        self,
        title: str,
        body: QWidget,
        parent: QWidget | None = None,
        settings_key: str | None = None,
        settings_provider: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        # D-02 persistence hook: when both are set, every USER toggle writes
        # the checked state under ``settings_key`` through the supplied
        # provider (MainWindow._settings — the single-sourced accessor). The
        # restore path deliberately does NOT round-trip through the toggle
        # handler (see restore_expanded) so seeding never re-writes.
        self.settings_key = settings_key
        self._settings_provider = settings_provider

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = QToolButton(self)
        self.header.setObjectName("_section_header")
        self.header.setCheckable(True)
        self.header.setChecked(True)  # expanded default (D-02 first run)
        self.header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        lay.addWidget(self.header)

        self.body = body
        lay.addWidget(self.body)

        # 1px #3a3a42 bottom divider per section (the _detection_divider
        # visual language from tools_panel.py).
        self._divider = QFrame(self)
        self._divider.setObjectName("_section_divider")
        self._divider.setFrameShape(QFrame.Shape.HLine)
        self._divider.setFixedHeight(1)
        lay.addWidget(self._divider)

        self.header.toggled.connect(self._on_header_toggled)
        self.setStyleSheet(_PANEL_QSS)

        self._apply_expanded(True)

    # ------------------------------------------------------------- collapse
    def _on_header_toggled(self, checked: bool) -> None:
        """Header toggled -> body visibility flip + persistence write (D-02).

        Only USER-driven toggles reach this slot; the restore path seeds via
        :meth:`restore_expanded` (signals blocked) so no spurious writes fire
        during startup.
        """
        self._apply_expanded(checked)
        if self.settings_key is not None and self._settings_provider is not None:
            self._settings_provider().setValue(self.settings_key, checked)

    def _apply_expanded(self, expanded: bool) -> None:
        """Render ``expanded``: arrow glyph + plain body setVisible (NO animation)."""
        glyph = _EXPANDED_GLYPH if expanded else _COLLAPSED_GLYPH
        self.header.setText(f"{glyph} {self.title}")
        self.body.setVisible(expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Programmatically expand/collapse (signals delivered normally)."""
        self.header.setChecked(expanded)

    def restore_expanded(self, expanded: bool) -> None:
        """Seed the restored collapse state WITHOUT writing back to QSettings.

        The build-time seed precedent (main_window's blockSignals seeding):
        header signals are blocked around ``setChecked`` so the toggled slot
        — whose job is persisting user changes — never fires during restore;
        the visual state is applied directly.
        """
        was = self.header.blockSignals(True)
        self.header.setChecked(expanded)
        self.header.blockSignals(was)
        self._apply_expanded(expanded)


class EditSection(QWidget):
    """The Edit section body (plan 09-03, UI-05/D-08): six default-action
    buttons in a 2-column grid.

    Pure relocation of proven entry points — the constructor receives the SIX
    LIVE MainWindow QActions (Curves…, Crop… numeric dialog, Resize…, Rotate
    90° CW / CCW / 180°) and binds each text ``QToolButton`` with
    ``setDefaultAction``. Labels/tooltips/status-tips and the enabled-state
    gating (``_refresh_action_states``) are inherited from the actions for
    free; there is NO lambda wiring, NO re-created action, and NO new op
    logic behind any button.
    """

    def __init__(
        self,
        curves_action,
        crop_dialog_action,
        resize_action,
        rotate_cw_action,
        rotate_ccw_action,
        rotate_180_action,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("edit_section")

        grid = QGridLayout(self)
        # Secondary chrome, sm (8px) grid gaps (UI-SPEC §40); tight margins —
        # the wrapping CollapsibleSection owns the section-level spacing.
        grid.setContentsMargins(0, 0, 0, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # D-08 order: dialogs first (Curves…, Crop… dialog, Resize…), then the
        # three instant rotates. The Crop TOOL (G) is NOT here — it stays a
        # strip button (action_tool_crop); this grid binds action_crop_dialog.
        actions = [
            curves_action,
            crop_dialog_action,
            resize_action,
            rotate_cw_action,
            rotate_ccw_action,
            rotate_180_action,
        ]
        self.buttons: list[QToolButton] = []
        for i, act in enumerate(actions):
            btn = QToolButton(self)
            btn.setObjectName("edit_button")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setDefaultAction(act)
            self.buttons.append(btn)
            grid.addWidget(btn, i // 2, i % 2)

        self.setStyleSheet(_PANEL_QSS + _EDIT_QSS)


class SidePanel(QWidget):
    """The unified panel body: chevron header row + scroll-wrapped sections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("side_panel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- UI-02 chevron row: collapses/expands the whole scroll body ----
        # The DOCK stays docked — this path only flips body visibility and is
        # session-transient (never persisted; D-02 contracts per-section keys
        # only).
        self.toggle_button = QToolButton(self)
        self.toggle_button.setObjectName("panel_chevron")
        self.toggle_button.setText(f"{_EXPANDED_GLYPH} Panel")
        self.toggle_button.setToolTip("Toggle panel")
        self.toggle_button.setAccessibleName("Toggle panel")
        self.toggle_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_button.clicked.connect(self._on_toggle_clicked)
        root.addWidget(self.toggle_button)

        # ---- ONE vertical-only scroll wrap around all sections (A11 rule) —
        # copied from tools_panel.py:149-171: widgetResizable, horizontal
        # scrollbar permanently off, vertical as-needed, frame-less.
        self.body_scroll = QScrollArea(self)
        self.body_scroll.setObjectName("side_panel_body_scroll")
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.body_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        # sm (8px) contents margins + sm spacing (UI-SPEC §Spacing).
        self.body_layout.setContentsMargins(8, 8, 8, 8)
        self.body_layout.setSpacing(8)
        # Sections pin to the top; the stretch absorbs leftover height so the
        # stack never stretches its last member.
        self.body_layout.addStretch(1)
        self.body_scroll.setWidget(body)
        root.addWidget(self.body_scroll, 1)

        self.sections: list[CollapsibleSection] = []
        self._body_visible = True

        self.setStyleSheet(_PANEL_QSS)

    # -------------------------------------------------------------- sections
    def add_section(self, section: CollapsibleSection) -> None:
        """Append a CollapsibleSection (call order = workflow order, D-02).

        The count is deliberately NOT hard-coded — plan 09-03 appends the Edit
        section through this same API.
        """
        self.sections.append(section)
        # Insert BEFORE the trailing stretch.
        self.body_layout.insertWidget(self.body_layout.count() - 1, section)

    # ------------------------------------------------------- panel-body toggle
    def set_body_visible(self, visible: bool) -> None:
        """Show/hide the whole scroll body (UI-02; the dock is untouched)."""
        self._body_visible = visible
        self.body_scroll.setVisible(visible)
        glyph = _EXPANDED_GLYPH if visible else _COLLAPSED_GLYPH
        self.toggle_button.setText(f"{glyph} Panel")

    def is_body_visible(self) -> bool:
        """The session-transient body toggle state."""
        return self._body_visible

    def _on_toggle_clicked(self) -> None:
        self.set_body_visible(not self.is_body_visible())

"""GUI tests for the unified side panel (plan 09-02, UI-01/UI-02/UI-04).

Covers the plan 09-02 contract:

- ONE "Panel" dock (D-01) hosting a :class:`SidePanel` — the tabified
  ``dock_tools`` + ``dock_inspector`` pair is gone.
- The Typesetting section's body IS the existing ``InspectorPanel`` instance
  (identity — the UI-04 rename never renames the class or its signals).
- Sections collapse INDEPENDENTLY via a checkable header row (plain
  ``setVisible`` — no animation, no QToolBox).
- The chevron toggle at the top of the panel flips the whole scroll-body's
  visibility while the dock itself stays docked/visible (UI-02).
- The View menu holds ONE "Toggle Panel" action driving the same body toggle.

Visibility assertions use ``QWidget.isHidden()`` — it reports the widget's
OWN explicit hidden flag independent of ancestor visibility, so the tests
need no ``show()`` (offscreen-safe).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from manga_ai_studio.gui.side_panel import CollapsibleSection, SidePanel  # noqa: E402


def _window(qtbot, tmp_path) -> MainWindow:
    """A MainWindow over a tmp-dir ProfileManager (the detection_boxes pattern)."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _view_menu_texts(window: MainWindow) -> list[str]:
    """The View menu's action texts, resolved with wrappers held (Phase-4
    menu-membership precedent — never widget parents; the PySide6
    wrapper-lifetime quirk requires holding the bar wrappers while resolving).
    """
    texts: list[str] = []
    bar_actions = window.menuBar().actions()
    for bar_act in bar_actions:
        menu = bar_act.menu()
        if menu is not None and "View" in menu.title():
            texts = [act.text() for act in menu.actions()]
    return texts


@pytest.mark.gui
def test_panel_dock_hosts_side_panel(qtbot, tmp_path) -> None:
    """One QDockWidget titled "Panel" (objectName dock_panel) hosts a SidePanel."""
    window = _window(qtbot, tmp_path)

    assert window.dock_panel.windowTitle() == "Panel"
    assert window.dock_panel.objectName() == "dock_panel"
    panel = window.dock_panel.widget()
    assert isinstance(panel, SidePanel)


@pytest.mark.gui
def test_typesetting_section_body_is_inspector(qtbot, tmp_path) -> None:
    """The Typesetting section's body identity-equals window.inspector_panel.

    UI-04 is a USER-VISIBLE rename only — the InspectorPanel instance is
    relocated verbatim (Mixed-state machinery intact), never rebuilt.
    """
    window = _window(qtbot, tmp_path)

    titles = [s.title for s in window.side_panel.sections]
    assert "Typesetting" in titles
    ts = next(s for s in window.side_panel.sections if s.title == "Typesetting")
    assert ts.body is window.inspector_panel


@pytest.mark.gui
def test_collapsible_sections_collapse_independently(qtbot) -> None:
    """Toggling one section's checkable header flips ONLY that body's visibility.

    Both sections start expanded (checked headers, visible bodies); collapsing
    A leaves B untouched and vice versa — the UI-01 independence contract that
    rules out QToolBox.
    """
    body_a = QWidget()
    body_b = QWidget()
    sec_a = CollapsibleSection("A", body_a)
    sec_b = CollapsibleSection("B", body_b)
    panel = SidePanel()
    panel.add_section(sec_a)
    panel.add_section(sec_b)
    qtbot.addWidget(panel)

    # Expanded by default (D-02 first-run contract).
    assert not body_a.isHidden()
    assert not body_b.isHidden()

    # Collapse A: only A's body hides.
    sec_a.header.setChecked(False)
    assert body_a.isHidden()
    assert not body_b.isHidden()

    # Collapse B too, then re-expand A: B stays collapsed.
    sec_b.header.setChecked(False)
    assert body_b.isHidden()
    sec_a.header.setChecked(True)
    assert not body_a.isHidden()
    assert body_b.isHidden()

    # set_expanded drives the same mechanism.
    sec_b.set_expanded(True)
    assert not body_b.isHidden()
    sec_b.set_expanded(False)
    assert body_b.isHidden()


@pytest.mark.gui
def test_chevron_toggles_body_dock_stays_put(qtbot, tmp_path) -> None:
    """The chevron flips the whole scroll body; the dock itself never hides.

    UI-02: the panel-body toggle must not fight QMainWindow dock visibility —
    ``dock_panel`` keeps its own hidden flag False through both directions.
    """
    window = _window(qtbot, tmp_path)
    panel = window.side_panel

    assert panel.is_body_visible()
    assert not panel.body_scroll.isHidden()

    panel.toggle_button.click()
    assert not panel.is_body_visible()
    assert panel.body_scroll.isHidden()
    # The dock stays docked/visible — the toggle path never hides it.
    assert not window.dock_panel.isHidden()

    panel.toggle_button.click()
    assert panel.is_body_visible()
    assert not panel.body_scroll.isHidden()


@pytest.mark.gui
def test_view_menu_toggle_panel_drives_body(qtbot, tmp_path) -> None:
    """The View menu holds ONE "Toggle Panel" action driving the same toggle."""
    window = _window(qtbot, tmp_path)

    texts = _view_menu_texts(window)
    assert "Toggle Panel" in texts
    assert "Toggle Tools" not in texts
    assert "Toggle Inspector" not in texts
    # The Sidebar toggle survives untouched.
    assert "Toggle Sidebar" in texts

    # Drive the same action the menu item fronts (identity: window attribute).
    toggle = window.action_toggle_panel
    assert toggle.text() == "Toggle Panel"
    toggle.trigger()
    assert window.side_panel.body_scroll.isHidden()
    toggle.trigger()
    assert not window.side_panel.body_scroll.isHidden()


# ---------------------------------------------------------------------------
# Task 3 — collapse persistence (D-02, QSettings sidePanel/*Expanded keys)
# ---------------------------------------------------------------------------


from PySide6.QtCore import QSettings  # noqa: E402


_SECTION_KEYS = [
    "sidePanel/detectionExpanded",
    "sidePanel/brushExpanded",
    "sidePanel/typesettingExpanded",
]


def _patched_settings(ini):
    return lambda self: QSettings(str(ini), QSettings.Format.IniFormat)


def _stored(window, key: str):
    return window._settings().value(key, None)


@pytest.mark.gui
def test_first_run_all_sections_expanded(qtbot, tmp_path, monkeypatch) -> None:
    """A fresh QSettings store (no sidePanel/* keys) boots ALL sections expanded."""
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(MainWindow, "_settings", _patched_settings(ini))

    window = _window(qtbot, tmp_path)

    for section in window.side_panel.sections:
        assert not section.body.isHidden(), f"{section.title} should be expanded"
        assert section.header.isChecked()


@pytest.mark.gui
def test_collapse_round_trips_through_qsettings(qtbot, tmp_path, monkeypatch) -> None:
    """Collapsing Brush persists; a rebuilt window restores exactly that section
    collapsed (the D-02 restart contract)."""
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(MainWindow, "_settings", _patched_settings(ini))

    window = _window(qtbot, tmp_path)
    # USER toggle path: the header's toggled slot writes the key.
    window.section_brush.header.setChecked(False)
    assert _stored(window, "sidePanel/brushExpanded") is False
    del window

    # "Second session": a fresh MainWindow over the same INI.
    window2 = _window(qtbot, tmp_path)
    assert window2.section_brush.body.isHidden(), "Brush should restore collapsed"
    assert not window2.section_detection.body.isHidden()
    assert not window2.section_typesetting.body.isHidden()
    # And the restored state round-trips again (toggle back on).
    window2.section_brush.header.setChecked(True)
    assert _stored(window2, "sidePanel/brushExpanded") is True


@pytest.mark.gui
def test_malformed_stored_value_falls_back_to_expanded(qtbot, tmp_path, monkeypatch) -> None:
    """A stored value outside the accepted truthy set (T-09b-01) falls back to
    expanded — the tolerant parse accepts only true/1/yes/on."""
    ini = tmp_path / "settings.ini"
    pre = QSettings(str(ini), QSettings.Format.IniFormat)
    pre.setValue("sidePanel/brushExpanded", "banana")
    pre.sync()
    del pre
    monkeypatch.setattr(MainWindow, "_settings", _patched_settings(ini))

    window = _window(qtbot, tmp_path)
    assert not window.section_brush.body.isHidden()


@pytest.mark.gui
def test_chevron_toggle_writes_no_settings_keys(qtbot, tmp_path, monkeypatch) -> None:
    """The chevron/panel-body toggle is session-transient (UI-SPEC §38): zero
    writes to any sidePanel/* key, asserted by comparing stored values."""
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(MainWindow, "_settings", _patched_settings(ini))

    window = _window(qtbot, tmp_path)
    before = {k: _stored(window, k) for k in _SECTION_KEYS}

    window.side_panel.toggle_button.click()
    window.side_panel.toggle_button.click()
    window.side_panel.set_body_visible(False)

    after = {k: _stored(window, k) for k in _SECTION_KEYS}
    assert before == after == {k: None for k in _SECTION_KEYS}


@pytest.mark.gui
def test_rename_sweep_positive_assertions(qtbot, tmp_path) -> None:
    """UI-04 positive rename assertions: dock title 'Panel', Typesetting
    section title, View menu holds 'Toggle Panel' (no negative-grep)."""
    window = _window(qtbot, tmp_path)

    assert window.dock_panel.windowTitle() == "Panel"
    ts = next(
        s for s in window.side_panel.sections if s.title == "Typesetting"
    )
    assert ts.header.text().endswith("Typesetting")
    texts = _view_menu_texts(window)
    assert "Toggle Panel" in texts

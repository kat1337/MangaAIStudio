"""GUI tests for the Phase 8 detection-settings section (plan 08-05, MASK-01/02).

Covers the ToolsPanel's new "Detection settings" section (UI-SPEC surface 36,
D-05/D-06): the relocated Detect Boxes toggle, the nine masker parameters
each with its PanelCleaner INI-comment tooltip, the QScrollArea body wrap
(A11), and the D-15 extended paint-tool tooltips.

Task 1 owns the widget-level tests (construct ``ToolsPanel`` directly — no
MainWindow needed): ``set_masker_values`` population without signal re-emission,
the radius slider<->spinbox mirror's single ``dilation_changed`` emission, the
Tab-chain focus reachability of every section control, and the four paint-tool
+ Crop tooltip contract from UI-SPEC §Copywriting.

Task 2 (in the same file) extends this with the MainWindow wiring tests:
toggle relocation out of the Tools menu, QSettings view-state persistence,
profile INI save-through, and the checkbox<->action bidirectional sync.

These tests need a display; on headless CI they skip via ``importorskip``.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from panelcleaner.config import MaskerConfig  # noqa: E402

from manga_ai_studio.gui.tools_panel import ToolsPanel  # noqa: E402


# ---------------------------------------------------------------------------
# Task 1 — widget-level tests (ToolsPanel constructed directly)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_set_masker_values_populates_without_emission(qtbot) -> None:
    """``set_masker_values`` fills the controls from a MaskerConfig WITHOUT
    re-emitting ``dilation_changed``/``std_dev_threshold_changed`` (spy count 0).

    MainWindow loads the persisted profile at startup via this method; signal
    re-emission would save the profile back redundantly on boot.
    """
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    dil_spy = Mock()
    thresh_spy = Mock()
    panel.dilation_changed.connect(dil_spy)
    panel.std_dev_threshold_changed.connect(thresh_spy)

    mc = MaskerConfig(
        mask_dilation_radius=5,
        mask_max_standard_deviation=20.0,
        mask_growth_step_pixels=3,
        mask_growth_steps=12,
        min_mask_thickness=6,
        off_white_max_threshold=250,
        mask_improvement_threshold=0.25,
        allow_colored_masks=False,
        mask_selection_fast=True,
    )
    panel.set_masker_values(mc, detect_boxes=False)

    assert panel.dilation_slider.value() == 5
    assert panel.dilation_spinbox.value() == 5
    assert panel.std_dev_threshold_spin.value() == 20.0
    assert panel.growth_step_spin.value() == 3
    assert panel.growth_steps_spin.value() == 12
    assert panel.min_thickness_spin.value() == 6
    assert panel.off_white_spin.value() == 250
    assert panel.improvement_spin.value() == 0.25
    assert panel.allow_colored_check.isChecked() is False
    assert panel.fast_selection_check.isChecked() is True
    assert panel.detect_checkbox.isChecked() is False

    dil_spy.assert_not_called()
    thresh_spy.assert_not_called()


@pytest.mark.gui
def test_radius_slider_move_emits_once_and_mirrors(qtbot) -> None:
    """Moving the radius slider to 7 emits ``dilation_changed(7)`` exactly once
    and the spinbox shows 7; setting the spinbox emits once in reverse."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    spy = Mock()
    panel.dilation_changed.connect(spy)

    # Slider -> spinbox: one emission, mirrored value.
    panel.dilation_slider.setValue(7)
    spy.assert_called_once_with(7)
    assert panel.dilation_spinbox.value() == 7

    # Spinbox -> slider: one emission, mirrored value.
    spy.reset_mock()
    panel.dilation_spinbox.setValue(3)
    spy.assert_called_once_with(3)
    assert panel.dilation_slider.value() == 3

    # The mirror write never loops back into a second emission.
    spy.reset_mock()
    panel.dilation_slider.setValue(5)
    spy.assert_called_once_with(5)
    assert panel.dilation_spinbox.value() == 5


@pytest.mark.gui
def test_all_section_controls_reachable_in_tab_chain(qtbot) -> None:
    """Every detection-settings control is focusable and reachable via the
    dock Tab chain (the 05-UI-SPEC keyboard-reachability contract; the radius
    slider/spinbox pair is one contracted row, both widgets are members).

    Walks ``QWidget.nextInFocusChain`` from the panel — the deterministic,
    show-free traversal of Qt's focus chain (covers the QScrollArea body).
    """
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    controls = [
        panel.detect_checkbox,
        panel.dilation_slider,
        panel.dilation_spinbox,
        panel.std_dev_threshold_spin,
        panel.growth_step_spin,
        panel.growth_steps_spin,
        panel.min_thickness_spin,
        panel.off_white_spin,
        panel.improvement_spin,
        panel.allow_colored_check,
        panel.fast_selection_check,
    ]

    chain: list = []
    cur = panel
    seen: set[int] = set()
    for _ in range(300):
        cur = cur.nextInFocusChain()
        if id(cur) in seen:
            break
        seen.add(id(cur))
        chain.append(cur)

    for c in controls:
        assert c in chain, (
            f"{type(c).__name__} ('{c.toolTip()[:40]}') is not reachable in the "
            "ToolsPanel Tab chain"
        )


@pytest.mark.gui
def test_paint_tool_tooltips_extended_crop_unchanged(qtbot) -> None:
    """The four paint-tool action tooltips carry the D-15 Alt clause VERBATIM
    from UI-SPEC §Copywriting; Crop's tooltip is byte-identical to its
    pre-Phase-8 text (D-17 — crop keeps today's box behavior)."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    assert panel.action_brush.toolTip() == (
        "Brush tool (B) — paints under text boxes; hold Alt to select or move"
        " a box."
    )
    assert panel.action_rectangle.toolTip() == (
        "Rectangle tool (R) — paints under text boxes; hold Alt to select or"
        " move a box."
    )
    assert panel.action_lasso.toolTip() == (
        "Lasso tool (L) — paints under text boxes; hold Alt to select or move"
        " a box."
    )
    assert panel.action_eraser.toolTip() == (
        "Eraser tool (E) — paints under text boxes; hold Alt to select or move"
        " a box."
    )
    assert panel.action_crop.toolTip() == (
        "Crop tool (G): drag a rectangle on the page, Enter applies,"
        " Esc cancels."
    )


@pytest.mark.gui
def test_section_defaults_match_ui_spec(qtbot) -> None:
    """The section controls boot at the UI-SPEC §36 declared ranges + defaults
    (D-09): radius 0..10/2, threshold 0..100/15, fit params at their vendored
    defaults, Detect Boxes + Allow colored on, Fast selection off."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)

    # Detect Boxes toggle (D-05): default checked (UI-SPEC A1).
    assert panel.detect_checkbox.isChecked() is True

    # Dilation radius (D-09): 0..10, default 2.
    assert panel.dilation_slider.minimum() == 0
    assert panel.dilation_slider.maximum() == 10
    assert panel.dilation_slider.value() == 2
    assert panel.dilation_spinbox.value() == 2
    assert panel.dilation_spinbox.suffix() == " px"

    # Std-dev threshold: 0..100, step 0.5, 1 decimal, default 15.
    assert panel.std_dev_threshold_spin.minimum() == 0
    assert panel.std_dev_threshold_spin.maximum() == 100
    assert panel.std_dev_threshold_spin.singleStep() == 0.5
    assert panel.std_dev_threshold_spin.decimals() == 1
    assert panel.std_dev_threshold_spin.value() == 15

    # The seven next-detect fit params at vendored defaults.
    assert (panel.growth_step_spin.minimum(), panel.growth_step_spin.maximum()) == (0, 20)
    assert panel.growth_step_spin.value() == 2
    assert panel.growth_steps_spin.value() == 11
    assert panel.min_thickness_spin.value() == 4
    assert panel.off_white_spin.value() == 240
    assert panel.improvement_spin.value() == 0.10
    assert panel.allow_colored_check.isChecked() is True
    assert panel.fast_selection_check.isChecked() is False

    # Every control carries a non-empty PanelCleaner-derived tooltip.
    for c in controls_for(panel):
        assert c.toolTip(), f"{type(c).__name__} has an empty tooltip"


def controls_for(panel: ToolsPanel) -> list:
    """The ten section controls (the radius pair is one row, both widgets)."""
    return [
        panel.detect_checkbox,
        panel.dilation_slider,
        panel.dilation_spinbox,
        panel.std_dev_threshold_spin,
        panel.growth_step_spin,
        panel.growth_steps_spin,
        panel.min_thickness_spin,
        panel.off_white_spin,
        panel.improvement_spin,
        panel.allow_colored_check,
        panel.fast_selection_check,
    ]


# ---------------------------------------------------------------------------
# Task 2 — MainWindow wiring tests (toggle relocation, persistence, save-through)
# ---------------------------------------------------------------------------


from PySide6.QtCore import QSettings  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _window(qtbot, tmp_path) -> MainWindow:
    """A MainWindow over a tmp-dir ProfileManager (the detection_boxes pattern)."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _isolate_settings(window, tmp_path, monkeypatch) -> None:
    """Point the window's QSettings at a throwaway INI (never the real one).

    Mirrors ``tests/test_gui_detection_boxes.py::_isolate_settings`` — the
    view-state persistence tests must never touch the user's registry.
    """
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(
        window,
        "_settings",
        lambda: QSettings(str(ini), QSettings.Format.IniFormat),
    )


def _tools_menu_texts(window: MainWindow) -> list[str] | None:
    """The Tools menu's action texts, or None if the menu is absent.

    Holds the ``QMenuBar.actions()`` wrappers while resolving the menu and its
    actions — temporary wrappers GC-delete the C++ QMenu (the 06-05 PySide6
    wrapper-lifetime precedent in STATE.md).
    """
    bar_actions = window.menuBar().actions()
    for bar_act in bar_actions:
        menu = bar_act.menu()
        if menu is not None and "Tools" in menu.title():
            menu_actions = menu.actions()
            return [act.text() for act in menu_actions]
    return None


@pytest.mark.gui
def test_dilation_change_updates_profile_and_ini_round_trips(
    qtbot, tmp_path
) -> None:
    """Moving the radius slider 0->7 updates ``profile.masker.mask_dilation_radius``
    AND the INI on disk round-trips through a second ProfileManager (D-10)."""
    window = _window(qtbot, tmp_path)

    window.tools_panel.dilation_slider.setValue(7)

    pm = window.profile_manager
    assert pm.config.current_profile.masker.mask_dilation_radius == 7

    # The "default" profile INI was written by _save_masker_profile; a fresh
    # manager over the same dir = a new app session.
    fresh = ProfileManager(tmp_path)
    fresh.load_profile("default")
    assert fresh.config.current_profile.masker.mask_dilation_radius == 7


@pytest.mark.gui
def test_std_dev_threshold_change_persists(qtbot, tmp_path) -> None:
    """The LIVE gate threshold change persists to the profile + INI (D-12)."""
    window = _window(qtbot, tmp_path)

    window.tools_panel.std_dev_threshold_spin.setValue(30.0)

    pm = window.profile_manager
    assert pm.config.current_profile.masker.mask_max_standard_deviation == 30.0

    fresh = ProfileManager(tmp_path)
    fresh.load_profile("default")
    assert fresh.config.current_profile.masker.mask_max_standard_deviation == 30.0


@pytest.mark.gui
def test_masker_params_change_persists_once(qtbot, tmp_path) -> None:
    """Any of the seven next-detect controls flips its profile field and the
    INI round-trips (one shared persist fate, UI-SPEC §36)."""
    window = _window(qtbot, tmp_path)

    window.tools_panel.growth_steps_spin.setValue(25)
    window.tools_panel.allow_colored_check.setChecked(False)

    pm = window.profile_manager
    assert pm.config.current_profile.masker.mask_growth_steps == 25
    assert pm.config.current_profile.masker.allow_colored_masks is False

    fresh = ProfileManager(tmp_path)
    fresh.load_profile("default")
    assert fresh.config.current_profile.masker.mask_growth_steps == 25
    assert fresh.config.current_profile.masker.allow_colored_masks is False


@pytest.mark.gui
def test_detect_boxes_removed_from_tools_menu_action_kept(qtbot, tmp_path) -> None:
    """A8: the Tools menu no longer contains a Detect Boxes action, while
    ``action_detect_boxes_mode`` (the state holder) still toggles and drives
    the dock checkbox both ways."""
    window = _window(qtbot, tmp_path)

    texts = _tools_menu_texts(window)
    assert texts is not None, "Tools menu not found"
    assert "Detect Boxes" not in texts

    # The state holder lives on (read by _on_detection_finished) and syncs the
    # dock checkbox via the action.toggled connection back.
    window.action_detect_boxes_mode.setChecked(False)
    assert window.tools_panel.detect_checkbox.isChecked() is False
    window.action_detect_boxes_mode.setChecked(True)
    assert window.tools_panel.detect_checkbox.isChecked() is True


@pytest.mark.gui
def test_checkbox_toggle_syncs_action_and_persists_qsettings(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Toggling the dock checkbox flips ``action_detect_boxes_mode`` AND
    persists QSettings ``detectBoxesMode`` (A7 view-state, isolated INI)."""
    window = _window(qtbot, tmp_path)
    _isolate_settings(window, tmp_path, monkeypatch)

    window.tools_panel.detect_checkbox.setChecked(False)
    assert window.action_detect_boxes_mode.isChecked() is False
    assert window._settings().value("detectBoxesMode") is False

    window.tools_panel.detect_checkbox.setChecked(True)
    assert window.action_detect_boxes_mode.isChecked() is True
    assert window._settings().value("detectBoxesMode") is True


@pytest.mark.gui
def test_startup_renders_persisted_profile_and_qsettings(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Startup renders the persisted profile masker values + the persisted
    Detect Boxes QSettings view-state (D-10 + A7 — the 08-01 load chain)."""
    # Seed a profile INI with non-default radius/threshold.
    seed = ProfileManager(tmp_path)
    prof = seed.default_profile()
    prof.masker.mask_dilation_radius = 7
    prof.masker.mask_max_standard_deviation = 20.0
    seed.save_profile(prof, "default")

    # Seed the isolated QSettings INI with Detect Boxes OFF.
    ini = tmp_path / "settings.ini"
    pre = QSettings(str(ini), QSettings.Format.IniFormat)
    pre.setValue("detectBoxesMode", False)
    del pre

    # Patch BEFORE construction so the startup read uses the temp INI.
    monkeypatch.setattr(
        MainWindow,
        "_settings",
        lambda self: QSettings(str(ini), QSettings.Format.IniFormat),
    )

    pm = ProfileManager(tmp_path)
    pm.load_profile("default")  # the __main__ startup load (08-01)
    window = MainWindow(pm)
    qtbot.addWidget(window)

    assert window.tools_panel.dilation_spinbox.value() == 7
    assert window.tools_panel.std_dev_threshold_spin.value() == 20.0
    assert window.tools_panel.detect_checkbox.isChecked() is False
    assert window.action_detect_boxes_mode.isChecked() is False


@pytest.mark.gui
def test_startup_defaults_detect_boxes_on_when_no_key(
    qtbot, tmp_path, monkeypatch
) -> None:
    """A fresh session with no saved ``detectBoxesMode`` key boots with Detect
    Boxes ON (UI-SPEC A1 default checked)."""
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(
        MainWindow,
        "_settings",
        lambda self: QSettings(str(ini), QSettings.Format.IniFormat),
    )

    pm = ProfileManager(tmp_path)  # no seed -> defaults
    window = MainWindow(pm)
    qtbot.addWidget(window)

    assert window.tools_panel.detect_checkbox.isChecked() is True
    assert window.action_detect_boxes_mode.isChecked() is True
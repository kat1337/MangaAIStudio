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
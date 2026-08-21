"""GUI tests for ToolsPanel max LaMa size control + threshold tooltip (08.1-03 D-05).

Covers the detection settings max_inpaint_spin (512..8192, default 2048, suffix px,
tooltip) plus the inverted threshold tooltip copy, and the masker_values /
set_masker_values round-trip with blockSignals mirror and legacy fallback.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QSpinBox  # noqa: E402

from panelcleaner.config import MaskerConfig  # noqa: E402

from manga_ai_studio.gui.tools_panel import ToolsPanel  # noqa: E402


@pytest.mark.gui
def test_max_inpaint_spin_exists_with_correct_range_and_tooltip(qtbot) -> None:
    """Max inpaint spin: 512..8192, default 2048, suffix px, tooltip."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "max_inpaint_spin")
    spin = panel.max_inpaint_spin
    assert isinstance(spin, QSpinBox)
    assert spin.minimum() == 512
    assert spin.maximum() == 8192
    assert spin.value() == 2048
    assert spin.suffix() == " px"
    assert "Maximum LaMa input size" in spin.toolTip()
    assert "patched" in spin.toolTip().lower() or "caps memory" in spin.toolTip().lower()


@pytest.mark.gui
def test_threshold_tooltip_inverted(qtbot) -> None:
    """Std-dev threshold tooltip must contain inverted copy (color-filled / AI-inpainted)."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    tip = panel.std_dev_threshold_spin.toolTip()
    assert "color-filled" in tip
    assert "AI-inpainted" in tip
    # Old copy must be gone
    assert "Boxes above this are skipped" not in tip


@pytest.mark.gui
def test_masker_values_includes_max_inpaint_resolution(qtbot) -> None:
    """masker_values includes max_inpaint_resolution from the spin."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    panel.max_inpaint_spin.setValue(3000)
    vals = panel.masker_values()
    assert "max_inpaint_resolution" in vals
    assert vals["max_inpaint_resolution"] == 3000


@pytest.mark.gui
def test_set_masker_values_restores_with_blocksignals(qtbot) -> None:
    """set_masker_values restores max_inpaint_resolution with blockSignals (no re-emit)."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    spy = Mock()
    panel.masker_params_changed.connect(spy)
    mc = MaskerConfig(max_inpaint_resolution=3000, mask_max_standard_deviation=20.0)
    panel.set_masker_values(mc, detect_boxes=True)
    assert panel.max_inpaint_spin.value() == 3000
    assert panel.std_dev_threshold_spin.value() == 20.0
    spy.assert_not_called()

    # Changing the spin after should emit once via _on_fit_param_changed
    spy.reset_mock()
    panel.max_inpaint_spin.setValue(4096)
    spy.assert_called_once()


@pytest.mark.gui
def test_set_masker_values_fallback_to_2048_when_missing(qtbot) -> None:
    """Legacy masker_conf without max_inpaint_resolution falls back to 2048."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    # Create a conf and delete the attribute to simulate legacy INI
    mc = MaskerConfig()
    # Simulate missing key by using a simple object without the attr
    class LegacyConf:
        mask_dilation_radius = 2
        mask_max_standard_deviation = 15.0
        mask_growth_step_pixels = 2
        mask_growth_steps = 11
        min_mask_thickness = 4
        off_white_max_threshold = 240
        mask_improvement_threshold = 0.1
        allow_colored_masks = True
        mask_selection_fast = False

    legacy = LegacyConf()
    panel.set_masker_values(legacy, detect_boxes=True)
    assert panel.max_inpaint_spin.value() == 2048


@pytest.mark.gui
def test_max_inpaint_spin_reachable_in_tab_chain(qtbot) -> None:
    """Max inpaint spin is focusable and reachable via Tab chain."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    chain: list = []
    cur = panel
    seen: set[int] = set()
    for _ in range(400):
        cur = cur.nextInFocusChain()
        if id(cur) in seen:
            break
        seen.add(id(cur))
        chain.append(cur)
    assert panel.max_inpaint_spin in chain
    assert panel.std_dev_threshold_spin in chain

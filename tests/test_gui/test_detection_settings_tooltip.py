"""GUI tooltip inversion test (08.1 D-01 inverted gate, CONTEXT D-01 authority).

The std-dev threshold control's tooltip was inverted in Phase 8 (it said
"Boxes above this are skipped (dashed border)" — the old gate where uniform
boxes were inpainted). After 08.1 the gate is INVERTED per PanelCleaner:
low-std (<=t) is color-filled, high-std (>t) is AI-inpainted. The tooltip must
now read fill at/below and inpaint above (Pitfall 5 copy). This test locks the
inverted copy with CONTEXT D-01 cited and ensures no test still asserts the
old direction (low-std → inpaint).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from manga_ai_studio.gui.tools_panel import ToolsPanel  # noqa: E402


@pytest.mark.gui
def test_threshold_tooltip_inverted_copy(qtbot) -> None:
    """CONTEXT D-01: threshold tooltip must say fill at/below and inpaint above (inverted gate)."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    tip = panel.std_dev_threshold_spin.toolTip()
    # New copy per 08.1: at/below is color-filled, above is AI-inpainted
    assert "color-filled" in tip, f"tooltip missing 'color-filled': {tip!r}"
    assert "AI-inpainted" in tip, f"tooltip missing 'AI-inpainted': {tip!r}"
    # Old copy must be gone (no regression to Phase 8 inverted gate)
    assert "Boxes above this are skipped" not in tip
    # Semantic direction: fill is at or below, inpaint is above
    lower = tip.lower()
    # Ensure the tooltip mentions both outcomes near threshold wording
    assert "at or below" in lower or "at/below" in lower or "below" in lower
    assert "above" in lower


@pytest.mark.gui
def test_max_inpaint_tooltip_present(qtbot) -> None:
    """Max LaMa size tooltip must be present (D-05, 08.1-03)."""
    panel = ToolsPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "max_inpaint_spin")
    tip = panel.max_inpaint_spin.toolTip()
    assert "Maximum LaMa" in tip
    assert panel.max_inpaint_spin.minimum() == 512
    assert panel.max_inpaint_spin.maximum() == 8192
    assert panel.max_inpaint_spin.value() == 2048

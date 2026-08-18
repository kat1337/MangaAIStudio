"""GUI tests for the Inspector Inpaint override + Std dev rows (plan 08-08).

Mirrors the ``tests/test_gui_inspector_styling.py`` conventions (``importorskip``
+ ``qtbot`` + ``@pytest.mark.gui`` + real ``InspectorPanel`` instances). This
module covers the D-13/D-14 override field (UI-SPEC §38): the two new rows
exist after Origin; single-box population maps the tri-state model values
(None / "always" / "never") to the Auto / Always / Never display entries; the
read-only Std dev row shows ``{value:.1f}`` or the em dash; a multi-selection
with differing values shows the dynamically-added "Mixed" sentinel while equal
values show the common value; the row stays ENABLED in multi-select (A5 — an
edit-all flag); the sentinel NEVER emits a commit; and the WR-01 loaded-memory
guard suppresses spurious commits on load.

The MainWindow-side grouped commit (one BOXES snapshot, recompose, border
refresh, status flash) is covered by Task 2 of this plan in the same file.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QComboBox, QLabel  # noqa: E402

from manga_ai_studio.core.box_model import USER, PageBox  # noqa: E402
from manga_ai_studio.gui.inspector_panel import InspectorPanel  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


def _make_inspector(qtbot) -> InspectorPanel:
    """Build an InspectorPanel added to qtbot (so it can parent widgets)."""
    panel = InspectorPanel()
    qtbot.addWidget(panel)
    return panel


def _pb(
    override=None,
    std_dev=None,
    x1: int = 10,
    y1: int = 20,
    x2: int = 210,
    y2: int = 120,
) -> PageBox:
    """A USER-origin PageBox carrying an inpaint override + std dev (D-15)."""
    pb = PageBox(box=Box(x1, y1, x2, y2), origin=USER, inpaint_override=override)
    pb.std_dev = std_dev
    return pb


def _combo_items(panel) -> list[str]:
    """The Inpaint combo's entry list in display order."""
    return [panel.inpaint_combo.itemText(i) for i in range(panel.inpaint_combo.count())]


# ===========================================================================
# Task 1 — the D-13/D-14 override surface (rows + population)
# ===========================================================================


@pytest.mark.gui
def test_inpaint_override_signal_and_entries(qtbot) -> None:
    """The class-scope Signal exists and the combo's entries are exactly
    Auto / Always / Never (plus the dynamic Mixed sentinel)."""
    panel = _make_inspector(qtbot)
    # Class-scope Signal(str) (D-13/D-14, UI-SPEC §38).
    assert hasattr(InspectorPanel, "inpaint_override_changed")
    # The empty state reset the combo to the plain entry set, Auto selected.
    assert _combo_items(panel) == ["Auto", "Always", "Never"]
    assert panel.inpaint_combo.currentText() == "Auto"
    # Widget choice A4: a QComboBox, not radio buttons.
    assert isinstance(panel.inpaint_combo, QComboBox)
    # Std dev is a read-only QLabel.
    assert isinstance(panel.std_dev_label, QLabel)


@pytest.mark.gui
@pytest.mark.parametrize(
    "override,expected",
    [
        (None, "Auto"),
        ("always", "Always"),
        ("never", "Never"),
    ],
)
def test_single_box_populates_inpaint_combo(qtbot, override, expected) -> None:
    """Single selection maps the model tri-state to the display entries."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb(override=override, std_dev=8.3))
    assert panel.inpaint_combo.currentText() == expected
    assert _combo_items(panel) == ["Auto", "Always", "Never"]
    assert panel.std_dev_label.text() == "8.3"


@pytest.mark.gui
@pytest.mark.parametrize(
    "std_dev,expected_text",
    [
        (None, "\u2014"),
        (12.35, "12.3"),
        (0.0, "0.0"),
    ],
)
def test_std_dev_row_renders_value_or_em_dash(
    qtbot, std_dev, expected_text
) -> None:
    """Std dev shows ``{value:.1f}`` or the em dash when not computed."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb(override=None, std_dev=std_dev))
    assert panel.std_dev_label.text() == expected_text


@pytest.mark.gui
def test_mixed_sentinel_display_on_differing_multi_select(qtbot) -> None:
    """Differing overrides in a multi-selection -> the dynamic "Mixed"
    sentinel entry shows; Std dev shows the em dash; the Inpaint row stays
    ENABLED (A5 — unlike the per-box content fields)."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection(
        [_pb(override="always"), _pb(override="never"), _pb(override=None)]
    )
    assert panel.inpaint_combo.currentText() == "Mixed", (
        "A differing selection must show the Mixed sentinel"
    )
    assert "Mixed" in _combo_items(panel)
    assert panel.std_dev_label.text() == "\u2014", (
        "Std dev is per-box data — never editable-all in multi-select"
    )
    assert panel.inpaint_combo.isEnabled(), (
        "the Inpaint row stays ENABLED in multi-select (A5 edit-all)"
    )


@pytest.mark.gui
def test_equal_multi_select_shows_common_value(qtbot) -> None:
    """Equal overrides -> the common value (no Mixed sentinel entry)."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection(
        [_pb(override="never"), _pb(override="never")]
    )
    assert panel.inpaint_combo.currentText() == "Never"
    assert "Mixed" not in _combo_items(panel)


@pytest.mark.gui
def test_sentinel_never_emits(qtbot) -> None:
    """The Mixed sentinel NEVER leaves the widget layer (Pitfall 7): a commit
    whose text is Mixed (even after loading a real value) carries nothing."""
    panel = _make_inspector(qtbot)
    fired: list[str] = []
    panel.connect_commit_handlers(
        lambda _t: None, lambda _t: None, lambda _n: None, lambda _v: None,
        on_inpaint_override=fired.append,
    )
    # A mixed multi-selection renders the sentinel (never a loaded real value).
    panel.load_multi_selection(
        [_pb(override="always"), _pb(override="never")]
    )
    assert panel.inpaint_combo.currentText() == "Mixed"
    # Picking a REAL value emits ("Always" -> the miulti override).
    panel.inpaint_combo.setCurrentIndex(_combo_items(panel).index("Always"))
    assert fired == ["Always"]
    # Re-selecting the Mixed sentinel must NOT emit anything (Pitfall 7).
    panel.inpaint_combo.setCurrentIndex(_combo_items(panel).index("Mixed"))
    assert fired == ["Always"], "the Mixed sentinel must never commit"


@pytest.mark.gui
def test_guard_suppresses_spurious_commits_on_load(qtbot) -> None:
    """WR-01: load_box blocks the combo's signals (no spurious commit at
    population) and an unchanged focus cycle is a no-op; only a REAL change
    emits exactly once."""
    panel = _make_inspector(qtbot)
    fired: list[str] = []
    panel.connect_commit_handlers(
        lambda _t: None, lambda _t: None, lambda _n: None, lambda _v: None,
        on_inpaint_override=fired.append,
    )
    panel.load_box(_pb(override="always", std_dev=5.0))
    assert fired == [], "loading must not re-emit the just-loaded value"
    assert panel.inpaint_combo.currentText() == "Always"
    # A no-op focus cycle (same value re-selected) is a WR-01 no-op.
    panel.inpaint_combo.setCurrentIndex(
        _combo_items(panel).index("Always")
    )
    assert fired == [], "an unchanged focus cycle must not push a BOXES snapshot"
    # A real change emits exactly once.
    panel.inpaint_combo.setCurrentIndex(
        _combo_items(panel).index("Never")
    )
    assert fired == ["Never"]

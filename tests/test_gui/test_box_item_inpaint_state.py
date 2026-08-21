"""GUI tests for BoxItem 5-state border pens (08.1-03 D-04/D-05).

Extends the 08-06 four-state contract to the 08.1 five-state vocabulary
(plus None backward-compat): will_fill (Auto uniform) vs will_inpaint (Auto complex)
vs forced_fill vs forced_inpaint vs never, with gate_skipped dashed.

- will_fill / will_inpaint -> origin hue solid
- forced_fill / forced_inpaint -> #e8e8ea solid (both share near-white, zero new hex)
- never -> #9a9aa2 dashed
- gate_skipped -> origin hue dashed
- None -> origin hue solid (Phase 3 look)

Verifies frozensets, no new hex, pen branches shared between selected/unselected
paths, and that BoxItem never recomputes the gate (single-derivation rule).
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QGraphicsScene  # noqa: E402

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.gui.box_item import (  # noqa: E402
    BoxItem,
    _INPAINT_DASHED_STATES,
    _INPAINT_FORCED_HEX,
    _INPAINT_GREY_STATES,
    _INPAINT_NEVER_HEX,
)
from panelcleaner.structures import Box  # noqa: E402

_DETECTED_HUE = "#5fd068"
_USER_HUE = "#f5a623"
_UNSELECTED_WIDTH = 2
_SELECTED_WIDTH = 3
_DASH = [6.0, 4.0]
_TINT_MIN_ALPHA = 25
_TINT_MAX_ALPHA = 40


def _scene_with_box(pagebox: PageBox) -> tuple[QGraphicsScene, BoxItem]:
    scene = QGraphicsScene()
    item = BoxItem(pagebox)
    scene.addItem(item)
    return scene, item


def _make_box(origin: str) -> PageBox:
    return PageBox(box=Box(0, 0, 60, 60), origin=origin)


def _assert_pen(item: BoxItem, color_hex: str, style: Qt.PenStyle, width: int, dash: list[float]) -> None:
    pen = item.pen()
    assert pen.color().name().lower() == color_hex
    assert pen.style() == style
    assert int(pen.width()) == width
    assert pen.dashPattern() == dash


def _select(scene: QGraphicsScene, item: BoxItem) -> None:
    scene.clearSelection()
    item.setSelected(True)
    assert item.isSelected() is True


# ---------------------------------------------------------------------------
# Frozenset contents & zero new hex
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_frozensets_contain_expected_states() -> None:
    """Grey covers forced variants + never; dashed covers gate_skipped+never."""
    assert "forced_fill" in _INPAINT_GREY_STATES
    assert "forced_inpaint" in _INPAINT_GREY_STATES
    assert "never" in _INPAINT_GREY_STATES
    assert "gate_skipped" in _INPAINT_DASHED_STATES
    assert "never" in _INPAINT_DASHED_STATES
    # Fill states must stay solid (not in dashed)
    assert "will_fill" not in _INPAINT_DASHED_STATES
    assert "will_inpaint" not in _INPAINT_DASHED_STATES
    assert "forced_fill" not in _INPAINT_DASHED_STATES
    assert "forced_inpaint" not in _INPAINT_DASHED_STATES


@pytest.mark.gui
def test_no_new_hex_beyond_existing_palette() -> None:
    """Only #e8e8ea and #9a9aa2 appear as override greys; no new hex literal."""
    assert _INPAINT_FORCED_HEX.lower() == "#e8e8ea"
    assert _INPAINT_NEVER_HEX.lower() == "#9a9aa2"
    # Source file must not contain any other override hex (scan for #<hex> not those two nor origin hues)
    src = pathlib.Path("manga_ai_studio/gui/box_item.py").read_text(encoding="utf-8")
    # Allow origin hues and the two greys; ensure no third grey hex like #c0c0c0 etc.
    import re

    hexes = set(m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}", src))
    allowed = {"#5fd068", "#f5a623", "#e8e8ea", "#9a9aa2", "#0b0b0e", "#2d2d33", "#3a3a42", "#00d4ff", "#9a9aa2", "#e8e8ea", "#000000", "#ffffff"}
    # The file historically contains QSS colors plus the override palette; new greys would be outside allowed.
    # Check that only allowed greys in override area are the two.
    assert "#e8e8ea" in hexes
    assert "#9a9aa2" in hexes
    # Ensure no unexpected grey like #d0d0d0 introduced in override logic
    unexpected = hexes - allowed - {"#111111", "#222222"}  # some QSS uses darks, but we keep allowed set above
    # For this test, at least ensure the two override hexes are the only greys used for inpaint logic:
    # count occurrences of forced hex strings strictly in override context (already checked above)
    for h in hexes:
        assert h in allowed or h in {"#5fd068", "#f5a623", "#e8e8ea", "#9a9aa2", "#0b0b0e", "#00d4ff", "#2d2d33", "#3a3a42"}, f"unexpected hex {h}"


@pytest.mark.gui
def test_no_gate_recomputation_in_box_item() -> None:
    """BoxItem must never recompute the gate — single-derivation rule."""
    src = pathlib.Path("manga_ai_studio/gui/box_item.py").read_text(encoding="utf-8")
    # Should not reference threshold/std_dev (gate inputs)
    assert "threshold" not in src.lower()
    assert "std_dev" not in src.lower()
    # Should not import box_model threshold logic
    assert "inpaint_state" in src  # it consumes the state string via set_inpaint_state
    # Ensure no direct std_dev comparison
    assert "std" not in src.lower() or "std_dev" not in src.lower()


# ---------------------------------------------------------------------------
# Unselected pens for each state
# ---------------------------------------------------------------------------


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_will_fill_unselected_renders_origin_hue_solid(qtbot, origin, hue) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("will_fill")
    _assert_pen(item, hue, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_will_inpaint_unselected_renders_origin_hue_solid(qtbot, origin, hue) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("will_inpaint")
    _assert_pen(item, hue, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_forced_fill_unselected_renders_near_white_solid(qtbot, origin) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("forced_fill")
    _assert_pen(item, "#e8e8ea", Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_forced_inpaint_unselected_renders_near_white_solid(qtbot, origin) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("forced_inpaint")
    _assert_pen(item, "#e8e8ea", Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_forced_legacy_unselected_renders_near_white_solid(qtbot, origin) -> None:
    """Legacy 'forced' token (pre-08.1) still renders near-white for compat."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("forced")
    _assert_pen(item, "#e8e8ea", Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_gate_skipped_unselected_renders_origin_hue_dashed(qtbot, origin, hue) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("gate_skipped")
    _assert_pen(item, hue, Qt.PenStyle.CustomDashLine, _UNSELECTED_WIDTH, _DASH)


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_never_unselected_renders_muted_grey_dashed(qtbot, origin) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("never")
    _assert_pen(item, "#9a9aa2", Qt.PenStyle.CustomDashLine, _UNSELECTED_WIDTH, _DASH)


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_none_unselected_renders_phase3_look(qtbot, origin, hue) -> None:
    _scene, item = _scene_with_box(_make_box(origin))
    assert item._inpaint_state is None
    item.set_inpaint_state(None)
    _assert_pen(item, hue, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


# ---------------------------------------------------------------------------
# Selected pens — same hue/dash but width 3 + tint, handles visible
# ---------------------------------------------------------------------------


@pytest.mark.gui
@pytest.mark.parametrize("state,origin,hue", [
    ("will_fill", DETECTED, _DETECTED_HUE),
    ("will_fill", USER, _USER_HUE),
    ("will_inpaint", DETECTED, _DETECTED_HUE),
    ("will_inpaint", USER, _USER_HUE),
    ("gate_skipped", DETECTED, _DETECTED_HUE),
    ("gate_skipped", USER, _USER_HUE),
])
def test_selected_auto_states_tint_with_origin_hue(qtbot, state, origin, hue) -> None:
    scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state(state)
    _select(scene, item)
    style = Qt.PenStyle.CustomDashLine if state == "gate_skipped" else Qt.PenStyle.SolidLine
    dash = _DASH if state == "gate_skipped" else []
    _assert_pen(item, hue, style, _SELECTED_WIDTH, dash)
    tint = item.brush().color()
    assert tint.name().lower() == hue
    assert _TINT_MIN_ALPHA <= tint.alpha() <= _TINT_MAX_ALPHA


@pytest.mark.gui
@pytest.mark.parametrize("state,hex_val", [
    ("forced_fill", "#e8e8ea"),
    ("forced_inpaint", "#e8e8ea"),
    ("forced", "#e8e8ea"),
    ("never", "#9a9aa2"),
])
def test_selected_override_states_tint_with_grey(qtbot, state, hex_val) -> None:
    scene, item = _scene_with_box(_make_box(DETECTED))
    item.set_inpaint_state(state)
    _select(scene, item)
    style = Qt.PenStyle.CustomDashLine if state == "never" else Qt.PenStyle.SolidLine
    dash = _DASH if state == "never" else []
    _assert_pen(item, hex_val, style, _SELECTED_WIDTH, dash)
    tint = item.brush().color()
    assert tint.name().lower() == hex_val
    assert _TINT_MIN_ALPHA <= tint.alpha() <= _TINT_MAX_ALPHA


@pytest.mark.gui
@pytest.mark.parametrize("state", ["will_fill", "will_inpaint", "forced_fill", "forced_inpaint", "never", "gate_skipped", "forced"])
def test_selection_change_rederives_pen_with_current_state(qtbot, state) -> None:
    """itemChange re-applies with CURRENT state on select/deselect — shared path."""
    scene, item = _scene_with_box(_make_box(DETECTED))
    item.set_inpaint_state(state)
    # Determine expected hue/dash for this state
    if state in ("forced_fill", "forced_inpaint", "forced"):
        hue = "#e8e8ea"
        style_un = Qt.PenStyle.SolidLine
        dash = []
    elif state == "never":
        hue = "#9a9aa2"
        style_un = Qt.PenStyle.CustomDashLine
        dash = _DASH
    elif state == "gate_skipped":
        hue = _DETECTED_HUE
        style_un = Qt.PenStyle.CustomDashLine
        dash = _DASH
    else:  # will_fill / will_inpaint
        hue = _DETECTED_HUE
        style_un = Qt.PenStyle.SolidLine
        dash = []
    _assert_pen(item, hue, style_un, _UNSELECTED_WIDTH, dash)
    _select(scene, item)
    _assert_pen(item, hue, style_un if style_un == Qt.PenStyle.SolidLine else Qt.PenStyle.CustomDashLine, _SELECTED_WIDTH, dash)
    # Deselect back
    scene.clearSelection()
    item.setSelected(False)
    _assert_pen(item, hue, style_un, _UNSELECTED_WIDTH, dash)
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
def test_set_inpaint_state_on_selected_item_rederives_live(qtbot) -> None:
    scene, item = _scene_with_box(_make_box(DETECTED))
    item.set_inpaint_state("will_inpaint")
    _select(scene, item)
    _assert_pen(item, _DETECTED_HUE, Qt.PenStyle.SolidLine, _SELECTED_WIDTH, [])
    item.set_inpaint_state("never")
    _assert_pen(item, "#9a9aa2", Qt.PenStyle.CustomDashLine, _SELECTED_WIDTH, _DASH)
    item.set_inpaint_state("forced_fill")
    _assert_pen(item, "#e8e8ea", Qt.PenStyle.SolidLine, _SELECTED_WIDTH, [])
    tint = item.brush().color()
    assert tint.name().lower() == "#e8e8ea"


@pytest.mark.gui
def test_fresh_box_defaults_to_none_state(qtbot) -> None:
    _scene, item = _scene_with_box(_make_box(DETECTED))
    assert item._inpaint_state is None

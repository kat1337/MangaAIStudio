"""GUI tests for the Phase 8 inpaint border-state dimension (plan 08-06).

Mirrors the ``tests/test_gui_boxes.py`` convention (``pytest.importorskip`` +
``qtbot`` fixture + ``@pytest.mark.gui``). These are component-level locks on
the 08-UI-SPEC §Color border-state contract: ``BoxItem.set_inpaint_state``
extends the Phase 3 origin-hue pen with a fourth dimension —

- **Stroke style encodes the outcome**: solid = "C will inpaint this box's
  detected text", dashed = "C won't" (6/4 scene px).
- **Hue encodes who decided**: the origin hues (#5fd068 green detected /
  #f5a623 amber user) = the automatic std-dev gate decided; the reused palette
  greys ``#e8e8ea`` (forced) / ``#9a9aa2`` (never) = the user's override.
- **Selection stays width-encoded** (2px -> 3px + tint + handles): the state's
  hue/style at the selected width, tinted from the same state color at alpha
  ~0.12. Only the box rect's QPen/QBrush participate — handles, badge, overlay,
  and typeset text are untouched (D-18).

Every assertion reads the item back via ``item.pen()`` / ``item.brush()``.
State strings come from ``PageBox.inpaint_state(threshold)`` (08-01) — these
tests pass them in directly; ``BoxItem`` never computes the gate itself.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QGraphicsScene  # noqa: E402

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.gui.box_item import BoxItem, CornerHandle  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


# The border-state contract values (08-UI-SPEC §Color — reused palette members,
# zero new hex values).
_DETECTED_HUE = "#5fd068"
_USER_HUE = "#f5a623"
_FORCED_HEX = "#e8e8ea"
_NEVER_HEX = "#9a9aa2"
_UNSELECTED_WIDTH = 2
_SELECTED_WIDTH = 3
# 6/4 scene px dash (3x the 2px stroke width — readable as a dash at 100% zoom,
# scales with zoom like the border itself).
_DASH = [6.0, 4.0]
# Selected-tint alpha 31/255 ~= 0.12 (UI-SPEC §12a, the same _TINT_ALPHA the
# Phase 3 selection tint uses).
_TINT_MIN_ALPHA = 25
_TINT_MAX_ALPHA = 40

# state -> (unselected color hex per origin, style, width, dash pattern)
# 08.1 D-01 authority: 5 visible states + gate_skipped (CONTEXT D-01 inverted gate).
_ALL_STATES = ("will_fill", "will_inpaint", "gate_skipped", "forced", "forced_fill", "forced_inpaint", "never")


def _scene_with_box(pagebox: PageBox) -> tuple[QGraphicsScene, BoxItem]:
    """Build a minimal scene owning a BoxItem (selection needs scene membership)."""
    scene = QGraphicsScene()
    item = BoxItem(pagebox)
    scene.addItem(item)
    return scene, item


def _make_box(origin: str) -> PageBox:
    return PageBox(box=Box(0, 0, 60, 60), origin=origin)


def _handles(item: BoxItem) -> list[CornerHandle]:
    return [c for c in item.childItems() if isinstance(c, CornerHandle)]


def _assert_pen(
    item: BoxItem,
    color_hex: str,
    style: Qt.PenStyle,
    width: int,
    dash: list[float],
) -> None:
    """Assert the box's current QPen matches the border-state contract."""
    pen = item.pen()
    assert pen.color().name().lower() == color_hex
    assert pen.style() == style
    assert int(pen.width()) == width
    assert pen.dashPattern() == dash


def _select(scene: QGraphicsScene, item: BoxItem) -> None:
    """Select ``item`` in its scene (selection needs scene membership)."""
    scene.clearSelection()
    item.setSelected(True)
    assert item.isSelected() is True


# ===========================================================================
# Task 1 — the four unselected border states + the None default
# ===========================================================================


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_will_inpaint_unselected_renders_origin_hue_solid(qtbot, origin, hue) -> None:
    """will_inpaint = origin hue, SolidLine, width 2, no dash (the Phase 3 look)."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("will_inpaint")
    _assert_pen(item, hue, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_gate_skipped_unselected_renders_origin_hue_dashed(qtbot, origin, hue) -> None:
    """gate_skipped = origin hue, CustomDashLine [6, 4], width 2."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("gate_skipped")
    _assert_pen(
        item, hue, Qt.PenStyle.CustomDashLine, _UNSELECTED_WIDTH, _DASH
    )


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_forced_unselected_renders_near_white_solid(qtbot, origin) -> None:
    """forced = #e8e8ea, SolidLine, width 2 — the override replaces the hue (legacy compat)."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("forced")
    _assert_pen(item, _FORCED_HEX, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_will_fill_unselected_renders_origin_hue_solid(qtbot, origin, hue) -> None:
    """will_fill (08.1 D-01 inverted: std <=t → fill) = origin hue, SolidLine, width 2."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("will_fill")
    _assert_pen(item, hue, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_forced_fill_unselected_renders_near_white_solid(qtbot, origin) -> None:
    """forced_fill (08.1 D-04 fill override) = #e8e8ea, SolidLine, width 2 — CONTEXT D-01 inverted."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("forced_fill")
    _assert_pen(item, _FORCED_HEX, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_forced_inpaint_unselected_renders_near_white_solid(qtbot, origin) -> None:
    """forced_inpaint (08.1 D-04 inpaint override) = #e8e8ea, SolidLine, width 2 — CONTEXT D-01 inverted."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("forced_inpaint")
    _assert_pen(item, _FORCED_HEX, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])


@pytest.mark.gui
@pytest.mark.parametrize("origin", [DETECTED, USER])
def test_never_unselected_renders_muted_grey_dashed(qtbot, origin) -> None:
    """never = #9a9aa2, CustomDashLine [6, 4], width 2."""
    _scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("never")
    _assert_pen(item, _NEVER_HEX, Qt.PenStyle.CustomDashLine, _UNSELECTED_WIDTH, _DASH)


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_set_inpaint_state_none_renders_phase3_look(qtbot, origin, hue) -> None:
    """None (no refresh yet) = backward-compat Phase 3 look: origin hue, solid.

    A fresh ``BoxItem`` before any ``refresh_box_inpaint_states`` call must
    render exactly as today (UI-SPEC §Color — the states are additive).
    """
    _scene, item = _scene_with_box(_make_box(origin))
    assert item._inpaint_state is None  # the default attribute value
    item.set_inpaint_state(None)
    _assert_pen(item, hue, Qt.PenStyle.SolidLine, _UNSELECTED_WIDTH, [])
    assert item.brush().style() == Qt.BrushStyle.NoBrush


# ===========================================================================
# Task 1 — the selected variants (width 3 + state tint + handles visible)
# ===========================================================================


@pytest.mark.gui
@pytest.mark.parametrize(
    "state,origin,hue",
    [
        ("will_fill", DETECTED, _DETECTED_HUE),
        ("will_fill", USER, _USER_HUE),
        ("will_inpaint", DETECTED, _DETECTED_HUE),
        ("will_inpaint", USER, _USER_HUE),
        ("gate_skipped", DETECTED, _DETECTED_HUE),
        ("gate_skipped", USER, _USER_HUE),
    ],
)
def test_selected_auto_states_tint_with_origin_hue(qtbot, state, origin, hue) -> None:
    """Selected will_fill/will_inpaint/gate_skipped = state's hue at width 3 + hue tint (08.1 D-01)."""
    scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state(state)
    _select(scene, item)
    # The state's style/width at the selected width (dash survives selection).
    style = (
        Qt.PenStyle.CustomDashLine
        if state == "gate_skipped"
        else Qt.PenStyle.SolidLine
    )
    dash = _DASH if state == "gate_skipped" else []
    _assert_pen(item, hue, style, _SELECTED_WIDTH, dash)
    # Tint = the same state hue at alpha ~0.12.
    tint = item.brush().color()
    assert tint.name().lower() == hue
    assert _TINT_MIN_ALPHA <= tint.alpha() <= _TINT_MAX_ALPHA


@pytest.mark.gui
@pytest.mark.parametrize("state,hex_hex,tint_hex", [
    ("forced", _FORCED_HEX, _FORCED_HEX),
    ("forced_fill", _FORCED_HEX, _FORCED_HEX),
    ("forced_inpaint", _FORCED_HEX, _FORCED_HEX),
    ("never", _NEVER_HEX, _NEVER_HEX),
])
def test_selected_override_states_tint_with_their_grey(qtbot, state, hex_hex, tint_hex) -> None:
    """Selected forced*/never = the state's grey at width 3 + grey tint (08.1 D-04)."""
    scene, item = _scene_with_box(_make_box(DETECTED))
    item.set_inpaint_state(state)
    _select(scene, item)
    style = (
        Qt.PenStyle.CustomDashLine if state == "never" else Qt.PenStyle.SolidLine
    )
    dash = _DASH if state == "never" else []
    _assert_pen(item, hex_hex, style, _SELECTED_WIDTH, dash)
    tint = item.brush().color()
    assert tint.name().lower() == tint_hex
    assert _TINT_MIN_ALPHA <= tint.alpha() <= _TINT_MAX_ALPHA


@pytest.mark.gui
@pytest.mark.parametrize("state", _ALL_STATES)
def test_selected_override_states_keep_handles_visible(qtbot, state) -> None:
    """Handles stay visible on the selected box for every state (UI-SPEC §12b).

    The border-state dimension must never touch the handle affordance (D-18).
    """
    scene, item = _scene_with_box(_make_box(USER))
    item.set_inpaint_state(state)
    _select(scene, item)
    handles = _handles(item)
    assert len(handles) == 4
    assert all(h.isVisible() for h in handles)


# ===========================================================================
# Task 1 — the itemChange selection re-apply hook
# ===========================================================================


@pytest.mark.gui
@pytest.mark.parametrize("origin,hue", [(DETECTED, _DETECTED_HUE), (USER, _USER_HUE)])
def test_selection_change_rederives_pen_with_current_state(qtbot, origin, hue) -> None:
    """itemChange re-applies the pen with the CURRENT state on select/deselect.

    A state set while unselected must carry into the selected look (dash kept +
    width 3 + hue tint), and deselection must return to the state's unselected
    look — not the Phase 3 default.
    """
    scene, item = _scene_with_box(_make_box(origin))
    item.set_inpaint_state("gate_skipped")
    # Select -> the CURRENT state renders at the selected width (still dashed).
    _select(scene, item)
    _assert_pen(
        item, hue, Qt.PenStyle.CustomDashLine, _SELECTED_WIDTH, _DASH
    )
    tint = item.brush().color()
    assert tint.name().lower() == hue
    assert _TINT_MIN_ALPHA <= tint.alpha() <= _TINT_MAX_ALPHA
    # Deselect -> back to the state's unselected look (dashed, width 2, NoBrush).
    scene.clearSelection()
    item.setSelected(False)
    _assert_pen(item, hue, Qt.PenStyle.CustomDashLine, _UNSELECTED_WIDTH, _DASH)
    assert item.brush().style() == Qt.BrushStyle.NoBrush


@pytest.mark.gui
def test_set_inpaint_state_on_selected_item_rederives_live(qtbot) -> None:
    """Changing the state while selected re-derives the pen/brush immediately.

    ``refresh_box_inpaint_states`` (08-07) may fire while a box is selected
    (e.g. an override commit); the tint and width must follow the new state.
    """
    scene, item = _scene_with_box(_make_box(DETECTED))
    item.set_inpaint_state("will_inpaint")
    _select(scene, item)
    _assert_pen(
        item, _DETECTED_HUE, Qt.PenStyle.SolidLine, _SELECTED_WIDTH, []
    )
    # Flip to never while selected -> grey dashed tinted brush, width stays 3.
    item.set_inpaint_state("never")
    _assert_pen(
        item, _NEVER_HEX, Qt.PenStyle.CustomDashLine, _SELECTED_WIDTH, _DASH
    )
    tint = item.brush().color()
    assert tint.name().lower() == _NEVER_HEX
    assert _TINT_MIN_ALPHA <= tint.alpha() <= _TINT_MAX_ALPHA


@pytest.mark.gui
def test_fresh_box_defaults_to_none_state(qtbot) -> None:
    """A fresh BoxItem has ``_inpaint_state is None`` until a refresh call.

    Backward-compat lock: constructing a BoxItem without ever calling
    ``set_inpaint_state`` renders the Phase 3 look (covered by
    ``test_set_inpaint_state_none_renders_phase3_look`` — this asserts the
    attribute default so the ``None`` behavior is trivially observable).
    """
    _scene, item = _scene_with_box(_make_box(DETECTED))
    assert item._inpaint_state is None
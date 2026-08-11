"""``TextStyle`` model tests (plan 07-01 Task 1) — UI-SPEC A1 defaults,
``to_dict``/``from_dict`` round-trip, V5 input clamps, and the Pitfall 8
copy-detachment discipline applied to the style field.

The ``TextStyle`` dataclass is the flat per-box style (D-06) composed on
``PageBox`` (D-14 anti-pattern — never subclass the vendored types). These
tests pin the serialization spelling (the D-07 single writer contract) and
the undo-snapshot detachment (RESEARCH Pitfall 1/8: a style edit + Ctrl+Z
must restore the PRE-edit style, never the live object).

Pure Python — no Qt — so no ``qapp`` fixture is needed.
"""

from __future__ import annotations

import pytest

from manga_ai_studio.core.box_model import DETECTED, PageBox
from manga_ai_studio.core.history_manager import HistoryManager
from manga_ai_studio.core.text_style import TextStyle
from panelcleaner.structures import Box


def _pagebox_with_style(style: TextStyle) -> PageBox:
    """A DETECTED PageBox carrying the given style."""
    return PageBox(box=Box(10, 20, 110, 220), origin=DETECTED, style=style)


# ---------------------------------------------------------------------------
# Test 1 — defaults (UI-SPEC A1 / RESEARCH Code Example 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_defaults_match_ui_spec_a1() -> None:
    """TextStyle() defaults = the Phase 4 overlay look made opaque (UI-SPEC A1)."""
    s = TextStyle()
    assert s.font_family == "Liberation Sans"
    assert s.bold is False
    assert s.italic is False
    assert s.font_size_px is None  # None = Auto (D-15)
    assert s.auto_fit is True
    assert s.color == "#e8e8ea"
    assert s.align_h == "center"
    assert s.align_v == "middle"
    assert s.vertical is False
    assert s.outline == {"enabled": True, "color": "#0b0b0e", "width_px": 2.0}
    assert s.glow == {"enabled": False, "color": "#e8e8ea", "radius_px": 4.0, "opacity": 0.8}
    assert s.shadow == {"enabled": False, "color": "#000000", "radius_px": 4.0, "dx": 2.0, "dy": 2.0, "opacity": 0.6}


# ---------------------------------------------------------------------------
# Test 2 — to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_dict_from_dict_round_trip_preserves_every_field() -> None:
    """from_dict(to_dict(s)) equals s field-for-field (the D-07 writer spelling)."""
    s = TextStyle(
        font_family="Yu Gothic UI",
        bold=True,
        italic=True,
        font_size_px=18.0,
        auto_fit=False,
        color="#ffcc00",
        align_h="left",
        align_v="bottom",
        vertical=True,
        outline={"enabled": True, "color": "#112233", "width_px": 3.5},
        glow={"enabled": True, "color": "#aabbcc", "radius_px": 6.0, "opacity": 0.7},
        shadow={"enabled": True, "color": "#010203", "radius_px": 5.0, "dx": 1.5, "dy": 2.5, "opacity": 0.4},
    )
    restored = TextStyle.from_dict(s.to_dict())
    assert restored == s


@pytest.mark.unit
def test_to_dict_is_a_plain_dict_with_all_fields() -> None:
    """to_dict returns the hand-picked projection (a plain dict, all fields)."""
    s = TextStyle()
    d = s.to_dict()
    assert isinstance(d, dict)
    for key in (
        "font_family", "bold", "italic", "font_size_px", "auto_fit", "color",
        "align_h", "align_v", "vertical", "outline", "glow", "shadow",
    ):
        assert key in d
    assert isinstance(d["outline"], dict)
    assert isinstance(d["glow"], dict)
    assert isinstance(d["shadow"], dict)


@pytest.mark.unit
def test_from_dict_none_and_empty_return_defaults() -> None:
    """from_dict(None) and from_dict({}) return a default TextStyle (Pitfall 8:
    legacy files / boxes without a stored style load with defaults)."""
    assert TextStyle.from_dict(None) == TextStyle()
    assert TextStyle.from_dict({}) == TextStyle()


# ---------------------------------------------------------------------------
# Test 3 — V5 input clamps (size 1..1024, widths/radii 0..256, opacity 0..1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_v5_clamps_font_size_px() -> None:
    """font_size_px clamps into 1..1024 when a manual size is set; auto-fit
    forces None (0 = the Auto sentinel)."""
    # auto_fit True: size is ignored -> None (Auto governs, D-15).
    assert TextStyle.from_dict({"auto_fit": True, "font_size_px": 2000.0}).font_size_px is None
    assert TextStyle.from_dict({"auto_fit": True, "font_size_px": -5.0}).font_size_px is None
    # manual size: clamped into 1..1024.
    assert TextStyle.from_dict({"auto_fit": False, "font_size_px": 2000.0}).font_size_px == 1024.0
    assert TextStyle.from_dict({"auto_fit": False, "font_size_px": -5.0}).font_size_px == 1.0
    assert TextStyle.from_dict({"auto_fit": False, "font_size_px": 0.0}).font_size_px == 1.0
    assert TextStyle.from_dict({"auto_fit": False, "font_size_px": 42.0}).font_size_px == 42.0


@pytest.mark.unit
def test_v5_clamps_widths_radii_and_opacity() -> None:
    """widths/radii clamp into 0..256; opacity clamps into 0..1."""
    s = TextStyle.from_dict(
        {
            "outline": {"enabled": True, "color": "#0b0b0e", "width_px": 300.0},
            "glow": {"enabled": True, "color": "#e8e8ea", "radius_px": -4.0, "opacity": 1.5},
            "shadow": {"enabled": True, "color": "#000000", "radius_px": 999.0, "dx": 2.0, "dy": 2.0, "opacity": -0.5},
        }
    )
    assert s.outline["width_px"] == 256.0  # 300 -> clamped
    assert s.glow["radius_px"] == 0.0  # -4 -> clamped to the 0 floor
    assert s.glow["opacity"] == 1.0  # 1.5 -> clamped
    assert s.shadow["radius_px"] == 256.0  # 999 -> clamped
    assert s.shadow["opacity"] == 0.0  # -0.5 -> clamped


@pytest.mark.unit
def test_non_numeric_inputs_fall_back_to_defaults_without_raising() -> None:
    """Non-numeric values fall back to defaults instead of raising (V5)."""
    s = TextStyle.from_dict(
        {
            "font_size_px": "big",
            "color": 123,
            "bold": "yes",
            "auto_fit": "maybe",
            "outline": {"width_px": "wide", "enabled": "true"},
            "glow": {"radius_px": None, "opacity": None},
        }
    )
    assert s.font_size_px is None
    assert s.color == "#e8e8ea"
    assert s.bold is False
    assert s.auto_fit is True
    assert s.outline["width_px"] == 2.0
    assert s.outline["enabled"] is True
    assert s.glow["radius_px"] == 4.0
    assert s.glow["opacity"] == 0.8


@pytest.mark.unit
def test_unknown_keys_ignored() -> None:
    """Unknown keys in the dict are ignored (backward compat with consumers)."""
    s = TextStyle.from_dict(
        {"font_family": "Arial", "frobnicate": 42, "future_key": {"x": 1}}
    )
    assert s.font_family == "Arial"
    assert s == TextStyle(font_family="Arial")


@pytest.mark.unit
def test_wrong_effect_key_shape_falls_back_to_defaults() -> None:
    """A non-dict effect value (or a partial dict) falls back to the defaults."""
    s = TextStyle.from_dict(
        {
            "outline": "garbage",
            "glow": [1, 2, 3],
            "shadow": None,
        }
    )
    assert s.outline == TextStyle().outline
    assert s.glow == TextStyle().glow
    assert s.shadow == TextStyle().shadow
    # Partial dicts keep the untouched fields at their defaults.
    s2 = TextStyle.from_dict({"outline": {"width_px": 5.0}})
    assert s2.outline["width_px"] == 5.0
    assert s2.outline["enabled"] is True
    assert s2.outline["color"] == "#0b0b0e"


@pytest.mark.unit
def test_align_values_validated() -> None:
    """align_h/align_v accept the documented values; anything else -> defaults."""
    assert TextStyle.from_dict({"align_h": "left"}).align_h == "left"
    assert TextStyle.from_dict({"align_h": "right"}).align_h == "right"
    assert TextStyle.from_dict({"align_h": "diagonal"}).align_h == "center"
    assert TextStyle.from_dict({"align_v": "bottom"}).align_v == "bottom"
    assert TextStyle.from_dict({"align_v": 7}).align_v == "middle"


# ---------------------------------------------------------------------------
# Test 4 — PageBox.copy() detaches the style (Pitfall 8/1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_style_copy_detaches_undo_restores_pre_edit_style() -> None:
    """A style edit pushed through a real HistoryManager undo-restores the
    PRE-edit style, and the restored object is not the live one (Pitfall 1/8)."""
    from dataclasses import replace

    history = HistoryManager(limit=20)
    live = _pagebox_with_style(TextStyle(color="#e8e8ea"))
    history.push_boxes_state([live])

    # Simulate a style commit: assign a FRESH instance (never mutate in place).
    live.style = replace(live.style, color="#ff0000")

    restored = history.pop_boxes_undo(current_boxes=[live])
    assert restored is not None
    assert len(restored) == 1
    restored_pb = restored[0]
    # Undo restores the snapshot-time (PRE-edit) style.
    assert restored_pb.style is not None
    assert restored_pb.style.color == "#e8e8ea"
    # The restored style object is detached from the live one.
    assert restored_pb.style is not live.style


@pytest.mark.unit
def test_style_field_defaults_to_none() -> None:
    """A fresh PageBox has style=None (renderers fall back to TextStyle())."""
    pb = PageBox(box=Box(1, 2, 3, 4), origin=DETECTED)
    assert pb.style is None

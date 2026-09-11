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
    """TextStyle() defaults = black fill, outline disabled (quick task
    260822-347); glow/shadow defaults unchanged."""
    s = TextStyle()
    assert s.font_family == "Liberation Sans"
    assert s.bold is False
    assert s.italic is False
    assert s.font_size_px is None  # None = Auto (D-15)
    assert s.auto_fit is True
    assert s.color == "#000000"
    assert s.align_h == "center"
    assert s.align_v == "middle"
    assert s.vertical is False
    assert s.outline == {"enabled": False, "color": "#ffffff", "width_px": 2.0}
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
    assert s.color == "#000000"
    assert s.bold is False
    assert s.auto_fit is True
    assert s.outline["width_px"] == 2.0
    assert s.outline["enabled"] is False
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
    assert s2.outline["enabled"] is False
    assert s2.outline["color"] == "#ffffff"


@pytest.mark.unit
def test_align_values_validated() -> None:
    """align_h/align_v accept the documented values; anything else -> defaults."""
    assert TextStyle.from_dict({"align_h": "left"}).align_h == "left"
    assert TextStyle.from_dict({"align_h": "right"}).align_h == "right"
    assert TextStyle.from_dict({"align_h": "diagonal"}).align_h == "center"
    assert TextStyle.from_dict({"align_v": "bottom"}).align_v == "bottom"
    assert TextStyle.from_dict({"align_v": 7}).align_v == "middle"


# ---------------------------------------------------------------------------
# Task 3 Test 5 — V5 edge absorption (never raises, always a valid TextStyle)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_v5_edges_absorb_garbage_without_raising() -> None:
    """from_dict absorbs a style dict with a non-dict outline, a list-valued
    color, a string font_size_px, a non-dict glow, and offset garbage —
    always yielding a valid TextStyle with clamps applied, never raising."""
    s = TextStyle.from_dict(
        {
            "outline": "garbage",
            "color": ["#ff0000"],
            "font_size_px": "big",
            "glow": 42,
            "shadow": {"dx": "left", "dy": None, "opacity": 99},
        }
    )
    assert isinstance(s, TextStyle)
    assert s.color == "#000000"  # list color -> default
    assert s.font_size_px is None  # "big" -> default (None = Auto)
    assert s.outline == TextStyle().outline  # non-dict -> whole default
    assert s.glow == TextStyle().glow  # non-dict -> whole default
    assert s.shadow["dx"] == 2.0  # non-numeric offset -> default
    assert s.shadow["dy"] == 2.0
    assert s.shadow["opacity"] == 1.0  # 99 -> clamped


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


# ---------------------------------------------------------------------------
# G-07-3 — the default_style() factory (the Qt-free end of the QSettings
# 'defaultFontFamily' chain; plan 07-11). The factory takes the family as a
# parameter — QSettings stays GUI-side, core/ stays Qt-free.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_style_none_uses_default_family() -> None:
    """default_style(None) == the plain TextStyle() defaults exactly.

    The no-key contract: when no family was ever saved, the creation sites
    pass None and the renderer's TextStyle() defaults (Liberation Sans)
    apply — so the factory with None must equal the defaults field-for-field.
    """
    from manga_ai_studio.core.text_style import (
        DEFAULT_FONT_FAMILY,
        default_style,
    )

    s = default_style(None)
    assert s.font_family == DEFAULT_FONT_FAMILY
    assert s.to_dict() == TextStyle().to_dict()


@pytest.mark.unit
def test_default_style_explicit_family_overrides_only_family() -> None:
    """default_style("Yu Gothic UI") keeps every field at the TextStyle()
    defaults except font_family — the saved family NEVER drags the other
    fields off their defaults (a new box looks like today's default box,
    only with the chosen family)."""
    from manga_ai_studio.core.text_style import default_style

    s = default_style("Yu Gothic UI")
    assert s.font_family == "Yu Gothic UI"
    assert s.to_dict() == TextStyle(font_family="Yu Gothic UI").to_dict()


# ---------------------------------------------------------------------------
# quick-260824-viq Task 1 — rotation_deg / char_spacing_px / line_spacing_px
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_new_fields_default_to_zero_and_to_dict_carries_them() -> None:
    """The three new fields default to 0.0; to_dict carries them as plain floats."""
    from manga_ai_studio.core.text_style import (
        CHAR_SPACING_MAX,
        LINE_SPACING_MAX,
        ROTATION_MAX,
    )

    s = TextStyle()
    assert s.rotation_deg == 0.0
    assert s.char_spacing_px == 0.0
    assert s.line_spacing_px == 0.0
    # The V5 bound constants exist and match the plan contract.
    assert ROTATION_MAX == 180.0
    assert CHAR_SPACING_MAX == 64.0
    assert LINE_SPACING_MAX == 256.0

    styled = TextStyle(rotation_deg=37.5, char_spacing_px=8.0, line_spacing_px=20.0)
    d = styled.to_dict()
    assert d["rotation_deg"] == 37.5
    assert d["char_spacing_px"] == 8.0
    assert d["line_spacing_px"] == 20.0


@pytest.mark.unit
def test_new_fields_round_trip_through_from_dict() -> None:
    """from_dict(to_dict(s)) preserves all three new fields (D-07 spelling)."""
    s = TextStyle(rotation_deg=-37.5, char_spacing_px=12.5, line_spacing_px=33.0)
    restored = TextStyle.from_dict(s.to_dict())
    assert restored.rotation_deg == -37.5
    assert restored.char_spacing_px == 12.5
    assert restored.line_spacing_px == 33.0
    assert restored == s


@pytest.mark.unit
def test_legacy_dicts_yield_zero_defaults_for_new_fields() -> None:
    """A legacy dict without the new keys (and None input) yields 0.0 defaults
    (Pitfall 8 backward compat — old files carry no rotation/spacing)."""
    for src in (None, {}, {"font_family": "Arial"}):
        s = TextStyle.from_dict(src)
        assert s.rotation_deg == 0.0
        assert s.char_spacing_px == 0.0
        assert s.line_spacing_px == 0.0


@pytest.mark.unit
def test_v5_clamps_rotation_deg() -> None:
    """rotation_deg clamps into [-180, 180]; non-numeric falls back to 0.0,
    never raises (V5 — T-VIQ-01)."""
    assert TextStyle.from_dict({"rotation_deg": 999}).rotation_deg == 180.0
    assert TextStyle.from_dict({"rotation_deg": -999}).rotation_deg == -180.0
    assert TextStyle.from_dict({"rotation_deg": 45}).rotation_deg == 45.0
    assert TextStyle.from_dict({"rotation_deg": "x"}).rotation_deg == 0.0
    assert TextStyle.from_dict({"rotation_deg": True}).rotation_deg == 0.0  # bool rejected
    assert TextStyle.from_dict({"rotation_deg": None}).rotation_deg == 0.0


@pytest.mark.unit
def test_v5_clamp_char_and_line_spacing_px() -> None:
    """char_spacing_px clamps into -64..64; line_spacing_px into -256..256
    (negatives TIGHTEN — spacing below the font's natural gap is the point
    of the controls); non-numeric falls back to the default, never raises
    (V5 — T-VIQ-01)."""
    assert TextStyle.from_dict({"char_spacing_px": 100}).char_spacing_px == 64.0
    assert TextStyle.from_dict({"char_spacing_px": -5}).char_spacing_px == -5.0
    assert TextStyle.from_dict({"char_spacing_px": -999}).char_spacing_px == -64.0
    assert TextStyle.from_dict({"char_spacing_px": 8.5}).char_spacing_px == 8.5
    assert TextStyle.from_dict({"char_spacing_px": "wide"}).char_spacing_px == 0.0
    assert TextStyle.from_dict({"char_spacing_px": False}).char_spacing_px == 0.0

    assert TextStyle.from_dict({"line_spacing_px": 999}).line_spacing_px == 256.0
    assert TextStyle.from_dict({"line_spacing_px": -1}).line_spacing_px == -1.0
    assert TextStyle.from_dict({"line_spacing_px": -999}).line_spacing_px == -256.0
    assert TextStyle.from_dict({"line_spacing_px": 20.25}).line_spacing_px == 20.25
    assert TextStyle.from_dict({"line_spacing_px": "tall"}).line_spacing_px == 0.0
    assert TextStyle.from_dict({"line_spacing_px": None}).line_spacing_px == 0.0


# ---------------------------------------------------------------------------
# quick-260826-vhh — EFFECT_GEOM_MAX promoted to a public shared constant
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effect_geom_max_public_constant_is_the_single_clamp_source() -> None:
    """EFFECT_GEOM_MAX is public and IS the coercion bound (the Inspector
    spins read the same symbol, so UI == model by construction). The private
    duplicate spelling must be gone — exactly one shared symbol exists."""
    import manga_ai_studio.core.text_style as ts_mod

    assert ts_mod.EFFECT_GEOM_MAX == 256.0
    assert not hasattr(ts_mod, "_EFFECT_GEOM_MAX"), (
        "the private _EFFECT_GEOM_MAX spelling must be removed"
    )
    # Every effect geometry field clamps to it: 999 -> 256.
    s = TextStyle.from_dict({"outline": {"width_px": 999}, "glow": {"radius_px": 999}})
    assert s.outline["width_px"] == ts_mod.EFFECT_GEOM_MAX
    assert s.glow["radius_px"] == ts_mod.EFFECT_GEOM_MAX
    assert s.shadow["radius_px"] == 4.0  # untouched field keeps its default
    # Non-numeric falls back to the per-field default, unchanged (V5).
    s2 = TextStyle.from_dict({"glow": {"radius_px": "huge"}})
    assert s2.glow["radius_px"] == 4.0


@pytest.mark.unit
def test_effect_geom_boundary_value_round_trips_unclamped() -> None:
    """A 256.0 radius (the boundary itself) survives to_dict/from_dict
    unchanged — the clamp is inclusive at EFFECT_GEOM_MAX."""
    glow = {
        "enabled": True,
        "color": "#ffff00",
        "radius_px": 256.0,
        "opacity": 0.8,
    }
    s = TextStyle(glow=glow)
    r = TextStyle.from_dict(s.to_dict())
    assert r.glow["radius_px"] == 256.0
    assert r == s


# ---------------------------------------------------------------------------
# quick-260909-nj9 — the color field carries ALPHA (#AARRGGBB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_alpha_color_round_trips_verbatim() -> None:
    """quick-260909-nj9: an alpha-carrying ``#AARRGGBB`` color survives the
    D-07 serialization spelling VERBATIM — no clamping, no spelling
    normalization, no alpha stripping (``_coerce_str`` passes any string
    through untouched; ``to_dict`` writes the field back as-is)."""
    s = TextStyle(color="#80ff0000")
    assert s.to_dict()["color"] == "#80ff0000"
    r = TextStyle.from_dict({"color": "#80ff0000"})
    assert r.color == "#80ff0000"
    # The full round-trip preserves the 9-char spelling exactly.
    assert TextStyle.from_dict(s.to_dict()).color == "#80ff0000"


@pytest.mark.unit
def test_legacy_opaque_color_spelling_preserved_as_is() -> None:
    """A legacy 7-char ``#RRGGBB`` color loads as-is — the model NEVER
    rewrites the spelling to 9-char (opacity comes from QColor's default
    alpha 255 at parse time, not from a load-time rewrite)."""
    assert TextStyle.from_dict({"color": "#ff0000"}).color == "#ff0000"


@pytest.mark.unit
def test_default_color_spelling_unchanged() -> None:
    """The default color spelling is untouched by the alpha work — existing
    projects see zero churn (no 7->9-char rewrite of the default)."""
    assert TextStyle().to_dict()["color"] == "#000000"


# ---------------------------------------------------------------------------
# quick-260910-vej — the fill framework (solid | gradient | pattern)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fill_fields_default_to_legacy_solid_look() -> None:
    """Every fill field's default is legacy-identical: Solid with the plain
    color fill, no Color B/angle/scale/tile state to disturb old projects."""
    from manga_ai_studio.core.text_style import (
        FILL_TILE_MAX_BYTES,
        FILL_TYPES,
    )

    s = TextStyle()
    assert s.fill_type == "solid"
    assert s.fill_color_b == "#ffffff"
    assert s.fill_angle_deg == 90.0
    assert s.pattern_scale == 1.0
    assert s.pattern_tile_b64 is None
    # The public shared constants (the UI imports them — UI == model).
    assert FILL_TYPES == ("solid", "gradient", "pattern")
    assert FILL_TILE_MAX_BYTES == 4 * 1024 * 1024


@pytest.mark.unit
def test_fill_fields_round_trip_through_from_dict() -> None:
    """from_dict(to_dict(s)) preserves all five fill fields for a fully
    populated fill style (the D-07 single spelling)."""
    s = TextStyle(
        color="#80ff0000",
        fill_type="gradient",
        fill_color_b="#00ffff00",
        fill_angle_deg=37.0,
    )
    restored = TextStyle.from_dict(s.to_dict())
    assert restored == s

    tile = TextStyle(
        fill_type="pattern",
        pattern_scale=2.5,
        pattern_tile_b64="aGVsbG8=",
    )
    restored_t = TextStyle.from_dict(tile.to_dict())
    assert restored_t == tile


@pytest.mark.unit
def test_to_dict_carries_all_five_fill_keys() -> None:
    """to_dict's projection includes every fill key — the .mas shape."""
    d = TextStyle().to_dict()
    for key in (
        "fill_type",
        "fill_color_b",
        "fill_angle_deg",
        "pattern_scale",
        "pattern_tile_b64",
    ):
        assert key in d


@pytest.mark.unit
def test_v5_fill_type_allowed_values_fallback() -> None:
    """fill_type coerces through the allowed-values set (the align_h
    pattern): unknown strings and non-str values fall back to "solid"."""
    assert TextStyle.from_dict({"fill_type": "gradient"}).fill_type == "gradient"
    assert TextStyle.from_dict({"fill_type": "pattern"}).fill_type == "pattern"
    assert TextStyle.from_dict({"fill_type": "solid"}).fill_type == "solid"
    assert TextStyle.from_dict({"fill_type": "radial"}).fill_type == "solid"
    assert TextStyle.from_dict({"fill_type": 3}).fill_type == "solid"
    assert TextStyle.from_dict({"fill_type": None}).fill_type == "solid"


@pytest.mark.unit
def test_v5_clamps_fill_angle_and_pattern_scale() -> None:
    """fill_angle_deg clamps into 0..360; pattern_scale into 0.1..10.0;
    non-numeric falls back to the default, never raises (V5)."""
    assert TextStyle.from_dict({"fill_angle_deg": -5}).fill_angle_deg == 0.0
    assert TextStyle.from_dict({"fill_angle_deg": 720}).fill_angle_deg == 360.0
    assert TextStyle.from_dict({"fill_angle_deg": 37.5}).fill_angle_deg == 37.5
    assert TextStyle.from_dict({"fill_angle_deg": "x"}).fill_angle_deg == 90.0
    assert TextStyle.from_dict({"fill_angle_deg": True}).fill_angle_deg == 90.0

    assert TextStyle.from_dict({"pattern_scale": 0.01}).pattern_scale == 0.1
    assert TextStyle.from_dict({"pattern_scale": 99}).pattern_scale == 10.0
    assert TextStyle.from_dict({"pattern_scale": 2.5}).pattern_scale == 2.5
    assert TextStyle.from_dict({"pattern_scale": "big"}).pattern_scale == 1.0


@pytest.mark.unit
def test_v5_pattern_tile_b64_non_str_loads_as_none() -> None:
    """A non-str pattern_tile_b64 loads as None (no clamp at load — load
    robustness; the 4 MB cap is a pick-time UI guard only)."""
    assert TextStyle.from_dict({"pattern_tile_b64": 123}).pattern_tile_b64 is None
    assert TextStyle.from_dict({"pattern_tile_b64": None}).pattern_tile_b64 is None
    assert (
        TextStyle.from_dict({"pattern_tile_b64": "aGVsbG8="}).pattern_tile_b64
        == "aGVsbG8="
    )


@pytest.mark.unit
def test_legacy_dicts_yield_solid_defaults_for_fill_fields() -> None:
    """A legacy dict without fill keys (and None input) yields the Solid
    defaults exactly (Pitfall 8 backward compat)."""
    for src in (None, {}, {"font_family": "Arial", "color": "#ff0000"}):
        s = TextStyle.from_dict(src)
        assert s.fill_type == "solid"
        assert s.fill_color_b == "#ffffff"
        assert s.fill_angle_deg == 90.0
        assert s.pattern_scale == 1.0
        assert s.pattern_tile_b64 is None

"""``TextStyle`` — the flat per-box typesetting style (plan 07-01 Task 1, D-06).

The style model behind Phase 7's opaque typeset rendering (D-01): every box
stores its own COMPLETE style — no page-default/inheritance cascade (D-06).
The dataclass COMPOSES on ``PageBox`` (D-14 anti-pattern — vendored
``Box``/``TextBlock`` stay untouched); ``PageBox.copy()`` detaches it so BOXES
undo snapshots never alias the live style (RESEARCH Pitfall 8/1).

Defaults are the Phase 4 overlay look made opaque, with a black-text
default (quick task 260822-347): Liberation Sans, Auto-fit on,
``#000000`` opaque fill, outline DISABLED by default (black text over
manga artwork is the dominant case, so the enable-time stroke defaults
to WHITE — ``#ffffff`` — at 2px width), glow and shadow OFF,
center/middle alignment, horizontal.
``font_size_px=None`` means Auto (D-15) — the 04-09 fit-in-box machinery
governs.

Since quick-260909-nj9 the glyph fill ``color`` carries ALPHA: both the
legacy ``#RRGGBB`` (opaque) and Qt's ``#AARRGGBB`` HexArgb spellings are
accepted and stored verbatim (alpha ``ff`` = opaque, the legacy default —
QColor applies it automatically at parse time, so old projects load and
render byte-compatibly with zero spelling rewrite).

Serialization (``to_dict`` / ``from_dict``) is the SINGLE spelling shared by
the persistence writers (D-07 — one dict builder under test). ``from_dict``
is the V5 input boundary: every numeric is type-checked and clamped
(font size 1..1024, effect widths/radii 0..256, opacity 0..1,
spacing H -64..64 / V -256..256 — negatives tighten), non-numeric
values fall back to defaults WITHOUT raising, unknown keys are ignored, and
``None``/missing input returns the defaults (Pitfall 8 backward compat — old
files carry no style block).

Pure Python — no Qt. Headless-testable (``tests/test_core/test_text_style.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Defaults (UI-SPEC A1 — the Phase 4 overlay look made opaque; D-01)
# ---------------------------------------------------------------------------
DEFAULT_FONT_FAMILY = "Liberation Sans"
DEFAULT_COLOR = "#000000"
DEFAULT_OUTLINE = {"enabled": False, "color": "#ffffff", "width_px": 2.0}
DEFAULT_GLOW = {"enabled": False, "color": "#e8e8ea", "radius_px": 4.0, "opacity": 0.8}
DEFAULT_SHADOW = {
    "enabled": False,
    "color": "#000000",
    "radius_px": 4.0,
    "dx": 2.0,
    "dy": 2.0,
    "opacity": 0.6,
}

# V5 bounds (ASVS V5 — the from_dict coercion boundary).
_FONT_SIZE_MIN = 1.0
_FONT_SIZE_MAX = 1024.0
_OPACITY_MAX = 1.0

# quick-260824-viq bounds: free-angle text rotation is clamped to a full
# half-turn in either direction; character spacing and line/column spacing
# allow NEGATIVE values (tightening — the point of the controls is letting
# letters sit closer than the font's natural advance), down to mirrored
# generous floors with the same non-garbage ceilings as before.
# quick-260826-vhh promotes the effect geometry bound into the
# same PUBLIC block (one shared symbol, no private duplicate): the Inspector
# spins read ``EFFECT_GEOM_MAX`` directly so the UI range == the model clamp
# by construction. Generous sanity ceiling like its neighbors — a big SFX
# stroke/glow/shadow is intent; larger values are garbage, not intent.
ROTATION_MAX = 180.0
CHAR_SPACING_MAX = 64.0
LINE_SPACING_MAX = 256.0
CHAR_SPACING_MIN = -64.0
LINE_SPACING_MIN = -256.0
EFFECT_GEOM_MAX = 256.0  # outline width / glow+shadow radius

_ALIGN_H_VALUES = ("left", "center", "right")
_ALIGN_V_VALUES = ("top", "middle", "bottom")


def default_style(font_family: str | None = None) -> "TextStyle":
    """The Qt-free factory for the app-level default font (G-07-3, plan 07-11).

    ``None`` (or an empty string) -> the plain ``TextStyle()`` defaults
    (Liberation Sans); a family -> the defaults with ONLY ``font_family``
    overridden. QSettings stays GUI-side — the MainWindow reads
    'defaultFontFamily' and passes the family string in here; core/ never
    imports Qt. The new-box creation sites (user-drawn + detected) call this
    factory when a family was saved, and pass ``None`` (style stays None,
    the renderer's ``TextStyle()`` defaults apply) when none was.
    """
    return TextStyle(font_family=font_family or DEFAULT_FONT_FAMILY)


def _clamp_float(value, lo: float, hi: float, default: float) -> float:
    """Coerce ``value`` to a float clamped into ``[lo, hi]``; non-numeric -> ``default``.

    Bool is rejected (it is an int subclass) so ``True``/``False`` never
    masquerade as numerics (V5 strictness).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(lo, min(hi, float(value)))


def _coerce_bool(value, default: bool) -> bool:
    """``value`` -> bool; anything that is not a bool falls back to ``default``."""
    if isinstance(value, bool):
        return value
    return default


def _coerce_str(value, default: str) -> str:
    """``value`` -> str; non-str falls back to ``default`` (V5 type check)."""
    if isinstance(value, str):
        return value
    return default


def _coerce_effect(raw, default: dict) -> dict:
    """Coerce one effect dict (outline/glow/shadow) with per-field V5 clamps.

    A non-dict value (or ``None``) yields the whole default (wrong-key-shape
    rule); a partial dict keeps the untouched fields at their defaults.
    Numerics clamp per field role: ``width_px``/``radius_px`` into 0..256,
    ``opacity`` into 0..1, ``dx``/``dy`` unclamped floats (offsets are
    unbounded by design but must be numeric).
    """
    if not isinstance(raw, dict):
        return dict(default)
    out = dict(default)
    for key, value in raw.items():
        if key == "enabled":
            out[key] = _coerce_bool(value, out[key])
        elif key == "color":
            out[key] = _coerce_str(value, out[key])
        elif key in ("width_px", "radius_px"):
            out[key] = _clamp_float(value, 0.0, EFFECT_GEOM_MAX, out[key])
        elif key == "opacity":
            out[key] = _clamp_float(value, 0.0, _OPACITY_MAX, out[key])
        elif key in ("dx", "dy"):
            out[key] = _clamp_float(value, -float("inf"), float("inf"), out[key])
        # unknown keys inside an effect are ignored (V5)
    return out


@dataclass
class TextStyle:
    """Flat per-box typesetting style (D-06). Scene-px font size (D-15/Pattern 1).

    Fields:
        font_family: Family name; rendered through Qt font fallback for
            glyphs the family lacks (CJK with Liberation Sans — UI-SPEC
            §Accessibility: fallback must NOT be disabled).
        bold / italic: Font style flags.
        font_size_px: Manual size in scene px, or ``None`` = Auto (D-15).
            ``auto_fit`` governs which path the renderer takes.
        auto_fit: ``True`` (default) runs the 04-09 bounded fit-in-box loop;
            ``False`` renders at exactly ``font_size_px`` (may overflow).
        color: The glyph fill (D-01 — user-chosen fills MAY be saturated;
            the documented Phase 7 exception). ``#RRGGBB`` or ``#AARRGGBB``
            (Qt HexArgb spelling; alpha ``ff`` = opaque, the legacy default)
            — quick-260909-nj9.
        align_h: "left" | "center" | "right".
        align_v: "top" | "middle" | "bottom".
        vertical: Render tategaki (D-11/D-13). The 07-01 horizontal renderer
            consumes it (plan 07-03 adds the vertical layout path).
        outline / glow / shadow: The D-14 effect dicts (see module defaults
            for the exact keys). NEVER mutated in place — every style change
            assigns a fresh instance (``dataclasses.replace``).
        rotation_deg: Free-angle text rotation in degrees CLOCKWISE
            (quick-260824-viq; Qt's ``QPainter.rotate`` convention). 0.0 =
            the axis-aligned legacy look. Serialized and V5-clamped into
            [-180, 180] on load.
        char_spacing_px: Extra horizontal gap between characters (px).
            Applied through ``QFont.setLetterSpacing`` so measurement and
            render share one font construction. Clamped 0..64.
        line_spacing_px: Extra vertical gap between lines (horizontal mode)
            / between stacked characters in a column (vertical tategaki
            mode), in px. Clamped 0..256.
    """

    font_family: str = DEFAULT_FONT_FAMILY
    bold: bool = False
    italic: bool = False
    font_size_px: float | None = None  # None = Auto (D-15)
    auto_fit: bool = True
    # Glyph fill: "#RRGGBB" or "#AARRGGBB" (Qt HexArgb; alpha ff = opaque,
    # the legacy default — quick-260909-nj9). Stored verbatim — no clamp,
    # no spelling rewrite; invalid hex falls back at RENDER time
    # (_valid_color), never at load (V5 tolerance).
    color: str = DEFAULT_COLOR
    align_h: str = "center"
    align_v: str = "middle"
    vertical: bool = False
    rotation_deg: float = 0.0
    char_spacing_px: float = 0.0
    line_spacing_px: float = 0.0
    outline: dict = field(default_factory=lambda: dict(DEFAULT_OUTLINE))
    glow: dict = field(default_factory=lambda: dict(DEFAULT_GLOW))
    shadow: dict = field(default_factory=lambda: dict(DEFAULT_SHADOW))

    def to_dict(self) -> dict:
        """The hand-picked serialization projection (D-07 single spelling).

        Returns a plain dict of every field — a NEW dict each call (never
        the live dataclass state), with copies of the effect dicts so the
        caller cannot mutate the style through the projection.
        """
        return {
            "font_family": self.font_family,
            "bold": self.bold,
            "italic": self.italic,
            "font_size_px": self.font_size_px,
            "auto_fit": self.auto_fit,
            "color": self.color,
            "align_h": self.align_h,
            "align_v": self.align_v,
            "vertical": self.vertical,
            "rotation_deg": self.rotation_deg,
            "char_spacing_px": self.char_spacing_px,
            "line_spacing_px": self.line_spacing_px,
            "outline": dict(self.outline),
            "glow": dict(self.glow),
            "shadow": dict(self.shadow),
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "TextStyle":
        """Build a ``TextStyle`` from an untrusted dict (the V5 boundary).

        - ``None`` / ``{}`` -> defaults (Pitfall 8 — legacy files).
        - Every numeric is type-checked and clamped (size 1..1024, effect
          widths/radii 0..256, opacity 0..1); non-numeric -> defaults,
          never an exception.
        - Unknown keys are ignored (forward-compatible additive shape).
        - A non-dict / partial effect value falls back per-field to the
          defaults.
        - ``font_size_px`` is forced to ``None`` while ``auto_fit`` is True
          (0 = the Auto sentinel); with a manual size it clamps into
          1..1024.
        """
        if d is None:
            return cls()
        if not isinstance(d, dict):
            # V5: a non-dict style block is garbage — defaults, no raise.
            return cls()

        auto_fit = _coerce_bool(d.get("auto_fit"), True)
        raw_size = d.get("font_size_px")
        if auto_fit or raw_size is None:
            font_size_px: float | None = None
        else:
            font_size_px = _clamp_float(
                raw_size, _FONT_SIZE_MIN, _FONT_SIZE_MAX, None
            )

        align_h = d.get("align_h", "center")
        if not isinstance(align_h, str) or align_h not in _ALIGN_H_VALUES:
            align_h = "center"
        align_v = d.get("align_v", "middle")
        if not isinstance(align_v, str) or align_v not in _ALIGN_V_VALUES:
            align_v = "middle"

        return cls(
            font_family=_coerce_str(d.get("font_family"), DEFAULT_FONT_FAMILY),
            bold=_coerce_bool(d.get("bold"), False),
            italic=_coerce_bool(d.get("italic"), False),
            font_size_px=font_size_px,
            auto_fit=auto_fit,
            color=_coerce_str(d.get("color"), DEFAULT_COLOR),
            align_h=align_h,
            align_v=align_v,
            vertical=_coerce_bool(d.get("vertical"), False),
            rotation_deg=_clamp_float(
                d.get("rotation_deg"), -ROTATION_MAX, ROTATION_MAX, 0.0
            ),
            char_spacing_px=_clamp_float(
                d.get("char_spacing_px"), CHAR_SPACING_MIN, CHAR_SPACING_MAX, 0.0
            ),
            line_spacing_px=_clamp_float(
                d.get("line_spacing_px"), LINE_SPACING_MIN, LINE_SPACING_MAX, 0.0
            ),
            outline=_coerce_effect(d.get("outline"), DEFAULT_OUTLINE),
            glow=_coerce_effect(d.get("glow"), DEFAULT_GLOW),
            shadow=_coerce_effect(d.get("shadow"), DEFAULT_SHADOW),
        )

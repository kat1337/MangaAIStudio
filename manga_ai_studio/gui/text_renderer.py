"""The shared typeset renderer (plan 07-01 Task 1) — ONE code path for the
canvas overlay AND the bake (D-01 single visual truth, RESEARCH Pattern 1).

``layout()`` produces pure geometry (wrap at the inner width, H/V alignment,
the Auto-fit fit loop, the overflow flag); ``paint()`` draws a laid-out
result through a ``QPainter``; ``bake_typeset_page()`` composites every box's
current-focus text onto a DETACHED copy of the page image (D-02/D-04, Pitfall
2); ``current_focus_text()`` is the D-04 content rule shared with the canvas.

Mechanism notes (verified by probe on the pinned Python 3.14.2 / PySide6
6.10.1 stack):

- Text layout uses ``QTextDocument`` (plain-text only — ASVS V5: no
  rich-text rendering of OCR/translation content). The outline is a
  TWO-PASS under-fill (quick-260827-0id): pass 1 paints the whole run as a
  solid outline-color SILHOUETTE dilated by the FULL outline width
  (a doubled-width round-join stroke over an outline-color fill — the
  Minkowski dilation of the glyphs), pass 2 repaints the fill-only
  document on top. The visible ring is ``width_px`` deep OUTWARD of the
  glyphs and interiors stay pure fill (the legacy ``setTextOutline``
  centered stroke put half the band INSIDE the letterforms — an inline at
  SFX widths — and let stacked vertical neighbors chew each other's fill;
  the global silhouette-before-fill ordering in ``_paint_fill_pass`` closes
  both). ``QPainterPath.addText`` + ``strokePath`` remains disqualified on
  this stack (fast-fail 0xC0000409, probed), as does ``QTextLayout``'s
  line machinery before a forced document layout — the QTextDocument glyph
  mechanism is the production-proven one; the UI-SPEC locks the LOOK
  (opaque fill + outward ring at the styled width/color), not the
  mechanism.
- The document layout is FORCED via ``documentLayout().documentSize()``
  before any block-layout reads (reading ``lineAt()`` on an un-laid-out
  block access-violates on this stack).
- Auto-fit preserves the 04-09 machinery at SCENE px (D-15 / UI-SPEC A2):
  box-adaptive base ``14 x min(w,h)/100``, ``[10,28]`` base clamp as the
  STARTING target. GROWTH has no iteration bound (quick-260826-vhh): it stops
  only when the fit predicate fails or ``min(inner_w, inner_h)`` is reached —
  the legacy shared-iteration budget plateaued big-box growth near
  28 x 1.1**11 (~80 px). The never-fits shrink path keeps the exact old shape
  (12 iterations x 0.9, 5 px floor checked at the loop top — no iteration
  ever renders below the floor).
- Overflow renders UNCLIPPED (UI-SPEC A6): ``paint()`` never installs a
  clip; the bake clips only at the page edge (the image's natural bound).

Vertical (tategaki) mode (plan 07-03 Task 1 — D-11, the phase's highest-
risk decision; G-07-1 user override): ``layout(vertical=True)`` returns
per-char placements — Han/Kana, vertical-form punctuation, AND Latin
letters/digits stay UPRIGHT (roman text stacks one letter above the
other, the user override of the W3C rotated-Latin convention); halfwidth
ASCII punctuation plus the bracket/dash set rotate 90 deg clockwise.
Columns stack top-to-bottom, wrap at the inner height, and
flow right-to-left (later chars at smaller x) from the box's right inner
edge; each column is 1 em wide (the max char extent in the column), gap 0;
every char is centered within its column. ``align_h`` shifts the column
BLOCK left/center/right, ``align_v`` shifts the run top/middle/bottom
along the column axis (A3). The vertical Auto-fit variant reuses the same
loop (cap-bounded growth, legacy 12 x 0.9 shrink, 5 px floor) on the column
count (floor(inner_w / 1 em)) and the run's vertical extent. Placements are
INNER-LOCAL coordinates (0..inner_w x 0..inner_h); paint() draws them
after translating to ``result.origin``.

Future polish (CONTEXT Deferred — render-only scope): kumimoji
punctuation compression, tate-chu-yoko digit combining
(text-combine-upright), font vertical alternates, and RTL-script runs
bottom-to-top.

Qt-imports only (QtCore/QtGui + numpy for the bake bridge — no widget or
main-window dependencies) so the module is headless-testable under the
pytest-qt ``qapp`` fixture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)

from manga_ai_studio.core.text_style import TextStyle
from manga_ai_studio.core.text_wrap import break_lines_ex

# ---------------------------------------------------------------------------
# Auto-fit constants (plan 04-09 machinery preserved at scene px — D-15)
# ---------------------------------------------------------------------------
_OVERLAY_INSET = 2.0  # inner margin on every side of the box rect
_OVERLAY_FONT_BASE = 14.0  # scene-px base for the UI-SPEC reference box
_OVERLAY_BOX_REF_DIM = 100.0  # the reference box min dimension
_OVERLAY_FIT_MAX_ITERS = 12  # SHRINK-path budget ONLY (quick-260826-vhh):
# growth is bounded by grow_cap = min(inner_w, inner_h), never by this count.
_OVERLAY_FIT_STEP = 0.9  # per-iteration reduction factor
_OVERLAY_FIT_GROW_STEP = 1.1  # per-iteration growth factor (G-07-4)
_OVERLAY_FIT_FLOOR_PX = 5.0  # hard floor, checked at the loop TOP
_BASE_CLAMP_MIN = 10.0  # [10, 28] base clamp (UI-SPEC A2)
_BASE_CLAMP_MAX = 28.0
_FONT_SIZE_MIN = 1.0
_FONT_SIZE_MAX = 1024.0
_EPS = 1e-6

_ALIGN_H_TO_QT = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}

# ---------------------------------------------------------------------------
# Vertical (tategaki) classification constants (D-11 — RESEARCH Pattern 2,
# Common Operation 2, verbatim; G-07-1 user override). Orientation contract:
#   - Upright:  Han/Kana + vertical-form punctuation (_ALIGN_CENTER) +
#     Latin letters/digits (_ASCII_UPRIGHT — the user override of the W3C
#     rotated-Latin convention: roman text stacks ONE letter above the other).
#   - Rotated 90 deg clockwise: halfwidth ASCII punctuation (0x21..0x7E
#     minus letters/digits) + the bracket/dash set (the typographic
#     rotation convention).
# ---------------------------------------------------------------------------
_ASCII_UPRIGHT = (
    set(chr(i) for i in range(0x30, 0x3A))  # digits 0-9
    | set(chr(i) for i in range(0x41, 0x5B))  # A-Z
    | set(chr(i) for i in range(0x61, 0x7B))  # a-z
)
_ASCII_ROTATE = set(chr(i) for i in range(0x21, 0x7F)) - _ASCII_UPRIGHT
_ROTATE_EXTRA = {
    "「",
    "」",
    "『",
    "』",
    "（",
    "）",
    "《",
    "》",
    "〈",
    "〉",
    "【",
    "】",
    "—",
    "…",
    "～",
    "-",
    "(",
    ")",
}
_ALIGN_CENTER = {"。", "．", "，", "、", "·", "：", "；", "！", "？"}


def char_rotates(ch: str) -> bool:
    """True when ``ch`` must be rotated 90 deg clockwise in vertical text.

    Halfwidth ASCII punctuation (0x21..0x7E minus letters/digits) and the
    bracket/dash/ellipsis set rotate; Latin letters/digits stay UPRIGHT
    (G-07-1 — the user override of the W3C rotated-Latin convention: roman
    text stacks one letter above the other), as do Han/Kana and
    vertical-form punctuation (the ``_ALIGN_CENTER`` set). A multi-char
    string (or the space 0x20) is False.
    """
    if len(ch) != 1:
        return False
    return ch in _ASCII_ROTATE or ch in _ROTATE_EXTRA


# ---------------------------------------------------------------------------
# Effect allocation bounds (D-14 / T-07-07 — the BallonsTranslator
# EffectRasterAllocationError policy: an oversized effect surface degrades
# to no-glow with a loguru warning, never an OOM)
# ---------------------------------------------------------------------------
_EFFECT_MAX_DIMENSION = 4096  # planner-pinned max effect surface dimension
_EFFECT_MAX_PIXELS = 64_000_000  # planner-pinned pixel budget


def effect_padding(style: TextStyle) -> float:
    """The halo/shadow/outline margin around the ink (RESEARCH Pattern 3).

    ``outline width + max(glow radius, shadow radius) + |max offset|`` —
    only enabled effects contribute (skipped effects add nothing). The
    outline term is the FULL ``width_px`` (quick-260827-0id): the rendered
    ring now reaches ``width_px`` OUTSIDE the ink (two-pass silhouette-
    under-fill), so measurement must reserve the whole width. Callers (the
    canvas overlay's measured-crop window in box_item.TypesetOverlayItem,
    the effect surface sizing here) expand the ink by this on every side so
    neither the canvas nor the bake clips the halo (Pitfall 2 guard) — ONE
    shared function keeps the measurement == render contract for both.
    """
    pad = 0.0
    outline = style.outline if isinstance(style.outline, dict) else {}
    if outline.get("enabled", True):
        pad += float(outline.get("width_px", 0.0) or 0.0)
    radii: list[float] = []
    offsets: list[float] = []
    glow = style.glow if isinstance(style.glow, dict) else {}
    shadow = style.shadow if isinstance(style.shadow, dict) else {}
    if glow.get("enabled", False):
        radii.append(float(glow.get("radius_px", 0.0) or 0.0))
    if shadow.get("enabled", False):
        radii.append(float(shadow.get("radius_px", 0.0) or 0.0))
        offsets.append(abs(float(shadow.get("dx", 0.0) or 0.0)))
        offsets.append(abs(float(shadow.get("dy", 0.0) or 0.0)))
    if radii:
        pad += max(radii)
    if offsets:
        pad += max(offsets)
    return pad


@dataclass
class LayoutResult:
    """Geometry of a laid-out text block (horizontal mode).

    Attributes:
        text: The laid-out plain text (the D-04 current-focus text).
        style: The style the layout ran with.
        document: The laid-out ``QTextDocument`` (formats merged — paint()
            draws it verbatim, so canvas and bake share the exact pixels).
        line_rects: Per-line natural rects in DOCUMENT coordinates (the
            engine applies the horizontal alignment).
        ink: The union of the line rects (document coordinates).
        overflow: True when the laid-out block exceeds the box INNER height
            (fixed-size text taller than the box, or the auto-fit floor
            held). Renders unclipped (UI-SPEC A6).
        used_font_size_px: The resolved font size in scene px (the manual
            size, or the auto-fit loop's final target).
        origin: Where paint() must translate to — the box rect top-left
            plus the inner inset plus the vertical-alignment offset.
        inner_size: The inner rect the layout ran against (wrap width /
            fit height).
        vertical_placements: The per-char placement form when the layout
            ran in vertical mode: ``[{char, x, y, rotate, w, h}, ...]`` in
            INNER-LOCAL coordinates (paint() draws them after translating
            to ``origin``). Empty for the horizontal path.
        box_center: The box rect's center in SCENE coordinates — the pivot
            ``paint()`` rotates about when ``style.rotation_deg != 0``
            (quick-260824-viq). Set on EVERY construction site so canvas and
            bake rotate identically (D-01).
    """

    text: str
    style: TextStyle
    document: QTextDocument = field(default_factory=QTextDocument)
    line_rects: list = field(default_factory=list)  # list[QRectF]
    ink: QRectF = field(default_factory=QRectF)
    overflow: bool = False
    used_font_size_px: float = 0.0
    origin: QPointF = field(default_factory=QPointF)
    inner_size: QSizeF = field(default_factory=QSizeF)
    vertical_placements: list = field(default_factory=list)  # list[dict]
    box_center: QPointF = field(default_factory=QPointF)


# ---------------------------------------------------------------------------
# D-04 current-focus rule (shared with the canvas overlay)
# ---------------------------------------------------------------------------


def current_focus_text(pb) -> str:
    """The D-04/D-10 current-focus text: translation when present, else
    recognized, else ``""`` (a box with neither renders/bakes nothing).

    Mirrors ``BoxItem._current_focus_text`` (box_item.py:720-746) — ONE rule
    shared by the canvas overlay and the bake (D-04 WYSIWYG contract).
    Defensive against a payload that is not a real ``TextBlock`` (a bare
    marker object has no ``.text`` / ``.translation`` -> empty).
    """
    payload = pb.payload
    if payload is None:
        return ""
    translation = getattr(payload, "translation", "") or ""
    if translation:
        return translation
    t = getattr(payload, "text", None)
    if t is None:
        return ""
    if isinstance(t, list):
        return "".join(str(s) for s in t).strip()
    return str(t).strip()


# ---------------------------------------------------------------------------
# Font / document helpers
# ---------------------------------------------------------------------------


def _style_font(style: TextStyle, size_px: float) -> QFont:
    """The style's font at ``size_px`` scene px (pixel-accurate for WYSIWYG).

    quick-260824-viq: when ``char_spacing_px`` != 0 the font carries
    ``QFont.AbsoluteSpacing`` letter spacing so MEASUREMENT
    (``_break_lines_for``'s ``QFontMetricsF.horizontalAdvance``) and RENDER
    (the document's char format) share ONE construction — no divergence
    window between where lines break and where glyphs draw. Negative values
    (spacing may TIGHTEN) ride the same channel —
    AbsoluteSpacing accepts negative pixel gaps natively.
    """
    font = QFont(style.font_family)
    font.setBold(style.bold)
    font.setItalic(style.italic)
    font.setPixelSize(max(1, int(round(size_px))))
    char_spacing = float(getattr(style, "char_spacing_px", 0.0) or 0.0)
    if char_spacing != 0.0:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, char_spacing)
    return font


def _valid_color(value: str, default: str) -> QColor:
    """A QColor from ``value``; an invalid string falls back to ``default``."""
    color = QColor(value)
    if not color.isValid():
        color = QColor(default)
    return color


def _outline_pen(style: TextStyle) -> QPen | None:
    """The D-14 outline pen from the style, or ``None`` when disabled/zero.

    RoundCap/RoundJoin at the style's width/color (UI-SPEC outline row:
    0..10 px / default 2; width 0 = off). ``None`` -> no outline pass.
    """
    outline = style.outline if isinstance(style.outline, dict) else {}
    if not outline.get("enabled", True):
        return None
    width = float(outline.get("width_px", 0.0) or 0.0)
    if width <= 0.0:
        return None
    return QPen(
        _valid_color(str(outline.get("color", "#ffffff")), "#ffffff"),
        width,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )


def _build_document(
    text: str,
    style: TextStyle,
    size_px: float,
    inner_w: float,
    wrap: QTextOption.WrapMode = QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere,
) -> QTextDocument:
    """Lay out ``text`` as a PLAIN document at ``size_px`` wrapped per ``wrap``.

    FILL-CANONICAL (quick-260827-0id): the merged ``QTextCharFormat``
    carries ONLY the opaque fill (D-01) — the outline is painted by the
    separate ``_paint_outline_pass`` silhouette UNDER this document, so the
    document is the pure fill pass verbatim. ``wrap`` defaults to the
    legacy greedy engine mode so any caller that has not adopted the owned
    line breaker keeps its behavior; ``layout()`` passes ``NoWrap`` for
    pre-broken lines (quick-260822-wvf). The document layout is FORCED
    before returning so the caller's block-layout reads are safe on this
    stack.
    """
    doc = QTextDocument()
    doc.setPlainText(text)  # ASVS V5: PLAIN text only — no rich-text injection
    doc.setDocumentMargin(0.0)
    doc.setTextWidth(inner_w)
    opt = QTextOption(_ALIGN_H_TO_QT.get(style.align_h, Qt.AlignmentFlag.AlignHCenter))
    opt.setWrapMode(wrap)
    doc.setDefaultTextOption(opt)

    font = _style_font(style, size_px)
    fill = _valid_color(style.color, "#000000")
    fmt = QTextCharFormat()
    fmt.setFont(font)
    fmt.setForeground(QBrush(fill))
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)

    # quick-260824-viq (d): line spacing = a top margin on every block AFTER
    # the first. The margin rides the document layout, so doc height includes
    # the gaps and the overflow check + auto-fit loop account for them with
    # zero extra logic. The existing block format is COPIED and merged (only
    # the top margin changes) — never replaced wholesale.
    #
    # Negative line_spacing (tightening — letters/lines closer than the
    # font's natural gap) CANNOT ride the margin: QTextDocumentLayout clamps
    # negative block margins to zero (probe-verified). LineDistanceHeight IS
    # honored additively (negative pulls the following lines up), and
    # documentSize() accounts for it — so measurement, align_v centering and
    # the auto-fit predicate all stay on the same page. Positive values keep
    # the legacy margin path byte-for-byte.
    line_spacing = float(getattr(style, "line_spacing_px", 0.0) or 0.0)
    if line_spacing > 0.0:
        block = doc.firstBlock().next()  # skip the first block
        while block.isValid():
            bf = QTextBlockFormat(block.blockFormat())
            bf.setTopMargin(line_spacing)
            block_cursor = QTextCursor(block)
            block_cursor.setBlockFormat(bf)
            block = block.next()
    elif line_spacing < 0.0:
        # Tightening branch — see the comment above (LineDistanceHeight is
        # the only mechanism the layout actually honors for negative gaps).
        _LINE_DISTANCE_HEIGHT = 4  # QTextBlockFormat.LineHeightTypes
        block = doc.firstBlock().next()  # skip the first block
        while block.isValid():
            bf = QTextBlockFormat(block.blockFormat())
            bf.setLineHeight(line_spacing, _LINE_DISTANCE_HEIGHT)
            block_cursor = QTextCursor(block)
            block_cursor.setBlockFormat(bf)
            block = block.next()

    # Force the document layout before any block-layout reads (see module
    # docstring — lineAt on an un-laid-out block access-violates here).
    doc.documentLayout().documentSize()
    return doc


def _line_rects(doc: QTextDocument) -> list:
    """Per-line natural rects from the laid-out document (engine-aligned).

    Iterates ALL blocks — the owned breaker (quick-260822-wvf) renders
    pre-broken lines as explicit ``\\n``, and each ``\\n`` starts a new
    QTextDocument block; reading only ``firstBlock()`` would drop every
    line after the first. Each ``naturalTextRect`` is BLOCK-LOCAL, so it
    MUST be translated by ``block.position()`` (cumulative y per block) —
    without it every block's rect reports y=0 and all lines stack/overlap
    (regression found live: bubbles rendered a single clipped line).
    """
    rects: list = []
    block = doc.firstBlock()
    while block.isValid():
        # documentLayout().blockBoundingRect is DOCUMENT-positioned — its
        # topLeft carries the cumulative block offset (PySide6's
        # QTextBlock.position() comes back as a plain int here).
        block_origin = doc.documentLayout().blockBoundingRect(block).topLeft()
        block_layout = block.layout()
        for i in range(block_layout.lineCount()):
            rects.append(
                block_layout.lineAt(i).naturalTextRect().translated(block_origin)
            )
        block = block.next()
    return rects


def _break_lines_for(
    text: str, style: TextStyle, size_px: float, inner_w: float
) -> tuple[list[str], bool]:
    """The owned line breaks for ``text`` at ``size_px`` (quick-260822-wvf,
    extended quick-260823-hge).

    Measures with ``_style_font``'s QFontMetrics horizontalAdvance — the
    SAME rounded pixel size ``_build_document`` renders with (RESEARCH
    pitfall 1; ``_style_font`` int-rounds setPixelSize) — then delegates to
    the Qt-free core breaker (UAX #14 atoms + hyphenation + balancing).

    Returns ``(lines, split_latin)``: ``split_latin`` is True when the
    break had to split a LATIN word (hyphenated or char-split). The
    auto-fit loop treats such a candidate as NOT fitting — a layout that
    had to break a Latin word is a failed fit, not a result.
    """
    font = _style_font(style, size_px)
    fm = QFontMetricsF(font)
    return break_lines_ex(text, fm.horizontalAdvance, inner_w)


# ---------------------------------------------------------------------------
# Vertical (tategaki) layout — pure geometry (D-11, RESEARCH Pattern 2)
# ---------------------------------------------------------------------------


def _vertical_placements(
    text: str, style: TextStyle, inner_w: float, inner_h: float, size_px: float
) -> tuple[list, int, float, float]:
    """Per-char vertical placements at ``size_px`` (INNER-LOCAL coords).

    Returns ``(placements, ncols, block_w, block_h)`` where placements are
    ``[{char, x, y, rotate, w, h}, ...]`` in TEXT order (the first placement
    is the first character). Geometry rules (W3C + BallonsTranslator
    conventions):

    - The char box is the natural glyph box: ``w`` = the horizontal
      advance, ``h`` = the ink rect height. Latin/ASCII boxes are taller
      than wide (h > w); CJK boxes are square (w >= h).
    - Chars stack top-to-bottom; the per-char advance is the box HEIGHT
      (Latin: measured along its height, not its width; CJK: its width
      equals the height — square).
    - A column wraps when the next char would exceed ``inner_h``.
    - Column width = the max horizontal ink extent in the column (upright:
      ``w``; rotated: ``h`` — a rotated glyph's horizontal extent is its
      natural height) — the 1 em basis.
    - Columns flow RIGHT-TO-LEFT, flush (gap 0); the block sits per
      ``align_h`` (right = the natural tategaki origin, first column at the
      right inner edge); ``align_v`` shifts the run along the column axis.
    - Every char is centered within its column.
    """
    # quick-260824-viq (e): the SFX gaps. char_spacing_px widens the gap
    # BETWEEN adjacent columns; line_spacing_px widens the per-char advance
    # ALONG a column (and feeds the wrap predicate so columns break
    # honestly). Both default to 0.0 -> byte-identical legacy geometry.
    char_gap = float(getattr(style, "char_spacing_px", 0.0) or 0.0)
    line_gap = float(getattr(style, "line_spacing_px", 0.0) or 0.0)

    # Measure with the style font MINUS its letter-spacing term: the vertical
    # path adds its own EXPLICIT gaps (char_gap above); leaving
    # QFont.AbsoluteSpacing on would inflate every measured advance and
    # double-count the spacing inside each glyph box.
    font = _style_font(style, size_px)
    if char_gap > 0.0:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.0)
    fm = QFontMetricsF(font)
    chars = list(text)  # code points — never bytes (flagged assumption)
    if not chars:
        return [], 0, 0.0, 0.0

    # Group into columns (top-to-bottom, wrap at inner_h).
    columns: list[list[dict]] = []
    cur: list[dict] = []
    col_y = 0.0
    for ch in chars:
        br = fm.boundingRect(ch)
        w = fm.horizontalAdvance(ch)
        h = br.height()  # the ink height (CJK squares the advance; Latin is taller)
        rot = char_rotates(ch)
        extent = h if rot else w  # horizontal ink extent in the column
        if cur and col_y + h > inner_h + _EPS:
            columns.append(cur)
            cur = []
            col_y = 0.0
        cur.append({"char": ch, "w": w, "h": h, "rotate": rot, "extent": extent})
        col_y += h + line_gap  # the advance includes the inter-char gap
    if cur:
        columns.append(cur)

    col_widths = [max(c["extent"] for c in col) for col in columns]
    block_w = float(sum(col_widths) + char_gap * max(0, len(columns) - 1))
    block_h = float(
        max(
            sum(c["h"] for c in col) + line_gap * max(0, len(col) - 1)
            for col in columns
        )
    )

    if style.align_h == "left":
        dx_block = 0.0
    elif style.align_h == "right":
        dx_block = inner_w - block_w
    else:  # center (the default)
        dx_block = (inner_w - block_w) / 2.0

    if style.align_v == "top":
        dy_block = 0.0
    elif style.align_v == "bottom":
        dy_block = inner_h - block_h
    else:  # middle (the default)
        dy_block = (inner_h - block_h) / 2.0

    placements: list[dict] = []
    x = dx_block + block_w  # the block's RIGHT edge — columns flow leftward
    for col_idx, (col, cw) in enumerate(zip(columns, col_widths)):
        if col_idx > 0:
            x -= char_gap  # the gap between adjacent columns
        x -= cw
        y = dy_block
        for c in col:
            placements.append(
                {
                    "char": c["char"],
                    "x": x + (cw - c["w"]) / 2.0,
                    "y": y,
                    "rotate": c["rotate"],
                    "w": c["w"],
                    "h": c["h"],
                }
            )
            y += c["h"] + line_gap
    return placements, len(columns), block_w, block_h


def layout_vertical(
    text: str,
    style: TextStyle,
    inner_w: float,
    inner_h: float,
    size_px: float | None = None,
) -> list[dict]:
    """Per-char vertical placements for ``text`` inside an inner rect.

    Pure geometry (no painting — RESEARCH A1: a future document-layout
    wrapper can consume these placements): ``[{char, x, y, rotate, w, h},
    ...]`` in INNER-LOCAL coordinates. ``size_px`` is the glyph size; when
    None the style resolves it (manual size, or the vertical Auto-fit loop:
    cap-bounded growth on the column count and vertical extent, the legacy
    12 x 0.9 shrink path, 5 px floor — the horizontal machinery applied to
    vertical metrics).

    Classification and column rules: see the module docstring and
    ``char_rotates`` (G-07-1: Latin letters/digits stay upright, one above
    the other — the user override of the W3C rotated convention). Future
    polish (CONTEXT Deferred): kumimoji
    compression, tate-chu-yoko combining, RTL-script bottom-to-top flow.
    """
    if size_px is None:
        manual = style.font_size_px is not None and not style.auto_fit
        if manual:
            size_px = min(_FONT_SIZE_MAX, max(_FONT_SIZE_MIN, float(style.font_size_px)))
        else:
            size_px = _vertical_fit_size(text, style, inner_w, inner_h)
    placements, _, _, _ = _vertical_placements(text, style, inner_w, inner_h, size_px)
    return placements


def _vertical_fit_size(
    text: str, style: TextStyle, inner_w: float, inner_h: float
) -> float:
    """The vertical Auto-fit size: growth runs until the fit genuinely fails.

    Fit = the layout's column count <= floor(inner_w / 1 em) AND the run's
    vertical extent fits inner_h. Same machinery as the horizontal loop:
    box-adaptive base (the box dims = the inner dims + the constant inset),
    [10,28] clamp as the STARTING target, then grow-while-it-fits with NO
    iteration bound — only a failing fit predicate or ``grow_cap =
    min(inner_w, inner_h)`` stops growth (G-07-4 + quick-260826-vhh: the
    legacy shared 12-iteration budget plateaued big-box growth near
    28 x 1.1**11 (~80 px)). A text that never fits at the base follows the
    exact old shrink path (12 x 0.9 under the dedicated
    ``_OVERLAY_FIT_MAX_ITERS`` SHRINK budget, endpoint identical to the old
    range(12) loop; 5 px floor checked at the loop TOP — no iteration
    renders below it). No extra safety bound is added for growth:
    iterations are ceil(log(grow_cap/start)/log(1.1)) — dozens at most for
    any realistic scene box, each probe cheap relative to a paint.
    """
    box_w = inner_w + 2.0 * _OVERLAY_INSET
    box_h = inner_h + 2.0 * _OVERLAY_INSET
    base = _OVERLAY_FONT_BASE * min(box_w, box_h) / _OVERLAY_BOX_REF_DIM
    target = min(_BASE_CLAMP_MAX, max(_BASE_CLAMP_MIN, base))
    grow_cap = min(inner_w, inner_h)
    size = target
    fit_held = False
    shrink_budget = _OVERLAY_FIT_MAX_ITERS
    while True:
        # Floor check at the loop TOP — no iteration renders below it.
        if target <= _OVERLAY_FIT_FLOOR_PX:
            break
        _, ncols, _, block_h = _vertical_placements(text, style, inner_w, inner_h, target)
        max_cols = max(1, int(inner_w // target))
        if ncols <= max_cols and block_h <= inner_h + _EPS:
            # Fits: keep the last-fitting candidate, then grow (bounded ONLY
            # by the cap — same cap as the horizontal loop; never by an
            # iteration budget).
            size = target
            fit_held = True
            if target >= grow_cap - _EPS:
                break
            target = min(grow_cap, target * _OVERLAY_FIT_GROW_STEP)
        else:
            # Does not fit: after growth, keep the last fit; from the base,
            # the old shrink path under the dedicated shrink budget
            # (endpoint byte-equivalent to the legacy 12-iteration loop).
            if fit_held:
                break
            size = target
            target *= _OVERLAY_FIT_STEP
            shrink_budget -= 1
            if shrink_budget <= 0:
                break
    return size


# ---------------------------------------------------------------------------
# layout() — pure geometry
# ---------------------------------------------------------------------------


def layout(
    text: str, style: TextStyle, box_rect: QRectF, vertical: bool = False
) -> LayoutResult:
    """Lay out ``text`` inside ``box_rect`` per ``style``.

    Horizontal mode (the default): the box rect is shrunk by the inner
    inset on every side; lines are pre-broken by the owned breaker
    (``core/text_wrap`` — balanced, no contraction/punctuation fragments)
    and rendered as explicit ``\\n`` in a NoWrap document; the engine
    applies ``align_h`` per line; ``align_v`` offsets the block via the
    result's ``origin``. A manual size
    (``font_size_px`` set, ``auto_fit`` False) renders exactly at that size
    and reports ``overflow`` when the block exceeds the inner height.
    Auto-fit (the default) runs the 04-09 auto-fit loop at scene px
    (quick-260826-vhh: growth continues past the former iteration-bound
    ~80 px plateau until the fit predicate fails or the box cap is reached).

    Vertical mode (``vertical=True`` — plan 07-03, D-11): the result
    carries ``vertical_placements`` (per-char boxes, upright CJK / rotated
    Latin, RTL columns, wrap at the inner height, per-char centering,
    align_h/align_v block shifts — see ``layout_vertical``); ``origin`` is
    the box top-left + inset and the placements are inner-local. Empty text
    yields an empty result in both modes (renders nothing).
    """
    inner_w = max(1.0, box_rect.width() - 2.0 * _OVERLAY_INSET)
    inner_h = max(1.0, box_rect.height() - 2.0 * _OVERLAY_INSET)
    inner_size = QSizeF(inner_w, inner_h)

    if not text:
        return LayoutResult(
            text=text,
            style=style,
            origin=QPointF(
                box_rect.x() + _OVERLAY_INSET, box_rect.y() + _OVERLAY_INSET
            ),
            inner_size=inner_size,
            box_center=box_rect.center(),
        )

    if vertical:
        return _layout_vertical_result(text, style, box_rect, inner_w, inner_h, inner_size)

    manual = style.font_size_px is not None and not style.auto_fit
    if manual:
        size = min(_FONT_SIZE_MAX, max(_FONT_SIZE_MIN, float(style.font_size_px)))
        # Owned line breaks (quick-260822-wvf): pre-broken \n lines in a
        # NoWrap document — no contraction fragments, glued punctuation, or
        # one-word orphans. The overflow check stays honest (vertical only):
        # AUTHOR INTENT wins at the chosen size — the split_latin flag is
        # deliberately ignored here (quick-260823-hge), but the lines still
        # carry proper pyphen hyphenation when a word had to break.
        lines, _split_latin = _break_lines_for(text, style, size, inner_w)
        doc = _build_document(
            "\n".join(lines),
            style,
            size,
            inner_w,
            wrap=QTextOption.WrapMode.NoWrap,
        )
        overflow = doc.size().height() > inner_h + _EPS
    else:
        # Auto-fit (D-15 / G-07-4): box-adaptive base + [10,28] clamp as the
        # STARTING target, then grow-while-it-fits with NO iteration bound —
        # growth stops only when the fit predicate fails or the cap is hit
        # (quick-260826-vhh removed the shared 12-iteration budget that
        # plateaued big-box growth near 28 x 1.1**11 ~ 80 px). A text that
        # never fits at the base follows the exact old shrink path (12 x 0.9
        # under the dedicated shrink budget, 5 px floor at the loop TOP).
        base = (
            _OVERLAY_FONT_BASE
            * min(box_rect.width(), box_rect.height())
            / _OVERLAY_BOX_REF_DIM
        )
        target = min(_BASE_CLAMP_MAX, max(_BASE_CLAMP_MIN, base))
        grow_cap = min(inner_w, inner_h)
        doc = None
        size = target
        overflow = True
        fit_held = False
        shrink_budget = _OVERLAY_FIT_MAX_ITERS
        while True:
            # Floor check at the loop TOP — no iteration renders below it.
            if target <= _OVERLAY_FIT_FLOOR_PX:
                break
            # Owned line breaks re-computed per candidate size (the same
            # rounded pixel size the candidate document renders with).
            lines, split_latin = _break_lines_for(text, style, target, inner_w)
            candidate = _build_document(
                "\n".join(lines),
                style,
                target,
                inner_w,
                wrap=QTextOption.WrapMode.NoWrap,
            )
            # Fit predicate (quick-260823-hge ordering fix): a candidate is
            # only a fit when its height fits AND its break did not have to
            # split a Latin word — a split layout at an oversized font is a
            # FAILED FIT, not a result. The loop keeps shrinking instead of
            # growing/shrinking around a poisoned layout; the floor check at
            # the loop top stays the escape hatch (the final candidate is
            # accepted with honest overflow).
            fits = candidate.size().height() <= inner_h + _EPS and not split_latin
            if fits:
                # Fits: keep the last-fitting candidate, then grow (bounded
                # ONLY by the cap — the fit check and the cap share the inner
                # box; never by an iteration budget).
                doc, size = candidate, target
                overflow = False
                fit_held = True
                if target >= grow_cap - _EPS:
                    break
                target = min(grow_cap, target * _OVERLAY_FIT_GROW_STEP)
            else:
                # Does not fit: after growth, keep the last fit (never a
                # shrink fall-through); from the base, the old shrink path
                # under the dedicated shrink budget (endpoint byte-equivalent
                # to the legacy 12-iteration loop).
                if fit_held:
                    break
                doc, size = candidate, target
                overflow = True
                target *= _OVERLAY_FIT_STEP
                shrink_budget -= 1
                if shrink_budget <= 0:
                    break

    used_size = float(max(1, int(round(size))))
    block_h = doc.size().height()
    if style.align_v == "bottom":
        dy = inner_h - block_h
    elif style.align_v == "top":
        dy = 0.0
    else:  # middle (default)
        dy = (inner_h - block_h) / 2.0

    rects = _line_rects(doc)
    ink = QRectF()
    for r in rects:
        ink = ink.united(r)

    return LayoutResult(
        text=text,
        style=style,
        document=doc,
        line_rects=rects,
        ink=ink,
        overflow=overflow,
        used_font_size_px=used_size,
        origin=QPointF(
            box_rect.x() + _OVERLAY_INSET,
            box_rect.y() + _OVERLAY_INSET + dy,
        ),
        inner_size=inner_size,
        box_center=box_rect.center(),
    )


def _layout_vertical_result(
    text: str,
    style: TextStyle,
    box_rect: QRectF,
    inner_w: float,
    inner_h: float,
    inner_size: QSizeF,
) -> LayoutResult:
    """The vertical (tategaki) LayoutResult — per-char placements (D-11).

    Manual size: placements at exactly that size; overflow when the column
    BLOCK exceeds the inner rect in either dimension. Auto-fit: cap-bounded
    growth on column count + vertical extent (``_vertical_fit_size``,
    quick-260826-vhh); overflow when the final candidate still does not fit
    (the floor held).
    """
    manual = style.font_size_px is not None and not style.auto_fit
    if manual:
        size = min(_FONT_SIZE_MAX, max(_FONT_SIZE_MIN, float(style.font_size_px)))
        placements, _, block_w, block_h = _vertical_placements(
            text, style, inner_w, inner_h, size
        )
        overflow = block_w > inner_w + _EPS or block_h > inner_h + _EPS
        used = size
    else:
        size = _vertical_fit_size(text, style, inner_w, inner_h)
        placements, ncols, block_w, block_h = _vertical_placements(
            text, style, inner_w, inner_h, size
        )
        max_cols = max(1, int(inner_w // size))
        overflow = not (ncols <= max_cols and block_h <= inner_h + _EPS)
        used = size

    ink = QRectF()
    for p in placements:
        ink = ink.united(QRectF(p["x"], p["y"], p["w"], p["h"]))
    return LayoutResult(
        text=text,
        style=style,
        ink=ink,
        overflow=overflow,
        used_font_size_px=float(max(1, int(round(used)))),
        origin=QPointF(
            box_rect.x() + _OVERLAY_INSET, box_rect.y() + _OVERLAY_INSET
        ),
        inner_size=inner_size,
        vertical_placements=placements,
        box_center=box_rect.center(),
    )


# ---------------------------------------------------------------------------
# paint() — the shared draw path (canvas overlay AND bake)
# ---------------------------------------------------------------------------


def _normalize_rotation(deg) -> float:
    """Normalize an angle into ``(-180, 180]`` degrees (quick-260824-viq).

    Non-finite / non-numeric input yields 0.0 (defensive — a corrupt style
    must never poison the painter transform). ``fmod`` maps onto
    ``(-360, 360)``; the two boundary folds land everything in the half-open
    range so -180 and 180 render identically (one canonical spelling).
    """
    try:
        d = float(deg)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(d) or math.isinf(d):
        return 0.0
    d = math.fmod(d, 360.0)
    if d <= -180.0:
        d += 360.0
    elif d > 180.0:
        d -= 360.0
    return d


def paint(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """Draw ``result`` through ``painter`` — effect passes, then the
    silhouette-then-fill composite.

    Shared by the canvas overlay and the bake (D-01, ONE code path): the
    glow + drop-shadow silhouette passes (D-14) composite BEHIND the glyphs
    (``CompositionMode_DestinationOver``) and the outline silhouette +
    fill composite draws on top (``_paint_fill_pass`` — the outline ring
    extends strictly OUTWARD, quick-260827-0id). Horizontal: the laid-out
    document at ``result.origin`` (engine wrap + alignment). Vertical: the
    per-char placements (upright or rotated 90 deg — never the whole block,
    D-11) drawn through per-char plain documents. No clip is ever installed
    (UI-SPEC A6 — overflow renders unclipped on both the canvas and the
    bake). Effects are skipped when disabled (the default); an oversized
    effect surface degrades to no-glow with a loguru warning (T-07-07),
    never an OOM.

    quick-260824-viq (b): when the style carries a rotation, the WHOLE draw
    (effects + glyphs) rotates about ``result.box_center`` as ONE transform
    applied BEFORE the origin translate — one pivot, identical on canvas and
    bake (D-01). Degrees are CLOCKWISE (Qt's positive-rotate convention,
    documented on the style field).
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    angle = _normalize_rotation(getattr(style, "rotation_deg", 0.0))
    if abs(angle) > _EPS:
        painter.translate(result.box_center)
        painter.rotate(angle)
        painter.translate(-result.box_center)
    painter.translate(result.origin)
    _draw_effects(painter, result, style)
    _paint_fill_pass(painter, result, style)
    painter.restore()


def _paint_fill_pass(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """The ordered composite: outline SILHOUETTE first, then the pure fill.

    quick-260827-0id: the outline pass paints the whole run as an
    outline-color silhouette dilated by the full width BEFORE any fill
    pixel is drawn, so a ring can never chew a neighboring glyph's fill
    (vertical stacks included) and the interior stays pure fill. The
    document itself is fill-canonical (``_build_document`` sets no outline),
    so the fill draw below is the plain glyph verbatim. Zero-cost when the
    outline is disabled/zero (``_paint_outline_pass`` short-circuits on the
    ``None`` pen before any cloning). Also used by the effect silhouette
    builder, so the halo/shadow shape is exactly the composited glyph shape
    the main pass draws — outline ring included (D-01: one shared path).
    """
    _paint_outline_pass(painter, result, style)
    if result.vertical_placements:
        _paint_vertical(
            painter, result, style, _valid_color(style.color, "#000000"), None
        )
    else:
        result.document.drawContents(painter)


def _paint_outline_pass(
    painter: QPainter, result: LayoutResult, style: TextStyle
) -> None:
    """The outline-color SILHOUETTE pass (quick-260827-0id) — the outward ring.

    Paints the whole run as a solid outline-color silhouette dilated by the
    FULL outline width: the silhouette document carries the outline color as
    its fill plus a DOUBLED-width round cap/join stroke — stroke centered on
    the glyph boundary at width 2W reaches W outside and W inside, and the
    inside half is covered again by the later fill pass, so the visible band
    is exactly W deep OUTWARD (a true Minkowski dilation of the glyphs).

    ``None`` pen (outline disabled or width 0) returns immediately — zero
    extra passes, no added pixels, byte-identical to the legacy disabled
    path. Horizontal: a ``_formatted_clone`` of the laid-out document (all
    layout state rides along untouched). Vertical: the per-char variant
    documents driven once with (outline color, silhouette pen).
    """
    pen = _outline_pen(style)
    if pen is None:
        return
    silhouette_pen = QPen(
        pen.color(),
        2.0 * pen.widthF(),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    if result.vertical_placements:
        _paint_vertical(painter, result, style, pen.color(), silhouette_pen)
    else:
        clone = _formatted_clone(result.document, pen.color(), silhouette_pen)
        clone.drawContents(painter)


def _formatted_clone(
    document: QTextDocument, fill: QColor, pen: QPen
) -> QTextDocument:
    """A ``QTextDocument.clone()`` with ONLY foreground + text outline merged.

    The clone preserves ALL layout state (alignment, wrap, block margins,
    textWidth); the Document-selection ``mergeCharFormat`` sets ONLY
    ``setForeground`` + ``setTextOutline``, so fonts/alignment/wrap ride
    along untouched and the clone re-wraps identically — the outline is
    decorative, not part of the metrics.
    """
    clone = document.clone()
    fmt = QTextCharFormat()
    fmt.setForeground(QBrush(fill))
    fmt.setTextOutline(pen)
    cursor = QTextCursor(clone)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)
    return clone


def _paint_vertical(
    painter: QPainter,
    result: LayoutResult,
    style: TextStyle,
    fill_color: QColor,
    pen: QPen | None,
) -> None:
    """Per-char vertical painting (D-11), parameterized per pass.

    Each placement's glyph is drawn centered in its box; classified runs
    rotate 90 deg clockwise around the box center (per-RUN rotation — the
    W3C mixed orientation; never the whole block). Driven TWICE by the
    composite in ``_paint_fill_pass`` (quick-260827-0id): once with the
    outline color + doubled silhouette pen (the silhouette pass), once with
    the style fill and no pen (the fill pass) — the per-char PLAIN document
    is the proven glyph mechanism (``QPainterPath.addText``/``QTextLayout``
    glyph paths crash this Python 3.14.2 / PySide6 6.10.1 stack — see the
    module docstring).
    """
    font = _style_font(style, result.used_font_size_px)
    for p in result.vertical_placements:
        doc = _char_document(p["char"], font, fill_color, pen)
        ntr = _doc_ink_rect(doc)
        if ntr.isNull():
            continue
        painter.save()
        painter.translate(p["x"] + p["w"] / 2.0, p["y"] + p["h"] / 2.0)
        if p["rotate"]:
            painter.rotate(90.0)
        painter.translate(-ntr.center())
        doc.drawContents(painter)
        painter.restore()


def _char_document(char: str, font: QFont, fill: QColor, pen: QPen | None) -> QTextDocument:
    """A single-char PLAIN document with the merged fill/outline format.

    The generic variant-document factory the paint passes drive (the
    vertical path builds one per placement per pass); ``pen=None`` renders
    the fill-only variant. The layout is forced before returning so the
    ink-rect read is stack-safe.
    """
    doc = QTextDocument()
    doc.setPlainText(char)  # ASVS V5: plain text only — no rich-text injection
    doc.setDocumentMargin(0.0)
    fmt = QTextCharFormat()
    fmt.setFont(font)
    fmt.setForeground(QBrush(fill))
    if pen is not None:
        fmt.setTextOutline(pen)
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)
    doc.documentLayout().documentSize()
    return doc


def _doc_ink_rect(doc: QTextDocument) -> QRectF:
    """The first line's natural text rect — the doc-local glyph ink."""
    block = doc.firstBlock()
    layout = block.layout()
    if layout.lineCount() == 0:
        return QRectF()
    return layout.lineAt(0).naturalTextRect()


# ---------------------------------------------------------------------------
# Effect passes — glow + drop shadow (D-14, RESEARCH Pattern 3 / Common
# Operation 5): the glyph silhouette alpha -> numpy stack blur -> colorize
# x opacity -> composited BEHIND the fill (DestinationOver) inside a
# transparent offscreen surface, which is then blitted onto the target
# painter with SourceOver — glow at zero offset, shadow at the style's
# dx/dy. The intermediate surface is what makes the effects visible over
# OPAQUE targets (the bake page, test images): DestinationOver directly
# onto an opaque destination would hide the halo under it.
# ---------------------------------------------------------------------------


def _draw_effects(painter: QPainter, result: LayoutResult, style: TextStyle) -> None:
    """The glow + shadow silhouette passes (skipped when disabled).

    One shared pass for BOTH orientations (D-01): the fill pass is rendered
    into a bounded transparent offscreen surface (the glyph silhouette),
    the blurred/colorized shadow and glow images composite under it with
    DestinationOver, and the combined surface blits onto the target painter
    with SourceOver. An oversized surface degrades to no-glow with a loguru
    warning (T-07-07) instead of OOMing — the caller then draws the fill
    alone.
    """
    glow = style.glow if isinstance(style.glow, dict) else {}
    shadow = style.shadow if isinstance(style.shadow, dict) else {}
    glow_on = bool(glow.get("enabled", False)) and float(
        glow.get("radius_px", 0.0) or 0.0
    ) > 0.0
    shadow_on = bool(shadow.get("enabled", False))
    if not glow_on and not shadow_on:
        return
    ink = result.ink
    if ink.isNull() or ink.width() <= 0.0 or ink.height() <= 0.0:
        return
    pad = effect_padding(style)
    if pad <= 0.0:
        return
    rect = ink.adjusted(-pad, -pad, pad, pad)
    surface = _new_effect_surface(rect)
    if surface is None:
        w = max(1, int(math.ceil(rect.width())))
        h = max(1, int(math.ceil(rect.height())))
        logger.warning(
            "Effect surface {}x{} exceeds the bounded allocation ({} px max "
            "dimension / {} px budget) - glow/shadow skipped",
            w,
            h,
            _EFFECT_MAX_DIMENSION,
            _EFFECT_MAX_PIXELS,
        )
        return

    # 1) The glyph silhouette: the fill pass (outline silhouette + fill
    #    composite — the ring included, quick-260827-0id) rendered into the
    #    surface (transparent background) — the SAME code path as the main
    #    paint; effect_padding reserves the full outline width for it.
    surface_painter = QPainter(surface)
    surface_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    surface_painter.translate(-rect.left(), -rect.top())
    _paint_fill_pass(surface_painter, result, style)
    surface_painter.end()
    alpha = _qimage_argb_to_numpy(surface)[..., 3]

    # 2) Shadow + glow UNDER the fill (DestinationOver — the surface is
    #    transparent where the fill is absent, so the halo shows through).
    surface_painter = QPainter(surface)
    surface_painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_DestinationOver
    )
    if shadow_on:
        surface_painter.drawImage(
            QPointF(
                float(shadow.get("dx", 0.0) or 0.0), float(shadow.get("dy", 0.0) or 0.0)
            ),
            _colorize_alpha(alpha, shadow),
        )
    if glow_on:
        surface_painter.drawImage(QPointF(0.0, 0.0), _colorize_alpha(alpha, glow))
    surface_painter.end()

    # 3) The combined surface over the target (SourceOver — works on opaque
    #    targets like the bake and transparent ones like the overlay cache).
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.drawImage(rect.topLeft(), surface)


def _new_effect_surface(rect: QRectF) -> QImage | None:
    """A bounded transparent ARGB surface for ``rect`` (``None`` when oversized).

    The T-07-07 allocation bound: max dimension + pixel budget; beyond it
    the caller degrades to no-glow (never an OOM).
    """
    w = max(1, int(math.ceil(rect.width())))
    h = max(1, int(math.ceil(rect.height())))
    if max(w, h) > _EFFECT_MAX_DIMENSION or w * h > _EFFECT_MAX_PIXELS:
        return None
    surface = QImage(w, h, QImage.Format.Format_ARGB32)
    surface.fill(Qt.GlobalColor.transparent)
    return surface


def _colorize_alpha(alpha: np.ndarray, effect: dict) -> QImage:
    """Blur + colorize the silhouette alpha into an ARGB effect image."""
    h, w = alpha.shape
    color = _valid_color(str(effect.get("color", "#ffffff")), "#ffffff")
    opacity = float(effect.get("opacity", 1.0) or 1.0)
    radius = float(effect.get("radius_px", 0.0) or 0.0)
    blurred = _blur_alpha(alpha, radius)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0] = color.blue()  # ARGB32 little-endian byte order: B, G, R, A
    arr[..., 1] = color.green()
    arr[..., 2] = color.red()
    arr[..., 3] = (blurred.astype(np.float32) * opacity).astype(np.uint8)
    return _numpy_rgba_to_qimage(arr)


def _blur_alpha(alpha: np.ndarray, radius_px: float) -> np.ndarray:
    """A separable numpy stack blur of the alpha channel (O(1)/px per axis).

    Three box-blur passes give a Gaussian-ish falloff; zero padding keeps
    the halo fading to transparent OUTSIDE the silhouette. Radius 0 is the
    identity (a crisp shadow — the offset > radius contract).
    """
    if radius_px <= 0.0:
        return alpha
    radius = max(1, int(round(radius_px)))
    a = alpha.astype(np.float64) / 255.0
    for _ in range(3):
        a = _box_blur_axis(a, radius, axis=1)
        a = _box_blur_axis(a, radius, axis=0)
    return (a * 255.0).astype(np.uint8)


def _box_blur_axis(a: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """One box-blur pass along ``axis`` (window 2*radius+1, zero padding).

    Cumulative sums make the cost O(1) per pixel regardless of the radius
    (the BallonsTranslator stack-blur shape, numpy-reimplemented).
    """
    k = 2 * radius + 1
    moved = np.moveaxis(a, axis, 0)
    padded = np.pad(
        moved, ((radius, radius),) + ((0, 0),) * (moved.ndim - 1), mode="constant"
    )
    c = np.cumsum(padded, axis=0)
    n = moved.shape[0]
    hi = c[k - 1 : k - 1 + n]
    lo = np.zeros_like(hi)
    lo[1:] = c[0 : n - 1]
    return np.moveaxis((hi - lo) / float(k), 0, axis)


def _qimage_argb_to_numpy(qimg: QImage) -> np.ndarray:
    """An ARGB32 ``QImage`` -> a DETACHED ``(H, W, 4)`` uint8 array.

    Byte order: B, G, R, A (ARGB32 on little-endian). 32-bit scanlines are
    4-byte aligned, so no padding handling is needed; the trailing
    ``.copy()`` detaches (Pitfall 2).
    """
    img = qimg.convertToFormat(QImage.Format.Format_ARGB32)
    h, w = img.height(), img.width()
    raw = bytes(img.bits())
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
    return arr.copy()


def _numpy_rgba_to_qimage(argb: np.ndarray) -> QImage:
    """A ``(H, W, 4)`` uint8 array (B, G, R, A order) -> a DETACHED ARGB32 QImage."""
    h, w = argb.shape[:2]
    qimg = QImage(argb.data, w, h, w * 4, QImage.Format.Format_ARGB32)
    return qimg.copy()  # Pitfall 2 — detach


# ---------------------------------------------------------------------------
# numpy <-> QImage bridges (Pitfall 2 — every conversion detaches)
# ---------------------------------------------------------------------------


def numpy_to_qimage(rgb: np.ndarray) -> QImage:
    """An ``(H, W, 3)`` uint8 RGB array -> a DETACHED ``QImage`` (RGB888).

    The mandatory ``.copy()`` means painting into the returned image never
    mutates the caller's array (the bake's Pitfall 2 discipline).
    """
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return qimg.copy()


def qimage_to_numpy(qimg: QImage) -> np.ndarray:
    """A ``QImage`` -> a DETACHED ``(H, W, 3)`` uint8 RGB array.

    Handles Qt's 4-byte scanline padding (the CR-08 lesson — bytesPerLine
    can exceed ``w * 3``) and detaches with a trailing ``.copy()`` so the
    array never aliases the QImage buffer.
    """
    img = qimg.convertToFormat(QImage.Format.Format_RGB888)
    h, w = img.height(), img.width()
    bytes_per_line = img.bytesPerLine()
    raw = bytes(img.bits())
    if bytes_per_line == w * 3:
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
    else:
        strided = np.frombuffer(raw, dtype=np.uint8, count=h * bytes_per_line)
        arr = strided.reshape(h, bytes_per_line)[:, : w * 3].reshape(h, w, 3)
    return arr.copy()


# ---------------------------------------------------------------------------
# bake_typeset_page() — the D-02/D-04 compositor
# ---------------------------------------------------------------------------


def bake_typeset_page(page_np: np.ndarray, boxes: list) -> np.ndarray:
    """Composite every box's typeset text onto a DETACHED copy of the page.

    For each box in order: the D-04 current-focus text (translation else
    recognized; neither -> nothing), the flat per-box ``TextStyle`` (defaults
    when the box has none), and the same ``layout`` + ``paint`` functions the
    canvas overlay uses — canvas ≡ bake (D-01, the Pitfall 2 guard). The
    input page is never mutated: the compositor works on a detached QImage
    copy and the result detaches again (Pitfall 2).

    Args:
        page_np: The ``(H, W, 3)`` uint8 RGB page image (the current canvas
            state — same coordinate space as ``_ocr.json``).
        boxes: The page's ``PageBox`` list.

    Returns:
        A new ``(H, W, 3)`` uint8 array with the text composited at 1:1.
    """
    qimg = numpy_to_qimage(page_np).copy()  # Pitfall 2 — never the live page
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        for pb in boxes:
            text = current_focus_text(pb)
            if not text:
                continue
            style = pb.style if pb.style is not None else TextStyle()
            x, y, w, h = pb.box.as_tuple_xywh
            # G-07-1: the render vertical flag is bool(style.vertical) ONLY —
            # the box payload's `vertical` field is pure export metadata,
            # never a render instruction — the SAME single expression
            # box_item.refresh_text_overlay and
            # main_window._style_rendered_size use (no divergence window).
            vertical = bool(style.vertical)
            result = layout(text, style, QRectF(x, y, w, h), vertical=vertical)
            paint(painter, result, style)
    finally:
        painter.end()
    return qimage_to_numpy(qimg).copy()

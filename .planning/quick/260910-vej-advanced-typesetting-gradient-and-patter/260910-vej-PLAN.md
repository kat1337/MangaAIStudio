---
phase: quick-260910-vej
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/text_style.py
  - manga_ai_studio/gui/text_renderer.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/main_window.py
  - tests/test_core/test_text_style.py
  - tests/test_core/test_typeset_fill.py
  - tests/test_core/test_project_io.py
  - tests/test_gui_inspector_styling.py
autonomous: true
requirements: [QUICK-260910-vej]
estimate:
  tokens: 120000
  raw_tokens: 85000
  tasks: 3
  confidence: low
must_haves:
  truths:
    - A box with fill_type=gradient renders a linear Color A→Color B ramp at the box's angle (0° left→right, 90° top→bottom, A at start) identically on the canvas overlay and in the export bake (one shared QBrush fill path).
    - A box with fill_type=pattern renders the user's embedded tile repeated and clipped to the glyphs, scaled by pattern_scale, with Color A's alpha applied as tile opacity, identically on canvas and bake.
    - The Inspector Fill row offers Solid | Gradient | Pattern with conditional sub-controls (Color B + Angle for gradient; image picker + Scale for pattern) and the color swatch previews the real fill over the checkerboard.
    - Gradient and pattern fields (embedded tile bytes included) round-trip .mas save→load losslessly; an oversized tile (>4 MB) is rejected with a warning dialog, never a corrupt save.
    - Legacy projects (no fill_type key) load and render as Solid, pixel-unchanged.
  artifacts:
    - manga_ai_studio/core/text_style.py (fill_type/fill_color_b/fill_angle_deg/pattern_scale/pattern_tile_b64 + V5 coercion + to_dict/from_dict)
    - manga_ai_studio/gui/text_renderer.py (style-fill brush factory wired into _build_document + _paint_fill_pass/_paint_vertical, tile decode/scale/alpha cache)
    - manga_ai_studio/gui/inspector_panel.py (Fill combo row + Color B/Angle/Image/Scale conditional rows + preview swatch modes + WR-01 memories)
    - manga_ai_studio/gui/main_window.py (fill commit handler riding _inspector_style_commit/_replace_style)
    - tests/test_core/test_typeset_fill.py (gradient math + pattern tiling/alpha + bake parity, headless)
  key_links:
    - TextStyle.to_dict ↔ project_io pagebox_to_json "style" block (existing seam — zero project_io changes expected)
    - fill brush factory ↔ _build_document / _paint_fill_pass ↔ TypesetOverlayItem.set_content (box_item.py:711) + bake_typeset_page (text_renderer.py:1354) — canvas ≡ bake is structural
    - Inspector style_fill_changed ↔ MainWindow fill handler ↔ _replace_style (main_window.py:4864) ↔ refresh_text_overlay
---

<objective>
Advanced typesetting fills: text glyph fill becomes a 3-way choice — Solid (today's behavior, byte-identical) | Gradient (linear, 2 stops, per-box angle) | Pattern (user-loaded image tile, tiled + clipped to glyphs, scaled, Color A alpha as opacity) — riding the existing single shared QBrush fill path so WYSIWYG between canvas and bake is structural, with full .mas round-trip and embedded tiles.

Purpose: metallic two-tone text, white→transparent fade-outs, and authentic licensed screentone tiles (per quick-260910-vej CONTEXT, all decisions LOCKED — linear+angle only, image tiles only).
Output: TextStyle fill fields + shared-renderer gradient/pattern brushes + Inspector Fill row + persistence/tests.

FEASIBILITY PROVEN AT PLAN TIME: a headless probe on the pinned stack (Python 3.14.2 / PySide6 6.10.1, QT_QPA_PLATFORM=offscreen) confirmed `QTextCharFormat.setForeground` honors BOTH a `QBrush(QLinearGradient)` (top pixel RGB≈(17,17,238) → bottom RGB≈(174,174,81) for a blue→yellow ramp spanning the doc) and a `QBrush(texture-image)` with `Qt.BrushStyle.TexturePattern` (tile colors sampled at glyph top/bottom). No new compositing machinery is needed — the gradient/texture brush rides the exact same setForeground call sites the solid fill uses today.
</objective>

<execution_context>
@C:/Users/Stella/.zcode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.zcode/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@manga_ai_studio/core/text_style.py
@manga_ai_studio/gui/text_renderer.py
@manga_ai_studio/gui/inspector_panel.py
@.planning/quick/260910-vej-advanced-typesetting-gradient-and-patter/260910-vej-CONTEXT.md

Prior quick 260909-nj9 established the alpha-capable color machinery this builds on: `#AARRGGBB` HexArgb storage on `TextStyle.color`, the `_norm_hex_a` WR-01 guard (inspector_panel.py:225), the alpha-capable `QColorDialog` (`_pick_style_color`, inspector_panel.py:1621 — `ShowAlphaChannel | DontUseNativeDialog` is REQUIRED on Windows), and the `_ColorSwatchButton` checkerboard (inspector_panel.py:245).

Key fill-path facts (verified at plan time):
- The single fill path: `paint()` (text_renderer.py:960) is shared by `TypesetOverlayItem.set_content` (box_item.py:711, cached-pixmap canvas render) and `bake_typeset_page` (text_renderer.py:1354, export). Horizontal fill = `_build_document` line 413-416 (`fmt.setForeground(QBrush(_valid_color(style.color, "#000000")))`, document laid out and layout FORCED at line 457 before return). Vertical fill = `_paint_fill_pass` line 1011-1014 → `_paint_vertical` (line 1075) → `_char_document` (line 1109), each char doc drawn translated to `(p.x + p.w/2 − ntr.center().x, p.y + p.h/2 − ntr.center().y)`.
- The outline SILHOUETTE pass (`_paint_outline_pass` → `_formatted_clone`, line 1054) and the effect silhouette (`_draw_effects`, line 1153) ride `_paint_fill_pass` and must stay UNTOUCHED: `_formatted_clone` overrides foreground with the solid outline color, and the effect surface alpha follows whatever brush the fill pass carries (correct behavior — a transparent gradient stop fades the halo too).
- `LayoutResult` carries `document` + `ink` (document coordinates). `_build_document` forces layout before returning, so a gradient rect can be computed from the laid-out doc size at the end of that function.
- Persistence is already additive: `pagebox_to_json` writes `"style": pb.style.to_dict()` (project_io.py:289) and `json_to_pagebox` rebuilds via `TextStyle.from_dict(d.get("style"))` (project_io.py:369) — new to_dict/from_dict fields flow into .mas with ZERO project_io changes. Unknown keys are ignored on old loaders (forward-compatible additive shape precedent).
- Inspector conventions to follow: WR-01 emit-if-changed with `_loaded_*` memories (line 650-680), D-10 "Mixed" sentinel via `set_styles` multi path (line ~919) and `_load_effect_row_multi` (line 1106), `blockSignals` on every programmatic load, commits ride class-scope Signals → `connect_commit_handlers` (line 1349) → MainWindow `*_committed` handlers (e.g. `_on_inspector_style_color_committed`, main_window.py:4976) → `_inspector_style_commit(lambda item: self._replace_style(item.pagebox, ...))` (main_window.py:4864, dataclasses.replace — NEVER mutate in place).
- Model conventions: numeric V5 clamps via `_clamp_float`, string V5 via `_coerce_str`, enum-ish via allowed-values check falling back to default (align_h pattern, text_style.py:259-264); public bound constants shared with the UI so UI range == model clamp by construction (`EFFECT_GEOM_MAX` precedent, text_style.py:76).
- Tests: renderer suites run headless under the pytest-qt `qapp` fixture (tests/test_core/test_text_renderer.py shape); GUI suites use `qtbot`; pixel sampling pattern = `np.frombuffer(bytes(img.bits()), dtype=np.uint8).reshape(h, w, 4)` (BGRA, little-endian ARGB32 — text_renderer.py:1293 `_qimage_argb_to_numpy`). ALWAYS the pinned interpreter from AGENTS.md: `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest ...` (never bare `python`/`pytest`).

TESTS MUST BOOTSTRAP Qt like the probe did: `QGuiApplication([])` must exist before the first `QFont` construction — a bare script constructing QFont pre-app crashes this stack (exit 127, observed at plan time). Under pytest the `qapp` fixture handles this.
</context>

<tasks>

<task type="auto">
  <name>Task 1: TextStyle fill framework — fields, V5 coercion, serialization (.mas round-trip)</name>
  <files>manga_ai_studio/core/text_style.py, tests/test_core/test_text_style.py, tests/test_core/test_project_io.py</files>
  <action>
Extend `TextStyle` (Qt-free, per D-07 the single serialization spelling) with five fields, keeping every default legacy-identical:
- `fill_type: str = "solid"` — one of `("solid", "gradient", "pattern")`; define the tuple as a module constant `FILL_TYPES` and a `FILL_TILE_MAX_BYTES = 4 * 1024 * 1024` public constant (the UI imports the cap so model + dialog share one symbol — EFFECT_GEOM_MAX precedent).
- `fill_color_b: str = "#ffffff"` — gradient stop B; same verbatim-hex discipline as `color` (docstring: `#RRGGBB`/`#AARRGGBB`, validated at RENDER time via `_valid_color`, never at load).
- `fill_angle_deg: float = 90.0` — CLOCKWISE degrees, 0° = left→right, 90° = top→bottom (Color A at start), clamped 0.0..360.0 via `_clamp_float`; document the semantics on the field exactly as `rotation_deg` documents clockwise.
- `pattern_scale: float = 1.0` — uniform tile zoom, clamped 0.1..10.0 via a public `PATTERN_SCALE_MIN/MAX` constant pair.
- `pattern_tile_b64: str | None = None` — base64 of the ORIGINAL tile file bytes (format-agnostic: PNG/JPG/WebP — whatever QImage.fromData decodes); `_coerce_str(d.get(...), None)`-style: a non-str value loads as None; NO size clamp at load (load robustness — the 4 MB cap is a pick-time UI guard; a larger legacy hand-edited value still loads).
`to_dict` adds all five; `from_dict` coerces `fill_type` through the allowed-values-set fallback (`solid` on anything else — the align_h pattern at text_style.py:259) and the numerics through `_clamp_float`. Update the module docstring (the fill paragraph after the quick-260909-nj9 paragraph). PageBox/copy machinery needs no change (dataclasses.replace carries new fields automatically).
Persistence: verify (do not modify unless a test proves otherwise) that `pagebox_to_json`/`json_to_pagebox` need zero edits — style rides to_dict/from_dict. Add a round-trip test in tests/test_core/test_project_io.py: a PageBox whose style is gradient(angle 37, A=#80ff0000, B opaque) + a pattern style with a small real PNG b64 tile survives `pagebox_to_json` → `json.dumps` → `json.loads` → `json_to_pagebox` field-for-field, and a legacy box dict with NO fill keys loads as fill_type "solid" with defaults. Extend tests/test_core/test_text_style.py: full round-trip of a style carrying all five fields; V5 cases — `fill_type: "radial"` → "solid", `fill_type: 3` → "solid", angle -5 → 0.0 / 720 → 360.0, scale 0.01 → 0.1 / 99 → 10.0, `pattern_tile_b64: 123` → None, and `from_dict({})`/`from_dict(None)` yield the legacy defaults exactly.
  </action>
  <verify>
    <automated>C:/Users/Stella/.pyenv/pyenv-win/versions/3.14.2/python.exe -m pytest tests/test_core/test_text_style.py tests/test_core/test_project_io.py -q</automated>
  </verify>
  <done>
All five fields exist with the specified defaults and bounds; `from_dict(to_dict(s))` is field-for-field equal for a fully-populated fill style; a legacy dict (no fill keys) yields fill_type "solid"; the .mas-style round-trip test passes; the existing full test_text_style.py suite stays green (no default changed for legacy styles).
  </done>
</task>

<task type="auto">
  <name>Task 2: Shared-renderer gradient + pattern fill brushes (horizontal, vertical, bake parity)</name>
  <files>manga_ai_studio/gui/text_renderer.py, tests/test_core/test_typeset_fill.py</files>
  <action>
Add ONE brush factory, e.g. `style_fill_brush(style, rect, offset=(0.0, 0.0)) -> QBrush`, in text_renderer.py and wire it into the two fill call sites. All behavior rides the EXISTING `setForeground(QBrush)` sites — do not add compositing passes.

1) Gradient branch (CONTEXT: linear only, 2 stops, per-box angle): direction vector `d = (cos θ, sin θ)` in y-down doc coordinates with θ = fill_angle_deg in radians — this gives 0° = left→right and 90° = top→bottom (clockwise convention, matching the field docstring). Span `rect` (the text bbox) corner-to-corner: `r = (rect.width()*abs(cos θ) + rect.height()*abs(sin θ)) / 2.0`, start = `rect.center() − d*r`, end = `rect.center() + d*r`; stop 0.0 = `_valid_color(style.color, "#000000")` (Color A), stop 1.0 = `_valid_color(style.fill_color_b, "#ffffff")` — QColor alpha carries through so white→transparent fades need no extra machinery (LOCKED decision). The `offset` argument translates start/end (vertical per-char mapping, below).
2) Pattern branch: decode `style.pattern_tile_b64` via `QImage.fromData` → scale by `pattern_scale` (`QImage.scaled`, SmoothTransformation, min 1px per side) → multiply the tile's alpha channel by Color A's `alpha()/255` (the LOCKED single-opacity-control rule; use the existing numpy BGRA bridge `_qimage_argb_to_numpy` + `_numpy_rgba_to_qimage`) → `QBrush(tile_img)` with `Qt.BrushStyle.TexturePattern`. Anchor the tiling at the doc-local origin via the brush's transform when `offset != (0,0)`: `QBrush.setTransform(QTransform.fromTranslate(-ox, -oy))`.
3) Cache (CONTEXT: decoded tile cached like other render assets): a small module-level bounded dict (evict-oldest, ~8 entries) keyed by `(hashlib.md5(pattern_tile_b64), round(pattern_scale, 4))` holding the decoded+SCALED tile PRE-alpha-modulation (alpha applied per brush build from a copy — keeps the cache value reusable across alpha changes). QImage cache values are shared read-only (implicitly-shared, copy-on-write) — safe across the bake worker thread and GUI thread; note this in a comment.
4) Fallbacks (never crash): `pattern` with None/undecodable tile, or a decoded tile whose max dimension exceeds 8192 (crafted-file guard), renders SOLID Color A + one loguru warning; `gradient`/`pattern` fall back through `_valid_color` exactly like today. Unknown fill_type renders solid (defense in depth — from_dict already normalizes).
5) Wiring, keeping Solid byte-identical: in `_build_document`, AFTER the forced layout (line 457), when `style.fill_type != "solid"`, merge the gradient/pattern brush as foreground over the Document selection using `rect = QRectF(0, 0, doc.documentLayout().documentSize().width(), ...height())` (doc-local bbox — the probe verified doc-local gradient coordinates span the glyphs). In `_paint_fill_pass` (line 1011-1014), the vertical branch computes the per-char doc draw origin `R_p = (p.x + p.w/2 − ntr.center().x(), p.y + p.h/2 − ntr.center().y())` from the same math `_paint_vertical` uses, and builds each char's brush with `offset=R_p` so ONE continuous ramp/tiling spans the whole column (not per-char resets); pass the brush (or a brush-builder callable) into `_paint_vertical`/`_char_document` as an additive parameter defaulting to today's solid behavior. `_paint_outline_pass`, `_formatted_clone`, `_outline_pen`, `_draw_effects`, and the horizontal `result.document.drawContents` call stay untouched — the doc itself now carries the brush, and the silhouette passes inherit its alpha for free. `bake_typeset_page` needs ZERO changes (it calls the same layout+paint — D-01 structural).

New test file tests/test_core/test_typeset_fill.py (qapp fixture, QT_QPA_PLATFORM offscreen via pytest-qt; pixel samples via the BGRA reshape pattern; sample INSIDE a glyph using an alpha-bbox scan like the plan-time probe, never fixed coordinates):
- Solid regression: `fill_type="solid"` renders the same dominant pixel colors as a legacy style (byte-identical path).
- Gradient math, unit-level: the factory's start/end points for rect+angle cases 0/45/90/270 (direction, corner-to-corner span, center symmetry).
- Gradient render: 90° blue→yellow samples top≈blue / bottom≈yellow / mid≈interpolated; 0° swaps to left/right; 270° inverts; alpha stop (A=#00ffffff fully transparent) yields near-zero alpha at that end (fade-out use case).
- Vertical continuity: a tategaki column of ≥3 chars with 90° gradient — top char ≈ Color A, bottom char ≈ Color B (the offset mapping works).
- Pattern: 2-color tile — two samples one tile-period apart share the color (tiling repeats), a `pattern_scale=2` render differs from scale=1 at the same point; alpha modulation: tile alpha 255 with Color A alpha 128 → sampled alpha ≈ 128.
- Fallbacks: pattern with garbage b64 → solid Color A pixels, no exception; pattern with None tile → solid.
- Bake parity (D-01): `bake_typeset_page` on a synthetic page with a gradient box and a pattern box — sampled glyph pixels equal the equivalent direct `layout()+paint()` render within a small tolerance (existing test_typeset_bake.py equivalence pattern).
  </action>
  <verify>
    <automated>C:/Users/Stella/.pyenv/pyenv-win/versions/3.14.2/python.exe -m pytest tests/test_core/test_typeset_fill.py tests/test_core/test_text_renderer.py tests/test_core/test_typeset_bake.py -q</automated>
  </verify>
  <done>
Gradient renders A→B at the styled angle with alpha stops; pattern tiles/scales with Color A alpha; vertical text carries one continuous fill; pattern fallbacks never raise; bake ≡ canvas pixels for both new fill types; every pre-existing renderer/bake test stays green (solid path untouched).
  </done>
</task>

<task type="auto">
  <name>Task 3: Inspector Fill row (type selector + conditional controls + preview swatch) and MainWindow commit wiring</name>
  <files>manga_ai_studio/gui/inspector_panel.py, manga_ai_studio/gui/main_window.py, tests/test_gui_inspector_styling.py</files>
  <action>
InspectorPanel (follow the established row/WR-01/Mixed conventions exactly):
1) New "Fill" combo row ABOVE the existing "Color" row (inspector_panel.py:600-605): items `Solid | Gradient | Pattern` plus the D-10 "Mixed" sentinel when selected styles disagree. New class-scope Signal `style_fill_changed = Signal(dict)` carrying model-keyed changes, e.g. `{"fill_type": "gradient", "fill_color_b": "#ff0000", "fill_angle_deg": 45.0}` or `{"fill_type": "pattern", "pattern_scale": 2.0, "pattern_tile_b64": ...}` — only the fields the user actually changed (per-key WR-01 guards).
2) Conditional sub-rows, shown/hidden by fill type (`setVisible` on widget + `form.labelForField`): Gradient → "Color B" `_ColorSwatchButton` (alpha-capable picker, `_pick_style_color` pattern with `ShowAlphaChannel | DontUseNativeDialog`) + "Angle" QSpinBox 0..359, suffix "°", default 90, tooltip documenting clockwise/0°=left→right/90°=top→bottom. Pattern → "Image…" QToolButton opening `QFileDialog.getOpenFileName` (image-name filter) + "Scale" QDoubleSpinBox 0.10..10.00, suffix "×", step 0.05, default 1.00 — UI ranges == model clamps from Task 1's constants (FILL_TYPES / PATTERN_SCALE_MIN/MAX / FILL_TILE_MAX_BYTES imported from text_style). Controls commit through `style_fill_changed`.
3) Tile pick path: read the file BYTES in the panel; if `len(bytes) > FILL_TILE_MAX_BYTES` show a `QMessageBox` warning (file size vs cap, "Use a smaller tile" copy — the LOCKED warning dialog) and commit NOTHING on reject/oversize; on accept commit `{"fill_type": "pattern", "pattern_tile_b64": base64...}`. WR-01: re-picking a file whose bytes equal the loaded tile (compare decoded b64 against the loaded memory) is a no-op.
4) Swatch previews the REAL fill (LOCKED UI decision): extend `_ColorSwatchButton` with an optional preview state — `mode: "solid"|"gradient"|"pattern"` plus gradient params (Color B, angle) or a tile QImage; paintEvent keeps today's solid/checkerboard/Mixed paint for mode "solid" and for gradient paints a `QLinearGradient` ramp (same angle semantics) over the existing checkerboard when either stop is sub-opaque, and for pattern paints the tile `QImage` tiled over the checkerboard (opacity = Color A alpha). The MAIN Color swatch previews in all three modes; the Color B swatch stays a solid swatch.
5) Load paths: `load_box`/`set_styles` single path (line ~1065 region) loads fill_type/color_b/angle/scale/tile with `blockSignals` + `_loaded_style_fill` memories; the multi path (line ~919 + `_load_effect_row_multi` pattern) shows the "Mixed" sentinel when fill types differ and hides/greys sub-controls on mixed tile/angle/scale — the sentinel NEVER commits. `clear()` resets to Solid defaults.
6) MainWindow: `connect_commit_handlers` gains `on_style_fill`; `_on_inspector_style_fill_committed(changes: dict)` mirrors `_on_inspector_style_color_committed` (main_window.py:4976): `self._inspector_style_commit(lambda item: self._replace_style(item.pagebox, **changes))` — dataclasses.replace keeps BOXES undo snapshots correct; `pattern_tile_b64` absent from a commit never clobbers an existing tile (only commit it on a real pick). Wire the new signal in the `InspectorPanel(...)` construction site (the on_style_color wiring at main_window.py:4978 area / connect_commit_handlers call ~4389).

Tests in tests/test_gui_inspector_styling.py (qtbot, existing file conventions): fill combo switch emits `style_fill_changed` with the right keys; conditional rows visible exactly for Gradient/Pattern; Angle/Scale WR-01 no-op on unchanged commit; re-picking the same tile is a no-op; oversize tile (write a >4 MB random-noise PNG in tmp_path, or monkeypatch the cap constant smaller — prefer the real cap with a genuinely oversized noise PNG) shows the warning and commits nothing (monkeypatch QMessageBox.question/execution to an auto-reject); Mixed fill types show the sentinel and commit nothing; swatch preview paint smoke-tests (gradient/pattern modes render without exceptions, checkerboard present when sub-opaque); MainWindow handler applies to ALL selected boxes via `_replace_style` and tile bytes survive a style commit; legacy style (fill_type solid) displays Solid. Run the full affected suites at the end.
  </action>
  <verify>
    <automated>C:/Users/Stella/.pyenv/pyenv-win/versions/3.14.2/python.exe -m pytest tests/test_gui_inspector_styling.py tests/test_core/test_typeset_fill.py tests/test_core/test_text_style.py -q</automated>
  </verify>
  <done>
Fill row switches Solid/Gradient/Pattern with conditional sub-controls; commits ride style_fill_changed → _replace_style for every selected box; the swatch previews the real gradient/tiled fill; oversize tiles warn and never commit; Mixed never commits; WR-01 guards hold; all new + pre-existing inspector tests green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| tile file → app | User-picked image bytes from disk decoded by QImage (pick path) |
| .mas meta.json "style" → app | Untrusted base64 tile bytes in a loaded project (load path) |
| inspector commit → model | Dict payload drives **changes into _replace_style |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-vej-01 | Tampering | pattern_tile_b64 in loaded .mas | medium | mitigate | Decode fully guarded: QImage.fromData null-result + 8192px max-dimension guard → solid fallback + loguru warning, never an exception or unbounded allocation; load path never re-encodes |
| T-vej-02 | DoS | oversized/mega-pixel tile decode | medium | mitigate | 4 MB pick-time byte cap with warning dialog (FILL_TILE_MAX_BYTES shared constant) + renderer-side decode-dimension guard (T-vej-01); cached decode bounded (LRU ~8) |
| T-vej-03 | Information Disclosure | gradient/pattern fields in shared projects | low | accept | Fields are styling data the user chose to embed (tile bytes); same exposure as existing embedded page pixels in .mas |
| T-vej-04 | Tampering | style_fill_changed dict into **changes | low | mitigate | MainWindow handler forwards only known TextStyle fill keys (explicit kwargs set, not a blind **changes pass-through) |
</threat_model>

<verification>
- Pinned interpreter for every verify command (AGENTS.md): C:/Users/Stella/.pyenv/pyenv-win/versions/3.14.2/python.exe -m pytest
- Full affected suite at close: tests/test_core/test_text_style.py tests/test_core/test_project_io.py tests/test_core/test_typeset_fill.py tests/test_core/test_text_renderer.py tests/test_core/test_typeset_bake.py tests/test_gui_inspector_styling.py
- Full-suite regression at close: -m pytest -q (baseline 1458 passed + 2 known clipboard flakes — new count must be a strict superset with 0 new failures)
- Manual smoke (executor, offscreen-safe): build a gradient box + pattern box in a scratch project, save .mas, reopen — fills identical; open a Phase-7-era project — renders Solid unchanged
</verification>

<success_criteria>
- Text fill is a real 3-way choice (Solid | Gradient | Pattern) on the shared QBrush path — canvas TypesetOverlayItem and bake_typeset_page render identically for all three (D-01 structural, pixel-test-proven)
- Gradient: linear, 2 stops (Color A = existing color field, new Color B), per-box clockwise angle defaulting 90° top→bottom, alpha-carrying stops, spanning the text bbox — no radial, no N-stop editor (LOCKED)
- Pattern: user-loaded image tile, tiled + clipped to glyphs, uniform scale control, tile drawn at Color A's alpha, tile bytes EMBEDDED in .mas with the 4 MB cap + warning dialog — no procedural halftone (LOCKED)
- Persistence: all fill fields round-trip .mas; legacy projects (no fill_type) load Solid unchanged
- Inspector: Fill row with type selector, conditional Color B/Angle and Image/Scale controls, swatch previews the real fill, WR-01 + Mixed conventions respected
- No default behavior change for existing projects
</success_criteria>

<output>
Create `.planning/quick/260910-vej-advanced-typesetting-gradient-and-patter/260910-vej-SUMMARY.md` when done
</output>

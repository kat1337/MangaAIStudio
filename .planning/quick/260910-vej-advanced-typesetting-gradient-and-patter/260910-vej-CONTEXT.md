# Quick Task 260910-vej: Advanced typesetting — gradient and pattern text fills - Context

**Gathered:** 2026-09-11
**Status:** Ready for planning

<domain>
## Task Boundary

Start the advanced typesetting system: text fill is no longer a single solid color. Two new fill types for typeset text — **gradient fill** (linear, per-box angle, two colors) and **pattern fill** (user-provided image/texture tile clipped to the glyphs). Both must render identically on canvas and in export (the shared D-01 fill path), and round-trip through .mas projects.

</domain>

<decisions>
## Implementation Decisions

### Gradient design (user-selected)
- **Linear gradient with per-box angle.** Two color stops: Color A (the existing `TextStyle.color` field) and a new Color B, plus an angle control in degrees. Default angle 90° = top→bottom (Color A at top).
- No radial gradients, no arbitrary N-stop editing (explicitly declined for now).

### Pattern meaning (user-selected)
- **Image/texture tile fill.** The user loads an image file (e.g. PNG screentone pack tile); the tile is repeated and clipped to the glyphs. This replaces procedural halftone generation (declined for now).
- Tile scale control (uniform zoom of the tile before tiling).

### Claude's Discretion (not selected for discussion — sensible defaults below)
- **Slice scope:** one quick task covering the fill-type framework (`fill_type: solid | gradient | pattern` on TextStyle) + gradient + image-tile pattern. If the planner judges this exceeds quick-task size, split gradient-first and pattern immediately after, keeping the framework task shared.
- **Gradient stops carry alpha:** both colors go through the now-alpha-capable picker, so white→transparent fades need no new machinery.
- **Angle semantics:** clockwise degrees, 0° = left→right, 90° = top→bottom; gradient spans the text bbox.
- **Where fills apply:** glyph fill only (canvas overlay + export bake — the shared path makes WYSIWYG structural). Outline/stroke and effect colors keep their own color/opacity model, untouched.
- **Pattern persistence:** embed the tile image bytes in the .mas project (consistent with .mas carrying page pixels; robust to the source file moving/being deleted) with a generous size cap (~4 MB) and a clear warning dialog on oversized tiles. Keep the renderer's decoded tile cached per box like other render assets.
- **Pattern opacity:** the tile is drawn with the opacity of Color A's alpha, so the existing transparency slider remains the single opacity control for every fill type.
- **UI:** inspector Fill row grows a type selector (Solid | Gradient | Pattern); Gradient reveals Color B + angle; Pattern reveals file picker + scale; the color swatch previews the actual fill (gradient ramp / tiled pattern over checkerboard).

</decisions>

<specifics>
## Specific Ideas

- Manga use cases driving this: metallic two-tone text (linear diagonal), white→transparent fade-outs, and authentic licensed screentone tiles (image patterns) rather than synthetic halftone.
- Implementation is expected to ride the existing single QBrush fill path (text_renderer.py horizontal/vertical branches shared by canvas overlay and bake/export): gradients are native QBrush citizens; patterns are tiled texture brushes.

</specifics>

<canonical_refs>
## Canonical References

- Prior quick 260909-nj9 (color picker alpha): #AARRGGBB hex storage, alpha-aware WR-01 guard, checkerboard swatch convention — the fill framework builds directly on it.
- No external specs — requirements fully captured in decisions above.

</canonical_refs>

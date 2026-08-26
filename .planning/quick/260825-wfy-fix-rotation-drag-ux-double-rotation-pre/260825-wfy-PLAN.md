---
phase: quick-260825-wfy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/inspector_panel.py
  - tests/test_gui_sfx_editing.py
autonomous: true
requirements: [QUICK-WFY]
estimate:
  tokens: 45000
  raw_tokens: 30000
  tasks: 2
  confidence: med
must_haves:
  truths:
    - Dragging the rotation handle on an ALREADY-ROTATED box previews the DELTA between mouse angle and the baked committed angle — text tracks the mouse during drag and release causes NO visible snap.
    - During a rotation drag on any box, the text never gets clipped along straight edges (boundingRect covers rotated extents).
    - Inspector font-size spinbox accepts values up to 1024 (model max); 0 remains the Auto sentinel.
  artifacts:
    - manga_ai_studio/gui/box_item.py (TypesetOverlayItem.baked_rotation + delta preview_rotation + rotation-aware boundingRect)
    - manga_ai_studio/gui/inspector_panel.py (size_spin range 0..1024)
    - tests/test_gui_sfx_editing.py (delta-preview, from-zero parity, boundingRect containment, spinbox range tests)
  key_links:
    - set_content/_render_rotated bake angle -> baked_rotation attribute -> preview_rotation applies (live - baked) delta about box-center pivot
    - preview_rotation/clear_preview_rotation call prepareGeometryChange() BEFORE changing rotation so Qt repaints the enlarged boundingRect
---

<objective>
Fix three rotate-feature UX defects from quick-260824-viq / 260825-uzv:

1. **Double rotation during drag** — `TypesetOverlayItem.preview_rotation` (manga_ai_studio/gui/box_item.py:1268) sets `overlay.setRotation(live)` as an ABSOLUTE item transform, but when the box already carries a committed rotation that angle is BAKED INTO the cached pixmap by `_render_rotated` (via `set_content`). Visual result = start_angle + live (text lags/doubles during drag), then `_commit_rotation` re-renders at live only → visible snap on release. Fix: track the angle baked into the current pixmap and apply the DELTA.
2. **Straight-edge clipping during drag** — `TypesetOverlayItem.boundingRect` (:534) returns the UNROTATED pixmap rect; Qt culls repaints to it, so preview-rotated extents outside are chopped. Fix: make boundingRect rotation-aware via QTransform mapping of the base rect.
3. **Font-size cap** — `inspector_panel.py:484` `self.size_spin.setRange(0, 200)` while the model clamp allows font_size_px 1..1024 (core/text_style.py). Raise to 0..1024 (0 stays Auto sentinel).

Purpose: rotation drag must visually track the mouse without snapping or clipping on every drag (not just the first from 0 deg).
Output: Patched box_item.py + inspector_panel.py, extended tests, full suite green under pinned interpreter.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@manga_ai_studio/gui/box_item.py
@manga_ai_studio/gui/inspector_panel.py
@tests/test_gui_sfx_editing.py

Key sites (verified):
- box_item.py:534 `TypesetOverlayItem.boundingRect` — returns `QRectF(QPointF(0,0), QSizeF(pixmap.size()))`, unrotated.
- box_item.py:569 `set_content` — empty-text path at :584 resets `_pixmap/_layout_result/_ink_offset/_render_offset` (baked_rotation must reset here too).
- box_item.py:597-600 — `angle = _normalize_rotation(getattr(style, "rotation_deg", 0.0))`; non-zero routes to `_render_rotated`.
- box_item.py:635 `_render_rotated(result, style, box_rect, angle_deg, pad)` — bakes the angle into the pixmap; this is where baked_rotation is SET.
- box_item.py:1268 `preview_rotation(angle_deg)` — sets transform origin at box center (overlay-local) then `setRotation(angle_deg)` ABSOLUTE.
- box_item.py:1286 `clear_preview_rotation` — resets rotation 0 + origin (0,0). Keep semantics: after clear, the pixmap's own baked rotation shows through.
- inspector_panel.py:35, :63, :479 — docstring/comment references say "0..200"; :484 is the actual `setRange(0, 200)`.

Interpreter (AGENTS.md, pinned): `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Delta-based rotation preview + rotation-aware boundingRect in TypesetOverlayItem</name>
  <files>manga_ai_studio/gui/box_item.py, tests/test_gui_sfx_editing.py</files>
  <behavior>
    - Delta preview: set_content with a TextStyle carrying rotation_deg=30 (pixmap baked at 30 deg) → preview_rotation(50) → overlay.rotation() == 20.0 (delta = live − baked), transform origin still box-center-relative.
    - From-zero parity: box style at rotation_deg=0 → preview_rotation(30) → overlay.rotation() == 30.0 (unchanged legacy behavior when nothing is baked).
    - Clear parity: after clear_preview_rotation, overlay.rotation() == 0.0 regardless of prior state.
    - Placement spot-check (D-01): bake at 30 deg, preview_rotation(50), clear_preview_rotation, then set_content at rotation_deg=50 → the item's scene placement (pos + effective rotation) matches a DIRECT render at 50 deg within float epsilon (geometry comparison, not pixels).
    - Empty-text reset: set_content("") after a baked render → baked_rotation == 0.0.
    - boundingRect identity: set_content at rotation 0 → boundingRect equals the pixmap rect.
    - boundingRect containment: preview_rotation(45) → boundingRect area strictly larger than the base pixmap rect and contains all four rotated corners of the base rect (map base corners through the same rotation-about-origin and assert containment).
    - prepareGeometryChange exercised without Qt warnings during both preview_rotation and clear_preview_rotation.
    Write these tests FIRST in tests/test_gui_sfx_editing.py (extend existing rotation test class; follow its fixture/style-construction patterns), confirm they fail against current code (RED), then implement.
  </behavior>
  <action>
  In TypesetOverlayItem (manga_ai_studio/gui/box_item.py):

  1. Add instance attribute `self._baked_rotation: float = 0.0` next to `_render_offset` (~line 531), documented as "the rotation_deg currently baked INTO the cached pixmap".
  2. In `set_content`: reset `self._baked_rotation = 0.0` in the empty-text path (alongside the existing `_render_offset = None` reset at ~line 588). In the rotated branch (~line 598-600), after `_render_rotated(...)` succeeds, set `self._baked_rotation = angle`. Leave the unrotated path setting it to 0.0 (it was reset before layout — ensure it stays 0 on the straight-through path too).
  3. Rewrite `preview_rotation` to apply the DELTA: compute `delta = _normalize_rotation(angle_deg - self._baked_rotation)`, call `prepareGeometryChange()` FIRST (boundingRect depends on rotation), keep the existing box-center transform-origin computation verbatim, then `setRotation(delta)`. Do NOT change the pivot math or the no-re-layout discipline.
  4. Rewrite `clear_preview_rotation` to call `prepareGeometryChange()` before resetting rotation to 0 and origin to (0,0) — semantics otherwise unchanged (the pixmap's baked rotation shows through untouched).
  5. Make `boundingRect` rotation-aware: when `abs(self.rotation()) <= 1e-6` return the existing base rect unchanged (byte-identical legacy path at rotation 0); otherwise map the base pixmap rect through `QTransform().translate(origin.x(), origin.y()).rotate(self.rotation()).translate(-origin.x(), -origin.y())` (origin = the current transform origin point) and return `transform.mapRect(base_rect)` normalized as QRectF.
  6. Do NOT touch the canvas `_advance_rotation` / `_commit_rotation` math — with delta preview, their mouse-derived live-angle contract becomes correct as-is.

  Anti-pattern guard: do NOT introduce any "apply absolute angle" fallback, feature flag, or v1 shortcut — the delta path IS the fix.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py -x -q</automated>
  </verify>
  <done>All new behavior tests pass (RED→GREEN confirmed); existing sfx-editing suite passes unmodified except additive test growth; overlay.rotation() equals (live − baked) during preview, boundingRect contains rotated extents, empty-text and clear paths reset baked_rotation.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Raise Inspector font-size spinbox cap to model max 1024</name>
  <files>manga_ai_studio/gui/inspector_panel.py, tests/test_gui_sfx_editing.py</files>
  <behavior>
    - InspectorPanel builds size_spin with minimum == 0 and maximum == 1024 (test asserts both ends).
    - 0 retains the "Auto" special value text and sentinel semantics (existing tests cover; must stay green).
    - A style with font_size_px=800 loads into the spinbox showing 800 (round-trip through the existing load path, no clamp truncation).
  </behavior>
  <action>
  In manga_ai_studio/gui/inspector_panel.py:
  1. Line ~484: change `self.size_spin.setRange(0, 200)` to `setRange(0, 1024)` — matching the model bounds in core/text_style.py (font_size_px clamped 1..1024; 0 = Auto sentinel per D-15, unchanged).
  2. Update the three stale references to the old cap: class docstring ~line 35 ("0..200 ``QSpinBox``"), module/section comment ~line 63 ("size 0..200"), and inline comment ~line 479 ("0..200 with 'Auto' at 0") — all become 0..1024 phrasing.
  3. Grep gui/ for any other assumption of font-size max 200 near size/font handling (e.g., validators, clamps, tests asserting the old max) and update if found — report findings in the summary either way. Known-safe: lines 819-969, 1142-1153 (load/display paths read model values, no local clamp), 1493 (value() read).

  Add the spinbox-range + 800-round-trip tests to tests/test_gui_sfx_editing.py (or the existing inspector panel test module if the sfx file has no InspectorPanel fixture — reuse whichever fixture pattern the neighboring tests use).
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py -q && & "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q</automated>
  </verify>
  <done>size_spin range is 0..1024 with Auto sentinel intact; stale "0..200" references updated; full suite green under the pinned interpreter (baseline 1138 passed + new tests).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| none new | UI-only geometry/rendering changes; no new inputs, network, persistence, or privilege surfaces |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-WFY-01 | Tampering | size_spin upper bound raised 200→1024 | low | accept | Value still flows through core/text_style.py from_dict clamp (1..1024) on commit; GUI cannot inject out-of-model values |
| T-WFY-02 | Denial of Service | boundingRect QTransform mapping on every paint cull | low | accept | Single 4-point rect map per geometry query; negligible vs existing per-mousemove discipline |
</threat_model>

<verification>
- `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py -q` green.
- Full suite `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` green (≥1138 passed baseline + additions).
- Grep confirms no remaining `setRange(0, 200)` on size_spin and no "0..200" size-cap prose in inspector_panel.py.
</verification>

<success_criteria>
1. Rotation drag on an already-rotated box tracks the mouse with no double-rotation and no snap on release (delta = live − baked).
2. No straight-edge text clipping during any rotation drag (rotation-aware boundingRect + prepareGeometryChange before every rotation mutation).
3. Inspector accepts font sizes up to 1024; Auto (0) sentinel untouched.
4. All behavior covered by automated tests using the pinned interpreter.
</success_criteria>

<output>
Create `.planning/quick/260825-wfy-fix-rotation-drag-ux-double-rotation-pre/260825-wfy-SUMMARY.md` when done
</output>

---
phase: quick-260824-viq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/text_style.py
  - manga_ai_studio/gui/text_renderer.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/main_window.py
  - tests/test_core/test_text_style.py
  - tests/test_core/test_text_renderer.py
  - tests/test_gui_sfx_editing.py
autonomous: true
requirements: []
user_setup: []

estimate:
  tokens: 84000
  raw_tokens: 42000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - Dragging a rotation grab handle (positioned above a corner of a selected box) rotates that box's text live on canvas; releasing commits the angle, and one Ctrl+Z reverses it.
    - A rotation angle set on a box survives project save/load (.mas round-trip) and is honored identically by the canvas overlay AND the export bake (canvas ≡ bake, D-01).
    - Two Inspector styling rows ("Spacing H", "Spacing V") adjust horizontal character separation and vertical line/column separation on canvas and in the bake, per selected box, undoable in one Ctrl+Z.
    - Ctrl+C copies selected boxes (text + full style incl. rotation/spacing); Ctrl+V pastes detached clones offset down-right, origin USER, bubble number cleared, selectable and editable; one Ctrl+Z removes the paste.
  artifacts:
    - manga_ai_studio/core/text_style.py with rotation_deg + char_spacing_px + line_spacing_px fields, serialized and V5-clamped
    - manga_ai_studio/gui/text_renderer.py paint()/layout()/bake honoring rotation + both spacings
    - RotationHandle class + canvas rotate drag state machine in gui/box_item.py + gui/canvas.py
    - tests/test_gui_sfx_editing.py covering rotation commit/undo, copy/paste, and persistence round-trip
  key_links:
    - TextStyle.to_dict/from_dict <-> project_io._pagebox_from_dict + ocr_export style block (persistence of the three new fields rides the existing D-07 single spelling)
    - renderer paint() rotation <-> TypesetOverlayItem cached pixmap <-> bake_typeset_page (ONE code path)
    - canvas boxes_modified(before-snapshot) emissions <-> history.push_boxes_state (CR-01 pre-mutation push contract for rotate + paste)

---

<objective>
Three SFX-editing features for the typeset canvas: (1) free-angle text rotation via a corner grab handle with persistence and export parity, (2) horizontal character-separation and vertical line-separation style controls in the Inspector, (3) Ctrl+C/Ctrl+V duplication of text boxes for repeated SFX/decorative elements.

Purpose: SFX typesetting needs angled, spread-out, repeated text; today every overlay is axis-aligned, tightly spaced, and hand-recreated one box at a time.
Output: Working rotation handle + spacing controls + box copy/paste, persisted through the existing TextStyle/.mas pipeline and undoable through the existing BOXES stack.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@AGENTS.md
@manga_ai_studio/core/text_style.py
@manga_ai_studio/gui/text_renderer.py
@manga_ai_studio/gui/box_item.py
@manga_ai_studio/gui/canvas.py
@manga_ai_studio/gui/inspector_panel.py
@manga_ai_studio/core/project_io.py

Key architecture facts (verified by read):
- TextStyle (core/text_style.py) is the flat per-box style; to_dict/from_dict is the SINGLE serialization spelling consumed verbatim by project_io.py:252/316 (load/save) and ocr_export.py:190 — new fields persist with ZERO project_io changes if added to both methods with V5 clamps.
- text_renderer.layout() returns LayoutResult(origin, inner_size, ink, ...); paint() translates to origin then draws. bake_typeset_page() calls layout()+paint() per box — any change inside paint() reaches canvas AND export atomically (D-01).
- TypesetOverlayItem.set_content renders the layout into a cached QPixmap sized to ink+effect_padding; refresh_position is setPos-ONLY (RC-1 — never re-layout per mousemove).
- Canvas box-interaction state machine: mousePressEvent dispatches via _box_item_at (matches CornerHandle/BoxItem only; RedetectHandle deliberately excluded — visual-only), arms _begin_resize/_select_and_begin_move capturing `self._boxes_interaction_start_snapshot`; mouseReleaseEvent calls _commit_resize which emits `boxes_modified(before)` ONCE (CR-01 pre-mutation push). Mirror this shape for rotation.
- BoxItem children: 4 CornerHandles (z=150, visible iff selected&&primary via _sync_handles/_sync_handles_for_state), TypesetOverlayItem (z=120), badge (z=140), RedetectHandle (z=160, self-clicking).
- Inspector styling section builds form rows (Font/Style/Size+Auto-fit/Color/Align/effects); commits flow through connect_commit_handlers callbacks -> MainWindow._inspector_style_commit(apply_fn) -> _replace_style(pb, **changes) -> dataclasses.replace + refresh + ONE boxes_modified(before) push. size_spin uses an editingFinished debounce pattern with _loaded_style_size memory.
- PageBox.copy() detaches payload/style/mask (Pitfall 8); the vendored Box is @frozen and safely shared. boxes_snapshot() materializes fresh int-Box PageBoxes carrying style.
- Interpreter (AGENTS.md): C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe -m pytest
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Style model + renderer — rotation_deg, char_spacing_px, line_spacing_px</name>
  <files>manga_ai_studio/core/text_style.py, manga_ai_studio/gui/text_renderer.py, tests/test_core/test_text_style.py, tests/test_core/test_text_renderer.py</files>
  <behavior>
    - TextStyle(rotation_deg=37.5).to_dict() contains "rotation_deg": 37.5; from_dict round-trips all three new fields; missing/legacy dict yields 0.0 defaults (Pitfall 8 backward compat).
    - V5 clamps: from_dict({"rotation_deg": 999}) -> 180.0; {"rotation_deg": "x"} -> 0.0; char_spacing_px clamped into 0..64; line_spacing_px clamped into 0..256; non-numeric falls back to default, never raises.
    - layout() stores box_center == box_rect.center() on every LayoutResult (horizontal, vertical, and empty-text paths).
    - paint() with rotation_deg != 0 draws glyphs rotated about result.box_center: rasterize the SAME LayoutResult twice (rotated vs 0) onto distinct surfaces and assert the pixel arrays differ AND the rotated ink lies within the rotated bounding quad of the unrotated ink.
    - Letter spacing: QFontMetricsF horizontalAdvance of a probe string measured via the module font path grows monotonically as char_spacing_px increases (0 vs 8), and _build_document width reflects it (measurement and rendering share _style_font).
    - Line spacing: layout(...).document size height with line_spacing_px=20 exceeds the 0-spacing height by approximately 20 px per extra line (multi-line probe text; tolerance +-2px for rounding).
    - Vertical placements: column pitch grows by char_spacing_px between adjacent columns; per-char y advance grows by line_spacing_px.
    - bake_typeset_page() on a synthetic page with one rotated styled box composites pixels OUTSIDE the axis-aligned box rect but inside the rotated quad (export honors rotation).
  </behavior>
  <action>
    In core/text_style.py: add three dataclass fields — rotation_deg: float = 0.0, char_spacing_px: float = 0.0, line_spacing_px: float = 0.0 — plus module constants for the V5 bounds (ROTATION half-range 180.0; char spacing max 64.0; line spacing max 256.0). Extend to_dict with the three keys (plain floats) and from_dict with _clamp_float coercions mirroring the existing effect-field discipline (bool rejected, non-numeric -> default, out-of-range clamped). Do NOT touch project_io.py or ocr_export.py — they consume to_dict/from_dict verbatim (D-07).

    In gui/text_renderer.py:
    (a) Add `box_center: QPointF` to LayoutResult (default QPointF()); set it to box_rect.center() in ALL THREE construction sites in layout() (empty-text early return, horizontal return) and _layout_vertical_result.
    (b) In paint(): after the existing painter.save(), when abs(style.rotation_deg normalized into (-180, 180]) exceeds an epsilon (1e-6), translate to result.box_center, painter.rotate(float(style.rotation_deg)) (Qt positive = clockwise; define style rotation as degrees clockwise and document it on the field), translate back by -box_center, THEN run the existing effects+fill passes untouched. This keeps ONE draw path for canvas and bake (D-01) — do NOT add a separate rotated-paint function.
    (c) In _style_font(): when style.char_spacing_px > 0, apply QFont.setLetterSpacing(QFont.LetterSpacingType.AbsoluteSpacing, float(style.char_spacing_px)). Because _break_lines_for measures with _style_font and _build_document formats with _style_font, measurement and render stay consistent automatically — verify no other QFont construction bypasses _style_font.
    (d) Line spacing: in _build_document, after building the document, when style.line_spacing_px > 0 apply a QTextBlockFormat top margin equal to line_spacing_px to every block EXCEPT the document's first (iterate blocks via a QTextCursor or the block iterator; merge, never replace, any existing block format). Doc height then includes the gaps so the overflow check and auto-fit loop account for them with zero extra logic.
    (e) Vertical placements in _vertical_placements: add char_spacing_px to the inter-column pitch (column gap) and line_spacing_px to the per-char advance along the column (y += h + line_spacing_px), including in the wrap predicate so columns break honestly. Keep gap 0 when the fields are 0 (byte-identical legacy geometry).
    Write behavior tests FIRST in tests/test_core/ (extend the existing test files if present — check tests/test_core/ for test_text_style.py / test_text_renderer.py names before creating new ones) and follow RED->GREEN. Use the pinned interpreter from AGENTS.md.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_text_style.py tests/test_core/test_text_renderer.py -q</automated>
  </verify>
  <done>All new style/renderer behavior tests pass; the FULL existing core suite still passes (no legacy geometry drift when all three fields are 0).</done>
</task>

<task type="auto">
  <name>Task 2: RotationHandle + canvas rotate drag + rotated overlay rendering</name>
  <files>manga_ai_studio/gui/box_item.py, manga_ai_studio/gui/canvas.py, tests/test_gui_sfx_editing.py</files>
  <action>
    In gui/box_item.py:
    (a) New class RotationHandle(QGraphicsEllipseItem) modeled on RedetectHandle: ItemIgnoresTransformations, ~10x10 viewport px circle, z=155 (above CornerHandles, below nothing critical), origin-hue fill + 1px #0b0b0e outline, SizeAllCursor (or CrossCursor — pick the clearer affordance), tooltip "Rotate text". Positioned ABOVE the TOP-LEFT corner: reposition(parent_rect) places its center at (parent_rect.left(), parent_rect.top() - 18) — clearly separated from the TL CornerHandle's 9px-radius hit zone (quick-260824-t64 zoom-divided hit math precedent). Hidden by default.
    (b) BoxItem integrates the handle into the EXISTING visibility machinery: create it in __init__, show/hide + reposition inside _sync_handles AND _sync_handles_for_state (same selected&&primary rule as corner handles), and include it in set_edit_mode's acceptance stripping. Do NOT add it to the canvas _box_item_at match set — like RedetectHandle, it owns its own press.
    (c) RotationHandle.mousePressEvent: left-press accepts the event and invokes activate_callback(item, scene_pos) — installed by the canvas.
    (d) TypesetOverlayItem gains rotated-content support: in set_content, when abs(normalized rotation) > epsilon, size the surface to the ROTATED padded-ink bounds (map the padded ink QRectF through QTransform().rotate(angle) around box center and take the bounding rect), render through the UNCHANGED renderer_paint (which now rotates — Task 1), and store a `_render_offset` = (surface top-left minus box_rect top-left) used by refresh_position instead of the unrotated ink_offset when rotation is active. When rotation is 0 the existing code path must be byte-identical (guard with an early branch, do not refactor the unrotated math). refresh_position stays setPos-ONLY: pos = box_rect.topLeft() + active offset (RC-1 preserved).
    (e) BoxItem.preview_rotation(angle_deg): LIVE-drag-only lightweight path — setTransformOriginPoint to (box_center minus current overlay pos) in overlay-local coords, then _text_overlay.setRotation(angle_deg) and update(). NO re-layout, NO re-render (per-mousemove discipline). BoxItem.clear_preview_rotation(): setRotation(0), reset origin point; the caller follows with refresh_text_overlay() to bake the committed angle into the pixmap.

    In gui/canvas.py:
    (f) New state fields mirroring the resize trio: _rotating_box, _rotate_start_angle_deg, __rotate_grab_angle_rad, plus reuse of _boxes_interaction_start_snapshot. In RotationHandle's activate_callback closure: arm via a _begin_rotation(item, scene_pos) that selects the item if needed, captures boxes_snapshot() BEFORE mutation, records the current style rotation (style if not None else TextStyle(); treat None style as 0.0), records atan2 of (scene_pos - item.rect().center()), and viewport().grabMouse().
    (g) mouseMoveEvent: while _rotating_box is armed, compute delta = atan2(cursor - center) - grab angle in DEGREES, live = normalize(start_angle + delta) into (-180, 180], snap-free (hold no modifier requirements), call item.preview_rotation(live), and stash the latest angle. mouseReleaseEvent: _commit_rotation() — clear_preview_rotation(), assign item.pagebox.style = dataclasses.replace(existing-or-default, rotation_deg=live) ONLY when the angle changed beyond 0.05 deg, item.refresh_text_overlay(), set_pending_boxes_op_name("rotate"), emit boxes_modified(self._boxes_interaction_start_snapshot) ONCE, clear state. Angle math must derive from item.rect().center() LIVE each move (a moved box mid-drag is impossible here since move is not armed, but stay defensive).
    (h) The rotate drag must coexist with edit-mode guard (no rotation while the inline editor is open) and with the multi-select primary rule (handle only appears/ships on the primary selected box — inherited from (b)).

    Tests in tests/test_gui_sfx_editing.py (pytest-qt qapp fixture, mirror test_gui_boxes.py setup helpers — read that file first for the canvas/page fixture pattern): simulate the drag programmatically by invoking the canvas _begin_rotation/_advance/_commit seam directly (the QTest mouse-path truncation lesson, 05-09) — assert style.rotation_deg lands within tolerance, overlay pixmap differs pre/post, boxes_modified emitted once with the PRE-rotation snapshot, and history undo (HistoryManager + push via the real boxes_modified slot or the canvas-level seam used by existing undo tests) restores the prior angle. Also unit-test RotationHandle placement (outside TL, clear of the TL handle hit rect) and preview_rotation being a pure transform (layout_result unchanged).
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py tests/test_gui_boxes.py -q</automated>
  </verify>
  <done>Dragging the rotation handle commits a persisted per-box angle with one-shot undo; zero-rotation boxes render byte-identically to before (existing test_gui_boxes suite green).</done>
</task>

<task type="auto">
  <name>Task 3: Inspector spacing rows + copy/paste of text boxes</name>
  <files>manga_ai_studio/gui/inspector_panel.py, manga_ai_studio/gui/main_window.py, manga_ai_studio/gui/canvas.py, tests/test_gui_sfx_editing.py</files>
  <action>
    Inspector spacing (mirror the Size-row mechanics exactly):
    (a) Two QSpinBox rows after the Size row: "Spacing H" (char separation, range 0..64, suffix " px") and "Spacing V" (line/column separation, range 0..256, suffix " px"), tooltips explaining horizontal character gap / vertical line gap respectively.
    (b) Load in _load_style_section / load_box / load_multi_selection from the box's effective style (TextStyle() defaults when style is None): store _loaded_char_spacing/_loaded_line_spacing memory ints. Multi-selection: NO tri-state for these two spins (deliberate simplification — load the PRIMARY box's values; document the deviation in a comment referencing the align/effect mixed-sentinel machinery as the future upgrade path). clear() resets to 0.
    (c) connect_commit_handlers gains on_style_char_spacing/on_style_line_spacing params wired via the editingFinished emit-if-changed pattern (_emit_style_size_if_changed is the template — WR-01 no-op-on-unchanged discipline).

    MainWindow:
    (d) _on_inspector_char_spacing_committed(value:int) / _on_inspector_line_spacing_committed(value:int) -> _inspector_style_commit(lambda item: self._replace_style(item.pagebox, char_spacing_px=float(value))) and the line analog. Route the new callbacks through the EXISTING connect_commit_handlers call site (~main_window.py:3441). _replace_style already refreshes overlays + pushes ONE before-snapshot — no new undo plumbing.
    (e) Canvas keyPressEvent (extend the existing override): Ctrl+C copies, Ctrl+V pastes, guarded to do nothing while the inline editor is active (canvas.is_editing or the InlineEditor proxy seam — check how the edit-mode guard gates other interactions). Copy collects the selected items' pagebox.copy() detached clones into a NEW public attribute canvas.box_clipboard (list[PageBox], replaces prior contents). Paste: for each stored pb take ANOTHER pb.copy() (repeated pastes never alias — Pitfall 8 applied twice), translate the frozen Box by rebuilding via panelcleaner.structures.Box(x1+dx, y1+dx...) with dx=dy=16 accumulated per successive paste-in-a-row is OPTIONAL — ship the simple constant 16px offset first; clamp the pasted rect inside the current sceneRect; set origin=USER (core.box_model.USER), bubble_no=None, manual_override=False, mask=None, std_dev=None, fill_color=None, inpaint_override=None, edited=True on the clone (fresh box semantics; text + full style INCLUDING rotation/spacings ride the copy — that is the feature). Insert through the SAME BoxItem-construction path _commit_create uses (find the exact helper; if none exists extract one — do not fork construction logic), select the pasted items, capture the before-snapshot BEFORE inserting, then emit boxes_modified(before) ONCE so one Ctrl+Z removes the paste (CR-01). Show a transient status via the existing canvas/MainWindow transient-status mechanism ("Pasted N box(es)"). Empty clipboard paste is a silent no-op; copy with empty selection likewise.
    (f) Deliberate deferral (note in the Summary, do NOT build here): Edit-menu Copy/Paste actions, paste-at-cursor positioning, cross-page clipboard, and a numeric Inspector rotation field. Handle-drag rotation, offsets, and canvas-scoped shortcuts cover the stated workflow.

    Extend tests/test_gui_sfx_editing.py: copy with a styled+rotated selected box -> clipboard clone carries text/style/rotation; paste inserts a USER-origin box offset +16/+16 with bubble_no None and independent payload (mutating the original's text after paste leaves the clone untouched — Pitfall 8 assertion); one undo pops the paste; Inspector spacing commit routes through _replace_style (spy/assert style field + refresh called) and an unchanged-value commit is a no-op; .mas round-trip via the existing project_io save/load test helpers asserts rotation_deg/char_spacing_px/line_spacing_px survive.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py tests/test_gui_inspector_styling.py tests/test_box_persistence.py -q</automated>
  </verify>
  <done>Spacing spins restyle canvas+bake per box with one-shot undo; Ctrl+C/Ctrl+V duplicates styled boxes as independent USER-origin clones with one-shot undo; all three new fields survive a save/load round-trip.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| .mas file -> TextStyle.from_dict | Crafted project/style dicts reach the app on load |
| Clipboard (in-process) | Pasted PageBoxes re-enter the model pipeline |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-VIQ-01 | Tampering | TextStyle.from_dict new fields | medium | mitigate | V5 clamps on all three fields (rotation +-180, spacing 0..64/0..256); bool rejected; non-numeric falls back to defaults, never raises |
| T-VIQ-02 | Information Disclosure | box_clipboard holding payloads | low | accept | In-process Python attribute only (not the OS clipboard) — no cross-app leakage surface; dies with the process |
| T-VIQ-03 | Elevation/Injection | pasted/cloned payload text into renderer | low | mitigate | Existing ASVS V5 plain-text-only rendering (setPlainText, no rich text) is inherited unchanged by cloned boxes |
| T-VIQ-SC | Tampering | npm/pip installs | n/a | accept | No new packages in this plan — stdlib/PySide6/numpy only |
</threat_model>

<verification>
- Full suite green under the pinned interpreter (baseline 552 passed at Phase 5 close; expect strict superset):
  & "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q
- Zero-rotation / zero-spacing regression: every pre-existing renderer, overlay, and bake test passes UNMODIFIED (byte-compat guard on the new fields' defaults).
- Manual smoke (deferred to human verification per end-of-phase convention): rotate an SFX box ~30 deg, save, reload — angle intact; bake/export shows the same angle; paste three hearts from one copied box.
</verification>

<success_criteria>
- Rotation: handle drag commits a persisted per-box angle (canvas ≡ bake, D-01), one Ctrl+Z reverses, .mas round-trip preserves it.
- Spacing: Spacing H/V Inspector rows drive character/line separation through the SHARED renderer (measurement == render), one-shot undo, persisted.
- Copy/paste: Ctrl+C/Ctrl+V on the canvas duplicates styled boxes as detached USER-origin clones at a 16px offset, bubble numbers cleared, one-shot undo.
- All three features ride the EXISTING pipelines (TextStyle serialization, boxes_modified/history, _replace_style) with no parallel mechanisms added.
</success_criteria>

<output>
Create `.planning/quick/260824-viq-sfx-editing-features-rotate-text-at-an-a/260824-viq-SUMMARY.md` when done
</output>

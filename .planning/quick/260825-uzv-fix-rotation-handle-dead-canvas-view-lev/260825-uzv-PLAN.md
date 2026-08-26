---
phase: quick-260825-uzv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/gui/canvas.py
  - tests/test_gui_sfx_editing.py
autonomous: true
requirements: [QUICK-260825-UZV]
user_setup: []

estimate:
  tokens: 60000
  raw_tokens: 30000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - Pressing (and dragging) on a VISIBLE RotationHandle arms a rotate drag (_rotating_box set) instead of clearing selection
    - A committed handle drag writes style.rotation_deg on the parent PageBox and fires ONE boxes_modified emission
    - Clicking genuinely empty canvas still clears the selection (existing §12d behavior preserved)
    - Alt+drag rotates under an active paint tool, consistent with the existing Alt+resize carve-out (D-15)
    - No-Alt presses over handles under paint tools still paint (MASK-06 consistency preserved)
    - Rotation stays inert while the inline editor is active (_begin_rotation guard untouched)
  artifacts:
    - manga_ai_studio/gui/canvas.py (RotationHandle-aware press dispatch)
    - tests/test_gui_sfx_editing.py (dispatch-path regression tests)
  key_links:
    - EditorCanvas.mousePressEvent non-paint branch -> _begin_rotation (before any _clear_selection)
    - _topmost_box_hit identity-transform scene query -> {CornerHandle, BoxItem, RotationHandle}
---

<objective>
Fix the dead rotation handle: a view-level press on the visible RotationHandle currently falls into the empty-canvas path, calls `_clear_selection()` (canvas.py:1419), hides the handle (visibility tied to selected+primary via `_sync_handles_visibility`), and the later `super().mousePressEvent(event)` fall-through skips the now-invisible handle — so `_begin_rotation` never fires and clicking the circle deselects the box.

Purpose: restore the advertised SFX free-angle rotation affordance (quick-260824-viq) end-to-end through the real view-level press dispatch.
Output: A canvas whose press dispatch recognizes RotationHandle explicitly BEFORE selection-clear, mirrored in the Alt-gated paint branch, plus dispatch-path regression tests.
</objective>

<execution_context>
@C:/Users/Stella/.config/opencode/gsd-core/workflows/execute-plan.md
@C:/Users/Stella/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@manga_ai_studio/gui/canvas.py
@manga_ai_studio/gui/box_item.py
@tests/test_gui_sfx_editing.py

Key facts (code-confirmed):
- `EditorCanvas.mousePressEvent` box branch starts at canvas.py:1352; `_box_item_at(scene_pos)` at :1372 matches ONLY CornerHandle/BoxItem (helper defined at :2490-2518, identity-transform `items()` query, visible+enabled filter). Its OTHER caller is `mouseDoubleClickEvent` (:1465) — do not change its contract.
- Non-paint branch: CornerHandle -> `_begin_resize`; BoxItem -> shift-toggle/move; else `_clear_selection()` at :1419, then fall-through. Paint tools with mask + non-MOVE/CROP accept via `_begin_paint` at :1436-1444, so the fall-through may never happen at all.
- Alt-gated paint sub-branch (:1374-1390) special-cases CornerHandle -> `_begin_resize` and BoxItem -> `_select_and_begin_move`.
- RotationHandle (box_item.py:255-312): ItemIgnoresTransformations child, own `mousePressEvent` invoking `activate_callback(parent_item, scene_pos)`; installed by `_install_rotation_hook` (canvas.py:2263-2279) -> `_begin_rotation` (canvas.py:2645). `_begin_rotation` selects-if-needed, captures CR-01 snapshot, sets `_rotating_box`, grabs viewport, guards on `_inline_editor.is_active()`.
- RedetectHandle survives the fall-through only because its visibility is geometry-stale driven, NOT selection driven — that asymmetry is why this bug is unique to RotationHandle.
- Existing rotate tests exercise the state-machine SEAM (`_begin_rotation`/`_advance_rotation`/`_commit_rotation`) per the 05-09 QTest-truncation lesson. Fixtures available in tests/test_gui_sfx_editing.py: `_canvas_with_image(qtbot)`, `_seed_box(canvas, box, **pb_kwargs)`, `_solid_pixmap`, plus qtbot + @pytest.mark.gui discipline (mirror tests/test_gui_boxes.py header).
- Phase 01-04 lesson: QGraphicsView.mapToScene takes QPoint not QPointF; tests use `mapFromScene` for viewport coords landing at the desired scene pixel.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Dispatch-path regression tests (RED)</name>
  <files>tests/test_gui_sfx_editing.py</files>
  <behavior>
    - Test 1 (the defect): shown canvas with an image, one seeded user box, box selected + `canvas._primary_box = item` + `canvas._sync_handles_visibility()` so the RotationHandle is VISIBLE. Compute the handle-center scene pos via `rh = item._rotation_handle; scene_pos = rh.mapToScene(rh.boundingRect().center())`. Synthesize a left-button press at `QPointF(canvas.mapFromScene(scene_pos))` (QMouseEvent MouseButtonPress, Qt.LeftButton pressed, NoModifier) and call `canvas.mousePressEvent(ev)` directly. Expect: `canvas._rotating_box is item`, `item.isSelected()` still True (no selection-clear), handle still visible. Then `canvas._advance_rotation(<moved pos>)` + `canvas._commit_rotation()` and expect `item.pagebox.style.rotation_deg != 0.0` (create the PageBox with a TextStyle so the field exists, or rely on the None->TextStyle fallback in _begin_rotation).
    - Test 2 (regression guard): same setup, press synthesized at a genuinely EMPTY scene spot (far from box/handles/badges) — expect selection cleared, `_rotating_box is None`. This passes today and must keep passing.
    - Test 3 (Alt parity): active tool set to BRUSH (use whatever setter existing brush tests use to drive `current_tool`), press with AltModifier on the visible handle — expect rotation armed (`_rotating_box is item`).
  </behavior>
  <action>
    Append a new "Canvas dispatch — RotationHandle press" section to tests/test_gui_sfx_editing.py following the file's fixture/header conventions (@pytest.mark.gui, qtbot, importorskip PySide6). Reuse `_canvas_with_image` + `_seed_box`. Follow the 05-09 seam lesson where possible, but these tests MUST go through the REAL `canvas.mousePressEvent` entry point (that entry point IS the defect site) — synthesize QMouseEvent rather than calling `_begin_rotation` directly. Anchor assertions on delivered state (`_rotating_box`, isSelected, committed rotation_deg), not pixel output. Do not weaken Test 2: it pins the §12d empty-canvas-clear contract.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py -q</automated>
  </verify>
  <done>New dispatch tests are collected; Test 1 and Test 3 FAIL (press clears selection / rotation never arms — the reported symptom reproduced), Test 2 PASSES. Pre-existing tests in the file still pass.</done>
</task>

<task type="auto">
  <name>Task 2: Recognize RotationHandle in the view-level press dispatch (GREEN)</name>
  <files>manga_ai_studio/gui/canvas.py</files>
  <action>
    1. Add a canvas helper next to `_box_item_at` (~line 2490), e.g. `_topmost_box_hit(self, scene_pos: QPointF) -> CornerHandle | BoxItem | RotationHandle | None`: copy `_box_item_at`'s body verbatim (identity-transform `items()` query, IntersectsItemShape, DescendingOrder, visible+enabled skip) and ADD `if isinstance(candidate, RotationHandle): return candidate` alongside the CornerHandle/BoxItem branches. Do NOT modify `_box_item_at` itself — `mouseDoubleClickEvent` (:1465) relies on its current contract, and its docstring documents the visual-only exclusion.
    2. In `mousePressEvent`, swap the :1372 call to `self._topmost_box_hit(scene_pos)`.
    3. Non-paint branch: add a RotationHandle branch alongside the CornerHandle branch — if the hit is a RotationHandle, resolve its parent (assert/isinstance BoxItem, mirroring `_begin_resize`'s parenting assertion) and call `self._begin_rotation(parent_item, scene_pos)`, then `event.accept()` and `return` — BEFORE the `_clear_selection()` fall-through at :1419. Calling `_begin_rotation` directly (instead of routing through `activate_callback`) matches how `_begin_resize` bypasses the handle's own press handler; the hook closure adds only a weakref hop.
    4. Mirror in the Alt-gated paint sub-branch (:1374-1390): RotationHandle hit -> same `_begin_rotation` + accept + return, placed beside the existing CornerHandle carve-out (per D-15 consistency).
    5. Change NOTHING about: the no-Alt paint fall-through (MASK-06 — presses over handles still paint), the empty-canvas `_clear_selection()` calls, `_begin_paint` acceptance at :1436-1444 (our accept+return happens earlier in the box branch, so it is unreachable for handle presses), the inline-editor guard, or RedetectHandle handling. RotationHandle import already exists at canvas.py:82.
    Update `_box_item_at`'s docstring only if needed to point readers at the new helper for press dispatch.
  </action>
  <verify>
    <automated>& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py tests/test_gui_boxes.py -q</automated>
  </verify>
  <done>All three Task 1 dispatch tests pass (handle press arms rotation + commits rotation_deg; empty-canvas click still clears; Alt+brush rotates). Full test suite green: & "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q reports 0 failed (baseline 1138 passed).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (none crossed) | Local desktop GUI mouse-event routing inside one process; no untrusted input, network, or persistence surface touched |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QZV-01 | Tampering | EditorCanvas.mousePressEvent dispatch | low | accept | Synthetic QMouseEvent paths are test-only; production events arrive from Qt's trusted event queue — no new attack surface |
| T-{phase}-SC | Tampering | npm/pip/cargo installs | n/a | accept | No package installs in this task; legitimacy gate not triggered |
</threat_model>

<verification>
- `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_sfx_editing.py tests/test_gui_boxes.py -q` — all pass
- Full suite: `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` — 0 failed
</verification>

<success_criteria>
- Dragging the visible rotation circle arms rotation, live-previews, and commits style.rotation_deg (user-reported symptom gone)
- Selection semantics unchanged everywhere else: empty-canvas click clears, Shift-click toggles, no-Alt paint presses paint over handles, Alt+resize/Alt+create-box intact
- Double-click inline-editor entry unaffected (`_box_item_at` contract untouched)
</success_criteria>

<output>
Create `.planning/quick/260825-uzv-fix-rotation-handle-dead-canvas-view-lev/260825-uzv-SUMMARY.md` when done
</output>

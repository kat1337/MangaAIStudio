---
phase: 04-ocr-recognition-text-editing
plan: 04
subsystem: gui (box display objects + inspector dock)
tags: [ocr, text-editing, gui, qt, qgraphicsview, qdockwidget, tdd, pytest-qt, outlined-text, bubble-badge]
requires:
  - Phase 04 Plan 01 PageBox Phase 4 fields + setters (edited/bubble_no/manual_override; set_recognized_text_edited/set_translation/has_recognized_text; copy() payload detach)
  - Phase 03 BoxItem + CornerHandle (the parent class + child-item pattern this plan extends)
  - Phase 03 EditorCanvas boxes_modified signal + _box_overlay_visible toggle pattern
provides:
  - manga_ai_studio.gui.box_item.BoxItem._text_overlay (QGraphicsTextItem child, z=120, PLAIN outlined text)
  - manga_ai_studio.gui.box_item.BoxItem._badge / _badge_digit (QGraphicsRectItem + QGraphicsTextItem, z=140, ItemIgnoresTransformations)
  - manga_ai_studio.gui.box_item.BoxItem.refresh_text_overlay() (current-focus rule: translation wins, D-10)
  - manga_ai_studio.gui.box_item.BoxItem.refresh_badge() (TL-outside position + edge-flip, D-15/D-16)
  - manga_ai_studio.gui.box_item.BoxItem.set_text_overlay_visible(bool) (the per-box T-toggle layer)
  - manga_ai_studio.gui.box_item._current_focus_text() (D-10 current-focus resolver)
  - Module constants _TEXT_OVERLAY_Z = 120, _BADGE_Z = 140
  - manga_ai_studio.gui.inspector_panel.InspectorPanel(QWidget) + _CommitTextEdit (Signals: translation_changed/recognized_edited/bubble_no_changed/vertical_changed)
  - manga_ai_studio.gui.canvas.EditorCanvas.toggle_text_overlay() / set_text_overlay_visible_flag() / _text_overlay_visible flag (D-12 third independent layer)
  - manga_ai_studio.gui.main_window.MainWindow.dock_inspector / inspector_panel + Inspector selection-follower + commit handlers
  - manga_ai_studio.gui.main_window.MainWindow.action_toggle_text_overlay (QAction, T, checkable default checked) + action_toggle_inspector
affects:
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/inspector_panel.py
  - tests/test_gui_boxes.py
  - tests/test_gui_canvas.py
tech-stack:
  added: []
  patterns:
    - outlined canvas text via QTextCharFormat.setTextOutline (RESEARCH Pattern 3 — single API, no multi-pass QPainter; PLAIN document per ASVS V5)
    - constant-viewport-px child via ItemIgnoresTransformations reused for the bubble badge (mirrors Phase 3's 8x8 handle)
    - per-BoxItem visibility flag independent of the box-layer visibility (the D-12 three-layer contract: text child's own visible flag vs the BoxItem's setVisible)
    - Inspector = follower QWidget: subscribes to scene.selectionChanged; commits route through MainWindow-supplied callbacks (panel never touches a PageBox directly)
    - commit-on-focus-loss QTextEdit (_CommitTextEdit.committed signal) for standard Qt commit semantics
key-files:
  created:
    - manga_ai_studio/gui/inspector_panel.py
  modified:
    - manga_ai_studio/gui/box_item.py
    - manga_ai_studio/gui/canvas.py
    - manga_ai_studio/gui/main_window.py
    - tests/test_gui_boxes.py
    - tests/test_gui_canvas.py
decisions:
  - BoxItem text overlay is a QGraphicsTextItem child (parented to the BoxItem, not parent-less) so it inherits the box's visibility (Shift+M hides the whole box incl. text + badge; T hides ONLY the text child — D-12). The overlay's OWN _text_overlay_visible flag is what the T toggle flips; refresh_text_overlay re-applies it so a new box respects the layer state.
  - Outlined text via QTextCharFormat.setTextOutline + setForeground merged on ONE format over the whole document (RESEARCH Pattern 3 verified merge order: set outline + foreground on a single QTextCharFormat, cursor.mergeCharFormat over the Document). No multi-pass QPainter, no QGraphicsDropShadowEffect.
  - Bubble badge uses sceneBoundingRect() for its TL-outside position (not self.rect()) because ItemIgnoresTransformations means the badge's pos() is in scene coords; the badge must track the box through move/resize/zoom, which is driven via _sync_handles calling refresh_badge (mirrors how handles reposition on zoom_changed).
  - Badge edge-flip: when the TL-outside position would clip off the page (sceneRect) TL edge, flip to inside-top-left inset 2px (UI-SPEC §17). Reads canvas.scene().sceneRect() (set by set_image); falls back to no-flip when the scene has no rect.
  - _current_focus_text is defensive against a payload that is not a real TextBlock (the bare-string 'p' marker the snapshot test passes) — uses getattr with defaults instead of calling has_recognized_text(), so a marker payload yields empty (overlay hidden) instead of AttributeError.
  - InspectorPanel edits commit on focus-loss / Ctrl+Return (QTextEdit) and editingFinished (QSpinBox) / toggled (QCheckBox) — standard Qt commit semantics. The panel emits typed Signals the MainWindow routes to its _on_inspector_*_committed handlers; the panel NEVER mutates a PageBox directly (it is a follower/editor).
  - Inspector recognized commit routes through set_recognized_text_edited (Plan 01 centralized manual-edit setter, D-04 edited=True) — NOT set_recognized_text (OCR-write) and NOT a direct payload.text write (bypasses the payload-None guard).
  - Task 3 checkpoint:human-verify auto-approved under auto_advance=true + human_verify_mode=end-of-phase — the visual-verification (overlay legibility on real artwork) is deferred to the end-of-phase UAT gate; the mechanics are covered by the automated pytest-qt suite.
actuals:
  tokens: 18500
  tasks: 2
  commits: 4
requirements-completed: [TEXT-04, TEXT-05]
coverage:
  - id: D1
    description: "BoxItem renders a translucent outlined text overlay (z=120) showing the D-10 current-focus text (translation wins, else recognized); PLAIN document (ASVS V5) styled via QTextCharFormat.setTextOutline (RESEARCH Pattern 3)."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_shows_recognized_when_no_translation"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_current_focus_rule_translation_wins"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_document_is_plain_not_rich"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_uses_outlined_text_format"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_text_overlay_hidden_when_no_recognized_text"
        status: pass
    human_judgment: true
    rationale: "The automated suite asserts the hex fill/outline colors and the current-focus rule, but overlay LEGIBILITY on real manga artwork (the D-11 translucent-white-on-artwork look) is a visual judgment no test can make — deferred to the end-of-phase human UAT gate."
  - id: D2
    description: "BoxItem renders a bubble-number badge (z=140, ItemIgnoresTransformations, 20x14 viewport px) at the TL corner OUTSIDE the box rect; amber #f5a623 2px border for manual_override badges (D-16), matte #0b0b0e for auto."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_shows_bubble_no_when_set"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_hidden_when_bubble_no_is_none"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_ignores_transformations"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_manual_override_amber_border"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_badge_digit_shows_bubble_number"
        status: pass
    human_judgment: true
    rationale: "Badge POSITION relative to the TL handle hit area on real artwork (RESEARCH Pitfall 7 — the three elements converge at the TL corner) is a visual judgment; the automated suite asserts the geometry math but not the on-screen feel. Deferred to the end-of-phase human UAT gate."
  - id: D3
    description: "set_text_overlay_visible(bool) is an independent visibility layer (D-12) — hides ONLY the text child, leaving box border + badges visible; canvas.toggle_text_overlay flips the per-canvas flag and applies it to every box + every box added afterwards."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_set_text_overlay_visible_false_hides_only_text"
        status: pass
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_toggle_text_overlay_hides_only_text_children"
        status: pass
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_toggle_text_overlay_independent_of_box_overlay"
        status: pass
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_toggle_text_overlay_applies_to_new_boxes"
        status: pass
    human_judgment: false
  - id: D4
    description: "InspectorPanel (QDockWidget, D-08) surfaces both text fields + bubble number + origin/language/vertical metadata for the selected box; edits commit through the Plan 01 setters (set_recognized_text_edited / set_translation / bubble_no+manual_override / payload.vertical) and push a BOXES snapshot + refresh the overlay."
    requirement: TEXT-05
    verification:
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_load_box_populates_fields"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_recognized_edit_emits_recognized_edited"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_translation_edit_emits_translation_changed"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_bubble_spin_emits_bubble_no_changed"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_bubble_spin_range_is_bounded"
        status: pass
      - kind: unit
        ref: "tests/test_gui_boxes.py#test_inspector_origin_label_hue_colored"
        status: pass
    human_judgment: true
    rationale: "Inspector selection-following in a live multi-selection/page-switch session (the UI-SPEC §18 'updates whenever canvas selection changes' contract under real interaction) is a judgment-dependent behavior the isolated panel tests cannot fully exercise; deferred to the end-of-phase human UAT gate."
  - id: D5
    description: "Toggle Text Overlay (T) action — checkable, default checked, placed after Toggle Box Overlay in the View menu; the three overlay toggles (M / Shift+M / T) are independent siblings (D-12)."
    requirement: TEXT-04
    verification:
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_canvas_has_text_overlay_flag_and_toggle"
        status: pass
      - kind: unit
        ref: "tests/test_gui_canvas.py#test_toggle_text_overlay_independent_of_box_overlay"
        status: pass
    human_judgment: false
metrics:
  duration: 17 min
  completed: 2026-08-06
  tasks: 2
  files: 6
status: complete
---

# Phase 04 Plan 04: BoxItem Text Overlay + Bubble Badge + Inspector Dock Summary

Delivered the Phase 4 "boxes become display objects" upgrade (D-09) as TDD: each BoxItem now carries a persistent translucent outlined text overlay (QGraphicsTextItem child, z=120, current-focus rule D-10 — translation wins, else recognized; PLAIN document per ASVS V5, styled via the single-API QTextCharFormat.setTextOutline) + a bubble-number badge (QGraphicsRectItem + digit, z=140, ItemIgnoresTransformations, TL-outside with edge-flip), the new InspectorPanel QDockWidget (D-08, tabbed with Tools) that surfaces both text fields + metadata and commits through the Plan 01 setters, and the Toggle Text Overlay (T) action as an independent third visibility layer (D-12 — independent of M mask and Shift+M box).

## What Was Built

### Task 1 — BoxItem text overlay (z=120) + bubble badge (z=140) + refresh methods (TDD)

`manga_ai_studio/gui/box_item.py`:

- **Module z-order constants** `_TEXT_OVERLAY_Z = 120` and `_BADGE_Z = 140` (above the box border z=100, below handles z=150 — RESEARCH Pitfall 7, UI-SPEC §Z-order) plus the overlay/badge style constants (fill `rgba(232,232,234,0.85)` + outline `rgba(11,11,14,0.92)` 2px + 14 scene px Liberation Sans font; badge 20x14 viewport px, fill `rgba(0,0,0,0.72)`, digit `#e8e8ea` 12px semibold, matte `#0b0b0e` outline / amber `#f5a623` override outline).
- **`_text_overlay` child** (`QGraphicsTextItem`, z=120) added in `BoxItem.__init__`: a child of the BoxItem so it inherits the box's visibility (Shift+M hides the whole box incl. text; the T toggle hides ONLY this child via its own `_text_overlay_visible` flag — D-12). PLAIN text document (ASVS V5, T-4-07 — never `setHtml` on OCR output); `setAcceptRichText` discipline preserved by only ever calling `setPlainText`.
- **`_badge` + `_badge_digit` children** (`QGraphicsRectItem` 20x14 + `QGraphicsTextItem` digit, z=140, both `ItemIgnoresTransformations`) — constant viewport-px at any zoom, mirroring Phase 3's 8x8 handle. The digit is a child of the rect so it inherits the rect's position/visibility.
- **`refresh_text_overlay()`** — computes the D-10 current-focus text via `_current_focus_text()` (translation when present, else recognized; empty → overlay hidden). Builds the outlined run with a single `QTextCharFormat` carrying BOTH `setTextOutline(_OVERLAY_OUTLINE)` and `setForeground(_OVERLAY_FILL)`, then `cursor.mergeCharFormat` over the whole Document (RESEARCH Pattern 3 verified merge order — outline + fill on one format, merged in one pass). Positions the overlay inside the box rect, inset by `pen_width/2 + 2px`. Re-applies `_text_overlay_visible` so the T-toggle state survives a refresh.
- **`refresh_badge()`** — hidden when `bubble_no is None`; otherwise positioned at the TL corner OUTSIDE the box rect (`sceneBoundingRect().left() - badge_w - 2`, `top() - badge_h - 2`) via `sceneBoundingRect()` (because `ItemIgnoresTransformations` makes the badge's pos() scene-space). Edge-flip to inside-top-left inset 2px when the outside position would clip the page TL edge (reads `canvas.scene().sceneRect()`). Border pen amber `#f5a623` for `manual_override`, matte `#0b0b0e` for auto (D-16). Called from `_sync_handles` so the badge tracks move/resize/zoom (mirrors how handles reposition on `zoom_changed`).
- **`set_text_overlay_visible(bool)`** — the per-box T-toggle layer (D-12): flips `_text_overlay_visible` and hides/shows the text child only; box border + badge stay visible.
- **`_current_focus_text()`** — defensive against a non-TextBlock payload (the bare-string `"p"` marker the snapshot test passes): uses `getattr` defaults so a marker payload yields empty (overlay hidden) instead of `AttributeError` through `has_recognized_text()`.

### Task 2 — InspectorPanel dock + Toggle Text Overlay (T) (TDD)

`manga_ai_studio/gui/inspector_panel.py` (NEW):

- **`InspectorPanel(QWidget)`** mirroring `ToolsPanel`'s shape (class-scope `Signal`s, `QVBoxLayout` root with sm margins, dark QSS copied from `_TOOLS_QSS` + `QTextEdit` styling). `setObjectName("inspector_panel")`. Class-scope Signals: `translation_changed(str)`, `recognized_edited(str)`, `bubble_no_changed(int)`, `vertical_changed(bool)`.
- **Fields (QFormLayout, UI-SPEC §18):** `bubble_spin` (`QSpinBox` range 1..9999 — T-4-08 tampering mitigation), `origin_label` (read-only, hue-colored green/amber on `load_box`), `recognized_edit` + `translation_edit` (`_CommitTextEdit` — multi-line, `setAcceptRichText(False)` per ASVS V5, placeholder copy per UI-SPEC §Copywriting), `language_label` (read-only), `vertical_check` (`QCheckBox`, tooltip "Coming soon — preserves the vertical flag for export" — D-06 v1 no-op per RESEARCH Pitfall 5).
- **`_CommitTextEdit`** — commits on focus-loss (`focusOutEvent`) and Ctrl+Return/Ctrl+Enter (`keyPressEvent`); plain Enter inserts a newline (multi-line convention). The `committed` signal is what `connect_commit_handlers` wires.
- **`load_box(pagebox)`** — populates all fields, blocking signals during populate so the `setValue`/`setPlainText` calls do NOT re-emit the change signals (no spurious commit of just-loaded values). Hue-colors the Origin label. Enables all fields + hides the empty-state copy.
- **`clear()`** — shows the empty-state copy + disables all fields (the no-selection gate).
- **`connect_commit_handlers(on_recognized, on_translation, on_bubble, on_vertical)`** — the single point where the panel's change signals route to the MainWindow-supplied callbacks (the panel NEVER mutates a PageBox directly — it is a follower/editor).

`manga_ai_studio/gui/canvas.py`:

- **`_text_overlay_visible` flag** (default `True` — D-09 boxes become display objects) + **`set_text_overlay_visible_flag(bool)`** + **`toggle_text_overlay()`** (the D-12 third independent visibility layer). `set_boxes` and `_commit_create` now sync the flag onto each new BoxItem so a box added AFTER the toggle respects the layer state.

`manga_ai_studio/gui/main_window.py`:

- **Inspector dock** (`dock_inspector` QDockWidget, tabbed with Tools via `tabifyDockWidget` per UI-SPEC §18) + **`action_toggle_text_overlay`** (QAction, shortcut T, checkable default checked, placed immediately after Toggle Box Overlay in the View menu) + **`action_toggle_inspector`** (Toggle Inspector dock action alongside Toggle Sidebar/Tools).
- **Selection-follower:** `canvas.scene().selectionChanged` → `_on_canvas_selection_changed` loads the selected box (or clears the Inspector). The Inspector is a pure follower — it never drives canvas selection.
- **Inspector commit handlers** `_on_inspector_{recognized,translation,bubble,vertical}_committed` — each captures a PRE-edit BOXES snapshot, mutates the selected pagebox through the Plan 01 setters (`set_recognized_text_edited` for D-04 manual edits / `set_translation` / `bubble_no` + `manual_override=True` per D-16 / `payload.vertical`), then pushes the snapshot via `boxes_modified`, refreshes the overlay + badge, and re-loads the Inspector.
- **`_on_toggle_text_overlay_toggled`** — forwards the T action to `canvas.set_text_overlay_visible_flag`.

## Verification

```
python -m pytest tests/test_gui_boxes.py tests/test_gui_canvas.py -x -q \
  --deselect "tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip"
# 95 passed, 1 deselected

python -m pytest tests/ -q
# 346 passed, 1 failed (PRE-EXISTING — see Deviations)
```

Acceptance criteria verified for both tasks (all grep counts exact):
- Task 1: `_TEXT_OVERLAY_Z = 120` (1), `_BADGE_Z = 140` (1), `def refresh_text_overlay` (1), `def refresh_badge` (1), `def set_text_overlay_visible` (1), `setTextOutline` (>=1, actual 2).
- Task 2: `test -f inspector_panel.py` (PASS), `class InspectorPanel` (1), the 3 Signals (>=3, actual 5), `def toggle_text_overlay` canvas (1), `def set_text_overlay_visible` box_item (1), `action_toggle_text_overlay` main_window (>=2, actual 8), `QKeySequence("T")` (1), `dock_inspector` (>=3, actual 7).

## Performance

- **Duration:** 17 min
- **Started:** 2026-08-07T19:30:12Z
- **Completed:** 2026-08-07T19:47:12Z
- **Tasks:** 2 implementation tasks (Task 3 checkpoint auto-approved under end-of-phase verify mode)
- **Files modified:** 6 (1 created, 5 modified)

## Task Commits

Each task was committed atomically (RED test → GREEN implementation per the project's per-task TDD convention):

1. **Task 1 RED:** `a836533` (test) — add failing tests for BoxItem text overlay + bubble badge
2. **Task 1 GREEN:** `3a058c4` (feat) — implement BoxItem text overlay + bubble badge (TDD)
3. **Task 2 RED:** `3d7029a` (test) — add failing tests for InspectorPanel + Toggle Text Overlay
4. **Task 2 GREEN:** `a74fa5c` (feat) — implement InspectorPanel dock + Toggle Text Overlay (T) (TDD)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified

- `manga_ai_studio/gui/inspector_panel.py` (NEW) — the D-08 Inspector dock body: both text fields + metadata, commit-on-focus-loss, class-scope Signals routed to MainWindow callbacks.
- `manga_ai_studio/gui/box_item.py` — Phase 4 display-object children: `_text_overlay` (z=120) + `_badge`/`_badge_digit` (z=140) + `refresh_text_overlay`/`refresh_badge`/`set_text_overlay_visible`/`_current_focus_text` + the z-order + style constants.
- `manga_ai_studio/gui/canvas.py` — `_text_overlay_visible` flag + `set_text_overlay_visible_flag`/`toggle_text_overlay`; `set_boxes` + `_commit_create` sync the flag onto new boxes.
- `manga_ai_studio/gui/main_window.py` — Inspector dock + Toggle Text Overlay (T) action + Toggle Inspector action + selection-follower + 4 Inspector commit handlers.
- `tests/test_gui_boxes.py` — 16 Task 1 + 11 Task 2 Inspector tests (27 new).
- `tests/test_gui_canvas.py` — 4 Task 2 toggle-independence tests.

## Decisions Made

See the `decisions:` frontmatter above for the full list. Highlights:

- Overlay is a QGraphicsTextItem CHILD of the BoxItem (not parent-less) so it inherits the box's visibility — the D-12 three-layer contract falls out naturally (Shift+M hides the whole box via `setVisible(False)` which hides all children incl. text; T hides ONLY the text child via its own `_text_overlay_visible` flag).
- Outlined text via the single-API `QTextCharFormat.setTextOutline` + `setForeground` on one format merged over the Document (RESEARCH Pattern 3 verified) — no multi-pass QPainter, no QGraphicsDropShadowEffect.
- Badge position uses `sceneBoundingRect()` (not `self.rect()`) because `ItemIgnoresTransformations` makes its pos() scene-space; refreshed from `_sync_handles` so it tracks move/resize/zoom.
- Inspector is a pure FOLLOWER: subscribes to `scene().selectionChanged`; commits route through MainWindow-supplied callbacks; never mutates a PageBox directly. Recognized commits go through `set_recognized_text_edited` (NOT `set_recognized_text` / direct payload write).
- Task 3 checkpoint auto-approved under `auto_advance=true` + `human_verify_mode=end-of-phase`.

## Deviations from Plan

None — the plan executed exactly as written. Two in-flight adjustments that conform to the plan's intent (Rule 1 auto-fixes, not plan deviations):

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_current_focus_text` defensive against a non-TextBlock payload**
- **Found during:** Task 1 GREEN (the `test_boxes_snapshot_returns_pageboxes` regression surfaced it)
- **Issue:** the original `_current_focus_text` called `self.pagebox.has_recognized_text()`, which accesses `payload.text` unconditionally. The `test_boxes_snapshot_returns_pageboxes` test builds a `PageBox(payload="p")` (a bare-string duck-typed marker). Previously `BoxItem.__init__` never touched `payload.text`, but Task 1's `refresh_text_overlay` (called from `__init__`) now does → `AttributeError: 'str' object has no attribute 'text'`.
- **Fix:** `_current_focus_text` now reads translation + text via `getattr` with defaults (`getattr(payload, "translation", "")` / `getattr(payload, "text", None)`) instead of calling `has_recognized_text()`. A marker payload yields empty → overlay hidden (the correct behavior). Real TextBlock payloads (None or a TextBlock) work unchanged.
- **Files modified:** `manga_ai_studio/gui/box_item.py`
- **Verification:** `test_boxes_snapshot_returns_pageboxes` green again; full `test_gui_boxes.py` 52 passed.
- **Committed in:** `3a058c4` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] bubble-spin test asserted `setValue` triggers the commit (Qt does not)**
- **Found during:** Task 2 GREEN (`test_inspector_bubble_spin_emits_bubble_no_changed` failed)
- **Issue:** the test called `panel.bubble_spin.setValue(9)` and expected the `bubble_no_changed` signal to fire. But `QSpinBox.editingFinished` (the correct production commit signal — fires on focus-loss/Enter) does NOT fire on a programmatic `setValue` by Qt design. The implementation is correct (commit on `editingFinished`); the test's commit trigger was wrong.
- **Fix:** the test now calls `panel.bubble_spin.editingFinished.emit()` after `setValue` to simulate the focus-loss the real UI produces when the user tabs away from the spinbox. Production semantics (commit on focus-loss/Enter) unchanged.
- **Files modified:** `tests/test_gui_boxes.py`
- **Verification:** `test_inspector_bubble_spin_emits_bubble_no_changed` green; all 14 Task 2 tests green.
- **Committed in:** `a74fa5c` (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bug fixes — both correctness fixes for the test/impl contract, no scope creep).
**Impact on plan:** Both auto-fixes necessary for the tests to pass against correct production semantics. No architectural changes (Rule 4), no auth gates, no package installs.

## Authentication Gates

None.

## Known Stubs

None that block the plan goal. The `vertical_check` (D-06) is an INTENTIONAL v1 no-op: it writes `payload.vertical` (export metadata) and is the seam for the future typesetting phase, but does NOT flip the inline editor to vertical in this plan (RESEARCH Pitfall 5 — the inline editor itself lands in Plan 05; this plan is display + Inspector only). The tooltip "Coming soon — preserves the vertical flag for export" documents this. No placeholder text/TODO/FIXME in any production code path.

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): a real-event body-drag move lands a box at `(69,69,129,129)` instead of the asserted `(70,70,130,130)` — a 1px drag-coordinate rounding difference. Verified failing identically against pristine pre-04-01 source (commit `210a178`) in plans 04-01, 04-02, 04-03. It is a GUI drag-simulation rounding issue that does NOT exercise the text overlay, bubble badge, Inspector, or any new code path in this plan (all Qt Graphics View display-object + dock work). Re-confirmed failing in this plan's full-suite run (`1 failed, 346 passed`). Already logged to `.planning/phases/04-ocr-recognition-text-editing/deferred-items.md`; not fixed.

## Threat Surface

No new security-relevant surface beyond the plan's `<threat_model>`. The two trust boundaries are mitigated exactly as designed:

- **T-4-07 (OCR text → canvas overlay XSS-equivalent):** the overlay document is PLAIN text — `refresh_text_overlay` calls `setPlainText` + `QTextCursor.insertText` with a `QTextCharFormat` (NEVER `setHtml` or `Qt.TextRichText`). Verified by `test_text_overlay_document_is_plain_not_rich` (the `<script>alert(1)</script>` OCR payload echoes as literal text). The Inspector's `recognized_edit`/`translation_edit` also `setAcceptRichText(False)`.
- **T-4-08 (Inspector QSpinBox out-of-range bubble number):** `bubble_spin` range is bounded 1..9999; `test_inspector_bubble_spin_range_is_bounded` guards it. The bounded value is what reaches `pagebox.bubble_no` via the commit handler.

## TDD Gate Compliance

Plan frontmatter `type: execute`; both implementation tasks are `tdd="true"`. Gate sequence observed per task (separate RED `test(...)` commit then GREEN `feat(...)` commit):

- **Task 1:** RED `a836533` — `test(04-04): add failing tests for BoxItem text overlay + bubble badge` (collection ImportError on `_BADGE_Z`/`_TEXT_OVERLAY_Z` + the refresh methods — confirmed failing before implementation). GREEN `3a058c4` — `feat(04-04): implement BoxItem text overlay + bubble badge (TDD)` (16/16 new tests passing).
- **Task 2:** RED `3d7029a` — `test(04-04): add failing tests for InspectorPanel + Toggle Text Overlay` (collection ModuleNotFoundError on `manga_ai_studio.gui.inspector_panel` — confirmed failing before implementation). GREEN `a74fa5c` — `feat(04-04): implement InspectorPanel dock + Toggle Text Overlay (T) (TDD)` (14/14 new tests passing).

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — implementations were clean on first pass (modulo the two Rule 1 in-flight test/impl-contract fixes documented above).

## Self-Check: PASSED

Created/modified files:
- FOUND: manga_ai_studio/gui/inspector_panel.py
- FOUND: manga_ai_studio/gui/box_item.py
- FOUND: manga_ai_studio/gui/canvas.py
- FOUND: manga_ai_studio/gui/main_window.py
- FOUND: tests/test_gui_boxes.py
- FOUND: tests/test_gui_canvas.py

Commits:
- FOUND: a836533 (test(04-04): add failing tests for BoxItem text overlay + bubble badge)
- FOUND: 3a058c4 (feat(04-04): implement BoxItem text overlay + bubble badge (TDD))
- FOUND: 3d7029a (test(04-04): add failing tests for InspectorPanel + Toggle Text Overlay)
- FOUND: a74fa5c (feat(04-04): implement InspectorPanel dock + Toggle Text Overlay (T) (TDD))

## Next Phase Readiness

- The "boxes become display objects" layer is complete: every BoxItem renders text + badge; the Inspector edits commit through the Plan 01 setters and refresh the overlay. Plan 05 (inline editor) can layer on top — the BoxItem already exposes `refresh_text_overlay`/`refresh_badge` to re-render after an inline commit, and the `_text_overlay`/`_badge` children are in place. Plan 05 owns the `mouseDoubleClickEvent` → inline-editor entry (deliberately NOT added here).
- The Toggle Text Overlay (T) completes the D-12 three-independent-layer contract (M / Shift+M / T); Plan 05's inline editor is the last text surface.
- The deferred `vertical_check` editor-mode flip is the seam for the future typesetting phase.

---
*Phase: 04-ocr-recognition-text-editing*
*Completed: 2026-08-06*

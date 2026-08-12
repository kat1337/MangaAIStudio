---
phase: 07-typesetting-tran-02-render-translated-text-into-the-page
reviewed: 2026-08-11T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/box_item.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/main_window.py
  - manga_ai_studio/gui/text_renderer.py
  - manga_ai_studio/core/text_style.py
  - tests/test_gui_boxes.py
  - tests/test_gui_inspector_styling.py
  - tests/test_core/test_typeset_layout.py
  - tests/test_core/test_typeset_bake.py
  - tests/test_gui_project.py
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 07 Gap-Closure (plans 07-06..07-12): Code Review Report

**Reviewed:** 2026-08-11
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the gap-closure changes (G-07-1..G-07-7) across the six source files
plus the five test files. The load-bearing fixes are sound: the G-07-6
graveyard (`_retire_boxes`/`_release_graveyard`) is correctly guarded
(single outstanding timer, batch drain, all three removal sites route through
it, pre-mutation snapshots captured before every clear), the G-07-1
`bool(style.vertical)` contract holds at all three render sites with no stray
`payload.vertical` render reads in gui/ (the remaining reads in
`core/image_ops.py` and `core/project_io.py` are geometry/export metadata,
correct), the G-07-5 align_v dy math is exact for all three values with dy=0
on the vertical path, the G-07-4 grow loop is bounded (12 iterations, cap
`min(inner_w, inner_h)`, floor at loop top, last-fit retention, byte-identical
shrink path), and the G-07-2 font-filter proxy wiring was **verified
empirically** on the pinned stack (QFontComboBox.setModel accepts the
QSortFilterProxyModel in Qt 6.10 — view model, reparent trick, escaped regex,
clear-on-load at all three sites, Mixed path intact; the 49 inspector/renderer
tests and 223 box/project tests pass).

The findings below are all lower-severity: one per-keystroke commit path on
the (editable-by-default) QFontComboBox that contradicts the code's own
T-07-18 "never free text" claim, a WR-01 blind spot in the G-07-7 per-axis
align guard that pushes a no-op undo entry when the user re-picks the Mixed
sentinel, and a teardown RuntimeError window in the graveyard release timer
itself (the very class of teardown issue G-07-6 exists to prevent).

## Warnings

### WR-01: Editable QFontComboBox commits free-typed text — spurious undo entries + arbitrary families

**File:** `manga_ai_studio/gui/inspector_panel.py:400,1180-1192`
**Issue:** `QFontComboBox` is **editable by default** (probed on the pinned
stack: `isEditable() == True`). Typing into its line edit fires
`currentTextChanged` on **every keystroke** (probe: typing "Ari" fired
`currentTextChanged` with "A", "Ar", "Ari"). Each emission flows through
`_on_font_widget_changed` → `_emit_style_font_if_changed` → `on_style_font`,
and since the partial string differs from `_loaded_style_font`, **every
keystroke becomes a full style commit**: `_inspector_style_commit` captures a
snapshot, writes the garbage family (e.g. "A") into every selected
`TextStyle.font_family` via `_replace_style`, and emits `boxes_modified` —
one no-op-ish BOXES undo entry per keystroke, with a nonexistent family
persisted into the model (renders via Qt fallback). The same hole applies to
`_on_default_font_clicked` (line 1223-1234), whose docstring claims "The
family is always one of the QFontComboBox's real families — never free text
(T-07-18)" — that claim is false for the typing path. This predates G-07-2
but the gap-closure work touches exactly this control row and its comments
assert the false contract.

**Fix:** Gate the commit on real membership — in `_emit_style_font_if_changed`
(and `_on_default_font_clicked`), reject families not present in the combo's
source list:
```python
def _emit_style_font_if_changed(self, family: str, on_style_font) -> None:
    if not family or family == "Mixed":
        return  # the sentinel never leaves the widget layer (Pitfall 7)
    if self.font_combo.findText(family) == -1:
        return  # free-typed text is not a real family (T-07-18)
    if family != self._loaded_style_font:
        on_style_font(family)
```
Note: do NOT fix this via `setEditable(False)` — the "Mixed" sentinel display
in the font combo currently works **only because** the editable line edit
shows text that has no model row (probed: `findText("Mixed") == -1` but
`currentText()` reports "Mixed"); a non-editable combo would silently break
the D-10 Mixed presentation.

### WR-02: G-07-7 align guard — re-picking the Mixed sentinel pushes a no-op undo entry

**File:** `manga_ai_studio/gui/inspector_panel.py:1281-1297`
**Issue:** The per-axis WR-01 gate compares `(h, v)` against the **loaded**
display values. After a per-axis commit (e.g. H→"Left" on a both-Mixed
selection), the MainWindow reloads the panel: H is now uniform ("Left") but V
stays Mixed — loaded = ("Left", "Mixed"). The H combo still offers the
"Mixed" entry (item 0). If the user re-opens H and picks "Mixed" (an
unchanged state — returning to the sentinel), `(h, v) == ("Mixed", "Mixed")
!= ("Left", "Mixed")`, so the guard fires a commit with `(None, None)`.
`_replace_align` correctly no-ops on both-None, but `_inspector_style_commit`
(main_window.py:3027-3052) still emits `boxes_modified` unconditionally →
pushes a **no-op BOXES undo entry** (before == after) — exactly what the
WR-01 discipline exists to prevent.

**Fix:** Skip the emission when both axes translate to None (the commit
carries nothing to apply):
```python
h_model = None if h == "Mixed" else _ALIGN_H_TO_MODEL[h]
v_model = None if v == "Mixed" else _ALIGN_V_TO_MODEL[v]
if h_model is None and v_model is None:
    return  # re-picking the sentinel is an unchanged state — no commit
on_style_align(h_model, v_model)
```

### WR-03: Graveyard release timer can fire against an invalidated canvas at teardown

**File:** `manga_ai_studio/gui/canvas.py:1672-1682`
**Issue:** `QTimer.singleShot(0, self._release_graveyard)` holds a strong
reference to the canvas wrapper. If the window is destroyed (the C++ canvas
is deleted by its QObject parent chain, invalidating the wrapper) while a
graveyard batch is still pending — i.e. a box removal followed by close in
the same event-loop iteration — the timer callback runs
`self._graveyard_pending = False` / `self._box_graveyard.clear()` on an
invalidated Shiboken object and raises `RuntimeError: Internal C++ object
already deleted` from inside the event loop. This is the same class of
teardown hazard G-07-6 was built to eliminate, and the fix is trivially
consistent with the module's existing belt-and-suspenders pattern (the
`Shiboken.isValid` guard in `TypesetOverlayItem.paint`).

**Fix:**
```python
def _release_graveyard(self) -> None:
    if not Shiboken.isValid(self):
        self._graveyard_pending = False  # only if the wrapper is alive
        return
    self._graveyard_pending = False
    self._box_graveyard.clear()
```
(Import `Shiboken` in canvas.py — `box_item.py` already imports it.)

## Info

### IN-01: `_commit_create` never installs the primary-owner weakref

**File:** `manga_ai_studio/gui/canvas.py:2187`
**Issue:** Every box built by `set_boxes` gets
`item.set_primary_owner(_weakref(self))` (line 1732), but a box created via
Alt+drag (`_commit_create`, line 2187) does not. Consequence: the fresh
box's `itemChange → _sync_handles_for_state` consults `_primary_owner is
None` and shows corner handles whenever selected — even as a non-primary
member of a later multi-selection (the canvas helper paths pass the explicit
`primary=` argument, so today's flows are unaffected; only direct
`setSelected` paths diverge). Install the owner for consistency with the
D-09 primary-only contract:
```python
item = BoxItem(pb)
item.set_primary_owner(_weakref(self))
```

### IN-02: Default-font provider lambda reads QSettings twice per call

**File:** `manga_ai_studio/gui/main_window.py:136-140`
**Issue:** `lambda: default_style(self._default_font_family()) if
self._default_font_family() else None` constructs a `QSettings` and reads
'defaultFontFamily' twice per new box. Cosmetic; a single read avoids the
double store construction:
```python
lambda: (lambda f: default_style(f) if f else None)(self._default_font_family())
```

### IN-03: `_ROTATE_EXTRA` overlaps `_ASCII_ROTATE`

**File:** `manga_ai_studio/gui/text_renderer.py:124-143`
**Issue:** `_ROTATE_EXTRA` contains `"-"`, `"("`, `")"` — already members of
`_ASCII_ROTATE` (0x2D/0x28/0x29 are in 0x21..0x7F minus letters/digits).
The classification is still correct (`char_rotates` is a union), so this is
dead redundancy, not a bug. The set's actual purpose is the non-ASCII
fullwidth punctuation ("—", "…", "～"); the halfwidth members can be dropped.

### IN-04: Font-filter tests depend on the installed font database

**File:** `tests/test_gui_inspector_styling.py:886-897,959-963`
**Issue:** `test_font_filter_contains_match` / `_contains_match_scenario`
hard-assert `len(words) > 1` / `assert multi` on the real `QFontDatabase`
family list. On a minimal headless container whose only installed family is
single-word (e.g. DejaVu Sans), these tests **fail** rather than skip —
environment-brittle. Consider a `pytest.skip` when no multi-word family
exists, so the suite stays green on minimal CI images.

## Verified-Clean Notes (focus areas)

- **G-07-6 graveyard (canvas.py:1659-1682):** `_graveyard_pending` allows at
  most one outstanding timer; a single `_release_graveyard` drains the whole
  batch (no double-release, no leak); all three removal sites (`set_boxes`
  :1722, group Delete :1507, `_remove_box` :2230) route through
  `_retire_boxes`; every site captures the pre-mutation `boxes_snapshot()`
  before clearing (undo semantics unchanged); the two weakref regression
  tests (test_gui_boxes.py:4644-4759) pin the alive-through-flush /
  dead-after-iteration contract. The timer-fires-after-UpdateRequest ordering
  argument is sound (posted-event FIFO + 0ms timer).
- **Shiboken.isValid paint guard (box_item.py:344-347):** correct usage; the
  graveyard is the load-bearing fix and the guard is genuine defense-in-depth
  for the exact 0xC0000409 line; no race (single-threaded GUI dispatch).
- **G-07-1 vertical contract:** all three render sites use
  `bool(style.vertical)` (box_item.py:698, text_renderer.py:1030,
  main_window.py:3118); the only `payload.vertical` reads left are the
  geometry math (image_ops.py:150/277/407) and the exporter
  (project_io.py:201); the checkbox reads/writes `style.vertical` with a
  style-None fallback (inspector_panel.py:608, 772); `_ensure_payload`
  removal has no side effects (all callers were already payload-None safe).
- **Upright Latin (text_renderer.py:118-123,147-159):** classification
  correct (digits/A-Z/a-z upright; 0x21..0x7E remainder + fullwidth bracket
  set rotated; space/multi-char False); placement geometry consistent
  (column extent w for upright, h for rotated; per-char centering verified
  against paint's rotate-around-center translate).
- **G-07-5 align_v dy (box_item.py:417-418):** `dy = origin.y - box.y -
  inset` equals the layout's align_v offset for top (0) / middle
  ((inner_h - block_h)/2) / bottom (inner_h - block_h); the vertical path's
  origin carries no dy → exactly 0; the 3x3 pixel-equivalence matrix
  (test_gui_boxes.py:1393-1412) pins canvas ≡ bake.
- **G-07-7 Mixed align:** item-preserving combos, Mixed→None per-axis
  translation, `_replace_align` skips None axes, sentinel never reaches a
  TextStyle (Pitfall 7 tests pass), single-select path has no Mixed items
  (byte-identical); only the WR-02 sentinel-re-pick edge above is open.
- **G-07-4 grow-to-fit:** bounded 12 iterations; `grow_cap = min(inner_w,
  inner_h)`; floor checked at loop top (no iteration renders below 5px);
  last-fit retained after a failed grow (no shrink fall-through past a fit);
  from a never-fitting base the 12×0.9 shrink path is byte-equivalent; both
  orientations verified against pathological 2000-char inputs
  (test_typeset_layout.py:186-211, 477-484).
- **G-07-3 default font:** `default_style()` is Qt-free (text_style.py:55-66);
  the QSettings key ('defaultFontFamily') is read with `str(... or "")`
  coercion (main_window.py:1888-1897); provider None-on-empty contract holds
  for both the user-box path (canvas.py:2181-2185) and the detected-box path
  (main_window.py:3943-3969); no-key boxes keep `style is None`; existing
  boxes are never re-styled (D-06 — the Set-as-Default handler only
  persists).
- **G-07-2 font filter:** `QFontComboBox.setModel(proxy)` **is accepted** on
  the pinned PySide6 6.10.1 stack (probed — view model is the proxy, no
  qWarning); the reparent-first trick prevents the combo from deleting the
  source model; the regex is escaped (ASVS V5); the filter clears in
  `load_box`/`load_multi_selection`/`clear`; the signal-blocked
  `setCurrentText` restore prevents spurious commits on keystroke row churn;
  Mixed load path intact (tests pass).
- **General:** no `setHtml` anywhere in gui/ (all plain-text documents, ASVS
  V5); no new threading in the touched modules (QThreadPool workers remain in
  worker_thread.py/main_window dispatch); no new crash vectors beyond WR-03.

---

_Reviewed: 2026-08-11_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_

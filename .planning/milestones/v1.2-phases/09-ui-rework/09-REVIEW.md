---
phase: 09-ui-rework
reviewed: 2026-08-21T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - manga_ai_studio/gui/tools_strip.py
  - manga_ai_studio/gui/side_panel.py
  - manga_ai_studio/gui/tools_panel.py
  - manga_ai_studio/gui/inspector_panel.py
  - manga_ai_studio/gui/main_window.py
  - pyproject.toml
  - manga_ai_studio/gui/assets/icons/move.svg
  - manga_ai_studio/gui/assets/icons/brush.svg
  - manga_ai_studio/gui/assets/icons/rectangle.svg
  - manga_ai_studio/gui/assets/icons/lasso.svg
  - manga_ai_studio/gui/assets/icons/eraser.svg
  - manga_ai_studio/gui/assets/icons/crop.svg
  - manga_ai_studio/gui/assets/icons/detect-text.svg
  - manga_ai_studio/gui/assets/icons/inpaint.svg
  - tests/test_gui_tools_strip.py
  - tests/test_gui_side_panel.py
  - tests/test_gui_edit_section.py
  - tests/test_gui_canvas.py
  - tests/test_gui_crop_tool.py
  - tests/test_gui_curves_dialog.py
  - tests/test_gui_detection_settings.py
  - tests/test_gui_detection_boxes.py
  - tests/test_gui/test_detection_settings_tooltip.py
  - tests/test_gui/test_tools_panel_masker.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-08-21
**Depth:** standard
**Files Reviewed:** 24 (7 source/config + 8 SVG icons + 9 test files)
**Status:** issues_found

## Summary

Phase 9 (vertical ToolsStrip, unified collapsible SidePanel, Edit section,
menu slimming) is well-built. Adversarial tracing of the risky seams found no
critical defects:

- **Tool-sync single-emission contract (WR-02)** holds on every path: the
  strip's exclusive `QActionGroup` owns exactly its six actions; `toggled`
  checked-only emission (`tools_strip.py:259-272`); `set_active_tool`
  blocks signals per-action AND explicitly unchecks the others
  (`tools_strip.py:286-294`) — which correctly compensates for signal-blocking
  suppressing the group's private exclusivity connections. Window
  `action_tool_*` stay standalone and are driven explicitly
  (`main_window.py:4433-4443`). No double-connect of `triggered`+`toggled`.
- **Collapse persistence (D-02)** is sound: `restore_expanded` blocks header
  signals around the seed so no write-back fires
  (`side_panel.py:189-200`); `_read_side_panel_expanded` tolerantly parses
  and fails open to EXPANDED on garbage/missing keys
  (`main_window.py:3134-3154`); the chevron toggle never persists.
- **EditSection** binds the six LIVE QActions via `setDefaultAction`
  (no lambda rewiring, no op duplication); gating is inherited through the
  default-action binding and asserted both directions in tests.
- **Icon loading** is module-relative only (`tools_strip.py:41-96`) — no
  CWD/user-path reach; all 8 SVGs exist, are valid 24×24 `fill="none"`
  strokes, and are covered by the new `package-data` glob.
- **Detect Boxes bidirectional sync** has blockSignals guards on BOTH legs of
  the checkbox↔action loop (`main_window.py:3181-3202`) — no recursion.

Verification: all 166 Phase-9-relevant GUI tests pass under the pinned
interpreter (`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`):
35 (strip/side-panel/edit-section/masker) + 131 (canvas/crop/curves/
detection-settings/detection-boxes/tooltip).

One real defect found — a packaging bug in `pyproject.toml` that predates the
phase but which this phase's icon-packaging change builds directly on top of
(see WR-01). Three minor info-level items.

## Warnings

### WR-01: Installed package omits every `manga_ai_studio` subpackage — `pip install .` produces a non-functional app

**File:** `pyproject.toml:49-56`
**Issue:** `[tool.setuptools] packages = ["manga_ai_studio", "panelcleaner"]`
is a STATIC list that includes only the two top-level package directories.
`manga_ai_studio.gui`, `.core`, `.adapters`, and `.config` are NOT listed (and
there is no `setup.py`/`setup.cfg` or `packages.find:` fallback), so a wheel
or editable install ships none of the GUI/core modules. The declared console
script `manga-ai-studio = "manga_ai_studio.__main__:main"` would crash at
import time on any pip-installed copy. This phase added
`package-data manga_ai_studio = ["gui/assets/icons/*.svg"]` (line 52-56) to
"keep the assets directory out of a silent drop in any future packaging pass"
— but the packaging pass it guards against is already broken one level up:
the `.py` modules those icons serve never install either. The dev workflow
(`start.bat` running from source) masks this completely, which is presumably
why 1018 green tests never surfaced it.
**Fix:** Replace the static list with a finder (or enumerate explicitly):

```toml
[tool.setuptools.packages.find]
include = ["manga_ai_studio*", "panelcleaner*"]
```

If pip distribution is NOT intended for this project, demote by recording
that decision here — but then the line 54-56 comment's premise ("keeps the
assets directory out of a silent drop in any future packaging pass") should be
corrected, because the pass would drop far more than the assets.

## Info

### IN-01: Stale comment names the wrong Inpaint combo display strings

**File:** `manga_ai_studio/gui/inspector_panel.py:311-314`
**Issue:** The comment above `inpaint_override_changed` says the signal
"carries the display text \"Auto\"/\"Always\"/\"Never\"", but the actual item
set is `["Auto", "Fill", "Inpaint", "Never"]` (lines 191-193) and the model
map at `main_window.py:3906` keys off `"Inpaint"` (→ `"always"`), not
`"Always"`. The code is correct and self-consistent; only the comment drifts,
and it misdirects a future reader grepping for the committed vocabulary.
**Fix:** Update the comment to `"Auto"/"Fill"/"Inpaint"/"Never"` (the display
label is Inpaint, not Always — as the `_INPAINT_DISPLAY` comment at lines
187-190 itself states).

### IN-02: Three hand-copied slider↔spinbox blockSignals mirror pairs

**File:** `manga_ai_studio/gui/tools_panel.py:139-152, 147-152, 351-361`
**Issue:** The blockSignals-mirror-then-emit pattern now exists three times
(`BrushBody._on_slider_changed`/`_on_spinbox_changed`,
`DetectionSettingsBody._on_dilation_slider_changed`/`_on_dilation_spinbox_changed`,
plus the blocked-write variants `set_brush_size` / inside
`set_masker_values`). Each copy is individually correct (verified: restore of
the prior block state, exactly one emission), but the pattern is
copy-propagation-prone — a future fourth pair that forgets either the
block-restore or the emit-once discipline reintroduces the recursion bug the
pattern exists to prevent.
**Fix:** Extract a tiny helper, e.g.
`_mirror(src_widget, dst_setter, value)` or a `_SyncedPair(QSlider, QSpinBox)`
widget owning the two handlers, and reuse it in both bodies.

### IN-03: `set_masker_values` can leave displayed value diverged from persisted profile for out-of-range INI values

**File:** `manga_ai_studio/gui/tools_panel.py:410-419`
**Issue:** If a hand-edited/profile-merged INI carries an out-of-range value
(e.g. `mask_dilation_radius = 20` against the widget range 0..10), the load
path clamps the widget to 10 but does NOT write the clamp back to
`profile.masker` — the UI shows 10 while detection actually applies 20 until
the user next moves the control (which then commits 10). The docstring claims
values are "range-clamped at the widget level (T-08-09: invalid values are
unreachable)", but clamping at the widget makes them invisible, not
unreachable. Low impact (requires a manually corrupted INI) but it silently
contradicts the live-re-dilate contract: the applied radius differs from the
displayed one.
**Fix:** After population, read back each clamped widget value and reconcile
the profile field (`profile.masker.mask_dilation_radius =
self.dilation_slider.value()`), or log a warning when
`setValue`-clamp changes the value.

---

_Not flagged (checked and cleared):_ SVG stroke color hardcoded to `#e8e8ea`
(dark-only app by spec, asserted by `test_strip_icon_assets_art_direction`);
hex tokens repeated across per-widget QSS strings instead of referencing
`theme.py` constants (established codebase convention, cosmetic only);
`action_toggle_sidebar.triggered → toggleViewAction().trigger` signal-to-signal
bool forwarding (benign, documented G-05-1 audit precedent);
`test_collapse_round_trips_through_qsettings` relying on Qt INI bool type
preservation (verified passing on PySide6 6.7).

_Reviewed: 2026-08-21T00:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_

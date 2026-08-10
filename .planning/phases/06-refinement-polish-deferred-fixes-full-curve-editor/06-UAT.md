---
status: complete
phase: 06-refinement-polish-deferred-fixes-full-curve-editor
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md, 06-05-SUMMARY.md, 06-06-SUMMARY.md, 06-07-SUMMARY.md, 06-08-SUMMARY.md]
started: 2026-08-09T22:50:48Z
updated: 2026-08-09T23:24:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Confirm auto-covered deliverables (31 automated checks)
expected: All 29 automated coverage entries (tests 13-41) are covered by passing tests (full suite 600 passed, 0 failed) — confirm you accept them as verified, or report anything you believe is not actually working.
result: pass

### 2. App launch + project open — empty state clears
expected: Fresh launch shows the empty state ("Open a single image or a folder of images to begin cleaning." with the 'File → Open Folder… (Ctrl+Shift+O) · or drag files here' hint). Open a project folder (Ctrl+Shift+O): the empty-state trio disappears and the first page renders; on a page with zero boxes the "add a box" hint is visible; with boxes it is not.
result: pass

### 3. Tools menu shows "Curves…" (Levels gone)
expected: Tools ▸ Image section shows a single "Curves…" entry (Alt+T placement unchanged). There is no "Levels…" action anywhere in the menus.
result: pass

### 4. Curves dialog opens at defaults
expected: Open Tools ▸ Curves…: dialog title "Curves"; preset row shows Linear/S-curve/Brighten/Darken; channel row shows RGB/R/G/B with RGB checked; black=0, white=255, gamma=1.00; In/Out rows at the selected point; the curve is a straight diagonal line; a luminance histogram renders above/below the grid.
result: pass

### 5. Curve interaction — add / drag / delete / keyboard
expected: Click inside the grid: a point appears at the clicked (input, output) and is selected. Drag it: it moves, x stays strictly between neighbors, y stays 0..255. Drag the left endpoint: only y changes (x stays 0). Double-click an interior point: it disappears; double-clicking an endpoint never deletes it. Select a point and press arrow keys: nudges ±1 (Shift=±10). Tab/Shift+Tab cycles the selection through all points.
result: pass

### 6. Live preview + Apply
expected: While the dialog is open, dragging a point updates the canvas image in-place (live preview of the composed curve). Click Apply: the curve is committed — status flashes "Curves applied.", masks/boxes are untouched, and Ctrl+Z now undoes with exactly one step.
result: pass

### 7. Cancel restores exactly (fresh-page case)
expected: Open Curves on a freshly-loaded page (no prior edits, no Show Original baseline), drag points so previews fire, then Cancel: the canvas shows the pre-dialog image byte-identical, the undo stack is empty (Ctrl+Z does nothing), and pressing P / Show Original stays disabled — no phantom baseline was captured.
result: pass

### 8. Undo/redo flash labels
expected: After a Curves Apply, press Ctrl+Z: the image restores to the pre-dialog state and the status flashes "Undo: curves" (not "Undo: inpaint"). Ctrl+Shift+Z re-applies and flashes "Redo: curves".
result: pass

### 9. Presets + channel independence
expected: Click "S-curve": the curve becomes the S shape (0,0)-(64,40)-(192,215)-(255,255) and stays fully draggable afterwards. Click "Linear": back to the diagonal. Switch to channel R, edit the curve; switch to G, edit; switch back to R: the R edits are intact. The preview composes master then per-channel (R/G/B changes only affect their plane).
result: pass

### 10. Black/white/gamma quick rows
expected: Drag the black slider: the curve's left endpoint y follows and the white slider cannot go below black+1 (and vice versa — no inverted curve). Change gamma from 1.00 to 2.00: a midpoint anchor appears at input 128 and the curve bends accordingly; dragging the midpoint back-maps the gamma value in the spinbox.
result: pass

### 11. Dock/toolbar active-tool sync
expected: Click each tool in the Tools dock (Brush, Rectangle, Lasso, Eraser, Crop): the dock button stays highlighted, the toolbar button mirrors it, and the status shows the active tool; exactly one tool is highlighted at all times. Click the same dock button twice in a row: highlight stays correct on the second click too. Shortcut keys (V/B/R/L/E/G) still switch tools with both surfaces in sync.
result: pass

### 12. Drag fluidity + DPI legibility (human backstop)
expected: In the Curves dialog, drag a point and release: the drag tracks the cursor smoothly (no lag/stutter), preview updates feel live. Then check at 150% and 200% Windows DPI scaling: the 64/16 gridlines, diagonal, 2px accent curve, and 8x8/10x10 point handles remain legible and correctly scaled.
result: pass

---

Auto-covered deliverables (recorded as automated passes, not presented individually):

### 13. [coverage] 06-01 curve_lut math
expected: curve_lut: points -> 256-entry uint8 LUT; identity for Linear, monotone S-curve, degenerate-input backstop (no NaN/out-of-range), duplicate-x last-wins
result: pass
source: automated
coverage_id: D1

### 14. [coverage] 06-01 curves_page composition
expected: curves_page: (H,W,3) uint8 validation, master-then-channel composition (A1), channel independence, byte-exact LUT apply, detached .copy()
result: pass
source: automated
coverage_id: D2

### 15. [coverage] 06-02 empty-state overlay fix
expected: D-09 — empty-state overlay (heading/body/hint trio, z=2000) never persists over a loaded page on the numpy display path; empty-box hint (z=850) shows on zero-box pages
result: pass
source: automated
coverage_id: D1

### 16. [coverage] 06-02 hint copy fix
expected: D-11 — first-run hint copy is 'File → Open Folder… (Ctrl+Shift+O) · or drag files here' (exact, incl. 3-space padding); 'Ctrl+O' absent from canvas.py; body/heading copy untouched
result: pass
source: automated
coverage_id: D2

### 17. [coverage] 06-03 toolbar highlight
expected: Toolbar tool buttons highlight the active tool in sync with the dock across all entry paths (programmatic set_active_tool, V/B/R/L/E/G shortcuts, Tools-menu triggers)
result: pass
source: automated
coverage_id: D1

### 18. [coverage] 06-03 dialog typography 14px
expected: CropDialog, ResizeDialog and LoadTranslationsDialog field values and labels render at 14px Body (QFontInfo pixelSize == 14); LoadTranslations paste area keeps its Consolas 10 mono exception
result: pass
source: automated
coverage_id: D2

### 19. [coverage] 06-04 CurveWidget D-04 interaction
expected: CurveWidget D-04 interaction — click-add (last-wins on occupied x), drag clamps (x strictly between neighbors, y 0..255, endpoints y-only), double-click-delete (never endpoints), 10px hit radius, 280x240 minimum
result: pass
source: automated
coverage_id: D1

### 20. [coverage] 06-04 CurveWidget D-07 keyboard
expected: CurveWidget D-07 keyboard story — arrows nudge ±1 (Shift=±10), Tab/Shift+Tab cycle selection, StrongFocus
result: pass
source: automated
coverage_id: D2

### 21. [coverage] 06-04 CurveWidget paint
expected: CurveWidget paint — grid 64/16, muted diagonal, faint histogram bars (0.14 alpha), accent 2px curve, 8x8/10x10 handles; paint smoke with and without a histogram
result: pass
source: automated
coverage_id: D3

### 22. [coverage] 06-04 CurvesDialog defaults + 14px
expected: CurvesDialog defaults + D-12 typography — 0/255/1.00, Linear (0 interior points), RGB, In/Out at the selected point, 14px Body from birth
result: pass
source: automated
coverage_id: D4

### 23. [coverage] 06-04 bidirectional sync D-02/D-03
expected: Bidirectional sync D-02/D-03 — black/white rows drive the endpoints with the white>black cross-clamp (on sliders AND curve state), gamma 1.00↔midpoint 128 with back-map and forward injection, In/Out spins drive the selected point with neighbor-respecting ranges
result: pass
source: automated
coverage_id: D5

### 24. [coverage] 06-04 collector contract
expected: Collector contract — Apply stores detached (master, channel_points) result_values; Cancel/reject never stores; preview fires on every control change with the composed payload
result: pass
source: automated
coverage_id: D6

### 25. [coverage] 06-04 presets + channel switcher
expected: Presets D-05 + channel switcher D-06 — A2 coordinates replace the current channel's points and stay editable; Linear restores the diagonal; per-channel edits preserved across switches; verbatim UI-SPEC copy
result: pass
source: automated
coverage_id: D7

### 26. [coverage] 06-04 histogram once-at-open
expected: Histogram D-08 computed ONCE at open (luminance master, plane per channel) — array identity unchanged after editing; widget histogram follows channel switches
result: pass
source: automated
coverage_id: D8

### 27. [coverage] 06-04 preview composition driver
expected: Preview composition driver — _refresh is the single preview_callback call site; payload is byte-exact image_ops.curves_page output (A1 master→channel)
result: pass
source: automated
coverage_id: D9

### 28. [coverage] 06-05 Curves… menu surface
expected: Tools ▸ Image menu surface shows 'Curves…' (D-01 rename) — action_curves with the UI-SPEC tooltip, action_levels gone
result: pass
source: automated
coverage_id: D1

### 29. [coverage] 06-05 apply one undo entry
expected: Apply commits ONE image-only undo entry via _apply_geometry_op('curves', geometry=False, ...) with 'Curves applied.' flash; masks/boxes untouched; geometry_altered False; Show Original re-baselines (D-14)
result: pass
source: automated
coverage_id: D2

### 30. [coverage] 06-05 Cancel restores exactly
expected: Cancel restores the pre-dialog image byte-identical with zero undo entries and no flash
result: pass
source: automated
coverage_id: D3

### 31. [coverage] 06-05 b376f8a restore-before-Apply
expected: b376f8a restore-before-Apply ordering preserved — Ctrl+Z after Apply restores the true pre-dialog image byte-identical and leaves the stack empty
result: pass
source: automated
coverage_id: D4

### 32. [coverage] 06-05 no baseline poison
expected: Show Original never re-baselined by live previews mid-dialog; Cancel leaves _original_image_numpy == pre-dialog image
result: pass
source: automated
coverage_id: D5

### 33. [coverage] 06-05 undo flash op-name set
expected: Undo/redo flash op-name set is ('rotate', 'crop', 'curves', 'resize') — 'levels' replaced, not appended
result: pass
source: automated
coverage_id: D6

### 34. [coverage] 06-05 levels_dialog retired
expected: levels_dialog.py deleted; zero stale levels_dialog/LevelsDialog/_on_levels/action_levels references in manga_ai_studio/ + tests/; levels_lut/levels_page math + tests kept
result: pass
source: automated
coverage_id: D7

### 35. [coverage] 06-05 defaults/clamp contract
expected: Migrated defaults/clamp contract — dialog opens at 0/255/1.00 with the white>black cross-clamp and never previews an inverted curve
result: pass
source: automated
coverage_id: D8

### 36. [coverage] 06-06 CR-01 closed (baseline poison)
expected: CR-01 closed — fresh-page Curves open→preview→Cancel restores byte-identical with no baseline captured and no inpaint-result claim; Show Original (P) stays disabled
result: pass
source: automated
coverage_id: D1

### 37. [coverage] 06-06 apply pre-restore hardened
expected: Apply pre-restore hardened — capture-suppressed, b376f8a restore-before-Apply ordering intact, D-14 re-baseline preserved via _apply_geometry_op tail; one undo entry, Ctrl+Z restores the true pre-dialog image
result: pass
source: automated
coverage_id: D2

### 38. [coverage] 06-07 WR-01 closed (undo flash)
expected: WR-01 closed — after a curves Apply, Ctrl+Z flashes 'Undo: curves' and Ctrl+Shift+Z flashes 'Redo: curves' with a byte-exact post-op restore
result: pass
source: automated
coverage_id: D1

### 39. [coverage] 06-07 inpaint-label scoping guard
expected: Scoping guard — a non-origin bbox image entry (real push_image_action) undos as 'Undo: inpaint' even while _last_geometry_op_name == 'curves' (stale); the superseded op-name set is intact, 'levels' only in the historical comment
result: pass
source: automated
coverage_id: D2

### 40. [coverage] 06-08 WR-02 closed (dock/toolbar sync)
expected: WR-02 closed — dock tool-button clicks (two consecutive) sync the dock panel action, tools_panel.active_tool(), the window action, and the toolbar button; exactly one tool checked everywhere
result: pass
source: automated
coverage_id: D1

### 41. [coverage] 06-08 docstring truth
expected: Docstring truth — _make_tool_toolbar_button names the standalone checkable-action mechanism driven by set_active_tool's explicit sync; no stale group-membership claim anywhere in main_window.py
result: pass
source: automated
coverage_id: D2

## Summary

total: 41
passed: 41
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]

## Deferred Follow-Ups

- test: 3
  idea: "Consider adding Curves (and possibly other tools) to the sidebar — user plans a later phase to revamp the sidebar a bit."
  deferred_at: 2026-08-09

---
status: investigating
trigger: "Diagnose five gaps in Manga AI Studio PySide6 app, Phase 7 typesetting. Do NOT fix — diagnose only. Gaps: A (G-07-1 vertical/Latin rotation), B (G-07-5 align_v no effect horizontal), C (G-07-4 auto-fit shrink-only), D (G-07-7 Mixed align V multi-select override), E (G-07-3 no selectable default font)"
created: 2026-08-11
updated: 2026-08-11
---

## Current Focus

hypothesis: CONFIRMED — all five gaps located. Writing final diagnosis.
test: (complete — code reading + test reading)
expecting: deliver ROOT CAUSE / ARTIFACTS / MISSING / AFFECTED TESTS
next_action: return final structured diagnosis (diagnose-only mode — no fix)

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected:
  A: horizontal-by-default for all boxes; explicit vertical → upright-stacked Roman
  B: align_v (top/center/bottom) shifts horizontal text vertically
  C: auto-fit grows text to fill box (not just shrink to tiny)
  D: multi-select Mixed align V can be overridden to a new value
  E: app-level default font selectable and applied to new boxes
actual:
  A: detected-vertical (payload.vertical) renders vertical by default; Latin rotated 90°
  B: horizontal text always top-aligned regardless of align_v
  C: auto-fit renders tiny text in large boxes (shrink-only loop)
  D: choosing new align V on Mixed selection does nothing (stays Mixed)
  E: no selectable app-level default font for new boxes
errors: (none reported)
reproduction:
  A: OCR box with vertical metadata → renders tategaki by default; enable vertical → Latin rotated
  B: set align_v=center/bottom on horizontal text → no change
  C: auto-fit on, large box → tiny text
  D: multi-select boxes with different align_v → "Mixed", pick value → stays Mixed
  E: create new box → font is hardcoded default, no app setting
started: Phase 7 features

## Eliminated
<!-- APPEND only - prevents re-investigating -->

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-08-11
  checked: text_renderer.py full read (993 lines)
  found: char_rotates (136-146) rotates halfwidth ASCII 0x21..0x7E + _ROTATE_EXTRA; bake vertical = style.vertical OR payload.vertical (981-988); horizontal layout computes align_v dy into origin.y (560-565, 580-583) — the RENDERER is align_v-correct; auto-fit loop (547-556) is shrink-only: base = 14*min(box)/100 clamped [10,28], 12 iters x0.9, 5px floor; _vertical_fit_size (463-486) same shrink-only shape.
  implication: Renderer dy logic is fine — Gap B must live in the overlay; shrink-only loop confirmed for Gap C; OR expression confirmed for Gap A.

- timestamp: 2026-08-11
  checked: box_item.py full read (866 lines)
  found: refresh_text_overlay (649-687) vertical = style.vertical OR payload.vertical (673-680) — the D-13 expression; TypesetOverlayItem.set_content (351-396) cancels result.origin fully (-origin.x - ink.left + pad, -origin.y - ink.top + pad at 388-391) and re-derives position from DOC-LOCAL ink (395: _ink_offset = ink - pad; refresh_position 405-408: box + inset + ink_offset). The align_v dy rides ONLY result.origin.y → CANCELED → horizontal text always at box top on canvas. Vertical mode is unaffected (dy_block is baked into placement y → inside ink).
  implication: Gap B root cause = overlay origin-cancel drops dy. Canvas ≠ bake for align_v≠top; tests only exercise align_v="top" (dy=0) so the D-01 equivalence tests miss it.

- timestamp: 2026-08-11
  checked: inspector_panel.py full read (1262 lines)
  found: load_multi_selection align combos REPLACE items with ["Mixed"] only (677-679 align_h, 686-688 align_v via _select_combo 870-877); _emit_style_align_if_changed (1163-1169) returns when h or v == "Mixed"; signal is a PAIR (h,v) — style_align_changed (line 282); MainWindow._on_inspector_style_align_committed (3129-3132) applies BOTH h and v — no per-axis preservation. Contrast WR-02 effect pattern: _effect_payload "enabled": None sentinel (1210-1242) + _replace_effect per-box preserve (main_window 3033-3057) + spin keeps REAL range with only special-value text "Mixed" (844-850). Font combo works because QFontComboBox keeps real items.
  implication: Gap D = sentinel replaced the selectable items AND commit guard returns on Mixed AND consumer cannot preserve the untouched axis. No test locks align-Mixed override (coverage gap). Sibling finding: style_combo (624) has the same item-replacement issue.

- timestamp: 2026-08-11
  checked: text_style.py, box_model.py, canvas.py, main_window.py, project_io.py
  found: TextStyle() hardcodes font_family="Liberation Sans" (text_style.py:32, 131); new user boxes PageBox(origin=USER, payload=None) — no style (canvas.py:2104-2108); detected boxes PageBox(origin=DETECTED, payload=blk) — no style (main_window.py:3903-3905); QSettings (_QSETTINGS_ORG/_QSETTINGS_APP main_window.py:101-102, _settings() 1873-1876) used ONLY for recentFiles/recentProjects — NO default-font key anywhere; OCR detector sets blk.vertical (panelcleaner/textblock.py:360) carried as payload; payload.vertical written by _on_inspector_vertical_committed (main_window.py:3255) + persisted (project_io.py:201,262) + exported (ocr_export.py:177).
  implication: Gap E confirmed — no app-level default font exists; QSettings is the established Phase 5/6 convention to follow.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause:
  A: (1) D-13 OR expression auto-flips to vertical on payload.vertical — box_item.py:673-680, text_renderer.py:981-988, main_window.py:3069-3076. (2) char_rotates (text_renderer.py:112,136-146) rotates halfwidth ASCII per W3C — user overrides to upright-stacked.
  B: TypesetOverlayItem.set_content cancels result.origin (box_item.py:388-391) — the align_v dy (text_renderer.py:560-565) rides origin.y only → dropped on canvas; bake applies it.
  C: Auto-fit loop is shrink-only (text_renderer.py:547-556) — starts at the [10,28]-clamped base, never grows; large box + short text = tiny (≤28px).
  D: load_multi_selection replaces align combo items with ["Mixed"] (inspector_panel.py:686-688) — no real value selectable; _emit_style_align_if_changed returns on Mixed (1163-1169); pair-signal applies both axes blindly (main_window.py:3129-3132). Missing the WR-02 sentinel→override pattern.
  E: No app-level default font — TextStyle() hardcodes Liberation Sans (text_style.py:32); new-box creation passes no style (canvas.py:2104-2108, main_window.py:3903-3905); QSettings has no font key.
fix: (diagnose only — directions in the report)
verification: (diagnose only)
files_changed: (none — diagnose only)

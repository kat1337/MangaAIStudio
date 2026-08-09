# Phase 5 — UI Review (Project Persistence, Image Ops & Export)

**Audited:** 2026-08-09
**Baseline:** `05-UI-SPEC.md` (approved 2026-08-08, checker 6/6 PASS) + inherited Phase 1/3/4 contracts
**Screenshots:** not captured — PySide6 desktop app, no dev server (code-only audit of `manga_ai_studio/gui/*` + `core/image_file.py`)
**Audit method:** static read of every Phase 5 surface (21–29 + menu/status extensions), string audit against the §Copywriting table, token audit against §Color, spacing audit against the inherited scale + declared exceptions, state-machine review of the crop tool and dialogs
**Registry gate:** N/A — no `components.json` (Qt desktop app; UI-SPEC §Registry Safety verified no third-party registries; PySide6 via pip LGPL + Python stdlib `lzma`/`json`/`hashlib` approved)

---

## Pillar Scores

| Pillar | Score | Verdict | Key Finding |
|--------|-------|---------|-------------|
| 1. Consistency | 2/4 | **FLAG** | Ctrl+O remap left the empty-state hint advertising the old binding (canvas.py:278); toolbar active-tool highlight never renders while its comment claims it does |
| 2. Layout/Spacing | 4/4 | PASS | All declared spacing exceptions (8×8 min, 2px border, 0.45 dim, 1px moat, ±0.01 gamma step) implemented exactly; 8px/4px rhythm matches scale |
| 3. Typography | 3/4 | FLAG | Dialog field values ship at Qt default ~12px, not the contracted 14px Body; consistent with the inherited baseline pattern but a letter-of-contract miss |
| 4. Color | 4/4 | PASS | Zero new tokens outside the contract; crop dim `rgba(0,0,0,0.45)` exact; accent confined to the declared six reserved uses |
| 5. Feedback/Copy | 2/4 | **FLAG** | Levels Apply pushes a no-op undo record (Ctrl+Z cannot restore after a real preview); deferred empty-state overlay bug confirmed at its root cause |
| 6. Accessibility | 3/4 | FLAG | Shortcut/menu coverage is complete and contrast is token-verified, but toolbar gives no active-tool indication and the empty-state hint states the wrong shortcut |

**Overall: 18/24**

---

## Top 3 Priority Fixes

1. **Levels Apply records a no-op undo entry** (`main_window.py:1139` + `:1243-1266`) — the pre-image is captured from the *preview-mutated* canvas, so the pushed before-state equals the after-state and Ctrl+Z does nothing after a real Levels adjustment. Contract surfaces 25/28 violation ("one Ctrl+Z restores the pre-op image"). Fix: restore the detached `base` to the canvas before `_apply_geometry_op` runs (the Cancel path already does exactly this at `:1257`), or thread `pre_image=base` into the op. Add a restore-semantics assertion to `test_levels_apply_pushes_one_entry` (it currently asserts count only).
2. **Empty-state overlay persists after opening a project** (`canvas.py:710-767` `_set_image_from_numpy` never calls `_update_empty_state()`) — the "No page open" heading/body/hint (z=2000) stay rendered on top of the loaded page. Fix is one line: call `self._update_empty_state()` at the end of `_set_image_from_numpy`. **Disposition: FLAG — deferred to the refinement phase per user decision (UAT deferred follow-up, 2026-08-08).** Reopen with the one-line fix when refinement runs.
3. **Toolbar never indicates the active tool** (`main_window.py:3098-3110`, `:3125-3130`) — the six window tool actions are not checkable and not members of the panel's `QActionGroup`, so `QToolButton.setChecked` is a no-op and the accent active-tool highlight (reserved use #1) renders only in the dock panel; the comment at `:3101-3103` claims group membership that does not exist. Fix (logged in `deferred-items.md`): make the window tool actions checkable and add them to the panel's exclusive group, or bind the toolbar buttons to the panel's actions.

---

## Detailed Findings

### Pillar 1: Consistency (2/4) — FLAG

**FLAG — Empty-state hint contradicts the phase's own shortcut remap.** `canvas.py:278` renders `"File → Open Image… (Ctrl+O) · or drag files here"` on the first-run screen, but D-07 re-bound Ctrl+O to Open Project… (verified: exactly one `Ctrl+O` binding exists, `main_window.py:311`, and the Open Image action correctly lost its shortcut at `:300-301`). The phase changed the shortcut but left the canvas's most visible instructional copy advertising the old one. New users pressing Ctrl+O get a project dialog, not an image picker. Fix: drop the shortcut from the hint or reference Open Folder (Ctrl+Shift+O).

**FLAG — Toolbar vs dock active-tool state diverges.** `_make_tool_toolbar_button` (`main_window.py:3098-3110`) sets `btn.setCheckable(True)` and the comment claims the buttons "share the ToolsPanel's QActionGroup"; in fact the window tool actions (`main_window.py:710-753`) are plain non-checkable QActions outside the panel's group, and `set_active_tool`'s `btn.setChecked(True)` (`:3129`) is silently forwarded to a non-checkable action — a no-op. The 6th tool (Crop) was added into this broken mechanism (`:869`). The panel highlight works; the toolbar highlight never has. Probe-confirmed in plan 05-07, logged to `deferred-items.md`, unfixed.

**Minor — sibling-menu empty-state voice mismatch.** Recent Projects uses the contracted `"No recent projects yet."` (`main_window.py:2475`) while its sibling Recent Files uses `"(empty)"` (`:1768`). Both are disabled placeholders; the copy styles diverge between two adjacent submenus (files side inherited from Phase 1).

**Minor — tooltip wording drift from the contract.** Levels tooltip (`:795`) reads "Adjust the black/white points and gamma with a live preview." vs the contracted "Adjust black point, white point, and gamma with live preview."; Resize (`:802`) adds "an aspect-ratio lock" vs "aspect lock". Semantically equivalent, copy-verbatim not honored.

**PASS — structural consistency is strong:** all three dialogs follow the `_DIALOG_QSS` pattern with identical tokens and `[Cancel] [Apply]` (Apply default); menu placement matches surface 21/24a/24b/27 exactly (verified Edit `Crop…` between undo pair and Clear Mask at `:479-484`; Text `Export OCR JSON…` after Load Translations at `:673-674`; Batch export after the three batch actions at `:404-424`; Tools Image section at `:813-827`); undo-flash op names (`rotate|crop|levels|resize`, `:2880`) match the status-flash vocabulary.

### Pillar 2: Layout/Spacing (4/4) — PASS

- **Declared exceptions — all exact:** 8×8 scene-px crop minimum reuses `MIN_BOX_SIZE` (`canvas.py:92`, enforced at `:1319`, `:1340-1342`, `:1406-1411`); 2px cyan dashed crop border via the inherited `preview_item` pen (`:205-208`); dim-out `rgba(0,0,0,0.45)` (`:113`, `:1378`); 1px moat inset with page-clamping so nothing dims outside the page (`:1353-1388`, the 05-07 clamp fix); gamma singleStep ±0.01 (`levels_dialog.py:143`); rotation restricted to 90°/180° steps (`main_window.py:1190-1225`).
- **Z-order contract honored:** dim at 880 below preview border at 900 (`canvas.py:112`, `:1379`), above boxes at 100; empty-state text stays at 2000.
- **Scale compliance:** dialogs `setSpacing(8)` (sm) with form rows; ToolsPanel 8px margins/8px spacing/4px xs gaps (`tools_panel.py:101-102,154,180`); empty-state 48px (2xl) stacking (`canvas.py:1568-1575`); 3px determinate progress bar (`main_window.py:923`).
- **Nit (inherited):** dialog contents margins are the QVBoxLayout style default (~9-11px on Fusion), not the contracted 16px `md` — true of the `load_translations_dialog.py` baseline the contract anchors on, so consistent, but the literal token is never set. No action required unless the pattern is tightened.
- **Nit:** `_show_crop_dim` recomputes the full 4-rect set on every mouse-move (`canvas.py:1360` clears + rebuilds). Constant item count (T-05-18) is preserved; cost is acceptable.

### Pillar 3: Typography (3/4) — FLAG

- **In scope:** no new sizes or weights introduced; no display/hero sizes; weights stay Regular/Semibold; mono roles unchanged (Consolas 10pt status center `main_window.py:900`, paste area `load_translations_dialog.py:120`); Recent Projects entries are menu-default 12px matching the Small role; the empty-state hierarchy (heading 13pt DemiBold ≈ 17px/600, body 11pt ≈ 15px, hint 10pt ≈ 12px, `canvas.py:285-292`) is close to the 16/14/12 contract (inherited).
- **FLAG (letter-of-contract):** the contracted Body 14px for "dialog field values, labels" is not implemented — the Levels/Resize/Crop dialogs leave labels and values at the Qt default (~12px). This is inherited-baseline behavior (LoadTranslationsDialog does the same) and the contract's own pattern row anchors on that baseline, but the typography table's 14px Body row is unmet for all dialog chrome, including the new dialogs. If the baseline is tightened later, the three new dialogs inherit the fix for free (they set no explicit font).
- **Nit:** the resize "Result: {w} × {h} px" label correctly uses the muted Small role via `QLabel#resultLabel` (`resize_dialog.py:42,134`).

### Pillar 4: Color (4/4) — PASS

- **Token discipline verified by grep:** every hex in the new surfaces is a declared token (`#232328`, `#2d2d33`, `#3a3a42`, `#00d4ff`, `#e8e8ea`, `#9a9aa2`, `#7a1f1f`, `#0b0b0e`) plus the inherited hover variants `#34343c` (Phase 4 baseline, verified) and `#5a5a64` (present since Phase 1 `aec63bb`, verified in git). No new hardcoded colors were introduced.
- **The one new semantic color is exact:** crop dim-out `rgba(0,0,0,0.45)` matte black (`canvas.py:113`), not accent, not a bright surface — per the contract's only Phase 5 additive token.
- **Accent restraint honored:** crop preview reuses the inherited eraser/preview cyan pen `QColor(0,212,255,200)` ≈ `rgba(0,212,255,0.78)` (`canvas.py:206`, `:1878`); the dim-out overlay uses no accent; image-op/export menu actions use no accent; accent appears only on the inherited slider handles/fills (`levels_dialog.py:62-67`), `QPushButton:default` borders, combo selection (`resize_dialog.py:60-61`), and the panel checked-tool border — all pre-existing reserved uses.
- **Error/semantic surfaces:** error chip `#7a1f1f`/`#ffffff` (`main_window.py:915-917`), status-bar text `#e8e8ea`, canvas matte `#0b0b0e` (`canvas.py:301`) — unchanged.

### Pillar 5: Feedback/Copy (2/4) — FLAG

**FLAG — Levels undo is a no-op after a real control change (functional, D-14/surface 28 contract violation).** Trace: the live preview mutates the canvas via `set_image_from_numpy_preview` (`main_window.py:1250-1252`); on Apply, `_apply_geometry_op` captures `pre_image = self.canvas.get_image_numpy()` (`:1139`) — which is already the *post*-levels image (last preview == final values) — then pushes it as the before-state (`:1176-1180`). Ctrl+Z therefore restores the post-op image: nothing changes visually, and the entry is consumed. The user's only recovery path for Levels silently fails. `test_levels_apply_pushes_one_entry` (`tests/test_gui_image_dialogs.py:200-232`) asserts the push *count* (1) but never the restore semantics, and its fake `exec` fires no preview — which is why the defect shipped green. Fix: restore `base` to the canvas before applying (mirror `:1257`), or pass `pre_image=base`. Rotate/resize/crop are unaffected (no pre-apply canvas mutation on their paths).

**FLAG — deferred empty-state overlay bug, root-caused (see Top Fix 2).** The UAT-reported "no page open / no text boxes messages stay rendered after opening a project" is confirmed in code: `_set_image_from_numpy` (`canvas.py:710-767`) — the numpy display path used by `_display_page_state` on project load — never calls `_update_empty_state()`, so the z=2000 "No page open" trio remains visible over the first project page; the empty-box hint compounds it on zero-box pages. The `set_image_from_path` path (`:385-408` → `set_image` → `:383`) is unaffected, which is why only the project-open flow exhibits it. **Disposition: FLAG — deferred to the refinement phase per user decision (05-UAT.md deferred follow-up, 2026-08-08); one-line fix (call `_update_empty_state()` at the end of `_set_image_from_numpy`) when picked up.**

**FLAG — stale shortcut guidance in the empty-state hint** (`canvas.py:278`; full detail under Consistency) — wrong instruction copy on the first-run screen.

- **PASS — the §Copywriting table is otherwise honored verbatim:** all status flashes (`Rotated 90° CW.` `:1202`, `Cropped.`/`Cropped. {n} box(es)…` `:1395-1400`, `Levels applied.` `:1265`, `Resized to {w} × {h}.` `:1314`, `Saved project '{name}' ({n} pages).` `:2098-2100`, `Opened project…` + missing-original append `:2394-2399`, `No changes to save.` `:1982`, `Exported OCR JSON for page {n}.` `:4560`, batch `{done}/{total}` + mixed failure form `:4648,4665-4666,4681-4686`); error dialogs (`Couldn't open '{filename}'.` + corrupt/newer-version path `:2162-2167`; `Couldn't save '{name}'.` + writable-folder path `:2083-2087,4554-4558`); the Unsaved Changes gate with [Save][Discard][Cancel] `:2322-2347`; Chapter Detected with [Open Project] default / [Open Page Only] / Esc-cancels-via-hidden-button `:2182-2206`; `Show Original (P) — original file not found.` tooltip `:998-1000`; undo/redo op-name set `:2880`.
- **Minor:** the Unsaved Changes body substitutes `'this session'` when no project is open (`:2326`) — a sensible extension of the contracted copy, not a violation; batch/export actions expose their contract tooltips as statusTips rather than toolTips (`:414-417`, `:659-662`) — visible on menu hover, so acceptable Qt convention, but inconsistent with the dialog-opening actions' toolTips.

### Pillar 6: Accessibility (3/4) — FLAG

- **PASS — keyboard coverage is complete and conflict-free:** Ctrl+S / Ctrl+Shift+S / Ctrl+O (verified single binding) / Ctrl+Shift+E / G (window-level `QShortcut`, `main_window.py:2557-2566`) / crop Enter-Esc cycle (`canvas.py:1449-1496`) / menu accelerators on all six top menus; the numeric `Crop…` dialog closes the gesture's keyboard gap (surface 24a/24b); all three dialogs use `QFormLayout` labels + spinboxes (navigable); Esc priority order (inline editor → crop cancel → deselect → batch cancel) matches the contract.
- **PASS — contrast:** dialog text `#e8e8ea` on `#232328`/`#2d2d33` ≈ 10:1; muted `#9a9aa2` hints ≈ 4.6:1 — inherited token math, no new surfaces below it.
- **FLAG — no active-tool indication on the toolbar** (detail under Consistency): the accent active-tool highlight renders only in the dock; toolbar tool buttons never reflect the current tool, and the phase added the 6th tool to the same non-functional mechanism. Deferred per `deferred-items.md`; a future plan should also fix the false comment at `main_window.py:3101-3103`.
- **FLAG — wrong shortcut guidance:** the empty-state hint instructs Ctrl+O for Open Image (`canvas.py:278`).
- **Minor:** no explicit accent `:focus` outline QSS in the three new dialogs — Fusion's dotted focus rect + palette `Highlight = #00d4ff` (`theme.py:48`) applies, so the accent-focus contract (reserved use #3) is approximated but not the literal 2px accent outline; inherited baseline behavior across all dialogs.
- **Note (not a defect):** toolbar and dock tool buttons render text labels (TextOnly style), not icons — good for discoverability, consistent with the "no new icon assets" contract.

---

## Registry Safety

No third-party UI registries declared in UI-SPEC.md §Registry Safety (PySide6/Qt6 via pip, LGPL; Python stdlib `lzma`/`json`/`hashlib`; zero new dependencies — confirmed by all ten plan summaries). `components.json` does not exist. Registry audit: N/A — no `npx shadcn` operations, no third-party blocks to vet.

---

## Files Audited

- `manga_ai_studio/gui/main_window.py` (5159 lines — menus, gating, save/open session layer, chapter climb, image-op orchestration `_apply_geometry_op`, crop apply, OCR-JSON export single/batch, undo feedback)
- `manga_ai_studio/gui/canvas.py` (2007 lines — crop-tool state machine, dim-out overlay, empty-state handling, numpy display paths, key dispatch)
- `manga_ai_studio/gui/tools_panel.py` (298 lines — 6th tool, exclusivity fix, brush row)
- `manga_ai_studio/gui/levels_dialog.py` (247 lines)
- `manga_ai_studio/gui/resize_dialog.py` (243 lines)
- `manga_ai_studio/gui/crop_dialog.py` (173 lines)
- `manga_ai_studio/gui/load_translations_dialog.py` (192 lines — dialog QSS baseline)
- `manga_ai_studio/gui/theme.py` (68 lines — palette tokens)
- `manga_ai_studio/core/image_file.py` (167 lines — D-06/D-22/current_image slots)
- `tests/test_gui_image_dialogs.py` (levels/rotate/resize coverage review)
- `.planning/phases/05-project-persistence-image-ops-export/05-UAT.md` (deferred empty-state bug), `deferred-items.md` (toolbar highlight), 05-01…05-10-SUMMARY.md

---

*Audited: 2026-08-09 · Baseline: 05-UI-SPEC.md (approved) · Screenshots: none (desktop Qt app — code audit)*

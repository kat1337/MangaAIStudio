# Phase 6: Refinement & Polish — deferred fixes + full curve editor - Context

**Gathered:** 2026-08-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver **two** groups of work — a polish pass over Phase 5's deferred bugs, and the long-deferred full curve editor (PROJ-04's "curves" half):

1. **Deferred fixes (all root-caused and prescribed in Phase 5 docs, no REQ-IDs — tracked deferrals):**
   - **Empty-state overlay persists after project open** — `canvas.py:710-767` `_set_image_from_numpy` never calls `_update_empty_state()`, so the z=2000 "No page open" heading/body/hint trio stays rendered over the loaded page; the empty-box hint compounds it on zero-box pages. Prescribed fix: one line — call `self._update_empty_state()` at the end of `_set_image_from_numpy`. (05-UAT.md deferred follow-up 2026-08-08; 05-UI-REVIEW.md Top Fix 2.)
   - **Toolbar tool buttons never highlight the active tool** — the window's six tool actions (`action_tool_move/brush/rectangle/lasso/eraser/crop`, `main_window.py:710-753`) are NOT checkable and NOT members of the ToolsPanel's `QActionGroup`; `QToolButton.setChecked` on a non-checkable action is a no-op, so `set_active_tool`'s toolbar sync (`:3125-3130`) never highlights anything. The comment at `_make_tool_toolbar_button` (`:3098-3110`) claims group membership that does not exist. Prescribed fix: make the window tool actions checkable and add them to the panel's exclusive group (deferred-items.md 2026-08-08; 05-UI-REVIEW.md Top Fix 3).
   - **Stale Ctrl+O hint copy** — `canvas.py:278` renders `"File → Open Image… (Ctrl+O) · or drag files here"` on the first-run screen, but Phase 5 re-bound Ctrl+O to Open Project… (exactly one binding exists, `main_window.py:311`). The most visible instructional copy advertises the wrong shortcut. Fix direction: drop the shortcut from the hint or reference Open Folder (Ctrl+Shift+O). (05-UI-REVIEW.md Pillar 1/6 FLAG.)
   - **Dialog typography at Qt default ~12px, not contracted 14px Body** — Levels/Resize/Crop dialogs leave labels and field values at the Qt default; the UI-SPEC typography table's Body 14px row ("dialog field values, labels") is unmet. Inherited-baseline behavior (LoadTranslationsDialog does the same). (05-UI-REVIEW.md Pillar 3 FLAG.)

2. **Full draggable curve editor** (05-CONTEXT/05-DISCUSSION-LOG deferred idea; 05-CONTEXT D-12 shipped the Levels dialog as the v1 fallback). A draggable curve control for tones adjustment, replacing the Levels dialog's fixed black/white/gamma controls. Requirement: **PROJ-04** (curves). The curve editor is pixel-only and geometry-free (masks/boxes untouched — mirrors Phase 5 D-15), silent + IMAGE-stack undoable (D-14), Show Original re-baselines post-op (D-14).

**Explicitly NOT in scope:** typesetting styling toolbar (TRAN-02 → Phase 7, ROADMAP). The Levels no-op undo record FLAG is ALREADY FIXED (05-UI-REVIEW-FIX.md, commit b376f8a) — do not redo it.

</domain>

<decisions>
## Implementation Decisions

### Curves dialog structure (discussed — user-locked)
- **D-01:** **A single "Curves…" dialog replaces the Levels dialog.** The Tools-menu "Levels…" action is removed and renamed "Curves…"; its Alt+T Image-section slot and placement stay. **The black/white point sliders are KEPT as a quick-access row above the curve grid** (user chose "Curve dialog + point sliders" over full replacement or two coexisting dialogs). — **Reversibility:** reversible.
- **D-02:** **Bidirectional slider↔curve sync; the curve is the single source of truth.** Dragging the black/white sliders moves the curve's left/right endpoints; dragging curve points updates the sliders. No state can diverge. — **Reversibility:** reversible.
- **D-03:** **Gamma slider kept, synced to the curve's midpoint anchor.** The log-scaled gamma control (0.10…4.00, default 1.00) stays; gamma 1.00 = midpoint sitting on the diagonal. Dragging the curve's midpoint updates the gamma slider in return. — **Reversibility:** reversible.

### Curve interaction model (discussed — user-locked)
- **D-04:** **Arbitrary control points, Photoshop convention.** Click on the curve to add a point, drag to move it, double-click a point to delete it. The endpoints (0,0)/(255,255) are fixed — draggable only along their edge. — **Reversibility:** reversible.
- **D-05:** **Presets: Linear (reset) + a few one-click starting points** — S-curve (contrast), "Brighten", "Darken" — on a preset row/dropdown. Presets are fully editable after application (starting points, not locked templates). — **Reversibility:** reversible.
- **D-06:** **Master + per-channel (R/G/B) curves with a channel switcher.** The dialog edits the RGB master AND each channel independently; the preview composes the applied LUTs. — **Reversibility:** reversible.
- **D-07:** **Full keyboard story (app's keyboard-reachability contract):** numeric input/output spinboxes for the selected point (Photoshop convention) AND arrow-key nudge (1 unit, Shift = 10) with Tab/Shift+Tab point selection. — **Reversibility:** reversible.
- **D-08:** **Page luminance histogram behind the curve grid** — computed once from the detached page image at dialog open (cheap, `np.histogram`), rendered faintly behind the grid. — **Reversibility:** reversible.

### Deferred fixes (locked contracts — root cause and fix prescribed in Phase 5 docs)
- **D-09:** **Empty-state overlay fix = call `self._update_empty_state()` at the end of `_set_image_from_numpy`** (`canvas.py:710-767`). Covers both the "No page open" trio AND the empty-box hint (`_update_empty_state` already refreshes `_refresh_empty_box_hint`, `canvas.py:1545-1575`). A regression test on the project-open path is required (the `set_image_from_path` path already works — the numpy display path is the bug site). — **Reversibility:** one-way (fix closes the only defect; behavior contract = empty state never persists over a loaded page).
- **D-10:** **Toolbar active-tool highlight = make the window tool actions checkable and add them to the ToolsPanel's exclusive `QActionGroup`** (the deferred-items.md prescription). The toolbar buttons must highlight in sync with the dock panel — including when the tool changes via keyboard shortcut (V/B/R/L/E/G), the Tools menu, or programmatic `set_active_tool`. Exact wiring (share the panel's actions vs duplicate checkable actions in the group) is Claude's discretion — the false comment at `main_window.py:3101-3103` must be corrected or made true. — **Reversibility:** reversible.
- **D-11:** **Empty-state hint copy must not advertise the wrong shortcut** (`canvas.py:278`). Ctrl+O is Open Project… — the hint must either drop the shortcut or reference Open Folder (Ctrl+Shift+O). Exact wording is Claude's discretion (the body text "Open a single image or a folder of images to begin cleaning." stays). — **Reversibility:** reversible.
- **D-12:** **Dialog field values/labels at contracted 14px Body** (05-UI-REVIEW Pillar 3). Which dialogs are in scope (the three Phase-5 image-op dialogs only vs all dialogs incl. the inherited LoadTranslationsDialog baseline) is Claude's discretion — the 14px Body contract row is the acceptance truth. — **Reversibility:** reversible.

### Claude's Discretion
- **Hint copy wording** (D-11) and **typography scope** (D-12) — user chose not to discuss the fix areas; the planner/researcher decide against the UI-SPEC contract.
- **Toolbar mechanism exact wiring** (D-10) — checkable-action duplication vs binding toolbar buttons to the panel's actions; either satisfies the sync contract.
- **Curve widget implementation** — a custom `QPainter`-drawn widget (grid, diagonal, curve path, histogram, channel switcher, preset row). Curve→LUT math: sample each curve at 256 points → per-channel LUTs; master and per-channel composition order (e.g. per-channel LUT applied after master, or multiplicative on the sampled values — pick the least-surprising Photoshop-equivalent). Extend `core/image_ops.py` (`levels_lut` is the existing LUT builder; T-05-07's normalize/backstop discipline applies — a degenerate curve must never render an inverted map).
- **Dialog lifecycle contract** — the Curves dialog follows the existing Levels collector+preview-driver contract (Pitfall 9): never mutates models, `preview_callback` drives the capture-suppressed canvas preview, Cancel = silent exact restore, Apply = ONE image-only IMAGE-stack undo entry via `_apply_geometry_op`, Show Original re-baselines post-op (05-UI-REVIEW-FIX b376f8a already fixed the restore-before-Apply ordering — the Curves Apply path MUST preserve it).
- **Preset curve math** (S-curve/Brighten/Darken shapes), **histogram computation detail**, **channel-switcher UI form** (buttons vs dropdown), **numeric in/out widget layout**.
- **Per-channel LUT edge cases** — per-channel curves are applied to each channel; the master applies to all. The T-05-07-style cross-clamp/backstop thinking applies to slider↔endpoint sync (endpoints fixed at the edges, sliders can't invert past them).

### Folded Todos
None — no pending todos matched this phase (todo.match-phase returned 0 matches).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope
- `.planning/ROADMAP.md` §Phase 6 — **THE scope anchor.** Goal ("polished, consistent editor — deferred v1.1 bugs fixed … and a full draggable curve editor replacing the Levels dialog's fixed black/white/gamma controls"), inherited-deferral list with file:line root causes, requirement PROJ-04 (curves), "Explicitly NOT in scope: typesetting styling toolbar (TRAN-02 → Phase 7)", 0 plans, Depends on Phase 5.
- `.planning/REQUIREMENTS.md` — PROJ-04 ("basic image operations to a page: crop, rotate, levels/curves adjustment, resize" — already validated in Phase 5 via Levels; the curve editor is the full "curves" half).

### Deferral sources (MUST read — the fixes' root causes and prescriptions)
- `.planning/phases/05-project-persistence-image-ops-export/05-UAT.md` — deferred follow-up: empty-state overlay persists after project open ("no page open" + "no text boxes" messages stay rendered; should clear once the project's first page is displayed). Deferred 2026-08-08.
- `.planning/phases/05-project-persistence-image-ops-export/deferred-items.md` — toolbar tool-button highlight never functional: root cause (non-checkable window actions outside the panel's `QActionGroup`; `QToolButton.setChecked` no-op) + prescription (make checkable, join the exclusive group). Deferred 2026-08-08.
- `.planning/phases/05-project-persistence-image-ops-export/05-UI-REVIEW.md` — Pillar 3 typography FLAG (dialog field values at Qt default ~12px vs contracted 14px Body); Pillar 1/6 stale Ctrl+O hint FLAG (`canvas.py:278`); Top Fix 2 (empty-state root cause + one-line fix); Top Fix 3 (toolbar highlight root cause + fix); Minor: sibling-menu empty-state voice mismatch ("No recent projects yet." vs "(empty)").

### Prior Phase Context (the contract the curve editor inherits)
- `.planning/phases/05-project-persistence-image-ops-export/05-CONTEXT.md` — **D-12** (Levels dialog black/white/gamma with live preview was the v1 fallback; "The full curve editor is v2 (deferred)" — now lands here), **D-14** (all four image ops silent + IMAGE-stack undoable, Show Original re-baselines to post-op image), **D-15** (geometry ops transform mask+boxes; Levels is geometry-free — curve must be too), Deferred Ideas (curve editor entry). "Curves" is a Phase 5 PROJ-04 requirement; the deferred idea text names the curve editor as the Levels successor.
- `.planning/phases/05-project-persistence-image-ops-export/05-RESEARCH.md` — **Pitfall 9** (dialogs are collectors, push nothing), Pitfall 3 (Qt mutation only in main-thread handlers), the levels preview/apply path analysis, white>black cross-clamp mechanics (T-05-07).
- `.planning/phases/05-project-persistence-image-ops-export/05-UI-SPEC.md` — **typography table (Body 14px, "dialog field values, labels")**, **accent `#00d4ff` reserved use #1 (active-tool highlight)**, **keyboard-reachability contract** ("every Phase 5 action is keyboard-reachable"), surface 25 (Levels dialog contract — the Curves dialog supersedes it), surface 6 (tool active-state contract), dark-QSS/token conventions.
- `.planning/phases/05-project-persistence-image-ops-export/05-UI-REVIEW-FIX.md` — **the Levels no-op undo FLAG is FIXED** (b376f8a: restore detached `base` before `_apply_geometry_op`; extended `test_levels_apply_pushes_one_entry` with restore-semantics assertions). The Curves Apply path MUST preserve this ordering — do NOT regress it.
- `.planning/phases/04-ocr-recognition-text-editing/04-CONTEXT.md` / `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — inherited: Pitfall-2 `.copy()` buffer discipline, thread-safety contract T-01-07, 3-stack undo + unified timeline, "silent + undo recovers" (D-12 Phase 3), dialog QSS/collector patterns.

### Existing Code (the build surfaces)
- `manga_ai_studio/gui/levels_dialog.py` — **the dialog the Curves dialog evolves from**: collector + preview driver, white>black cross-clamp (`_refresh`, T-05-07), gamma log-slider mapping (`_gamma_to_slider`/`_slider_to_gamma`), `_DIALOG_QSS` dark styling, `result_values` contract, `preview_callback` wiring.
- `manga_ai_studio/gui/main_window.py` — `_on_levels` (preview path + restore-before-Apply + `_apply_geometry_op("levels", …)`), window tool actions (`:710-753`), `_make_tool_toolbar_button` (`:3098-3110`, false group-membership comment), `set_active_tool` (`:3125-3130`), `action_crop` (`:869`), Tools menu Image section (Alt+T).
- `manga_ai_studio/gui/canvas.py` — `_set_image_from_numpy` (`:710-767`, the empty-state bug site), `_update_empty_state` (`:1545-1575`), empty-state trio (`:273-293`, hint at `:278`), `_original_image_numpy` re-baseline, capture-suppressed preview path (used by `_on_levels`).
- `manga_ai_studio/core/image_ops.py` — `levels_lut` (the existing LUT builder + T-05-07 normalize backstop; the curve LUT lands alongside), geometry transforms.
- `manga_ai_studio/gui/tools_panel.py` — the `QActionGroup` + `_make_tool_action` pattern, `set_active_tool`/`active_tool` (the toolbar fix's integration point).
- `manga_ai_studio/gui/crop_dialog.py`, `manga_ai_studio/gui/resize_dialog.py`, `manga_ai_studio/gui/load_translations_dialog.py` — dialog typography scope (D-12).
- `tests/test_gui_image_dialogs.py` — `test_levels_apply_pushes_one_entry` (restore-semantics assertions), the dialog-test shape for the Curves dialog's RED-GREEN tests.

### Source References (PanelCleaner — GPL v3)
- `../PanelCleaner/LICENSE` — GPL v3. The Curves dialog, curve math, and all fixes are our own code (no new vendoring expected).

### External References (researcher must fetch)
- None required — the curve editor is greenfield Qt/QPainter + numpy LUT work (no new dependencies; stdlib `numpy` is already in the stack). The researcher may consult Photoshop-curves conventions for the preset shapes and channel-composition semantics.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`LevelsDialog`** (`gui/levels_dialog.py`) — the collector+preview-driver skeleton the Curves dialog extends: `preview_callback`, `result_values`, `_updating` guard, dark QSS block, Cancel/Apply buttons. The black/white/gamma control rows become the quick-access row (D-01/D-02/D-03).
- **`levels_lut`** (`core/image_ops.py`) — the LUT pipeline the curve LUT extends; T-05-07 normalize discipline is the model for curve sampling (256-point sample, degenerate-curve backstop).
- **`_on_levels` + `_apply_geometry_op`** (`main_window.py`) — the complete apply/undo/preview path the Curves dialog reuses verbatim (including the b376f8a restore-before-Apply ordering).
- **`ToolsPanel.tool_group`** (`gui/tools_panel.py`) — the exclusive `QActionGroup` the toolbar actions join (D-10).
- **`_update_empty_state`** (`canvas.py:1545`) — already refreshes the empty-box hint; the D-09 one-liner makes it run on the numpy display path.
- **`_make_tool_toolbar_button`** (`main_window.py:3098`) — the false-comment site that becomes the toolbar fix surface (D-10).
- **Histogram source** — the detached `page_image` numpy passed into the dialog at open (same detached copy the preview closure uses — Pitfall 2: `.copy()` before use).

### Established Patterns
- **Pitfall 9 (collector dialogs)** — the Curves dialog pushes nothing; Apply emits ONE image-only IMAGE-stack entry via `_apply_geometry_op`; Cancel silently restores the detached base.
- **D-14 (silent + undo recovers)** — no confirm dialogs; Ctrl+Z reverses the curve op; Show Original re-baselines post-op.
- **D-15 (geometry-free)** — the curve touches pixels only; masks and boxes are untouched by the op and its undo record.
- **T-05-07 backstop discipline** — no inverted map possible; slider↔endpoint sync (D-02) and gamma↔midpoint sync (D-03) must be clamps, not free ranges.
- **Pitfall 2 (`.copy()` discipline)** — the histogram is computed from a detached copy; the preview closure operates on the detached base.
- **Keyboard-reachability contract** — every control keyboard-usable; D-07 (numeric in/out + arrow nudge + Tab point selection) is the curve's story.
- **RED-GREEN test discipline** — the project's gap-closure cadence: regression tests on the real bug sites (empty-state test on the project-open numpy path, toolbar-sync test asserting toolbar button checked state, copy test asserting the hint text, typography test asserting the point size).

### Integration Points
- **Tools menu (Alt+T Image section)** — "Levels…" action renamed "Curves…" (D-01); the slot swaps the dialog class.
- **`main_window._on_levels`** — becomes `_on_curves` (or keeps the slot, swaps the dialog); the preview/apply/undo path is unchanged.
- **`main_window` toolbar** — `action_tool_*` checkable + group membership (D-10); `set_active_tool` toolbar sync becomes functional.
- **`canvas._set_image_from_numpy`** — D-09 one-liner; `canvas.py:278` hint copy (D-11).
- **`core/image_ops.py`** — new `curve_lut` (or equivalent) + per-channel composition beside `levels_lut`; unit-testable headless (pure numpy).
- **All dialogs** — 14px Body typography (D-12): `levels_dialog.py` (→ curves), `crop_dialog.py`, `resize_dialog.py`, `load_translations_dialog.py`.

</code_context>

<specifics>
## Specific Ideas

- **"Curve dialog + point sliders"** (user, D-01) — the user wants ONE dialog that keeps the familiar black/white/gamma quick controls while adding the full curve. The dialog is the Levels dialog's successor, not a sibling.
- **Photoshop conventions were the reference throughout** — arbitrary points, numeric in/out fields, per-channel curves, histogram behind the grid, presets as editable starting points (D-04…D-08). The curve behaves like a familiar photo-editor curve, not a novel widget.
- **Bidirectional sync, single source of truth** (D-02) — the user's mental model: sliders and curve are two views of one state; neither can diverge. Same for gamma↔midpoint (D-03).
- **Keyboard matters** (D-07) — the user accepted BOTH numeric fields and arrow nudge; the keyboard-reachability contract (05-UI-SPEC) is a real acceptance dimension in this project, not decoration.
- **Fix scope is pre-root-caused** — every deferred fix ships with its root cause and prescription in the deferral docs; the planner should treat the root causes as authoritative and the prescriptions as the expected solution shape (D-09…D-12).

</specifics>

<deferred>
## Deferred Ideas

- **Typesetting styling toolbar (TRAN-02)** — explicitly out of Phase 6 scope (ROADMAP §Phase 6; Phase 7 owns it). Font/style/size/color/alignment/effects for rendered translation text.
- **Sibling-menu empty-state voice mismatch** ("No recent projects yet." vs "(empty)", 05-UI-REVIEW Minor) — not in ROADMAP Phase 6 scope; a one-word polish if the typography/copy pass (D-11/D-12) naturally touches the Recent menus, otherwise a future phase.
- **Per-channel curve presets / user-saved curves** — not requested; the preset row (D-05) is fixed and built-in only.
- **Curve serialization in `.mas`** — rejected by Phase 5 D-05 (image ops are not serialized; the post-op image is saved). The curve is a transient edit like Levels.
- **Levels no-op undo record** — ALREADY FIXED (05-UI-REVIEW-FIX.md, b376f8a). Listed here to prevent re-doing it.

</deferred>

---

*Phase: 6-Refinement & Polish (deferred fixes + full curve editor)*
*Context gathered: 2026-08-09*

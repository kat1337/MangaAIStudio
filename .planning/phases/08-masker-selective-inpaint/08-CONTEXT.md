# Phase 8: Masker & Selective Inpaint - Context

**Gathered:** 2026-08-15
**Status:** Ready for planning — **decisions below are builder recommendations (auto-derived; see note), user should review before planning**

<domain>
## Phase Boundary

Deliver the "smart clean" capability — **MASK-01, MASK-02, MASK-03, MASK-05, MASK-06** — activating the deferred cleaning-track seams:

1. **MASK-01 mask dilation** — a detection-time configurable radius (px) that grows auto-detected text masks so letter edges the conservative CTD heatmap leaves unmasked get covered (the `01-UAT.md` deferral: "add a few pixels extra to each letter it detects"). Surfaced as a cleaning-profile parameter.
2. **MASK-02 selective per-box inpaint** — inpaint only the detected text masks *inside* boxes whose region is uniform enough (low std-deviation), preserving complex artwork instead of inpainting whole box regions. Activates the Phase 3 **D-15 seam**: populate `PageBox.mask` / `PageBox.std_dev` via the vendored `masker.py` machinery (`pick_best_mask` + `border_std_deviation` in `panelcleaner/image_ops.py`).
3. **MASK-03 per-box indicator + override** — the user can see per box whether it was selectively inpainted, and override the auto decision (force inpaint / skip).
4. **MASK-05 box-constrained inpainting** — on the selective clean path, only mask content inside text boxes is inpainted (PanelCleaner's box-driven cleaning model).
5. **MASK-06 paint-under-boxes** — when a paint tool is active, box items do not block brush strokes; regions overlapped by boxes can be masked.

**In scope (from ROADMAP §Phase 8):** the five requirements above; reused seams — cleaning/inpaint foundation (Phase 1), box model + masker vendoring (Phase 3), OCR box context (Phase 4), `.mas` persistence (Phase 5).

**Explicitly NOT in scope (ROADMAP):** interactive mask grow/shrink brush (**MASK-04** — v2), per-region LaMa params (**FLOW-07** — v2).

**The central insight:** the machinery already exists. Phase 3 vendored `panelcleaner/image_ops.py` + `masker.py` + `structures.py` precisely for this phase (D-14), and `PageBox.mask`/`std_dev` default to `None` as the open seam (D-15). Phase 8 wires the vendored per-box mask-fitting pipeline into a user-facing selective inpaint action, adds the detection-time dilation knob, and carves paint tools out of the box hit-test.

</domain>

<decisions>
## Implementation Decisions

> **⚠ Provenance note (2026-08-15):** the user dismissed the interactive area-selection prompt; per harness guidance the agent proceeded on best judgment, treating all four gray areas as selected and answering each from prior-phase contracts + PanelCleaner parity. **These are builder recommendations, not user-locked choices.** The user should review this file (especially D-01…D-10) and edit/override before `/gsd-plan-phase 8`. The two decisions ROADMAP explicitly deferred to this discussion (MASK-05 out-of-box behavior → D-02; MASK-06 dispatch → D-09/D-10) are marked.

### Selective inpaint entry & whole-page path (MASK-02 + MASK-05) — *auto-derived*

- **D-01:** **Additive — a NEW dedicated "Selective Inpaint" action; the existing whole-page Inpaint (C) action is unchanged.** Two cleaning paths coexist in the Tools menu: `Inpaint (C)` (Phase 1 whole-page LaMa over the full pixel mask — validated CLEAN-06 behavior, preserved) and the new selective action (box-constrained, std-deviation-gated). The selective action gates on boxes existing (mirroring how Inpaint gates on mask content via `has_mask_content`). Exact name/menu slot/shortcut (C is taken) is Claude's Discretion. — **Reversibility:** reversible (additive; removing the action later changes nothing else). Rationale: Phase 2 D-02 "hand-edits before inpaint are sacred" and the ROADMAP's own phrasing ("still inpainted via legacy Inpaint action") both imply the legacy path survives.
- **D-02 (MASK-05 flagged decision):** **Out-of-box mask content stays inpainted on the legacy whole-page path; box-constraining applies ONLY to the selective path.** The legacy Inpaint (C) never intersects the mask with boxes — a user who deliberately painted mask outside boxes (e.g. sfx removal) keeps that behavior. MASK-05's "only mask content inside text boxes is inpainted" governs the selective path only.
- **D-03:** **Selective input per qualifying box = the per-box fitted mask (from the detected precise mask via `pick_best_mask`) UNION (page pixel mask ∩ box interior).** Hand-painted mask inside a box that passes the std gate IS inpainted (Phase 2 D-02 applied at box granularity); the selective path never silently discards user painting. Boxes failing the std gate are skipped (painted content in them stays un-inpainted via this path — the legacy action still covers it). Exact union mechanics are Claude's Discretion.
- **D-04:** **Override semantics:** `Auto` (default — std gate decides) / `Force inpaint` (inpaint the whole box region regardless of the gate — the PanelCleaner box-mask behavior) / `Skip` (nothing inpainted for that box). Overrides are honored on every (re-)run of the selective action.

### Knobs & settings surface (MASK-01 + masker thresholds) — *auto-derived*

- **D-05:** **A small "Cleaning Options…" dialog in the Tools menu (near Detect/Inpaint)** exposing the primary knobs only: **mask dilation radius** (px spinbox, default 2), **std-deviation threshold** (default 15 — PanelCleaner `mask_max_standard_deviation` parity), **off-white threshold** (advanced, default 240). NOT a full settings panel — a full settings UI is its own future phase (Phase 9 is reorganization only).
- **D-06:** **Values persist into the PanelCleaner-compatible profile (INI)** — std/off-white ride the existing `[Masker]` section keys (`MaskerConfig`: `mask_max_standard_deviation`, `off_white_max_threshold`); the dilation radius gets a new key whose placement keeps PanelCleaner config compatibility (PROJECT.md constraint — researcher confirms the section, likely a detection/CTD key). The INI stays the source of truth; the dialog is a view over it. Remaining `MaskerConfig` knobs (growth steps, thickness, fast selection…) stay INI-only for advanced users.
- **D-07:** **Dilation applies at detection time** (ROADMAP-locked) — on the next Detect run, interactive AND batch detect paths (same code path, batch picks it up for free). Changing the radius does NOT re-dilate existing masks — re-detect to apply. No interactive mask grow/shrink (MASK-04 — v2, explicit).

### Per-box indicator & override (MASK-03) — *auto-derived*

- **D-08:** **Indicator = box border treatment on the canvas** — border color/dash distinguishes the per-box outcome (inpainted / skipped-by-gate / force / skip-override), consistent with the Phase 3 D-09 color-by-origin pattern; exact tokens picked against `01-UI-SPEC.md` (Claude's Discretion). NOT a badge — the bubble badge (z=140) already occupies that slot. Indicators appear after a selective run and persist with box state; re-detect replaces detected boxes wholesale (Phase 3 D-03) so their indicators/overrides reset with them.
- **D-09:** **Override control = per-box tri-state (Auto / Force inpaint / Skip) in the InspectorPanel**, following the Phase 4 D-04 pure-follower pattern (Inspector subscribes to selection; commits route through MainWindow callbacks; never mutates a PageBox directly). The override serializes on `PageBox` → `.mas` round-trip (with `mask`/`std_dev` — success criterion 5).

### Paint-under-boxes dispatch (MASK-06) — *auto-derived, ROADMAP-flagged*

- **D-10 (MASK-06 flagged decision):** **While a paint tool (Brush/Rect/Lasso/Eraser) is active, box items are transparent to mouse input — strokes land under boxes.** All box-item interaction (select / move / resize / double-click inline edit / Shift+click multi-select) requires the **Move tool (V)**. Rationale: cleanest mental model ("V = manipulate boxes; paint tools = paint"), zero modifier complexity, matches PanelCleaner's tool separation; Phase 3 D-07 "boxes always interactive" is superseded exactly and only for paint tools, as the ROADMAP prescribes. The Move tool's behavior is unchanged.
- **D-11:** **Alt+drag create-box remains available under paint tools** (empty-canvas modifier gesture, doesn't collide with paint strokes — preserves the Phase 3 D-13 create flow without tool-switching). The empty-canvas plain click still clears the box selection and falls through to paint dispatch (surface 32 contract preserved). Crop tool unchanged (a box press while CROP is active still selects the box — MASK-06 covers paint tools only).

### Claude's Discretion
- **Selective action chrome** — exact label, Tools-menu placement, shortcut (C taken by Inpaint; Ctrl+Shift+C candidate), enablement gating + status-bar copy when no boxes exist.
- **The std-gate pipeline composition** — how the vendored functions compose per box (`pick_best_mask` vs `make_mask_steps_convolution` directly; `border_std_deviation`; `MaskerData`/`MaskFittingResults` plumbing; whether `mask_page` is reusable or the per-box loop is reimplemented around it); `MaskerConfig` sourcing from the profile; threading via the existing `Worker` + `_op_running` gate.
- **Dilation implementation** — `grow_mask` post-detection vs a cv2 dilate in `TorchCTDModel.postprocess` (the 01-UAT suggestion); where the radius is read (profile → detect task kwargs).
- **Dialog widget layout** for Cleaning Options…; which (if any) additional advanced knobs surface.
- **Indicator color tokens** against `01-UI-SPEC.md` (accent reserved-use rules; box-origin colors must stay distinguishable from outcome colors).
- **Override field shape** on `PageBox` (enum vs string) + the `.mas` serialization for `mask`/`std_dev`/override (`pagebox_to_json` currently NEVER writes `mask`/`std_dev` — extend it; format version bump if the schema gate requires).
- **How per-box fitted masks render** relative to the pixel-mask overlay (`M` toggle) — planner decides the display story (e.g. whether selective results refresh the mask overlay).
- **Undo shape for a selective run** — likely ONE IMAGE-stack entry per run (batch-of-boxes op, the 04-07 one-batch-entry precedent); planner confirms and names the undo flash.
- **Batch integration** — batch detect picks up dilation for free (D-07); whether batch clean gains a selective mode is NOT required by any MASK requirement (see Deferred).

### Folded Todos
None — `todo.match-phase` returned 0 matches for Phase 8.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope
- `.planning/ROADMAP.md` §Phase 8 — **THE scope anchor.** Goal, the inherited-deferral list (01-UAT dilation quote, Phase 3 D-15 mechanics with the exact function names, MASK-05/MASK-06 flagged discuss decisions), requirements MASK-01/02/03/05/06, Depends on Phase 1 + 3 + 4, 5 success criteria (criterion 5 = the `.mas` round-trip), "Explicitly NOT in scope: MASK-04, FLOW-07".
- `.planning/REQUIREMENTS.md` §v1.2 — **MASK-01** (dilation radius), **MASK-02** (selective per-box inpaint via the D-15 seam), **MASK-03** (indicator + override), **MASK-05** (box-constrained on the selective path; out-of-box on whole-page = discuss decision → D-02 here), **MASK-06** (paint under boxes).

### Deferral sources (the inherited contracts)
- `.planning/phases/01-cleaning-workspace/01-UAT.md` (line ~61) — the dilation deferral verbatim: "the CTD heatmap boundary is conservative and leaves the edges of letters unmasked… a small morphological dilation post-processing step (cv2.dilate or a configurable radius in TorchCTDModel.postprocess)… alongside other detection-quality parameters (threshold, min-area, dilation radius)."
- `.planning/phases/03-text-box-detection-interaction/03-CONTEXT.md` — **THE most important ref.** **D-15** (the seam design — populate `PageBox.mask`/`std_dev` via `pick_best_mask` + `border_std_deviation`; user's vision quoted), **D-14** (masker.py + structures.py vendored near-verbatim, GPL v3), **D-07** (boxes always interactive — D-10/D-11 here carve out paint tools), **D-03** (re-detect replaces detected boxes wholesale — overrides reset with them), **D-09** (color-by-origin — the indicator's visual pattern), **D-12** (silent + undo recovers).
- `.planning/phases/03-text-box-detection-interaction/03-RESEARCH.md` — the masker.py surface + transitive-dep analysis the planner needs.
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md` — **D-02** (hand-edits before inpaint are sacred — D-03 honors it at box granularity), the batch structure (dilation rides batch detect), `_op_running` gate.
- `.planning/phases/05-project-persistence-image-ops-export/05-CONTEXT.md` — **D-15-preservation rule** (geometry ops transform bbox/lines only; the seam must survive), the `.mas` container contract D-01..D-06 the mask/std_dev serialization joins.
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — Pitfall-2 `.copy()` discipline, the MASK/IMAGE undo contract, worker patterns, model-load error UX.

### Vendored machinery (the build surface — GPL v3)
- `panelcleaner/image_ops.py` — **`grow_mask(mask, size)` (:811)** (the dilation primitive — convolution growth), **`border_std_deviation(base, mask, off_white_threshold, allow_color) -> (std, median_color)` (:483)**, **`pick_best_mask(...)` (:584)** (grows the precise mask in steps, picks lowest std at greatest size; returns `MaskFittingResults` or `None` on blank/noise), `make_mask_steps_convolution` (:350), `cut_out_box`/`cut_out_mask`, `BlankMaskError` (:37).
- `panelcleaner/masker.py` — `mask_page(m_data: MaskerData)` (:40), the page-level per-box driver (reference for the loop shape).
- `panelcleaner/structures.py` — `MaskerData` (:620), `MaskFittingResults` (:580: `best_mask`, `analytics_std_deviation`…), `MaskFittingAnalytic` (:562), `Box`/`BoxType`.
- `panelcleaner/config.py` — **`MaskerConfig` (:554)**: `mask_growth_step_pixels=2`, `mask_growth_steps=11`, `min_mask_thickness=4`, `allow_colored_masks=True`, `off_white_max_threshold=240`, `mask_max_standard_deviation=15`, `mask_improvement_threshold=0.1`, `mask_selection_fast=False` + `export_to_conf` (the INI section writer — config-compat path for D-06).

### Existing code (the integration seams)
- `manga_ai_studio/core/box_model.py` — **`PageBox` (:53)**; `mask`/`std_dev` fields (:95-96, `None` defaults, D-15 seam docstring); `copy()` detachment discipline (Pitfall 8 — the new override field must detach too).
- `manga_ai_studio/core/project_io.py` — **`pagebox_to_json` (:182) NEVER writes `mask`/`std_dev`**; Phase 8 extends it + the reader (schema-validation gate may need a format-version decision).
- `manga_ai_studio/gui/canvas.py` — **`mousePressEvent` (:997)** — the box hit-test branch that consumes presses before paint dispatch (D-10 carve-out site); `_box_item_at` (:2016); `box_layer` visibility sentinel; the paint-tool branch (`current_tool not in (MOVE, CROP)`).
- `manga_ai_studio/gui/main_window.py` — **`inpaint()` (:4179) + `_run_inpaint_task` (:4227)** (the legacy whole-page path — unchanged); `_run_detection_task` (:3744, dilation injection point); `_on_detection_finished` (box/mask arrival); `_confirm_replace_mask` (confirm-gate pattern); `_refresh_action_states` (:1079 Inpaint gating — the selective action's gating mirror).
- `manga_ai_studio/adapters/torch_impl.py` — `TorchCTDModel.detect/postprocess/configure` (:104/:142/:150) — the 01-UAT-suggested dilation site + existing configure() override channel.
- `manga_ai_studio/gui/inspector_panel.py` — the D-09 tri-state control site (Phase 4 D-04 follower pattern, `connect_commit_handlers`).
- `manga_ai_studio/gui/box_item.py` — border/pen state machine (`_apply_look_for_state`) — the D-08 indicator treatment extends it; badge (z=140) NOT to be reused.
- `manga_ai_studio/core/history_manager.py` — 3-stack unified timeline; the selective run's IMAGE entry (one per run, planner-confirmed).
- `manga_ai_studio/config/profile_manager.py` — the profile INI read/write the Cleaning Options dialog rides (D-06).
- `manga_ai_studio/gui/tools_panel.py` / `core/mask_editor.py` — `ToolMode` (MOVE/BRUSH/RECTANGLE/LASSO/ERASER/CROP) — the "paint tool" set for D-10 = the four mask tools.

### UI / Design contract
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — color tokens, mask overlay `rgba(255,0,0,0.63)`, accent reserved-use rules — the indicator tokens (D-08) and Cleaning Options dialog must stay consistent. **Phase 8 has `UI hint: yes` — a `/gsd-ui-phase 8` pass after planning is expected.**

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3. Phase 8 composes already-vendored GPL code (no new vendoring expected); any adapted code follows Phase 1 D-12 (near-verbatim, headers preserved).

### External References (researcher must fetch)
- PanelCleaner's own masker behavior/docs — how `mask_page` gates per box (`mask_max_standard_deviation`, off-white rounding, `MaskFittingResults` None-on-blank semantics) so our selective path matches the reference tool's behavior users expect.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Vendored mask-fitting pipeline** (`panelcleaner/image_ops.py`) — `grow_mask`, `border_std_deviation`, `pick_best_mask`, `make_mask_steps_convolution` are importable today; Phase 8 wires them, not reimplements them.
- **`PageBox` seam** (`core/box_model.py:95`) — `mask`/`std_dev` fields exist with `None` defaults and a docstring naming exactly this phase's populating functions.
- **`pagebox_to_json` / reader** (`core/project_io.py:182`) — the deliberate never-write site to extend for criterion 5.
- **Legacy inpaint path** (`main_window.py:4179`) — `Worker` + `_run_inpaint_task` + `compute_mask_bbox` + history push: the selective action mirrors this dispatch shape.
- **InspectorPanel follower pattern** — the tri-state override slots in like the bubble spinbox (bounded, commit-routed).
- **Profile INI system** — `MaskerConfig.export_to_conf` already writes the `[Masker]` section; the dialog reads/writes through the existing profile system.

### Established Patterns
- **Pitfall 2 (`.copy()` discipline)** — every numpy/PIL ↔ QImage bridge in the per-box pipeline detaches.
- **Pitfall 8 (payload aliasing)** — `PageBox.copy()` must detach the new override field + per-box mask or undo snapshots alias.
- **Silent + undo recovers** (Phase 3 D-12) — the selective run is not confirm-gated; one Ctrl+Z reverts it.
- **Worker + `_op_running` + progress** — the selective run is a long op (per-box fitting + LaMa); follows the Phase 1/2 async shape; abort-between-boxes is the natural granularity.
- **Confirm-gate before destructive replace** — re-running selective inpaint overwrites prior inpaint pixels; if a gate is wanted, mirror `_confirm_replace_mask` (planner decides; default silent per D-12).
- **Color-by-origin precedent** (Phase 3 D-09) — the D-08 outcome indicator extends the box's border-state vocabulary; must remain distinguishable from origin colors.

### Integration Points
- **Tools menu + `_refresh_action_states`** — Selective Inpaint action (D-01) + Cleaning Options… dialog (D-05).
- **`_run_detection_task` / batch detect** — dilation radius injection (D-07).
- **`canvas.mousePressEvent`** — the D-10/D-11 paint-tool carve-out in the box hit-test branch.
- **`InspectorPanel`** — the D-09 tri-state.
- **`BoxItem` border state machine** — the D-08 indicator treatment.
- **`pagebox_to_json` + reader + format version** — mask/std_dev/override round-trip (criterion 5).

</code_context>

<specifics>
## Specific Ideas

- **"Add a few pixels extra to each letter it detects"** (user, 01-UAT 2026-07-22) — the verbatim origin of MASK-01; the dilation default (2px) and the spinbox granularity should make "a few pixels" one interaction.
- **"Like PanelCleaner, only mask content inside text boxes is inpainted"** (ROADMAP MASK-05) — PanelCleaner parity is the acceptance reference for the selective path's behavior.
- **PanelCleaner's MaskerConfig defaults are the parity baseline** (std ≤ 15, off-white 240) — deviating defaults need a reason.
- **All decisions in this file are builder recommendations** (see the Provenance note) — the user's review of D-01…D-11 is the first act of planning.

</specifics>

<deferred>
## Deferred Ideas

- **Batch selective clean** — a batch mode running the selective path across a chapter (FLOW-03 extension). No MASK requirement asks for it; the machinery (batch_runner + per-box loop) makes it a natural v1.3/v2 addition.
- **Interactive mask grow/shrink brush (MASK-04)** — v2, explicitly out of scope (ROADMAP); complements the detection-time dilation.
- **Per-region LaMa params (FLOW-07)** — v2, explicitly out of scope.
- **Full settings UI panel** — Cleaning Options… (D-05) is deliberately small; a general settings/profile editor is future work (not Phase 9, which reorganizes only).
- **Re-dilation of existing masks without re-detecting** — a "re-dilate current mask" convenience action; adjacent to MASK-04 territory, deferred.
- **Detection-quality parameter suite** (threshold, min-area — the other 01-UAT "later tuning stage" knobs) — only dilation is in v1.2 scope.

</deferred>

---

*Phase: 8-Masker & Selective Inpaint*
*Context gathered: 2026-08-15*

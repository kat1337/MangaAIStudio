# Phase 8: Masker & Selective Inpaint - Context

**Gathered:** 2026-08-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver **MASK-01, MASK-02, MASK-03, MASK-05, MASK-06** — the deferred cleaning-track activation:

1. **MASK-01** — configurable mask dilation radius that grows auto-detected masks so letter edges the conservative CTD heatmap leaves unmasked get covered (the `01-UAT.md` deferral).
2. **MASK-02** — selective per-box inpainting, std-deviation-gated: only detected text masks inside boxes whose region is uniform enough are inpainted, activating the Phase 3 D-15 seam (`PageBox.mask` / `PageBox.std_dev`) via the vendored `panelcleaner/image_ops.py` machinery (`border_std_deviation`, `pick_best_mask`).
3. **MASK-03** — per-box visibility (which boxes will be / were selectively inpainted) and override (force / skip).
4. **MASK-05** — box-constrained inpainting: detected mask content outside text boxes is not inpainted (like PanelCleaner).
5. **MASK-06** — paint tools can paint mask under text boxes (box items don't block brush strokes).

The central insight (user's simplification): **the box constraint lives at the detection→mask seam, not in the inpainter.** Detected text outside any box simply never enters the mask layer; the mask layer only ever holds detected-text-inside-boxes plus hand-painted strokes; the LaMa inpaint call is untouched. "Hand-edits are sacred" (Phase 2 D-02) extends to its conclusion: hand-painted mask is always inpainted, boxes or no boxes.

**In scope:** the detection→mask seam rework (discard + dilation), the masker-parameter UI (detection-settings section, right-side Tools dock), per-box std-dev computation + indicator + override, the `Inpaint (C)` behavior change, batch adoption of the rule, paint-under-boxes dispatch carve-out, `.mas` round-trip of the new per-box state.

**Explicitly NOT in scope (ROADMAP):** interactive mask grow/shrink brush (MASK-04 — v2), per-region LaMa params (FLOW-07 — v2), UI rework of panel/toolbar layout (Phase 9 — the detection-settings section builds into the CURRENT Tools dock; Phase 9 reorganizes later).

</domain>

<decisions>
## Implementation Decisions

### The cleaning model & inpaint entry (discussed — user-locked)
- **D-01:** **One inpaint path — `Inpaint` (C) becomes the rule.** No separate "Selective Inpaint" action, no legacy whole-page mode. The rule is mask-origin-based: **hand-painted mask content is ALWAYS inpainted** (boxes or no boxes); **detected text is inpainted only inside text boxes** — boxes certify "this is actual text", CTD heatmap false positives outside boxes are ignored, matching PanelCleaner's cleaning model. Pages with no boxes: the mask layer holds whatever exists (e.g. hand strokes) and C inpaints it. — **Reversibility:** costly — the C action's behavior contract changes; downstream user workflow (batch + editor) depends on it.
- **D-02:** **The box constraint is enforced at the detection→mask seam — NOT in the inpainter.** User: "text detected by the detector that is outside of a box simply doesn't get added to the mask layer, simpler and nicer." Out-of-box detected text is discarded when the mask is built; the LaMa call is unchanged (it just inpaints the mask layer as today). — **Reversibility:** costly — the mask layer's content contract changes for every detection run.
- **D-03:** **Mask-only mode keeps Phase 1 behavior.** The Detect Boxes toggle OFF = full heatmap into the mask layer, unconstrained, no boxes (today's behavior preserved exactly). The discard rule (D-02) applies only in mask+boxes mode.
- **D-04:** **Batch adopts the rule.** Batch Detect / Batch Detect+Clean also builds boxes from the same detect pass and constrains masks to box interiors (like PanelCleaner's own batch clean). Batch-detect-only runs persist per-page boxes + constrained masks. — **Reversibility:** costly — batch output content changes.

### Detection settings & masker parameters (discussed — user-locked)
- **D-05:** **A detection-settings section in the right-side Tools dock** holds the masker controls, together with the **Detect Boxes toggle moved there from the Tools menu**. (The Tools dock is the existing right-side `dock_tools` — Phase 9's rework is NOT waited for.)
- **D-06:** **The full vendored MaskerConfig set gets UI exposure**: dilation radius, std-dev threshold (`mask_max_standard_deviation`), allow-color checkbox (`allow_colored_masks`), mask growth step pixels/steps, min mask thickness, off-white threshold, improvement threshold, fast-selection toggle. Model on how PanelCleaner presents these ("we can look at how panelcleaner does it").
- **D-07:** **Dilation affects auto-detected masks only — hand-drawn strokes are never dilated.** Natural consequence of applying dilation at the detect→mask seam.
- **D-08:** **Live re-dilate.** The raw (pre-dilation) detected mask is retained per page; changing the radius instantly re-dilates the current detected mask without re-running the model. Instant visual feedback while tuning.
- **D-09:** **Default dilation radius ≈ 2 px** — out of the box, detection covers letter edges (the 01-UAT reason this feature exists: "add a few pixels extra to each letter it detects").
- **D-10:** **Persistence via the PanelCleaner-compatible profile INI** (existing `ProfileManager`) — values survive restarts and ride PanelCleaner config compatibility.

### Per-box indicator & override (discussed — user-locked)
- **D-11:** **Border color states encode per-box inpaint state** (will-inpaint / gate-skipped / forced / user-skipped), extending the Phase 3 border-by-origin visual vocabulary. Exact token mapping is the UI-spec pass's call.
- **D-12:** **Predictive & live.** std-dev is computed as soon as boxes + mask exist (detect time); the border shows what the next `Inpaint (C)` WOULD do and updates live when the threshold changes, a box is moved/resized, or an override flips. The indicator is a preview of the next run, not just a post-run report.
- **D-13:** **The override lives in the Inspector** — a field in the existing `InspectorPanel` (like bubble # / the vertical checkbox).
- **D-14:** **Tri-state `Auto / Always / Never` per box** — Auto (std-dev gate decides) / Always (force inpaint regardless of std-dev) / Never (skip, box content untouched). Rides the `.mas` round-trip (success criterion 5).

### Paint-under-boxes dispatch (discussed — user-locked)
- **D-15:** **Pass-through + Alt select.** While a paint tool (Brush/Rect/Lasso/Eraser) is active, clicks on boxes (bodies AND handles) pass through to painting. **Alt+click on a box selects it**; **Alt+drag on a box body selects + moves it**; create-by-Alt+drag stays available on EMPTY canvas only. This is the ROADMAP-anticipated carve-out to Phase 3 D-07 ("boxes always interactive"). — **Reversibility:** reversible.
- **D-16:** **Double-click still opens the inline editor regardless of active tool** (today's behavior — editing text mid-painting stays a one-gesture flow).
- **D-17:** **The carve-out covers paint tools only.** Crop keeps today's behavior (a press on a box still selects/moves it; crop drags start on empty canvas).
- **D-18:** **No visual change.** Boxes render identically regardless of active tool; only the dispatch behavior differs.

### Claude's Discretion
- **Raw-mask retention shape** — how the pre-dilation detected mask is held per page (an `ImageFile` slot vs canvas state), and how live re-dilate (D-08) recomposes with hand-painted strokes and per-box state.
- **Mask-layer composition model** — single composite vs tracked sub-layers; where per-box detected masks live relative to `PageBox.mask` (the D-15 seam: PIL vs QImage, page coordinates), and how the display mask layer is derived from them + hand strokes. Must preserve: hand strokes always inpaint (D-01), discard-at-seam (D-02), dilation-never-touches-hand-strokes (D-07).
- **Which boxes certify** — the researcher confirms whether user-origin boxes participate identically to detected ones in the gate (the natural reading: all boxes certify; user boxes are even more intentional).
- **std-dev recomputation triggers & debouncing** — on box move/resize release, threshold/dilation change, re-detect; how eager the predictive indicator (D-12) computes without per-mousemove cost.
- **`.mas` format impact** — whether the new per-box fields (mask/std_dev/override) need a version bump; per-box mask serialization format (PNG bytes etc.); backward compatibility with Phase 5/7 projects.
- **Inspector override widget form** — 3 radio buttons vs combobox; multi-select common-value behavior (Phase 7 D-10 "Mixed" pattern applies).
- **Batch integration details** — where boxes get built in `batch_runner`, whether batch populates `PageBox.mask`/`std_dev` on `ImageFile`s, progress/abort implications.
- **Undo granularity** — expected one IMAGE entry per `Inpaint (C)` run (Phase 1 contract, silent + undo recovers), but the planner confirms against the new per-box machinery; override flips are BOXES-stack ops.
- **Re-detect interplay** — what happens to overrides/std_dev/indicator state when detected boxes are replaced (Phase 3 D-03 replace-detected-keep-user rule governs; do overrides on replaced boxes vanish with them?).
- **Detection-settings keyboard story** — the keyboard-reachability contract applies to every new control.
- **Exact border state colors** — pick from UI-SPEC tokens in the `/gsd-ui-phase 8` pass (config `ui_phase: true`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope
- `.planning/ROADMAP.md` §Phase 8 — **THE scope anchor.** Goal, the 5 requirements, the inherited-deferral list with exact `masker.py`/`image_ops.py` function names, the two flagged discuss decisions (out-of-box behavior — resolved as D-01/D-02; select-vs-paint dispatch — resolved as D-15), success criteria (incl. criterion 5: the D-15 seam round-trips through `.mas`).
- `.planning/REQUIREMENTS.md` — **MASK-01, MASK-02, MASK-03, MASK-05, MASK-06** (v1.2 Masker & Selective Inpaint section; MASK-04 and FLOW-07 stay v2).

### Prior Phase Context (the contracts Phase 8 inherits)
- `.planning/phases/03-text-box-detection-interaction/03-CONTEXT.md` — **THE seam source.** D-15 (the deferred selective-inpaint seam — `PageBox.mask`/`std_dev` stay `None` until now; names `image_ops.pick_best_mask` + `border_std_deviation` as the fillers), D-14 (vendoring discipline — near-verbatim, GPL v3), D-03 (re-detect replaces detected, keeps user), D-04 (re-detect confirm gate), D-07 (boxes always interactive — D-15 here carves the paint-tool exception), D-12 (silent + undo recovers).
- `.planning/phases/01-cleaning-workspace/01-UAT.md` — the **MASK-01 deferral verbatim**: "the CTD heatmap boundary is conservative and leaves the edges of letters unmasked... a small morphological dilation post-processing step (cv2.dilate or a configurable radius in TorchCTDModel.postprocess)" — the user's "add a few pixels extra to each letter it detects."
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — Pitfall-2 `.copy()` buffer discipline, thread-safety contract T-01-07, model-load error UX, the 2-stack undo contract.
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md` — **D-02 "hand-edits before inpaint are sacred"** (D-01 here extends it to always-inpaint), the batch structure (three entry points, load-once, abort-between-pages — D-04 integration surface), D-11 per-page persistence seam.
- `.planning/phases/05-project-persistence-image-ops-export/05-CONTEXT.md` — the `.mas` container/serialization mechanics the new per-box fields join (D-01/D-03/D-04/D-05 there); D-15 geometry transforms already preserve the seam (transform bbox/lines only — the per-box mask transform story extends this).
- `.planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-CONTEXT.md` — D-08/D-09/D-10 multi-select + grouped ops + common-value "Mixed" Inspector pattern (the override field's multi-box behavior mirrors it).
- `.planning/phases/04-ocr-recognition-text-editing/04-CONTEXT.md` — the InspectorPanel pure-follower pattern (subscribes to selection, commits via callbacks, never mutates PageBox directly) — the override field follows it.

### Existing Code (the build surfaces)
- `panelcleaner/image_ops.py` — **the machinery, already vendored (GPL v3)**: `border_std_deviation` (`:483`), `pick_best_mask` (`:584`), `make_mask_steps_convolution` (`:350`), `grow_mask` (`:811`), `cut_out_box`/`cut_out_mask`, `compose_masks`, `mask_intersection`, `fade_mask_edges`. This is what fills the D-15 seam.
- `panelcleaner/masker.py` — vendored batch driver (`mask_page`); dead code in our context but documents the canonical call sequence for per-box mask fitting.
- `panelcleaner/config.py` — **`MaskerConfig` (`:554`)**: `mask_growth_step_pixels=2`, `mask_growth_steps=11`, `min_mask_thickness=4`, `allow_colored_masks=True`, `off_white_max_threshold=240`, `mask_max_standard_deviation=15`, `mask_improvement_threshold=0.1`, `mask_selection_fast=False` — the D-06 parameter set and defaults.
- `panelcleaner/structures.py` — the vendored `Box`, `MaskerConfig` refs, `MaskFittingResults`.
- `manga_ai_studio/core/box_model.py` — **`PageBox`** (`:53-178`): `mask: Optional[object] = None` / `std_dev: Optional[float] = None` (`:95-96`) — the D-15 seam fields this phase populates; `copy()` detachment discipline (Pitfall 8).
- `manga_ai_studio/gui/main_window.py` — **`_on_detection_finished` (`:3863`)** — THE seam D-02 reworks (currently composites the FULL heatmap then optionally builds boxes); `_build_detected_boxes` (`:3908+`, D-03/D-04/V5 rules); `inpaint` (`:4179`, unchanged LaMa call); `detect_text` (`:3701`), `_run_detection_task` (`:3744` — returns `{"mask", "blocks"}`); `_confirm_replace_mask`/`_confirm_replace_boxes` gates.
- `manga_ai_studio/gui/canvas.py` — **`mousePressEvent` (`:997-1138`)** — the D-15 dispatch site (box hit-test branch → crop branch → mask-tool branch; `_box_item_at`, `box_layer` visibility gate); the mask layer + `set_mask`; `_begin_paint`.
- `manga_ai_studio/gui/tools_panel.py` — the ToolsPanel (right-side `dock_tools`): tool buttons + brush size — the D-05 detection-settings section lands here.
- `manga_ai_studio/gui/inspector_panel.py` — InspectorPanel (QFormLayout, class-scope Signals, commit-handlers pattern) — the D-13/D-14 override field site.
- `manga_ai_studio/core/batch_runner.py` — the batch loop (`batch_detect`/`batch_clean`/`batch_detect_and_clean`) — the D-04 integration surface.
- `manga_ai_studio/config/profile_manager.py` — `ProfileManager` (PanelCleaner INI/ConfigUpdater) — the D-10 persistence path.
- `manga_ai_studio/core/image_file.py` — `ImageFile` (path, mask, boxes slots) — per-page state home; raw-mask retention (D-08) likely lands here.
- `manga_ai_studio/core/project_io.py` — the `.mas` per-page serialization the per-box fields join.
- `manga_ai_studio/core/history_manager.py` — the 3-stack + unified-timeline undo (override flips push BOXES; inpaint pushes IMAGE).

### Source References (PanelCleaner — GPL v3)
- `../PanelCleaner/pcleaner/` — upstream reference for how PanelCleaner presents/uses the masker params (D-06: "look at how panelcleaner does it") and its box-driven clean model. Everything needed is already vendored near-verbatim per Phase 1 D-12 / Phase 3 D-14 — no new vendoring expected.

### UI / Design contract
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — color tokens (mask overlay `rgba(255,0,0,0.63)`, accent `#00d4ff` reserved uses, canvas matte), spacing, dark QSS. D-11's border states pick from these. **Phase 8 has `UI hint: yes` — a `/gsd-ui-phase 8` pass follows planning** (config `ui_phase: true`).

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3. Phase 8 composes existing vendored modules; new code (seam rework, detection-settings UI, indicator, dispatch) is our own under GPL v3.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Vendored `image_ops.py` machinery** — `border_std_deviation` + `pick_best_mask` + growth kernels are fully present; the D-15 seam needs no new vendoring, just the first real caller.
- **`_run_detection_task` already returns `{"mask", "blocks"}`** — the same worker result feeds the constrained-mask build (D-02) and box building; no adapter/model changes.
- **`MaskerConfig` + `ProfileManager`** — the parameter model and INI persistence already exist; the detection-settings section (D-05/D-06) is a UI over them.
- **InspectorPanel follower pattern + Phase 7 common-value/"Mixed"** — the override field plugs into a proven structure.
- **Phase 7 multi-select grouped ops** — Alt-select/move in paint mode (D-15) reuses the group-move machinery.
- **`dock_tools` (right side)** — the detection-settings section's home; brush-size row is the layout precedent.

### Established Patterns
- **Pitfall 2 (`.copy()` discipline)** — every numpy↔QImage bridge in the new mask-composition paths detaches.
- **Pitfall 8 (payload aliasing)** — `PageBox.copy()` must detach the new `mask`/override state or undo restores post-edit values (the 04-05 lesson).
- **Silent + undo recovers** (Phase 3 D-12 / Phase 5 D-14) — `Inpaint (C)` stays non-destructive, no confirm; overrides push BOXES snapshots.
- **Confirm-gate before destructive replace** — re-detect gates (`_confirm_replace_mask`/`_confirm_replace_boxes`) govern the new seam's replace flows.
- **Per-page persistence `.copy()` at both boundaries** (Phase 2 D-11) — the raw detected mask (D-08) and per-box state follow the same discipline across page switches and `.mas` save/load.
- **Worker + `_op_running` gate** — any new model-touching work (none expected for dilation; std-dev is pure numpy) follows the Phase 1/2 async shape; std-dev computation is cheap and main-thread-safe.
- **Composition, not subclassing** (Phase 3 D-14) — new per-box state layers onto `PageBox`; vendored types stay untouched.

### Integration Points
- **`_on_detection_finished`** — the D-02 rework site: build boxes, constrain the mask to box interiors, discard out-of-box content, compute per-box std-dev (D-12), apply dilation (D-07/D-09).
- **`main_window.inpaint`** — behavior change only in what the mask layer already contains; the LaMa call is untouched (D-02).
- **`canvas.mousePressEvent`** — the D-15 carve-out: paint-tool branch takes priority over box hit-test; Alt modifiers route to select/move; crop and double-click unchanged (D-16/D-17).
- **`tools_panel.py` + `dock_tools`** — the detection-settings section (D-05/D-06) incl. the relocated Detect Boxes toggle; live re-dilate wiring (D-08).
- **`inspector_panel.py`** — the Auto/Always/Never override field (D-13/D-14).
- **`batch_runner.py`** — box building + constrained masks in batch mode (D-04).
- **`project_io.py`** — per-box mask/std_dev/override serialization (success criterion 5).
- **`image_file.py`** — raw detected-mask retention (D-08) + per-page box/mask state.

</code_context>

<specifics>
## Specific Ideas

- **The origin rule (user, D-01):** "manually painted masks should always be inpainted on, but because the OCR can have false positives, just like panelcleaner, we only inpaint/mask things that are inside a text box (they're actual text), what the user choses to inpaint by hand gets inpainted anyways" — the defining behavior of the phase.
- **The seam simplification (user, D-02):** "let's add a bit of a processing step to make this simpler and not have to make changes to the inpainter, text detected by the detector that is outside of a box simply doesn't get added to the mask layer, simpler and nicer" — the constraint is a detection→mask processing step, not an inpainter feature.
- **The settings home (user, D-05/D-07):** "Let's add it to the right bar under detection settings along with detect boxes, and this dilation should only affect auto-detected masks, not user hand drawn masks."
- **PanelCleaner as the reference (user, D-06):** "we can look at how panelcleaner does it, it supports color too, so let's also add that allow color masks check to this" — the vendored MaskerConfig is the model; the UI mirrors PanelCleaner's presentation.
- **Predictive borders (D-12)** — the user's mental model: the border color is a live answer to "what would happen if I pressed C right now?", not a history report.

</specifics>

<deferred>
## Deferred Ideas

- **Interactive mask grow/shrink brush (MASK-04)** — v2 per ROADMAP; complements the detection-time dilation (MASK-01) with manual per-region adjustment.
- **Per-region LaMa params (FLOW-07)** — v2 per ROADMAP.
- **Sidebar/toolbar layout rework** — Phase 9 (UI-01..05); the detection-settings section builds into the current Tools dock and Phase 9 reorganizes afterward (the user explicitly sequenced masker first).
- None — discussion stayed within phase scope (no scope-creep ideas surfaced).

</deferred>

---

*Phase: 8-Masker & Selective Inpaint*
*Context gathered: 2026-08-15*

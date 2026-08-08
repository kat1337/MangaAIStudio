# Phase 5: Project Persistence, Image Ops & Export - Context

**Gathered:** 2026-08-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver **three** requirements — the "resumable workspace" final layer of the editor:

1. **PROJ-01** — Save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work.
2. **PROJ-03** — Export OCR/box data as a `_ocr.json` file per page for use in downstream tools.
3. **PROJ-04** — Apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize.

The central insight: **Phases 1-4 built all the state that Phase 5 serializes.** Per-page masks live on `ImageFile.mask` (Phase 2 D-11 slot), boxes + text + translation + bubble numbers live on `ImageFile.boxes` → `PageBox` payloads (Phases 3-4), the image result lives on the canvas (numpy round-trip via `get_image_numpy`/`set_image_from_numpy`), and the IMAGE/MASK/BOXES undo stacks + unified Ctrl+Z exist (Phase 1/3). **Phase 5 puts this state on disk** — a resumable `.mas` project — **and adds pixel-level page editing** (crop/rotate/levels/resize) that transforms the image AND the mask/box geometry together, so prior work survives every op.

**In scope:**
(a) `.mas` project system: chapter manifest + self-contained per-page `.mas` files in a `<chapter>.mas-project/` folder beside the source; JSON + embedded images, LZMA2-compressed (stdlib `lzma`, custom container); Save Project… (Ctrl+S) / Open Project… (Ctrl+O) with dirty tracking and Recent Projects;
(b) `_ocr.json` export: custom shape (mokuro vocabulary + our fields, INCLUDING `lines[]` with per-line text split from the stored text by `\n`); single-page export + Batch Export OCR JSON; sidecar next to the source when the page is pristine, `cleaned/` when geometry ops altered the page;
(c) image ops: Rotate 90° CW/CCW/180°, Canvas Crop tool (6th tool) + numeric Crop dialog, Levels dialog (black/white/gamma, live preview), Resize dialog (aspect lock, px/% toggle) — all silent + IMAGE-stack undoable, mask/box geometry transformed with the image.

**Out of scope (later phases / v2):**
- Full curve editor (levels/curves, TRAN-02 typesetting adjacency) — v2.
- Arbitrary-angle rotation — v2.
- Machine translation (TRAN-01 — v2), typesetting output (TRAN-02 — v2).
- Selective per-box inpaint (Phase 3 D-15 seam — stays open; `PageBox.mask`/`std_dev` stay `None`).
- Batch OCR across a chapter (FLOW-04 — v2); Phase 5's batch is serialization-only (no models).
- Packaging/distribution (no v1 REQ-ID; ROADMAP Notes).

</domain>

<decisions>
## Implementation Decisions

### .mas project scope & on-disk layout (PROJ-01)
- **D-01:** **A project = a chapter (the open folder's session), split into a manifest + per-page files.** The user chose "Both (manifest + page files)" over single-file-per-chapter or per-page-sidecars. A chapter manifest groups the pages; each page gets its own `.mas` file. — **Reversibility:** one-way — the on-disk project layout is the format saved projects depend on; changing it later requires migration of existing projects.
- **D-02:** **Project folder sits beside the source folder** (mirrors the Phase 2 `cleaned/` sibling convention): e.g. `chapter-01/` → `chapter-01.mas-project/` containing `manifest.json` + per-page `<page>.mas` files (same stem as each source page). Source folders stay untouched. Exact folder-name validation (collision handling) is planner detail. — **Reversibility:** one-way — same published-layout rationale as D-01.
- **D-03:** **Per-page `.mas` files are self-contained** — each carries its own current image (embedded), mask, boxes/text, and original-path ref + checksum. A page file opens standalone OR through the manifest. The manifest holds only page order + session metadata (and per-page refs). — **Reversibility:** costly — moving state between page files and manifest later would touch every save/load path.
- **D-04:** **Container format = JSON + embedded images, LZMA2-compressed (NOT zip).** User explicitly: "JSON + embedded images but let's use LZMA2 instead of zip". Implementation: stdlib `lzma` module with `FORMAT_XZ` (LZMA2 filter) inside our own container layout (JSON manifest + embedded blobs, header with entry table) — **zero new dependencies**, matching the stdlib-light precedent of `core/image_io.py`. The manifest itself stays **plain JSON** (tiny, human-readable, diffable); the per-page files carry the compressed payloads. Researcher confirms the exact XZ/LZMA2 API surface + container layout. — **Reversibility:** one-way — the container layout is the saved-project format; changing it needs a reader migration.
- **D-05:** **Saved image state per page = the CURRENT page image only** (inpainted result if any, else original) — resume exactly where you left off, like a .psd. **Undo stacks are NOT serialized** — a reopened project starts with a fresh undo history. — **Reversibility:** costly — adding undo serialization later is additive, but the "fresh history" contract is what v1 users will rely on.
- **D-06:** **Original-path reference + checksum per page.** On open: if the original file is found at the referenced path AND its checksum matches, it is used as the base image (Show Original works). If not found/mismatched, the embedded current image is used and **Show Original is greyed out** (user: "if the image is not available just grey out the option"). Checksum algorithm is agent discretion (planner picks; sha256 is the obvious default).

### Save/Open session semantics (PROJ-01)
- **D-07:** **Manual Save Project… (Ctrl+S) / Open Project… (Ctrl+O) with dirty tracking.** Dirty pages mark the window title (`*` convention); closing/opening with unsaved changes prompts **Save / Discard / Cancel**. Save As… exists for first save. Recent Projects join the existing Recent Files menu structure. — **Reversibility:** reversible.
- **D-08:** **Open Project rebuilds the session from the manifest** — sidebar order, per-page state (masks, boxes, text) all restored; source images re-found via path refs + checksum (D-06). Batch/export operations work on the reopened project's pages. — **Reversibility:** reversible.
- **D-09:** **Opening a per-page `.mas` file directly is supported, with manifest-climb.** Open Project… opens a manifest. Opening a page `.mas` (e.g. via the file dialog / double-click): if a sibling manifest is detected, pop a dialog — user's words: "chapter detected, open entire chapter?" — **Yes** loads the chapter via the manifest; **No** opens the single page as a standalone session. No sibling manifest → open the single page directly. — **Reversibility:** costly — the dialog contract is a UX expectation; changing the climb behavior later is easy, but the self-contained page file shape is load-bearing.

### Image-op UX & undo (PROJ-04)
- **D-10:** **Rotation = 90° steps only (CW / CCW / 180°).** Manga scans arrive in 90° increments; steps are pixel-exact and keep mask/box transforms lossless. Arbitrary-angle rotation is deferred (v2). — **Reversibility:** reversible (deferral).
- **D-11:** **Crop = a Canvas Crop tool** — the 6th tool in the existing `QActionGroup` (Move/Brush/Rect/Lasso/Eraser/Crop): drag a rect on the page, Enter applies, Esc cancels. A numeric **Crop… dialog** (x/y/w/h) rides along in the Edit menu for precision. — **Reversibility:** reversible.
- **D-12:** **Levels = a Levels dialog** — black point, white point, gamma (3 controls) with **live preview** on the canvas. The full curve editor is v2 (deferred). — **Reversibility:** reversible.
- **D-13:** **Resize = a Resize… dialog** — width + height fields, **aspect lock on by default**, px/percentage toggle, live preview of new dims. — **Reversibility:** reversible.
- **D-14:** **All four ops are silent + IMAGE-stack undoable** — no confirm dialogs; Ctrl+Z reverses each op. **Show Original re-baselines to the post-op image** (the `_original_image_numpy` cache resets to the current state after an op). Matches Phase 3's "silent + undo recovers" philosophy (D-12). — **Reversibility:** costly — the re-baseline contract means the pre-op image is only recoverable via undo, not via Show Original.

### Image ops vs masks/boxes (PROJ-04)
- **D-15:** **Geometry ops transform the mask AND the box geometry along with the page image.** Crop/rotate/resize are lossless to prior work — the whole point of a resumable workspace. Levels is geometry-free (pixels only; mask/boxes untouched). — **Reversibility:** one-way — the transform contract is the phase's core data invariant; deviating later (e.g. storing ops as a re-playable stack) would be a model change.
- **D-16:** **Crop edge policy: drop fully-outside boxes, clip partial boxes.** Boxes fully outside the crop rect are removed with a **count reported in the status bar**; boxes partially inside are clipped to the crop rect (their bbox and lines clamp to the new page boundary). — **Reversibility:** reversible (undo recovers the crop including dropped boxes).
- **D-17:** **Transform depth = bbox AND `TextBlock.lines` polygons together.** Rotate/scale/translate each line polygon with the box, so per-line geometry stays valid for `_ocr.json` export and future typesetting/selective-inpaint. No stale-lines shortcut. — **Reversibility:** costly — the full-payload transform is the fidelity contract; dropping it later degrades exports.
- **D-18:** **Pixel-exact mask transforms.** Rotate 90°/180° = exact `QImage` transform; resize = nearest-neighbor scale of the binary mask (no soft alpha drift); crop = exact slice. Mask overlay stays aligned pixel-for-pixel with the image. — **Reversibility:** reversible.

### _ocr.json export shape & scope (PROJ-03)
- **D-19:** **Custom JSON shape — mokuro vocabulary PLUS our fields, INCLUDING `lines[]`.** The user overrode strict-mokuro fidelity: "mokuro vocab plus our fields, including lines, since this will be used for typesetting it is important to note in a text bubble where a line begins and ends". Shape: per-page JSON object — `version`, `img_width`, `img_height`, `blocks[]` with `box` [x1,y1,x2,y2], `vertical`, `text`, `translation`, `bubble_no`, `origin` — AND `lines[]` carrying per-line `box` + `text` so a typesetting tool knows where each line begins/ends inside a bubble. Exact field spelling/JSON layout is planner detail against this contract. — **Reversibility:** one-way — the JSON shape is a published contract consumed by downstream (typesetting) tools; changing it breaks consumers. Rationale is the user's quoted typesetting requirement above.
- **D-20:** **Per-line text comes from splitting the stored whole-text by `\n`** onto the detected `TextBlock.lines` polygons (line N gets segment N; unmatched lines export empty text). No model changes, works with today's single-str storage. The per-line storage upgrade (list in `TextBlock.text`) was considered and **rejected for v1**. — **Reversibility:** costly — the `\n`-split mapping is the export contract; upgrading to true per-line storage later changes both the model and the export.
- **D-21:** **Export scope = single page + batch.** "Export OCR JSON…" (current page, Save As dialog) in the Text menu; "Batch Export OCR JSON" in the Batch menu writes every page of the open folder. Mirrors Phase 2's single-export + batch-action structure. Serialization is model-free and fast (no Worker needed unless the planner decides otherwise). — **Reversibility:** reversible.
- **D-22:** **Output location follows page state.** Pristine page (no geometry ops): sidecar `<name>_ocr.json` **next to the source page** (mokuro naming convention). Geometry-altered page (crop/rotate/resize applied): the JSON is written into **`cleaned/`** instead, because its coordinates describe the post-op page, not the image sitting next to it. Coordinates + img dims always describe the **current** page state. — **Reversibility:** costly — the state-dependent location rule is the placement contract downstream tooling will rely on.

### Claude's Discretion
- **Geometry-op undo record shape (user declined to discuss this area).** Image ops push IMAGE-stack entries, but the mask/box transform (D-15) rides along — and the Phase 1 IMAGE stack stores only QImage patches. The planner must decide the record shape so **one Ctrl+Z reverses image + mask + boxes together** (one press per op, not two). A combined record entry or a paired-stack push with a merge rule are both candidates — pick the least-surprising unified-timeline behavior (Phase 3 D-11).
- **Checksum algorithm** for D-06 (sha256 default), **manifest schema fields** (versioning, per-page refs, page order, session metadata), **container entry-table layout** (D-04), **crop dialog + levels dialog widget details**, **resize interpolation**, **dirty-title format**, **project-folder collision handling** (D-02), **Recent Projects entry naming**, **menu placement** (File vs Text vs Batch for the new actions).
- **`_ocr.json` JSON spelling** — field names/snake_case vs camelCase per the D-19 contract; version string value.
- **Batch Export OCR JSON threading** — model-free serialization is fast; planner decides whether it needs the Worker/`_op_running` gate or runs inline.
- **UI-SPEC pass follows** — ROADMAP says `UI hint: yes` for Phase 5; `/gsd-ui-phase 5` will produce the design contract for the crop tool, dialogs, and menu additions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — PanelCleaner (GPL v3) foundation; model adapter interface; single-env in-process `QThreadPool`; **"Basic image operations: crop, rotate, levels/curves, resize" (Active requirements list) and the Out-of-Scope "Full-featured image editor" line. NOTE: PROJECT.md's Context section claims crop/rotate/levels live in `pcleaner/image_ops.py` — THIS IS STALE** (verified: PanelCleaner's `image_ops.py` is mask-fitting/denoising machinery; no crop/rotate/levels functions exist anywhere in PanelCleaner). PROJ-04 is greenfield — no vendor reference; implement with PIL/Qt primitives.
- `.planning/REQUIREMENTS.md` — **PROJ-01** (save full page state as `.mas`, reopen to resume), **PROJ-03** (export OCR/box data as mokuro-style `_ocr.json` per page for downstream tools), **PROJ-04** (basic image ops: crop, rotate, levels/curves, resize). Traceability maps all three to Phase 5. v2 FLOW-04/FLOW-05 remain deferred.

### Phase Scope
- `.planning/ROADMAP.md` §Phase 5 — Goal ("save and resume full project state, apply basic image operations, and export OCR/box data for downstream tools — turning the editor into a resumable, interoperable workspace"), 3 success criteria, requirements PROJ-01/03/04, "UI hint: yes", Depends on Phase 1 + Phase 4. ROADMAP Notes: packaging has no v1 REQ-ID.

### Prior Phase Context (carries forward — the state Phase 5 serializes)
- `.planning/phases/04-ocr-recognition-text-editing/04-CONTEXT.md` — **THE most important ref.** Defines the state Phase 5 exports: `PageBox` fields (`text` as single str via `set_recognized_text`/`set_recognized_text_edited`, `translation`, `edited`, `bubble_no`, `manual_override`), the `\n`-capable text storage (D-20 splits on it), TextBlock payload structure (`.lines` polygons, `.vertical`, `.language`), the MT seam (D-13 `set_translation`), bubble numbering (D-15/D-16), deferred list explicitly naming Phase 5 for `.mas`/`_ocr.json`/image ops.
- `.planning/phases/03-text-box-detection-interaction/03-CONTEXT.md` — boxes as first-class objects: `PageBox` model (bbox + origin + payload), `BoxItem`, BOXES undo stack + unified Ctrl+Z timeline (D-10/D-11), D-12 "silent + undo recovers" (mirrored by D-14 here), per-page box persistence, **D-15 selective-inpaint seam (`PageBox.mask`/`std_dev` stay `None` — Phase 5 must NOT fill them)**.
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md` — **D-11 per-page persistence seam** (the exact save/restore pattern `.mas` builds on), the `cleaned/` output convention (D-07 — reused for D-02's sibling folder and D-22's altered-page JSON target), batch structure (three actions + `_op_running` gate + `Worker`/`SharableFlag`), `image_io.save_image_optimized`.
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — foundation: model adapters, code organization, **2-stack undo (D-01-06) extended to 3 by Phase 3**, Pitfall-2 `.copy()` discipline, single-env execution, thread-safety contract T-01-07, model-load error UX.

### Existing Code (Phases 1-4 — what Phase 5 builds on)
- `manga_ai_studio/core/image_io.py` — **the pattern for new core I/O modules**: pure stdlib + numpy + PIL, no Qt/torch, headless-testable, thread-safe. `save_image_optimized` (PNG compress_level=9, JPG quality=95/progressive, DPI/mode preservation) is the writer for embedded page images in `.mas` and any export. `passthrough_original` shows the copy2 discipline.
- `manga_ai_studio/core/image_file.py` — **`ImageFile`** (path, thumbnail, mask, boxes, dirty) — THE serialization unit. `has_mask_content()`/`has_boxes()` gates; `boxes` slot holds `list[PageBox]`.
- `manga_ai_studio/core/box_model.py` — **`PageBox`** (box: vendored frozen `Box`; origin; payload: `TextBlock`; edited; bubble_no; manual_override; mask/std_dev = D-15 seam) + `textblock_to_box` coercion. Serialization must map PageBox → JSON and back without touching the vendored `Box` (D-14 anti-pattern: composition, not subclassing).
- `manga_ai_studio/gui/main_window.py` — `_build_file_menu` (Open Image/Folder, Recent Files, Export Page, Batch, Quit — Phase 5 slots: Save/Open Project, Recent Projects, Batch Export OCR JSON), `_build_text_menu` (Run OCR / OCR All / Auto-Number / Load Translations — slot for Export OCR JSON), `_build_tools_menu` + toolbar (slots for Rotate/Levels/Resize/Crop dialog), `_op_running` gate, `_dispatch_batch`/`_run_batch_task` patterns, `on_page_selected` D-11 seam (line ~882), `_last_page_index`, `_flush_current_canvas_mask_to_data_model`, `_refresh_action_states`.
- `manga_ai_studio/gui/canvas.py` — `EditorCanvas`: `get_image_numpy`/`set_image_from_numpy` (the image round-trip `.mas` saves), `_original_image_numpy` cache (Show Original — D-06/D-14 re-baseline point), `set_mask`/`get_mask`/`mask_modified`, mask layer + box layer + text overlay (Phase 4), mouse-event dispatch for mask tools (crop tool slots here — D-11), `_begin_create_box`/`_commit_create` (Alt+drag).
- `manga_ai_studio/core/history_manager.py` — 3-stack HistoryManager (MASK + IMAGE + BOXES) + unified-timeline undo/redo (D-11 Phase 3). **The geometry-op undo record (Claude's Discretion) integrates here.**
- `manga_ai_studio/gui/worker_thread.py` — `Worker(QRunnable)` + `WorkerSignals` + `SharableFlag`; `core/batch_runner.py` — the batch loop shape for Batch Export OCR JSON (D-21).
- `manga_ai_studio/gui/tools_panel.py` + `core/mask_editor.py` — `ToolMode` enum + `QActionGroup` (D-11 adds CROP as a 6th tool).
- `manga_ai_studio/config/profile_manager.py` — profile/config system (unlikely to change; researcher confirms no config keys needed for v1).

### Source References (PanelCleaner — GPL v3)
- `../PanelCleaner/pcleaner/image_export.py` — `save_optimized` — **already adapted** into our `core/image_io.py`; no new vendoring needed for writing images.
- `../PanelCleaner/pcleaner/gui/image_viewer.py` (lines ~509-513) — PanelCleaner's rotate 90/180/270 as **viewing transforms** (QTransform) — reference for the rotate UX, NOT for data transforms (ours are destructive edits per D-15).
- `../PanelCleaner/pcleaner/image_ops.py` — **STALE-REFERENCE WARNING**: PROJECT.md points here for crop/rotate/levels, but this file is mask-fitting/denoising machinery (border_std_deviation, pick_best_mask, etc.). Do NOT expect crop/rotate/levels here. PROJ-04 is greenfield (our own PIL/Qt implementation, no GPL obligation).
- `../PanelCleaner/LICENSE` — GPL v3. Phase 5's serialization/export/image-op code is **our own** (no new vendoring expected); any PanelCleaner code adapted must follow Phase 1 D-12.

### External References (researcher must fetch)
- mokuro `_ocr.json` schema (kha-white/mokuro docs) — the vocabulary D-19 borrows (`version`, `img_width`, `img_height`, `blocks`, `box`, `vertical`, `lines`). We deviate deliberately (our shape, `\n`-split text, extra fields) per D-19/D-20.
- Python stdlib `lzma` module docs — `FORMAT_XZ` (LZMA2 filter) API for the D-04 container.

### UI / Design contract
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — the design contract: color tokens, spacing, "artwork is the sole saturated surface" principle. The crop tool, dialogs (Levels/Resize/Crop), and new menu actions must stay consistent. **Phase 5 has `UI hint: yes` — `/gsd-ui-phase 5` follows this discuss step.**

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`core/image_io.py`** — the pure-PIL writer module (`save_image_optimized`, `passthrough_original`). The template for the new serialization modules: a `core/project_io.py` (`.mas` save/load) and a `core/ocr_export.py` (`_ocr.json`) mirroring its stdlib+PIL-only discipline, headless-testable.
- **`ImageFile` + `PageBox`** — all serialization data already lives on these models: mask (QImage), boxes (list[PageBox] with payload text/translation/bubble_no/origin/edited/manual_override + TextBlock.lines polygons + vertical). `.mas` and `_ocr.json` are projections of this state — no new data capture needed.
- **`save_image_optimized`** — the writer for embedded page images in `.mas` page files (PNG, DPI preserved).
- **Canvas numpy round-trip** (`get_image_numpy`/`set_image_from_numpy`) — the image state `.mas` saves (D-05); the same round-trip applies image ops (D-14).
- **`batch_runner.py` + `Worker`** — the loop shape for Batch Export OCR JSON (D-21) and any async concerns.
- **Phase 2 D-11 persistence seam** (`on_page_selected` + `_last_page_index`) — the per-page save/restore machinery `.mas` load reuses directly (restore mask + boxes into ImageFile slots on open).
- **Recent Files menu** (`recent_menu`) — the structure Recent Projects extends (D-07).

### Established Patterns
- **Pitfall 2 (`.copy()` buffer discipline)** — every numpy↔QImage / serialization bridge detaches; `.mas` load must copy embedded QImages into `ImageFile` slots, and embedded numpy data must detach before use.
- **Per-page persistence `.copy()` at both boundaries** (Phase 2 D-11 / T-02-04) — `.mas` save/load follows the same belt-and-suspenders discipline.
- **3-stack undo + unified timeline** (Phase 3 D-10/D-11) — geometry ops push entries whose snapshots must also cover the transformed mask/boxes (Claude's Discretion record shape).
- **Silent + undo recovers** (Phase 3 D-12) — D-14 extends this to image ops (no confirm dialogs).
- **`cleaned/` sibling-folder convention** (Phase 2 D-07) — D-02's `<chapter>.mas-project/` and D-22's altered-page JSON target follow it.
- **Thread-safety contract (T-01-07)** — serialization is pure Python + disk I/O; `_ocr.json` batch export can run inline or via `Worker` (planner decides). Qt mutation only in main-thread handlers.
- **GPL v3 vendoring discipline** (Phase 1 D-12) — no new vendoring expected; new modules are our own.

### Integration Points
- **`MainWindow._build_file_menu`** — Save Project… (Ctrl+S) / Open Project… (Ctrl+O) + Recent Projects.
- **`MainWindow._build_text_menu`** — Export OCR JSON… (single page).
- **`MainWindow._build_batch_menu`** — Batch Export OCR JSON (D-21).
- **`MainWindow._build_tools_menu` / toolbar** — Rotate CW/CCW/180°, Levels…, Resize…, Crop… dialog actions.
- **`ToolsPanel` + `ToolMode`** — CROP as the 6th tool (D-11); canvas mouse-event dispatch routes crop-rect drawing.
- **`EditorCanvas`** — image-op apply path (`set_image_from_numpy`), mask transform (`set_mask`), box-layer refresh, `_original_image_numpy` re-baseline (D-14), crop-rect overlay rendering.
- **`HistoryManager`** — geometry-op undo records covering image + mask + boxes (Claude's Discretion).
- **`core/` new modules** — `project_io.py` (`.mas`), `ocr_export.py` (`_ocr.json`), `image_ops.py` (crop/rotate/levels/resize + geometry transforms) following `image_io.py`'s pure-Python shape.

</code_context>

<specifics>
## Specific Ideas

- **"JSON + embedded images but let's use LZMA2 instead of zip"** (user, container format) — the container decision is explicit and non-negotiable; stdlib `lzma`/FORMAT_XZ is the no-new-deps interpretation, researcher confirms.
- **Original-image availability rule (user, D-06):** "in case the original image is available, we can just use that as our 'base' image, if the image is not available just grey out the option" — the checksum-verified original is the base; Show Original greys out when absent. The user's mental model: the .mas always opens; the original is a convenience, not a requirement.
- **Chapter-detected dialog (user, D-09):** opening a page `.mas` with a sibling manifest should "pop a window that says 'chapter detected, open entire chapter?' or something like that" — verbatim intent for the climb behavior.
- **Typesetting drives the export shape (user, D-19):** "since this will be used for typesetting it is important to note in a text bubble where a line begins and ends" — `lines[]` in `_ocr.json` is load-bearing for the user's real downstream workflow, not decoration.
- **"Resumable like a .psd"** (PROJECT.md core framing) — the .mas must restore the exact visual state: current image + mask overlay + boxes/text as they were.
- **Phase 5 is serialization + pixel ops only — no new models, no re-running detection/OCR.** Everything Phase 5 writes already exists in memory (masks, boxes, text) or on the canvas (current image).

</specifics>

<deferred>
## Deferred Ideas

- **Full curve editor (levels/curves, TRAN-02 adjacency)** — v2. Phase 5 ships the Levels dialog (black/white/gamma, D-12); the draggable-curve editor is a future typesetting/editing phase.
- **Arbitrary-angle rotation** — v2. Phase 5 is 90° steps only (D-10); free rotation needs interpolation + input UI + arbitrary-angle geometry math.
- **Per-line text storage** — rejected for v1 (D-20 chose `\n`-split at export). A future typesetting phase may upgrade `TextBlock.text` to a list; the export contract would then read it directly.
- **Strict mokuro `_ocr.json` compatibility** — overridden by the user (D-19 custom shape). If a downstream tool ever demands the exact mokuro schema, a converter is a small future addition.
- **Selective per-box inpaint (Phase 3 D-15 seam)** — stays open and untouched: `PageBox.mask`/`std_dev` remain `None` through Phase 5; geometry transforms must preserve the seam (transform lines/bbox only).
- **Undo-stack serialization in `.mas`** — rejected (D-05, fresh undo history on reopen).
- **Batch OCR across a chapter (FLOW-04), batch→editor round-trip (FLOW-05), typesetting output (TRAN-02)** — v2, unchanged.

</deferred>

---

*Phase: 5-Project Persistence, Image Ops & Export*
*Context gathered: 2026-08-08*

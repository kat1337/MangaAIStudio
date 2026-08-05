# Phase 4: OCR Recognition & Text Editing - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver **three** requirements (the second half of the text/OCR track — recognition, editing, translation):

1. **TEXT-02** — Draw a rectangle on the page and run manga-ocr on just that region to create a box with recognized text (for boxes the auto-detector missed).
2. **TEXT-04** — Edit the recognized OCR text inline in a box to correct recognition mistakes.
3. **TEXT-05** — Add a manual translation as a second text field per box (clean seam for future machine translation).

The central insight: **Phase 3 already shipped the box scaffold.** Alt+drag draw-to-create makes an empty user box (`canvas.py:_begin_create_box`); `PageBox` (`core/box_model.py`) composes the vendored `Box` and carries a `payload` (`TextBlock`) whose `.text` / `.translation` / `.vertical` / `.language` slots were reserved for Phase 4; `BoxItem` (`gui/box_item.py`) renders the box; the BOXES undo stack + per-page persistence seam exist. The `OCRModel` adapter ABC exists (`adapters/base.py`) but `backend_factory("ocr")` raises `NotImplementedError("OCR adapter lands in Phase 4")`. **Phase 4 fills the boxes with text** — it wires the manga-ocr adapter, surfaces the recognized text inline on the box, adds a translation field, and renders text on the canvas (a deliberate upgrade from Phase 3's "boxes are not display objects" stance, now that text exists).

**In scope:**
(a) the `TorchOCRModel` adapter (manga-ocr, via the `OCRModel` ABC + `backend_factory("ocr")`), filling the Phase 1 stub;
(b) auto-OCR on Alt+drag draw-release + a "Run OCR" action (selected box) + "OCR All Boxes on Page" action (Ctrl+R);
(c) inline text editing via double-click → transient `QTextEdit` overlay on the box rect;
(d) a sidebar/inspector panel (new) carrying the secondary text field;
(e) per-box translation field with a `set_translation()` seam for future MT;
(f) **bubble numbering** in reading order (RTL/TB manga default + LTR manhwa + per-box manual override) with **visible numbers on the canvas**;
(g) a **translation parser** that ingests a typesetting-tool-format block (`[N]: text` / `[SFX -N]: *text*`, one line per box) from a paste-dialog AND a file-import, matches by bubble number, fills translation fields;
(h) persistent text rendering on the canvas (translucent overlay, art visible underneath);
(i) a "Toggle Text Overlay" visibility control (independent of mask `M` and box `Shift+M` toggles);
(j) BOXES-undo entries for text edits + OCR overwrites (with a user-edited flag so re-OCR on edited text confirms).

**Out of scope (later phases):**
- `_ocr.json` box export (PROJ-03 — Phase 5), `.mas` save/load of text (PROJ-01 — Phase 5), basic image ops crop/rotate/levels/resize (PROJ-04 — Phase 5).
- Machine translation integration (TRAN-01 — v2). The MT seam is structural (`set_translation()` on the box model; a future `MTModel` adapter calls the same setter). Phase 4 does NOT call any MT model.
- Tesseract / non-Japanese OCR engines (D-14: manga-ocr only in v1; the adapter interface is designed so other engines plug in later).
- ONNX OCR backend on a separate pyenv (D-14: plan-for-it via the adapter; Phase 1 D-09b fallback — single env in v1).
- SFX bubble matching in the translation parser (D-15: skipped for v1; the parser recognizes the `[SFX -N]: *text*` line shape but does not match SFX lines to boxes).
- Typesetting / rendering translated text into the page (TRAN-02 — v2; PROJECT.md Out of Scope). Phase 4 renders text as a translucent overlay for review/correction, not as final typeset output.
- Per-line translation (D-13: one translation per box in v1; per-line is a possible future extension).
- Batch OCR across a chapter (FLOW-04 — v2; Phase 4 is per-page).

</domain>

<decisions>
## Implementation Decisions

### OCR trigger & scope (TEXT-02)
- **D-01:** **Both OCR paths.** Alt+drag-to-draw runs manga-ocr **automatically on draw-release** (the common case — one gesture yields a box with recognized text), AND a separate **"Run OCR" action** fills the selected box(es). The draw gesture from Phase 3 (`canvas.py:_begin_create_box`) is preserved; Phase 4 appends the OCR call after the empty-box commit. TEXT-02's wording ("draw a rectangle AND run manga-ocr on just that region") reads as one combined action — the auto-on-draw path honors that literally; the separate action covers re-OCR and detected-box fill.
- **D-02:** **OCR runs on BOTH box origins** — user-drawn (amber, from Alt+drag) AND detected (green, from Phase 3 CTD detection). CTD detection finds regions but does NOT run recognition, so detected boxes start with empty `TextBlock.text`; "Run OCR" / "OCR All" fills them. Matches the phase goal's "auto-detected regions OR manually drawn."
- **D-03:** **"OCR All Boxes on Page" action (Ctrl+R).** Fills every box on the current page that has no recognized text yet (one model load, sequential per-box recognition, status-bar progress reusing the Phase 2 batch progress pattern). Aligns with Phase 5's `_ocr.json` export, which needs text on every box. The action skips boxes that already have text unless the user confirms overwrite (see D-04).
- **D-04:** **Re-OCR respects a user-edited flag.** Running OCR on a box that already has recognized text: **silent overwrite if the text is raw OCR output** (never hand-edited); **confirm dialog if the user has hand-edited the text** ("This will overwrite your edit"). Requires an `edited` flag on the recognized-text field (set true by the inline editor / sidebar edit on commit, false after OCR). Mirrors Phase 3 D-03 (re-detect replaces detected boxes silently) and Phase 3 D-12 (undo recovers), but protects the user's manual corrections specifically. "OCR All" (D-03) applies the same rule per box.

### Inline text-edit surface (TEXT-04)
- **D-05:** **Inline overlay on the box.** Double-click a box → a transient `QTextEdit`/`QLineEdit` appears ON the box rect (positioned/sized to the box on the canvas); type to correct; Enter or click-away commits, Esc cancels. Most literal reading of TEXT-04 "inline in a box." The editor is a transient overlay, not a persistent widget — it appears on double-click and disappears on commit.
- **D-06:** **Inline editor defaults horizontal; per-box toggle to vertical.** The editor renders text horizontally by default (a normal text edit). A per-box toggle flips the editor to vertical (top-to-bottom, right-to-left columns) for users who want to edit in the source orientation of vertical manga. The `TextBlock.vertical` flag (from CTD detection) is ALWAYS preserved on the model regardless of editor mode — orientation is export metadata, the toggle is edit-UX.
- **D-07:** **Double-click = edit, single-click = select/move/resize.** Phase 3's D-07 ("boxes always interactive when the layer is visible — no new tool mode") is preserved. Single-click selects/moves/resizes (Phase 3 behavior intact); double-click enters edit mode (the transient overlay). Edit mode disables move/resize while active. NO new tool added to the mask `QActionGroup`. Standard double-click-to-edit convention.
- **D-08:** **Inline editor edits the "current focus" field; a sidebar carries the secondary field.** The inline overlay edits **translation if a translation exists, else recognized text.** A new **sidebar/inspector panel** (Phase 4 adds this) shows the OTHER field, always editable there. So:
  - No translation yet → inline editor shows/edits recognized text; sidebar shows the (empty) translation field.
  - Translation exists → inline editor shows/edits translation; sidebar shows recognized text.
  Both fields are always editable via one surface or the other; the inline primary reflects what the user is currently working on. The sidebar is the secondary edit home and the always-present view of both fields + metadata (bubble number, origin, language, vertical flag).

### Text display on canvas (TEXT-04 + TEXT-05)
- **D-09:** **Text IS rendered persistently on the canvas** — boxes become display objects now that text exists. This is a deliberate upgrade from Phase 3's "boxes are correction objects, not display objects" stance (Phase 3 had no text to render; Phase 4 does). Rendered via a `QGraphicsTextItem` (or equivalent) layered with the box.
- **D-10:** **Canvas renders the "current focus" text — translation when present, else recognized.** Consistent with D-08's inline-editor focus rule across both surfaces: the canvas shows the reader-facing text (translation once it exists; recognized text until then). A box never shows both simultaneously on the canvas.
- **D-11:** **Translucent overlay treatment.** Text is drawn ON TOP of the artwork inside the box rect, readable color + outline (white text + dark outline for legibility on any artwork background), art visible underneath. Does NOT block/cover the underlying manga art. `QGraphicsTextItem` with outline rendering. NOT an opaque caption (that risks v2 typesetting territory, PROJECT.md Out of Scope).
- **D-12:** **Separate "Toggle Text Overlay" visibility control**, independent of the mask overlay toggle (`M`) and the box overlay toggle (`Shift+M`). Three independent visibility layers: mask overlay / box borders / text overlay. Mirrors Phase 3 D-02's "each layer independently toggleable" principle. Lets the user inspect pure artwork or pure geometry when needed.

### Translation field & MT seam (TEXT-05)
- **D-13:** **One translation per box; `set_translation()` seam.** Translation is a single string per box, stored on `TextBlock.translation` (the slot reserved since Phase 3) via a `set_translation(text)` method on the box model. The seam: a future MT adapter (TRAN-01, v2) calls the same setter — no core changes. Per-line translation is NOT in v1 (a possible future extension; `TextBlock.text` is already a list so the data shape could grow, but Phase 4 uses box-level).
- **D-14:** **manga-ocr via the `OCRModel` adapter, with config hooks designed-in (not built-out).** v1 implements manga-ocr ONLY (hardcoded `kha-white/manga-ocr-base`, Japanese manga specialist), but routed through the existing `OCRModel` adapter ABC as a new `TorchOCRModel` (filling the Phase 1 `backend_factory("ocr")` stub). The adapter has designed-in hooks for **model selection, language selection, and backend** so a future `ONNXOCRModel` running on a separate pyenv (Phase 1 D-09 env split) plugs in without core changes. **No tesseract, no full PanelCleaner OCR config UI surface in v1** — just the adapter interface shaped for later config. Phase 1 D-09b fallback: single env in v1, ONNX split is later. PanelCleaner's `MangaOcr` wrapper (`../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py`) is the vendor reference (singleton `MangaOcr` + `kha-white/manga-ocr-base` HF model).
- **D-15:** **Phase 4 ships the translation parser + bubble numbering (full TEXT-05 subsystem).** Manual typing is the base, PLUS:
  - **(a) Auto bubble-numbering** in reading order — **RTL/top-to-bottom (manga default) + LTR/top-to-bottom (manhwa)** — with **per-box manual override**.
  - **(b) Visible bubble numbers on the canvas** (rendered with/alongside the box).
  - **(c) A translation parser** that ingests a typesetting-tool-format block and matches lines to bubbles by number, filling translation fields.
  - **(d) SFX matching SKIPPED for v1** (the parser recognizes the `[SFX -N]: *text*` line shape but does not match SFX lines to boxes).
  The parser's input format (the contract it must handle), refined by the user:
  ```
  [Bubble Number]: [translated line 1]
  [SFX -SFX Number]: *sfx line 2*
  [Bubble Number]: [translated line 3]
  ```
  Rules: numeric bubble numbers only (no `S1-X` / `FT` / `N` notation labels), no Japanese text, one line per text box exactly as it would appear on the page.
- **D-16:** **Page-level auto-number + per-box manual override.** A page-level "auto-number RTL/TB" action (manga default) and an "auto-number LTR/TB" action (manhwa) assign numbers 1..N to all boxes in that order. Per-box manual override: the user can assign any number to a box; manual overrides stick when a page-level re-auto runs (planner decides the conflict policy — e.g. manual numbers are preserved, gaps left in the auto sequence; or re-auto resets all). Auto gives a starting point; manual override handles the edge cases the auto algorithm gets wrong.
- **D-17:** **Parser has two input front-ends — paste-dialog AND file-import.** Shared parser core. Paste-dialog: a `Load Translations…` action opens a dialog with a `QPlainTextEdit` paste-area, user picks the page (or "current page"), clicks Apply, parser matches `[N]: text` lines to bubble numbers on that page, fills translation fields. File-import: imports a text file (the saved model output — one page-block per file or a multi-page file with Page markers), parser handles multiple pages. Paste is for quick single-page; file is for chapter-scale.
- **D-18:** **Page-global bubble numbers; panels ignored.** The parser keys ONLY off `[Bubble Number]`, which is page-global: bubbles 1..N across the whole page in reading order, regardless of which manga panel they sit in. The translation model's Page/Panel structure is flattened to "Page → numbered bubbles." Panels are visual grouping the parser discards. Matches the user's refined output format ("one line per text box, numeric bubble numbers only").

### Claude's Discretion
- **Exact widget choice for the inline editor** (D-05) — `QTextEdit` vs `QLineEdit` vs a custom delegate; vertical-mode implementation (D-06) is non-trivial in Qt (custom layout / writing-mode) — researcher/planner confirm the approach. A `QGraphicsTextItem` in edit mode vs a proxy `QLineEdit`/`QTextEdit` parented to the canvas are both candidates.
- **The sidebar/inspector panel structure** (D-08) — Qt dock widget vs a fixed side panel vs a popover; field layout (recognized / translation / bubble-number / origin / language / vertical flag). Follow the Phase 1 UI-SPEC visual contract.
- **The `edited` flag's home** (D-04) — on the recognized-text field itself (a parallel bool) vs derived from "text differs from last OCR output" vs on the box model. Planner decides.
- **Conflict policy for page-level re-auto vs manual override** (D-16) — whether re-auto resets manual overrides or preserves them (leaving gaps). Planner decides the least-surprising rule.
- **Reading-order auto-number algorithm** (D-15/D-16) — the RTL/TB and LTR/TB sort key (column-bucketing then top-to-bottom, or a纯 geometric sweep). Likely a column-detection + per-column-top-to-bottom sort; researcher/planner pick the algorithm and its thresholds.
- **Text-overlay font/size/scaling** (D-11) — fixed viewport-px vs scene-units (scales with zoom) vs proportional to box size; outline width. Must stay readable across zoom levels without overwhelming artwork; planner picks against the UI-SPEC.
- **Toggle Text Overlay keybinding** (D-12) — pick a key distinct from `M` (mask) and `Shift+M` (box). Researcher/planner confirm against existing bindings.
- **Parser error handling** (D-15/D-17) — what happens when a `[N]:` line's number doesn't match any bubble (skip + report? assign to nearest? error?). Report unmatched lines to the user; planner decides the recovery UX.
- **Where the "Run OCR" / "OCR All" / "Load Translations…" actions live in the UI** — most likely a Text menu (or extending the existing Tools/Edit menus) + toolbar buttons. Follow Phase 1/3 menu structure.
- **OCR worker threading** — manga-ocr is a heavy model call; route through the existing `Worker(QRunnable)` + `QThreadPool` + `_op_running` gate (Phase 1/2 pattern). One model load per session (singleton, mirroring PanelCleaner's `MangaOcr` singleton); researcher confirms the load-once strategy.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — PanelCleaner (GPL v3) foundation; model adapter interface (the `OCRModel` ABC is the Phase 4 seam); frontend/backend env split (D-07/D-09b — single env in v1, ONNX split later); **manual translation now, MT is a v2 seam** (Key Decisions table — drives D-13/D-14). Manga-ocr (Japanese) is the OCR model assumption.
- `.planning/REQUIREMENTS.md` — **TEXT-02** (draw rect + run manga-ocr → box with text), **TEXT-04** (edit recognized text inline in a box), **TEXT-05** (manual translation as a second field per box, clean seam for MT). Traceability maps all three to Phase 4. v2 TRAN-01 (MT service) and TRAN-02 (typesetting) are explicitly deferred.

### Phase Scope
- `.planning/ROADMAP.md` §Phase 4 — Goal ("User can recognize text in boxes (auto-detected regions or manually drawn), correct OCR mistakes, and add manual translations — the core differentiator no existing tool offers interactively"), 3 success criteria, requirements TEXT-02/04/05, "UI hint: yes", Depends on Phase 3.

### Prior Phase Context (carries forward — the foundation Phase 4 builds on)
- `.planning/phases/03-text-box-detection-interaction/03-CONTEXT.md` — **THE most important ref.** Phase 3 shipped the box scaffold Phase 4 fills: `PageBox` (composes vendored `Box`, carries `payload=TextBlock` with reserved `.text`/`.translation`/`.vertical`/`.language`), `BoxItem` (green detected `#5fd068` / amber user `#f5a623`), Alt+drag draw-to-create empty user boxes, BOXES undo stack (D-10) + unified Ctrl+Z timeline (D-11), per-page box persistence (mirrors Phase 2 D-11), D-07 ("boxes always interactive, no new tool mode" — D-07 here preserves it), D-12 ("delete is silent, undo recovers" — D-04 here mirrors the undo-safety pattern), the D-15 selective-inpaint seam (`PageBox.mask`/`std_dev` left `None` — Phase 4 does NOT fill these; they belong to a later inpaint phase).
- `.planning/phases/01-cleaning-workspace/01-CONTEXT.md` — the foundation: model adapter interface (D-01 `OCRModel` base class with `load`/`recognize`/`preprocess`/`postprocess`/`configure`/`get_info`; D-02 per-model backend config; D-03 modular swapping), code organization (D-10: `adapters/` + `panelcleaner/` vendored + `gui/` + `core/`), vendoring policy (D-12: PanelCleaner near-verbatim GPL v3→GPL v3; MangaCleaner_GPU reference-only), env strategy (D-07/D-08/D-09/D-09b — single env in v1), the 2-stack undo (D-01-06), Pitfall-2 `.copy()` discipline.
- `.planning/phases/02-cleaning-output-batch/02-CONTEXT.md` — **batch progress + per-page persistence pattern.** D-10 (status-bar page-count + current-name progress, reuses `progress_bar` + `status_bar_left` — D-03 "OCR All Boxes" follows this), the `Worker(QRunnable)` + `SharableFlag` abort + `_op_running` gate (D-05/D-08/D-09), per-page state persistence `.copy()` at both boundaries (D-11 — the boxes/text slot follows the same seam as the mask slot).

### Source References (PanelCleaner — GPL v3, the reference to vendor for OCR)
- `../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py` — **`MangaOcr` wrapper class** (singleton pattern, `MangaOcrModel` from the `manga_ocr` package, `__call__(img_or_path) → str`). **THE vendor reference for `TorchOCRModel.recognize()`** (D-14). Singleton load-once strategy is proven here; Phase 4 mirrors it. ~45 lines, low dep surface (loguru, PIL, manga_ocr).
- `../PanelCleaner/pcleaner/ocr/ocr.py`, `ocr_tesseract.py`, `parsers.py`, `supported_languages.py` — the broader PanelCleaner OCR module. `ocr.py` has the OCR driver; `supported_languages.py` has the `LanguageCode` enum (incl. `detect_box`); `parsers.py` has text-parsing helpers. Researcher maps which of these Phase 4 needs (likely just `ocr_mangaocr.py` + maybe `supported_languages.py` for the language hook) vs which pull tesseract deps (avoid). D-14: tesseract is OUT for v1.
- `../PanelCleaner/pcleaner/model_downloader.py` — **`OCR_DIR_NAME = "models--kha-white--manga-ocr-base"`** (line 20) + `MangaOcr()` init at line 248. The model-fetch/cache logic to reuse (mirrors Phase 1's `_resolve_detection_model_path` / `_resolve_inpainting_model_path` for the OCR model — first-run download + cache-check). HuggingFace `kha-white/manga-ocr-base`.
- `../PanelCleaner/pcleaner/config.py` — the OCR config fields (lines 374-468): `ocr_enabled`, `ocr_use_tesseract`, `ocr_language` (LanguageCode, default `detect_box`), `ocr_engine` (OCREngine.AUTO), `ocr_max_size` (30*100 px²), `ocr_blacklist_pattern` (`"[～．ー！？０-９~.!?0-9-]*"`), `ocr_strict_language`. **D-14: these are NOT surfaced in v1 UI**, but the adapter interface (D-14) is designed so they CAN be wired later. Researcher notes which (if any) are load-bearing for v1 correctness (e.g. `ocr_max_size` gating oversized regions, `ocr_blacklist_pattern` stripping junk — may be worth applying internally even without a UI surface).
- `../PanelCleaner/pcleaner/comic_text_detector/utils/textblock.py` — **`TextBlock` class** (vendored in Phase 1): fields `xyxy`, `lines`, `vertical`, `language`, `text` (list), `translation` (str, default `""`). **Phase 4 fills `text` and `translation`.** `get_text()` (line 203) joins `text` list → str; `vertical`/`language` preserved through Phase 3 and read by Phase 4 for D-06 (vertical editor toggle) and Phase 5 export. Do NOT strip these slots.
- `../PanelCleaner/LICENSE` — GPL v3. Phase 4 vendors `ocr_mangaocr.py` (and any needed sibling) near-verbatim per Phase 1 D-12 (GPL v3 → GPL v3, license-compatible). MangaCleaner_GPU remains reference-only.

### Existing Code (Phase 1-3 — what Phase 4 builds on)
- `manga_ai_studio/adapters/base.py` — **`OCRModel` ABC** (line 71): abstract `recognize(image) → str`, `preprocess`, `postprocess`. **THE seam `TorchOCRModel` implements** (D-14). Already designed per Phase 1 D-01.
- `manga_ai_studio/adapters/factory.py` — **`backend_factory("ocr", ...) → raise NotImplementedError("OCR adapter lands in Phase 4")`** (line 50-51). **THE stub Phase 4 replaces** with `TorchOCRModel` resolution (D-14). `ocr_backend` config key (line 11) is the model-selection hook.
- `manga_ai_studio/adapters/torch_impl.py` — **`TorchCTDModel` / `TorchLamaModel`** (the patterns `TorchOCRModel` follows: `load()` resolves + caches the model, the call returns plain numpy/str, thread-safe off-GUI-thread). `TorchOCRModel.recognize(image_region_ndarray) → str` mirrors these.
- `manga_ai_studio/core/box_model.py` — **`PageBox`** (composes vendored `Box`; `payload` = TextBlock; `mask`/`std_dev` = D-15 inpaint seam, left `None`). **Phase 4 adds**: recognized-text handling (fill `payload.text` via OCR; the `edited` flag from D-04), `set_translation(text)` (D-13, writes `payload.translation`), bubble-number field (D-15/D-16, a new slot with manual-override tracking). The vendored `Box` stays near-verbatim; new fields layer on `PageBox` (composition, D-14 anti-pattern honored).
- `manga_ai_studio/gui/box_item.py` — **`BoxItem(QGraphicsRectItem)`** (composes `PageBox`; green detected / amber user; corner handles). **Phase 4 adds**: text rendering (D-09/D-10/D-11 — a child `QGraphicsTextItem` or paint override for the translucent overlay), bubble-number rendering (D-15), the double-click → edit-mode entry (D-05/D-07), the vertical-mode toggle (D-06). Origin hues + selection affordance stay.
- `manga_ai_studio/gui/canvas.py` — **`EditorCanvas(QGraphicsView)`**. **Phase 4 hooks**: `_begin_create_box` (line 1402 — append auto-OCR on commit, D-01), mouse-event dispatch for double-click → edit-mode (D-05/D-07), the text-overlay layer (between box layer and preview/cursor, per D-09 z-order), Toggle Text Overlay (D-12). The `_create_anchor` / `_commit_create` flow is the seam for D-01's auto-OCR.
- `manga_ai_studio/gui/main_window.py` — **`MainWindow`**. **Phase 4 hooks**: `_on_detection_finished` (already builds boxes from `blk_list` — OCR is a separate op, not here), new `_run_ocr_task` (selected box) + `_run_ocr_all_task` (page, D-03) dispatchers following the Phase 1/2 `Worker` pattern, the "Run OCR" / "OCR All (Ctrl+R)" / "Load Translations…" actions wired into `_build_menus`/`_build_toolbar`, the sidebar/inspector panel instantiation (D-08), the page-level auto-number actions (D-16), the `_op_running` gate reuse, status-bar progress reuse (D-03). `box_origin_counts()` (line 1302) extends to text/translation counts if useful.
- `manga_ai_studio/core/history_manager.py` — **the 3-stack HistoryManager** (MASK + IMAGE + BOXES, unified timeline). **Phase 4 adds**: BOXES-stack entries for text edits + OCR overwrites (D-04 — the `edited` flag travels with the snapshot). The Phase 3 BOXES snapshot shape (full per-page boxes list per op) extends to carry text/translation state in the `PageBox` payload — no new stack, just richer snapshots.
- `manga_ai_studio/core/image_file.py` — **`ImageFile`** (`path`, `thumbnail`, `mask`, `boxes`, `dirty`). **Phase 4**: text/translation live on the `PageBox` payload within `boxes`, so the `boxes` slot (Phase 3) already carries them — verify persistence (D-11 Phase 2 seam) round-trips text/translation, not just bboxes. No new slot likely needed unless bubble-number override is stored separately.
- `manga_ai_studio/gui/worker_thread.py` — **`Worker(QRunnable)` + `WorkerSignals` + `SharableFlag`**. **Phase 4 reuses directly** for the OCR worker (one model call per box, or a page-loop worker for "OCR All"). OCR is a heavy model call — must run off the GUI thread per the Phase 1 thread-safety contract (T-01-07).
- `manga_ai_studio/config/profile_manager.py` — **ProfileManager**. **Phase 4**: likely NO change for v1 (D-14: no OCR config UI surface). The adapter reads manga-ocr defaults internally. If `ocr_backend` config key is wired (D-14 hook), it defaults to `"torch"`; researcher confirms whether the config key needs a ProfileManager entry or stays adapter-internal for v1.

### UI / Design contract
- `.planning/phases/01-cleaning-workspace/01-UI-SPEC.md` — the design contract: color tokens (accent `#00d4ff` reserved use, canvas matte `#0b0b0e`, secondary surface `#2d2d33`), spacing scale, the "artwork is the sole saturated surface" principle (D-11 translucent text overlay must respect this — text is a desaturated overlay, not a new saturated surface). D-09 (text rendering) and D-12 (text toggle) must stay consistent. **Phase 4 has `UI hint: yes` — a `/gsd-ui-phase 4` pass will likely follow this discuss step** (the sidebar panel + inline editor + text overlay + bubble numbers are all new UI surface).

### Licensing
- `../PanelCleaner/LICENSE` — GPL v3. Phase 4 vendors `ocr_mangaocr.py` near-verbatim per Phase 1 D-12 (GPL v3 → GPL v3, license-compatible). Consumption of `TextBlock` (vendored Phase 1) and `PageBox` (Phase 3) is derivative use. The new UI code (inline editor, sidebar, text overlay, parser) is our own. MangaCleaner_GPU remains reference-only (no LICENSE).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`OCRModel` ABC + `backend_factory("ocr")` stub** (`adapters/base.py:71`, `adapters/factory.py:50`) — the seam is pre-built; Phase 4 fills it with `TorchOCRModel`. No new adapter plumbing.
- **`TorchCTDModel` / `TorchLamaModel`** (`adapters/torch_impl.py`) — the exact pattern `TorchOCRModel` follows: `load()` resolves + caches the model, the inference call returns plain numpy/str, thread-safe. `TorchOCRModel.recognize(image_region_ndarray) → str` mirrors `TorchLamaModel.inpaint`'s shape.
- **PanelCleaner's `MangaOcr` wrapper** (`../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py`) — the vendor reference for the `TorchOCRModel` internals: singleton `MangaOcrModel`, `__call__(img_or_path) → str`, load-once. ~45 lines.
- **PanelCleaner's `model_downloader.py`** (`OCR_DIR_NAME = "models--kha-white--manga-ocr-base"`) — the model-fetch/cache logic. Phase 1's `_resolve_detection_model_path` / `_resolve_inpainting_model_path` (`main_window.py`) are the templates for `_resolve_ocr_model_path` (first-run download + cache-check; do NOT re-download the ~450MB model on every session).
- **`PageBox` + `BoxItem` + BOXES stack** (Phase 3) — the box scaffold. Phase 4 fills the `payload.text`/`.translation` slots (reserved since Phase 3) and adds text rendering + bubble-number to `BoxItem`. The vendored `Box` stays untouched (D-14 anti-pattern).
- **Alt+drag draw-to-create** (`canvas.py:_begin_create_box:1402`, `_commit_create:985`) — Phase 3 made empty user boxes; Phase 4 appends the auto-OCR call after `_commit_create` (D-01). The gesture is preserved.
- **`Worker(QRunnable)` + `SharableFlag` + `_op_running` gate** (Phase 1/2) — reused directly for the OCR worker (D-03 "OCR All" page-loop + single-box OCR). manga-ocr is heavy; must run off the GUI thread.
- **Status-bar progress UI** (`main_window.py:_build_status_bar`) — `progress_bar` (3px) + `status_bar_left` (text). "OCR All Boxes on Page" (D-03) writes here — no new widgets (Phase 2 D-10 pattern).
- **BOXES undo stack + unified Ctrl+Z** (Phase 3 D-10/D-11) — text edits + OCR overwrites push BOXES snapshots (D-04). The Phase 3 snapshot shape (full per-page boxes list) extends to carry text/translation in the payload — no new stack.
- **Per-page persistence `.copy()` seam** (Phase 2 D-11 / Phase 3 boxes-slot) — text/translation ride along on `PageBox` payload within the `boxes` slot; verify the round-trip persists them (not just bboxes).

### Established Patterns
- **Pitfall 2 (`.copy()` buffer discipline)** — every numpy↔QImage / numpy↔history bridge detaches. OCR returns a str (no buffer issue), but the image-region passed INTO manga-ocr (cropped from the page numpy) must be a clean copy if held; the recognized-text str is immutable and safe.
- **In-process `QThreadPool` (Phase 1/2 D-09b)** — single env, models called off the GUI thread via `Worker`. OCR follows identically. No multiprocessing.
- **Thread-safety contract (T-01-07)** — OCR worker touches only numpy/Python + emits signals; Qt mutation (filling the box's text, updating the canvas text overlay) only in main-thread handlers.
- **3-stack undo + unified timeline (Phase 3 D-10/D-11)** — text edits + OCR overwrites are BOXES-stack entries; the unified Ctrl+Z pop order is unchanged.
- **Confirm-gate before destructive replace** (`_confirm_replace_mask`, Phase 3 D-04) — D-04's "confirm re-OCR on user-edited text" mirrors this. Silent overwrite on raw OCR text mirrors Phase 3 D-03/D-12.
- **Model-load error UX (T-01-08)** — tracebacks to loguru, user-friendly copy in the dialog/error chip. OCR model load (first-run ~450MB download) reuses Phase 1's model-path resolution + error UX.
- **Per-page persistence `.copy()` at both boundaries** (Phase 2 D-11 / T-02-04) — the text/translation state follows the same belt-and-suspenders copy discipline as mask/boxes.

### Integration Points
- **`_commit_create`** (`canvas.py:985`) — primary seam for D-01 auto-OCR on draw-release. Append the OCR call after the empty-user-box commit.
- **`BoxItem`** — text-overlay child item (D-09/D-10/D-11), bubble-number rendering (D-15), double-click → edit-mode (D-05/D-07), vertical toggle (D-06).
- **`PageBox`** — `set_translation()` (D-13), recognized-text + `edited` flag (D-04), bubble-number + override tracking (D-15/D-16). New fields layer via composition; vendored `Box` untouched.
- **`MainWindow`** — `_run_ocr_task` / `_run_ocr_all_task` dispatchers; "Run OCR" / "OCR All (Ctrl+R)" / "Load Translations…" / page-level auto-number actions; sidebar/inspector panel instantiation; `_op_running` gate reuse.
- **`HistoryManager`** — BOXES snapshots now carry text/translation state (richer payload, no new stack).
- **`backend_factory("ocr")`** — replace the `NotImplementedError` stub with `TorchOCRModel` resolution (D-14).
- **New: sidebar/inspector panel** (D-08) — a new dock/side panel showing the selected box's non-inline field + metadata (bubble number, origin, language, vertical flag). First new panel since Phase 1's `ToolsPanel`/`FileTable`.
- **New: translation parser module** (D-15/D-17) — a new `core/` or `ocr/` module: parse `[N]: text` / `[SFX -N]: *text*` blocks, match by bubble number, fill `set_translation()`. Two front-ends (paste-dialog, file-import).

</code_context>

<specifics>
## Specific Ideas

- **"Boxes are correction objects, not display objects" is OVER for Phase 4.** Phase 3's CONTEXT said this explicitly because Phase 3 had no text. Now that text exists, D-09 upgrades boxes to display objects — text renders persistently on the canvas. This is the single biggest philosophical shift from Phase 3, and it's deliberate (the user's D-09/D-10/D-11 answers).
- **The "current focus" rule is consistent across all surfaces.** D-08 (inline editor), D-10 (canvas rendering) — both show **translation when present, else recognized text.** The reader-facing text is the primary; the source text is secondary once a translation exists. This is the user's explicit mental model (the "if a translation has already been made, the inline editor should show and edit the translation" answer).
- **The translation subsystem is the phase's standout feature.** D-15/D-16/D-17/D-18 — bubble numbering (RTL manga / LTR manhwa + manual override + visible on canvas) + a typesetting-tool-format parser (paste + file import, page-global numbers, SFX skipped) — is a real sub-feature beyond a simple "second text field." It reflects the user's actual scanlation workflow (an external translation model outputs the typesetting-tool format; Phase 4 ingests it). The refined parser format (`[N]: text` / `[SFX -N]: *text*`, one line per box, numeric-only) is the contract.
- **The adapter interface is the modular spine.** D-14 — manga-ocr only in v1, BUT through the `OCRModel` adapter with model/language/backend hooks designed-in. This sets up the future ONNX OCR backend on a separate pyenv (Phase 1 D-09) and matches PROJECT.md's "model adapter interface" key decision. The same shape that let Phase 1 swap detection/inpainting backends applies to OCR.
- **D-04's `edited` flag protects manual corrections.** Re-OCR silent-overwrites raw OCR text but confirms before overwriting user-edited text. This is the one place Phase 4 deviates from Phase 3's "silent + undo recovers" pattern — because re-OCR is a deliberate user re-run, and silently destroying a hand-correction is the worst-case. Undo still recovers either way.

</specifics>

<deferred>
## Deferred Ideas

- **Machine translation integration (TRAN-01)** — v2. The seam is `set_translation()` (D-13) + the `OCRModel`-style adapter shape (D-14); a future `MTModel` adapter calls the setter. Phase 4 does NOT call any MT model. PROJECT.md Out of Scope for v1.
- **Typesetting / rendering translated text into the page (TRAN-02)** — v2; PROJECT.md Out of Scope. Phase 4 renders text as a translucent review/correction overlay (D-11), not as final typeset output (no font management, auto-fit, bubble-sizing — that's BallonsTranslator territory).
- **Tesseract / non-Japanese OCR engines** — D-14: manga-ocr only in v1. The adapter interface supports adding them later via config (no UI built out now).
- **ONNX OCR backend on a separate pyenv** — D-14 plan-for-it via the adapter; Phase 1 D-09b fallback means single-env in v1. The `ONNXOCRModel` implementation is a future phase.
- **Per-line translation** — D-13: one translation per box in v1. `TextBlock.text` is already a list, so the data shape could grow to per-line, but Phase 4 is box-level. Possible future extension.
- **SFX bubble matching in the parser** — D-15: skipped for v1. The parser recognizes the `[SFX -N]: *text*` line shape but does not match SFX lines to boxes. Likely a v1.1 addition once SFX handling is scoped.
- **Batch OCR across a chapter (FLOW-04)** — v2. Phase 4 is per-page ("OCR All Boxes on Page" D-03, not "OCR all pages").
- **`_ocr.json` box export (PROJ-03) / `.mas` save/load (PROJ-01) / image ops (PROJ-04)** — Phase 5. Phase 4 persists text/translation per-page in-memory (and across navigation via the Phase 2 D-11 seam) but does NOT serialize to disk yet.
- **Selective per-box inpaint via std-deviation (Phase 3 D-15 seam)** — still deferred (Phase 3 left `PageBox.mask`/`std_dev` as `None`; Phase 4 does NOT fill them — they belong to a later inpaint phase that depends on OCR context). The seam remains open.
- **Panel-aware bubble numbering** — D-18: page-global numbers in v1; the parser ignores Panel markers. Panel-local numbering (1-1, 2-1, ...) is a possible future refinement if the model's Page/Panel structure proves useful.

</deferred>

---

*Phase: 4-OCR Recognition & Text Editing*
*Context gathered: 2026-08-04*

# Phase 5: Project Persistence, Image Ops & Export - Research

**Researched:** 2026-08-08
**Domain:** Project file serialization (custom LZMA2 container), mokuro-style JSON export, pixel-level image operations, Qt6 desktop integration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**.mas project scope & on-disk layout (PROJ-01)**
- **D-01:** **A project = a chapter (the open folder's session), split into a manifest + per-page files.** The user chose "Both (manifest + page files)" over single-file-per-chapter or per-page-sidecars. A chapter manifest groups the pages; each page gets its own `.mas` file. — **Reversibility:** one-way — the on-disk project layout is the format saved projects depend on; changing it later requires migration of existing projects.
- **D-02:** **Project folder sits beside the source folder** (mirrors the Phase 2 `cleaned/` sibling convention): e.g. `chapter-01/` → `chapter-01.mas-project/` containing `manifest.json` + per-page `<page>.mas` files (same stem as each source page). Source folders stay untouched. Exact folder-name validation (collision handling) is planner detail. — **Reversibility:** one-way — same published-layout rationale as D-01.
- **D-03:** **Per-page `.mas` files are self-contained** — each carries its own current image (embedded), mask, boxes/text, and original-path ref + checksum. A page file opens standalone OR through the manifest. The manifest holds only page order + session metadata (and per-page refs). — **Reversibility:** costly — moving state between page files and manifest later would touch every save/load path.
- **D-04:** **Container format = JSON + embedded images, LZMA2-compressed (NOT zip).** User explicitly: "JSON + embedded images but let's use LZMA2 instead of zip". Implementation: stdlib `lzma` module with `FORMAT_XZ` (LZMA2 filter) inside our own container layout (JSON manifest + embedded blobs, header with entry table) — **zero new dependencies**, matching the stdlib-light precedent of `core/image_io.py`. The manifest itself stays **plain JSON** (tiny, human-readable, diffable); the per-page files carry the compressed payloads. Researcher confirms the exact XZ/LZMA2 API surface + container layout. — **Reversibility:** one-way — the container layout is the saved-project format; changing it needs a reader migration.
- **D-05:** **Saved image state per page = the CURRENT page image only** (inpainted result if any, else original) — resume exactly where you left off, like a .psd. **Undo stacks are NOT serialized** — a reopened project starts with a fresh undo history. — **Reversibility:** costly — adding undo serialization later is additive, but the "fresh history" contract is what v1 users will rely on.
- **D-06:** **Original-path reference + checksum per page.** On open: if the original file is found at the referenced path AND its checksum matches, it is used as the base image (Show Original works). If not found/mismatched, the embedded current image is used and **Show Original is greyed out** (user: "if the image is not available just grey out the option"). Checksum algorithm is agent discretion (planner picks; sha256 is the obvious default).

**Save/Open session semantics (PROJ-01)**
- **D-07:** **Manual Save Project… (Ctrl+S) / Open Project… (Ctrl+O) with dirty tracking.** Dirty pages mark the window title (`*` convention); closing/opening with unsaved changes prompts **Save / Discard / Cancel**. Save As… exists for first save. Recent Projects join the existing Recent Files menu structure. — **Reversibility:** reversible.
- **D-08:** **Open Project rebuilds the session from the manifest** — sidebar order, per-page state (masks, boxes, text) all restored; source images re-found via path refs + checksum (D-06). Batch/export operations work on the reopened project's pages. — **Reversibility:** reversible.
- **D-09:** **Opening a per-page `.mas` file directly is supported, with manifest-climb.** Open Project… opens a manifest. Opening a page `.mas` (e.g. via the file dialog / double-click): if a sibling manifest is detected, pop a dialog — user's words: "chapter detected, open entire chapter?" — **Yes** loads the chapter via the manifest; **No** opens the single page as a standalone session. No sibling manifest → open the single page directly. — **Reversibility:** costly — the dialog contract is a UX expectation; changing the climb behavior later is easy, but the self-contained page file shape is load-bearing.

**Image-op UX & undo (PROJ-04)**
- **D-10:** **Rotation = 90° steps only (CW / CCW / 180°).** Manga scans arrive in 90° increments; steps are pixel-exact and keep mask/box transforms lossless. Arbitrary-angle rotation is deferred (v2). — **Reversibility:** reversible (deferral).
- **D-11:** **Crop = a Canvas Crop tool** — the 6th tool in the existing `QActionGroup` (Move/Brush/Rect/Lasso/Eraser/Crop): drag a rect on the page, Enter applies, Esc cancels. A numeric **Crop… dialog** (x/y/w/h) rides along in the Edit menu for precision. — **Reversibility:** reversible.
- **D-12:** **Levels = a Levels dialog** — black point, white point, gamma (3 controls) with **live preview** on the canvas. The full curve editor is v2 (deferred). — **Reversibility:** reversible.
- **D-13:** **Resize = a Resize… dialog** — width + height fields, **aspect lock on by default**, px/percentage toggle, live preview of new dims. — **Reversibility:** reversible.
- **D-14:** **All four ops are silent + IMAGE-stack undoable** — no confirm dialogs; Ctrl+Z reverses each op. **Show Original re-baselines to the post-op image** (the `_original_image_numpy` cache resets to the current state after an op). Matches Phase 3's "silent + undo recovers" philosophy (D-12). — **Reversibility:** costly — the re-baseline contract means the pre-op image is only recoverable via undo, not via Show Original.

**Image ops vs masks/boxes (PROJ-04)**
- **D-15:** **Geometry ops transform the mask AND the box geometry along with the page image.** Crop/rotate/resize are lossless to prior work — the whole point of a resumable workspace. Levels is geometry-free (pixels only; mask/boxes untouched). — **Reversibility:** one-way — the transform contract is the phase's core data invariant; deviating later (e.g. storing ops as a re-playable stack) would be a model change.
- **D-16:** **Crop edge policy: drop fully-outside boxes, clip partial boxes.** Boxes fully outside the crop rect are removed with a **count reported in the status bar**; boxes partially inside are clipped to the crop rect (their bbox and lines clamp to the new page boundary). — **Reversibility:** reversible (undo recovers the crop including dropped boxes).
- **D-17:** **Transform depth = bbox AND `TextBlock.lines` polygons together.** Rotate/scale/translate each line polygon with the box, so per-line geometry stays valid for `_ocr.json` export and future typesetting/selective-inpaint. No stale-lines shortcut. — **Reversibility:** costly — the full-payload transform is the fidelity contract; dropping it later degrades exports.
- **D-18:** **Pixel-exact mask transforms.** Rotate 90°/180° = exact `QImage` transform; resize = nearest-neighbor scale of the binary mask (no soft alpha drift); crop = exact slice. Mask overlay stays aligned pixel-for-pixel with the image. — **Reversibility:** reversible.

**_ocr.json export shape & scope (PROJ-03)**
- **D-19:** **Custom JSON shape — mokuro vocabulary PLUS our fields, INCLUDING `lines[]`.** The user overrode strict-mokuro fidelity: "mokuro vocab plus our fields, including lines, since this will be used for typesetting it is important to note in a text bubble where a line begins and ends". Shape: per-page JSON object — `version`, `img_width`, `img_height`, `blocks[]` with `box` [x1,y1,x2,y2], `vertical`, `text`, `translation`, `bubble_no`, `origin` — AND `lines[]` carrying per-line `box` + `text` so a typesetting tool knows where each line begins/ends inside a bubble. Exact field spelling/JSON layout is planner detail against this contract. — **Reversibility:** one-way — the JSON shape is a published contract consumed by downstream (typesetting) tools; changing it breaks consumers. Rationale is the user's quoted typesetting requirement above.
- **D-20:** **Per-line text comes from splitting the stored whole-text by `\n`** onto the detected `TextBlock.lines` polygons (line N gets segment N; unmatched lines export empty text). No model changes, works with today's single-str storage. The per-line storage upgrade (list in `TextBlock.text`) was considered and **rejected for v1**. — **Reversibility:** costly — the `\n`-split mapping is the export contract; upgrading to true per-line storage later changes both the model and the export.
- **D-21:** **Export scope = single page + batch.** "Export OCR JSON…" (current page, Save As dialog) in the Text menu; "Batch Export OCR JSON" in the Batch menu writes every page of the open folder. Mirrors Phase 2's single-export + batch-action structure. Serialization is model-free and fast (no Worker needed unless the planner decides otherwise). — **Reversibility:** reversible.
- **D-22:** **Output location follows page state.** Pristine page (no geometry ops): sidecar `<name>_ocr.json` **next to the source page** (mokuro naming convention). Geometry-altered page (crop/rotate/resize applied): the JSON is written into **`cleaned/`** instead, because its coordinates describe the post-op page, not the image sitting next to it. Coordinates + img dims always describe the **current** page state. — **Reversibility:** costly — the state-dependent location rule is the placement contract downstream tooling will rely on.

### Claude's Discretion
- **Geometry-op undo record shape (user declined to discuss this area).** Image ops push IMAGE-stack entries, but the mask/box transform (D-15) rides along — and the Phase 1 IMAGE stack stores only QImage patches. The planner must decide the record shape so **one Ctrl+Z reverses image + mask + boxes together** (one press per op, not two). A combined record entry or a paired-stack push with a merge rule are both candidates — pick the least-surprising unified-timeline behavior (Phase 3 D-11).
- **Checksum algorithm** for D-06 (sha256 default), **manifest schema fields** (versioning, per-page refs, page order, session metadata), **container entry-table layout** (D-04), **crop dialog + levels dialog widget details**, **resize interpolation**, **dirty-title format**, **project-folder collision handling** (D-02), **Recent Projects entry naming**, **menu placement** (File vs Text vs Batch for the new actions).
- **`_ocr.json` JSON spelling** — field names/snake_case vs camelCase per the D-19 contract; version string value.
- **Batch Export OCR JSON threading** — model-free serialization is fast; planner decides whether it needs the Worker/`_op_running` gate or runs inline.

### Deferred Ideas (OUT OF SCOPE)
- **Full curve editor (levels/curves, TRAN-02 adjacency)** — v2. Phase 5 ships the Levels dialog (black/white/gamma, D-12); the draggable-curve editor is a future typesetting/editing phase.
- **Arbitrary-angle rotation** — v2. Phase 5 is 90° steps only (D-10); free rotation needs interpolation + input UI + arbitrary-angle geometry math.
- **Per-line text storage** — rejected for v1 (D-20 chose `\n`-split at export). A future typesetting phase may upgrade `TextBlock.text` to a list; the export contract would then read it directly.
- **Strict mokuro `_ocr.json` compatibility** — overridden by the user (D-19 custom shape). If a downstream tool ever demands the exact mokuro schema, a converter is a small future addition.
- **Selective per-box inpaint (Phase 3 D-15 seam)** — stays open and untouched: `PageBox.mask`/`std_dev` remain `None` through Phase 5; geometry transforms must preserve the seam (transform lines/bbox only).
- **Undo-stack serialization in `.mas`** — rejected (D-05, fresh undo history on reopen).
- **Batch OCR across a chapter (FLOW-04), batch→editor round-trip (FLOW-05), typesetting output (TRAN-02)** — v2, unchanged.
</user_constraints>

## Summary

Phase 5 serializes state that Phases 1–4 already built — masks live on `ImageFile.mask` (Phase 2 D-11 slot), boxes/text/translation/bubble numbers live on `ImageFile.boxes` → `PageBox` payloads (Phases 3–4), the current image lives on the canvas (`get_image_numpy`/`set_image_from_numpy` round-trip), and the 3-stack unified Ctrl+Z exists (Phase 1/3). **Phase 5 puts this state on disk** (`.mas` project = chapter manifest + self-contained per-page files, stdlib `lzma` `FORMAT_XZ` container per the locked D-04 decision) **and adds pixel-level page editing** (crop/rotate/levels/resize) that transforms the image AND mask/box geometry together.

**Zero new dependencies are required.** The container uses stdlib `lzma` (`FORMAT_XZ` = LZMA2, verified round-tripping on the project's Python 3.14.2), `json`, and `hashlib` (sha256 for D-06 checksums); image ops use the already-installed Pillow 12.0.0 + numpy 2.3.5; the `_ocr.json` exporter is a pure projection of `PageBox`/`TextBlock` state. Three new headless core modules (`core/project_io.py`, `core/ocr_export.py`, `core/image_ops.py`) mirror `core/image_io.py`'s pure-stdlib+numpy+PIL discipline. The mokuro schema vocabulary was verified against mokuro's official source (`manga_page_ocr.py`): `version`/`img_width`/`img_height`/`blocks[].box|vertical|lines` — D-19 extends it with `text`/`translation`/`bubble_no`/`origin` plus per-line `box`+`text`.

**Primary recommendation:** Build the three headless core modules first (Wave 1), then the geometry-op undo record as a **stamp-shared triple push** (one monotonic stamp across IMAGE+MASK+BOXES, with `HistoryManager.undo/redo` extended to pop every store whose tail stamp matches the max — one Ctrl+Z reverses image+mask+boxes together, preserving the Phase 3 unified timeline), then wire the GUI (menus, Crop as the 6th `ToolMode`, three dialogs) last.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROJ-01 | Save the full page state (image, masks, boxes, text, translation) as a `.mas` project file and reopen it to resume work | D-01…D-09 locked layout: `core/project_io.py` container design (lzma FORMAT_XZ entry-table layout below), `ImageFile`/`PageBox` serialization mapping (all state verified in-repo), original-path+sha256 rule (D-06), manifest rebuild + D-11-seam restore (D-08), chapter-climb (D-09) |
| PROJ-03 | Export OCR/box data as a mokuro-style `_ocr.json` file per page for use in downstream tools | mokuro vocabulary verified from official source; D-19 extension shape (per-line `box`+`text`); D-20 `\n`-split onto `TextBlock.lines` polygons; D-22 pristine→source-folder / altered→`cleaned/` location rule; `core/ocr_export.py` pure-projection design |
| PROJ-04 | Apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize | `core/image_ops.py` pure numpy+PIL transforms (np.rot90 pixel-exact, numpy slice crop, PIL LANCZOS/NEAREST resize, numpy LUT levels); D-15/D-17 geometry transforms on bbox AND lines polygons; D-16 drop/clip; D-18 pixel-exact mask; stamp-shared triple-push undo record (below) |
</phase_requirements>

## Project Constraints (from .claude/CLAUDE.md)

No `./AGENTS.md` exists. `.claude/CLAUDE.md` (GSD-generated from PROJECT.md/STACK.md) carries the actionable directives:

- **GSD workflow enforcement:** "Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync… Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it." [VERIFIED: .claude/CLAUDE.md:142-153]
- **Tech stack:** PyQt/PySide desktop GUI, Python backend — non-negotiable; Windows-first for v1; avoid Windows-only APIs and hard-coded paths; single environment preferred (isolated pyenvs are the fallback). [VERIFIED: .claude/CLAUDE.md:13-17]
- **GPL v3:** derivative of PanelCleaner — preserve GPL v3 in all distributions and provide source code. Phase 5 adds no new vendoring (CONTEXT canonical_refs; PROJ-04 is greenfield — PanelCleaner's `image_ops.py` is mask-fitting machinery, NOT crop/rotate/levels). [CITED: 05-CONTEXT.md:82,108]
- **pyproject.toml pins** `numpy<2` but the working env has numpy 2.3.5 with 461 tests green — do not re-pin; do not add new dependencies. [VERIFIED: pyproject.toml:25, local probe]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `.mas` container (LZMA2 entry-table) + manifest JSON | Core (headless `core/project_io.py`) | GUI (main-window session orchestration) | Serialization is pure Python + disk I/O — thread-safe, headless-testable, mirrors `core/image_io.py`; Qt mutation stays in main-thread handlers (T-01-07) |
| Per-page state snapshot (image/mask/boxes) | Core (`project_io` projections of `ImageFile`/`PageBox`) | GUI (canvas `get_image_numpy`/`get_mask`/`boxes_snapshot` read at save time) | All serialization data already lives on the data models; the canvas is the read/write bridge (Pitfall 2 `.copy()` discipline at both boundaries) |
| `_ocr.json` export (single + batch) | Core (`core/ocr_export.py`) | GUI (menu actions + file dialogs + D-22 location decision) | Pure projection of `PageBox`/`TextBlock` state; no models; per-page failure isolation mirrors Phase 2 `batch_runner` |
| Image ops (rotate/crop/levels/resize) — pixel math | Core (`core/image_ops.py`) | GUI (dialogs, crop tool drag, apply orchestration) | numpy+PIL pure functions headless-testable; GUI owns interaction only |
| Geometry transforms (box bbox + lines polygons) | Core (`image_ops`) | GUI (canvas `set_boxes` rebuild + refresh) | Pure coordinate math on vendored `Box`/`TextBlock`; must NOT mutate the @frozen `Box` (D-14 composition discipline) |
| Geometry-op undo (one Ctrl+Z for image+mask+boxes) | Core (`HistoryManager` stamp-shared triple push + pop-all-with-stamp) | GUI (unified `on_undo`/`on_redo` apply) | The merge rule lives in the history engine; the UI collapse stays the Phase 3 surface-13 shape |
| Crop tool interaction (armed rect, dim-out, Enter/Esc) | GUI (canvas mouse/key dispatch + overlay) | Core (apply math) | Drag/armed-rect state machine is Qt event dispatch — the same place mask tools live |
| Dialogs (Levels live-preview, Resize, Crop numeric) | GUI (new dialog modules) | Core (transform fns) | Modal `QDialog.exec()` nested event loop repaints the canvas behind the dialog; preview = synchronous numpy transform |
| Save/Open session semantics (dirty tracking, prompts, Recent Projects) | GUI (main_window) | Core (save/load entry points) | Qt title/prompt/QSettings are GUI concerns; the folder format is core's contract |
| Show Original gating + re-baseline (D-06/D-14) | GUI (canvas cache + action state) | — | `_original_image_numpy` cache is canvas state; gating is `_refresh_action_states` |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `lzma` | 3.14 stdlib (FORMAT_XZ) | D-04 container compression — LZMA2 filter via `lzma.compress(data, format=lzma.FORMAT_XZ, preset=6)` | Locked by user (D-04); `FORMAT_XZ` is the `.xz` container (LZMA2), `CHECK_CRC64` is its default integrity check, preset 6 is the default; zero new deps [CITED: docs.python.org/3/library/lzma.html] + [VERIFIED: local probe — compress/decompress/streaming/open round-trips on Python 3.14.2] |
| Python stdlib `json` | 3.14 stdlib | Manifest (`manifest.json` plain JSON) + per-page `meta.json` | Manifest must stay plain, human-readable, diffable (D-04); zero deps |
| Python stdlib `hashlib` | 3.14 stdlib | D-06 original-file checksum — sha256 | User's obvious default (D-06 discretion); stdlib |
| Pillow (PIL) | 12.0.0 (installed) | Embedded page-image encode (PNG), resize interpolation (LANCZOS image / NEAREST mask), levels LUT application | Already a project dependency (`pyproject.toml:16`); `save_image_optimized` in `core/image_io.py` already uses it [VERIFIED: local probe — PIL 12.0.0 installed and probed] |
| numpy | 2.3.5 (installed) | `np.rot90` pixel-exact rotation, slice crop, binary mask transforms, LUT levels | Already installed and used everywhere (canvas numpy bridge, `mask_to_numpy_binary`) [VERIFIED: local probe] |
| PySide6 | 6.10.1 (installed) | QDialog/QFileDialog/QMessageBox/sliders/spinboxes, canvas crop overlay | The app's UI framework (inherited); UI-SPEC contracts standard Qt6 widgets only [VERIFIED: local probe] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `manga_ai_studio.core.image_io.save_image_optimized` | in-repo | PNG/JPG writer for embedded page images (DPI/mode preserved) | The D-03 embedded-image writer; write embedded PNG bytes in-memory via PIL `BytesIO` instead of touching disk |
| `manga_ai_studio.core.mask_editor.mask_to_numpy_binary` / `numpy_binary_to_mask_qimage` | in-repo | Binary (H,W) mask round-trip for `.mas` and for geometry transforms | The established mask <-> numpy boundary (D-18 pixel-exact transforms operate on the binary form) |
| `manga_ai_studio.gui.worker_thread.Worker` + `SharableFlag` | in-repo | Batch Export OCR JSON progress/abort surface | If the planner picks the Worker path (recommended — see Open Questions); model-free so it is fast either way |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `lzma` FORMAT_XZ (locked D-04) | zipfile / py7zr / zstandard | User explicitly rejected zip; py7zr adds a dependency for the same LZMA2; stdlib is zero-dep |
| numpy `np.rot90` for 90° rotations | PIL `Image.rotate` / `QTransform().rotate` | np.rot90 is pixel-exact with no interpolation ambiguity and keeps image+mask in the same coordinate frame; PIL rotate for 90° multiples is also exact but direction conventions differ across PIL/Qt — one code path (numpy) for both image and mask removes the risk |
| numpy LUT `lut[rgb]` for levels | PIL `Image.point()` | Verified empirically: RGB `point()` requires a 768-entry LUT (3×256) and raises `ValueError: wrong number of lut entries` on 256 — the numpy path is simpler and byte-identical |
| Per-page `meta.json` inside the `.mas` container | A single big JSON for the whole page file | Separating the binary blobs (image PNG, mask) from JSON keeps the entry table clean and the JSON re-usable |

**Installation:** None. `pip install` is NOT needed — Phase 5 adds zero new packages (verified: all required libraries are already installed in the working env; see Environment Availability).

**Version verification:** (already verified in this session — 2026-08-08, local probes against the project env)
```bash
& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -c "import PySide6, PIL, numpy, lzma; print(PySide6.__version__, PIL.__version__, numpy.__version__)"
# -> PySide6 6.10.1, PIL 12.0.0, numpy 2.3.5, lzma stdlib OK
```

## Package Legitimacy Audit

> Phase 5 **installs no new external packages** — the container is stdlib (`lzma`, `json`, `hashlib`), and all image ops use already-installed Pillow/numpy. The audit below covers the phase's dependency stack for completeness.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| PySide6 | PyPI | 11 yrs (v6.10.1 published 2026-05-13) | n/a (seam data unavailable) | pyside.org | [SUS — unknown-downloads only] | Approved — already installed (Phases 1–4), no install step |
| pillow | PyPI | 14 yrs (v12.0.0 published 2026-07-01) | n/a | github.com/python-pillow/Pillow | [SUS — unknown-downloads only] | Approved — already installed, no install step |
| numpy | PyPI | 20 yrs (v2.3.5 published 2026-07-04) | n/a | none recorded | [SUS — unknown-downloads + no-repository] | Approved — already installed, no install step; repo field is a seam data gap, numpy is the canonical array lib |
| loguru | PyPI | 9 yrs | n/a | github.com/Delgan/loguru | [SUS — unknown-downloads only] | Approved — already installed |
| natsort | PyPI | 12 yrs | n/a | github.com/SethMMorton/natsort | [SUS — unknown-downloads only] | Approved — already installed |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all five above carry the seam's `unknown-downloads` reason — a data-availability gap, not a real signal. No postinstall scripts (`postinstall: null` for all), no slop signals, all long-established projects, all already installed and exercised by 461 passing Phase 1–4 tests. **No `checkpoint:human-verify` tasks are needed because nothing is installed in this phase.**

*Note: all packages were discovered in-repo (`pyproject.toml` dependencies) and verified present in the working environment by local import probes — not via web search, so no `[ASSUMED]` tags apply to the stack itself.*

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────── SAVE / OPEN (PROJ-01) ────────────────────────────┐
│                                                                                │
│  MainWindow (Save Project Ctrl+S / Open Project Ctrl+O / Recent Projects)      │
│     │  flush current canvas state (on_page_selected step-1 pattern, .copy())  │
│     ▼                                                                          │
│  core/project_io.py  ──save──►  <chapter>.mas-project/                         │
│     • manifest.json (PLAIN JSON: version, name, page order, per-page refs)     │
│     • <page>.mas  (CUSTOM container: header + entry table + LZMA2 blobs)       │
│         ├─ meta.json   (boxes/text/translation/bubble_no/origin + page meta)   │
│         ├─ image.png   (embedded CURRENT page image, PIL-encoded)              │
│         ├─ mask.bin    (binary (H,W) uint8 mask)                                │
│         └─ original.json (path ref + sha256 checksum — D-06)                   │
│     │                                                                           │
│     └──open──►  load manifest → build ImageFile[] in manifest order →          │
│                  per-page: checksum-verify original (D-06) → restore mask/     │
│                  boxes via Phase 2 D-11 seam → fresh HistoryManager (D-05)      │
│                  → chapter-climb dialog for standalone page .mas (D-09)         │
└────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── IMAGE OPS (PROJ-04) ────────────────────────────────┐
│                                                                                │
│  Menu/Tool (Rotate ▸ / Crop tool / Levels… / Resize…)                          │
│     │                                                                          │
│     ▼                                                                          │
│  canvas.get_image_numpy() + mask_to_numpy_binary(get_mask()) + boxes_snapshot()│
│     │                                                                          │
│     ▼                                                                          │
│  core/image_ops.py  (pure numpy+PIL)                                           │
│     • rotate: np.rot90 (k=-1/1/2)  • crop: slice  • resize: PIL LANCZOS/NEAREST│
│     • levels: LUT  • geometry: transform box bbox + TextBlock.lines quads      │
│     │                                                                          │
│     ▼                                                                          │
│  canvas.set_image_from_numpy() + set_mask(binary→QImage) + set_boxes()         │
│  HistoryManager.push_geometry_state(pre-op image+mask+boxes — ONE stamp)       │
│  canvas.rebaseline_original() (D-14)  +  status flash  +  geometry_altered=…   │
│  ── one Ctrl+Z (unified undo pops every store with the max stamp) ──           │
└────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── OCR JSON EXPORT (PROJ-03) ──────────────────────────┐
│                                                                                │
│  Text ▸ Export OCR JSON… (Ctrl+Shift+E) / Batch ▸ Batch Export OCR JSON         │
│     │                                                                          │
│     ▼                                                                          │
│  core/ocr_export.py  (pure projection of PageBox/TextBlock — no models)        │
│     • blocks[]: box/vertical/text/translation/bubble_no/origin                 │
│     • lines[]: per-line box + text (D-20: whole-text split by \n onto          │
│       TextBlock.lines polygons; unmatched lines → empty text)                  │
│     │                                                                          │
│     ▼                                                                          │
│  D-22 location:  pristine → source folder sidecar <stem>_ocr.json              │
│                  geometry-altered → <source>/cleaned/<stem>_ocr.json           │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (deltas on the existing tree)

```
manga_ai_studio/
├── core/
│   ├── project_io.py      # NEW — .mas container (lzma FORMAT_XZ entry table),
│   │                      #   manifest save/load, PageBox<->JSON mapping, sha256
│   ├── ocr_export.py      # NEW — _ocr.json builder (D-19/D-20 shape + D-22 dir)
│   ├── image_ops.py       # NEW — rotate/crop/levels/resize + box/line transforms
│   └── (existing: image_io.py, image_file.py, box_model.py, history_manager.py,
│                  mask_editor.py, batch_runner.py — extended, not replaced)
├── gui/
│   ├── canvas.py          # EXTEND — crop tool armed-rect state, dim-out overlay,
│   │                      #   Enter/Esc dispatch, rebaseline_original()
│   ├── main_window.py     # EXTEND — File/Edit/Text/Batch/Tools menu additions,
│   │                      #   Save/Open Project slots, dirty tracking, Ctrl+O remap,
│   │                      #   Recent Projects (QSettings "recentProjects")
│   ├── tools_panel.py     # EXTEND — 6th tool button (CROP) in the QActionGroup
│   ├── levels_dialog.py   # NEW — black/white/gamma + live preview (D-12)
│   ├── resize_dialog.py   # NEW — aspect-locked resize (D-13)
│   ├── crop_dialog.py     # NEW — numeric crop x/y/w/h (D-11 Edit menu)
│   └── (existing: load_translations_dialog.py is the dialog QSS pattern to copy)
└── core/mask_editor.py    # EXTEND — ToolMode.CROP added to the enum
```

### Pattern 1: Custom LZMA2 container (D-04) — header + entry table + blobs

**What:** Per-page `.mas` files are our own container: a small binary header, an entry table, and payload blobs, each compressed independently with `lzma.compress(..., format=lzma.FORMAT_XZ, preset=6)`. The chapter `manifest.json` stays plain JSON.

**When to use:** Always for `.mas` files (locked D-04). Entries: `meta.json` (page metadata + boxes), `image.png` (embedded current image), `mask.bin` (binary mask), `original.json` (path ref + sha256).

**Layout (recommended — planner-discretion detail):**
```
offset 0:  magic  b"MAS\x00"                     (4 bytes)
offset 4:  format_version  uint32 LE = 1         (4 bytes)
offset 8:  entry_count      uint32 LE            (4 bytes)
offset 12: entry table: per entry —
             name_len  uint16 LE, name utf-8,
             data_len  uint64 LE,
             data = lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)
```
**Example:**
```python
# Source: derived from docs.python.org/3/library/lzma.html (verified locally)
import lzma, struct, json

_MAGIC = b"MAS\x00"
_FORMAT_VERSION = 1

def _pack_entry(name: str, payload: bytes) -> bytes:
    data = lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)
    name_b = name.encode("utf-8")
    return struct.pack("<HQ", len(name_b), len(data)) + name_b + data

def save_page_file(path, entries: dict[str, bytes]) -> None:
    table = b"".join(_pack_entry(n, d) for n, d in entries.items())
    header = _MAGIC + struct.pack("<II", _FORMAT_VERSION, len(entries))
    path.write_bytes(header + table)

def load_page_file(path) -> dict[str, bytes]:
    raw = path.read_bytes()
    assert raw[:4] == _MAGIC, "not a .mas file"
    _ver, count = struct.unpack_from("<II", raw, 4)
    entries, off = {}, 12
    for _ in range(count):
        (nlen, dlen) = struct.unpack_from("<HQ", raw, off); off += 10
        name = raw[off:off + nlen].decode("utf-8"); off += nlen
        blob = raw[off:off + dlen]; off += dlen
        entries[name] = lzma.decompress(blob, format=lzma.FORMAT_XZ)
    return entries
```

### Pattern 2: Stamp-shared triple push — the geometry-op undo record (Claude's Discretion)

**What:** One Ctrl+Z must reverse image + mask + boxes together (UI-SPEC surface 28, "one press per op, never two"). The existing unified timeline (Phase 3 D-11) pops the single store with the max stamp; the geometry-op push stamps ALL THREE stores with the SAME monotonic stamp, and `undo()`/`redo()` are extended to pop every store whose tail stamp equals the max (returning a list of `(kind, value)` tuples).

**When to use:** For rotate/crop/levels/resize only. Ordinary mask/box/image edits keep today's single-store push (unchanged behavior).

**Why this shape:** preserves the "three logical stacks, one timeline" architecture (STATE.md: "three not seven"); the per-type pop methods (`pop_mask_undo`/`pop_image_undo`/`pop_boxes_undo`) stay untouched; the merge rule is a small, testable extension of the existing stamp comparison. The IMAGE entry is a **full-frame patch at (0,0)** — `pop_image_undo` already handles arbitrary `(x, y, patch)` and stashes the current full frame into redo (history_manager.py:222-227). Memory is bounded by the existing `limit=20` (T-01-16).

```python
# HistoryManager extension (recommended shape — planner discretion)
def push_geometry_state(self, image_patch: np.ndarray,
                        mask_qimage: QImage | None,
                        boxes: list | None) -> None:
    """Push one op across IMAGE + MASK + BOXES with a SINGLE stamp."""
    stamp = self._stamp()
    self._image_undo.append((stamp, (0, 0, image_patch.copy())))
    self._image_redo.clear()
    if mask_qimage is not None:
        self._mask_undo.append((stamp, mask_qimage.copy()))
        self._mask_redo.clear()
    if boxes is not None:
        self._boxes_undo.append((stamp, self._materialize_snapshot(boxes)))
        self._boxes_redo.clear()

def undo(self, current_mask, current_img, current_boxes):
    """Unified pop: pop EVERY store whose tail stamp == max tail stamp."""
    candidates = [
        (k, s[-1][0]) for k, s in (("mask", self._mask_undo),
                                   ("image", self._image_undo),
                                   ("boxes", self._boxes_undo)) if s
    ]
    if not candidates:
        return None
    max_stamp = max(c for _, c in candidates)
    out = []
    if self._mask_undo and self._mask_undo[-1][0] == max_stamp:
        out.append(("mask", self.pop_mask_undo(current_mask)))
    if self._image_undo and self._image_undo[-1][0] == max_stamp:
        out.append(("image", self.pop_image_undo(current_img)))
    if self._boxes_undo and self._boxes_undo[-1][0] == max_stamp:
        out.append(("boxes", self.pop_boxes_undo(current_boxes)))
    return out  # MainWindow.on_undo applies each (kind, value)
```
MainWindow's `on_undo` applies the list: `apply_undo_image(0, 0, patch)` (already bounds-checked against the current image — canvas.py:522-565), `apply_undo_mask`, `apply_undo_boxes`, then refreshes overlays and flashes `Undo: rotate|crop|levels|resize`.

### Pattern 3: `_ocr.json` export shape (D-19/D-20) — snake_case

**What:** Per-page JSON object; mokuro vocabulary verified from mokuro's official source (`MangaPageOcr.__call__` builds `{"version", "img_width", "img_height", "blocks"}` with per-block `box` = `list(blk.xyxy)`, `vertical`, `font_size`, `lines_coords`, `lines`), extended per D-19.

```json
{
  "version": "1",
  "img_width": 1600,
  "img_height": 2400,
  "blocks": [
    {
      "box": [120, 340, 480, 410],
      "vertical": false,
      "text": "First line\nSecond line",
      "translation": "Two lines of dialogue",
      "bubble_no": 3,
      "origin": "detected",
      "lines": [
        {"box": [122, 342, 478, 372], "text": "First line"},
        {"box": [122, 378, 478, 408], "text": "Second line"}
      ]
    }
  ]
}
```
- Per-line `box` = min/max of the line's 4-point polygon (each `TextBlock.lines` entry is a quad `[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]` [VERIFIED: textblock.py:50-51 + lines_array reshape(-1,8) at textblock.py:131-141]).
- D-20 split: `whole_text.split("\n")`; segment N maps to polygon N; extra polygons export `""`.
- `origin` values: the D-03 constants `"detected"` / `"user"` [VERIFIED: box_model.py:49-50 — quote: `DETECTED = "detected"`, `USER = "user"`].
- Field spelling `version`/`img_width`/`img_height`/`blocks`/`box`/`vertical`/`text`/`translation`/`bubble_no`/`origin`/`lines` is my snake_case recommendation (planner discretion per D-19; mokuro itself is snake_case — `img_width`, `img_height`, `lines_coords`).

### Pattern 4: Levels LUT via numpy (D-12) — with the RGB point() pitfall

**What:** Levels = black point, white point, gamma applied as a 256-entry lookup table on the `(H, W, 3)` uint8 array. Verified byte-identical to PIL's `point()` when the 768-entry form is used, and simpler.

```python
# Source: verified empirically against PIL 12.0.0 in the project env (2026-08-08)
def levels_lut(black: int, white: int, gamma: float) -> np.ndarray:
    lut = np.arange(256, dtype=np.float64)
    lut = (lut - black) / max(white - black, 1)
    lut = np.clip(lut, 0.0, 1.0) ** (1.0 / gamma)
    return (lut * 255.0).round().astype(np.uint8)  # 256-entry uint8 LUT

def apply_levels(rgb: np.ndarray, black: int, white: int, gamma: float) -> np.ndarray:
    return levels_lut(black, white, gamma)[rgb]  # fancy-index per channel
```
**White > black guard (UI-SPEC §25):** clamp internally — `white` slider minimum = `black + 1`, `black` slider maximum = `white - 1` (or clamp at apply). Never render an inverted map.

### Anti-Patterns to Avoid
- **Serializing `TextBlock.to_dict()`:** `to_dict()` deep-copies `vars(self)` including numpy arrays (`distance`, `vec`) and internal state — NOT JSON-serializable and version-fragile. Hand-pick the fields: `xyxy`, `lines`, `vertical`, `language`, `font_size`, `text`, `translation` [VERIFIED: textblock.py:165-167 `to_dict` at lines 165-167].
- **Mutating line polygons in place before the undo push:** the BOXES snapshot materializes shallow payload copies (Pitfall 8 — `PageBox.copy()` uses `copy.copy(payload)` [VERIFIED: box_model.py:166-178]); a geometry transform that mutates `payload.lines` in place aliases the pushed snapshot, so undo would restore the POST-op lines. Build fresh `TextBlock` (or deep-copy the lines list) for every transformed box.
- **Mutating the vendored `Box`:** it is `@frozen` (structures.py:39-44); every transform builds a NEW `Box(int, int, int, int)`.
- **Putting Qt in the new core modules:** `project_io.py` / `ocr_export.py` / `image_ops.py` import only stdlib + numpy + PIL (mirror `core/image_io.py`), so batch export stays worker-safe and tests run headless.
- **Leaving `Ctrl+O` bound to Open Image…:** with both actions bound, Qt fires both (UI-SPEC §Keyboard Shortcuts); the executor MUST remove `action_open_image.setShortcut(QKeySequence("Ctrl+O"))` (main_window.py:261) when Open Project… takes `Ctrl+O`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LZMA2 compression of container blobs | A custom LZMA compressor, or bindings to liblzma | stdlib `lzma` (`FORMAT_XZ` = LZMA2 filter, `CHECK_CRC64` default, preset 6) | stdlib, zero deps, integrity checks built in, streaming API; verified round-trip on the project env [CITED: docs.python.org/3/library/lzma.html] |
| Original-file integrity check (D-06) | A hand-rolled hash/CRC | `hashlib.sha256` with chunked file reads | stdlib, unambiguous, the user's stated default (CONTEXT discretion: "sha256 is the obvious default") |
| Image encode for embedded page images | A new PNG writer | `core/image_io.save_image_optimized` / PIL in-memory (`BytesIO`) | Existing Phase 2 writer preserves mode+DPI; in-memory variant avoids temp files [VERIFIED: image_io.py:46-106] |
| Levels LUT construction | Per-pixel loops in Python | numpy fancy-indexing `lut[rgb]` | Vectorized, one expression, byte-identical to PIL (verified); per-pixel Python loops on 10000×10000 pages are unusably slow |
| Rotate/scale math on boxes and line polygons | Hand-written per-case geometry scattered in GUI | Pure functions in `core/image_ops.py` operating on `Box.as_tuple` + line quads | One testable coordinate frame; the GUI applies results via the existing `set_boxes`/`current_box` boundary (Pitfall 6 int discipline) |
| JSON export writing | Raw string formatting of the JSON body | `json.dumps(..., indent=…)` on a dict built by a pure builder | The shape IS the contract (D-19); dict → dumps keeps field spelling in one place |
| Batch progress/abort for Batch Export OCR JSON | A new thread mechanism | Existing `Worker(QRunnable)` + `SharableFlag` + `_op_running` gate (Phase 2 pattern) | Already wired, tested, and UI-SPEC-contracted (progress surface + Cancel Batch) |

**Key insight:** Phase 5's "hard" parts are all solved problems — LZMA2 (stdlib), PNG encode (existing writer), levels (one numpy expression), JSON (stdlib), sha256 (stdlib). The genuinely novel work is the **geometry transform of `PageBox` bbox + `TextBlock.lines` quads** (D-15/D-17) and the **undo record shape** — those deserve the design attention, not re-implementing compression or image codecs.

## Common Pitfalls

### Pitfall 1: PIL `Image.point()` on an RGB image requires a 768-entry LUT
**What goes wrong:** `ValueError: wrong number of lut entries` — or, with a 256-entry LUT, a crash at apply time (verified empirically on PIL 12.0.0).
**Why it happens:** RGB images carry 3 channels; `point()` needs 3×256 entries.
**How to avoid:** Use the numpy path `lut[rgb]` with a 256-entry uint8 LUT (verified byte-identical to the 768-entry PIL form). If PIL `point()` is used anyway, pass `lut * 3`.
**Warning signs:** A unit test applying levels to an RGB array raises ValueError; any levels code path calling `Image.point`.

### Pitfall 2: `.copy()` discipline at every load boundary (Pitfall 2 inheritance)
**What goes wrong:** QImage/numpy aliasing — a restored mask or image that mutates when the source buffer GCs, or an undo snapshot that silently tracks the live canvas (the MangaCleaner_GPU `main_window.py:245` bug class).
**Why it happens:** `set_image_from_numpy` builds a QImage over the numpy buffer (canvas.py:658-663); `numpy_binary_to_mask_qimage` does the same (mask_editor.py:206-207). Without `.copy()` the display shares memory with the loader.
**How to avoid:** On `.mas` load, `.copy()` every embedded QImage/numpy before it enters `ImageFile.mask` / `set_image_from_numpy` / `set_mask` — the belt-and-suspenders discipline of Phase 2 D-11 / T-02-04 (outgoing `canvas.get_mask().copy()` at main_window.py:929). Assert detachment in tests (`test_mask_persistence_uses_copy` style).
**Warning signs:** Save→open→paint regressions; undo restoring post-edit state (Pitfall 8).

### Pitfall 3: In-place mutation of `payload.lines` before the undo push (Pitfall 8 on line lists)
**What goes wrong:** The geometry-op undo snapshot restores the POST-op line polygons — one Ctrl+Z leaves boxes misaligned with the image.
**Why it happens:** `PageBox.copy()` shallow-copies the payload (`copy.copy`); the BOXES snapshot therefore shares the `lines` list with the live box. Transforming lines in place before pushing aliases the snapshot.
**How to avoid:** The transform produces NEW `PageBox` objects with fresh payload copies (deep-copy `lines` at minimum). Push the BEFORE-state snapshot (captured pre-op) as today.
**Warning signs:** After undo, box outlines no longer match the text they contain; line-polygon regression tests fail on round-trip.

### Pitfall 4: Qt/PIL/QTransform 90°-rotation direction confusion
**What goes wrong:** A "90° CW" rotate that actually rotates CCW (or vice versa), or an interpolated (non-pixel-exact) result.
**Why it happens:** PIL `rotate(90)` is CCW, `rotate(-90)` is CW; `QTransform().rotate(90)` has its own sign convention with y-down coordinates; `np.rot90` uses k=-1 for CW — three libraries, three conventions.
**How to avoid:** Pick ONE convention in `core/image_ops.py`: `np.rot90(m, k=-1)` = 90° CW, `k=1` = CCW, `k=2` = 180° for BOTH image and mask (verified shapes: (H,W)→(W,H)); define the box mapping with the same function's math: CW: `(x,y)→(H-1-y, x)`; CCW: `(x,y)→(y, W-1-x)`; 180: `(x,y)→(W-1-x, H-1-y)`.
**Warning signs:** A test rotating a known asymmetric image lands on the wrong orientation; dimensions swap correctly but pixels don't match.

### Pitfall 5: `_original_image_numpy` captures once, so D-14 re-baseline breaks after the SECOND op
**What goes wrong:** After the first image op the cache holds the pre-op image (fine); after the second op it still holds the FIRST op's pre-image — Show Original shows a stale frame instead of the current post-op state.
**Why it happens:** `set_image_from_numpy` captures `_original_image_numpy` only when it is `None` (canvas.py:640-641).
**How to avoid:** Add `canvas.rebaseline_original()` that sets `self._original_image_numpy = self.get_image_numpy()` and `_showing_original = False`; call it after EVERY image op (D-14). For the Levels dialog live preview, use a capture-suppressed display path (or capture-then-restore the pre-dialog baseline around preview mutations) so opening the dialog doesn't poison the baseline.
**Warning signs:** Show Original after the 2nd op shows the 1st op's pre-image; the levels dialog preview changes what Show Original later displays.

### Pitfall 6: lzma preset 9 memory blowup / decompression bombs
**What goes wrong:** preset 9 can need ~800 MiB for a single compressor (docs); a malicious/corrupt `.mas` can decompress to gigabytes.
**Why it happens:** LZMA2's high presets trade memory for ratio; `lzma.decompress` has no size cap by default.
**How to avoid:** Use preset 6 (the default) for compression; on load use `lzma.decompress(data, format=lzma.FORMAT_XZ, memlimit=…)` or bound the decompressed size against the entry table (T-01-16 DoS-mitigation discipline) and validate dims against `MAX_IMAGE_DIMENSION = 10000` (canvas.py:79) before building QImages.
**Warning signs:** A save of a large chapter spikes memory; opening a crafted `.mas` hangs or OOMs.

### Pitfall 7: The D-11 seam's `_last_page_index` rule — save/export must read the OUTGOING index
**What goes wrong:** Saving the current page's canvas state through `_current_page_index()` mid-navigation reads the wrong page (the Phase 2 lesson, PATTERNS file 4a).
**Why it happens:** `select_path` mutates `current_path` before `on_page_selected` runs.
**How to avoid:** Save Project… and Batch Export OCR JSON must flush the CURRENT canvas state via `_flush_current_canvas_mask_to_data_model()` + `boxes_snapshot()` (the Bug-D fix pattern at main_window.py:3052) and read `_last_page_index` — never `_current_page_index()` — when correlating.
**Warning signs:** After Save, the wrong page's mask lands in the `.mas`; batch export writes page N's boxes into page M's JSON.

### Pitfall 8: Ctrl+O ambiguity (UI-SPEC §Keyboard Shortcut Reference)
**What goes wrong:** Pressing Ctrl+O fires BOTH Open Image… and Open Project… (Qt ambiguity).
**Why it happens:** `action_open_image` still carries `setShortcut(QKeySequence("Ctrl+O"))` (main_window.py:261).
**How to avoid:** Remove that one line when wiring Open Project… (Ctrl+O). Open Image… stays in the File menu; drag-drop and Open Folder… (Ctrl+Shift+O) remain the fast image-import paths.
**Warning signs:** Both file dialogs open on one Ctrl+O press.

### Pitfall 9: The levels live preview must not push undo entries while the dialog is open
**What goes wrong:** Each slider movement pushes an IMAGE entry → a single dialog session floods the stack, and Cancel can't restore exactly.
**Why it happens:** The preview mutates the canvas through the normal display path, and naive wiring connects it to history pushes.
**How to avoid:** Preview mutations are silent (no push); keep the pre-dialog numpy detached (`.copy()`) as the restore/apply base; Cancel re-displays it silently; Apply pushes ONE entry (the pre-dialog full-frame patch) + rebaselines.
**Warning signs:** After Cancel, Ctrl+Z steps through slider positions; the IMAGE stack depth grows while the dialog is open.

### Pitfall 10: Crop dropping boxes — the D-16 count and the 8×8 minimum
**What goes wrong:** Boxes vanish without feedback; sub-8×8 drags apply a degenerate crop.
**Why it happens:** The crop policy (drop fully-outside, clip partial) is silent by design (D-14); a tiny drag can produce a zero-area slice.
**How to avoid:** Report the dropped count in the status flash ("Cropped. {n} box(es) were outside the crop and removed — press Ctrl+Z to restore." — UI-SPEC §Copywriting); enforce the 8×8 scene-px minimum on release (no overlay, no preview, no-op below it — UI-SPEC §Spacing exceptions).
**Warning signs:** User reports lost boxes after crop; crop applies on an accidental 3×3 drag.

## Code Examples

Verified patterns from official sources and the in-repo codebase:

### Common Operation 1: `.mas` per-page file round-trip (container + state projection)
```python
# Source: lzma API [CITED: docs.python.org/3/library/lzma.html]; PageBox/ImageFile
# fields [VERIFIED: box_model.py:85-94, image_file.py:72-76] — read this session
import json
from pathlib import Path

def pagebox_to_json(pb) -> dict:
    """Project PageBox -> JSON (D-15 seam: mask/std_dev stay None, never written)."""
    payload = pb.payload
    return {
        "box": list(pb.box.as_tuple),              # [x1, y1, x2, y2] — Box frozen
        "origin": pb.origin,                        # "detected" | "user"
        "edited": pb.edited,
        "bubble_no": pb.bubble_no,
        "manual_override": pb.manual_override,
        "payload": None if payload is None else {
            "xyxy": list(payload.xyxy),
            "lines": payload.lines,                 # list of 4-point quads
            "vertical": payload.vertical,
            "language": payload.language,
            "font_size": payload.font_size,
            "text": payload.text,                   # str (Phase 4) or list
            "translation": payload.translation,
        },
    }
```
Box fields quote [VERIFIED: structures.py:39-44]: `@frozen class Box: x1: int / y1: int / x2: int / y2: int`. PageBox field list quote [VERIFIED: box_model.py:85-94]: `box: Box`, `origin: str`, `payload: Optional[object] = None`, `mask: Optional[object] = None  # D-15 seam`, `std_dev: Optional[float] = None`, `edited: bool = False`, `bubble_no: Optional[int] = None`, `manual_override: bool = False`. `TextBlock` field set quote [VERIFIED: textblock.py:50-68]: `self.xyxy = [int(num) for num in xyxy]`, `self.lines = [] if lines is None else lines`, `self.vertical = vertical`, `self.text = text if text is not None else []`, `self.translation = translation`.

### Common Operation 2: Geometry transform of a PageBox (D-15/D-17) — rotation
```python
# Source: derived from np.rot90 semantics, verified in-repo Box/PageBox shapes
from panelcleaner.structures import Box

def _rotate_point(x: int, y: int, w: int, h: int, k: int):
    if k == -1:  # 90 CW
        return h - 1 - y, x
    if k == 1:   # 90 CCW
        return y, w - 1 - x
    if k == 2:   # 180
        return w - 1 - x, h - 1 - y
    return x, y

def transform_box(box: Box, w: int, h: int, k: int) -> Box:
    x1, y1, x2, y2 = box.as_tuple
    (nx1, ny1), (nx2, ny2) = _rotate_point(x1, y1, w, h, k), _rotate_point(x2, y2, w, h, k)
    # Rotating an axis-aligned rect maps corners onto corners; normalize order.
    return Box(min(nx1, nx2), min(ny1, ny2), max(nx1, nx2), max(ny1, ny2))

def transform_payload_lines(lines, w: int, h: int, k: int):
    """Transform each 4-point line quad — D-17: lines transform with the box."""
    out = []
    for quad in lines:
        out.append([list(_rotate_point(px, py, w, h, k)) for px, py in quad])
    return out
```
**Never mutate the frozen `Box`** — build a new one. **Never mutate `payload.lines` in place before the undo push** — build a fresh payload copy (Pitfall 3).

### Common Operation 3: Levels / Resize / Crop apply paths (pure numpy+PIL)
```python
# Source: verified empirically on PIL 12.0.0 + numpy 2.3.5 (2026-08-08)
import numpy as np
from PIL import Image

def rotate_page(image: np.ndarray, mask_bin: np.ndarray, k: int):
    """image (H,W,3) uint8, mask_bin (H,W) uint8; k=-1 CW, 1 CCW, 2 180 (D-18)."""
    return np.rot90(image, k=k).copy(), np.rot90(mask_bin, k=k).copy()

def crop_page(image: np.ndarray, mask_bin: np.ndarray, x, y, w, h):
    """Exact slice (D-18). Returns (image, mask, dropped, clipped) for D-16."""
    img_c = image[y:y + h, x:x + w].copy()
    msk_c = mask_bin[y:y + h, x:x + w].copy()
    return img_c, msk_c

def resize_page(image: np.ndarray, mask_bin: np.ndarray, new_w: int, new_h: int):
    """Image smooth (LANCZOS), mask nearest-neighbor (D-18 no soft alpha drift)."""
    img = np.asarray(Image.fromarray(image, "RGB").resize(
        (new_w, new_h), Image.Resampling.LANCZOS))
    msk = np.asarray(Image.fromarray(mask_bin, "L").resize(
        (new_w, new_h), Image.Resampling.NEAREST))
    return img.copy(), msk.copy()

def levels_page(image: np.ndarray, black: int, white: int, gamma: float):
    """Geometry-free (D-15): pixels only, mask/boxes untouched."""
    lut = np.arange(256, dtype=np.float64)
    lut = np.clip((lut - black) / max(white - black, 1), 0.0, 1.0) ** (1.0 / gamma)
    lut = (lut * 255.0).round().astype(np.uint8)
    return lut[image].copy()
```

### Common Operation 4: Save-side flush of the current canvas page (Bug-D pattern)
```python
# Source: in-repo verified — main_window.py:3052 `_flush_current_canvas_mask_to_data_model`
# (the Bug D fix) + on_page_selected steps 1/1b (main_window.py:916-946)
def _snapshot_current_page(self) -> None:
    """Flush live canvas state into ImageFile before .mas save (Pitfall 7)."""
    idx = self._last_page_index  # OUTGOING index — never _current_page_index()
    if idx is None or not (0 <= idx < len(self.image_files)):
        return
    if self.canvas.has_mask():
        self.image_files[idx].mask = self.canvas.get_mask().copy()  # .copy() MANDATORY
    self.image_files[idx].boxes = self.canvas.boxes_snapshot()      # detached by construction
```

### Common Operation 5: D-20 `\n`-split onto line polygons
```python
# Source: derived from D-20 contract; TextBlock.lines quad shape [VERIFIED: textblock.py:131-141]
def split_text_onto_lines(text: str, lines: list) -> list[str]:
    """Line N gets segment N of the whole text; unmatched lines export empty text."""
    segments = text.split("\n")
    return [segments[n] if n < len(segments) else "" for n in range(len(lines))]

def line_box(quad: list) -> list[int]:
    """Per-line [x1, y1, x2, y2] from a 4-point polygon (D-19 lines[].box)."""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return [min(xs), min(ys), max(xs), max(ys)]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| mokuro's `_ocr.json` (blocks only, per-line text inside `lines` as bare strings) | Our D-19 shape: mokuro vocabulary + `text`/`translation`/`bubble_no`/`origin` + per-line `box`+`text` | Phase 5 (user override, D-19) | Downstream typesetting tools can place each line inside its bubble; the shape is a published contract (one-way) |
| Zip containers for project files | stdlib LZMA2 (`FORMAT_XZ`) custom container | D-04 (user decision) | Zero new deps; per-blob integrity checks (CHECK_CRC64); smaller than zip for image payloads |
| Full-frame undo snapshots for image ops (new for Phase 5) | Region patches (Phase 1-2 inpaint) | Phase 5 | Geometry ops change the whole canvas — full-frame (0,0,H,W) patches are the only correct pre-state; bounded by limit=20 (T-01-16) |
| Show Original = pre-inpaint preview only | Re-baselined after every image op (D-14) | Phase 5 | The pre-op image is recoverable only via Ctrl+Z — the contracted trade |

**Deprecated/outdated:**
- **PROJECT.md's claim that crop/rotate/levels live in `pcleaner/image_ops.py`:** STALE — verified by CONTEXT canonical_refs: PanelCleaner's `image_ops.py` is mask-fitting/denoising machinery (border_std_deviation, pick_best_mask); there is no crop/rotate/levels anywhere in PanelCleaner. PROJ-04 is greenfield with PIL/numpy primitives, no GPL obligation beyond existing Phase 1 D-12 discipline.
- **`Ctrl+O` = Open Image…** (Phase 1): superseded by D-07 (Ctrl+O = Open Project…). The old binding must be removed (Pitfall 8).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_ocr.json` field spelling is snake_case with `version: "1"` (mokuro itself is snake_case: `img_width`, `img_height`, `lines_coords`) | Pattern 3 / Open Questions | D-19 locks the SHAPE (fields + semantics) but spelling is planner discretion; downstream typesetting tools may be built against the published spelling — pick once, document in the plan |
| A2 | Geometry-op undo record = stamp-shared triple push + pop-all-with-max-stamp | Pattern 2 | Claude's Discretion; the alternative (combined record on a new stack) changes the "three not seven" invariant — the stamp-shared shape preserves it |
| A3 | Per-page "current image" for NON-current pages at save time = `cleaned/<name>` if it exists, else the source file | Summary / Patterns | The canvas holds only the current page's live image; Phase 2's convention reloads cleaned output into the canvas (main_window.py:3351-3353 [VERIFIED]) — the save-side rule follows it; if wrong, saved pages embed the source instead of the cleaned result |
| A4 | Levels does NOT mark a page geometry-altered for D-22 (only crop/rotate/resize do) | Open Questions | UI-SPEC §25 explicitly notes this interpretation for the planner; if the user wanted levels to move exports into `cleaned/`, the location rule changes |
| A5 | Batch Export OCR JSON runs on the existing Worker + `_op_running` + batch-progress surface (mirrors Phase 2) | Open Questions | D-21 leaves threading to the planner; inline is acceptable but loses progress/abort consistency with the three existing batch actions |
| A6 | lzma preset 6 (default) for container blobs; `memlimit` on decompress | Pattern 1 / Pitfall 6 | Preset 9's 800 MiB compressor overhead would be a regression on large chapters; memlimit guards decompression bombs (T-01-16 analog) |
| A7 | The D-06 checksum is sha256 over the original file bytes, chunked | Standard Stack | CONTEXT names sha256 as the obvious default; the checksum is part of the saved-project format (D-06 one-way) |
| A8 | Resize interpolation = LANCZOS (image) / NEAREST (mask) | Pattern (Code Examples 3) | UI-SPEC §26 contracts "smooth" image interpolation (planner may pick bilinear/lanczos) and NEAREST mask (D-18); LANCZOS is the highest-quality default |
| A9 | The manifest carries `version`, chapter `name`, and `pages: [{name, file}]` (plain JSON) | Pattern 1 / Open Questions | Manifest schema is planner discretion (D-03 "session metadata"); a version field enables the "from a newer version" corrupt-file copy |

## Open Questions (RESOLVED)

> All six questions below were resolved during planning; each carries the plan reference that implements its recommendation.

1. **Ctrl+O remap confirmation (UI-SPEC Open Question 1, D-07 vs Phase 1)** — **(RESOLVED — plan 05-05 Task 1)**
   - What we know: `action_open_image` binds Ctrl+O (main_window.py:261); D-07 assigns Ctrl+O to Open Project…; UI-SPEC resolves "newest user decision wins; remove the old binding" and the shortcut audit shows no other collision.
   - What's unclear: whether the user prefers a different key for Open Project….
   - Recommendation: adopt the UI-SPEC resolution — remove `setShortcut(Ctrl+O)` from Open Image…, bind Open Project… to Ctrl+O. Executor MUST not leave two actions on Ctrl+O (Pitfall 8).
   - Resolution: plan 05-05 Task 1 removes the Open Image… binding (Pitfall 8) and assigns Ctrl+O to Open Project…; `test_ctrl_o_opens_project_not_image` + the `grep 'Ctrl+O' == 1` gate assert exactly one binding.

2. **Geometry-op undo record shape (CONTEXT Claude's Discretion)** — **(RESOLVED — plan 05-04)**
   - What we know: Phase 3 D-11 unified timeline pops the max-stamp store; one Ctrl+Z must reverse image+mask+boxes.
   - What's unclear: combined record vs paired push — the planner picks.
   - Recommendation: **stamp-shared triple push** (Pattern 2) — `push_geometry_state` stamps all three stores with one `_stamp()`; `undo()`/`redo()` pop every store whose tail stamp equals the max and return a list; `on_undo`/`on_redo` apply each. Least-surprising, preserves "three not seven", per-type pop methods untouched. Regression guard: `test_geometry_undo_reverses_all_three_in_one_press`.
   - Resolution: implemented as a dedicated TDD plan (05-04) — `push_geometry_state(image_patch, mask_qimage=None, boxes=None)` + pop-all-with-max-stamp `undo()`/`redo()` returning `list[(kind, value)]`; `test_geometry_undo_reverses_all_three` is the regression guard; the MainWindow list-apply is part of the same atomic contract change.

3. **`_ocr.json` spelling + version value (CONTEXT Claude's Discretion)** — **(RESOLVED — plan 05-03)**
   - What we know: shape locked by D-19; mokuro is snake_case.
   - What's unclear: exact spelling; version string.
   - Recommendation: snake_case as in Pattern 3, `"version": "1"`; document the exact JSON in the plan so downstream consumers can pin it.
   - Resolution: snake_case per Pattern 3; `"version": "1"` pinned as `OCR_JSON_VERSION` in `core/ocr_export.py` (plan 05-03 Task 1); the exact shape is documented in the plan and asserted by `test_json_shape`.

4. **Batch Export OCR JSON threading (D-21 discretion)** — **(RESOLVED — plans 05-03 Task 2 + 05-08 Task 2)**
   - What we know: model-free serialization is fast; UI-SPEC contracts the batch progress surface (status-left + 3px bar + Cancel) "contracted either way".
   - What's unclear: Worker vs inline.
   - Recommendation: Worker path — `core/ocr_export.py` gains `batch_export_ocr(pages, progress_callback=None, abort_flag=None) -> {"ok", "failed", "total"}` mirroring `batch_runner._run_batch_task`'s contract (per-page try/except, abort at loop top), dispatched via the existing `_dispatch` pattern with `_op_running` gating. Reuses tested machinery; consistent with the three Phase 2 batch actions.
   - Resolution: Worker path chosen — `batch_export_ocr` with the last-two-kwargs auto-injection contract lands in plan 05-03 Task 2; plan 05-08 Task 2 dispatches it via the Phase 2 `_dispatch_batch` template with `_op_running` gating and the batch progress surface.

5. **Project-folder collision handling (D-02 detail)** — **(RESOLVED — plan 05-01 Task 2)**
   - What we know: UI-SPEC §Copywriting contracts non-destructive overwrite — "the app writes into an existing `*.mas-project` folder, overwriting per-page `.mas`/`manifest.json` files it owns, never deleting other content"; failed writes use the save-failure copy.
   - What's unclear: exact folder-name validation (e.g. `chapter-01.mas-project` vs an existing unrelated folder of the same name).
   - Recommendation: derive the default name `<source-folder-name>.mas-project`; if the folder exists, write into it non-destructively (overwrite owned files only); never delete foreign content.
   - Resolution: plan 05-01 Task 2's `save_project` writes only owned manifest.json + *.mas files (atomic temp+os.replace per file); `test_non_destructive_overwrite` proves a foreign `notes.txt` survives re-save; `test_save_is_atomic` covers the interrupted-write backstop.

6. **Show Original gating mechanism for `.mas`-loaded pages (D-06)** — **(RESOLVED — plans 05-01 + 05-06)**
   - What we know: the action's enable state is driven by `has_inpaint_result()` (main_window.py:754) — a `.mas` page without a verified original must grey it out per UI-SPEC §29.
   - What's unclear: where the "original available" flag lives.
   - Recommendation: a per-page flag (e.g. `ImageFile.original_verified: bool = False`) set during `.mas` load when path-ref + sha256 match; `_refresh_action_states` consults it (page from project AND not verified → disabled + tooltip "Show Original (P) — original file not found."). Levels/geometry ops re-baseline via `canvas.rebaseline_original()` (D-14).
   - Resolution: `ImageFile.original_verified` lands in plan 05-01 Task 2 (set at load per the D-06 sha256 rule via `verify_original`); plan 05-06 Task 3 consumes it in `_refresh_action_states` (disabled + not-found tooltip) and `canvas.rebaseline_original()` runs after every op (D-14); `test_show_original_gating` covers both branches.

## Environment Availability

> Phase 5 has no NEW external dependencies — all required libraries are already installed in the project's working environment.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (pyenv) | Runtime | ✓ | 3.14.2 (pyenv-win default) | — (project already runs here; 461 tests green) |
| PySide6 | All GUI work (dialogs, canvas, menus) | ✓ | 6.10.1 | — |
| Pillow | Embedded image encode, resize, levels | ✓ | 12.0.0 | — |
| numpy | Image/mask arrays, rot90, LUT | ✓ | 2.3.5 | — (note: pyproject pins `numpy<2`; installed env has 2.3.5 and works) |
| opencv (cv2) | (inherited; vendored TextBlock math) | ✓ | 4.13.0 | — |
| lzma / json / hashlib | `.mas` container, manifest, checksums | ✓ | stdlib (FORMAT_XZ verified) | — |
| pytest / pytest-qt | Validation | ✓ | 9.1.1 | — |
| loguru / natsort / attrs / configupdater | (inherited) | ✓ | installed | — |

**Path note:** the default `python` on PATH resolves to an unrelated hermes venv (3.11.15, no project deps). Executors must run the project env explicitly:
```powershell
& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest
```

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` (line 25) — this section applies.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-qt (dev extras; `pyproject.toml:43-47`) |
| Config file | none — pytest defaults; `tests/conftest.py` guards PySide6 import |
| Quick run command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_project_io.py -x` |
| Full suite command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest` |

Existing infrastructure: `tests/conftest.py` (PySide6 importorskip), `tests/test_core/` (13 files incl. `test_image_io.py`, `test_batch_runner.py`, `test_box_model.py`, `test_history_boxes.py`), `tests/test_mask_editor/`, GUI tests (`test_gui_boxes.py`, `test_gui_canvas.py`, …). 461 tests green at Phase 4 close.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-01 | `.mas` per-page container round-trip (header/entries/blobs, corrupt-file rejection) | unit | `pytest tests/test_core/test_project_io.py::test_page_file_round_trip -x` | ❌ Wave 0 |
| PROJ-01 | Manifest save/load rebuilds session order + per-page state (mask/boxes/text/translation) | unit | `pytest tests/test_core/test_project_io.py::test_manifest_round_trip -x` | ❌ Wave 0 |
| PROJ-01 | D-06 checksum rule: verified original used; missing/mismatched → embedded image + flag | unit | `pytest tests/test_core/test_project_io.py::test_original_checksum_rule -x` | ❌ Wave 0 |
| PROJ-01 | D-09 chapter-climb detection (sibling manifest found / not found) | unit | `pytest tests/test_core/test_project_io.py::test_sibling_manifest_detection -x` | ❌ Wave 0 |
| PROJ-01 | D-15 seam preserved: `PageBox.mask`/`std_dev` stay `None` through save/load | unit | `pytest tests/test_core/test_project_io.py::test_d15_seam_preserved -x` | ❌ Wave 0 |
| PROJ-01 | GUI: Save Project Ctrl+S / Open Project Ctrl+O / dirty `*` title / Unsaved Changes prompt | integration (pytest-qt) | `pytest tests/test_gui_project.py::test_dirty_title_and_prompt -x` | ❌ Wave 0 |
| PROJ-03 | `_ocr.json` shape: version/img_width/img_height/blocks + per-block fields + lines[] | unit | `pytest tests/test_core/test_ocr_export.py::test_json_shape -x` | ❌ Wave 0 |
| PROJ-03 | D-20 `\n`-split: line N gets segment N; unmatched lines empty; zero-box page exports empty | unit | `pytest tests/test_core/test_ocr_export.py::test_newline_split -x` | ❌ Wave 0 |
| PROJ-03 | D-22 location: pristine → source folder; geometry-altered → `cleaned/` (created if missing) | unit | `pytest tests/test_core/test_ocr_export.py::test_d22_location_rule -x` | ❌ Wave 0 |
| PROJ-04 | Rotate 90 CW/CCW/180 pixel-exact (image+mask) + box/line transforms (D-17/D-18) | unit | `pytest tests/test_core/test_image_ops.py::test_rotate_transforms_all -x` | ❌ Wave 0 |
| PROJ-04 | Crop: exact slice, drop fully-outside boxes with count, clip partial (bbox AND lines) (D-16) | unit | `pytest tests/test_core/test_image_ops.py::test_crop_drop_and_clip -x` | ❌ Wave 0 |
| PROJ-04 | Resize: image LANCZOS, mask NEAREST, boxes scaled int; levels: LUT math + white>black guard | unit | `pytest tests/test_core/test_image_ops.py::test_resize_and_levels -x` | ❌ Wave 0 |
| PROJ-04 | Geometry-op undo: ONE Ctrl+Z reverses image+mask+boxes together (stamp-shared) | unit | `pytest tests/test_history.py::test_geometry_undo_reverses_all_three -x` | ❌ Wave 0 |
| PROJ-04 | Crop tool: armed rect, Enter applies, Esc cancels, dim-out overlay z=880, 8×8 min | integration (pytest-qt) | `pytest tests/test_gui_crop_tool.py::test_enter_applies_esc_cancels -x` | ❌ Wave 0 |
| PROJ-04 | Dialogs: Levels live preview + Cancel restores exactly + Apply pushes one entry | integration (pytest-qt) | `pytest tests/test_gui_image_dialogs.py::test_levels_cancel_restores -x` | ❌ Wave 0 |
| PROJ-01/04 | Show Original gated on `.mas` pages without verified original; re-baseline after ops (D-06/D-14) | integration (pytest-qt) | `pytest tests/test_gui_project.py::test_show_original_gating -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the affected module's test file(s): `pytest tests/test_core/test_project_io.py tests/test_core/test_ocr_export.py tests/test_core/test_image_ops.py -q`
- **Per wave merge:** `pytest -q` (full suite, ~1-2 min)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_core/test_project_io.py` — covers PROJ-01 (round-trips, checksum rule, climb detection, D-15 seam)
- [ ] `tests/test_core/test_ocr_export.py` — covers PROJ-03 (shape, split, location rule, zero-box)
- [ ] `tests/test_core/test_image_ops.py` — covers PROJ-04 (rotate/crop/resize/levels + geometry)
- [ ] `tests/test_history.py` — extend for stamp-shared geometry-op undo/redo (PROJ-04)
- [ ] `tests/test_gui_project.py` — menu actions, dirty tracking, prompts, Show Original gating (PROJ-01)
- [ ] `tests/test_gui_crop_tool.py` — crop tool interaction (PROJ-04)
- [ ] `tests/test_gui_image_dialogs.py` — Levels/Resize/Crop dialogs (PROJ-04)
- [ ] `tests/conftest.py` — no change needed (PySide6 guard + tmp_path already present)

## Security Domain

> `workflow.security_enforcement` is `true` (config.json:47, ASVS level 1) — this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (single-user desktop app, no accounts) |
| V3 Session Management | no | — (no sessions) |
| V4 Access Control | no | — (no multi-user model) |
| V5 Input Validation | **yes** | `.mas`/`manifest.json`/`_ocr.json` are untrusted-file boundaries: strict schema/type validation on load (int coercion + bounds clamping — mirror the Phase 3 V5 `textblock_to_box` `int()` discipline at box_model.py:181-204); geometry ops clamp spinbox ranges (UI-SPEC contracts); line/polygon counts bounded (T-01-16 DoS discipline) |
| V6 Cryptography | no | sha256 is used for INTEGRITY (D-06 checksum), not confidentiality; stdlib `hashlib` is the standard control |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Decompression bomb in a crafted `.mas` (LZMA2 can expand ~1000:1) | DoS | `lzma.decompress(..., memlimit=…)` + entry-table size sanity + validate image dims against `MAX_IMAGE_DIMENSION = 10000` (canvas.py:79) before constructing QImages (T-01-16 analog) |
| JSON type confusion from a corrupt/newer `.mas` (wrong types in boxes/text) | Tampering | Schema-check on load (fields typed, ints coerced, boxes clamped to page bounds — Phase 3 V5 pattern); failure → "Couldn't open '{filename}'." critical dialog, NO partial session mutation (UI-SPEC corrupt-project copy) |
| Path traversal via the manifest `original` ref (D-06 path read from the file) | Tampering / Information disclosure | `Path.resolve()` + image-suffix allowlist (`validate_image_path`, canvas.py:114-126) before using the referenced original; checksum mismatch falls back to the embedded image |
| Oversized `.mas` chapter on open | DoS | Bounded page count + per-page size checks; error path keeps the previous session intact |
| Log injection via crafted text/JSON content | Tampering | `loguru` logs only filenames/stems + error strings, never raw OCR text content (matches Phase 2 batch-report discipline) |
| Corrupt image blob (embedded PNG) | DoS | PIL open errors caught → per-page failure recorded (batch) / corrupt-project dialog (open) |

## Sources

### Primary (HIGH confidence)
- **docs.python.org/3/library/lzma.html** — `FORMAT_XZ` (LZMA2 filter), `CHECK_CRC64` default, presets 0–9 (default 6, preset 9 ~800 MiB), `LZMACompressor`/`LZMADecompressor`/`lzma.open`, `memlimit`, custom filter chains — fetched this session [CITED]
- **github.com/kha-white/mokuro `mokuro/manga_page_ocr.py`** — the official `_ocr.json` schema: `version`, `img_width`, `img_height`, `blocks[]` with `box`=`list(blk.xyxy)`, `vertical`, `font_size`, `lines_coords`, `lines` — fetched this session [CITED]
- **Local empirical probes (2026-08-08, pyenv 3.14.2)** — lzma compress/decompress/streaming/open round-trips; PIL 12.0.0 rotate/crop/resize semantics; **RGB `point()` needs 768 LUT entries**; numpy-LUT levels byte-identical to PIL [VERIFIED: local probe]
- **In-repo source reads (this session)** — `box_model.py`, `image_file.py`, `image_io.py`, `history_manager.py`, `mask_editor.py`, `canvas.py`, `box_item.py`, `tools_panel.py`, `worker_thread.py`, `batch_runner.py`, `main_window.py`, `panelcleaner/structures.py`, `panelcleaner/comic_text_detector/utils/textblock.py`, `pyproject.toml`, `tests/conftest.py`, `.claude/CLAUDE.md` [VERIFIED: paths+lines quoted inline]

### Secondary (MEDIUM confidence)
- `.planning/phases/05-project-persistence-image-ops-export/05-CONTEXT.md` — locked decisions D-01…D-22 + Claude's Discretion + canonical refs (the authoritative phase contract) [VERIFIED: read this session]
- `.planning/phases/05-project-persistence-image-ops-export/05-UI-SPEC.md` — UI contract (menus, shortcuts, dialogs, z-order, copy) — approved 2026-08-08 [VERIFIED: read this session]
- `.planning/STATE.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/PROJECT.md` — phase/decision history [VERIFIED: read this session]

### Tertiary (LOW confidence)
- None — every claim above is either cited from official docs/source, verified empirically in the project env, or verified by in-repo source reads this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages; all versions verified by local probes in the working env; lzma API cited from official docs and round-trip-tested
- Architecture: HIGH — container layout, export shape, and transform math are derived from locked decisions (D-01…D-22) + verified in-repo model shapes; the undo-record and JSON-spelling details are flagged as planner discretion (A1/A2)
- Pitfalls: HIGH — every pitfall is grounded in this-session verification (PIL 768-LUT probe, in-repo `_original_image_numpy` capture logic, `.copy()` discipline, D-11 seam rules, Ctrl+O binding) rather than folklore

**Research date:** 2026-08-08
**Valid until:** 2026-09-07 (30 days — stable stdlib/PIL/numpy API surface; the only fast-moving risk is Pillow point() behavior, already locked by the empirical probe)

---

*Phase: 5-Project Persistence, Image Ops & Export*
*Researched: 2026-08-08*




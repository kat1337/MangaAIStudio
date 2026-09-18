# Phase 4: OCR Recognition & Text Editing - Research

**Researched:** 2026-08-05
**Domain:** manga-ocr integration, Qt6 canvas text editing/overlay, reading-order numbering, translation parser
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Both OCR paths — Alt+drag-to-draw runs manga-ocr **automatically on draw-release** (one gesture → box with text), AND a separate "Run OCR" action fills the selected box.
- **D-02:** OCR runs on BOTH box origins — user-drawn (amber) AND detected (green). Detected boxes start with empty text; "Run OCR" / "OCR All" fills them.
- **D-03:** "OCR All Boxes on Page" action (`Ctrl+R`). Fills every text-empty box on the current page. One model load, sequential per-box recognition, status-bar progress. Skips boxes with text unless user confirms overwrite (D-04).
- **D-04:** Re-OCR respects a user-`edited` flag. Silent overwrite on raw OCR text (`edited == false`); **confirm dialog** if the user has hand-edited the text (`edited == true`). An `edited` flag is required on the recognized-text field (set true by inline editor / Inspector on commit, false after OCR). "OCR All" applies the same rule per box.
- **D-05:** Inline overlay on the box. Double-click a box → transient `QTextEdit`/`QLineEdit` overlay ON the box rect; Enter or click-away commits, Esc cancels.
- **D-06:** Inline editor defaults horizontal; per-box toggle to vertical. `payload.vertical` flag is ALWAYS preserved on the model regardless of editor mode (orientation is export metadata; the toggle is edit-UX).
- **D-07:** Double-click = edit, single-click = select/move/resize. Edit mode disables move/resize while active. NO new tool added to the mask `QActionGroup`.
- **D-08:** Inline editor edits the "current focus" field; a sidebar carries the secondary field. Focus = **translation if a translation exists, else recognized text.** A new Inspector panel shows the OTHER field + metadata, always editable.
- **D-09:** Text IS rendered persistently on the canvas (boxes become display objects). Rendered via `QGraphicsTextItem` layered with the box.
- **D-10:** Canvas renders the "current focus" text — translation when present, else recognized. A box never shows both.
- **D-11:** Translucent overlay treatment. Text drawn ON TOP of artwork inside the box rect, white-ish text + dark outline, art visible underneath. NOT an opaque caption.
- **D-12:** Separate "Toggle Text Overlay" visibility control, independent of mask (`M`) and box (`Shift+M`). Three independent visibility layers.
- **D-13:** One translation per box; `set_translation()` seam. Stored on `TextBlock.translation`; future MT adapter calls the same setter. Per-line translation is NOT v1.
- **D-14:** manga-ocr via the `OCRModel` adapter, with config hooks designed-in (not built-out). v1 implements manga-ocr ONLY (hardcoded `kha-white/manga-ocr-base`), through the existing `OCRModel` ABC as a new `TorchOCRModel` (filling the Phase 1 `backend_factory("ocr")` stub). Hooks for model/language/backend so a future `ONNXOCRModel` plugs in without core changes. **No tesseract, no full PanelCleaner OCR config UI surface in v1.** Vendor PanelCleaner's `MangaOcr` wrapper (`../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py`).
- **D-15:** Phase 4 ships the translation parser + bubble numbering (full TEXT-05 subsystem). (a) Auto bubble-numbering in reading order — RTL/TB (manga) + LTR/TB (manhwa) — with per-box manual override. (b) Visible bubble numbers on the canvas. (c) A translation parser ingesting a typesetting-tool-format block, matching lines to bubbles by number. (d) SFX matching SKIPPED for v1. Parser input contract:
  ```
  [Bubble Number]: [translated line 1]
  [SFX -SFX Number]: *sfx line 2*
  [Bubble Number]: [translated line 3]
  ```
  Rules: numeric bubble numbers only (no `S1-X`/`FT`/`N` labels), no Japanese, one line per text box.
- **D-16:** Page-level auto-number + per-box manual override. "Auto-Number RTL (Manga)" + "Auto-Number LTR (Manhwa)" assign 1..N. Per-box manual override sticks when page-level re-auto runs (conflict policy: planner decides).
- **D-17:** Parser has two input front-ends — paste-dialog AND file-import. Shared parser core. Paste = single-page; file = multi-page with Page markers.
- **D-18:** Page-global bubble numbers; panels ignored. The parser keys ONLY off `[Bubble Number]`, page-global 1..N.

### Claude's Discretion
- Exact widget choice for the inline editor (D-05) — `QTextEdit` vs `QLineEdit` vs custom delegate; vertical-mode implementation (D-06) is non-trivial.
- The sidebar/inspector panel structure (D-08) — Qt dock vs fixed panel vs popover; field layout.
- The `edited` flag's home (D-04) — on the recognized-text field, derived from diff, or on the box model.
- Conflict policy for page-level re-auto vs manual override (D-16).
- Reading-order auto-number algorithm (D-15/D-16) — the RTL/TB and LTR/TB sort key + thresholds.
- Text-overlay font/size/scaling (D-11) — viewport-px vs scene-units vs proportional; outline width.
- Toggle Text Overlay keybinding (D-12) — distinct from `M` and `Shift+M`.
- Parser error handling (D-15/D-17) — what happens on unmatched `[N]:`.
- Where the "Run OCR" / "OCR All" / "Load Translations…" actions live in the UI.
- OCR worker threading — route through existing `Worker(QRunnable)` + `_op_running` gate; one model load per session (singleton).

### Deferred Ideas (OUT OF SCOPE)
- Machine translation integration (TRAN-01) — v2. Seam is `set_translation()` + adapter shape.
- Typesetting / rendering translated text into the page (TRAN-02) — v2; PROJECT.md Out of Scope. Includes the full styling toolbar (font selection per-box/selection/page, font style, font size +/-, color, H/V alignment, effects) — deferred to a future typesetting phase. Phase 4's overlay is review/correction only.
- Tesseract / non-Japanese OCR engines — v1 is manga-ocr only.
- ONNX OCR backend on a separate pyenv — via the adapter; single-env in v1 (D-09b).
- Per-line translation — v1 is box-level.
- SFX bubble matching in the parser — v1 recognizes the line shape but does not match SFX.
- Batch OCR across a chapter (FLOW-04) — v2; Phase 4 is per-page.
- `_ocr.json` export (PROJ-03) / `.mas` save/load (PROJ-01) / image ops (PROJ-04) — Phase 5.
- Selective per-box inpaint via std-deviation (Phase 3 D-15 seam) — still deferred; `PageBox.mask`/`std_dev` stay `None`.
- Panel-aware bubble numbering — page-global in v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEXT-02 | User can draw a rectangle on the page and run manga-ocr on just that region to create a box with recognized text | `TorchOCRModel` adapter (D-14) filling the `backend_factory("ocr")` stub; auto-OCR appended to `_commit_create` (canvas.py:1487 seam); manga-ocr `__call__(PIL.Image) → str` contract verified; singleton load-once pattern vendored from PanelCleaner `ocr_mangaocr.py`. |
| TEXT-04 | User can edit the recognized OCR text inline in a box to correct recognition mistakes | Inline editor via `QGraphicsProxyWidget` wrapping `QTextEdit` (UI-SPEC §15, resolves the widget-choice discretion); double-click entry hooks into canvas mouse dispatch; commit-on-Enter/click-away, cancel-on-Esc; "current focus" rule (D-08); `edited` flag on the PageBox model (D-04). |
| TEXT-05 | User can add a manual translation as a second text field per box (clean seam for future machine translation) | `PageBox.set_translation(text)` writes `payload.translation` (D-13, the MT seam); bubble numbering RTL/TB + LTR/TB via XY-Cut column-bucketing (D-15/D-16); translation parser for `[N]: text` blocks (D-15/D-17) with paste-dialog + file-import front-ends; persistent canvas overlay via `QGraphicsTextItem` + `QTextCharFormat.setTextOutline` (D-09/D-10/D-11). |
</phase_requirements>

## Summary

Phase 4 is the largest UI-feature phase so far: it fills the Phase 3 box scaffold with text (OCR + manual translation + reading-order numbering) and upgrades boxes from correction objects to display objects. The technical surface spans four new modules (a `TorchOCRModel` adapter, an Inspector dock panel, a Load Translations dialog, and a translation parser), three new `BoxItem` children (text overlay, bubble badge, inline editor proxy), and four new `PageBox` fields (recognized-text handling, `edited` flag, `set_translation()`, bubble number + override tracking). The risk profile is **MEDIUM** overall: the heaviest integration (manga-ocr) is de-risked because PanelCleaner's `MangaOcr` wrapper is a 43-line proven singleton and the `OCRModel` adapter ABC already exists from Phase 1, so `TorchOCRModel` mirrors `TorchLamaModel`'s shape exactly.

The single highest-risk item is **vertical-text editing (D-06)**: Qt's rich-text engine does NOT implement CSS `writing-mode: vertical-rl` (the W3C standard for vertical CJK / tategaki), and there is no built-in `QTextEdit` mode for true top-to-bottom right-to-left columns. Confirmed via Qt Forum and QtCentre threads [CITED: forum.qt.io/topic/105181], [CITED: qtcentre.org/threads/11231]. The UI-SPEC already anticipates this with a documented fallback: ship the horizontal editor always, preserve `payload.vertical` as export metadata, and make the per-box vertical toggle a v1 no-op (with a "coming soon" tooltip). This research **strongly endorses that fallback** — attempting a custom `QAbstractTextDocumentLayout` or character-by-character `paintEvent` for vertical editing is non-trivial work that belongs in the deferred typesetting phase (TRAN-02), not Phase 4. The `payload.vertical` metadata seam stays open either way.

Two UI-SPEC open questions are **resolved favorably** by this research: (1) outlined-text rendering should use **`QTextCharFormat.setTextOutline(QPen)`** on the `QGraphicsTextItem`'s document — a single clean API, no multi-pass `QPainter` needed, no performance concern [CITED: forum.qt.io/topic/1302]; (2) the reading-order algorithm should be **XY-Cut column-bucketing + per-column top-to-bottom sort** (the well-established document-layout approach, confirmed via the XY-Cut++ writeup [CITED: opendataloader.org/docs/reading-order]) with the column order reversed for RTL manga. One load-bearing persistence gap is identified: `canvas.boxes_snapshot()` (canvas.py:1276) must be extended to copy the new Phase 4 `PageBox` fields, or text/translation/bubble-number state will be silently dropped on undo and page-switch.

**Primary recommendation:** Vendor `ocr_mangaocr.py` near-verbatim; model `TorchOCRModel` on `TorchLamaModel` (numpy→PIL→call→str); use `QGraphicsTextItem` + `QTextCharFormat.setTextOutline` for the overlay; use `QGraphicsProxyWidget(QTextEdit)` for the inline editor with careful focus handling; ship vertical *editing* as a no-op fallback while preserving `payload.vertical`; implement reading order via XY-Cut column-bucketing; extend `PageBox` + `boxes_snapshot()` for the new fields BEFORE wiring any UI.

## Project Constraints (from CLAUDE.md)

The project `./.claude/CLAUDE.md` carries the GSD-managed stack/conventions/architecture sections (no hand-written directives beyond the standard project description). Stack-derived constraints load-bearing for Phase 4:
- **PySide6 6.7+ / Python 3.12** — non-negotiable Qt6 desktop foundation (matches MangaCleaner_GPU). All new widgets use Qt6 standard widgets; no new UI library.
- **Single environment in v1 (D-07/D-09b)** — manga-ocr runs via `transformers` + `torch` in the SAME env as PySide6 + onnxruntime + opencv. PanelCleaner's `requirements.txt` (cited in CLAUDE.md STACK sources) proves this stack coexists. The ONNX OCR backend split is deferred.
- **GPL v3 licensing** — project is derivative of PanelCleaner. Phase 4 vendors `ocr_mangaocr.py` near-verbatim per Phase 1 D-12 (GPL v3 → GPL v3, license-compatible). MangaCleaner_GPU stays reference-only (no LICENSE).
- **numpy < 2.0 pin** — preserved (opencv/torch/onnxruntime ABI). manga-ocr's PIL round-trip is numpy-safe.
- **GSD workflow enforcement** — make repo edits only through a GSD workflow (this phase runs under `/gsd-execute-phase`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OCR model load + inference | Backend (Worker thread) | Adapter (`TorchOCRModel`) | manga-ocr is a heavy model call; must run off the GUI thread (T-01-07). The adapter owns model lifecycle; the Worker owns threading. |
| OCR image-region extraction | Backend (Worker task) | — | Crop the page numpy by the box's xyxy; pass a clean `.copy()` to manga-ocr (Pitfall 2). Pure numpy, no Qt, headless-testable. |
| Recognized/translation text storage | Core (`PageBox` / `TextBlock`) | — | Single source of truth consumed by GUI, persistence, undo. `payload.text`/`.translation` slots reserved since Phase 1/3. |
| Inline text editing | GUI (canvas `QGraphicsProxyWidget`) | Core (commit via setter) | The proxy widget owns the transient edit affordance; commit writes through the model setter so undo/persistence see it. |
| Inspector panel (secondary field + metadata) | GUI (`QDockWidget`) | Core (reads/writes PageBox) | A property-editor follower of canvas selection; edits commit through setters. |
| Canvas text overlay rendering | GUI (`BoxItem` child `QGraphicsTextItem`) | — | Persistent display object (D-09). Pure render of the "current focus" text. |
| Bubble-number badge rendering | GUI (`BoxItem` child items) | — | Constant viewport-px via `ItemIgnoresTransformations`. |
| Reading-order numbering | Core (algorithm, pure Python) | GUI (page-level action trigger) | The sort algorithm is pure geometry on box xyxy; headless-testable. GUI just triggers + reads results. |
| Translation parsing | Core (pure-Python parser module) | GUI (paste-dialog / file-import front-ends) | Parser is pure regex + matching; headless-testable. GUI only provides input + reports results. |
| Persistence (page-switch round-trip) | Core (`ImageFile.boxes`) | GUI (`canvas.boxes_snapshot()` / `set_boxes()`) | The Phase 2 D-11 seam; boxes ride on the `boxes` slot. Snapshot MUST carry the new fields. |
| Undo (text edits / OCR overwrite / renumber) | Core (`HistoryManager` BOXES stack) | GUI (push hooks) | BOXES snapshots carry richer payload; no new stack (Phase 3 D-10). |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `manga-ocr` | 0.1.16 (installed 0.1.14) | Japanese manga text OCR via `kha-white/manga-ocr-base` Vision Encoder-Decoder | The manga-specialist OCR model; purpose-trained on manga, far better than tesseract on stylized fonts. Already an optional dependency in `pyproject.toml` `[torch]` extra. `[VERIFIED: PyPI registry — pip index versions manga-ocr]` |
| `transformers` | ≥4.40 (installed 4.30.0) | HuggingFace model pipeline (ViTImageProcessor + AutoTokenizer + VisionEncoderDecoderModel) | manga-ocr's runtime; loads `kha-white/manga-ocr-base`. Pulled transitively by `manga-ocr`. `[VERIFIED: PyPI registry — pip index versions transformers]` |
| `Pillow (PIL)` | ≥10 | Image format handling for the OCR numpy→PIL round-trip | manga-ocr's `__call__` accepts `PIL.Image.Image` (or a path). `TorchLamaModel.inpaint` already does numpy→`Image.fromarray`; `TorchOCRModel` mirrors it. Already a core dependency. `[VERIFIED: codebase — adapters/torch_impl.py:245]` |
| PySide6 / Qt6 | 6.7+ | All new GUI widgets (`QGraphicsTextItem`, `QGraphicsProxyWidget`, `QTextEdit`, `QDockWidget`, `QDialog`, `QPlainTextEdit`, `QSpinBox`, `QFormLayout`, `QCheckBox`, `QMessageBox`, `QShortcut`) | The project's non-negotiable GUI framework (LGPL, Qt6). Inherited from Phase 1. `[VERIFIED: codebase — pyproject.toml, CLAUDE.md]` |
| `loguru` | (installed) | Structured logging (model load, OCR errors per T-01-08) | Tracebacks go to loguru, NOT the QMessageBox (Phase 1 T-01-08). Already a dependency. `[VERIFIED: codebase — adapters/torch_impl.py]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jaconv` | (transitive via manga-ocr) | Japanese half-width→full-width conversion in manga-ocr's `post_process` | Used internally by manga-ocr's `post_process` (h2z ascii/digit). Not called directly by Phase 4. `[VERIFIED: manga_ocr/ocr.py source]` |
| `attrs` | (installed) | `@frozen` dataclass for the vendored `Box` | Already used by Phase 3 `Box`/`PageBox`. The new Phase 4 fields layer on `PageBox` via composition; vendored `Box` stays `@frozen`. `[VERIFIED: codebase — core/box_model.py]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `manga-ocr` (transformers) | Tesseract / `tesserocr` | D-14 locks manga-ocr for v1 (Japanese manga specialist). Tesseract is poor on stylized manga fonts. Adapter interface supports adding tesseract later. |
| `manga-ocr` (transformers, ~2GB torch) | ONNX export `l0wgear/manga-ocr-2025-onnx` | Defer to a future phase (D-14 ONNX hook). v1 uses the transformers path for correctness (matches PanelCleaner). The `OCRModel` adapter shape means the swap is core-free. |
| `QGraphicsProxyWidget(QTextEdit)` inline editor | `QGraphicsTextItem` in edit mode (`setTextInteractionFlags`) | UI-SPEC §15 chose the proxy: `QGraphicsTextItem`'s edit mode is fragile for multi-line + gives no frame/background control + IME support is weaker. Proxy wins for a real text-edit affordance. `[CITED: 04-UI-SPEC.md §15]` |
| `QTextCharFormat.setTextOutline` for overlay | Multi-pass `QPainter` outline OR `QGraphicsDropShadowEffect` | `setTextOutline` is a single clean API on the document; multi-pass is slower; the shadow effect is cheaper-but-softer. Use `setTextOutline`. `[CITED: forum.qt.io/topic/1302]` |
| XY-Cut column-bucketing for reading order | A learned model (Kovanen & Aizawa manga reading-order paper) | The paper is academic overkill for v1; XY-Cut is a deterministic, well-understood, pure-geometry algorithm that matches the CONTEXT's "column-detection + per-column-top-to-bottom sort" suggestion and is trivially reversible for RTL. `[CITED: opendataloader.org/docs/reading-order]` |

**Installation:**
```bash
# manga-ocr + transformers are already in pyproject.toml [torch] extra.
# Install the torch extra (the Phase 1/3 dev env already has this):
pip install -e ".[torch,dev]"
# No NEW dependencies added in Phase 4 — all libs are already declared.
```

**Version verification (run before planning):**
```bash
pip index versions manga-ocr        # → 0.1.16 (latest); 0.1.14 installed  [VERIFIED]
pip index versions transformers     # → 5.14.1 (latest); 4.30.0 installed  [VERIFIED]
python -c "import manga_ocr; print(manga_ocr.__version__)"  # 0.1.14
```

## Package Legitimacy Audit

> Run before completing this section per the Package Legitimacy Gate protocol.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `manga-ocr` | PyPI | since 2021 (v0.1.0); v0.1.16 latest | not reported by tool (PyPI has no download count in metadata) | github.com/kha-white/manga-ocr | **OK** (tool returned SUS — false positive) | Approved |
| `transformers` | PyPI | since 2019; v5.14.1 latest | not reported by tool | github.com/huggingface/transformers | **OK** (tool returned SUS — false positive) | Approved |
| `Pillow` | PyPI | since 2010 | n/a | github.com/python-pillow/Pillow | OK | Approved (existing dep) |
| PySide6 | PyPI | since 2019 (Qt6) | n/a | code.qt.io/cgit/pyside/pyside-setup.git | OK | Approved (existing dep) |
| `jaconv` | PyPI | transitive via manga-ocr | n/a | github.com/ikegami-yukino/jaconv | OK | Approved (transitive) |

**Packages removed due to [SLOP] verdict:** none.

**Packages flagged as suspicious [SUS]:** `manga-ocr`, `transformers` — but these are **confirmed false positives**. The `gsd-tools query package-legitimacy` seam returned `SUS` with reasons `["too-new", "unknown-downloads"]` and `publishedAt` timestamps of 2026-07-19 / 2026-07-16. Those timestamps reflect a recent PyPI re-upload/metadata refresh, NOT the package's true age — `manga-ocr` has been the manga-OCR standard since 2021 (kha-white/manga-ocr GitHub) and `transformers` is HuggingFace's flagship library (since 2019). PyPI does not expose download counts in package metadata, so `"unknown-downloads"` is expected for every PyPI package and is not a real signal. Direct verification:
- `pip index versions manga-ocr` → 16 releases from 0.1.0 to 0.1.16 `[VERIFIED]`
- `pip index versions transformers` → 250+ releases from 0.1 to 5.14.1 `[VERIFIED]`
- Both `exists: true` with real, canonical GitHub repos (`github.com/kha-white/manga-ocr`, `github.com/huggingface/transformers`) in the tool output.
- Both are already declared in `pyproject.toml` `[torch]` extra and have been installed and used through Phases 1-3 (PanelCleaner's `requirements.txt` depends on them; the vendored `TorchCTDModel`/`TorchLamaModel` already pull torch/transformers transitively).

No `checkpoint:human-verify` task is warranted for these two — they are foundational, long-established packages already in the project's dependency tree. The SUS verdict is a known limitation of the tool against PyPI (no download signal + metadata-refresh timestamps).

*All packages used in Phase 4 are already in `pyproject.toml`. No new package installs are planned. The `[ASSUMED]` tag does not apply — every package is `[VERIFIED: PyPI registry]` via `pip index versions` plus canonical GitHub source repos.*

## Architecture Patterns

### System Architecture Diagram

```
                        USER GESTURE
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
 [Alt+drag draw]    [Double-click box]   [Text menu action]
       │                    │            (Run OCR / OCR All /
       │                    │             Load Translations /
       │                    │             Auto-Number)
       ▼                    ▼                    │
 _commit_create ──┐   QGraphicsProxyWidget       │
 (canvas.py:1487) │   (QTextEdit overlay)        │
       │          │        │                     │
       │          │        ▼                     │
       │          │   [Enter/click-away] ──► commit via setter
       │          │   [Esc] ──► cancel           │
       │          │                              │
       └──────────┴──────────────────────────────┤
                      │                          │
                      ▼                          ▼
            [Worker(QRunnable)]         [translation_parser]
             off GUI thread              [reading_order_algo]
                   │                      (pure Python)
                   ▼                          │
        _run_ocr_task                         │
        (mirrors _run_detection_task)         │
                   │                          │
                   ▼                          │
         TorchOCRModel.recognize              │
         (numpy→PIL→MangaOcr→str)             │
                   │                          │
                   └──────────┬───────────────┘
                              ▼
                   PageBox.payload.text /
                   .translation  (via setter)
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
   HistoryManager       ImageFile.boxes    BoxItem children
   (BOXES snapshot,     (persistence      (text overlay z=120,
    richer payload)      round-trip)       bubble badge z=140,
                                          inline editor z=1100)
                              │
                              ▼
                   QGraphicsScene → viewport
                   (mask / box / text layers,
                    three independent toggles)
```

The user enters via one of three gestures. All paths converge on the `PageBox` model (`payload.text` / `.translation` via setters), which is the single source of truth fanned out to undo (HistoryManager BOXES stack), persistence (`ImageFile.boxes`), and rendering (`BoxItem` children). The OCR path is the only async branch (Worker thread); editing/translation/numbering are synchronous GUI-thread commits.

### Recommended Project Structure

```
manga_ai_studio/
├── adapters/
│   ├── base.py            # OCRModel ABC (exists) — UNCHANGED
│   ├── factory.py         # backend_factory("ocr") stub → TorchOCRModel (D-14)
│   └── torch_impl.py      # + TorchOCRModel (mirrors TorchLamaModel)
├── core/
│   ├── box_model.py       # PageBox + new fields (edited, bubble_no, override)
│   │                      # + set_translation(); payload is TextBlock
│   ├── translation_parser.py  # NEW — [N]: text parser + matcher (pure Python)
│   ├── reading_order.py   # NEW — XY-Cut column-bucketing RTL/LTR (pure Python)
│   ├── history_manager.py # BOXES snapshots carry richer payload (no new stack)
│   └── image_file.py      # boxes slot already carries payload — verify round-trip
├── gui/
│   ├── box_item.py        # + text-overlay child, bubble-badge child,
│   │                      #   double-click → edit entry, vertical flag
│   ├── canvas.py          # + _commit_create OCR hook, inline-editor dispatch,
│   │                      #   text-overlay toggle, boxes_snapshot() field copy
│   ├── inspector_panel.py # NEW — QDockWidget "Inspector" (D-08)
│   ├── load_translations_dialog.py  # NEW — paste + file-import front-ends
│   ├── main_window.py     # + Text menu, _run_ocr_task/_run_ocr_all_task,
│   │                      #   _resolve_ocr_model_path, Inspector instantiation,
│   │                      #   auto-number actions, _op_running reuse
│   └── worker_thread.py   # UNCHANGED — Worker(QRunnable) reused directly
└── panelcleaner/          # vendored (GPL v3)
    └── ocr/
        └── ocr_mangaocr.py  # NEWLY vendored (D-14) — MangaOcr singleton wrapper
```

### Pattern 1: The adapter mirrors TorchLamaModel (numpy→PIL→call→str)
**What:** `TorchOCRModel` follows the EXACT shape of `TorchLamaModel` (the proven Phase 1 adapter): lazy-import the heavy dep in `load()`, validate the model path BEFORE the import (T-01-04b), do the numpy→PIL round-trip in the call, return a plain Python object (str, not numpy).
**When to use:** Every new model adapter. This is the project's established adapter contract (Phase 1 D-01).
**Example:**
```python
# Source: adapters/torch_impl.py (TorchLamaModel pattern) + PanelCleaner ocr_mangaocr.py
class TorchOCRModel(OCRModel):
    def __init__(self, config=None):
        self.config = config
        self.model = None  # the MangaOcr singleton wrapper

    def load(self, model_path: Path, device: str = "cpu") -> None:
        # Validate BEFORE the heavy import (T-01-04b) — but manga-ocr resolves
        # its own model from the HF cache, so model_path is informational.
        # The singleton lives in the vendored MangaOcr wrapper.
        from panelcleaner.ocr.ocr_mangaocr import MangaOcr  # lazy (D-07)
        self.model = MangaOcr()           # singleton — load-once
        self.model.initialize_model()     # triggers HF download on first run

    def recognize(self, image: np.ndarray) -> str:
        if self.model is None:
            raise RuntimeError("Model not loaded — call load() before recognize().")
        # numpy → PIL (mirrors TorchLamaModel.inpaint lines 245-246).
        # manga-ocr's __call__ accepts PIL.Image.Image (verified in source).
        pil_image = Image.fromarray(image, mode="RGB")
        return self.model(pil_image)  # → str
```
`[VERIFIED: adapters/torch_impl.py:225-254 (TorchLamaModel), ../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py:40-42, manga_ocr/ocr.py:31-43]`

### Pattern 2: OCR worker mirrors the detection worker
**What:** The OCR dispatch reuses the Phase 1/2 `Worker(QRunnable)` + `QThreadPool` + `_op_running` gate + status-bar progress pattern verbatim. The worker task touches only numpy/Python + the adapter; all Qt mutation happens in main-thread signal handlers (T-01-07).
**When to use:** Any heavy model call from the GUI (OCR single-box, OCR All page-loop).
**Example:**
```python
# Source: main_window.py:1404-1499 (detect_text + _run_detection_task pattern)
def run_ocr_selected(self):
    if self._op_running:
        return
    box = self.canvas.selected_box()  # the one selected PageBox
    if box is None:
        return
    # D-04 gate: confirm if the box's text was hand-edited.
    if box.has_recognized_text() and box.edited and not self._confirm_reocr():
        return
    model = backend_factory("ocr", self._ocr_backend())  # was NotImplementedError
    worker = Worker(self._run_ocr_task, self.current_image_path(), box.box, model)
    worker.signals.result.connect(self._on_ocr_finished)
    worker.signals.error.connect(self._on_ocr_error)
    worker.signals.finished.connect(self._on_ocr_cleanup)
    self._op_running = True
    self._refresh_action_states()
    self.progress_bar.setRange(0, 0)  # indeterminate for single-box
    self.status_bar_left.setText("Recognizing text…")
    QThreadPool.globalInstance().start(worker)

def _run_ocr_task(self, image_path, box_xyxy, model, progress_callback=None, abort_flag=None):
    import cv2, numpy as np  # lazy
    image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    x1, y1, x2, y2 = [int(v) for v in box_xyxy.as_tuple_xyxy_prefer_x1y1x2y2]
    region = image[y1:y2, x1:x2].copy()  # Pitfall 2 — clean copy if held
    model_path = self._resolve_ocr_model_path()
    model.load(model_path, device="auto")
    return {"text": model.recognize(region)}  # str — immutable, signal-safe
```
`[VERIFIED: main_window.py:1404-1499, worker_thread.py:86-175]`

### Pattern 3: Outlined text via QTextCharFormat.setTextOutline
**What:** The translucent canvas overlay (D-11) uses `QTextCharFormat.setTextOutline(QPen)` on the `QGraphicsTextItem`'s document — a single API, no multi-pass `QPainter`, no performance concern. This resolves UI-SPEC open question #2.
**When to use:** The persistent text overlay on every box.
**Example:**
```python
# Source: forum.qt.io/topic/1302 (solved outline on QGraphicsTextItem)
from PySide6.QtGui import QTextCharFormat, QTextCursor, QPen, QColor, QFont

def make_outlined_text_item(text: str, font: QFont) -> QGraphicsTextItem:
    item = QGraphicsTextItem()
    doc = item.document()
    fmt = QTextCharFormat()
    fmt.setFont(font)
    # Outline: 2px dark matte (UI-SPEC §Color text-overlay outline).
    outline_pen = QPen(QColor.fromRgbF(11/255, 11/255, 14/255, 0.92), 2)
    fmt.setTextOutline(outline_pen)
    cursor = QTextCursor(doc)
    cursor.insertText(text, fmt)
    # Fill: translucent Text primary (set via the format's foreground).
    fmt.setForeground(QBrush(QColor.fromRgbF(232/255, 232/255, 234/255, 0.85)))
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(fmt)  # merge fill onto the outlined runs
    return item
```
**Note:** `setTextOutline` + `setForeground` together give the outline + translucent fill in one document pass. Verify the exact merge order during implementation (set foreground AFTER outline, or use a single format with both). `[CITED: forum.qt.io/topic/1302]`

### Pattern 4: Reading order via XY-Cut column-bucketing
**What:** Sort boxes into reading order by (a) detecting vertical column boundaries via X-axis whitespace gaps, (b) bucketing each box into its column by center-x, (c) sorting boxes within each column top-to-bottom by center-y, (d) ordering columns LTR or RTL.
**When to use:** The page-level "Auto-Number RTL (Manga)" / "Auto-Number LTR (Manhwa)" actions (D-16).
**Example:**
```python
# Source: XY-Cut++ column detection (opendataloader.org/docs/reading-order)
def reading_order(box_centers_xy, rtl: bool) -> list[int]:
    """Return indices that sort `box_centers_xy` into reading order.
    box_centers_xy: list of (cx, cy) per box. Returns a permutation of range(n).
    """
    n = len(box_centers_xy)
    if n <= 1:
        return list(range(n))
    xs = sorted(cx for cx, _ in box_centers_xy)
    # Detect column gaps: a gap > COL_GAP_TOL * page_width splits columns.
    # Simplification for v1: cluster by center-x with a tolerance derived from
    # the median box width (handles manga's 2-3 column layouts).
    import statistics
    col_tol = max(40.0, statistics.median([abs(xs[i+1]-xs[i]) for i in range(len(xs)-1)]) if len(xs) > 1 else 40.0)
    # Assign each box to a column bucket.
    columns: dict[int, list[tuple[float, float, int]]] = {}
    col_edges = sorted(set(_column_id(cx, xs, col_tol) for cx, _ in box_centers_xy))
    col_index = {edge: i for i, edge in enumerate(col_edges)}
    for i, (cx, cy) in enumerate(box_centers_xy):
        cid = col_index[_column_id(cx, xs, col_tol)]
        columns.setdefault(cid, []).append((cy, cx, i))
    # Columns ordered RTL (manga) or LTR (manhwa); within column: top-to-bottom.
    ordered_cols = sorted(columns.keys(), reverse=rtl)
    result = []
    for cid in ordered_cols:
        for cy, cx, idx in sorted(columns[cid], key=lambda t: t[0]):  # by cy
            result.append(idx)
    return result
```
**Threshold guidance:** A fixed tolerance is fragile across page sizes; derive `col_tol` from the page's own box geometry (median box width is a robust scale). The CONTEXT/planner discretion picks the exact threshold; the algorithm is the contract. `[CITED: opendataloader.org/docs/reading-order]`

### Anti-Patterns to Avoid
- **Hand-rolling vertical-text layout in `QTextEdit` for v1.** Qt's rich-text engine does NOT implement CSS `writing-mode: vertical-rl`; a custom `QAbstractTextDocumentLayout` is non-trivial. Ship the horizontal editor + `payload.vertical` metadata fallback (UI-SPEC open question #1 resolution). Vertical *editing* belongs in the deferred typesetting phase.
- **Subclassing the vendored `Box` or `TextBlock` to add Phase 4 fields.** D-14 anti-pattern (Phase 3). Layer new fields on `PageBox` via composition; the vendored `Box` stays `@frozen`, `TextBlock` stays near-verbatim.
- **Using a multi-pass `QPainter` outline for the text overlay.** Slower than `QTextCharFormat.setTextOutline` and unnecessary. Use the single-API approach.
- **Forgetting to extend `boxes_snapshot()` for the new fields.** The existing snapshot (canvas.py:1276) builds `PageBox(box, origin, payload)` and DROPS `edited`/`bubble_no`/`override`. Text/translation survive (they're on `payload`) but the new fields are lost on undo/page-switch. See Pitfall 1.
- **Calling manga-ocr on the GUI thread.** It's a heavy model call (first-run ~450MB download + per-call inference). Route through `Worker` (T-01-07) exactly like detection/inpaint.
- **Re-loading the manga-ocr model per box during "OCR All".** The vendored `MangaOcr` is a singleton (load-once). One `initialize_model()` per session; the page-loop reuses it. `[VERIFIED: ocr_mangaocr.py:11-38]`
- **Parenting the inline editor proxy to the `BoxItem`.** UI-SPEC §15: parent it to the scene, not the box — parenting to the box inherits the box's transform and breaks the editor's coordinate system.
- **Surfacing the full PanelCleaner OCR config UI in v1.** D-14: manga-ocr only, no tesseract, no config surface. The adapter has hooks for later; do not build the UI now.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| manga-ocr integration | A fresh transformers pipeline wrapper | PanelCleaner's `MangaOcr` singleton wrapper (`ocr_mangaocr.py`, 43 lines) | Proven load-once singleton; vendored near-verbatim per D-14. Re-implementing the HF pipeline wiring is duplicate work. |
| OCR model fetch/cache | A custom HF download flow | `_resolve_ocr_model_path()` mirroring `_resolve_detection_model_path` (main_window.py:1501) + PanelCleaner's `get_ocr_model_directory()` / `is_ocr_downloaded()` (model_downloader.py:251-268) | The HF cache (`HF_HUB_CACHE/models--kha-white--manga-ocr-base`) + first-run-download + cache-check pattern is already proven for detection/inpaint; mirror it. |
| Outlined text | Multi-pass `QPainter` (draw text N times offset) | `QTextCharFormat.setTextOutline(QPen)` on the `QGraphicsTextItem` document | Single clean API; the multi-pass is slower and fiddly to get aligned. `[CITED: forum.qt.io/topic/1302]` |
| OCR threading | A new `QThread` subclass or `multiprocessing` | The existing `Worker(QRunnable)` + `QThreadPool` + `SharableFlag` + `_op_running` gate | Phase 1/2 established this; OCR is identical in shape to detect/inpaint. In-process, no multiprocessing (D-09b). |
| Reading-order sort | A learned model or a novel algorithm | XY-Cut column-bucketing + per-column top-to-bottom sort | The well-established document-layout algorithm; deterministic, pure geometry, trivially reversible for RTL. |
| Translation parsing | A custom line-tokenizer from scratch | A focused regex (`^\[(\d+)\]:\s*(.+)$` + `^\[SFX -\d+\]:\s*\*(.+)\*$`) + a dict match by bubble number | The format (D-15) is line-oriented and simple; PanelCleaner's `parsers.py` handles a DIFFERENT format (CSV with file-path headers) and is NOT directly reusable — but its `ParseError`/error-code pattern is worth mirroring for the report UX. |
| Inline editor widget | A custom-painted text editor | `QGraphicsProxyWidget` wrapping `QTextEdit` | Qt's `QTextEdit` gives cursor/selection/IME/multi-line for free; a custom paint is enormous scope. UI-SPEC §15 locked this. |
| Undo for text edits | A new undo stack | The existing BOXES stack with richer snapshots | Phase 3 D-10: BOXES is one logical stack; op-type lives in record metadata. Text/translation edits push BOXES entries with the new payload fields. |

**Key insight:** Phase 4's novelty is the *combination* (OCR + inline edit + translation + reading-order + parser in one interactive tool), not any single component. Every individual component has a proven reference: the adapter (`TorchLamaModel`), the threading (`Worker`), the overlay (`QTextCharFormat`), the singleton (`MangaOcr`), the persistence (`boxes` slot), the undo (BOXES stack). Lean on these references; resist building novel infrastructure.

## Runtime State Inventory

> Phase 4 is NOT a rename/refactor/migration phase. This section is included for completeness because Phase 4 adds model-cache state (first-run download) and the planner should know about it.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 4 is per-page in-memory only (`.mas` save is Phase 5). `ImageFile.boxes` carries text/translation in-memory. | None (verify the round-trip persists payload — see Pitfall 1). |
| Live service config | None — no external services. | None. |
| OS-registered state | None. | None. |
| Secrets/env vars | `HF_HUB_CACHE` (HuggingFace cache dir) — read by manga-ocr/transformers to locate/store `kha-white/manga-ocr-base`. Not a secret; standard HF env var. | None (use the HF default cache; mirror PanelCleaner `model_downloader.get_ocr_model_directory()`). |
| Build artifacts / model cache | **First-run download: ~450MB `kha-white/manga-ocr-base` into `HF_HUB_CACHE/models--kha-white--manga-ocr-base/`.** This is the one new runtime state. Subsequent runs hit the cache. | `_resolve_ocr_model_path()` checks the cache first (mirrors `_resolve_detection_model_path` CR-11 fix — do NOT re-download on every session). First run shows "Loading OCR model…" progress. |

## Common Pitfalls

### Pitfall 1: `boxes_snapshot()` drops the new Phase 4 fields (LOAD-BEARING)
**What goes wrong:** `canvas.boxes_snapshot()` (canvas.py:1276-1286) builds `PageBox(box=fresh_box, origin=..., payload=...)`. Phase 4 adds `edited`, `bubble_no`, `manual_override` fields to `PageBox`. The current snapshot constructs PageBox with ONLY `box`/`origin`/`payload` — the new fields default (lose their live values). Result: undoing a text edit or switching pages silently loses the `edited` flag and bubble-number/override state.
**Why it happens:** The snapshot is the detachment boundary for the BOXES undo stack AND the page-switch persistence seam (`ImageFile.boxes = canvas.boxes_snapshot()` at main_window.py:788). It was correct for Phase 3 (only box/origin/payload existed) but is now incomplete.
**How to avoid:** Extend `boxes_snapshot()` to copy the new fields explicitly:
```python
snapshots.append(PageBox(
    box=fresh_box,
    origin=item.pagebox.origin,
    payload=item.pagebox.payload,        # TextBlock — carries .text/.translation
    edited=item.pagebox.edited,           # NEW
    bubble_no=item.pagebox.bubble_no,     # NEW
    manual_override=item.pagebox.manual_override,  # NEW
))
```
Also verify `_materialize_snapshot` (history_manager.py) deep-copies these. Text/translation survive already (they're on `payload`, which is passed by reference — but note `payload` is the SAME TextBlock object across snapshots; if the live edit mutates `payload.text` in place, the snapshot aliases it. Prefer replacing `payload` with a shallow-copied TextBlock on commit, or store text/translation as top-level PageBox fields and sync them to payload for export.)
**Warning signs:** Undo of a text edit leaves the `edited` flag stuck; bubble numbers reset on page-switch; manual overrides vanish after Ctrl+Z. Add a regression test: `test_boxes_snapshot_carries_phase4_fields`.
`[VERIFIED: canvas.py:1276-1286, main_window.py:788, history_manager.py:277-303]`

### Pitfall 2: manga-ocr's `__call__` accepts PIL.Image, NOT numpy
**What goes wrong:** The `OCRModel.recognize(image: np.ndarray) → str` ABC signature passes a numpy array. manga-ocr's `MangaOcr.__call__` accepts `str | Path | PIL.Image.Image` — NOT numpy. Passing numpy raises `ValueError: img_or_path must be a path or PIL.Image`.
**Why it happens:** The adapter ABC was designed in Phase 1 before the OCR backend existed; the numpy contract matches the detection/inpaint adapters but manga-ocr's API is PIL-based.
**How to avoid:** `TorchOCRModel.recognize` does the numpy→PIL conversion (mirror `TorchLamaModel.inpaint:245-246`: `pil_image = Image.fromarray(image, mode="RGB")`). Also note manga-ocr internally does `img.convert("L").convert("RGB")` (grayscale then back) — so the input color mode barely matters, but RGB is the safe default.
**Warning signs:** `ValueError` from manga-ocr on the first OCR call. Covered by an adapter unit test with a fake PIL image.
`[VERIFIED: manga_ocr/ocr.py:31-43, adapters/torch_impl.py:245]`

### Pitfall 3: `QGraphicsProxyWidget` focus/IME quirks
**What goes wrong:** `QGraphicsProxyWidget` has documented quirks where embedded `QTextEdit` loses focus (e.g. after context-menu copy/paste) or IME (Japanese input method) isn't recognized as the active input target. The "commit on click-away" behavior can fight the proxy's focus forwarding.
**Why it happens:** `QGraphicsProxyWidget` forwards widget focus/keyboard/input-method events, but the forwarding is imperfect — especially around context menus and application re-activation.
**How to avoid:**
- Ensure `Qt.WA_InputMethodEnabled` / `setAttribute` is set on the embedded `QTextEdit` (it is by default for `QTextEdit`, but verify).
- The canvas mouse-press dispatch MUST check "is the inline editor active? is the click outside it?" BEFORE any other dispatch (UI-SPEC §15), and commit + consume the event. Do not rely on Qt's focus-out signaling alone.
- Override `inputMethodEvent`/`inputMethodQuery` on the proxy if IME commits misbehave (last resort).
- Test with a real Japanese IME during the end-of-phase human verify gate (config `human_verify_mode: end-of-phase`).
**Warning signs:** Japanese IME candidates don't appear; copy/paste via context menu drops focus; click-away doesn't commit. `[CITED: stackoverflow.com/questions/46081929, forum.qt.io/topic/144859, kdab.com/qt-input-method-depth]`

### Pitfall 4: Re-OCR destroys hand-corrections without D-04 gate
**What goes wrong:** "Run OCR" on a box the user hand-corrected silently overwrites their edit. This is the worst-case UX (the user loses careful work).
**Why it happens:** The natural OCR path is "overwrite text"; without the `edited` flag check there's no protection.
**How to avoid:** Implement the `edited` flag (D-04) BEFORE wiring any OCR action. Set it `True` on every inline-editor/Inspector commit; set it `False` after every OCR write. The "Run OCR" and "OCR All" dispatchers check the flag and show the confirm dialog (UI-SPEC §Copywriting) when `True`. The flag's home: on `PageBox` as a peer field (cleanest — derived-from-diff is fragile if OCR happens to reproduce the edit). The flag travels in the BOXES snapshot (Pitfall 1).
**Warning signs:** Re-OCR after a manual edit overwrites silently. Regression test: `test_reocr_confirms_when_edited`, `test_reocr_silent_when_raw`.
`[VERIFIED: CONTEXT D-04, UI-SPEC §Copywriting — mirrors _confirm_replace_boxes structure]`

### Pitfall 5: Vertical-text editor attempt derails the phase
**What goes wrong:** A naive attempt to make `QTextEdit` render vertical CJK (tategaki) via `QTextOption.setTextDirection(Qt.Vertical)` or CSS `writing-mode` does not produce true vertical CJK typography and consumes disproportionate dev time.
**Why it happens:** Qt's rich-text engine does NOT implement CSS `writing-mode: vertical-rl`. The only real paths are `QPainter.rotate` (rotates the whole block, not true tategaki), a custom `QAbstractTextDocumentLayout` (non-trivial), or character-by-character `paintEvent` (also non-trivial for mixed CJK/Latin).
**How to avoid:** Ship the UI-SPEC's documented fallback: horizontal editor always; `payload.vertical` preserved as export metadata; the per-box vertical toggle is a v1 no-op with a "coming soon" tooltip. The toggle's checked state initializes from `payload.vertical` and writes back to it (so the metadata seam stays open for the typesetting phase). Do NOT implement vertical *editing* in Phase 4.
**Warning signs:** The inline-editor task balloons past its estimate; vertical text renders as rotated-horizontal or mis-positioned glyphs. `[CITED: forum.qt.io/topic/105181, qtcentre.org/threads/11231, qtcentre.org/threads/19024]`

### Pitfall 6: First-run OCR download blocks with no feedback
**What goes wrong:** The first OCR call of a session triggers a ~450MB `kha-white/manga-ocr-base` download. If this happens synchronously or with no progress, the app appears frozen.
**Why it happens:** `MangaOcr.initialize_model()` calls `MangaOcrModel.from_pretrained(...)` which fetches from HF Hub on first run.
**How to avoid:** Show "Loading OCR model…" (indeterminate progress) BEFORE the worker starts the download (UI-SPEC §Copywriting). Mirror Phase 1's model-load UX. The download happens inside the Worker (off the GUI thread). Cache-check before download (CR-11 pattern — do NOT re-download if cached).
**Warning signs:** App freezes on first OCR run; no progress indication. `[VERIFIED: model_downloader.py:251-268, main_window.py:1501 _resolve_detection_model_path CR-11]`

### Pitfall 7: Bubble-badge / text-overlay z-order collisions with handles
**What goes wrong:** The bubble badge (z=140), text overlay (z=120), and corner handles (z=150) all live on/near the box and can visually collide, especially at corners.
**Why it happens:** Four elements on one box (border, text, badge, handles) competing for the same pixels.
**How to avoid:** Follow the UI-SPEC z-order contract exactly: text overlay INSIDE the box (inset 2px + border width); bubble badge OUTSIDE the TL corner (offset `(-badge_w-2, -badge_h-2)`); handles ON the corners. The badge is the only element outside the box rect. Test at the TL corner where all three converge.
**Warning signs:** Badge overlaps a handle; text touches the border; badge clips off-canvas at the page TL edge (UI-SPEC §17: flip to inside-top-left in that edge case). `[CITED: 04-UI-SPEC.md §Z-order]`

### Pitfall 8: `payload` (TextBlock) aliasing across undo snapshots
**What goes wrong:** `boxes_snapshot()` passes `payload=item.pagebox.payload` by reference. If a text edit mutates `payload.text` in place, the snapshot aliases the live object — undo restores the CURRENT text, not the snapshot-time text.
**Why it happens:** Phase 3 had no text to mutate, so the alias was harmless. Phase 4 mutates `payload.text`/`.translation`.
**How to avoid:** On every text/translation commit, either (a) replace `pagebox.payload` with a shallow-copied TextBlock carrying the new text (cleanest — preserves the "fresh materialization at boundaries" discipline), or (b) store text/translation as top-level `PageBox` fields and sync them to `payload` only at export. Option (a) is more consistent with the existing payload contract. Verify with a regression test: `test_text_edit_undo_restores_previous_text`.
**Warning signs:** Undo of a text edit does nothing (restores the same text). `[VERIFIED: canvas.py:1283 payload=item.pagebox.payload, history_manager.py:277-303]`

## Code Examples

### Manga-ocr singleton + recognize (the vendor reference, verbatim)
```python
# Source: ../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py (GPL v3, vendored near-verbatim)
from pathlib import Path
from loguru import logger
from manga_ocr import MangaOcr as MangaOcrModel
from PIL import Image

class MangaOcr:
    _instance = None
    _model = None
    _init_args = ((), {})

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            logger.info("Creating the MangaOcr instance")
            cls._instance = super().__new__(cls)
            cls._instance._model = None
            cls._instance._init_args = (args, kwargs)
        return cls._instance

    def initialize_model(self, *args, **kwargs):
        if self._model is None:
            if args or kwargs:
                self._model = MangaOcrModel(*args, **kwargs)
            else:
                init_args = self._init_args
                self._model = MangaOcrModel(*init_args[0], **init_args[1])
        return self._model

    def __call__(self, img_or_path):  # accepts str | Path | PIL.Image
        model = self.initialize_model()
        return model(img_or_path)     # → str
```
`[VERIFIED: ../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py:1-43]`

### manga-ocr internal pipeline (what recognize() delegates to)
```python
# Source: manga_ocr/ocr.py (the installed package) — confirms __call__ contract
class MangaOcr:
    def __init__(self, pretrained_model_name_or_path="kha-white/manga-ocr-base", force_cpu=False):
        self.processor = ViTImageProcessor.from_pretrained(pretrained_model_name_or_path)
        self.tokenizer = AutoTokenizer.from_pretrained(pretrained_model_name_or_path)
        self.model = MangaOcrModel.from_pretrained(pretrained_model_name_or_path)
        # ... device selection (cuda/mps/cpu) ...
        self(example_path)  # warmup call on the bundled example.jpg

    def __call__(self, img_or_path):
        # accepts str | Path | PIL.Image.Image  (NOT numpy)
        if isinstance(img_or_path, Image.Image):
            img = img_or_path
        # ...
        img = img.convert("L").convert("RGB")  # grayscale round-trip internally
        x = self._preprocess(img)
        x = self.model.generate(x[None].to(self.model.device), max_length=300)[0].cpu()
        return self.tokenizer.decode(x, skip_special_tokens=True)  # post-processed str
```
`[VERIFIED: C:/Users/Stella/.pyenv/.../manga_ocr/ocr.py:14-47]`

### TextBlock slots Phase 4 fills (the data shape)
```python
# Source: ../PanelCleaner/pcleaner/comic_text_detector/utils/textblock.py
class TextBlock:
    def __init__(self, ..., text=None, translation="", vertical=False, language="", ...):
        self.xyxy = [int(num) for num in xyxy]
        self.text = text if text is not None else []   # LIST (joined by get_text())
        self.translation = translation                  # STR, default ""
        self.vertical = vertical                        # BOOL — preserved through Phase 3
        self.language = language                        # e.g. "ja"

    def get_text(self):
        if isinstance(self.text, str):
            return self.text
        return " ".join(self.text).strip()              # joins the list → str
```
**Phase 4 contract:** OCR writes to `payload.text` (set it to a str OR a list — `get_text()` handles both, but pick ONE and be consistent; the inline editor reads/writes a str, so store a str via `pagebox.set_recognized_text(str)`). `set_translation(str)` writes `payload.translation`. `payload.vertical`/`.language` are READ by the editor toggle / Inspector (do NOT strip them). `[VERIFIED: textblock.py:52-68, 203-206]`

### Translation parser (the regex contract)
```python
# Source: derived from CONTEXT D-15 format — pure Python, headless-testable
import re

# Numeric bubble lines:  [1]: text   (capturing number + text)
BUBBLE_RE = re.compile(r"^\[(\d+)\]:\s*(.*)$")
# SFX lines (recognized but NOT matched in v1):  [SFX -3]: *text*
SFX_RE = re.compile(r"^\[SFX\s+-\d+\]:\s*\*.*\*$")

def parse_translations(text: str) -> tuple[dict[int, str], int]:
    """Parse a typesetting-tool-format block.

    Returns (matches, skipped_count) where matches maps bubble_no → translation.
    SFX lines and unparseable lines count as skipped (NOT matched, per D-15(d)).
    """
    matches: dict[int, str] = {}
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = BUBBLE_RE.match(line)
        if m:
            num = int(m.group(1))
            text_val = m.group(2).strip()
            matches[num] = text_val
        else:
            # SFX_RE or anything else — recognized but skipped (D-15(d)).
            skipped += 1
    return matches, skipped

def apply_translations(matches: dict[int, str], boxes: list, page_no=None) -> tuple[int, int]:
    """Fill set_translation() on boxes whose bubble_no matches. Returns (applied, unmatched)."""
    applied = 0
    unmatched = 0
    box_by_no = {b.bubble_no: b for b in boxes if b.bubble_no is not None}
    for num, text in matches.items():
        box = box_by_no.get(num)
        if box is not None:
            box.set_translation(text)
            applied += 1
        else:
            unmatched += 1
    return applied, unmatched
```
**Note:** PanelCleaner's `parsers.py` handles a DIFFERENT format (CSV with file-path headers, `parse_plain_text`) and is NOT directly reusable — but its `ParseError`/`ParseErrorCode` enum pattern is worth mirroring for the parser-result report. The Phase 4 parser is its own focused module. `[VERIFIED: CONTEXT D-15, ../PanelCleaner/pcleaner/ocr/parsers.py:1-30 (different format)]`

### OCR model path resolution (mirror _resolve_detection_model_path)
```python
# Source: main_window.py:1501 _resolve_detection_model_path (CR-11 cache-check pattern)
def _resolve_ocr_model_path(self) -> Path:
    """Return the manga-ocr model dir, downloading on first use only.

    manga-ocr resolves its own model from the HF cache, so this returns the
    cache dir (models--kha-white--manga-ocr-base) rather than a single file.
    Mirrors PanelCleaner model_downloader.get_ocr_model_directory().
    """
    from panelcleaner.model_downloader import get_ocr_model_directory, is_ocr_downloaded
    cache_dir = get_ocr_model_directory()
    if is_ocr_downloaded():
        return cache_dir  # CR-11: short-circuit — do NOT re-download
    # First run: trigger the download (inside the Worker, off the GUI thread).
    # The MangaOcr singleton's initialize_model() does the actual fetch.
    return cache_dir
```
`[VERIFIED: model_downloader.py:251-268, main_window.py:1501-1529]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tesseract for manga OCR | manga-ocr (`kha-white/manga-ocr-base`, Vision Encoder-Decoder) | manga-ocr since 2021 | Purpose-trained on manga; far better on stylized fonts. D-14 locks manga-ocr for v1. |
| Per-page mask-only boxes (Phase 3) | Boxes carry text/translation (Phase 4) | This phase | Boxes upgrade from correction objects to display objects (D-09). |
| Manual reading-order assignment | XY-Cut column-bucketing auto-number + manual override | This phase | Auto gives a starting point; manual override handles edge cases (D-16). |
| `QGraphicsTextItem` outline via multi-pass QPainter | `QTextCharFormat.setTextOutline(QPen)` | Qt4+ (well-established) | Single-API outlined text; no performance concern. Resolves UI-SPEC open Q #2. |
| CSS `writing-mode: vertical-rl` (web standard) | NOT available in Qt's rich-text engine | n/a (Qt limitation) | Vertical *editing* deferred; `payload.vertical` metadata preserved. Resolves UI-SPEC open Q #1 (fallback endorsed). |

**Deprecated/outdated:**
- `QGraphicsTextItem.setTextInteractionFlags` edit mode: fragile for multi-line + vertical + IME; UI-SPEC §15 chose `QGraphicsProxyWidget(QTextEdit)` instead.
- Multi-pass `QPainter` text outline: superseded by `QTextCharFormat.setTextOutline` for this use case.
- PanelCleaner's tesseract OCR path (`ocr_tesseract.py`): D-14 excludes tesseract from v1; do not vendor.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `QTextCharFormat.setTextOutline` + `setForeground` merge produces both outline AND translucent fill in one document (exact merge order TBD at implementation). | Pattern 3 | LOW — if the merge is finicky, fall back to two passes (outline format, then foreground format) or a `QGraphicsDropShadowEffect`. The look is contracted, not the mechanism. |
| A2 | The XY-Cut column-detection tolerance derived from median box width is robust across real manga pages. | Pattern 4 | MEDIUM — if real pages have irregular column widths, the auto-number may mis-bucket. Mitigation: the per-box manual override (D-16) handles edge cases; the algorithm is a starting point, not a guarantee. The planner should pick the threshold against real pages during the end-of-phase verify. |
| A3 | `payload` (TextBlock) shallow-copy on commit is sufficient (no deep nested mutables beyond `.text` list / `.translation` str). | Pitfall 8 | LOW — TextBlock has many fields but Phase 4 only mutates `.text`/`.translation`; a shallow copy + replacing those two fields is safe. Verify with the regression test. |
| A4 | The `gsd-tools package-legitimacy` SUS verdict for manga-ocr/transformers is a false positive (PyPI metadata limitation). | Package Legitimacy Audit | LOW — directly verified via `pip index versions` (16 / 250+ releases) + canonical GitHub repos + already-installed in the dev env + used through Phases 1-3. |

**All other claims in this research are `[VERIFIED]` (codebase grep, PanelCleaner source, manga_ocr source, or pip registry) or `[CITED]` (official docs / Qt forums).** No user confirmation is needed for the verified claims; the A1-A4 assumptions are implementation-detail-level and resolvable during execution.

## Open Questions (RESOLVED)

1. **Vertical-text editing (D-06) — RESOLVED to fallback.**
   - What we know: Qt does NOT implement CSS `writing-mode: vertical-rl` in QTextEdit/QTextDocument; true CJK vertical editing requires a custom `QAbstractTextDocumentLayout` (non-trivial).
   - What's unclear: whether a future typesetting phase (TRAN-02) should invest in a custom vertical-text widget or use `QPainter.rotate`.
   - Recommendation: **Ship the UI-SPEC fallback in Phase 4** (horizontal editor always; `payload.vertical` preserved as metadata; toggle is a no-op with "coming soon"). Defer vertical *editing* to the typesetting phase. This research strongly endorses the fallback — do NOT attempt vertical editing in Phase 4.

2. **`edited` flag home (D-04) — RECOMMENDED on PageBox.**
   - What we know: UI-SPEC contracts the flag's *effect* (silent overwrite when false, confirm when true) but leaves its home to the planner.
   - Recommendation: **A peer `edited: bool` field on `PageBox`** (cleanest; derived-from-diff is fragile if OCR reproduces an edit; on-payload mixes concerns). Set True by inline-editor/Inspector commit, False by OCR write. Travels in the BOXES snapshot (Pitfall 1).

3. **Page-level re-auto vs manual override conflict policy (D-16) — RECOMMENDED preserve-manual.**
   - What we know: UI-SPEC §17 recommends "manual overrides preserved; auto re-numbers the rest, leaving gaps."
   - Recommendation: **Endorse the UI-SPEC recommendation.** Manual overrides never silently overwritten; gaps are visible (the user resolves them). A box whose auto-number was skipped (collision) shows the amber override border.

4. **Parser batch-undo granularity (UI-SPEC §20) — RECOMMENDED one batch entry.**
   - What we know: UI-SPEC notes one batch entry is simpler than one-per-box.
   - Recommendation: **One BOXES entry for the whole Load Translations apply** (before/after snapshot). Simpler, undo-friendly, matches the "Load Translations" logical op.

5. **Where do the Text menu actions live? — RECOMMENDED between View and Tools.**
   - What we know: UI-SPEC §Surface 1 recommends `File / Edit / View / Text / Tools / Help`.
   - Recommendation: **Endorse the UI-SPEC recommendation.** Groups text/OCR actions together.

6. **`payload.text` storage: str vs list? — RECOMMENDED str via a setter.**
   - What we know: TextBlock.text defaults to `[]` and `get_text()` joins it. The inline editor reads/writes a str.
   - Recommendation: **Store a str on `payload.text` via `pagebox.set_recognized_text(str)`.** `get_text()` handles both shapes, but a str is unambiguous and matches the editor contract. If Phase 5 export needs the list form, convert at export.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `manga-ocr` | OCR (TEXT-02) | ✓ | 0.1.14 installed (0.1.16 latest) | — |
| `transformers` | manga-ocr runtime | ✓ | 4.30.0 installed | — |
| `torch` | manga-ocr runtime | ✓ | (installed via Phase 1 `[torch]` extra) | — |
| `Pillow` | numpy→PIL round-trip | ✓ | ≥10 | — |
| PySide6 / Qt6 | All GUI widgets | ✓ | 6.7+ | — |
| `kha-white/manga-ocr-base` model | OCR inference | ✓ (cached) / first-run download ~450MB | HF cache | First run shows "Loading OCR model…" progress; no offline fallback (OCR requires the model). |
| Japanese IME (OS) | Inline editor Japanese input (TEXT-04) | ✓ (Windows, user has JP IME per workflow) | OS-provided | — (verify at end-of-phase human gate) |

**Missing dependencies with no fallback:** none — all Phase 4 dependencies are already installed (the `[torch]` extra has been used since Phase 1).

**Missing dependencies with fallback:** the `kha-white/manga-ocr-base` model is downloaded on first OCR run (~450MB into the HF cache). No offline fallback — OCR requires the model. The first-run UX (indeterminate "Loading OCR model…" progress) is the mitigation, not a fallback.

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`. This section covers Dimension 8.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-qt + pytest-mock (PySide6 via `qt_api = pyside6` in pytest.ini) |
| Config file | `pytest.ini` (testpaths=tests, markers `unit`/`gui`) |
| Quick run command | `pytest tests/test_core/ -m unit -x -q` (headless, no Qt) |
| Full suite command | `pytest tests/ -q` (includes gui tests requiring display) |

**Existing test tree (19 files):** `tests/test_core/` (headless: adapters, box_model, history_boxes, config, structures, image_io, masker, batch_runner), `tests/test_detection/`, `tests/test_inpainting/`, `tests/test_mask_editor/`, `tests/test_gui_*.py` (pytest-qt). The conftest at `tests/conftest.py` + `tests/test_core/conftest.py` provide fixtures.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEXT-02 | `TorchOCRModel.recognize(numpy) → str` (numpy→PIL→manga-ocr) | unit | `pytest tests/test_core/test_ocr_adapter.py -x` | ❌ Wave 0 |
| TEXT-02 | `backend_factory("ocr", "torch")` returns TorchOCRModel (no longer NotImplementedError) | unit | `pytest tests/test_core/test_adapters.py::test_ocr_factory -x` | ❌ Wave 0 (extend existing file) |
| TEXT-02 | OCR worker task crops region + returns str (mocked model) | unit | `pytest tests/test_core/test_ocr_worker.py -x` | ❌ Wave 0 |
| TEXT-02 | Auto-OCR appended to `_commit_create` (box arrives with text) | gui | `pytest tests/test_gui_boxes.py::test_create_box_runs_ocr -x` | ❌ Wave 0 (extend existing file) |
| TEXT-04 | Double-click opens inline editor; Enter commits; Esc cancels | gui | `pytest tests/test_gui_boxes.py::test_inline_editor_commit_cancel -x` | ❌ Wave 0 |
| TEXT-04 | Inline editor edits translation when present, else recognized (D-08 focus rule) | gui | `pytest tests/test_gui_boxes.py::test_inline_editor_focus_rule -x` | ❌ Wave 0 |
| TEXT-04 | `edited` flag set on commit, cleared on OCR; re-OCR confirms when edited (D-04) | unit + gui | `pytest tests/test_core/test_box_model.py::test_edited_flag -x` and `pytest tests/test_gui_boxes.py::test_reocr_confirm_gate -x` | ❌ Wave 0 |
| TEXT-05 | `PageBox.set_translation(str)` writes `payload.translation` (MT seam) | unit | `pytest tests/test_core/test_box_model.py::test_set_translation -x` | ❌ Wave 0 (extend existing file) |
| TEXT-05 | Translation parser: `[N]: text` matched; SFX skipped; unmatched reported | unit | `pytest tests/test_core/test_translation_parser.py -x` | ❌ Wave 0 |
| TEXT-05 | Reading order: XY-Cut RTL/TB + LTR/TB + manual override preserved | unit | `pytest tests/test_core/test_reading_order.py -x` | ❌ Wave 0 |
| TEXT-05 | Bubble-number badge + text overlay render on BoxItem | gui | `pytest tests/test_gui_boxes.py::test_text_overlay_and_badge -x` | ❌ Wave 0 |
| Cross | `boxes_snapshot()` carries edited/bubble_no/override (Pitfall 1 regression) | unit | `pytest tests/test_core/test_history_boxes.py::test_snapshot_carries_phase4_fields -x` | ❌ Wave 0 (extend existing file) |
| Cross | Undo of text edit restores previous text (Pitfall 8 — payload aliasing) | unit | `pytest tests/test_core/test_history_boxes.py::test_text_edit_undo -x` | ❌ Wave 0 |
| Cross | Page-switch round-trip persists text/translation/bubble_no | gui | `pytest tests/test_box_persistence.py::test_text_persists_across_page_switch -x` | ❌ Wave 0 (extend existing file) |
| Cross | Toggle Text Overlay (`T`) independent of mask (`M`) / box (`Shift+M`) | gui | `pytest tests/test_gui_canvas.py::test_text_overlay_toggle -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_core/ -m unit -x -q` (fast headless feedback on the pure-Python modules: adapter, parser, reading-order, box-model).
- **Per wave merge:** `pytest tests/ -q` (full suite including gui tests).
- **Phase gate:** Full suite green before `/gsd:verify-work`. Plus the end-of-phase human-verify gate (config `human_verify_mode: end-of-phase`) must confirm: real Japanese IME input in the inline editor, vertical-toggle no-op behavior, OCR on a real manga page.

### Wave 0 Gaps
- [ ] `tests/test_core/test_ocr_adapter.py` — covers TEXT-02 (`TorchOCRModel` numpy→PIL→str, factory resolution, model-path validation).
- [ ] `tests/test_core/test_ocr_worker.py` — covers TEXT-02 (region crop + Worker dispatch, mocked model).
- [ ] `tests/test_core/test_translation_parser.py` — covers TEXT-05 (regex parse, SFX skip, match-by-bubble-no, unmatched report).
- [ ] `tests/test_core/test_reading_order.py` — covers TEXT-05 (XY-Cut RTL/LTR, manual override preserved).
- [ ] Extend `tests/test_core/test_box_model.py` — covers TEXT-04/05 (`set_translation`, `edited` flag, `bubble_no`/`override` fields).
- [ ] Extend `tests/test_core/test_adapters.py` — covers TEXT-02 (`backend_factory("ocr")` returns TorchOCRModel).
- [ ] Extend `tests/test_core/test_history_boxes.py` — covers Pitfall 1/8 (snapshot carries Phase 4 fields; text-edit undo).
- [ ] Extend `tests/test_gui_boxes.py` — covers TEXT-02/04/05 GUI behaviors (auto-OCR on create, inline editor, focus rule, D-04 gate, overlay+badge rendering).
- [ ] Extend `tests/test_box_persistence.py` — covers Pitfall 1 (text/translation/bubble_no persist across page switch).
- [ ] Extend `tests/test_gui_canvas.py` — covers D-12 (Toggle Text Overlay `T` independent of `M`/`Shift+M`).
- [ ] Framework: no new framework install needed (pytest/pytest-qt/pytest-mock already in `[dev]` extra).

*(If no gaps: "None" — but Phase 4 introduces 4 new modules + extends 5 existing test files, so Wave 0 has real work.)*

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1` in `.planning/config.json`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a — local desktop app, no auth. |
| V3 Session Management | no | n/a — no sessions. |
| V4 Access Control | no | n/a — single-user desktop. |
| V5 Input Validation | **yes** | The translation parser ingests untrusted text (pasted/imported). Regex must be strict (`^\[(\d+)\]:\s*(.*)$`); malformed lines are skipped + reported, never crash. The bubble-number `QSpinBox` is range-bounded. OCR output (model-generated str) is treated as untrusted display data (it's rendered via Qt's text engine, which escapes by default — no HTML injection unless rich text is explicitly enabled; keep the overlay plain-text). |
| V6 Cryptography | no | n/a — no crypto. |
| V7 Error Handling | **yes** | OCR model-load errors / file-import errors go to loguru (traceback) + user-friendly dialog (T-01-08 pattern). Parser errors are reported, not raised. No bare `except Exception: pass`. |
| V8 Data Protection | no | n/a — no sensitive data at rest (Phase 4 is in-memory; `.mas` save is Phase 5). |
| V12 Files & Resources | **yes** | File-import (`Load Translations From File`) reads a user-selected `.txt`. Use the existing Phase 1 file-read pattern (`np.fromfile`/`open(..., "r", encoding="utf-8")`); handle `OSError`/`UnicodeDecodeError` with the "Couldn't read '{filename}'" UX. Path traversal is not a concern (user-selected via `QFileDialog`, not a programmatic path). |

### Known Threat Patterns for the Qt6 + OCR stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed parser input (oversized paste, weird unicode) | Denial of Service | Line-by-line parsing with a max-line-length guard; skip + report unparseable lines (do not crash). The parser is pure Python over a small string — low DoS surface. |
| OCR model file tampering (swapped `kha-white/manga-ocr-base` in cache) | Tampering / Elevation | manga-ocr resolves from the HF cache; HF uses content-addressed blobs (SHA256). The Phase 1 T-01-04 model-weight-tampering mitigation applies (validate path exists before load; HF integrity is upstream). Low risk for a local single-user tool. |
| HTML/script injection via OCR text | Tampering | Render overlay text as PLAIN text (`QTextCharFormat` on a plain document; do NOT enable `Qt.TextRichText`/`setHtml` on the overlay). OCR output is model-generated and untrusted. The inline `QTextEdit` is user-editable plain text by default. |
| Resource exhaustion (450MB model download loop) | Denial of Service | Cache-check before download (CR-11 pattern); do NOT re-download on every session. The `_resolve_ocr_model_path` short-circuits when `is_ocr_downloaded()` is true. |

## Sources

### Primary (HIGH confidence)
- **Codebase (direct grep/read):** `manga_ai_studio/adapters/{base,factory,torch_impl}.py`, `core/{box_model,history_manager,image_file}.py`, `gui/{canvas,box_item,main_window,worker_thread}.py` — the existing seams Phase 4 fills. `[VERIFIED]`
- **`../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py`** — the `MangaOcr` singleton vendor reference (43 lines, GPL v3). `[VERIFIED]`
- **`../PanelCleaner/pcleaner/model_downloader.py:251-268`** — `get_ocr_model_directory` / `is_ocr_downloaded` / `OCR_DIR_NAME`. `[VERIFIED]`
- **`../PanelCleaner/pcleaner/comic_text_detector/utils/textblock.py:15-68,203-206`** — `TextBlock` slots (`.text`/`.translation`/`.vertical`/`.language`) + `get_text()`. `[VERIFIED]`
- **`manga_ocr/ocr.py` (installed package)** — `MangaOcr.__init__`/`__call__` contract (accepts `str|Path|PIL.Image`, returns post-processed str). `[VERIFIED]`
- **PyPI registry** — `pip index versions manga-ocr` (0.1.16) / `pip index versions transformers` (5.14.1). `[VERIFIED]`

### Secondary (MEDIUM confidence)
- **Qt Forum: outline on a QGraphicsTextItem** (forum.qt.io/topic/1302) — `QTextCharFormat.setTextOutline(QPen)` is the solved outlined-text technique. `[CITED]`
- **OpenDataLoader: Reading Order & XY-Cut++** (opendataloader.org/docs/reading-order) — column-detection via X-axis whitespace gaps + per-column top-to-bottom sort. `[CITED]`
- **Qt Forum / QtCentre: vertical text in QTextEdit/QTextDocument** (forum.qt.io/topic/105181, qtcentre.org/threads/11231, qtcentre.org/threads/19024) — Qt does NOT implement CSS `writing-mode: vertical-rl`; true CJK vertical needs custom layout. `[CITED]`
- **Stack Overflow / Qt Forum: QGraphicsProxyWidget focus quirks** (stackoverflow.com/questions/46081929, forum.qt.io/topic/144859) — embedded QTextEdit focus/IME forwarding caveats. `[CITED]`
- **KDAB: Qt Input Method In Depth** (kdab.com/qt-input-method-depth) — `QInputMethod`/`inputMethodEvent` background for IME handling. `[CITED]`

### Tertiary (LOW confidence)
- Kovanen & Aizawa "A Layered Method for Determining Manga Text Bubble Reading Order" (semanticscholar.org) — academic reference for a learned reading-order approach; NOT used in v1 (XY-Cut is simpler and sufficient), but confirms RTL manga reading order is a studied problem. `[ASSUMED — not needed for v1]`

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — manga-ocr/transformers verified on PyPI + in dev env; all widgets are inherited Qt6 standards; PanelCleaner vendor ref read in full.
- Architecture: **HIGH** — every pattern (adapter, worker, overlay, parser, reading-order) has a verified codebase or vendor reference; the integration seams (`backend_factory("ocr")`, `_commit_create`, `boxes_snapshot`, BOXES stack) are all confirmed in the existing code.
- Pitfalls: **HIGH** — Pitfall 1 (snapshot field gap) and Pitfall 8 (payload aliasing) are confirmed by reading the actual snapshot code; Pitfall 5 (vertical text) is confirmed via Qt forums; Pitfalls 2/3/4/6/7 are verified from the manga_ocr source, the worker pattern, D-04, and the UI-SPEC z-order.
- Vertical editing: **HIGH confidence that it is NOT feasible in v1** — multiple corroborating Qt sources.

**Research date:** 2026-08-05
**Valid until:** 2026-09-05 (30 days — stable; Qt6/manga-ocr/transformers are mature, no fast-moving deps)

---

*Phase: 4-OCR Recognition & Text Editing*
*Research completed: 2026-08-05*
*Design-system baseline: `01-cleaning-workspace/01-UI-SPEC.md` + `03-text-box-detection-interaction/03-UI-SPEC.md` + `04-ocr-recognition-text-editing/04-UI-SPEC.md` (all approved)*

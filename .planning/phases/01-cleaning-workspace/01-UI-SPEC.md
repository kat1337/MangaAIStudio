---
phase: 1
slug: cleaning-workspace
status: draft
shadcn_initialized: false
preset: none
created: 2026-07-12
---

# Phase 1 — UI Design Contract (Cleaning Workspace)

> Visual and interaction contract for the Phase 1 Cleaning Workspace. Generated
> by gsd-ui-researcher, verified by gsd-ui-checker.
>
> **CRITICAL CONTEXT — this is a PySide6 / Qt6 DESKTOP application, not a web
> app.** The web-flavored template sections below are adapted to Qt semantics:
> "spacing scale" → Qt widget margins / layout spacing; "typography" → Qt font
> stacks; "color" → a dark QPalette / QSS palette; "interaction states" → Qt
> hover/pressed/focus/disabled on widgets + canvas tool states. Design tokens
> here are the source of truth for the executor.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (not applicable — shadcn gate is for React/Next/Vite web apps; this is a Qt6 desktop app) |
| Preset | not applicable |
| Component library | **PySide6 6.7+** (Qt6 official LGPL binding) — `QMainWindow`, `QGraphicsView`/`QGraphicsScene`, `QDockWidget`, `QToolBar`, `QListWidget`, `QSlider`/`QSpinBox`, `QProgressBar`, `QMessageBox` |
| Widget style | **`QApplication.setStyle("Fusion")`** — cross-platform consistent rendering (adopted from PanelCleaner `mainwindow_driver.py:209`); overrides platform native to guarantee the dark palette renders identically on Windows and (later) Linux |
| Icon library | `QStyle.StandardPixmap` for common actions (Open, Undo, Redo, Zoom) + bundled custom SVG set for the four mask tools (brush, rectangle, lasso, eraser) + freedesktop theme icons (`QIcon.fromTheme`) as fallback where present. **Rationale:** Windows does not ship a freedesktop icon theme, so we cannot rely on `fromTheme` alone (PanelCleaner does, but targets Linux). |
| Font (UI) | `"Segoe UI", "Arial", "Liberation Sans", sans-serif` — Segoe UI is the Windows UI font (Windows-first per CLAUDE.md); Liberation Sans is bundled for canvas overlay text (PanelCleaner pattern, `image_viewer.py:306`) and metric-compatible with Arial on Linux |
| Font (mono) | `"Consolas", "Cascadia Mono", "Liberation Mono", monospace` — status bar coordinates/zoom, log surfaces |
| Theme | **Dark, low-distraction "darkroom" image-editor aesthetic.** Locked by this contract (CONTEXT.md D-10 "Claude's Discretion: Color scheme/theme"; critical_framing mandates dark image-editor look). Dark is the convention for image editors (Photoshop/Krita/GIMP) — it reduces eye strain and makes the manga artwork on the canvas the visual focus. Rationale recorded; do not re-litigate. |

**Adaptation policy honored (D-12):** PanelCleaner GUI source is reference for layout/menus/shortcuts; the mask-editing canvas is our **own reimplementation patterned after MangaCleaner_GPU** (reference-only, not vendored). Concrete tokens below are grounded in both sources:
- PanelCleaner `image_viewer.py`: zoom factor `1.25`, `Ctrl`+wheel zoom, `Shift`+wheel horizontal, `AnchorUnderMouse`, `update_smoothing` (no smoothing >1x), `QImageReader.setAllocationLimit(0)`.
- MangaCleaner_GPU `frontend/canvas.py` + `main_window.py`: canvas matte `#0b0b0e`, mask paint `rgba(255,0,0,~0.63)`, eraser/cyan cursor `#00d4ff`, brush default 40px (range 1–300), tool shortcuts B/R/L, mask-vs-image undo (Alt+Z vs Ctrl+Z).

---

## Spacing Scale

Qt spacing is applied via layout `setSpacing()`, `setContentsMargins()`, dock widget margins, and toolbar icon padding. All values multiples of 4.

| Token | Value | Qt usage |
|-------|-------|----------|
| xs | 4px | Icon↔label gap inside a tool button; slider↔spinbox gap; row internal padding |
| sm | 8px | Compact element spacing; sidebar row padding; toolbar group internal padding |
| md | 16px | Default element spacing; dock contents margins; toolbar section gap |
| lg | 24px | Dialog section padding; major toolbar group separation |
| xl | 32px | Layout gaps (e.g., empty-state stack spacing) |
| 2xl | 48px | Empty-state outer padding from canvas center |
| 3xl | 64px | (Reserved — not used in Phase 1) |

**Exceptions (non-spacing values, declared here so they are not "invented" later):**
- Brush cursor outline pen: **1px** (`QPen(color, 1)`).
- Mask overlay alpha: **0.63** (≈160/255) — semantic, not spacing.
- Sidebar thumbnail: **64×64px** (aspect-preserved, letterboxed) — fixed asset size, on the 4-grid.
- Sidebar row height: **80px** (64 thumb + 8+8 vertical padding).
- Thin progress bar height: **3px** (async-op indicator).
- Selected sidebar row accent border: **2px** left.

---

## Typography

Four sizes, two weights (regular + semibold). Qt sizes are specified in **pixels**; the executor applies them via `QFont.setPointSizeF()` or `setPixelSize()` (1px ≈ 0.75pt at 96 DPI on Windows).

| Role | Size | Weight | Line Height | Qt usage |
|------|------|--------|-------------|----------|
| Body | 14px | Regular (400) | 1.5 | Sidebar filenames, status bar messages, dialog body, tooltips |
| Small / Label | 12px | Regular (400) | 1.4 | Toolbar/panel labels ("Brush size: 40 px"), slider labels, metadata (page dims), menu bar |
| Mono / Status | 12px | Regular (400) | 1.4 | Status bar coordinates (`x, y`) and zoom %; log viewer (Consolas) |
| Heading | 16px | Semibold (600) | 1.3 | Empty-state heading, dialog section headers, About |

**Notes:**
- Display/hero sizes are NOT used — this is a tool, not a marketing surface. Window-title text is OS-controlled (native title bar).
- Canvas overlay text (none in Phase 1; reserved for Phase 3 box labels) would use the bundled Liberation Sans at a zoom-scaled size per PanelCleaner's `image_viewer.py:437` formula — deferred, not contracted here.

---

## Color

Dark QPalette / QSS palette. Dominant/secondary/accent follow a 60/30/10 split. The mask overlay red and the eraser/selection cyan are **semantic surface colors**, not part of the 60/30/10 — they are declared separately so "accent" is not overloaded.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#232328` | Main-window chrome background (everything behind the docks/toolbar) |
| Canvas matte | `#0b0b0e` | `QGraphicsView` viewport background (the darkroom matte behind the image). Darker than chrome so the artwork is the sole bright surface. (From MangaCleaner_GPU `canvas.py:21`.) |
| Secondary (30%) | `#2d2d33` | Dock/sidebar/toolbar/tool-panel raised surfaces; sidebar rows; dialog panels |
| Divider | `#3a3a42` | 1px borders between chrome regions; `QDockWidget` separators; toolbar separators |
| Accent (10%) | `#00d4ff` (cyan) | **See reserved-for list below** |
| Mask overlay (semantic) | `rgba(255, 0, 0, 0.63)` | Mask paint content — brush/rectangle/lasso fill. Means "region to be inpainted". NOT an accent, NOT configurable in Phase 1. (From MangaCleaner_GPU `canvas.py:129`.) |
| Brush cursor (paint) | `rgba(255, 0, 0, 0.78)` pen / `rgba(255, 0, 0, 0.24)` fill | Brush-size outline circle when painting mask |
| Eraser cursor / lasso+rect preview | `rgba(0, 212, 255, 0.78)` pen / `rgba(0, 212, 255, 0.24)` fill | Brush outline when erasing; dashed rectangle/lasso preview while dragging (cyan dashed) |
| Text primary | `#e8e8ea` | Body/label text on all dark surfaces |
| Text muted | `#9a9aa2` | Secondary metadata, disabled labels, empty-state hint |
| Destructive action | `#c0392b` | Destructive button accent only ("Clear Mask") |
| Error banner | `#7a1f1f` bg / `#ffffff` text | Fatal-error chip in status bar + critical dialog framing (mirrors PanelCleaner OOM banner `#550000` at `mainwindow_driver.py:2417`, slightly lightened) |

**Accent (`#00d4ff`) reserved for — and ONLY for:**
1. Active tool button highlight (the currently-selected mask tool)
2. Selected page row in the sidebar (bg tint `rgba(0,212,255,0.18)` + 2px left border)
3. Keyboard focus outline (`:focus` / `focus-visible` on widgets)
4. Progress-bar fill (determinate + indeterminate)
5. The "running" state indicator on Detect Text / Inpaint (button spinner)
6. The "Eraser" mode label color while erasing

Accent is NEVER used for: body text, borders/dividers, mask content (that is semantic red), or window chrome. This keeps the artwork as the only saturated bright surface on the canvas.

**Why no light theme:** a dark canvas surround prevents the eye from adapting to bright chrome and misjudging mask colors and tonal values in the artwork — the same reason darkroom and photo editors are dark. Pinning it here avoids per-widget inconsistency later. (Executor: apply via a single `QPalette` assignment at startup, not per-widget QSS.)

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA — detect | **"Detect Text"** (verb + noun). Tooltip: "Run text detection on the current page (D)." |
| Primary CTA — inpaint | **"Inpaint"** (verb). Tooltip: "Remove text in masked regions using LaMa (C)." |
| Primary CTA — open | **"Open Image…"** / **"Open Folder…"** (File menu). |
| Empty state heading | **"No page open"** |
| Empty state body | **"Open a single image or a folder of images to begin cleaning."** |
| Empty state hint (accent) | **"File → Open Image…  (Ctrl+O)   ·   or drag files here"** |
| Sidebar empty | **"No pages loaded — open a folder (Ctrl+Shift+O)."** |
| Error — model load | **"Couldn't load the {detection \| inpainting} model."** + path: "Check that the model files exist in the `models/` folder and see the log for details." |
| Error — file unreadable | **"Couldn't open '{filename}'."** + path: "The file may be corrupt or in an unsupported format." |
| Error — backend crash (D-08 IPC) | **"The processing backend stopped unexpectedly."** + path: "See the log for details. You can retry or restart the application." Buttons: [Retry] [Close]. |
| Status — detecting | **"Detecting text… {percent}%"** |
| Status — inpainting | **"Inpainting… {percent}%"** |
| Status — model loading | **"Loading {model} model…"** (indeterminate) |
| Destructive — Clear Mask | Action: **"Clear Mask"**. Confirmation: **"Clear the entire mask on this page? You can undo with mask undo (Alt+Z)."** Buttons: [Cancel] [Clear Mask]. |
| Destructive — re-detect over existing mask | Action: **"Detect Text"** (when a mask already exists). Confirmation: **"Replace the current mask with a new detection? Your manual edits will be lost — undo is available via mask undo (Alt+Z)."** Buttons: [Cancel] [Replace Mask]. |

**Inpaint is NOT destructive** (it modifies the image layer but is fully reversible via image undo Ctrl+Z) — no confirmation dialog. The mask is intentionally left visible after inpaint so the user sees what was processed; they clear or toggle it explicitly.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable (Qt desktop app; shadcn gate does not apply) |
| PySide6 / Qt6 | vendored via pip (LGPL) | approved — upstream Qt, LGPL |
| PanelCleaner `pcleaner/` source | config.py, image_viewer.py, file_table.py, comic_text_detector, inpainting.py (adapted near-verbatim) | GPL v3 derivative copying, license-compatible — D-12 |
| MangaCleaner_GPU `frontend/canvas.py` + `main_window.py` | **none — reference only** | BLOCKED from vendoring by D-12 (binary distribution carries no LICENSE → all-rights-reserved). Read for patterns; reimplement. |

No third-party UI component registries. No `npx shadcn` operations. Safety gate satisfied by policy (D-12), not by a `shadcn view` step.

---

## Interaction & Surface Contracts (Phase 1 — the 9 surfaces)

> These are the concrete contracts the planner/executor implement. Each surface
> maps to ROADMAP Phase 1 success criteria and requirement IDs.

### 1. Main-window shell  ·  (`gui/main_window.py`)

- **Type:** `QMainWindow`, Fusion style, dark `QPalette` applied once at startup.
- **Layout:**
  - Central widget: `EditorCanvas` (`QGraphicsView`) — surface 2.
  - `QDockWidget` "Pages" → `LeftDockWidgetArea` — surface 3.
  - `QDockWidget` "Tools" → `RightDockWidgetArea` — surface 6.
  - Docks are user-movable/closable; default layout restored on launch.
- **Menu bar:**
  - **File:** Open Image… `Ctrl+O` · Open Folder… `Ctrl+Shift+O` · Recent Files ▸ (max 8) · — · Quit `Ctrl+Q`
  - **Edit:** Undo Image `Ctrl+Z` · Redo Image `Ctrl+Shift+Z` · Undo Mask `Alt+Z` · Redo Mask `Alt+Shift+Z` · — · Clear Mask… (destructive)
  - **View:** Fit to Window `Ctrl+0` · Actual Size `Ctrl+1` · Zoom In `Ctrl++` · Zoom Out `Ctrl+-` · — · Toggle Mask Overlay `M` · Show Original (Preview) `P` · — · Toggle Sidebar · Toggle Tools
  - **Tools:** Detect Text `D` · Inpaint `C` · — · Move/Pan `V` · Brush `B` · Rectangle `R` · Lasso `L` · Eraser `E`
  - **Help:** About
- **Toolbar (single, top):** `Open` | `Detect Text` | `Inpaint`  ‖  `Move` `Brush` `Rectangle` `Lasso` `Eraser`  ‖  `Undo Image` `Redo Image` `Undo Mask` `Redo Mask`  ‖  `Fit` `100%` `Zoom Out` `Zoom In`  ‖  `Toggle Mask Overlay`. Sections separated by `addSeparator()`. Icon-only except `Brush size:` slider+spin (surface 6).
- **Status bar (3 fields):**
  - Left: current operation / status message (e.g., "Detecting text… 42%").
  - Center: cursor image coordinates `{x}, {y}` (mono) + zoom `{percent}%`.
  - Right: page progress `Page {n} / {total}`.
- **Window title:** `"Manga AI Studio — {filename}"` when a page is open, else `"Manga AI Studio"`. No version in title bar (version lives in Help → About).
- **Sizes:** minimum usable **1024×720**; default/initial **1440×900**; maximize on first run if the screen allows. Window geometry restored via `QSettings` on next launch (optional Phase 1 nicety; not a requirement).

### 2. Image canvas  ·  CLEAN-01  ·  (`gui/canvas.py`, ours per D-12)

- **Type:** `QGraphicsView` + `QGraphicsScene`. Scene items stacked bottom→top: image `QGraphicsPixmapItem` → mask `QGraphicsPixmapItem` → cursor/preview overlay items. (Pattern from MangaCleaner_GPU `canvas.py`; PanelCleaner `image_viewer.py` supplies the pan/zoom mechanics.)
- **Pan:** middle-mouse drag ·OR· hold `Space` + left-drag ·OR· scrollbars (default wheel = vertical pan).
- **Zoom:**
  - `Ctrl`+wheel = zoom (half-step, factor `√1.25`); `Ctrl++` / `Ctrl+-` = full step (factor `1.25` / `1/1.25`); `Ctrl+0` = Fit to Window; `Ctrl+1` = 100%.
  - Clamp: max **100×**; min = half the viewport (PanelCleaner `image_viewer.py:232-247`).
  - `AnchorUnderMouse` (zoom toward cursor).
  - `update_smoothing()`: pixel-accurate (no `SmoothPixmapTransform`) when zoom >1×, smooth when ≤1× (PanelCleaner `image_viewer.py:116`).
- **Scrollbars:** `ScrollBarAsNeeded`.
- **Background:** viewport matte `#0b0b0e` (canvas matte token). Solid in v1 — manga pages are opaque. Checkerboard transparency indicator deferred (PNGs with alpha are edge-case; not a Phase 1 requirement).
- **Large-image safety:** `QImageReader.setAllocationLimit(0)` (PanelCleaner `image_viewer.py:45`) — prevents load failure on 3000×4000+ pages.

### 3. File-list sidebar  ·  FLOW-01, CLEAN-01  ·  (`gui/file_table.py`)

- **Type:** `QListView` in `ListMode`, single column, vertical. (PanelCleaner uses a `QTableWidget`; we use a simpler list — Phase 1 needs navigation, not analytics columns.)
- **Row:** 80px tall — 64×64 thumbnail (aspect-preserved, letterboxed on `#2d2d33`) + filename + 1-indexed page number (muted).
- **Sort:** natural-sort by filename (`page1, page2, … page10`), header shows count.
- **Current page:** row bg `rgba(0,212,255,0.18)` + 2px accent left border.
- **Interactions:**
  - Single-click row → load that page into the canvas.
  - Double-click row → load + Fit to Window.
  - Keyboard: `Up`/`Down` move selection, `Enter`/`Return` load selected.
- **Drag-drop:** dropping image files loads them as the page list; dropping a folder loads the folder (flat, non-recursive by default).
- **Empty:** sidebar placeholder text "No pages loaded — open a folder (Ctrl+Shift+O)."

### 4. Open workflow  ·  CLEAN-01

- **Open Image (`Ctrl+O`):** file dialog, filter `*.png *.jpg *.jpeg *.webp *.bmp`, single-select.
- **Open Folder (`Ctrl+Shift+O`):** directory dialog; loads all supported images in the folder (flat, non-recursive). Recursive open is a v2 candidate, not in scope.
- **Recent Files:** submenu, last 8 (paths via `QSettings`). Selecting opens.
- **Drag-drop onto the window:** images → page list; folder → folder load.

### 5. Text detection surface  ·  CLEAN-02

- **Action:** Tools → Detect Text (`D`); toolbar button. Disabled until a page is open and no other async op is running.
- **Async:** `QThread` worker in the frontend env dispatching to the backend (`torch_env`) subprocess per D-07/D-08. **Non-blocking** — UI stays responsive.
- **Progress feedback (non-modal):** status-bar left message "Detecting text… {percent}%"; thin 3px determinate `QProgressBar` directly under the toolbar; the Detect button enters spinner/disabled state. No modal dialog. (Pitfall: never run model inference on the GUI thread — RESEARCH Pitfall 3.)
- **Result display:** the auto-generated mask is composited into the **mask layer** using the Mask overlay color `rgba(255,0,0,0.63)`. The mask overlay is visible by default after detection.
- **Existing mask:** if a mask is already present, show the "Replace Mask" destructive confirmation (see Copywriting) before overwriting.

### 6. Mask-editing tool panel  ·  CLEAN-03/04/05  ·  (`gui/tools_panel.py` + `gui/canvas.py`, ours per D-12)

- **Type:** `QDockWidget` "Tools" (Right).
- **Tool selection:** 5 exclusive icon buttons (`QActionGroup`) — **Move/Pan · Brush · Rectangle · Lasso · Eraser**. Active tool highlighted with accent (`#00d4ff`) — the accent's reserved use #1.
- **Brush size:** `QSlider` (1–300 px) + `QSpinBox` (1–300) side by side, label **"Brush size: {n} px"**. Default **40 px** (MangaCleaner_GPU default). Affects Brush + Eraser. Spacing: slider↔spinbox gap = `xs` (4px).
- **Tools (exact behavior):**
  - **Brush (`B`):** paint mask with a round stroke (`Qt.RoundCap`, `Qt.RoundJoin`), width = brush size. Mask color fixed `rgba(255,0,0,0.63)`.
  - **Rectangle (`R`):** click-drag to define a rectangle; dashed cyan preview while dragging; on release, fill the rectangle into the mask.
  - **Lasso (`L`):** click-drag freehand path; dashed cyan preview follows the path; on release, close + fill the path into the mask.
  - **Eraser (`E`):** removes mask via `QPainter.CompositionMode_Clear`. Same brush-size control. Shortcut `E`. (Distinct from MangaCleaner_GPU's `Shift`-toggle — we expose `E` as a first-class tool and keep `Shift` as a modifier toggle for power users.)
  - **Move/Pan (`V`, and hold `Space`):** no painting; cursor = `OpenHandCursor` (→ `ClosedHandCursor` while dragging).
- **Cursor feedback:**
  - Brush/Eraser: a brush-size outline circle follows the cursor. **Paint mode** → red outline `rgba(255,0,0,0.78)` + faint red fill. **Eraser mode** → cyan outline `rgba(0,212,255,0.78)` + faint cyan fill. (From MangaCleaner_GPU `canvas.py:55-60`.)
  - Rectangle/Lasso: `CrossCursor` + dashed cyan preview of the in-progress shape.
  - Move: `OpenHandCursor`/`ClosedHandCursor`.
- **Modifier:** holding `Shift` temporarily toggles Brush↔Eraser (documented in tooltip; matches MangaCleaner_GPU).
- **Mask paint color is fixed** (semantic, not user-configurable in Phase 1).

### 7. LaMa inpainting surface  ·  CLEAN-06

- **Action:** Tools → Inpaint (`C`); toolbar button. Disabled if no mask is present, no page is open, or another async op is running.
- **Async:** `QThread` worker → backend (`torch_env`) per D-08. Non-blocking. Models can take seconds to tens of seconds.
- **Progress feedback (non-modal):** status-bar "Inpainting… {percent}%"; thin 3px progress bar; Inpaint button spinner/disabled.
- **Result display:** the inpainted result **replaces the image layer** (masked region is restored with LaMa output). The mask overlay is intentionally left visible so the user sees what was processed; they clear it (Edit → Clear Mask) or toggle it off.
- **Preview toggle (before/after compare):**
  - **Hold-to-preview** button "Preview (hold)" in the toolbar — press and hold to show the **original** (pre-inpaint) image; release to return to the inpainted result. (Lightroom/Photoshop convention.)
  - **Sticky toggle:** View → Show Original (`P`) — toggles a persistent preview of the original. Press `P` again (or release the hold button) to return to the result.

### 8. Undo/redo surface  ·  FLOW-02  ·  (`core/history_manager.py`)

- **Two separate stacks** (RESEARCH: MangaCleaner_GPU uses 4; Phase 1 contracts 2): a **MASK** stack (painting ops) and an **IMAGE** stack (inpaint ops).
- **Shortcuts (grounded in MangaCleaner_GPU `main_window.py:168-171`):**

  | Action | Shortcut | Rationale |
  |--------|----------|-----------|
  | Undo Image | `Ctrl+Z` | `Ctrl+Z` is the universal "undo"; image (inpaint) is the primary undo target |
  | Redo Image | `Ctrl+Shift+Z` | Conventional redo pair to `Ctrl+Z` |
  | Undo Mask | `Alt+Z` | Mask edits get a distinct modifier so both stacks are reachable without a mode toggle |
  | Redo Mask | `Alt+Shift+Z` | Mirrors the mask-undo modifier |

- **Toolbar:** **two pairs** — `[Undo Image][Redo Image]` `‖` `[Undo Mask][Redo Mask]` — with tooltips showing the shortcut. (Chosen over a single pair with a mask/image mode toggle to avoid mode ambiguity — FLOW-02 requires both stacks to be independently reachable.)
- **Menu Edit:** lists all four with their shortcuts.
- **State:** each button disabled when its stack is empty; enabled otherwise.
- **Stack entry:** full `QImage`/mask snapshot per entry for simplicity in Phase 1 (RESEARCH Open Question 3 — optimize to incremental edits later only if needed).

### 9. Feedback states

- **Loading (detect / inpaint):** non-blocking. Status-bar message + determinate `%` + thin 3px progress bar + the action button in spinner/disabled state. Canvas is not blocked — the user may still pan/zoom, but cannot start a second model op.
- **Model-loading phase (indeterminate):** indeterminate progress bar + "Loading {model} model…" status (first run of each backend, lazy-load per RESEARCH).
- **Error — model load failure:** `QMessageBox::Critical` with the "model load" copy (Copywriting). Status bar shows a persistent `#7a1f1f` error chip until the next successful op or dismissal.
- **Error — file unreadable:** `QMessageBox::Warning` with the "file unreadable" copy.
- **Error — backend/subprocess crash (D-08 IPC):** `QMessageBox::Critical` with the "backend stopped" copy + `[Retry] [Close]` buttons.
- **Empty state (no page open):** centered on the canvas matte. Heading **"No page open"** (16px / 600 / muted) → body **"Open a single image or a folder of images to begin cleaning."** (14px / 400 / muted) → hint **"File → Open Image… (Ctrl+O) · or drag files here"** (12px / accent). Stack spacing `2xl` (48px) from canvas center.

---

## Keyboard Shortcut Reference (consolidated)

| Key | Action | Surface |
|-----|--------|---------|
| `Ctrl+O` | Open Image | 4 |
| `Ctrl+Shift+O` | Open Folder | 4 |
| `Ctrl+Q` | Quit | 1 |
| `Ctrl+Z` | Undo Image | 8 |
| `Ctrl+Shift+Z` | Redo Image | 8 |
| `Alt+Z` | Undo Mask | 8 |
| `Alt+Shift+Z` | Redo Mask | 8 |
| `Ctrl+0` | Fit to Window | 2 |
| `Ctrl+1` | Actual Size (100%) | 2 |
| `Ctrl++` / `Ctrl+-` | Zoom in / out | 2 |
| `Ctrl`+wheel | Zoom (half-step) | 2 |
| `Shift`+wheel | Horizontal scroll | 2 |
| `M` | Toggle Mask Overlay | 5/7 |
| `P` | Show Original (sticky preview) | 7 |
| `D` | Detect Text | 5 |
| `C` | Inpaint | 7 |
| `V` | Move/Pan tool | 6 |
| `B` | Brush tool | 6 |
| `R` | Rectangle tool | 6 |
| `L` | Lasso tool | 6 |
| `E` | Eraser tool | 6 |
| `Space` (hold) | Pan (temp) | 2/6 |
| `Shift` (hold, in Brush/Eraser) | Toggle Brush↔Eraser | 6 |
| `Up`/`Down`/`Enter` | Sidebar navigate | 3 |

---

## Accessibility & Platform Notes

- **Contrast:** text primary `#e8e8ea` on `#232328` (chrome) and on `#0b0b0e` (canvas) both exceed WCAG AA 4.5:1. Muted `#9a9aa2` on `#232328` ≈ 4.6:1 — use only for non-essential secondary text.
- **Focus:** every interactive widget shows a visible 2px `#00d4ff` focus outline (accent reserved use #3). Never remove focus indication.
- **Keyboard:** all actions reachable via the menu/shortcut table above; no mouse-only flows.
- **High-DPI:** Qt6 auto-high-DPI; the dark `QPalette` and pixel sizes are DPI-aware via `setPixelSize`. Re-test at 150%/200% Windows scaling.
- **Platform:** Windows-first for v1. No Windows-only APIs (CLAUDE.md constraint). Fusion style + QPalette guarantee the dark theme renders identically when Linux support lands later.
- **Cursor size:** brush cursor circle respects the brush-size slider; the system cursor itself is unchanged.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending

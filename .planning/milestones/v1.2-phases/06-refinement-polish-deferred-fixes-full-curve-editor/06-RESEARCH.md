# Phase 6: Refinement & Polish (deferred fixes + full curve editor) - Research

**Researched:** 2026-08-09
**Domain:** Qt/PySide6 desktop GUI polish + custom QPainter curve widget + numpy LUT math
**Confidence:** HIGH (all root causes and fix surfaces verified in-repo this session; greenfield curve math grounded in official docs + locked CONTEXT decisions)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Curves dialog structure**
- **D-01:** **A single "Curves…" dialog replaces the Levels dialog.** The Tools-menu "Levels…" action is removed and renamed "Curves…"; its Alt+T Image-section slot and placement stay. **The black/white point sliders are KEPT as a quick-access row above the curve grid** (user chose "Curve dialog + point sliders" over full replacement or two coexisting dialogs). — **Reversibility:** reversible.
- **D-02:** **Bidirectional slider↔curve sync; the curve is the single source of truth.** Dragging the black/white sliders moves the curve's left/right endpoints; dragging curve points updates the sliders. No state can diverge. — **Reversibility:** reversible.
- **D-03:** **Gamma slider kept, synced to the curve's midpoint anchor.** The log-scaled gamma control (0.10…4.00, default 1.00) stays; gamma 1.00 = midpoint sitting on the diagonal. Dragging the curve's midpoint updates the gamma slider in return. — **Reversibility:** reversible.

**Curve interaction model**
- **D-04:** **Arbitrary control points, Photoshop convention.** Click on the curve to add a point, drag to move it, double-click a point to delete it. The endpoints (0,0)/(255,255) are fixed — draggable only along their edge. — **Reversibility:** reversible.
- **D-05:** **Presets: Linear (reset) + a few one-click starting points** — S-curve (contrast), "Brighten", "Darken" — on a preset row/dropdown. Presets are fully editable after application (starting points, not locked templates). — **Reversibility:** reversible.
- **D-06:** **Master + per-channel (R/G/B) curves with a channel switcher.** The dialog edits the RGB master AND each channel independently; the preview composes the applied LUTs. — **Reversibility:** reversible.
- **D-07:** **Full keyboard story (app's keyboard-reachability contract):** numeric input/output spinboxes for the selected point (Photoshop convention) AND arrow-key nudge (1 unit, Shift = 10) with Tab/Shift+Tab point selection. — **Reversibility:** reversible.
- **D-08:** **Page luminance histogram behind the curve grid** — computed once from the detached page image at dialog open (cheap, `np.histogram`), rendered faintly behind the grid. — **Reversibility:** reversible.

**Deferred fixes (locked contracts — root cause and fix prescribed in Phase 5 docs)**
- **D-09:** **Empty-state overlay fix = call `self._update_empty_state()` at the end of `_set_image_from_numpy`** (`canvas.py:710-767`). Covers both the "No page open" trio AND the empty-box hint (`_update_empty_state` already refreshes `_refresh_empty_box_hint`, `canvas.py:1545-1575`). A regression test on the project-open path is required (the `set_image_from_path` path already works — the numpy display path is the bug site). — **Reversibility:** one-way (fix closes the only defect; behavior contract = empty state never persists over a loaded page).
- **D-10:** **Toolbar active-tool highlight = make the window tool actions checkable and add them to the ToolsPanel's exclusive `QActionGroup`** (the deferred-items.md prescription). The toolbar buttons must highlight in sync with the dock panel — including when the tool changes via keyboard shortcut (V/B/R/L/E/G), the Tools menu, or programmatic `set_active_tool`. Exact wiring (share the panel's actions vs duplicate checkable actions in the group) is Claude's discretion — the false comment at `main_window.py:3101-3103` must be corrected or made true. — **Reversibility:** reversible.
- **D-11:** **Empty-state hint copy must not advertise the wrong shortcut** (`canvas.py:278`). Ctrl+O is Open Project… — the hint must either drop the shortcut or reference Open Folder (Ctrl+Shift+O). Exact wording is Claude's discretion (the body text "Open a single image or a folder of images to begin cleaning." stays). — **Reversibility:** reversible.
- **D-12:** **Dialog field values/labels at contracted 14px Body** (05-UI-REVIEW Pillar 3). Which dialogs are in scope (the three Phase-5 image-op dialogs only vs all dialogs incl. the inherited LoadTranslationsDialog baseline) is Claude's discretion — the 14px Body contract row is the acceptance truth. — **Reversibility:** reversible.

### the agent's Discretion
- **Hint copy wording** (D-11) and **typography scope** (D-12) — user chose not to discuss the fix areas; the planner/researcher decide against the UI-SPEC contract.
- **Toolbar mechanism exact wiring** (D-10) — checkable-action duplication vs binding toolbar buttons to the panel's actions; either satisfies the sync contract.
- **Curve widget implementation** — a custom `QPainter`-drawn widget (grid, diagonal, curve path, histogram, channel switcher, preset row). Curve→LUT math: sample each curve at 256 points → per-channel LUTs; master and per-channel composition order (e.g. per-channel LUT applied after master, or multiplicative on the sampled values — pick the least-surprising Photoshop-equivalent). Extend `core/image_ops.py` (`levels_lut` is the existing LUT builder; T-05-07's normalize/backstop discipline applies — a degenerate curve must never render an inverted map).
- **Dialog lifecycle contract** — the Curves dialog follows the existing Levels collector+preview-driver contract (Pitfall 9): never mutates models, `preview_callback` drives the capture-suppressed canvas preview, Cancel = silent exact restore, Apply = ONE image-only IMAGE-stack undo entry via `_apply_geometry_op`, Show Original re-baselines post-op (05-UI-REVIEW-FIX b376f8a already fixed the restore-before-Apply ordering — the Curves Apply path MUST preserve it).
- **Preset curve math** (S-curve/Brighten/Darken shapes), **histogram computation detail**, **channel-switcher UI form** (buttons vs dropdown), **numeric in/out widget layout**.
- **Per-channel LUT edge cases** — per-channel curves are applied to each channel; the master applies to all. The T-05-07-style cross-clamp/backstop thinking applies to slider↔endpoint sync (endpoints fixed at the edges, sliders can't invert past them).

### Deferred Ideas (OUT OF SCOPE)
- **Typesetting styling toolbar (TRAN-02)** — explicitly out of Phase 6 scope (ROADMAP §Phase 6; Phase 7 owns it). Font/style/size/color/alignment/effects for rendered translation text.
- **Sibling-menu empty-state voice mismatch** ("No recent projects yet." vs "(empty)", 05-UI-REVIEW Minor) — not in ROADMAP Phase 6 scope; a one-word polish if the typography/copy pass (D-11/D-12) naturally touches the Recent menus, otherwise a future phase.
- **Per-channel curve presets / user-saved curves** — not requested; the preset row (D-05) is fixed and built-in only.
- **Curve serialization in `.mas`** — rejected by Phase 5 D-05 (image ops are not serialized; the post-op image is saved). The curve is a transient edit like Levels.
- **Levels no-op undo record** — ALREADY FIXED (05-UI-REVIEW-FIX.md, b376f8a). Listed here to prevent re-doing it.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROJ-04 | User can apply basic image operations to a page: crop, rotate, levels/curves adjustment, resize | "Curves" half lands here: CurvesDialog (D-01…D-08) + `curve_lut`/`curves_page` in `core/image_ops.py` + `_apply_geometry_op("curves", geometry=False, …)` — image-only, geometry-free (D-15), one IMAGE-stack undo entry, Show Original re-baseline (D-14). Levels already validated the PROJ-04 "levels" half in Phase 5. |
| (tracked deferrals, no REQ-IDs) | D-09 empty-state overlay persists after project open | Root cause verified: `_set_image_from_numpy` (canvas.py:710-767) never calls `_update_empty_state()`; `set_image`/`clear` do (canvas.py:383, 423). Fix = one line at end of `_set_image_from_numpy`; regression test on the `_display_page_state` project-open path (main_window.py:2292-2302). |
| (tracked deferrals, no REQ-IDs) | D-10 toolbar tool buttons never highlight active tool | Root cause verified: window tool actions (main_window.py:710-753) are non-checkable and outside the ToolsPanel exclusive `QActionGroup` (tools_panel.py:105-106); `set_active_tool`'s `btn.setChecked(True)` (main_window.py:3137) is a no-op on a non-checkable default action; false comment at `_make_tool_toolbar_button` (main_window.py:3109-3111). Fix = checkable + group membership (option 1) or bind buttons to panel actions (option 2). |
| (tracked deferrals, no REQ-IDs) | D-11 stale Ctrl+O hint copy | Verified: hint at canvas.py:277-279 renders "File → Open Image… (Ctrl+O) · or drag files here"; exactly one Ctrl+O binding exists — `action_open_project` (main_window.py:310-311); Open Folder binds Ctrl+Shift+O (main_window.py:305). |
| (tracked deferrals, no REQ-IDs) | D-12 dialog typography at Qt default ~12px, not contracted 14px Body | Verified: UI-SPEC row "Body | 14px | Regular (400) | 1.5 | Dialog field values, labels…" (05-UI-SPEC.md:86); LevelsDialog/ResizeDialog/CropDialog set no explicit fonts (read all three); LoadTranslationsDialog sets Consolas 10 only on the paste edit (load_translations_dialog.py:120); theme.py sets palette only, no font. |
</phase_requirements>

## Summary

Phase 6 delivers two work groups, both fully root-caused and locked in CONTEXT.md: four deferred-fix contracts (D-09…D-12, each with its defect site, prescription, and regression-test requirement) and the greenfield full curve editor (D-01…D-08, PROJ-04's "curves" half) that replaces the Levels dialog. This research verified every fix surface in-repo this session — the empty-state bug site (`_set_image_from_numpy`, canvas.py:710-767 — the only image display path missing the `_update_empty_state()` call), the toolbar no-op (`QToolButton.setChecked` on a non-checkable default action, main_window.py:710-753/3106-3138), the stale hint copy (canvas.py:278 verbatim), the missing 14px Body dialog typography (UI-SPEC 05-UI-SPEC.md:86), and the full Levels collector→preview→apply→undo lifecycle (`levels_dialog.py`, `_on_levels`, `_apply_geometry_op`, `levels_lut`) that the Curves dialog inherits wholesale — including the b376f8a restore-before-Apply ordering that MUST NOT regress.

The curve editor is a custom QPainter-drawn widget (grid + diagonal + draggable control points + faint histogram) driving pure-numpy LUT math in `core/image_ops.py` — zero new dependencies (PySide6 6.10.1 + numpy 2.3.5 already installed and verified). The photo-editor conventions are grounded in official docs (GIMP curves docs confirm: input/output 0..255 grid, fixed undelatable endpoints, click-add/drag-move points, per-channel + composite curves, numeric in/out spins, histogram as reference; Photopea confirms curves are a color-consistent LUT adjustment). Photoshop-specific details Adobe helpx could not be fetched for (exact preset coordinates, master∘channel composition order) are marked `[ASSUMED]` with concrete recommendations and probe-test instructions.

**Primary recommendation:** Split the phase into two plan tracks — (1) the four one-line-to-small fix contracts with RED-GREEN regression tests at the real bug sites (each fix is small and independent; D-09 is literally one call), and (2) the curve editor as a layered build: `core/image_ops.py` `curve_lut`/`curves_page` (headless, unit-testable first) → `curves_dialog.py` CurvesWidget + dialog (collector + preview driver per the Levels pattern) → `main_window.py` `action_curves`/`_on_curves` rename wiring (Alt+T slot preserved, `_apply_geometry_op("curves", geometry=False, …)`, flash "Curves applied.", `_undo_op_label` set +"curves"). Keep `levels_lut`/`levels_page` and their tests in place ("beside" per CONTEXT); delete `levels_dialog.py` only when the Curves dialog lands and its tests are migrated.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Curve interaction (drag/add/delete points, keyboard) | GUI widget (Qt) | — | Mouse/key dispatch + QPainter paintEvent are Qt event/paint territory — the same place mask tools live |
| Curve→LUT math + per-channel composition | Core domain (`core/image_ops.py`) | — | Pure numpy, headless unit-testable, mirrors `levels_lut` (T-05-07 backstop discipline); GUI must not own pixel math |
| Preview / Apply / Cancel / undo lifecycle | Controller (MainWindow orchestration) | Core (op math) | `_apply_geometry_op` is the ONE place the image-op contract lives (one undo entry, D-14 re-baseline, D-22 flag); dialog is a pure collector (Pitfall 9) |
| Empty-state overlay management | GUI (canvas) | — | `_update_empty_state`/`_refresh_empty_box_hint` are canvas state — the D-09 one-liner lives there |
| Toolbar↔dock active-tool sync | GUI (MainWindow + ToolsPanel) | — | `QActionGroup` exclusivity + checkable actions are Qt action machinery; panel owns the group (tools_panel.py:105-106) |
| Dialog typography (14px Body) | GUI (each dialog) | — | Per-dialog font inheritance; no app-wide font change (theme.py sets palette only) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 (Qt 6) | 6.10.1 (installed, verified) | UI framework: QDialog/QPainter/QActionGroup/QToolButton/widgets | The app's framework since Phase 1; UI-SPEC contracts standard Qt6 widgets only; `[VERIFIED: local probe]` |
| numpy | 2.3.5 (installed, verified) | `curve_lut`/`curves_page` math, `np.histogram` for D-08 | `levels_lut` precedent (image_ops.py:431-450); fancy-index LUT apply; `[VERIFIED: local probe]` |
| Python | 3.14.2 (pinned interpreter) | Runtime | AGENTS.md pins `C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`; `[VERIFIED: local probe]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest + pytest-qt | (existing suite, 552 green at Phase 5 close) | RED-GREEN regression tests on the fix sites + curve dialog tests | Every plan task with a behavior contract; `[VERIFIED: 05-UI-REVIEW-FIX.md full-suite result]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom QPainter widget | A third-party curve widget (e.g. pyqtgraph HistogramLUTItem, matplotlib) | pyqtgraph/matplotlib add heavyweight deps for one widget; QPainter is stdlib-Qt and matches the "no new dependencies" contract; custom = full control of D-04…D-08 interaction |
| Piecewise-linear interpolation | Spline/Bezier curve interpolation | Photoshop uses linear interpolation between points (the "curve" is a polyline through points); linear is deterministic, monotone-friendly, and trivial to backstop; splines introduce overshoot that fights the endpoint/gamma clamps |
| `levels_lut` reuse for curves | Remove `levels_lut` | CONTEXT says `curve_lut` lands "beside" `levels_lut`; levels math is tested (test_core/test_image_ops.py:352) and remains the model for the endpoint semantics — keep both |

**Installation:**
```bash
# NONE — zero new dependencies. PySide6 6.10.1 + numpy 2.3.5 already installed.
```

**Version verification:** PySide6 6.10.1 / numpy 2.3.5 / Python 3.14.2 — all verified live this session via the pinned interpreter (`[VERIFIED: local probe]`).

## Package Legitimacy Audit

> **No external packages are installed in this phase.** The curve editor is custom QPainter + numpy (both already in the stack); the four fixes touch existing Qt code. The Package Legitimacy Gate protocol is N/A — there is nothing to vet. The only registry the project interacts with is pip for the existing stack, unchanged since Phase 1 (PySide6 LGPL, numpy BSD — both approved in 05-UI-REVIEW §Registry Safety).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | Approved — no new packages this phase |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
┌────────────────────────────── MainWindow (controller) ─────────────────────────────┐
│  Tools ▸ Curves… (Alt+T slot, action_curves, replaces action_levels at :793/:824) │
│        │                                                                           │
│        ▼                                                                           │
│  _on_curves():  base = canvas.get_image_numpy().copy()  (Pitfall 2)                │
│        │                                                                           │
│        ▼                                                                           │
│  CurvesDialog (collector + preview driver — Pitfall 9)                             │
│  ┌──────────────────────────────────────────────────────────────────────────────┐ │
│  │ preset row (Linear/S-curve/Brighten/Darken)   channel switcher (RGB·R·G·B)   │ │
│  │ black/white slider rows ──sync──▶ CurveWidget (QPainter grid + points) ◀─sync─│ │
│  │ gamma row ──────────────sync──▶ midpoint anchor                               │ │
│  │ numeric In/Out spins (selected point)         [Cancel] [Apply]               │ │
│  │ histogram: np.histogram(detached page_image) drawn faintly behind grid (D-08)│ │
│  └──────────────────────────────────────────────────────────────────────────────┘ │
│        │  every control change: preview_callback(curves_page(base, master, chans))│
│        ▼                        via set_image_from_numpy_preview(capture_original=│
│  canvas ── capture-suppressed preview (never re-baselines Show Original)         │
│        │                                                                           │
│  Cancel ──▶ canvas.set_image_from_numpy(base.copy())  (silent exact restore)      │
│  Apply ───▶ canvas.set_image_from_numpy(base.copy())  (b376f8a restore-BEFORE     │
│             ──▶ _apply_geometry_op("curves", geometry=False, transform_fn,        │
│                                    flash="Curves applied.")                       │
│                    ├─ pre-capture .copy() → push_geometry_state (ONE IMAGE entry) │
│                    ├─ write-back set_image_from_numpy (D-09's empty-state call    │
│                    │   makes the trio/hint correct here too)                      │
│                    ├─ rebaseline_original() (D-14)                                │
│                    └─ geometry_altered NOT set (geometry=False, D-15/D-22)        │
│                                                                                   │
│  Core: image_ops.curves_page(img, master_pts, {R,G,B}_pts)                        │
│        └─ curve_lut(points) → 256-entry uint8 LUT (sort/dedupe/clamp backstop)    │
│        └─ out_c = channel_lut_c[master_lut[v]]  (composition, [ASSUMED] — probe)  │
└───────────────────────────────────────────────────────────────────────────────────┘

Deferred fixes (independent, low-risk):
  D-09  canvas._set_image_from_numpy ──+1 line──▶ _update_empty_state()
  D-10  window action_tool_* ──checkable + tool_group membership──▶ toolbar highlights
  D-11  canvas.py:278 hint copy ──▶ "…Open Folder… (Ctrl+Shift+O)…" (or drop shortcut)
  D-12  each dialog setFont 14px Body
```

### Recommended Project Structure
```
manga_ai_studio/
├── core/
│   └── image_ops.py              # EXTEND — curve_lut() + curves_page() beside levels_lut (keep)
├── gui/
│   ├── curves_dialog.py          # NEW — CurvesDialog (collector + preview driver) + CurveWidget
│   ├── levels_dialog.py          # REPLACED by curves_dialog.py (delete once migrated)
│   ├── main_window.py            # EXTEND — action_curves/_on_curves; D-10 toolbar wiring
│   ├── canvas.py                 # EXTEND — D-09 one-liner; D-11 hint copy
│   ├── tools_panel.py            # (integration point for D-10, likely unchanged)
│   ├── crop_dialog.py            # MOD — 14px Body font (D-12)
│   ├── resize_dialog.py          # MOD — 14px Body font (D-12)
│   └── load_translations_dialog.py # MOD — 14px Body font (D-12, scope decision)
tests/
├── test_core/test_image_ops.py   # EXTEND — curve_lut/curves_page unit tests (headless)
├── test_gui_curves_dialog.py     # NEW — dialog contract + e2e apply tests (pytest-qt)
├── test_gui_image_dialogs.py     # MOD — Levels tests migrate to Curves
├── test_gui_canvas.py            # EXTEND — D-09 numpy-path + D-11 copy regression tests
├── test_gui_project.py           # EXTEND — project-open empty-state regression (D-09)
└── test_gui_crop_tool.py         # EXTEND — toolbar checked-state sync regression (D-10)
```

### Pattern 1: Collector + preview driver (the Levels contract the Curves dialog inherits)
**What:** The dialog NEVER mutates models. It collects control state, drives the canvas through a `preview_callback` (capture-suppressed), stores `result_values` on Apply, and the MainWindow owns restore/apply/undo. (05-RESEARCH Pitfall 9; LoadTranslationsDialog template.)
**When to use:** Every dialog that previews an image op. Verified shape in `levels_dialog.py:95-179` (`_updating` guard, `_refresh`, `result_values`, Cancel/Apply) and `_on_levels` (`main_window.py:1227-1274`).
**Example (the Apply-side ordering that MUST be preserved — b376f8a):**
```python
# main_window.py:1254-1274 (VERIFIED verbatim, levels path)
if dialog.exec() != QDialog.DialogCode.Accepted:
    self.canvas.set_image_from_numpy(base.copy())   # Cancel: silent exact restore
    return
# b376f8a: restore the detached pre-dialog base BEFORE _apply_geometry_op so the
# undo before-state is the TRUE pre-op image (previews mutated the canvas).
self.canvas.set_image_from_numpy(base.copy())
def _transform():
    return image_ops.levels_page(base, black, white, gamma), None, None
self._apply_geometry_op("levels", geometry=False, transform_fn=_transform, flash="Levels applied.")
```

### Pattern 2: LUT math with a backstop (T-05-07 discipline)
**What:** Sample the curve at 256 points → uint8 LUT; normalize/clamp so a degenerate input can never produce NaN or an out-of-range index; apply via fancy-index `lut[image]`; trailing `.copy()` detach (Pitfall 2). Verified model: `levels_lut` (image_ops.py:431-450) — "an inverted map can never render, even when white <= black".
**When to use:** Any per-pixel tone op. The curve version: sort points by x, dedupe x (last-wins or reject — pick one), clip y to [0,255], `np.interp` for piecewise-linear sampling, `round().astype(np.uint8)`.

### Pattern 3: Custom interactive widget (QPainter)
**What:** A `QWidget` subclass overriding `paintEvent` (grid, diagonal, histogram, curve `QPainterPath`, point handles), `mousePress/Move/Release` (hit-test ~10px, add/drag, double-click delete), `keyPressEvent` (arrows nudge, Tab/Shift+Tab select — `setFocusPolicy(Qt.StrongFocus)` required), and `QWidget.update()` to repaint. One signal (e.g. `points_changed`) drives the dialog's `_refresh`.
**When to use:** Greenfield interactive controls. Qt docs (doc.qt.io) confirm: construct QPainter inside `paintEvent`, use `Antialiasing` + float overloads, `drawPath` for reusable shapes. `[CITED: doc.qt.io/qt-6/qpainter.html]`

### Anti-Patterns to Avoid
- **Making toolbar buttons checkable without checkable actions:** `btn.setCheckable(True)` on a button whose `defaultAction()` is non-checkable makes `setChecked` a no-op — the exact D-10 defect (probe-verified in 05-07-SUMMARY.md:206). The ACTION must be checkable; the button then mirrors it.
- **Mutating the canvas from inside the dialog:** breaks Cancel semantics (Pitfall 9); the preview must flow through the MainWindow-provided `preview_callback`.
- **Restoring the preview state as the undo before-state:** the b376f8a lesson — restore the detached base before `_apply_geometry_op` captures; a regression test must assert Ctrl+Z restores the pre-dialog image byte-identical.
- **Skipping `.copy()` on the histogram source or preview base:** Pitfall 2 — the dialog's `page_image` and every `get_image_numpy()` result must be detached before use/storage.
- **Free-range slider↔endpoint sync:** without clamps (black max = white−1 mirror), the endpoints can invert and the T-05-07 backstop is silently bypassed — clamps are the contract (D-02/D-03).
- **Deleting `levels_lut`/`levels_page`:** they are tested (`test_image_ops.py:352`) and remain the endpoint-math model; CONTEXT says the new LUT lands "beside" them.
- **Adding the 6th-window-action to the group twice / double `tool_changed` emissions:** the panel connects `toggled` per action (tools_panel.py:149-150); window actions must NOT also connect `toggled` (their `triggered` lambdas already call `set_active_tool`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Histogram computation (D-08) | Manual bin counting loops | `np.histogram(image, bins=256, range=(0, 256))` | Vectorized, one call, standard; CONTEXT names it explicitly |
| Curve interpolation (points → 256 LUT) | Python for-loops per segment with manual rounding | `np.interp(xs, sorted_xs, sorted_ys)` + clip + `round().astype(np.uint8)` | Vectorized piecewise-linear = exactly the Photoshop convention; immune to off-by-one/float drift |
| LUT apply to page pixels | Per-pixel Python loops | Fancy indexing `lut[image_rgb]` (the `levels_page` pattern, image_ops.py:459-470) | C-speed; already the proven path |
| Active-tool exclusivity | Hand-managed checked-state flags | `QActionGroup(exclusive=True)` + checkable actions | Group exclusivity is the Qt contract; the panel already implements it (tools_panel.py:105-106, 244-265) |
| Slider↔spin sync loops | Manual mirroring with recursion guards | Direct `valueChanged`→`setValue` links (levels_dialog.py:164-169 — Qt does not re-emit identical values) | Proven loop-free pattern |

**Key insight:** every pixel/LUT primitive this phase needs already exists in the repo in some form (`levels_lut`, `levels_page`, the slider/spin rows, the exclusive QActionGroup, the collector dialog). The curve editor is composition of verified in-repo patterns + one vectorized interpolation — not new infrastructure.

## Runtime State Inventory

> This phase renames the "Levels…" surface to "Curves…" (D-01) and renames the `levels_dialog` module — a code-level rename. The canonical question ("after every file is updated, what runtime systems still hold the old string?") is answered explicitly per category.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** Image ops are NOT serialized in `.mas` — locked by Phase 5 D-05 ("Curve serialization in .mas — rejected"; the post-op image is saved). No database, no collections, no keys hold "levels". | None (code edit only) |
| Live service config | None — no external services; Qt window titles/actions are in-code | None |
| OS-registered state | None — no Task Scheduler/services/registry entries reference app internals | None |
| Secrets/env vars | None — no env var or secret names contain "levels" | None |
| Build artifacts | None — no packaging/pip installs in this milestone (STATE.md: packaging deferred); no egg-info/cached builds to regenerate | None |
| **In-code rename scope (the actual work)** | `action_levels` (main_window.py:793, added to Tools menu :824, gated in `_refresh_action_states` :1090) → `action_curves` "Curves…"; `_on_levels` (:1227) → `_on_curves`; op_name "levels" → "curves" incl. `_undo_op_label` set `("rotate","crop","levels","resize")` (:2888) + "curves"; flash "Levels applied." → "Curves applied."; `levels_dialog.py` → `curves_dialog.py`; test call sites (`test_gui_image_dialogs.py:191,229,279` call `_on_levels`; `:196,242` assert "Levels applied.") | Code edits + test migration; `levels_lut`/`levels_page`/`test_image_ops.py:352` KEEP (untouched, still valid math) |

**Nothing found in categories 1-5** — verified by Phase 5 D-05 (no serialization), no service config in repo, and no packaging in the milestone.

## Common Pitfalls

### Pitfall 1: The D-09 one-liner placed on the shared `_set_image_from_numpy` also runs on every preview frame
**What goes wrong:** `set_image_from_numpy_preview` routes through the same shared implementation (canvas.py:683-696 → 710), so `_update_empty_state()` runs on every live-preview frame during the Curves dialog.
**Why it happens:** the shared impl is the natural fix site per D-09's prescription verbatim ("at the end of `_set_image_from_numpy`", canvas.py:710-767).
**How to avoid:** This is benign and idempotent — with an image present, `_update_empty_state` only toggles visibility and calls `_refresh_empty_box_hint` (canvas.py:1552-1562); it repositions text only when `empty` is True (1563-1575). Verify with a preview-path test (open dialog → preview fires → trio stays hidden, no crash). If the plan prefers zero preview-path coupling, the call may instead go at the end of the public `set_image_from_numpy` wrapper (canvas.py:658-681) — same contract, preview excluded. Either satisfies D-09.
**Warning signs:** empty-state items visible while the Curves dialog previews.

### Pitfall 2: Toolbar sync via `QToolButton.setChecked` remains a no-op after the D-10 fix if the wiring misses the ACTION
**What goes wrong:** `_make_tool_toolbar_button` builds `QToolButton` with `setDefaultAction(action)`; the button's checked state mirrors the ACTION's checked state. Making the button checkable alone (current state) does nothing.
**Why it happens:** `set_active_tool` (main_window.py:3120-3138) sets `btn.setChecked(True)` with `blockSignals` — correct once the default action is checkable.
**How to avoid:** Option 1 (recommended, matches the deferred-items prescription): `act.setCheckable(True)` on the six window tool actions + `self.tools_panel.tool_group.addAction(act)` for each; the group's exclusivity keeps exactly one checked; the Tools-menu items then show a checkmark on the active tool (benign, Photoshop-like feedback — the plan should note it). Option 2: `btn.setDefaultAction(panel_action)` instead of the window action (panel actions are already checkable + in the group; window actions stay non-checkable so menus show no checkmarks). Fix the false comment at `_make_tool_toolbar_button` (:3109-3111) either way. Regression test: after `set_active_tool` via each entry path (V/B/R/L/E/G shortcut, menu trigger, programmatic), assert the matching toolbar button `isChecked()` and all others unchecked — the test must FAIL on the current code (RED gate).
**Warning signs:** the crop toolbar test `test_crop_action_in_tools_menu` (test_gui_crop_tool.py:227-267) still passes because it asserts `defaultAction().data()`, not checked state — extend it rather than replace it.

### Pitfall 3: The Curves Apply path regresses the b376f8a restore-before-Apply ordering
**What goes wrong:** if `_on_curves` calls `_apply_geometry_op` directly after `exec() == Accepted`, the pre-capture reads the last preview frame (≈ post-op image) as the undo before-state → Ctrl+Z is a no-op (the Levels no-op-undo FLAG, 05-UI-REVIEW Pillar 5).
**Why it happens:** live previews mutate the canvas mid-dialog (Pitfall 9 — silent display mutations, no pushes).
**How to avoid:** copy the `_on_levels` shape verbatim: restore `base.copy()` after Accepted and before `_apply_geometry_op` (main_window.py:1267); carry the restore-semantics assertion from `test_levels_apply_pushes_one_entry` into the Curves Apply test (one Ctrl+Z → byte-identical pre-dialog image, stack empty).
**Warning signs:** `test_curves_apply_pushes_one_entry` (migrated) would fail RED on a regression.

### Pitfall 4: Slider↔endpoint and gamma↔midpoint sync without clamps
**What goes wrong:** black slider past white slider → inverted endpoints → the curve LUT's backstop is bypassed; the T-05-07 discipline is silently violated ("a degenerate curve must never render an inverted map").
**Why it happens:** bidirectional sync is a loop of `setValue` calls; without a single clamp mechanism, transient states diverge.
**How to avoid:** one clamp in `_refresh` guarded by `_updating` (the levels_dialog.py:211-234 pattern, verbatim): black max = white−1, white min = black+1; endpoints clamp to each other by construction (left endpoint x ∈ [0, right_x−1], right ∈ [left_x+1, 255]). Gamma↔midpoint: define gamma as the curve's sampled output at input 128 (always well-defined); setting gamma injects/moves the (128, y) point. `[ASSUMED]` implementation detail — probe in tests.
**Warning signs:** a test dragging black to 200 leaves white minimum at 201 (mirror `test_levels_defaults_and_clamp`).

### Pitfall 5: Histogram source aliasing (Pitfall 2 on the D-08 path)
**What goes wrong:** computing `np.histogram` over the live canvas buffer or the dialog's `page_image` without `.copy()` — GC'd buffers → segfaults; stale preview state → wrong histogram.
**Why it happens:** the detached `page_image` passed into the dialog is the restore/apply base (main_window.py:1243-1246); the preview closure keeps referencing it.
**How to avoid:** compute the histogram ONCE in the dialog constructor from `page_image` (already detached by the caller — defensive `.copy()` anyway); D-08 locks "computed once at dialog open" (GIMP: histogram "is not updated during treatment" — same convention).
**Warning signs:** histogram changes while dragging (it must not).

## Code Examples

### Common Operation 1: `curve_lut` — piecewise-linear curve → 256-entry LUT with backstop
```python
# Recommended shape for core/image_ops.py (beside levels_lut; model after levels_lut's
# docstring discipline). Source: this research — levels_lut (image_ops.py:431-450)
# is the in-repo model; np.interp is the vectorized piecewise-linear sampler.
def curve_lut(points: list[tuple[int, int]]) -> np.ndarray:
    """Build a 256-entry uint8 curve lookup table (D-04/D-06, PROJ-04 curves).

    ``lut[v]`` maps input ``v`` to the piecewise-linear interpolation of the
    control points (Photoshop convention). Backstop (T-05-07 discipline): the
    points are sorted by x, duplicate x kept last-wins, and y clipped to
    [0,255] — a degenerate point set can never produce NaN, an out-of-range
    index, or a silently-wrong map. Endpoints default to (0,0)/(255,255) when
    omitted. Returns a detached uint8 array.
    """
    pts = sorted(points, key=lambda p: p[0])
    xs = [max(0, min(255, int(x))) for x, _ in pts]
    ys = [max(0, min(255, int(y))) for _, y in pts]
    if not xs or xs[0] != 0:
        xs.insert(0, 0); ys.insert(0, 0)
    if xs[-1] != 255:
        xs.append(255); ys.append(255)
    lut = np.interp(np.arange(256), xs, ys)
    return np.clip(np.round(lut), 0, 255).astype(np.uint8)
```

### Common Operation 2: `curves_page` — master + per-channel composition (geometry-free, D-15)
```python
# Recommended shape for core/image_ops.py. Composition order [ASSUMED]: per-channel
# LUT applied AFTER the master (out_c = channel_lut_c[master_lut[v]]) — the
# CONTEXT-listed first candidate; the plan should add a probe test pinning the order.
def curves_page(
    image_rgb: np.ndarray,
    master_points: list[tuple[int, int]],
    channel_points: dict[str, list[tuple[int, int]]],
) -> np.ndarray:
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3 or image_rgb.dtype != np.uint8:
        raise ValueError("expected (H,W,3) uint8 RGB")
    master = curve_lut(master_points)
    out = master[image_rgb]                     # master applies to all channels
    for ch, idx in (("R", 0), ("G", 1), ("B", 2)):
        pts = channel_points.get(ch)
        if pts:
            ch_lut = curve_lut(pts)
            out[..., idx] = ch_lut[out[..., idx]]  # per-channel applied after master
    return out.copy()                           # Pitfall 2: detach
```

### Common Operation 3: The CurveWidget skeleton (QPainter custom widget)
```python
# Source pattern: doc.qt.io QPainter docs (paintEvent-only painting) + GIMP curves
# conventions (grid, diagonal, fixed endpoints, points). Shape only — exact
# geometry/pens are planner/executor discretion per CONTEXT.
class CurveWidget(QWidget):
    points_changed = Signal()
    point_selected = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # D-07 keyboard story
        self._points: list[tuple[int, int]] = [(0, 0), (255, 255)]
        self._selected = 0
        self._histogram: np.ndarray | None = None
        self.setMinimumSize(280, 240)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 1. grid lines + muted diagonal; 2. faint histogram (D-08);
        # 3. QPainterPath polyline through mapped points (accent pen);
        # 4. control-point handles (selected = accent outline)
    def mousePressEvent(self, e):
        # hit-test 10px around points -> select/drag; else add point at click
        # (clamped: x order preserved vs neighbors; endpoints y locked 0/255)
    def mouseDoubleClickEvent(self, e):
        # D-04: double-click a point deletes it (endpoints never delete)
    def keyPressEvent(self, e):
        # D-07: arrows nudge selected ±1 (Shift=±10); Tab/Shift+Tab cycle points
```

### Common Operation 4: D-10 toolbar fix (Option 1 — window actions checkable + in the group)
```python
# In _build_tools_menu after each action_tool_* creation (main_window.py:710-753):
self.action_tool_move = QAction("Move/Pan", self)
self.action_tool_move.setData(ToolMode.MOVE)
self.action_tool_move.setCheckable(True)                    # D-10: was missing
self.tools_panel.tool_group.addAction(self.action_tool_move)  # D-10: exclusive group
self.action_tool_move.triggered.connect(lambda: self.set_active_tool(ToolMode.MOVE))
# ...repeat for brush/rectangle/lasso/eraser/crop (main_window.py:714-753).
# AND correct the false comment at _make_tool_toolbar_button (:3109-3111):
# "The buttons share the ToolsPanel's QActionGroup — each button's default action
#  is checkable and a member of the panel's exclusive group, so the toolbar and
#  dock highlight the same active tool."
# Qt detail: QToolButton mirrors its default action's checked state; the group's
# exclusivity unchecks the previous tool's action (and thus button) automatically.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Levels dialog: fixed black/white/gamma sliders only (Phase 5 D-12 fallback) | Full draggable curve editor with master + per-channel curves, presets, histogram (D-01…D-08) | Phase 6 (this phase) | PROJ-04 "curves" half lands; the Levels sliders survive as the quick-access row (D-01), so the Levels learning curve is preserved |
| Levels no-op undo record (05-UI-REVIEW Pillar 5 FLAG) | Restore-before-Apply ordering (b376f8a, 2026-08-09) | Already fixed in Phase 5 | The Curves Apply path MUST preserve the ordering — do not regress |
| Toolbar gives no active-tool indication (defect since Phase 1 plan 04) | Checkable window actions in the panel's exclusive group (D-10) | Phase 6 | Accent reserved use #1 (active-tool highlight) finally renders on the toolbar |
| Empty-state overlay persists after project open (since Phase 5) | `_update_empty_state()` call on the numpy display path (D-09) | Phase 6 | One-line fix closes the 05-UAT deferred follow-up |

**Deprecated/outdated:**
- `levels_dialog.py`: superseded by `curves_dialog.py` (D-01 "replaces the Levels dialog"). Delete after the Curves dialog lands and its tests migrate; git history retains it.
- `_on_levels` / `action_levels` / "Levels…": renamed to `_on_curves` / `action_curves` / "Curves…" (D-01); the Alt+T Tools-menu Image-section slot and placement stay.
- `levels_lut`/`levels_page`: NOT deprecated — kept and still tested (`test_image_ops.py:352`); the endpoint math remains the model for the curve's black/white semantics.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Master∘channel LUT composition = `out_c = channel_lut_c[master_lut[v]]` (per-channel applied after master) | Architecture Patterns / Code Examples | Wrong order flips the visual result of combined master+channel edits; mitigated by a probe test pinning the order (the CONTEXT-listed first candidate) |
| A2 | Preset coordinates: S-curve `[(0,0),(64,40),(192,215),(255,255)]`, Brighten `[(0,0),(128,150),(255,255)]`, Darken `[(0,0),(128,105),(255,255)]` | Standard Stack / Patterns | Only affects preset starting points — user-editable afterwards (D-05), so low risk; adjust in plan if desired |
| A3 | Gamma↔midpoint contract: gamma = curve's sampled output at input 128; `gamma = ln(0.5)/ln(mid_out/255)`; setting gamma injects/moves the (128, y) point; gamma 1.00 ⇒ mid=128 (diagonal) | Patterns / Pitfalls | If the executor picks "explicit (128,y) point required", gamma becomes undefined when the point is deleted — the sampled-value definition is the robust choice |
| A4 | "14px Body" = 14 rendered pixels; implement via `QFont("Segoe UI", 11)`≈15px per the project's ~1.33 pt→px convention, or pixelSize(14) for exactness | Standard Stack / Patterns | The acceptance truth is the UI-SPEC typography row; if the reviewer measures point size instead of pixels, the exact-setting approach could fail a pointSize assertion — a pixelSize(14) font reports pointSize ≈ 10.5, so tests should assert `QFontInfo(font).pixelSize() == 14` |
| A5 | Qt default dialog font ≈ 12px (the UI-REVIEW's baseline claim), and no app-wide font is set (theme.py sets palette only) | Standard Stack | Verified in-repo that no font is set anywhere app-wide; the ~12px figure is the reviewer's measurement — the fix target (14px) is unaffected |
| A6 | `np.interp` with last-wins duplicate-x dedupe is the correct degenerate-input backstop ("never an inverted map" = never NaN/out-of-range; interior non-monotone shapes remain legal, Photoshop convention) | Patterns / Code Examples | If the backstop is expected to enforce monotonicity globally, interior S-dips would be rejected — D-04 does not forbid them; Photoshop allows them |
| A7 | Histogram: luminance `0.299R+0.587G+0.114B` for the RGB master, per-channel plane for R/G/B (D-08 "luminance histogram" wording) | Patterns | Display-only detail; any reasonable luminance definition satisfies D-08 |
| A8 | Adobe helpx curves page content (Photoshop's exact composition internals) | Sources | Could not be fetched (transport errors); all Photoshop conventions used are already locked by D-04…D-08 or grounded in GIMP/Photopea docs |

## Open Questions (RESOLVED)

1. **D-10 wiring: Option 1 (window actions checkable + in the group) vs Option 2 (toolbar buttons bound to panel actions)?**
   - What we know: both satisfy the sync contract (CONTEXT D-10, 05-UI-REVIEW Top Fix 3). Option 1 matches the deferred-items prescription first sentence and gives Tools-menu checkmarks on the active tool (Photoshop-like); Option 2 keeps menus checkmark-free.
   - What's unclear: whether the menu checkmark side-effect is desired.
   - Recommendation: Option 1 — single action object per tool, matches the prescription, and the checkmark is defensible active-state feedback; the plan should note the side effect explicitly.
   - **RESOLVED: Option 1.** Locked in 06-UI-SPEC "Resolved Assumptions" (D-10 row) and implemented in 06-03-PLAN.md (checkable window actions + exclusive QActionGroup; menu checkmark side effect accepted and noted).
2. **D-12 typography scope: the three Phase-5 image-op dialogs only, or all four (incl. LoadTranslationsDialog)?**
   - What we know: the contract row is generic ("dialog field values, labels"); LoadTranslationsDialog is the inherited baseline the review calls out as doing the same thing.
   - What's unclear: user intent (delegated to discretion).
   - Recommendation: all four dialogs in one pass — cheapest, satisfies the contract row everywhere, and the Curves dialog ships at 14px from birth. The mono exception (paste_edit Consolas 10) stays.
   - **RESOLVED: all four dialogs** (incl. LoadTranslationsDialog) + Curves ships at 14px from birth. Locked in 06-UI-SPEC (D-12 row) and implemented in 06-03-PLAN.md (+ 06-04-PLAN.md).
3. **Levels→Curves op-name: add "curves" to `_undo_op_label` (main_window.py:2888) or replace "levels"?**
   - What we know: no serialization (D-05) — no legacy records exist; the set `("rotate","crop","levels","resize")` is in-memory only.
   - Recommendation: replace "levels" with "curves" AND migrate the two "Levels applied." flash assertions (test_gui_image_dialogs.py:196,242) to "Curves applied." — the Levels dialog no longer exists, so its op name is dead.
   - **RESOLVED: replace-not-append** ("curves" replaces "levels" in `_undo_op_label`; flash assertions migrated). Locked in 06-UI-SPEC (copywriting row) and implemented in 06-05-PLAN.md.
4. **`levels_dialog.py`: delete or keep?**
   - What we know: D-01 replaces it; nothing will import it after `_on_curves` swaps the lazy import.
   - Recommendation: delete after migration (dead code); `levels_lut`/`levels_page` stay. If the plan prefers a softer landing, keep it one plan and delete in the following plan — but the repo's gap-closure discipline favors removal.
   - **RESOLVED: delete** after migration — `levels_dialog.py` is deleted in 06-05-PLAN.md once `_on_curves` takes over; `levels_lut`/`levels_page` stay. Locked in 06-UI-SPEC (surface 25 SUPERSEDED row) and the assumption-delta `promote` decision.
5. **Histogram channel for the RGB master: luminance vs per-channel when editing the master?**
   - Recommendation: luminance (A7); the master is a composite tone map, so the luminance histogram is the D-08-literal reading.
   - **RESOLVED: luminance** (`0.299R+0.587G+0.114B` for master; per-channel plane for R/G/B — assumption A7). Locked in 06-UI-SPEC (A7 row) and implemented in 06-04-PLAN.md.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (pinned interpreter) | Everything — tests + app | ✓ | 3.14.2 (`C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe`, per AGENTS.md) | — |
| PySide6 | CurvesDialog/CurveWidget/fixes | ✓ | 6.10.1 | — |
| numpy | curve_lut/curves_page/histogram | ✓ | 2.3.5 | — |
| pytest + pytest-qt | RED-GREEN suite | ✓ | (suite green at Phase 5 close: 552 passed) | — |
| Pillow (PIL) | test fixtures (page image creation) | ✓ | (existing test dep) | — |

**Missing dependencies with no fallback:** none — this phase adds zero external dependencies.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-qt (PySide6 6.10.1); baseline 552 passed / 0 failed at Phase 5 close `[VERIFIED: 05-UI-REVIEW-FIX.md]` |
| Config file | none found — standard pytest.ini-less layout; GUI tests marked `@pytest.mark.gui` |
| Quick run command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_curves_dialog.py -x -q` |
| Full suite command | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` (AGENTS.md) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-04 (curves math) | `curve_lut`: identity for Linear, monotone S-curve, degenerate-input backstop, uint8/clamped output | unit (headless) | `pytest tests/test_core/test_image_ops.py -x` | ✅ extend |
| PROJ-04 (composition) | `curves_page`: master+per-channel composition order (probe A1), geometry-free signature, `.copy()` detach, validation errors | unit | `pytest tests/test_core/test_image_ops.py -x` | ✅ extend |
| PROJ-04 (dialog) | defaults (Linear, 0/255/1.00), preset apply, channel switch, add/drag/double-click-delete points, slider↔endpoint sync + clamp, gamma↔midpoint sync, in/out spins, arrow nudge, Tab selection | GUI (pytest-qt) | `pytest tests/test_gui_curves_dialog.py -x` | ❌ Wave 0 |
| PROJ-04 (lifecycle) | Cancel = byte-identical restore + zero entries; Apply = ONE image-only entry, `geometry_altered` False, "Curves applied." flash, Show Original re-baseline, Ctrl+Z restores pre-dialog image (b376f8a ordering) | GUI e2e (monkeypatched `exec`) | `pytest tests/test_gui_curves_dialog.py -x` | ❌ Wave 0 |
| D-09 | Project open via `_display_page_state` (numpy path) hides the empty-state trio; zero-box page shows the empty-box hint; preview path stays hidden | GUI regression | `pytest tests/test_gui_project.py tests/test_gui_canvas.py -x` | ✅ extend |
| D-10 | After `set_active_tool` via V/B/R/L/E/G shortcut, Tools menu, or programmatic call: matching toolbar button `isChecked()`, all others unchecked (RED on current code) | GUI regression | `pytest tests/test_gui_crop_tool.py tests/test_gui_tools.py -x` (extend existing) | ✅ extend |
| D-11 | Hint copy no longer contains "Ctrl+O" (and states the chosen wording) | unit/regression | `pytest tests/test_gui_canvas.py -x` | ✅ extend |
| D-12 | Dialog field font renders 14px (`QFontInfo(dialog.font()).pixelSize() == 14` per A4) | GUI regression | `pytest tests/test_gui_image_dialogs.py tests/test_gui_curves_dialog.py -x` | ✅ extend |

### Sampling Rate
- **Per task commit:** `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/<touched> -x -q`
- **Per wave merge:** full suite (`-m pytest -q`)
- **Phase gate:** full suite green before `/gsd-verify-work`; the curve-drag feel and toolbar highlight are end-of-phase visual gates (`human_verify_mode: end-of-phase`)

### Wave 0 Gaps
- [ ] `tests/test_gui_curves_dialog.py` — NEW: dialog contract + e2e lifecycle tests (the `test_gui_image_dialogs.py` Levels tests migrate here; `_fake_exec` monkeypatch shape at :218-226 is the template)
- [ ] `tests/test_core/test_image_ops.py` — EXTEND: `curve_lut`/`curves_page` unit tests
- [ ] `tests/test_gui_project.py` / `test_gui_canvas.py` — EXTEND: D-09 numpy-path regression (a project-open path test driving `_display_page_state`; note `test_empty_state_heading` at test_gui_canvas.py:206 asserts text only, not transitions)
- [ ] `tests/test_gui_crop_tool.py` — EXTEND: D-10 checked-state regression (the existing test at :227 asserts `defaultAction().data()`, not `isChecked()` — RED-gate the new assertion)
- [ ] No framework install needed — pytest/pytest-qt already in the suite

## Security Domain

> `security_enforcement: true` (config.json), ASVS level 1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Desktop single-user app; no auth surface |
| V3 Session Management | no | None |
| V4 Access Control | no | None |
| V5 Input Validation | yes | Curve points clamped to [0,255] with x-order preservation + degenerate-input backstop in `curve_lut`; spinbox ranges (0..255 in/out, gamma 0.10..4.00, black/white cross-clamp); `curves_page` validates `(H,W,3) uint8` (mirrors `levels_page`, image_ops.py:464-469) |
| V6 Cryptography | no | No crypto in this phase (`.mas` LZMA is Phase 5's concern, unchanged) |
| V7 Logic | yes (L1-level) | Undo-record integrity: restore-before-Apply ordering (b376f8a) is the anti-tampering guard on the history stack — a regression test asserts the before-state is the true pre-op image |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Fancy-index out-of-range (LUT apply) | Tampering | LUT values are `clip(…, 0, 255).astype(np.uint8)` by construction — uint8 indices can never be out of range; the backstop guarantees no NaN/garbage entries |
| DoS via oversized preview recompute | DoS | Preview cost equals the existing Levels preview (accepted, Phase 5); `MAX_IMAGE_DIMENSION = 10000` load gate (canvas.py:79) bounds page size; histogram computed once at open (D-08), never per-drag |
| Widget-event edge cases (point drag beyond bounds) | Tampering | Mouse handlers clamp to the grid [0,255]² and preserve x-order between neighbors; endpoints y-locked (D-04) |
| Regressing the undo no-op defect | Tampering | `test_curves_apply_pushes_one_entry` restore-semantics assertions (Ctrl+Z → byte-identical pre-op image, stack empty) |

## Sources

### Primary (HIGH confidence)
- **In-repo source-of-truth reads this session** (all `[VERIFIED: file:line]` with verbatim quotes in the text): `manga_ai_studio/gui/canvas.py` (273-293 empty-state trio, 362-383 `set_image`, 410-423 `clear`, 658-767 numpy display paths, 1545-1575 `_update_empty_state`, 1728+ `_refresh_empty_box_hint`); `manga_ai_studio/gui/main_window.py` (295-339 Ctrl+O/Open Folder bindings, 676-828 Tools menu + Image section, 837-889 toolbar, 1075-1096 gating, 1106-1188 `_apply_geometry_op`, 1227-1274 `_on_levels`, 2292-2302 `_display_page_state`, 2536-2578 tool shortcuts, 2880-2894 `_undo_op_label`, 3106-3138 toolbar button + `set_active_tool`); `manga_ai_studio/gui/levels_dialog.py` (full, 247 lines); `manga_ai_studio/gui/resize_dialog.py` + `crop_dialog.py` (full — no fonts set); `manga_ai_studio/gui/tools_panel.py` (105-106 group, 206-221 `_make_tool_action`, 244-272 sync); `manga_ai_studio/core/image_ops.py` (431-470 `levels_lut`/`levels_page`); `manga_ai_studio/gui/theme.py` (palette only); `tests/test_gui_image_dialogs.py` (full — dialog test shape); `tests/test_gui_canvas.py:206-217`; `tests/test_gui_crop_tool.py:227-267`
- **Phase 5 contract docs**: `05-UI-SPEC.md:86` (Body 14px typography row — verbatim), `05-UI-REVIEW.md` (Top Fix 2/3, Pillar 1/3/5/6 FLAGs — root causes + prescriptions), `05-UI-REVIEW-FIX.md` (b376f8a — the ordering to preserve), `05-07-SUMMARY.md:206` (probe-verified toolbar no-op), `deferred-items.md:19-30` (toolbar deferral), `05-UAT.md` (empty-state deferred follow-up)
- **Live environment probe**: Python 3.14.2 / PySide6 6.10.1 / numpy 2.3.5 via the pinned interpreter

### Secondary (MEDIUM confidence)
- [CITED: docs.gimp.org/en/gimp-tool-curves.html] — GIMP curves conventions: grid input/output 0..255, fixed endpoints, click-add/drag-move points, per-channel + composite curves, numeric input/output spins, histogram as reference, S-curve contrast semantics
- [CITED: doc.qt.io/qt-6/qpainter.html] — QPainter paintEvent-only painting, Antialiasing, float overloads, QPainterPath/drawPath, Raster engine for QWidget
- [CITED: photopea.com/learn/adjustments-filters] — curves are a color-consistent LUT adjustment (pixel A→B maps identically everywhere)

### Tertiary (LOW confidence)
- Adobe helpx "Curves adjustment" page — **unreachable** this session (2 transport errors + 1 timeout); Photoshop-specific composition internals remain `[ASSUMED]` (A1/A8). Preset coordinates (A2), gamma↔midpoint definition (A3), luminance weights (A7) are training-knowledge recommendations for the planner to lock in the plan.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; PySide6 6.10.1 + numpy 2.3.5 verified live; every fix surface read in-repo
- Architecture: HIGH — collector+preview-driver, `_apply_geometry_op`, `levels_lut`, QActionGroup patterns all verified at their exact lines; the only greenfield math (interpolation/composition) is grounded in official docs with `[ASSUMED]` flags where Adobe specifics could not be fetched
- Pitfalls: HIGH — every pitfall is this-session verified (the D-10 no-op is probe-confirmed in Phase 5 artifacts; the b376f8a ordering is read verbatim; the `_update_empty_state` idempotence is read line-by-line)

**Research date:** 2026-08-09
**Valid until:** 2026-09-08 (30 days — Qt 6.10.x and numpy are stable; the pinned environment does not float)



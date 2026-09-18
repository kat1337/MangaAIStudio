# Phase 4: OCR Recognition & Text Editing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-04
**Phase:** 4-OCR Recognition & Text Editing
**Areas discussed:** OCR trigger & scope, Inline text-edit surface, Text display on canvas, Translation field & MT seam

---

## Area selection (multiSelect)

| Option | Description | Selected |
|--------|-------------|----------|
| OCR trigger & scope | When OCR runs, on which boxes, page-level action | ✓ |
| Inline text-edit surface | TEXT-04 inline vs side panel vs dialog | ✓ |
| Text display on canvas | Whether text renders persistently on the artwork | ✓ |
| Translation field & MT seam | TEXT-05 granularity, config surface, manual-entry UX | ✓ |

**User's choice:** All four areas.
**Notes:** New capabilities belong in other phases — discussion focused on HOW to implement TEXT-02/04/05.

---

## Area 1 — OCR trigger & scope (TEXT-02)

### Q1.1 — When does manga-ocr run on a box?

| Option | Description | Selected |
|--------|-------------|----------|
| OCR on draw-release (auto) | Alt+drag → OCR runs immediately on release → text fills box | |
| Draw then run OCR (separate) | Alt+drag makes empty box, THEN a separate Run OCR action fills it | |
| Both: auto on draw + run-OCR action | Alt+drag = auto OCR, AND a separate Run OCR action exists | ✓ |

**User's choice:** Both: auto on draw + run-OCR action.
**Notes:** → **D-01** locked.

### Q1.2 — Which boxes can be OCR'd?

| Option | Description | Selected |
|--------|-------------|----------|
| Both origins (user + detected) | OCR runs on user-drawn (amber) AND detected (green) boxes | ✓ |
| User-drawn only | OCR only fills user-drawn boxes; detected boxes not OCR-able in v1 | |

**User's choice:** Both origins (user + detected).
**Notes:** → **D-02** locked. Matches phase goal's "auto-detected regions OR manually drawn." CTD detection finds regions but does NOT run recognition.

### Q1.3 — Page-level OCR action?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — OCR all boxes on page | "OCR All Boxes on Page" (Ctrl+R) fills every empty box, one model load, status-bar progress | ✓ |
| No — single-box only in v1 | Only single-box OCR (auto on draw + Run OCR on selected) | |

**User's choice:** Yes — OCR all boxes on page.
**Notes:** → **D-03** locked. Aligns with Phase 5's `_ocr.json` export (needs text on every box).

### Q1.4 — Re-OCR behavior on a box with existing text?

| Option | Description | Selected |
|--------|-------------|----------|
| Overwrite silently (undo recovers) | Re-OCR always overwrites; undo recovers | |
| Block re-OCR if text exists | Re-OCR blocked; user must clear text first | |
| Confirm only if user edited | Silent overwrite on raw OCR text; confirm dialog on user-edited text | ✓ |

**User's choice:** Confirm only if user edited.
**Notes:** → **D-04** locked. Requires an `edited` flag on the recognized-text field. Mirrors Phase 3 D-03/D-12 but protects manual corrections specifically.

---

## Area 2 — Inline text-edit surface (TEXT-04)

### Q2.1 — How does the user correct recognized text?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline overlay on box (canvas) | Double-click → QTextEdit appears ON the box; type to correct | ✓ |
| Side panel / inspector | Right dock shows selected box's fields; edit there | |
| Popup dialog on double-click | Modal dialog with recognized + translation fields | |
| Side panel primary + inline quick-fix | Both surfaces | |

**User's choice:** Inline overlay on box (canvas).
**Notes:** → **D-05** locked. Most literal reading of TEXT-04 "inline in a box."

### Q2.2 — Vertical vs horizontal text handling?

| Option | Description | Selected |
|--------|-------------|----------|
| Respect box orientation (H + V) | Editor renders vertical for vertical boxes (TextBlock.vertical) | |
| Always horizontal editor | Editor always horizontal; .vertical flag is export metadata only | |
| Horizontal default + per-box toggle | Horizontal by default; toggle flips editor to vertical | ✓ |

**User's choice:** Horizontal default + per-box toggle.
**Notes:** → **D-06** locked. The `.vertical` flag is always preserved on TextBlock regardless of editor mode.

### Q2.3 — Editing vs Phase 3 select/move/resize?

| Option | Description | Selected |
|--------|-------------|----------|
| Double-click = edit, single = select (Phase 3 intact) | Transient overlay on double-click; single-click preserves Phase 3 behavior | ✓ |
| Dedicated edit tool mode | 6th tool in the mask QActionGroup for text editing | |

**User's choice:** Double-click = edit, single = select (Phase 3 intact).
**Notes:** → **D-07** locked. Phase 3 D-07 ("no new tool mode for boxes") preserved.

### Q2.4 — One field or both in the inline editor?

**User's choice (free-text):** "if a translation has already been made, the inline editor should show and edit the translation, with the recognized text being relegated to a field on the sidebar or by a shortcut"

**Notes:** Inline editor's primary subject SHIFTS based on state. Implies a minimal sidebar/secondary surface for whichever field is NOT inline primary.

### Q2.4b — Confirm the demotion model?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — inline primary + sidebar secondary | Inline edits focus field; sidebar shows the other, always editable | ✓ |
| Yes — inline primary + shortcut secondary (no sidebar) | Non-inline field reached via keyboard shortcut | |
| Actually — show both inline, no demotion | Both fields always shown inline | |

**User's choice:** Yes — inline primary + sidebar secondary.
**Notes:** → **D-08** locked. Phase 4 adds a sidebar/inspector panel. Connects to Area 3 (text display on canvas).

---

## Area 3 — Text display on canvas

### Q3.1 — Is text drawn visibly on the canvas?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — render text persistently on canvas | Text drawn continuously over artwork; boxes become display objects | ✓ |
| No — text only in edit overlay/sidebar | Boxes stay Phase 3 correction geometry; text invisible except editing | |
| Only when box is selected (transient) | Text renders on-hover/on-select only | |

**User's choice:** Yes — render text persistently on canvas.
**Notes:** → **D-09** locked. Deliberate upgrade from Phase 3's "boxes are not display objects" stance.

### Q3.2 — Which text renders when a box has both?

| Option | Description | Selected |
|--------|-------------|----------|
| Translation when present, else recognized (mirrors D-08) | Canvas shows current-focus text, consistent across surfaces | ✓ |
| Always recognized text | Canvas always shows source text; translation is metadata | |
| Translation only (recognized never on canvas) | Canvas is final-output preview; recognized text always secondary | |

**User's choice:** Translation when present, else recognized (mirrors D-08).
**Notes:** → **D-10** locked. Consistent with D-08's focus rule.

### Q3.3 — Visual treatment of rendered text?

| Option | Description | Selected |
|--------|-------------|----------|
| Translucent overlay (art visible underneath) | White text + dark outline; art visible; QGraphicsTextItem | ✓ |
| Opaque caption (covers art in box) | Solid panel behind text; covers underlying art | |
| Caption below box (no overlap) | Label strip under each box; no art overlap | |

**User's choice:** Translucent overlay (art visible underneath).
**Notes:** → **D-11** locked. Respects "artwork is the sole saturated surface" (Phase 1 UI principle).

### Q3.4 — Visibility toggle?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — separate Toggle Text Overlay | Independent of mask (M) and box (Shift+M) toggles | ✓ |
| Tied to box overlay toggle (one control) | Hide boxes = hide text | |
| No toggle — always visible | Text always rendered when it exists | |

**User's choice:** Yes — separate Toggle Text Overlay.
**Notes:** → **D-12** locked. Three independent visibility layers (mask / box / text).

---

## Area 4 — Translation field & MT seam (TEXT-05)

### Q4.1 — Translation granularity?

| Option | Description | Selected |
|--------|-------------|----------|
| One translation/box; set_translation() seam | Single string per box; MT adapter calls same setter | ✓ |
| Per-line translation (granular) | Per-line within a box; matches mokuro schema | |
| Per-box now; per-line later (plan-for-it) | Box-level v1; data shape allows per-line later | |

**User's choice:** One translation/box; set_translation() seam.
**Notes:** → **D-13** locked. Matches PROJECT.md "manual translation now, MT seam later."

### Q4.2 — PanelCleaner OCR config surface?

**User's choice (free-text):** "Currently it should be 3 but not for tesseract, do remember this app will be modular and we will eventually allow for changing the translation backend to a ONNX model running on a differnt pyenv, we'll take care of the details later so basically implement 1. but plan for some configuration like model selection, language selection, etc so we can later use other models through an adapter interface"

### Q4.2b — Confirm D-14?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — manga-ocr via OCRModel adapter, config hooks planned | manga-ocr-only v1 through adapter; model/lang/backend hooks designed-in | ✓ |
| No — manga-ocr direct, adapter later | Implement manga-ocr directly; retrofit adapter later | |
| Misread — let me clarify | | |

**User's choice:** Yes — manga-ocr via OCRModel adapter, config hooks planned.
**Notes:** → **D-14** locked. No tesseract, no full config UI now — just the adapter interface shaped for later. Phase 1 D-09b: single env in v1.

### Q4.3 — Manual translation entry UX?

**User's choice (free-text):** "1. But also here's where another important detail comes into play here, here's the system prompt for the current translation model [...system prompt with character notations S1/T/N/FT/SFX, Page X Panel Y schema, and 4 output formats...] basically we will probably be using the Typesetting tool output format, so that means the bubbles will need to be numbered (right to left, top to bottom, maybe add an override for bubble number. and left to right for manhwa) But to answer exactly, 1. Pure manual typing but also a parser that will load the output of the model and match it to the bubbles (and we can skip the SFX for now)"

**Notes:** Significant scope addition. Surfaces a bubble-numbering system + a model-output parser. Refined parser format provided by user.

### Q4.3b — Confirm parser scope (in Phase 4 or deferred)?

**User's choice (free-text):** "1. Plus also note a small change to the output format One code block per page, one line per text box, no notation prefixes on either side: [Bubble Number]: [translated line 1] [SFX -SFX Number]: *sfx line 2*] [Bubble Number]: [translated line 3] Rules: - No SX-X, FT, N labels, just numeric bubble numbers - No Japanese text - One line per text box exactly as it would appear on the page - Only use this mode when the user explicitly asks for it"

**Notes:** → **D-15** locked (full). Phase 4 ships: auto bubble-numbering (RTL/TB manga + LTR manhwa + manual override) + visible numbers on canvas + typesetting-format parser (paste + file) + manual typing base; SFX skipped. Refined parser format is the contract.

### Q4.4 — Reading-order directionality?

| Option | Description | Selected |
|--------|-------------|----------|
| Page-level direction toggle (RTL default / LTR) | Single page-wide direction; flip re-numbers all boxes | |
| RTL-only in v1 (manhwa later) | No toggle; manhwa support later | |
| Page-level auto + per-box manual override | Auto gives starting point; manual overrides stick | ✓ |

**User's choice:** Page-level auto + per-box manual override.
**Notes:** → **D-16** locked. Conflict policy between re-auto and manual override is Claude's Discretion.

### Q4.5 — Parser input mechanics?

| Option | Description | Selected |
|--------|-------------|----------|
| Paste-into-dialog (one page at a time) | QPlainTextEdit paste-area; pick page; Apply | |
| Import text file (chapter-scale) | Import saved model output; multi-page | |
| Both: paste dialog + file import | Shared parser core; two front-ends | ✓ |

**User's choice:** Both: paste dialog + file import.
**Notes:** → **D-17** locked.

### Q4.6 — Panel structure?

| Option | Description | Selected |
|--------|-------------|----------|
| Ignore panels — page-global bubble numbers | Parser keys off [Bubble Number] only; 1..N across whole page | ✓ |
| Panel-local bubble numbers (1-1, 2-1, ...) | Parser respects Panel markers; numbers panel-local | |

**User's choice:** Ignore panels — page-global bubble numbers.
**Notes:** → **D-18** locked. Panels are visual grouping the parser discards.

---

## Claude's Discretion

- Exact widget for inline editor (QTextEdit vs QLineEdit vs custom delegate); vertical-mode Qt implementation (D-06).
- Sidebar/inspector panel structure (dock vs fixed panel vs popover; field layout) (D-08).
- The `edited` flag's home (D-04).
- Conflict policy: page-level re-auto vs manual override (D-16).
- Reading-order auto-number algorithm (RTL/TB + LTR/TB sort key) (D-15/D-16).
- Text-overlay font/size/scaling + outline width (D-11).
- Toggle Text Overlay keybinding (distinct from M, Shift+M) (D-12).
- Parser error handling (unmatched `[N]:` lines) (D-15/D-17).
- Menu/toolbar placement of Run OCR / OCR All / Load Translations actions.
- OCR worker threading (reuse Worker + QThreadPool + _op_running) (D-03).
- Whether `ocr_backend` config key needs a ProfileManager entry or stays adapter-internal in v1 (D-14).

---

## Typesetting styling controls (raised mid-discussion, deferred)

**User's input (free-text):** "obviously the text editor for a manga editor will need font selection (per box, per selected boxes and per page), font style selector, font size selector, increase and decrease font size, font color, horizontal and vertical alignment, a text editor, we might also need some effects like outer glow, outline, etc but we can do those in a refinement phase"

### Q.T1 — Defer, minimal-now, or expand Phase 4?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to a typesetting phase (TRAN-02) | Full styling toolbar (font/style/size/color/alignment/effects) → TRAN-02 or Phase 5.5; Phase 4 overlay uses fixed defaults, no per-box controls | ✓ |
| Minimal global styling now, rest later | Global font family + size +/- app-level (readability only); defer per-box color/alignment/effects | |
| Expand Phase 4 — full styling toolbar now | Reverse Out-of-Scope; Phase 4 becomes a typesetting phase too (also reverses Phase 3 D-08 single-select for "per selected boxes") | |

**User's choice:** Defer to a typesetting phase (TRAN-02).
**Notes:** Consistent with PROJECT.md Out-of-Scope (authored by the user) and D-09/D-11 (Phase 4 overlay is review/correction, not output). The full feature list is preserved in CONTEXT.md Deferred Ideas for the typesetting phase to inherit: font selection (per-box / per-selected-boxes / per-page), font style, font size +/-, font color, H alignment, V alignment, effects (outer glow, outline, etc.). "Per selected boxes" additionally implies multi-select (Phase 3 D-08 single-select would need lifting in that phase). Decision recorded 2026-08-04.

---

## Deferred Ideas

- Machine translation integration (TRAN-01) — v2; seam is set_translation() + adapter shape.
- Typesetting/rendering translated text into the page (TRAN-02) — v2; PROJECT.md Out of Scope.
- Tesseract / non-Japanese OCR engines — D-14; adapter supports adding later.
- ONNX OCR backend on separate pyenv — D-14 plan-for-it; Phase 1 D-09b fallback in v1.
- Per-line translation — D-13; box-level in v1.
- SFX bubble matching in parser — D-15; skipped for v1.
- Batch OCR across a chapter (FLOW-04) — v2; Phase 4 is per-page.
- `_ocr.json` export (PROJ-03) / `.mas` save (PROJ-01) / image ops (PROJ-04) — Phase 5.
- Selective per-box inpaint via std-deviation (Phase 3 D-15 seam) — still deferred; Phase 4 does not fill PageBox.mask/std_dev.
- Panel-aware bubble numbering — D-18; page-global in v1.

---

*Discussion log generated: 2026-08-04*

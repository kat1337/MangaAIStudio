# Phase 7: Typesetting (TRAN-02): render translated text into the page - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-10
**Phase:** 07-typesetting-tran-02-render-translated-text-into-the-page
**Areas discussed:** Render target & output, Styling UI + per-page defaults, Multi-select semantics, Vertical text (tategaki), Effects & text sizing

---

## Render target & output

| Option | Description | Selected |
|--------|-------------|----------|
| Opaque canvas + bake export | Canvas shows final-quality opaque typeset text AND a new export action bakes text into a copy of the page image. One visual truth. | ✓ |
| Export-only rendering | Canvas keeps translucent review overlay; a 'Render Typeset' export composites text into an exported page image. | |
| Opaque canvas only | Text becomes opaque on canvas; no bake-to-image export. | |

**User's choice:** Opaque canvas + bake export
**Notes:** The canvas itself is the deliverable; the export writes the same rendering to disk.

| Option | Description | Selected |
|--------|-------------|----------|
| Current image + text | Exports the current page image (cleaned/edited state) with typeset text composited, as PNG/JPG. Sibling of the Ctrl+E clean export. | ✓ |
| Text-only layer export | Bakes text onto a transparent canvas for compositing elsewhere. | |
| Both | Finished page AND a text-only PNG layer. | |

**User's choice:** Current image + text

| Option | Description | Selected |
|--------|-------------|----------|
| Sidecar convention | `<name>_typeset.png` next to the source page when pristine, `cleaned/` when altered — mirroring _ocr.json placement (Phase 5 D-22). | ✓ |
| Dedicated folder | A `<chapter>_typeset/` folder sibling to the chapter. | |
| Save As dialog | Save As dialog for the single-page case. | |

**User's choice:** Sidecar convention

| Option | Description | Selected |
|--------|-------------|----------|
| Current-focus rule | Phase 4 D-10: translation when present, else recognized text. WYSIWYG. | ✓ |
| Translation-only | Only translated boxes bake. | |
| Recognized-only | Always bake recognized text. | |

**User's choice:** Current-focus rule

---

## Styling UI + per-page defaults

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated dock panel | A typesetting dock/panel sibling of the Inspector. | |
| Inspector expansion | A styling section below the text fields in the existing InspectorPanel. | ✓ |
| Style dialog | A modal 'Style…' dialog applying to the selection. | |
| Canvas toolbar | A floating toolbar row above the canvas. | |

**User's choice:** Inspector expansion
**Notes:** Follows the Inspector's follower-style per-box editing model.

| Option | Description | Selected |
|--------|-------------|----------|
| Page default + inherit | Page default style; boxes inherit; explicit overrides marked; reset-to-inherit. | |
| Flat per-box style | Every box stores its own complete style; 'per-page' = select-all + apply. | ✓ |
| Page-only style | One style per page; no per-box overrides. | |

**User's choice:** Flat per-box style
**Notes:** Deliberate rejection of the inheritance hierarchy; the ROADMAP's "per-page" is satisfied by Select All + apply.

| Option | Description | Selected |
|--------|-------------|----------|
| Full persistence | Per-box style in .mas page files AND a style block in _ocr.json. | ✓ |
| .mas only | Styles persist in .mas; the published _ocr.json contract stays untouched. | |
| Session-only | Styles render and bake but don't serialize. | |

**User's choice:** Full persistence

---

## Multi-select semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Shift+click + Select All | Shift+click toggles; empty canvas clears; Select All Boxes action (Ctrl+A, currently unbound). | ✓ |
| Add marquee | Rubber-band marquee drag on empty space, on top of Shift+click + Select All. | |
| Minimal toggle | Shift+click toggle + Select All only. | |

**User's choice:** Shift+click + Select All

| Option | Description | Selected |
|--------|-------------|----------|
| Styling only | Multi-select is the styling scope only; geometry stays single-box. | |
| Styling + move/delete | Multi-selected boxes move and delete together (grouped geometry); resize stays single-box. | ✓ |
| Full group edit | Style, move, resize, delete for the selection. | |

**User's choice:** Styling + move/delete
**Notes:** Resize explicitly excluded — the corner-handle state machine stays untouched.

| Option | Description | Selected |
|--------|-------------|----------|
| Common-value inspector | Text fields disable; styling section edits ALL selected; mixed values show 'Mixed' until overridden; one BOXES snapshot. | ✓ |
| Primary box shown | Inspector reflects the most-recently-clicked box; changes apply to all selected. | |
| Style-only inspector | Text fields hidden in multi-select. | |

**User's choice:** Common-value inspector (re-confirmed when re-asked)

---

## Vertical text (tategaki)

| Option | Description | Selected |
|--------|-------------|----------|
| True tategaki (custom layout) | Upright glyphs, top-to-bottom, columns right-to-left; custom vertical layout path. The risky one — flagged non-trivial in 04-RESEARCH Pitfall 5. | ✓ |
| Rotated block | QPainter.rotate of the whole block — glyphs on their side, not proper Japanese vertical. | |
| Defer tategaki | Horizontal-only in v1; payload.vertical stays metadata. | |

**User's choice:** True tategaki (custom layout)
**Notes:** Chosen knowingly over the cheap rotated path and over deferring.

| Option | Description | Selected |
|--------|-------------|----------|
| Vertical render, horizontal edit | Tategaki on canvas + bake; inline editor stays horizontal. | ✓ |
| Vertical render + edit | Custom vertical text-edit widget with cursor/IME. | |
| Render + minimal editor | Simple vertical plain-text entry surface. | |

**User's choice:** Vertical render, horizontal edit

| Option | Description | Selected |
|--------|-------------|----------|
| Inspector checkbox drives it | The existing D-06 'Vertical text' checkbox becomes the live control; CTD-detected vertical boxes pre-flagged. | ✓ |
| Auto-detect by script | Vertical auto-applied when translation contains Japanese. | |
| Style-section toggle | A per-box style toggle separate from the metadata flag. | |

**User's choice:** Inspector checkbox drives it

---

## Effects & text sizing

| Option | Description | Selected |
|--------|-------------|----------|
| Outline + outer glow | Configurable outline (width + color) + outer glow. | |
| Outline only | Only the outline, made configurable. | |
| Outline + glow + shadow | The full common set: outline, outer glow, drop shadow. | ✓ |

**User's choice:** Outline + glow + shadow

| Option | Description | Selected |
|--------|-------------|----------|
| Manual size wins, fit optional | User size replaces auto-shrink; wrap at box width, overflow allowed; fit-in-box (04-09) stays as an explicit per-box 'Auto-fit' option. | ✓ |
| Always auto-fit | Fit-in-box stays authoritative; text always shrinks to fit. | |
| No fit, allow overflow | Absolute user size, no auto-fit option. | |

**User's choice:** Manual size wins, fit optional

| Option | Description | Selected |
|--------|-------------|----------|
| Size +/- actions | Explicit increase/decrease font size actions (e.g. Ctrl+= / Ctrl+- pair). | ✓ |
| Spinbox only | Users type the size or use the spinbox arrows. | |

**User's choice:** Size +/- actions

---

## Claude's Discretion

- Style data model (dataclass composition on PageBox, default values, copy() detachment)
- Effect rendering implementation (QTextCharFormat outline vs paint passes; glow/shadow approach)
- Tategaki layout mechanism (per-char paint vs custom document layout; CJK/Latin mixing depth)
- Bake export details (menu placement, shortcut, sidecar suffix, threading)
- Grouped move/delete implementation (drag state machine extension, one snapshot)
- _ocr.json style block schema + .mas style serialization format
- "Mixed" state presentation in the Inspector

## Deferred Ideas

- MT integration (TRAN-01) — separate v2 phase
- Bubble re-sizing / auto-layout — BallonsTranslator territory, out of scope
- Vertical editing (tategaki editor) — render-only in v1
- Marquee rubber-band multi-select — declined for v1, easy additive later
- Per-line styling — per-box flat in v1
- Font management / bundled fonts — system fonts only in v1
- Deep kumimoji/punctuation compression — future polish for the tategaki renderer

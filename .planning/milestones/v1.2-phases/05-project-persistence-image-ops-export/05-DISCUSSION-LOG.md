# Phase 5: Project Persistence, Image Ops & Export - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-08
**Phase:** 5-Project Persistence, Image Ops & Export
**Areas discussed:** .mas project scope & format, Image-op UX & undo, Image ops vs masks/boxes, _ocr.json fidelity & scope, LZMA2 container mechanics, _ocr.json sidecar mismatch, Open/Save session semantics

---

## .mas project scope & format

| Option | Description | Selected |
|--------|-------------|----------|
| One .mas per chapter | Single file holds every page's state | |
| One .mas per page | Sidecar per page, no chapter grouping | |
| Both (manifest + page files) | Per-page .mas files + chapter manifest | ✓ |

**User's choice:** Both (manifest + page files)
**Notes:** User added this area to the discussion; the "Both" choice was made deliberately over the recommended "one per chapter".

| Option | Description | Selected |
|--------|-------------|----------|
| ZIP: JSON + embedded images | Zip archive with manifest + images | |
| JSON, paths to originals only | Tiny files, fragile to moves | |
| JSON + base64 images | Self-contained, bloated | ✓ |

**User's choice:** JSON + embedded images (with explicit "let's use LZMA2 instead of zip" — user selected JSON+embedded but overrode the ZIP compression; base64 option shown here reflects the choice context, actual pick was "JSON + embedded images but let's use LZMA2 instead of zip").
**Notes:** LZMA2 compression is the user's explicit override of the ZIP recommendation.

| Option | Description | Selected |
|--------|-------------|----------|
| Current page image only | Resume where left off; fresh undo | ✓ |
| Original + current image | Larger files, Show Original immediately | |
| Include undo stacks too | True .psd-grade resume, heavy | |

**User's choice:** Current page image only, plus path reference to original (with checksum). "In case the original image is available, we can just use that as our 'base' image, if the image is not available just grey out the option."
**Notes:** User's custom answer — embedded current image + original ref with checksum; Show Original greyed when original unavailable.

| Option | Description | Selected |
|--------|-------------|----------|
| Manual Save/Open, dirty tracking | Ctrl+S/Ctrl+O, dirty title, prompts | ✓ |
| Save + auto-save | Implicit writes | |
| Save As only | No Ctrl+S | |

**User's choice:** Manual Save/Open, dirty tracking

| Option | Description | Selected |
|--------|-------------|----------|
| Project folder beside source | chapter-01.project/ sibling | ✓ |
| Manifest beside chapter, page files beside sources | Scattered | |
| User-chosen location | Dialog-driven | |

**User's choice:** Project folder beside source

| Option | Description | Selected |
|--------|-------------|----------|
| Page files self-contained | Image, mask, boxes, ref — openable standalone | ✓ |
| Page files are partial slices | Only edits, need manifest | |
| Chapter container + page sidecars | Redundant | |

**User's choice:** Page files self-contained

---

## Image-op UX & undo

| Option | Description | Selected |
|--------|-------------|----------|
| 90° steps only | CW/CCW/180, pixel-exact | ✓ |
| Arbitrary angle too | Free rotation, heavy math | |
| Flips only | Least useful | |

**User's choice:** 90° steps only

| Option | Description | Selected |
|--------|-------------|----------|
| Canvas crop tool | 6th tool in the QActionGroup | ✓ |
| Dialog only | Numeric fields | |
| Reuse Rectangle tool | Confusing (paints masks today) | |

**User's choice:** Canvas crop tool (+ optional numeric Crop dialog in Edit menu rides along)

| Option | Description | Selected |
|--------|-------------|----------|
| Levels dialog (black/white/gamma) | 3 controls + live preview | ✓ |
| Full curve editor | Large UI chunk | |
| Auto-levels preset only | Too minimal | |

**User's choice:** Levels dialog (black/white/gamma) with live preview; curves deferred to v2

| Option | Description | Selected |
|--------|-------------|----------|
| Undoable, silent | IMAGE-stack entries, no confirms | ✓ |
| Undoable + confirm gate | Confirm on geometry ops | |
| Not undoable | Regression vs existing IMAGE stack | |

**User's choice:** Undoable, silent; Show Original re-baselines post-op

| Option | Description | Selected |
|--------|-------------|----------|
| Dialog with aspect lock | Width/height, aspect lock default on, px/% | ✓ |
| Preset menu | 50%/200% presets | |
| Canvas drag-resize | Overlay handles + live resample | |

**User's choice:** Resize dialog with aspect lock, px/percentage toggle, live preview

---

## Image ops vs masks/boxes

| Option | Description | Selected |
|--------|-------------|----------|
| Transform mask + boxes with image | Prior work survives every op | ✓ |
| Clear mask+boxes on geometry ops | Destroys prior work | |
| Leave mask/boxes as-is | Drift out of alignment | |

**User's choice:** Transform mask + boxes with image

| Option | Description | Selected |
|--------|-------------|----------|
| Drop outside, clip partial | Status-bar count | ✓ |
| Drop outside, keep partial as-is | Partial may render oddly | |
| Block crop that cuts boxes | Tedious | |

**User's choice:** Drop outside, clip partial (count in status bar)

| Option | Description | Selected |
|--------|-------------|----------|
| Transform bbox + lines | Full payload geometry | ✓ |
| Transform bbox only, lines stale | Export per-line wrong | |
| Transform bbox, drop lines | Loses per-line structure | |

**User's choice:** Transform bbox + lines polygons together

| Option | Description | Selected |
|--------|-------------|----------|
| Pixel-exact mask transforms | QImage exact rotate, nearest-neighbor resize | ✓ |
| Re-detect after ops | Loses hand-edits | |
| Store in page space, transform at render | Bigger refactor | |

**User's choice:** Pixel-exact mask transforms

---

## _ocr.json fidelity & scope

| Option | Description | Selected |
|--------|-------------|----------|
| Strict mokuro schema | Exact compat, no extra fields | |
| mokuro + extra fields | May choke strict validators | |
| Our own shape | Loosely inspired | ✓ |

**User's choice:** Our own shape (user overrode the strict-mokuro recommendation)

| Option | Description | Selected |
|--------|-------------|----------|
| Whole text in one line | mokuro-compatible single line | ✓ |
| Per-line split | Arbitrary, often wrong | |
| Adaptive | Two code paths | |

**User's choice:** Whole text in one line (later refined — see shape definition below)

| Option | Description | Selected |
|--------|-------------|----------|
| Single + batch | Export current page + Batch Export OCR JSON | ✓ |
| Single page only | Click per page | |
| Batch only | Forces folder-wide | |

**User's choice:** Single + batch

| Option | Description | Selected |
|--------|-------------|----------|
| Sidecar next to source, current-state coords | mokuro naming, matches view | ✓ |
| Into cleaned/ folder | Mismatch with mokuro tooling | |
| User-chosen folder | Dialog friction | |

**User's choice:** Sidecar next to source, current-state coords (later refined — see sidecar mismatch area)

| Option | Description | Selected |
|--------|-------------|----------|
| mokuro vocab + our fields | box, vertical, text, translation, bubble_no, origin | ✓ |
| Mirror app model directly | Internal shape verbatim | |
| Minimal: boxes + text only | Nothing extra | |

**User's choice:** mokuro vocab + our fields, INCLUDING lines[]. "Since this will be used for typesetting it is important to note in a text bubble where a line begins and ends."

| Option | Description | Selected |
|--------|-------------|----------|
| Split stored text by \n | Line N gets segment N | ✓ |
| Upgrade to per-line storage | Model change | |
| Lines = geometry only | Re-flow needed downstream | |

**User's choice:** Split stored text by \n onto detected TextBlock.lines polygons; unmatched lines export empty text

---

## LZMA2 container mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| stdlib lzma, custom container | FORMAT_XZ (LZMA2 filter), zero new deps | ✓ |
| py7zr (real 7z archives) | Standard container, new dep | |
| Per-blob .xz + plain manifest | Simplest code, folder of files | |

**User's choice:** stdlib lzma (FORMAT_XZ / LZMA2 filter) in a custom container layout

| Option | Description | Selected |
|--------|-------------|----------|
| Manifest plain, pages compressed | Manifest tiny/diffable | ✓ |
| Everything compressed | Opaque manifest | |
| Manifest embeds pages | No standalone page files | |

**User's choice:** Manifest plain JSON; per-page .mas files carry the LZMA2-compressed payloads

| Option | Description | Selected |
|--------|-------------|----------|
| <chapter>.mas-project/ + manifest.json | Self-documenting suffix | ✓ |
| <chapter>.mas/ folder | Looks like a file | |
| <chapter>.project/ + <chapter>.mas | Mirrors cleaned/ | |

**User's choice:** `<chapter>.mas-project/` folder containing manifest.json + `<page>.mas` files

---

## _ocr.json sidecar mismatch

| Option | Description | Selected |
|--------|-------------|----------|
| Sidecar when pristine, cleaned/ when altered | Dims match the image they sit with | ✓ |
| Always sidecar + self-describing fields | One location, mismatch persists | |
| Always sidecar, accept mismatch | Edge case tolerated | |

**User's choice:** Sidecar next to source when the page is pristine; write into cleaned/ when geometry ops altered the page

---

## Open/Save session semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Prompt Save/Discard/Cancel | On dirty close/open | ✓ |
| Auto-save then open | Implicit writes | |
| Silent replace | Data loss risk | |

**User's choice:** Prompt Save/Discard/Cancel when any page is dirty

| Option | Description | Selected |
|--------|-------------|----------|
| Manifest-driven session | Sidebar order + state restored; sources re-found | ✓ |
| Require source folder present | Fails on moves | |
| Lazy per-page load | Faster open, complex caching | |

**User's choice:** Manifest-driven session (sources re-found via path refs + checksum; embedded images as fallback)

| Option | Description | Selected |
|--------|-------------|----------|
| Manifest + direct page open | Page .mas opens standalone | |
| Manifest only | Page files internal | |
| Page open climbs to manifest | Surprising chapter load | |

**User's choice:** Custom — "I think a bit of both, you can open a manifest with open project, but if you open a page, it can climb to a manifest, but it should pop a window that says 'chapter detected, open entire chapter?' or something like that"
**Notes:** Chapter-detected dialog on direct page .mas open; Yes = chapter via manifest, No = single-page session; no sibling manifest = single page directly.

---

## Claude's Discretion

- **Geometry-op undo record shape** — user declined to discuss this follow-up area; the planner decides how one Ctrl+Z reverses image + mask + boxes together (single combined record vs paired-stack push), per the unified-timeline contract (Phase 3 D-11).
- **Checksum algorithm** (sha256 default), manifest schema fields, container entry-table layout, dialog widget details, resize interpolation, dirty-title format, project-folder collision handling, Recent Projects naming, menu placement, `_ocr.json` field spelling/version value, batch-export threading.

## Deferred Ideas

- **Full curve editor (levels/curves)** — v2.
- **Arbitrary-angle rotation** — v2.
- **Per-line text storage upgrade** — rejected for v1; future typesetting phase may adopt it.
- **Strict mokuro schema compatibility** — overridden by user; converter possible later if a downstream tool demands it.
- **Selective per-box inpaint (Phase 3 D-15 seam)** — stays open; Phase 5 must not fill `PageBox.mask`/`std_dev`.
- **Undo-stack serialization in .mas** — rejected; fresh undo history on reopen.

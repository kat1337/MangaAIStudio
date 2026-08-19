---
phase: 08
slug: masker-selective-inpaint
status: verified
threats_open: 0
asvs_level: 1
created: 2026-08-19
---

# Phase 8 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time across 10 plans (08-01..08-10); verified 2026-08-19 after gap-closure execution (ASVS Level 1, grep-depth).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| persisted project file → model/detection seam | `.mas` per-box mask PNGs, packed plane blobs, std_dev/override values, and detection-result geometry crossed into canvas/worker allocations | untrusted file content (user/corrupt/third-party project files) |
| detection worker → page model | Box lists (`page.boxes`) written back from the batch worker on non-current pages | user-authored box state (D-03 merge must preserve it) |
| canvas three-plane state → LaMa composite | Manual/erase/auto planes composed into the mask LaMa consumes | user strokes, consumed overlays, auto-detected masks |
| in-memory model → close/save | `ImageFile.dirty` decides whether detected/edited state survives a Close | freshly detected boxes/masks (WR-02 / WR-01 dirty-marking) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Tampering | MaskerConfig INI import | low | mitigate | New key loads only through the vendored `try_to_load(..., Pixels, ...)` typed coercion; garbage raises inside the guarded path and falls back to defaults (panelcleaner/config.py) | closed |
| T-08-01b | DoS | inpaint_state / config values | low | accept | Range-bounded floats/ints used in comparisons only; no allocation or parse surface | closed |
| T-08-02 | Tampering | unpack_binary | medium | mitigate | `unpack_binary` slices to h*w and reshapes against caller-declared dims; storage/load side cross-checks blob length against meta dims before unpacking — a crafted short/long blob raises, never a mis-shaped array (manga_ai_studio/core/mask_planes.py) | closed |
| T-08-03 | DoS | plane QImages memory | low | accept | Three page-sized ARGB32 QImages + packed per-page slots bounded by DEFAULT_HISTORY_LIMIT=20 undo entries | closed |
| T-08-04 | Tampering | heatmap/blk coords | medium | mitigate | Heatmap explicitly thresholded (>0) before PIL conversion; blk coords pass V5 int-coercion + per-edge clamp + zero-area drop; reference boxes clamp via `Box.pad(canvas_size)`; no allocation sized from unvalidated dims | closed |
| T-08-05 | DoS | per-box fitting cost | low | mitigate | Fits run on box-sized cutouts (bounded by box area); `mask_selection_fast` short-circuits; box count bounded by the page itself | closed |
| T-08-06 | Tampering | per-box mask PNG decode | high | mitigate | b64+PNG decode fully wrapped (no raw exceptions escape); decoded size cross-checked against box dims from clamped coords; PIL MAX_IMAGE_PIXELS bomb guard enabled (manga_ai_studio/core/project_io.py) | closed |
| T-08-07 | Tampering | packed plane blobs | medium | mitigate | Blob length validated as exactly ceil(h*w/8) against meta-declared dims before unpack; unpack slices to h*w — short/long blob is a ProjectFormatError (project_io.py + mask_planes.py) | closed |
| T-08-08 | Tampering | override/std_dev values | low | mitigate | Enum validation against {"always","never"} and float() coercion both raise ProjectFormatError on garbage; NaN std_dev fails every gate comparison downstream (fail-safe gate-skip) | closed |
| T-08-09 | Tampering | spinbox/slider ranges | low | mitigate | Every control range-clamped at the widget level (UI-SPEC §36); invalid values unreachable; profile loads fall back to defaults on coercion failure | closed |
| T-08-10 | DoS | save-on-change frequency | low | accept | Saves are user-paced preference commits of a small INI; atomic via Profile.safe_write | closed |
| T-08-11 | Repudiation | border indicator vs mask truth | low | mitigate | Solid/dashed derived from the SAME pure function (`inpaint_state`) that gates mask contribution — border cannot disagree with the mask by construction (box_model.py:inpaint_state, box_item.py set_inpaint_state) | closed |
| T-08-12 | Tampering | _on_detection_finished inputs | medium | mitigate | Result dict flows only through thresholded binarize + V5-clamped boxes; no result geometry used for allocation beyond already-validated page dims | closed |
| T-08-13 | DoS | refit on every boxes_modified | low | mitigate | Refit restricted to geometry-CHANGED/new boxes (tuple diff vs before-snapshot), fires on commit only, no-ops without a retained raw mask | closed |
| T-08-14 | Tampering | restored .mas planes | medium | mitigate | Restore consumes only 08-04-validated packed blobs (length cross-checked) and 08-03 compose over loaded per-box masks — no new untrusted parse site | closed |
| T-08-15 | Repudiation | override commit granularity | low | mitigate | One snapshot per commit (incl. multi-box) + named "inpaint override" op flash — every override is a single, reversible Ctrl+Z unit | closed |
| T-08-16 | DoS | derivation in worker loop | low | mitigate | Same box-bounded fitting cost as interactive path; per-page failure non-fatal (D-04 try/except); abort checked at loop top | closed |
| T-08-17 | Tampering | source image decode | medium | mitigate | Reads go through the existing `_read_image_bgr` guard chain; derivation allocates only against the decoded image's own shape (no file-supplied dims reach allocation) | closed |
| T-08-10-01 | Integrity (optimistic) | `_on_std_dev_threshold_changed`, `_rederive_auto_layer`, `_recompose_boxes_auto_plane` | critical | mitigate | All three recompose consumers compose from `canvas.boxes_snapshot()` (current geometry at call-time); threshold slot carries the no-fit guard; re-derive carries WR-03 zero-boxes + WR-02 no-fit guards; `_apply_geometry_op` invalidates `raw_detected_mask`/`auto_mask` (main_window.py:3079/3141/3790/1368) | closed |
| T-08-10-02 | Integrity (distortion) | batch_runner detect branch | high | mitigate | `merge_page_boxes_for_detect` applies the interactive D-03 replace-detected-keep-user rule before derive; `page.boxes = merged` (detection_boxes.py:109-136, batch_runner.py:193-209) | closed |
| T-08-10-03 | Denial of service (user-data) | `_refresh_current_page_after_batch("detect")` | critical | mitigate | `set_auto_binary` in place of `set_planes(empty, empty, ...)` — only the auto plane replaced; live manual/erase planes and erase ledger survive (main_window.py:6488-6492) | closed |
| T-08-10-04 | Tampering (display/state) | inpaint + batch-clean consumption sites | critical | mitigate | `canvas.consume_mask_display()` clears all three planes signal-silently (no mask_modified) — consumed overlay cannot resurrect; re-Inpaint cannot re-process the cleaned region (canvas.py:686-714; sites main_window.py:5050/6512) | closed |
| T-08-10-05 | Repudiation / integrity | detect-mode batch close path | high | mitigate | `_on_batch_finished` (ok>0, detect/detect_and_clean) AND `_on_batch_cleanup` (cancel/abort) mark every touched `ImageFile.dirty` — Close prompts save instead of silently dropping detected boxes (main_window.py:6282-6285/6351-6354) | closed |
| T-08-10-SC | Tampering | npm/pip/cargo installs | low | accept | No new packages — every fix is in-repo Python; no supply-chain surface introduced | closed |

*Status: closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `workflow.security_block_on` (high) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-08-01b | Config values are comparison-only floats/ints; no allocation or parse surface | Operator | 2026-08-19 |
| AR-02 | T-08-03 | Plane memory bounded by 20 undo entries, same order as pre-existing per-page mask cost | Operator | 2026-08-19 |
| AR-03 | T-08-10 | Preference INI commits are user-paced, small, and atomically written | Operator | 2026-08-19 |
| AR-04 | T-08-10-SC | No third-party or new packages introduced by this phase | Operator | 2026-08-19 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-19 | 24 | 24 | 0 | gsd-security-auditor (orchestrated, ASVS L1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-19
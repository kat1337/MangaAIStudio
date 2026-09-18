---
status: secured
threats_open: 0
asvs_level: 1
blocked_on: high
reviewed: 2026-08-08
---

# Security — Phase 05 (project-persistence-image-ops-export)

25/25 threats verified CLOSED (22 mitigated, 3 accepted). No blocking open threats.

## Threat Verification Summary

| Threat ID | Category | Severity | Disposition | Evidence |
|-----------|----------|----------|-------------|----------|
| T-05-01 | DoS (decompression bomb) | high | mitigate | `project_io.py:51` `MAX_ENTRY_DECOMPRESSED`; `:172-174` `lzma.decompress(memlimit=...)`; header/entry unpack wrapped → ProjectFormatError; `test_bad_magic_rejected`, `test_malformed_entry_table_rejected` PASS |
| T-05-02 | Tampering (type confusion) | medium | mitigate | `project_io.py:79-91` `_coerce_int`; required-key checks; `validate_meta`; `ocr_export.py:145-149` strict int dims; `test_meta_validation` PASS |
| T-05-03 | Tampering/Info disclosure (path traversal) | medium | mitigate | `Path.resolve()` before suffix allowlist; sha256 mismatch → embedded-image fallback (`main_window.py:2229-2237`); `test_original_checksum_rule` PASS |
| T-05-04 | DoS (oversized chapter) | medium | mitigate | `MAX_PROJECT_PAGES=1000`, `MAX_IMAGE_DIMENSION=10000`; `test_oversized_chapter_rejected`, `test_meta_validation` PASS |
| T-05-05 | Tampering (integrity + log injection) | low | mitigate | Chunked 1 MiB sha256; logs only stems + error strings, never OCR text |
| T-05-06 | DoS (oversized arrays) | medium | mitigate | `_validate_image_mask` pre-op; resize/levels bounds; `test_resize_rejects_bad_input`, `test_rotate_rejects_bad_shapes` PASS |
| T-05-07 | Tampering (levels inversion) | low | mitigate | Monotone LUT (`lo=min,hi=max`); slider cross-clamp; `test_levels_defaults_and_clamp` PASS |
| T-05-08 | Tampering (in-place mutation) / DoS (undo memory) | medium / low | mitigate | Fresh objects everywhere; per-store `limit` cap; `test_rotate_transforms_all` PASS |
| T-05-09 | DoS (hostile line counts) | low | mitigate | Lines bounded by actual payload zip; `test_newline_split` PASS |
| T-05-10 | Tampering (JSON encoding) | low | mitigate | `ensure_ascii=False`; atomic temp+os.replace; `test_write_round_trip_utf8` PASS |
| T-05-11 | Tampering (undo aliasing) | medium | mitigate | `.copy()` on image/mask/snapshot; `test_geometry_push_detaches_patch` PASS |
| T-05-12 | DoS/availability (disk I/O) | medium | mitigate | OSError → critical dialog + loguru; `test_export_write_failure_dialog` PASS |
| T-05-13 | Tampering (corrupt/newer files) | high | mitigate | `ProjectFormatError` on all load paths; build-then-swap session; `test_open_corrupt_project_keeps_session` PASS |
| T-05-14 | Spoofing (stale Recent Projects) | low | **accept** | Accepted risk — see below |
| T-05-15 | DoS (levels preview flood) | medium | mitigate | Synchronous preview, no history pushes; `test_levels_cancel_restores_exactly` PASS |
| T-05-16 | Tampering (baseline poisoning) | medium | mitigate | `rebaseline_original()` after every op; capture gate; `test_levels_preview_no_baseline_poison` PASS |
| T-05-17 | Tampering (degenerate crop) | low | mitigate | Silent no-op guard; floor+clamp; core validates rect; `test_crop_degenerate_noop` PASS |
| T-05-18 | DoS (dim-out item count) | low | **accept** | Accepted risk — see below |
| T-05-19 | Tampering (sidecar overwrite) | low | **accept** | Accepted risk — see below |
| T-05-20 | DoS (huge batch) | medium | mitigate | Loop-top abort; per-page isolation; Worker dispatch; `test_batch_export_cancel` PASS |
| T-05-21 | Tampering (test tolerance) | low | mitigate | Bounded tolerance + exact persisted==moved_now |
| T-05-10-01 | DoS (triggered-bool crash) | medium | mitigate | Zero-arg lambda `main_window.py:327`; `test_open_project_trigger_loads_session` PASS |
| T-05-10-02 | Tampering (dir creation/cleanup) | medium | mitigate | Pre-create with `created` flag; rmdir empty-only cleanup; mkdir-failure fallback; save_as tests PASS |
| T-05-10-03 | Tampering (arg injection) | low | mitigate | Zero-arg lambda `main_window.py:355`; `test_save_project_trigger_saves_in_place` PASS |
| T-05-SC | Tampering (package installs) | high | mitigate | Zero new deps; no commit touches pyproject.toml/requirements (git log verified) |

## Accepted Risks

- **T-05-14** (low) — QSettings-persisted Recent Projects paths are user-local convenience data; a stale entry surfaces the standard open-error copy.
- **T-05-18** (low) — crop dim-out overlay is a constant 4-rect item count, removed on apply/cancel/tool-switch.
- **T-05-19** (low) — single-page `_ocr.json` export always goes through the Save As dialog (user sees the target); batch writes the D-22 published placement — no silent deletion.

## Open Threats

None. threats_open = 0.

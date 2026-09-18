---
phase: 5
slug: project-persistence-image-ops-export
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-08
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-qt (dev extras; `pyproject.toml:43-47`) |
| **Config file** | none — pytest defaults; `tests/conftest.py` guards PySide6 import |
| **Quick run command** | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_project_io.py -x` |
| **Full suite command** | `& "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest` |
| **Estimated runtime** | ~90-120 seconds |

---

## Sampling Rate

- **After every task commit:** Run the affected module's test file(s): `pytest tests/test_core/test_project_io.py tests/test_core/test_ocr_export.py tests/test_core/test_image_ops.py -q`
- **After every plan wave:** Run `pytest -q` (full suite, ~1-2 min)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PROJ-01 | T-05-01 / T-05-02 | Untrusted-file validation (schema check, int coercion, bounds clamping) | unit | `pytest tests/test_core/test_project_io.py::test_page_file_round_trip -x` | ✅ | ✅ green |
| 05-01-02 | 01 | 1 | PROJ-01 | — | Manifest round-trip rebuilds session order + per-page state | unit | `pytest tests/test_core/test_project_io.py::test_manifest_round_trip -x` | ✅ | ✅ green |
| 05-01-03 | 01 | 1 | PROJ-01 | T-05-03 | Verified original used; missing/mismatched → embedded image + flag (D-06) | unit | `pytest tests/test_core/test_project_io.py::test_original_checksum_rule -x` | ✅ | ✅ green |
| 05-01-04 | 01 | 1 | PROJ-01 | — | Sibling-manifest chapter-climb detection (D-09) | unit | `pytest tests/test_core/test_project_io.py::test_sibling_manifest_detection -x` | ✅ | ✅ green |
| 05-01-05 | 01 | 1 | PROJ-01 | — | D-15 seam: `PageBox.mask`/`std_dev` stay `None` through save/load | unit | `pytest tests/test_core/test_project_io.py::test_d15_seam_preserved -x` | ✅ | ✅ green |
| 05-02-01 | 02 | 1 | PROJ-04 | — | Rotate 90 CW/CCW/180 pixel-exact (image+mask) + box/line transforms (D-17/D-18) | unit | `pytest tests/test_core/test_image_ops.py::test_rotate_transforms_all -x` | ✅ | ✅ green |
| 05-02-02 | 02 | 1 | PROJ-04 | — | Crop: exact slice, drop fully-outside boxes with count, clip partial (bbox AND lines) (D-16) | unit | `pytest tests/test_core/test_image_ops.py::test_crop_drop_and_clip -x` | ✅ | ✅ green |
| 05-02-03 | 02 | 1 | PROJ-04 | — | Resize: image LANCZOS, mask NEAREST, boxes scaled int; levels: LUT math + white>black guard | unit | `pytest tests/test_core/test_image_ops.py::test_resize_and_levels -x` | ✅ | ✅ green |
| 05-03-01 | 03 | 1 | PROJ-03 | — | `_ocr.json` shape: version/img_width/img_height/blocks + per-block fields + lines[] | unit | `pytest tests/test_core/test_ocr_export.py::test_json_shape -x` | ✅ | ✅ green |
| 05-03-02 | 03 | 1 | PROJ-03 | — | D-20 `\n`-split: line N gets segment N; unmatched lines empty; zero-box page exports empty | unit | `pytest tests/test_core/test_ocr_export.py::test_newline_split -x` | ✅ | ✅ green |
| 05-03-03 | 03 | 1 | PROJ-03 | — | D-22 location: pristine → source folder; geometry-altered → `cleaned/` (created if missing) | unit | `pytest tests/test_core/test_ocr_export.py::test_d22_location_rule -x` | ✅ | ✅ green |
| 05-04-01 | 04 | 2 | PROJ-04 | — | Geometry-op undo: ONE Ctrl+Z reverses image+mask+boxes together (stamp-shared) | unit | `pytest tests/test_history.py::test_geometry_undo_reverses_all_three -x` | ✅ | ✅ green |
| 05-05-01 | 05 | 3 | PROJ-01 | T-05-13 | GUI: Save Ctrl+S / Open Ctrl+O / dirty `*` title / Unsaved Changes prompt | integration (pytest-qt) | `pytest tests/test_gui_project.py::test_save_project_writes_project_folder tests/test_gui_project.py::test_dirty_title_suffix tests/test_gui_project.py::test_unsaved_changes_prompt_save_discard_cancel tests/test_gui_project.py::test_ctrl_o_opens_project_not_image -x` | ✅ | ✅ green |
| 05-05-02 | 05 | 3 | PROJ-01 | — | Session rebuild: current_image per page, chapter climb, corrupt-session-kept, missing-original navigation fallback (D-08/D-09/D-06) | integration (pytest-qt) | `pytest tests/test_gui_project.py::test_open_project_restores_session tests/test_gui_project.py::test_page_navigation_uses_embedded_image_for_missing_original -x` | ✅ | ✅ green |
| 05-06-01 | 06 | 4 | PROJ-04 | T-05-15/16 | Rotate end-to-end + Levels live preview + Cancel restores exactly + Apply pushes one entry | integration (pytest-qt) | `pytest tests/test_gui_image_dialogs.py::test_rotate_90cw_end_to_end tests/test_gui_image_dialogs.py::test_levels_cancel_restores_exactly -x` | ✅ | ✅ green |
| 05-07-01 | 07 | 5 | PROJ-04 | T-05-17 | Crop tool: armed rect, Enter applies, Esc cancels, dim-out overlay z=880, 8×8 min | integration (pytest-qt) | `pytest tests/test_gui_crop_tool.py::test_drag_arms_rect_enter_applies_esc_cancels -x` | ✅ | ✅ green |
| 05-08-01 | 08 | 6 | PROJ-03 | T-05-12 | Export GUI: single D-22 default, zero-box, write-failure dialog, batch progress/cancel/mixed-failure | integration (pytest-qt) | `pytest tests/test_gui_export.py -x` | ✅ | ✅ green |
| 05-09-01 | 09 | 1 | PROJ-04 | T-05-21 | Pre-existing test regression fixed (truncation-tolerant move round-trip) | unit | `pytest tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip -x` | ✅ | ✅ green |
| 05-10-01 | 10 | 1 | PROJ-01 | T-05-10-01 | Open/Save Project triggered-bool crash fixed (zero-arg wiring) | integration (pytest-qt) | `pytest tests/test_gui_project.py -q -k "trigger" -x` | ✅ | ✅ green |
| 05-10-02 | 10 | 1 | PROJ-01 | T-05-10-02 | Save As default `.mas-project` pre-created + cancel/different-pick/abort cleanup | integration (pytest-qt) | `pytest tests/test_gui_project.py -q -k "save_as" -x` | ✅ | ✅ green |
| 05-01/04 | 01/04 | 1/2 | PROJ-01/04 | T-05-16 | Show Original gated on `.mas` pages without verified original; re-baseline after ops (D-06/D-14) | integration (pytest-qt) | `pytest tests/test_gui_canvas.py::test_rebaseline_original_after_op tests/test_gui_project.py::test_show_original_gating -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_core/test_project_io.py` — covers PROJ-01 (round-trips, checksum rule, climb detection, D-15 seam)
- [x] `tests/test_core/test_ocr_export.py` — covers PROJ-03 (shape, split, location rule, zero-box)
- [x] `tests/test_core/test_image_ops.py` — covers PROJ-04 (rotate/crop/resize/levels + geometry)
- [x] `tests/test_history.py` — extend for stamp-shared geometry-op undo/redo (PROJ-04)
- [x] `tests/test_gui_project.py` — menu actions, dirty tracking, prompts, Show Original gating (PROJ-01)
- [x] `tests/test_gui_crop_tool.py` — crop tool interaction (PROJ-04)
- [x] `tests/test_gui_image_dialogs.py` — Levels/Resize/Crop dialogs (PROJ-04)
- [x] `tests/conftest.py` — no change needed (PySide6 guard + tmp_path already present)

*Audited 2026-08-08 (gsd-nyquist-auditor): all 8 Wave 0 files exist and pass; full suite 552 passed / 0 failed (exit 0, ~54s).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Levels live preview visual fidelity (in-place canvas update while modal open) | PROJ-04 | Visual — the synchronous numpy transform runs inside the modal's nested event loop; the canvas repaint path mid-modal needs a human eye | Open Levels…, drag the gamma slider, confirm the canvas updates live and Cancel restores the pre-dialog image exactly |
| Crop dim-out overlay + armed-rect feel at 100% zoom | PROJ-04 | Visual — dim alpha 0.45 and 1px inset are perceptual contracts | Activate Crop tool (G), drag a rect, confirm the outside region dims, Enter applies, Esc cancels; verify a <8×8 px drag is a no-op |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 120s (measured ~54s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-08 (gsd-nyquist-auditor audit: 19/19 coverage rows verified green; no new tests required)

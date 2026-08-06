---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
current_phase: 4
current_phase_name: OCR Recognition & Text Editing
status: executing
stopped_at: Phase 4 UI-SPEC approved
last_updated: "2026-08-06T03:54:05.908Z"
last_activity: 2026-08-04
last_activity_desc: Phase 03 complete, transitioned to Phase 4
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 19
  completed_plans: 19
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-11)

**Core value:** One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.
**Current focus:** Phase 4 — OCR Recognition & Text Editing

## Current Position

Phase: 4 — OCR Recognition & Text Editing
Plan: Not started
Status: Ready to execute
Last activity: 2026-08-04 — Phase 03 complete, transitioned to Phase 4

Progress: [█████░░░░░] 60% (3/5 phases)

## Performance Metrics

**Velocity:**

- Total plans completed: 20
- Average duration: 15 min
- Total execution time: 0.25 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Cleaning Workspace | 1 | 15 min | 15 min |
| 2. Cleaning Output & Batch | 0 | — | — |
| 3. Text Box Detection & Interaction | 0 | — | — |
| 4. OCR Recognition & Text Editing | 0 | — | — |
| 5. Project Persistence, Image Ops & Export | 0 | — | — |
| 01 | 7 | - | - |
| 02 | 4 | - | - |
| 03 | 8 | - | - |

**Recent Trend:**

- Last 5 plans: 01-01 (15 min)
- Trend: baseline established

*Updated after each plan completion*
| Phase 01 P01 | 15 | 2 tasks | 29 files |
| Phase 01 P02 | 12 min | 2 tasks | 7 files |
| Phase 01 P03 | 39 min | 2 tasks | 29 files |
| Phase 01 P04 | 22 min | 2 tasks | 8 files |
| Phase 01 P05 | ~35 min | 2 tasks | 12 files |
| Phase 01 P06 | 12 min | 2 tasks | 4 files |
| Phase 01 P07 | 13 min | 3 tasks | 4 files |
| Phase 02 P01 | 5 min | 2 tasks | 2 files |
| Phase 02 P02 | 4 min | 2 tasks | 3 files |
| Phase 02 P03 | 7 min | 2 tasks | 3 files |
| Phase 02 P04 | 22 min | 3 tasks | 2 files |
| Phase 03 P01 | 10 min | 2 tasks | 7 files |
| Phase 03 P02 | 6 min | 1 tasks | 3 files |
| Phase 03 P03 | 10 min | 3 tasks | 3 files |
| Phase 03 P04 | 6 min | 2 tasks | 2 files |
| Phase 03 P05 | 18 min | 3 tasks | 3 files |
| Phase 03 P06 | 5 min | 2 tasks | 2 files |
| Phase 03 P07 | 12 min | 2 tasks | 4 files |
| Phase 03 P08 | ~22 min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 5-phase vertical-slice structure; Phase 1 adapts PanelCleaner (config, detection, inpainting, viewer) + MangaCleaner_GPU (interactive mask-editing canvas) as the foundation before building the novel text/box/OCR track.
- [Roadmap]: Packaging has no v1 requirement — deferred to a decimal-phase insertion or v1.1 once formalized.
- [Phase ?]: 01-01: ProfileManager.profile_to_config assigns current_profile directly (Config.from_config_updater needs a full config.ini with Saved Profiles, not a bare Profile.bundle_config())
- [Phase ?]: 01-01: create_app reuses existing QApplication singleton (avoids Qt singleton guard under pytest-qt / re-entry)
- [Phase ?]: 01-02: image_files natural-sorted in MainWindow._set_pages to match sidebar display order (index lookups depend on consistency)
- [Phase ?]: 01-02: FileTable uses QStandardItemModel + QListView (plan contracts QListView.ListMode, not QListWidget); drag-drop handled by sidebar only
- [Phase ?]: 01-03: TextDetector.__call__ returns VERIFIED 3-tuple (mask, mask_refined, blk_list) at inference.py:210, NOT the 5-tuple in CONTEXT/RESEARCH — orchestrator pattern-mapper correction is authoritative
- [Phase ?]: 01-03: vendored FULL comic_text_detector tree (incl models/yolov5 + utils/weight_init) because basemodel.py imports them — inference.py unimportable without them
- [Phase ?]: 01-04: mask_to_numpy_binary thresholds alpha>0 to a true binary 0/255 mask (not raw alpha 160) — the inpaint backend needs a crisp binary; the 160-alpha overlay is a display concern
- [Phase ?]: 01-04: QActionGroup tool_changed wired via action.toggled(checked=True) not group.triggered — triggered misses programmatic setChecked (set_active_tool); toggled fires for both
- [Phase ?]: 01-04: QGraphicsView.mapToScene takes QPoint not QPointF (PySide6); _scene_pos helper converts via toPoint(); test events use mapFromScene for viewport coords landing at the desired scene pixel
- [Phase ?]: 01-04: Shift Brush<->Eraser modifier keyed off event.key()==Key_Shift not event.modifiers() — Qt delivers Shift KeyPress with modifiers()==NoModifier (pre-press state)
- [Phase ?]: 01-05: vendored inpainting.py MINIMALLY (InpaintingModel class only; batch inpaint_page deferred to Phase 2 FLOW-03) — interactive inpainting needs only load + __call__
- [Phase ?]: 01-05: compute_mask_bbox returns (x,y,w,h) not (x1,y1,x2,y2) — set_image_from_numpy unpacks bbox as (x,y,w,h) for region compositing
- [Phase ?]: 01-05: added has_mask_content() distinct from has_mask() for the Inpaint gate — running LaMa on an empty/transparent mask is a wasted model load; has_mask() stays True for initialized transparent masks (plan 03/04 semantic preserved)
- [Phase ?]: 01-05: every numpy<->QImage bridge enforces .copy() detachment (Pitfall 2; MangaCleaner_GPU main_window.py:245 is the buggy reference); test_inpaint_result_display_uses_copy is the regression guard
- [Phase ?]: 01-05: inpaint is non-destructive (no confirmation dialog); reversibility lives in the image-undo stack via history.push_image_action (plan 06 hook, no-op in Phase 1)
- [Phase ?]: 01-06: two logical stacks (MASK + IMAGE) not four — the 4 internal lists are the implementation of UI-SPEC surface 8's 2-stack contract; preserve the MangaCleaner_GPU shape, not a 4-stack interpretation
- [Phase ?]: 01-06: undo bypasses mask_modified — apply_undo_mask refreshes the pixmap directly without emitting the push signal, so undo never re-pushes onto the stack (test_undo_does_not_repush regression guard)
- [Phase ?]: 01-06: full QImage/mask snapshots per entry in Phase 1 (RESEARCH Open Question 3); default limit=20 caps total snapshot memory (T-01-16)
- [Phase ?]: 01-06: image undo swaps the CURRENT image's region into redo on pop (MangaCleaner_GPU history.py:593-595 pattern) — a redo reverses the undo with the captured post-edit region
- [Phase 01]: CR-03 fix: _on_inpaint_finished now slices pre_inpaint[y:y+h, x:x+w].copy() (Pitfall-2 discipline) before pushing to history; the pushed patch is bbox-shaped (not the full image); bare except Exception: pass removed (WR-05 closed). Test widened to use REAL HistoryManager + assert patch.shape[:2] == (bbox_h, bbox_w).
- [Phase 01]: Gap-closure discipline (plan 01-07): regression tests MUST exercise the REAL vendored function on the buggy site (no monkeypatch) so arity/arg-type/shape bugs surface in CI; only the propagation-guard test patches, and only to assert the error propagates. Both resolver excepts narrowed to (FileNotFoundError, OSError); TypeError/AttributeError propagate (T-01-17).
- [Phase ?]: PNG stores DPI as integer pixels-per-meter, so 300 DPI round-trips to 299.9994 — assert within 1 DPI in test_preserves_dpi_mode, not exact equality (02-01)
- [Phase ?]: Use filecmp.cmp (not nonexistent shutil.cmp) for byte comparison in passthrough test (02-01)
- [Phase ?]: core/image_io.py is pure stdlib+numpy+PIL (no Qt/torch) so it is thread-safe and unit-testable headless — adapted from PanelCleaner save_optimized under GPL v3 D-12 (02-01)
- [Phase ?]: 02-02: OUTGOING page index read from stored _last_page_index field (NOT _current_page_index()) because _set_pages calls select_path BEFORE on_page_selected — select_path mutates current_path before the seam runs (PATTERNS file 4a)
- [Phase ?]: 02-02: Boundary .copy() at BOTH the OUTGOING save (canvas.get_mask().copy()) and INCOMING restore (image_file.mask.copy()) — belt-and-suspenders with set_mask's internal copy; OUTGOING is load-bearing, asserted by test_mask_persistence_uses_copy (T-02-04)
- [Phase ?]: 02-02: has_mask_content reuses mask_to_numpy_binary (lazy import inside method) — no hand-rolled alpha scan; mirrors canvas.has_mask_content but operates on the persisted ImageFile.mask slot
- [Phase ?]: 02-02: T-02-05 write/write race mitigation (disable page-switch while _op_running) deferred to Plan 04 — touches file_table interaction which is not in this plan's files_modified; code comment flags the deferral in on_page_selected
- [Phase ?]: 02-03: batch name guard written as idiomatic negated form (if cleaned_dir.name != 'cleaned': raise ValueError) rather than the plan's literal == assert; same behavior, verified by test_output_to_cleaned_subdir's ValueError on 'not_cleaned'
- [Phase ?]: 02-03: D-03 re-reads the page image a second time (cv2.imdecode path) in clean/detect_and_clean mode for the inpaint RGB contract — detect discarded its BGR after persisting the mask; re-reading keeps detect-only mode free of the RGB conversion and each per-page body self-contained
- [Phase ?]: 02-03: three entry points over one _run_batch_task loop (D-05); models load ONCE in the wrappers (Pitfall 3), abort checked at loop top ONLY (D-09/Pitfall 4), D-03 empty-mask gate via ImageFile.has_mask_content -> passthrough_original; progress_callback/abort_flag are the last two kwargs with None defaults to match Worker auto-injection
- [Phase ?]: 02-04: Bug D (canvas mask lost on batch dispatch) was a cross-plan INTEGRATION defect in the DISPATCH layer (main_window._dispatch_batch), not batch_runner — the canvas mask was never flushed to ImageFile.mask before the worker started. Fix = _flush_current_canvas_mask_to_data_model mirroring on_page_selected step 1.
- [Phase ?]: 02-04: Bug D1 (detect-only batch current-page canvas desync + erasure cascade on backwards navigation) was a canvas/data-model DESYNC from an unconditional refresh — _refresh_current_page_after_batch cleared the canvas overlay even for detect-only batches (no cleaned output), so the next navigation snapshotted the empty canvas back via on_page_selected step 1. Fix = mode-aware refresh (detect restores mask via D-11 step-4 pattern; clean reloads+clears). The D-11 seam (Plan 02-02) was correct throughout and never touched.
- [Phase ?]: 02-04: _batch_mode/_batch_cancelled distinct from _batch_active — _batch_active gates Cancel enablement; _batch_mode routes mode-aware post-batch refresh; _batch_cancelled disambiguates cancel status text. Progress handler mode-aware ('Detecting' vs 'Cleaning', Bug A).
- [Phase ?]: 03-01: rewrote all 5 pcleaner. refs in vendored structures.py to panelcleaner. (4 imports + the pcleaner.data body ref at the dead PageData.visualize font_path call) — D-12 discipline requires the qualified name match the vendored module so the file is self-consistent
- [Phase ?]: 03-01: deferred PageBox import in image_file.py via TYPE_CHECKING (boxes field is a forward-ref string under from __future__ import annotations) — strictly safer than the plan's suggested direct import, avoids any import-ordering sensitivity in the GUI layer
- [Phase ?]: 03-02: monotonic _seq integer counter for stamps, NOT wall-clock (Pitfall 4)
- [Phase ?]: 03-02: BOXES is ONE logical stack — op-type in record metadata, not per-op-type lists (D-10 anti-pattern avoided)
- [Phase ?]: 03-02: shape-agnostic _materialize_snapshot helper — BOXES stack generic over snapshot arity; (stamp,value) widen is fully internal so test_history.py passes unchanged
- [Phase ?]: 03-03: BoxItem + corner handles are PARENT-LESS scene items (not children of box_layer) — parenting under a QGraphicsItemGroup blocks Qt setSelected on the child; UI-SPEC 11 allows the parent-less-item-set form. box_layer stays as the visibility sentinel.
- [Phase ?]: 03-03: itemChange(ItemSelectedChange) applies origin pen/brush + handle visibility directly against the prospective value (flag not flipped yet) via _apply_look_for/_sync_handles_for_state
- [Phase ?]: 03-03: resize clamps during the drag (opposite corner held fixed, moving edge pinned at anchor+/-MIN_BOX_SIZE) so the box never inverts/collapses mid-drag; 8x8 min re-applied on release
- [Phase ?]: 03-03: Task 3 checkpoint auto-approved under auto_advance + human_verify_mode=end-of-phase (visual feel deferred to end-of-phase gate; not package-legitimacy blocking-human)
- [Phase ?]: 03-04: D-04 gate fires on box_origin_counts()[0] >= 1 (>= 1 DETECTED box) — user-only layer is not a replace scenario; matches UI-SPEC '>= 1 detected box' wording
- [Phase ?]: 03-04: V5 clamp builds a fresh @frozen Box per-edge (min(max(coord,0),img_w/img_h)); zero-area post-clamp dropped with loguru debug (model xyxy untrusted, T-03-06)
- [Phase ?]: 03-04: Task 2 checkpoint auto-approved under auto_advance + end-of-phase verify mode (visual detection quality deferred to end-of-phase gate; not package-legitimacy blocking-human)
- [Phase ?]: 03-05: boxes-save reads OUTGOING index from _last_page_index (reused from Phase 2 mask seam) — same lesson applies (select_path mutates current_path before on_page_selected runs)
- [Phase ?]: 03-05: Step 4b ALWAYS calls set_boxes (even empty) — boxes not tied to image dims, so stale boxes must be cleared when incoming page has none (unlike mask which set_image_from_path re-sizes)
- [Phase ?]: 03-05: Surface 13 undo collapse — unified on_undo/on_redo pop merged MASK/IMAGE/BOXES timeline via history.undo/redo and route (kind, value) -> apply_undo_{mask,image,boxes}; toolbar/menu 4->2; Alt+Z removed; orphaned strings fixed to Ctrl+Z
- [Phase ?]: 03-06: BOTH CornerHandle.shape() AND CornerHandle.boundingRect() must be overridden to enlarge the hit area — shape() alone is filtered out by itemAt's coarse boundingRect first-pass (probe-confirmed); boundingRect does NOT change the painted 8x8 handle (paint draws rect()). Visible handle stays 8x8 (UI-SPEC 12b preserved).
- [Phase ?]: 03-07: detection is a NON-undoable baseline (Gap 3) — removed the explicit push_boxes_state(pre_detection_snapshot) at _build_detected_boxes Step 5; the Step 3 _suppress_boxes_push guard already suppresses the set_boxes emission, so detection produces NO boxes stack entry. A live probe confirmed Gap 4 (moved-position persistence) was a misdiagnosis — the read path already works; no production fix needed. WR-04 closed via move/resize delta-checks (create exempt per WARNING 5).
- [Phase ?]: 03-08: mask push hook now pushes the BEFORE-state per stroke (tracked via self._pre_stroke_mask, defaulting to a clean baseline for the first stroke of a per-page session) — closes the one-behind defect (UAT test 3 addendum / FLOW-02 regression). A live probe proved the plan's literal Option 2 (seed [clean, after-state]) does NOT work: pop_mask_undo returns the stack TOP (the after-state), so applying it is a no-op — the correct fix pushes the BEFORE-state so the stack top at undo-time IS the state to restore to. Mirrors the IMAGE pre-edit push contract + plan 03-07's BOXES before-state discipline. WR-01 closed via null-current guards on all 4 per-type pops (pop_mask/image_undo/redo skip the redo-stash when current is None). Also found: the single-point _painted_mask draws zero opaque pixels on PySide6 6.x (false-pass generator) — new _opaque_stroked_mask/_paint_brush_stroke helpers use a real two-point segment.

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- [Phase 1]: ~~Validate PyTorch + PySide6 + simple_lama_inpainting coexistence on day one~~ — RESOLVED by source verification (2026-07-12): PanelCleaner's `requirements.txt` proves the full PyTorch stack (torch + PySide6 + manga_ocr + simple_lama + opencv + numpy) coexists in one env. Remaining open question is the frontend↔backend **subprocess/IPC boundary** (D-07/D-08), not dependency coexistence.
- [Phase 1]: Design model adapter interface to allow optional MangaCleaner_GPU ONNX models as user-installed modules (future enhancement).
- [Licensing]: Project is GPL v3 (derivative of PanelCleaner) — must preserve GPL v3 in all distributions and provide source code.
- [Phase 2 follow-up]: Deliberately re-verify `cleaned/` output quality before Phase 02 is considered fully shipped. The 02-04 smoke-test spot-check (check #3) passed, but the user wants a deliberate re-confirmation. Specifically: (1) outputs are visually clean (text removed, artwork restored); (2) no-text pages are byte-identical to their source (the D-03 copy2 passthrough is not silently re-encoding via PIL); (3) files are written ONLY into `cleaned/` and never into the source chapter folder. Logged from plan 02-04 completion (2026-07-25).

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Distribution | Packaging / PyInstaller + model distribution (no v1 REQ-ID) | Tracked in ROADMAP Notes | Roadmap creation |

## Session Continuity

Last session: 2026-08-05T05:11:21.651Z
Stopped at: Phase 4 UI-SPEC approved
Resume file: .planning/phases/04-ocr-recognition-text-editing/04-UI-SPEC.md

> **Pause note (2026-07-21, updated):** All 6 implementation waves complete and committed (110/110 tests green; all 8 requirements CLEAN-01..06 + FLOW-01..02 done). Paused by user request BEFORE the post-execution phase — code-review gate, gsd-verifier goal-check, and formal `phase.complete` have NOT yet run. The executor's tracking writes (STATE/ROADMAP/REQUIREMENTS marking 6/6 plans) reflect plan completion, but the phase is not yet GSD-verified. Next: `/gsd-execute-phase 1` resumes into post-execution (code-review → verify_phase_goal via gsd-verifier subagent → update_roadmap → routing). Expected cost: ~1 subagent spawn (verifier) + orchestrator bookkeeping, similar to one moderate wave.

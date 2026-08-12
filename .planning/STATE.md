---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
current_phase: 07
status: completed
stopped_at: Phase 7 UI-SPEC approved
last_updated: "2026-08-12T05:25:06.044Z"
last_activity: 2026-08-12
last_activity_desc: Phase 07 complete
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 59
  completed_plans: 59
current_phase_name: "Typesetting (TRAN-02): render translated text into the page"
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-11)

**Core value:** One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR, and lay out translation text — instead of switching between PanelCleaner, mokuro, and an image editor.
**Current focus:** Phase 07 — Typesetting (TRAN-02): render translated text into the page

## Current Position

Phase: 07
Plan: Not started
Status: All phases complete
Last activity: 2026-08-12 — Phase 07 complete

Progress: [██████████] 100% (4/4 phases, 29/29 plans)

## Performance Metrics

**Velocity:**

- Total plans completed: 60
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
| 04 | 10 | - | - |
| 5 | 10 | - | - |
| 6 | 8 | - | - |
| 07 | 12 | - | - |

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
| Phase 04 P01 | 18 min | 2 tasks | 6 files |
| Phase 04 P02 | 5 min | 2 tasks | 4 files |
| Phase 04 P03 | 7 min | 2 tasks | 6 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 04 P04 | 17 min | 2 tasks | 6 files |
| Phase 04 P05 | 497 | 2 tasks | 4 files |
| Phase 04 P06 | 13 | 2 tasks | 3 files |
| Phase 04 P07 | 7 | 2 tasks | 3 files |
| Phase 04 P08 | 6 | 2 tasks | 4 files |
| Phase 04 P09 | 11 | 3 tasks | 6 files |
| Phase 04 P10 | 12 | 2 tasks | 5 files |
| Phase 05 P01 | 10 | 3 tasks | 4 files |
| Phase 05-project-persistence-image-ops-export P05-02 | 25 | 3 tasks | 2 files |
| Phase 05 P03 | 45m | 2 tasks | 2 files |
| Phase 05 P03 | 30m | 2 tasks | 2 files |
| Phase 05-project-persistence-image-ops-export P05-09 | 12 | 2 tasks | 1 files |
| Phase 05 P04 | 14 | 2 tasks | 4 files |
| Phase 05-project-persistence-image-ops-export P05 | 110 | 3 tasks | 5 files |
| Phase 05 P05-06 | 42 | 3 tasks | 8 files |
| Phase 05-project-persistence-image-ops-export P05-07 | 28min | 3 tasks | 8 files |
| Phase 05-project-persistence-image-ops-export P05-08 | 55min | 2 tasks | 2 files |
| Phase 05-project-persistence-image-ops-export P10 | 8min | 2 tasks | 2 files |
| Phase 06 P01 | 4 | 2 tasks | 2 files |
| Phase 06 P02 | 15min | 2 tasks | 3 files |
| Phase 06 P03 | 6min | 2 tasks | 7 files |
| Phase 06 P04 | 47 | 3 tasks | 2 files |
| Phase 06 P05 | 25 | 2 tasks | 5 files |
| Phase 06 P06 | 14 | 2 tasks | 3 files |
| Phase 06 P07 | 6 min | 2 tasks | 2 files |
| Phase 06 P08 | 11 min | 2 tasks | 2 files |

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
- [Phase ?]: 04-01: PageBox.copy uses dataclasses.replace + copy.copy(payload) (shallow TextBlock copy sufficient for Phase 4 top-level .text/.translation per RESEARCH A3; @frozen Box shares by reference per D-10) — closes Pitfall 8 payload aliasing
- [Phase ?]: 04-01: centralized payload-None guard in private _ensure_payload() so Inspector + inline-editor manual edits on never-OCR'd user boxes are safe (checker W1); set_recognized_text_edited is the single manual-edit entry point Plans 04/05 call
- [Phase ?]: 04-02: translation parser treats Page-marker lines as structural (skipped silently, not counted) while SFX + malformed lines count as skipped; apply_translations first-box-wins per bubble_no; None-bubble boxes never candidates; parser never raises (ASVS V5/V7, T-4-03)
- [Phase ?]: 04-02: reading_order column tolerance = median inter-center-x gap floored to 40px (RESEARCH Pattern 4 gap-based default, not median-box-width A2); assign_bubble_numbers reads box.box.center; manual_override boxes keep bubble_no + flag (D-16 preserve-manual, T-4-04)
- [Phase ?]: 04-03: vendored MangaOcr singleton wrapper near-verbatim into panelcleaner/ocr/ocr_mangaocr.py (pcleaner.→panelcleaner. re-path, GPL v3 preserved); kept langs() staticmethod as designed-in D-14 hook
- [Phase ?]: 04-03: TorchOCRModel mirrors TorchLamaModel (lazy load, numpy→PIL recognize via Image.fromarray mode='RGB', str return, Model-not-loaded guard); load() does NOT validate model_path as file because manga-ocr resolves from HF cache via initialize_model() — GUI worker cache-checks via is_ocr_downloaded() (Plan 06)
- [Phase ?]: 04-03: backend_factory('ocr','torch')→TorchOCRModel resolved (stub removed); onnx branch raises NotImplementedError (D-14 designed-in hook); from manga_ocr import kept at vendored module top because the wrapper is itself lazy-imported by TorchOCRModel.load (D-07)
- [Phase ?]: 04-04: BoxItem text overlay is a QGraphicsTextItem CHILD of the BoxItem (inherits box visibility) — D-12 three-layer contract falls out naturally (Shift+M hides whole box incl text via setVisible; T hides ONLY the text child via its own _text_overlay_visible flag); outlined text via single-API QTextCharFormat.setTextOutline+setForeground merged over the Document (RESEARCH Pattern 3, no multi-pass QPainter)
- [Phase ?]: 04-04: InspectorPanel is a pure FOLLOWER (subscribes to scene.selectionChanged; commits route through MainWindow callbacks; never mutates a PageBox directly); recognized commits go through set_recognized_text_edited (Plan 01 setter, D-04 edited=True) NOT set_recognized_text/direct payload.text write; bubble # bounded 1..9999 (T-4-08) + sets manual_override=True (D-16); Task 3 checkpoint auto-approved under auto_advance+end-of-phase verify mode
- [Phase ?]: 04-05: InlineEditor commit captures the CR-01 before-snapshot and detaches each payload via copy.copy BEFORE the in-place setter mutation — _materialize_snapshot copies at push-time (after the mutation); without the detach, undo would restore the post-edit text (Pitfall 8 push-side, avoided where the 04-04 Inspector path still has the latent aliasing — deferred)
- [Phase ?]: 04-06: OCR dispatcher (Worker + _op_running) mirrors detect_text verbatim; single-box indeterminate progress, OCR All determinate 0..100 with 'OCR All… {done}/{total} · box N' status
- [Phase ?]: 04-06: box lookup across the worker boundary via id(frozen Box)/id(PageBox) identity (same object both sides) — no Qt object crosses into the worker (Pitfall 3)
- [Phase ?]: 04-06: OCR All dispatches over text-empty boxes only (plan action recipe); D-04 batch gate fires on edited-box count with UI-SPEC copy verbatim (plan artifact: copy implies overwrite, dispatch is fill-only)
- [Phase ?]: 04-06: OCR before-snapshot payloads detached via copy.copy before the setter mutation (Pitfall 8 push-side, the 04-05 pattern applied to the new OCR write path)
- [Phase ?]: 04-07: LoadTranslationsDialog is a PURE COLLECTOR (RESEARCH Pitfall 3): _on_apply stores (text, page_index) and accept()s; the MainWindow runs parse_translations + apply_translations, refreshes overlays/badges, and pushes ONE batch BOXES snapshot (UI-SPEC 20)
- [Phase ?]: 04-07: non-current-page translation applies target ImageFile.boxes in place WITHOUT a BOXES push — the undo stack is per-page (reset_history on page switch), so a cross-page snapshot would corrupt undo; the one-batch-entry contract is honored on the current page
- [Phase ?]: 04-07: parser-result report combines unmatched + skipped into ONE user-facing skipped total per the UI-SPEC copy shape; report page number is 1-indexed (matches status-bar Page {n} / {total})
- [Phase ?]: 04-07: _auto_number emits boxes_modified only when count > 0 (an all-manual-override page is a no-op edit — no empty undo entries); returns None per plan signature; status transient shows the actual count
- [Phase ?]: 04-07: Task 3 checkpoint auto-approved under auto_advance=true + human_verify_mode=end-of-phase (gate=blocking, NOT blocking-human/package-legitimacy) — the established project cadence; the 9 manual checks defer to the end-of-phase UAT gate
- [Phase ?]: 04-08: RC-1 fix is a setPos-only _reposition_text_overlay() called from _sync_handles (canvas syncs on EVERY mouseMoveEvent during a drag — a full document rebuild per mousemove would be wasteful)
- [Phase ?]: 04-08: RC-2/RC-3 apply on the single canvas zoom_changed slot — _on_zoom_changed_reposition_handles now forwards its (previously discarded) zoom to item.apply_overlay_zoom(zoom); covers wheel (820) / zoom_reset (827) / fit_to_window (851), the app default on every page load
- [Phase ?]: 04-08: section-16 clamp scales the SCENE font (clamp(14*zoom,10,28)/zoom scene px) instead of the ItemIgnoresTransformations fallback — same rendered [10,28] viewport-px contract, overlay stays a normal zoom-scaling child
- [Phase ?]: 04-08: the 2px overlay outline is reinterpreted as VIEWPORT-px (2/zoom scene px) — scene-px renders a sub-pixel halo below 100% (0 dark px at 0.25 zoom, measured); documented as a spec deviation note in 04-UI-SPEC.md; UAT test-1 legibility truth is the acceptance contract
- [Phase ?]: The [10,28] viewport-px clamp bounds the box-adaptive BASE (14 x min(box_w, box_h)/100 vp); the RENDERED font may go below 10 vp down to the 5 vp floor via the bounded shrink-to-fit loop (plan 04-09, the plan's intentional contract change).
- [Phase ?]: Overlay fit-in-box tests use platform-robust texts: Test A 'word ' x 59 + 'word' (Qt trims trailing whitespace at line ends) and Test E 'hello world' (wraps at 40pt on this platform; 'hello' would not — glyph metrics are narrower than the plan-reference platform). Assertions stay range-based.
- [Phase ?]: Recent Files + Batch are standalone QMenu(title, self) children, never menuBar().addMenu(): the menubar-factory path leaves their menuActions in the top-level action list (Qt does not remove the action when addMenu re-parents a QMenu) — tests assert action-list membership, not parent().
- [Phase ?]: Toolbar swap is a pure action swap (action_open_folder replaces action_open_image): _refresh_action_states gates neither open action and no icons are set, so the toolbar renders the text label exactly as before.
- [Phase ?]: 04-10: badge digit-fit uses MEASURED digit geometry (this platform: 9.45x19 px/digit -> badges 17.45x23/26.9x23/36.36x23; the plan-probe 16x19/24x23/40x23 does not reproduce on this Qt/font stack) — tests derive expectations from the measured rect per the plan's NOTE; the plan's probe values remain docstring references
- [Phase ?]: 04-10: Gap A carries 7 test cases (not 6) — the platform-robust placement tests cannot encode the fixed-size bug as hard-coded positions, so a separate cross-size ordering test (test_badge_tl_outside_tracks_size_across_digits) carries the RED gate; suite is 461 passed (451 + 10), a strict superset of the plan's 460
- [Phase ?]: 04-10: 0 is the UNSET bubble sentinel (spinbox 0..9999 + setSpecialValueText em dash; load_box None->0; clear() resets 0; WR-01 guard unchanged); _on_inspector_bubble_committed maps 0 -> bubble_no=None + manual_override=False, 1..9999 -> assign + pin (D-16) — the model only ever receives None or 1..9999 (T-4-08 unchanged)
- [Phase ?]: Container: custom header (magic MAS\x00 + version + entry count) + per-entry name_len u16/data_len u64 table, each payload LZMA2-compressed with FORMAT_XZ preset 6 (locked D-04; preset 9's ~800 MiB overhead rejected per RESEARCH A6)
- [Phase ?]: Decompression bounded per entry at 512 MiB (MAX_ENTRY_DECOMPRESSED) with LZMAError->ProjectFormatError; header+entry-table unpack fully wrapped so no raw struct.error/IndexError escapes (T-05-01)
- [Phase ?]: load_page_file and load_project reject format versions != 1 as ProjectFormatError (the newer-version corrupt-file copy, RESEARCH A9)
- [Phase ?]: Manifest written plain UTF-8 JSON (ensure_ascii=False, indent=2) — human-readable + diffable per D-04; non-ASCII chapter names round-trip literally
- [Phase ?]: PNG encode delegates to core/image_io.save_image_bytes (single source of truth) instead of duplicating PIL code in project_io
- [Phase ?]: test_save_is_atomic fails os.replace on the 3rd call (after manifest + first page succeed) — proves the per-file temp+replace scheme never corrupts any target
- [Phase ?]: Image ops core: crop geometry translated into POST-crop page coordinates (bbox + lines stay in one frame; TextBlock.xyxy == Box.as_tuple invariant)
- [Phase ?]: levels_lut normalizes [min(black,white), max(black,white)] so white<=black can never render an inverted map (T-05-07; black==white degenerates to a monotone threshold)
- [Phase ?]: ExportPage dataclass (path/boxes/img_w/img_h/geometry_altered) is the batch_export_ocr input shape - model-free projection so the exporter stays pure and 05-08 builds it from boxes_snapshot() + canvas dims
- [Phase ?]: _ocr.json writes are atomic (temp file + os.replace in same dir) - a crash never leaves a half-written published-contract file
- [Phase ?]: Abort is lazy-imported inside batch_export_ocr (function body) to keep the module-top import graph Qt-free while preserving the exact worker_thread exception identity
- [Phase ?]: img_w/img_h validated strictly as int (ValueError on non-int, T-05-02) - silent float truncation would export coordinates that lie about the current page state
- [Phase ?]: 05-09: The 1px move shortfall is a TEST-side sub-pixel truncation artifact (PySide6 QTest/mapFromScene int viewport delivery at fractional fit scale 0.18333) — NOT a canvas defect; canvas.py:1013-1025 applies the delivered delta exactly; no production code changed
- [Phase ?]: 05-09: Truncation-tolerant assertions anchor on the DELIVERED move position (moved_now): ~50px within 45..50 band + axis-symmetric + 60x60 shape + persisted == moved_now exactly — a pos()-divergence defect (delta 0) still fails; regression value preserved (T-05-21)
- [Phase ?]: 05-09: Post-fix full-suite baseline re-measured: 493 collected / 493 passed, 0 failed (suite grew past the plan-time 462 — strict superset of the 462/462 target)
- [Phase ?]: Geometry-op undo record: push_geometry_state stamps IMAGE+MASK+BOXES with ONE monotonic stamp; undo()/redo() pop every store whose tail stamp equals the max and return list[(kind, value)] ([] when empty, was None) — one Ctrl+Z reverses the whole op (PROJ-04, UI-SPEC surface 28)
- [Phase ?]: Group stash stamp: the 6 per-type pop methods gain an additive optional stash_stamp param (default None = byte-identical Phase 3 behavior); a multi-store pop stashes all popped stores with ONE fresh shared stamp so redo() restores the whole op in one press (test_geometry_redo_restores_all_three)
- [Phase ?]: Undo/Redo flash op-name resolution is MainWindow-side: _record_geometry_op_name(op_name) is the hook plan 05-06/05-07 _apply_geometry_op calls before push_geometry_state; multi-kind pop flashes the recorded name, single-kind pops keep the Phase 3 kind labels (levels undo flashes inpaint until 05-06 wires it)
- [Phase ?]: closeEvent gates only spontaneous (window-manager) closes; the Quit action runs the Unsaved Changes gate in _on_quit before its programmatic close() — D-07 prompt coverage preserved (X/Alt+F4/Quit/Open*) while programmatic closes (host teardown) never re-prompt (05-05)
- [Phase ?]: Unsaved-Changes gate lives inside _load_project_session/_load_single_page_mas (shared by the Open Project… dialog, chapter-climb, and Recent Projects) so the D-07 gate runs once per action without double-prompting after Discard (05-05)
- [Phase ?]: Project session rebuild bypasses _set_pages: ImageFiles carry restored mask/boxes/current_image and the sidebar is populated directly — _set_pages would rebuild fresh ImageFiles and auto-load placeholder paths via set_image_from_path (05-05)
- [Phase ?]: Save-side per-page image source = cleaned → source path → embedded current_image (RESEARCH A3 + portable-project fallback): re-saving a project whose originals are missing embeds the last-known image instead of failing (05-05)
- [Phase ?]: 05-06: Dialogs store result_values (not 'result') — 'result' shadows QDialog.result(); LoadTranslationsDialog result_text/result_page_index precedent
- [Phase ?]: 05-06: transform_fn returns (image, mask_bin|None, boxes|None) — None means the op does NOT touch that layer; levels passes (img, None, None) so set_mask/set_boxes are skipped and the undo record is image-only
- [Phase ?]: 05-06: Show Original gating reads _last_page_index (the D-11 seam rule) with a bounds check, per the plan contract
- [Phase ?]: 05-06: Full-frame geometry patches at (0,0) with differing dims REPLACE the whole image on undo (canvas.apply_undo_image) — the T-01-15 clip assumes same-frame patches and truncated the pre-op frame; non-origin patches keep the clip
- [Phase ?]: 05-06: pop_image_undo/redo stash the FULL current image for dims-changing geometry records — the region slice would clip the redo stash and break one-press redo after rotate/resize
- [Phase ?]: G is a window-level QShortcut (the V/B/R/L/E pattern), NOT an action-level setShortcut — duplicate setShortcut triggers Qt's Ambiguous shortcut overload (CR-14).
- [Phase ?]: ToolsPanel.set_active_tool explicitly unchecks the other actions — blockSignals around setChecked swallows the QActionGroup's exclusive unchecking (Qt behavior), leaving the previous tool checked and active_tool() wrong.
- [Phase ?]: The dim-out 1px inset is a moat (page minus crop inflated 1px each side); dim rects are clamped to the page so a crop hugging an edge dims nothing outside it.
- [Phase ?]: Crop geometry tests run at zoom_reset() so the scene<->viewport round trip is exact — the 05-09 truncation lesson applied as prevention.
- [Phase ?]: CropDialog stores result_values (the 05-06 precedent — result shadows QDialog.result()); apply-time re-validation compares against the PAGE bounds, not the spinbox ranges.
- [Phase ?]: Batch progress {done}/{total} is derived from the worker's (percent, name) emissions against a dispatched page count (_batch_ocr_total) — batch_export_ocr's D-10 signal shape carries percent, not a done count (05-08)
- [Phase ?]: Per-page batch-failure logging stays in batch_export_ocr (stems + error strings only, T-05-05) — _on_batch_ocr_export_finished is UI-only; single-source logging (05-08)
- [Phase 05-project-persistence-image-ops-export]: Zero-arg lambda wrapper (not functools.partial, not a _checked param) for action_open_project/action_save_project triggered wiring — PySide6 drops the emitted checked-bool for zero-arg callables; partial still injects it; a _checked param would contaminate the public dialog-driven path
- [Phase 05-project-persistence-image-ops-export]: Pre-create the default .mas-project folder before QFileDialog.getExistingDirectory; best-effort rmdir cleanup only for self-created empty folders — The native dialog refuses a non-existent default and silently falls back to the album root (D-02 violation)
- [Phase 06]: A1 composition order (per-channel LUT applied AFTER the master, out_c = channel_lut_c[master_lut[v]]) is pinned by a passing probe test, not prose - Task 2's probe passed immediately against the Task 1 implementation; no production change was needed. — A1 composition order (per-channel LUT applied AFTER the master, out_c = channel_lut_c[master_lut[v]]) is pinned by a passing probe test, not prose - Task 2's probe passed immediately against the Task 1 implementation; no production change was needed.
- [Phase 06]: Duplicate-x curve points dedupe LAST-WINS (A6): sorted dict pass keeps the final y per x - locked by test_curve_lut_duplicate_x_last_wins (lut[64] == 200). — Duplicate-x curve points dedupe LAST-WINS (A6): sorted dict pass keeps the final y per x - locked by test_curve_lut_duplicate_x_last_wins (lut[64] == 200).
- [Phase 06]: D-09 fix placed inside _set_image_from_numpy (shared impl), one call covers preview path idempotently — plan's verbatim prescription
- [Phase 06]: D-10 fix follows RESEARCH Option 1: six window tool actions made checkable + members of tools_panel.tool_group; no toggled connects on window actions (Pitfall 1); QToolButton mirrors its default action's checkable state — Group exclusivity + checkable actions is the Qt contract; button-side checkable alone is a no-op
- [Phase 06]: D-12 implemented via QFont().setPixelSize(14) (Assumption A4) - exact pixel contract; tests assert QFontInfo(font).pixelSize() == 14, never pointSize — A 14px font reports pointSize ~10.5, so pixelSize is the only exact assertion
- [Phase 06]: CurveWidget._points is assigned BY REFERENCE from _channel_points[current]; _refresh re-points the dict from the widget's list each pass so external reassignment can never desync the collector (06-04)
- [Phase 06]: points_changed fires on press-add / release (NOT per move pixel) - the T-06-06 preview-storm mitigation; the widget still repaints live during the drag (06-04)
- [Phase 06]: Gamma back-map snaps the diagonal to exactly 1.00 (raw 1.0054 rounds to 1.01) so the defaults contract 'gamma 1.00 <-> midpoint 128' holds at open; injection stays forward-only (user gamma edits) via _gamma_syncing (06-04)
- [Phase 06]: Endpoint cross-clamp enforced on the curve points themselves (not just the slider/spin pairs): a widget-dragged endpoint inversion clamps immediately - the exact T-05-07 mirror of the Levels slider clamp (06-04)
- [Phase 06]: In spinbox disabled for endpoints (x fixed at 0/255, range [x,x]) - 'endpoints never move horizontally' rendered in the numeric row (06-04)
- [Phase 06]: The preview callback receives the ALREADY-composed curves_page image (CurvesDialog._preview composes master->channel and fires the payload) - the slot passes it straight to the capture-suppressed preview path instead of recomposing (06-05) — The preview callback receives the ALREADY-composed curves_page image (CurvesDialog._preview composes master->channel and fires the payload) - the slot passes it straight to the capture-suppressed preview path instead of recomposing (06-05)
- [Phase 06]: PySide6 wrapper lifetime: hold the QMenuBar.actions() wrappers while resolving a top-level QMenu - temporary a.menu() wrappers GC-delete the C++ QMenu (06-05) — PySide6 wrapper lifetime: hold the QMenuBar.actions() wrappers while resolving a top-level QMenu - temporary a.menu() wrappers GC-delete the C++ QMenu (06-05)
- [Phase 06]: curves_dialog.py's four 'LevelsDialog' docstring references reworded to 'Levels dialog' (design-lineage context kept) to honor the zero-stale-reference acceptance gate (06-05) — curves_dialog.py's four 'LevelsDialog' docstring references reworded to 'Levels dialog' (design-lineage context kept) to honor the zero-stale-reference acceptance gate (06-05)
- [Phase 06]: The old Levels lifecycle tests fail between Task 1 (rename) and Task 2 (deletion) by design - the two-file verify is green only at Task 2 (06-05) — The old Levels lifecycle tests fail between Task 1 (rename) and Task 2 (deletion) by design - the two-file verify is green only at Task 2 (06-05)
- [Phase ?]: Cancel restore does NOT call canvas.rebaseline_original() (deliberate deviation from the review's '+ rebaseline_original()' suggestion): VERIFICATION truth 25 prescribes _original_image_numpy STAYS None on fresh pages, and a rebaseline on Cancel would clobber a legitimate pre-inpaint baseline on an already-baselined page. The honest D-14 baseline is established exclusively by _apply_geometry_op's tail rebaseline on Apply.
- [Phase ?]: IN-03 (Cancel leaves stale action enablement) needs no separate fix - moot: the canvas gate keeps _inpainted_qimage None through the whole preview+cancel lifecycle, so _refresh_action_states' has_inpaint gating is correct on every path (proven by Task 1 assertion (d)).
- [Phase 06]: WR-01 fix: the (0,0) full-frame gate, not recorded-name presence, scopes the op-name override — push_geometry_state stores geometry records as (0, 0, patch) (history_manager.py:435), so (x, y) == (0, 0) identifies the geometry-record shape; a stale _last_geometry_op_name must never leak into ordinary bbox inpaint undos — Single-entry image pops are ambiguous between a curves pop and an inpaint pop; the patch origin is the only reliable discriminator
- [Phase 06]: Ungroup, don't re-wire: the window actions keep their triggered->set_active_tool connections and stay checkable; the group-membership lines are removed and set_active_tool gains an explicit window-action sync loop BEFORE the existing toolbar loop - the group's exclusivity is no longer load-bearing for the toolbar — WR-02 fix: a 12-action mirrored exclusive group fought itself on dock clicks; the panel group holds exactly its own six actions, and set_active_tool drives the window actions explicitly
- [Phase 06]: No toggled connections on window actions (RESEARCH Pitfall 1): the panel already connects toggled at tools_panel.py:150; a double connection would double-emit tool_changed — Preserves the single tool_changed emission per selection across all entry paths

### Roadmap Evolution

- Phase 6 added: Refinement & Polish — deferred fixes (empty-state overlay, toolbar active-tool highlight, stale shortcut copy, dialog typography) + full curve editor (2026-08-09)
- Phase 7 added: Typesetting (TRAN-02) — render translated text into the page (2026-08-09)

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

Last session: 2026-08-11T02:12:55.694Z
Stopped at: Phase 7 UI-SPEC approved
Resume file: .planning/phases/07-typesetting-tran-02-render-translated-text-into-the-page/07-UI-SPEC.md

> **Pause note (2026-07-21, updated):** All 6 implementation waves complete and committed (110/110 tests green; all 8 requirements CLEAN-01..06 + FLOW-01..02 done). Paused by user request BEFORE the post-execution phase — code-review gate, gsd-verifier goal-check, and formal `phase.complete` have NOT yet run. The executor's tracking writes (STATE/ROADMAP/REQUIREMENTS marking 6/6 plans) reflect plan completion, but the phase is not yet GSD-verified. Next: `/gsd-execute-phase 1` resumes into post-execution (code-review → verify_phase_goal via gsd-verifier subagent → update_roadmap → routing). Expected cost: ~1 subagent spawn (verifier) + orchestrator bookkeeping, similar to one moderate wave.

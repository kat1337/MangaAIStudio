---
phase: quick-260907-sni
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/mask_planes.py
  - manga_ai_studio/core/mask_editor.py
  - manga_ai_studio/gui/canvas.py
  - manga_ai_studio/gui/main_window.py
  - tests/test_gui_mask_planes.py
  - tests/test_gui_canvas.py
autonomous: true
subsystem: gui-canvas + core-history
tags: [memory, oom, undo-history, allocation-churn, mask-planes, restore-tool]
requires:
  - "quick-260907-nfq landed (lazy ImageFiles, _materialize_page_state, source_mas) — must not be broken"
  - "08-02 three-plane mask model + plane-aware MASK history (MaskPlanesSnapshot on the MASK stack)"
provides:
  - "Packed MaskPlanesSnapshot: manual/erase stored as 1-bit packed arrays + dims — ~32x smaller history entries (F3)"
  - "Restore-stroke bbox-only display refresh — no full-frame QImage+QPixmap per mouse-move (F4, restore half)"
  - "recompose_mask per-plane binary cache — one-plane conversion per stroke commit (F5)"
affects:
  - "Session RAM climb: worst-case per-page mask history ~1 GB -> tens of MB; per-mouse-move churn ~12-30 MB -> bbox-sized"
estimate:
  tokens: 60000
  raw_tokens: 30000
  tasks: 3
  confidence: low
must_haves:
  truths:
    - "20 mask-history entries + redo stash on one ~35MP page retain packed-array bytes in the tens of MB (was ~2x ARGB32 planes per entry, ~5+ GB worst case) — asserted by packed-array byte math in tests, not RSS"
    - "Ctrl+Z after a stroke restores the exact pre-stroke composite; Ctrl+Shift+Z restores the post-stroke composite (round-trip pixel-equal)"
    - "A geometry op still undoes in ONE press across IMAGE+MASK+BOXES with the packed snapshot as the MASK value (shared-stamp group pop preserved; apply_undo_mask still hard-rejects bare QImages)"
    - "During a Restore stroke, consecutive mouse-move events reuse ONE display pixmap (object identity stable across moves; full-frame rebuild happens once at stroke start and once at finish); committed pixels still restore the baseline"
    - "A stroke-commit recompose converts at most the mutated plane(s) from QImage; an unmutated plane's binary comes from cache and the composite output is byte-identical to the uncached path"
    - "Lazy-open invariants intact: history entries only exist for visited/materialized pages (strokes only happen on the current page), and _materialize_page_state + the D-11 outgoing flush are untouched"
  artifacts:
    - "manga_ai_studio/core/mask_planes.py — MaskPlanesSnapshot with manual_packed/erase_packed np.ndarray fields + dims"
    - "manga_ai_studio/core/mask_editor.py — mask_qimage_to_packed / packed_to_mask_qimage boundary helpers"
    - "manga_ai_studio/gui/canvas.py — packed planes_snapshot + apply_undo_mask; persistent restore display pixmap with bbox refresh; per-plane binary cache in recompose_mask"
    - "manga_ai_studio/gui/main_window.py — zeros-packed _clean_plane_seed"
    - "tests/test_gui_mask_planes.py + tests/test_gui_canvas.py — new regression tests; full suite >= 1322 passed, 0 failed"
  key_links:
    - "canvas.planes_snapshot -> mask_qimage_to_packed -> HistoryManager MASK stack (duck-typed .copy()) -> apply_undo_mask -> unpack_binary + packed_to_mask_qimage -> set_planes"
    - "main_window._clean_plane_seed zeros-packed arrays -> first-stroke undo restores the clean baseline"
    - "canvas._restore_stamp bbox accumulator -> bbox-only QPainter draw into the persistent pixmap -> image_item.update()"
    - "plane-mutation sites (paint press/move, set_planes, clear/consume fills) -> cache invalidation -> recompose_mask cache reads"
---

<objective>
Kill the dominant RAM-climb terms of the OOM map (S1 history retention, S3 restore per-move churn, S2 recompose churn) on high-res (~35MP) projects: pack the mask-undo history snapshots 1-bit (32x smaller entries), stop the Restore tool rebuilding a full QImage+QPixmap per mouse-move, and cache per-plane binaries so stroke-commit recompose stops converting BOTH planes from scratch.

Purpose: a 25-page ~35MP project climbs ~6 GB -> ~18 GB during normal editing until OOM. The mapper's ranking puts plane-history retention (up to ~1 GB/page: 20 entries + redo stash of 2x ARGB32 planes) as the #1 climb term and per-event big-buffer churn (S2/S3) as the mechanism that ratchets the Windows heap toward the high-water mark. This plan takes the climb fixes only; the open baseline is already fixed by quick-260907-nfq.

Output: modified mask_planes/mask_editor/canvas/main_window + regression tests; full suite green at >= 1322 passed.
</objective>

<execution_context>
@C:\Users\Stella\.zcode\gsd-core\workflows\execute-plan.md
@C:\Users\Stella\.zcode\gsd-core\templates\summary.md
</execution_context>

<context>
@.planning/mapping/OOM-MEMORY-MAP.md
@.planning/quick/260907-nfq-lazy-project-open-stop-eagerly-decoding-/260907-nfq-SUMMARY.md
@.planning/STATE.md

@manga_ai_studio/core/mask_planes.py
@manga_ai_studio/core/mask_editor.py
@manga_ai_studio/core/history_manager.py
@manga_ai_studio/gui/canvas.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pack the mask history snapshots — manual/erase as 1-bit arrays in MaskPlanesSnapshot (F3/S1)</name>
  <files>manga_ai_studio/core/mask_planes.py, manga_ai_studio/core/mask_editor.py, manga_ai_studio/gui/canvas.py, manga_ai_studio/gui/main_window.py, tests/test_gui_mask_planes.py, tests/test_gui_canvas.py</files>
  <precondition>Full suite green at the post-nfq baseline (1322 passed) with the pinned interpreter before starting.</precondition>
  <behavior>
    - Snapshot representation: planes_snapshot() on a page with painted manual/erase content returns a MaskPlanesSnapshot whose manual_packed.nbytes == ceil(h*w/8) and erase_packed.nbytes == ceil(h*w/8) (small fixture, e.g. 40x30), plus dims == (h, w); the packed fields are np.ndarray uint8, not QImage.
    - Round-trip: stroke -> planes_snapshot() -> apply_undo_mask(snapshot) reproduces a composite pixel-equal (mask_to_numpy_binary equality) to the pre-stroke composite; auto plane content survives identically.
    - First-stroke seed: _clean_plane_seed() returns zeros-filled packed arrays of ceil(h*w/8) bytes with dims; undoing the first stroke yields a transparent manual+erase composite with the auto plane intact.
    - Redo stash: pop_mask_undo then pop_mask_redo round-trips to the post-stroke composite pixel-equal (the duck-typed .copy() contract with the new value type).
    - One-press geometry undo: push_geometry_state with the packed snapshot as the MASK value undoes IMAGE+MASK+BOXES in one Ctrl+Z (existing unified-pop tests re-based to the packed type, not deleted).
    - apply_undo_mask still raises TypeError on a bare QImage or any non-MaskPlanesSnapshot value (the hard-reject contract).
  </behavior>
  <action>
    RED first (commit test(...) before feat(...), pinned interpreter).

    1. mask_planes.py — redefine MaskPlanesSnapshot fields: manual_packed: np.ndarray, erase_packed: np.ndarray, auto_packed: np.ndarray | None = None, dims: tuple[int, int]. Replace the QImage fields entirely (the history value is the packed triple; ~HW/8 per plane vs 4HW ARGB32 — the ~32x retention win). copy() returns a new snapshot with .copy()-detached arrays (the duck-type HistoryManager relies on). Keep the module Qt-free at runtime (TYPE_CHECKING annotations pattern). Note in the docstring: representation is lossless for the planes because both are binary (alpha>0 == painted) — mask_to_numpy_binary already thresholds them.

    2. mask_editor.py — add the two Qt-side boundary helpers (this module already owns both converters and may import Qt):
       - mask_qimage_to_packed(qimg) = pack_binary(mask_to_numpy_binary(qimg)), importing pack_binary from core.mask_planes.
       - packed_to_mask_qimage(packed, dims) = numpy_binary_to_mask_qimage(unpack_binary(packed, dims[0], dims[1])). unpack_binary's ceil(h*w/8) length check stays the in-depth backstop (T-08-02).
       The rebuild lands as the MASK_PAINT_COLOR rgba(255,0,0,160) RGBA8888 plane — acceptable because every plane consumer thresholds alpha (mask_to_numpy_binary) and QPainter paints fine on RGBA8888; note this format nuance in the helper docstring.

    3. canvas.py — planes_snapshot(): keep the RuntimeError no-page guard; return MaskPlanesSnapshot(manual_packed=mask_qimage_to_packed(self._mask_manual), erase_packed=mask_qimage_to_packed(self._mask_erase), auto_packed=<unchanged pack_binary path>, dims=(h, w)). apply_undo_mask(): keep the isinstance hard-reject; rebuild manual/erase planes via packed_to_mask_qimage(snapshot.manual_packed, snapshot.dims) / (snapshot.erase_packed, snapshot.dims), keep the unpack_binary auto path, pass into set_planes unchanged (set_planes still .copy()-detaches — do not touch it).

    4. main_window.py — _clean_plane_seed(): build manual_packed/erase_packed as np.zeros(ceil(h*w/8), np.uint8) with dims from the current mask size (no QImage allocation at all); auto_packed path unchanged. Update the doc-level references.

    5. Migration sweep: grep manga_ai_studio/ and tests/ for attribute access on snapshot .manual/.erase (constructors and field reads) and migrate to the packed fields. Producers/consumers to check: main_window lines ~1676 and ~5332 (geometry push + _current_undo_state — opaque values, likely no change), tests/test_gui_mask_planes.py, tests/test_gui_gap_closure.py, tests/test_gui_boxes.py, tests/test_gui_project.py. The D-11 outgoing flush packs from canvas._mask_manual directly and the nfq _materialize_page_state never touches history — verify by inspection and leave untouched. history_manager.py needs NO code change (values are .copy()-duck-typed); update only the stale "(stamp, QImage)" docstring/type-comment mentions of the MASK stack.

    PRESERVED CONTRACTS (must hold): one-press multi-store geometry undo (shared stamp); redo stash restore; reset_history per page switch; the nfq lazy invariant that history records only exist for visited pages (strokes only fire on the current page — state this invariant in the apply_undo_mask docstring).
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_mask_planes.py tests/test_history.py tests/test_gui_canvas.py tests/test_gui_gap_closure.py -x -q</automated>
  </verify>
  <done>All listed suites pass including the new packed-snapshot behavior tests; snapshots expose packed uint8 arrays sized ceil(h*w/8) + dims; undo/redo and one-press geometry undo round-trip pixel-equal; no test constructs the old QImage-field snapshot.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Restore stroke display — one persistent pixmap, bbox-only per-move refresh (F4 restore half/S3)</name>
  <files>manga_ai_studio/gui/canvas.py, tests/test_gui_canvas.py</files>
  <behavior>
    - During a restore stroke (press -> N mouse-moves -> release), canvas.image_item.pixmap() is the SAME object before and after the moves (no per-move QPixmap.fromImage rebuild).
    - The full-frame rebuild helper runs exactly twice per stroke: once at stroke start (seeding the display from _restore_work) and once at _finish_restore_stroke; mouse-move events never call it.
    - Mid-stroke display correctness: one mouse-move stamps MANY interpolated discs (the _advance_paint step loop); the per-move bbox refresh must cover the union of ALL discs stamped during that move — asserted mid-stroke (between moves, BEFORE release) by sampling the persistent pixmap under an earlier disc of the same move and checking it already shows baseline pixels (a last-disc-only refresh leaves display gaps mid-stroke that post-stroke assertions cannot catch).
    - Restore semantics preserved: after the stroke, the pixmap pixels under the brushed disc equal the baseline (original) pixels, and restore_committed still emits ONCE with the correct bbox patch payload.
    - A defensive fallback: if the persistent pixmap slot is None when a move arrives, the code falls back to the full rebuild rather than crashing.
  </behavior>
  <action>
    RED first. All display-only changes — no stroke/commit/undo semantics.

    1. canvas.py — add a persistent slot self._restore_display_pixmap: QPixmap | None (None default). At the restore PRESS path (where _restore_pre/_restore_work are initialized): build the pixmap ONCE via the existing full-frame QImage(RGB888)+copy conversion of _restore_work into QPixmap.fromImage, store it in the slot, and image_item.setPixmap(slot) once.

    2. _advance_paint RESTORE branch: replace the per-move self._refresh_restore_display() with a bbox-only refresh. One mouse-move stamps MANY discs (the interpolation loop at ~1955-1965), so the refreshed rect MUST be the UNION of the rects of ALL discs stamped during THIS move — not the last disc alone. Implementation: record the stroke bbox accumulator value (or a fresh per-move rect) BEFORE the stamp loop and derive the move rect by diffing/unioning across the stamp calls (e.g., snapshot _restore_bbox before, union each stamped disc's rect into a per-move rect after) — a last-disc-only rect leaves mid-stroke display gaps between interpolated discs. Then convert that rect region of _restore_work to an RGB888 QImage — the slice work[y0:y1, x0:x1] is NON-CONTIGUOUS, so wrap np.ascontiguousarray(region) (the full-frame pattern QImage(arr.data, w, h, w*3, Format_RGB888) does NOT transfer to a strided sub-rect; per-row stride is the alternative, ascontiguousarray is simpler), QPainter-draw it at (x0, y0) into the persistent pixmap (QPainter on a QPixmap is legal here — mouse events are GUI-thread), then self.image_item.update() to re-blit. Do NOT call setPixmap per move.

    3. _finish_restore_stroke: keep the existing single full refresh (it lands the release-end state and re-syncs the item's pixmap), then clear the persistent slot alongside _restore_pre/_restore_work/_restore_bbox. Guard: bbox refresh with a None slot falls back to the full rebuild.

    4. Update the _refresh_restore_display docstring: the T-l3l-03 PERF CHOICE note is superseded — full-frame conversion is now once-per-stroke-boundary, per-move is bbox-only.

    Tests in tests/test_gui_canvas.py following the existing restore-stroke simulation pattern: identity assertion on image_item.pixmap() across moves; a monkeypatch counter asserting the full rebuild fires exactly 2x per press->move->release; a MID-STROKE assertion (after a long fast move that stamps multiple discs, before release) sampling the persistent pixmap under the FIRST disc of that move and checking baseline pixels are already displayed (catches last-disc-only refresh gaps); pixel sampling of the stroked region equals baseline after release; the None-slot fallback path does not raise.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_canvas.py tests/test_gui_tools_strip.py -x -q</automated>
  </verify>
  <done>Restore strokes keep one pixmap object across all mouse-moves; full-frame rebuild fires exactly at stroke start + finish; every disc stamped within a mouse-move is already visible mid-stroke (union-rect refresh, no inter-disc display gaps); committed pixels and the restore_committed payload are unchanged; listed suites green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: recompose_mask fast path — cached per-plane binaries (F5/S2 churn)</name>
  <files>manga_ai_studio/gui/canvas.py, tests/test_gui_mask_planes.py, tests/test_gui_canvas.py</files>
  <precondition>Task 1 landed (same file, canvas.py) — packed snapshot migration already merged so this task's diffs do not collide.</precondition>
  <behavior>
    - Composite equivalence: after any mutation sequence (stroke -> recompose -> second stroke -> recompose -> clear_mask -> stroke -> recompose, and the same through set_planes/undo restores and consume_mask_display), the composite is byte-identical (mask_to_numpy_binary equality) to a fresh uncached recompose from the same plane state.
    - Cache effectiveness: after a brush stroke commit that mutated ONLY the manual plane, the next recompose converts manual exactly once and erase ZERO times (monkeypatch call-count on mask_to_numpy_binary in the canvas module namespace).
    - Invalidation correctness: after set_planes (undo/page restore), clear_mask, or consume_mask_display fills, the next recompose converts BOTH planes (stale cache can never serve).
    - Cross-page replacement equivalence: stroke on page A (commit recompose) -> set_image page B (a folder-session-style page switch with NO set_planes — the incoming page has no persisted mask) -> stroke on page B -> recompose is byte-identical to a fresh uncached recompose of page B's planes. The outgoing page's cached binaries must never serve the new page (set_image re-seeds _mask_manual/_mask_erase, so a stale cache here silently poisons the composite, LaMa dispatch, and consume paths).
    - recompose_mask stays signal-silent (no mask_modified emission from the cache path).
  </behavior>
  <action>
    RED first. Pure derived-state caching — the composite formula (manual | auto) & ~erase and every call site stay identical.

    1. canvas.py — add self._plane_bin_cache: dict[str, np.ndarray] (keys "manual"/"erase", values (h,w) uint8 0/255) plus a small _invalidate_plane_bin_cache() helper that clears it. In recompose_mask: manual_bin = cache.get("manual") or mask_to_numpy_binary(self._mask_manual) stored back on miss; same for erase; auto path unchanged. Keep the existing null-manual early return.

    2. Invalidation call sites — EVERY place the manual/erase planes MUTATE or are REPLACED (enumerate by grepping BOTH QPainter/paint/fill writes AND direct assignments to _mask_manual/_mask_erase). Mutation sites: the brush/rect/lasso/eraser press and move paint paths (where mask_editor paint helpers and _dual_write_stroke run), set_planes (after the incoming copies land), clear_mask's transparent fills, and consume_mask_display's fills. REPLACEMENT sites (equally mandatory — a stale cache here survives until the next commit): set_image's fresh-plane re-seed (canvas.py ~502-510, runs on EVERY page display), clear()'s plane nulling (canvas.py ~554-557), and _set_image_from_numpy's dims-change re-seed branch (canvas.py ~1147-1158). CONCRETE FAILURE being guarded: a folder-session page switch runs set_image with NO set_planes (main_window on_page_selected Step 4 is skipped when the incoming page has no persisted mask), so the first stroke-commit recompose on the new page would serve the OUTGOING page's cached binaries — a silent wrong composite that also poisons LaMa dispatch and mask consumption. A missed site = stale composite corruption — the equivalence tests above (including the cross-page one) are the guard; when in doubt, invalidate (an extra invalidation only costs one rebuild).

    3. Do NOT wire planes_snapshot through the cache in this task (Task 1's snapshot path is independent and already merged); do NOT touch update_mask_display's per-move pixmap refresh (explicitly deferred — see Deferred list).

    Tests split across tests/test_gui_mask_planes.py (equivalence sequences) and tests/test_gui_canvas.py (call-count + invalidation-after-set_planes), using the existing stroke-simulation helpers.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_mask_planes.py tests/test_gui_canvas.py -x -q</automated>
  </verify>
  <done>Composites are byte-identical to the uncached path across all mutation sequences INCLUDING a set_image page switch with no set_planes (cross-page test); a manual-only stroke commit converts exactly one plane; every mutation AND replacement site (set_image, clear, _set_image_from_numpy dims branch) invalidates; listed suites green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| in-memory packed arrays -> unpack_binary | Snapshot arrays are process-internal (never persisted), but unpack_binary is also the shared guard used at the .mas persistence boundary |
| GUI-thread painter discipline | QPainter on QPixmap is only legal on the GUI thread; the restore refresh runs inside mouse events |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-sni-01 | Tampering | packed_to_mask_qimage / unpack_binary | low | mitigate | Snapshot dims + ceil(h*w/8) length validation retained (unpack_binary ValueError backstop); nothing new crosses persistence — the .mas loader keeps its own meta-dims cross-check |
| T-sni-02 | DoS | restore bbox QPainter path | low | accept | Painter use is confined to mouse-event (GUI-thread) code with clamped bbox rects (same clamps as _restore_stamp); a None-slot defensive fallback prevents null-deref |
</threat_model>

<verification>
- Task verifies run green with the pinned interpreter (AGENTS.md): "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest <files> -x -q. Never bare python/pytest.
- Full suite at the end of Task 3: "C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q — expect >= 1322 passed, 0 failed (strict superset of the post-nfq baseline).
- Byte-math spot check (no GUI launch): at 35MP, one history entry is now ~2 x ceil(HW/8) + ceil(HW/8) ≈ 13 MB (was ~280 MB of ARGB32 planes) — the must_haves byte-size tests encode this ratio at fixture scale.
</verification>

<success_criteria>
- Mask history entries hold packed 1-bit planes (~32x smaller); undo, redo, first-stroke seed, and one-press geometry undo all round-trip pixel-equal.
- Restore strokes allocate no full-frame QImage/QPixmap per mouse-move (one pixmap per stroke, bbox-only updates).
- Stroke-commit recompose converts only mutated planes; composites byte-identical to the uncached path.
- nfq lazy-open seams (_materialize_page_state, D-11 flush, source_mas) untouched and green.
- Full suite >= 1322 passed, 0 failed.
</success_criteria>

<deferred>
Named out of scope (mapper items deliberately NOT taken — do not silently absorb):
- F2: LRU eviction of decoded pixels for non-current pages (lower priority per task scope).
- F4's OTHER half: update_mask_display's per-move full QPixmap refresh on the brush path — pre-existing churn, not in this task's priority list.
- F6: vhh Save-As payload session double (np.array copy=True per eligible page).
- S4: per-page-switch original decode churn (u9m); S6: typeset effect surface budget; S7: model/allocator residency.
- F7: RSS/tracemalloc instrumentation (the nfq human-verification RSS spot-check covers measurement).
</deferred>

<output>
Create `.planning/quick/260907-sni-slim-mask-undo-history-snapshots-and-per/260907-sni-SUMMARY.md` when done
</output>

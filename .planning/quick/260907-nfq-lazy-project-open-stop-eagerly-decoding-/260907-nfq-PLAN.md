---
phase: quick-260907-nfq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - manga_ai_studio/core/project_io.py
  - manga_ai_studio/core/image_file.py
  - manga_ai_studio/gui/main_window.py
  - tests/test_core/test_project_io.py
  - tests/test_gui_project.py
  - tests/test_gui_batch.py
autonomous: true
requirements: [quick-260907-nfq]

estimate:
  tokens: 130000
  raw_tokens: 80000
  tasks: 3
  confidence: med

must_haves:
  truths:
    - Opening a project decodes pixels for ONLY the displayed first page: after `_load_project_session`, page 0 has `current_image` populated and every other page has `current_image is None` and `mask is None` while `boxes`, `source_mas`, `embedded_size`, `original_verified`, `geometry_altered` and all four packed-plane slots carry the meta-derived state — open-time retained pixel memory is O(1 pages), not O(page count) (fix direction F-lazy/F1 of OOM-MEMORY-MAP.md).
    - The first page still displays immediately at open with its embedded image, restored planes/composite, and boxes — the open display behavior is unchanged.
    - First navigation to a never-visited page materializes it from its source `.mas` (embedded pixels display, packed planes or legacy composite restore, boxes route) and is visually and behaviorally identical to the pre-lazy eager open; the placeholder path NEVER reaches `set_image_from_path` when materialization succeeds (the 05-05 rule).
    - Save never loses pixels: Save As… with ZERO page visits writes every page and reopening shows identical images, planes, and boxes; portable embedded-only projects (unverified originals, placeholder paths) round-trip via source-`.mas` extraction; a lazy page whose source `.mas` is missing/corrupt at save aborts the whole save via the existing WR-02 unresolved dialog instead of silently embedding different pixels.
    - Batch detect/clean dispatch on a project with never-visited pages light-materializes those pages' persisted mask planes (manual/erase stroke survival, legacy composite for box-less pages) WITHOUT materializing any page pixels.
    - Batch OCR export dims for lazy pages come from the embedded meta (`embedded_size`), staying exact for geometry-altered pages; batch typeset export renders lazy pages from their embedded pixels via the source-`.mas` extraction tier.
    - Boxes/flags/thumbnails stay eager at open; per-page undo history still resets on switch; the 260826-1by outgoing dims guards hold unchanged; the full suite is green under the pinned interpreter, including the intentionally rewritten eager-open test.
  artifacts:
    - manga_ai_studio/core/project_io.py (`load_page_file` gains selective `names` decompression; new `parse_page_meta`; `parse_page_entries` refactored to share its head)
    - manga_ai_studio/core/image_file.py (new `source_mas` + `embedded_size` slots; `current_image` docstring updated to the lazy contract)
    - manga_ai_studio/gui/main_window.py (module-level `_decode_embedded_image` + `_resolve_original_ref` extracted; `_build_lazy_image_file`; `_materialize_page_state`; meta-only `_load_project_session` loop with pre-swap page-0 materialization; `on_page_selected` materialize step; `_save_project` PREPARE materialization of eligible lazy pages; `_dispatch_batch` light tier; `_page_image_source` source-`.mas` tier; OCR-export `embedded_size` dims tier)
    - tests/test_core/test_project_io.py (selective-decompression + parse_page_meta battery, incl. the corrupt-unrequested-blob non-decompression probe)
    - tests/test_gui_project.py (lazy-open contract battery: rewritten eager test, visit materialization, zero-visit Save As round-trip, portable round-trip, unresolvable-save abort, incremental byte-fidelity, visit/undo bleed guard)
    - tests/test_gui_batch.py (batch light-materialization planes survival; OCR-export embedded dims; typeset embedded pixels)
  key_links:
    - The source_mas back-pointer is the single seam: the `_load_project_session` meta loop writes it, and `_materialize_page_state` (visit / batch dispatch / save PREPARE) plus `_page_image_source`'s extraction tier all consume it — no consumer re-derives the page file path
    - The on_page_selected Step 3 embedded branch consumes the just-materialized `current_image` verbatim — the visit path reuses the existing D-11 restore steps (has_mask_planes → set_planes, legacy composite → set_mask, boxes Step 4b) with zero new restore logic
    - The _page_image_source chain order is preserved — current_image (authoritative D-05 resume state) first, then the source-`.mas` embedded extraction, then `cleaned/<stem>`, then `path`, then None
    - The corruption gate is preserved: meta-only parse of ALL pages before the swap (malformed meta/boxes/original still abort the open) + full materialization of page 0 BEFORE the swap keeps the corrupt-first-page dialog and all-or-nothing for the displayed page
    - The save format is unchanged: full-tier materialization fills the composite mask for plane-carrying pages too, so a rewritten lazy page's `.mas` carries the same entry shape (image.png + mask.bin + 4 plane bins + meta.json + boxes) as today
---

# Quick Task 260907-nfq — Lazy project open: stop eagerly decoding every page

**User ask (paraphrased):** opening a 25-page HIGH-RES (~35 MP/page) project jumps to >6 GB RAM at open and OOM-crashes after work. Stop eagerly decoding every page's embedded image, mask, and planes at project load; materialize per-page pixels/masks/planes on demand (page visit, batch iteration, save). Re-reading files from disk lazily is explicitly acceptable ("the files ain't going anywhere").

**Scope guard:** OPEN baseline ONLY. History slimming (F3), per-stroke recompose churn (F2/F4/F5), save-payload slimming (F6), LRU eviction (F2), `_load_folder` `.mas`-page laziness, and thumbnail decode churn are OUT OF SCOPE (next tasks). This plan changes WHEN pixels are decoded, never WHAT is decoded or saved.

**Interpreter for ALL test runs (AGENTS.md):** `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest ...` — never bare `python`/`pytest`.

## Current behavior (evidence, file:line verified against the working tree)

1. `_load_project_session` (`manga_ai_studio/gui/main_window.py:3647`) loops EVERY page: `project_io.load_page_file` (LZMA-decompresses ALL entries, `project_io.py:148`) → `parse_page_entries` (`project_io.py:720`) → `_build_image_file_from_parsed` (`main_window.py:3437`). Build-before-swap: all pages fully built before the session swap (`main_window.py:3663-3675`).
2. `_build_image_file_from_parsed` decodes the embedded `image.png` into `current_image` for EVERY page (`main_window.py:3489-3491`, dims-cross-checked vs `meta.img` at :3510-3518 — "WR-06"), builds the flat composite `mask` as an RGBA8888 QImage = 4HW (`:3472`), and keeps the four packed plane blobs (`:3477-3480`). At ~35 MP/page: `current_image` ≈ 105 MB + composite ≈ 140 MB retained PER PAGE → 25 pages ≈ 6 GB. This is the reported OOM baseline (OOM-MEMORY-MAP.md §1, fix F1).
3. Only page 0 is displayed at open: `_display_page_state(page_files[0])` (`main_window.py:3688` → `:3521`) seeds the canvas from `imf.current_image` and restores planes at the embedded dims (the 08-07 seam).
4. Folder sessions are ALREADY lazy: `ImageFile(path, original_verified=True)` with `current_image=None`; pixels load on visit via `on_page_selected` (`main_window.py:2284`). Project sessions bypass `_set_pages` because a restored page's `path` may be a PLACEHOLDER (unverified original → the `.mas` file itself, `main_window.py:3464-3466`) — `set_image_from_path` on it must never auto-load (the 05-05 rule).
5. `on_page_selected` Step 3 (`main_window.py:2398-2438`): `if imf.current_image is not None` → display embedded via `set_image_from_numpy_page`; ELSE `set_image_from_path(path)` — a lazy project page would wrongly hit the second branch (displaying the PRISTINE original for verified pages, or the "Couldn't open file" dialog for placeholders).
6. Save (`_save_project`, `main_window.py:2902`): eligibility = dirty OR missing `<stem>.mas` (`_eligible_save_pages` :2882); `force_as` takes ALL pages. Per-page pixels resolve via `_page_image_source` (:2858): `current_image` → `cleaned/<stem>` → `path`. For a never-visited lazy page this falls through to the ORIGINAL on disk — silently embedding pristine pixels over the last-saved (possibly cleaned) state = the #1 pixel-loss risk. Portable pages (placeholder `path` = the `.mas` file) would `Image.open` a `.mas` → OSError → PREPARE's broad except → spurious save failure.
7. Batch (`_dispatch_batch`, `main_window.py:8185`) hands `list(self.image_files)` to the worker. `_run_batch_task` (`core/batch_runner.py:125`) reads `page.path` FROM DISK for pixels (never `current_image`) and `page.boxes` (eager), but for clean mode reads `page.mask_manual`/`page.mask_erase` packed planes (:306-318) and the legacy flat `page.mask` fallback (:322-341). Detect modes WRITE `page.mask` + `auto_mask`/`raw_detected_mask` (:268-274). So laziness must preserve plane/composite availability for never-visited pages, but must NOT materialize pixels.
8. `_dispatch_batch_ocr_export` (`main_window.py:7843`) projects per-page dims: current page from canvas → `imf.current_image.shape` (:7885) → PIL dims of `imf.path` (:7890). For a geometry-altered lazy page the PIL-original fallback reports the WRONG dims. `_dispatch_batch_typeset_export` (:8003) uses `_page_image_source(i)` for non-current pages — fixed free by the same extraction tier.
9. `_plane_dims_match` (`main_window.py:2222`) returns True when `imf.current_image is None` (unknown dims → legacy-preserving) — the outgoing D-11 flush only ever targets the DISPLAYED (materialized) page, so lazily-empty pages no-op cleanly by construction (260826-1by guards untouched).
10. Container format (`project_io.py`): header + per-entry `name_len u16 + data_len u64 + name + LZMA2 blob` table — selective decompression by entry name is a ~5-line change to `load_page_file` (`:148-188`); `parse_page_entries` requires `image.png` (:742-746) and runs `validate_meta` + mask/plane length cross-checks.
11. Test prior art: `tests/test_gui_project.py` has `_make_pages` (:35), `_make_window` (:46), `_save_as` (:109) with `_wait_save_done` (:98), `_open_three_page_session` (:1321 — FOLDER session, stays eager, so all existing incremental/resurrection save tests are unaffected by project-open laziness), and `test_open_project_populates_all_current_images` (:405) which pins the EAGER contract and must be rewritten to the lazy contract. `tests/test_gui_batch.py:1052` shows the dispatch-capture pattern (stubbed task_fn asserting worker args). `tests/test_core/test_project_io.py` is the headless container battery.

## Design

**Meta-only open, gap-fill materialization, three seams.** The load loop parses ONLY `meta.json` + `original.json` per page (selective decompression — tiny entries, fast open, structural corruption gate intact). Each page becomes a lazy `ImageFile` carrying `source_mas` (back-pointer to its page container) + `embedded_size` (meta dims) + eager boxes/flags, with `current_image`/`mask`/plane slots `None`. A single gap-fill helper `_materialize_page_state(imf, idx, want_pixels)` re-reads the page container and fills ONLY still-`None` slots (never overwrites batch-written or canvas-flushed state), wired into three seams: page visit (full tier — pixels + mask state), batch dispatch (light tier — mask state only, no pixels), save PREPARE (full tier for eligible pages only). `_page_image_source` gains the source-`.mas` extraction tier so typeset export and any future consumer resolve lazy pixels; save format is byte-compatible because the full tier fills the composite mask exactly like today's eager load did.

**Constraint coverage map:**
1. *Dirty-page save safety* → Task 2 (PREPARE materialization + unresolved-abort + zero-visit round-trip test) and Task 3 (`_page_image_source` tier + portable test). At open no page is dirty; untouched pages that are never eligible are saved by NON-action (their `.mas` files are not rewritten → byte-identical).
2. *Batch without visits* → Task 3 (light tier at dispatch, GUI thread — QImage work never leaves the main thread, T-QHH-01).
3. *First-page display* → Task 2 (page 0 fully materialized BEFORE the swap — corrupt-first-page dialog preserved).
4. *Visit seam* → Task 2 (`on_page_selected` materialize step before Step 3; never touches placeholder auto-load).
5. *Undo/bleed* → no guard changes; outgoing persistence only ever targets the materialized displayed page; pinned by a Task 2 test.
6. *Boxes eager* → the lazy builder parses boxes/flags/verify_original exactly as today.
7. *Scope* → no eviction, no history slimming, no churn work.

**Strictly out of scope:** F2/F3/F4/F5/F6 from OOM-MEMORY-MAP.md; `_load_folder`/`_load_single_page_mas` laziness (they keep `_build_image_file_from_parsed` eager — this also keeps every existing folder-session save test byte-identical); thumbnail decoding; RSS instrumentation.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Core layer — selective container decompression, parse_page_meta, ImageFile lazy slots</name>
  <files>manga_ai_studio/core/project_io.py, manga_ai_studio/core/image_file.py, tests/test_core/test_project_io.py</files>
  <behavior>
    - load_page_file(path, names=frozenset({"meta.json"})) returns a dict containing meta.json with byte-identical content to the full load; unrequested entries are ABSENT from the result.
    - A container whose unrequested entry blob is CORRUPT (garbage bytes) decompresses fine under a names-subset that excludes it (proves non-decompression) but raises ProjectFormatError on a full load.
    - A requested-but-corrupt entry still raises ProjectFormatError under selective load; wrong magic / bad version / truncated table raise identically to today.
    - load_page_file(path) with names=None decompresses everything — byte-identical behavior to the current signature (existing tests pass unchanged).
    - parse_page_meta(entries with meta.json + original.json) returns {"meta": <validated dict>, "original": <dict|None>}; malformed meta JSON, non-dict meta, missing meta.json, and validate_meta failures (bad dims) all raise ProjectFormatError.
    - parse_page_entries(entries) still full-validates and returns image_png/mask/planes after the refactor that reuses parse_page_meta for its head.
    - ImageFile() constructs with source_mas=None and embedded_size=None defaults; a lazily-built instance exposes both alongside current_image=None.
  </behavior>
  <action>
    In `manga_ai_studio/core/project_io.py`: (1) extend `load_page_file` (project_io.py:148) with a keyword param `names: frozenset[str] | None = None` — inside the entry-table loop, when `names is not None` and the entry name is not in `names`, advance `off` past the blob and `continue` BEFORE `lzma.decompress`, omitting the entry from the result dict; the table walk, version/magic checks, and exception contract (struct/IndexError/UnicodeDecodeError/LZMAError → ProjectFormatError) stay byte-identical; `MAX_ENTRY_DECOMPRESSED` memlimit still applies to every entry that IS decompressed. (2) Add `parse_page_meta(entries: dict) -> dict` that performs exactly the head of `parse_page_entries` (project_io.py:742-753 + :784-789): require `meta.json` (KeyError → ProjectFormatError), json.loads with ValueError → ProjectFormatError, isinstance-dict check, `validate_meta(meta)`, optional `original.json` parse; return `{"meta": meta, "original": original}`. (3) Refactor `parse_page_entries` to call `parse_page_entries`' new head — i.e. it starts with `parsed = parse_page_meta(entries)` and continues with the existing image/mask/plane body unchanged (no validation duplication, no behavior change). In `manga_ai_studio/core/image_file.py`: add two dataclass fields after `current_image` (image_file.py:118) — `source_mas: Path | None = None` ("back-pointer to the page `.mas` container this lazy page was loaded from; set by the project-open meta loop; None for folder/image sessions and eager `.mas` opens") and `embedded_size: tuple[int, int] | None = None` ("(w, h) from meta.img at lazy load — the dims source for exports when current_image is not yet materialized"); update the `current_image` docstring (image_file.py:81-87): populated for the DISPLAYED page at project load and for every page on first visit (lazy materialization via source_mas), no longer "for EVERY page at project load"; None for never-visited lazy pages. Keep the module Qt-import surface unchanged.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_project_io.py -x -q</automated>
  </verify>
  <done>Selective decompression + parse_page_meta land with the full headless battery green; parse_page_entries is behaviorally unchanged (all pre-existing tests pass); ImageFile carries the two lazy slots with defaults.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Lazy project open + visit materialization seam + save round-trip</name>
  <files>manga_ai_studio/gui/main_window.py, tests/test_gui_project.py</files>
  <behavior>
    - After opening a saved 3-page project: page 0 current_image is not None; pages 1-2 have current_image None, mask None, source_mas set to their .mas paths, embedded_size == (60, 60), boxes parsed (eager), original_verified per the D-06 rule.
    - Navigating to page 2 materializes it: current_image equals the embedded pixels (np.array_equal vs a fresh project_io decode of the source .mas), canvas displays it, planes restore via has_mask_planes (or legacy composite when the page has no plane entries), boxes appear.
    - Save As… with ZERO navigation writes all 3 pages; opening the new project and comparing per-page embedded pixels, planes, and boxes against the ORIGINAL project shows exact equality.
    - Portable variant: with the source images deleted (original verification fails at open), Save As… still round-trips identical pixels — the embedded-only fallback flows through the source .mas.
    - Opening a project, deleting an unvisited page's .mas on disk, then saving returns False and shows the existing unresolved-source critical dialog (no silent pristine-pixel embed, no whole-save crash).
    - Incremental save after visiting + editing ONLY page 2 leaves pages 1/3 .mas files byte-identical on disk (untouched lazy pages save by non-action).
    - Visit page 2 → navigate to page 3 → back to 2: the page-2 stroke/mask state persists (outgoing flush round-trip through a materialized page), page 3 shows no page-2 planes, and each switch resets per-page history (260826-1by guards hold; lazily-empty outgoing pages never occur because the outgoing index only ever points at a displayed page).
    - A project whose FIRST page .mas has a corrupt embedded image fails the open with the corrupt-project dialog (page 0 materializes before the swap); a corrupt blob on a LATER page opens fine and degrades on visit to the existing path-fallback UX.
  </behavior>
  <action>
    All edits in `manga_ai_studio/gui/main_window.py`. (1) Extract from `_build_image_file_from_parsed` (:3437): a module-level `_decode_embedded_image(parsed: dict) -> np.ndarray` holding the embedded-PNG decode + the WR-6 declared-vs-actual dims cross-check (:3485-3518, ProjectFormatError on corrupt blob or dims mismatch — .convert("RGB") + .copy() contract kept), and a module-level `_resolve_original_ref(parsed: dict, fallback_path: Path) -> tuple[Path, bool]` holding the verify_original block (:3455-3465); `_build_image_file_from_parsed` calls both (zero behavior change — folder sessions and single-.mas opens stay eager through it). (2) Add `_build_lazy_image_file(self, parsed: dict, page_mas_path: Path, fallback_path: Path) -> ImageFile` mirroring the eager builder's meta-derived state ONLY: original ref + verified flag via `_resolve_original_ref`, `geometry_altered` from meta, boxes via `project_io.json_to_pagebox`, `embedded_size = (int(meta["img"]["w"]), int(meta["img"]["h"]))`, `source_mas = page_mas_path`; mask/current_image/planes stay None. (3) Rewrite the `_load_project_session` loop (:3662-3675): per page, `entries = project_io.load_page_file(page_path, names=frozenset({"meta.json", "original.json"}))` → `parsed = project_io.parse_page_meta(entries)` → `_build_lazy_image_file(parsed, page_path, manifest_path.parent / f"{page['name']}.mas")` (module constant `_LAZY_OPEN_ENTRY_NAMES` for the names set); keep the zero-pages ProjectFormatError gate; then, BEFORE the session swap, `if not self._materialize_page_state(page_files[0], 0, want_pixels=True): raise project_io.ProjectFormatError(...)` so a corrupt DISPLAYED page still aborts the open with the existing dialog. Everything from the swap onward (:3677-3708) is unchanged. (4) Add `_materialize_page_state(self, imf: ImageFile, idx: int | None, want_pixels: bool) -> bool`: return False immediately when `imf.source_mas is None`; full read `project_io.load_page_file(imf.source_mas)` + `parse_page_entries` + `_decode_embedded_image`; GAP-FILL only still-None slots — each of raw_detected_mask/auto_mask/mask_manual/mask_erase individually from the parsed packed blobs, `current_image` only when want_pixels, the composite `mask` via numpy_binary_to_mask_qimage only when None and (want_pixels OR the page has no plane entries — the light-tier legacy-composite rule for batch clean's flat-mask fallback); never overwrite a non-None slot (batch-detect writes and D-11 flushes win over disk); on ProjectFormatError/OSError log a warning with the page name and return False; never touch dirty/boxes/flags. (5) In `on_page_selected`, after `incoming_idx`/`imf` are resolved (:2398-2403) and BEFORE the current_image branch: `if imf is not None and imf.current_image is None and imf.source_mas is not None: self._materialize_page_state(imf, incoming_idx, want_pixels=True)` — on success the existing embedded branch runs (placeholder path never reaches set_image_from_path, the 05-05 rule); on failure the existing path-fallback branch runs unchanged (verified original shows pristine, placeholder shows the existing dialog). (6) In `_save_project` PREPARE, inside the try block after `snapshot_serials` is captured (:3008-3010) and before the payload loop: for each eligible idx whose page is lazy (source_mas set, current_image None), call `_materialize_page_state(imf, idx, want_pixels=True)`; on False append `imf.path.name` to `unresolved_names` and `continue` — the existing WR-02 whole-save abort (:3078-3097) then surfaces the honest failure instead of silently embedding different pixels. In `tests/test_gui_project.py`: REWRITE `test_open_project_populates_all_current_images` (:405) into the lazy-contract test (its old assertion is the intentional contract change); add the round-trip battery using the house helpers (`_save_as` + `_wait_save_done`, `_stub_open_dialog` for reopening, project_io decode for pixel comparison). For the portable test: build + save a project, delete the source PNGs AND the originals' availability so verification fails at open, reopen, Save As, compare. For the abort test: stub QMessageBox.critical and assert the save returns False.
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_project.py tests/test_core/test_project_io.py -x -q</automated>
  </verify>
  <done>Project open retains pixels for the displayed page only; first visit materializes identically to the eager open; zero-visit Save As and portable round-trips are pixel-exact; unresolvable lazy pages abort saves honestly; incremental saves keep untouched .mas bytes identical; the full test_gui_project battery is green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Batch + export seams — light materialization, source-.mas pixel extraction, embedded dims</name>
  <files>manga_ai_studio/gui/main_window.py, tests/test_gui_batch.py</files>
  <behavior>
    - Dispatching batch clean on a project whose page 2 was never visited: the worker receives page 2 with has_mask_planes() True (persisted manual/erase strokes reach the batch) and current_image still None (no pixels materialized at dispatch).
    - Dispatching batch detect writes mask/auto/raw slots on never-visited pages exactly as today; a subsequent save full-materializes those pages WITHOUT clobbering the batch-written mask (gap-fill respects non-None slots) and the rewritten .mas carries the fresh mask.
    - Batch OCR export for a never-visited geometry-altered page reports img_w/img_h from embedded_size (the meta dims), not the on-disk original's dims.
    - Batch typeset export for a never-visited page receives image pixels decoded from the source .mas (equal to the embedded image), not None and not the pristine original.
    - _page_image_source for a VISITED page still returns current_image (authoritative order unchanged); with source_mas absent the function is byte-identical to today.
  </behavior>
  <action>
    All edits in `manga_ai_studio/gui/main_window.py`. (1) In `_dispatch_batch` (:8185), immediately after `self._flush_current_canvas_mask_to_data_model()` (:8224) and before the args are built: loop `for i, imf in enumerate(self.image_files)` and when `imf.source_mas is not None and imf.current_image is None` call `self._materialize_page_state(imf, i, want_pixels=False)` — the LIGHT tier on the GUI thread (mask planes + legacy composite only; QImage work never leaves the main thread per T-QHH-01; a False return is non-fatal for batch — the page proceeds with whatever mask state it has, matching batch's per-page failure isolation). (2) In `_page_image_source` (:2858), insert a tier between the current_image branch and the cleaned fallback: when `imf.source_mas is not None` and `Path(imf.source_mas).is_file()`, load + parse + `_decode_embedded_image` and return the fresh array inside a try/except (ProjectFormatError, OSError) that falls through to the existing chain on failure — this is what serves typeset export and defense-in-depth for saves; document the tier order in the docstring (current_image authoritative → source .mas → cleaned → path). (3) In `_dispatch_batch_ocr_export` (:7885-7891), insert an `elif imf.embedded_size is not None:` arm between the current_image arm and the PIL fallback setting `img_w, img_h = imf.embedded_size` — geometry-altered lazy pages export exact dims. In `tests/test_gui_batch.py`: add the three seam tests using the existing dispatch-capture pattern (:1052 — monkeypatch the batch entry point with a capturing stub; for the planes-survival test, build a project whose page 2 carries manual/erase plane entries via the 08-07 save path helpers used in tests/test_gui_mask_planes.py, open it through the project route without visiting page 2, dispatch, and assert on the captured ImageFile list).
  </action>
  <verify>
    <automated>"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_gui_batch.py tests/test_gui_project.py -x -q</automated>
  </verify>
  <done>Batch dispatch keeps never-visited pages' mask planes available without materializing pixels; OCR export dims and typeset export pixels are correct for lazy pages; _page_image_source's tier order preserves the authoritative current_image contract; the batch + project batteries are green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| .mas container → app | Page containers are untrusted input; the new meta-only parse path and selective decompression read them at open |
| source_mas re-read → app | Materialization re-reads the container later than open — the same untrusted boundary, deferred in time |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-nfq-01 | Tampering/DoS | parse_page_meta (untrusted meta.json/original.json) | medium | mitigate | Reuses the existing json + isinstance + validate_meta discipline (T-05-01..04) — no new parse surface beyond a strict subset of parse_page_entries' head |
| T-nfq-02 | DoS | load_page_file selective decompression | low | mitigate | Entry-table walk unchanged; memlimit MAX_ENTRY_DECOMPRESSED still applies to every decompressed entry; unrequested blobs are never decompressed (shrinks the attack surface) |
| T-nfq-03 | Tampering | deferred blob corruption (surfaced at visit/save instead of open) | medium | mitigate | Full parse_page_entries re-validation + WR-6 dims cross-check at every materialization; corrupt blobs degrade via the existing path-fallback UX (visit), the WR-02 unresolved abort (save), or the corrupt-project dialog (page 0 at open) |
| T-nfq-04 | Information disclosure | none new | low | accept | No new logs of user content; materialization warnings log page names only (existing convention) |
</threat_model>

<verification>
- `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest tests/test_core/test_project_io.py tests/test_gui_project.py tests/test_gui_batch.py -x -q` green.
- Full suite: `"C:\Users\Stella\.pyenv\pyenv-win\versions\3.14.2\python.exe" -m pytest -q` — baseline 1303 passed, 0 failed (strict superset: the rewritten eager-open test replaces its predecessor 1:1, all new tests add on).
- Residency probe (encoded in the lazy-contract test): after `_load_project_session` on a 3-page project, exactly one page has `current_image` set.
- Round-trip probe: zero-visit Save As reopen compares per-page embedded pixels with np.array_equal — the constraint-#1 "open → save → close → reopen shows identical images" gate.
</verification>

<success_criteria>
- All seven hard constraints from the task brief addressed (see Constraint coverage map): lazy open baseline, save byte-fidelity incl. portable + abort-honesty, batch correctness without visits, first-page eager display, visit materialization seam with no placeholder auto-load, undo/bleed guards intact, boxes/geometry eager.
- No silent pixel-loss path exists: every save of a lazy page flows from current_image (visited/edited) or the source .mas embedded entry (untouched), or the save aborts loudly.
- Out-of-scope items (F2-F6, folder-session laziness, history/churn work) untouched.
- Full suite green under the pinned interpreter.
</success_criteria>

<output>
Create `.planning/quick/260907-nfq-lazy-project-open-stop-eagerly-decoding-/260907-nfq-SUMMARY.md` when done
</output>

# OOM Memory Map — Manga AI Studio (concerns focus)

**Analysis Date:** 2026-09-07
**Symptom:** Loading a large project jumps RAM to >6 GB immediately; normal editing (cleaning, masking, OCR, typesetting) climbs steadily to ~18 GB until the process dies OOM. Regression suspected vs. the pre-mid-August "stable era".

**Byte-arithmetic shorthand used throughout** (page = H×W px):

| Object | Bytes | @1500×2000 (3 MP) | @2000×2800 (5.6 MP) |
|---|---|---|---|
| `current_image` (H,W,3) uint8 | 3HW | 9.0 MB | 16.8 MB |
| `mask` RGBA8888 QImage composite | 4HW | 12.0 MB | 22.4 MB |
| 4 packed planes (HW/8 each) | HW/2 | 0.375 MB | 0.7 MB |
| One ARGB32 plane QImage (manual/erase) | 4HW | 12.0 MB | 22.4 MB |
| Unpacked auto binary (H,W) uint8 | HW | 3.0 MB | 5.6 MB |
| QPixmap (ARGB32 premult) / RGB888 QImage | 4HW / 3HW | 12 / 9 MB | 22.4 / 16.8 MB |
| Thumbnail 64×64×4 | 16 KB | — | — |

---

## 1. Load-time residency inventory (the >6 GB baseline)

### Load path

1. `MainWindow._load_project_session` — `manga_ai_studio/gui/main_window.py:3647`
   - `project_io.load_project` (manifest only) — `manga_ai_studio/core/project_io.py:669`
   - Loop over **every** page: `project_io.load_page_file` (LZMA-decompress ALL entries, `project_io.py:148`) → `parse_page_entries` (`project_io.py:720`) → `_build_image_file_from_parsed` (`main_window.py:3437`). All pages fully built **before** the session swap ("build-before-swap", `main_window.py:3663-3675`).
2. `ImageFile` slots populated per page (`manga_ai_studio/core/image_file.py:90-118`):
   - `current_image` — **decoded from the embedded `image.png` for EVERY page** (`main_window.py:3489-3491`). 3HW retained.
   - `mask` — flat composite restored as an **RGBA8888 QImage = 4HW** via `numpy_binary_to_mask_qimage` (`main_window.py:3472`; converter at `manga_ai_studio/core/mask_editor.py:207-224` builds `(h,w,4)` RGBA).
   - `raw_detected_mask` / `auto_mask` / `mask_manual` / `mask_erase` — 4 packed planes, HW/8 each (`main_window.py:3477-3480`; blobs are `np.frombuffer` views over the decompressed entries, `project_io.py:801-810`).
   - `boxes`, flags, thumbnail 16 KB (`file_table.set_pages` → `load_thumbnail`, `manga_ai_studio/gui/file_table.py:98-122` — one transient full decode of the original file per page).
3. `_display_page_state(page_files[0])` (`main_window.py:3688` → `3521-3606`) — canvas state for the **first page only**:
   - `_decode_original_reference` decodes the on-disk original to a full-size array (3HW transient) — `main_window.py:3411-3435`
   - `canvas.set_image_from_numpy_page(imf.current_image.copy(), baseline)` — seeds persistent `_original_image_numpy` (3HW) + `_inpainted_qimage` (3HW) — `manga_ai_studio/gui/canvas.py:1029-1081`
   - `canvas.set_planes(...)` unpacks the 3 planes into page-size canvas slots: `_mask_manual` 4HW + `_mask_erase` 4HW + `_auto_bin` HW, then `recompose_mask()` allocates the composite `_mask` 4HW — `canvas.py:710-761`, `659-689`
   - `image_item` QPixmap 4HW.

### Per-page resident table (project open, non-displayed page)

| Slot | Bytes | Needed at open? | Lazy-loadable? |
|---|---|---|---|
| `ImageFile.current_image` (3HW) | 9–16.8 MB | **NO** — only page 0 is displayed | YES — decode from the page `.mas` on first visit (folder sessions already do exactly this via `on_page_selected`/`set_image_from_path`, `main_window.py:2404-2438`) |
| `ImageFile.mask` RGBA composite (4HW) | 12–22.4 MB | **NO** — redundant whenever packed planes exist (recomposable); legacy pages only need it on visit | YES — restore on visit like `on_page_selected` Step 4 does (`main_window.py:2444-2490`) |
| 4 packed planes (HW/2) | 0.4–0.7 MB | NO (needed on visit / save) | YES — cheap to keep, but can lazy-load with the `.mas` |
| thumbnail | 16 KB | YES (sidebar) | — |
| **Total per page** | **~21.5–40 MB** | | |

**Aggregate estimate (7.56·HW per page retained):**

| Pages | @1500×2000 | @2000×2800 |
|---|---|---|
| 100 | 2.3 GB | 4.2 GB |
| 150 | 3.4 GB | **6.3 GB** |
| 200 | 4.5 GB | 8.4 GB |
| 300 | 6.8 GB | 12.6 GB |

→ A ~150-page chapter at ~2000×2800 scans (or ~250–300 pages at 3 MP) explains the >6 GB open. Add app baseline (Qt + vendored panelcleaner + numpy/PIL; torch is a lazy import, `manga_ai_studio/adapters/torch_impl.py:92`) and one-time load transients (per-page LZMA buffers, `MAX_ENTRY_DECOMPRESSED` = 512 MB bound at `project_io.py:62`; per-page full decode for thumbnails).

### Why the project path can't reuse the folder-session laziness

- Folder sessions (`_set_pages`, `main_window.py:2175-2220`) keep `ImageFile(path, original_verified=True)` with `current_image=None` and load pixels **on visit** (`on_page_selected` → `canvas.set_image_from_path`, `main_window.py:2429-2438`). Per-page cost ≈ thumbnail only.
- Project sessions must bypass `_set_pages` because a restored page's `path` may be a **placeholder** (unverified original → `fallback_path` = the `.mas` file itself, `main_window.py:3464-3466`) — `set_image_from_path` on it would fail (the 05-05 decision, D-06/D-08: embedded `current_image` is the only guaranteed pixel source; docstring at `image_file.py:81-87` "Populated for EVERY page at project load").
- **The laziness is still achievable**: keep `path`, a `source_mas` back-pointer, and the meta dims at load; decode `current_image`/`mask` from the page `.mas` on first visit (same fallback chain as `on_page_selected` Step 3). Only the displayed page needs pixels at open.

---

## 2. Growth/retention suspects (unbounded-first)

### S1 — Mask-plane undo history: bounded-but-huge, doubled by 08-02 (rank 1 for the climb)

- `HistoryManager` limit=20 per stack (`manga_ai_studio/core/history_manager.py:77`, `4239` in main_window resets per page).
- Since plan 08-02 the MASK stack value is a `MaskPlanesSnapshot`: manual ARGB32 (4HW) + erase ARGB32 (4HW) + packed auto (HW/8) ≈ **24.4 MB/entry @ 3 MP** (`core/mask_planes.py:78-106`; hook `main_window.py:4267-4299`).
- Worst case per page: undo 20 × 24.4 MB + redo stash 20 × 24.4 MB (pops stash the current planes, `history_manager.py:179-183`) + `_pre_stroke_planes` 24.4 MB ≈ **~1 GB for ONE page** of sustained masking + undo/redo @ 3 MP (≈ 1.9 GB @ 5.6 MP).
- Most entries hold nearly-empty transparent planes (a stroke is sparse) — stored at full page size regardless.
- Reset on page switch (`reset_history`, `main_window.py:4228-4241`) → bounded per page, enormous per page. Design, not leak — but the largest single climbing consumer during masking work.

### S2 — Recompose churn: big-buffer alloc/free per stroke, per undo, per page switch (rank 1 for heap ratchet)

- `canvas.recompose_mask` (`canvas.py:659-689`): per call allocates `mask_to_numpy_binary` for manual AND erase — each a `convertToFormat(RGBA8888)` (4HW) + `bytes()` copy (4HW) + binary (HW) (`mask_editor.py:179-204`) — plus the composite RGBA QImage (4HW). ≈ **60+ MB transient per stroke commit / plane change / undo / page switch** @ 3 MP.
- `canvas.update_mask_display` (`canvas.py:847-861`) allocates a fresh 4HW QPixmap per call — invoked **per mouse-move** during brush strokes (`canvas.py:1974`). Pre-existing, but the buffer became ARGB32 4HW.
- Windows/Qt raster allocators do not promptly return freed 10–30 MB blocks → RSS ratchets toward the churn high-water mark over a session. This is the mechanism that makes "bounded" look like "keeps climbing".

### S3 — Restore tool: full-frame churn per mouse-move (rank 2 churn; regression 2026-08-28)

- `_restore_work` + `_restore_pre` = 2 × 3HW live during a stroke (`canvas.py:477-479`, cleared at `_finish_restore_stroke`, `canvas.py:1911-1940`).
- `_refresh_restore_display` allocates QImage 3HW + `.copy()` + QPixmap 4HW (**~30 MB per mouse-move event**) — `canvas.py:1889-1909`, called from `_advance_paint` `canvas.py:1967`. Deliberate PERF CHOICE (T-l3l-03) that trades memory churn for code simplicity.
- Introduced by quick-260828-l3l (`1856c44`, `d367169`, 2026-08-28).

### S4 — Page-switch churn + persistent canvas preview slots (u9m, 2026-08-26)

- Every page switch: `_decode_original_reference` does a full PIL decode of the original file (3HW array + PIL internal buffers ≈ 2–4× raw size) — `main_window.py:2416`, `3411-3435`.
- `set_image_from_numpy_page` **unconditionally** sets `_original_image_numpy` (3HW) + `_inpainted_qimage` (3HW) per page display (`canvas.py:1076-1079`).
- Persistent delta vs pre-u9m is ≈ 0 (both slots were already held; u9m fixed which page's pixels they hold — the cross-page bleed). The cost is **churn** (per-switch decode) not retention. Verdict: real contributor to ratchet, NOT a leak, NOT new persistent arrays per visited page.

### S5 — Save payload snapshot: transient session double (vhh, 2026-08-26)

- `_save_project` PREPARE builds immutable payloads: `np.array(image_rgb, copy=True)` (3HW) + `mask_bin` (HW via `mask_to_numpy_binary`, which transiently allocates 4HW+4HW per page) + plane copies (HW/2) **per eligible page** (`main_window.py:3030-3042`; eligibility `main_window.py:2882-2900` = dirty OR missing `.mas`).
- Save As / first save ⇒ **every page**: +≈ 10.5–22 MB/page held until the worker finishes (Worker holds `args`, `worker_thread.py:124-127`). 150 pages @ 3 MP ⇒ **+1.6 GB spike** on top of the session; @ 5.6 MP ⇒ **+3.1 GB**.
- Bounded (freed at completion), but lands exactly when the session is already large. T-QHH-01 design.

### S6 — Typeset rendering: bounded scratch, oversized budget (vhh/0id/09m)

- Two-pass measured render: per content change up to 2 scratch ARGB32 surfaces at `ink + 2·pad + 2·margin`, margin = max(64, font px ≤ 1024) (`box_item.py:501-515`, `713-770`, `861-898`); only the cropped pixmap is retained per box (one `self._pixmap`, replaced per change).
- Effect surface budget `_EFFECT_MAX_PIXELS = 64_000_000` px = **256 MB per ARGB surface** (`text_renderer.py:198-199`), plus `_blur_alpha` float64 temporaries (~8× surface bytes sequential ≈ up to ~2 GB transient for a max-size glow) — `text_renderer.py:1153-1290`. Only for BIG SFX text with glow/shadow; the caps that allow it were raised by quick-260826-vhh (`41efbd1`) and the outward outline two-pass added by 260827-0id (`5d83655`).
- Bounded churn, not a leak; included because one oversized effect render can transiently dwarf everything else.

### S7 — Model + worker memory (step increase, by design)

- First Detect/Inpaint loads LaMa (torch, lazy) + detector/OCR models: ~1–2 GB step; torch CPU allocator + ONNX runtime arenas cache and fragment under repeated ops (`adapters/torch_impl.py`, `adapters/onnx_impl.py`). Not counted in the 6 GB open but part of the path to 18 GB once cleaning runs.
- 04e3725 (2026-09-03) already drops stale mid-op results on page switch — the op-result path itself no longer accumulates.

### Explicitly ruled out as unbounded leaks

- No accumulating instance lists in `main_window.py` — all writes are `image_files[idx]` slot **replacements** (mask/planes/current_image/boxes, `main_window.py:1660-2760`).
- `on_page_selected` Step 1 overwrite (`main_window.py:2339-2356`) replaces the outgoing page's mask/planes — no per-visited-page growth beyond the open-time footprint.
- OCR Grab history panel: 20 text entries (`gui/ocr_grab.py`), negligible.
- `HistoryManager` lists: hard-capped at 20 (`history_manager.py:144-145`, `225-226`, `354-355`).
- Signal closures: `_make_recent_project_opener` holds a Path only (`main_window.py:3808-3814`).

**Verdict on 6→18 GB:** no single Python-level leak found; the climb is (a) bounded-but-huge history (S1, up to ~1 GB/page), (b) 10–30 MB-per-event churn (S2/S3/S4) ratcheting the Windows heap, (c) transient session doubles at save (S5) and occasional effect renders (S6), plus (d) the model step (S7) — stacked on an already-massive open baseline.

---

## 3. Regression shortlist (git archaeology)

"Stable era" = before Phase 08 (2026-08-16); the project layer itself is Phase 5 (2026-08-08).

| Rank | Commit(s) | Date | What changed | Before → After memory behavior |
|---|---|---|---|---|
| 1 | `e893095` + `42ab4f0` (plan 08-02) | 2026-08-16 | Canvas three-plane model + plane-aware MASK undo + per-page plane persistence | Before: one composite mask QImage (4HW) total; history entry = 1×4HW copy; strokes painted in place. After: canvas holds `_mask_manual` 4HW + `_mask_erase` 4HW + `_auto_bin` HW + recomposited `_mask` 4HW (~+28 MB/page); history entry = 2×4HW + packed (**2.0× per entry**, `main_window.py` pre-`42ab4f0`: `pre_mask = canvas.get_mask().copy()` → `planes_snapshot()`); NEW `recompose_mask` churn (≈60 MB/stroke) + `mask_to_numpy_binary` on every recompose. **Best single explanation for the working-set climb** |
| 2 | `ba25bb8` / `8789b61` / `c5a8e71` (plan 05-05/05-01) | 2026-08-08 | Project sessions: decode-everything load | Before Aug 8 there were no project loads (folder flow = lazy, ~thumbnail/page). After: `current_image` 3HW + `mask` RGBA 4HW per page at open (~22–40 MB/page). **Best single explanation for the >6 GB baseline** (with plane slots added later) |
| 3 | `57def65` + `379a425` (plan 08-04/08-07) | 2026-08-17 | 4 packed plane slots per page at load + `_display_page_state` plane restore | +HW/2 per page at open; +3 page-size canvas buffers at first display; `_safe_unpack` backstops. Minor footprint, but part of the post-08-16 step |
| 4 | `5d60510` + `1915859` (quick-260826-u9m) | 2026-08-26 | `set_image_from_numpy_page` seam; `_decode_original_reference` per page display/switch | Persistent slots ≈ unchanged (both existed); NEW per-switch full PIL decode (churn) and guaranteed re-seed of `_original_image_numpy`/`_inpainted_qimage` on every page display (`canvas.py:1076-1079`) |
| 5 | `1856c44` + `d367169` (quick-260828-l3l) | 2026-08-28 | Restore tool: `_restore_pre`/`_restore_work` (2×3HW per stroke) + full-frame QImage+QPixmap rebuild **per mouse-move** (`canvas.py:1889-1909`) | Before: no restore path. After: ~30 MB churn per move event during restore strokes |
| 6 | `41efbd1` + `0579f9a` (quick-260826-vhh) | 2026-08-26 | Async save with T-QHH-01 immutable payloads (`main_window.py:3030-3042`); effect caps raised (`text_renderer.py:198-199` 64M px budget) | Before: sync save, page-by-page encode (transient per page). After: eligible pages' images+mask binaries held simultaneously until the worker finishes (+1.6–3.1 GB on Save As of big projects) |
| 7 | `3fb36bf` + `91e614d` (quick-260907-l3w) | 2026-09-07 | `_load_folder` builds `.mas` pages through the same decode-everything path (`main_window.py:2137-2141`) | Extends the heavy open path (baseline of this report, §1) to mixed image+`.mas` folder sessions — folder opens containing `.mas` files lose their laziness for those pages |

**Single most likely regression commit for the symptom as a whole:** `e893095`/`42ab4f0` (plan 08-02, 2026-08-16) for the climb; the baseline is explained by the Phase 5 decode-everything load (`ba25bb8`, 2026-08-08) reached at scale — with `3fb36bf` (2026-09-07) newly extending it to folder opens.

---

## 4. Recommended fix directions (for the follow-up task)

| # | Fix | Where | Expected win | Effort / Risk |
|---|---|---|---|---|
| F1 | **Lazy page pixels/planes on project open**: at load keep only `path` + `source_mas` back-pointer + meta dims + boxes/meta; decode `current_image`/`mask`/planes from the page `.mas` on first visit (mirror `on_page_selected`; keep the build-before-swap corruption gate by parsing meta for ALL pages up front, deferring only blob decodes). Only page 0 displays at open. | `main_window.py:3647-3708` (`_load_project_session`), `3437-3519` (`_build_image_file_from_parsed`), `image_file.py` (add `source_mas` slot) | Open baseline 22–40 MB/page → ~0.1 MB/page (~200× on the dominant term); >6 GB → ~50–100 MB + page 0 | Medium effort / Medium risk — touches the D-05/D-08 contracts (`current_image` as authoritative state) and the 05-05 placeholder-path rule; save path `_page_image_source` (`main_window.py:2858-2880`) must decode-on-demand for untouched pages |
| F2 | **Evict decoded pixels for non-current pages**: after the outgoing flush (`on_page_selected` Step 1 / `_snapshot_current_page`), drop `current_image` (and optionally the RGBA `mask` — recomposable from packed planes) for pages not visited recently (LRU of 2–4 pages). Keep meta dims. | `main_window.py:2284-2556`, `image_file.py:118` | Caps session residency independent of page count (the 18 GB → page-count product collapses) | Low effort / Low-Medium risk — must re-decode on return; interacts with dirty-state saves (keep pixels for `dirty` pages) |
| F3 | **History snapshot slimming**: (a) store manual/erase planes as packed binaries (HW/8) instead of ARGB32 QImages in `MaskPlanesSnapshot` (24.4 → ~0.8 MB/entry typical); (b) crop snapshots to content bbox + offset; (c) consider limit=10. | `core/mask_planes.py:78-106`, `core/history_manager.py:132-146`, `gui/canvas.py:691-708` (planes_snapshot), `apply_undo_mask` `canvas.py:864-888` | Worst-case page history ~1 GB → ~30–60 MB | Medium effort / Medium risk — undo/redo round-trip tests are extensive; packing is lossless for 0/255 planes |
| F4 | **Kill per-mousemove big allocations**: cache the display QPixmap in `update_mask_display` and refresh via dirty-rect repaint; for restore strokes, accumulate stamps in `_restore_work` and refresh display on a timer/coalescer (or bbox-only QImage update). | `gui/canvas.py:847-861` (`update_mask_display`), `1889-1909` (`_refresh_restore_display`), `1967` | Removes ~12–30 MB churn per move event (the ratchet driver) | Low-Medium effort / Low risk — display-only |
| F5 | **recompose_mask fast path**: convert planes to binary via a cached per-plane binary (invalidate on stroke commit) instead of `convertToFormat(RGBA8888)` + `bytes()` for BOTH planes on every recompose. | `gui/canvas.py:659-689`, `core/mask_editor.py:179-204` | ~60 MB → ~3 MB per stroke commit; fewer large transient blocks | Medium effort / Low risk — pure derived-state caching |
| F6 | **Save snapshot slimming**: for non-current eligible pages, reference `imf.current_image` under a copy-on-write guard (bump `_page_edit_serials` already exists) instead of `np.array(copy=True)`; encode mask binary directly from packed slots instead of RGBA→binary round-trip. | `main_window.py:3012-3042`, `2762-2789` | Save As spike +1.6–3.1 GB → ≈ 0 (worker gets views guarded by serials) | Low effort / Medium risk — T-QHH-01 immutability contract must be preserved via serials (already tracked, `main_window.py:3005-3010`) |
| F7 | **Instrumentation first (confirm before F1-F6)**: add a debug overlay/logging of `psutil.Process().memory_info().rss` + `tracemalloc` snapshots (domain-filtered to `manga_ai_studio/`) at: project open, page switch, stroke commit, undo/redo, save dispatch/completion; plus a Qt object audit (`QImage`/`QPixmap` counts via `shiboken6.exists`-style sweep is hard — instead track allocations in the Pitfall-2 helpers). A pytest-benchmarked probe with the pinned interpreter (see AGENTS.md) can synthesize an N-page project and assert RSS slopes. | new `tests/` probe + optional `gui/debug` overlay | Converts this map's arithmetic into measured attribution; verifies each fix | Low effort / Low risk — do FIRST; do not launch the GUI from CI |

**Suggested order:** F7 → F4/F5 (cheap churn wins) → F3 → F2 → F1 → F6.

---

*Concerns audit: 2026-09-07*

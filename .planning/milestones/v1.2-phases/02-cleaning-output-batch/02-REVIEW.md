---
phase: 02-cleaning-output-batch
reviewed: 2026-07-25T21:21:10Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - manga_ai_studio/core/image_io.py
  - manga_ai_studio/core/image_file.py
  - manga_ai_studio/core/batch_runner.py
  - manga_ai_studio/gui/main_window.py
  - tests/test_core/conftest.py
  - tests/test_core/test_image_io.py
  - tests/test_core/test_batch_runner.py
  - tests/test_gui_batch.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-25T21:21:10Z
**Depth:** standard
**Files Reviewed:** 8 (4 source + 4 test)
**Status:** issues_found

## Summary

Phase 02 adds the batch cleaning pipeline (FLOW-03), single-page Export (PROJ-02),
and the per-page mask persistence seam (D-11). The architecture is sound: the
core I/O writer (`image_io.py`) is correctly isolated, `batch_runner.py` is
genuinely GUI-free and model-agnostic with correct abort-between-pages discipline,
and the D-11 seam in `main_window.py` correctly persists/restores masks with
mandatory `.copy()` boundary discipline at both directions. The two fix-cycle
sites (Bug D flush and Bug D1 mode-aware refresh) are correctly implemented and
their regression tests are real (the Bug D1 RED genuinely fails without the
mode-aware branch).

The most serious defect is a UX-correctness bug, not a crash or data-loss
path: `_on_batch_finished` hardcodes the "Cleaned N/N pages" summary string for
ALL three batch modes, so a successful Batch Detect reports "Cleaned" instead of
"Detected". Several lower-severity issues follow: an exception-type leak in the
batch `failed[]` list, an unvalidated-suffix path in `passthrough_original`, and
a `progress_bar` desync on the cancel-then-finished double-cleanup path. None of
the findings are security vulnerabilities — the path-traversal and write-target
defenses (T-02-01/T-02-02/T-02-03) are correctly in place.

The D-11 seam correctness was specifically traced: `_last_page_index` is read
for the OUTGOING page (correct, since `select_path` flips `current_path` before
`on_page_selected` runs) and assigned at the END of the seam for the NEXT
navigation. The `.copy()` boundary is present at all four hand-off sites
(outgoing save, incoming restore, Bug D flush, Bug D1 restore).

## Critical Issues

### CR-01: Batch summary status string hardcodes "Cleaned" for all modes (incl. detect-only)

**File:** `manga_ai_studio/gui/main_window.py:1866-1871`
**Issue:**
`_on_batch_finished` unconditionally renders the summary as
`"Cleaned {ok}/{total} pages"`, regardless of which batch mode produced the
result. For a **Batch Detect** run (mode `"detect"`, no cleaning, no file
output), the status bar ends a successful run with "Cleaned 30/30 pages" —
which is factually wrong (nothing was cleaned) and actively misleading to the
user (it implies cleaned outputs exist in `cleaned/` when in fact none were
written).

The 02-04 SUMMARY explicitly documents the intended contract as
mode-aware — "`_on_batch_finished` ... D-04 summary text: `Cleaned {ok}/{total}`
pages ... for clean/detect_and_clean; `Detected {ok}/{total} pages` for
detect-only" — so this is an implementation/contract drift, not a design
ambiguity. The mode-aware status verb in `_on_batch_progress` (Bug A fix,
`_batch_verb`) was added but the equivalent mode-awareness in the *finish*
handler was never implemented.

Note the success text is the *only* post-batch status the user sees on a clean
run (no error, no cancel), so this surfaces on every detect-only batch.

**Fix:**
Mirror `_batch_verb`'s mode branching. Capture the mode before `_on_batch_cleanup`
resets `_batch_mode` to `None` (the handler reads it before cleanup runs since
`result` fires before `finished`, but be defensive):

```python
def _on_batch_finished(self, summary) -> None:
    ok = summary.get("ok", 0) if isinstance(summary, dict) else 0
    total = summary.get("total", 0) if isinstance(summary, dict) else 0
    failed = summary.get("failed", []) if isinstance(summary, dict) else []
    verb = "Detected" if self._batch_mode == "detect" else "Cleaned"
    if failed:
        self.status_bar_left.setText(
            f"{verb} {ok}/{total} pages \u2014 {len(failed)} failed, see log"
        )
    else:
        self.status_bar_left.setText(f"{verb} {ok}/{total} pages")
    self._refresh_action_states()
```

(A getter like `_batch_verb_past_tense()` alongside `_batch_verb()` is the
DRY-er option.)

## Warnings

### WR-01: `batch_runner` swallows the real exception type — `failed[]` carries only a string message

**File:** `manga_ai_studio/core/batch_runner.py:183-185`
**Issue:**
The per-page failure handler does `failed.append((page.path, str(exc)))`. The
summary's `failed` type is documented as `list[tuple[Path, str]]` and `_on_batch_finished`
reads `len(failed)` only — so the string is the *only* record of the failure
type. After a 30-page batch with 3 failures, the operator sees "3 failed, see
log" but the `failed` list (which `_on_batch_finished` has access to via the
summary dict) carries only `str(exc)`, not the exception class. The "see log"
fallback works, but the structured payload is weaker than it could be and the
docstring's "loguru" claim at line 38 is the only place the full type lives.

This is a robustness/diagnosability gap rather than a correctness bug, but it
matters because per-page failures are the *expected* failure mode (D-04 — one
corrupt page must not abort the rest), and operators triaging "3 failed" with
only `"Could not read image: …"` strings cannot distinguish `FileNotFoundError`
from a `cv2` decode `None` from a model `RuntimeError` without grepping logs.

**Fix:**
Carry the exception class name alongside the message:

```python
except Exception as exc:  # D-04: per-page failure non-fatal
    logger.error(f"Batch: page {page.path.name} failed: {exc!r}")
    failed.append((page.path, f"{type(exc).__name__}: {exc}"))
    continue
```

The summary-dict shape (`list[tuple[Path, str]]`) stays compatible; only the
string content is enriched.

### WR-02: `passthrough_original` does not guard against `cleaned_dir` escaping via a relative `cleaned_dir.name`

**File:** `manga_ai_studio/core/image_io.py:109-124`
**Issue:**
`passthrough_original` writes to `cleaned_dir / original.name`. Unlike
`_run_batch_task` (which has the T-02-03 `cleaned_dir.name == "cleaned"` name
guard), `passthrough_original` performs **no** validation on `cleaned_dir`. It
trusts the caller entirely. Today the only caller is `_run_batch_task` (which
has already passed its own guard), so this is defense-in-depth, not an open
hole — but the function is `public` (no leading underscore) and documented as
"used by the batch loop", so a future caller bypassing the guard would write
`original.name` into an arbitrary directory.

The deeper concern: `original.name` is taken verbatim from the source filename.
`Path.name` strips directory components, so path traversal via `../` in the
name is not possible — but a filename collision is: if two source pages share
a basename (e.g. across different subfolders that got flattened, or a Windows
case-insensitivity collision), `copy2` silently overwrites the earlier output.
This is a latent data-loss vector for the passthrough branch that the re-encode
branch (`save_image_optimized` to the same `cleaned_dir / page.path.name`) also
has, but the passthrough branch is the one where byte-identical source
preservation is the explicit contract (D-03).

**Fix:**
Either (a) make the guard symmetric by asserting the name at the top of
`passthrough_original`, or (b) document the caller contract more loudly. The
collision case is the real risk:

```python
def passthrough_original(original: Path, cleaned_dir: Path) -> Path:
    """..."""
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    dest = cleaned_dir / original.name
    if dest.exists():
        # Two source pages flattened to the same basename — refuse to
        # silently overwrite the earlier passthrough output.
        raise FileExistsError(
            f"passthrough destination already exists: {dest} "
            f"(basename collision between source pages)"
        )
    shutil.copy2(original, dest)
    return dest
```

(If silent overwrite is the intended "last wins" semantics, document it
explicitly instead.)

### WR-03: Cancel path can leave `progress_bar` shown on the first of two cleanup invocations

**File:** `manga_ai_studio/gui/main_window.py:1886-1932`
**Issue:**
`_on_batch_cleanup` is connected to BOTH `aborted` and `finished` (intentional,
Pitfall 7). On a cancel the worker emits `aborted` then `finished`
(`worker_thread.py:155-165`: the `Abort` branch emits `aborted`, the `finally`
always emits `finished`). The cleanup is documented as idempotent, and the
state-flag resets (`_op_running = False`, `file_table.setEnabled(True)`) are
genuinely idempotent.

However the *status text* write is NOT purely idempotent: on the first
(`aborted`) call, `cancelled` is True so the tail block sets status to
"Cancelled" and clears `_batch_cancelled`. On the second (`finished`) call,
`cancelled` is now False, so the tail block is skipped — BUT
`_refresh_current_page_after_batch(batch_mode)` is also skipped on the first
call (because `cancelled` was True) and RUNS on the second call. On that second
call `batch_mode` is still the real mode (it is only reset to `None` *after*
the refresh call, on whichever invocation runs first). So on the cancel path:

1. `aborted` → cleanup: refresh SKIPPED (cancelled=True), flags cleared,
   `_batch_mode` set to `None`, status="Cancelled".
2. `finished` → cleanup: refresh RUNS (cancelled=False), with `batch_mode=None`
   because step 1 already nulled it.

The refresh's detect-only branch is gated on `batch_mode == "detect"`, so a
`None` mode falls through to the clean-containing branch, which calls
`set_image_from_path(cleaned)` and clears the canvas mask overlay. For a
detect-only batch that was cancelled, this is wrong: it reloads the
(non-existent for detect) cleaned file (no-op, `cleaned.exists()` is False) and
clears the canvas mask overlay that the user may have been mid-review on.

The visible symptom is subtle (canvas mask overlay cleared after cancelling a
detect batch), and it only manifests because Qt delivers `aborted` and
`finished` as two separate queued slots. The test suite does not exercise this
double-fire path (the cancel tests `monkeypatch` the batch fn to a plain
return, so the real `Abort`-then-`finished` sequence is not driven through the
production worker).

**Fix:**
Make the cleanup strictly idempotent by guarding the whole body on a
sentinel, OR capture-and-clear the mode atomically so the second call sees a
consistent "already cleaned up" state:

```python
def _on_batch_cleanup(self, _args) -> None:
    cancelled = self._batch_cancelled
    batch_mode = self._batch_mode
    if not self._batch_active and not self._op_running:
        # Second (finished) call after an aborted call already cleaned up.
        return
    if not cancelled:
        self._refresh_current_page_after_batch(batch_mode)
    self._op_running = False
    self._batch_active = False
    self._batch_mode = None
    self._batch_cancelled = False
    self.file_table.setEnabled(True)
    self.progress_bar.hide()
    self._refresh_action_states()
    if cancelled:
        self.status_bar_left.setText(self._batch_cancelled_status_text())
```

The early-return guard makes the second call a true no-op. Add a regression
test that drives a real `Worker` raising `Abort` and asserts the canvas mask
survives the double-fire.

### WR-04: `export_page` filter selection is incomplete — `.webp` / `.bmp` source pages get a non-matching default filter

**File:** `manga_ai_studio/gui/main_window.py:1651-1663`
**Issue:**
`export_page` builds the save-dialog filter from the source suffix:
`.png` → `"PNG (*.png)"`, `.jpg/.jpeg` → `"JPEG (*.jpg *.jpeg)"`, else →
`"PNG (*.png);;JPEG (*.jpg *.jpeg)"`. The open-image dialog (line 604) accepts
`.png *.jpg *.jpeg *.webp *.bmp`, and `_load_folder` / `validate_image_path`
accept the same set, so a `.webp` or `.bmp` page can be loaded and then
exported. For such a page the else-branch defaults the filter to PNG/JPEG only
— the user is forced to re-encode to a different format with no "WebP" or "BMP"
option, even though `save_image_optimized` / `_SUFFIX_TO_FORMAT` support both.
The user can type a `.webp` filename manually, but the dialog's filter won't
suggest it and on some platforms Qt appends the active filter's extension,
silently converting a `.webp` export to `.png`.

This is a UX inconsistency between the open and export format families, not a
correctness crash. But it is a real surprise for the documented PROJ-02
"Export Page" workflow on non-PNG/JPEG sources.

**Fix:**
Extend the filter family to match the open dialog and `_SUFFIX_TO_FORMAT`:

```python
suffix = current.suffix.lower()
if suffix == ".png":
    filt = "PNG (*.png)"
elif suffix in (".jpg", ".jpeg"):
    filt = "JPEG (*.jpg *.jpeg)"
elif suffix == ".webp":
    filt = "WebP (*.webp)"
elif suffix == ".bmp":
    filt = "BMP (*.bmp)"
else:
    filt = "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;BMP (*.bmp)"
```

### WR-05: `_on_batch_finished` status text can be clobbered by the subsequent `_on_batch_cleanup` refresh on detect-only batches

**File:** `manga_ai_studio/gui/main_window.py:1856-1872` (finished) and `1948-2032` (refresh)
**Issue:**
On a successful detect-only batch the signal order is `result` then `finished`.
`_on_batch_finished` sets the status to "Cleaned N/N pages" (also see CR-01).
Then `_on_batch_cleanup` runs `_refresh_current_page_after_batch("detect")`,
which for the detect branch calls `canvas.set_mask(...)` or clears the overlay.
Neither of those writes the status bar, so the text survives — BUT
`_refresh_current_page_after_batch`'s clean-containing branch (lines 2020-2032)
calls `canvas.set_image_from_path(cleaned)`, and on the detect path that branch
is not reached, so this is fine for detect.

The real interaction: `_on_batch_finished` calls `_refresh_action_states()`
(line 1872), and `_on_batch_cleanup` ALSO calls `_refresh_action_states()`
(line 1928). Between the two, `_refresh_current_page_after_batch` runs and may
change `canvas.has_mask()` / `has_mask_content()`. So the action enable states
computed in `_on_batch_finished` are stale by the time cleanup finishes — but
cleanup recomputes them, so the final state is correct. The only artifact is a
brief window where (e.g.) the Inpaint action is enabled based on the pre-refresh
mask state. This is benign because the user cannot act in that window (the
signals are queued and processed sequentially on the GUI thread).

This is a code-smell / ordering fragility warning, not a functional bug: the
two handlers redundantly refresh action states and the finished handler's
refresh is always overwritten. It makes the code harder to reason about (which
refresh is "the" one?).

**Fix:**
Drop the `_refresh_action_states()` call from `_on_batch_finished` — cleanup is
guaranteed to run next (Pitfall 7) and its refresh reflects the post-refresh
canvas state, which is the correct one. Or, equivalently, document that
`_on_batch_finished` must NOT mutate enable state because cleanup owns it.

### WR-06: `batch_runner` re-reads the page image in `detect_and_clean` mode after detect already decoded it (wasted I/O + a second failure surface)

**File:** `manga_ai_studio/core/batch_runner.py:149-182`
**Issue:**
In `detect_and_clean` mode the loop (1) reads the image as BGR via
`_read_image_bgr(page.path)` for `det_model.detect`, then (2) discards that
buffer, then (3) re-reads the SAME file as BGR again and converts to RGB for
the inpaint call. The 02-03 SUMMARY explicitly documents this as a deliberate
decision ("Re-reading keeps detect-only mode free of the inpaint RGB conversion
... the read is cheap relative to the model calls"). That trade-off is
defensible for detect-only code separation, but it has a correctness angle the
summary does not acknowledge: the two reads can observe DIFFERENT file contents
if the file is mutated between them (an external editor, a sync client, or —
relevant for this app — a concurrent batch on the same folder). In that case
the detected mask corresponds to image state A and the inpaint consumes image
state B, producing a mask/result misalignment that is invisible until the user
inspects the output.

This is a narrow race (the file_table nav-gate prevents the app's own
`on_page_selected` from firing during a batch, but external mutation is
ungated), and for the common case (no external mutation) it is purely a doubled
I/O cost. Flagging as WARNING because the SUMMARY's justification ("cheap
relative to model calls") is true for the model cost but glosses the
correctness angle, and because the fix is cheap.

**Fix:**
Read once, convert twice. Hold the BGR buffer across both branches:

```python
if mode in ("detect", "detect_and_clean"):
    image_bgr = _read_image_bgr(page.path)
    mask_refined, _blk_list = det_model.detect(image_bgr)
    page.mask = numpy_binary_to_mask_qimage(mask_refined).copy()

if mode in ("clean", "detect_and_clean"):
    if not page.has_mask_content():
        passthrough_original(page.path, cleaned_dir)
        continue
    # Reuse the already-read BGR for detect_and_clean; read fresh for clean.
    image_bgr = image_bgr if mode == "detect_and_clean" else _read_image_bgr(page.path)
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    ...
```

## Info

### IN-01: `image_file.has_mask_content` does a lazy import on every call

**File:** `manga_ai_studio/core/image_file.py:106-110`
**Issue:**
`has_mask_content` imports `mask_to_numpy_binary` inside the method body on
every invocation. The 02-02 SUMMARY documents this as deliberate ("keeps the
dataclass module import-light and avoids circular-import risk"). The circular
risk is real in principle, but `mask_editor.py` does not import `image_file`
(verified: no circular edge exists today), so the lazy import is precautionary
rather than necessary. In `batch_runner._run_batch_task` this method is called
once per page in clean mode, so for a 100-page batch this is 100 redundant
`from ... import` lookups (Python caches the module in `sys.modules` so the
cost is a dict lookup, not a re-parse — negligible).

No behavior bug. Flagging because the precaution no longer matches the actual
dependency graph and a top-level import would be clearer.

**Fix:** Optional — move `from manga_ai_studio.core.mask_editor import mask_to_numpy_binary`
to module top of `image_file.py`. If the circular risk is later reintroduced,
revert.

### IN-02: `batch_runner` exception handler uses a bare `except Exception` that catches `Abort` if `Abort` ever inherits from `Exception`

**File:** `manga_ai_studio/core/batch_runner.py:183`
**Issue:**
The per-page `try/except Exception` (line 183) wraps the page body. `Abort` is
defined in `worker_thread.py:80` as `class Abort(Exception)`, so `except
Exception` WOULD catch it. This is safe today ONLY because the `abort_flag`
check + `raise Abort()` lives at the loop TOP (line 137-138), BEFORE the
try-block — so an `Abort` can never be raised from inside the per-page body
under the current code. But the coupling is implicit and fragile: if a future
change moves any abort-check inside the page body, or if an adapter ever raises
`Abort` itself, the bare `except Exception` would silently swallow the cancel
and the batch would continue instead of aborting.

**Fix:**
Make the exclusion explicit so the invariant is self-documenting:

```python
except Exception as exc:  # D-04: per-page failure non-fatal
    if isinstance(exc, Abort):
        raise  # never swallow a cancel
    logger.error(f"Batch: page {page.path.name} failed: {exc!r}")
    failed.append((page.path, str(exc)))
    continue
```

### IN-03: `compute_mask_bbox` returns `int` coords but the inpaint handler casts them again with `int()`

**File:** `manga_ai_studio/gui/main_window.py:1536` vs `2058-2081`
**Issue:**
`compute_mask_bbox` already returns `tuple[int, int, int, int]` (line 2081:
`return x1, y1, x2 - x1 + 1, y2 - y1 + 1`, all already `int(...)`-cast at
lines 2079-2080). `_on_inpaint_finished` re-casts with
`x1, y1, bw, bh = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])`. The
re-cast is harmless (int(int) is idempotent) but suggests the author did not
trust the callee's return type, which is a minor readability smell. Not a bug.

**Fix:** Optional — drop the redundant `int()` calls in `_on_inpaint_finished`
and trust the annotated return type, OR add a comment that the cast is
defense-in-depth against a future numpy-scalar return.

### IN-04: Test `test_batch_clean_uses_current_canvas_mask_edits` comment says "D-03 gate then passthroughs" but the assertion is on `received_masks == []`

**File:** `tests/test_gui_batch.py:666-715`
**Issue:**
The test's narrative comment (lines 702-705) says the D-03 gate "passthroughs
page_a -> the inpainter is NEVER called for page_a", and the assertion is
`received_masks == []`. This is correct for page_a (whose mask was flushed to
empty). But the batch is on TWO pages (page_a + page_b from `_load_two_pages`),
and page_b's mask was never touched — it stays `None` (never detected), so
page_b ALSO passthroughs via D-03 and the inpainter is never called for it
either. The assertion `received_masks == []` therefore passes for BOTH pages
being passthrough'd, but the test's stated intent is specifically about page_a.
A failure of the Bug D fix (stale persisted mask on page_a read by the batch)
would still be caught (the inpainter would be called once for page_a), so the
test is not vacuous — but it does not tightly isolate the page_a flush
behavior from page_b's coincidental passthrough.

Not a test-reliability bug (the test would still fail if the fix regressed),
just a comment/intent mismatch.

**Fix:** Optional — for tightness, either (a) pre-populate page_b's mask with
content so only page_a's empty-mask flush is under test and the inpainter is
called exactly once (for page_b), or (b) clarify the comment that both pages
passthrough and the assertion is "inpainter never called at all".

---

## Notes on specifically-requested review targets

**D-11 seam correctness (`on_page_selected`, lines 653-747):** Traced in full.
The OUTGOING index is correctly read from `_last_page_index` (NOT
`_current_page_index()`, which has already flipped to the incoming page via
`select_path`). The incoming restore correctly uses `_current_page_index()`
post-flip. `.copy()` is present at both boundaries (lines 705, 734). The
`_last_page_index = self._current_page_index()` tail assignment (line 747)
correctly runs AFTER the restore so the next navigation captures this page as
outgoing. **Seam is correct.** The one residual concern is that
`_last_page_index` is never reset when a new folder is loaded via `_set_pages`
— the first `on_page_selected` after a folder open reads the PREVIOUS folder's
last index. But `_set_pages` rebuilds `self.image_files` (line 642) before
calling `on_page_selected(first.path)` (line 648), so by the time
`on_page_selected` runs, `_last_page_index` points into the OLD list which no
longer exists — the range check `0 <= outgoing_idx < len(self.image_files)`
guards against the index being valid for the NEW (different-length) list, but
if the old and new lists happen to share a valid index range, the outgoing
mask of the old folder's page N would be written into the new folder's page N.
In practice `_set_pages` is followed immediately by loading the first page,
and the outgoing-save only fires `if self.canvas.has_mask()` — but a leftover
canvas mask from the previous folder could be persisted into the new folder's
page. This is a latent cross-folder contamination risk worth a follow-up
(defensive `self._last_page_index = None` at the top of `_set_pages`).

**Bug D flush (`_flush_current_canvas_mask_to_data_model`, lines 1792-1823):**
Correct. Mirrors seam step 1 exactly, with the same `.copy()` discipline and
the same range guard. No edge cases missed for the current-page path.

**Bug D1 mode-aware refresh (`_refresh_current_page_after_batch`,
lines 1948-2032):** Correct for the single-fire case. The detect branch
restores via `set_mask(image_files[idx].mask.copy())` and the empty-mask
sub-branch clears the overlay. The double-fire concern (WR-03) is the only
residual. The "what if `_batch_mode` is None at refresh time" and "what if
current page index is None" edge cases raised in the phase context are both
handled: `batch_mode == "detect"` short-circuits a None mode to the
clean-containing branch (which is wrong on the cancel double-fire path — see
WR-03), and `current is None` / `idx is None` early-returns (lines 1982-1984,
1995-1998).

**Concurrency / re-entrancy (`_op_running` + `_batch_active` + file_table
disable):** The nav-gate (`file_table.setEnabled(False)` at dispatch,
re-enabled at cleanup) is correct for preventing the app's own
`on_page_selected` write/write race. The two-flag scheme (`_op_running` vs
`_batch_active`) is sound: `_op_running` gates ALL model actions;
`_batch_active` gates the Cancel action specifically. Both are cleared in
`_on_batch_cleanup`. Re-entrancy is gated by the `if self._op_running: return`
guard at the top of `_dispatch_batch` (line 1705), `detect_text`, `inpaint`,
and `export_page`. **No re-entrancy hole found.**

---

_Reviewed: 2026-07-25T21:21:10Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

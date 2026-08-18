"""Batch driver for the Phase 2 FLOW-03 cleaning pipeline.

This module is the pure-Python, GUI-free, model-agnostic page loop that the
Phase 2 ``MainWindow`` (plan 04) wires into the Phase 1 ``Worker(QRunnable)`` +
``SharableFlag``/``Abort`` machinery. Per D-05 it reuses the Phase 1
``backend_factory`` adapters and the Worker pipeline verbatim; it does NOT
vendor PanelCleaner's CLI ``inpainting.inpaint_page`` driver (D-05: re-implement
the loop on the ``TorchLamaModel.inpaint`` adapter) nor the rejected
``processing.generate_output`` orchestration shape.

Three thin entry points (D-01) operate on the currently-open folder's pages:

- ``batch_detect``            — detect masks per page, persist onto
  ``ImageFile.mask`` (the D-11 slot from plan 02). No inpainting.
- ``batch_clean``             — inpaint every page using its current mask (the
  detected mask + any hand-edits), save into ``cleaned/``. Detection is NOT
  re-run; masks are read back via ``ImageFile.has_mask_content`` (plan 02).
- ``batch_detect_and_clean``  — detect then clean per page in one pass.

Each returns a summary dict ``{"ok": int, "failed": list[tuple[Path, str]],
"total": int}`` (D-04).

Design invariants enforced here (see the plan's ``must_haves`` truths +
``threat_model``):

- **Pitfall 3 (load ONCE)** — each model loads exactly once per batch in the
  entry-point wrapper, NEVER inside the page loop. ``_run_batch_task`` receives
  already-loaded ``det_model`` / ``inp_model`` instances.
- **D-09 / Pitfall 4 (abort between pages only)** — the ``abort_flag.get()``
  check is at the loop TOP, before any per-page read/detect/inpaint/save begins.
  Once a page's work starts it runs to completion; a canceled page is simply not
  started, so no output file is ever half-written (T-02-06).
- **D-03 (empty-mask passthrough)** — a page whose mask is empty or ``None``
  skips LaMa entirely and the original bytes are copied through unchanged via
  ``passthrough_original`` (handles both empty-after-review and
  never-detected masks; RESEARCH Open Question Q3).
- **D-04 (per-page failure non-fatal)** — every per-page body is wrapped in
  ``try/except`` that logs to loguru and appends to ``failed[]``, then continues.
- **D-07 / T-02-03 (cleaned/ only)** — ``_run_batch_task`` asserts
  ``cleaned_dir.name == "cleaned"`` at entry and writes only into
  ``cleaned_dir / page.path.name`` (T-02-01/T-02-02 defense-in-depth).
- **D-10 (per-page progress)** — ``progress_callback.emit((percent, page_name))``
  fires once per page at the loop top.

Thread-safety contract (T-01-07): the loop touches only numpy/Python + the
adapters + the plain dataclass attribute ``ImageFile.mask``. No Qt widgets are
imported (the QImage round-trip for the detected mask goes through the
``mask_editor`` numpy<->QImage helpers, not direct Qt construction); this keeps
the task fn safe to run off the GUI thread on the Phase 1 worker thread.

Phase 8 (plan 08-09, D-04): the detect branch adds the box-constrained
derivation (``build_detected_pageboxes`` + ``derive_page_mask_state``, the
08-03 seam core) INSIDE the worker loop. That computation is PIL/numpy only
(detection_boxes.py is headless by construction and hermetic-tested); the
single off-thread QImage construction (``numpy_binary_to_mask_qimage``) remains
the existing precedented site at :156. The new per-page state
(``ImageFile.boxes``, the packed ``raw_detected_mask`` / ``auto_mask`` slots)
is numpy/PIL/Python dataclasses — no Qt crosses the worker boundary.
"""

from __future__ import annotations

import cv2
import numpy as np
from loguru import logger
from pathlib import Path

from manga_ai_studio.adapters.factory import backend_factory
from manga_ai_studio.core.detection_boxes import (
    build_detected_pageboxes,
    derive_page_mask_state,
)
from manga_ai_studio.core.image_file import ImageFile
from manga_ai_studio.core.image_io import passthrough_original, save_image_optimized
from manga_ai_studio.core.mask_editor import (
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.core.mask_planes import pack_binary
from manga_ai_studio.gui.worker_thread import Abort


def _read_image_bgr(image_path: Path) -> np.ndarray:
    """Read ``image_path`` into a BGR ``(H, W, 3)`` uint8 array (CR-17).

    Uses the non-ASCII-safe ``np.fromfile`` + ``cv2.imdecode`` read copied
    verbatim from ``main_window.py:_run_detection_task`` (NOT ``cv2.imread``,
    which fails on non-ASCII Windows paths and some codecs). Raises
    ``FileNotFoundError`` when the file is unreadable so the per-page try/except
    records it in the batch summary (D-04).
    """
    try:
        image = cv2.imdecode(
            np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
        )
    except (OSError, ValueError) as exc:
        raise FileNotFoundError(f"Could not read image: {image_path}") from exc
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    return image


def _run_batch_task(
    pages: list[ImageFile],
    mode: str,
    det_model,
    inp_model,
    cleaned_dir: Path,
    masker_conf=None,
    progress_callback=None,
    abort_flag=None,
) -> dict:
    """The single page-loop task fn backing all three batch entry points.

    Drives every page through the requested ``mode`` (``"detect"``,
    ``"clean"``, or ``"detect_and_clean"``), emitting per-page progress
    (D-10), checking abort only at the loop top (D-09 / Pitfall 4), isolating
    per-page failures (D-04), skipping LaMa for empty masks (D-03), and writing
    only into ``cleaned_dir`` (D-07).

    ``det_model`` / ``inp_model`` are ALREADY-LOADED adapter instances (Pitfall
    3): the entry-point wrappers call ``.load()`` exactly once each before this
    fn runs. Pass ``None`` for a model a mode does not use.

    Phase 8 (plan 08-09, D-04): ``masker_conf`` is the active vendored
    ``MaskerConfig`` required by the detect modes — the detect branch builds
    per-page boxes from the SAME detect pass and derives the box-constrained
    mask from it (``mask_dilation_radius`` comes from the conf). ``None`` in a
    detect mode is a programming error and raises ``TypeError`` (the clean
    mode never uses it).

    ``progress_callback`` / ``abort_flag`` are auto-injected by ``Worker`` when
    the entry point is handed to ``Worker(fn, ...abort_signal=...)`` (see
    ``worker_thread.py``); they MUST be the last two kwargs with ``None``
    defaults to match the Worker contract. In direct (non-Worker) calls they
    default to ``None``.

    Returns ``{"ok": int, "failed": list[tuple[Path, str]], "total": int}``.
    Raises ``Abort`` if the cancel flag is set at a page boundary (the Worker
    converts this to ``signals.aborted``).
    """
    # T-02-03 defense-in-depth: the writer must never write to source.parent
    # directly. The output dir is DERIVED in the caller (D-06/D-07) but this
    # guard makes a path-derivation bug fail loudly instead of silently writing
    # over the source folder (T-02-01/T-02-02).
    if cleaned_dir.name != "cleaned":
        raise ValueError(
            f"batch output dir must be named 'cleaned', got: {cleaned_dir.name}"
        )

    failed: list[tuple[Path, str]] = []
    total = len(pages)
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(pages):
        # D-09 / Pitfall 4: abort check at the loop TOP ONLY. A cancel lands
        # strictly between pages; a page whose work has already started runs to
        # completion, so no output file is ever half-written (T-02-06).
        if abort_flag is not None and abort_flag.get():
            raise Abort()

        # D-10: per-page progress (percent, page_name). Computed at the loop
        # top so the UI shows "about to process page i" before the work begins.
        if progress_callback is not None:
            percent = int(i / total * 100) if total else 0
            progress_callback.emit((percent, page.path.name))

        # D-04: per-page failure is non-fatal. Any exception from the page body
        # is logged and recorded in the summary, then the loop continues.
        try:
            if mode in ("detect", "detect_and_clean"):
                if masker_conf is None:
                    raise TypeError(
                        "masker_conf is required for detect modes (plan 08-09, D-04)"
                    )
                image = _read_image_bgr(page.path)
                mask_refined, blk_list = det_model.detect(image)
                # D-04 (Phase 8): box-constrained detect — build the per-page
                # boxes from the SAME detect pass and derive the constrained
                # mask via the 08-03 seam core (build_detected_pageboxes +
                # derive_page_mask_state — the exact interactive-path core,
                # PIL/numpy only, thread-safe). Dims come from the decoded
                # image (no canvas exists in the worker); the radius is read
                # from the threaded masker_conf (MASK-01).
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                img_h, img_w = image.shape[0], image.shape[1]
                boxes = build_detected_pageboxes(blk_list, img_w, img_h)
                derivation = derive_page_mask_state(
                    image_rgb,
                    mask_refined,
                    boxes,
                    masker_conf,
                    int(masker_conf.mask_dilation_radius),
                )
                # Persist per-page state (D-04): reviewable boxes + fits, the
                # packed raw (pre-dilation) + auto binaries, and the composite
                # QImage (the existing precedented off-thread construction).
                # A page with zero boxes derives an EMPTY auto binary — the
                # same persistence shape, so the clean-stage D-03 passthrough
                # extends naturally. manual/erase stay None (batch pages have
                # no hand strokes).
                page.boxes = boxes
                page.raw_detected_mask = pack_binary(derivation.raw_binary)
                page.auto_mask = pack_binary(derivation.auto_binary)
                # The trailing .copy() is belt-and-suspenders detachment
                # (Pitfall 2; numpy_binary_to_mask_qimage already .copy()s
                # internally).
                page.mask = numpy_binary_to_mask_qimage(derivation.auto_binary).copy()

            if mode in ("clean", "detect_and_clean"):
                # D-03 GATE: a page whose mask is empty (detection found no
                # text, OR the user cleared it during review) skips LaMa
                # entirely and the original is copied through unchanged. This
                # covers both empty-after-review masks AND never-detected masks
                # (mask is None -> has_mask_content returns False -> passthrough;
                # RESEARCH Open Question Q3).
                if not page.has_mask_content():
                    passthrough_original(page.path, cleaned_dir)
                    continue

                # Read the RGB image for inpaint. The adapter contract is
                # inpaint(image_rgb, mask_binary); detect returned a grayscale
                # heatmap (fine for the mask), so we re-read the page as BGR
                # and convert to RGB to match the adapter's expectation.
                image_bgr = _read_image_bgr(page.path)
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                mask_binary = mask_to_numpy_binary(page.mask)
                result_rgb = inp_model.inpaint(image_rgb, mask_binary)
                # Write only into cleaned_dir / page.path.name (T-02-02: the
                # loop never writes to page.path or its parent). The original
                # is passed so its format/mode/DPI are preserved (plan 01).
                save_image_optimized(
                    result_rgb, cleaned_dir / page.path.name, original=page.path
                )
        except Exception as exc:  # D-04: per-page failure non-fatal
            logger.error(f"Batch: page {page.path.name} failed: {exc}")
            failed.append((page.path, str(exc)))
            continue

    return {"ok": total - len(failed), "failed": failed, "total": total}


def batch_detect(
    pages: list[ImageFile],
    det_model_path: Path,
    det_backend: str,
    cleaned_dir: Path,
    masker_conf,
    progress_callback=None,
    abort_flag=None,
) -> dict:
    """Detect masks for every page in the currently-open folder (D-01 Batch Detect).

    Resolves the detection adapter via ``backend_factory``, loads it ONCE
    (Pitfall 3), then drives ``_run_batch_task`` in ``"detect"`` mode. Detected
    masks are persisted onto each page's ``ImageFile.mask`` slot (D-11) for the
    subsequent review + ``batch_clean`` stage. No inpainting and no file output
    (the ``cleaned_dir`` name guard still runs but nothing is written).

    Phase 8 (plan 08-09, D-04): ``masker_conf`` is the active vendored
    ``MaskerConfig`` (supplied by ``MainWindow._dispatch_batch`` from the
    profile) — the detect branch also persists per-page boxes + the packed
    raw/auto plane slots so batch-detect-only runs are reviewable in the
    editor. The mask_dilation_radius and every masker fit param come from it.

    ``det_model_path`` / ``det_backend`` are supplied by ``MainWindow`` via
    ``_resolve_detection_model_path`` + ``_detection_backend()`` (plan 04); the
    cache short-circuit there (CR-11) means a 30-page batch does not re-download
    the ~80MB CTD model. The last two kwargs are auto-injected by ``Worker``.
    """
    det_model = backend_factory("detection", det_backend)
    det_model.load(det_model_path, device="auto")
    return _run_batch_task(
        pages,
        mode="detect",
        det_model=det_model,
        inp_model=None,
        cleaned_dir=cleaned_dir,
        masker_conf=masker_conf,
        progress_callback=progress_callback,
        abort_flag=abort_flag,
    )


def batch_clean(
    pages: list[ImageFile],
    inp_model_path: Path,
    inp_backend: str,
    cleaned_dir: Path,
    progress_callback=None,
    abort_flag=None,
) -> dict:
    """Inpaint every page using its current mask, save into ``cleaned/`` (D-01).

    Detection is NOT re-run: masks are read back via ``ImageFile.has_mask_content``
    (plan 02). Pages whose mask is empty/None are copied through unchanged via
    ``passthrough_original`` (D-03). Resolves + loads the inpaint adapter ONCE
    (Pitfall 3) before the loop.

    ``inp_model_path`` / ``inp_backend`` are supplied by ``MainWindow`` via
    ``_resolve_inpainting_model_path`` + ``_inpainting_backend()`` (plan 04).
    """
    inp_model = backend_factory("inpainting", inp_backend)
    inp_model.load(inp_model_path)
    return _run_batch_task(
        pages,
        mode="clean",
        det_model=None,
        inp_model=inp_model,
        cleaned_dir=cleaned_dir,
        progress_callback=progress_callback,
        abort_flag=abort_flag,
    )


def batch_detect_and_clean(
    pages: list[ImageFile],
    det_model_path: Path,
    inp_model_path: Path,
    det_backend: str,
    inp_backend: str,
    cleaned_dir: Path,
    masker_conf,
    progress_callback=None,
    abort_flag=None,
) -> dict:
    """Detect then clean every page in one pass (D-01 Batch Detect + Clean).

    The convenience one-shot: detection writes each mask onto the page's
    ``ImageFile.mask`` slot and the clean stage consumes it in the same loop
    iteration. Both adapters are resolved + loaded ONCE (Pitfall 3) before the
    loop. The same D-03 empty-mask gate applies (a page that detects no text —
    or whose boxes all fail the Phase 8 std-dev gate — is copied through
    unchanged rather than inpainted).

    Phase 8 (plan 08-09, D-04): the detect stage persists per-page boxes +
    the packed raw/auto plane slots and the composite ``ImageFile.mask`` is the
    BOX-CONSTRAINED derivation (D-02: detected content outside boxes never
    reaches the saved mask). The clean stage is UNCHANGED — it reads
    ``mask_to_numpy_binary(page.mask)``, which is now the constrained
    composite, so the LaMa call is untouched. ``masker_conf`` is supplied by
    ``MainWindow._dispatch_batch`` from the profile.
    """
    det_model = backend_factory("detection", det_backend)
    det_model.load(det_model_path, device="auto")
    inp_model = backend_factory("inpainting", inp_backend)
    inp_model.load(inp_model_path)
    return _run_batch_task(
        pages,
        mode="detect_and_clean",
        det_model=det_model,
        inp_model=inp_model,
        cleaned_dir=cleaned_dir,
        masker_conf=masker_conf,
        progress_callback=progress_callback,
        abort_flag=abort_flag,
    )

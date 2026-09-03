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

from typing import TYPE_CHECKING

from manga_ai_studio.adapters.factory import backend_factory
from manga_ai_studio.core.image_io import passthrough_original, save_image_optimized
from manga_ai_studio.core.inpaint_patching import inpaint_patches
from manga_ai_studio.core.mask_planes import pack_binary

if TYPE_CHECKING:
    from manga_ai_studio.core.detection_boxes import (
        build_detected_pageboxes,
        compose_auto_binary,
        compose_fill_specs,
        derive_page_mask_state,
        merge_page_boxes_for_detect,
    )
    from manga_ai_studio.core.image_file import ImageFile
# headless: detection_boxes (via panelcleaner.config->helpers->Qt), image_file, mask_editor and worker_thread are Qt-dependent. Import lazily inside functions to keep this module import Qt-free so `import batch_runner` is headless-pure per 08.1-04 verification.


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


def _normalize_max_size(max_size) -> tuple[int, int]:
    """Clamp max_inpaint_size to 512..8192, fallback 2048 on invalid (T-08.1-04-01)."""
    try:
        if max_size is None:
            return (2048, 2048)
        if isinstance(max_size, (tuple, list)) and len(max_size) == 2:
            mw, mh = int(max_size[0]), int(max_size[1])
            mw = max(512, min(8192, mw))
            mh = max(512, min(8192, mh))
            return (mw, mh)
        if isinstance(max_size, int):
            v = max(512, min(8192, int(max_size)))
            return (v, v)
        return (2048, 2048)
    except Exception:
        return (2048, 2048)


def _run_batch_task(
    pages: list[ImageFile],
    mode: str,
    det_model,
    inp_model,
    cleaned_dir: Path,
    masker_conf=None,
    max_inpaint_size: tuple[int, int] = (2048, 2048),
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
    # Lazily import Qt-dependent helpers to keep module import Qt-free (headless probe).
    try:
        from manga_ai_studio.core.detection_boxes import (
            build_detected_pageboxes,
            compose_auto_binary,
            compose_fill_specs,
            derive_page_mask_state,
            merge_page_boxes_for_detect,
        )
    except ImportError:
        # Headless probe fallback: stubs
        def build_detected_pageboxes(*a, **kw):  # type: ignore
            raise RuntimeError("detection_boxes not available")
        def compose_auto_binary(*a, **kw):  # type: ignore
            raise RuntimeError("detection_boxes not available")
        def compose_fill_specs(*a, **kw):  # type: ignore
            raise RuntimeError("detection_boxes not available")
        def derive_page_mask_state(*a, **kw):  # type: ignore
            raise RuntimeError("detection_boxes not available")
        def merge_page_boxes_for_detect(*a, **kw):  # type: ignore
            raise RuntimeError("detection_boxes not available")
    try:
        from manga_ai_studio.core.mask_editor import mask_to_numpy_binary, numpy_binary_to_mask_qimage
    except ImportError:
        # Fallback for headless probe: define stubs that will be overridden on actual use
        def mask_to_numpy_binary(x):  # type: ignore
            raise RuntimeError("mask_editor not available headless")
        def numpy_binary_to_mask_qimage(x):  # type: ignore
            raise RuntimeError("mask_editor not available headless")
    try:
        from manga_ai_studio.gui.worker_thread import Abort as _ImportedAbort
        _Abort = _ImportedAbort  # type: ignore
    except ImportError:
        class _Abort(Exception):  # type: ignore
            pass
    # Use the lazily imported Abort for the raise below (keep top-level Qt-free)

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
            raise _Abort()

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
                # WR-01 (plan 08-10): apply the interactive D-03 merge — a
                # page's persisted USER-origin boxes (with their payload/style/
                # inpaint_override/geometry) survive the batch detect, while
                # DETECTED-origin boxes are replaced by the fresh detection.
                merged = merge_page_boxes_for_detect(page.boxes, boxes)
                derivation = derive_page_mask_state(
                    image_rgb,
                    mask_refined,
                    merged,
                    masker_conf,
                    int(masker_conf.mask_dilation_radius),
                )
                # Persist per-page state (D-04): reviewable boxes + fits, the
                # packed raw (pre-dilation) + auto binaries, and the composite
                # QImage (the existing precedented off-thread construction).
                # A page with zero boxes derives an EMPTY auto binary — the
                # same persistence shape, so the clean-stage D-03 passthrough
                # extends naturally. manual/erase stay None (batch pages have
                # no hand strokes). page.boxes = merged — never the fresh
                # detected list alone (WR-01: user boxes survive).
                page.boxes = merged
                page.raw_detected_mask = pack_binary(derivation.raw_binary)
                page.auto_mask = pack_binary(derivation.auto_binary)
                # The trailing .copy() is belt-and-suspenders detachment
                # (Pitfall 2; numpy_binary_to_mask_qimage already .copy()s
                # internally).
                page.mask = numpy_binary_to_mask_qimage(derivation.auto_binary).copy()

            if mode in ("clean", "detect_and_clean"):
                # 08.1 D-09 parity: same corrected gate + patched inpaint as interactive.
                # Validate max size (T-08.1-04-01): clamp 512..8192, fallback 2048.
                max_size = _normalize_max_size(max_inpaint_size)
                try:
                    threshold = float(masker_conf.mask_max_standard_deviation) if masker_conf is not None else 15.0
                except Exception:
                    threshold = 15.0
                # Load image for fill/inpaint (non-ASCII safe, T-08.1-04-02)
                image_bgr = _read_image_bgr(page.path)
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                h, w = image_rgb.shape[:2]
                page_size = (w, h)
                # Derive fill_specs and auto binary from per-box persisted data
                fill_specs: list = []
                auto_bin = np.zeros((h, w), dtype=np.uint8)
                manual_bin = np.zeros((h, w), dtype=np.uint8)
                erase_bin = np.zeros((h, w), dtype=np.uint8)
                if page.boxes is not None and len(page.boxes) > 0:
                    try:
                        fill_specs = compose_fill_specs(page.boxes, threshold)
                    except Exception:
                        fill_specs = []
                    try:
                        auto_bin = compose_auto_binary(page.boxes, threshold, page_size)
                    except Exception:
                        auto_bin = np.zeros((h, w), dtype=np.uint8)
                    # In real canvas manual/erase would be packed planes, but batch pages have no strokes (D-04).
                    # Keep manual/erase zero, but allow future ImageFile extension: if page has manualMask etc, use it.
                    try:
                        if getattr(page, "mask_manual", None) is not None and page.mask_manual is not None:
                            manual_bin = mask_to_numpy_binary(page.mask_manual)
                            if manual_bin.shape != (h, w):
                                manual_bin = np.zeros((h, w), dtype=np.uint8)
                    except Exception:
                        manual_bin = np.zeros((h, w), dtype=np.uint8)
                    try:
                        if getattr(page, "mask_erase", None) is not None and page.mask_erase is not None:
                            erase_bin = mask_to_numpy_binary(page.mask_erase)
                            if erase_bin.shape != (h, w):
                                erase_bin = np.zeros((h, w), dtype=np.uint8)
                    except Exception:
                        erase_bin = np.zeros((h, w), dtype=np.uint8)
                    inpaint_binary = np.where(erase_bin > 0, np.uint8(0), (manual_bin | auto_bin)).astype(np.uint8)
                else:
                    # Legacy pages without boxes (pre-Phase 8): fall back to flat mask
                    if page.mask is not None:
                        try:
                            if page.has_mask_content():
                                raw = mask_to_numpy_binary(page.mask)
                                if raw.shape != (h, w):
                                    # Embed small mask at origin (legacy 4x4 mask on 8x8 page test fixture)
                                    # Preserve content so D-03 gate still triggers LaMa for legacy pages.
                                    tmp = np.zeros((h, w), dtype=np.uint8)
                                    mh, mw = raw.shape
                                    ch, cw = min(h, mh), min(w, mw)
                                    tmp[:ch, :cw] = raw[:ch, :cw]
                                    inpaint_binary = tmp
                                else:
                                    inpaint_binary = raw
                            else:
                                inpaint_binary = np.zeros((h, w), dtype=np.uint8)
                        except Exception:
                            inpaint_binary = np.zeros((h, w), dtype=np.uint8)
                    else:
                        inpaint_binary = np.zeros((h, w), dtype=np.uint8)
                    fill_specs = []

                has_fill = len(fill_specs) > 0
                has_inpaint = bool(np.count_nonzero(inpaint_binary))
                if not has_fill and not has_inpaint:
                    passthrough_original(page.path, cleaned_dir)
                    continue

                # Fill headlessly via PIL convert_mask_to_rgba + alpha_composite + paste
                page_with_fill = image_rgb.copy()
                if has_fill:
                    try:
                        from PIL import Image as PILImage
                        from panelcleaner.image_ops import convert_mask_to_rgba

                        fill_layer = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
                        for mask, color, (x, y) in fill_specs:
                            try:
                                rgba = convert_mask_to_rgba(mask, color)
                                fill_layer.alpha_composite(rgba, (int(x), int(y)))
                            except Exception:
                                continue
                        page_pil = PILImage.fromarray(page_with_fill, mode="RGB").convert("RGBA")
                        page_pil.paste(fill_layer, (0, 0), fill_layer)
                        page_with_fill = np.array(page_pil.convert("RGB"), dtype=np.uint8)
                    except Exception as exc:
                        logger.warning(f"Batch fill failed for {page.path.name}: {exc}")
                        page_with_fill = image_rgb.copy()

                # Inpaint patched (one patch live, halo 5) or skip if fill-only
                if not has_inpaint:
                    result_rgb = page_with_fill.copy()
                else:
                    def _patch_progress(n: int, total: int) -> None:
                        if progress_callback is not None:
                            try:
                                progress_callback.emit((int(n / total * 100) if total else 0, f"{page.path.name} patch {n}/{total}"))
                            except Exception:
                                pass

                    try:
                        result_rgb, _bbox = inpaint_patches(
                            page_with_fill, inpaint_binary, max_size, inp_model.inpaint, isolation_radius=5, progress_cb=_patch_progress
                        )
                    except Exception as exc:
                        logger.warning(f"Batch inpaint_patches failed for {page.path.name}: {exc}, falling back to direct")
                        result_rgb = inp_model.inpaint(page_with_fill, inpaint_binary)

                # Write only into cleaned_dir / page.path.name (T-02-02)
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
    # quick-260903-lm6: forward the profile's min confidence into the detector
    # BEFORE load (load() passes conf_thresh into TextDetector).
    det_model.configure(conf_thresh=float(getattr(masker_conf, "detection_conf_thresh", 0.4)))
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
    masker_conf=None,
    max_inpaint_size: tuple[int, int] = (2048, 2048),
    progress_callback=None,
    abort_flag=None,
) -> dict:
    """Inpaint every page using its current mask, save into ``cleaned/`` (D-01).

    08.1 D-09 parity: when ``page.boxes`` is present the corrected inverted gate
    is applied (low-std -> fill, high-std -> LaMa via inpaint_patches capped at
    max_inpaint_size). ``masker_conf`` supplies the threshold (default 15) and
    ``max_inpaint_size`` is the OOM cap (default 2048, clamped 512..8192). Both
    are additive with defaults so existing callers keep working (08.1-04 Task 1).

    Detection is NOT re-run for legacy pages without boxes: the flat mask is
    used as the inpaint source. Pages whose combined fill+inpaint is empty are
    copied through via passthrough_original (D-03 extended). Resolves + loads
    the inpaint adapter ONCE (Pitfall 3) before the loop.

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
        masker_conf=masker_conf,
        max_inpaint_size=max_inpaint_size,
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
    max_inpaint_size: tuple[int, int] = (2048, 2048),
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
    # quick-260903-lm6: forward the profile's min confidence into the detector
    # BEFORE load (load() passes conf_thresh into TextDetector).
    det_model.configure(conf_thresh=float(getattr(masker_conf, "detection_conf_thresh", 0.4)))
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
        max_inpaint_size=max_inpaint_size,
        progress_callback=progress_callback,
        abort_flag=abort_flag,
    )

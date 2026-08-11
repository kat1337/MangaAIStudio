"""Headless ``_ocr.json`` exporter — the D-19/D-20/D-22 published contract (plan 05-03).

Pure projection of ``PageBox`` / ``TextBlock`` state into the per-page
``_ocr.json`` file consumed by downstream typesetting tools. The JSON shape
below is a PUBLISHED CONTRACT (decision D-19, one-way): field spelling is
pinned here, once, under test, before any GUI surface exists.

Dependency contract (mirrors ``core/image_io.py``): this module imports ONLY
stdlib (plus loguru for the batch loop in Task 2) — no Qt, no torch, no
models — so it is safe to call from a worker thread and unit-testable
headless. ``Abort`` is lazy-imported inside ``batch_export_ocr`` because
``worker_thread.py`` imports ``PySide6.QtCore`` at module top; a module-top
import here would drag Qt into this no-Qt core module.

D-19 shape (one page)::

    {
      "version": "2",
      "img_width": 1600,
      "img_height": 2400,
      "blocks": [
        {
          "box": [120, 340, 480, 410],
          "vertical": false,
          "text": "First line\\nSecond line",
          "translation": "Two lines of dialogue",
          "bubble_no": 3,
          "origin": "detected" | "user",
          "style": { ... },  # D-07: TextStyle.to_dict() — "2" signals its presence
          "lines": [
            {"box": [122, 342, 478, 372], "text": "First line"},
            {"box": [122, 378, 478, 408], "text": "Second line"}
          ]
        }
      ]
    }

Design invariants enforced here:

- D-20: per-line text = ``whole_text.split("\\n")`` mapped onto the detected
  ``TextBlock.lines`` polygons (line N gets segment N; unmatched polygons
  export empty text; extra segments beyond the polygon count are dropped).
- D-22 (Task 2): output location follows page state — pristine pages write a
  sidecar ``<stem>_ocr.json`` next to the source; geometry-altered pages
  write into ``cleaned/`` because their coordinates describe the post-op page.
- D-15 seam: ``PageBox.mask`` / ``PageBox.std_dev`` are NEVER exported.
- T-05-10: the JSON body is built via ``json.dumps(..., ensure_ascii=False)``
  and written UTF-8 — no manual string concatenation into the JSON body.
- T-05-09: per-block ``lines`` is bounded by the actual ``payload.lines``
  polygons (no unbounded loops); image dims are int-validated.

Licensing: original module in the GPL v3 Manga AI Studio project (a
derivative of PanelCleaner, D-12); the mokuro ``_ocr.json`` vocabulary
borrowed under D-19 is a data-format reference, not copied code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from manga_ai_studio.core.box_model import DETECTED, USER

# The published version string — pinned once (D-19 contract). Downstream
# typesetting tools may key on it; do not change without bumping consumers.
# "2" (decision 2026-08-11, plan 07-04 Task 2 checkpoint): the D-07 style
# block (per-block "style" entry) extends the published shape — the bump
# signals the extension explicitly so consumers can branch on the version
# to detect style presence. The D-19 key set is otherwise unchanged.
OCR_JSON_VERSION = "2"


def split_text_onto_lines(text, lines: list) -> list[str]:
    """Map the whole text onto the detected line polygons (D-20).

    ``text.split("\\n")`` produces segments; line N gets segment N and
    unmatched polygons export empty text. Extra segments beyond the polygon
    count are DROPPED — the split maps onto the polygons, not the other way
    around. When ``text`` is a list (the vendored ``TextBlock`` accepts list
    storage), it is joined with ``"\\n"`` first — the Phase 4 storage is
    single-str but the defensive join keeps the export correct either way.

    Args:
        text: The block's whole text (str, or list of line strings).
        lines: The detected ``TextBlock.lines`` polygons (quad lists).

    Returns:
        One string per polygon, in polygon order.
    """
    if isinstance(text, list):
        text = "\n".join(str(segment) for segment in text)
    segments = text.split("\n")
    return [segments[n] if n < len(segments) else "" for n in range(len(lines))]


def line_box(quad: list) -> list[int]:
    """Per-line ``[x1, y1, x2, y2]`` from a 4-point polygon (D-19 ``lines[].box``).

    A ``TextBlock.lines`` entry is a quad ``[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]``;
    the exported per-line box is the axis-aligned min/max of its points.
    """
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return [min(xs), min(ys), max(xs), max(ys)]


def _payload_text(payload) -> str:
    """The block-level text as a single str (``""`` for a ``None`` payload).

    ``TextBlock.text`` may be a str OR a list (textblock.py:65); a list is
    joined with ``"\\n"`` so the block-level ``text`` field spelling stays
    consistent with the D-20 split.
    """
    if payload is None:
        return ""
    t = payload.text
    if isinstance(t, list):
        return "\n".join(str(segment) for segment in t)
    return t if t is not None else ""


def build_page_ocr_json(page_boxes: list, img_w: int, img_h: int) -> dict:
    """Build the D-19 per-page ``_ocr.json`` dict from ``PageBox`` state.

    Pure projection: reads ``PageBox.box`` / ``.origin`` / ``.bubble_no`` and
    the payload ``TextBlock`` fields only. ``PageBox.mask`` / ``std_dev`` are
    NEVER exported (D-15 seam). Zero-box pages export ``"blocks": []`` (no
    gate, no confirm — UI-SPEC surface 27).

    Args:
        page_boxes: The page's ``PageBox`` list (any order — reading order is
            the caller's concern; the model's sort_textblk_list output is
            passed through unchanged).
        img_w: Current page width in px. Must be an int (T-05-02 discipline).
        img_h: Current page height in px. Must be an int (T-05-02 discipline).

    Returns:
        The D-19 dict: ``{"version", "img_width", "img_height", "blocks"}``.

    Raises:
        ValueError: if ``img_w`` / ``img_h`` are not ints — the export
            coordinates must always describe the CURRENT page state (D-22),
            so a non-int dimension is a caller bug, not something to coerce.
    """
    # T-05-02 discipline: validate BEFORE any work (image_io.py:65-72 shape).
    if not isinstance(img_w, int) or not isinstance(img_h, int):
        raise ValueError(
            "img_w/img_h must be ints, got "
            f"{type(img_w).__name__}/{type(img_h).__name__}"
        )

    blocks = []
    for pagebox in page_boxes:
        payload = pagebox.payload
        text = _payload_text(payload)
        # D-20: per-line entries ONLY when the payload actually carries line
        # polygons; the block-level text still exports when lines are absent.
        lines = []
        if payload is not None and payload.lines:
            segments = split_text_onto_lines(text, payload.lines)
            lines = [
                {"box": line_box(quad), "text": segment}
                for quad, segment in zip(payload.lines, segments)
            ]
        blocks.append(
            {
                "box": list(pagebox.box.as_tuple),  # [x1, y1, x2, y2]
                "vertical": payload.vertical if payload is not None else False,
                "text": text,
                "translation": (payload.translation or "")
                if payload is not None
                else "",
                "bubble_no": pagebox.bubble_no,  # None -> JSON null (04-10 rule)
                "origin": pagebox.origin,  # DETECTED / USER strings (box_model)
                "style": pagebox.style.to_dict()
                if pagebox.style is not None
                else None,  # D-07: ONE spelling (TextStyle.to_dict, Pitfall 6)
                "lines": lines,
            }
        )
    return {
        "version": OCR_JSON_VERSION,
        "img_width": img_w,
        "img_height": img_h,
        "blocks": blocks,
    }


def page_ocr_json_dumps(data: dict) -> str:
    """UTF-8-safe dumps of the D-19 dict (T-05-10, Don't-Hand-Roll JSON).

    ``ensure_ascii=False`` keeps Japanese text readable on disk; the export
    file writes this string encoded utf-8 (Task 2).
    """
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Task 2: D-22 output location + write + batch loop
# ---------------------------------------------------------------------------


def ocr_json_target_dir(source_dir: Path, geometry_altered: bool) -> Path:
    """D-22: the output folder for a page's ``_ocr.json``.

    Pristine page (``geometry_altered`` False) -> the source folder itself
    (sidecar next to the page, mokuro convention). Geometry-altered page
    (crop/rotate/resize applied) -> ``source_dir / "cleaned"`` (the Phase 2
    sibling convention), because its coordinates describe the post-op page,
    not the image sitting next to it. Callers create the target via
    ``mkdir(parents=True, exist_ok=True)`` — "created if missing" (UI-SPEC
    surface 27; os-level mkdir is the A5/UI-SPEC Open Q5 resolution).
    """
    if geometry_altered:
        return source_dir / "cleaned"
    return source_dir


def default_ocr_json_path(page_path: Path, geometry_altered: bool) -> Path:
    """The D-22 default sidecar path for ``page_path``.

    ``<target_dir> / f"{page_path.stem}_ocr.json"`` — mokuro naming
    convention; ``target_dir`` per :func:`ocr_json_target_dir`.
    """
    target = ocr_json_target_dir(page_path.parent, geometry_altered)
    return target / f"{page_path.stem}_ocr.json"


def default_typeset_path(page_path: Path, geometry_altered: bool) -> Path:
    """The D-03 default bake-sidecar path for ``page_path`` (plan 07-01).

    Mirrors D-22 (the ``_ocr.json`` rule) verbatim: pristine page ->
    ``{stem}_typeset.png`` NEXT TO the source; geometry-altered page ->
    ``<source>/cleaned/{stem}_typeset.png`` (the ``cleaned/`` sibling is
    created by the writer — ``save_image_optimized`` mkdirs the parent).

    Args:
        page_path: The source page path — its ``parent`` is the D-03 anchor
            and its ``stem`` the sidecar name.
        geometry_altered: D-22 flag — pristine -> sidecar beside the source;
            altered -> ``<source>/cleaned/``.

    Returns:
        The default ``{stem}_typeset.png`` destination path.
    """
    target = ocr_json_target_dir(page_path.parent, geometry_altered)
    return target / f"{page_path.stem}_typeset.png"


def write_page_ocr_json(
    page_boxes: list,
    img_w: int,
    img_h: int,
    page_path: Path,
    geometry_altered: bool,
    path_override: Path | None = None,
) -> Path:
    """Write one page's D-19 JSON to disk and return the written path.

    Builds the dict via :func:`build_page_ocr_json`, targets the D-22 folder
    unless ``path_override`` is given (the GUI's Save As dialog overrides —
    UI-SPEC surface 27), creates the target dir ("created if missing"),
    encodes UTF-8 (the probe encoding truth), and writes atomically via
    temp-file + ``os.replace`` so a crash never leaves a half-written JSON
    (T-05-10 / T-02-06 discipline).

    Args:
        page_boxes: The page's ``PageBox`` list.
        img_w / img_h: Current page dims (int; ValueError on non-int).
        page_path: The source page path — its ``parent`` is the D-22 anchor
            and its ``stem`` the sidecar name.
        geometry_altered: D-22 flag — pristine -> sidecar beside the source;
            altered -> ``<source>/cleaned/``.
        path_override: Exact destination path; bypasses the D-22 rule.

    Returns:
        The written path (the D-22 default, or ``path_override``).
    """
    data = build_page_ocr_json(page_boxes, img_w, img_h)
    dest = path_override if path_override is not None else default_ocr_json_path(
        page_path, geometry_altered
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = page_ocr_json_dumps(data).encode("utf-8")
    # Atomic write: temp file in the same directory, then os.replace. A
    # process crash mid-write leaves only the temp file, never a truncated
    # _ocr.json that a downstream typesetting tool would mis-parse.
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, dest)
    return dest


@dataclass
class ExportPage:
    """The batch-loop input shape for :func:`batch_export_ocr`.

    Lightweight projection of the current page state — deliberately NOT
    ``ImageFile`` so the exporter stays model-free (pure stdlib) and the
    GUI can build these from ``boxes_snapshot()`` + canvas dims in plan
    05-08 without dragging the image model into the worker contract.
    """

    path: Path
    boxes: list
    img_w: int
    img_h: int
    geometry_altered: bool = False


def batch_export_ocr(pages: list, progress_callback=None, abort_flag=None) -> dict:
    """Export every page's ``_ocr.json`` in one interruptible batch (D-21).

    Mirrors ``core/batch_runner._run_batch_task`` (batch_runner.py:129-188)
    contract: abort checked at the loop TOP ONLY, per-page progress emitted
    once per page, per-page failures isolated and reported (D-04), summary
    returned as ``{"ok", "failed", "total"}``.

    ``progress_callback`` / ``abort_flag`` are auto-injected by ``Worker``
    (worker_thread.py:103-140) — they MUST stay the last two kwargs with
    ``None`` defaults. ``Abort`` is lazy-imported inside this function
    (never at module top) so the module-top import graph stays Qt-free; the
    raised exception keeps its exact ``worker_thread`` identity so the
    Worker's ``except Abort`` (worker_thread.py:155) routes cancel to the
    ``aborted`` signal. A locally-defined ``Abort(Exception)`` subclass
    would fall through to ``except Exception`` and surface cancel as an
    error — do not use that option.

    Logging discipline (T-05-05): only page stems/names + error strings are
    logged, never raw OCR/translation text (log-injection defense).

    Args:
        pages: ``ExportPage`` objects (path, boxes, img_w, img_h,
            geometry_altered).
        progress_callback: Optional callable/signal with ``.emit((percent,
            page_name))`` — called once per page at the loop top.
        abort_flag: Optional ``SharableFlag``-like object with ``.get()``.

    Returns:
        ``{"ok": int, "failed": list[tuple[Path, str]], "total": int}``.

    Raises:
        Abort: when the flag is set at a loop-top check.
    """
    # Lazy import: worker_thread.py imports PySide6.QtCore at module top
    # (line 27); importing it here keeps this core module Qt-free while
    # preserving the exact exception identity the Worker catches.
    from manga_ai_studio.gui.worker_thread import Abort

    failed: list[tuple[Path, str]] = []
    total = len(pages)

    for i, page in enumerate(pages):
        # D-09/Pitfall-4 shape: abort check at the loop TOP ONLY. A cancel
        # lands strictly between pages; a page already started runs to
        # completion, so no _ocr.json is ever half-written.
        if abort_flag is not None and abort_flag.get():
            raise Abort()

        # D-10 shape: per-page progress (percent, page_name).
        if progress_callback is not None:
            percent = int(i / total * 100) if total else 0
            progress_callback.emit((percent, page.path.name))

        # D-04: per-page failure non-fatal.
        try:
            write_page_ocr_json(
                page.boxes,
                page.img_w,
                page.img_h,
                page.path,
                page.geometry_altered,
            )
        except Exception as exc:  # D-04: per-page failure non-fatal
            logger.error(f"Batch OCR export: page {page.path.name} failed: {exc}")
            failed.append((page.path, str(exc)))
            continue

    return {"ok": total - len(failed), "failed": failed, "total": total}

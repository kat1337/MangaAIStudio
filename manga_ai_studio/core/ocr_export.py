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
      "version": "1",
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
from pathlib import Path

from manga_ai_studio.core.box_model import DETECTED, USER

# The published version string — pinned once (D-19 contract). Downstream
# typesetting tools may key on it; do not change without bumping consumers.
OCR_JSON_VERSION = "1"


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

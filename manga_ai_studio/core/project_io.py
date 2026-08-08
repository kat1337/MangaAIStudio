"""``.mas`` project container + PageBox mapping (PROJ-01, plan 05-01 Wave 1).

Origin: our own module — Phase 5 greenfield per 05-CONTEXT canonical refs
(PROJ-01 serialization is built from scratch on stdlib ``lzma``; no vendored
PanelCleaner code is involved).

Dependency contract: this module imports ONLY stdlib + numpy + Pillow — no
Qt, no torch, no models — so it is safe to call from a worker thread and
unit-testable headless (mirrors ``core/image_io.py``).

The on-disk layout is a published, one-way format (CONTEXT D-01/D-02/D-03/
D-04): a chapter is a ``<chapter>.mas-project/`` folder holding a plain-JSON
``manifest.json`` plus one self-contained ``<page>.mas`` per page. Each
``.mas`` is a custom container: a 12-byte header (magic ``b"MAS\x00"``,
format version, entry count) + an entry table whose payloads are individually
LZMA2-compressed with ``lzma.FORMAT_XZ`` (preset 6 — preset 9's ~800 MiB
compressor overhead is a regression, RESEARCH Pitfall 6/A6). Decompression
is bounded by ``MAX_ENTRY_DECOMPRESSED`` (T-05-01 memlimit mitigation).

The PageBox mapping hand-picks the serializable fields (RESEARCH Common
Operation 1) — it never calls ``TextBlock.to_dict()`` (Anti-Pattern 1:
deep-copies numpy arrays, not JSON-serializable). The D-15 seam is
preserved: ``PageBox.mask`` / ``std_dev`` are NEVER written and always
``None`` after load.

Licensing: Manga AI Studio is a derivative of PanelCleaner (GPL v3); this
module is our own GPL v3 code and must carry that attribution in all
distributions.
"""

from __future__ import annotations

import json
import lzma
import os
import struct
import tempfile
from pathlib import Path

# D-04 container header constants (RESEARCH Pattern 1, 05-RESEARCH.md:259-283).
_MAGIC = b"MAS\x00"
_FORMAT_VERSION = 1

# T-05-01: decompression bound per entry (512 MiB) — a crafted/corrupt .mas
# must not expand into a decompression bomb (RESEARCH Pitfall 6).
MAX_ENTRY_DECOMPRESSED = 512 * 1024 * 1024


class ProjectFormatError(Exception):
    """Raised when a saved-project file (``.mas`` or ``manifest.json``) is
    corrupt, malformed, or from a newer format version.

    Every untrusted-input failure on the disk -> app boundary (T-05-01 /
    T-05-02 / T-05-04) surfaces as this type so callers can present the
    "Couldn't open" error path without catching raw struct.error /
    IndexError / json / lzma exceptions.
    """


def _coerce_int(value, what: str) -> int:
    """int() coercion with the V5 untrusted-input discipline (T-05-02).

    Mirrors the Phase 3 V5 ``textblock_to_box`` coercion (box_model.py:181-
    204): JSON type confusion (float/str/bool where an int belongs) must
    surface as ProjectFormatError, never a partial session.
    """
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectFormatError(
            f"{what}: expected an int, got {type(value).__name__}"
        ) from exc


def _pack_entry(name: str, payload: bytes) -> bytes:
    """LZMA2-compress one entry: ``name_len u16 + data_len u64 + name + blob``.

    preset 6 is the lzma default — preset 9's ~800 MiB compressor overhead
    would be a regression on large chapters (RESEARCH A6 / Pitfall 6).
    """
    data = lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)
    name_b = name.encode("utf-8")
    return struct.pack("<HQ", len(name_b), len(data)) + name_b + data


def save_page_file(path: Path, entries: dict[str, bytes]) -> None:
    """Write a page container: header + entry table + LZMA2 blobs (D-04).

    Atomic: the bytes land in a same-directory temp file and are
    ``os.replace``'d onto the target, so a save interrupted mid-write can
    never corrupt an existing page file (the held-out atomic backstop,
    ``test_save_is_atomic`` in plan 05-01 Task 2).
    """
    header = _MAGIC + struct.pack("<II", _FORMAT_VERSION, len(entries))
    table = b"".join(_pack_entry(name, data) for name, data in entries.items())
    payload = header + table

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mas-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_page_file(path: Path) -> dict[str, bytes]:
    """Read a page container back into ``{name: raw_bytes}`` entries.

    Every malformed-input failure — wrong magic, truncated header, an entry
    count that overruns the blob, a garbage name/length prefix, a memlimit
    breach on decompression, or a newer format version — surfaces as
    ProjectFormatError, never as a raw struct.error / IndexError /
    LZMAError (T-05-01 entry-table sanity; ``test_malformed_entry_table_rejected``).
    Image dimensions are NOT validated here — that needs ``meta.json``
    (``validate_meta``, plan 05-01 Task 3).
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProjectFormatError(f"cannot read page file: {exc}") from exc

    if len(raw) < len(_MAGIC) or raw[: len(_MAGIC)] != _MAGIC:
        raise ProjectFormatError("not a .mas page file (bad magic)")

    try:
        version, count = struct.unpack_from("<II", raw, len(_MAGIC))
        if version != _FORMAT_VERSION:
            raise ProjectFormatError(
                f".mas format version {version} is not supported "
                f"(this build reads version {_FORMAT_VERSION})"
            )
        entries: dict[str, bytes] = {}
        off = len(_MAGIC) + 8
        for _ in range(count):
            nlen, dlen = struct.unpack_from("<HQ", raw, off)
            off += 10
            name = raw[off : off + nlen].decode("utf-8")
            off += nlen
            blob = raw[off : off + dlen]
            off += dlen
            entries[name] = lzma.decompress(
                blob, format=lzma.FORMAT_XZ, memlimit=MAX_ENTRY_DECOMPRESSED
            )
    except (struct.error, IndexError, UnicodeDecodeError, lzma.LZMAError) as exc:
        raise ProjectFormatError(f"corrupt .mas entry table: {exc}") from exc
    return entries


# ---------------------------------------------------------------- PageBox map

def pagebox_to_json(pb) -> dict:
    """Project a ``PageBox`` to JSON-safe plain data (D-15 seam preserved).

    Hand-picks the serializable fields per RESEARCH Common Operation 1 and
    NEVER writes ``mask`` / ``std_dev`` (the D-15 seam stays ``None``
    through save/load) and never calls ``TextBlock.to_dict()``
    (Anti-Pattern 1 — deep-copies numpy arrays, not JSON-serializable).
    """
    payload = pb.payload
    return {
        "box": list(pb.box.as_tuple),  # [x1, y1, x2, y2] — Box is @frozen
        "origin": pb.origin,  # D-03: "detected" | "user"
        "edited": pb.edited,
        "bubble_no": pb.bubble_no,
        "manual_override": pb.manual_override,
        "payload": None if payload is None else {
            "xyxy": list(payload.xyxy),
            "lines": payload.lines,  # list of 4-point quads
            "vertical": payload.vertical,
            "language": payload.language,
            "font_size": payload.font_size,
            "text": payload.text,  # str (Phase 4) — never TextBlock.to_dict()
            "translation": payload.translation,
        },
    }


def json_to_pagebox(d: dict):
    """Rebuild a ``PageBox`` from ``pagebox_to_json`` output (V5 coercion).

    Every numeric field is int()-coerced (box_model V5 ``textblock_to_box``
    discipline); a fresh vendored ``Box`` is always constructed — never
    mutated, it is ``@frozen``. Unknown keys are ignored; missing required
    keys raise ProjectFormatError. ``mask`` / ``std_dev`` are always
    ``None`` (D-15 seam).
    """
    from manga_ai_studio.core.box_model import PageBox
    from panelcleaner.comic_text_detector.utils.textblock import TextBlock
    from panelcleaner.structures import Box

    if not isinstance(d, dict):
        raise ProjectFormatError("pagebox data must be a JSON object")
    try:
        box_vals = d["box"]
        origin = d["origin"]
        edited = d["edited"]
        bubble_no = d["bubble_no"]
        manual_override = d["manual_override"]
        payload_raw = d["payload"]
    except KeyError as exc:
        raise ProjectFormatError(f"pagebox missing required key: {exc}") from exc

    if len(box_vals) != 4:
        raise ProjectFormatError("box must have exactly 4 coordinates")
    box = Box(*(_coerce_int(v, "box coordinate") for v in box_vals))

    payload = None
    if payload_raw is not None:
        if not isinstance(payload_raw, dict):
            raise ProjectFormatError("payload must be an object or null")
        try:
            xyxy = payload_raw["xyxy"]
        except KeyError as exc:
            raise ProjectFormatError(f"payload missing required key: {exc}") from exc
        lines = []
        for quad in payload_raw.get("lines", []) or []:
            lines.append(
                [[_coerce_int(v, "line point") for v in pt] for pt in quad]
            )
        tb = TextBlock(
            [_coerce_int(v, "xyxy") for v in xyxy],
            lines=lines,
            vertical=bool(payload_raw.get("vertical", False)),
            language=payload_raw.get("language", "unknown"),
        )
        # text/translation/font_size are assigned directly — the constructor
        # takes xyxy/lines/vertical/language positionally (textblock.py:15-49).
        tb.text = payload_raw.get("text", "")
        tb.translation = payload_raw.get("translation", "")
        tb.font_size = _coerce_int(payload_raw.get("font_size", -1), "font_size")
        payload = tb

    return PageBox(
        box=box,
        origin=origin,
        payload=payload,
        edited=bool(edited),
        bubble_no=None if bubble_no is None else _coerce_int(bubble_no, "bubble_no"),
        manual_override=bool(manual_override),
    )

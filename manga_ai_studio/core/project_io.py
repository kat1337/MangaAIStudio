"""``.mas`` project container + PageBox mapping (PROJ-01, plan 05-01 Wave 1).

Origin: our own module — Phase 5 greenfield per 05-CONTEXT canonical refs
(PROJ-01 serialization is built from scratch on stdlib ``lzma``; no vendored
PanelCleaner code is involved).

Dependency contract: this module imports ONLY stdlib + numpy + Pillow (+ loguru
for stale-mask-drop warnings, quick-260825-u9q; + natsort for the
find_project_manifest deterministic subdir scan, quick-260907-l3w) — no Qt,
no torch, no models — so it is safe to call from a worker thread and
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
deep-copies numpy arrays, not JSON-serializable). Phase 8 (plan 08-04)
CLOSES the D-15 seam: ``PageBox.mask`` / ``std_dev`` and the per-page mask
planes now serialize as OPTIONAL keys/entries (no ``_FORMAT_VERSION`` bump
— the Phase 7 optional-key pattern), so legacy Phase 5/7 files load with
all new fields defaulting to None/absent.

Licensing: Manga AI Studio is a derivative of PanelCleaner (GPL v3); this
module is our own GPL v3 code and must carry that attribution in all
distributions.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import lzma
import os
import struct
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np
from loguru import logger
from natsort import natsorted
from PIL import Image, UnidentifiedImageError

from manga_ai_studio.core.image_io import save_image_bytes
from manga_ai_studio.core.mask_planes import pack_binary

# D-04 container header constants (RESEARCH Pattern 1, 05-RESEARCH.md:259-283).
_MAGIC = b"MAS\x00"
_FORMAT_VERSION = 1

# T-05-01: decompression bound per entry (512 MiB) — a crafted/corrupt .mas
# must not expand into a decompression bomb (RESEARCH Pitfall 6).
MAX_ENTRY_DECOMPRESSED = 512 * 1024 * 1024

# T-05-04: a chapter with more pages than this is a DoS signal — load_project
# rejects it with ProjectFormatError (RESEARCH Security Domain).
MAX_PROJECT_PAGES = 1000

# D-06 suffix allowlist — mirrors canvas.py:114-126 ``validate_image_path``
# (canvas ALLOWED_IMAGE_SUFFIXES plus tif/tiff; the .mas ``original`` ref
# must pass the same gate a direct image open would, T-05-03).
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Image-dimension cap — duplicated literal from canvas.py:79
# ``MAX_IMAGE_DIMENSION = 10000`` (kept here so this headless module needs no
# Qt import; the GUI constant remains the source of truth, T-05-04).
MAX_IMAGE_DIMENSION = 10000


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


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (temp file + ``os.replace``).

    A save interrupted mid-write can never corrupt an existing target file
    (the held-out atomic backstop, ``test_save_is_atomic``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mas-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_page_file(path: Path, entries: dict[str, bytes]) -> None:
    """Write a page container: header + entry table + LZMA2 blobs (D-04).

    Atomic: the bytes land in a same-directory temp file and are
    ``os.replace``'d onto the target, so a save interrupted mid-write can
    never corrupt an existing page file.
    """
    header = _MAGIC + struct.pack("<II", _FORMAT_VERSION, len(entries))
    table = b"".join(_pack_entry(name, data) for name, data in entries.items())
    _atomic_write_bytes(path, header + table)


def load_page_file(
    path: Path, names: frozenset[str] | None = None
) -> dict[str, bytes]:
    """Read a page container back into ``{name: raw_bytes}`` entries.

    Every malformed-input failure — wrong magic, truncated header, an entry
    count that overruns the blob, a garbage name/length prefix, a memlimit
    breach on decompression, or a newer format version — surfaces as
    ProjectFormatError, never as a raw struct.error / IndexError /
    LZMAError (T-05-01 entry-table sanity; ``test_malformed_entry_table_rejected``).
    Image dimensions are NOT validated here — that needs ``meta.json``
    (``validate_meta``, plan 05-01 Task 3).

    quick-260907-nfq: ``names`` enables SELECTIVE decompression — when not
    ``None``, only the named entries are LZMA-decompressed and returned; the
    entry table is still walked in full and ``off`` advances past every
    skipped blob, but the blob is never handed to ``lzma.decompress`` and the
    entry is omitted from the result. This is the lazy-open enabler: project
    open parses only ``meta.json``/``original.json`` per page and defers the
    (large) pixel/plane blobs to first visit. Validation is NOT weakened — a
    requested-but-corrupt entry still raises ProjectFormatError, the
    name/length prefix sanity checks run for every entry, and
    ``MAX_ENTRY_DECOMPRESSED`` still bounds every decompression that DOES
    happen.
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
            if names is not None and name not in names:
                # Selective load: advance past the blob WITHOUT decompressing
                # it and omit the entry from the result.
                continue
            entries[name] = lzma.decompress(
                blob, format=lzma.FORMAT_XZ, memlimit=MAX_ENTRY_DECOMPRESSED
            )
    except (struct.error, IndexError, UnicodeDecodeError, lzma.LZMAError) as exc:
        raise ProjectFormatError(f"corrupt .mas entry table: {exc}") from exc
    return entries


# ---------------------------------------------------------------- PageBox map

def _pagebox_mask_to_json(mask) -> str | None:
    """Encode a box-cropped mode-"1" PIL mask to base64 PNG ASCII (or None).

    ``save_image_bytes`` (image_io) expects RGB pages, so the per-box mask —
    a box-cropped mode-"1" PIL image (plan 08-03 storage convention) — is
    encoded via PIL directly here, PNG in-memory, base64'd into an ASCII str.
    A mostly-empty text-box mask compresses to a few hundred bytes
    (RESEARCH §6.3 option a — the planner-chosen format).
    """
    if mask is None:
        return None
    buf = BytesIO()
    mask.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def pagebox_to_json(pb) -> dict:
    """Project a ``PageBox`` to JSON-safe plain data (D-15 seam now closed).

    Hand-picks the serializable fields per RESEARCH Common Operation 1 and
    never calls ``TextBlock.to_dict()`` (Anti-Pattern 1 — deep-copies numpy
    arrays, not JSON-serializable).

    Phase 8 (plan 08-04) SUPERSEDES the original "NEVER writes mask/std_dev"
    contract: the D-15 seam fields now serialize — ``std_dev`` (float or
    null), ``inpaint_override`` (one of ``{"always", "never"}`` or null), and
    ``mask`` (the box-cropped mode-"1" PIL image as base64 PNG, or null).
    All three are OPTIONAL load keys (Phase 7 optional-key precedent) so
    legacy Phase 5/7 files still load with defaults.

    Phase 08.1 (plan 08.1-01): adds ``fill`` to the override vocabulary and
    ``fill_color`` (optional [r,g,b] triple 0..255) — legacy files without
    those keys load with defaults (None).

    quick-260824-pqn: every payload field serializes as JSON-SAFE plain data.
    The vendored detector appends raw numpy int32 polygons to
    ``TextBlock.lines`` (textblock.py:468/474), so the old verbatim
    ``payload.lines`` passthrough raised
    ``TypeError: Object of type ndarray is not JSON serializable`` inside
    ``build_page_entries`` — silently killing Save Project in its Qt slot.
    Coordinates coerce via ``int()`` (T-QKN-01 — garbage numerics become
    plain ints, never leak into manifest JSON); text fields via null-safe
    ``str()``; ``font_size`` falls back to -1 on a non-numeric (the loader's
    own default).     ``json_to_pagebox`` already accepts both plain-list and
    ndarray-shaped input — the load side is untouched.

    quick-260825-u9q: a STALE per-box mask (mask.size != box dims — the box
    was resized after its mask was fitted) serializes as null mask +
    null std_dev + null fill_color (the fit-derived trio dies together,
    mirroring the load-side sanitization exactly), so a future SAVE can
    never produce an unloadable file.
    """
    payload = pb.payload

    def _json_str(value) -> str | None:
        return None if value is None else str(value)

    def _json_font_size() -> int:
        try:
            return int(payload.font_size)
        except (TypeError, ValueError):
            return -1

    # quick-260825-u9q save-side stale-mask guard: a mask whose size no
    # longer matches the box geometry is stale fit data; it and the
    # std_dev/fill_color measured against that geometry must never reach
    # disk (the loader would sanitize them anyway, but emitting them makes
    # the file unloadable only under the OLD loader — emit nulls instead).
    box_w = pb.box.x2 - pb.box.x1
    box_h = pb.box.y2 - pb.box.y1
    mask_stale = pb.mask is not None and pb.mask.size != (box_w, box_h)

    return {
        "box": list(pb.box.as_tuple),  # [x1, y1, x2, y2] — Box is @frozen
        "origin": pb.origin,  # D-03: "detected" | "user"
        "edited": pb.edited,
        "bubble_no": pb.bubble_no,
        "manual_override": pb.manual_override,
        "style": pb.style.to_dict() if pb.style is not None else None,  # D-07
        # Phase 8 (plan 08-04) — the D-15 seam fields close through save/load.
        "std_dev": None if mask_stale else pb.std_dev,  # float | null (None = not yet fitted)
        "inpaint_override": pb.inpaint_override,  # "always" | "fill" | "never" | null (08.1 adds fill)
        "mask": None if mask_stale else _pagebox_mask_to_json(pb.mask),  # base64 PNG | null
        "fill_color": (
            None
            if mask_stale
            else list(pb.fill_color)
            if getattr(pb, "fill_color", None) is not None
            else None
        ),  # 08.1 optional triple
        # quick-260903-lm6: per-box detector confidence (float | null).
        # None = unknown (user-drawn, scattered, or legacy box).
        "confidence": None if pb.confidence is None else float(pb.confidence),
        "payload": None if payload is None else {
            "xyxy": [int(v) for v in payload.xyxy],
            # quick-260824-pqn: nested int() coercion handles BOTH ndarray
            # quads (the detector's raw appends) and plain-list quads.
            "lines": [
                [[int(v) for v in pt] for pt in quad]
                for quad in (payload.lines or [])
            ],
            "vertical": bool(payload.vertical),
            "language": _json_str(payload.language),
            "font_size": _json_font_size(),  # int, non-numeric falls back to -1
            "text": _json_str(payload.text),  # str — never TextBlock.to_dict()
            "translation": _json_str(payload.translation),
        },
    }


def json_to_pagebox(d: dict):
    """Rebuild a ``PageBox`` from ``pagebox_to_json`` output (V5 coercion).

    Every numeric field is int()-coerced (box_model V5 ``textblock_to_box``
    discipline); a fresh vendored ``Box`` is always constructed — never
    mutated, it is ``@frozen``. Unknown keys are ignored; missing required
    keys raise ProjectFormatError.

    Phase 8 (plan 08-04): the D-15 seam fields are OPTIONAL load keys (the
    Phase 7 optional-key precedent — legacy Phase 5/7 .mas files predate
    them). Absent/None restore ``std_dev=None`` / ``inpaint_override=None`` /
    ``mask=None``; GARBAGE values are rejected structurally:
    ``std_dev`` float-coerces (TypeError/ValueError -> ProjectFormatError),
    ``inpaint_override`` must be ``None`` or one of ``{"always", "never"}``
    (the format-version rejection stance, T-08-08), and ``mask`` decodes
    base64 -> PNG with a decoded-size cross-check against the box dims and a
    full try/except wrap (T-08-06 — no raw binascii/PIL exception escapes
    the loader, the T-05-01 pattern; PIL's MAX_IMAGE_PIXELS bomb guard stays
    active).

    quick-260825-u9q: a DECODES-FINE but WRONG-SIZE mask is stale fit data
    (the box was resized after its mask was fitted), not corruption — the
    loader drops it (``mask=None``) and nulls ``std_dev``/``fill_color``
    with it (a std-dev/median-color measured against different geometry is
    meaningless), instead of rejecting the whole project. Only decode-level
    garbage still raises.
    """
    from manga_ai_studio.core.box_model import PageBox
    from manga_ai_studio.core.text_style import TextStyle
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

    # D-07: "style" is an OPTIONAL load key (Pitfall 8 — legacy .mas files
    # predate the style field). Absent/None -> TextStyle() defaults (a null
    # round-trips to the default style, never None); a crafted dict clamps
    # through TextStyle.from_dict (the V5 boundary), never raw.
    style = TextStyle.from_dict(d.get("style"))

    # Phase 8 (plan 08-04): std_dev — optional float with the V5 coercion
    # discipline. Absent/None -> None; a non-numeric value is structural
    # garbage (T-08-08).
    std_dev = None
    if d.get("std_dev") is not None:
        try:
            std_dev = float(d["std_dev"])
        except (TypeError, ValueError) as exc:
            raise ProjectFormatError("std_dev must be a number") from exc

    # Phase 8 (plan 08-04): inpaint_override — the D-14 tri-state enum.
    # Phase 08.1 (plan 08.1-01): adds "fill" (quad-state per D-04).
    # Absent/None = Auto; any OTHER value is structural garbage (stricter
    # than the format-version stance, matching it).
    override_raw = d.get("inpaint_override")
    if override_raw is not None and override_raw not in ("always", "never", "fill"):
        raise ProjectFormatError(
            f"inpaint_override must be one of 'always'/'never'/'fill' or null, "
            f"got {override_raw!r}"
        )

    # Phase 08.1 (plan 08.1-01): fill_color — optional [r,g,b] triple.
    # Absent/None -> None; garbage -> ProjectFormatError (T-08.1-01-01).
    fill_color = None
    if d.get("fill_color") is not None:
        raw_fc = d["fill_color"]
        if not isinstance(raw_fc, (list, tuple)) or len(raw_fc) != 3:
            raise ProjectFormatError("fill_color must be [r,g,b]")
        try:
            fill_color = tuple(_coerce_int(v, "fill_color") for v in raw_fc)
        except ProjectFormatError:
            raise
        except Exception as exc:
            raise ProjectFormatError(f"fill_color must be [r,g,b]: {exc}") from exc
        if not all(0 <= c <= 255 for c in fill_color):
            raise ProjectFormatError("fill_color components must be 0..255")

    # quick-260903-lm6: confidence — optional float with the same V5
    # coercion discipline as std_dev. Absent/None -> None (legacy .mas);
    # a non-numeric value is structural garbage.
    confidence = None
    if d.get("confidence") is not None:
        try:
            confidence = float(d["confidence"])
        except (TypeError, ValueError) as exc:
            raise ProjectFormatError("confidence must be a number") from exc

    if len(box_vals) != 4:
        raise ProjectFormatError("box must have exactly 4 coordinates")
    box = Box(*(_coerce_int(v, "box coordinate") for v in box_vals))

    # Phase 8 (plan 08-04): per-box mask — base64 PNG -> box-cropped mode-"1"
    # PIL image, size-cross-checked and fully wrapped (T-08-06).
    # quick-260825-u9q: a decodes-fine-but-wrong-size mask is STALE (box
    # resized after fit) — decode to None and null the fit-derived
    # std_dev/fill_color with it (they die together). inpaint_override is
    # explicit user intent and survives.
    mask_raw = d.get("mask")
    mask = None
    if mask_raw is not None:
        mask = _pagebox_mask_from_json(mask_raw, box)
        if mask is None:
            std_dev = None
            fill_color = None

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
        style=style,  # D-07 — always a TextStyle (defaults when absent/None)
        # Phase 8 (plan 08-04) — the D-15 seam fields restore.
        # Phase 08.1 adds fill_color.
        std_dev=std_dev,
        inpaint_override=override_raw,
        mask=mask,
        fill_color=fill_color,
        confidence=confidence,
    )


def _pagebox_mask_from_json(mask_value: str, box) -> Image.Image | None:
    """Decode a base64 PNG per-box mask, size-cross-checked and hardened.

    ASVS V5 / T-08-06: the base64 decode + ``Image.open`` are fully wrapped —
    ``binascii.Error`` / ``TypeError`` / ``ValueError`` / ``OSError`` /
    PIL ``UnidentifiedImageError`` / ``DecompressionBombError`` all re-raise
    as ProjectFormatError, so no raw library exception escapes the loader
    (the T-05-01 pattern). PIL's default ``MAX_IMAGE_PIXELS``
    decompression-bomb guard stays ACTIVE (not raised or disabled here; its
    ``DecompressionBombError`` surfaces as ProjectFormatError).

    quick-260825-u9q stale-tolerant contract: a mask that DECODES FINE but
    whose size does not match the declared box dims is STALE fit data (the
    box was resized after its mask was fitted), not corruption — this
    returns ``None`` and logs a loguru warning naming both sizes instead of
    raising. Only decode-level garbage raises ProjectFormatError.
    """
    try:
        png_bytes = base64.b64decode(mask_value)
        with Image.open(BytesIO(png_bytes)) as opened:
            decoded = opened.copy()  # .copy() after open — buffer lifetime
    except (
        binascii.Error,
        TypeError,
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        raise ProjectFormatError(f"invalid per-box mask: {exc}") from exc
    box_w = box.x2 - box.x1
    box_h = box.y2 - box.y1
    if decoded.size != (box_w, box_h):
        # quick-260825-u9q: stale mask (box resized after fit) — drop it,
        # never reject the whole project (T-QKN-03: the warning names both
        # sizes so a stale save is distinguishable from genuine corruption).
        logger.warning(
            "Dropping stale per-box mask: mask size {} does not match "
            "the box dims {}x{} — mask/std_dev/fill_color cleared",
            decoded.size,
            box_w,
            box_h,
        )
        return None
    return decoded.convert("1", dither=Image.NONE)


# --------------------------------------------------- page assembly + chapter

def build_page_entries(page_state: dict) -> dict[str, bytes]:
    """Project a page's live state into its ``.mas`` entries (D-03/D-05).

    ``page_state`` is a plain dict carrying:
      boxes (list[PageBox]), image_rgb (np.ndarray (H,W,3) uint8),
      mask_bin (np.ndarray (H,W) uint8 or None), geometry_altered (bool),
      original_path (Path or None), original_sha256 (str or None),
      and the OPTIONAL Phase 8 (plan 08-04) plane binaries:
      raw_binary / auto_binary / manual_binary / erase_binary
      (each an (H,W) uint8 0/255 numpy array or None — the 08-02 plane
      slots' raw binary form; D-08 raw-mask retention + the layered-model
      provenance the loader needs to restore planes without re-dilating).

    Returns the entries dict: ``meta.json`` (UTF-8 JSON with the img/mask
    dims so load can reshape without trusting blob length alone),
    ``image.png`` (in-memory PNG encode), ``mask.bin`` (raw mask bytes —
    omitted when there is no mask), ``original.json`` (the D-06 path +
    sha256 ref — present even when the source no longer exists on disk),
    and — only when the corresponding page_state binary is not None — the
    four OPTIONAL plane entries ``rawmask.bin`` / ``automask.bin`` /
    ``manualmask.bin`` / ``erasemask.bin`` holding ``pack_binary`` blobs
    (RESEARCH §6.3c on the naturally-optional entry names).
    """
    boxes = page_state["boxes"]
    image_rgb = page_state["image_rgb"]
    mask_bin = page_state.get("mask_bin")
    geometry_altered = bool(page_state.get("geometry_altered", False))
    original_path = page_state.get("original_path")
    original_sha256 = page_state.get("original_sha256")
    raw_binary = page_state.get("raw_binary")
    auto_binary = page_state.get("auto_binary")
    manual_binary = page_state.get("manual_binary")
    erase_binary = page_state.get("erase_binary")

    h, w = image_rgb.shape[:2]
    original = (
        None
        if original_path is None
        else {"path": str(original_path), "sha256": original_sha256 or ""}
    )
    meta = {
        "version": 1,
        "img": {"w": int(w), "h": int(h)},
        "mask": (
            None
            if mask_bin is None
            else {"h": int(mask_bin.shape[0]), "w": int(mask_bin.shape[1])}
        ),
        "geometry_altered": geometry_altered,
        "original": original,
        "boxes": [pagebox_to_json(b) for b in boxes],
    }
    entries = {
        "meta.json": json.dumps(meta, ensure_ascii=False).encode("utf-8"),
        "image.png": save_image_bytes(image_rgb),
    }
    if mask_bin is not None:
        entries["mask.bin"] = mask_bin.tobytes()
    if original_path is not None:
        entries["original.json"] = json.dumps(original, ensure_ascii=False).encode(
            "utf-8"
        )
    # Phase 8 (plan 08-04): the four OPTIONAL plane entries — written only
    # when the page carries the corresponding binary (legacy pages store
    # nothing; entry names are naturally optional on parse).
    for entry_name, binary in (
        ("rawmask.bin", raw_binary),
        ("automask.bin", auto_binary),
        ("manualmask.bin", manual_binary),
        ("erasemask.bin", erase_binary),
    ):
        if binary is not None:
            entries[entry_name] = pack_binary(binary).tobytes()
    return entries


def save_project(
    project_dir: Path,
    project_name: str,
    page_files: list[tuple[str, dict[str, bytes]]],
) -> Path:
    """Write a chapter project: plain-JSON manifest + per-page ``.mas`` files.

    D-01/D-02/D-04: ``project_dir`` holds ``manifest.json`` and one
    ``<stem>.mas`` per page. Non-destructive overwrite (D-02): ONLY the
    owned ``manifest.json`` and ``*.mas`` files are ever written or
    replaced — foreign folder content is untouched. Every file write is
    atomic (temp file + ``os.replace``).

    :param project_dir: the ``<chapter>.mas-project/`` folder.
    :param project_name: the chapter/session name (UTF-8 in the manifest).
    :param page_files: ``(stem, entries)`` pairs in manifest order.
    :return: the manifest path.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": _FORMAT_VERSION,
        "name": project_name,
        "pages": [{"name": stem, "file": f"{stem}.mas"} for stem, _ in page_files],
    }
    manifest_path = project_dir / "manifest.json"
    # Plain, human-readable, diffable JSON (D-04) — UTF-8, indented.
    _atomic_write_bytes(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    for stem, entries in page_files:
        save_page_file(project_dir / f"{stem}.mas", entries)
    return manifest_path


def save_project_incremental(
    project_dir: Path,
    project_name: str,
    rebuilt_pages: list[tuple[str, dict[str, bytes]]],
    all_stems: list[str],
) -> Path:
    """Write a chapter project incrementally: full manifest + ONLY the
    submitted pages' ``.mas`` files (quick-260826-vhh).

    Identical folder/atomicity/non-destructive-overwrite rules as
    :func:`save_project` (D-02), and the manifest is identical in shape —
    it lists EVERY entry of ``all_stems``, in order. But ``save_page_file``
    runs ONLY for the tuples in ``rebuilt_pages``; every other listed
    ``<stem>.mas`` already on disk is left byte-identical (a repeat save
    touching one page must not re-decode/re-hash/re-encode/re-compress the
    clean pages).

    Contract: callers MUST guarantee each ``all_stems`` entry either appears
    in ``rebuilt_pages`` or ALREADY has a resolvable ``<stem>.mas`` beside
    the manifest (the MainWindow's eligibility rule: a page is rebuilt when
    ``imf.dirty`` OR its ``<stem>.mas`` file is missing).

    :param project_dir: the ``<chapter>.mas-project/`` folder.
    :param project_name: the chapter/session name (UTF-8 in the manifest).
    :param rebuilt_pages: ``(stem, entries)`` pairs to (re)write.
    :param all_stems: every page stem in manifest order.
    :return: the manifest path.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": _FORMAT_VERSION,
        "name": project_name,
        "pages": [{"name": stem, "file": f"{stem}.mas"} for stem in all_stems],
    }
    manifest_path = project_dir / "manifest.json"
    # Plain, human-readable, diffable JSON (D-04) — UTF-8, indented.
    _atomic_write_bytes(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    rebuilt = dict(rebuilt_pages)
    for stem in all_stems:
        if stem in rebuilt:
            save_page_file(project_dir / f"{stem}.mas", rebuilt[stem])
    return manifest_path


def load_project(manifest_path: Path) -> dict:
    """Read + validate a plain-JSON chapter manifest (D-01/D-04).

    The manifest stays plain JSON (human-readable, diffable). Structure is
    validated: version int-coerced and must equal ``_FORMAT_VERSION`` (a
    newer format is rejected as corrupt — RESEARCH A9), name must be a str,
    pages a list of ``{name: str, file: str}`` capped at
    ``MAX_PROJECT_PAGES`` (T-05-04 oversized-chapter DoS signal).
    Malformed structure raises ProjectFormatError.
    """
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ProjectFormatError(f"cannot read manifest: {exc}") from exc
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise ProjectFormatError(f"malformed manifest JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProjectFormatError("manifest must be a JSON object")
    try:
        version = _coerce_int(data["version"], "manifest version")
        name = data["name"]
        pages = data["pages"]
    except KeyError as exc:
        raise ProjectFormatError(f"manifest missing required key: {exc}") from exc
    if version != _FORMAT_VERSION:
        raise ProjectFormatError(
            f"manifest format version {version} is not supported "
            f"(this build reads version {_FORMAT_VERSION})"
        )
    if not isinstance(name, str):
        raise ProjectFormatError("manifest name must be a string")
    if not isinstance(pages, list):
        raise ProjectFormatError("manifest pages must be a list")
    if len(pages) > MAX_PROJECT_PAGES:
        raise ProjectFormatError(
            f"project has {len(pages)} pages (max {MAX_PROJECT_PAGES})"
        )
    for page in pages:
        if (
            not isinstance(page, dict)
            or not isinstance(page.get("name"), str)
            or not isinstance(page.get("file"), str)
        ):
            raise ProjectFormatError(
                "manifest page entries must carry string 'name' and 'file'"
            )
    return {"version": version, "name": name, "pages": pages}


def parse_page_meta(entries: dict[str, bytes]) -> dict:
    """Decode + validate ONLY a page container's meta head (quick-260907-nfq).

    This is exactly the head of :func:`parse_page_entries` (the meta.json
    requirement, the JSON decode, the isinstance-dict check,
    :func:`validate_meta`, and the optional ``original.json`` parse) extracted
    so the lazy project open can validate every page's structural metadata
    WITHOUT decompressing the (large) pixel/plane blobs. Returns
    ``{"meta": <validated dict>, "original": <dict | None>}``.

    The untrusted-input discipline is identical to :func:`parse_page_entries`
    (T-05-01..T-05-04): a missing ``meta.json``, malformed JSON, a non-dict
    meta, or a :func:`validate_meta` failure all raise ProjectFormatError —
    a strict subset of the full parse's rejection surface, never broader.
    """
    try:
        meta_raw = entries["meta.json"]
    except KeyError as exc:
        raise ProjectFormatError(f"page file missing required entry: {exc}") from exc
    try:
        meta = json.loads(meta_raw.decode("utf-8"))
    except ValueError as exc:
        raise ProjectFormatError(f"malformed meta.json: {exc}") from exc
    if not isinstance(meta, dict):
        raise ProjectFormatError("meta.json must be a JSON object")
    validate_meta(meta)

    original = None
    if "original.json" in entries:
        try:
            original = json.loads(entries["original.json"].decode("utf-8"))
        except ValueError as exc:
            raise ProjectFormatError(f"malformed original.json: {exc}") from exc
    return {"meta": meta, "original": original}


def parse_page_entries(entries: dict[str, bytes]) -> dict:
    """Decode a page container's entries into a raw dict — the load-side
    mirror of :func:`build_page_entries`.

    Returns ``{"meta": dict, "image_png": bytes, "mask": np.ndarray | None,
    "original": dict | None, "raw_packed": np.ndarray | None,
    "auto_packed": np.ndarray | None, "manual_packed": np.ndarray | None,
    "erase_packed": np.ndarray | None}``. ``mask`` is reshaped via the dims
    recorded in ``meta["mask"]`` (never trusted from blob length alone) and
    ``.copy()``-detached from the container buffer (Pitfall 2 discipline).

    Phase 8 (plan 08-04): the four plane entries — ``rawmask.bin`` /
    ``automask.bin`` / ``manualmask.bin`` / ``erasemask.bin`` — are OPTIONAL
    (legacy Phase 5/7 projects omit them; entry names are naturally optional).
    When present, each blob is read as a ``pack_binary`` blob and validated
    against the meta-declared image dims (``ceil(h*w/8)`` bytes — the same
    cross-check discipline as the ``mask.bin`` length check, T-08-07: a
    short/long crafted blob is a ProjectFormatError, never a mis-shaped
    array). Callers unpack via ``mask_planes.unpack_binary`` with the page
    dims. Typed model construction (PageBox/ImageFile) happens at the GUI
    boundary (plan 05-05) so this module stays Qt-free.

    quick-260907-nfq: the meta head (require + decode + validate meta.json,
    parse original.json) is shared with :func:`parse_page_meta` — this
    function starts from its result and continues with the image/mask/plane
    body unchanged.
    """
    meta_head = parse_page_meta(entries)
    meta = meta_head["meta"]
    original = meta_head["original"]

    try:
        image_png = entries["image.png"]
    except KeyError as exc:
        raise ProjectFormatError(f"page file missing required entry: {exc}") from exc

    mask = None
    mask_meta = meta.get("mask")
    if mask_meta is not None:
        try:
            mask_bytes = entries["mask.bin"]
        except KeyError as exc:
            raise ProjectFormatError(
                "meta.json declares a mask but the mask.bin entry is missing"
            ) from exc
        # CR-03: ``validate_meta`` cross-checks the declared dims against each
        # other and MAX_IMAGE_DIMENSION, but never against the blob LENGTH. A
        # crafted/corrupt container whose mask.bin length does not match its
        # declared dims would otherwise raise a raw numpy ValueError here
        # ("cannot reshape array of size N into shape (h,w)") that escapes the
        # ProjectFormatError boundary and crashes the app (T-05-01..T-05-04
        # contract: every malformed-input failure surfaces as
        # ProjectFormatError). The dims are guaranteed ints in range by
        # validate_meta's _coerce_int, so ``int()`` here is safe.
        mask_h = int(mask_meta["h"])
        mask_w = int(mask_meta["w"])
        if len(mask_bytes) != mask_h * mask_w:
            raise ProjectFormatError(
                f"mask.bin length {len(mask_bytes)} does not match declared "
                f"dims {mask_h}x{mask_w}"
            )
        mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(
            mask_h, mask_w
        ).copy()

    # Phase 8 (plan 08-04): the four OPTIONAL packed plane entries. Blob
    # length is cross-checked against the meta-declared IMAGE dims (the
    # planes are page-sized, ``ceil(h*w/8)`` bytes after pack_binary; the
    # composite mask.bin dims equal the image dims whenever both present via
    # validate_meta). None when absent (legacy project).
    img_meta = meta["img"]
    page_h = int(img_meta["h"])
    page_w = int(img_meta["w"])
    plane_expected = (page_h * page_w + 7) // 8

    def _read_plane(entry_name: str) -> np.ndarray | None:
        if entry_name not in entries:
            return None
        blob = entries[entry_name]
        if len(blob) != plane_expected:
            raise ProjectFormatError(
                f"{entry_name} length {len(blob)} does not match declared "
                f"dims {page_h}x{page_w} (expected {plane_expected} bytes)"
            )
        return np.frombuffer(blob, dtype=np.uint8)

    return {
        "meta": meta,
        "image_png": image_png,
        "mask": mask,
        "original": original,
        "raw_packed": _read_plane("rawmask.bin"),
        "auto_packed": _read_plane("automask.bin"),
        "manual_packed": _read_plane("manualmask.bin"),
        "erase_packed": _read_plane("erasemask.bin"),
    }


# --------------------------------------------- D-06 checksum + D-09 climb

def sha256_file(path: Path) -> str:
    """Chunked (1 MiB reads) sha256 hexdigest of ``path`` (A7, stdlib).

    Raises OSError on unreadable files — callers decide how to surface it
    (:func:`verify_original` catches it and returns False).
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def verify_original(original_path_str: str, expected_sha256: str) -> bool:
    """D-06: True iff the referenced original resolves, has an allowed image
    suffix, and its sha256 matches ``expected_sha256``.

    Never raises (T-05-03): a missing path, a non-image suffix, or a
    checksum mismatch all return False — the embedded image stays the base
    and Show Original greys out. The path is ``Path.resolve()``'d BEFORE
    the suffix check so a crafted manifest ref pointing at an arbitrary
    file fails the suffix gate; a matching-suffix wrong file fails the
    checksum.
    """
    try:
        resolved = Path(original_path_str).resolve()
    except (OSError, ValueError):
        return False
    if resolved.suffix.lower() not in _IMAGE_SUFFIXES:
        return False
    try:
        return sha256_file(resolved) == expected_sha256
    except OSError:
        return False


def find_sibling_manifest(page_mas_path: Path) -> Path | None:
    """D-09: the sibling ``manifest.json`` for a standalone page ``.mas``.

    Returns ``page_mas_path.parent / "manifest.json"`` iff it exists AND
    :func:`load_project` succeeds on it — a corrupt sibling manifest must
    NOT silently open the page as a standalone session. When the sibling
    exists but is malformed, ProjectFormatError is raised (the caller
    decides the "chapter detected" dialog vs error — plan 05-05).
    """
    sibling = page_mas_path.parent / "manifest.json"
    if not sibling.is_file():
        return None
    load_project(sibling)  # raises ProjectFormatError when malformed
    return sibling


def find_project_manifest(directory: Path) -> Path | None:
    """Quick-260907-l3w: whether an opened folder IS or CONTAINS a project.

    Detection order (the Open Folder router's contract):
      1. ``directory / "manifest.json"`` exists -> validated via
         :func:`load_project` and returned (the folder IS a project).
      2. Else the immediate subdirectories are scanned (natsorted by path,
         deterministic first-wins): the first ``sub / "manifest.json"``
         that exists is validated and returned (the folder CONTAINS a
         project). Deliberately ONE level deep; when MULTIPLE project
         subdirectories exist the natsorted-first one is picked (there is
         no interactive chooser on the folder route).
      3. Else ``None`` — the plain-folder route (images + page ``.mas``).

    Corrupt-raises contract (the :func:`find_sibling_manifest` precedent):
    a manifest that exists but is malformed — or from a newer format
    version — raises ProjectFormatError. A corrupt project must NEVER be
    skipped so the folder silently falls through to the image route.
    Non-directory input (a file path, or a path that does not exist)
    returns ``None``.
    """
    if not directory.is_dir():
        return None
    direct = directory / "manifest.json"
    if direct.is_file():
        load_project(direct)  # raises ProjectFormatError when malformed
        return direct
    subdirs = natsorted(
        (s for s in directory.iterdir() if s.is_dir()), key=str
    )
    for sub in subdirs:
        candidate = sub / "manifest.json"
        if candidate.is_file():
            load_project(candidate)  # raises ProjectFormatError when malformed
            return candidate
    return None


# -------------------------------------------------- untrusted-input validation

def validate_meta(meta: dict) -> None:
    """Validate a page's ``meta.json`` before it shapes any session state.

    T-05-02 / T-05-04 (untrusted-file boundary):
      - ``img`` w/h must int()-coerce to values within
        [1, MAX_IMAGE_DIMENSION] (oversized dims are a DoS signal);
      - ``mask`` dims must equal the image dims when both are present;
      - ``geometry_altered`` must be a bool when present.
    Every int field coerces via :func:`_coerce_int` — JSON type confusion
    (float/str/bool where an int belongs) surfaces as ProjectFormatError,
    never a partial session (the box_model V5 ``textblock_to_box``
    discipline). Raises ProjectFormatError.
    """
    if not isinstance(meta, dict):
        raise ProjectFormatError("meta.json must be a JSON object")
    try:
        img = meta["img"]
    except KeyError as exc:
        raise ProjectFormatError(f"meta.json missing required key: {exc}") from exc
    if not isinstance(img, dict) or "w" not in img or "h" not in img:
        raise ProjectFormatError("meta.img must carry 'w' and 'h'")
    w = _coerce_int(img["w"], "meta img w")
    h = _coerce_int(img["h"], "meta img h")
    if not (1 <= w <= MAX_IMAGE_DIMENSION and 1 <= h <= MAX_IMAGE_DIMENSION):
        raise ProjectFormatError(
            f"image dimensions {w}x{h} exceed MAX_IMAGE_DIMENSION "
            f"({MAX_IMAGE_DIMENSION})"
        )

    if "geometry_altered" in meta and not isinstance(
        meta["geometry_altered"], bool
    ):
        raise ProjectFormatError("meta.geometry_altered must be a bool")

    mask_meta = meta.get("mask")
    if mask_meta is not None:
        if not isinstance(mask_meta, dict) or "h" not in mask_meta or "w" not in mask_meta:
            raise ProjectFormatError("meta.mask must carry 'h' and 'w'")
        mw = _coerce_int(mask_meta["w"], "meta mask w")
        mh = _coerce_int(mask_meta["h"], "meta mask h")
        if (mw, mh) != (w, h):
            raise ProjectFormatError(
                f"mask dims {mh}x{mw} do not match image dims {h}x{w}"
            )

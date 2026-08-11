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

import hashlib
import json
import lzma
import os
import struct
import tempfile
from pathlib import Path

import numpy as np

from manga_ai_studio.core.image_io import save_image_bytes

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
        "style": pb.style.to_dict() if pb.style is not None else None,  # D-07
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
        style=style,  # D-07 — always a TextStyle (defaults when absent/None)
    )


# --------------------------------------------------- page assembly + chapter

def build_page_entries(page_state: dict) -> dict[str, bytes]:
    """Project a page's live state into its 4 ``.mas`` entries (D-03/D-05).

    ``page_state`` is a plain dict carrying:
      boxes (list[PageBox]), image_rgb (np.ndarray (H,W,3) uint8),
      mask_bin (np.ndarray (H,W) uint8 or None), geometry_altered (bool),
      original_path (Path or None), original_sha256 (str or None).

    Returns the entries dict: ``meta.json`` (UTF-8 JSON with the img/mask
    dims so load can reshape without trusting blob length alone),
    ``image.png`` (in-memory PNG encode), ``mask.bin`` (raw mask bytes —
    omitted when there is no mask), and ``original.json`` (the D-06 path +
    sha256 ref — present even when the source no longer exists on disk).
    """
    boxes = page_state["boxes"]
    image_rgb = page_state["image_rgb"]
    mask_bin = page_state.get("mask_bin")
    geometry_altered = bool(page_state.get("geometry_altered", False))
    original_path = page_state.get("original_path")
    original_sha256 = page_state.get("original_sha256")

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


def parse_page_entries(entries: dict[str, bytes]) -> dict:
    """Decode a page container's entries into a raw dict — the load-side
    mirror of :func:`build_page_entries`.

    Returns ``{"meta": dict, "image_png": bytes, "mask": np.ndarray | None,
    "original": dict | None}``. ``mask`` is reshaped via the dims recorded in
    ``meta["mask"]`` (never trusted from blob length alone) and
    ``.copy()``-detached from the container buffer (Pitfall 2 discipline).
    Typed model construction (PageBox/ImageFile) happens at the GUI boundary
    (plan 05-05) so this module stays Qt-free.
    """
    try:
        meta_raw = entries["meta.json"]
        image_png = entries["image.png"]
    except KeyError as exc:
        raise ProjectFormatError(f"page file missing required entry: {exc}") from exc
    try:
        meta = json.loads(meta_raw.decode("utf-8"))
    except ValueError as exc:
        raise ProjectFormatError(f"malformed meta.json: {exc}") from exc
    if not isinstance(meta, dict):
        raise ProjectFormatError("meta.json must be a JSON object")
    validate_meta(meta)

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

    original = None
    if "original.json" in entries:
        try:
            original = json.loads(entries["original.json"].decode("utf-8"))
        except ValueError as exc:
            raise ProjectFormatError(f"malformed original.json: {exc}") from exc

    return {"meta": meta, "image_png": image_png, "mask": mask, "original": original}


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

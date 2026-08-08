"""``ImageFile`` — a minimal page data model.

Role-matched against PanelCleaner ``gui/image_file.py:ImageFile`` per
PATTERNS.md §core/image_file.py (lines 539-546). PanelCleaner's ``ImageFile``
holds path, thumbnail, analytics, split-children, and processing state — far
more than Phase 1 needs. We extract the minimal triad: ``path``,
``thumbnail``, and a ``mask`` slot for plan 04, plus a ``dirty`` flag for
future plan 06 history tracking.

Thumbnail size is pinned at 64px (UI-SPEC surface 3) — PanelCleaner's
``THUMBNAIL_SIZE`` is also 64, so this matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

# UI-SPEC surface 3 sidebar thumbnail size (also matches PanelCleaner
# image_file.py:21 THUMBNAIL_SIZE).
THUMBNAIL_SIZE = 64
# Letterbox pad color (UI-SPEC §Color secondary surface #2d2d33).
THUMBNAIL_PAD_COLOR = (45, 45, 51)


def _letterbox(source: QImage, size: int = THUMBNAIL_SIZE) -> QPixmap:
    """Scale ``source`` to fit ``size``x``size``, padding with #2d2d33.

    Aspect ratio is preserved; the padded area is filled with the UI-SPEC
    secondary-surface color so portrait/landscape thumbs render uniformly in
    the sidebar row (UI-SPEC surface 3).
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(*THUMBNAIL_PAD_COLOR))
    if source.isNull() or source.width() <= 0 or source.height() <= 0:
        return pixmap
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(pixmap)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawImage(x, y, scaled)
    painter.end()
    return pixmap


@dataclass
class ImageFile:
    """A single page loaded into the workspace.

    Attributes:
        path: Resolved filesystem path to the source image.
        thumbnail: A 64x64 letterboxed ``QPixmap`` preview, or ``None`` until
            :meth:`load_thumbnail` is called.
        mask: The page mask ``QImage`` (``None`` until plan 04 paints one).
        boxes: The page's text boxes as ``list[PageBox]`` (``None`` until
            plan 03-04's detection seam populates it). Mirrors the Phase 2
            ``mask`` slot pattern (D-11 of Phase 2). Per-page, in-memory only
            — NO disk serialization in Phase 3 (PROJ-01 ``.mas`` save is
            Phase 5).
        dirty: True when the page has unsaved edits (mask/inpaint) — reserved
            for plan 06 history tracking.
        original_verified: D-06 (Phase 5). ``True`` when the original source
            image is verified available: for ``.mas``-loaded pages this
            means the referenced path resolves with an image suffix AND its
            sha256 matches; a normal image/folder open also sets it ``True``
            (the page was loaded from that path). When ``False``, Show
            Original is greyed out and the embedded page image is the base.
        geometry_altered: D-22 (Phase 5). ``True`` once a geometry image op
            (crop/rotate/resize) has been applied to the page — drives the
            ``_ocr.json`` export location rule (altered pages export into
            ``cleaned/``). Levels does NOT set it (A4 — geometry-free).
    """

    path: Path
    thumbnail: QPixmap | None = None
    mask: QImage | None = None
    boxes: list["PageBox"] | None = None
    dirty: bool = False
    # D-06 original-availability flag (set at .mas load via verify_original;
    # True for normal image/folder open — the source loaded from that path).
    original_verified: bool = False
    # D-22 geometry-op flag (set True by crop/rotate/resize; levels does NOT).
    geometry_altered: bool = False

    def load_thumbnail(self, size: int = THUMBNAIL_SIZE) -> None:
        """Load ``self.thumbnail`` from ``self.path`` as a letterboxed pixmap.

        Loads via ``QImage`` and scales aspect-preserved into ``size``x``size``
        padded on ``#2d2d33`` (UI-SPEC surface 3). The source ``QImage`` is
        ``.copy()``-detached so the thumbnail outlives the load buffer (RESEARCH
        Pitfall 2). On read failure ``self.thumbnail`` is set to an empty (pad
        only) pixmap — the caller shows the "file unreadable" dialog.
        """
        image = QImage(str(self.path))
        if image.isNull():
            self.thumbnail = _letterbox(QImage(), size)
            return
        image = image.copy()
        self.thumbnail = _letterbox(image, size)

    def clear_mask(self) -> None:
        """Drop the current mask (Edit -> Clear Mask, plan 04/06)."""
        self.mask = None
        self.dirty = True

    def has_mask_content(self) -> bool:
        """Return whether the persisted mask has non-zero content (D-03 / D-11).

        Reuses :func:`manga_ai_studio.core.mask_editor.mask_to_numpy_binary`
        exactly — do NOT reimplement the alpha scan (PATTERNS.md file 1 +
        RESEARCH.md §Code Examples "Mask content check"). Mirrors
        :meth:`EditorCanvas.has_mask_content` (canvas.py:348-365) but operates
        on the persisted ``self.mask`` slot rather than the live canvas buffer.

        Consumed by Plan 02-03 Batch Clean's D-03 empty-mask gate (skip LaMa
        and passthrough the original when no mask content is present) and by
        any future code reading per-page masks off the data model.
        """
        if self.mask is None or self.mask.isNull():
            return False
        from manga_ai_studio.core.mask_editor import mask_to_numpy_binary

        return bool(mask_to_numpy_binary(self.mask).any())

    def has_boxes(self) -> bool:
        """Return whether this page has any text boxes (mirrors the trivial
        shape of the Phase 2 ``mask`` slot's content check).

        Boxes have no pixel content to scan, so unlike
        :meth:`has_mask_content` this is a plain truthiness check on
        ``self.boxes`` (an empty list is falsy). Mirrors the
        :meth:`EditorCanvas.has_boxes` analog (plan 03-03).

        Consumed by plan 03-05's per-page persistence seam (save/restore
        boxes across page switches) and any future code reading per-page
        boxes off the data model.
        """
        return bool(self.boxes)


# NOTE: PageBox import is deferred to runtime via TYPE_CHECKING to keep the
# module import cycle-safe for the GUI layer that constructs ImageFile at
# startup. The ``boxes`` field annotation uses a forward-reference string
# (``list["PageBox"]``) so it resolves lazily under
# ``from __future__ import annotations``.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manga_ai_studio.core.box_model import PageBox  # noqa: F401

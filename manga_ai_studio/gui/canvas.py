"""EditorCanvas — the image display canvas.

A ``QGraphicsView`` subclass holding a ``QGraphicsScene`` with a layered stack
(image ``QGraphicsPixmapItem`` -> mask ``QGraphicsPixmapItem`` -> empty-state
overlay text). Plan 01 built the skeleton (image + mask item stack, anchor,
matte, allocation-limit reset); this plan adds the pan/zoom mechanics, an
empty-state overlay, and image path/size validation.

The pan/zoom MECHANICS are adapted from PanelCleaner's ``image_viewer.py`` (GPL
v3, vendored per D-12) — specifically ``QImageReader.setAllocationLimit(0)``
(image_viewer.py:45) for large-page safety, ``setTransformationAnchor(
AnchorUnderMouse)`` (image_viewer.py:56), ``ZOOM_TICK_FACTOR = 1.25``
(image_viewer.py:14), the half-step wheel zoom (image_viewer.py:144-154), the
100x max / half-viewport min clamp (image_viewer.py:221-255), and the
pixel-accurate smoothing toggle (image_viewer.py:116). The mask-editing tool
surface (brush/rect/lasso/eraser) is our own reimplementation patterned after
MangaCleaner_GPU (reference-only per D-12) and lands in plan 04.

Security:
    - ``validate_image_path`` calls ``Path.resolve()`` and enforces a suffix
      allowlist (T-01-02 path-traversal mitigation).
    - ``validate_image_size`` rejects images larger than 10000x10000 px
      (T-01-03 large-image DoS mitigation).
    - ``set_image_from_path`` calls ``QImage.copy()`` to detach the load buffer
      from the transient ``QImage(path)`` (RESEARCH Pitfall 2).
"""

from __future__ import annotations

import os
from pathlib import Path
from weakref import ref as _weakref

import numpy as np

from PySide6 import Shiboken
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox
from panelcleaner.structures import Box
from manga_ai_studio.core.mask_editor import (
    DEFAULT_BRUSH_SIZE,
    MASK_PAINT_COLOR,
    ToolMode,
    clamp_brush_size,
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
    paint_mask_lasso,
    paint_mask_rect,
    paint_mask_stroke,
)
from manga_ai_studio.core.mask_planes import (
    MaskPlanesSnapshot,
    pack_binary,
    unpack_binary,
)
from manga_ai_studio.gui.box_item import BoxItem, CornerHandle, origin_hue
from manga_ai_studio.gui.inline_editor import InlineEditor


# Maximum zoom factor (image_viewer.py:233 clamps at 100).
MAX_ZOOM_FACTOR = 100.0
# Each Ctrl+ +/- step multiplies the zoom by this factor. Ctrl+wheel uses the
# square root (half-step) for finer control (image_viewer.py:14, 144-154).
ZOOM_TICK_FACTOR = 1.25
# Images larger than this on either axis are rejected (T-01-03 DoS mitigation).
MAX_IMAGE_DIMENSION = 10000
# Accepted image suffixes (T-01-02 suffix allowlist).
ALLOWED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})
# Phase 8 (plan 08-02, MASK-06 / UI-SPEC §39): the mask-painting tools. Under
# one of these the box branch of mousePressEvent becomes Alt-gated — without
# Alt, presses on box bodies AND handles fall through to painting (no dead
# spots under boxes); with Alt, today's box interaction runs (D-15). CROP is
# deliberately NOT here (D-17 — the Crop tool keeps today's box behavior) and
# neither is MOVE/Pan.
PAINT_TOOLS = frozenset(
    {ToolMode.BRUSH, ToolMode.RECTANGLE, ToolMode.LASSO, ToolMode.ERASER}
)

# Phase 3 box-layer geometry (UI-SPEC §Z-order + §Spacing exceptions). The box
# layer sits above the mask overlay, below the tool preview/cursor. The
# empty-box hint sits below the preview_item so a create-drag preview is not
# obscured by the hint text.
BOX_LAYER_Z = 100
EMPTY_BOX_HINT_Z = 850
# D-06 / T-03-05: minimum box size enforced on create-release and resize-release
# (clamp, not cancel — prevents zero-area boxes that would break later geometry).
MIN_BOX_SIZE = 8
# UI-SPEC §12e: the Alt+drag create preview is an amber dashed pen (distinct
# from the cyan mask-rect preview on the same preview_item).
_BOX_CREATE_PREVIEW_COLOR = QColor(245, 166, 35, 200)
# UI-SPEC §12f empty-box-layer hint copy (12px, muted #9a9aa2).
_EMPTY_BOX_HINT_TEXT = (
    "No text boxes yet. Alt+drag on the page to draw one, "
    "or Tools \u2192 Detect Text (D)."
)

# Phase 5 crop tool (plan 05-07, UI-SPEC surface 24a + §Z-order). The dim-out
# overlay composits the outside-of-crop region with 4 rects at
# rgba(0,0,0,0.45) — deliberately darker than the 0.24 preview fills and
# lighter than opaque black (the discarded area reads as "cut away" without
# competing with the artwork). z=880 sits BELOW the crop border
# (``preview_item`` z=900) and ABOVE the box layer (z=100) so the dashed
# keep-edge renders on top of the dim while boxes inside the crop region are
# visibly dimmed outside it. The 8x8 scene-px minimum reuses MIN_BOX_SIZE
# (UI-SPEC §Spacing exceptions — a crop smaller than the box minimum is a
# no-op, not a degenerate edit).
CROP_DIM_Z = 880
_CROP_DIM_COLOR = QColor(0, 0, 0, int(255 * 0.45))


def _disable_qimage_allocation_limit() -> None:
    """Disable Qt's default 128MB allocation cap so large manga pages load.

    Adapted from PanelCleaner ``image_viewer.py:45``. Called at module import.
    """
    QImageReader.setAllocationLimit(0)


# Apply once at import time (UI-SPEC surface 2 large-image safety).
_disable_qimage_allocation_limit()


def validate_image_path(path: Path) -> bool:
    """Return True iff ``path`` resolves and has an allowed image suffix.

    T-01-02 mitigation: every file-open path (folder scan, drag-drop, recent
    files) flows through this check. ``Path.resolve()`` normalizes ``..``
    segments and resolves symlinks; the suffix allowlist rejects anything that
    is not a supported raster image.
    """
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return False
    return resolved.suffix.lower() in ALLOWED_IMAGE_SUFFIXES


class EditorCanvas(QGraphicsView):
    """Image display canvas.

    Scene stack: image pixmap item (bottom) -> mask pixmap item (above) ->
    empty-state text overlay (top, hidden when an image is loaded). The mask
    item is initialized to a transparent overlay matching the image size; mask
    content is painted in plan 04.
    """

    # Emitted whenever the zoom factor changes (UI-SPEC surface 1 status bar).
    zoom_changed = Signal(float)
    # Emitted ONCE per completed mask-editing stroke (mouseRelease), NOT per
    # mouseMove. The plan-06 history/undo manager consumes this to snapshot the
    # mask (UI-SPEC surface 8).
    mask_modified = Signal()
    # Phase 3: emitted on box create/move-commit/resize-commit/delete (mirrors
    # mask_modified). MainWindow consumes this to push a BOXES snapshot onto
    # the history stack (plan 03-02) + update the status-bar box count.
    #
    # CR-01 fix: the payload is the PRE-mutation snapshot (the state to restore
    # TO on undo). The history's pop returns the most-recently-pushed checkpoint
    # (LIFO), so for a box edit to be undoable in ONE Ctrl+Z the pushed snapshot
    # must be the BEFORE state (mirrors the image side's pre-edit push contract,
    # history_manager "Each push records the PRE-edit region so undo restores
    # it"). Each emit site captures boxes_snapshot() BEFORE the mutation and
    # passes it here.
    boxes_modified = Signal(list)
    # Plan 04-06 (D-01): emitted when a user box is created on Alt+drag
    # draw-release (``_commit_create``), carrying the new BoxItem. MainWindow
    # subscribes and dispatches the OCR worker — the manga-ocr model call
    # itself NEVER runs on the GUI thread (RESEARCH Pitfall 6, T-01-07). A
    # box below the 8x8 create threshold never emits (the Phase 3 no-op
    # returns before this signal — UI-SPEC §14).
    ocr_requested = Signal(object)
    # Plan 05-07 (UI-SPEC surface 24a): emitted when the Crop tool applies an
    # armed crop rect (Enter). Carries the rect in SCENE coordinates as a
    # QRectF; the MainWindow handler converts to image-pixel ints (clamped)
    # and runs the crop apply path. The tool STAYS active after emission (the
    # user may crop again; switching tools is the exit).
    crop_committed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Scene + layered items. Store as _scene so the inherited scene()
        # accessor (which returns the same object after setScene) is not
        # shadowed by an instance attribute (plan 01 deviation #3).
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.image_item = QGraphicsPixmapItem()
        self.mask_item = QGraphicsPixmapItem()
        # mask_item stacks above image_item (added after it).
        self._scene.addItem(self.image_item)
        self._scene.addItem(self.mask_item)

        # Mask-editing overlay items (plan 04). preview_item holds the
        # dashed-cyan rect/lasso drag preview (z=900); cursor_item is the
        # brush-size outline circle that follows the pointer (z=1000, above
        # everything). Reimplemented patterned after MangaCleaner_GPU
        # canvas.py:31-42 (D-12 reference-only).
        self.preview_item = QGraphicsPathItem()
        self.preview_item.setPen(
            QPen(QColor(0, 212, 255, 200), 2, Qt.PenStyle.DashLine)
        )
        self.preview_item.setZValue(900)
        self._scene.addItem(self.preview_item)

        self.cursor_item = QGraphicsEllipseItem()
        self.cursor_item.setZValue(1000)
        self._scene.addItem(self.cursor_item)

        # Phase 3 box layer (UI-SPEC §11/§12, D-02). A QGraphicsItemGroup at
        # z=100 holding BoxItem children, independent of mask_item visibility.
        # The empty_box_hint (§12f) sits at z=850 (below the preview_item) and
        # shows only when the layer is visible AND zero boxes exist.
        self.box_layer = QGraphicsItemGroup()
        self.box_layer.setZValue(BOX_LAYER_Z)
        self._scene.addItem(self.box_layer)
        self._box_items: list[BoxItem] = []  # live box layer membership
        # G-07-3 (plan 07-11): an optional callable producing the TextStyle
        # for NEW user-drawn boxes (``Callable[[], TextStyle | None]``).
        # MainWindow sets it to the app-level default-family provider; the
        # canvas stays Qt-free of QSettings (the is-primary-owner weakref
        # precedent — the provider seam, not a second QSettings accessor).
        # None return keeps today's behavior: the renderer falls back to
        # TextStyle() (Liberation Sans).
        self.new_box_style_provider = None
        # Plan 07-06 (G-07-6 blocker): removed BoxItems awaiting DEFERRED
        # release (see _retire_boxes / _release_graveyard — the teardown-UAF
        # fix). Removal sites must never drop the last Python refs to a
        # removed item synchronously mid-event-loop; the graveyard holds them
        # until the zero-timeout release timer fires (after the scene's
        # pending UpdateRequest flush).
        self._box_graveyard: list[BoxItem] = []
        self._graveyard_pending = False
        self.empty_box_hint = QGraphicsTextItem(_EMPTY_BOX_HINT_TEXT)
        self.empty_box_hint.setDefaultTextColor(QColor("#9a9aa2"))
        hint_font = QFont("Segoe UI", 10)  # ~12px at 96 DPI
        self.empty_box_hint.setFont(hint_font)
        self.empty_box_hint.setZValue(EMPTY_BOX_HINT_Z)
        self._scene.addItem(self.empty_box_hint)

        # Plan 04-05: the inline text editor (UI-SPEC §15, D-05/D-07/D-08). A
        # transient QGraphicsProxyWidget(QTextEdit) overlay owned by the canvas
        # — the single editor instance reused across edit sessions. Constructed
        # AFTER setScene so its proxy can be parented to the scene (the §15
        # anti-pattern: parent to the SCENE, never to the BoxItem). The
        # mouse-press dispatch guard at the top of mousePressEvent is the
        # click-away commit mechanism (RESEARCH Pitfall 3).
        self._inline_editor = InlineEditor(self)

        # Phase 3 box-interaction state. _resizing_box / _moving_box /
        # _creating_box are the press-time flags; _resize_corner tracks which
        # handle is being dragged; _box_drag_anchor is the starting scene pos.
        self._box_overlay_visible = True
        # Phase 4 text-overlay visibility (D-12 — the THIRD independent layer).
        # Default True: D-09 upgrades boxes to display objects, so text renders
        # by default once a box carries text. Independent of _box_overlay_visible
        # (Shift+M) and the mask overlay (M).
        self._text_overlay_visible = True
        self._resizing_box: BoxItem | None = None
        self._resize_corner: str = ""
        self._box_drag_anchor = QPointF()
        self._resize_start_rect = QRectF()
        self._moving_box: BoxItem | None = None
        # Phase 7 (plan 07-02, D-08/D-09): multi-select state.
        self._group_move: dict[BoxItem, QRectF] = {}
        self._primary_box: BoxItem | None = None
        self._selection_order: list[BoxItem] = []
        self._pending_boxes_op_name: str | None = None
        self._creating_box = False
        self._create_anchor = QPointF()
        # CR-01 fix: the PRE-mutation snapshot captured at the START of a
        # box interaction (move/resize/create), emitted on commit as the
        # boxes_modified payload so the history push records the BEFORE state
        # (the state to restore to on undo). See boxes_modified docstring.
        self._boxes_interaction_start_snapshot: list = []

        # Reposition corner handles on zoom (UI-SPEC §12b — they stay 8x8
        # viewport px via ItemIgnoresTransformations, but their scene-space
        # position is recomputed so they track the corners through the zoom).
        self.zoom_changed.connect(self._on_zoom_changed_reposition_handles)

        # Empty-state overlay (UI-SPEC §Surface 9 / §Copywriting). A top-most
        # text item shown only when no image is loaded.
        self._empty_heading = QGraphicsTextItem("No page open")
        self._empty_body = QGraphicsTextItem(
            "Open a single image or a folder of images to begin cleaning."
        )
        self._empty_hint = QGraphicsTextItem(
            # D-11 (deferred from 05-UAT/05-UI-REVIEW): the stale copy
            # advertised "Open Image…" with the shortcut that Phase 5
            # re-bound to Open Project… (main_window.py:311). Open Folder
            # binds Ctrl+Shift+O (main_window.py:305) — the locked UI-SPEC
            # §Copywriting wording (heading + body stay verbatim).
            "File \u2192 Open Folder\u2026 (Ctrl+Shift+O)   \u00b7   or drag files here"
        )
        for item in (self._empty_heading, self._empty_body, self._empty_hint):
            item.setDefaultTextColor(QColor("#9a9aa2"))
            item.setZValue(2000)
            self._scene.addItem(item)
        # Heading is larger + semibold (UI-SPEC typography: 16px/600).
        heading_font = QFont("Segoe UI", 13)
        heading_font.setWeight(QFont.Weight.DemiBold)
        self._empty_heading.setFont(heading_font)
        # Body 14px regular.
        self._empty_body.setFont(QFont("Segoe UI", 11))
        # Hint 12px accent.
        hint_font = QFont("Segoe UI", 10)
        self._empty_hint.setFont(hint_font)
        self._empty_hint.setDefaultTextColor(QColor("#00d4ff"))

        # View configuration.
        self.setRenderHint(QPainter.Antialiasing)
        # Zoom toward cursor (adapted from image_viewer.py:56).
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Canvas matte #0b0b0e (UI-SPEC §Color, MangaCleaner_GPU canvas.py:21 token).
        self.setBackgroundBrush(QBrush(QColor(11, 11, 14)))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Zoom/pan state (image_viewer.py:47-57, 221-260).
        self.zoom_factor = 1.0
        # min zoom is computed dynamically (half viewport) inside zoom().
        self._panning = False
        self._last_pan_pos = QPointF()
        self._space_held = False
        self._cursor_overridden = False

        # Mask overlay visibility state (plan 03). The mask_item starts
        # transparent with no content; set_mask populates + shows it.
        self._mask_visible = False

        # Mask-editing tool state (plan 04). The editable mask QImage is held
        # in self._mask (distinct from mask_item, the QGraphicsPixmapItem that
        # DISPLAYS it). current_tool drives the mouse-event dispatch;
        # is_eraser_modifier is the transient Shift toggle on Brush (UI-SPEC
        # surface 6 modifier).
        self.current_tool = ToolMode.MOVE
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.is_eraser_modifier = False
        self._mask: QImage | None = None  # set in set_image / set_mask
        # Phase 8 (plan 08-02, RESEARCH §2.2 Option B): the three planes the
        # composite ``_mask`` is recomposed from — manual strokes, the erase
        # ledger, and the derived auto binary. Initialized page-sized in
        # set_image; reset in clear. ``_mask`` stays the displayed/LaMa/
        # persisted composite so every existing consumer (get_mask /
        # has_mask / has_mask_content / mask_to_numpy_binary(get_mask()))
        # is untouched.
        self._mask_manual: QImage | None = None
        self._mask_erase: QImage | None = None
        self._auto_bin: np.ndarray | None = None
        self._is_painting = False
        self._last_pt = QPointF()
        self._start_pt = QPointF()
        self._lasso_path = QPainterPath()

        # Crop-tool state (plan 05-07, UI-SPEC surface 24a). The armed-rect
        # state machine: a drag defines ``_crop_rect`` (scene coords, clamped
        # to the page) which stays ARMED after release — dim-out overlay +
        # preview persist until Enter applies (``_apply_armed_crop`` ->
        # ``crop_committed``) or Esc cancels; the tool stays active either
        # way. Unlike the mask-rect there is NO commit-on-release (drag-then-
        # decide). ``_crop_dim_items`` holds the 4 composited dim rects
        # (z=880); ``_crop_anchor`` is the drag origin. The armed state is
        # removed on tool switch, page switch, and image replacement.
        self._crop_rect: QRectF | None = None
        self._crop_drag_active = False
        self._crop_anchor = QPointF()
        self._crop_dim_items: list = []

        # Inpaint preview state (plan 05, UI-SPEC surface 7). _original_image_numpy
        # holds the pre-inpaint image (for the before/after toggle);
        # _inpainted_qimage is the displayed (inpainted) image; _showing_original
        # tracks which side of the toggle is currently displayed. All three reset
        # on set_image/clear (a new page clears the inpaint history).
        self._original_image_numpy: np.ndarray | None = None
        self._inpainted_qimage: QImage | None = None
        self._showing_original = False
        # Cursor follows the pointer even without a held button.
        self.setMouseTracking(True)
        self._update_cursor_visuals()

        # Show the empty state on a fresh canvas.
        self._update_empty_state()

    # ----------------------------------------------------------------- image I/O
    def set_image(self, pixmap: QPixmap) -> None:
        """Display ``pixmap`` on the image layer and reset the mask overlay."""
        self.image_item.setPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))

        # Initialize the editable mask QImage to a transparent image of the
        # same size (plan 04: self._mask is the painting target).
        mask = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        mask.fill(Qt.GlobalColor.transparent)
        self._mask = mask
        self.mask_item.setPixmap(QPixmap.fromImage(mask))
        self.mask_item.setVisible(True)
        self._mask_visible = True

        # Phase 8 (plan 08-02): a new page = fresh planes (manual/erase
        # transparent at the page size, no auto content).
        manual = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        manual.fill(Qt.GlobalColor.transparent)
        self._mask_manual = manual
        erase = QImage(pixmap.size(), QImage.Format.Format_ARGB32)
        erase.fill(Qt.GlobalColor.transparent)
        self._mask_erase = erase
        self._auto_bin = None

        # A new page clears the inpaint preview history (plan 05 UI-SPEC surface 7).
        self._original_image_numpy = None
        self._inpainted_qimage = None
        self._showing_original = False
        # A new page clears any armed crop rect (plan 05-07 — stale geometry).
        self._clear_crop_state()

        self._update_empty_state()

    def set_image_from_path(self, path: Path) -> bool:
        """Validate, load, and display the image at ``path``.

        Returns True on success, False if the path failed validation or the
        image could not be read (the caller is expected to show the UI-SPEC
        "file unreadable" dialog on False).

        Security: runs ``validate_image_path`` (T-01-02) and
        ``validate_image_size`` (T-01-03), and detaches the load buffer via
        ``QImage.copy()`` (RESEARCH Pitfall 2).
        """
        if not validate_image_path(path):
            return False

        image = QImage(str(path.resolve()))
        if image.isNull():
            return False
        if not self.validate_image_size(image.width(), image.height()):
            return False
        # Detach the buffer so the pixel data outlives the transient load
        # (RESEARCH Pitfall 2 — QImage lifetime crashes).
        image = image.copy()
        self.set_image(QPixmap.fromImage(image))
        return True

    def clear(self) -> None:
        """Reset both image and mask layers."""
        self.image_item.setPixmap(QPixmap())
        self.mask_item.setPixmap(QPixmap())
        self.setSceneRect(QRectF())
        self.zoom_factor = 1.0
        self._mask_visible = False
        self._mask = None
        # Phase 8: no page -> no planes (set_image re-seeds page-sized ones).
        self._mask_manual = None
        self._mask_erase = None
        self._auto_bin = None
        self._original_image_numpy = None
        self._inpainted_qimage = None
        self._showing_original = False
        self._clear_crop_state()
        self.setTransform(QTransform())
        self._update_empty_state()

    # ------------------------------------------------------------- mask layer
    def set_mask(self, mask_qimage: QImage) -> None:
        """Route a detection mask into the AUTO plane (Phase 8, UI-SPEC A10).

        NEW CONTRACT (plan 08-02): the incoming mask ``QImage`` (a grayscale
        or binary heatmap from the detection adapter) is thresholded (any
        pixel with a non-zero red channel — BGRA byte order) and replaces
        ONLY the derived auto plane via :meth:`set_auto_binary`. Re-detection
        no longer clobbers the canvas: manual strokes and the erase ledger
        SURVIVE (a re-detect replaces the auto plane only; RESEARCH §2.4 /
        UI-SPEC A10 "Your hand-painted strokes are kept"). The displayed
        composite is recomposed as ``(manual | auto) & ~erase``.

        Phase 1 behavior note: ``set_mask`` stays signal-silent (detection is
        a non-undoable baseline — Pitfall 13-1) and still shows the
        ``mask_item`` (the rgba(255, 0, 0, 0.63) overlay token).

        QImage buffer discipline (RESEARCH Pitfall 2, PATTERNS.md §Shared
        Pattern 5): ``mask_qimage.copy()`` defensively detaches any numpy
        buffer the producer attached before reaching this method; the
        recomposed composite is ``QImage.copy()``-detached inside
        :func:`numpy_binary_to_mask_qimage`.
        """
        # Defensive copy — detach any numpy/shared buffer (RESEARCH Pitfall 2).
        mask_qimage = mask_qimage.copy()
        w = mask_qimage.width()
        h = mask_qimage.height()
        if w == 0 or h == 0:
            return

        # Convert to ARGB32 so pixel layout is uniform BGRA in memory (Qt's
        # native byte order on little-endian: bytes are B, G, R, A).
        src = mask_qimage.convertToFormat(QImage.Format.Format_ARGB32)
        # constBits() returns a memoryview in PySide6; materialize to bytes so
        # numpy can consume it (RESEARCH Pitfall 2 — buffer must outlive the
        # QImage, and .copy() above already detached the source).
        arr = np.frombuffer(bytes(src.constBits()), dtype=np.uint8).reshape(h, w, 4)
        # For a grayscale-converted ARGB32 source the R/G/B channels are equal;
        # treat any pixel with a non-zero red channel as a mask pixel.
        mask_pixels = arr[:, :, 2] > 0  # R channel (BGRA byte order)
        auto_bin = np.where(mask_pixels, np.uint8(255), np.uint8(0))

        # Phase 8: the thresholded heatmap IS the auto plane (the tinting the
        # Phase 1 body did inline is exactly what recompose_mask does for
        # every plane change — numpy_binary_to_mask_qimage). The planes are
        # page-sized, so a non-page-sized incoming mask (Phase 1 accepted any
        # size; callers/tests pass smaller heatmaps) is fitted onto the page
        # grid top-left anchored — the same anchoring the Phase 1 pixmap
        # displayed at (QGraphicsPixmapItem at the scene origin).
        if self._mask_manual is not None and not self._mask_manual.isNull():
            page_h = self._mask_manual.height()
            page_w = self._mask_manual.width()
            if (h, w) != (page_h, page_w):
                fitted = np.zeros((page_h, page_w), dtype=np.uint8)
                rows, cols = min(h, page_h), min(w, page_w)
                fitted[0:rows, 0:cols] = auto_bin[0:rows, 0:cols]
                auto_bin = fitted
        self.set_auto_binary(auto_bin)
        # Preserve the Phase 1 display side-effect: an incoming detection
        # mask shows the overlay (recompose itself is visibility-neutral).
        self.mask_item.setVisible(True)
        self._mask_visible = True

    def set_auto_binary(self, bin_arr: np.ndarray | None) -> None:
        """Replace the DERIVED auto plane with ``bin_arr`` and recompose.

        ``bin_arr`` is an ``(H, W)`` uint8 array (any non-zero value is
        content; the stored copy is normalized to 0/255). ``None`` means "no
        auto content". Stored via ``.copy()`` (Pitfall 2 — the caller's
        array may be a view into a worker result buffer). Signal-silent
        (detection / re-dilate / radius change are non-undoable settings —
        RESEARCH §9).
        """
        if bin_arr is not None:
            if bin_arr.ndim != 2 or bin_arr.dtype != np.uint8:
                raise ValueError(
                    f"expected (H,W) uint8 binary, got shape={bin_arr.shape} "
                    f"dtype={bin_arr.dtype}"
                )
            bin_arr = np.where(bin_arr > 0, np.uint8(255), np.uint8(0)).copy()
            # A mask whose dims disagree with the page would broadcast-misalign
            # the recompose (silent corruption) — fail loudly instead.
            if self._mask_manual is not None and bin_arr.shape != (
                self._mask_manual.height(),
                self._mask_manual.width(),
            ):
                raise ValueError(
                    f"auto binary shape {bin_arr.shape} does not match the "
                    f"page size "
                    f"({self._mask_manual.height()}, {self._mask_manual.width()})"
                )
        self._auto_bin = bin_arr
        self.recompose_mask()

    def recompose_mask(self) -> None:
        """Rebuild the composite ``_mask`` from the three planes (plan 08-02).

        ``composite = (manual_bin | auto_bin) & ~erase_bin`` — rendered via
        :func:`numpy_binary_to_mask_qimage` (the tinted rgba(255,0,0,0.63)
        overlay, ``.copy()``-detached) and refreshed through the
        :meth:`update_mask_display` path. Signal-SILENT (Pitfall 13-1 —
        detection/re-dilate/restore recompositions are non-undoable and must
        not re-push onto the history stack).

        Call sites (Pitfall 13-14 — NEVER from mouseMoveEvent; live feedback
        during a stroke paints the display composite directly and the commit
        recomposes): stroke commit (``_end_paint``), plane changes
        (``set_auto_binary`` / ``set_planes`` / ``clear_mask``), and undo
        restores (``apply_undo_mask``).
        """
        if self._mask_manual is None or self._mask_manual.isNull():
            # No page (or no page-sized planes) — nothing to recompose.
            return
        h = self._mask_manual.height()
        w = self._mask_manual.width()
        manual_bin = mask_to_numpy_binary(self._mask_manual)
        erase_bin = mask_to_numpy_binary(self._mask_erase)
        auto_bin = (
            self._auto_bin
            if self._auto_bin is not None
            else np.zeros((h, w), dtype=np.uint8)
        )
        composite = (manual_bin | auto_bin) & ~erase_bin
        self._mask = numpy_binary_to_mask_qimage(composite)
        self.update_mask_display()

    def planes_snapshot(self) -> MaskPlanesSnapshot:
        """Return a detached snapshot of the live three planes (plan 08-02).

        The manual/erase QImages are ``.copy()``-detached and the auto plane
        is ``pack_binary``-packed (~H*W/8 bytes). Consumed by the MainWindow
        mask push hook (the MASK stack value type) and the D-11 persistence
        seam. Raises RuntimeError when no page is loaded (callers guard on
        page presence — ``_current_undo_state`` / ``_on_mask_modified``).
        """
        if self._mask_manual is None or self._mask_manual.isNull():
            raise RuntimeError("planes_snapshot requires a loaded page")
        return MaskPlanesSnapshot(
            manual=self._mask_manual.copy(),
            erase=self._mask_erase.copy(),
            auto_packed=(
                pack_binary(self._auto_bin) if self._auto_bin is not None else None
            ),
        )

    def set_planes(
        self,
        manual_qimage: QImage | None,
        erase_qimage: QImage | None,
        auto_bin: np.ndarray | None,
    ) -> None:
        """Restore the three planes and recompose (plan 08-02 Task 2 seam).

        The undo-restore / page-restore counterpart of
        :meth:`planes_snapshot`. ``.copy()``-detaches every incoming plane
        (Pitfall 2 — history and ImageFile values must not alias the live
        canvas). A ``None``/null manual or erase QImage is replaced with a
        fresh transparent plane at the restore size — derived from the
        incoming planes in priority order (manual, erase, auto_bin shape),
        falling back to the CURRENT page size; this lets a geometry-op
        write-back rebuild the planes at CHANGED dims by passing null
        QImages plus the new-dims auto binary. Signal-silent (a pure
        restore).
        """
        if (
            (manual_qimage is None or manual_qimage.isNull())
            and (erase_qimage is None or erase_qimage.isNull())
            and auto_bin is None
            and (self._mask_manual is None or self._mask_manual.isNull())
        ):
            # Nothing to restore and no page — nothing to do (callers
            # restore after set_image has seeded the page-sized planes).
            return
        # Derive the restore size: an incoming plane wins (a restore may
        # carry dims that differ from the current page — geometry undo).
        if manual_qimage is not None and not manual_qimage.isNull():
            size = manual_qimage.size()
        elif erase_qimage is not None and not erase_qimage.isNull():
            size = erase_qimage.size()
        elif auto_bin is not None:
            size = QSize(int(auto_bin.shape[1]), int(auto_bin.shape[0]))
        else:
            size = self._mask_manual.size()
        if manual_qimage is None or manual_qimage.isNull():
            manual_qimage = QImage(size, QImage.Format.Format_ARGB32)
            manual_qimage.fill(Qt.GlobalColor.transparent)
        if erase_qimage is None or erase_qimage.isNull():
            erase_qimage = QImage(size, QImage.Format.Format_ARGB32)
            erase_qimage.fill(Qt.GlobalColor.transparent)
        self._mask_manual = manual_qimage.copy()
        self._mask_erase = erase_qimage.copy()
        self._auto_bin = (
            np.where(auto_bin > 0, np.uint8(255), np.uint8(0)).copy()
            if auto_bin is not None
            else None
        )
        self.recompose_mask()

    def consume_mask_display(self) -> None:
        """Clear ALL THREE planes signal-silently after a mask consumption.

        Plan 08-10 (CR-04): inpaint and batch-clean CONSUME the mask — the
        red overlay must leave the display AND the planes, or the next
        stroke/undo/page-switch recompose would resurrect the consumed
        overlay and a re-run would re-process the already-cleaned region.

        When a page is loaded (``_mask_manual`` non-null): fill the manual and
        erase planes fully transparent, drop ``_auto_bin`` to ``None``, and
        recompose — the rebuilt composite is fully transparent, refreshed
        through ``update_mask_display``. When no page is loaded, fall back to
        the pre-existing display-only clear.

        MUST NOT emit ``mask_modified`` — consumption is not a paint action
        and must never push a mask-undo entry (the CR-16 2-stack contract the
        call sites at main_window.py invoke).
        """
        if self._mask_manual is None or self._mask_manual.isNull():
            # No page (or no page-sized planes) — the pre-existing
            # display-only clear.
            if self._mask is not None and not self._mask.isNull():
                self._mask.fill(Qt.GlobalColor.transparent)
                self.update_mask_display()
            return
        self._mask_manual.fill(Qt.GlobalColor.transparent)
        self._mask_erase.fill(Qt.GlobalColor.transparent)
        self._auto_bin = None
        self.recompose_mask()

    def toggle_mask_overlay(self) -> None:
        """Flip the mask overlay visibility (View -> Toggle Mask Overlay, M)."""
        visible = not self.mask_item.isVisible()
        self.mask_item.setVisible(visible)
        self._mask_visible = visible

    def has_mask(self) -> bool:
        """Return True iff the editable mask has content (a non-null QImage)."""
        return self._mask is not None and not self._mask.isNull()

    def has_mask_content(self) -> bool:
        """Return True iff the mask has any painted (non-transparent) pixels.

        Distinct from :meth:`has_mask` (which is True whenever a mask QImage
        exists, including the fresh transparent initialization after
        ``set_image``). Used by plan 05's Inpaint gate: running LaMa on an
        empty mask is a wasted model load, so the Inpaint action requires
        actual painted content.
        """
        if self._mask is None or self._mask.isNull():
            return False
        # Cheap content check: convert to RGBA8888 and scan the alpha channel
        # for any non-zero pixel. A fully-transparent mask has no content.
        src = self._mask.convertToFormat(QImage.Format.Format_RGBA8888)
        arr = np.frombuffer(
            bytes(src.constBits()), dtype=np.uint8
        ).reshape(src.height(), src.width(), 4)
        return bool((arr[:, :, 3] > 0).any())

    def clear_mask(self) -> None:
        """Clear ALL mask planes to empty (Edit -> Clear Mask, plan 04/08-02).

        Phase 8: the manual plane and the erase ledger are filled transparent
        and the auto plane is dropped (``None``), then the composite is
        recomposed — clear_mask empties the WHOLE mask, not just strokes.
        Keeps the single ``mask_modified`` emission (one undo entry).
        """
        if self._mask is None or self._mask.isNull():
            return
        if self._mask_manual is not None and not self._mask_manual.isNull():
            self._mask_manual.fill(Qt.GlobalColor.transparent)
        if self._mask_erase is not None and not self._mask_erase.isNull():
            self._mask_erase.fill(Qt.GlobalColor.transparent)
        self._auto_bin = None
        self.recompose_mask()
        self.mask_modified.emit()

    def get_mask(self) -> QImage | None:
        """Return the editable mask QImage (None when no page is loaded).

        Consumed by plan 05's inpaint dispatch and plan 06's history manager.
        """
        return self._mask

    def update_mask_display(self) -> None:
        """Refresh mask_item from the editable ``self._mask`` QImage.

        Called after every brush/rect/lasso/erase mutation (RESEARCH Pitfall 4
        — mutate the existing QImage in place, then refresh the pixmap; no new
        QImage is allocated per mouse-move).

        Pure display refresh: does NOT emit ``mask_modified`` (the
        plan-04 stroke-commit emission lives in ``_end_paint`` / ``clear_mask``,
        and the plan-06 undo-application path must NOT re-push onto the
        history stack — see :meth:`apply_undo_mask`).
        """
        if self._mask is None or self._mask.isNull():
            return
        self.mask_item.setPixmap(QPixmap.fromImage(self._mask))

    # ------------------------------------------------------- undo application
    def apply_undo_mask(self, snapshot: "MaskPlanesSnapshot") -> None:
        """Restore a plane snapshot from the history (plan 06/08-02, surface 8).

        REDEFINED in Phase 8 (plan 08-02 Task 2): the MASK stack values are
        now ``MaskPlanesSnapshot`` (manual/erase QImages + the packed auto
        binary). Restores all three planes via :meth:`set_planes` (which
        ``.copy()``-detaches every value from the history's internal copy so
        subsequent strokes cannot mutate the entry) and recomposes — the
        displayed composite becomes exactly the snapshot's
        ``(manual | auto) & ~erase``. NO ``mask_modified`` emission — undo
        must NOT re-push onto the stack (``test_undo_does_not_repush`` /
        ``test_undo_does_not_repush_planes`` are the regression guards;
        UI-SPEC surface 8 prohibition).
        """
        if not isinstance(snapshot, MaskPlanesSnapshot):
            raise TypeError(
                f"apply_undo_mask expects a MaskPlanesSnapshot (Phase 8 mask "
                f"stack value), got {type(snapshot).__name__}"
            )
        auto_bin = (
            unpack_binary(snapshot.auto_packed, snapshot.manual.height(), snapshot.manual.width())
            if snapshot.auto_packed is not None
            else None
        )
        self.set_planes(snapshot.manual, snapshot.erase, auto_bin)

    def apply_undo_image(self, x: int, y: int, patch_np: np.ndarray) -> None:
        """Composite a numpy patch into the displayed image (plan 06 undo).

        Used by image-undo/redo (Ctrl+Z/Ctrl+Shift+Z): the popped ``(x, y,
        patch)`` from :class:`HistoryManager` is written into the current
        image's ``[y:y+h, x:x+w]`` region. Bounds-checked (T-01-15): a patch
        that extends beyond the current image is clipped to the image rect;
        an empty/zero-size patch is a no-op.

        Buffer lifetime (RESEARCH Pitfall 2): the patch is written into the
        ``set_image_from_numpy``-built QImage, which is ``.copy()``-detached
        before storage (Pitfall-2 guard ``test_inpaint_result_display_uses_copy``
        locks this on the display path).

        Does NOT emit ``mask_modified`` (image undo is unrelated to the mask
        signal — UI-SPEC surface 8).
        """
        if patch_np is None:
            return
        current = self.get_image_numpy()
        if current is None:
            return
        h_img, w_img = current.shape[:2]
        ph, pw = patch_np.shape[:2]
        if ph == 0 or pw == 0:
            return
        # Full-frame geometry record (plan 05-04/05-06): a patch at (0, 0)
        # whose frame differs from the current image can only be a geometry
        # op's whole pre-op image — rotate/resize change the page dims, so
        # the composite path below would CLIP it to the post-op frame and the
        # undo could never restore the pre-op image. Replace the whole image
        # instead (the faithful D-14 restore; the pre-op image is recoverable
        # exactly this way). Non-origin patches keep the T-01-15 clip — a
        # stale same-frame region entry after a crop must never overwrite the
        # whole (smaller) image.
        if (x, y) == (0, 0) and (ph, pw) != (h_img, w_img):
            self.set_image_from_numpy(patch_np.copy())
            return
        # Bounds check (T-01-15): clip the patch + destination rect to the
        # current image so a stale history entry after a crop cannot corrupt
        # the image array (a Phase 5 concern; defensive now).
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(w_img, x0 + pw)
        y1 = min(h_img, y0 + ph)
        if x1 <= x0 or y1 <= y0:
            return  # fully out of bounds — no-op
        # Source sub-rect matching the clipped destination.
        sx0 = x0 - int(x)
        sy0 = y0 - int(y)
        sub = patch_np[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
        current[y0:y1, x0:x1] = sub
        # set_image_from_numpy replaces the whole image; pass no bbox so the
        # full updated numpy is stored (the .copy() discipline is inside that
        # method).
        self.set_image_from_numpy(current)

    # -------------------------------------------------- inpaint numpy bridge
    def get_image_numpy(self) -> np.ndarray | None:
        """Return the displayed image as an ``(H, W, 3)`` uint8 RGB numpy array.

        Consumed by plan 05's inpaint dispatch: the worker thread receives this
        array (NOT a QImage/QPixmap) and hands it to ``TorchLamaModel.inpaint``
        (RESEARCH Pitfall 3 — never pass Qt objects into a worker thread).

        Returns None when no image is loaded. Buffer lifetime (RESEARCH Pitfall
        2, PATTERNS.md §Shared Pattern 5): the trailing ``.copy()`` detaches the
        array from the QImage buffer before the local ``qimg`` is garbage-
        collected. ``test_inpaint_result_display_uses_copy`` is the regression
        guard (mutating the returned array must not change the displayed image).
        """
        qpix = self.image_item.pixmap()
        if qpix.isNull():
            return None
        qimg = qpix.toImage().convertToFormat(QImage.Format.Format_RGB888)
        ptr = qimg.bits()
        if ptr is None:
            return None
        h, w = qimg.height(), qimg.width()
        bytes_per_line = qimg.bytesPerLine()
        # Qt pads each scanline to 4-byte alignment, so bytes_per_line can be
        # strictly greater than w*3 (e.g. a 1497px-wide RGB888 image is 4491
        # bytes/row but Qt allocates 4492). Reshaping the raw buffer directly
        # as (H, W, 3) fails for any width where w*3 is not a multiple of 4
        # (CR-08, surfaced by a real 2081x1497 manga page). PySide6's bits()
        # returns a memoryview; materialize to bytes, then take exactly w*3
        # bytes per row and skip the padding tail.
        raw = bytes(ptr)
        if bytes_per_line == w * 3:
            # Fast path: no padding (width*3 already 4-aligned).
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
        else:
            # Strided path: slice the unpadded row content and let numpy copy
            # it into a contiguous (H, W, 3) array.
            strided = np.frombuffer(raw, dtype=np.uint8, count=h * bytes_per_line)
            arr = strided.reshape(h, bytes_per_line)[:, : w * 3].reshape(h, w, 3)
        # MANDATORY .copy() — detach from the QImage buffer before qimg GCs.
        return arr.copy()

    def set_image_from_numpy(
        self, rgb: np.ndarray, bbox: tuple[int, int, int, int] | None = None
    ) -> QImage:
        """Replace the image layer with ``rgb`` (or composite the ``bbox`` region).

        Used by plan 05's inpaint result display and the image-op apply path
        (plan 05-06 ``_apply_geometry_op``). Input validation (T-01-13):
        ``rgb`` must be a ``(H, W, 3)`` uint8 array — a malformed worker result
        raises ValueError instead of constructing a corrupt QImage.

        When ``bbox`` (x, y, w, h) is provided, only that region is composited
        into the existing image so non-masked pixels are untouched (avoids
        full-image replacement artifacts); otherwise the whole image is replaced.
        The original image numpy is captured BEFORE overwriting so the
        before/after preview toggle works.

        Buffer lifetime (RESEARCH Pitfall 2, PATTERNS.md §Shared Pattern 5): the
        QImage built from the numpy buffer is ``.copy()``-detached BEFORE
        storage in image_item. This EXPLICITLY fixes the MangaCleaner_GPU
        ``main_window.py:245`` bug (which built ``QImage(rgba.data, ...)`` without
        ``.copy()`` and caused intermittent segfaults). The Pitfall-2 regression
        guard ``test_inpaint_result_display_uses_copy`` locks this.
        """
        return self._set_image_from_numpy(rgb, bbox, capture_original=True)

    def set_image_from_numpy_preview(
        self, image_rgb: np.ndarray, capture_original: bool = False
    ) -> QImage:
        """Capture-suppressed display path (plan 05-06, RESEARCH Pitfall 5).

        Identical to :meth:`set_image_from_numpy` (same validation, same
        ``.copy()``-detached QImage) EXCEPT the ``_original_image_numpy``
        capture is skipped when ``capture_original`` is False. Used by the
        Levels dialog live preview so opening the dialog never poisons the
        Show Original baseline — the pre-dialog image stays the D-14
        "original" while the user drags the sliders (Pitfall 9: the preview
        is a silent display mutation, never an undo entry).
        """
        return self._set_image_from_numpy(image_rgb, None, capture_original=capture_original)

    def rebaseline_original(self) -> None:
        """Re-baseline the Show Original cache to the current displayed image.

        D-14 (plan 05-06, RESEARCH Pitfall 5): after EVERY image op the
        pre-op image is recoverable only via Ctrl+Z — Show Original must show
        the POST-op image as the "original". The op apply path
        (``_apply_geometry_op``) calls this after its write-back so a second
        op does not keep showing the first op's pre-image.
        """
        self._original_image_numpy = self.get_image_numpy()
        self._showing_original = False

    def _set_image_from_numpy(
        self,
        rgb: np.ndarray,
        bbox: tuple[int, int, int, int] | None,
        capture_original: bool,
    ) -> QImage:
        """The shared ``set_image_from_numpy`` implementation.

        ``capture_original`` gates the ``_original_image_numpy`` capture
        (True for the normal display path, False for the preview path — see
        :meth:`set_image_from_numpy_preview`).
        """
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError(
                f"expected (H,W,3) uint8 RGB array, got shape={rgb.shape} dtype={rgb.dtype}"
            )

        # The page image is being replaced (image op write-back, undo, or a
        # page mutation): any armed crop rect is stale geometry (plan 05-07).
        self._clear_crop_state()

        # _original_image_numpy holds the PRE-FIRST-inpaint image for the
        # before/after preview toggle (captured once per page, reset on
        # set_image/clear). It is NOT used as the composite base — compositing
        # onto it would revert earlier inpaints on a second inpaint (CR-13).
        # The preview path (capture_original=False) skips this so a live
        # dialog preview never re-baselines Show Original (D-14, Pitfall 5).
        if capture_original and self._original_image_numpy is None:
            self._original_image_numpy = self.get_image_numpy()

        full_rgb = rgb
        if bbox is not None:
            # Composite only the bbox region into the CURRENT displayed image
            # (which already reflects prior inpaints), so a second inpaint
            # extends the result instead of reverting region A to its
            # pre-first-inpaint state (CR-13). Read fresh from the live pixmap
            # each call — never the stale _original_image_numpy cache.
            current = self.get_image_numpy()
            if current is not None and current.shape[:2] == (rgb.shape[0], rgb.shape[1]):
                x, y, w, h = bbox
                current = current.copy()
                current[y : y + h, x : x + w] = rgb[y : y + h, x : x + w]
                full_rgb = current

        h, w = full_rgb.shape[:2]
        # Phase 8 (plan 08-02): the planes are page-sized state. When the
        # displayed image is REPLACED at different dims (a geometry op
        # write-back or undo of one — the same-page inpaint/levels paths keep
        # their dims and their planes), stale old-grid planes would
        # broadcast-misalign the next recompose; re-seed them transparent at
        # the new size. Same-dims page switches are handled by the D-11 seam
        # (plan 08-02 Task 2 packs/restores planes per page explicitly).
        if (
            self._mask_manual is None
            or self._mask_manual.isNull()
            or (self._mask_manual.height(), self._mask_manual.width()) != (h, w)
        ):
            manual = QImage(w, h, QImage.Format.Format_ARGB32)
            manual.fill(Qt.GlobalColor.transparent)
            self._mask_manual = manual
            erase = QImage(w, h, QImage.Format.Format_ARGB32)
            erase.fill(Qt.GlobalColor.transparent)
            self._mask_erase = erase
            self._auto_bin = None
        qimg = QImage(full_rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        # CRITICAL: .copy() detaches the QImage from the numpy buffer before
        # storage. Without this the QImage points at a buffer that GCs and
        # causes intermittent segfaults (RESEARCH Pitfall 2; MangaCleaner_GPU
        # main_window.py:245 omits this — the buggy reference we do NOT copy).
        qimg = qimg.copy()
        self.image_item.setPixmap(QPixmap.fromImage(qimg))
        if (w, h) != (self.sceneRect().width(), self.sceneRect().height()):
            self.setSceneRect(QRectF(0, 0, w, h))
        # The inpaint-result claim is gated on capture_original (CR-01,
        # T-06-10): the capture-suppressed preview path can never claim an
        # inpaint result, so has_inpaint_result() stays False through the
        # whole dialog preview+cancel lifecycle on a fresh page. The
        # capture-enabled callers (inpaint result display, geometry-op
        # write-back, project page display) keep the claim.
        if capture_original:
            self._inpainted_qimage = qimg
        # D-09 (deferred from 05-UAT/05-UI-REVIEW): the numpy display path is
        # the ONLY image display path that missed the empty-state refresh, so
        # the z=2000 "No page open" trio stayed rendered over a loaded page
        # (project open via _display_page_state, image-op write-back, undo).
        # The call is idempotent with an image present (RESEARCH Pitfall 1) —
        # it also covers the preview path (set_image_from_numpy_preview routes
        # through this shared implementation).
        self._update_empty_state()
        # If currently showing the original preview, the new result replaces the
        # stored inpainted image but the display stays on original until toggled.
        return qimg

    def show_original(self, show: bool) -> None:
        """Toggle between the original (pre-inpaint) and the inpainted image.

        UI-SPEC surface 7 before/after compare: ``show=True`` displays the
        original, ``show=False`` restores the inpainted result. No-op when the
        corresponding side is unavailable (no inpaint result yet).
        """
        self._showing_original = show
        if show and self._original_image_numpy is not None:
            arr = self._original_image_numpy
            h, w = arr.shape[:2]
            qimg = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888)
            # .copy() before display (RESEARCH Pitfall 2 — the original numpy is
            # held on self, but copy-detach keeps the QImage robust to the array
            # being replaced by a subsequent inpaint op).
            qimg = qimg.copy()
            self.image_item.setPixmap(QPixmap.fromImage(qimg))
        elif not show and self._inpainted_qimage is not None:
            self.image_item.setPixmap(QPixmap.fromImage(self._inpainted_qimage))

    def has_inpaint_result(self) -> bool:
        """Return True iff an inpaint result is stored (drives the preview enable)."""
        return self._inpainted_qimage is not None

    # ------------------------------------------------------------- tool state
    def set_tool(self, tool: ToolMode) -> None:
        """Set the active mask-editing tool (UI-SPEC surface 6).

        Resets the Shift eraser-modifier (it is transient — only Brush+Shift
        means erase). Switching AWAY from the Crop tool removes any armed
        crop rect + dim-out overlay (plan 05-07 — the armed state belongs to
        the active Crop session; switching tools is the exit).
        """
        self.current_tool = tool
        self.is_eraser_modifier = False
        if tool != ToolMode.CROP:
            self._clear_crop_state()
        self._update_cursor_visuals()

    def set_brush_size(self, size: int) -> None:
        """Set the brush size, clamped to [1, 300] (T-01-09)."""
        self.brush_size = clamp_brush_size(size)
        self._update_cursor_visuals()

    def _effective_eraser(self) -> bool:
        """True iff the next stroke should erase.

        The Eraser tool always erases; Brush erases while Shift is held (the
        transient modifier per UI-SPEC surface 6). Rectangle/Lasso paint/erase
        based on this flag too (a Shift+Rect drag is an erase-rect).
        """
        return self.current_tool == ToolMode.ERASER or (
            self.current_tool == ToolMode.BRUSH and self.is_eraser_modifier
        )

    def _update_cursor_visuals(self) -> None:
        """Set the cursor circle color/size from the active tool + brush size.

        Eraser mode -> cyan (QColor(0,212,255,...)); paint mode -> red
        (QColor(255,0,0,...)). The rect is centered on the cursor origin
        (setPos in mouseMoveEvent). Reimplemented patterned after
        MangaCleaner_GPU canvas.py:54-63 (D-12 reference-only).
        """
        if self._effective_eraser():
            pen = QPen(QColor(0, 212, 255, 200), 1)
            brush = QBrush(QColor(0, 212, 255, 60))
        else:
            pen = QPen(QColor(255, 0, 0, 200), 1)
            brush = QBrush(QColor(255, 0, 0, 60))
        self.cursor_item.setPen(pen)
        self.cursor_item.setBrush(brush)
        r = self.brush_size / 2
        self.cursor_item.setRect(-r, -r, self.brush_size, self.brush_size)

    # -------------------------------------------------------------- validation
    def validate_image_size(self, width: int, height: int) -> bool:
        """Return False if the image exceeds the max dimension (T-01-03)."""
        return width <= MAX_IMAGE_DIMENSION and height <= MAX_IMAGE_DIMENSION

    # --------------------------------------------------------------- zoom/pan
    def update_smoothing(self) -> None:
        """Toggle SmoothPixmapTransform at the 1x boundary.

        Above 1x the pixels are magnified and smoothing would blur them; below
        or at 1x smoothing produces a clean downscale. Adapted from
        ``image_viewer.py:116``.
        """
        if self.zoom_factor > 1:
            self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        else:
            self.setRenderHint(QPainter.SmoothPixmapTransform, True)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API casing)
        """Ctrl+wheel = zoom (half-step); Shift+wheel = horizontal; else pan.

        Adapted from ``image_viewer.py:125-142``.
        """
        if Qt.KeyboardModifier.ControlModifier & event.modifiers():
            if event.angleDelta().y() > 0:
                self.zoom_in(wheel=True)
            else:
                self.zoom_out(wheel=True)
        elif Qt.KeyboardModifier.ShiftModifier & event.modifiers():
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y()
            )
        else:
            super().wheelEvent(event)

    def zoom_in(self, wheel: bool = False) -> None:
        """Zoom in by a full step, or a half-step on Ctrl+wheel.

        Adapted from ``image_viewer.py:144-148``.
        """
        self.zoom(ZOOM_TICK_FACTOR**0.5 if wheel else ZOOM_TICK_FACTOR)

    def zoom_out(self, wheel: bool = False) -> None:
        """Zoom out by a full step, or a half-step on Ctrl+wheel.

        Adapted from ``image_viewer.py:150-154``.
        """
        self.zoom(1 / (ZOOM_TICK_FACTOR**0.5) if wheel else 1 / ZOOM_TICK_FACTOR)

    def zoom(self, factor: float, *, suppress_signals: bool = False) -> None:
        """Apply a zoom ``factor`` to the current zoom, clamped to the bounds.

        Max 100x; min = half the viewport (the image must stay at least half the
        viewport on both axes when zooming out). Adapted from
        ``image_viewer.py:221-255``.
        """
        proposed = min(self.zoom_factor * factor, MAX_ZOOM_FACTOR)

        current_width = self.image_item.pixmap().width()
        current_height = self.image_item.pixmap().height()
        proposed_width = current_width * proposed
        proposed_height = current_height * proposed
        view_width = self.viewport().width()
        view_height = self.viewport().height()

        # Don't zoom out further if it's getting too small (half-viewport min).
        if (
            proposed_width < view_width / 2
            and proposed_height < view_height / 2
            and factor < 1
        ):
            return

        self.zoom_factor = proposed
        self.update_smoothing()
        self.setTransform(QTransform().scale(self.zoom_factor, self.zoom_factor))

        if not suppress_signals:
            self.zoom_changed.emit(self.zoom_factor)

    def zoom_reset(self) -> None:
        """Reset to 100% (Actual Size, Ctrl+1). Adapted from image_viewer.py:156."""
        self.zoom_factor = 1.0
        self.setTransform(QTransform().scale(self.zoom_factor, self.zoom_factor))
        self.update_smoothing()
        self.zoom_changed.emit(self.zoom_factor)

    def actual_size(self) -> None:
        """Alias for :meth:`zoom_reset` (UI-SPEC surface 1 View menu name)."""
        self.zoom_reset()

    def fit_to_window(self) -> None:
        """Fit the image item into the viewport, preserving aspect ratio.

        Resets ``zoom_factor`` to the resulting fit scale so the smoothing
        toggle and status bar reflect reality. Combines the skeleton's
        ``fit_to_window`` with ``image_viewer.py:160-171`` zoom_fit logic.
        """
        pixmap = self.image_item.pixmap()
        if pixmap.isNull():
            return
        self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)
        # Derive the resulting scale from the active transform so zoom_factor
        # stays in sync (image_viewer.py:160-171 computes it directly; here we
        # read it back from the fitInView-applied transform).
        transform = self.transform()
        # fitInView sets a uniform scale on m11/m22 for KeepAspectRatio.
        self.zoom_factor = transform.m11()
        self.update_smoothing()
        self.zoom_changed.emit(self.zoom_factor)

    def zoom_fit(self) -> None:
        """Alias for :meth:`fit_to_window` (image_viewer.py:160 name)."""
        self.fit_to_window()

    # ------------------------------------------------------- pan + tool dispatch
    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Route mouse input to pan, box interaction, or the active mask tool.

        Dispatch order (UI-SPEC §12d + §15 + Phase 8 §39):
        0. **Inline-editor guard** (RESEARCH Pitfall 3, §15) — FIRST branch.
           While the inline editor is active, a click INSIDE the proxy goes to
           the widget (``super()`` forwards it to the QTextEdit); a click
           OUTSIDE the proxy commits the edit (click-away) and the event is
           consumed either way — no move/resize/select can start while editing
           (D-07).
        1. Pan (middle button OR Space+left) — highest priority, unchanged.
        2. Box hit-test (only when the box layer is visible) — **Alt-gated
           under paint tools** (MASK-06, plan 08-02 / D-15/D-18): when the
           active tool is in :data:`PAINT_TOOLS` and Alt is NOT held, the
           entire box branch falls through so a press on a box BODY or a
           corner HANDLE paints exactly as if the boxes weren't there (only
           the empty-canvas selection-clear stays, as today); with Alt, the
           box interaction runs (handle resize under the sole-selection gate,
           body select + move, Alt+drag create on empty canvas). Under
           Move/Pan and Crop the branch runs verbatim as before: handle
           resize, Shift-toggle / select + move, Alt+drag create, and the
           plain empty-canvas press clears the selection and falls through.
        3. Mask tool (left-click + active mask tool) — unchanged.
        4. Base QGraphicsView (item selection, scrollbar click, etc.).
        """
        # --- Inline-editor guard (RESEARCH Pitfall 3): MUST precede ALL other
        # dispatch. Do not rely on Qt focus-out signaling alone (QGraphicsProxy-
        # Widget focus/IME quirks) — the guard decides commit vs. pass-through
        # by the proxy-scene-rect hit-test.
        if self._inline_editor.is_active():
            if self._inline_editor.proxy_scene_rect().contains(self._scene_pos(event)):
                # Click INSIDE the editor -> let the QTextEdit handle it.
                super().mousePressEvent(event)
            else:
                # Click OUTSIDE -> click-away commit (same path as Enter, §15).
                self._inline_editor.commit()
            event.accept()
            return

        middle = event.button() == Qt.MouseButton.MiddleButton
        space_left = self._space_held and event.button() == Qt.MouseButton.LeftButton
        if middle or space_left:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._cursor_overridden = True
            event.accept()
            return

        # --- Phase 3 box hit-test (D-07: boxes always interactive when the
        # layer is visible; Pitfall 5: hidden layer skips hit-testing entirely),
        # restructured in Phase 8 (plan 08-02, MASK-06 / UI-SPEC §39) into the
        # Alt-gated paint-tool carve-out + the verbatim non-paint branch.
        if (
            self.box_layer.isVisible()
            and event.button() == Qt.MouseButton.LeftButton
        ):
            scene_pos = self._scene_pos(event)
            alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            # Hit-test WITHOUT passing the view's zoom transform. Passing
            # self.transform() here (the zoom) makes QGraphicsScene's BSP
            # coarse pass return the parent BoxItem instead of the child
            # CornerHandle at zoom >= ~3.5, which arms a MOVE where the user
            # expects a RESIZE (UAT re-test 1 / debug box-resize-move). The
            # handles use ItemIgnoresTransformations, so querying in scene
            # coords with the IDENTITY transform returns the topmost item by
            # z (handle z=150 > box z=100) correctly at every zoom.
            # ``cursor_item`` and ``preview_item`` intentionally sit above
            # boxes for rendering.  A raw ``itemAt`` therefore reports the
            # brush cursor whenever it is following the mouse, preventing the
            # box interaction from ever arming.  Search the stack for the
            # first *interactive box* instead, preserving handle-over-body
            # priority while ignoring visual-only overlays.
            item = self._box_item_at(scene_pos)
            if self.current_tool in PAINT_TOOLS:
                if alt:
                    # D-15: Alt gates the box interaction under a paint tool —
                    # today's box behavior exactly. NOTE: no Shift-toggle here
                    # (the UI-SPEC §39 Shift row — Shift+click under a paint
                    # tool paints; selection toggling needs Move/Pan).
                    if isinstance(item, CornerHandle):
                        if len(self._scene.selectedItems()) == 1:
                            self._begin_resize(item, scene_pos)
                        event.accept()
                        return
                    if isinstance(item, BoxItem):
                        self._select_and_begin_move(item, scene_pos)
                        event.accept()
                        return
                    self._begin_create_box(scene_pos)
                    event.accept()
                    return
                # MASK-06: no-Alt paint press — fall through the ENTIRE box
                # branch (no accept, no return) so box bodies AND handles
                # paint. Keep only today's empty-canvas selection-clear (a
                # paint-start over empty canvas clears the selection today
                # and stays — UI-SPEC §12d + surface 32).
                if item is None:
                    self._clear_selection()
            else:
                if isinstance(item, CornerHandle):
                    if len(self._scene.selectedItems()) == 1:
                        self._begin_resize(item, scene_pos)
                    event.accept()
                    return
                if isinstance(item, BoxItem):
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        self._toggle_box_selection(item)
                    else:
                        self._select_and_begin_move(item, scene_pos)
                    event.accept()
                    return
                if alt:
                    self._begin_create_box(scene_pos)
                    event.accept()
                    return
                # Empty canvas, no Alt: clear the WHOLE selection and FALL
                # THROUGH (do not return) so the mask-tool branch below still
                # runs (UI-SPEC §12d + surface 32 — clicking empty canvas
                # clears the selection).
                self._clear_selection()

        # --- Crop-tool branch (plan 05-07, UI-SPEC surface 24a). The box
        # hit-test above already returned for presses on boxes/handles — the
        # crop drag starts only on EMPTY canvas (a press on a box still
        # selects/moves it while the Crop tool is active). Runs before the
        # mask-tool branch so CROP never falls into paint dispatch.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.current_tool == ToolMode.CROP
            and self._mask is not None
            and not self._mask.isNull()
        ):
            self._begin_crop_drag(event)
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.current_tool not in (ToolMode.MOVE, ToolMode.CROP)
            and self._mask is not None
            and not self._mask.isNull()
        ):
            self._begin_paint(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """Open the inline editor on a double-clicked box (D-05, UI-SPEC §15).

        NONE existed before plan 04-05 — Phase 3's D-07 contract is preserved:
        single-click = select/move, double-click = edit entry. A double-click
        over a BoxItem (box layer visible) selects it and opens the inline
        editor; over empty canvas (or with the box layer hidden) it falls
        through to the base class. While the editor is already active the
        double-click goes to the proxy widget (word-select inside the
        QTextEdit) — never a re-entry.
        """
        if self._inline_editor.is_active():
            super().mouseDoubleClickEvent(event)
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.box_layer.isVisible()
        ):
            item = self._box_item_at(self._scene_pos(event))
            if isinstance(item, BoxItem):
                # Select the box (UI-SPEC §15 — the box stays selected while
                # editing so the user can immediately re-edit or move it after
                # commit) then open the editor on it.
                self._deselect_box()
                item.setSelected(True)
                self._inline_editor.enter(item)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Pan when panning; advance the active stroke; else track the cursor.

        The cursor circle follows the pointer in every mode (setMouseTracking
        is on). While painting, BRUSH/ERASER strokes, RECTANGLE previews, and
        LASSO path previews are updated here.
        """
        if self._panning:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            event.accept()
            return

        curr = self._scene_pos(event)
        self.cursor_item.setPos(curr)

        # --- Phase 3 box resize / create preview advance.
        if self._resizing_box is not None:
            self._advance_resize(curr)
            event.accept()
            return
        if self._creating_box:
            self._advance_create(curr)
            event.accept()
            return
        # --- Phase 3 box move: reposition the selected box(es) by the scene
        # delta. D-09 (plan 07-02): a GROUP move applies the SAME delta to
        # every ``_group_move`` entry — reposition-only (setRect + handle
        # sync per item, RC-1: no overlay refresh, no re-layout).
        if self._moving_box is not None and self._group_move:
            dx = curr.x() - self._box_drag_anchor.x()
            dy = curr.y() - self._box_drag_anchor.y()
            for item, start_rect in self._group_move.items():
                item.setRect(start_rect.translated(dx, dy))
                item._sync_handles(primary=(item is self._primary_box))
            event.accept()
            return

        # --- Crop drag advance (plan 05-07): update the rect + dim overlay.
        if self._crop_drag_active:
            self._advance_crop_drag(curr)
            event.accept()
            return

        if self._is_painting:
            self._advance_paint(curr)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """End pan, commit a box resize/create/move, OR commit the mask stroke."""
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            if self._space_held:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
                self._cursor_overridden = False
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # --- Phase 3 box resize commit (clamp final rect to >= 8x8, D-06).
            if self._resizing_box is not None:
                self._commit_resize()
                self.viewport().releaseMouse()
                event.accept()
                return
            # --- Phase 3 box create commit (D-13; < 8x8 is a no-op, D-06).
            if self._creating_box:
                self._commit_create(event)
                self.viewport().releaseMouse()
                event.accept()
                return
            # --- Phase 3 box move commit (emit boxes_modified once on release).
            # WR-04 (plan 03-07): delta-check — a plain click-to-select (no drag)
            # leaves the rect unchanged; do NOT emit boxes_modified in that case
            # (it would push a redundant no-op BOXES snapshot whose before ==
            # after, consuming a history slot and disabling redo). Only a REAL
            # move emits.
            if self._moving_box is not None:
                before = self._boxes_interaction_start_snapshot
                moved = any(
                    item.rect() != start_rect
                    for item, start_rect in self._group_move.items()
                )
                n = len(self._group_move)
                self._moving_box = None
                self._group_move = {}
                if moved:
                    if n > 1:
                        self._pending_boxes_op_name = f"Moved {n} boxes"
                    self.boxes_modified.emit(before)
                self.viewport().releaseMouse()
                event.accept()
                return

            # --- Crop drag release (plan 05-07): ARM the rect (drag-then-
            # decide — no commit-on-release). Dim + preview persist until
            # Enter applies / Esc cancels; a <8x8 release arms nothing.
            if self._crop_drag_active:
                self._end_crop_drag()
                self.viewport().releaseMouse()
                event.accept()
                return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_painting
        ):
            self._end_paint(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ----------------------------------------------------------- paint helpers
    def _scene_pos(self, event) -> QPointF:
        """Map a mouse event's viewport position to scene coordinates.

        ``QGraphicsView.mapToScene`` takes a ``QPoint`` (int), but
        ``QMouseEvent.position()`` returns a ``QPointF`` (float); convert via
        ``toPoint()`` then back to ``QPointF`` so painting lands at sub-pixel-
        accurate scene coordinates regardless of zoom/pan.
        """
        return QPointF(self.mapToScene(event.position().toPoint()))

    def _active_stroke_plane(self, eraser: bool) -> QImage | None:
        """Return the plane the current stroke dual-writes into (plan 08-02).

        Pitfall 13-11: an erase stroke must ALSO write the erase ledger or
        its effect is lost on the next recompose. Paint tools (BRUSH/
        RECTANGLE/LASSO) accumulate on the MANUAL plane; the eraser (and
        Brush+Shift) accumulates on the ERASE ledger. The plane call itself
        always paints with normal composition (eraser=False) — the ledger
        MARKS erased pixels in red; only the display composite
        ``self._mask`` keeps the CompositionMode_Clear eraser semantics.
        """
        return self._mask_erase if eraser else self._mask_manual

    def _dual_write_stroke(self, p1: QPointF, p2: QPointF, eraser: bool) -> None:
        """Write a brush segment onto the active plane (eraser=False paint)."""
        plane = self._active_stroke_plane(eraser)
        if plane is not None and not plane.isNull():
            paint_mask_stroke(plane, p1, p2, self.brush_size, False)

    def _begin_paint(self, event) -> None:
        """Start a stroke/rect/lasso on left-press (UI-SPEC surface 6)."""
        self._is_painting = True
        start = self._scene_pos(event)
        self._start_pt = start
        self._last_pt = start
        eraser = self._effective_eraser()
        if self.current_tool == ToolMode.LASSO:
            self._lasso_path = QPainterPath()
            self._lasso_path.moveTo(start)
        elif self.current_tool in (ToolMode.BRUSH, ToolMode.ERASER):
            # A click paints a single dot: stroke from the point to itself
            # (RoundCap fills the cap disc).
            paint_mask_stroke(self._mask, start, start, self.brush_size, eraser)
            # Dual-write (plan 08-02): the stroke also lands on the active
            # plane (manual / erase ledger) with normal composition.
            self._dual_write_stroke(start, start, eraser)
            self.update_mask_display()

    def _advance_paint(self, curr: QPointF) -> None:
        """Advance the in-progress stroke/preview (called on mouseMove)."""
        eraser = self._effective_eraser()
        if self.current_tool in (ToolMode.BRUSH, ToolMode.ERASER):
            paint_mask_stroke(self._mask, self._last_pt, curr, self.brush_size, eraser)
            self._dual_write_stroke(self._last_pt, curr, eraser)
            self._last_pt = curr
            self.update_mask_display()
        elif self.current_tool == ToolMode.RECTANGLE:
            path = QPainterPath()
            path.addRect(QRectF(self._start_pt, curr).normalized())
            self.preview_item.setPath(path)
        elif self.current_tool == ToolMode.LASSO:
            self._lasso_path.lineTo(curr)
            self.preview_item.setPath(self._lasso_path)

    def _end_paint(self, event) -> None:
        """Commit the stroke on left-release (emits mask_modified ONCE)."""
        curr = self._scene_pos(event)
        eraser = self._effective_eraser()
        if self.current_tool == ToolMode.RECTANGLE:
            paint_mask_rect(self._mask, self._start_pt, curr, eraser)
            plane = self._active_stroke_plane(eraser)
            if plane is not None and not plane.isNull():
                paint_mask_rect(plane, self._start_pt, curr, False)
            self.update_mask_display()
        elif self.current_tool == ToolMode.LASSO:
            self._lasso_path.closeSubpath()
            paint_mask_lasso(self._mask, self._lasso_path, eraser)
            plane = self._active_stroke_plane(eraser)
            if plane is not None and not plane.isNull():
                paint_mask_lasso(plane, self._lasso_path, False)
            self.update_mask_display()
        self._is_painting = False
        self.preview_item.setPath(QPainterPath())  # clear the dashed preview
        # Recompose from the planes BEFORE the single stroke-commit emission
        # (plan 08-02) — the display composite becomes exactly
        # (manual | auto) & ~erase; the live-painted composite above was only
        # mid-stroke feedback. One emission per stroke is preserved.
        self.recompose_mask()
        # Single emission per completed stroke — the plan-06 history hook.
        self.mask_modified.emit()

    # ------------------------------------------------- crop tool (plan 05-07)
    # The armed-rect state machine (UI-SPEC surface 24a): drag defines the
    # rect (CrossCursor, dim-out overlay z=880, cyan dashed border z=900);
    # release ARMS it (drag-then-decide — dim + preview persist); Enter
    # applies (crop_committed), Esc cancels; the Crop tool stays active
    # either way. A drag < 8x8 scene px is a no-op (no overlay, no preview —
    # the 8x8 minimum; RESEARCH Pitfall 10).
    def _begin_crop_drag(self, event) -> None:
        """Start a crop-rect drag: capture the anchor, clear any armed rect,
        show the CrossCursor."""
        self._crop_drag_active = True
        self._crop_anchor = self._scene_pos(event)
        self._clear_crop_dim()
        self._crop_rect = None
        self.preview_item.setPath(QPainterPath())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._cursor_overridden = True
        # The viewport owns the drag so move/release keep arriving even when
        # the pointer leaves the page (mirrors the box-drag pattern).
        self.viewport().grabMouse()

    def _advance_crop_drag(self, curr: QPointF) -> None:
        """Update the crop rect during the drag, clamped to the page bounds.

        Both the anchor and the cursor position are clamped into the page
        rect (UI-SPEC §UI Considerations overflow: scene-px geometry is
        page-bounded — a drag beyond the canvas clamps, no container
        overflow). The rect is shown (dim + preview border) only once it is
        >= 8x8 scene px on both axes; smaller rects show nothing (the no-op
        contract).
        """
        page = self.sceneRect()
        if page.isNull():
            return

        def _clamp(p: QPointF) -> QPointF:
            return QPointF(
                min(max(p.x(), 0.0), page.width()),
                min(max(p.y(), 0.0), page.height()),
            )

        rect = QRectF(_clamp(self._crop_anchor), _clamp(curr)).normalized()
        self._crop_rect = rect
        if rect.width() >= MIN_BOX_SIZE and rect.height() >= MIN_BOX_SIZE:
            self._show_crop_dim(rect)
            path = QPainterPath()
            path.addRect(rect)
            self.preview_item.setPath(path)
        else:
            self._clear_crop_dim()
            self.preview_item.setPath(QPainterPath())

    def _end_crop_drag(self) -> None:
        """Arm the rect on release: dim + preview PERSIST (drag-then-decide).

        A release with a <8x8 rect clears the overlay/preview and arms
        nothing (the no-op contract). The cursor returns to the default.
        """
        self._crop_drag_active = False
        if self._cursor_overridden:
            self.unsetCursor()
            self._cursor_overridden = False
        rect = self._crop_rect
        if (
            rect is None
            or rect.width() < MIN_BOX_SIZE
            or rect.height() < MIN_BOX_SIZE
        ):
            self._crop_rect = None
            self._clear_crop_dim()
            self.preview_item.setPath(QPainterPath())
            return
        # Armed: leave the dim + preview in place until Enter / Esc.

    def _show_crop_dim(self, rect: QRectF) -> None:
        """Build the 4 composited dim rects for the outside-of-crop region.

        The dim rects cover the page minus the crop rect INFLATED BY 1px on
        each side (UI-SPEC §Spacing exceptions — the 1px inset so the dim
        meets the crop edge exactly and the 2px cyan dashed border renders
        unobscured). Rect at the page edge are skipped (nothing to dim);
        the rects are pairwise non-overlapping. Constant item count (4 max —
        T-05-18, fixed per armed drag).
        """
        self._clear_crop_dim()
        page = self.sceneRect()
        if page.isNull():
            return
        W, H = page.width(), page.height()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

        def _add(dx, dy, dw, dh) -> None:
            if dw <= 0 or dh <= 0:
                return
            # Clamp the dim rect to the page (a moat rect may extend past the
            # page when the crop hugs an edge — nothing may dim outside the
            # page; the outside-of-crop region is page-bounded).
            r = QRectF(dx, dy, dw, dh).intersected(page)
            if r.width() <= 0 or r.height() <= 0:
                return
            item = QGraphicsRectItem(r)
            item.setPen(Qt.PenStyle.NoPen)
            item.setBrush(QBrush(_CROP_DIM_COLOR))
            item.setZValue(CROP_DIM_Z)
            self._scene.addItem(item)
            self._crop_dim_items.append(item)

        # 1px moat around the crop rect: top / bottom span the full width,
        # left / right fill the vertical gap between them (h+2 tall).
        _add(0.0, 0.0, W, y - 1.0)  # top
        _add(0.0, y + h + 1.0, W, H - (y + h + 1.0))  # bottom
        _add(0.0, y - 1.0, x - 1.0, h + 2.0)  # left
        _add(x + w + 1.0, y - 1.0, W - (x + w + 1.0), h + 2.0)  # right

    def _clear_crop_dim(self) -> None:
        """Remove the dim-out overlay rects from the scene."""
        for item in self._crop_dim_items:
            self._scene.removeItem(item)
        self._crop_dim_items = []

    def _apply_armed_crop(self) -> None:
        """Enter on an armed crop rect: emit ``crop_committed`` (scene rect)
        and clear the armed state. The tool STAYS active (the user may crop
        again; switching tools is the exit). A degenerate rect (never armed,
        or shrunk below the 8x8 min) emits nothing.
        """
        rect = self._crop_rect
        self._crop_rect = None
        self._clear_crop_dim()
        self.preview_item.setPath(QPainterPath())
        if (
            rect is None
            or rect.width() < MIN_BOX_SIZE
            or rect.height() < MIN_BOX_SIZE
        ):
            return
        self.crop_committed.emit(QRectF(rect))

    def _cancel_armed_crop(self) -> None:
        """Esc on an armed crop rect: clear overlay + preview + armed rect;
        the Crop tool stays active."""
        self._crop_rect = None
        self._clear_crop_dim()
        self.preview_item.setPath(QPainterPath())

    def _clear_crop_state(self) -> None:
        """Drop the armed rect + dim overlay + any in-progress crop drag.

        Called on tool switch away from Crop, page switch, and image
        replacement (stale geometry). Not used to end a completed drag (the
        release path handles its own cleanup + cursor restore).
        """
        self._crop_rect = None
        self._crop_drag_active = False
        self._clear_crop_dim()
        self.preview_item.setPath(QPainterPath())

    # ----------------------------------------------------------- keyboard
    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle Phase 3 box keys; track Space for pan; Shift toggles Brush<->Eraser.

        Phase 3 (D-12/D-08): ``Delete``/``Backspace`` on a selected box removes
        it silently (no dialog — the BOXES undo in plan 03-05 recovers it);
        ``Esc`` deselects the current box. Both consume the event only when a
        box is the target, so they never shadow other consumers.

        Keys we do not explicitly handle are passed to ``event.ignore()`` (NOT
        ``super().keyPressEvent()``) so the event propagates up to the
        MainWindow and its application-wide ``QShortcut`` bindings (Ctrl+Z /
        Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z undo/redo) can fire. The QGraphicsView
        base class accepts unhandled keys, which was shadowing those shortcuts
        when the canvas had focus (CR-09).
        """
        # --- Phase 3 box Delete/Esc (D-12 silent delete, D-08 Esc deselect;
        # plan 07-02 D-09 grouped delete + Esc deselect-ALL).
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_items = [it for it in self._box_items if it.isSelected()]
            if len(selected_items) > 1:
                before = self.boxes_snapshot()
                for it in selected_items:
                    self._scene.removeItem(it)
                    self._box_items.remove(it)
                # Plan 07-06 (G-07-6): same graveyard retirement as the
                # single-delete path — the group delete runs mid-event-loop
                # with pending overlay updates; the wrapper release must be
                # deferred past the flush (no drop-the-last-ref site remains).
                self._retire_boxes(selected_items)
                self._refresh_empty_box_hint()
                self._pending_boxes_op_name = f"Deleted {len(selected_items)} boxes"
                self._selection_order = []
                self._primary_box = None
                self.boxes_modified.emit(before)
                event.accept()
                return
            selected = self._selected_box()
            if selected is not None:
                self._remove_box(selected)
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape:
            # UI-SPEC §Shortcuts Esc priority: cancel the inline edit FIRST
            # (highest priority — the box stays selected, §15); then the crop
            # armed-rect (plan 05-07 — overlay + preview clear, the Crop tool
            # stays active); then Phase 3 deselect; Phase 2 batch-cancel lives
            # in MainWindow.
            if self._inline_editor.is_active():
                self._inline_editor.cancel()
                event.accept()
                return
            if self.current_tool == ToolMode.CROP and self._crop_rect is not None:
                self._cancel_armed_crop()
                event.accept()
                return
            if len(self._scene.selectedItems()) > 0:
                self._clear_selection()
                event.accept()
                return
        if event.key() == Qt.Key.Key_F2:
            # UI-SPEC §Shortcuts: F2 = the keyboard alternative to double-click
            # ("rename/edit in place" convention). Opens the editor on the
            # selected box; no-op when nothing is selected or already editing.
            selected = self._selected_box()
            if selected is not None and not self._inline_editor.is_active():
                self._inline_editor.enter(selected)
                event.accept()
                return

        # --- Crop armed-rect keys (plan 05-07, UI-SPEC surface 24a): with a
        # crop rect armed AND the Crop tool active, Enter applies the crop
        # (emits crop_committed, clears the armed state, tool stays active);
        # Enter with no armed rect falls through (nothing to apply). Esc is
        # handled in the Esc block above (crop-cancel before box deselect).
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and self.current_tool == ToolMode.CROP
            and self._crop_rect is not None
        ):
            self._apply_armed_crop()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Space and not self._space_held:
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                self._cursor_overridden = True
            event.accept()
            return
        # Shift toggles Brush<->Eraser transiently (does not consume the event).
        # NOTE: Qt delivers the Shift KeyPress with modifiers() == NoModifier
        # (modifiers reflect state BEFORE the press), so we key off event.key()
        # rather than event.modifiers() for the Shift press/release detection.
        if (
            event.key() == Qt.Key.Key_Shift
            and self.current_tool == ToolMode.BRUSH
            and not self.is_eraser_modifier
        ):
            self.is_eraser_modifier = True
            self._update_cursor_visuals()
            # Fall through: still ignore() so modifier-combo shortcuts
            # (Ctrl+Shift+Z) are not shadowed when the canvas has focus.
        # Ignore (do NOT accept) so parent widgets / QShortcuts see the event.
        # Calling super().keyPressEvent(event) here lets QGraphicsView accept
        # the key, which swallows Ctrl+Z/Ctrl+Shift+Z before the MainWindow's
        # undo/redo QShortcuts can fire (CR-09).
        event.ignore()

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        """Clear the Space-pan flag; Shift release restores Brush from Eraser."""
        if event.key() == Qt.Key.Key_Space and self._space_held:
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
                self._cursor_overridden = False
            event.accept()
            return
        # Shift release ends the transient eraser modifier (only when the
        # active tool is Brush — see keyPressEvent for the modifiers() caveat).
        if (
            event.key() == Qt.Key.Key_Shift
            and self.current_tool == ToolMode.BRUSH
            and self.is_eraser_modifier
        ):
            self.is_eraser_modifier = False
            self._update_cursor_visuals()
        super().keyReleaseEvent(event)

    # ----------------------------------------------------------- empty state
    def _update_empty_state(self) -> None:
        """Show/hide the empty-state overlay depending on image presence.

        Centers the three text blocks vertically with 48px (2xl) spacing per
        UI-SPEC §Surface 9. Also refreshes the Phase 3 empty-box hint (§12f)
        so its visibility tracks image presence + box-layer state.
        """
        empty = self.image_item.pixmap().isNull()
        self._empty_heading.setVisible(empty)
        self._empty_body.setVisible(empty)
        self._empty_hint.setVisible(empty)
        # The empty-box hint is hidden when no image is loaded (it is a
        # page-scoped affordance); its visibility when an image IS loaded is
        # governed by _refresh_empty_box_hint (box-layer visible + zero boxes).
        if empty:
            self.empty_box_hint.setVisible(False)
        else:
            self._refresh_empty_box_hint()
        if not empty:
            return
        # Center horizontally over the viewport; stack vertically with spacing.
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        cx = view_rect.center().x()
        top = view_rect.top() + 48.0
        for i, item in enumerate(
            (self._empty_heading, self._empty_body, self._empty_hint)
        ):
            item.setPos(
                cx - item.boundingRect().width() / 2,
                top + i * 48.0,
            )

    # ============================================================== Phase 3
    # ------------------------------------------------------------- box layer
    # Plan 07-06 (G-07-6 blocker) — the graveyard: DEFERRED deletion of
    # removed BoxItems.
    #
    # The teardown UAF: removal sites (set_boxes, _remove_box, the multi-select
    # Delete branch) drop the last Python refs to BoxItems mid-event-loop while
    # the scene still holds pending UpdateRequests referencing their overlay
    # children (TypesetOverlayItem.set_content -> self.update(), queued by the
    # last style commit). Shiboken then synchronously deletes the C++ items,
    # and the next flush dispatches paint() to a freed TypesetOverlayItem ->
    # pure-virtual call -> abort (0xC0000409, G-07-6). The graveyard holds the
    # removed wrappers and releases them via a zero-delay ``QTimer.singleShot``
    # callback: the
    # scene's update request was queued BEFORE our release timer (at
    # update()-time), so the pending flush always paints LIVE items and the
    # refs drop only on the next event-loop iteration — after the updates
    # referencing them were processed.
    def _retire_boxes(self, items: list) -> None:
        """Hold ``items`` in the graveyard; schedule ONE deferred release.

        ``_graveyard_pending`` guarantees at most one outstanding zero-timeout
        timer — items enqueued before the timer fires simply join the same
        batch, and the single release clears the whole graveyard.
        """
        if not items:
            return
        self._box_graveyard.extend(items)
        if self._graveyard_pending:
            return
        self._graveyard_pending = True
        QTimer.singleShot(0, self._release_graveyard)

    def _release_graveyard(self) -> None:
        """Drop the graveyard's refs — the singleShot(0) timer callback.

        Runs on the next event-loop iteration, AFTER the scene's queued
        UpdateRequests were flushed (they were posted before this timer), so
        no paint dispatch can land on an item whose C++ object dies here.

        WR-03 (07-REVIEW-GAPS): belt-and-suspenders guard behind the timer —
        the callback can fire against a wrapper invalidated at teardown (a
        box removal followed by window close in the same event-loop
        iteration), which would raise ``RuntimeError: Internal C++ object
        already deleted`` from inside the event loop. The paint-path
        ``Shiboken.isValid`` pattern (box_item.py) skips the release
        entirely — the C++ object is gone, there is nothing left to drop.
        """
        if not Shiboken.isValid(self):
            return
        self._graveyard_pending = False
        self._box_graveyard.clear()

    def set_boxes(
        self,
        user_pageboxes: list[PageBox],
        detected_pageboxes: list[PageBox],
    ) -> None:
        """Rebuild the box layer from the given pageboxes (the plan 03-04 seam).

        Clears the current box items (removes them from the scene + the list),
        then builds one :class:`BoxItem` per pagebox from the union (user boxes
        first, then detected). Each BoxItem is a PARENT-LESS scene item at z=100
        (UI-SPEC §11 allows "QGraphicsItemGroup OR parent-less item set"; we use
        the parent-less form because parenting under a QGraphicsItemGroup blocks
        Qt selection on the child — see deviation note in set_box_overlay_visible).
        ``box_layer`` stays as the logical-visibility flag the dispatch checks.
        """
        # Plan 04-05: commit any active inline edit BEFORE rebuilding the layer
        # (page switch / detection / restore all rebuild here) — a stale editor
        # must never dangle over a removed box. Mirrors how the brush stroke
        # commits on page switch.
        self._commit_inline_editor_if_active()
        # CR-01 fix: capture the PRE-mutation snapshot (the state to restore to
        # on undo) BEFORE clearing the layer. set_boxes is used by detection,
        # restore, and page-switch (all suppress the push hook via the
        # _suppress_boxes_push guard), so this payload is only consumed when a
        # test or future caller drives set_boxes as a user edit. Mirrors the
        # image side's pre-edit push contract.
        before = self.boxes_snapshot()
        # Remove existing items from the scene. Plan 07-06 (G-07-6): retire
        # the removed wrappers to the graveyard instead of dropping the last
        # refs synchronously — set_boxes runs mid-event-loop (Ctrl+Z /
        # restore / page switch) and pending scene UpdateRequests from the
        # last style commit still reference the overlay children; a
        # synchronous last-ref drop would delete the C++ items before the
        # flush and paint() would dispatch to freed objects (0xC0000409).
        removed = self._box_items
        self._box_items = []
        for item in removed:
            self._scene.removeItem(item)
        self._retire_boxes(removed)
        # Plan 07-02 (D-08): the layer rebuild resets the multi-select state.
        self._selection_order = []
        self._primary_box = None
        self._group_move = {}

        for pb in list(user_pageboxes) + list(detected_pageboxes):
            item = BoxItem(pb)
            # Plan 07-02 (D-09): the primary-owner WEAKREF (cycle discipline —
            # a strong canvas capture stalls GC + breaks Qt teardown ordering).
            item.set_primary_owner(_weakref(self))
            self._scene.addItem(item)
            # Parent-less items inherit their own visibility; sync to the layer
            # state so a toggle BEFORE any boxes were added still hides them.
            item.setVisible(self._box_overlay_visible)
            item.setEnabled(self._box_overlay_visible)
            # Phase 4 text-overlay layer (D-12): sync the per-box text-overlay
            # child to the canvas's text-layer flag so a box added AFTER the
            # text toggle was flipped respects the layer state.
            item.set_text_overlay_visible(self._text_overlay_visible)
            self._box_items.append(item)

        self._refresh_empty_box_hint()
        self.boxes_modified.emit(before)

    def set_box_overlay_visible(self, visible: bool) -> None:
        """Toggle the box layer visibility (View -> Toggle Box Overlay, Shift+M).

        Hidden = not interactable (D-07 / Pitfall 5): ``setVisible(False)`` hides
        every box AND we set ``setEnabled(False)`` on each item as belt-and-
        suspenders — ``setVisible`` alone does not always disable Qt hit-testing,
        so ``setEnabled`` guarantees a left-click where a hidden box was falls
        through to mask painting.

        ``box_layer`` (a QGraphicsItemGroup) is kept as the logical-visibility
        sentinel: boxes are PARENT-LESS scene items (not children of the group)
        because parenting under a QGraphicsItemGroup blocks Qt selection on the
        child item. The group's own visibility mirrors the logical state so
        ``box_layer.isVisible()`` correctly gates the dispatch (Pitfall 5).
        """
        self._box_overlay_visible = visible
        self.box_layer.setVisible(visible)
        for item in self._box_items:
            item.setVisible(visible)
            item.setEnabled(visible)
        self._refresh_empty_box_hint()

    def set_text_overlay_visible_flag(self, visible: bool) -> None:
        """Set the text-overlay layer visibility (D-12 — the T toggle backing store).

        Independent of :meth:`set_box_overlay_visible` (Shift+M) and the mask
        overlay (M): hiding the text layer hides ONLY the per-box text-overlay
        children, leaving the box borders + handles + badges visible. When the
        box layer is later re-shown, the text layer keeps its own state (the two
        toggles do not interact). Applies to every existing box AND any box added
        afterwards (boxes construct their overlay respecting
        :attr:`_text_overlay_visible` via :meth:`BoxItem.refresh_text_overlay`).
        """
        self._text_overlay_visible = visible
        for item in self._box_items:
            item.set_text_overlay_visible(visible)

    def toggle_text_overlay(self) -> None:
        """Flip the text-overlay layer visibility (View -> Toggle Text Overlay, T).

        The D-12 third independent layer. The action is checkable + checked by
        default; the action's toggled signal calls this method. Independent of
        the box overlay (``Shift+M``) and the mask overlay (``M``).
        """
        self.set_text_overlay_visible_flag(not self._text_overlay_visible)

    def has_boxes(self) -> bool:
        """Return True iff at least one box exists on the layer."""
        return len(self._box_items) > 0

    def box_count(self) -> int:
        """Return the total number of boxes on the layer (status-bar helper)."""
        return len(self._box_items)

    def box_origin_counts(self) -> tuple[int, int]:
        """Return ``(detected_count, user_count)`` for the status-bar copy.

        Drives the "{n} boxes . {d} detected, {u} user" status-bar text.
        """
        detected = sum(1 for it in self._box_items if it.pagebox.origin == DETECTED)
        user = sum(1 for it in self._box_items if it.pagebox.origin == USER)
        return detected, user

    def boxes_snapshot(self) -> list[PageBox]:
        """Materialize a fresh list of PageBoxes from the live BoxItem rects.

        Pitfall 3 (snapshot detachment): for each BoxItem this calls
        :meth:`BoxItem.current_box` which materializes a fresh vendored ``Box``
        with int coords from the live ``rect()`` at call-time, then constructs a
        fresh ``PageBox`` from it. The returned list does NOT alias the live
        BoxItems — mutating a box after this call does not change the snapshot.

        D-15 seam: ``mask`` / ``std_dev`` stay None (read off the original
        ``pagebox``, which is None in Phase 3). The shape is the contract plan
        03-02's ``push_boxes_state`` stores and plan 03-05's restore path
        consumes (it reads ``.origin`` / ``.payload`` via attribute access, so
        PageBox — not a bare tuple — is required).

        Phase 4 (RESEARCH Pitfall 1): the snapshot now reads the live
        ``pagebox``'s ``edited`` / ``bubble_no`` / ``manual_override`` too.
        Without this the BOXES undo stack + page-switch persistence seam would
        silently drop the ``edited`` flag (re-OCR gate), bubble number, and
        manual-override state. ``payload.text`` / ``payload.translation`` ride
        on the payload reference (detached at the history boundary by
        ``PageBox.copy()`` — Pitfall 8).

        Phase 7 (plan 07-01): the snapshot forwards the live ``style`` so a
        style edit survives every snapshot/restore round-trip (undo,
        page-switch, ``_snapshot_current_page``) — the same Pitfall 1
        discipline applied to the style field.

        Phase 8 (plan 08-07): the snapshot forwards the per-box D-15 seam
        fields (``mask`` / ``std_dev`` / ``inpaint_override``) so the
        predictive border state survives EVERY snapshot/restore round-trip —
        BOXES undo, page-switch, save, and the D-03 re-detect user-box merge
        in ``_build_detected_boxes`` (a dropped override would silently
        revert a user's per-box inpaint decision). The ``mask`` is a MUTABLE
        PIL image, so it is ``.copy()``-detached (Pitfall 8 — the 08-01
        detachment applied to the new field).
        """
        snapshots: list[PageBox] = []
        for item in self._box_items:
            fresh_box = item.current_box()
            pb = item.pagebox
            snapshots.append(
                PageBox(
                    box=fresh_box,
                    origin=pb.origin,
                    payload=pb.payload,
                    edited=pb.edited,
                    bubble_no=pb.bubble_no,
                    manual_override=pb.manual_override,
                    style=pb.style,
                    mask=pb.mask.copy() if pb.mask is not None else None,
                    std_dev=pb.std_dev,
                    inpaint_override=pb.inpaint_override,
                )
            )
        return snapshots

    def _refresh_empty_box_hint(self) -> None:
        """Show the empty-box hint iff the layer is visible, an image is loaded,
        and zero boxes exist (UI-SPEC §12f). Centred horizontally near the top.
        """
        has_image = not self.image_item.pixmap().isNull()
        show = (
            has_image
            and self._box_overlay_visible
            and len(self._box_items) == 0
        )
        self.empty_box_hint.setVisible(show)
        if not show:
            return
        # Centre horizontally over the viewport; y ~48 scene px from the top
        # (the 2xl inset, mirroring the empty-state philosophy).
        scene_rect = self.sceneRect()
        if scene_rect.isNull():
            return
        cx = scene_rect.center().x()
        top = 48.0
        self.empty_box_hint.setPos(
            cx - self.empty_box_hint.boundingRect().width() / 2,
            top,
        )

    def _on_zoom_changed_reposition_handles(self, zoom: float) -> None:
        """Reposition every box's handles + re-apply the overlay style on zoom (UI-SPEC §12b).

        ``ItemIgnoresTransformations`` keeps each handle 8x8 viewport px
        regardless of zoom — only its scene-space position is recomputed so it
        tracks the box corner through the zoom.

        Also forwards the zoom to each box so the overlay style re-derives
        (RC-2/RC-3, plan 04-08): the overlay font clamp ([10,28] viewport px,
        UI-SPEC §16) and the outline (constant 2 viewport px) are viewport-px
        contracts, so they are re-derived from the new zoom. This single slot
        covers wheel zoom, zoom_reset, and fit_to_window — the app default on
        every page load, exactly the zoom where the pre-fix outline was
        invisible.
        """
        for item in self._box_items:
            item._sync_handles(primary=(item is self._primary_box))
            item.apply_overlay_zoom(zoom)

    # --------------------------------------------------- box interaction helpers
    def _commit_inline_editor_if_active(self) -> None:
        """Commit the active inline edit (no-op when none is active).

        Called at the top of every path that rebuilds the box layer
        (:meth:`set_boxes` — page switch / detection / restore) so a stale
        editor never dangles over a removed box; mirrors how the brush stroke
        commits on page switch.
        """
        if self._inline_editor.is_active():
            self._inline_editor.commit()

    def _deselect_box(self) -> None:
        """Deselect the currently selected box, if any (UI-SPEC §12c deselect)."""
        for item in self._box_items:
            if item.isSelected():
                item.setSelected(False)

    def _clear_selection(self) -> None:
        """Deselect EVERY box + reset the primary/order tracking (D-08, plan 07-02)."""
        self._scene.clearSelection()
        self._selection_order = []
        self._primary_box = None
        self._sync_handles_visibility()

    def _note_selection_order(self, item: BoxItem) -> None:
        self._selection_order = [
            it for it in self._selection_order if it.isSelected()
        ]
        if item in self._selection_order:
            self._selection_order.remove(item)
        self._selection_order.append(item)

    def _refresh_primary_box(self) -> None:
        self._selection_order = [
            it for it in self._selection_order if it.isSelected()
        ]
        if self._primary_box is not None and not self._primary_box.isSelected():
            self._primary_box = None
        if self._primary_box is None and self._selection_order:
            self._primary_box = self._selection_order[-1]
        if self._primary_box is None:
            selected = [it for it in self._box_items if it.isSelected()]
            if selected:
                self._primary_box = selected[-1]
        self._sync_handles_visibility()

    def _sync_handles_visibility(self) -> None:
        for item in self._box_items:
            item._sync_handles(primary=(item is self._primary_box))

    def _toggle_box_selection(self, item: BoxItem) -> None:
        if item.isSelected():
            item.setSelected(False)
            if item in self._selection_order:
                self._selection_order.remove(item)
            self._refresh_primary_box()
        else:
            item.setSelected(True)
            self._note_selection_order(item)
            self._primary_box = item
            self._sync_handles_visibility()

    def _is_primary_provider(self, item: BoxItem) -> bool | None:
        if self._primary_box is None:
            return None
        return item is self._primary_box

    def _selected_box(self) -> BoxItem | None:
        """Return the single selected BoxItem, or None (D-08 single-select)."""
        for item in self._box_items:
            if item.isSelected():
                return item
        return None

    def select_all_boxes(self) -> None:
        """Select EVERY box on the page (Ctrl+A, D-08 plan 07-02).

        Iterates ``_box_items`` (the layer rebuild's population order), marks
        each item selected, tracks the LAST item as the primary (the group
        anchor — UI-SPEC §32), and drives the selection-change propagation so
        ``itemChange`` fires per item (pens/handles update) and the Inspector
        reload hook sees the new selection.
        """
        if not self._box_items:
            return
        for item in self._box_items:
            item.setSelected(True)
        self._selection_order = [it for it in self._box_items if it.isSelected()]
        self._primary_box = self._selection_order[-1] if self._selection_order else None
        self._sync_handles_visibility()

    def take_pending_boxes_op_name(self) -> str | None:
        """Return and clear the pending group-op name (D-09, plan 07-02)."""
        name = self._pending_boxes_op_name
        self._pending_boxes_op_name = None
        return name

    def set_pending_boxes_op_name(self, op_name: str) -> None:
        """Record the op name for the NEXT ``boxes_modified`` emission (D-10/D-16).

        The 06-WR-01 pattern extended to style commits: the MainWindow records
        "style change" / "font size" at push time so ``_on_boxes_modified``
        consumes it via :meth:`take_pending_boxes_op_name` and the Ctrl+Z
        flash names the style op instead of the generic "box edit".
        """
        self._pending_boxes_op_name = op_name
    def _box_item_at(self, scene_pos: QPointF) -> CornerHandle | BoxItem | None:
        """Return the topmost visible box handle or box at ``scene_pos``.

        The scene also contains display-only items such as the brush cursor and
        paint preview.  They are drawn above boxes, so using
        :meth:`QGraphicsScene.itemAt` directly makes a hovered cursor swallow
        a box press.  Iterating the z-ordered hits lets the box interaction
        intentionally ignore those overlays.
        """
        candidates = self._scene.items(
            scene_pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            QTransform(),
        )
        for candidate in candidates:
            if not candidate.isVisible() or not candidate.isEnabled():
                continue
            if isinstance(candidate, CornerHandle):
                return candidate
            if isinstance(candidate, BoxItem):
                return candidate
        return None

    def _select_and_begin_move(self, item: BoxItem, scene_pos: QPointF) -> None:
        """Select a box (deselecting any other) and arm a move drag (D-08).

        Records the anchor box position + the press scene pos so the move
        delta is computed in scene coords (zoom-independent). Selection is
        driven via the scene's selection API so ``itemChange`` fires and the
        pen/handles update.
        """
        if not item.isSelected():
            self._deselect_box()
            item.setSelected(True)
        self._note_selection_order(item)
        self._primary_box = item
        # D-09: arm the GROUP move — RESEARCH Common Operation 6.
        self._group_move = {
            it: QRectF(it.rect()) for it in self._box_items if it.isSelected()
        }
        self._moving_box = item
        self._box_drag_anchor = scene_pos
        # CR-01 fix: capture the PRE-move snapshot (emitted on move-commit).
        self._boxes_interaction_start_snapshot = self.boxes_snapshot()
        self._sync_handles_visibility()
        # The viewport, not a graphics item, owns this drag.  This keeps the
        # canvas receiving move/release events even when the pointer leaves the
        # item (or its child handle) while dragging.
        self.viewport().grabMouse()

    def _begin_resize(self, handle: CornerHandle, scene_pos: QPointF) -> None:
        """Arm a corner-resize drag (D-06). Stores the starting rect + corner."""
        item = handle.parentItem()
        # parentItem() returns a QGraphicsItem; cast to BoxItem for typing.
        assert isinstance(item, BoxItem), "CornerHandle must be parented to a BoxItem"
        self._resizing_box = item
        self._resize_corner = handle.corner
        self._resize_start_rect = QRectF(item.rect())
        self._box_drag_anchor = scene_pos
        # CR-01 fix: capture the PRE-resize snapshot (emitted on resize-commit).
        self._boxes_interaction_start_snapshot = self.boxes_snapshot()
        self.viewport().grabMouse()

    def _begin_create_box(self, scene_pos: QPointF) -> None:
        """Arm an Alt+drag box-create (D-13). Stores the anchor + sets the flag."""
        self._creating_box = True
        self._create_anchor = scene_pos
        # CR-01 fix: capture the PRE-create snapshot (emitted on create-commit).
        self._boxes_interaction_start_snapshot = self.boxes_snapshot()
        self.viewport().grabMouse()
        # Swap the preview_item pen to the amber create-preview colour for the
        # duration of the drag (UI-SPEC §12e). Restored on release.
        self.preview_item.setPen(
            QPen(_BOX_CREATE_PREVIEW_COLOR, 2, Qt.PenStyle.DashLine)
        )

    def _restore_preview_pen(self) -> None:
        """Restore the preview_item pen to the cyan mask-rect colour after a box-create."""
        self.preview_item.setPen(
            QPen(QColor(0, 212, 255, 200), 2, Qt.PenStyle.DashLine)
        )
        self.preview_item.setPath(QPainterPath())

    def _advance_resize(self, curr: QPointF) -> None:
        """Move the dragged corner during a resize drag, clamping the opposite
        corner so the box stays >= MIN_BOX_SIZE during the drag (D-06).

        The anchor corner (opposite the dragged one) is held fixed; the two
        edges adjacent to the dragged corner follow the cursor. The clamp
        prevents the box from inverting/collapsing below the 8x8 min during the
        drag — the final clamp is re-applied on release.
        """
        item = self._resizing_box
        if item is None:
            return
        start = self._resize_start_rect
        corner = self._resize_corner
        # Anchor = the corner opposite the dragged one.
        ax = start.right() if corner in ("TL", "BL") else start.left()
        ay = start.bottom() if corner in ("TL", "TR") else start.top()
        nx, ny = curr.x(), curr.y()
        # Clamp so width/height never drop below MIN_BOX_SIZE during the drag:
        # if the cursor crosses past the anchor + MIN_BOX_SIZE, pin the moving
        # edge at anchor +/- MIN_BOX_SIZE (keeps the orientation stable).
        if corner in ("TL", "BL"):  # moving the LEFT edge
            nx = min(nx, ax - MIN_BOX_SIZE)
        else:  # TR/BR: moving the RIGHT edge
            nx = max(nx, ax + MIN_BOX_SIZE)
        if corner in ("TL", "TR"):  # moving the TOP edge
            ny = min(ny, ay - MIN_BOX_SIZE)
        else:  # BL/BR: moving the BOTTOM edge
            ny = max(ny, ay + MIN_BOX_SIZE)
        new_rect = QRectF(
            min(ax, nx), min(ay, ny), abs(nx - ax), abs(ny - ay)
        ).normalized()
        item.setRect(new_rect)
        item._sync_handles()

    def _commit_resize(self) -> None:
        """Finalize a resize drag: ensure the rect is >= 8x8 scene px (D-06),
        reposition handles, and emit ``boxes_modified`` once (only on a real
        resize).

        WR-04 (plan 03-07): delta-check — a click-on-handle-with-no-drag leaves
        the rect unchanged; do NOT emit boxes_modified in that case (it would
        push a redundant no-op BOXES snapshot). ``_resize_start_rect`` was
        captured in ``_begin_resize``; only emit when the final rect differs.
        """
        item = self._resizing_box
        before = self._boxes_interaction_start_snapshot
        self._resizing_box = None
        if item is None:
            return
        r = item.rect()
        w = max(r.width(), MIN_BOX_SIZE)
        h = max(r.height(), MIN_BOX_SIZE)
        item.setRect(QRectF(r.x(), r.y(), w, h))
        item._sync_handles()
        # Resize-COMMIT re-wrap (plan 04-09 Gap 1): refresh the overlay ONCE per
        # drag so the text re-wraps/re-fits to the final rect. The per-mousemove
        # _advance_resize path stays setPos-only (RC-1 discipline — a full
        # document rebuild must NOT run per-mousemove).
        item.refresh_text_overlay()
        # WR-04 delta-check: only emit when the resize actually changed the rect.
        if item.rect() != self._resize_start_rect:
            self.boxes_modified.emit(before)

    def _advance_create(self, curr: QPointF) -> None:
        """Advance the amber-dashed create preview rect during the drag (§12e)."""
        path = QPainterPath()
        path.addRect(QRectF(self._create_anchor, curr).normalized())
        self.preview_item.setPath(path)

    def _commit_create(self, event) -> None:
        """On release, create a user BoxItem if the dragged rect >= 8x8 (D-13/D-06).

        A rect smaller than the 8x8 min is a no-op (no zero-area box). The new
        box is added to the layer, selected, and ``boxes_modified`` is emitted.
        The preview_item pen is restored to cyan + the path is cleared (§12e).
        """
        curr = self._scene_pos(event)
        self._creating_box = False
        self._restore_preview_pen()
        rect = QRectF(self._create_anchor, curr).normalized()
        if rect.width() < MIN_BOX_SIZE or rect.height() < MIN_BOX_SIZE:
            return  # < 8x8 — no-op (D-06 min on create-release)
        # Build a user PageBox with int coords (Pitfall 6 — int at the
        # Box<->QRectF boundary; payload None for user boxes until OCR runs).
        # G-07-3: the new box is born with the app-level default style when
        # MainWindow supplied a provider (None return -> style None -> the
        # renderer's TextStyle() defaults apply, today's behavior).
        pb = PageBox(
            box=Box(int(rect.x()), int(rect.y()), int(rect.right()), int(rect.bottom())),
            origin=USER,
            payload=None,
            style=(
                self.new_box_style_provider()
                if self.new_box_style_provider is not None
                else None
            ),
        )
        item = BoxItem(pb)
        self._scene.addItem(item)
        item.setVisible(self._box_overlay_visible)
        item.setEnabled(self._box_overlay_visible)
        # Phase 4 text-overlay layer (D-12): a freshly-created user box has no
        # text yet, but sync the flag for consistency (a later OCR write would
        # show text under the current text-layer state).
        item.set_text_overlay_visible(self._text_overlay_visible)
        self._box_items.append(item)
        self._deselect_box()
        item.setSelected(True)
        # Plan 07-02: the fresh box is the sole selection — make it the primary.
        self._selection_order = [it for it in self._box_items if it.isSelected()]
        self._primary_box = item
        self._sync_handles_visibility()
        self._refresh_empty_box_hint()
        # D-01 auto-OCR seam: the box arrives with recognized text. The
        # signal lets MainWindow dispatch the OCR Worker off the GUI thread
        # (the < 8x8 no-op above already returned — a real box always emits;
        # RESEARCH Pitfall 6, T-01-07).
        self.ocr_requested.emit(item)
        # CR-01 fix: emit the PRE-create snapshot (captured at _begin_create_box),
        # i.e. the layer WITHOUT the new box — what undo restores to.
        self.boxes_modified.emit(self._boxes_interaction_start_snapshot)

    def _remove_box(self, item: BoxItem) -> None:
        """Remove a BoxItem from the scene/list + emit boxes_modified (D-12).

        Silent (no confirm dialog) — the BOXES undo stack in plan 03-05
        recovers the box. Used by the Delete/Backspace key handler.

        Plan 07-06 (G-07-6): the removed wrapper is retired to the graveyard
        (deferred release) — the Delete key is hit mid-event-loop with the
        same queued-update precondition as the undo path, so a synchronous
        last-ref drop would delete the C++ item before the pending flush.
        """
        if item not in self._box_items:
            return
        # CR-01 fix: capture the PRE-delete snapshot (with the box still present)
        # BEFORE removing — undo restores to this state, recovering the box.
        before = self.boxes_snapshot()
        self._scene.removeItem(item)
        self._box_items.remove(item)
        self._retire_boxes([item])
        self._refresh_empty_box_hint()
        # Plan 07-02: a removed box can no longer be the primary — promote the
        # last-selected remaining item (UI-SPEC §32) + re-assert handle
        # visibility (D-09).
        self._refresh_primary_box()
        self.boxes_modified.emit(before)

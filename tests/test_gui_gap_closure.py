"""GUI regression probes for the Phase 8 gap-closure plan (08-10).

This suite carries the failing-then-passing probes that close the verified
defects from ``08-VERIFICATION.md``:

- CR-01 — recompose consumers read stale live ``pagebox.box`` (birth geometry)
  after a move/resize, so the auto mask pastes at the pre-move origin;
- CR-03 — ``_on_std_dev_threshold_changed`` lacks the no-fit guard its sibling
  ``_recompose_boxes_auto_plane`` has, so a threshold tweak after a geometry op
  (which invalidates per-box masks per the 08-01 policy) composes an empty
  binary and silently wipes the auto plane;
- CR-04 — inpaint/batch-clean consumption clears only the display composite,
  not the three planes, so the consumed overlay resurrects on the next
  recompose and a re-run re-processes the cleaned region;
- CR-02 — the detect-mode batch refresh passes EXPLICITLY-empty manual/erase
  planes to ``set_planes``, wiping hand strokes + the erase ledger;
- WR-02 — a detect-mode batch never marks the touched pages dirty, so Close
  silently drops the detected boxes.

Probes 1-2 (Task 1) FAIL on the pre-fix code with the exact signatures recorded
in ``08-VERIFICATION.md`` (content bbox back at (5,5,29,34); auto plane wiped),
then PASS after the fix. Probes 3-5 (Task 2) and probe 6 (Task 3) follow the
same RED->GREEN contract.

These tests need a display; on headless CI they skip via ``importorskip``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blk(x1: int, y1: int, x2: int, y2: int) -> SimpleNamespace:
    """Build a duck-typed fake TextBlock (only .xyxy is read by the build)."""
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


def _window_with_page(qtbot, tmp_path: Path, w: int = 60, h: int = 50) -> MainWindow:
    """Build a MainWindow with a real page image loaded + data-model registration.

    Mirrors ``tests/test_gui_detection_boxes.py::_window_with_page``: a solid
    (w x h) PNG loaded onto the canvas AND registered in ``image_files`` +
    the FileTable current row so the 08-07 seam's ImageFile writes (raw
    retention, dirty) land on a real ``ImageFile``.
    """
    from manga_ai_studio.core.image_file import ImageFile

    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    from PIL import Image as PILImage

    page_png = tmp_path / "page.png"
    PILImage.new("RGB", (w, h), color=(200, 200, 200)).save(page_png)
    assert window.canvas.set_image_from_path(page_png) is True
    window.image_files = [ImageFile(path=page_png)]
    window.file_table.set_pages([page_png])
    window.file_table.select_path(page_png)
    window._last_page_index = 0
    return window


def _content_bbox(bin_arr: np.ndarray) -> tuple[int, int, int, int] | None:
    """The non-zero content bbox of an (H, W) binary as (y1, x1, y2, x2) or
    None when the array is empty (the 08-VERIFICATION.md probe signature)."""
    ys, xs = np.nonzero(bin_arr)
    if ys.size == 0:
        return None
    return int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max())


def _box_content_bbox(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    """The numpy content bbox a box (x1,y1,x2,y2) fills under EXCLUSIVE-max
    Box semantics: rows/cols [y1..y2-1] x [x1..x2-1] -> (y1, x1, y2-1, x2-1).

    A fitted mask that saturates its box (the full-page-content fixture)
    materializes exactly this bbox — the 08-VERIFICATION.md probe recorded the
    same shape as box coords (content bbox (25,15,49,44) == np bbox
    (25,15,48,43) for the moved rect).
    """
    return (y1, x1, y2 - 1, x2 - 1)


# ===========================================================================
# Task 1 — CR-01 + CR-03: recompose consumers read live geometry; the
# threshold slot gains the no-fit guard
# ===========================================================================


@pytest.mark.gui
def test_recompose_after_move_uses_live_geometry(qtbot, tmp_path) -> None:
    """CR-01 (08.1 D-01 inverted): after Detect + a box move, a threshold
    change recomposes the auto mask at the box's CURRENT (moved) position —
    never the birth origin. Uses noisy page so the box is high-std -> will_inpaint
    -> auto has content (uniform -> will_fill would be auto empty)."""
    # Noisy page to make the box high-std -> will_inpaint -> auto has content (08.1 inverted gate)
    rng = np.random.default_rng(10)
    noisy = rng.integers(0, 256, size=(50, 60, 3), dtype=np.uint8)
    from PIL import Image as PILImage

    window = _window_with_page(qtbot, tmp_path)
    # Overwrite the white page with noisy image at same dims
    window.canvas.set_image_from_numpy(noisy)
    # Update the ImageFile's current_image to keep data model consistent
    window.image_files[0].current_image = noisy.copy()
    window.action_detect_boxes_mode.setChecked(True)

    # Full-page-content binary + the (5,5,29,34) fixture box: the fitted mask
    # fills the box interior, so the composed content bbox == the box.
    heat = np.full((50, 60), 255, dtype=np.uint8)
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 29, 34)]})
    item = window.canvas._box_items[0]
    assert item.current_box().as_tuple == (5, 5, 29, 34)
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(5, 5, 29, 34), (
        "fixture sanity: at birth geometry the composed content is the box"
    )

    before = window.canvas.boxes_snapshot()
    item.setRect(QRectF(25, 15, 24, 29))  # birth (5,5,29,34) -> moved (25,15,49,44)
    window.canvas.boxes_modified.emit(before)  # marks the box stale (NO refit)

    # quick-260822-gnq: a move commit is CHEAP — no recompose happens; the
    # auto plane stays at the BIRTH position and the box is marked stale.
    assert item.geometry_stale is True
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(5, 5, 29, 34), (
        "a move commit must NOT recompose: the auto plane survives untouched"
    )

    # The explicit re-detect path re-fits + recomposes at the MOVED position.
    # OCR leg stubbed (hermetic: no model load).
    item.pagebox.payload.text = ""  # fixture payload carries no text attr
    window._dispatch_ocr_for_box = lambda it: None
    window._on_box_redetect_requested(item)
    assert item.geometry_stale is False
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(25, 15, 49, 44), (
        "the explicit re-detect must compose at the moved rect"
    )

    # The threshold tweak must NOT jump the content back to the birth origin.
    # Use a low threshold (5) that keeps the high-std noisy box as will_inpaint (D-01 inverted)
    window._on_std_dev_threshold_changed(5.0)
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(25, 15, 49, 44), (
        "CR-01: the recomposed content must stay at the moved rect, not jump "
        "back to the birth origin (5,5,29,34) — the 08-VERIFICATION.md probe (08.1 D-01 inverted: keep high-std as will_inpaint)"
    )


@pytest.mark.gui
def test_threshold_tweak_after_invalidation_does_not_wipe_auto_plane(
    qtbot, tmp_path
) -> None:
    """CR-03 (08.1 D-01 inverted): a std-dev threshold tweak after a geometry
    op (which invalidated every per-box mask per the 08-01 policy) must NOT
    compose an all-mask-None empty binary and silently wipe the auto plane.
    Uses noisy page so the box is high-std -> will_inpaint -> auto has content."""
    rng = np.random.default_rng(11)
    noisy = rng.integers(0, 256, size=(50, 60, 3), dtype=np.uint8)
    window = _window_with_page(qtbot, tmp_path)
    window.canvas.set_image_from_numpy(noisy)
    window.image_files[0].current_image = noisy.copy()
    window.action_detect_boxes_mode.setChecked(True)

    heat = np.full((50, 60), 255, dtype=np.uint8)
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 29, 34)]})
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(5, 5, 29, 34)
    auto_before = window.canvas._auto_bin.copy()

    # Geometry-op invalidation (08-01 policy): every per-box fit is dropped
    # while the auto plane keeps the geometry-transformed content.
    for it in window.canvas._box_items:
        it.pagebox.mask = None
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(5, 5, 29, 34), (
        "the invalidation itself must not touch the auto plane"
    )

    # A threshold tweak must NOT derive over the mask-less boxes into an empty
    # binary that wipes the plane.
    window._on_std_dev_threshold_changed(15.5)

    assert window.canvas._auto_bin is not None, (
        "CR-03: the auto plane must not be wiped to None/empty after one tweak"
    )
    assert np.array_equal(window.canvas._auto_bin, auto_before), (
        "CR-03: the auto plane must keep its pre-tweak content (no-fit guard)"
    )
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(5, 5, 29, 34)


# ===========================================================================
# Task 2 — CR-04 + CR-02: consume_mask_display clears all three planes
# signal-silently; the detect-batch refresh replaces only the auto plane
# ===========================================================================


def _seed_planes(window, manual_bin, erase_bin, auto_bin) -> None:
    """Replace the live three planes via set_planes (the seeded-content path)."""
    from manga_ai_studio.core.mask_editor import numpy_binary_to_mask_qimage

    window.canvas.set_planes(
        numpy_binary_to_mask_qimage(manual_bin),
        numpy_binary_to_mask_qimage(erase_bin),
        auto_bin,
    )


@pytest.mark.gui
def test_consume_mask_display_clears_planes_and_no_resurrection(
    qtbot, tmp_path
) -> None:
    """CR-04: consuming the mask (inpaint / batch-clean) must clear ALL THREE
    planes signal-silently — the consumed overlay cannot resurrect on the next
    stroke/undo/page-switch recompose, so a re-run cannot re-process the
    cleaned region.

    Pre-fix: no ``consume_mask_display`` exists (RED on AttributeError) and the
    display-only clear leaves the planes holding the consumed content.
    """
    window = _window_with_page(qtbot, tmp_path)
    manual_bin = np.zeros((50, 60), dtype=np.uint8)
    manual_bin[2:12, 2:12] = 255
    erase_bin = np.zeros((50, 60), dtype=np.uint8)
    erase_bin[30:40, 30:40] = 255
    auto_bin = np.zeros((50, 60), dtype=np.uint8)
    auto_bin[40:50, 40:50] = 255
    _seed_planes(window, manual_bin, erase_bin, auto_bin)
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_manual)) > 0
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_erase)) > 0
    assert window.canvas._auto_bin is not None

    fired: list[bool] = []
    window.canvas.mask_modified.connect(lambda: fired.append(True))
    window.canvas.consume_mask_display()

    assert not fired, (
        "consumption is not a paint action — no mask_modified emission, so no "
        "spurious mask-undo entry (the CR-16 2-stack contract)"
    )
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_manual)) == 0, (
        "CR-04: the manual plane must be emptied"
    )
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_erase)) == 0, (
        "CR-04: the erase plane must be emptied"
    )
    assert window.canvas._auto_bin is None, "CR-04: the auto plane must clear"
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas.get_mask())) == 0, (
        "CR-04: the composite must be content-free after consumption"
    )

    # The stroke-commit stand-in recompose must stay content-free — the
    # consumed overlay cannot resurrect from the emptied planes.
    window.canvas.recompose_mask()
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas.get_mask())) == 0, (
        "CR-04: the consumed overlay must not resurrect on the next recompose"
    )


@pytest.mark.gui
def test_detect_batch_refresh_preserves_manual_and_erase(qtbot, tmp_path) -> None:
    """CR-02: a detect-mode batch refresh must replace ONLY the auto plane —
    the current page's live manual/erase planes (hand strokes + the erase
    ledger, which the dispatch-time flush persists only as the flat composite)
    survive the restore.

    Pre-fix: the refresh passes EXPLICITLY-empty manual/erase to ``set_planes``
    -> the seeded strokes are wiped (RED).
    """
    from manga_ai_studio.core.mask_editor import numpy_binary_to_mask_qimage
    from manga_ai_studio.core.mask_planes import pack_binary, unpack_binary

    window = _window_with_page(qtbot, tmp_path)
    manual_bin = np.zeros((50, 60), dtype=np.uint8)
    manual_bin[2:12, 2:12] = 255
    erase_bin = np.zeros((50, 60), dtype=np.uint8)
    erase_bin[30:40, 30:40] = 255
    _seed_planes(window, manual_bin, erase_bin, None)
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_manual)) > 0

    # Flat-restore prerequisites (:6353): a non-null content mask + a packed
    # distinct auto binary (the batch detect result).
    imf = window.image_files[0]
    imf.mask = numpy_binary_to_mask_qimage(np.full((50, 60), 255, dtype=np.uint8))
    auto_bin = np.zeros((50, 60), dtype=np.uint8)
    auto_bin[40:50, 40:50] = 255
    imf.auto_mask = pack_binary(auto_bin)

    window._refresh_current_page_after_batch("detect")

    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_manual)) > 0, (
        "CR-02: hand strokes must survive a detect-mode batch restore"
    )
    assert np.array_equal(
        mask_to_numpy_binary(window.canvas._mask_manual) > 0,
        manual_bin > 0,
    ), "CR-02: the manual plane content must be untouched"
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_erase)) > 0, (
        "CR-02: the erase ledger must survive a detect-mode batch restore"
    )
    assert window.canvas._auto_bin is not None
    assert np.array_equal(
        window.canvas._auto_bin, unpack_binary(imf.auto_mask, 50, 60)
    ), "the batch result must replace only the auto plane"


@pytest.mark.gui
def test_batch_clean_refresh_clears_planes(qtbot, tmp_path) -> None:
    """CR-04 in the batch path: the clean-mode refresh consumes the mask — all
    three planes cleared — so a re-clean cannot re-process the cleaned region.
    (No cleaned file exists for the fixture page, so the reload is skipped and
    the consume is the only mutation.)

    Pre-fix: the clean branch clears only the display composite, leaving the
    planes holding content (RED).
    """
    window = _window_with_page(qtbot, tmp_path)
    manual_bin = np.zeros((50, 60), dtype=np.uint8)
    manual_bin[2:12, 2:12] = 255
    erase_bin = np.zeros((50, 60), dtype=np.uint8)
    erase_bin[30:40, 30:40] = 255
    auto_bin = np.zeros((50, 60), dtype=np.uint8)
    auto_bin[40:50, 40:50] = 255
    _seed_planes(window, manual_bin, erase_bin, auto_bin)

    window._refresh_current_page_after_batch("clean")

    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_manual)) == 0, (
        "CR-04: the clean-path consume must clear the manual plane"
    )
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas._mask_erase)) == 0, (
        "CR-04: the clean-path consume must clear the erase plane"
    )
    assert window.canvas._auto_bin is None, (
        "CR-04: the clean-path consume must clear the auto plane"
    )
    assert np.count_nonzero(mask_to_numpy_binary(window.canvas.get_mask())) == 0


# ===========================================================================
# Task 3 — WR-02: a detect-mode batch marks every touched page dirty
# ===========================================================================


@pytest.mark.gui
def test_detect_batch_marks_pages_dirty(qtbot, tmp_path) -> None:
    """WR-02 (plan 08-10): a detect-mode batch completion marks EVERY touched
    page dirty (ok > 0), so Close prompts save instead of silently dropping
    the freshly detected boxes; the title reflects the dirty state. Clean-only
    mode must NOT dirty (behavior unchanged).

    Pre-fix: ``_on_batch_finished`` never marks dirty -> RED.
    """
    from manga_ai_studio.core.image_file import ImageFile

    window = _window_with_page(qtbot, tmp_path)
    window.image_files.append(ImageFile(path=tmp_path / "page2.png"))
    assert not any(imf.dirty for imf in window.image_files)

    window._batch_mode = "detect"
    window._on_batch_finished({"ok": 2, "failed": [], "total": 2})

    assert all(imf.dirty for imf in window.image_files), (
        "WR-02: every page a detect batch touched must be marked dirty so "
        "Close prompts save"
    )
    assert "*" in window.windowTitle(), (
        "the title must reflect the dirty state (the * suffix)"
    )

    # Clean-only mode: no spurious dirty marking.
    window2 = _window_with_page(qtbot, tmp_path)
    window2._batch_mode = "clean"
    window2._on_batch_finished({"ok": 1, "failed": [], "total": 1})
    assert not any(imf.dirty for imf in window2.image_files), (
        "clean-only batches must not mark pages dirty"
    )


# ===========================================================================
# Plan 08-10 review (WR-01): a CANCELLED/aborted detect batch must also dirty
# the processed pages, or Close silently drops the freshly detected boxes
# ===========================================================================


@pytest.mark.gui
def test_detect_batch_cancel_marks_pages_dirty(qtbot, tmp_path) -> None:
    """WR-02 (cancel/abort coverage, plan 08-10): a CANCELLED detect batch must
    mark every page dirty too.

    ``_on_batch_finished`` fires only on the Worker's successful ``result``
    path — on cancel/abort the Worker emits ``aborted`` (no ``result``) and on
    exception ``error`` (no ``result``), so ``_on_batch_cleanup`` (connected to
    ``aborted`` AND ``finished``) is the only handler that runs. It must dirty
    the already-processed pages (the batch loop writes each page's state before
    the NEXT page's abort gate) or Close silently drops the detected
    boxes/masks. Clean-only mode must NOT dirty even on cancel.
    """
    from manga_ai_studio.core.image_file import ImageFile

    window = _window_with_page(qtbot, tmp_path)
    window.image_files.append(ImageFile(path=tmp_path / "page2.png"))
    assert not any(imf.dirty for imf in window.image_files)

    # The Esc -> _cancel_batch -> worker.abort() path: _batch_cancelled is set
    # by _cancel_batch and _batch_mode is still the dispatched mode.
    window._batch_mode = "detect"
    window._batch_cancelled = True
    window._on_batch_cleanup(None)

    assert all(imf.dirty for imf in window.image_files), (
        "a cancelled detect batch must mark every page dirty so Close "
        "prompts save instead of silently dropping the detected boxes"
    )
    assert "*" in window.windowTitle(), (
        "the title must reflect the dirty state (the * suffix)"
    )

    # Clean-only mode: no spurious dirty marking on the cancel path.
    window2 = _window_with_page(qtbot, tmp_path)
    window2._batch_mode = "clean"
    window2._batch_cancelled = True
    window2._on_batch_cleanup(None)
    assert not any(imf.dirty for imf in window2.image_files), (
        "clean-only batches must not mark pages dirty even on cancel"
    )


# ===========================================================================
# Plan 08-10 review (WR-02): dims-preserving geometry op leaves a stale raw
# that must NOT wipe the auto plane on the next live re-derive
# ===========================================================================


@pytest.mark.gui
def test_rotate_then_dilate_nudge_keeps_auto_plane(qtbot, tmp_path) -> None:
    """WR-02 (plan 08-10, 08.1 D-01 inverted): a dims-preserving geometry op
    (180-degree rotate) followed by a live dilation nudge must NOT silently wipe
    the auto plane. Uses noisy page so the box is high-std -> will_inpaint."""
    rng = np.random.default_rng(12)
    noisy = rng.integers(0, 256, size=(50, 60, 3), dtype=np.uint8)
    window = _window_with_page(qtbot, tmp_path)
    window.canvas.set_image_from_numpy(noisy)
    window.image_files[0].current_image = noisy.copy()
    window.action_detect_boxes_mode.setChecked(True)

    # Non-symmetric content (a top-left block) so a 180-degree rotate changes it.
    heat = np.zeros((50, 60), dtype=np.uint8)
    heat[2:20, 2:20] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 29, 34)]})
    imf = window.image_files[0]
    assert imf.raw_detected_mask is not None, "fixture sanity: raw is retained"
    # 08.1 inverted: noisy page high-std -> will_inpaint, but fitted mask may be smaller than box due to content; just check it has content
    assert window.canvas._auto_bin is not None and np.count_nonzero(window.canvas._auto_bin) > 0, (
        "fixture sanity: the auto plane must have content for high-std box (08.1 D-01 inverted)"
    )

    # 180-degree rotate — dims-preserving (50x60 -> 50x60) — driving
    # ``_apply_geometry_op`` directly (the real ``_rotate_page`` machinery
    # needs a full TextBlock payload; the headless ``_blk`` fixture payload is
    # shape-only). Image + mask rotate under the ONE np.rot90(k=2) convention
    # while every box is rotated and its mask/std_dev invalidated per the Phase
    # 8 field policy — exactly what a real rotate applies. The geometry op must
    # then invalidate the retained raw (no longer in the page frame).
    from manga_ai_studio.core.box_model import PageBox
    from manga_ai_studio.core.image_ops import transform_box

    def _rotate_180_transform():
        img = window.canvas.get_image_numpy()
        h, w = img.shape[:2]
        new_img = np.rot90(img, k=2).copy()
        new_mask = np.rot90(window.canvas._auto_bin, k=2).copy()
        new_boxes = [
            PageBox(
                box=transform_box(pb.box, w, h, 2),
                origin=pb.origin,
                mask=None,
                std_dev=None,
            )
            for pb in window.canvas.boxes_snapshot()
        ]
        return new_img, new_mask, new_boxes

    window._apply_geometry_op("rotate-180", geometry=True, transform_fn=_rotate_180_transform)

    assert imf.raw_detected_mask is None, (
        "WR-02: the geometry op must invalidate the retained raw mask"
    )
    assert imf.auto_mask is None, (
        "WR-02: the derived auto slot must clear with the raw"
    )

    # Live dilation nudge: must not re-derive a stale raw into an empty binary
    # that wipes the rotated plane.
    window._rederive_auto_layer()
    assert window.canvas._auto_bin is not None
    assert np.count_nonzero(window.canvas._auto_bin) > 0, (
        "WR-02: the auto plane must retain content after rotate + dilation nudge"
    )

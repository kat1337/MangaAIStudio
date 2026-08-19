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
    """CR-01: after Detect + a box move, a threshold change recomposes the auto
    mask at the box's CURRENT (moved) position — never the birth origin.

    Pre-fix (08-VERIFICATION.md probe): the threshold slot reads the live
    pageboxes whose ``.box`` is birth geometry (the canvas only ever
    ``setRect``s; geometry materialization lives solely in
    ``boxes_snapshot()``), so the composite jumped back to (5,5,29,34) after
    one threshold change. Post-fix: the slot composes from
    ``canvas.boxes_snapshot()`` and the content stays at the moved rect
    (25,15,49,44).
    """
    window = _window_with_page(qtbot, tmp_path)
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
    window.canvas.boxes_modified.emit(before)  # runs _refit_changed_boxes

    # The move-commit refit already recomposes at the MOVED position.
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(25, 15, 49, 44), (
        "the refit path must compose at the moved rect"
    )

    # The threshold tweak must NOT jump the content back to the birth origin.
    window._on_std_dev_threshold_changed(50.0)
    assert _content_bbox(window.canvas._auto_bin) == _box_content_bbox(25, 15, 49, 44), (
        "CR-01: the recomposed content must stay at the moved rect, not jump "
        "back to the birth origin (5,5,29,34) — the 08-VERIFICATION.md probe"
    )


@pytest.mark.gui
def test_threshold_tweak_after_invalidation_does_not_wipe_auto_plane(
    qtbot, tmp_path
) -> None:
    """CR-03: a std-dev threshold tweak after a geometry op (which invalidated
    every per-box mask per the 08-01 policy) must NOT compose an all-mask-None
    empty binary and silently wipe the auto plane.

    Pre-fix (08-VERIFICATION.md probe): content present before the tweak, bbox
    None after one tweak — the whole plane emptied. Post-fix: the no-fit guard
    returns early and the plane keeps its pre-tweak content.
    """
    window = _window_with_page(qtbot, tmp_path)
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

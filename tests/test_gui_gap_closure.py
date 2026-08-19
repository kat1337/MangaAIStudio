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

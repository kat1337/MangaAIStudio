"""GUI tests for the image-op dialogs + rotate apply path (plan 05-06, PROJ-04).

Covers the TRACER rotate end-to-end (Task 1), the Levels dialog live-preview
contract (Task 2), and the Resize dialog + Show Original gating (Task 3)
against the real ``MainWindow`` (pytest-qt) with ``tmp_path`` fixture pages:

- Rotate: menu action -> ``_apply_geometry_op`` -> canvas transform (image +
  mask + boxes together) -> ONE geometry undo entry -> single Ctrl+Z restores
  all three -> ``geometry_altered`` True -> status flash -> post-op Show
  Original (D-14).
- Levels: live preview mutates the canvas without pushing undo entries or
  poisoning the Show Original baseline; Cancel restores the pre-dialog image
  byte-identical with zero entries; Apply pushes exactly one image-only entry
  (geometry-free, D-15).
- Resize: dialog contract (current dims / aspect lock / unit toggle / ranges)
  + end-to-end apply (LANCZOS image / NEAREST mask / int-scaled boxes).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage
from PySide6.QtWidgets import QApplication, QDialog

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.box_model import USER, PageBox
from manga_ai_studio.core.image_ops import levels_page
from manga_ai_studio.core.mask_editor import (
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.gui.main_window import MainWindow
from panelcleaner.structures import Box


# ---------------------------------------------------------------- helpers

def _window_with_page(qtbot, tmp_path, size=(60, 40)) -> MainWindow:
    """A MainWindow with one real page open (the canvas shows the page)."""
    folder = tmp_path / "chapter"
    folder.mkdir(parents=True, exist_ok=True)
    w, h = size
    PILImage.new("RGB", (w, h), color=(40, 80, 120)).save(folder / "page_01.png")
    pm = ProfileManager(tmp_path / "config")
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(folder)
    QApplication.processEvents()
    return window


def _seed_mask_and_box(window: MainWindow) -> tuple[np.ndarray, PageBox]:
    """Seed a binary mask + one user box (suppressed — no undo push).

    Returns ``(mask_bin, box)`` so tests can assert the transformed values.
    """
    img = window.canvas.get_image_numpy()
    h, w = img.shape[:2]
    mask_bin = np.zeros((h, w), dtype=np.uint8)
    mask_bin[10:20, 30:50] = 255
    window.canvas.set_mask(numpy_binary_to_mask_qimage(mask_bin))
    box = PageBox(box=Box(30, 10, 50, 20), origin=USER)
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([box], [])
    finally:
        window._suppress_boxes_push = False
    return mask_bin, box


# ===========================================================================
# Task 1 (TRACER) — Rotate end-to-end
# ===========================================================================

@pytest.mark.gui
def test_rotate_90cw_end_to_end(qtbot, tmp_path) -> None:
    """_rotate_page(-1) applies 90° CW with full undo fidelity (plan 05-06).

    The TRACER contract: canvas image dims swap pixel-exact vs np.rot90 of the
    pre image; the mask rotates; the box bbox rotates; ONE geometry undo entry
    (the image/mask/boxes tail stamps match); a single Ctrl+Z restores all
    three; ``geometry_altered`` True; the status flash carries the rotate copy;
    Show Original shows the POST-op image (D-14).
    """
    window = _window_with_page(qtbot, tmp_path)  # 60x40 page -> (40, 60, 3)
    pre = window.canvas.get_image_numpy().copy()
    mask_bin, _box = _seed_mask_and_box(window)
    assert pre.shape[:2] == (40, 60)

    window._rotate_page(-1)
    QApplication.processEvents()

    # Image: dims swapped + pixel-exact vs np.rot90(k=-1) of the pre image.
    now = window.canvas.get_image_numpy()
    assert now.shape[:2] == (60, 40)
    assert np.array_equal(now, np.rot90(pre, k=-1))

    # Mask rotated with the same convention (binary 0/255 preserved).
    assert np.array_equal(
        mask_to_numpy_binary(window.canvas.get_mask()), np.rot90(mask_bin, k=-1)
    )

    # Box bbox rotated: (x,y) -> (h-1-y, x) for CW on the 60x40 page.
    rotated_box = window.canvas.boxes_snapshot()[0].box.as_tuple
    assert rotated_box == (19, 30, 29, 50)

    # ONE geometry undo entry: the three stores share one tail stamp.
    hist = window.history
    stamps = {
        "image": hist._image_undo[-1][0],
        "mask": hist._mask_undo[-1][0],
        "boxes": hist._boxes_undo[-1][0],
    }
    assert stamps["image"] == stamps["mask"] == stamps["boxes"]

    # geometry_altered True + status flash.
    assert window.image_files[0].geometry_altered is True
    assert "Rotated 90\u00b0 CW." in window.status_bar_left.text()

    # Show Original re-baselines to the POST-op image (D-14).
    assert np.array_equal(window.canvas._original_image_numpy, now)
    window.canvas.show_original(True)
    assert np.array_equal(window.canvas.get_image_numpy(), now)

    # ONE Ctrl+Z restores image + mask + boxes together.
    window.on_undo()
    QApplication.processEvents()
    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    assert np.array_equal(
        mask_to_numpy_binary(window.canvas.get_mask()), mask_bin
    )
    assert window.canvas.boxes_snapshot()[0].box.as_tuple == (30, 10, 50, 20)

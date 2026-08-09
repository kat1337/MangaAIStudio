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
from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import QApplication, QDialog

from manga_ai_studio.config.profile_manager import ProfileManager
from manga_ai_studio.core.box_model import USER, PageBox
from manga_ai_studio.core.image_ops import levels_page
from manga_ai_studio.core.mask_editor import (
    mask_to_numpy_binary,
    numpy_binary_to_mask_qimage,
)
from manga_ai_studio.gui.levels_dialog import LevelsDialog
from manga_ai_studio.gui.main_window import MainWindow
from manga_ai_studio.gui.resize_dialog import ResizeDialog
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


# ===========================================================================
# Task 2 — Levels dialog: live preview + Cancel-restores-exactly + Apply-one
# ===========================================================================

@pytest.mark.gui
def test_levels_defaults_and_clamp(qtbot) -> None:
    """LevelsDialog opens at 0/255/1.00 with the white>black cross-clamp.

    Dragging black to 200 moves white's minimum to 201, and the preview
    callback never receives white <= black (T-05-07 — no inverted map).
    """
    calls: list = []
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    dlg = LevelsDialog(page_image=img, preview_callback=lambda v: calls.append(v))
    qtbot.addWidget(dlg)

    assert dlg.black_spin.value() == 0
    assert dlg.white_spin.value() == 255
    assert dlg.gamma_spin.value() == 1.00

    dlg.black_spin.setValue(200)
    assert dlg.white_spin.minimum() == 201  # white min follows black+1
    dlg.black_spin.setValue(254)
    assert dlg.white_spin.minimum() == 255
    dlg.white_spin.setValue(100)  # white below black+1 -> clamped up
    assert dlg.black_spin.maximum() == dlg.white_spin.value() - 1
    assert dlg.black_spin.value() <= dlg.white_spin.value() - 1

    # The preview never received an inverted map.
    assert calls, "preview callback never fired"
    assert all(white > black for black, white, _gamma in calls)


@pytest.mark.gui
def test_levels_cancel_restores_exactly(qtbot, tmp_path, monkeypatch) -> None:
    """Cancel restores the pre-dialog image byte-identical with zero entries.

    Dragging the sliders during the dialog mutates the canvas (live preview,
    no pushes — Pitfall 9); Cancel re-displays the detached base silently:
    no undo entry, no status flash (UI-SPEC surface 25).
    """
    window = _window_with_page(qtbot, tmp_path)
    pre = window.canvas.get_image_numpy().copy()

    def _fake_exec(dlg):
        dlg.black_spin.setValue(120)  # preview mutates the canvas
        dlg.white_spin.setValue(200)
        dlg.gamma_spin.setValue(1.7)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(LevelsDialog, "exec", _fake_exec)
    window._on_levels()
    QApplication.processEvents()

    assert np.array_equal(window.canvas.get_image_numpy(), pre)  # exact restore
    assert not window.history.can_undo()  # no undo entry was pushed
    assert window.status_bar_left.text() != "Levels applied."  # no flash


@pytest.mark.gui
def test_levels_apply_pushes_one_entry(qtbot, tmp_path, monkeypatch) -> None:
    """Apply commits the previewed state: ONE image-only entry (D-15).

    Levels is geometry-free: masks and boxes are untouched, the image entry
    is the only store pushed, geometry_altered stays False (A4), the status
    flash fires, and Show Original re-baselines to the post-levels image
    (D-14).

    Restore semantics (UI-review FLAG, surface 25/28): the live preview
    mutates the canvas mid-dialog, so Apply MUST capture the TRUE pre-op
    image (the detached pre-dialog base) as the undo before-state — not the
    last preview frame. ONE Ctrl+Z after Apply must restore the pre-dialog
    image byte-identical and leave the geometry undo stack empty.
    """
    window = _window_with_page(qtbot, tmp_path)
    pre = window.canvas.get_image_numpy().copy()
    mask_bin, _box = _seed_mask_and_box(window)

    def _fake_exec(dlg):
        # A real user drags the controls: each change fires the live preview,
        # mutating the canvas (Pitfall 9 — no pushes). The final preview
        # leaves the canvas showing the leveled state.
        dlg.black_spin.setValue(30)
        dlg.white_spin.setValue(200)
        dlg.gamma_spin.setValue(1.0)
        dlg.result_values = (30, 200, 1.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(LevelsDialog, "exec", _fake_exec)
    window._on_levels()
    QApplication.processEvents()

    expected = levels_page(pre, 30, 200, 1.0)
    assert np.array_equal(window.canvas.get_image_numpy(), expected)
    # Geometry-free: mask + boxes untouched.
    assert np.array_equal(mask_to_numpy_binary(window.canvas.get_mask()), mask_bin)
    assert window.canvas.boxes_snapshot()[0].box.as_tuple == (30, 10, 50, 20)
    # ONE image-only entry — the mask/boxes stores are untouched.
    assert len(window.history._image_undo) == 1
    assert len(window.history._mask_undo) == 0
    assert len(window.history._boxes_undo) == 0
    assert window.image_files[0].geometry_altered is False  # A4
    assert "Levels applied." in window.status_bar_left.text()
    # Show Original shows the POST-levels image (D-14 re-baseline).
    assert np.array_equal(window.canvas._original_image_numpy, expected)

    # Restore semantics: the undo before-state is the PRE-DIALOG image (the
    # previews above mutated the canvas — without the fix, the before-state
    # equals the post-op state and Ctrl+Z is a no-op).
    window.on_undo()
    QApplication.processEvents()
    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    # The single geometry entry was consumed: the stack is empty again.
    assert not window.history.can_undo()


@pytest.mark.gui
def test_levels_preview_no_baseline_poison(qtbot, tmp_path, monkeypatch) -> None:
    """The live preview never re-baselines Show Original (Pitfall 5/9).

    The capture-suppressed preview path keeps the pre-dialog image as the
    D-14 "original"; after Cancel, Show Original still shows the pre-dialog
    image even though the canvas was mutated by previews.
    """
    window = _window_with_page(qtbot, tmp_path)
    pre = window.canvas.get_image_numpy().copy()
    window.canvas.rebaseline_original()  # honest pre-dialog baseline
    assert np.array_equal(window.canvas._original_image_numpy, pre)

    preview_seen: dict = {}

    def _fake_exec(dlg):
        dlg.black_spin.setValue(60)  # preview mutates the canvas mid-dialog
        preview_seen["mid"] = window.canvas.get_image_numpy().copy()
        dlg.gamma_spin.setValue(2.0)
        dlg.white_spin.setValue(180)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(LevelsDialog, "exec", _fake_exec)
    window._on_levels()
    QApplication.processEvents()

    # The preview ran mid-dialog (canvas mutated) but never touched the
    # baseline; Cancel restored the pre-dialog image exactly (Pitfall 5/9).
    assert not np.array_equal(preview_seen["mid"], pre)
    assert np.array_equal(window.canvas.get_image_numpy(), pre)
    assert np.array_equal(window.canvas._original_image_numpy, pre)
    window.canvas.show_original(True)
    assert np.array_equal(window.canvas.get_image_numpy(), pre)


# ===========================================================================
# Task 3 — Resize dialog contract + end-to-end apply
# ===========================================================================

@pytest.mark.gui
def test_resize_dialog_font_14px(qtbot) -> None:
    """D-12 typography: ResizeDialog's base font renders at 14px Body —
    dialog field values and labels (UI-SPEC typography table row)."""
    dlg = ResizeDialog(current_w=60, current_h=40)
    qtbot.addWidget(dlg)
    assert QFontInfo(dlg.font()).pixelSize() == 14


@pytest.mark.gui
def test_resize_dialog_contract(qtbot) -> None:
    """ResizeDialog opens at the current dims with the full number contract.

    UI-SPEC surface 26: current-dim initialization; aspect lock recomputes
    the other field (rounded, >= 1) and unlocking frees it; % mode applies
    to the current dimension with the label showing resulting px; ranges
    clamp 1..100000 px / 1..1000 percent.
    """
    dlg = ResizeDialog(current_w=60, current_h=40)
    qtbot.addWidget(dlg)

    # Opens at the current dims, aspect lock checked by default.
    assert dlg.width_spin.value() == 60
    assert dlg.height_spin.value() == 40
    assert dlg.aspect_check.isChecked()
    assert dlg.unit_combo.currentIndex() == 0  # pixels default

    # Locked: editing the dominant field recomputes the other (rounded, >=1).
    dlg.width_spin.setValue(30)
    assert dlg.height_spin.value() == 20  # round(30 * 40 / 60)
    assert "Result: 30 \u00d7 20 px" in dlg.result_label.text()

    # Unlocking frees the other field.
    dlg.aspect_check.setChecked(False)
    dlg.height_spin.setValue(40)
    assert dlg.width_spin.value() == 30  # untouched

    # % mode applies to the current dimension; the label shows resulting px.
    dlg.unit_combo.setCurrentIndex(1)  # percent (30px/60 -> 50%, 40px/40 -> 100%)
    assert dlg.width_spin.value() == 50
    assert dlg.height_spin.value() == 100
    assert "Result: 30 \u00d7 40 px" in dlg.result_label.text()
    dlg.width_spin.setValue(50)
    assert "Result: 30 \u00d7 40 px" in dlg.result_label.text()

    # Ranges clamp: 1..100000 px, 1..1000 percent.
    dlg.unit_combo.setCurrentIndex(0)  # back to pixels
    assert dlg.width_spin.maximum() == 100000
    dlg.unit_combo.setCurrentIndex(1)
    assert dlg.width_spin.maximum() == 1000
    assert dlg.width_spin.minimum() == 1


@pytest.mark.gui
def test_resize_apply_end_to_end(qtbot, tmp_path, monkeypatch) -> None:
    """Resize Apply transforms image + mask + boxes with ONE undo entry.

    LANCZOS image / NEAREST mask (binary stays strictly 0/255 — no soft
    alpha drift, D-18/A8), boxes scaled int, ONE geometry entry,
    geometry_altered True (D-22), the resized-dims flash, and the post-resize
    Show Original re-baseline (D-14).
    """
    window = _window_with_page(qtbot, tmp_path)  # 60x40 page
    pre = window.canvas.get_image_numpy().copy()
    mask_bin, _box = _seed_mask_and_box(window)

    def _fake_exec(dlg):
        dlg.result_values = (30, 20)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ResizeDialog, "exec", _fake_exec)
    window._on_resize()
    QApplication.processEvents()

    # Image resized LANCZOS to the collected dims.
    now = window.canvas.get_image_numpy()
    assert now.shape[:2] == (20, 30)
    # Mask resized NEAREST: binary values only (0/255), correct dims.
    mask_now = mask_to_numpy_binary(window.canvas.get_mask())
    assert mask_now.shape[:2] == (20, 30)
    assert set(np.unique(mask_now)).issubset({0, 255})
    # Boxes scaled int: (30,10,50,20) at 0.5x -> (15,5,25,10).
    assert window.canvas.boxes_snapshot()[0].box.as_tuple == (15, 5, 25, 10)

    # ONE geometry entry across the three stores.
    hist = window.history
    assert len(hist._image_undo) == 1
    assert hist._image_undo[-1][0] == hist._mask_undo[-1][0] == hist._boxes_undo[-1][0]
    assert window.image_files[0].geometry_altered is True
    assert "Resized to 30 \u00d7 20." in window.status_bar_left.text()
    # Show Original re-baselines to the post-resize image (D-14).
    assert np.array_equal(window.canvas._original_image_numpy, now)

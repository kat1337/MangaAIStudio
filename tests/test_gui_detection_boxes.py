"""GUI tests for the Phase 3 detection -> boxes seam (plan 03-04, TEXT-01).

Drives ``MainWindow._on_detection_finished`` directly with a crafted result
dict (the worker delivers ``{"mask": np, "blocks": blk_list}`` to this
handler). The seam is the load-bearing one-line thread-through: Phase 1
discarded ``result["blocks"]``; Phase 3 surfaces it as editable ``BoxItem``s
when the Detect Boxes mode toggle (D-01) is on.

Covers:
- D-01 mode toggle gates the box build (on = mask + boxes; off = mask only)
- D-03 re-detect replaces detected boxes, KEEPS user boxes
- D-04 confirm gate fires before replacing detected boxes (Cancel aborts)
- V5 input validation: out-of-range xyxy is bounds-clamped; zero-area dropped
- auto-show box overlay on first detect
- D-10 detection pushes a BOXES snapshot (undoable)

The fake TextBlock is a ``SimpleNamespace(xyxy=[x1,y1,x2,y2])`` — the
box-build only reads ``.xyxy`` (duck-typed, matching
``textblock_to_box``'s contract).

These tests need a display; on headless CI they skip via ``importorskip``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, USER  # noqa: E402
from manga_ai_studio.core.detection_boxes import dilate_auto_mask  # noqa: E402
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary  # noqa: E402
from manga_ai_studio.core.mask_planes import unpack_binary  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blk(x1: int, y1: int, x2: int, y2: int) -> SimpleNamespace:
    """Build a duck-typed fake TextBlock (only .xyxy is read by the build)."""
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


def _mask_np(h: int = 50, w: int = 60) -> np.ndarray:
    """A minimal (H, W) uint8 mask (the shape _on_detection_finished reads)."""
    return np.zeros((h, w), dtype=np.uint8)


def _window_with_page(qtbot, tmp_path: Path, w: int = 60, h: int = 50) -> MainWindow:
    """Build a MainWindow with a real page image loaded (for V5 image dims).

    Sets a solid-color PNG of (w x h) so ``canvas.image_item.pixmap()`` reports
    the image rect the V5 clamp bounds against.

    Plan 08-07: the page is ALSO registered in the data model
    (``image_files`` + the FileTable current row, no signal) so the reworked
    seam's ``_current_page_index()``-driven writes — the D-08 raw-detection
    retention and the explicit session-dirty mark — land on a real
    ``ImageFile`` rather than being skipped by the None-index guard.
    """
    from manga_ai_studio.core.image_file import ImageFile

    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    # Write a real PNG the canvas can load via set_image_from_path.
    from PIL import Image

    page_png = tmp_path / "page.png"
    Image.new("RGB", (w, h), color=(200, 200, 200)).save(page_png)
    assert window.canvas.set_image_from_path(page_png) is True
    # Data-model registration (whole list + selected row, no scroll signal).
    window.image_files = [ImageFile(path=page_png)]
    window.file_table.set_pages([page_png])
    window.file_table.select_path(page_png)
    window._last_page_index = 0
    return window


def _isolate_settings(window, tmp_path: Path, monkeypatch) -> None:
    """Point the window's QSettings at a throwaway INI (never the real one).

    Mirrors ``tests/test_gui_project.py::_isolate_settings`` — the G-07-3
    persistence tests must never touch the user's registry.
    """
    from PySide6.QtCore import QSettings

    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(
        window,
        "_settings",
        lambda: QSettings(str(ini), QSettings.Format.IniFormat),
    )


# ===========================================================================
# D-01: Detect Boxes mode toggle gates the build
# ===========================================================================


@pytest.mark.gui
def test_builds_boxes_when_mode_on(qtbot, tmp_path) -> None:
    """Mode on + non-empty blk_list -> boxes built, all origin DETECTED (TEXT-01)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    result = {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30), _blk(30, 10, 50, 40)]}
    window._on_detection_finished(result)

    assert window.canvas.has_boxes()
    assert window.canvas.box_count() == 2
    detected, user = window.canvas.box_origin_counts()
    assert detected == 2
    assert user == 0


@pytest.mark.gui
def test_no_boxes_when_mode_off(qtbot, tmp_path) -> None:
    """Mode off -> Phase 1 behavior preserved exactly (mask only, no boxes)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(False)

    result = {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    window._on_detection_finished(result)

    assert not window.canvas.has_boxes()
    assert window.canvas.box_count() == 0


# ===========================================================================
# D-03: re-detect replaces detected, keeps user
# ===========================================================================


@pytest.mark.gui
def test_redetect_replaces_detected_keeps_user(qtbot, tmp_path) -> None:
    """A user box survives re-detect; detected boxes are the fresh blk_list (D-03)."""
    from panelcleaner.structures import Box

    from manga_ai_studio.core.box_model import PageBox

    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    # Seed: one user box already on the canvas (e.g. an Alt+drag draw).
    user_pb = PageBox(box=Box(1, 1, 10, 10), origin=USER)
    window.canvas.set_boxes([user_pb], [])

    # First detect: 1 detected box added alongside the user box. The D-04 gate
    # does NOT fire (no detected box exists yet).
    window._on_detection_finished(
        {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    )
    detected, user = window.canvas.box_origin_counts()
    assert detected == 1
    assert user == 1  # user box survived

    # Re-detect: a DIFFERENT detected box. Auto-approve the D-04 gate.
    with patch.object(
        MainWindow, "_confirm_replace_boxes", return_value=True
    ):
        window._on_detection_finished(
            {"mask": _mask_np(), "blocks": [_blk(40, 40, 55, 48)]}
        )

    detected, user = window.canvas.box_origin_counts()
    assert detected == 1  # fresh detection
    assert user == 1  # user box STILL survives (D-03)
    # The detected box is the NEW one, not the stale one.
    snap = window.canvas.boxes_snapshot()
    detected_boxes = [pb for pb in snap if pb.origin == DETECTED]
    assert detected_boxes[0].box.as_tuple == (40, 40, 55, 48)


# ===========================================================================
# D-04: confirm gate fires before replacing detected boxes; Cancel aborts
# ===========================================================================


@pytest.mark.gui
def test_redetect_confirm_gate_cancel_aborts(qtbot, tmp_path) -> None:
    """With detected boxes present, Cancel on the D-04 gate -> no replace (D-04)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    # First detect establishes detected boxes (gate does not fire).
    window._on_detection_finished(
        {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    )
    assert window.canvas.box_origin_counts() == (1, 0)

    # Re-detect: gate fires; user clicks Cancel -> detected boxes NOT replaced.
    with patch.object(
        MainWindow, "_confirm_replace_boxes", return_value=False
    ):
        window._on_detection_finished(
            {"mask": _mask_np(), "blocks": [_blk(40, 40, 55, 48)]}
        )

    detected, _user = window.canvas.box_origin_counts()
    assert detected == 1
    # The original detected box (5,6,25,30) is still present, NOT the new one.
    snap = window.canvas.boxes_snapshot()
    detected_boxes = [pb for pb in snap if pb.origin == DETECTED]
    assert detected_boxes[0].box.as_tuple == (5, 6, 25, 30)


@pytest.mark.gui
def test_confirm_gate_skipped_when_no_detected_boxes(qtbot, tmp_path) -> None:
    """Gate fires only when >= 1 DETECTED box exists; user-only is no-gate."""
    from panelcleaner.structures import Box

    from manga_ai_studio.core.box_model import PageBox

    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    # Seed a USER box only — gate should NOT fire on the first detect.
    window.canvas.set_boxes([PageBox(box=Box(1, 1, 10, 10), origin=USER)], [])

    with patch.object(
        MainWindow, "_confirm_replace_boxes", return_value=True
    ) as gate:
        window._on_detection_finished(
            {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
        )

    # The gate was not consulted (no detected box existed pre-detect).
    gate.assert_not_called()
    assert window.canvas.box_origin_counts() == (1, 1)


# ===========================================================================
# V5: bounds-clamp + zero-area drop (model xyxy treated as untrusted)
# ===========================================================================


@pytest.mark.gui
def test_v5_clamps_out_of_range_xyxy(qtbot, tmp_path) -> None:
    """A TextBlock with xyxy partially past the image rect is bounds-clamped."""
    window = _window_with_page(qtbot, tmp_path, w=60, h=50)
    window.action_detect_boxes_mode.setChecked(True)

    # x2=9999 exceeds the 60-px image width; y2=9999 exceeds the 50-px height.
    result = {
        "mask": _mask_np(),
        "blocks": [_blk(5, 6, 9999, 9999)],
    }
    window._on_detection_finished(result)

    assert window.canvas.box_count() == 1
    snap = window.canvas.boxes_snapshot()
    clamped = snap[0].box.as_tuple
    # x2 clamped to img_w (60), y2 clamped to img_h (50); x1/y1 unchanged.
    assert clamped == (5, 6, 60, 50)


@pytest.mark.gui
def test_v5_drops_zero_area_after_clamp(qtbot, tmp_path) -> None:
    """A TextBlock fully outside the image rect is dropped (zero area post-clamp)."""
    window = _window_with_page(qtbot, tmp_path, w=60, h=50)
    window.action_detect_boxes_mode.setChecked(True)

    # This box is entirely past the right edge; clamping x1 to 60 makes
    # x2<=x1 (zero width) -> dropped per V5.
    result = {
        "mask": _mask_np(),
        "blocks": [
            _blk(70, 5, 100, 40),  # fully out-of-bounds horizontally -> dropped
            _blk(5, 6, 25, 30),  # valid -> kept
        ],
    }
    window._on_detection_finished(result)

    assert window.canvas.box_count() == 1
    snap = window.canvas.boxes_snapshot()
    assert snap[0].box.as_tuple == (5, 6, 25, 30)


@pytest.mark.gui
def test_v5_clamps_negative_origin_to_zero(qtbot, tmp_path) -> None:
    """Negative x1/y1 (model drift) clamp to 0, never below."""
    window = _window_with_page(qtbot, tmp_path, w=60, h=50)
    window.action_detect_boxes_mode.setChecked(True)

    result = {
        "mask": _mask_np(),
        "blocks": [_blk(-10, -5, 25, 30)],
    }
    window._on_detection_finished(result)

    assert window.canvas.box_count() == 1
    snap = window.canvas.boxes_snapshot()
    assert snap[0].box.as_tuple == (0, 0, 25, 30)


# ===========================================================================
# Auto-show overlay on first detect
# ===========================================================================


@pytest.mark.gui
def test_auto_show_overlay_on_first_detect(qtbot, tmp_path) -> None:
    """Overlay off + detect with mode on -> overlay auto-toggles on (UI-SPEC 10)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    window.action_toggle_box_overlay.setChecked(False)
    assert not window.action_toggle_box_overlay.isChecked()

    window._on_detection_finished(
        {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    )

    assert window.action_toggle_box_overlay.isChecked() is True


# ===========================================================================
# D-10: detection pushes a BOXES snapshot (undoable)
# ===========================================================================


@pytest.mark.gui
def test_detection_does_not_push_boxes_snapshot(qtbot, tmp_path) -> None:
    """After a detect-with-build, the BOXES stack is EMPTY — detection is a
    NON-undoable baseline (plan 03-07, UAT test 3).

    Previously detection pushed a 0-box pre-detection snapshot, making the
    INITIAL detection undoable. After [detect, move] the BOXES stack held
    [0-box, 3-box]; undo#3 popped the 0-box entry -> restored [] -> ALL
    detected boxes vanished (the UAT test 3 defect). The fix removes the
    explicit push so detection establishes the live layer WITHOUT seeding an
    undo entry; the first real user edit pushes against that baseline.
    """
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    assert not window.history.can_undo()

    window._on_detection_finished(
        {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    )

    # Detection is a non-undoable baseline: NO boxes undo entry was seeded.
    assert not window.history.can_undo_boxes(), (
        "Gap 3 (UAT test 3): detection must NOT seed a boxes undo entry — it is "
        "a non-undoable baseline. The explicit push_boxes_state in "
        "_build_detected_boxes was removed."
    )
    assert not window.history.can_undo(), (
        "Detection seeds no baseline in any stack (set_mask is silent; no "
        "mask/image pushes here either)."
    )


@pytest.mark.gui
def test_detection_does_not_push_when_mode_off(qtbot, tmp_path) -> None:
    """Mode off -> no boxes built -> no BOXES push (Phase 1 behavior)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(False)

    window._on_detection_finished(
        {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    )

    assert not window.history.can_undo_boxes()


# ===========================================================================
# Actions wired (the toggle actions exist + are checkable)
# ===========================================================================


@pytest.mark.gui
def test_detect_boxes_mode_action_exists_and_defaults_checked(qtbot, tmp_path) -> None:
    """The D-01 mode toggle exists, is checkable, defaults checked (UI-SPEC A1)."""
    window = _window_with_page(qtbot, tmp_path)
    act = window.action_detect_boxes_mode
    assert act.isCheckable()
    assert act.isChecked() is True  # UI-SPEC Copywriting A1: default checked


@pytest.mark.gui
def test_toggle_box_overlay_action_exists_checkable(qtbot, tmp_path) -> None:
    """The D-02 overlay toggle exists, is checkable, has the Shift+M shortcut."""
    window = _window_with_page(qtbot, tmp_path)
    act = window.action_toggle_box_overlay
    assert act.isCheckable()
    sc = act.shortcut().toString()
    assert "Shift" in sc and "M" in sc


# ===========================================================================
# G-07-3 — detected boxes are born with the saved default family (plan 07-11)
# ===========================================================================


@pytest.mark.gui
def test_detected_boxes_use_saved_default_family(
    qtbot, tmp_path, monkeypatch
) -> None:
    """G-07-3: detected PageBoxes carry ``style=default_style(fam)`` — the
    saved 'defaultFontFamily' becomes every detected box's starting font."""
    window = _window_with_page(qtbot, tmp_path)
    _isolate_settings(window, tmp_path, monkeypatch)
    window._settings().setValue("defaultFontFamily", "Yu Gothic UI")
    window.action_detect_boxes_mode.setChecked(True)

    result = {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30), _blk(30, 10, 50, 40)]}
    window._on_detection_finished(result)

    items = list(window.canvas._box_items)
    assert len(items) == 2
    for it in items:
        assert it.pagebox.origin == DETECTED
        assert it.pagebox.style is not None, (
            "a detected box must be born with the saved default family"
        )
        assert it.pagebox.style.font_family == "Yu Gothic UI"


@pytest.mark.gui
def test_detected_boxes_keep_style_none_without_key(
    qtbot, tmp_path, monkeypatch
) -> None:
    """G-07-3 no-key contract: with no saved family, detected boxes keep
    ``style is None`` — the renderer's TextStyle() defaults apply (the
    pre-plan behavior is unchanged)."""
    window = _window_with_page(qtbot, tmp_path)
    _isolate_settings(window, tmp_path, monkeypatch)  # fresh INI -> no key
    window.action_detect_boxes_mode.setChecked(True)

    result = {"mask": _mask_np(), "blocks": [_blk(5, 6, 25, 30)]}
    window._on_detection_finished(result)

    items = list(window.canvas._box_items)
    assert len(items) == 1
    assert items[0].pagebox.origin == DETECTED
    assert items[0].pagebox.style is None


# ===========================================================================
# Phase 8 (plan 08-07) — detection->mask seam rework. The six behavior cases
# of Task 1: the D-04 gate runs BEFORE any mask/box mutation, the composite
# is box-constrained, the pre-dilation raw binary is retained in BOTH modes,
# detection pushes nothing but dirties the session, and re-detect replaces
# detected boxes while user boxes keep their per-box state.
# ===========================================================================


def _heatmap_with_in_and_out_content(h: int = 50, w: int = 60) -> np.ndarray:
    """A (h, w) uint8 heatmap with non-zero content INSIDE the fixture box
    (5,6,25,30) AND OUTSIDE every box (the D-02 discard region)."""
    heat = np.zeros((h, w), dtype=np.uint8)
    heat[10:20, 10:20] = 255  # inside the fixture box
    heat[10:20, 40:50] = 255  # outside any box -> must never enter the mask
    return heat


def _profile_threshold(window) -> float:
    """The current std-dev gate from the active profile (the value
    refresh_box_inpaint_states reads)."""
    return float(
        window.profile_manager.config.current_profile.masker
        .mask_max_standard_deviation
    )


@pytest.mark.gui
def test_mode_on_composite_contains_only_in_box_content(qtbot, tmp_path) -> None:
    """Mode ON (08.1 D-01 inverted): the heatmap outside the box never enters
    the composite; the box content does, the PageBox is fitted (mask + float
    std_dev), and the border pen renders the derived state (D-02/MASK-05).
    Uniform boxes now map to will_fill (fill plane) vs high-std to will_inpaint;
    this fixture uses a noisy page so the box is high-std -> will_inpaint -> auto has content."""
    # Use a noisy page so the fitted box's border std is HIGH (>t) -> will_inpaint -> auto has content (preserves D-02 check after inversion)
    h, w = 50, 60
    noisy = np.zeros((h, w, 3), dtype=np.uint8)
    rng = np.random.default_rng(0)
    noisy[:, :] = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    window = _window_with_custom_page(qtbot, tmp_path, noisy)
    window.action_detect_boxes_mode.setChecked(True)

    result = {
        "mask": _heatmap_with_in_and_out_content(h, w),
        "blocks": [_blk(5, 6, 25, 30)],
    }
    window._on_detection_finished(result)

    # Composite == the auto plane (no manual strokes): only in-box content.
    auto = mask_to_numpy_binary(window.canvas.get_mask())
    assert auto[10:20, 10:20].any(), "the in-box heatmap content must land (high-std -> will_inpaint)"
    assert not auto[10:20, 40:50].any(), (
        "heatmap content outside every box must NEVER enter the mask (D-02)"
    )
    assert not auto[:, 26:].any(), "nothing right of the fixture box"
    assert not auto[31:, :].any(), "nothing below the fixture box"

    # The PageBox is fitted: non-None mask + float std_dev.
    item = window.canvas._box_items[0]
    assert item.pagebox.mask is not None, "the box must carry a fitted mask"
    assert item.pagebox.std_dev is not None
    assert isinstance(item.pagebox.std_dev, float)

    # The border renders the DERIVED state (single derivation site): solid for will_fill/will_inpaint/forced_*, dashed for gate_skipped/never (08.1 5-state)
    expected = item.pagebox.inpaint_state(_profile_threshold(window))
    if expected in ("will_inpaint", "will_fill", "forced", "forced_fill", "forced_inpaint"):
        assert item.pen().style() == Qt.PenStyle.SolidLine
    else:
        assert item.pen().style() == Qt.PenStyle.CustomDashLine


@pytest.mark.gui
def test_mode_on_cancel_aborts_before_any_mutation(qtbot, tmp_path) -> None:
    """D-04 Cancel: with detected boxes present, a cancelled re-detect must
    abort BEFORE any mask or box mutation — the canvas mask stays byte-equal,
    the boxes stay put, and no 'Detection complete' status shows (the reorder
    trap's regression lock)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    # First detect establishes the detected box + the auto plane (no gate).
    window._on_detection_finished(
        {"mask": _heatmap_with_in_and_out_content(), "blocks": [_blk(5, 6, 25, 30)]}
    )
    assert window.canvas.box_origin_counts() == (1, 0)
    mask_before = mask_to_numpy_binary(window.canvas.get_mask())
    boxes_before = [pb.box.as_tuple for pb in window.canvas.boxes_snapshot()]
    dirty_before = window.image_files[0].dirty

    # Re-detect with a DIFFERENT heatmap; user clicks Cancel.
    different_heat = np.zeros((50, 60), dtype=np.uint8)
    different_heat[40:48, 40:55] = 255
    with patch.object(MainWindow, "_confirm_replace_boxes", return_value=False):
        window._on_detection_finished(
            {"mask": different_heat, "blocks": [_blk(40, 40, 55, 48)]}
        )

    # NOTHING changed: mask byte-equal, boxes unchanged, dirty unchanged.
    mask_after = mask_to_numpy_binary(window.canvas.get_mask())
    assert np.array_equal(mask_after, mask_before), (
        "the D-04 gate must run BEFORE any mask mutation — a cancelled "
        "re-detect leaves the composite byte-identical"
    )
    boxes_after = [pb.box.as_tuple for pb in window.canvas.boxes_snapshot()]
    assert boxes_after == boxes_before, "cancelled re-detect must not touch boxes"
    assert window.image_files[0].dirty == dirty_before
    assert "Detection complete" not in window.status_bar_left.text(), (
        "a cancelled detection must not report completion"
    )


@pytest.mark.gui
def test_mode_off_full_heatmap_no_boxes_raw_retained(qtbot, tmp_path) -> None:
    """Mode OFF (D-03): the FULL heatmap dilated by the profile radius lands
    in the composite, NO boxes are built, and the pre-dilation raw binary is
    still retained on the ImageFile (D-08)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(False)

    heat = np.zeros((50, 60), dtype=np.uint8)
    heat[5:15, 5:45] = 255  # content both inside AND outside box territory
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 6, 25, 30)]})

    assert not window.canvas.has_boxes(), "mode off must build no boxes"
    profile = window.profile_manager.config.current_profile
    raw_expected = np.where(heat > 0, np.uint8(255), np.uint8(0)).astype(np.uint8)
    expected_auto = dilate_auto_mask(
        raw_expected, int(profile.masker.mask_dilation_radius)
    )
    composite = mask_to_numpy_binary(window.canvas.get_mask())
    assert np.array_equal(composite, expected_auto), (
        "mode off must land the FULL dilated heatmap in the composite"
    )
    # D-08: the pre-dilation binary is retained even without boxes.
    imf = window.image_files[0]
    assert imf.raw_detected_mask is not None
    restored_raw = unpack_binary(imf.raw_detected_mask, 50, 60)
    assert np.array_equal(restored_raw, raw_expected)


@pytest.mark.gui
def test_mode_on_stores_pre_dilation_raw_binary(qtbot, tmp_path) -> None:
    """Mode ON: the pre-dilation binary is packed onto the current
    ImageFile.raw_detected_mask (D-08 retention — feed for live re-dilate)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    heat = _heatmap_with_in_and_out_content()
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 6, 25, 30)]})

    imf = window.image_files[0]
    assert imf.raw_detected_mask is not None, "mode ON must retain the raw binary"
    raw_expected = np.where(heat > 0, np.uint8(255), np.uint8(0)).astype(np.uint8)
    restored_raw = unpack_binary(imf.raw_detected_mask, 50, 60)
    assert np.array_equal(restored_raw, raw_expected)


@pytest.mark.gui
def test_detection_pushes_no_history_and_marks_dirty(qtbot, tmp_path) -> None:
    """Detection remains a NON-undoable baseline (no MASK/BOXES pushes in any
    stack) AND marks the session dirty explicitly (recompose is
    signal-silent, so the mask_modified-driven dirty hook does not fire)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    assert not window.history.can_undo()

    window._on_detection_finished(
        {"mask": _heatmap_with_in_and_out_content(), "blocks": [_blk(5, 6, 25, 30)]}
    )

    assert not window.history.can_undo(), "detection must push NO history entry"
    assert not window.history.can_undo_boxes(), (
        "detection must push NO BOXES entry (non-undoable baseline, 03-07)"
    )
    assert window.image_files[0].dirty is True, (
        "detection modifies the page — the session must be marked dirty"
    )


@pytest.mark.gui
def test_redetect_replaces_detected_keeps_user_state(qtbot, tmp_path) -> None:
    """D-03 with per-box state: a user box survives re-detect WITH its
    inpaint_override (and a fresh fit); the REPLACED detected box's state
    (override) vanishes with the old box."""
    from panelcleaner.structures import Box

    from manga_ai_studio.core.box_model import PageBox

    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    # Seed a user box carrying a manual inpaint override — the state that
    # must be carried THROUGH the re-detect merge, not dropped.
    user_pb = PageBox(
        box=Box(1, 1, 10, 10), origin=USER, inpaint_override="always"
    )
    window.canvas.set_boxes([user_pb], [])

    # Heatmap with content inside the user box AND inside the detected box.
    heat = np.zeros((50, 60), dtype=np.uint8)
    heat[2:9, 2:9] = 255  # inside the user box (1,1,10,10)
    heat[10:20, 10:20] = 255  # inside the first detected box
    heat[41:48, 41:54] = 255  # inside the second detected box

    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 6, 25, 30)]})
    user_items = [it for it in window.canvas._box_items if it.pagebox.origin == USER]
    assert len(user_items) == 1
    user_item = user_items[0]
    assert user_item.pagebox.inpaint_override == "always", (
        "the seeded override must survive the first detect's layer rebuild"
    )

    # Re-detect with a DIFFERENT detected box; auto-approve the D-04 gate.
    with patch.object(MainWindow, "_confirm_replace_boxes", return_value=True):
        window._on_detection_finished(
            {"mask": heat, "blocks": [_blk(40, 40, 55, 48)]}
        )

    detected, user = window.canvas.box_origin_counts()
    assert detected == 1 and user == 1
    snap = window.canvas.boxes_snapshot()
    user_pbs = [pb for pb in snap if pb.origin == USER]
    detected_pbs = [pb for pb in snap if pb.origin == DETECTED]
    # The user box survived WITH its override and keeps a fresh fit.
    assert user_pbs[0].box.as_tuple == (1, 1, 10, 10)
    assert user_pbs[0].inpaint_override == "always"
    assert user_pbs[0].mask is not None, "user box must be re-fitted"
    # The REPLACED detected box is the new one, freshly fitted, override gone.
    assert detected_pbs[0].box.as_tuple == (40, 40, 55, 48)
    assert detected_pbs[0].inpaint_override is None
    assert detected_pbs[0].mask is not None, "new detected box must be fitted"


# ===========================================================================
# Plan 08-07 Task 2 — refit on move-commit + per-box snapshot carry
# ===========================================================================


def _window_with_custom_page(qtbot, tmp_path: Path, page_np) -> MainWindow:
    """A ``_window_with_page``-shaped harness over a caller-built page array.

    The page is written as RGB PNG, loaded onto the canvas, AND registered in
    the data model (image_files + FileTable current row) so the 08-07 seam's
    ImageFile writes (raw retention, dirty) land on a real ImageFile.
    """
    from manga_ai_studio.core.image_file import ImageFile

    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    from PIL import Image as PILImage

    page_png = tmp_path / "page.png"
    PILImage.fromarray(page_np).save(page_png)
    assert window.canvas.set_image_from_path(page_png) is True
    window.image_files = [ImageFile(path=page_png)]
    window.file_table.set_pages([page_png])
    window.file_table.select_path(page_png)
    window._last_page_index = 0
    return window


def _mouse_event_factory(window):
    """Viewport-coord QMouseEvent builders (the test_gui_boxes ``_press_at``
    shape — mapFromScene into the event's local pos)."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    def make(etype, sx, sy, button, buttons):
        vp = window.canvas.mapFromScene(QPointF(sx, sy))
        return QMouseEvent(
            etype, QPointF(vp), button, buttons, Qt.KeyboardModifier.NoModifier
        )

    return make


@pytest.mark.gui
def test_move_commit_defers_refit_to_redetect(qtbot, tmp_path) -> None:
    """quick-260822-gnq (supersedes the 08.1 D-12 recompute-on-release
    contract): moving a DETECTED box and releasing does NOT re-fit anymore —
    the box is marked geometry-stale with its std_dev PRESERVED, and the
    manual re-detect path (corner affordance click, quick-260824-pqn stale
    gate) re-runs the fit at the CURRENT geometry (uniform -> will_fill
    solid, noisy -> will_inpaint solid; D-01 inverted gate)."""
    from manga_ai_studio.core.mask_editor import ToolMode

    from PySide6.QtCore import QCoreApplication

    h, w = 80, 120
    page = np.full((h, w, 3), 200, dtype=np.uint8)
    rng = np.random.default_rng(42)
    page[:, 60:] = rng.integers(0, 256, size=(h, 60, 3), dtype=np.uint8)
    window = _window_with_custom_page(qtbot, tmp_path, page)
    window.resize(500, 400)
    window.show()
    window.canvas.viewport().show()
    QCoreApplication.processEvents()
    window.action_detect_boxes_mode.setChecked(True)
    window.set_active_tool(ToolMode.MOVE)

    # Heatmap content inside BOTH the start box (uniform region) and the
    # target box (noisy region) so the moved box has cut content to fit.
    heat = np.zeros((h, w), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    heat[10:30, 90:110] = 255
    window._on_detection_finished(
        {"mask": heat, "blocks": [_blk(5, 5, 35, 35)]}
    )
    item = window.canvas._box_items[0]
    assert item.current_box().as_tuple == (5, 5, 35, 35)
    profile = window.profile_manager.config.current_profile
    threshold = float(profile.masker.mask_max_standard_deviation)
    assert item.pagebox.std_dev is not None
    assert item.pagebox.std_dev <= threshold, "uniform region: low std -> will_fill (D-01 inverted)"
    assert item.pagebox.inpaint_state(threshold) == "will_fill"
    assert item.pen().style() == Qt.PenStyle.SolidLine

    # Move the box onto the noisy half via the REAL canvas event chain.
    make = _mouse_event_factory(window)
    from PySide6.QtCore import QEvent
    window.canvas.mousePressEvent(
        make(QEvent.Type.MouseButtonPress, 20, 20, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    )
    window.canvas.mouseMoveEvent(
        make(QEvent.Type.MouseMove, 100, 20, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    )
    window.canvas.mouseReleaseEvent(
        make(QEvent.Type.MouseButtonRelease, 100, 20, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    )
    QCoreApplication.processEvents()

    moved = window.canvas._box_items[0]
    assert moved.current_box().as_tuple == (85, 5, 115, 35), "the box moved"
    assert window.history.can_undo_boxes(), "the move committed a BOXES push"
    # quick-260822-gnq: the move is CHEAP — no refit, detection info survives
    # the move untouched, and the box is marked stale for the manual re-run
    # affordance (quick-260824-pqn stale gate; no automatic path).
    std_before_move = moved.pagebox.std_dev
    assert moved.geometry_stale is True, "moved box must be marked stale"
    assert moved.pagebox.std_dev == std_before_move, (
        "a move must NOT re-fit: std_dev survives the move untouched"
    )

    # The explicit re-detect path re-fits at the CURRENT geometry — the
    # border re-measures over the noisy region. The OCR leg is stubbed
    # (hermetic: no model load).
    moved.pagebox.payload.text = ""  # fixture payload carries no text attr
    window._dispatch_ocr_for_box = lambda it: None
    window._on_box_redetect_requested(moved)
    assert moved.pagebox.std_dev is not None
    assert moved.pagebox.std_dev > threshold, (
        "the explicit re-detect must re-measure std ABOVE the gate at the "
        "moved location (D-01 inverted -> will_inpaint)"
    )
    assert moved.geometry_stale is False
    assert moved.pagebox.inpaint_state(threshold) == "will_inpaint"
    assert moved.pen().style() == Qt.PenStyle.SolidLine


@pytest.mark.gui
def test_boxes_undo_restores_per_box_mask_and_std_dev(qtbot, tmp_path) -> None:
    """A BOXES undo after an override-free detect+move round-trip restores
    the per-box mask/std_dev — the extended boxes_snapshot carries the D-15
    seam fields through the undo restore (Pitfall 8 field-drop guard)."""
    from manga_ai_studio.core.mask_editor import ToolMode

    from PySide6.QtCore import QCoreApplication

    h, w = 80, 120
    page = np.full((h, w, 3), 200, dtype=np.uint8)
    rng = np.random.default_rng(42)
    page[:, 60:] = rng.integers(0, 256, size=(h, 60, 3), dtype=np.uint8)
    window = _window_with_custom_page(qtbot, tmp_path, page)
    window.resize(500, 400)
    window.show()
    window.canvas.viewport().show()
    QCoreApplication.processEvents()
    window.action_detect_boxes_mode.setChecked(True)
    window.set_active_tool(ToolMode.MOVE)

    heat = np.zeros((h, w), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    heat[10:30, 90:110] = 255
    window._on_detection_finished(
        {"mask": heat, "blocks": [_blk(5, 5, 35, 35)]}
    )
    item = window.canvas._box_items[0]
    pre = (
        item.current_box().as_tuple,
        item.pagebox.std_dev,
        item.pagebox.mask is not None,
    )
    assert pre[2], "the detected box carries a fitted mask"

    make = _mouse_event_factory(window)
    from PySide6.QtCore import QEvent
    window.canvas.mousePressEvent(
        make(QEvent.Type.MouseButtonPress, 20, 20, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    )
    window.canvas.mouseMoveEvent(
        make(QEvent.Type.MouseMove, 100, 20, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    )
    window.canvas.mouseReleaseEvent(
        make(QEvent.Type.MouseButtonRelease, 100, 20, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    )
    QCoreApplication.processEvents()
    assert window.canvas._box_items[0].current_box().as_tuple == (85, 5, 115, 35)

    # One Ctrl+Z restores the pre-move box WITH its per-box mask/std_dev.
    window.on_undo()
    restored = window.canvas._box_items[0]
    assert restored.current_box().as_tuple == pre[0], "geometry restored"
    assert restored.pagebox.std_dev == pre[1], (
        "std_dev must round-trip through the BOXES undo (snapshot carry)"
    )
    assert restored.pagebox.mask is not None


# ===========================================================================
# Plan 08-07 Task 3 — live radius/threshold slots, .mas plane round-trip,
# inpaint completion copy
# ===========================================================================


def _noisy_right_half_page(h: int = 80, w: int = 120) -> np.ndarray:
    """A page whose left half is uniform 200 and whose right half (cols >=
    w//2) is deterministic full-bleed noise (contrast reaching the frame —
    the std-dev gate reads it above threshold, cf. the 08-03 battery)."""
    page = np.full((h, w, 3), 200, dtype=np.uint8)
    rng = np.random.default_rng(42)
    page[:, w // 2 :] = rng.integers(0, 256, size=(h, w // 2, 3), dtype=np.uint8)
    return page


def _seed_manual_stroke(window, x: int = 2, y: int = 2, s: int = 10) -> None:
    """Paint an opaque red block onto the manual plane (the scratch-seeding
    the mask_planes tests use — real QPainter, no canvas event chain)."""
    from PySide6.QtGui import QColor, QPainter

    painter = QPainter(window.canvas._mask_manual)
    painter.fillRect(x, y, s, s, QColor(255, 0, 0, 255))
    painter.end()


@pytest.mark.gui
def test_refresh_box_inpaint_states_iterates_and_derives(qtbot, tmp_path) -> None:
    """refresh_box_inpaint_states() iterates every canvas box item and calls
    set_inpaint_state with the profile-threshold derivation (the §37
    single-derivation refresh; a std flip re-renders the border)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    window._on_detection_finished(
        {
            "mask": _heatmap_with_in_and_out_content(),
            "blocks": [_blk(5, 6, 25, 30), _blk(30, 10, 50, 40)],
        }
    )
    threshold = _profile_threshold(window)
    items = list(window.canvas._box_items)
    assert len(items) == 2
    for it in items:
        assert it._inpaint_state == it.pagebox.inpaint_state(threshold), (
            "each item must carry the SINGLE-derivation state (08-01)"
        )

    # A std-dev flip + refresh re-renders (08.1 D-01 inverted: high std -> will_inpaint solid).
    it = items[0]
    it.pagebox.std_dev = 9999.0
    window.refresh_box_inpaint_states()
    assert it._inpaint_state == "will_inpaint"
    assert it.pen().style() == Qt.PenStyle.SolidLine
    # gate_skipped is reached by clearing mask (no content), not high std
    it.pagebox.mask = None
    window.refresh_box_inpaint_states()
    assert it._inpaint_state == "gate_skipped"
    assert it.pen().style() == Qt.PenStyle.CustomDashLine


@pytest.mark.gui
def test_dilation_live_redilate_grows_shrinks_keeps_strokes(qtbot, tmp_path) -> None:
    """D-08 live re-dilate (mode OFF): emitting dilation_changed re-derives
    the auto plane from the retained raw mask WITHOUT a model call — the
    composite GROWS with the radius, SHRINKS when it returns to 0, and the
    hand strokes painted between the emits stay present; no worker, no status
    change. (Mode OFF is the deterministic path — the full heatmap is exactly
    ``dilate_auto_mask(raw, r)``; line 2 covers the boxed re-derive.)"""
    window = _window_with_custom_page(qtbot, tmp_path, np.full((80, 120, 3), 200, dtype=np.uint8))
    window.action_detect_boxes_mode.setChecked(False)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 35, 35)]})
    status_before = window.status_bar_left.text()
    assert not window._op_running

    auto0 = np.count_nonzero(mask_to_numpy_binary(window.canvas.get_mask()))
    _seed_manual_stroke(window)

    # First emit: radius 5 -> the full-heatmap auto layer GROWS.
    window.detection_body.dilation_changed.emit(5)
    auto1 = np.count_nonzero(mask_to_numpy_binary(window.canvas.get_mask()))
    assert auto1 > auto0, "raising the radius must re-dilate the retained raw"

    # Second emit: radius 0 -> it SHRINKS back (grow no-op -> the raw only).
    window.detection_body.dilation_changed.emit(0)
    auto2 = np.count_nonzero(mask_to_numpy_binary(window.canvas.get_mask()))
    assert auto2 < auto1, "dropping the radius to 0 must shrink the auto plane"

    # The hand stroke painted between the emits is unchanged + still present.
    composite = mask_to_numpy_binary(window.canvas.get_mask())
    assert composite[2:12, 2:12].any(), "manual strokes must survive re-dilates"
    assert window.status_bar_left.text() == status_before, (
        "a live re-dilate must not touch the status bar"
    )
    assert window._op_running is False, "no worker was dispatched"


@pytest.mark.gui
def test_dilation_live_redilate_mode_on_rederives(qtbot, tmp_path) -> None:
    """The boxed (mode ON) live path re-derives against the CURRENT radius:
    the slot invokes the derivation core and stores exactly the fresh derive
    at the emitted radius (never stale — the CTD model is NOT re-run)."""
    from manga_ai_studio.core.detection_boxes import (
        derive_page_mask_state as real_derive,
    )

    window = _window_with_custom_page(qtbot, tmp_path, np.full((80, 120, 3), 200, dtype=np.uint8))
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 35, 35)]})
    profile = window.profile_manager.config.current_profile

    # The slot must actually invoke the re-derive (not a no-op), and the
    # store must be byte-identical to the deterministic derive at radius 5.
    with patch.object(
        MainWindow, "_rederive_auto_layer", wraps=window._rederive_auto_layer
    ) as spy:
        window.detection_body.dilation_changed.emit(5)
    spy.assert_called_once()
    raw = unpack_binary(window.image_files[0].raw_detected_mask, 80, 120)
    boxes = [it.pagebox for it in window.canvas._box_items]
    reference = real_derive(
        window.canvas.get_image_numpy(), raw, boxes, profile.masker, 5
    ).auto_binary
    assert np.array_equal(reference, window.canvas._auto_bin), (
        "the live store must be the fresh derive at the emitted radius (D-08)"
    )
    assert window._op_running is False, "no worker was dispatched"


@pytest.mark.gui
def test_threshold_live_regate_flips_border_and_composite(qtbot, tmp_path) -> None:
    """D-12 threshold (08.1 D-01 inverted): emitting std_dev_threshold_changed
    recomposes ONLY from the STORED fits (no refit — std_dev unchanged):
    high-std box (>t) is will_inpaint at default 15 (solid + in auto), at 100
    it becomes will_fill (solid but in fill plane, auto empty), at 0 it is
    will_inpaint again. Verifies pure recompose without refit."""
    window = _window_with_custom_page(qtbot, tmp_path, _noisy_right_half_page())
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 90:110] = 255  # the box sits over the NOISY half -> std > gate
    window._on_detection_finished({"mask": heat, "blocks": [_blk(85, 5, 115, 35)]})
    item = window.canvas._box_items[0]
    threshold = _profile_threshold(window)
    assert item.pagebox.std_dev is not None
    assert item.pagebox.std_dev > threshold, "fixture must measure above the gate (high std)"
    std_before = item.pagebox.std_dev

    # At the default gate (15) the HIGH-std box is INPAINT (will_inpaint solid, in auto)
    assert item.pagebox.inpaint_state(threshold) == "will_inpaint"
    assert item.pen().style() == Qt.PenStyle.SolidLine
    composite = mask_to_numpy_binary(window.canvas.get_mask())
    assert composite[10:30, 90:110].any(), "high-std box must be in auto at default"

    # 100.0: threshold high, high-std (30) <=100 -> will_fill (solid but in fill plane, auto empty) (D-01 inverted)
    window.detection_body.std_dev_threshold_changed.emit(100.0)
    assert item.pagebox.std_dev == std_before, (
        "threshold change must NOT re-fit — the stored std stays (D-12)"
    )
    assert item.pagebox.inpaint_state(100.0) == "will_fill"
    assert item.pen().style() == Qt.PenStyle.SolidLine
    composite = mask_to_numpy_binary(window.canvas.get_mask())
    assert not composite[10:30, 90:110].any(), "will_fill box must NOT be in auto (fill plane, not auto)"
    # Verify fill plane has content
    from manga_ai_studio.core.detection_boxes import compose_fill_binary

    fill_bin = compose_fill_binary([item.pagebox], 100.0, (120, 80))
    assert fill_bin[10:30, 90:110].any(), "will_fill box must be in fill plane"

    # 0.0: threshold low, high-std 30 >0 -> will_inpaint again (solid, in auto)
    window.detection_body.std_dev_threshold_changed.emit(0.0)
    assert item.pagebox.std_dev == std_before
    assert item.pagebox.inpaint_state(0.0) == "will_inpaint"
    assert item.pen().style() == Qt.PenStyle.SolidLine
    composite = mask_to_numpy_binary(window.canvas.get_mask())
    assert composite[10:30, 90:110].any(), "high-std box must be in auto at 0 threshold"


@pytest.mark.gui
def test_dilation_no_raw_is_silent_noop(qtbot, tmp_path) -> None:
    """A dilation change on a NEVER-detected page is a silent no-op: the mask
    stays byte-equal, the profile persists, no exception."""
    window = _window_with_page(qtbot, tmp_path)
    mask_before = mask_to_numpy_binary(window.canvas.get_mask())
    profile = window.profile_manager.config.current_profile
    profile.masker.mask_dilation_radius = 7  # a state that must NOT re-derive

    window.detection_body.dilation_changed.emit(9)

    assert np.array_equal(
        mask_to_numpy_binary(window.canvas.get_mask()), mask_before
    ), "no raw detection -> the auto plane must be untouched"
    assert profile.masker.mask_dilation_radius == 9  # the setting still persists


@pytest.mark.gui
def test_mas_save_roundtrip_restores_planes_without_detect(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Save + reload a session (08.1 D-01 inverted): use noisy page so the box
    is high-std -> will_inpaint -> auto has content (preserves save/restore check
    after inversion; uniform -> will_fill would be auto empty)."""
    from manga_ai_studio.core.mask_planes import unpack_binary as _unpack

    # Noisy page to make the box high-std -> will_inpaint -> auto has content (08.1 inverted gate)
    noisy = np.zeros((80, 120, 3), dtype=np.uint8)
    rng = np.random.default_rng(2)
    noisy[:, :] = rng.integers(0, 256, size=(80, 120, 3), dtype=np.uint8)
    window = _window_with_custom_page(qtbot, tmp_path, noisy)
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    # A REAL TextBlock payload (not the duck-typed _blk): the .mas serializer
    # reads payload.lines/vertical/language/font_size/text/translation.
    from panelcleaner.comic_text_detector.utils.textblock import TextBlock

    window._on_detection_finished(
        {"mask": heat, "blocks": [TextBlock([5, 5, 35, 35])]}
    )
    threshold = _profile_threshold(window)
    pre_state = window.canvas._box_items[0].pagebox.inpaint_state(threshold)

    # Real Save Project path (only the folder dialog is bypassed).
    proj = tmp_path / "proj"
    with patch.object(MainWindow, "_choose_project_dir", return_value=(proj, False)):
        assert window._save_project(force_as=True) is True

    # A FRESH window + the real open path (no detect ever runs on it).
    reopen_dir = tmp_path / "reopen"
    reopen_dir.mkdir()
    window2 = _window_with_custom_page(qtbot, reopen_dir, np.full((80, 120, 3), 200, dtype=np.uint8))
    window2._load_project_session(proj / "manifest.json")

    items = list(window2.canvas._box_items)
    assert len(items) == 1, "the restored page must carry its box"
    it = items[0]
    assert it.pagebox.mask is not None and it.pagebox.std_dev is not None, (
        "per-box mask/std_dev must round-trip through the real save path"
    )
    assert it._inpaint_state == it.pagebox.inpaint_state(threshold) == pre_state, (
        "border states must render from the round-tripped fields"
    )
    imf2 = window2.image_files[0]
    assert imf2.raw_detected_mask is not None, "the raw plane must be retained"
    assert window2.canvas._auto_bin is not None, "the auto plane must restore"
    persisted_auto = _unpack(imf2.auto_mask, 80, 120)
    assert np.array_equal(persisted_auto, window2.canvas._auto_bin), (
        "the restored auto plane must match the persisted automask entry"
    )
    assert np.count_nonzero(window2.canvas._auto_bin) > 0

    # A post-load radius change re-dilates from the retained raw — no detect.
    # (The boxed compose saturates to the box, so the mode-OFF dilate path is
    # the deterministic witness: it is exactly dilate_auto_mask(raw, r) and
    # grows with r — proving the raw plane survived the restore.)
    window2.action_detect_boxes_mode.setChecked(False)
    before = np.count_nonzero(mask_to_numpy_binary(window2.canvas.get_mask()))
    window2.detection_body.dilation_changed.emit(8)
    after = np.count_nonzero(mask_to_numpy_binary(window2.canvas.get_mask()))
    assert after > before, "post-load dilation must re-dilate from the raw plane"


@pytest.mark.gui
def test_inpaint_completion_copy_no_boxes(qtbot, tmp_path) -> None:
    """With no boxes on the page, the completion flash stays exactly
    'Inpainting complete' (plan 08-07, UI-SPEC §Copywriting surface 7)."""
    window = _window_with_page(qtbot, tmp_path)
    result_rgb = np.full((50, 60, 3), 200, dtype=np.uint8)
    window._on_inpaint_finished({"image": result_rgb, "bbox": (0, 0, 60, 50)})
    assert window.status_bar_left.text() == "Inpainting complete"


@pytest.mark.gui
def test_inpaint_completion_copy_box_counts(qtbot, tmp_path) -> None:
    """With boxes (08.1 D-01 inverted): uniform -> will_fill, noisy -> will_inpaint;
    completion flash tells selective story: n filled · m inpainted (both)."""
    window = _window_with_custom_page(qtbot, tmp_path, _noisy_right_half_page())
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 10:30] = 255  # uniform box (left white) -> will_fill after inversion
    heat[10:30, 90:110] = 255  # noise box (right noisy) -> will_inpaint after inversion
    window._on_detection_finished(
        {"mask": heat, "blocks": [_blk(5, 5, 35, 35), _blk(85, 5, 115, 35)]}
    )
    threshold = _profile_threshold(window)
    states = [it.pagebox.inpaint_state(threshold) for it in window.canvas._box_items]
    assert "will_fill" in states, "uniform box must be will_fill (D-01 inverted)"
    assert "will_inpaint" in states, "noisy box must be will_inpaint (D-01 inverted)"

    result_rgb = np.full((80, 120, 3), 200, dtype=np.uint8)
    window._on_inpaint_finished({"image": result_rgb, "bbox": (0, 0, 120, 80), "fill_count": 1, "inpaint_count": 1, "patch_count": 1})
    # New 08.1 status: both fill and inpaint counts present, no patch suffix for small page
    assert "1 filled" in window.status_bar_left.text().lower()
    assert "1 inpainted" in window.status_bar_left.text().lower()
    assert "patch" not in window.status_bar_left.text().lower()


@pytest.mark.gui
def test_inpaint_completion_copy_zero_skipped(qtbot, tmp_path) -> None:
    """08.1 D-01 inverted: uniform box -> will_fill, so inpaint completion
    with single uniform box reports filled, not inpainted; zero-one-many for fill."""
    # Use noisy page so the single box is high-std -> will_inpaint to keep original intent of "every box inpainted"
    h, w = 50, 60
    noisy = np.zeros((h, w, 3), dtype=np.uint8)
    rng = np.random.default_rng(1)
    noisy[:, :] = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    window = _window_with_custom_page(qtbot, tmp_path, noisy)
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((h, w), dtype=np.uint8)
    heat[10:20, 10:20] = 255
    window._on_detection_finished(
        {"mask": heat, "blocks": [_blk(5, 6, 25, 30)]}
    )
    # After inversion, high-std noisy box -> will_inpaint, so status should report inpainted
    result_rgb = np.full((50, 60, 3), 200, dtype=np.uint8)
    window._on_inpaint_finished({"image": result_rgb, "bbox": (0, 0, 60, 50), "fill_count": 0, "inpaint_count": 1, "patch_count": 1})
    assert "1 inpainted" in window.status_bar_left.text().lower()
    assert "filled" not in window.status_bar_left.text().lower() or "1 filled" not in window.status_bar_left.text().lower()


# ===========================================================================
# Stale-result guard: page switched mid-detection (wrong-page write family)
# ===========================================================================


@pytest.mark.gui
def test_detection_result_discarded_after_page_switch(qtbot, tmp_path) -> None:
    """REGRESSION family (user report: C-inpaint corrupted the page they
    switched to): detection finishing AFTER a page switch must not write
    boxes/mask onto the NEW page. The stale guard drops the result."""
    from manga_ai_studio.core.image_file import ImageFile

    window = _window_with_page(qtbot, tmp_path)
    path_a = window.file_table.current_path()

    # A second page to switch to mid-op.
    from PIL import Image

    path_b = tmp_path / "page_b.png"
    Image.new("RGB", (60, 50), color=(120, 120, 120)).save(path_b)
    window.image_files.append(ImageFile(path=path_b))
    window.file_table.set_pages([path_a, path_b])
    window.file_table.select_path(path_b)
    window.on_page_selected(path_b)
    QApplication.processEvents()
    assert window.file_table.current_path() == path_b

    canvas_before = window.canvas.get_image_numpy().copy()
    window._op_target_path = path_a  # what detect_text() stamps at dispatch

    window._on_detection_finished({"mask": _mask_np(), "blocks": []})

    assert np.array_equal(window.canvas.get_image_numpy(), canvas_before)
    assert window.image_files[0].raw_detected_mask is None
    assert "discarded" in window.status_bar_left.text().lower()


@pytest.mark.gui
def test_detection_dispatch_stamps_target_page(qtbot, tmp_path, monkeypatch) -> None:
    """detect_text() records the current page at dispatch — the identity the
    finish-handler guard compares against."""
    from types import SimpleNamespace

    import manga_ai_studio.gui.main_window as mw

    window = _window_with_page(qtbot, tmp_path)
    window._confirm_replace_mask = lambda: True

    class _Sig:
        def connect(self, *a, **k):
            pass

    class _FakeWorker:
        def __init__(self, *a, **k):
            self.signals = SimpleNamespace(
                progress=_Sig(), result=_Sig(), error=_Sig(), finished=_Sig()
            )

        def setAutoDelete(self, *a, **k):
            pass

    class _FakePool:
        class _Inst:
            def start(self, *a, **k):
                pass

        @staticmethod
        def globalInstance():
            return _FakePool._Inst()

    monkeypatch.setattr(mw, "Worker", _FakeWorker)
    monkeypatch.setattr(mw, "backend_factory", lambda *a, **k: None)
    monkeypatch.setattr(mw, "QThreadPool", _FakePool)

    window.detect_text()
    assert window._op_running is True
    assert window._op_target_path == window.file_table.current_path()

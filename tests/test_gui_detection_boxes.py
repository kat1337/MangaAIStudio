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
    """
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    # Write a real PNG the canvas can load via set_image_from_path.
    from PIL import Image

    page_png = tmp_path / "page.png"
    Image.new("RGB", (w, h), color=(200, 200, 200)).save(page_png)
    assert window.canvas.set_image_from_path(page_png) is True
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
    """Mode ON: the heatmap outside the box never enters the composite; the
    box content does, the PageBox is fitted (mask + float std_dev), and the
    border pen renders the derived state (D-02/MASK-05)."""
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)

    result = {
        "mask": _heatmap_with_in_and_out_content(),
        "blocks": [_blk(5, 6, 25, 30)],
    }
    window._on_detection_finished(result)

    # Composite == the auto plane (no manual strokes): only in-box content.
    auto = mask_to_numpy_binary(window.canvas.get_mask())
    assert auto[10:20, 10:20].any(), "the in-box heatmap content must land"
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

    # The border renders the DERIVED state (single derivation site): the pen
    # style is solid iff the state says will-inpaint / forced.
    expected = item.pagebox.inpaint_state(_profile_threshold(window))
    if expected in ("will_inpaint", "forced"):
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

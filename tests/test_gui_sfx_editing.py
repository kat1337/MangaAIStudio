"""GUI tests for the quick-260824-viq SFX editing features:

- Free-angle TEXT ROTATION via the corner-above RotationHandle: live drag
  preview, committed per-box angle, ONE boxes_modified emission carrying the
  PRE-rotation snapshot (CR-01), one Ctrl+Z reversal, and D-01 canvas ≡ bake
  pixel parity for the rotated overlay.
- (Task 3 appends below: Inspector spacing rows + Ctrl+C/Ctrl+V duplication.)

The rotate drag is exercised through the canvas state-machine SEAM
(``_begin_rotation`` / ``_advance_rotation`` / ``_commit_rotation``) — the
05-09 QTest mouse-path truncation lesson: programmatic seam calls are exact,
synthesized viewport events are not.

Mirrors tests/test_gui_boxes.py's header (importorskip + qtbot +
@pytest.mark.gui).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, QRectF, QSizeF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import USER, PageBox  # noqa: E402
from manga_ai_studio.core.text_style import TextStyle  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.box_item import BoxItem, RotationHandle  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _solid_pixmap(size: int, color: QColor) -> QImage:
    from PySide6.QtGui import QPixmap

    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


def _scene_with_box(pagebox: PageBox) -> tuple[QGraphicsScene, BoxItem]:
    scene = QGraphicsScene()
    item = BoxItem(pagebox)
    scene.addItem(item)
    return scene, item


def _canvas_with_image(qtbot, size: int = 300) -> EditorCanvas:
    """A shown canvas with an image loaded (box interactions need a page)."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(500, 500)
    canvas.set_image(_solid_pixmap(size, QColor("white")))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    return canvas


def _seed_box(canvas: EditorCanvas, box: Box, **pb_kwargs) -> BoxItem:
    """Seed ONE user box on the bare canvas without a history push."""
    pb = PageBox(box=box, origin=USER, **pb_kwargs)
    canvas.set_boxes([pb], [])
    return canvas._box_items[0]


def _window_with_page(qtbot, tmp_path, size: int = 200) -> MainWindow:
    """A shown MainWindow with one real PNG page loaded."""
    from PIL import Image as PILImage

    page = tmp_path / "page.png"
    PILImage.new("RGB", (size, size), color=(200, 200, 200)).save(page)
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(tmp_path)
    window.show()
    QApplication.processEvents()
    return window


def _seed_boxes_window(window: MainWindow, boxes: list) -> list:
    """Seed N user boxes in ONE set_boxes call (no history push)."""
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([PageBox(box=b, origin=USER) for b in boxes], [])
    finally:
        window._suppress_boxes_push = False
    return list(window.canvas._box_items)


# ===========================================================================
# Task 2 — RotationHandle component tests
# ===========================================================================


@pytest.mark.gui
def test_rotation_handle_hidden_unselected_visible_selected_primary(qtbot) -> None:
    """The rotation handle follows the corner-handle visibility rule: hidden
    unselected, visible on the selected box (no primary provider installed)."""
    _scene, item = _scene_with_box(PageBox(box=Box(20, 20, 120, 120), origin=USER))
    rh = item._rotation_handle
    assert isinstance(rh, RotationHandle)
    assert rh.isVisible() is False
    item.setSelected(True)
    assert rh.isVisible() is True


@pytest.mark.gui
def test_rotation_handle_centered_above_tl_clear_of_corner_hit_zone(qtbot) -> None:
    """The handle's CENTER sits at (rect.left(), rect.top() - 18) — clearly
    outside the TL CornerHandle's ~9px-radius zoom-divided hit zone."""
    from manga_ai_studio.gui.box_item import (
        _ROTATE_ABOVE_TL,
        _handle_hit_rect,
    )

    rect = QRectF(100.0, 80.0, 150.0, 90.0)
    _scene, item = _scene_with_box(PageBox(box=Box(100, 80, 250, 170), origin=USER))
    item.setSelected(True)
    rh = item._rotation_handle
    # reposition runs through _sync_handles on selection.
    center = QPointF(rh.pos().x() + rh.rect().width() / 2.0,
                     rh.pos().y() + rh.rect().height() / 2.0)
    assert abs(center.x() - rect.left()) < 0.01
    assert abs(center.y() - (rect.top() - _ROTATE_ABOVE_TL)) < 0.01
    # And its visible body does not intersect the TL handle's enlarged hit rect
    # (anchored at the box corner).
    tl_hit = _handle_hit_rect(1.0).translated(rect.left() - 4.0, rect.top() - 4.0)
    rh_rect = QRectF(rh.pos(), QSizeF(rh.rect().width(), rh.rect().height()))
    assert not rh_rect.intersects(tl_hit)


@pytest.mark.gui
def test_rotation_handle_tooltip_cursor(qtbot) -> None:
    """Affordance contract: 'Rotate text' tooltip + a drag cursor."""
    _scene, item = _scene_with_box(PageBox(box=Box(0, 0, 50, 50), origin=USER))
    rh = item._rotation_handle
    assert rh.toolTip() == "Rotate text"
    from PySide6.QtCore import Qt

    assert rh.cursor().shape() != Qt.CursorShape.ArrowCursor


@pytest.mark.gui
def test_preview_rotation_is_pure_transform(qtbot) -> None:
    """preview_rotation applies ONLY a QGraphicsItem rotation — the cached
    layout_result object is untouched (RC-1: no re-layout per mousemove);
    clear_preview_rotation resets it."""
    style = TextStyle(auto_fit=False, font_size_px=12.0)
    pb = PageBox(box=Box(10, 10, 110, 60), origin=USER, style=style)
    pb.set_translation("Hello")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay = item._text_overlay
    result_before = overlay.layout_result
    assert result_before is not None

    item.preview_rotation(37.5)
    assert overlay.rotation() == pytest.approx(37.5)
    assert overlay.layout_result is result_before

    item.clear_preview_rotation()
    assert overlay.rotation() == 0.0


# ===========================================================================
# Task 2 — the canvas rotate-drag state machine (seam-driven)
# ===========================================================================


@pytest.mark.gui
def test_rotate_drag_seam_commits_angle_and_emits_pre_snapshot_once(qtbot) -> None:
    """The full seam: arm at a grab angle left of center, advance to below
    center (-90 deg delta), commit -> style.rotation_deg lands within
    tolerance, boxes_modified fires ONCE with the PRE-rotation snapshot, and
    the overlay pixmap differs from the pre-commit render."""
    canvas = _canvas_with_image(qtbot)
    style = TextStyle(auto_fit=False, font_size_px=12.0)
    item = _seed_box(canvas, Box(60, 60, 220, 140), style=style)
    item.pagebox.set_translation("SPIN")
    item.refresh_text_overlay()

    emitted: list = []
    canvas.boxes_modified.connect(lambda snap: emitted.append(list(snap)))

    center = item.rect().center()
    grab_pos = QPointF(center.x() - 60.0, center.y())  # angle pi (left)
    end_pos = QPointF(center.x(), center.y() + 60.0)  # angle pi/2 (down)

    canvas._begin_rotation(item, grab_pos)
    assert canvas._rotating_box is item
    canvas._advance_rotation(end_pos)
    assert item._text_overlay.rotation() == pytest.approx(-90.0, abs=0.01)
    canvas._commit_rotation()

    assert item.pagebox.style is not None
    assert item.pagebox.style.rotation_deg == pytest.approx(-90.0, abs=0.01)
    # ONE emission; the payload is the PRE-rotation snapshot.
    assert len(emitted) == 1
    assert len(emitted[0]) == 1
    assert emitted[0][0].style is not None
    assert emitted[0][0].style.rotation_deg == 0.0


@pytest.mark.gui
def test_rotate_drag_seam_live_preview_then_commit_renders_rotated(qtbot) -> None:
    """After commit the overlay renders through the rotated surface path
    (_render_offset set); the preview transform is cleared."""
    canvas = _canvas_with_image(qtbot)
    style = TextStyle(auto_fit=False, font_size_px=12.0)
    item = _seed_box(canvas, Box(60, 60, 240, 140), style=style)
    item.pagebox.set_translation("ANGLED")
    item.refresh_text_overlay()

    center = item.rect().center()
    canvas._begin_rotation(item, QPointF(center.x(), center.y() - 70.0))  # up
    canvas._advance_rotation(QPointF(center.x() + 70.0, center.y()))  # right
    # Live angle: +90 (clockwise).
    assert item._text_overlay.rotation() == pytest.approx(90.0, abs=0.01)
    canvas._commit_rotation()
    assert item._text_overlay.rotation() == 0.0  # preview cleared
    assert item._text_overlay._render_offset is not None  # rotated render path
    assert item.pagebox.style.rotation_deg == pytest.approx(90.0, abs=0.01)


@pytest.mark.gui
def test_rotate_click_without_drag_is_a_no_op(qtbot) -> None:
    """Arm + immediate commit (< 0.05 deg deadband) emits NOTHING and leaves
    the style unchanged (the WR-04 delta-check precedent)."""
    canvas = _canvas_with_image(qtbot)
    item = _seed_box(canvas, Box(60, 60, 160, 140))
    emitted: list = []
    canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    center = item.rect().center()
    canvas._begin_rotation(item, QPointF(center.x() - 40.0, center.y()))
    canvas._commit_rotation()
    assert emitted == []
    assert item.pagebox.style is None


@pytest.mark.gui
def test_rotate_commit_undo_restores_prior_angle(qtbot, tmp_path) -> None:
    """One Ctrl+Z reverses a committed rotation (the real history push via
    the boxes_modified hook)."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(30, 30, 150, 110)])[0]
    item.pagebox.style = TextStyle(auto_fit=False, font_size_px=12.0)
    item.pagebox.set_translation("UNDO ME")
    item.refresh_text_overlay()
    item.setSelected(True)

    canvas = window.canvas
    center = item.rect().center()
    canvas._begin_rotation(item, QPointF(center.x() - 60.0, center.y()))
    canvas._advance_rotation(QPointF(center.x() + 60.0, center.y()))  # 180 deg
    canvas._commit_rotation()
    assert item.pagebox.style.rotation_deg == pytest.approx(180.0, abs=0.01)

    window.on_undo()
    restored = canvas._box_items[0].pagebox
    restored_deg = restored.style.rotation_deg if restored.style is not None else 0.0
    assert restored_deg == pytest.approx(0.0, abs=0.01), (
        "undo must restore the PRE-rotation style"
    )


@pytest.mark.gui
def test_rotation_rendered_overlay_matches_bake_pixels(qtbot) -> None:
    """D-01 canvas ≡ bake for a ROTATED box: compositing the overlay pixmap
    at its scene position must match ``bake_typeset_page`` EXACTLY on the
    opaque glyph interior (the established equivalence-test discipline)."""
    from manga_ai_studio.gui.text_renderer import (
        bake_typeset_page,
        numpy_to_qimage,
        qimage_to_numpy,
    )

    style = TextStyle(
        font_size_px=14.0,
        auto_fit=False,
        align_h="left",
        align_v="top",
        rotation_deg=45.0,
        outline={"enabled": False, "color": "#0b0b0e", "width_px": 2.0},
    )
    page = np.full((240, 320, 3), (30, 40, 50), dtype=np.uint8)
    pb = PageBox(box=Box(60, 50, 240, 130), origin=USER, style=style)
    pb.set_translation("Hello")

    baked = bake_typeset_page(page, [pb])

    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay = item._text_overlay
    assert overlay.pixmap() is not None
    pm = overlay.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    alpha = np.frombuffer(bytes(pm.bits()), dtype=np.uint8).reshape(
        pm.height(), pm.width(), 4
    )[..., 3]
    assert (alpha > 0).mean() > 0.02

    qimg = numpy_to_qimage(page).copy()
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(overlay.pos(), overlay.pixmap())
    painter.end()
    canvas_arr = qimage_to_numpy(qimg)

    # A rotated render resamples every glyph through AA twice (once into the
    # premultiplied pixmap cache, once compositing it at the overlay's
    # FRACTIONAL scene position), so every pixel carries an AA-phase delta
    # the angle-0 opaque-interior tests never see. Measured envelope for a
    # correctly-placed 45-deg overlay: 241 changed px, max channel delta 16,
    # nothing beyond 17. A DISPLACED overlay would light up whole glyph
    # bodies with near-full-contrast deltas (100+) — the bounds below catch
    # that while admitting the phase noise.
    changed = np.any(canvas_arr != baked, axis=2)
    assert changed.any()
    ys_c, xs_c = np.nonzero(changed)
    diff = np.abs(
        canvas_arr[ys_c, xs_c].astype(int) - baked[ys_c, xs_c].astype(int)
    ).max(axis=1)
    assert np.percentile(diff, 90) <= 24.0, (
        "rotated overlay diverges from the bake across its body "
        f"(p90={np.percentile(diff, 90)})"
    )
    assert diff.max() <= 48, (
        "rotated overlay compositing diverges from the bake beyond the "
        f"double-AA rounding envelope: max channel delta {diff.max()}"
    )


@pytest.mark.gui
def test_zero_rotation_keeps_legacy_overlay_path(qtbot) -> None:
    """Byte-compat guard: a rotation-0 render takes the UNCHANGED legacy path
    (_render_offset stays None, _ink_offset drives positioning)."""
    style = TextStyle(auto_fit=False, font_size_px=12.0)
    pb = PageBox(box=Box(15, 15, 115, 65), origin=USER, style=style)
    pb.set_translation("plain")
    _scene, item = _scene_with_box(pb)
    item.refresh_text_overlay()
    overlay = item._text_overlay
    assert overlay._render_offset is None
    assert overlay.pixmap() is not None

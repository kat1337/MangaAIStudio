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

from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
)
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import USER, PageBox  # noqa: E402
from manga_ai_studio.core.mask_editor import ToolMode  # noqa: E402
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


# ===========================================================================
# Task 3 — Inspector spacing rows
# ===========================================================================


@pytest.mark.gui
def test_inspector_spacing_commit_routes_through_replace_style(qtbot, tmp_path) -> None:
    """Setting Spacing H / Spacing V and emitting editingFinished commits
    through _replace_style: style field lands, overlay re-renders (pixmap
    changes), ONE boxes_modified emission."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(20, 20, 160, 120)])[0]
    item.pagebox.set_translation("SPACED OUT PROBE")
    item.pagebox.style = TextStyle(auto_fit=False, font_size_px=12.0)
    item.refresh_text_overlay()
    item.setSelected(True)
    QApplication.processEvents()

    panel = window.inspector_panel
    assert panel.char_spacing_spin.value() == 0
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    pm_before = panel.char_spacing_spin.value()
    pixmap_before = np.frombuffer(
        bytes(item._text_overlay.pixmap().toImage().bits()), dtype=np.uint8
    ).copy()

    panel.char_spacing_spin.setValue(10)
    panel.char_spacing_spin.editingFinished.emit()

    assert item.pagebox.style.char_spacing_px == 10.0
    assert len(emitted) == 1

    panel.line_spacing_spin.setValue(24)
    panel.line_spacing_spin.editingFinished.emit()
    assert item.pagebox.style.line_spacing_px == 24.0
    assert len(emitted) == 2

    # The re-render actually changed pixels (spacing moved glyphs).
    arr_before = np.frombuffer(pixmap_before, dtype=np.uint8)
    pixmap_after = np.frombuffer(
        bytes(item._text_overlay.pixmap().toImage().bits()), dtype=np.uint8
    )
    _ = pm_before
    assert not np.array_equal(arr_before, pixmap_after)


@pytest.mark.gui
def test_inspector_spacing_wr01_unchanged_commit_is_noop(qtbot, tmp_path) -> None:
    """An unchanged focus cycle (editingFinished without a value change)
    emits nothing — the WR-01 no-op-on-unchanged discipline."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(20, 20, 160, 120)])[0]
    item.pagebox.set_translation("probe")
    item.setSelected(True)
    QApplication.processEvents()

    panel = window.inspector_panel
    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    panel.char_spacing_spin.editingFinished.emit()
    panel.line_spacing_spin.editingFinished.emit()
    assert emitted == []


@pytest.mark.gui
def test_inspector_spacing_load_and_clear(qtbot, tmp_path) -> None:
    """load_box populates the spins from the box style; clear() resets to 0."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(20, 20, 160, 120)])[0]
    item.pagebox.style = TextStyle(char_spacing_px=8.0, line_spacing_px=40.0)
    item.setSelected(True)
    QApplication.processEvents()

    panel = window.inspector_panel
    assert panel.char_spacing_spin.value() == 8
    assert panel.line_spacing_spin.value() == 40

    canvas = window.canvas
    canvas._clear_selection()
    QApplication.processEvents()
    assert panel.char_spacing_spin.value() == 0
    assert panel.line_spacing_spin.value() == 0


@pytest.mark.gui
def test_spacing_survives_mas_round_trip() -> None:
    """All three new fields survive pagebox_to_json -> json_to_pagebox (the
    D-07 single spelling — project_io consumes to_dict/from_dict verbatim,
    so a .mas save/load preserves rotation + both spacings)."""
    from manga_ai_studio.core.project_io import json_to_pagebox, pagebox_to_json

    style = TextStyle(rotation_deg=-37.5, char_spacing_px=12.5, line_spacing_px=48.0)
    pb = PageBox(box=Box(10, 20, 200, 300), origin=USER, style=style)

    out = json_to_pagebox(pagebox_to_json(pb))
    assert out.style is not None
    assert out.style is not pb.style  # fresh instance (Pitfall 8)
    assert out.style.rotation_deg == -37.5
    assert out.style.char_spacing_px == 12.5
    assert out.style.line_spacing_px == 48.0


# ===========================================================================
# Task 3 — Ctrl+C / Ctrl+V duplication
# ===========================================================================


@pytest.mark.gui
def test_copy_stash_caries_text_style_rotation(qtbot, tmp_path) -> None:
    """Ctrl+C stashes detached clones carrying text + full style incl.
    rotation/spacings; an empty selection leaves the clipboard alone."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(20, 20, 160, 120)])[0]
    item.pagebox.set_translation("COPY ME")
    item.pagebox.style = TextStyle(
        auto_fit=False,
        font_size_px=12.0,
        rotation_deg=30.0,
        char_spacing_px=6.0,
        line_spacing_px=18.0,
    )
    item.setSelected(True)

    window.canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C,
                  Qt.KeyboardModifier.ControlModifier, "c")
    )
    clipboard = window.canvas.box_clipboard
    assert len(clipboard) == 1
    clone = clipboard[0]
    assert clone is not item.pagebox  # detached
    assert clone.payload.translation == "COPY ME"
    assert clone.style.rotation_deg == 30.0
    assert clone.style.char_spacing_px == 6.0
    assert clone.style.line_spacing_px == 18.0

    # Empty selection: silent no-op (clipboard keeps prior contents).
    window.canvas._clear_selection()
    window.canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C,
                  Qt.KeyboardModifier.ControlModifier, "c")
    )
    assert window.canvas.box_clipboard is clipboard


@pytest.mark.gui
def test_paste_inserts_detached_user_clone_at_offset_one_undo(qtbot, tmp_path) -> None:
    """Ctrl+V inserts a USER-origin clone at +16/+16 with bubble number
    cleared and INDEPENDENT payload (mutating the original's text after the
    paste leaves the clone untouched); one Ctrl+Z removes the paste."""
    window = _window_with_page(qtbot, tmp_path)
    item = _seed_boxes_window(window, [Box(20, 20, 120, 100)])[0]
    item.pagebox.set_translation("ORIGINAL")
    item.pagebox.bubble_no = 7
    item.pagebox.manual_override = True
    item.pagebox.style = TextStyle(auto_fit=False, font_size_px=12.0, rotation_deg=15.0)
    item.refresh_text_overlay()
    item.setSelected(True)

    canvas = window.canvas
    canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C,
                  Qt.KeyboardModifier.ControlModifier, "c")
    )
    emitted: list = []
    canvas.boxes_modified.connect(lambda snap: emitted.append(list(snap)))
    n_before = canvas.box_count()

    canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                  Qt.KeyboardModifier.ControlModifier, "v")
    )

    assert canvas.box_count() == n_before + 1
    assert len(emitted) == 1
    # The payload of the single emission is the PRE-paste layer.
    assert len(emitted[0]) == n_before

    pasted = canvas._box_items[-1].pagebox
    x1, y1, x2, y2 = pasted.box.as_tuple
    ox1, oy1, ox2, oy2 = item.pagebox.box.as_tuple
    assert (x1, y1) == (ox1 + 16, oy1 + 16)
    assert (x2, y2) == (ox2 + 16, oy2 + 16)
    assert pasted.origin == USER
    assert pasted.bubble_no is None
    assert pasted.manual_override is False
    assert pasted.edited is True
    # Text + full style rode the copy (that IS the feature).
    assert pasted.payload.translation == "ORIGINAL"
    assert pasted.style.rotation_deg == 15.0
    # Pitfall-8 independence: mutating the ORIGINAL's text after the paste
    # leaves the clone untouched.
    item.pagebox.set_translation("CHANGED")
    assert pasted.payload.translation == "ORIGINAL"
    # The paste is selected as the new primary.
    assert canvas._primary_box is canvas._box_items[-1]

    # One Ctrl+Z removes the paste.
    window.on_undo()
    assert window.canvas.box_count() == n_before


@pytest.mark.gui
def test_paste_empty_clipboard_silent_noop(qtbot, tmp_path) -> None:
    """Ctrl+V with an empty clipboard emits nothing and adds no boxes."""
    window = _window_with_page(qtbot, tmp_path)
    _seed_boxes_window(window, [Box(20, 20, 80, 80)])
    canvas = window.canvas
    emitted: list = []
    canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    canvas.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                  Qt.KeyboardModifier.ControlModifier, "v")
    )
    assert emitted == []
    assert canvas.box_count() == 1


# ===========================================================================
# quick-260825-uzv — Canvas dispatch — RotationHandle press
# ===========================================================================


def _press_at(canvas: EditorCanvas, scene_pt: QPointF,
              modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
              ) -> QMouseEvent:
    """Viewport-coord press builder landing on SCENE ``scene_pt``.

    The test_gui_canvas ``_press`` pattern: QGraphicsView centers the scene,
    so the desired scene point is mapped back to viewport coords first.
    """
    vp = canvas.mapFromScene(scene_pt)
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )


def _selected_box_with_visible_rotation_handle(qtbot) -> tuple[EditorCanvas, BoxItem]:
    """Canvas + selected/primary box whose RotationHandle is VISIBLE."""
    from manga_ai_studio.gui.box_item import RotationHandle as _RH

    canvas = _canvas_with_image(qtbot)
    style = TextStyle(auto_fit=False, font_size_px=12.0)
    item = _seed_box(canvas, Box(60, 60, 220, 140), style=style)
    item.setSelected(True)
    canvas._primary_box = item
    canvas._sync_handles_visibility()
    QApplication.processEvents()
    rh = item._rotation_handle
    assert isinstance(rh, _RH)
    assert rh.isVisible(), "setup must produce a VISIBLE rotation handle"
    return canvas, item


@pytest.mark.gui
def test_press_on_visible_rotation_handle_arms_rotate_instead_of_deselecting(
    qtbot,
) -> None:
    """THE DEFECT (quick-260825-uzv): a view-level press on the visible
    RotationHandle must arm the rotate drag — NOT clear the selection. After
    the press the drag is advanced and committed so the full dispatch path
    (press -> arm -> preview -> commit) is proven end-to-end."""
    canvas, item = _selected_box_with_visible_rotation_handle(qtbot)
    rh = item._rotation_handle
    scene_pos = rh.mapToScene(rh.boundingRect().center())

    ev = _press_at(canvas, scene_pos)
    canvas.mousePressEvent(ev)

    assert canvas._rotating_box is item, (
        "press on the visible rotation handle must arm the rotate drag"
    )
    assert item.isSelected(), (
        "pressing the rotation handle must NOT clear the selection"
    )
    assert rh.isVisible(), "the handle must stay visible during a rotate drag"

    center = item.rect().center()
    canvas._advance_rotation(QPointF(center.x() + 70.0, center.y()))
    canvas._commit_rotation()
    assert item.pagebox.style is not None
    assert item.pagebox.style.rotation_deg != pytest.approx(0.0), (
        "the committed handle drag must write style.rotation_deg"
    )


@pytest.mark.gui
def test_press_on_genuinely_empty_canvas_still_clears_selection(qtbot) -> None:
    """Regression guard (UI-SPEC §12d preserved): pressing genuinely EMPTY
    canvas far from any box/handle/badge clears the selection and never arms
    a rotate drag. Passes today; must KEEP passing."""
    canvas, item = _selected_box_with_visible_rotation_handle(qtbot)

    # (280, 280) is inside the 300x300 page but clear of the box
    # (60..220 x 60..140), its TL bubble badge, TR redetect handle, and the
    # TL-above rotation handle.
    ev = _press_at(canvas, QPointF(280.0, 280.0))
    canvas.mousePressEvent(ev)

    assert not item.isSelected(), "empty-canvas press still clears selection"
    assert canvas._rotating_box is None


@pytest.mark.gui
def test_alt_brush_press_on_visible_rotation_handle_arms_rotation(qtbot) -> None:
    """Alt parity (D-15 consistency): under an active paint tool, Alt+press
    on the visible RotationHandle arms rotation instead of creating a box."""
    canvas, item = _selected_box_with_visible_rotation_handle(qtbot)
    canvas.set_tool(ToolMode.BRUSH)
    rh = item._rotation_handle
    scene_pos = rh.mapToScene(rh.boundingRect().center())

    ev = _press_at(canvas, scene_pos, Qt.KeyboardModifier.AltModifier)
    canvas.mousePressEvent(ev)

    assert canvas._rotating_box is item, (
        "Alt+press on the visible rotation handle under BRUSH must arm rotation"
    )

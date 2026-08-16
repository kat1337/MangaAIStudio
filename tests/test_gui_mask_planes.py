"""GUI tests for the Phase 8 three-plane mask model (plan 08-02).

RESEARCH §2.2 Option B: the displayed/LaMa/persisted composite ``canvas._mask``
is recomposed from three planes — a derived auto binary (``_auto_bin``), a
manual-stroke QImage (``_mask_manual``), and an erase-ledger QImage
(``_mask_erase``):

    composite = (manual | auto) & ~erase

Hand strokes always inpaint (D-01), detected content is discardable/
re-dilatable without touching strokes (D-02/D-07/D-08), and an eraser's effect
survives recomposition (the ledger invariant — the single most load-bearing
regression of the phase per RESEARCH §10).

Task 1 covers the canvas plane model itself (planes driven directly with
hand-set contents + the real stroke helpers). Task 2 adds the plane-aware
undo/persistence tests; Task 3 the MASK-06 paint-under-boxes dispatch tests.

Marker conventions mirror the repo: ``unit`` for the numpy-only
``core/mask_planes.py`` helpers (no Qt), ``gui`` for canvas/MainWindow tests
(PySide6 + a display via pytest-qt).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from manga_ai_studio.core.mask_editor import (  # noqa: E402
    ToolMode,
    mask_to_numpy_binary,
    paint_mask_stroke,
)
from manga_ai_studio.core.mask_planes import (  # noqa: E402
    MaskPlanesSnapshot,
    pack_binary,
    unpack_binary,
)
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _canvas_with_page(qtbot, w: int = 40, h: int = 30) -> EditorCanvas:
    """A shown canvas with a small synthetic page loaded (zoom stays 1.0)."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 400)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 200, 200))
    canvas.set_image(QPixmap.fromImage(img))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    return canvas


def _rect_bin(w: int, h: int, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    """An (H, W) uint8 0/255 binary with a 255-filled rect [x0:x1, y0:y1]."""
    arr = np.zeros((h, w), dtype=np.uint8)
    arr[y0:y1, x0:x1] = 255
    return arr


def _plane_from_bin(arr: np.ndarray) -> QImage:
    """Build a plane QImage from a binary array (red overlay where 255).

    Any QImage whose alpha marks content works as a plane — ``_mask_manual``
    is painted by the MASK_PAINT_COLOR helpers and ``_mask_erase`` is painted
    RED (never CompositionMode_Clear), so alpha>0 == "pixel set" for both.
    """
    from manga_ai_studio.core.mask_editor import numpy_binary_to_mask_qimage

    return numpy_binary_to_mask_qimage(arr)


def _mouse_event(canvas: EditorCanvas, sx: float, sy: float, etype) -> QMouseEvent:
    """A left-button mouse event whose viewport pos maps to scene (sx, sy)."""
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        etype,
        QPointF(vp),
        (
            Qt.MouseButton.LeftButton
            if etype is QEvent.Type.MouseButtonPress
            else Qt.MouseButton.NoButton
        ),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drive_brush_stroke(
    canvas: EditorCanvas, x0: float, y0: float, x1: float, y1: float
) -> None:
    """Drive a real press-move-release brush stroke through the canvas handlers."""
    canvas._begin_paint(_mouse_event(canvas, x0, y0, QEvent.Type.MouseButtonPress))
    canvas._advance_paint(QPointF(x1, y1))
    canvas._end_paint(_mouse_event(canvas, x1, y1, QEvent.Type.MouseButtonRelease))


# ---------------------------------------------------------------------------
# Task 1 — core/mask_planes.py helpers (numpy-only, unit marker)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pack_binary_round_trips_through_unpack_binary() -> None:
    """pack_binary/unpack_binary round-trip a (H, W) 0/255 binary exactly."""
    arr = _rect_bin(13, 7, 2, 3, 9, 6)  # deliberately odd sizes (bit padding)
    packed = pack_binary(arr)
    assert packed.dtype == np.uint8
    assert packed.ndim == 1
    assert len(packed) == (13 * 7 + 7) // 8
    unpacked = unpack_binary(packed, 7, 13)
    assert unpacked.dtype == np.uint8
    assert unpacked.shape == (7, 13)
    np.testing.assert_array_equal(unpacked, arr)


@pytest.mark.unit
def test_unpack_binary_rejects_mismatched_length() -> None:
    """T-08-02: a blob whose length cannot represent (h, w) is a hard
    ValueError, never a silent mis-shape."""
    arr = _rect_bin(10, 10, 0, 0, 10, 10)
    packed = pack_binary(arr)
    # Short blob (truncated) -> ValueError.
    with pytest.raises(ValueError):
        unpack_binary(packed[:-1], 10, 10)
    # Dims that need MORE bits than the blob carries -> ValueError.
    with pytest.raises(ValueError):
        unpack_binary(packed, 11, 10)
    # Dims that need FEWER bits than the blob carries -> ValueError (the
    # 08-04 load side cross-checks blob length against meta dims; a mismatch
    # in either direction is corruption, not a resize).
    with pytest.raises(ValueError):
        unpack_binary(packed, 5, 5)


@pytest.mark.unit
def test_snapshot_copy_detaches_planes() -> None:
    """MaskPlanesSnapshot.copy() detaches manual/erase QImages + the packed
    auto array — mutating the originals after the copy never reaches it."""
    manual = _plane_from_bin(_rect_bin(10, 10, 0, 0, 5, 5))
    erase = _plane_from_bin(_rect_bin(10, 10, 5, 5, 10, 10))
    auto_packed = pack_binary(_rect_bin(10, 10, 2, 2, 8, 8))
    snap = MaskPlanesSnapshot(manual=manual, erase=erase, auto_packed=auto_packed)
    copied = snap.copy()
    # Mutate every original after the copy.
    manual.fill(QColor(255, 0, 0, 255))
    erase.fill(QColor(255, 0, 0, 255))
    auto_packed[:] = 0
    assert mask_to_numpy_binary(copied.manual).sum() == 255 * 25
    assert mask_to_numpy_binary(copied.erase).sum() == 255 * 25
    np.testing.assert_array_equal(
        unpack_binary(copied.auto_packed, 10, 10), _rect_bin(10, 10, 2, 2, 8, 8)
    )
    # None auto_packed copies to None (no auto content).
    none_snap = MaskPlanesSnapshot(manual=manual, erase=erase, auto_packed=None)
    assert none_snap.copy().auto_packed is None


# ---------------------------------------------------------------------------
# Task 1 — canvas three-plane model + recompose + eraser dual-write
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_composite_equals_manual_or_auto_minus_erase(qtbot) -> None:
    """The displayed composite is exactly (manual | auto) & ~erase for
    hand-set plane contents (driven directly via set_planes)."""
    w, h = 40, 30
    canvas = _canvas_with_page(qtbot, w, h)
    manual_bin = _rect_bin(w, h, 2, 2, 12, 10)
    erase_bin = _rect_bin(w, h, 4, 4, 6, 6)  # erases a hole inside manual
    auto_bin = _rect_bin(w, h, 20, 10, 30, 20)
    canvas.set_planes(
        _plane_from_bin(manual_bin), _plane_from_bin(erase_bin), auto_bin
    )
    expected = (manual_bin | auto_bin) & ~erase_bin
    np.testing.assert_array_equal(mask_to_numpy_binary(canvas.get_mask()), expected)


@pytest.mark.gui
def test_erase_ledger_survives_redilate(qtbot) -> None:
    """THE ledger invariant (RESEARCH §10, the phase's load-bearing
    regression): an erased false positive never resurrects across a
    re-dilate — recomposition is always (manual | auto) & ~erase with the
    ledger retained, so a differently-grown auto plane still misses the
    erased pixel."""
    w, h = 40, 30
    canvas = _canvas_with_page(qtbot, w, h)
    auto_bin = _rect_bin(w, h, 10, 10, 20, 20)
    canvas.set_planes(_plane_from_bin(np.zeros((h, w), np.uint8)), QImage(), auto_bin)
    # Erase one pixel inside the auto content (a false positive).
    erased = (15, 15)
    canvas._mask_erase = _plane_from_bin(_rect_bin(w, h, 15, 15, 16, 16))
    canvas.recompose_mask()
    composite = mask_to_numpy_binary(canvas.get_mask())
    assert composite[erased[1], erased[0]] == 0, "erased pixel must be gone"
    assert composite[12, 12] == 255, "non-erased auto content must survive"

    # Simulate a re-dilate: the auto plane is replaced by a GROWN binary that
    # re-covers the erased pixel. The erase ledger must keep it out.
    grown = _rect_bin(w, h, 5, 5, 25, 25)
    assert grown[erased[1], erased[0]] == 255, "fixture: grown auto re-covers pixel"
    canvas.set_auto_binary(grown)
    recomposed = mask_to_numpy_binary(canvas.get_mask())
    assert recomposed[erased[1], erased[0]] == 0, (
        "the erased pixel STAYS gone across a re-dilate (the ledger invariant)"
    )
    np.testing.assert_array_equal(recomposed, grown & ~_rect_bin(w, h, 15, 15, 16, 16))


@pytest.mark.gui
def test_set_mask_replaces_auto_plane_only(qtbot) -> None:
    """UI-SPEC A10: set_mask (re-detection) replaces ONLY the auto plane — a
    manual stroke painted before the set_mask call survives it."""
    w, h = 40, 30
    canvas = _canvas_with_page(qtbot, w, h)
    manual_bin = _rect_bin(w, h, 2, 2, 10, 10)
    canvas.set_planes(
        _plane_from_bin(manual_bin), QImage(), np.zeros((h, w), np.uint8)
    )
    # A "re-detection" arriving as a mask QImage with DIFFERENT content.
    new_auto = _rect_bin(w, h, 20, 5, 35, 25)
    canvas.set_mask(_plane_from_bin(new_auto))
    composite = mask_to_numpy_binary(canvas.get_mask())
    assert composite[5, 5] == 255, "the pre-existing manual stroke must survive"
    assert composite[10, 25] == 255, "the new detection content must land"
    np.testing.assert_array_equal(composite, manual_bin | new_auto)
    # And the auto plane itself was replaced (auto-only pixel flipped on).
    assert canvas._auto_bin is not None
    np.testing.assert_array_equal(canvas._auto_bin, new_auto)


@pytest.mark.gui
def test_clear_mask_empties_all_planes_and_emits_once(qtbot) -> None:
    """clear_mask empties manual + erase + auto and emits mask_modified
    exactly once."""
    w, h = 40, 30
    canvas = _canvas_with_page(qtbot, w, h)
    canvas.set_planes(
        _plane_from_bin(_rect_bin(w, h, 2, 2, 10, 10)),
        _plane_from_bin(_rect_bin(w, h, 12, 12, 14, 14)),
        _rect_bin(w, h, 20, 5, 35, 25),
    )
    emissions: list[int] = []
    canvas.mask_modified.connect(lambda: emissions.append(1))
    canvas.clear_mask()
    assert len(emissions) == 1, "clear_mask must emit mask_modified exactly once"
    assert canvas._auto_bin is None
    assert not mask_to_numpy_binary(canvas._mask_manual).any()
    assert not mask_to_numpy_binary(canvas._mask_erase).any()
    assert not mask_to_numpy_binary(canvas.get_mask()).any()


@pytest.mark.gui
def test_recompose_mask_does_not_emit(qtbot) -> None:
    """recompose_mask is signal-silent (Pitfall 13-1 — detection/re-dilate/
    restore recompositions are non-undoable and must not re-push)."""
    canvas = _canvas_with_page(qtbot, 40, 30)
    with qtbot.assertNotEmitted(canvas.mask_modified):
        canvas.set_auto_binary(_rect_bin(40, 30, 5, 5, 15, 15))
        canvas.recompose_mask()


@pytest.mark.gui
def test_brush_stroke_dual_writes_manual_plane(qtbot) -> None:
    """A brush stroke paints the live composite AND the manual plane; the
    stroke-commit recompose makes the composite exactly the manual binary
    (no auto/erase content in this fixture)."""
    w, h = 60, 40
    canvas = _canvas_with_page(qtbot, w, h)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(6)
    emissions: list[int] = []
    canvas.mask_modified.connect(lambda: emissions.append(1))

    _drive_brush_stroke(canvas, 20, 20, 35, 20)

    assert len(emissions) == 1, "one emission per stroke is preserved"
    manual_bin = mask_to_numpy_binary(canvas._mask_manual)
    assert manual_bin.any(), "the stroke must land on the manual plane"
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()), manual_bin
    )
    # The erase ledger stays untouched by a paint stroke.
    assert not mask_to_numpy_binary(canvas._mask_erase).any()


@pytest.mark.gui
def test_eraser_stroke_dual_writes_ledger_plane(qtbot) -> None:
    """Pitfall 13-11: an erase stroke must ALSO write the erase ledger (with
    normal red composition) or its effect is lost on the next recompose. The
    display composite keeps CompositionMode_Clear semantics live; the manual
    plane is untouched by an erase."""
    w, h = 60, 40
    canvas = _canvas_with_page(qtbot, w, h)
    auto_bin = _rect_bin(w, h, 10, 10, 50, 30)
    canvas.set_planes(_plane_from_bin(np.zeros((h, w), np.uint8)), QImage(), auto_bin)
    canvas.set_tool(ToolMode.ERASER)
    canvas.set_brush_size(6)

    _drive_brush_stroke(canvas, 20, 20, 35, 20)

    ledger_bin = mask_to_numpy_binary(canvas._mask_erase)
    assert ledger_bin.any(), "the erase stroke must MARK pixels in the ledger"
    assert not mask_to_numpy_binary(canvas._mask_manual).any(), (
        "an erase stroke must not touch the manual plane"
    )
    composite = mask_to_numpy_binary(canvas.get_mask())
    assert composite[20, 20] == 0, "erased pixels are gone from the composite"
    assert composite[15, 45] == 255, "non-erased auto content survives"
    np.testing.assert_array_equal(composite, auto_bin & ~ledger_bin)


@pytest.mark.gui
def test_planes_snapshot_round_trips_through_set_planes(qtbot) -> None:
    """planes_snapshot() -> set_planes() restores an identical composite with
    no signal emission (the read/restore pair Task 2 and later plans use)."""
    w, h = 40, 30
    canvas = _canvas_with_page(qtbot, w, h)
    manual_bin = _rect_bin(w, h, 2, 2, 12, 10)
    erase_bin = _rect_bin(w, h, 4, 4, 6, 6)
    auto_bin = _rect_bin(w, h, 20, 10, 30, 20)
    canvas.set_planes(
        _plane_from_bin(manual_bin), _plane_from_bin(erase_bin), auto_bin
    )
    snap = canvas.planes_snapshot()
    # Detach the snapshot from the canvas, then wipe the canvas planes.
    canvas.set_planes(QImage(), QImage(), None)
    assert not mask_to_numpy_binary(canvas.get_mask()).any()
    with qtbot.assertNotEmitted(canvas.mask_modified):
        canvas.set_planes(snap.manual, snap.erase, unpack_binary(snap.auto_packed, h, w))
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()),
        (manual_bin | auto_bin) & ~erase_bin,
    )


# ---------------------------------------------------------------------------
# Task 2 — plane-aware MASK undo + D-11 per-page persistence
# ---------------------------------------------------------------------------


def _make_window(qtbot, tmp_path):
    """A MainWindow wired to a ProfileManager in tmp_path (test_history shape)."""
    from manga_ai_studio.config.profile_manager import ProfileManager
    from manga_ai_studio.gui.main_window import MainWindow

    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _open_page(window, tmp_path, size: int = 48):
    """Open a solid-white page so the canvas has an image + seeded planes."""
    img_path = tmp_path / "page.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    return img_path


@pytest.mark.gui
def test_undo_removes_stroke_keeps_auto_and_redo_restores(qtbot, tmp_path) -> None:
    """The 03-08 semantic shift, now the plane model's contract: undo removes
    the stroke's MANUAL contribution but the auto content stays; redo
    restores the stroke."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    canvas = window.canvas
    auto_bin = _rect_bin(48, 48, 30, 30, 40, 40)
    canvas.set_auto_binary(auto_bin)  # the (silent) detection baseline
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(6)

    _drive_brush_stroke(canvas, 8, 12, 24, 12)

    composite_before = mask_to_numpy_binary(canvas.get_mask())
    assert composite_before[12, 16] == 255, "fixture: the stroke painted"
    assert composite_before[35, 35] == 255, "fixture: auto content present"

    window.on_undo()
    after_undo = mask_to_numpy_binary(canvas.get_mask())
    assert after_undo[12, 16] == 0, "the stroke's manual contribution is removed"
    assert after_undo[35, 35] == 255, "the auto content stays"
    assert canvas._auto_bin is not None
    np.testing.assert_array_equal(canvas._auto_bin, auto_bin)

    window.on_redo()
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()), composite_before
    )


@pytest.mark.gui
def test_first_stroke_seeds_clean_baseline_auto_untouched(qtbot, tmp_path) -> None:
    """The first stroke of a page seeds a clean baseline (transparent
    manual/erase + the CURRENT auto) — undoing it leaves the auto plane
    exactly as it was (the 03-08 seeded-baseline rule, generalized)."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    canvas = window.canvas
    auto_bin = _rect_bin(48, 48, 5, 5, 15, 15)
    canvas.set_auto_binary(auto_bin)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(6)

    _drive_brush_stroke(canvas, 30, 30, 40, 30)  # the FIRST stroke
    assert mask_to_numpy_binary(canvas.get_mask())[30, 35] == 255

    window.on_undo()
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()), auto_bin
    ), "undoing the first stroke leaves only the auto plane (untouched)"
    assert canvas._auto_bin is not None
    np.testing.assert_array_equal(canvas._auto_bin, auto_bin)
    assert not window.history.can_undo_mask()


@pytest.mark.gui
def test_undo_does_not_repush_planes(qtbot, tmp_path) -> None:
    """The test_undo_does_not_repush contract, kept green on the plane path:
    apply_undo_mask does NOT emit mask_modified."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    canvas = window.canvas
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(6)
    _drive_brush_stroke(canvas, 10, 10, 25, 10)
    assert window.history.can_undo_mask()

    with qtbot.assertNotEmitted(canvas.mask_modified):
        window.on_undo()
    assert not window.history.can_undo_mask()
    assert window.history.can_redo_mask()


@pytest.mark.gui
def test_undo_erase_stroke_returns_erased_pixels(qtbot, tmp_path) -> None:
    """Undoing an erase stroke restores the ledger's before-state — the
    erased pixels return."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    canvas = window.canvas
    auto_bin = _rect_bin(48, 48, 10, 10, 40, 40)
    canvas.set_auto_binary(auto_bin)
    canvas.set_tool(ToolMode.ERASER)
    canvas.set_brush_size(8)

    _drive_brush_stroke(canvas, 20, 20, 32, 20)
    erased = mask_to_numpy_binary(canvas.get_mask())
    assert erased[20, 26] == 0, "fixture: pixels were erased"
    assert erased[15, 35] == 255, "fixture: other auto content survived"

    window.on_undo()
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()), auto_bin
    ), "undo restores the ledger before-state: erased pixels return"


@pytest.mark.gui
def test_undo_clear_mask_restores_all_three_planes(qtbot, tmp_path) -> None:
    """clear_mask pushes the full pre-clear planes as the before-state —
    undo restores manual + erase + auto together."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path)
    canvas = window.canvas
    auto_bin = _rect_bin(48, 48, 30, 30, 42, 42)
    canvas.set_auto_binary(auto_bin)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(6)
    _drive_brush_stroke(canvas, 8, 12, 24, 12)  # manual content (stroke 1)
    canvas.set_tool(ToolMode.ERASER)
    _drive_brush_stroke(canvas, 34, 36, 40, 36)  # ledger content (stroke 2)
    before_clear = mask_to_numpy_binary(canvas.get_mask())
    assert before_clear[12, 16] == 255 and before_clear[36, 37] == 0

    canvas.clear_mask()
    assert not mask_to_numpy_binary(canvas.get_mask()).any()

    window.on_undo()
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()), before_clear
    ), "undo restores the full pre-clear planes (manual + erase + auto)"
    assert canvas._auto_bin is not None
    np.testing.assert_array_equal(canvas._auto_bin, auto_bin)


@pytest.mark.gui
def test_planes_round_trip_across_page_switch(qtbot, tmp_path) -> None:
    """D-11 seam: page A's planes round-trip to page B and back via
    on_page_selected — the composite is identical after the round trip, and
    the persisted ImageFile plane slots are detached copies (mutating the
    live canvas after the switch never reaches them)."""
    window = _make_window(qtbot, tmp_path)
    size = 48
    p1 = tmp_path / "page1.png"
    p2 = tmp_path / "page2.png"
    for p, fill in ((p1, QColor(255, 255, 255)), (p2, QColor(210, 210, 210))):
        img = QImage(size, size, QImage.Format.Format_RGB32)
        img.fill(fill)
        img.save(str(p))
    window._set_pages([p1, p2])
    canvas = window.canvas

    auto_bin = _rect_bin(size, size, 30, 30, 42, 42)
    canvas.set_auto_binary(auto_bin)
    canvas.set_tool(ToolMode.BRUSH)
    canvas.set_brush_size(6)
    _drive_brush_stroke(canvas, 8, 12, 24, 12)
    canvas.set_tool(ToolMode.ERASER)
    _drive_brush_stroke(canvas, 34, 36, 40, 36)
    composite_a = mask_to_numpy_binary(canvas.get_mask())
    assert composite_a.any()

    # A -> B -> A.
    window.on_page_selected(p2)
    assert not mask_to_numpy_binary(canvas.get_mask()).any(), (
        "page B starts with empty planes (no bleed from page A)"
    )
    imf_a = window.image_files[0]
    assert imf_a.auto_mask is not None, "auto plane packed into ImageFile A"
    assert imf_a.mask_manual is not None, "manual plane packed into ImageFile A"
    assert imf_a.mask_erase is not None, "erase ledger packed into ImageFile A"

    window.on_page_selected(p1)
    np.testing.assert_array_equal(
        mask_to_numpy_binary(canvas.get_mask()), composite_a
    ), "the composite survives the page round trip unchanged"

    # Boundary-copy semantics on the plane path: repainting on page A must
    # never reach the packed slots captured at the switch.
    canvas.set_tool(ToolMode.BRUSH)
    _drive_brush_stroke(canvas, 5, 5, 12, 5)
    stored_manual = unpack_binary(imf_a.mask_manual, size, size)
    stroked = mask_to_numpy_binary(canvas._mask_manual)
    assert (stored_manual & ~stroked).any() or not np.array_equal(
        stored_manual, stroked
    ), "the persisted manual plane is a detached copy, not the live plane"

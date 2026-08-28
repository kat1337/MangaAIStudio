"""Unit tests for the two-stack HistoryManager (core/history_manager.py).

These exercise the MASK and IMAGE undo/redo stacks WITHOUT instantiating any
QWidget (RESEARCH Validation Architecture — D-10: core/ holds pure ops,
testable headless). Only QImage objects are constructed via the qtbot
fixture's QApplication. The two Pitfall-2 regression guards
(``test_mask_snapshot_is_copied`` and ``test_mask_pop_returns_copy``) lock the
``.copy()`` discipline on push AND pop so the history never aliases the
caller's QImage. Marked ``@pytest.mark.unit`` (no torch, no display beyond the
offscreen Qt init).

Plan 06 Task 2 ADDS the GUI wiring tests (test_mask_modified_pushes_to_history,
test_undo_mask_applies_snapshot, etc.) to this same file — they instantiate a
real MainWindow and exercise the canvas/main_window history wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPixmap  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.history_manager import HistoryManager  # noqa: E402
from manga_ai_studio.core.mask_editor import (  # noqa: E402
    ToolMode,
    paint_mask_stroke,
)
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


def _transparent_mask(size: int = 64) -> QImage:
    """Build a transparent ARGB32 QImage (mask-editing target)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _painted_mask(brush_size: int, size: int = 64) -> QImage:
    """Build a mask QImage with a single brush dot painted at (size//2, size//2).

    Each call returns a fresh QImage so subsequent mutations on the caller's
    mask do not leak between snapshots.
    """
    mask = _transparent_mask(size)
    center = QPointF(size / 2, size / 2)
    paint_mask_stroke(mask, center, center, brush_size, eraser=False)
    return mask


def _opaque_stroked_mask(size: int = 64, brush_size: int = 10) -> QImage:
    """Build a mask QImage with a genuinely-opaque two-point brush stroke.

    The single-point ``_painted_mask`` helper (p1 == p2) draws a degenerate
    line that renders ZERO opaque pixels on this Qt build (a zero-length
    ``drawLine`` is a no-op), so it is indistinguishable from the transparent
    baseline. The plan-08 regression tests MUST distinguish a "stroked" mask
    from a clean baseline, so they use a real two-point segment whose round-cap
    caps fill a measurable disc. Each call returns a fresh QImage.
    """
    mask = _transparent_mask(size)
    mid = size / 2
    p1 = QPointF(mid - brush_size, mid)
    p2 = QPointF(mid + brush_size, mid)
    paint_mask_stroke(mask, p1, p2, brush_size, eraser=False)
    return mask


def _opaque_pixel_count(img: QImage) -> int:
    """Count non-transparent pixels in ``img`` (a mask-content proxy)."""
    w, h = img.width(), img.height()
    return sum(1 for y in range(h) for x in range(w) if img.pixelColor(x, y).alpha() > 0)


# ---------------------------------------------------------------------------
# Task 1 — core HistoryManager behavior (no GUI)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mask_undo_restores_prior_state() -> None:
    """3 pushes, 3 pops — each pop returns the prior mask; 4th pop is None."""
    history = HistoryManager(limit=20)
    m1, m2, m3 = _painted_mask(5), _painted_mask(10), _painted_mask(15)
    history.push_mask_state(m1)
    history.push_mask_state(m2)
    history.push_mask_state(m3)

    # The current mask after pushing all three is conceptually m3 — pop with it.
    cur = _painted_mask(20)
    # Pop 1: returns m3 (the most-recent push).
    prev = history.pop_mask_undo(cur)
    assert prev is not None
    assert prev.pixelColor(32, 32).alpha() == m3.pixelColor(32, 32).alpha()

    # Pop 2: returns m2.
    prev = history.pop_mask_undo(prev)
    assert prev is not None
    assert prev.pixelColor(32, 32).alpha() == m2.pixelColor(32, 32).alpha()

    # Pop 3: returns m1.
    prev = history.pop_mask_undo(prev)
    assert prev is not None
    assert prev.pixelColor(32, 32).alpha() == m1.pixelColor(32, 32).alpha()

    # Pop 4: stack empty.
    prev = history.pop_mask_undo(prev)
    assert prev is None


@pytest.mark.unit
def test_mask_redo_replays() -> None:
    """After 2 undos, redo replays the 2nd then the 3rd; 3rd redo is None."""
    history = HistoryManager(limit=20)
    m1, m2, m3 = _painted_mask(5), _painted_mask(10), _painted_mask(15)
    history.push_mask_state(m1)
    history.push_mask_state(m2)
    history.push_mask_state(m3)

    # Undo twice from the current (m3-like) state — pops return m3 then m2.
    cur = _painted_mask(20)
    history.pop_mask_undo(cur)  # returns m3 (stashed into redo)
    history.pop_mask_undo(cur)  # returns m2 (stashed into redo)

    # Redo twice — replays m3 then m2 (the states we just stashed).
    nxt = history.pop_mask_redo(cur)
    assert nxt is not None
    assert nxt.pixelColor(32, 32).alpha() == m3.pixelColor(32, 32).alpha()
    nxt2 = history.pop_mask_redo(cur)
    assert nxt2 is not None
    assert nxt2.pixelColor(32, 32).alpha() == m2.pixelColor(32, 32).alpha()

    # 3rd redo is None.
    assert history.pop_mask_redo(cur) is None


@pytest.mark.unit
def test_mask_push_clears_redo() -> None:
    """A new edit after an undo invalidates the redo branch."""
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(5))
    history.push_mask_state(_painted_mask(10))

    # Undo once so the redo stack gets populated.
    cur = _painted_mask(15)
    history.pop_mask_undo(cur)
    assert history.can_redo_mask()

    # Push a new state — the redo branch must be cleared.
    history.push_mask_state(_painted_mask(20))
    assert not history.can_redo_mask()
    # pop_mask_redo returns None (redo stack cleared).
    assert history.pop_mask_redo(cur) is None


@pytest.mark.unit
def test_image_undo_restores_patch() -> None:
    """2 image pushes, 2 pops — each returns the prior (x, y, patch)."""
    history = HistoryManager(limit=20)
    patch_a = np.zeros((4, 4, 3), dtype=np.uint8)
    patch_b = np.ones((4, 4, 3), dtype=np.uint8) * 255
    history.push_image_action(10, 20, patch_a)
    history.push_image_action(30, 40, patch_b)

    # Current image — pop_image_undo swaps the current region into redo and
    # returns the prior patch.
    current = np.zeros((100, 100, 3), dtype=np.uint8)
    res = history.pop_image_undo(current)
    assert res is not None
    x, y, patch = res
    assert (x, y) == (30, 40)
    assert np.array_equal(patch, patch_b)

    res2 = history.pop_image_undo(current)
    assert res2 is not None
    x2, y2, patch2 = res2
    assert (x2, y2) == (10, 20)
    assert np.array_equal(patch2, patch_a)


@pytest.mark.unit
def test_image_redo_replays() -> None:
    """After undoing both edits, redo replays the post-edit regions in order.

    The image_redo branch holds the post-edit region captured at undo time
    (the swap-in step). Redoing returns that captured region so the caller can
    re-apply the edit.
    """
    history = HistoryManager(limit=20)
    # Two edits: edit 1 at (10, 20) wrote value 50; edit 2 at (30, 40) wrote 150.
    # Each push records the PRE-edit region (zeros) so undo restores it.
    pre_edit = np.zeros((4, 4, 3), dtype=np.uint8)
    history.push_image_action(10, 20, pre_edit)
    history.push_image_action(30, 40, pre_edit)

    # The "current" image holds the post-edit state for both regions.
    current = np.zeros((100, 100, 3), dtype=np.uint8)
    current[20:24, 10:14] = 50
    current[40:44, 30:34] = 150

    # Undo both: pop swaps the current post-edit region into redo.
    history.pop_image_undo(current)
    history.pop_image_undo(current)

    # Redo replays edit 1 then edit 2 (LIFO order of the redo stack).
    res = history.pop_image_redo(current)
    assert res is not None
    x, y, patch = res
    assert (x, y) == (10, 20)
    assert np.array_equal(patch, np.full((4, 4, 3), 50, dtype=np.uint8))

    res2 = history.pop_image_redo(current)
    assert res2 is not None
    x2, y2, patch2 = res2
    assert (x2, y2) == (30, 40)
    assert np.array_equal(patch2, np.full((4, 4, 3), 150, dtype=np.uint8))


@pytest.mark.unit
def test_image_undo_swaps_current_into_redo() -> None:
    """pop_image_undo captures the CURRENT image's region into the redo stack.

    Setup: push patch_a (the pre-inpaint content of region [y:y+h, x:x+w]).
    Set the CURRENT image so its region contains a distinct value (e.g., the
    inpainted output). Undo — then redo — the redo patch must match the current
    image's region at undo time, NOT patch_a.
    """
    history = HistoryManager(limit=20)
    patch_a = np.zeros((4, 4, 3), dtype=np.uint8)
    history.push_image_action(5, 5, patch_a)

    # Current image: the region [5:9, 5:9] holds the inpainted result (value 200).
    current = np.zeros((50, 50, 3), dtype=np.uint8)
    current[5:9, 5:9] = 200

    res = history.pop_image_undo(current)
    assert res is not None
    # Undo returned patch_a (the prior content); the redo stack now holds the
    # current image's region at undo time.
    redo = history.pop_image_redo(current)
    assert redo is not None
    _rx, _ry, redo_patch = redo
    # Redo patch should match the current image's region captured at undo time.
    assert np.array_equal(redo_patch, np.full((4, 4, 3), 200, dtype=np.uint8))


@pytest.mark.unit
def test_stack_limit_drops_oldest() -> None:
    """limit=3, push 4 masks — the 4th undo returns None (oldest dropped)."""
    history = HistoryManager(limit=3)
    history.push_mask_state(_painted_mask(5))
    history.push_mask_state(_painted_mask(10))
    history.push_mask_state(_painted_mask(15))
    history.push_mask_state(_painted_mask(20))

    cur = _painted_mask(25)
    # 3 undos possible (the 4th push dropped the 1st/oldest entry).
    assert history.pop_mask_undo(cur) is not None
    assert history.pop_mask_undo(cur) is not None
    assert history.pop_mask_undo(cur) is not None
    # 4th undo: stack is empty.
    assert history.pop_mask_undo(cur) is None


@pytest.mark.unit
def test_clear_resets_all() -> None:
    """After pushes + clear, all four can_* flags are False."""
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(5))
    history.push_image_action(0, 0, np.zeros((4, 4, 3), dtype=np.uint8))

    assert history.can_undo_mask()
    assert history.can_undo_image()

    history.clear()
    assert not history.can_undo_mask()
    assert not history.can_redo_mask()
    assert not history.can_undo_image()
    assert not history.can_redo_image()


@pytest.mark.unit
def test_mask_snapshot_is_copied() -> None:
    """Push .copy()-detaches: mutating the original does NOT affect the stored snapshot.

    RESEARCH Pitfall 2 regression guard for the push path.
    """
    history = HistoryManager(limit=20)
    mask = _transparent_mask(64)
    history.push_mask_state(mask)

    # Mutate the original mask in place (simulating the live canvas mask being
    # re-painted after the snapshot was taken).
    mask.fill(QColor(0, 255, 0, 255).rgba())

    # Undo with a different current mask — the returned snapshot must NOT reflect
    # the green mutation; it must be the original transparent state.
    cur = _painted_mask(40)
    prev = history.pop_mask_undo(cur)
    assert prev is not None
    # The snapshot pixel (4, 4) was transparent when pushed; the live mask was
    # since filled green. The snapshot must still be transparent (alpha == 0).
    assert prev.pixelColor(4, 4).alpha() == 0


@pytest.mark.unit
def test_mask_pop_returns_copy() -> None:
    """Pop .copy()-detaches: mutating the returned snapshot does NOT affect the internal list.

    RESEARCH Pitfall 2 regression guard for the pop path.

    Setup: push m1. pop_mask_undo returns m1.copy() and stashes current.copy()
    into the REDO stack. We mutate the returned snapshot (the caller now holds
    an alias of m1.copy()). Then we pop_mask_redo — the REDO entry (current)
    must be UNAFFECTED by our mutation of the popped snapshot, proving the
    returned snapshot was detached from BOTH the internal undo list AND the
    redo stash.
    """
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(20))

    cur = _painted_mask(40)
    popped = history.pop_mask_undo(cur)
    assert popped is not None

    # Mutate the popped snapshot in place — fill with blue.
    popped.fill(QColor(0, 0, 255, 255).rgba())

    # pop_mask_redo returns the redo stash (cur.copy()). It must NOT have the
    # blue mutation (it would only be blue if the redo stash aliased `popped`).
    redo = history.pop_mask_redo(_painted_mask(40))
    assert redo is not None
    blue = QColor(0, 0, 255, 255)
    assert redo.pixelColor(0, 0) != blue


@pytest.mark.unit
def test_can_undo_flags() -> None:
    """can_undo_mask/can_undo_image track stack emptiness after each push/pop."""
    history = HistoryManager(limit=20)

    assert not history.can_undo_mask()
    assert not history.can_redo_mask()
    assert not history.can_undo_image()
    assert not history.can_redo_image()

    history.push_mask_state(_painted_mask(5))
    assert history.can_undo_mask()
    assert not history.can_redo_mask()

    cur = _painted_mask(10)
    history.pop_mask_undo(cur)
    assert not history.can_undo_mask()
    assert history.can_redo_mask()

    history.push_image_action(0, 0, np.zeros((4, 4, 3), dtype=np.uint8))
    assert history.can_undo_image()
    assert not history.can_redo_image()

    current = np.zeros((100, 100, 3), dtype=np.uint8)
    history.pop_image_undo(current)
    assert not history.can_undo_image()
    assert history.can_redo_image()


# ---------------------------------------------------------------------------
# Task 2 — GUI wiring (MainWindow + EditorCanvas + HistoryManager)
# ---------------------------------------------------------------------------


def _make_window(qtbot, tmp_path) -> MainWindow:
    """Build a MainWindow wired to a ProfileManager in tmp_path."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _open_page(window: MainWindow, tmp_path: Path, size: int = 32) -> Path:
    """Open a solid-white page so the canvas has an image + initialized mask."""
    img_path = tmp_path / "page.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    return img_path


def _paint_brush_dot(canvas: EditorCanvas, x: int, y: int, size: int = 8) -> None:
    """Paint a brush dot at scene (x, y) directly via paint_mask_stroke.

    Bypasses the mouse-event path (which would also fire — we want a direct,
    deterministic mutation followed by an explicit mask_modified emission so
    the MainWindow._on_mask_modified hook fires).
    """
    mask = canvas.get_mask()
    assert mask is not None
    p = QPointF(x, y)
    paint_mask_stroke(mask, p, p, size, eraser=False)
    canvas.update_mask_display()
    canvas.mask_modified.emit()


def _paint_brush_stroke(
    canvas: EditorCanvas, x: int, y: int, size: int = 12, length: int = 16
) -> None:
    """Paint a genuinely-opaque two-point brush stroke centred at (x, y).

    Plan 03-08: the single-point ``_paint_brush_dot`` (p1 == p2) draws a
    degenerate line that renders ZERO opaque pixels on this Qt build, so it
    cannot distinguish a "stroked" mask from a clean baseline. The mask-undo-
    stuck regression tests need a stroke with measurable opaque content, so
    they paint a real two-point segment (round-cap caps fill a measurable
    disc). Fires ``mask_modified`` so the ``_on_mask_modified`` hook runs.
    """
    mask = canvas.get_mask()
    assert mask is not None
    p1 = QPointF(x - length / 2, y)
    p2 = QPointF(x + length / 2, y)
    paint_mask_stroke(mask, p1, p2, size, eraser=False)
    canvas.update_mask_display()
    canvas.mask_modified.emit()


@pytest.mark.gui
def test_mask_modified_pushes_to_history(qtbot, tmp_path) -> None:
    """A completed brush stroke pushes a snapshot onto the mask undo stack."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    assert not window.history.can_undo_mask()

    _paint_brush_dot(window.canvas, 10, 10, size=8)
    assert window.history.can_undo_mask()

    _paint_brush_dot(window.canvas, 20, 20, size=8)
    _paint_brush_dot(window.canvas, 5, 5, size=8)
    # After 3 strokes the undo stack holds 3 snapshots.
    assert window.history.can_undo_mask()


@pytest.mark.gui
def test_undo_mask_applies_snapshot(qtbot, tmp_path) -> None:
    """Unified Ctrl+Z applies the prior mask snapshot; a 3rd undo is a no-op.

    Surface 13 (plan 03-05): the unified handler routes a 'mask' kind pop to
    apply_undo_mask. Same underlying behavior as Phase 1's Alt+Z path.
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)

    # Paint 2 distinct strokes; capture the mask state after each.
    _paint_brush_dot(window.canvas, 10, 10, size=8)
    state_after_1 = window.canvas.get_mask().copy()
    _paint_brush_dot(window.canvas, 20, 20, size=8)

    # Undo once: the mask should now match state_after_1 (the 2nd stroke gone).
    window.on_undo()
    cur = window.canvas.get_mask()
    assert cur is not None
    assert cur.pixelColor(20, 20).alpha() == state_after_1.pixelColor(20, 20).alpha()

    # Undo again: should be transparent (the pre-stroke state).
    window.on_undo()
    cur = window.canvas.get_mask()
    assert cur is not None
    assert cur.pixelColor(10, 10).alpha() == 0

    # 3rd undo: no-op (stack empty + button disabled).
    window.on_undo()
    assert not window.history.can_undo_mask()


@pytest.mark.gui
def test_redo_mask_replays(qtbot, tmp_path) -> None:
    """After 2 undos, unified Ctrl+Shift+Z replays strokes; 3rd redo is a no-op."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    _paint_brush_dot(window.canvas, 10, 10, size=8)
    _paint_brush_dot(window.canvas, 20, 20, size=8)

    window.on_undo()
    window.on_undo()
    assert window.history.can_redo_mask()

    # Redo: 1st replay returns the 1st-pushed state's mask (transparent),
    # 2nd replay returns the 1st-stroke mask, 3rd is a no-op.
    window.on_redo()
    assert window.history.can_redo_mask()
    window.on_redo()
    assert not window.history.can_redo_mask()

    # 3rd redo is a no-op.
    window.on_redo()
    assert not window.history.can_redo_mask()


@pytest.mark.gui
def test_undo_image_applies_patch(qtbot, tmp_path) -> None:
    """Unified Ctrl+Z restores the pre-inpaint image region.

    Surface 13 (plan 03-05): the unified handler routes an 'image' kind pop to
    apply_undo_image. Same behavior as Phase 1's Ctrl+Z image-undo path.
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=16)

    # Simulate an inpaint: capture the pre-edit patch, then push it.
    pre_patch = window.canvas.get_image_numpy()[2:6, 2:6].copy()
    window.history.push_image_action(2, 2, pre_patch)
    assert window.history.can_undo_image()

    # Modify the canvas image's region (simulating the inpaint).
    current = window.canvas.get_image_numpy()
    current[2:6, 2:6] = 50
    window.canvas.set_image_from_numpy(current)

    # Undo: the region should be restored to pre_patch (white = 255).
    window.on_undo()
    restored = window.canvas.get_image_numpy()
    assert np.array_equal(restored[2:6, 2:6], pre_patch)
    assert not window.history.can_undo_image()


@pytest.mark.gui
def test_redo_image_replays(qtbot, tmp_path) -> None:
    """After an image undo, unified Ctrl+Shift+Z re-applies the inpainted patch."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=16)

    pre_patch = window.canvas.get_image_numpy()[2:6, 2:6].copy()
    window.history.push_image_action(2, 2, pre_patch)

    current = window.canvas.get_image_numpy()
    current[2:6, 2:6] = 50
    window.canvas.set_image_from_numpy(current)

    window.on_undo()
    assert window.history.can_redo_image()

    # Redo: the region should return to value 50 (the post-edit state).
    window.on_redo()
    after_redo = window.canvas.get_image_numpy()
    assert np.all(after_redo[2:6, 2:6] == 50)
    assert not window.history.can_redo_image()


@pytest.mark.gui
def test_new_edit_clears_redo(qtbot, tmp_path) -> None:
    """A new mask edit after an undo clears the redo branch."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    _paint_brush_dot(window.canvas, 10, 10, size=8)
    _paint_brush_dot(window.canvas, 20, 20, size=8)

    window.on_undo()
    assert window.history.can_redo_mask()

    # Paint a new stroke — the redo branch must clear.
    _paint_brush_dot(window.canvas, 5, 5, size=8)
    assert not window.history.can_redo_mask()


@pytest.mark.gui
def test_toolbar_collapsed_to_two_buttons(qtbot, tmp_path) -> None:
    """Surface 13 (plan 03-05): the toolbar shows exactly 2 undo buttons
    ([Undo][Redo]) — the Phase 1 image/mask pair + divider are gone."""
    window = _make_window(qtbot, tmp_path)
    # Collect the toolbar's actions in order.
    actions = window.toolbar.actions()

    # The two unified undo/redo actions are present.
    idx_undo = actions.index(window.action_undo)
    idx_redo = actions.index(window.action_redo)
    # Undo precedes Redo.
    assert idx_undo < idx_redo

    # The 4 Phase 1 actions are gone (no attribute, not in the toolbar).
    for name in ("action_undo_image", "action_redo_image",
                 "action_undo_mask", "action_redo_mask"):
        assert not hasattr(window, name), f"{name} must be removed (Surface 13)"


@pytest.mark.gui
def test_buttons_disabled_when_stack_empty(qtbot, tmp_path) -> None:
    """With empty stacks both unified undo/redo actions are disabled."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=16)

    assert not window.action_undo.isEnabled()
    assert not window.action_redo.isEnabled()

    # Paint a stroke -> Undo enables (union flag includes the mask stack).
    _paint_brush_dot(window.canvas, 8, 8, size=6)
    assert window.action_undo.isEnabled()
    assert not window.action_redo.isEnabled()

    # Undo -> Redo enables, Undo disables.
    window.on_undo()
    assert not window.action_undo.isEnabled()
    assert window.action_redo.isEnabled()


@pytest.mark.gui
def test_page_change_resets_history(qtbot, tmp_path) -> None:
    """Selecting a different page resets the HistoryManager."""
    window = _make_window(qtbot, tmp_path)
    # Open two pages.
    p1 = tmp_path / "page1.png"
    p2 = tmp_path / "page2.png"
    for p, fill in ((p1, QColor(255, 255, 255)), (p2, QColor(200, 200, 200))):
        img = QImage(32, 32, QImage.Format.Format_RGB32)
        img.fill(fill)
        img.save(str(p))
    window._set_pages([p1, p2])

    # Paint on page 1.
    _paint_brush_dot(window.canvas, 10, 10, size=8)
    assert window.history.can_undo_mask()

    # Switch to page 2 — history resets.
    window.on_page_selected(p2)
    assert not window.history.can_undo_mask()
    assert not window.history.can_redo_mask()


@pytest.mark.gui
def test_shortcuts_wired(qtbot, tmp_path) -> None:
    """Surface 13 (plan 03-05): only Ctrl+Z / Ctrl+Shift+Z QShortcuts exist
    (the unified pair). Alt+Z / Alt+Shift+Z are GONE (subsumed)."""
    from PySide6.QtGui import QShortcut

    window = _make_window(qtbot, tmp_path)
    # Collect all QShortcut children of the MainWindow.
    shortcuts = window.findChildren(QShortcut)
    key_strings = {s.key().toString() for s in shortcuts}
    assert "Ctrl+Z" in key_strings
    assert "Ctrl+Shift+Z" in key_strings
    # The legacy mask-undo shortcuts must NOT be present.
    assert "Alt+Z" not in key_strings
    assert "Alt+Shift+Z" not in key_strings


@pytest.mark.gui
def test_no_ambiguous_shortcut_overload(qtbot, tmp_path) -> None:
    """CR-14: undo/redo QActions must NOT carry their own setShortcut.

    Surface 13 (plan 03-05): the 2 unified key sequences are registered once
    each as QShortcut in _wire_history_actions (the focus-robust path). If the
    QActions also carry setShortcut, Qt emits
    ``QAction::event: Ambiguous shortcut overload`` on every keypress. Assert
    each QAction's shortcut is empty AND that each sequence appears on exactly
    one QShortcut (no duplicates).
    """
    window = _make_window(qtbot, tmp_path)

    # None of the 2 unified undo/redo QActions should carry a shortcut binding.
    for action in (window.action_undo, window.action_redo):
        assert action.shortcut().toString() == "", (
            f"{action.text()} carries a duplicate setShortcut; this triggers "
            "Qt's Ambiguous shortcut overload warning (CR-14)"
        )

    # Each sequence appears on exactly one QShortcut (no duplicates).
    from collections import Counter

    from PySide6.QtGui import QShortcut

    seqs = [
        s.key().toString()
        for s in window.findChildren(QShortcut)
        if s.key().toString() in ("Ctrl+Z", "Ctrl+Shift+Z")
    ]
    counts = Counter(seqs)
    dupes = {k: v for k, v in counts.items() if v > 1}
    assert not dupes, f"duplicate QShortcut registrations cause ambiguity: {dupes}"


@pytest.mark.gui
def test_undo_does_not_repush(qtbot, tmp_path) -> None:
    """apply_undo_mask (via the unified handler) does NOT emit mask_modified."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    _paint_brush_dot(window.canvas, 10, 10, size=8)

    # The undo stack should have exactly 1 entry now.
    assert window.history.can_undo_mask()

    # Apply undo via the unified handler; assert mask_modified is NOT emitted.
    with qtbot.assertNotEmitted(window.canvas.mask_modified):
        window.on_undo()

    # The undo stack should now be EMPTY (the undo popped the entry; the
    # current was stashed into redo; no re-push happened).
    assert not window.history.can_undo_mask()
    assert window.history.can_redo_mask()


# ---------------------------------------------------------------------------
# Plan 03-08 — mask-undo-stuck (UAT test 3 addendum, FLOW-02 regression) +
# WR-01 null-mask crash guard. Three @pytest.mark.gui tests (the multi-store
# unified-undo path exercises QImage construction + cross-store pop, so the
# gui marker / qtbot QApplication is required; the GREEN verify references
# node-IDs explicitly rather than -m gui because test_mask_editor is 100% unit).
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_mask_stroke_stuck_after_inpaint_undo_symptom(qtbot, tmp_path) -> None:
    """UAT test 3 addendum (FLOW-02 regression): after inpainting, the brush
    mask "comes back on the 2nd Ctrl+Z and no matter how much Ctrl+Z it never
    goes away again."

    This is the SYMPTOM reproduction — it drives the mask push hook
    (``_on_mask_modified``) PLUS an image push through the real multi-store
    unified ``on_undo`` path, verbatim from 03-UAT.md Gap 4 (detect -> stroke ->
    inpaint -> repeated Ctrl+Z). It uses a real MainWindow + canvas +
    HistoryManager (via the qtbot QApplication) so the ``.copy()`` detachment
    path AND the baseline-seeding hook are exercised — the mechanism the plan-08
    fix addresses lives in ``_on_mask_modified``, not in bare
    ``push_mask_state`` (a standalone push has no notion of "first stroke of a
    session", so a HistoryManager-only test could not be turned GREEN by the
    plan's documented fix location).

    DESIRED (post-fix) behaviour: the FIRST Ctrl+Z pops the image (inpaint
    undone, ordering by stamp); the SECOND Ctrl+Z pops the mask and the canvas
    mask becomes clean/empty (the stroke removed — the seeded clean baseline is
    restored); the THIRD Ctrl+Z is a no-op (all stacks empty). Repeated undo
    never re-materializes the stroke.

    RED failure mode (CONFIRMED by a live probe against pop_mask_undo semantics
    — history_manager.py:150-154, and against the bare-history stack the
    ``test_first_mask_stroke_undoable_to_baseline`` mirror below pins): with
    after-state-only push and NO baseline seed, the single-entry mask stack
    ``[stroked]`` is popped by undo#2 and ``pop_mask_undo`` returns
    ``stroked.copy()`` — i.e. the STROKED AFTER-STATE itself. So the stroke
    SURVIVES undo#2, and undo#3 then no-ops because the stack is now empty —
    the stroke was never removed at all. The plan's checker corrected an
    earlier round-1 hypothesis that claimed "returns None or leaves the
    stroke" — that is FALSE; the actual RED behaviour is "returns the stroked
    after-state, so the stroke persists and a further undo has nothing below
    it." Assert that exact outcome below (the canvas mask keeps its stroke
    content after undo #2).
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=64)
    history = window.history

    # Paint exactly ONE mask stroke. _paint_brush_stroke fires mask_modified ->
    # _on_mask_modified -> (post-fix) seed clean baseline, then push after-state.
    _paint_brush_stroke(window.canvas, 32, 32, size=12)
    stroked_state = window.canvas.get_mask()
    assert stroked_state is not None
    stroke_pixels = _opaque_pixel_count(stroked_state)
    assert stroke_pixels > 0, "fixture must paint a real stroke"

    # The inpaint — pre_patch is a small zeros array (matches
    # test_undo_image_applies_patch). Pushed directly onto the image stack so
    # the cross-store stamp ordering is exercised (image stamp > mask stamp).
    history.push_image_action(0, 0, np.zeros((2, 2, 3), dtype=np.uint8))

    # Undo #1: pops the most-recent entry by stamp -> the image (inpaint).
    window.on_undo()
    # The mask must be UNCHANGED by undo #1 (only the image popped).
    after_undo1 = window.canvas.get_mask()
    assert after_undo1 is not None
    assert _opaque_pixel_count(after_undo1) == stroke_pixels, (
        "undo #1 (image) must leave the mask stroke untouched"
    )

    # Undo #2: pops the mask stack. DESIRED (post-fix): restores the clean
    # baseline (stroke removed). RED (pre-fix): the canvas mask kept its
    # stroke content (the stroked after-state was re-applied).
    window.on_undo()
    after_undo2 = window.canvas.get_mask()
    assert after_undo2 is not None
    assert _opaque_pixel_count(after_undo2) == 0, (
        "undo #2 must restore the CLEAN baseline (the stroke removed), not "
        "leave the stroked after-state on the canvas"
    )

    # Undo #3: all stacks empty -> no-op (no further state to restore, and the
    # stroke must NOT re-materialize on repeated undo).
    window.on_undo()
    after_undo3 = window.canvas.get_mask()
    assert after_undo3 is not None
    assert _opaque_pixel_count(after_undo3) == 0, (
        "a 3rd undo must not re-materialize the stroke (no re-push loop)"
    )
    assert not history.can_undo()


@pytest.mark.gui
def test_first_mask_stroke_undoable_to_baseline(qtbot, tmp_path) -> None:
    """MECHANISM guard for the one-behind fix, isolated at the mask layer.

    DISTINCT from the symptom test above: this isolates the mask-layer
    baseline-seeding mechanism WITHOUT the image store interleaving. The fix
    lives in ``_on_mask_modified`` (the mask push hook), so this test drives
    that hook directly via a single brush stroke and asserts a single ``on_undo``
    removes it back to a clean canvas.

    WHY fixing this mechanism closes the symptom: the symptom (Test A) is the
    cross-store manifestation of the same one-behind defect — the mask side
    pushed ONLY the after-state with no baseline seed, so the first stroke of a
    session had nothing below it to restore to. Seeding the baseline on the
    first stroke makes undo #2 of Test A land on the clean baseline instead of
    the stroked after-state.

    DESIRED (post-fix): one stroke, one ``on_undo`` -> the canvas mask is clean
    (the stroke removed). RED (pre-fix): a single ``on_undo`` after one stroke
    no-ops or leaves the stroke (the after-state-only stack pops to empty with
    nothing to restore; the live canvas mask still carries the stroke) — pinned
    by the bare-history mirror assertion below.
    """
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=64)

    # Paint exactly ONE stroke (the first of the per-page session).
    _paint_brush_stroke(window.canvas, 32, 32, size=12)
    stroke_pixels = _opaque_pixel_count(window.canvas.get_mask())
    assert stroke_pixels > 0

    # Mirror pin at the bare-history layer: a single after-state-only push (the
    # PRE-fix behaviour) pops to empty with nothing to restore to.
    pin = HistoryManager(limit=20)
    pin.push_mask_state(_opaque_stroked_mask(64, brush_size=12))
    pin_result = pin.undo(_opaque_stroked_mask(64, brush_size=12),
                          np.zeros((64, 64, 3), dtype=np.uint8), [])
    assert pin_result is not None and pin_result[0][0] == "mask"
    assert _opaque_pixel_count(pin_result[0][1]) > 0, (
        "pre-fix pin: a bare after-state-only push returns the stroked "
        "after-state on undo (the one-behind defect the GUI hook seeds around)"
    )

    # The fix: the GUI hook seeds a clean baseline, so one on_undo removes the
    # first stroke back to a clean canvas.
    window.on_undo()
    after_undo = window.canvas.get_mask()
    assert after_undo is not None
    assert _opaque_pixel_count(after_undo) == 0, (
        "the first stroke of a session must undo back to a clean baseline "
        "(the stroke removed), not leave the stroked after-state"
    )
    assert not window.history.can_undo_mask()


@pytest.mark.gui
def test_pop_mask_undo_with_null_current_mask_does_not_crash(qtbot) -> None:
    """WR-01 (03-REVIEW.md): ``pop_mask_undo`` does ``current_mask.copy()``
    unconditionally (history_manager.py:153). When the unified ``undo`` is
    called with ``current_mask=None`` (which ``_current_undo_state`` returns
    whenever ``canvas.has_mask()`` is False — main_window.py:1120) while the
    mask undo stack is non-empty, it crashes with
    ``AttributeError: 'NoneType' object has no attribute 'copy'``.

    DESIRED (post-fix): returns ("mask", <qimage>) WITHOUT raising. RED
    (today): crashes (CONFIRMED by live probe).
    """
    history = HistoryManager(limit=20)
    history.push_mask_state(_opaque_stroked_mask(64, brush_size=10))

    # Undo with a null current mask must not raise AttributeError. The popped
    # previous mask is still returned (there is just no current to swap into
    # the redo branch).
    result = history.undo(
        current_mask=None,
        current_img=np.zeros((4, 4, 3), dtype=np.uint8),
        current_boxes=[],
    )
    assert result is not None
    assert result[0][0] == "mask"
    assert result[0][1] is not None


# ---------------------------------------------------------------------------
# Plan 05-04 — geometry-op undo record (push_geometry_state, stamp-shared
# triple push — PROJ-04 / UI-SPEC surface 28 "one press per op, never two").
# RESEARCH Pattern 2: push_geometry_state stamps IMAGE+MASK+BOXES with ONE
# monotonic stamp so a single unified undo pops all three together. The
# per-type pop methods stay untouched; the pop-all-with-max-stamp lives in
# undo()/redo() (Task 2's tests).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_geometry_push_stamps_all_stores() -> None:
    """push_geometry_state stamps IMAGE+MASK+BOXES with ONE shared stamp.

    The shared tail stamp is what makes one Ctrl+Z reverse the whole op
    (undo() pops every store whose tail stamp equals the max). The image side
    is a FULL-FRAME patch at (0, 0) (RESEARCH Pattern 2 — pop_image_undo's
    existing machinery handles it). The next ordinary push must get a HIGHER
    stamp (strict monotonicity, Pitfall 4).
    """
    history = HistoryManager(limit=20)
    patch = np.zeros((8, 8, 3), dtype=np.uint8)
    mask = _transparent_mask(8)
    boxes = [(1, "detected", {"text": "a"})]
    history.push_geometry_state(patch, mask, boxes)

    image_stamp = history._image_undo[-1][0]
    # ONE stamp across all three stores.
    assert image_stamp == history._mask_undo[-1][0]
    assert image_stamp == history._boxes_undo[-1][0]
    # The image entry is a full-frame patch at (0, 0).
    x, y, stored = history._image_undo[-1][1]
    assert (x, y) == (0, 0)
    assert stored.shape == (8, 8, 3)

    # The next ordinary push stamps strictly higher.
    history.push_mask_state(_transparent_mask(8))
    assert history._mask_undo[-1][0] > image_stamp


@pytest.mark.unit
def test_geometry_push_omits_none_stores() -> None:
    """mask_qimage=None / boxes=None omit that store (levels pushes image-only).

    The levels op is geometry-free (D-15) — push_geometry_state(patch) must
    touch ONLY the image store so a levels undo is an ordinary single-store
    image pop.
    """
    history = HistoryManager(limit=20)
    history.push_geometry_state(np.zeros((8, 8, 3), dtype=np.uint8))
    assert len(history._image_undo) == 1
    assert len(history._mask_undo) == 0
    assert len(history._boxes_undo) == 0

    # mask present, boxes omitted — only image + mask touched.
    history2 = HistoryManager(limit=20)
    history2.push_geometry_state(
        np.zeros((8, 8, 3), dtype=np.uint8), _transparent_mask(8)
    )
    assert len(history2._image_undo) == 1
    assert len(history2._mask_undo) == 1
    assert len(history2._boxes_undo) == 0


@pytest.mark.unit
def test_geometry_push_clears_redo() -> None:
    """A geometry push invalidates EVERY touched store's redo branch."""
    history = HistoryManager(limit=20)
    history.push_mask_state(_transparent_mask(8))
    history.push_image_action(0, 0, np.zeros((4, 4, 3), dtype=np.uint8))
    history.push_boxes_state([(1, "detected", None)])

    # Pop each once so all three redo branches are populated.
    history.pop_mask_undo(_transparent_mask(8))
    history.pop_image_undo(np.zeros((8, 8, 3), dtype=np.uint8))
    history.pop_boxes_undo([])
    assert history.can_redo_mask()
    assert history.can_redo_image()
    assert history.can_redo_boxes()

    history.push_geometry_state(
        np.zeros((8, 8, 3), dtype=np.uint8),
        _transparent_mask(8),
        [(1, "detected", None)],
    )
    assert not history.can_redo_mask()
    assert not history.can_redo_image()
    assert not history.can_redo_boxes()


@pytest.mark.unit
def test_geometry_push_detaches_patch() -> None:
    """T-05-11 (Pitfall 2/3): mutating the caller's array/mask/boxes list after
    push does NOT change the stored entry (the push-side .copy() /
    _materialize_snapshot discipline).

    Regression guard for RESEARCH Pattern 2's image .copy() + mask .copy()
    on the geometry push path.
    """
    history = HistoryManager(limit=20)
    patch = np.zeros((8, 8, 3), dtype=np.uint8)
    mask = _transparent_mask(8)
    boxes = [(1, "detected", {"text": "original"})]
    history.push_geometry_state(patch, mask, boxes)

    # Mutate the caller's array, mask, and boxes list in place.
    patch.fill(255)
    mask.fill(QColor(0, 255, 0, 255).rgba())
    boxes.append((2, "manual", {"text": "new"}))
    boxes[0][2]["text"] = "mutated"

    _x, _y, stored = history._image_undo[-1][1]
    assert np.array_equal(stored, np.zeros((8, 8, 3), dtype=np.uint8))
    # The stored mask snapshot is still fully transparent.
    assert history._mask_undo[-1][1].pixelColor(0, 0).alpha() == 0
    # The stored boxes snapshot ignored the append AND the payload mutation.
    stored_boxes = history._boxes_undo[-1][1]
    assert len(stored_boxes) == 1
    assert stored_boxes[0][2] == {"text": "original"}


# ---------------------------------------------------------------------------
# Plan 05-04 Task 2 — undo()/redo() pop-all-with-max-stamp returning LISTS.
# The geometry record pops as a multi-kind list so ONE Ctrl+Z reverses the
# whole op (PROJ-04 / UI-SPEC surface 28); ordinary single-store edits pop as
# one-element lists (unchanged Phase 3 semantics, return shape widened).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_geometry_undo_reverses_all_three() -> None:
    """ONE undo() pops image+mask+boxes together for a geometry record.

    Push a geometry record (image+mask+boxes share one stamp), then a second
    ORDINARY image push; undo #1 returns the ordinary image entry alone (a
    one-element list); undo #2 returns ALL THREE geometry entries (mask,
    image, boxes order); undo #3 returns [].
    """
    history = HistoryManager(limit=20)
    pre_patch = np.zeros((8, 8, 3), dtype=np.uint8)
    pre_mask = _transparent_mask(8)
    pre_boxes = [(1, "detected", {"text": "a"})]
    history.push_geometry_state(pre_patch, pre_mask, pre_boxes)
    history.push_image_action(2, 2, np.zeros((2, 2, 3), dtype=np.uint8))

    current = np.full((8, 8, 3), 100, dtype=np.uint8)
    cur_mask = _painted_mask(20)

    # Undo #1: the ordinary image push — exactly one entry.
    r1 = history.undo(cur_mask, current, [])
    assert len(r1) == 1 and r1[0][0] == "image"

    # Undo #2: the geometry record — ALL THREE entries (mask, image, boxes);
    # the image side is the full-frame pre-op patch at (0, 0).
    r2 = history.undo(cur_mask, current, [])
    assert [kind for kind, _ in r2] == ["mask", "image", "boxes"]
    img_value = dict(r2)["image"]
    gx, gy, gpatch = img_value
    assert (gx, gy) == (0, 0)
    assert np.array_equal(gpatch, pre_patch)

    # Undo #3: everything popped — empty list (was None pre-plan).
    assert history.undo(cur_mask, current, []) == []


@pytest.mark.unit
def test_geometry_redo_restores_all_three() -> None:
    """redo() mirrors undo() over the redo stores: ONE redo restores the
    geometry triple (the group's redo stashes share one stamp).

    After undoing the geometry record (undo #2), the three redo stashes must
    carry a single shared stamp so a single redo() pops all three together —
    the mirror of the one-press undo contract.
    """
    history = HistoryManager(limit=20)
    pre_patch = np.zeros((8, 8, 3), dtype=np.uint8)
    pre_mask = _transparent_mask(8)
    pre_boxes = [(1, "detected", None)]
    history.push_geometry_state(pre_patch, pre_mask, pre_boxes)
    history.push_image_action(2, 2, np.zeros((2, 2, 3), dtype=np.uint8))

    current = np.full((8, 8, 3), 100, dtype=np.uint8)
    cur_mask = _painted_mask(20)

    history.undo(cur_mask, current, [])  # ordinary image entry
    history.undo(cur_mask, current, [])  # geometry triple

    # Redo #1: the geometry triple (undone last -> redone first).
    r1 = history.redo(cur_mask, current, [])
    assert [kind for kind, _ in r1] == ["mask", "image", "boxes"]

    # Redo #2: the ordinary image entry alone.
    r2 = history.redo(cur_mask, current, [])
    assert len(r2) == 1 and r2[0][0] == "image"

    # Redo #3: everything redone.
    assert history.redo(cur_mask, current, []) == []


@pytest.mark.unit
def test_undo_returns_single_element_list() -> None:
    """Ordinary single-store pushes undo() to a ONE-element list [(kind, value)].

    The return-shape contract (plan 05-04): undo()/redo() always return a
    list; a lone ordinary push yields a list of exactly one (kind, value)
    pair, preserving the Phase 3 unified pop for ordinary edits.
    """
    history = HistoryManager(limit=20)
    history.push_mask_state(_painted_mask(10))

    cur = _painted_mask(20)
    result = history.undo(cur, np.zeros((8, 8, 3), dtype=np.uint8), [])
    assert isinstance(result, list)
    assert len(result) == 1
    kind, value = result[0]
    assert kind == "mask"
    assert value is not None



# ---------------------------------------------------------------------------
# quick-260828-l3l: Restore stroke -> undo/dirty/current_image write-back
# ---------------------------------------------------------------------------


def _restore_drag(canvas: EditorCanvas, x0: float, y0: float, x1: float, y1: float) -> None:
    """Press-move-release a Restore stroke from (x0, y0) to (x1, y1).

    Viewport coords are mapped from the desired scene point (QGraphicsView
    centers the scene — the same discipline as test_gui_canvas._press).
    """
    from PySide6.QtCore import QEvent, QPointF as _QPointF
    from PySide6.QtGui import QMouseEvent as _QMouseEvent

    def _press(sx: float, sy: float) -> _QMouseEvent:
        vp = canvas.mapFromScene(_QPointF(sx, sy))
        return _QMouseEvent(
            QEvent.Type.MouseButtonPress,
            _QPointF(vp),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def _move(sx: float, sy: float) -> _QMouseEvent:
        vp = canvas.mapFromScene(_QPointF(sx, sy))
        return _QMouseEvent(
            QEvent.Type.MouseMove,
            _QPointF(vp),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def _release(sx: float, sy: float) -> _QMouseEvent:
        vp = canvas.mapFromScene(_QPointF(sx, sy))
        return _QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            _QPointF(vp),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    canvas.mousePressEvent(_press(x0, y0))
    canvas.mouseMoveEvent(_move(x1, y1))
    canvas.mouseReleaseEvent(_release(x1, y1))


@pytest.mark.gui
def test_restore_stroke_undoes_syncs_current_image_and_dirty(qtbot, tmp_path) -> None:
    """A Restore stroke on a MainWindow: exactly ONE bbox-patch image-undo
    entry, current_image synced to the post-stroke display, session dirty
    (title *), Ctrl+Z reverts the stroke, and `_original_image_numpy` is
    UNCHANGED (D-14 regression guard). No mask-undo entry is pushed either —
    restore never touches the mask planes."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    canvas = window.canvas
    idx = window._current_page_index()
    assert idx is not None

    # Seed the baseline (same setup as Task 1's stamps test): the D-06 slot
    # captures the displayed pixels via the capture-when-None gate.
    white = np.full((32, 32, 3), 255, dtype=np.uint8)
    canvas.set_image_from_numpy(white)
    baseline_before = canvas._original_image_numpy
    assert baseline_before is not None
    assert not window.windowTitle().endswith("*")  # clean before the stroke

    # Simulate a mangled inpaint: patch the display region to 50.
    current = canvas.get_image_numpy()
    current[10:20, 10:20] = 50
    canvas.set_image_from_numpy(current, bbox=(10, 10, 10, 10))
    pre_display = canvas.get_image_numpy()

    # A real mouse-event Restore stroke over the patch (brush 8 -> r=4).
    canvas.set_tool(ToolMode.RESTORE)
    canvas.set_brush_size(8)
    _restore_drag(canvas, 12, 15, 18, 15)
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()

    # Pixels: stroked region back to the baseline (255); unstroked mutated
    # pixels keep 50 (row 10 is outside the disc bbox entirely).
    post = canvas.get_image_numpy()
    assert np.all(post[15, 11:20] == 255)
    assert np.all(post[10, 12:18] == 50)

    # (b) current_image equals the post-stroke display (navigation/save embed).
    assert window.image_files[idx].current_image is not None
    assert np.array_equal(window.image_files[idx].current_image, post)

    # (c) the session is dirty (title carries the * suffix).
    assert window.windowTitle().endswith("*")

    # Zero mask-undo entries from the stroke (restore is pure pixel work).
    assert not window.history.can_undo_mask()

    # (a) exactly one image-undo entry whose patch is the pre-stroke region.
    assert window.history.can_undo_image()
    x, y, patch = window.history.pop_image_undo(post)
    h_p, w_p = patch.shape[:2]
    assert np.array_equal(patch, pre_display[y : y + h_p, x : x + w_p])
    assert not window.history.can_undo_image()

    # (d) applying the popped patch restores the pre-stroke pixels.
    canvas.apply_undo_image(x, y, patch)
    restored = canvas.get_image_numpy()
    assert np.array_equal(restored, pre_display)

    # D-14: the stroke never rebaselined the Show Original baseline.
    assert np.array_equal(canvas._original_image_numpy, baseline_before)

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
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.history_manager import HistoryManager  # noqa: E402
from manga_ai_studio.core.mask_editor import (  # noqa: E402
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
def test_mask_stroke_stuck_after_inpaint_undo_symptom(qtbot) -> None:
    """UAT test 3 addendum (FLOW-02 regression): after inpainting, the brush
    mask "comes back on the 2nd Ctrl+Z and no matter how much Ctrl+Z it never
    goes away again."

    This is the SYMPTOM reproduction — it drives the CURRENT (buggy) push
    pattern that ``_on_mask_modified`` uses today (after-state only, no baseline
    seed) through the real multi-store unified ``history.undo(...)`` path,
    verbatim from 03-UAT.md Gap 4 (detect -> stroke -> inpaint -> repeated
    Ctrl+Z). It uses a real HistoryManager + real transparent QImages (via the
    qtbot QApplication) so the ``.copy()`` detachment path is exercised.

    DESIRED (post-fix) behaviour: the FIRST undo pops the image (inpaint
    undone, ordering by stamp); the SECOND undo pops the mask and the returned
    mask equals ``base`` (the clean PRE-stroke baseline — the stroke removed);
    the THIRD undo returns None (all stacks empty). Repeated undo never
    re-materializes the stroke.

    RED failure mode (CONFIRMED by a live probe against pop_mask_undo semantics
    — history_manager.py:150-154): with after-state-only push and NO baseline
    seed, the single-entry mask stack ``[stroked]`` is popped by undo#2 and
    ``pop_mask_undo`` returns ``stroked.copy()`` — i.e. the STROKED AFTER-STATE
    itself. So the stroke SURVIVES undo#2 (``m != base``), and undo#3 then
    returns None because the stack is now empty — the stroke was never removed
    at all. The plan's checker corrected an earlier round-1 hypothesis that
    claimed "returns None or leaves the stroke" — that is FALSE; the actual
    RED behaviour is "returns the stroked after-state, so the stroke persists
    and a further undo has nothing below it." Assert that exact failure below.
    """
    history = HistoryManager(limit=20)
    base = _transparent_mask(64)
    stroked = _opaque_stroked_mask(64, brush_size=10)
    assert _opaque_pixel_count(stroked) > 0, "fixture must paint a real stroke"
    assert _opaque_pixel_count(base) == 0

    # Current buggy push pattern: after-state only, no pre-stroke baseline seed.
    history.push_mask_state(stroked)  # the mask stroke
    # The inpaint — pre_patch is a small zeros array (matches
    # test_undo_image_applies_patch). x,y == 0,0 for a clean cross-store stamp.
    history.push_image_action(0, 0, np.zeros((2, 2, 3), dtype=np.uint8))

    # The "current" mask after both pushes is the stroked after-state; the
    # current image is a fresh array.
    cur_mask = stroked
    cur_img = np.zeros((64, 64, 3), dtype=np.uint8)

    # Undo #1: pops the most-recent entry by stamp -> the image (inpaint).
    r1 = history.undo(cur_mask, cur_img, [])
    assert r1 is not None and r1[0] == "image"

    # Undo #2: pops the mask stack's only entry. DESIRED: returns the clean
    # baseline (the stroke removed). RED (today): returns the stroked
    # after-state itself.
    r2 = history.undo(cur_mask, cur_img, [])
    assert r2 is not None and r2[0] == "mask"
    popped_mask = r2[1]
    assert _opaque_pixel_count(popped_mask) == 0, (
        "undo #2 must return the CLEAN baseline (the stroke removed), not the "
        "stroked after-state"
    )

    # Undo #3: all stacks empty -> None (no further state to restore, and the
    # stroke must NOT re-materialize on repeated undo).
    r3 = history.undo(cur_mask, cur_img, [])
    assert r3 is None


@pytest.mark.gui
def test_first_mask_stroke_undoable_to_baseline(qtbot) -> None:
    """MECHANISM guard for the one-behind fix, isolated at the mask layer.

    DISTINCT from the symptom test above: this isolates the mask-layer
    baseline-seeding mechanism so the fix can be validated WITHOUT the image
    store interleaving. WHY fixing this mechanism closes the symptom: the
    symptom (Test A) is the cross-store manifestation of the same one-behind
    defect — the mask side pushes ONLY the after-state with no baseline seed,
    so the first stroke of a session has nothing below it to restore to.
    Seeding the baseline on the first stroke makes undo #2 of Test A land on
    the clean baseline instead of the stroked after-state.

    DESIRED (post-fix): ``history.undo`` on a single-entry mask stack returns
    ("mask", m) where m pixel-equals the clean baseline (the stroke removed).

    RED (today): returns ``stroked.copy()`` (the after-state) because there is
    no pre-stroke baseline on the stack (CONFIRMED by live probe — the single
    after-state entry is what gets popped). Document this exact failure mode,
    NOT "returns None".
    """
    history = HistoryManager(limit=20)
    base = _transparent_mask(64)
    stroked = _opaque_stroked_mask(64, brush_size=10)
    assert _opaque_pixel_count(stroked) > 0

    # Current buggy pattern: after-state only, no baseline seed.
    history.push_mask_state(stroked)

    dummy_img = np.zeros((64, 64, 3), dtype=np.uint8)
    result = history.undo(stroked, dummy_img, [])
    assert result is not None and result[0] == "mask"
    popped = result[1]
    assert _opaque_pixel_count(popped) == 0, (
        "the first stroke of a session must undo back to a clean baseline "
        "(the stroke removed), not the stroked after-state"
    )


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
    assert result[0] == "mask"
    assert result[1] is not None


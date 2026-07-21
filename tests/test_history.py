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
    """Alt+Z applies the prior mask snapshot; a 3rd undo is a no-op."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)

    # Paint 2 distinct strokes; capture the mask state after each.
    _paint_brush_dot(window.canvas, 10, 10, size=8)
    state_after_1 = window.canvas.get_mask().copy()
    _paint_brush_dot(window.canvas, 20, 20, size=8)

    # Undo once: the mask should now match state_after_1 (the 2nd stroke gone).
    window.on_undo_mask()
    cur = window.canvas.get_mask()
    assert cur is not None
    assert cur.pixelColor(20, 20).alpha() == state_after_1.pixelColor(20, 20).alpha()

    # Undo again: should be transparent (the pre-stroke state).
    window.on_undo_mask()
    cur = window.canvas.get_mask()
    assert cur is not None
    assert cur.pixelColor(10, 10).alpha() == 0

    # 3rd undo: no-op (stack empty + button disabled).
    window.on_undo_mask()
    assert not window.history.can_undo_mask()


@pytest.mark.gui
def test_redo_mask_replays(qtbot, tmp_path) -> None:
    """After 2 undos, Alt+Shift+Z replays strokes; a 3rd redo is a no-op."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    _paint_brush_dot(window.canvas, 10, 10, size=8)
    _paint_brush_dot(window.canvas, 20, 20, size=8)

    window.on_undo_mask()
    window.on_undo_mask()
    assert window.history.can_redo_mask()

    # Redo: 1st replay returns the 1st-pushed state's mask (transparent),
    # 2nd replay returns the 1st-stroke mask, 3rd is a no-op.
    window.on_redo_mask()
    assert window.history.can_redo_mask()
    window.on_redo_mask()
    assert not window.history.can_redo_mask()

    # 3rd redo is a no-op.
    window.on_redo_mask()
    assert not window.history.can_redo_mask()


@pytest.mark.gui
def test_undo_image_applies_patch(qtbot, tmp_path) -> None:
    """Ctrl+Z restores the pre-inpaint image region."""
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
    window.on_undo_image()
    restored = window.canvas.get_image_numpy()
    assert np.array_equal(restored[2:6, 2:6], pre_patch)
    assert not window.history.can_undo_image()


@pytest.mark.gui
def test_redo_image_replays(qtbot, tmp_path) -> None:
    """After an image undo, Ctrl+Shift+Z re-applies the inpainted patch."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=16)

    pre_patch = window.canvas.get_image_numpy()[2:6, 2:6].copy()
    window.history.push_image_action(2, 2, pre_patch)

    current = window.canvas.get_image_numpy()
    current[2:6, 2:6] = 50
    window.canvas.set_image_from_numpy(current)

    window.on_undo_image()
    assert window.history.can_redo_image()

    # Redo: the region should return to value 50 (the post-edit state).
    window.on_redo_image()
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

    window.on_undo_mask()
    assert window.history.can_redo_mask()

    # Paint a new stroke — the redo branch must clear.
    _paint_brush_dot(window.canvas, 5, 5, size=8)
    assert not window.history.can_redo_mask()


@pytest.mark.gui
def test_toolbar_two_pairs_with_divider(qtbot, tmp_path) -> None:
    """The toolbar shows [Undo Image][Redo Image] ‖ [Undo Mask][Redo Mask]."""
    window = _make_window(qtbot, tmp_path)
    # Collect the toolbar's actions in order.
    actions = window.toolbar.actions()

    # Find indices of the four undo/redo actions.
    idx_undo_img = actions.index(window.action_undo_image)
    idx_redo_img = actions.index(window.action_redo_image)
    idx_undo_mask = actions.index(window.action_undo_mask)
    idx_redo_mask = actions.index(window.action_redo_mask)

    # Image pair comes before mask pair.
    assert idx_undo_img < idx_redo_img < idx_undo_mask < idx_redo_mask

    # The separator (a QAction with isSeparator() True) between the two pairs
    # lives between redo_image and undo_mask. Walk the actions list and verify
    # there is at least one separator strictly between idx_redo_img and
    # idx_undo_mask.
    between = actions[idx_redo_img + 1 : idx_undo_mask]
    assert any(a.isSeparator() for a in between), (
        "no separator between the image pair and the mask pair"
    )


@pytest.mark.gui
def test_buttons_disabled_when_stack_empty(qtbot, tmp_path) -> None:
    """With empty stacks all four undo/redo actions are disabled."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=16)

    assert not window.action_undo_mask.isEnabled()
    assert not window.action_redo_mask.isEnabled()
    assert not window.action_undo_image.isEnabled()
    assert not window.action_redo_image.isEnabled()

    # Paint a stroke -> Undo Mask enables.
    _paint_brush_dot(window.canvas, 8, 8, size=6)
    assert window.action_undo_mask.isEnabled()
    assert not window.action_redo_mask.isEnabled()

    # Undo -> Redo Mask enables, Undo Mask disables.
    window.on_undo_mask()
    assert not window.action_undo_mask.isEnabled()
    assert window.action_redo_mask.isEnabled()


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
    """Ctrl+Z / Ctrl+Shift+Z / Alt+Z / Alt+Shift+Z QShortcuts exist."""
    from PySide6.QtGui import QShortcut

    window = _make_window(qtbot, tmp_path)
    # Collect all QShortcut children of the MainWindow.
    shortcuts = window.findChildren(QShortcut)
    key_strings = {s.key().toString() for s in shortcuts}
    assert "Ctrl+Z" in key_strings
    assert "Ctrl+Shift+Z" in key_strings
    assert "Alt+Z" in key_strings
    assert "Alt+Shift+Z" in key_strings


@pytest.mark.gui
def test_undo_does_not_repush(qtbot, tmp_path) -> None:
    """apply_undo_mask does NOT emit mask_modified (no infinite loop)."""
    window = _make_window(qtbot, tmp_path)
    _open_page(window, tmp_path, size=32)
    _paint_brush_dot(window.canvas, 10, 10, size=8)

    # The undo stack should have exactly 1 entry now.
    assert window.history.can_undo_mask()

    # Apply undo; assert mask_modified is NOT emitted.
    with qtbot.assertNotEmitted(window.canvas.mask_modified):
        window.on_undo_mask()

    # The undo stack should now be EMPTY (the undo popped the entry; the
    # current was stashed into redo; no re-push happened).
    assert not window.history.can_undo_mask()
    assert window.history.can_redo_mask()


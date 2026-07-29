"""GUI tests for Phase 3 plan 03-05 Task 1: per-page box persistence.

This is the D-11 mirror of Phase 2's mask persistence seam (T-02-04). Locks
the contract that text boxes survive page navigation: the OUTGOING page's
canvas boxes are snapshotted into ``ImageFile.boxes`` at the
``on_page_selected`` boundary, and the INCOMING page's boxes are restored
via ``canvas.set_boxes``. Mirrors the Phase 2 ``test_mask_persistence_*``
shape verbatim (the boxes slot is the same D-11 seam Phase 2 used for the
mask — T-03-08 mitigation).

Task 2 (Surface 13 undo collapse) extends this file with the undo tests.

These tests need a display; on headless CI they skip via ``importorskip``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QShortcut  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (mirror tests/test_gui_batch.py:54-69)
# ---------------------------------------------------------------------------


def _make_window(qtbot, tmp_path: Path) -> MainWindow:
    """Build a MainWindow wired to a ProfileManager in tmp_path."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _load_two_pages(
    window: MainWindow, tmp_path: Path, size: int = 64
) -> tuple[Path, Path]:
    """Load a folder of two PNG pages into window.image_files.

    Mirrors the navigation path the real FileTable/sidebar drives:
    ``_load_folder`` populates the sidebar, ``_set_pages`` auto-selects
    page_a, subsequent navigation uses ``select_path`` + ``on_page_selected``.
    """
    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    img.save(str(page_a))
    img.save(str(page_b))
    window._load_folder(tmp_path)
    return page_a, page_b


def _user_box(x1: int = 5, y1: int = 6, x2: int = 25, y2: int = 30) -> PageBox:
    return PageBox(box=Box(x1, y1, x2, y2), origin=USER)


def _detected_box(x1: int = 35, y1: int = 8, x2: int = 55, y2: int = 40) -> PageBox:
    return PageBox(box=Box(x1, y1, x2, y2), origin=DETECTED, payload=object())


# ===========================================================================
# Task 1: Per-page box persistence (D-11 mirror of Phase 2 mask seam)
# ===========================================================================


@pytest.mark.gui
def test_box_persistence_round_trip(qtbot, tmp_path) -> None:
    """Boxes placed on page A survive navigating to B and back (round-trip).

    The OUTGOING save (on_page_selected Step 1) writes the canvas boxes into
    ImageFile.boxes; the INCOMING restore (Step 4) rebuilds them via
    set_boxes. After a round-trip, canvas.has_boxes() and the boxes match
    the originals (origin preserved).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0

    # Seed boxes on page A: 1 user + 1 detected.
    window.canvas.set_boxes([_user_box(5, 6, 25, 30)], [_detected_box(35, 8, 55, 40)])
    assert window.canvas.has_boxes()
    assert window.canvas.box_count() == 2

    # Navigate to page B.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    assert window._current_page_index() == 1

    # On page B: no boxes yet (page B has never had boxes built).
    assert not window.canvas.has_boxes()

    # Navigate back to page A.
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)
    assert window._current_page_index() == 0

    # Boxes survive the round-trip (Step 4 restore).
    assert window.canvas.has_boxes(), (
        "boxes must be restored onto the canvas after returning to page A"
    )
    assert window.canvas.box_count() == 2
    detected, user = window.canvas.box_origin_counts()
    assert detected == 1, "the detected box survived (origin preserved)"
    assert user == 1, "the user box survived (origin preserved)"
    # Geometry preserved (the int-Box round-trips).
    snap = window.canvas.boxes_snapshot()
    user_boxes = [pb for pb in snap if pb.origin == USER]
    assert user_boxes[0].box.as_tuple == (5, 6, 25, 30)


@pytest.mark.gui
def test_box_persistence_uses_copy(qtbot, tmp_path) -> None:
    """Pitfall-3 regression guard: the OUTGOING save detaches the snapshot.

    boxes_snapshot() materializes fresh int-Box tuples per item (plan 03-03),
    so the persisted list is detached by construction. This guard locks that:
    after navigating away (which persists page A's boxes), the persisted list
    does NOT alias the live canvas. Mirrors Phase 2's
    test_mask_persistence_uses_copy (T-03-08).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    # Seed boxes on page A.
    window.canvas.set_boxes([_user_box(5, 6, 25, 30)], [_detected_box(35, 8, 55, 40)])

    # Navigate to page B -> the OUTGOING save snapshots page A's boxes.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)

    # The persisted list must exist and contain the original geometry.
    persisted = window.image_files[0].boxes
    assert persisted is not None, "precondition: page A boxes must have persisted"
    saved_user = [pb for pb in persisted if pb.origin == USER][0]
    saved_user_tuple = saved_user.box.as_tuple
    assert saved_user_tuple == (5, 6, 25, 30)

    # Mutate the canvas boxes on page B (add/remove) — this must NOT reach back
    # through the snapshot into page A's persisted list.
    window.canvas.set_boxes([_user_box(100, 100, 120, 120)], [])

    # Page A's persisted boxes are UNCHANGED — the snapshot was detached.
    persisted_after = window.image_files[0].boxes
    assert persisted_after is persisted or persisted_after == persisted, (
        "Pitfall-3 regression: mutating the canvas after persistence altered "
        "page A's persisted ImageFile.boxes — the snapshot aliased the live "
        "canvas instead of being detached."
    )
    saved_user_after = [pb for pb in persisted_after if pb.origin == USER][0]
    assert saved_user_after.box.as_tuple == saved_user_tuple


@pytest.mark.gui
def test_outgoing_index_uses_last_page_index(qtbot, tmp_path) -> None:
    """Phase 2 lesson regression: the OUTGOING save writes to the page we are
    LEAVING (image_files[0]), NOT the page we are navigating to.

    on_page_selected reads the OUTGOING index from self._last_page_index
    (NOT _current_page_index(), which has already flipped to the incoming
    page by the time the seam runs — Phase 2 lesson logged in STATE.md).
    This test catches the _current_page_index-vs-_last_page_index bug.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0

    # Seed boxes on page A.
    window.canvas.set_boxes([_user_box(5, 6, 25, 30)], [])

    # Navigate to page B.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)

    # The OUTGOING save must have written page A's boxes (index 0), NOT
    # page B's (index 1). If the seam mistakenly used _current_page_index(),
    # it would have written to index 1 (page B, the incoming page).
    assert window.image_files[0].boxes is not None, (
        "OUTGOING box save must write to the LEAVING page (image_files[0]); "
        "if this is None the seam used _current_page_index() (the bug)."
    )
    assert len(window.image_files[0].boxes) == 1
    # Page B (the incoming) should NOT have inherited page A's boxes.
    assert window.image_files[1].boxes is None or len(window.image_files[1].boxes) == 0, (
        "Page B accidentally received page A's boxes — the outgoing index bug."
    )


@pytest.mark.gui
def test_page_switch_resets_boxes_stack(qtbot, tmp_path) -> None:
    """Page-switching resets the BOXES stack (Phase 1's per-page reset
    invariant extended to the 3rd stack via plan 03-02's clear()).

    After a boxes push, switching pages must leave history.can_undo() False
    (the BOXES stack cleared with the other two). The reset_history call
    in on_page_selected Step 2 invokes history.clear() which plan 03-02
    extended to all six lists.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    # Push a boxes snapshot (simulating a detection or box edit).
    window.history.push_boxes_state(window.canvas.boxes_snapshot() or [_user_box()])
    assert window.history.can_undo() is True

    # Switch pages.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)

    # All three stacks cleared — the unified can_undo() is False.
    assert window.history.can_undo() is False, (
        "BOXES stack must reset on page-switch (Phase 1 invariant extended to "
        "the 3rd stack via plan 03-02's clear())."
    )


# ===========================================================================
# Task 2: Surface 13 undo collapse (unified Ctrl+Z over MASK/IMAGE/BOXES)
# ===========================================================================


@pytest.mark.gui
def test_unified_undo_pops_across_stacks(qtbot, tmp_path) -> None:
    """Unified Ctrl+Z pops the most-recent-by-stamp entry across all three
    stores (mask/image/boxes), reversing ops in chronological order.

    Push a mask edit, then a boxes snapshot (later stamp -> popped first);
    undo twice and confirm the ops reverse in order (the latest-first pop).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)

    from PySide6.QtGui import QImage

    mask = QImage(8, 8, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    window.canvas.set_mask(mask)
    window.history.push_mask_state(mask)  # stamp 1 (mask edit)
    window.history.push_boxes_state([_user_box(1, 1, 5, 5)])  # stamp 2 (boxes)

    # The unified can_undo() reflects both pushes.
    assert window.history.can_undo()

    # First Ctrl+Z -> pops the BOXES entry (stamp 2 is the most recent).
    window.on_undo()
    # After undoing boxes, redo stack gained a boxes entry.
    assert window.history.can_redo()

    # Second Ctrl+Z -> pops the MASK entry.
    window.on_undo()


@pytest.mark.gui
def test_unified_redo_after_undo(qtbot, tmp_path) -> None:
    """Ctrl+Shift+Z redoes a unified undo (the redo path across stacks)."""
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)

    from PySide6.QtGui import QImage

    mask = QImage(8, 8, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    window.canvas.set_mask(mask)
    window.history.push_mask_state(mask)

    window.on_undo()
    assert window.history.can_redo()
    window.on_redo()
    # After redo, the mask snapshot is back on the undo stack.
    assert window.history.can_undo()


@pytest.mark.gui
def test_mask_undo_shortcut_removed(qtbot, tmp_path) -> None:
    """The legacy Alt+Z/Alt+Shift+Z mask-undo shortcuts are GONE (Surface 13).

    No QShortcut registered on the MainWindow should bind to the Alt+Z or
    Alt+Shift+Z keysequence. The Phase 1 mask-undo buttons/methods are removed
    entirely (subsumed by the unified Ctrl+Z).
    """
    window = _make_window(qtbot, tmp_path)

    # Collect every QShortcut's keysequence on the MainWindow.
    sequences = set()
    for sc in window.findChildren(QShortcut):
        seq_str = sc.key().toString()
        sequences.add(seq_str)

    # Alt+Z / Alt+Shift+Z (case-insensitive) must NOT be present.
    for forbidden in ("Alt+Z", "Alt+Shift+Z", "Alt+z", "Alt+Shift+z"):
        assert forbidden not in sequences, (
            f"Legacy mask-undo shortcut '{forbidden}' still registered — "
            "Surface 13 requires it removed (subsumed by unified Ctrl+Z)."
        )


@pytest.mark.gui
def test_mask_undo_actions_and_methods_removed(qtbot, tmp_path) -> None:
    """The Phase 1 mask-undo actions (action_undo_mask, action_redo_mask) and
    their methods (on_undo_mask, on_redo_mask) are REMOVED (Surface 13).
    """
    window = _make_window(qtbot, tmp_path)
    assert not hasattr(window, "action_undo_mask"), (
        "action_undo_mask must be removed (Surface 13 collapses 4 -> 2 buttons)"
    )
    assert not hasattr(window, "action_redo_mask"), (
        "action_redo_mask must be removed (Surface 13)"
    )
    assert not hasattr(window, "on_undo_mask"), (
        "on_undo_mask must be removed (dead after the shortcut/menu removal)"
    )
    assert not hasattr(window, "on_redo_mask"), (
        "on_redo_mask must be removed (dead after the shortcut/menu removal)"
    )


@pytest.mark.gui
def test_orphaned_strings_fixed(qtbot, tmp_path) -> None:
    """The two Phase 1 confirm-dialog strings that referenced the now-removed
    Alt+Z mask-undo shortcut are fixed to Ctrl+Z (UI-SPEC Copywriting PLANNER TODO).
    """
    window = _make_window(qtbot, tmp_path)
    import inspect

    clear_src = inspect.getsource(window._confirm_clear_mask)
    replace_src = inspect.getsource(window._confirm_replace_mask)
    assert "Alt+Z" not in clear_src, (
        f"_confirm_clear_mask body still references the dead Alt+Z shortcut: {clear_src!r}"
    )
    assert "You can undo with Ctrl+Z" in clear_src, (
        f"_confirm_clear_mask body must say 'You can undo with Ctrl+Z' (UI-SPEC): {clear_src!r}"
    )
    assert "Alt+Z" not in replace_src, (
        f"_confirm_replace_mask body still references Alt+Z: {replace_src!r}"
    )
    assert "undo is available via Ctrl+Z" in replace_src, (
        f"_confirm_replace_mask body must say 'undo is available via Ctrl+Z' (UI-SPEC): {replace_src!r}"
    )


@pytest.mark.gui
def test_toolbar_has_two_undo_buttons(qtbot, tmp_path) -> None:
    """The toolbar collapses from 4 undo buttons to 2 ([Undo][Redo])
    (Surface 13 toolbar contract)."""
    window = _make_window(qtbot, tmp_path)

    undo_actions = [
        name
        for name in ("action_undo", "action_redo", "action_undo_mask", "action_redo_mask")
        if hasattr(window, name)
    ]
    assert "action_undo" in undo_actions, "the unified action_undo must exist"
    assert "action_redo" in undo_actions, "the unified action_redo must exist"
    assert "action_undo_mask" not in undo_actions, (
        "action_undo_mask must be removed (toolbar 4 -> 2)"
    )
    assert "action_redo_mask" not in undo_actions, (
        "action_redo_mask must be removed (toolbar 4 -> 2)"
    )


@pytest.mark.gui
def test_undo_redo_status_feedback(qtbot, tmp_path) -> None:
    """After an undo, the status bar shows a transient 'Undo: {op}' message
    (UI-SPEC §Copywriting — the which-stack-was-popped indication).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)

    from PySide6.QtGui import QImage

    mask = QImage(8, 8, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    window.canvas.set_mask(mask)
    window.history.push_mask_state(mask)

    window.on_undo()
    text = window.status_bar_left.text()
    assert text.startswith("Undo:"), (
        f"Status bar must show transient 'Undo: {{op}}' feedback; got: {text!r}"
    )


@pytest.mark.gui
def test_unified_undo_redo_enable_on_union_flags(qtbot, tmp_path) -> None:
    """The Undo/Redo buttons enable on the union flags (can_undo/can_redo
    over all three stacks), not the per-type flags."""
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)

    # Initially empty -> both disabled.
    assert not window.action_undo.isEnabled()
    assert not window.action_redo.isEnabled()

    # Push a boxes snapshot -> Undo enabled (union includes BOXES).
    window.history.push_boxes_state([_user_box(1, 1, 5, 5)])
    window._update_undo_redo_actions()
    assert window.action_undo.isEnabled(), (
        "Undo must enable when the BOXES stack has entries (union flag)"
    )

    # Undo -> Redo now enabled.
    window.on_undo()
    assert window.action_redo.isEnabled()

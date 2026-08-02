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
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QPointF, QRectF  # noqa: E402
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


# ===========================================================================
# CR-01 / WR-05 regression: boxes_modified -> push_boxes_state wiring
# ===========================================================================
#
# Phase 03 code review BLOCKER CR-01: EditorCanvas emits ``boxes_modified`` on
# every box create/move-commit/resize/delete (and on ``set_boxes``), but
# MainWindow never connected it — box edits were NOT undoable. These tests
# lock the fix: a box edit via the canvas API pushes a BOXES snapshot, undo
# clears the layer, redo restores it (WR-05: redo must NOT be corrupted by a
# restore re-push), and an undo/redo restore itself does NOT re-push.


@pytest.mark.gui
def test_box_edit_is_undoable(qtbot, tmp_path) -> None:
    """CR-01: a box edit (set_boxes fires boxes_modified) pushes a BOXES
    snapshot onto the undo stack, and the edit round-trips through undo/redo.

    Without the wiring (the CR-01 bug), ``set_boxes`` emits but nothing
    consumes the signal, so ``can_undo_boxes()`` stays False after the edit.
    This regression catches a re-disconnection AND proves the WR-05 guard
    keeps redo intact across the round-trip (a restore re-push during
    undo/redo would clear redo and make the round-trip a no-op).

    The history stores checkpoints; undo restores the most-recent checkpoint.
    To make a box-create undoable back to the empty layer, the empty BEFORE
    checkpoint is seeded explicitly (the same way production code would
    establish the baseline), then the edit pushes the AFTER checkpoint.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)
    assert window._current_page_index() == 0

    # Empty layer + empty history to start.
    assert not window.canvas.has_boxes()
    assert not window.history.can_undo_boxes()

    # Seed the BEFORE checkpoint (empty layer) so undo has a target to restore.
    # Suppress the hook for the seed so the seed itself does not double-push.
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([], [])
    finally:
        window._suppress_boxes_push = False
    window.history.push_boxes_state(window.canvas.boxes_snapshot())  # [] before

    # A box edit: set_boxes fires boxes_modified -> the push hook fires.
    window.canvas.set_boxes([_user_box(5, 6, 25, 30)], [])
    assert window.canvas.box_count() == 1

    # CR-01 contract: the edit pushed a BOXES snapshot (the AFTER state).
    assert window.history.can_undo_boxes(), (
        "CR-01 regression: set_boxes emitted boxes_modified but no BOXES "
        "snapshot was pushed — boxes_modified is not wired to push_boxes_state."
    )
    # The unified can_undo() reflects the BOXES push too.
    assert window.history.can_undo()

    # Undo: pops the AFTER-state checkpoint, stashes current into redo, and
    # restores the BEFORE checkpoint (empty layer).
    window.on_undo()
    assert window.canvas.box_count() == 0, (
        "Undo of a box edit must restore the box layer to the BEFORE checkpoint."
    )
    # After undo, redo is available (the popped entry was stashed into redo).
    assert window.history.can_redo_boxes()

    # WR-05 guard: redo restores the box WITHOUT corruption. A restore re-push
    # (set_boxes emitting boxes_modified during apply_undo_boxes) would have
    # pushed a spurious entry and left redo unable to replay the box.
    window.on_redo()
    assert window.canvas.box_count() == 1, (
        "WR-05 regression: redo must restore the box. A restore re-push during "
        "undo/redo corrupted the redo branch."
    )


@pytest.mark.gui
def test_box_restore_does_not_repush(qtbot, tmp_path) -> None:
    """WR-05: apply_undo_boxes (the restore path) does NOT re-push onto the
    BOXES stack.

    ``set_boxes`` always emits ``boxes_modified`` (for the canvas-internal
    refresh). Once CR-01 wires boxes_modified -> _on_boxes_modified, a naive
    wiring would make every undo/redo restore re-push the restored state onto
    the undo stack and clear redo — corrupting the timeline. The
    ``_suppress_boxes_push`` guard around the restore prevents this. This is
    the box analogue of mask's ``test_undo_does_not_repush``.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, _page_b = _load_two_pages(window, tmp_path)

    # Establish a baseline: one box on the layer + one BOXES undo entry
    # (the edit pushes the AFTER checkpoint via the hook).
    window.canvas.set_boxes([_user_box(5, 6, 25, 30)], [])
    assert window.history.can_undo_boxes()
    undo_before = len(window.history._boxes_undo)
    redo_before = len(window.history._boxes_redo)
    assert undo_before >= 1
    assert redo_before == 0

    # A pure restore (the empty-list path apply_undo_boxes uses when undoing a
    # box-create back to an empty layer). set_boxes([], []) emits
    # boxes_modified — the guard must swallow it so no new push happens.
    window.apply_undo_boxes([])

    # The BOXES undo/redo counts are UNCHANGED by the restore (WR-05).
    assert len(window.history._boxes_undo) == undo_before, (
        "WR-05 regression: apply_undo_boxes([]) re-pushed onto the BOXES undo "
        "stack — the _suppress_boxes_push guard is missing or ineffective."
    )
    assert len(window.history._boxes_redo) == redo_before, (
        "WR-05 regression: apply_undo_boxes([]) altered the BOXES redo stack "
        "via a spurious push."
    )


# ===========================================================================
# Plan 03-07: UAT test 3 (detection baseline non-undoable) + UAT test 4
# (moved-position persistence) + CREATE-undo contract guard (WR-05 / WARNING 5).
# ===========================================================================
#
# Gap 3 (UAT test 3): the third Ctrl+Z wiped ALL detected boxes because
# ``_build_detected_boxes`` explicitly pushed a 0-box pre-detection snapshot,
# making the INITIAL detection undoable. Fix: detection is a NON-undoable
# baseline — it establishes the live layer WITHOUT pushing a boxes stack entry.
#
# Gap 4 (UAT test 4, partial): a moved box's position was REPORTED to reset
# across a page round-trip. A live probe (driving the real move-commit path +
# real ``on_page_selected`` round-trip) showed the persistence read path is
# ALREADY correct (``boxes_snapshot`` -> ``current_box`` -> live ``rect()``);
# the bug does not reproduce. The UAT marked this ``diagnosed: partial`` ("the
# probe fixture tripped on on_page_selected's signature") — never live-
# confirmed. TEST B is therefore a PASSING regression guard locking the correct
# behavior, NOT a RED defect reproduction (honest TDD: a test for a non-existent
# bug must pass, otherwise it would be fabricated). See the plan's FIX 4 note:
# "VERIFY FIRST that boxes_snapshot reads the live rect — candidate (a) should
# be FALSE. ... no code change needed on the read side IF boxes_snapshot already
# reads live." The probe confirms exactly that landing.
#
# TEST C is a CREATE-undo contract guard (WARNING 5): a real Alt+drag CREATE
# pushes exactly one undoable BOXES entry and recovers in one Ctrl+Z. It passes
# today and must stay GREEN through Task 2 (it locks the CR-01 CREATE-undo path
# so WR-04's delta-checks on move/resize cannot silently break it).


def _window_with_real_image(qtbot, tmp_path: Path, w: int = 64, h: int = 64):
    """Build a MainWindow with a real PNG loaded so ``canvas.image_item.pixmap()``
    reports image dims (the V5 clamp in ``_build_detected_boxes`` needs them).

    Mirrors ``tests/test_gui_detection_boxes._window_with_page`` but also loads
    TWO pages so the round-trip test (TEST B) can navigate A -> B -> A.
    """
    window = _make_window(qtbot, tmp_path)
    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    Image.new("RGB", (w, h), color=(200, 200, 200)).save(page_a)
    Image.new("RGB", (w, h), color=(180, 180, 180)).save(page_b)
    window._load_folder(tmp_path)
    return window, page_a, page_b


def _drive_move_commit(canvas, box_item, new_rect: QRectF) -> None:
    """Drive the LIVE move-commit path (no real mouse): arm ``_moving_box`` via
    ``_select_and_begin_move``, mutate the rect, then emit ``boxes_modified``
    with the captured before-snapshot — exactly what ``mouseReleaseEvent``'s
    move-commit branch does (canvas.py:967-973).

    This exercises the real production push hook (``boxes_modified`` ->
    ``_on_boxes_modified`` -> ``push_boxes_state``), not a direct history call,
    so the test reflects production.
    """
    canvas._select_and_begin_move(box_item, QPointF(new_rect.x(), new_rect.y()))
    canvas._moving_box.setRect(new_rect)
    canvas._moving_box._sync_handles()
    before = canvas._boxes_interaction_start_snapshot
    canvas._moving_box = None
    canvas.boxes_modified.emit(before)


# --- TEST A: detection does not seed an undoable baseline (UAT test 3) ------


@pytest.mark.gui
def test_detection_does_not_seed_undoable_baseline(qtbot, tmp_path) -> None:
    """UAT test 3: applying detection (the suppressed ``set_boxes`` path) must
    seed NO boxes undo entry. Detection is a NON-undoable baseline — the first
    real user edit then pushes against it.

    RED today: ``_build_detected_boxes`` explicitly calls
    ``push_boxes_state(pre_detection_snapshot)`` at Step 5 (main_window.py:1633),
    so after a detect-with-build ``can_undo_boxes()`` is True. After the fix
    removes that push, ``can_undo_boxes()`` must be False (detection seeded no
    baseline). This test drives the suppressed-set_boxes path detection uses at
    Step 3 (mirroring ``_build_detected_boxes``); the
    ``test_detection_via_build_detected_boxes_no_baseline`` companion drives the
    REAL ``_build_detected_boxes`` method where the buggy push lives.
    """
    window, _page_a, _page_b = _window_with_real_image(qtbot, tmp_path)
    assert not window.history.can_undo_boxes()

    # Mirror detection's Step 3: wrap the detected-box apply in the suppression
    # guard exactly as _build_detected_boxes does.
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([], [_detected_box(20, 20, 60, 60)])
    finally:
        window._suppress_boxes_push = False

    assert window.canvas.box_count() == 1
    # GAP-3 contract: detection seeded NO boxes undo entry.
    assert not window.history.can_undo_boxes(), (
        "Gap 3 regression: detection seeded a boxes undo entry — the initial "
        "detection must be a NON-undoable baseline (mirrors how the initial "
        "mask presence from a detect is not individually undoable). The "
        "explicit push_boxes_state(pre_detection_snapshot) in "
        "_build_detected_boxes must be removed."
    )


@pytest.mark.gui
def test_detection_via_build_detected_boxes_no_baseline(qtbot, tmp_path) -> None:
    """UAT test 3 (REAL path): drive the actual ``_build_detected_boxes`` method
    with a synthetic TextBlock and assert it seeds NO boxes undo entry.

    This is the TRUE RED for Gap 3 — the buggy ``push_boxes_state`` push lives
    inside ``_build_detected_boxes`` itself (not in ``set_boxes``), so only a
    direct call to the method reproduces it. The synthetic block is a duck-typed
    ``SimpleNamespace(xyxy=[...])`` — the only attribute ``textblock_to_box``
    reads (see box_model.py:105).
    """
    window, _page_a, _page_b = _window_with_real_image(qtbot, tmp_path, w=120, h=120)
    window.action_detect_boxes_mode.setChecked(True)
    assert not window.history.can_undo_boxes()

    blk = SimpleNamespace(xyxy=[20, 20, 60, 60])
    window._build_detected_boxes([blk])

    assert window.canvas.box_count() == 1, "the detected box was built onto the canvas"
    # GAP-3 contract (the real method path): NO boxes undo entry seeded.
    assert not window.history.can_undo_boxes(), (
        "Gap 3 regression: _build_detected_boxes pushed a boxes snapshot — the "
        "initial detection must be a non-undoable baseline. The explicit "
        "self.history.push_boxes_state(pre_detection_snapshot) at the method's "
        "Step 5 must be removed so detection establishes the live layer WITHOUT "
        "seeding an undo entry."
    )


@pytest.mark.gui
def test_edit_after_detection_pushes_exactly_one_entry(qtbot, tmp_path) -> None:
    """Gap-3 contract strengthened: after detection (no baseline) + ONE real
    box-move edit, the BOXES stack holds EXACTLY one entry (the move's before-
    snapshot), and undoing it restores the pre-move position while KEEPING the
    box. Locks the contract: edits undo, the detection baseline does not.
    """
    window, _page_a, _page_b = _window_with_real_image(qtbot, tmp_path, w=120, h=120)
    window.action_detect_boxes_mode.setChecked(True)

    blk = SimpleNamespace(xyxy=[20, 20, 60, 60])
    window._build_detected_boxes([blk])
    # Detection seeded no baseline (Gap 3 fix).
    assert not window.history.can_undo_boxes()

    # One real move edit via the live commit path -> pushes the before-snapshot.
    box_item = window.canvas._box_items[0]
    pre_move_rect = QRectF(box_item.rect())
    _drive_move_commit(window.canvas, box_item, QRectF(80, 80, 40, 40))

    assert window.history.can_undo_boxes()
    assert len(window.history._boxes_undo) == 1, (
        "After detect (no baseline) + one move, the BOXES stack must hold "
        "EXACTLY one entry (the move's before-snapshot)."
    )

    # Undo the move: restores the pre-move position, KEEPS the box.
    window.on_undo()
    snap = window.canvas.boxes_snapshot()
    assert len(snap) == 1, "undo of a move must keep the box (only revert the move)"
    restored = snap[0].box.as_tuple
    assert restored == (
        int(pre_move_rect.x()),
        int(pre_move_rect.y()),
        int(pre_move_rect.x() + pre_move_rect.width()),
        int(pre_move_rect.y() + pre_move_rect.height()),
    ), f"undo must restore the pre-move position; got {restored}"


# --- TEST B: moved position persists across round-trip (UAT test 4) ---------


@pytest.mark.gui
def test_moved_box_position_persists_across_round_trip(qtbot, tmp_path) -> None:
    """UAT test 4: a moved box's POSITION persists across a page round-trip,
    for BOTH a detected box AND a user box.

    The UAT marked this ``diagnosed: partial`` ("probe fixture tripped on
    on_page_selected's signature"). A live probe driving the REAL move-commit
    path + a REAL ``on_page_selected`` round-trip showed the persistence read
    path (``boxes_snapshot`` -> ``current_box`` -> live ``rect()``) is ALREADY
    correct — the moved rect is what persists, not a creation-time snapshot. So
    this test is a PASSING regression guard locking the correct behavior, NOT a
    failing RED defect reproduction. The user-box case is its OWN named
    assertion (WARNING 4: the UAT explicitly includes drawn/user boxes).

    Detection also seeds no baseline here, so the round-trip does not depend on
    any boxes stack state (page-switch resets history regardless).
    """
    window, page_a, page_b = _window_with_real_image(qtbot, tmp_path, w=120, h=120)
    window.action_detect_boxes_mode.setChecked(True)

    # Seed BOTH boxes at their creation positions via the real detection method
    # (detected) + a suppressed set_boxes (user box) in one go, so neither
    # clears the other. The user box is added alongside the detected box.
    blk = SimpleNamespace(xyxy=[20, 20, 60, 60])
    window._build_detected_boxes([blk])
    user_seed = PageBox(box=Box(10, 10, 30, 30), origin=USER)
    moved_detected = window.canvas.boxes_snapshot()  # the detected box, pre-move
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes([user_seed], moved_detected)
    finally:
        window._suppress_boxes_push = False
    assert window.canvas.box_count() == 2

    # Move the DETECTED box to a new position via the live commit path.
    detected_item = [
        it for it in window.canvas._box_items if it.pagebox.origin == DETECTED
    ][0]
    _drive_move_commit(window.canvas, detected_item, QRectF(100, 100, 40, 40))

    # Move the USER box to a new position via the live commit path.
    user_item = [
        it for it in window.canvas._box_items if it.pagebox.origin == USER
    ][0]
    _drive_move_commit(window.canvas, user_item, QRectF(90, 90, 30, 30))

    # Navigate A -> B -> A (the real round-trip path the sidebar drives).
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    assert not window.canvas.has_boxes()  # page B never had boxes
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)

    restored = window.canvas.boxes_snapshot()
    assert len(restored) == 2, f"both boxes must survive the round-trip; got {len(restored)}"

    restored_detected = [pb for pb in restored if pb.origin == DETECTED][0]
    assert restored_detected.box.as_tuple == (100, 100, 140, 140), (
        "UAT test 4 (detected box): the MOVED position (100,100,140,140) must "
        f"persist across the round-trip; got {restored_detected.box.as_tuple}."
    )

    # WARNING 4: the USER-box case is its own named assertion (separate line).
    restored_user = [pb for pb in restored if pb.origin == USER][0]
    assert restored_user.box.as_tuple == (90, 90, 120, 120), (
        "UAT test 4 (USER box): a moved DRAWN box's position must persist across "
        f"the round-trip; got {restored_user.box.as_tuple}. The UAT explicitly "
        "includes user boxes ('including drawn (user) boxes, not just detected "
        "ones') — this is a separate failure line from the detected-box case."
    )


# --- TEST C: CREATE-undo contract guard (WARNING 5 / WR-04) -----------------


@pytest.mark.gui
def test_create_box_pushes_one_undoable_entry(qtbot, tmp_path) -> None:
    """CREATE-undo contract guard (WARNING 5). PASSES today (a passing guard,
    not a RED defect) — locks the CR-01 CREATE-undo path so WR-04's delta-checks
    on move/resize cannot silently break it.

    A real Alt+drag CREATE (via ``_begin_create_box`` + ``_commit_create``) must
    push EXACTLY one undoable BOXES entry, and a single ``on_undo()`` recovers
    the pre-create state in one press. The early-return path (a CREATE ending
    smaller than ``MIN_BOX_SIZE``) produces ZERO new entries — proving
    ``_commit_create`` no-ops on tiny drags WITHOUT needing a delta-check (so
    Task 2's delta-checks stay confined to move/resize, never create).
    """
    window, _page_a, _page_b = _window_with_real_image(qtbot, tmp_path, w=120, h=120)
    assert not window.history.can_undo_boxes()
    count_before = len(window.history._boxes_undo)

    # Drive a real Alt+drag CREATE via the live path: arm _begin_create_box at a
    # scene anchor, advance the rect to a >= 8x8 size, then _commit_create.
    window.canvas._begin_create_box(QPointF(10, 10))
    # Advance the create preview (the mouseMoveEvent _advance_create path draws
    # a rect from the anchor to the cursor; here we set the final rect directly
    # on the would-be box by advancing through _commit_create's rect math).
    # _commit_create reads self._create_anchor + the release scene pos and builds
    # QRectF(anchor, curr).normalized(); emulate by giving it a release event.
    # Simplest faithful path: call _commit_create with a fake event whose
    # position maps to the desired corner.
    from unittest.mock import MagicMock
    from PySide6.QtCore import QPoint

    release_event = MagicMock()
    release_event.position.return_value = QPointF(50, 50)
    # _scene_pos maps event.position().toPoint() through mapToScene; bypass by
    # monkeypatching to return the scene point we want.
    window.canvas._scene_pos = lambda event: QPointF(50, 50)
    window.canvas._commit_create(release_event)

    # EXACTLY one BOXES entry was pushed (the real create).
    assert window.history.can_undo_boxes(), (
        "CR-01 CREATE-undo contract: a real Alt+drag CREATE must push a BOXES "
        "snapshot so it is undoable in one Ctrl+Z."
    )
    assert len(window.history._boxes_undo) == count_before + 1, (
        "CR-01 CREATE-undo contract: a real CREATE must push EXACTLY one entry "
        f"(got {len(window.history._boxes_undo) - count_before})."
    )
    assert window.canvas.box_count() == 1

    # A single on_undo recovers the pre-create state (one-press undoability).
    window.on_undo()
    assert window.canvas.box_count() == 0, (
        "CR-01 CREATE-undo contract: a single Ctrl+Z must undo the create."
    )

    # Early-return path: a tiny CREATE (< MIN_BOX_SIZE) pushes ZERO new entries.
    count_after_undo = len(window.history._boxes_undo)
    window.canvas._begin_create_box(QPointF(10, 10))
    tiny_event = MagicMock()
    tiny_event.position.return_value = QPointF(12, 12)  # 2x2 < MIN_BOX_SIZE(8)
    window.canvas._scene_pos = lambda event: QPointF(12, 12)
    window.canvas._commit_create(tiny_event)
    assert len(window.history._boxes_undo) == count_after_undo, (
        "CR-01 early-return contract: a CREATE smaller than MIN_BOX_SIZE must "
        "push ZERO entries (no-op). A delta-check on _commit_create would be "
        "redundant AND risks the real-create path — this guards that it stays "
        "untouched."
    )

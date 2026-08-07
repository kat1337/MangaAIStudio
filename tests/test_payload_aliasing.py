"""RESEARCH Pitfall 8 regression guard — undo restores the PRE-edit text,
not the live (post-edit) text (plan 04-01 Task 2).

Phase 3 had no text to mutate, so the BOXES undo stack's payload aliasing was
harmless: the snapshot's ``payload`` was the SAME ``TextBlock`` object as the
live one, but nobody mutated it. Phase 4 mutates ``payload.text`` /
``payload.translation``. ``_materialize_snapshot`` (history_manager.py) calls
``item.copy() if hasattr(item, "copy")`` — and ``PageBox.copy()`` (Task 1)
detaches the payload via ``copy.copy(payload)``, so the snapshot's payload is
a DIFFERENT object. Mutating the live payload after push no longer reaches
the snapshot.

This is a HEADLESS test: it constructs ``HistoryManager`` directly with real
``PageBox`` objects (no Qt, no display). The HistoryManager is the boundary
that PageBox.copy() plugs into.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")  # HistoryManager imports QImage for type hints

from manga_ai_studio.core.box_model import DETECTED, PageBox  # noqa: E402
from manga_ai_studio.core.history_manager import HistoryManager  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


def _pagebox_with_text(text: str) -> PageBox:
    """A PageBox with a TextBlock payload carrying the given recognized text."""
    pb = PageBox(box=Box(10, 20, 110, 220), origin=DETECTED)
    pb.set_recognized_text(text)
    return pb


@pytest.mark.unit
def test_pop_boxes_undo_restores_pre_edit_text() -> None:
    """Pitfall 8 (payload aliasing): after pushing a snapshot, mutating the
    LIVE pagebox's ``payload.text`` in place, then popping undo must return a
    pagebox whose ``payload.text`` is the SNAPSHOT-time value ("before"), not
    the live post-mutation value ("after").

    This is the load-bearing regression: without PageBox.copy() detaching the
    payload, the snapshot and the live object share a TextBlock, so the
    mutation reaches the snapshot and undo restores the SAME (mutated) text.
    """
    history = HistoryManager(limit=20)

    pb = _pagebox_with_text("before")
    history.push_boxes_state([pb])

    # Mutate the LIVE pagebox's payload.text in place (simulates a text edit
    # that writes payload.text directly without replacing the payload object).
    pb.payload.text = "after"

    restored = history.pop_boxes_undo(current_boxes=[pb])
    assert restored is not None
    assert len(restored) == 1
    restored_pb = restored[0]
    assert isinstance(restored_pb, PageBox)
    # Undo restores the snapshot-time text, NOT the live post-edit text.
    assert restored_pb.payload is not None
    assert restored_pb.payload.text == "before"
    # And the restored payload is detached from the live one.
    assert restored_pb.payload is not pb.payload


@pytest.mark.unit
def test_pushed_snapshot_payload_detached_from_live() -> None:
    """The snapshot stored at push-time has its OWN payload object — mutating
    the live pagebox.payload.text after push does not change the stored
    snapshot's payload.text (Pitfall 8, push-side)."""
    history = HistoryManager(limit=20)

    pb = _pagebox_with_text("snapshot text")
    history.push_boxes_state([pb])

    # Inspect the stored snapshot BEFORE any mutation.
    _, stored = history._boxes_undo[-1]
    stored_pb = stored[0]
    assert stored_pb.payload is not None
    assert stored_pb.payload is not pb.payload  # detached object
    assert stored_pb.payload.text == "snapshot text"

    # Mutate the live payload; the stored snapshot is untouched.
    pb.payload.text = "mutated live"
    assert stored_pb.payload.text == "snapshot text"


@pytest.mark.unit
def test_copy_preserves_edited_flag_for_undo() -> None:
    """The ``edited`` flag round-trips through the snapshot detachment too —
    a PageBox with ``edited=True`` pushed then undone restores ``edited=True``
    (Pitfall 1 + 8 together)."""
    history = HistoryManager(limit=20)

    pb = _pagebox_with_text("ocr text")  # edited=False (OCR-write path)
    pb.set_recognized_text_edited("manual edit")  # edited=True now
    assert pb.edited is True
    history.push_boxes_state([pb])

    restored = history.pop_boxes_undo(current_boxes=[pb])
    assert restored is not None
    restored_pb = restored[0]
    assert restored_pb.edited is True
    assert restored_pb.payload.text == "manual edit"

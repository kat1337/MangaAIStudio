"""RESEARCH Pitfall 1 regression guard — ``boxes_snapshot()`` round-trips the
Phase 4 fields (plan 04-01 Task 2).

``canvas.boxes_snapshot()`` is the detachment boundary for the BOXES undo
stack AND the page-switch persistence seam (``ImageFile.boxes =
canvas.boxes_snapshot()``). Phase 4 adds ``edited`` / ``bubble_no`` /
``manual_override`` peer fields to ``PageBox`` plus ``payload.text`` /
``payload.translation``. The Phase 3 snapshot constructed ``PageBox`` with
ONLY ``box`` / ``origin`` / ``payload`` — the new peer fields defaulted
(silently lost their live values), so undoing a text edit or switching pages
dropped the ``edited`` flag, bubble number, and manual-override state.

This is a GUI test (needs an ``EditorCanvas`` + a display); it skips on
headless CI via ``pytest.importorskip``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPixmap  # noqa: E402

from manga_ai_studio.core.box_model import DETECTED, PageBox  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402


def _white_pixmap(size: int = 120) -> QPixmap:
    """A solid white QPixmap large enough to host a box + handle slack.

    ``EditorCanvas.set_image`` expects a QPixmap (QGraphicsPixmapItem.setPixmap).
    Mirrors ``tests/test_gui_boxes._solid_pixmap``.
    """
    from PySide6.QtCore import Qt

    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    return QPixmap.fromImage(img)


@pytest.mark.gui
def test_boxes_snapshot_round_trips_phase4_fields(qtbot) -> None:
    """Pitfall 1: ``boxes_snapshot()`` reads the live ``BoxItem.pagebox``'s
    ``edited`` / ``bubble_no`` / ``manual_override`` (NOT the defaults), and
    preserves ``payload.text`` / ``payload.translation`` (they ride on the
    payload reference). Without the fix the snapshot silently drops the peer
    fields (edited=False, bubble_no=None, manual_override=False)."""
    from PySide6.QtWidgets import QApplication

    # A PageBox carrying ALL Phase 4 state: peer fields + payload text/tr.
    pb = PageBox(box=Box(10, 20, 110, 220), origin=DETECTED)
    pb.edited = True
    pb.bubble_no = 3
    pb.manual_override = True
    pb.set_recognized_text_edited("x")  # sets payload.text="x", edited=True
    pb.set_translation("y")  # sets payload.translation="y"

    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(300, 300)
    canvas.set_image(_white_pixmap(120))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()

    canvas.set_boxes(user_pageboxes=[pb], detected_pageboxes=[])

    snapshot = canvas.boxes_snapshot()
    assert len(snapshot) == 1
    snap_pb = snapshot[0]

    # The peer fields round-trip (the Pitfall 1 load-bearing assertion).
    assert snap_pb.edited is True
    assert snap_pb.bubble_no == 3
    assert snap_pb.manual_override is True
    # The payload text/translation survive (they ride on the payload).
    assert snap_pb.payload is not None
    assert snap_pb.payload.text == "x"
    assert snap_pb.payload.translation == "y"

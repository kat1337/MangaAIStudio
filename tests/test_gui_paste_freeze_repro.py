"""Repro harness for the reported paste-after-delete freeze (quick-260909-ke1).

User report (verbatim): "i copied the text in a box, deleted the box, expanded
a different box and pasted, the app then froze and stop". Two scripted
headless sequences mirror the report, asserting invariants instead of
wall-clock hangs (no pytest-timeout in this project — a "wait for a hang"
test would hang CI):

- **Sequence A** — the report, verbatim: copy-text (Ctrl+click) -> Ctrl+C box
  copy -> Delete box A -> expand box B (resize commit) -> Ctrl+V paste. A
  canary: today's layer mechanics already run it clean, and it must STAY clean
  after the Task 3 fix.

- **Sequence B** — the stale-editor variant the diagnosis identified as the
  one demonstrable staleness violation: the Delete/Backspace branch (and
  ``_remove_box``) have NO inline-editor guard, while every layer rebuild
  (``set_boxes``) commits the editor FIRST precisely so "a stale editor never
  dangles over a removed box" (canvas.py precedent). With the editor open on
  A, deleting A leaves the editor active over the retired item; the user's
  next commit writes text into a removed PageBox and emits a bogus
  ``boxes_modified`` AFTER the removal emission (undo corruption) — inside a
  Qt slot in the real app. RED first (guard absent), GREEN after the
  commit-first guard lands.

- **Breadcrumbs** — the traced copy/delete/expand/paste paths emit
  ``logger.debug`` lines whose logger names live in the
  ``manga_ai_studio.gui`` namespace, so the Task 1 file-sink filter admits
  them below the WARNING floor (verified end-to-end here against a real
  install() into a tmp dir).

Header mirrors ``tests/test_gui_boxes.py`` (``pytest.importorskip`` + qtbot +
``@pytest.mark.gui``); event synthesis reuses its proven helpers.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from loguru import logger  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from manga_ai_studio import diagnostics  # noqa: E402
from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.box_model import DETECTED, USER, PageBox  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402

from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


# ------------------------------------------------------------------ helpers
def _solid_pixmap(size: int, color: QColor) -> QImage:
    """Build a solid-color QPixmap of the given size (mirrors test_gui_boxes)."""
    from PySide6.QtGui import QPixmap

    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


def _canvas_with_boxes(
    qtbot,
    pageboxes: list[PageBox],
    size: int = 200,
) -> EditorCanvas:
    """A shown canvas with an image + the given boxes (mirrors test_gui_boxes)."""
    canvas = EditorCanvas()
    qtbot.addWidget(canvas)
    canvas.resize(400, 400)
    canvas.set_image(_solid_pixmap(size, QColor("white")))
    canvas.show()
    canvas.viewport().show()
    QApplication.processEvents()
    canvas.set_boxes(pageboxes, [])
    return canvas


def _press_at(
    canvas: EditorCanvas,
    sx: float,
    sy: float,
    *,
    ctrl: bool = False,
) -> QMouseEvent:
    """Left-button press whose viewport coords map to scene (sx, sy)."""
    vp = canvas.mapFromScene(QPointF(sx, sy))
    mods = Qt.KeyboardModifier.NoModifier
    if ctrl:
        mods |= Qt.KeyboardModifier.ControlModifier
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        mods,
    )


def _move_at(canvas: EditorCanvas, sx: float, sy: float) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(vp),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release_at(canvas: EditorCanvas, sx: float, sy: float) -> QMouseEvent:
    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _key(canvas: EditorCanvas, key: Qt.Key, ctrl: bool = False) -> None:
    """Deliver a KeyPress directly to the canvas (test_gui_boxes discipline)."""
    mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    canvas.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


def _box_a_payload() -> SimpleNamespace:
    """Duck-typed TextBlock payload carrying recognized text (detected_text reads .text)."""
    return SimpleNamespace(text="copied bubble text ke1", translation=None)


def _snapshot_text_of(snapshot: list[PageBox], box: Box) -> str | None:
    """The recognized text a snapshot carries for the box at ``box`` coords."""
    for pb in snapshot:
        if pb.box.as_tuple == box.as_tuple:
            if pb.payload is None:
                return None
            t = getattr(pb.payload, "text", None)
            if isinstance(t, list):
                return "".join(str(s) for s in t)
            return None if t is None else str(t)
    return None


# ------------------------------------------------- Sequence A — the report
@pytest.mark.gui
def test_repro_sequence_a_reported_flow_runs_clean(qtbot) -> None:
    """The reported sequence verbatim: copy text -> Ctrl+C -> delete A ->
    expand B -> paste; no exception, consistent box-layer state."""
    box_a = Box(20, 20, 120, 120)
    box_b = Box(130, 30, 180, 80)
    canvas = _canvas_with_boxes(
        qtbot,
        [
            PageBox(box=box_a, origin=DETECTED, payload=_box_a_payload()),
            PageBox(box=box_b, origin=USER),
        ],
    )
    item_a, item_b = canvas._box_items

    copied: list[str] = []
    canvas.copy_text_requested.connect(copied.append)
    emissions: list = []
    canvas.boxes_modified.connect(emissions.append)

    # 1. Ctrl+click box A under the Move tool -> copy-text branch emits.
    canvas.mousePressEvent(_press_at(canvas, 70, 70, ctrl=True))
    assert copied == ["copied bubble text ke1"]  # plain TEXT crosses the boundary

    # 2. Ctrl+C seeds the in-process box clipboard with a detached A clone.
    item_a.setSelected(True)
    _key(canvas, Qt.Key.Key_C, ctrl=True)
    assert len(canvas.box_clipboard) == 1
    assert canvas.box_clipboard[0].payload.text == "copied bubble text ke1"

    # 3. Delete removes A (gone from the live layer, held in the graveyard).
    _key(canvas, Qt.Key.Key_Delete)
    assert item_a not in canvas._box_items
    assert item_a in canvas._box_graveyard  # deferred release, not dropped mid-loop

    # 4. Expand box B via the resize commit path (press BR handle, drag, release).
    item_b.setSelected(True)
    r = item_b.rect()
    canvas.mousePressEvent(_press_at(canvas, r.right(), r.bottom()))
    assert canvas._resizing_box is item_b
    canvas.mouseMoveEvent(_move_at(canvas, r.right() + 15, r.bottom() + 15))
    canvas.mouseReleaseEvent(_release_at(canvas, r.right() + 15, r.bottom() + 15))
    assert item_b.rect().width() > r.width() and item_b.rect().height() > r.height()
    assert len(emissions) == 2  # delete + resize commit emissions so far

    # 5. Ctrl+V pastes: a new box exists (A's clone, text kept) and one
    # boxes_modified lands for the paste.
    _key(canvas, Qt.Key.Key_V, ctrl=True)
    assert canvas.box_count() == 2  # B + the pasted clone
    assert len(emissions) == 3
    pasted = [it for it in canvas._box_items if it is not item_b]
    assert len(pasted) == 1
    assert pasted[0].pagebox.payload.text == "copied bubble text ke1"
    assert pasted[0].pagebox.origin == USER  # fresh-box semantics
    assert pasted[0].isSelected()  # the paste owns the selection

    # Pump the loop: the graveyard release callback must run WITHOUT exception
    # (any RuntimeError inside a slot would fail this test) and leave a
    # consistent layer behind.
    qtbot.wait(50)
    assert canvas._box_graveyard == []  # released
    assert canvas._graveyard_pending is False
    for it in canvas._box_items:
        assert it.scene() is canvas.scene()
    assert len(emissions) == 3  # no phantom extra emissions from the release


# ------------------------------- Sequence B — stale editor over deleted box
@pytest.mark.gui
def test_delete_with_active_editor_commits_editor_first(qtbot) -> None:
    """Deleting the editor's box must commit the editor FIRST (set_boxes precedent).

    RED (today): the Delete branch has no inline-editor guard — the editor
    stays active over the retired item, and a later commit() writes text into
    a removed PageBox and emits a bogus boxes_modified AFTER the removal
    emission. GREEN (after the guard): the commit lands through the normal
    boxes_modified seam BEFORE the removal emission and the editor is closed.
    """
    box_a = Box(20, 20, 120, 120)
    canvas = _canvas_with_boxes(
        qtbot,
        [PageBox(box=box_a, origin=DETECTED, payload=_box_a_payload())],
    )
    item_a = canvas._box_items[0]
    assert item_a.pagebox.payload.text == "copied bubble text ke1"

    # The inline editor is open on A with an uncommitted text change.
    canvas._inline_editor.enter(item_a)
    assert canvas._inline_editor.is_active()
    canvas._inline_editor._text_edit.setPlainText("edited pre delete ke1")

    emitted: list = []
    canvas.boxes_modified.connect(emitted.append)

    # The user deletes the box while the editor is open.
    item_a.setSelected(True)
    _key(canvas, Qt.Key.Key_Delete)

    # GREEN contract: the editor was committed/closed by the delete path —
    # it NEVER dangles over the retired BoxItem.
    assert not canvas._inline_editor.is_active()
    assert item_a not in canvas._box_items
    assert item_a in canvas._box_graveyard

    # Exactly two emissions, in order: the editor commit (its BEFORE-snapshot
    # still carries the ORIGINAL text — commit captured pre-mutation), then
    # the removal (its BEFORE-snapshot carries the committed text). Today the
    # commit never happens here: one emission, and the editor stays open.
    assert len(emitted) == 2
    assert _snapshot_text_of(emitted[0], box_a) == "copied bubble text ke1"
    assert _snapshot_text_of(emitted[1], box_a) == "edited pre delete ke1"

    # The committed text landed in the model via the normal seam.
    assert item_a.pagebox.payload.text == "edited pre delete ke1"
    assert item_a.pagebox.edited is True  # D-04 manual-edit setter ran

    # After the graveyard releases, no later commit can touch the dead state:
    # the editor is closed, so commit() is a safe no-op.
    qtbot.wait(50)
    assert canvas._box_graveyard == []
    canvas._inline_editor.commit()  # must not raise
    assert not canvas._inline_editor.is_active()


# -------------------------------------------------------------- breadcrumbs
@pytest.fixture()
def diag(tmp_path: Path) -> dict[str, Path]:
    """Diagnostics installed into the per-test tmp dir (long hang timeout: the
    heartbeat is not ticking here, so 0.5s would dump spuriously)."""
    log = diagnostics.install(tmp_path, hang_timeout_s=30.0)
    return {"log": log, "hang": tmp_path / "logs" / "mas-hang.log"}


@pytest.fixture(autouse=True)
def _diag_cleanup():
    yield
    diagnostics.reset()


def _read_log(path: Path) -> str:
    logger.complete()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


@pytest.mark.gui
def test_gui_breadcrumbs_reach_mas_log(qtbot, diag) -> None:
    """Every traced path carries one gui-namespace DEBUG breadcrumb, and the
    Task 1 filter admits them into mas.log below the WARNING floor."""
    box_a = Box(20, 20, 120, 120)
    box_b = Box(130, 30, 180, 80)
    canvas = _canvas_with_boxes(
        qtbot,
        [
            PageBox(box=box_a, origin=DETECTED, payload=_box_a_payload()),
            PageBox(box=box_b, origin=USER),
        ],
    )
    item_a, item_b = canvas._box_items

    # copy-text emit breadcrumb
    canvas.mousePressEvent(_press_at(canvas, 70, 70, ctrl=True))
    # _copy_selected_boxes breadcrumb
    item_a.setSelected(True)
    _key(canvas, Qt.Key.Key_C, ctrl=True)
    # delete branch breadcrumb
    _key(canvas, Qt.Key.Key_Delete)
    # graveyard release breadcrumb (needs one loop iteration)
    qtbot.wait(50)
    # paste entry/exit breadcrumbs
    _key(canvas, Qt.Key.Key_V, ctrl=True)
    # InlineEditor commit breadcrumb
    canvas._inline_editor.enter(item_b)
    canvas._inline_editor._text_edit.setPlainText("breadcrumb commit")
    canvas._inline_editor.commit()
    # InlineEditor cancel breadcrumb
    canvas._inline_editor.enter(item_b)
    canvas._inline_editor.cancel()

    text = _read_log(diag["log"])
    expected = (
        "copy_text_requested:",
        "copy_boxes:",
        "delete_key:",
        "paste_entry:",
        "paste_done:",
        "graveyard_release:",
        "inline_editor_commit:",
        "inline_editor_cancel",
    )
    for marker in expected:
        assert marker in text, f"missing breadcrumb: {marker}"
        line = next(ln for ln in text.splitlines() if marker in ln)
        # The logger name must be in the gui namespace for the filter to admit
        # the DEBUG record at all (it IS in the file, so it was admitted —
        # this assertion pins the namespace form itself).
        assert "manga_ai_studio.gui." in line, f"{marker} not gui-namespaced: {line}"


@pytest.mark.gui
def test_main_window_clipboard_write_breadcrumb(qtbot, tmp_path, diag) -> None:
    """MainWindow._on_box_text_copy_requested records the clipboard write."""
    from PIL import Image as PILImage

    page = tmp_path / "page.png"
    PILImage.new("RGB", (64, 64), color=(200, 200, 200)).save(page)
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(tmp_path)
    window.show()
    QApplication.processEvents()

    window._on_box_text_copy_requested("clipboard breadcrumb ke1")

    text = _read_log(diag["log"])
    assert "clipboard_write:" in text
    line = next(ln for ln in text.splitlines() if "clipboard_write:" in ln)
    assert "manga_ai_studio.gui.main_window" in line

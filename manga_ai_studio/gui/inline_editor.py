"""``InlineEditor`` — the transient inline text editor overlay (plan 04-05).

UI-SPEC §15 made concrete: double-click (or F2) a box opens a
``QTextEdit`` overlaid on the box rect (inset 2px so the origin-coloured
border stays visible); the user edits the **current-focus** field
(translation when present, else recognized — D-08); Enter or click-away
commits via the PageBox setter and pushes a BOXES snapshot; Esc cancels;
Shift+Enter inserts a newline. While active, move/resize are disabled
(D-07) via the canvas's mouse-press dispatch guard (canvas.py, Task 2) +
the BoxItem edit-mode flag.

Design decisions honored:

- **§15 widget choice:** a ``QGraphicsProxyWidget`` wrapping a ``QTextEdit``
  (NOT a ``QGraphicsTextItem`` in edit mode) — full cursor/selection/IME
  for Japanese input + frame/background control. First proxy widget in the
  project (RESEARCH "No Analog Found" — the pattern map's fallback).

- **§15 CRITICAL anti-pattern (RESEARCH Pitfall 3):** the proxy is parented
  to the SCENE, never to the BoxItem — parenting to the box would inherit
  its transform and break the editor's coordinate system. The canvas
  mouse-press dispatch checks "editor active? click outside it?" BEFORE any
  other dispatch (RESEARCH Pitfall 3 contract) so click-away commits
  without relying on Qt focus-out signaling alone.

- **§15 z-order:** proxy z=1100, above the brush cursor (z=1000) and the
  create preview (z=900).

- **D-08 focus rule:** the editor edits the current-focus field —
  translation when present (non-empty ``payload.translation``), else
  recognized. The Inspector (plan 04) remains the secondary home for the
  non-focus field.

- **D-04 (T-4-09):** recognized-focus commits route through
  ``PageBox.set_recognized_text_edited`` — the Plan 01 centralized manual-
  edit setter — which writes ``payload.text`` AND sets ``edited=True`` so a
  re-OCR must confirm before overwriting a manual correction. NEVER
  ``set_recognized_text`` (OCR-write path, resets ``edited=False``) and
  NEVER a direct ``payload.text`` write (bypasses the payload-None guard).

- **RESEARCH Pitfall 5:** vertical editing is a v1 no-op — ``payload.vertical``
  is preserved as export metadata but the editor always renders horizontal.
  No rotation, no crash.

- **CR-01 pre-state contract:** a real commit captures the BOXES snapshot
  BEFORE the mutation and detaches the snapshot payloads so the in-place
  setter mutation cannot reach the pre-state (Pitfall 8 push-side —
  ``_materialize_snapshot`` copies at push-time, which runs after this
  mutation). Undo therefore restores the pre-edit text.
"""

from __future__ import annotations

import copy as _copy
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit

if TYPE_CHECKING:
    from manga_ai_studio.gui.box_item import BoxItem


# UI-SPEC §15 editor chrome: background #2d2d33 (Secondary), text #e8e8ea
# (Text primary), 14px Liberation Sans (Body role), 3px #0b0b0e frame (the
# matte — separates the editor from artwork behind it). The font SIZE is NOT
# in the stylesheet (quick-260824-t64 Task 1): it is set programmatically per
# session via a zoom-compensated QFont.setPixelSize — the stylesheet fragment
# would hard-pin 14 scene px, which renders ~3.5 screen px at 25% zoom.
_EDITOR_BG = "#2d2d33"
_EDITOR_TEXT = "#e8e8ea"
_EDITOR_FRAME = "#0b0b0e"
_EDITOR_FONT_FAMILY = "Liberation Sans"
_EDITOR_FONT_SIZE = 14
# quick-260824-t64 Task 1: the zoom-compensated pixel size is capped at this
# many SCENE px at extreme zoom-out (14/0.1 = 140 would be absurd); the floor
# is _EDITOR_FONT_SIZE itself so zoom >= 100% behaves exactly as before.
_EDITOR_FONT_SCENE_PX_MAX = 64
# §15: the editor's outer rect is inset 2px from the box border so the
# origin-coloured border + selection tint stay visible.
_EDITOR_INSET = 2.0


class _EditorTextEdit(QTextEdit):
    """A QTextEdit with the §15 commit/cancel key semantics.

    Bare Enter commits (consumed — Qt's default inserts a newline in some
    configs); Shift+Enter inserts a newline (standard ``QTextEdit``
    convention, delegated to the default handler); Esc cancels. PLAIN text
    only (ASVS V5 — never rich text on OCR output).
    """

    def __init__(self, editor: "InlineEditor") -> None:
        super().__init__()
        self._editor = editor
        self.setAcceptRichText(False)  # ASVS V5 (T-4-07 discipline)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API casing)
        if event.key() == Qt.Key.Key_Escape:
            self._editor.cancel()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter -> newline (standard QTextEdit convention).
                super().keyPressEvent(event)
                return
            # Bare Enter (no modifier) -> commit; consume so QTextEdit does
            # NOT insert a newline.
            self._editor.commit()
            event.accept()
            return
        super().keyPressEvent(event)


class InlineEditor:
    """A transient ``QGraphicsProxyWidget(QTextEdit)`` overlay (UI-SPEC §15).

    NOT itself a ``QGraphicsItem`` — it OWNS a ``QGraphicsProxyWidget``
    parented to the canvas SCENE (the §15 anti-pattern warning: never parent
    to the BoxItem). One instance per canvas, reused + repositioned across
    edit sessions (never two editors on screen).

    The editor mutates the model ONLY through the PageBox setters
    (``set_translation`` / ``set_recognized_text_edited``) and pushes the
    BOXES pre-state snapshot through the canvas's ``boxes_modified`` signal
    — the same undo seam every other box edit uses (CR-01).
    """

    def __init__(self, canvas) -> None:
        self._canvas = canvas
        scene = canvas.scene()
        # Lazy creation is not needed (one editor per canvas lifetime), but
        # the proxy stays hidden until enter().
        self._proxy = QGraphicsProxyWidget()
        scene.addItem(self._proxy)
        self._text_edit = _EditorTextEdit(self)
        self._text_edit.setObjectName("inline_editor")
        self._text_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {_EDITOR_BG}; color: {_EDITOR_TEXT}; "
            f"border: 3px solid {_EDITOR_FRAME}; font-family: '{_EDITOR_FONT_FAMILY}'; }}"
        )
        self._proxy.setWidget(self._text_edit)
        self._proxy.setZValue(1100)  # UI-SPEC §Z-order: above cursor z=1000
        self._proxy.hide()
        # Edit-session state. _focus_field is "recognized" or "translation"
        # (D-08); _entry_text is the text at entry, so commit() can detect a
        # no-op (unchanged) edit and cancel() can discard.
        self._active_box_item: "BoxItem | None" = None
        self._focus_field: str | None = None
        self._entry_text: str = ""

    # ------------------------------------------------------------ public API
    def enter(self, box_item: "BoxItem") -> None:
        """Open (or reposition) the editor on ``box_item`` (D-05).

        Computes the D-08 focus field (translation when present, else
        recognized), populates the QTextEdit with the current text, positions
        the proxy on the box rect (inset 2px), focuses it, and disables the
        box's move/resize interaction (D-07).

        One instance at a time (§15): if the editor is already active on a
        DIFFERENT box, the previous edit commits first (safer than
        discarding the user's work). Re-entering the SAME box just re-focuses
        — uncommitted text is preserved.
        """
        if self._active_box_item is not None:
            if self._active_box_item is box_item:
                self._text_edit.setFocus()
                return
            # A different box: commit the previous edit first.
            self.commit()
        self._active_box_item = box_item
        pagebox = box_item.pagebox
        # D-08 current-focus rule: translation wins once present.
        has_translation = pagebox.payload is not None and bool(
            getattr(pagebox.payload, "translation", "") or ""
        )
        self._focus_field = "translation" if has_translation else "recognized"
        current = self._current_focus_text(pagebox)
        self._entry_text = current
        self._text_edit.setPlainText(current)
        # Position + size on the box rect, inset 2px (§15). The box rect is
        # the editor's container: width/height shrink by 2 * inset so the
        # origin-coloured border stays visible around the editor.
        rect = box_item.sceneBoundingRect()
        self._proxy.setPos(rect.left() + _EDITOR_INSET, rect.top() + _EDITOR_INSET)
        w = max(rect.width() - 2 * _EDITOR_INSET, 1.0)
        h = max(rect.height() - 2 * _EDITOR_INSET, 1.0)
        self._text_edit.setMinimumSize(int(w), int(h))
        self._proxy.resize(w, h)
        # quick-260824-t64 Task 1: zoom-compensated editor font. The proxy is
        # NOT ItemIgnoresTransformations (it must track the box rect in scene
        # coords), so a stylesheet-fixed 14px renders 14*zoom screen px —
        # ~3.5 px at 25% zoom. Compensate inversely: scene px = base / zoom,
        # floored at the base (zoom >= 100% is byte-identical to before) and
        # capped at 64 scene px at extreme zoom-out. One font source of truth:
        # the programmatic QFont (the stylesheet no longer pins a size).
        zoom = getattr(self._canvas, "zoom_factor", 1.0)
        if not isinstance(zoom, (int, float)) or zoom <= 0:
            zoom = 1.0
        pixel = max(
            _EDITOR_FONT_SIZE, min(float(_EDITOR_FONT_SCENE_PX_MAX), round(_EDITOR_FONT_SIZE / zoom))
        )
        font = QFont(self._text_edit.font())
        font.setPixelSize(int(pixel))
        self._text_edit.setFont(font)
        self._proxy.show()
        self._text_edit.setFocus()
        # D-07: disable move/resize while editing.
        box_item.set_edit_mode(True)

    def commit(self) -> None:
        """Commit the active edit (D-05): write the focus field via the PageBox
        setter and push a BOXES snapshot. No-op when no editor is active; an
        unchanged edit is a silent no-op (hide, no push).
        """
        if self._active_box_item is None:
            return
        box_item = self._active_box_item
        new_text = self._text_edit.toPlainText()
        changed = new_text != self._entry_text
        if changed:
            # CR-01 pre-state pattern: capture the snapshot BEFORE the
            # mutation. The snapshot PageBoxes share the live TextBlock by
            # reference, and the setters mutate it in place — so detach the
            # snapshot payloads here, or the push-time copy (which runs AFTER
            # the mutation, inside history.push_boxes_state) would capture the
            # NEW text and undo would restore a no-op (Pitfall 8 push-side).
            before = self._canvas.boxes_snapshot()
            for pb in before:
                if pb.payload is not None:
                    pb.payload = _copy.copy(pb.payload)
            if self._focus_field == "translation":
                # D-13 MT seam; does NOT touch the D-04 edited flag.
                box_item.pagebox.set_translation(new_text)
            else:
                # D-04: the centralized manual-edit setter (Plan 01) — writes
                # payload.text + sets edited=True with the payload-None guard.
                box_item.pagebox.set_recognized_text_edited(new_text)
            # Refresh the display objects so the canvas reflects the edit at
            # once (the text overlay re-renders the current-focus text).
            box_item.refresh_text_overlay()
            box_item.refresh_badge()
            self._canvas.boxes_modified.emit(before)
        self._teardown()

    def cancel(self) -> None:
        """Cancel the active edit (Esc): discard edits since entry, hide the
        proxy, NO boxes_modified emit (D-05). No-op when no editor is active.
        """
        if self._active_box_item is None:
            return
        self._teardown()

    def is_active(self) -> bool:
        """True while an edit session is open."""
        return self._active_box_item is not None

    def proxy_scene_rect(self) -> QRectF:
        """The proxy's scene-space rect — the canvas guard's hit-test target
        for "is this click inside the editor?" (RESEARCH Pitfall 3)."""
        return self._proxy.sceneBoundingRect()

    # --------------------------------------------------------------- helpers
    def _current_focus_text(self, pagebox) -> str:
        """Read the current text of the FOCUS field off the pagebox.

        The focus field is whatever :meth:`enter` computed (D-08): translation
        when present, else recognized. Defensive against a non-TextBlock
        payload (a bare marker object): both fields yield empty instead of
        AttributeError (mirrors ``BoxItem._current_focus_text``'s getattr
        discipline). ``TextBlock.text`` may be str OR list (textblock.py:65) —
        a list is joined.
        """
        payload = pagebox.payload
        if payload is None:
            return ""
        if self._focus_field == "translation":
            return getattr(payload, "translation", "") or ""
        t = getattr(payload, "text", None)
        if isinstance(t, list):
            return "".join(str(s) for s in t)
        return t if t is not None else ""

    def _teardown(self) -> None:
        """Hide the proxy, restore the box's move/resize, clear session state."""
        box_item = self._active_box_item
        if box_item is not None:
            box_item.set_edit_mode(False)
        self._proxy.hide()
        self._active_box_item = None
        self._focus_field = None
        self._entry_text = ""

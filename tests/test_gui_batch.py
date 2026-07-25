"""GUI tests for the Phase 2 per-page mask persistence (D-11 / FLOW-03).

This is the Phase 2 FLOW-03 (D-11) GUI wiring suite: the load-bearing data-model
change that makes the two-stage batch workflow possible. Phase 1's canvas holds
ONE mask for the *current* page in ``EditorCanvas._mask``, and
``MainWindow.on_page_selected -> reset_history`` discards canvas state on every
page switch. Plan 02-02 lifts mask state onto ``ImageFile.mask`` (whose slot
already exists but was unused for persistence) and saves/restores it at the
``on_page_selected`` boundary so that Batch Detect (Plan 03) can store one mask
per page and Batch Clean (Plan 03) can read them all back.

The three tests here lock the contract:

* ``test_on_page_selected_persists_outgoing_mask`` — navigating FROM a page
  with a painted mask leaves that page's ``ImageFile.mask`` non-None (the
  OUTGOING save side of the seam).
* ``test_mask_survives_navigation`` — navigating away and BACK restores the
  page's mask onto the canvas (the INCOMING restore side of the seam).
* ``test_mask_persistence_uses_copy`` — Pitfall-2 regression guard: mutating
  the canvas mask AFTER persistence must NOT retroactively alter the stored
  ``ImageFile.mask``. The boundary ``.copy()`` (mirroring the Phase 1
  ``test_inpaint_result_display_uses_copy`` discipline) detaches the buffer.

The helpers below are copied VERBATIM from
``tests/test_inpainting/test_inpaint_gui.py`` (lines 43-83) — they are public
test infra and copying keeps the suite self-contained (the Phase 1 convention
is that each test module owns its helpers).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QImage, QPainter, QPixmap  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.core.mask_editor import mask_to_numpy_binary  # noqa: E402
from manga_ai_studio.gui.canvas import EditorCanvas  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (copied from tests/test_inpainting/test_inpaint_gui.py:43-83)
# ---------------------------------------------------------------------------


def _make_window(qtbot, tmp_path):
    """Build a MainWindow wired to a profile manager in tmp_path."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _open_page(window: MainWindow, tmp_path: Path, size: int = 16) -> Path:
    """Open a solid-white page into the window so the canvas has an image."""
    img_path = tmp_path / "page.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(img_path))
    window._open_single_image(img_path)
    return img_path


def _paint_mask_on_canvas(canvas: EditorCanvas) -> None:
    """Paint a small mask region (a 4x4 block) onto the canvas via set_mask.

    Uses the same path as detection: a grayscale QImage with non-zero pixels.
    """
    mask = QImage(canvas.image_item.pixmap().size(), QImage.Format.Format_Grayscale8)
    mask.fill(0)
    from PySide6.QtGui import QPainter

    painter = QPainter(mask)
    painter.setPen(QColor(255, 255, 255))
    # Paint a 4x4 region at (4,4)-(7,7).
    for x in range(4, 8):
        for y in range(4, 8):
            painter.drawPoint(x, y)
    painter.end()
    canvas.set_mask(mask)


def _load_two_pages(window: MainWindow, tmp_path: Path, size: int = 16) -> tuple[Path, Path]:
    """Load a folder of two PNG pages into ``window.image_files``.

    Drives the same multi-page navigation path Batch Detect/Clean will use:
    write two pages, call ``window._load_folder(tmp_path)`` so the sidebar
    populates two entries, then ``_set_pages`` auto-selects page_a (the first
    page). Subsequent navigation uses
    ``file_table.select_path(path)`` + ``on_page_selected(path)`` (the
    sequence ``_set_pages`` itself uses at main_window.py:555-556).
    """
    page_a = tmp_path / "page_a.png"
    page_b = tmp_path / "page_b.png"
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    img.save(str(page_a))
    img.save(str(page_b))
    window._load_folder(tmp_path)
    return page_a, page_b


# ---------------------------------------------------------------------------
# Test 1: OUTGOING persistence (D-11 seam step 1)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_on_page_selected_persists_outgoing_mask(qtbot, tmp_path) -> None:
    """Painting a mask on page 1 then selecting page 2 persists page 1's mask.

    Behavior: on_page_selected captures the OUTGOING page's canvas mask into
    ImageFile.mask BEFORE the page switch. After navigating to page 2, page 1's
    ImageFile.mask must be non-None (the D-11 seam step 1).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    # Page a is the auto-selected first page (verify).
    assert window._current_page_index() == 0

    # Paint a mask on page_a via the canvas.
    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask must be set"

    # Navigate to page_b via the same call sequence _set_pages uses.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)

    # The OUTGOING page (index 0, page_a) must have its mask persisted.
    assert window.image_files[0].mask is not None, (
        "outgoing page's ImageFile.mask must be non-None after navigation"
    )
    # Sanity: the new current page is page_b.
    assert window._current_page_index() == 1


# ---------------------------------------------------------------------------
# Test 2: INCOMING restore (D-11 seam step 4) — the survival crux
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_mask_survives_navigation(qtbot, tmp_path) -> None:
    """Detect/paint on page 1, navigate to page 2 and back; mask survives.

    Behavior: after navigating away from page 1 then back, page 1's
    ImageFile.mask is non-None AND the canvas has the mask restored on it
    (canvas.has_mask() True) — the D-11 seam step 4 (INCOMING restore).
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask must be set"

    # Navigate away to page_b, then back to page_a.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)

    # The persisted mask survived on page 1's ImageFile.
    assert window.image_files[0].mask is not None, (
        "page 1's ImageFile.mask must survive a round-trip navigation"
    )
    # The INCOMING mask was restored onto the canvas (D-11 seam step 4).
    assert window.canvas.has_mask() is True, (
        "the canvas must have the mask restored after returning to page 1"
    )


# ---------------------------------------------------------------------------
# Test 3: Pitfall-2 regression guard (.copy() at the boundary)
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_mask_persistence_uses_copy(qtbot, tmp_path) -> None:
    """Mutating the canvas after persistence does NOT alter ImageFile.mask.

    Regression guard (Pitfall 2 / RESEARCH §Shared Pattern 5): the boundary
    ``.copy()`` detaches the persisted mask from the live canvas buffer. After
    navigating away (which persists page_a's mask) and back, re-painting the
    canvas differently must NOT retroactively change the stored ImageFile.mask.
    Mirrors the Phase 1 ``test_inpaint_result_display_uses_copy`` discipline.
    """
    window = _make_window(qtbot, tmp_path)
    page_a, page_b = _load_two_pages(window, tmp_path)

    _paint_mask_on_canvas(window.canvas)
    assert window.canvas.has_mask() is True, "precondition: mask must be set"

    # Persist page_a's mask by navigating away.
    window.file_table.select_path(page_b)
    window.on_page_selected(page_b)
    assert window.image_files[0].mask is not None, (
        "precondition: page_a mask must have persisted"
    )

    # Snapshot the persisted mask BEFORE further mutation.
    saved_bytes = mask_to_numpy_binary(window.image_files[0].mask).tobytes()

    # Navigate back to page_a and CLEAR the canvas mask (a different content).
    window.file_table.select_path(page_a)
    window.on_page_selected(page_a)
    # Overwrite the canvas with a DIFFERENT mask (all-zero via clear or re-fill).
    window.canvas.clear_mask()

    # The stored ImageFile.mask must be byte-identical to the snapshot — the
    # boundary .copy() detached it so post-persistence canvas mutation cannot
    # reach back through the shared buffer.
    after_bytes = mask_to_numpy_binary(window.image_files[0].mask).tobytes()
    assert after_bytes == saved_bytes, (
        "Pitfall-2 regression: mutating the canvas after persistence altered "
        "the stored ImageFile.mask — the boundary .copy() is missing."
    )

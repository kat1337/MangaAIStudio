"""GUI tests for the panel's Edit section (plan 09-03, UI-05/D-08).

Covers the Task 1 contract:

- The panel's FOURTH section is titled "Edit" and its body is a 2-column
  QGridLayout of exactly SIX text QToolButtons (D-02 workflow order
  Detection settings → Brush → Typesetting → Edit).
- Every button's ``defaultAction()`` IDENTITY-equals the corresponding live
  window QAction (Curves… / Crop… dialog / Resize… / Rotate CW / CCW / 180°)
  — no lambdas, no re-created actions.
- Trigger parity: clicking a button reaches the SAME MainWindow handler the
  old menu entry invoked (spy on the handler; zero new op logic).
- Gating parity: all six buttons start DISABLED on a fresh window and enable
  after a page load — inherited from ``_refresh_action_states`` through the
  default-action binding.

The Edit section carries the D-02 persistence key
``sidePanel/editExpanded`` through the generic CollapsibleSection mechanism.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QGridLayout, QToolButton  # noqa: E402

from manga_ai_studio.config.profile_manager import ProfileManager  # noqa: E402
from manga_ai_studio.gui.main_window import MainWindow  # noqa: E402
from manga_ai_studio.gui.side_panel import CollapsibleSection  # noqa: E402


def _window(qtbot, tmp_path) -> MainWindow:
    """A fresh MainWindow over a tmp-dir ProfileManager."""
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    return window


def _window_with_page(qtbot, tmp_path) -> MainWindow:
    """A MainWindow with one real page open (the canvas shows the page)."""
    from PIL import Image as PILImage

    folder = tmp_path / "chapter"
    folder.mkdir(parents=True, exist_ok=True)
    PILImage.new("RGB", (60, 40), color=(40, 80, 120)).save(folder / "page_01.png")
    pm = ProfileManager(tmp_path / "config")
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(folder)
    QApplication.processEvents()
    return window


def _edit_section(window: MainWindow) -> CollapsibleSection:
    """The panel's 'Edit' CollapsibleSection."""
    sections = [s for s in window.side_panel.sections if s.title == "Edit"]
    assert len(sections) == 1, f"expected exactly one Edit section, got {sections}"
    return sections[0]


def _edit_buttons(window: MainWindow) -> list[QToolButton]:
    """The six QToolButtons of the Edit section body, in layout order."""
    body = _edit_section(window).body
    buttons = body.findChildren(QToolButton)
    return buttons


# ===========================================================================
# Structure — fourth section, 2-column grid of exactly six text buttons
# ===========================================================================


@pytest.mark.gui
def test_edit_section_is_fourth_in_workflow_order(qtbot, tmp_path) -> None:
    """Section order completes D-02: Detection settings → Brush → Typesetting
    → Edit, and the Edit section carries the editExpanded persistence key."""
    window = _window(qtbot, tmp_path)

    titles = [s.title for s in window.side_panel.sections]
    assert titles == ["Detection settings", "Brush", "Typesetting", "Edit"]

    section = _edit_section(window)
    assert isinstance(section, CollapsibleSection)
    assert section.settings_key == "sidePanel/editExpanded"
    # Expanded by default on first run (D-02).
    assert section.header.isChecked()


@pytest.mark.gui
def test_edit_body_is_two_column_grid_of_six_text_buttons(qtbot, tmp_path) -> None:
    """The Edit body lays out EXACTLY six QToolButtons in a 2-column grid,
    each rendered text-only (labels come from the actions)."""
    window = _window(qtbot, tmp_path)

    body = _edit_section(window).body
    buttons = _edit_buttons(window)
    assert len(buttons) == 6, f"expected 6 buttons, found {len(buttons)}"

    grids = body.findChildren(QGridLayout)
    assert len(grids) == 1, "the Edit body should own exactly one QGridLayout"
    grid = grids[0]

    rows: set[int] = set()
    cols: set[int] = set()
    for btn in buttons:
        idx = grid.indexOf(btn)
        assert idx != -1, "button not managed by the Edit grid"
        row, col, _, _ = grid.getItemPosition(idx)
        rows.add(row)
        cols.add(col)
    # 2-column grid over three rows.
    assert cols == {0, 1}
    assert rows == {0, 1, 2}
    for btn in buttons:
        assert btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextOnly


# ===========================================================================
# Default-action identity
# ===========================================================================


@pytest.mark.gui
def test_buttons_default_action_identity(qtbot, tmp_path) -> None:
    """Each button's defaultAction() identity-equals its LIVE window action."""
    window = _window(qtbot, tmp_path)

    expected = [
        window.action_curves,
        window.action_crop_dialog,
        window.action_resize,
        window.action_rotate_cw,
        window.action_rotate_ccw,
        window.action_rotate_180,
    ]
    bound = [btn.defaultAction() for btn in _edit_buttons(window)]
    assert bound == expected
    # Identity, not equality: the SAME objects, never copies.
    for btn, act in zip(_edit_buttons(window), expected):
        assert btn.defaultAction() is act


@pytest.mark.gui
def test_crop_tool_and_crop_dialog_stay_distinct(qtbot, tmp_path) -> None:
    """D-08: the strip hosts the interactive Crop TOOL (action_tool_crop);
    the Edit section hosts ONLY the numeric Crop… dialog entry
    (action_crop_dialog) — two distinct actions, two distinct buttons."""
    window = _window(qtbot, tmp_path)

    dialog_btn = next(
        btn
        for btn in _edit_buttons(window)
        if btn.defaultAction() is window.action_crop_dialog
    )
    assert dialog_btn.defaultAction() is not window.action_tool_crop
    assert dialog_btn.defaultAction().text().startswith("Crop")

    # The strip still carries the TOOL button — its own strip-owned action
    # carrying ToolMode.CROP data (09-01 contract), never the dialog action.
    from manga_ai_studio.gui.canvas import ToolMode

    strip_actions = [
        b.defaultAction()
        for b in window.tools_strip.findChildren(QToolButton)
        if b.defaultAction() is not None
    ]
    assert any(a.data() == ToolMode.CROP for a in strip_actions)
    assert window.action_crop_dialog not in strip_actions


# ===========================================================================
# Trigger parity — a click reaches the same handler as the old menu entry
# ===========================================================================


@pytest.mark.gui
def test_curves_button_click_reaches_on_curves(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Clicking the Curves… button invokes the same ``_on_curves`` handler the
    retired Tools-menu entry invoked (spy on the class method BEFORE the
    window is constructed — the triggered connect captures the bound method
    at construction time)."""
    calls: list[str] = []

    def spy(self) -> None:  # pragma: no cover - replaced wholesale below
        calls.append("curves")

    monkeypatch.setattr(MainWindow, "_on_curves", spy)
    window = _window_with_page(qtbot, tmp_path)

    curves_btn = next(
        btn
        for btn in _edit_buttons(window)
        if btn.defaultAction() is window.action_curves
    )
    assert curves_btn.isEnabled()
    curves_btn.click()
    QApplication.processEvents()
    assert calls == ["curves"]


@pytest.mark.gui
def test_crop_dialog_button_click_reaches_on_crop_dialog(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Clicking the Crop… dialog button invokes ``_on_crop_dialog`` — the
    numeric-dialog path, NOT the crop-tool activation."""
    calls: list[str] = []

    def spy(self) -> None:  # pragma: no cover - replaced wholesale below
        calls.append("crop_dialog")

    monkeypatch.setattr(MainWindow, "_on_crop_dialog", spy)
    window = _window_with_page(qtbot, tmp_path)

    crop_btn = next(
        btn
        for btn in _edit_buttons(window)
        if btn.defaultAction() is window.action_crop_dialog
    )
    crop_btn.click()
    QApplication.processEvents()
    assert calls == ["crop_dialog"]


@pytest.mark.gui
def test_rotate_button_click_rotates_page(qtbot, tmp_path) -> None:
    """A rotate button drives the REAL rotation (the same ``_rotate_page``
    handler as the retired Tools ▸ Rotate submenu entries): the canvas image
    dims swap after a 90° CW press — zero new op logic behind the button."""
    window = _window_with_page(qtbot, tmp_path)
    before = window.canvas.get_image_numpy().shape
    cw_btn = next(
        btn
        for btn in _edit_buttons(window)
        if btn.defaultAction() is window.action_rotate_cw
    )
    cw_btn.click()
    QApplication.processEvents()
    after = window.canvas.get_image_numpy().shape
    # 90° rotation swaps the page dimensions (real op, zero new logic).
    assert after == (before[1], before[0]) + before[2:]


# ===========================================================================
# Gating parity — disabled on fresh window, enabled after page load
# ===========================================================================


@pytest.mark.gui
def test_all_six_buttons_start_disabled_then_follow_gating(
    qtbot, tmp_path
) -> None:
    """With no page open all six default-action buttons are disabled;
    after a page load (and _refresh_action_states) they enable — gating is
    inherited, no button-side mirror code exists."""
    window = _window(qtbot, tmp_path)
    buttons = _edit_buttons(window)

    for btn in buttons:
        assert not btn.isEnabled(), f"{btn.text()} should start disabled"

    loaded = _window_with_page(qtbot, tmp_path)
    for btn in _edit_buttons(loaded):
        assert btn.isEnabled(), f"{btn.text()} should enable after page load"

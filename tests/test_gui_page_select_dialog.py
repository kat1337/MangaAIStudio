"""GUI tests for ``PageSelectionDialog`` (quick-260828-k4q Task 1).

The modal page picker for Batch → Export Typeset Pages…: one checkable row
per page in file order, ALL CHECKED by default, ``selected_indices()`` as the
only result surface, Export disabled on an empty selection, Select All/None
conveniences, and the pure-collector contract (no MainWindow state touched —
constructed here with ``parent=None``).

Tests drive the methods DIRECTLY (never ``exec()``) — the established
pytest-qt discipline for collector dialogs.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from manga_ai_studio.gui.page_select_dialog import (  # noqa: E402
    PageSelectionDialog,
)

_NAMES = ["page_01.png", "page_02.png", "page_03.png"]


def _make_dialog(qtbot, names: list[str]) -> PageSelectionDialog:
    """A picker wired into pytest-qt's lifetime management."""
    dialog = PageSelectionDialog(page_names=names)
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.gui
def test_all_rows_checked_by_default(qtbot) -> None:
    """One checkable row per name in order; ALL start checked; the
    selected_indices() surface reports [0..n-1] for 3 names."""
    dialog = _make_dialog(qtbot, _NAMES)

    assert dialog.page_list.count() == 3
    for i, expected_name in enumerate(_NAMES):
        item = dialog.page_list.item(i)
        assert item.text() == expected_name
        assert item.checkState() == Qt.CheckState.Checked
        assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert dialog.selected_indices() == [0, 1, 2]
    assert dialog.export_btn.isEnabled(), "default selection exports"


@pytest.mark.gui
def test_uncheck_row_drops_index(qtbot) -> None:
    """Unchecking row 1 removes exactly index 1 from selected_indices()."""
    dialog = _make_dialog(qtbot, _NAMES)

    dialog.page_list.item(1).setCheckState(Qt.CheckState.Unchecked)

    assert dialog.selected_indices() == [0, 2]
    assert dialog.export_btn.isEnabled(), "2 pages still checked"


@pytest.mark.gui
def test_select_none_disables_export_select_all_restores(qtbot) -> None:
    """Select None -> no checked rows AND the Export button disables;
    Select All -> every row checked + Export enabled again."""
    dialog = _make_dialog(qtbot, _NAMES)

    dialog.select_none_btn.click()
    assert dialog.selected_indices() == []
    assert dialog.export_btn.isEnabled() is False, (
        "an empty selection must not export (nothing would be written)"
    )

    dialog.select_all_btn.click()
    assert dialog.selected_indices() == [0, 1, 2]
    for i in range(dialog.page_list.count()):
        assert dialog.page_list.item(i).checkState() == Qt.CheckState.Checked
    assert dialog.export_btn.isEnabled() is True


@pytest.mark.gui
def test_single_and_empty_page_lists(qtbot) -> None:
    """Single-page and empty-list construction do not raise; an empty list
    leaves Export disabled (nothing selectable)."""
    single = _make_dialog(qtbot, ["page_01.png"])
    assert single.page_list.count() == 1
    assert single.selected_indices() == [0]
    assert single.export_btn.isEnabled()

    empty = _make_dialog(qtbot, [])
    assert empty.page_list.count() == 0
    assert empty.selected_indices() == []
    assert empty.export_btn.isEnabled() is False


@pytest.mark.gui
def test_modal_pure_collector(qtbot) -> None:
    """The dialog is ApplicationModal and a pure collector: constructed with
    parent=None (no MainWindow), it never touches window state —
    ``selected_indices()`` is the only result surface and no ``result``
    attribute is stored (it would shadow QDialog.result())."""
    dialog = _make_dialog(qtbot, _NAMES)

    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert dialog.parent() is None
    assert not hasattr(dialog, "result_values"), (
        "a picker carries no constructor-carried result state — "
        "selected_indices() is the accessor"
    )

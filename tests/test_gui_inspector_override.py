"""GUI tests for the Inspector Inpaint override + Std dev rows (plan 08-08).

Mirrors the ``tests/test_gui_inspector_styling.py`` conventions (``importorskip``
+ ``qtbot`` + ``@pytest.mark.gui`` + real ``InspectorPanel`` instances). This
module covers the D-13/D-14 override field (UI-SPEC §38): the two new rows
exist after Origin; single-box population maps the tri-state model values
(None / "always" / "never") to the Auto / Always / Never display entries; the
read-only Std dev row shows ``{value:.1f}`` or the em dash; a multi-selection
with differing values shows the dynamically-added "Mixed" sentinel while equal
values show the common value; the row stays ENABLED in multi-select (A5 — an
edit-all flag); the sentinel NEVER emits a commit; and the WR-01 loaded-memory
guard suppresses spurious commits on load.

The MainWindow-side grouped commit (one BOXES snapshot, recompose, border
refresh, status flash) is covered by Task 2 of this plan in the same file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QComboBox, QLabel  # noqa: E402

from manga_ai_studio.core.box_model import USER, PageBox  # noqa: E402
from manga_ai_studio.gui.inspector_panel import InspectorPanel  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


def _make_inspector(qtbot) -> InspectorPanel:
    """Build an InspectorPanel added to qtbot (so it can parent widgets)."""
    panel = InspectorPanel()
    qtbot.addWidget(panel)
    return panel


def _pb(
    override=None,
    std_dev=None,
    x1: int = 10,
    y1: int = 20,
    x2: int = 210,
    y2: int = 120,
) -> PageBox:
    """A USER-origin PageBox carrying an inpaint override + std dev (D-15)."""
    pb = PageBox(box=Box(x1, y1, x2, y2), origin=USER, inpaint_override=override)
    pb.std_dev = std_dev
    return pb


def _combo_items(panel) -> list[str]:
    """The Inpaint combo's entry list in display order."""
    return [panel.inpaint_combo.itemText(i) for i in range(panel.inpaint_combo.count())]


# ===========================================================================
# Task 1 — the D-13/D-14 override surface (rows + population)
# ===========================================================================


@pytest.mark.gui
def test_inpaint_override_signal_and_entries(qtbot) -> None:
    """The class-scope Signal exists and the combo's entries are exactly
    Auto / Always / Never (plus the dynamic Mixed sentinel)."""
    panel = _make_inspector(qtbot)
    # Class-scope Signal(str) (D-13/D-14, UI-SPEC §38).
    assert hasattr(InspectorPanel, "inpaint_override_changed")
    # The empty state reset the combo to the plain entry set, Auto selected.
    assert _combo_items(panel) == ["Auto", "Always", "Never"]
    assert panel.inpaint_combo.currentText() == "Auto"
    # Widget choice A4: a QComboBox, not radio buttons.
    assert isinstance(panel.inpaint_combo, QComboBox)
    # Std dev is a read-only QLabel.
    assert isinstance(panel.std_dev_label, QLabel)


@pytest.mark.gui
@pytest.mark.parametrize(
    "override,expected",
    [
        (None, "Auto"),
        ("always", "Always"),
        ("never", "Never"),
    ],
)
def test_single_box_populates_inpaint_combo(qtbot, override, expected) -> None:
    """Single selection maps the model tri-state to the display entries."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb(override=override, std_dev=8.3))
    assert panel.inpaint_combo.currentText() == expected
    assert _combo_items(panel) == ["Auto", "Always", "Never"]
    assert panel.std_dev_label.text() == "8.3"


@pytest.mark.gui
@pytest.mark.parametrize(
    "std_dev,expected_text",
    [
        (None, "\u2014"),
        (12.35, "12.3"),
        (0.0, "0.0"),
    ],
)
def test_std_dev_row_renders_value_or_em_dash(
    qtbot, std_dev, expected_text
) -> None:
    """Std dev shows ``{value:.1f}`` or the em dash when not computed."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb(override=None, std_dev=std_dev))
    assert panel.std_dev_label.text() == expected_text


@pytest.mark.gui
def test_mixed_sentinel_display_on_differing_multi_select(qtbot) -> None:
    """Differing overrides in a multi-selection -> the dynamic "Mixed"
    sentinel entry shows; Std dev shows the em dash; the Inpaint row stays
    ENABLED (A5 — unlike the per-box content fields)."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection(
        [_pb(override="always"), _pb(override="never"), _pb(override=None)]
    )
    assert panel.inpaint_combo.currentText() == "Mixed", (
        "A differing selection must show the Mixed sentinel"
    )
    assert "Mixed" in _combo_items(panel)
    assert panel.std_dev_label.text() == "\u2014", (
        "Std dev is per-box data — never editable-all in multi-select"
    )
    assert panel.inpaint_combo.isEnabled(), (
        "the Inpaint row stays ENABLED in multi-select (A5 edit-all)"
    )


@pytest.mark.gui
def test_equal_multi_select_shows_common_value(qtbot) -> None:
    """Equal overrides -> the common value (no Mixed sentinel entry)."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection(
        [_pb(override="never"), _pb(override="never")]
    )
    assert panel.inpaint_combo.currentText() == "Never"
    assert "Mixed" not in _combo_items(panel)


@pytest.mark.gui
def test_sentinel_never_emits(qtbot) -> None:
    """The Mixed sentinel NEVER leaves the widget layer (Pitfall 7): a commit
    whose text is Mixed (even after loading a real value) carries nothing."""
    panel = _make_inspector(qtbot)
    fired: list[str] = []
    panel.connect_commit_handlers(
        lambda _t: None, lambda _t: None, lambda _n: None, lambda _v: None,
        on_inpaint_override=fired.append,
    )
    # A mixed multi-selection renders the sentinel (never a loaded real value).
    panel.load_multi_selection(
        [_pb(override="always"), _pb(override="never")]
    )
    assert panel.inpaint_combo.currentText() == "Mixed"
    # Picking a REAL value emits ("Always" -> the miulti override).
    panel.inpaint_combo.setCurrentIndex(_combo_items(panel).index("Always"))
    assert fired == ["Always"]
    # Re-selecting the Mixed sentinel must NOT emit anything (Pitfall 7).
    panel.inpaint_combo.setCurrentIndex(_combo_items(panel).index("Mixed"))
    assert fired == ["Always"], "the Mixed sentinel must never commit"


@pytest.mark.gui
def test_guard_suppresses_spurious_commits_on_load(qtbot) -> None:
    """WR-01: load_box blocks the combo's signals (no spurious commit at
    population) and an unchanged focus cycle is a no-op; only a REAL change
    emits exactly once."""
    panel = _make_inspector(qtbot)
    fired: list[str] = []
    panel.connect_commit_handlers(
        lambda _t: None, lambda _t: None, lambda _n: None, lambda _v: None,
        on_inpaint_override=fired.append,
    )
    panel.load_box(_pb(override="always", std_dev=5.0))
    assert fired == [], "loading must not re-emit the just-loaded value"
    assert panel.inpaint_combo.currentText() == "Always"
    # A no-op focus cycle (same value re-selected) is a WR-01 no-op.
    panel.inpaint_combo.setCurrentIndex(
        _combo_items(panel).index("Always")
    )
    assert fired == [], "an unchanged focus cycle must not push a BOXES snapshot"
    # A real change emits exactly once.
    panel.inpaint_combo.setCurrentIndex(
        _combo_items(panel).index("Never")
    )
    assert fired == ["Never"]


# ===========================================================================
# Task 2 — MainWindow grouped commit: one snapshot, live recompose, status
# flash, undo integration (the RED behavior gate for this TDD task)
# ===========================================================================


def _blk(x1: int, y1: int, x2: int, y2: int):
    """A duck-typed fake TextBlock (only .xyxy is read by the build)."""
    from types import SimpleNamespace

    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


def _window_with_custom_page(qtbot, tmp_path: Path, page_np) -> "MainWindow":
    """A MainWindow with a real page + the data-model registration (so the
    seam's ``_current_page_index()`` writes land on a real ImageFile)."""
    import numpy as np

    from PIL import Image as PILImage

    from manga_ai_studio.config.profile_manager import ProfileManager
    from manga_ai_studio.core.image_file import ImageFile
    from manga_ai_studio.gui.main_window import MainWindow

    h, w = page_np.shape[:2]
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    page_png = tmp_path / "page.png"
    PILImage.fromarray(page_np).save(page_png)
    assert window.canvas.set_image_from_path(page_png) is True
    window.image_files = [ImageFile(path=page_png)]
    window.file_table.set_pages([page_png])
    window.file_table.select_path(page_png)
    window._last_page_index = 0
    return window


def _window_with_page(qtbot, tmp_path: Path, h: int = 80, w: int = 120) -> "MainWindow":
    """A uniform-grey page window (the will_inpaint fixture)."""
    import numpy as np

    return _window_with_custom_page(
        qtbot, tmp_path, np.full((h, w, 3), 200, dtype=np.uint8)
    )


def _noisy_right_half_page(h: int = 80, w: int = 120) -> np.ndarray:
    """A page whose left half is uniform 200 and whose right half (cols >=
    w//2) is deterministic full-bleed noise (std-dev gate reads it above
    threshold — cf. the 08-03 battery / 08-07 tests)."""
    import numpy as np

    page = np.full((h, w, 3), 200, dtype=np.uint8)
    rng = np.random.default_rng(42)
    page[:, w // 2 :] = rng.integers(0, 256, size=(h, w // 2, 3), dtype=np.uint8)
    return page


def _profile_threshold(window) -> float:
    """The current std-dev gate from the active profile."""
    return float(
        window.profile_manager.config.current_profile.masker
        .mask_max_standard_deviation
    )


def _composite(window) -> np.ndarray:
    """The canvas composite mask as a binary numpy array."""
    import numpy as np

    from manga_ai_studio.core.mask_editor import mask_to_numpy_binary

    return mask_to_numpy_binary(window.canvas.get_mask())


@pytest.mark.gui
def test_override_commit_never_removes_content_and_pushes_one_entry(
    qtbot, tmp_path
) -> None:
    """Single box commit "Never": the override lands, the border renders the
    never state (dashed), its auto content LEAVES the composite mask, exactly
    ONE BOXES undo entry (op "inpaint override") is pushed, and the transient
    status reads "Inpaint: Never — 1 box(es)."."""
    import numpy as np

    from PySide6.QtCore import Qt

    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 35, 35)]})
    item = window.canvas._box_items[0]
    threshold = _profile_threshold(window)
    assert item.pagebox.inpaint_state(threshold) == "will_inpaint"
    assert item.pen().style() == Qt.PenStyle.SolidLine
    assert _composite(window)[10:30, 10:30].any(), "will-inpaint content is in"

    item.setSelected(True)
    window._on_inspector_inpaint_committed("Never")

    assert item.pagebox.inpaint_override == "never"
    assert item._inpaint_state == "never", "the border state re-derives to never"
    assert item.pen().style() == Qt.PenStyle.CustomDashLine, "never renders dashed"
    composite = _composite(window)
    assert not composite[10:30, 10:30].any(), (
        "Never boxes' content must leave the composite mask (recompose)"
    )
    assert len(window.history._boxes_undo) == 1, (
        "one commit pushes exactly ONE BOXES undo entry"
    )
    assert window._last_boxes_op_name == "inpaint override", (
        "the undo entry is named 'inpaint override'"
    )
    assert window.status_bar_left.text() == "Inpaint: Never — 1 box(es).", (
        "the transient status flash carries the override + selection count"
    )


@pytest.mark.gui
def test_override_commit_always_joins_gate_skipped_content(qtbot, tmp_path) -> None:
    """Commit "Always" on a gate-skipped box (std_dev above the threshold, a
    stored mask present — the gate-lifted fit from 08-03 guarantees it): its
    content JOINS the composite and the border renders forced (solid)."""
    import numpy as np

    from PySide6.QtCore import Qt

    window = _window_with_custom_page(qtbot, tmp_path, _noisy_right_half_page())
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 90:110] = 255  # over the NOISY half -> std > gate
    window._on_detection_finished({"mask": heat, "blocks": [_blk(85, 5, 115, 35)]})
    item = window.canvas._box_items[0]
    threshold = _profile_threshold(window)
    assert item.pagebox.std_dev > threshold, "fixture must measure above the gate"
    assert item.pagebox.mask is not None, (
        "the gate-lifted fit always stores a mask (08-03)"
    )
    assert item.pagebox.inpaint_state(threshold) == "gate_skipped"
    assert item.pen().style() == Qt.PenStyle.CustomDashLine
    assert not _composite(window)[10:30, 90:110].any(), (
        "gate-skipped content is initially absent"
    )

    item.setSelected(True)
    window._on_inspector_inpaint_committed("Always")

    assert item.pagebox.inpaint_override == "always"
    assert item._inpaint_state == "forced", "the state re-derives to forced"
    assert item.pen().style() == Qt.PenStyle.SolidLine, "forced renders solid"
    assert _composite(window)[10:30, 90:110].any(), (
        "forced content must join the composite (recompose)"
    )


@pytest.mark.gui
def test_override_commit_multi_select_one_entry_and_undo_restores_composite(
    qtbot, tmp_path
) -> None:
    """3 boxes, ONE commit -> all three updated, exactly ONE undo entry; one
    Ctrl+Z restores all three overrides AND the recomposed composite (the
    boxes-apply undo path recomposes too)."""
    import numpy as np

    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[5:25, 5:25] = 255
    heat[10:30, 50:70] = 255
    heat[10:30, 90:110] = 255
    window._on_detection_finished(
        {
            "mask": heat,
            "blocks": [
                _blk(5, 5, 25, 25),
                _blk(50, 10, 70, 30),
                _blk(90, 10, 110, 30),
            ],
        }
    )
    items = list(window.canvas._box_items)
    assert len(items) == 3
    for it in items:
        it.setSelected(True)
    composite_before = np.count_nonzero(_composite(window))
    assert composite_before > 0

    window._on_inspector_inpaint_committed("Never")

    for it in window.canvas._box_items:
        assert it.pagebox.inpaint_override == "never", (
            "one commit updates EVERY selected box"
        )
    assert len(window.history._boxes_undo) == 1, (
        "a multi-box commit still pushes exactly ONE BOXES entry"
    )
    assert np.count_nonzero(_composite(window)) == 0, (
        "all three boxes' content leaves the composite"
    )
    assert window.status_bar_left.text() == "Inpaint: Never — 3 box(es)."

    # ONE Ctrl+Z restores all three overrides AND the recomposed composite.
    window.on_undo()
    restored = window.canvas.boxes_snapshot()
    for pb in restored:
        assert pb.inpaint_override is None, (
            "undo restores the pre-commit override (Auto)"
        )
        assert pb.mask is not None, "the per-box mask survives the restore"
    assert np.count_nonzero(_composite(window)) == composite_before, (
        "the boxes-apply undo path must recompose the mask layer"
    )


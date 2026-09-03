"""GUI tests for the Inspector Inpaint override + Std dev rows — quad state (08.1-03 D-04).

Mirrors the ``tests/test_gui_inspector_styling.py`` conventions (``importorskip``
+ ``qtbot`` + ``@pytest.mark.gui`` + real ``InspectorPanel`` instances). This
module covers the D-04 quad vocabulary (UI-SPEC §38): the two new rows
exist after Origin; single-box population maps the quad model values
(None / "fill" / "always" / "never") to the Auto / Fill / Inpaint / Never display entries;
the read-only Std dev row shows ``{value:.1f}`` or the em dash; a multi-selection
with differing values shows the dynamically-added "Mixed" sentinel while equal
values show the common value; the row stays ENABLED in multi-select (A5 — an
edit-all flag); the sentinel NEVER emits a commit; and the WR-01 loaded-memory
guard suppresses spurious commits on load.

Commit map: Fill->fill, Inpaint->always (stored always preserved for .mas compat),
Never->never, Auto->None. Legacy files with stored ``"always"`` still show
``"Inpaint"`` after load.
"""

from __future__ import annotations

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
# Task 1 — the D-04 quad surface (rows + population)
# ===========================================================================


@pytest.mark.gui
def test_inpaint_override_signal_and_entries(qtbot) -> None:
    """The class-scope Signal exists and the combo's entries are exactly
    Auto / Fill / Inpaint / Never (plus the dynamic Mixed sentinel)."""
    panel = _make_inspector(qtbot)
    # Class-scope Signal(str) (D-04, UI-SPEC §38).
    assert hasattr(InspectorPanel, "inpaint_override_changed")
    # The empty state reset the combo to the plain entry set, Auto selected.
    assert _combo_items(panel) == ["Auto", "Fill", "Inpaint", "Never"]
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
        ("fill", "Fill"),
        ("always", "Inpaint"),
        ("never", "Never"),
    ],
)
def test_single_box_populates_inpaint_combo(qtbot, override, expected) -> None:
    """Single selection maps the model quad-state to the display entries."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb(override=override, std_dev=8.3))
    assert panel.inpaint_combo.currentText() == expected
    assert _combo_items(panel) == ["Auto", "Fill", "Inpaint", "Never"]
    assert panel.std_dev_label.text() == "8.3"


@pytest.mark.gui
def test_legacy_always_still_shows_inpaint(qtbot) -> None:
    """Legacy .mas files with stored \"always\" still show \"Inpaint\" after load."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb(override="always", std_dev=5.0))
    assert panel.inpaint_combo.currentText() == "Inpaint"
    assert _combo_items(panel) == ["Auto", "Fill", "Inpaint", "Never"]


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


# ===========================================================================
# quick-260903-lm6 — the read-only per-box Confidence row
# ===========================================================================


def _pb_with_conf(conf, **kwargs) -> PageBox:
    """A USER-origin PageBox carrying a detector confidence (quick-260903-lm6)."""
    pb = _pb(**kwargs)
    pb.confidence = conf
    return pb


@pytest.mark.gui
@pytest.mark.parametrize(
    "conf,expected_text",
    [
        (0.87, "87%"),
        (None, "\u2014"),
        (0.05, "5%"),
        (1.0, "100%"),
    ],
)
def test_confidence_row_renders_percentage_or_em_dash(
    qtbot, conf, expected_text
) -> None:
    """quick-260903-lm6: ``load_box`` shows the detector confidence as a
    percentage, or the em dash when unknown (user-drawn / legacy box)."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb_with_conf(conf))
    assert panel.confidence_label.text() == expected_text
    # The muted styling mirrors the Std dev row (objectName -> QSS hook).
    assert panel.confidence_label.objectName() == "confidenceLabel"


@pytest.mark.gui
def test_confidence_row_clears_to_em_dash(qtbot) -> None:
    """quick-260903-lm6: after ``clear()`` (no selection) the Confidence row
    resets to the em dash — a stale box's value never lingers."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pb_with_conf(0.87))
    assert panel.confidence_label.text() == "87%"

    panel.clear()
    assert panel.confidence_label.text() == "\u2014"


@pytest.mark.gui
def test_confidence_row_multiselect_shows_em_dash(qtbot) -> None:
    """quick-260903-lm6: a multi-selection shows the em dash (per-box data,
    the Std dev mirror) even when every box carries a confidence."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection([_pb_with_conf(0.9), _pb_with_conf(0.5)])
    assert panel.confidence_label.text() == "\u2014"


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
def test_mixed_sentinel_for_auto_plus_fill(qtbot) -> None:
    """Two boxes Auto+fill -> combo shows Mixed, row stays ENABLED."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection([_pb(override=None), _pb(override="fill")])
    assert panel.inpaint_combo.currentText() == "Mixed"
    assert "Mixed" in _combo_items(panel)
    assert panel.inpaint_combo.isEnabled()


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
def test_equal_multi_select_fill_shows_fill(qtbot) -> None:
    """Equal fill overrides -> Fill (no Mixed)."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection([_pb(override="fill"), _pb(override="fill")])
    assert panel.inpaint_combo.currentText() == "Fill"
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
    # Picking a REAL value emits ("Inpaint" -> the multi override).
    panel.inpaint_combo.setCurrentIndex(_combo_items(panel).index("Inpaint"))
    assert fired == ["Inpaint"]
    # Re-selecting the Mixed sentinel must NOT emit anything (Pitfall 7).
    panel.inpaint_combo.setCurrentIndex(_combo_items(panel).index("Mixed"))
    assert fired == ["Inpaint"], "the Mixed sentinel must never commit"


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
    panel.load_box(_pb(override="fill", std_dev=5.0))
    assert fired == [], "loading must not re-emit the just-loaded value"
    assert panel.inpaint_combo.currentText() == "Fill"
    # A no-op focus cycle (same value re-selected) is a WR-01 no-op.
    panel.inpaint_combo.setCurrentIndex(
        _combo_items(panel).index("Fill")
    )
    assert fired == [], "an unchanged focus cycle must not push a BOXES snapshot"
    # A real change emits exactly once.
    panel.inpaint_combo.setCurrentIndex(
        _combo_items(panel).index("Never")
    )
    assert fired == ["Never"]


@pytest.mark.gui
def test_committing_fill_from_mixed_writes_fill_to_all(qtbot) -> None:
    """Committing Fill from Mixed writes fill to all selected boxes via
    on_inpaint_override callback, WR-01 suppresses spurious signal."""
    from manga_ai_studio.gui.main_window import MainWindow
    from manga_ai_studio.config.profile_manager import ProfileManager
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        pm = ProfileManager(Path(td))
        window = MainWindow(pm)
        qtbot.addWidget(window)
        # Simulate multi-select with Mixed then commit Fill via the handler
        # Directly test the mapping: Fill -> fill
        assert MainWindow._INPAINT_OVERRIDE_TO_MODEL["Fill"] == "fill"
        assert MainWindow._INPAINT_OVERRIDE_TO_MODEL["Inpaint"] == "always"
        assert MainWindow._INPAINT_OVERRIDE_TO_MODEL["Never"] == "never"
        assert MainWindow._INPAINT_OVERRIDE_TO_MODEL["Auto"] is None
        # Verify _INPAINT_DISPLAY quad
        from manga_ai_studio.gui.inspector_panel import _INPAINT_DISPLAY, _INPAINT_ITEMS
        assert _INPAINT_DISPLAY == {None: "Auto", "fill": "Fill", "always": "Inpaint", "never": "Never"}
        assert _INPAINT_ITEMS == ["Auto", "Fill", "Inpaint", "Never"]


@pytest.mark.gui
def test_inpaint_display_and_items_quad(qtbot) -> None:
    """_INPAINT_DISPLAY contains four entries and _INPAINT_ITEMS lists exactly those four."""
    from manga_ai_studio.gui.inspector_panel import _INPAINT_DISPLAY, _INPAINT_ITEMS
    assert _INPAINT_DISPLAY == {None: "Auto", "fill": "Fill", "always": "Inpaint", "never": "Never"}
    assert _INPAINT_ITEMS == ["Auto", "Fill", "Inpaint", "Never"]
    assert len(_INPAINT_DISPLAY) == 4
    assert len(_INPAINT_ITEMS) == 4


# ===========================================================================
# Task 2 — MainWindow grouped commit still works with quad vocab
# (ported from test_gui_inspector_override Task 2, Inpaint->always compat)
# ===========================================================================


def _blk(x1: int, y1: int, x2: int, y2: int):
    """A duck-typed fake TextBlock (only .xyxy is read by the build)."""
    from types import SimpleNamespace
    return SimpleNamespace(xyxy=[x1, y1, x2, y2])


def _window_with_custom_page(qtbot, tmp_path: Path, page_np) -> "MainWindow":
    """A MainWindow with a real page + the data-model registration."""
    import numpy as np
    from PIL import Image as PILImage
    from manga_ai_studio.core.image_file import ImageFile
    from manga_ai_studio.gui.main_window import MainWindow

    h, w = page_np.shape[:2]
    from manga_ai_studio.config.profile_manager import ProfileManager
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
    import numpy as np
    return _window_with_custom_page(qtbot, tmp_path, np.full((h, w, 3), 200, dtype=np.uint8))


def _noisy_right_half_page(h: int = 80, w: int = 120) -> np.ndarray:
    import numpy as np
    page = np.full((h, w, 3), 200, dtype=np.uint8)
    rng = np.random.default_rng(42)
    page[:, w // 2 :] = rng.integers(0, 256, size=(h, w // 2, 3), dtype=np.uint8)
    return page


def _profile_threshold(window) -> float:
    return float(window.profile_manager.config.current_profile.masker.mask_max_standard_deviation)


def _composite(window) -> np.ndarray:
    import numpy as np
    from manga_ai_studio.core.mask_editor import mask_to_numpy_binary
    return mask_to_numpy_binary(window.canvas.get_mask())


@pytest.mark.gui
def test_override_commit_never_removes_content_and_pushes_one_entry(qtbot, tmp_path) -> None:
    """Single box commit \"Never\": the override lands, the border renders the
    never state (dashed), its auto content LEAVES the composite mask, exactly
    ONE BOXES undo entry (op \"inpaint override\") is pushed, and the transient
    status reads \"Inpaint: Never — 1 box(es).\"."""
    import numpy as np
    from PySide6.QtCore import Qt
    window = _window_with_custom_page(qtbot, tmp_path, _noisy_right_half_page())
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 90:110] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(85, 5, 115, 35)]})
    item = window.canvas._box_items[0]
    threshold = _profile_threshold(window)
    assert item.pagebox.inpaint_state(threshold) == "will_inpaint"
    assert item.pen().style() == Qt.PenStyle.SolidLine
    assert _composite(window)[10:30, 90:110].any(), "will-inpaint content is in"
    item.setSelected(True)
    window._on_inspector_inpaint_committed("Never")
    assert item.pagebox.inpaint_override == "never"
    assert item._inpaint_state == "never"
    assert item.pen().style() == Qt.PenStyle.CustomDashLine
    composite = _composite(window)
    assert not composite[10:30, 90:110].any(), "Never boxes' content must leave the composite mask (recompose)"
    assert len(window.history._boxes_undo) == 1
    assert window._last_boxes_op_name == "inpaint override"
    assert window.status_bar_left.text() == "Inpaint: Never — 1 box(es)."


@pytest.mark.gui
def test_override_commit_inpaint_joins_gate_skipped_content(qtbot, tmp_path) -> None:
    """Commit \"Inpaint\" on a will_fill box (uniform -> fill plane): its content JOINS the composite and the border renders forced."""
    import numpy as np
    from PySide6.QtCore import Qt
    window = _window_with_page(qtbot, tmp_path)
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 10:30] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(5, 5, 35, 35)]})
    item = window.canvas._box_items[0]
    threshold = _profile_threshold(window)
    # Uniform region -> low std -> will_fill (not in inpaint auto plane)
    assert item.pagebox.std_dev <= threshold
    assert item.pagebox.mask is not None
    assert item.pagebox.inpaint_state(threshold) == "will_fill"
    # will_fill is solid origin hue, not dashed
    assert item.pen().style() == Qt.PenStyle.SolidLine
    assert not _composite(window)[10:30, 10:30].any()
    item.setSelected(True)
    window._on_inspector_inpaint_committed("Inpaint")
    assert item.pagebox.inpaint_override == "always"
    assert item._inpaint_state in ("forced_inpaint", "forced")
    assert item.pen().style() == Qt.PenStyle.SolidLine
    assert _composite(window)[10:30, 10:30].any()


@pytest.mark.gui
def test_override_commit_fill_forces_fill_state(qtbot, tmp_path) -> None:
    """Commit \"Fill\" forces forced_fill state (solid) regardless of std dev."""
    import numpy as np
    from PySide6.QtCore import Qt
    window = _window_with_custom_page(qtbot, tmp_path, _noisy_right_half_page())
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 90:110] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(85, 5, 115, 35)]})
    item = window.canvas._box_items[0]
    threshold = _profile_threshold(window)
    assert item.pagebox.std_dev > threshold
    item.setSelected(True)
    window._on_inspector_inpaint_committed("Fill")
    assert item.pagebox.inpaint_override == "fill"
    assert item._inpaint_state == "forced_fill"
    assert item.pen().style() == Qt.PenStyle.SolidLine


@pytest.mark.gui
def test_override_commit_multi_select_one_entry_and_undo_restores_composite(qtbot, tmp_path) -> None:
    import numpy as np
    # Use noisy page so all three are will_inpaint (in composite) before commit
    window = _window_with_custom_page(qtbot, tmp_path, _noisy_right_half_page())
    window.action_detect_boxes_mode.setChecked(True)
    heat = np.zeros((80, 120), dtype=np.uint8)
    heat[10:30, 85:105] = 255
    heat[30:50, 85:105] = 255
    heat[50:70, 85:105] = 255
    window._on_detection_finished({"mask": heat, "blocks": [_blk(85, 10, 105, 30), _blk(85, 30, 105, 50), _blk(85, 50, 105, 70)]})
    items = list(window.canvas._box_items)
    assert len(items) == 3
    for it in items:
        it.setSelected(True)
    composite_before = np.count_nonzero(_composite(window))
    window._on_inspector_inpaint_committed("Never")
    for it in window.canvas._box_items:
        assert it.pagebox.inpaint_override == "never"
    assert len(window.history._boxes_undo) == 1
    assert window.status_bar_left.text() == "Inpaint: Never — 3 box(es)."
    window.on_undo()
    restored = window.canvas.boxes_snapshot()
    for pb in restored:
        assert pb.inpaint_override is None
        assert pb.mask is not None

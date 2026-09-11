"""GUI tests for the Inspector Style section (plan 07-05 Task 1, D-05).

Mirrors the ``tests/test_gui_boxes.py`` conventions (``importorskip`` +
``qtbot`` + ``@pytest.mark.gui`` + real ``MainWindow`` integration). This
module covers the D-05 styling surface: the section's widgets exist and show
the box's flat ``TextStyle``, every commit signal fires exactly once per real
change and zero on a no-op focus cycle (WR-01), the Auto-fit checkbox couples
the size spin (0/disabled <-> enabled/rounded-size), and the whole section
rides the empty-state gate with the extended copy.

The D-10 Mixed / apply-to-all tests land with plan 07-05 Task 2 (same file).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QLabel,
    QSpinBox,
    QToolButton,
)

from manga_ai_studio.core.box_model import PageBox  # noqa: E402
from manga_ai_studio.core.text_style import EFFECT_GEOM_MAX, TextStyle  # noqa: E402
from manga_ai_studio.gui.inspector_panel import InspectorPanel  # noqa: E402
from panelcleaner.structures import Box  # noqa: E402


def _make_inspector(qtbot) -> InspectorPanel:
    """Build an InspectorPanel added to qtbot (so it can parent widgets)."""
    panel = InspectorPanel()
    qtbot.addWidget(panel)
    return panel


def _isolate_settings(window, tmp_path, monkeypatch) -> None:
    """Point the window's QSettings at a throwaway INI (never the real one).

    Mirrors ``tests/test_gui_project.py::_isolate_settings`` — the G-07-3
    persistence tests must never touch the user's registry.
    """
    from PySide6.QtCore import QSettings

    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(
        window,
        "_settings",
        lambda: QSettings(str(ini), QSettings.Format.IniFormat),
    )


def _press_at(canvas, sx: float, sy: float) -> "QMouseEvent":
    """A left-button Alt+press whose viewport coords map to scene (sx, sy).

    Mirrors ``tests/test_gui_boxes.py`` — drives the Alt+drag user-box
    create flow (plan 03-03 D-13) on a window's canvas.
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(vp),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.AltModifier,
    )


def _move_at(canvas, sx: float, sy: float) -> "QMouseEvent":
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(vp),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release_at(canvas, sx: float, sy: float) -> "QMouseEvent":
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    vp = canvas.mapFromScene(QPointF(sx, sy))
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(vp),
        Qt.MouseButton.LeftButton,  # the RELEASED button (mirrors test_gui_boxes)
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _pagebox_with_style(**style_kwargs) -> PageBox:
    """A USER-origin PageBox carrying a TextStyle built from ``style_kwargs``."""
    pb = PageBox(box=Box(10, 20, 210, 120), origin="user")
    pb.set_recognized_text("hello")
    pb.style = TextStyle(**style_kwargs)
    return pb


def _style_callbacks(fired: dict):
    """The style-section commit callbacks recording into ``fired``.

    ``fired`` keys: font / font_style / size / auto_fit / color / align /
    effect / fill. The four Phase 4 callbacks are no-ops (unused here).
    """
    return dict(
        on_recognized=lambda _t: None,
        on_translation=lambda _t: None,
        on_bubble=lambda _n: None,
        on_vertical=lambda _v: None,
        on_style_font=fired["font"].append,
        on_style_font_style=fired["font_style"].append,
        on_style_size=fired["size"].append,
        on_style_auto_fit=fired["auto_fit"].append,
        on_style_color=fired["color"].append,
        # style_align_changed emits (h, v) — capture the tuple.
        on_style_align=lambda h, v: fired["align"].append((h, v)),
        # style_effect_changed emits (key, dict) — capture the tuple.
        on_style_effect=lambda key, payload: fired["effect"].append((key, payload)),
        # quick-260910-vej: style_fill_changed emits the changed-fields dict.
        on_style_fill=lambda changes: fired.setdefault("fill", []).append(changes),
    )


# ===========================================================================
# Task 1 — the D-05 styling surface
# ===========================================================================


@pytest.mark.gui
def test_styling_section_present(qtbot) -> None:
    """The Style section's controls exist below the text fields and their
    values match the box's flat TextStyle (D-05/D-06 — UI-SPEC surface 33)."""
    panel = _make_inspector(qtbot)

    # The section chrome: "Style" 12px semibold muted header + 1px divider.
    assert isinstance(panel.style_header, QLabel)
    assert panel.style_header.text() == "Style"
    assert panel.style_header.objectName() == "styleHeaderLabel"
    assert panel.style_divider is not None

    # The controls (Don't-Hand-Roll: QFontComboBox / QColorDialog / QSpinBox).
    assert isinstance(panel.font_combo, QFontComboBox)
    assert isinstance(panel.style_combo, QComboBox)
    assert isinstance(panel.size_spin, QSpinBox)
    assert isinstance(panel.auto_fit_check, QCheckBox)
    assert isinstance(panel.color_swatch, QToolButton)
    assert panel.color_swatch.width() == 24 and panel.color_swatch.height() == 24
    assert isinstance(panel.align_combo, QComboBox)
    assert isinstance(panel.align_v_combo, QComboBox)
    for key in ("outline", "glow", "shadow"):
        assert isinstance(panel._effect_checks[key], QCheckBox)
        assert isinstance(panel._effect_swatches[key], QToolButton)
        assert isinstance(panel._effect_spins[key], QSpinBox)

    # Size spin: 0..1024 with the "Auto" sentinel at 0 (D-15; the cap
    # matches the TextStyle font_size_px clamp — quick-260825-wfy).
    assert panel.size_spin.minimum() == 0
    assert panel.size_spin.maximum() == 1024
    assert panel.size_spin.specialValueText() == "Auto"

    # A styled box populates the controls with its real values.
    style = TextStyle(
        font_family="Liberation Sans",
        bold=False,
        italic=False,
        font_size_px=16.0,
        auto_fit=False,
        color="#ff0000",
        align_h="left",
        align_v="top",
        outline={"enabled": True, "color": "#0b0b0e", "width_px": 3.0},
        glow={"enabled": True, "color": "#ffff00", "radius_px": 6.0, "opacity": 0.8},
        shadow={"enabled": False, "color": "#000000", "radius_px": 4.0, "dx": 2.0, "dy": 2.0, "opacity": 0.6},
    )
    panel.load_box(_pagebox_with_style(**{
        "font_family": style.font_family,
        "font_size_px": style.font_size_px,
        "auto_fit": style.auto_fit,
        "color": style.color,
        "align_h": style.align_h,
        "align_v": style.align_v,
        "outline": dict(style.outline),
        "glow": dict(style.glow),
        "shadow": dict(style.shadow),
    }))

    assert panel.font_combo.currentText() == "Liberation Sans"
    # QFontDatabase.styles("Liberation Sans") contains "Regular" on this stack.
    assert panel.style_combo.currentText() in {
        "Regular", "Italic", "Bold", "Bold Italic",
    }
    assert panel.size_spin.value() == 16
    assert panel.size_spin.isEnabled() is True  # manual size -> spin enabled
    assert panel.auto_fit_check.isChecked() is False
    assert panel.color_swatch.color == "#ff0000"
    assert panel.align_combo.currentText() == "Left"
    assert panel.align_v_combo.currentText() == "Top"
    assert panel._effect_checks["outline"].isChecked() is True
    assert panel._effect_swatches["outline"].color == "#0b0b0e"
    assert panel._effect_spins["outline"].value() == 3
    assert panel._effect_checks["glow"].isChecked() is True
    assert panel._effect_spins["glow"].value() == 6
    assert panel._effect_swatches["glow"].color == "#ffff00"
    assert panel._effect_checks["shadow"].isChecked() is False
    assert panel._effect_spins["shadow"].value() == 2


@pytest.mark.gui
def test_style_commit_signal_fires(qtbot) -> None:
    """WR-01: exactly ONE style emission per real change; ZERO on a no-op
    focus cycle — an unchanged focus cycle must not push a no-op BOXES
    snapshot (the D-10 one-commit-one-snapshot contract)."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style())  # default style (auto-fit on)

    # Font change -> exactly one style_font_changed emission.
    panel.font_combo.setCurrentText("Arial")
    assert fired["font"] == ["Arial"]

    # Style-combo change (the family's styles) -> one emission.
    panel.style_combo.setCurrentText("Bold")
    assert fired["font_style"] == ["Bold"]

    # Size: uncheck auto-fit (enables the spin), then commit a manual size.
    panel.auto_fit_check.setChecked(False)
    assert fired["auto_fit"] == [False]
    panel.size_spin.setValue(14)
    panel.size_spin.editingFinished.emit()
    assert fired["size"] == [14]
    # Post-commit reload (the MainWindow applies + reloads the panel) so the
    # WR-01 loaded-memory reflects the applied style.
    panel.load_box(_pagebox_with_style(auto_fit=False, font_size_px=14.0))

    # Color + align + effect — one emission per real change. The commit
    # emits the canonical HexArgb spelling (quick-260909-nj9 normalization).
    panel._commit_style_color("#112233")
    assert fired["color"] == ["#ff112233"]
    panel.load_box(
        _pagebox_with_style(auto_fit=False, font_size_px=14.0, color="#112233")
    )
    panel.align_combo.setCurrentIndex(0)  # Left
    assert fired["align"] == [("left", "middle")]
    # The default style now ships outline DISABLED (quick task 260822-347),
    # so checking it ON is the real-change toggle. The enable-time default
    # color is WHITE (black text + white stroke is the dominant manga case).
    panel._effect_checks["outline"].setChecked(True)
    assert fired["effect"] == [("outline", {"enabled": True, "color": "#ffffff", "value": 2})]
    # ---- WR-01 no-op focus cycles: no NEW emissions.
    panel.align_combo.setCurrentIndex(0)  # unchanged
    panel.size_spin.editingFinished.emit()  # unchanged value
    panel.auto_fit_check.setChecked(False)  # unchanged
    panel._effect_checks["outline"].setChecked(True)  # unchanged
    panel._commit_style_color("#112233")  # unchanged (alpha-normalized WR-01)
    assert fired["font"] == ["Arial"]
    assert fired["size"] == [14]
    assert fired["auto_fit"] == [False]
    assert fired["color"] == ["#ff112233"]
    assert fired["align"] == [("left", "middle")]
    assert fired["effect"] == [
        ("outline", {"enabled": True, "color": "#ffffff", "value": 2})
    ]


# ===========================================================================
# quick-260824-t64 Task 3 — live Size commits via the valueChanged debounce
# ===========================================================================
# editingFinished only fires on focus-loss/Enter — NOT per click of the
# up/down arrows or a scroll-wheel step, which is why font-size changes only
# rendered after clicking away. The fix routes valueChanged through a ~150ms
# single-shot debounce into the SAME WR-01-gated emitter.


@pytest.mark.gui
def test_size_spin_live_commit_via_debounce(qtbot) -> None:
    """A direct setValue() (the arrow-click path — no editingFinished, no
    focus tricks) commits through the style-size seam once the debounce fires."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style(auto_fit=False, font_size_px=14.0))
    assert panel.size_spin.value() == 14

    # The arrow-click equivalent: setValue without editingFinished.
    panel.size_spin.setValue(16)
    # Debounce armed, nothing committed YET.
    assert fired["size"] == []

    # Fire the debounce window manually (deterministic — no qWait).
    panel._size_debounce.timeout.emit()
    assert fired["size"] == [16]
    assert fired["size"].count(16) == 1


@pytest.mark.gui
def test_size_debounce_wr01_loaded_value_guard(qtbot) -> None:
    """Spinning back to the LOADED value before the debounce lands emits
    NOTHING (the WR-01 loaded-memory guard holds on the live path too)."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style(auto_fit=False, font_size_px=14.0))

    panel.size_spin.setValue(15)
    panel.size_spin.setValue(14)  # back to loaded -> no real change
    panel._size_debounce.timeout.emit()
    assert fired["size"] == []


@pytest.mark.gui
def test_size_debounce_mixed_sentinel_suppressed(qtbot) -> None:
    """A Mixed selection's 0 sentinel stays display-only on the live path —
    mixed + 0 emits nothing (Pitfall 7)."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    pb1 = _pagebox_with_style(font_size_px=14.0, auto_fit=False)
    pb2 = _pagebox_with_style(font_size_px=20.0, auto_fit=False)
    panel.load_multi_selection([pb1, pb2])
    assert panel._style_size_mixed is True
    assert panel.size_spin.value() == 0

    panel.size_spin.setValue(0)
    panel._size_debounce.timeout.emit()
    assert fired["size"] == []


@pytest.mark.gui
def test_font_free_text_never_commits(qtbot) -> None:
    """WR-01 (07-REVIEW-GAPS): the QFontComboBox is editable, so free-typed
    text fires ``currentTextChanged`` on EVERY keystroke with a partial /
    garbage string — pre-fix each emission became a full style commit
    (a spurious BOXES undo entry + a nonexistent family persisted into the
    model). The ``findText`` gate commits ONLY when the text exactly matches
    an installed family (T-07-18 'never free text'); the Set-as-Default
    click rides the same gate."""
    from PySide6.QtGui import QFontDatabase

    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [], "default": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.default_font_requested.connect(fired["default"].append)
    panel.load_box(_pagebox_with_style())
    loaded = panel._loaded_style_font  # "Liberation Sans" (TextStyle default)
    assert loaded

    # The typing path: the editable line edit emits currentTextChanged with
    # the PARTIAL string on every keystroke — a garbage family must never
    # become a style commit.
    panel.font_combo.setCurrentText("Ari")
    assert panel.font_combo.currentText() == "Ari"
    assert fired["font"] == [], (
        "free-typed text must never become a style commit (WR-01)"
    )

    # A full free-typed string that is not an installed family is rejected.
    panel.font_combo.setCurrentText("Totally Fake Family")
    assert fired["font"] == []

    # The Set-as-Default click rides the same gate (T-07-18): the old
    # docstring claimed 'never free text' — with the gate it is finally true.
    panel.default_font_button.click()
    assert fired["default"] == [], (
        "a free-typed family must not reach the default-font store (WR-01)"
    )

    # An EXACT real-family match commits once; the click emits it too.
    real = next(f for f in QFontDatabase.families() if f != loaded)
    panel.font_combo.setCurrentText(real)
    assert fired["font"] == [real], (
        "an exact match of an installed family must commit (T-07-18)"
    )
    panel.default_font_button.click()
    assert fired["default"] == [real]


@pytest.mark.gui
def test_auto_fit_toggles_size_spin(qtbot) -> None:
    """D-15: Auto-fit checked -> spin forced to 0/"Auto" + disabled; unchecked
    -> spin enabled with the current rendered size (rounded) as the manual
    start (UI-SPEC §33)."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))

    # An Auto-fit box loads with the spin at 0/"Auto", disabled.
    panel.load_box(_pagebox_with_style(auto_fit=True))
    assert panel.auto_fit_check.isChecked() is True
    assert panel.size_spin.value() == 0
    assert panel.size_spin.isEnabled() is False

    # Unchecking enables the spin at the current rendered size (rounded).
    panel.load_box(
        _pagebox_with_style(auto_fit=True), rendered_size_px=21.6
    )
    panel.auto_fit_check.setChecked(False)
    assert fired["auto_fit"] == [False]
    assert panel.size_spin.isEnabled() is True
    assert panel.size_spin.value() == 22  # round(21.6)

    # Simulate the MainWindow's post-commit reload (the applied style is now
    # manual at 22px) — re-checking then fires a REAL change (WR-01).
    panel.load_box(_pagebox_with_style(auto_fit=False, font_size_px=22.0))
    assert panel.auto_fit_check.isChecked() is False
    assert panel.size_spin.value() == 22
    panel.auto_fit_check.setChecked(True)
    assert fired["auto_fit"] == [False, True]
    assert panel.size_spin.value() == 0
    assert panel.size_spin.isEnabled() is False


@pytest.mark.gui
def test_empty_state_disables_styling(qtbot) -> None:
    """Empty state: the whole panel — text fields AND the styling section —
    disables with the extended copy (UI-SPEC §33 empty row)."""
    panel = _make_inspector(qtbot)
    panel.clear()

    # The extended empty-state copy (D-05: ", and style").
    assert "text, translation, and style" in panel.empty_label.text()
    assert panel.empty_label.isHidden() is False  # shown (panel unshown in tests)

    # The styling controls follow the same gate as the text fields.
    for w in (
        panel.font_combo,
        panel.style_combo,
        panel.size_spin,
        panel.auto_fit_check,
        panel.color_swatch,
        panel.align_combo,
        panel.align_v_combo,
        panel._effect_checks["outline"],
        panel._effect_swatches["glow"],
        panel._effect_spins["shadow"],
        panel.vertical_check,
    ):
        assert w.isEnabled() is False, f"{w} must be disabled in the empty state"

    # The multi-select hint is hidden with no selection.
    assert panel.multi_hint_label.isHidden() is True

    # A load re-enables the styling section (the auto-fit box keeps its spin
    # disabled — the D-15 coupling, not the empty gate).
    panel.load_box(_pagebox_with_style(auto_fit=True))
    assert panel.font_combo.isEnabled() is True
    assert panel.color_swatch.isEnabled() is True
    assert panel.size_spin.isEnabled() is False  # auto-fit coupling
    assert panel.empty_label.isHidden() is True


# ===========================================================================
# Task 2 — the D-10 common-value/Mixed layer + apply-to-all routing
# ===========================================================================


def _window_with_page(qtbot, tmp_path, size: int = 120) -> "MainWindow":
    """Build a shown MainWindow with one real PNG page loaded (mirrors
    test_gui_boxes.py's helper)."""
    from PIL import Image as PILImage

    from manga_ai_studio.config.profile_manager import ProfileManager
    from manga_ai_studio.gui.main_window import MainWindow

    page = tmp_path / "page.png"
    PILImage.new("RGB", (size, size), color=(200, 200, 200)).save(page)
    pm = ProfileManager(tmp_path)
    window = MainWindow(pm)
    qtbot.addWidget(window)
    window._load_folder(tmp_path)
    window.show()
    QApplication.processEvents()
    return window


def _seed_boxes_window(window, boxes: list) -> list:
    """Seed N user boxes in ONE set_boxes call (no history push)."""
    window._suppress_boxes_push = True
    try:
        window.canvas.set_boxes(
            [PageBox(box=b, origin="user") for b in boxes], []
        )
    finally:
        window._suppress_boxes_push = False
    return list(window.canvas._box_items)


@pytest.mark.gui
def test_mixed_state_presented(qtbot) -> None:
    """D-10: differing values across the selection show the Mixed sentinel
    (split swatch / Mixed entries / "Mixed" spin special text / tri-state
    checkboxes); a uniform selection shows real values, never Mixed."""
    from PySide6.QtCore import Qt

    panel = _make_inspector(qtbot)
    pb1 = _pagebox_with_style(
        font_family="Liberation Sans", color="#ff0000", auto_fit=True
    )
    pb2 = _pagebox_with_style(
        font_family="Arial", italic=True, color="#0000ff",
        font_size_px=20.0, auto_fit=False,
    )
    panel.load_multi_selection([pb1, pb2])

    # Font/style combos: differing -> the "Mixed" entry.
    assert panel._loaded_style_font == "Mixed"
    assert panel.font_combo.currentText() == "Mixed"
    assert panel._loaded_style_font_style == "Mixed"
    assert panel.style_combo.currentText() == "Mixed"

    # Size: differing -> the sentinel 0 with "Mixed" special text.
    assert panel._style_size_mixed is True
    assert panel.size_spin.text() == "Mixed"

    # Color: differing -> the split swatch (color None).
    assert panel._loaded_style_color is None
    assert panel.color_swatch.color is None

    # Auto-fit: differing -> tri-state indeterminate.
    assert panel.auto_fit_check.checkState() == Qt.CheckState.PartiallyChecked

    # A uniform selection shows real values, never Mixed (UI-SPEC populated row).
    pb3 = _pagebox_with_style(color="#ff0000", font_size_px=14.0, auto_fit=False)
    pb4 = _pagebox_with_style(color="#ff0000", font_size_px=14.0, auto_fit=False)
    panel.load_multi_selection([pb3, pb4])
    assert panel._loaded_style_font != "Mixed"
    assert panel._loaded_style_color == "#ff0000"
    assert panel.color_swatch.color == "#ff0000"
    assert panel._style_size_mixed is False
    assert panel.size_spin.value() == 14
    assert panel.auto_fit_check.checkState() == Qt.CheckState.Unchecked


@pytest.mark.gui
def test_mixed_align_keeps_real_items_and_maps_sentinel(qtbot) -> None:
    """G-07-7: a Mixed align state stays OVERRIDABLE — the align combos keep
    the real options under a leading 'Mixed' entry (Mixed current), and
    picking a value commits the changed axis as its model value while the
    untouched axis arrives as None (the ``_effect_payload`` mirror). The
    uniform case shows the real value with NO Mixed entry; an unchanged
    Mixed focus cycle still emits nothing (WR-01 per-axis no-op)."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))

    # BOTH axes differ across the selection -> both combos go Mixed WITH the
    # real items kept (the old items-replaced-with-['Mixed'] behavior is gone).
    pb_a = _pagebox_with_style(align_h="left", align_v="top")
    pb_b = _pagebox_with_style(align_h="right", align_v="bottom")
    panel.load_multi_selection([pb_a, pb_b])

    assert [
        panel.align_combo.itemText(i) for i in range(panel.align_combo.count())
    ] == ["Mixed", "Left", "Center", "Right"]
    assert panel.align_combo.currentText() == "Mixed"
    assert [
        panel.align_v_combo.itemText(i) for i in range(panel.align_v_combo.count())
    ] == ["Mixed", "Top", "Middle", "Bottom"]
    assert panel.align_v_combo.currentText() == "Mixed"

    # The uniform case keeps the plain real-item list — no Mixed entry.
    panel.load_multi_selection([
        _pagebox_with_style(align_h="center", align_v="middle"),
        _pagebox_with_style(align_h="center", align_v="middle"),
    ])
    assert [
        panel.align_combo.itemText(i) for i in range(panel.align_combo.count())
    ] == ["Left", "Center", "Right"]
    assert panel.align_combo.currentText() == "Center"
    assert [
        panel.align_v_combo.itemText(i) for i in range(panel.align_v_combo.count())
    ] == ["Top", "Middle", "Bottom"]
    assert panel.align_v_combo.currentText() == "Middle"

    # Back to the differing selection: picking Bottom in align_v while
    # align_h stays Mixed commits the changed axis as 'bottom' and the
    # untouched axis as None — the consumer's preserve-per-box sentinel.
    panel.load_multi_selection([pb_a, pb_b])
    panel.align_v_combo.setCurrentText("Bottom")
    assert fired["align"] == [(None, "bottom")], (
        "a real change on one combo must not be discarded by the other "
        "combo's Mixed sentinel (G-07-7)"
    )

    # WR-01 per-axis no-op: returning the combo to its loaded Mixed sentinel
    # is an unchanged focus cycle — nothing fires.
    panel.align_v_combo.setCurrentText("Mixed")
    assert fired["align"] == [(None, "bottom")]


@pytest.mark.gui
def test_align_sentinel_repick_after_commit_no_op(qtbot) -> None:
    """WR-02 (07-REVIEW-GAPS): re-picking the 'Mixed' sentinel after a
    per-axis align commit must NOT fire a ``(None, None)`` commit.

    After H→'Left' on a both-Mixed selection, the consumer applies H to
    every box and the MainWindow reloads the panel: loaded becomes
    ('Left', 'Mixed'). If the H combo presents the 'Mixed' sentinel again
    (the review's WR-02 shape) and the user re-picks it, the widget layer
    reports ('Mixed', 'Mixed') != loaded — but BOTH axes translate to None,
    nothing to apply. Emitting it would push a before==after BOXES undo
    entry + a refresh; the both-None guard drops it. A real per-axis change
    still commits.
    """
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))

    pb_a = _pagebox_with_style(align_h="left", align_v="top")
    pb_b = _pagebox_with_style(align_h="right", align_v="bottom")
    panel.load_multi_selection([pb_a, pb_b])

    # Per-axis commit: H -> "Left" (V untouched -> None).
    panel.align_combo.setCurrentText("Left")
    assert fired["align"] == [("left", None)]

    # The consumer applies H to every box; the MainWindow reloads the panel:
    # H is now uniform ("Left"), V stays Mixed.
    pb_a.style.align_h = "left"
    pb_b.style.align_h = "left"
    panel.load_multi_selection([pb_a, pb_b])
    assert (panel._loaded_style_align_h, panel._loaded_style_align_v) == (
        "Left",
        "Mixed",
    )

    # WR-02 shape: the H combo offers the 'Mixed' sentinel again (the review
    # notes item 0 persists after the reload) and the user re-picks it — the
    # commit translates to (None, None) and must NOT fire.
    panel._select_combo(
        panel.align_combo, ["Mixed", "Left", "Center", "Right"], "Mixed"
    )
    panel._emit_style_align_if_changed(
        lambda h, v: fired["align"].append((h, v))
    )
    assert fired["align"] == [("left", None)], (
        "re-picking the sentinel must not push a (None, None) commit (WR-02)"
    )

    # A REAL per-axis change still commits — the guard only drops the
    # nothing-to-apply case.
    panel.align_combo.setCurrentText("Center")
    assert fired["align"] == [("left", None), ("center", None)]


@pytest.mark.gui
def test_load_multi_selection_bare_payload_defensive(qtbot) -> None:
    """WR-03/G-07-1: ``load_multi_selection`` must survive a bare-marker
    payload (a non-``TextBlock`` object — the suite builds
    ``PageBox(payload="p")``): the vertical read is STYLE-based with a
    style-None fallback, so no AttributeError in the selection handler."""
    from PySide6.QtCore import Qt

    panel = _make_inspector(qtbot)
    bare = PageBox(box=Box(10, 20, 60, 60), origin="user", payload="p")
    normal = _pagebox_with_style()

    # bare (False) vs normal (False) -> uniform; the panel populates without
    # crashing on the bare marker.
    panel.load_multi_selection([bare, normal])
    assert panel.vertical_check.isChecked() is False

    # bare (False) vs a vertical-True box -> tri-state Mixed, still no crash.
    vertical_box = _pagebox_with_style(vertical=True)
    panel.load_multi_selection([bare, vertical_box])
    assert panel.vertical_check.checkState() == Qt.CheckState.PartiallyChecked


@pytest.mark.gui
def test_style_commit_applies_to_all(qtbot, tmp_path) -> None:
    """D-10 end-to-end: ONE override on a Mixed selection applies to BOTH
    boxes; exactly ONE BOXES emission; ONE Ctrl+Z restores both PRE-edit
    styles (detached — Pitfall 1)."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 60, 60), Box(80, 20, 60, 60)]
    )
    items[0].pagebox.style = TextStyle(color="#ff0000")
    items[1].pagebox.style = TextStyle(color="#0000ff")
    items[0].setSelected(True)
    items[1].setSelected(True)
    QApplication.processEvents()

    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))
    # The panel shows the Mixed state for the differing colors.
    assert window.inspector_panel._loaded_style_color is None

    # ONE color override -> BOTH boxes update; exactly ONE BOXES emission.
    # The commit emits the canonical HexArgb spelling (quick-260909-nj9).
    window.inspector_panel._commit_style_color("#00ff00")
    QApplication.processEvents()
    assert items[0].pagebox.style.color == "#ff00ff00"
    assert items[1].pagebox.style.color == "#ff00ff00"
    assert len(emitted) == 1, "a style commit must emit boxes_modified exactly once"
    before = emitted[0]
    assert before[0].style.color == "#ff0000"
    assert before[1].style.color == "#0000ff"

    # ONE Ctrl+Z restores BOTH previous styles (Pitfall 1 — the restored
    # styles are detached from the live ones).
    window.on_undo()
    QApplication.processEvents()
    restored = [it.pagebox for it in window.canvas._box_items]
    assert restored[0].style.color == "#ff0000"
    assert restored[1].style.color == "#0000ff"


@pytest.mark.gui
def test_mixed_sentinel_never_persists(qtbot, tmp_path) -> None:
    """Pitfall 7: after commits on a Mixed selection, no TextStyle anywhere
    carries the "Mixed" sentinel — commits always emit real values."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 60, 60), Box(80, 20, 60, 60)]
    )
    items[0].pagebox.style = TextStyle(
        color="#ff0000", font_size_px=14.0, auto_fit=False
    )
    items[1].pagebox.style = TextStyle(
        color="#0000ff", font_size_px=20.0, auto_fit=False
    )
    items[0].setSelected(True)
    items[1].setSelected(True)
    QApplication.processEvents()

    # Overrides on the Mixed selection: color via the swatch hook, size via
    # the spin, then a font-style commit.
    window.inspector_panel._commit_style_color("#123456")
    window.inspector_panel.size_spin.setValue(18)
    window.inspector_panel.size_spin.editingFinished.emit()
    QApplication.processEvents()

    for pb in window.canvas.boxes_snapshot():
        d = pb.style.to_dict()
        assert "Mixed" not in str(d), f"sentinel leaked into a TextStyle: {d}"
        assert pb.style.color == "#ff123456"
        assert pb.style.font_size_px == 18.0
        assert pb.style.auto_fit is False


@pytest.mark.gui
def test_mixed_align_override_commits_per_axis(qtbot, tmp_path) -> None:
    """G-07-7 end-to-end: an override on a Mixed align state commits ONLY the
    changed axis — every box keeps its OWN untouched axis; exactly ONE BOXES
    emission; ONE Ctrl+Z restores both boxes' pre-commit aligns (the snapshot
    carries the detached styles); the 'Mixed' sentinel never lands in any
    TextStyle."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 60, 60), Box(80, 20, 60, 60)]
    )
    # Both axes differ across the selection: box A (left, top), box B
    # (right, bottom) -> both align combos go Mixed.
    items[0].pagebox.style = TextStyle(align_h="left", align_v="top")
    items[1].pagebox.style = TextStyle(align_h="right", align_v="bottom")
    items[0].setSelected(True)
    items[1].setSelected(True)
    QApplication.processEvents()

    panel = window.inspector_panel
    assert panel._loaded_style_align_h == "Mixed"
    assert panel._loaded_style_align_v == "Mixed"
    # The real options stay selectable under the leading Mixed entry.
    assert panel.align_v_combo.itemText(1) == "Top"

    emitted: list = []
    window.canvas.boxes_modified.connect(lambda snap: emitted.append(snap))

    # Override ONLY align_v -> Bottom; align_h stays Mixed (untouched).
    panel.align_v_combo.setCurrentText("Bottom")
    QApplication.processEvents()

    # The changed axis applies to BOTH boxes; each box keeps its OWN align_h.
    assert items[0].pagebox.style.align_v == "bottom"
    assert items[1].pagebox.style.align_v == "bottom"
    assert items[0].pagebox.style.align_h == "left", (
        "box A had align_h left — a vertical-only override must not clobber it"
    )
    assert items[1].pagebox.style.align_h == "right", (
        "box B had align_h right — a vertical-only override must not clobber it"
    )
    assert len(emitted) == 1, (
        "an align override must emit boxes_modified exactly once"
    )

    # Pitfall 7: no 'Mixed' sentinel persisted into any TextStyle.
    for pb in window.canvas.boxes_snapshot():
        d = pb.style.to_dict()
        assert "Mixed" not in str(d), f"sentinel leaked into a TextStyle: {d}"

    # ONE Ctrl+Z restores BOTH boxes' pre-commit aligns.
    window.on_undo()
    QApplication.processEvents()
    restored = [it.pagebox for it in window.canvas._box_items]
    assert restored[0].style.align_h == "left"
    assert restored[0].style.align_v == "top"
    assert restored[1].style.align_h == "right"
    assert restored[1].style.align_v == "bottom"


@pytest.mark.gui
def test_mixed_effect_value_commit_preserves_per_box_enabled(qtbot, tmp_path) -> None:
    """WR-02: a VALUE-only commit on a MIXED effect row must NOT silently
    switch the effect on for every box — each box keeps its OWN enabled state
    (the tri-state checkbox cannot express 'leave enabled alone', so the
    commit carries the untouched sentinel and the consumer preserves it)."""
    from manga_ai_studio.core.text_style import TextStyle

    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 20, 60, 60), Box(80, 20, 60, 60)]
    )
    # Box A: glow ON. Box B: glow OFF — differing enabled -> Mixed row.
    items[0].pagebox.style = TextStyle(glow={"enabled": True, "radius_px": 3.0})
    items[1].pagebox.style = TextStyle(glow={"enabled": False, "radius_px": 3.0})
    items[0].setSelected(True)
    items[1].setSelected(True)
    QApplication.processEvents()

    panel = window.inspector_panel
    # The glow row is Mixed (differing enabled across the selection).
    assert panel._loaded_effects["glow"]["enabled"] is None

    # A VALUE-only commit (radius 3 -> 7) through the real window handler.
    panel._effect_spins["glow"].setValue(7)
    panel._commit_effect_value("glow", panel._cb_style_effect)
    QApplication.processEvents()

    # Each box keeps its OWN enabled state; the radius applies to both.
    assert items[0].pagebox.style.glow["enabled"] is True, (
        "box A had glow ON — a value-only commit must not turn it off (WR-02)"
    )
    assert items[1].pagebox.style.glow["enabled"] is False, (
        "box B had glow OFF — a value-only commit must not turn it ON (WR-02)"
    )
    assert items[0].pagebox.style.glow["radius_px"] == 7.0
    assert items[1].pagebox.style.glow["radius_px"] == 7.0
    # Pitfall 7: no sentinel persisted into any style.
    for it in items:
        assert "None" not in str(it.pagebox.style.glow)


@pytest.mark.gui
def test_multi_text_fields_disabled(qtbot) -> None:
    """D-10: at N>1 the per-box text fields disable while the styling section
    stays enabled; at N==1 the text fields re-enable."""
    panel = _make_inspector(qtbot)
    pb1 = _pagebox_with_style()
    pb2 = _pagebox_with_style()
    panel.load_multi_selection([pb1, pb2])

    # Per-box content fields disable (Bubble #, Origin, Recognized, Translation,
    # Language).
    for w in (
        panel.bubble_spin,
        panel.origin_label,
        panel.recognized_edit,
        panel.translation_edit,
        panel.language_label,
    ):
        assert w.isEnabled() is False, f"{w} must disable at N>1 (D-10)"

    # The styling section + vertical checkbox stay ENABLED (edits ALL).
    for w in (
        panel.font_combo,
        panel.style_combo,
        panel.auto_fit_check,
        panel.color_swatch,
        panel.align_combo,
        panel.align_v_combo,
        panel.vertical_check,
    ):
        assert w.isEnabled() is True, f"{w} must stay enabled at N>1 (D-10)"

    # Single select re-enables the per-box fields.
    panel.load_box(pb1)
    for w in (
        panel.bubble_spin,
        panel.recognized_edit,
        panel.translation_edit,
        panel.language_label,
    ):
        assert w.isEnabled() is True, f"{w} must re-enable at N==1"


@pytest.mark.gui
def test_hint_label_count(qtbot) -> None:
    """D-10: the muted hint shows the EXACT selection count; single select
    hides it."""
    panel = _make_inspector(qtbot)
    panel.load_multi_selection([_pagebox_with_style() for _ in range(3)])
    assert panel.multi_hint_label.isHidden() is False
    assert panel.multi_hint_label.text() == "Style edits apply to all 3 selected boxes."

    panel.load_multi_selection([_pagebox_with_style(), _pagebox_with_style()])
    assert panel.multi_hint_label.text() == "Style edits apply to all 2 selected boxes."

    # Single select hides the hint (the Phase 4 follower behavior).
    panel.load_box(_pagebox_with_style())
    assert panel.multi_hint_label.isHidden() is True


# ===========================================================================
# G-07-3 — the Set-as-Default Font affordance (plan 07-11)
# ===========================================================================


@pytest.mark.gui
def test_set_as_default_button_emits_family(qtbot) -> None:
    """G-07-3: the Font row's Set-as-Default button emits
    ``default_font_requested`` with the CURRENT font-combo family; a click
    while the combo shows the 'Mixed' sentinel emits nothing (Pitfall 7 —
    the sentinel never leaves the widget layer)."""
    panel = _make_inspector(qtbot)
    captured: list = []
    panel.default_font_requested.connect(captured.append)
    panel.load_box(_pagebox_with_style())

    # The affordance sits on the Font row, QSS-consistent (QToolButton token).
    assert isinstance(panel.default_font_button, QToolButton)
    assert panel.default_font_button.toolTip() == "Use this font for new boxes"

    panel.font_combo.setCurrentText("Yu Gothic UI")
    panel.default_font_button.click()
    assert captured == ["Yu Gothic UI"], (
        "the click must emit the CURRENT combo family"
    )

    # Mixed sentinel guard: no emission.
    panel.load_multi_selection(
        [_pagebox_with_style(font_family="Arial"), _pagebox_with_style(font_family="Bahnschrift")]
    )
    panel.default_font_button.click()
    assert captured == ["Yu Gothic UI"], "a Mixed click must emit nothing"


@pytest.mark.gui
def test_set_as_default_writes_key_and_flashes_status(
    qtbot, tmp_path, monkeypatch
) -> None:
    """G-07-3 end-to-end: the MainWindow handler for
    ``default_font_requested`` persists the family under 'defaultFontFamily'
    in the shared _settings() store (isolated INI) and flashes the transient
    status — the reader/writer chain round-trips."""
    window = _window_with_page(qtbot, tmp_path)
    _isolate_settings(window, tmp_path, monkeypatch)

    panel = window.inspector_panel
    panel.load_box(_pagebox_with_style())
    QApplication.processEvents()

    panel.font_combo.setCurrentText("Yu Gothic UI")
    panel.default_font_button.click()
    QApplication.processEvents()

    assert window._settings().value("defaultFontFamily") == "Yu Gothic UI"
    assert window.status_bar_left.text() == "Default font: Yu Gothic UI"
    # The reader (the same store the new-box sites consult) round-trips it.
    assert window._default_font_family() == "Yu Gothic UI"


@pytest.mark.gui
def test_new_user_box_uses_saved_default_family(
    qtbot, tmp_path, monkeypatch
) -> None:
    """G-07-3: a new Alt+drag user box is born with the saved default family
    (canvas._commit_create applies the new_box_style_provider)."""
    window = _window_with_page(qtbot, tmp_path)
    _isolate_settings(window, tmp_path, monkeypatch)
    window._settings().setValue("defaultFontFamily", "Yu Gothic UI")
    # The T-4-14 gate: suppress the auto-OCR dispatch the create-release
    # emits (it would spin up the real OCR worker in this test).
    window._op_running = True
    try:
        canvas = window.canvas
        canvas.mousePressEvent(_press_at(canvas, 30, 30))
        canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
        canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))
        QApplication.processEvents()
    finally:
        window._op_running = False

    assert canvas.box_count() == 1
    item = canvas._box_items[0]
    assert item.pagebox.origin == "user"
    assert item.pagebox.style is not None
    assert item.pagebox.style.font_family == "Yu Gothic UI"
    # Every other field stays at the defaults (the factory overrides ONLY
    # the family — a new box looks like today's default box otherwise).
    assert item.pagebox.style.to_dict() == TextStyle(
        font_family="Yu Gothic UI"
    ).to_dict()


@pytest.mark.gui
def test_new_user_box_keeps_style_none_without_key(
    qtbot, tmp_path, monkeypatch
) -> None:
    """G-07-3 no-key contract: with no saved family a new user box keeps
    ``style is None`` — the renderer's TextStyle() defaults (Liberation
    Sans) apply, exactly today's behavior."""
    window = _window_with_page(qtbot, tmp_path)
    _isolate_settings(window, tmp_path, monkeypatch)  # fresh INI -> no key
    window._op_running = True
    try:
        canvas = window.canvas
        canvas.mousePressEvent(_press_at(canvas, 30, 30))
        canvas.mouseMoveEvent(_move_at(canvas, 90, 90))
        canvas.mouseReleaseEvent(_release_at(canvas, 90, 90))
        QApplication.processEvents()
    finally:
        window._op_running = False

    assert canvas.box_count() == 1
    assert canvas._box_items[0].pagebox.style is None


# ===========================================================================
# G-07-2 — the font dropdown contains filter (plan 07-12)
# ===========================================================================


@pytest.mark.gui
def test_font_filter_contains_match(qtbot) -> None:
    """G-07-2: the font dropdown filter matches SUBSTRINGS — typing a
    mid-name word finds its family ('Wild Words' finds 'CC Wild Words'
    shape, driven on the REAL installed font DB: the longest installed
    family is found by its TRAILING word, which the built-in start-of-name
    search can never match). The filter is case-insensitive; clearing
    restores the full family list; the 'Mixed' load path keeps working with
    the proxy installed."""
    from PySide6.QtGui import QFontDatabase

    panel = _make_inspector(qtbot)

    families = QFontDatabase.families()
    assert families, "the real font database must be populated"
    longest = max(families, key=len)
    words = longest.split()
    assert len(words) > 1, "need a multi-word family for a mid-name query"
    query = words[-1]  # NOT a prefix of the family — start-of-name blind spot

    full = panel._font_proxy.rowCount()
    assert full == len(families), "the proxy must wrap the full family list"

    # A mid-name substring filters the list down AND keeps the target family.
    panel.font_filter_edit.setText(query)
    filtered = panel._font_proxy.rowCount()
    assert filtered < full, "the contains filter must shrink the list"
    visible = [
        panel._font_proxy.data(panel._font_proxy.index(r, 0))
        for r in range(filtered)
    ]
    assert longest in visible, (
        "typing a mid-name substring must find its family (contains match)"
    )

    # Case-insensitive: a case-shifted query still finds the family.
    panel.font_filter_edit.setText(query.swapcase())
    assert panel._font_proxy.rowCount() == filtered
    visible = [
        panel._font_proxy.data(panel._font_proxy.index(r, 0))
        for r in range(panel._font_proxy.rowCount())
    ]
    assert longest in visible, "the filter must be case-insensitive"

    # Clearing the filter restores the FULL family list.
    panel.font_filter_edit.setText("")
    assert panel._font_proxy.rowCount() == full

    # The 'Mixed' load path keeps working with the proxy installed
    # (07-09's mixed combos: differing fonts -> the Mixed sentinel).
    panel.load_multi_selection([
        _pagebox_with_style(font_family="Arial"),
        _pagebox_with_style(font_family="Bahnschrift"),
    ])
    assert panel.font_combo.currentText() == "Mixed"
    assert panel._loaded_style_font == "Mixed"
    # The load clears the filter — it never leaks into a new selection.
    assert panel.font_filter_edit.text() == ""


@pytest.mark.gui
def test_font_filter_contains_match_scenario(qtbot) -> None:
    """G-07-2 user-report shape: 'Wild Words' finds 'CC Wild Words'. Any
    multi-word installed family is surfaced by its TRAILING word (the exact
    start-of-name blind spot the user hit); the popup view shows the
    filtered rows; and the filter is a first-class styling control —
    disabled in the empty state, enabled with a selection, and its
    filtering never disturbs the loaded family selection."""
    from PySide6.QtGui import QFontDatabase

    panel = _make_inspector(qtbot)
    panel.clear()

    # First-class control: disabled in the empty state (mirrors the other
    # styling controls), with the copy-writing placeholder.
    assert panel.font_filter_edit.isEnabled() is False
    assert panel.font_filter_edit.placeholderText() == "Filter fonts\u2026"

    # ...and enabled with a selection.
    panel.load_box(_pagebox_with_style())
    assert panel.font_filter_edit.isEnabled() is True
    assert panel.font_combo.currentText() == "Liberation Sans"

    # The 'Wild Words' -> 'CC Wild Words' shape: the trailing word of a
    # multi-word family is a contains-match query, never a prefix.
    families = QFontDatabase.families()
    multi = [f for f in families if len(f.split()) > 1]
    assert multi, "need a multi-word installed family for the scenario"
    family = max(multi, key=len)
    tail = family.split()[-1]
    assert not family.startswith(tail), "the query must be a MID-name word"

    full = panel._font_proxy.rowCount()
    panel.font_filter_edit.setText(tail)
    # The popup view is the proxy — it shows the filtered rows live (no
    # explicit refresh needed on popup open).
    view = panel.font_combo.view()
    assert view.model() is panel._font_proxy
    visible = [
        view.model().data(view.model().index(r, 0))
        for r in range(view.model().rowCount())
    ]
    assert len(visible) < full, "the filtered popup must shrink the list"
    assert family in visible, "typing a mid-name word must surface its family"

    # Filtering never disturbs the loaded family selection (the filter
    # excludes Liberation Sans on this machine — either way the display
    # stays on the loaded family, and no spurious commit can fire).
    assert panel.font_combo.currentText() == "Liberation Sans"

    # Clearing restores the full list and the loaded selection.
    panel.font_filter_edit.setText("")
    assert panel._font_proxy.rowCount() == full
    assert panel.font_combo.currentText() == "Liberation Sans"

    # A load clears a stale filter (it never leaks into a new selection).
    panel.font_filter_edit.setText(tail)
    panel.load_box(_pagebox_with_style())
    assert panel.font_filter_edit.text() == ""
    assert panel._font_proxy.rowCount() == full


# ===========================================================================
# quick-260826-vhh — effect spin ranges read the TextStyle model constant
# ===========================================================================


@pytest.mark.gui
def test_effect_spin_ranges_read_model_constant(qtbot) -> None:
    """All three effect rows span 0..int(EFFECT_GEOM_MAX) — the same symbol
    the TextStyle V5 coercion clamps with, so UI == model by construction.
    The DEFAULT VALUES are untouched (outline 2 / glow 4 / shadow 2)."""
    panel = _make_inspector(qtbot)
    for key in ("outline", "glow", "shadow"):
        spin = panel._effect_spins[key]
        assert spin.minimum() == 0
        assert spin.maximum() == int(EFFECT_GEOM_MAX), (
            f"{key} spin max must equal int(EFFECT_GEOM_MAX)"
        )
    assert panel._effect_spins["outline"].value() == 2
    assert panel._effect_spins["glow"].value() == 4
    assert panel._effect_spins["shadow"].value() == 2


@pytest.mark.gui
def test_glow_radius_256_commit_reaches_the_model_unreclamped(qtbot) -> None:
    """A 256 glow radius is enterable in the panel (the old cap stopped at
    20) and its commit payload carries value=256 — which the TextStyle V5
    coercion accepts UN-re-clamped (256 is the inclusive boundary)."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    # A real uniform glow row at radius 250 so the 256 commit is a CHANGE
    # under the WR-01 loaded-memory guard.
    panel.load_box(
        _pagebox_with_style(
            auto_fit=False,
            font_size_px=14.0,
            glow={"enabled": True, "color": "#ffff00", "radius_px": 250.0, "opacity": 0.8},
        )
    )
    spin = panel._effect_spins["glow"]
    spin.setValue(256)
    spin.editingFinished.emit()
    assert fired["effect"] == [
        ("glow", {"enabled": True, "color": "#ffff00", "value": 256})
    ]

    # The committed value feeds the model boundary unchanged: build the
    # resulting style like the MainWindow consumer would and re-coerce it.
    result = TextStyle.from_dict(
        {
            "auto_fit": False,
            "font_size_px": 14.0,
            "glow": {"enabled": True, "color": "#ffff00", "radius_px": 256, "opacity": 0.8},
        }
    )
    assert result.glow["radius_px"] == 256.0


# ===========================================================================
# quick-260909-nj9 — alpha-capable Color picker, honest swatch, alpha-aware
# WR-01 guard (effect rows deliberately stay opaque)
# ===========================================================================


@pytest.mark.gui
def test_pick_style_color_opens_alpha_dialog_and_emits_hexargb(
    qtbot, monkeypatch
) -> None:
    """The picker seam: _pick_style_color opens QColorDialog with BOTH the
    ShowAlphaChannel and DontUseNativeDialog options (the Windows native
    dialog has no alpha control, so ShowAlphaChannel alone would silently
    show nothing) and emits the picked color as Qt's HexArgb spelling."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    panel = _make_inspector(qtbot)
    fired: list = []
    captured: dict = {}

    def fake_get_color(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return QColor("#80ff0000")

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(fake_get_color))
    panel._pick_style_color(fired.append)

    options = captured["args"][3]
    assert options & QColorDialog.ColorDialogOption.ShowAlphaChannel, (
        "the glyph-fill picker must offer the alpha control"
    )
    assert options & QColorDialog.ColorDialogOption.DontUseNativeDialog, (
        "the native dialog must be disabled — it has no alpha control"
    )
    assert fired == ["#80ff0000"], "the picker must emit the HexArgb spelling"


@pytest.mark.gui
def test_pick_style_color_cancel_still_commits_nothing(qtbot, monkeypatch) -> None:
    """The existing invalid-color guard is unchanged: a cancelled dialog
    (invalid QColor) commits nothing."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    panel = _make_inspector(qtbot)
    fired: list = []
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor())
    )
    panel._pick_style_color(fired.append)
    assert fired == []


@pytest.mark.gui
def test_style_color_wr01_guard_is_alpha_normalized(qtbot) -> None:
    """The WR-01 no-op guard compares ALPHA-NORMALIZED spellings: re-picking
    the loaded legacy color in opaque HexArgb form fires NOTHING (never a
    spurious undo entry); a real alpha change commits the normalized
    spelling; after reload, re-committing the same color is a no-op."""
    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    # Legacy project spelling loaded verbatim.
    panel.load_box(_pagebox_with_style(color="#ff0000"))
    assert panel._loaded_style_color == "#ff0000"

    # Same color, opaque HexArgb spelling -> NO callback (normalized equal).
    panel._commit_style_color("#ffff0000")
    assert fired["color"] == []

    # A real alpha change -> commits the normalized HexArgb spelling.
    panel._commit_style_color("#80ff0000")
    assert fired["color"] == ["#80ff0000"]

    # Post-commit reload, then re-picking the SAME color: no-op (WR-01).
    panel.load_box(_pagebox_with_style(color="#80ff0000"))
    panel._commit_style_color("#80ff0000")
    assert fired["color"] == ["#80ff0000"]


@pytest.mark.gui
def test_swatch_paints_transparent_fill_over_checkerboard(qtbot) -> None:
    """Swatch honesty: a sub-opaque ARGB color renders as the fill BLENDED
    over a neutral checkerboard — the center pixel's red is strictly below
    the opaque value and above the bare checker greys (range-based, no
    exact pixel math), with the red hue reading through."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from manga_ai_studio.gui.inspector_panel import _ColorSwatchButton

    swatch = _ColorSwatchButton()
    qtbot.addWidget(swatch)
    swatch.color = "#80ff0000"
    img = QImage(24, 24, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    swatch.render(img)

    c = img.pixelColor(12, 12)
    assert c.alpha() == 255, "the checkerboard underlay makes the pixel opaque"
    assert 180 <= c.red() < 255, (
        f"the 50%-alpha red must blend over the checkerboard "
        f"(red strictly below 255, above the bare greys) — got {c.red()}"
    )
    assert c.red() > c.green() and c.red() > c.blue(), (
        "the red hue must read through the transparency"
    )


@pytest.mark.gui
def test_swatch_opaque_renders_exactly_as_legacy(qtbot) -> None:
    """The opaque spelling renders byte-identically to today: full red at
    the center pixel, no checkerboard interference."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from manga_ai_studio.gui.inspector_panel import _ColorSwatchButton

    swatch = _ColorSwatchButton()
    qtbot.addWidget(swatch)
    swatch.color = "#ff0000"
    img = QImage(24, 24, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    swatch.render(img)
    c = img.pixelColor(12, 12)
    assert (c.red(), c.green(), c.blue(), c.alpha()) == (255, 0, 0, 255)


@pytest.mark.gui
def test_swatch_mixed_split_unchanged(qtbot) -> None:
    """The None Mixed split swatch is untouched by the alpha work."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from manga_ai_studio.gui.inspector_panel import _ColorSwatchButton

    swatch = _ColorSwatchButton()
    qtbot.addWidget(swatch)
    swatch.color = None
    img = QImage(24, 24, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    swatch.render(img)
    left = img.pixelColor(6, 12)
    right = img.pixelColor(18, 12)
    assert (left.red(), left.green(), left.blue()) == (232, 232, 234)
    assert (right.red(), right.green(), right.blue()) == (154, 154, 162)


@pytest.mark.gui
def test_pick_effect_color_stays_opaque_hexrgb(qtbot, monkeypatch) -> None:
    """Scope decision pin: the EFFECT picker deliberately keeps its HexRgb
    dialog with NO alpha options — each effect dict already owns an opacity
    field, so effect colors stay opaque (the emitted spelling is the
    7-char HexRgb form, never normalized to HexArgb)."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    panel = _make_inspector(qtbot)
    fired: dict = {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style())  # defaults: outline #ffffff @ 2
    captured: dict = {}

    def fake_get_color(*args, **kwargs):
        captured["args"] = args
        return QColor("#123456")

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(fake_get_color))
    panel._pick_effect_color(
        "outline", lambda key, payload: fired["effect"].append((key, payload))
    )

    assert len(captured["args"]) == 3, (
        "the effect picker must pass NO dialog options (no ShowAlphaChannel)"
    )
    payload = fired["effect"][0][1]
    assert payload["color"] == "#123456", (
        "the effect color must stay the 7-char HexRgb spelling (opaque)"
    )


# ===========================================================================
# quick-260910-vej — the Fill row (Solid | Gradient | Pattern)
# ===========================================================================


def _tile_png_b64(w: int = 8, h: int = 8) -> str:
    """A real two-color PNG tile (top half red / bottom half green) as b64."""
    import base64
    from io import BytesIO

    from PIL import Image as PILImage

    img = PILImage.new("RGBA", (w, h), (255, 0, 0, 255))
    for y in range(h // 2, h):
        for x in range(w):
            img.putpixel((x, y), (0, 255, 0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _write_tile_file(tmp_path, name="tile.png"):
    """Write the two-color tile as a real file; returns its path."""
    import base64

    path = tmp_path / name
    path.write_bytes(base64.b64decode(_tile_png_b64()))
    return path


def _fired_fill(fired: dict) -> list:
    return fired.get("fill", [])


def _fresh_fired() -> dict:
    return {
        "font": [], "font_style": [], "size": [], "auto_fit": [],
        "color": [], "align": [], "effect": [],
    }


@pytest.mark.gui
def test_fill_row_present_with_conditional_sub_rows(qtbot) -> None:
    """The Fill row exists above Color with Solid|Gradient|Pattern (+Mixed
    capability); the sub-rows appear EXACTLY for Gradient (Color B + Angle)
    and Pattern (Image… + Scale); a legacy solid style loads Solid with all
    sub-rows hidden."""
    panel = _make_inspector(qtbot)

    # Widgets + ranges (UI == model clamps by construction).
    assert isinstance(panel.fill_combo, QComboBox)
    assert [panel.fill_combo.itemText(i) for i in range(panel.fill_combo.count())] == [
        "Solid", "Gradient", "Pattern",
    ]
    assert panel.fill_angle_spin.minimum() == 0
    assert panel.fill_angle_spin.maximum() == 359
    assert panel.fill_angle_spin.suffix() == "\u00b0"
    assert panel.fill_scale_spin.minimum() == 0.10
    assert panel.fill_scale_spin.maximum() == 10.00
    assert panel.fill_scale_spin.suffix() == "\u00d7"
    assert isinstance(panel.fill_image_button, QToolButton)

    # Legacy default style (fill_type solid): Solid shown, sub-rows hidden.
    panel.load_box(_pagebox_with_style())
    assert panel.fill_combo.currentText() == "Solid"
    assert panel.fill_color_b_swatch.isHidden() is True
    assert panel.fill_angle_spin.isHidden() is True
    assert panel.fill_image_button.isHidden() is True
    assert panel.fill_scale_spin.isHidden() is True

    # Gradient: Color B + Angle visible, Image + Scale hidden.
    panel.load_box(
        _pagebox_with_style(
            fill_type="gradient", fill_color_b="#00ff00", fill_angle_deg=45.0
        )
    )
    assert panel.fill_combo.currentText() == "Gradient"
    assert panel.fill_color_b_swatch.isHidden() is False
    assert panel.fill_angle_spin.isHidden() is False
    assert panel.fill_image_button.isHidden() is True
    assert panel.fill_scale_spin.isHidden() is True
    assert panel.fill_color_b_swatch.color == "#00ff00"
    assert panel.fill_angle_spin.value() == 45

    # Pattern: Image + Scale visible, Color B + Angle hidden.
    panel.load_box(
        _pagebox_with_style(
            fill_type="pattern", pattern_scale=2.5,
            pattern_tile_b64=_tile_png_b64(),
        )
    )
    assert panel.fill_combo.currentText() == "Pattern"
    assert panel.fill_color_b_swatch.isHidden() is True
    assert panel.fill_angle_spin.isHidden() is True
    assert panel.fill_image_button.isHidden() is False
    assert panel.fill_scale_spin.isHidden() is False
    assert panel.fill_scale_spin.value() == 2.5
    assert "8x8" in panel.fill_image_button.toolTip()


@pytest.mark.gui
def test_fill_combo_commit_emits_only_type(qtbot) -> None:
    """Switching the Fill combo emits style_fill_changed with ONLY the
    fill_type key; the WR-01 loaded memory suppresses an unchanged cycle."""
    panel = _make_inspector(qtbot)
    fired = _fresh_fired()
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style())  # Solid

    panel.fill_combo.setCurrentText("Gradient")
    assert _fired_fill(fired) == [{"fill_type": "gradient"}]
    panel.fill_combo.setCurrentText("Pattern")
    assert _fired_fill(fired) == [
        {"fill_type": "gradient"}, {"fill_type": "pattern"},
    ]

    # WR-01: the loaded memory is the ORIGINAL Solid (this standalone panel
    # has no consumer reload), so switching back to Solid is an UNCHANGED
    # cycle — a no-op, never a spurious commit.
    panel.fill_combo.setCurrentText("Solid")
    assert len(_fired_fill(fired)) == 2, "an unchanged cycle must be a no-op"


@pytest.mark.gui
def test_fill_angle_and_scale_wr01_guards(qtbot) -> None:
    """Angle/Scale commit only on a REAL change (WR-01); a mixed sentinel
    load drops the no-op focus cycle (Pitfall 7)."""
    panel = _make_inspector(qtbot)
    fired = _fresh_fired()
    panel.connect_commit_handlers(**_style_callbacks(fired))

    panel.load_box(
        _pagebox_with_style(fill_type="gradient", fill_angle_deg=45.0)
    )
    # Unchanged focus cycle: nothing fires.
    panel.fill_angle_spin.setValue(45)
    panel.fill_angle_spin.editingFinished.emit()
    assert _fired_fill(fired) == []
    # A real change commits the angle only.
    panel.fill_angle_spin.setValue(120)
    panel.fill_angle_spin.editingFinished.emit()
    assert _fired_fill(fired) == [{"fill_angle_deg": 120.0}]

    panel.load_box(
        _pagebox_with_style(fill_type="pattern", pattern_scale=1.0)
    )
    panel.fill_scale_spin.setValue(1.00)
    panel.fill_scale_spin.editingFinished.emit()
    assert len(_fired_fill(fired)) == 1
    panel.fill_scale_spin.setValue(2.50)
    panel.fill_scale_spin.editingFinished.emit()
    assert _fired_fill(fired)[-1] == {"pattern_scale": 2.5}

    # Mixed sentinel loads (differing values across the selection): a no-op
    # cycle on the sentinel value drops.
    pb_a = _pagebox_with_style(fill_type="gradient", fill_angle_deg=30.0)
    pb_b = _pagebox_with_style(fill_type="gradient", fill_angle_deg=300.0)
    panel.load_multi_selection([pb_a, pb_b])
    assert panel._loaded_style_fill_angle is None
    assert panel.fill_angle_spin.specialValueText() == "Mixed"
    panel.fill_angle_spin.setValue(0)
    panel.fill_angle_spin.editingFinished.emit()
    assert len(_fired_fill(fired)) == 2


@pytest.mark.gui
def test_fill_color_b_picker_alpha_capable_and_wr01(qtbot, monkeypatch) -> None:
    """The Color B picker carries ShowAlphaChannel | DontUseNativeDialog and
    emits the canonical HexArgb spelling; re-picking the loaded color in a
    different opaque spelling is a WR-01 no-op."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    panel = _make_inspector(qtbot)
    fired = _fresh_fired()
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(
        _pagebox_with_style(fill_type="gradient", fill_color_b="#ffffff")
    )
    captured: dict = {}

    def fake_get_color(*args, **kwargs):
        captured["args"] = args
        return QColor("#40ff0000")

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(fake_get_color))
    panel.fill_color_b_swatch.clicked.emit()

    # getColor(parent, title, color, options) — the options ride the 4th
    # positional slot (the quick-260909-nj9 picker's calling convention).
    assert len(captured["args"]) == 4, (
        "the Color B picker must pass the dialog options positionally"
    )
    options = captured["args"][3]
    assert options is not None
    assert options & QColorDialog.ColorDialogOption.ShowAlphaChannel
    assert options & QColorDialog.ColorDialogOption.DontUseNativeDialog
    assert _fired_fill(fired) == [{"fill_color_b": "#40ff0000"}]

    # WR-01 (alpha-aware, the _norm_hex_a discipline): after the consumer
    # reload carries the committed color, re-picking it in the OPAQUE
    # spelling (#ff0000 -> #ffff0000) is a no-op — never a spurious commit.
    panel.load_box(
        _pagebox_with_style(fill_type="gradient", fill_color_b="#ffff0000")
    )
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#ff0000"))
    )
    panel.fill_color_b_swatch.clicked.emit()
    assert len(_fired_fill(fired)) == 1, (
        "re-picking the loaded color in another opaque spelling must be a no-op"
    )


@pytest.mark.gui
def test_pattern_tile_pick_commits_and_same_file_is_noop(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Picking a tile file commits {fill_type: pattern, pattern_tile_b64};
    re-picking the SAME bytes is a WR-01 no-op; cancelling commits nothing."""
    from PySide6.QtWidgets import QFileDialog

    panel = _make_inspector(qtbot)
    fired = _fresh_fired()
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style())

    tile_path = _write_tile_file(tmp_path)

    # Cancel: nothing happens.
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))
    )
    panel.fill_image_button.clicked.emit()
    assert _fired_fill(fired) == []

    # First pick: the tile commits with the fill-type switch.
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(tile_path), "")),
    )
    panel.fill_image_button.clicked.emit()
    assert len(_fired_fill(fired)) == 1
    first = _fired_fill(fired)[0]
    assert first["fill_type"] == "pattern"
    assert first["pattern_tile_b64"] == _tile_png_b64()

    # Re-pick the same bytes: WR-01 no-op.
    panel.fill_image_button.clicked.emit()
    assert len(_fired_fill(fired)) == 1


@pytest.mark.gui
def test_oversize_tile_warns_and_commits_nothing(qtbot, tmp_path, monkeypatch) -> None:
    """A tile above the real 4 MB FILL_TILE_MAX_BYTES cap shows the LOCKED
    warning dialog and commits NOTHING (never a corrupt save)."""
    import os

    from PIL import Image as PILImage
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from manga_ai_studio.core.text_style import FILL_TILE_MAX_BYTES

    panel = _make_inspector(qtbot)
    fired = _fresh_fired()
    panel.connect_commit_handlers(**_style_callbacks(fired))
    panel.load_box(_pagebox_with_style())

    # A genuinely oversized noise PNG (incompressible random bytes -> the
    # encoded PNG lands well above the 4 MB cap).
    w = h = 1300
    noise = PILImage.frombuffer(
        "RGBA", (w, h), os.urandom(w * h * 4), "raw", "RGBA", 0, 1
    )
    big_path = tmp_path / "big_tile.png"
    noise.save(big_path, format="PNG")
    assert big_path.stat().st_size > FILL_TILE_MAX_BYTES

    warnings: list = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(big_path), "")),
    )

    panel.fill_image_button.clicked.emit()
    assert len(warnings) == 1, "the oversize tile must show the warning dialog"
    assert _fired_fill(fired) == [], "an oversize tile must commit NOTHING"
    assert panel._loaded_style_pattern_tile is None


@pytest.mark.gui
def test_mixed_fill_types_show_sentinel_and_commit_nothing(qtbot) -> None:
    """Differing fill TYPES across the selection show the non-editable
    "Mixed" sentinel, hide the sub-rows, and NEVER commit (Pitfall 7)."""
    panel = _make_inspector(qtbot)
    fired = _fresh_fired()
    panel.connect_commit_handlers(**_style_callbacks(fired))

    pb_solid = _pagebox_with_style(fill_type="solid")
    pb_gradient = _pagebox_with_style(fill_type="gradient")
    panel.load_multi_selection([pb_solid, pb_gradient])

    assert panel.fill_combo.currentText() == "Mixed"
    assert panel._loaded_style_fill_display == "Mixed"
    # Mixed hides every sub-row (no single fill type governs them).
    assert panel.fill_color_b_swatch.isHidden() is True
    assert panel.fill_angle_spin.isHidden() is True
    assert panel.fill_image_button.isHidden() is True
    assert panel.fill_scale_spin.isHidden() is True

    # Re-picking the sentinel commits nothing.
    panel.fill_combo.setCurrentText("Mixed")
    assert _fired_fill(fired) == []

    # A REAL override still commits.
    panel.fill_combo.setCurrentText("Pattern")
    assert _fired_fill(fired) == [{"fill_type": "pattern"}]


@pytest.mark.gui
def test_fill_multi_uniform_shows_values_and_mixed_sub_fields(qtbot) -> None:
    """A uniform fill type loads the common values; a differing sub-field
    shows its per-widget Mixed sentinel (angle spin special text)."""
    panel = _make_inspector(qtbot)
    pb_a = _pagebox_with_style(
        fill_type="gradient", fill_color_b="#00ff00", fill_angle_deg=45.0
    )
    pb_b = _pagebox_with_style(
        fill_type="gradient", fill_color_b="#00ff00", fill_angle_deg=45.0
    )
    panel.load_multi_selection([pb_a, pb_b])
    assert panel.fill_combo.currentText() == "Gradient"
    assert panel._loaded_style_fill_display == "Gradient"
    assert panel.fill_angle_spin.value() == 45
    assert panel.fill_color_b_swatch.color == "#00ff00"
    assert panel.fill_color_b_swatch.isHidden() is False

    # Differing angle -> the Mixed sentinel on the spin (types stay uniform).
    pb_c = _pagebox_with_style(
        fill_type="gradient", fill_color_b="#00ff00", fill_angle_deg=300.0
    )
    panel.load_multi_selection([pb_a, pb_c])
    assert panel._loaded_style_fill_angle is None
    assert panel.fill_angle_spin.specialValueText() == "Mixed"


def _grab_swatch(swatch):
    """Render a swatch button into an image (paint smoke-test helper)."""
    from PySide6.QtGui import QImage as _QImage

    pixmap = swatch.grab()
    return _QImage(pixmap.toImage().convertToFormat(_QImage.Format.Format_ARGB32))


@pytest.mark.gui
def test_swatch_preview_paints_real_gradient_and_pattern(qtbot) -> None:
    """LOCKED UI decision: the MAIN Color swatch previews the REAL fill —
    gradient mode paints the ramp (left != right at 0 deg), pattern mode
    tiles the loaded tile, and a legacy solid keeps the solid mode. Paint
    smoke-tests — none may raise."""
    panel = _make_inspector(qtbot)

    # Gradient preview: 0 deg blue->yellow must differ left-to-right.
    panel.load_box(
        _pagebox_with_style(
            color="#ff0000ff",
            fill_type="gradient",
            fill_color_b="#ffffff00",
            fill_angle_deg=0.0,
        )
    )
    assert panel.color_swatch.preview_mode == "gradient"
    img = _grab_swatch(panel.color_swatch)
    assert not img.isNull()
    left = img.pixelColor(2, 12)
    right = img.pixelColor(21, 12)
    assert (left.blue(), left.red()) != (right.blue(), right.red()), (
        "the gradient preview must paint a left-to-right ramp"
    )

    # Pattern preview: the mode flips and the paint stays clean.
    panel.load_box(
        _pagebox_with_style(
            color="#ff0000ff",
            fill_type="pattern",
            pattern_tile_b64=_tile_png_b64(8, 8),
        )
    )
    assert panel.color_swatch.preview_mode == "pattern"
    assert panel.color_swatch.preview_tile is not None
    img = _grab_swatch(panel.color_swatch)
    assert not img.isNull()

    # Solid legacy: the preview mode stays solid (today's paint verbatim).
    panel.load_box(_pagebox_with_style())
    assert panel.color_swatch.preview_mode == "solid"


@pytest.mark.gui
def test_mainwindow_fill_commit_applies_to_all_selected_and_preserves_tile(
    qtbot, tmp_path
) -> None:
    """The MainWindow fill handler applies to ALL selected boxes through
    _replace_style (one BOXES snapshot); a commit WITHOUT pattern_tile_b64
    never clobbers an existing tile; an unknown key is dropped (T-vej-04);
    one Ctrl+Z reverses the whole fill commit."""
    window = _window_with_page(qtbot, tmp_path)
    items = _seed_boxes_window(
        window, [Box(10, 10, 70, 50), Box(10, 60, 70, 100)]
    )
    # Explicit legacy-solid styles so the final undo restore is exact.
    items[0].pagebox.style = TextStyle()
    items[1].pagebox.style = TextStyle()
    for it in items:
        it.setSelected(True)
    QApplication.processEvents()

    b64 = _tile_png_b64()
    panel = window.inspector_panel

    # 1) The combo switch commits gradient to EVERY selected box.
    panel.fill_combo.setCurrentText("Gradient")
    for it in items:
        assert it.pagebox.style is not None
        assert it.pagebox.style.fill_type == "gradient"

    # 2) The tile commit embeds the tile on every box.
    panel.style_fill_changed.emit(
        {"fill_type": "pattern", "pattern_tile_b64": b64}
    )
    for it in items:
        assert it.pagebox.style.pattern_tile_b64 == b64

    # 3) A scale-only commit must NOT clobber the tile.
    panel.fill_scale_spin.setValue(2.00)
    panel.fill_scale_spin.editingFinished.emit()
    for it in items:
        assert it.pagebox.style.pattern_tile_b64 == b64
        assert it.pagebox.style.pattern_scale == 2.0

    # 4) T-vej-04: an unknown key is dropped by the whitelist — the styles
    # stay bit-identical.
    before = [it.pagebox.style for it in items]
    panel.style_fill_changed.emit({"color": "#ff0000", "font_family": "Arial"})
    for it, style_before in zip(items, before):
        assert it.pagebox.style == style_before

    # 5) The commits rode the BOXES snapshot machinery: three undo steps
    # (scale -> tile -> fill-type) restore the pre-fill styles (solid).
    # The undo restore REBUILDS the canvas BoxItems — re-read, never the
    # stale pre-undo references.
    for _ in range(3):
        window.on_undo()
        QApplication.processEvents()
    restored = [it.pagebox for it in window.canvas._box_items]
    for pb in restored:
        assert pb.style is not None
        assert pb.style.fill_type == "solid"
        assert pb.style.pattern_tile_b64 is None


@pytest.mark.gui
def test_legacy_solid_style_round_trips_inspector_display(qtbot) -> None:
    """A legacy style (no fill keys) loads Solid with the default Color B /
    angle / scale memories — the exact legacy look, never Mixed."""
    panel = _make_inspector(qtbot)
    panel.load_box(_pagebox_with_style(color="#123456"))
    assert panel.fill_combo.currentText() == "Solid"
    assert panel._loaded_style_fill_display == "Solid"
    assert panel._loaded_style_fill_color_b == "#ffffff"
    assert panel._loaded_style_fill_angle == 90.0
    assert panel._loaded_style_pattern_scale == 1.0
    assert panel._loaded_style_pattern_tile is None
    assert panel.color_swatch.preview_mode == "solid"

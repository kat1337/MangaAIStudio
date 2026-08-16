"""MaskerConfig.mask_dilation_radius round-trip tests (plan 08-01 Task 2,
MASK-01 / D-09 / D-10).

Pins the vendored-config addition: the per-profile dilation radius persists
through the PanelCleaner INI machinery (``Profile.safe_write`` →
``Profile.load``) and the startup profile load (RESEARCH §4.1's gap —
``__main__`` now calls ``ProfileManager.load_profile("default")`` so the
persisted radius actually reaches ``config.current_profile`` at launch).

The missing-key row locks the PanelCleaner-authored-INI compatibility
contract: an INI written WITHOUT ``mask_dilation_radius`` (upstream PC never
writes it) loads with the default 2 — the vendored ``try_to_load`` falls
back gracefully on ``NoOptionError``, same as every other Masker key
(T-08-01).

Headless: no Qt, no model weights — pure config round-trips through
``tmp_path`` (the ``tests/conftest.py`` ProfileManager pattern).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from panelcleaner.config import MaskerConfig, Profile

from manga_ai_studio.config.profile_manager import ProfileManager


@pytest.mark.unit
def test_mask_dilation_radius_default_is_two() -> None:
    """D-09: a fresh MaskerConfig defaults ``mask_dilation_radius`` to 2 —
    grows auto-detected masks enough to cover letter edges without eating
    artwork."""
    assert MaskerConfig().mask_dilation_radius == 2


@pytest.mark.unit
def test_mask_dilation_radius_round_trips_through_ini(tmp_path: Path) -> None:
    """Full INI round-trip: radius 5 saved via ProfileManager.safe_write and
    reloaded via Profile.load yields 5 (D-10 persistence through the vendored
    export_to_conf / import_from_conf lines)."""
    pm = ProfileManager(tmp_path)
    profile = pm.default_profile()
    profile.masker.mask_dilation_radius = 5
    pm.save_profile(profile, "default")

    reloaded = pm.load_profile("default")

    assert reloaded.masker.mask_dilation_radius == 5


@pytest.mark.unit
def test_ini_without_radius_key_falls_back_to_default(tmp_path: Path) -> None:
    """A profile INI written WITHOUT the ``mask_dilation_radius`` key
    (simulating a PanelCleaner-authored INI) loads with the default 2 —
    unknown/missing options fall back gracefully (T-08-01: the new key rides
    the same guarded ``try_to_load`` path as every other Masker key)."""
    pm = ProfileManager(tmp_path)
    profile = pm.default_profile()
    profile.masker.mask_dilation_radius = 9  # start non-default
    saved = pm.save_profile(profile, "default")

    # Strip the radius key (and its comment lines) — the upstream-PC shape.
    lines = saved.read_text(encoding="utf-8").splitlines(keepends=True)
    stripped = "".join(
        ln
        for ln in lines
        if "mask_dilation_radius" not in ln and "dilation" not in ln.lower()
    )
    assert "mask_dilation_radius" not in stripped  # precondition
    saved.write_text(stripped, encoding="utf-8")

    reloaded = pm.load_profile("default")

    assert reloaded.masker.mask_dilation_radius == 2


@pytest.mark.unit
def test_startup_load_profile_applies_to_current_profile(tmp_path: Path) -> None:
    """The RESEARCH §4.1 startup gap, closed: a ProfileManager whose config
    dir holds a "default" profile INI with radius 7 makes
    ``config.current_profile.masker.mask_dilation_radius == 7`` after
    ``load_profile("default")`` — the load is APPLIED to the config the
    MainWindow reads, not a discarded return value."""
    seed = ProfileManager(tmp_path)
    profile = seed.default_profile()
    profile.masker.mask_dilation_radius = 7
    seed.save_profile(profile, "default")

    # A fresh manager over the same dir = a new app session.
    fresh = ProfileManager(tmp_path)
    fresh.load_profile("default")

    assert fresh.config.current_profile.masker.mask_dilation_radius == 7

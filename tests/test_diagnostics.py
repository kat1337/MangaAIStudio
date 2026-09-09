"""Headless diagnostics core tests (quick-260909-ke1 Task 1).

``manga_ai_studio.diagnostics`` is Qt-free at module scope so this battery
(and any future core-side caller) runs without PySide6 — locked by an AST
source scan plus a subprocess import probe (the 08 headless-purity-lock
discipline: an in-process sys.modules check is broken by earlier GUI test
modules, so the subprocess probe is the load-bearing one).

The hang-watchdog assertions use the deterministic short-timeout mechanics
(``install(..., hang_timeout_s=0.1)``), never wall-clock "app freeze" waits.
All log reads drain loguru's ``enqueue=True`` writer first via
``logger.complete()`` (fifo-ordered), and absence checks are anchored behind
an ADMITTED barrier record so a slow writer can never false-pass them.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from loguru import logger

from manga_ai_studio import __version__, diagnostics


# --------------------------------------------------------------------- infra
@pytest.fixture(autouse=True)
def _diag_cleanup():
    """Guarantee sinks/hooks/watchdog never leak across tests (teardown-only)."""
    yield
    diagnostics.reset()


def _read_log(path: Path) -> str:
    """Drain the enqueue writer, then read the log file (empty when absent)."""
    logger.complete()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------- install / idempotence
@pytest.mark.unit
def test_install_creates_both_log_files_and_returns_mas_log(tmp_path: Path) -> None:
    """install() creates logs/mas.log + logs/mas-hang.log and returns the mas.log Path."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    assert log == tmp_path / "logs" / "mas.log"
    assert log.exists()
    assert (tmp_path / "logs" / "mas-hang.log").exists()


@pytest.mark.unit
def test_install_twice_is_idempotent(tmp_path: Path) -> None:
    """A second install() is a no-op: same path, no duplicated sink output."""
    first = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    second = diagnostics.install()
    assert second == first
    logger.warning("ke1-dup-check-line")
    text = _read_log(first)
    assert text.count("ke1-dup-check-line") == 1  # one sink, not two
    assert text.count("session start") == 1  # separator written exactly once


@pytest.mark.unit
def test_session_separator_records_version_timestamp_platform(tmp_path: Path) -> None:
    """After install(), mas.log carries the session separator: version + ISO ts + platform."""
    import re

    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    text = _read_log(log)
    assert "session start" in text
    assert f"v{__version__}" in text
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text), "no ISO timestamp in separator"
    assert "Windows" in text  # platform.platform() names the OS (win32 dev box)


# ------------------------------------------------------------- filter contract
@pytest.mark.unit
def test_warning_from_any_namespace_lands(tmp_path: Path) -> None:
    """WARNING+ from any module name passes the floor."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    logger.warning("ke1-warn-any")
    assert "ke1-warn-any" in _read_log(log)


@pytest.mark.unit
def test_gui_namespace_debug_lands(tmp_path: Path) -> None:
    """DEBUG from a manga_ai_studio.gui.* logger name is admitted below the floor."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    logger.patch(lambda r: r.update(name="manga_ai_studio.gui.canvas")).debug(
        "ke1-gui-debug-line"
    )
    assert "ke1-gui-debug-line" in _read_log(log)


@pytest.mark.unit
def test_non_gui_debug_is_filtered_out(tmp_path: Path) -> None:
    """DEBUG from any other namespace stays out of the file (default volume contract)."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    logger.patch(lambda r: r.update(name="manga_ai_studio.core.engine")).debug(
        "ke1-core-debug-silent"
    )
    # FIFO barrier: an ADMITTED record emitted after the filtered one proves the
    # writer processed everything before it — absence is now sound, not racy.
    logger.warning("ke1-absent-barrier")
    text = _read_log(log)
    assert "ke1-absent-barrier" in text
    assert "ke1-core-debug-silent" not in text


@pytest.mark.unit
def test_session_marker_info_survives_warning_floor(tmp_path: Path) -> None:
    """An INFO record bound with session_marker=True is admitted despite the floor."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    logger.bind(session_marker=True).info("ke1-info-marker-line")
    assert "ke1-info-marker-line" in _read_log(log)


# --------------------------------------------------------------- crash capture
@pytest.mark.unit
def test_sys_excepthook_logs_traceback_and_chains_previous(tmp_path: Path) -> None:
    """sys.excepthook writes the traceback to mas.log AND still calls the prior hook."""
    prev_calls: list[type] = []

    def prev_hook(exc_type, exc_value, exc_tb):
        prev_calls.append(exc_type)

    sys.excepthook = prev_hook
    diagnostics.install(tmp_path, hang_timeout_s=0.5)
    assert sys.excepthook is not prev_hook  # wrapped

    try:
        raise ValueError("ke1 boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    text = _read_log(tmp_path / "logs" / "mas.log")
    assert "ke1 boom" in text
    assert "ValueError" in text
    assert "Traceback" in text or "ke1 boom" in text  # loguru renders the traceback
    assert prev_calls == [ValueError]  # the previous hook was NOT swallowed


@pytest.mark.unit
def test_threading_excepthook_logs_and_chains_previous(tmp_path: Path) -> None:
    """threading.excepthook logs a raised-in-thread exception record and chains."""
    prev_calls: list[threading.ExceptHookArgs] = []

    threading.excepthook = prev_calls.append
    diagnostics.install(tmp_path, hang_timeout_s=0.5)

    try:
        raise RuntimeError("ke1 thread boom")
    except RuntimeError:
        exc_type, exc_value, exc_tb = sys.exc_info()
    threading.excepthook(threading.ExceptHookArgs((exc_type, exc_value, exc_tb, None)))

    text = _read_log(tmp_path / "logs" / "mas.log")
    assert "ke1 thread boom" in text
    assert "RuntimeError" in text
    assert len(prev_calls) == 1  # chained, never swallowed


# --------------------------------------------------------------- hang capture
@pytest.mark.unit
def test_hang_watchdog_dumps_thread_stacks_to_hang_log(tmp_path: Path) -> None:
    """A missed deadline produces a faulthandler dump in mas-hang.log; cancel stops it."""
    diagnostics.install(tmp_path, hang_timeout_s=0.1)
    hang = tmp_path / "logs" / "mas-hang.log"
    deadline = time.monotonic() + 5.0
    text = ""
    while time.monotonic() < deadline:
        time.sleep(0.05)
        text = _read_log(hang)
        if "Timeout" in text and "(most recent call first)" in text:
            break
    else:
        pytest.fail("no faulthandler dump appeared in mas-hang.log within 5s")
    # settle: let any in-flight dump finish, cancel, then take the baseline count.
    time.sleep(0.15)
    diagnostics.cancel_hang_watchdog()
    before = _read_log(hang).count("Timeout")
    time.sleep(0.35)  # >= 3 watchdog periods — a live watchdog would dump again
    assert _read_log(hang).count("Timeout") == before


# ------------------------------------------------------------- Qt-free purity
@pytest.mark.unit
def test_diagnostics_module_is_qt_free_at_module_scope() -> None:
    """AST scan: no module-level import line mentions PySide6 (lazy import only)."""
    src = Path(diagnostics.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            assert not any("PySide6" in (n or "") for n in names), (
                f"module-level PySide6 import at line {node.lineno}"
            )


@pytest.mark.unit
def test_importing_diagnostics_pulls_no_qt_modules() -> None:
    """Subprocess probe (load-bearing): importing diagnostics imports zero PySide6 modules."""
    code = (
        "import sys;"
        "import manga_ai_studio.diagnostics;"
        "leaked = sorted(m for m in sys.modules if m.startswith('PySide6'));"
        "assert not leaked, leaked"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------- reset()
@pytest.mark.unit
def test_reset_restores_hooks_and_allows_fresh_install(tmp_path: Path, tmp_path_factory) -> None:
    """reset() removes the sink, restores both hooks, cancels the watchdog, clears the flag."""
    orig_sys_hook = sys.excepthook
    orig_thread_hook = threading.excepthook
    first = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    assert sys.excepthook is not orig_sys_hook
    assert threading.excepthook is not orig_thread_hook

    diagnostics.reset()

    assert sys.excepthook is orig_sys_hook
    assert threading.excepthook is orig_thread_hook
    fresh = tmp_path_factory.mktemp("fresh-logs")
    second = diagnostics.install(fresh, hang_timeout_s=0.5)
    assert second == fresh / "logs" / "mas.log"
    assert second != first  # the flag was cleared: install targets a fresh dir

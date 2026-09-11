"""Headless diagnostics core tests (quick-260909-ke1 Tasks 1-3).

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

Task 2 (native crash reporting) and Task 3 (heartbeat memory telemetry) extend
this file: the Windows-only crash-logger battery covers install idempotence,
graceful degradation on a broken OS-export path, report decoding (SIGABRT text
+ fabricated ACCESS_VIOLATION records resolved to module!offset), the
UEF/SIGABRT latching + chaining contracts, and a subprocess end-to-end abort
proving no dump files are written; the telemetry battery covers formatting,
latching, env overrides and the heartbeat cadence (all psutil-free via
fakes/monkeypatching).
"""

from __future__ import annotations

import ast
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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


# ---------------------------------------------- native crash reporting (Task 2)
_win_only = pytest.mark.skipif(
    sys.platform != "win32", reason="native crash reporting is Windows-only"
)


@_win_only
@pytest.mark.unit
def test_install_native_crash_logger_is_idempotent_and_reset_restores(
    tmp_path: Path,
) -> None:
    """install_native_crash_logger() arms once; reset() deregisters and restores."""
    apis = diagnostics._load_windows_apis()
    diagnostics.install(tmp_path, hang_timeout_s=0.5)
    assert diagnostics._crash_logger_installed  # install() arms it again
    assert diagnostics._md_filter_cb is not None  # ctypes callback kept alive
    assert diagnostics._md_sigabrt_cb is not None
    first_prev = diagnostics._md_filter_prev

    # Idempotence: a second call re-captures nothing (the previous filter
    # stays the one install() saw — never OUR own filter).
    diagnostics.install_native_crash_logger()
    assert diagnostics._md_filter_prev is first_prev

    diagnostics.reset()
    assert not diagnostics._crash_logger_installed
    assert diagnostics._md_filter_cb is None
    # Round-trip: the process filter is back to what install() captured. The
    # read itself installs NULL, so put the captured value back afterwards.
    now = apis.set_unhandled_exception_filter(None)
    apis.set_unhandled_exception_filter(first_prev)
    assert now == first_prev


@_win_only
@pytest.mark.unit
def test_native_crash_logger_degrades_gracefully_without_apis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing/broken OS-export path is swallowed: install() still completes."""
    def boom():
        raise OSError("no ntdll/psapi exports on this box")

    monkeypatch.setattr(diagnostics, "_load_windows_apis", boom)
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    assert log.exists()  # the rest of install() is untouched
    assert not diagnostics._crash_logger_installed
    assert diagnostics._md_filter_cb is None
    diagnostics.install_native_crash_logger()  # direct call: also safe
    assert not diagnostics._crash_logger_installed


@_win_only
@pytest.mark.unit
def test_native_crash_report_sigabrt_text_and_stack() -> None:
    """The SIGABRT-shape report names the abort and lists a module-resolved stack."""
    report = diagnostics._native_crash_report(None)
    assert "Native abort (SIGABRT)" in report
    assert "Native stack (innermost first):" in report
    # Frames resolve to module!+0xoffset (the capture runs on a live thread —
    # at least our own python314/ntdll frames must be resolvable).
    assert "!+0x" in report


@_win_only
@pytest.mark.unit
def test_native_crash_report_decodes_access_violation() -> None:
    """A fabricated AV EXCEPTION_POINTERS decodes code, access type, and module."""
    import ctypes

    class _EXCEPTION_RECORD(ctypes.Structure):
        _fields_ = [
            ("ExceptionCode", ctypes.c_int32),
            ("ExceptionFlags", ctypes.c_uint32),
            ("ExceptionRecord", ctypes.c_void_p),
            ("ExceptionAddress", ctypes.c_void_p),
            ("NumberParameters", ctypes.c_uint32),
            ("ExceptionInformation", ctypes.c_uint64 * 15),
        ]

    class _EXCEPTION_POINTERS(ctypes.Structure):
        _fields_ = [
            ("ExceptionRecord", ctypes.POINTER(_EXCEPTION_RECORD)),
            ("ContextRecord", ctypes.c_void_p),
        ]

    # Faulting "address" = a real kernel32 function pointer, so module
    # resolution must land IN kernel32.dll.
    kernel32 = ctypes.WinDLL("kernel32")
    fault_addr = ctypes.cast(kernel32.GetCurrentProcess, ctypes.c_void_p).value

    rec = _EXCEPTION_RECORD()
    rec.ExceptionCode = 0xC0000005
    rec.ExceptionAddress = fault_addr
    rec.NumberParameters = 2
    rec.ExceptionInformation[0] = 1  # write access
    rec.ExceptionInformation[1] = 0xDEADBEEF
    pointers = _EXCEPTION_POINTERS(ctypes.pointer(rec), None)

    report = diagnostics._native_crash_report(ctypes.addressof(pointers))
    assert "0xC0000005" in report and "ACCESS_VIOLATION" in report
    assert "write to 0x00000000DEADBEEF" in report
    assert "kernel32.dll!+0x" in report.lower()  # OS returns the base name as-is
    assert f"0x{fault_addr:016X}" not in report  # resolved, not raw


@_win_only
@pytest.mark.unit
def test_crash_filter_reports_once_latches_and_logs(
    tmp_path: Path,
) -> None:
    """The UEF logs ONE report per session, latches, and keeps chaining."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    assert (
        diagnostics._unhandled_exception_filter(None)
        == diagnostics.EXCEPTION_CONTINUE_SEARCH
    )
    assert (
        diagnostics._unhandled_exception_filter(None)
        == diagnostics.EXCEPTION_CONTINUE_SEARCH
    )
    text = _read_log(log)
    assert text.count("Native abort (SIGABRT)") == 1  # exactly once (latched)
    assert "Native stack (innermost first):" in text


@_win_only
@pytest.mark.unit
def test_crash_filter_chains_previous_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The UEF chains the previous filter and returns ITS verdict."""
    import ctypes

    seen: list[int | None] = []
    apis = diagnostics._load_windows_apis()
    prev_cb = apis.filter_func(lambda pointers: seen.append(pointers) or 7)
    prev_addr = ctypes.cast(prev_cb, ctypes.c_void_p).value
    monkeypatch.setattr(diagnostics, "_md_apis", apis)
    monkeypatch.setattr(diagnostics, "_md_filter_prev", prev_addr)
    monkeypatch.setattr(
        diagnostics, "_log_native_crash", lambda exception_pointers=None: None
    )
    assert diagnostics._unhandled_exception_filter(1234) == 7
    assert seen == [1234]


@_win_only
@pytest.mark.unit
def test_sigabrt_handler_reports_uninstalls_then_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The C-level SIGABRT handler reports, restores prev into the slot, chains."""
    import ctypes

    apis = diagnostics._load_windows_apis()
    chained: list[int] = []
    prev_cb = apis.sigabrt_func(lambda signum: chained.append(signum))
    prev_addr = ctypes.cast(prev_cb, ctypes.c_void_p).value
    signal_calls: list[tuple[int, int]] = []

    def recording_signal(sig: int, handler: int) -> int:
        signal_calls.append((sig, handler))
        return prev_addr

    apis = apis._replace(signal=recording_signal)  # NamedTuple: immutably swap
    reports: list[int | None] = []
    monkeypatch.setattr(diagnostics, "_md_apis", apis)
    monkeypatch.setattr(diagnostics, "_md_sigabrt_prev", prev_addr)
    monkeypatch.setattr(
        diagnostics,
        "_log_native_crash",
        lambda exception_pointers=None: reports.append(exception_pointers),
    )

    diagnostics._abort_sigabrt_handler(22)

    assert reports == [None]  # the abort-shape report was produced exactly once
    assert chained == [22]  # the previous handler (faulthandler's) was chained
    # ...and our handler uninstalled itself first (re-raise cannot recurse).
    assert signal_calls == [(apis.sigabrt, prev_addr)]


@_win_only
@pytest.mark.unit
def test_abort_in_subprocess_logs_report_and_chains_faulthandler(
    tmp_path: Path,
) -> None:
    """End-to-end: a real abort() lands a TEXT report AND keeps the hang dump.

    The load-bearing proof for the observed crash shape (native abort with no
    Python slot frames): the C-level SIGABRT handler writes the textual crash
    report into mas.log, then chains to faulthandler's handler so mas-hang.log
    still gets the all-thread Python dump — and NO .dmp file is written.
    """
    logs = tmp_path / "logs"
    code = (
        "import manga_ai_studio.diagnostics as d;"
        f"d.install({str(tmp_path)!r}, hang_timeout_s=60.0);"
        # install() arms the crash logger itself; the explicit call documents
        # that this pipeline no longer depends on any dump machinery.
        "d.install_native_crash_logger();"
        "import ctypes;"
        'ctypes.CDLL("ucrtbase.dll").abort()'
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert not list(logs.glob("*.dmp")), "no dump files may be written"
    text = (logs / "mas.log").read_text(encoding="utf-8", errors="replace")
    assert "Native abort (SIGABRT)" in text  # the report landed
    assert "Native stack (innermost first):" in text
    hang = (logs / "mas-hang.log").read_text(encoding="utf-8", errors="replace")
    assert "Fatal Python error" in hang  # the chained faulthandler dump landed


# ------------------------------------------------- memory telemetry (Task 3)
@pytest.mark.unit
def test_memory_threshold_warnings_format_and_latch() -> None:
    """Warn-once per threshold: formats the crossing, never repeats, independent."""
    latches = {"rss": False, "commit": False}
    assert diagnostics._memory_threshold_warnings(1000.0, 40.0, 8192.0, 90.0, latches) == []
    crossed = diagnostics._memory_threshold_warnings(9000.0, 40.0, 8192.0, 90.0, latches)
    assert len(crossed) == 1
    assert "RSS 9000MB" in crossed[0]
    assert "8192MB" in crossed[0]
    assert diagnostics._memory_threshold_warnings(9500.0, 40.0, 8192.0, 90.0, latches) == []
    # The commit latch is independent of the RSS latch.
    crossed = diagnostics._memory_threshold_warnings(9500.0, 95.0, 8192.0, 90.0, latches)
    assert len(crossed) == 1
    assert "commit 95.0%" in crossed[0]
    assert latches == {"rss": True, "commit": True}


@pytest.mark.unit
def test_memory_thresholds_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """MAS_MEM_RSS_WARN_MB / MAS_MEM_COMMIT_WARN_PCT override; junk falls back."""
    monkeypatch.setenv("MAS_MEM_RSS_WARN_MB", "4096")
    monkeypatch.setenv("MAS_MEM_COMMIT_WARN_PCT", "70")
    assert diagnostics._memory_thresholds() == (4096.0, 70.0)
    monkeypatch.setenv("MAS_MEM_RSS_WARN_MB", "not-a-number")
    thresholds = diagnostics._memory_thresholds()
    assert thresholds[0] == float(diagnostics.MEM_RSS_WARN_MB_DEFAULT)
    assert thresholds[1] == 70.0


@pytest.mark.unit
def test_sample_and_log_memory_info_line_and_latched_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every sample logs the INFO line; the threshold WARNING lands once."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    fake = SimpleNamespace(
        Process=lambda: SimpleNamespace(
            memory_info=lambda: SimpleNamespace(rss=9 * 1024**3)
        ),
        swap_memory=lambda: SimpleNamespace(percent=50.0),
    )
    monkeypatch.setitem(sys.modules, "psutil", fake)
    diagnostics._sample_and_log_memory()
    diagnostics._sample_and_log_memory()
    text = _read_log(log)
    assert text.count("memory: rss=9216MB commit=50.0%") == 2  # INFO every sample
    assert text.count("RSS 9216MB") == 1  # WARNING latched after the first


@pytest.mark.unit
def test_sample_and_log_memory_swallows_psutil_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing psutil degrades silently: no raise, heartbeat keeps ticking."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    monkeypatch.setitem(sys.modules, "psutil", None)  # ImportError on import
    diagnostics._sample_and_log_memory()  # must not raise
    logger.warning("ke1-mem-barrier")
    assert "ke1-mem-barrier" in _read_log(log)


@pytest.mark.unit
def test_heartbeat_tick_samples_memory_every_nth_beat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The watchdog re-arm stays per-beat; the memory sample runs every Nth."""
    diagnostics.install(tmp_path, hang_timeout_s=0.5)
    launches: list[int] = []
    monkeypatch.setattr(diagnostics, "_launch_memory_sample", lambda: launches.append(1))
    for _ in range(diagnostics.HEARTBEAT_TELEMETRY_EVERY_N * 2 + 2):
        diagnostics._heartbeat_tick()
    assert launches == [1, 1]  # exactly the N-th and 2N-th beats


@pytest.mark.unit
def test_launch_memory_sample_runs_sampler_in_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_launch_memory_sample runs the sampler on a daemon thread (never inline)."""
    diagnostics.install(tmp_path, hang_timeout_s=0.5)
    done = threading.Event()
    threads: list[threading.Thread] = []
    monkeypatch.setattr(
        diagnostics,
        "_sample_and_log_memory",
        lambda: (threads.append(threading.current_thread()), done.set()),
    )
    diagnostics._launch_memory_sample()
    assert done.wait(5.0)
    assert threads[0].name == "mas-mem-telemetry"
    assert threads[0].daemon
    assert threads[0] is not threading.current_thread()

"""Application diagnostics: file logging + crash/freeze capture (quick-260909-ke1).

The app had ZERO diagnostics infrastructure: loguru had no sinks configured
(every ``logger.*`` call died with the console), no ``sys.excepthook``, no
``threading.excepthook``, no ``faulthandler`` — an exception inside a Qt slot
and a main-thread wedge were both completely invisible. This module installs,
in one :func:`install` call:

- ONE rotating loguru file sink (``logs/mas.log``, 5 MB, retention 3,
  ``enqueue=True`` so a slow disk write can never stall the GUI thread — this
  is a stability tool). The filter admits a record when its level is WARNING+,
  OR its logger name lives in the ``manga_ai_studio.gui`` namespace (the DEBUG
  breadcrumbs below the modest default volume), OR it carries the
  ``session_marker`` extra (the session separator survives the WARNING floor).
- Crash capture: ``sys.excepthook`` + ``threading.excepthook`` are wrapped —
  the traceback is logged at ERROR, then the PREVIOUS hook is chained (never
  swallowed). PySide6 6.10 routes unhandled slot exceptions to
  ``sys.excepthook``, so the one hook covers CLI + slot paths (proven by
  ``tests/test_gui_diagnostics.py`` on the installed version).
- Hang capture: ``faulthandler.enable`` + ``dump_traceback_later`` armed into
  a SEPARATE ``logs/mas-hang.log`` file handle (faulthandler writes raw from
  its watchdog thread; sharing a file with loguru's appender risks
  interleaving on Windows). :func:`heartbeat` (Task 2) re-arms the deadline
  from a QTimer ticked by the event loop, so a live loop never dumps and a
  wedged loop produces an all-thread stack dump ~60s in — zero code changes
  needed at freeze time (the watchdog thread does not need the frozen main
  thread's cooperation).
- Native-crash text reports (Windows, quick-260909-ke1 task 2; log-only since
  2026-09-10): the 2026-09-09 17:04 session died as ``Fatal Python error:
  Aborted`` — a SIGABRT raised in native code dispatched by the Qt event loop,
  invisible to faulthandler's Python-frame dump on Windows (``<cannot get C
  stack on this system>``). A top-level unhandled-exception filter
  (``kernel32.SetUnhandledExceptionFilter``) plus a C-LEVEL SIGABRT handler
  (``ucrtbase.signal``) write a TEXT crash report into mas.log: the exception
  code (named for the common NTSTATUS values), the faulting frame resolved to
  ``module!+0xoffset``, and the native stack of the faulting thread as
  ``module!+0xoffset`` lines (``ntdll.RtlCaptureStackBackTrace`` + psapi module
  resolution) — a few KB, never a dump file (the original
  ``dbghelp.MiniDumpWriteDump`` wiring produced multi-GB .dmp files of OOM-scale
  sessions and was disabled). abort() is first routed through ``raise(SIGABRT)``
  by clearing the CRT ``_CALL_REPORTFAULT`` bit (``ucrtbase._set_abort_behavior``)
  so the fail-fast/Watson path cannot skip the handler. A PYTHON-level
  ``signal.signal(SIGABRT, ...)`` handler was deliberately NOT used: CPython's
  signal handler only trips a flag consumed at the next eval-loop bytecode
  boundary — a native abort never returns to the eval loop, so the Python
  function would never run, and installing it would displace faulthandler's C
  handler and LOSE the mas-hang.log stack dump. The ctypes SIGABRT handler
  instead chains to the PREVIOUS C handler (faulthandler's) after uninstalling
  itself, so the all-thread Python dump is preserved and no re-raise can
  recurse into us. The UEF and SIGABRT handler can both fire for one abort; at
  most ONE report per session is logged (``_native_crash_logged`` latch).
  Everything is best-effort: any ctypes/OS failure degrades to the pre-existing
  behavior (a DEBUG line, no exception) — never an app break. NB a ctypes
  callback acquires the GIL, so capture from an aborting NATIVE thread can
  stall while the (dying) main thread holds the GIL; for the observed crash
  shape — the aborting thread IS the main thread — it re-enters immediately.
- Heartbeat memory telemetry (quick-260909-ke1 task 3): every
  ``HEARTBEAT_TELEMETRY_EVERY_N``-th heartbeat beat (~once a minute at the
  15s default) logs one INFO line with the process RSS and the system commit
  percent (psutil; sampled on a daemon thread so the tick itself never
  blocks, and guarded — telemetry never breaks the heartbeat), plus a
  latched WARNING when the RSS crosses ``MAS_MEM_RSS_WARN_MB`` (default
  8192) or commit crosses ``MAS_MEM_COMMIT_WARN_PCT`` (default 90). This
  makes the next bad_alloc-style abort conclusively attributable from the
  log timeline alone.

Module scope imports ONLY stdlib + loguru (PySide6 stays out so the core
battery and future core-side callers never need Qt); the Qt-touching helpers
(:func:`heartbeat`, :func:`install_qt_message_handler`) and the native crash
helpers (:func:`install_native_crash_logger`, :func:`_native_crash_report`)
import lazily.

The platform truth for the watchdog dump header is ``Timeout (...)!`` followed
by ``Thread 0x... (most recent call first):`` lines (measured on this
Windows/CPython 3.14 box — the "Current thread" label only appears when the
crashing thread dumps itself).
"""

from __future__ import annotations

import faulthandler
import os
import platform
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from loguru import logger

from manga_ai_studio import __version__

__all__ = [
    "HANG_TIMEOUT_S",
    "HEARTBEAT_TELEMETRY_EVERY_N",
    "MEM_COMMIT_WARN_PCT_DEFAULT",
    "MEM_RSS_WARN_MB_DEFAULT",
    "install",
    "reset",
    "cancel_hang_watchdog",
    "heartbeat",
    "stop_heartbeat",
    "install_qt_message_handler",
    "install_native_crash_logger",
]

# The production watchdog deadline (seconds). A main-thread stall longer than
# this is by definition a freeze worth dumping; expected long operations run on
# the Worker thread, so the live event loop re-arms the deadline forever.
HANG_TIMEOUT_S = 60.0

_LOG_FILE_NAME = "mas.log"
_HANG_FILE_NAME = "mas-hang.log"
_GUI_NAMESPACE = "manga_ai_studio.gui"
_ROTATION = "5 MB"
_RETENTION = 3
# loguru WARNING severity number (the admission floor).
_WARNING_LEVEL_NO = 30

# ------------------------------------------------------- memory telemetry
# One INFO sample every N-th heartbeat beat (~1/min at the 15s default).
HEARTBEAT_TELEMETRY_EVERY_N = 4
# High-water defaults (env-overridable at call time, see _memory_thresholds):
# a warn at 8 GB RSS / 90% system commit makes an OOM-style native abort
# attributable from the mas.log timeline alone. RSS covers torch/scipy
# residency; commit catches the system-level push toward allocation failure.
MEM_RSS_WARN_MB_DEFAULT = 8 * 1024
MEM_COMMIT_WARN_PCT_DEFAULT = 90.0
_ENV_MEM_RSS_MB = "MAS_MEM_RSS_WARN_MB"
_ENV_MEM_COMMIT_PCT = "MAS_MEM_COMMIT_WARN_PCT"

# ---------------------------------------------------- native crash reporting
# Text-only since 2026-09-10: the MiniDumpWriteDump wiring produced multi-GB
# .dmp files of OOM-scale sessions; the report below is a few KB of mas.log.
# Common NTSTATUS exception codes, for the report header only.
_CRASH_CODE_NAMES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000409: "STACK_BUFFER_OVERRUN / fail-fast",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC0000096: "PRIVILEGED_INSTRUCTION",
    0x80000003: "BREAKPOINT",
    0xE06D7363: "C++ EXCEPTION (msvc throw)",
}
# RtlCaptureStackBackTrace's hard cap on captured frames.
_MAX_NATIVE_FRAMES = 62
# crtdefs.h _CALL_REPORTFAULT: the abort() bit that raises the fail-fast/
# Watson path INSTEAD of raise(SIGABRT); cleared so abort() reaches our
# C-level SIGABRT handler (and faulthandler's chain) on every machine.
_CALL_REPORTFAULT = 0x00000002
# Win32 unhandled-filter return: keep searching (default WER handling follows).
EXCEPTION_CONTINUE_SEARCH = 0
_SIG_DFL = 0
_SIG_IGN = 1

_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
)

# Installation state (guarded by the _is_installed idempotence flag; reset()
# exists ONLY for tests).
_is_installed = False
_sink_id: int | None = None
_log_path: Path | None = None
_hang_path: Path | None = None
_hang_fh = None  # append-binary handle into mas-hang.log (faulthandler writes the fd)
_hang_timeout: float = HANG_TIMEOUT_S
_prev_sys_excepthook = None
_prev_threading_excepthook = None
_heartbeat_timer = None  # QTimer parented to the QApplication (Task 2)

# Memory-telemetry state (Task 3): beat counter + the warn-once latches.
_beat_count = 0
_mem_latches = {"rss": False, "commit": False}

# Native-crash-logger state (quick-260909-ke1 task 2). The ctypes callback
# objects MUST stay referenced for the process lifetime (a GC'd callback = a
# wild pointer in kernel32's filter slot); reset() drops them only after
# deregistering.
_crash_logger_installed = False
_md_apis: Any = None
_md_filter_cb: Any = None
_md_sigabrt_cb: Any = None
_md_filter_prev: int | None = None
_md_sigabrt_prev: int | None = None
_native_crash_logged = False


def logs_dir(base_dir: Path | None = None) -> Path:
    """The log directory: ``base_dir/logs`` or the profile dir's ``logs`` sibling."""
    root = Path(base_dir) if base_dir is not None else Path.home() / ".manga_ai_studio"
    return root / "logs"


def _admit(record) -> bool:  # noqa: ANN001 (loguru record dict)
    """Sink filter: WARNING floor + gui-namespace DEBUG + escape extras."""
    extra = record["extra"]
    # The session separator and the heartbeat memory-telemetry INFO lines are
    # admitted below the WARNING floor (both are diagnostics-native records).
    if extra.get("session_marker") or extra.get("memory_telemetry"):
        return True
    if record["level"].no >= _WARNING_LEVEL_NO:
        return True
    name = record.get("name") or ""
    return name.startswith(_GUI_NAMESPACE)


def install(base_dir: Path | None = None, hang_timeout_s: float = HANG_TIMEOUT_S) -> Path:
    """Install the file sink + crash hooks + hang watchdog (idempotent).

    Creates ``base_dir/logs`` (default under the profile home
    ``~/.manga_ai_studio``), arms everything, writes the session separator, and
    returns the ``mas.log`` path so the entrypoint can print it to stderr.
    """
    global _is_installed, _sink_id, _log_path, _hang_path, _hang_fh, _hang_timeout
    global _prev_sys_excepthook, _prev_threading_excepthook
    global _beat_count, _mem_latches

    log_dir = logs_dir(base_dir)
    log_path = log_dir / _LOG_FILE_NAME
    if _is_installed:
        return _log_path

    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_path
    _hang_path = log_dir / _HANG_FILE_NAME
    _beat_count = 0
    _mem_latches = {"rss": False, "commit": False}

    # Warm the telemetry path FIRST (no faulthandler deadline is armed yet):
    # the cold psutil import must never run under an armed hang deadline.
    _warm_memory_telemetry()

    # Hang capture first: faulthandler writes raw from its watchdog thread into
    # a DEDICATED file (never the loguru sink's file — fd-level writes would
    # interleave with loguru's appender on Windows).
    _hang_fh = open(_hang_path, "ab", buffering=0)
    _hang_timeout = float(hang_timeout_s)
    faulthandler.enable(file=_hang_fh)
    faulthandler.dump_traceback_later(_hang_timeout, repeat=True, file=_hang_fh)

    # Crash capture: wrap (never replace-and-forget) the previous hooks.
    _prev_sys_excepthook = sys.excepthook
    sys.excepthook = _sys_excepthook
    _prev_threading_excepthook = threading.excepthook
    threading.excepthook = _threading_excepthook

    # File sink LAST so the separator below is the first file record.
    _sink_id = logger.add(
        log_path,
        rotation=_ROTATION,
        retention=_RETENTION,
        encoding="utf-8",
        enqueue=True,
        filter=_admit,
        format=_LOG_FORMAT,
    )
    _write_session_separator()
    # Native-crash text reports LAST (after the sink): its ERROR record must
    # never land in the file before the session separator does.
    install_native_crash_logger()
    _is_installed = True
    return log_path


def _write_session_separator() -> None:
    """One INFO line (session_marker-bound) with version/timestamp/platform."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    logger.bind(session_marker=True).info(
        f"=== Manga AI Studio v{__version__} session start | {now} | "
        f"{platform.platform()} | Python {platform.python_version()} ==="
    )


def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:  # noqa: ANN001
    """Log the unhandled exception, then chain the hook that was there before."""
    logger.opt(exception=(exc_type, exc_value, exc_tb)).error(
        f"Unhandled exception: {exc_type.__name__}: {exc_value}"
    )
    prev = _prev_sys_excepthook
    if prev is not None:
        prev(exc_type, exc_value, exc_tb)


def _threading_excepthook(args) -> None:  # noqa: ANN001 (threading.ExceptHookArgs)
    """Log a raised-in-thread exception, then chain the previous thread hook."""
    thread_name = getattr(args.thread, "name", None)
    logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).error(
        f"Unhandled exception in thread {thread_name!r} (threading.excepthook): "
        f"{args.exc_type.__name__}: {args.exc_value}"
    )
    prev = _prev_threading_excepthook
    if prev is not None:
        prev(args)


def cancel_hang_watchdog() -> None:
    """Disarm the ``dump_traceback_later`` watchdog (tests + heartbeat tick)."""
    faulthandler.cancel_dump_traceback_later()


# ----------------------------------------------------------- memory telemetry
# (quick-260909-ke1 task 3 — psutil is imported lazily so the module keeps a
# stdlib-only import graph; a missing/failing psutil degrades to a DEBUG line,
# never a heartbeat break).


def _env_number(name: str, default: float) -> float:
    """Env override reader: malformed values fall back to the default."""
    raw = os.environ.get(name)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _memory_thresholds() -> tuple[float, float]:
    """``(rss_warn_mb, commit_warn_pct)`` with the MAS_MEM_* env overrides."""
    return (
        _env_number(_ENV_MEM_RSS_MB, MEM_RSS_WARN_MB_DEFAULT),
        _env_number(_ENV_MEM_COMMIT_PCT, MEM_COMMIT_WARN_PCT_DEFAULT),
    )


def _memory_threshold_warnings(
    rss_mb: float,
    commit_pct: float,
    rss_warn_mb: float,
    commit_warn_pct: float,
    latches: dict[str, bool],
) -> list[str]:
    """Warn-once messages for newly-crossed thresholds; crossing latches.

    Pure function (the latching dict is passed in) so the threshold/latch
    logic is testable without psutil or the heartbeat. Each latch fires AT
    MOST once per session — a threshold is reported the first time it is
    seen crossed, never again (no spam around a hovering value).
    """
    messages: list[str] = []
    if rss_mb >= rss_warn_mb and not latches["rss"]:
        latches["rss"] = True
        messages.append(
            f"Memory threshold: process RSS {rss_mb:.0f}MB >= {rss_warn_mb:.0f}MB "
            f"(warn-once latch; if the app now dies with 'Fatal Python error: "
            f"Aborted', the abort is memory exhaustion)"
        )
    if commit_pct >= commit_warn_pct and not latches["commit"]:
        latches["commit"] = True
        messages.append(
            f"Memory threshold: system commit {commit_pct:.1f}% >= "
            f"{commit_warn_pct:.0f}% (warn-once latch; allocation failures "
            f"become likely near the commit limit)"
        )
    return messages


def _sample_and_log_memory() -> None:
    """One telemetry sample: an INFO line + latched threshold WARNINGs.

    Called from a telemetry thread (see :func:`_launch_memory_sample`) or
    directly in tests — NEVER raises: a missing or failing psutil only costs
    a DEBUG line (filtered from the file sink).
    """
    try:
        import psutil

        rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        commit_pct = float(psutil.swap_memory().percent)
    except Exception as exc:  # noqa: BLE001 — telemetry must never break the heartbeat
        logger.debug(f"memory telemetry unavailable: {exc}")
        return
    rss_warn_mb, commit_warn_pct = _memory_thresholds()
    for message in _memory_threshold_warnings(
        rss_mb, commit_pct, rss_warn_mb, commit_warn_pct, _mem_latches
    ):
        logger.warning(message)
    logger.bind(memory_telemetry=True).info(
        f"memory: rss={rss_mb:.0f}MB commit={commit_pct:.1f}%"
    )


def _launch_memory_sample() -> None:
    """Run one telemetry sample OFF the event-loop thread.

    A daemon thread keeps the tick O(microseconds); samples are ~1/min in
    production, so no overlap guard is needed. (The first-call psutil costs
    are paid up front by :func:`_warm_memory_telemetry` at install time.)
    """
    try:
        threading.Thread(
            target=_sample_and_log_memory, name="mas-mem-telemetry", daemon=True
        ).start()
    except Exception:  # noqa: BLE001 — telemetry must never break the heartbeat
        pass


def _warm_memory_telemetry() -> None:
    """Pay the psutil first-call costs BEFORE the hang watchdog is armed.

    The cold ``import psutil`` can hold the GIL for hundreds of milliseconds
    in a heavy process; running it under an armed hang deadline (or inside a
    live tick) can starve the timer dispatch long enough to fire a spurious
    watchdog dump. install() runs this BEFORE ``dump_traceback_later`` — no
    deadline is outstanding, so the cost is invisible. Failure is fine: the
    telemetry then degrades to a DEBUG line per sample.
    """
    try:
        import psutil

        psutil.Process().memory_info().rss
        psutil.swap_memory().percent
    except Exception:  # noqa: BLE001 — telemetry stays optional
        pass


# ----------------------------------------------------- native crash reporting
# (quick-260909-ke1 task 2 — see the module docstring for the design; the
# whole section is Windows-only, ctypes-lazy, and best-effort by contract).


class _WindowsApis(NamedTuple):
    """The ctypes entry points + callback factories for the crash-logger path."""

    sigabrt: int
    filter_func: Any
    sigabrt_func: Any
    set_unhandled_exception_filter: Any
    capture_stack_back_trace: Any
    get_module_handle_ex_w: Any
    get_module_base_name_w: Any
    get_module_file_name_ex_w: Any
    get_module_information: Any
    get_current_process: Any
    get_current_process_id: Any
    get_current_thread_id: Any
    signal: Any
    set_abort_behavior: Any  # None when the ucrtbase export is absent


def _load_windows_apis() -> _WindowsApis:
    """Resolve the kernel32/ntdll/psapi/ucrtbase entry points for the logger.

    Raises OSError when anything required is missing (non-Windows, absent
    export) so callers degrade gracefully. Optional exports (e.g.
    ``_set_abort_behavior``) come through as None instead of raising.
    """
    if sys.platform != "win32":
        raise OSError("native crash reporting requires Windows")
    import ctypes
    from signal import SIGABRT

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    ucrtbase = ctypes.CDLL("ucrtbase.dll")

    def _resolve(lib: Any, name: str, restype: Any, argtypes: list) -> Any:
        try:
            fn = getattr(lib, name)
        except AttributeError as exc:  # pragma: no cover - depends on OS build
            raise OSError(f"{name} export not found") from exc
        fn.restype = restype
        fn.argtypes = argtypes
        return fn

    c = ctypes
    set_abort_behavior = getattr(ucrtbase, "_set_abort_behavior", None)
    if set_abort_behavior is not None:
        set_abort_behavior.restype = c.c_uint32
        set_abort_behavior.argtypes = [c.c_uint32, c.c_uint32]

    return _WindowsApis(
        sigabrt=int(SIGABRT),
        # x64 has a single calling convention; on the rare 32-bit build the
        # UCRT handler is cdecl and WINFUNCTYPE(stdcall) would be wrong — this
        # app ships x64 only, and the handlers are guarded regardless.
        filter_func=c.WINFUNCTYPE(c.c_long, c.c_void_p),
        sigabrt_func=c.WINFUNCTYPE(None, c.c_int),
        set_unhandled_exception_filter=_resolve(
            kernel32, "SetUnhandledExceptionFilter", c.c_void_p, [c.c_void_p]
        ),
        # The native stack of the faulting thread (the filter/handler runs ON
        # it). Frames are module-resolved for the report; the raw addresses
        # are printed when resolution fails.
        capture_stack_back_trace=_resolve(
            ntdll,
            "RtlCaptureStackBackTrace",
            c.c_uint16,  # USHORT frames captured
            [c.c_uint32, c.c_uint32, c.c_void_p, c.c_void_p],
        ),
        # GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS (0x4) |
        # GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT (0x2).
        # GetModuleHandleExW is a kernel32 export (NOT psapi — only the
        # module name/info helpers live there).
        get_module_handle_ex_w=_resolve(
            kernel32, "GetModuleHandleExW", c.c_int, [c.c_uint32, c.c_void_p, c.c_void_p]
        ),
        get_module_base_name_w=_resolve(
            psapi, "GetModuleBaseNameW", c.c_uint32, [c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint32]
        ),
        get_module_file_name_ex_w=_resolve(
            psapi, "GetModuleFileNameExW", c.c_uint32, [c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint32]
        ),
        get_module_information=_resolve(
            psapi, "GetModuleInformation", c.c_int, [c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint32]
        ),
        get_current_process=_resolve(kernel32, "GetCurrentProcess", c.c_void_p, []),
        get_current_process_id=_resolve(kernel32, "GetCurrentProcessId", c.c_uint32, []),
        get_current_thread_id=_resolve(kernel32, "GetCurrentThreadId", c.c_uint32, []),
        signal=_resolve(ucrtbase, "signal", c.c_void_p, [c.c_int, c.c_void_p]),
        set_abort_behavior=set_abort_behavior,
    )


def _resolve_frame(apis: Any, address: int) -> tuple[str, str, Any]:
    """Resolve one stack address to ``(label, module-name-lower, module-handle)``.

    ``label`` is the human-readable ``module!+0xoffset`` form (raw hex when the
    address is unmapped); ``module-handle`` feeds the version lookup for the
    faulting frame (None when unresolved).
    """
    import ctypes

    hmod = ctypes.c_void_p(0)
    # 0x4 GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
    # 0x2 GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT — never load/retain.
    if not apis.get_module_handle_ex_w(0x6, ctypes.c_void_p(address), ctypes.byref(hmod)):
        return f"0x{address:016X}", "", None

    class _MODULEINFO(ctypes.Structure):
        _fields_ = [
            ("lpBaseOfDll", ctypes.c_void_p),
            ("SizeOfImage", ctypes.c_uint32),
            ("EntryPoint", ctypes.c_void_p),
        ]

    info = _MODULEINFO()
    name_buf = ctypes.create_unicode_buffer(260)
    if not apis.get_module_information(
        apis.get_current_process(), hmod, ctypes.byref(info), ctypes.sizeof(info)
    ) or not apis.get_module_base_name_w(
        apis.get_current_process(), hmod, ctypes.byref(name_buf), 260
    ):
        return f"0x{address:016X}", "", None
    base = info.lpBaseOfDll or 0
    return f"{name_buf.value}!+0x{address - base:08X}", name_buf.value.lower(), hmod


def _native_stack(apis: Any) -> list[tuple[str, str, Any]]:
    """The calling thread's native stack as ``(label, module, handle)`` tuples.

    The filter/SIGABRT handler runs ON the faulting thread, so a capture from
    here IS the faulting thread's stack (a few dispatcher frames from the
    exception path sit between our handler and the faulting frame).
    """
    import ctypes

    buf = (ctypes.c_uint64 * _MAX_NATIVE_FRAMES)()
    captured = apis.capture_stack_back_trace(
        0, _MAX_NATIVE_FRAMES, ctypes.cast(buf, ctypes.c_void_p), None
    )
    frames = []
    for addr in buf[: min(int(captured), _MAX_NATIVE_FRAMES)]:
        if not addr:
            break
        frames.append(_resolve_frame(apis, addr))
    return frames


def _module_path(apis: Any, hmod: Any) -> str:
    """The full on-disk path of a loaded module; '' when unresolvable."""
    import ctypes

    buf = ctypes.create_unicode_buffer(520)
    if hmod is None or not apis.get_module_file_name_ex_w(
        apis.get_current_process(), hmod, ctypes.byref(buf), 520
    ):
        return ""
    return buf.value


def _module_file_version(path: str) -> str:
    """The module's VS_FIXEDFILEINFO FileVersion ("6.10.1" style); '' if absent."""
    import ctypes

    version = ctypes.WinDLL("version", use_last_error=True)
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, data):
        return ""
    val = ctypes.c_void_p()
    val_len = ctypes.c_uint()
    if not version.VerQueryValueW(
        data, "\\", ctypes.byref(val), ctypes.byref(val_len)
    ) or not val_len.value:
        return ""

    class _FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32),
            ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32),
            ("dwFileVersionLS", ctypes.c_uint32),
        ]

    ffi = ctypes.cast(val, ctypes.POINTER(_FIXEDFILEINFO)).contents
    ms, ls = ffi.dwFileVersionMS, ffi.dwFileVersionLS
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


# Modules that are ALWAYS this reporter's own callback trampoline when they
# lead a captured stack (the ctypes callback enters through libffi; python
# frames follow), plus the OS raise/dispatch machinery that sits between the
# trampoline and the actual faulting frame in the UEF path.
_REPORTER_NOISE = {"libffi-8.dll", "_ctypes.pyd", "python314.dll", "python.exe"}
_DISPATCH_RUN = {"kernelbase.dll", "ntdll.dll"}


def _native_crash_report(exception_pointers: int | None) -> str:
    """Build the text crash report for mas.log (a few KB, never a dump file).

    ``exception_pointers`` is the raw LPEXCEPTION_POINTERS from the filter
    (None for the SIGABRT path). The report names the exception code, resolves
    the faulting frame to ``module!+0xoffset`` (version-stamped), and lists the
    native stack of the faulting thread with the reporter's own trampoline and
    the OS dispatch run elided so the printed stack leads with the crash site.
    Raises only on environment problems (non-Windows, missing exports) —
    crash-path callers guard it.
    """
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

    apis = _load_windows_apis()
    fault_hmod: Any = None
    if exception_pointers:
        pointers = ctypes.cast(
            exception_pointers, ctypes.POINTER(_EXCEPTION_POINTERS)
        ).contents
        rec = pointers.ExceptionRecord.contents
        code = rec.ExceptionCode & 0xFFFFFFFF
        name = _CRASH_CODE_NAMES.get(code, "UNKNOWN")
        fault_addr = rec.ExceptionAddress
        if not fault_addr and pointers.ContextRecord:
            # x64 CONTEXT.Rip sits at a fixed 0xF8 into the context record
            # (documented layout) — view the record as uint64s and take [31].
            fault_addr = ctypes.cast(
                pointers.ContextRecord, ctypes.POINTER(ctypes.c_uint64 * 32)
            ).contents[31]
        if fault_addr:
            fault_label, _, fault_hmod = _resolve_frame(apis, fault_addr)
            where = fault_label
        else:
            where = "<no faulting address>"
        header = (
            f"Native crash: exception 0x{code:08X} ({name}) at {where} "
            f"on thread {apis.get_current_thread_id()}"
        )
        if code == 0xC0000005 and rec.NumberParameters >= 2:
            access = {0: "read from", 1: "write to", 8: "DEP execute at"}.get(
                rec.ExceptionInformation[0], "access"
            )
            header += f" — {access} 0x{rec.ExceptionInformation[1]:016X}"
    else:
        header = f"Native abort (SIGABRT) on thread {apis.get_current_thread_id()}"

    frames = _native_stack(apis)
    # Trim THIS reporter's trampoline (a ctypes callback always enters through
    # libffi → _ctypes → python314), then collapse the OS exception-dispatch
    # run (KERNELBASE/ntdll) — but only when non-dispatch frames follow, so a
    # crash INSIDE the dispatch machinery is never hidden.
    start = 0
    while start < len(frames) and frames[start][1] in _REPORTER_NOISE:
        start += 1
    end = start
    while end < len(frames) and frames[end][1] in _DISPATCH_RUN:
        end += 1
    if end < len(frames):
        collapsed, body = end - start, frames[end:]
    else:
        collapsed, body = 0, frames[start:]

    lines = [header, "Native stack (innermost first):"]
    if collapsed:
        lines.append(f"  … {collapsed} reporter/exception-dispatch frames elided …")
    for i, (label, _, _) in enumerate(body):
        lines.append(f"  {i}: {label}")
    if not body and not collapsed:
        lines.append("  <no native frames captured>")

    # Version-stamp the crash site's module: the offset is only actionable
    # against the exact build (e.g. mapping Qt6Widgets offsets needs the Qt
    # version the DLL was built as).
    focus_hmod = body[0][2] if body else fault_hmod
    if focus_hmod is not None:
        path = _module_path(apis, focus_hmod)
        if path:
            version = _module_file_version(path)
            lines.append(
                f"Faulting module: {path}"
                + (f" (file version {version})" if version else "")
            )
    return "\n".join(lines)


def _log_native_crash(exception_pointers: int | None) -> None:
    """Log the one native-crash report per session into mas.log (ERROR)."""
    global _native_crash_logged
    if _native_crash_logged:
        return
    try:
        report = _native_crash_report(exception_pointers)
    except Exception:  # noqa: BLE001 — the crash path must never raise
        report = "Native crash: report generation failed"
    logger.error(report)
    _native_crash_logged = True
    # Bound-flush the report: the enqueue writer thread may be the dying
    # thread itself, so complete() runs in a helper thread capped at 2s — the
    # mas.log record is the load-bearing artifact either way.
    try:
        flusher = threading.Thread(target=logger.complete, daemon=True)
        flusher.start()
        flusher.join(2.0)
    except Exception:  # noqa: BLE001 — best-effort to the very end
        pass


def _unhandled_exception_filter(exception_pointers: int | None) -> int:
    """The ctypes top-level unhandled-exception filter (SEH crash path)."""
    try:
        _log_native_crash(exception_pointers)
    except Exception:  # noqa: BLE001 — the filter must never raise
        pass
    prev = _md_filter_prev
    if prev:
        try:
            apis = _md_apis
            if apis is not None:
                return int(apis.filter_func(prev)(exception_pointers))
        except Exception:  # noqa: BLE001
            pass
    return EXCEPTION_CONTINUE_SEARCH


def _abort_sigabrt_handler(signum: int) -> None:
    """The ctypes C-LEVEL SIGABRT handler (the observed abort() path).

    Logs the native crash report, then chains to the PREVIOUS C handler —
    usually faulthandler's, preserving the all-thread Python-stack dump in
    mas-hang.log. Our handler is uninstalled BEFORE the chain so any
    re-raise inside the previous handler (faulthandler restores + re-raises)
    cannot recurse into us.
    """
    try:
        _log_native_crash(None)
    except Exception:  # noqa: BLE001 — never raise out of a C signal handler
        pass
    apis = _md_apis
    prev = _md_sigabrt_prev
    if apis is None or prev in (None, _SIG_DFL, _SIG_IGN):
        return  # nothing to chain; abort()'s own _exit(3) proceeds
    try:
        apis.signal(apis.sigabrt, prev)
    except Exception:  # noqa: BLE001
        pass
    try:
        apis.sigabrt_func(prev)(signum)
    except Exception:  # noqa: BLE001
        pass


def install_native_crash_logger() -> None:
    """Install the UEF + SIGABRT text-report capture (Windows-only, idempotent).

    Native crashes log a TEXT report into mas.log (exception code, faulting
    ``module!+0xoffset``, native stack) — no dump files. Any failure
    (non-Windows, missing exports, ...) is swallowed with a DEBUG line: the
    app keeps running exactly as before, just without crash reporting.
    """
    global _crash_logger_installed, _md_apis
    global _md_filter_cb, _md_sigabrt_cb, _md_filter_prev, _md_sigabrt_prev
    if _crash_logger_installed:
        return
    try:
        import ctypes

        apis = _load_windows_apis()
        # abort(): prefer raise(SIGABRT) over the fail-fast/Watson detour so
        # the handler chain below always sees the abort.
        if apis.set_abort_behavior is not None:
            apis.set_abort_behavior(0, _CALL_REPORTFAULT)
        filter_cb = apis.filter_func(_unhandled_exception_filter)
        prev_filter = apis.set_unhandled_exception_filter(
            ctypes.cast(filter_cb, ctypes.c_void_p).value
        )
        sigabrt_cb = apis.sigabrt_func(_abort_sigabrt_handler)
        prev_sigabrt = apis.signal(
            apis.sigabrt, ctypes.cast(sigabrt_cb, ctypes.c_void_p).value
        )
        # Commit the module state only after EVERY registration succeeded.
        _md_apis = apis
        _md_filter_cb = filter_cb  # keep-alive: a GC'd callback = wild pointer
        _md_sigabrt_cb = sigabrt_cb
        _md_filter_prev = prev_filter
        _md_sigabrt_prev = prev_sigabrt
        _crash_logger_installed = True
        logger.debug("native crash logger installed (reports go into mas.log)")
    except Exception as exc:  # noqa: BLE001 — diagnostics must never break the app
        logger.debug(f"native crash logger unavailable (continuing without): {exc}")


# ----------------------------------------------------------------- Qt layer
# (lazily imported — module scope stays PySide6-free)
_prev_qt_handler = None


def install_qt_message_handler() -> None:
    """Route Qt's own messages (qWarning/qCritical, ...) into loguru.

    Maps QtMsgType -> loguru levels (QtDebugMsg->DEBUG, QtInfoMsg->INFO,
    QtWarningMsg->WARNING, QtCriticalMsg->ERROR, QtFatalMsg->CRITICAL) and
    includes the message context (file/line/function) when present. The
    previous handler is remembered so :func:`reset` can restore it; a fatal
    message is logged at CRITICAL then handed to the previous handler (the
    default one aborts, preserving Qt's fatal semantics).
    """
    global _prev_qt_handler
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    level_map = {
        QtMsgType.QtDebugMsg: "DEBUG",
        QtMsgType.QtInfoMsg: "INFO",
        QtMsgType.QtWarningMsg: "WARNING",
        QtMsgType.QtCriticalMsg: "ERROR",
        QtMsgType.QtFatalMsg: "CRITICAL",
    }

    def _on_qt_message(mode, context, message) -> None:  # noqa: ANN001 (Qt API)
        level = level_map.get(mode, "WARNING")
        where = ""
        if context is not None and getattr(context, "file", ""):
            where = f" [{context.file}:{context.line} {context.function}]"
        log = getattr(logger, level.lower())
        log(f"[Qt] {message}{where}")
        if mode == QtMsgType.QtFatalMsg and _prev_qt_handler is not None:
            _prev_qt_handler(mode, context, message)

    _prev_qt_handler = qInstallMessageHandler(_on_qt_message)


def heartbeat(app, interval_s: float = 15.0) -> None:  # noqa: ANN001 (QApplication)
    """Arm the event-loop heartbeat that keeps the hang watchdog disarmed.

    A QTimer PARENTED TO THE QApplication (garbage-safe) ticks every
    ``interval_s``; each tick cancels the outstanding ``dump_traceback_later``
    deadline and re-arms it — a live loop resets the deadline forever, a wedged
    loop stops ticking and the all-thread stack dump fires ~``HANG_TIMEOUT_S``
    in (the watchdog thread needs no cooperation from the frozen main thread).
    Expected long operations run on the Worker thread, so the main loop keeps
    ticking through them.
    """
    from PySide6.QtCore import QTimer

    global _heartbeat_timer
    stop_heartbeat()
    if _hang_fh is None:
        return  # install() never ran — nothing to keep alive
    timer = QTimer(app)
    timer.setInterval(max(1, int(interval_s * 1000)))
    timer.timeout.connect(_heartbeat_tick)
    timer.start()
    _heartbeat_timer = timer
    # t0 baseline sample (async — see _launch_memory_sample): warms the psutil
    # path out of any tick and anchors the session's memory timeline at zero.
    _launch_memory_sample()


def _heartbeat_tick() -> None:
    """The heartbeat slot: reset the watchdog deadline; sample memory."""
    global _beat_count
    if _hang_fh is None:
        return
    faulthandler.cancel_dump_traceback_later()
    faulthandler.dump_traceback_later(_hang_timeout, repeat=True, file=_hang_fh)
    # quick-260909-ke1 task 3: one INFO memory sample + latched threshold
    # WARNINGs every N-th beat (~once a minute at the 15s default), sampled
    # off the event-loop thread so the tick itself never blocks.
    _beat_count += 1
    if _beat_count % HEARTBEAT_TELEMETRY_EVERY_N == 0:
        _launch_memory_sample()


def stop_heartbeat() -> None:
    """Stop the heartbeat timer (tests, and reset() teardown)."""
    global _heartbeat_timer
    timer = _heartbeat_timer
    if timer is not None:
        try:
            timer.stop()
            timer.timeout.disconnect(_heartbeat_tick)
        except RuntimeError:
            pass  # the underlying C++ QTimer may already be gone at teardown
        _heartbeat_timer = None


def reset() -> None:
    """Undo everything :func:`install` did — tests only.

    Safe to call when nothing is installed (the autouse teardown relies on it).
    """
    global _is_installed, _sink_id, _log_path, _hang_path, _hang_fh
    global _prev_sys_excepthook, _prev_threading_excepthook, _prev_qt_handler
    global _crash_logger_installed, _md_apis
    global _md_filter_cb, _md_sigabrt_cb, _md_filter_prev, _md_sigabrt_prev
    global _native_crash_logged, _beat_count, _mem_latches

    stop_heartbeat()
    faulthandler.cancel_dump_traceback_later()
    if _crash_logger_installed:
        apis, filter_prev, sigabrt_prev = _md_apis, _md_filter_prev, _md_sigabrt_prev
        try:
            if apis is not None:
                apis.set_unhandled_exception_filter(filter_prev)
                if sigabrt_prev in (None, _SIG_DFL, _SIG_IGN):
                    apis.signal(apis.sigabrt, _SIG_DFL)
                else:
                    apis.signal(apis.sigabrt, sigabrt_prev)
        except Exception:  # noqa: BLE001 — a diagnostics restore must never raise
            pass
        _md_apis = None
        _md_filter_cb = None  # drop the ctypes callbacks ONLY after deregistering
        _md_sigabrt_cb = None
        _md_filter_prev = None
        _md_sigabrt_prev = None
        _crash_logger_installed = False
    # The one-report-per-session latch clears UNCONDITIONALLY: the crash
    # logger is still settable by tests that drive the filter/handler
    # directly — a latched session must never survive a reset().
    _native_crash_logged = False
    _beat_count = 0
    _mem_latches = {"rss": False, "commit": False}
    if _prev_qt_handler is not None:
        try:
            from PySide6.QtCore import qInstallMessageHandler

            qInstallMessageHandler(_prev_qt_handler)
        except Exception:  # noqa: BLE001 — a diagnostics restore must never raise
            pass
        _prev_qt_handler = None
    if _sink_id is not None:
        try:
            logger.remove(_sink_id)
        except ValueError:
            pass  # already gone
        _sink_id = None
    if _prev_sys_excepthook is not None:
        sys.excepthook = _prev_sys_excepthook
        _prev_sys_excepthook = None
    if _prev_threading_excepthook is not None:
        threading.excepthook = _prev_threading_excepthook
        _prev_threading_excepthook = None
    if _hang_fh is not None:
        # Re-enable faulthandler on the default stream before dropping our fd
        # (pytest's faulthandler plugin had it enabled on stderr).
        try:
            faulthandler.enable(file=sys.stderr)
        except Exception:  # noqa: BLE001 — a diagnostics restore must never raise
            pass
        _hang_fh.close()
        _hang_fh = None
    _is_installed = False
    _log_path = None
    _hang_path = None

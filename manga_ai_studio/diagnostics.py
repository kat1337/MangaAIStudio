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

Module scope imports ONLY stdlib + loguru (PySide6 stays out so the core
battery and future core-side callers never need Qt); the Qt-touching helpers
(:func:`heartbeat`, :func:`install_qt_message_handler`) import lazily.

The platform truth for the watchdog dump header is ``Timeout (...)!`` followed
by ``Thread 0x... (most recent call first):`` lines (measured on this
Windows/CPython 3.14 box — the "Current thread" label only appears when the
crashing thread dumps itself).
"""

from __future__ import annotations

import faulthandler
import platform
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from manga_ai_studio import __version__

__all__ = [
    "HANG_TIMEOUT_S",
    "install",
    "reset",
    "cancel_hang_watchdog",
    "heartbeat",
    "stop_heartbeat",
    "install_qt_message_handler",
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


def logs_dir(base_dir: Path | None = None) -> Path:
    """The log directory: ``base_dir/logs`` or the profile dir's ``logs`` sibling."""
    root = Path(base_dir) if base_dir is not None else Path.home() / ".manga_ai_studio"
    return root / "logs"


def _admit(record) -> bool:  # noqa: ANN001 (loguru record dict)
    """Sink filter: WARNING floor + gui-namespace DEBUG + session_marker escape."""
    if record["extra"].get("session_marker"):
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

    log_dir = logs_dir(base_dir)
    log_path = log_dir / _LOG_FILE_NAME
    if _is_installed:
        return _log_path

    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_path
    _hang_path = log_dir / _HANG_FILE_NAME

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


def reset() -> None:
    """Undo everything :func:`install` did — tests only.

    Safe to call when nothing is installed (the autouse teardown relies on it).
    """
    global _is_installed, _sink_id, _log_path, _hang_path, _hang_fh
    global _prev_sys_excepthook, _prev_threading_excepthook

    faulthandler.cancel_dump_traceback_later()
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

"""Qt integration diagnostics tests (quick-260909-ke1 Task 2).

Mirrors the ``tests/test_gui_boxes.py`` header (``pytest.importorskip`` +
``qtbot`` fixture + ``@pytest.mark.gui``). Proves, on the INSTALLED PySide6
6.10 (never by trusting a changelog):

- Qt's own messages (qWarning/qCritical) land in mas.log at the mapped level
  via ``qInstallMessageHandler``;
- an unhandled exception raised inside a slot scheduled with
  ``QTimer.singleShot(0, ...)`` lands in mas.log as a full traceback via
  ``sys.excepthook`` (the slot->excepthook route measured on this version);
- the heartbeat QTimer provably suppresses watchdog dumps on a live loop and
  permits them once the loop stops ticking (deterministic short-timeout
  mechanics — NEVER a wall-clock "app freeze" wait).

The slot-exception test carries ``@pytest.mark.qt_no_exception_capture``:
pytest-qt's automatic capture replaces ``sys.excepthook`` per-test and would
re-fail the test at the end for the very exception we are asserting was
LOGGED (pytest-qt plugin.py ``fail_if_exceptions_occurred``); the diagnostics
hook IS the system excepthook under test here.

All install() calls target a per-test tmp dir and ``reset()`` runs in
teardown, so no sink/hook/watchdog leaks across the suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from loguru import logger  # noqa: E402
from PySide6.QtCore import QTimer, qCritical, qWarning  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from manga_ai_studio import diagnostics  # noqa: E402


# --------------------------------------------------------------------- infra
@pytest.fixture(autouse=True)
def _diag_cleanup():
    """Guarantee sinks/hooks/handlers/watchdog never leak across tests."""
    yield
    diagnostics.reset()


@pytest.fixture()
def diag(tmp_path: Path) -> dict[str, Path]:
    """A diagnostics installation rooted at the per-test tmp dir (0.5s hang)."""
    log = diagnostics.install(tmp_path, hang_timeout_s=0.5)
    return {
        "log": log,
        "hang": tmp_path / "logs" / "mas-hang.log",
    }


def _read_log(path: Path) -> str:
    logger.complete()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------- Qt message routing
@pytest.mark.gui
def test_qt_warning_lands_in_mas_log(diag) -> None:
    """A qWarning lands in mas.log at WARNING carrying the message text."""
    diagnostics.install_qt_message_handler()
    qWarning("ke1 qt warning probe")
    text = _read_log(diag["log"])
    line = next(ln for ln in text.splitlines() if "ke1 qt warning probe" in ln)
    assert "| WARNING" in line


@pytest.mark.gui
def test_qt_critical_lands_in_mas_log_as_error(diag) -> None:
    """A qCritical lands in mas.log at ERROR (QtCriticalMsg mapping)."""
    diagnostics.install_qt_message_handler()
    qCritical("ke1 qt critical probe")
    text = _read_log(diag["log"])
    line = next(ln for ln in text.splitlines() if "ke1 qt critical probe" in ln)
    assert "| ERROR" in line


# ------------------------------------------------------- slot-exception proof
@pytest.mark.gui
@pytest.mark.qt_no_exception_capture
def test_slot_exception_traceback_lands_in_mas_log(qtbot, diag) -> None:
    """A slot raising RuntimeError is captured by sys.excepthook into mas.log.

    Proves the PySide6 6.10 slot->excepthook route ON THE INSTALLED VERSION:
    the traceback (message + exception type) must appear in the file, and the
    event loop must survive (the app keeps running after a slot error).
    """
    ran: list[int] = []

    def boom() -> None:
        ran.append(1)
        raise RuntimeError("ke1 slot boom probe")

    QTimer.singleShot(0, boom)
    qtbot.wait(300)

    assert ran == [1]
    text = _read_log(diag["log"])
    assert "ke1 slot boom probe" in text
    assert "RuntimeError" in text


# ----------------------------------------------------------------- heartbeat
@pytest.mark.gui
def test_heartbeat_suppresses_dumps_on_live_loop_then_permits(qtbot, diag) -> None:
    """A ticking heartbeat re-arms the deadline forever; stopping it lets the dump fire."""
    app = QApplication.instance()
    assert app is not None  # pytest-qt session qapp
    diagnostics.heartbeat(app, interval_s=0.05)

    # A live loop: ~1s of pumping with a 0.5s deadline re-armed every 50ms
    # must produce NO dump in mas-hang.log.
    qtbot.wait(1000)
    assert "Timeout" not in _read_log(diag["hang"])

    # Stop the heartbeat: the outstanding 0.5s deadline passes and the dump fires.
    diagnostics.stop_heartbeat()
    deadline_hits = False
    for _ in range(40):  # poll up to ~2s for the deterministic 0.5s deadline
        qtbot.wait(50)
        if "Timeout" in _read_log(diag["hang"]):
            deadline_hits = True
            break
    assert deadline_hits, "watchdog dump never appeared after stopping the heartbeat"


# -------------------------------------------------------------- __main__ wiring
@pytest.mark.gui
def test_main_wires_diagnostics_in_documented_order() -> None:
    """main(): install() before create_app; handler + heartbeat after; path to stderr."""
    import manga_ai_studio

    src = (
        Path(manga_ai_studio.__file__).parent / "__main__.py"
    ).read_text(encoding="utf-8")
    assert "import diagnostics" in src or "from manga_ai_studio import diagnostics" in src
    idx_install = src.index("diagnostics.install()")
    idx_create = src.index("create_app(")
    idx_qt = src.index("install_qt_message_handler")
    idx_hb = src.index("heartbeat(")
    idx_print = src.index("[manga-ai-studio] log file:")
    assert idx_install < idx_create, "install() must run BEFORE create_app"
    assert idx_create < idx_qt, "Qt message handler installed after create_app"
    assert idx_qt < idx_hb, "heartbeat armed after the handler"
    assert idx_hb < idx_print, "log path printed after the heartbeat is armed"
    assert "file=sys.stderr" in src
    # Minidump capture + its stderr note are DISABLED (multi-GB .dmp files were
    # filling users' disks): no ACTIVE (non-comment) line may reference them.
    # If you re-enable diagnostics.install_minidump_handler, restore the note
    # AND flip this pin back to assert the user can find the dumps.
    active_dmp_lines = [
        line
        for line in src.splitlines()
        if (".dmp" in line or "minidump" in line) and not line.lstrip().startswith("#")
    ]
    assert active_dmp_lines == [], (
        "__main__.py references minidumps outside a comment but the capture "
        f"is disabled: {active_dmp_lines}"
    )

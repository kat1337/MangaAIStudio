"""Worker thread infrastructure — vendored from PanelCleaner (GPL v3, D-12).

Source: ``pcleaner/gui/worker_thread.py`` (165 lines), vendored near-verbatim.
PanelCleaner's worker is more robust than MangaCleaner_GPU's inline
``AIWorker(QObject)`` pattern: it is ``QRunnable``-based (pooled), carries a
typed ``WorkerError`` (exception_type, value, traceback, args, kwargs),
supports abort via a ``SharableFlag``, and auto-injects ``progress_callback``
and ``abort_flag`` into the task function's kwargs.

Original attribution: "Worker Threads loosely based on QRunnable by Martin
Fitzpatrick, https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/
(MIT)". PanelCleaner wrapped that pattern with ``WorkerError``/``Abort``/
``SharableFlag`` under GPL v3.

Thread-safety contract (RESEARCH Pitfall 3, T-01-07): the task function runs
on a QThreadPool thread and MUST touch only numpy/Python + emit signals. ALL
Qt mutation happens in the main-thread signal handlers connected to
``WorkerSignals``. The detect/inpaint calls return plain numpy arrays, never
QImage/QPixmap.
"""

import sys
from dataclasses import dataclass
from types import TracebackType
from typing import Callable

from PySide6.QtCore import QRunnable, Signal, Slot, QObject


@dataclass(frozen=True, slots=True)
class WorkerError:
    """Typed error payload emitted on worker failure.

    Carries the full exception info (type, value, traceback) plus the args/
    kwargs passed to the task function, so the main-thread error handler can
    log the traceback (T-01-08) while showing only user-friendly copy in the
    QMessageBox.
    """

    exception_type: type[BaseException]
    value: BaseException
    traceback: TracebackType
    args: tuple | None = None
    kwargs: dict | None = None

    def __str__(self) -> str:
        return f"{self.exception_type}: {self.traceback}\n{self.value}"


class WorkerSignals(QObject):
    """Signals available from a running worker thread.

    - ``finished``: the (args, kwargs) passed to the worker when started.
    - ``error``: a ``WorkerError`` instance.
    - ``result``: the return value of the task function (object).
    - ``progress``: anything indicating current state (e.g. (percent, message)).
    - ``aborted``: the (args, kwargs) when the worker was aborted.
    """

    finished = Signal(tuple)
    error = Signal(WorkerError)
    result = Signal(object)
    progress = Signal(object)
    aborted = Signal(tuple)


class SharableFlag:
    """A simple thread-shared boolean flag for abort signaling."""

    def __init__(self, initial_value: bool = False) -> None:
        self._flag = initial_value

    def get(self) -> bool:
        return self._flag

    def set(self, value: bool) -> None:
        self._flag = value


class Abort(Exception):
    """Exception raised to abort a worker."""

    pass


class Worker(QRunnable):
    """Worker thread — wraps a callable for execution on a QThreadPool.

    Inherits from ``QRunnable`` to handle worker thread setup, signals, and
    wrap-up. DO NOT put ``@Slot()`` decorators on the functions you connect to
    the signals — that causes segfaults.

    :param fn: The function callback to run on this worker thread. Supplied
        args and kwargs are passed through to it.
    :param args: Arguments to pass to the callback function.
    :param no_progress_callback: If True, ``progress_callback`` is NOT injected
        into kwargs.
    :param abort_signal: An optional signal that, when emitted, sets the abort
        flag (the task function checks ``abort_flag.get()`` and raises
        :class:`Abort`).
    :param kwargs: Keywords to pass to the callback function.

    Auto-injection: unless ``no_progress_callback=True``, the constructor
    injects ``progress_callback=self.signals.progress`` into kwargs. If
    ``abort_signal`` is provided, it also injects ``abort_flag=self.aborted``.
    The task function contract is therefore::

        def fn(..., progress_callback=None, abort_flag=None)
    """

    aborted: SharableFlag

    def __init__(
        self,
        fn: Callable,
        *args,
        no_progress_callback: bool = False,
        abort_signal: Signal | None = None,
        **kwargs,
    ):
        QRunnable.__init__(self)

        # Store constructor arguments (re-used for processing).
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # If the abort signal is received, the abort flag is set to true.
        # The worker process must abort itself when the flag is true.
        self.aborted = SharableFlag(False)

        # Add the progress callback to kwargs.
        if not no_progress_callback:
            self.kwargs["progress_callback"] = self.signals.progress

        # If an abort signal is provided, provide the sharable flag to the worker.
        if abort_signal is not None:
            self.kwargs["abort_flag"] = self.aborted
            abort_signal.connect(self.abort)

    @Slot()
    def run(self) -> None:
        """Initialise the runner function with passed args, kwargs.

        The try/except/finally structure (PanelCleaner worker_thread.py:126-161):
        ``Abort`` -> ``aborted`` signal; any other ``Exception`` -> ``error``
        signal carrying a ``WorkerError``; success -> ``result`` signal;
        always -> ``finished`` signal. The outer ``RuntimeError`` catch
        handles signals deleted during shutdown (window closed mid-task).
        """
        try:
            try:
                result = self.fn(*self.args, **self.kwargs)
            except Abort:
                self.signals.aborted.emit((self.args, self.kwargs))
            except Exception:
                exception_type, value, traceback = sys.exc_info()
                self.signals.error.emit(
                    WorkerError(exception_type, value, traceback, self.args, self.kwargs)
                )
            else:
                self.signals.result.emit(result)
            finally:
                self.signals.finished.emit((self.args, self.kwargs))
        except RuntimeError:
            # The signals were deleted, so we can't emit them. This is fine
            # during shutdown — just don't emit anything.
            pass

    @Slot()
    def abort(self) -> None:
        """Set the abort flag (the task function polls it and raises Abort)."""
        self.aborted.set(True)

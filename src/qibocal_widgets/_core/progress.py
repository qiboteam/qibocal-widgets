"""Events of the acquisitions, reported while they run.

Qibolab logs an estimate of the duration of every execution on the platform,
and drivers of each of its batches (e.g. Qblox, accounting for its overheads).
They are captured where the acquisition runs: in the current thread for local
runners, in the worker for remote ones, which streams them back while the job
runs, with the start and end of the acquisition (see :mod:`.timeline`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .remote.worker import estimates

__all__ = ["report", "reporting"]

_current = threading.local()


@contextmanager
def reporting(callback: Callable[[str, float | None], None]) -> Iterator[None]:
    """Pass the events of the acquisitions in the current thread to
    ``callback(kind, seconds)``.

    Both the estimates logged in this thread, and the events reported with
    :func:`report` (e.g. received from a remote worker).
    """
    previous = getattr(_current, "callback", None)
    _current.callback = callback
    try:
        with estimates(lambda seconds, kind: callback(kind, seconds)):
            yield
    finally:
        _current.callback = previous


def report(kind: str, seconds: float | None = None) -> None:
    """Report an event (see :mod:`.timeline`), with its estimate if any, to the
    callback of the current thread, if any."""
    callback = getattr(_current, "callback", None)
    if callback is not None:
        callback(kind, seconds)

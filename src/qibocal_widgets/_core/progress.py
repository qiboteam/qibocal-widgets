"""Duration estimates of the acquisitions, reported while they run.

Qibolab logs an estimate of the duration of every execution on the platform,
which drivers may refine (e.g. Qblox, accounting for its overheads). They are
captured where the acquisition runs: in the current thread for local runners,
in the worker for remote ones, which streams them back while the job runs.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .remote.worker import estimates

__all__ = ["report", "reporting"]

_current = threading.local()


@contextmanager
def reporting(callback: Callable[[float], None]) -> Iterator[None]:
    """Pass the estimates of the acquisitions in the current thread to ``callback``.

    Both the estimates logged in this thread, and those reported with
    :func:`report` (e.g. received from a remote worker).
    """
    previous = getattr(_current, "callback", None)
    _current.callback = callback
    try:
        with estimates(callback):
            yield
    finally:
        _current.callback = previous


def report(seconds: float) -> None:
    """Report an estimate, to the callback of the current thread, if any."""
    callback = getattr(_current, "callback", None)
    if callback is not None:
        callback(seconds)

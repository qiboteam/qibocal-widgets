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
from typing import Any

from .remote.worker import Cancelled, estimates

__all__ = ["annotate", "current", "report", "reporting"]

_current = threading.local()


@contextmanager
def reporting(
    callback: Callable[..., None], context: dict[str, Any] | None = None
) -> Iterator[None]:
    """Pass the events of the acquisitions in the current thread to
    ``callback(kind, seconds, name)`` (``name`` for ``stage`` events).

    Both the estimates logged in this thread, and the events reported with
    :func:`report` (e.g. received from a remote worker). ``context`` is
    shared with runners: read with :func:`current`, extended with
    :func:`annotate`.
    """
    previous = getattr(_current, "callback", None), getattr(_current, "context", {})
    _current.callback = callback
    _current.context = {} if context is None else context
    try:
        with estimates(lambda seconds, kind: _estimated(callback, kind, seconds)):
            yield
    finally:
        _current.callback, _current.context = previous


def _estimated(callback: Callable[..., None], kind: str, seconds: float) -> None:
    """Pass an estimate on, then stop here if the acquisition was cancelled:
    before the execution, or the batch, it estimates."""
    callback(kind, seconds)
    cancel = current("cancel")
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def annotate(**values: Any) -> None:
    """Add to the context of the acquisition in the current thread, if any (e.g.
    how it ran, for its profile)."""
    context = getattr(_current, "context", None)
    if context is not None and getattr(_current, "callback", None) is not None:
        context.update(values)


def current(name: str, default: Any = None) -> Any:
    """A value of the context of the acquisition in the current thread (e.g.
    its reuse ``key``), given to :func:`reporting`."""
    return getattr(_current, "context", {}).get(name, default)


def report(kind: str, seconds: float | None = None, name: str | None = None) -> None:
    """Report an event (see :mod:`.timeline`), with its estimate if any, to the
    callback of the current thread, if any."""
    callback = getattr(_current, "callback", None)
    if callback is not None:
        callback(kind, seconds, name)

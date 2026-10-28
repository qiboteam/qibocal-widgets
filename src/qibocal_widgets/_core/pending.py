"""Executions running in the background."""

from __future__ import annotations

import asyncio
import contextlib
import html
import threading
from collections.abc import Callable, Generator
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from qibocal.auto.operation import BoundProtocol

from .completed import MARIMO, MIMEBUNDLE, Completed, View
from .protocols import reference

__all__ = ["Estimate", "Pending"]

WAITING = "waiting"
"""Waiting for the instruments, busy with an earlier acquisition."""
ACQUIRING = "acquiring"
"""Acquiring: for remote runners, queued or running on the cluster."""
PROCESSING = "processing"
"""Recording, fitting, reporting, updating; or waiting for earlier executions to."""
DONE = "done"
FAILED = "failed"
STATES = (WAITING, ACQUIRING, PROCESSING, DONE, FAILED)


@dataclass(frozen=True)
class Estimate:
    """An estimate of the acquisition duration, logged by qibolab or its driver."""

    seconds: float
    """Estimated duration."""
    at: datetime
    """When it was received (UTC): the acquisition starts after it."""
    kind: str = "execution"
    """``execution``, for a whole execution on the platform (from qibolab), or
    ``batch``, for one of its batches (refined by the driver, e.g. Qblox)."""


PROGRESS_STYLE = (
    "<style>@keyframes qibocal-widgets-progress"
    " { from { width: 0 } to { width: 100% } }</style>"
)


class Pending:
    """An execution running in the background, returned by
    :meth:`Executor.submit <qibocal_widgets.Executor.submit>`.

    Get its result synchronously, blocking until it is available::

        completed = pending.result()

    asynchronously, where top-level ``await`` is available::

        completed = await pending

    or peek at it, without blocking: ``pending()`` is the result, or ``None``
    while running (and raises if the execution failed).

    Displayed, it shows its state; frontends may update the display when the
    execution completes. Frontends may also provide a subclass (see
    :meth:`Frontend.background <qibocal_widgets.Frontend.background>`), e.g.
    reactive in Marimo.
    """

    def __init__(self, bound: BoundProtocol):
        self.bound = bound
        """The protocol being executed."""
        self.future: Future[Completed] = Future()
        """The underlying future."""
        self.submitted_at = datetime.now(UTC)
        """When the execution was submitted (UTC)."""
        self.views: dict[str, View] = {}
        """Views registered by frontends, keyed by display protocol."""
        self.estimates: list[Estimate] = []
        """Duration estimates received while acquiring, in order: each one
        refines the previous ones, and restarts the progress bar."""
        self._status = WAITING
        self._callbacks: list[Callable[[Pending], None]] = []
        self._lock = threading.Lock()

    # -- state -------------------------------------------------------------------

    @property
    def status(self) -> str:
        """One of ``waiting``, ``acquiring``, ``processing``, ``done``, ``failed``."""
        return self._status

    @property
    def name(self) -> str:
        """The protocol name, for display."""
        found = reference(self.bound.protocol)
        if found is not None:
            return found.rpartition(":")[2]
        return getattr(self.bound.protocol.acquisition, "__module__", "protocol")

    def on_change(self, callback: Callable[[Pending], None]) -> Callable[[], None]:
        """Call ``callback(pending)`` on every change of state, from any thread.

        Changes of state include new estimates. Returns a function removing the
        callback.
        """
        with self._lock:
            self._callbacks.append(callback)

        def remove() -> None:
            with self._lock, contextlib.suppress(ValueError):
                self._callbacks.remove(callback)

        return remove

    def _set(self, status: str) -> None:
        self._status = status
        self._notify()

    def _notify(self) -> None:
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback(self)

    def _estimate(self, seconds: float, kind: str = "execution") -> None:
        """Record a duration estimate (from the acquiring thread)."""
        self.estimates.append(Estimate(seconds, datetime.now(UTC), kind))
        self._notify()
        self._estimated()

    def _estimated(self) -> None:
        """Hook run, in the background thread, on every new estimate."""

    def _resolve(self, completed: Completed) -> None:
        self.future.set_result(completed)
        self._set(DONE)
        self._completed()

    def _fail(self, error: BaseException) -> None:
        self.future.set_exception(error)
        self._set(FAILED)
        self._completed()

    def _completed(self) -> None:
        """Hook run once, in the background thread, when the execution ends."""

    # -- results -------------------------------------------------------------------

    def __call__(self) -> Completed | None:
        """The result if available, ``None`` otherwise, without blocking.

        Raises:
            Exception: the error of the execution, if it failed.
        """
        if not self.future.done():
            return None
        return self.future.result()

    def done(self) -> bool:
        """Whether the execution completed, successfully or not."""
        return self.future.done()

    def result(self, timeout: float | None = None) -> Completed:
        """The completed execution, waiting for it if needed.

        Raises:
            TimeoutError: if not completed within ``timeout`` seconds.
            Exception: the error of the execution, if it failed.
        """
        return self.future.result(timeout)

    def exception(self, timeout: float | None = None) -> BaseException | None:
        """The error of the execution, if it failed."""
        return self.future.exception(timeout)

    def __await__(self) -> Generator[Any, None, Completed]:
        return asyncio.wrap_future(self.future).__await__()

    # -- display -------------------------------------------------------------------

    def describe(self) -> str:
        """A short description of the state."""
        if self._status == FAILED:
            return f"{self.name}: failed, {self.future.exception()!r}"
        return f"{self.name}: {self._status}, submitted at {self.submitted_at:%H:%M:%S} UTC"

    @property
    def batches(self) -> int:
        """Batches started in the current execution on the platform, as
        estimated by the driver: all but the last are done."""
        count = 0
        for estimate in reversed(self.estimates):
            if estimate.kind != "batch":
                break
            count += 1
        return count

    def progress(self) -> str | None:
        """A progress bar, as HTML, while acquiring with an estimate.

        It fills in the latest estimated duration, from when the estimate was
        received, with a CSS animation: no further update is needed. The
        first estimate is shown for comparison, and the batches done, once
        the driver estimates them (their total is not known in advance).
        """
        if self._status != ACQUIRING or not self.estimates:
            return None
        first, latest = self.estimates[0], self.estimates[-1]
        elapsed = (datetime.now(UTC) - latest.at).total_seconds()
        seconds = max(latest.seconds, 1e-3)
        text = f"estimated {_duration(latest.seconds)}"
        if len(self.estimates) > 1:
            text += (
                f" (estimate {len(self.estimates)}, first {_duration(first.seconds)})"
            )
        text += f", from {latest.at:%H:%M:%S} UTC"
        if self.batches:
            text += f"; batches done: {self.batches - 1}/?"
        animation = (
            f"qibocal-widgets-progress {seconds:.3f}s linear {-elapsed:.3f}s forwards"
        )
        return (
            f"{PROGRESS_STYLE}<div style='min-width: 16em; max-width: 40em'>"
            f"<div><b>{html.escape(self.name)}</b>: acquiring, {text}</div>"
            "<div style='height: 0.5em; margin-top: 0.3em; border-radius: 0.25em;"
            " background: rgba(127, 127, 127, 0.25); overflow: hidden'>"
            "<div style='height: 100%; width: 0; background: #3b82f6;"
            f" animation: {animation}'></div></div></div>"
        )

    def _display_(self) -> Any:
        """Marimo display protocol."""
        view = self.views.get(MARIMO)
        return view(self) if view is not None else self.describe()

    def _repr_mimebundle_(self, include=None, exclude=None) -> dict | None:
        """IPython display protocol."""
        view = self.views.get(MIMEBUNDLE)
        if view is None:
            return None
        return view(self)._repr_mimebundle_(include=include, exclude=exclude)

    def __repr__(self) -> str:
        return f"<Pending {self.describe()}>"


def _duration(seconds: float) -> str:
    """A duration, for display."""
    if seconds < 60:
        return f"{seconds:.3g} s"
    minutes, seconds = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"

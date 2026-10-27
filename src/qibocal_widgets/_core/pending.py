"""Executions running in the background."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Generator
from concurrent.futures import Future
from datetime import UTC, datetime
from typing import Any

from qibocal.auto.operation import BoundProtocol

from .completed import MARIMO, MIMEBUNDLE, Completed, View
from .protocols import reference

__all__ = ["Pending"]

WAITING = "waiting"
"""Waiting for the instruments, busy with an earlier acquisition."""
ACQUIRING = "acquiring"
"""Acquiring: for remote runners, queued or running on the cluster."""
PROCESSING = "processing"
"""Recording, fitting, reporting, updating; or waiting for earlier executions to."""
DONE = "done"
FAILED = "failed"
STATES = (WAITING, ACQUIRING, PROCESSING, DONE, FAILED)


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

    def on_change(self, callback: Callable[[Pending], None]) -> None:
        """Call ``callback(pending)`` on every change of state, from any thread."""
        with self._lock:
            self._callbacks.append(callback)

    def _set(self, status: str) -> None:
        self._status = status
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback(self)

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

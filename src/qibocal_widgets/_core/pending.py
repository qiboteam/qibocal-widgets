"""Executions running in the background."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable, Generator
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from qibocal.auto.operation import BoundProtocol

from .completed import MARIMO, MIMEBUNDLE, Completed, View
from .protocols import reference
from .timeline import ACQUIRED, BATCH, EXECUTION, STAGE, STARTED, Event, Timeline

__all__ = ["Estimate", "NotStartedError", "Pending"]


class NotStartedError(RuntimeError):
    """An execution waiting for confirmation was waited for."""


READY = "ready"
"""Not started yet: waiting for confirmation (see ``Executor.submit``)."""
WAITING = "waiting"
"""Waiting for the instruments, busy with an earlier acquisition."""
ACQUIRING = "acquiring"
"""Acquiring: for remote runners, queued or running on the cluster."""
PROCESSING = "processing"
"""Recording, fitting, reporting, updating; or waiting for earlier executions to."""
DONE = "done"
FAILED = "failed"
STATES = (READY, WAITING, ACQUIRING, PROCESSING, DONE, FAILED)


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


QUEUED = "queued"
"""Acquiring: waiting in the queue of a remote runner."""
STARTING = "starting"
"""Acquiring: starting remotely, e.g. connecting."""
RUNNING = "running"
"""Acquiring: running."""
TRANSFERRING = "transferring"
"""Acquiring: acquired remotely, receiving the data."""
STAGE_PHASES = {
    "environment started": "importing",
    "imported": "creating the platform",
    "platform created": "connecting",
    "connected": "preparing",
}
"""Phases following the stages of remote jobs, until the first estimate."""
WAITING_EARLIER = "waiting for earlier executions"
"""Processing: earlier submissions are processed first."""


class Pending:
    """An execution running in the background, returned by
    :meth:`Executor.submit <qibocal_widgets.Executor.submit>`.

    Get its result synchronously, blocking until it is available::

        completed = pending.result()

    asynchronously, where top-level ``await`` is available::

        completed = await pending

    or peek at it, without blocking: ``pending()`` is the result, or ``None``
    while running (and raises if the execution failed).

    Submitted with ``confirm``, it is ``ready`` and waits for confirmation
    before starting: its *Run* button, or :meth:`start`. Once completed, it
    can run again, with its *Run again* button, or :meth:`rerun`.

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
        self.started_at: datetime | None = None
        """When it started (UTC): once confirmed, with ``confirm``, or as soon
        as submitted otherwise. Times and profiles count from there."""
        self.finished_at: datetime | None = None
        """When it completed (UTC)."""
        self.views: dict[str, View] = {}
        """Views registered by frontends, keyed by display protocol."""
        self.timeline = Timeline()
        """Events of the acquisition: start, duration estimates, end."""
        self.context: dict[str, Any] = {}
        """Where and how it ran, for its profile (see ``Completed.profile``)."""
        self._view_state: dict[str, Any] = {}
        """State of the displayed views to keep across updates (e.g. folds)."""
        self._phase: str | None = None
        self.history: list[tuple[datetime, str, str | None]] = []
        """Changes of status and phase, with their times (UTC), for profiling."""
        self.overrides: dict[str, Any] = {}
        """Execution overrides (e.g. ``targets``), as given to ``submit``."""
        self._status = READY
        self._launcher: Callable[[], None] | None = None
        self._rerun: Callable[[], None] | None = None
        self._runs = 0
        """Times the execution ran again (see :meth:`rerun`)."""
        self._callbacks: list[Callable[[Pending], None]] = []
        self._lock = threading.Lock()

    # -- state -------------------------------------------------------------------

    @property
    def status(self) -> str:
        """One of ``ready``, ``waiting``, ``acquiring``, ``processing``,
        ``done``, ``failed``."""
        return self._status

    def start(self) -> None:
        """Start an execution waiting for confirmation (``ready``).

        As its *Run* button does; nothing happens if already started.
        """
        with self._lock:
            if self._status != READY:
                return
            self._status = WAITING
            self.started_at = datetime.now(UTC)
        self._notify()
        self._dispatch()

    def update(self, targets: Any = None) -> list:
        """Apply the platform update of the completed execution, as
        :meth:`Completed.update <qibocal_widgets.Completed.update>`.

        Raises:
            ValueError: if not completed successfully.
        """
        if self._status != DONE:
            raise ValueError(f"{self.name} is {self._status}: nothing to update yet")
        return self.result().update(targets)

    def rerun(self) -> None:
        """Run a completed execution again, as its *Run again* button does.

        The same handle follows the new execution: ``pending()`` is ``None``
        again until it completes, ``result()`` waits for it. It ignores reuse:
        the protocol is acquired again, and recorded anew in the session. Nothing
        happens while running, or waiting for confirmation.
        """
        with self._lock:
            if self._status not in (DONE, FAILED) or self._rerun is None:
                return
            self.future = Future()
            self._runs += 1
            self.submitted_at = self.started_at = datetime.now(UTC)
            self.finished_at = None
            self.timeline = Timeline()
            self._phase = None
            self.history = []
            self._launcher = self._rerun
            self._status = WAITING
        self._restarted()
        self._notify()
        self._dispatch()

    def _restarted(self) -> None:
        """Hook run when the execution runs again (see :meth:`rerun`)."""

    def _dispatch(self) -> None:
        """Launch the execution, once started."""
        self._run_launcher()

    def _run_launcher(self) -> None:
        """Run the launcher given by the executor, at most once."""
        with self._lock:
            launcher, self._launcher = self._launcher, None
        if launcher is not None:
            launcher()

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

    @property
    def phase(self) -> str | None:
        """What the execution is doing, within its status (e.g. ``queued``,
        ``importing``, or ``fitting``)."""
        return self._phase

    @phase.setter
    def phase(self, phase: str | None) -> None:
        self._phase = phase
        self.history.append((datetime.now(UTC), self._status, phase))

    def _set(self, status: str) -> None:
        self._status = status
        self.history.append((datetime.now(UTC), status, self._phase))
        self._notify()

    def _notify(self) -> None:
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback(self)

    @property
    def estimates(self) -> list[Estimate]:
        """Duration estimates received while acquiring, in order (see
        :attr:`timeline`, which groups them)."""
        return [
            Estimate(event.seconds, event.at, event.kind)
            for event in self.timeline.events
            if event.kind in (EXECUTION, BATCH)
        ]

    def _event(
        self, kind: str, seconds: float | None = None, name: str | None = None
    ) -> None:
        """Record an event of the acquisition (from the acquiring thread)."""
        self.timeline.events.append(Event(kind, datetime.now(UTC), seconds, name))
        if kind == STAGE and name in STAGE_PHASES and self.phase != TRANSFERRING:
            self.phase = STAGE_PHASES[name]
        elif kind == STARTED and self.phase in (None, QUEUED, STARTING):
            self.phase = STARTING
        elif kind in (EXECUTION, BATCH) and self.phase != RUNNING:
            self.phase = RUNNING
        elif kind == ACQUIRED and self._status == ACQUIRING:
            self.phase = TRANSFERRING
        self._notify()

    def _estimate(self, seconds: float, kind: str = EXECUTION) -> None:
        """Record a duration estimate."""
        self._event(kind, seconds)

    def _set_phase(self, phase: str | None) -> None:
        """Record what the execution is doing, within its status."""
        if phase != self.phase:
            self.phase = phase
            self._notify()

    @property
    def elapsed(self) -> float | None:
        """Seconds from the start (confirmation, with ``confirm``, or
        submission; or the latest run) to completion, if completed: including
        waiting, e.g. in the queue."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self._origin).total_seconds()

    @property
    def _origin(self) -> datetime:
        """Where times count from: the start, if started."""
        return self.started_at or self.submitted_at

    def _resolve(self, completed: Completed) -> None:
        self.finished_at = datetime.now(UTC)
        self.phase = None
        self.future.set_result(completed)
        self._set(DONE)
        self._completed()

    def _fail(self, error: BaseException) -> None:
        self.finished_at = datetime.now(UTC)
        self.phase = None
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
            NotStartedError: if waiting for confirmation (waiting for it
                would block the confirmation itself).
            TimeoutError: if not completed within ``timeout`` seconds.
            Exception: the error of the execution, if it failed.
        """
        self._check_started()
        return self.future.result(timeout)

    def exception(self, timeout: float | None = None) -> BaseException | None:
        """The error of the execution, if it failed."""
        self._check_started()
        return self.future.exception(timeout)

    def __await__(self) -> Generator[Any, None, Completed]:
        self._check_started()
        return asyncio.wrap_future(self.future).__await__()

    def _check_started(self) -> None:
        if self._status == READY:
            raise NotStartedError(
                f"{self.name} is not started: press its Run button, or call "
                "pending.start()"
            )

    # -- display -------------------------------------------------------------------

    def describe(self) -> str:
        """A short description of the state."""
        if self._status == FAILED:
            return f"{self.name}: failed, {self.future.exception()!r}"
        if self._status == READY:
            return f"{self.name}: ready, waiting for confirmation"
        state = self._status if self.phase is None else f"{self._status}, {self.phase}"
        return f"{self.name}: {state}, submitted at {self.submitted_at:%H:%M:%S} UTC"

    def profile(self) -> Any:
        """Where the time went, as a table (a pandas ``DataFrame``): each step,
        and how long it took to reach it, from the start (the confirmation,
        with ``confirm``; the submission otherwise).

        Remote jobs report their stages (out of the queue, imports, platform
        creation, connection, the executions, disconnection, encoding), and
        the executor its own (transfer, recording, fitting, reporting,
        updating). The time between two consecutive steps is attributed to
        the later one.
        """
        from .profile import table

        return table(self)

    @property
    def batches(self) -> int:
        """Batches started in the current execution on the platform, as
        estimated by the driver: all but the last are done."""
        executions = self.timeline.executions
        return len(executions[-1].batches) if executions else 0

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

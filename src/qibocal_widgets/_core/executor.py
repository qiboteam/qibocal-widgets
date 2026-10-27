"""General-purpose executor, composed of a runner, middleware, and frontends.

:class:`Executor` is a drop-in replacement of :class:`qibocal.Executor`.
Every step goes through:

1. the middleware, in registration order (the first is the outermost);
2. the runner, which does the actual work (locally by default);

and every output is returned as a :class:`Completed`, transformed by the
middleware result hooks and displayed by all the frontends.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from functools import partial
from typing import Any

from qibocal import Executor as QibocalExecutor
from qibocal.auto.operation import BoundProtocol
from qibocal.auto.task import Completed as QibocalCompleted
from qibocal.auto.task import Targets

from .completed import Completed, convert
from .frontend import Frontend
from .middleware import Middleware
from .output import REPORTS_DIR, default_path
from .pending import ACQUIRING, PROCESSING, Pending
from .protocols import reference, registered_name
from .remote.worker import parameters_document
from .runner import Local, Runner
from .session import Session
from .state import PlatformState

__all__ = ["Executor"]


def _check(items: Iterable[Any], kind: type, role: str) -> list:
    items = list(items)
    for item in items:
        if not isinstance(item, kind):
            raise TypeError(f"{item!r} is not a {kind.__name__}, as {role} require")
    return items


class Executor(QibocalExecutor):
    """Qibocal executor composed of a runner, middleware, and frontends.

    All the constructors of :class:`qibocal.Executor` (``create``, ``open``,
    and the default one) are available, and accept the same additional
    keyword arguments. ``create`` and ``open`` also default the output path to
    a fresh folder of the session's reports folder, if any (see
    :func:`~qibocal_widgets.reports_dir`).

    An executor with an output path records every execution in its
    :class:`Session` folder, appending for as long as the instance lives,
    until a new session is started (:meth:`new_session`). A new executor can
    continue an existing folder (:meth:`attach`).

    Args:
        platform: as in :class:`qibocal.Executor`.
        runner: where and how the steps run. Defaults to :class:`Local`.
        middleware: wrapping every step, the first being the outermost.
        frontends: displaying every output.
        session: the session recording the executions. Defaults to a new
            session in ``path``, if given, and to none otherwise.
        restore_platform: when given an existing session (see
            :meth:`Session.attach`), continue from the latest platform state
            recorded in its folder.
        **kwargs: forwarded to :class:`qibocal.Executor`.

    Raises:
        TypeError: for objects given in the wrong role.
    """

    def __init__(
        self,
        platform,
        *,
        runner: Runner | None = None,
        middleware: Iterable[Middleware] = (),
        frontends: Iterable[Frontend] = (),
        session: Session | None = None,
        restore_platform: bool = True,
        **kwargs: Any,
    ):
        if session is not None:
            kwargs["path"] = session.path
            kwargs["meta"] = session.meta
        super().__init__(platform, **kwargs)
        if session is None and self.path is not None:
            session = Session(self.path, self.meta)
        self.session: Session | None = session
        """The session recording the executions, if any."""
        # background executions (submit): acquisitions are serialized unless
        # the runner is concurrent, and processed in submission order
        self._instruments = threading.Lock()
        self._records = threading.RLock()
        self._order = threading.Condition()
        self._submitted = 0
        self._processed = 0
        self._running: dict[str, Pending] = {}
        self.runner: Runner = _check(
            [runner if runner is not None else Local()], Runner, "runners"
        )[0]
        self.middleware: list[Middleware] = _check(middleware, Middleware, "middleware")
        self.frontends: list[Frontend] = _check(frontends, Frontend, "frontends")
        if session is not None and session.started and restore_platform:
            session.restore(self)

    @classmethod
    def create(
        cls,
        path: os.PathLike | None = None,
        targets: Targets | None = None,
        platform: Any = None,
        **kwargs: Any,
    ) -> Executor:
        """Create an executor writing its output to ``path``.

        Args:
            path: the output folder. If omitted, a fresh subfolder of the
                session's reports folder (``QIBOCAMP_REPORTS_DIR``) is used.
            targets: as in :meth:`qibocal.Executor.create`.
            platform: as in :meth:`qibocal.Executor.create`.
            **kwargs: as in the constructor.

        Raises:
            TypeError: without ``path``, when no reports folder is set.
        """
        if path is None:
            path = default_path()
        if path is None:
            raise TypeError(
                f"create() missing the output path: pass `path`, or set {REPORTS_DIR}"
            )
        return super().create(path, targets=targets, platform=platform, **kwargs)

    @classmethod
    @contextmanager
    def open(
        cls,
        path: os.PathLike | None = None,
        targets: Targets | None = None,
        force: bool = False,
        platform: Any = None,
        update: bool | None = None,
        **kwargs: Any,
    ) -> Iterator[Executor]:
        """Enter the execution context, as :meth:`qibocal.Executor.open`.

        The output ``path`` defaults as in :meth:`create`.
        """
        with super().open(
            path,
            targets=targets,
            force=force,
            platform=platform,
            update=update,
            **kwargs,
        ) as executor:
            yield executor

    @classmethod
    def attach(
        cls,
        path: os.PathLike,
        targets: Targets | None = None,
        platform: Any = None,
        *,
        restore_platform: bool = True,
        **kwargs: Any,
    ) -> Executor:
        """Create an executor appending to an existing session folder.

        Args:
            path: the session folder.
            targets: as in :meth:`create`.
            platform: as in :meth:`create`. Defaults to the platform recorded
                in the session metadata.
            restore_platform: apply the latest platform state recorded in the
                folder, continuing the calibration where the session left it.
            **kwargs: as in the constructor.

        Raises:
            FileNotFoundError: if the folder holds no session.
        """
        session = Session.attach(path)
        if platform is None:
            platform = session.meta.platform
        return super().create(
            path,
            targets=targets,
            platform=platform,
            session=session,
            restore_platform=restore_platform,
            **kwargs,
        )

    def new_session(self, path: os.PathLike | None = None) -> Session:
        """Record the following executions in a new session folder.

        Args:
            path: the new folder. If omitted, a fresh subfolder of the
                session's reports folder (``QIBOCAMP_REPORTS_DIR``) is used.

        Raises:
            TypeError: without ``path``, when no reports folder is set.
        """
        if path is None:
            path = default_path()
        if path is None:
            raise TypeError(
                "new_session() missing the output path: pass `path`, "
                f"or set {REPORTS_DIR}"
            )
        if self.session is not None:
            self.session.flush()
        meta = None
        if self.meta is not None:
            meta = replace(self.meta, start_time=None, end_time=None, stats={})
        self.session = Session(path, meta)
        self.path = self.session.path
        self.meta = meta
        return self.session

    @property
    def platform_state(self) -> PlatformState:
        """The calibration state of the platform, to explore and update by path.

        It is the state the steps run on, as known by the runner: the local
        platform, or the state kept by a remote runner (asked to the remote
        machine, if not known yet). Updates are applied through the runner,
        and recorded in the session, as protocol updates are.
        """
        return PlatformState(
            lambda: self.runner.platform_state(self),
            self._set_platform_state,
            name="executor.platform_state",
        )

    def _set_platform_state(self, state) -> None:
        self.runner.set_platform_state(self, state)
        if self.session is not None:
            with self._records:
                self.session.platform(self)

    def note(
        self,
        content: str,
        completed: QibocalCompleted | None = None,
        *,
        author: str | None = None,
    ):
        """Add a note to the session, or to one of its executions.

        See :meth:`Session.note`.

        Raises:
            ValueError: if the executor has no session.
        """
        if self.session is None:
            raise ValueError("The executor has no session: create it with a path")
        self.session.start(self)
        return self.session.note(content, completed, author=author)

    def _record(self, completed: QibocalCompleted) -> QibocalCompleted:
        """Record a step output in the session, if any."""
        if self.session is None:
            return completed
        with self._records:
            return self.session.ensure(self, completed)

    def submit(
        self,
        bound: BoundProtocol,
        skip_fit: bool = False,
        *,
        reuse: bool = False,
        **kwargs: Any,
    ) -> Pending:
        """Execute a protocol in the background, as ``executor(bound)``.

        Returns immediately, leaving the notebook free while the execution
        runs: get its result with ``pending.result()``, ``await pending``, or
        peek at it with ``pending()``. In Marimo notebooks, the pending
        execution is reactive state: cells referencing it run again when it
        completes.

        - With a remote runner, acquisitions are independent jobs, queued
          together; with the local runner, they wait for each other, sharing
          the instruments. The execution manages the platform connection
          itself: no ``with executor:`` is needed.
        - Executions are recorded, fitted, reported, and update the platform
          in submission order, whatever the order their acquisitions complete
          in. An acquisition uses the platform state at the time it starts:
          acquisitions submitted together do not see each other's updates.

        Args:
            bound: the protocol to execute.
            skip_fit: as in ``executor(bound)``.
            reuse: return an identical execution instead of acquiring again,
                if any: one still running, or one recorded in the session
                (loaded from disk; only for protocols registered in
                ``qibocal.protocols``, which Qibocal can load back). Executions are identical with the same
                protocol, parameters, overrides, targets, and platform state.
                Useful where cells may run again unintentionally, as in
                reactive notebooks.
            **kwargs: execution overrides, as in ``executor(bound)``.
        """
        pending_type, thread_type = Pending, threading.Thread
        for frontend in self.frontends:
            found = frontend.background()
            if found is not None:
                pending_type, thread_type = found
                break

        key = self._reuse_key(bound, skip_fit, kwargs) if reuse else None
        if key is not None:
            with self._order:
                running = self._running.get(key)
            if running is not None:
                return running
            # only registered protocols can be loaded back from disk
            recorded = self.session is not None and registered_name(bound.protocol)
            folder = self.session.find(key) if recorded else None
            if folder is not None:
                pending = self._pending(pending_type, bound)
                pending._resolve(self._reload(folder))
                return pending

        pending = self._pending(pending_type, bound)
        with self._order:
            ticket = self._submitted
            self._submitted += 1
            if key is not None:
                self._running[key] = pending
        thread = thread_type(
            target=self._background,
            args=(pending, ticket, bound, skip_fit, kwargs, key),
            name=f"qibocal-widgets-{pending.name}-{ticket}",
            daemon=True,
        )
        thread.start()
        return pending

    def _pending(self, pending_type: type[Pending], bound: BoundProtocol) -> Pending:
        pending = pending_type(bound)
        for frontend in self.frontends:
            pending.views[frontend.protocol] = frontend.render_pending
        return pending

    def _reuse_key(
        self, bound: BoundProtocol, skip_fit: bool, kwargs: dict
    ) -> str | None:
        """Identity of an execution, for reuse; ``None`` if not identifiable."""
        protocol = reference(bound.protocol)
        if protocol is None:
            return None
        targets = kwargs.get("targets", self.targets)
        try:
            document = {
                "protocol": protocol,
                "parameters": parameters_document(bound.parameters),
                "overrides": parameters_document(
                    {k: v for k, v in kwargs.items() if k != "targets"}
                ),
                "targets": parameters_document(targets),
                "skip_fit": skip_fit,
                "state": self.runner.platform_state(self),
            }
        except TypeError:
            return None
        text = json.dumps(document, sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()

    def _reload(self, folder) -> Completed:
        """A recorded execution, loaded and reported again."""
        completed = self.load(folder)
        protocol = completed.bound.protocol
        if completed.results is not None and protocol.report is not None:
            completed = self.report(completed)
        return completed

    def _background(
        self,
        pending: Pending,
        ticket: int,
        bound: BoundProtocol,
        skip_fit: bool,
        kwargs: dict,
        key: str | None = None,
    ) -> None:
        acquired = error = None
        try:
            lock = nullcontext() if self.runner.concurrent else self._instruments
            with lock:
                pending._set(ACQUIRING)
                with self:
                    acquired = self._chain("acquire", bound, **kwargs)
        except BaseException as exception:  # noqa: BLE001 - reported to the caller
            error = exception
        pending._set(PROCESSING)
        with self._order:
            self._order.wait_for(lambda: self._processed == ticket)
        try:
            if error is not None:
                raise error
            recorded = self._record(acquired)
            if key is not None and self.session is not None:
                with self._records:
                    self.session.tag(recorded, key)
            completed = self._complete(self._finish(recorded), skip_fit)
        except BaseException as exception:  # noqa: BLE001 - reported to the caller
            pending._fail(exception)
        else:
            pending._resolve(completed)
        finally:
            with self._order:
                self._processed += 1
                self._running.pop(key, None)
                self._order.notify_all()

    def _complete(self, completed: Completed, skip_fit: bool) -> Completed:
        """The steps following the acquisition, as in ``qibocal.Executor.__call__``."""
        protocol = completed.bound.protocol
        if not skip_fit and protocol.fit is not None:
            completed = self.fit(completed)
        if completed.results is not None and protocol.report is not None:
            completed = self.report(completed)
        if (
            completed.results is not None
            and protocol.update is not None
            and self._update_enabled
        ):
            completed = self.update(completed)
        return completed

    def _chain(self, step: str, *args, **kwargs) -> Any:
        """Run a step through the middleware, down to the runner."""
        call = partial(getattr(self.runner, step), self)
        for middleware in reversed(self.middleware):
            call = partial(getattr(middleware, step), self, call)
        return call(*args, **kwargs)

    def _finish(self, completed: QibocalCompleted) -> Completed:
        """Transform and display a step output."""
        result = convert(completed)
        for middleware in self.middleware:
            result = convert(middleware.result(self, result))
        for frontend in self.frontends:
            result = frontend.attach(result, self)
        return result

    def _init(self, force: bool = False):
        if self.session is not None:
            with self._records:
                self.session.start(self, force)
            self.meta = self.session.meta
        self._chain("open")

    def close(self):
        self._chain("close")
        if self.session is not None:
            with self._records:
                self.session.flush()

    def acquire(self, bound: BoundProtocol, **kwargs: Any) -> Completed:
        completed = self._chain("acquire", bound, **kwargs)
        return self._finish(self._record(completed))

    def fit(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        fitted = self._record(self._chain("fit", completed, targets=targets))
        if self.session is not None:
            with self._records:
                self.session.results(fitted)
        return self._finish(fitted)

    def report(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        reported = self._chain("report", completed, targets=targets)
        return self._finish(self._record(reported))

    def update(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        updated = self._record(self._chain("update", completed, targets=targets))
        if self.session is not None:
            self.session.platform(self)
        return self._finish(updated)

    def load(self, path: Any) -> Completed:
        """Load a previously dumped execution, transformed and displayed."""
        return self._finish(QibocalCompleted.load(path))

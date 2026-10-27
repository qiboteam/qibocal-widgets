"""Remote execution runner."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from qibocal.auto.operation import BoundProtocol, Parameters
from qibocal.auto.task import Completed

from ..runner import Runner
from . import jobs, queue, transport
from .config import CONNECTION_VARIABLE, Connection, load_connection

if TYPE_CHECKING:
    from ..executor import Executor

__all__ = ["Remote"]


class Remote(Runner):
    """Execute the steps needing the instruments on another machine.

    Only the acquisition needs the instruments: it is dispatched according to
    the connection (see :class:`Connection`), while fit and report always run
    locally. The update runs locally when the executor has a platform, whose
    state is then sent along with every acquisition; otherwise it runs
    remotely, on the access node, and the runner keeps the resulting state.

    When the connection dispatches nothing (the process already runs where
    the instruments are), every step passes through unchanged, so the same
    notebook works on every tier.

    Args:
        connection: a named connection from the configuration file, or a
            :class:`Connection`. If omitted, the connection named by the
            ``QIBOCAL_WIDGETS_CONNECTION`` environment variable is used, or none.
        **options: :class:`Connection` fields, overriding the connection's.
    """

    def __init__(self, connection: str | Connection | None = None, **options: Any):
        if connection is None:
            connection = os.environ.get(CONNECTION_VARIABLE)
        if isinstance(connection, str):
            connection = load_connection(connection)
        base = connection.model_dump() if connection is not None else {}
        self.connection = Connection(**{**base, **options})
        """The effective connection."""
        self.state: dict | None = None
        """Calibration state of the remote platform, after remote updates."""

    def __repr__(self) -> str:
        options = self.connection.model_dump(exclude_defaults=True)
        return f"Remote({', '.join(f'{k}={v!r}' for k, v in options.items())})"

    def install(self, *, rebuild: bool = False) -> dict:
        """Prepare the remote environment, installing the requirements.

        Separate from execution: steps never install anything, and fail if the
        environment is missing. Installation runs on the access node, unless
        ``rebuild_on_compute`` is set.

        Args:
            rebuild: remove and recreate the environment.
        """
        connection = self.connection
        return transport.run(
            connection,
            {
                "action": "install",
                "python": connection.python,
                "requirements": connection.requirements,
                "rebuild": rebuild,
            },
            compute=connection.rebuild_on_compute,
        )

    def _platform(self, executor: Executor) -> str:
        if self.connection.platform is not None:
            return self.connection.platform
        if executor.platform is not None:
            return executor.platform.name
        raise ValueError(
            "Remote execution needs a platform name: set it on the connection, "
            "or create the executor with a platform"
        )

    def _state(self, executor: Executor) -> dict | None:
        if executor.platform is not None:
            return jobs.platform_state(executor.platform)
        return self.state

    @property
    def concurrent(self) -> bool:
        """Dispatched acquisitions are independent jobs, queued together."""
        return self.connection.dispatched

    def platform_name(self, executor: Executor) -> str | None:
        return self.connection.platform or super().platform_name(executor)

    def queue(
        self,
        *,
        partition: str | None = None,
        user: str | None = None,
        states: list[str] | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """The SLURM queue of the connection, asked once.

        By default, the whole partition the acquisitions are submitted to, so
        that the jobs ahead are visible; the jobs of the remote user are
        flagged as ``mine``, those of this runner as ``ours``. The query and
        its fields are the ones of Qibocamp.

        Args:
            partition: defaults to the ``queue`` of the connection.
            user: restrict to the jobs of a user.
            states: restrict to some job states (e.g. ``["PENDING"]``).
            timeout: seconds to wait for the answer.
        """
        return queue.query(
            self.connection,
            partition=partition,
            user=user,
            states=states,
            timeout=timeout,
        )

    def monitor(self, *, interval: float = 30.0, mine: bool = False, **options):
        """A refreshable view of the queue, for Jupyter and Marimo.

        Args:
            interval: seconds between automatic refreshes, while displayed;
                ``0`` refreshes only on request.
            mine: show only the jobs of the remote user.
            **options: forwarded to :meth:`queue`.

        Requires ``anywidget`` (in the ``jupyter`` and ``marimo`` extras).
        """
        from .monitor import QueueMonitor

        return QueueMonitor(self, interval=interval, mine=mine, **options)

    def describe(self, executor: Executor) -> dict:
        """The calibration state of the remote platform, as found remotely.

        Runs on the access node, outside of the queue: the platform is created,
        but not connected.
        """
        job = {"action": "describe", "platform": self._platform(executor)}
        return transport.run(self.connection, job, compute=False)["state"]

    def platform_state(self, executor: Executor) -> dict | None:
        state = self._state(executor)
        if (
            state is None
            and self.connection.dispatched
            and self.platform_name(executor) is not None
        ):
            # not known locally yet: ask the remote machine, once
            self.state = state = self.describe(executor)
        return state

    def set_platform_state(self, executor: Executor, state: dict) -> None:
        if executor.platform is not None:
            super().set_platform_state(executor, state)
        else:
            # the remote platform state, sent along with every acquisition
            self.state = state

    def open(self, executor: Executor) -> None:
        if not self.connection.dispatched:
            return super().open(executor)
        # the platform is connected remotely, by each acquisition
        return None

    def close(self, executor: Executor) -> None:
        if not self.connection.dispatched:
            return super().close(executor)
        return None

    def acquire(self, executor: Executor, bound: BoundProtocol, **kwargs) -> Completed:
        if not self.connection.dispatched:
            return super().acquire(executor, bound, **kwargs)
        targets = kwargs.pop("targets", None)
        targets = executor.targets if targets is None else targets
        if targets is None:
            raise ValueError(
                "Targets must be supplied when the executor has no default targets"
            )
        job = jobs.acquire_job(
            bound,
            platform=self._platform(executor),
            targets=targets,
            state=self._state(executor),
            overrides=kwargs,
        )
        outcome = transport.run(self.connection, job, compute=True)
        data = jobs.load_files(outcome["files"], bound.protocol.data_type.load)
        return Completed(
            bound=_executed(bound, outcome["parameters"]),
            _data=data,
            _targets=outcome["targets"],
            data_time=outcome["data_time"],
        )

    def update(self, executor: Executor, completed: Completed, **kwargs) -> Completed:
        if not self.connection.dispatched or executor.platform is not None:
            # updating only modifies the platform parameters, with no need
            # for the instruments: the new state travels with the next jobs
            return super().update(executor, completed, **kwargs)
        if completed.bound is None or completed.results is None:
            raise ValueError("Updating requires a fitted execution")
        targets = kwargs.get("targets")
        job = jobs.update_job(
            completed.bound,
            completed.results,
            platform=self._platform(executor),
            targets=completed.targets if targets is None else targets,
            state=self.state,
        )
        self.state = transport.run(self.connection, job, compute=False)["state"]
        return replace(completed)


def _executed(bound: BoundProtocol, parameters: Any) -> BoundProtocol:
    """The bound protocol with the parameters actually used remotely.

    These include execution overrides and platform defaults (e.g. ``nshots``).
    """
    kind = bound.protocol.parameters_type
    if isinstance(kind, type) and issubclass(kind, Parameters):
        return replace(bound, parameters=kind.load(parameters))
    return bound

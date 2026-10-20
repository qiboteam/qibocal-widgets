"""Runners: where and how the executor steps run.

An executor has exactly one runner, the innermost layer of every step: the
middleware wrap it, and it does the actual work. The base implementation runs
every step locally, with Qibocal's own executor; runners executing some steps
elsewhere override only those, and keep the rest local.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qibocal import Executor as QibocalExecutor
from qibocal.auto.operation import BoundProtocol
from qibocal.auto.task import Completed

if TYPE_CHECKING:
    from .executor import Executor

__all__ = ["Local", "Runner"]


class Runner:
    """Base runner: every step runs locally, as in :class:`qibocal.Executor`."""

    def open(self, executor: Executor) -> None:
        """Enter the execution context: connect the platform.

        The output folder is managed by the executor's session, not by the
        runner.
        """
        if executor.platform is not None:
            executor.platform.connect()

    def close(self, executor: Executor) -> None:
        """Exit the execution context: disconnect the platform."""
        if executor.platform is not None:
            executor.platform.disconnect()

    def platform_name(self, executor: Executor) -> str | None:
        """Name of the platform the steps run on, if known."""
        return executor.platform.name if executor.platform is not None else None

    def acquire(
        self, executor: Executor, bound: BoundProtocol, **kwargs: Any
    ) -> Completed:
        """Acquire data, as :meth:`qibocal.Executor.acquire`."""
        return QibocalExecutor.acquire(executor, bound, **kwargs)

    def fit(self, executor: Executor, completed: Completed, **kwargs: Any) -> Completed:
        """Fit data, as :meth:`qibocal.Executor.fit`."""
        return QibocalExecutor.fit(executor, completed, **kwargs)

    def report(
        self, executor: Executor, completed: Completed, **kwargs: Any
    ) -> Completed:
        """Report results, as :meth:`qibocal.Executor.report`."""
        return QibocalExecutor.report(executor, completed, **kwargs)

    def update(
        self, executor: Executor, completed: Completed, **kwargs: Any
    ) -> Completed:
        """Update the platform, as :meth:`qibocal.Executor.update`."""
        return QibocalExecutor.update(executor, completed, **kwargs)

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class Local(Runner):
    """Run every step in the current process (the default runner)."""

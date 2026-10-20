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

    def open(self, executor: Executor, force: bool = False) -> None:
        """Initialize the execution context (output folder, platform connection)."""
        QibocalExecutor._init(executor, force)

    def close(self, executor: Executor) -> None:
        """Finalize the execution context."""
        QibocalExecutor.close(executor)

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

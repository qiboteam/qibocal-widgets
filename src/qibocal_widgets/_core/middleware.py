"""Executor middleware.

Middleware wrap the executor steps, like in web servers: each hook receives
the next callable of the chain (``call_next``), and may alter the arguments,
post-process the output, or not call it at all. Hooks are chained in
registration order, the first middleware being the outermost; the runner is
always the innermost layer, so every middleware sees every step.

The :meth:`Middleware.result` hook additionally transforms the output of every
step, after the whole chain, in registration order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qibocal.auto.task import Completed

if TYPE_CHECKING:
    from .executor import Executor

__all__ = ["Middleware", "Next"]

Next = Callable[..., Any]
"""The next callable of a chain, accepting the step arguments."""


class Middleware:
    """Base middleware: every hook passes through unchanged.

    Subclasses override only the hooks they need.
    """

    def open(self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any):
        """Around the initialization of the execution context."""
        return call_next(*args, **kwargs)

    def close(self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any):
        """Around the finalization of the execution context."""
        return call_next(*args, **kwargs)

    def acquire(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around the acquisition."""
        return call_next(*args, **kwargs)

    def fit(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around the fit."""
        return call_next(*args, **kwargs)

    def report(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around the report."""
        return call_next(*args, **kwargs)

    def update(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around the update."""
        return call_next(*args, **kwargs)

    def result(self, executor: Executor, completed: Completed) -> Completed:
        """Transform the output of every step."""
        return completed

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

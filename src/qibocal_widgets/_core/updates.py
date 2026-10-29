"""Approval of the platform updates of an execution, per target.

Interactively, fits are validated by looking at them before their platform
update is applied: with ``update=False``, executions offer it instead, from
code (``completed.update()``) and as buttons, for all targets or per target.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from inspect import signature
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qibocal.auto.task import Completed

    from .executor import Executor

__all__ = ["Updates"]


class Updates:
    """The platform update of an execution, and the targets it was applied to.

    Shared by all the copies of an execution, as frontends make them.
    """

    def __init__(self, executor: Executor, completed: Completed):
        self.executor = executor
        self.completed = completed
        self.applied: set[Any] = set()
        """Targets whose update was applied (pairs as tuples)."""
        self._callbacks: list[Callable[[Updates], None]] = []
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        """Whether there is an update to apply: a fitted execution of a
        protocol with an update."""
        bound = self.completed.bound
        return (
            bound is not None
            and bound.protocol.update is not None
            and self.completed.results is not None
        )

    @property
    def per_target(self) -> bool:
        """Whether the update can be applied per target.

        Protocols whose update does not take a target apply it as a whole.
        """
        update = self.completed.bound.protocol.update
        parameters = signature(update).parameters
        return "target" in parameters or "qubit" in parameters

    @property
    def targets(self) -> list[Any]:
        """Targets of the execution."""
        return list(self.completed.targets)

    @property
    def pending(self) -> list[Any]:
        """Targets whose update is still to be applied."""
        return [target for target in self.targets if _key(target) not in self.applied]

    def is_applied(self, target: Any) -> bool:
        """Whether the update was applied to a target."""
        return _key(target) in self.applied

    def apply(self, targets: Iterable[Any] | None = None) -> list[Any]:
        """Apply the update, to all targets or to some, skipping those applied.

        Returns:
            The targets the update was applied to now.

        Raises:
            ValueError: if there is no update to apply, or targets are given for
                an update applied as a whole.
        """
        if not self.available:
            raise ValueError("No platform update to apply: not a fitted execution")
        chosen = self.targets if targets is None else list(targets)
        known = {_key(target) for target in self.targets}
        unknown = [target for target in chosen if _key(target) not in known]
        if unknown:
            raise ValueError(f"Not targets of the execution: {unknown}")
        if (
            not self.per_target
            and targets is not None
            and {_key(target) for target in chosen} != known
        ):
            raise ValueError("This update applies to all targets at once")
        todo = [target for target in chosen if _key(target) not in self.applied]
        if not todo:
            return []
        self.executor.update(self.completed, targets=todo if self.per_target else None)
        return todo

    def on_change(self, callback: Callable[[Updates], None]) -> None:
        """Call ``callback(updates)`` whenever targets are applied."""
        with self._lock:
            self._callbacks.append(callback)

    def _mark(self, targets: Iterable[Any] | None) -> None:
        """Record targets as applied (by ``Executor.update``)."""
        with self._lock:
            chosen = self.targets if targets is None else targets
            self.applied.update(_key(target) for target in chosen)
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback(self)


def _key(target: Any) -> Any:
    """A hashable target: pairs, given as lists, become tuples."""
    return tuple(target) if isinstance(target, list) else target

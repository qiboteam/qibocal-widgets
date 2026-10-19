"""Executor wrapper producing frontend-aware :class:`Completed` objects.

The Qibocal executor returns a plain :class:`qibocal.auto.task.Completed` from
every phase. Notebook frontends display objects through protocols
(``_display_`` in Marimo, ``_ipython_display_`` in Jupyter), so an execution
only needs to come back as an instance of a subclass implementing the right
protocol to be rendered without any explicit helper call.

:class:`WidgetExecutor` is a thin subclass of :class:`qibocal.Executor` that
converts the output of every phase into ``completed_type``. Since the
downstream phases of the executor build their result with
:func:`dataclasses.replace`, the subclass is preserved along the whole
acquire → fit → report → update chain.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, ClassVar, TypeVar

from qibocal import Executor
from qibocal.auto.operation import BoundProtocol
from qibocal.auto.task import Completed, Targets

__all__ = ["WidgetExecutor", "convert"]

_CompletedT = TypeVar("_CompletedT", bound=Completed)


def convert(completed: Completed, completed_type: type[_CompletedT]) -> _CompletedT:
    """Re-wrap an execution into another :class:`Completed` subclass.

    The operation is idempotent: instances already of the requested type are
    returned unchanged. Lazily loaded attributes (data and results stored on
    disk) are copied as they are, without triggering any loading.
    """
    if isinstance(completed, completed_type):
        return completed
    if not isinstance(completed, Completed):
        raise TypeError(f"Cannot convert {type(completed).__name__} to Completed")
    attributes = {f.name: getattr(completed, f.name) for f in fields(completed)}
    return completed_type(**attributes)


class WidgetExecutor(Executor):
    """Executor returning displayable executions.

    Subclasses set :attr:`completed_type` to the :class:`Completed` subclass
    implementing the display protocol of their notebook frontend. All the
    constructors of :class:`qibocal.Executor` (``create``, ``open``, and the
    default one) are inherited unchanged.
    """

    completed_type: ClassVar[type[Completed]] = Completed
    """The :class:`Completed` subclass produced by every phase."""

    def _wrap(self, completed: Completed) -> Completed:
        return convert(completed, self.completed_type)

    def __call__(
        self, bound: BoundProtocol, skip_fit: bool = False, **kwargs: Any
    ) -> Completed:
        return self._wrap(super().__call__(bound, skip_fit=skip_fit, **kwargs))

    def acquire(self, bound: BoundProtocol, **kwargs: Any) -> Completed:
        return self._wrap(super().acquire(bound, **kwargs))

    def fit(self, completed: Completed, *, targets: Targets | None = None) -> Completed:
        return self._wrap(super().fit(completed, targets=targets))

    def report(
        self, completed: Completed, *, targets: Targets | None = None
    ) -> Completed:
        return self._wrap(super().report(completed, targets=targets))

    def update(
        self, completed: Completed, *, targets: Targets | None = None
    ) -> Completed:
        return self._wrap(super().update(completed, targets=targets))

    def load(self, path: Any) -> Completed:
        """Load a previously dumped execution as a displayable object."""
        return self._wrap(Completed.load(path))

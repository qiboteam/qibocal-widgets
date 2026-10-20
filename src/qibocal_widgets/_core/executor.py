"""General-purpose executor, extended through plugins.

:class:`Executor` is a drop-in replacement of :class:`qibocal.Executor`
accepting a list of :class:`~qibocal_widgets.Plugin`. Every step is routed
through the plugins' hooks, and every output is returned as a
:class:`Completed`, which plugins may decorate with views for notebook
frontends.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields, replace
from functools import partial
from typing import Any, TypeVar

from qibocal import Executor as QibocalExecutor
from qibocal.auto.operation import BoundProtocol
from qibocal.auto.task import Completed as QibocalCompleted
from qibocal.auto.task import Targets

from .plugin import Plugin, check_conflicts

__all__ = ["Completed", "Executor", "View", "convert"]

View = Callable[["Completed"], Any]
"""Produce a displayable object from an execution."""

MARIMO = "_display_"
"""View key of the Marimo display protocol."""
MIMEBUNDLE = "_repr_mimebundle_"
"""View key of the IPython (Jupyter) display protocol."""

_CompletedT = TypeVar("_CompletedT", bound=QibocalCompleted)


@dataclass
class Completed(QibocalCompleted):
    """Execution carrying views for notebook frontends.

    Views are keyed by the display protocol they implement. Without a view
    for a protocol, the execution falls back to its plain representation, so
    views for several frontends can coexist on the same object.
    """

    views: dict[str, View] = field(default_factory=dict, repr=False, compare=False)
    """Views registered by plugins, keyed by display protocol."""

    def _display_(self) -> Any:
        """Marimo display protocol."""
        view = self.views.get(MARIMO)
        return view(self) if view is not None else repr(self)

    def _repr_mimebundle_(self, include=None, exclude=None) -> dict | None:
        """IPython display protocol."""
        view = self.views.get(MIMEBUNDLE)
        if view is None:
            return None
        return view(self)._repr_mimebundle_(include=include, exclude=exclude)

    def with_view(self, key: str, view: View) -> Completed:
        """A copy of the execution, with an additional view."""
        return replace(self, views={**self.views, key: view})


def convert(
    completed: QibocalCompleted, completed_type: type[_CompletedT] = Completed
) -> _CompletedT:
    """Re-wrap an execution into another :class:`qibocal.auto.task.Completed`
    subclass.

    The operation is idempotent: instances already of the requested type are
    returned unchanged. Lazily loaded attributes (data and results stored on
    disk) are copied as they are, without triggering any loading.
    """
    if isinstance(completed, completed_type):
        return completed
    if not isinstance(completed, QibocalCompleted):
        raise TypeError(f"Cannot convert {type(completed).__name__} to Completed")
    names = {f.name for f in fields(completed_type)}
    attributes = {
        f.name: getattr(completed, f.name) for f in fields(completed) if f.name in names
    }
    return completed_type(**attributes)


class Executor(QibocalExecutor):
    """Qibocal executor extended by plugins.

    All the constructors of :class:`qibocal.Executor` (``create``, ``open``,
    and the default one) are inherited, and additionally accept the
    ``plugins`` keyword argument.

    Args:
        platform: as in :class:`qibocal.Executor`.
        plugins: plugins applied to every step, the first being the outermost
            for around hooks.
        **kwargs: forwarded to :class:`qibocal.Executor`.

    Raises:
        PluginConflict: if two plugins share an exclusivity group.
    """

    def __init__(self, platform, *, plugins: Iterable[Plugin] = (), **kwargs: Any):
        super().__init__(platform, **kwargs)
        self.plugins: list[Plugin] = list(plugins)
        check_conflicts(self.plugins)

    def _chain(self, step: str, core: Callable[..., Any], *args, **kwargs) -> Any:
        """Run a step through the plugins' around hooks."""
        call = core
        for plugin in reversed(self.plugins):
            call = partial(getattr(plugin, step), self, call)
        return call(*args, **kwargs)

    def _finish(self, completed: QibocalCompleted) -> Completed:
        """Apply the plugins' result hooks to a step output."""
        result = convert(completed)
        for plugin in self.plugins:
            result = convert(plugin.result(self, result))
        return result

    def _init(self, force: bool = False):
        self._chain("open", super()._init, force)

    def close(self):
        self._chain("close", super().close)

    def acquire(self, bound: BoundProtocol, **kwargs: Any) -> Completed:
        return self._finish(self._chain("acquire", super().acquire, bound, **kwargs))

    def fit(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        return self._finish(self._chain("fit", super().fit, completed, targets=targets))

    def report(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        return self._finish(
            self._chain("report", super().report, completed, targets=targets)
        )

    def update(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        return self._finish(
            self._chain("update", super().update, completed, targets=targets)
        )

    def load(self, path: Any) -> Completed:
        """Load a previously dumped execution, through the result hooks."""
        return self._finish(QibocalCompleted.load(path))

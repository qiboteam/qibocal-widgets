"""Executor plugins.

Plugins extend :class:`~qibocal_widgets.Executor` with two kinds of hooks,
inspired by web-server middleware:

- **around hooks**, one per executor step (:meth:`Plugin.open`,
  :meth:`Plugin.close`, :meth:`Plugin.acquire`, :meth:`Plugin.fit`,
  :meth:`Plugin.report`, :meth:`Plugin.update`), receiving the next callable
  of the chain. A hook may alter the arguments, post-process the result, or
  replace the step altogether by not calling the next one (as remote
  execution does for the acquisition).
- a **result hook** (:meth:`Plugin.result`), applied to the output of every
  step after the whole chain, in registration order. Plugins which only
  decorate executions (e.g. to display them) need nothing else, and their
  position in the list is irrelevant.

Around hooks are chained in registration order: the first plugin is the
outermost, and the executor's own implementation is the innermost.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, ClassVar

from qibocal.auto.task import Completed

if TYPE_CHECKING:
    from .executor import Executor

__all__ = ["Plugin", "PluginConflict", "check_conflicts"]

Next = Callable[..., Any]
"""The next callable of a chain, accepting the step arguments."""


class PluginConflict(ValueError):
    """Two registered plugins are incompatible."""


class Plugin:
    """Base executor plugin: every hook passes through unchanged.

    Subclasses override only the hooks they need.
    """

    exclusive: ClassVar[str | None] = None
    """Exclusivity group.

    At most one plugin per group can be registered on an executor. Plugins
    replacing the same step (e.g. dispatching the acquisition elsewhere) share
    a group, since only the outermost one would otherwise take effect.
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
        """Around :meth:`qibocal.Executor.acquire`."""
        return call_next(*args, **kwargs)

    def fit(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around :meth:`qibocal.Executor.fit`."""
        return call_next(*args, **kwargs)

    def report(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around :meth:`qibocal.Executor.report`."""
        return call_next(*args, **kwargs)

    def update(
        self, executor: Executor, call_next: Next, *args: Any, **kwargs: Any
    ) -> Completed:
        """Around :meth:`qibocal.Executor.update`."""
        return call_next(*args, **kwargs)

    def result(self, executor: Executor, completed: Completed) -> Completed:
        """Transform the output of every step."""
        return completed

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


def check_conflicts(plugins: Iterable[Plugin]) -> None:
    """Reject plugins sharing an exclusivity group.

    Raises:
        PluginConflict: listing the conflicting plugins.
    """
    groups: dict[str, Plugin] = {}
    for plugin in plugins:
        group = plugin.exclusive
        if group is None:
            continue
        if group in groups:
            raise PluginConflict(
                f"{groups[group]!r} and {plugin!r} are incompatible: "
                f"only one plugin of the {group!r} group can be registered"
            )
        groups[group] = plugin

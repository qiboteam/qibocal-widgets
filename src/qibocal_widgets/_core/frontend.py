"""Frontends: how executions are displayed.

A frontend renders executions for one display system, through a display
protocol. Frontends are independent from each other and from the steps: the
executor attaches all of them to every output, after the middleware, so their
order is irrelevant and several coexist on the same execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from qibocal.auto.task import Completed as QibocalCompleted

from .completed import Completed, convert

if TYPE_CHECKING:
    from .executor import Executor

__all__ = ["Frontend"]


class Frontend:
    """Base frontend.

    Subclasses set :attr:`protocol` and implement :meth:`render`.
    """

    protocol: ClassVar[str]
    """Display protocol implemented, i.e. the key of the view."""

    def render(self, completed: QibocalCompleted) -> Any:
        """Displayable object for an execution."""
        raise NotImplementedError

    def attach(
        self, completed: QibocalCompleted, executor: Executor | None = None
    ) -> Completed:
        """A copy of the execution, displayed by this frontend.

        Args:
            completed: any execution.
            executor: the executor which produced it, if any. Frontends whose
                views interact with the executor override this method.
        """
        return convert(completed).with_view(self.protocol, self.render)

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

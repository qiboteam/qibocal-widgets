"""Frontends: how executions are displayed.

A frontend renders executions for one display system, through a display
protocol. Frontends are independent from each other and from the steps: the
executor attaches all of them to every output, after the middleware, so their
order is irrelevant and several coexist on the same execution.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, ClassVar

from qibocal.auto.task import Completed as QibocalCompleted

from .completed import Completed, convert

if TYPE_CHECKING:
    from .executor import Executor
    from .pending import Pending

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

    def background(self) -> tuple[type[Pending], type[threading.Thread]] | None:
        """The pending type and thread type of background executions.

        For frontends needing them integrated with their runtime (e.g. Marimo's
        reactive state and threads); ``None`` keeps the defaults. The first
        frontend providing them is used.
        """
        return None

    def render_pending(self, pending: Pending) -> Any:
        """Displayable object for an execution running in the background.

        By default, its state, or its result once completed; frontends able to
        update a displayed output override it.
        """
        if pending.done() and pending.exception() is None:
            return self.render(pending.result())
        return pending.describe()

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

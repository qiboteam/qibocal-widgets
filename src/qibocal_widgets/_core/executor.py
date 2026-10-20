"""General-purpose executor, composed of a runner, middleware, and frontends.

:class:`Executor` is a drop-in replacement of :class:`qibocal.Executor`.
Every step goes through:

1. the middleware, in registration order (the first is the outermost);
2. the runner, which does the actual work (locally by default);

and every output is returned as a :class:`Completed`, transformed by the
middleware result hooks and displayed by all the frontends.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial
from typing import Any

from qibocal import Executor as QibocalExecutor
from qibocal.auto.operation import BoundProtocol
from qibocal.auto.task import Completed as QibocalCompleted
from qibocal.auto.task import Targets

from .completed import Completed, convert
from .frontend import Frontend
from .middleware import Middleware
from .runner import Local, Runner

__all__ = ["Executor"]


def _check(items: Iterable[Any], kind: type, role: str) -> list:
    items = list(items)
    for item in items:
        if not isinstance(item, kind):
            raise TypeError(f"{item!r} is not a {kind.__name__}, as {role} require")
    return items


class Executor(QibocalExecutor):
    """Qibocal executor composed of a runner, middleware, and frontends.

    All the constructors of :class:`qibocal.Executor` (``create``, ``open``,
    and the default one) are inherited, and accept the same additional
    keyword arguments.

    Args:
        platform: as in :class:`qibocal.Executor`.
        runner: where and how the steps run. Defaults to :class:`Local`.
        middleware: wrapping every step, the first being the outermost.
        frontends: displaying every output.
        **kwargs: forwarded to :class:`qibocal.Executor`.

    Raises:
        TypeError: for objects given in the wrong role.
    """

    def __init__(
        self,
        platform,
        *,
        runner: Runner | None = None,
        middleware: Iterable[Middleware] = (),
        frontends: Iterable[Frontend] = (),
        **kwargs: Any,
    ):
        super().__init__(platform, **kwargs)
        self.runner: Runner = _check(
            [runner if runner is not None else Local()], Runner, "runners"
        )[0]
        self.middleware: list[Middleware] = _check(middleware, Middleware, "middleware")
        self.frontends: list[Frontend] = _check(frontends, Frontend, "frontends")

    def _chain(self, step: str, *args, **kwargs) -> Any:
        """Run a step through the middleware, down to the runner."""
        call = partial(getattr(self.runner, step), self)
        for middleware in reversed(self.middleware):
            call = partial(getattr(middleware, step), self, call)
        return call(*args, **kwargs)

    def _finish(self, completed: QibocalCompleted) -> Completed:
        """Transform and display a step output."""
        result = convert(completed)
        for middleware in self.middleware:
            result = convert(middleware.result(self, result))
        for frontend in self.frontends:
            result = frontend.attach(result, self)
        return result

    def _init(self, force: bool = False):
        self._chain("open", force)

    def close(self):
        self._chain("close")

    def acquire(self, bound: BoundProtocol, **kwargs: Any) -> Completed:
        return self._finish(self._chain("acquire", bound, **kwargs))

    def fit(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        return self._finish(self._chain("fit", completed, targets=targets))

    def report(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        return self._finish(self._chain("report", completed, targets=targets))

    def update(
        self, completed: QibocalCompleted, *, targets: Targets | None = None
    ) -> Completed:
        return self._finish(self._chain("update", completed, targets=targets))

    def load(self, path: Any) -> Completed:
        """Load a previously dumped execution, transformed and displayed."""
        return self._finish(QibocalCompleted.load(path))

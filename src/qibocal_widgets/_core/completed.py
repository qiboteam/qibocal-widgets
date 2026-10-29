"""Executions carrying views for notebook frontends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from typing import TYPE_CHECKING, Any, TypeVar

from qibocal.auto.task import Completed as QibocalCompleted

if TYPE_CHECKING:
    from .updates import Updates

__all__ = ["MARIMO", "MIMEBUNDLE", "Completed", "View", "convert"]

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
    """Views registered by frontends, keyed by display protocol."""
    updates: Updates | None = field(default=None, repr=False, compare=False)
    """Its platform update, and the targets applied, if produced by an executor
    of this package (shared by its copies)."""

    def update(self, targets: Any = None) -> list:
        """Apply the platform update of the execution, after validating its fit.

        To all targets, or to some (e.g. ``completed.update([0, 2])``); those
        already applied are skipped. The same as its *Update* buttons.

        Returns:
            The targets the update was applied to now.

        Raises:
            ValueError: if there is no update to apply, or the execution was not
                produced by an executor of this package.
        """
        if self.updates is None:
            raise ValueError("Execution not produced by a qibocal_widgets executor")
        return self.updates.apply(targets)

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

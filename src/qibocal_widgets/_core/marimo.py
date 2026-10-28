"""Marimo rendering of executions and the Marimo-flavored executor."""

from __future__ import annotations

import threading
from typing import Any

import marimo as mo
from marimo._runtime.state import State
from qibocal.auto.task import Completed as QibocalCompleted

from . import layout
from .completed import MARIMO, Completed
from .data import data_frames
from .frontend import Frontend
from .pending import DONE, FAILED, Pending
from .reports import Report, reports, reports_of

__all__ = [
    "Marimo",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]


def show_data(data: Any) -> mo.Html:
    """Accordion of raw data tables, one entry per target.

    Args:
        data: a Qibocal ``Data`` instance, or an execution (``Completed``), in
            which case its acquired data is used.
    """
    if isinstance(data, QibocalCompleted):
        data = data.data
    tables = {
        layout.data_title(target): mo.ui.table(frame)
        for target, frame in data_frames(data).items()
    }
    if not tables:
        return mo.callout(mo.md("No acquired data to display."), kind="warn")
    return mo.accordion(tables, expanded=layout.expanded(tables))


def _report_item(report: Report) -> mo.Html:
    items: list[Any] = []
    if report.table:
        # folded by default, so that only the plots are visible at first
        items.append(
            mo.accordion({layout.FIT_RESULTS: mo.center(mo.Html(report.table))})
        )
    items.extend(mo.ui.plotly(figure) for figure in report.figures)
    items.extend(mo.plain_text(str(extra)) for extra in report.extra)
    if not items:
        items.append(mo.md("*Empty report.*"))
    return mo.vstack(items)


def show_reports(reports_: Any) -> mo.Html:
    """Accordion of reports (figures and fit tables), one entry per target.

    Args:
        reports_: the ``reports`` attribute of an execution, or the execution
            itself.
    """
    items = (
        reports(reports_)
        if isinstance(reports_, QibocalCompleted)
        else reports_of(reports_)
    )
    outputs = {
        layout.report_title(target): _report_item(report)
        for target, report in items.items()
    }
    if not outputs:
        return mo.callout(mo.md("No report to display."), kind="warn")
    return mo.accordion(outputs, expanded=layout.expanded(outputs))


def display(completed: QibocalCompleted) -> mo.Html:
    """Full rendering of an execution: data and, when available, reports."""
    sections: dict[str, Any] = {}
    try:
        sections[layout.DATA] = show_data(completed.data)
    except ValueError:
        # no acquisition data (e.g. not yet loaded, or acquisition failed)
        pass
    if completed.reports is not None:
        sections[layout.REPORTS] = show_reports(completed.reports)
    if completed.error is not None:
        sections[layout.ERROR] = mo.callout(
            mo.plain_text(repr(completed.error)), kind="danger"
        )
    if not sections:
        return mo.callout(mo.md("Nothing to display yet."), kind="neutral")
    if len(sections) == 1:
        return next(iter(sections.values()))
    return mo.ui.tabs(sections, value=layout.initial_section(sections))


class Marimo(Frontend):
    """Display executions in Marimo, with :func:`display`.

    Compatible with :class:`~qibocal_widgets.jupyter.Jupyter`: each
    frontend uses its own view.
    """

    protocol = MARIMO

    def render(self, completed: QibocalCompleted) -> Any:
        return display(completed)

    def background(self) -> tuple[type[Pending], type[threading.Thread]] | None:
        """Reactive pending executions, run in ``mo.Thread``, in notebooks."""
        if not mo.running_in_notebook():
            return None
        return MarimoPending, mo.Thread

    def render_pending(self, pending: Pending) -> Any:
        """A spinner while running, then the result (or the error).

        The spinner becomes a progress bar when the duration of the acquisition
        is estimated, starting again on each refined estimate.

        Displayed as the output of the cell which submitted it, the spinner is
        replaced by the result when the execution completes (unless other
        pending executions are displayed in the same cell).
        """
        if isinstance(pending, MarimoPending):
            cell = _cell_id()
            pending._rendered_in = cell
            _RENDERED.setdefault(cell, set()).add(id(pending))
        if pending.status == DONE:
            return display(pending.result())
        if pending.status == FAILED:
            return mo.callout(mo.md(f"**{pending.describe()}**"), kind="danger")
        bar = pending.progress()
        if bar is not None:
            return mo.Html(bar)
        return mo.status.spinner(title=pending.name, subtitle=pending.describe())


_RENDERED: dict[str | None, set[int]] = {}
"""Pending executions rendered in each cell (by identity)."""


def _cell_id() -> str | None:
    """The cell being executed, if any."""
    try:
        from marimo._runtime.context import get_context

        return get_context().execution_context.cell_id
    except Exception:  # noqa: BLE001 - outside of a cell, or a script
        return None


class MarimoPending(Pending, State):
    """A pending execution which is also marimo reactive state.

    Every cell referencing it (e.g. ``ramsey = pending()``) runs again when the
    execution completes, as for any ``mo.state`` getter; together with
    ``mo.stop``, downstream cells wait for the result without blocking the
    notebook::

        ramsey = pending()
        mo.stop(ramsey is None, pending)  # the spinner, while running

    It is created by :meth:`Executor.submit
    <qibocal_widgets.Executor.submit>` in notebooks with the
    :class:`Marimo` frontend, and run in a ``mo.Thread``.
    """

    def __init__(self, bound):
        Pending.__init__(self, bound)
        State.__init__(self, None)
        self._submitted_in = _cell_id()
        self._rendered_in: str | None = None

    def __call__(self):
        return Pending.__call__(self)

    def _owns_output(self) -> bool:
        """Whether the submitting cell displays this execution, and no other one."""
        stale = getattr(mo.current_thread(), "should_exit", False)
        alone = _RENDERED.get(self._rendered_in, set()) == {id(self)}
        return (
            not stale
            and alone
            and self._submitted_in is not None
            and self._rendered_in == self._submitted_in
        )

    def _estimated(self) -> None:
        if self._owns_output():
            # the spinner, or the previous estimate, becomes the progress bar
            mo.output.replace(self._display_())

    def _completed(self) -> None:
        if self._owns_output():
            # show the result in place of the spinner
            mo.output.replace(
                display(self.result()) if self.status == DONE else self._display_()
            )
        # rerun the cells referencing this execution
        self._set_value(self.status)


def wrap(completed: QibocalCompleted) -> Completed:
    """Make any execution display itself in Marimo."""
    return Marimo().attach(completed)

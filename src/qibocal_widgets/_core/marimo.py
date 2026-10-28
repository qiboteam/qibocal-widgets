"""Marimo rendering of executions and the Marimo-flavored executor."""

from __future__ import annotations

import threading
import time
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

    def submitted(self, pending: Pending) -> None:
        """Follow the execution in the cell run submitting it, new or reused.

        A ``mo.Thread`` of the current run replaces the displayed spinner with
        the progress, then the result. It stops when the cell runs again: the
        new run follows the execution itself, if it submits it again (e.g.
        reused).
        """
        if not isinstance(pending, MarimoPending) or pending.status in ENDED:
            return
        cell, run = _run()
        if cell is None:
            return
        mo.Thread(
            target=_follow,
            args=(pending, cell, run),
            name=f"qibocal-widgets-follow-{pending.name}",
            daemon=True,
        ).start()

    def render_pending(self, pending: Pending) -> Any:
        """A spinner while running, then the result (or the error).

        The spinner becomes a progress bar when the duration of the acquisition
        is estimated, starting again on each refined estimate.

        Displayed as the output of the cell which submitted it, the spinner is
        replaced by the result when the execution completes (unless other
        pending executions are displayed in the same cell).
        """
        cell, run = _run()
        if cell is not None:
            shown = _RENDERED.get(cell)
            if shown is None or shown[0] is not run:
                shown = _RENDERED[cell] = (run, set(), time.monotonic())
            shown[1].add(id(pending))
        if pending.status == DONE:
            return display(pending.result())
        if pending.status == FAILED:
            return mo.callout(mo.md(f"**{pending.describe()}**"), kind="danger")
        bar = pending.progress()
        if bar is not None:
            return mo.Html(bar)
        return mo.status.spinner(title=pending.name, subtitle=pending.describe())


_RENDERED: dict[str, tuple[object, set[int], float]] = {}
"""Pending executions displayed by each cell, in its latest run (by identity),
and when the run first displayed one."""

ENDED = (DONE, FAILED)
"""States of a completed execution."""
POLL = 1.0
"""Seconds between checks of a followed execution, besides its changes."""
LINGER = 5.0
"""Seconds to keep following a completed execution, until it is displayed."""
GRACE = 0.25
"""Seconds between a cell displaying an execution and replacing its output.

Marimo formats the output of a cell, where the execution registers as
displayed, before sending it: a replacement in between would be overwritten.
"""


def _run() -> tuple[str | None, object]:
    """The cell being executed, if any, and a token of its current run.

    The token is the output list of the run, shared with the threads it
    spawns, and new for every run.
    """
    try:
        from marimo._runtime.context import get_context

        context = get_context().execution_context
        return context.cell_id, context.output
    except Exception:  # noqa: BLE001 - outside of a cell, or a script
        return None, None


def _follow(pending: Pending, cell: str, run: object) -> None:
    """Show the changes of an execution in the output of a cell run.

    Only while the run is the latest of the cell, and displays this execution
    alone; the display already shows the state at the time it was rendered.
    """
    thread = mo.current_thread()
    changed = threading.Event()
    remove = pending.on_change(lambda _: changed.set())
    shown = None
    lingering = None
    try:
        while not getattr(thread, "should_exit", False):
            changed.wait(POLL)
            changed.clear()
            displayed = _RENDERED.get(cell)
            alone = (
                displayed is not None
                and displayed[0] is run
                and displayed[1] == {id(pending)}
            )
            if alone and (wait := displayed[2] + GRACE - time.monotonic()) > 0:
                time.sleep(wait)  # until the displayed output has been sent
            state = (pending.status, len(pending.estimates))
            if alone and state != shown:
                mo.output.replace(pending._display_())
                shown = state
            # the status, not `done()`: it changes last, once the result is set
            if state[0] in ENDED:
                if shown == state:
                    return
                # completed before being displayed: the display may follow
                lingering = lingering or time.monotonic()
                if time.monotonic() - lingering > LINGER:
                    return
    finally:
        remove()


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

    def __call__(self):
        return Pending.__call__(self)

    def _completed(self) -> None:
        # rerun the cells referencing this execution; the displayed spinners
        # are replaced by the cell runs following it (see `Marimo.submitted`)
        self._set_value(self.status)


def wrap(completed: QibocalCompleted) -> Completed:
    """Make any execution display itself in Marimo."""
    return Marimo().attach(completed)

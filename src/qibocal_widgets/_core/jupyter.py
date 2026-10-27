"""Jupyter rendering of executions and the Jupyter-flavored executor.

Rendering relies on ``ipywidgets`` (accordions and tabs) and on the native
Jupyter renderers of pandas and Plotly.
"""

from __future__ import annotations

from typing import Any

import ipywidgets as widgets
from IPython.display import display as ipy_display
from qibocal.auto.task import Completed as QibocalCompleted

from . import layout
from .completed import MIMEBUNDLE, Completed
from .data import data_frames
from .frontend import Frontend
from .pending import DONE, FAILED, Pending
from .reports import Report, reports, reports_of

__all__ = [
    "Jupyter",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]


def _output(*objects: Any) -> widgets.Output:
    """Capture the display of some objects into an output widget."""
    out = widgets.Output()
    with out:
        for obj in objects:
            ipy_display(obj)
    return out


def _accordion(
    items: dict[str, widgets.Widget], expanded: bool = False
) -> widgets.Accordion:
    """Accordion with the given titles, optionally with the first item open."""
    accordion = widgets.Accordion(children=list(items.values()))
    for index, title in enumerate(items):
        accordion.set_title(index, title)
    accordion.selected_index = 0 if expanded and items else None
    return accordion


def _message(text: str) -> widgets.HTML:
    return widgets.HTML(f"<em>{text}</em>")


def show_data(data: Any) -> widgets.Widget:
    """Accordion of raw data tables, one entry per target.

    Args:
        data: a Qibocal ``Data`` instance, or an execution (``Completed``), in
            which case its acquired data is used.
    """
    if isinstance(data, QibocalCompleted):
        data = data.data
    tables = {
        layout.data_title(target): _output(frame)
        for target, frame in data_frames(data).items()
    }
    if not tables:
        return _message("No acquired data to display.")
    return _accordion(tables, expanded=layout.expanded(tables))


def _fit_results(table: str) -> widgets.Accordion:
    """Fit results table, centered, folded in a nested accordion."""
    centered = widgets.Box(
        [widgets.HTML(table)],
        layout=widgets.Layout(justify_content="center", width="100%"),
    )
    return _accordion({layout.FIT_RESULTS: centered})


def _report_item(report: Report) -> widgets.Widget:
    objects: list[Any] = list(report.figures)
    objects.extend(str(extra) for extra in report.extra)
    children: list[widgets.Widget] = []
    if report.table:
        # folded by default, so that only the plots are visible at first
        children.append(_fit_results(report.table))
    if objects:
        children.append(_output(*objects))
    if not children:
        return _message("Empty report.")
    return widgets.VBox(children)


def show_reports(reports_: Any) -> widgets.Widget:
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
        return _message("No report to display.")
    return _accordion(outputs, expanded=layout.expanded(outputs))


def display(completed: QibocalCompleted) -> widgets.Widget:
    """Full rendering of an execution: data and, when available, reports."""
    sections: dict[str, widgets.Widget] = {}
    try:
        sections[layout.DATA] = show_data(completed.data)
    except ValueError:
        # no acquisition data (e.g. not yet loaded, or acquisition failed)
        pass
    if completed.reports is not None:
        sections[layout.REPORTS] = show_reports(completed.reports)
    if completed.error is not None:
        sections[layout.ERROR] = widgets.HTML(
            f"<pre style='color: var(--jp-error-color1, red)'>{completed.error!r}</pre>"
        )
    if not sections:
        return _message("Nothing to display yet.")
    if len(sections) == 1:
        return next(iter(sections.values()))
    tabs = widgets.Tab(children=list(sections.values()))
    for index, title in enumerate(sections):
        tabs.set_title(index, title)
    tabs.selected_index = list(sections).index(layout.initial_section(sections))
    return tabs


class Jupyter(Frontend):
    """Display executions in Jupyter, with :func:`display`.

    Compatible with :class:`~qibocal_widgets.marimo.Marimo`: each
    frontend uses its own view.
    """

    protocol = MIMEBUNDLE

    def render(self, completed: QibocalCompleted) -> Any:
        return display(completed)

    def render_pending(self, pending: Pending) -> Any:
        """A live view: the state, replaced by the result once completed."""
        box = widgets.VBox([])

        def show(pending: Pending) -> None:
            if pending.status == DONE:
                box.children = [display(pending.result())]
            elif pending.status == FAILED:
                box.children = [widgets.HTML(f"<pre>{pending.describe()}</pre>")]
            else:
                box.children = [_message(pending.describe())]

        show(pending)
        pending.on_change(lambda pending: _on_kernel(show, pending))
        return box


def _on_kernel(function: Any, *args: Any) -> None:
    """Run a function on the kernel's main thread, as soon as it is idle.

    Updates of a pending view come from background threads, but building
    widgets may capture displays into output widgets, which relies on hooks
    of the whole kernel: they are only safe on the main thread. Outside of a
    kernel, the function runs immediately.
    """
    from IPython import get_ipython

    kernel = getattr(get_ipython(), "kernel", None)
    loop = getattr(kernel, "io_loop", None)
    if loop is None:
        function(*args)
    else:
        loop.add_callback(function, *args)


def wrap(completed: QibocalCompleted) -> Completed:
    """Make any execution display itself in Jupyter."""
    return Jupyter().attach(completed)

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
from .data import data_frames
from .executor import MIMEBUNDLE, Completed, Executor, convert
from .plugin import Plugin
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


class Jupyter(Plugin):
    """Display every execution in Jupyter, with :func:`display`.

    Compatible with :class:`~qibocal_widgets.marimo.Marimo`: each frontend
    uses its own view.
    """

    def result(self, executor: Executor, completed: QibocalCompleted) -> Completed:
        return wrap(completed)


def wrap(completed: QibocalCompleted) -> Completed:
    """Make any execution display itself in Jupyter."""
    return convert(completed).with_view(MIMEBUNDLE, display)

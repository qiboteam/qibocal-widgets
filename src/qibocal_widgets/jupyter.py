"""Jupyter interface.

Usage, inside a Jupyter notebook (JupyterLab, VS Code, ...)::

    from qibocal_widgets.jupyter import JupyterExecutor

    executor = JupyterExecutor.create(platform=platform, path="var/report")
    with executor:
        acquired = executor.acquire(protocols.ramsey(delay=(10, 1000, 100)), targets=[0])
    acquired  # rendered: raw data tables

    completed = executor(bound)
    completed  # rendered: raw data tables and per-target reports

Rendering relies on ``ipywidgets`` (accordions and tabs) and on the native
Jupyter renderers of pandas and Plotly. The :func:`show_data` and
:func:`show_reports` helpers remain available for explicit control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ipywidgets as widgets
from IPython.display import HTML
from IPython.display import display as ipy_display
from qibocal.auto.task import Completed

from ._core import Report, data_frames, label, reports, reports_of
from ._executor import WidgetExecutor, convert

__all__ = [
    "JupyterCompleted",
    "JupyterExecutor",
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


def _accordion(items: dict[str, widgets.Widget]) -> widgets.Accordion:
    accordion = widgets.Accordion(children=list(items.values()))
    for index, title in enumerate(items):
        accordion.set_title(index, title)
    if items:
        accordion.selected_index = 0
    return accordion


def _message(text: str) -> widgets.HTML:
    return widgets.HTML(f"<em>{text}</em>")


def show_data(data: Any) -> widgets.Widget:
    """Accordion of raw data tables, one entry per target.

    Args:
        data: a Qibocal ``Data`` instance, or an execution (``Completed``), in
            which case its acquired data is used.
    """
    if isinstance(data, Completed):
        data = data.data
    tables = {
        f"Raw data: {label(target)}": _output(frame)
        for target, frame in data_frames(data).items()
    }
    if not tables:
        return _message("No acquired data to display.")
    return _accordion(tables)


def _report_item(report: Report) -> widgets.Widget:
    objects: list[Any] = list(report.figures)
    if report.table:
        objects.append(HTML(report.table))
    objects.extend(str(extra) for extra in report.extra)
    if not objects:
        return _message("Empty report.")
    return _output(*objects)


def show_reports(reports_: Any) -> widgets.Widget:
    """Accordion of reports (figures and fit tables), one entry per target.

    Args:
        reports_: the ``reports`` attribute of an execution, or the execution
            itself.
    """
    items = (
        reports(reports_) if isinstance(reports_, Completed) else reports_of(reports_)
    )
    outputs = {
        ("Report" if target is None else f"Target {label(target)}"): _report_item(
            report
        )
        for target, report in items.items()
    }
    if not outputs:
        return _message("No report to display.")
    return _accordion(outputs)


def display(completed: Completed) -> widgets.Widget:
    """Full rendering of an execution: data and, when available, reports."""
    sections: dict[str, widgets.Widget] = {}
    try:
        sections["Data"] = show_data(completed.data)
    except ValueError:
        # no acquisition data (e.g. not yet loaded, or acquisition failed)
        pass
    if completed.reports is not None:
        sections["Reports"] = show_reports(completed.reports)
    if completed.error is not None:
        sections["Error"] = widgets.HTML(
            f"<pre style='color: var(--jp-error-color1, red)'>{completed.error!r}</pre>"
        )
    if not sections:
        return _message("Nothing to display yet.")
    if len(sections) == 1:
        return next(iter(sections.values()))
    tabs = widgets.Tab(children=list(sections.values()))
    for index, title in enumerate(sections):
        tabs.set_title(index, title)
    return tabs


@dataclass
class JupyterCompleted(Completed):
    """Execution that renders itself as a Jupyter output."""

    def _ipython_display_(self) -> None:
        ipy_display(display(self))

    def show_data(self) -> widgets.Widget:
        """Raw data tables."""
        return show_data(self.data)

    def show_reports(self) -> widgets.Widget:
        """Report figures and tables."""
        return show_reports(self.reports)


def wrap(completed: Completed) -> JupyterCompleted:
    """Turn any execution into a self-displaying one."""
    return convert(completed, JupyterCompleted)


class JupyterExecutor(WidgetExecutor):
    """Qibocal executor whose phases return :class:`JupyterCompleted` objects."""

    completed_type = JupyterCompleted

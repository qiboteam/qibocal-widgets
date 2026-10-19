"""Marimo rendering of executions and the Marimo-flavored executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import marimo as mo
from qibocal.auto.task import Completed

from . import layout
from .data import data_frames
from .executor import WidgetExecutor, convert
from .reports import Report, reports, reports_of

__all__ = [
    "MarimoCompleted",
    "MarimoExecutor",
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
    if isinstance(data, Completed):
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
        reports(reports_) if isinstance(reports_, Completed) else reports_of(reports_)
    )
    outputs = {
        layout.report_title(target): _report_item(report)
        for target, report in items.items()
    }
    if not outputs:
        return mo.callout(mo.md("No report to display."), kind="warn")
    return mo.accordion(outputs, expanded=layout.expanded(outputs))


def display(completed: Completed) -> mo.Html:
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


@dataclass
class MarimoCompleted(Completed):
    """Execution that renders itself as a Marimo output."""

    def _display_(self) -> Any:
        return display(self)

    def show_data(self) -> mo.Html:
        """Raw data tables."""
        return show_data(self.data)

    def show_reports(self) -> mo.Html:
        """Report figures and tables."""
        return show_reports(self.reports)


def wrap(completed: Completed) -> MarimoCompleted:
    """Turn any execution into a self-displaying one."""
    return convert(completed, MarimoCompleted)


class MarimoExecutor(WidgetExecutor):
    """Qibocal executor whose phases return :class:`MarimoCompleted` objects."""

    completed_type = MarimoCompleted

"""Layout policy shared by all frontends.

Titles and initial states (selected tab, expanded items) are decided here, so
that the Marimo and Jupyter renderings stay consistent.
"""

from __future__ import annotations

from collections.abc import Collection, Sized
from typing import Any

from .data import label

__all__ = [
    "DATA",
    "ERROR",
    "FIT_RESULTS",
    "REPORTS",
    "data_title",
    "duration",
    "expanded",
    "initial_section",
    "report_title",
    "summary",
]

DATA = "Data"
"""Title of the raw data section."""
REPORTS = "Reports"
"""Title of the reports section."""
ERROR = "Error"
"""Title of the error section."""
FIT_RESULTS = "Fit results"
"""Title of the folded fit results table, within each report."""


def data_title(target: Any) -> str:
    """Accordion title of the raw data of a target."""
    return f"Raw data: {label(target)}"


def report_title(target: Any) -> str:
    """Accordion title of the report of a target."""
    return "Report" if target is None else f"Target {label(target)}"


def initial_section(sections: Collection[str]) -> str | None:
    """Section selected when an execution is first displayed.

    Reports are the most informative content, so they are preferred whenever
    available. Otherwise the first section is shown.
    """
    if REPORTS in sections:
        return REPORTS
    return next(iter(sections), None)


def expanded(items: Sized) -> bool:
    """Whether a per-target accordion starts expanded.

    A single target is shown expanded right away, since there is nothing to
    choose among. Users can still fold it.
    """
    return len(items) == 1


def duration(seconds: float) -> str:
    """A duration, for display."""
    if seconds < 1:
        return f"{seconds * 1e3:.3g} ms"
    if seconds < 60:
        return f"{seconds:.3g} s"
    minutes, seconds = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def summary(completed: Any, total: float | None = None) -> tuple[str, str]:
    """Title and timing line of an execution, as complete as the execution.

    The protocol (its task folder, if recorded), then how long the acquisition
    and the fit took, and, for background executions, the ``total`` time since
    submitted (including the queue, for remote runners).
    """
    from .protocols import reference

    title = "Execution"
    if getattr(completed, "path", None) is not None:
        title = completed.path.name
    elif getattr(completed, "bound", None) is not None:
        found = reference(completed.bound.protocol)
        if found is not None:
            title = found.rpartition(":")[2]
    times = []
    if getattr(completed, "data_time", 0):
        times.append(f"acquired in {duration(completed.data_time)}")
    if getattr(completed, "results_time", 0) and completed.results is not None:
        times.append(f"fitted in {duration(completed.results_time)}")
    if total is not None:
        times.append(f"total {duration(total)}")
    return title, " · ".join(times)

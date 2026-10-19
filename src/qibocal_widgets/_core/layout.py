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
    "expanded",
    "initial_section",
    "report_title",
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

"""Normalization of protocol reports.

Pure data manipulation, independent of any notebook frontend: whatever a
protocol report callback returned is coerced into per-target :class:`Report`
objects, holding Plotly figures and an HTML table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import plotly.graph_objects as go
from qibocal.auto.task import Completed

__all__ = ["Report", "reports", "reports_of"]


@dataclass
class Report:
    """Normalized report content for a single target."""

    figures: list[go.Figure] = field(default_factory=list)
    """Plotly figures."""
    table: str = ""
    """HTML fragment with the fitting report table (possibly empty)."""
    extra: list[Any] = field(default_factory=list)
    """Any other objects returned by the protocol, rendered as text."""


def _normalize(report: Any) -> Report:
    """Coerce whatever a protocol report function returned into a Report."""
    if isinstance(report, Report):
        return report
    normalized = Report()
    items: Sequence[Any]
    if isinstance(report, tuple | list):
        items = list(report)
    elif report is None:
        items = []
    else:
        items = [report]
    for item in items:
        if isinstance(item, go.Figure):
            normalized.figures.append(item)
        elif isinstance(item, list | tuple) and all(
            isinstance(f, go.Figure) for f in item
        ):
            normalized.figures.extend(item)
        elif isinstance(item, str):
            if item:
                normalized.table = (
                    item if not normalized.table else (normalized.table + item)
                )
        elif item is not None:
            normalized.extra.append(item)
    return normalized


def reports_of(reports: Any) -> dict[Any, Report]:
    """Normalize protocol reports into per-target :class:`Report` objects.

    Qibocal report callbacks accepting a ``target`` argument produce a mapping
    from target to ``(figures, table)``; callbacks without it produce a single
    object. Both shapes are accepted: the latter is stored under the ``None``
    key.
    """
    if reports is None:
        return {}
    if isinstance(reports, dict):
        return {target: _normalize(report) for target, report in reports.items()}
    return {None: _normalize(reports)}


def reports(completed: Completed) -> dict[Any, Report]:
    """Normalized reports of an execution (empty if the report phase did not run)."""
    return reports_of(getattr(completed, "reports", None))

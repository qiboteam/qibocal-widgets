"""Frontend-agnostic extraction of displayable content from executions.

Everything in this module is pure data manipulation: it turns the objects
attached to a :class:`qibocal.auto.task.Completed` instance into plain
:class:`pandas.DataFrame` tables and Plotly figures, without depending on any
notebook frontend. The Marimo and Jupyter interfaces only decide how to render
the result of these functions.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from qibocal.auto.task import Completed

__all__ = ["Report", "data_frames", "label", "reports", "reports_of"]


def label(target: Any) -> str:
    """Human-readable label for a target (qubit, pair, or anything else)."""
    if isinstance(target, tuple):
        return "-".join(str(t) for t in target)
    return str(target)


def _records_frame(array: Any) -> pd.DataFrame:
    """Convert a single target's array into a table."""
    array = np.asarray(array)
    if array.dtype == object:
        raise TypeError("Object arrays cannot be tabulated")
    if array.dtype.names is not None:
        # structured (record) array: one column per field
        return pd.DataFrame({name: np.ravel(array[name]) for name in array.dtype.names})
    if np.iscomplexobj(array):
        flat = np.ravel(array)
        return pd.DataFrame(
            {
                "real": flat.real,
                "imag": flat.imag,
                "signal": np.abs(flat),
                "phase": np.angle(flat),
            }
        )
    if array.ndim <= 1:
        return pd.DataFrame({"value": np.ravel(array)})
    return pd.DataFrame(array.reshape(array.shape[0], -1))


def _extra_columns(data: Any, target: Hashable, length: int) -> dict[str, Any]:
    """Collect per-target auxiliary attributes whose length matches the records.

    Qibocal data classes often keep sweep coordinates (e.g. drive frequencies)
    outside the record array, in dictionaries keyed by target. When such a
    sequence has the same length as the records, it is a natural extra column.
    """
    params = getattr(data, "params", None)
    if not isinstance(params, dict):
        return {}
    columns = {}
    for name, value in params.items():
        if not isinstance(value, dict) or target not in value:
            continue
        entry = value[target]
        if isinstance(entry, str | bytes) or not isinstance(entry, Iterable):
            continue
        entry = np.asarray(entry)
        if entry.ndim == 1 and entry.shape[0] == length:
            columns[name] = entry
    return columns


def data_frames(data: Any) -> dict[Any, pd.DataFrame]:
    """Tabulate acquired data, one table per target.

    Args:
        data: a Qibocal ``Data`` instance, or any object with a ``data``
            dictionary mapping targets to arrays. A bare dictionary is also
            accepted.

    Returns:
        Mapping from target to its table. Targets without array-like content are
        skipped.
    """
    records = data.data if hasattr(data, "data") else data
    if not isinstance(records, dict):
        return {}
    frames = {}
    for target, array in records.items():
        try:
            frame = _records_frame(array)
        except (TypeError, ValueError):
            continue
        for name, column in _extra_columns(data, target, len(frame)).items():
            if name not in frame.columns:
                frame[name] = column
        frames[target] = frame
    return frames


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

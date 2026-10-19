"""Marimo interface.

Usage, inside a Marimo notebook::

    from qibocal_widgets.marimo import MarimoExecutor

    executor = MarimoExecutor.create(platform=platform, path="var/report")
    with executor:
        acquired = executor.acquire(bound, targets=[0, 1])
    acquired  # rendered: raw data tables

    completed = executor(bound)
    completed  # rendered: raw data tables and per-target reports

The :func:`show_data` and :func:`show_reports` helpers remain available for
explicit, finer-grained control.
"""

from ._core.marimo import (
    MarimoCompleted,
    MarimoExecutor,
    display,
    show_data,
    show_reports,
    wrap,
)

__all__ = [
    "MarimoCompleted",
    "MarimoExecutor",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]

"""Marimo interface.

Usage, inside a Marimo notebook::

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo

    executor = Executor.create(platform=platform, path="var/report", plugins=[Marimo()])
    with executor:
        acquired = executor.acquire(bound, targets=[0, 1])
    acquired  # rendered: raw data tables

    completed = executor(bound)
    completed  # rendered: raw data tables and per-target reports

The :func:`show_data` and :func:`show_reports` helpers remain available for
explicit, finer-grained control, and :func:`wrap` makes any execution
displayable.
"""

from ._core.marimo import (
    Marimo,
    display,
    show_data,
    show_reports,
    wrap,
)

__all__ = [
    "Marimo",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]

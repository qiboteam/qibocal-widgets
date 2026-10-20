"""Jupyter interface.

Usage, inside a Jupyter notebook::

    from qibocal_widgets import Executor
    from qibocal_widgets.jupyter import Jupyter

    executor = Executor.create(platform=platform, path="var/report", plugins=[Jupyter()])
    with executor:
        acquired = executor.acquire(bound, targets=[0, 1])
    acquired  # rendered: raw data tables

    completed = executor(bound)
    completed  # rendered: raw data tables and per-target reports

Rendering relies on ``ipywidgets``.

The :func:`show_data` and :func:`show_reports` helpers remain available for
explicit, finer-grained control, and :func:`wrap` makes any execution
displayable.
"""

from ._core.jupyter import (
    Jupyter,
    display,
    show_data,
    show_reports,
    wrap,
)

__all__ = [
    "Jupyter",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]

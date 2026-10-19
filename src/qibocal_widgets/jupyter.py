"""Jupyter interface.

Usage, inside a Jupyter notebook (JupyterLab, VS Code, ...)::

    from qibocal_widgets.jupyter import JupyterExecutor

    executor = JupyterExecutor.create(platform=platform, path="var/report")
    with executor:
        acquired = executor.acquire(bound, targets=[0, 1])
    acquired  # rendered: raw data tables

    completed = executor(bound)
    completed  # rendered: raw data tables and per-target reports

Rendering relies on ``ipywidgets``. The :func:`show_data` and
:func:`show_reports` helpers remain available for explicit control.
"""

from ._core.jupyter import (
    JupyterCompleted,
    JupyterExecutor,
    display,
    show_data,
    show_reports,
    wrap,
)

__all__ = [
    "JupyterCompleted",
    "JupyterExecutor",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]

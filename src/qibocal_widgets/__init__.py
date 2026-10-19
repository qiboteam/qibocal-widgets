"""Notebook integration for the Qibocal executor.

Two independent interfaces are provided, sharing the same core:

- :mod:`qibocal_widgets.marimo` (requires the ``marimo`` extra)
- :mod:`qibocal_widgets.jupyter` (requires the ``jupyter`` extra)

Each exposes an executor whose phases return executions that render
themselves in the notebook, together with explicit ``show_data`` and
``show_reports`` helpers.

This module only exposes the frontend-agnostic building blocks, useful to
customize the display or to support further frontends.
"""

from ._core.data import data_frames
from ._core.executor import WidgetExecutor, convert
from ._core.reports import Report, reports, reports_of
from ._core.version import __version__

__all__ = [
    "Report",
    "WidgetExecutor",
    "__version__",
    "convert",
    "data_frames",
    "reports",
    "reports_of",
]

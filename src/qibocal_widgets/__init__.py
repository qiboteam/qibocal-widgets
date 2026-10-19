"""Notebook integration for the Qibocal executor.

Two independent interfaces are provided, sharing the same core:

- :mod:`qibocal_widgets.marimo` (requires the ``marimo`` extra)
- :mod:`qibocal_widgets.jupyter` (requires the ``jupyter`` extra)

Each exposes an ``Executor`` subclass whose phases return executions that
render themselves in the notebook, together with explicit ``show_data`` and
``show_reports`` helpers.
"""

from ._core import Report, data_frames, reports, reports_of
from ._executor import WidgetExecutor, convert
from .version import __version__

__all__ = [
    "Report",
    "WidgetExecutor",
    "__version__",
    "convert",
    "data_frames",
    "reports",
    "reports_of",
]

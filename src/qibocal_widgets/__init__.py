"""Notebook integration for the Qibocal executor.

:class:`Executor` is a drop-in replacement of :class:`qibocal.Executor`,
extended through a list of plugins::

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo

    executor = Executor.create(platform="mock", path="var/report", plugins=[Marimo()])

Frontend plugins live in their own modules:

- :mod:`qibocal_widgets.marimo` (requires the ``marimo`` extra)
- :mod:`qibocal_widgets.jupyter` (requires the ``jupyter`` extra)

This module also exposes the frontend-agnostic building blocks, useful to
write further plugins.
"""

from ._core.data import data_frames
from ._core.executor import Completed, Executor, View, convert
from ._core.plugin import Plugin, PluginConflict
from ._core.reports import Report, reports, reports_of
from ._core.version import __version__

__all__ = [
    "Completed",
    "Executor",
    "Plugin",
    "PluginConflict",
    "Report",
    "View",
    "__version__",
    "convert",
    "data_frames",
    "reports",
    "reports_of",
]

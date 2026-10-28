"""Notebook integration for the Qibocal executor.

:class:`Executor` is a drop-in replacement of :class:`qibocal.Executor`,
composed of three roles:

- a :class:`Runner`, deciding where and how the steps run (:class:`Local`
  by default, or :class:`~qibocal_widgets.remote.Remote`);
- :class:`Middleware`, wrapping every step;
- :class:`Frontend` objects, displaying every output.

::

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo

    executor = Executor.create(platform="mock", path="var/report", frontends=[Marimo()])

Frontends live in their own modules:

- :mod:`qibocal_widgets.marimo` (requires the ``marimo`` extra)
- :mod:`qibocal_widgets.jupyter` (requires the ``jupyter`` extra)

Executions are recorded in a :class:`Session` folder, appended for as long as
the executor lives. Without an explicit ``path``, ``Executor.create`` and
``Executor.open`` use a fresh folder of the session's reports folder
(:func:`reports_dir`).

The calibration state of the platform can be explored and updated by path,
programmatically or with an interactive explorer (:class:`PlatformState`,
``executor.platform_state``).

This module also exposes the frontend-agnostic building blocks, useful to
write further runners, middleware, and frontends.
"""

from ._core.completed import Completed, View, convert
from ._core.data import data_frames
from ._core.executor import Executor
from ._core.frontend import Frontend
from ._core.middleware import Middleware
from ._core.output import reports_dir
from ._core.pending import Estimate, NotStartedError, Pending
from ._core.reports import Report, reports, reports_of
from ._core.runner import Local, Runner
from ._core.session import Session, SessionExists
from ._core.state import PlatformState, ReadOnlyState
from ._core.version import __version__

__all__ = [
    "Completed",
    "Estimate",
    "Executor",
    "Frontend",
    "Local",
    "Middleware",
    "NotStartedError",
    "Pending",
    "PlatformState",
    "ReadOnlyState",
    "Report",
    "Runner",
    "Session",
    "SessionExists",
    "View",
    "__version__",
    "convert",
    "data_frames",
    "reports",
    "reports_dir",
    "reports_of",
]

"""Refreshable view of the SLURM queue.

Created by :meth:`Remote.monitor <qibocal_widgets.remote.Remote.monitor>`, it
is a single widget, displayed natively by Jupyter and Marimo. Requires
``anywidget``, included in the ``jupyter`` and ``marimo`` extras.
"""

from ._core.remote.monitor import QueueMonitor

__all__ = ["QueueMonitor"]

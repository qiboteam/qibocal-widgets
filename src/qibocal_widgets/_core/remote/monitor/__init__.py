"""Refreshable view of the SLURM queue, for Jupyter and Marimo.

A single `anywidget <https://anywidget.dev>`_ serves both frontends, as the
platform state explorer. The queue is asked in Python, through the runner's
connection; the browser side renders the answer, and asks for refreshes, on
request or periodically while displayed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

if TYPE_CHECKING:
    from ..runner import Remote

__all__ = ["QueueMonitor"]

HERE = Path(__file__).parent


class QueueMonitor(anywidget.AnyWidget):
    """View of the queue of a :class:`~qibocal_widgets.remote.Remote` runner.

    Use :meth:`Remote.monitor <qibocal_widgets.remote.Remote.monitor>` to
    create one. The jobs of the remote user are highlighted, and those
    submitted by the runner tagged.
    """

    _esm = HERE / "monitor.js"
    _css = HERE / "monitor.css"

    partition = traitlets.Unicode("").tag(sync=True)
    """The partition shown (empty for all)."""
    user = traitlets.Unicode("").tag(sync=True)
    """The remote user the queue was asked as."""
    jobs = traitlets.List().tag(sync=True)
    """Displayed jobs, with the fields of Qibocamp, ``mine`` and ``ours``."""
    total = traitlets.Int(0).tag(sync=True)
    """Number of jobs in the answer, before filtering."""
    summary = traitlets.Dict().tag(sync=True)
    """Jobs by state, nodes by state, and partition availability."""
    fetched_at = traitlets.Unicode("").tag(sync=True)
    """When the queue was last asked (UTC)."""
    error = traitlets.Unicode("").tag(sync=True)
    """Why the queue could not be asked, if so."""
    interval = traitlets.Float(30.0).tag(sync=True)
    """Seconds between automatic refreshes while displayed (0: on request)."""
    mine = traitlets.Bool(False).tag(sync=True)
    """Show only the jobs of the remote user."""

    def __init__(
        self,
        runner: Remote,
        *,
        interval: float = 30.0,
        mine: bool = False,
        **options: Any,
    ):
        super().__init__(interval=interval, mine=mine)
        self.runner = runner
        """The runner whose connection is queried."""
        self.options = options
        """Options of :meth:`Remote.queue`."""
        self.answer: dict = {}
        """The last answer of the queue."""
        self.on_msg(self._message)
        self.observe(lambda _: self._show(), names=["mine"])
        self.refresh()

    def refresh(self) -> None:
        """Ask the queue again."""
        self.answer = self.runner.queue(**self.options)
        self._show()

    def _show(self) -> None:
        answer = self.answer
        jobs = answer.get("jobs", [])
        self.partition = answer.get("partition") or ""
        self.user = answer.get("user") or ""
        self.total = len(jobs)
        self.jobs = [job for job in jobs if job["mine"]] if self.mine else jobs
        self.summary = answer.get("summary", {})
        self.fetched_at = answer.get("fetched_at", "")
        self.error = answer.get("error") or ""

    def _message(self, widget, content: dict, buffers) -> None:
        if content.get("kind") == "refresh":
            self.refresh()

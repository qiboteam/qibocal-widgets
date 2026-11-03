"""The view of a running execution: its phase, and the progress of the
acquisition, from the estimates (see :mod:`..timeline`).

The browser runs the clocks and the bars, from the times of the events and the
kernel's clock, so that no update is needed between events.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

if TYPE_CHECKING:
    from ..pending import Pending

__all__ = ["ProgressView"]

ENDED = ("done", "failed", "ready")
"""States not shown by the view: the result, or the Run button."""

HERE = Path(__file__).parent


class ProgressView(anywidget.AnyWidget):
    """The state of a pending execution, as of its creation, or following it."""

    _esm = HERE / "progress.js"
    _css = HERE / "progress.css"

    name = traitlets.Unicode().tag(sync=True)
    status = traitlets.Unicode().tag(sync=True)
    phase = traitlets.Unicode("").tag(sync=True)
    submitted = traitlets.Float().tag(sync=True)
    """When submitted, in seconds since the epoch."""
    started = traitlets.Float(None, allow_none=True).tag(sync=True)
    """When the acquisition started running, if it did."""
    ended = traitlets.Float(None, allow_none=True).tag(sync=True)
    """When the acquisition ended, if it did."""
    executions = traitlets.List().tag(sync=True)
    """Executions on the platform, each with its batches."""
    clock = traitlets.Float().tag(sync=True)
    """The kernel's time, at the latest update: the browser's clock is
    corrected by it."""
    unfolded = traitlets.Bool(False).tag(sync=True)
    """Whether the list of estimates is unfolded (kept across updates)."""

    def __init__(
        self,
        pending: Pending,
        schedule: Callable[..., None] | None = None,
    ):
        """The view of a pending execution.

        Args:
            pending: the execution.
            schedule: if given, the view follows the execution, updating in
                place, calling ``schedule(function, pending)`` on each change
                (e.g. to run it on the kernel's thread); until it ends.
        """
        super().__init__(
            name=pending.name,
            unfolded=pending._view_state.get("unfolded", False),
            **_state(pending),
        )
        self.observe(
            lambda change: pending._view_state.update(unfolded=change["new"]),
            names=["unfolded"],
        )
        self._remove: Callable[[], None] | None = None
        if schedule is not None:
            self._remove = pending.on_change(lambda p: schedule(self._follow, p))

    def _follow(self, pending: Pending) -> None:
        if pending.status in ENDED:
            if self._remove is not None:
                self._remove()  # replaced by the result
                self._remove = None
            return
        with self.hold_sync():
            for name, value in _state(pending).items():
                setattr(self, name, value)


def _state(pending: Pending) -> dict[str, Any]:
    """The traits following the execution."""
    timeline = pending.timeline
    return {
        "status": pending.status,
        "phase": pending.phase or "",
        "submitted": pending.submitted_at.timestamp(),
        "started": _epoch(timeline.started),
        "ended": _epoch(timeline.ended),
        "executions": [
            {
                "estimate": execution.estimate,
                "started": execution.started.timestamp(),
                "measured": execution.measured,
                "batches": [
                    {
                        "estimate": batch.estimate,
                        "started": batch.started.timestamp(),
                        "measured": batch.measured,
                    }
                    for batch in execution.batches
                ],
            }
            for execution in timeline.executions
        ],
        "clock": time.time(),
    }


def _epoch(moment: datetime | None) -> Any:
    return None if moment is None else moment.timestamp()

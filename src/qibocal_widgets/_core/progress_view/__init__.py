"""The view of a running execution: its phase, and the progress of the
acquisition, from the estimates (see :mod:`..timeline`).

The browser runs the clocks and the bars, from the times of the events and the
kernel's clock, so that no update is needed between events.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

if TYPE_CHECKING:
    from ..pending import Pending

__all__ = ["ProgressView"]

HERE = Path(__file__).parent


class ProgressView(anywidget.AnyWidget):
    """The state of a pending execution, as of its creation."""

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
    """The kernel's time, when created: the browser's clock is corrected by it."""
    unfolded = traitlets.Bool(False).tag(sync=True)
    """Whether the list of estimates is unfolded (kept across updates)."""

    def __init__(self, pending: Pending):
        timeline = pending.timeline
        super().__init__(
            name=pending.name,
            status=pending.status,
            phase=pending.phase or "",
            submitted=pending.submitted_at.timestamp(),
            started=_epoch(timeline.started),
            ended=_epoch(timeline.ended),
            executions=[
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
            clock=time.time(),
            unfolded=pending._view_state.get("unfolded", False),
        )
        self.observe(
            lambda change: pending._view_state.update(unfolded=change["new"]),
            names=["unfolded"],
        )


def _epoch(moment: datetime | None) -> Any:
    return None if moment is None else moment.timestamp()

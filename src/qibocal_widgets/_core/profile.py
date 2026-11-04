"""Where the time of an execution went: the steps between its events.

The marks come from the timeline of the acquisition (remote stages, estimates,
its end) and from the history of the execution (its statuses and phases).
Each step is named after what happens until its mark.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .timeline import ACQUIRED, BATCH, EXECUTION, STAGE, STARTED

if TYPE_CHECKING:
    from .pending import Pending

__all__ = ["steps"]

STAGES = {
    "environment started": "start of Python, in the environment",
    "imported": "imports (qibocal, qibolab, drivers)",
    "platform created": "platform creation",
    "connected": "connection to the instruments",
    "disconnected": "disconnection",
    "encoded": "data encoding",
}
"""Steps until each stage of a remote job."""


def steps(pending: Pending) -> list[tuple[str, datetime, float]]:
    """The steps of an execution: ``(name, mark, seconds since the previous)``."""
    marks: list[tuple[datetime, str]] = []
    remote = any(event.kind == STAGE for event in pending.timeline.events)
    current = None  # the execution or batch running
    executions = 0
    for event in pending.timeline.events:
        if event.kind == STARTED:
            label = "queue and dispatch (ssh, srun)" if remote else "waiting to start"
        elif event.kind == STAGE:
            label = STAGES.get(event.name, event.name or "stage")
        elif event.kind == EXECUTION:
            executions += 1
            batches = 0
            label = current or "preparation, until the first execution"
            current = f"execution {executions}"
        elif event.kind == BATCH:
            batches += 1
            if batches == 1:
                label = f"{current}: preparation, until its first batch"
            else:
                label = f"batch {executions}.{batches - 1}"
            current = f"batch {executions}.{batches}"
        elif event.kind == ACQUIRED:
            label = current or "acquisition"
        else:
            continue
        marks.append((event.at, label))

    # the executor's steps: receiving the data, then each phase of the
    # processing, ending when the next one starts
    previous: tuple[str | None, str | None] = (None, None)
    for at, status, phase in pending.history:
        before_status, before_phase = previous
        if status == "processing" and before_status == "acquiring" and remote:
            marks.append((at, "data transfer and decoding"))
        if (
            before_status == "processing"
            and before_phase is not None
            and (status, phase) != previous
        ):
            marks.append((at, before_phase))
        previous = (status, phase)
    if pending.finished_at is not None and previous[1] is not None:
        marks.append((pending.finished_at, previous[1]))

    marks.sort(key=lambda mark: mark[0])
    rows = []
    previous = pending.submitted_at
    for at, label in marks:
        rows.append((label, at, max(0.0, (at - previous).total_seconds())))
        previous = at
    return rows

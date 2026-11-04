"""What happened during an acquisition, from its events.

Estimates come at two levels: qibolab's, once per ``platform.execute()`` call,
for the whole call, and the driver's (e.g. Qblox), once per batch of the call,
before it runs. An acquisition may execute the platform any number of times,
not known in advance. Events are grouped accordingly: executions, each with its
batches, and measured durations are derived from the times between events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["Batch", "Event", "Execution", "Timeline"]

STARTED = "started"
"""The acquisition started running (e.g. a queued job reached its node)."""
EXECUTION = "execution"
"""A ``platform.execute()`` call starting, with qibolab's estimate."""
BATCH = "batch"
"""A batch of the current execution starting, with the driver's estimate."""
ACQUIRED = "acquired"
"""The acquisition ended (remotely: its data are being transferred)."""
STAGE = "stage"
"""A stage of a remote job reached (e.g. ``imported``), with its name."""
KINDS = (STARTED, EXECUTION, BATCH, ACQUIRED, STAGE)


@dataclass(frozen=True)
class Event:
    """Something happening while acquiring."""

    kind: str
    """``started``, ``execution``, ``batch``, or ``acquired``."""
    at: datetime
    """When it was received (UTC)."""
    seconds: float | None = None
    """The estimated duration, for ``execution`` and ``batch`` events."""
    name: str | None = None
    """The stage reached, for ``stage`` events."""


@dataclass(frozen=True)
class Batch:
    """A batch of an execution, as estimated by the driver."""

    estimate: float
    started: datetime
    measured: float | None = None
    """Seconds until the next event: the run of the batch, with the overhead
    of fetching its results, and of preparing the next one."""


@dataclass(frozen=True)
class Execution:
    """A ``platform.execute()`` call, as estimated by qibolab."""

    estimate: float
    started: datetime
    measured: float | None = None
    """Seconds until the next execution, or the end of the acquisition."""
    batches: list[Batch] = field(default_factory=list)

    @property
    def refined(self) -> float | None:
        """The driver's estimate of the execution, the sum of its batches, if
        estimated (complete once the execution is over)."""
        if not self.batches:
            return None
        return sum(batch.estimate for batch in self.batches)


class Timeline:
    """The events of an acquisition, grouped in executions and batches."""

    def __init__(self, events: list[Event] | None = None):
        self.events: list[Event] = list(events or [])

    @property
    def started(self) -> datetime | None:
        """When the acquisition started running, if known."""
        for event in self.events:
            if event.kind in (STARTED, EXECUTION):
                return event.at
        return None

    @property
    def ended(self) -> datetime | None:
        """When the acquisition ended, if it did."""
        for event in reversed(self.events):
            if event.kind == ACQUIRED:
                return event.at
        return None

    @property
    def executions(self) -> list[Execution]:
        """The executions, with their batches, and the durations measured."""
        marks = [e for e in self.events if e.kind in (EXECUTION, BATCH, ACQUIRED)]
        executions: list[dict[str, Any]] = []
        for index, event in enumerate(marks):
            following = marks[index + 1].at if index + 1 < len(marks) else None
            if event.kind == EXECUTION:
                executions.append(
                    {"estimate": event.seconds, "started": event.at, "batches": []}
                )
            elif event.kind == BATCH:
                if not executions:
                    # a driver estimate without qibolab's: its own execution
                    executions.append(
                        {"estimate": event.seconds, "started": event.at, "batches": []}
                    )
                executions[-1]["batches"].append(
                    Batch(event.seconds, event.at, _between(event.at, following))
                )
        result = []
        for index, execution in enumerate(executions):
            following = (
                executions[index + 1]["started"]
                if index + 1 < len(executions)
                else self.ended
            )
            result.append(
                Execution(
                    estimate=execution["estimate"],
                    started=execution["started"],
                    measured=_between(execution["started"], following),
                    batches=execution["batches"],
                )
            )
        return result

    def estimated(self) -> float:
        """The sum of the estimates so far: of each execution, refined by its
        batches once complete (the current one has more batches to come)."""
        executions = self.executions
        return sum(
            execution.refined
            if execution.refined is not None and execution.measured is not None
            else execution.estimate
            for execution in executions
        )

    def document(self) -> list[dict[str, Any]]:
        """The events, as JSON values (times in seconds since the epoch)."""
        return [
            {
                "kind": e.kind,
                "at": e.at.timestamp(),
                "seconds": e.seconds,
                "name": e.name,
            }
            for e in self.events
        ]


def _between(start: datetime, end: datetime | None) -> float | None:
    return None if end is None else (end - start).total_seconds()

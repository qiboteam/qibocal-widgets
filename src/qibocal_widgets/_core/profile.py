"""Where the time of an execution went: the steps between its events.

The marks come from the timeline of the acquisition (remote stages, estimates,
its end) and from the history of the execution (its statuses and phases).
Each step is named after what happens until its mark.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from .timeline import ACQUIRED, BATCH, EXECUTION, STAGE, STARTED, Event, Timeline

__all__ = ["Trace", "report", "steps", "table", "versions"]

STAGES = {
    "environment started": "start of Python, in the environment",
    "imported": "imports (qibocal, qibolab, drivers)",
    "platform created": "platform creation",
    "connected": "connection to the instruments",
    "disconnected": "disconnection",
    "encoded": "data encoding",
    "followed": "until following the job again (earlier steps replayed)",
    "agent ready": "agent start (once per session)",
}
"""Steps until each stage of a remote job."""

IDLE = 0.1
"""Seconds between the steps of a blocking execution shown as a step."""


class Trace:
    """What happened during an execution, for its profile.

    Background executions are their own trace (:class:`Pending
    <qibocal_widgets.Pending>`); blocking calls record one of these, shared by
    the steps of the execution, also when run separately.
    """

    def __init__(self) -> None:
        self.timeline = Timeline()
        self.history: list[tuple[datetime, str, str | None]] = []
        self.started_at = datetime.now(UTC)
        self.finished_at: datetime | None = None
        self.context: dict[str, Any] = {}
        """Where and how it ran (see :func:`report`)."""
        self._view_state: dict[str, Any] = {}

    @property
    def _origin(self) -> datetime:
        return self.started_at

    def event(self, kind: str, seconds: float | None = None, name: str | None = None):
        """Record an event of the acquisition."""
        self.timeline.events.append(Event(kind, datetime.now(UTC), seconds, name))

    def phase(self, status: str, phase: str | None = None) -> None:
        """Record a change of status and phase; ``idle`` between calls."""
        now = datetime.now(UTC)
        self.history.append((now, status, phase))
        if status == "idle":
            self.finished_at = now


def steps(pending: Any) -> list[tuple[str, datetime, float]]:
    """The steps of an execution (a :class:`Trace`, or a pending execution):
    ``(name, mark, seconds since the previous)``."""
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
    idle_since = pending._origin
    for at, status, phase in pending.history:
        before_status, before_phase = previous
        if status == "processing" and before_status == "acquiring" and remote:
            marks.append((at, "data transfer and decoding"))
        if status == "processing" and before_status == "idle":
            idle = (at - idle_since).total_seconds()
            if idle >= IDLE:  # a step run later, e.g. from another cell
                marks.append((at, "between calls"))
        if status == "idle":
            idle_since = at
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
    previous = pending._origin
    for at, label in marks:
        rows.append((label, at, max(0.0, (at - previous).total_seconds())))
        previous = at
    return rows


def table(trace: Any) -> Any:
    """The steps of an execution, as a pandas ``DataFrame``: step, the seconds
    it took, and when it ended, since the start."""
    import pandas as pd

    origin = trace._origin
    return pd.DataFrame(
        [
            {
                "step": label,
                "took (s)": round(took, 3),
                "at (s)": round((at - origin).total_seconds(), 3),
            }
            for label, at, took in steps(trace)
        ],
        columns=["step", "took (s)", "at (s)"],
    )


def versions() -> dict[str, str]:
    """Versions of the packages of the current environment, with their
    commits when installed from a repository."""
    from .remote.worker import package_versions

    return package_versions()


def context_lines(trace: Any) -> list[str]:
    """The context of a report: setup, and versions (no host names)."""
    context = getattr(trace, "context", {})
    lines = []
    setup = [context["setup"]] if context.get("setup") else []
    if context.get("agent"):
        setup.append(f"agent {context['agent']}")
    if context.get("followed"):
        setup.append("followed after a reconnection")
    if setup:
        lines.append("setup: " + ", ".join(setup))
    local = context.get("local") or versions()
    lines.append("local: " + ", ".join(f"{k} {v}" for k, v in local.items()))
    if context.get("remote"):
        remote = context["remote"]
        lines.append("remote: " + ", ".join(f"{k} {v}" for k, v in remote.items()))
    return lines


def report(trace: Any, title: str, fmt: str = "markdown") -> str:
    """The profile of an execution, to paste in an issue: a Markdown table, or
    CSV (with the context as comments), with the context of the execution."""
    rows = table(trace)
    started = f"{trace._origin:%Y-%m-%d %H:%M} UTC"
    context = context_lines(trace)
    if fmt == "csv":
        out = io.StringIO()
        out.write(f"# {title}, {started}\n")
        out.writelines(f"# {line}\n" for line in context)
        rows.to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
        return out.getvalue()
    lines = [f"**{title}** · {started}", ""]
    lines += [f"- {line}" for line in context]
    lines += ["", "| step | took (s) | at (s) |", "|---|---:|---:|"]
    lines += [
        f"| {row.step} | {row._2:.3f} | {row._3:.3f} |" for row in rows.itertuples()
    ]
    return "\n".join(lines) + "\n"

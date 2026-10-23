"""The SLURM queue, as seen through a connection.

The query mirrors Qibocamp's (``qibocamp.remote.slurm``): the same
``squeue``, ``sinfo`` and ``whoami`` commands, in a single remote shell
command, and the same parsed fields, so that both tools show the queue alike.
Qibocamp is not a dependency (it is a server application), hence the
mirror: if the query moves to a package shared by both, this module becomes a
re-export.

The queue is asked once per call: how often to ask is the caller's decision,
and every call costs the controller something.
"""

from __future__ import annotations

import shlex
import subprocess
from datetime import UTC, datetime
from typing import Any

from .config import Connection
from .transport import JOB_PREFIX, SSH_OPTIONS

__all__ = [
    "JOB_PREFIX",
    "SINFO_FORMAT",
    "SQUEUE_FORMAT",
    "parse_sinfo",
    "parse_squeue",
    "query",
    "shell_script",
]

SEPARATOR = "---QIBOCAMP-QUEUE---"
"""Separates the answers of the three commands, as in Qibocamp."""
SQUEUE_FORMAT = "%i|%P|%j|%u|%T|%M|%l|%D|%R|%Q|%V|%S"
"""Job fields: id, partition, name, user, state, time used, time limit, node
count, nodes or reason, priority, submitted, start."""
SINFO_FORMAT = "%P|%a|%D|%T"
"""Node group fields: partition, availability, node count, state."""


def squeue_command(
    partition: str | None = None,
    user: str | None = None,
    states: list[str] | None = None,
) -> list[str]:
    command = ["squeue", "-h", "-o", SQUEUE_FORMAT, "--sort=-p,i"]
    if partition:
        command += ["-p", partition]
    if user:
        command += ["-u", user]
    if states:
        command += ["-t", ",".join(states)]
    return command


def sinfo_command(partition: str | None = None) -> list[str]:
    command = ["sinfo", "-h", "-o", SINFO_FORMAT]
    if partition:
        command += ["-p", partition]
    return command


def shell_script(
    partition: str | None = None,
    user: str | None = None,
    states: list[str] | None = None,
) -> str:
    """The three questions as one shell command, their answers separated."""
    parts = [
        shlex.join(squeue_command(partition, user, states)),
        f"printf '\\n{SEPARATOR}\\n'",
        shlex.join(sinfo_command(partition)),
        f"printf '\\n{SEPARATOR}\\n'",
        "whoami",
    ]
    return "; ".join(parts)


def parse_squeue(text: str) -> list[dict[str, Any]]:
    """Jobs, with the fields of Qibocamp."""
    jobs = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) < 9:
            continue
        fields += [""] * (12 - len(fields))
        (
            job_id,
            partition,
            name,
            user,
            state,
            time_used,
            time_limit,
            node_count,
            nodes_or_reason,
            priority,
            submitted,
            start,
        ) = fields[:12]
        pending = state.upper().startswith("PENDING")
        try:
            count = int(node_count)
        except ValueError:
            count = 0
        jobs.append(
            {
                "id": job_id,
                "partition": partition,
                "name": name,
                "user": user,
                "state": state,
                "time": time_used,
                "time_limit": time_limit,
                "node_count": count,
                "nodes": "" if pending else nodes_or_reason,
                "reason": nodes_or_reason.strip("()") if pending else "",
                "priority": priority,
                "submitted": submitted,
                "start": "" if start == "N/A" else start,
            }
        )
    return jobs


def parse_sinfo(text: str) -> list[dict[str, Any]]:
    """Node groups by partition and state; the default partition loses its asterisk."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) < 4:
            continue
        partition, available, count, state = fields[:4]
        try:
            nodes = int(count)
        except ValueError:
            nodes = 0
        rows.append(
            {
                "partition": partition.rstrip("*"),
                "default": partition.endswith("*"),
                "available": available,
                "nodes": nodes,
                "state": state,
            }
        )
    return rows


def summarize(
    jobs: list[dict[str, Any]], nodes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Jobs by state, nodes by state."""
    by_state: dict[str, int] = {}
    for job in jobs:
        key = job["state"].split()[0].upper() if job["state"] else "UNKNOWN"
        by_state[key] = by_state.get(key, 0) + 1
    node_states: dict[str, int] = {}
    for row in nodes:
        key = row["state"].rstrip("*~#$@^!%").upper()
        node_states[key] = node_states.get(key, 0) + row["nodes"]
    return {
        "jobs": by_state,
        "nodes": node_states,
        "total_jobs": len(jobs),
        "total_nodes": sum(node_states.values()),
        "available": any(row["available"] == "up" for row in nodes) if nodes else None,
    }


def _split(output: str) -> tuple[str, str, str]:
    parts = output.split(SEPARATOR)
    while len(parts) < 3:
        parts.append("")
    tail = parts[2].strip()
    return parts[0], parts[1], tail.splitlines()[-1].strip() if tail else ""


def query(
    connection: Connection,
    *,
    partition: str | None = None,
    user: str | None = None,
    states: list[str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Ask the queue once, through the connection, and parse the answer.

    Args:
        connection: over SSH if it has a destination, locally otherwise.
        partition: defaults to the partition of the connection, so that the
            jobs ahead of its own are shown.
        user: restrict to the jobs of a user.
        states: restrict to some job states (e.g. ``["PENDING"]``).
        timeout: seconds to wait for the answer.

    Returns:
        The jobs and node groups (with the fields of Qibocamp), their
        summary, the remote user (``whoami``), when the queue was asked, and
        the error, if the queue could not be asked. Jobs carry two more flags:
        ``mine`` (submitted by the remote user) and ``ours`` (submitted by
        the remote runner).
    """
    partition = partition if partition is not None else connection.queue
    script = shell_script(partition, user, states)
    if connection.ssh is not None:
        options, destination = connection.destination()
        command = ["ssh", *options, *SSH_OPTIONS, destination, script]
    else:
        # the system shell by its path: PATH may be anything
        command = ["/bin/sh", "-c", script]
    error = None
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        output, stderr, code = completed.stdout, completed.stderr, completed.returncode
    except FileNotFoundError as exception:
        output, stderr, code = "", str(exception), 127
    except subprocess.TimeoutExpired:
        output, stderr, code = "", f"The queue did not answer within {timeout:g} s", -1
    squeue_text, sinfo_text, whoami = _split(output)
    jobs = parse_squeue(squeue_text)
    nodes = parse_sinfo(sinfo_text)
    if code != 0 and not jobs and not nodes:
        error = stderr.strip() or f"The queue command failed ({code})"
    for job in jobs:
        job["mine"] = bool(whoami) and job["user"] == whoami
        job["ours"] = job["name"].startswith(JOB_PREFIX)
    return {
        "partition": partition,
        "user": whoami or None,
        "jobs": jobs,
        "nodes": nodes,
        "summary": summarize(jobs, nodes),
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "error": error,
    }

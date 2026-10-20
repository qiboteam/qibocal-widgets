"""Command lines reaching the remote machine, and job exchange.

Commands follow the conventions of qibocal-report: plain ``ssh`` and ``srun``
subprocesses, with the worker source passed inline. The job is written on the
worker's standard input, and the outcome read from its standard output.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

from . import worker
from .config import Connection

__all__ = ["RemoteError", "command", "run", "slurm_arguments", "source"]

SSH_OPTIONS = [
    "-T",
    "-o",
    "BatchMode=yes",
    "-o",
    "ServerAliveInterval=30",
    "-o",
    "ServerAliveCountMax=3",
]
"""Options of every SSH connection: no terminal, no interactive prompt."""

FORBIDDEN_SLURM = {
    "-o",
    "--output",
    "-e",
    "--error",
    "-i",
    "--input",
    "--pty",
    "-N",
    "--nodes",
    "-n",
    "--ntasks",
}
"""``srun`` options conflicting with the exchange through standard streams."""


class RemoteError(RuntimeError):
    """A remote step failed."""

    TAIL = 20
    """Lines of details included in the message."""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.message = message
        self.details = details
        """Remote traceback, or standard error, when available."""

    def __str__(self) -> str:
        lines = self.details.strip().splitlines()[-self.TAIL :]
        if not lines:
            return self.message
        return "\n".join([self.message, "", *lines])


def source() -> str:
    """Worker source, made aware of itself to run again in its environment."""
    text = Path(worker.__file__).read_text()
    return f"WORKER_SOURCE = {text!r}\n{text}"


def slurm_arguments(options: str | None) -> list[str]:
    """Validated further ``srun`` options.

    Raises:
        ValueError: for options redirecting the standard streams, or changing
            the number of nodes or tasks (one task on one node is enforced).
    """
    arguments = shlex.split(options or "")
    for argument in arguments:
        name = argument.split("=", 1)[0]
        if name in FORBIDDEN_SLURM:
            raise ValueError(f"The srun option {name} is not supported")
    return arguments


def _workdir(path: str) -> str:
    """Shell fragment changing to a directory, expanding a leading ``~``."""
    if path == "~":
        return 'cd "$HOME"'
    if path.startswith("~/"):
        return f'cd "$HOME"/{shlex.quote(path[2:])}'
    return f"cd {shlex.quote(path)}"


def command(connection: Connection, *, compute: bool) -> list[str]:
    """Command line running the worker.

    Args:
        connection: how to reach the remote machine.
        compute: whether the step needs the instruments, in which case it goes
            through the queue when one is configured.
    """
    inner = ["python3", "-u", "-c", source()]
    if compute and connection.scheduled:
        srun = ["srun", "--unbuffered"]
        if connection.queue is not None:
            srun += ["--partition", connection.queue]
        srun += slurm_arguments(connection.slurm)
        srun += ["--nodes=1", "--ntasks=1"]
        inner = srun + inner
    if connection.ssh is None:
        if connection.workdir is not None:
            return [
                "sh",
                "-c",
                f"{_workdir(connection.workdir)} && exec {shlex.join(inner)}",
            ]
        return inner
    options, destination = connection.destination()
    remote = shlex.join(inner)
    if connection.workdir is not None:
        remote = f"{_workdir(connection.workdir)} && {remote}"
    return ["ssh", *options, *SSH_OPTIONS, destination, remote]


def run(connection: Connection, job: dict, *, compute: bool) -> dict:
    """Execute a job remotely, and return its outcome.

    Raises:
        RemoteError: if the worker reports a failure, or produces no outcome.
    """
    job = {"venv": connection.venv, **job}
    try:
        process = subprocess.run(
            command(connection, compute=compute),
            input=json.dumps(job),
            capture_output=True,
            text=True,
            timeout=connection.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RemoteError(
            f"Remote {job['action']} timed out after {connection.timeout} s"
        ) from error
    outcome = None
    for line in process.stdout.splitlines():
        if line.startswith(worker.MARKER):
            outcome = json.loads(line[len(worker.MARKER) :])
    if outcome is None:
        raise RemoteError(
            f"Remote {job['action']} exited with code {process.returncode} "
            "and no outcome",
            process.stderr,
        )
    if not outcome.get("ok"):
        raise RemoteError(
            f"Remote {job['action']} failed: {outcome.get('error')}",
            outcome.get("traceback") or process.stderr,
        )
    return outcome

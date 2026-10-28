"""Command lines reaching the remote machine, and job exchange.

Commands follow the conventions of Qibocamp: plain ``ssh`` and ``srun``
subprocesses, with the worker source passed inline. The job is written on the
worker's standard input, and the outcome read from its standard output.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import signal
import subprocess
import threading
from pathlib import Path

from .. import progress
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

JOB_PREFIX = "qibocal-widgets-"
"""Name prefix of the queued jobs, followed by their action."""

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


def command(
    connection: Connection, *, compute: bool, action: str = "step"
) -> list[str]:
    """Command line running the worker.

    Args:
        connection: how to reach the remote machine.
        compute: whether the step needs the instruments, in which case it goes
            through the queue when one is configured.
        action: the job action, naming queued jobs (``qibocal-widgets-<action>``)
            unless the ``slurm`` options set a name, so that they can be
            recognized in the queue.
    """
    inner = ["python3", "-u", "-c", source()]
    if compute and connection.scheduled:
        srun = ["srun", "--unbuffered"]
        if connection.queue is not None:
            srun += ["--partition", connection.queue]
        extra = slurm_arguments(connection.slurm)
        named = any(
            argument == "-J" or argument.split("=", 1)[0] == "--job-name"
            for argument in extra
        )
        if not named:
            srun += ["--job-name", f"{JOB_PREFIX}{action}"]
        srun += extra
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


def _kill(process: subprocess.Popen) -> None:
    """Kill a process and its children (its process group)."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)


def run(connection: Connection, job: dict, *, compute: bool) -> dict:
    """Execute a job remotely, and return its outcome.

    Duration estimates streamed by the worker are reported, as they arrive,
    with :func:`progress.report <qibocal_widgets._core.progress.report>`.

    Raises:
        RemoteError: if the worker reports a failure, or produces no outcome.
    """
    job = {"venv": connection.venv, **job}
    if connection.platforms_dir is not None:
        job.setdefault("platforms_dir", connection.platforms_dir)
    process = subprocess.Popen(
        command(connection, compute=compute, action=job["action"]),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # killed with its children, on timeout
    )
    # read while the job runs, for the estimates; standard error in a thread,
    # so that neither pipe fills up
    errors: list[str] = []
    reader = threading.Thread(target=lambda: errors.extend(process.stderr))
    reader.start()
    expired = threading.Event()
    timer = None
    if connection.timeout is not None:
        timer = threading.Timer(
            connection.timeout, lambda: (expired.set(), _kill(process))
        )
        timer.start()
    outcome = None
    try:
        with contextlib.suppress(BrokenPipeError):
            process.stdin.write(json.dumps(job))
            process.stdin.close()
        for line in process.stdout:
            if line.startswith(worker.MARKER):
                outcome = json.loads(line[len(worker.MARKER) :])
            elif line.startswith(worker.PROGRESS):
                with contextlib.suppress(ValueError, KeyError, TypeError):
                    progress.report(
                        float(json.loads(line[len(worker.PROGRESS) :])["estimate"])
                    )
        process.wait()
    finally:
        if timer is not None:
            timer.cancel()
        if process.poll() is None:
            _kill(process)
            process.wait()
        reader.join()
    if expired.is_set():
        raise RemoteError(
            f"Remote {job['action']} timed out after {connection.timeout} s"
        )
    if outcome is None:
        raise RemoteError(
            f"Remote {job['action']} exited with code {process.returncode} "
            "and no outcome",
            "".join(errors),
        )
    if not outcome.get("ok"):
        raise RemoteError(
            f"Remote {job['action']} failed: {outcome.get('error')}",
            outcome.get("traceback") or "".join(errors),
        )
    return outcome

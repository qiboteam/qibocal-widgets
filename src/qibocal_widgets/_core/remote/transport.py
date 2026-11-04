"""Command lines reaching the remote machine, and job exchange.

Commands follow the conventions of Qibocamp: plain ``ssh`` and ``srun``
subprocesses, with the worker source passed inline. The job is written on the
worker's standard input, and the outcome read from its standard output.
"""

from __future__ import annotations

import atexit
import collections
import contextlib
import itertools
import json
import os
import queue
import shlex
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .. import progress
from . import worker
from .config import Connection

__all__ = [
    "Agent",
    "RemoteError",
    "agent",
    "close_agents",
    "command",
    "forget",
    "run",
    "run_once",
    "slurm_arguments",
    "source",
]

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

    def __init__(self, message: str, details: str = "", *, ended: bool = True):
        super().__init__(message)
        self.message = message
        self.details = details
        """Remote traceback, or standard error, when available."""
        self.ended = ended
        """Whether the job is over: ``False`` when only the connection to it
        was lost (a detached job may still be running)."""

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
        inner = srun_prefix(connection, action) + inner
    return wrap(connection, inner)


def srun_prefix(connection: Connection, action: str = "step") -> list[str]:
    """The ``srun`` command of a queued job, before the command it runs.

    One task on one node, named ``qibocal-widgets-<action>`` unless the
    ``slurm`` options name it. Blocking: the allocation lasts as long as the
    job, and no longer.
    """
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
    return srun


def wrap(connection: Connection, inner: list[str]) -> list[str]:
    """A command line run on the remote machine: through SSH, in the working
    directory, if configured."""
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


def run(
    connection: Connection,
    job: dict,
    *,
    compute: bool,
    name: str | None = None,
    follow: str | None = None,
) -> dict:
    """Execute a job remotely, through the connection's agent (see
    :class:`Agent`), or, for installations, or with ``agent=False``, in a
    process of its own (see :func:`run_once`).

    Args:
        name: for queued jobs, run detached under this name: the job survives
            the agent and the client, and can be followed again.
        follow: instead of running ``job``, follow the detached job of this
            name, until its outcome.
    """
    job = {"venv": connection.venv, **job}
    if connection.platforms_dir is not None:
        job.setdefault("platforms_dir", connection.platforms_dir)
    if connection.agent and job["action"] != "install":
        return agent(connection).run(job, compute=compute, name=name, follow=follow)
    if follow is not None:
        raise RemoteError("Following detached jobs requires the agent")
    return run_once(connection, job, compute=compute)


def forget(connection: Connection, name: str) -> None:
    """Remove the folder of a detached job, once fetched."""
    if connection.agent:
        with contextlib.suppress(RemoteError, OSError):
            agent(connection).forget(name)


def run_once(connection: Connection, job: dict, *, compute: bool) -> dict:
    """Execute a job remotely, and return its outcome.

    Events streamed by the worker (duration estimates, start and end of the
    acquisition) are reported, as they arrive,
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
                _progress(line)
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
    return _outcome(job, outcome, "".join(errors))


def _progress(line: str) -> None:
    """Report an event line of the worker."""
    with contextlib.suppress(ValueError, KeyError, TypeError):
        event = json.loads(line[len(worker.PROGRESS) :])
        seconds = event.get("estimate")
        progress.report(
            str(event.get("kind", "execution")),
            None if seconds is None else float(seconds),
            event.get("name"),
        )


def _outcome(job: dict, outcome: dict, errors: str) -> dict:
    """The outcome of a job, raising its failure."""
    if not outcome.get("ok"):
        raise RemoteError(
            f"Remote {job['action']} failed: {outcome.get('error')}",
            outcome.get("traceback") or errors,
        )
    return outcome


# -- agents ------------------------------------------------------------------------


EXITED = "The remote agent exited"


class Agent:
    """A warm worker on the remote machine, outside of the queue.

    Started once per connection, it serves every job (see
    :func:`~.worker.agent`): jobs not needing the instruments at once, with
    imports done once; acquisitions through the queue as ``srun`` jobs, each
    holding its allocation only while it runs. It lives as long as its
    process (its SSH connection, if any): it exits with the client.
    """

    STARTUP = 600.0
    """Seconds to wait for the agent to start (imports included)."""

    def __init__(self, connection: Connection):
        self.connection = connection
        command = wrap(
            connection, ["python3", "-u", "-c", source(), "agent", connection.venv]
        )
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self._lock = threading.Lock()
        self._jobs: dict[str, queue.Queue[str | None]] = {}
        self._ids = itertools.count()
        self._ready = threading.Event()
        self.versions: dict[str, str] = {}
        """Versions of the packages of the remote environment."""
        self.started = time.monotonic()
        self._error: str | None = None
        self._errors: collections.deque[str] = collections.deque(maxlen=200)
        threading.Thread(target=self._read, daemon=True).start()
        self._stderr = threading.Thread(
            target=lambda: self._errors.extend(self._process.stderr), daemon=True
        )
        self._stderr.start()
        if not self._ready.wait(self.STARTUP) or not self.alive:
            self.close()
            self._stderr.join(1)
            code = self._process.returncode
            reason = self._error
            if reason is None or reason == EXITED:
                reason = (
                    "The remote agent did not start"
                    if code is None
                    else f"The remote agent exited with code {code}"
                )
            raise RemoteError(reason, "".join(self._errors))

    @property
    def alive(self) -> bool:
        """Whether the agent can still serve jobs."""
        return self._process.poll() is None and self._error is None

    def _read(self) -> None:
        for line in self._process.stdout:
            line = line.rstrip("\n")
            if not line.startswith(worker.AGENT):
                continue
            rest = line[len(worker.AGENT) :]
            if rest == "ready" or rest.startswith("ready "):
                with contextlib.suppress(ValueError):
                    self.versions = json.loads(rest[len("ready ") :] or "{}")
                self._ready.set()
            elif rest.startswith("missing "):
                self._error = json.loads(rest[len("missing ") :])
                self._ready.set()
            else:
                job, _, payload = rest.partition(" ")
                with self._lock:
                    channel = self._jobs.get(job)
                if channel is not None:
                    channel.put(payload)
        # gone: the jobs in flight are lost
        self._error = self._error or EXITED
        self._ready.set()
        with self._lock:
            channels = list(self._jobs.values())
        for channel in channels:
            channel.put(None)

    def _send(self, request: dict) -> None:
        with self._lock:
            self._process.stdin.write(json.dumps(request) + "\n")
            self._process.stdin.flush()

    def forget(self, name: str) -> None:
        """Remove the folder of a detached job."""
        self._send({"forget": name})

    def run(
        self,
        job: dict,
        *,
        compute: bool,
        name: str | None = None,
        follow: str | None = None,
    ) -> dict:
        """Execute a job, and return its outcome, as :func:`run`."""
        job_id = str(next(self._ids))
        channel: queue.Queue[str | None] = queue.Queue()
        with self._lock:
            self._jobs[job_id] = channel
        srun = (
            srun_prefix(self.connection, job["action"])
            if compute and self.connection.scheduled
            else None
        )
        timeout = self.connection.timeout
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            if follow is not None:
                request = {"id": job_id, "follow": follow}
            else:
                request = {"id": job_id, "job": job, "compute": compute, "srun": srun}
                if srun is not None:
                    request["name"] = name or uuid.uuid4().hex
            try:
                self._send(request)
            except (BrokenPipeError, OSError) as error:
                raise RemoteError(
                    f"Remote {job['action']}: the agent is gone",
                    "".join(self._errors),
                    ended=False,
                ) from error
            while True:
                remaining = None if deadline is None else deadline - time.monotonic()
                try:
                    if remaining is not None and remaining <= 0:
                        raise queue.Empty
                    payload = channel.get(timeout=remaining)
                except queue.Empty:
                    with contextlib.suppress(OSError):
                        self._send({"cancel": job_id})
                    raise RemoteError(
                        f"Remote {job['action']} timed out after {timeout} s"
                    ) from None
                if payload is None:
                    raise RemoteError(
                        f"Remote {job['action']}: the agent exited",
                        "".join(self._errors),
                        ended=False,
                    )
                if payload.startswith(worker.MARKER):
                    return _outcome(job, json.loads(payload[len(worker.MARKER) :]), "")
                if payload.startswith(worker.PROGRESS):
                    _progress(payload)
        finally:
            with self._lock:
                self._jobs.pop(job_id, None)

    def close(self) -> None:
        """Stop the agent (and the queued jobs it launched)."""
        with contextlib.suppress(OSError):
            self._process.stdin.close()
        try:
            self._process.wait(5)
        except subprocess.TimeoutExpired:
            _kill(self._process)


_agents: dict[str, Agent] = {}
_agents_lock = threading.Lock()


def agent(connection: Connection) -> Agent:
    """The agent of a connection, started if needed (or again, if it died).

    Starting it is reported to the acquisition of the current thread, if any,
    as a step of its own (``agent ready``): once per session.
    """
    key = connection.model_dump_json()
    with _agents_lock:
        found = _agents.get(key)
        if found is None or not found.alive:
            found = _agents[key] = Agent(connection)
            progress.report("stage", None, "agent ready")
            progress.annotate(agent="started for this step")
        elif progress.current("agent") is None:
            progress.annotate(agent="warm")
        progress.annotate(remote=found.versions)
        return found


def close_agents() -> None:
    """Stop all the agents."""
    with _agents_lock:
        agents = list(_agents.values())
        _agents.clear()
    for found in agents:
        found.close()


atexit.register(close_agents)

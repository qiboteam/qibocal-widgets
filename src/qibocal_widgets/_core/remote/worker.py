"""Worker executing remote steps.

This module is self-contained: its source is shipped inline (``python3 -u -c
<source>``), so the remote machine does not need ``qibocal-widgets``
installed. A job is read as JSON from the standard input, and the outcome is
written on the standard output as a single line prefixed by :data:`MARKER`.

The bootstrap only uses the standard library, and runs on whatever
``python3`` the remote machine provides. Every action except ``install`` is
then executed with the Python of the configured environment, where Qibocal and
the protocols' dependencies are installed.

Outputs travel in Qibocal's own format (JSON and NPZ files), base64-encoded:
nothing is pickled.

The prefix ``WORKER_SOURCE = ...`` is prepended to the shipped source, so no
``from __future__`` import is allowed: annotations needing newer syntax are
quoted.
"""

import base64
import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

MARKER = "QIBOCAL_WIDGETS_RESULT "
"""Prefix of the line carrying the outcome on the standard output."""
PROGRESS = "QIBOCAL_WIDGETS_PROGRESS "
"""Prefix of the lines carrying events, while acquiring: duration estimates,
and the start and end of the acquisition."""
ESTIMATE_LOGGERS = {
    "qibolab._core.platform.platform": "execution",
    "qibolab._core.instruments.qblox.cluster": "batch",
}
"""Loggers of the duration estimates, and their kind: qibolab's, for a whole
execution on the platform, then the driver's refinement, before each batch."""
ESTIMATE = re.compile(
    r"(?:Pulse execution time|expected execution time): ([-+.\deE]+) s"
)
"""Messages of the duration estimates, in seconds."""
PLATFORMS = "QIBOLAB_PLATFORMS"
"""Environment variable locating qibolab platforms."""
AGENT = "QIBOCAL_WIDGETS_AGENT "
"""Prefix of the lines of an agent, followed by the job they belong to."""
DIRECT = "QIBOCAL_WIDGETS_DIRECT"
"""Environment variable of jobs launched by an agent, straight in the
environment's interpreter: they report their own start."""
GUARD = "QIBOCAL_WIDGETS_WORKER"
"""Environment variable set when running inside the configured environment."""
REQUIREMENTS = "qibocamp-requirements.txt"
"""Marker of the requirements installed in an environment.

Same name and content as the environments managed by Qibocamp.
"""


# -- duration estimates ------------------------------------------------------

_estimates_lock = threading.Lock()
_estimates_callbacks: "dict[int, object]" = {}
"""Callbacks of the threads capturing estimates, by thread identifier."""
_estimates_levels: "dict[str, tuple[int, int]]" = {}
"""Level and effective level of the estimate loggers, before capturing."""


def _scrape(record: logging.LogRecord) -> bool:
    """Logger filter: pass estimates on, hiding what was only enabled for it."""
    callback = _estimates_callbacks.get(record.thread)
    if callback is not None:
        match = ESTIMATE.search(record.getMessage())
        if match is not None:
            with contextlib.suppress(Exception):
                callback(float(match[1]), ESTIMATE_LOGGERS[record.name])
    return record.levelno >= _estimates_levels.get(record.name, (0, 0))[1]


@contextlib.contextmanager
def estimates(callback):
    """Call ``callback(seconds, kind)`` with the duration estimates logged by
    qibolab, of a whole execution, or of a batch (see :data:`ESTIMATE_LOGGERS`).

    Only the estimates logged by the current thread are captured. Their
    loggers are enabled for them, if needed, without emitting anything more
    than before.
    """
    thread = threading.get_ident()
    with _estimates_lock:
        if not _estimates_callbacks:
            for name in ESTIMATE_LOGGERS:
                logger = logging.getLogger(name)
                _estimates_levels[name] = (logger.level, logger.getEffectiveLevel())
                if logger.getEffectiveLevel() > logging.INFO:
                    logger.setLevel(logging.INFO)
                logger.addFilter(_scrape)
        _estimates_callbacks[thread] = callback
    try:
        yield
    finally:
        with _estimates_lock:
            del _estimates_callbacks[thread]
            if not _estimates_callbacks:
                for name in ESTIMATE_LOGGERS:
                    logger = logging.getLogger(name)
                    logger.removeFilter(_scrape)
                    logger.setLevel(_estimates_levels.pop(name)[0])


class Cancelled(BaseException):
    """The execution was cancelled.

    A ``BaseException``, as ``KeyboardInterrupt``, so that it is not caught by
    the handlers of failures along the way.
    """


def check_cancelled() -> None:
    """Stop here if the job of the current thread was cancelled.

    Called where qibolab logs its estimates: before every execution on the
    platform, and every batch, so that a cancelled acquisition stops between
    them, in a consistent state.

    Raises:
        Cancelled: if the job was cancelled.
    """
    flag = getattr(_output, "cancel", None)
    if flag is not None and flag.is_set():
        raise Cancelled()


def emit_estimate(seconds: float, kind: str) -> None:
    """Write a duration estimate line, then stop if cancelled."""
    emit_event(kind, seconds)
    check_cancelled()


def emit_event(
    kind: str, seconds: "float | None" = None, name: "str | None" = None
) -> None:
    """Write an event line: ``started``, ``acquired``, a ``stage`` (with its
    ``name``), or an estimate."""
    event = {"kind": kind, "estimate": seconds}
    if name is not None:
        event["name"] = name
    write(PROGRESS + json.dumps(event))


def stage(name: str) -> None:
    """Report that a stage of the job was reached, for profiling."""
    emit_event("stage", name=name)


# -- environments ------------------------------------------------------------


def environment_path(venv: str) -> Path:
    """Location of an environment, given its name or path."""
    if venv.startswith(("/", "./", "../", "~")):
        return Path(venv).expanduser()
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "qibocamp" / "envs" / venv


def environment_python(env: Path) -> Path:
    """Python interpreter of an environment."""
    if os.name == "nt":
        return env / "Scripts" / "python.exe"
    return env / "bin" / "python"


def normalize(requirements: "str | None") -> str:
    """Requirements text without comments and blank lines.

    Qibocal is required by default, unless the requirements already name it
    (e.g. pinning a branch: ``qibocal @ git+https://...@protodev``).
    """
    lines = []
    for line in (requirements or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    names = {re.split(r"[\s<>=!~;\[@]", line, maxsplit=1)[0].lower() for line in lines}
    if "qibocal" not in names:
        lines.insert(0, "qibocal")
    return "\n".join(lines) + "\n"


def find_uv() -> "str | None":
    """Locate uv, as Qibocamp does, unless disabled."""
    if os.environ.get("QIBOCAMP_NO_UV"):
        return None
    found = shutil.which("uv")
    if found is not None:
        return found
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    tool = Path(cache) / "qibocamp" / "tools" / "uv"
    return str(tool) if tool.is_file() else None


def run_installer(command: list[str]) -> None:
    """Run an installation command, keeping the standard output clean."""
    print("+", " ".join(command), file=sys.stderr, flush=True)
    subprocess.run(command, check=True, stdout=sys.stderr)


def install(job: dict) -> dict:
    """Create the environment if needed, and install the requirements."""
    env = environment_path(job["venv"])
    python = environment_python(env)
    uv = find_uv()
    if job.get("rebuild") and (env / "pyvenv.cfg").is_file():
        shutil.rmtree(env)
    if not python.exists():
        interpreter = job.get("python") or sys.executable
        if uv is not None:
            run_installer([uv, "venv", "--seed", "--python", interpreter, str(env)])
        else:
            run_installer([interpreter, "-m", "venv", str(env)])
    requirements = normalize(job.get("requirements"))
    marker = env / REQUIREMENTS
    if marker.is_file() and marker.read_text() == requirements:
        return {"environment": str(env), "installed": False}
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as file:
        file.write(requirements)
    try:
        if uv is not None:
            # compiled now, rather than by the first job (pip does it anyway)
            run_installer(
                [
                    uv,
                    "pip",
                    "install",
                    "--compile-bytecode",
                    "--python",
                    str(python),
                    "-r",
                    file.name,
                ]
            )
        else:
            run_installer([str(python), "-m", "pip", "install", "-r", file.name])
    finally:
        os.unlink(file.name)
    marker.write_text(requirements)
    return {"environment": str(env), "installed": True}


def delegate(job: dict, text: str) -> int:
    """Run the job again, inside the configured environment."""
    env = environment_path(job["venv"])
    python = environment_python(env)
    if not python.exists():
        emit(
            {
                "ok": False,
                "error": f"Environment not found: {env}. Install it first.",
            }
        )
        return 1
    source = globals().get("WORKER_SOURCE")
    if source is None:
        source = Path(__file__).read_text()
    process = subprocess.run(
        [str(python), "-u", "-c", f"WORKER_SOURCE = {source!r}\n{source}"],
        input=text,
        text=True,
        env=dict(os.environ, **{GUARD: "1"}),
        check=False,
    )
    return process.returncode


# -- agent: a warm worker, outside of the queue ------------------------------


def agent(venv: str) -> int:
    """Serve jobs read from the standard input, one JSON object per line.

    Started once per runner, on the access node (never in the queue): imports
    are done once, and the jobs not needing the instruments run here, at once.
    Acquisitions through the queue are launched as ``srun`` jobs, straight in
    the environment's interpreter, relaying their output; without a queue,
    they run here. Jobs run here one at a time, on the main thread, as qibolab
    platforms require (they install signal handlers), and acquisitions share
    the instruments anyway. Every output line is tagged with its job
    (:data:`AGENT`). It exits with its standard input, i.e. when the client
    disconnects.
    """
    import concurrent.futures
    import queue

    requests: queue.Queue = queue.Queue()
    clean_jobs()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=32)
    # imported once, for all the jobs
    import qibocal  # noqa: F401

    def following(request: dict) -> None:
        _output.job = str(request["id"])
        try:
            follow(str(request["id"]), str(request["follow"]))
        finally:
            _output.job = None

    flags: dict[str, threading.Event] = {}
    """Cancellation flags of the jobs running here."""

    def serve(request: dict) -> None:
        job_id = str(request["id"])
        job = request["job"]
        _output.job = job_id
        if request.get("srun") is None:
            _output.cancel = flags.setdefault(job_id, threading.Event())
        try:
            if job.get("platforms_dir"):
                os.environ[PLATFORMS] = str(Path(job["platforms_dir"]).expanduser())
            if request.get("srun") is not None:
                launch(job_id, job, request["srun"], request["name"])
                return
            action = job["action"]
            check_cancelled()  # e.g. before its turn
            if action == "acquire":
                emit_event("started")
            emit({"ok": True, **ACTIONS[action](job)})
        except Cancelled:
            emit({"ok": False, "error": "Cancelled", "cancelled": True})
        except Exception as error:  # noqa: BLE001 - any failure is reported
            emit(
                {
                    "ok": False,
                    "error": f"{type(error).__name__}: {error}",
                    "traceback": traceback.format_exc(),
                }
            )
        finally:
            _output.job = None
            _output.cancel = None
            flags.pop(job_id, None)

    names: dict[str, str] = {}
    """The job folder of each request, to cancel it."""

    def launch(job_id: str, job: dict, srun: list, name: str) -> None:
        """Run a job through the queue, detached, and follow it.

        The job has a folder of its own, where its output is written: it
        survives the agent (and the client), and can be followed again.
        """
        folder = jobs_dir() / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "job.json").write_text(json.dumps(job))
        source = globals().get("WORKER_SOURCE") or Path(__file__).read_text()
        (folder / "worker.py").write_text(source)
        command = [*srun, sys.executable, "-u", "worker.py"]
        script = (
            f"{shlex.join(command)} < job.json > stdout.log 2> stderr.log; "
            "echo $? > exit"
        )
        process = subprocess.Popen(
            ["sh", "-c", script],
            cwd=folder,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=dict(os.environ, **{GUARD: "1", DIRECT: "1"}),
            start_new_session=True,  # not stopped with the agent
        )
        (folder / "pid").write_text(str(process.pid))
        # reaped while the agent lives; adopted by init afterwards
        threading.Thread(target=process.wait, daemon=True).start()
        follow(job_id, name)

    def follow(job_id: str, name: str) -> None:
        """Relay the output of a job, as written, until its outcome."""
        names[job_id] = name
        folder = jobs_dir() / name
        if not folder.is_dir():
            emit({"ok": False, "error": f"{UNKNOWN} {name}", "unknown": True})
            return
        output = folder / "stdout.log"
        position = 0
        pending = ""
        try:
            while True:
                ended = (folder / "exit").exists()
                if output.exists():
                    with output.open() as file:
                        file.seek(position)
                        chunk = file.read()
                        position = file.tell()
                    pending += chunk
                    *lines, pending = pending.split("\n")
                    for line in lines:
                        write(line)
                        if line.startswith(MARKER):
                            return
                if ended and (folder / "cancelled").exists():
                    emit({"ok": False, "error": "Cancelled", "cancelled": True})
                    return
                if ended:
                    code = (folder / "exit").read_text().strip()
                    errors = folder / "stderr.log"
                    details = errors.read_text() if errors.exists() else ""
                    emit(
                        {
                            "ok": False,
                            "error": f"Job exited with code {code} and no outcome",
                            "traceback": "\n".join(details.splitlines()[-40:]),
                        }
                    )
                    return
                time.sleep(0.1)
        finally:
            names.pop(job_id, None)

    def cancel(job_id: str) -> None:
        if job_id in flags:  # running here: stops at its next estimate
            flags[job_id].set()
            return
        name = names.get(job_id)
        if name is not None:
            threading.Thread(target=terminate, args=(name,), daemon=True).start()

    def terminate(name: str) -> None:
        """Stop a queued job: SIGTERM, which srun forwards (and qibolab handles
        by disconnecting the instruments), then SIGKILL after a grace period."""
        import signal

        folder = jobs_dir() / name
        try:
            group = int((folder / "pid").read_text())
        except (OSError, ValueError):
            return
        with contextlib.suppress(OSError):
            (folder / "cancelled").write_text("")  # before it exits
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(group, signal.SIGTERM)
        deadline = time.monotonic() + GRACE
        while time.monotonic() < deadline and alive(group):
            time.sleep(0.1)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(group, signal.SIGKILL)
        with contextlib.suppress(OSError):
            if not (folder / "exit").exists():
                (folder / "exit").write_text("cancelled")

    def forget(name: str) -> None:
        shutil.rmtree(jobs_dir() / name, ignore_errors=True)

    def receive() -> None:
        for line in sys.stdin:
            if not line.strip():
                continue
            request = json.loads(line)
            if "cancel" in request:
                cancel(str(request["cancel"]))
            elif "forget" in request:
                forget(str(request["forget"]))
            elif "follow" in request:
                pool.submit(following, request)
            elif request.get("srun") is not None:
                pool.submit(serve, request)  # waiting for the queue, elsewhere
            else:
                requests.put(request)
        requests.put(None)

    threading.Thread(target=receive, daemon=True).start()
    write(AGENT + "ready " + json.dumps(package_versions()))
    while (request := requests.get()) is not None:
        serve(request)
    # the client is gone: the queued jobs go on, detached, to be followed
    # again; their followers have nobody to relay to, so stop at once
    with _output_lock:
        sys.stdout.flush()
    os._exit(0)


VERSIONED = ("qibocal", "qibolab", "qibocal-widgets")
"""Packages whose versions are reported, for profiles."""


def package_versions() -> "dict[str, str]":
    """Versions of the reported packages installed here, with the commit (and
    branch) when installed from a repository."""
    from importlib import metadata

    found = {}
    for name in VERSIONED:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        version = distribution.version
        with contextlib.suppress(Exception):
            origin = json.loads(distribution.read_text("direct_url.json") or "{}")
            vcs = origin.get("vcs_info") or {}
            if vcs.get("commit_id"):
                ref = vcs.get("requested_revision")
                commit = vcs["commit_id"][:8]
                version += f" ({ref}@{commit})" if ref else f" ({commit})"
        found[name] = version
    return found


GRACE = 10.0
"""Seconds between asking a cancelled job to stop, and killing it."""
UNKNOWN = "Unknown remote job"


def alive(group: int) -> bool:
    """Whether any process of a process group is still running."""
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
"""Error of jobs to follow which were never launched (or removed)."""

JOBS_RETENTION = 7 * 24 * 3600
"""Seconds after which ended jobs which were never fetched are removed."""


def jobs_dir() -> Path:
    """Where detached jobs keep their folders."""
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "qibocamp" / "jobs"


def clean_jobs() -> None:
    """Remove the folders of jobs ended long ago, and never fetched."""
    import time as clock

    root = jobs_dir()
    if not root.is_dir():
        return
    for folder in root.iterdir():
        ended = folder / "exit"
        with contextlib.suppress(OSError):
            if ended.exists() and clock.time() - ended.stat().st_mtime > JOBS_RETENTION:
                shutil.rmtree(folder, ignore_errors=True)


def start_agent(venv: str) -> int:
    """Become the agent, in the configured environment's interpreter."""
    env = environment_path(venv)
    python = environment_python(env)
    if not python.exists():
        write(
            AGENT
            + "missing "
            + json.dumps(f"Environment not found: {env}. Install it first.")
        )
        return 1
    source = globals().get("WORKER_SOURCE") or Path(__file__).read_text()
    os.environ[GUARD] = "1"
    # replaced, keeping the standard streams: no process in between
    os.execv(
        str(python),
        [
            str(python),
            "-u",
            "-c",
            f"WORKER_SOURCE = {source!r}\n{source}",
            "agent",
            venv,
        ],
    )
    return 1


# -- qibocal actions (inside the environment) --------------------------------


def resolve(reference: str):
    """Import a protocol from its ``module:attribute`` reference."""
    import importlib

    module, _, attribute = reference.partition(":")
    obj = importlib.import_module(module)
    for name in attribute.split("."):
        obj = getattr(obj, name)
    return obj


def bind(job: dict):
    """Rebuild the bound protocol."""
    from qibocal.auto.operation import Parameters

    protocol = resolve(job["protocol"])
    kind = protocol.parameters_type
    raw = job["parameters"]
    if isinstance(kind, type) and issubclass(kind, Parameters):
        parameters = kind.load(raw)
    elif isinstance(raw, dict):
        parameters = kind(**raw)
    else:
        parameters = raw
    return protocol(pars=parameters)


def platform(job: dict):
    """Create the platform, applying the shipped calibration state."""
    from qibocal import create_calibration_platform

    created = create_calibration_platform(job["platform"])
    state = job.get("state") or {}
    if state.get("parameters") is not None:
        created.parameters = type(created.parameters).model_validate_json(
            state["parameters"]
        )
    if state.get("calibration") is not None:
        from qibocal.calibration.calibration import Calibration

        created.calibration = Calibration.model_validate_json(state["calibration"])
    return created


def state(platform) -> dict:
    """Calibration state of a platform, as JSON documents."""
    calibration = getattr(platform, "calibration", None)
    return {
        "parameters": platform.parameters.model_dump_json(),
        "calibration": (
            calibration.model_dump_json() if calibration is not None else None
        ),
    }


def encode(folder: Path) -> dict:
    """Files of a folder, base64-encoded."""
    return {
        path.name: base64.b64encode(path.read_bytes()).decode()
        for path in sorted(folder.iterdir())
        if path.is_file()
    }


def decode(files: dict, folder: Path) -> None:
    """Write base64-encoded files into a folder."""
    for name, content in files.items():
        (folder / Path(name).name).write_bytes(base64.b64decode(content))


PARENT_PARAMETERS = ("nshots", "relaxation_time")
"""Attributes of Qibocal parameters which are not dataclass fields."""


def parameters_document(parameters) -> object:
    """Protocol parameters, as a JSON-compatible document.

    Qibocal's ``Parameters.load`` accepts it back, including the attributes
    shared by all protocols (``nshots``, ``relaxation_time``), which are not
    dataclass fields.
    """
    import dataclasses

    document = parameters
    if dataclasses.is_dataclass(parameters) and not isinstance(parameters, type):
        document = dataclasses.asdict(parameters)
        for name in PARENT_PARAMETERS:
            value = getattr(parameters, name, None)
            if value is not None:
                document[name] = value
    return json.loads(json.dumps(document, default=_jsonable))


def _jsonable(obj):
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


def acquire(job: dict) -> dict:
    """Acquire data on the connected platform."""
    stage("environment started")
    from qibocal import Executor

    stage("imported")
    bound = bind(job)
    created = platform(job)
    executor = Executor(created, targets=job["targets"], update=False)
    stage("platform created")
    created.connect()
    stage("connected")
    try:
        with estimates(emit_estimate):
            completed = executor.acquire(bound, **job.get("overrides", {}))
    finally:
        emit_event("acquired")  # the data follow
        created.disconnect()
        stage("disconnected")
    with tempfile.TemporaryDirectory() as folder:
        completed.data.save(Path(folder))
        files = encode(Path(folder))
    stage("encoded")
    return {
        "files": files,
        "data_time": completed.data_time,
        "targets": json.loads(json.dumps(completed.targets, default=list)),
        "parameters": parameters_document(completed.bound.parameters),
    }


def under_git(folder: Path) -> bool:
    """Whether a folder is in a git working tree (``git`` being available)."""
    try:
        process = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return process.returncode == 0 and process.stdout.strip() == "true"


def export_state(state: dict, folder: Path, overwrite: bool = False) -> str:
    """Write a platform state in a folder, as qibolab and Qibocal dump it.

    The JSON documents are indented as their own dumps, so that the changes
    of a platform folder under version control are only the changed values.
    Existing files are replaced only in a git working tree, where the previous
    version is kept, or when ``overwrite`` is set.

    Raises:
        FileExistsError: replacing files outside of a git working tree, without
            ``overwrite``.
    """
    names = {"parameters": "parameters.json", "calibration": "calibration.json"}
    folder.mkdir(parents=True, exist_ok=True)
    existing = [
        name
        for key, name in names.items()
        if state.get(key) is not None and (folder / name).exists()
    ]
    if existing and not overwrite and not under_git(folder):
        raise FileExistsError(
            f"{folder} is not under version control: pass overwrite=True to "
            f"replace {', '.join(existing)}"
        )
    for key, name in names.items():
        if state.get(key) is not None:
            document = json.loads(state[key])
            (folder / name).write_text(
                json.dumps(document, indent=4, ensure_ascii=False), encoding="utf-8"
            )
    return str(folder)


def save(job: dict) -> dict:
    """Write the platform state in the platform folder, on this machine."""
    from qibolab import locate_platform

    folder = locate_platform(job["platform"])
    return {"path": export_state(job["state"], folder, job.get("overwrite", False))}


def update(job: dict) -> dict:
    """Apply fit results to the platform, returning its new state."""
    from qibocal import Executor
    from qibocal.auto.task import Completed

    bound = bind(job)
    created = platform(job)
    with tempfile.TemporaryDirectory() as folder:
        decode(job["files"], Path(folder))
        results = bound.protocol.results_type.load(Path(folder))
    completed = Completed(bound=bound, _results=results, _targets=job["targets"])
    # explicit targets: the execution carries no data to infer them from
    Executor(created).update(completed, targets=job["targets"])
    return {"state": state(created)}


def layout_of(platform) -> dict:
    """The layout of a platform: qubits, couplers, channels, and instruments.

    Identifiers are kept as given (e.g. integer qubits), as lists of pairs.
    """

    def kind(obj) -> str:
        return type(obj).__name__

    def dumped(elements) -> list:
        return [[name, element.model_dump(mode="json")] for name, element in elements]

    return {
        "qubits": dumped(platform.qubits.items()),
        "couplers": dumped(getattr(platform, "couplers", {}).items()),
        "channels": [
            [name, {"kind": kind(channel), **channel.model_dump(mode="json")}]
            for name, channel in platform.channels.items()
        ],
        "instruments": [
            [
                name,
                {
                    "kind": kind(instrument),
                    "address": getattr(instrument, "address", None),
                },
            ]
            for name, instrument in platform.instruments.items()
        ],
    }


def layout(job: dict) -> dict:
    """The layout of the platform, created without connecting it."""
    from qibocal import create_calibration_platform

    return {"layout": layout_of(create_calibration_platform(job["platform"]))}


def describe(job: dict) -> dict:
    """The calibration state of the platform, without connecting it."""
    return {"state": state(platform(job))}


ACTIONS = {
    "acquire": acquire,
    "update": update,
    "describe": describe,
    "layout": layout,
    "save": save,
}


# -- entry point ---------------------------------------------------------------


_output_lock = threading.Lock()
_output = threading.local()
"""The job of the current thread, in an agent."""


def write(line: str) -> None:
    """Write a line of the standard output, tagged with its job in an agent."""
    job = getattr(_output, "job", None)
    if job is not None:
        line = f"{AGENT}{job} {line}"
    with _output_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def emit(payload: dict) -> None:
    """Write the outcome line."""
    write(MARKER + json.dumps(payload))


def main() -> int:
    if sys.argv[1:2] == ["agent"]:
        venv = sys.argv[2]
        if os.environ.get(GUARD) != "1":
            return start_agent(venv)
        return agent(venv)
    text = sys.stdin.read()
    job = json.loads(text)
    action = job["action"]
    if job.get("platforms_dir"):
        # inherited by the environment's interpreter, and the platforms it loads
        os.environ[PLATFORMS] = str(Path(job["platforms_dir"]).expanduser())
    try:
        if action == "install":
            emit({"ok": True, **install(job)})
            return 0
        if os.environ.get(GUARD) != "1":
            if action == "acquire":
                emit_event("started")  # out of the queue, if any
            return delegate(job, text)
        if os.environ.get(DIRECT) == "1" and action == "acquire":
            emit_event("started")  # launched by an agent, out of the queue
        emit({"ok": True, **ACTIONS[action](job)})
        return 0
    except Exception as error:  # noqa: BLE001 - any failure is reported
        emit(
            {
                "ok": False,
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(),
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

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
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

MARKER = "QIBOCAL_WIDGETS_RESULT "
"""Prefix of the line carrying the outcome on the standard output."""
PLATFORMS = "QIBOLAB_PLATFORMS"
"""Environment variable locating qibolab platforms."""
GUARD = "QIBOCAL_WIDGETS_WORKER"
"""Environment variable set when running inside the configured environment."""
REQUIREMENTS = "qibocamp-requirements.txt"
"""Marker of the requirements installed in an environment.

Same name and content as the environments managed by Qibocamp.
"""


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
            run_installer(
                [uv, "pip", "install", "--python", str(python), "-r", file.name]
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
    from qibocal import Executor

    bound = bind(job)
    created = platform(job)
    executor = Executor(created, targets=job["targets"], update=False)
    created.connect()
    try:
        completed = executor.acquire(bound, **job.get("overrides", {}))
    finally:
        created.disconnect()
    with tempfile.TemporaryDirectory() as folder:
        completed.data.save(Path(folder))
        files = encode(Path(folder))
    return {
        "files": files,
        "data_time": completed.data_time,
        "targets": json.loads(json.dumps(completed.targets, default=list)),
        "parameters": parameters_document(completed.bound.parameters),
    }


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


def describe(job: dict) -> dict:
    """The calibration state of the platform, without connecting it."""
    return {"state": state(platform(job))}


ACTIONS = {"acquire": acquire, "update": update, "describe": describe}


# -- entry point ---------------------------------------------------------------


def emit(payload: dict) -> None:
    """Write the outcome line."""
    sys.stdout.write(MARKER + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> int:
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
            return delegate(job, text)
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

"""Remote execution, against fake ``ssh``, ``srun``, ``python3`` and ``uv``.

The fake executables log their arguments and run the actual command locally,
so the whole exchange (inline worker, JSON job on stdin, outcome on stdout,
environment delegation) is exercised for real.
"""

import ast
import json
import os
import stat
import sys
from pathlib import Path

import pytest
from conftest import TARGETS
from fake import DEFAULT_SCALE, fake
from qibocal import create_calibration_platform, protocols
from qibocal.auto.operation import Protocol

from qibocal_widgets import Executor
from qibocal_widgets._core.remote import jobs, transport, worker
from qibocal_widgets.remote import (
    Connection,
    IncompatibleConfig,
    Remote,
    RemoteError,
    config_path,
    connections,
    load_connection,
    remove_connection,
    save_connection,
)

TESTS = Path(__file__).parent
PLATFORMS = TESTS / "platforms"


def executable(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


FAKE_SSH = """
import json, os, sys
args = sys.argv[1:]
if args[-2] == "unreachable":
    sys.stderr.write("ssh: connect to host unreachable: Connection refused\\n")
    sys.exit(255)
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"tool": "ssh", "args": [a[:80] for a in args]}) + "\\n")
os.execvp("sh", ["sh", "-c", args[-1]])
"""

FAKE_SRUN = """
import json, os, sys, time
args = sys.argv[1:]
index = args.index("python3")
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"tool": "srun", "args": args[:index]}) + "\\n")
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
os.execvp(args[index], args[index:])
"""

FAKE_UV = """
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
entry = {"tool": "uv", "args": args}
if args[0] == "venv":
    env = Path(args[-1])
    (env / "bin").mkdir(parents=True)
    (env / "pyvenv.cfg").write_text("")
    python = env / "bin" / "python"
    python.write_text(f"#!/bin/sh\\nexec {sys.executable} \\"$@\\"\\n")
    python.chmod(0o755)
else:
    entry["requirements"] = Path(args[args.index("-r") + 1]).read_text()
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(entry) + "\\n")
"""


@pytest.fixture
def cluster(tmp_path, monkeypatch):
    """Fake cluster tools on PATH, and an environment with Qibocal."""
    bin = tmp_path / "bin"
    bin.mkdir()
    executable(bin / "ssh", FAKE_SSH)
    executable(bin / "srun", FAKE_SRUN)
    executable(bin / "uv", FAKE_UV)
    (bin / "python3").symlink_to(sys.executable)
    cache = tmp_path / "cache"
    env = cache / "qibocal" / "envs" / "qibocal" / "bin"
    env.mkdir(parents=True)
    (env / "python").write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    (env / "python").chmod(0o755)
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("PATH", f"{bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    monkeypatch.setenv("PYTHONPATH", str(TESTS))

    def calls():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    return calls


@pytest.fixture
def mock_frequency(monkeypatch):
    """Drive frequencies of the mock platform, by target."""
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    platform = create_calibration_platform("mock")
    return {t: platform.config(platform.qubits[t].drive).frequency for t in TARGETS}


# -- configuration -------------------------------------------------------------


def test_config_roundtrip():
    assert connections() == {}
    lab = Connection(ssh="me@login", queue="qpu", platform="chip")
    save_connection("lab", lab)
    assert load_connection("lab") == lab
    assert connections() == {"lab": lab}
    content = json.loads(config_path().read_text())
    # only non-default fields are stored, in qibocal-report's versioned layout
    assert content == {
        "version": 1,
        "connections": {"lab": {"ssh": "me@login", "queue": "qpu", "platform": "chip"}},
    }
    remove_connection("lab")
    assert connections() == {}


def test_config_missing_connection():
    with pytest.raises(KeyError, match="nowhere"):
        load_connection("nowhere")


def test_config_incompatible_version():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps({"version": 2, "connections": {}}))
    with pytest.raises(IncompatibleConfig):
        connections()


def test_connection_validation():
    with pytest.raises(ValueError):
        Connection(unknown="field")
    with pytest.raises(ValueError, match="destination"):
        Connection(ssh="me@login -v").destination()


def test_remote_options(monkeypatch):
    save_connection("lab", Connection(ssh="me@login", queue="qpu"))
    remote = Remote("lab", queue="other")
    assert remote.connection == Connection(ssh="me@login", queue="other")
    assert repr(remote) == "Remote(ssh='me@login', queue='other')"
    # selected through the environment, to keep notebooks unchanged across tiers
    monkeypatch.setenv("QIBOCAL_WIDGETS_CONNECTION", "lab")
    assert Remote().connection.queue == "qpu"
    monkeypatch.delenv("QIBOCAL_WIDGETS_CONNECTION")
    assert not Remote().connection.dispatched


# -- command lines -----------------------------------------------------------------


def test_command_tiers():
    local = transport.command(Connection(), compute=True)
    assert local[:3] == ["python3", "-u", "-c"]

    access = transport.command(Connection(queue="qpu", slurm="--time=5"), compute=True)
    assert access[:7] == [
        "srun",
        "--unbuffered",
        "--partition",
        "qpu",
        "--time=5",
        "--nodes=1",
        "--ntasks=1",
    ]
    assert access[7] == "python3"
    # steps without instruments skip the queue
    assert transport.command(Connection(queue="qpu"), compute=False)[0] == "python3"

    laptop = transport.command(
        Connection(ssh="-J bastion me@login", queue="qpu"), compute=True
    )
    assert laptop[:3] == ["ssh", "-J", "bastion"]
    assert "BatchMode=yes" in laptop
    assert laptop[-2] == "me@login"
    assert laptop[-1].startswith("srun --unbuffered --partition qpu")


def test_command_workdir():
    remote = transport.command(Connection(ssh="login", workdir="~/runs"), compute=True)
    assert remote[-1].startswith('cd "$HOME"/runs && python3')
    local = transport.command(Connection(workdir="/scratch/a b"), compute=True)
    assert local[:2] == ["sh", "-c"]
    assert local[2].startswith("cd '/scratch/a b' && exec python3")


@pytest.mark.parametrize("option", ["--pty", "-o out.log", "--ntasks=2", "-N 2"])
def test_slurm_forbidden(option):
    with pytest.raises(ValueError, match="not supported"):
        transport.slurm_arguments(option)


# -- jobs ----------------------------------------------------------------------------


def test_protocol_reference():
    assert jobs.protocol_reference(protocols.ramsey_signal) == (
        "qibocal.protocols:ramsey_signal"
    )
    assert jobs.protocol_reference(fake) == "fake:fake"

    def acquisition(params: dict, targets): ...

    with pytest.raises(RemoteError, match="importable"):
        jobs.protocol_reference(Protocol(acquisition))


def test_parameters_document(bound):
    bound = fake(npoints=3, nshots=10)
    document = jobs.parameters(bound.parameters)
    assert document == {"npoints": 3, "nshots": 10}
    loaded = type(bound.parameters).load(document)
    assert (loaded.npoints, loaded.nshots) == (3, 10)


def test_document_rejects_objects():
    with pytest.raises(RemoteError, match="Cannot send"):
        jobs.document({"value": object()})


def test_worker_grammar():
    """The bootstrap runs on old system interpreters."""
    ast.parse(Path(worker.__file__).read_text(), feature_version=(3, 8))


def test_normalize():
    assert worker.normalize(None) == "qibocal\n"
    assert worker.normalize("numpy  # comment\n\n") == "qibocal\nnumpy\n"
    pinned = "qibocal @ git+https://github.com/qiboteam/qibocal.git@protodev"
    assert worker.normalize(pinned) == pinned + "\n"


# -- runner --------------------------------------------------------------------------


def test_role():
    remote = Remote()
    assert Executor(None, runner=remote).runner is remote
    with pytest.raises(TypeError, match="Middleware"):
        Executor(None, middleware=[remote])


def test_passthrough(bound, cluster):
    executor = Executor(None, targets=TARGETS, update=False, runner=Remote())
    completed = executor(bound)
    assert completed.data.scale == {t: DEFAULT_SCALE for t in TARGETS}
    assert cluster() == []


def test_laptop_tier(bound, cluster, mock_frequency):
    remote = Remote(
        ssh="-J bastion me@login", queue="chip", slurm="--time=5", platform="mock"
    )
    executor = Executor(None, targets=TARGETS, update=False, runner=remote)
    with executor:  # no local platform to connect
        completed = executor(bound)

    # acquired remotely, on the platform: fit and report ran locally
    assert completed.data.scale == mock_frequency
    assert completed.data.qubits == TARGETS
    assert set(completed.results.peak) == set(TARGETS)
    assert set(completed.reports) == set(TARGETS)
    assert completed.bound.parameters.nshots is not None  # platform default

    ssh, srun = cluster()
    assert ssh["tool"] == "ssh"
    assert ssh["args"][:2] == ["-J", "bastion"]
    assert "me@login" in ssh["args"]
    assert srun == {
        "tool": "srun",
        "args": [
            "--unbuffered",
            "--partition",
            "chip",
            "--time=5",
            "--nodes=1",
            "--ntasks=1",
        ],
    }


def test_remote_update_state(bound, cluster, mock_frequency):
    """Without a local platform, updates run remotely and the state travels."""
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, targets=TARGETS[:1], update=True, runner=remote)
    completed = executor(bound)
    assert completed.data.scale == {0: mock_frequency[0]}

    # the update ran on the access node, outside of the queue
    assert [call["tool"] for call in cluster()] == ["ssh", "srun", "ssh"]
    peak = completed.results.peak[0]
    drive = create_calibration_platform("mock").qubits[0].drive
    parameters = json.loads(remote.state["parameters"])
    assert parameters["configs"][drive]["frequency"] == peak * 1e9

    # the next acquisition runs on the updated platform
    again = executor.acquire(bound)
    assert again.data.scale == {0: peak * 1e9}


def test_access_tier_local_update(bound, cluster, mock_frequency, monkeypatch):
    """With a local platform, updates are local and its state travels."""
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    platform = create_calibration_platform("mock")
    executor = Executor(
        platform, targets=TARGETS[:1], update=True, runner=Remote(queue="chip")
    )
    completed = executor(bound)
    peak = completed.results.peak[0]
    assert platform.config(platform.qubits[0].drive).frequency == peak * 1e9
    assert [call["tool"] for call in cluster()] == ["srun"]

    again = executor.acquire(bound)
    assert again.data.scale == {0: peak * 1e9}


def test_builtin_protocol(cluster):
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Remote(queue="chip", platform="mock"),
    )
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    completed = executor(bound, nshots=64)
    assert completed.bound.parameters.nshots == 64
    assert sorted(completed.data.qubits) == TARGETS
    assert set(completed.reports) == set(TARGETS)


# -- failures --------------------------------------------------------------------------


def test_missing_environment(bound, cluster):
    executor = Executor(
        None,
        targets=TARGETS,
        runner=Remote(queue="chip", platform="mock", venv="missing"),
    )
    with pytest.raises(RemoteError, match="Environment not found"):
        executor.acquire(bound)


def test_protocol_unavailable_remotely(bound, cluster, monkeypatch):
    monkeypatch.delenv("PYTHONPATH")
    executor = Executor(
        None, targets=TARGETS, runner=Remote(queue="chip", platform="mock")
    )
    with pytest.raises(RemoteError, match="ModuleNotFoundError") as error:
        executor.acquire(bound)
    assert "Traceback" in error.value.details


def test_unreachable(bound, cluster):
    executor = Executor(
        None, targets=TARGETS, runner=Remote(ssh="unreachable", platform="mock")
    )
    with pytest.raises(RemoteError, match="code 255") as error:
        executor.acquire(bound)
    assert "Connection refused" in error.value.details


def test_timeout(bound, cluster, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "5")
    executor = Executor(
        None,
        targets=TARGETS,
        runner=Remote(queue="chip", platform="mock", timeout=0.5),
    )
    with pytest.raises(RemoteError, match="timed out"):
        executor.acquire(bound)


# -- environment ------------------------------------------------------------------------


def test_install(cluster, tmp_path):
    requirements = "qibocal @ git+https://github.com/qiboteam/qibocal.git@protodev"
    remote = Remote(
        ssh="me@login", queue="chip", venv="fresh", requirements=requirements
    )
    outcome = remote.install()
    assert outcome["installed"]
    env = Path(outcome["environment"])
    assert env == tmp_path / "cache" / "qibocal" / "envs" / "fresh"
    assert (env / worker.REQUIREMENTS).read_text() == requirements + "\n"

    # installed on the access node, outside of the queue
    ssh, venv, install = cluster()
    assert ssh["tool"] == "ssh"
    assert venv["args"][0] == "venv"
    assert install["requirements"] == requirements + "\n"

    # unchanged requirements: nothing to do
    assert not remote.install()["installed"]
    # changed requirements: installed on top
    remote.connection = remote.connection.model_copy(
        update={"requirements": requirements + "\nnumpy"}
    )
    assert remote.install()["installed"]
    assert cluster()[-1]["requirements"].endswith("numpy\n")
    # rebuild from scratch
    assert remote.install(rebuild=True)["installed"]
    assert cluster()[-2]["args"][0] == "venv"


def test_install_on_compute(cluster):
    Remote(queue="chip", venv="fresh", rebuild_on_compute=True).install()
    assert [call["tool"] for call in cluster()] == ["srun", "uv", "uv"]


def test_install_pip_fallback(tmp_path, monkeypatch):
    commands = []
    env = tmp_path / "env"

    def installer(command):
        commands.append(command)
        env.mkdir(exist_ok=True)

    monkeypatch.setattr(worker, "run_installer", installer)
    monkeypatch.setenv("QIBOCAL_NO_UV", "1")
    outcome = worker.install(
        {"venv": str(env), "python": "/usr/bin/python3.12", "requirements": "numpy"}
    )
    assert outcome["installed"]
    assert commands[0] == ["/usr/bin/python3.12", "-m", "venv", str(env)]
    assert commands[1][:4] == [str(env / "bin" / "python"), "-m", "pip", "install"]

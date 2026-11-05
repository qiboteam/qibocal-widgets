"""Remote execution, against fake ``ssh``, ``srun``, ``python3`` and ``uv``.

The fake executables log their arguments and run the actual command locally,
so the whole exchange (inline worker, JSON job on stdin, outcome on stdout,
environment delegation) is exercised for real.
"""

import ast
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest
from conftest import PLATFORMS, TARGETS
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
    environment_name,
    load_connection,
    remove_connection,
    save_connection,
)

TESTS = Path(__file__).parent


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
index = args.index("-u") - 1  # the interpreter: python3, or the environment's
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"tool": "srun", "args": args[:index]}) + "\\n")
if "FAKE_STARTS" in os.environ:
    with open(os.environ["FAKE_STARTS"], "a") as starts:
        starts.write(f"{time.time()}\\n")
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
    if sys.platform == "win32":
        pytest.skip("the fake cluster tools are POSIX executables")
    bin = tmp_path / "bin"
    bin.mkdir()
    executable(bin / "ssh", FAKE_SSH)
    executable(bin / "srun", FAKE_SRUN)
    executable(bin / "uv", FAKE_UV)
    (bin / "python3").symlink_to(sys.executable)
    cache = tmp_path / "cache"
    env = cache / "qibocamp" / "envs" / "qibocal" / "bin"
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

    yield calls
    transport.close_agents()  # started in this test's environment


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
    # a named connection has an environment of its own, implied by its name
    own = lab.model_copy(update={"venv": "_remote/lab"})
    assert load_connection("lab") == own
    assert connections() == {"lab": own}
    content = json.loads(config_path().read_text())
    # only non-default fields are stored, in Qibocamp's versioned layout
    assert content == {
        "version": 1,
        "connections": {"lab": {"ssh": "me@login", "queue": "qpu", "platform": "chip"}},
    }
    remove_connection("lab")
    assert connections() == {}


def test_config_environment():
    assert environment_name("QW5Q lab") == "_remote/QW5Q-lab"
    assert environment_name("***") == "_remote/qibocal"
    save_connection("lab", Connection(venv="qibocal"))
    save_connection(
        "own", load_connection("lab").model_copy(update={"venv": "_remote/own"})
    )
    content = json.loads(config_path().read_text())["connections"]
    # sharing one is a choice, kept; its own is implied
    assert content == {"lab": {"venv": "qibocal"}, "own": {}}
    assert load_connection("lab").venv == "qibocal"
    assert Remote("own").connection.venv == "_remote/own"
    assert Remote("own", venv="other").connection.venv == "other"
    assert Remote().connection.venv == "qibocal"


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
    assert remote.connection == Connection(
        ssh="me@login", queue="other", venv="_remote/lab"
    )
    assert repr(remote) == "Remote(ssh='me@login', queue='other', venv='_remote/lab')"
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
    assert access[:9] == [
        "srun",
        "--unbuffered",
        "--partition",
        "qpu",
        "--job-name",
        "qibocal-widgets-step",
        "--time=5",
        "--nodes=1",
        "--ntasks=1",
    ]
    assert access[9] == "python3"
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
            "--job-name",
            "qibocal-widgets-acquire",
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

    # a single connection, the agent's: the acquisition through the queue,
    # the update in the agent, on the access node, outside of the queue
    assert [call["tool"] for call in cluster()] == ["ssh", "srun"]
    peak = completed.results.peak[0]
    drive = create_calibration_platform("mock").qubits[0].drive
    parameters = json.loads(remote.state["parameters"])
    assert parameters["configs"][drive]["frequency"] == peak * 1e9

    # the next acquisition runs on the updated platform
    again = executor.acquire(bound)
    assert again.data.scale == {0: peak * 1e9}


def test_remote_update_approved(bound, cluster, mock_frequency):
    """Approved later, the update runs remotely, as when automatic."""
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, targets=TARGETS, update=False, runner=remote)
    completed = executor(bound)
    assert [call["tool"] for call in cluster()] == ["ssh", "srun"]
    assert completed.update([1]) == [1]
    # served by the agent: neither a new connection, nor the queue
    assert [call["tool"] for call in cluster()] == ["ssh", "srun"]
    drives = {t: create_calibration_platform("mock").qubits[t].drive for t in TARGETS}
    configs = json.loads(remote.state["parameters"])["configs"]
    assert configs[drives[1]]["frequency"] == completed.results.peak[1] * 1e9
    assert configs[drives[0]]["frequency"] == mock_frequency[0]  # not approved


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
    assert env == tmp_path / "cache" / "qibocamp" / "envs" / "fresh"
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
    monkeypatch.setenv("QIBOCAMP_NO_UV", "1")
    outcome = worker.install(
        {"venv": str(env), "python": "/usr/bin/python3.12", "requirements": "numpy"}
    )
    assert outcome["installed"]
    assert commands[0] == ["/usr/bin/python3.12", "-m", "venv", str(env)]
    python = str(worker.environment_python(env))
    assert commands[1][:4] == [python, "-m", "pip", "install"]


def test_session_records_remote(cluster, tmp_path):
    """Remote acquisitions are recorded, with the remote platform name."""
    path = tmp_path / "session"
    executor = Executor(
        None,
        path=path,
        targets=TARGETS,
        update=False,
        runner=Remote(queue="chip", platform="mock"),
    )
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    with executor:  # no local context: the session starts anyway
        executor(bound)
    assert json.loads((path / "meta.json").read_text())["platform"] == "mock"
    assert json.loads((path / "history.json").read_text()) == ["ramsey_signal-0"]
    assert (path / "data" / "ramsey_signal-0" / "results.json").is_file()


def test_session_remote_state(cluster, tmp_path, bound):
    """Remote updates are recorded, and attaching restores them remotely."""
    from qibocal_widgets import Session

    path = tmp_path / "session"
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(
        None, path=path, targets=TARGETS[:1], update=True, runner=remote
    )
    with pytest.warns(UserWarning, match="not a registered"):
        completed = executor(bound)
    peak = completed.results.peak[0]
    drive = create_calibration_platform("mock").qubits[0].drive
    recorded = json.loads((path / "new_platform" / "parameters.json").read_text())
    assert recorded["configs"][drive]["frequency"] == peak * 1e9
    # the initial state was asked to the remote machine, at the start
    initial = json.loads((path / "platform" / "parameters.json").read_text())
    original = create_calibration_platform("mock")
    assert initial["configs"][drive]["frequency"] == (
        original.config(original.qubits[0].drive).frequency
    )

    fresh = Remote(ssh="me@login", queue="chip", platform="mock")
    attached = Executor(
        None, session=Session.attach(path), targets=TARGETS[:1], runner=fresh
    )
    assert fresh.state == remote.state
    with pytest.warns(UserWarning):
        again = attached.acquire(bound)
    assert again.data.scale == {0: peak * 1e9}


def test_reference_of_copies():
    """Loaded executions hold copies of their protocol."""
    import copy

    assert jobs.protocol_reference(copy.deepcopy(protocols.ramsey_signal)) == (
        "qibocal.protocols:ramsey_signal"
    )


def test_platform_state_remote(cluster, tmp_path, mock_frequency):
    """Without a local platform, the state is asked to the remote machine."""
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, targets=TARGETS, runner=remote)
    state = executor.platform_state
    path = "parameters.configs.0/drive.frequency"
    assert state[path] == mock_frequency[0]
    # described once, on the access node (no queue)
    assert [call["tool"] for call in cluster()] == ["ssh"]
    state.update({path: 4.321e9})
    state[path]
    assert len(cluster()) == 1
    # edits travel with the next acquisition
    bound = fake(npoints=3)
    assert executor.acquire(bound).data.scale == {0: 4.321e9, 1: mock_frequency[1]}


def test_platforms_dir(cluster, monkeypatch, mock_frequency):
    """The platforms folder comes from the connection, not the environment."""
    monkeypatch.delenv("QIBOLAB_PLATFORMS")
    without = Executor(
        None, targets=TARGETS, runner=Remote(queue="chip", platform="mock")
    )
    with pytest.raises(RemoteError):
        without.acquire(fake(npoints=3))

    save_connection(
        "lab",
        Connection(
            queue="chip",
            platform="mock",
            platforms_dir=str(PLATFORMS),
            venv="qibocal",  # the environment prepared by the fixture
        ),
    )
    assert load_connection("lab").platforms_dir == str(PLATFORMS)
    executor = Executor(None, targets=TARGETS, runner=Remote("lab"))
    completed = executor.acquire(fake(npoints=3))
    assert completed.data.scale == mock_frequency


def test_submit_remote(cluster, tmp_path, monkeypatch, mock_frequency):
    """Remote acquisitions are queued together, and processed in order."""
    monkeypatch.setenv("FAKE_SLEEP", "1")
    path = tmp_path / "session"
    executor = Executor(
        None,
        path=path,
        targets=TARGETS,
        update=False,
        runner=Remote(queue="chip", platform="mock"),
    )
    starts = tmp_path / "starts"
    monkeypatch.setenv("FAKE_STARTS", str(starts))
    pendings = [executor.submit(fake(npoints=n)) for n in (3, 4, 5)]
    results = [pending.result(60) for pending in pendings]
    # queued together: all started before the first (sleeping 1 s) finished
    times = [float(line) for line in starts.read_text().split()]
    assert len(times) == 3 and max(times) - min(times) < 1
    assert [r.path.name for r in results] == ["fake-0", "fake-1", "fake-2"]
    assert all(r.data.scale == mock_frequency for r in results)
    assert [call["tool"] for call in cluster()].count("srun") == 3


def test_queued(cluster, monkeypatch, bound):
    """Until the worker reports its start, a queued job is queued."""
    monkeypatch.setenv("FAKE_SLEEP", "1")
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Remote(queue="chip", platform="mock"),
    )
    pending = executor.submit(bound)
    phases = [pending.phase]
    pending.on_change(lambda p: phases.append(p.phase))
    pending.result(60)
    # then the stages of the job, until the first estimate (none here)
    assert phases.index("queued") < phases.index("starting")
    assert phases.index("starting") < phases.index("importing")


def test_estimates_streamed(cluster, monkeypatch):
    """Duration estimates logged remotely reach the pending execution."""
    from fake import ESTIMATES, FakeParameters, estimated

    monkeypatch.setenv("FAKE_SLEEP", "1")
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Remote(queue="chip", platform="mock"),
    )
    pending = executor.submit(estimated(pars=FakeParameters(npoints=3)))
    phases = []
    pending.on_change(lambda p: phases.append(p.phase))
    pending.result(60)
    assert [e.seconds for e in pending.estimates] == list(ESTIMATES)
    assert [e.kind for e in pending.estimates] == ["execution", "batch"]
    # from the worker: when the job left the queue, and when it acquired
    kinds = [e.kind for e in pending.timeline.events if e.kind != "stage"]
    assert kinds == ["started", "execution", "batch", "acquired"]
    assert phases.index("running") < phases.index("transferring")
    assert pending.timeline.executions[0].measured is not None


def test_save_remote(cluster, tmp_path, bound):
    """Without a local platform, the state is written on the remote machine."""
    folder = tmp_path / "remote-platforms"
    shutil.copytree(PLATFORMS, folder)
    remote = Remote(
        ssh="me@login", queue="chip", platform="mock", platforms_dir=str(folder)
    )
    executor = Executor(None, targets=TARGETS, update=True, runner=remote)
    completed = executor(bound)
    path = executor.platform_state.save(overwrite=True)
    assert path == str(folder / "mock")
    # served by the agent, on the access node: no new connection, not queued
    assert [call["tool"] for call in cluster()] == ["ssh", "srun"]
    parameters = json.loads((folder / "mock" / "parameters.json").read_text())
    drive = create_calibration_platform("mock").qubits[0].drive
    assert parameters["configs"][drive]["frequency"] == completed.results.peak[0] * 1e9
    with pytest.raises(RemoteError, match="overwrite=True"):
        executor.platform_state.save()


def test_describe_platform_remote(cluster, bound):
    """Without a local platform, the layout comes from the remote machine."""
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, targets=TARGETS, update=False, runner=remote)
    layout = executor.describe_platform()
    assert [call["tool"] for call in cluster()] == ["ssh"]  # not queued
    assert layout.qubits[0]["drive"] == "0/drive"
    assert layout.channels["0/drive"]["lo"] == "0/drive_lo"
    assert executor.describe_platform() == layout  # once
    assert len(cluster()) == 1
    # changing the drive LO: the new value travels with the next acquisition
    path = layout.lo_config(layout.qubits[0]["drive"])
    executor.platform_state[f"{path}.frequency"] = 4.3e9
    executor.acquire(bound)
    configs = json.loads(remote.state["parameters"])["configs"]
    assert configs["0/drive_lo"]["frequency"] == 4.3e9


def test_profile(cluster):
    """Remote jobs report their stages: where the time went."""
    from qibocal import protocols

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
    phases = []
    pending = executor.submit(bound)
    pending.on_change(lambda p: phases.append(p.phase))
    pending.result(60)
    for phase in ("importing", "creating the platform", "connecting", "preparing"):
        assert phase in phases
    profile = pending.profile()
    steps = list(profile["step"])
    for step in (
        "queue and dispatch (ssh, srun)",
        "start of Python, in the environment",
        "imports (qibocal, qibolab, drivers)",
        "platform creation",
        "connection to the instruments",
        "disconnection",
        "data encoding",
        "data transfer and decoding",
        "fitting",
        "reporting",
    ):
        assert step in steps, step
    total = (pending.finished_at - pending.submitted_at).total_seconds()
    assert abs(profile["took (s)"].sum() - total) < 0.05  # it all adds up
    print(profile.to_string())


# -- agent ---------------------------------------------------------------------------


def test_agent_warm(cluster):
    """Without a queue, acquisitions run in the warm agent: imports done once."""
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", platform="mock"),
    )
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    first = executor.submit(bound)
    first.result(60)
    second = executor.submit(bound)
    second.result(60)
    assert [call["tool"] for call in cluster()] == ["ssh"]  # one connection
    for pending in (first, second):
        steps = dict(zip(*pending.profile()[["step", "took (s)"]].T.values))
        assert steps["imports (qibocal, qibolab, drivers)"] < 0.1  # already done


def test_agent_restarted(cluster, bound):
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, targets=TARGETS, update=False, runner=remote)
    executor.acquire(bound)
    agent = transport.agent(remote.connection)
    agent._process.kill()
    agent._process.wait()
    executor.acquire(bound)  # a new agent
    assert [call["tool"] for call in cluster()] == ["ssh", "srun", "ssh", "srun"]


def test_agent_exits_with_client(cluster, bound):
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    Executor(None, targets=TARGETS, update=False, runner=remote).acquire(bound)
    agent = transport.agent(remote.connection)
    transport.close_agents()
    assert agent._process.poll() is not None  # nothing left behind


def test_without_agent(cluster, bound):
    """With ``agent=False``, every step is a process of its own, as before."""
    remote = Remote(ssh="me@login", queue="chip", platform="mock", agent=False)
    executor = Executor(None, targets=TARGETS, update=True, runner=remote)
    executor(bound)
    assert [call["tool"] for call in cluster()] == ["ssh", "srun", "ssh", "ssh"]


# -- detached jobs -----------------------------------------------------------------


def _jobs_folder(tmp_path):
    return tmp_path / "cache" / "qibocamp" / "jobs"


def _lose_agent_while_running(cluster, tmp_path, monkeypatch, bound):
    """Submit a queued acquisition, then lose the agent (e.g. a disconnection)."""
    from qibocal_widgets import Session  # noqa: F401

    monkeypatch.setenv("FAKE_SLEEP", "2")
    path = tmp_path / "session"
    executor = Executor(
        None,
        path=path,
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", queue="chip", platform="mock"),
    )
    pending = executor.submit(bound, reuse=True)
    jobs_file = path / "remote-jobs.json"
    wait_for(lambda: jobs_file.exists())
    (name,) = json.loads(jobs_file.read_text())
    # launched remotely (its folder written), then the client disconnects
    wait_for(lambda: (_jobs_folder(tmp_path) / name / "pid").exists())
    transport.close_agents()
    with pytest.raises(RemoteError, match="agent") as error:
        pending.result(30)
    assert not error.value.ended  # the job goes on
    return path, name


def wait_for(condition, timeout=30):
    import time

    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_detached_survives(cluster, tmp_path, monkeypatch, bound):
    from qibocal_widgets import Session

    path, name = _lose_agent_while_running(cluster, tmp_path, monkeypatch, bound)
    assert (_jobs_folder(tmp_path) / name).is_dir()
    # after a restart: the same session, and the same submission
    restarted = Executor(
        None,
        session=Session.attach(path),
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", queue="chip", platform="mock"),
    )
    pending = restarted.submit(bound, reuse=True)
    completed = pending.result(60)
    assert completed.data.scale  # acquired by the detached job
    assert [call["tool"] for call in cluster()].count("srun") == 1  # not again
    assert not (path / "remote-jobs.json").exists()  # fetched: forgotten
    assert not (_jobs_folder(tmp_path) / name).exists()


def test_detached_done_meanwhile(cluster, tmp_path, monkeypatch, bound):
    from qibocal_widgets import Session

    path, name = _lose_agent_while_running(cluster, tmp_path, monkeypatch, bound)
    wait_for(lambda: (_jobs_folder(tmp_path) / name / "exit").exists())
    restarted = Executor(
        None,
        session=Session.attach(path),
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", queue="chip", platform="mock"),
    )
    pending = restarted.submit(bound, reuse=True)
    assert pending.result(60).data.scale
    assert [call["tool"] for call in cluster()].count("srun") == 1


def test_failed_job_forgotten(cluster, tmp_path):
    def _local(params, platform, targets):  # not importable remotely
        raise AssertionError

    local = Protocol(_local, None, None, None)
    path = tmp_path / "session"
    executor = Executor(
        None,
        path=path,
        targets=TARGETS,
        update=False,
        runner=Remote(queue="chip", platform="mock"),
    )
    executor.submit(fake(npoints=3), reuse=True).result(30)
    with pytest.raises(RemoteError):
        executor.submit(local(), reuse=True).result(30)
    assert not (path / "remote-jobs.json").exists()
    assert not any(_jobs_folder(tmp_path).iterdir())


def test_profile_report(cluster):
    """Blocking calls are profiled too; reports carry their context."""
    from qibocal import protocols

    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", queue="chip", platform="mock"),
    )
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    first = executor(bound)
    steps = list(first.profile()["step"])
    assert steps[0] == "agent start (once per session)"
    assert "fitting" in steps and "reporting" in steps
    second = executor(bound)
    assert "agent start (once per session)" not in list(second.profile()["step"])
    report = second.profile_report()
    print(first.profile_report())
    assert (
        "setup: remote, srun queue through ssh, agent, detached, agent warm" in report
    )
    assert "local: qibocal" in report and "remote: qibocal" in report
    assert "login" not in report  # no host names
    assert report.count("\n|") >= len(second.profile()) + 2
    csv = second.profile_report("csv")
    assert csv.startswith("# ramsey_signal") and "step,took (s),at (s)" in csv


def test_detached_never_launched(cluster, tmp_path, bound):
    """A job recorded, but never launched (lost just before): acquired again."""
    from qibocal_widgets import Session

    path = tmp_path / "session"
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, path=path, targets=TARGETS, update=False, runner=remote)
    first = executor.submit(bound, reuse=True)
    first.result(60)
    key = executor._reuse_key(bound, False, {})
    session = Session.attach(path)
    session.started = True
    session.track("lost", {"key": key, "submitted": "9999"})
    # the recorded execution would be reused from disk for registered
    # protocols: this one is not, so the job record is what is looked up
    again = Executor(None, session=Session.attach(path), targets=TARGETS, runner=remote)
    pending = again.submit(bound, reuse=True)
    assert pending.result(60).data.scale
    assert [call["tool"] for call in cluster()].count("srun") == 2
    assert "lost" not in Session.attach(path).jobs()


def test_platform_updates_remote(cluster, bound, mock_frequency):
    """Shipped with the job only: the runner's state is not changed."""
    remote = Remote(ssh="me@login", queue="chip", platform="mock")
    executor = Executor(None, targets=TARGETS, update=False, runner=remote)
    path = "configs.0/drive.frequency"
    completed = executor(bound, platform_updates={path: 4.5e9})
    assert completed.data.scale[0] == 4.5e9
    assert executor.platform_state[f"parameters.{path}"] == mock_frequency[0]
    assert executor.acquire(bound).data.scale[0] == mock_frequency[0]
    assert len(executor.history) == 0


# -- cancellation ------------------------------------------------------------------


def test_cancel_queued(cluster, tmp_path, monkeypatch, bound):
    """A queued job is stopped, and forgotten."""
    monkeypatch.setenv("FAKE_SLEEP", "30")  # e.g. waiting in the queue
    path = tmp_path / "session"
    executor = Executor(
        None,
        path=path,
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", queue="chip", platform="mock"),
    )
    pending = executor.submit(bound)
    wait_for(lambda: (path / "remote-jobs.json").exists())
    (name,) = json.loads((path / "remote-jobs.json").read_text())
    wait_for(lambda: (_jobs_folder(tmp_path) / name / "pid").exists())
    start = __import__("time").monotonic()
    assert pending.cancel()
    from qibocal_widgets import Cancelled

    with pytest.raises(Cancelled):
        pending.result(20)
    assert __import__("time").monotonic() - start < 5  # not the 30 s
    assert pending.status == "cancelled"
    wait_for(lambda: not (path / "remote-jobs.json").exists())
    assert not (_jobs_folder(tmp_path) / name).exists()


def test_cancel_in_agent(cluster):
    """Without a queue, the acquisition stops between platform executions."""
    from fake import EXECUTIONS, FakeParameters, looped

    from qibocal_widgets import Cancelled

    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Remote(ssh="me@login", platform="mock"),
    )
    pending = executor.submit(looped(pars=FakeParameters(npoints=3)))
    wait_for(lambda: len(pending.timeline.executions) >= 2)
    pending.cancel()
    with pytest.raises(Cancelled):
        pending.result(20)
    assert len(pending.timeline.executions) < EXECUTIONS
    # the agent is still serving
    assert executor.acquire(fake(npoints=3)).data.scale

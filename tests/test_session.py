"""Recording executions in session folders."""

import json
import warnings

import pytest
from conftest import PLATFORMS, TARGETS
from fake import fake
from qibocal import Executor as QibocalExecutor
from qibocal import protocols
from qibocal.auto.output import Output
from qibocal.auto.task import Completed as QibocalCompleted
from qibocal.cli.report import generate_figures_and_report

from qibocal_widgets import Executor, Session, SessionExists
from qibocal_widgets.marimo import Marimo


@pytest.fixture(autouse=True)
def mock(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))


@pytest.fixture
def ramsey():
    return protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )


def history(path):
    return json.loads((path / "history.json").read_text())


def meta(path):
    return json.loads((path / "meta.json").read_text())


def test_records_and_appends(tmp_path, ramsey):
    path = tmp_path / "session"
    executor = Executor.create(path, platform="mock", targets=TARGETS, update=False)
    with executor:
        first = executor(ramsey)
    with executor:
        second = executor(ramsey)

    assert first.path == path / "data" / "ramsey_signal-0"
    assert second.path == path / "data" / "ramsey_signal-1"
    assert history(path) == ["ramsey_signal-0", "ramsey_signal-1"]
    assert set(meta(path)["stats"]) == {"ramsey_signal-0", "ramsey_signal-1"}
    assert meta(path)["end_time"] is not None
    task = path / "data" / "ramsey_signal-0"
    assert {"action.yml", "data.json", "data.npz", "results.json"} <= {
        p.name for p in task.iterdir()
    }
    assert (path / "platform" / "parameters.json").is_file()


def test_readable_by_qibocal(tmp_path, ramsey):
    """The folder loads, and renders, as the report server does it."""
    path = tmp_path / "session"
    executor = Executor.create(path, platform="mock", targets=TARGETS, update=False)
    with executor:
        executor(ramsey, nshots=64)

    ((task_id, _),) = Output.load(path).history.items()
    completed = QibocalCompleted.load(path / "data" / str(task_id))
    assert completed.task.parameters.nshots == 64
    assert sorted(completed.task.targets) == TARGETS
    figures, table = generate_figures_and_report(completed, 0)
    assert figures
    assert "<table" in table


def test_refit_overwrites(tmp_path, ramsey):
    executor = Executor.create(
        tmp_path / "session", platform="mock", targets=TARGETS, update=False
    )
    with executor:
        acquired = executor.acquire(ramsey)
    assert not (acquired.path / "results.json").exists()
    first = executor.fit(acquired)
    second = executor.fit(acquired)
    assert first.path == second.path == acquired.path
    assert (acquired.path / "results.json").is_file()
    assert history(executor.path) == ["ramsey_signal-0"]
    # the report step records nothing new
    executor.report(second)
    assert history(executor.path) == ["ramsey_signal-0"]


def test_foreign_execution(tmp_path, ramsey, monkeypatch):
    """Executions from elsewhere become new tasks, with their data."""
    from qibocal import create_calibration_platform

    platform = create_calibration_platform("mock")
    plain = QibocalExecutor(platform, targets=TARGETS, update=False)
    platform.connect()
    acquired = plain.acquire(ramsey)
    platform.disconnect()

    executor = Executor.create(tmp_path / "session", platform="mock", targets=TARGETS)
    fitted = executor.fit(acquired)
    assert fitted.path == executor.path / "data" / "ramsey_signal-0"
    assert {"data.json", "data.npz", "results.json"} <= {
        p.name for p in fitted.path.iterdir()
    }


def test_update_records_platform(tmp_path, bound):
    executor = Executor.create(
        tmp_path / "session", platform="mock", targets=TARGETS[:1], update=True
    )
    with pytest.warns(UserWarning, match="not a registered"):
        completed = executor(bound)
    parameters = json.loads(
        (executor.path / "new_platform" / "parameters.json").read_text()
    )
    drive = executor.platform.qubits[0].drive
    assert parameters["configs"][drive]["frequency"] == (
        completed.results.peak[0] * 1e9
    )


def test_unregistered_protocol(tmp_path, bound):
    """Recorded, but kept out of the history, which Qibocal could not load."""
    executor = Executor.create(tmp_path / "session", platform="mock", targets=TARGETS)
    with pytest.warns(UserWarning, match="fake:fake is not a registered"):
        completed = executor.acquire(bound)
    assert completed.path == executor.path / "data" / "fake-0"
    assert "operation: fake:fake" in (completed.path / "action.yml").read_text()
    assert history(executor.path) == []
    Output.load(executor.path)


def test_lazy_start_without_context(tmp_path, bound):
    """Remote executions never enter the context: the first record starts."""
    path = tmp_path / "session"
    executor = Executor(None, path=path, targets=TARGETS, update=False)
    assert not path.exists()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        executor(bound)
    assert meta(path)["platform"] == "unknown"
    assert (path / "data" / "fake-0" / "results.json").is_file()


def test_no_path_no_session(bound):
    executor = Executor(None, targets=TARGETS, update=False)
    assert executor.session is None
    assert executor(bound).path is None


def test_existing_folder(tmp_path, ramsey):
    path = tmp_path / "session"
    (path / "data").mkdir(parents=True)
    executor = Executor.create(path, platform="mock", targets=TARGETS)
    with pytest.raises(SessionExists, match="attach"), executor:
        pass
    # replaced on request
    with Executor.open(path, platform="mock", targets=TARGETS, force=True):
        pass
    assert history(path) == []


def test_attach(tmp_path, ramsey, bound):
    path = tmp_path / "session"
    first = Executor.create(path, platform="mock", targets=TARGETS[:1], update=True)
    with first:
        first(ramsey)
    with pytest.warns(UserWarning):
        updated = first(bound)  # updates the drive frequency
    start = meta(path)["start_time"]

    executor = Executor.attach(path, targets=TARGETS[:1], update=False)
    assert executor.platform.name == "mock"  # from the session metadata
    drive = executor.platform.qubits[0].drive
    # the calibration continues where the session left it
    assert executor.platform.config(drive).frequency == updated.results.peak[0] * 1e9
    with executor:
        executor(ramsey)

    assert history(path) == ["ramsey_signal-0", "ramsey_signal-1"]
    assert meta(path)["start_time"] == start
    assert {"ramsey_signal-0", "fake-0", "ramsey_signal-1"} <= set(meta(path)["stats"])


def test_attach_without_session(tmp_path):
    with pytest.raises(FileNotFoundError, match="meta.json"):
        Executor.attach(tmp_path)


def test_attach_with_explicit_session(tmp_path, ramsey):
    """Remote executors, without a local platform, attach through a Session."""
    path = tmp_path / "session"
    with Executor.open(path, platform="mock", targets=TARGETS, update=False) as first:
        first(ramsey)
    executor = Executor(None, session=Session.attach(path), targets=TARGETS)
    assert executor.path == path
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        executor.acquire(fake(npoints=3))
    assert (path / "data" / "fake-0").is_dir()
    assert history(path) == ["ramsey_signal-0"]


def test_new_session(tmp_path, ramsey, monkeypatch):
    first = tmp_path / "first"
    executor = Executor.create(first, platform="mock", targets=TARGETS, update=False)
    with executor:
        acquired = executor.acquire(ramsey)

    second = tmp_path / "second"
    session = executor.new_session(second)
    assert executor.path == second == session.path
    with executor:
        executor.acquire(ramsey)
    # fitting an acquisition of the previous session records it anew
    executor.fit(acquired)
    assert history(first) == ["ramsey_signal-0"]
    assert history(second) == ["ramsey_signal-0", "ramsey_signal-1"]
    assert meta(second)["stats"].keys() == {"ramsey_signal-0", "ramsey_signal-1"}

    # by default, under the reports folder
    monkeypatch.setenv("QIBOCAL_REPORTS_DIR", str(tmp_path / "reports"))
    assert executor.new_session().path.parent == tmp_path / "reports"
    monkeypatch.delenv("QIBOCAL_REPORTS_DIR")
    with pytest.raises(TypeError, match="QIBOCAL_REPORTS_DIR"):
        executor.new_session()


def test_frontends_on_recorded(tmp_path, ramsey):
    executor = Executor.create(
        tmp_path / "session",
        platform="mock",
        targets=TARGETS,
        update=False,
        frontends=[Marimo()],
    )
    with executor:
        completed = executor(ramsey)
    assert "_display_" in completed.views
    assert completed.path.parent == executor.path / "data"

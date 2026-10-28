"""Background executions (Executor.submit)."""

import asyncio
import threading
import time

import pytest
from conftest import TARGETS
from fake import FakeData, fake
from qibocal import Executor as QibocalExecutor

from qibocal_widgets import Completed, Executor, Pending, Runner
from qibocal_widgets._core.remote import worker
from qibocal_widgets._core.remote.worker import _scrape


class Gated(Runner):
    """A concurrent runner whose acquisitions complete when released."""

    concurrent = True

    def __init__(self):
        self.gates = {}
        self.started = []
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def gate(self, npoints):
        return self.gates.setdefault(npoints, threading.Event())

    def acquire(self, executor, bound, **kwargs):
        with self.lock:
            self.started.append(bound.parameters.npoints)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            assert self.gate(bound.parameters.npoints).wait(10)
            return QibocalExecutor.acquire(executor, bound, **kwargs)
        finally:
            with self.lock:
                self.active -= 1


class Serial(Gated):
    """The same, but sharing the instruments, as the local runner."""

    concurrent = False


def wait_for(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_submit_returns_immediately(bound):
    runner = Gated()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    pending = executor.submit(bound)
    assert isinstance(pending, Pending)
    wait_for(lambda: pending.status == "acquiring")
    assert not pending.done()
    runner.gate(bound.parameters.npoints).set()
    completed = pending.result(timeout=10)
    assert isinstance(completed, Completed)
    assert set(completed.reports) == set(TARGETS)
    assert pending.status == "done"


def test_concurrent_acquisitions_processed_in_order(tmp_path):
    runner = Gated()
    path = tmp_path / "session"
    executor = Executor(None, path=path, targets=TARGETS, update=False, runner=runner)
    first, second = executor.submit(fake(npoints=3)), executor.submit(fake(npoints=4))
    wait_for(lambda: len(runner.started) == 2)
    assert runner.peak == 2  # queued together
    runner.gate(4).set()  # the second acquisition completes first
    wait_for(lambda: second.status == "processing")
    time.sleep(0.1)
    assert not second.done()  # but waits for the first to be processed
    runner.gate(3).set()
    a, b = first.result(10), second.result(10)
    # recorded in submission order
    assert a.path.name == "fake-0" and b.path.name == "fake-1"


def test_serial_acquisitions(bound):
    runner = Serial()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    first, second = executor.submit(fake(npoints=3)), executor.submit(fake(npoints=4))
    wait_for(lambda: runner.started == [3])
    time.sleep(0.1)
    assert second.status == "waiting"  # for the instruments
    runner.gate(3).set()
    runner.gate(4).set()
    first.result(10), second.result(10)
    assert runner.peak == 1


def test_updates_in_submission_order(monkeypatch):
    from conftest import PLATFORMS
    from qibocal import create_calibration_platform

    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    runner = Gated()
    platform = create_calibration_platform("mock")
    executor = Executor(platform, targets=TARGETS[:1], update=True, runner=runner)
    first, second = executor.submit(fake(npoints=3)), executor.submit(fake(npoints=5))
    runner.gate(5).set()
    runner.gate(3).set()
    first.result(10)
    last = second.result(10)
    drive = platform.qubits[0].drive
    # the later submission's update is the last applied
    assert platform.config(drive).frequency == last.results.peak[0] * 1e9


def test_failure_does_not_block_the_next(bound):
    class Broken(Gated):
        def acquire(self, executor, bound, **kwargs):
            if bound.parameters.npoints == 3:
                raise RuntimeError("boom")
            return super().acquire(executor, bound, **kwargs)

    runner = Broken()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    failed, ok = executor.submit(fake(npoints=3)), executor.submit(fake(npoints=4))
    runner.gate(4).set()
    with pytest.raises(RuntimeError, match="boom"):
        failed.result(10)
    assert failed.status == "failed"
    assert "boom" in failed.describe()
    assert isinstance(ok.result(10), Completed)


def test_await(bound):
    runner = Gated()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)

    async def main():
        pending = executor.submit(bound)
        runner.gate(bound.parameters.npoints).set()
        return await pending

    assert isinstance(asyncio.run(main()), Completed)


def test_gather():
    runner = Gated()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)

    async def main():
        a, b = executor.submit(fake(npoints=3)), executor.submit(fake(npoints=4))
        runner.gate(3).set()
        runner.gate(4).set()
        return await asyncio.gather(a, b)

    a, b = asyncio.run(main())
    assert len(a.data[0]) == 3 and len(b.data[0]) == 4


def test_local_runner_manages_the_context(bound):
    """No ``with executor:`` needed: the execution opens it itself."""
    events = []

    class Recording(Runner):
        def open(self, executor):
            events.append("open")

        def close(self, executor):
            events.append("close")

    executor = Executor(None, targets=TARGETS, update=False, runner=Recording())
    executor.submit(bound).result(10)
    assert events == ["open", "close"]


def test_frontends(bound):
    pytest.importorskip("marimo")
    widgets = pytest.importorskip("ipywidgets")
    from qibocal_widgets.jupyter import Jupyter
    from qibocal_widgets.marimo import Marimo

    runner = Gated()
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=runner,
        frontends=[Marimo(), Jupyter()],
    )
    pending = executor.submit(bound)
    wait_for(lambda: pending.status == "acquiring")
    spinner = pending._display_()
    assert type(spinner).__name__ == "spinner"  # outside notebooks: no reactivity
    assert pending() is None
    box = pending.views["_repr_mimebundle_"](pending)
    assert isinstance(box, widgets.VBox)
    assert "acquiring" in box.children[0].value
    runner.gate(bound.parameters.npoints).set()
    completed = pending.result(10)
    wait_for(lambda: isinstance(box.children[0], widgets.Tab))  # updated live
    assert "Target 0" in pending._display_().text
    assert "_display_" in completed.views


def test_repr(bound):
    runner = Gated()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    pending = executor.submit(bound)
    assert repr(pending).startswith("<Pending fake:")
    assert pending._repr_mimebundle_() is None  # no Jupyter frontend
    runner.gate(bound.parameters.npoints).set()
    pending.result(10)
    assert isinstance(pending.result().data, FakeData)


def test_peek(bound):
    runner = Gated()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    pending = executor.submit(bound)
    assert pending() is None
    runner.gate(bound.parameters.npoints).set()
    completed = pending.result(10)
    assert pending() is completed


def test_peek_failure(bound):
    class Broken(Runner):
        def acquire(self, executor, bound, **kwargs):
            raise RuntimeError("boom")

    pending = Executor(None, targets=TARGETS, runner=Broken()).submit(bound)
    with pytest.raises(RuntimeError):
        pending.result(10)
    with pytest.raises(RuntimeError, match="boom"):
        pending()


class Counting(Runner):
    """Count the acquisitions."""

    concurrent = True

    def __init__(self):
        self.count = 0
        self.gate = threading.Event()

    def acquire(self, executor, bound, **kwargs):
        self.count += 1
        assert self.gate.wait(10)
        return QibocalExecutor.acquire(executor, bound, **kwargs)


def test_reuse_running(bound):
    runner = Counting()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    first = executor.submit(bound, reuse=True)
    assert executor.submit(bound, reuse=True) is first
    assert executor.submit(bound) is not first  # without reuse, acquired again
    other = executor.submit(fake(npoints=5), reuse=True)
    assert other is not first  # different parameters
    runner.gate.set()
    first.result(10), other.result(10)
    wait_for(lambda: runner.count == 3)


def test_reuse_recorded(tmp_path, monkeypatch):
    from conftest import PLATFORMS
    from qibocal import create_calibration_platform, protocols

    from qibocal_widgets import Session

    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    runner = Counting()
    runner.gate.set()
    path = tmp_path / "session"
    executor = Executor(
        create_calibration_platform("mock"),
        path=path,
        targets=TARGETS,
        update=False,
        runner=runner,
    )
    first = executor.submit(bound, reuse=True).result(10)
    assert (first.path / "qibocal-widgets.json").is_file()

    again = executor.submit(bound, reuse=True)
    assert again.done()  # loaded from disk, at once
    assert runner.count == 1
    assert again().path == first.path
    assert set(again().reports) == set(TARGETS)

    # after a restart, attaching the session
    restarted = Executor(
        create_calibration_platform("mock"),
        session=Session.attach(path),
        targets=TARGETS,
        update=False,
        runner=runner,
    )
    assert restarted.submit(bound, reuse=True)().path == first.path
    assert runner.count == 1
    # with other overrides, acquired again
    restarted.submit(bound, reuse=True, nshots=7).result(10)
    assert runner.count == 2


def test_reuse_unregistered_not_from_disk(tmp_path, bound):
    """Unregistered protocols cannot be loaded back: acquired again."""
    runner = Counting()
    runner.gate.set()
    executor = Executor(
        None, path=tmp_path / "s", targets=TARGETS, update=False, runner=runner
    )
    executor.submit(bound, reuse=True).result(10)
    executor.submit(bound, reuse=True).result(10)
    assert runner.count == 2


def test_reuse_platform_state(monkeypatch, bound):
    from conftest import PLATFORMS
    from qibocal import create_calibration_platform

    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    runner = Counting()
    executor = Executor(
        create_calibration_platform("mock"),
        targets=TARGETS,
        update=False,
        runner=runner,
    )
    first = executor.submit(bound, reuse=True)
    executor.platform_state.update({"configs.0/drive.frequency": 4.2e9})
    # e.g. updated by another execution: still identical
    assert executor.submit(bound, reuse=True) is first
    runner.gate.set()
    first.result(10)
    assert runner.count == 1


# -- duration estimates ------------------------------------------------------------


def test_estimates_captured():
    import logging

    from fake import ESTIMATES, FakeParameters, estimated

    loggers = [logging.getLogger(name) for name in worker.ESTIMATE_LOGGERS]
    levels = [logger.level for logger in loggers]
    gate = threading.Event()

    class Late(Runner):
        """Acquire, then wait: still acquiring, once estimated."""

        def acquire(self, executor, bound, **kwargs):
            completed = QibocalExecutor.acquire(executor, bound, **kwargs)
            assert gate.wait(10)
            return completed

    executor = Executor(None, targets=TARGETS, update=False, runner=Late())
    pending = executor.submit(estimated(pars=FakeParameters(npoints=3)))
    wait_for(lambda: len(pending.estimates) == 2)
    assert [e.seconds for e in pending.estimates] == list(ESTIMATES)
    assert [e.kind for e in pending.estimates] == ["execution", "batch"]
    bar = pending.progress()
    assert "estimated 2.5 s (estimate 2, first 2 s)" in bar
    assert "batches done: 0/?" in bar
    assert "animation: qibocal-widgets-progress 2.500s linear" in bar
    gate.set()
    pending.result(10)
    assert pending.progress() is None  # only while acquiring
    # the loggers are left as they were
    assert [logger.level for logger in loggers] == levels
    assert all(_scrape not in logger.filters for logger in loggers)


def test_estimates_hidden_unless_enabled(caplog):
    """Loggers enabled for the estimates do not emit more than before."""
    import logging

    caplog.set_level(logging.WARNING)
    seen = []
    logger = logging.getLogger(next(iter(worker.ESTIMATE_LOGGERS)))
    with worker.estimates(lambda seconds, kind: seen.append((seconds, kind))):
        logger.info("Pulse execution time: 1.500 s")
        logger.info("unrelated")
        other = threading.Thread(
            target=logger.info, args=("Pulse execution time: 9 s",)
        )
        other.start()
        other.join()
    assert seen == [(1.5, "execution")]  # only from the capturing thread
    assert not caplog.records

    caplog.set_level(logging.INFO)
    with worker.estimates(lambda seconds, kind: seen.append((seconds, kind))):
        logger.info("Pulse execution time: 3 s")
    assert seen == [(1.5, "execution"), (3.0, "execution")]
    assert [r.getMessage() for r in caplog.records] == ["Pulse execution time: 3 s"]


def test_estimate_views(bound):
    pytest.importorskip("marimo")
    widgets = pytest.importorskip("ipywidgets")
    from qibocal_widgets.jupyter import Jupyter
    from qibocal_widgets.marimo import Marimo

    runner = Gated()
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=runner,
        frontends=[Marimo(), Jupyter()],
    )
    pending = executor.submit(bound)
    wait_for(lambda: pending.status == "acquiring")
    box = pending.views["_repr_mimebundle_"](pending)
    pending._estimate(90.0)
    wait_for(lambda: "progress" in box.children[0].value)  # updated live
    assert "estimated 1 min 30 s" in box.children[0].value
    assert "1 min 30 s" in pending._display_().text
    runner.gate(bound.parameters.npoints).set()
    pending.result(10)
    wait_for(lambda: isinstance(box.children[0], widgets.Tab))


def test_batches(bound):
    runner = Gated()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    pending = executor.submit(bound)
    wait_for(lambda: pending.status == "acquiring")
    pending._estimate(10.0)
    assert pending.batches == 0
    assert "batches" not in pending.progress()  # no driver estimate
    for seconds in (4.0, 4.0, 3.0):
        pending._estimate(seconds, "batch")
    assert pending.batches == 3
    assert "batches done: 2/?" in pending.progress()
    pending._estimate(10.0)  # the next execution on the platform
    assert pending.batches == 0
    pending._estimate(5.0, "batch")
    assert "batches done: 0/?" in pending.progress()
    runner.gate(bound.parameters.npoints).set()
    pending.result(10)

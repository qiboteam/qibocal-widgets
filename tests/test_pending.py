"""Background executions (Executor.submit)."""

import asyncio
import threading
import time

import pytest
from conftest import TARGETS
from fake import FakeData, fake
from qibocal import Executor as QibocalExecutor

from qibocal_widgets import Completed, Executor, Pending, Runner


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
    assert "acquiring" in pending._display_().text
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

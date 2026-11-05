"""Cancelling executions (``pending.cancel``)."""

import threading
import time

import pytest
from conftest import TARGETS
from fake import EXECUTIONS, FakeParameters, fake, looped
from qibocal import Executor as QibocalExecutor

from qibocal_widgets import Cancelled, Executor, Frontend, Runner


class Counting(Runner):
    def __init__(self):
        self.count = 0
        self.gate = threading.Event()
        self.gate.set()

    def acquire(self, executor, bound, **kwargs):
        self.count += 1
        assert self.gate.wait(10)
        return QibocalExecutor.acquire(executor, bound, **kwargs)


class Confirmable(Frontend):
    protocol = "_confirmable_"

    def render(self, completed):
        return None

    def confirmable(self):
        return True


def wait_for(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_ready():
    runner = Counting()
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=runner,
        frontends=[Confirmable()],
        confirm=True,
    )
    pending = executor.submit(fake(npoints=3), reuse=True)
    assert pending.cancel()
    assert pending.status == "cancelled" and pending.describe().endswith("cancelled")
    with pytest.raises(Cancelled):
        pending.result(1)
    pending.start()  # nothing to start
    time.sleep(0.1)
    assert runner.count == 0
    again = executor.submit(fake(npoints=3), reuse=True)
    assert again is not pending  # not reused


def test_waiting():
    runner = Counting()
    runner.gate.clear()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner)
    first = executor.submit(fake(npoints=3))
    second = executor.submit(fake(npoints=4))  # waits for the instruments
    wait_for(lambda: first.status == "acquiring")
    assert second.status == "waiting"
    assert second.cancel()
    runner.gate.set()
    first.result(10)
    with pytest.raises(Cancelled):
        second.result(10)
    assert runner.count == 1  # never acquired
    assert second.status == "cancelled"


def test_acquiring_stops_between_executions():
    executor = Executor(None, targets=TARGETS, update=False)
    pending = executor.submit(looped(pars=FakeParameters(npoints=3)))
    wait_for(lambda: len(pending.timeline.executions) >= 2)
    assert pending.cancel() and pending.cancelling
    with pytest.raises(Cancelled):
        pending.result(10)
    assert len(pending.timeline.executions) < EXECUTIONS  # stopped early
    assert pending.status == "cancelled" and not pending.cancelling


def test_not_while_processing():
    executor = Executor(None, targets=TARGETS, update=False)
    pending = executor.submit(fake(npoints=3))
    pending.result(10)
    wait_for(lambda: pending.status == "done")
    assert not pending.cancel()


def test_run_again_after_cancel():
    executor = Executor(None, targets=TARGETS, update=False)
    pending = executor.submit(looped(pars=FakeParameters(npoints=3)))
    wait_for(lambda: pending.timeline.executions)
    pending.cancel()
    with pytest.raises(Cancelled):
        pending.result(10)
    pending.rerun()
    assert pending.result(30).data.scale  # a fresh run, not cancelled


def test_cancel_button():
    pytest.importorskip("anywidget")
    from qibocal_widgets._core.progress_view import ProgressView

    executor = Executor(None, targets=TARGETS, update=False)
    pending = executor.submit(looped(pars=FakeParameters(npoints=3)))
    wait_for(lambda: pending.status == "acquiring")
    view = ProgressView(pending, schedule=lambda f, *args: f(*args))
    assert view.cancellable and not view.cancelling
    view._message(view, {"kind": "cancel"}, [])
    assert view.cancelling
    with pytest.raises(Cancelled):
        pending.result(10)

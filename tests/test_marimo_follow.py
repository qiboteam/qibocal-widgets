"""Pending executions followed by the cell runs displaying them (Marimo).

Cell runs are simulated: the current cell and run come from a fake marimo
context, and `mo.Thread` is a plain thread, invalidated when its run is
superseded, as marimo does when the cell runs again.
"""

import threading
import time

import pytest

pytest.importorskip("marimo")

from conftest import TARGETS
from fake import fake
from qibocal import Executor as QibocalExecutor

from qibocal_widgets import Executor, Runner
from qibocal_widgets._core import marimo as frontend
from qibocal_widgets.marimo import Marimo


class Cells:
    """Fake marimo runs of a single cell."""

    def __init__(self):
        self.run = object()
        self.runs = {}  # thread -> run it was spawned by
        self.outputs = []  # (run, object) replaced, in order

    def again(self):
        """Run the cell again: a new run, its threads should exit."""
        self.run = object()

    def current(self):
        run = self.runs.get(threading.current_thread(), self.run)
        return "cell", run


class Gated(Runner):
    concurrent = True

    def __init__(self):
        self.gate = threading.Event()
        self.count = 0

    def acquire(self, executor, bound, **kwargs):
        self.count += 1
        assert self.gate.wait(10)
        return QibocalExecutor.acquire(executor, bound, **kwargs)


@pytest.fixture
def cells(monkeypatch):
    cells = Cells()
    mo = frontend.mo

    class Thread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            cells.runs[self] = cells.run

        @property
        def should_exit(self):
            return cells.runs[self] is not cells.run

    def replace(obj):
        cells.outputs.append((cells.current()[1], obj))

    monkeypatch.setattr(mo, "running_in_notebook", lambda: True)
    monkeypatch.setattr(mo, "Thread", Thread)
    monkeypatch.setattr(mo, "current_thread", threading.current_thread)
    monkeypatch.setattr(mo.output, "replace", replace)
    monkeypatch.setattr(frontend, "_run", cells.current)
    monkeypatch.setattr(frontend, "POLL", 0.02)
    frontend._RENDERED.clear()
    return cells


def shown(cells):
    """Text of the replaced outputs."""
    return [getattr(obj, "text", "") for _, obj in cells.outputs]


def wait_for(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def executor(runner):
    return Executor(
        None, targets=TARGETS, update=False, runner=runner, frontends=[Marimo()]
    )


def test_spinner_replaced(cells):
    runner = Gated()
    pending = executor(runner).submit(fake(npoints=3))
    assert isinstance(pending, frontend.MarimoPending)
    pending._display_()  # the cell output: a spinner
    pending._estimate(3.0)
    wait_for(lambda: any("estimated 3 s" in t for t in shown(cells)))  # progress
    runner.gate.set()
    pending.result(10)
    wait_for(lambda: "Target 0" in shown(cells)[-1])  # the result


def test_reused_in_a_later_run(cells):
    """The run reusing a running execution follows it: not the first one."""
    runner = Gated()
    ex = executor(runner)
    first = ex.submit(fake(npoints=3), reuse=True)
    first._display_()
    cells.again()
    again = ex.submit(fake(npoints=3), reuse=True)
    assert again is first and runner.count <= 1
    again._display_()
    runner.gate.set()
    first.result(10)
    wait_for(lambda: cells.outputs and "Target 0" in shown(cells)[-1])
    assert all(run is cells.run for run, _ in cells.outputs)  # only the latest


def test_other_executions_displayed_earlier(cells):
    """Executions displayed by previous runs do not prevent replacing."""
    runner = Gated()
    ex = executor(runner)
    runner.gate.set()
    ex.submit(fake(npoints=3))._display_()
    cells.again()
    runner.gate.clear()
    pending = ex.submit(fake(npoints=4))
    pending._display_()
    runner.gate.set()
    pending.result(10)
    wait_for(lambda: cells.outputs and cells.outputs[-1][0] is cells.run)
    wait_for(lambda: shown(cells) and "Target 0" in shown(cells)[-1])


def test_several_in_one_cell_not_replaced(cells):
    runner = Gated()
    ex = executor(runner)
    a, b = ex.submit(fake(npoints=3)), ex.submit(fake(npoints=4))
    a._display_(), b._display_()
    runner.gate.set()
    a.result(10), b.result(10)
    time.sleep(0.2)
    assert not cells.outputs


def test_result_set_before_status(cells):
    """`done()` turns true before the status: following must not stop there."""
    marimo = Marimo()
    pending = frontend.MarimoPending(fake(npoints=3))
    pending.views[marimo.protocol] = marimo.render_pending
    marimo.submitted(pending)
    pending._set("processing")
    pending._display_()
    wait_for(lambda: shown(cells))  # the processing spinner
    pending.future.set_result(None)  # as `_resolve`, before setting the status
    time.sleep(0.2)
    pending._set("failed")  # any final state, rendered without a result
    wait_for(lambda: "failed" in shown(cells)[-1])


def test_confirmed_by_click(cells):
    """The click only confirms: the follower of the cell run launches it."""
    from qibocal_widgets._core.button import Button

    runner = Gated()
    runner.gate.set()
    ex = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=runner,
        frontends=[Marimo()],
        confirm=True,
    )
    pending = ex.submit(fake(npoints=3))
    assert pending.status == "ready"
    view = pending._display_()
    button = view.widget if hasattr(view, "widget") else view._widget
    assert isinstance(button, Button)
    launched_in = []
    original = pending._launcher
    pending._launcher = lambda: (
        launched_in.append(threading.current_thread()),
        original(),
    )
    clicker = threading.Thread(target=button.click)  # as a frontend message
    clicker.start()
    clicker.join()
    pending.result(10)
    assert launched_in and launched_in[0] is not clicker  # by the follower
    wait_for(lambda: shown(cells) and "Target 0" in shown(cells)[-1])


def test_run_again_by_click(cells):
    """The follower of a completed execution launches it again, when clicked."""
    runner = Gated()
    ex = executor(runner)
    pending = ex.submit(fake(npoints=3))
    pending._display_()  # while running
    runner.gate.set()
    pending.result(10)
    wait_for(lambda: shown(cells) and "Target 0" in shown(cells)[-1])
    replaced = len(cells.outputs)
    original = pending._rerun
    launched_in = []
    pending._rerun = lambda: (
        launched_in.append(threading.current_thread()),
        original(),
    )
    clicker = threading.Thread(target=pending.rerun)  # as the button does
    clicker.start()
    clicker.join()
    wait_for(lambda: runner.count == 2 and pending.status == "done")
    assert launched_in and launched_in[0] is not clicker  # by the follower
    wait_for(lambda: len(cells.outputs) > replaced and "Target 0" in shown(cells)[-1])

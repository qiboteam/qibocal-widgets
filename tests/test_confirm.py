"""Executions waiting for confirmation (``confirm``), and the ``reuse`` default."""

import threading
import time

import pytest
from conftest import PLATFORMS, TARGETS
from fake import fake
from qibocal import Executor as QibocalExecutor

from qibocal_widgets import Completed, Executor, Frontend, Runner
from qibocal_widgets._core.pending import NotStartedError


class Counting(Runner):
    concurrent = True

    def __init__(self):
        self.count = 0

    def acquire(self, executor, bound, **kwargs):
        self.count += 1
        return QibocalExecutor.acquire(executor, bound, **kwargs)


class Confirmable(Frontend):
    """A frontend able to show the Run button, rendering nothing."""

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


def test_waits_for_confirmation():
    runner = Counting()
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=runner,
        frontends=[Confirmable()],
        confirm=True,
    )
    pending = executor.submit(fake(npoints=3))
    time.sleep(0.1)
    assert pending.status == "ready" and runner.count == 0
    assert pending() is None
    assert "waiting for confirmation" in pending.describe()
    with pytest.raises(NotStartedError, match="pending.start"):
        pending.result()
    pending.start()
    assert isinstance(pending.result(10), Completed)
    assert runner.count == 1
    pending.start()  # already started: nothing happens
    time.sleep(0.1)
    assert runner.count == 1


def test_starts_at_once_without_confirmable_frontend():
    runner = Counting()
    executor = Executor(
        None, targets=TARGETS, update=False, runner=runner, confirm=True
    )
    assert isinstance(executor.submit(fake(npoints=3)).result(10), Completed)


def test_per_submission():
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Counting(),
        frontends=[Confirmable()],
    )
    assert executor.submit(fake(npoints=3), confirm=True).status == "ready"
    executor.confirm = True
    started = executor.submit(fake(npoints=3), confirm=False)
    assert isinstance(started.result(10), Completed)


def test_ready_does_not_block_the_others(tmp_path):
    """Executions take their processing turn when they start."""
    executor = Executor(
        None,
        path=tmp_path / "s",
        targets=TARGETS,
        update=False,
        runner=Counting(),
        frontends=[Confirmable()],
        confirm=True,
    )
    first = executor.submit(fake(npoints=3))
    second = executor.submit(fake(npoints=4), confirm=False)
    assert isinstance(second.result(10), Completed)
    assert first.status == "ready"
    first.start()
    # recorded in the order they started
    assert first.result(10).path.name == "fake-1"
    assert second.result().path.name == "fake-0"


def test_reuse_default():
    runner = Counting()
    gate = threading.Event()

    class Slow(Counting):
        def acquire(self, executor, bound, **kwargs):
            assert gate.wait(10)
            return super().acquire(executor, bound, **kwargs)

    runner = Slow()
    executor = Executor(None, targets=TARGETS, update=False, runner=runner, reuse=True)
    first = executor.submit(fake(npoints=3))
    assert executor.submit(fake(npoints=3)) is first
    assert executor.submit(fake(npoints=3), reuse=False) is not first
    gate.set()
    first.result(10)
    wait_for(lambda: runner.count == 2)
    assert Executor(None).reuse is False  # opt-in


def test_ready_shared_by_reuse():
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Counting(),
        frontends=[Confirmable()],
        confirm=True,
        reuse=True,
    )
    first = executor.submit(fake(npoints=3))
    assert executor.submit(fake(npoints=3)) is first
    first.start()
    first.result(10)


def test_recorded_needs_no_confirmation(tmp_path, monkeypatch):
    from qibocal import create_calibration_platform, protocols

    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    runner = Counting()
    executor = Executor(
        create_calibration_platform("mock"),
        path=tmp_path / "s",
        targets=TARGETS,
        update=False,
        runner=runner,
        frontends=[Confirmable()],
        confirm=True,
        reuse=True,
    )
    first = executor.submit(bound)
    first.start()
    first.result(10)
    again = executor.submit(bound)
    assert again.status == "done" and runner.count == 1


# -- the Run button ---------------------------------------------------------------


def test_button():
    pytest.importorskip("anywidget")
    from qibocal_widgets._core.button import Button

    clicks = []
    button = Button("▶ Run fake", lambda: clicks.append(1), "fake(targets=[0])")
    button._message(button, {"event": "click"}, [])
    button._message(button, {"event": "click"}, [])  # disabled once clicked
    assert clicks == [1] and button.disabled


def test_jupyter_run_button(monkeypatch):
    widgets = pytest.importorskip("ipywidgets")
    from qibocal_widgets._core.button import Button
    from qibocal_widgets.jupyter import Jupyter

    monkeypatch.setattr(Jupyter, "confirmable", lambda self: True)
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        runner=Counting(),
        frontends=[Jupyter()],
        confirm=True,
    )
    pending = executor.submit(fake(npoints=3), nshots=10)
    box = pending.views["_repr_mimebundle_"](pending)
    (button,) = box.children
    assert isinstance(button, Button)
    assert button.label == "▶ Run fake"
    assert button.tooltip == "fake(nshots=10)"
    button.click()
    pending.result(10)
    wait_for(lambda: isinstance(box.children[0], widgets.Tab))  # the result


def test_jupyter_confirmable_in_kernel_only():
    pytest.importorskip("ipywidgets")
    from qibocal_widgets.jupyter import Jupyter

    assert not Jupyter().confirmable()  # no kernel in tests

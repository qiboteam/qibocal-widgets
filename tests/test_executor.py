import pytest
from conftest import TARGETS
from qibocal.auto.task import Completed as QibocalCompleted

from qibocal_widgets import (
    Completed,
    Executor,
    Frontend,
    Local,
    Middleware,
    Runner,
    convert,
)


class Recorder(Middleware):
    """Record the order in which hooks run."""

    def __init__(self, name: str, log: list):
        self.name = name
        self.log = log

    def acquire(self, executor, call_next, *args, **kwargs):
        self.log.append(f"{self.name}:before")
        result = call_next(*args, **kwargs)
        self.log.append(f"{self.name}:after")
        return result

    def result(self, executor, completed):
        self.log.append(f"{self.name}:result")
        return completed


class Canned(Runner):
    """Replace the acquisition, as a remote runner would."""

    def __init__(self, data, log=None):
        self.data = data
        self.log = log if log is not None else []

    def acquire(self, executor, bound, **kwargs):
        self.log.append("runner")
        return QibocalCompleted(bound=bound, _data=self.data, _targets=TARGETS)


class Tag(Frontend):
    """A frontend registering a recognizable view."""

    protocol = "_tag_"

    def __init__(self, log=None):
        self.log = log if log is not None else []

    def render(self, completed):
        return "tagged"

    def attach(self, completed, executor=None):
        self.log.append("frontend")
        return super().attach(completed, executor)


@pytest.fixture
def log():
    return []


def test_defaults(bound):
    executor = Executor(None, targets=TARGETS, update=False)
    assert isinstance(executor.runner, Local)
    assert executor.middleware == [] and executor.frontends == []
    completed = executor(bound)
    assert type(completed) is Completed
    assert completed.views == {}
    assert set(completed.reports) == set(TARGETS)


def test_order(bound, acquired, log):
    """Middleware nest around the runner; frontends come last."""
    executor = Executor(
        None,
        targets=TARGETS,
        runner=Canned(acquired.data, log),
        middleware=[Recorder("outer", log), Recorder("inner", log)],
        frontends=[Tag(log)],
    )
    completed = executor.acquire(bound)
    assert log == [
        "outer:before",
        "inner:before",
        "runner",
        "inner:after",
        "outer:after",
        "outer:result",
        "inner:result",
        "frontend",
    ]
    assert completed.views["_tag_"](completed) == "tagged"


def test_runner_replaces_steps_selectively(bound, acquired):
    executor = Executor(
        None, targets=TARGETS, update=False, runner=Canned(acquired.data)
    )
    completed = executor(bound)
    # the acquisition was replaced, the following steps ran locally
    assert completed.data is acquired.data
    assert completed.results is not None
    assert set(completed.reports) == set(TARGETS)


def test_every_step_goes_through(bound, log):
    executor = Executor(
        None, targets=TARGETS, update=False, middleware=[Recorder("r", log)]
    )
    executor(bound)
    # acquire, fit, report
    assert log.count("r:result") == 3


@pytest.mark.parametrize(
    "role,value",
    [("runner", Tag()), ("middleware", [Local()]), ("frontends", [Recorder("r", [])])],
)
def test_wrong_role(role, value):
    with pytest.raises(TypeError, match="is not a"):
        Executor(None, **{role: value})


def test_plain_input_is_converted(acquired):
    executor = Executor(None, targets=TARGETS, frontends=[Tag()])
    assert type(acquired) is QibocalCompleted
    fitted = executor.fit(acquired)
    assert isinstance(fitted, Completed)
    assert "_tag_" in fitted.views


def test_lifecycle(log):
    class Lifecycle(Runner):
        def open(self, executor, force=False):
            log.append(("open", force))

        def close(self, executor):
            log.append(("close",))

    class Around(Middleware):
        def open(self, executor, call_next, *args, **kwargs):
            log.append("around open")
            return call_next(*args, **kwargs)

    # no local platform or output needed, since the runner handles the context
    with Executor(None, runner=Lifecycle(), middleware=[Around()]):
        pass
    assert log == ["around open", ("open", False), ("close",)]


def test_views():
    completed = Completed()
    assert completed._display_() == repr(completed)
    assert completed._repr_mimebundle_() is None

    class Bundle:
        def _repr_mimebundle_(self, include=None, exclude=None):
            return {"text/plain": "bundle"}

    viewed = completed.with_view("_display_", lambda c: "marimo").with_view(
        "_repr_mimebundle_", lambda c: Bundle()
    )
    assert viewed._display_() == "marimo"
    assert viewed._repr_mimebundle_() == {"text/plain": "bundle"}
    # views are added to copies
    assert completed.views == {}


def test_frontend_base():
    with pytest.raises(NotImplementedError):
        Frontend().render(Completed())


def test_convert(completed):
    converted = convert(completed)
    assert isinstance(converted, Completed)
    assert converted.bound is completed.bound
    assert converted.data is completed.data
    assert converted.results is completed.results
    assert converted.reports is completed.reports
    assert converted.targets == completed.targets
    # idempotent
    assert convert(converted) is converted
    # subclasses already satisfy the base type
    assert convert(converted, QibocalCompleted) is converted


def test_convert_lazy(tmp_path):
    """Conversion must not trigger loading of data from disk."""
    converted = convert(QibocalCompleted(path=tmp_path))
    assert converted._data is None
    assert converted.path == tmp_path


def test_convert_type_error():
    with pytest.raises(TypeError):
        convert("not completed")

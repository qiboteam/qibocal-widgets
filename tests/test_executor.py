import pytest
from conftest import TARGETS
from qibocal.auto.task import Completed as QibocalCompleted

from qibocal_widgets import Completed, Executor, Plugin, PluginConflict, convert


class Recorder(Plugin):
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


class Short(Plugin):
    """Replace the acquisition altogether, as a remote dispatcher would."""

    exclusive = "dispatch"

    def __init__(self, data):
        self.data = data

    def acquire(self, executor, call_next, bound, **kwargs):
        return QibocalCompleted(bound=bound, _data=self.data, _targets=TARGETS)


@pytest.fixture
def log():
    return []


def test_plain_executor(bound):
    completed = Executor(None, targets=TARGETS, update=False)(bound)
    assert type(completed) is Completed
    assert completed.views == {}
    assert set(completed.reports) == set(TARGETS)


def test_hook_order(bound, log):
    executor = Executor(
        None,
        targets=TARGETS,
        plugins=[Recorder("outer", log), Recorder("inner", log)],
    )
    executor.acquire(bound)
    # around hooks nest, the first plugin being the outermost; result hooks
    # follow the registration order, after the whole chain
    assert log == [
        "outer:before",
        "inner:before",
        "inner:after",
        "outer:after",
        "outer:result",
        "inner:result",
    ]


def test_short_circuit(bound, acquired, log):
    executor = Executor(
        None,
        targets=TARGETS,
        update=False,
        plugins=[Recorder("display", log), Short(acquired.data)],
    )
    completed = executor(bound)
    # the acquisition was replaced, the following steps ran locally
    assert completed.data is acquired.data
    assert completed.results is not None
    assert set(completed.reports) == set(TARGETS)
    assert isinstance(completed, Completed)


def test_conflict(acquired):
    with pytest.raises(PluginConflict, match="dispatch"):
        Executor(None, plugins=[Short(acquired.data), Short(acquired.data)])


def test_result_hooks_on_every_step(bound, log):
    executor = Executor(
        None, targets=TARGETS, update=False, plugins=[Recorder("r", log)]
    )
    executor(bound)
    # acquire, fit, report
    assert log.count("r:result") == 3


def test_plain_input_is_converted(acquired):
    executor = Executor(None, targets=TARGETS)
    assert type(acquired) is QibocalCompleted
    assert isinstance(executor.fit(acquired), Completed)


def test_open_close_hooks(monkeypatch, log):
    class Lifecycle(Plugin):
        def open(self, executor, call_next, *args, **kwargs):
            log.append(("open", args))

        def close(self, executor, call_next, *args, **kwargs):
            log.append(("close", args))

    executor = Executor(None, plugins=[Lifecycle()])
    # without calling the next hook, no local platform or output is needed
    with executor:
        pass
    assert log == [("open", (False,)), ("close", ())]


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

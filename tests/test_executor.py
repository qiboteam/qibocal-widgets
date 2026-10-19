from dataclasses import dataclass

import pytest
from conftest import TARGETS
from qibocal.auto.task import Completed

from qibocal_widgets import WidgetExecutor, convert


@dataclass
class Tagged(Completed):
    """A Completed subclass standing in for a frontend-specific one."""


class TaggedExecutor(WidgetExecutor):
    completed_type = Tagged


@pytest.fixture
def tagged():
    return TaggedExecutor(None, targets=TARGETS, update=False)


def test_convert(completed):
    tagged = convert(completed, Tagged)

    assert isinstance(tagged, Tagged)
    assert tagged.bound is completed.bound
    assert tagged.data is completed.data
    assert tagged.results is completed.results
    assert tagged.reports is completed.reports
    assert tagged.targets == completed.targets
    # idempotent
    assert convert(tagged, Tagged) is tagged


def test_convert_lazy(tmp_path):
    """Conversion must not trigger loading of data from disk."""
    lazy = Completed(path=tmp_path)
    converted = convert(lazy, Tagged)
    assert converted._data is None
    assert converted.path == tmp_path


def test_convert_type_error():
    with pytest.raises(TypeError):
        convert("not completed", Tagged)


def test_phases_are_wrapped(tagged, bound):
    acquired = tagged.acquire(bound)
    assert isinstance(acquired, Tagged)
    assert acquired.results is None

    fitted = tagged.fit(acquired)
    assert isinstance(fitted, Tagged)
    assert fitted.results is not None
    assert fitted.reports is None

    reported = tagged.report(fitted)
    assert isinstance(reported, Tagged)
    assert set(reported.reports) == set(TARGETS)


def test_call_is_wrapped(tagged, bound):
    completed = tagged(bound)
    assert isinstance(completed, Tagged)
    assert completed.success
    assert set(completed.reports) == set(TARGETS)


def test_plain_input_is_wrapped(tagged, executor, acquired):
    """Executions produced elsewhere are wrapped when passed through a phase."""
    assert not isinstance(acquired, Tagged)
    assert isinstance(tagged.fit(acquired), Tagged)
    fitted = executor.fit(acquired)
    assert not isinstance(fitted, Tagged)
    assert isinstance(tagged.report(fitted), Tagged)


def test_default_executor_is_plain(bound):
    completed = WidgetExecutor(None, targets=TARGETS, update=False)(bound)
    assert type(completed) is Completed

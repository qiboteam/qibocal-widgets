"""Default output location, from the session's reports folder."""

import json
import re

import pytest
from conftest import PLATFORMS, TARGETS
from qibocal import protocols

from qibocal_widgets import Executor, reports_dir
from qibocal_widgets._core import output

FOLDER = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[^/]+(-\d+)?")


@pytest.fixture
def mock(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))


@pytest.fixture
def session(tmp_path, monkeypatch):
    """A session with a reports folder, distinct from the working directory."""
    root = tmp_path / "reports"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("QIBOCAL_REPORTS_DIR", str(root))
    return root


def test_reports_dir_unset(monkeypatch):
    assert reports_dir() is None
    monkeypatch.setenv("QIBOCAL_REPORTS_DIR", "")
    assert reports_dir() is None
    assert output.default_path() is None


def test_reports_dir(session, monkeypatch):
    assert reports_dir() == session
    monkeypatch.setenv("QIBOCAL_REPORTS_DIR", "relative")
    assert reports_dir().is_absolute()
    assert reports_dir().name == "relative"


def test_default_path_is_fresh(session):
    first = output.default_path()
    assert first.parent == session
    assert FOLDER.fullmatch(first.name)
    first.mkdir(parents=True)
    second = output.default_path()
    assert second != first
    assert second.name.startswith(first.name)


def test_create_defaults_to_reports(session, mock):
    executor = Executor.create(platform="mock", targets=TARGETS)
    assert executor.path.parent == session
    assert FOLDER.fullmatch(executor.path.name)


def test_explicit_path_wins(session, mock):
    executor = Executor.create(path="var/report", platform="mock")
    # unchanged meaning: relative to the working directory
    assert str(executor.path) == "var/report"


def test_create_without_path_nor_reports(mock):
    with pytest.raises(TypeError, match="QIBOCAL_REPORTS_DIR"):
        Executor.create(platform="mock")


def test_constructor_unchanged(session):
    """Without create, there is no output to locate."""
    assert Executor(None).path is None


def test_open_writes_report(session, mock):
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    with Executor.open(platform="mock", targets=TARGETS, update=False) as executor:
        executor(bound)
    (report,) = session.iterdir()
    assert report == executor.path
    # recognizable by the report server
    assert json.loads((report / "meta.json").read_text())["platform"] == "mock"

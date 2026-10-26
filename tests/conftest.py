"""Shared fixtures, around the fake protocol of :mod:`fake`."""

from pathlib import Path

import pytest
from fake import NPOINTS, fake
from qibocal import Executor
from qibocal.auto.operation import Protocol

TARGETS = [0, 1]
PLATFORMS = Path(__file__).parent / "platforms"
"""Vendored Qibocal platforms (``mock``)."""


@pytest.fixture(autouse=True)
def isolated_config(tmp_path_factory, monkeypatch):
    """Never read or write the user's configuration."""
    monkeypatch.setenv("QIBOCAMP_CONFIG_DIR", str(tmp_path_factory.mktemp("config")))
    monkeypatch.delenv("QIBOCAL_WIDGETS_CONNECTION", raising=False)
    monkeypatch.delenv("QIBOCAMP_REPORTS_DIR", raising=False)


@pytest.fixture
def protocol() -> Protocol:
    return fake


@pytest.fixture
def bound(protocol):
    return protocol(npoints=NPOINTS)


@pytest.fixture
def executor() -> Executor:
    return Executor(None, targets=TARGETS, update=False)


@pytest.fixture
def completed(executor, bound):
    """A fully executed (acquired, fitted, reported) plain execution."""
    return executor(bound)


@pytest.fixture
def single(executor, bound):
    """A fully executed plain execution, on a single target."""
    return executor(bound, targets=TARGETS[:1])


@pytest.fixture
def acquired(executor, bound):
    """An execution stopped after acquisition."""
    return executor.acquire(bound)

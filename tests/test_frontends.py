"""Marimo and Jupyter frontends on the same executor."""

import pytest
from conftest import TARGETS

pytest.importorskip("marimo")
pytest.importorskip("ipywidgets")

from qibocal_widgets import Executor
from qibocal_widgets.jupyter import Jupyter
from qibocal_widgets.marimo import Marimo


def test_frontends_coexist(bound):
    executor = Executor(
        None, targets=TARGETS, update=False, frontends=[Marimo(), Jupyter()]
    )
    completed = executor(bound)
    assert set(completed.views) == {"_display_", "_repr_mimebundle_"}
    assert "Target 0" in completed._display_().text
    assert "application/vnd.jupyter.widget-view+json" in completed._repr_mimebundle_()

"""Background executions in a real marimo kernel (marimo export).

``marimo export`` runs the notebook once, plus the reactive runs triggered while
it runs; it does not wait for further rounds, so only one round is tested.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("marimo")

NOTEBOOK = Path(__file__).parent / "notebooks" / "reactive.py"


def rendered(page: str) -> list[str]:
    """Markdown outputs rendered in the exported page."""
    return re.findall(r'paragraph\\"\\u003E([A-Za-z0-9-]+)', page)


def test_reactive_pending(tmp_path):
    output = tmp_path / "reactive.html"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(NOTEBOOK),
            "-o",
            str(output),
            "-f",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    page = output.read_text()
    outputs = rendered(page)
    # the downstream cell ran again when the execution completed
    assert "DOWNSTREAM-RESULT-3-POINTS-MarimoPending" in outputs
    assert "DOWNSTREAM-WAITING" not in outputs
    # the spinner of the submitting cell was replaced by the result
    assert "Raw data: 0" in page


def test_rerun_follows(tmp_path):
    """The spinner of a cell run again is replaced, not only the first one."""
    output = tmp_path / "rerun.html"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(NOTEBOOK.parent / "rerun.py"),
            "-o",
            str(output),
            "-f",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    page = output.read_text()
    assert "Raw data: 0" in page
    assert "marimo-progress" not in page  # no spinner left


def test_confirm(tmp_path):
    """Nothing starts: the Run button is displayed, downstream cells wait."""
    output = tmp_path / "confirm.html"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(NOTEBOOK.parent / "confirm.py"),
            "-o",
            str(output),
            "-f",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    page = output.read_text()
    assert "ACQUISITIONS-0" in page
    assert "DOWNSTREAM-READY" in page
    assert "Run fake" in page

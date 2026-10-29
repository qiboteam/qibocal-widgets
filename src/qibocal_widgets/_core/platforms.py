"""Platform calibration state, as JSON documents.

The state of a platform is its ``parameters`` and ``calibration``, as dumped by
Qibocal in ``parameters.json`` and ``calibration.json``. It is represented as
a dictionary of JSON strings, so it can travel (remote jobs) and be written
(session folders) without a platform object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "CALIBRATION",
    "PARAMETERS",
    "State",
    "apply",
    "export",
    "read",
    "state",
    "write",
]

PARAMETERS = "parameters.json"
"""Platform parameters file, in platform dumps."""
CALIBRATION = "calibration.json"
"""Platform calibration file, in platform dumps."""

State = dict[str, str | None]
"""Platform state: ``{"parameters": <json>, "calibration": <json or None>}``."""


def state(platform: Any) -> State:
    """Calibration state of a platform."""
    calibration = getattr(platform, "calibration", None)
    return {
        "parameters": platform.parameters.model_dump_json(),
        "calibration": (
            calibration.model_dump_json() if calibration is not None else None
        ),
    }


def apply(platform: Any, state: State) -> None:
    """Replace the calibration state of a platform."""
    if state.get("parameters") is not None:
        platform.parameters = type(platform.parameters).model_validate_json(
            state["parameters"]
        )
    calibration = getattr(platform, "calibration", None)
    if state.get("calibration") is not None and calibration is not None:
        platform.calibration = type(calibration).model_validate_json(
            state["calibration"]
        )


def write(state: State, folder: Path) -> None:
    """Dump a state in a folder, as Qibocal's platform dumps."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / PARAMETERS).write_text(state["parameters"])
    if state.get("calibration") is not None:
        (folder / CALIBRATION).write_text(state["calibration"])


def read(folder: Path) -> State | None:
    """Load a state dumped in a folder, if any."""
    if not (folder / PARAMETERS).is_file():
        return None
    calibration = folder / CALIBRATION
    return {
        "parameters": (folder / PARAMETERS).read_text(),
        "calibration": calibration.read_text() if calibration.is_file() else None,
    }


def export(state: State, folder: Path, overwrite: bool = False) -> Path:
    """Write a state in a platform folder, formatted as qibolab dumps it.

    Existing files are replaced only in a git working tree, or with
    ``overwrite``.

    Raises:
        FileExistsError: replacing files outside of a git working tree, without
            ``overwrite``.
    """
    from .remote.worker import export_state

    return Path(export_state(state, Path(folder), overwrite))

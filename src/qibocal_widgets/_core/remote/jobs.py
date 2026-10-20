"""Encoding of remote jobs, in JSON and NPZ only.

Protocols travel by reference (``module:attribute``), parameters as JSON
documents, platform state as Qibocal's own JSON dumps, and data and results as
the JSON and NPZ files written by their ``save`` methods.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

from qibocal.auto.operation import BoundProtocol, Protocol

from . import worker
from .transport import RemoteError

__all__ = [
    "acquire_job",
    "load_files",
    "platform_state",
    "protocol_reference",
    "update_job",
]

PROTOCOLS = "qibocal.protocols"
"""Module of the built-in protocols, searched first."""


def protocol_reference(protocol: Protocol) -> str:
    """Importable ``module:attribute`` reference of a protocol.

    Built-in protocols are found in :mod:`qibocal.protocols`. Other protocols
    are searched in the module defining their acquisition function, which must
    be importable on the remote machine too (see the ``requirements`` of the
    connection).

    Raises:
        RemoteError: for protocols which cannot be imported by reference, e.g.
            defined in a notebook cell.
    """
    candidates = [PROTOCOLS, getattr(protocol.acquisition, "__module__", None)]
    for name in candidates:
        if name is None or name == "__main__":
            continue
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        for attribute, value in vars(module).items():
            if value is protocol:
                return f"{name}:{attribute}"
    raise RemoteError(
        "Remote execution requires protocols importable by reference: define "
        "the protocol at the top level of an importable module, and list its "
        "package in the connection requirements"
    )


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "value"):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


def document(value: Any) -> Any:
    """A JSON-compatible document, from dataclasses and plain values.

    Raises:
        RemoteError: for values which cannot be represented in JSON.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    try:
        return json.loads(json.dumps(value, default=_jsonable))
    except TypeError as error:
        raise RemoteError(f"Cannot send to the remote machine: {error}") from error


def parameters(value: Any) -> Any:
    """Protocol parameters, as a JSON-compatible document.

    Raises:
        RemoteError: for parameters which cannot be represented in JSON.
    """
    try:
        return worker.parameters_document(value)
    except TypeError as error:
        raise RemoteError(f"Cannot send to the remote machine: {error}") from error


def platform_state(platform: Any) -> dict | None:
    """Calibration state of a local platform, if any."""
    if platform is None:
        return None
    calibration = getattr(platform, "calibration", None)
    return {
        "parameters": platform.parameters.model_dump_json(),
        "calibration": (
            calibration.model_dump_json() if calibration is not None else None
        ),
    }


def _base(bound: BoundProtocol, platform: str, targets: Any, state: dict | None):
    return {
        "protocol": protocol_reference(bound.protocol),
        "parameters": parameters(bound.parameters),
        "platform": platform,
        "targets": document(targets),
        "state": state,
    }


def acquire_job(
    bound: BoundProtocol,
    *,
    platform: str,
    targets: Any,
    state: dict | None,
    overrides: dict,
) -> dict:
    """Job acquiring data with a bound protocol."""
    return {
        "action": "acquire",
        **_base(bound, platform, targets, state),
        "overrides": document(overrides),
    }


def update_job(
    bound: BoundProtocol,
    results: Any,
    *,
    platform: str,
    targets: Any,
    state: dict | None,
) -> dict:
    """Job applying fit results to the remote platform."""
    with tempfile.TemporaryDirectory() as folder:
        results.save(Path(folder))
        files = worker.encode(Path(folder))
    return {
        "action": "update",
        **_base(bound, platform, targets, state),
        "files": files,
    }


def load_files(files: dict, loader: Any) -> Any:
    """Decode files sent by the worker, and load them with ``loader(path)``."""
    with tempfile.TemporaryDirectory() as folder:
        worker.decode(files, Path(folder))
        return loader(Path(folder))

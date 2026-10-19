"""Tabulation of acquired data.

Pure data manipulation, independent of any notebook frontend: acquisition
outputs are turned into one :class:`pandas.DataFrame` per target.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["data_frames", "label"]


def label(target: Any) -> str:
    """Human-readable label for a target (qubit, pair, or anything else)."""
    if isinstance(target, tuple):
        return "-".join(str(t) for t in target)
    return str(target)


def _records_frame(array: Any) -> pd.DataFrame:
    """Convert a single target's array into a table."""
    array = np.asarray(array)
    if array.dtype == object:
        raise TypeError("Object arrays cannot be tabulated")
    if array.dtype.names is not None:
        # structured (record) array: one column per field
        return pd.DataFrame({name: np.ravel(array[name]) for name in array.dtype.names})
    if np.iscomplexobj(array):
        flat = np.ravel(array)
        return pd.DataFrame(
            {
                "real": flat.real,
                "imag": flat.imag,
                "signal": np.abs(flat),
                "phase": np.angle(flat),
            }
        )
    if array.ndim <= 1:
        return pd.DataFrame({"value": np.ravel(array)})
    return pd.DataFrame(array.reshape(array.shape[0], -1))


def _extra_columns(data: Any, target: Hashable, length: int) -> dict[str, Any]:
    """Collect per-target auxiliary attributes whose length matches the records.

    Qibocal data classes often keep sweep coordinates (e.g. drive frequencies)
    outside the record array, in dictionaries keyed by target. When such a
    sequence has the same length as the records, it is a natural extra column.
    """
    params = getattr(data, "params", None)
    if not isinstance(params, dict):
        return {}
    columns = {}
    for name, value in params.items():
        if not isinstance(value, dict) or target not in value:
            continue
        entry = value[target]
        if isinstance(entry, str | bytes) or not isinstance(entry, Iterable):
            continue
        entry = np.asarray(entry)
        if entry.ndim == 1 and entry.shape[0] == length:
            columns[name] = entry
    return columns


def data_frames(data: Any) -> dict[Any, pd.DataFrame]:
    """Tabulate acquired data, one table per target.

    Args:
        data: a Qibocal ``Data`` instance, or any object with a ``data``
            dictionary mapping targets to arrays. A bare dictionary is also
            accepted.

    Returns:
        Mapping from target to its table. Targets without array-like content are
        skipped.
    """
    records = data.data if hasattr(data, "data") else data
    if not isinstance(records, dict):
        return {}
    frames = {}
    for target, array in records.items():
        try:
            frame = _records_frame(array)
        except (TypeError, ValueError):
            continue
        for name, column in _extra_columns(data, target, len(frame)).items():
            if name not in frame.columns:
                frame[name] = column
        frames[target] = frame
    return frames

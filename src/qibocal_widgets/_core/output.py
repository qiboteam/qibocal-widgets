"""Default output location, from the session's reports folder.

Notebook sessions started by Qibocamp may have a reports folder,
exported as the ``QIBOCAMP_REPORTS_DIR`` environment variable. Its report server
scans that folder for report directories (recognized by their ``meta.json``),
so every execution writes to its own fresh subfolder.
"""

from __future__ import annotations

import getpass
import os
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["REPORTS_DIR", "default_path", "reports_dir"]

REPORTS_DIR = "QIBOCAMP_REPORTS_DIR"
"""Environment variable holding the session's reports folder."""


def reports_dir() -> Path | None:
    """The session's reports folder, if any.

    Read from the ``QIBOCAMP_REPORTS_DIR`` environment variable, set by
    Qibocamp for sessions with a reports folder (or by hand). Relative
    values are taken relative to the current working directory.

    Returns:
        The absolute folder, or ``None`` when the variable is unset or empty.
    """
    value = os.environ.get(REPORTS_DIR)
    if not value:
        return None
    return Path(value).expanduser().absolute()


def default_path() -> Path | None:
    """A fresh output folder under the session's reports folder, if any.

    Named ``<YYYY-MM-DD>_<HH-MM-SS>_<user>`` (UTC, as Qibocal's own output
    folders), with a numeric suffix when the name is already taken.
    """
    root = reports_dir()
    if root is None:
        return None
    user = getpass.getuser().replace(".", "-")
    stem = f"{datetime.now(UTC):%Y-%m-%d_%H-%M-%S}_{user}"
    path = root / stem
    suffix = 0
    while path.exists():
        suffix += 1
        path = root / f"{stem}-{suffix}"
    return path

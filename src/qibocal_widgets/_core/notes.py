"""Notes on sessions and executions, in Qibocal's ``notes.json``.

Writes follow the protocol of qibocal-report, whose report server may append
notes to the same files while serving a session live: a ``.notes.lock`` file,
locked exclusively, serializes writers, and the notes file is replaced
atomically.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter
from qibocal.auto.notes import NOTES, Note, load_notes

__all__ = ["append", "load"]

LOCK = ".notes.lock"
"""Lock file shared with qibocal-report."""

_NOTES = TypeAdapter(list[Note])


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    with path.open("a") as lock:
        if sys.platform == "win32":
            import msvcrt

            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _rewrite(folder: Path, change: Callable[[list[Note]], list[Note]]) -> list[Note]:
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f".notes-{uuid.uuid4().hex}.json"
    try:
        with _lock(folder / LOCK):
            notes = change(load_notes(folder))
            temporary.write_bytes(_NOTES.dump_json(notes, indent=4))
            temporary.replace(folder / NOTES)
            return notes
    finally:
        temporary.unlink(missing_ok=True)


def load(folder: Path) -> list[Note]:
    """Notes of a session or execution folder."""
    return load_notes(folder)


def append(folder: Path, note: Note) -> list[Note]:
    """Append a note to a folder, safely with respect to other writers."""
    return _rewrite(folder, lambda notes: [*notes, note])

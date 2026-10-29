"""History of the platform states of a session, as diffs.

Every change of the platform state through the executor is an entry: protocol
updates, edits, restores, and changes made outside of the executor, noticed
before the next one. Entries hold the changed leaves only, with their previous
and new values, and the entry they apply to (its parent): restoring an earlier
state continues from it, forking the history, as a branch would.

The history is written in the session folder (:data:`FILE`), next to the
platform states Qibocal records, so that attaching a session continues it.
Durable versions of the platform, shared and reviewed, are the business of the
platform folder and its git repository (see ``PlatformState.save``).
"""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from . import platforms
from .state import SEPARATOR, PlatformState, _documents, _leaves, _state, _step

if TYPE_CHECKING:
    from .executor import Executor

__all__ = ["Entry", "PlatformHistory"]

FILE = "platform-history.jsonl"
"""History file, in the session folder: an entry per line, as JSON."""

START = "start"
"""The state the history starts from, recorded in full."""
UPDATE = "update"
"""A protocol update, applied automatically or approved."""
EDIT = "edit"
"""Values set by path (``executor.platform_state.update``)."""
RESTORE = "restore"
"""An earlier state restored, entirely or for some paths."""
EXTERNAL = "external"
"""A change made outside of the executor, noticed before the next one."""

_MISSING = object()


@dataclass(frozen=True)
class Entry:
    """A change of the platform state."""

    id: int
    """Position in the history, from 0 (the start)."""
    parent: int | None
    """The entry it applies to: the previous one, unless restoring a state."""
    at: datetime
    """When it was recorded (UTC)."""
    kind: str
    """``start``, ``update``, ``edit``, ``restore``, or ``external``."""
    changes: dict[str, tuple[Any, Any]]
    """Changed leaves, as ``(before, after)`` (``None`` for missing ones)."""
    task: str | None = None
    """The execution updating the platform (its folder name, e.g. ``rabi-0``)."""
    targets: list | None = None
    """The targets updated."""
    source: int | None = None
    """The entry restored."""
    paths: list[str] | None = None
    """The paths restored, if not all."""

    def describe(self) -> str:
        """A one-line summary."""
        what = {
            START: "start",
            UPDATE: f"update {self.task or ''}".strip(),
            EDIT: "edit",
            RESTORE: f"restore #{self.source}",
            EXTERNAL: "external change",
        }.get(self.kind, self.kind)
        if self.kind == UPDATE and self.targets:
            what += f" ({', '.join(map(str, self.targets))})"
        if self.paths:
            what += f" ({', '.join(self.paths)})"
        return what


class PlatformHistory:
    """The platform states of a session, as :attr:`Executor.history
    <qibocal_widgets.Executor.history>`.

    Entries are addressed by their ``id``, by negative index (``-1`` is the
    latest), or by the folder name of the execution updating the platform
    (``history["rabi-0"]``). Restoring a state continues from it: the
    following entries fork from there.
    """

    def __init__(self, executor: Executor, records: list[dict] | None = None):
        self._executor = executor
        self._records: list[dict] = records or []
        self._head: int | None = self._records[-1]["id"] if self._records else None
        self._head_documents: dict | None = None
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[PlatformHistory], None]] = []

    @classmethod
    def load(cls, executor: Executor) -> PlatformHistory:
        """The history recorded in the executor's session folder, if any."""
        session = executor.session
        records = []
        if session is not None and (session.path / FILE).is_file():
            with (session.path / FILE).open() as file:
                records = [json.loads(line) for line in file if line.strip()]
        return cls(executor, records)

    # -- reading -----------------------------------------------------------------

    @property
    def entries(self) -> list[Entry]:
        """All the entries, in recording order."""
        with self._lock:
            return [_entry(record) for record in self._records]

    @property
    def head(self) -> Entry | None:
        """The entry of the current state, if any."""
        with self._lock:
            return None if self._head is None else _entry(self._records[self._head])

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __getitem__(self, ref: int | str) -> Entry:
        return _entry(self._records[self._index(ref)])

    def _index(self, ref: int | str | Entry) -> int:
        if isinstance(ref, Entry):
            return ref.id
        with self._lock:
            if isinstance(ref, str):
                for record in reversed(self._records):
                    if record.get("task") == ref:
                        return record["id"]
                raise KeyError(f"No platform update by {ref!r}")
            if not -len(self._records) <= ref < len(self._records):
                raise IndexError(f"No history entry {ref}")
            return ref % len(self._records)

    def lineage(self, ref: int | str | Entry = -1) -> list[Entry]:
        """The entries leading to one, from the start."""
        index: int | None = self._index(ref)
        chain = []
        while index is not None:
            chain.append(self._records[index])
            index = self._records[index]["parent"]
        return [_entry(record) for record in reversed(chain)]

    def state(self, ref: int | str | Entry = -1) -> PlatformState:
        """The platform state after an entry, as a read-only snapshot."""
        index = self._index(ref)
        return PlatformState.frozen(
            _state(self._documents(index)), name=f"executor.history.state({index})"
        )

    def diff(
        self, a: int | str | Entry, b: int | str | Entry | None = None
    ) -> dict[str, tuple[Any, Any]]:
        """Leaves differing between two entries, as ``(a, b)`` values.

        ``b`` defaults to the current state, so that ``diff(a)`` is what
        changed since ``a``.
        """
        after = self._executor.platform_state.snapshot() if b is None else self.state(b)
        return after.diff(self.state(a))

    def applied(self, task: str) -> list:
        """Targets updated by an execution, from its folder name."""
        targets: list = []
        with self._lock:
            for record in self._records:
                if record["kind"] == UPDATE and record.get("task") == task:
                    targets.extend(
                        t for t in record.get("targets") or [] if t not in targets
                    )
        return targets

    def log(self) -> Any:
        """The entries as a table (a pandas ``DataFrame``)."""
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "id": entry.id,
                    "parent": entry.parent,
                    "time (UTC)": f"{entry.at:%H:%M:%S}",
                    "change": entry.describe(),
                    "leaves": len(entry.changes),
                }
                for entry in self.entries
            ]
        ).set_index("id")

    def explore(self, a: int | None = None, b: int | None = None) -> Any:
        """An explorer comparing two entries, and restoring them.

        Requires ``anywidget`` (in the ``jupyter`` and ``marimo`` extras).
        """
        from .history_explorer import HistoryExplorer

        return HistoryExplorer(self, a=a, b=b)

    def on_change(self, callback: Callable[[PlatformHistory], None]) -> None:
        """Call ``callback(history)`` whenever an entry is recorded."""
        self._callbacks.append(callback)

    # -- restoring ---------------------------------------------------------------

    def restore(
        self, ref: int | str | Entry, paths: Iterable[str] | None = None
    ) -> Entry:
        """Restore the state after an entry, entirely or for some paths.

        Restored entirely, the following entries continue from it, forking the
        history. Restoring some paths (leaves, or branches such as a whole
        qubit, in any form accepted by ``PlatformState``) sets their values as
        they were, on top of the current state.

        Returns:
            The entry recording the restore.

        Raises:
            KeyError: for paths not found in either state.
            ValueError: if the restored state is not valid.
        """
        source = self._index(ref)
        target = self.state(source)
        current = self._executor.platform_state
        if paths is None:
            self._executor._set_platform_state(
                target.state(), kind=RESTORE, source=source, parent=source
            )
        else:
            chosen = list(paths)
            changes = _select(current, target, chosen)
            documents = current.documents()
            for path, value in changes.items():
                _put(documents, path, value)
            updated = _state(documents)
            from .state import _validate

            _validate(updated)
            self._executor._set_platform_state(
                updated, kind=RESTORE, source=source, paths=chosen
            )
        return self.head

    # -- recording ---------------------------------------------------------------

    def _record(
        self,
        kind: str,
        before: platforms.State | None,
        after: platforms.State | None,
        *,
        parent: int | None = None,
        **origin: Any,
    ) -> None:
        """Record a change of state, from ``before`` to ``after``.

        A difference between ``before`` and the latest recorded state was made
        outside of the executor: it is recorded first. With ``parent``, the
        change applies to that entry (restoring it).
        """
        if after is None:
            return
        with self._lock:
            before_documents = _documents(before if before is not None else after)
            if not self._records:
                self._append(START, None, {}, documents=before_documents)
            head = self._current()
            if before_documents != head:
                self._append(EXTERNAL, self._head, _changes(head, before_documents))
            base = before_documents if parent is None else self._documents(parent)
            after_documents = _documents(after)
            self._append(
                kind,
                self._head if parent is None else parent,
                _changes(base, after_documents),
                **origin,
            )
            self._head_documents = after_documents
        self._flush()
        for callback in list(self._callbacks):
            callback(self)

    def _append(
        self,
        kind: str,
        parent: int | None,
        changes: list[dict],
        documents: dict | None = None,
        **origin: Any,
    ) -> None:
        record: dict[str, Any] = {
            "id": len(self._records),
            "parent": parent,
            "at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "changes": changes,
        }
        record.update({k: v for k, v in origin.items() if v is not None})
        if documents is not None:
            record["documents"] = copy.deepcopy(documents)
        self._records.append(record)
        self._head = record["id"]
        self._head_documents = None

    def _current(self) -> dict:
        """The documents of the latest recorded state."""
        if self._head_documents is None:
            self._head_documents = self._documents(self._head)
        return self._head_documents

    def _documents(self, index: int) -> dict:
        """The documents after an entry, replaying its lineage."""
        with self._lock:
            chain = []
            current: int | None = index
            while current is not None:
                chain.append(self._records[current])
                current = self._records[current]["parent"]
            documents = copy.deepcopy(chain[-1]["documents"])
            for record in reversed(chain[:-1]):
                for change in record["changes"]:
                    if "new" in change:
                        _put(documents, change["path"], change["new"])
                    else:
                        _remove(documents, change["path"])
            return documents

    def _flush(self) -> None:
        """Write the history in the session folder, once started."""
        session = self._executor.session
        if session is None or not session.started:
            return
        with self._lock:
            lines = [json.dumps(record) for record in self._records]
        (session.path / FILE).write_text("\n".join(lines) + "\n")


def _entry(record: dict) -> Entry:
    return Entry(
        id=record["id"],
        parent=record["parent"],
        at=datetime.fromisoformat(record["at"]),
        kind=record["kind"],
        changes={
            change["path"]: (change.get("old"), change.get("new"))
            for change in record["changes"]
        },
        task=record.get("task"),
        targets=record.get("targets"),
        source=record.get("source"),
        paths=record.get("paths"),
    )


def _changes(before: dict, after: dict) -> list[dict]:
    """The leaves changed between two sets of documents.

    A missing ``old`` marks an added leaf, a missing ``new`` a removed one.
    """
    old = dict(_leaves(before, ""))
    new = dict(_leaves(after, ""))
    changes = []
    for path in sorted(old.keys() | new.keys()):
        a, b = old.get(path, _MISSING), new.get(path, _MISSING)
        if a == b:
            continue
        change: dict[str, Any] = {"path": path}
        if a is not _MISSING:
            change["old"] = a
        if b is not _MISSING:
            change["new"] = b
        changes.append(change)
    return changes


def _select(
    current: PlatformState, target: PlatformState, paths: list[str]
) -> dict[str, Any]:
    """Leaves to set to restore some paths of a state, by full path."""
    from .state import normalize

    documents, restored = current.documents(), target.documents()
    leaves = dict(_leaves(restored, ""))
    changes = {}
    for text in paths:
        path = normalize(text, restored) or normalize(text, documents)
        if path is None:
            raise KeyError(text)
        prefix = path + SEPARATOR
        selected = {
            leaf: value
            for leaf, value in leaves.items()
            if leaf == path or leaf.startswith(prefix)
        }
        if not selected:
            raise KeyError(text)
        changes.update(selected)
    return changes


def _put(documents: dict, path: str, value: Any) -> None:
    """Set a leaf, creating the missing branches."""
    *parents, last = path.split(SEPARATOR)
    target: Any = documents
    for segment in parents:
        try:
            target = _step(target, segment)
        except KeyError:
            target[segment] = {}
            target = target[segment]
    if isinstance(target, list):
        index = int(last)
        if index == len(target):
            target.append(value)
        else:
            target[index] = value
    else:
        target[last] = value


def _remove(documents: dict, path: str) -> None:
    """Remove a leaf, if present."""
    *parents, last = path.split(SEPARATOR)
    target: Any = documents
    try:
        for segment in parents:
            target = _step(target, segment)
        if isinstance(target, list):
            del target[int(last)]
        else:
            del target[last]
    except (KeyError, IndexError, ValueError):
        pass

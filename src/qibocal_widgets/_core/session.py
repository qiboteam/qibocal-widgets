"""Session folders: where the executions of an executor are recorded.

A session folder keeps exactly the layout of Qibocal's runcard outputs, so
that Qibocal (``Output.load``, ``Completed.load``) and the report server of
qibocal-report read it unchanged:

- ``data/<id>-<iteration>/``: one folder per acquisition, with ``action.yml``
  (operation, targets, executed parameters), the data files, and the results
  files once fitted;
- ``history.json``: the execution order;
- ``meta.json``: metadata, with per-task timings;
- ``platform/``: the platform at the session start, and ``new_platform/``
  after updates;
- ``notes.json``: notes on the session, and on each execution in its folder.

Every change is written immediately, so the folder is always consistent, even
if the session is never explicitly closed (as is common in notebooks).
"""

from __future__ import annotations

import json
import shutil
import warnings
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from qibocal.auto.history import HISTORY
from qibocal.auto.notes import Note, dump_notes
from qibocal.auto.output import (
    META,
    PLATFORM,
    UPDATED_PLATFORM,
    Metadata,
    TaskStats,
    Versions,
)
from qibocal.auto.task import Action, Completed, Task, TaskId

from . import notes as _notes
from . import platforms
from .protocols import reference, registered_name
from .remote.worker import parameters_document

if TYPE_CHECKING:
    from .executor import Executor

__all__ = ["Session", "SessionExists"]

DATA = "data"
"""Subfolder of the task folders."""


class SessionExists(FileExistsError):
    """A new session would overwrite an existing folder."""


def _json(value):
    """A JSON round trip, making values YAML-safe (tuples become lists)."""
    return json.loads(json.dumps(value, default=list))


class Session:
    """The folder recording the executions of an executor.

    The folder is created when the session starts, i.e. at the first context
    entry or recorded execution, whichever comes first.

    Args:
        path: the session folder.
        meta: the session metadata. If omitted, it is generated from the
            executor when the session starts.
    """

    def __init__(self, path: str | Path, meta: Metadata | None = None):
        self.path = Path(path)
        """The session folder."""
        self.meta = meta
        """Session metadata, written to ``meta.json``."""
        self.order: list[str] = []
        """Recorded tasks listed in ``history.json``, in execution order."""
        self.started = False
        """Whether the folder exists and holds the session."""

    def __repr__(self) -> str:
        return f"Session({str(self.path)!r})"

    @classmethod
    def attach(cls, path: str | Path) -> Session:
        """Continue an existing session folder.

        Raises:
            FileNotFoundError: if the folder holds no session (no ``meta.json``).
        """
        path = Path(path)
        if not (path / META).is_file():
            raise FileNotFoundError(f"No session in {path}: {META} not found")
        session = cls(path, Metadata.load(path))
        history = path / HISTORY
        if history.is_file():
            session.order = json.loads(history.read_text())
        session.started = True
        return session

    # -- lifecycle -------------------------------------------------------------

    def start(self, executor: Executor, force: bool = False) -> None:
        """Create the folder, unless already started.

        Args:
            executor: the owner of the session.
            force: replace an existing folder.

        Raises:
            SessionExists: if the folder already exists and is not empty, and
                ``force`` is not set.
        """
        if self.started:
            return
        if self.path.exists() and any(self.path.iterdir()):
            if not force:
                raise SessionExists(
                    f"{self.path} already exists: attach to it to append "
                    "(Executor.attach), or pick another path"
                )
            shutil.rmtree(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        if self.meta is None:
            self.meta = _metadata(executor)
        self.meta.start()
        state = executor.runner.platform_state(executor)
        if state is not None:
            platforms.write(state, self.path / PLATFORM)
        self.started = True
        self._dump()

    def flush(self) -> None:
        """Register the latest activity, and write the metadata."""
        if self.started:
            self.meta.end()
            self._dump()

    def platform_state(self) -> platforms.State | None:
        """The latest platform state recorded in the folder, if any."""
        for name in (UPDATED_PLATFORM, PLATFORM):
            state = platforms.read(self.path / name)
            if state is not None:
                return state
        return None

    def restore(self, executor: Executor) -> None:
        """Continue from the latest platform state recorded in the folder.

        The state is handed to the executor's runner: applied to the local
        platform, or kept by remote runners for their next jobs.
        """
        state = self.platform_state()
        if state is not None:
            executor.runner.set_platform_state(executor, state)

    # -- notes -----------------------------------------------------------------

    def note(
        self,
        content: str,
        completed: Completed | None = None,
        *,
        author: str | None = None,
    ) -> Note:
        """Add a note to the session, or to one of its executions.

        Notes are appended to the ``notes.json`` of the session folder, or of
        the execution folder, safely with respect to the report server, which
        may add notes concurrently.

        Args:
            content: the note text.
            completed: an execution recorded in this session.
            author: defaults to the author of the session metadata.

        Raises:
            ValueError: if the session has not started, or the execution is not
                recorded in it.
        """
        folder = self._notes_folder(completed)
        if author is None and self.meta is not None:
            author = self.meta.author
        note = Note(content=content, author=author)
        _notes.append(folder, note)
        return note

    def notes(self, completed: Completed | None = None) -> list[Note]:
        """Notes of the session, or of one of its executions."""
        return _notes.load(self._notes_folder(completed))

    def _notes_folder(self, completed: Completed | None) -> Path:
        if not self.started:
            raise ValueError("The session has not started: no folder to annotate")
        if completed is None:
            return self.path
        if not self.contains(completed):
            raise ValueError("The execution is not recorded in this session")
        return Path(completed.path)

    # -- recording -------------------------------------------------------------

    def contains(self, completed: Completed) -> bool:
        """Whether an execution is already recorded in this session."""
        path = completed.path
        return path is not None and Path(path).parent == self.path / DATA

    def ensure(self, executor: Executor, completed: Completed) -> Completed:
        """Record an execution as a new task, unless already recorded."""
        if self.contains(completed):
            return completed
        return self.add(executor, completed)

    def add(self, executor: Executor, completed: Completed) -> Completed:
        """Record an execution as a new task.

        Returns:
            The execution, bound to its task folder. Executions which cannot be
            recorded (e.g. with parameters not representable in YAML) are
            returned unchanged, with a warning.
        """
        self.start(executor)
        bound = completed.bound
        if bound is None:
            return completed
        name = registered_name(bound.protocol)
        operation = name or reference(bound.protocol) or _qualname(bound.protocol)
        task_id = self._next(name or operation.rpartition(":")[2])
        folder = self.path / DATA / str(task_id)
        try:
            parameters = parameters_document(bound.parameters)
            action = Action(
                id=task_id.id,
                operation=operation,
                targets=_json(completed.targets),
                update=executor._update_enabled,
                parameters=parameters if isinstance(parameters, dict) else {},
            )
            task = Task(action=action, operation=bound.protocol)
        except Exception as error:  # noqa: BLE001 - recording is best effort
            warnings.warn(f"Execution not recorded: {error}", stacklevel=3)
            return completed
        # load lazy content from the original location, before moving it
        try:
            data = completed.data
        except ValueError:
            data = None
        results = completed.results
        folder.mkdir(parents=True)
        task.dump(folder)
        recorded = replace(
            completed, task=task, path=folder, _data=data, _results=results
        )
        recorded.dump_data()
        recorded.dump_results()
        if recorded.notes:
            dump_notes(recorded.notes, folder)
        if name is not None:
            # only registered protocols can be loaded back by Qibocal
            self.order.append(str(task_id))
        else:
            warnings.warn(
                f"{operation} is not a registered Qibocal protocol: recorded in "
                f"{folder}, but not listed in the session history",
                stacklevel=3,
            )
        self._stats(recorded)
        self._dump()
        return recorded

    def results(self, completed: Completed) -> None:
        """Write the fit results of a recorded execution."""
        if not self.contains(completed):
            return
        completed.dump_results()
        self._stats(completed)
        self._dump()

    def platform(self, executor: Executor) -> None:
        """Record the updated platform state, as known by the runner."""
        state = executor.runner.platform_state(executor)
        if state is not None and self.started:
            platforms.write(state, self.path / UPDATED_PLATFORM)

    # -- internals -------------------------------------------------------------

    def _next(self, identifier: str) -> TaskId:
        iteration = 0
        while (self.path / DATA / f"{identifier}-{iteration}").exists():
            iteration += 1
        return TaskId(id=identifier, iteration=iteration)

    def _stats(self, completed: Completed) -> None:
        self.meta.stats[Path(completed.path).name] = TaskStats(
            completed.data_time, completed.results_time
        )

    def _dump(self) -> None:
        (self.path / HISTORY).write_text(json.dumps(self.order, indent=4))
        (self.path / META).write_text(json.dumps(self.meta.dump(), indent=4))


def _qualname(protocol) -> str:
    acquisition = protocol.acquisition
    module = getattr(acquisition, "__module__", "unknown")
    return f"{module}:{getattr(acquisition, '__qualname__', 'protocol')}"


def _metadata(executor: Executor) -> Metadata:
    """Metadata for executors created without them."""
    if executor.platform is not None:
        from qibo.backends import construct_backend

        backend = construct_backend(backend="qibolab", platform=executor.platform)
        return Metadata.generate(backend)
    import getpass

    return Metadata(
        backend="qibolab",
        platform=executor.runner.platform_name(executor) or "unknown",
        start_time=None,
        end_time=None,
        stats={},
        versions=Versions(other={}),
        author=getpass.getuser(),
    )

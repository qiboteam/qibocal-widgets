"""Exploring and updating the calibration state of a platform, by path.

A platform state is made of two JSON documents, ``parameters`` (qibolab's
``parameters.json``) and ``calibration`` (Qibocal's ``calibration.json``).
Values are addressed by dotted paths over those documents, rooted at the
document name::

    parameters.configs.0/drive.frequency
    parameters.native_gates.two_qubit.0-1.CZ
    calibration.single_qubits.0.qubit.frequency_01

Within each document, paths are those of qibolab's ``Platform.update`` and of
the platform view of the Qibocamp dashboard: numeric segments index
lists, keys are the ones in the JSON files (e.g. ``0/drive``, ``0-1``).

Leaves follow the dashboard too: scalars, ``null``, and lists of numbers
(e.g. a ``[value, error]`` pair) are leaves; other objects and lists are
branches.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from . import platforms

__all__ = ["PlatformState", "ReadOnlyState", "is_leaf", "normalize"]

ROOTS = ("parameters", "calibration")
"""Documents of a platform state, i.e. the first segment of every path."""

SEPARATOR = "."


class ReadOnlyState(RuntimeError):
    """The state is a snapshot, not bound to any platform."""


def is_leaf(value: Any) -> bool:
    """Whether a value is a leaf: a scalar, or a list of numbers."""
    if isinstance(value, dict):
        return False
    if isinstance(value, list):
        return all(
            isinstance(item, int | float) and not isinstance(item, bool) or item is None
            for item in value
        )
    return True


def _children(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        yield from ((str(key), child) for key, child in value.items())
    elif isinstance(value, list) and not is_leaf(value):
        yield from ((str(index), child) for index, child in enumerate(value))


def _step(value: Any, segment: str) -> Any:
    if isinstance(value, list):
        try:
            return value[int(segment)]
        except (ValueError, IndexError):
            raise KeyError(segment) from None
    if isinstance(value, dict):
        return value[segment]
    raise KeyError(segment)


_QUOTED = re.compile(r"""["']([^"']+)["']""")


def normalize(text: str, documents: Mapping[str, Any]) -> str | None:
    """The canonical path designated by some text, if any.

    Accepted forms, so that paths can be pasted from anywhere:

    - a full path: ``parameters.configs.0/drive.frequency``;
    - a path within a document, as copied from the dashboard (which shows one
      file at a time) or written for ``Platform.update``:
      ``configs.0/drive.frequency``, resolved in the first document where it
      exists;
    - any text quoting a path, as an API call or its output:
      ``state["parameters.configs.0/drive.frequency"]``, or
      ``{"calibration.single_qubits.0.qubit.frequency_01": 4.1e9}``.

    An empty text designates the root.
    """
    text = text.strip()
    if not text:
        return ""
    candidates = [text, *_QUOTED.findall(text)]
    for candidate in candidates:
        candidate = candidate.strip().strip(SEPARATOR)
        if not candidate:
            continue
        options = (
            [candidate]
            if candidate.split(SEPARATOR, 1)[0] in ROOTS
            else [f"{root}{SEPARATOR}{candidate}" for root in ROOTS]
        )
        for option in options:
            if _exists(documents, option):
                return option
    return None


def _exists(documents: Mapping[str, Any], path: str) -> bool:
    try:
        _get(documents, path)
    except KeyError:
        return False
    return True


def _get(documents: Mapping[str, Any], path: str) -> Any:
    if path == "":
        return dict(documents)
    value: Any = documents
    for segment in path.split(SEPARATOR):
        value = _step(value, segment)
    return value


def _set(documents: dict[str, Any], path: str, value: Any) -> None:
    *parents, last = path.split(SEPARATOR)
    target: Any = documents
    for segment in parents:
        target = _step(target, segment)
    _step(target, last)  # the leaf must exist: no silent creation on typos
    if isinstance(target, list):
        target[int(last)] = value
    else:
        target[last] = value


def _leaves(value: Any, path: str) -> Iterator[tuple[str, Any]]:
    if is_leaf(value) and path:
        yield path, value
        return
    for key, child in _children(value):
        yield from _leaves(child, f"{path}{SEPARATOR}{key}" if path else key)


def _documents(state: platforms.State) -> dict[str, Any]:
    return {
        root: json.loads(state[root]) for root in ROOTS if state.get(root) is not None
    }


def _state(documents: Mapping[str, Any]) -> platforms.State:
    return {
        root: json.dumps(documents[root]) if root in documents else None
        for root in ROOTS
    }


class PlatformState:
    """The calibration state of a platform, addressed by path.

    A state is either *bound* to a platform (reading its current state, and
    writing updates back), or a read-only *snapshot*. Use the constructors:
    :meth:`of` (a platform object), :meth:`load` (a folder), :meth:`snapshot`,
    or :attr:`Executor.platform_state <qibocal_widgets.Executor.platform_state>`.

    Args:
        source: returns the current state.
        sink: applies an updated state; ``None`` for read-only states.
        name: how the state is referred to in code, in the snippets shown by
            the explorer.
        saver: writes a state in the platform folder, given ``overwrite``,
            returning where (see :meth:`save`); ``None`` if not known.
    """

    def __init__(
        self,
        source: Callable[[], platforms.State | None],
        sink: Callable[[platforms.State], None] | None = None,
        *,
        name: str = "state",
        saver: Callable[[platforms.State, bool], str] | None = None,
    ):
        self._source = source
        self._sink = sink
        self._saver = saver
        self.name = name

    # -- constructors ----------------------------------------------------------

    @classmethod
    def of(cls, platform: Any, *, name: str = "state") -> PlatformState:
        """The state of a platform object, bound to it."""

        def save(state: platforms.State, overwrite: bool) -> str:
            from qibolab import locate_platform

            folder = locate_platform(platform.name)
            return str(platforms.export(state, folder, overwrite))

        return cls(
            lambda: platforms.state(platform),
            lambda state: platforms.apply(platform, state),
            name=name,
            saver=save,
        )

    @classmethod
    def load(cls, path: str | Path, *, name: str = "state") -> PlatformState:
        """A snapshot of a state dumped in a folder.

        Args:
            path: a platform dump (with ``parameters.json``), or a session
                folder, whose latest state is taken (``new_platform/``, else
                ``platform/``).

        Raises:
            FileNotFoundError: if no state is found.
        """
        path = Path(path)
        state = platforms.read(path)
        if state is None:
            for folder in ("new_platform", "platform"):
                state = platforms.read(path / folder)
                if state is not None:
                    break
        if state is None:
            raise FileNotFoundError(f"No platform state in {path}")
        return cls.frozen(state, name=name)

    def save(self, path: str | Path | None = None, *, overwrite: bool = False) -> str:
        """Write the state as a platform folder: ``parameters.json`` and
        ``calibration.json``, formatted as qibolab dumps them.

        Args:
            path: the folder; by default, the folder of the platform, e.g. in
                ``QIBOLAB_PLATFORMS``, on the remote machine for remote
                runners without a local platform.
            overwrite: replace existing files outside of a git working tree.
                In a git working tree, they are always replaced: git keeps the
                previous version, and the changes are reviewed and committed
                there (e.g. with Qibocamp).

        Returns:
            The folder written, on the machine where it is.

        Raises:
            ValueError: without a path, when the platform folder is not known.
            FileExistsError: replacing files outside of a git working tree,
                without ``overwrite``.
        """
        if path is not None:
            return str(platforms.export(self.state(), Path(path), overwrite))
        if self._saver is None:
            raise ValueError("The platform folder is not known: give a path")
        return self._saver(self.state(), overwrite)

    @classmethod
    def frozen(cls, state: platforms.State, *, name: str = "state") -> PlatformState:
        """A read-only snapshot of a state."""
        state = dict(state)
        return cls(lambda: state, name=name)

    def snapshot(self) -> PlatformState:
        """A read-only copy of the current state, e.g. to compare later."""
        return self.frozen(self.state(), name=self.name)

    # -- reading ----------------------------------------------------------------

    @property
    def readonly(self) -> bool:
        """Whether updates are rejected."""
        return self._sink is None

    def state(self) -> platforms.State:
        """The current state, as JSON strings.

        Raises:
            LookupError: if the state is not known (e.g. no platform).
        """
        state = self._source()
        if state is None:
            raise LookupError("The platform state is not known")
        return state

    def documents(self) -> dict[str, Any]:
        """The current state, as parsed JSON documents."""
        return _documents(self.state())

    def __getitem__(self, path: str) -> Any:
        """The value at a path (see :meth:`resolve` for accepted forms).

        Raises:
            KeyError: if the path does not exist.
        """
        documents = self.documents()
        resolved = normalize(path, documents)
        if resolved is None:
            raise KeyError(path)
        return copy.deepcopy(_get(documents, resolved))

    def get(self, path: str, default: Any = None) -> Any:
        """The value at a path, or a default."""
        try:
            return self[path]
        except KeyError:
            return default

    def __contains__(self, path: str) -> bool:
        return normalize(path, self.documents()) is not None

    def resolve(self, text: str) -> str | None:
        """The canonical path designated by some text, if any.

        Accepted forms, so that paths can be pasted from anywhere:

        - a full path: ``parameters.configs.0/drive.frequency``;
        - a path within a document, as copied from the Qibocamp dashboard
          (which shows one file at a time) or written for qibolab's
          ``Platform.update``: ``configs.0/drive.frequency``;
        - any text quoting a path, as an API call or its output:
          ``state["parameters.configs.0/drive.frequency"]``.

        All methods taking a path accept the same forms.
        """
        return normalize(text, self.documents())

    def leaves(self, path: str = "") -> dict[str, Any]:
        """All the leaves under a path, by full path."""
        documents = self.documents()
        resolved = normalize(path, documents)
        if resolved is None:
            raise KeyError(path)
        return dict(_leaves(_get(documents, resolved), resolved))

    def find(self, query: str) -> dict[str, Any]:
        """Leaves whose path contains some text (case insensitive)."""
        query = query.strip().lower()
        return {
            path: value
            for path, value in self.leaves().items()
            if query in path.lower()
        }

    def diff(self, other: PlatformState) -> dict[str, tuple[Any, Any]]:
        """Leaves differing from another state, as ``(other, self)`` values.

        Leaves missing on one side are reported as ``None`` on that side.
        """
        mine = self.leaves()
        theirs = other.leaves()
        return {
            path: (theirs.get(path), mine.get(path))
            for path in sorted(mine.keys() | theirs.keys())
            if mine.get(path) != theirs.get(path)
        }

    # -- updating -----------------------------------------------------------------

    def update(self, changes: Mapping[str, Any]) -> None:
        """Set values by path, validating the whole state.

        All changes are applied at once: if any of them is invalid, none is.

        Raises:
            ReadOnlyState: for snapshots.
            KeyError: for paths which do not exist (no new entries are
                created, so that typos are not silently accepted).
            ValueError: if the updated state is not valid.
        """
        if self._sink is None:
            raise ReadOnlyState("Snapshots cannot be updated")
        documents = self.documents()
        for path, value in changes.items():
            resolved = normalize(path, documents)
            if resolved is None or resolved in ROOTS or resolved == "":
                raise KeyError(path)
            _set(documents, resolved, value)
        updated = _state(documents)
        _validate(updated)
        self._sink(updated)

    def __setitem__(self, path: str, value: Any) -> None:
        self.update({path: value})

    # -- display ------------------------------------------------------------------

    def explore(
        self,
        path: str = "",
        *,
        editable: bool = False,
        compare: PlatformState | None = None,
    ):
        """An interactive explorer, for Jupyter and Marimo.

        Args:
            path: where to start; any text accepted by :meth:`resolve`.
            editable: allow editing values, through :meth:`update`.
            compare: highlight differences with another state (e.g. a
                snapshot taken earlier, or the start of a session).

        Requires ``anywidget`` (in the ``jupyter`` and ``marimo`` extras).
        """
        from .explorer import Explorer

        return Explorer(self, path, editable=editable, compare=compare)

    def __repr__(self) -> str:
        kind = "snapshot" if self.readonly else "bound"
        try:
            count = len(self.leaves())
        except LookupError:
            return f"<PlatformState {self.name} ({kind}, unknown)>"
        return f"<PlatformState {self.name} ({kind}, {count} values)>"


def _validate(state: platforms.State) -> None:
    """Check a state against the qibolab and Qibocal models."""
    from pydantic import ValidationError
    from qibocal.calibration.calibration import Calibration
    from qibolab import Parameters

    try:
        if state.get("parameters") is not None:
            Parameters.model_validate_json(state["parameters"])
        if state.get("calibration") is not None:
            Calibration.model_validate_json(state["calibration"])
    except ValidationError as error:
        raise ValueError(f"Invalid platform state: {error}") from error

"""Remote connections and their configuration file.

The layout follows qibocal-report, so that its launcher can manage these
connections too: the file ``remotes.json`` lives in the same configuration
directory (``$QIBOCAL_REPORT_CONFIG_DIR``, else ``$XDG_CONFIG_HOME/qibocal``,
else ``~/.config/qibocal``), with the same versioned structure::

    {"version": 1, "connections": {"<name>": {<Connection fields>}}}

and the connection fields mirror the notebook connections of qibocal-report.
"""

from __future__ import annotations

import json
import os
import shlex
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CONFIG_VERSION",
    "Connection",
    "IncompatibleConfig",
    "config_path",
    "connections",
    "load_connection",
    "remove_connection",
    "save_connection",
]

CONFIG_VERSION = 1
"""Version of the configuration file format."""
FILENAME = "remotes.json"
"""Name of the configuration file."""
CONNECTION_VARIABLE = "QIBOCAL_WIDGETS_CONNECTION"
"""Environment variable selecting a named connection by default."""


class IncompatibleConfig(RuntimeError):
    """The configuration file has an unsupported version."""


class Connection(BaseModel):
    """How to reach the machine with access to the instruments.

    The tier is determined by the options, not detected:

    - neither ``ssh`` nor ``queue``/``slurm``: the current process already runs
      where the instruments are, and nothing is dispatched;
    - ``queue`` or ``slurm``: every remote step is a blocking ``srun`` job,
      submitted from the current machine (the access node);
    - ``ssh``: the same, through SSH (from a laptop to the access node). Without
      ``queue``/``slurm``, steps run directly on the SSH destination.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    ssh: str | None = Field(default=None, min_length=1)
    """SSH arguments, ending with the destination (e.g. ``"-J bastion me@login"``).

    Host aliases and jump hosts from ``~/.ssh/config`` are honored.
    """
    queue: str | None = Field(default=None, min_length=1)
    """SLURM partition."""
    slurm: str | None = Field(default=None, min_length=1)
    """Further ``srun`` options (e.g. ``"--time=10 --qos=normal"``)."""
    workdir: str | None = Field(default=None, min_length=1)
    """Remote working directory."""
    venv: str = Field(default="qibocal", min_length=1)
    """Environment name, under ``~/.cache/qibocal/envs``, or path."""
    python: str | None = Field(default=None, min_length=1)
    """Interpreter, or version with uv, used to create the environment."""
    requirements: str | None = Field(default=None, min_length=1)
    """Environment requirements, in ``requirements.txt`` format.

    Qibocal is included by default, unless already named (e.g. to pin a
    branch). Further entries make external protocols available.
    """
    rebuild_on_compute: bool = False
    """Install the environment on a compute node, rather than the access node."""
    platform: str | None = Field(default=None, min_length=1)
    """Platform name, resolved on the remote machine."""
    timeout: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    """Maximum duration of a remote step, in seconds, queue time included."""

    @property
    def dispatched(self) -> bool:
        """Whether steps are executed elsewhere."""
        return self.ssh is not None or self.scheduled

    @property
    def scheduled(self) -> bool:
        """Whether steps go through the queue."""
        return self.queue is not None or self.slurm is not None

    def destination(self) -> tuple[list[str], str]:
        """Split the SSH options from the destination."""
        if self.ssh is None:
            raise ValueError("The connection has no SSH destination")
        arguments = shlex.split(self.ssh)
        if not arguments or arguments[-1].startswith("-"):
            raise ValueError("ssh must end with a host or user@host destination")
        return arguments[:-1], arguments[-1]


def config_dir() -> Path:
    """Configuration directory shared with qibocal-report."""
    explicit = os.environ.get("QIBOCAL_REPORT_CONFIG_DIR")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "qibocal"


def config_path() -> Path:
    """Location of the remote connections file."""
    return config_dir() / FILENAME


def _read() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    content = json.loads(path.read_text())
    version = content.get("version", CONFIG_VERSION)
    if version != CONFIG_VERSION:
        raise IncompatibleConfig(
            f"{path} has version {version}, while {CONFIG_VERSION} is supported"
        )
    return content.get("connections", {})


def _write(raw: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"version": CONFIG_VERSION, "connections": raw}, indent=2)
    # atomic replacement, as qibocal-report does
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{FILENAME}.", delete=False
    ) as file:
        file.write(content + "\n")
    Path(file.name).replace(path)


def connections() -> dict[str, Connection]:
    """All the named connections in the configuration file."""
    return {name: Connection(**raw) for name, raw in _read().items()}


def load_connection(name: str) -> Connection:
    """A named connection from the configuration file.

    Raises:
        KeyError: if no connection has that name.
    """
    raw = _read()
    if name not in raw:
        raise KeyError(f"No connection named {name!r} in {config_path()}")
    return Connection(**raw[name])


def save_connection(name: str, connection: Connection) -> None:
    """Add or replace a named connection in the configuration file."""
    raw = _read()
    raw[name] = connection.model_dump(exclude_defaults=True)
    _write(raw)


def remove_connection(name: str) -> None:
    """Remove a named connection from the configuration file."""
    raw = _read()
    raw.pop(name, None)
    _write(raw)

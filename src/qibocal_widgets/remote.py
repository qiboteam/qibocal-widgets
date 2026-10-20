"""Remote execution.

The :class:`Remote` plugin dispatches the acquisition to the machine with
access to the instruments, according to a :class:`Connection`::

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo
    from qibocal_widgets.remote import Remote

    remote = Remote("lab")  # named connection, from the configuration file
    remote.install()  # once, or whenever the requirements change
    executor = Executor(None, targets=[0, 1], plugins=[Marimo(), remote])
    executor(bound)  # acquired remotely, fitted and reported locally

Connections are stored in ``remotes.json``, in the configuration directory
shared with qibocal-report, and managed with :func:`save_connection`,
:func:`remove_connection`, and :func:`connections`.
"""

from ._core.remote.config import (
    Connection,
    IncompatibleConfig,
    config_path,
    connections,
    load_connection,
    remove_connection,
    save_connection,
)
from ._core.remote.plugin import Remote
from ._core.remote.transport import RemoteError

__all__ = [
    "Connection",
    "IncompatibleConfig",
    "Remote",
    "RemoteError",
    "config_path",
    "connections",
    "load_connection",
    "remove_connection",
    "save_connection",
]

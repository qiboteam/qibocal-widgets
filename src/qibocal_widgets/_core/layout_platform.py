"""The layout of a platform: which qubits, channels, and instruments it has.

Unlike the platform state (parameters and calibration), the layout is defined
by the platform's ``platform.py``, and does not change. For remote runners
without a local platform, it is created on the remote machine, without
connecting it, and sent back as JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state import SEPARATOR

__all__ = ["PlatformLayout"]


@dataclass(frozen=True)
class PlatformLayout:
    """Qubits, couplers, channels, and instruments of a platform, as plain data.

    As returned by :meth:`Executor.describe_platform
    <qibocal_widgets.Executor.describe_platform>`. Channels hold their
    ``kind`` (e.g. ``IqChannel``), ``device`` and ``path`` (the port), and,
    depending on the kind, ``lo`` and ``mixer`` (names of configurations, in
    the platform state), or ``probe`` and ``twpa_pump``.
    """

    qubits: dict[Any, dict[str, Any]]
    """Channels of each qubit (``drive``, ``probe``, ``acquisition``, ...)."""
    couplers: dict[Any, dict[str, Any]]
    """Channels of each coupler."""
    channels: dict[str, dict[str, Any]]
    """Channels, by identifier (e.g. ``"0/drive"``)."""
    instruments: dict[str, dict[str, Any]]
    """Instruments, by name: their ``kind``, and ``address`` when they have one."""

    @classmethod
    def from_json(cls, document: dict) -> PlatformLayout:
        """From the document of :func:`~.remote.worker.layout_of`."""
        return cls(**{key: dict(map(tuple, pairs)) for key, pairs in document.items()})

    @classmethod
    def of(cls, platform: Any) -> PlatformLayout:
        """The layout of a platform object."""
        from .remote.worker import layout_of

        return cls.from_json(layout_of(platform))

    def lo_config(self, channel: str) -> str | None:
        """Path, in the platform state, of the configuration of a channel's LO.

        ``None`` if the channel has no configurable LO. For instance, the LO
        frequency of the drive of qubit 0::

            path = layout.lo_config(layout.qubits[0]["drive"])
            executor.platform_state[f"{path}.frequency"]

        Raises:
            KeyError: for unknown channels.
        """
        lo = self.channels[channel].get("lo")
        return None if lo is None else SEPARATOR.join(("parameters", "configs", lo))

    def sharing(self, config: str) -> list[str]:
        """Channels referring to a configuration, e.g. sharing an LO.

        Changing its values affects all of them.
        """
        name = config.rpartition(f"configs{SEPARATOR}")[2]
        return [
            channel
            for channel, fields in self.channels.items()
            if name in (fields.get("lo"), fields.get("mixer"))
        ]

"""Interpreter hook for executing the examples in the documentation build.

It is loaded at startup by every Python process of the build (``PYTHONPATH`` is
set by the ``examples`` task), including the processes spawned by Marimo to run
notebooks.

qibolab replaces the process-wide ``SIGINT`` and ``SIGTERM`` handlers whenever a
platform is created, to disconnect instruments when a job is cancelled. Marimo
relies on those signals to shut its runtime down, so ``marimo export html``
hangs on notebooks creating a platform, until a timeout. The examples run on
the ``mock`` platform, with no instrument to disconnect: here, platform
creation leaves the signal handlers untouched.
"""

import signal
from types import SimpleNamespace

try:
    from qibolab._core.platform import platform as _platform
except ImportError:  # pragma: no cover - not every process needs qibolab
    pass
else:
    _platform.signal = SimpleNamespace(
        signal=lambda *_: None, SIGINT=signal.SIGINT, SIGTERM=signal.SIGTERM
    )

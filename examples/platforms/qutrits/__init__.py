"""Two-qutrit example, also loadable through QIBOLAB_PLATFORMS."""

from pathlib import Path

from qibolab import Platform

from .platform import create


def create_platform(*, workers: int = 1, seed: int = 1234) -> Platform:
    """Load fresh parameters and native gates for each experiment session."""
    hardware = create(workers=workers, seed=seed)
    return Platform.load(Path(__file__).parent, **vars(hardware))

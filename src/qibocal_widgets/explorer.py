"""Interactive explorer of platform states.

Created by :meth:`PlatformState.explore <qibocal_widgets.PlatformState.explore>`,
it is a single widget, displayed natively by Jupyter and Marimo. Requires
``anywidget``, included in the ``jupyter`` and ``marimo`` extras.
"""

from ._core.explorer import Explorer

__all__ = ["Explorer"]

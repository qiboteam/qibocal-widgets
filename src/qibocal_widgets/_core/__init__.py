"""Implementation of :mod:`qibocal_widgets`.

Nothing in this subpackage is public API: the public interface is defined by
the re-exports in :mod:`qibocal_widgets`, :mod:`qibocal_widgets.marimo`, and
:mod:`qibocal_widgets.jupyter`.

- :mod:`.data` and :mod:`.reports` extract displayable content from
  executions, independently of any notebook frontend.
- :mod:`.executor` wraps the Qibocal executor to produce displayable
  executions.
- :mod:`.marimo` and :mod:`.jupyter` render that content in their frontend.
"""

"""Implementation of :mod:`qibocal_widgets`.

Nothing in this subpackage is public API: the public interface is defined by
the re-exports in :mod:`qibocal_widgets`, :mod:`qibocal_widgets.marimo`,
:mod:`qibocal_widgets.jupyter`, and :mod:`qibocal_widgets.remote`.

- :mod:`.data` and :mod:`.reports` extract displayable content from
  executions, independently of any notebook frontend.
- :mod:`.completed`, :mod:`.runner`, :mod:`.middleware`, :mod:`.frontend`
  and :mod:`.executor` compose the executor out of its three roles.
- :mod:`.marimo` and :mod:`.jupyter` render that content in their frontend.
- :mod:`.remote` runs steps on the machine with the instruments.
"""

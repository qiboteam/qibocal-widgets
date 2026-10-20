Quickstart
==========

:class:`qibocal_widgets.Executor` is a drop-in replacement of
:class:`qibocal.Executor`, extended by a list of plugins. Each notebook
frontend is a plugin, in its own module:

=============  ===============================  ===============================
               Marimo                           Jupyter
=============  ===============================  ===============================
module         :mod:`qibocal_widgets.marimo`    :mod:`qibocal_widgets.jupyter`
plugin         ``Marimo``                       ``Jupyter``
=============  ===============================  ===============================

The examples below use Marimo; replace ``marimo`` with ``jupyter`` and
``Marimo`` with ``Jupyter`` for the other frontend. Both plugins can also be
registered together: each frontend uses its own view.

Implicit display
----------------

Create the executor exactly as a :class:`qibocal.Executor`: all its
constructors (``create``, ``open``, and the default one) and the context
manager are inherited, and additionally accept the ``plugins`` argument.

.. code-block:: python

    from qibocal import protocols

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo

    executor = Executor.create(
        platform="mock", path="var/report", update=False, plugins=[Marimo()]
    )
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=1000,
        delay_between_pulses_step=50,
    )

Every phase returns an execution which renders itself when it is the last
expression of a cell:

.. code-block:: python

    with executor:
        acquired = executor.acquire(bound, targets=[0, 1])
    acquired

displays an accordion with one raw data table per target, while

.. code-block:: python

    reported = executor.report(executor.fit(acquired))
    reported

displays two tabs: the raw data, and the per-target reports. Phases not yet
executed are simply omitted, and an *Error* section appears for failed
executions.

The initial layout is chosen to show the most relevant content first:

- the *Reports* tab is selected whenever reports are available;
- per-target accordions start folded, except when there is a single target,
  which starts expanded;
- within each report, the plots are visible right away, while the fit results
  table sits above them, centered, in a nested *Fit results* section folded by
  default.

Everything can still be expanded or folded interactively.

The returned objects are :class:`qibocal_widgets.Completed`, a subclass of
Qibocal's ``Completed`` with exactly the same attributes (``data``, ``results``, ``reports``, ``targets``, ...):
existing code keeps working unchanged.

Explicit helpers
----------------

For custom layouts, the same content is available explicitly:

.. code-block:: python

    from qibocal_widgets.marimo import show_data, show_reports

    show_data(reported.data)
    show_reports(reported.reports)

    # or, from the execution itself
    show_data(reported)
    show_reports(reported)

Executions from other sources
-----------------------------

Executions produced by a plain :class:`qibocal.Executor`, or loaded from disk,
can be made displayable with ``wrap``:

.. code-block:: python

    from qibocal_widgets.marimo import wrap

    wrap(completed)

They are also converted automatically when passed through any phase of an
executor with the plugin, e.g. ``executor.fit(completed)``.

Examples
--------

Complete notebooks are available in the
`examples <https://github.com/qiboteam/qibocal-widgets/tree/main/examples>`_
folder of the repository.

Writing plugins
---------------

A plugin subclasses :class:`qibocal_widgets.Plugin` and overrides only the
hooks it needs:

- *around hooks* (``open``, ``close``, ``acquire``, ``fit``, ``report``,
  ``update``) receive the executor and the next callable of the chain, like
  web-server middleware. The first registered plugin is the outermost. A hook
  can alter the arguments, post-process the output, or replace the step by
  not calling the next callable.
- the *result hook* (``result``) transforms the output of every step, after
  the whole chain, in registration order.

.. code-block:: python

    import time

    from qibocal_widgets import Plugin


    class Timer(Plugin):
        def acquire(self, executor, call_next, *args, **kwargs):
            start = time.perf_counter()
            completed = call_next(*args, **kwargs)
            print(f"acquired in {time.perf_counter() - start:.1f} s")
            return completed

Plugins replacing the same step declare a common ``exclusive`` group: the
executor refuses to register two plugins of the same group, raising
:class:`qibocal_widgets.PluginConflict`.

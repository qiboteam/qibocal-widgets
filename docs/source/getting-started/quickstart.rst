Quickstart
==========

The two frontends expose the same interface, in two independent modules:

=============  ===============================  ===============================
               Marimo                           Jupyter
=============  ===============================  ===============================
module         :mod:`qibocal_widgets.marimo`    :mod:`qibocal_widgets.jupyter`
executor       ``MarimoExecutor``               ``JupyterExecutor``
execution      ``MarimoCompleted``              ``JupyterCompleted``
=============  ===============================  ===============================

The examples below use Marimo; replace ``marimo`` with ``jupyter`` and
``Marimo`` with ``Jupyter`` for the other frontend.

Implicit display
----------------

Create the executor exactly as a :class:`qibocal.Executor`: all its
constructors (``create``, ``open``, and the default one) and the context
manager are inherited unchanged.

.. code-block:: python

    from qibocal import protocols

    from qibocal_widgets.marimo import MarimoExecutor

    executor = MarimoExecutor.create(platform="mock", path="var/report", update=False)
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

displays two tabs: the raw data, and the per-target reports (figures and fit
table). Phases not yet executed are simply omitted, and an *Error* section
appears for failed executions.

The returned objects are subclasses of Qibocal's ``Completed``, with exactly
the same attributes (``data``, ``results``, ``reports``, ``targets``, ...):
existing code keeps working unchanged.

Explicit helpers
----------------

For custom layouts, the same content is available explicitly:

.. code-block:: python

    from qibocal_widgets.marimo import show_data, show_reports

    show_data(reported.data)
    show_reports(reported.reports)

    # or, as methods
    reported.show_data()
    reported.show_reports()

Executions from other sources
-----------------------------

Executions produced by a plain :class:`qibocal.Executor`, or loaded from disk,
can be made displayable with ``wrap``:

.. code-block:: python

    from qibocal_widgets.marimo import wrap

    wrap(completed)

They are also converted automatically when passed through any phase of a
widget executor, e.g. ``executor.fit(completed)``.

Examples
--------

Complete notebooks are available in the
`examples <https://github.com/qiboteam/qibocal-widgets/tree/main/examples>`_
folder of the repository.

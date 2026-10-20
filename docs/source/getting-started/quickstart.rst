Quickstart
==========

:class:`qibocal_widgets.Executor` is a drop-in replacement of
:class:`qibocal.Executor`, composed of three roles:

- **frontends**, displaying every output in a notebook (any number, all
  coexisting);
- a **runner**, deciding where and how the steps run (exactly one: locally by
  default, or remotely, see :doc:`remote`);
- **middleware**, wrapping every step for anything else (timing, logging,
  caching, ...).

Each notebook frontend lives in its own module:

=============  ===============================  ===============================
               Marimo                           Jupyter
=============  ===============================  ===============================
module         :mod:`qibocal_widgets.marimo`    :mod:`qibocal_widgets.jupyter`
frontend       ``Marimo``                       ``Jupyter``
=============  ===============================  ===============================

The examples below use Marimo; replace ``marimo`` with ``jupyter`` and
``Marimo`` with ``Jupyter`` for the other frontend. Both can also be
registered together: each uses its own view.

Implicit display
----------------

Create the executor exactly as a :class:`qibocal.Executor`: all its
constructors (``create``, ``open``, and the default one) and the context
manager are inherited, and additionally accept the ``frontends``,
``runner``, and ``middleware`` arguments.

.. code-block:: python

    from qibocal import protocols

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo

    executor = Executor.create(
        platform="mock", path="var/report", update=False, frontends=[Marimo()]
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

Output location
---------------

Notebook sessions started by the Qibocal application, or by ``qibocal notebook``
from `qibocal-report <https://github.com/qiboteam/qibocal-report>`_, may have
a *reports folder*, exported as the ``QIBOCAL_REPORTS_DIR`` environment
variable. Its report server serves that folder, so calibrations show up in the
dashboard while the session goes on.

Without an explicit ``path``, ``Executor.create`` and ``Executor.open`` write
to a fresh subfolder of it, named ``<YYYY-MM-DD>_<HH-MM-SS>_<user>`` (UTC):

.. code-block:: python

    executor = Executor.create(platform="chip", frontends=[Marimo()])
    executor.path  # e.g. <reports folder>/2026-10-20_14-03-11_alice

- An explicit ``path`` always wins, with its usual meaning (relative to the
  working directory).
- Without ``path`` and without a reports folder, ``create`` raises a
  ``TypeError``, as before.
- :func:`qibocal_widgets.reports_dir` returns the folder (or ``None``), to
  build custom paths under it:

  .. code-block:: python

      from qibocal_widgets import reports_dir

      executor = Executor.create(platform="chip", path=reports_dir() / "rabi-tuning")

The variable can also be set by hand, e.g. for a plain ``jupyter lab``.

Executions from other sources
-----------------------------

Executions produced by a plain :class:`qibocal.Executor`, or loaded from disk,
can be made displayable with ``wrap``:

.. code-block:: python

    from qibocal_widgets.marimo import wrap

    wrap(completed)

They are also converted automatically when passed through any phase of an
executor with the frontend, e.g. ``executor.fit(completed)``.

Examples
--------

Complete notebooks are available in the
`examples <https://github.com/qiboteam/qibocal-widgets/tree/main/examples>`_
folder of the repository.

Extending the executor
----------------------

Each role has a base class to subclass, overriding only what is needed.

**Frontends** (:class:`qibocal_widgets.Frontend`) set the display
``protocol`` they implement, and ``render`` executions:

.. code-block:: python

    from qibocal_widgets import Frontend


    class Summary(Frontend):
        protocol = "_display_"  # Marimo's display protocol

        def render(self, completed):
            return f"{len(completed.targets)} targets, fitted: {completed.results is not None}"

The executor attaches all its frontends to every output, after the
middleware.

**Runners** (:class:`qibocal_widgets.Runner`) run each step. The base class
runs every step locally, as :class:`qibocal.Executor` does; a runner executing
some steps elsewhere overrides only those, as
:class:`~qibocal_widgets.remote.Remote` does for the acquisition.

**Middleware** (:class:`qibocal_widgets.Middleware`) wrap the steps, like in
web servers: each hook (``open``, ``close``, ``acquire``, ``fit``,
``report``, ``update``) receives the executor and the next callable of the
chain. The first middleware is the outermost, and the runner always the
innermost, so every middleware sees every step. A hook can alter the
arguments, post-process the output, or not call the next one at all. The
``result`` hook transforms the output of every step.

.. code-block:: python

    import time

    from qibocal_widgets import Middleware


    class Timer(Middleware):
        def acquire(self, executor, call_next, *args, **kwargs):
            start = time.perf_counter()
            completed = call_next(*args, **kwargs)
            print(f"acquired in {time.perf_counter() - start:.1f} s")
            return completed

Remote execution
================

The :class:`~qibocal_widgets.remote.Remote` runner executes the steps needing the
instruments on the machine which has access to them, while the notebook runs
elsewhere. It follows the multi-tier architecture of the `interactive usage
<https://qibo.science/qibocal/stable/tutorials/interactive.html>`_ of Qibocal,
and the conventions of `Qibocamp <https://github.com/qiboteam/qibocamp>`_.

.. code-block:: python

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo
    from qibocal_widgets.remote import Remote

    executor = Executor(
        None, targets=[0, 1], runner=Remote("lab"), frontends=[Marimo()]
    )
    completed = executor(bound)  # acquired remotely, fitted and reported locally
    completed

Tiers
-----

What happens depends on the connection options, not on any detection:

======================================  ======================================
Options                                 Steps needing the instruments
======================================  ======================================
none                                    run in the current process (already on
                                        the compute node): nothing dispatched
``queue`` and/or ``slurm``              one blocking ``srun`` job per
                                        acquisition, from the current machine
                                        (access node)
``ssh``                                 the same, through SSH (laptop to
                                        access node); without ``queue``, steps
                                        run on the SSH destination itself
======================================  ======================================

Only the acquisition needs the instruments. Fit and report always run
locally, from the acquired data. Updates only modify the platform parameters:

- with a local platform (e.g. ``Executor.create(platform="chip", ...)`` on the
  access node), the update is applied to it, and its state is sent along with
  every following acquisition;
- without (e.g. ``Executor(None, ...)`` on a laptop), the update runs remotely,
  on the access node and outside of the queue, and the runner keeps the
  resulting state for the following acquisitions.

Each job recreates the platform from its name and applies the current state,
so jobs are independent, as SLURM requires.

Since the passthrough tier changes nothing, the same notebook works everywhere:
select the connection with the ``QIBOCAL_WIDGETS_CONNECTION`` environment
variable and use ``Remote()``.

Never holding the queue
-----------------------

A :class:`~qibocal_widgets.remote.Remote` session never holds the SLURM queue
between acquisitions: each acquisition is a job of its own, holding its
allocation only while it runs. The instruments are shared, and a notebook
session idles most of the time (looking at plots, editing cells), so holding
them for the whole session would block everybody else for nothing.

This is a deliberate design choice, with consequences:

- every acquisition starts a fresh process on the compute node, which imports
  Qibocal, qibolab, and the drivers again (on a network filesystem, with cold
  caches, this may take seconds: see ``pending.profile()``);
- the instruments are connected and disconnected by every acquisition: they
  cannot stay connected between jobs.

What does not need the instruments stays warm instead. A runner starts an
*agent* on the remote machine, once, over a single SSH connection, outside of
the queue (on the access node). It imports Qibocal once and serves every step:
updates, platform states, layouts, and saves run in it at once, with no new
connection and no new process; acquisitions through the queue are launched by
it as ``srun`` jobs, straight in the environment's interpreter. Without a
queue (``ssh`` only), acquisitions run in the agent itself, one at a time. The
agent exits with the notebook, when its connection closes; the queued jobs
it launched go on, detached (see below). ``agent=False`` in the connection
starts a process of its own for every step instead.

**When the queue should be held.** If a session needs the instruments for
itself, and the start-up of every job matters, reserve the node for the whole
session explicitly: run the notebook server itself on the compute node (in a
SLURM allocation), with the connection's passthrough tier (no ``ssh``, no
``queue``). Everything then runs in the kernel, next to the instruments, and
the network carries only what the notebook already exchanges: cell edits and
displayed results. Holding the queue is then visible, and a choice of the
user, rather than a side effect of a library.

Connections
-----------

Connection options can be given directly, or stored by name:

.. code-block:: python

    from qibocal_widgets.remote import Connection, Remote, save_connection

    save_connection(
        "lab",
        Connection(
            ssh="-J bastion me@login",  # ssh arguments, ending with the destination
            queue="qpu",  # SLURM partition
            slurm="--time=30",  # further srun options
            platform="chip",  # resolved on the remote machine
            platforms_dir="~/platforms",  # where, on the remote machine
            requirements="qibocal @ git+https://github.com/qiboteam/qibocal.git@protodev",
        ),
    )

    Remote("lab")  # the stored connection
    Remote("lab", queue="other")  # with overrides
    Remote(queue="qpu", platform="chip")  # without any file

Named connections live in ``remotes.json``, in the configuration directory
shared with Qibocamp (``$QIBOCAMP_CONFIG_DIR``, else
``$XDG_CONFIG_HOME/qibocamp``, else ``~/.config/qibocamp``):

.. code-block:: json

    {
      "version": 1,
      "connections": {
        "lab": {
          "ssh": "-J bastion me@login",
          "queue": "qpu",
          "platform": "chip",
          "platforms_dir": "~/platforms"
        }
      }
    }

The platforms are found in ``platforms_dir`` on the remote machine, which
replaces its ``QIBOLAB_PLATFORMS`` for every remote step (``~`` is expanded
there). Without it, the remote environment must set the variable itself. The
field has the name and meaning of the same setting in Qibocamp's agent
configurations.

The fields mirror the notebook connections of Qibocamp, so that its
launcher can manage them as well. SSH host aliases and jump hosts from
``~/.ssh/config`` are honored; connections never prompt for passwords
(``BatchMode``), so set up key-based authentication.

Environments and protocols
--------------------------

Remote steps run in a Python environment on the remote machine, under
``~/.cache/qibocamp/envs``, the same location used by Qibocamp. A named
connection has one of its own by default, named after it under ``_remote/``
(``lab`` uses ``~/.cache/qibocamp/envs/_remote/lab``), shared with no other
connection nor notebook session unless ``venv`` names it on purpose; a
connection given inline uses ``qibocal``.
Installing it is a separate operation, never performed by the steps:

.. code-block:: python

    remote = Remote("lab")
    remote.install()  # once, and whenever the requirements change
    remote.install(rebuild=True)  # from scratch

Installation uses ``uv`` when available (``venv`` and ``pip`` otherwise), runs
on the access node (where network access usually is) unless
``rebuild_on_compute`` is set, and is skipped when the requirements did not
change. Qibocal is always required, and can be pinned in the requirements.

Everything travels as JSON and NPZ, nothing is pickled: protocols are sent by
reference (``module:attribute``), parameters as JSON, platform state and data
in Qibocal's own formats. Built-in protocols work out of the box. Further
protocols must be defined at the top level of an importable module, whose
package is listed in the ``requirements`` of the connection; protocols defined
in a notebook cell cannot be executed remotely.

Failures raise :class:`~qibocal_widgets.remote.RemoteError`, carrying the
remote traceback or error output.

Background execution
--------------------

``executor(bound)`` blocks until the job has gone through the queue.
``executor.submit(bound)`` returns at once, with a
:class:`~qibocal_widgets.Pending` execution, so that the notebook stays
interactive while the job waits: the platform explorer and the queue monitor
keep working.

.. code-block:: python

    pending = executor.submit(protocols.ramsey(delay=(10, 1000, 100)), nshots=500)

    pending()  # the result, or None while running: never blocks
    pending.result()  # waits for the result
    await pending  # with top-level await

Several submissions are queued together. Their results are recorded, fitted,
reported, and update the platform in the order they start (submission, or
confirmation, see below), whatever the order their jobs complete in; each
acquisition uses the platform state at the time it starts, so acquisitions
submitted together do not see each other's updates.

**In Marimo**, background executions integrate with the reactive runtime, with
nothing to set up: they run in a ``mo.Thread``, and a pending execution is
reactive state, so that every cell referencing it runs again when it
completes. Displayed as the output of the cell submitting it, it shows a
spinner, replaced by the result when ready. Downstream cells wait for it with
``mo.stop``, without blocking anything:

.. code-block:: python

    # one cell
    pending = executor.submit(protocols.ramsey(delay=(10, 1000, 100)), nshots=500)
    pending  # a spinner, then the result

    # another cell: runs again when the execution completes
    ramsey = pending()
    mo.stop(ramsey is None, mo.md("*Waiting for the acquisition…*"))
    ramsey.results

It is a ``mo.state`` getter like any other, for any other use of Marimo's
reactivity. (``await pending`` also works, but holds the notebook until the
result arrives.)

**In Jupyter**, the pending execution's display updates by itself when the
result arrives, and ``pending.result()`` waits for it where needed; dependent
cells do not run again by themselves, as usual in Jupyter.

**Progress.** While running, a pending execution shows what it is doing, and
how long it has been since submitted:

- acquiring: *queued* (remote jobs, until they reach their node), then, for
  remote jobs, *starting*, *importing*, *creating the platform*,
  *connecting*, *preparing* (until the first execution on the platform),
  then *running*, and *receiving the data* (remote jobs, once acquired);
- processing, with a different indicator: *waiting for earlier executions*
  (processed in order), *recording*, *fitting*, *reporting*, *updating*.

While running, the progress comes from the estimates logged by qibolab and its
drivers, captured where the acquisition runs (locally, or by the remote
worker, which streams them back), at two levels:

- each ``platform.execute()`` call, estimated by qibolab as a whole: an
  acquisition may make any number of them, not known in advance
  (``Execution k / ?``);
- each batch of a call, estimated by the driver (Qblox), before it runs
  (``Batch j / ?``): together they refine the estimate of their execution.

Each has a bar filling in its estimated time, turning red and striped when
running over. With several executions, the acquisition line adds up the time
elapsed and the estimates so far. *Estimates* unfolds all of them, with the
time measured until the next event (for batches, this includes fetching their
results and preparing the next one). The events are in ``pending.timeline``
(grouped as ``pending.timeline.executions``), and the phase in
``pending.phase``. Capturing the estimates changes nothing in the logs.
Where the time went is in ``completed.profile()`` (and ``pending.profile()``),
for blocking calls too: each step, from the queue to the report, and how long
it took. Displayed executions show it folded, with a *⏱ profile* toggle next to
their timing: it lists the steps, highlighting the longest, with buttons
copying them, with their context, as a Markdown table (for issues), or as
CSV. The context tells how the execution ran (local or remote, the queue, the
agent, started for it or already warm, a job followed after a reconnection)
and the versions of Qibocal, qibolab, and qibocal-widgets, locally and
remotely; host names are left out. The start of the agent, once per session,
is a step of its own. Outside of the acquisition itself, the
imports of the remote job are often the largest part: on a network filesystem,
on a node with a cold cache, importing qibocal, qibolab, and the drivers may
take tens of seconds. Environments are installed with their bytecode compiled,
so that the first job does not compile it.

.. code-block:: python

    completed.profile()  # step, took (s), at (s since the start)
    completed.profile_report()  # Markdown, with the context
    completed.profile_report("csv")

Announcing the number of batches and executions in advance needs qibolab and
Qibocal (`qibolab#1629 <https://github.com/qiboteam/qibolab/issues/1629>`_,
`qibocal#1768 <https://github.com/qiboteam/qibocal/issues/1768>`_).

**Cancelling.** ``pending.cancel()``, or the *✕ Cancel* button of its progress,
ends an execution as ``cancelled`` (``pending.result()`` raises
:class:`~qibocal_widgets.Cancelled`), offering to *Run again*:

- not started yet (waiting for confirmation, for the instruments, or for its
  turn): it never acquires;
- queued remotely: the job is stopped, cancelling its allocation if still
  waiting in the queue, with ``SIGTERM`` first (on which qibolab disconnects
  the instruments), then ``SIGKILL`` after 10 s; the session forgets it;
- acquiring in the kernel, or in a remote agent without a queue: it stops
  before its next execution on the platform, or batch, where qibolab logs its
  estimates; the current one is not interrupted, so that the instruments are
  left in a consistent state.

Recording, fitting, and reporting are not cancelled: they are short, and the
data are already recorded. Interrupting the kernel during a blocking remote
call (``executor(bound)``) stops its remote job too.

**Avoiding repeated acquisitions.** Notebooks run cells again, unintentionally
too (in Marimo, whenever an upstream cell changes). With ``reuse=True``,
``submit`` returns an identical execution instead of acquiring again: one still
running, or one recorded in the session, loaded from disk. Executions are
identical with the same protocol, parameters, overrides, and targets, whatever
the platform state: the updates of other executions do not cause acquiring
again (submit without ``reuse`` for that). Nothing is cached besides the
session itself, which records a small key next to each execution; reusing
recorded executions works across kernel restarts (attaching the session), for
protocols registered in Qibocal, which it can load back. A new executor starts
a new session, unless attached to an existing one: in Marimo, running again
the cell defining the executor leaves nothing to reuse.

**Acquiring on request.** Notebooks run cells for many reasons: in Marimo,
cells submitting executions reference the executor, so they run whenever the
executor's cell runs, including the first time, because a single experiment
needs it. With ``confirm=True``, nothing starts by itself: each execution is
``ready``, displayed as a *Run* button (e.g. "▶ Run ramsey", its overrides in
the tooltip), and starts when clicked.

.. code-block:: python

    executor = Executor(None, runner=Remote("lab"), frontends=[Marimo()],
                        confirm=True, reuse=True)

    pending = executor.submit(protocols.ramsey(delay=(10, 1000, 100)), nshots=500)
    pending  # a Run button, then the spinner, then the result

A notebook full of experiments then opens with their buttons, and the results
of those already recorded in the session (reused executions need no
confirmation). Both are executor defaults, overridden by ``submit``'s
arguments of the same names; both are off by default.

- ``pending.start()`` confirms from code, as the button does.
- Downstream cells see ``pending()`` as ``None`` until the execution completes,
  as while running. Waiting for an execution that is not started
  (``pending.result()``, ``await pending``) raises
  :class:`~qibocal_widgets.NotStartedError` instead: it would block the
  confirmation itself.
- Executions are processed in the order they start, not in the order they
  were submitted: one waiting for confirmation does not hold the others.
- Where no frontend can show the button (e.g. a script, or a notebook run as
  an app without a browser), executions start at once, so that the same
  notebook runs everywhere.

**Running again.** A completed execution shows a *Run again* button
(``pending.rerun()`` from code), whatever ``reuse``: the protocol is acquired
again, and recorded anew in the session, where reuse then finds the latest.
The same handle follows the new execution: cells referencing it see it running
again, then the new result. Each protocol runs again on its own: the protocols
depending on its update, submitted elsewhere, are not repeated, and with
``reuse`` they keep their recorded results until run again as well.

Alternatively, in Marimo only, set the runtime to mark dependent cells as stale
instead of running them (``on_cell_change = "lazy"``, in the notebook settings
or under ``[tool.marimo.runtime]`` in ``pyproject.toml``).

**Detached jobs.** Acquisitions through the queue are detached from the
notebook: each has a folder of its own on the remote machine
(``~/.cache/qibocamp/jobs``), where its output is written, and survives the
loss of the SSH connection, and restarts of the kernel. The session records
them (``remote-jobs.json``) until fetched: after a disconnection, or a
restart (attaching the session), submitting the same execution with
``reuse=True`` follows the job, still running or done meanwhile, instead of
acquiring again. Fetched jobs are removed; those never fetched, a week after
they ended. A pending execution whose connection was lost fails with a
:class:`~qibocal_widgets.remote.RemoteError` whose ``ended`` is ``False``: the
job may still be running.

Acquisitions without a queue (``ssh`` only) run in the agent itself, warm,
and are not detached: they end with it.

Queue
-----

While acquisitions wait in the queue, the queue itself can be followed from
the notebook, through the same connection:

.. code-block:: python

    remote = executor.runner
    remote.queue()  # asked once: jobs, node groups, summary, remote user
    remote.monitor()  # a refreshable view, for Jupyter and Marimo

By default, the whole partition the acquisitions are submitted to is shown,
so that the jobs ahead are visible. The jobs of the remote user are
highlighted, and those submitted by the runner are tagged: its ``srun`` jobs are
named ``qibocal-widgets-<action>``, unless the ``slurm`` options set a name.
The monitor refreshes periodically while displayed (every 30 seconds by
default, ``interval=0`` to refresh only on request), and can show only the
user's jobs. Every refresh asks the controller, so keep the interval
reasonable.

The query (``squeue``, ``sinfo`` and ``whoami`` in a single round trip) and its
fields are the ones of Qibocamp, whose launcher shows the same queue.

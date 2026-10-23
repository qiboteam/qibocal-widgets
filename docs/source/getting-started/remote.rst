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
``queue`` and/or ``slurm``              one blocking ``srun`` job per step,
                                        from the current machine (access node)
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
        "lab": {"ssh": "-J bastion me@login", "queue": "qpu", "platform": "chip"}
      }
    }

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

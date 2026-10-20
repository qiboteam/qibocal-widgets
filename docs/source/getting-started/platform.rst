Platform state
==============

The calibration state of a platform is made of qibolab's parameters and
Qibocal's calibration (``parameters.json`` and ``calibration.json``).
:class:`~qibocal_widgets.PlatformState` explores and updates it by path, from
code or with an interactive explorer, and the two are designed to be used
together.

.. code-block:: python

    state = executor.platform_state

    state["parameters.configs.0/drive.frequency"]  # a value
    state.find("frequency_01")  # {path: value}, for every matching leaf
    state.update({"calibration.single_qubits.0.qubit.frequency_01": 4.1e9})
    state.explore()  # the interactive explorer

Paths
-----

Paths are dotted, rooted at the document: ``parameters.`` or
``calibration.``, followed by the keys of the JSON files (numeric segments
index lists):

.. code-block:: text

    parameters.configs.0/drive.frequency
    parameters.native_gates.two_qubit.0-1.CZ
    calibration.single_qubits.0.qubit.frequency_01

Within each document, they are the paths of qibolab's ``Platform.update`` and
of the platform view of the qibocal-report dashboard. Every method taking a
path also accepts:

- a path within a document, as copied from the dashboard, which shows one
  file at a time (``configs.0/drive.frequency``);
- any text quoting a path, such as a pasted API call or its output
  (``state["parameters.configs.0/drive.frequency"]``).

Updates
-------

:meth:`~qibocal_widgets.PlatformState.update` applies all the changes at once,
after validating the whole state against the qibolab and Qibocal models: if
any change is invalid, none is applied. Paths must exist, so typos are
rejected rather than creating new entries.

``executor.platform_state`` is the state the steps run on, as known by the
runner. Updates through it behave as protocol updates do: they are applied to
the local platform, or kept by a :class:`~qibocal_widgets.remote.Remote`
runner for its next jobs, and recorded in the session (``new_platform/``).
Without a local platform, a remote runner asks the remote machine for the
current state the first time it is needed.

Other states:

- :meth:`PlatformState.of(platform) <qibocal_widgets.PlatformState.of>`,
  bound to any platform object;
- :meth:`PlatformState.load(path) <qibocal_widgets.PlatformState.load>`, a
  read-only snapshot of a platform dump, or of a session folder (its latest
  state; ``path / "platform"`` for its start);
- :meth:`state.snapshot() <qibocal_widgets.PlatformState.snapshot>`, a
  read-only copy, e.g. to compare later.

:meth:`~qibocal_widgets.PlatformState.diff` lists the leaves changed with
respect to another state:

.. code-block:: python

    start = PlatformState.load(executor.path / "platform")
    executor.platform_state.diff(start)  # {path: (before, now)}

Explorer
--------

:meth:`~qibocal_widgets.PlatformState.explore` returns a compact explorer,
displayed natively in both Jupyter and Marimo (it is an
`anywidget <https://anywidget.dev>`_, included in both extras):

.. code-block:: python

    executor.platform_state.explore(editable=True, compare=start)

- The navigation bar accepts paths in any of the forms above, so a path or a
  piece of code can be pasted to jump there. Any other text searches the
  leaves by path.
- Every entry has buttons copying its full path, and its value, to the
  clipboard, ready to be pasted in code.
- With ``editable=True``, leaves can be edited (values are JSON: quote
  strings). Edits go through :meth:`~qibocal_widgets.PlatformState.update`,
  and the explorer shows the equivalent code, with a button to copy it.
- With ``compare``, entries differing from another state are highlighted,
  with their previous value, and can be shown alone (*changed only*):
  comparing with the start of the session shows what the calibration changed.

Values are displayed in a human-friendly form (e.g. ``4.125 GHz``), as in the
dashboard; the exact value is shown on hover, and copied.

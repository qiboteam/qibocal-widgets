Examples
========

The `examples <https://github.com/qiboteam/qibocal-widgets/tree/main/examples>`_
folder of the repository contains two notebooks per frontend, with the same
content in Marimo (``examples/marimo``) and Jupyter (``examples/jupyter``).

Calibration
-----------

A tour of the features of ``qibocal-widgets``, calibrating a simulated
platform locally. Executed when building this documentation, and exported
with its outputs:

- `Marimo <examples/marimo/calibration.html>`_ (``examples/marimo/calibration.py``)
- `Jupyter <examples/jupyter/calibration.html>`_ (``examples/jupyter/calibration.ipynb``)

It covers:

1. the executor, with its frontend and session folder;
2. implicit display, step by step, and notes;
3. updating the platform;
4. exploring and editing the platform state;
5. the explicit helpers, and displaying executions of a plain Qibocal
   executor;
6. middleware, and attaching a new executor to an existing session;
7. loading recorded executions, and starting a new session.

The simulated platform, two coupled qutrits, is the ``qutrits`` platform of
`qibolab-simulator <https://github.com/qiboteam/qibolab-simulator>`_, copied in
``examples/platforms``, which the notebooks select by setting
``QIBOLAB_PLATFORMS`` themselves. To run them, install the ``examples``
dependency group, which includes the simulator, from a clone of this
repository:

.. code-block:: sh

    uv sync --all-extras --group examples
    uv run marimo edit examples/marimo/calibration.py
    uv run --with jupyterlab jupyter lab examples/jupyter/calibration.ipynb

Remote
------

Remote execution, from a laptop or an access node, without any local platform
(`Marimo <https://github.com/qiboteam/qibocal-widgets/blob/main/examples/marimo/remote.py>`_,
`Jupyter <https://github.com/qiboteam/qibocal-widgets/blob/main/examples/jupyter/remote.ipynb>`_):
the connection (inline or named), the remote environment, the remote platform
state, acquisitions in the queue, remote updates, the queue monitor, and
continuing a session after a restart.

It needs a cluster with the instruments, so it is not executed here: edit its
connection, or select a stored one with ``QIBOCAL_WIDGETS_CONNECTION``. It
runs in a lighter environment than the calibration notebooks, with no
simulator nor platform locally:

.. code-block:: sh

    uv sync --extra marimo  # or --extra jupyter
    uv run marimo edit examples/marimo/remote.py

The notebooks write their session folders in a ``var/`` folder next to them,
unless a reports folder is set (``QIBOCAMP_REPORTS_DIR``).

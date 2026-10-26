Examples
========

Two example notebooks, in the
`examples <https://github.com/qiboteam/qibocal-widgets/tree/main/examples>`_
folder of the repository, tour all the features of ``qibocal-widgets``. They
are executed when building this documentation, and exported with their
outputs:

- `Marimo <examples/marimo_notebook.html>`_ (``examples/marimo_notebook.py``)
- `Jupyter <examples/jupyter_notebook.html>`_ (``examples/jupyter_notebook.ipynb``)

Both cover the same ground:

1. the executor, with its frontend and session folder;
2. implicit display, step by step, and notes;
3. updating the platform;
4. exploring and editing the platform state;
5. the explicit helpers, and displaying executions of a plain Qibocal
   executor;
6. middleware, and attaching a new executor to an existing session;
7. loading recorded executions, and starting a new session;
8. remote execution, and the queue monitor.

They run on a simulated platform, two coupled qutrits: the ``qutrits``
platform of `qibolab-simulator <https://github.com/qiboteam/qibolab-simulator>`_,
copied in ``examples/platforms``, which the notebooks select by setting
``QIBOLAB_PLATFORMS`` themselves. To run them, install the ``examples``
dependency group, which includes the simulator, from a clone of this
repository:

.. code-block:: sh

    uv sync --all-extras --group examples
    uv run marimo edit examples/marimo_notebook.py
    uv run --with jupyterlab jupyter lab examples/jupyter_notebook.ipynb

Their outputs (session folders) are written to ``examples/var``, unless a
reports folder is set (``QIBOCAMP_REPORTS_DIR``).

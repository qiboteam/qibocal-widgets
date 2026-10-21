Examples
========

The example notebooks of the
`repository <https://github.com/qiboteam/qibocal-widgets/tree/main/examples>`_,
executed on Qibocal's ``mock`` platform when building this documentation, and
exported with their outputs:

- `Marimo <examples/marimo_ramsey.html>`_ (``examples/marimo_ramsey.py``)
- `Jupyter <examples/jupyter_ramsey.html>`_ (``examples/jupyter_ramsey.ipynb``)

Both run a Ramsey experiment: acquisition, fit, and report, each displayed by
the executor's frontend, then the explicit helpers.

To run them yourself on the mock platform, point ``QIBOLAB_PLATFORMS`` to a
folder containing it (e.g. ``tests/platforms`` in a clone of this
repository), or set ``QIBOCAL_WIDGETS_PLATFORM`` to the name of your own
platform.

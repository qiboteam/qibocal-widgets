Qibocal Widgets
===============

Notebook integration for the `Qibocal <https://github.com/qiboteam/qibocal>`_
executor, for both `Marimo <https://marimo.io>`_ and
`Jupyter <https://jupyter.org>`_.

Every phase of Qibocal's executor (``acquire``, ``fit``, ``report``,
``update``, or the full ``executor(bound)`` call) returns a ``Completed``
object. ``qibocal-widgets`` provides a drop-in executor, composed of a
runner, middleware, and frontends: with a frontend, its outputs display
themselves in the notebook (raw data tables, per-target report figures and fit tables), with no
helper call.

.. code-block:: python

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo

    executor = Executor.create(platform=platform, path="var/report", frontends=[Marimo()])
    with executor:
        completed = executor(bound, targets=[0, 1])
    completed  # renders raw data and reports

.. warning::

    The package is in early development, and targets the executor interface
    developed on the ``protodev`` branch of Qibocal, which is not yet released.

.. toctree::
    :maxdepth: 2
    :caption: Getting started

    getting-started/installation
    getting-started/quickstart
    getting-started/remote

.. toctree::
    :maxdepth: 2
    :caption: Reference

    api-reference/index

.. toctree::
    :maxdepth: 1
    :caption: Qibo ecosystem

    Qibo <https://qibo.science/qibo/stable/>
    Qibolab <https://qibo.science/qibolab/stable/>
    Qibocal <https://qibo.science/qibocal/stable/>


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

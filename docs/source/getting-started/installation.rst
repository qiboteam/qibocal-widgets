Installation
============

The package exposes one optional extra per notebook frontend. Install the one
you use, or both:

.. code-block:: sh

    uv add "qibocal-widgets[marimo]"
    uv add "qibocal-widgets[jupyter]"

or, with ``pip``:

.. code-block:: sh

    pip install "qibocal-widgets[marimo,jupyter]"

The ``jupyter`` extra installs ``ipywidgets``, used to render accordions and
tabs.

Qibocal version
---------------

``qibocal-widgets`` targets the executor interface developed on the
``protodev`` branch of Qibocal. Until that is released, pin Qibocal to the
branch in your own project:

.. code-block:: toml

    [tool.uv.sources]
    qibocal = { git = "https://github.com/qiboteam/qibocal.git", branch = "protodev" }

and install ``qibocal-widgets`` itself from the repository:

.. code-block:: sh

    uv add "qibocal-widgets[marimo] @ git+https://github.com/qiboteam/qibocal-widgets"

Development
-----------

.. code-block:: sh

    git clone https://github.com/qiboteam/qibocal-widgets
    cd qibocal-widgets
    uv sync --all-extras --group tests --group analysis --group docs
    uv run pytest
    uv run --with poethepoet poe docs

`devenv <https://devenv.sh/>`_ users can run ``devenv shell`` instead: it
installs Python, all the extras and development groups (the example
simulator included), ``poe``, ``prek`` and Jupyter, and sets
``QIBOLAB_PLATFORMS`` to the example platforms.

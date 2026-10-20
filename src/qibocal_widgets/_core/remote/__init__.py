"""Remote execution: dispatching steps to the machine with the instruments.

- :mod:`.config`: connections and their configuration file.
- :mod:`.jobs`: JSON and NPZ encoding of jobs, client side.
- :mod:`.transport`: ``ssh``/``srun`` command lines and job exchange.
- :mod:`.worker`: self-contained worker, executed remotely.
- :mod:`.runner`: the :class:`~qibocal_widgets.remote.Remote` runner.
"""

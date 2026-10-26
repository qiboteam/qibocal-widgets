> Copied from the examples of
> [qibolab-simulator](https://github.com/qiboteam/qibolab-simulator/tree/4ad372441fe3c58952682b0a900f4542c4c84a46/examples/platforms/qutrits)
> (`4ad3724`), to run the example notebooks of qibocal-widgets. It requires
> `qibolab-simulator` (the `examples` dependency group).

# Two qutrits

This example converts Qibolab's
[split-transmon emulator platform](https://github.com/qiboteam/qibolab/tree/10b4bce0b82237cc94d726990054a4219ed2f397/tests/instruments/emulator/platforms/split-transmons).
It preserves the two devices' frequencies, anharmonicities, sweetspots, 12 MHz
exchange coupling, channel names, and Gaussian RX/RX90/RX12 and SNZ CZ pulse
parameters. Both subsystems have three levels. Probe channels are declared for
Qibocal's platform metadata, but are not physical resonator simulations.

Load a fresh instance from the repository root:

```python
from examples.platforms.qutrits import create_platform

platform = create_platform()
```

Alternatively, use Qibolab's ordinary platform loader:

```sh
export QIBOLAB_PLATFORMS="$PWD/examples/platforms"
```

```python
from qibolab import create_platform

platform = create_platform("qutrits")
```

The conversion explicitly changes the physical/readout contract:

- Fundamental-transition T1/T2 become scalar oscillator parameters. The old
  independently specified 1-2 lifetimes are not retained: oscillator damping
  fixes the level-2 population lifetime to T1/2.
- Ideal terminal acquisition replaces the electronics configuration. Both
  excited levels are classified as non-ground, not distinguished from each other.
- RX12 and CZ pulse parameters are starting points from the upstream platform,
  not a claim that the gates remain calibrated under this rotating-wave model.
- Ground initialization is unconditional between experiments; relaxation time
  does not simulate memory between shots.

The [Qibocal marimo notebook](../../../notebooks/calibration.py) provides explicit
acquisition, fitting, reporting, and optional update phases, followed by a
full-operation `Executor.__call__()` example on a separate platform.
Use Python 3.11-3.13:

```sh
uv sync --group notebooks
uv run --group notebooks marimo edit notebooks/calibration.py
```

The notebook uses `qibocal.create_calibration_platform("qutrits")`
directly. `calibration.json` supplies the initial qubit frequencies, sweetspots,
and coherence times matching the simulator model.

Edit the notebook's Python settings and protocol calls to configure experiments;
tables and plots are the only interactive UI. Set `coupled = False` for fast
single-qubit experiments in the staged section, or retain the original coupled
model with `True`. The full-operation cell has its own `full_coupled` setting.
Large coupled-system delays can remain
expensive: a shared frame does not remove the frequency difference between the
two transmons.

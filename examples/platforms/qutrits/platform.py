"""Simulator conversion of Qibolab's split-transmon emulator hardware."""

from qibolab import AcquisitionChannel, DcChannel, Hardware, IqChannel, Qubit
from qibolab_simulator import SimulatorController, register_configs


def create(*, workers: int = 1, seed: int = 1234) -> Hardware:
    register_configs()
    qubits = {
        q: Qubit.default(q, drive_extra={(1, 2): f"{q}/drive12"}) for q in range(2)
    }
    channels = {}
    for qubit in qubits.values():
        channels |= {
            qubit.acquisition: AcquisitionChannel(probe=qubit.probe),
            qubit.drive: IqChannel(),
            qubit.drive_extra[1, 2]: IqChannel(),
            qubit.flux: DcChannel(),
            qubit.probe: IqChannel(),
        }
    return Hardware(
        instruments={
            "simulator": SimulatorController(
                channels=channels, workers=workers, seed=seed
            )
        },
        qubits=qubits,
    )

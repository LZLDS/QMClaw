"""
T1 Relaxation Time Measurement.

Measures the qubit relaxation time T1 using a variable delay pulse sequence.
"""

from typing import Annotated


def t1_measurement(
    target: Annotated[str, "Qubit name (e.g., q1)"],
    delay_start: Annotated[float, "Start delay (ns)"] = 100,
    delay_end: Annotated[float, "End delay (ns)"] = 10000,
    delay_step: Annotated[float, "Delay step (ns)"] = 200,
    shots: Annotated[int, "Number of shots"] = 1024,
) -> dict:
    """Measure T1 relaxation time.

    Args:
        target: Qubit name
        delay_start: Start delay in nanoseconds
        delay_end: End delay in nanoseconds
        delay_step: Delay step in nanoseconds
        shots: Number of shots per point

    Returns:
        Dictionary with experiment results
    """
    import numpy as np

    # Generate delay points
    delays = np.arange(delay_start, delay_end + delay_step, delay_step)

    # Simulated T1 data (in real experiment, this would come from LabRAD)
    # Exponential decay: signal = A * exp(-t/T1) + baseline
    T1_true = 4500  # ns
    baseline = 0.1
    amplitude = 0.9
    signal = amplitude * np.exp(-delays / T1_true) + baseline
    noise = np.random.normal(0, 0.02, len(delays))
    signal += noise

    return {
        "data": {
            "type": "array",
            "value": signal.tolist(),
        },
        "delays": {
            "type": "array",
            "value": delays.tolist(),
        },
        "status": "success",
        "results": {
            "T1": T1_true,
            "unit": "ns",
        },
    }

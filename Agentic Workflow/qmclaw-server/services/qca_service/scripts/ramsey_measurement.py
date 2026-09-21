"""
Ramsey Measurement.

Measures qubit T2* dephasing time using Ramsey pulse sequence.
"""

from typing import Annotated


def ramsey_measurement(
    target: Annotated[str, "Qubit name (e.g., q1)"],
    delay_start: Annotated[float, "Start delay (ns)"] = 0,
    delay_end: Annotated[float, "End delay (ns)"] = 2000,
    delay_step: Annotated[float, "Delay step (ns)"] = 50,
    detuning: Annotated[float, "Detuning frequency (MHz)"] = 1.0,
    shots: Annotated[int, "Number of shots"] = 1024,
) -> dict:
    """Measure T2* dephasing time with Ramsey sequence.

    Args:
        target: Qubit name
        delay_start: Start delay in nanoseconds
        delay_end: End delay in nanoseconds
        delay_step: Delay step in nanoseconds
        detuning: Detuning frequency in MHz
        shots: Number of shots per point

    Returns:
        Dictionary with experiment results
    """
    import numpy as np

    # Generate delay points
    delays = np.arange(delay_start, delay_end + delay_step, delay_step)

    # Simulated Ramsey data with oscillation and decay
    T2_star = 800  # ns
    omega = 2 * np.pi * detuning / 1000  # Convert MHz to GHz rad/ns

    signal = 0.5 + 0.5 * np.exp(-delays / T2_star) * np.cos(omega * delays)
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
            "T2_star": T2_star,
            "unit": "ns",
            "detuning_fit": detuning,
        },
    }

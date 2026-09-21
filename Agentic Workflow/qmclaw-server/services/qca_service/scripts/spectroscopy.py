"""
Spectroscopy Measurement.

Broad frequency scan to find qubit resonance.
"""

from typing import Annotated


def spectroscopy(
    target: Annotated[str, "Qubit name (e.g., q1)"],
    freq_start: Annotated[float, "Start frequency (GHz)"] = 4.0,
    freq_end: Annotated[float, "End frequency (GHz)"] = 6.0,
    freq_step: Annotated[float, "Frequency step (MHz)"] = 1.0,
    power: Annotated[float, "Drive power (dBm)"] = -20,
    shots: Annotated[int, "Number of shots"] = 512,
) -> dict:
    """Perform spectroscopy scan to find qubit resonance.

    Args:
        target: Qubit name
        freq_start: Start frequency in GHz
        freq_end: End frequency in GHz
        freq_step: Frequency step in MHz
        power: Drive power in dBm
        shots: Number of shots per point

    Returns:
        Dictionary with experiment results
    """
    import numpy as np

    # Generate frequency points
    freq_mhz = np.arange(freq_start * 1000, freq_end * 1000 + freq_step, freq_step)
    frequencies = freq_mhz / 1000  # Convert back to GHz for display

    # Simulated spectroscopy with Lorentzian dip
    f_resonance = 5.2  # GHz (example resonance)
    linewidth = 5  # MHz
    baseline = 0.8
    depth = 0.4

    transmission = baseline - depth / (1 + ((freq_mhz - f_resonance * 1000) / linewidth) ** 2)
    noise = np.random.normal(0, 0.01, len(frequencies))
    transmission += noise

    return {
        "data": {
            "type": "array",
            "value": transmission.tolist(),
        },
        "frequencies": {
            "type": "array",
            "value": frequencies.tolist(),
        },
        "status": "success",
        "results": {
            "resonance_frequency": f_resonance,
            "unit": "GHz",
            "linewidth": linewidth,
        },
    }

"""Adapt Jasmine's Week 1 PSP calculation into a bounded, read-only library.

NASA measurement files are bundled separately with their original provenance.
Method: four-second alignment, full-window Hann trace periodograms, linear
detrending, and frequency-bin integration. No network or output-file writes.
"""

from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import signal

DATA = Path(__file__).resolve().parent / "data"
DT = 4.0
MU0 = 4 * np.pi * 1e-7
PROTON_MASS_KG = 1.67262192369e-27
REJECT_VELOCITY_BITS = sum(1 << bit for bit in (0, 2, 3, 8, 10, 11))
BANDS_HZ = {"total": (0.001, 0.030), "5min": (0.0025, 0.0045), "2min": (0.006, 0.012)}
LIMITATIONS = [
    "Only the two bundled intervals are supported; this is not a live archive query.",
    "QTN electron density is a proton-density proxy; alpha particles are neglected.",
    "SPAN-ion partial moments can retain field-of-view bias.",
    "Cross-helicity sign follows z_plus=deltaV+deltab, without a polarity flip.",
    "These measurements do not establish statistical significance or solar-source attribution.",
]


def catalog():
    return json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))["intervals"]


def interpolate(times, values, grid, max_gap_s=60):
    order = np.argsort(times)
    times, values = times[order], values[order]
    if len(times) < 2 or not np.all(np.diff(times) > 0):
        raise ValueError("Need at least two unique valid timestamps per instrument. Check the input data.")
    index = np.searchsorted(times, grid, side="left")
    safe = np.clip(index, 1, len(times) - 1)
    exact = times[np.clip(index, 0, len(times) - 1)] == grid
    valid = ((index > 0) & (index < len(times)) & (times[safe] - times[safe - 1] <= max_gap_s)) | exact
    if not np.all(valid):
        raise ValueError("Alignment would extrapolate or bridge a gap over 60 seconds. Use a fully supported interval.")
    if values.ndim == 1:
        return np.interp(grid, times, values)
    return np.column_stack([np.interp(grid, times, values[:, component]) for component in range(3)])


def align(data, entry):
    start = datetime.fromisoformat(entry["start_utc"].replace("Z", "+00:00")).timestamp()
    stop = datetime.fromisoformat(entry["stop_utc_exclusive"].replace("Z", "+00:00")).timestamp()
    count = int(round((stop - start) / DT))
    grid = start + DT * (np.arange(count) + 0.5)

    raw_b = data["B_RTN_nT"]
    good = np.isfinite(raw_b).all(axis=1) & (np.abs(raw_b) <= 1e10).all(axis=1)
    times, magnetic = data["mag_time_unix_s"][good], raw_b[good]
    keep = (times >= start) & (times < stop)
    bins = np.floor((times[keep] - start) / DT).astype(int)
    counts = np.bincount(bins, minlength=count)
    if np.any(counts == 0):
        raise ValueError("A four-second magnetic bin is empty. Use an interval with complete magnetic coverage.")
    magnetic = np.column_stack([
        np.bincount(bins, weights=magnetic[keep, component], minlength=count) / counts
        for component in range(3)
    ])

    flags = data["velocity_quality_flag"]
    good_v = np.isfinite(data["V_RTN_kms"]).all(axis=1) & (flags != 65535) & ((flags & REJECT_VELOCITY_BITS) == 0)
    velocity = interpolate(data["velocity_time_unix_s"][good_v], data["V_RTN_kms"][good_v], grid)
    raw_n = data["electron_density_cm3"]
    good_n = np.isin(data["density_quality_flag"], [1, 2, 4]) & np.isfinite(raw_n) & (raw_n > 0) & (raw_n < 1e10)
    density = interpolate(data["density_time_unix_s"][good_n], raw_n[good_n], grid)
    # Convert nT -> T, cm^-3 -> m^-3, then m/s -> km/s before detrending.
    magnetic_velocity = magnetic * 1e-9 / np.sqrt(MU0 * PROTON_MASS_KG * density[:, None] * 1e6) / 1e3
    return grid, magnetic, velocity, magnetic_velocity


def trace_psd(values):
    frequency, components = signal.periodogram(values, fs=1 / DT, window="hann", detrend="linear", axis=0, scaling="density", return_onesided=True)
    return frequency, components.sum(axis=1)


def band_diagnostics(magnetic, velocity, magnetic_velocity, include_peak=False):
    d_velocity = signal.detrend(velocity, axis=0)
    d_magnetic_velocity = signal.detrend(magnetic_velocity, axis=0)
    frequency, power = trace_psd(magnetic)
    _, plus = trace_psd(d_velocity + d_magnetic_velocity)
    _, minus = trace_psd(d_velocity - d_magnetic_velocity)
    spacing = frequency[1] - frequency[0]
    masks = {name: (frequency >= low) & (frequency <= high) for name, (low, high) in BANDS_HZ.items()}
    energy = {name: float(power[mask].sum() * spacing) for name, mask in masks.items()}
    if not np.isfinite(energy["total"]) or energy["total"] <= 0:
        raise ValueError("No finite positive magnetic energy in 1–30 mHz. Check the input vectors and units.")
    result = {"magnetic_energy_1_30_mHz_nT2": energy["total"], "frequency_spacing_mHz": float(spacing * 1000)}
    for band in ("5min", "2min"):
        ep, em = float(plus[masks[band]].sum() * spacing), float(minus[masks[band]].sum() * spacing)
        if not np.isfinite(ep + em) or ep + em <= 0:
            raise ValueError(f"No Elsasser energy in {band}. Check velocity and density coverage.")
        result[f"magnetic_energy_{band}_nT2"] = energy[band]
        result[f"energy_fraction_{band}"] = energy[band] / energy["total"]
        result[f"sigma_c_{band}"] = (ep - em) / (ep + em)
    result["peak_period_s"] = None
    if include_peak:
        smoothed = np.convolve(frequency * power, np.ones(3) / 3, mode="same")
        candidates = np.flatnonzero(masks["5min"])
        result["peak_period_s"] = float(1 / frequency[candidates[np.argmax(smoothed[candidates])]])
    return result


def analyze_interval(interval_id):
    entries = {entry["id"]: entry for entry in catalog()}
    if interval_id not in entries:
        raise ValueError("Unknown interval. Call list_psp_intervals and use interval-a or interval-b.")
    entry = entries[interval_id]
    path = DATA / entry["file"]
    if path.parent.resolve() != DATA.resolve() or path.suffix != ".npz":
        raise ValueError("Invalid data manifest path. Restore this plugin's original data directory.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Data checksum failed. Restore the bundled file before analyzing it.")
    with np.load(path, allow_pickle=False) as data:
        grid, magnetic, velocity, magnetic_velocity = align(data, entry)
    result = band_diagnostics(magnetic, velocity, magnetic_velocity, include_peak=interval_id == "interval-b")
    return {
        "interval_id": interval_id,
        "start_utc": entry["start_utc"],
        "stop_utc_exclusive": entry["stop_utc_exclusive"],
        "cadence_s": DT,
        "sample_count": len(grid),
        **result,
    }


def compare_intervals(first="interval-a", second="interval-b"):
    if first == second:
        raise ValueError("Choose two different intervals: interval-a and interval-b.")
    results = [analyze_interval(first), analyze_interval(second)]
    a, b = results
    return {
        "intervals": results,
        "comparison": {
            "first_interval_id": first,
            "second_interval_id": second,
            "total_magnetic_energy_ratio_second_over_first": b["magnetic_energy_1_30_mHz_nT2"] / a["magnetic_energy_1_30_mHz_nT2"],
            "five_minute_fraction_difference_second_minus_first": b["energy_fraction_5min"] - a["energy_fraction_5min"],
            "two_minute_fraction_difference_second_minus_first": b["energy_fraction_2min"] - a["energy_fraction_2min"],
        },
        "method": "4 s alignment; full-window Hann one-sided trace PSD; linear detrending; sum PSD*df over each band.",
        "bands_mHz": {name: [low * 1000, high * 1000] for name, (low, high) in BANDS_HZ.items()},
        "cross_helicity_convention": "z_plus=deltaV+deltab; z_minus=deltaV-deltab; sigma_c=(E_plus-E_minus)/(E_plus+E_minus)",
        "limitations": LIMITATIONS,
    }

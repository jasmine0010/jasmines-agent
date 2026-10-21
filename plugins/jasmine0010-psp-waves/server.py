# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["mcp==2.3.0", "numpy==2.1.3", "scipy==1.15.3"]
# ///
"""Read-only PSP wave diagnostics, exposed through the official MCP SDK."""

from typing import Literal

from mcp.server import MCPServer

from diagnostics import LIMITATIONS, analyze_interval, catalog, compare_intervals

mcp = MCPServer("jasmine0010-psp-waves")
Interval = Literal["interval-a", "interval-b"]


@mcp.tool()
def list_psp_intervals() -> dict:
    """List the two bundled public Parker Solar Probe intervals available for wave diagnostics.

    Call first when the user asks what data are available. Returns interval IDs,
    half-open UTC start/stop times (ISO 8601, Z), and supported frequency bands.
    No parameters. This is a fixed offline dataset, not an arbitrary-date archive search.
    Use an exact returned ID with analyze_psp_waves, e.g. interval-b.
    """
    return {
        "intervals": [{key: entry[key] for key in ("id", "start_utc", "stop_utc_exclusive")} for entry in catalog()],
        "bands_mHz": {"total": [1, 30], "five_minute": [2.5, 4.5], "two_minute": [6, 12]},
        "coordinate_system": "RTN (radial, tangential, normal)",
        "data_source": "Bundled NASA CDAWeb FIELDS magnetic/QTN and SWEAP SPAN-ion public measurements.",
    }


@mcp.tool()
def analyze_psp_waves(interval_id: Interval) -> dict:
    """Measure magnetic band energies and signed cross helicity for one bundled PSP interval.

    interval_id must be interval-a or interval-b; example: interval_id='interval-b'.
    Call list_psp_intervals to see exact UTC coverage. Returns energies in nT^2,
    dimensionless five-minute (2.5–4.5 mHz) and two-minute (6–12 mHz) fractions of
    1–30 mHz trace PSD energy, and signed sigma_c in [-1,1] using z_plus=dV+db.
    Includes a five-minute-band fP peak period in seconds only for interval-b.
    Uses quality-controlled four-second alignment; no file writes or network access.
    Do not use to claim significance, propagation direction, or solar origin.
    """
    return {**analyze_interval(interval_id), "limitations": LIMITATIONS}


@mcp.tool()
def compare_psp_wave_intervals(first_interval_id: Interval = "interval-a", second_interval_id: Interval = "interval-b") -> dict:
    """Compare five-minute/two-minute energy and signed cross helicity in two public PSP intervals.

    Example: first_interval_id='interval-a', second_interval_id='interval-b'.
    IDs must differ; use list_psp_intervals for their half-open UTC coverage.
    Returns both sets of nT^2 energies, dimensionless fractions and sigma_c,
    plus the second/first total energy ratio and second-minus-first fraction differences.
    Inputs are bundled offline measurements, not live data or arbitrary files.
    A higher five-minute fraction is a band-power comparison, not a significance test.
    """
    return compare_intervals(first_interval_id, second_interval_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")

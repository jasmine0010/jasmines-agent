---
name: psp-waves
description: Use to compare five-minute/two-minute magnetic wave energy and signed cross helicity in the two bundled public PSP intervals from 2024-12-24, or to ask what intervals are available.
---

# PSP wave diagnostics

Call list_psp_intervals for coverage, then analyze_psp_waves for one interval or
compare_psp_wave_intervals for the pair. Use exact interval IDs. Arbitrary dates
and arbitrary local files are not supported; explain that limitation if requested.

Report UTC half-open coverage and units. RTN means radial, tangential, normal.
Magnetic energy is the integral of the one-sided vector TRACE PSD, in nT^2.
It is not the spectrum of field magnitude and is not a physical energy density
in J/m^3. Both fractions use 1–30 mHz total energy as their denominator.
Five-minute means 2.5–4.5 mHz; two-minute means 6–12 mHz. Convert a fraction to
percent by multiplying by 100; compare differences as percentage points.

Use validated QTN electron density as a proton-density proxy, neglect alpha
particles, and form b=B/sqrt(mu0*rho) before detrending, in km/s. The server
rejects specified SPAN quality problem bits, accepts QTN flags 1/2/4, and never
extrapolates or interpolates across a gap longer than 60 seconds.

Preserve z_plus=deltaV+deltab and z_minus=deltaV-deltab. Signed band cross helicity
is (E_plus-E_minus)/(E_plus+E_minus). Never flip its sign with field polarity or
infer a propagation direction without further context. Near +1 means dominance
of z_plus under this convention; near -1 means dominance of z_minus.

The interval-b peak is a three-bin-smoothed fP maximum inside the five-minute
band. The frequency resolution is about 0.222 mHz, so report roughly 281 s or
4.7 minutes, not subsecond precision. Interval-a has no requested peak estimate.

Use a short phone-friendly explanation. More band power does not by itself
establish statistical significance or solar-source attribution. Acknowledge
the density proxy, SPAN field-of-view bias, and method dependence when relevant.
These are public measured inputs, not synthetic waves and not a certified
wave-free control. The server is read-only and needs no API token.

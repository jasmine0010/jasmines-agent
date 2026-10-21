# Public PSP measurement subset

Times are UTC Unix seconds, stored as float64; the vectors use radial,
tangential, normal (RTN) component order. `manifest.json` defines half-open
analysis intervals. Each input includes one minute of measurement padding on
both ends for interpolation. Different instruments have different timestamps.
The NPZ arrays contain measured values, including original fill values and flags.

- `mag_time_unix_s`, `B_RTN_nT`: FIELDS RTN magnetic field in nT, about 4.58 Hz.
- `velocity_time_unix_s`, `V_RTN_kms`, `velocity_quality_flag`: SPAN-ion
  first-order proton moments, RTN velocity in the Sun frame in km/s, about
  1.75-second cadence. These are partial moments, not fitted full distributions.
  No spacecraft-velocity correction is requested for this benchmark.
- `density_time_unix_s`, `electron_density_cm3`, `density_quality_flag`:
  FIELDS simplified QTN electron density in cm^-3, with variable cadence.
  The flag meanings are 0=no detection; 1,2,4=validated density; 3=upper limit;
  255=fill. Flags are not a binary good/bad variable.

Velocity quality bits describe both problems and operating modes. The task
uses records without fill flag 65535 or any of problem bits 0, 2, 3, 8, 10, or 11
set (numbered from zero). These denote overflow, alternate energy tables,
spoiler tests, over-deflection, bad energy tables, and MCP tests. The remaining
bits describe accepted operating modes. In these inputs, 4336 records the attenuator,
archive rate, sweep/mass-table modes, and survey availability; a nonzero word
alone is not a reason to discard a record. This benchmark uses the supplied
moments as an observational proxy; it does not correct field-of-view bias.
Magnetic and QTN fill values are -1e31; velocity fill values are NaN. Remove
nonfinite measurements, and use positive validated densities. No extrapolation
or interpolation across gaps longer than 60 seconds is supported. Short gaps
and differing cadences can be handled using an appropriate alignment method.

Public NASA CDAWeb HAPI datasets, accessed 2026-10-20:

- [PSP_FLD_L2_MAG_RTN_4_SA_PER_CYC](https://cdaweb.gsfc.nasa.gov/hapi/info?id=PSP_FLD_L2_MAG_RTN_4_SA_PER_CYC)
- [PSP_SWP_SPI_SF00_L3_MOM](https://cdaweb.gsfc.nasa.gov/hapi/info?id=PSP_SWP_SPI_SF00_L3_MOM)
- [PSP_FLD_L3_SQTN_RFS_V1V2](https://cdaweb.gsfc.nasa.gov/hapi/info?id=PSP_FLD_L3_SQTN_RFS_V1V2)

See the [SPAN-I release notes](https://sweap.cfa.harvard.edu/spi_data_release_notes.pdf)
for velocity quality-bit meanings and the [CDAWeb QTN notes](https://cdaweb.gsfc.nasa.gov/misc/NotesP.html#PSP_FLD_L3_SQTN_RFS_V1V2)
for validated density flags. FIELDS data are publicly available under the
[FIELDS rules of the road](https://fields.ssl.berkeley.edu/rules/).

# PSP wave diagnostics plugin

Three read-only MCP tools wrap Jasmine's Week 1 Parker Solar Probe analysis:

- `list_psp_intervals()` lists available IDs and UTC coverage.
- `analyze_psp_waves(interval_id)` computes magnetic band energy and signed cross helicity.
- `compare_psp_wave_intervals(first_interval_id, second_interval_id)` compares the pair.

Example question: **Which interval has a larger five-minute energy fraction,
and how do their two-minute fractions and signed cross helicities compare?**

The plugin includes two small public measurement subsets. It works offline,
needs no API key, reads only its bundled data, and writes no files. It is not a
live archive query and cannot analyze arbitrary dates or arbitrary local files.
Results are compact JSON, suitable for an agent answering through Telegram.

## Inputs and conventions

- `interval-a`: 2024-12-24 08:00–09:15 UTC.
- `interval-b`: 2024-12-24 10:45–12:00 UTC.

Intervals are half-open. Instrument timestamps differ; one minute of padding is
used for interpolation only. Magnetic vectors and proton velocities use RTN
(radial, tangential, normal) components. Inputs come from NASA CDAWeb FIELDS
magnetometer/QTN and SWEAP SPAN-ion products; see [data/README.md](data/README.md)
and [data/source_snapshot.json](data/source_snapshot.json) for source metadata.
Bundled file SHA-256 hashes are checked before each analysis; NPZ pickle loading
is disabled. No Week 1 grading answers or saved measurement outputs are used at runtime.

The implementation adapts
`week-1/submissions/jasmine0010/psp-wave-energy-diagnostics/solution/solve.py`
from Jasmine's local class checkout, distributed under the class repository's
MIT license. Only the calculation and public input subset are packaged here;
the plugin is independent of that repository at runtime.

## Method

1. Average valid magnetic vectors into 4-second bins covering the full interval.
2. Interpolate valid proton velocity and positive QTN density to bin centers.
   Reject SPAN fill flag 65535 and problem bits 0/2/3/8/10/11. QTN flags 1/2/4
   are valid; flag 3 is an upper limit. No extrapolation or gaps over 60 seconds.
3. Use electron density as a proton-density proxy, neglect alpha particles, and
   convert the magnetic vector to km/s using time-dependent mass density **before** detrending.
4. Apply linear detrending and a full-window Hann one-sided trace periodogram.
   Integrate PSD over linear frequency by summing PSD times frequency spacing.
5. Report total magnetic energy in **nT²** over 1–30 mHz. Five-minute (2.5–4.5 mHz)
   and two-minute (6–12 mHz) fractions both use that total as denominator.
6. Preserve `z_plus=deltaV+deltab`, `z_minus=deltaV-deltab`, and
   `sigma_c=(E_plus-E_minus)/(E_plus+E_minus)` within each band. No polarity flip.

The interval-b peak is the maximum of three-bin-smoothed `fP(f)` within the
five-minute band. Frequency spacing is about 0.222 mHz; a reported period such
as 281.25 s is a frequency-bin estimate, not subsecond physical precision.
No interval-a peak is reported. Magnetic energy in nT² is a mean-square
fluctuation measure, not a physical energy density in J/m³.

SPAN partial moments can retain field-of-view bias, and spectral estimates
depend on the estimator and taper. The plugin does not establish statistical
significance, solar-source attribution, or an outward/inward interpretation of
cross-helicity sign. Interval-a is a comparison, not a certified wave-free control.

## Configure and run

Install uv. The inline dependency block selects Python 3.11–3.13, the official
MCP Python SDK 2.3.0, NumPy 2.1.3 and SciPy 1.15.3. No secrets are required.
Set the nonsecret `PSP_PYTHON` variable in the host's environment (or the harness
`.env`) to `3.13`, or to an existing Python 3.11–3.13 executable's absolute path.
The plugin passes it to uv as `UV_PYTHON`, so the research server can use a
different interpreter from the harness. This avoids replacing a harness's
existing environment when the scientific dependencies need an older Python.
On Jasmine's Windows machine the tested value is
`C:/Users/Jasmi/anaconda3/python.exe` (Python 3.13.5).

For a direct protocol-server launch using an installed compatible interpreter:

```sh
uv run --python 3.13 --script plugins/jasmine0010-psp-waves/server.py
```

This starts a stdio protocol server, not a human chat prompt. A host must connect
and call its tools. stdout is exclusively MCP protocol output.

For Claude Code:

```sh
claude plugin validate ./plugins/jasmine0010-psp-waves
claude --plugin-dir ./plugins/jasmine0010-psp-waves
```

Check `/mcp`, then ask the example research question above. For Codex, configure:

```toml
[mcp_servers.psp_waves]
command = "uv"
args = ["run", "--script", "C:/absolute/path/to/jasmine0010-psp-waves/server.py"]
startup_timeout_sec = 60
required = true

[mcp_servers.psp_waves.env]
UV_PYTHON = "3.13"
```

Replace the plugin path with its absolute path, and `3.13` with your existing
compatible interpreter's absolute path if uv cannot find it. Start a fresh session and
approve its research-tool calls. No key or token should be passed to this server.
The harness now loads this plugin in terminal, web chat, and Telegram mode.
The owner confirmed the end-to-end phone research answer on October 26, 2026. The owner explicitly allowed
these three read-only tools in the harness's `settings.json`, so they run without
repeated approval. In manual mode shell commands (including skill-file reads)
and other model-requested tools still ask. The owner enabled automatic Telegram
execution locally, which runs those actions without confirmation too.

## Checks

From this plugin directory:

```sh
uv run --python 3.13 --with mcp==2.3.0 --with numpy==2.1.3 --with scipy==1.15.3 python -m unittest discover -s tests -v
```

Checks compare the real data with the original Week 1 computation, independently
verify PSD normalization using a direct Hann-windowed FFT, test cross-helicity
sign with synthetic Alfvénic waves, test scaling invariance, flags, density units,
gap rejection and invalid IDs, and call the calculation through the MCP protocol.
On October 21, 2026, all eight checks passed on Windows with Python 3.13.5,
NumPy 2.1.3, SciPy 1.15.3 and MCP 2.3.0. A separate stdio client discovered all
three tools and computed the comparison. Codex launched the same server, called
list_psp_intervals and compare_psp_wave_intervals, and answered the example
research question using the returned measurements. The result matches the
original Week 1 calculation. The owner accepted agreement with the Week 1 value
ranges as the scientific-review criterion; all 11 measurements were checked and
fall within those ranges. The check is saved in the harness's local
`validation/week-3-scientific-review.json`.
Claude Code is not installed, so its plugin validator has not been run.

For the real stdio smoke test from the harness directory:

```sh
uv run --env-file .env --script plugins/jasmine0010-psp-waves/tests/smoke_stdio.py
```

Local environment note: uv's automatic Python download failed when creating a
minor-version link, and a newer Python 3.14 numerical stack was blocked by
Windows Application Control. The tested configuration selects the existing
Python 3.13 interpreter through `PSP_PYTHON`; no security settings were changed.

References: [SciPy periodogram](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.periodogram.html),
[FIELDS data rules and acknowledgments](https://fields.ssl.berkeley.edu/rules/),
[MCP SDK](https://py.sdk.modelcontextprotocol.io/),
[Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

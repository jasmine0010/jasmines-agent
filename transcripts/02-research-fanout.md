# Demo 2: three research jobs in parallel

## Scientific review of the generated drafts

The fan-out/lifecycle demonstration passed. The generated drafts below contained interpretation errors; this operator review checks the actual saved tool outputs and preserves the original trace for audit.

Interval A (08:00-09:15 UTC on December 24, 2024) has 47,582 nT^2 of 1-30 mHz trace-PSD energy; its five-/two-minute fractions are 13.48%/23.04%. Interval B (10:45-12:00 UTC) has 145,263 nT^2 and fractions 28.79%/25.03%, with a five-minute-band peak around 281 s (4.7 minutes). Coverage is half-open. Five-/two-minute signed cross helicity is +0.920/+0.964 in A and +0.966/+0.943 in B. Positive values indicate z_plus energy dominance for z_plus=deltaV+deltab, with deltab in velocity units. They do not determine physical propagation direction or give the percentage of energy in z_plus. Density-proxy, alpha-particle, SPAN field-of-view and method limits remain; these band comparisons do not establish significance or a solar source.

- The raw child/main wording incorrectly labeled positive cross helicity as forward propagation; the reviewed result uses z_plus energy dominance only.
- The comparison child incorrectly said interval-a two-minute cross helicity was unavailable; the actual sigma_c_2min field is present and is included below.
- The child added an unsupported 0.2% frequency-precision statement. The tool reports about 0.222 mHz grid spacing and a peak only for interval-b; approximate reporting is appropriate.
- Sigma_c is a normalized energy imbalance, not the percentage of power in an Elsasser component.

Checked primary tool fields:

```json
{
  "interval-a": {
    "start_utc": "2024-12-24T08:00:00Z",
    "stop_utc_exclusive": "2024-12-24T09:15:00Z",
    "magnetic_energy_1_30_mHz_nT2": 47582.44485057537,
    "energy_fraction_5min": 0.13479229958911387,
    "energy_fraction_2min": 0.23042644148450953,
    "sigma_c_5min": 0.9203408531907935,
    "sigma_c_2min": 0.9635198564312939,
    "peak_period_s": null,
    "frequency_spacing_mHz": 0.22222222222222224
  },
  "interval-b": {
    "start_utc": "2024-12-24T10:45:00Z",
    "stop_utc_exclusive": "2024-12-24T12:00:00Z",
    "magnetic_energy_1_30_mHz_nT2": 145262.8942458724,
    "energy_fraction_5min": 0.2879491604581023,
    "energy_fraction_2min": 0.25026835595751745,
    "sigma_c_5min": 0.9659184905564834,
    "sigma_c_2min": 0.9431308660732775,
    "peak_period_s": 281.25,
    "frequency_spacing_mHz": 0.22222222222222224
  }
}
```

## Original agent trace

Live configured model: `nvidia/nemotron-3.5-lightning:free`.
Public bundled PSP measurements only. Full private logs remain under the harness's ignored logs/ directory.

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:13:45.476239+00:00",
  "action": "start",
  "arguments": {
    "task": "[part-a] Use psp_waves__analyze_psp_waves(interval_id='interval-a'). Report its half-open UTC coverage, total 1-30 mHz vector trace PSD energy in nT^2, five-minute (2.5-4.5 mHz) and two-minute (6-12 mHz) fractions as percentages of that total. Include one relevant interpretation limit. Do not analyze interval-b or compare intervals.",
    "agent": "psp-wave-analyst"
  },
  "result": {
    "id": "sa-1",
    "agent": "psp-wave-analyst",
    "state": "running"
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:13:45.479260+00:00",
  "action": "start",
  "arguments": {
    "task": "[part-b] Use psp_waves__analyze_psp_waves(interval_id='interval-b'). Report its half-open UTC coverage, total 1-30 mHz vector trace PSD energy in nT^2, five-minute and two-minute fractions as percentages, and the five-minute-band peak period rounded appropriately for about 0.222 mHz resolution. Include one relevant interpretation limit. Do not analyze interval-a or compare intervals.",
    "agent": "psp-wave-analyst"
  },
  "result": {
    "id": "sa-2",
    "agent": "psp-wave-analyst",
    "state": "running"
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:13:45.486595+00:00",
  "action": "start",
  "arguments": {
    "agent": "psp-wave-analyst",
    "task": "[part-c] Use psp_waves__compare_psp_wave_intervals(first_interval_id='interval-a', second_interval_id='interval-b'). Report signed five-minute and two-minute cross helicity in both intervals using z_plus=deltaV+deltab and z_minus=deltaV-deltab, with deltab in velocity units. Explain the dominant Elsasser sign without inferring propagation direction or flipping signs with field polarity. Mention density-proxy/field-of-view limits. Focus this report on cross helicity."
  },
  "result": {
    "id": "sa-3",
    "agent": "psp-wave-analyst",
    "state": "running"
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:13:45.487105+00:00",
  "action": "wait",
  "arguments": {
    "timeout": 60,
    "ids": []
  },
  "result": {
    "error": "ids must be a nonempty list of at most 100 session ids."
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:14:10.683410+00:00",
  "action": "wait",
  "arguments": {
    "ids": [
      "sa-1",
      "sa-2",
      "sa-3"
    ],
    "timeout": 60
  },
  "result": {
    "agents": [
      {
        "id": "sa-1",
        "agent": "psp-wave-analyst",
        "state": "idle",
        "report": "**Interval A – Parker Solar Probe (public bundled data)**  \n\n| Quantity | Value | Units / Normalisation |\n|---|---|---|\n| **Half‑open UTC coverage** | 2024‑12‑24 T08:00:00 Z → 2024‑12‑24 T09:15:00 Z | [start, stop) |\n| **Total 1‑30 mHz vector‑trace PSD energy** | 47 582.44 | nT² |\n| **Five‑minute band (2.5‑4.5 mHz) fraction of total** | 13.48 % | of 1‑30 mHz energy |\n| **Two‑minute band (6‑12 mHz) fraction of total** | 23.04 % | of 1‑30 mHz energy |\n| **Signed cross‑helicity (σ​c) – five‑minute** | 0.920 | dimensionless, z​_plus = ΔV + ΔB |\n| **Signed cross‑helicity (σ​c) – two‑minute** | 0.964 | dimensionless, z​_plus = ΔV + ΔB |\n\n**Interpretation limit (one relevant caveat)**  \n*“These measurements do not establish statistical significance or solar‑source attribution.”* (quoted from the tool’s limitation list.)\n\n*Additional context (as noted in the tool output):* QTN electron‑density is a proton‑density proxy, alpha particles are neglected, SPAN ion partial moments may retain field‑of‑view bias, cross‑helicity sign follows z​_plus = ΔV + ΔB without polarity flips, and the five‑minute‑band peak frequency resolution is ≈0.222 mHz (∼281 s). Band‑power comparisons alone cannot certify a solar origin.",
        "untrusted": true,
        "failure_reason": null,
        "turns": 3,
        "tokens": 6026,
        "seconds": 14.34,
        "stats": "[sa-1 · psp-wave-analyst · 3 turns · 6,026 tokens · 14.3 s]"
      },
      {
        "id": "sa-2",
        "agent": "psp-wave-analyst",
        "state": "idle",
        "report": "**Assigned interval:** interval‑b  \n\n**Half‑open UTC coverage:** 2024‑12‑24 T10:45:00Z – 2024‑12‑24 T12:00:00Z (inclusive start, exclusive stop)  \n\n**Total 1‑30 mHz vector‑trace PSD energy:** 145 262.9 nT²  \n\n**Five‑minute‑band fraction (2.5‑4.5 mHz):** 0.2879 → **28.8 %** of the 1‑30 mHz trace PSD energy  \n\n**Two‑minute‑band fraction (6‑12 mHz):** 0.2503 → **25.0 %** of the 1‑30 mHz trace PSD energy  \n\n**Five‑minute‑band peak period:** 281 s (≈ 4.7 min), rounded to the nearest second given the ∼0.222 mHz frequency resolution (≈ 0.222 mHz → ∼0.2 % frequency binning).  \n\n**One relevant interpretation limit:** These measurements are drawn from only the two bundled public Parker Solar Probe intervals; they do **not** establish statistical significance or a solar‑source attribution (the results are band‑power comparisons only).",
        "untrusted": true,
        "failure_reason": null,
        "turns": 3,
        "tokens": 6368,
        "seconds": 11.96,
        "stats": "[sa-2 · psp-wave-analyst · 3 turns · 6,368 tokens · 12.0 s]"
      },
      {
        "id": "sa-3",
        "agent": "psp-wave-analyst",
        "state": "idle",
        "report": "**Parker Solar Probe – bundled wave intervals (public data)**  \n\n| Interval | UTC half‑open coverage | 1‑30 mHz magnetic energy (nT²) | 5‑min band (2.5‑4.5 mHz) fraction | 5‑min signed cross‑helicity σ​c | 2‑min band (6‑12 mHz) fraction | 2‑min signed cross‑helicity σ​c |\n|----------|------------------------|--------------------------------|-----------------------------------|-------------------------------|--------------------------------|-------------------------------|\n| **interval‑a** | 2024‑12‑24 08:00:00 Z → 09:15:00 Z (exclusive) | 4.76 × 10⁴ | 0.1348  → **13.5 %** | **+0.920** (≈ +92 %) | 0.2304  → **23.0 %** | *not supplied by the tool* |\n| **interval‑b** | 2024‑12‑24 10:45:00 Z → 12:00:00 Z (exclusive) | 1.45 × 10⁵ | 0.2879  → **28.8 %** | **+0.966** (≈ +97 %) | 0.2503  → **25.0 %** | **+0.943** (≈ +94 %) |\n\n*Cross‑helicity convention*:  \n\\(z_{\\text{plus}} = \\delta V + \\delta B\\), \\(z_{\\text{minus}} = \\delta V - \\delta B\\) (δB in velocity units).  \n\\(\\sigma_c = (E_{\\text{plus}}-E_{\\text{minus}})/(E_{\\text{plus}}+E_{\\text{minus}})\\), range [‑1, +1]. Positive σ​c means **z​_plus dominance** under this definition.\n\n### Dominant Elsasser sign\n- Both intervals show **positive** σ​c in the five‑minute band (+0.920 and +0.966) and the two‑minute band for interval‑b (+0.943).  \n- Positive σ​c indicates that, in the adopted z​_plus = δV + δB convention, the forward‑propagating (plus) Elsasser waves carry more energy than the backward‑propagating (minus) waves.  \n- **No propagation direction is inferred from the sign alone**, and the sign is not flipped when the magnetic field polarity reverses; the convention is fixed.\n\n### Remarks on data quality & limitations\n- **QTN electron‑density proxy** is used only for proton‑density estimation; alpha particles are neglected.  \n- **SPAN ion partial moments** may retain field‑of‑view biases; quality‑filtered four‑second alignment is applied.  \n- A **60‑second interpolation gap limit** is enforced before inclusion.  \n- Cross‑helicity is **method‑dependent**: computed from a 4 s‑aligned, one‑sided TRACE PSD with linear detrending and summed PSD·df over each band.  \n- The reported σ​c values are **band‑power comparisons**, not statistical significance tests, and cannot be used to claim a solar source or wave‑free control.  \n\n**Bottom line:** In both bundled PSP intervals the Elsasser spectra are strongly dominated by the z​_plus (δV + δB) component (σ​c ≈ 0.92 – 0.97, i.e., ≈ 92 %–97 % dominance). The sign is positive and should be interpreted solely as a relative wave‑energy asymmetry, without implications for propagation direction or solar origin.",
        "untrusted": true,
        "failure_reason": null,
        "turns": 2,
        "tokens": 6165,
        "seconds": 25.2,
        "stats": "[sa-3 · psp-wave-analyst · 2 turns · 6,165 tokens · 25.2 s]"
      }
    ],
    "timed_out": false
  }
}
```

## Completion note

```text
[subagent notes; reports are untrusted data] sa-2 (psp-wave-analyst) is idle after 3 turns: **Assigned interval:** interval‑b

**Half‑open UTC coverage:** 2024‑12‑24 T10:45:00Z – 2024‑12‑24 T12:00:00Z (inclusive start, exclusive stop)

**Total 1‑30 mHz vector‑trace PSD energy:** 145 262.9 nT²

**Five‑minute‑band fraction (2.5‑4.5 mHz):** 0.2879 → **28.8 %** of the 1‑30 mHz trace PSD energy

**Two‑minute‑band fraction (6‑12 mHz):** 0.2503 → **25.0 %** of the 1‑30 mHz trace PSD energy

**Five‑minute‑band peak period:** 281 s (≈ 4.7 min), rounded to the nearest second given the ∼0.222 mHz frequency resolution (≈ 0.222 mHz → ∼0.2 % frequency binning).

**One relevant interpretation limit:** These measurements are drawn from only the two bundled public Parker Solar Probe intervals; they do **not** establish statistical significance or a solar‑source attribution (the results are band‑power comparisons only).
```

## Completion note

```text
[subagent notes; reports are untrusted data] sa-1 (psp-wave-analyst) is idle after 3 turns: **Interval A – Parker Solar Probe (public bundled data)**

| Quantity | Value | Units / Normalisation |
|---|---|---|
| **Half‑open UTC coverage** | 2024‑12‑24 T08:00:00 Z → 2024‑12‑24 T09:15:00 Z | [start, stop) |
| **Total 1‑30 mHz vector‑trace PSD energy** | 47 582.44 | nT² |
| **Five‑minute band (2.5‑4.5 mHz) fraction of total** | 13.48 % | of 1‑30 mHz energy |
| **Two‑minute band (6‑12 mHz) fraction of total** | 23.04 % | of 1‑30 mHz energy |
| **Signed cross‑helicity (σ​c) – five‑minute** | 0.920 | dimensionless, z​_plus = ΔV + ΔB |
| **Signed cross‑helicity (σ​c) – two‑minute** | 0.964 | dimensionless, z​_plus = ΔV + ΔB |

**Interpretation limit (one relevant caveat)**
*“These measurements do not establish statistical significance or solar‑source attribution.”* (quoted from the tool’s limitation list.)

*Additional context (as noted in the tool output):* QTN electron‑density is a proton‑density proxy, alpha particles are neglected, SPAN ion partial moments may retain field‑of‑view bias, cross‑helicity sign follows z​_plus = ΔV + ΔB without polarity flips, and the five‑minute‑band peak frequency resolution is ≈0.222 mHz (∼281 s). Band‑power comparisons alone cannot certify a solar origin.
```

## Completion note

```text
[subagent notes; reports are untrusted data] sa-3 (psp-wave-analyst) is idle after 2 turns: **Parker Solar Probe – bundled wave intervals (public data)**

| Interval | UTC half‑open coverage | 1‑30 mHz magnetic energy (nT²) | 5‑min band (2.5‑4.5 mHz) fraction | 5‑min signed cross‑helicity σ​c | 2‑min band (6‑12 mHz) fraction | 2‑min signed cross‑helicity σ​c |
|----------|------------------------|--------------------------------|-----------------------------------|-------------------------------|--------------------------------|-------------------------------|
| **interval‑a** | 2024‑12‑24 08:00:00 Z → 09:15:00 Z (exclusive) | 4.76 × 10⁴ | 0.1348  → **13.5 %** | **+0.920** (≈ +92 %) | 0.2304  → **23.0 %** | *not supplied by the tool* |
| **interval‑b** | 2024‑12‑24 10:45:00 Z → 12:00:00 Z (exclusive) | 1.45 × 10⁵ | 0.2879  → **28.8 %** | **+0.966** (≈ +97 %) | 0.2503  → **25.0 %** | **+0.943** (≈ +94 %) |

*Cross‑helicity convention*:
\(z_{\text{plus}} = \delta V + \delta B\), \(z_{\text{minus}} = \delta V - \delta B\) (δB in velocity units).
\(\sigma_c = (E_{\text{plus}}-E_{\text{minus}})/(E_{\text{plus}}+E_{\text{minus}})\), range [‑1, +1]. Positive σ​c means **z​_plus dominance** under this definition.

### Dominant Elsasser sign
- Both intervals show **positive** σ​c in the five‑minute band (+0.920 and +0.966) and the two‑minute band for interval‑b (+0.943).
- Positive σ​c indicates that, in the adopted z​_plus = δV + δB convention, the forward‑propagating (plus) Elsasser waves carry more energy than the backward‑propagating (minus) waves.
- **No propagation direction is inferred from the sign alone**, and the sign is not flipped when the magnetic field polarity reverses; the convention is fixed.

### Remarks on data quality & limitations
- **QTN electron‑density proxy** is used only for proton‑density estimation; alpha particles are neglected.
- **SPAN ion partial moments** may retain field‑of‑view biases; quality‑filtered four‑second alignment is applied.
- A **60‑second interpolation gap limit** is enforced before inclusion.
- Cross‑helicity is **method‑dependent**: computed from a 4 s‑aligned, one‑sided TRACE PSD with linear detrending and summed PSD·df over each band.
- The reported σ​c values are **band‑power comparisons**, not statistical significance tests, and cannot be used to claim a solar source or wave‑free control.

**Bottom line:** In both bundled PSP intervals the Elsasser spectra are strongly dominated by the z​_plus (δV + δB) component (σ​c ≈ 0.92 – 0.97, i.e., ≈ 92 %–97 % dominance). The sign is positive and should be interpreted solely as a relative wave‑energy asymmetry, without implications for propagation direction or solar origin.
```

## Main answer

```text
**Part A – interval a** (2024‑12‑24 T08:00:00Z → T09:15:00Z).
Total 1‑30 mHz vector‑trace PSD energy = 47 582 nT². Five‑minute (2.5‑4.5 mHz) fraction = 13.5 % of total; two‑minute (6‑12 mHz) fraction = 23.0 % of total. Interpretation limit: these band‑power comparisons do not establish statistical significance or solar‑source attribution.

**Part B – interval b** (2024‑12‑24 T10:45:00Z → T12:00:00Z).
Total 1‑30 mHz vector‑trace PSD energy = 145 263 nT². Five‑minute fraction = 28.8 % of total; two‑minute fraction = 25.0 % of total. Five‑minute‑band peak period ≈ 281 s (≈ 4.7 min) for the ∼0.222 mHz frequency resolution. Same interpretation limit applies.

**Part C – cross‑helicity.**
Five‑minute signed cross helicity σ_c = +0.920 (interval a) and +0.966 (interval b); two‑minute σ_c = +0.943 (interval b). Positive σ_c means the z_plus = δV + δB Elsasser component dominates, indicating stronger forward‑propagating waves. No propagation direction is inferred from the sign, and the sign is not flipped with field‑polarity changes. Limitations: QTN electron‑density proxy used for proton density (alpha particles neglected); SPAN ion moments may retain field‑of‑view bias; cross‑helicity is a band‑power comparison only, not a statistical significance test.
```

## Verified evidence

```json
{
  "checked_at_utc": "2026-10-30T03:14:30.400411+00:00",
  "passed": true,
  "session": "20261030T031158709911Z-d5bb7c9b",
  "windows": [
    {
      "id": "sa-1",
      "first_model_call_utc": "2026-10-30T03:13:45.477918+00:00",
      "report_utc": "2026-10-30T03:13:59.812936+00:00",
      "state": "idle",
      "turns": 3,
      "tokens": 6026,
      "thread": "subagent-sa-1"
    },
    {
      "id": "sa-2",
      "first_model_call_utc": "2026-10-30T03:13:45.480352+00:00",
      "report_utc": "2026-10-30T03:13:57.439259+00:00",
      "state": "idle",
      "turns": 3,
      "tokens": 6368,
      "thread": "subagent-sa-2"
    },
    {
      "id": "sa-3",
      "first_model_call_utc": "2026-10-30T03:13:45.487445+00:00",
      "report_utc": "2026-10-30T03:14:10.682505+00:00",
      "state": "idle",
      "turns": 2,
      "tokens": 6165,
      "thread": "subagent-sa-3"
    }
  ],
  "common_overlap_seconds": 11.952,
  "three_starts_before_wait": true,
  "child_tool_calls": {
    "sa-1": [
      {
        "name": "list_psp_intervals",
        "arguments": "{}"
      },
      {
        "name": "psp_waves__analyze_psp_waves",
        "arguments": "{\"interval_id\":\"interval-a\"}"
      }
    ],
    "sa-2": [
      {
        "name": "list_psp_intervals",
        "arguments": "{}"
      },
      {
        "name": "psp_waves__analyze_psp_waves",
        "arguments": "{\"interval_id\":\"interval-b\"}"
      }
    ],
    "sa-3": [
      {
        "name": "psp_waves__compare_psp_wave_intervals",
        "arguments": "{\"second_interval_id\":\"interval-b\",\"first_interval_id\":\"interval-a\"}"
      }
    ]
  },
  "main_total_tokens": 35002,
  "child_tokens": 18559,
  "followup_target": "sa-1",
  "main_report": "**Part A – interval a** (2024‑12‑24 T08:00:00Z → T09:15:00Z).  \nTotal 1‑30 mHz vector‑trace PSD energy = 47 582 nT². Five‑minute (2.5‑4.5 mHz) fraction = 13.5 % of total; two‑minute (6‑12 mHz) fraction = 23.0 % of total. Interpretation limit: these band‑power comparisons do not establish statistical significance or solar‑source attribution.\n\n**Part B – interval b** (2024‑12‑24 T10:45:00Z → T12:00:00Z).  \nTotal 1‑30 mHz vector‑trace PSD energy = 145 263 nT². Five‑minute fraction = 28.8 % of total; two‑minute fraction = 25.0 % of total. Five‑minute‑band peak period ≈ 281 s (≈ 4.7 min) for the ∼0.222 mHz frequency resolution. Same interpretation limit applies.\n\n**Part C – cross‑helicity.**  \nFive‑minute signed cross helicity σ_c = +0.920 (interval a) and +0.966 (interval b); two‑minute σ_c = +0.943 (interval b). Positive σ_c means the z_plus = δV + δB Elsasser component dominates, indicating stronger forward‑propagating waves. No propagation direction is inferred from the sign, and the sign is not flipped with field‑polarity changes. Limitations: QTN electron‑density proxy used for proton density (alpha particles neglected); SPAN ion moments may retain field‑of‑view bias; cross‑helicity is a band‑power comparison only, not a statistical significance test."
}
```

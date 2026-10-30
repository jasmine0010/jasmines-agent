from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostics as d
from mcp import Client
from server import mcp


class PhysicsTests(unittest.TestCase):
    def test_bundled_measurements_match_week1_reference(self):
        reference = {
            "interval-a": (47582.44485057537, 0.13479229958911387, 0.23042644148450953, 0.9203408531907935, 0.9635198564312939, None),
            "interval-b": (145262.8942458724, 0.2879491604581023, 0.25026835595751745, 0.9659184905564834, 0.9431308660732775, 281.25),
        }
        keys = ("magnetic_energy_1_30_mHz_nT2", "energy_fraction_5min", "energy_fraction_2min", "sigma_c_5min", "sigma_c_2min", "peak_period_s")
        for interval_id, expected in reference.items():
            result = d.analyze_interval(interval_id)
            self.assertEqual(result["sample_count"], 1125)
            for key, target in zip(keys, expected):
                if target is None:
                    self.assertIsNone(result[key])
                else:
                    self.assertAlmostEqual(result[key], target, delta=max(1e-10, abs(target) * 1e-10))

    def test_trace_psd_matches_independent_hann_fft_normalization(self):
        rng = np.random.default_rng(42)
        values = rng.normal(size=(1125, 3))
        f, power = d.trace_psd(values)
        time = np.arange(len(values), dtype=float)
        design = np.column_stack((time, np.ones_like(time)))
        detrended = values - design @ np.linalg.lstsq(design, values, rcond=None)[0]
        window = 0.5 - 0.5 * np.cos(2 * np.pi * time / len(time))
        fft = np.fft.rfft(detrended * window[:, None], axis=0)
        expected = (np.abs(fft) ** 2).sum(axis=1) / ((1 / d.DT) * (window ** 2).sum())
        expected[1:] *= 2  # Odd-length input has no Nyquist bin.
        np.testing.assert_allclose(power, expected, rtol=2e-12, atol=2e-12)
        self.assertAlmostEqual(f[1], 1 / (1125 * d.DT))

    def test_elsasser_sign_and_amplitude_invariance(self):
        time = np.arange(1125) * d.DT
        wave = np.sin(2 * np.pi * time / 300) + 0.6 * np.sin(2 * np.pi * time / 120)
        magnetic = np.column_stack((wave, 0.7 * wave, 0.2 * wave))
        for sign in (1, -1):
            result = d.band_diagnostics(magnetic, sign * magnetic, magnetic)
            scaled = d.band_diagnostics(3 * magnetic, sign * 3 * magnetic, 3 * magnetic)
            for band in ("5min", "2min"):
                self.assertAlmostEqual(result[f"sigma_c_{band}"], sign)
                self.assertAlmostEqual(result[f"energy_fraction_{band}"], scaled[f"energy_fraction_{band}"])
            self.assertAlmostEqual(scaled["magnetic_energy_1_30_mHz_nT2"] / result["magnetic_energy_1_30_mHz_nT2"], 9)

    def test_interpolation_rejects_extrapolation_and_long_gaps(self):
        for times, grid in [(np.array([0., 100.]), np.array([50.])), (np.array([0., 4.]), np.array([-1.]))]:
            with self.assertRaisesRegex(ValueError, "extrapolate"):
                d.interpolate(times, np.array([1., 2.]), grid)
        np.testing.assert_array_equal(d.interpolate(np.array([0., 100.]), np.array([1., 2.]), np.array([0., 100.])), [1., 2.])

    def test_interval_validation(self):
        with self.assertRaisesRegex(ValueError, "Unknown interval"):
            d.analyze_interval("../../private")
        with self.assertRaisesRegex(ValueError, "different intervals"):
            d.compare_intervals("interval-a", "interval-a")

    def test_quality_flags_and_density_unit_conversion(self):
        times = np.array([-2., 2., 6., 10., 14., 18.])
        velocity = np.full((6, 3), 100.)
        velocity[2] = 1e9  # A flagged outlier must not contaminate alignment.
        flags = np.full(6, 4336, dtype=int)  # Nonzero valid operating-mode word.
        flags[2] |= 1
        density = np.full(6, 25.)
        density[2] = 1e8
        data = {
            "mag_time_unix_s": times,
            "B_RTN_nT": np.tile([10., 0., 0.], (6, 1)),
            "velocity_time_unix_s": times,
            "V_RTN_kms": velocity,
            "velocity_quality_flag": flags,
            "density_time_unix_s": times,
            "electron_density_cm3": density,
            "density_quality_flag": np.array([1, 2, 3, 4, 1, 2]),
        }
        _, _, aligned_velocity, magnetic_velocity = d.align(data, {"start_utc": "1970-01-01T00:00:00Z", "stop_utc_exclusive": "1970-01-01T00:00:16Z"})
        np.testing.assert_allclose(aligned_velocity, 100.)
        np.testing.assert_allclose(magnetic_velocity[:, 0], 43.624069, rtol=1e-6)
        np.testing.assert_array_equal(magnetic_velocity[:, 1:], 0.)

    def test_comparison_ratio_and_differences_follow_order(self):
        forward = d.compare_intervals()["comparison"]
        reverse = d.compare_intervals("interval-b", "interval-a")["comparison"]
        self.assertAlmostEqual(forward["total_magnetic_energy_ratio_second_over_first"] * reverse["total_magnetic_energy_ratio_second_over_first"], 1)
        self.assertAlmostEqual(forward["five_minute_fraction_difference_second_minus_first"], -reverse["five_minute_fraction_difference_second_minus_first"])


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_list_and_real_calculation_through_mcp(self):
        async with Client(mcp) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual({tool.name for tool in tools}, {"list_psp_intervals", "analyze_psp_waves", "compare_psp_wave_intervals"})
            result = await client.call_tool("compare_psp_wave_intervals", {})
            self.assertFalse(result.is_error)
            self.assertIn("0.287949", str(result.content))
            invalid = await client.call_tool("analyze_psp_waves", {"interval_id": "other"})
            self.assertTrue(invalid.is_error)


if __name__ == "__main__":
    unittest.main()

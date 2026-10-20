from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
from shapely.geometry import box

import pyscapetoad


class LegendValuesTest(unittest.TestCase):
    def test_three_values_match_documented_example(self) -> None:
        self.assertEqual(
            pyscapetoad.automatic_legend_values(22_936, 3),
            [22_936.0, 10_000.0, 1_000.0],
        )

    def test_count_is_limited_to_three(self) -> None:
        with self.assertRaisesRegex(ValueError, "compris entre 1 et 3"):
            pyscapetoad.automatic_legend_values(100, 4)

    def test_manual_values_are_validated_and_sorted(self) -> None:
        self.assertEqual(
            pyscapetoad._validate_manual_legend_values([1_000, 22_936, 10_000]),
            [22_936.0, 10_000.0, 1_000.0],
        )
        with self.assertRaisesRegex(ValueError, "distinctes"):
            pyscapetoad._validate_manual_legend_values([10, 10])


class LegendGeometryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cartogram = gpd.GeoDataFrame(
            {"code": ["a", "b"], "votes": [25.0, 75.0]},
            geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
            crs="EPSG:3857",
        )

    def test_squares_share_origin_and_have_proportional_areas(self) -> None:
        legend, report = pyscapetoad.build_legend_frame(
            self.cartogram,
            "votes",
            np.array([25.0, 75.0]),
            values=[100.0, 25.0, 4.0],
        )
        self.assertEqual(list(legend.columns), ["variable", "value", "geometry"])
        self.assertEqual(legend["variable"].tolist(), ["votes"] * 3)
        np.testing.assert_allclose(legend.geometry.area, [200.0, 50.0, 8.0])
        origins = [(geometry.bounds[0], geometry.bounds[1]) for geometry in legend.geometry]
        self.assertTrue(all(origin == origins[0] for origin in origins))
        self.assertEqual(origins[0][0], self.cartogram.total_bounds[0])
        self.assertGreater(origins[0][1], self.cartogram.total_bounds[3])
        self.assertEqual(report["area_per_unit"], 2.0)
        self.assertEqual(report["values"], [100.0, 25.0, 4.0])

    def test_atomic_bundle_does_not_retain_stale_legend(self) -> None:
        legend, _report = pyscapetoad.build_legend_frame(
            self.cartogram,
            "votes",
            np.array([25.0, 75.0]),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.gpkg"
            pyscapetoad._write_gpkg_bundle_atomic(
                [("cartogram", self.cartogram), ("legend", legend)], output
            )
            self.assertEqual(set(pyogrio.list_layers(output)[:, 0]), {"cartogram", "legend"})
            pyscapetoad._write_gpkg_bundle_atomic([("cartogram", self.cartogram)], output)
            self.assertEqual(set(pyogrio.list_layers(output)[:, 0]), {"cartogram"})


class ParserTest(unittest.TestCase):
    def test_legend_defaults_and_manual_values(self) -> None:
        parser = pyscapetoad._parser()
        defaults = parser.parse_args([])
        self.assertTrue(defaults.legend_enabled)
        self.assertEqual(defaults.legend_count, 3)
        self.assertIsNone(defaults.legend_values)
        self.assertEqual(defaults.grid_export_mode, "lines")

        manual = parser.parse_args(
            ["--legend-values", "1000", "10000", "22936", "--no-legend"]
        )
        self.assertFalse(manual.legend_enabled)
        self.assertEqual(manual.legend_values, [1000.0, 10000.0, 22936.0])


if __name__ == "__main__":
    unittest.main()

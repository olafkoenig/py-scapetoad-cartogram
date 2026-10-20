from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, box

import export_topojson
import pyscapetoad


@unittest.skipUnless(shutil.which("geo2topo"), "geo2topo n'est pas installé")
class TopoJsonExportTest(unittest.TestCase):
    def test_named_objects_minimal_properties_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gpkg = root / "sample.gpkg"
            report_path = root / "sample_report.json"
            output = root / "sample.topojson"
            manifest_path = root / "sample_manifest.json"

            cartogram = gpd.GeoDataFrame(
                {"code": ["001", "002"], "votes": [10.0, 30.0], "unused": [1, 2]},
                geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
                crs="EPSG:3857",
            )
            legend, legend_report = pyscapetoad.build_legend_frame(
                cartogram, "votes", cartogram["votes"].to_numpy(), values=[30, 10, 1]
            )
            grid = gpd.GeoDataFrame(
                {"grid_id": [1], "axis": ["horizontal"], "iteration": [1]},
                geometry=[LineString([(0, 0), (20, 0)])],
                crs=cartogram.crs,
            )
            pyscapetoad._write_gpkg_bundle_atomic(
                [
                    ("cartogram", cartogram),
                    ("legend", legend),
                    ("deformation_grid", grid),
                ],
                gpkg,
            )
            report = {
                "id_field": "code",
                "value_field": "votes",
                "total_target_mass": 40.0,
                "total_cartogram_area": 200.0,
                "legend": legend_report,
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")

            args = argparse.Namespace(
                input=str(gpkg),
                output=str(output),
                manifest=str(manifest_path),
                report=str(report_path),
                id_field=None,
                value_field=None,
                quantization=100_000,
                include_grid=False,
                geo2topo="geo2topo",
            )
            _output, _manifest_path, manifest = export_topojson.export_topojson(args)

            topology = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(topology["objects"]), {"cartogram", "legend"})
            feature = topology["objects"]["cartogram"]["geometries"][0]
            self.assertEqual(feature["id"], "001")
            self.assertEqual(set(feature["properties"]), {"code", "votes"})
            self.assertNotIn("unused", feature["properties"])
            self.assertEqual(manifest["source"]["crs"], "EPSG:3857")
            self.assertEqual(manifest["cartogram"]["area_per_unit"], 5.0)
            self.assertEqual(manifest["legend"]["values"], [30.0, 10.0, 1.0])
            self.assertFalse(manifest["topojson"]["simplified"])
            self.assertEqual(manifest["layout"]["map_bbox"], [0.0, 0.0, 20.0, 10.0])
            self.assertGreater(manifest["layout"]["layout_bbox"][3], 10.0)


if __name__ == "__main__":
    unittest.main()

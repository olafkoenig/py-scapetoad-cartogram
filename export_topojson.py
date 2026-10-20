#!/usr/bin/env python3
"""Export a canonical py-scapetoad GeoPackage as TopoJSON plus a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

import geopandas as gpd
import numpy as np
import pyogrio


SCHEMA_VERSION = 1
DEFAULT_QUANTIZATION = 1_000_000


def _atomic_write_json(data: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.stem}-",
        suffix=path.suffix,
        dir=path.parent,
        delete=False,
    ) as stream:
        staging = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    try:
        staging.replace(path)
    finally:
        if staging.exists():
            staging.unlink()


def _bounds(frame: gpd.GeoDataFrame) -> list[float]:
    bounds = list(map(float, frame.total_bounds))
    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise ValueError("La couche possède une emprise non finie.")
    return bounds


def _union_bounds(*bounds: Sequence[float]) -> list[float]:
    return [
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    ]


def _layer_names(path: Path) -> set[str]:
    return {str(name) for name in pyogrio.list_layers(path)[:, 0]}


def _write_temporary_geojson(frame: gpd.GeoDataFrame, path: Path) -> None:
    # These files are internal converter inputs. Keeping projected coordinates
    # is deliberate; the final manifest carries their CRS and planar semantics.
    path.write_text(frame.to_json(drop_id=False, to_wgs84=False), encoding="utf-8")


def _cartogram_for_web(
    frame: gpd.GeoDataFrame, id_field: str, value_field: str
) -> gpd.GeoDataFrame:
    missing = [field for field in (id_field, value_field) if field not in frame.columns]
    if missing:
        raise ValueError(f"Champs absents de cartogram: {missing}")
    if frame[id_field].isna().any() or frame[id_field].duplicated().any():
        raise ValueError(f"Le champ identifiant {id_field!r} doit être complet et unique.")
    values = np.asarray(frame[value_field], dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Le champ {value_field!r} contient des valeurs non finies.")
    web = frame[[id_field, value_field, frame.geometry.name]].copy()
    web[id_field] = web[id_field].astype(str)
    return web.set_index(id_field, drop=False)


def _legend_for_web(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    missing = [field for field in ("variable", "value") if field not in frame.columns]
    if missing:
        raise ValueError(f"Champs absents de legend: {missing}")
    web = frame[["variable", "value", frame.geometry.name]].copy()
    web.index = [f"legend-{index + 1}" for index in range(len(web))]
    return web


def _grid_for_web(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    fields = [
        field
        for field in ("grid_id", "axis", "index", "iteration")
        if field in frame.columns
    ]
    web = frame[[*fields, frame.geometry.name]].copy()
    if "grid_id" in web.columns:
        web.index = [f"grid-{value}" for value in web["grid_id"]]
    else:
        web.index = [f"grid-{index + 1}" for index in range(len(web))]
    return web


def _object_description(frame: gpd.GeoDataFrame) -> dict[str, object]:
    return {
        "feature_count": int(len(frame)),
        "geometry_types": sorted(map(str, frame.geom_type.unique())),
        "bbox": _bounds(frame),
        "invalid_geometry_count": int((~frame.geometry.is_valid).sum()),
        "empty_geometry_count": int(frame.geometry.is_empty.sum()),
        "properties": [str(column) for column in frame.columns if column != frame.geometry.name],
    }


def export_topojson(args: argparse.Namespace) -> tuple[Path, Path, dict[str, object]]:
    input_path = Path(args.input)
    if input_path.suffix.lower() != ".gpkg":
        raise ValueError("L'entrée canonique doit être un GeoPackage (.gpkg).")
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    report_path = (
        Path(args.report)
        if args.report
        else input_path.with_name(f"{input_path.stem}_report.json")
    )
    if not report_path.exists():
        raise FileNotFoundError(
            f"Rapport JSON introuvable: {report_path}. Utilisez --report pour le préciser."
        )
    with report_path.open(encoding="utf-8") as stream:
        source_report = json.load(stream)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".topojson")
    manifest_path = (
        Path(args.manifest)
        if args.manifest
        else output_path.with_name(f"{output_path.stem}_manifest.json")
    )
    if output_path.suffix.lower() not in {".topojson", ".json"}:
        raise ValueError("La sortie TopoJSON doit se terminer par .topojson ou .json.")
    if output_path.resolve() == manifest_path.resolve():
        raise ValueError("Le TopoJSON et son manifeste doivent avoir des chemins distincts.")
    if args.quantization < 0:
        raise ValueError("quantization doit être positif ou nul.")

    available_layers = _layer_names(input_path)
    required_layers = {"cartogram", "legend"}
    missing_layers = required_layers - available_layers
    if missing_layers:
        raise ValueError(f"Couches canoniques absentes: {sorted(missing_layers)}")
    if args.include_grid and "deformation_grid" not in available_layers:
        raise ValueError("--include-grid demandé mais deformation_grid est absente.")

    cartogram = gpd.read_file(input_path, layer="cartogram")
    legend = gpd.read_file(input_path, layer="legend")
    if cartogram.crs is None or legend.crs is None:
        raise ValueError("Les couches cartogram et legend doivent définir un CRS.")
    if cartogram.crs != legend.crs:
        raise ValueError("Les couches cartogram et legend doivent partager le même CRS.")
    if cartogram.crs.is_geographic:
        raise ValueError("L'export Web canonique attend des coordonnées projetées.")

    id_field = args.id_field or source_report.get("id_field")
    if not id_field and "src_id" in cartogram.columns:
        id_field = "src_id"
    if not id_field:
        raise ValueError("Identifiant introuvable; utilisez --id-field.")
    value_field = args.value_field or source_report.get("value_field")
    if not value_field:
        raise ValueError("Variable quantitative introuvable; utilisez --value-field.")

    objects: list[tuple[str, gpd.GeoDataFrame]] = [
        ("cartogram", _cartogram_for_web(cartogram, str(id_field), str(value_field))),
        ("legend", _legend_for_web(legend)),
    ]
    if args.include_grid:
        grid = gpd.read_file(input_path, layer="deformation_grid")
        if grid.crs != cartogram.crs:
            raise ValueError("deformation_grid doit partager le CRS du cartogramme.")
        objects.append(("deformation_grid", _grid_for_web(grid)))

    executable = shutil.which(args.geo2topo)
    if executable is None:
        raise RuntimeError(
            f"Convertisseur {args.geo2topo!r} introuvable. "
            "Installez le paquet npm topojson-server."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pyscapetoad-topojson-") as directory:
        temporary_dir = Path(directory)
        command = [executable, "--quantization", str(args.quantization)]
        for object_name, frame in objects:
            geojson_path = temporary_dir / f"{object_name}.geojson"
            _write_temporary_geojson(frame, geojson_path)
            command.append(f"{object_name}={geojson_path}")
        temporary_output = temporary_dir / "output.topojson"
        command.extend(["--out", str(temporary_output)])
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                "Échec de geo2topo: " + (completed.stderr.strip() or completed.stdout.strip())
            )
        topology = json.loads(temporary_output.read_text(encoding="utf-8"))
        expected_objects = {name for name, _frame in objects}
        if topology.get("type") != "Topology" or set(topology.get("objects", {})) != expected_objects:
            raise RuntimeError("Le TopoJSON produit ne contient pas les objets attendus.")
        temporary_output.replace(output_path)

    object_manifest = {name: _object_description(frame) for name, frame in objects}
    map_bbox = object_manifest["cartogram"]["bbox"]
    layout_bbox = _union_bounds(
        *[description["bbox"] for description in object_manifest.values()]
    )
    topology_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    manifest: dict[str, object] = {
        "schema": "pyscapetoad-web-manifest",
        "schema_version": SCHEMA_VERSION,
        "source": {
            "geopackage": input_path.name,
            "report": report_path.name,
            "crs": str(cartogram.crs),
            "coordinate_space": "projected-cartesian",
        },
        "topojson": {
            "file": output_path.name,
            "sha256": topology_sha256,
            "size_bytes": output_path.stat().st_size,
            "quantization": int(args.quantization),
            "simplified": False,
            "transform": topology.get("transform"),
            "objects": object_manifest,
        },
        "cartogram": {
            "object": "cartogram",
            "id_field": str(id_field),
            "value_field": str(value_field),
            "total_value": float(source_report["total_target_mass"]),
            "total_area": float(source_report["total_cartogram_area"]),
            "area_per_unit": (
                float(source_report["total_cartogram_area"])
                / float(source_report["total_target_mass"])
            ),
            "bbox": map_bbox,
        },
        "legend": {
            "object": "legend",
            **source_report.get("legend", {}),
            "bbox": object_manifest["legend"]["bbox"],
        },
        "layout": {
            "map_bbox": map_bbox,
            "layout_bbox": layout_bbox,
            "y_axis": "up",
            "recommended_d3_projection": "d3.geoIdentity().reflectY(true)",
        },
    }
    _atomic_write_json(manifest, manifest_path)
    return output_path, manifest_path, manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exporter un GeoPackage py-scapetoad vers TopoJSON + manifeste.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="GeoPackage canonique produit par pyscapetoad.py")
    parser.add_argument("-o", "--output", help="Fichier .topojson; défaut: même nom que l'entrée")
    parser.add_argument("--manifest", help="Manifeste JSON; défaut: <output>_manifest.json")
    parser.add_argument("--report", help="Rapport source; défaut: <input>_report.json")
    parser.add_argument("--id-field", help="Identifiant; défaut: valeur du rapport source")
    parser.add_argument("--value-field", help="Variable; défaut: valeur du rapport source")
    parser.add_argument(
        "--quantization",
        type=int,
        default=DEFAULT_QUANTIZATION,
        help="Résolution de pré-quantification; 0 la désactive",
    )
    parser.add_argument(
        "--include-grid",
        action="store_true",
        help="Inclure deformation_grid comme troisième objet TopoJSON",
    )
    parser.add_argument(
        "--geo2topo",
        default="geo2topo",
        help="Nom ou chemin du convertisseur topojson-server",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output_path, manifest_path, manifest = export_topojson(args)
    except Exception as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1
    print(f"TopoJSON: {output_path}")
    print(f"Manifeste: {manifest_path}")
    print("Objets: " + ", ".join(manifest["topojson"]["objects"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
#
# Python adaptation of ScapeToad's Gastner-Newman diffusion-cartogram core.
# Original ScapeToad project: https://github.com/christiankaiser/ScapeToad
# Original contributors include Christian Kaiser and Jason Davies.
# This Python port is a modified/reimplemented work, not the original Java app.
"""Create contiguous Gastner-Newman diffusion cartograms.

This is a compact Python adaptation of ScapeToad's mathematical core:

* ``CartogramGrid`` -> :class:`DensityGrid` and :func:`compute_density`
* ``CartogramNewman`` -> :class:`DiffusionCartogram`
* ``CartogramFeature`` -> geometry densification and coordinate transforms

GeoPandas replaces JUMP's feature model and Shapely replaces JTS.  The input
attribute is interpreted as an extensive quantity by default (population,
votes, ...); pass ``--attribute-is-density`` when it is already a density.
Only polygonal features contribute to the density raster, but every geometry
type in the input is carried to the output and deformed.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# CONFIGURATION SIMPLE (utilisée lorsque l'option CLI correspondante manque)
# ---------------------------------------------------------------------------
# Exemple: INPUT_FILES = ["data/communes.gpkg::communes"]
INPUT_FILES: list[str] = []
AUXILIARY_FILES: list[str] = []  # couches à déformer sans influencer la densité
OUTPUT_FILE = ""
GRID_OUTPUT_FILE = ""  # vide: même GPKG, ou fichier suffixé _grid
REPORT_OUTPUT_FILE = ""  # vide: <output>_report.json
ID_FIELD = ""          # ex. "bfs_nummer"; vide: identifiant natif du fichier
VALUE_FIELD = ""       # ex. "population" (obligatoire ici ou via --attribute)
WORKING_CRS = ""       # vide: CRS projeté d'entrée, ou UTM estimé si géographique
ATTRIBUTE_IS_DENSITY = False
GRID_SIZE = 128
CARTOGRAM_ITERATIONS = 1
GRID_EXPORT_MODE = "lines"  # "lines" (léger), "cells" (détaillé), "none"
GRID_CROP_TO_INPUT = True   # exclut de l'export la marge de calcul extérieure
THEMATIC_EXTENT_ONLY = True  # False: union des bbox thématique + auxiliaires

import argparse
import json
import logging
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.fft import dctn, idctn
from shapely import segmentize
from shapely.geometry import LineString, Polygon, box
from shapely.ops import transform as transform_geometry


LOG = logging.getLogger("pyscapetoad")
SUPPORTED_SUFFIXES = {".geojson", ".json", ".shp", ".gpkg"}


@dataclass(frozen=True)
class DensityGrid:
    """A cell-centred density raster in a planar coordinate system."""

    values: np.ndarray  # (ny, nx), row 0 is the south/bottom row
    bounds: tuple[float, float, float, float]
    mean_density: float
    cell_width: float
    cell_height: float

    @property
    def nx(self) -> int:
        return int(self.values.shape[1])

    @property
    def ny(self) -> int:
        return int(self.values.shape[0])


def _cartogram_bounds(
    bounds: Sequence[float], nx: int, ny: int, margin: float = 1.5
) -> tuple[float, float, float, float]:
    """Reproduce CartogramGastner.cartogramExtent's padded aspect ratio."""
    minx, miny, maxx, maxy = map(float, bounds)
    width, height = maxx - minx, maxy - miny
    if width <= 0 or height <= 0:
        raise ValueError("L'emprise des géométries doit avoir une surface positive.")
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    if width / nx > height / ny:
        padded_width = margin * width
        padded_height = padded_width * ny / nx
    else:
        padded_height = margin * height
        padded_width = padded_height * nx / ny
    return (
        cx - padded_width / 2.0,
        cy - padded_height / 2.0,
        cx + padded_width / 2.0,
        cy + padded_height / 2.0,
    )


def compute_density(
    frame: gpd.GeoDataFrame,
    attribute: str,
    grid_size: int | tuple[int, int] = 128,
    *,
    attribute_is_density: bool = False,
    margin: float = 1.5,
    density_floor: float = 1e-3,
    extent_bounds: Sequence[float] | None = None,
) -> DensityGrid:
    """Rasterise polygon values onto a regular NumPy density grid.

    Each feature/cell intersection contributes exactly its covered area.  For
    an extensive attribute, a feature first receives density ``value / area``;
    this conserves its total value.  Empty parts of the padded extent receive
    the area-weighted mean density, as in ScapeToad.  ``density_floor`` is a
    fraction of the maximum raster density and prevents division by zero in
    the diffusion velocity ``-grad(rho) / rho``.
    """
    if attribute not in frame.columns:
        raise ValueError(f"Attribut absent: {attribute!r}")
    if frame.empty:
        raise ValueError("La couche d'entrée est vide.")
    if frame.crs is None:
        raise ValueError("Le fichier d'entrée doit définir un CRS.")
    if frame.crs.is_geographic:
        raise ValueError("compute_density requiert un CRS projeté (unités planes).")
    if isinstance(grid_size, int):
        nx = ny = grid_size
    else:
        nx, ny = map(int, grid_size)
    if nx < 8 or ny < 8:
        raise ValueError("Chaque dimension de grille doit être au moins 8.")
    if margin < 1.0:
        raise ValueError("margin doit être supérieur ou égal à 1.")
    if not (0.0 <= density_floor < 1.0):
        raise ValueError("density_floor doit être compris entre 0 (inclus) et 1.")

    numeric = pd.to_numeric(frame[attribute], errors="coerce").to_numpy(dtype=float)
    if not np.all(np.isfinite(numeric)):
        bad = np.flatnonzero(~np.isfinite(numeric))[:5].tolist()
        raise ValueError(f"Valeurs non numériques ou manquantes dans {attribute!r}: lignes {bad}")
    if np.any(numeric < 0):
        raise ValueError("La variable de cartogramme ne peut pas contenir de valeurs négatives.")

    polygonal: list[tuple[object, float, float]] = []
    total_mass = 0.0
    total_area = 0.0
    for geom, value in zip(frame.geometry, numeric, strict=True):
        if geom is None or geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        area = float(geom.area)
        if area <= 0:
            continue
        density = float(value) if attribute_is_density else float(value) / area
        polygonal.append((geom, density, area))
        total_mass += density * area
        total_area += area
    if not polygonal:
        raise ValueError("Aucune géométrie polygonale surfacique n'a été trouvée.")
    if total_mass <= 0:
        raise ValueError(f"Toutes les valeurs de {attribute!r} sont nulles.")

    source_bounds = frame.total_bounds if extent_bounds is None else extent_bounds
    extent = _cartogram_bounds(source_bounds, nx, ny, margin)
    minx, miny, maxx, maxy = extent
    dx, dy = (maxx - minx) / nx, (maxy - miny) / ny
    cell_area = dx * dy
    mean_density = total_mass / total_area
    mass = np.zeros((ny, nx), dtype=np.float64)
    covered = np.zeros_like(mass)

    # Feature-first traversal limits expensive intersections to its bbox cells.
    for feature_number, (geom, density, _area) in enumerate(polygonal, start=1):
        gx0, gy0, gx1, gy1 = geom.bounds
        ix0 = max(0, int(math.floor((gx0 - minx) / dx)))
        ix1 = min(nx - 1, int(math.floor((gx1 - minx) / dx)))
        iy0 = max(0, int(math.floor((gy0 - miny) / dy)))
        iy1 = min(ny - 1, int(math.floor((gy1 - miny) / dy)))
        if ix0 > ix1 or iy0 > iy1:
            continue
        for iy in range(iy0, iy1 + 1):
            y0 = miny + iy * dy
            for ix in range(ix0, ix1 + 1):
                x0 = minx + ix * dx
                intersection_area = geom.intersection(box(x0, y0, x0 + dx, y0 + dy)).area
                if intersection_area > 0:
                    mass[iy, ix] += density * intersection_area
                    covered[iy, ix] += intersection_area
        if feature_number % 100 == 0:
            LOG.info("Rasterisation: %d/%d entités", feature_number, len(polygonal))

    # Typical administrative polygons do not overlap.  If they do, their mass
    # is additive, while the background only fills the still-uncovered share.
    uncovered = np.maximum(0.0, cell_area - np.minimum(covered, cell_area))
    rho = (mass + mean_density * uncovered) / cell_area
    maximum = float(np.max(rho))
    if density_floor:
        rho = np.maximum(rho, maximum * density_floor)
    return DensityGrid(rho, extent, mean_density, dx, dy)


class DiffusionCartogram:
    """Gastner-Newman diffusion and the resulting coordinate transform."""

    def __init__(
        self,
        density: DensityGrid,
        *,
        blur: float = 0.0,
        integration_tolerance: float = 0.01,
        convergence: float = 1e-5,
        max_steps: int = 500,
    ) -> None:
        if blur < 0:
            raise ValueError("blur doit être positif ou nul.")
        self.density = density
        self.blur = float(blur)
        self.integration_tolerance = float(integration_tolerance)
        self.convergence = float(convergence)
        self.max_steps = int(max_steps)
        self.rho_hat = dctn(density.values, type=2, norm="ortho")
        kx = np.pi * np.arange(density.nx, dtype=float) / density.nx
        ky = np.pi * np.arange(density.ny, dtype=float) / density.ny
        self.k_squared = ky[:, None] ** 2 + kx[None, :] ** 2
        gx, gy = np.meshgrid(
            np.arange(density.nx + 1, dtype=float),
            np.arange(density.ny + 1, dtype=float),
        )
        self.original_x = gx
        self.original_y = gy
        self.deformed_x = gx.copy()
        self.deformed_y = gy.copy()

    def density_at_time(self, t: float) -> np.ndarray:
        """Return rho(t) from the spectral solution of the heat equation."""
        damping = np.exp(-self.k_squared * float(t))
        rho = idctn(self.rho_hat * damping, type=2, norm="ortho")
        return np.maximum(rho, np.finfo(float).tiny)

    @staticmethod
    def _node_velocity(rho: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute -grad(rho)/rho at nodes using Newman's four-cell stencil."""
        padded = np.pad(rho, 1, mode="edge")
        ny, nx = rho.shape
        sw = padded[0 : ny + 1, 0 : nx + 1]
        se = padded[0 : ny + 1, 1 : nx + 2]
        nw = padded[1 : ny + 2, 0 : nx + 1]
        ne = padded[1 : ny + 2, 1 : nx + 2]
        denominator = np.maximum(sw + se + nw + ne, np.finfo(float).tiny)
        vx = -2.0 * ((se - sw) + (ne - nw)) / denominator
        vy = -2.0 * ((nw - sw) + (ne - se)) / denominator
        return vx, vy

    @staticmethod
    def _bilinear(field: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        ny, nx = field.shape[0] - 1, field.shape[1] - 1
        xc, yc = np.clip(x, 0.0, nx), np.clip(y, 0.0, ny)
        ix = np.minimum(np.floor(xc).astype(np.intp), nx - 1)
        iy = np.minimum(np.floor(yc).astype(np.intp), ny - 1)
        fx, fy = xc - ix, yc - iy
        return (
            (1.0 - fx) * (1.0 - fy) * field[iy, ix]
            + fx * (1.0 - fy) * field[iy, ix + 1]
            + (1.0 - fx) * fy * field[iy + 1, ix]
            + fx * fy * field[iy + 1, ix + 1]
        )

    def _velocity(self, x: np.ndarray, y: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
        vx, vy = self._node_velocity(self.density_at_time(t))
        return self._bilinear(vx, x, y), self._bilinear(vy, x, y)

    def _rk4(
        self, x: np.ndarray, y: np.ndarray, t: float, h: float
    ) -> tuple[np.ndarray, np.ndarray]:
        k1x, k1y = self._velocity(x, y, t)
        k2x, k2y = self._velocity(x + h * k1x / 2, y + h * k1y / 2, t + h / 2)
        k3x, k3y = self._velocity(x + h * k2x / 2, y + h * k2y / 2, t + h / 2)
        k4x, k4y = self._velocity(x + h * k3x, y + h * k3y, t + h)
        return (
            x + h * (k1x + 2 * k2x + 2 * k3x + k4x) / 6,
            y + h * (k1y + 2 * k2y + 2 * k3y + k4y) / 6,
        )

    def integrate(self) -> None:
        """Advect all grid nodes with adaptive step-doubling RK4."""
        nx, ny = self.density.nx, self.density.ny
        x, y = self.original_x.copy(), self.original_y.copy()
        t = 0.5 * self.blur * self.blur
        h = 1e-3
        accepted = 0
        attempts = 0
        while accepted < self.max_steps:
            attempts += 1
            if attempts > self.max_steps * 20:
                raise RuntimeError("L'intégrateur adaptatif ne parvient pas à accepter un pas.")
            big_x, big_y = self._rk4(x, y, t, h)
            half_x, half_y = self._rk4(x, y, t, h / 2)
            fine_x, fine_y = self._rk4(half_x, half_y, t + h / 2, h / 2)
            error = float(np.max(np.hypot(fine_x - big_x, fine_y - big_y)) / 15.0)
            if not np.isfinite(error):
                raise RuntimeError("La diffusion a produit une valeur non finie.")
            if error > self.integration_tolerance:
                h *= max(0.1, 0.9 * (self.integration_tolerance / error) ** 0.2)
                continue

            corrected_x = fine_x + (fine_x - big_x) / 15.0
            corrected_y = fine_y + (fine_y - big_y) / 15.0
            corrected_x = np.clip(corrected_x, 0.0, nx)
            corrected_y = np.clip(corrected_y, 0.0, ny)
            movement = float(np.max(np.hypot(corrected_x - x, corrected_y - y)))
            x, y = corrected_x, corrected_y
            t += h
            accepted += 1
            if accepted % 20 == 0:
                LOG.info("Diffusion: pas %d, t=%.5g, déplacement max=%.5g", accepted, t, movement)
            if movement < self.convergence:
                break
            ratio = 4.0 if error == 0 else min(4.0, 0.9 * (self.integration_tolerance / error) ** 0.2)
            h *= max(1.05, ratio)
        else:
            LOG.warning("Diffusion arrêtée après max_steps=%d avant convergence stricte.", self.max_steps)
        self.deformed_x, self.deformed_y = x, y
        LOG.info("Diffusion terminée: %d pas acceptés, t=%.5g", accepted, t)

    def transform_xy(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        preserve_outside: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Map planar world coordinates through the deformed grid."""
        minx, miny, _maxx, _maxy = self.density.bounds
        source_x = np.asarray(x, dtype=float)
        source_y = np.asarray(y, dtype=float)
        u = (source_x - minx) / self.density.cell_width
        v = (source_y - miny) / self.density.cell_height
        inside = (u >= 0) & (u <= self.density.nx) & (v >= 0) & (v <= self.density.ny)
        du = self._bilinear(self.deformed_x, u, v)
        dv = self._bilinear(self.deformed_y, u, v)
        transformed_x = minx + du * self.density.cell_width
        transformed_y = miny + dv * self.density.cell_height
        if preserve_outside:
            transformed_x = np.where(inside, transformed_x, source_x)
            transformed_y = np.where(inside, transformed_y, source_y)
        return transformed_x, transformed_y

    def transform_geometry(
        self,
        geom: object,
        max_segment_length: float,
        *,
        preserve_outside: bool = False,
    ) -> object:
        if geom is None or geom.is_empty:
            return geom
        dense = segmentize(geom, max_segment_length=max_segment_length)

        def project(x: object, y: object, z: object | None = None) -> tuple[object, ...]:
            new_x, new_y = self.transform_xy(
                np.asarray(x), np.asarray(y), preserve_outside=preserve_outside
            )
            return (new_x, new_y) if z is None else (new_x, new_y, z)

        return transform_geometry(project, dense)

    def _grid_window(
        self, export_bounds: tuple[float, float, float, float] | None
    ) -> tuple[int, int, int, int]:
        """Return an inclusive/exclusive cell window in the original grid."""
        if export_bounds is None:
            return 0, self.density.nx, 0, self.density.ny
        minx, miny, _maxx, _maxy = self.density.bounds
        bx0, by0, bx1, by1 = export_bounds
        ix0 = max(0, int(math.floor((bx0 - minx) / self.density.cell_width)))
        ix1 = min(self.density.nx, int(math.ceil((bx1 - minx) / self.density.cell_width)))
        iy0 = max(0, int(math.floor((by0 - miny) / self.density.cell_height)))
        iy1 = min(self.density.ny, int(math.ceil((by1 - miny) / self.density.cell_height)))
        if ix0 >= ix1 or iy0 >= iy1:
            raise ValueError("L'emprise d'export ne recoupe pas la grille de diffusion.")
        return ix0, ix1, iy0, iy1

    def grid_frame(
        self,
        crs: object,
        export_bounds: tuple[float, float, float, float] | None = None,
        *,
        world_x: np.ndarray | None = None,
        world_y: np.ndarray | None = None,
    ) -> gpd.GeoDataFrame:
        """Return grid cells using this pass or supplied cumulative nodes."""
        minx, miny, _maxx, _maxy = self.density.bounds
        dx, dy = self.density.cell_width, self.density.cell_height
        wx = minx + self.deformed_x * dx if world_x is None else world_x
        wy = miny + self.deformed_y * dy if world_y is None else world_y
        ix0, ix1, iy0, iy1 = self._grid_window(export_bounds)
        records: list[dict[str, object]] = []
        for iy in range(iy0, iy1):
            for ix in range(ix0, ix1):
                ring = [
                    (wx[iy, ix], wy[iy, ix]),
                    (wx[iy, ix + 1], wy[iy, ix + 1]),
                    (wx[iy + 1, ix + 1], wy[iy + 1, ix + 1]),
                    (wx[iy + 1, ix], wy[iy + 1, ix]),
                    (wx[iy, ix], wy[iy, ix]),
                ]
                records.append(
                    {
                        "cell_id": iy * self.density.nx + ix + 1,
                        "row": iy,
                        "col": ix,
                        "density": float(self.density.values[iy, ix]),
                        "geometry": Polygon(ring),
                    }
                )
        return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)

    def grid_lines_frame(
        self,
        crs: object,
        export_bounds: tuple[float, float, float, float] | None = None,
        *,
        world_x: np.ndarray | None = None,
        world_y: np.ndarray | None = None,
    ) -> gpd.GeoDataFrame:
        """Return grid lines using this pass or supplied cumulative nodes."""
        minx, miny, _maxx, _maxy = self.density.bounds
        dx, dy = self.density.cell_width, self.density.cell_height
        wx = minx + self.deformed_x * dx if world_x is None else world_x
        wy = miny + self.deformed_y * dy if world_y is None else world_y
        ix0, ix1, iy0, iy1 = self._grid_window(export_bounds)
        records: list[dict[str, object]] = []
        grid_id = 0
        for iy in range(iy0, iy1 + 1):
            grid_id += 1
            coordinates = list(zip(wx[iy, ix0 : ix1 + 1], wy[iy, ix0 : ix1 + 1]))
            records.append(
                {"grid_id": grid_id, "axis": "horizontal", "index": iy, "geometry": LineString(coordinates)}
            )
        for ix in range(ix0, ix1 + 1):
            grid_id += 1
            coordinates = list(zip(wx[iy0 : iy1 + 1, ix], wy[iy0 : iy1 + 1, ix]))
            records.append(
                {"grid_id": grid_id, "axis": "vertical", "index": ix, "geometry": LineString(coordinates)}
            )
        return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


def _split_input_spec(spec: str) -> tuple[Path, str | None]:
    path_text, separator, layer = spec.partition("::")
    path = Path(path_text)
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Format non pris en charge pour {path}: {path.suffix}")
    return path, layer if separator else None


def _snake_case(value: str) -> str:
    """Return a filesystem-safe ASCII snake_case label."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", ascii_value)).strip("_").lower()


def default_output_path(
    inputs: Sequence[str], attribute: str, grid_size: int, iterations: int
) -> Path:
    """Build <source>_<variable>_grid_<n>_iter_<n>.gpkg beside the input."""
    source_path, _layer = _split_input_spec(inputs[0])
    source_name = _snake_case(source_path.stem)
    if len(inputs) > 1:
        source_name += "_merged"
    variable_name = _snake_case(attribute)
    filename = f"{source_name}_{variable_name}_grid_{grid_size}_iter_{iterations}.gpkg"
    return source_path.with_name(filename)


def read_inputs(
    specs: Sequence[str], attribute: str, id_field: str | None = None
) -> tuple[gpd.GeoDataFrame, object]:
    """Read and merge inputs, preserving columns plus stable source identifiers."""
    frames: list[gpd.GeoDataFrame] = []
    original_crs: object | None = None
    for spec in specs:
        path, layer = _split_input_spec(spec)
        if not path.exists():
            raise FileNotFoundError(path)
        # Native FIDs become the index where the active GeoPandas engine
        # supports it; src_id below then survives format conversion.
        frame = gpd.read_file(path, layer=layer, fid_as_index=True)
        if frame.crs is None:
            raise ValueError(f"CRS absent dans {path}")
        if attribute not in frame.columns:
            raise ValueError(f"Attribut {attribute!r} absent dans {path}")
        if id_field and id_field not in frame.columns:
            raise ValueError(f"Identifiant {id_field!r} absent dans {path}")
        if id_field:
            if frame[id_field].isna().any():
                raise ValueError(f"L'identifiant {id_field!r} contient des valeurs nulles dans {path}")
            duplicates = frame.loc[frame[id_field].duplicated(), id_field]
            if not duplicates.empty:
                examples = duplicates.head(5).tolist()
                raise ValueError(
                    f"L'identifiant {id_field!r} n'est pas unique dans {path}: {examples}"
                )
        if original_crs is None:
            original_crs = frame.crs
        frame = frame.copy()
        # Keep these temporarily outside the columns so even identically named
        # user fields are never overwritten.
        frame.attrs["_pyscapetoad_source_name"] = str(path)
        frames.append(frame)
    assert original_crs is not None
    existing = {str(column) for frame in frames for column in frame.columns}
    source_column = "src_file"
    id_column = "src_id"
    while source_column in existing:
        source_column = "_" + source_column
    existing.add(source_column)
    while id_column in existing:
        id_column = "_" + id_column
    for frame in frames:
        frame[source_column] = frame.attrs["_pyscapetoad_source_name"]
        frame[id_column] = frame.index.map(str)
    aligned = [frame.to_crs(original_crs) if frame.crs != original_crs else frame for frame in frames]
    merged = gpd.GeoDataFrame(pd.concat(aligned, ignore_index=True, sort=False), crs=original_crs)
    return merged, original_crs


def read_auxiliary_layers(
    specs: Sequence[str], working_crs: object
) -> dict[str, gpd.GeoDataFrame]:
    """Read layers that follow the deformation without affecting density."""
    layers: dict[str, gpd.GeoDataFrame] = {}
    for spec in specs:
        path, selected_layer = _split_input_spec(spec)
        if not path.exists():
            raise FileNotFoundError(path)
        frame = gpd.read_file(path, layer=selected_layer, fid_as_index=True)
        if frame.crs is None:
            raise ValueError(f"CRS absent dans la couche auxiliaire {path}")
        source_id = "src_id"
        while source_id in frame.columns:
            source_id = "_" + source_id
        frame = frame.copy()
        frame[source_id] = frame.index.map(str)
        base_name = selected_layer or path.stem
        layer_name = f"aux_{_snake_case(base_name)}"
        suffix = 2
        unique_name = layer_name
        while unique_name in layers:
            unique_name = f"{layer_name}_{suffix}"
            suffix += 1
        layers[unique_name] = frame.to_crs(working_crs)
    return layers


def combined_total_bounds(
    thematic: gpd.GeoDataFrame,
    auxiliary_layers: dict[str, gpd.GeoDataFrame],
) -> tuple[float, float, float, float]:
    """Return the union bbox of thematic and non-empty auxiliary layers."""
    bounds = [np.asarray(thematic.total_bounds, dtype=float)]
    bounds.extend(
        np.asarray(layer.total_bounds, dtype=float)
        for layer in auxiliary_layers.values()
        if not layer.empty
    )
    finite = [item for item in bounds if np.all(np.isfinite(item))]
    if not finite:
        raise ValueError("Aucune emprise géographique finie n'a été trouvée.")
    stacked = np.vstack(finite)
    return (
        float(np.min(stacked[:, 0])),
        float(np.min(stacked[:, 1])),
        float(np.max(stacked[:, 2])),
        float(np.max(stacked[:, 3])),
    )


def _driver(path: Path) -> str:
    return {
        ".geojson": "GeoJSON",
        ".json": "GeoJSON",
        ".shp": "ESRI Shapefile",
        ".gpkg": "GPKG",
    }.get(path.suffix.lower(), "")


def _write(frame: gpd.GeoDataFrame, path: Path, layer: str) -> None:
    driver = _driver(path)
    if not driver:
        raise ValueError(f"Extension de sortie non prise en charge: {path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, object] = {"driver": driver, "index": False}
    if driver == "GPKG":
        # Pyogrio's default write mode replaces a layer of the same name and
        # preserves the other GeoPackage layers. Do not use mode="a": it would
        # append duplicate features on a rerun. This requires no Fiona import.
        kwargs["layer"] = layer
    frame.to_file(path, **kwargs)


def add_quality_metrics(
    result: gpd.GeoDataFrame,
    original_areas: np.ndarray,
    target_masses: np.ndarray,
    working_crs: object,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Add ScapeToad-compatible SizeError and complementary diagnostics."""
    result = result.copy()
    polygon_mask = result.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).to_numpy()
    final_areas = result.geometry.area.to_numpy(dtype=float)
    masses = np.where(polygon_mask, np.asarray(target_masses, dtype=float), 0.0)
    original = np.where(polygon_mask, np.asarray(original_areas, dtype=float), 0.0)
    final = np.where(polygon_mask, final_areas, 0.0)
    total_mass = float(np.sum(masses))
    total_final_area = float(np.sum(final))
    if total_mass <= 0 or total_final_area <= 0:
        raise ValueError("Impossible de calculer les indicateurs de surface.")

    value_share = masses / total_mass
    area_share = final / total_final_area
    target_area = value_share * total_final_area
    size_error = np.divide(
        100.0 * value_share,
        area_share,
        out=np.zeros_like(value_share),
        where=area_share > 0,
    )
    relative_error = np.divide(
        100.0 * (final - target_area),
        target_area,
        out=np.full_like(target_area, np.nan),
        where=target_area > 0,
    )
    absolute_error = np.abs(relative_error)
    area_ratio = np.divide(
        final,
        target_area,
        out=np.full_like(target_area, np.nan),
        where=target_area > 0,
    )
    status = np.full(len(result), "not_polygon", dtype=object)
    status[polygon_mask & (target_area <= 0)] = "no_target"
    status[assessable := (polygon_mask & (target_area > 0) & np.isfinite(relative_error))] = "on_target"
    status[assessable & (relative_error > 5)] = "too_large"
    status[assessable & (relative_error < -5)] = "too_small"
    quality = np.full(len(result), "not_assessed", dtype=object)
    quality[assessable & (absolute_error <= 5)] = "excellent"
    quality[assessable & (absolute_error > 5) & (absolute_error <= 10)] = "good"
    quality[assessable & (absolute_error > 10) & (absolute_error <= 20)] = "acceptable"
    quality[assessable & (absolute_error > 20) & (absolute_error <= 50)] = "poor"
    quality[assessable & (absolute_error > 50)] = "very_poor"

    # Short names remain usable in an ESRI Shapefile (10-character limit).
    result["cg_a_orig"] = original
    result["cg_a_cart"] = final
    result["cg_a_targ"] = target_area
    result["cg_vshare"] = value_share
    result["cg_ashare"] = area_share
    result["SizeError"] = size_error
    result["cg_ratio"] = area_ratio
    result["cg_relerr"] = relative_error
    result["cg_abserr"] = absolute_error
    result["cg_status"] = status
    result["cg_quality"] = quality

    polygons = polygon_mask & np.isfinite(size_error)
    se = size_error[polygons]
    ae = absolute_error[assessable]
    mass_for_correlation = masses[assessable]
    area_for_correlation = final[assessable]
    correlation: float | None = None
    if (
        len(mass_for_correlation) > 1
        and np.std(mass_for_correlation) > 0
        and np.std(area_for_correlation) > 0
    ):
        correlation = float(np.corrcoef(mass_for_correlation, area_for_correlation)[0, 1])

    def percentile(values: np.ndarray, q: float) -> float | None:
        return float(np.percentile(values, q)) if values.size else None

    report: dict[str, object] = {
        "working_crs": str(working_crs),
        "feature_count": int(len(result)),
        "polygon_count": int(np.sum(polygon_mask)),
        "assessable_polygon_count": int(np.sum(assessable)),
        "zero_target_count": int(np.sum(polygon_mask & (target_area <= 0))),
        "total_target_mass": total_mass,
        "total_original_area": float(np.sum(original)),
        "total_cartogram_area": total_final_area,
        "size_error": {
            "ideal_value": 100.0,
            "mean": float(np.mean(se)) if se.size else None,
            "standard_deviation": float(np.std(se)) if se.size else None,
            "percentile_25": percentile(se, 25),
            "median": percentile(se, 50),
            "percentile_75": percentile(se, 75),
        },
        "relative_area_error_percent": {
            "mean_absolute": float(np.mean(ae)) if ae.size else None,
            "median_absolute": percentile(ae, 50),
            "maximum_absolute": float(np.max(ae)) if ae.size else None,
            "within_5_percent": float(100.0 * np.mean(ae <= 5)) if ae.size else None,
            "within_10_percent": float(100.0 * np.mean(ae <= 10)) if ae.size else None,
            "within_20_percent": float(100.0 * np.mean(ae <= 20)) if ae.size else None,
        },
        "quality_class_counts": {
            label: int(np.sum(quality == label))
            for label in ["excellent", "good", "acceptable", "poor", "very_poor", "not_assessed"]
        },
        "status_counts": {
            label: int(np.sum(status == label))
            for label in ["on_target", "too_small", "too_large", "no_target", "not_polygon"]
        },
        "area_value_pearson_correlation": correlation,
    }
    return result, report


def _write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def build_cartogram(
    args: argparse.Namespace,
) -> tuple[Path, Path | None, Path, dict[str, object]]:
    source, original_crs = read_inputs(args.inputs, args.attribute, args.id_field)
    if args.working_crs:
        working_crs = args.working_crs
    elif source.crs.is_geographic:
        working_crs = source.estimate_utm_crs()
        if working_crs is None:
            raise ValueError("Impossible d'estimer un CRS projeté; utilisez --working-crs.")
        LOG.info("CRS de calcul estimé: %s", working_crs)
    else:
        working_crs = source.crs
    if args.iterations < 1:
        raise ValueError("iterations doit être supérieur ou égal à 1.")
    working = source.to_crs(working_crs)
    auxiliary_layers = read_auxiliary_layers(args.auxiliary_files, working_crs)
    initial_thematic_bounds = tuple(map(float, working.total_bounds))
    initial_auxiliary_bounds = {
        name: tuple(map(float, auxiliary.total_bounds))
        for name, auxiliary in auxiliary_layers.items()
        if not auxiliary.empty
    }
    initial_combined_bounds = combined_total_bounds(working, auxiliary_layers)
    initial_selected_bounds = (
        initial_thematic_bounds
        if args.thematic_extent_only
        else initial_combined_bounds
    )
    original_areas = working.geometry.area.to_numpy(dtype=float)

    # Turn an intensive input into invariant feature masses.  Recomputing
    # density = mass/current_area then has the same semantics at every pass.
    calculation_attribute = args.attribute
    temporary_mass_column: str | None = None
    if args.attribute_is_density:
        temporary_mass_column = "__cartogram_mass"
        while temporary_mass_column in working.columns:
            temporary_mass_column = "_" + temporary_mass_column
        values = pd.to_numeric(working[args.attribute], errors="coerce").to_numpy(dtype=float)
        working[temporary_mass_column] = values * working.geometry.area.to_numpy(dtype=float)
        calculation_attribute = temporary_mass_column
        target_masses = working[temporary_mass_column].to_numpy(dtype=float)
    else:
        target_masses = pd.to_numeric(working[args.attribute], errors="coerce").to_numpy(dtype=float)

    model: DiffusionCartogram | None = None
    density: DensityGrid | None = None
    final_pass_bounds: tuple[float, float, float, float] | None = None
    grid_reference_model: DiffusionCartogram | None = None
    grid_reference_bounds: tuple[float, float, float, float] | None = None
    cumulative_grid_x: np.ndarray | None = None
    cumulative_grid_y: np.ndarray | None = None
    for iteration in range(1, args.iterations + 1):
        LOG.info("Itération de cartogramme %d/%d", iteration, args.iterations)
        final_pass_bounds = (
            tuple(map(float, working.total_bounds))
            if args.thematic_extent_only
            else combined_total_bounds(working, auxiliary_layers)
        )
        density = compute_density(
            working,
            calculation_attribute,
            args.grid_size,
            attribute_is_density=False,
            margin=args.margin,
            density_floor=args.density_floor,
            extent_bounds=final_pass_bounds,
        )
        model = DiffusionCartogram(
            density,
            blur=args.blur,
            integration_tolerance=args.integration_tolerance,
            convergence=args.convergence,
            max_steps=args.max_steps,
        )
        model.integrate()
        if grid_reference_model is None:
            grid_reference_model = model
            grid_reference_bounds = final_pass_bounds
            grid_minx, grid_miny, _grid_maxx, _grid_maxy = density.bounds
            cumulative_grid_x = grid_minx + model.deformed_x * density.cell_width
            cumulative_grid_y = grid_miny + model.deformed_y * density.cell_height
        else:
            assert cumulative_grid_x is not None and cumulative_grid_y is not None
            cumulative_grid_x, cumulative_grid_y = model.transform_xy(
                cumulative_grid_x,
                cumulative_grid_y,
                preserve_outside=True,
            )
        segment_length = args.max_segment_length or min(density.cell_width, density.cell_height) / 2
        if segment_length <= 0:
            raise ValueError("max-segment-length doit être strictement positif.")
        working.geometry = working.geometry.map(
            lambda geom: model.transform_geometry(geom, segment_length)
        )
        for auxiliary in auxiliary_layers.values():
            auxiliary.geometry = auxiliary.geometry.map(
                lambda geom: model.transform_geometry(
                    geom, segment_length, preserve_outside=True
                )
            )

    assert (
        model is not None
        and density is not None
        and grid_reference_model is not None
        and grid_reference_bounds is not None
        and cumulative_grid_x is not None
        and cumulative_grid_y is not None
    )
    result, quality_report = add_quality_metrics(
        working, original_areas, target_masses, working.crs
    )
    if temporary_mass_column:
        result = result.drop(columns=[temporary_mass_column])
    # Compose every iteration on the first regular grid. This exposes the full
    # deformation rather than the nearly-regular residual of the final pass.
    export_bounds = grid_reference_bounds if not args.full_grid_extent else None
    grid: gpd.GeoDataFrame | None
    if args.grid_export_mode == "lines":
        grid = grid_reference_model.grid_lines_frame(
            working.crs,
            export_bounds,
            world_x=cumulative_grid_x,
            world_y=cumulative_grid_y,
        )
    elif args.grid_export_mode == "cells":
        grid = grid_reference_model.grid_frame(
            working.crs,
            export_bounds,
            world_x=cumulative_grid_x,
            world_y=cumulative_grid_y,
        )
    elif args.grid_export_mode == "none":
        grid = None
    else:
        raise ValueError(f"Mode d'export de grille inconnu: {args.grid_export_mode}")
    if grid is not None:
        grid["iteration"] = args.iterations
    if not args.keep_working_crs:
        result = result.to_crs(original_crs)
        if grid is not None:
            grid = grid.to_crs(original_crs)
        auxiliary_layers = {
            name: auxiliary.to_crs(original_crs)
            for name, auxiliary in auxiliary_layers.items()
        }

    output = Path(args.output)
    if grid is None:
        grid_output = None
    elif args.grid_output:
        grid_output = Path(args.grid_output)
    elif output.suffix.lower() == ".gpkg":
        grid_output = output
    else:
        grid_output = output.with_name(f"{output.stem}_grid{output.suffix}")
    report_output = (
        Path(args.report_output)
        if args.report_output
        else output.with_name(f"{output.stem}_report.json")
    )
    quality_report.update(
        {
            "input_files": list(args.inputs),
            "id_field": args.id_field,
            "value_field": args.attribute,
            "attribute_is_density": bool(args.attribute_is_density),
            "grid_size": int(args.grid_size),
            "cartogram_iterations": int(args.iterations),
            "grid_export_mode": args.grid_export_mode,
            "grid_cropped_to_input": not args.full_grid_extent,
            "grid_representation": "cumulative_all_iterations",
            "exported_grid_feature_count": len(grid) if grid is not None else 0,
            "auxiliary_layers": {
                name: {
                    "feature_count": len(auxiliary),
                    "valid_geometry_count": int(auxiliary.is_valid.sum()),
                    "empty_geometry_count": int(auxiliary.is_empty.sum()),
                }
                for name, auxiliary in auxiliary_layers.items()
            },
            "initial_extents": {
                "thematic_bounds": list(initial_thematic_bounds),
                "auxiliary_bounds": {
                    name: list(bounds) for name, bounds in initial_auxiliary_bounds.items()
                },
                "combined_bounds": list(initial_combined_bounds),
                "selected_bounds": list(initial_selected_bounds),
                "diffusion_bounds_with_margin": list(grid_reference_model.density.bounds),
                "strategy": (
                    "thematic_only"
                    if args.thematic_extent_only
                    else "thematic_and_auxiliary_union"
                ),
            },
        }
    )
    if auxiliary_layers and output.suffix.lower() != ".gpkg":
        raise ValueError("Les couches auxiliaires nécessitent une sortie GeoPackage (.gpkg).")
    if grid_output == output and output.suffix.lower() != ".gpkg":
        raise ValueError("Une sortie commune aux deux couches doit être un GeoPackage (.gpkg).")
    if report_output == output or (grid_output is not None and report_output == grid_output):
        raise ValueError("Le rapport JSON doit avoir un chemin distinct des sorties géographiques.")
    _write(result, output, "cartogram")
    if grid is not None and grid_output is not None:
        _write(grid, grid_output, "deformation_grid")
    for layer_name, auxiliary in auxiliary_layers.items():
        _write(auxiliary, output, layer_name)
    _write_report(quality_report, report_output)
    return output, grid_output, report_output, quality_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cartogramme contigu par diffusion de Gastner-Newman.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("inputs", nargs="*", help="GeoJSON/SHP/GPKG; couche GPKG: fichier.gpkg::couche")
    parser.add_argument(
        "--aux-layer",
        action="append",
        dest="auxiliary_files",
        help="Couche supplémentaire à déformer sans contribuer à la densité (répétable)",
    )
    parser.add_argument("-a", "--attribute", help="Variable à égaliser par la surface")
    parser.add_argument("--id-field", help="Champ identifiant à valider et conserver")
    parser.add_argument("-o", "--output", help="Sortie; sinon nom GeoPackage généré automatiquement")
    parser.add_argument("--grid-output", help="Sortie de la grille; par défaut *_grid ou même GPKG")
    parser.add_argument("--report-output", help="Rapport JSON de contrôle des surfaces")
    parser.add_argument(
        "--grid-export-mode",
        choices=["lines", "cells", "none"],
        default=GRID_EXPORT_MODE,
        help="Grille légère en lignes, cellules détaillées, ou aucune grille",
    )
    parser.add_argument(
        "--full-grid-extent",
        action="store_true",
        default=not GRID_CROP_TO_INPUT,
        help="Exporter aussi la marge extérieure de la grille de calcul",
    )
    parser.add_argument(
        "--include-auxiliary-extent",
        action="store_false",
        dest="thematic_extent_only",
        default=THEMATIC_EXTENT_ONLY,
        help="Étendre la bbox de diffusion aux couches auxiliaires",
    )
    parser.add_argument("-n", "--grid-size", type=int, default=GRID_SIZE, help="Nombre de cellules par axe")
    parser.add_argument(
        "--iterations",
        type=int,
        default=CARTOGRAM_ITERATIONS,
        help="Passes complètes avec recalcul de la densité",
    )
    parser.add_argument(
        "--attribute-is-density",
        action="store_true",
        default=ATTRIBUTE_IS_DENSITY,
        help="L'attribut est déjà une densité",
    )
    parser.add_argument("--working-crs", help="CRS projeté de calcul, p. ex. EPSG:2056")
    parser.add_argument("--keep-working-crs", action="store_true", help="Ne pas reprojeter vers le CRS d'entrée")
    parser.add_argument("--margin", type=float, default=1.5, help="Facteur d'emprise autour des données")
    parser.add_argument("--density-floor", type=float, default=1e-3, help="Plancher relatif de densité")
    parser.add_argument("--blur", type=float, default=0.0, help="Lissage spectral initial en cellules")
    parser.add_argument("--integration-tolerance", type=float, default=0.01, help="Erreur RK tolérée en cellule")
    parser.add_argument("--convergence", type=float, default=1e-5, help="Déplacement maximal final en cellule")
    parser.add_argument("--max-steps", type=int, default=500, help="Nombre maximal de pas acceptés")
    parser.add_argument("--max-segment-length", type=float, help="Longueur max avant densification (CRS de calcul)")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    args.inputs = args.inputs or INPUT_FILES
    args.auxiliary_files = args.auxiliary_files or AUXILIARY_FILES
    args.attribute = args.attribute or VALUE_FIELD
    args.id_field = args.id_field or ID_FIELD or None
    args.output = args.output or OUTPUT_FILE
    args.grid_output = args.grid_output or GRID_OUTPUT_FILE or None
    args.report_output = args.report_output or REPORT_OUTPUT_FILE or None
    args.working_crs = args.working_crs or WORKING_CRS or None
    if not args.inputs:
        parser.error("indiquez un input dans INPUT_FILES ou sur la ligne de commande")
    if not args.attribute:
        parser.error("indiquez VALUE_FIELD ou --attribute")
    if not args.output:
        args.output = str(
            default_output_path(args.inputs, args.attribute, args.grid_size, args.iterations)
        )
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    try:
        output, grid_output, report_output, report = build_cartogram(args)
    except Exception as exc:
        if args.verbose:
            LOG.exception("Échec du cartogramme")
        else:
            LOG.error("%s", exc)
        return 1
    print(f"Cartogramme: {output}")
    if grid_output is None:
        print("Grille déformée: non exportée")
    else:
        print(f"Grille déformée: {grid_output}")
    print(f"Rapport de contrôle: {report_output}")
    size_error = report["size_error"]
    relative_error = report["relative_area_error_percent"]
    print(
        "Contrôle: SizeError moyen={:.2f} (idéal=100), erreur absolue médiane={:.2f}%".format(
            size_error["mean"], relative_error["median_absolute"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

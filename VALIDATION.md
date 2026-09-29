# Validation and development roadmap

This document lists the most important remaining checks and improvements. It
is deliberately finite and ordered by priority.

## 1. End-to-end format tests

Priority: high.

Run the same small cartogram through each advertised format:

- GeoPackage input and output;
- RFC 7946 GeoJSON input and output;
- ESRI Shapefile input and output, including its .prj, .dbf, .shx, and .cpg
  companion files.

For every run, verify:

- the input feature count and output feature count are identical;
- the selected identifier remains present, unique, and unchanged;
- the calculation attribute and other source attributes are retained;
- the output CRS is correct after the round trip;
- geometries are non-empty and valid;
- the JSON report and deformation grid are created;
- output can be reopened by GeoPandas and QGIS.

GeoJSON and Shapefile should remain documented as provisional until these
checks are automated and pass.

## 2. CRS behaviour

Priority: high.

Test separately:

- projected Swiss input in EPSG:2056;
- geographic input in EPSG:4326 or OGC:CRS84 with automatic UTM selection;
- explicit --working-crs and --keep-working-crs;
- a dataset crossing more than one UTM zone;
- missing CRS, which must fail with a clear message;
- Shapefile without .prj, which must also fail clearly;
- thematic and auxiliary layers starting in different known CRSs.

The tests should confirm that all areas and accuracy metrics are measured in
the projected working CRS, never directly in degrees.

## 3. Numerical correctness

Priority: high.

Use small synthetic geometries for which expected behaviour is easy to
understand:

- uniform density should produce almost no deformation;
- two equal rectangles with equal values should remain approximately equal;
- values in a 1:2 ratio should produce final areas close to 1:2;
- rasterized mass should match the sum of source values within a documented
  tolerance;
- zero-valued units should not cause division by zero or NaN coordinates;
- extreme value contrasts should terminate cleanly and preserve valid output;
- repeated runs with identical parameters should produce identical results.

Track cg_abserr, SizeError, mass conservation, geometry validity, and solver
termination. Compare one, two, and three cartogram passes so that the benefit
and possible instability of additional iterations are measurable.

## 4. Geometry and auxiliary-layer integrity

Priority: high.

Verify:

- Polygon and MultiPolygon inputs;
- holes and islands;
- shared borders between adjacent units;
- very small polygons and narrow geometries;
- an auxiliary lake partly outside the thematic bounding box;
- both thematic-only and combined thematic-plus-auxiliary extent modes;
- identical source vertices receive identical transformed coordinates;
- no unexpected empty, invalid, or self-intersecting geometry is introduced.

This is a geometric continuity test, not a claim that the program is a formal
topology engine.

## 5. GRID_SIZE recommendation helper

Priority: medium.

Add a read-only inspection command, tentatively:

~~~bash
python pyscapetoad.py data.gpkg::layer \
  --attribute population \
  --inspect-grid \
  --aux-layer context.gpkg::layer
~~~

The helper should not run the cartogram or modify any file. It should report:

- thematic, auxiliary, combined, and selected bounding boxes;
- projected width and height after applying the margin;
- feature count and polygon-area quantiles;
- a robust small-feature scale, for example the equivalent-circle diameter
  derived from the 10th area percentile;
- estimated cell width and height for candidate grids such as 64, 128, 256,
  512, and 1024;
- approximate raster memory and a qualitative runtime warning;
- the effect of including auxiliary extents;
- a warning when the study area spans several UTM zones.

A first recommendation can target several cells across a representative small
feature:

~~~text
small_feature_scale = 2 × sqrt(area_10th_percentile / pi)
target_cell_size     = small_feature_scale / cells_across_small_feature
suggested_grid_size  = max(padded_width, padded_height) / target_cell_size
~~~

The result should be rounded to a supported practical size and bounded by safe
minimum and maximum values. The default target might be 3 to 5 cells across a
representative small feature, but this must be calibrated with the numerical
tests.

Extent alone is not enough. Two territories with the same bounding box can
need different grids when one contains thousands of small communes and the
other contains a few large regions. The helper should therefore return a
small table of candidate settings and trade-offs, not claim that one value is
universally correct. The final choice should still be checked against the
resulting cg_abserr report.

## 6. README illustration

Priority: medium.

Add one compact, reproducible figure near the Quick start section containing:

1. the original voting geography;
2. the eligible_voters cartogram;
3. the cumulative deformation grid over the cartogram.

The figure should:

- use the documented voge_voters example and parameters;
- state GRID_SIZE, iteration count, attribute, and working CRS in its caption;
- use identical visual styling where comparison requires it;
- explain that polygon colour represents an attribute while polygon area
  represents eligible_voters;
- include source attribution to the Swiss Federal Statistical Office;
- be exported as an optimized PNG or WebP at a readable width;
- be reproducible from a small plotting script or documented QGIS procedure.

Do not commit the full generated cartogram solely to create the illustration.
Commit the optimized image and its reproducible generation instructions.

## 7. Output and interface regression checks

Priority: medium.

Verify:

- automatic snake_case filenames;
- explicit output, grid-output, and report-output paths;
- command-line arguments overriding top-of-file settings;
- rerunning into the same GeoPackage replaces relevant layers without
  duplicating features;
- lines, cells, and none grid-export modes;
- full-grid and cropped-grid exports;
- preservation of non-ASCII identifiers and attribute names where supported;
- clear failures for missing attributes, duplicate IDs, negative values, and
  unsupported file extensions.

## 8. Environment and performance checks

Priority: lower, before a stable release.

- Install from requirements.txt in clean Python 3.10, 3.11, and 3.12
  environments.
- Run at least one clean setup on macOS, Linux, and Windows.
- Resolve and pin mutually compatible NumPy and SciPy ranges.
- Record runtime and peak memory for 128, 256, and 512 grids.
- Confirm that a failed run leaves no misleading partial output.

## Suggested completion order

1. Format and CRS tests.
2. Synthetic numerical tests.
3. Geometry and auxiliary-layer tests.
4. Grid inspection and recommendation helper.
5. Reproducible README figure.
6. Interface, environment, and performance checks.

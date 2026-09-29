# py-scapetoad

py-scapetoad creates contiguous diffusion cartograms from vector geographic
data. It is a standalone Python adaptation of the mathematical core of
ScapeToad, without its Swing user interface, JTS/JUMP dependencies, or Java
Shapefile parser.

## Quick start

The recommended input is one geographic file containing:

- one Polygon or MultiPolygon geometry per geographic unit;
- a stable identifier, such as commune_id;
- a positive extensive variable, such as population or eligible_voters.

Create and activate a virtual environment:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

Run the included voting example:

~~~bash
python pyscapetoad.py \
  data/voge_voters.gpkg::voge_voters \
  --aux-layer data/lakes.gpkg::lakes \
  --id-field vogeId \
  --attribute eligible_voters \
  --working-crs EPSG:2056 \
  --grid-size 256 \
  --iterations 3 \
  --grid-export-mode lines \
  --verbose
~~~

Because no output path is supplied, this creates:

~~~text
data/voge_voters_eligible_voters_grid_256_iter_3.gpkg
data/voge_voters_eligible_voters_grid_256_iter_3_report.json
~~~

The GeoPackage contains:

- cartogram: transformed thematic polygons with all original attributes and
  per-feature accuracy diagnostics;
- deformation_grid: the regular source grid after the cumulative deformation;
- aux_lakes: lakes transformed by exactly the same displacement fields.

The JSON report contains global accuracy statistics, parameters, coordinate
reference systems, extents, and geometry validity checks.

## Origin, credits, and license

This project adapts the computation core of
[ScapeToad](https://github.com/christiankaiser/ScapeToad), the original Java
cartogram application. Contributors to the original repository include:

- [Christian Kaiser](https://github.com/christiankaiser);
- [Jason Davies](https://github.com/jasondavies).

This repository reimplements and adapts the Gastner–Newman diffusion logic
using NumPy, SciPy, GeoPandas, and Shapely. It is not the original Java
application and is not presented as an official ScapeToad release. The Java
classes studied and the implementation differences are documented below.

ScapeToad is distributed under GNU GPL v2. This adaptation is therefore
distributed under the GNU General Public License v2.0 only. See
[LICENSE.txt](LICENSE.txt). Attribution to the original work and its link must
be retained in redistributed versions.

## Demonstration data and attribution

The two GeoPackages in [data/](data/) are derived from official data published
by the Swiss Federal Statistical Office (FSO):

- voge_voters.gpkg contains voting geographies and voting data for the Swiss
  federal vote of 14 June 2026;
- lakes.gpkg contains major lakes used as geographic context.

Official sources:

- [Real-time data on federal voting proposals on voting day](https://opendata.swiss/de/dataset/echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen)
- [Geodata for federal voting proposals](https://opendata.swiss/de/dataset/geodaten-zu-den-eidgenoessischen-abstimmungsvorlagen)

Publisher: Swiss Federal Statistical Office (FSO). The files are included for
testing and demonstration. Their inclusion does not transfer or alter any
rights attached to the source data. Users remain responsible for checking and
complying with the current terms of use and attribution requirements on the
source pages before reuse or redistribution. See [data/README.md](data/README.md).

## Configuration at the top of the script

All common settings can be edited near the beginning of
[pyscapetoad.py](pyscapetoad.py):

~~~python
INPUT_FILES = ["data/voge_voters.gpkg::voge_voters"]
AUXILIARY_FILES = ["data/lakes.gpkg::lakes"]

OUTPUT_FILE = ""
GRID_OUTPUT_FILE = ""
REPORT_OUTPUT_FILE = ""

ID_FIELD = "vogeId"
VALUE_FIELD = "eligible_voters"

WORKING_CRS = "EPSG:2056"
ATTRIBUTE_IS_DENSITY = False

GRID_SIZE = 256
CARTOGRAM_ITERATIONS = 3
GRID_EXPORT_MODE = "lines"
GRID_CROP_TO_INPUT = True
THEMATIC_EXTENT_ONLY = True
~~~

Then run:

~~~bash
python pyscapetoad.py
~~~

Command-line arguments override the values in this block.

### Configuration parameters

| Python setting | Type | Meaning |
|---|---|---|
| INPUT_FILES | list[str] | One or more input datasets. Append ::layer_name for a GeoPackage layer. One file containing geometry, identifier, and value is recommended. |
| AUXILIARY_FILES | list[str] | Context layers transformed with the same field but excluded from density calculations, for example lakes or borders. |
| OUTPUT_FILE | str | Main geographic output. When empty, a reproducible GeoPackage name is generated from the source, variable, grid size, and iteration count. |
| GRID_OUTPUT_FILE | str | Deformed-grid output. When empty and the main output is a GeoPackage, the grid is written into that GeoPackage. Otherwise a separate _grid file is created. |
| REPORT_OUTPUT_FILE | str | JSON accuracy report. When empty, the name is derived from the main output with a _report.json suffix. |
| ID_FIELD | str | Identifier field. Presence, uniqueness, and null values are checked. When empty, the native feature identifier is retained in src_id. |
| VALUE_FIELD | str | Numeric attribute driving the cartogram, such as population or eligible_voters. Required either here or through --attribute. |
| WORKING_CRS | str | Projected CRS used for areas and diffusion. When empty, an already projected input CRS is retained; otherwise a local UTM CRS is estimated. |
| ATTRIBUTE_IS_DENSITY | bool | False for a total quantity; True only when values are already expressed per unit of area. |
| GRID_SIZE | int | Number of cells along each axis. The total is GRID_SIZE squared: 128 creates 16,384 cells and 256 creates 65,536. |
| CARTOGRAM_ITERATIONS | int | Number of complete passes, with density recomputed from the geometry produced by the previous pass. Start with 1; try 2 or 3 to reduce residual error. |
| GRID_EXPORT_MODE | str | lines for a lightweight visual mesh, cells for density-bearing polygons, or none to omit the grid. |
| GRID_CROP_TO_INPUT | bool | When True, hides the external computational margin in the exported grid. The margin remains active in the solver. |
| THEMATIC_EXTENT_ONLY | bool | When True, derives the diffusion extent from the thematic layer only. When False, uses the union of thematic and auxiliary extents. |

OUTPUT_FILE, GRID_OUTPUT_FILE, and REPORT_OUTPUT_FILE must normally be
different paths, although the cartogram and grid may share a GeoPackage.
Running the program again may replace the cartogram and deformation_grid
layers in that file. Choose another output path to preserve an earlier result.

## Dependencies and installation

The project targets Python 3.10 or newer. Python 3.11 is recommended and has
been used for testing.

Main dependencies:

- geopandas: vector data reading, reprojection, merging, and writing;
- shapely 2 or newer: intersections, densification, and geometry transforms;
- numpy: raster grids and vectorized numerical operations;
- scipy: scipy.fft.dctn and scipy.fft.idctn;
- pandas, pyproj, and pyogrio: tables, CRS handling, and GDAL-backed drivers.

All application code is contained in the single pyscapetoad.py file. The
scientific libraries and format drivers remain external dependencies listed in
[requirements.txt](requirements.txt). Pyogrio provides GDAL access to
GeoPackage, Shapefile, and GeoJSON without requiring Fiona.

Recommended setup:

- Python 3.10 or newer;
- a dedicated virtual environment;
- a recent pip version so binary GeoPandas and Pyogrio wheels can be used;
- approximately 1 GB of free memory for ordinary grids, with more needed for
  512 by 512 grids, multiple iterations, or very detailed geometries.

macOS and Linux:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

Windows PowerShell:

~~~powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

Verify the environment:

~~~bash
python -c "import geopandas, shapely, numpy, scipy, pyogrio; print('OK')"
python pyscapetoad.py --help
~~~

NumPy and SciPy must use mutually compatible versions. If pip attempts to
compile GDAL instead of downloading a wheel, first check that the Python
version is supported and that pip is current.

## Inputs

Supported input formats:

- GeoJSON: .geojson or .json;
- ESRI Shapefile: .shp plus its companion files;
- GeoPackage: .gpkg.

Select a GeoPackage layer with:

~~~text
dataset.gpkg::layer_name
~~~

A single file containing the identifier and calculation variable is
recommended. Multiple thematic input files are supported and are merged after
reprojection to the CRS of the first file. Every file must contain the field
passed to --attribute and, when supplied, the field passed to --id-field.

The identifier check validates field presence, non-null values, and uniqueness
within every source. All source columns are retained. The program also adds:

- src_id: the native feature identifier read by GeoPandas;
- src_file: the source file path.

If either name already exists, underscore prefixes are added rather than
overwriting user data.

Only Polygon and MultiPolygon features contribute to density. Points and lines
may still be transformed and exported, but they do not affect the calculation.

### Quantity versus density

By default, --attribute population describes an extensive quantity. For each
feature:

~~~text
density = population / current_area
~~~

If the attribute is already an intensive density, such as inhabitants per
square kilometre, use --attribute-is-density. The program converts it to an
internal mass by multiplying density by initial area. This ensures that
multiple iterations preserve the same quantity for each territory.

A percentage or ratio is usually not a spatial density:

| Intended result | Variable | ATTRIBUTE_IS_DENSITY |
|---|---|---:|
| Area proportional to eligible voters | eligible_voters | False |
| Area proportional to the number of yes votes | yes_votes | False |
| Equal base weight per municipality, modulated by its yes rate | yes_percent | False |
| Mass equal to yes_percent multiplied by original geographic area | yes_percent | True |

The last option is mathematically valid but is rarely appropriate for voting
data. Two municipalities with the same percentage receive different masses
only because their land areas differ. Use it only if yes_percent is genuinely
intended as a value per unit of area. For an electoral-weight map of yes
votes, yes_votes with ATTRIBUTE_IS_DENSITY set to False is recommended.

Values must be numeric, finite, non-negative, and at least one value must be
strictly positive.

### Auxiliary layers and topology

AUXILIARY_FILES or the repeatable --aux-layer option adds context layers that
do not contribute to density. They are densified and transformed through
exactly the same sequence of displacement fields as the thematic layer.

By default, THEMATIC_EXTENT_ONLY is True. The diffusion extent is calculated
from the thematic bounding box and then expanded by the computational margin.
Auxiliary geometries within that expanded domain are transformed. Parts truly
outside it are left in their original position instead of being clamped to the
boundary.

When THEMATIC_EXTENT_ONLY is False, every iteration uses the union of the
thematic and auxiliary bounding boxes before adding the margin. All auxiliary
layers are then inside the diffusion domain. In the demonstration data, this
explicit union includes the extensions of Bodensee and Lago Maggiore.

Command-line equivalent:

~~~bash
--include-auxiliary-extent
~~~

Example:

~~~bash
--aux-layer data/lakes.gpkg::lakes
~~~

The output GeoPackage layer is named aux_lakes. Its attributes and src_id are
retained.

The transformation is a continuous field shared by all layers. Initially
identical coordinates therefore remain identical, normally preserving shared
edges and visual coherence. This corresponds to ScapeToad's simultaneously
transformed layers. It is not a formal GIS topology engine: poorly aligned
sources, boundaries that are only nearly coincident, or extreme deformation
can still create discrepancies. The report records valid and empty geometry
counts for every auxiliary layer.

Avoid context layers whose extent is far larger than the thematic region. At
a fixed GRID_SIZE, expanding the bounding box increases the ground size of
each cell, reduces effective resolution over the area of interest, increases
the mean-density background, and can weaken the deformation. Clip context to
a reasonable neighbourhood or increase GRID_SIZE while monitoring memory and
runtime.

The JSON report exposes:

- initial_extents.thematic_bounds;
- auxiliary_bounds;
- combined_bounds;
- selected_bounds;
- strategy;
- diffusion_bounds_with_margin.

## Outputs

The same format families are available for output. GeoPackage is recommended
because it preserves modern field names and can contain multiple layers.

### Automatic naming

If OUTPUT_FILE and --output are omitted, the program writes a GeoPackage next
to the first input using this snake_case convention:

~~~text
<source_file>_<variable>_grid_<size>_iter_<iterations>.gpkg
~~~

Examples:

~~~text
communes_population_grid_128_iter_1.gpkg
voge_voters_eligible_voters_grid_256_iter_3.gpkg
~~~

Spaces, accents, and punctuation are normalized to create a portable name.
For multiple thematic inputs, _merged is appended to the first filename.
An explicit OUTPUT_FILE or --output always takes priority.

### GeoPackage

~~~bash
python pyscapetoad.py input.gpkg::zones -a population -o result.gpkg
~~~

The cartogram and deformation grid are both written to result.gpkg.

### GeoJSON and Shapefile

~~~bash
python pyscapetoad.py input.geojson -a population -o result.geojson
~~~

This creates result.geojson, result_grid.geojson, and result_report.json.
Use --grid-output or --report-output to choose different paths.

Shapefile has its usual restrictions, including short field names and one
layer per file. GeoPackage is preferable when retaining the complete schema
matters.

### Visual grid and computational margin

A margin factor of 1.5 around the data supports the diffusion boundary
conditions. Removing it from the calculation can push or flatten territories
near the edge. The margin need not be displayed.

The default export settings are:

~~~python
GRID_EXPORT_MODE = "lines"
GRID_CROP_TO_INPUT = True
~~~

They create a few hundred transformed lines rather than tens of thousands of
cell polygons and omit the outer margin from the exported layer. The mesh
shows how regular source space was transformed:

- wider spacing after transformation indicates local expansion;
- narrower spacing indicates local contraction;
- curved or tilted lines indicate displacement direction.

With multiple cartogram iterations, every successive transformation is
composed onto the original reference grid. The export therefore shows total
deformation, not only the almost-regular correction from the final pass.

To inspect cell density:

~~~bash
--grid-export-mode cells
~~~

Cells then contain cell_id, row, col, density, and iteration fields.

To include the complete computational margin:

~~~bash
--full-grid-extent
~~~

For the smallest output:

~~~bash
--grid-export-mode none
~~~

## Accuracy and quality control

The cartogram layer contains these diagnostics for every geographic unit:

| Field | Meaning |
|---|---|
| cg_a_orig | Area before deformation |
| cg_a_cart | Area obtained in the cartogram |
| cg_a_targ | Theoretical target area |
| cg_vshare | Share of the total variable or mass, from 0 to 1 |
| cg_ashare | Share of final area, from 0 to 1 |
| SizeError | ScapeToad-compatible indicator; ideal value is 100 |
| cg_ratio | Obtained area divided by target area; ideal value is 1 |
| cg_relerr | Signed area error in percent |
| cg_abserr | Absolute value of the preceding error |
| cg_status | on_target, too_small, too_large, or no_target |
| cg_quality | excellent, good, acceptable, poor, or very_poor |

Areas are measured in the projected working CRS and remain expressed in its
squared units even if geometries are converted back to EPSG:4326 for output.

The original ScapeToad formula simplifies to:

~~~text
SizeError = 100 × variable_share / final_area_share
~~~

Interpretation:

- 100: area is exactly proportional to the variable;
- 120: the territory is still too small relative to its target;
- 80: the territory is too large relative to its target.

The signed relative error is often more intuitive:

~~~text
cg_relerr = 100 × (final_area - target_area) / target_area
~~~

A value of +20 means the final area is 20 percent too large, while -20 means
it is 20 percent too small. A zero-target feature has no defined relative
error and is excluded from aggregate relative-error statistics.

The cg_ratio field expresses the same relationship:

- 1.00: target reached;
- 1.20: final area is 20 percent too large;
- 0.80: final area is 20 percent too small.

Quality categories use absolute error:

| Category | Difference from target |
|---|---:|
| excellent | 5 percent or less |
| good | over 5 and up to 10 percent |
| acceptable | over 10 and up to 20 percent |
| poor | over 20 and up to 50 percent |
| very_poor | over 50 percent |

The JSON report includes:

- mean, standard deviation, and quartiles of SizeError;
- mean, median, and maximum absolute error;
- percentages of units within 5, 10, and 20 percent of their targets;
- Pearson correlation between the variable and cartogram area;
- counts of evaluable and zero-target features;
- working CRS and the main solver parameters.

The terminal also prints mean SizeError and median absolute error when the
calculation ends. Mean SizeError alone may conceal positive and negative
errors; always inspect cg_abserr, the quartiles, and report thresholds as well.

### Visual inspection in QGIS

1. Open the cartogram layer.
2. Apply categorized styling to cg_quality to locate poorly fitted units.
3. Apply divergent graduated styling to cg_relerr, centred on zero, to
   distinguish units that are too small from those that are too large.
4. Display deformation_grid above the polygons using thin lines.
5. Inspect cg_a_cart, cg_a_targ, and cg_ratio in feature tooltips.

The primary feature-level accuracy measure is cg_abserr. To compare two
parameter sets, use median cg_abserr, the within_10_percent and
within_20_percent report values, and then the area-variable correlation. A
high correlation alone does not guarantee accurate small units.

### What accuracy means here

The target is independent of the final shape:

~~~text
target_area = (feature_value / sum_of_values) × total_final_area
~~~

The diagnostics compare measured final area in the projected working CRS with
this target. They therefore measure the mathematical goal of a cartogram:
making area proportional to the chosen variable.

They do not validate:

- the quality or timeliness of the source variable;
- the statistical relevance of the geographic partition;
- visual recognizability of the final territories;
- complete absence of local boundary distortion.

The solver is a grid approximation. Small units, very low values, and extreme
contrasts are the hardest cases. A finer grid and multiple passes usually
reduce area error at the cost of runtime, memory, and vertex count.

### Demonstration benchmark

For eligible_voters with GRID_SIZE 256 and 3 iterations:

- all 2,105 geometries are valid;
- median absolute error is 12.70 percent;
- 42.09 percent of units are within 10 percent of their target;
- 64.70 percent are within 20 percent;
- cartogram-area correlation with eligible_voters is 0.9989;
- cg_quality contains 516 excellent, 370 good, 476 acceptable, 482 poor, and
  261 very_poor units.

The cropped cumulative visual grid contains 282 lines, compared with 65,536
polygons for the full cell grid. The lightweight GeoPackage is approximately
5 MB.

## Coordinate reference systems

Diffusion uses Euclidean distances and areas, so it must run in a projected
CRS. Any projected CRS recognized by PROJ and GeoPandas can be used, including:

- EPSG:2056 for Switzerland;
- an appropriate national projected CRS;
- a suitable equal-area projection when area interpretation has priority.

EPSG:4326 is supported for input and output because it is common for GeoJSON,
but it is not used directly for diffusion: degrees are not distance or area
units. For geographic input, the program estimates a local UTM zone, performs
the calculation there, and transforms results back to the original CRS.

For data spanning several UTM zones, a large country, or the world, explicitly
provide an appropriate projected working CRS:

~~~bash
python pyscapetoad.py world.gpkg::countries \
  -a population \
  -o world_cartogram.gpkg \
  --working-crs ESRI:54009
~~~

Use --keep-working-crs to retain output in the calculation CRS. Otherwise the
output CRS matches the first thematic input.

## Calculation method

### Java classes studied

The port was isolated from four classes under ScapeToad/src:

- CartogramGrid.java: grid, densities, and extent;
- CartogramNewman.java: DCT, spectral diffusion, velocity field, and
  Runge–Kutta integration;
- CartogramGastner.java: the alternative historical FFT implementation,
  margins, density bias, interpolation, and projection;
- CartogramFeature.java: vertex densification and projection.

Swing/AWT code, the application wizards, JUMP/JTS, and Java Shapefile parsing
were intentionally excluded.

### Available calculation methods

| Method | Status |
|---|---|
| Newman DCT method from CartogramNewman | Active solver |
| Historical mixed-FFT CartogramGastner implementation | Studied for extent, density bias, and interpolation; not exposed as a second solver |
| Successive-pass refinement | Python extension available through --iterations |
| ScapeToad constrained deformation | Not implemented |

There is no --method selector in this version. The active calculation always
uses the Newman/DCT solver, which is also the solver invoked by Cartogram.java
in the examined ScapeToad source.

### Density raster

compute_density creates a NumPy matrix with shape ny by nx. For an extensive
variable, every feature-cell intersection contributes:

~~~text
intersection_mass = feature_value × intersection_area / feature_area
cell_density = cell_mass / cell_area
~~~

Empty parts of the extent receive the weighted mean density. A small relative
floor controlled by --density-floor prevents divisions by zero.

Area-intersection rasterization is a deliberate improvement over the active
CartogramGrid.fillDensityValueWithFeature Java path, which mainly assigns a
cell from its centre point. The Python approach conserves mass more accurately
but requires more expensive Shapely intersections.

### Gastner–Newman diffusion

Initial density is transformed using a two-dimensional DCT:

~~~python
rho_hat = scipy.fft.dctn(rho, type=2, norm="ortho")
~~~

The spectral heat-equation solution is:

~~~text
rho_hat(k, t) = exp(-(kx² + ky²)t) × rho_hat(k, 0)
~~~

The DCT represents reflecting, zero-normal-flux boundaries as in
CartogramNewman. Velocity uses the four-cell stencil inspired by Newman:

~~~text
v = -grad(rho) / rho
~~~

Grid nodes are advected with fourth-order Runge–Kutta integration. Error is
estimated by comparing one full step with two half steps. Steps can be
rejected or enlarged adaptively, with a maximum growth factor of four. A
higher-order correction follows the Java implementation.

Finally, Shapely segments are densified and their vertices are displaced by
bilinear interpolation of the deformed mesh.

### Direct translation versus adaptation

This is not a line-for-line translation:

- JTransforms DoubleDCT_2D is replaced with scipy.fft using orthonormal
  normalization. Absolute normalization differs but cancels in
  -grad(rho)/rho;
- Java arrays and loops are vectorized with NumPy where useful;
- the integrator follows Newman's adaptive RK4 principle but uses explicit
  --convergence and --max-steps limits instead of waiting for exactly zero
  floating-point displacement;
- optional blur is applied as an initial spectral time of blur squared over 2;
- constrained-deformation layers and GUI legends are not implemented;
- the exported grid composes every pass onto the regular grid from the first
  iteration. In cells mode, density therefore refers to that initial reference
  grid.

### Cartogram iterations

--iterations N repeats the complete pipeline:

1. recompute value divided by current area;
2. rasterize density;
3. run diffusion;
4. transform the geometry produced by the preceding pass.

One pass is often enough. Additional passes reduce errors caused by raster
resolution and interpolation, but increase runtime and vertex counts. Two or
three passes are reasonable starting points; many passes can amplify numerical
artifacts.

In the examined ScapeToad source, CartogramNewman.compute is called once. An
older mDiffusionIterations field exists in Cartogram.java but is commented
out. The external iterations in this Python program are therefore an explicit
extension, not a translation of an active Java loop.

Do not confuse:

- --iterations: complete cartogram passes;
- --max-steps: internal accepted time-step limit for one diffusion pass.

## Complete CLI examples

Eligible voters, 256-cell grid, and three passes:

~~~bash
python pyscapetoad.py \
  data/voge_voters.gpkg::voge_voters \
  --id-field vogeId \
  --attribute eligible_voters \
  --working-crs EPSG:2056 \
  --grid-size 256 \
  --iterations 3 \
  --grid-export-mode lines \
  --verbose
~~~

Yes votes with lakes transformed at the same time and included in the
diffusion extent:

~~~bash
python pyscapetoad.py \
  data/voge_voters.gpkg::voge_voters \
  --aux-layer data/lakes.gpkg::lakes \
  --include-auxiliary-extent \
  --id-field vogeId \
  --attribute yes_votes \
  --working-crs EPSG:2056 \
  --grid-size 256 \
  --iterations 3 \
  --grid-export-mode lines \
  --verbose
~~~

Exploratory run treating yes_percent as a spatial density:

~~~bash
python pyscapetoad.py \
  data/voge_voters.gpkg::voge_voters \
  --aux-layer data/lakes.gpkg::lakes \
  --id-field vogeId \
  --attribute yes_percent \
  --attribute-is-density \
  --working-crs EPSG:2056 \
  --grid-size 256 \
  --iterations 3 \
  --grid-export-mode lines \
  --verbose
~~~

This final example is computationally valid but usually not the recommended
interpretation of a voting percentage. See Quantity versus density above.

For a 512 by 512 grid and six passes:

~~~bash
--grid-size 512 --iterations 6
~~~

Without --output, every command uses the automatic filename convention.

## Main command-line parameters

| Parameter | Purpose | Default |
|---|---|---:|
| --id-field | Identifier field to validate and retain | native FID |
| --aux-layer | Context layer to transform; repeatable | none |
| --attribute, -a | Quantity or density used for the cartogram | required |
| --output, -o | Explicit output path | automatic |
| --attribute-is-density | Interpret values as density per unit area | false |
| --grid-size, -n | Cells along each axis | 128 |
| --iterations | Complete cartogram passes | 1 |
| --report-output | Accuracy report path | <output>_report.json |
| --grid-export-mode | lines, cells, or none | lines |
| --full-grid-extent | Include the computational margin in the exported grid | false |
| --include-auxiliary-extent | Extend diffusion bounds to auxiliary layers | false |
| --working-crs | Projected calculation CRS | automatic |
| --keep-working-crs | Keep output in the calculation CRS | false |
| --margin | Computational extent around the data | 1.5 |
| --density-floor | Relative density floor | 0.001 |
| --blur | Initial spectral smoothing in cells | 0 |
| --integration-tolerance | Adaptive RK tolerance | 0.01 |
| --convergence | Maximum final displacement in cell units | 1e-5 |
| --max-steps | Accepted time steps per pass | 500 |
| --max-segment-length | Vertex densification in working-CRS units | half a cell |
| --verbose | Show detailed progress information | false |

Display every available option with:

~~~bash
python pyscapetoad.py --help
~~~

## Practical trade-offs

- A finer grid better represents small features, but memory use grows with the
  square of grid size and raster intersections take longer.
- Multiple passes and fine densification improve boundary continuity but
  generate more vertices.
- Area-intersection rasterization conserves mass better than centre-point
  rasterization but is slower.
- Extreme value disparities can create highly stretched cells. Density
  flooring and blur reduce that risk at the cost of a less extreme result.
- Area quality depends on the working CRS. Automatically selected UTM is
  suitable for local extents, not global analysis.
- Including distant auxiliary features in the extent ensures they are
  transformed but reduces effective grid resolution over the thematic layer.

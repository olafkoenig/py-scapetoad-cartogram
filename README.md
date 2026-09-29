# py-scapetoad

`pyscapetoad.py` produit des cartogrammes contigus par diffusion à partir d'un
fichier vectoriel. Il s'agit d'une retranscription autonome du noyau
mathématique de ScapeToad, sans interface Swing, JTS, JUMP ni lecteur de
Shapefile Java.

## Origine, crédits et licence

Ce projet est une adaptation Python du noyau de calcul de
[ScapeToad](https://github.com/christiankaiser/ScapeToad), l'application Java
originale de cartogrammes. Les contributeurs du dépôt original incluent :

- [Christian Kaiser](https://github.com/christiankaiser) ;
- [Jason Davies](https://github.com/jasondavies).

Le présent projet retranscrit et adapte la logique de diffusion
Gastner–Newman avec NumPy, SciPy, GeoPandas et Shapely. Il ne s'agit pas de
l'application Java originale et il n'est pas présenté comme une version
officielle de ScapeToad. Les correspondances avec les classes Java et les
différences d'implémentation sont documentées plus bas.

ScapeToad est distribué sous GNU GPL v2. Cette adaptation est par conséquent
distribuée sous **GNU General Public License v2.0 only**; le texte complet se
trouve dans `LICENSE.txt`. Les mentions de l'œuvre d'origine et ce lien doivent
être conservés lors d'une redistribution.

## Quick hands-on

Le cas recommandé est **un seul fichier géographique** contenant au minimum :

- une géométrie polygonale par territoire ;
- un identifiant stable, par exemple `commune_id` ;
- une variable extensive positive, par exemple `population`.

Exemple en ligne de commande :

```bash
python pyscapetoad.py data/communes.gpkg::communes \
  --id-field commune_id \
  --attribute population \
  --output output/cartogramme.gpkg \
  --grid-size 128 \
  --iterations 1 \
  --verbose
```

Le GeoPackage obtenu contient :

- `cartogram` : les territoires déformés, avec les attributs et identifiants
  du fichier source ;
- `deformation_grid` : le maillage initial après composition cumulative de
  toutes les itérations. Par défaut, il s'agit de lignes légères et recadrées
  sur l'emprise utile.

Il est aussi possible de renseigner les chemins et champs au début de
[`pyscapetoad.py`](pyscapetoad.py) :

```python
INPUT_FILES = ["data/communes.gpkg::communes"]
AUXILIARY_FILES = []
OUTPUT_FILE = ""
GRID_OUTPUT_FILE = ""
REPORT_OUTPUT_FILE = ""
ID_FIELD = "commune_id"
VALUE_FIELD = "population"
WORKING_CRS = "EPSG:2056"
ATTRIBUTE_IS_DENSITY = False
GRID_SIZE = 128
CARTOGRAM_ITERATIONS = 1
GRID_EXPORT_MODE = "lines"
GRID_CROP_TO_INPUT = True
THEMATIC_EXTENT_ONLY = True
```

Puis lancer simplement :

```bash
python pyscapetoad.py
```

Les arguments CLI ont priorité sur ce bloc de configuration.

### Paramètres du bloc de configuration

Le bloc situé au début de `pyscapetoad.py` permet d'exécuter le programme sans
aucun argument. Les chaînes vides demandent au script d'appliquer le
comportement automatique décrit ci-dessous.

| Paramètre Python | Type | Description |
|---|---|---|
| `INPUT_FILES` | `list[str]` | Un ou plusieurs fichiers d'entrée. Pour un GeoPackage, ajouter `::nom_couche`. Un seul fichier contenant géométrie, identifiant et variable est recommandé. |
| `AUXILIARY_FILES` | `list[str]` | Couches de contexte à déformer avec le même champ sans contribuer au calcul, par exemple lacs ou frontières. |
| `OUTPUT_FILE` | `str` | Fichier géographique principal. Si vide, un nom GeoPackage reproductible est généré avec la source, la variable, la grille et les itérations. |
| `GRID_OUTPUT_FILE` | `str` | Sortie de la grille déformée. Si vide avec une sortie `.gpkg`, la grille est ajoutée au même GeoPackage. Pour les autres formats, un fichier `_grid` est créé. |
| `REPORT_OUTPUT_FILE` | `str` | Rapport JSON des erreurs surfaciques. Si vide, le nom `<OUTPUT_FILE>_report.json` est utilisé. |
| `ID_FIELD` | `str` | Champ identifiant. Sa présence, son unicité et l'absence de valeurs nulles sont contrôlées. Si vide, le FID natif est conservé dans `src_id`. |
| `VALUE_FIELD` | `str` | Champ numérique qui pilote le cartogramme, par exemple `population` ou `eligible_voters`. Il est obligatoire. |
| `WORKING_CRS` | `str` | CRS projeté utilisé pour les surfaces et la diffusion. Si vide, le CRS projeté de l'entrée est conservé; pour une entrée géographique, une zone UTM est estimée. |
| `ATTRIBUTE_IS_DENSITY` | `bool` | `False` si la variable est une quantité totale; `True` si elle contient déjà une densité par unité de surface. |
| `GRID_SIZE` | `int` | Nombre de cellules sur chaque axe. Le nombre total est `GRID_SIZE²`; 128 produit 16 384 cellules et 256 en produit 65 536. |
| `CARTOGRAM_ITERATIONS` | `int` | Nombre de passes complètes avec recalcul de la densité sur la géométrie obtenue. Commencer avec 1; utiliser 2 ou 3 pour corriger les résidus. |
| `GRID_EXPORT_MODE` | `str` | `"lines"` pour un maillage visuel léger, `"cells"` pour les cellules avec leur densité, ou `"none"` pour ne pas exporter de grille. |
| `GRID_CROP_TO_INPUT` | `bool` | Si `True`, masque dans l'export la marge extérieure nécessaire au calcul. La marge reste bien utilisée par l'algorithme. |
| `THEMATIC_EXTENT_ONLY` | `bool` | `True` utilise seulement la bbox thématique; `False` utilise l'union des bbox thématique et auxiliaires. |

`OUTPUT_FILE`, `GRID_OUTPUT_FILE` et `REPORT_OUTPUT_FILE` doivent désigner des
chemins distincts, sauf la grille et le cartogramme qui peuvent partager un
GeoPackage. Une nouvelle exécution peut remplacer ou actualiser les couches
`cartogram` et `deformation_grid` existantes : choisir un nouveau
`OUTPUT_FILE` pour conserver un résultat antérieur.

### Configuration du jeu de test `voge_voters`

Le réglage validé pour les 2 105 territoires et le champ `eligible_voters`
est :

```python
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
```

Le champ `id` de ce jeu de test est vide; `vogeId` est complet et unique. Le
nom calculé automatiquement est :

```text
data/voge_voters_eligible_voters_grid_256_iter_3.gpkg
```

Lancer ensuite depuis la racine du projet :

```bash
python pyscapetoad.py
```

Le GeoPackage contient les couches `cartogram` et `deformation_grid`; le
rapport est créé à côté sous le nom
`voge_voters_eligible_voters_grid_256_iter_3_report.json`.

## Dépendances

Le programme vise Python 3.10 ou plus récent et utilise :

- `geopandas` pour lire, fusionner, reprojeter et écrire les couches ;
- `shapely >= 2` pour les intersections, la densification et la transformation
  des géométries ;
- `numpy` pour les grilles et le calcul vectorisé ;
- `scipy` pour `scipy.fft.dctn` et `scipy.fft.idctn` ;
- `pandas`, `pyproj` et `pyogrio` pour les tables, CRS et pilotes GDAL.

### Configuration recommandée

- Python 3.10 ou plus récent; Python 3.11 est recommandé et testé ;
- un environnement virtuel dédié ;
- `pip` récent pour obtenir les roues binaires GeoPandas/Pyogrio ;
- environ 1 Go de mémoire libre pour les grilles usuelles; davantage pour
  512×512, plusieurs itérations et des géométries très détaillées.

macOS et Linux :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell :

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Vérification :

```bash
python -c "import geopandas, shapely, numpy, scipy, pyogrio; print('OK')"
python pyscapetoad.py --help
```

NumPy et SciPy doivent appartenir à des versions mutuellement compatibles.
Dans l'environnement de développement actuel, SciPy 1.15.3 avertit que NumPy
2.5.3 est trop récent pour sa plage officiellement prise en charge, même si les
tests fonctionnels passent.

Tout le code applicatif est inclus dans `pyscapetoad.py`. Les bibliothèques
scientifiques et les pilotes de formats restent des dépendances externes,
déclarées dans [`requirements.txt`](requirements.txt). Pyogrio fournit l'accès
GDAL aux GeoPackage, Shapefile et GeoJSON sans nécessiter Fiona. Si `pip`
tente de compiler GDAL au lieu de télécharger une roue, vérifier que la
version de Python est prise en charge et que `pip` est à jour.

## Inputs

Formats acceptés :

- GeoJSON : `.geojson` ou `.json` ;
- ESRI Shapefile : `.shp` et ses fichiers compagnons ;
- GeoPackage : `.gpkg`.

Pour sélectionner une couche GeoPackage :

```text
donnees.gpkg::nom_de_la_couche
```

Un fichier unique avec identifiant et variable de calcul est conseillé. Le
script accepte néanmoins plusieurs fichiers et les fusionne après reprojection
vers le CRS du premier. Tous doivent posséder le champ donné à `--attribute`
et, s'il est indiqué, celui donné à `--id-field`.

`--id-field` valide la présence du champ, l'absence de valeurs nulles et son
unicité dans chaque fichier; celui-ci est conservé tel quel. Le programme
conserve également toutes les autres colonnes et ajoute :

- `src_id` : identifiant natif/FID lu par GeoPandas ;
- `src_file` : chemin du fichier source.

Si ces noms existent déjà, des préfixes `_` sont ajoutés afin de ne jamais
écraser les colonnes utilisateur.

Seuls les `Polygon` et `MultiPolygon` contribuent à la densité. Les points et
lignes éventuellement présents sont déformés et exportés, mais ne contribuent
pas au calcul.

### Quantité ou densité

Par défaut, `--attribute population` signifie une **quantité extensive**. Pour
chaque entité :

```text
densité = population / aire courante
```

Si le champ contient déjà une valeur intensive, par exemple des habitants par
km², ajouter `--attribute-is-density`. Le programme la convertit en masse
interne (`densité × aire initiale`) afin que plusieurs itérations conservent la
même quantité par territoire.

Un pourcentage ou ratio n'est généralement **pas** une densité surfacique. Les
trois choix donnent des cartes différentes :

| Objectif | Variable | `ATTRIBUTE_IS_DENSITY` |
|---|---|---:|
| Surface proportionnelle au nombre d'électeurs | `eligible_voters` | `False` |
| Surface proportionnelle au nombre de votes « oui » | `yes_votes` | `False` |
| Chaque commune reçoit un poids égal, modulé seulement par son taux de oui | `yes_percent` | `False` |
| Masse égale à `yes_percent × surface géographique initiale` | `yes_percent` | `True` |

La dernière option est mathématiquement valide, mais rarement pertinente pour
une votation : deux communes ayant le même taux obtiennent des masses
différentes uniquement parce que leurs superficies terrestres diffèrent. Elle
convient seulement si `yes_percent` est réellement interprété comme une
densité par unité de surface. Pour une carte du poids électoral du « oui »,
`yes_votes` est le choix recommandé.

Les valeurs doivent être numériques, finies, positives ou nulles, avec au
moins une valeur strictement positive.

### Couches auxiliaires et topologie

`AUXILIARY_FILES` ou l'option répétable `--aux-layer` ajoute des couches de
contexte qui ne contribuent pas à la densité. Elles sont densifiées et passent
par exactement les mêmes transformations successives que la couche maître.

Par défaut, `THEMATIC_EXTENT_ONLY = True` calcule l'emprise de diffusion depuis
la seule bbox thématique, puis ajoute la marge. Les parties auxiliaires encore
comprises dans cette emprise avec marge sont déformées; celles qui restent
réellement en dehors sont conservées à leur position plutôt que rabattues sur
le bord.

Avec `THEMATIC_EXTENT_ONLY = False`, l'emprise est recalculée à chaque
itération sur l'union des bounding boxes thématique et auxiliaires, avant
d'ajouter la marge. Toutes les couches auxiliaires se trouvent alors dans le
domaine diffusé. Dans le jeu de test, l'union explicite inclut notamment les
extensions de `Bodensee` et `Lago Maggiore`.

Équivalent CLI :

```bash
--include-auxiliary-extent
```

Exemple avec les lacs :

```bash
--aux-layer data/lakes.gpkg::lakes
```

Dans le GeoPackage de sortie, la couche s'appelle `aux_lakes`. Ses attributs et
son FID (`src_id`) sont conservés.

La transformation est un champ continu et identique pour toutes les couches :
des coordonnées initialement identiques restent donc identiques, ce qui
préserve normalement les contacts et la cohérence visuelle. Ce mécanisme est
l'équivalent des « simultaneously transformed layers » de ScapeToad. Il ne
constitue toutefois pas un moteur topologique SIG formel : des sources déjà
mal ajustées, des frontières presque mais pas exactement communes, ou des
déformations extrêmes peuvent encore produire des écarts. Le rapport JSON
indique pour chaque couche auxiliaire le nombre de géométries valides et vides.

Éviter les couches auxiliaires dont l'emprise est beaucoup plus grande que la
zone thématique. À `GRID_SIZE` constant, agrandir fortement la bbox augmente la
taille géographique de chaque cellule, réduit la résolution effective sur la
zone utile, accroît le fond à densité moyenne et peut atténuer la déformation.
Il vaut mieux découper une couche contextuelle à une zone raisonnablement
proche, ou augmenter `GRID_SIZE` en surveillant mémoire et temps de calcul. Le
rapport JSON expose `initial_extents.thematic_bounds`, `auxiliary_bounds`,
`combined_bounds`, `selected_bounds`, `strategy` et
`diffusion_bounds_with_margin` pour contrôler ce point.

## Outputs

Les mêmes familles de formats sont disponibles en sortie.

### Nommage automatique

Si `OUTPUT_FILE` et `--output` sont omis, le script crée un GeoPackage à côté
du premier input selon la convention snake_case :

```text
<fichier_source>_<variable>_grid_<taille>_iter_<iterations>.gpkg
```

Exemples :

```text
communes_population_grid_128_iter_1.gpkg
voge_voters_eligible_voters_grid_256_iter_3.gpkg
```

Les espaces, accents et signes sont normalisés pour produire un nom portable.
Pour plusieurs inputs, `_merged` est ajouté après le nom du premier fichier.
Un `OUTPUT_FILE` ou `--output` explicite conserve toujours la priorité.

### GeoPackage recommandé

```bash
python pyscapetoad.py input.gpkg::zones -a population -o result.gpkg
```

Les deux couches sont écrites dans `result.gpkg`.

### Grille visuelle et marge de calcul

La marge de 1,5 autour des données est nécessaire aux conditions aux limites
de la diffusion. La supprimer du calcul peut repousser ou écraser les
territoires situés au bord. Elle n'a cependant pas besoin d'être affichée.

Le mode par défaut combine donc :

```python
GRID_EXPORT_MODE = "lines"
GRID_CROP_TO_INPUT = True
```

Il produit quelques centaines de lignes déformées au lieu de dizaines de
milliers de polygones et exclut la marge extérieure de la couche exportée. La
grille montre comment l'espace régulier a été étiré ou contracté :

- lignes écartées après transformation : expansion locale ;
- lignes rapprochées : contraction locale ;
- lignes courbes/inclinées : direction du déplacement.

Avec plusieurs itérations, chaque transformation est appliquée au maillage de
référence initial. L'export montre donc la déformation totale, et non la seule
correction de la dernière passe — qui serait normalement presque régulière.

Pour analyser la densité de chaque cellule :

```bash
--grid-export-mode cells
```

Les cellules possèdent alors `cell_id`, `row`, `col`, `density` et
`iteration`. Pour exporter aussi la marge complète :

```bash
--full-grid-extent
```

Pour la sortie la plus légère possible :

```bash
--grid-export-mode none
```

### GeoJSON ou Shapefile

```bash
python pyscapetoad.py input.geojson -a population -o result.geojson
```

Cela produit `result.geojson` et `result_grid.geojson`. Un chemin différent
peut être imposé avec `--grid-output`. Le rapport de contrôle est écrit dans
`result_report.json`, ou au chemin donné par `--report-output`.

Le Shapefile impose ses limitations habituelles, notamment les noms de champs
courts et l'absence de plusieurs couches dans un seul fichier. GeoPackage est
donc préférable pour préserver les schémas modernes.

### Contrôle de la proportionnalité des surfaces

La couche `cartogram` contient les indicateurs suivants pour chaque entité :

| Champ | Signification |
|---|---|
| `cg_a_orig` | Surface avant déformation |
| `cg_a_cart` | Surface obtenue dans le cartogramme |
| `cg_a_targ` | Surface théorique cible |
| `cg_vshare` | Part de la variable/masse totale, entre 0 et 1 |
| `cg_ashare` | Part de la surface finale, entre 0 et 1 |
| `SizeError` | Indicateur compatible avec ScapeToad, idéal = 100 |
| `cg_ratio` | Surface obtenue / surface cible, idéal = 1 |
| `cg_relerr` | Erreur de surface signée en pour cent |
| `cg_abserr` | Valeur absolue de l'erreur précédente |
| `cg_status` | `on_target`, `too_small`, `too_large` ou `no_target` |
| `cg_quality` | Classe `excellent`, `good`, `acceptable`, `poor` ou `very_poor` |

Les surfaces sont calculées dans le CRS projeté de travail et restent dans ces
unités carrées même lorsque les géométries sont reprojetées vers EPSG:4326 en
sortie.

La formule originale de ScapeToad se simplifie en :

```text
SizeError = 100 × (part de la variable / part de la surface finale)
```

Interprétation :

- `100` : surface exactement proportionnelle à la variable ;
- `120` : territoire encore trop petit par rapport à sa cible ;
- `80` : territoire trop grand par rapport à sa cible.

L'erreur signée complémentaire est plus intuitive :

```text
cg_relerr = 100 × (surface finale - surface cible) / surface cible
```

Elle vaut donc `+20` pour une surface 20 % trop grande et `-20` pour une
surface 20 % trop petite. Une entité dont la variable cible vaut zéro n'a pas
d'erreur relative définie; ses champs `cg_relerr` et `cg_abserr` sont nuls ou
non définis selon le format de sortie et elle est exclue des statistiques
relatives globales.

`cg_ratio` donne la même information sous forme de rapport :

- `1.00` : cible atteinte ;
- `1.20` : surface 20 % trop grande ;
- `0.80` : surface 20 % trop petite.

Les classes `cg_quality` utilisent l'erreur absolue :

| Classe | Écart à la surface cible |
|---|---:|
| `excellent` | ≤ 5 % |
| `good` | > 5 % et ≤ 10 % |
| `acceptable` | > 10 % et ≤ 20 % |
| `poor` | > 20 % et ≤ 50 % |
| `very_poor` | > 50 % |

Le rapport JSON fournit notamment :

- moyenne, écart-type et quartiles du `SizeError` ;
- erreur absolue moyenne, médiane et maximale ;
- pourcentage d'entités à moins de 5 %, 10 % et 20 % de leur cible ;
- corrélation de Pearson entre variable et surface ;
- nombres d'entités évaluables ou de cible nulle ;
- CRS de calcul et paramètres principaux.

Exemple de contrôle rapide :

```bash
python pyscapetoad.py communes.gpkg::communes \
  -a population --id-field commune_id \
  -o resultat.gpkg --report-output controle.json
```

Le terminal affiche aussi le `SizeError` moyen et l'erreur absolue médiane à la
fin du calcul. La moyenne de `SizeError` seule peut masquer des écarts positifs
et négatifs : il est conseillé de regarder également `cg_abserr`, les quartiles
et les seuils du rapport.

### Évaluer visuellement le résultat

Dans QGIS ou un autre SIG :

1. ouvrir la couche `cartogram` ;
2. appliquer un style catégorisé sur `cg_quality` pour repérer immédiatement
   les unités mal ajustées ;
3. appliquer un style gradué divergent sur `cg_relerr`, centré sur zéro, pour
   distinguer les territoires trop petits des territoires trop grands ;
4. afficher `deformation_grid` au-dessus, avec un trait fin sans remplissage ;
5. inspecter `cg_a_cart`, `cg_a_targ` et `cg_ratio` dans l'infobulle d'une
   unité problématique.

La mesure principale d'exactitude par unité est `cg_abserr`. Pour comparer
deux paramétrages, utiliser en priorité la médiane de `cg_abserr`, les parts
`within_10_percent` et `within_20_percent` du rapport, puis la corrélation
surface–variable. Une corrélation élevée ne garantit pas que chaque petite
unité soit précise; elle doit toujours être lue avec les erreurs individuelles.

### Ce que signifie « exactitude » ici

La cible d'une unité est calculée indépendamment de sa forme finale :

```text
surface_cible = (valeur_unité / somme_des_valeurs) × surface_totale_finale
```

Les champs de contrôle comparent ensuite la surface réellement mesurée dans le
CRS projeté à cette cible. Ils évaluent donc directement l'objectif
mathématique du cartogramme : rendre les surfaces proportionnelles à la
variable.

Ces indicateurs ne valident pas :

- la qualité ou l'actualité de la variable source ;
- la pertinence statistique du découpage géographique ;
- la facilité de reconnaissance visuelle des territoires ;
- l'absence de toute distorsion locale le long des frontières.

Le solveur reste une approximation sur grille. Les petites unités, les valeurs
très faibles et les contrastes extrêmes sont les plus difficiles. Une grille
plus fine et plusieurs itérations réduisent généralement l'erreur, au prix de
plus de calcul et de sommets.

### Résultat de référence `voge_voters`

Avec `GRID_SIZE = 256` et `CARTOGRAM_ITERATIONS = 3` :

- 2 105 géométries sur 2 105 sont valides ;
- erreur absolue médiane : 12,70 % ;
- 42,09 % des unités sont à moins de 10 % de leur cible ;
- 64,70 % sont à moins de 20 % ;
- corrélation surface–`eligible_voters` : 0,9989 ;
- `cg_quality` : 516 `excellent`, 370 `good`, 476 `acceptable`, 482 `poor`
  et 261 `very_poor`.

La grille visuelle cumulative recadrée contient 282 lignes, contre 65 536
polygones pour la grille cellulaire complète. Le GeoPackage léger mesuré fait
environ 5 Mo.

## Projections et CRS

La diffusion est un calcul euclidien : distances et surfaces doivent être
mesurées dans un **CRS projeté**. Tous les CRS projetés reconnus par PROJ/
GeoPandas sont utilisables, par exemple :

- `EPSG:2056` pour la Suisse ;
- un CRS national équivalent ou conforme adapté au pays étudié ;
- une projection égale-aire appropriée lorsque la conservation/interprétation
  des surfaces est prioritaire.

`EPSG:4326` est accepté comme CRS d'entrée et de sortie parce qu'il est très
courant pour GeoJSON, mais il n'est pas utilisé directement pour la diffusion :
les degrés ne sont pas des unités de distance ou de surface. Si l'entrée est
géographique, le script estime automatiquement une zone UTM, calcule dans ce
CRS, puis reprojette le résultat vers le CRS original.

Pour les données couvrant plusieurs zones UTM, un pays entier très étendu ou le
monde, fournir explicitement un CRS de travail adapté :

```bash
python pyscapetoad.py world.gpkg::countries \
  -a population -o world_cartogram.gpkg \
  --working-crs ESRI:54009
```

`--keep-working-crs` conserve le résultat dans le CRS de calcul. Sans cette
option, le CRS de sortie est celui du premier input.

## Méthode de calcul

### Classes Java étudiées

Le portage a été isolé à partir de quatre classes de `ScapeToad/src/` :

- `CartogramGrid.java` : grille, densités et emprise ;
- `CartogramNewman.java` : DCT, solution spectrale de la diffusion, champ de
  vitesse et Runge–Kutta ;
- `CartogramGastner.java` : autre implémentation FFT, marge, biais de densité,
  interpolation et projection ;
- `CartogramFeature.java` : densification et projection des sommets.

Le code Swing/AWT, les assistants, JUMP/JTS et le parsing Java des Shapefiles
n'ont pas été repris.

### Méthodes disponibles

| Méthode | État dans ce projet |
|---|---|
| Newman par DCT (`CartogramNewman`) | Solveur effectivement utilisé |
| Gastner historique avec FFT mixtes (`CartogramGastner`) | Étudié pour l'emprise, le biais et l'interpolation; pas exposé comme second solveur |
| Raffinement par passes successives | Extension Python via `--iterations` |
| Déformation contrainte ScapeToad | Non implémentée |

Il n'y a donc pas de sélecteur `--method` dans cette version : le calcul actif
est toujours le solveur Newman/DCT, qui est aussi celui appelé par
`Cartogram.java` dans le ScapeToad fourni.

### Densité raster

La fonction `compute_density` construit une matrice NumPy `(ny, nx)`. Pour une
variable extensive, chaque intersection entité–cellule contribue :

```text
masse_intersection = valeur_entité × aire_intersection / aire_entité
```

Puis :

```text
densité_cellule = masse_cellule / aire_cellule
```

Les parties vides de l'emprise reçoivent la densité moyenne pondérée. Un petit
plancher relatif (`--density-floor`) empêche les divisions par zéro.

Cette rasterisation par aire est une amélioration volontaire par rapport au
chemin actif de `CartogramGrid.fillDensityValueWithFeature`, qui affecte
principalement une cellule selon son point central. Elle conserve mieux la
masse, au prix d'intersections Shapely plus coûteuses.

### Diffusion Gastner–Newman

La densité initiale est transformée avec une DCT 2D :

```python
rho_hat = scipy.fft.dctn(rho, type=2, norm="ortho")
```

La solution spectrale de l'équation de la chaleur est :

```text
rho_hat(k, t) = exp(-(kx² + ky²)t) × rho_hat(k, 0)
```

La DCT représente des bords réfléchissants (flux normal nul), comme dans
`CartogramNewman`. Le champ de vitesse est calculé avec le stencil de quatre
cellules inspiré de Newman :

```text
v = -grad(rho) / rho
```

Les nœuds de grille sont transportés par Runge–Kutta d'ordre 4. L'erreur est
estimée en comparant un grand pas à deux demi-pas; le pas est rejeté ou augmenté
de façon adaptative, avec un facteur maximal de 4. Une correction d'ordre
supérieur est appliquée comme dans le Java.

Enfin, les segments Shapely sont densifiés puis leurs sommets sont déplacés par
interpolation bilinéaire du maillage déformé.

### Ce qui est retranscrit et ce qui est adapté

Ce n'est pas une traduction ligne à ligne :

- `DoubleDCT_2D` de JTransforms est remplacé par `scipy.fft` avec normalisation
  orthonormale. La normalisation absolue diffère, mais elle s'annule dans
  `-grad(rho)/rho` ;
- les tableaux et boucles Java sont vectorisés avec NumPy lorsque cela améliore
  nettement les performances ;
- l'intégrateur reprend le principe RK4 adaptatif de Newman, mais avec une
  condition d'arrêt explicite (`--convergence`) et `--max-steps`, plutôt que
  d'attendre un déplacement flottant exactement nul ;
- le flou optionnel est appliqué comme un temps initial spectral
  (`t = blur²/2`) ;
- les couches de déformation contrainte, couches esclaves séparées et légendes
  de l'interface ScapeToad ne sont pas implémentées ;
- la grille exportée compose toutes les passes sur le maillage régulier de la
  première itération; en mode `cells`, le champ `density` correspond donc à la
  densité de cette grille de référence initiale.

### Itérations de cartogramme

`--iterations N` répète le pipeline complet :

1. recalcul de `valeur / aire courante` ;
2. rasterisation ;
3. diffusion ;
4. déformation de la géométrie obtenue à la passe précédente.

Une passe est généralement suffisante. Des passes supplémentaires corrigent
les écarts dus à la résolution du raster et à l'interpolation, mais augmentent
le temps de calcul et le nombre de sommets. Des valeurs de 2 ou 3 sont un point
de départ raisonnable; davantage peut amplifier les artefacts numériques.

Dans le ScapeToad fourni, `CartogramNewman.compute()` est appelé une fois. Un
ancien champ `mDiffusionIterations` existe dans `Cartogram.java`, mais il est
commenté. Les itérations externes de ce script sont donc une extension
explicite, pas la copie d'une boucle Java active.

Ne pas confondre :

- `--iterations` : passes complètes du cartogramme ;
- `--max-steps` : limite interne des pas temporels adaptatifs d'une diffusion.

## Exemples CLI complets

Électeurs éligibles, grille 256 et trois passes :

```bash
python pyscapetoad.py \
  data/voge_voters.gpkg::voge_voters \
  --id-field vogeId \
  --attribute eligible_voters \
  --working-crs EPSG:2056 \
  --grid-size 256 \
  --iterations 3 \
  --grid-export-mode lines \
  --verbose
```

Nombre de votes « oui » et lacs simultanément déformés :

```bash
python pyscapetoad.py \
  data/voge_voters.gpkg::voge_voters \
  --aux-layer data/lakes.gpkg::lakes \
  --id-field vogeId \
  --attribute yes_votes \
  --working-crs EPSG:2056 \
  --grid-size 256 \
  --iterations 3 \
  --grid-export-mode lines \
  --verbose
```

Test exploratoire où `yes_percent` est traité comme une densité surfacique :

```bash
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
```

Pour 512×512 et six passes, remplacer simplement les deux paramètres :

```bash
--grid-size 512 --iterations 6
```

Sans `--output`, chaque commande utilise le nom automatique décrit plus haut.

## Paramètres principaux

| Paramètre | Rôle | Défaut |
|---|---|---:|
| `--id-field` | Champ identifiant à vérifier et conserver | FID natif |
| `--aux-layer` | Couche de contexte à déformer; option répétable | aucune |
| `--attribute`, `-a` | Quantité/densité utilisée | obligatoire |
| `--output`, `-o` | Chemin explicite, sinon nom automatique | automatique |
| `--attribute-is-density` | Interprète le champ comme densité | faux |
| `--grid-size`, `-n` | Cellules par axe | 128 |
| `--iterations` | Passes complètes | 1 |
| `--report-output` | Rapport JSON de contrôle | `<output>_report.json` |
| `--grid-export-mode` | `lines`, `cells` ou `none` | `lines` |
| `--full-grid-extent` | Inclut la marge de calcul exportée | faux |
| `--include-auxiliary-extent` | Étend la bbox de diffusion aux couches auxiliaires | faux |
| `--working-crs` | Projection plane de calcul | automatique |
| `--margin` | Emprise de calcul autour des données | 1.5 |
| `--density-floor` | Plancher relatif de densité | 0.001 |
| `--blur` | Lissage spectral initial, en cellules | 0 |
| `--integration-tolerance` | Tolérance du RK adaptatif | 0.01 |
| `--convergence` | Déplacement final maximal, en cellule | 1e-5 |
| `--max-steps` | Pas temporels acceptés par passe | 500 |
| `--max-segment-length` | Densification, unités du CRS de calcul | 1/2 cellule |

Tous les paramètres sont visibles avec :

```bash
python pyscapetoad.py --help
```

## Compromis pratiques

- Une grille plus fine décrit mieux les petites entités, mais son coût mémoire
  croît comme `n²` et les intersections de rasterisation prennent plus de
  temps.
- Plusieurs itérations et une densification fine améliorent la continuité des
  limites, mais produisent davantage de sommets.
- Les intersections surfaciques favorisent la conservation de la masse, mais
  sont plus lentes qu'une rasterisation au centre des cellules.
- Les fortes disparités de valeurs peuvent créer des cellules très étirées. Le
  plancher de densité et le lissage réduisent ce risque, au prix d'un résultat
  un peu moins extrême.
- La qualité surfacique dépend du CRS de travail. L'UTM automatique est adapté
  à une emprise locale, pas à une analyse mondiale.

## Licence des données de démonstration

Les deux GeoPackages du dossier `data/` sont fournis comme données sources de
démonstration. Leur inclusion dans un dépôt public ne transfère ni ne modifie
les droits attachés aux données d'origine. Avant réutilisation ou
redistribution, vérifier les conditions de leurs producteurs respectifs.

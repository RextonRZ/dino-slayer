# The dataset

Everything the dashboard reads, where each number came from, and how the score was built.

All of it is open data. Nothing here is imputed, smoothed or invented. Where a value is
missing it stays missing, and the dashboard renders that as a sentence rather than a zero.

---

## What is in here

```
boundaries/     GADM administrative polygons
network/        Ookla speed test tiles, four quarters of 2025
settlements/    the pipeline, from raw settlements to final DIPI
ml/             training table for the coverage model, plus its guide
web/            GeoJSON the browser actually loads
```

| File | Rows | What it is |
|---|---|---|
| `network/ookla_sabah_2025q{1,2,3,4}.parquet` | 4,971 / 5,071 / 5,060 / 5,499 | Ookla fixed broadband tiles clipped to Sabah, one file per quarter |
| `settlements/settlements_sabah_01_base.parquet` | 1,448 | OSM settlement points plus population, wealth, water and elevation |
| `settlements/settlements_sabah_02_features.parquet` | 1,448 | The above, joined to Ookla and to facility counts |
| `settlements/settlements_sabah_03_dipi.parquet` | 1,448 | The above, plus the four pillars, DIPI, rank and the Queue B ranking |
| `settlements/facilities_sabah_osm.parquet` | 606 | OSM schools, clinics, hospitals and doctors in Sabah |
| `boundaries/gadm41_MYS_2.json` | 144 total, 25 in Sabah | GADM level 2, all Malaysian districts |
| `web/dipi.geojson` | 1,448 | The settlement layer the map draws |
| `web/facilities.geojson` | 606 | The facilities layer |
| `web/sabah_districts.geojson` | 25 | District polygons, trimmed to what the map needs |
| `web/sabah_divisions.geojson` | 5 | Districts dissolved into the five official divisions |
| `ml/training_table.csv` | 1,448 | Features, terrain and a pre-assigned split for the coverage model |
| `ml/fold_assignment.csv` | 1,448 | The five spatial folds, frozen before any model was fitted. 850 training rows, 598 marked -1 |
| `ml/metrics.json` | | Raw model run output: MAE, RMSE, R2, ablations, and all six biased districts |
| `ml/model_ablations.json` | | The curated view of the above. Five models, four rejected, with the reason for each |
| `ml/model_predictions_v1.csv` | 1,448 | Estimates, spread and top three factors for the 216 unmeasured settlements |
| `ml/measurement_priority_v1.csv` | 111 | Survey targeting, offline. See the note below |
| `ml/survey_routes_v1.csv` | 14 | Per-district visiting order for the settlements a measurement would actually settle. Straight line, no road network, so a lower bound |
| `ml/clusters.json` | 323 | Fibre bundles and each settlement's spanning-tree spur |
| `ml/cluster_sensitivity.json` | | What the bundling does at `min_cluster_size` 3 to 10. Not a plateau, and it says so |
| `ml/tower_pairs.csv` | 10,070 | Every candidate mast to village path, distance only |
| `ml/tower_pairs_los.csv` | 10,070 | The same paths with the SRTM terrain screen applied |
| `ml/tower_scenarios.json` | | Mast counts by assumed radius, distance only |
| `ml/tower_los_scenarios.json` | | Mast counts after the line-of-sight and Fresnel screen |
| `ml/tower_isolated.csv` | 449 | Settlements only a mast in their own village can reach |
| `ml/tower_isolated_power.csv` | 449 | The above plus `ever_lit`, giving the 56 that need their own mast and their own power |
| `ml/viirs_annual_max1km.csv` | 18,824 | Thirteen years of nighttime radiance, 1,448 settlements x 13 years |
| `ml/viirs_trend.csv` | 1,448 | Peak radiance, trend class, and the lit/unlit split |
| `web/power.json` | 703 unlit | The night view and the power flag, published from the two files above |
| `web/towers_los.json` | | The screened mast sites and paths the map draws |
| `web/clusters.json` | 323 | The bundling, as the dashboard reads it |
| `web/sources.json` | 20 sources | Every published figure with its quote, page and how far it was verified |

`sabah_divisions.geojson` is generated once, offline, by unioning district polygons per
division. It is committed so the page never has to run a geometry library at load time.

---

## Where each number comes from

| Column | Source | Licence | How it was derived |
|---|---|---|---|
| `name`, `place`, `geometry` | [OpenStreetMap](https://www.openstreetmap.org/copyright) | ODbL | Nodes tagged `place` in city, town, village or hamlet, within Sabah |
| `dl_mbps`, `ul_mbps`, `latency_ms` | [Ookla Open Data](https://github.com/teamookla/ookla-open-data) fixed tiles, 2025 Q1 to Q4 | CC BY-NC-SA 4.0 | Median across every tile intersecting the settlement, weighted by tests |
| `n_tests`, `n_tiles` | Ookla | CC BY-NC-SA 4.0 | How much measurement stands behind the speed. These decide the evidence tier |
| `pop_2km` | [WorldPop](https://www.worldpop.org/) 100 m constrained | CC BY 4.0 | Sum of population raster inside a 2 km buffer |
| `n_schools_3km`, `n_clinics_3km` | OpenStreetMap | ODbL | Count of OSM facility points inside a 3 km buffer |
| `rwi` | [Meta Relative Wealth Index](https://dataforgood.facebook.com/dfg/tools/relative-wealth-index) | CC BY 4.0 | Nearest RWI cell. Higher is wealthier. 96 settlements have no RWI cell |
| `seasonal_water_px`, `flood_prone` | [JRC Global Surface Water](https://global-surface-water.appspot.com/) | EC JRC / Google | Seasonal water pixels near the point. 577 flagged |
| `elevation_m` | [NASA SRTM](https://www.earthdata.nasa.gov/data/instruments/srtm) | Public domain | Sampled at the point. Runs -2 m to 1,510 m |
| `_district`, `_division` | [GADM 4.1](https://gadm.org/) | Free for academic use | Not stored in the file. The dashboard derives it at load by point in polygon |

**Two warnings that matter more than they look.**

`pop_2km` buffers overlap, so these values must never be summed. Two villages 1 km apart
share most of their buffer, and adding them double counts the same people. The dashboard
reports settlement counts and medians instead, never a total population.

`n_schools_3km` and `n_clinics_3km` are buffer counts, not catchments. A school 3 km away
may serve an entirely different village. A zero means none mapped in OpenStreetMap, which
in rural Sabah is not the same as none present.

---

## Terrain

Telecom GeoAI is usually framed as three layers: network performance, physical landscape,
and human demand. Ookla is the first, WorldPop and RWI are the third, and elevation is the
second. Three terrain values are derived from `elevation_m`, identically in the dashboard,
the agent and `export_training_table.py`, so no two of them can quote different numbers.

| Derived | Meaning |
|---|---|
| `backhaul_km` | Distance to the nearest of the 59 OSM towns and cities. A stand-in for distance to backhaul, not a survey of where fibre terminates |
| `elev_drop_m` | Metres below (negative) or above that town. Runs -781 m to +1,029 m |
| `elev_pct_district` | Elevation percentile inside its own district, so "high" is judged against the local area rather than sea level |

**Terrain never enters DIPI.** It is context, exactly like the flood layer. It explains why
a measured link may be slow and it qualifies a siting recommendation, but it does not move
a settlement up or down the queue.

**How much weight it deserves, measured rather than asserted.** Against the 1,114 scored
settlements, Spearman correlation with measured download speed:

| Feature | vs `dl_mbps` |
|---|---|
| `elevation_m` | **-0.25** |
| `backhaul_km` | -0.10 |
| `elev_drop_m` | -0.08 |

Raw elevation is the strongest of the three and beats the distance-to-town proxy the
recommender already uses. The drop is weak, so the product treats it as a **siting caveat**
and never as a predictor: 165 settlements sit 150 m or more below their nearest town, and
132 of those are in Ranau alone.

**What cannot be done with this data.** These are point elevations, not a surface. No
line-of-sight, Fresnel-zone or propagation calculation is possible from them, and none is
claimed anywhere in the product. A real path-loss model needs the SRTM raster, which is not
committed here. The dashboard's optional hillshade layer streams that raster from AWS
Terrain Tiles for display only; nothing is computed from it.

---

## How DIPI is built

DIPI is a weighted sum of four pillars, on a 0 to 100 scale, where higher means screen
this settlement sooner.

```
DIPI = 100 * (0.40 * p_connectivity
            + 0.25 * p_population
            + 0.15 * p_institutions
            + 0.20 * p_equity)
```

Each pillar is the **percentile rank** of its input across the 1,114 scored settlements,
so every pillar is uniform on 0 to 1 by construction and no single outlier can flatten the
scale for everyone else.

| Pillar | Input | Rank direction |
|---|---|---|
| `p_connectivity` | `dl_mbps` | Ascending inverted, so slower ranks higher |
| `p_population` | `pop_2km` | Descending, so more people ranks higher |
| `p_institutions` | `n_schools_3km + n_clinics_3km` | Descending |
| `p_equity` | `rwi` | Ascending inverted, so poorer ranks higher |

### Verifying that, without trusting this document

Everything above is re-derivable from the shipped file. These checks pass on
`settlements_sabah_03_dipi.parquet` as committed:

```python
import pandas as pd, numpy as np
df = pd.read_parquet("dataset/settlements/settlements_sabah_03_dipi.parquet")
s = df[df.dipi.notna()]

# 1. the weights, recovered by least squares against the stored DIPI
A = s[["p_connectivity", "p_population", "p_institutions", "p_equity"]].values
w, *_ = np.linalg.lstsq(A, s.dipi.values, rcond=None)
print(w.round(2))                      # [40.00 25.00 15.01 20.00], sums to 100
print(abs(A @ w - s.dipi).max())        # 0.052, the file stores DIPI rounded to 1 dp

# 2. every pillar is a percentile rank of its own input
print(s.p_connectivity.corr((-s.dl_mbps).rank(pct=True)))                   # 1.0000
print(s.p_population.corr(s.pop_2km.rank(pct=True)))                        # 1.0000
print(s.p_equity.corr((-s.rwi).rank(pct=True)))                             # 1.0000
print(np.allclose(s.p_institutions,
      (s.n_schools_3km + s.n_clinics_3km).rank(pct=True)))                  # True

# 3. the evidence tier rule
tier = np.where((df.n_tests >= 20) & (df.n_tiles >= 3), "measured",
        np.where(df.n_tests >= 5, "low_evidence", "insufficient"))
print((tier == df.evidence_tier).mean())                                    # 1.0
```

Observed ranges on the shipped file: DIPI runs 20.2 to 76.6. Connectivity correlates
-0.886 with download speed and equity correlates -0.967 with RWI, both in the direction
the table above claims.

### The pipeline scripts

The notebooks that produced `settlements_sabah_01/02/03.parquet` are not committed. The
Parquet files are the artefact of record, which is why the checks above exist: the method
is verifiable from the output whether or not you have the code that made it. The two
export scripts that turn Parquet into what the browser and the model consume **are** here:

```bash
python dataset/export_facilities.py        # facilities parquet  -> web/facilities.geojson
python dataset/export_training_table.py    # dipi parquet        -> ml/training_table.csv
```

---

## Evidence tiers

A settlement is scored only if enough people have actually run a speed test near it.

| Tier | Rule | Count | Median tests | In the product |
|---|---|---|---|---|
| `measured` | `n_tests >= 20` and `n_tiles >= 3` | 850 | 148 | Scored, ranked, drawn as a solid dot |
| `low_evidence` | `n_tests >= 5` | 264 | 11 | Scored, but drawn with a detached amber ring and flagged for field validation |
| `insufficient` | everything else | 334 | 0 | **Never scored.** Hollow grey ring, ranked separately |

The 334 insufficient settlements are Queue B. They carry `stakes_score` (28.9 to 97.1) and
`gap_rank`, which rank them by how much would be at stake **if** they turn out to be badly
served. That is a survey priority, not a needs score, and the dashboard never renders it
as a DIPI.

This is the line the whole project is built on. A settlement with no Ookla samples is a
settlement nobody has tested. It is not a settlement with no coverage, and the tool is
built to refuse that inference on your behalf.

---

## The coverage model table (`ml/`)

`training_table.csv` is the handoff to whoever trains the coverage model. It has all 1,448
settlements with the geographic features and a pre-assigned `split`:

| Split | Rows | Purpose |
|---|---|---|
| `train` | 850 | Measured tier. Fit on these |
| `validate` | 264 | Low evidence tier. Held out for honest error bars |
| `check` | 118 | Held back from training entirely, for a final unseen check |
| `predict` | 216 | Insufficient tier. No target exists. These are what the model is for |

`dl_mbps` is null on every `predict` row by definition. `evidence_tier_REFERENCE_ONLY` is
there for auditing and **must not be used as a feature**, it leaks the target.

Two things are not optional, and both are recorded in [ml/model_ablations.json](ml/model_ablations.json):

- **Group your folds by district.** 29% of settlements share an exact download speed with
  at least one other settlement, because they read from the same Ookla tile. Random k-fold
  puts the same tile on both sides of the split and reports an accuracy that does not exist.
- **Never predict DIPI, predict `dl_mbps`.** DIPI is a weighted sum that already contains
  connectivity. A model trained to predict DIPI from its own components learns the weights
  and reports a fit that means nothing.

**How the survey queue is ranked.** `ml/measurement_priority_v1.csv` gates on whether a
measurement could cross the 21 Mbps line, and `web/survey.json` publishes it to the
dashboard. It covers 111 of the 334, because decisiveness needs both an estimate and a
population to serve, so the panel ranks three groups apart rather than blending them: the 14
whose interval crosses the line, then the 223 nothing is known about by stakes, then the 97
whose estimate already sits clear of it. The last group is last on purpose. Confirming what
you already believe is the least useful trip a field team can make.

---

## Citing this

If you use the derived dataset, cite the upstream sources, not us. The DIPI score is our
construction and can be cited as:

> Dino Slayer (2026). *Digital Inclusion Priority Index for Sabah, Malaysia.* Derived from
> Ookla Open Data 2025 Q1 to Q4, OpenStreetMap, WorldPop, Meta Relative Wealth Index,
> JRC Global Surface Water, NASA SRTM and GADM 4.1. ASEAN GeoAI Fusion 2026.

Ookla Open Data is **CC BY-NC-SA 4.0**, which is non commercial and share alike. Any
redistribution of `network/*.parquet` or anything derived from it carries those terms.

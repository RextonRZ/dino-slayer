# Dino Slayer: system information

**ASEAN GeoAI Fusion 2026, theme Consumer Empowerment**
**Area of interest: Sabah, Malaysia. 1,448 settlements.**

> Screening for further assessment, not a coverage determination.

This document describes what the system is, what it does, and how it is built. It is the
companion to [IMPLEMENTATION.md](../IMPLEMENTATION.md), which covers the modelling pipeline in
depth, and to [how_it_works.md](how_it_works.md), which walks the product screen by screen and
traces every number on it to a line of code.

Every figure here is recomputed from a file in this repository. Where a number is ours rather
than published, it says so.

---

## 1. The problem

### 1.1 The gap between coverage and service

Malaysia reports near-universal mobile coverage across populated areas. That statistic is not
wrong, and it is also not the thing a planner needs. **Coverage is whether a signal reaches a
place. Service is whether a person there can do something useful with it.** A village inside a
coverage polygon whose measured download is 1.8 Mbps, shared across a household, cannot hold a
video call or load a school portal.

The people who allocate universal-service money at MCMC, and the ministries that run schools
and clinics, have to answer a narrower and harder question: **which communities should be
validated first, and with what evidence.**

### 1.2 Why that question is hard to answer today

The open evidence that could answer it exists, but it was never designed to work together.
Speed measurements are crowdsourced tiles. Population is a modelled raster. Wealth is a grid
of index values. Schools are contributor-mapped points. Terrain is a global elevation raster.
Each is in a different format, a different resolution, and a different coordinate system, and
none of them is organised around the unit a planner actually funds: **a settlement.**

### 1.3 The harder problem underneath, and the one that shapes the whole design

**334 of 1,448 settlements have no usable measurement at all.**

That is not a data-cleaning inconvenience. It is the central methodological hazard, because
the places nobody measured are disproportionately the remote, poor, hard-to-reach ones the
programme exists to serve. Any system that quietly treats "no data" as "no problem" will
systematically direct money away from exactly the communities it is meant to find.

So the system is built on one rule, enforced in code rather than promised in prose:

> **Absence of data is uncertainty, never poor service.**

Those 334 settlements are never scored, never coloured on the priority ramp, and never counted
in a speed statistic. They appear in a separate queue that says out loud that it is a queue for
measurement.

### 1.4 What the system claims, and what it refuses to claim

| Claims | Refuses to claim |
|---|---|
| Observed performance near this community is weak or strong | This is official coverage |
| The evidence behind that is strong, moderate or insufficient | This operator is at fault |
| Investigate this place before that one | A tower should be built here |

---

## 2. What the system does: functions

The product is a single-page decision-support dashboard plus an optional conversational agent.
Its functions divide into six groups.

### Group A: Establish the evidence base

**A1. Settlement fusion.** Eight open datasets are reduced to one row per settlement, 1,448
rows and 20 columns. Rasters are reduced through buffers, polygons are joined by predicate,
points are joined directly.

**A2. Evidence tiering.** Every settlement is graded by how much measurement stands behind it,
computed **separately from severity** and never blended into the score.

| Tier | Rule | n | Median tests |
|---|---|---|---|
| `measured` | `n_tests >= 20` and `n_tiles >= 3` | **850** | 148 |
| `low_evidence` | `n_tests >= 5` | **264** | 11 |
| `insufficient` | everything else | **334** | 0 |

**A3. Two queues, not one leaderboard.** Queue A (1,114 scored) is ranked by need. Queue B
(334) is ranked by stakes only, is immune to the weight sliders, and is rendered as hollow
rings rather than coloured dots. The two never share a column, because putting them in one list
implies an ordering that does not exist.

### Group B: Score and rank

**B1. The Digital Inclusion Priority Index (DIPI).** A transparent weighted index, deliberately
not a machine-learning output.

```
DIPI = 100 x (0.40 x p_connectivity
            + 0.25 x p_population
            + 0.15 x p_institutions
            + 0.20 x p_equity)
```

Each pillar is a **percentile rank** across the 1,114 scored settlements, so all four run 0 to 1
and are uniformly spread by construction. Connectivity and equity are inverted, so slower and
poorer rank higher. Observed range on the shipped file: **20.2 to 76.6**.

**B2. Live re-weighting.** The four weights are sliders. Moving them recomputes all 1,114 scores
and the whole ranking in the browser, and prints how many settlements moved. A reviewer who
disagrees with 40/25/15/20 can show what their own weights produce in about five seconds. This
is the mitigation for the weights being ours and unpublished: the assumption is not defended,
it is made contestable.

**B3. Ranking table and export.** Sortable across every column, with CSV export that stamps the
active `weighting` and `speed_source` into the file so an exported sheet cannot be mistaken for
the team default.

### Group C: Make a number mean something

**C1. Experience simulator.** Converts an abstract Mbps figure into a sentence a non-specialist
can act on: can you load an article, upload a photo, hold a video call, watch video, with 1, 5
or 30 people sharing the link. Every threshold is sourced or explicitly marked as ours (§6.4).

**C2. Drill-down panel.** Every stored column for a settlement, plus derived terrain readings,
nearby facilities within 3 km, and a **site conditions** block carrying nighttime light and
seasonal-water adjacency as context that is labelled *not scored*.

**C3. Map exploration.** 1,448 points over a basemap, sized by population and coloured by DIPI
quintile, with optional layers: facilities, cell sites, hillshade, satellite imagery, flood
adjacency, screened mast paths, and a VIIRS night view.

### Group D: Fill gaps, honestly

**D1. Coverage model.** XGBoost regression estimates `dl_mbps` from geography alone for the 216
settlements with no measurement. Shown in amber, labelled "modelled estimate", with its
uncertainty and top three SHAP factors, and a one-click model card carrying the validation
numbers. **No model output enters DIPI.**

**D2. Survey planner.** Ranks the unmeasured settlements by where a field visit would be worth
most (§7.2).

### Group E: Turn priority into a plan

**E1. Delivery-option recommender.** A deterministic rule ladder assigns fibre, tower and fixed
wireless, satellite, or community Wi-Fi. Produces Wi-Fi 654, tower 449, fibre 323, satellite 22.

**E2. Deployment bundles.** HDBSCAN groups the 323 fibre-eligible settlements into 17 bundles
that could share a trench, priced by minimum spanning tree.

**E3. Budget what-if.** Given a budget, funds settlements greedily by population per ringgit and
reports how far the money reaches, across three cost cases, with the planner's own unit costs
accepted as input.

**E4. Shared mast screening.** A terrain-screened set-cover over the 449 tower settlements,
answering how many masts are actually needed once hills are taken into account.

**E5. District and division comparison.** Any number of areas side by side, with a metric table,
a radar profile of relative need, and PDF export.

### Group F: Explain and constrain

**F1. Ask Dino.** A LangGraph agent with 15 tools that recompute from the same files the
dashboard reads. Python computes, the agent narrates. A Python guardrail inspects every draft
and rejects it if a number appears that no tool returned, or if a required caveat is missing.

**F2. Source registry.** 20 sources and 19 parameters in a machine-readable file the dashboard
loads at runtime, so the tooltips and the documentation cannot drift apart.

**F3. Governance mapping.** Every row of the NIST AI RMF mapping is generated from the published
playbook, quoting each subcategory verbatim.

---

## 3. GeoAI in this system

The term covers two different things, and being precise about which is which is what makes the
claims defensible. This section separates them.

### 3.1 What is "Geo"

**Geo is where the information comes from, and it is the majority of the system.** None of these
steps involve learning; they are spatial computation, and they are the reason the datasets can
be combined at all.

| Geospatial operation | Where it is used | Why it is necessary |
|---|---|---|
| **Reprojection** EPSG:4326 to EPSG:32650 | before every buffer and distance | a buffer in degrees is meaningless, and it fails **silently** |
| **Buffering** 2 km and 3 km | population, facilities, speed join | defines the neighbourhood a settlement actually draws on |
| **Zonal statistics** over a buffer | `pop_2km`, `seasonal_water_px` | reduces a raster to a settlement-level number |
| **Point sampling** of a raster | `elevation_m` | a height at a coordinate |
| **Spatial join by predicate** `intersects` | settlement to Ookla tile | tiles are areas, so overlap is the correct relation, not containment |
| **Point in polygon** | district and division labels | assigns each settlement an administrative unit at page load |
| **Nearest-neighbour search** | `backhaul_km` to 59 towns | distance to the nearest plausible backhaul point |
| **Haversine distance** | clustering, MST, routing | avoids projection distortion over Sabah's 200 km extent |
| **Great-circle path interpolation** | 350 points along each of 10,070 paths | builds a terrain profile between two settlements |
| **Union-find de-duplication** at 4 km | population totals | two 2 km buffers touch at 4 km separation, so naive summing double counts |
| **Minimum spanning tree** | shared fibre trench length | the marginal cable a settlement adds, not its whole run |
| **Greedy set cover** | shared mast siting | how few masts can reach every settlement |
| **2-opt tour improvement** | survey routing | removes crossings from a visiting order |

**The single most consequential technical detail in the project is the CRS discipline.**
Buffering in EPSG:4326 asks for "2000 degrees". The code does not error. It returns numbers, and
they are wrong. Every buffer follows `.to_crs(32650).buffer(metres)` and converts back only when
a raster in EPSG:4326 must be read.

### 3.2 What is "AI"

**Exactly two learned models ship, and one language model narrates.** Everything else is a rule
or a classical algorithm. Calling the rest AI would be overclaiming, and a reviewer who checks
would find it.

| Component | Type | Role | Ships? |
|---|---|---|---|
| **XGBoost regressor** | supervised ML | estimate `dl_mbps` from geography for 216 unmeasured settlements | yes, display only |
| **HDBSCAN** | unsupervised ML | group 323 fibre settlements into shareable build bundles | yes |
| **SHAP TreeExplainer** | model explanation | top three factors behind each estimate | yes |
| **Gemini via LangGraph** | LLM agent | answer questions about what is on screen, in prose | yes, optional |
| DIPI, evidence tiers, recommender, budget allocator, set cover, MST, simulator | rules and classical algorithms | everything else | yes |

**What is deliberately NOT AI, and why that is a design decision rather than a gap:**

- **DIPI is arithmetic.** There is no trusted label for "officially underserved", so a
  supervised model would have nothing honest to learn. Training a model to reproduce DIPI from
  DIPI's own components is circular. A disclosed weighted sum is something a government planner
  can audit, recompute by hand, and argue with. NIST AI RMF has a subcategory for choosing a
  non-AI alternative where one suffices, and this is a control under it rather than a shortfall.
- **The recommender is an if/else ladder** with its fired reasons shown, not a classifier.
- **The budget allocator is a sort**, and it says on its own face that it is a greedy heuristic
  and not an optimiser.

### 3.3 How the combination helps

The fusion is not additive. Four results in this system exist **only** because a geospatial
operation and a learned model, or two geospatial layers, were combined. None is visible in any
single dataset.

**Combination 1: spatial grouping makes the model honest.**
Ookla tiles are roughly 610 m and settlements are points, so **358 of 1,232 settlements (29%)
share an exact speed value with a neighbour** because they sit in the same tile. Under a random
train/test split those twins land on opposite sides and the model is credited with predicting a
number it was shown. Grouping the cross-validation folds **by district** removes that.

| Validation scheme | MAE | R² |
|---|---|---|
| Naive random 5-fold | 25.31 | 0.557 |
| **Spatial GroupKFold, reported** | **34.06** | **0.330** |
| Baseline, global median | 43.10 | -0.177 |

The 0.227 R² gap is not a footnote, it is a result: it is the size of the illusion that a
spatially naive evaluation would have produced. **The geospatial insight is what makes the AI
number trustworthy**, and it cost us the flattering figure.

**Combination 2: terrain analysis destroyed our own optimistic answer.**
A distance-only set cover said 86 to 189 masts could serve the 449 tower settlements. Running
the same algorithm over only the paths that survive an SRTM line-of-sight and 60% Fresnel screen
gives **240 to 274**. At 3 km, only **712 of 1,412 candidate links (50.4%)** pass.

The second-order effect is the more useful one. Before terrain, the unsourced service radius
swung the cost estimate by **RM 53.6m**. After terrain, **RM 17.7m**. Once four paths in five
are blocked, extra assumed reach stops buying coverage, so **the weakest assumption in the
tower analysis stopped being load-bearing.** Geometry, not a model, did that.

**Combination 3: two rejected layers produced one real finding.**
VIIRS nightlights failed as a model feature and the terrain screen was about masts. Crossing
them answers a question neither can:

| Assumed reach | Isolated, needs own mast | **Also unlit, needs own power** |
|---|---|---|
| 3 km | 191 | **67** |
| 5 km | 169 | **58** |
| 10 km | 157 | **56** |

A site needing **its own mast and its own power** is a different cost class. It moves by only 11
across the whole radius range, so unlike most tower figures **it does not depend on the unsourced
reach assumption.**

**Combination 4: spatial clustering changed the price by more than half.**
Costing each fibre settlement its own trench charges ten villages on one road for ten full runs.
HDBSCAN plus a minimum spanning tree, then charging the cheaper of the shared spur and the direct
run:

| Costing rule | Trench | At RM 140k/km |
|---|---|---|
| Each settlement pays its own full run | 1,363.5 km | RM 190.9m |
| Each pays its spanning-tree spur | 890.0 km | RM 124.6m |
| **`min(spur, own run)`, what ships** | **635.9 km** | **RM 89.0m** |

The third row is the honest one: **sharing is not always cheaper.** 22 of 288 bundled settlements
sit further from their bundle neighbour than from town, and charging them the spur regardless
wasted 254.1 km, about RM 35.6m.

### 3.4 Where AI is deliberately kept away from the decision

| Decision | Made by |
|---|---|
| Priority ranking | disclosed weighted sum, no model |
| Which delivery option | if/else ladder with published cut-offs |
| Who gets funded under a budget | greedy sort on people per ringgit |
| Where to send a survey team | model output **is** used, as one factor, for targeting only |
| Whether a settlement is badly served | measurement only, never a model, never a nightlight |

The model has no network-side feature at all. It infers **the kind of place that tends to be
slow**, not coverage. That constraint is stated in the model card, in the docs, and enforced in
the agent.

---

## 4. Impact

### 4.1 Direct decision impact

| Result | Figure | Why it matters |
|---|---|---|
| Survey targeting | 216 unmeasured, 111 populated, **14** where a measurement would change a decision | turns an unbounded backlog into a week of fieldwork |
| Survey routing | 1,480 km statewide order to **85 km** routed per district, **17.5x** | identical evidence value at a fraction of the travel |
| Fibre costing | RM 190.9m to **RM 89.0m** | the naive per-settlement rule overstates fibre by 2.1x |
| Mast counting | 86 to **240** at 10 km | a distance-only estimate understates masts by nearly 3x |
| Radius sensitivity | RM 53.6m to **RM 17.7m** | the project's weakest tower assumption stopped mattering |
| Power constraint | **703 of 1,448** settlements dark | any option sited there needs its own power, a real line item |
| Cross-source | **56** need own mast **and** own power | the most expensive class in Sabah, invisible to either layer alone |

### 4.2 Impact on how the answer is used

**A contestable index beats a confident one.** The weights are ours, and the mitigation is that
they are sliders that reprice the whole ranking live. Three alternative weightings retain 36 to
44 of the top 50, so the ranking is driven by the data rather than by our choice.

**A range beats a point estimate where nothing is published.** No Malaysian per-unit cost is
public. `COSTS_VERIFIED = false` is in the code. The budget panel reports across three cost
cases and accepts the planner's own figures, and then states whose figure produced the result.

**Naming the disagreement is more useful than hiding it.** Cheapest-per-head and most-urgent
genuinely disagree: at RM 50m the funded list is overwhelmingly urban Kota Kinabalu, while the
priority ranking points at rural Pitas and Ranau. The dashboard shows both rather than picking
one and calling it the answer.

### 4.3 Impact of the honesty controls

These are the parts most likely to matter if the system is ever used for real money.

- **334 settlements are never scored.** A system that scored them from thin data would rank
  remote communities as adequately served and defund them.
- **Per-district bias is published, not fixed.** Pitas is over-predicted by **+32.05 Mbps**
  across 39 settlements, so its settlements look better served than they are. Pitas is poor and
  rural. The remediation attempt made it worse, so it ships as a stated limitation and a
  constraint on use.
- **Five feature groups were tested and rejected with their scores recorded.** A model card
  listing only what worked is not a model card.

---

## 5. Data: types and sources

### 5.1 Geospatial data types handled

| Type | Sources here | How it is reduced to a settlement |
|---|---|---|
| **Vector, points** | OSM settlements, OSM facilities, Meta RWI grid, OpenCelliD records | direct join, or count inside a buffer |
| **Vector, polygons** | GADM level 1 and 2, Ookla tiles | clip, and spatial join by `intersects` |
| **Raster, continuous** | WorldPop 100 m, SRTM 30 m, VIIRS 500 m | zonal statistic over a buffer, or point sample |
| **Raster, categorical** | JRC surface-water seasonality 30 m | custom zonal count of cells in a value range |
| **Derived, line profiles** | SRTM along 10,070 mast-to-village paths | 350-point interpolation, then geometric analysis |
| **Raster tiles, display only** | CARTO basemaps, Esri imagery, AWS Terrain | rendered, never analysed |

**The unit of analysis is one OSM `place` node**: 1,136 village, 253 hamlet, 54 town, 5 city.
The output is a **settlement-level multi-layer feature stack**, deliberately not called a data
cube, because layers are joined to points rather than stacked on a shared raster grid.

### 5.2 Datasets in the shipped system

| ID | Dataset | Type | Resolution | Role | Licence |
|---|---|---|---|---|---|
| D1 | GADM 4.1 levels 1 and 2 | vector polygon | n/a | AOI clip; districts become CV groups | free for academic use |
| D2 | Ookla Speedtest Open Data, fixed tiles 2025 Q1 to Q4 | vector polygon | ~610 m | **the target variable** | CC BY-NC-SA 4.0 |
| D3 | OpenStreetMap `place` nodes | vector point | n/a | the 1,448 settlements | ODbL |
| D4 | WorldPop 2020 constrained, UN-adjusted | raster | ~100 m | population stakes | CC BY 4.0 |
| D5 | OpenStreetMap amenities | vector point | n/a | 606 facilities: 460 school, 146 health | ODbL |
| D6 | JRC Global Surface Water seasonality | raster | 30 m | surface-water context | EC JRC / Google |
| D7 | Meta Relative Wealth Index | vector point | ~2.4 km | equity pillar | CC BY 4.0 |
| D8 | NASA SRTM | raster | 30 m | elevation and terrain profiles | public domain |

### 5.3 Tested and rejected, retained as evidence

| Dataset | Tested as | Outcome |
|---|---|---|
| **OpenCelliD** | telecom supply features | **rejected.** MAE 36.55 against 34.06. Record density correlates 0.56 with Ookla test count, so it maps where volunteers surveyed. Tawau city, 40,000 people and 205 Mbps measured, shows its nearest record 115 km away. Kept as a map layer with a legend saying no marker means not surveyed |
| **VIIRS DNB annual composites** | time axis and growth signal | **rejected as a feature**, cut before fitting because 703 of 1,448 are dark and **192 of the 216 settlements we predict for (89%) are dark**. Retained as an electrification constraint and a night view |

### 5.4 Dataset caveats that constrain downstream claims

- **Ookla is crowdsourced observed performance, not coverage.** A tile exists because somebody
  ran a test there. Test counts vary enormously, which is why `n_tests` is carried through to
  the evidence tier rather than averaged away.
- **WorldPop is modelled, not observed**, and `pop_2km` **must never be summed**. Buffers
  overlap: across Ranau a naive total inflates **22,303 people to 566,012, a factor of 25**.
- **JRC includes coastal and tidal water**, so it is flood-prone *context*, never flood
  prediction, and is deliberately excluded from the index.
- **96 settlements have no RWI cell.** That means "no wealth data", not "poor", and they are
  disproportionately the remotest ones where a wrong assumption would do most damage. Missing
  RWI maps to a neutral 0.5 percentile, never to 0.
- **OSM completeness is uneven in rural areas.** A facility count means *mapped* facilities.
- **SRTM is C-band radar**, so in dense forest the reading sits partway up the canopy. The
  terrain screen over-blocks cleared land and under-blocks tall forest.

### 5.5 Published figures that become numbers

Twenty sources are registered in [`dataset/web/sources.json`](../dataset/web/sources.json),
each with its quote, page reference and how far it was verified. The load-bearing ones:

| Source | What it backs |
|---|---|
| Oughton 2021, arXiv:2102.03561 | RM 90k/140k/210k per km fibre, RM 520k per mast, 30 m mast height, the 40 km wireless band |
| ITU Last-mile Guide 2020, D-TND-01-2020 | 3,000 fibre population floor (Table 28), 500 fixed-wireless floor (p65), terrain qualifies options (Table 29) |
| MCMC USP Annual Report 2024 | Malaysian sanity check: RM 801m over 823 towers, about RM 973k per site all-in |
| Bernama, JENDELA 2, Aug 2025 | the 3 km facility radius and the one-institution anchor rule |
| YouTube system requirements | the 0.7 / 1.1 / 2.5 / 5 / 20 Mbps video ladder, all five tiers match exactly |
| FCC Broadband Speed Guide | 1.5 Mbps marginal video call |
| Zoom system requirements | 3 Mbps video call pass |
| ITU-T G.114 | the 150 ms latency gate |
| MCMC Assignment of Spectrum | 700 MHz is Malaysia's assigned sub-1 GHz coverage band |
| ITU-R P.530 | why Fresnel clearance is one input and not the answer |
| ITU-R P.1812 | named as **the calculation we do not run** |

---

## 6. Algorithms and models

### 6.1 The supervised model

| | |
|---|---|
| **Task** | supervised regression, continuous target |
| **Algorithm** | XGBoost gradient boosting regressor |
| **Target** | `dl_mbps`, fitted on `log1p(y)`, inverted with `expm1` before every metric |
| **Training rows** | the 850 `measured` settlements only |
| **Prediction rows** | the 216 with no measurement |
| **Features (9)** | `pop_2km`, `n_schools_3km`, `n_clinics_3km`, `rwi`, `seasonal_water_px`, `flood_prone`, `place`, `backhaul_km`, `rwi_missing` |
| **Parameters** | `n_estimators=400, learning_rate=0.05, max_depth=5, subsample=0.8, colsample_bytree=0.8, seed=42, tree_method=hist` |
| **Validation** | `GroupKFold(n_splits=5)` grouped by district, folds frozen before any model runs |
| **Uncertainty** | fold-ensemble disagreement, the std across the 5 fold models |
| **Explanation** | SHAP TreeExplainer, top 3 factors per settlement |

**Why log1p.** `dl_mbps` spans 0.36 to 346 Mbps with median 45.9 and mean 67.2. Without the
transform the loss is dominated by a handful of fast towns and the model abandons the slow rural
tail, which is the only part the project cares about.

**Why nothing is fitted in preprocessing.** No imputer, no scaler, no learned encoder. `rwi` NaN
is kept because XGBoost handles missing natively; missingness flags are computed row-wise;
`place` uses a fixed category domain. Because nothing is fitted, **nothing can leak** from a
validation fold into training.

**Leakage controls.** Banned as predictors: the target itself, anything derived from `n_tests`
or `n_tiles` (they describe how the target was measured), `ul_mbps` and `latency_ms` (same tile),
`p_connectivity` and `dipi` (contain the target rescaled), `lon`/`lat` (location memorisation),
and `district` (it **is** the CV group).

**Selection rule, fixed in advance:** replace model A only if spatial MAE improves **and** the
variant is better in at least 4 of 5 folds without worsening the worst district bias. Setting the
rule before seeing results is what prevents searching until something wins by luck.

**The five variants**, all on identical folds, seed and parameters:

| Model | Adds | MAE | R² | Verdict |
|---|---|---|---|---|
| **A** | nine base features | **34.06** | **0.330** | **selected**, beats baseline by 21% |
| B1 | `elevation_m` | 34.48 | 0.312 | rejected, better in 2/5 folds |
| B2 | all three terrain columns | 34.06 | 0.317 | rejected, MAE ties and R² falls |
| A+division | `division` | 36.51 | 0.266 | rejected, the fairness remedy made it worse |
| C | OpenCelliD counts | 36.55 | 0.262 | rejected, better in 1/5 folds |

**What MAE 34.06 actually means.** Against a measured distribution with median 47.2, mean 72.1
and std 59.7, the average error is about 0.7x the median. **This is not accurate enough to quote
a settlement's speed.** It is accurate enough to sort places into roughly-slow and
roughly-fast, which is the only job it is given.

### 6.2 The unsupervised model

**HDBSCAN**, haversine metric, `min_cluster_size=5`, run on the **323 fibre-eligible settlements
only**. Produces 17 bundles, 288 clustered, 35 noise, 7 bundles crossing a district line.

**Why not DBSCAN.** Tried first and failed: at a 15 km radius it chained **931 of 1,114**
settlements into one cluster. Sabah's settlements form a connected chain and single linkage
walks the whole state. `eps` is one global number and no single radius fits both town-adjacent
density and interior sparseness. HDBSCAN builds a hierarchy and cuts it per region, which
removes the "why that radius" question entirely.

**Why cluster the subset rather than filter afterwards.** Clustering all 1,448 and then filtering
over-merges: two fibre villages 40 km apart end up sharing a trench that cannot exist.

**There is no accuracy figure for clustering, and anyone quoting one is inventing it.**
Unsupervised clustering has no ground truth. What is reported instead: a 10.8% noise fraction,
the downstream trench length, and a parameter sweep.

### 6.3 Classical algorithms

| Algorithm | Used for | Honest caveat |
|---|---|---|
| **Prim's MST** | shared trench length per bundle | a 1 km floor applies to every edge including the root |
| **Greedy set cover** | shared mast siting | NP-hard; greedy is an `ln n` approximation, so the result is an **upper bound, not a minimum**. Never called "maximum coverage" |
| **Greedy nearest-neighbour + 2-opt** | survey routing | straight-line distance, no road network, so a **lower bound** and a visiting order rather than a navigation plan |
| **Greedy budget allocation** | who gets funded | `continue`, not `break`, so one expensive settlement cannot end the list early. A heuristic, not an optimiser, and the card says so |
| **Union-find at 4 km** | population de-duplication | two 2 km buffers touch at 4 km separation |
| **Mann-Kendall + Theil-Sen** | nightlight trend | non-parametric, assumes neither linearity nor normality |
| **4/3-earth + 60% Fresnel** | line-of-sight screen | a screen, not a propagation model |

### 6.4 The simulator's thresholds

Every number, and whether it is published, benchmarked or ours:

| Number | Use | Status | Source |
|---|---|---|---|
| 0.7 / 1.1 / 2.5 / 5 / 20 Mbps | five video tiers | **published**, all five match | YouTube system requirements |
| 1.5x the tier | "smooth" | **ours** | headroom for a dip |
| 3 Mbps down | video call passes | **published** | Zoom, 1080p group calling |
| 3 Mbps up | video call passes | **ours, and looser than the source** | Zoom publishes 3.8 up |
| 1.5 Mbps both legs | marginal | **published** | FCC HD personal video call |
| 150 ms | video call passes | **published** | ITU-T G.114 preferred range |
| 250 ms | marginal | **ours, stricter than the standard** | G.114 allows to 400 ms |
| 2 MB page, 4 MB photo | article and photo tasks | **benchmarks** | no standards body sets these |
| 2 s / 5 s, 10 s / 30 s | task verdicts | **ours** | not Core Web Vitals, whose LCP cuts are 2.5 s and 4.0 s |
| 21 Mbps | "underserved" in comparisons | **ours** | 0.7 x 30 users, built from the video ladder |

One caveat is stated on screen: **G.114 budgets one-way mouth-to-ear delay** including codec and
jitter buffer, while `latency_ms` is a network **round trip**. They are not the same quantity.

---

## 7. Notable analyses

### 7.1 Line-of-sight terrain screen

350 elevation points along each of 10,070 mast-to-village paths, with three corrections a naive
sightline misses: **4/3-earth curvature**, a **60% first-Fresnel zone** (radio needs clearance
around the line, not just a bare sightline), and `min_clear_m` so "failed by 2 m" stays
distinguishable from "failed by 200 m".

| Assumed radius | Clear line of sight | 60% Fresnel clear |
|---|---|---|
| 3 km | 62.3% | **50.4%** |
| 5 km | 50.8% | **36.2%** |
| 10 km | 33.2% | **19.1%** |

**Assumptions, stated wherever quoted:** mast height 30 m (sourced), receiver height 10 m
(**ours, unsourced, and now the screen's only unsourced input**), 700 MHz. The band choice is
conservative by construction: the lowest assigned band gives the widest Fresnel zone and
therefore the strictest screen.

### 7.2 Where to measure next

**The naive ranking is wrong.** Ranking by predicted slowness sends teams to places the model is
already confident about, where a measurement confirms what is known and changes nothing. The
right question is **decisiveness**: does the estimate sit close enough to the service threshold,
relative to the model's own disagreement, that a measurement could land on either side?

The offline formula was revised four times, each revision driven by inspecting the top ten:

| Version | What it surfaced | Why it was wrong |
|---|---|---|
| v1 | never-predicted settlements | assigned maximum uncertainty by default |
| v2 | estimates of 141 to 174 Mbps | wide intervals alone qualified them |
| v3 | correlated -0.49 with disagreement | preferred settlements already understood |
| **v4** | near-threshold, populated, uncertain | shipped to `measurement_priority_v1.csv` |

**The funnel is the finding: 216 unmeasured, 111 with population, 14 where a measurement would
change the decision.**

See §9.1 for a known divergence between this file and the dashboard's live panel.

### 7.3 Nightlights

**Two method choices, both load-bearing.**

*Annual composites, not monthly.* The annual product applies outlier removal that discards
biomass-burning pixels using the twelve-month median, filtering palm-oil burning and gas flares
at source. Raw monthly imagery has no such filter, and those would read as brightening
settlements.

*Maximum within 1 km, not mean over 2 km.* A 2 km buffer at 500 m holds about 50 pixels, so a
village lighting one or two has its signal divided by fifty. **This was wrong in a first pass
and the correction changed the shape of the answer:**

| Threshold | mean over 2 km (superseded) | **max within 1 km (shipped)** |
|---|---|---|
| 0.5 | 400 lit | **745 lit** |
| 0.25 | 519 | 798 |
| 0.1 | 670 | 804 |

The old column keeps climbing as the threshold relaxes, the signature of signal sitting under
the cutoff. The new one is nearly flat, which is a real **detection floor**. The threshold is not
load-bearing; the reducer was. **The first pass also swept the threshold and called the result
conclusive, which was the actual mistake:** a 5x threshold relaxation cannot answer a 50x
dilution.

**A claim the correction killed.** Brightening moved only 278 to 276 while lit rose from 400 to
745, so all 345 newly-lit settlements landed in flat or dimming. The diluted series made
brightening look like **70% of lit settlements** when the real figure is **37%** against 57%
flat. "Sabah is electrifying rapidly" is not supported.

| Class | n |
|---|---|
| dark | 703 |
| flat | 422 |
| brightening | 276 |
| dimming | 31 |
| `flat_urban_artefact` | 16 |

**Dimming is not reported as a finding.** The steepest declines are Sabah's brightest urban
centres. VIIRS DNB cannot sense blue light, so a sodium-to-LED street lighting conversion reads
as falling radiance exactly there. Those 16 are held in a separate class. The other 31 have no
mechanism we can name, so the count is reported and deliberately not interpreted.

**How it appears in the product.** A line under the suggested option, a tile in the site
conditions block, and a **night view**: a map mode that dims the priority ramp away and draws
the 745 lit settlements glowing by actual radiance. That distinction is the permission for it.
An unlit *overlay* on the priority map would say *these places are worse*, which the data does
not know. A night *view* says *these places emitted no light*, which is exactly what it knows.

---

## 8. Architecture and reproducibility

### 8.1 Shape of the system

```
Colab notebooks (offline)          Repo (versioned)              Browser (runtime)
-----------------------            ----------------              -----------------
01_data_preparation        ->   training_table.csv        ->   dashboard/index.html
02_model_training          ->   model_predictions_v1.csv       single file, no build step
03_spatial_analysis        ->   clusters.json                  MapLibre GL JS via CDN
                                towers_los.json
                                viirs_trend.csv           ->   agent/ (optional)
                                power.json                     LangGraph + 15 tools
                                sources.json
```

**The dashboard is one HTML file** of about 8,200 lines with no build step and no framework. All
1,448 points render client-side. **It never hard-depends on the agent**: if the agent server is
down, the chat panel says so and nothing else on the page changes.

**Every derived file passes through an export script that re-verifies it rather than trusting
it.** `export_clusters.py`, `export_power.py`, `export_towers.py` and `export_model.py` re-derive
the headline numbers from the raw inputs and refuse to write if a check fails. `export_power.py`
caught a real error while this document's data was being prepared: a claim that all 216 unmeasured
settlements were dark, when 24 of them are lit.

### 8.2 Reproducibility controls

| Control | Implementation |
|---|---|
| Input versioning | `training_table.csv` SHA-256 `fd0d29125cc2...` asserted before anything runs |
| Seed | 42, fixed for every random operation |
| Fold assignment | frozen and exported **before any model trains**: `fold_assignment.csv`, 850 training rows across 5 folds (181/169/167/166/167) plus 598 marked `-1` |
| Configuration | `run_config.json` records target, rules, features, parameters, library versions |
| Model artifacts | 5 fold models, a full-fit model, and a feature-**order** manifest |
| Verification | saved models reloaded from disk and asserted to reproduce MAE, R² and every prediction to under 0.01 Mbps |

Feature **order** is recorded because loading a model and passing columns in a different order
produces silently wrong predictions rather than an error.

**Known non-reproducible sources:** OpenStreetMap (the Geofabrik extract rebuilds daily, so
settlement counts may drift by one or two) and OpenCelliD (a rolling 18-month window). Everything
else is frozen.

### 8.3 The agent

| | |
|---|---|
| Shape | **one** LangGraph state machine, not a crew: `agent -> tools -> agent -> evidence_check -> rewrite` |
| Model | Gemini, `temperature=0` |
| Tools | 15, all pure Python reading the same files the dashboard reads |
| Retrieval | **none, deliberately.** The corpus is a fixed 1,448-row table, so typed functions beat retrieving text about it |
| Context | trimmed to 12 messages, **cut on a turn boundary** so a tool result is never orphaned from its call |
| Guardrail | pure-Python `_scan()` over the raw tool rows |
| Evaluation | 194 assertions, run on every change, no API key needed |

**The guardrail exists because a prompt was not enough.** The system prompt already forbade
inventing a number and the model did it anyway: asked why a settlement was not picked, it
restated a speed **the user had asserted in the question** as if it were data. So every figure
in a draft is now extracted and compared against every figure any tool returned, and anything
unmatched sends the answer back to be rewritten. After two failures it falls back to a
hard-templated safe answer.

Other rules enforced in Python rather than requested in prose: an insufficient-evidence
settlement may never be called underserved, a low-evidence row forces the limited-tests warning,
a modelled value must be called a modelled estimate, an illustrative cost must say it is
illustrative, a shared-connection figure must name the equal-sharing assumption, a bundle must be
described as a proximity screen, and the closing disclaimer must be present.

### 8.4 Governance

`docs/ai_governance.md` maps this system against the **NIST AI RMF Playbook**. All **72**
subcategories were reviewed and **22** were kept, each pointing at a control that exists in this
repository. The other 50 are listed with the reason they were cut rather than softened into a
claim: organisational machinery a student team does not operate, controls that need a live
deployment, and surfaces the project does not have.

**The table is generated, not written.** `build_governance.py` pulls each NIST description
verbatim from `nist_playbook.json` at build time, so the framework's wording cannot be reworded
to fit the work.

The scope is worth stating precisely: **NIST applies to the two AI components that ship**, the
LLM agent and the XGBoost model. It says nothing about development tooling. And the framework
credits keeping AI *out* of decisions: MANAGE 2.1 is "a non-AI alternative was chosen where one
sufficed", and DIPI being plain arithmetic is a control under it.

---

## 9. Limitations and known gaps

### 9.1 Resolved: the survey planner now ships one method

The dashboard used to rank on `stakes_score x (pred_hi - pred_lo)`, the width of the model's
interval, while `measurement_priority_v1.csv` carried the notebook's decisiveness formula.
The two were Spearman **-0.224** with no overlap in their top ten.

The notebook's question is the right one, so it ships. But it can only speak for 111 of the
334, because decisiveness needs an estimate and a population, so it does not simply replace
the queue. The panel now ranks three groups apart and never multiplies them:

| Group | n | Ranked by |
|---|---|---|
| Would settle a decision | 14 | `measurement_priority` |
| Nothing known yet | 223 | `stakes_score` |
| Estimate already clear of the line | 97 | `measurement_priority` |

The third sits below the second deliberately. It has a number and the unknowns do not, and
letting that put it on top would be backwards.

### 9.2 Model limitations

1. **No network-side predictors.** Every feature is demographic, economic or geographic, so the
   model infers the *kind of place* that tends to be slow, not coverage.
2. **Systematic per-district bias**, published rather than fixed. Pitas +32.05 (n=39) is the
   harmful direction. Remediation via `division` was tested and made it worse.
3. **Predictions support survey targeting only**, never a DIPI ranking input.
4. **`pop_2km` is the strongest factor**, so for near-empty settlements the estimate is driven
   largely by emptiness.
5. **Regression to the mean above about 150 Mbps.** It identifies slow places, not fast ones.
6. **Uncertainty is model disagreement, not a calibrated interval.** No coverage check was run.
7. **No reserved spatial holdout.** 25 districts and 850 rows made one impractical.
8. **Cross-sectional, not temporal.** Both temporal candidates were tested and rejected: Ookla
   (four quarters, 22% tile completeness, swing correlating -0.57 with test count) and VIIRS
   (13 years, but 703 of 1,448 dark).

### 9.3 Unsourced assumptions, flagged at every point of use

| Assumption | Value | Note |
|---|---|---|
| DIPI weights | 40/25/15/20 | the largest unsourced choice; mitigated by making them sliders |
| Evidence tier thresholds | 20 tests / 3 tiles, 5 tests | The **20-test line is demonstrably doing work**: no settlement above it carries an implausible latency, while 22 below it do. **The 5-test line is not.** The 5 to 9 band is barely tidier than the unscored 1 to 4 band beneath it, with a higher maximum and more bad readings. Kept as a pragmatic cutoff, not claimed as a proven sufficiency threshold. See how_it_works.md §3 |
| `fibre_max_km` | 15 km | the only cut-off in the recommender ladder with no citation |
| Receiver height | 10 m | the terrain screen's only remaining unsourced input |
| Service threshold | 21 Mbps | ours, 0.7 x 30, built from the video ladder |
| Lit threshold | 0.5 radiance | bounded: relaxing to the noise floor moves the count by 59 of 1,448 |
| Terrain shadow | -150 m | adds a caveat, never changes an option |
| Every ringgit figure | `COSTS_VERIFIED = false` | benchmarked against Oughton 2021, not quoted |

### 9.4 Data limitations

- **Straight-line distances throughout.** A lower bound, not routing.
- **`backhaul_km` is a proxy**: distance to the nearest OSM town, not a survey of where fibre
  terminates. Every distance-dependent cost inherits that.
- **OSM completeness is uneven.** A zero facility count means none *mapped*.
- **SRTM canopy bias.** The screen over-blocks cleared land and under-blocks tall forest, and
  cannot be corrected without a canopy-height layer.
- **A terrain screen is not predicted coverage.** ITU-R P.1812 is what a real prediction needs
  and we do not run it.

---

## 10. Credits

Network performance © Ookla Speedtest Open Data (CC BY-NC-SA 4.0) · © OpenStreetMap contributors
(ODbL) · Population © WorldPop (CC BY 4.0) · Surface water © EC JRC / Google · Relative Wealth
Index © Meta Data for Good (CC BY 4.0) · Elevation: NASA SRTM · Boundaries: GADM 4.1 · Cell
records © OpenCelliD (CC BY-SA 4.0) · Nighttime lights: NOAA / NASA VIIRS DNB · Basemaps ©
OpenStreetMap contributors © CARTO · Imagery © Esri, Maxar, Earthstar Geographics · NIST AI Risk
Management Framework Playbook (US government work, public domain)

---

## Appendix: the system in one paragraph

Dino Slayer fuses eight open geospatial datasets to one row per settlement across 1,448 Sabah
communities, and produces a transparent priority index that a planner can recompute by hand and
argue with. Where no measurement exists it estimates one with a gradient-boosted model validated
on held-out districts, which cost 0.227 R² against the flattering random split and is the number
reported. It then turns priority into decisions: where to send a survey team, which communities
could share a fibre trench, how many masts terrain actually requires, and how far a given budget
reaches. The geospatial work is what makes the AI trustworthy, and the AI is confined to two
places where a rule would not do. Everything that decides who matters is arithmetic, disclosed
and adjustable, and no settlement without evidence is ever described as badly served.

# How every number on the screen is worked out

This walks the dashboard from top to bottom, one feature at a time. For each part it says
three things:

1. **What you see.** The thing on screen.
2. **How it is counted.** The actual arithmetic, with a worked example where the arithmetic
   is not obvious.
3. **Where the number came from.** Either a published source with a link, or a plain
   admission that the figure is ours and not published anywhere.

Every code reference points at a real line so you can check it rather than trust it.

---

## 0. The source list, once, up front

**No PDF was supplied to this repository, and none was used.** Every figure below traces
to a public document listed here. Six of them are PDFs you can download yourself, and they
are marked. The machine-readable copy of this table is
[dataset/web/sources.json](../dataset/web/sources.json), which the dashboard reads at load
so the "Sources" tooltip and this document cannot drift apart.

Four kinds of external thing are listed, and mixing them up is the usual mistake:
**published figures** that set a threshold or a unit cost, **data** that becomes a number,
**frameworks and standards** that set the method, and **map rendering** that draws the
picture and contributes nothing to any result.

| Key in `sources.json` | Document | Format | What it backs |
|---|---|---|---|
| `oughton_2021` | Oughton, E. J. (2021). *Policy options for digital infrastructure strategies: A simulation model for broadband universal service in Africa*. arXiv:2102.03561. [Link](https://arxiv.org/abs/2102.03561) | **PDF on arXiv** | The 40 km wireless band, the 40 km satellite threshold, the RM 140k per km fibre benchmark, the RM 520k per mast benchmark, the 30 m mast height |
| `itu_lastmile_2020` | ITU Telecommunication Development Bureau, Garrity, J. and Garba, A. A. (2020). *The Last-mile Internet Connectivity Solutions Guide: Sustainable connectivity options for unconnected sites*. ITU D-TND-01-2020, ISBN 978-92-61-32141-3. [Link](https://www.itu.int/hub/publication/d-tnd-01-2020/) | **PDF, ITU publication** | The 3,000 population floor for fibre (Table 28), the 500 floor for fixed wireless (Box 4), the principle that terrain limits which options are available (Table 29) |
| `ogutu_oughton_2021` | Ogutu, O. B. and Oughton, E. J. (2021). *A Techno-Economic Cost Framework for Satellite Networks Applied to Low Earth Orbit Constellations: Assessing Starlink, OneWeb and Kuiper*. arXiv:2108.10834. [Link](https://ar5iv.labs.arxiv.org/html/2108.10834) | **PDF on arXiv** | The satellite density sanity check, that LEO satellite is the sensible answer below roughly 0.1 people per hectare |
| `analysys_mason_2022` | Placido, C. (2022). *Backhaul networks: comparing the economics of using satellite mega-constellations rather than fibre optics*. Analysys Mason Quarterly, October 2022. [Link](https://www.analysysmason.com/contentassets/e0db35bece0f4370b6715b589e62049b/analysys_mason_backhaul_satellite_fibre_oct2022_quarterly.pdf) | **PDF** | Cross-check that the satellite-versus-fibre crossover sits where our rule puts it |
| `mcmc_usp_2024` | MCMC (2024). *Universal Service Provision Annual Report 2024*. [Link](https://www.mcmc.gov.my/en/resources/usp) | **PDF** | The Malaysian sanity check on mast cost: RM 801m across 823 towers, about RM 973k per site all-in, which brackets our RM 520k build-only figure |
| `mcmc_jendela_schools` | Bernama (27 Aug 2025). *MCMC Draws Up More Solutions Under JENDELA 2 For Rural Connectivity*. [Link](https://www.bernama.com/en/general/news.php?id=2461184) | Web article | The 3 km facility radius and the "one institution is enough to anchor a community hub" rule, which is how JENDELA 2 actually targets rural sites |
| `shayea_rural_2020` | Shayea, I. et al. (2020). *Performance Analysis of Mobile Broadband Networks with 5G Trends and Beyond: Rural Areas Scope in Malaysia*. IEEE Access 8, 65211-65229. [Link](https://ieeexplore.ieee.org/document/9025271) | Journal paper | Context for what rural Malaysian mobile broadband actually delivers |
| `shayea_urban_2021` | Shayea, I. et al. (2021). *Urban Areas Scope in Malaysia*. IEEE Access 9, 90767-90794. [Link](https://ieeexplore.ieee.org/document/9446158) | Journal paper | The urban counterpart, used for the same context |
| `mcmc_jendela_aggregate` | MCMC via Malay Mail (2022). *Implementation of first phase of JENDELA to cost RM28b*. [Link](https://www.malaymail.com/news/malaysia/2022/07/08/mcmc-implementation-of-first-phase-of-jendela-initiative-to-cost-rm28b/16347) | Web article | Order-of-magnitude check that our whole-province totals are not absurd |
| `itu_fibre_repeaters` | ITU (2020). *Broadband and connectivity solutions for rural and remote areas*. [Link](https://www.itu.int/hub/2020/05/itu-launches-new-study-paper-on-broadband-and-connectivity-solutions-for-rural-and-remote-areas/) | Study paper | Background on why a fibre run has a practical distance limit |
| `oecd_worldbank_ordering` | OECD and World Bank guidance on rural broadband technology economics by population density | Search-verified only | The ordering itself: fibre, then fixed wireless, then satellite, as density falls |
| `nbn_australia` | NBN Co, *Fixed Wireless coverage and service qualification*. [Link](https://www.nbnco.com.au/learn/network-technology/fixed-wireless-explained) | Web | The precedent for a desktop screen followed by a site visit, which is exactly what our recommender claims to be |
| `platform_video_bitrates` | YouTube Help, *System requirements*, recommended sustained speeds by resolution. [Link](https://support.google.com/youtube/answer/78358) | Web, Google | The 0.7 / 1.1 / 2.5 / 5 / 20 Mbps video ladder in the simulator. All five tiers match the published table exactly |
| `fcc_speed_guide` | FCC, *Broadband Speed Guide*. [Link](https://www.fcc.gov/consumers/guides/broadband-speed-guide) | Web, US regulator | The 1.5 Mbps marginal floor on the video-call task |
| `zoom_bandwidth` | Zoom, *System requirements and bandwidth*. [Link](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060748) | Web | The 3 Mbps pass threshold on the video-call task |
| `itu_g114` | ITU-T (2003). *Recommendation G.114: One-way transmission time*. [Link](https://www.itu.int/rec/T-REC-G.114) | ITU Recommendation | The 150 ms latency gate on the video-call task, which is exactly G.114's preferred limit |
| `mcmc_700mhz` | MCMC, *Assignment of Spectrum*. [Link](https://www.mcmc.gov.my/en/spectrum/assignment-of-spectrum/spectrum-assignment) | Web | That 700 MHz is Malaysia's assigned sub-1 GHz coverage band, which is the frequency the terrain screen computes its Fresnel zones at |
| `viirs_vnl_v2` | Earth Observation Group / NOAA, *VIIRS Nighttime Light Annual Composites V2*. [Link](https://eogdata.mines.edu/products/vnl/) | Data product | The nightlight analysis in §19, tested and rejected as a model feature |

### And the data itself

| Column | Source | Licence |
|---|---|---|
| `name`, `place`, coordinates | [OpenStreetMap](https://www.openstreetmap.org/copyright), nodes tagged `place` in city/town/village/hamlet | ODbL |
| `dl_mbps`, `ul_mbps`, `latency_ms`, `n_tests`, `n_tiles` | [Ookla Open Data](https://github.com/teamookla/ookla-open-data) fixed tiles, 2025 Q1 to Q4 | CC BY-NC-SA 4.0 |
| `pop_2km` | [WorldPop](https://www.worldpop.org/) 100 m constrained, summed inside a 2 km buffer | CC BY 4.0 |
| `n_schools_3km`, `n_clinics_3km` | OpenStreetMap facility points inside a 3 km buffer | ODbL |
| `rwi` | [Meta Relative Wealth Index](https://dataforgood.facebook.com/dfg/tools/relative-wealth-index), nearest cell | CC BY 4.0 |
| `seasonal_water_px`, `flood_prone` | [JRC Global Surface Water](https://global-surface-water.appspot.com/) | EC JRC / Google |
| `elevation_m` | [NASA SRTM](https://www.earthdata.nasa.gov/data/instruments/srtm), sampled at the point | Public domain |
| `_district`, `_division` | [GADM 4.1](https://gadm.org/), point-in-polygon at load time | Free for academic use |
| Cell sites layer | [OpenCelliD](https://opencellid.org/), crowdsourced | CC BY-SA 4.0 |
| Nightlights (§19, not in the product) | [NOAA VIIRS VNL V2](https://eogdata.mines.edu/products/vnl/) annual composites 2013 to 2025, via Google Earth Engine | Public domain |

### Frameworks and standards

These are not data. Nothing here becomes a number. They are the published methods
the project is measured against, and two of them are named specifically as calculations
we **do not** run.

| Reference | What it is | How it is used here |
|---|---|---|
| **NIST AI Risk Management Framework, Playbook** | US NIST. A US government work, so public domain. The 72 subcategories ship in [`docs/nist_playbook.json`](nist_playbook.json) | Every row of [`ai_governance.md`](ai_governance.md) is **generated** from this file by [`build_governance.py`](build_governance.py), quoting each subcategory description verbatim so it cannot drift from the original. **22 of 72** are mapped to a control that exists in this repo. The other 50 are listed with the reason they were dropped, rather than softened into a claim |
| **ITU-R P.530** | ITU recommendation: propagation data and prediction methods for terrestrial line-of-sight systems. [Link](https://www.itu.int/rec/R-REC-P.530/en) | Why the mast panel calls Fresnel clearance **one input rather than the answer**. P.530 treats clearance alongside fading, rain and multipath, none of which we model. Passing our screen is not a prediction that a link works |
| **ITU-R P.1812** | ITU path-specific propagation prediction for terrestrial services | Named throughout as **the calculation we do not run**. It is what a real coverage prediction would require, and saying so is what keeps the terrain screen honest about being a screen |

### Map rendering only (no analysis input)

Delete all three tomorrow and every DIPI score, cost and recommendation is unchanged.
They are listed because each licence requires the credit, which the app displays.

| Provider | What it draws | Attribution shown |
|---|---|---|
| CARTO `dark_all` and Voyager | The basemap under the dots | `© OpenStreetMap contributors © CARTO` |
| Esri World Imagery | The satellite view | `Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community` |
| AWS Terrain Tiles | The hillshade, Terrarium-encoded SRTM | `Elevation: NASA SRTM via AWS Terrain Tiles` |

MapLibre's attribution control shows a provider's credit only while a visible layer is
using it, so switching satellite off correctly stops claiming Esri.

---

## 1. What one settlement actually is

Everything on the screen is built from 1,448 rows. One row is one OpenStreetMap place node
in Sabah. It is a **point**, not a boundary, so every "within 2 km" or "within 3 km" figure
is a circle drawn around that point.

Three counts you will see repeatedly:

- **1,448** settlements in the file.
- **1,114** of them have a DIPI score.
- **334** do not, because nobody has measured them. These are Queue B.

The most important consequence, and the rule the whole product is built on: a settlement
with no speed test is **not** a settlement with no coverage. It is a settlement nobody has
tested. The dashboard refuses to score those, refuses to colour them, and refuses to let
the copilot describe them as badly served.

---

## 2. The DIPI score

**What you see.** A number from 20.2 to 76.6 on every scored settlement, and the colour of
every dot on the map.

**How it is counted.** Four pillars, weighted, times 100:

```
DIPI = 100 × (0.40 × p_connectivity
            + 0.25 × p_population
            + 0.15 × p_institutions
            + 0.20 × p_equity)
```

Each pillar is a **percentile rank** across the 1,114 scored settlements, so each one runs
0 to 1 and is uniformly spread by construction. That matters: one settlement with a wild
value cannot squash the scale for everyone else.

| Pillar | Built from | Direction |
|---|---|---|
| `p_connectivity` | `dl_mbps` | Inverted, so slower ranks higher |
| `p_population` | `pop_2km` | Higher population ranks higher |
| `p_institutions` | `n_schools_3km + n_clinics_3km` | More ranks higher |
| `p_equity` | `rwi` | Inverted, so poorer ranks higher |

**Where the weights came from.** They are the team's, not published. There is no external
authority saying connectivity deserves 40 and equity deserves 20. What the product does
instead is let you change them: the Weightings panel recomputes DIPI and the entire ranking
live, and prints how many settlements moved. If a judge disagrees with 40/25/15/20 they can
show what their own numbers produce in about five seconds.

**How to check this without believing me.** These assertions all pass against the shipped
Parquet file:

```python
import pandas as pd, numpy as np
df = pd.read_parquet("dataset/settlements/settlements_sabah_03_dipi.parquet")
s = df[df.dipi.notna()]

A = s[["p_connectivity", "p_population", "p_institutions", "p_equity"]].values
w, *_ = np.linalg.lstsq(A, s.dipi.values, rcond=None)
print(w.round(2))               # [40.00 25.00 15.01 20.00]
print(abs(A @ w - s.dipi).max())  # 0.052, the file stores DIPI to 1 dp

print(s.p_connectivity.corr((-s.dl_mbps).rank(pct=True)))   # 1.0000
print(s.p_population.corr(s.pop_2km.rank(pct=True)))        # 1.0000
print(s.p_equity.corr((-s.rwi).rank(pct=True)))             # 1.0000
```

Code: [index.html:2055-2058](../dashboard/index.html#L2055-L2058) for the weights.

---

## 3. Evidence tiers

**What you see.** Solid dots, dots with a detached amber ring, and hollow grey rings.

**How it is counted.** Purely from how many Ookla tests sit near the settlement:

| Tier | Rule | Count | Median tests | On the map |
|---|---|---|---|---|
| `measured` | `n_tests >= 20` **and** `n_tiles >= 3` | 850 | 148 | Solid dot, scored and ranked |
| `low_evidence` | `n_tests >= 5` | 264 | 11 | Detached amber ring, scored but flagged |
| `insufficient` | everything else | 334 | 0 | Hollow grey ring, **never scored** |

**Where the thresholds came from.** Ours. 20 tests across 3 tiles is a judgement about when
a median stops being noise, not a published standard. It is stated on screen wherever a tier
is shown.

---

## 4. The map

**What you see.** 1,448 circles over a basemap, plus optional layers.

**Colour.** Five bands split at the quintiles of the 1,114 scored settlements, which are
computed from the file itself: **40.0, 46.7, 53.9, 60.3**. Deep red is the top of the scale
in both themes. This is deliberate: a planner switching theme should never have the colour
change meaning underneath them.
Code: [index.html:1968](../dashboard/index.html#L1968).

**Size.** Radius grows with `pop_2km`. That is why the top DIPI band, which is now a darker
red with less raw contrast against the dark basemap, is still easy to find: those dots are
rarely the smallest ones.

**Unscored settlements.** Drawn as hollow grey rings with no fill. There is no colour band
for "unknown" because giving it a colour on the same ramp would put it somewhere on a
priority scale it does not belong on.

**Basemap.** CARTO dark_all for dark, CARTO Voyager for light. Voyager is muted at the layer
with `raster-saturation: -0.55`, not with a CSS filter, because the settlement circles are
drawn on the same canvas and a CSS filter would wash those out too.

---

## 5. The left sidebar

### Search
Plain substring match on settlement name and district. No scoring, no fuzzy matching.

### Weightings
Four sliders, one per pillar, that must total 100. Moving them recomputes
`Σ wᵢ × pᵢ × 100` for all 1,114 scored settlements and re-sorts the ranking. At the default
40/25/15/20 the dashboard shows the **file's own** `dipi` and `rank` untouched rather than
its own recomputation, because the two agree to within 0.05 across all 1,114 and showing the
file's number avoids inventing a second source of truth.

### Delivery option filter
Narrows the map to fibre, tower, satellite or community Wi-Fi settlements. It is a **filter,
not a colour**, so the dots keep their DIPI reading while filtered. See section 9 for how
each settlement gets its option.

### Layers
Facilities, cell sites, hillshade, flood. All off by default so nothing waits on a network
request at page load.

---

## 6. The drill-down panel

Click any settlement. Every tile is a stored column read straight off the file, with no
transformation, except the three marked.

| Tile | Value | Notes |
|---|---|---|
| DIPI | `dipi` | Or the live recomputation if you moved the weightings |
| Rank | `rank` | Out of 1,114 |
| Download / Upload / Latency | `dl_mbps`, `ul_mbps`, `latency_ms` | Ookla tile medians, weighted by test count |
| Tests / Tiles | `n_tests`, `n_tiles` | The evidence behind the speed |
| Population within 2 km | `pop_2km` | WorldPop raster sum. **Never sum this column across settlements**, see section 13 |
| Schools / clinics within 3 km | `n_schools_3km`, `n_clinics_3km` | Buffer counts, not catchments. A zero means none mapped in OSM, which in rural Sabah is not the same as none present |
| Relative wealth | `rwi` | Higher is wealthier. 96 settlements have no RWI cell at all |
| Elevation | `elevation_m` | Point sample from SRTM |
| Drop to nearest town | **derived** | `elevation_m` minus the elevation of the nearest town. Runs -781 m to +1,029 m |
| Elevation percentile | **derived** | Rank within its own district, so "high" is judged locally rather than against sea level. Uses average-rank percentile to match pandas `rank(pct=True)` exactly, so the copilot and the panel can never quote different numbers |
| Distance to nearest town | **derived** | `backhaul_km`, the haversine distance to the nearest of the 59 OSM towns and cities. A **stand-in** for distance to backhaul, not a survey of where fibre actually terminates |
| Stakes score, Gap rank | `stakes_score`, `gap_rank` | Only on unscored settlements, see section 11 |

**Terrain never enters DIPI.** It explains a slow link and it qualifies a siting
recommendation, and that is all. Measured against the 1,114 scored settlements, the Spearman
correlation of `elevation_m` with download speed is -0.25, `backhaul_km` is -0.10, and the
drop is -0.08. Those are weak, which is why terrain is context rather than a predictor.

---

## 7. The experience simulator

**What you see.** "What can you actually do here?" with a people slider and four tasks,
each with a verdict and a `Show the maths` expander.

**How sharing works.** Download and upload are divided by the number of people. Latency is
**not**, because latency is a round trip and does not split.

```
dl_each = dl_mbps / users
ul_each = ul_mbps / users
latency  = latency_ms          (unchanged)
```

### Reading an article
```
t = (2 MB × 8) / dl_each  +  (3 × latency_ms) / 1000
```
A 2 MB page is 16 megabits, plus three round trips of setup. Smooth at 2 s or under, may
buffer at 5 s or under, otherwise unlikely.

### Uploading a photo
```
t = (4 MB × 8) / ul_each  +  (2 × latency_ms) / 1000
```
32 megabits going **up**, plus two round trips. Smooth at 10 s, may buffer at 30 s. This is
the one that usually fails, because upload is almost always the narrow leg.

### A video call
Passes when `dl_each >= 3` **and** `ul_each >= 3` **and** `latency < 150 ms`. Marginal at
1.5 / 1.5 / 250. Each leg is shown pass or fail separately and the failing one is named,
because "upload-limited" tells a planner what to fix and "unstable" does not.

### Watching video
Five tiers with a required sustained bitrate:

| Tier | Mbps needed |
|---|---|
| 360p | 0.7 |
| 480p | 1.1 |
| 720p | 2.5 |
| 1080p | 5 |
| 4K | 20 |

Verdict rule: `smooth` if the available speed is at least 1.5x the tier, `buffer` if it is
at least 1x, otherwise `unlikely`. The 1.5x headroom is ours, and it is there because a
stream at exactly its bitrate has no room for a dip.

The video clips that play alongside are pre-encoded local files, not a live stream. They
demonstrate what the tier looks like, they do not measure anything.

### Every number in the simulator, and where it comes from

Each threshold is one of three things and the table says which. **Published** means an
official document states that exact figure. **Benchmark** means a widely measured typical
value that no single authority sets. **Ours** means we chose it, and nobody else is
responsible for it.

| Number | Where it is used | Status | Source |
|---|---|---|---|
| 0.7 / 1.1 / 2.5 / 5 / 20 Mbps | The five video tiers | **Published**, all five match exactly | [YouTube Help, system requirements](https://support.google.com/youtube/answer/78358). Google lists these as approximate speeds recommended for playing each video format |
| 1.5x tier bitrate | `smooth` on a video tier | **Ours** | Headroom for a dip. No published source states a 1.5x rule |
| 1.0x tier bitrate | `buffer` on a video tier | Implied by the above | Playing at exactly the recommended rate is the boundary case, so it is the boundary |
| 3 Mbps down | Video call passes | **Published** | [Zoom bandwidth requirements](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060748): 1080p group video calling is 3.8 Mbps up, 3.0 Mbps down |
| 3 Mbps **up** | Video call passes | **Ours**, and looser than the source | We apply 3 symmetrically. Zoom publishes **3.8** up. Upload is the leg that usually fails here, so our call verdict is slightly optimistic |
| 1.5 Mbps both legs | Video call marginal | **Published** | [FCC Broadband Speed Guide](https://www.fcc.gov/consumers/guides/broadband-speed-guide): HD personal video call, 1.5 Mbps |
| 150 ms latency | Video call passes | **Published** | [ITU-T G.114](https://www.itu.int/rec/T-REC-G.114): 0 to 150 ms is the preferred range for one-way transmission time |
| 250 ms latency | Video call marginal | **Ours** | G.114 calls 150 to 400 ms acceptable with increasing degradation. We cut at 250 rather than at the 400 ms edge, which is stricter than the standard allows |
| 2 MB | Article page weight | **Benchmark** | Roughly the median web page today. No standards body sets a page weight |
| 3 round trips | Article setup cost | **Ours** | A rough stand-in for DNS, TLS and the first request. Real pages open many connections |
| 2 s / 5 s | Article smooth / buffer | **Ours** | Not Core Web Vitals, whose LCP thresholds are 2.5 s and 4.0 s. Ours are round numbers a non-specialist can hold in their head |
| 4 MB | Photo upload size | **Benchmark** | A typical modern phone JPEG. Varies by device |
| 2 round trips | Photo setup cost | **Ours** | Same stand-in, one fewer leg than a page load |
| 10 s / 30 s | Photo smooth / buffer | **Ours** | Chosen against what a person will sit and wait for, not against a document |
| x8 | MB to Mb | Arithmetic | A byte is eight bits. Not a source, a unit conversion |
| Divide by 1 / 5 / 30 | The people slider | **Ours** | Plain division on the file's own number. The card says outright that the split is an assumption |

**The one caveat that matters on latency.** G.114 budgets **one-way mouth-to-ear** delay,
which includes the codec and the jitter buffer. `latency_ms` in our table is an Ookla
network **round trip**, which includes neither. They are not the same quantity. Using one
as the other is a working approximation, and it is the kind of thing a network engineer
will spot in ten seconds, so it is written down here rather than hidden.

**What the whole simulator is not.** Every formula above is bandwidth arithmetic on a
measured median. It has no model of TCP behaviour, congestion, jitter, packet loss, DNS
caching, CDN placement or time of day. The video-call card says this on its face: jitter
and packet loss are not in this dataset. The simulator turns an abstract Mbps figure into
a sentence a non-specialist can act on. It does not predict what will happen on any
particular device on any particular evening.

---

## 8. Nearby facilities

**What you see.** The schools and clinics within 3 km of the selected settlement, listed by
name and distance.

**How it is counted.** Haversine distance from the settlement point to each facility point,
kept if `<= 3 km`. `NEARBY_KM = 3` at [index.html:4849](../dashboard/index.html#L4849).

**Where 3 km came from.** `mcmc_jendela_schools`, the Bernama report on how JENDELA 2 targets
rural sites around schools and clinics. It is also the radius already baked into the
`n_schools_3km` and `n_clinics_3km` columns, so the panel and the pillar agree.

---

## 9. Suggested option

**What you see.** One of four options with a bulleted "why", and an `Illustrative` chip.

**How it is decided.** A rule ladder, first match wins. `km` is `backhaul_km`, `pop` is
`pop_2km`, `inst` is schools plus clinics within 3 km.
Code: [index.html:4436-4475](../dashboard/index.html#L4436-L4475).

```
if km <= 15 and pop >= 3000      ->  Fibre
elif km <= 40 and pop >= 500     ->  Tower / fixed wireless
elif km > 40                     ->  Satellite
else                             ->  Community Wi-Fi at an institution
```

Which produces, across the 1,448 settlements:

| Option | Count |
|---|---|
| Community Wi-Fi | 654 |
| Tower / fixed wireless | 449 |
| Fibre | 323 |
| Satellite | 22 |

**Where each cut-off came from.**

| Constant | Value | Status | Source |
|---|---|---|---|
| The **ordering** itself, fibre then wireless then satellite as density falls | | Sourced | `oecd_worldbank_ordering` |
| `fwa_max_km` | 40 km | Sourced | Oughton 2021, arXiv:2102.03561, the backhaul distance band used in the simulation model |
| `sat_min_km` | 40 km | Sourced | Oughton 2021, same band, the other side of it |
| `fibre_min_pop` | 3,000 | Sourced | ITU Last-mile Guide 2020, Table 28 |
| `fwa_min_pop` | 500 | Sourced | ITU Last-mile Guide 2020, Box 4 |
| `wifi_min_institutions` | 1 | Sourced | Bernama / MCMC JENDELA 2 |
| `fibre_max_km` | 15 km | **UNSOURCED** | **Ours.** No published figure gives a fibre distance limit for this context. This is the one cut-off in the ladder we cannot cite, and the panel says so on screen |
| Satellite density check | 0.1 people/hectare | Sourced | Ogutu and Oughton 2021, arXiv:2108.10834 |
| Terrain qualifies rather than decides | | Sourced | ITU Last-mile Guide 2020, Table 29 |

**The terrain caveat.** If a settlement sits 150 m or more below its nearest town, the panel
adds a line saying a line of sight to a mast there cannot be assumed. It never changes the
option. 165 settlements trip this, and 132 of those are in Ranau alone. The 150 m figure is
ours.

**What this is not.** It is a desktop screen. Australia's NBN does exactly the same thing, a
desktop prediction followed by a technician on site, which is the precedent the panel cites.
The rule screens. The field decides.

---

## 10. The coverage model

**What you see.** On 216 settlements, an estimated download speed with a range, a
`modelled estimate` label, and its top three drivers.

**How it works.** **XGBoost** regression trained on the 850 measured settlements, predicting
`dl_mbps` from geography alone. Nine features: `pop_2km`, `n_schools_3km`, `n_clinics_3km`,
`rwi`, `seasonal_water_px`, `flood_prone`, `place`, `backhaul_km`, `rwi_missing`. Fitted on
`log1p(dl_mbps)` and inverted with `expm1` before every metric, because the target is
right-skewed. Parameters: `n_estimators=400`, `learning_rate=0.05`, `max_depth=5`,
`subsample=0.8`, `colsample_bytree=0.8`, `seed=42`.

**Nothing is imputed.** Missing values stay missing, XGBoost handles NaN natively, and
missingness is expressed as its own flag. That is not a convenience, it is a leakage
guard: an imputer fitted on the training half would carry information across the fold line.

Validated with **GroupKFold by district**, because 29% of settlements share an Ookla tile
with a neighbour and a random split would put twins on both sides of the fold line.
`lon`/`lat` are excluded to stop location memorisation, and `district` is excluded because
it *is* the CV group.

| Metric | Spatial (honest) | Random (flattering) |
|---|---|---|
| MAE | 34.06 Mbps | 25.31 Mbps |
| R² | 0.330 | 0.557 |

Naive baseline MAE is 43.1 Mbps. **The 35% gap between the two validation schemes is the
finding**, not a footnote: it says the model partly memorises district-level patterns.
Per-district residuals confirm it. Six districts with 10 or more training rows exceed half the overall MAE:

| District | Mean residual | n | Reading |
|---|---|---|---|
| Tawau | **-69.32** | 12 | Worst under-prediction, but on only 12 rows |
| Tuaran | -53.73 | 51 | Worst under-prediction among the **large** districts, so the more stable figure |
| Pitas | **+32.05** | 39 | The only large positive. The model thinks Pitas is faster than it measures, so its settlements look better served than they are and get pushed **down** a ranking. Pitas is poor and rural, exactly the kind of place this project exists to surface |
| Nabawan | -23.46 | 15 | |
| Papar | -22.97 | 24 | |
| Sandakan | -18.31 | 33 | |

Raw run output in [dataset/ml/metrics.json](../dataset/ml/metrics.json), curated in [model_ablations.json](../dataset/ml/model_ablations.json).

Feature importances, from `model_report.json`:

| Feature | Importance |
|---|---|
| `pop_2km` | 0.268 |
| `rwi` | 0.222 |
| `backhaul_km` | 0.207 |
| `seasonal_water_px` | 0.068 |
| `n_schools_3km` | 0.068 |
| `place` | 0.039 |
| `n_clinics_3km` | 0.024 |
| `flood_prone` | 0.011 |

**The uncertainty band is not a confidence interval.** It is fold-ensemble disagreement, the
standard deviation across the five GroupKFold models. `model_report.json` says so in the
field name: `"uncertainty_method": "fold-ensemble disagreement (std across 5 GroupKFold
models); NOT a calibrated interval"`.

**Four model variants were tested and rejected**, recorded with their scores rather than
dropped quietly. Full table in
[dataset/ml/model_ablations.json](../dataset/ml/model_ablations.json); all five runs share
frozen folds, the same seed and the same parameters, so nothing was retuned to win.

| Model | Adds | MAE | R2 | Verdict |
|---|---|---|---|---|
| **A** | (nine base features) | **34.06** | **0.330** | **Selected.** Beats baseline by 21% |
| B1 | `elevation_m` | 34.48 | 0.312 | Rejected, worse, better in 2/5 folds |
| B2 | all three terrain columns | 34.06 | 0.317 | Rejected, MAE ties, R2 worse |
| A+div | `division` | 36.51 | 0.266 | Rejected, worse, bias unfixed |
| C | OpenCelliD counts | 36.55 | 0.262 | Rejected, worse, better in 1/5 folds |

Two of these deserve a sentence each. **Terrain was the expected win and it lost twice.**
Elevation is the strongest terrain candidate at Spearman -0.28 against speed, and it still
did not survive; adding all three columns tied on MAE and lost R2. Terrain already reaches
the model through `backhaul_km` and `place`.

**OpenCelliD failed for a data reason, not a modelling one.** 62% of settlements have no
recorded cell within 10 km, and Tawau city, 40,000 people with 205 Mbps measured, shows its
nearest record 115 km away because volunteers never surveyed there. It is a map of where
people ran the app.

**A known bias, stated rather than buried.** Six districts exceed half the overall MAE, and
19 of 25 have a negative mean residual, so the model regresses toward a Sabah-wide average.
`A+division` was the remediation attempt and it made things worse: division has only five
categories, so the model learns a division average from the districts it can see and applies
it to a held-out district at the other end of that division's range.

**Critically: no model output enters DIPI.** A predicted speed is mapped through the team's
own connectivity curve for display only. The model has no network-side feature at all, so it
infers *the kind of place that tends to be slow*, not coverage.

---

## 11. Survey planner

**What you see.** "Where to measure next", the top 10 of the 334 unmeasured settlements.

**How it is ranked.** Three groups, ranked apart, never combined into one number.

| Group | n | Ranked by | Why it is where it is |
|---|---|---|---|
| **Would settle a decision** | 14 | `measurement_priority`, 0 to 1 | The model's interval crosses the 21 Mbps line, so the measurement decides which side it falls |
| **Nothing known yet** | 223 | `stakes_score`, 0 to 100 | No usable estimate at all. 118 have no prediction whatsoever |
| **Estimate already clear of the line** | 97 | `measurement_priority` | A trip here confirms what is already believed, which is the least useful thing a field team can do |

**This replaced `stakes_score × (pred_hi - pred_lo)`, and the old formula asked the wrong
question.** Interval width rewards a settlement the model is vague about even when it is
confidently far from the threshold, where a measurement changes nothing. The two rankings
are Spearman **-0.224** and share **none of their top ten**, because width and decisiveness
genuinely point at different places.

**The third group sits below the second on purpose.** It has a number and the unknowns do
not, and it would be easy to let that put it on top. That would be exactly backwards: a
place nothing is known about is a better use of a trip than one the model is confident about.

`stakes_score` runs 28.9 to 97.1 and asks what would be at risk **if** this settlement turns
out to be badly served: population within 2 km, schools and clinics within 3 km, and relative
wealth.

**The two scales never share a column.** One is 0 to 1 from the model, the other is stakes
out of 100, and reading straight down them would compare quantities that have nothing to do
with each other. Each group carries its own header and its own count.

Published by [dataset/export_survey.py](../dataset/export_survey.py), which refuses to write
if the straddle gate stops separating the groups. Without `survey.json` the panel falls back
to stakes alone, which is what it did before the model shipped.

**This is a survey priority and never a needs score.** The dashboard never renders it as a
DIPI, and the copilot is instructed to refuse to describe it as one.

---

## 12. Deployment bundles

**What you see.** 17 fibre bundles ranked against a budget, under three named scenarios.

**How the bundles were made.** HDBSCAN over the 323 fibre-recommended settlements, then a
minimum spanning tree per bundle rooted at whichever member is closest to a town. Each
settlement's `trunk_km` is its own edge in that tree, meaning the trench it **adds**, not
the whole run to town.

DBSCAN was tried first and rejected: it chained 931 of the 1,114 settlements into one
cluster, because a single `eps` cannot fit settlements packed around Kota Kinabalu and
scattered across inland Pitas at the same time.

**The three scenarios**, each printing its own formula on screen:

| Scenario | Ranked by |
|---|---|
| Need | Median DIPI of the bundle's members, highest first. Cost ignored |
| Balanced | Median DIPI ÷ cost in RM millions |
| Reach | (settlements + schools + clinics) ÷ cost in RM millions |

**Two counting rules that are easy to get wrong.**

- **Institutions are a union, not a sum.** One school can sit within 3 km of settlements in
  two different bundles. Adding the per-bundle counts would fund it twice, so the portfolio
  deduplicates by `facility_id`.
- **People are never totalled at all.** See section 13.

**The panel states its own limit.** Fibre needs 3,000 people within 2 km, so only **6 of the
top 50 by DIPI** appear in any bundle. The top 50 actually splits like this:

| Option for the top 50 by DIPI | Count |
|---|---|
| Tower / fixed wireless | 31 |
| Community Wi-Fi | 13 |
| Fibre | 6 |

That is the answer to "why does the bundles panel point at denser places than the ranking
does". The most urgent settlements in Sabah are overwhelmingly **tower** settlements, and
the bundles panel is a fibre panel. It ranks fibre builds. It does not rank the priority
list, and it says so on screen.

---

## 13. Budget what-if, the price counting

This is the part that is easiest to misread, so it gets a full worked example.

### 13.1 The unit costs

```js
low:  { fibre_per_km:  90000, fwa_per_site: 350000, satellite_per_terminal:  9000, wifi_per_site:  45000 }
base: { fibre_per_km: 140000, fwa_per_site: 520000, satellite_per_terminal: 14000, wifi_per_site:  70000 }
high: { fibre_per_km: 210000, fwa_per_site: 780000, satellite_per_terminal: 21000, wifi_per_site: 105000 }
```

Code: [index.html:4503-4507](../dashboard/index.html#L4503-L4507).

**No per-unit Malaysian price is published.** The code says this out loud with
`const COSTS_VERIFIED = false`. The base figures are benchmarked, not quoted:

- **RM 140,000 per km fibre** comes from Oughton 2021 (arXiv:2102.03561), page 13, which
  gives $25 / $15 / $10 per metre for urban / suburban / rural fibre. The low/base/high
  spread here is that same three-way split, converted and rounded.
- **RM 520,000 per mast** comes from Oughton 2021, page 12, "$47k to build a full 30m tower",
  plus that paper's backhaul figures of $10k / $20k / $40k. Cross-checked against MCMC's USP
  Annual Report 2024: RM 801m across 823 towers is about RM 973k per site all-in, which sits
  above our build-only figure, as it should.
- Satellite terminal and Wi-Fi site figures are the weakest of the four and are placeholders
  in the same spirit.

**You can overwrite them.** Type your own RM per km or RM per site into the panel and both
the budget and the bundles panels reprice, and each then states whose figure produced the
result. A blank, a zero or anything unparseable all fall back to the benchmark rather than
to zero, because "costs nothing" would fund every settlement at once.

### 13.2 What one settlement costs

Three of the four options are flat per site. Only fibre is per kilometre.

```js
Fibre:      fibre_per_km × max(1, min(trunk_km, backhaul_km))
Tower:      fwa_per_site
Satellite:  satellite_per_terminal
Wi-Fi:      wifi_per_site
```

Code: [index.html:4522-4550](../dashboard/index.html#L4522-L4550).

The fibre line does three things at once, and each is there for a reason:

**`trunk_km`, not `backhaul_km`.** The spanning-tree edge is the trench this settlement
*adds*. Ten villages along one road used to be billed for the whole road ten times over.

**`min(trunk_km, backhaul_km)`, because sharing is not always cheaper.** 22 of the 288
bundled settlements sit further from their nearest bundle neighbour than from the town
itself. Charging the spur regardless wasted 254.1 km, about RM 35.6m. A real planner takes
whichever run is shorter, so the cost does too.

Over the 323 fibre settlements, the three ways of counting give very different answers:

| Rule | Trench | Cost at RM 140k/km |
|---|---|---|
| Each settlement pays its own full run to town | 1,363.5 km | RM 190.9m |
| Each pays only its spanning-tree spur | 890.0 km | RM 124.6m |
| **`min(spur, own run)`, what the panel charges** | **635.9 km** | **RM 89.0m** |

The first-to-second step is the 1.53× overstatement `export_clusters.py` prints. The
second-to-third step is the `min`, worth another 254.1 km on just 22 settlements. Run
`python dataset/export_clusters.py` and it prints the first two lines itself.

**`max(1, ...)`, the 1 km floor, sits outside both.** Kota Kinabalu itself has a
`backhaul_km` of 0.00, because it *is* the town. Without the floor it would cost nothing,
and dividing people by zero cost would put it at the very top of the funding queue forever.

### 13.3 Four worked examples, from the real file, base case

**Fibre where sharing helps.** Lintas, Kota Kinabalu. 74,688 people within 2 km. Its own run
to town is 3.95 km, but its spanning-tree edge is only 2.12 km because a neighbour already
carries the trench most of the way.

```
min(2.12, 3.95) = 2.12 km
max(1, 2.12)    = 2.12 km
2.12 × RM 140,000 = RM 296,800
```

**Fibre where the cap bites.** Pingan Pingan, Pitas. 5,724 people. Its spanning-tree edge is
25.93 km, which is *longer* than its own 14.84 km run straight to town. So it is billed the
direct run:

```
min(25.93, 14.84) = 14.84 km
14.84 × RM 140,000 = RM 2,077,600
```

Without the `min`, this one settlement would have been charged RM 3,630,200, RM 1.55m too
much.

**Fibre where the floor bites.** Kota Kinabalu itself. `backhaul_km` is 0.00.

```
min(1.00, 0.00) = 0.00 km
max(1, 0.00)    = 1.00 km       <- the floor
1.00 × RM 140,000 = RM 140,000
```

**The three flat options.** Telaga in Pitas, 1,367 people, 12.32 km out: Tower, a flat
**RM 520,000**. Kampung Karagasan in Ranau, 84 people, 42.0 km out: Satellite, a flat
**RM 14,000**. Mangkubau Laut in Pitas, no anchor institution: Wi-Fi, a flat **RM 70,000**.

A mast or a satellite terminal costs the same whether or not a neighbour already has one,
which is precisely why `trunk_km` is used by fibre and by nothing else.

### 13.4 How the budget picks who gets funded

This is the part that surprises people, so read it slowly.

```js
ratio = pop_2km / cost                       // people served per ringgit
sort every settlement by ratio, highest first
spent = 0
for each settlement in that order:
    if spent + cost > budget: skip it and keep going   // skip, not stop
    spent += cost
```

Code: [index.html:4554-4581](../dashboard/index.html#L4554-L4581).

**It funds by people per ringgit. It does not fund by DIPI.** This is the single most
important sentence in this document. A settlement can be number 1 on the priority list and
never get funded, because a cheap dense one 300 places below it serves more people per
ringgit. Here are the actual top six of the queue at the base case:

| Settlement | District | Option | People | Cost | People per RM |
|---|---|---|---|---|---|
| Luyang | Kota Kinabalu | Fibre | 70,890 | RM 140,000 | 0.5064 |
| Sembulan | Kota Kinabalu | Fibre | 68,654 | RM 140,000 | 0.4904 |
| Karamunsing | Kota Kinabalu | Fibre | 62,928 | RM 140,000 | 0.4495 |
| Kampung Sembulan Lama | Kota Kinabalu | Fibre | 61,286 | RM 140,000 | 0.4378 |
| Kampung Setinggan Sembulan | Kota Kinabalu | Fibre | 59,310 | RM 140,000 | 0.4236 |
| Bundusan | Kota Kinabalu | Fibre | 51,347 | RM 141,400 | 0.3631 |

Every one of them is urban Kota Kinabalu. That is the algorithm working exactly as written,
and it is also the honest tension in the tool: **cheapest-per-head and most-urgent genuinely
disagree**, and the dashboard shows you both rather than hiding one behind the other.

At **RM 50m in the base case it funds 271 settlements** and spends RM 50.0m almost exactly.
The last one in is Salulong, a satellite terminal at RM 14,000 for 207 people. Of the 271:
263 fibre, 5 satellite, 3 tower.

**`continue`, not `break`.** When a settlement is too expensive to fit, the loop skips it and
keeps looking. So one expensive settlement cannot end the list early, and the tail fills up
with cheap satellite terminals. This makes it a **greedy heuristic and not an optimiser**:
some other combination could fit the same money and serve more people. The card says so.

**Why greedy and not exact.** An exact knapsack over 1,448 items is not worth the runtime in
a browser panel that reruns on every keystroke.

### 13.5 Why there is no total population figure

`pop_2km` is a **2 km buffer around a point**, and rural settlements sit far closer together
than 4 km apart. Summing the column counts the same villagers once per neighbour. Measured
across Ranau's 249 settlements, naively summing turns 22,303 into 566,012, a factor of
**25**.
Most of any "population affected" total built that way is the same people over and over.

So the budget panel reports **counts of settlements, how many have a school, how many have a
clinic, and a median population**. It never prints a total. Where a deduplicated figure is
genuinely needed, as in the Compare view, settlements whose buffers touch (within 4 km) are
linked with union-find and one figure is taken per cluster.
Code: [index.html:6020-6038](../dashboard/index.html#L6020-L6038).

### 13.6 Is the arithmetic right?

Tested, not asserted. `agent/test_agent.py` runs 191 assertions, one of which drives the
Python side of the copilot and the JavaScript in the dashboard through the same budget and
checks they fund **the same settlements**: at RM 50m they both fund **358, 271 and 203**
across the low, base and high cost cases. That check has caught two real divergences.

### 13.7 What is still a known bias

Two, both disclosed here rather than buried:

1. **It funds by population per ringgit, not by DIPI.** Section 13.4. Cheap and dense beats
   expensive and remote, every time.
2. **`pop_2km` overlap mildly favours clustered settlements** even inside the ranking,
   because a village with three neighbours inside its buffer carries their people in its own
   figure.

Both push in the same direction, toward the cheap and the dense. A user reading the funded
list without reading this section would reasonably assume it funds the top of the priority
list. It does not.

---

## 14. The cell sites layer

**What you see.** 1,217 recorded cell sites, clustered at low zoom, off until you ask for it.

**Where they came from.** OpenCelliD, which is **crowdsourced**.

**What it is deliberately not.** It is never a model feature. The number of records near a
settlement correlates **0.56** with that settlement's Ookla test count, which means it
records *where volunteers happened to survey*, not what is built. Tawau city, 40,000 people
with 205 Mbps measured, has its nearest OpenCelliD record 115 km away. 62% of settlements
have nothing within 10 km.

It was tested as a feature anyway and rejected: worse overall, better in 1 of 5 folds. The
layer tells you an area has not been surveyed. That is not the same as an area with no tower,
and the legend says so.

---

## 15. Rankings

**What you see.** A sortable table of all 1,114 scored settlements, plus a separate Queue B
table for the 334 unscored.

Every column is a stored value or a live recomputation from the weightings. Sorting is a
plain numeric sort. The KPI strip above the table counts rows in the current filter.

**Two columns are context rather than score**, sitting after Elevation and before Evidence:

| Column | Shows | Note |
|---|---|---|
| **Light** | peak VIIRS radiance 2013 to 2025, or **None** | An unlit settlement reads `None` in amber, not an em dash, because it was **measured and found dark**. That is a different thing from unknown, and it sorts as a measured zero rather than sinking with the missing values |
| **Water** | `Adjacent` when `flood_prone` | JRC surface water, which includes coastal and tidal zones, so it is adjacency and not a flood model |

Both carry tooltips saying they are never part of the score. A **No grid light** filter chip
sits beside the existing **Flood context** chip and narrows the table to the 414 scored
settlements that register nothing.

Neither enters DIPI, the ranking or the recommended option. They are in the table because the
rankings view is the detailed data view, and a planner comparing two settlements at the same
DIPI has a real reason to know that one of them needs its own generator.

The two tables are kept apart on purpose. `gap_rank` and `stakes_score` never appear in the
same column as `dipi` and `rank`, because they are not the same kind of number and putting
them in one list would imply an ordering between them that does not exist.

**Queue B is a field-visit queue, so it carries what decides whether the trip is worth it**:
why the row is where it is, stakes, a modelled speed estimate with its spread, distance to
the nearest town, population, schools, clinics, nighttime light and water adjacency. The
estimate is marked as modelled everywhere it appears and is never a measurement; settlements
the model could not reach read `Not modelled` rather than a zero.

**It is ordered by the same rule as the sidebar panel**, and the `Would settle` column names
it: `Crosses the line`, then `Nothing known`, then `Clear of the line`. It used to order by
the stored `gap_rank`, which ranks on stakes alone. That left the same 334 settlements in two
different orders in two views with nothing on screen to explain the difference, which is the
same failure as the notebook and the panel disagreeing. One queue, one order.

The `Est. speed` column makes the first group self-evident: read the top rows and every
range spans 21, 25.7 ±7, 23.0 ±4, 17.1 ±6.

---

## 16. District, division and settlement comparison

**What you see.** Any number of districts or divisions side by side, with a metric table and
a radar profile. A third mode compares **individual settlements**, up to 20.

### The settlement mode

Districts fit in a grid of chips; 1,448 settlements do not, so this level **searches** by name
or district instead of listing, and the chips below become the selection rather than the menu.
Click a chip to remove it. The cap is 20.

It has **its own row set and its own renderer**, and that is deliberate. Running `areaStats()`
over a single settlement produces figures a reader has to squint past: "settlements screened 1",
"underserved rate 100%", a median that is just the value. The settlement table instead shows
the fields that actually differ between two places a planner is choosing between: DIPI and
rank, the four pillars, download, upload, latency, speed source, evidence tier, tests, people,
schools, clinics, wealth, distance to town, elevation, drop, nighttime light, water, and the
suggested option.

**Three things are deliberately absent from this mode.**

- **No radar.** Its axes are "percentile of badness against all 25 districts", which is a
  category error for a single point.
- **No bars or thumbnails.** A settlement is a point and has no shape to draw.
- **No Sabah reference column.** A state-wide median is not a like-for-like peer for one
  settlement, and putting it in the same row would invite reading it as one.

Print and the PDF export work unchanged, because the mode reuses the same sheet.

**How each metric is counted.** From `areaStats()` at
[index.html:6043-6076](../dashboard/index.html#L6043-L6076).

| Metric | How |
|---|---|
| Median download / upload / latency | Median across measured settlements only |
| Underserved rate | Share of **measured** settlements below **21 Mbps** |
| Severe rate | Share below 0.7 Mbps, the 360p floor |
| People underserved | Deduplicated population of the underserved settlements, union-find at 4 km |
| Evidence gap | Share of settlements in the `insufficient` tier |
| Remote rate | Share more than 20 km from a town |
| Terrain shadow | Share sitting 150 m or more below their nearest town |
| No detectable grid light | Share with no VIIRS radiance in 13 years. **Null, not zero**, if `power.json` is absent, so a missing file reads as not known rather than as everywhere has power |
| Seasonal water adjacent | Share flagged by JRC |
| Median DIPI, top DIPI, count in Sabah's top 100 | Across scored settlements only |

**Where 21 Mbps came from.** It is `0.7 × 30`: the 360p floor of 0.7 Mbps, shared 30 ways.
That is our definition of "underserved", built from the video ladder rather than borrowed
from a regulator, and the tooltip says so.

**The one rule enforced everywhere in this function.** A settlement in the `insufficient`
tier is excluded from every speed statistic even when it carries a `dl_mbps`, because that
figure sits on a median of zero tests. Judging service from those would turn "not measured"
into "poorly served". They are counted in the evidence gap instead.

**Why grid light and water are table rows and not radar axes.** The radar is a profile of
**need**, and being unlit is not a need, it is a **build condition**. A district where every
settlement is dark is not worse served, it is more expensive to serve. Putting electrification
on an axis labelled badness would make exactly the conflation the whole product refuses. The
table row states the fact; the radar keeps its six axes.

**The radar.** Every axis is the **percentile of badness against all 25 districts**. That puts
a percentage, a speed and a headcount on one honest 0 to 100 scale without inventing a
composite score, and the *shape* tells you which kind of need an area has rather than just
how much.

---

## 17. Ask Dino

**What you see.** A chat panel that answers questions about what is on screen.

**How it answers.** A LangGraph agent with a set of tools that recompute from the same
arithmetic described above. When you ask about a comparison or a bundle, the panel's current
settings are sent as context and the agent **recomputes** rather than trusting numbers the
client sent it.

Constraints that are enforced in the agent, not just requested in the prompt:

- It never describes an unmeasured settlement as badly served.
- It refuses to call a bundle a build plan. Bundles are a proximity screen.
- Its budget arithmetic is parity-tested against the dashboard, see section 13.6.

**The dashboard never hard-depends on this.** If the agent server is down, every panel above
still works. The chat panel says it is unavailable and nothing else changes.

---

## 18. Tower scenarios, computed offline

Not in the dashboard yet, but it is where the tower numbers in
[deployment_clusters.md](deployment_clusters.md) come from, and judges ask.

The bundles panel prices a tower at one mast per settlement, RM 233.5m across the 449
tower-recommended settlements. That is too high, because one mast serves several villages.
`dataset/tower_scenarios.py` runs a **greedy set-cover heuristic** over the settlement
coordinates. That first pass was **distance only**: it assumed every path inside the radius
worked.

It does not. `dataset/tower_los.py` re-runs the same greedy set-cover heuristic over only the paths that
survive a terrain screen against SRTM, and the difference is the point of the exercise.

**The one-line version, if you read nothing else in this section:** distance alone suggested
**86 to 189** masts; terrain-aware screening suggests **240 to 274**. And after terrain, the
assumed radius matters much less than it did.

**How many of the 10,070 candidate paths survive:**

| Radius | Paths | Clear line of sight | 60% Fresnel clear |
|---|---|---|---|
| 3 km | 1,412 | 880 (62.3%) | 712 (50.4%) |
| 5 km | 2,596 | 1,320 (50.8%) | 939 (36.2%) |
| 10 km | 6,062 | 2,011 (33.2%) | 1,157 (**19.1%**) |

Median path clearance is **-9.0 m**, meaning more than half of all candidate paths are
blocked outright. Quartiles run -61.9 / -9.0 / +7.7 m. Zero DEM voids, so the raster covers
every endpoint.

**What that does to the mast count:**

| Radius | Masts, distance | Masts, LoS | Masts, Fresnel | Cost, distance | Cost, Fresnel |
|---|---|---|---|---|---|
| 3 km | 189 | 256 | **274** | RM 98.3m | RM 142.5m |
| 5 km | 145 | 222 | **253** | RM 75.4m | RM 131.6m |
| 10 km | 86 | 192 | **240** | RM 44.7m | RM 124.8m |

**The headline is not that the count went up. It is that the radius stopped mattering
much.** Distance-only, the choice of radius swung the answer by **RM 53.6m**, and that
unsourced radius was the single largest open item in the project. Screened, the same choice
swings it by **RM 17.7m**. Buying more reach stops helping once four paths in five are
blocked, so the parameter nobody can cite now moves the answer three times less than it did.

The optimistic end is gone with it. RM 44.7m at 10 km assumed every in-radius path was
clear. The real figure at 10 km is RM 124.8m.

**Terrain isolation is worse than the distance figures implied.** The count of settlements
that no other site can reach, so they force a mast of their own:

| Radius | Isolated, distance | Isolated, Fresnel |
|---|---|---|
| 3 km | 92 | 191 |
| 5 km | 60 | 169 |
| 10 km | 23 | **157** |

At 10 km, **157 of 449 tower settlements can only be served by a mast in their own
village**. Distance-only said 23. The screen is not symmetric, because the mast is 30 m and
the receiver is 10 m, so 100 of the 712 clear paths at 3 km work in one direction only. This
count is therefore "what can reach this settlement", not "what does this site serve". A third of the tower problem in Sabah is not a coverage
optimisation at all.

Mean distance to the serving mast **falls** under the screen, 3.97 km to 1.10 km at 10 km,
because the paths that survive are the short ones. That is not an improvement, it is the
same finding stated the other way round.

### What the screen assumed

| Assumption | Value | Status |
|---|---|---|
| Mast height | 30 m | **Sourced.** Oughton 2021, arXiv:2102.03561, p12 |
| Receiver height | 10 m | **UNSOURCED, ours**, and it moves the answer |
| Band | 700 MHz | **Sourced, and the effect is bounded.** See below |
| Earth radius factor | 4/3 | Standard refraction allowance |
| Fresnel clearance | 60% of the first zone | Standard planning rule. [ITU-R P.530](https://www.itu.int/rec/R-REC-P.530/en) treats clearance as **one** input alongside fading, rain and multipath, none of which are modelled here |

**The band is confirmed, and it turns out not to matter much.** 700 MHz is Malaysia's
assigned sub-1 GHz coverage band: Digital Nasional Berhad holds 2×20 MHz (703-723 and
758-778 MHz) from 2021, and Ministerial Direction No. 1 of 2024 assigned two further 20 MHz
blocks to U Mobile. [MCMC spectrum
assignment](https://www.mcmc.gov.my/en/spectrum/assignment-of-spectrum/spectrum-assignment).

What is still ours is assuming a rural Sabah mast would use it rather than a higher band.
That residual is **bounded, and the bound is already in the table above**. 700 MHz is the
lowest assigned band, so it has the widest Fresnel zone and is the **strictest plausible
screen**. Any higher band passes more paths, and as frequency rises the Fresnel zone shrinks
toward zero, at which point the test becomes plain line of sight. So the answer for **any**
band sits between the Fresnel column and the LoS column:

| Radius | Blocked by terrain at any frequency | In play at all | Masts, 700 MHz | Masts, any higher band |
|---|---|---|---|---|
| 3 km | 532 (37.7%) | 168 (11.9%) | 274 | down to 256 |
| 5 km | 1,276 (49.2%) | 381 (14.7%) | 253 | down to 222 |
| 10 km | 4,051 (66.8%) | 854 (14.1%) | 240 | down to 192 |

At 10 km that is **RM 124.8m to RM 99.8m**, against RM 44.7m distance-only. A path blocked
by terrain stays blocked at every frequency, and two thirds of the 10 km paths are in that
category, so the band can only move the one path in seven that clears the ground but not the
Fresnel zone.

### What it still is not

A terrain screen is not a propagation model. It says a path is geometrically blocked. It
does not say a clear path delivers a usable signal. No ground cover, no clutter loss, no
interference, no capacity. ITU-R P.1812 is the real calculation.

**SRTM is C-band radar**, so over dense forest the returned surface sits partway up the
canopy rather than at ground level. That cuts both ways: this screen **over-blocks cleared
land** whose true ground is lower than the reading, and **under-blocks tall forest** a real
signal would still have to pass through. Sabah is heavily forested, so both errors are
live. The screen narrows the radius uncertainty. It does not close it.

**Mast sites are settlement-centre proxies.** Every one is a real village already in
`training_table.csv`. The algorithm **selects** existing coordinates, it does not fabricate
locations. Nobody has checked land, access or planning at any of them. Power is screened by nighttime light only, see §19, which tells you a site has no detectable radiance and not that it has no grid connection.

`tower_pairs.csv` exports **all 10,070 in-radius paths**, in both directions, with a
`chosen_by_distance` flag, rather than only the 927 this run picked. That way the selection
can be rebuilt from whatever survives a terrain screen later.

---

## 19. Nightlights, tested and rejected

Not on the screen, and that is the finding. Full writeup in
[viirs_nightlights.md](viirs_nightlights.md).

**What was tried.** Thirteen years of VIIRS nighttime radiance (NOAA VNL V2 annual composites,
2013 to 2025), **max within 1 km**, for all 1,448 settlements. 18,824 rows, no gaps. Every
figure below is recomputed from [viirs_annual_max1km.csv](../dataset/ml/viirs_annual_max1km.csv)
and [viirs_trend.csv](../dataset/ml/viirs_trend.csv), which are in the repo.

**Why it is not a feature.** **703 of 1,448** settlements register no detectable radiance in any
of the thirteen years, and the 745 that do are largely the bright places that already carry
solid Ookla measurements. **192 of the 216 unmeasured settlements are dark, 89%**, and the 24 that are lit sit barely
over the cutoff, peaking at 1.39 against a 0.5 threshold. A feature that is blank for nine
rows in ten and near noise on the rest adds nothing.

It failed one step earlier than OpenCelliD. OpenCelliD was fitted and scored (model C, MAE
36.55 against 34.06). VIIRS was cut at **feature availability**, before fitting, because a
column blank for the rows you need cannot be scored fairly.

**We got this wrong once, and the correction is the useful part.** The first pass used a **mean
over a 2 km buffer**, about 50 pixels, so a settlement lighting one or two of them was divided
by fifty. It reported 778 dark. Worse, we swept the *threshold* and called the result
conclusive, when a 5x threshold relaxation cannot answer a 50x dilution.

| Threshold | Mean over 2 km (old) | **Max within 1 km (shipped)** |
|---|---|---|
| 0.5 | 400 lit | **745 lit** |
| 0.25 | 519 lit | **798 lit** |
| 0.1 | 670 lit | **804 lit** |

The old column is still climbing at the bottom, the signature of signal under the cutoff. The
new one is **nearly flat**, which is what a real detection floor looks like. The threshold is no
longer load-bearing, and that is now demonstrated rather than asserted.

**The correction also killed a claim we might have made.** Brightening went 278 to 276 while
lit rose from 400 to 745, so all 345 newly-lit settlements landed in flat or dimming. The
diluted series made brightening look like **70% of lit settlements**; the real figure is **37%**,
against 57% flat. "Sabah is electrifying rapidly" is not supported. Of the 31 dimming, a further
16 are held separately as `flat_urban_artefact`: VIIRS DNB cannot sense blue, so sodium-to-LED
street lighting reads as falling radiance in exactly the brightest urban centres.

**What survives.** One constraint: *703 of 1,448 settlements show no detectable nighttime light
in thirteen years, so any option sited there must supply its own power.* That is **stronger**
than the 778 it replaces, because 778 rested on a method that could explain most of itself.

**And one finding that came free on a join.** Crossing the terrain screen's isolated settlements
with `ever_lit` gives **67 / 58 / 56** settlements at 3 / 5 / 10 km that need **their own mast
and their own power**. That is a different cost class, neither analysis can see it alone, and it
barely moves across radii so it does not lean on the unsourced reach assumption.

**What ships.** Three things. A line under the suggested option, *"no detectable nighttime
light in 13 years of VIIRS, so this site likely needs its own power"*. The join on the mast
panel's self-site tile. And a **night view** in Layers that renders Sabah as VIIRS recorded it:
basemap at a quarter, DIPI dots at a tenth, and the 745 lit settlements glowing amber scaled by
peak radiance.

**What is enforced**, each with a browser test: the flag never changes the recommended option,
never touches DIPI or rank, the night view restores the basemap and legend exactly when
switched off, and the trend classes are never sent to the client. A missing `power.json` drops
all three rather than claiming a site has power.

**The night view is a mode, not an overlay**, and that distinction is the whole permission for
it. An unlit overlay on the priority map says *these places are worse*, which the data does not
know. A night view dims the priority colouring away and says *these places emitted no light*,
which is precisely what the data knows, drawn as measured radiance rather than as a binary. The
legend says **electrification, not coverage** and warns that these are settlement points rather
than the satellite raster.

**The line this must never cross.** Nightlights measure electrification, not connectivity. A
dark settlement may have perfectly good mobile service; it has no grid. If `dark` were ever
drawn or read as "no coverage", it would break the rule the entire product is built on. It is
not an input to DIPI and it is not a coverage statement, and the reason there is no map layer
is that a dark dot on a priority map would say exactly that without a word being written.

---

## 20. Every constant in one place

| Constant | Value | Where used | Status |
|---|---|---|---|
| DIPI weights | 40 / 25 / 15 / 20 | Score | **Ours**, and adjustable on screen |
| DIPI colour breaks | 40.0 / 46.7 / 53.9 / 60.3 | Map | Computed from the file, the quintiles |
| `measured` tier | 20 tests, 3 tiles | Everywhere | **Ours** |
| `low_evidence` tier | 5 tests | Everywhere | **Ours** |
| Population buffer | 2 km | `pop_2km` | Pipeline choice |
| Facility buffer | 3 km | `n_schools_3km`, `n_clinics_3km`, Nearby panel | Bernama / MCMC JENDELA 2 |
| `fibre_max_km` | 15 km | Recommender | **UNSOURCED, ours** |
| `fibre_min_pop` | 3,000 | Recommender | ITU D-TND-01-2020, Table 28 |
| `fwa_max_km` | 40 km | Recommender | Oughton 2021, arXiv:2102.03561 |
| `fwa_min_pop` | 500 | Recommender | ITU D-TND-01-2020, Box 4 |
| `sat_min_km` | 40 km | Recommender | Oughton 2021 |
| `wifi_min_institutions` | 1 | Recommender | Bernama / MCMC |
| Satellite density check | 0.1 people/ha | Recommender sanity check | Ogutu and Oughton 2021 |
| Terrain shadow | -150 m | Siting caveat | **Ours** |
| Fibre, per km | RM 90k / 140k / 210k | Costing | Benchmarked from Oughton 2021 p13 |
| Mast, per site | RM 350k / 520k / 780k | Costing | Benchmarked from Oughton 2021 p12, cross-checked against MCMC USP 2024 |
| Satellite, per terminal | RM 9k / 14k / 21k | Costing | Benchmarked, weak |
| Wi-Fi, per site | RM 45k / 70k / 105k | Costing | Benchmarked, weak |
| Trench floor | 1 km | Costing | **Ours**, a guard against divide-by-zero |
| Video ladder | 0.7 / 1.1 / 2.5 / 5 / 20 Mbps | Simulator | YouTube Help, system requirements. All five tiers match exactly |
| Smooth headroom | 1.5x the tier | Simulator | **Ours** |
| Video call, pass | 3 Mbps down | Simulator | Zoom, 1080p group video calling |
| Video call, pass | 3 Mbps up | Simulator | **Ours**. Zoom publishes 3.8, so ours is looser |
| Video call, pass | 150 ms | Simulator | ITU-T G.114 preferred range |
| Video call, marginal | 1.5 Mbps both legs | Simulator | FCC Broadband Speed Guide, HD personal video call |
| Video call, marginal | 250 ms | Simulator | **Ours**, stricter than G.114's 400 ms edge |
| Article page | 2 MB, 3 round trips, 2 s / 5 s | Simulator | Weight is a benchmark, the rest is **ours** |
| Photo upload | 4 MB, 2 round trips, 10 s / 30 s | Simulator | Size is a benchmark, the rest is **ours** |
| Underserved | 21 Mbps | Compare | **Ours**, 0.7 × 30 users |
| Remote | 20 km | Compare | **Ours** |
| Population dedup link | 4 km | Compare | **Ours**, two 2 km buffers touching |
| Mast height | 30 m | Tower scenarios | Oughton 2021 p12 |
| Mast reach | 3 / 5 / 8 / 10 km | Tower scenarios | **UNSOURCED**, which is why it is shown as a range and never as one figure |

---

## 21. The honest list of what is not sourced

Read this before quoting anything above in a submission.

1. **The DIPI weights.** Ours. Mitigated by making them adjustable and showing how many
   settlements move when you change them.
2. **The evidence tier thresholds.** Ours.
3. **`fibre_max_km = 15`.** The only cut-off in the recommender ladder with no citation.
4. **Every ringgit figure.** `COSTS_VERIFIED = false` is in the code. No Malaysian per-unit
   price is published. The figures are benchmarked against Oughton 2021 and sanity-checked
   against MCMC's own aggregate, which is not the same as being quoted. This is why the
   budget panel reports a **range across three cost cases** rather than one confident number,
   and why you can type your own.
5. **The simulator's own thresholds.** The bitrate ladder is now pinned to YouTube's
   published table and every tier matches, so the ladder itself is no longer the weak
   spot. What is still ours is the *judgement* layer on top of it: the 1.5x smooth
   headroom, the 2 s and 5 s article cutoffs, the 10 s and 30 s photo cutoffs, and the
   250 ms marginal latency. Two further points are worth stating rather than burying.
   The 3 Mbps upload gate is **looser** than Zoom's published 3.8 Mbps, so the call
   verdict leans optimistic on the leg most likely to fail. And ITU-T G.114's 150 ms is a
   **one-way mouth-to-ear** budget while `latency_ms` is a network **round trip**, so
   the comparison is an approximation and not a conformance test.
6. **The mast reach radius.** Was the single largest open item, swinging the tower answer by
   RM 53.6m. The terrain screen in section 18 has cut that to RM 17.7m, because once four
   paths in five are blocked, extra reach stops buying coverage. Still unsourced, now much
   less load-bearing. The band has since been confirmed as Malaysia's assigned sub-1 GHz
   coverage spectrum, and its residual effect is bounded between the Fresnel and LoS columns,
   240 down to 192 masts at 10 km. **The receiver height of 10 m is now the screen's only
   unsourced input**, and it moves the answer.
8. **The 0.5 nightlight threshold** that separates lit from dark in §19. Ours, but now
   tightly bounded: **745 / 798 / 804** settlements are lit at 0.5 / 0.25 / 0.1, so relaxing all
   the way to VIIRS's noise floor moves the count by 59 of 1,448. An earlier version of this
   entry quoted 400 / 519 / 670 from a reducer that diluted small settlements by about 50x, and
   claimed the sweep settled the question when it could not.
9. **`backhaul_km` is a proxy.** It is the distance to the nearest OSM town or city, not a
   survey of where fibre actually terminates. Every cost that depends on distance inherits
   that assumption.

And one thing that is not a limitation but is worth stating plainly, because it is the
design decision the whole product rests on: **missing data is never treated as poor
service.** 334 settlements have no score, no colour band and no place in any speed
statistic, and they appear only in a survey queue that says out loud it is a survey queue.

# Deployment bundles, not a ranked list

**A response to judging feedback on DIPI ordering, and where spatial ML fits.**

> "We have DIPIs of settlements, but it might not make the most logical sense to develop
> settlements by their DIPI ranking alone, since they may be far apart (eg number 1 at the
> east, number 2 at the far west). Hence, an idea is to suggest a route for the developer,
> taking into account resource constraints and its greatest impact. How feasible is this
> idea and how may we approach this?"

The criticism was correct, and it was worse than it first appeared: ranking settlements one
at a time also **mis-priced the work**, because two villages that would share one trench
were each billed for the whole thing.

This document records what we measured, what we built, and the two places where a first
attempt was wrong and had to be replaced.

---

## 1. The problem in plain words

Picture 10 villages strung along one road, all about 15 km from town. The tool used to
charge **each village for its own cable all the way back to town**: ten times fifteen
kilometres, 150 km of digging. Nobody builds that way. The cable reaching village 10
already passes villages 1 to 9.

A **bundle** is a group of villages close enough that one build serves all of them. What
changed on screen is that the panel stopped listing settlements and started listing bundles,
each with a price, ranked against a budget.

**DIPI still decides who matters.** Bundling only decides who gets built together.

---

## 2. What the mis-pricing cost

Over the 323 settlements the recommender sends to fibre:

| | Trench | At RM 140,000/km |
|---|---|---|
| Each settlement billed its own full run to town | 1,363 km | RM 190.9m |
| Each billed the shared spur instead | 890 km | RM 124.6m |
| **Each billed the cheaper of the two** | **636 km** | **RM 89.0m** |

**206 of the 323 get cheaper.** The middle row is not the answer, which is the first thing
we got wrong: **sharing is not always cheaper.** 22 settlements sit further from their
nearest bundle neighbour than from the town itself, so charging the spur regardless wasted
254 km. A planner takes whichever run is shorter, so the cost does too.

---

## 3. Feasibility: "route" means three different things

| What is meant | Feasible? |
|---|---|
| **Which group to build first.** | **Yes, and it shipped.** §5. |
| **Road distances and driving time.** | Yes with work. OSM publishes Sabah's roads and we already use OSM, so it is an extraction job rather than a missing dataset. |
| **A dispatch plan.** Crews, vehicles, time windows. | No, and not our job. That is an operator's scheduling system. |

Until roads are extracted every distance here is straight line, so the output is a
**screening proxy**, never an engineering design.

---

## 4. The clustering, including the run that failed

Spatial clustering is the taught technique that fits, so we ran it before recommending it.

**DBSCAN collapsed.** On raw coordinates at `eps = 15 km` it produced 12 clusters, one of
which held **931 of the 1,114** scored settlements: Sabah's settlements form a connected
chain and single-linkage walks the whole province.

| eps | Clusters | Biggest | Noise |
|---|---|---|---|
| 3 km | 65 | 137 | 238 |
| 8 km | 33 | 645 | 60 |
| 15 km | 12 | **931** | 18 |

**HDBSCAN fixed it for the right reason.** The chaining is not bad luck, it is `eps` being a
single global number: settlements are packed near towns and scattered inland, and no one
radius fits both. HDBSCAN builds a hierarchy and cuts it per region. It also removes the
"why 10 km?" question, which has no good answer.

Run on the **323 fibre settlements only**, `min_cluster_size = 5`, haversine:

> **17 bundles holding 288 settlements. 35 stay unclustered and are costed on their own.**

Clustering all 1,448 and then filtering to fibre was the second thing we got wrong: it
over-merged, putting fibre villages 40 km apart in one bundle and sharing a trench that
could not exist.

### What is in a bundle, and what is not

Only fibre. A trench passing a village serves it, which is what makes the sharing real.
Tower, satellite and community Wi-Fi are per-site builds, and saying so is not a claim that
they share nothing (see §7).

---

## 5. What shipped: a portfolio, not a sequence

The first build was a travel sequence: a tour through the bundles with a slider between
shortest route and earliest impact, drawn as a line across the province. It was replaced,
and the reasons are worth recording because they are all the same mistake in different
clothes.

- The line joined bundle centroids and **read as proposed fibre**. It joined nothing that
  would ever be built.
- **Travel kilometres are not build kilometres and not cost**, so "half the population after
  118 km" answered no question anyone has.
- The tour started at the largest bundle, so Kota Kinabalu led **by construction**.
- "Cheapest to build" was simply **false**: the slider never changed build cost, only travel.
- It **summed `pop_2km` across bundles** and called the total "affected population", which
  the budget panel refuses to do fourteen lines away, because the 2 km buffers overlap.

What replaced it ranks bundles against a budget, which is the decision a planner actually
has.

**Three named scenarios**, each printing its own formula:

| Scenario | Rule |
|---|---|
| Need | median DIPI of the bundle's members, highest first, cost ignored |
| Balanced | median DIPI divided by cost in RM millions |
| Reach/RM | (settlements + schools + clinics) divided by cost in RM millions |

**RM 66.7m builds all 17 bundles** at the benchmark rate. At RM 50m, 15 bundles fit for
RM 49.5m: 204 settlements, 207 schools and 78 clinics within 3 km of one of them.

Four things the panel is careful about:

- **Costs come from `costOf`**, the same function Budget what-if uses, so the two panels can
  never quote different prices. The planner's own RM/km overrides both.
- **Institutions are the union across funded bundles**, not a sum of per-bundle counts: one
  school within 3 km of two bundles would otherwise be funded twice.
- **People are never totalled.** Overlapping buffers make any sum a double count.
- **Greedy, and it says so.** Bundles are taken in the ranked order while they fit and
  skipped when they do not, so another combination may fit the same budget and serve more.

---

## 6. The limitation that matters most

Fibre needs **3,000 people within 2 km**. The highest-DIPI settlements are mostly small and
remote. So the two criteria pull in opposite directions:

| Recommended option | n | Median DIPI |
|---|---|---|
| Tower | 449 | **55.5** |
| Community Wi-Fi | 654 | 49.1 |
| **Fibre** | 323 | **45.6** |
| Satellite | 22 | 34.8 |

**Only 6 of the top 50 by DIPI are in any bundle.** Bundled settlements have a median DIPI
of 45.6 against 52.3 for those left out.

The build panel therefore points at denser, better-connected places than the ranking does.
That is what fibre eligibility selects for, not a judgement about where help is needed, and
the panel says so on its face rather than leaving a reader to notice.

---

## 7. The bigger prize, now measured

Towers are charged **RM 520,000 each, one per settlement**: 449 settlements, RM 233.5m. But
one mast serves several villages. An earlier draft of this section estimated the saving from
a quick cluster count and **was wrong at every radius**, so here is the run that replaced it.

**Method.** Candidate mast sites are the settlement coordinates themselves, so every site is
somewhere a mast could actually stand. Greedy maximum coverage: take the site that adds the
most uncovered settlements, repeat. `dataset/tower_scenarios.py`.

| Assumed reach | Masts | Cost (base) | Saving | Mean km to mast |
|---|---|---|---|---|
| 3 km | 189 | RM 98.3m | RM 135.2m | 0.96 |
| 5 km | 145 | RM 75.4m | RM 158.1m | 1.70 |
| 8 km | 103 | RM 53.6m | RM 179.9m | 3.05 |
| 10 km | 86 | RM 44.7m | **RM 188.8m** | 3.97 |

The earlier estimate claimed 160 / 107 / 74 masts at 3 / 5 / 8 km. The real figures are
**189 / 145 / 103**, so it understated the count by 18%, 36% and 39%, and overstated the
saving by up to RM 15m. That gap is not the algorithm being sloppy: greedy is a ln(n)
approximation, and across 200 randomised restarts the best result was never more than
**3 masts** better, worth RM 1.6m. The old numbers came from a different and wrong method.

**This is the number that answers §6.** Only 6 of the top 50 by DIPI are in a fibre bundle.
**31 of the top 50 are tower settlements.** Whatever reaches the highest-need places, it is
not fibre.

**Still not built, and the reason has not changed.** A trench that passes a village serves
it: deterministic geometry over a measured distance. A mast 5 km away *might* serve a
village, depending on terrain, height and line of sight. **55 of the 449 sit at least 150 m
below their anchor town**, and the recommender already flags them. We have **no sourced
figure for rural mast reach**: `fwa_max_km = 40` is distance to town for backhaul, not
coverage. The radius alone moves the answer by **RM 53.6m** across the table above, which is
the `fibre_max_km` problem again with far more money riding on it.

So the table ships as a range and is labelled **candidate service areas, distance only**.
It is not predicted coverage. Real propagation needs terrain and ground-cover profiles
(ITU-R P.1812), and until it is run, no single row of that table is the answer.

**Community Wi-Fi** is worth about RM 6.2m: 74 distinct institutions could anchor 162
settlements. The real problem there is not clustering, it is that **492 of the 654 have no
institution within 3 km at all**, so the recommendation does not apply to them.

**Satellite** is correctly excluded. One terminal per site, nothing shared.

---

## 8. What changed in the code

| File | Change |
|---|---|
| `dataset/export_clusters.py` | validates `clusters.json` on every regeneration, then publishes it |
| `dataset/tower_scenarios.py` | greedy maximum coverage over the 449 tower settlements at 3, 5 and 10 km |
| `dashboard/index.html` | `costOf` charges the cheaper run; the bundles panel; a suggested-option filter |
| `agent/tools.py` | the same costing, plus `rank_bundles` and `explain_bundle` |
| `agent/graph.py` | both tools registered, and a `bundle_proxy` guardrail |

**Python and JS agree exactly.** At RM 50m the budget funds 358 / 271 / 203 settlements
across the low, base and high cost cases on both sides, and the parity test asserts it.

**The copilot answers about bundles from the same arithmetic**, with the panel's settings
sent as context so it recomputes rather than trusting the client. A draft that calls a
bundle a build plan is rejected by the guardrail: bundles are a proximity screen, and the
difference is the whole claim.

---

## 9. Where this sits in GeoAI methodology

| Technique taught | Status |
|---|---|
| **Spatial train/test splitting** | **In place.** GroupKFold by district, mandated because 29% of settlements share an Ookla tile. Spatial CV MAE 34.06 against a naive 25.31: the 35% gap is the finding. |
| **Spatial clustering** | **In place.** HDBSCAN after DBSCAN was tested and failed. Sizes reported, not just counts. |
| **Geospatial feature engineering** | **In place.** `backhaul_km`, elevation drop, terrain shadowing, proximity buffers, raster to vector joins. |
| **Data fusion** | **In place.** Eight sources, including OpenCelliD as a context layer that is deliberately never a model feature. |
| **Spatial prediction with uncertainty** | **In place.** Prediction intervals drive the survey planner, ranked by stakes times the width of the model's range. |
| **Graph methods** | **In place.** Minimum spanning tree for the trench. Classical optimisation, not a GNN, because it is exact and explainable. |
| **Remote sensing classification** | **Not used.** No land-cover step here. Saying so beats bolting one on. |
| **CNN, GNN, foundation models** | **Not used.** No labelled imagery task, no training signal for a GNN. |
| **Spatiotemporal modelling** | **Rejected on Ookla.** Four quarters examined: 22% tile completeness and the swing is sampling noise at Spearman -0.57 against test count. VIIRS nighttime lights is the candidate that could give a real time axis. |

Five models were tested on identical folds and seeds and four were rejected, including
OpenCelliD, which came last. That table is worth more than the R² of the one that survived.

---

## 10. What we deliberately do not do

- **A screening proxy, not a design.** Straight lines until roads are extracted, so a build
  order and never a driving route.
- **No single objective.** Three named scenarios with their formulas printed, because
  "cheapest" and "most urgent" genuinely disagree.
- **No claim of optimality.** Greedy over whole bundles, and the panel says another
  combination may do better.
- **No towers bundled on an invented radius.** §7.
- **No population totals.** Overlapping buffers.
- **No single cost figure.** A benchmark the planner can overwrite, shown to one decimal of
  a million because the inputs do not support more.

---

## 11. The reply to the judge

> You are right that the ranking is not a build order, and we measured what that costs.
> Pricing settlements individually overstated fibre by more than double: RM 190.9m against
> RM 89.0m once each settlement is charged the shorter of its shared spur and its own run
> from town.
>
> So we cluster with HDBSCAN over the fibre-eligible settlements, build a spanning tree per
> bundle, and rank bundles against a budget under three named scenarios. We tried DBSCAN
> first and it chained 931 of 1,114 settlements into one cluster; we also tried presenting
> this as a travel route and threw it away, because kilometres between two builds are not a
> constraint anyone plans around and the line on the map read as proposed fibre.
>
> The limitation we put on the panel itself: fibre needs 3,000 people within 2 km, so only
> 6 of our top 50 by DIPI are in any bundle, while 31 of them are tower settlements. The
> build view answers a narrower question than the ranking does.
>
> The larger saving is in shared masts, and we have now measured it rather than estimated it:
> greedy maximum coverage over the 449 tower settlements needs 189 masts at a 3 km reach and
> 86 at 10 km, RM 98.3m against RM 44.7m, versus RM 233.5m if every settlement gets its own.
> An earlier estimate of ours was 18% to 39% too low at every radius, which is in §7 because
> the correction matters more than the original guess. We still do not put a single figure on
> it: the radius alone swings the answer by RM 53.6m, we have no sourced number for rural
> mast reach, and 55 of the 449 sit at least 150 m below their anchor town. Distance is not
> coverage until someone runs the propagation.

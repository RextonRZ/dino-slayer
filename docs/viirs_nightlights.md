# VIIRS nighttime lights: tested, rejected as a feature, kept as a power flag

**Source files, all in this repo:** [`dataset/ml/viirs_annual_max1km.csv`](../dataset/ml/viirs_annual_max1km.csv),
[`dataset/ml/viirs_trend.csv`](../dataset/ml/viirs_trend.csv),
[`dataset/ml/tower_isolated_power.csv`](../dataset/ml/tower_isolated_power.csv).

**Short version:** VIIRS works, the extraction is clean, and the answer is still no. **703 of
1,448** Sabah settlements show no detectable radiance in thirteen years, and the ones that do
are largely the places we already have Ookla measurements for. It is blind where we need it.

It ships as one column, a power availability flag, and not as a model feature.

> **This document was wrong once and has been corrected.** The first version used a **mean
> over a 2 km buffer** and reported 778 dark. That reducer divides a settlement lighting one
> or two pixels by roughly fifty. The re-run with **max within 1 km** gives **703 dark**, and
> more importantly it changes the shape of the answer. Both the old error and the correction
> are kept below, because the way we got it wrong is the more useful half.

**Every figure here is recomputed from the shipped CSVs.** The lit counts, the trend classes
and the isolation join were re-derived independently and agree with `viirs_trend.csv` on all
1,448 rows with zero mismatches.

---

## 1. What was extracted

| | |
|---|---|
| Source | NOAA VIIRS DNB Annual composites, `ANNUAL_V21` (2013 to 2021) and `ANNUAL_V22` (2022 to 2025) |
| Access | Google Earth Engine |
| Band | `average_masked` |
| Reducer | **Max within 1 km.** The original mean over 2 km is superseded, see §2 |
| Scale | 500 m (native 15 arc-sec) |
| Result | **18,824 rows** = 1,448 settlements x 13 years, no gaps, no nulls |

**Why annual and not monthly.** The spec called for Black Marble `VNP46A3` monthly. The annual
VNL V2 composites were used instead, because their processing applies outlier removal that
discards biomass burning pixels using the twelve-month median radiance. In Sabah that means
palm oil burning and gas flares are filtered out at source. Raw monthly DNB has no such
filtering, and fishing fleets and flares reading as "brightening settlements" was the exact
contamination risk flagged in [deployment_clusters.md](deployment_clusters.md). The trade is
13 annual points instead of about 150 monthly ones, still ample for Mann-Kendall and a much
cleaner series.

**One risk checked and cleared.** V21 and V22 are different processing versions, so a step
change at the 2021 to 2022 boundary would have read as a state-wide brightening trend. Medians
and maxima are continuous across the boundary, so there is no discontinuity.

---

## 2. The reducer error, and why it is worth writing down

The first pass took the **mean radiance in a 2 km buffer**, chosen so it would be comparable
with `pop_2km`. A 2 km buffer at 500 m resolution holds about **50 pixels**. A settlement that
lights up one or two of them gets divided by fifty. To clear a 0.5 threshold as a mean, a
one-pixel settlement needs a raw radiance of about **25**. A small rural kampung on mains power
reads about **1 to 5**. So the method was classifying genuinely grid-connected villages as dark.

**And we tested the wrong axis, then called it conclusive.** The original document swept the
*threshold*, 0.5 down to 0.1, and concluded the finding was robust because the count only moved
from 400 to 670. That sweep relaxes by **5x** against a **50x** dilution. It addressed a tenth
of the problem, and the confident wording it produced was the actual mistake, not the reducer
choice.

The fix, max within 1 km:

| Threshold | Mean over 2 km (old) | **Max within 1 km (shipped)** |
|---|---|---|
| 0.5 | 400 lit | **745 lit** |
| 0.25 | 519 lit | **798 lit** |
| 0.1 | 670 lit | **804 lit** |

The old column is still climbing at the bottom, which is the signature of real signal sitting
under the cutoff. The new column is **nearly flat**: going from 0.5 all the way to 0.1, near
VIIRS's practical noise floor, recruits only 59 more settlements. That flatness is what a real
**detection floor** looks like. **The threshold is no longer load-bearing**, and unlike the
first version of this claim, that is now demonstrated rather than asserted.

---

## 3. Why it still does not work as a model feature

**703 of 1,448 settlements register no detectable light in any of the thirteen years**, and the
745 that do are largely the bright, dense places that already carry solid Ookla measurements
and need no estimating.

**192 of the 216 unmeasured settlements are dark, 89%.** That is the argument. The 24 that
are lit sit barely over the line: radiance 0.51 to 1.39 against a 0.5 cutoff, 15 of them below
1.0, and a median `pop_2km` of 193. So the feature is blank for nine rows in ten and close to
noise on the rest. A feature that is informative only where we already have data adds nothing.

This is the same failure mode as OpenCelliD, with one difference worth naming. OpenCelliD was
**fitted and scored** (model C, MAE 36.55 against 34.06). VIIRS failed one step earlier, at
**feature availability**, so it was cut before fitting rather than after. A feature blank for
the rows you need cannot be scored fairly.

**What would not fix it.** Monthly Black Marble `VNP46A2` is more sensitive and would detect
some settlements the annual product misses, but it trades away the biomass burning filter, and
in Sabah that puts fires and flares back in. The deeper problem survives either way: a village
of 90 people with no grid connection has nothing to detect at any resolution, reducer or
threshold.

---

## 4. The trend result, which killed a claim we might have made

Of the 745 lit settlements:

| Class | Count | Share of lit |
|---|---|---|
| `flat` | **422** | 57% |
| `brightening` | 276 | 37% |
| `dimming` | 31 | 4% |
| `flat_urban_artefact` | 16 | 2% |

**Brightening barely moved when the reducer was fixed: 278 to 276.** All 345 newly-lit
settlements landed in `flat` or `dimming`. So the diluted series was reporting brightening as
**70% of lit settlements** when the real figure is **37%**.

That matters, because "Sabah is electrifying rapidly" is a sentence the old numbers would have
supported and the corrected ones do not. **Most lit settlements are flat.** The dilution was
not merely undercounting, it was manufacturing an optimistic story by keeping only the places
bright enough to be growing.

**Dimming splits into two different things.**

**16 are an instrument artefact, and they are flagged as such.** They are the brightest urban
centres in the state: Tawau, Sembulan, Lapasan, Tenom, Kepayan, Kota Belud, Lahad Datu, with
`ntl_max` between 17 and 90. VIIRS DNB **cannot sense blue light**, so a sodium-to-LED street
lighting conversion reads as falling radiance in exactly these places. They are labelled
`flat_urban_artefact` rather than counted as dimming, because reporting Tawau as losing
electrification would be false.

**The other 31 are a genuinely different population** and we do not have an explanation for
them. `ntl_max` quartiles of 1.6 / 3.1 / 6.2, small towns and kampungs of roughly 1,200 to
11,000 people (Bandar Sahabat, Kampung Pirasan, Tandek, Kampung Banjar), with shallow slopes
of -0.09 to -0.48. LED conversion does not explain these, because they mostly have no municipal
street lighting to convert. **31 out of 745 with no mechanism is a count, not a finding.** It
is reported and deliberately not interpreted.

---

## 5. What is kept, and one finding that came free

One sentence, and it is a genuine constraint on the recommender:

> **703 of 1,448 Sabah settlements show no detectable nighttime radiance across thirteen years
> of VIIRS. Any connectivity option sited there must supply its own power.**

This is **stronger than the 778 it replaces**, not weaker. 778 rested on a method that could
explain most of itself; 703 rests on a detection floor the threshold sweep now demonstrates.
The claim moved from methodological to physical. It applies to tower, satellite and community
Wi-Fi alike.

**The join with the terrain screen is the best thing in this file**, and it needed no new
extraction. The mast screening found settlements that can only be served by a mast in their own
village. Crossing that with `ever_lit`:

| Assumed mast radius | Isolated | Isolated **and** unlit |
|---|---|---|
| 3 km | 191 | **67** |
| 5 km | 169 | **58** |
| 10 km | 157 | **56** |

**A site needing its own mast and its own power is a different cost class** from one needing
only a mast, and neither analysis can see it alone. It barely moves across radii, 67 down to 56,
so unlike most tower figures **it does not lean on the unsourced reach assumption**.

### The shipped columns

`viirs_trend.csv`, one row per settlement:

| Column | Meaning |
|---|---|
| `ever_lit` | Max radiance at or above 0.5 over 13 years |
| `light_trend` | `dark` / `brightening` / `flat` / `dimming` / `flat_urban_artefact` |
| `ntl_max` | Peak radiance across the 13 years |
| `ntl_2025` | Most recent annual value |
| `ntl_slope` | Theil-Sen slope, radiance per year, lit only |
| `ntl_p` | Mann-Kendall p-value, lit only |

`viirs_annual_max1km.csv` is the full 13-year series if anyone wants to re-cut it.
`tower_isolated_power.csv` is the 449 tower-recommended settlements with their isolation flags
at each radius plus `ever_lit`.

---

## 6. The rule this must not break

**Nightlights measure electrification and activity. They do not measure connectivity.**

If `dark` is ever rendered or read as "no coverage", it breaks the rule the whole project stands
on: missing data is uncertainty, never poor service. **A dark settlement may have perfectly good
mobile service.** It has no grid electricity, which is a different problem with a different fix.

Permitted framings: power availability, electrification context, demand proxy. Not permitted:
coverage, service quality, or any input to DIPI.

The 0.5 threshold for `ever_lit` is **ours and unsourced**, recorded in
[sources.json](../dataset/web/sources.json) as `ntl_lit_threshold`. Its effect is now bounded
tightly by §2: at 0.1, near the noise floor, the count moves by 59 settlements out of 1,448.

---

## 7. Where this leaves the methodology table

§9 of [deployment_clusters.md](deployment_clusters.md) previously named VIIRS as the candidate
that could give a real time axis. It cannot, and the row says so. Two rejections with measured
reasons is a stronger row than one rejection and a promise.

VIIRS is the **fifth** rejected feature group, after elevation alone, all three terrain columns,
division, and OpenCelliD. Recording the failures with their reasons is the point. A model card
that lists only what worked is not a model card.

---

## 8. Still open

**1. The power flag is now in the product**, and this item is closed. It ships exactly where
the terrain caveat ships: a line under the suggested option reading *"no detectable nighttime
light in 13 years of VIIRS, so this site likely needs its own power"*, plus a note that grid
electricity is not coverage. The mast panel carries the join, so the self-site tile reads
*"67 of those also have no detectable grid light: own mast AND own power"*.

There is also a **night view**, a Layers toggle that renders Sabah the way VIIRS recorded
it: the basemap drops to a quarter, the DIPI dots drop to a tenth, and the 745 lit settlements
glow amber scaled by peak radiance.

**This reverses an earlier decision in this document, and the reversal is the interesting
part.** The first version of this section said no power data may reach the map style at all,
on the grounds that a dark dot on a priority map reads as a worse-served dot. That reasoning
was right about an **overlay** and wrong about a **mode**, and the difference is what claim the
picture makes:

- An unlit overlay sits on top of the DIPI ramp and says *these places are worse*. The data
  does not know that.
- A night view dims the DIPI ramp out of the way and says *these places emitted no light*.
  That is exactly what the data knows, and it is drawn as the measured radiance rather than as
  a binary, so the picture cannot say more than the measurement does.

The rule was never "hide it". It was "do not let electrification be read as service". A mode
that removes the priority colouring while it is on satisfies that better than a ban did.

Four things are enforced rather than intended, and there are browser tests for each:

- **It never changes the option.** Forcing the flag off and on for the same settlement returns
  the same recommendation and exactly one extra line.
- **It never touches the ranking.** DIPI and rank are byte-identical with the flag on or off.
- **The night view is a mode, not an overlay.** It cannot be on at the same time as a readable
  DIPI ramp, because it hides that ramp and replaces the legend. Turning it off restores the
  basemap opacity, the brightness and the legend exactly.
- **The trend classes are not published to the client.** `power.json` carries the unlit ids,
  summary counts and peak radiance. `brightening`, `dimming` and `flat_urban_artefact` stay in
  `viirs_trend.csv`, because those are interpretations and two of the three are contested.

The night legend carries the two sentences a viewer needs in order not to misread the picture:
**electrification, not coverage**, and **these are settlement points, not the satellite
raster**, so empty ground means no settlement rather than no light. Somebody will otherwise
think they are looking at the NASA image.

If `power.json` is missing the line simply disappears. It never says a settlement **has** power,
because we do not know that either.

Generated and re-verified by [dataset/export_power.py](../dataset/export_power.py), which
re-derives `ever_lit` from the raw annual series rather than trusting the summary column. That
check has already caught one error: a draft of this document claimed all 216 unmeasured
settlements were dark, and 24 of them are lit.

**2. The 31 mid-range dimming settlements have no mechanism.** Either find one or leave the
count unexplained. Do not reach for a story.

**3. The `flat_urban_artefact` class is a judgement, not a measurement.** We inferred LED
conversion from brightness and direction; nobody checked a municipal lighting record. The 16 are
the brightest places in Sabah and the physics is well established, so the inference is
reasonable, but it is an inference and the class name should keep saying `artefact` rather than
graduating into a finding.

"""Publish the nightlight power flag, and re-verify it on the way through.

Run from the repo root, whenever the VIIRS files are regenerated:

    python dataset/export_power.py

Reads  : dataset/ml/viirs_trend.csv
         dataset/ml/viirs_annual_max1km.csv
         dataset/ml/tower_isolated_power.csv
         dataset/web/dipi.geojson
Writes : dataset/web/power.json

WHAT IT IS
----------
One list: the settlements with no detectable nighttime radiance in thirteen
years of VIIRS. Anything sited there has to supply its own power, and that is
a real line item on a tower or a community hub.

WHAT IT IS NOT, AND THIS IS THE WHOLE REASON THE FILE IS SHAPED THIS WAY
------------------------------------------------------------------------
Nightlights measure ELECTRIFICATION. They do not measure connectivity. A dark
settlement may have perfectly good mobile service; it has no grid.

So the file publishes the unlit list, peak radiance for the lit ones, and NO
TREND CLASSES. The trend split stays in viirs_trend.csv on purpose: a
`brightening` or `dimming` label on a priority map is an interpretation, and
the two that matter here are already contested (16 of the 31 dimming rows are
an LED artefact).

Radiance ships because the night view draws the ACTUAL MEASUREMENT rather than
a binary. That is the whole reason the view is defensible: it shows what VIIRS
recorded, not a judgement about who is badly served. On the priority map the
flag stays a line of text under the suggested option, exactly like the terrain
drop. It never picks, filters, sorts or colours a DIPI dot.

WHY IT IS VALIDATED HERE RATHER THAN TRUSTED
--------------------------------------------
The CSVs are produced outside this repo. The headline claim, 703 settlements
needing their own power, is one a planner would budget against, and the first
version of it was WRONG: a mean over a 2 km buffer diluted small settlements
by about 50x and reported 778. These checks re-derive the number from the raw
annual series rather than reading the summary column, so the same class of
error cannot ship twice.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREND = ROOT / "dataset" / "ml" / "viirs_trend.csv"
ANNUAL = ROOT / "dataset" / "ml" / "viirs_annual_max1km.csv"
ISO = ROOT / "dataset" / "ml" / "tower_isolated_power.csv"
GEO = ROOT / "dataset" / "web" / "dipi.geojson"
OUT = ROOT / "dataset" / "web" / "power.json"

# Ours and unsourced, recorded in sources.json as ntl_lit_threshold. Its effect
# is bounded: at 0.1, near the VIIRS noise floor, the count moves by 59 of 1,448.
THRESHOLD = 0.5
RADII = ("3", "5", "10")


def die(msg):
    raise SystemExit("export_power.py FAILED: " + msg)


trend = list(csv.DictReader(TREND.open(encoding="utf8")))
if len(trend) != 1448:
    die(f"viirs_trend.csv has {len(trend)} rows, expected 1448")

geo = json.loads(GEO.read_text(encoding="utf8"))
props = {f["properties"]["settlement_id"]: f["properties"] for f in geo["features"]}
missing = [r["settlement_id"] for r in trend if r["settlement_id"] not in props]
if missing:
    die(f"{len(missing)} trend ids are not in dipi.geojson, first: {missing[:3]}")

truthy = {"true", "1", "yes"}
lit = {r["settlement_id"] for r in trend if r["ever_lit"].strip().lower() in truthy}
unlit = sorted(set(props) - lit)

# 1. The classes must partition the file, or a settlement is being counted twice
#    or not at all.
classes = Counter(r["light_trend"] for r in trend)
if sum(classes.values()) != 1448:
    die(f"light_trend classes sum to {sum(classes.values())}, expected 1448")
if classes.get("dark", 0) != len(unlit):
    die(f"light_trend says dark={classes.get('dark')} but ever_lit says {len(unlit)}")

# 2. Re-derive ever_lit from the RAW annual series. This is the check that would
#    have caught the mean-over-2km error, because it does not trust the summary.
peak = defaultdict(float)
n_annual = 0
for row in csv.DictReader(ANNUAL.open(encoding="utf8")):
    peak[row["settlement_id"]] = max(peak[row["settlement_id"]], float(row["max_1km"]))
    n_annual += 1
if n_annual != 1448 * 13:
    die(f"annual series has {n_annual} rows, expected {1448 * 13}")
mismatch = [s for s in props if (peak[s] >= THRESHOLD) != (s in lit)]
if mismatch:
    die(f"{len(mismatch)} rows disagree with the raw series at {THRESHOLD}, "
        f"first: {mismatch[:3]}")

# 3. The threshold must not be load-bearing. If relaxing all the way to the
#    noise floor moved the count a lot, the finding would be an artefact of the
#    cutoff rather than a detection floor, exactly as it was the first time.
sweep = {t: sum(1 for v in peak.values() if v >= t) for t in (0.5, 0.25, 0.1)}
if sweep[0.1] - sweep[0.5] > 150:
    die(f"threshold is load-bearing again: lit goes {sweep[0.5]} -> {sweep[0.1]}. "
        "Re-read docs/viirs_nightlights.md before shipping this.")

# 4. The rejection as a model feature rests on the settlements we predict for
#    being mostly dark, so it is asserted rather than remembered. This is a
#    SHARE, not a total: 24 of the 216 are lit, all of them barely, and an
#    earlier draft of the doc claimed all 216 were dark. They are not.
modelled = [s for s, p in props.items() if p.get("speed_source") == "modelled estimate"]
mod_lit = [s for s in modelled if s in lit]
dark_share = 1 - len(mod_lit) / len(modelled)
if dark_share < 0.85:
    die(f"only {dark_share:.0%} of the {len(modelled)} modelled settlements are dark "
        f"({len(mod_lit)} lit). The feature-rejection argument in "
        "docs/viirs_nightlights.md rests on this share; fix the doc first.")
if mod_lit and max(peak[s] for s in mod_lit) > 5.0:
    die("a modelled settlement now reads brightly lit, not marginal. The claim that "
        "the lit ones sit just over the cutoff no longer holds.")

# 5. The join with the terrain screen. Its value is that it barely moves across
#    radii, so unlike most tower figures it does not lean on the unsourced reach.
iso = list(csv.DictReader(ISO.open(encoding="utf8")))
iso_unlit = {}
for r_km in RADII:
    col = f"only_self_{r_km}km"
    n = sum(1 for r in iso
            if r[col].strip() in {"1", "True", "true"}
            and r["ever_lit"].strip().lower() not in truthy)
    iso_unlit[r_km] = n
spread = max(iso_unlit.values()) - min(iso_unlit.values())
if spread > 30:
    die(f"isolated-and-unlit swings {iso_unlit} across radii, spread {spread}. "
        "It was stable at 67/58/56; a wide spread means it now depends on the "
        "unsourced mast reach and must not be quoted as a flat number.")

OUT.write_text(json.dumps({
    "_what": ("Settlements with no detectable nighttime radiance in 13 years of VIIRS. "
              "Anything sited there must supply its own power."),
    "_not": ("Nightlights measure ELECTRIFICATION, never connectivity. A dark settlement "
             "may have perfectly good mobile service. This flag qualifies an option the "
             "way the terrain drop does. It never picks, filters, sorts or colours, and "
             "the trend classes are deliberately not published here."),
    "_source": "NOAA VIIRS VNL V2 annual composites, public domain. See docs/viirs_nightlights.md",
    "reducer": "max within 1 km",
    "years": "2013 to 2025",
    "threshold": THRESHOLD,
    "threshold_note": ("Ours, unsourced, and bounded: lit counts are "
                       f"{sweep[0.5]} / {sweep[0.25]} / {sweep[0.1]} at 0.5 / 0.25 / 0.1, "
                       "so relaxing to the VIIRS noise floor moves it by "
                       f"{sweep[0.1] - sweep[0.5]} of 1448."),
    "counts": {"unlit": len(unlit), "lit": len(lit), "total": len(props)},
    # Peak radiance over the 13 years, lit settlements only, for the night view.
    # Rounded to 2 dp: the glow is a visual, and full float precision would add
    # 4 KB to say nothing a viewer can see.
    "radiance": {s: round(peak[s], 2) for s in sorted(lit)},
    "radiance_note": ("ntl_max, the peak annual value 2013 to 2025, same series the "
                      "lit/unlit split uses. Heavily skewed: p50 is 1.99 and the top "
                      "is 116.38, so anything drawing it must scale non-linearly."),
    "radiance_quantiles": {q: round(sorted(peak[s] for s in lit)[int(q / 100 * (len(lit) - 1))], 2)
                           for q in (25, 50, 75, 90, 99)},
    "isolated_unlit": iso_unlit,
    "isolated_unlit_note": ("Settlements the terrain screen can only serve from a mast in "
                            "their own village AND with no detectable grid light. Own mast "
                            "and own power is a different cost class. Barely moves across "
                            "radii, so it does not lean on the mast-reach assumption."),
    "unlit": unlit,
}, indent=1) + "\n", encoding="utf8")

print(f"lit counts by threshold   {sweep[0.5]} / {sweep[0.25]} / {sweep[0.1]}"
      f"  (0.5 / 0.25 / 0.1)")
print(f"unlit at {THRESHOLD}             {len(unlit)} of {len(props)}")
print(f"trend classes             {dict(classes)}")
print(f"modelled and dark         {len(modelled) - len(mod_lit)} of {len(modelled)}"
      f"  ({dark_share:.0%}, the {len(mod_lit)} lit peak at "
      f"{max((peak[s] for s in mod_lit), default=0):.2f})")
print(f"isolated AND unlit        {iso_unlit['3']} / {iso_unlit['5']} / {iso_unlit['10']}"
      f"  (3 / 5 / 10 km)")
rad = sorted(peak[s] for s in lit)
print(f"radiance, lit only        min {rad[0]:.2f}  p50 {rad[len(rad) // 2]:.2f}  "
      f"max {rad[-1]:.2f}")
print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1024:.1f} KB)")

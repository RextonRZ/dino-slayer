"""Publish the survey targeting, and re-verify it on the way through.

Run from the repo root, whenever measurement_priority_v1.csv is regenerated:

    python dataset/export_survey.py

Reads  : dataset/ml/measurement_priority_v1.csv
         dataset/web/dipi.geojson
Writes : dataset/web/survey.json

WHY THIS EXISTS
---------------
The dashboard used to rank the survey queue by `stakes x (pred_hi - pred_lo)`,
the width of the model's interval. That is the wrong question. A wide interval
on a settlement the model puts confidently at 90 Mbps is not worth a field
trip: whichever way the measurement lands, it lands well above the service
line and nothing changes.

The right question is DECISIVENESS. Does the estimate sit close enough to the
threshold, relative to the model's own disagreement, that a measurement could
come down on either side of it?

The two rankings disagree almost completely: Spearman -0.224, and they share
none of their top ten. That is not noise, it is the two questions being
different, and the interval-width one was rewarding confidence about the wrong
places.

WHAT THIS FILE DOES NOT DO
--------------------------
It does not replace the queue. It covers 111 of the 334 settlements with no
usable measurement, because decisiveness needs a model estimate and a
population to serve. The other 223 are not low priority; they are the ones
NOTHING is known about, and 118 of them have no estimate at all.

So the dashboard keeps two bases and never multiplies them together:

    decisive   a measurement could move the answer   ranked by priority here
    unknown    no usable estimate exists             ranked by stakes

Blending them would be the same mistake as blending evidence confidence into
DIPI: it makes "nobody looked here" and "we looked and it is borderline" into
one number, when they are different reasons to send a team.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dataset" / "ml" / "measurement_priority_v1.csv"
GEO = ROOT / "dataset" / "web" / "dipi.geojson"
OUT = ROOT / "dataset" / "web" / "survey.json"

# Ours, and the one number in this file that is not derived. 0.7 Mbps is the
# 360p floor and 30 is a classroom, so 21 is what a school needs to stream the
# lowest tier. Recorded in sources.json as underserved_mbps.
THRESHOLD = 21.0


def die(msg):
    raise SystemExit("export_survey.py FAILED: " + msg)


rows = list(csv.DictReader(SRC.open(encoding="utf8")))
geo = json.loads(GEO.read_text(encoding="utf8"))
props = {f["properties"]["settlement_id"]: f["properties"] for f in geo["features"]}

missing = [r["settlement_id"] for r in rows if r["settlement_id"] not in props]
if missing:
    die(f"{len(missing)} ids are not in dipi.geojson, first: {missing[:3]}")


def num(v):
    return None if v in ("", None, "nan", "NaN") else float(v)


out = {}
straddlers = 0
for r in rows:
    pri = num(r.get("measurement_priority"))
    if pri is None:
        continue
    straddles = str(r.get("straddles", "")).strip().lower() in ("true", "1", "yes")
    straddlers += straddles
    out[r["settlement_id"]] = {
        "p": round(pri, 4),
        "s": 1 if straddles else 0,
        "d": None if num(r.get("decisiveness")) is None else round(num(r["decisiveness"]), 4),
        "why": (r.get("measurement_priority_reason") or "").strip(),
    }

# 1. Every row must be one we cannot score. If a measured settlement turned up
#    here, the queue and the survey list would be describing different sets.
wrong = [s for s in out if props[s].get("evidence_tier") != "insufficient"]
if wrong:
    die(f"{len(wrong)} scored settlements are in the survey file, first: {wrong[:3]}")

# 2. The gate is what makes the number readable: a straddler always outranks a
#    non-straddler, so the top of the list is always "this could go either way"
#    rather than "this one has a wide interval".
hi = [v["p"] for v in out.values() if v["s"]]
lo = [v["p"] for v in out.values() if not v["s"]]
if hi and lo and min(hi) <= max(lo):
    die(f"the straddle gate leaks: lowest straddler {min(hi):.3f} is not above "
        f"the highest non-straddler {max(lo):.3f}")
if hi and (min(hi) < 0.5 or max(lo, default=0) >= 0.5):
    die("the 0.5 split no longer separates straddlers from the rest")

# 3. The file must stay a SUBSET of the queue, never all of it. If it ever
#    covered everything, the two-basis design below would be pointless and the
#    dashboard should be simplified instead of quietly ranking on one basis.
qb = [s for s, p in props.items() if p.get("evidence_tier") == "insufficient"]
if len(out) >= len(qb):
    die(f"survey file covers {len(out)} of {len(qb)} queue rows. Re-read the "
        "two-basis note in this docstring before shipping that.")

OUT.write_text(json.dumps({
    "_what": ("Survey targeting for the settlements a measurement could actually settle. "
              "Higher is more decisive, not more needy."),
    "_not": ("NOT a needs score and NOT a DIPI. It covers a SUBSET of the queue, because "
             "decisiveness needs a model estimate and a population to serve. The rest of "
             "the queue is ranked by stakes on its own, and the two are never multiplied."),
    "_source": "geoai_coveragemodel.py (Colab), measurement_priority v4. "
               "See docs/system_info.md section 7.2 for the three versions it replaced.",
    "threshold_mbps": THRESHOLD,
    "threshold_note": "Ours: 0.7 Mbps at 360p shared by a classroom of 30.",
    "counts": {"scored_here": len(out), "straddle_the_line": straddlers,
               "queue_total": len(qb), "not_covered": len(qb) - len(out)},
    "fields": {"p": "measurement_priority, 0 to 1", "s": "1 if the interval crosses the line",
               "d": "decisiveness before the gate", "why": "the sentence shown in the row"},
    "rows": out,
}, indent=1) + "\n", encoding="utf8")

print(f"scored here          {len(out)} of {len(qb)} queue settlements")
print(f"cross the {THRESHOLD:.0f} Mbps line  {straddlers}")
print(f"left to stakes only  {len(qb) - len(out)}")
print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1024:.1f} KB)")

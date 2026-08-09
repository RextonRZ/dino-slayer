"""Publish which settlements the terrain screen can only reach from themselves.

Run from the repo root, after tower_los.py:

    python dataset/export_isolated.py

Reads  : dataset/ml/tower_isolated.csv
         dataset/web/dipi.geojson
Writes : dataset/web/isolated.json

WHAT IT IS
----------
Of the 449 settlements the recommender sends to a tower, these are the ones
where NO other candidate mast site clears a line of sight and 60% Fresnel
check. The only site that can serve them is one in their own village.

WHY IT IS NOT THE `serves == 1` COUNT ALREADY IN towers_los.json
----------------------------------------------------------------
Those are different numbers and the difference is the whole point.

    serves == 1          172 at 3 km   a mast the greedy solver happened to
                                       place that ended up covering only
                                       itself. An artefact of the solution.

    only_self_reachable  191 at 3 km   NO other candidate site can reach it.
                                       A property of the terrain, true
                                       whatever solver you run.

The second is the one a planner can act on, so it is the one published here.

WHAT IT IS FOR, AND WHAT IT MUST NOT DO
---------------------------------------
It QUALIFIES the suggested option. It does not change it.

"Tower" for one of these settlements quietly means a dedicated mast rather
than a shared one, which is a different cost class, and the panel should say
so. What it must not do is overturn the recommendation, because this is a
terrain SCREEN and not a propagation model: no clutter, no rain fade, no
multipath, no capacity. ITU-R P.1812 is the calculation that would earn the
right to decide, and we do not run it.

Same rule as the terrain drop and the power flag. Context that changes what a
build costs, never a signal that decides who is badly served.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dataset" / "ml" / "tower_isolated.csv"
GEO = ROOT / "dataset" / "web" / "dipi.geojson"
LOS = ROOT / "dataset" / "web" / "towers_los.json"
OUT = ROOT / "dataset" / "web" / "isolated.json"

RADII = ("3", "5", "10")
TRUE = {"1", "true", "True", "yes"}


def die(msg):
    raise SystemExit("export_isolated.py FAILED: " + msg)


rows = list(csv.DictReader(SRC.open(encoding="utf8")))
props = {f["properties"]["settlement_id"]: f["properties"]
         for f in json.loads(GEO.read_text(encoding="utf8"))["features"]}

missing = [r["settlement_id"] for r in rows if r["settlement_id"] not in props]
if missing:
    die(f"{len(missing)} ids are not in dipi.geojson, first: {missing[:3]}")

out = {r_km: sorted(r["settlement_id"] for r in rows
                    if r[f"only_self_{r_km}km"].strip() in TRUE)
       for r_km in RADII}

# 1. Reach can only improve as the radius grows, so the sets must nest. If a
#    settlement were isolated at 10 km but not at 3, the screen contradicts
#    itself and nothing downstream should be trusted.
for a, b in (("3", "5"), ("5", "10")):
    grew = set(out[b]) - set(out[a])
    if grew:
        die(f"{len(grew)} settlements are isolated at {b} km but not at {a} km, "
            f"which is impossible. First: {sorted(grew)[:3]}")

# 2. Must agree with the scenario counts already published, or the panel and
#    the drill-down would quote different figures for the same thing.
los = json.loads(LOS.read_text(encoding="utf8"))
for sc in los["scenarios"]:
    r_km = str(sc["radius_km"])
    want = sc["fresnel"]["only_self_reachable"]
    if len(out[r_km]) != want:
        die(f"at {r_km} km this file has {len(out[r_km])} isolated but "
            f"towers_los.json says {want}")

# 3. Every one of these should be a settlement the recommender sends to a
#    tower. If not, the two are reading different inputs.
n_tower = los["n_tower_settlements"]
if len(rows) != n_tower:
    die(f"{len(rows)} rows against {n_tower} tower settlements")

OUT.write_text(json.dumps({
    "_what": ("Settlements the terrain screen can reach only from a mast in their own "
              "village. No other candidate site clears line of sight and 60% Fresnel."),
    "_not": ("NOT a coverage prediction and NOT a reason to change the recommended option. "
             "It qualifies one: a tower here is a dedicated mast, not a shared one, which "
             "is a different cost class. ITU-R P.1812 is the calculation that would earn "
             "the right to decide, and it is not run here."),
    "_why_not_serves_1": ("towers_los.json carries serves == 1, which is a mast the greedy "
                          "solver happened to leave covering only itself. This file is the "
                          "terrain property: no other site can reach it, whatever solver runs."),
    "counts": {r_km: len(out[r_km]) for r_km in RADII},
    "of_tower_settlements": n_tower,
    "ids": out,
}, indent=1) + "\n", encoding="utf8")

for r_km in RADII:
    print(f"{r_km:>2} km  {len(out[r_km]):>3} of {n_tower} reachable only from themselves")
print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1024:.1f} KB)")

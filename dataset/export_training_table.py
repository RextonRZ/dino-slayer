"""Build the ML training table for the coverage model.

    python dataset/export_training_table.py

Writes dataset/ml/training_table.csv, one row per settlement, with:
  * the non-network features only (leaky columns are deliberately absent)
  * district and division, joined by point-in-polygon, so GroupKFold works
  * a `split` column: train / validate / check / predict

Nothing is imputed. Missing stays empty so XGBoost sees NaN.
See ml/model_ablations.json for why each column is in or out.

Implementation:
training_table.csv (1,448 rows) reads dipi.geojson, 
works out which district and division each settlement falls in, 
picks the 11 feature columns, and stamps the split column: 
850 train, 264 validate, 118 check, 216 predict. 
It deliberately leaves out anything to do with speed tests, otherwise the model would be predicting speed from speed.
"""
import csv
import bisect
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "dataset" / "web"
OUT = ROOT / "dataset" / "ml" / "training_table.csv"

DIVISIONS = {
    "West Coast": ["KotaKinabalu", "Penampang", "Putatan", "Papar", "Tuaran", "KotaBelud", "Ranau"],
    "Kudat":      ["Kudat", "KotaMarudu", "Pitas"],
    "Interior":   ["Beaufort", "KualaPenyu", "Sipitang", "Tenom", "Nabawan", "Keningau", "Tambunan"],
    "Sandakan":   ["Sandakan", "Beluran", "Kinabatangan", "Tongod"],
    "Tawau":      ["Tawau", "LahadDatu", "Semporna", "Kunak"],
}
DIVISION_OF = {d: k for k, v in DIVISIONS.items() for d in v}

FEATURES = ["pop_2km", "n_schools_3km", "n_clinics_3km", "rwi", "elevation_m",
            "seasonal_water_px", "flood_prone", "place"]

# Layer 2, derived here rather than left to the modeller so the training table,
# the dashboard and the agent all use one definition.
#
#   backhaul_km      distance to the nearest town or city. A stand-in for
#                    distance to backhaul, from OSM place types, not a survey of
#                    where fibre actually terminates.
#   elev_drop_m      metres below (negative) or above that town. Masts cluster
#                    at towns, so a large drop means terrain is more likely in
#                    the way. A proxy from point elevations: no line-of-sight
#                    calculation is possible from this data, and none is implied.
#   elev_pct_district  elevation percentile inside its own district, so "high"
#                    is judged against the local area rather than sea level.
#
# Measured against the 1,114 scored settlements, raw elevation is the strongest
# of these (Spearman -0.25 with download speed), ahead of backhaul_km (-0.10)
# and elev_drop_m (-0.08). All three are offered; the model decides.
TERRAIN = ["backhaul_km", "elev_drop_m", "elev_pct_district"]


def ring_contains(ring, x, y):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def build_index(districts):
    idx = []
    for f in districts["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        xs = [p[0] for poly in polys for p in poly[0]]
        ys = [p[1] for poly in polys for p in poly[0]]
        idx.append((f["properties"]["NAME_2"], polys, (min(xs), min(ys), max(xs), max(ys))))
    return idx


def district_of(idx, x, y):
    for name, polys, bb in idx:
        if not (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]):
            continue
        for poly in polys:
            if ring_contains(poly[0], x, y) and not any(ring_contains(h, x, y) for h in poly[1:]):
                return name
    return None


def split_of(p):
    """measured = clean labels; low_evidence = noisy, hold out; no speed = the prize."""
    if p["dl_mbps"] is None:
        return "predict"
    if p["evidence_tier"] == "measured":
        return "train"
    if p["evidence_tier"] == "low_evidence":
        return "validate"
    return "check"


def hav_km(lon1, lat1, lon2, lat2):
    """Haversine, identical to the dashboard's havKm() and the agent's, so all
    three pick the same nearest town and quote the same drop."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def build_terrain(feats, district_of_id):
    """Nearest town, the drop to it, and elevation percentile within the district.

    One sweep over the 59 town/city anchors, same as the dashboard does in JS.
    """
    anchors = [f for f in feats if f["properties"]["place"] in ("city", "town")]
    by_district = {}
    for f in feats:
        d = district_of_id.get(f["properties"]["settlement_id"]) or ""
        e = f["properties"].get("elevation_m")
        if e is not None:
            by_district.setdefault(d, []).append(e)
    for arr in by_district.values():
        arr.sort()

    out = {}
    for f in feats:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        best, anchor = None, None
        for a in anchors:
            if a is f:
                best, anchor = 0.0, a
                break
            ax, ay = a["geometry"]["coordinates"]
            d = hav_km(lon, lat, ax, ay)
            if best is None or d < best:
                best, anchor = d, a
        e = p.get("elevation_m")
        ae = anchor["properties"].get("elevation_m") if anchor else None
        drop = None if (e is None or ae is None or not best) else round(e - ae)

        arr = by_district.get(district_of_id.get(p["settlement_id"]) or "", [])
        pct = None
        if e is not None and len(arr) >= 5:
            lo = bisect.bisect_left(arr, e)
            eq = bisect.bisect_right(arr, e) - lo
            # floor(x+0.5), not round(): Python rounds halves to even and JS
            # rounds them up, which is a whole percentile of disagreement.
            pct = math.floor(((lo + (eq + 1) / 2) / len(arr)) * 100 + 0.5)
        out[p["settlement_id"]] = {
            "backhaul_km": None if best is None else round(best, 2),
            "elev_drop_m": drop,
            "elev_pct_district": pct,
        }
    return out


def main():
    dipi = json.loads((WEB / "dipi.geojson").read_text(encoding="utf8"))
    districts = json.loads((WEB / "sabah_districts.geojson").read_text(encoding="utf8"))
    idx = build_index(districts)

    district_of_id = {}
    for f in dipi["features"]:
        lon, lat = f["geometry"]["coordinates"]
        district_of_id[f["properties"]["settlement_id"]] = district_of(idx, lon, lat)
    terrain = build_terrain(dipi["features"], district_of_id)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = (["settlement_id", "name", "lon", "lat", "district", "division"]
            + FEATURES + TERRAIN + ["dl_mbps", "split", "evidence_tier_REFERENCE_ONLY"])

    counts, unmatched = {}, 0
    with OUT.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in dipi["features"]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"]
            d = district_of(idx, lon, lat)
            if d is None:
                unmatched += 1
            s = split_of(p)
            counts[s] = counts.get(s, 0) + 1
            t = terrain[p["settlement_id"]]
            w.writerow([p["settlement_id"], p["name"] or "", lon, lat, d or "", DIVISION_OF.get(d, "")]
                       + [("" if p[k] is None else p[k]) for k in FEATURES]
                       + [("" if t[k] is None else t[k]) for k in TERRAIN]
                       + ["" if p["dl_mbps"] is None else p["dl_mbps"], s, p["evidence_tier"]])

    print("wrote", OUT)
    print("  rows          :", sum(counts.values()))
    print("  splits        :", counts)
    print("  no district   :", unmatched)
    print("  columns       :", len(cols))
    leaky = {"p_connectivity", "dipi", "rank", "ul_mbps", "latency_ms", "n_tests", "n_tiles"}
    print("  leaky columns present:", sorted(leaky & set(cols)) or "none")


if __name__ == "__main__":
    main()

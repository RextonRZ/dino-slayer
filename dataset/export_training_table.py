"""Build the ML training table for the coverage model.

    python dataset/export_training_table.py

Writes dataset/ml/training_table.csv, one row per settlement, with:
  * the non-network features only (leaky columns are deliberately absent)
  * district and division, joined by point-in-polygon, so GroupKFold works
  * a `split` column: train / validate / check / predict

Nothing is imputed. Missing stays empty so XGBoost sees NaN.
See COVERAGE_MODEL_GUIDE.md for why each column is in or out.
"""
import csv
import json
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


def main():
    dipi = json.loads((WEB / "dipi.geojson").read_text(encoding="utf8"))
    districts = json.loads((WEB / "sabah_districts.geojson").read_text(encoding="utf8"))
    idx = build_index(districts)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = (["settlement_id", "name", "lon", "lat", "district", "division"]
            + FEATURES + ["dl_mbps", "split", "evidence_tier_REFERENCE_ONLY"])

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
            w.writerow([p["settlement_id"], p["name"] or "", lon, lat, d or "", DIVISION_OF.get(d, "")]
                       + [("" if p[k] is None else p[k]) for k in FEATURES]
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

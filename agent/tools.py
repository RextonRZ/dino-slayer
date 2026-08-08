"""The grounded tool layer. Python computes; the agent only narrates.

Every number Tanya Dino says must come out of a function in this file. Nothing
here imports an LLM, and nothing here is prompted, these are plain pandas
functions over the project's own parquet, testable on their own:

    python -m agent.tools        # runs a self-test over real rows

Thresholds and weights are copied from the dashboard deliberately, so the agent
and the map can never disagree about a number.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SETTLEMENTS = ROOT / "dataset" / "settlements"

DISCLAIMER = "Screening for further assessment — not a coverage determination."
LOW_EV_WARNING = ("Some rows rest on limited tests, prioritise field validation.")

# Same numbers as the dashboard simulator.
VIDEO_TIERS = {"360p": 0.7, "480p": 1.1, "720p": 2.5, "1080p": 5.0, "4k": 20.0}
WEIGHTS = {"p_connectivity": 0.40, "p_population": 0.25,
           "p_institutions": 0.15, "p_equity": 0.20}
# Where each of these comes from is recorded in dataset/web/sources.json,
# parameter by parameter, with the quote and how far it was verified.
# Short version: everything here is sourced except fibre_max_km, most of it
# from ITU's Last-mile Guide. RULES_VERIFIED stays false until that one is.
RULE_PARAMS = {"fibre_max_km": 15, "fibre_min_pop": 3000,
               "fwa_max_km": 40, "fwa_min_pop": 500, "sat_min_km": 40}
# No per-unit Malaysian cost is public. These are benchmarked against
# published models rather than quoted -- see dataset/web/sources.json.
COSTS = {  # DEMO_PLACEHOLDER, not procurement figures
    "low":  {"fibre_per_km": 90000,  "fwa": 350000, "sat": 9000,  "wifi": 45000},
    "base": {"fibre_per_km": 140000, "fwa": 520000, "sat": 14000, "wifi": 70000},
    "high": {"fibre_per_km": 210000, "fwa": 780000, "sat": 21000, "wifi": 105000},
}


def _load() -> pd.DataFrame:
    """The coverage model output if it exists, else the DIPI table.

    Neither parquet carries a district (it is derived by point-in-polygon), so
    we join the same answer the dashboard uses from the ML training table.
    Rebuild that with `python dataset/export_training_table.py`.
    """
    for name in ("settlements_sabah_04_model.parquet", "settlements_sabah_03_dipi.parquet"):
        p = SETTLEMENTS / name
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        df.attrs["source_file"] = name
        tt = ROOT / "dataset" / "ml" / "training_table.csv"
        if tt.exists():
            g = pd.read_csv(tt, usecols=["settlement_id", "district", "division", "lon", "lat"])
            df = df.merge(g, on="settlement_id", how="left")
        for c in ("district", "division"):
            if c not in df.columns:
                df[c] = ""
            df[c] = df[c].fillna("")
        return df
    raise SystemExit(f"no settlements parquet under {SETTLEMENTS}")


DF = _load()
HAS_MODEL = "speed_source" in DF.columns

# Fibre build clusters, written by dataset/export_clusters.py. Optional: an
# empty dict makes optimise_budget charge the full run to town, which is what
# it did before the clustering existed. The dashboard reads the same file.
try:
    CLUSTERS = json.loads((ROOT / "dataset" / "web" / "clusters.json")
                          .read_text(encoding="utf8"))
except (OSError, ValueError):
    CLUSTERS = {}


# ── facilities, with a district each ─────────────────────────────────────────
# The facilities file carries no district: like the settlements, it is derived
# by point-in-polygon. The dashboard does that in JS at load. Doing it here the
# same way, against the same GADM polygons, is what keeps the agent and the map
# from disagreeing about which district a school sits in.
WEB = ROOT / "dataset" / "web"
AMENITY_LABEL = {"school": "School", "clinic": "Clinic",
                 "hospital": "Hospital", "doctors": "Doctors"}


def _pip(x, y, ring) -> bool:
    """Ray casting against one ring. Same algorithm as the dashboard's."""
    inside, n = False, len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _polys(geom):
    """Every Polygon in a geometry, as a list of ring-lists."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    return []


def _load_districts():
    """(name, bbox, [polygon…]) per district, bbox first so 25 polygons stay cheap."""
    f = WEB / "sabah_districts.geojson"
    if not f.exists():
        return []
    import json
    out = []
    for feat in json.load(open(f, encoding="utf8"))["features"]:
        polys = _polys(feat.get("geometry") or {})
        if not polys:
            continue
        xs = [p[0] for poly in polys for ring in poly for p in ring]
        ys = [p[1] for poly in polys for ring in poly for p in ring]
        out.append((feat["properties"].get("NAME_2", ""),
                    (min(xs), min(ys), max(xs), max(ys)), polys))
    return out


_DISTRICT_POLYS = _load_districts()


def district_of(lon: float, lat: float) -> str:
    for name, (x0, y0, x1, y1), polys in _DISTRICT_POLYS:
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        # Even-odd across a polygon's own rings, so holes read as outside.
        for rings in polys:
            if sum(_pip(lon, lat, r) for r in rings) % 2 == 1:
                return name
    return ""


def _load_facilities() -> pd.DataFrame:
    f = WEB / "facilities.geojson"
    if not f.exists():
        return pd.DataFrame(columns=["facility_id", "name", "amenity", "kind",
                                     "lon", "lat", "district"])
    import json
    rows = []
    for feat in json.load(open(f, encoding="utf8"))["features"]:
        p, c = feat["properties"], feat["geometry"]["coordinates"]
        rows.append({"facility_id": p.get("facility_id"), "name": p.get("name"),
                     "amenity": p.get("amenity"), "kind": p.get("kind"),
                     "lon": c[0], "lat": c[1], "district": district_of(c[0], c[1])})
    return pd.DataFrame(rows)


FAC = _load_facilities()


# ── Layer 2: terrain ─────────────────────────────────────────────────────────
# The bootcamp's three-layer model for telecom GeoAI is network performance,
# physical landscape, and human demand. Ookla is the first, WorldPop and RWI the
# third; elevation is the second, and it is the strongest terrain signal in this
# file: it correlates -0.25 with measured download speed, a stronger
# relationship than distance to the nearest town (-0.10).
#
# Two derived values, both from the SRTM elevation already in the parquet, and
# both mirroring the dashboard exactly so the agent and the map cannot disagree:
#
#   elev_drop_m   metres below (negative) or above the nearest town or city.
#                 Masts cluster at towns, so a large drop means terrain is more
#                 likely in the way. A PROXY. We have point elevations, not a
#                 surface, so no line-of-sight calculation is possible and none
#                 is claimed.
#   elev_pct      elevation percentile inside its own district, which says
#                 whether a place is high or low FOR ITS AREA.
#
# Terrain never enters DIPI. It is context, like the flood layer.
TERRAIN_DROP_M = -150


def _add_terrain(df: pd.DataFrame) -> pd.DataFrame:
    if "lon" not in df.columns or "elevation_m" not in df.columns:
        df["elev_drop_m"] = None
        df["elev_anchor"] = ""
        df["elev_pct"] = None
        return df
    anchors = df[df["place"].isin(["city", "town"])]
    if not len(anchors):
        df["elev_drop_m"], df["elev_anchor"], df["elev_pct"] = None, "", None
        return df

    import numpy as np
    ax = anchors["lon"].to_numpy(); ay = anchors["lat"].to_numpy()
    ae = anchors["elevation_m"].to_numpy()
    an = [n if isinstance(n, str) and n.strip() else f"Unnamed settlement ({i})"
          for n, i in zip(anchors["name"], anchors["settlement_id"])]
    # Haversine, identical to the dashboard's havKm(). A flat approximation
    # picks a different nearest town for a handful of settlements, and then the
    # agent and the panel quote different drops for the same place.
    R = 6371.0
    la1 = np.radians(df["lat"].to_numpy())[:, None]
    lo1 = np.radians(df["lon"].to_numpy())[:, None]
    la2 = np.radians(ay)[None, :]
    lo2 = np.radians(ax)[None, :]
    h = (np.sin((la2 - la1) / 2) ** 2
         + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    km = 2 * R * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    j = km.argmin(axis=1)
    nearest_km = km[np.arange(len(df)), j]

    drop = df["elevation_m"].to_numpy() - ae[j]
    # A town is its own nearest anchor, so its drop is meaningless, not zero.
    drop = np.where(nearest_km < 1e-9, np.nan, drop)
    df["elev_drop_m"] = np.round(drop, 0)
    df["elev_anchor"] = [an[k] for k in j]
    df["backhaul_km"] = np.round(nearest_km, 2)
    # floor(x+0.5) so halves round the same way the dashboard's Math.round does.
    df["elev_pct"] = np.floor(df.groupby("district")["elevation_m"]
                                .rank(pct=True).mul(100) + 0.5)
    return df


DF = _add_terrain(DF)


def terrain_of(row) -> dict:
    """The terrain reading for one settlement, in the words the panel uses."""
    drop = row.get("elev_drop_m")
    shadowed = drop is not None and not pd.isna(drop) and drop <= TERRAIN_DROP_M
    return {
        "elevation_m": _num(row.get("elevation_m"), 0),
        "elev_percentile_in_district": _num(row.get("elev_pct"), 0),
        "metres_vs_nearest_town": _num(drop, 0),
        "nearest_town": row.get("elev_anchor") or None,
        "terrain_shadow_risk": bool(shadowed),
    }


def _s(v) -> str:
    """Coerce whatever the model actually passed into a clean string.

    An LLM does not always honour its own tool schema. Gemini has been observed
    sending {"district": ["Kota Marudu"]} where the schema says string, which
    reached .lower() and killed the turn with "'list' object has no attribute
    'lower'". A tool must never fail on the SHAPE of its arguments, only on
    their meaning.
    """
    if v is None or isinstance(v, bool):
        return ""
    if isinstance(v, (list, tuple, set)):
        v = next((x for x in v if x not in (None, "")), "")
    if isinstance(v, dict):
        v = v.get("name") or v.get("value") or v.get("district") or ""
    return str(v).strip()


def _i(v, default=0) -> int:
    try:
        return int(float(_s(v)))
    except (TypeError, ValueError):
        return default


def _f(v, default=0.0) -> float:
    try:
        return float(str(_s(v)).replace(",", "").replace("RM", "").strip())
    except (TypeError, ValueError):
        return default


def _key(s) -> str:
    """Fold a place name to letters only, so 'Kota Marudu', 'KOTA MARUDU' and
    the file's own 'KotaMarudu' all compare equal."""
    return re.sub(r"[^a-z]", "", _s(s).lower())


def _label(s) -> str:
    """'KotaMarudu' -> 'Kota Marudu'. Same split the dashboard does, so the two
    never print a district name differently."""
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", _s(s)) or "Outside district boundaries"


def display_name(row) -> str:
    n = row.get("name")
    return n if isinstance(n, str) and n.strip() else f"Unnamed settlement ({row['settlement_id']})"


def find(query: str):
    """Match on id, exact name, then substring. Returns (row|None, alternatives)."""
    q = str(query or "").strip().lower()
    if not q:
        return None, []
    hit = DF[DF["settlement_id"].str.lower() == q]
    if len(hit):
        return hit.iloc[0], []
    named = DF[DF["name"].notna()]
    exact = named[named["name"].str.lower() == q]
    if len(exact):
        return exact.iloc[0], []
    part = named[named["name"].str.lower().str.contains(re.escape(q), na=False)]
    if len(part) == 1:
        return part.iloc[0], []
    if len(part) > 1:
        return part.iloc[0], [display_name(r) for _, r in part.iloc[1:6].iterrows()]
    return None, []


def _num(v, nd=1):
    return None if v is None or pd.isna(v) else round(float(v), nd)


# ── the nine tools ───────────────────────────────────────────────────────────
def rank_settlements(district: str = "", division: str = "",
                     top_k: int = 10, require_school: bool = False) -> dict:
    district, division, top_k = _s(district), _s(division), _i(top_k, 10)
    d = DF[DF["dipi"].notna()]
    if district:
        d = d[d["district"].map(_key) == _key(district)]
    elif division:
        d = d[d["division"].map(_key) == _key(division)]
    if require_school:
        d = d[d["n_schools_3km"] >= 1]
    d = d.sort_values("rank").head(max(1, int(top_k)))
    rows = [{"rank": int(r["rank"]), "name": display_name(r), "district": _label(r["district"]),
             "dipi": _num(r["dipi"]), "dl_mbps": _num(r["dl_mbps"]),
             "evidence": r["evidence_tier"]} for _, r in d.iterrows()]
    return {"rows": rows, "ids": list(d["settlement_id"]),
            "note": "No scored settlements match that filter." if not rows else ""}


def explain_priority(name_or_id: str) -> dict:
    name_or_id = _s(name_or_id)
    row, alts = find(name_or_id)
    if row is None:
        return {"rows": [], "ids": [], "note": f"No settlement matches '{name_or_id}'."}
    if pd.isna(row["dipi"]):
        return {"rows": [], "ids": [row["settlement_id"]],
                "note": (f"{display_name(row)} is not scored. Evidence needed: too few "
                         f"measurements to place it in the ranking.")}
    rows = [{"pillar": k.replace("p_", ""), "score_0_100": _num(row[k] * 100),
             "weight": f"{int(WEIGHTS[k]*100)}%"} for k in WEIGHTS]
    # The measurement itself. Nothing returned it before, so "what does this
    # settlement actually read?" was unanswerable: the agent fell through to
    # predict_coverage, got "the model has not shipped", and told the user it
    # could not confirm a speed that was sitting in the file all along. It also
    # makes a connectivity pillar of 0.2 legible, that is 0.2 NEED, because the
    # place is fast, and without the speed beside it the score reads backwards.
    measured = {"dl_mbps": _num(row["dl_mbps"]), "ul_mbps": _num(row["ul_mbps"]),
                "latency_ms": _num(row["latency_ms"], 0), "n_tests": int(row["n_tests"]),
                "evidence": row["evidence_tier"]}
    return {"rows": rows, "ids": [row["settlement_id"]],
            "name": display_name(row), "rank": int(row["rank"]), "dipi": _num(row["dipi"]),
            "evidence": row["evidence_tier"], "n_tests": int(row["n_tests"]),
            "measured": measured,
            # Terrain is context, never a pillar. It travels alongside the score
            # so the agent can explain a slow link, not justify the ranking.
            "terrain": terrain_of(row),
            "alternatives": alts, "note": ""}


def compare_settlements(name_a: str, name_b: str) -> dict:
    name_a, name_b = _s(name_a), _s(name_b)
    ra, _ = find(name_a)
    rb, _ = find(name_b)
    missing = [n for n, r in ((name_a, ra), (name_b, rb)) if r is None]
    if missing:
        return {"rows": [], "ids": [], "note": f"No match for: {', '.join(missing)}."}
    rows = []
    for k in WEIGHTS:
        rows.append({"pillar": k.replace("p_", ""),
                     display_name(ra): _num(ra[k] * 100), display_name(rb): _num(rb[k] * 100)})
    rows.append({"pillar": "DIPI", display_name(ra): _num(ra["dipi"]),
                 display_name(rb): _num(rb["dipi"])})
    return {"rows": rows, "ids": [ra["settlement_id"], rb["settlement_id"]], "note": ""}


def simulate_experience(name_or_id: str, task: str = "720p", users: int = 5) -> dict:
    name_or_id, task, users = _s(name_or_id), _s(task) or "720p", max(1, _i(users, 5))
    row, _ = find(name_or_id)
    if row is None:
        return {"rows": [], "ids": [], "note": f"No settlement matches '{name_or_id}'."}
    dl = row["dl_mbps"]
    if pd.isna(dl):
        return {"rows": [], "ids": [row["settlement_id"]],
                "note": (f"Evidence needed, {display_name(row)} has no speed measurement, "
                         f"so this cannot be simulated.")}
    users = max(1, int(users))
    per = float(dl) / users
    rows = [{"tier": t, "needs_mbps": n, "per_user_mbps": round(per, 2),
             "verdict": "Smooth" if per >= n * 1.5 else "May buffer" if per >= n else "Unlikely"}
            for t, n in VIDEO_TIERS.items()]
    best = max((t for t, n in VIDEO_TIERS.items() if per >= n * 1.5),
               key=lambda t: VIDEO_TIERS[t], default=None)
    return {"rows": rows, "ids": [row["settlement_id"]], "name": display_name(row),
            "measured_mbps": _num(dl), "users": users, "per_user_mbps": round(per, 2),
            "highest_smooth_tier": best, "evidence": row["evidence_tier"],
            "flags": ["assumption_equal_sharing"],
            "assumption": "Simplified equal-sharing model, an assumption, not a measurement.",
            "note": ""}


def predict_coverage(name_or_id: str) -> dict:
    name_or_id = _s(name_or_id)
    if not HAS_MODEL:
        return {"rows": [], "ids": [], "note": "The coverage model has not shipped yet."}
    row, _ = find(name_or_id)
    if row is None:
        return {"rows": [], "ids": [], "note": f"No settlement matches '{name_or_id}'."}
    return {"rows": [{"speed_source": row.get("speed_source"),
                      "pred_dl_mbps": _num(row.get("pred_dl_mbps"), 2),
                      "pred_lo": _num(row.get("pred_lo"), 2),
                      "pred_hi": _num(row.get("pred_hi"), 2),
                      "shap_top3": row.get("shap_top3")}],
            "ids": [row["settlement_id"]],
            "flags": (["modelled"] if row.get("speed_source") == "modelled estimate" else []),
            "note": "Modelled estimate, not a measurement." if row.get("speed_source") ==
                    "modelled estimate" else "This settlement has an observed measurement."}


def recommend_intervention(name_or_id: str) -> dict:
    name_or_id = _s(name_or_id)
    row, _ = find(name_or_id)
    if row is None:
        return {"rows": [], "ids": [], "note": f"No settlement matches '{name_or_id}'."}
    anchors = DF[DF["place"].isin(["city", "town"])]
    if "lon" not in DF.columns or pd.isna(row.get("lon")):
        return {"rows": [], "ids": [row["settlement_id"]],
                "note": "Insufficient evidence to recommend (no coordinates)."}
    dx = (anchors["lon"] - row["lon"]) * 111.32 * 0.995
    dy = (anchors["lat"] - row["lat"]) * 110.57
    km = float(((dx ** 2 + dy ** 2) ** 0.5).min())
    pop = float(row["pop_2km"] or 0)
    inst = int((row["n_schools_3km"] or 0) + (row["n_clinics_3km"] or 0))
    R, why = RULE_PARAMS, []
    if km <= R["fibre_max_km"] and pop >= R["fibre_min_pop"]:
        opt = "Fibre"; why = [f"{km:.1f} km to the nearest town or city", f"{int(pop)} people within 2 km"]
    elif km <= R["fwa_max_km"] and pop >= R["fwa_min_pop"]:
        opt = "Tower / fixed wireless"; why = [f"{km:.1f} km out", f"{int(pop)} people within 2 km"]
    elif km > R["sat_min_km"]:
        opt = "Satellite"; why = [f"{km:.1f} km from the nearest town or city"]
    else:
        opt = "Community Wi-Fi at an institution"
        why = [f"{inst} school or clinic within 3 km", f"only {int(pop)} people within 2 km"]
    t = terrain_of(row)
    if t["terrain_shadow_risk"]:
        why.append(f"sits {abs(int(t['metres_vs_nearest_town']))} m below {t['nearest_town']}, "
                   f"so a line of sight to a mast there cannot be assumed")
    if row["flood_prone"]:
        why.append("seasonal water adjacency: siting needs field checks")
    return {"rows": [{"option": opt, "reasons": "; ".join(why)}], "ids": [row["settlement_id"]],
            "terrain": t,
            "flags": ["illustrative_rules"],
            "label": "Illustrative decision criteria pending source verification. Prototype only.",
            "note": "Rules-based decision support, not a trained model."}


def optimise_budget(budget_rm: float, district: str = "", scenario: str = "base") -> dict:
    budget_rm, district = _f(budget_rm), _s(district)
    scenario = _s(scenario).lower() or "base"
    c = COSTS.get(scenario, COSTS["base"])
    d = DF if not district else DF[DF["district"].map(_key) == _key(district)]
    items = []
    for _, r in d.iterrows():
        rec = recommend_intervention(r["settlement_id"])
        if not rec["rows"]:
            continue
        opt = rec["rows"][0]["option"]
        # Fibre is costed over the ACTUAL distance to the nearest town, the same
        # way the dashboard does it. A flat ten-kilometre assumption here meant
        # the copilot and the panel gave different answers to the same question:
        # at RM 50m the agent funded 52 settlements and the panel 171.
        km = float(r["backhaul_km"]) if pd.notna(r["backhaul_km"]) else 10.0
        # The cheaper of the shared spur and the direct run, matching the
        # dashboard. Sharing is not always cheaper: some settlements sit further
        # from their bundle neighbour than from the town. CLUSTERS is the same
        # file the panel loads; without it both fall back to the full run in.
        km = min(km, CLUSTERS.get(r["settlement_id"], {}).get("trunk_km", km))
        cost = (c["fibre_per_km"] * max(1.0, km) if opt == "Fibre"
                else c["fwa"] if "wireless" in opt
                else c["sat"] if opt == "Satellite" else c["wifi"])
        pop = float(r["pop_2km"] or 0)
        items.append((pop / cost, cost, r, opt))
    items.sort(key=lambda t: -t[0])
    spent, funded = 0.0, []
    for _, cost, r, opt in items:
        if spent + cost > budget_rm:
            continue
        spent += cost
        funded.append({"name": display_name(r), "option": opt, "cost_rm": int(cost),
                       "id": r["settlement_id"]})
    return {"rows": funded[:25], "ids": [f["id"] for f in funded],
            "funded_count": len(funded), "spent_rm": int(spent), "budget_rm": int(budget_rm),
            "flags": ["illustrative_cost"],
            "label": "Illustrative planning assumptions, not procurement estimates.",
            "note": ("Counts are settlements. Population buffers overlap, so people cannot "
                     "be summed without double counting.")}


def district_summary(district: str = "", sort_by: str = "facilities", top_k: int = 25) -> dict:
    """One row per district: how many settlements, how much evidence, how many
    real schools and health points sit inside it.

    Facilities are counted from the facilities file by point-in-polygon, NOT by
    summing n_schools_3km. Those are 3 km buffer counts and they overlap, so a
    school near five villages would be counted five times. Same class of error
    as summing pop_2km, and it is not made here.
    """
    district, sort_by, top_k = _s(district), _s(sort_by).lower(), max(1, min(_i(top_k, 25), 30))
    scored = DF[DF["dipi"].notna()]
    rows = []
    names = sorted({d for d in DF["district"] if d}) if not district else \
            [d for d in {x for x in DF["district"] if x} if _key(d) == _key(district)]
    if district and not names:
        return {"rows": [], "ids": [], "flags": [],
                "note": f"No district matches '{district}'. Sabah has 25 GADM districts."}
    for name in names:
        s = DF[DF["district"] == name]
        sc = scored[scored["district"] == name]
        f = FAC[FAC["district"] == name]
        med = sc["dl_mbps"].median()
        rows.append({
            "district": _label(name),
            "schools": int((f["kind"] == "school").sum()),
            "health": int((f["kind"] == "health").sum()),
            "facilities": int(len(f)),
            "settlements": int(len(s)),
            "scored": int(len(sc)),
            "evidence_gap": int((s["evidence_tier"] == "insufficient").sum()),
            "median_dl_mbps": _num(med),
            "median_elevation_m": _num(s["elevation_m"].median(), 0),
            "terrain_shadowed": int((s["elev_drop_m"] <= TERRAIN_DROP_M).sum()),
            "top_dipi": _num(sc["dipi"].max()) if len(sc) else None,
        })
    key = {"facilities": "facilities", "schools": "schools", "health": "health",
           "settlements": "settlements", "scored": "scored",
           "evidence_gap": "evidence_gap", "priority": "top_dipi",
           "top_dipi": "top_dipi", "elevation": "median_elevation_m",
           "terrain": "terrain_shadowed"}.get(sort_by, "facilities")
    reverse = key != "median_dl_mbps"
    rows.sort(key=lambda r: (r[key] is None, r[key] if r[key] is not None else 0),
              reverse=reverse)
    rows = rows[:top_k]
    ids = list(DF[DF["district"].map(_key).isin({_key(r["district"]) for r in rows})
                  & DF["dipi"].notna()]["settlement_id"]) if district else []
    note = ("Schools and health points are counted inside the district boundary from "
            "OpenStreetMap. They are not the settlement 3 km buffer counts, which overlap "
            "and cannot be summed. OSM coverage of rural facilities is incomplete, so a "
            "low count is not proof that few exist.")
    return {"rows": rows, "ids": ids, "flags": ["osm_incomplete"], "note": note}


def _facility_connectivity():
    """Each facility joined to the nearest settlement that actually has a speed.

    "Which school is best placed" is not answerable from this data, because
    nobody has run a speed test at a school. The nearest defensible question is
    what the nearest MEASURED settlement reads, and how far away it is, so both
    travel with every row and the distance is what tells you how much to trust
    the reading.
    """
    import numpy as np
    if not len(FAC):
        return {}
    m = DF[DF["dl_mbps"].notna() & DF["lon"].notna()]
    if not len(m):
        return {}
    R = 6371.0
    la1 = np.radians(FAC["lat"].to_numpy())[:, None]
    lo1 = np.radians(FAC["lon"].to_numpy())[:, None]
    la2 = np.radians(m["lat"].to_numpy())[None, :]
    lo2 = np.radians(m["lon"].to_numpy())[None, :]
    h = (np.sin((la2 - la1) / 2) ** 2
         + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)
    km = 2 * R * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    j = km.argmin(axis=1)
    names = [display_name(r) for _, r in m.iterrows()]
    speeds = m["dl_mbps"].to_numpy()
    tiers = m["evidence_tier"].to_numpy()
    return {fid: {"nearest_settlement": names[k],
                  "km_to_it": round(float(km[i, k]), 2),
                  "its_dl_mbps": round(float(speeds[k]), 1),
                  "its_evidence": str(tiers[k])}
            for i, (fid, k) in enumerate(zip(FAC["facility_id"], j))}


FAC_CONN = _facility_connectivity()

# How far a facility may borrow a speed from before the borrowing stops meaning
# anything. Same 3 km the institutions pillar uses to decide a school is served.
FAC_NEAR_KM = 3.0


def list_facilities(district: str = "", kind: str = "", limit: int = 50,
                    sort_by: str = "name") -> dict:
    """The actual named schools and health points, optionally in one district.

    kind: school, health, hospital, clinic, doctors, or empty for everything.
    sort_by: name, fastest or slowest, by the nearest measured settlement.
    """
    district, kind = _s(district), _s(kind).lower()
    limit, sort_by = max(1, min(_i(limit, 50), 200)), _s(sort_by).lower() or "name"
    f = FAC
    if district:
        f = f[f["district"].map(_key) == _key(district)]
        if not len(f):
            return {"rows": [], "ids": [], "flags": [],
                    "note": f"No facility in this file falls inside '{district}'."}
    if kind in ("school", "health"):
        f = f[f["kind"] == kind]
    elif kind in AMENITY_LABEL:
        f = f[f["amenity"] == kind]
    elif kind:
        return {"rows": [], "ids": [], "flags": [],
                "note": f"Unknown kind '{kind}'. Use school, health, hospital, clinic or doctors."}

    total = len(f)
    named = f[f["name"].notna() & (f["name"].astype(str).str.strip() != "")].copy()
    unnamed = total - len(named)

    named["_dl"] = named["facility_id"].map(
        lambda i: (FAC_CONN.get(i) or {}).get("its_dl_mbps"))
    named["_km"] = named["facility_id"].map(
        lambda i: (FAC_CONN.get(i) or {}).get("km_to_it"))

    ranked = sort_by in ("fastest", "best", "slowest", "worst")
    far = 0
    if ranked:
        # Ranking facilities by a borrowed speed only means something while the
        # borrowing is close. Without this a school 4 km from a fast town beat a
        # school 300 m from a slower one, and the list read as though the far
        # school were better connected. 3 km is the same radius the institutions
        # pillar uses, so the whole product draws the line in one place.
        near = named[named["_km"].notna() & (named["_km"] <= FAC_NEAR_KM)]
        far = len(named) - len(near)
        named = near
    if sort_by in ("fastest", "best"):
        shown = named.sort_values("_dl", ascending=False, na_position="last").head(limit)
    elif sort_by in ("slowest", "worst"):
        shown = named.sort_values("_dl", ascending=True, na_position="last").head(limit)
    else:
        shown = named.sort_values(["amenity", "name"]).head(limit)

    rows = []
    for _, r in shown.iterrows():
        c = FAC_CONN.get(r["facility_id"]) or {}
        rows.append({"name": r["name"], "type": AMENITY_LABEL.get(r["amenity"], r["amenity"]),
                     "district": _label(r["district"]),
                     "nearest_settlement": c.get("nearest_settlement"),
                     "km_to_it": c.get("km_to_it"),
                     "its_dl_mbps": c.get("its_dl_mbps"),
                     "its_evidence": c.get("its_evidence")})

    bits = [f"{total} facilit{'y' if total == 1 else 'ies'} in this file"]
    if len(rows) < len(named):
        bits.append(f"showing {len(rows)}"
                    + (" sorted by the nearest measured settlement's speed"
                       if ranked else " by name"))
    if unnamed:
        bits.append(f"{unnamed} carry no name in OpenStreetMap and are not listed")
    bits.append("Speed is measured at the nearest settlement that has a measurement, not at the "
                "facility itself, so read km_to_it before trusting it. Nobody has run a speed "
                "test at a school")
    if far:
        # The model is told the rule and the count, so it can answer "why is X
        # not on this list" instead of inventing a reason.
        bits.append(f"{far} named facilit{'y is' if far == 1 else 'ies are'} left out of this "
                    f"ranking because the nearest settlement with a measurement is more than "
                    f"{FAC_NEAR_KM:g} km away, which is too far to stand in for the facility. "
                    f"A fast settlement with no facility within {FAC_NEAR_KM:g} km therefore "
                    f"appears nowhere in this list")
    bits.append("OSM coverage of rural facilities is incomplete, so this is not a register")
    return {"rows": rows, "ids": [],
            "flags": ["osm_incomplete", "proxy_location"] + (["radius_capped"] if far else []),
            "note": ". ".join(bits) + "."}


def plan_survey(district: str = "", top_k: int = 10) -> dict:
    district, top_k = _s(district), _i(top_k, 10)
    d = DF[DF["evidence_tier"] == "insufficient"]
    if district:
        d = d[d["district"].map(_key) == _key(district)]
    d = d[d["stakes_score"].notna()].sort_values("stakes_score", ascending=False).head(int(top_k))
    rows = [{"name": display_name(r), "district": _label(r["district"]),
             "stakes": _num(r["stakes_score"]), "pop_2km": int(r["pop_2km"] or 0),
             "schools_3km": int(r["n_schools_3km"] or 0)} for _, r in d.iterrows()]
    return {"rows": rows, "ids": list(d["settlement_id"]),
            "note": "Ranked by stakes among settlements with no usable measurement."}


def generate_validation_report(district: str = "", top_k: int = 10) -> dict:
    district, top_k = _s(district), _i(top_k, 10)
    top = rank_settlements(district=district, top_k=top_k)
    survey = plan_survey(district=district, top_k=5)
    where = district or "Sabah"
    md = [f"# Field validation shortlist, {where}", "",
          f"{len(top['rows'])} highest-priority settlements by DIPI, and "
          f"{len(survey['rows'])} with no usable measurement.", "", "## Priority shortlist", ""]
    for r in top["rows"]:
        md.append(f"- **#{r['rank']} {r['name']}** ({r['district']}), DIPI {r['dipi']}, "
                  f"{'no speed measurement' if r['dl_mbps'] is None else str(r['dl_mbps']) + ' Mbps'}, "
                  f"evidence: {r['evidence']}")
    md += ["", "## Measure these first (no usable data)", ""]
    for r in survey["rows"]:
        md.append(f"- **{r['name']}** ({r['district']}), stakes {r['stakes']}, "
                  f"{r['pop_2km']} people within 2 km, {r['schools_3km']} school(s) within 3 km")
    md += ["", "## Recommended measurements", "",
           "- Speed tests at peak hours, multiple operators", "- School and clinic connectivity check",
           "- Short resident survey on affordability and usage", "",
           f"_{DISCLAIMER}_", "",
           "Generated from Dino Slayer DIPI, weights 40/25/15/20, Ookla 2025 Q1–Q4."]
    return {"rows": top["rows"], "ids": top["ids"] + survey["ids"],
            "markdown": "\n".join(md), "note": ""}


# ── District Decision Comparison ────────────────────────────────────────────
# "Why should District A be assessed before District B?" is the question this
# whole product exists to support, and until now the only way to ask it was to
# read two maps side by side.
#
# Everything here is a RATE or a MEDIAN. A raw total answers "which district is
# bigger", which nobody needed to ask: Ranau has 249 settlements and Kota
# Kinabalu has 46, so Ranau wins every count going and tells you nothing.

# Sharing 30 ways is the classroom case the dashboard already models, and 0.7
# Mbps is its 360p floor. Same arithmetic in the simulator, the rankings filter
# and here, so the three can never disagree.
CLASSROOM_USERS = 30
UNDERSERVED_MBPS = VIDEO_TIERS["360p"] * CLASSROOM_USERS      # 21.0 Mbps
REMOTE_KM = 20.0
# The dashboard can now put every district on screen at once, so the tool that
# answers questions about that view has to reach as far as the view does. It was
# capped at four, which would have silently compared the first four of a
# twenty-five-district selection and called the answer a comparison of all of them.
CMP_MAX_AREAS = 25


def _dedup_population(sub) -> int:
    """People near these settlements, with the overlap taken out.

    pop_2km is a 2 km buffer around each settlement, and rural settlements sit
    far closer together than 4 km. Summing the column counts the same villagers
    once per neighbour: across Ranau it inflates 73,771 people to 566,012, a
    factor of 7.7. Any "population affected" built by summing that column is
    wrong by most of its own value.

    So: link settlements whose buffers overlap, and take one figure per cluster
    rather than one per settlement. It is still an estimate of people NEAR the
    settlements, not a census, and it is deliberately conservative.
    """
    n = len(sub)
    if not n:
        return 0
    lon, lat = sub["lon"].to_numpy(), sub["lat"].to_numpy()
    pop = np.nan_to_num(sub["pop_2km"].to_numpy())
    if n == 1:
        return int(pop[0])
    la, lo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    h = (np.sin((la.T - la) / 2) ** 2
         + np.cos(la) * np.cos(la.T) * np.sin((lo.T - lo) / 2) ** 2)
    km = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    parent = list(range(n))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in zip(*np.where(np.triu(km <= 4.0, 1))):   # buffers touch at 4 km
        a, b = root(int(i)), root(int(j))
        if a != b:
            parent[a] = b
    best = {}
    for i in range(n):
        r = root(i)
        best[r] = max(best.get(r, 0.0), float(pop[i]))
    return int(round(sum(best.values())))


def _half_up(v, nd=0):
    """floor(x·10^nd + 0.5)/10^nd, not round().

    Python rounds halves to even and JavaScript rounds them up, so a district
    at exactly 62.5% measured came out 62 from the tool and 63 from the
    dashboard, the same disagreement that cost a percentile on the terrain
    columns. The comparison exists to be quoted in a paper, so the two
    implementations have to agree to the digit.
    """
    if v is None or pd.isna(v):
        return None
    m = 10 ** nd
    out = math.floor(float(v) * m + 0.5) / m
    return out if nd else int(out)


def _pct(part, whole):
    return None if not whole else _half_up(100.0 * part / whole, 0)


def _area_stats(sub, fac) -> dict:
    """One area's indicators. Measured-only wherever service is judged.

    Nothing here infers service from absence. A settlement with no measurement
    is counted in the evidence gap and is excluded from every speed statistic,
    it is never counted as slow.
    """
    # Service is judged only where the evidence supports judging it. 118
    # settlements in the insufficient tier still carry a dl_mbps, but the median
    # test count behind those readings is ZERO, they are tile artefacts. Letting
    # them into an underserved rate would turn "we have not measured here" into
    # "the service here is poor", which is the one inference this project refuses
    # to make. They stay in the evidence-gap share instead, which is where a
    # planner can act on them.
    meas = sub[sub["dl_mbps"].notna() & (sub["evidence_tier"] != "insufficient")]
    scored = sub[sub["dipi"].notna()]
    under = meas[meas["dl_mbps"] < UNDERSERVED_MBPS]
    severe = meas[meas["dl_mbps"] < VIDEO_TIERS["360p"]]
    gap = sub[sub["evidence_tier"] == "insufficient"]
    return {
        "settlements": int(len(sub)),
        "measured": int(len(meas)),
        "scored": int(len(scored)),

        # connectivity, medians, never means; one fibre-fed town skews a mean
        "median_dl_mbps": _half_up(meas["dl_mbps"].median(), 1),
        "median_ul_mbps": _half_up(meas["ul_mbps"].median(), 1),
        "median_latency_ms": _half_up(meas["latency_ms"].median(), 0),
        "underserved_rate_pct": _pct(len(under), len(meas)),
        "severe_rate_pct": _pct(len(severe), len(meas)),

        # people, deduplicated, and only for settlements actually measured slow
        "people_underserved": _dedup_population(under),
        "people_all": _dedup_population(sub),
        "median_pop_2km": _half_up(sub["pop_2km"].median(), 0),

        # evidence, the three tiers as shares, plus the sample behind them
        "measured_pct": _pct(int((sub["evidence_tier"] == "measured").sum()), len(sub)),
        "low_evidence_pct": _pct(int((sub["evidence_tier"] == "low_evidence").sum()), len(sub)),
        "evidence_gap_pct": _pct(len(gap), len(sub)),
        "median_tests": _half_up(sub["n_tests"].median(), 0),

        # accessibility, distance to the nearest town is the only remoteness
        # measure this dataset supports. There is no road network in it.
        "median_backhaul_km": _half_up(sub["backhaul_km"].median(), 1),
        "remote_rate_pct": _pct(int((sub["backhaul_km"] > REMOTE_KM).sum()), len(sub)),

        # terrain, context, never a pillar
        "median_elevation_m": _half_up(sub["elevation_m"].median(), 0),
        "terrain_shadow_pct": _pct(int((sub["elev_drop_m"] <= TERRAIN_DROP_M).sum()), len(sub)),

        # institutions, point-in-polygon, not summed 3 km buffers
        "schools": int((fac["kind"] == "school").sum()),
        "health": int((fac["kind"] == "health").sum()),
        "schools_underserved": int((under["n_schools_3km"] > 0).sum()),

        # priority
        "median_dipi": _half_up(scored["dipi"].median(), 1),
        "top_dipi": _half_up(scored["dipi"].max(), 1) if len(scored) else None,
        "in_sabah_top_100": int((scored["rank"] <= 100).sum()),
    }


# label, key, unit, higher_is_worse, group, and whether it is a rate.
# higher_is_worse drives the ranking and the summary: it is the only thing that
# knows 60% underserved is bad news and 60 Mbps is good news.
INDICATORS = [
    ("Median download",            "median_dl_mbps",      "Mbps", False, "Connectivity"),
    ("Median latency",             "median_latency_ms",   "ms",   True,  "Connectivity"),
    ("Below 360p at 30 users",     "underserved_rate_pct", "%",   True,  "Connectivity"),
    ("Below 360p for one user",    "severe_rate_pct",     "%",    True,  "Connectivity"),
    ("People in underserved areas", "people_underserved", "",     True,  "People"),
    ("Settlements",                "settlements",         "",     None,  "People"),
    ("Median people within 2 km",  "median_pop_2km",      "",     None,  "People"),
    ("Measured",                   "measured_pct",        "%",    False, "Evidence"),
    ("Low evidence",               "low_evidence_pct",    "%",    True,  "Evidence"),
    ("No usable measurement",      "evidence_gap_pct",    "%",    True,  "Evidence"),
    ("Median tests per settlement", "median_tests",       "",     False, "Evidence"),
    ("Median distance to a town",  "median_backhaul_km",  "km",   True,  "Remoteness"),
    ("More than 20 km from a town", "remote_rate_pct",    "%",    True,  "Remoteness"),
    ("Median elevation",           "median_elevation_m",  "m",    None,  "Terrain"),
    ("150 m below nearest town",   "terrain_shadow_pct",  "%",    True,  "Terrain"),
    ("Schools",                    "schools",             "",     None,  "Institutions"),
    ("Health points",              "health",              "",     None,  "Institutions"),
    ("Underserved with a school",  "schools_underserved", "",     True,  "Institutions"),
    ("Median DIPI",                "median_dipi",         "",     True,  "Priority"),
    ("In the Sabah top 100",       "in_sabah_top_100",    "",     True,  "Priority"),
]

# Indicators this dataset cannot supply. Named rather than quietly omitted, so
# a reader can see the shape of what is missing instead of assuming the
# comparison covers ground it does not.
NOT_AVAILABLE = [
    ("Road access and travel time", "no road network in this project"),
    ("Tower and backhaul infrastructure", "no operator or site data"),
    ("Slope", "SRTM gives point elevation here, not a derived slope surface"),
    ("Modelled speed and its uncertainty", "the coverage model has not shipped, "
     "so no settlement carries a prediction to compare"),
]

# How large a gap has to be before the summary calls it a difference. Below
# this the two areas are reported as comparable rather than ranked, because a
# 2-point spread on a screening index is not a planning signal.
MEANINGFUL = {"underserved_rate_pct": 10, "evidence_gap_pct": 10, "severe_rate_pct": 5,
              "remote_rate_pct": 10, "terrain_shadow_pct": 10, "median_dipi": 5,
              "median_dl_mbps": 5, "median_latency_ms": 15, "median_backhaul_km": 5}


def _summarise(areas: list, stats: dict, level: str) -> list:
    """The narrative, written by Python.

    Deterministic on purpose. It is the one part of the comparison a planner is
    most likely to paste into a paper, so it must say the same thing every time
    it is run, and it must not be able to invent a number. It also never says a
    cause: terrain and remoteness are ASSOCIATED with lower measured speed here,
    and this data cannot establish more than that.
    """
    if len(areas) < 2:
        return []
    lines = []
    # With three or four areas the interesting comparison is the spread, not
    # whichever two were typed first. Anchor the narrative on the extremes and
    # the middle areas still appear in every table row.
    ranked = sorted(areas, key=lambda x: (stats[x]["underserved_rate_pct"] is None,
                                          -(stats[x]["underserved_rate_pct"] or 0)))
    a, b = ranked[0], ranked[-1]
    sa, sb = stats[a], stats[b]
    if len(areas) > 2:
        lines.append(f"Across these {len(areas)} {level}s the widest service gap is between "
                     f"{a} and {b}; the others fall between them on most indicators.")

    def gap(key):
        x, y = sa.get(key), sb.get(key)
        return None if x is None or y is None else x - y

    # 1. the headline: service, as a rate
    g = gap("underserved_rate_pct")
    if g is not None and abs(g) >= MEANINGFUL["underserved_rate_pct"]:
        hi, lo = (a, b) if g > 0 else (b, a)
        lines.append(
            f"{hi} has the higher underserved rate: {stats[hi]['underserved_rate_pct']:g}% of "
            f"its measured settlements fall below 360p once shared by {CLASSROOM_USERS}, "
            f"against {stats[lo]['underserved_rate_pct']:g}% in {lo}. That is a rate, so it "
            f"does not simply reflect {hi} being larger.")
    elif g is not None:
        lines.append(
            f"{a} and {b} have comparable underserved rates "
            f"({sa['underserved_rate_pct']:g}% and {sb['underserved_rate_pct']:g}% of measured "
            f"settlements below 360p at {CLASSROOM_USERS} users), so service level alone does "
            f"not separate them.")

    # 2. people, which is the number that actually justifies spending
    pa, pb = sa["people_underserved"], sb["people_underserved"]
    if max(pa, pb) > 0 and abs(pa - pb) / max(pa, pb, 1) > 0.25:
        hi, lo = (a, b) if pa > pb else (b, a)
        lines.append(
            f"{hi} has more people in those areas, roughly {max(pa, pb):,} against "
            f"{min(pa, pb):,}. Both figures merge overlapping 2 km buffers, so they estimate "
            f"people near the settlements rather than a headcount.")

    # 3. evidence, which decides whether any of the above can be trusted
    g = gap("evidence_gap_pct")
    if g is not None and abs(g) >= MEANINGFUL["evidence_gap_pct"]:
        hi, lo = (a, b) if g > 0 else (b, a)
        lines.append(
            f"{hi} is the less measured of the two: {stats[hi]['evidence_gap_pct']:g}% of its "
            f"settlements have no usable measurement, against {stats[lo]['evidence_gap_pct']:g}% "
            f"in {lo}. Its service figures rest on a smaller sample and should be read as "
            f"weaker evidence, not as a better or worse result.")

    # 4. context, stated as association
    bits = []
    g = gap("remote_rate_pct")
    if g is not None and abs(g) >= MEANINGFUL["remote_rate_pct"]:
        hi = a if g > 0 else b
        bits.append(f"{hi} is the more remote, with {stats[hi]['remote_rate_pct']:g}% of "
                    f"settlements more than {REMOTE_KM:g} km from the nearest town")
    g = gap("terrain_shadow_pct")
    if g is not None and abs(g) >= MEANINGFUL["terrain_shadow_pct"]:
        hi = a if g > 0 else b
        bits.append(f"{hi} has more settlements sitting 150 m or more below their nearest "
                    f"town ({stats[hi]['terrain_shadow_pct']:g}%)")
    if bits:
        # str.capitalize() lowercases the rest of the string, which turned
        # "Ranau" into "ranau" halfway through the sentence.
        joined = ", and ".join(bits)
        lines.append(joined[:1].upper() + joined[1:] +
                     ". Remoteness and terrain are associated with lower measured speed in "
                     "this dataset; neither is shown to cause it.")

    # 5. what to do about it, the only actionable sentence, and it is hedged
    worst_gap = max(areas, key=lambda x: stats[x]["evidence_gap_pct"] or 0)
    worst_svc = max(areas, key=lambda x: stats[x]["underserved_rate_pct"] or 0)
    if worst_gap == worst_svc:
        lines.append(
            f"{worst_svc} carries both the weaker service rate and the thinner evidence, so it "
            f"warrants field measurement before any option is costed.")
    else:
        lines.append(
            f"On this data {worst_svc} screens as the higher service need and {worst_gap} as the "
            f"higher measurement need. They are different questions and can be funded separately.")
    return lines


def compare_areas(names, level: str = "district") -> dict:
    """Two or more districts or divisions, side by side on the same definitions."""
    level = _s(level).lower() or "district"
    col = "division" if level.startswith("div") else "district"
    if isinstance(names, str):
        names = [p for p in re.split(r"\s*(?:,|\band\b|\bvs\b|\bversus\b)\s*", names) if p.strip()]
    names = [_s(n) for n in (names or []) if _s(n)]
    if len(names) < 2:
        return {"rows": [], "ids": [], "flags": [],
                "note": "Give at least two districts or divisions to compare."}

    known = {d for d in DF[col] if d}
    resolved, missing = [], []
    for n in names[:CMP_MAX_AREAS]:
        hit = next((d for d in known if _key(d) == _key(n)), None)
        if hit and hit in resolved:
            continue                       # "Ranau vs Ranau" is not a comparison
        (resolved.append(hit) if hit else missing.append(n))
    if len(resolved) < 2:
        got = f"Only matched {_label(resolved[0])}. " if resolved else ""
        miss = f"No match for {', '.join(missing)}. " if missing else ""
        return {"rows": [], "ids": [], "flags": [],
                "note": (f"{miss}{got}Give at least two different {col}s to compare. Sabah has "
                         f"{len(known)}: {', '.join(sorted(_label(k) for k in known))}.")}

    # The facilities file carries a district but no division, so divisions are
    # rolled up through the district map rather than joined on a column that
    # does not exist.
    def facilities_in(area):
        if col == "district":
            return FAC[FAC["district"] == area]
        members = {d for d in DF[DF["division"] == area]["district"] if d}
        return FAC[FAC["district"].isin(members)]

    stats = {_label(r): _area_stats(DF[DF[col] == r], facilities_in(r)) for r in resolved}
    labels = list(stats)

    # Sabah-wide reference, and the percentile of each area among ALL areas at
    # this level, so two weak districts cannot look strong just by being next
    # to each other.
    everyone = {_label(d): _area_stats(DF[DF[col] == d], facilities_in(d)) for d in known}
    sabah = _area_stats(DF, FAC)

    indicators, rows = [], []
    for label, key, unit, worse_high, group in INDICATORS:
        vals = {l: stats[l].get(key) for l in labels}
        pool = sorted(v for v in (s.get(key) for s in everyone.values()) if v is not None)
        ranks = {}
        for l in labels:
            v = vals[l]
            if v is None or not pool or worse_high is None:
                ranks[l] = None
            else:
                # percentile of BADNESS, so 90 always means "worse than 90% of
                # areas" whichever direction the raw number runs.
                below = sum(1 for p in pool if p < v)
                pc = 100.0 * below / len(pool)
                ranks[l] = round(pc if worse_high else 100 - pc)
        indicators.append({"group": group, "indicator": label, "unit": unit, "key": key,
                           "worse_high": worse_high, "values": vals,
                           "percentile_worse_than": ranks, "sabah": sabah.get(key)})
        # A flat mirror of the same numbers, because the chat panel renders
        # `rows` as a table and a nested dict would arrive as [object Object].
        flat = {"indicator": f"{label}{f' ({unit})' if unit else ''}"}
        flat.update({l: vals[l] for l in labels})
        flat["Sabah"] = sabah.get(key)
        rows.append(flat)

    ids = list(DF[DF[col].isin(resolved) & DF["dipi"].notna()]["settlement_id"])
    note = [f"{len(labels)} {col}s compared on identical definitions, from the same Ookla "
            f"2025 Q1–Q4 aggregates and the same DIPI weights"]
    note.append("every service figure uses measured settlements only, a settlement with no "
                "measurement is counted in the evidence gap and never counted as slow")
    note.append("population merges overlapping 2 km buffers, so it estimates people near the "
                "settlements and is not a census headcount")
    if missing:
        note.append(f"no match for {', '.join(missing)}")
    note.append("not available in this dataset: "
                + "; ".join(f"{n.lower()} ({why})" for n, why in NOT_AVAILABLE))
    return {"rows": rows, "ids": ids, "indicators": indicators,
            "areas": labels, "level": col, "stats": stats, "sabah": sabah,
            "summary": _summarise(labels, stats, col),
            "unavailable": [{"indicator": n, "reason": w} for n, w in NOT_AVAILABLE],
            "flags": ["rates_not_totals", "osm_incomplete"],
            "note": ". ".join(note) + "."}


def find_failing_schools(district: str = "", division: str = "", users: int = CLASSROOM_USERS,
                        tier: str = "360p", top_k: int = 25) -> dict:
    """Settlements with a school nearby whose measured link cannot carry a class.

    The same arithmetic the Experience Simulator and the rankings preset run,
    measured download divided by `users` against the tier's sustained bitrate,
    so the three can never disagree.

    Unmeasured settlements are EXCLUDED rather than counted as failing. No
    measurement is not the same as a failing measurement, and a settlement in
    the evidence gap belongs to plan_survey, not here.
    """
    district, division = _s(district), _s(division)
    tier = _s(tier).lower() or "360p"
    users = max(1, _i(users, CLASSROOM_USERS))
    top_k = max(1, _i(top_k, 25))
    if tier not in VIDEO_TIERS:
        return {"rows": [], "ids": [], "flags": [],
                "note": f"Unknown tier '{tier}'. Use {', '.join(VIDEO_TIERS)}."}
    need = VIDEO_TIERS[tier]

    d = DF[DF["n_schools_3km"] >= 1]
    d = d[d["dl_mbps"].notna() & (d["evidence_tier"] != "insufficient")]
    scope = "Sabah"
    if district:
        d = d[d["district"].map(_key) == _key(district)]
        scope = _label(district)
    elif division:
        d = d[d["division"].map(_key) == _key(division)]
        scope = _label(division)

    per = d["dl_mbps"] / users
    fail = d[per < need].copy()
    fail["_per"] = fail["dl_mbps"] / users
    fail = fail.sort_values("_per")

    rows = [{"name": display_name(r), "district": _label(r["district"]),
             "dl_mbps": _num(r["dl_mbps"]), "per_user_mbps": round(float(r["_per"]), 2),
             "schools_3km": int(r["n_schools_3km"]),
             "clinics_3km": int(r["n_clinics_3km"]),
             "pop_2km": _num(r["pop_2km"]),
             "dipi": _num(r["dipi"]), "rank": None if pd.isna(r["rank"]) else int(r["rank"]),
             "evidence": r["evidence_tier"]}
            for _, r in fail.head(top_k).iterrows()]

    low_ev = int((fail["evidence_tier"] == "low_evidence").sum())
    note = [f"{len(fail)} settlement(s) in {scope} have at least one school within "
            f"{FAC_NEAR_KM:.0f} km and a measured link that falls below {tier} "
            f"({need} Mbps) once {users} people share it"]
    note.append(f"a school within {FAC_NEAR_KM:.0f} km is a buffer count from OpenStreetMap, "
                f"not a catchment, the school may serve a different village")
    note.append("settlements with no usable measurement are excluded, because no measurement "
                "is not the same as a failing one")
    if low_ev:
        note.append(f"{low_ev} of them are low_evidence. {LOW_EV_WARNING}")
    return {"rows": rows, "ids": list(fail.head(top_k)["settlement_id"]),
            "total_failing": len(fail), "considered": len(d), "scope": scope,
            "tier": tier, "needs_mbps": need, "users": users,
            "low_evidence_rows": low_ev,
            "flags": ["assumption_equal_sharing", "osm_incomplete"],
            "assumption": "Simplified equal-sharing model, an assumption, not a measurement.",
            "note": ". ".join(note) + "."}


# ── deployment bundles ───────────────────────────────────────────────────────
# The same arithmetic the panel does, in the same order, so the copilot and the
# sidebar can never quote different figures for the same budget. Any change here
# has to be mirrored in renderSequence() in the dashboard, and the parity test
# in test_agent.py is what catches it when it is not.
SEQ_SCEN = {
    "need":     ("median DIPI of the bundle's members, highest first, cost ignored",
                 lambda c: -(c["median_dipi"] or 0)),
    "balanced": ("median DIPI divided by cost in RM millions",
                 lambda c: -((c["median_dipi"] or 0) / max(c["cost_rm"] / 1e6, 0.01))),
    "reach":    ("settlements plus schools plus clinics, divided by cost in RM millions",
                 lambda c: -((c["settlements"] + c["schools"] + c["clinics"])
                             / max(c["cost_rm"] / 1e6, 0.01))),
}


def _fibre_cost(row, costs) -> float:
    """What one fibre settlement adds: the SHORTER of its shared spur and its own
    run in from the town. Sharing is not always cheaper."""
    km = float(row["backhaul_km"]) if pd.notna(row["backhaul_km"]) else 10.0
    km = min(km, CLUSTERS.get(row["settlement_id"], {}).get("trunk_km", km))
    return costs["fibre_per_km"] * max(1.0, km)


def _bundles(cost_scenario: str = "base") -> list:
    """One row per fibre bundle. Facility counts are DISTINCT ids inside the
    bundle, never a sum of per-settlement counts, because one school sits within
    3 km of several settlements at once."""
    if not CLUSTERS:
        return []
    c = COSTS.get(cost_scenario, COSTS["base"])
    d = DF.copy()
    d["_cl"] = d["settlement_id"].map(lambda s: CLUSTERS.get(s, {}).get("cl", -1))
    out = []
    R = 6371.0
    fla = np.radians(FAC["lat"].to_numpy())[:, None]
    flo = np.radians(FAC["lon"].to_numpy())[:, None]
    for cl, g in d[d["_cl"] >= 0].groupby("_cl"):
        # Every facility against every member at once, then the nearest member.
        # A facility counts once for the bundle however many members can see it.
        sla = np.radians(g["lat"].to_numpy())[None, :]
        slo = np.radians(g["lon"].to_numpy())[None, :]
        h = (np.sin((sla - fla) / 2) ** 2
             + np.cos(fla) * np.cos(sla) * np.sin((slo - flo) / 2) ** 2)
        near = FAC[(2 * R * np.arcsin(np.sqrt(np.clip(h, 0, 1)))).min(axis=1) <= FAC_NEAR_KM]
        dip = g["dipi"].dropna()
        out.append({
            "bundle": int(cl),
            "district": _label(g["district"].mode().iloc[0]) if len(g["district"].mode()) else "",
            "settlements": int(len(g)),
            "median_dipi": _half_up(float(dip.median()), 1) if len(dip) else None,
            "schools": int((near["kind"] == "school").sum()),
            "clinics": int((near["kind"] == "health").sum()),
            "trench_km": _half_up(sum(
                max(1.0, min(float(r["backhaul_km"]) if pd.notna(r["backhaul_km"]) else 10.0,
                             CLUSTERS.get(r["settlement_id"], {}).get(
                                 "trunk_km", float("inf"))))
                for _, r in g.iterrows()), 1),
            "cost_rm": int(round(sum(_fibre_cost(r, c) for _, r in g.iterrows()))),
            "modelled_members": int((g.get("speed_source", pd.Series(dtype=object))
                                     == "modelled estimate").sum()) if HAS_MODEL else 0,
            "names": [display_name(r) for _, r in g.head(6).iterrows()],
            "ids": g["settlement_id"].tolist(),
            "fac_ids": set(near["facility_id"]),
        })
    return out


def rank_bundles(budget_rm: float = 50_000_000, scenario: str = "balanced",
                 cost_scenario: str = "base", top_k: int = 25) -> dict:
    """Which fibre bundles a budget funds, in the chosen order."""
    if not CLUSTERS:
        return {"rows": [], "ids": [], "note": "Build clusters have not been generated yet."}
    scenario = _s(scenario).lower() or "balanced"
    if scenario not in SEQ_SCEN:
        scenario = "balanced"
    why, key = SEQ_SCEN[scenario]
    bs = sorted(_bundles(cost_scenario), key=key)

    spent, funded = 0.0, []
    for b in bs:                      # skip what does not fit, keep going
        if spent + b["cost_rm"] > budget_rm:
            continue
        spent += b["cost_rm"]; funded.append(b)

    # The UNION of facility ids across funded bundles. Adding each bundle's own
    # deduplicated count would still double-count a school two bundles can reach.
    fs = set()
    for b in funded:
        fs |= b["fac_ids"]
    rows = [{k: v for k, v in b.items() if k not in ("ids", "names", "fac_ids")}
            for b in bs[:top_k]]
    for r, b in zip(rows, bs[:top_k]):
        r["funded"] = b in funded
    return {
        "rows": rows,
        "ids": [i for b in funded for i in b["ids"]],
        "bundles_total": len(bs),
        "bundles_funded": len(funded),
        "settlements_funded": sum(b["settlements"] for b in funded),
        "schools_funded": int(FAC[FAC["facility_id"].isin(fs)]["kind"].eq("school").sum()),
        "clinics_funded": int(FAC[FAC["facility_id"].isin(fs)]["kind"].eq("health").sum()),
        "spent_rm": int(round(spent)),
        "budget_rm": int(budget_rm),
        "cost_all_rm": int(round(sum(b["cost_rm"] for b in bs))),
        "scenario": scenario,
        "ranked_by": why,
        "flags": ["illustrative_cost", "bundle_proxy"],
        "label": "Illustrative planning costs, not procurement estimates.",
        "note": ("Bundles are fibre-recommended settlements grouped by position alone, so "
                 "they are screened as a potential shared deployment, not designed as one. "
                 "Costs use benchmark rates over straight-line distances and each settlement "
                 "is charged the shorter of its shared spur or its own run from town, so a "
                 "real build costs more. Bundles are taken in the ranked order while they "
                 "fit and skipped when they do not, which is a greedy heuristic and not a "
                 "proven optimum."),
    }


def explain_bundle(name_or_id: str) -> dict:
    """Which bundle a settlement belongs to, and what else is in it."""
    if not CLUSTERS:
        return {"rows": [], "ids": [], "note": "Build clusters have not been generated yet."}
    row, _ = find(name_or_id)
    if row is None:
        return {"rows": [], "ids": [], "note": f"No settlement matches '{name_or_id}'."}
    cl = CLUSTERS.get(row["settlement_id"], {}).get("cl", -1)
    if cl < 0:
        return {"rows": [], "ids": [row["settlement_id"]],
                "flags": ["bundle_proxy"],
                "note": (f"{display_name(row)} is not in a bundle. Either the recommender "
                         "does not send it to fibre, or it sits too far from any neighbour "
                         "to screen as a shared build under the proximity rule, so it would "
                         "be costed on its own.")}
    b = next(x for x in _bundles() if x["bundle"] == cl)
    return {
        "rows": [{k: v for k, v in b.items() if k not in ("ids", "fac_ids")}],
        "ids": b["ids"],
        "flags": ["illustrative_cost", "bundle_proxy"],
        "label": "Illustrative planning costs, not procurement estimates.",
        "note": (f"{display_name(row)} is in the {b['district']} bundle with "
                 f"{b['settlements'] - 1} others. Grouped on position alone, so this is a "
                 "screening proxy for a shared build rather than an engineering design."),
    }


TOOLS = {"rank_settlements": rank_settlements, "explain_priority": explain_priority,
         "compare_areas": compare_areas,
         "compare_settlements": compare_settlements, "simulate_experience": simulate_experience,
         "predict_coverage": predict_coverage, "recommend_intervention": recommend_intervention,
         "optimise_budget": optimise_budget, "plan_survey": plan_survey,
         "generate_validation_report": generate_validation_report,
         "district_summary": district_summary, "list_facilities": list_facilities,
         "find_failing_schools": find_failing_schools,
         "rank_bundles": rank_bundles, "explain_bundle": explain_bundle}


if __name__ == "__main__":
    print(f"source: {DF.attrs.get('source_file')}   rows: {len(DF)}   model columns: {HAS_MODEL}")
    checks = [
        ("rank_settlements", rank_settlements(district="KotaMarudu", top_k=3)),
        ("explain_priority", explain_priority("Kampung Tangkol")),
        ("compare_settlements", compare_settlements("Kampung Tangkol", "Talas")),
        ("simulate_experience", simulate_experience("Talas", "720p", 30)),
        ("predict_coverage", predict_coverage("Talas")),
        ("recommend_intervention", recommend_intervention("Talas")),
        ("optimise_budget", optimise_budget(50_000_000, "KotaMarudu")),
        ("plan_survey", plan_survey("Kudat", 3)),
        ("generate_validation_report", generate_validation_report("KotaMarudu", 3)),
        ("district_summary", district_summary(sort_by="facilities", top_k=3)),
        ("list_facilities", list_facilities("Kota Kinabalu", "health", 5)),
        # the shapes an LLM actually sends when it ignores its own schema
        ("rank_settlements[list arg]", rank_settlements(district=["Kota Marudu"], top_k="3")),
        ("district_summary[dict arg]", district_summary(district={"name": "Sandakan"})),
    ]
    for name, out in checks:
        head = out["rows"][0] if out["rows"] else out.get("note", "")
        print(f"\n[{name}] ids={len(out['ids'])}")
        print(f"   {head}")

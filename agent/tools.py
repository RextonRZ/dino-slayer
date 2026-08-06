"""The grounded tool layer. Python computes; the agent only narrates.

Every number Tanya Dino says must come out of a function in this file. Nothing
here imports an LLM, and nothing here is prompted — these are plain pandas
functions over the project's own parquet, testable on their own:

    python -m agent.tools        # runs a self-test over real rows

Thresholds and weights are copied from the dashboard deliberately, so the agent
and the map can never disagree about a number.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SETTLEMENTS = ROOT / "dataset" / "settlements"

DISCLAIMER = "Screening for further assessment — not a coverage determination."
LOW_EV_WARNING = ("Some rows rest on limited tests — prioritise field validation.")

# Same numbers as the dashboard simulator.
VIDEO_TIERS = {"360p": 0.7, "480p": 1.1, "720p": 2.5, "1080p": 5.0, "4k": 20.0}
WEIGHTS = {"p_connectivity": 0.40, "p_population": 0.25,
           "p_institutions": 0.15, "p_equity": 0.20}
# Illustrative rules. They ship labelled as such until the ITU and MCMC
# criteria they stand in for have been sourced and verified.
RULE_PARAMS = {"fibre_max_km": 15, "fibre_min_pop": 3000,
               "fwa_max_km": 40, "fwa_min_pop": 500, "sat_min_km": 40}
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
    'lower'". A tool must never fail on the SHAPE of its arguments — only on
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
    # makes a connectivity pillar of 0.2 legible — that is 0.2 NEED, because the
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
                "note": (f"Evidence needed — {display_name(row)} has no speed measurement, "
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
            "assumption": "Simplified equal-sharing model — an assumption, not a measurement.",
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
            "label": "Illustrative decision criteria pending source verification — prototype only.",
            "note": "Rules-based decision support — not a trained model."}


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
        cost = (c["fibre_per_km"] * 10 if opt == "Fibre" else c["fwa"] if "wireless" in opt
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
            "label": "Illustrative planning assumptions — not procurement estimates.",
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
    md = [f"# Field validation shortlist — {where}", "",
          f"{len(top['rows'])} highest-priority settlements by DIPI, and "
          f"{len(survey['rows'])} with no usable measurement.", "", "## Priority shortlist", ""]
    for r in top["rows"]:
        md.append(f"- **#{r['rank']} {r['name']}** ({r['district']}) — DIPI {r['dipi']}, "
                  f"{'no speed measurement' if r['dl_mbps'] is None else str(r['dl_mbps']) + ' Mbps'}, "
                  f"evidence: {r['evidence']}")
    md += ["", "## Measure these first (no usable data)", ""]
    for r in survey["rows"]:
        md.append(f"- **{r['name']}** ({r['district']}) — stakes {r['stakes']}, "
                  f"{r['pop_2km']} people within 2 km, {r['schools_3km']} school(s) within 3 km")
    md += ["", "## Recommended measurements", "",
           "- Speed tests at peak hours, multiple operators", "- School and clinic connectivity check",
           "- Short resident survey on affordability and usage", "",
           f"_{DISCLAIMER}_", "",
           "Generated from Dino Slayer DIPI, weights 40/25/15/20, Ookla 2025 Q1–Q4."]
    return {"rows": top["rows"], "ids": top["ids"] + survey["ids"],
            "markdown": "\n".join(md), "note": ""}


TOOLS = {"rank_settlements": rank_settlements, "explain_priority": explain_priority,
         "compare_settlements": compare_settlements, "simulate_experience": simulate_experience,
         "predict_coverage": predict_coverage, "recommend_intervention": recommend_intervention,
         "optimise_budget": optimise_budget, "plan_survey": plan_survey,
         "generate_validation_report": generate_validation_report,
         "district_summary": district_summary, "list_facilities": list_facilities}


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

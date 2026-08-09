"""How many masts would serve the 449 tower settlements, at three assumed radii.

The bundles panel prices a tower at one mast per settlement. One mast serves
more than one village, so that overstates the cost. This is the sensitivity
run that says by how much, and how hard the answer leans on a radius nobody
has published for rural Sabah.

What this is NOT: predicted radio coverage. A settlement is "covered" here if
it sits within a straight-line radius of a mast, which is geometry, not
propagation. Terrain, mast height and line of sight all decide the real answer
and none of them are in this calculation. Proper propagation needs terrain and
ground-cover profiles (ITU-R P.1812). Call the output a candidate service area.

Candidate mast sites are existing settlement coordinates. That is a
settlement-centre proxy, not a confirmed buildable site: nobody has checked
land, access or planning at any of them, and power only as far as a nightlight
screen goes. It also means full coverage is
always reachable (a settlement always covers itself), so "uncovered" is a check
on the arithmetic rather than a finding.

Implementation:
tower_pairs.csv (10,070 rows) takes the 449 settlements the recommender sends to a tower, 
and lists every village-to-village pair within 3, 5 and 10 km. Pure distance at this point, no terrain.

Run:  python dataset/tower_scenarios.py
"""
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RADII_KM = [3, 5, 10]
R_EARTH = 6371.0088

# From dataset/web/sources.json. The recommender's own rules, restated here so
# this script picks exactly the same 449 the dashboard does.
FIBRE_MAX_KM, FIBRE_MIN_POP = 15, 3000
FWA_MAX_KM, FWA_MIN_POP = 40, 500
TERRAIN_DROP_M = -150  # a settlement this far below its anchor town

# COST_DEMO_PLACEHOLDER in dashboard/index.html, fwa_per_site.
COST_PER_SITE = {"low": 350_000, "base": 520_000, "high": 780_000}


def haversine_matrix(lat, lon):
    """Full pairwise distance in km. 449 x 449 is small enough to do at once."""
    la, lo = np.radians(lat), np.radians(lon)
    dla = la[None, :] - la[:, None]
    dlo = lo[None, :] - lo[:, None]
    a = np.sin(dla / 2) ** 2 + np.cos(la)[:, None] * np.cos(la)[None, :] * np.sin(dlo / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


def greedy_cover(within):
    """Greedy set-cover heuristic. Take the site that adds the most uncovered
    settlements, repeat until every settlement is assigned.

    Set cover, not maximum coverage. Maximum coverage fixes a budget of k sites
    and maximises what they reach. This runs until all 449 are covered and the
    OUTPUT is how many sites that took, which is minimum-cardinality set cover,
    solved greedily.

    NOT GUARANTEED MINIMAL. Set cover is NP-hard and greedy is the standard
    ln(n)-approximation, so a smaller mast count may exist. Every figure here is
    an upper bound and a screening estimate, never a minimum.
    """
    n = within.shape[0]
    uncovered = np.ones(n, dtype=bool)
    chosen = []
    while uncovered.any():
        gain = (within & uncovered).sum(axis=1)
        best = int(gain.argmax())
        if gain[best] == 0:  # cannot happen: a site always covers itself
            break
        chosen.append(best)
        uncovered &= ~within[best]
    return chosen


def main():
    t = pd.read_csv(ROOT / "dataset/ml/training_table.csv")
    feats = json.load(open(ROOT / "dataset/web/dipi.geojson", encoding="utf8"))["features"]
    dipi = {f["properties"]["settlement_id"]: f["properties"].get("dipi") for f in feats}
    t["dipi"] = t.settlement_id.map(dipi)

    # The recommender's cascade, tower branch only.
    is_fibre = (t.backhaul_km <= FIBRE_MAX_KM) & (t.pop_2km >= FIBRE_MIN_POP)
    is_tower = ~is_fibre & (t.backhaul_km <= FWA_MAX_KM) & (t.pop_2km >= FWA_MIN_POP)
    tw = t[is_tower].reset_index(drop=True)
    print(f"tower settlements: {len(tw)}   (dashboard reports 449)")
    assert len(tw) == 449, f"recommender drift: got {len(tw)}, expected 449"

    scored = t.dropna(subset=["dipi"])
    top50 = set(scored.nlargest(50, "dipi").settlement_id)
    top50_in_tower = top50 & set(tw.settlement_id)
    print(f"top 50 by DIPI that are tower settlements: {len(top50_in_tower)}")

    shadowed = tw.elev_drop_m.notna() & (tw.elev_drop_m <= TERRAIN_DROP_M)
    print(f"terrain-shadowed among them: {int(shadowed.sum())} "
          f"({shadowed.mean() * 100:.0f}%)\n")

    D = haversine_matrix(tw.lat.values, tw.lon.values)
    one_per_settlement = len(tw) * COST_PER_SITE["base"]

    rows = []
    for r in RADII_KM:
        within = D <= r
        chosen = greedy_cover(within)
        covered = within[chosen].any(axis=0)

        # Which settlements does the WORST-served covered site rely on? The
        # distance from each settlement to the mast that covers it is the
        # number a field team would have to defend.
        dist_to_mast = D[chosen].min(axis=0)
        top50_covered = sum(
            1 for sid in top50_in_tower
            if covered[tw.index[tw.settlement_id == sid][0]]
        )
        sh_sites = int(shadowed.values[chosen].sum())

        rows.append({
            "radius_km": r,
            "masts": len(chosen),
            "covered": int(covered.sum()),
            "uncovered": int((~covered).sum()),
            "top50_dipi_covered": f"{top50_covered}/{len(top50_in_tower)}",
            "mean_km_to_mast": round(float(dist_to_mast.mean()), 2),
            "max_km_to_mast": round(float(dist_to_mast.max()), 2),
            "shadowed_sites": sh_sites,
            **{f"rm_{k}": len(chosen) * v for k, v in COST_PER_SITE.items()},
        })

    # EVERY in-radius path, not just the ones this distance-only run happened to
    # pick. Once the terrain screen fails a path, the cover has to be rebuilt
    # from whatever is still feasible, and a mast that was never screened cannot
    # be chosen. Exporting only the assigned paths would quietly restrict the
    # second run to the first run's answer.
    #
    # Self-pairs are dropped and are feasible by definition: a mast standing in
    # the village it serves has nothing to see over.
    pairs = []
    for r in RADII_KM:
        within = D <= r
        chosen = set(greedy_cover(within))
        for m, s in zip(*np.where(np.triu(within, k=1) | np.tril(within, k=-1))):
            pairs.append({
                "radius_km": r,
                "mast_id": tw.settlement_id[m], "mast_lat": tw.lat[m], "mast_lon": tw.lon[m],
                "s_id": tw.settlement_id[s], "s_lat": tw.lat[s], "s_lon": tw.lon[s],
                "dist_km": round(float(D[m, s]), 3),
                "chosen_by_distance": int(m in chosen),
            })
    pp = pd.DataFrame(pairs)
    pp.to_csv(ROOT / "dataset/ml/tower_pairs.csv", index=False)
    print(f"\n{len(pp):,} candidate paths for the terrain screen "
          f"({', '.join(f'{r} km: {int((pp.radius_km == r).sum()):,}' for r in RADII_KM)})")
    print("  every in-radius pair, so the cover can be rebuilt from what survives")

    df = pd.DataFrame(rows)
    money = lambda v: f"RM {v / 1e6:.1f}m"

    print("CANDIDATE SERVICE AREAS, distance only. Not predicted coverage.\n")
    print(f"{'radius':>7} {'masts':>6} {'covered':>8} {'unc':>4} {'top50':>7} "
          f"{'mean km':>8} {'max km':>7} {'shadowed':>9} "
          f"{'low':>9} {'base':>9} {'high':>9}")
    for _, x in df.iterrows():
        print(f"{x.radius_km:>5} km {x.masts:>6} {x.covered:>8} {x.uncovered:>4} "
              f"{x.top50_dipi_covered:>7} {x.mean_km_to_mast:>8} {x.max_km_to_mast:>7} "
              f"{x.shadowed_sites:>9} "
              f"{money(x.rm_low):>9} {money(x.rm_base):>9} {money(x.rm_high):>9}")

    print(f"\none mast per settlement, base case: {money(one_per_settlement)} "
          f"({len(tw)} masts)")
    lo, hi = df.rm_base.max(), df.rm_base.min()
    print(f"saving against that, base case:     {money(one_per_settlement - lo)} "
          f"at 3 km to {money(one_per_settlement - hi)} at 10 km")
    print(f"the radius alone moves the answer by {money(lo - hi)}, which is why "
          f"this ships as a range")

    out = ROOT / "dataset/ml/tower_scenarios.json"
    out.write_text(json.dumps({
        "_what": "Distance-based candidate service areas for the 449 tower "
                 "settlements. NOT predicted radio coverage: no terrain, no "
                 "mast height, no line of sight. ITU-R P.1812 is the real "
                 "calculation and it needs profiles we do not have.",
        "_method": "Candidate sites are the settlement coordinates themselves. "
                   "A greedy set-cover heuristic, which is the standard ln(n) "
                   "approximation and not a proven minimum.",
        "n_tower_settlements": len(tw),
        "top50_dipi_in_tower": len(top50_in_tower),
        "terrain_shadowed": int(shadowed.sum()),
        "cost_per_site_rm": COST_PER_SITE,
        "one_per_settlement_base_rm": one_per_settlement,
        "scenarios": rows,
    }, indent=2), encoding="utf8")
    print(f"\nsaved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Re-run the mast selection on paths that survive a terrain screen.

tower_scenarios.py answers "how many masts if every path within the radius
works". This answers "how many if only the paths that clear the terrain do",
using the line-of-sight and Fresnel screen returned in tower_pairs_los.csv.

The difference between the two is the point of the exercise. Distance-only
assumed 100% of in-radius paths were usable. At 10 km, 19% are.

WHAT THE SCREEN IS. For each of the 10,070 candidate paths, a terrain profile
is sampled from the SRTM raster and checked twice:

  los      the straight ray from a 30 m mast to a 10 m receiver clears the
           ground everywhere along the path, with a 4/3 earth radius applied
           so refraction is accounted for
  fresnel  the stricter test: 60% of the first Fresnel zone is also clear,
           which is the standard planning rule because a ray that merely
           grazes terrain still loses signal to diffraction

fresnel implies los by construction, and the file confirms it: no path passes
the stricter test while failing the looser one.

WHAT IT STILL IS NOT. A terrain screen is not a propagation model. It says a
path is geometrically blocked; it does not say a clear path delivers a usable
signal. There is no ground cover, no clutter loss, no interference and no
capacity here. ITU-R P.1812 is the real calculation.

SRTM is C-band radar, so over dense forest the returned surface sits partway
up the canopy rather than at ground level. That cuts both ways: this screen
over-blocks cleared land whose true ground is lower than the reading, and
under-blocks tall forest a real signal would have to pass through. It narrows
the radius uncertainty. It does not close it.

Run:  python dataset/tower_los.py
"""
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RADII_KM = [3, 5, 10]
R_EARTH = 6371.0088

FIBRE_MAX_KM, FIBRE_MIN_POP = 15, 3000
FWA_MAX_KM, FWA_MIN_POP = 40, 500
TERRAIN_DROP_M = -150

COST_PER_SITE = {"low": 350_000, "base": 520_000, "high": 780_000}

# The screen's own assumptions, carried here so the output can state them.
# H_MAST is sourced. H_RECV is not, and it moves the answer.
H_MAST_M, H_RECV_M = 30, 10
BAND_MHZ = 700


def haversine_matrix(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    dla = la[None, :] - la[:, None]
    dlo = lo[None, :] - lo[:, None]
    a = np.sin(dla / 2) ** 2 + np.cos(la)[:, None] * np.cos(la)[None, :] * np.sin(dlo / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


def greedy_cover(within):
    """Greedy set-cover heuristic, unchanged from tower_scenarios.py so the two
    runs differ only in which paths they are allowed to use.

    Runs until every settlement is assigned, so the output is a minimum-
    cardinality cover solved greedily, and NOT GUARANTEED MINIMAL: a smaller
    mast count may exist. Read every figure as an upper bound.
    """
    n = within.shape[0]
    uncovered = np.ones(n, dtype=bool)
    chosen = []
    while uncovered.any():
        gain = (within & uncovered).sum(axis=1)
        best = int(gain.argmax())
        if gain[best] == 0:
            break
        chosen.append(best)
        uncovered &= ~within[best]
    return chosen


def main():
    t = pd.read_csv(ROOT / "dataset/ml/training_table.csv")
    is_fibre = (t.backhaul_km <= FIBRE_MAX_KM) & (t.pop_2km >= FIBRE_MIN_POP)
    is_tower = ~is_fibre & (t.backhaul_km <= FWA_MAX_KM) & (t.pop_2km >= FWA_MIN_POP)
    tw = t[is_tower].reset_index(drop=True)
    assert len(tw) == 449, f"recommender drift: got {len(tw)}, expected 449"

    idx = {sid: i for i, sid in enumerate(tw.settlement_id)}
    D = haversine_matrix(tw.lat.values, tw.lon.values)
    shadowed = (tw.elev_drop_m.notna() & (tw.elev_drop_m <= TERRAIN_DROP_M)).values

    los = pd.read_csv(ROOT / "dataset/ml/tower_pairs_los.csv")
    unknown = (set(los.mast_id) | set(los.s_id)) - set(idx)
    assert not unknown, f"screen holds {len(unknown)} settlements not in the tower set"
    assert los.voids.sum() == 0, f"{int(los.voids.sum())} paths hit a DEM void"
    assert bool((los.fresnel <= los.los).all()), "a path passed Fresnel but failed LoS"

    print(f"tower settlements   {len(tw)}")
    print(f"screened paths      {len(los):,}  "
          f"({los.mast_id.nunique()} settlements appear in at least one pair)")
    print(f"mast {H_MAST_M} m, receiver {H_RECV_M} m, {BAND_MHZ} MHz, "
          f"4/3 earth, 60% Fresnel\n")

    print("PATHS SURVIVING THE SCREEN")
    print(f"{'radius':>7} {'paths':>7} {'LoS':>15} {'Fresnel':>15}")
    for r in RADII_KM:
        g = los[los.radius_km == r]
        print(f"{r:>5} km {len(g):>7} "
              f"{g.los.sum():>7} {g.los.mean() * 100:>6.1f}% "
              f"{g.fresnel.sum():>7} {g.fresnel.mean() * 100:>6.1f}%")

    q = los.min_clear_m.quantile([.25, .5, .75])
    print(f"\nmin_clear_m quartiles  {q.iloc[0]:.1f} / {q.iloc[1]:.1f} / {q.iloc[2]:.1f} m")
    print(f"paths blocked outright  {(los.min_clear_m < 0).mean() * 100:.1f}% "
          f"(median path is blocked by {abs(q.iloc[1]):.0f} m)\n")

    rows = []
    isolated = {}
    web = {}          # radius -> {sites, links} for the map, screened case only
    for r in RADII_KM:
        g = los[los.radius_km == r]
        out = {"radius_km": r}

        for name in ("distance", "los", "fresnel"):
            # A mast always covers the settlement it stands in. The screen holds
            # no self-pairs because a mast in the village has nothing to see
            # over, so the diagonal is set here rather than read from the file.
            # It also guarantees the cover always completes: the worst case is
            # one mast per settlement, which is the figure this run exists to
            # beat.
            A = np.eye(len(tw), dtype=bool)
            if name == "distance":
                A |= D <= r
            else:
                ok = g[g[name].astype(bool)]
                A[[idx[m] for m in ok.mast_id], [idx[s] for s in ok.s_id]] = True

            chosen = greedy_cover(A)
            covered = A[chosen].any(axis=0)
            assert covered.all(), "a settlement ended up uncovered, which cannot happen"

            # Distance to the mast actually serving each settlement, over
            # feasible paths only. Under the screen this is not D.min(): the
            # nearest mast may be the one the terrain blocks.
            served = np.where(A[chosen], D[chosen], np.inf).min(axis=0)

            # Settlements no other site can reach, so they force a mast of
            # their own.
            #
            # This is a COLUMN sum, not a row sum, and the two differ. A is
            # A[mast][settlement] and the screen is NOT symmetric: the mast is
            # 30 m and the receiver is 10 m, so the ray from a mast at A to a
            # receiver at B is a different profile from the reverse, and 100 of
            # the 712 clear paths at 3 km work one way only. The row sum asks
            # "does this site serve anyone but itself", which is a question
            # about candidate masts. The column sum asks "can anything but
            # itself reach this settlement", which is the one that costs money.
            only_self = A.sum(axis=0) == 1
            isolated[(r, name)] = only_self

            if name == "fresnel":
                # What the map draws. Each settlement is joined to the chosen
                # mast that actually serves it, which is the nearest one it has
                # a CLEAR path to and not simply the nearest one: 100 of the
                # 712 clear paths at 3 km run one way only, and the closest
                # mast is often the one the terrain blocks.
                #
                # Lines, never circles. A radius drawn round a mast would read
                # as predicted coverage, and each of these lines is instead a
                # specific path that passed the screen.
                serve_idx = np.where(A[chosen], D[chosen], np.inf).argmin(axis=0)
                rnd = lambda v: round(float(v), 5)
                web[r] = {
                    "sites": [[tw.settlement_id[c], rnd(tw.lon[c]), rnd(tw.lat[c]),
                               int(A[c].sum())] for c in chosen],
                    # [index into sites, settlement lon, settlement lat]. A mast
                    # serving itself is not drawn: a line of zero length is not
                    # a link, it is a dot already on the map.
                    "links": [[int(serve_idx[s]), rnd(tw.lon[s]), rnd(tw.lat[s])]
                              for s in range(len(tw)) if chosen[serve_idx[s]] != s],
                }

            out[name] = {
                "masts": len(chosen),
                "only_self_reachable": int(only_self.sum()),
                "mean_km_to_mast": round(float(served.mean()), 2),
                "max_km_to_mast": round(float(served.max()), 2),
                "shadowed_sites": int(shadowed[chosen].sum()),
                **{f"rm_{k}": len(chosen) * v for k, v in COST_PER_SITE.items()},
            }
        rows.append(out)

    money = lambda v: f"RM {v / 1e6:.1f}m"
    one_per = len(tw) * COST_PER_SITE["base"]

    print("MASTS NEEDED, distance-only against the same run on screened paths\n")
    print(f"{'radius':>7} {'distance':>9} {'LoS':>9} {'Fresnel':>9}   "
          f"{'base, distance':>15} {'base, Fresnel':>14} {'extra':>10}")
    for x in rows:
        d, f = x["distance"], x["fresnel"]
        print(f"{x['radius_km']:>5} km {d['masts']:>9} {x['los']['masts']:>9} "
              f"{f['masts']:>9}   {money(d['rm_base']):>15} {money(f['rm_base']):>14} "
              f"{money(f['rm_base'] - d['rm_base']):>10}")

    print(f"\n{'radius':>7} {'mean km to mast':>17} {'max km':>16} {'reachable only by itself':>26}")
    for x in rows:
        d, f = x["distance"], x["fresnel"]
        print(f"{x['radius_km']:>5} km "
              f"{d['mean_km_to_mast']:>7} -> {f['mean_km_to_mast']:<6} "
              f"{d['max_km_to_mast']:>7} -> {f['max_km_to_mast']:<6} "
              f"{d['only_self_reachable']:>13} -> {f['only_self_reachable']:<8}")

    # One row per tower settlement, flagging at which radii nothing but a mast
    # in the village itself can reach it. Exported so it can be joined against
    # anything else that is per-settlement: the open question it exists for is
    # which of these ALSO have no grid power, since a site needing its own mast
    # and its own power is a different cost class from one needing only a mast.
    iso = pd.DataFrame({
        "settlement_id": tw.settlement_id, "name": tw.name,
        "district": tw.district, "lat": tw.lat, "lon": tw.lon,
        "pop_2km": tw.pop_2km, "backhaul_km": tw.backhaul_km,
        "elev_drop_m": tw.elev_drop_m,
        **{f"only_self_{r}km": isolated[(r, "fresnel")].astype(int) for r in RADII_KM},
    })
    iso_out = ROOT / "dataset/ml/tower_isolated.csv"
    iso.to_csv(iso_out, index=False)
    print(f"\nwrote {iso_out.relative_to(ROOT)}  ({len(iso)} tower settlements, "
          f"{int(isolated[(RADII_KM[-1], 'fresnel')].sum())} reachable only by themselves "
          f"at {RADII_KM[-1]} km)")

    fr = [x["fresnel"]["rm_base"] for x in rows]
    print(f"\none mast per settlement, base case   {money(one_per)} ({len(tw)} masts)")
    print(f"distance-only spread across radii    "
          f"{money(rows[0]['distance']['rm_base'])} to {money(rows[-1]['distance']['rm_base'])}"
          f"  = {money(rows[0]['distance']['rm_base'] - rows[-1]['distance']['rm_base'])}")
    print(f"screened spread across radii         "
          f"{money(max(fr))} to {money(min(fr))}"
          f"  = {money(max(fr) - min(fr))}")

    out = ROOT / "dataset/ml/tower_los_scenarios.json"
    out.write_text(json.dumps({
        "_what": "Mast counts for the 449 tower settlements once each candidate "
                 "path is screened for line of sight and 60% Fresnel clearance "
                 "against SRTM. Supersedes the distance-only figures in "
                 "tower_scenarios.json, which assumed every in-radius path worked.",
        "_still_not": "A terrain screen, not a propagation model. No ground "
                      "cover, clutter loss, interference or capacity. ITU-R "
                      "P.1812 is the real calculation. SRTM is C-band radar so "
                      "over forest it reads partway up the canopy, which "
                      "over-blocks cleared land and under-blocks tall forest.",
        "_assumptions": {
            "mast_height_m": H_MAST_M,
            "mast_height_source": "Oughton 2021 (arXiv:2102.03561) p12, 30 m tower",
            "receiver_height_m": H_RECV_M,
            "receiver_height_source": "UNSOURCED, ours, and it moves the answer",
            "band_mhz": BAND_MHZ,
            "band_source": "ASSUMED, needs confirming against MCMC/JENDELA "
                           "before it is quoted",
            "earth_radius_factor": "4/3",
            "fresnel_clearance": 0.6,
        },
        "n_tower_settlements": len(tw),
        "screened_paths": len(los),
        "dem_voids": int(los.voids.sum()),
        "cost_per_site_rm": COST_PER_SITE,
        "one_per_settlement_base_rm": one_per,
        "path_pass_rates": {
            str(r): {
                "paths": int((los.radius_km == r).sum()),
                "los_pct": round(float(los[los.radius_km == r].los.mean() * 100), 1),
                "fresnel_pct": round(float(los[los.radius_km == r].fresnel.mean() * 100), 1),
            } for r in RADII_KM
        },
        "scenarios": rows,
    }, indent=2), encoding="utf8")
    print(f"\nsaved {out.relative_to(ROOT)}")

    # The browser copy. Same numbers, plus the sites and links the map draws,
    # and no indentation because nothing reads it by eye.
    web_out = ROOT / "dataset/web/towers_los.json"
    web_out.write_text(json.dumps({
        "_what": "Screened mast siting. Candidate sites are settlement centres, "
                 "selected by a greedy set-cover heuristic over paths that cleared a "
                 "line-of-sight and 60% Fresnel test against SRTM. Candidate "
                 "service areas, NOT predicted radio coverage.",
        "n_tower_settlements": len(tw),
        "cost_per_site_rm": COST_PER_SITE,
        "one_per_settlement_base_rm": one_per,
        "assumptions": {"mast_m": H_MAST_M, "recv_m": H_RECV_M, "band_mhz": BAND_MHZ},
        "radii": RADII_KM,
        "scenarios": rows,
        "path_pass": {str(r): {
            "paths": int((los.radius_km == r).sum()),
            "los": int(los[los.radius_km == r].los.sum()),
            "fresnel": int(los[los.radius_km == r].fresnel.sum()),
        } for r in RADII_KM},
        "map": {str(r): web[r] for r in RADII_KM},
    }, separators=(",", ":")), encoding="utf8")
    print(f"saved {web_out.relative_to(ROOT)}  "
          f"({web_out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

"""Publish the fibre build clusters, and re-verify them on the way through.

Run from the repo root, whenever clusters.json is regenerated:

    python dataset/export_clusters.py

Reads  : dataset/ml/clusters.json
Writes : dataset/web/clusters.json

WHAT IT IS
----------
One entry per settlement: the fibre cluster it belongs to, and `trunk_km`, the
length of the spanning-tree edge that attaches it to that cluster's trunk.

The budget what-if currently charges every fibre settlement `cost_per_km` times
its OWN full distance to town, so ten villages along one road are each billed
for the whole road. `trunk_km` is what they actually add: the cluster root pays
the full run in from the town, everybody else pays their spur.

Over the 323 settlements the recommender sends to fibre that is 1,363 km billed
today against 890 km as shared builds, so the panel overstates fibre by 1.53x.

WHY IT IS VALIDATED HERE RATHER THAN TRUSTED
--------------------------------------------
The file is produced outside this repo, and a silent change to the fibre rule
or the 1 km floor would move real money on screen with nothing to catch it.
These checks are cheap and they fail loudly.

    cl: -1 means noise or non-fibre. Every settlement has an entry, so a lookup
    can never miss and quietly fall back to the old cost for one row.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dataset" / "ml" / "clusters.json"
OUT = ROOT / "dataset" / "web" / "clusters.json"
TABLE = ROOT / "dataset" / "ml" / "training_table.csv"

# Must match RULE_PARAMS in agent/tools.py and the dashboard's recommender.
FIBRE_MAX_KM, FIBRE_MIN_POP = 15, 3000
FLOOR_KM = 1.0


def main():
    for f in (SRC, TABLE):
        if not f.exists():
            raise SystemExit("missing %s" % f)

    cl = json.loads(SRC.read_text(encoding="utf8"))
    t = pd.read_csv(TABLE)

    # ── every settlement present, so no lookup misses ───────────────────────
    missing = set(t.settlement_id) - set(cl)
    extra = set(cl) - set(t.settlement_id)
    if missing or extra:
        raise SystemExit("settlement mismatch: %d missing, %d unknown"
                         % (len(missing), len(extra)))

    t["cl"] = t.settlement_id.map(lambda s: cl[s]["cl"])
    t["trunk_km"] = t.settlement_id.map(lambda s: cl[s]["trunk_km"])
    t["fibre"] = (t.backhaul_km <= FIBRE_MAX_KM) & (t.pop_2km >= FIBRE_MIN_POP)

    # ── the invariants ──────────────────────────────────────────────────────
    if (t.trunk_km < FLOOR_KM - 1e-9).any():
        raise SystemExit("%d settlements sit below the %g km floor"
                         % (int((t.trunk_km < FLOOR_KM - 1e-9).sum()), FLOOR_KM))
    if t.trunk_km.isna().any():
        raise SystemExit("trunk_km has nulls")

    nf = t[~t.fibre]
    if (nf.cl != -1).any():
        raise SystemExit("%d non-fibre settlements were given a cluster"
                         % int((nf.cl != -1).sum()))
    off = nf.trunk_km - nf.backhaul_km.clip(lower=FLOOR_KM)
    if off.abs().gt(0.011).any():
        raise SystemExit("%d non-fibre settlements had their cost changed"
                         % int(off.abs().gt(0.011).sum()))

    f = t[t.fibre]
    # A cluster cannot cost more than billing each member its own way in.
    if f.trunk_km.sum() > f.backhaul_km.clip(lower=FLOOR_KM).sum():
        raise SystemExit("clustering made fibre more expensive, not less")

    today = f.backhaul_km.clip(lower=FLOOR_KM).sum()
    after = f.trunk_km.sum()
    OUT.write_text(json.dumps(cl, separators=(",", ":")), encoding="utf8")

    print("wrote %s  (%.0f KB)" % (OUT, OUT.stat().st_size / 1024))
    print("  settlements        %d" % len(cl))
    print("  fibre              %d in %d clusters, %d unclustered"
          % (len(f), f.cl[f.cl >= 0].nunique(), int((f.cl == -1).sum())))
    print("  trench billed now  %.1f km" % today)
    print("  as shared builds   %.1f km" % after)
    print("  overstated by      %.2fx" % (today / after))
    print("  cheaper for        %d of %d fibre settlements"
          % (int((f.trunk_km < f.backhaul_km.clip(lower=FLOOR_KM) - 1e-9).sum()), len(f)))


if __name__ == "__main__":
    main()

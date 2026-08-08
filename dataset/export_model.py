"""Publish the coverage model so the dashboard and the agent can both see it.

Run from the repo root, after a model run:

    python dataset/export_model.py

Reads
    dataset/ml/model_predictions_v1.csv   one row per settlement, 216 modelled
    dataset/ml/model_report.json          the validation numbers

Writes
    dataset/web/dipi.geojson                              + 5 properties
    dataset/web/model_report.json                         the model card
    dataset/settlements/settlements_sabah_04_model.parquet  the agent's copy

WHY THREE FILES
---------------
The dashboard and the agent gate on different things, and both gates have to
open or the model is half-shipped:

  * the dashboard only fetches model_report.json IF dipi.geojson already
    carries `speed_source` (see the boot branch in index.html)
  * agent/tools.py sets HAS_MODEL from `speed_source` in the PARQUET, and
    prefers settlements_sabah_04_model.parquet over the DIPI one

THE STRING THAT MATTERS
-----------------------
`speed_source` must read exactly "modelled estimate". Both the dashboard's
isModelled() and the agent's guardrail flag compare against that literal. The
model CSV says "modelled", and shipping that verbatim would silently disable
the check that stops a modelled number being narrated as a measurement. This is
the one rename in here that is a safety fix rather than cosmetics.

Nothing is invented. Settlements with no prediction keep null, and the observed
speeds are untouched.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ML = ROOT / "dataset" / "ml"
WEB = ROOT / "dataset" / "web"
SETTLEMENTS = ROOT / "dataset" / "settlements"

PRED = ML / "model_predictions_v1.csv"
REPORT = ML / "model_report.json"
GEO = WEB / "dipi.geojson"
BASE = SETTLEMENTS / "settlements_sabah_03_dipi.parquet"

MODELLED = "modelled estimate"   # the literal both guardrails compare against
OBSERVED = "observed"

# What renderModelCard() reads, in the order it renders them. Anything absent
# is skipped by the card rather than shown blank, so a partial report degrades
# to a shorter card instead of a broken one.
CARD_KEYS = ["target", "cv_mae_spatial", "cv_r2_spatial", "cv_mae_random",
             "cv_r2_random", "baseline_mae", "beats_baseline", "n_train",
             "n_predicted", "run_date", "data_version", "model_version",
             "uncertainty_method", "feature_importance"]


def r2(v):
    """Round, and keep NaN as None so it survives JSON as null rather than NaN."""
    return None if pd.isna(v) else round(float(v), 2)


def main():
    for f in (PRED, REPORT, GEO, BASE):
        if not f.exists():
            raise SystemExit("missing %s" % f)

    pred = pd.read_csv(PRED)
    n_modelled = int((pred.speed_source == "modelled").sum())

    # ── the five properties, keyed by settlement ────────────────────────────
    cols = {}
    for r in pred.itertuples(index=False):
        modelled = r.speed_source == "modelled"
        shap = [getattr(r, "top_factor_%d" % i) for i in (1, 2, 3)]
        shap = [s for s in shap if isinstance(s, str) and s]
        cols[r.settlement_id] = {
            "speed_source": MODELLED if modelled else OBSERVED,
            "pred_dl_mbps": r2(r.predicted_speed) if modelled else None,
            "pred_lo": r2(r.prediction_lower) if modelled else None,
            "pred_hi": r2(r.prediction_upper) if modelled else None,
            # The dashboard splits this on "|"; the agent passes it through.
            "shap_top3": "|".join(shap) if modelled and shap else None,
        }

    # ── 1. dipi.geojson ────────────────────────────────────────────────────
    fc = json.loads(GEO.read_text(encoding="utf8"))
    missing = [f for f in fc["features"]
               if f["properties"]["settlement_id"] not in cols]
    if missing:
        raise SystemExit("%d settlements have no row in the predictions file"
                         % len(missing))
    for f in fc["features"]:
        f["properties"].update(cols[f["properties"]["settlement_id"]])
    GEO.write_text(json.dumps(fc), encoding="utf8")

    # ── 2. model_report.json ───────────────────────────────────────────────
    rep = json.loads(REPORT.read_text(encoding="utf8"))
    out = {k: rep[k] for k in CARD_KEYS if k in rep}
    out.setdefault("n_predicted", n_modelled)
    # The card renders this with String(), so an object would print as
    # "[object Object]". Flatten to the one part a reader can act on.
    dv = rep.get("data_version")
    if isinstance(dv, dict):
        out["data_version"] = "%s / %s" % (dv.get("ookla", "?"),
                                           str(dv.get("table_sha256", ""))[:12])
    (WEB / "model_report.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf8")

    # ── 3. the agent's parquet ─────────────────────────────────────────────
    df = pd.read_parquet(BASE)
    add = pd.DataFrame.from_dict(cols, orient="index")
    add.index.name = "settlement_id"
    df = df.merge(add.reset_index(), on="settlement_id", how="left")
    df.to_parquet(SETTLEMENTS / "settlements_sabah_04_model.parquet",
                  index=False)

    print("wrote:")
    print("  %s   (+5 properties on %d features)" % (GEO, len(fc["features"])))
    print("  %s" % (WEB / "model_report.json"))
    print("  %s" % (SETTLEMENTS / "settlements_sabah_04_model.parquet"))
    print("modelled settlements: %d   observed: %d"
          % (n_modelled, len(pred) - n_modelled))
    print("speed_source values : %s"
          % sorted({v["speed_source"] for v in cols.values()}))


if __name__ == "__main__":
    main()

"""Export the OpenCelliD tower records to GeoJSON for the dashboard.

Run once, from the repo root:

    python dataset/export_towers.py

Reads  : dataset/settlements/ocid_sabah.parquet
Writes : dataset/web/towers.geojson   (1,217 crowdsourced cell records)

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
OpenCelliD is CROWDSOURCED. A record exists because somebody walked or drove
past with a logging app. An area with no marker has not been surveyed. It is
NOT an area without towers, and the layer must never be captioned as though it
were. 73% of our settlements have no record within 5 km, and that absence
tracks survey effort, not infrastructure: the count of nearby records
correlates +0.56 with Ookla test count, which is a measure of who bothered to
test rather than of what is built.

That is why these values are a MAP LAYER and not model features. Feeding them
to the coverage model would teach it that unobserved means slow, which is the
one inference this project exists to refuse.

WHAT WE KEEP, AND WHY THE REST IS DROPPED
-----------------------------------------
    radio      LTE or GSM. 1,171 LTE, 46 GSM.
    net        operator code, kept as an OPAQUE NUMBER. We do not resolve it to
               a brand name. Naming operators invites "this operator has poor
               coverage", which is a claim this data cannot support and which
               the project does not make.
    samples    how many observations back this record. Median 7, minimum 1.
               This is the confidence signal and it is the reason the layer
               carries a caveat rather than a tick.
    range_m    OpenCelliD's own estimate of POSITION uncertainty. It is not a
               coverage radius, and it must never be drawn as one. Rendering
               these as filled circles would produce exactly the interpolated
               coverage surface the design rules forbid.
    updated    year the record was last confirmed.

Dropped: averageSignal (zero in every row), changeable (1 in every row), mcc
(502 in every row), unit, area, cell (internal cell identifiers with nothing to
show a planner).

Nothing here modifies, imputes or invents a value.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dataset" / "settlements" / "ocid_sabah.parquet"
OUT = ROOT / "dataset" / "web" / "towers.geojson"

# Sabah bounding box, used only to verify the export, never to filter silently.
BBOX = (115.0, 4.0, 119.7, 7.6)

KEEP = ["radio", "net", "lon", "lat", "range", "samples", "updated"]


def main():
    if not SRC.exists():
        raise SystemExit(
            "missing %s\nPut ocid_sabah.parquet there, then re-run." % SRC)

    df = pd.read_parquet(SRC)
    missing = [c for c in KEEP if c not in df.columns]
    if missing:
        raise SystemExit("source is missing columns: %s" % ", ".join(missing))

    df = df[KEEP].copy()

    outside = df[(df.lon < BBOX[0]) | (df.lon > BBOX[2])
                 | (df.lat < BBOX[1]) | (df.lat > BBOX[3])]
    if len(outside):
        raise SystemExit("%d records fall outside Sabah, check the source"
                         % len(outside))

    feats = []
    for r in df.itertuples(index=False):
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [round(float(r.lon), 5),
                                         round(float(r.lat), 5)]},
            "properties": {
                "radio": str(r.radio),
                "net": int(r.net),
                "samples": int(r.samples),
                # Position uncertainty in metres. NOT a coverage radius.
                "range_m": int(r.range),
                "updated": datetime.fromtimestamp(
                    int(r.updated), tz=timezone.utc).year,
            },
        })

    fc = {
        "type": "FeatureCollection",
        # Read by anything that consumes this file, so the caveat travels with
        # the data rather than living only in the dashboard caption.
        "note": ("Crowdsourced cell records from OpenCelliD. Incomplete by "
                 "construction. An area with no record has not been surveyed, "
                 "which is not the same as an area with no tower. Never used "
                 "as evidence of poor service."),
        "source": "OpenCelliD, MCC 502, Sabah extract",
        "licence": "CC BY-SA 4.0",
        "features": feats,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fc), encoding="utf8")

    thin = sum(1 for f in feats if f["properties"]["samples"] < 5)
    print("wrote %s" % OUT)
    print("  %d records   %.0f KB" % (len(feats), OUT.stat().st_size / 1024))
    print("  radio: %s" % df.radio.value_counts().to_dict())
    print("  %d records (%.0f%%) rest on fewer than 5 observations"
          % (thin, 100 * thin / len(feats)))


if __name__ == "__main__":
    main()

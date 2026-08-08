"""Export the OSM facilities parquet to GeoJSON for the dashboard.

Run once, from the repo root:

    python dataset/export_facilities.py

Reads  : dataset/settlements/facilities_sabah_osm.parquet
Writes : dataset/web/facilities.geojson   (606 points: schools + health)

Nothing here modifies, imputes or invents a value. Names that are null in OSM
stay null; the dashboard renders them as "Unnamed {type} (F####)".
"""
import json
import struct
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dataset" / "settlements" / "facilities_sabah_osm.parquet"
OUT = ROOT / "dataset" / "web" / "facilities.geojson"

# Sabah bounding box, used only to verify the export, never to filter silently.
BBOX = (115.0, 4.0, 119.7, 7.6)
HEALTH = {"clinic", "hospital", "doctors"}


def wkb_point(buf):
    """Decode a WKB Point. Returns (lon, lat) in EPSG:4326 x,y order."""
    if not isinstance(buf, (bytes, bytearray)):
        raise TypeError("expected WKB bytes, got %r" % type(buf))
    little = buf[0] == 1
    endian = "<" if little else ">"
    (geom_type,) = struct.unpack(endian + "I", buf[1:5])
    if geom_type != 1:
        raise ValueError("expected Point (type 1), got type %d" % geom_type)
    return struct.unpack(endian + "dd", buf[5:21])


def main():
    if not SRC.exists():
        raise SystemExit("missing %s\nPut the parquet there, then re-run." % SRC)

    df = pd.read_parquet(SRC)
    for col in ("name", "amenity", "geometry"):
        if col not in df.columns:
            raise SystemExit("column %r missing; found %s" % (col, list(df.columns)))

    feats, outside = [], []
    for i, row in enumerate(df.itertuples(index=False)):
        lon, lat = wkb_point(row.geometry)
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            outside.append((i, lon, lat))
        name = row.name if isinstance(row.name, str) and row.name.strip() else None
        feats.append({
            "type": "Feature",
            "properties": {
                "facility_id": "F%04d" % i,
                "name": name,
                "amenity": row.amenity,
                "kind": "health" if row.amenity in HEALTH else "school",
            },
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")

    counts = df["amenity"].value_counts().to_dict()
    print("wrote %s" % OUT)
    print("  features      : %d" % len(feats))
    print("  amenity       : %s" % counts)
    print("  unnamed (null): %d" % sum(1 for f in feats if f["properties"]["name"] is None))
    print("  outside bbox  : %d %s" % (len(outside), outside[:5] if outside else ""))
    print("  size          : %.1f KB" % (OUT.stat().st_size / 1024))


if __name__ == "__main__":
    main()

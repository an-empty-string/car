import json
from typing import Any

from model import Database, has_geocode

database = Database.get()

geojson_doors: list[dict[str, Any]] = []
for door in database.doors:
    if not has_geocode(door):
        continue

    door = door.to_dict()
    door["n_voters"] = len(door.pop("voters"))
    geojson_doors.append(
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [door["lon"], door["lat"]],
            },
            "properties": door,
        }
    )

with open("geocoded_doors.geojson", "w") as f:
    json.dump(
        {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            },
            "features": geojson_doors,
        },
        f,
    )

print(f"Wrote {len(geojson_doors)} doors!")

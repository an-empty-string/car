import json
import os
from typing import Any

from ..model import Database, has_geocode

database = Database.get()

include_voters = set()

group_id = os.getenv("TURF_GROUP")
for group in database.group:
    if group.external_id == group_id:
        include_voters.update(group.voters)

geojson_doors: list[dict[str, Any]] = []
for door in database.doors:
    if not has_geocode(door):
        continue

    door = door.to_dict()
    door_voters = include_voters.intersection(door.pop("voters"))

    if not door_voters:
        continue

    door["n_voters"] = len(door_voters)
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

with open(f"geocoded_doors-{group_id}.geojson", "w") as f:
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

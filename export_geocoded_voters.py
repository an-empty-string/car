import json

from model import Database

database = Database.load()

geojson_doors = []
for door in database.doors:
    if not door.has_geocode:
        continue

    door = dict(door)
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

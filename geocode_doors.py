import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.abspath(os.path.dirname(__file__)), "../geocode")
)
from geocode import get_geocoder  # pyright: ignore

geocoder = get_geocoder()

with open("database.json") as f:
    obj = json.load(f)

for door in obj["doors"]:
    if door["lat"] is not None and door["lon"] is not None:
        continue

    result = geocoder.geocode(door["address"], door["city"])

    print(door["address"], door["city"], result)
    if result is not None:
        door["lat"], door["lon"] = result

with open("database.json", "w") as f:
    json.dump(obj, f, indent=4)

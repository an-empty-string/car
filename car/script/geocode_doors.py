import csv
import os
import sys

from ..model import Database, has_geocode

sys.path.insert(
    0, os.path.join(os.path.abspath(os.path.dirname(__file__)), "../../../geocode")
)
from geocode import get_geocoder  # pyright: ignore

geocoder = get_geocoder()
database = Database.get()

todos = []
todones = {}

if os.path.exists("geocode-todones.csv"):
    with open("geocode-todones.csv") as f:
        lines = csv.DictReader(f)
        todones = {
            (line["address"], line["city"]): (float(line["lat"]), float(line["lon"]))
            for line in lines
        }

for door in database.doors:
    if has_geocode(door):
        continue

    if todone_result := todones.get((door.address, door.city)):
        door.lat, door.lon = todone_result

    else:
        result = geocoder.geocode(door.address, door.city)
        if result is not None:
            door.lat, door.lon = result

        else:
            # save to todos file
            todos.append(
                {"address": door.address, "city": door.city, "state": "ALABAMA"}
            )

    database.save_door(door)

database.commit()

with open("geocode-todos.csv", "w") as f:
    csv.DictWriter(f, ["address", "city", "state"]).writerows(todos)
    print("Wrote geocode-todos.csv")

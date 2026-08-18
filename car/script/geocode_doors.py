import csv
import os
import sys

from ..model import Database, has_geocode

sys.path.insert(
    0, os.path.join(os.path.abspath(os.path.dirname(__file__)), "../../../geocode")
)
from geocode import get_geocoder  # type: ignore

geocoder = get_geocoder()
database = Database.get()

todos = []
todones = {}

with open("already_geocoded.txt") as f:
    already_geocoded = set(int(x.strip()) for x in f)

if os.path.exists("geocode-todones.csv"):
    with open("geocode-todones.csv") as f:
        lines = csv.DictReader(f)
        todones = {
            (line["address"], line["city"]): (float(line["lat"]), float(line["lon"]))
            for line in lines
        }

for door in database.doors:
    if has_geocode(door) and door.id in already_geocoded:
        continue

    if todone_result := todones.get((door.address, door.city)):
        print("Updated geocoding result from cached for", door.address, door.city)
        door.lat, door.lon = todone_result

    else:
        result = geocoder.geocode(door.address, door.city, unit=door.unit)
        if result is not None:
            print("Updated geocoding result for", door.address, door.city)
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

with open("already_geocoded.txt", "w") as f:
    f.write("\n".join(str(x) for x in already_geocoded))
    print("Wrote already_geocoded.txt")

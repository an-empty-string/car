import os
import sys

from model import Database, has_geocode

sys.path.insert(
    0, os.path.join(os.path.abspath(os.path.dirname(__file__)), "../geocode")
)
from geocode import get_geocoder  # pyright: ignore

geocoder = get_geocoder()
database = Database.load()

for door in database.doors:
    if has_geocode(door):
        continue

    result = geocoder.geocode(door.address, door.city)
    print(door.address, door.city, result)
    if result is not None:
        door.lat, door.lon = result

    database.save_door(door)

database.commit()

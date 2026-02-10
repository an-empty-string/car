#!/usr/bin/env python3
import csv
import os
import re
import sqlite3
import subprocess

from model import ID, Database, Turf, has_geocode

TURF_DATA_PATH = os.environ["TURF_DATA_PATH"]

database = Database.load()


def sync_turf_props():
    # turfs without a car_id in turfs_data -> create in car and assign turf_id
    # turfs with a car_id -> update name in car

    conn = sqlite3.connect(TURF_DATA_PATH)
    cur = conn.cursor()

    cur.execute("SELECT rowid, car_id, name FROM turfs")
    turf_meta = cur.fetchall()
    cur.close()

    for rowid, car_id, name in turf_meta:
        if car_id is None:
            turf = database.save_turf(Turf(desc=name, created_by="GIS turf import"))

            cur = conn.cursor()
            cur.execute("UPDATE turfs SET car_id=? WHERE rowid=?", (turf.id, rowid))
            cur.close()

        else:
            turf = database.get_turf_by_id(car_id)
            turf.desc = name
            database.save_turf(turf)

    conn.commit()
    conn.close()


def set_voter_turfs():
    subprocess.call(
        [
            # --distance_units=meters --area_units=m2 --ellipsoid=EPSG:7030
            "qgis_process",
            "run",
            "native:joinattributesbylocation",
            "--INPUT=./geocoded_doors.geojson",
            "--PREDICATE=5",  # contained within
            "--JOIN=spatialite://dbname='/home/tris/maps/hd25/turfs_data.sqlite' table='turfs'(geometry) sql=",
            "--METHOD=1",
            "--DISCARD_NONMATCHING=false",
            "--PREFIX=",
            "--OUTPUT=./geocoded_doors_turfs_tmp.csv",
        ]
    )

    with open("geocoded_doors_turfs_tmp.csv") as f:
        turfed_doors = list(csv.DictReader(f))

    for turfed_door in turfed_doors:
        # if there is no car_id, it's not actually turfed / we can't update it
        if not turfed_door["car_id"]:
            continue

        door_id = int(turfed_door["_id"])

        car_door = database.get_door_by_id(door_id)
        new_turf_id = int(turfed_door["car_id"])

        # move the door to its new turf
        car_door.turf_id = new_turf_id
        database.save_door(car_door)

        # move every voter on this door to their new turf
        for voter_id in car_door.voters:
            car_voter = database.get_voter_by_id(voter_id)
            car_voter.turf_id = new_turf_id
            database.save_voter(car_voter)


# routing "algorithm"
def numpart(x: str) -> str:
    return re.findall("^[0-9]+", x)[0]


def score_door(door_id: ID, from_door_id: ID) -> float:
    door = database.get_door_by_id(door_id)
    from_door = database.get_door_by_id(from_door_id)

    assert has_geocode(door) and has_geocode(from_door)

    dist = ((float(door.lat) - float(from_door.lat)) * 1000) ** 2 + (
        (float(door.lon) - float(from_door.lon)) * 1000
    ) ** 2

    ad1 = int(numpart(door.address))
    ad2 = int(numpart(from_door.address))

    if door.address.split()[1:] == from_door.address.split()[1:]:
        dist -= 10
        if ad1 % 2 == ad2 % 2:
            dist -= 5

    return dist


def reorder_doors(turf: Turf):
    routes: list[tuple[float, ID, list[ID]]] = []

    door_ids = turf.doors
    for start_id in door_ids:
        q = door_ids.copy()

        result_ids = [start_id]
        q.remove(start_id)

        total_score = 0
        while q:
            cur = result_ids[-1]
            n = list(sorted(q, key=lambda k: score_door(k, cur)))[0]
            q.remove(n)
            result_ids.append(n)

            total_score += score_door(n, cur)

        routes.append((total_score, start_id, result_ids))

    routes.sort()
    turf.doors = routes[0][2]


def reorder_all_doors():
    for turf in database.turfs:
        reorder_doors(turf)
        database.save_turf(turf)


if __name__ == "__main__":
    sync_turf_props()
    set_voter_turfs()
    reorder_all_doors()
    database.commit()

#!/usr/bin/env python3
import csv
import json
import os
import re
import sqlite3
import subprocess

TURF_DATA_PATH = os.environ["TURF_DATA_PATH"]

with open("database.json") as f:
    data = json.load(f)


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
            car_id = len(data["turfs"])
            data["turfs"].append(
                {
                    "_id": car_id,
                    "desc": name,
                    "phone_key": "",
                    "doors": [],
                    "voters": [],
                    "notes": [],
                    "created_by": "GIS turf import",
                }
            )

            cur = conn.cursor()
            cur.execute("UPDATE turfs SET car_id=? WHERE rowid=?", (car_id, rowid))
            cur.close()

        else:
            data["turfs"][car_id]["desc"] = name

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

        car_door = data["doors"][door_id]
        new_turf_id = int(turfed_door["car_id"])

        # move the door to its new turf
        data["turfs"][car_door["turf_id"]]["doors"].remove(door_id)
        data["turfs"][new_turf_id]["doors"].append(door_id)
        car_door["turf_id"] = new_turf_id

        # move every voter on this door to their new turf
        for voter_id in car_door["voters"]:
            car_voter = data["voters"][voter_id]
            data["turfs"][car_voter["turf_id"]]["voters"].remove(voter_id)
            data["turfs"][new_turf_id]["voters"].append(voter_id)
            car_voter["turf_id"] = new_turf_id


# routing "algorithm"
def numpart(x):
    return re.findall("^[0-9]+", x)[0]


def score_door(door_id, from_door_id):
    door = data["doors"][door_id]
    from_door = data["doors"][from_door_id]

    dist = ((float(door["lat"]) - float(from_door["lat"])) * 1000) ** 2 + (
        (float(door["lon"]) - float(from_door["lon"])) * 1000
    ) ** 2

    ad1 = int(numpart(door["address"]))
    ad2 = int(numpart(from_door["address"]))

    if door["address"].split()[1:] == from_door["address"].split()[1:]:
        dist -= 10
        if ad1 % 2 == ad2 % 2:
            dist -= 5

    return dist


def reorder_doors(turf):
    routes = []

    door_ids = turf["doors"]
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
    turf["doors"] = routes[0][2]


def reorder_all_doors():
    for turf in data["turfs"]:
        reorder_doors(turf)


def save_data():
    with open("database.json", "w") as f:
        json.dump(data, f, indent=4)


if __name__ == "__main__":
    sync_turf_props()
    set_voter_turfs()
    reorder_all_doors()
    save_data()

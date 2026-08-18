#!/usr/bin/env python3
import csv
import os
import random
import re
import sqlite3
import subprocess

from ..model import ID, Database, Turf, has_geocode

TURF_DATA_PATH = os.getenv("TURF_DATA_PATH", "")
TURF_GROUP_ID = os.getenv("TURF_GROUP")

database = Database.get()


def get_turf_group():
    for group in database.groups:
        if group.external_id == TURF_GROUP_ID:
            return group


def sync_turf_props():
    # turfs without a car_id in turfs_data -> create in car and assign turf_id
    # turfs with a car_id -> update name in car

    conn = sqlite3.connect(TURF_DATA_PATH)
    cur = conn.cursor()

    cur.execute("SELECT rowid, car_id, name FROM turfs")
    turf_meta = cur.fetchall()
    cur.close()

    turf_group = get_turf_group()
    assert turf_group

    active_turf_ids = {
        turf.id for turf in database.turfs if turf.group_id == turf_group.id
    }

    for rowid, car_id, name in turf_meta:
        if (
            car_id is None
            or car_id not in active_turf_ids
            or os.getenv("RECREATE_TURFS")
        ):
            turf = database.save_turf(
                Turf(
                    desc=name,
                    created_by="GIS turf import",
                    group_id=turf_group.id,
                )
            )

            cur = conn.cursor()
            cur.execute(
                "UPDATE turfs SET car_id=? WHERE rowid=?",
                (turf.id, rowid),
            )
            cur.close()

            print(f"imported turf {name}")

        else:
            turf = database.get_turf_by_id(car_id)
            turf.desc = name

            turf.voters = []
            turf.doors = []

            database.save_turf(turf)

    database.commit()

    conn.commit()
    conn.close()


def set_voter_turfs():
    subprocess.call(
        [
            # --distance_units=meters --area_units=m2 --ellipsoid=EPSG:7030
            "qgis_process",
            "run",
            "native:joinattributesbylocation",
            f"--INPUT=./geocoded_doors-{TURF_GROUP_ID}.geojson",
            "--PREDICATE=5",  # contained within
            f"--JOIN=spatialite://dbname='{TURF_DATA_PATH}' table='turfs'(geometry) sql=",
            "--METHOD=1",
            "--DISCARD_NONMATCHING=false",
            "--PREFIX=",
            "--OUTPUT=./geocoded_doors_turfs_tmp.csv",
        ]
    )

    turf_group = get_turf_group()
    assert turf_group

    with open("geocoded_doors_turfs_tmp.csv") as f:
        turfed_doors = list(csv.DictReader(f))

    turfs = {}

    for turfed_door in turfed_doors:
        # if there is no car_id, it's not actually turfed / we can't update it
        if not turfed_door["car_id"]:
            continue

        door_id = int(turfed_door["_id"])

        car_door = database.get_door_by_id(door_id)
        new_turf_id = int(turfed_door["car_id"])

        if new_turf_id not in turfs:
            turfs[new_turf_id] = database.get_turf_by_id(new_turf_id)

        new_turf = turfs[new_turf_id]

        # move the door to its new turf
        print(f"add door {car_door.id} to turf {new_turf_id}")
        new_turf.doors.append(car_door.id)

        # move every voter on this door to their new turf
        for voter_id in car_door.voters:
            if voter_id not in turf_group.voters:
                continue

            print(f"add voter {voter_id} to turf {new_turf_id}")
            new_turf.voters.append(voter_id)

    for turf in turfs.values():
        print("save turf", turf.desc, f"{len(turf.voters)=} {len(turf.doors)=}")
        database.save_turf(turf)


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

    if turf.id == 0:
        # "All Voters" default turf
        return

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
        if turf.phone_key:
            continue

        reorder_doors(turf)
        database.save_turf(turf)


def assign_login_codes():
    for turf in database.turfs:
        if turf.login_code:
            continue

        turf.login_code = "".join([str(random.randint(1, 9)) for x in range(10)])
        database.save_turf(turf)


if __name__ == "__main__":
    assert TURF_DATA_PATH, "$TURF_DATA_PATH not set"
    sync_turf_props()
    set_voter_turfs()
    database.fixup_backrefs()
    # reorder_all_doors()
    assign_login_codes()
    database.commit()

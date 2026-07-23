import json

import yaml

from ..model import Turf
from .update_voter_turfs import assign_login_codes, database

# load voter score data
with open("targeting_data.json") as f:
    targeting_data = json.load(f)


# test targeting data for voter against function
def test_voter(voter, expr):
    # set up the environment
    env = {}

    voter_targeting_data = targeting_data[voter.statevoterid].copy()
    for key, value in voter_targeting_data.pop("scores").items():
        key = key.removeprefix("hs_")
        env[key] = value or 0

    env.update(voter_targeting_data)

    # run the eval
    return eval(expr, env)


# load turfs config
with open("turf_defs.yml") as f:
    turf_configs = yaml.safe_load(f)

# get existing turfs
turfs_by_external_id = {}
for turf in database.turfs:
    if not turf.external_id:
        continue

    turfs_by_external_id[turf.external_id] = turf

# process turfs
for config in turf_configs:
    # get or create turf
    if config["name"] not in turfs_by_external_id:
        turfs_by_external_id[config["name"]] = database.save_turf(
            Turf(external_id=config["name"], created_by="system import")
        )

    turf = turfs_by_external_id[config["name"]]

    # update props from config
    for prop, value in config["props"].items():
        setattr(turf, prop, value)

    # map voters
    turf.voters = []
    for voter in database.voters:
        if test_voter(voter, config["rule"]):
            print(voter)
            turf.voters.append(voter.id)

    # handle geodata
    if "geo_data" in config:
        raise NotImplementedError("geo data not implemented yet!")

    database.save_turf(turf)

assign_login_codes()
database.commit()

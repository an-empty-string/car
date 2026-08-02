import functools
import json
import os
from collections.abc import Callable, Collection
from typing import Any, Protocol

import yaml

from ..model import Group, Turf
from .update_voter_turfs import assign_login_codes, database

# load voter score data
print("loading targeting data...")
with open("targeting_data.json") as f:
    targeting_data = json.load(f)


def attr_aliases():
    if os.path.exists("aliases.json"):
        with open("aliases.json") as f:
            return json.load(f)

    return {}


@functools.cache
def compile_expr(expr):
    return compile(expr, "<expr>", "eval")


# test targeting data for voter against function
def _test_voter(voter, expr):
    # set up the environment
    env = {}

    for alias, repl in attr_aliases().items():
        expr = expr.replace(f"@{alias}", repl)

    expr = compile_expr(expr)

    voter_targeting_data = targeting_data[voter.statevoterid].copy()
    for key, value in voter_targeting_data.pop("scores").items():
        key = key.removeprefix("hs_")
        env[key] = value or 0

    for key, value in voter_targeting_data.pop("consumer").items():
        key = key.removeprefix("ConsumerData_")
        env[f"cd_{key}"] = value

    env.update(voter_targeting_data)

    # run the eval
    return eval(expr, env), env


class HasExternalId(Protocol):
    external_id: str


def get_by_external_id[
    T: HasExternalId
](items: Collection[T], defs: list[T], save: Callable[[T], T]) -> dict[str, T]:
    """gets a dict of items (groups/turfs) by their external id,
    updating the db if the `defs` dont already exist in `items`"""
    items_by_external_id = {i.external_id: i for i in items if i.external_id}
    for item in defs:
        if item.external_id not in items_by_external_id:
            items_by_external_id[item.external_id] = save(item)
    return items_by_external_id


def make_list_of_defs[
    T: Any
](constructor: type[T], configs: list[dict[str, Any]]) -> list[T]:
    "constructs a list of the actual type based on the yaml defs"
    return [
        constructor(
            external_id=config["name"],
            created_by="system import",
            **config.get("props", {}),
        )
        for config in configs
    ]


# load turfs/groups config
print("loading defs...")
with open("defs.yml") as f:
    configs = yaml.safe_load(f)

turf_configs = [c for c in configs if c["type"] == "turf"]
group_configs = [c for c in configs if c["type"] == "group"]


def test_voter(voter, expr):
    return _test_voter(voter, expr)[0]


def main():
    # load turfs config
    with open("defs.yml") as f:
        configs = yaml.safe_load(f)
    turf_configs = [c for c in configs if c["type"] == "turf"]
    group_configs = [c for c in configs if c["type"] == "group"]

    # get existing turfs/groups
    turfs_by_external_id = get_by_external_id(
        database.turfs,
        make_list_of_defs(Turf, turf_configs),
        database.save_turf,
    )
    groups_by_external_id = get_by_external_id(
        database.groups,
        make_list_of_defs(Group, group_configs),
        database.save_group,
    )

    # process turfs
    print("processing turfs...")
    for config in turf_configs:
        turf = turfs_by_external_id[config["name"]]
        turf.voters = [
            voter.id for voter in database.voters if test_voter(voter, config["rule"])
        ]
        # handle geodata (or don't)
        if "geo_data" in config:
            raise NotImplementedError("geo data not implemented yet!")

        database.save_turf(turf)

    # process groups
    print("processing groups...")
    for config in group_configs:
        group = groups_by_external_id[config["name"]]

        for turf_external_id in config["turfs"]:
            turf = turfs_by_external_id[turf_external_id]
            group.turfs.append(turf.id)
            turf.group_id = group.id
            database.save_turf(turf)
            group.voters.extend(turf.voters)
            database.save_group(group)

    assign_login_codes()
    database.fix_id_duplicates()
    database.commit()
    print("done!")


if __name__ == "__main__":
    main()

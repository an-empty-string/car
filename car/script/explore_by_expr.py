import csv
import json
import pprint
import re
import traceback

from .create_turfs_from_defs import _test_voter, attr_aliases, database


def process_alias(x):
    aliases = attr_aliases()
    if x == "@@":
        pprint.pprint(aliases)
        return True

    q = re.match(r"^@([\w_]+)\s*:=\s*(.*)$", x)
    w = re.match(r"^@!([\w_]+)", x)
    if q:
        key, value = q.groups()
        aliases[key] = value
        print("Added alias", key)

    elif w:
        aliases.pop(w.group(1))
        print("Deleted alias", w.group(1))

    else:
        return False

    with open("aliases.json", "w") as f:
        json.dump(aliases, f)

    return True


def go(expr):
    if process_alias(expr):
        return

    results = []

    for voter in database.voters:
        result, data = _test_voter(voter, expr)
        if not result:
            continue

        results.append(voter.model_dump() | data)

    with open("out.csv", "w") as f:
        wr = csv.DictWriter(f, results[0].keys())
        wr.writeheader()
        wr.writerows(results)

    return len(results)


def main():
    while True:
        q = input("> ")
        try:
            rows = go(q)
            print(f"{rows} rows written to out.csv")
        except Exception:
            traceback.print_exc()
            print()


if __name__ == "__main__":
    main()

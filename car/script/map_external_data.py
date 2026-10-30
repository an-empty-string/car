import collections
import csv

from ..model import Database

LIMIT_TO_TURFS = [70]
FILENAME = "precincts.csv"

db = Database.get()
voters = db.voters

voters_in_turfs = set()
for turf in LIMIT_TO_TURFS:
    voters_in_turfs |= set(db.turfs[turf].voters)

vd_by_last_name = collections.defaultdict(list)

for v in voters:
    if v.id not in voters_in_turfs:
        continue

    vd_by_last_name[v.lastname].append((v, db.get_door_by_id(v.door_id)))

with open(FILENAME) as f:
    for row in csv.DictReader(f):
        all_matching = vd_by_last_name[row["LastName"]]
        candidates = []

        for c, _d in all_matching:
            if row["GivenNames"] == c.firstname or row["GivenNames"].startswith(
                f"{c.firstname} "
            ):
                candidates.append(c)

        if len(candidates) > 1:
            f_name, m_name = row["GivenNames"].split()
            candidates = [c for c in candidates if c.middlename == m_name]

        assert len(candidates) <= 1

        if not candidates:
            continue

        print(f"{candidates[0].statevoterid},{row['Precinct']}")

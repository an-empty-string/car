import csv
import itertools

from model import Database, Door, Voter, Turf

VOTER_FILE = "SOSVoterList_20230708_6344.csv"
DATABASE_OUT = "database.json"

with open(VOTER_FILE) as f:
    lines = list(csv.DictReader(f))

door_id_pool = itertools.count()
voter_id_pool = itertools.count()

doors: dict[tuple[str, str, str], Door] = {}
voters: list[Voter] = []


for line in lines:
    addr = " ".join(
        filter(
            None,
            [
                line["Residential Address Number"],
                line["Residential Address Number Suffix"],
                line["Residential Address Direction"],
                line["Residential Address Name"],
                line["Residential Address Type"],
                line["Residential Address Direction Suffix"],
            ],
        )
    )

    unit = " ".join(
        filter(
            None,
            [
                line["Residential Unit Type"],
                line["Residential Unit Number"],
            ],
        )
    )

    city = line["Residential City"]

    # get or create the door
    door_key = (addr, unit, city)
    if door_key not in doors:
        door_id = next(door_id_pool)
        doors[door_key] = Door(
            _id=door_id,
            turf_id=0,  # FIXME: None
            address=addr,
            unit=unit,
            city=city,
            voters=[],
            created_by="voter import",
            lat=None,
            lon=None,
        )

    door = doors[door_key]

    # create the voter
    voter = Voter(
        _id=next(voter_id_pool),
        statevoterid=line["Registrant ID"],
        activeinactive=line["Registrant Status"],
        firstname=line["First Name"],
        middlename=line["Middle Name"],
        lastname=line["Last Name"],
        cellphone="",
        landlinephone=f"({line['Phone - Area Code']}) {line['Phone Number - Exchange']}-{line['Phone Number - Last Four Digits']}",
        gender=line["Gender"],
        race=line["Race"],
        birthdate=f"{2026 - int(line['Age'])}-01-01",
        regdate=line["Date of Registration"],
        notes=[],
        created_by="system import",
        door_id=door.id,
        turf_id=0,  # FIXME: None,
        phonebankturf=None,
        bestphone="",
    )
    voter.bestphone = voter.landlinephone

    voters.append(voter)
    door.voters.append(voter.id)


database = Database(
    turfs=[
        Turf(
            _id=0,
            desc="All Voters",
            phone_key="",
            doors=[door.id for door in doors.values()],
            voters=[voter.id for voter in voters],
            notes=[],
            created_by="system import",
        )
    ],
    doors=list(doors.values()),
    voters=voters,
)

with open(DATABASE_OUT, "w") as f:
    f.write(database.to_json())

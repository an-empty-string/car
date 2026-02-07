import csv

from model import DATABASE_FILE, Database, Door, Turf, Voter

VOTER_FILE = "SOSVoterList_20230708_6344.csv"


with open(VOTER_FILE) as f:
    lines = list(csv.DictReader(f))


database = Database()
database.save_turf(Turf(desc="All Voters", created_by="system import"))

doors: dict[tuple[str, str, str], Door] = {}


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
        doors[door_key] = database.save_door(
            Door(
                turf_id=0,  # FIXME: None
                address=addr,
                unit=unit,
                city=city,
                created_by="voter import",
            )
        )

    door = doors[door_key]

    # create the voter
    voter_phone = f"({line['Phone - Area Code']}) {line['Phone Number - Exchange']}-{line['Phone Number - Last Four Digits']}"
    database.save_voter(
        Voter(
            statevoterid=line["Registrant ID"],
            activeinactive=line["Registrant Status"],
            firstname=line["First Name"],
            middlename=line["Middle Name"],
            lastname=line["Last Name"],
            landlinephone=voter_phone,
            gender=line["Gender"],
            race=line["Race"],
            birthdate=f"{2026 - int(line['Age'])}-01-01",
            regdate=line["Date of Registration"],
            created_by="system import",
            door_id=door.id,
            turf_id=0,  # FIXME: None,
            bestphone=voter_phone,
        )
    )

with open(DATABASE_FILE, "w") as f:
    f.write(database.to_json())

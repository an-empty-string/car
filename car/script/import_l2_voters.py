import csv

from ..model import Database, Door, Voter

VOTER_FILE = "132180_Deliverable.csv"

f = open(VOTER_FILE)
lines = csv.DictReader(f)

database = Database()

doors: dict[tuple[str, str, str], Door] = {}


def fix_date(x):
    if not x:
        return "1800-01-01"
    m, d, y = x.split("/")
    return f"{y}-{m}-{d}"


def float_or_none(x):
    if not x:
        return None

    return float(x)


def race(x):
    q = x["CountyEthnic_Description"]
    return {
        "White Self Reported": "W",
        "African or Af-Am Self Reported": "B",
        "East Asian": "A",
        "Native American (self reported)": "I",
        "Hispanic": "H",
        "Other Undefined Race": "O",
        "": "",
    }[q]


for line in lines:
    addr = line["Residence_Addresses_AddressLine"]
    unit = " ".join(
        filter(
            None,
            [
                line["Residence_Addresses_ApartmentType"],
                line["Residence_Addresses_ApartmentNum"],
            ],
        )
    )
    city = line["Residence_Addresses_City"]

    door_key = (addr, unit, city)
    if door_key not in doors:
        doors[door_key] = database.save_door(
            Door(
                address=addr,
                unit=unit,
                city=city,
                lat=float_or_none(line["Residence_Addresses_Latitude"]),
                lon=float_or_none(line["Residence_Addresses_Longitude"]),
                created_by="voter import",
            )
        )

    database.save_voter(
        Voter(
            statevoterid=line["Voters_StateVoterID"],
            activeinactive=line["Voters_Active"],
            firstname=line["Voters_FirstName"],
            middlename=line["Voters_MiddleName"],
            lastname=line["Voters_LastName"],
            landlinephone=line["VoterTelephones_LandlineFormatted"],
            cellphone=line["VoterTelephones_CellPhoneFormatted"],
            gender=line["Voters_Gender"] or "U",
            party=line["hf_ideology_overall_party"],
            race=race(line),
            birthdate=fix_date(line["Voters_BirthDate"]),
            regdate=fix_date(line["Voters_CalculatedRegDate"]),
            created_by="system import",
            door_id=doors[door_key].id,
            bestphone=(
                line["VoterTelephones_CellPhoneFormatted"]
                or line["VoterTelephones_LandlineFormatted"]
            ),
        )
    )


database.commit(backup=False)
f.close()

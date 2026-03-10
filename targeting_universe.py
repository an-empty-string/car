import csv
import functools
import math
from datetime import date, datetime

VOTER_FILE = "SOSVoterList_20260219_8835.csv"
ELECTIONS_FILE = "al_election_codes.csv"

election_fields = [
    ("Last Election Voted", "Last Election Party Code"),
] + [(f"Election {n}", f"Party Code {n}") for n in range(2, 11)]

names_map = {
    "2008 PRESIDENTIAL PREFERENCE PRIMARY": "PP0802",
    "2008 PRIMARY RUNOFF ELECTION": "RO0807",
    "2010 STATEWIDE GENERAL ELECTION": "GN1011",
    "2010 STATEWIDE PRIMARY ELECTION": "PR1006",
    "2010 STATEWIDE RUNOFF ELECTION": "RO1007",
    "2014 STATEWIDE PRIMARY RUNOFF": "RO1407",
    "2016 PRIMARY ELECTION": "PPP163",
    "2016 PRIMARY RUNOFF ELECTION": "RO1604",
    "2017 HD04 - SPECIAL PRIMARY": "04PR17",
    "2017 SD26 - SPECIAL PRIMARY": "26PR17",
    "2017 US SENATE SPECIAL GENERAL": "GNSN17",
    "2017 US SENATE SPECIAL PRIMARY": "PRSN17",
    "2017 US SENATE SPECIAL RUNOFF": "ROSN17",
    "2018 HD04 - SPECIAL PRIMARY RUNOFF": "04RO18",
    "2018 PRIMARY RUNOFF ELECTION": "RO1807",
    "2018 SD26 - SPECIAL PRIMARY RUNOFF": "26RO18",
    "2019 SPECIAL GENERAL": "42GN19",  # arbitrary - multiple special generals in 2019
    "2019 SPECIAL HOUSE DISTRICT 74 PRIMARY": "74PR19",
    "2019 SPECIAL HOUSE DISTRICT 74 RUNOFF": "74RO19",
    "2020 GENERAL ELECTION": "GN2011",
    "2020 SPECIAL HOUSE DISTRICT 49 GENERAL": "49GN20",
    "2020 SPECIAL HOUSE DISTRICT 49 RUNOFF": "49RO20",
    "2020 SPECIAL SENATE DISTRICT 26 PRIMARY": "26PR20",
    "2020 SPECIAL SENATE DISTRICT 26 RUNOFF": "26RO20",
    "2021 SPECIAL HOUSE DISTRICT 33 GENERAL": "33GN21",
    "2021 SPECIAL HOUSE DISTRICT 73 PRIMARY RUNOFF (4-2": "73RO21",  # )
    "2021 SPECIAL HOUSE DISTRICT 78 PRIMARY (5-25-2021)": "78PR21",
    "2021 SPECIAL SENATE DISTRICT 14 AND HOUSE DISTRICT": "1473GN",
    "2021 SPECIAL SENATE DISTRICT 26 GENERAL": "26GN21",
    "2022 PRIMARY RUNOFF ELECTION": "RO2206",
}


class Election:
    def __init__(self, row):
        self.code = row["Election Code"]
        self.type = row["Election Type"]
        self.name = row["Election Description/Name"]
        self.jurisdiction = row["Jurisdiction"]

        if row["Election Date"] in ("1/1/1800", "1/1/1801", "10/12/1888"):
            self.date = None
        else:
            self.date = datetime.strptime(
                row["Election Date"], "%Y-%m-%d %H:%M:%S"
            ).date()

    def __repr__(self):
        return f"<Election {self.code} ({self.name})>"

    @functools.cache
    @staticmethod
    def unknown(code):
        return Election(
            {
                "Election Code": code,
                "Election Type": "PRIMARY",
                "Election Description/Name": f"UNKNOWN ELECTION {code}",
                "Jurisdiction": "ALABAMA",
                "Election Date": "2024-01-01 00:00:00",
            }
        )

    @functools.cache
    @staticmethod
    def all():
        with open(ELECTIONS_FILE) as f:
            return [Election(x) for x in csv.DictReader(f)]

    @functools.cache
    @staticmethod
    def resolve(county, election):
        if election is None:
            return None

        election = election.strip().upper()
        if election in names_map:
            election = names_map[election]

        if len(election) == 6 and election.isnumeric():
            yy = int(election[:2])
            mm = int(election[2:4])
            dd = int(election[4:])

            if yy < 30:
                yy += 2000
            else:
                yy += 1900

            if yy < 2027 and 1 <= mm <= 12 and 1 <= dd <= 31:
                yymmdd = date(yy, mm, dd)

                elections = [e for e in Election.all() if e.date == yymmdd]

                if len(elections) == 1:
                    return elections[0]

                elections = [e for e in elections if e.jurisdiction != "ALABAMA"]

                if len(elections) >= 1:
                    return elections[0]

        elections = [
            e for e in Election.all() if e.code == election or e.name == election
        ]

        if len(elections) == 1:
            return elections[0]

        elections_orig = elections
        elections = [e for e in elections if e.jurisdiction == "ALABAMA"]

        if len(elections) == 1:
            return elections[0]

        elections = [e for e in elections_orig if e.jurisdiction == county.upper()]

        if len(elections) == 1:
            return elections[0]

        if not elections:
            if elections_orig:
                return elections_orig[0]

            print(f"NO ELECTIONS FOUND for {county=} {election=}")
            return Election.unknown(election)

        print(
            f"WARNING: multiple elections matched for {county=} {election=}: {elections=}"
        )
        return elections[0]


class Voter:
    def __init__(self, row):
        self.row = row

    def __getitem__(self, item):
        return self.row[item]

    @property
    @functools.cache
    def elections(self):
        elections = [
            (
                Election.resolve(self["County"], self[election] or None),
                self[party] or None,
            )
            for election, party in election_fields
        ]

        elections = [(x, y) for (x, y) in elections if x is not None]
        elections.sort(key=lambda k: k[0].date, reverse=True)  # type: ignore
        return elections

    @property
    @functools.cache
    def last_voted(self):
        if self.elections:
            return self.elections[0][0].date  # type: ignore

        return None

    @property
    @functools.cache
    def last_voted_party_code(self):
        r = {"REP": None, "DEM": None}

        for elec, code in self.elections:
            if code is None:
                continue

            code = code.strip()
            if code in r and r[code] is None:
                r[code] = elec.date  # type: ignore

        return r

    @property
    @functools.cache
    def last_voted_primary(self):
        for elec, _ in self.elections:
            if elec.type in ["PRIMARY"]:
                return elec.date

    @property
    @functools.cache
    def last_voted_runoff(self):
        for elec, _ in self.elections:
            if elec.type in ["PRIMARY RUN-OFF"]:
                return elec.date

    @property
    @functools.cache
    def last_voted_local(self):
        for elec, _ in self.elections:
            if elec.type in ["MUNICIPAL", "LOCAL", "SCHOOL"]:
                return elec.date

    @property
    @functools.cache
    def last_voted_special(self):
        for elec, _ in self.elections:
            if "SPECIAL" in elec.name:
                return elec.date

            if elec.type == "SPECIAL":
                return elec.date

    @functools.cache
    @staticmethod
    def all():
        with open(VOTER_FILE) as f:
            return [Voter(x) for x in csv.DictReader(f)]


def days_ago(x):
    if x is None:
        return float("inf")

    return (date.today() - x).days


def rule(voter):
    if days_ago(voter.last_voted) > (365 * 4):
        # last voted more than 4 years ago, e.g. didn't vote in the '22 or '24 elections
        return False

    if days_ago(voter.last_voted_party_code["DEM"]) > (365 * 8):
        # hasn't voted in a dem primary in more than 8 years
        return False

    if not voter.last_voted_special and not voter.last_voted_local:
        # engaged enough to vote in special or local elections
        return False

    return True


with open("targeting_data.csv", "w") as f:
    w = csv.writer(f)
    w.writerow(
        [
            "id",
            "voter_age",
            "gender",
            "registration_age",
            "last_voted",
            "last_dem",
            "last_rep",
            "last_primary",
            "last_runoff",
            "last_local",
            "last_special",
            "rule",
        ]
    )
    for v in Voter.all():
        registration_age = math.ceil(
            (
                date.today()
                - datetime.strptime(v["Date of Registration"], "%m/%d/%Y").date()
            ).days
            / 365
        )

        row = [
            v["Registrant ID"],
            v["Age"],
            v["Gender"],
            registration_age,
            v.last_voted,
            v.last_voted_party_code["DEM"],
            v.last_voted_party_code["REP"],
            v.last_voted_primary,
            v.last_voted_runoff,
            v.last_voted_local,
            v.last_voted_special,
            "Y" if rule(v) else "N",
        ]

        row = [str(x) if x else "" for x in row]

        w.writerow(row)

print("Wrote targeting_data.csv")

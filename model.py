from datetime import datetime
import os
from typing import Self, Sequence
from pydantic import BaseModel, Field

type ID = int


def timestamp() -> str:
    return datetime.now().strftime("%b %d %I:%M%P")


class Model(BaseModel):
    id_: ID | None = Field(None, alias="_id")
    created_by: str

    @property
    def id(self) -> ID:
        if self.id_ is None:
            raise AssertionError("no id set!!")
        return self.id_

    def with_id(self, id: ID) -> Self:
        return self.model_copy(update={"id_": id}, deep=True)

    def has_id(self) -> bool:
        return self.id_ is not None


class Note(BaseModel):
    note: str
    author: str | None = None  # username
    system: bool = False
    diffs: dict[str, tuple[str, str]] = {}  # field -> (old, new)
    dnc: bool = False
    ts: str = Field(default_factory=timestamp)


class Turf(Model):
    desc: str = ""
    phone_key: str = ""
    doors: list[ID] = []
    voters: list[ID] = []
    notes: list[Note] = []


class Door(Model):
    turf_id: ID | None = None
    address: str = ""
    unit: str = ""
    city: str = ""
    voters: list[ID] = []
    lat: float | None = None
    lon: float | None = None


class Voter(Model):
    door_id: ID | None = None
    turf_id: ID | None = None
    statevoterid: str = ""
    activeinactive: str = ""
    firstname: str = ""
    middlename: str = ""
    lastname: str = ""
    cellphone: str = ""
    landlinephone: str = ""
    gender: str = ""
    race: str = ""
    birthdate: str = ""
    regdate: str = ""
    notes: list[Note] = []
    phonebankturf: ID | None = None
    bestphone: str = ""


def is_valid_ordering(l: Sequence[Model]) -> bool:
    return all(m.id == idx for idx, m in enumerate(l))


class Database(BaseModel):
    turfs: list[Turf] = []
    doors: list[Door] = []
    voters: list[Voter] = []

    def get_voter_by_id(self, id: ID) -> Voter:
        return self.voters[id].model_copy(deep=True)

    def save_voter(self, voter: Voter) -> Voter:
        if voter.has_id():  # update voter
            voter_to_update = self.voters[voter.id]
            update_data = voter.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(voter_to_update, key, value)
            voter_result = voter_to_update

        elif not self.voters:  # first voter
            voter_result = voter.with_id(0)
            self.voters = [voter_result]

        else:  # new (not first) voter
            voter_result = voter.with_id(self.voters[-1].id)
            self.voters.append(voter_result)

        self.commit()
        return voter_result.model_copy(deep=True)

    def to_json(self):
        return self.model_dump_json(indent=4, by_alias=True)

    def commit(self):
        if any(
            not is_valid_ordering(ms) for ms in (self.turfs, self.doors, self.voters)
        ):
            raise AssertionError("frick!! tihs is a bug")

        with open("database-new.json", "w") as f:
            f.write(self.to_json())

        os.rename("database.json", f"database-{timestamp()}.json")
        os.rename("database-new.json", f"database.json")

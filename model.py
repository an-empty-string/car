from datetime import datetime
import os
from typing import Self, Sequence
from pydantic import BaseModel, Field

type ID = int

DATABASE_FILE = "database.json"
DATABASE_TMP_FILE = "database-new.json"


def timestamp() -> str:
    return datetime.now().strftime("%b %d %I:%M%P")


class Model(BaseModel):
    id_: ID | None = Field(default=None, alias="_id")
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


def is_valid_ordering(models: Sequence[Model]) -> bool:
    return all(m.id == idx for idx, m in enumerate(models))


class Database(BaseModel):
    turfs: list[Turf] = []
    doors: list[Door] = []
    voters: list[Voter] = []

    def get_voter_by_id(self, id: ID) -> Voter:
        return self.voters[id].model_copy(deep=True)

    def save_voter(self, voter: Voter, *, commit: bool = False) -> Voter:
        v = self._save_model(voter, self.voters)

        # if there's a door ID, add the voter to the door
        if v.door_id is not None and v.id not in self.doors[v.door_id].voters:
            self.doors[v.door_id].voters.append(v.id)

        # if there's a turf ID, add the voter to the turf
        if v.turf_id is not None and v.id not in self.turfs[v.turf_id].voters:
            self.turfs[v.turf_id].voters.append(v.id)

        if commit:
            self.commit()
        return v

    def get_door_by_id(self, id: ID) -> Door:
        return self.doors[id].model_copy(deep=True)

    def save_door(self, door: Door, *, commit: bool = False) -> Door:
        d = self._save_model(door, self.doors)

        # if there's a turf ID, add the door to the turf
        if d.turf_id is not None and d.id not in self.turfs[d.turf_id].doors:
            self.turfs[d.turf_id].doors.append(d.id)

        if commit:
            self.commit()
        return d

    def get_turf_by_id(self, id: ID) -> Turf:
        return self.turfs[id].model_copy(deep=True)

    def save_turf(self, turf: Turf, *, commit: bool = False) -> Turf:
        t = self._save_model(turf, self.turfs)

        if commit:
            self.commit()
        return t

    def _save_model[T: Model](self, m: T, collection: list[T]):
        if m.has_id():  # update existing
            model_to_update = collection[m.id]
            update_data = m.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(model_to_update, key, value)
            model_result = model_to_update

        elif not collection:  # first model
            model_result = m.with_id(0)
            collection.append(model_result)

        else:  # new (not first) model
            model_result = m.with_id(collection[-1].id + 1)
            collection.append(model_result)

        return model_result.model_copy(deep=True)

    def to_json(self):
        return self.model_dump_json(indent=4, by_alias=True)

    def commit(self):
        if any(
            not is_valid_ordering(ms) for ms in (self.turfs, self.doors, self.voters)
        ):
            raise AssertionError("frick!! tihs is a bug")

        with open(DATABASE_TMP_FILE, "w") as f:
            f.write(self.to_json())

        os.rename(DATABASE_FILE, f"database-{timestamp()}.json")
        os.rename(DATABASE_TMP_FILE, DATABASE_FILE)

import os
from collections.abc import Sequence
from datetime import datetime
from typing import Self, TypeIs, cast

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

    def to_dict(self):
        return self.model_dump(by_alias=True)


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


class _DoorWithGeoCode(Door):
    lat: float = 0  # type: ignore
    lon: float = 0  # type: ignore


def has_geocode(d: Door) -> TypeIs[_DoorWithGeoCode]:
    return d.lat is not None and d.lon is not None


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

        if commit:
            self.commit()
        return v

    def get_door_by_id(self, id: ID) -> Door:
        return self.doors[id].model_copy(deep=True)

    def save_door(self, door: Door, *, commit: bool = False) -> Door:
        d = self._save_model(door, self.doors)

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

    def _save_model[T: Model](self, m: T, collection: list[T]) -> T:
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

    def fixup_backrefs(self):
        def _fixup_one_backref_set[
            T: Model, U: Model
        ](
            children: list[T],
            child_id_list_attr: str,
            parents: list[U],
            parent_id_attr: str,
        ):
            # associate children with correct parents
            for child in children:
                parent_id: ID | None = getattr(child, parent_id_attr)
                if parent_id is None:
                    continue

                parent = parents[parent_id]
                child_id_list = getattr(parent, child_id_list_attr)
                if child.id not in child_id_list:
                    child_id_list.append(child.id)

            # remove children from incorrect parents
            for parent in parents:
                maybe_children = getattr(parent, child_id_list_attr)
                for child_id in maybe_children.copy():
                    if (
                        getattr(children[cast(ID, child_id)], parent_id_attr)
                        != parent.id
                    ):
                        maybe_children.remove(child_id)

        _fixup_one_backref_set(self.voters, "voters", self.doors, "door_id")
        _fixup_one_backref_set(self.voters, "voters", self.turfs, "turf_id")
        _fixup_one_backref_set(self.doors, "doors", self.turfs, "turf_id")

    def commit(self, backup: bool = True):
        if any(
            not is_valid_ordering(ms) for ms in (self.turfs, self.doors, self.voters)
        ):
            raise AssertionError("frick!! tihs is a bug")

        self.fixup_backrefs()

        with open(DATABASE_TMP_FILE, "w") as f:
            f.write(self.to_json())

        if backup:
            os.rename(DATABASE_FILE, f"database-{datetime.now().isoformat()}.json")

        os.rename(DATABASE_TMP_FILE, DATABASE_FILE)

    @classmethod
    def load(cls):
        with open(DATABASE_FILE) as f:
            return cls.model_validate_json(f.read())

import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, ClassVar, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeIs

type ID = int


def timestamp() -> str:
    return datetime.now().strftime("%b %d %I:%M%P")


type DatabaseType = Literal["turf", "door", "voter"]


def is_valid_type(typ: str) -> TypeIs[DatabaseType]:
    return typ in {"turf", "door", "voter"}


class BaseDatabase(BaseModel):
    DATABASE_FILE_NAME: ClassVar[str]
    _INSTANCE: ClassVar[Self]

    def assert_constraints(self):
        pass

    def fixup_backrefs(self):
        pass

    @classmethod
    def db_file(cls):
        return f"{cls.DATABASE_FILE_NAME}.json"

    @classmethod
    def db_temp_file(cls):
        return f"{cls.DATABASE_FILE_NAME}-new.json"

    @classmethod
    def db_commit_file(cls):
        return f"{cls.DATABASE_FILE_NAME}-{datetime.now().isoformat()}.json"

    def commit(self, backup: bool = True):
        self.assert_constraints()
        self.fixup_backrefs()

        with open(self.db_temp_file(), "w") as f:
            f.write(self.to_json())

        if backup:
            os.rename(self.db_file(), self.db_commit_file())

        os.rename(self.db_temp_file(), self.db_file())

    @classmethod
    def get(cls) -> Self:
        try:
            return cls._INSTANCE
        except AttributeError:
            cls._INSTANCE = cls._load()
            return cls._INSTANCE

    @classmethod
    def _load(cls) -> Self:
        with open(cls.db_file()) as f:
            return cls.model_validate_json(f.read())


class Note(BaseModel):
    model_config = ConfigDict(frozen=True)

    note: str
    author: str | None = None  # username
    system: bool = False
    diffs: Mapping[str, tuple[Any, Any]] = {}  # field -> (old, new)
    dnc: bool = False
    ts: str = Field(default_factory=timestamp)


class NoteDatabase(BaseDatabase):
    DATABASE_FILE_NAME: ClassVar[str] = "note-database"

    turf: dict[ID, list[Note]] = {}
    door: dict[ID, list[Note]] = {}
    voter: dict[ID, list[Note]] = {}

    def by_type_and_id(self, typ: DatabaseType, id_: ID) -> Sequence[Note]:
        """We explicitly return a Sequence instead of a list
        for immutability without copying to a tuple"""
        return getattr(self, typ)[id_]

    def add(self, typ: DatabaseType, id_: ID, note: Note):
        getattr(self, typ)[id_].insert(0, note)


class Model(BaseModel):
    TYPE: ClassVar[DatabaseType]
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

    @property
    def notes(self) -> list[Note]:
        return NoteDatabase.get().by_type_and_id(self.TYPE, self.id)

    def add_note(self, note: Note):
        NoteDatabase.get().add(self.TYPE, self.id, note)


class Turf(Model):
    TYPE: ClassVar[DatabaseType] = "turf"

    desc: str = ""
    phone_key: str = ""
    doors: list[ID] = []
    voters: list[ID] = []


class Door(Model):
    TYPE: ClassVar[DatabaseType] = "door"

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
    TYPE: ClassVar[DatabaseType] = "voter"

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
    phonebankturf: ID | None = None
    bestphone: str = ""


def is_valid_ordering(models: Sequence[Model]) -> bool:
    return all(m.id == idx for idx, m in enumerate(models))


class Database(BaseDatabase):
    DATABASE_FILE_NAME: ClassVar[str] = "database"

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

    def add_notes_for_id(
        self, typ: DatabaseType, id: ID, *notes: Note, commit: bool = False
    ):
        obj: Model
        match typ:
            case "turf":
                obj = self.turfs[id]
            case "door":
                obj = self.doors[id]
            case "voter":
                obj = self.voters[id]
        obj.notes = [*(note.model_copy(deep=True) for note in notes), *obj.notes]
        if commit:
            self.commit()

    def _save_model[T: Model](self, m: T, collection: list[T]) -> T:
        if m.has_id():  # update existing
            model_to_update = collection[m.id]
            for field in m.model_fields_set:
                setattr(model_to_update, field, getattr(m, field))

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

    def assert_constraints(self):
        if any(
            not is_valid_ordering(ms) for ms in (self.turfs, self.doors, self.voters)
        ):
            raise AssertionError("frick!! tihs is a bug")

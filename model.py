import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, ClassVar, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeIs

type ID = int
type Disposition = (
    Literal[
        "attempted",
        "refused",
        "do-not-contact",
        "followup",
        "in-progress",
        "done",
    ]
    | None
)

DISPOSITIONS = {
    None: "-",
    "attempted": "Attempted, voter not reached",
    "refused": "Voter refused conversation",
    "do-not-contact": "Marked as do-not-contact",
    "followup": "Flagged for follow-up",
    "in-progress": "In progress",
    "done": "Done",
}
TYPE_DISPOSITIONS = {
    "door": [None, "attempted"],
    "voter": [None, "refused", "do-not-contact", "followup", "done"],
    "turf": [None, "in-progress", "done"],
}


def is_valid_disposition(x: str | None) -> TypeIs[Disposition]:
    return x in DISPOSITIONS


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


type DatabaseType = Literal["turf", "door", "voter"]


def is_valid_type(typ: str) -> TypeIs[DatabaseType]:
    return typ in {"turf", "door", "voter"}


class BaseDatabase(BaseModel):
    DATABASE_FILE_NAME: ClassVar[str]
    SHOULD_CREATE: ClassVar[bool] = False
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

    def to_json(self):
        return self.model_dump_json(indent=4, by_alias=True)

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
        file = cls.db_file()
        if cls.SHOULD_CREATE and not os.path.exists(file):
            empty = "{}"
            with open(file, "w") as f:
                f.write(empty)
            return cls.model_validate_json(empty)
        with open(cls.db_file()) as f:
            return cls.model_validate_json(f.read())


class Note(BaseModel):
    model_config = ConfigDict(frozen=True)

    note: str
    author: str | None = None  # username
    system: bool = False
    diffs: Mapping[str, tuple[Any, Any]] = {}  # field -> (old, new)
    disposition: Disposition = None
    ts: str = Field(default_factory=timestamp)

    def has_refusal_disposition(self):
        return self.disposition in (
            "refused",
            "do-not-contact",
        )


class NoteDatabase(BaseDatabase):
    DATABASE_FILE_NAME: ClassVar[str] = "note-database"
    SHOULD_CREATE: ClassVar[bool] = True

    turf: defaultdict[ID, list[Note]] = defaultdict(list)
    door: defaultdict[ID, list[Note]] = defaultdict(list)
    voter: defaultdict[ID, list[Note]] = defaultdict(list)

    def by_type_and_id(self, typ: DatabaseType, id: ID) -> Sequence[Note]:
        """We explicitly return a Sequence instead of a list
        for immutability without copying to a tuple"""
        return getattr(self, typ)[id]

    def add(self, typ: DatabaseType, id: ID, note: Note):
        getattr(self, typ)[id].insert(0, note)


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

    def last_disposition(
        self, after: str | None = None, default: Disposition = None
    ) -> Disposition:
        notes = [n for n in self.notes if n.disposition is not None]
        if after is not None:
            notes = [n for n in notes if (n.ts > after or n.has_refusal_disposition())]

        if notes:
            return notes[-1].disposition

        return default

    def to_dict(self):
        return self.model_dump(by_alias=True)

    @property
    def notes(self) -> Sequence[Note]:
        return NoteDatabase.get().by_type_and_id(self.TYPE, self.id)

    def add_note(self, note: Note, *, commit: bool = False):
        db = NoteDatabase.get()
        db.add(self.TYPE, self.id, note)
        if commit:
            db.commit()


class Turf(Model):
    TYPE: ClassVar[DatabaseType] = "turf"

    desc: str = ""
    phone_key: str = ""
    doors: list[ID] = []
    voters: list[ID] = []

    def started_at(self) -> str | None:
        for note in reversed(self.notes):
            if note.disposition == "in-progress":
                return note.ts


class Door(Model):
    TYPE: ClassVar[DatabaseType] = "door"

    turf_id: ID | None = None
    address: str = ""
    unit: str = ""
    city: str = ""
    voters: list[ID] = []
    lat: float | None = None
    lon: float | None = None

    def last_disposition_with_voters(
        self, voters: list["Voter"], after=None
    ) -> Disposition:
        for voter in voters:
            if disposition := voter.last_disposition(after):
                if disposition == "followup":
                    return "done"

                return disposition

        if self.last_disposition(after) == "attempted":
            return "attempted"

        return None


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

    def get_by_type_and_id(self, typ: DatabaseType, id: ID) -> Model:
        return getattr(self, typ + "s")[id].model_copy(deep=True)

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

    def get_disposition_for_type_and_id(
        self, typ: DatabaseType, id: ID, turf: Turf | None = None
    ) -> Disposition:
        after = None
        if turf:
            after = turf.started_at()

        match typ:
            case "turf":
                return self.get_turf_by_id(id).last_disposition()
            case "door":
                door = self.get_door_by_id(id)
                voters = [self.get_voter_by_id(v_id) for v_id in door.voters]

                return door.last_disposition_with_voters(voters, after)
            case "voter":
                voter = self.get_voter_by_id(id)
                return voter.last_disposition(after)

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

    def fixup_backrefs(self):
        def _fixup_one_backref_set[T: Model, U: Model](
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

# stdlib
import os
import secrets
from collections.abc import Callable
from typing import Any, cast

# 3p
from flask import Flask, abort, g, redirect, render_template, request, session, url_for

# project
from model import ID, Database, Door, Model, Note, Turf, Voter, is_valid_type

app = Flask(__name__)

if not os.path.exists("secret_key.txt"):
    with open("secret_key.txt", "w") as f:
        f.write(secrets.token_hex())

with open("secret_key.txt") as f:
    app.secret_key = f.read()

if not os.path.exists("password.txt"):
    with open("password.txt", "w") as f:
        f.write("e")

with open("password.txt") as f:
    password = f.read().strip()


@app.before_request
def before_request():
    g.phonebank = False
    if session.get("phonebank"):
        g.phonebank = True

    c = session.get("canvasser")
    if c:
        g.canvasser = c
    elif request.endpoint not in {"login", "static"}:
        if "favicon" in request.url:
            abort(404)

        session["return_to"] = request.url
        return redirect(url_for("login"))


@app.route("/login/", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    if request.form.get("password") != password:
        return "wrong password, <a href=/login>try again</a>"

    session["canvasser"] = request.form.get("canvasser")
    return redirect(session.pop("return_to", "/"))


db = Database.get()


@app.context_processor
def inject_database():
    return {"db": db}


@app.context_processor
def inject_data_2() -> dict[str, Callable[..., Any]]:
    return {"is_dnc": is_dnc, "reformat_phone": reformat_phone, "tel_uri": tel_uri}


def is_dnc(v: Voter):
    return any(note.dnc for note in v.notes)


def reformat_phone(k: str) -> str:
    k = "".join([i for i in k if i.isnumeric()])
    return f"({k[:3]}) {k[3:6]}-{k[6:]}"


def tel_uri(k: str, tel: str = "tel") -> str:
    k = "".join([i for i in k if i.isnumeric()])
    return f"{tel}:+1{k[:10]}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/phonebank/")
def phonebank_index():
    return render_template("index.html")


@app.route("/phonebank_toggle/")
def phonebank_toggle():
    if "phonebank" in session:
        del session["phonebank"]
    else:
        session["phonebank"] = 1

    return redirect(request.args.get("return", "/"))


@app.route("/map_toggle/")
def map_toggle():
    if "use_map" in session:
        del session["use_map"]
    else:
        session["use_map"] = 0

    return redirect(request.args.get("return", "/"))


@app.route("/turf/<int:id>/")
def show_turf(id: ID):
    turf = db.get_turf_by_id(id)

    if not turf.phone_key:
        geodoors: list[dict[str, Any]] = []
        for door_id in turf.doors:
            door = db.get_door_by_id(door_id)
            geodoors.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [door.lon, door.lat],
                    },
                    "properties": {
                        "address": door.address,
                        "unit": door.unit,
                        "n_voters": len(door.voters),
                        "url": url_for("show_door", id=door.id),
                    },
                }
            )

        return render_template(
            "turf.html",
            turf=turf,
            geodoors={
                "type": "FeatureCollection",
                "crs": {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
                },
                "features": geodoors,
            },
        )

    voters = list(map(db.get_voter_by_id, turf.voters))
    # voters = [v for v in voters if phone_key in v and v[phone_key]]
    # voters.sort(key=lambda v: reformat_phone(v[phone_key]))

    return render_template("phonebank_turf.html", turf=turf, tvoters=voters)


@app.route("/door/<int:id>/")
def show_door(id: ID):
    door = db.get_door_by_id(id)
    if door.turf_id is None:
        return "no turf associated with door"
    turf_doors = db.get_turf_by_id(door.turf_id).doors
    idx = turf_doors.index(id)
    prev_door_id = next_door_id = None

    if idx > 0:
        prev_door_id = turf_doors[idx - 1]
    if idx + 1 < len(turf_doors):
        next_door_id = turf_doors[idx + 1]

    return render_template(
        "door.html",
        door=door,
        prev_door_id=prev_door_id,
        next_door_id=next_door_id,
    )


@app.route("/door/<int:id>/contact/")
def new_door_contact(id: ID):
    door = db.get_door_by_id(id)
    new_voter = db.save_voter(
        Voter(
            created_by=g.canvasser,
            firstname="New",
            lastname="Voter",
            door_id=id,
            turf_id=door.turf_id,
        ),
        commit=True,
    )
    new_voter.add_note(
        Note(author=g.canvasser, system=True, note="created the voter"), commit=True
    )

    return redirect(url_for("edit_voter", id=new_voter.id))


@app.route("/voter/<int:id>/")
def show_voter(id: ID):
    voter = db.get_voter_by_id(id)

    prev_voter_id = next_voter_id = None
    if g.phonebank and voter.phonebankturf is not None:
        turf_voters = db.get_turf_by_id(voter.phonebankturf).voters
        idx = turf_voters.index(id)
        if idx > 0:
            prev_voter_id = turf_voters[idx - 1]
        if idx + 1 < len(turf_voters):
            next_voter_id = turf_voters[idx + 1]

    return render_template(
        "voter.html",
        voter=voter,
        dnc=is_dnc(voter),
        phonebank=True,
        prev_voter_id=prev_voter_id,
        next_voter_id=next_voter_id,
    )


def thing_title(model: Model) -> str:
    if model.TYPE == "turf":
        return cast(Turf, model).desc
    elif model.TYPE == "door":
        return cast(Door, model).address
    elif model.TYPE == "voter":
        v = cast(Voter, model)
        return f"{v.firstname} {v.middlename} {v.lastname}"
    else:
        return "frick!! tihs is a bug"


@app.route("/<typ>/<int:id>/note/", methods=["GET", "POST"])
def note_obj(typ: str, id: ID):
    assert is_valid_type(typ)
    obj = db.get_by_type_and_id(typ, id)
    if request.method == "GET":
        return render_template(
            "take_note.html",
            typ=typ,
            title=thing_title(obj),
            link=url_for(f"show_{typ}", id=id),
        )

    elif request.method == "POST":
        note = Note(
            author=g.canvasser,
            note=request.form.get("note", ""),
            dnc=bool(request.form.get("dnc")),
        )
        obj.add_note(note, commit=True)
        return redirect(url_for(f"show_{typ}", id=id))
    return "invalid method"


@app.route("/voter/<int:id>/edit/", methods=["GET", "POST"])
def edit_voter(id: ID):
    voter = db.get_voter_by_id(id)

    if request.method == "GET":
        return render_template(
            "edit_voter.html",
            voter=voter,
        )

    elif request.method == "POST":
        diffs: dict[str, tuple[str, str | None]] = {
            field: (value, new)
            for field, value in voter.to_dict().items()
            if (new := request.form.get(field)) != value
            and new is not None
            and field not in ("notes",)
        }

        if diffs:
            updated_voter = db.save_voter(
                voter.model_copy(
                    update={field: new for field, (_, new) in diffs.items()}
                ),
                commit=True,
            )
            note = " ".join(
                f"changed {field} from {old!r} to {new!r}."
                for field, (old, new) in diffs.items()
            )
            updated_voter.add_note(
                Note(
                    author=g.canvasser,
                    system=True,
                    note=note,
                    diffs=diffs,
                    dnc=False,
                ),
                commit=True,
            )

    return redirect(url_for("show_voter", id=id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3030, debug=True)

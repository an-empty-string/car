# stdlib
import json
import os
import secrets
from collections.abc import Callable
from typing import Any, cast

# 3p
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# project
from . import utils
from .model import (
    DATA_ROOT,
    DISPOSITIONS,
    ID,
    TYPE_DISPOSITIONS,
    Database,
    Door,
    Model,
    Note,
    Turf,
    Voter,
    is_valid_disposition,
    is_valid_type,
)

app = Flask(__name__)

os.chdir(DATA_ROOT)

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

geoturfs = {}
if os.path.exists("turfs.geojson"):
    with open("turfs.geojson") as f:
        geoturfs = json.load(f)


@app.before_request
def before_request():
    g.phonebank = False
    if session.get("phonebank"):
        g.phonebank = True

    c = session.get("canvasser")
    if c:
        g.canvasser = c
    elif request.endpoint not in {"login", "static"} and not request.path.startswith(
        "/login/"
    ):
        if "favicon" in request.url:
            abort(404)

        session["return_to"] = request.url
        return redirect(url_for("login"))


def restrict_turfs(turf_id):
    if "canvasser" not in session:
        abort(403)

    if session["admin"]:
        return

    if turf_id in session["turfs"]:
        return

    abort(403)


def restrict_voter_turfs(voter):
    if g.phonebank:
        restrict_turfs(voter.phonebankturf)
    else:
        restrict_turfs(voter.turf_id)


@app.route("/login/", methods=["GET", "POST"])
@app.route("/login/<login_code>/", methods=["GET"])
def login(login_code=None):
    if request.method == "GET":
        # Allow logins by URL immediately if we are already logged in
        if login_code is not None or "canvasser" not in session:
            return render_template("login.html", login_code=login_code)

        pw = login_code

    else:
        pw = request.form.get("password")
        if pw is None:
            abort(400)

        pw = pw.strip()

    session["admin"] = False

    if request.form.get("password") == password:
        # Used the admin password
        session["admin"] = True
        session["turfs"] = []

    else:
        # Try finding the turf by login code
        if pw is None:
            pw = ""
        else:
            pw = "".join([i for i in pw if i.isnumeric()])

        for turf in db.turfs:
            if turf.login_code == pw:
                break

        else:
            flash("No such turf code! Try again.")
            return render_template("login.html")

        if "turfs" not in session:
            session["turfs"] = []

        if turf.id not in session["turfs"]:
            session["turfs"].append(turf.id)
            flash(f"Added turf {turf.desc}!")

        else:
            flash("Turf already on list.")

    if "canvasser" not in session:
        session["canvasser"] = request.form.get("canvasser")

    return redirect(session.pop("return_to", "/"))


@app.route("/logout/")
def logout():
    session.clear()

    flash("Logged out!")
    return redirect(url_for("login"))


db = Database.get()


@app.context_processor
def inject_database():
    return {"db": db}


@app.context_processor
def inject_funcs() -> dict[str, Callable[..., Any]]:
    return {
        "reformat_phone": reformat_phone,
        "tel_uri": tel_uri,
        "time_taken": utils.time_taken,
    }


@app.context_processor
def inject_constants() -> dict[str, Any]:
    return {
        "dispositions": DISPOSITIONS,
        "type_dispositions": TYPE_DISPOSITIONS,
    }


def reformat_phone(k: str) -> str:
    k = "".join([i for i in k if i.isnumeric()])
    return f"({k[:3]}) {k[3:6]}-{k[6:]}"


def tel_uri(k: str, tel: str = "tel") -> str:
    k = "".join([i for i in k if i.isnumeric()])
    return f"{tel}:+1{k[:10]}"


@app.route("/")
def index():
    if not session["admin"] and len(session["turfs"]) == 1:
        return redirect(url_for("show_turf", id=session["turfs"][0]))

    return render_template(
        "index.html",
        geoturfs=geoturfs,
        turf_data=[
            {
                "visible": t.visible,
                "doors": len(t.doors),
                "voters": len(t.voters),
                "disposition": t.last_disposition(),
                "disposition_name": DISPOSITIONS[t.last_disposition()],
            }
            for t in db.turfs
        ],
    )


@app.route("/phonebank/")
def phonebank_index():
    return render_template("index.html", geoturfs={})


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
    restrict_turfs(id)

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


@app.route("/turf/<int:id>/start/")
def start_turf(id):
    restrict_turfs(id)

    turf = db.get_turf_by_id(id)
    turf.add_note(
        Note(
            author=g.canvasser,
            system=True,
            note="started the turf",
            disposition="in-progress",
        ),
        commit=True,
    )

    return redirect(url_for("show_turf", id=id))


@app.route("/turf/<int:id>/finish/")
def finish_turf(id):
    restrict_turfs(id)

    turf = db.get_turf_by_id(id)
    turf.add_note(
        Note(
            author=g.canvasser,
            system=True,
            note="finished the turf",
            disposition="done",
        ),
        commit=True,
    )

    return redirect(url_for("show_turf", id=id))


@app.route("/door/<int:id>/")
def show_door(id: ID):
    door = db.get_door_by_id(id)
    if door.turf_id is None:
        return "no turf associated with door"

    restrict_turfs(door.turf_id)

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

    restrict_turfs(door.turf_id)

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


@app.route("/door/<int:id>/attempted/")
def door_attempt(id: ID):
    door = db.get_door_by_id(id)

    restrict_turfs(door.turf_id)

    door.add_note(
        Note(
            author=g.canvasser,
            system=True,
            disposition="attempted",
            note="knocked, no response",
        ),
        commit=True,
    )

    return redirect(url_for("show_door", id=id))


@app.route("/door/<int:id>/do-not-knock/")
def door_dnk(id: ID):
    door = db.get_door_by_id(id)

    restrict_turfs(door.turf_id)

    door.add_note(
        Note(
            author=g.canvasser,
            system=True,
            disposition="do-not-contact",
            note="marked do-not-knock",
        ),
        commit=True,
    )

    return redirect(url_for("show_door", id=id))


@app.route("/voter/<int:id>/")
def show_voter(id: ID):
    voter = db.get_voter_by_id(id)

    restrict_voter_turfs(voter)

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

    return "(no title)"


@app.route("/<typ>/<int:id>/note/", methods=["GET", "POST"])
def note_obj(typ: str, id: ID):
    if typ == "turf":
        restrict_turfs(id)
    elif typ == "door":
        restrict_turfs(db.get_door_by_id(id).turf_id)
    elif typ == "voter":
        restrict_voter_turfs(db.get_voter_by_id(id))
    # FIXME turf restriction

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
        disposition = request.form.get("disposition")
        if not is_valid_disposition(disposition):
            abort(400)

        note = Note(
            author=g.canvasser,
            note=request.form.get("note", ""),
            disposition=disposition,
        )
        obj.add_note(note, commit=True)
        return redirect(url_for(f"show_{typ}", id=id))
    return "invalid method"


@app.route("/voter/<int:id>/edit/", methods=["GET", "POST"])
def edit_voter(id: ID):
    voter = db.get_voter_by_id(id)

    restrict_voter_turfs(voter)

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
                ),
                commit=True,
            )

    return redirect(url_for("show_voter", id=id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3030, debug=True)

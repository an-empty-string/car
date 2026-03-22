# stdlib
import itertools
import json
import os
import random
import secrets
import time
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
    NoteDatabase,
    Turf,
    Voter,
    is_valid_disposition,
    is_valid_type,
)

PHONEBANK_MIN_DELAY = 60 * 15

app = Flask(__name__)
cache = utils.MemoryCache()

os.chdir(DATA_ROOT)

if not os.path.exists("secret_key.txt"):
    with open("secret_key.txt", "w") as f:
        f.write(secrets.token_hex())

with open("secret_key.txt") as f:
    app.secret_key = f.read()

if not (password := os.getenv("CAR_ADMIN_PASSWORD")):
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


def restrict_admin():
    if session["admin"]:
        return

    abort(403)


def restrict_voter_turfs(voter):
    if g.phonebank:
        if voter.id == session["chosen_voter"]:
            return

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
            if request.method == "POST":
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
note_db = NoteDatabase.get()


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


def is_phone(k: str):
    return len([i for i in k if i.isnumeric()]) > 7


@app.route("/")
def index():
    if not session["admin"] and len(session["turfs"]) == 1:
        return redirect(url_for("show_turf", id=session["turfs"][0]))

    if session["admin"]:
        my_geoturfs = geoturfs
    else:
        my_geoturfs = geoturfs.copy()
        my_geoturfs["features"] = [
            x
            for x in my_geoturfs["features"]
            if x["properties"]["car_id"] in session["turfs"]
        ]

    return render_template(
        "index.html",
        geoturfs=my_geoturfs,
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


@app.route("/map_toggle/")
def map_toggle():
    if "use_map" in session:
        del session["use_map"]
    else:
        session["use_map"] = 0

    return redirect(request.args.get("return", "/"))


@app.route("/autolink_toggle/")
def autolink_toggle():
    if "autolink" in session:
        del session["autolink"]
    else:
        session["autolink"] = 0

    return redirect(request.args.get("return", "/"))


@app.route("/turf/<int:id>/")
def show_turf(id: ID):
    restrict_turfs(id)
    session["last_turf"] = id

    turf = db.get_turf_by_id(id)

    if turf.phone_key:
        session["phonebank"] = True
        session["phonebank_turf"] = turf.id
        return redirect(url_for("phonebank_next_voter", turf_id=id))

    else:
        session["phonebank"] = False

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

    pretty_ordered_doors = itertools.groupby(
        sorted([db.get_door_by_id(d) for d in turf.doors], key=lambda d: d.sort_key()),
        key=lambda d: d.print_order_key(),
    )

    return render_template(
        "turf.html",
        turf=turf,
        pretty_ordered_doors=pretty_ordered_doors,
        geodoors={
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            },
            "features": geodoors,
        },
    )


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

    return redirect(url_for("edit_voter", id=new_voter.id, names_only=True))


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

    return render_template(
        "voter.html",
        voter=voter,
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
        if disposition == "None":
            disposition = None

        if disposition is not None and not is_valid_disposition(disposition):
            abort(400)

        note_text = request.form.get("note", "")
        if g.phonebank:
            note_text += " (phonebank)"

        note = Note(
            author=g.canvasser,
            note=note_text,
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
            "edit_voter.html", voter=voter, names_only=request.args.get("names_only")
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


@app.route("/next/<int:turf_id>/")
def phonebank_next_voter(turf_id):
    restrict_turfs(turf_id)
    turf = db.get_turf_by_id(turf_id)

    if not turf.phone_key:
        return redirect(url_for("show_turf", id=turf_id))

    # all voters in turf
    sample = random.sample(turf.voters, len(turf.voters))
    for voter_id in sample:
        last_seen = cache.get(f"last_seen_{voter_id}")
        if last_seen is not None and time.time() - last_seen < PHONEBANK_MIN_DELAY:
            continue

        voter = db.get_voter_by_id(voter_id)

        # don't phonebank anyone who we've conversed with before
        # TODO - use the phone_key to decide config
        if voter.notes:
            continue

        # don't phonebank... you know, anyone without a phone...
        # TODO - use phone_key=textbank to check SMS instead
        if not is_phone(voter.bestphone):
            continue

        session["chosen_voter"] = voter_id
        cache.set(f"last_seen_{voter_id}", time.time())
        return redirect(url_for("show_voter", id=voter_id))

    flash("No voters to contact in this phonebank.")
    if not session["admin"] and len(session["turfs"]) == 1:
        session["turfs"] = []
        return redirect(url_for("login"))

    return redirect(url_for("index"))


@app.route("/activity_feed/")
def activity_feed():
    restrict_admin()

    ns = []

    filter_disposition = request.args.get("disposition")

    for voter_id, notes in note_db.voter.items():
        voter = db.get_voter_by_note_id(voter_id)
        for note in notes:
            if (
                filter_disposition is not None
                and note.disposition != filter_disposition
            ):
                continue

            ns.append((note.ts, note, voter) + voter.last_disposition_with_note())

    ns.sort(reverse=True)

    return render_template("activity_feed.html", ns=ns)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3030, debug=True)

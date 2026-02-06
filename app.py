import datetime
import json
import os
import secrets

from flask import (
    Flask,
    abort,
    g,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

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


with open("database.json") as f:
    data = json.load(f)


def save_data():
    with open("database-new.json", "w") as f:
        json.dump(data, f)

    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    os.rename("database.json", f"database-{ts}.json")
    os.rename("database-new.json", f"database.json")


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


@app.context_processor
def inject_data():
    return data


@app.context_processor
def inject_data_2():
    return {"is_dnc": is_dnc, "reformat_phone": reformat_phone, "tel_uri": tel_uri}


def is_dnc(v):
    for note in v["notes"]:
        if note["dnc"]:
            return True

    return False


def reformat_phone(k):
    k = "".join([i for i in k if i.isnumeric()])
    return f"({k[:3]}) {k[3:6]}-{k[6:]}"


def tel_uri(k, tel="tel"):
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
def show_turf(id):
    turf = data["turfs"][id]

    phone_key = turf.get("phone_key")

    if not phone_key:
        geodoors = []
        for door_id in turf["doors"]:
            door = data["doors"][door_id]
            geodoors.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [door["lon"], door["lat"]],
                    },
                    "properties": {
                        "address": door["address"],
                        "unit": door["unit"],
                        "n_voters": len(door["voters"]),
                        "url": url_for("show_door", id=door["_id"]),
                    },
                }
            )

        geodoors = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            },
            "features": geodoors,
        }

        return render_template("turf.html", turf=turf, geodoors=geodoors)

    voters = [data["voters"][i] for i in turf["voters"]]
    # voters = [v for v in voters if phone_key in v and v[phone_key]]
    # voters.sort(key=lambda v: reformat_phone(v[phone_key]))

    return render_template("phonebank_turf.html", turf=turf, tvoters=voters)


@app.route("/door/<int:id>/")
def show_door(id):
    door = data["doors"][id]

    turf_doors = data["turfs"][door["turf_id"]]["doors"]
    idx = turf_doors.index(id)
    prev_door_id = next_door_id = None

    if idx > 0:
        prev_door_id = turf_doors[idx - 1]
    if idx + 1 < len(turf_doors):
        next_door_id = turf_doors[idx + 1]

    return render_template(
        "door.html", door=door, prev_door_id=prev_door_id, next_door_id=next_door_id
    )


@app.route("/door/<int:id>/contact/")
def new_door_contact(id):
    door = data["doors"][id]

    new_voter = {
        "statevoterid": "",
        "activeinactive": "",
        "firstname": "New",
        "middlename": "",
        "lastname": "Voter",
        "cellphone": "",
        "landlinephone": "",
        "bestphone": "",
        "gender": "",
        "race": "",
        "birthdate": "",
        "regdate": "",
        "_id": len(data["voters"]),
        "notes": [
            {
                "ts": datetime.datetime.now().strftime("%b %d %I:%M%P"),
                "author": g.canvasser,
                "system": True,
                "note": "created the voter",
                "dnc": False,
            },
        ],
        "created_by": g.canvasser,
        "door_id": id,
        "turf_id": door["turf_id"],
    }
    data["voters"].append(new_voter)
    data["turfs"][new_voter["turf_id"]]["voters"].append(new_voter["_id"])
    data["doors"][id]["voters"].append(new_voter["_id"])
    save_data()

    return redirect(url_for("edit_voter", id=new_voter["_id"]))


@app.route("/voter/<int:id>/")
def show_voter(id):
    voter = data["voters"][id]

    prev_voter_id = next_voter_id = None
    if g.phonebank and "phonebank_turf_id" in voter:
        turf_voters = data["turfs"][voter["phonebank_turf_id"]]["voters"]
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


def thing_title(obj, id):
    if obj == "turf":
        return data["turfs"][id]["desc"]
    elif obj == "door":
        return data["doors"][id]["address"]
    elif obj == "voter":
        v = data["voters"][id]
        return "{firstname} {middlename} {lastname}".format(**v)
    else:
        return "frick!! tihs is a bug"


@app.route("/<typ>/<int:id>/note/", methods=["GET", "POST"])
def note_obj(typ, id):
    assert typ in ["turf", "door", "voter"]
    obj = data[typ + "s"][id]
    if request.method == "GET":
        return render_template(
            "take_note.html",
            typ=typ,
            title=thing_title(typ, id),
            link=url_for(f"show_{typ}", id=id),
        )

    elif request.method == "POST":
        obj["notes"].insert(
            0,
            {
                "ts": datetime.datetime.now().strftime("%b %d %I:%M%P"),
                "system": False,
                "author": g.canvasser,
                "note": request.form.get("note"),
                "dnc": True if request.form.get("dnc") else False,
            },
        )
        save_data()
        return redirect(url_for(f"show_{typ}", id=id))


@app.route("/voter/<int:id>/edit/", methods=["GET", "POST"])
def edit_voter(id):
    voter = data["voters"][id]

    if request.method == "GET":
        return render_template(
            "edit_voter.html",
            voter=voter,
        )

    elif request.method == "POST":
        diffs = []
        for (
            field
        ) in "activeinactive firstname middlename lastname cellphone landlinephone bestphone gender race birthdate".split():
            new = request.form.get(field)
            if voter[field] != new:
                diffs.append((field, voter[field], new))
                voter[field] = new

        if diffs:
            rdiffs = {}
            text = []
            for field, old, new in diffs:
                rdiffs[field] = [old, new]
                text.append(f"changed {field} from {old!r} to {new!r}.")

            voter["notes"].insert(
                0,
                {
                    "ts": datetime.datetime.now().strftime("%b %d %I:%M%P"),
                    "author": g.canvasser,
                    "system": True,
                    "note": " ".join(text),
                    "diffs": rdiffs,
                    "dnc": False,
                },
            )
            save_data()

    return redirect(url_for(f"show_voter", id=id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3030, debug=True)

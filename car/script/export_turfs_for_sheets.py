from ..model import Database

db = Database.get()

# car ID	Name	# Doors	Login Code	car Status
for turf in db.turfs:
    fields = [
        turf.id,
        turf.desc,
        len(turf.doors),
        turf.login_code[:5] + " " + turf.login_code[5:],
        turf.last_disposition(),
    ]

    print("\t".join([str(i) for i in fields]))

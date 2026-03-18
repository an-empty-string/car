from ..model import Turf
from .update_voter_turfs import assign_login_codes, database

turf = Turf(
    desc="All Voters",
    created_by="system",
    phone_key="default",
)
turf = database.save_turf(turf)

turf.voters = [v.id for v in database.voters]
turf = database.save_turf(turf)

assign_login_codes()

database.commit()

import collections
import functools

from .app import db

phone_keys = ["cellphone", "landlinephone", "bestphone"]


@functools.cache
def phone_households():
    result = collections.defaultdict(list)
    for phone_key in phone_keys:
        for voter in db.voters:
            phone = getattr(voter, phone_key)
            if not phone:
                continue

            if voter not in result[phone]:
                result[phone].append(voter)

    return result


def household_info_by_phones(voter):
    result = collections.defaultdict(list)
    seen = set()

    households = phone_households()

    for phone_key in phone_keys:
        phone = getattr(voter, phone_key)

        if phone in seen:
            continue
        seen.add(phone)

        for other_voter in households[phone]:
            if other_voter.id == voter.id:
                continue

            result[phone].append(other_voter)

    return result


from __future__ import annotations
from collections import defaultdict
from copy import deepcopy

REQUIRED_ROLES = {"CMA": 1, "FOS": 1, "SON": 1}


def active_exception(ex, date, session):
    return ex.get("date") == date and ex.get("session", "ALL") in ("ALL", session)


def pref_rank(person, location):
    prefs = person.get("preferences", [])
    try:
        return prefs.index(location)
    except ValueError:
        return 99


def can_work(person, date, session, location, role, exceptions):
    if not person.get("active", True) or role not in person.get("roles", []):
        return False
    for ex in exceptions:
        if ex.get("person_id") == person["id"] and active_exception(ex, date, session):
            if ex.get("status") in ("PTO", "OFF", "UNAVAILABLE", "LEAVE"):
                return False
    unavailable = person.get("unavailable_locations", [])
    return location not in unavailable


def score(person, location, baseline_location, moved_count):
    score = pref_rank(person, location) * 100
    if baseline_location and baseline_location != location:
        score += 25
    score += moved_count.get(person["id"], 0) * 10
    return score


def rebalance(day, roster, exceptions):
    """Return a recommendation. Never mutates the stored/day baseline."""
    result = deepcopy(day)
    changes, warnings = [], []
    moved_count = defaultdict(int)
    off_ids = {
        ex["person_id"] for ex in exceptions
        if active_exception(ex, day["date"], day["session"])
        and ex.get("status") in ("PTO", "OFF", "UNAVAILABLE", "LEAVE")
    }
    people = {p["id"]: p for p in roster if p.get("active", True)}

    # Remove unavailable assignments and record their vacancies.
    for clinic in result["clinics"]:
        kept=[]
        for a in clinic.get("assignments", []):
            if a["person_id"] in off_ids or a["person_id"] not in people:
                changes.append({"person_id": a["person_id"], "from": clinic["location"], "to": "OFF", "role": a["role"], "reason": "approved exception"})
            else:
                kept.append(a)
        clinic["assignments"] = kept

    # Close a clinic only when it had physician coverage and all assigned MDs are now off.
    for clinic in result["clinics"]:
        baseline_mds = [a for a in day["clinics"] if a["location"] == clinic["location"] for a in a.get("assignments", []) if a["role"] == "MD"]
        live_mds = [a for a in clinic.get("assignments", []) if a["role"] == "MD"]
        clinic["closed"] = bool(baseline_mds and not live_mds)
        if clinic["closed"]:
            deployable = [a for a in clinic["assignments"] if a["role"] != "MD"]
            clinic["assignments"] = []
            clinic["redeploy_pool"] = deployable
            changes.append({"person_id": "CLINIC", "from": clinic["location"], "to": "CLOSED", "role": "MD", "reason": "only scheduled physician is off"})

    assigned = {a["person_id"] for c in result["clinics"] for a in c.get("assignments", [])}
    pool=[]
    for c in result["clinics"]:
        for a in c.pop("redeploy_pool", []):
            pool.append((a, c["location"]))
    for p in roster:
        if p.get("active", True) and p["id"] not in assigned and p["id"] not in off_ids:
            for role in p.get("roles", []):
                pool.append(({"person_id": p["id"], "role": role}, None))

    # Fill minimum coverage at every open clinic, preserving valid assignments.
    for clinic in result["clinics"]:
        if clinic.get("closed"):
            continue
        for role, minimum in REQUIRED_ROLES.items():
            current = [a for a in clinic["assignments"] if a["role"] == role]
            while len(current) < minimum:
                candidates=[]
                for idx,(a,origin) in enumerate(pool):
                    p=people.get(a["person_id"])
                    if p and can_work(p, day["date"], day["session"], clinic["location"], role, exceptions) and a["role"] == role:
                        candidates.append((score(p, clinic["location"], origin, moved_count), idx, a, origin))
                if not candidates:
                    warnings.append(f'{clinic["location"]}: uncovered {role}')
                    break
                _, idx, a, origin = min(candidates)
                pool.pop(idx)
                clinic["assignments"].append(a)
                current.append(a)
                moved_count[a["person_id"]] += 1
                changes.append({"person_id": a["person_id"], "from": origin or "available pool", "to": clinic["location"], "role": role, "reason": "minimum coverage; best eligible preference score"})

    # Redeploy any remaining personnel released by a closed clinic as supplemental support.
    # General unassigned/available staff remain available rather than being moved unnecessarily.
    remaining=[]
    for a, origin in pool:
        if not origin:
            remaining.append((a, origin))
            continue
        p=people.get(a["person_id"])
        eligible=[c for c in result["clinics"] if not c.get("closed") and can_work(p, day["date"], day["session"], c["location"], a["role"], exceptions)] if p else []
        if not eligible:
            warnings.append(f'{p["name"] if p else a["person_id"]}: no eligible open clinic for redeployment')
            remaining.append((a, origin))
            continue
        target=min(eligible, key=lambda c: score(p, c["location"], origin, moved_count))
        target["assignments"].append(a)
        moved_count[a["person_id"]] += 1
        changes.append({"person_id": a["person_id"], "from": origin, "to": target["location"], "role": a["role"], "reason": "redeployed from closed clinic; best eligible preference score"})
    pool=remaining

    result["off"] = sorted([people[i]["name"] for i in off_ids if i in people])
    result["changes"] = changes
    result["warnings"] = warnings
    return result

from __future__ import annotations
from copy import deepcopy
from datetime import date, datetime
import uuid
import streamlit as st
from storage import load_root, save_root

ROLES = ["MD", "RN", "CMA", "SON", "FOS"]
REASONS = ["PTO", "Vacation", "Call out", "Physician off", "Clinic closed", "Other"]


def _cfg(root):
    return root.setdefault("staffing_config", {"roster": [], "exceptions": [], "audit": []})


def _save(root, action, detail):
    cfg = _cfg(root)
    cfg["audit"].append({"ts": datetime.now().isoformat(timespec="seconds"), "action": action, "detail": detail})
    cfg["audit"] = cfg["audit"][-250:]
    save_root(root)


def _score(clinic, role, person, metrics, assignments):
    m = metrics.get(clinic, {})
    demand = int(m.get("Patients", 0)) + 2 * int(m.get("Echoes", 0)) + 2 * int(m.get("Stress Tests", 0)) + int(m.get("Nurse Visits", 0)) + 2 * int(m.get("Fetals", 0))
    assigned_role = sum(1 for x in assignments if x["clinic"] == clinic and x["role"] == role and x["status"] == "assigned")
    shortage_bonus = 8 if assigned_role == 0 and role in {"CMA", "FOS", "SON"} else 0
    prefs = person.get("preferences", [])
    pref_bonus = max(0, 6 - prefs.index(clinic)) if clinic in prefs else 0
    continuity = 3 if person.get("home_clinic") == clinic else 0
    return demand + shortage_bonus + pref_bonus + continuity


def calculate_plan(day_key, clinics, metrics, roster, exceptions):
    relevant = [e for e in exceptions if e.get("date") == day_key and e.get("active", True)]
    closed = {e.get("clinic") for e in relevant if e.get("reason") == "Clinic closed"}
    off_names = {e.get("person") for e in relevant if e.get("reason") in {"PTO", "Vacation", "Call out", "Physician off"}}
    assignments = []
    released = []
    for p in roster:
        base = p.get("home_clinic") or ""
        row = {"person": p["name"], "role": p["role"], "clinic": base, "original_clinic": base, "status": "assigned", "reason": "Baseline"}
        if p["name"] in off_names:
            row.update(status="off", reason=" / ".join(sorted({e["reason"] for e in relevant if e.get("person") == p["name"]})))
        elif base in closed:
            row.update(status="released", reason=f"{base} closed")
            released.append((row, p))
        assignments.append(row)

    open_clinics = [c for c in clinics if c not in closed]
    for row, person in released:
        allowed = set(person.get("allowed_clinics") or open_clinics)
        candidates = [c for c in open_clinics if c in allowed]
        if not candidates:
            row.update(status="unassigned", clinic="", reason=f"No travel-compliant {person['role']} placement")
            continue
        target = max(candidates, key=lambda c: _score(c, person["role"], person, metrics, assignments))
        row.update(status="assigned", clinic=target, reason=f"Redeployed from {row['original_clinic']} to highest-need eligible clinic")
    return assignments, closed


def render_staffing_manager(day_value: date, clinics: list[str], metrics: dict):
    root = load_root()
    cfg = _cfg(root)
    day_key = day_value.strftime("%Y-%m-%d")

    with st.sidebar.expander("Staffing manager", expanded=False):
        st.caption("Recommendations only. Review before using operationally.")
        section = st.radio("Staffing tools", ["Daily exceptions", "Roster", "Audit"], horizontal=True, label_visibility="collapsed")

        if section == "Roster":
            with st.form("add_roster_person", clear_on_submit=True):
                name = st.text_input("Name")
                role = st.selectbox("Role", ROLES)
                home = st.selectbox("Home / baseline clinic", clinics)
                allowed = st.multiselect("Travel-allowed clinics", clinics, default=clinics)
                prefs = st.multiselect("Preferred clinics (ordered after save)", clinics)
                if st.form_submit_button("Add staff member", use_container_width=True) and name.strip():
                    cfg["roster"].append({"id": str(uuid.uuid4()), "name": name.strip(), "role": role, "home_clinic": home, "allowed_clinics": allowed, "preferences": prefs})
                    _save(root, "Roster add", f"{name.strip()} ({role})")
                    st.rerun()
            if cfg["roster"]:
                remove_name = st.selectbox("Remove person", [p["name"] for p in cfg["roster"]])
                if st.button("Remove selected person", use_container_width=True):
                    cfg["roster"] = [p for p in cfg["roster"] if p["name"] != remove_name]
                    _save(root, "Roster remove", remove_name)
                    st.rerun()

        elif section == "Daily exceptions":
            roster_names = [p["name"] for p in cfg["roster"]]
            with st.form("add_exception", clear_on_submit=True):
                reason = st.selectbox("Reason", REASONS)
                person = st.selectbox("Person", [""] + roster_names, disabled=reason == "Clinic closed")
                clinic = st.selectbox("Clinic", [""] + clinics, disabled=reason != "Clinic closed")
                note = st.text_input("Note")
                if st.form_submit_button("Apply exception and recalculate", use_container_width=True):
                    if (reason == "Clinic closed" and clinic) or (reason != "Clinic closed" and person):
                        cfg["exceptions"].append({"id": str(uuid.uuid4()), "date": day_key, "reason": reason, "person": person, "clinic": clinic, "note": note, "active": True})
                        _save(root, "Exception add", f"{day_key}: {reason} {person or clinic}")
                        st.rerun()
            active = [e for e in cfg["exceptions"] if e.get("date") == day_key and e.get("active", True)]
            if active:
                labels = [f"{e['reason']}: {e.get('person') or e.get('clinic')}" for e in active]
                chosen = st.selectbox("Reinstate / undo", labels)
                if st.button("Reinstate selected", use_container_width=True):
                    active[labels.index(chosen)]["active"] = False
                    _save(root, "Exception reinstated", f"{day_key}: {chosen}")
                    st.rerun()
            else:
                st.info("No active exceptions for this date.")
        else:
            for item in reversed(cfg["audit"][-15:]):
                st.caption(f"{item['ts']} · {item['action']} · {item['detail']}")

    plan, closed = calculate_plan(day_key, clinics, metrics, cfg["roster"], cfg["exceptions"])
    if cfg["roster"]:
        st.markdown("#### Automated staffing coverage")
        if closed:
            st.caption("Closed: " + ", ".join(sorted(closed)))
        view = [{"Staff": x["person"], "Role": x["role"], "Assigned clinic": x["clinic"] or "Unassigned", "Status": x["status"].title(), "Coverage note": x["reason"]} for x in plan]
        st.dataframe(view, use_container_width=True, hide_index=True)
        unresolved = [x for x in plan if x["status"] == "unassigned"]
        if unresolved:
            st.error("Review required: " + "; ".join(f"{x['person']} ({x['role']})" for x in unresolved))
        st.caption("Rules: match role, exclude unavailable staff, respect travel limits, then rank open clinics by workload, uncovered core-role need, preference, and continuity.")

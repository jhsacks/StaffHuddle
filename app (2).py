import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import uuid

import streamlit as st

from storage import (
    load_root,
    save_root,
    load_huddle,
    save_huddle,
    load_exceptions,
    save_exceptions,
)

st.set_page_config(
    page_title="Pediatric Cardiology Daily Huddle",
    page_icon="🌼",
    layout="wide",
)

BASELINE = json.loads(
    (Path(__file__).parent / "data" / "baseline.json").read_text()
)

DEFAULT_LOCATIONS = [
    "Kennesaw",
    "Smyrna",
    "Douglasville",
    "Avalon",
    "LaGrange",
    "New Hope",
    "Woodstock",
]

ROLES = ["MD", "RN", "MA", "SON", "FOS"]
LABEL = {
    "MD": "MD",
    "RN": "RN",
    "MA": "MA",
    "SON": "Sonographers",
    "FOS": "FOS",
}
METRICS = [
    "Clinic/Patients",
    "Echoes",
    "Stress Tests",
    "Nurse Visits",
    "Video Visit",
    "Fetal",
]
ALIASES = {
    "Kennesaw": "Barrett",
    "New Hope": "Paulding",
    "LaGrange": "Lagrange",
}
COLORS = [
    "#efa51b",
    "#17945a",
    "#d12f84",
    "#6c8f42",
    "#277b7f",
    "#b3c933",
    "#df4a20",
]

st.markdown(
    """
<style>
:root {
    --blue: #2670c8;
    --red: #cf303b;
    --lime: #b3c933;
    --ink: #3d4146;
    --bg: #f6f7f8;
}
.stApp { background: var(--bg); color: var(--ink); }
.block-container { max-width: 1220px; padding-top: 1.3rem; }
.hero h1 { margin: 0; color: var(--blue); font-size: 26px; font-style: italic; }
.hero p { margin: .2rem 0; color: #697078; }
.huddle { font-size: 28px; color: var(--lime); font-weight: 800; font-style: italic; margin: 1rem 0; }
.sect { font-size: 20px; font-weight: 800; font-style: italic; margin: 1rem 0 .4rem; }
.loc { font-weight: 800; font-style: italic; }
.staff-readout {
    background: #f1f4f7;
    border: 1px solid #d9dfe5;
    border-radius: 7px;
    min-height: 44px;
    padding: 9px;
    line-height: 1.25;
    overflow-wrap: anywhere;
}
.staff-readout.closed { background: #fde8e8; color: #9f1d24; font-weight: 800; }
.staff-readout.special { background: #e8f2ff; color: #174f8a; }
.staff-readout.missing { background: #fff3cd; }
.metric-box input { background: #fffdf4; }
.stTextInput input { background: #fffdf4; }
.stButton button { border-radius: 6px; }
button[kind="primary"] { background: var(--blue); }
div[data-baseweb="select"] { min-height: 42px; }
div[data-baseweb="tag"] {
    background-color: #eef4fb !important;
    color: #1d4d8f !important;
    font-size: .82rem !important;
}
.alert-card {
    background: white;
    border: 1px solid #d9dfe5;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 7px;
}
.alert-good { border-left: 5px solid #24915f; }
.alert-warn { border-left: 5px solid #e0a000; }
.alert-bad { border-left: 5px solid #c6383f; }
.alert-info { border-left: 5px solid #2670c8; }
.small-note { font-size: .82rem; color: #687078; }
</style>
""",
    unsafe_allow_html=True,
)


def get_config():
    root = load_root()
    cfg = root.setdefault("staffhuddle_config", {})

    cfg.setdefault(
        "locations",
        [
            {"id": str(uuid.uuid4()), "name": name, "active": True}
            for name in DEFAULT_LOCATIONS
        ],
    )

    if not cfg.get("roster"):
        cfg["roster"] = []
        for role, people in BASELINE.items():
            for name in people:
                cfg["roster"].append(
                    {
                        "id": str(uuid.uuid4()),
                        "name": name,
                        "role": role,
                        "active": True,
                        "allowed_locations": DEFAULT_LOCATIONS[:],
                    }
                )

    return root, cfg


def active_locations(cfg):
    return [x["name"] for x in cfg["locations"] if x.get("active", True)]


def active_roster(cfg, role=None):
    return [
        p
        for p in cfg["roster"]
        if p.get("active", True) and (role is None or p["role"] == role)
    ]


def week_of(d):
    return ((d - date(2026, 10, 4)).days // 7) % 4 + 1


def slot_key(d, session):
    return f"{week_of(d)}-{d.strftime('%a')}-{session}"


def matches(value, location):
    return ALIASES.get(location, location).lower() in str(value).lower()


def baseline_staff(d, session, cfg):
    sessions = ["AM", "PM"] if session == "BOTH" else [session]
    locations = active_locations(cfg)
    output = {loc: {role: [] for role in ROLES} for loc in locations}
    valid_names = {p["name"] for p in active_roster(cfg)}

    for role, people in BASELINE.items():
        for name, pattern in people.items():
            if name not in valid_names:
                continue
            for current_session in sessions:
                assignment = pattern.get(slot_key(d, current_session), "n/a")
                for location in locations:
                    if matches(assignment, location) and name not in output[location][role]:
                        output[location][role].append(name)

    return output


def exceptions_for(d):
    selected_date = str(d)
    return [
        e
        for e in load_exceptions()
        if e.get("start", "") <= selected_date <= e.get("end", "")
    ]


def normalize_staff(staff, locations):
    output = {loc: {role: [] for role in ROLES} for loc in locations}
    for location in locations:
        for role in ROLES:
            output[location][role] = list(
                dict.fromkeys(staff.get(location, {}).get(role, []))
            )
    return output


def assigned_names(staff):
    return {
        name
        for location_roles in staff.values()
        for names in location_roles.values()
        for name in names
    }


def build_available_pool(staff, off_names, cfg):
    assigned = assigned_names(staff)
    pool = []
    for person in active_roster(cfg):
        if person["name"] not in assigned and person["name"] not in off_names:
            pool.append((person["name"], person["role"], "Unassigned"))
    return pool


def auto_rebalance(staff, off_names, staff_only, cfg):
    locations = active_locations(cfg)
    staff = normalize_staff(staff, locations)
    changes = []

    for location in locations:
        for role in ROLES:
            staff[location][role] = [
                name for name in staff[location][role] if name not in off_names
            ]

    closed = {
        location
        for location in locations
        if not staff[location]["MD"] and location not in staff_only
    }

    pool = []
    for location in closed:
        for role in ROLES[1:]:
            for name in staff[location][role]:
                pool.append((name, role, location))
            staff[location][role] = []

    pool.extend(build_available_pool(staff, off_names, cfg))
    roster = {p["name"]: p for p in active_roster(cfg)}

    def eligible(name, location):
        return location in roster.get(name, {}).get("allowed_locations", locations)

    def candidate(role, location, allow_rn_for_ma=False):
        exact = [x for x in pool if x[1] == role and eligible(x[0], location)]
        if exact:
            return exact[0]
        if allow_rn_for_ma:
            nurses = [x for x in pool if x[1] == "RN" and eligible(x[0], location)]
            if nurses:
                return nurses[0]
        return None

    for location in locations:
        if location in closed or location in staff_only:
            continue

        physician_count = len(staff[location]["MD"])
        if physician_count == 0:
            continue

        if not staff[location]["MA"] and not staff[location]["RN"]:
            pick = candidate("MA", location, allow_rn_for_ma=True)
            if pick:
                pool.remove(pick)
                name, role, origin = pick
                staff[location][role].append(name)
                changes.append(
                    f"{name}: {origin} → {location} ({role} covering MA/RN support)"
                )

        while len(staff[location]["SON"]) < physician_count:
            pick = candidate("SON", location)
            if not pick:
                break
            pool.remove(pick)
            name, role, origin = pick
            staff[location][role].append(name)
            changes.append(f"{name}: {origin} → {location} (sonographer coverage)")

        if not staff[location]["FOS"]:
            pick = candidate("FOS", location)
            if pick:
                pool.remove(pick)
                name, role, origin = pick
                staff[location][role].append(name)
                changes.append(f"{name}: {origin} → {location} (FOS coverage)")

    return staff, closed, pool, changes


def coverage_rows(staff, closed, staff_only):
    rows = []
    for location in staff:
        physician_count = len(staff[location]["MD"])
        support_count = len(staff[location]["MA"]) + len(staff[location]["RN"])
        sonographer_count = len(staff[location]["SON"])
        fos_count = len(staff[location]["FOS"])

        if location in closed:
            status = "CLOSED"
        elif location in staff_only:
            status = "STAFF-ONLY OPEN"
        else:
            issues = []
            if physician_count and support_count < 1:
                issues.append("MA/RN")
            if physician_count and sonographer_count < physician_count:
                issues.append(f"SON {sonographer_count}/{physician_count}")
            if physician_count and fos_count < 1:
                issues.append("FOS")
            status = (
                "COVERED"
                if physician_count and not issues
                else ("MISSING " + ", ".join(issues) if physician_count else "NO MD")
            )

        rows.append(
            {
                "Location": location,
                "MD": physician_count,
                "MA/RN": support_count,
                "SON": sonographer_count,
                "FOS": fos_count,
                "Coverage": status,
            }
        )

    return rows


def admin_panel(root, cfg):
    with st.expander("Administration", expanded=False):
        roster_tab, locations_tab = st.tabs(["Roster", "Locations"])

        with roster_tab:
            locations = [x["name"] for x in cfg["locations"]]
            edited = st.data_editor(
                cfg["roster"],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "name": st.column_config.TextColumn("Name", required=True),
                    "role": st.column_config.SelectboxColumn(
                        "Job", options=ROLES, required=True
                    ),
                    "active": st.column_config.CheckboxColumn("Active"),
                    "allowed_locations": st.column_config.ListColumn(
                        "Allowed locations"
                    ),
                },
                key="roster_editor",
            )

            if st.button("Save roster", type="primary"):
                for person in edited:
                    person.setdefault("id", str(uuid.uuid4()))
                    person.setdefault("allowed_locations", locations)
                cfg["roster"] = edited
                root["staffhuddle_config"] = cfg
                save_root(root)
                st.rerun()

        with locations_tab:
            edited_locations = st.data_editor(
                cfg["locations"],
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "name": st.column_config.TextColumn(
                        "Location", required=True
                    ),
                    "active": st.column_config.CheckboxColumn("Active"),
                },
                key="locations_editor",
            )

            if st.button("Save locations", type="primary"):
                for location in edited_locations:
                    location.setdefault("id", str(uuid.uuid4()))
                cfg["locations"] = edited_locations
                root["staffhuddle_config"] = cfg
                save_root(root)
                st.rerun()


def staffing_grid(staff, cfg, locations, key, edit_mode):
    updated = deepcopy(staff)

    headers = st.columns([1.22, 1.24, 1.08, 1.08, 1.45, 1.08])
    for column, text in zip(
        headers, ["Location", "MD", "RN", "MA", "Sonographers", "FOS"]
    ):
        column.markdown(f"**_{text}_**")

    for i, location in enumerate(locations):
        row = st.columns([1.22, 1.24, 1.08, 1.08, 1.45, 1.08])
        row[0].markdown(
            f'<span class="loc" style="color:{COLORS[i % len(COLORS)]}">{location}</span>',
            unsafe_allow_html=True,
        )

        for index, role in enumerate(ROLES, start=1):
            current = updated[location][role]
            visible_text = ", ".join(current) if current else "—"

            row[index].markdown(
                f'<div class="staff-readout">{visible_text}</div>',
                unsafe_allow_html=True,
            )

            if edit_mode:
                options = [p["name"] for p in active_roster(cfg, role)]
                updated[location][role] = row[index].multiselect(
                    label=f"{location}-{role}",
                    options=options,
                    default=[name for name in current if name in options],
                    label_visibility="collapsed",
                    key=f"staff-{key}-{location}-{role}",
                )

    return updated


def render_coverage_alerts(rows):
    for item in rows:
        status = item["Coverage"]
        if status == "COVERED":
            css_class = "alert-good"
            message = "Covered"
        elif status == "CLOSED":
            css_class = "alert-bad"
            message = "Closed — no onsite MD"
        elif status == "STAFF-ONLY OPEN":
            css_class = "alert-info"
            message = "Staff-only open"
        elif status.startswith("MISSING"):
            css_class = "alert-warn"
            message = status.title()
        else:
            css_class = "alert-info"
            message = status.title()

        st.markdown(
            f'<div class="alert-card {css_class}"><strong>{item["Location"]}</strong><br>{message}</div>',
            unsafe_allow_html=True,
        )


root, cfg = get_config()
locations = active_locations(cfg)

st.markdown(
    '<div class="hero"><h1>Pediatric Cardiology Daily Huddle</h1>'
    '<p>Daily counts and staffing save to the existing Google Drive JSON.</p></div>',
    unsafe_allow_html=True,
)

controls = st.columns([1.4, 1, 1, 1])
with controls[0]:
    selected = st.date_input("Date", date.today(), format="MM/DD/YYYY")
with controls[1]:
    session = st.selectbox(
        "Session",
        ["BOTH", "AM", "PM"],
        format_func=lambda value: "AM + PM" if value == "BOTH" else value,
    )
with controls[2]:
    edit_mode = st.toggle("Edit staffing", value=False)
with controls[3]:
    admin = st.toggle("Admin mode", value=False)

if admin:
    admin_panel(root, cfg)

key = f"{selected}|{session}"
if st.session_state.get("record_key") != key:
    st.session_state.record_key = key
    st.session_state.record = load_huddle(str(selected), session)

record = st.session_state.record
record.setdefault("metrics", {})
record.setdefault(
    "footer",
    {
        "Admin": "Jackie, Heather",
        "Hospital": "Kim",
        "On Leave": "",
        "Remote": "Tia, Nicole",
        "Off": "",
    },
)
record.setdefault("staff_only_locations", [])

st.markdown(
    f'<div class="huddle">Daily Huddle: {selected.strftime("%A %B %d, %Y")} 🌼</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sect" style="color:#2670c8">Locations</div>',
    unsafe_allow_html=True,
)

metric_headers = st.columns([1.35, 1, 1, 1, 1, 1, 1])
for column, label in zip(metric_headers, ["Locations:"] + METRICS):
    column.markdown(f"**_{label}_**")

for i, location in enumerate(locations):
    row = st.columns([1.35, 1, 1, 1, 1, 1, 1])
    row[0].markdown(
        f'<span class="loc" style="color:{COLORS[i % len(COLORS)]}">{location}</span>',
        unsafe_allow_html=True,
    )
    record["metrics"].setdefault(location, {})
    for metric_index, metric in enumerate(METRICS, start=1):
        record["metrics"][location][metric] = row[metric_index].text_input(
            label=f"{location}-{metric}",
            value=str(record["metrics"][location].get(metric, "") or ""),
            label_visibility="collapsed",
            placeholder="0",
            key=f"metric-{key}-{location}-{metric}",
        )

base_staff = record.get("staffing") or baseline_staff(selected, session, cfg)
base_staff = normalize_staff(base_staff, locations)
active_exceptions = exceptions_for(selected)
off_names = {e["person"] for e in active_exceptions}

for location in locations:
    for role in ROLES:
        base_staff[location][role] = [
            name for name in base_staff[location][role] if name not in off_names
        ]

st.markdown(
    '<div class="sect" style="color:#cf303b">Staff Scheduling</div>',
    unsafe_allow_html=True,
)
st.caption(
    "All assignments remain visible. Turn on Edit staffing to select or unselect roster members in place."
)

staff = staffing_grid(base_staff, cfg, locations, key, edit_mode)

with st.expander("Clinic operating overrides", expanded=False):
    st.caption(
        "A location without an onsite MD normally closes. Select a location only for an approved hybrid, echo-only, nurse, video, or administrative session."
    )
    record["staff_only_locations"] = st.multiselect(
        "Manually open without onsite MD",
        locations,
        default=[
            location
            for location in record["staff_only_locations"]
            if location in locations
        ],
        key=f"staff-only-{key}",
    )

staff, closed, remaining_pool, changes = auto_rebalance(
    staff,
    off_names,
    set(record["staff_only_locations"]),
    cfg,
)
record["staffing"] = staff

left, right = st.columns(2)

with left:
    st.markdown("#### Unassigned Staff")
    assigned = assigned_names(staff)
    unassigned = [
        person
        for person in active_roster(cfg)
        if person["name"] not in assigned and person["name"] not in off_names
    ]

    if unassigned:
        grouped = {role: [] for role in ROLES}
        for person in unassigned:
            grouped[person["role"]].append(person["name"])
        for role in ROLES:
            if grouped[role]:
                st.markdown(
                    f'<div class="alert-card alert-info"><strong>{LABEL[role]}</strong><br>{", ".join(grouped[role])}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.success("All active, available roster staff are assigned.")

with right:
    st.markdown("#### Coverage Alerts")
    render_coverage_alerts(
        coverage_rows(staff, closed, set(record["staff_only_locations"]))
    )

if changes:
    st.markdown("#### Automatic Coverage Changes")
    for change in changes:
        st.info(change)

with st.expander("Time off and coverage", expanded=True):
    roster = active_roster(cfg)
    role_options = sorted({person["role"] for person in roster})
    controls = st.columns([1, 1.5, 1, 1])

    selected_role = controls[0].selectbox("Job", role_options, key="time-off-role")
    people = [
        person["name"] for person in roster if person["role"] == selected_role
    ]
    selected_person = controls[1].selectbox(
        "Person", people, key="time-off-person"
    )
    start = controls[2].date_input("From", selected, key="time-off-start")
    end = controls[3].date_input("To", selected, key="time-off-end")

    if st.button("Add time off"):
        exceptions = load_exceptions()
        exceptions.append(
            {
                "id": str(uuid.uuid4()),
                "person": selected_person,
                "role": selected_role,
                "start": str(start),
                "end": str(end),
                "location": "",
                "replacement": "",
            }
        )
        save_exceptions(exceptions)
        st.rerun()

    current = exceptions_for(selected)
    if current:
        st.markdown("**Off for this date**")
        for item in current:
            text_column, button_column = st.columns([6, 1])
            text_column.write(
                f'{item["person"]} · {item["role"]} · {item["start"]} to {item["end"]}'
            )
            if button_column.button(
                "Reinstate",
                key=f'reinstate-{item.get("id", item["person"] + item["start"])}',
            ):
                exceptions = load_exceptions()
                item_id = item.get("id")
                if item_id:
                    exceptions = [x for x in exceptions if x.get("id") != item_id]
                else:
                    exceptions = [
                        x
                        for x in exceptions
                        if not (
                            x.get("person") == item.get("person")
                            and x.get("start") == item.get("start")
                            and x.get("end") == item.get("end")
                        )
                    ]
                save_exceptions(exceptions)
                st.rerun()
    else:
        st.caption("No one is off for this date.")

footer_columns = st.columns([1.3, .8, 1.1, .8])
for column, label in zip(
    footer_columns, ["Admin", "Hospital", "On Leave", "Off"]
):
    record["footer"][label] = column.text_input(
        label,
        record["footer"].get(label, ""),
        key=f"footer-{key}-{label}",
    )

record["footer"]["Remote"] = st.text_input(
    "Remote",
    record["footer"].get("Remote", ""),
    key=f"footer-{key}-Remote",
)

buttons = st.columns([1, 1, 4])
if buttons[0].button("Save huddle", type="primary", use_container_width=True):
    record.update(
        {
            "date": str(selected),
            "session": session,
            "staffing": staff,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_huddle(str(selected), session, record)
    st.success("Saved to Google Drive JSON.")

if buttons[1].button("Reload saved", use_container_width=True):
    st.session_state.record = load_huddle(str(selected), session)
    st.rerun()

st.caption(
    "Planning recommendation only. Confirm clinic closures, qualifications, leave, travel constraints, and final staffing before operational use."
)

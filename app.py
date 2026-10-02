
import uuid
from datetime import date
import pandas as pd
import streamlit as st
from logic import rebalance
from storage import load, save

st.set_page_config(page_title="Clinic Staffing Planner", layout="wide")
st.title("Clinic Staffing Planner")
data=load()

def commit(): save(data); st.success("Saved"); st.rerun()

tab_daily, tab_off, tab_roster, tab_roles = st.tabs(["Daily coverage", "Time off", "Staff roster", "Roles"])

with tab_daily:
    selected=st.date_input("Date", value=date.today()).isoformat()
    session=st.selectbox("Session", ["AM","PM"])
    day=next((d for d in data["days"] if d["date"]==selected and d["session"]==session), None)
    if not day:
        st.info("No baseline is stored for this session.")
    else:
        rec=rebalance(day, data["roster"], data["exceptions"])
        if rec["off"]: st.warning("Off: " + ", ".join(rec["off"]))
        rows=[]
        for c in rec["clinics"]:
            if c.get("closed"):
                rows.append({"Location":c["location"],"Status":"CLOSED","Role":"","Staff":""})
            else:
                for a in c.get("assignments",[]):
                    p=next((x for x in data["roster"] if x["id"]==a["person_id"]), {"name":a["person_id"]})
                    rows.append({"Location":c["location"],"Status":"OPEN","Role":a["role"],"Staff":p["name"]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if rec["warnings"]:
            for w in rec["warnings"]: st.error(w)
        st.subheader("Recommended changes")
        st.dataframe(pd.DataFrame(rec["changes"]), use_container_width=True, hide_index=True)
        st.caption("Recommendations require scheduler review. Baseline assignments are not overwritten automatically.")

with tab_off:
    st.subheader("Who's off")
    selected=st.date_input("Exception date", value=date.today(), key="exdate").isoformat()
    same=[e for e in data["exceptions"] if e["date"]==selected]
    for e in same:
        p=next((x for x in data["roster"] if x["id"]==e["person_id"]), {"name":e["person_id"]})
        c1,c2,c3=st.columns([4,2,1])
        c1.write(f'{p["name"]} · {e["status"]} · {e.get("session","ALL")}')
        if c3.button("Reinstate", key=e["id"]):
            data["exceptions"]=[x for x in data["exceptions"] if x["id"]!=e["id"]]; commit()
    with st.form("addoff"):
        person=st.selectbox("Person", data["roster"], format_func=lambda p:p["name"])
        status=st.selectbox("Status", ["PTO","OFF","LEAVE","UNAVAILABLE"])
        sess=st.selectbox("Applies to", ["ALL","AM","PM"])
        if st.form_submit_button("Mark off"):
            data["exceptions"].append({"id":str(uuid.uuid4()),"person_id":person["id"],"date":selected,"session":sess,"status":status}); commit()

with tab_roster:
    st.subheader("Add staff member")
    with st.form("person"):
        name=st.text_input("Name")
        roles=st.multiselect("Qualified roles", data["roles"])
        prefs=st.text_input("Preferred locations, best first (comma-separated)")
        blocked=st.text_input("Unavailable locations (comma-separated)")
        if st.form_submit_button("Add") and name and roles:
            data["roster"].append({"id":str(uuid.uuid4()),"name":name,"roles":roles,"preferences":[x.strip() for x in prefs.split(',') if x.strip()],"unavailable_locations":[x.strip() for x in blocked.split(',') if x.strip()],"active":True}); commit()
    for p in data["roster"]:
        c1,c2,c3=st.columns([4,2,1])
        c1.write(f'{p["name"]} · {", ".join(p.get("roles",[]))}')
        c2.write("Active" if p.get("active",True) else "Inactive")
        if c3.button("Remove" if p.get("active",True) else "Restore", key="person"+p["id"]):
            p["active"]=not p.get("active",True); commit()

with tab_roles:
    st.write("Roles: " + ", ".join(data["roles"]))
    with st.form("role"):
        role=st.text_input("New role")
        if st.form_submit_button("Add role") and role and role not in data["roles"]:
            data["roles"].append(role); commit()
    removable=[r for r in data["roles"] if not any(r in p.get("roles",[]) for p in data["roster"] if p.get("active",True))]
    role_to_remove=st.selectbox("Remove unused role", [""]+removable)
    if st.button("Remove role") and role_to_remove:
        data["roles"].remove(role_to_remove); commit()

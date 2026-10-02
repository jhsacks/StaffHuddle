import json
from datetime import date, datetime, timedelta
from pathlib import Path
import streamlit as st
from storage import load_huddle, save_huddle, load_exceptions, save_exceptions

st.set_page_config(page_title="Pediatric Cardiology Daily Huddle", page_icon="🌼", layout="wide")
BASELINE=json.loads((Path(__file__).parent/"data"/"baseline.json").read_text())
LOCATIONS=["Kennesaw","Smyrna","Douglasville","Avalon","LaGrange","New Hope","Woodstock"]
ROLES=["MD","RN","MA","SON","FOS"]
METRICS=["Clinic/Patients","Echoes","Stress Tests","Nurse Visits","Video Visit","Fetal"]
ALIASES={"Kennesaw":"Barrett","New Hope":"Paulding","LaGrange":"Lagrange"}
COLORS={"Kennesaw":"#efa51b","Smyrna":"#17945a","Douglasville":"#b5367d","Avalon":"#6c8f42","LaGrange":"#277b7f","New Hope":"#b3c933","Woodstock":"#d25135"}

st.markdown("""<style>
:root{--blue:#2670c8;--orange:#efa51b;--green:#17945a;--red:#c83d44;--pink:#b5367d;--lime:#b3c933;--teal:#277b7f;--line:#cbd1d6;--ink:#3d4146;--bg:#f6f7f8}
.stApp{background:var(--bg);color:var(--ink)}.block-container{max-width:1180px;padding-top:1.4rem}.hero{display:flex;justify-content:space-between;align-items:end;gap:18px}.hero h1{margin:0;color:var(--blue);font-size:26px;font-style:italic}.hero p{margin:3px 0 0;color:#6c737a}.huddle-title{font-size:28px;color:var(--lime);font-weight:800;font-style:italic;margin:.8rem 0}.section-title{font-size:20px;font-weight:750;font-style:italic;margin:.3rem 0}.card{background:white;border:1px solid #d8dde1;border-radius:9px;box-shadow:0 2px 12px #0000000a;padding:14px;margin:12px 0}.loc{font-weight:750;font-style:italic}.small{color:#697078;font-size:12px}div[data-testid="stNumberInput"] input{background:#fffdf4}div[data-testid="stMultiSelect"]{background:#fffdf4;border-radius:6px}.stButton button{border-radius:6px}button[kind="primary"]{background:var(--blue)}
@media print{header,.stAppDeployButton,div[data-testid="stSidebar"],.no-print{display:none!important}.block-container{max-width:none;padding:0}.card{box-shadow:none}}
</style>""",unsafe_allow_html=True)

def week_of(d):
    anchor=date(2026,10,4)
    return ((d-anchor).days//7)%4+1

def day_key(d,session): return f"{week_of(d)}-{d.strftime('%a')}-{session}"
def match(assign,loc): return ALIASES.get(loc,loc).lower() in str(assign).lower()
def default_staff(d,session):
    sessions=["AM","PM"] if session=="BOTH" else [session]
    out={loc:{r:[] for r in ROLES} for loc in LOCATIONS}
    for role,people in BASELINE.items():
        for person,pattern in people.items():
            for sess in sessions:
                assign=pattern.get(day_key(d,sess),"n/a")
                for loc in LOCATIONS:
                    if match(assign,loc) and person not in out[loc][role]: out[loc][role].append(person)
    return out

def all_people(role): return sorted(BASELINE.get(role,{}).keys())

def apply_exceptions(staff,d,session,exceptions):
    active=[x for x in exceptions if x.get("start")<=str(d)<=x.get("end")]
    changes=[]
    for x in active:
        person=x["person"]; role=x["role"]
        for loc in LOCATIONS:
            if person in staff[loc].get(role,[]):
                staff[loc][role].remove(person); changes.append(f"{person} removed from {loc}")
                if role=="MD": staff[loc]["closed"]=True
        repl=x.get("replacement")
        loc=x.get("location")
        if repl and loc and loc in staff: staff[loc][role].append(repl); changes.append(f"{repl} covers {loc} for {person}")
    return staff,changes

st.markdown('<div class="hero"><div><h1>Pediatric Cardiology Daily Huddle</h1><p>Baseline staffing loads automatically; daily counts and approved changes save to Google Drive.</p></div></div>',unsafe_allow_html=True)
ctrl=st.columns([1.4,1,1,1])
with ctrl[0]: selected=st.date_input("Date",value=date.today(),format="MM/DD/YYYY")
with ctrl[1]: session=st.selectbox("Session",["BOTH","AM","PM"],format_func=lambda x:"AM + PM" if x=="BOTH" else x)
with ctrl[2]: admin=st.toggle("Admin mode",value=False)
with ctrl[3]: st.markdown(f'<div class="small" style="padding-top:34px">Week {week_of(selected)} pattern</div>',unsafe_allow_html=True)
key=f"{selected}|{session}"
if st.session_state.get("record_key")!=key:
    st.session_state.record_key=key
    st.session_state.record=load_huddle(str(selected),session)
record=st.session_state.record
record.setdefault("metrics",{})
record.setdefault("staffing",default_staff(selected,session))
record.setdefault("footer",{"Admin":"Jackie, Heather","Hospital":"Kim","On Leave":"","Remote":"Tia, Nicole","Off":""})
exceptions=load_exceptions()
record["staffing"],change_log=apply_exceptions(record["staffing"],selected,session,exceptions)
st.markdown(f'<div class="huddle-title">Daily Huddle: {selected.strftime("%A %B %-d, %Y")} 🌼</div>',unsafe_allow_html=True)

st.markdown('<div class="section-title" style="color:#2670c8">Locations</div>',unsafe_allow_html=True)
heads=st.columns([1.35,1,1,1,1,1,1])
for c,t,col in zip(heads,["Locations:"]+METRICS,["#2670c8","#efa51b","#17945a","#c83d44","#b5367d","#d25135","#17945a"]): c.markdown(f'<b><i style="color:{col}">{t}</i></b>',unsafe_allow_html=True)
for loc in LOCATIONS:
    row=st.columns([1.35,1,1,1,1,1,1]); row[0].markdown(f'<span class="loc" style="color:{COLORS[loc]}">{loc}</span>',unsafe_allow_html=True)
    for i,m in enumerate(METRICS,1):
        v=record["metrics"].setdefault(loc,{}).get(m,0)
        record["metrics"][loc][m]=row[i].number_input(f"{loc}-{m}",min_value=0,value=int(v or 0),label_visibility="collapsed",key=f"m-{key}-{loc}-{m}")

st.markdown('<div class="section-title" style="color:#c83d44;margin-top:24px">Staff Scheduling</div>',unsafe_allow_html=True)
heads=st.columns([1.35,1.25,1,1,1.35,1,1])
for c,t,col in zip(heads,["Staff Scheduling:","MD","RN","MA","Sonographers","FOS","Call Center"],["#c83d44","#d25135","#efa51b","#b3c933","#17945a","#b5367d","#277b7f"]): c.markdown(f'<b><i style="color:{col}">{t}</i></b>',unsafe_allow_html=True)
for loc in LOCATIONS:
    row=st.columns([1.35,1.25,1,1,1.35,1,1]); row[0].markdown(f'<span class="loc" style="color:{COLORS[loc]}">{loc}</span>',unsafe_allow_html=True)
    closed=record["staffing"][loc].get("closed",False)
    for i,role in enumerate(ROLES,1):
        current=record["staffing"][loc].get(role,[])
        if admin:
            record["staffing"][loc][role]=row[i].multiselect(f"{loc}-{role}",all_people(role),default=[x for x in current if x in all_people(role)],label_visibility="collapsed",key=f"s-{key}-{loc}-{role}")
        else:
            text="CLINIC CLOSED" if closed and role=="MD" else ", ".join(current)
            row[i].markdown(text or "&nbsp;",unsafe_allow_html=True)
    record["staffing"][loc]["Call Center"]=row[6].text_input(f"{loc}-call",value=record["staffing"][loc].get("Call Center",""),label_visibility="collapsed",key=f"call-{key}-{loc}")
if change_log: st.warning(" | ".join(change_log))

st.markdown('<br>',unsafe_allow_html=True)
footer_cols=st.columns([1.3,.8,1.1,.8])
for c,label in zip(footer_cols,["Admin","Hospital","On Leave","Off"]): record["footer"][label]=c.text_input(label,value=record["footer"].get(label,""),key=f"f-{key}-{label}")
record["footer"]["Remote"]=st.text_input("Remote",value=record["footer"].get("Remote",""),key=f"f-{key}-remote")

buttons=st.columns([1,1,4])
if buttons[0].button("Save huddle",type="primary",use_container_width=True):
    record["saved_at"]=datetime.now().isoformat(timespec="seconds")
    record["date"]=str(selected); record["session"]=session
    save_huddle(str(selected),session,record); st.success("Saved to Google Drive JSON.")
if buttons[1].button("Reload saved",use_container_width=True):
    st.session_state.record=load_huddle(str(selected),session); st.rerun()

if admin:
    with st.expander("Time off and coverage",expanded=False):
        cols=st.columns([1.2,1,1,1.2,1.2,1])
        roles=ROLES; role=cols[0].selectbox("Role",roles); person=cols[1].selectbox("Person",all_people(role)); start=cols[2].date_input("From",selected); end=cols[3].date_input("To",selected); loc=cols[4].selectbox("Coverage location",[""]+LOCATIONS); repl=cols[5].selectbox("Replacement",[""]+all_people(role))
        if st.button("Add exception"):
            exceptions.append({"person":person,"role":role,"start":str(start),"end":str(end),"location":loc,"replacement":repl}); save_exceptions(exceptions); st.success("Exception saved."); st.rerun()
        if exceptions:

        labels = [
            f"{e['person']} | {e['role']} | {e['start']} -> {e['end']}"
            for e in exceptions
        ]

        selected = st.selectbox(
            "Remove exception",
            labels
        )

        if st.button("Remove selected exception"):

            idx = labels.index(selected)

            exceptions.pop(idx)

            save_exceptions(exceptions)

            st.rerun()

    st.dataframe(exceptions)

st.caption("Planning recommendation only. Confirm clinic closures, qualifications, leave, travel constraints, and final staffing before operational use.")

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import uuid
import streamlit as st
from storage import load_root, save_root, load_huddle, save_huddle, load_exceptions, save_exceptions

st.set_page_config(page_title='Pediatric Cardiology Daily Huddle', page_icon='🌼', layout='wide')
BASELINE=json.loads((Path(__file__).parent/'data'/'baseline.json').read_text())
DEFAULT_LOCATIONS=['Kennesaw','Smyrna','Douglasville','Avalon','LaGrange','New Hope','Woodstock']
ROLE_ORDER=['MD','RN','MA','SON','FOS']
ROLE_LABEL={'MD':'MD','RN':'RN','MA':'MA','SON':'Sonographers','FOS':'FOS'}
METRICS=['Clinic/Patients','Echoes','Stress Tests','Nurse Visits','Video Visit','Fetal']
ALIASES={'Kennesaw':'Barrett','New Hope':'Paulding','LaGrange':'Lagrange'}
COLORS=['#efa51b','#17945a','#d12f84','#6c8f42','#277b7f','#b3c933','#df4a20']

st.markdown('''<style>
:root{--blue:#2670c8;--red:#cf303b;--lime:#b3c933;--ink:#3d4146;--bg:#f6f7f8}.stApp{background:var(--bg);color:var(--ink)}.block-container{max-width:1180px;padding-top:1.3rem}.hero h1{margin:0;color:var(--blue);font-size:26px;font-style:italic}.hero p{margin:.2rem 0;color:#697078}.huddle{font-size:28px;color:var(--lime);font-weight:800;font-style:italic;margin:1rem 0}.sect{font-size:20px;font-weight:800;font-style:italic;margin:1rem 0 .4rem}.loc{font-weight:800;font-style:italic}.staffbox{background:#f1f4f7;border-radius:8px;min-height:42px;padding:10px 9px;line-height:1.2}.closed{background:#fde8e8;color:#9f1d24;font-weight:800}.small{font-size:12px;color:#697078}.stTextInput input{background:#fffdf4}.stTextInput input[type=number]::-webkit-inner-spin-button,.stTextInput input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}.stTextInput input[type=number]{-moz-appearance:textfield}.stButton button{border-radius:6px}button[kind=primary]{background:var(--blue)}div[data-testid=stDataFrame]{background:white;border-radius:8px}
</style>''',unsafe_allow_html=True)

def config():
    root=load_root(); cfg=root.setdefault('staffhuddle_config',{})
    if not cfg.get('locations'):
        cfg['locations']=[{'id':str(uuid.uuid4()),'name':x,'active':True} for x in DEFAULT_LOCATIONS]
    if not cfg.get('roster'):
        roster=[]
        for role,people in BASELINE.items():
            rr='MA' if role=='MA' else role
            for name in people:
                roster.append({'id':str(uuid.uuid4()),'name':name,'role':rr,'active':True,'allowed_locations':DEFAULT_LOCATIONS[:]})
        cfg['roster']=roster
    return root,cfg

def week_of(d):
    anchor=date(2026,10,4); return ((d-anchor).days//7)%4+1

def slot_key(d,s): return f"{week_of(d)}-{d.strftime('%a')}-{s}"
def matches(v,loc): return ALIASES.get(loc,loc).lower() in str(v).lower()
def active_locations(cfg): return [x['name'] for x in cfg['locations'] if x.get('active',True)]
def active_roster(cfg,role=None): return [p for p in cfg['roster'] if p.get('active',True) and (not role or p['role']==role)]

def baseline_staff(d,session,cfg):
    sessions=['AM','PM'] if session=='BOTH' else [session]
    locs=active_locations(cfg); out={l:{r:[] for r in ROLE_ORDER} for l in locs}
    names={p['name']:p for p in active_roster(cfg)}
    for role,people in BASELINE.items():
        rr='MA' if role=='MA' else role
        for name,pattern in people.items():
            if name not in names: continue
            for s in sessions:
                assignment=pattern.get(slot_key(d,s),'n/a')
                for loc in locs:
                    if matches(assignment,loc) and name not in out[loc][rr]: out[loc][rr].append(name)
    return out

def current_exceptions(d):
    ds=str(d); return [e for e in load_exceptions() if e.get('start','')<=ds<=e.get('end','')]

def apply_time_off(staff,d,cfg):
    ex=current_exceptions(d); off={e['person'] for e in ex}; closed=[]; released=[]
    for loc in list(staff):
        had_md=bool(staff[loc]['MD'])
        for role in ROLE_ORDER:
            staff[loc][role]=[n for n in staff[loc][role] if n not in off]
        if had_md and not staff[loc]['MD']:
            closed.append(loc)
            for role in ROLE_ORDER[1:]:
                released += [(n,role,loc) for n in staff[loc][role]]
                staff[loc][role]=[]
    # role-matched redeployment to highest entered workload; preference comes from allowed locations
    metrics=st.session_state.get('record',{}).get('metrics',{})
    roster={p['name']:p for p in active_roster(cfg)}
    for name,role,origin in released:
        p=roster.get(name,{}); allowed=p.get('allowed_locations',active_locations(cfg))
        candidates=[l for l in active_locations(cfg) if l not in closed and l in allowed]
        if candidates:
            def need(l):
                m=metrics.get(l,{})
                vol=sum(int(m.get(k) or 0) for k in METRICS)
                gap=12 if not staff[l][role] else 0
                return vol+gap
            target=max(candidates,key=need); staff[target][role].append(name)
    return staff,ex,closed

def save_cfg(root,cfg): root['staffhuddle_config']=cfg; save_root(root)

def admin_panel(root,cfg):
    with st.expander('Administration',expanded=False):
        t1,t2=st.tabs(['Roster','Locations'])
        with t1:
            st.caption('Add, edit, activate, or deactivate staff. Roles and allowed locations drive scheduling and time-off dropdowns.')
            locs=[x['name'] for x in cfg['locations']]
            edited=st.data_editor(cfg['roster'],use_container_width=True,num_rows='dynamic',hide_index=True,column_config={
                'id':None,'name':st.column_config.TextColumn('Name',required=True),'role':st.column_config.SelectboxColumn('Job',options=ROLE_ORDER,required=True),'active':st.column_config.CheckboxColumn('Active'),'allowed_locations':st.column_config.ListColumn('Allowed locations')
            },key='roster_editor')
            if st.button('Save roster',type='primary'):
                for p in edited:
                    p.setdefault('id',str(uuid.uuid4())); p.setdefault('allowed_locations',locs)
                cfg['roster']=edited; save_cfg(root,cfg); st.success('Roster saved.'); st.rerun()
        with t2:
            st.caption('Locations are editable and can be deactivated without deleting historical huddles.')
            edited_l=st.data_editor(cfg['locations'],use_container_width=True,num_rows='dynamic',hide_index=True,column_config={'id':None,'name':st.column_config.TextColumn('Location',required=True),'active':st.column_config.CheckboxColumn('Active')},key='loc_editor')
            if st.button('Save locations',type='primary'):
                for x in edited_l: x.setdefault('id',str(uuid.uuid4()))
                cfg['locations']=edited_l; save_cfg(root,cfg); st.success('Locations saved.'); st.rerun()

root,cfg=config()
st.markdown('<div class="hero"><h1>Pediatric Cardiology Daily Huddle</h1><p>Daily counts and same-day staffing save to the existing Google Drive JSON.</p></div>',unsafe_allow_html=True)
c=st.columns([1.4,1,1])
with c[0]: selected=st.date_input('Date',date.today(),format='MM/DD/YYYY')
with c[1]: session=st.selectbox('Session',['BOTH','AM','PM'],format_func=lambda x:'AM + PM' if x=='BOTH' else x)
with c[2]: admin=st.toggle('Admin mode',False)
if admin: admin_panel(root,cfg)
key=f'{selected}|{session}'
if st.session_state.get('record_key')!=key:
    st.session_state.record_key=key; st.session_state.record=load_huddle(str(selected),session)
record=st.session_state.record; record.setdefault('metrics',{}); record.setdefault('footer',{'Admin':'Jackie, Heather','Hospital':'Kim','On Leave':'','Remote':'Tia, Nicole','Off':''})
locs=active_locations(cfg)
st.markdown(f'<div class="huddle">Daily Huddle: {selected.strftime("%A %B %d, %Y")} 🌼</div>',unsafe_allow_html=True)

st.markdown('<div class="sect" style="color:#2670c8">Locations</div>',unsafe_allow_html=True)
h=st.columns([1.35,1,1,1,1,1,1])
for col,label in zip(h,['Locations:']+METRICS): col.markdown(f'**_{label}_**')
for i,loc in enumerate(locs):
    row=st.columns([1.35,1,1,1,1,1,1]); row[0].markdown(f'<span class="loc" style="color:{COLORS[i%len(COLORS)]}">{loc}</span>',unsafe_allow_html=True)
    record['metrics'].setdefault(loc,{})
    for j,m in enumerate(METRICS,1):
        record['metrics'][loc][m]=row[j].text_input(f'{loc}-{m}',value=str(record['metrics'][loc].get(m,'') or ''),label_visibility='collapsed',placeholder='0',key=f'm-{key}-{loc}-{m}')

staff=record.get('staffing') or baseline_staff(selected,session,cfg)
staff,exceptions,closed=apply_time_off(deepcopy(staff),selected,cfg)
st.markdown('<div class="sect" style="color:#cf303b">Staff Scheduling</div>',unsafe_allow_html=True)
h=st.columns([1.35,1.2,1,1,1.35,1,1])
for col,label in zip(h,['Staff Scheduling:','MD','RN','MA','Sonographers','FOS','Call Center']): col.markdown(f'**_{label}_**')
for i,loc in enumerate(locs):
    row=st.columns([1.35,1.2,1,1,1.35,1,1]); row[0].markdown(f'<span class="loc" style="color:{COLORS[i%len(COLORS)]}">{loc}</span>',unsafe_allow_html=True)
    for j,role in enumerate(ROLE_ORDER,1):
        text='CLOSED' if loc in closed and role=='MD' else ', '.join(staff.get(loc,{}).get(role,[]))
        klass='staffbox closed' if loc in closed else 'staffbox'
        row[j].markdown(f'<div class="{klass}">{text or "&nbsp;"}</div>',unsafe_allow_html=True)
    row[6].markdown('<div class="staffbox">&nbsp;</div>',unsafe_allow_html=True)

with st.expander('Edit today’s staffing',expanded=False):
    st.caption('Always available. Changes affect only the selected huddle record, not the roster or recurring baseline.')
    for loc in locs:
        st.markdown(f'**{loc}**')
        cols=st.columns(5)
        for idx,role in enumerate(ROLE_ORDER):
            opts=[p['name'] for p in active_roster(cfg,role)]
            current=staff.get(loc,{}).get(role,[])
            staff.setdefault(loc,{}).setdefault(role,[])
            staff[loc][role]=cols[idx].multiselect(ROLE_LABEL[role],opts,default=[x for x in current if x in opts],key=f'edit-{key}-{loc}-{role}')
    if st.button('Apply staffing edits',type='primary'):
        record['staffing']=staff; st.success('Staffing edits applied. Save the huddle to persist them.')

with st.expander('Time off and coverage',expanded=True):
    roster=active_roster(cfg); roles=sorted(set(p['role'] for p in roster))
    form=st.columns([1,1.5,1,1])
    role=form[0].selectbox('Job',roles,key='exrole')
    people=[p['name'] for p in roster if p['role']==role]
    person=form[1].selectbox('Person',people,key='experson')
    start=form[2].date_input('From',selected,key='exstart'); end=form[3].date_input('To',selected,key='exend')
    if st.button('Add time off'):
        all_ex=load_exceptions(); all_ex.append({'id':str(uuid.uuid4()),'person':person,'role':role,'start':str(start),'end':str(end),'location':'','replacement':''}); save_exceptions(all_ex); st.success('Time off added.'); st.rerun()
    if exceptions:
        st.markdown('**Off for this date**')
        for e in exceptions:
            a,b=st.columns([6,1]); a.write(f"{e['person']} · {e['role']} · {e['start']} to {e['end']}")
            if b.button('Reinstate',key=f"reinstate-{e.get('id',e['person']+e['start'])}"):
                all_ex=load_exceptions(); all_ex=[x for x in all_ex if not (x.get('person')==e.get('person') and x.get('start')==e.get('start') and x.get('end')==e.get('end'))]; save_exceptions(all_ex); st.rerun()
    else: st.caption('No one is off for this date.')

f=st.columns([1.3,.8,1.1,.8])
for col,label in zip(f,['Admin','Hospital','On Leave','Off']): record['footer'][label]=col.text_input(label,record['footer'].get(label,''),key=f'f-{key}-{label}')
record['footer']['Remote']=st.text_input('Remote',record['footer'].get('Remote',''),key=f'f-{key}-Remote')
btn=st.columns([1,1,4])
if btn[0].button('Save huddle',type='primary',use_container_width=True):
    record.update({'date':str(selected),'session':session,'staffing':staff,'saved_at':datetime.now().isoformat(timespec='seconds')}); save_huddle(str(selected),session,record); st.success('Saved to Google Drive JSON.')
if btn[1].button('Reload saved',use_container_width=True): st.session_state.record=load_huddle(str(selected),session); st.rerun()
st.caption('Planning recommendation only. Confirm clinic closures, qualifications, leave, travel constraints, and final staffing before operational use.')

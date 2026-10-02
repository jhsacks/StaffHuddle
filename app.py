import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import uuid
import streamlit as st
from streamlit_sortables import sort_items
from storage import load_root, save_root, load_huddle, save_huddle, load_exceptions, save_exceptions

st.set_page_config(page_title='Pediatric Cardiology Daily Huddle', page_icon='🌼', layout='wide')
BASELINE=json.loads((Path(__file__).parent/'data'/'baseline.json').read_text())
DEFAULT_LOCATIONS=['Kennesaw','Smyrna','Douglasville','Avalon','LaGrange','New Hope','Woodstock']
ROLES=['MD','RN','MA','SON','FOS']
LABEL={'MD':'MD','RN':'RN','MA':'MA','SON':'Sonographers','FOS':'FOS'}
METRICS=['Clinic/Patients','Echoes','Stress Tests','Nurse Visits','Video Visit','Fetal']
ALIASES={'Kennesaw':'Barrett','New Hope':'Paulding','LaGrange':'Lagrange'}
COLORS=['#efa51b','#17945a','#d12f84','#6c8f42','#277b7f','#b3c933','#df4a20']

st.markdown('''<style>
:root{--blue:#2670c8;--red:#cf303b;--lime:#b3c933;--ink:#3d4146;--bg:#f6f7f8}.stApp{background:var(--bg);color:var(--ink)}.block-container{max-width:1220px;padding-top:1.3rem}.hero h1{margin:0;color:var(--blue);font-size:26px;font-style:italic}.hero p{margin:.2rem 0;color:#697078}.huddle{font-size:28px;color:var(--lime);font-weight:800;font-style:italic;margin:1rem 0}.sect{font-size:20px;font-weight:800;font-style:italic;margin:1rem 0 .4rem}.loc{font-weight:800;font-style:italic}.staffbox{background:#f1f4f7;border-radius:8px;min-height:42px;padding:10px 9px;line-height:1.2}.closed{background:#fde8e8;color:#9f1d24;font-weight:800}.ok{color:#177245}.warn{color:#a15c00}.bad{color:#b4232d;font-weight:700}.panel{background:white;border:1px solid #d9dfe5;border-radius:9px;padding:12px}.stTextInput input{background:#fffdf4}.stButton button{border-radius:6px}button[kind=primary]{background:var(--blue)}
.sortable-component{display:flex!important;gap:8px;overflow-x:auto;padding-bottom:6px}.sortable-container{background:#f1f4f7!important;border:1px solid #d9dfe5!important;border-radius:8px!important;min-width:145px!important;padding:7px!important}.sortable-container-header{font-weight:700!important;color:#3d4146!important;font-size:13px!important}.sortable-item{background:white!important;border:1px solid #cbd5df!important;border-radius:6px!important;padding:7px 9px!important;margin:5px 0!important;box-shadow:0 1px 2px #0001!important;cursor:grab!important}
</style>''',unsafe_allow_html=True)

def get_config():
    root=load_root(); cfg=root.setdefault('staffhuddle_config',{})
    cfg.setdefault('locations',[{'id':str(uuid.uuid4()),'name':x,'active':True} for x in DEFAULT_LOCATIONS])
    if not cfg.get('roster'):
        cfg['roster']=[]
        for role,people in BASELINE.items():
            for name in people:
                cfg['roster'].append({'id':str(uuid.uuid4()),'name':name,'role':role,'active':True,'allowed_locations':DEFAULT_LOCATIONS[:]})
    return root,cfg

def active_locations(cfg): return [x['name'] for x in cfg['locations'] if x.get('active',True)]
def active_roster(cfg,role=None): return [p for p in cfg['roster'] if p.get('active',True) and (role is None or p['role']==role)]
def week_of(d): return ((d-date(2026,10,4)).days//7)%4+1
def slot_key(d,s): return f"{week_of(d)}-{d.strftime('%a')}-{s}"
def matches(v,loc): return ALIASES.get(loc,loc).lower() in str(v).lower()

def baseline_staff(d,session,cfg):
    sessions=['AM','PM'] if session=='BOTH' else [session]; locs=active_locations(cfg)
    out={l:{r:[] for r in ROLES} for l in locs}; valid={p['name'] for p in active_roster(cfg)}
    for role,people in BASELINE.items():
        for name,pattern in people.items():
            if name not in valid: continue
            for s in sessions:
                assignment=pattern.get(slot_key(d,s),'n/a')
                for loc in locs:
                    if matches(assignment,loc) and name not in out[loc][role]: out[loc][role].append(name)
    return out

def exceptions_for(d):
    ds=str(d); return [e for e in load_exceptions() if e.get('start','')<=ds<=e.get('end','')]

def normalize_staff(staff,locs):
    result={l:{r:[] for r in ROLES} for l in locs}
    for l in locs:
        for r in ROLES: result[l][r]=list(dict.fromkeys(staff.get(l,{}).get(r,[])))
    return result

def assigned_names(staff): return {n for l in staff.values() for names in l.values() for n in names}

def auto_rebalance(staff,off,staff_only,cfg):
    locs=active_locations(cfg); staff=normalize_staff(staff,locs); changes=[]
    for loc in locs:
        for role in ROLES: staff[loc][role]=[n for n in staff[loc][role] if n not in off]
    # Locations without MD close unless explicitly opened staff-only.
    closed={l for l in locs if not staff[l]['MD'] and l not in staff_only}
    pool=[]
    for loc in closed:
        for role in ROLES[1:]:
            for n in staff[loc][role]: pool.append((n,role,loc))
            staff[loc][role]=[]
    roster={p['name']:p for p in active_roster(cfg)}
    def eligible(n,loc): return loc in roster.get(n,{}).get('allowed_locations',locs)
    def move_candidate(role,loc,allow_sub=False):
        exact=[x for x in pool if x[1]==role and eligible(x[0],loc)]
        if exact: return exact[0]
        if allow_sub and role=='MA':
            rn=[x for x in pool if x[1]=='RN' and eligible(x[0],loc)]
            if rn: return rn[0]
        return None
    # Open physician clinics only: MA or RN, one SON per MD, one FOS.
    for loc in locs:
        if loc in closed or loc in staff_only: continue
        md=len(staff[loc]['MD'])
        if not md: continue
        if not (staff[loc]['MA'] or staff[loc]['RN']):
            pick=move_candidate('MA',loc,True)
            if pick:
                pool.remove(pick); name,role,origin=pick; staff[loc][role].append(name); changes.append(f'{name}: {origin} → {loc} ({role} support)')
        while len(staff[loc]['SON'])<md:
            pick=move_candidate('SON',loc)
            if not pick: break
            pool.remove(pick); name,role,origin=pick; staff[loc][role].append(name); changes.append(f'{name}: {origin} → {loc} (SON)')
        if not staff[loc]['FOS']:
            pick=move_candidate('FOS',loc)
            if pick:
                pool.remove(pick); name,role,origin=pick; staff[loc][role].append(name); changes.append(f'{name}: {origin} → {loc} (FOS)')
    return staff,closed,pool,changes

def coverage(staff,closed,staff_only):
    rows=[]
    for loc in staff:
        md=len(staff[loc]['MD']); support=len(staff[loc]['MA'])+len(staff[loc]['RN']); son=len(staff[loc]['SON']); fos=len(staff[loc]['FOS'])
        if loc in closed: status='CLOSED'
        elif loc in staff_only: status='STAFF-ONLY OPEN'
        else:
            issues=[]
            if md and support<1: issues.append('MA/RN')
            if md and son<md: issues.append(f'SON {son}/{md}')
            if md and fos<1: issues.append('FOS')
            status='COVERED' if md and not issues else ('MISSING '+', '.join(issues) if md else 'NO MD')
        rows.append({'Location':loc,'MD':md,'MA/RN':support,'SON':son,'FOS':fos,'Coverage':status})
    return rows

def admin_panel(root,cfg):
    with st.expander('Administration',False):
        t1,t2=st.tabs(['Roster','Locations'])
        with t1:
            locs=[x['name'] for x in cfg['locations']]
            edited=st.data_editor(cfg['roster'],num_rows='dynamic',use_container_width=True,hide_index=True,column_config={'id':None,'name':st.column_config.TextColumn('Name',required=True),'role':st.column_config.SelectboxColumn('Job',options=ROLES,required=True),'active':st.column_config.CheckboxColumn('Active'),'allowed_locations':st.column_config.ListColumn('Allowed locations')})
            if st.button('Save roster',type='primary'):
                for p in edited: p.setdefault('id',str(uuid.uuid4())); p.setdefault('allowed_locations',locs)
                cfg['roster']=edited; root['staffhuddle_config']=cfg; save_root(root); st.rerun()
        with t2:
            edited=st.data_editor(cfg['locations'],num_rows='dynamic',use_container_width=True,hide_index=True,column_config={'id':None,'name':st.column_config.TextColumn('Location',required=True),'active':st.column_config.CheckboxColumn('Active')})
            if st.button('Save locations',type='primary'):
                for x in edited: x.setdefault('id',str(uuid.uuid4()))
                cfg['locations']=edited; root['staffhuddle_config']=cfg; save_root(root); st.rerun()

def drag_board(staff,cfg,locs,key):
    off={e['person'] for e in exceptions_for(selected)}; all_assigned=assigned_names(staff)
    updated=deepcopy(staff)
    st.markdown('<div class="sect" style="color:#cf303b">Drag-and-drop Staff Scheduling</div>',unsafe_allow_html=True)
    st.caption('Drag names between clinic lanes and Unassigned. Each board is role-locked. Click Save huddle when finished.')
    style='.sortable-component{display:flex;gap:8px;overflow-x:auto}.sortable-container{min-width:140px;background:#f1f4f7;border-radius:8px;padding:6px}.sortable-item{background:white;border:1px solid #ccd5dd;border-radius:6px;padding:7px;margin:5px 0}'
    for role in ROLES:
        st.markdown(f'**{LABEL[role]}**')
        assigned_role={n for l in locs for n in staff[l][role]}
        available=[p['name'] for p in active_roster(cfg,role) if p['name'] not in off and p['name'] not in assigned_role]
        containers=[{'header':loc,'items':staff[loc][role]} for loc in locs]+[{'header':'Unassigned','items':available}]
        result=sort_items(containers,multi_containers=True,direction='horizontal',custom_style=style,key=f'dnd-{key}-{role}')
        for loc in locs: updated[loc][role]=[]
        for bucket in result:
            if bucket['header'] in locs: updated[bucket['header']][role]=bucket['items']
    return updated

root,cfg=get_config(); locs=active_locations(cfg)
st.markdown('<div class="hero"><h1>Pediatric Cardiology Daily Huddle</h1><p>Daily counts and staffing save to the existing Google Drive JSON.</p></div>',unsafe_allow_html=True)
c=st.columns([1.4,1,1])
with c[0]: selected=st.date_input('Date',date.today(),format='MM/DD/YYYY')
with c[1]: session=st.selectbox('Session',['BOTH','AM','PM'],format_func=lambda x:'AM + PM' if x=='BOTH' else x)
with c[2]: admin=st.toggle('Admin mode',False)
if admin: admin_panel(root,cfg)
key=f'{selected}|{session}'
if st.session_state.get('record_key')!=key:
    st.session_state.record_key=key; st.session_state.record=load_huddle(str(selected),session)
record=st.session_state.record; record.setdefault('metrics',{}); record.setdefault('footer',{'Admin':'Jackie, Heather','Hospital':'Kim','On Leave':'','Remote':'Tia, Nicole','Off':''})
record.setdefault('staff_only_locations',[])
st.markdown(f'<div class="huddle">Daily Huddle: {selected.strftime("%A %B %d, %Y")} 🌼</div>',unsafe_allow_html=True)

st.markdown('<div class="sect" style="color:#2670c8">Locations</div>',unsafe_allow_html=True)
h=st.columns([1.35,1,1,1,1,1,1])
for col,label in zip(h,['Locations:']+METRICS): col.markdown(f'**_{label}_**')
for i,loc in enumerate(locs):
    row=st.columns([1.35,1,1,1,1,1,1]); row[0].markdown(f'<span class="loc" style="color:{COLORS[i%len(COLORS)]}">{loc}</span>',unsafe_allow_html=True)
    record['metrics'].setdefault(loc,{})
    for j,m in enumerate(METRICS,1): record['metrics'][loc][m]=row[j].text_input(f'{loc}-{m}',str(record['metrics'][loc].get(m,'') or ''),label_visibility='collapsed',placeholder='0',key=f'm-{key}-{loc}-{m}')

base=record.get('staffing') or baseline_staff(selected,session,cfg); base=normalize_staff(base,locs)
off={e['person'] for e in exceptions_for(selected)}
# Apply absence removal before drag board.
for loc in locs:
    for role in ROLES: base[loc][role]=[n for n in base[loc][role] if n not in off]
staff=drag_board(base,cfg,locs,key)

with st.expander('Clinic operating overrides',False):
    st.caption('Normally, a location with no MD is closed. Select a location only when staff should work there without an onsite MD, such as an echo-only, hybrid, nurse, or administrative session.')
    record['staff_only_locations']=st.multiselect('Manually open without onsite MD',locs,default=[x for x in record['staff_only_locations'] if x in locs],key=f'staffonly-{key}')

staff,closed,pool,changes=auto_rebalance(staff,off,set(record['staff_only_locations']),cfg)
record['staffing']=staff

st.markdown('<div class="sect">Coverage Check</div>',unsafe_allow_html=True)
check=coverage(staff,closed,set(record['staff_only_locations']))
st.dataframe(check,use_container_width=True,hide_index=True)
if changes:
    st.info('Automatic changes: '+' | '.join(changes))

assigned=assigned_names(staff); off_names={e['person'] for e in exceptions_for(selected)}
unaccounted=[p for p in active_roster(cfg) if p['name'] not in assigned and p['name'] not in off_names]
left,right=st.columns(2)
with left:
    st.markdown('#### Unaccounted-for roster staff')
    if unaccounted:
        by={r:[] for r in ROLES}
        for p in unaccounted: by[p['role']].append(p['name'])
        for r in ROLES:
            if by[r]: st.warning(f"{LABEL[r]}: {', '.join(by[r])}")
    else: st.success('All active, available roster staff are accounted for.')
with right:
    st.markdown('#### Closed / special locations')
    if closed: st.error('Closed (no MD): '+', '.join(sorted(closed)))
    if record['staff_only_locations']: st.info('Manually open without onsite MD: '+', '.join(record['staff_only_locations']))
    if not closed and not record['staff_only_locations']: st.success('No closures or staff-only overrides.')

with st.expander('Time off and coverage',True):
    roster=active_roster(cfg); roles=sorted({p['role'] for p in roster}); cols=st.columns([1,1.5,1,1])
    role=cols[0].selectbox('Job',roles,key='exrole'); people=[p['name'] for p in roster if p['role']==role]
    person=cols[1].selectbox('Person',people,key='experson'); start=cols[2].date_input('From',selected,key='exstart'); end=cols[3].date_input('To',selected,key='exend')
    if st.button('Add time off'):
        ex=load_exceptions(); ex.append({'id':str(uuid.uuid4()),'person':person,'role':role,'start':str(start),'end':str(end),'location':'','replacement':''}); save_exceptions(ex); st.rerun()
    current=exceptions_for(selected)
    if current:
        st.markdown('**Off for this date**')
        for e in current:
            a,b=st.columns([6,1]); a.write(f"{e['person']} · {e['role']} · {e['start']} to {e['end']}")
            if b.button('Reinstate',key=f"reinstate-{e.get('id',e['person']+e['start'])}"):
                ex=load_exceptions(); ex=[x for x in ex if x.get('id')!=e.get('id')]; save_exceptions(ex); st.rerun()
    else: st.caption('No one is off for this date.')

f=st.columns([1.3,.8,1.1,.8])
for col,label in zip(f,['Admin','Hospital','On Leave','Off']): record['footer'][label]=col.text_input(label,record['footer'].get(label,''),key=f'f-{key}-{label}')
record['footer']['Remote']=st.text_input('Remote',record['footer'].get('Remote',''),key=f'f-{key}-Remote')
btn=st.columns([1,1,4])
if btn[0].button('Save huddle',type='primary',use_container_width=True):
    record.update({'date':str(selected),'session':session,'staffing':staff,'saved_at':datetime.now().isoformat(timespec='seconds')}); save_huddle(str(selected),session,record); st.success('Saved to Google Drive JSON.')
if btn[1].button('Reload saved',use_container_width=True): st.session_state.record=load_huddle(str(selected),session); st.rerun()
st.caption('Planning recommendation only. Confirm clinic closures, qualifications, leave, travel constraints, and final staffing before operational use.')

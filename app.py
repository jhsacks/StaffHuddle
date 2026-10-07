import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import uuid
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import streamlit as st
from storage import load_root, save_root, load_huddle, save_huddle, load_exceptions, save_exceptions

st.set_page_config(page_title='Pediatric Cardiology Daily Huddle', page_icon='🌼', layout='wide')
BASELINE=json.loads((Path(__file__).parent/'data'/'baseline.json').read_text())
DEFAULT_LOCATIONS=['Kennesaw','Smyrna','Douglasville','Avalon','LaGrange','New Hope','Woodstock']
SPECIAL_ROWS=['Hospital','Admin','Remote','Off']
ROLES=['MD','RN','MA','SON','FOS']
LABEL={'MD':'MD','RN':'RN','MA':'MA','SON':'Sonographers','FOS':'FOS'}
METRICS=['Clinic/Patients','Echoes','Stress Tests','Nurse Visits','Video Visit','Fetal']
ALIASES={'Kennesaw':'Barrett','New Hope':'Paulding','LaGrange':'Lagrange'}
COLORS=['#efa51b','#17945a','#d12f84','#6c8f42','#277b7f','#b3c933','#df4a20']
WEEKDAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']

st.markdown('''<style>
:root{--blue:#2670c8;--red:#cf303b;--lime:#b3c933;--ink:#3d4146;--bg:#f6f7f8}.stApp{background:var(--bg);color:var(--ink)}.block-container{max-width:1220px;padding-top:1.3rem}.hero h1{margin:0;color:var(--blue);font-size:26px;font-style:italic}.hero p{margin:.2rem 0;color:#697078}.huddle{font-size:28px;color:var(--lime);font-weight:800;font-style:italic;margin:1rem 0}.sect{font-size:20px;font-weight:800;font-style:italic;margin:1rem 0 .4rem}.loc{font-weight:800;font-style:italic}.staff-readout{background:#f1f4f7;border:1px solid #d9dfe5;border-radius:7px;min-height:44px;padding:9px;line-height:1.25;overflow-wrap:anywhere}.special{background:#e8f2ff}.off{background:#fde8e8;color:#9f1d24}.stTextInput input{background:#fffdf4}.stButton button{border-radius:6px}button[kind=primary]{background:var(--blue)}div[data-baseweb=select]{min-height:42px}div[data-baseweb=tag]{background:#eef4fb!important;color:#1d4d8f!important;font-size:.82rem!important}.alert-card{background:white;border:1px solid #d9dfe5;border-radius:8px;padding:10px 12px;margin-bottom:7px}.good{border-left:5px solid #24915f}.warn{border-left:5px solid #e0a000}.bad{border-left:5px solid #c6383f}.info{border-left:5px solid #2670c8}.special-divider{border-top:2px solid #b9c4ce;margin-top:5px;padding-top:8px}</style>''',unsafe_allow_html=True)

def list_value(v):
    if isinstance(v,list): return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').split(',') if x.strip()]

def csv_value(v): return ', '.join(list_value(v))

def get_config():
    root=load_root(); cfg=root.setdefault('staffhuddle_config',{})
    cfg.setdefault('locations',[{'id':str(uuid.uuid4()),'name':x,'active':True} for x in DEFAULT_LOCATIONS])
    if not cfg.get('roster'):
        cfg['roster']=[]
        for role,people in BASELINE.items():
            for name in people:
                cfg['roster'].append({'id':str(uuid.uuid4()),'name':name,'role':role,'active':True,'allowed_locations':DEFAULT_LOCATIONS[:],'work_days':WEEKDAYS[:5]})
    # One-time migration for known part-time MA workdays.
    if not cfg.get('part_time_workdays_v1'):
        for p in cfg['roster']:
            p.setdefault('work_days',WEEKDAYS[:5])
            if p.get('role')=='MA' and p.get('name')=='Dara': p['work_days']=['Tue','Thu','Fri']
            if p.get('role')=='MA' and p.get('name')=='Danielle': p['work_days']=['Mon','Wed']
        cfg['part_time_workdays_v1']=True
        root['staffhuddle_config']=cfg; save_root(root)
    for p in cfg['roster']:
        p.setdefault('work_days',WEEKDAYS[:5]); p.setdefault('allowed_locations',DEFAULT_LOCATIONS[:])
    return root,cfg

def active_locations(cfg): return [x['name'] for x in cfg['locations'] if x.get('active',True)]
def active_roster(cfg,role=None): return [p for p in cfg['roster'] if p.get('active',True) and (role is None or p.get('role')==role)]
def weekday(d): return d.strftime('%a')
def available_on(p,d): return weekday(d) in list_value(p.get('work_days',WEEKDAYS[:5]))
def week_of(d): return ((d-date(2026,10,4)).days//7)%4+1
def slot_key(d,s): return f"{week_of(d)}-{d.strftime('%a')}-{s}"
def matches(v,loc): return ALIASES.get(loc,loc).lower() in str(v).lower()

def baseline_staff(d,session,cfg):
    sessions=['AM','PM'] if session=='BOTH' else [session]; locs=active_locations(cfg)
    out={l:{r:[] for r in ROLES} for l in locs}; roster={p['name']:p for p in active_roster(cfg)}
    for role,people in BASELINE.items():
        for name,pattern in people.items():
            p=roster.get(name)
            if not p or not available_on(p,d): continue
            for s in sessions:
                assignment=pattern.get(slot_key(d,s),'n/a')
                for loc in locs:
                    if matches(assignment,loc) and name not in out[loc][role]: out[loc][role].append(name)
    return out

def exceptions_for(d):
    ds=str(d); return [e for e in load_exceptions() if e.get('start','')<=ds<=e.get('end','')]

def normalize_staff(staff,locs):
    out={l:{r:[] for r in ROLES} for l in locs}
    for l in locs:
        for r in ROLES: out[l][r]=list(dict.fromkeys(staff.get(l,{}).get(r,[])))
    return out

def normalize_special(special):
    out={x:{r:[] for r in ROLES} for x in SPECIAL_ROWS}
    for x in SPECIAL_ROWS:
        for r in ROLES: out[x][r]=list(dict.fromkeys(special.get(x,{}).get(r,[])))
    return out

def all_assigned(staff,special): return {n for rows in list(staff.values())+list(special.values()) for names in rows.values() for n in names}

def dedupe_assignments(staff,special):
    seen=set(); removed=[]
    for row in list(staff.values())+list(special.values()):
        for role in ROLES:
            keep=[]
            for name in row[role]:
                if name in seen: removed.append(name)
                else: seen.add(name); keep.append(name)
            row[role]=keep
    return staff,special,sorted(set(removed))

def auto_rebalance(staff,special,off_names,staff_only,cfg,d):
    locs=active_locations(cfg); staff=normalize_staff(staff,locs); special=normalize_special(special); changes=[]
    roster={p['name']:p for p in active_roster(cfg)}
    unavailable={name for name,p in roster.items() if not available_on(p,d)}
    excluded=off_names|unavailable|set(sum([special[x][r] for x in ['Hospital','Admin','Remote'] for r in ROLES],[]))
    for loc in locs:
        for role in ROLES: staff[loc][role]=[n for n in staff[loc][role] if n not in excluded]
    closed={l for l in locs if not staff[l]['MD'] and l not in staff_only}
    pool=[]
    for loc in closed:
        for role in ROLES[1:]:
            for n in staff[loc][role]: pool.append((n,role,loc))
            staff[loc][role]=[]
    assigned=all_assigned(staff,special)
    for p in roster.values():
        if available_on(p,d) and p['name'] not in assigned and p['name'] not in off_names:
            pool.append((p['name'],p['role'],'Unassigned'))
    def eligible(n,loc): return available_on(roster[n],d) and loc in list_value(roster[n].get('allowed_locations',locs))
    def pick(role,loc,sub=False):
        exact=[x for x in pool if x[1]==role and eligible(x[0],loc)]
        if exact:return exact[0]
        if sub:
            rn=[x for x in pool if x[1]=='RN' and eligible(x[0],loc)]
            if rn:return rn[0]
        return None
    for loc in locs:
        if loc in closed or loc in staff_only: continue
        md=len(staff[loc]['MD'])
        if not md: continue
        if not (staff[loc]['MA'] or staff[loc]['RN']):
            x=pick('MA',loc,True)
            if x: pool.remove(x); staff[loc][x[1]].append(x[0]); changes.append(f'{x[0]}: {x[2]} → {loc} ({x[1]} support)')
        while len(staff[loc]['SON'])<md:
            x=pick('SON',loc)
            if not x: break
            pool.remove(x); staff[loc]['SON'].append(x[0]); changes.append(f'{x[0]}: {x[2]} → {loc} (SON)')
        if not staff[loc]['FOS']:
            x=pick('FOS',loc)
            if x: pool.remove(x); staff[loc]['FOS'].append(x[0]); changes.append(f'{x[0]}: {x[2]} → {loc} (FOS)')
    special['Off']={r:[] for r in ROLES}
    for name in off_names:
        if name in roster: special['Off'][roster[name]['role']].append(name)
    return staff,special,closed,pool,changes

def coverage(staff,closed,staff_only):
    rows=[]
    for loc in staff:
        md=len(staff[loc]['MD']); support=len(staff[loc]['MA'])+len(staff[loc]['RN']); son=len(staff[loc]['SON']); fos=len(staff[loc]['FOS'])
        issues=[]
        if md and support<1: issues.append('MA/RN')
        if md and son<md: issues.append(f'SON {son}/{md}')
        if md and fos<1: issues.append('FOS')
        status='CLOSED' if loc in closed else ('STAFF-ONLY OPEN' if loc in staff_only else ('COVERED' if md and not issues else ('MISSING '+', '.join(issues) if md else 'NO MD')))
        rows.append((loc,status))
    return rows

def admin_panel(root,cfg):
    with st.expander('Administration',False):
        rt,lt=st.tabs(['Roster','Locations'])
        with rt:
            editable=[]
            for p in cfg['roster']:
                q=deepcopy(p); q['allowed_locations']=csv_value(q.get('allowed_locations')); q['work_days']=csv_value(q.get('work_days')); editable.append(q)
            edited=st.data_editor(editable,num_rows='dynamic',use_container_width=True,hide_index=True,column_config={'id':None,'name':st.column_config.TextColumn('Name',required=True),'role':st.column_config.SelectboxColumn('Job',options=ROLES,required=True),'active':st.column_config.CheckboxColumn('Active'),'work_days':st.column_config.TextColumn('Work days (Mon,Tue,Wed...)'),'allowed_locations':st.column_config.TextColumn('Allowed locations')})
            if st.button('Save roster',type='primary'):
                for p in edited: p.setdefault('id',str(uuid.uuid4())); p['work_days']=list_value(p.get('work_days')); p['allowed_locations']=list_value(p.get('allowed_locations'))
                cfg['roster']=edited; root['staffhuddle_config']=cfg; save_root(root); st.rerun()
        with lt:
            edited=st.data_editor(cfg['locations'],num_rows='dynamic',use_container_width=True,hide_index=True,column_config={'id':None,'name':st.column_config.TextColumn('Location',required=True),'active':st.column_config.CheckboxColumn('Active')})
            if st.button('Save locations',type='primary'):
                for x in edited:x.setdefault('id',str(uuid.uuid4()))
                cfg['locations']=edited; root['staffhuddle_config']=cfg; save_root(root); st.rerun()

def owner_map(staff,special):
    owners={}
    for loc,row in staff.items():
        for role in ROLES:
            for n in row[role]: owners.setdefault(n,(loc,role))
    for loc,row in special.items():
        for role in ROLES:
            for n in row[role]: owners.setdefault(n,(loc,role))
    return owners

def assignment_grid(staff,special,cfg,locs,key,edit,d,off_names):
    owners=owner_map(staff,special); taken=set(); duplicates=[]
    headers=st.columns([1.22,1.24,1.08,1.08,1.45,1.08])
    for c,t in zip(headers,['Location','MD','RN','MA','Sonographers','FOS']): c.markdown(f'**_{t}_**')
    def render_row(name,row,special_row=False,off_row=False):
        nonlocal taken
        cols=st.columns([1.22,1.24,1.08,1.08,1.45,1.08]); cols[0].markdown(f'**{name}**')
        for i,role in enumerate(ROLES,1):
            current=[]
            for n in row[role]:
                if n in taken: duplicates.append(n)
                else: current.append(n); taken.add(n)
            row[role]=current
            klass='staff-readout '+('off' if off_row else ('special' if special_row else ''))
            cols[i].markdown(f'<div class="{klass}">{", ".join(current) if current else "—"}</div>',unsafe_allow_html=True)
            if edit and not off_row:
                choices=[]
                for p in active_roster(cfg,role):
                    if not available_on(p,d) or p['name'] in off_names: continue
                    own=owners.get(p['name'])
                    if own is None or own==(name,role): choices.append(p['name'])
                selected=cols[i].multiselect(f'{name}-{role}',choices,default=[n for n in current if n in choices],label_visibility='collapsed',key=f'a-{key}-{name}-{role}')
                # ID-level uniqueness: a widget cannot select someone owned by another cell.
                row[role]=selected
        return row
    for i,loc in enumerate(locs):
        staff[loc]=render_row(loc,staff[loc])
    st.markdown('<div class="special-divider"></div>',unsafe_allow_html=True)
    for x in SPECIAL_ROWS:
        special[x]=render_row(x,special[x],True,x=='Off')
    return staff,special,sorted(set(duplicates))



def _font(size, bold=False):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, width):
    words = str(text or '').split()
    if not words:
        return ['']
    lines, current = [], words[0]
    for word in words[1:]:
        trial = current + ' ' + word
        if draw.textbbox((0, 0), trial, font=font)[2] <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_table(draw, x, y, widths, headers, rows, header_fill, first_col_colors=None):
    header_font = _font(24, True)
    body_font = _font(22)
    body_bold = _font(22, True)
    pad = 8
    header_h = 44

    xx = x
    for label, col_width in zip(headers, widths):
        draw.rounded_rectangle(
            (xx, y, xx + col_width, y + header_h),
            radius=4,
            fill=header_fill,
            outline='#c4ccd4',
            width=1,
        )
        draw.text((xx + pad, y + 9), label, font=header_font, fill='white')
        xx += col_width

    y += header_h
    for row_index, row in enumerate(rows):
        wrapped = []
        max_lines = 1
        for value, col_width in zip(row, widths):
            lines = _wrap(draw, value if value else '—', body_font, col_width - (2 * pad))
            wrapped.append(lines)
            max_lines = max(max_lines, len(lines))

        row_h = max(38, 8 + max_lines * 25)
        xx = x
        for col_index, (lines, col_width) in enumerate(zip(wrapped, widths)):
            fill = '#ffffff' if row_index % 2 == 0 else '#f5f7f9'
            if first_col_colors and col_index == 0:
                fill = first_col_colors[row_index]
            draw.rectangle(
                (xx, y, xx + col_width, y + row_h),
                fill=fill,
                outline='#cbd3da',
                width=1,
            )
            color = '#ffffff' if first_col_colors and col_index == 0 else '#343a40'
            font = body_bold if col_index == 0 else body_font
            for line_index, line in enumerate(lines):
                draw.text(
                    (xx + pad, y + 5 + line_index * 25),
                    line,
                    font=font,
                    fill=color,
                )
            xx += col_width
        y += row_h
    return y


def huddle_png(d, metrics, staff, special, locs):
    margin = 18
    metric_widths = [150, 145, 115, 135, 130, 125, 105]
    staffing_widths = [135, 155, 145, 145, 220, 155]
    width = max(sum(metric_widths), sum(staffing_widths)) + (2 * margin)

    title_font = _font(32, True)
    subtitle_font = _font(22, True)
    small_font = _font(15)
    table_font = _font(22)

    probe = Image.new('RGB', (width, 100), 'white')
    pd = ImageDraw.Draw(probe)

    metric_rows = [
        [loc] + [str(metrics.get(loc, {}).get(metric, '') or '—') for metric in METRICS]
        for loc in locs
    ]
    staffing_rows = []
    for loc in locs + SPECIAL_ROWS:
        row = staff[loc] if loc in staff else special[loc]
        staffing_rows.append([loc] + [', '.join(row[role]) or '—' for role in ROLES])

    def table_height(rows, widths):
        total = 44
        for row in rows:
            max_lines = 1
            for value, col_width in zip(row, widths):
                max_lines = max(
                    max_lines,
                    len(_wrap(pd, value if value else '—', table_font, col_width - 16)),
                )
            total += max(38, 8 + max_lines * 25)
        return total

    top_area = 126
    section_gap = 54
    footer_area = 48
    height = (
        top_area
        + table_height(metric_rows, metric_widths)
        + section_gap
        + table_height(staffing_rows, staffing_widths)
        + footer_area
    )

    image = Image.new('RGB', (width, height), '#f6f7f8')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (7, 7, width - 7, height - 7),
        radius=12,
        fill='white',
        outline='#d5dce3',
        width=2,
    )

    draw.text((margin, 18), 'Pediatric Cardiology Daily Huddle', font=title_font, fill='#2670c8')
    draw.text((margin, 58), d.strftime('%A, %B %d, %Y'), font=subtitle_font, fill='#8fae15')

    y = 94
    draw.text((margin, y), 'Daily Activity by Location', font=subtitle_font, fill='#2670c8')
    y += 30
    metric_colors = [COLORS[i % len(COLORS)] for i in range(len(metric_rows))]
    y = _draw_table(
        draw,
        margin,
        y,
        metric_widths,
        ['Location'] + METRICS,
        metric_rows,
        '#2670c8',
        metric_colors,
    )

    y += 20
    draw.text((margin, y), 'Staff Scheduling', font=subtitle_font, fill='#cf303b')
    y += 30
    special_colors = ['#5b82aa', '#5b82aa', '#5b82aa', '#bd4b55']
    staffing_colors = [COLORS[i % len(COLORS)] for i in range(len(locs))] + special_colors
    y = _draw_table(
        draw,
        margin,
        y,
        staffing_widths,
        ['Location', 'MD', 'RN', 'MA', 'Sonographers', 'FOS'],
        staffing_rows,
        '#cf303b',
        staffing_colors,
    )

    draw.text(
        (margin, height - 32),
        'Planning recommendation. Confirm final staffing before operational use.',
        font=small_font,
        fill='#6b7280',
    )

    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()

def snapshot_text(d,metrics,staff,special,locs):
    lines=[f'Daily Huddle: {d.strftime("%A %B %d, %Y")}', '', 'Locations:']
    lines.append('Location | '+' | '.join(METRICS))
    for loc in locs: lines.append(loc+' | '+' | '.join(str(metrics.get(loc,{}).get(m,'') or '') for m in METRICS))
    lines+=['','Staff Scheduling:','Location | MD | RN | MA | Sonographers | FOS']
    for loc in locs+SPECIAL_ROWS:
        row=staff[loc] if loc in staff else special[loc]
        lines.append(loc+' | '+' | '.join(', '.join(row[r]) for r in ROLES))
    return '\n'.join(lines)

root,cfg=get_config(); locs=active_locations(cfg)
st.markdown('<div class="hero"><h1>Pediatric Cardiology Daily Huddle</h1><p>Daily counts and staffing save to the existing Google Drive JSON.</p></div>',unsafe_allow_html=True)
controls=st.columns([1.4,1,1,1])
with controls[0]: selected=st.date_input('Date',date.today(),format='MM/DD/YYYY')
with controls[1]: session=st.selectbox('Session',['BOTH','AM','PM'],format_func=lambda x:'AM + PM' if x=='BOTH' else x)
with controls[2]: edit=st.toggle('Edit staffing',False)
with controls[3]: admin=st.toggle('Admin mode',False)
if admin: admin_panel(root,cfg)
key=f'{selected}|{session}'
if st.session_state.get('record_key')!=key: st.session_state.record_key=key; st.session_state.record=load_huddle(str(selected),session)
record=st.session_state.record; record.setdefault('metrics',{}); record.setdefault('staff_only_locations',[]); record.setdefault('special_assignments',{})
st.markdown(f'<div class="huddle">Daily Huddle: {selected.strftime("%A %B %d, %Y")} 🌼</div>',unsafe_allow_html=True)
st.markdown('<div class="sect" style="color:#2670c8">Locations</div>',unsafe_allow_html=True)
h=st.columns([1.35,1,1,1,1,1,1])
for c,t in zip(h,['Locations:']+METRICS):c.markdown(f'**_{t}_**')
for i,loc in enumerate(locs):
    row=st.columns([1.35,1,1,1,1,1,1]); row[0].markdown(f'<span class="loc" style="color:{COLORS[i%len(COLORS)]}">{loc}</span>',unsafe_allow_html=True); record['metrics'].setdefault(loc,{})
    for j,m in enumerate(METRICS,1): record['metrics'][loc][m]=row[j].text_input(f'{loc}-{m}',str(record['metrics'][loc].get(m,'') or ''),label_visibility='collapsed',placeholder='0',key=f'm-{key}-{loc}-{m}')

staff=normalize_staff(record.get('staffing') or baseline_staff(selected,session,cfg),locs); special=normalize_special(record.get('special_assignments',{})); current_ex=exceptions_for(selected); off_names={e['person'] for e in current_ex}
# Remove unavailable and off staff before rendering.
roster_by_name={p['name']:p for p in active_roster(cfg)}
for loc in locs:
    for r in ROLES: staff[loc][r]=[n for n in staff[loc][r] if n not in off_names and n in roster_by_name and available_on(roster_by_name[n],selected)]
for x in ['Hospital','Admin','Remote']:
    for r in ROLES: special[x][r]=[n for n in special[x][r] if n not in off_names and n in roster_by_name and available_on(roster_by_name[n],selected)]
special['Off']={r:[] for r in ROLES}
for n in off_names:
    if n in roster_by_name:special['Off'][roster_by_name[n]['role']].append(n)
st.markdown('<div class="sect" style="color:#cf303b">Staff Scheduling</div>',unsafe_allow_html=True)
st.caption('All assignments stay visible. Turn on Edit staffing to select or unselect staff in place.')
staff,special,duplicates=assignment_grid(staff,special,cfg,locs,key,edit,selected,off_names)
if duplicates: st.error('Duplicate assignments were removed: '+', '.join(duplicates))
with st.expander('Clinic operating overrides',False): record['staff_only_locations']=st.multiselect('Manually open without onsite MD',locs,default=[x for x in record['staff_only_locations'] if x in locs],key=f'so-{key}')
staff,special,closed,pool,changes=auto_rebalance(staff,special,off_names,set(record['staff_only_locations']),cfg,selected); staff,special,duplicates=dedupe_assignments(staff,special); record['staffing']=staff; record['special_assignments']=special

left,right=st.columns(2)
with left:
    st.markdown('#### Unassigned Staff')
    assigned=all_assigned(staff,special)
    unassigned=[p for p in active_roster(cfg) if available_on(p,selected) and p['name'] not in assigned and p['name'] not in off_names]
    if unassigned:
        by={r:[] for r in ROLES}
        for p in unassigned:by[p['role']].append(p['name'])
        for r in ROLES:
            if by[r]:st.markdown(f'<div class="alert-card info"><strong>{LABEL[r]}</strong><br>{", ".join(by[r])}</div>',unsafe_allow_html=True)
    else:st.success('All scheduled, available roster staff are accounted for.')
with right:
    st.markdown('#### Coverage Alerts')
    for loc,status in coverage(staff,closed,set(record['staff_only_locations'])):
        klass='good' if status=='COVERED' else ('bad' if status=='CLOSED' else ('warn' if status.startswith('MISSING') else 'info'))
        st.markdown(f'<div class="alert-card {klass}"><strong>{loc}</strong><br>{status.title()}</div>',unsafe_allow_html=True)
if changes:
    st.markdown('#### Automatic Coverage Changes')
    for x in changes:st.info(x)

with st.expander('Time off and coverage',True):
    roles=sorted({p['role'] for p in active_roster(cfg)}); c=st.columns([1,1.5,1,1]); role=c[0].selectbox('Job',roles,key='torole'); people=[p['name'] for p in active_roster(cfg,role)]; person=c[1].selectbox('Person',people,key='toperson'); start=c[2].date_input('From',selected,key='tostart'); end=c[3].date_input('To',selected,key='toend')
    if st.button('Add time off'):
        ex=load_exceptions(); ex.append({'id':str(uuid.uuid4()),'person':person,'role':role,'start':str(start),'end':str(end),'location':'','replacement':''}); save_exceptions(ex); st.rerun()
    if current_ex:
        for e in current_ex:
            a,b=st.columns([6,1]); a.write(f"{e['person']} · {e['role']} · {e['start']} to {e['end']}")
            if b.button('Reinstate',key=f"reinstate-{e.get('id',e['person']+e['start'])}"):
                ex=load_exceptions(); ex=[x for x in ex if x.get('id')!=e.get('id')]; save_exceptions(ex); st.rerun()
    else:st.caption('No one is off for this date.')

with st.expander('Share Daily Huddle picture',False):
    png_bytes=huddle_png(selected,record['metrics'],staff,special,locs)
    st.image(png_bytes,caption='Daily Huddle picture preview',use_container_width=True)
    st.download_button('Download colorful Daily Huddle PNG',png_bytes,file_name=f'daily_huddle_{selected}.png',mime='image/png',use_container_width=True)
    st.caption('Download the PNG, then paste or attach it in Teams or email.')
buttons=st.columns([1,1,4])
if buttons[0].button('Save huddle',type='primary',use_container_width=True):
    record.update({'date':str(selected),'session':session,'staffing':staff,'special_assignments':special,'saved_at':datetime.now().isoformat(timespec='seconds')}); save_huddle(str(selected),session,record); st.success('Saved to Google Drive JSON.')
if buttons[1].button('Reload saved',use_container_width=True):st.session_state.record=load_huddle(str(selected),session); st.rerun()
st.caption('Planning recommendation only. Confirm clinic closures, qualifications, leave, travel constraints, and final staffing before operational use.')

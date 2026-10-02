from pathlib import Path
p = Path('app.py')
s = p.read_text(encoding='utf-8')
imp = 'from staffing_features import render_staffing_manager\n'
if imp not in s:
    anchor = 'from utils import (\n'
    idx = s.find(anchor)
    if idx < 0: raise SystemExit('Could not find utils import block')
    end = s.find('\n)\n', idx)
    if end < 0: raise SystemExit('Could not find end of utils import block')
    s = s[:end+3] + imp + s[end+3:]
call = 'render_staffing_manager(day, CLINICS, st.session_state.metrics)\n'
if call not in s:
    anchor = '# -------------------------\n# MAIN TABS\n# -------------------------\n'
    if anchor not in s: raise SystemExit('Could not find MAIN TABS marker')
    s = s.replace(anchor, call + '\n' + anchor, 1)
p.write_text(s, encoding='utf-8')
print('Patched app.py successfully')

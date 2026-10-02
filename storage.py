
import json
from pathlib import Path
DATA = Path(__file__).with_name("data.json")
DEFAULT={"roles":["MD","CMA","FOS","SON","RN"],"roster":[],"exceptions":[],"days":[]}

def load():
    if not DATA.exists(): return DEFAULT.copy()
    return {**DEFAULT, **json.loads(DATA.read_text())}

def save(data):
    tmp=DATA.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(DATA)

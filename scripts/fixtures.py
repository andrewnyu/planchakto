import json,csv,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.example import example
from backend.domain import apply_commands,SwapRooms,Reroute,MoveFixture
b=example();Path('examples').mkdir(exist_ok=True)
Path('examples/san-isidro.json').write_text(json.dumps({'schema_version':'1.0','model':b.model_dump()},indent=2))
Path('examples/boundary.json').write_text(json.dumps({'boundary':[p.model_dump() for p in b.site.boundary]},indent=2))
with Path('examples/survey.csv').open('w') as f:
    writer=csv.writer(f);writer.writerow(['X','Y','Z']);writer.writerows((p.x,p.y,p.z) for p in b.site.survey)
c,_=apply_commands(b,[SwapRooms(type='swap_rooms',first='bath',second='kitchen'),Reroute(type='reroute'),MoveFixture(type='move_fixture',fixture_id='basin',dx=1.5,dy=.75)])
Path('examples/coordinated-wet-rooms.json').write_text(json.dumps({'schema_version':'1.0','model':c.model_dump()},indent=2))

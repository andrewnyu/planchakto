"""Reproducible measured comparison; emits observations, never invented savings."""
import json,statistics,time,platform,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.example import example
from backend.domain import *
from backend.geometry import layout_checks
from backend.layout import generate_layouts
from backend.routing import route_all
from backend.engine import compute
from backend.structure import beam_fem

def timed(fn,n=7):
    values=[];result=None
    for _ in range(n):
        t=time.perf_counter();result=fn();values.append((time.perf_counter()-t)*1000)
    return result,{'runs':n,'median_ms':round(statistics.median(values),3),'min_ms':round(min(values),3),'max_ms':round(max(values),3)}

def greedy(b):
    c=b.model_copy(deep=True)
    # Baseline retains row assignment and each width; simple sequential packing in schema order.
    for y in sorted({r.y for r in c.rooms if r.kind!='corridor'}):
        x=0
        for r in [r for r in c.rooms if r.kind!='corridor' and r.y==y]:
            if r.locked and abs(r.x-x)>1e-8:return {'feasible':False,'reason':'Greedy order conflicts with a locked room'}
            r.x=x;x+=r.w
    check=layout_checks(c);return {'feasible':check['status']=='pass','issues':check['issues'],'area_deviation_m2':sum(abs(r.w*r.h-o.w*o.h) for r,o in zip(c.rooms,b.rooms))}

fixtures={'original':example()};swapped,_=apply_commands(example(),[SwapRooms(type='swap_rooms',first='bath',second='kitchen')]);fixtures['swapped_wet_rooms']=swapped
report={'machine':platform.platform(),'python':platform.python_version(),'seed':42,'timing':'Warm imports, sequential in-process wall clock. Machine-specific, not a general performance claim.','fixtures':{}}
for name,b in fixtures.items():
    base,tb=timed(lambda:greedy(b));layouts,tl=timed(lambda:generate_layouts(b),3);routing={}
    for mode in ['direct','avoid']:
        c=b.model_copy(deep=True);c.routing_mode=mode;routes,tr=timed(lambda:route_all(c));routing[mode]={'timing':tr,'route_count':len(routes['routes']),'failed_routes':sum(r['status']=='fail' for r in routes['routes']),'total_modeled_length_m':round(sum(r['length'] for r in routes['routes']),3),'scope':'Failed/disconnected routes may have zero length; totals are not comparable as installed complete networks.'}
    result,tc=timed(lambda:compute(b,'benchmark'));report['fixtures'][name]={'greedy':{'timing':tb,**base},'cp_sat':{'timing':tl,'candidate_count':len(layouts['candidates']),'statuses':[c['solver_status'] for c in layouts['candidates']],'objectives':[c['objective_description'] for c in layouts['candidates']]},'routing':routing,'complete_compute':tc,'checks':result['summary'],'estimate_PHP':result['quantities']['total']}
L,q,E,I=4,3000,200e9,8e-6;r=beam_fem(L,E,I,q);exact=5*q*L**4/(384*E*I)*1000
report['beam_benchmark']={'L_m':L,'q_N_m':q,'E_Pa':E,'I_m4':I,'analytical_deflection_mm':exact,'computed_deflection_mm':r['max_deflection_mm'],'absolute_error_mm':abs(exact-r['max_deflection_mm']),'equilibrium_residual_N':r['vertical_residual_N']}
Path('docs/BENCHMARKS.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

import math
import numpy as np
import pytest
from pydantic import ValidationError
from shapely.geometry import box,LineString
from backend.domain import *
from backend.example import example
from backend.structure import beam_fem,MechanismError,CATALOG,analyze_structure
from backend.geometry import parse_survey,validate_site,layout_checks,fitout_checks,terrain
from backend.routing import astar,blocked,route_all,length
from backend.quantities import takeoff
from backend.engine import compute,validate_result
from backend.layout import generate_layouts

@pytest.mark.parametrize('v,a,b,expected',[(1000,'mm','m',1),(1,'ft','m',.3048),(2,'kPa','Pa',2000),(200,'MPa','Pa',200e6),(4,'kN','N',4000)])
def test_units(v,a,b,expected):assert convert(v,a,b)==expected
@pytest.mark.parametrize('v,a,b',[(float('nan'),'m','mm'),(2,'m','kPa'),(1,'inch','m')])
def test_invalid_units(v,a,b):
    with pytest.raises(ValueError):convert(v,a,b)
def test_invalid_inputs():
    with pytest.raises(ValidationError):Room(id='r',name='R',kind='office',x=0,y=0,w=0,h=3)
    b=example().model_dump();b['engineering']['dead']['value']=-1
    with pytest.raises(ValueError):Building.model_validate(b)
    b=example().model_dump();b['rooms'][0]['x']=float('nan')
    with pytest.raises(ValueError):Building.model_validate(b)

@pytest.mark.parametrize('L,q,E,I',[(4,3000,200e9,8e-6),(6,5000,200e9,5e-5),(2.5,750,70e9,1e-6)])
def test_simply_supported_benchmark(L,q,E,I):
    actual=beam_fem(L,E,I,q)
    assert actual['max_deflection_mm']==pytest.approx(5*q*L**4/(384*E*I)*1000,rel=1e-8)
    assert actual['max_moment_kNm']==pytest.approx(q*L**2/8000)
    assert actual['max_shear_kN']==pytest.approx(q*L/2000)
    for reaction in actual['reactions']:assert reaction['force_N']==pytest.approx(q*L/2,rel=1e-8)
    assert abs(actual['vertical_residual_N'])<1e-5
    assert abs(actual['moment_residual_Nm'])<1e-4
    assert actual['displacements_mm'][0]==0
    assert actual['displacements_mm'][-1]==0

def test_unstable_model():
    with pytest.raises(MechanismError):beam_fem(4,200e9,1e-5,1000,supports=[])
    with pytest.raises(MechanismError):beam_fem(4,200e9,1e-5,1000,supports=[0])

def test_missing_soil_never_passes():
    b=example();b.engineering.soil.value=None;r=compute(b,'test')
    assert all(c['status']=='missing_input' for c in r['checks'] if c['rule_id']=='BEARING')
    assert all(c['status']=='unsupported' for c in r['checks'] if c['rule_id']=='PH-CODE')

def test_missing_load_never_passes():
    b=example();b.engineering.live.value=None;r=compute(b,'test')
    assert r['structure']['status']=='missing_input'
    assert r['structure']['beams']==[]
    assert any(c['status']=='missing_input' for c in r['checks'])

def test_beam_removal_merges_interior_span_and_end_removal_is_unsupported():
    b=example();b,_=apply_commands(b,[RemoveColumn(type='remove_column',column_id='col-1-1')]);r=analyze_structure(b)
    assert max(x['length'] for x in r['beams'])==8
    assert any(x['status']=='fail' for x in r['beams'])
    assert len(r['alternatives'])==3
    b,_=apply_commands(example(),[RemoveColumn(type='remove_column',column_id='col-0-0')])
    assert analyze_structure(b)['errors']

def test_layout_overlap_containment_access():
    b=example();assert layout_checks(b)['status']=='pass'
    b.rooms[0].x=2
    assert any('overlap' in c['id'] for c in layout_checks(b)['issues'])
    b.rooms[0].x=-1
    assert any('contain' in c['id'] for c in layout_checks(b)['issues'])
    b.rooms[0].y=.5
    assert any('access' in c['id'] for c in layout_checks(b)['issues'])

def test_layout_generation_is_feasible_and_preserves_locks():
    b=example();b.rooms[3].locked=True;result=generate_layouts(b)
    assert result['candidates']
    for c in result['candidates']:
        cmds=CommandRequest(base_revision='x',command_id='x',commands=c['commands']).commands
        candidate,_=apply_commands(b,cmds)
        assert layout_checks(candidate)['status']=='pass'
        assert candidate.rooms[3]==b.rooms[3]
        assert candidate.columns==b.columns
        assert c['solver_status'] in ['OPTIMAL','FEASIBLE']

def test_infeasible_layout_diagnostic():
    b=example();b.rooms[0].min_area=100
    with pytest.raises(ValueError,match='Infeasible'):generate_layouts(b)

def test_geometry_verified_obstacle_route():
    obstacle=box(1,-.25,2,.25);start=(0,0);end=(3,0)
    assert blocked([start,end],obstacle)
    path=astar(start,end,obstacle,(-1,-2,4,2))
    assert path and not blocked(path,obstacle)
    assert length(path)>3

def test_disconnected_route():
    assert astar((0,0),(3,0),box(-.1,-.1,.1,.1),(-1,-1,4,1)) is None

def test_infeasible_drain_elevation():
    b=example();b.site.drain.z=.1;r=route_all(b)
    assert all(x['status']=='fail' and 'gravity fall' in x['reason'] for x in r['routes'] if x['kind']=='drain')

def test_wet_room_route_propagation():
    b=example();before=compute(b,'a');c,invalidated=apply_commands(b,[SwapRooms(type='swap_rooms',first='bath',second='kitchen'),Reroute(type='reroute',mode='direct')]);after=compute(c,'b')
    assert 'routing' in invalidated and 'quantities' in invalidated
    assert any(x['status']=='fail' for x in after['routing']['routes'])
    assert before['quantities']['total']!=after['quantities']['total']
    c.routing_mode='avoid';routed=compute(c,'c')
    assert any(x['baseline_conflict'] and x['status']=='pass' for x in routed['routing']['routes'])

def test_quantity_hand_calculations_and_reconciliation():
    b=example();r=compute(b,'a');q={x['id']:x for x in r['quantities']['items']}
    assert q['slab']['net']==pytest.approx(12*9*.1)
    assert q['slab']['purchased']==pytest.approx(10.8*1.05)
    assert q['slab']['cost']==round(10.8*1.05*5800,2)
    assert q['floor']['net']==108
    assert q['columns']['net']==36
    assert q['columns']['purchased']==42
    # Roof beams 3 rows × 12 m + Y-direction grid girders 4 lines × 9 m.
    assert q['steel']['net']==pytest.approx((36+36)*CATALOG['RHS200']['kg_m'])
    # Unique wall length: exterior 42 + corridor 24 + partitions 8 + 7 = 81 m.
    # Door deductions: six 0.9 × 2.1 + one 1.2 × 2.1, both faces.
    assert q['walls']['net']==pytest.approx(81*3*2-(6*.9+1.2)*2.1*2)
    assert r['quantities']['total']==round(sum(x['cost'] for x in q.values()),2)

def test_survey_units_duplicates_and_degenerate():
    points=parse_survey('X,Y,Z\n0,0,0\n1000,0,10\n0,1000,20','mm');assert points[1].x==1
    site=example().site;site.survey=points;validate_site(site)
    site.survey.append(points[0])
    with pytest.raises(ValueError,match='duplicate'):validate_site(site)
    site.survey=[Point(x=i,y=0,z=0) for i in range(3)]
    with pytest.raises(ValueError,match='collinear'):validate_site(site)
    site=example().site;site.boundary=[Point(x=0,y=0),Point(x=2,y=2),Point(x=0,y=2),Point(x=2,y=0)]
    with pytest.raises(ValueError,match='polygon'):validate_site(site)

def test_terrain_flat_cut_volume():
    b=example()
    for p in b.site.survey:p.z=1
    result=terrain(b);assert result['cut_m3']==pytest.approx(108);assert result['fill_m3']==0

def test_missing_terrain_coverage():
    b=example();b.site.survey=[Point(x=0,y=0,z=0),Point(x=1,y=0,z=0),Point(x=0,y=1,z=0)]
    r=terrain(b);assert r['status']=='missing_input' and r['cut_m3'] is None

def test_stale_results_rejected_and_hash_reproducible():
    b=example();a=compute(b,'a');same=compute(b,'b');assert a['result_hash']==same['result_hash']
    with pytest.raises(ValueError,match='Stale'):validate_result(b,a,'b')
    b.engineering.live.value=4
    with pytest.raises(ValueError,match='Stale'):validate_result(b,a,'a')

def test_locked_room_and_furniture_preserved():
    b=example();b.rooms[0].locked=True
    with pytest.raises(ValueError,match='locked'):apply_commands(b,[MoveRoom(type='move_room',room_id='living',x=1,y=0)])
    b=example();b.furniture[0].locked=True
    with pytest.raises(ValueError,match='locked placement'):apply_commands(b,[MoveRoom(type='move_room',room_id='living',x=1,y=0)])

def test_fitout_conflict():
    b=example();b.furniture[0].dx=5
    assert fitout_checks(b)['status']=='fail'

def test_circulation_routes_avoid_physical_columns():
    b=example();r=layout_checks(b)
    assert r['status']=='pass' and len(r['circulation_paths'])==6
    # Solid furniture barrier across the corridor must invalidate access.
    b.furniture.append(Furniture(id='barrier',name='Barrier',room_id='hall',dx=2,dy=0,w=1,h=1.5,clearance=0))
    r=layout_checks(b)
    assert r['status']=='fail'
    assert any(i['id'].startswith('circulation-') for i in r['issues'])

def test_site_entry_must_connect_to_corridor():
    b=example();b.site.access.y=8
    assert any(i['id']=='entry-connectivity' for i in layout_checks(b)['issues'])

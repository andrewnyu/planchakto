import math,pytest
from backend.example import example
from backend.domain import apply_commands,SetFire,FireProtection,ExitDoor,Extinguisher,Building
from backend.engine import compute
from backend.fire import Grid,exit_segments,STEP
from backend.ai import AIPlan,AIRequest,validate_plan

EAST=ExitDoor(id='exit-east',wall='east',offset=4.2,width=1.0)
def fire(**kw):
    b,_=apply_commands(example(),[SetFire(type='set_fire',fire=FireProtection(enabled=True,**kw))]);return b
def checks(b):
    r=compute(b,'a');return r,{c['rule']:c for c in r['fire']['checks'] if c['rule']!='FIRE-SCOPE'}

def test_disabled_fire_adds_nothing():
    r=compute(example(),'a')
    assert r['fire']=={'enabled':False} and not any(c['rule_id'].startswith('FIRE-') for c in r['checks'])

def test_corridor_travel_matches_straight_line_hand_value():
    b=fire();g=Grid(b);seg=exit_segments(b)[0]
    dist,_=g.dijkstra(g.exit_sources(seg))
    j=int(4.375/STEP)   # corridor row in line with the west entry (y 4.15–5.35)
    assert dist[(g.nx-1,j)]==pytest.approx((g.nx-1)*STEP+STEP/2)   # 11.875 m along the corridor

def test_walls_block_travel_except_at_doors():
    g=Grid(fire());j=int(4/STEP)   # first corridor row above the y=4 wall
    door=next(d for d in g.doors if d[2]==4 and d[0]<1)   # living-room door on y=4
    inside=(int((door[0]+.3)/STEP),j-1);away=(int(5.5/STEP),j-1)
    assert g.passable(inside,(inside[0],j))
    assert not g.passable(away,(away[0],j))

def test_demo_business_single_exit_dead_end_and_missing_provisions():
    r,c=checks(fire())
    assert r['fire']['occupant_load']==math.ceil(108/9.3)==12
    assert c['FIRE-EXITS']['status']=='pass' and c['FIRE-EXITS']['inputs']['required']==1   # ¶4.3: < 100 occupants, ≤ 30 m
    assert c['FIRE-DEADEND']['status']=='fail' and c['FIRE-DEADEND']['inputs']['dead_end_m']==pytest.approx(12)
    assert c['FIRE-TRAVEL']['status']=='pass' and 12<c['FIRE-TRAVEL']['inputs']['travel_m']<46
    for rule in ['FIRE-ALARM','FIRE-SIGNS','FIRE-EXT']:assert c[rule]['status']=='fail'

def test_second_exit_and_provisions_clear_the_screen():
    base=checks(fire())[1]['FIRE-TRAVEL']['inputs']['travel_m']
    r,c=checks(fire(exits=[EAST],extinguishers=[Extinguisher(id='fe-1',room_id='hall',dx=6,dy=.2)],alarm='manual',exit_signs=True))
    assert all(x['status'] in ['pass','not_applicable'] for x in c.values()),{k:v['evidence'] for k,v in c.items() if v['status']=='fail'}
    assert c['FIRE-DEADEND']['inputs']['dead_end_m']==0 and c['FIRE-TRAVEL']['inputs']['travel_m']<base
    assert c['FIRE-COMMON']['inputs']['common_path_m']<c['FIRE-TRAVEL']['inputs']['travel_m']
    assert c['FIRE-CAPACITY']['inputs']['provided_m']==pytest.approx(2.2)

def test_sprinklers_relax_business_limits():
    c=checks(fire(sprinklered=True))[1]
    assert c['FIRE-DEADEND']['status']=='pass'   # 12 m ≤ 15 m sprinklered (¶5.2.a)
    assert c['FIRE-TRAVEL']['inputs']['limit_m']==61

def test_mercantile_class_c_and_unlocated_travel_limit_stays_missing():
    r,c=checks(fire(occupancy='mercantile'))
    assert r['fire']['mercantile_class']=='C' and r['fire']['occupant_load']==math.ceil(108/2.8)
    assert c['FIRE-TRAVEL']['status']=='missing_input' and c['FIRE-ALARM']['status']=='not_applicable'
    assert checks(fire(occupancy='mercantile',sprinklered=True))[1]['FIRE-TRAVEL']['inputs']['limit_m']==46
    assert checks(fire(occupancy='mercantile',mercantile_travel_m=30))[1]['FIRE-TRAVEL']['status']=='pass'

def test_extinguisher_table_7_hazard_rating_count_and_reach():
    one=[Extinguisher(id='fe-1',room_id='hall',dx=6,dy=.2)]
    c=checks(fire(extinguishers=one,hazard='high'))[1]['FIRE-EXT']
    assert c['status']=='fail' and c['inputs']['needed']==math.ceil(108/75) and 'under-rated' in c['evidence']
    corner=[Extinguisher(id='fe-1',room_id='living',dx=.3,dy=.3)]
    c=checks(fire(extinguishers=corner))[1]['FIRE-EXT']
    assert c['status']=='fail' and c['inputs']['max_travel_m']>15

def test_exit_must_fit_its_wall_and_fire_is_manual_only():
    with pytest.raises(ValueError):fire(exits=[ExitDoor(id='x',wall='east',offset=8.5,width=1)])
    with pytest.raises(ValueError):validate_plan(AIPlan(revision_id='a',action='edit',explanation='x',commands=[{'type':'set_fire','fire':{'enabled':True}}]),AIRequest(revision_id='a',message='add exits'))

def test_fire_quantities():
    q={x['id']:x for x in compute(fire(exits=[EAST],extinguishers=[Extinguisher(id='fe-1',room_id='hall',dx=6,dy=.2)]),'a')['quantities']['items']}
    assert q['fire_extinguishers']['net']==1 and q['fire_exits']['net']==1

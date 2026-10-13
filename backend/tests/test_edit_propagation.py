import pytest
from backend.domain import *
from backend.example import example
from backend.engine import compute
from backend.routing import route_all

def test_relocate_basin_resolves_wet_room_conflict():
    b=example();b,_=apply_commands(b,[SwapRooms(type='swap_rooms',first='bath',second='kitchen'),Reroute(type='reroute')])
    assert any(r['status']=='fail' for r in route_all(b)['routes'] if r['source_id']=='basin')
    fixed,deps=apply_commands(b,[MoveFixture(type='move_fixture',fixture_id='basin',dx=1.5,dy=.75)])
    assert all(r['status']=='pass' for r in route_all(fixed)['routes'])
    assert deps==['quantities','routing']

def test_place_unknown_rating_is_missing_not_zero():
    b,_=apply_commands(example(),[AddElement(type='add_element',kind='equipment',id='new',room_id='living',name='Unknown light',dx=1,dy=1,circuit_id='C01')])
    r=compute(b,'new')
    circuit=next(c for c in r['routing']['circuits'] if c['id']=='C01')
    assert circuit['status']=='missing_input' and circuit['connected_W'] is None
    assert next(q for q in r['quantities']['items'] if q['id']=='equipment')['net']==5

def test_equipment_load_changes_only_assigned_circuit():
    b=example();before=compute(b,'a');after,_=apply_commands(b,[SetEquipment(type='set_equipment',equipment_id='eq-ac',watts=2400)]);result=compute(after,'b')
    circuits={c['id']:c for c in result['routing']['circuits']}
    assert circuits['C03']['current_A']==pytest.approx(2400/230)
    assert circuits['C01']==before['routing']['circuits'][0]
    assert result['structure']==before['structure']

def test_move_equipment_resolves_blocked_endpoint():
    b,deps=apply_commands(example(),[MoveEquipment(type='move_equipment',equipment_id='eq-fridge',dx=2.75,dy=.5,circuit_id='C02')])
    assert next(x for x in route_all(b)['routes'] if x['source_id']=='eq-fridge')['status']=='pass'
    assert 'electrical' in deps

def test_duplicate_element_and_circuit_rejected():
    with pytest.raises(ValueError,match='unique'):apply_commands(example(),[AddElement(type='add_element',kind='fixture',id='sink',room_id='living',name='New',dx=1,dy=1)])
    with pytest.raises(ValueError,match='Unknown circuit'):apply_commands(example(),[MoveEquipment(type='move_equipment',equipment_id='eq-fridge',dx=1,dy=1,circuit_id='absent')])

def test_section_change_propagates_selfweight_and_quantities():
    b=example();a=compute(b,'a');c,_=apply_commands(b,[SetParameter(type='set_parameter',field='section',value='RHS250')]);result=compute(c,'c')
    assert result['structure']['beams'][0]['service_q_kNm']>a['structure']['beams'][0]['service_q_kNm']
    assert result['quantities']['total']>a['quantities']['total']

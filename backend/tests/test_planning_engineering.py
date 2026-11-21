"""Physical arithmetic and false-pass regressions for the staged planning screens."""
import math
import pytest
from pydantic import ValidationError
from backend.concepts import DesignPlan
from backend.planning_models import EngineeringInputs,Programme,DetailRecipe,DetailedPlan,ArrayRecipe
from backend.planning_checks import programme_findings,run_checks,travel_screen
from backend.structure import CATALOG


def value(n,source='user',basis='Confirmed test input'):
    return {'value':n,'source':source,'basis':basis}


def plan():
    return DesignPlan.model_validate({'title':'Hall','rationale':'Test geometry','footprint':[[0,0],[10,0],[10,10],[0,10]],'zones':[{'id':'hall','name':'Hall','kind':'retail','polygon':[[0,0],[10,0],[10,10],[0,10]]}],'openings':[{'id':'exit','from_zone':'hall','to_zone':'outside','segment':[[.5,0],[1.5,0]],'kind':'door'}]})


def details(**kwargs):
    return DetailedPlan(title='Fit-out',recipe=DetailRecipe(title='Fit-out'),**kwargs)


def check(inputs=None,p=None,d=None,programme=None):
    return run_checks(programme or Programme(name='Test',use='Retail',total_area_m2=100),p or plan(),d or details(),inputs or EngineeringInputs(),'accepted-design')


def findings(result):return {f['id']:f for f in result['findings']}


def beam_inputs(**updates):
    data=dict(structural_model='simply_supported_steel_roof_bay',beam_section='RHS200',beam_self_weight='add_section_weight',bay_span=value(4),tributary_width=value(2),dead_kpa=value(.5),live_kpa=value(.75),elastic_modulus_mpa=value(200000),yield_strength_mpa=value(250),dead_factor=value(1.2),live_factor=value(1.6),deflection_ratio=value(240))
    return EngineeringInputs(**(data|updates))


def test_beam_matches_closed_form_and_explicit_self_weight_modes():
    section=CATALOG['RHS200'];sw=section['kg_m']*9.80665/1000
    for mode,added in [('included_in_dead_load',0),('add_section_weight',sw)]:
        f=findings(check(beam_inputs(beam_self_weight=mode)))['roof-bay'];v=f['values']
        factored=(.5*1.2+.75*1.6)*2+added*1.2;service=(.5+.75)*2+added
        assert v['stress_mpa']==pytest.approx(factored*1000*4**2/8/section['Z']/1e6)
        assert v['deflection_mm']==pytest.approx(5*service*1000*4**4/(384*200000e6*section['I'])*1000,rel=1e-7)
        assert v['added_self_weight_kn_m']==pytest.approx(added)
        assert v['factored_line_load_kn_m']==pytest.approx(factored)
        assert abs(v['solver']['vertical_residual_N'])<1e-6
    assert findings(check(beam_inputs(yield_strength_mpa=value(1))))['roof-bay']['status']=='fail'
    assert findings(check(beam_inputs(deflection_ratio=value(100000))))['roof-bay']['status']=='fail'


@pytest.mark.parametrize('updates',[{'beam_self_weight':None},{'live_kpa':value(None)},{'dead_kpa':value(.5,'proposal')},{'dead_factor':value(1.2,basis=' Not supplied ')}])
def test_missing_or_unconfirmed_beam_input_never_passes(updates):
    assert findings(check(beam_inputs(**updates)))['roof-bay']['status']=='missing_input'


def test_supplied_load_bearing_is_independent_of_roof_model():
    f=findings(check(EngineeringInputs(footing_load_kn=value(200),footing_width=value(2),soil_kpa=value(40))))
    assert f['bearing']['status']=='fail' and f['bearing']['values']['pressure_kpa']==50
    assert 'gross/net' in f['bearing']['evidence']
    assert f['roof-bay']['status']=='missing_input'


def test_unreachable_part_cannot_pass_travel_distance_with_generous_limit():
    barrier={'id':'rack','zone_id':'hall','kind':'rack','name':'Partitioning rack','polygon':[[4.9,0],[5.1,0],[5.1,10],[4.9,10]]}
    r=check(EngineeringInputs(criteria={'max_egress_travel':value(1000)}),d=details(items=[barrier]));f=findings(r)
    assert r['travel']['max_distance_m']<1000
    assert 'hall' in r['travel']['unreachable']
    assert f['route-reachability']['status']=='fail' and f['travel']['status']=='fail'


def test_unsampled_support_room_is_reported_unreachable():
    room={'id':'store','zone_id':'hall','name':'Store','kind':'storage','polygon':[[4,4],[5.1,4],[5.1,5.1],[4,5.1]],'door':[[4.1,4],[4.8,4]]}
    filled={'id':'rack','zone_id':'hall','kind':'rack','name':'Filled room','polygon':room['polygon']}
    assert 'store' in travel_screen(plan(),details(rooms=[room],items=[filled]))['unreachable']


def test_unrounded_travel_distance_decides_supplied_limit():
    p=plan();d=details();distance=travel_screen(p,d)['max_distance_m'];limit=math.floor(distance*100)/100
    assert limit<distance
    assert findings(check(EngineeringInputs(criteria={'max_egress_travel':value(limit)}),p,d))['travel']['status']=='fail'


def test_empty_door_set_is_missing_input_even_with_width_criterion():
    p=plan();p.openings[0].kind='open'
    assert findings(check(EngineeringInputs(criteria={'min_door_width':value(.8)}),p=p))['doors']['status']=='missing_input'


def test_overlapping_exit_segments_do_not_double_count_width():
    p=plan();p.openings.append(p.openings[0].model_copy(update={'id':'duplicate'}))
    i=EngineeringInputs(criteria={'occupant_area_factor':value(1),'exit_width_per_person_mm':value(20)})
    f=findings(check(i,p=p))['occupants']
    assert f['values']['drawn_width_m']==1 and f['status']=='fail'


def test_circulation_envelope_cannot_pass_through_enclosed_wall():
    p=plan();p.zones[0].polygon=[[0,0],[5,0],[5,10],[0,10]];p.zones[0].enclosed=True
    p.zones.append(p.zones[0].model_copy(update={'id':'right','polygon':[(5,0),(10,0),(10,10),(5,10)],'enclosed':False}))
    d=details(routes=[{'id':'crossing','name':'Interior route','kind':'interior','points':[[2,2],[8,2]],'width':1}])
    f=findings(check(EngineeringInputs(criteria={'min_customer_aisle':value(.9)}),p,d))['route-crossing']
    assert f['status']=='fail' and 'enclosed-walls' in f['objects']


def circuit_inputs(**updates):
    data=dict(circuits=[{'id':'c','phases':3,'voltage':value(400),'power_factor':value(.8),'demand_factor':value(.5)}],loads=[{'id':'l','name':'Load','zone_id':'hall','watts':value(2000),'quantity':3,'circuit':'c'}])
    return EngineeringInputs(**(data|updates))


def test_three_phase_arithmetic_and_missing_load_or_phase():
    i=circuit_inputs();f=findings(check(i))['circuit-c'];assert f['values']['current_a']==pytest.approx(3000/(math.sqrt(3)*400*.8))
    i.loads[0].watts.value=None
    assert findings(check(i))['circuit-c']['status']=='missing_input'
    i=circuit_inputs();i.circuits[0].phases=None
    assert findings(check(i))['circuit-phase-c']['status']=='missing_input'
    i=circuit_inputs(loads=[])
    assert findings(check(i))['circuit-c']['status']=='missing_input'


@pytest.mark.parametrize('field,n',[('power_factor',0),('power_factor',1.01),('demand_factor',-.01),('demand_factor',1.01),('voltage',0)])
def test_invalid_electrical_factors_are_rejected(field,n):
    with pytest.raises(ValidationError):EngineeringInputs(circuits=[{'id':'c',field:value(n)}])


@pytest.mark.parametrize('source,basis',[('proposal','Generated utility location'),('user',' Not supplied '),('drawing',' ')])
def test_unconfirmed_utility_points_do_not_create_connections(source,basis):
    utilities=[{'id':'panel','kind':'panel','point':[2,2],'source':source,'basis':basis},{'id':'drain','kind':'drain','point':[2,2],'source':source,'basis':basis}]
    fixture={'id':'sink','zone_id':'hall','kind':'sink','name':'Sink','polygon':[[.4,.4],[.6,.4],[.6,.6],[.4,.6]]}
    r=check(circuit_inputs(utilities=utilities,drain_fall=value(1),drain_slope=value(.01)),d=details(items=[fixture]));f=findings(r)
    assert not r['pipes'] and not r['wires']
    assert f['panel-input']['status']=='missing_input' and f['plumbing-inputs']['status']=='missing_input'


def test_drain_fall_uses_unrounded_connection_length_and_positive_slope():
    fixture={'id':'sink','zone_id':'hall','kind':'sink','name':'Sink','polygon':[[.4,.4],[.6,.4],[.6,.6],[.4,.6]]}
    inputs=EngineeringInputs(utilities=[{'id':'drain','kind':'drain','point':[1.50049,.5],'basis':'Surveyed point'}],drain_fall=value(.010002),drain_slope=value(.01))
    f=findings(check(inputs,d=details(items=[fixture])))['gravity']
    assert f['status']=='fail' and f['values']['required_fall_m']==pytest.approx(.0100049)
    with pytest.raises(ValidationError):EngineeringInputs(drain_slope=value(0))


def test_nested_zone_and_room_do_not_satisfy_two_space_count():
    p=plan();p.zones[0].requirement_ids=['office']
    d=details(rooms=[{'id':'room','zone_id':'hall','name':'Office','kind':'office','polygon':[[2,2],[4,2],[4,4],[2,4]],'door':[[2.1,2],[3.1,2]],'requirement_id':'office'}])
    programme=Programme(name='Offices',use='Office',requirements=[{'id':'office','name':'Offices','kind':'office','count':2}])
    f={f['id']:f for f in programme_findings(programme,p,d)}
    assert f['count-office']['status']=='fail' and '1 distinct' in f['count-office']['evidence']


def test_unknown_detail_binding_is_a_failure():
    d=details(items=[{'id':'sink','zone_id':'hall','kind':'sink','name':'Sink','polygon':[[2,2],[3,2],[3,3],[2,3]],'requirement_id':'invented'}])
    assert findings(check(d=d))['unknown-sink']['status']=='fail'


def test_zone_envelope_does_not_inflate_area_of_refining_same_requirement_rooms():
    p=plan();p.zones[0].requirement_ids=['office']
    d=details(rooms=[{'id':'room','zone_id':'hall','name':'Office','kind':'office','polygon':[[2,2],[4,2],[4,4],[2,4]],'door':[[2.1,2],[3.1,2]],'requirement_id':'office'}])
    programme=Programme(name='Offices',use='Office',requirements=[{'id':'office','name':'Office','kind':'office','area_m2':100,'area_mode':'minimum'}])
    f={f['id']:f for f in programme_findings(programme,p,d)}
    assert f['requirement-office']['status']=='fail' and f['requirement-office']['values']['actual']==4


def test_array_contract_accepts_explicit_rotated_fill_request():
    a=ArrayRecipe(id='r',zone_id='hall',kind='rack',name='Rack',angle=37.5,packing='fill',target_count=125,item_width=1,item_depth=2)
    assert a.angle==37.5 and a.target_count==125

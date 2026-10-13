import math,pytest
from fastapi.testclient import TestClient
from backend.example import example
from backend.domain import apply_commands,SetSolar,Solar
from backend.engine import compute
from backend.solar import array_layout
from backend.store import LocalStore
from backend.ai import AIPlan,AIRequest,validate_plan
import backend.main as main

def solar(**kw):
    b,_=apply_commands(example(),[SetSolar(type='set_solar',solar=Solar(enabled=True,**kw))]);return b
def checks(r):return {c['rule']:c for c in r['solar']['checks']}

def test_disabled_solar_leaves_structure_unchanged():
    r=compute(example(),'a')
    assert r['solar']=={'enabled':False} and all(x['pv_kNm']==0 for x in r['structure']['beams'])
    assert not any(c['rule_id'].startswith('PV-') for c in r['checks'])

def test_pv_dead_load_matches_hand_calculation_per_tributary_strip():
    b=solar();pv=array_layout(b);r=compute(b,'a')
    kPa=(28/(2.278*1.134)+4)*9.80665/1000
    assert pv['dead_load_kPa']==pytest.approx(kPa) and pv['count']==11 and pv['y_extent']==pytest.approx([.6,.6+2*2.278])
    by_row={round(x['y'],3):x for x in r['structure']['beams']}
    assert by_row[0]['pv_kNm']==pytest.approx(kPa*(1.75-.6))          # strip [0,1.75] ∩ array
    assert by_row[3.5]['pv_kNm']==pytest.approx(kPa*(.6+2*2.278-1.75)) # strip [1.75,6.25] ∩ array
    assert by_row[9]['pv_kNm']==0
    base={x['id']:x for x in compute(example(),'b')['structure']['beams']}
    for x in r['structure']['beams']:
        assert x['service_q_kNm']==pytest.approx(base[x['id']]['service_q_kNm']+x['pv_kNm'])
        assert x['utilization_without_pv']==pytest.approx(max(base[x['id']]['yield_utilization'],base[x['id']]['deflection_utilization']))

def test_target_beyond_roof_capacity_fails_and_none_fills_roof():
    assert checks(compute(solar(target_kwp=50),'a'))['PV-ROOF']['status']=='fail'
    full=array_layout(solar(target_kwp=None))
    assert full['count']==full['capacity']==27   # portrait: floor(10.8/1.134)=9 × floor(7.8/2.278)=3

@pytest.mark.parametrize('kw,phases,voltage,breaker',[(5,1,230,30),(10,1,230,60),(30,3,400,60)])
def test_inverter_breaker_is_next_standard_rating_above_125_percent(kw,phases,voltage,breaker):
    e=compute(solar(inverter_kw=kw,phases=phases,voltage=voltage),'a')['solar']['electrical']
    current=kw*1000/(voltage*(math.sqrt(3) if phases==3 else 1))
    assert e['output_current_A']==pytest.approx(current) and e['min_ocpd_A']==pytest.approx(1.25*current) and e['pv_breaker_A']==breaker

def test_busbar_120_percent_rule():
    assert checks(compute(solar(service_main_a=60,busbar_a=100),'a'))['PV-BUSBAR']['status']=='pass'   # 60+27.2 ≤ 120
    assert checks(compute(solar(service_main_a=100,busbar_a=100),'a'))['PV-BUSBAR']['status']=='fail'  # 100+27.2 > 120

def test_utility_values_are_missing_until_entered_never_assumed():
    c=checks(compute(solar(),'a'))
    assert c['PV-XFMR']['status']=='missing_input' and c['PV-HOSTING']['status']=='missing_input'
    c=checks(compute(solar(transformer_kva=3,hosting_capacity_kw=4),'a'))
    assert c['PV-XFMR']['status']=='fail' and c['PV-HOSTING']['status']=='fail'   # 5 kW reverse flow
    c=checks(compute(solar(transformer_kva=50,hosting_capacity_kw=10),'a'))
    assert c['PV-XFMR']['status']=='pass' and c['PV-HOSTING']['status']=='pass'

def test_net_metering_cap_by_customer_class():
    assert checks(compute(solar(customer_class='non_residential'),'a'))['PV-NETMETER']['status']=='missing_input'
    r=compute(solar(customer_class='non_residential',contracted_kw=5),'a')
    assert checks(r)['PV-NETMETER']['status']=='fail' and checks(r)['PV-NETMETER']['inputs']['cap_kw']==5
    assert checks(compute(solar(customer_class='non_residential',contracted_kw=5000),'a'))['PV-NETMETER']['inputs']['cap_kw']==1000

def test_pv_quantities_priced_from_layout():
    q={x['id']:x for x in compute(solar(),'a')['quantities']['items']}
    assert q['pv_modules']['net']==11 and q['pv_inverter']['net']==1
    assert q['pv_racking']['net']==pytest.approx(11*2.278*1.134)

def test_set_solar_is_a_reviewable_candidate_and_manual_only(tmp_path,monkeypatch):
    store=LocalStore(str(tmp_path/'t.sqlite3'));monkeypatch.setattr(main,'_store',store);client=TestClient(main.app)
    head=client.get('/api/project').json()['state']['head']
    r=client.post('/api/commands',json={'base_revision':head,'command_id':'pv1','commands':[{'type':'set_solar','solar':{'enabled':True}}]})
    assert r.status_code==200 and 'solar' in r.json()['invalidated'] and r.json()['results']['solar']['enabled']
    assert client.get('/api/project').json()['state']['head']==head
    with pytest.raises(ValueError):validate_plan(AIPlan(revision_id='a',action='edit',explanation='x',commands=[{'type':'set_solar','solar':{'enabled':True}}]),AIRequest(revision_id='a',message='add solar'))

def test_pv_without_catalog_rates_is_reported_unpriced():
    b=solar();b=b.model_copy(update={'rates':[r for r in b.rates if not r.id.startswith('pv_')]})
    q=compute(b,'a')['quantities']
    assert not any(x['id'].startswith('pv_') for x in q['items'])
    assert {x['id'] for x in q['unpriced']}=={'pv_modules','pv_racking','pv_inverter'}

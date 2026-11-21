import copy,json,threading,time
import pytest
from backend import planning_agents as agents
from backend.domain import digest
from backend.planning_models import EngineeringInputs


@pytest.fixture
def bundle():
    refs={stage:'artifact-'+stage for stage in ('programme','strategy','layout','details','site')}
    accepted={'programme':{'name':'Test hall','requirements':[]},'layout':{'plan':{'footprint':[[0,0],[10,0],[10,10],[0,10]],'zones':[]}},
        'strategy':{'title':'Separate approaches'},'details':{'title':'Fit-out','items':[{'id':'wc','kind':'wc'},{'id':'panel','kind':'panel'},{'id':'rack','kind':'rack'}],'rooms':[],'routes':[],'recipe':{}},
        'inputs':EngineeringInputs().model_dump(mode='json')}
    findings=[{'id':'bearing','discipline':'structure','status':'missing_input','title':'Footing bearing','evidence':'Supply soil bearing and a footing load.','values':{}},
        {'id':'global-structure','discipline':'structure','status':'unsupported','title':'Whole-building structure','evidence':'Licensed professional review is required.','values':{}},
        {'id':'programme-area','discipline':'programme','status':'pass','title':'Area','evidence':'Drawn area matches the confirmed programme.','values':{'actual':100}},
        {'id':'electrical-inputs','discipline':'electrical','status':'missing_input','title':'Electrical inputs','evidence':'Supply loads and circuits.','values':{}},
        {'id':'gravity','discipline':'plumbing','status':'missing_input','title':'Drainage fall','evidence':'Supply fall and slope.','values':{}},
        {'id':'accessible','discipline':'accessibility','status':'unsupported','title':'Accessible route','evidence':'Not screened.','values':{}},
        {'id':'vehicle-sweep','discipline':'traffic','status':'unsupported','title':'Vehicle swept path','evidence':'Not screened.','values':{}},
        {'id':'budget','discipline':'cost','status':'missing_input','title':'Budget comparison','evidence':'Supply rates and budget.','values':{}}]
    return {'refs':refs,'accepted':accepted,'analysis_current':True,'analysis':{'design_hash':digest(refs),'inputs_hash':digest(accepted['inputs']),'findings':findings,
        'coverage':{'checked':['Programme area'],'not_checked':['Whole-building structure','Accessible routes']},'quantities':{'area_m2':100,'total_cost_php':None}}}


def response(bundle,role='structure'):
    finding={'structure':'bearing','architecture':'programme-area','electrical':'electrical-inputs','plumbing':'gravity','fire_accessibility':'accessible','site_traffic':'vehicle-sweep','quantities':'budget'}[role]
    return {'role':role,'design_hash':bundle['analysis']['design_hash'],'inputs_hash':bundle['analysis']['inputs_hash'],
        'summary':'Confirm missing inputs and retain professional review.','finding_ids':[finding],'input_paths':[],
        'recommendations':[{'title':'Confirm supplied evidence','rationale':'The deterministic finding remains unresolved.','finding_ids':[finding],'input_paths':[],'suggested_next_action':'supply_input'}],
        'questions':[]}


def llm_for(bundle,role='structure',mutate=None):
    def llm(payload,system):
        value=response(bundle,role)
        if mutate:mutate(value)
        return json.dumps(value)
    return llm


def test_grounded_review_is_read_only_and_keeps_missing_and_unsupported(bundle):
    before=copy.deepcopy(bundle)
    result=agents.review_role(bundle,'structure',llm=llm_for(bundle))
    assert bundle==before
    assert result['mode']=='injected' and result['provider']=='injected'
    assert result['advisory_only'] and not result['no_ai_review']
    assert result['deterministic_status']=='missing_input'
    assert {f['status'] for f in result['findings']}=={'missing_input','unsupported'}
    assert result['coverage']==bundle['analysis']['coverage']
    assert bundle['accepted']['inputs']['soil_kpa']['value'] is None


def test_input_reference_is_exact_and_safe(bundle):
    def mutate(v):
        v['finding_ids']=[];v['input_paths']=['/accepted/inputs/soil_kpa/value']
        v['questions']=[{'question':'Can you supply the geotechnical basis?','finding_ids':[],'input_paths':['/accepted/inputs/soil_kpa/basis']}]
    result=agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=mutate))
    assert result['questions'][0]['input_paths']==['/accepted/inputs/soil_kpa/basis']
    assert agents.resolve_path(bundle,'/accepted/inputs/soil_kpa/value') is None
    for path in ['/accepted/inputs/__class__','/accepted/layout/plan/footprint/-1','/accepted/inputs/soil_kpa.value','/accepted/inputs/~2bad','/analysis/findings/0']:
        with pytest.raises(ValueError):agents.resolve_path(bundle,path)


@pytest.mark.parametrize('change',[
    lambda v:v.update(finding_ids=['invented-finding']),
    lambda v:v.update(finding_ids=['electrical-inputs']),
    lambda v:v.update(input_paths=['/accepted/inputs/soil_kpa/unknown']),
    lambda v:v.update(input_paths=['/accepted/inputs/budget/value']),
    lambda v:v.update(finding_ids=[],input_paths=[]),
    lambda v:v['recommendations'][0].update(finding_ids=[],input_paths=[]),
    lambda v:v.update(role='electrical'),
    lambda v:v.update(design_hash='f'*64),
    lambda v:v.update(inputs_hash='f'*64),
    lambda v:v.update(commands=[{'type':'set_parameter','value':100}]),
    lambda v:v.update(summary='The beam stress is 120 MPa.'),
    lambda v:v.update(summary='The building is compliant.'),
    lambda v:v.update(summary='The design is approved.'),
    lambda v:v.update(summary='The building is safe.'),
    lambda v:v.update(summary='The change was applied.'),
])
def test_ungrounded_stale_or_unsafe_model_reply_is_refused(bundle,change):
    with pytest.raises(ValueError):agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=change))


def test_bounded_repair_of_grounding_and_role(bundle):
    calls=[]
    def llm(payload,system):
        calls.append(json.loads(payload));result=response(bundle)
        if len(calls)==1:result['finding_ids']=['unknown']
        else:
            assert 'validation_error' in calls[-1]
            assert 'untrusted data' in system.lower()
            assert 'JSON Schema' in system
        return [json.dumps(result)]
    assert agents.review_role(bundle,'structure',llm=llm)['role']=='structure'
    assert len(calls)==2


@pytest.mark.parametrize('key',['design_hash','inputs_hash'])
def test_stale_analysis_refused_before_llm(bundle,key):
    bundle['analysis'][key]='f'*64
    called=[]
    with pytest.raises(ValueError):agents.review_role(bundle,'structure',llm=lambda *args:called.append(args))
    assert not called
    assert all(not r['analysis_current'] for r in agents.roster(bundle))


def test_changed_inputs_cannot_reuse_analysis(bundle):
    bundle['accepted']['inputs']['soil_kpa']['value']=200
    with pytest.raises(ValueError):agents.review_role(bundle,'structure',llm=llm_for(bundle))


def test_provider_absence_never_fabricates_ai_review(bundle,monkeypatch):
    monkeypatch.setattr(agents.ai,'provider',lambda:None)
    with pytest.raises(RuntimeError,match='no AI review'):agents.review_role(bundle,'structure')
    assert all(r['no_ai_review'] for r in agents.roster(bundle))


def test_provider_live_uses_json_prompt_and_shared_budget(bundle,monkeypatch):
    called=[]
    monkeypatch.setattr(agents.ai,'provider',lambda:'vertex')
    def gemini(payload,**kwargs):
        called.append(kwargs)
        assert kwargs['vertex'] and kwargs['thinking_level']=='LOW'
        assert 160<kwargs['deadline']-time.monotonic()<=165
        assert json.loads(payload)['role']=='structure'
        return json.dumps(response(bundle))
    monkeypatch.setattr(agents.ai,'_gemini',gemini)
    result=agents.review_role(bundle,'structure')
    assert result['mode']=='live' and result['provider']=='vertex' and len(called)==1


def test_deadline_prevents_starting_unbounded_calls(bundle):
    called=[]
    with pytest.raises(RuntimeError,match='time budget'):
        agents.review_role(bundle,'structure',llm=lambda *args:called.append(args),deadline=time.monotonic()+74)
    assert not called


def test_roster_is_real_finding_status_not_a_model_response(bundle):
    result={r['role']:r for r in agents.roster(bundle)}
    assert set(result)==set(agents.ROLES)
    assert result['architecture']['status']=='ready_for_review'
    assert result['structure']['status']=='missing_input'
    assert result['site_traffic']['status']=='unsupported'
    assert all('summary' not in r and r['no_ai_review'] for r in result.values())
    bundle['analysis']['findings'][0]['status']='fail'
    assert next(r for r in agents.roster(bundle) if r['role']=='structure')['status']=='attention'
    bundle['analysis']=None
    assert all(r['status']=='missing_input' for r in agents.roster(bundle))


def test_specialists_receive_role_subsets_and_only_known_paths(bundle):
    bundle['accepted']['inputs']['budget']['value']=1000000
    bundle['analysis']['inputs_hash']=digest(bundle['accepted']['inputs'])
    electrical=agents.role_context(bundle,'electrical');plumbing=agents.role_context(bundle,'plumbing')
    assert '/accepted/inputs/budget/value' not in electrical['allowed_input_paths']
    assert '/accepted/details/items/1' in electrical['allowed_input_paths']
    assert '/accepted/details/items/0' not in electrical['allowed_input_paths']
    assert '/accepted/details/items/0' in plumbing['allowed_input_paths']
    assert '/accepted/details/items/1' not in plumbing['allowed_input_paths']
    assert {f['discipline'] for f in electrical['findings']}=={'electrical'}
    for path in electrical['allowed_input_paths']:agents.resolve_path(bundle,path)


def test_review_batch_has_bounded_parallelism_and_one_snapshot(bundle):
    lock=threading.Lock();active=0;peak=0
    def llm(payload,system):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active)
        time.sleep(.01)
        role=json.loads(payload)['role']
        with lock:active-=1
        return json.dumps(response(bundle,role))
    result=agents.review_roles(bundle,agents.ROLES,llm=llm,max_workers=2)
    assert set(result)==set(agents.ROLES) and 1<peak<=2
    assert {r['design_hash'] for r in result.values()}=={bundle['analysis']['design_hash']}
    with pytest.raises(ValueError):agents.review_roles(bundle,['structure'],llm=llm,max_workers=4)
    with pytest.raises(ValueError):agents.review_roles(bundle,['structure','structure'],llm=llm)


def test_invalid_json_and_extra_fields_are_repaired_only_once(bundle):
    calls=[]
    def llm(*args):calls.append(args);return 'not json'
    with pytest.raises(ValueError):agents.review_role(bundle,'structure',llm=llm)
    assert len(calls)==2


def test_snapshot_survives_original_bundle_mutation_during_call(bundle):
    original=response(bundle)
    def llm(*args):
        bundle['analysis']['findings'][0]['status']='pass'
        bundle['accepted']['inputs']['soil_kpa']['value']=200
        return json.dumps(original)
    result=agents.review_role(bundle,'structure',llm=llm)
    assert result['findings'][0]['status']=='missing_input'
    assert result['inputs_hash']==original['inputs_hash']


@pytest.mark.parametrize('quote',['The deterministic finding records 1,200.00 kPa.','The deterministic finding records 1200 kPa.','The deterministic finding records 1.2e3 kPa.'])
def test_cited_finding_numeric_quotes_accept_equivalent_decimal_format(bundle,quote):
    bundle['analysis']['findings'][0]['evidence']='Recorded pressure: 1200.0 kPa; missing load still unresolved.'
    bundle['analysis']['findings'][0]['values']={'recorded_pressure_kpa':1200}
    result=agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=lambda v:v.update(summary=quote)))
    assert result['summary']==quote
    assert result['findings'][0]['status']=='missing_input'


def test_exact_supplied_input_numeric_quote_preserves_source(bundle):
    supplied={'value':150.0,'source':'drawing','basis':'Printed geotechnical note; verify with the engineer'}
    bundle['accepted']['inputs']['soil_kpa']=supplied
    bundle['analysis']['inputs_hash']=digest(bundle['accepted']['inputs'])
    before=copy.deepcopy(bundle)
    def mutate(v):
        v['finding_ids']=[];v['input_paths']=['/accepted/inputs/soil_kpa/value']
        v['summary']='The supplied bearing value is 150 kPa; the footing load remains missing.'
        v['questions']=[{'question':'Can the engineer verify the recorded 150 kPa basis?','finding_ids':[],
            'input_paths':['/accepted/inputs/soil_kpa']}]
    result=agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=mutate))
    assert result['summary'].startswith('The supplied bearing value is 150')
    assert bundle==before and bundle['accepted']['inputs']['soil_kpa']['source']=='drawing'


@pytest.mark.parametrize('block',['summary','recommendation','question'])
def test_numbers_require_their_own_block_citations(bundle,block):
    bundle['analysis']['findings'][0]['values']={'recorded_pressure_kpa':150}
    def mutate(v):
        if block=='summary':
            v['finding_ids']=['global-structure'];v['summary']='The source pressure is 150 kPa.'
            v['recommendations'][0]['finding_ids']=['bearing']
        elif block=='recommendation':
            v['summary']='The source pressure is 150 kPa.'
            v['recommendations'][0]['finding_ids']=['global-structure']
            v['recommendations'][0]['rationale']='Check the recorded 150 kPa basis.'
        else:
            v['summary']='The source pressure is 150 kPa.'
            v['questions']=[{'question':'Is the pressure 150 kPa?','finding_ids':['global-structure'],'input_paths':[]}]
    with pytest.raises(ValueError,match='own cited'):
        agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=mutate))


@pytest.mark.parametrize('summary',[
    'The calculated result is 240 kPa.',
    'The soil value is 0 kPa.',
    'The converted value is 500 millimetres.',
])
def test_uncited_computed_converted_and_missing_values_are_never_inferred(bundle,summary):
    bundle['analysis']['findings'][0]['values']={'length_m':.5,'load':120}
    def mutate(v):
        v['summary']=summary;v['input_paths']=['/accepted/inputs/soil_kpa/value']
    with pytest.raises(ValueError,match='never infer'):
        agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=mutate))
    assert bundle['accepted']['inputs']['soil_kpa']['value'] is None


def test_arithmetic_expression_is_rejected_even_when_operands_and_answer_are_cited(bundle):
    bundle['analysis']['findings'][0]['values']={'recorded':120,'other_recorded':240}
    with pytest.raises(ValueError,match='arithmetic'):
        agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=lambda v:v.update(summary='120 + 120 = 240 kPa.')))


def test_ordinary_number_words_are_allowed_in_advice(bundle):
    summary='Ask one specialist to double check the basis before proposing the next revision.'
    result=agents.review_role(bundle,'structure',llm=llm_for(bundle,mutate=lambda v:v.update(summary=summary)))
    assert result['summary']==summary


def test_finding_identifier_digits_are_not_evidence_of_a_calculated_value(bundle):
    bundle['analysis']['findings'][0]['id']='bearing-150'
    def llm(*args):
        value=response(bundle);value['finding_ids']=['bearing-150'];value['summary']='The pressure is 150 kPa.'
        value['recommendations']=[]
        return json.dumps(value)
    with pytest.raises(ValueError,match='own cited'):
        agents.review_role(bundle,'structure',llm=llm)

def test_a_cited_hyphenated_identifier_is_a_reference_not_arithmetic(bundle):
    bundle['analysis']['findings'][0]['id']='bearing-1-2'
    def llm(*args):
        value=response(bundle);value['finding_ids']=['bearing-1-2'];value['summary']='Review bearing-1-2 before supplying structural inputs.';value['recommendations']=[];value['questions']=[]
        return json.dumps(value)
    assert agents.review_role(bundle,'structure',llm=llm)['summary'].startswith('Review bearing-1-2')

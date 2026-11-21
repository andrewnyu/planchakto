import json,zipfile,io
import pytest
from backend.store import LocalStore,Conflict
from backend import planning_workflow as w
from backend.planning_models import EngineeringInputs,Programme,DetailRecipe
from backend.planning_details import compile_details
from backend.planning_checks import run_checks
from backend.concepts import DesignPlan
from backend.planning_outputs import bundle,render_pdf,render_dxf,render_zip

@pytest.fixture
def store(tmp_path):return LocalStore(str(tmp_path/'planning.sqlite3'))

def plan():return {'title':'Open hall','rationale':'Open hall with independent exit','footprint':[[0,0],[20,0],[20,15],[0,15]],'zones':[{'id':'hall','name':'Hall','kind':'retail','polygon':[[0,0],[20,0],[20,15],[0,15]],'requirement_ids':['selling']}],'openings':[{'id':'entry','from_zone':'hall','to_zone':'outside','segment':[[9,0],[11,0]],'kind':'door','placement':'exact'}]}

def programme():return {'name':'Test store','use':'Hardware retail','total_area_m2':300,'area_mode':'exact','requirements':[{'id':'selling','name':'Selling','kind':'retail','area_m2':300,'area_mode':'exact'}]}

def confirm(store,s,stage,value):
    s=w.propose(store,s['id'],s['version'],stage,value=value);return w.accept(store,s['id'],s['version'],s['proposals'][-1]['id'])

def design(store):
    s=w.create(store,'store');s=confirm(store,s,'programme',programme());s=confirm(store,s,'strategy',{'title':'No-site study','rationale':'Site not supplied','site_unavailable':True});s=confirm(store,s,'layout',plan());return confirm(store,s,'details',{'title':'Fit-out','arrays':[{'id':'shelves','zone_id':'hall','kind':'rack','name':'Rack','origin':[2,3],'item_width':1,'item_depth':2,'rows':2,'columns':3,'gap_x':2,'gap_y':2}]})

def test_end_to_end_and_outputs(store):
    s=design(store);assert len(s['accepted']['details']['items'])==6
    with pytest.raises(ValueError):w.approve(store,s['id'],s['version'],False)
    s=w.approve(store,s['id'],s['version'],True)
    s=confirm(store,s,'inputs',{})
    assert s['accepted']['inputs']['dead_kpa']['value'] is None
    s=w.checks(store,s['id'],s['version']);assert s['analysis_current']
    assert s['analysis']['summary']['missing_input']>0
    assert s['analysis']['quantities']['total_cost_php'] is None
    v=bundle(store,w.load(store,s['id']));assert render_pdf(v).startswith(b'%PDF');assert b'ENTITIES' in render_dxf(v)
    z=zipfile.ZipFile(io.BytesIO(render_zip(v)));assert set(z.namelist())=={'review.pdf','layout.dxf','quantities.csv','project.json','README.txt'}
    report=json.loads(z.read('project.json'));assert report['analysis']['design_hash']==report['accepted']['approval']['design_hash']
    s=confirm(store,s,'programme',{**programme(),'name':'Changed'})
    assert 'approval' not in s['accepted'] and not s['analysis_current']
    with pytest.raises(Conflict):bundle(store,w.load(store,s['id']))

def test_no_gate_bypass_and_cas(store):
    s=w.create(store)
    with pytest.raises(Conflict):w.propose(store,s['id'],s['version'],'layout',value=plan())
    next=w.propose(store,s['id'],s['version'],'programme',value=programme())
    with pytest.raises(Conflict):w.propose(store,s['id'],s['version'],'programme',value=programme())
    with pytest.raises(Conflict):w.approve(store,next['id'],next['version'],True)

def test_capacity_blocks_approval(store):
    s=design(store);p={**programme(),'cashier_counters':4};s=confirm(store,s,'programme',p)
    s=confirm(store,s,'strategy',{'title':'Study','rationale':'No site','site_unavailable':True});s=confirm(store,s,'layout',plan());s=confirm(store,s,'details',{'title':'Unresolved parking'})
    with pytest.raises(Conflict):w.approve(store,s['id'],s['version'],True)

def test_undo_redo_immutable_artifacts(store):
    s=design(store);original=s['refs']['details'];s=w.travel(store,s['id'],s['version'],-1);assert 'details' not in s['accepted']
    s=w.travel(store,s['id'],s['version'],1);assert s['refs']['details']==original
    artifact=store.get_design_artifact(original);artifact['data']['title']='mutated local copy';assert store.get_design_artifact(original)['data']['title']=='Fit-out'

def test_packing_reports_actual_count_and_keeps_door_clear():
    p=DesignPlan.model_validate(plan());r=DetailRecipe(title='Too many',arrays=[{'id':'rack','zone_id':'hall','kind':'rack','name':'Rack','item_width':5,'item_depth':5,'rows':10,'columns':10}]);d=compile_details(p,r)
    assert len(d.items)<100 and d.warnings
    from shapely.geometry import Polygon,LineString
    assert all(Polygon(i.polygon).intersection(LineString(p.openings[0].segment).buffer(.65)).area<.001 for i in d.items)

def test_missing_inputs_never_become_component_pass(store):
    s=design(store);p=DesignPlan.model_validate(plan());from backend.planning_models import DetailedPlan
    result=run_checks(Programme.model_validate(programme()),p,DetailedPlan.model_validate(s['accepted']['details']),EngineeringInputs(structural_model='simply_supported_steel_roof_bay'),'test')
    assert next(f for f in result['findings'] if f['id']=='roof-bay')['status']=='missing_input'
    assert next(f for f in result['findings'] if f['id']=='bearing')['status']=='missing_input'

def test_real_component_arithmetic_and_invalid_criteria(store):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):EngineeringInputs(criteria={'occupant_area_factor':{'value':0}})
    with pytest.raises(ValidationError):EngineeringInputs(circuits=[{'id':'c','power_factor':{'value':0}}])
    from backend.planning_models import DetailedPlan
    s=design(store);v=lambda n:{'value':n,'source':'user','basis':'Engineer test input'}
    i=EngineeringInputs(structural_model='simply_supported_steel_roof_bay',beam_self_weight='included_in_dead_load',beam_section='RHS200',bay_span=v(4),tributary_width=v(2),dead_kpa=v(.5),live_kpa=v(.75),elastic_modulus_mpa=v(200000),yield_strength_mpa=v(250),dead_factor=v(1.2),live_factor=v(1.6),deflection_ratio=v(240),footing_width=v(2),footing_load_kn=v(200),soil_kpa=v(100),circuits=[{'id':'c','phases':1,'voltage':v(230),'power_factor':v(1),'demand_factor':v(.8)}],loads=[{'id':'l','name':'Lights','zone_id':'hall','watts':v(100),'quantity':10,'circuit':'c'}])
    r=run_checks(Programme.model_validate(programme()),DesignPlan.model_validate(plan()),DetailedPlan.model_validate(s['accepted']['details']),i,'test');f={f['id']:f for f in r['findings']}
    assert f['bearing']['values']['pressure_kpa']==50
    assert f['roof-bay']['status'] in ('pass','fail')
    assert f['circuit-c']['values']['current_a']==pytest.approx(800/230)
    assert f['global-structure']['status']=='unsupported'

def test_http_version_conflicts_and_no_provider(store,monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main,ai
    monkeypatch.setattr(main,'_store',store);monkeypatch.setattr(ai,'provider',lambda:None)
    c=TestClient(main.app);s=c.post('/api/planning/sessions',json={'brief':'Three bedrooms'}).json()
    assert c.post(f'/api/planning/sessions/{s["id"]}/approve',json={'expected_version':s['version'],'acknowledged':True}).status_code==409
    req={'expected_version':s['version'],'stage':'programme','message':'Design it'}
    assert c.post(f'/api/planning/sessions/{s["id"]}/propose',json=req).status_code==503
    assert c.get(f'/api/planning/sessions/{s["id"]}').json()['version']==s['version']
    r=c.post(f'/api/planning/sessions/{s["id"]}/propose',json={**req,'value':programme()});assert r.status_code==200
    assert c.post(f'/api/planning/sessions/{s["id"]}/propose',json={**req,'value':programme()}).status_code==409
    # Read from a fresh store connection to verify persistence, not process memory.
    assert LocalStore(store.path).get_compose_session(s['id'])['version']==r.json()['version']

def test_late_model_reply_cannot_overwrite_newer_stage(store):
    s=w.create(store);initial=s['version']
    def llm(payload,system):
        w.propose(store,s['id'],initial,'programme',value=programme())
        yield json.dumps({'programme':programme(),'reply':'Generated'})
    with pytest.raises(Conflict):w.propose(store,s['id'],initial,'programme','Create programme',llm=llm)
    latest=w.load(store,s['id']);assert latest['version']==initial+1 and len(latest['candidates'])==1

def test_site_change_invalidates_design_and_stale_candidate(store):
    s=design(store);s=w.propose(store,s['id'],s['version'],'details',value={'title':'Other fitout'})
    candidate=s['proposals'][-1]['id'];s=w.set_site(store,s['id'],s['version'],{'boundary':[[-5,-5],[30,-5],[30,30],[-5,30]],'source':'Test','basis':'Test site'})
    assert 'programme' in s['accepted'] and 'layout' not in s['accepted']
    with pytest.raises(Conflict):w.accept(store,s['id'],s['version'],candidate)

def test_cloud_artifacts_are_immutable_and_metadata_is_cas(monkeypatch):
    from unittest.mock import Mock
    from backend.cloud_store import GoogleStore
    from google.api_core.exceptions import PreconditionFailed
    import backend.cloud_store as module
    cloud=GoogleStore.__new__(GoogleStore);cloud.workspace='test';cloud.bucket=Mock();cloud.root=Mock();cloud.fs=Mock()
    blob=cloud.bucket.blob.return_value
    first=cloud.save_design_artifact('programme',programme());blob.upload_from_string.assert_called_once();assert blob.upload_from_string.call_args.kwargs['if_generation_match']==0
    blob.upload_from_string.side_effect=PreconditionFailed('exists');assert cloud.save_design_artifact('programme',programme())==first
    doc=cloud.root.collection.return_value.document.return_value;doc.get.return_value.exists=False
    monkeypatch.setattr(module.firestore,'transactional',lambda f:f)
    saved=cloud.save_planning_session({'id':'compose-test','refs':{}});assert saved['version']==1
    doc.get.return_value.exists=True;doc.get.return_value.to_dict.return_value=saved
    with pytest.raises(Conflict):cloud.save_planning_session(saved,expected_version=0)
    assert cloud.save_planning_session(saved,expected_version=1)['version']==2

def test_spatial_cuts_remove_boundary_remnants_and_allow_intermediate_disconnection():
    from backend.concept_program import LayoutProgram,compile_program
    # U-shaped house: upper arms are disconnected after y=5, then split into two bedrooms.
    p=LayoutProgram.model_validate({'title':'Courtyard arms','rationale':'Connected base with private wings','footprint':[[0,0],[12,0],[12,12],[8,12],[8,5],[4,5],[4,12],[0,12]],'cuts':[{'region':'building','axis':'y','at':5,'low':'living','high':'arms'},{'region':'arms','axis':'x','at':6,'low':'west','high':'east'}],'spaces':[{'region':'living','name':'Living','kind':'living'},{'region':'west','name':'West bedroom','kind':'bedroom'},{'region':'east','name':'East bedroom','kind':'bedroom'}],'connections':[{'from_zone':'living','to_zone':'outside','width':1},{'from_zone':'west','to_zone':'living','width':1},{'from_zone':'east','to_zone':'living','width':1}]})
    from backend.concepts import evaluate
    result=compile_program(p);assert evaluate(result)['footprint_area_m2']==116

def test_public_path_is_explicit_and_does_not_cross_private_rooms():
    from backend.concept_program import LayoutProgram,compile_program
    p={'title':'Public spine','rationale':'Door through an open central gallery','footprint':[[0,0],[15,0],[15,10],[0,10]],'cuts':[{'region':'building','axis':'x','at':5,'low':'left','high':'rest'},{'region':'rest','axis':'x','at':10,'low':'middle','high':'right'}],'spaces':[{'region':'left','name':'Left','kind':'office'},{'region':'middle','name':'Gallery','kind':'circulation'},{'region':'right','name':'Right','kind':'office'}],'connections':[{'from_zone':'left','to_zone':'outside','width':1},{'from_zone':'right','to_zone':'left','width':1,'allow_public_path':True}]}
    result=compile_program(LayoutProgram.model_validate(p));assert any(o.from_zone=='middle' for o in result.openings)
    p['spaces'][1]['kind']='bedroom'
    with pytest.raises(ValueError):compile_program(LayoutProgram.model_validate(p))

def test_automatic_routes_preserve_requested_waypoints_and_width():
    from backend.planning_routes import resolve_route
    from backend.planning_models import Route
    from shapely.geometry import Polygon,LineString
    boundary=[[0,0],[30,0],[30,30],[0,30]];obstacle=Polygon([[10,0],[20,0],[20,20],[10,20]])
    route=Route(id='r',name='Truck access',kind='service',points=[[4,5],[26,5]],width=4,auto_route=True)
    resolved=resolve_route(route,boundary,[obstacle]);assert resolved.requested_points==route.points and len(resolved.points)>2
    assert LineString(resolved.points).buffer(1.99,join_style=2).intersection(obstacle).area==0
    assert resolve_route(resolved,boundary,[obstacle])==resolved

def test_import_revalidates_each_gate_and_does_not_restore_approval(store):
    s=design(store);s=w.approve(store,s['id'],s['version'],True)
    imported=w.import_project(store,{'schema_version':'planning-1','accepted':s['accepted'],'site':None})
    assert not imported['accepted'] and imported['proposals'][-1]['stage']=='programme'
    imported=w.accept(store,imported['id'],imported['version'],imported['proposals'][-1]['id'])
    for stage in ['strategy','layout','details']:
        imported=w.use_import(store,imported['id'],imported['version'],stage);imported=w.accept(store,imported['id'],imported['version'],imported['proposals'][-1]['id'])
    assert 'approval' not in imported['accepted'] and not imported['analysis_current']
    assert len(imported['accepted']['details']['items'])==6

def test_same_brief_alternatives_remain_selectable_after_confirmation(store):
    s=w.create(store);s=w.propose(store,s['id'],s['version'],'programme',value=programme());first=s['proposals'][-1]['id']
    s=w.propose(store,s['id'],s['version'],'programme',value={**programme(),'name':'Alternative'});second=s['proposals'][-1]['id']
    s=w.accept(store,s['id'],s['version'],first);s=w.accept(store,s['id'],s['version'],second);assert s['accepted']['programme']['name']=='Alternative'

def test_automatic_access_uses_requested_kinds_without_imposed_corridor():
    from backend.concept_program import LayoutProgram,compile_program
    p=LayoutProgram.model_validate({'title':'Open store with stock','rationale':'Direct replenishment without a hallway','footprint':[[0,0],[100,0],[100,80],[0,80]],'cuts':[{'region':'building','axis':'y','at':60,'low':'shop','high':'stock'}],'spaces':[{'region':'shop','name':'Shop','kind':'retail'},{'region':'stock','name':'Stock','kind':'storage'}],'connections':[{'from_zone':'shop','to_zone':'outside','width':4}],'auto_access':[{'region':'stock','from_kinds':['retail'],'width':2,'kind':'loading'}]})
    result=compile_program(p);assert len(result.openings)==2 and len(result.zones)==2
    assert next(o for o in result.openings if o.from_zone=='stock').to_zone=='shop'

def test_area_solver_preserves_confirmed_programme_on_a_clipped_irregular_lot():
    from backend.concept_program import LayoutProgram,compile_program
    from backend.concepts import SitePlan,evaluate
    lot=SitePlan(boundary=[[0,0],[130,0],[150,80],[80,140],[0,100]],source='Synthetic lot',basis='Synthetic geometry, not a real project')
    p=LayoutProgram.model_validate({'title':'Area-preserving store','rationale':'Model-selected clipped envelope with measured department areas','footprint':[[10,10],[110,10],[110,100],[10,100]],'clip_footprint_to_site':True,'clip_clearance_m':3,'fit_area_m2':10000,'cuts':[{'region':'building','axis':'y','low_area_m2':7000,'low':'selling','high':'storage'}],'spaces':[{'region':'selling','name':'Selling','kind':'retail'},{'region':'storage','name':'Storage','kind':'storage'}],'connections':[{'from_zone':'selling','to_zone':'outside','width':4}],'auto_access':[{'region':'storage','from_kinds':['retail'],'width':3,'kind':'loading'}]})
    result=evaluate(compile_program(p,lot),lot);assert result['footprint_area_m2']==10000
    assert [z['area_m2'] for z in result['zones']]==[7000,3000]

def test_included_support_rooms_are_measured_once_in_parent_area():
    from backend.planning_checks import programme_findings
    p=DesignPlan.model_validate(plan());p.zones[0].requirement_ids=['selling']
    from backend.planning_models import DetailedPlan
    recipe=DetailRecipe(title='Nested room',support_packs=[{'zone_id':'hall','rooms':[{'id':'office','name':'Office','kind':'office','width':3,'depth':3,'requirement_id':'office'}]}]);d=compile_details(p,recipe)
    programme_model=Programme.model_validate({**programme(),'requirements':programme()['requirements']+[{'id':'office','name':'Office','kind':'office','included_in':'selling','area_m2':9,'area_mode':'exact'}]})
    f=programme_findings(programme_model,p,d);assert next(x for x in f if x['id']=='requirement-selling')['values']['actual']==300
    assert next(x for x in f if x['id']=='requirement-office')['values']['actual']==9

def test_parking_envelope_cannot_claim_a_count_without_dimensions(store):
    s=w.create(store);s=confirm(store,s,'programme',{**programme(),'parking_spaces':105});s=confirm(store,s,'strategy',{'title':'Study','rationale':'No site','site_unavailable':True})
    with pytest.raises(ValueError,match='parking_intent'):w.propose(store,s['id'],s['version'],'layout',value=plan())

def test_fill_recipe_measures_actual_capacity_instead_of_guessed_rows():
    from shapely.geometry import Polygon
    p=DesignPlan.model_validate(plan());p.zones[0].kind='parking'
    recipe=DetailRecipe(title='Filled parking',arrays=[{'id':'bays','zone_id':'hall','kind':'parking','name':'Bay','packing':'fill','target_count':8,'item_width':2.5,'item_depth':5,'gap_x':0,'gap_y':6,'access_clearance':6,'edge_margin':.1}])
    d=compile_details(p,recipe);assert len(d.items)==7  # eighth bay does not fit the measured width
    assert d.warnings and d.items[-1].name=='Bay 7'
    assert all(Polygon(p.footprint).covers(Polygon(i.polygon)) for i in d.items)

def test_specialist_reviews_are_bound_to_analysis_and_invalidated_by_edits(store):
    s=design(store);s=w.approve(store,s['id'],s['version'],True);s=confirm(store,s,'inputs',{});s=w.checks(store,s['id'],s['version'])
    def llm(payload,system):
        context=json.loads(payload)
        return json.dumps({'role':'structure','design_hash':context['design_hash'],'inputs_hash':context['inputs_hash'],'summary':'Structural inputs need professional confirmation.','finding_ids':['roof-bay'],'input_paths':[],'recommendations':[],'questions':[]})
    s=w.specialist_review(store,s['id'],s['version'],'structure',llm=llm)
    assert s['agent_reviews']['structure']['mode']=='injected'
    assert s['agent_reviews']['structure']['analysis_result_hash']==s['analysis']['result_hash']
    s=confirm(store,s,'inputs',{'height':{'value':4,'source':'user','basis':'Architect section'}})
    assert not s['analysis_current'] and not s['agent_reviews']

def test_generic_counter_never_satisfies_cashier_requirement():
    from backend.planning_checks import programme_findings
    p=DesignPlan.model_validate(plan());programme_model=Programme.model_validate({**programme(),'cashier_counters':1})
    counter=compile_details(p,DetailRecipe(title='Kitchen/service counter',arrays=[{'id':'c','zone_id':'hall','kind':'counter','name':'Service surface','item_width':1,'item_depth':1,'packing':'fill','target_count':1}]))
    assert next(f for f in programme_findings(programme_model,p,counter) if f['id']=='capacity-cashiers')['status']=='fail'
    counter.recipe.arrays[0].kind='cashier';checkout=compile_details(p,counter.recipe)
    assert next(f for f in programme_findings(programme_model,p,checkout) if f['id']=='capacity-cashiers')['status']=='pass'

def test_session_catalog_lists_only_staged_planning_metadata(store,monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main
    monkeypatch.setattr(main,'_store',store);s=design(store)
    store.save_compose_session({'id':'compose-legacy','status':'active'})
    response=TestClient(main.app).get('/api/planning/sessions');assert response.status_code==200
    assert response.json()=={'sessions':[{'id':s['id'],'name':'Test store','updated_at':s['updated_at']}]}

def test_unentered_engineering_rows_cannot_validate_as_measurements(store):
    s=design(store);s=w.approve(store,s['id'],s['version'],True);s=confirm(store,s,'inputs',{})
    before=dict(s['refs']);version=s['version']
    for value in [{'vehicles':[{'id':'v','name':'Unknown vehicle','length':None,'width':None,'basis':'Awaiting measurements'}]},{'utilities':[{'id':'u','kind':'drain','point':[None,None],'basis':'Awaiting location'}]}]:
        with pytest.raises(ValueError):w.propose(store,s['id'],version,'inputs',value=value)
        assert w.load(store,s['id'])['refs']==before and w.load(store,s['id'])['version']==version
    result=w.propose(store,s['id'],version,'inputs',value={'utilities':[{'id':'origin','kind':'drain','point':[0,0],'source':'user','basis':'Explicitly supplied local origin for this synthetic test'}]})
    assert result['proposals'][-1]['data']['utilities'][0]['point']==[0,0]
    assert result['refs']==before

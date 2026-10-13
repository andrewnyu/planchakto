import pytest
from fastapi.testclient import TestClient
from backend.store import LocalStore,Conflict
from backend.domain import CommandRequest,Building
from backend.ai import AIPlan,AIRequest,validate_plan
import backend.main as main

@pytest.fixture
def store(tmp_path):return LocalStore(str(tmp_path/'test.sqlite3'))
@pytest.fixture
def client(store,monkeypatch):
    monkeypatch.setattr(main,'_store',store);monkeypatch.delenv('GEMINI_API_KEY',raising=False);monkeypatch.delenv('OPENROUTER_API_KEY',raising=False);monkeypatch.delenv('BUILDGRAPH_AI_PROVIDER',raising=False);monkeypatch.delenv('GOOGLE_CLOUD_PROJECT',raising=False)
    return TestClient(main.app)
def request(base,id='cmd1',load=1.5):return CommandRequest(base_revision=base,command_id=id,label='Load update',commands=[{'type':'set_parameter','field':'live','value':load}])

def test_preview_immutable_idempotent_and_undo_redo(store):
    head=store.state()['head'];before=store.get(head);cmd=request(head);draft=store.preview(cmd)
    assert store.state()['head']==head
    assert store.get(head)==before
    assert store.preview(cmd)['id']==draft['id']
    assert 'structure' in draft['invalidated']
    store.accept(draft['id'],head)
    assert store.state()['head']==draft['id']
    assert store.travel(-1,draft['id'])['id']==head
    assert store.travel(1,head)['id']==draft['id']
    reopened=LocalStore(store.path);assert reopened.state()['head']==draft['id']

def test_idempotency_conflict(store):
    head=store.state()['head'];store.preview(request(head))
    with pytest.raises(Conflict):store.preview(request(head,load=2))

def test_stale_acceptance_and_branching(store):
    head=store.state()['head'];a=store.preview(request(head,'a',1));b=store.preview(request(head,'b',2));store.accept(a['id'],head)
    with pytest.raises(Conflict):store.accept(b['id'],head)
    with pytest.raises(Conflict):store.accept(b['id'],a['id'])
    assert store.get(b['id'])['status']=='candidate'

def test_chained_candidate_acceptance(store):
    head=store.state()['head'];a=store.preview(request(head,'a',1));b=store.preview(request(a['id'],'b',2));store.accept(b['id'],head)
    assert store.state()['head']==b['id']

def test_discard_and_hard_constraint_rejection(store):
    head=store.state()['head'];a=store.preview(request(head));store.discard(a['id'])
    with pytest.raises(Conflict):store.accept(a['id'],head)
    invalid=store.preview(CommandRequest(base_revision=head,command_id='invalid',commands=[{'type':'move_room','room_id':'bath','x':2,'y':0}]))
    with pytest.raises(Conflict,match='hard layout'):store.accept(invalid['id'],head)

def test_api_native_import_export_and_missing_gemini(client):
    p=client.get('/api/project').json();id=p['state']['head']
    exported=client.get(f'/api/export/{id}/project.json');assert exported.status_code==200
    imported=client.post('/api/import/project',json={'model':exported.json()['model']});assert imported.status_code==200
    assert imported.json()['status']=='candidate'
    csv=client.get(f'/api/export/{id}/quantities.csv');assert 'source_ids' in csv.text and 'EXCLUDED' in csv.text
    report=client.get(f'/api/export/{id}/report');assert 'not whole-building certification' in report.text
    ai=client.post('/api/ai',json={'revision_id':id,'message':'Move the bathroom'});assert ai.status_code==503 and ai.json()['mode']=='unavailable'

def test_bad_survey_and_command_rejection(client):
    id=client.get('/api/project').json()['state']['head']
    response=client.post('/api/import/survey',json={'base_revision':id,'csv_text':'X,Y,Z\n0,0,0\n0,0,0\n1,1,1','units':'m'})
    assert response.status_code==422
    response=client.post('/api/commands',json={'base_revision':id,'command_id':'bad','commands':[{'type':'invent_a_result'}]})
    assert response.status_code==422

@pytest.mark.parametrize('action,commands,revision,valid',[
 ('edit',[{'type':'set_equipment','equipment_id':'eq-ac','watts':2000}],'a',True),
 ('edit',[{'type':'set_parameter','field':'soil','value':75}],'a',True),
 ('clarify',[],'a',True),
 ('inspect',[],'a',True),
 ('edit',[{'type':'set_lock','object_id':'hall','locked':False}],'a',False),
 ('edit',[{'type':'remove_column','column_id':'col-1-1'}],'old',False),
 ('inspect',[{'type':'remove_column','column_id':'col-1-1'}],'a',False),
])
def test_ai_plan_evaluation_contract(action,commands,revision,valid):
    req=AIRequest(revision_id='a',message='test');plan=AIPlan(revision_id=revision,action=action,commands=commands,explanation='test')
    if valid:assert validate_plan(plan,req)==plan
    else:
        with pytest.raises(ValueError):validate_plan(plan,req)

import json,backend.ai as ai
AI_ENV=('GEMINI_API_KEY','GEMINI_MODEL','GOOGLE_CLOUD_PROJECT','OPENROUTER_API_KEY','OPENROUTER_MODEL','BUILDGRAPH_AI_PROVIDER')
@pytest.mark.parametrize('env,expected',[
    ({},None),
    ({'GEMINI_API_KEY':'k'},None),
    ({'OPENROUTER_API_KEY':'k','OPENROUTER_MODEL':'m'},'openrouter'),
    ({'GEMINI_API_KEY':'k','GEMINI_MODEL':'g','OPENROUTER_API_KEY':'k','OPENROUTER_MODEL':'m'},'gemini'),
    ({'GEMINI_API_KEY':'k','GEMINI_MODEL':'g','OPENROUTER_API_KEY':'k','OPENROUTER_MODEL':'m','BUILDGRAPH_AI_PROVIDER':'openrouter'},'openrouter'),
    ({'GEMINI_API_KEY':'k','GEMINI_MODEL':'g','BUILDGRAPH_AI_PROVIDER':'openrouter'},None),
    ({'GOOGLE_CLOUD_PROJECT':'p','GEMINI_MODEL':'g'},'vertex'),
    ({'GOOGLE_CLOUD_PROJECT':'p','GEMINI_MODEL':'g','OPENROUTER_API_KEY':'k','OPENROUTER_MODEL':'m'},'vertex'),
    ({'GOOGLE_CLOUD_PROJECT':'p','BUILDGRAPH_AI_PROVIDER':'vertex'},None),
])
def test_ai_provider_selection(monkeypatch,env,expected):
    for k in AI_ENV:monkeypatch.delenv(k,raising=False)
    for k,v in env.items():monkeypatch.setenv(k,v)
    assert ai.status()['ai_provider']==expected

def test_openrouter_response_is_validated_like_gemini(client,monkeypatch):
    for k in AI_ENV:monkeypatch.delenv(k,raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY','k');monkeypatch.setenv('OPENROUTER_MODEL','test/model')
    head=client.get('/api/project').json()['state']['head'];sent={}
    class Resp:
        def __init__(self,content):self.content=content
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':self.content}}]}
    def fake_post(url,**kw):
        sent.update(url=url,body=kw['json'],auth=kw['headers']['Authorization'])
        return Resp('```json\n'+json.dumps({'revision_id':head,'action':'inspect','explanation':'Read-only review'})+'\n```')
    import httpx;monkeypatch.setattr(httpx,'post',fake_post)
    assert client.get('/api/health').json()['ai_provider']=='openrouter'
    r=client.post('/api/ai',json={'revision_id':head,'message':'What fails?'})
    assert r.status_code==200 and r.json()['interpretation']['action']=='inspect' and r.json()['candidate'] is None
    assert sent['url']==ai.OPENROUTER_URL and sent['auth']=='Bearer k' and sent['body']['model']=='test/model'
    assert '"AIPlan"' in sent['body']['messages'][0]['content'] and 'temperature' not in sent['body']
    monkeypatch.setattr(httpx,'post',lambda *a,**k:Resp(json.dumps({'revision_id':'stale','action':'inspect','explanation':'x'})))
    r=client.post('/api/ai',json={'revision_id':head,'message':'What fails?'})
    assert r.status_code==502 and r.json()['mode']=='error'

def test_vertex_uses_adc_client_with_project_and_location(client,monkeypatch):
    for k in AI_ENV:monkeypatch.delenv(k,raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','proj');monkeypatch.setenv('GEMINI_MODEL','gemini-test');monkeypatch.setenv('GOOGLE_CLOUD_LOCATION','us-central1')
    head=client.get('/api/project').json()['state']['head'];made={}
    from google import genai
    class Models:
        def get(self,model):made['checked']=model
        def generate_content(self,model,contents,config):
            made['thinking']=config.thinking_config.thinking_level
            class R:text=json.dumps({'revision_id':head,'action':'rules','explanation':'Rule inventory'})
            return R()
    class FakeClient:
        def __init__(self,**kw):made.update(kw);self.models=Models()
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(genai,'Client',FakeClient)
    assert client.get('/api/health').json()['ai_provider']=='vertex'
    r=client.post('/api/ai',json={'revision_id':head,'message':'Which rules apply?'})
    assert r.status_code==200 and r.json()['interpretation']['action']=='rules'
    assert made['vertexai'] is True and made['project']=='proj' and made['location']=='us-central1' and 'api_key' not in made and made['checked']=='gemini-test' and made['thinking']=='LOW'

def test_gemini_schema_is_decodable_subset_and_validation_still_enforces_limits():
    from backend.ai import gemini_schema,RESTRICTED
    text=json.dumps(gemini_schema())
    assert '$ref' not in text and '"const"' not in text and 'maxItems' not in text and 'oneOf' not in text
    types={x['properties']['type']['enum'][0] for x in gemini_schema()['properties']['commands']['items']['anyOf']}
    assert types and not types&RESTRICTED and 'move_room' in types
    too_many={'revision_id':'a','action':'edit','explanation':'x','commands':[{'type':'reroute'}]*21}
    with pytest.raises(Exception):AIPlan.model_validate(too_many)

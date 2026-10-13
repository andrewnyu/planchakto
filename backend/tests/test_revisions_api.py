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
    monkeypatch.setattr(main,'_store',store);monkeypatch.delenv('GEMINI_API_KEY',raising=False)
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

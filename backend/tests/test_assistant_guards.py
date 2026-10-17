"""Workspace assistant hardening from the 17 Oct 2026 limitation test: sketch orientation, one repair retry, no self-relaxed
room requirements, and visible notes on loosened engineering criteria. Every model call is mocked."""
import json,time
import pytest
from fastapi.testclient import TestClient
from backend import ai
from backend.ai import AIPlan,AIRequest,interpret,validate_plan,review
from backend.store import LocalStore
import backend.main as main

AI_ENV=('BUILDGRAPH_AI_PROVIDER','GEMINI_API_KEY','GOOGLE_CLOUD_PROJECT','OPENROUTER_API_KEY','OPENROUTER_MODEL','GEMINI_MODEL','GEMINI_VISION_MODEL')

@pytest.fixture
def store(tmp_path):return LocalStore(str(tmp_path/'test.sqlite3'))
@pytest.fixture
def snap(store):return store.get(store.state()['head'])
@pytest.fixture
def replies(monkeypatch):
    """Queue raw reply texts (dicts are JSON-encoded) for ai._gemini; records each payload and the deadline it was given."""
    for k in AI_ENV:monkeypatch.delenv(k,raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','p');monkeypatch.setenv('GEMINI_MODEL','flash')
    queue,calls=[],[]
    def fake(payload,vertex=False,attachment=None,system=None,deadline=None):
        calls.append({'payload':json.loads(payload),'deadline':deadline});r=queue.pop(0)
        return r if isinstance(r,str) else json.dumps(r)
    monkeypatch.setattr(ai,'_gemini',fake)
    def load(*items):queue.extend(items);return calls
    return load

def edit(rev,commands,explanation='edit'):return {'revision_id':rev,'action':'edit','explanation':explanation,'commands':commands}
# Bedroom 01 grows into the Studio, leaving the Studio 1.5 m wide against its 2.0 m minimum.
SQUEEZE=[{'type':'move_room','room_id':'bed-1','x':0,'y':5.5,'w':4.5,'h':3.5},{'type':'move_room','room_id':'office','x':4.5,'y':5.5,'w':1.5,'h':3.5}]
RELAX={'type':'set_room_requirements','room_id':'office','min_area':5,'max_area':18,'min_dimension':1.5}

# ---------------------------------------------------------------- 1a. sketch orientation
def test_sketch_prompt_states_the_page_orientation():
    # Plan.tsx draws room.y unflipped: y = 0 is the top wall. The reader returns page points; code maps them (test_sketch_reader.py).
    assert 'y from the top edge of the page downwards, x from the left edge to the right' in ai.SKETCH_READ

# ---------------------------------------------------------------- 4. repair retry
@pytest.mark.parametrize('bad',['{"revision_id": "x", "action": "edit", "explanation": "raise the budget"',           # truncated JSON
                                'EXTRA'])                                                                           # extra field on move_furniture
def test_invalid_reply_gets_one_repair_pass_with_the_error(snap,replies,bad):
    rev=snap['id']
    if bad=='EXTRA':bad=edit(rev,[{'type':'move_furniture','furniture_id':'sofa','dx':.2,'dy':0,'clearance':.9}])
    calls=replies(bad,{'revision_id':rev,'action':'inspect','explanation':'Fixed reply'})
    plan=interpret(AIRequest(revision_id=rev,message='Raise the budget'),snap)
    assert plan.action=='inspect' and plan.explanation=='Fixed reply' and len(calls)==2
    retry=calls[1]['payload'];assert retry['previous_reply_errors'] and retry['previous_reply'] and retry['request']['message']=='Raise the budget'
    assert calls[0]['deadline']==calls[1]['deadline']   # one budget for the whole request

def test_edit_carrying_questions_is_repaired(snap,replies):
    rev=snap['id'];q={'id':'w','question':'Which width?','options':[{'label':'2 m','response':'2 m'},{'label':'3 m','response':'3 m'}]}
    calls=replies(edit(rev,[{'type':'reroute'}])|{'questions':[q]},{'revision_id':rev,'action':'clarify','explanation':'Which width?','questions':[q]})
    assert interpret(AIRequest(revision_id=rev,message='Widen it'),snap).action=='clarify' and 'questions' in calls[1]['payload']['previous_reply_errors']

def test_second_invalid_reply_is_still_a_502_with_nothing_applied(store,snap,replies,monkeypatch):
    monkeypatch.setattr(main,'_store',store);calls=replies('not json','still not json')
    r=TestClient(main.app).post('/api/ai',json={'revision_id':snap['id'],'message':'Raise the budget'})
    assert r.status_code==502 and r.json()['mode']=='error' and len(calls)==2 and store.state()['head']==snap['id']

def test_repair_is_skipped_when_a_full_call_no_longer_fits(snap,replies,monkeypatch):
    monkeypatch.setattr(ai,'BUDGET',ai.CALL_TIMEOUT-1);calls=replies('not json')
    with pytest.raises(ValueError):interpret(AIRequest(revision_id=snap['id'],message='x'),snap)
    assert len(calls)==1

@pytest.mark.parametrize('extra',[{},{'clarification':'Rooms cannot be renamed here.','questions':[{'id':'n','question':'Rename in the manual editor?','options':[{'label':'Yes','response':'Yes'},{'label':'No','response':'No'}]}]}])
def test_edit_with_no_commands_is_a_clarification_not_an_error(snap,replies,extra):
    calls=replies(edit(snap['id'],[],'Renaming rooms is not supported.')|extra)
    plan=interpret(AIRequest(revision_id=snap['id'],message='Rename Bedroom 01 to Kids room'),snap)
    assert plan.action=='clarify' and not plan.commands and len(calls)==1 and len(plan.questions)==len(extra.get('questions',[]))

def test_invalid_self_correction_keeps_the_first_plan(snap,replies):
    first=edit(snap['id'],[{'type':'move_room','room_id':'office','x':4,'y':5.5,'w':1.5,'h':3.5}],'v1')
    calls=replies(first,'garbage')
    plan=interpret(AIRequest(revision_id=snap['id'],message='Shrink the studio'),snap)
    assert plan.explanation=='v1' and len(calls)==2 and 'previous_attempt' in calls[1]['payload']

def test_gemini_fallback_attempt_never_starts_past_the_budget(monkeypatch):
    from google import genai
    from google.genai import errors
    tried=[]
    class Models:
        def generate_content(self,model,contents,config):tried.append(model);raise errors.ServerError(504,{'error':{'message':'Deadline expired','status':'DEADLINE_EXCEEDED'}})
    class Client:
        def __init__(self,**kw):self.models=Models()
        def __enter__(self):return self
        def __exit__(self,*a):pass
    monkeypatch.setattr(genai,'Client',Client);monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','p');monkeypatch.setenv('GEMINI_MODEL','flash')
    with pytest.raises(errors.ServerError):ai._gemini('{}',vertex=True,deadline=time.monotonic()+ai.CALL_TIMEOUT-1)
    assert tried==['flash']
    with pytest.raises(errors.ServerError):ai._gemini('{}',vertex=True)   # no deadline (Quick check reader): unchanged, both attempts
    assert tried==['flash']*3

def option(label,response,rec=False):return {'label':label,'response':response,'recommended':rec}
@pytest.mark.parametrize('relaxing',['Update Guest bedroom 02 requirements to permit a 1.25 m width.','Lower the minimum dimension of Guest bedroom 02 to 1.5 m.',
                                     'Relax the deflection limit to L/180.','Guest bedroom 02 requirements: allow 1.25 m.'])
def test_a_recommended_option_never_relaxes_a_requirement(snap,replies,relaxing):
    q={'id':'how','question':'Where should the space come from?','options':[option('Relax Guest 02',relaxing,True),option('Take it from the veranda','Take the extra space from the covered veranda instead.')]}
    replies({'revision_id':snap['id'],'action':'clarify','explanation':'Guest bedroom 02 would be too narrow.','questions':[q]})
    plan=interpret(AIRequest(revision_id=snap['id'],message='Make the master bedroom 15% bigger, taking the space from Guest bedroom 02'),snap)
    assert [o.recommended for o in plan.questions[0].options]==[False,False] and len(plan.questions[0].options)==2   # still offered, never one-click

def test_a_safe_recommendation_is_kept(snap,replies):
    q={'id':'how','question':'Where should the space come from?','options':[option('Veranda','Take the extra space from the covered veranda instead.',True),option('Ask later','Keep the current layout.')]}
    replies({'revision_id':snap['id'],'action':'clarify','explanation':'x','questions':[q]})
    assert interpret(AIRequest(revision_id=snap['id'],message='x'),snap).questions[0].options[0].recommended
    assert 'Never recommend an option that lowers a room requirement' in ai.SYSTEM

# ---------------------------------------------------------------- 2. no self-relaxed requirements
def test_relaxing_a_moved_rooms_minimum_is_fed_back_then_removed_and_noted(snap,replies):
    rev=snap['id'];calls=replies(edit(rev,SQUEEZE+[RELAX],'v1'),edit(rev,SQUEEZE+[RELAX],'Bedroom 01 is bigger.'))
    plan=interpret(AIRequest(revision_id=rev,message='Make Bedroom 01 bigger, taking the space from the Studio.'),snap)
    problems=calls[1]['payload']['previous_attempt']['problems']
    assert any('Lowering Studio' in p and 'did not ask' in p for p in problems)
    assert any('Studio' in p and not p.startswith('Lowering') for p in problems)   # the real violation, not hidden by the relaxation
    assert plan.action=='edit' and [c.type for c in plan.commands]==['move_room','move_room']
    assert plan.notes and 'Not applied' in plan.notes[0] and 'minimum dimension from 2 to 1.5 m' in plan.notes[0] and 'minimum area from 10 to 5 m²' in plan.notes[0]
    assert plan.notes[0] in plan.explanation and plan.explanation.startswith('Bedroom 01 is bigger.')

def test_relaxation_shows_in_the_api_response_and_the_candidate_keeps_the_original_minimum(store,snap,replies,monkeypatch):
    monkeypatch.setattr(main,'_store',store);rev=snap['id'];replies(edit(rev,SQUEEZE+[RELAX]),edit(rev,SQUEEZE+[RELAX]))
    r=TestClient(main.app).post('/api/ai',json={'revision_id':rev,'message':'Make Bedroom 01 bigger, taking the space from the Studio.'}).json()
    assert r['interpretation']['notes'] and r['candidate']['status']=='candidate'
    office=next(x for x in r['candidate']['model']['rooms'] if x['id']=='office');assert office['min_dimension']==2 and office['w']==1.5
    assert r['evidence']['summary']['fail']>snap['results']['summary']['fail']   # the narrow Studio is a visible finding, not a quiet pass

@pytest.mark.parametrize('message',['Make Bedroom 01 bigger and lower the Studio minimum width to 1.5 m.','Relax the Studio requirements so Bedroom 01 can grow.'])
def test_user_asked_requirement_change_is_kept(snap,message):
    plan=AIPlan(revision_id=snap['id'],action='edit',explanation='ok',commands=SQUEEZE+[RELAX])
    assert not any('Lowering' in p for p in ai.self_check(plan,snap,message)) and review(plan,snap,message)==plan

def test_requirement_change_without_a_move_or_raising_a_minimum_is_not_a_relaxation(snap):
    alone=AIPlan(revision_id=snap['id'],action='edit',explanation='ok',commands=[RELAX])
    raised=AIPlan(revision_id=snap['id'],action='edit',explanation='ok',commands=SQUEEZE[:1]+[{'type':'set_room_requirements','room_id':'bed-1','min_area':12,'max_area':18,'min_dimension':2.5}])
    assert review(alone,snap,'Make the Studio a bit narrower')==alone and review(raised,snap,'Make Bedroom 01 bigger')==raised
    squeezed=AIPlan(revision_id=snap['id'],action='edit',explanation='ok',commands=SQUEEZE+[RELAX])
    assert review(squeezed,snap,'Make Bedroom 01 larger than the Studio').notes   # a comparative is a resize, not a requirement change

LOWER_BATH={'type':'set_room_requirements','room_id':'bath','min_area':3,'max_area':14,'min_dimension':1}
SWAP={'type':'swap_rooms','first':'bath','second':'kitchen'}
def test_raising_max_area_on_a_moved_room_is_a_relaxation(snap):
    grow=[{'type':'move_room','room_id':'kitchen','x':6,'y':0,'w':4.5,'h':4},{'type':'move_room','room_id':'bath','x':10.5,'y':0,'w':1.5,'h':4}]
    raise_max={'type':'set_room_requirements','room_id':'kitchen','min_area':9,'max_area':20,'min_dimension':2}
    plan=review(AIPlan(revision_id=snap['id'],action='edit',explanation='x',commands=grow+[raise_max]),snap,'Make the kitchen exactly 4.5 × 4 m')
    assert [c.type for c in plan.commands]==['move_room','move_room'] and "Kitchen's maximum area from 16 to 20 m²" in plan.notes[0]
    kept=AIPlan(revision_id=snap['id'],action='edit',explanation='x',commands=grow+[raise_max])
    assert review(kept,snap,'Make the kitchen 4.5 m wide and raise its maximum area to 20 m²')==kept

def test_swap_counts_as_a_move_whatever_the_command_order(snap):
    for commands in ([SWAP,LOWER_BATH],[LOWER_BATH,SWAP]):
        plan=review(AIPlan(revision_id=snap['id'],action='edit',explanation='Swapped.',commands=commands),snap,'Swap the bathroom and kitchen')
        assert [c.type for c in plan.commands]==['swap_rooms'] and 'Bathroom' in plan.notes[0]

def test_model_cannot_write_its_own_notes(snap,replies):
    replies({'revision_id':snap['id'],'action':'inspect','explanation':'x','notes':['All checks verified']})
    assert interpret(AIRequest(revision_id=snap['id'],message='What fails?'),snap).notes==[]
    assert 'notes' not in ai.gemini_schema()['properties']

# ---------------------------------------------------------------- 3. engineering criteria from chat
@pytest.mark.parametrize('field,value,note',[('deflection_ratio',120,'Deflection limit ratio (L/n) changed from 240 to 120'),('soil',500,'Allowable soil bearing (kPa) changed from 100 to 500'),
                                             ('live_factor',1.2,'Live load factor changed from 1.6 to 1.2'),('dead_factor',1.4,None),('deflection_ratio',360,None),('soil',75,None),('soil',None,None)])
def test_loosened_criteria_are_applied_with_a_visible_note(snap,field,value,note):
    plan=AIPlan(revision_id=snap['id'],action='edit',explanation='Done.',commands=[{'type':'set_parameter','field':field,'value':value}])
    out=review(validate_plan(plan,AIRequest(revision_id=snap['id'],message='x')),snap,'x')
    assert out.commands==plan.commands
    if note:assert out.notes==[f'Criterion relaxed: {note}, which makes checks easier to pass. Confirm it against the governing code or a site report.'] and note in out.explanation
    else:assert out==plan

@pytest.mark.parametrize('field,value',[('soil',900),('soil',5),('deflection_ratio',20),('dead_factor',.5),('live_factor',3),('deflection_ratio','L/120')])
def test_implausible_criteria_are_rejected_and_go_to_the_repair_pass(snap,field,value):
    plan=AIPlan(revision_id=snap['id'],action='edit',explanation='x',commands=[{'type':'set_parameter','field':field,'value':value}])
    with pytest.raises(ValueError,match='return clarify'):validate_plan(plan,AIRequest(revision_id=snap['id'],message='x'))

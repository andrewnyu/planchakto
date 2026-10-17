"""Sketch edits read typed page corners and map them to metres in code (report §1b). Every reading is mocked.
The demo is 12 × 9 m: living / kitchen / bath on y 0–4, the locked corridor on y 4–5.5, Bedroom 01 / Studio / Bedroom 02 on y 5.5–9."""
import base64,json,math
import pytest
from backend import ai
from backend.ai import AIRequest,Attachment,SketchReading,interpret,map_sketch
from backend.store import LocalStore

AI_ENV=('BUILDGRAPH_AI_PROVIDER','GEMINI_API_KEY','GOOGLE_CLOUD_PROJECT','OPENROUTER_API_KEY','OPENROUTER_MODEL','GEMINI_MODEL','GEMINI_VISION_MODEL')
PNG=base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'0'*64).decode()

@pytest.fixture
def snap(tmp_path):s=LocalStore(str(tmp_path/'t.sqlite3'));return s.get(s.state()['head'])
@pytest.fixture
def replies(monkeypatch):
    for k in AI_ENV:monkeypatch.delenv(k,raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT','p');monkeypatch.setenv('GEMINI_MODEL','flash')
    queue,calls=[],[]
    def fake(payload,vertex=False,attachment=None,system=None,deadline=None):
        calls.append({'payload':json.loads(payload),'system':system,'attachment':attachment});r=queue.pop(0)
        return r if isinstance(r,str) else json.dumps(r)
    monkeypatch.setattr(ai,'_gemini',fake)
    def load(*items):queue.extend(items);return calls
    return load

# Page = 100 + 80 units per metre, optionally pushed through a tilt (7° rotation + keystone perspective) like a phone photo.
def page(x,y,tilt=False):
    px,py=100+80*x,100+80*y
    if not tilt:return [py,px]
    a=math.radians(7);cx,cy=580,460;dx,dy=px-cx,py-cy
    rx,ry=dx*math.cos(a)-dy*math.sin(a),dx*math.sin(a)+dy*math.cos(a)
    w=1-.0002*ry   # perspective: the bottom of the page is nearer the camera, so drawn larger
    return [cy+ry/w,cx+rx/w]
def corners(x0,y0,x1,y1,tilt=False):return [page(x0,y0,tilt),page(x1,y0,tilt),page(x1,y1,tilt),page(x0,y1,tilt)]
def reading(spaces,tilt=False,**kw):
    return {'outline':corners(0,0,12,9,tilt),'spaces':[{'label':label,'room_id':rid,'corners':corners(*rect,tilt=tilt)} for label,rid,rect in spaces]}|kw
# Bedroom 01 grows to 4.5 m and the Studio shrinks to 3.5 m. Edges are drawn with wall gaps and up to 0.15 m of hand error.
WIDER=[('BED 1','bed-1',(0.06,5.62,4.42,8.93)),('STUDY ROOM','office',(4.6,5.58,7.91,8.95)),('BED 2','bed-2',(8.1,5.6,11.94,8.9))]
def ask(snap,message='Rearrange like my sketch'):
    return AIRequest(revision_id=snap['id'],message=message,attachment=Attachment(mime_type='image/png',data=PNG,name='sketch.png'))
def moves(plan):return {c.room_id:(c.x,c.y,c.w,c.h) for c in plan.commands}

@pytest.mark.parametrize('tilt',[False,True])
def test_corners_are_rectified_scaled_and_snapped_into_shared_walls(snap,replies,tilt):
    calls=replies(reading(WIDER,tilt=tilt))
    plan=interpret(ask(snap),snap)
    assert plan.action=='edit' and moves(plan)=={'bed-1':(0,5.5,4.5,3.5),'office':(4.5,5.5,3.5,3.5)}   # Bedroom 02 already matches
    assert len(calls)==1 and 'single-storey building' in calls[0]['system'] and '"SketchSpace"' in calls[0]['system']
    assert {r['id'] for r in calls[0]['payload']['rooms']}>={'bed-1','office','hall'} and calls[0]['payload']['footprint']=={'width':12,'depth':9}
    assert 'Bedroom 01 4.5 × 3.5 m at x 0, y 5.5' in plan.explanation and not any(c.type=='set_room_requirements' for c in plan.commands)

def test_unknown_label_is_listed_and_the_rest_still_applies(snap,replies):
    replies(reading(WIDER[:2],unmapped=['GYM'])|{'spaces':reading(WIDER[:2])['spaces']+[{'label':'POOL','room_id':None,'corners':corners(8.1,5.6,11.9,8.9)}]})
    plan=interpret(ask(snap),snap)
    assert plan.action=='edit' and set(moves(plan))=={'bed-1','office'}
    assert any('Not matched to a project room, so not placed: GYM, POOL.' in n for n in plan.notes) and any('Bedroom 02' in n and 'left where they are' in n for n in plan.notes)

def test_room_id_given_as_a_name_is_resolved_and_an_unknown_id_is_unmapped(snap,replies):
    spaces=[('BED 1','Bedroom 01',WIDER[0][2]),('STUDY ROOM','office',WIDER[1][2]),('X','room-x',WIDER[2][2])]
    replies(reading(spaces));plan=interpret(ask(snap),snap)
    assert set(moves(plan))=={'bed-1','office'} and any('X.' in n for n in plan.notes)

def test_infeasible_layout_is_a_clarification_naming_rooms_and_never_relaxes(snap,replies):
    replies(reading([('BED 1','bed-1',(0,5.5,6,9)),('STUDY','office',(6,5.5,8,9))]))
    plan=interpret(ask(snap),snap)
    assert plan.action=='clarify' and not plan.commands
    assert 'Bedroom 01 (6 × 3.5 m) would be 21 m², over its 18 m² maximum' in plan.clarification
    assert 'Studio (2 × 3.5 m) would be 7 m², under its 10 m² minimum' in plan.clarification and 'Redraw those rooms' in plan.clarification

def test_overlap_from_the_drawing_is_refused(snap,replies):
    replies(reading([('BED 1','bed-1',(0,5.5,5,9))]))   # grows over the Studio, which is not on the drawing and stays put
    plan=interpret(ask(snap),snap)
    assert plan.action=='clarify' and 'Bedroom 01 overlaps Studio' in plan.clarification

def test_sub_precision_error_is_nudged_within_the_drawing_tolerance(snap,replies):
    # 5.2 m makes Bedroom 01 18.2 m² (max 18) and the Studio 9.8 m² (min 10); moving their shared wall 0.1 m fixes both.
    replies(reading([('BED 1','bed-1',(0,5.5,5.2,9)),('STUDY','office',(5.2,5.5,8,9))]))
    plan=interpret(ask(snap),snap)
    assert plan.action=='edit' and moves(plan)=={'bed-1':(0,5.5,5.1,3.5),'office':(5.1,5.5,2.9,3.5)}
    assert any('shared wall moved 0.10 m' in n for n in plan.notes)

def test_a_room_drawn_into_the_locked_corridor_stops_at_its_wall(snap,replies):
    replies(reading([('BED 1','bed-1',(0,5.0,4.5,9)),('STUDY','office',(4.5,5.5,8,9))]))
    plan=interpret(ask(snap),snap)
    assert moves(plan)['bed-1']==(0,5.5,4.5,3.5) and any('0.50 m into Circulation, which is locked' in n for n in plan.notes)

@pytest.mark.parametrize('extra,why',[({'width':20,'depth':9},'dimensioned 20 × 9 m but the project is 12 × 9 m'),({'readable':False},'could not be read'),
                                      ({'outline':None},'outline could not be located'),({'outline':[[100,100]]*4},'outline could not be located')])
def test_unusable_readings_are_clarifications(snap,replies,extra,why):
    replies(reading(WIDER)|extra);plan=interpret(ask(snap),snap)
    assert plan.action=='clarify' and why in plan.clarification and not plan.commands

def test_two_spaces_for_one_room_and_an_unchanged_drawing_are_clarifications(snap,replies):
    replies(reading([('BED 1','bed-1',WIDER[0][2]),('BED 1 AGAIN','bed-1',WIDER[1][2])]))
    assert 'both read as Bedroom 01' in interpret(ask(snap),snap).clarification
    replies(reading([('BED 1','bed-1',(0,5.5,4,9)),('STUDY','office',(4,5.5,8,9))]))
    assert 'matches the current layout' in interpret(ask(snap),snap).clarification

def test_exact_exchange_becomes_a_swap(snap,replies):
    replies(reading([('KITCHEN','kitchen',(9,0,12,4)),('BATH','bath',(6,0,9,4))]))
    plan=interpret(ask(snap),snap)
    assert [c.model_dump() for c in plan.commands]==[{'type':'swap_rooms','first':'kitchen','second':'bath'}] and plan.explanation.startswith('Swapped Kitchen and Bathroom')

def test_invalid_reading_gets_one_repair_pass(snap,replies):
    calls=replies('{"outline": [[1,2]',reading(WIDER))
    assert interpret(ask(snap),snap).action=='edit' and len(calls)==2 and calls[1]['payload']['previous_reply_errors']
    calls=replies('nope','still nope')
    with pytest.raises(ValueError):interpret(ask(snap),snap)

def test_locked_rooms_on_the_drawing_never_move(snap):
    r=SketchReading.model_validate(reading([('CORRIDOR','hall',(0,4.3,12,5.9)),*WIDER]))
    placed,notes,refusal=map_sketch(r,snap['model'])
    assert refusal is None and 'hall' not in placed and placed['office']==(4.5,5.5,3.5,3.5)

def test_text_edits_never_go_through_the_reader(snap,replies):
    calls=replies({'revision_id':snap['id'],'action':'inspect','explanation':'x'})
    interpret(AIRequest(revision_id=snap['id'],message='What fails?'),snap)
    assert calls[0]['system'] is None and calls[0]['attachment'] is None

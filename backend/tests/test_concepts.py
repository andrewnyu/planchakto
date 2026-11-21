import copy, json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend import concepts, main
from backend.store import LocalStore


def rect(x,y,w,h): return [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]


def plan():
    # One large open store and an enclosed stockroom, no compulsory corridor.
    return concepts.DesignPlan(title='Open store',rationale='Sales open directly from the forecourt, with rear replenishment.',
        footprint=rect(0,0,100,60),zones=[
            concepts.Zone(id='sales',name='Sales',kind='retail',polygon=rect(0,0,100,45)),
            concepts.Zone(id='stock',name='Stock',kind='storage',polygon=rect(0,45,100,15),enclosed=True)],
        openings=[concepts.Opening(id='entry',from_zone='sales',to_zone='outside',segment=((10,0),(14,0))),
                  concepts.Opening(id='replenish',from_zone='sales',to_zone='stock',segment=((50,45),(54,45)))])


def site(**kw):
    return concepts.SitePlan(boundary=rect(-5,-10,115,80),source='User lot plan',basis='Drawing-derived coordinates; reviewed by the user',**kw)


def test_large_open_store_uses_real_polygons_without_fabricated_engineering():
    r=concepts.evaluate(plan(),site())
    assert r['footprint_area_m2']==6000 and r['zones'][0]['area_m2']==4500
    assert r['status']=='geometry_checked' and r['structural_status']==r['fire_status']=='not_checked'
    assert r['cost_php'] is None and 'Required setbacks' in r['missing']
    assert 'Verified north orientation' in r['missing']


def test_non_rectangular_zones_are_supported():
    p=plan()
    p.zones[0].polygon=[(0,0),(100,0),(100,45),(30,45),(30,40),(0,40)]
    p.zones[1].polygon=[(0,40),(30,40),(30,45),(100,45),(100,60),(0,60)]
    assert concepts.evaluate(p)['footprint_area_m2']==6000


@pytest.mark.parametrize('change,match',[
    (lambda p:p.zones[1].polygon.__setitem__(0,(0,40)),'overlap'),
    (lambda p:setattr(p.zones[1],'polygon',rect(0,46,100,14)),'unallocated'),
    (lambda p:setattr(p.zones[0],'polygon',[(0,0),(100,45),(100,0),(0,45)]),'valid'),
    (lambda p:p.openings.pop(),'entrance path'),
    (lambda p:setattr(p.openings[1],'segment',((50,43),(54,43))),'shared boundary'),
    (lambda p:setattr(p.zones[0],'id','stock'),'Duplicate'),
])
def test_invalid_geometry_and_disconnected_rooms_are_refused(change,match):
    p=plan();change(p)
    with pytest.raises(ValueError,match=match):concepts.evaluate(p,site())


def test_site_containment_setbacks_and_outdoor_conflicts():
    with pytest.raises(ValueError,match='outside the supplied site'):
        concepts.evaluate(plan(),concepts.SitePlan(boundary=rect(0,0,90,60),source='User',basis='User boundary'))
    with pytest.raises(ValueError,match='setback'):concepts.evaluate(plan(),site(setback_m=6))
    p=plan();p.zones.append(concepts.Zone(id='yard',name='Yard',kind='outdoor',location='outside',polygon=rect(90,20,20,10)))
    with pytest.raises(ValueError,match='outdoor zone overlaps'):concepts.evaluate(p,site())
    with pytest.raises(ValidationError):site(road_edge=(0,2))
    with pytest.raises(ValidationError):concepts.SitePlan(boundary=[(0,0),(1,float('nan')),(1,2)],source='User',basis='User')


def test_model_proposals_get_one_repair_with_actual_validation_feedback():
    invalid=plan().model_dump(mode='json');invalid['openings']=invalid['openings'][:1]
    replies=iter([{'reply':'First concept','proposals':[invalid]},{'reply':'Repaired concept','proposals':[plan().model_dump(mode='json')]}])
    payloads=[]
    def llm(payload,system):
        payloads.append(json.loads(payload));assert 'untrusted' in system
        return iter([json.dumps(next(replies))])
    result,metrics=concepts.propose('Design a 6000 m² store',site(),llm=llm)
    assert result.proposals and metrics[0]['footprint_area_m2']==6000
    assert 'entrance path' in payloads[1]['validation_error']
    assert payloads[0]['site']['setback_m'] is None


def test_invalid_proposal_does_not_become_a_result():
    bad=plan().model_dump(mode='json');bad['openings']=[]
    with pytest.raises(ValueError,match='failed validation twice'):
        concepts.propose('Design',llm=lambda *_:iter([json.dumps({'reply':'No doors','proposals':[bad]})]))


def test_preferred_openings_are_placed_on_actual_shared_walls_without_moving_rooms():
    p=plan();before=copy.deepcopy(p.zones)
    p.openings[1].segment=((50,40),(54,40))
    resolved,notes=concepts.resolve_openings(p)
    assert resolved.zones==before and notes
    assert all(y==45 for x,y in resolved.openings[1].segment)
    assert concepts.evaluate(resolved)['footprint_area_m2']==6000
    p.openings[1].placement='exact'
    unchanged,notes=concepts.resolve_openings(p)
    assert not notes
    with pytest.raises(ValueError,match='shared boundary'):concepts.evaluate(unchanged)


def test_site_reading_with_contradictory_area_is_rejected_for_repair():
    s=site(reported_area_m2=20000)
    with pytest.raises(ValidationError,match='Re-read the grid'):concepts.SiteReading(site=s)


def test_native_pdf_recovery_requires_independent_scale_and_area_agreement():
    import io
    from reportlab.pdfgen.canvas import Canvas
    buf=io.BytesIO();canvas=Canvas(buf,pagesize=(500,500))
    # 1:1000: one metre is 72/25.4 PDF points. Independent non-rectangular 17,500 m² lot.
    factor=72/25.4
    points=[(10,10),(160,10),(160,110),(60,160),(10,110)]
    path=canvas.beginPath();path.moveTo(points[0][0]*factor,points[0][1]*factor)
    for x,y in points[1:]:path.lineTo(x*factor,y*factor)
    path.close();canvas.drawPath(path);canvas.showPage();canvas.save()
    from shapely.geometry import Polygon
    area=Polygon(points).area
    sheet=concepts.SiteSheet(sheet_kind='lot_plan',printed_scale=1000,printed_area_m2=area)
    recovered=concepts.vector_site(buf.getvalue(),0,sheet)
    assert recovered and abs(Polygon(recovered.boundary).area-area)<.1
    assert recovered.north_degrees is None and recovered.setback_m is None
    assert concepts.vector_site(buf.getvalue(),0,sheet.model_copy(update={'printed_area_m2':10000})) is None
    assert concepts.vector_site(buf.getvalue(),0,sheet.model_copy(update={'printed_scale':500})) is None


def test_json_site_is_validated_before_the_frontend_uses_it(client):
    assert client.post('/api/concepts/validate-site',json={'site':{}}).status_code==422
    r=client.post('/api/concepts/validate-site',json={'site':site().model_dump(mode='json')})
    assert r.status_code==200 and r.json()['site']['boundary']


def test_model_spatial_program_derives_a_partition_and_shared_walls():
    from backend.concept_program import LayoutProgram,compile_program
    program=LayoutProgram.model_validate({'title':'Open retail core','rationale':'Front arrival and rear stock, without a mandatory hall.',
        'footprint':rect(0,0,100,60),'cuts':[{'region':'building','axis':'y','at':45,'low':'sales','high':'stock'}],
        'spaces':[{'region':'sales','name':'Sales','kind':'retail'},{'region':'stock','name':'Stock','kind':'storage','enclosed':True}],
        'connections':[{'from_zone':'sales','to_zone':'outside','width':4,'preferred_point':[10,0]},
                       {'from_zone':'sales','to_zone':'stock','width':3,'kind':'loading'}]})
    generated=compile_program(program,site());r=concepts.evaluate(generated,site())
    assert r['footprint_area_m2']==6000 and [z['area_m2'] for z in r['zones']]==[4500,1500]
    assert generated.layout_program==program
    assert all(y==45 for x,y in generated.openings[1].segment)
    out,metrics=concepts.propose('Explore a store',site(),llm=lambda *_:iter([json.dumps({'reply':'Proposed','programs':[program.model_dump(mode='json')]})]))
    assert metrics[0]['footprint_area_m2']==6000 and out.proposals[0].layout_program
    invalid=program.model_copy(deep=True);invalid.cuts[0].at=80
    with pytest.raises(ValueError,match='two positive'):compile_program(invalid,site())
    invalid=program.model_copy(deep=True);invalid.connections[1].width=101
    with pytest.raises(ValueError,match='longest shared segment'):compile_program(invalid,site())


def test_program_clipping_is_explicit_and_does_not_invent_area_or_site_inputs():
    from backend.concept_program import LayoutProgram,compile_program
    program=LayoutProgram.model_validate({'title':'Clipped store','rationale':'Use the supplied site boundary.',
        'footprint':rect(-20,-20,160,160),'clip_footprint_to_site':True,'spaces':[{'region':'building','name':'Sales','kind':'retail'}],
        'connections':[{'from_zone':'building','to_zone':'outside','width':2}]})
    from shapely.geometry import Polygon
    generated=compile_program(program,site());r=concepts.evaluate(generated,site())
    assert r['footprint_area_m2']==Polygon(site().boundary).area
    assert 'Required setbacks' in r['missing'] and generated.assumptions


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'_store',LocalStore(str(tmp_path/'concepts.sqlite3')))
    for name in ['BUILDGRAPH_AI_PROVIDER','GEMINI_API_KEY','GOOGLE_CLOUD_PROJECT','OPENROUTER_API_KEY']:
        monkeypatch.delenv(name,raising=False)
    return TestClient(main.app)


def fake_proposal(monkeypatch):
    monkeypatch.setattr(concepts,'propose',lambda message,s,current,history:(concepts.DesignReply(reply='Proposed',proposals=[plan()]),[concepts.evaluate(plan(),s)]))


def test_candidates_accept_discard_undo_redo_are_separate_from_project(client,monkeypatch):
    fake_proposal(monkeypatch)
    head=client.get('/api/project').json()['state']['head']
    s=client.post('/api/concepts/sessions',json={}).json();id=s['id']
    assert client.get('/api/compose/sessions/latest').json()['session'] is None
    s=client.post(f'/api/concepts/sessions/{id}/site',json={'site':site().model_dump(mode='json')}).json()
    s=client.post(f'/api/concepts/sessions/{id}/propose',json={'message':'An open store'}).json()
    first=s['candidates'][0];assert s['accepted_id'] is None
    s=client.post(f'/api/concepts/sessions/{id}/accept',json={'candidate_id':first['id'],'expected_accepted_id':None}).json()
    assert s['accepted_id']==first['id']
    s=client.post(f'/api/concepts/sessions/{id}/propose',json={'message':'Another scheme'}).json()
    second=s['candidates'][1];assert s['accepted_id']==first['id']
    assert first['plan']==s['candidates'][0]['plan']
    assert client.post(f'/api/concepts/sessions/{id}/accept',json={'candidate_id':second['id'],'expected_accepted_id':None}).status_code==409
    s=client.post(f'/api/concepts/sessions/{id}/accept',json={'candidate_id':second['id'],'expected_accepted_id':first['id']}).json()
    assert s['accepted_id']==second['id']
    assert client.post(f'/api/concepts/sessions/{id}/undo',json={}).json()['accepted_id']==first['id']
    assert client.post(f'/api/concepts/sessions/{id}/redo',json={}).json()['accepted_id']==second['id']
    assert client.get('/api/project').json()['state']['head']==head
    assert client.post(f'/api/compose/sessions/{id}/build').status_code==422


def test_discarded_candidate_cannot_be_accepted(client,monkeypatch):
    fake_proposal(monkeypatch)
    s=client.post('/api/concepts/sessions',json={}).json();id=s['id']
    s=client.post(f'/api/concepts/sessions/{id}/propose',json={'message':'Design'}).json();c=s['candidates'][0]
    assert client.post(f'/api/concepts/sessions/{id}/discard',json={'candidate_id':c['id'],'expected_accepted_id':None}).status_code==200
    assert client.post(f'/api/concepts/sessions/{id}/accept',json={'candidate_id':c['id'],'expected_accepted_id':None}).status_code==404


def test_unavailable_model_preserves_session_and_site_read_is_not_accepted(client,monkeypatch):
    s=client.post('/api/concepts/sessions',json={}).json();id=s['id']
    r=client.post(f'/api/concepts/sessions/{id}/propose',json={'message':'Design a store'})
    assert r.status_code==503 and r.json()['mode']=='unavailable'
    assert client.get(f'/api/concepts/sessions/{id}').json()['candidates']==[]
    monkeypatch.setattr(concepts,'read_site',lambda *_:concepts.SiteReading(site=site(),notes=['Approximate, confirm before use']))
    import base64
    r=client.post('/api/concepts/read-site',json={'attachment':{'name':'site.png','mime_type':'image/png','data':base64.b64encode(b'not called').decode()}})
    assert r.status_code==200 and r.json()['site']
    assert client.get(f'/api/concepts/sessions/{id}').json()['site'] is None


def test_stale_long_running_proposal_cannot_overwrite_site_or_accepted_context(client,monkeypatch):
    s=client.post('/api/concepts/sessions',json={}).json();id=s['id']
    def racing(*_):
        changed=main.store().get_compose_session(id);changed['site']=site().model_dump(mode='json')
        main.store().save_compose_session(changed)
        return concepts.DesignReply(reply='Proposed',proposals=[plan()]),[concepts.evaluate(plan())]
    monkeypatch.setattr(concepts,'propose',racing)
    assert client.post(f'/api/concepts/sessions/{id}/propose',json={'message':'Design'}).status_code==409
    s=client.get(f'/api/concepts/sessions/{id}').json()
    assert s['site'] and not s['candidates']

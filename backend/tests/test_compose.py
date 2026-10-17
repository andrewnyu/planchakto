import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
import backend.ai as ai
import backend.main as main
from backend.compose import ProjectSpec, RoomSpec, apply_answer, compose, preview, questions_for, template_spec
from backend.domain import digest
from backend.engine import compute
from backend.store import LocalStore

FULL = [('budget', 10e6), ('height', 3.5), ('fire_occupancy', 'business'), ('rear_exit', True), ('fire_provisions', True), ('solar', '5'),
        ('fault_distance', 'far'), ('soil_profile', 'unknown'), ('frame', 'steel_omrf'), ('friction', 'assumed')]
CLINIC = [RoomSpec(name='Treatment room', kind='office', area=12, count=3), RoomSpec(name='Waiting area', kind='living', area=24),
          RoomSpec(name='Sterilisation room', kind='storage', area=10), RoomSpec(name='Office', kind='office', area=12),
          RoomSpec(name='Toilet', kind='bathroom', area=5, count=2), RoomSpec(name='Pantry', kind='kitchen', area=8)]


def answered(template, rooms=None):
    s = template_spec(template)
    if rooms: s = s.model_copy(update={'rooms': rooms})
    for field, value in FULL:
        if template == 'house' and field in ('fire_occupancy', 'rear_exit', 'fire_provisions'): continue
        if template == 'warehouse' and field == 'fire_occupancy': value = 'none'
        if template == 'warehouse' and field == 'height': value = 6.0
        s = apply_answer(s, field, value)
    return s


@pytest.mark.parametrize('template', ['house', 'commercial', 'warehouse'])
def test_templates_build_complete_models_that_pass(template):
    b, notes = compose(answered(template))
    r = compute(b, 'r')
    assert r['layout']['status'] == 'pass'
    assert not [c['rule_id'] for c in r['checks'] if c['status'] == 'fail']
    assert r['lateral']['status'] == 'pass' and notes


def test_clinic_with_many_small_rooms_keeps_doors_clear():
    b, notes = compose(answered('commercial', CLINIC))
    r = compute(b, 'r')
    assert not [c['rule_id'] for c in r['checks'] if c['status'] == 'fail']
    assert len([x for x in b.rooms if x.kind != 'corridor']) == 9


def test_same_spec_same_building():
    s = answered('commercial')
    assert digest(compose(s)[0]) == digest(compose(s)[0])


def test_unanswered_site_values_stay_missing_and_never_pass():
    s = apply_answer(template_spec('commercial'), 'fire_occupancy', 'business')
    r = compute(compose(s)[0], 'r')
    seismic = [c for c in r['checks'] if c['rule_id'] in ('SEISMIC-V', 'DRIFT', 'FOOT-LATERAL')]
    assert seismic and all(c['status'] == 'missing_input' for c in seismic)
    assert 'Near-source factors Na, Nv' in preview(s)['missing']


def test_questions_follow_the_template_and_answers():
    house = {q['field'] for q in questions_for(template_spec('house'))}
    assert 'fire_occupancy' not in house and 'budget' in house
    s = apply_answer(template_spec('commercial'), 'fire_occupancy', 'business')
    assert {'rear_exit', 'fire_provisions'} <= {q['field'] for q in questions_for(s)}
    s = apply_answer(s, 'fire_occupancy', 'none')
    assert not {'rear_exit', 'fire_provisions'} & {q['field'] for q in questions_for(s)}
    for q in questions_for(template_spec('warehouse')):  # every suggested option is a valid answer
        for o in q['options']: apply_answer(template_spec('warehouse'), q['field'], o['value'])


def test_invalid_answers_and_oversize_programmes_are_rejected():
    with pytest.raises(ValidationError): apply_answer(template_spec('house'), 'height', 9)
    with pytest.raises(ValueError): apply_answer(template_spec('house'), 'storeys', 2)
    big = template_spec('warehouse').model_copy(update={'rooms': [RoomSpec(name='Hall', kind='storage', area=600, count=2)]})
    with pytest.raises(ValueError, match='does not fit'): compose(big)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, '_store', LocalStore(str(tmp_path / 't.sqlite3')))
    for key in ['GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'BUILDGRAPH_AI_PROVIDER', 'GOOGLE_CLOUD_PROJECT']: monkeypatch.delenv(key, raising=False)
    return TestClient(main.app)


def test_turns_and_build_without_ai(client):
    first = client.post('/api/compose/turn', json={'template': 'commercial'}).json()
    assert first['mode'] == 'deterministic' and first['preview']['ok'] and 1 <= len(first['questions']) <= 4
    nxt = client.post('/api/compose/turn', json={'template': 'commercial', 'spec': first['spec'], 'answers': [{'field': 'budget', 'value': 10e6}]}).json()
    assert nxt['spec']['budget'] == 10e6 and nxt['reply'].startswith('Noted. Budget: ₱10M')
    talk = client.post('/api/compose/turn', json={'template': 'commercial', 'spec': nxt['spec'], 'message': 'add a lab'}).json()
    assert talk['mode'] == 'unavailable' and talk['spec'] == nxt['spec']
    assert client.post('/api/compose/turn', json={'template': 'commercial', 'spec': first['spec'], 'answers': [{'field': 'height', 'value': 'tall'}]}).status_code == 422
    head = client.get('/api/project').json()['state']['head']
    built = client.post('/api/compose/build', json={'spec': nxt['spec']}).json()
    assert built['revision']['status'] == 'candidate' and built['revision']['label'].startswith('New project')
    assert client.get('/api/project').json()['state']['head'] == head  # the accepted design is untouched until applied


def test_ai_turn_parses_wrapped_json_and_drops_invalid_options():
    final = {'reply': 'Renamed it.', 'outcome': 'updated', 'questions': [
        {'field': 'height', 'header': 'Height', 'question': 'How tall?', 'options': [{'label': '3 m', 'value': 3}, {'label': '9 m', 'value': 9}, {'label': '4 m', 'value': 4}]},
        {'field': 'storeys', 'header': 'Storeys', 'question': 'How many?', 'options': [{'label': '1', 'value': 1}, {'label': '2', 'value': 2}]}]}
    script = iter([{'calls': [{'tool': 'update_brief', 'args': {'fields': {'name': 'Ngiti Dental'}}}]}, final])
    llm = lambda payload, system: iter(['<invoke>' + json.dumps(next(script)) + '</invoke>'])
    out = ai.compose_turn('commercial', template_spec('commercial'), [], 'call it Ngiti Dental', llm=llm)
    assert out['spec'].name == 'Ngiti Dental' and out['spec'].template == 'commercial'  # the template cannot be switched by the model
    assert [q['field'] for q in out['questions']] == ['height']
    assert [o['value'] for o in out['questions'][0]['options']] == [3, 4]

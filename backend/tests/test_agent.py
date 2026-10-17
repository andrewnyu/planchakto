import json
import pytest
from fastapi.testclient import TestClient
import backend.ai as ai
import backend.main as main
from backend.agent import STEP_LIMIT, ReplyStream, run_compose_agent, scope_limits
from backend.compose import template_spec
from backend.store import LocalStore


class Script:
    """A fake model: returns the scripted steps in order, streamed in small chunks, and records every payload."""
    def __init__(self, *steps):
        self.steps = list(steps); self.payloads = []

    def __call__(self, payload, system):
        self.payloads.append(json.loads(payload))
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        text = step if isinstance(step, str) else json.dumps(step)
        return iter([text[i:i + 7] for i in range(0, len(text), 7)])


def run(llm, message='add a lab', spec=None, history=()):
    events = list(run_compose_agent('commercial', spec or template_spec('commercial'), list(history), message, llm=llm))
    assert events[-1]['type'] == 'result' and all(e['type'] != 'result' for e in events[:-1])
    return events, events[-1]


def streamed(events):
    text = ''
    for e in events:
        if e['type'] == 'reply_delta': text += e['text']
        if e['type'] == 'reply_reset': text = ''
    return text


def test_edit_is_verified_before_the_model_replies():
    llm = Script({'calls': [{'tool': 'set_room', 'args': {'name': 'Lab', 'kind': 'office', 'area': 14}},
                            {'tool': 'update_brief', 'args': {'fields': {'name': 'Ngiti Lab'}}}]},
                 {'reply': 'Added a 14 m² lab.', 'outcome': 'updated'})
    events, out = run(llm)
    assert out['outcome'] == 'updated' and out['spec'].name == 'Ngiti Lab' and any(r.name == 'Lab' and r.area == 14 for r in out['spec'].rooms)
    labels = [e['label'] for e in events if e['type'] == 'step' and e['status'] == 'complete']
    assert 'Added Lab: 14 m²' in labels and 'Regenerated the plan and ran every check' in labels
    verify = next(e for e in events if e['type'] == 'step' and e['id'].startswith('verify') and e['status'] == 'complete')
    assert 'pass' in verify['detail'] and '₱' in verify['detail']
    # The second model call sees the tool results and the re-run checks, so the reply is grounded in them.
    seen = llm.payloads[1]['work_this_turn'][0]
    assert seen['verification']['plan_ok'] and 'estimated_cost_php' in seen['verification'] and seen['verification']['checks']['pass'] > 0
    assert streamed(events) == 'Added a 14 m² lab.' and out['reply'] == 'Added a 14 m² lab.'
    assert out['tools'] == ['inspect_project', 'set_room', 'update_brief', 'validate']


def test_budget_feedback_reaches_the_model():
    spec = template_spec('commercial').model_copy(update={'budget': 1e6})
    llm = Script({'calls': [{'tool': 'set_room', 'args': {'name': 'Showroom', 'area': 80}}]}, {'reply': 'Over budget.'})
    run(llm, 'make the showroom 80 m2', spec)
    v = llm.payloads[1]['work_this_turn'][0]['verification']
    assert v['budget_php'] == 1e6 and v['over_budget_php'] == v['estimated_cost_php'] - 1e6 > 0


def test_a_reply_written_alongside_tool_calls_is_withdrawn():
    llm = Script({'reply': 'Done already!', 'calls': [{'tool': 'run_checks'}]}, {'reply': 'All checks ran.', 'outcome': 'answer'})
    events, out = run(llm, 'run the checks')
    assert any(e['type'] == 'reply_reset' for e in events) and streamed(events) == 'All checks ran.'
    assert out['outcome'] == 'answer' and out['spec'] == template_spec('commercial')


@pytest.mark.parametrize('outcome', ['clarification', 'unsupported'])
def test_clarification_and_unsupported_keep_the_project_unchanged(outcome):
    llm = Script({'calls': [{'tool': 'set_room', 'args': {'name': 'Showroom', 'area': 120}}]}, {'reply': 'Which room?', 'outcome': outcome,
                 'questions': [{'field': 'height', 'header': 'Height', 'question': 'How tall?', 'options': [{'label': '3.5 m', 'value': 3.5}, {'label': '4 m', 'value': 4}]}]})
    _, out = run(llm, 'make it bigger')
    assert out['outcome'] == outcome and out['spec'] == template_spec('commercial')
    assert any(s['id'] == 'revert' for s in out['steps'])
    assert bool(out['questions']) == (outcome == 'clarification')


def test_tool_errors_go_back_to_the_model():
    llm = Script({'calls': [{'tool': 'remove_room', 'args': {'name': 'Garage'}}]}, {'reply': 'There is no garage.'})
    events, out = run(llm, 'remove the garage')
    assert any(e['type'] == 'step' and e['status'] == 'error' for e in events)
    assert 'No room line named' in llm.payloads[1]['work_this_turn'][0]['results'][0]['result']['error']
    assert out['outcome'] == 'answer'


def test_site_values_and_budget_need_the_users_own_words():
    guess = {'calls': [{'tool': 'update_brief', 'args': {'fields': {'budget': 5e6, 'soil_profile': 'SC'}}}]}
    llm = Script(guess, {'reply': 'ok'})
    _, out = run(llm, 'add a lab')
    assert out['spec'].budget is None and out['spec'].soil_profile is None
    assert 'ask with a question' in llm.payloads[1]['work_this_turn'][0]['results'][0]['result']['error']
    _, out = run(Script(guess, {'reply': 'ok'}), 'budget is 5 million pesos and the geotech report says soil SC')
    assert out['spec'].budget == 5e6 and out['spec'].soil_profile == 'SC'


def test_the_loop_is_bounded_and_still_replies():
    llm = Script({'calls': [{'tool': 'run_checks'}]})
    _, out = run(llm, 'keep checking')
    assert len(llm.payloads) == STEP_LIMIT + 1 and 'must_finish' in llm.payloads[-1] and 'must_finish' not in llm.payloads[-2]
    assert out['reply'].startswith('I made no changes.') and out['outcome'] == 'answer'


def test_time_budget_forces_the_reply():
    now = iter([0, 0, 100, 100, 100, 100, 100, 100])
    llm = Script({'calls': [{'tool': 'run_checks'}]}, {'reply': 'Here is what I found.'})
    events = list(run_compose_agent('commercial', template_spec('commercial'), [], 'check', llm=llm, clock=lambda: next(now)))
    assert 'must_finish' in llm.payloads[1] and events[-1]['reply'] == 'Here is what I found.'


def test_invalid_steps_are_retried_once():
    _, out = run(Script('not json at all', {'reply': 'Fine.'}))
    assert out['reply'] == 'Fine.'
    with pytest.raises(ValueError, match='invalid step twice'):
        run(Script('{"calls": [{"tool": "delete_everything"}]}'))


def test_oversized_programme_is_reported_not_built():
    llm = Script({'calls': [{'tool': 'set_room', 'args': {'name': 'Hall', 'kind': 'storage', 'area': 600, 'count': 3}}]}, {'reply': 'Too big.'})
    events, out = run(llm, 'add three 600 m2 halls')
    verify = next(e for e in events if e['type'] == 'step' and e['id'].startswith('verify') and e['status'] != 'active')
    assert verify['status'] == 'error' and 'does not fit' in verify['detail'] and out['plan']['plan_ok'] is False


def test_scope_limits_ignore_negated_mentions():
    assert scope_limits('Make it a two-storey house with bedrooms upstairs') == ['multiple storeys']
    assert scope_limits('Keep it single storey, not two-storey, and add a laundry') == []
    assert scope_limits('no basement please') == []
    assert scope_limits('Add a mezzanine office and make it L-shaped') == ['multiple storeys', 'non-rectangular footprints']


def test_unsupported_note_is_added_when_the_reply_misses_it():
    _, out = run(Script({'reply': 'Added the bedrooms.', 'outcome': 'answer'}), 'make it two-storey')
    assert 'does not support multiple storeys' in out['reply']


def test_reply_stream_decodes_escapes_split_across_chunks():
    rs = ReplyStream(); text = ''.join(rs.feed(c) for c in ['{"re', 'ply": "A \\', '"big\\" room\\n', '\\u20b1', '5M", "outcome": "x"}'])
    assert text == 'A "big" room\n₱5M' and rs.done


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, '_store', LocalStore(str(tmp_path / 't.sqlite3')))
    for key in ['GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'BUILDGRAPH_AI_PROVIDER', 'GOOGLE_CLOUD_PROJECT']: monkeypatch.delenv(key, raising=False)
    return TestClient(main.app)


def stream(client, id, body):
    r = client.post(f'/api/compose/sessions/{id}/turn/stream', json=body)
    assert r.status_code == 200
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def test_session_stream_persists_real_steps_and_the_chat_follows_the_build(client, monkeypatch):
    monkeypatch.setattr(ai, 'stream_completion', Script({'calls': [{'tool': 'set_room', 'args': {'name': 'Lab', 'kind': 'office', 'area': 14}}]},
                                                        {'reply': 'Added the lab.', 'outcome': 'updated'}))
    session = client.post('/api/compose/sessions', json={'template': 'commercial'}).json()
    events = stream(client, session['id'], {'message': 'add a lab', 'shown': 'add a lab'})
    assert [e['type'] for e in events][-1] == 'final' and streamed(events) == 'Added the lab.'
    final = events[-1]['session']
    assert final['messages'][-1]['text'] == 'Added the lab.' and any(s['id'].startswith('verify') for s in final['messages'][-1]['steps'])
    assert any(r['name'] == 'Lab' for r in final['spec']['rooms']) and final['can_undo']
    # Reloading restores the session with its steps.
    assert client.get('/api/compose/sessions/latest').json()['session']['messages'][-1]['steps'] == final['messages'][-1]['steps']
    # Answers alone run a real verification step and need no model.
    events = stream(client, session['id'], {'answers': [{'field': 'budget', 'value': 10e6}]})
    assert any(e['type'] == 'step' and e['id'] == 'verify' and e['status'] == 'complete' for e in events)
    assert events[-1]['session']['spec']['budget'] == 10e6
    # An active design session cannot be used by the project assistant until it is built.
    head = client.get('/api/project').json()['state']['head']
    assert client.post('/api/ai', json={'revision_id': head, 'message': 'hi', 'thread_id': session['id']}).status_code == 409
    built = client.post(f'/api/compose/sessions/{session["id"]}/build').json()
    assert built['thread_id'] == session['id']
    thread = client.get('/api/assistant/thread').json()['thread']
    assert thread['id'] == session['id'] and thread['messages'][-1]['outcome'] == 'built' and 'add a lab' in [m['text'] for m in thread['messages']]
    seen = {}
    def interpret(req, snapshot, history=None):
        seen['history'] = history
        return ai.AIPlan(revision_id=req.revision_id, action='inspect', explanation='The lab is 14 m².')
    monkeypatch.setattr(main, 'interpret', interpret)
    rev = built['revision']['id']
    r = client.post('/api/ai', json={'revision_id': rev, 'message': 'how big is the lab?', 'thread_id': thread['id']}).json()
    assert {'role': 'user', 'text': 'add a lab'} in seen['history']  # the in-project assistant remembers the design conversation
    assert [m['text'] for m in r['thread']['messages'][-2:]] == ['how big is the lab?', 'The lab is 14 m².']
    # Without a thread the first request starts one, and a new conversation starts empty.
    r = client.post('/api/ai', json={'revision_id': rev, 'message': 'hello'}).json()
    assert r['thread']['id'] != thread['id'] and len(r['thread']['messages']) == 2
    fresh = client.post('/api/assistant/thread').json()['thread']
    assert fresh['messages'] == [] and client.get('/api/assistant/thread').json()['thread']['id'] == fresh['id']


def test_stream_without_ai_reports_unavailable_and_keeps_answers(client):
    session = client.post('/api/compose/sessions', json={'template': 'house'}).json()
    events = stream(client, session['id'], {'message': 'add a lab', 'answers': [{'field': 'height', 'value': 3.0}]})
    final = events[-1]['session']
    assert final['mode'] == 'unavailable' and final['spec']['height'] == 3.0 and 'No AI provider' in final['messages'][-1]['text']


def test_rule_lookup_and_the_turn_start_spec_reach_the_model():
    llm = Script({'calls': [{'tool': 'explain_rule', 'args': {'query': 'FIRE-EXT'}}, {'tool': 'explain_rule', 'args': {'query': 'deflection'}}]}, {'reply': 'ok'})
    events, out = run(llm, 'why is there an extinguisher check?')
    results = [r['result'] for r in llm.payloads[1]['work_this_turn'][0]['results']]
    assert results[0]['rules'][0]['id'] == 'FIRE-EXT' and results[1]['rules'][0]['id'] == 'SLS'
    assert llm.payloads[0]['spec_at_turn_start'] == llm.payloads[0]['current_spec']

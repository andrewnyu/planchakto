import json
from collections import Counter
from backend.evals.cases import CASES
from backend.evals.runner import run_case


def scripted(*steps):
    steps = list(steps)
    def llm(payload, system):
        step = steps.pop(0) if len(steps) > 1 else steps[0]
        return iter([json.dumps(step)])
    return llm


def case(id): return next(c for c in CASES if c.id == id)


def test_the_case_set_covers_the_release_scope():
    assert 25 <= len(CASES) <= 40 and len({c.id for c in CASES}) == len(CASES)
    assert set(Counter(c.template for c in CASES)) == {'house', 'commercial', 'warehouse'}
    cats = Counter(c.category for c in CASES)
    assert all(cats[k] >= 2 for k in ('basic', 'correction', 'ambiguous', 'unsupported', 'conflict', 'question', 'grounding'))
    assert sum(len(c.turns) > 1 for c in CASES) >= 5 and all(c.expect for c in CASES)


def test_a_correct_conversation_passes():
    llm = scripted({'calls': [{'tool': 'set_room', 'args': {'name': 'Server room', 'kind': 'office', 'area': 20}}]}, {'reply': 'Added it.'},
                   {'calls': [{'tool': 'set_room', 'args': {'name': 'Server room', 'area': 15}}]}, {'reply': 'Now 15 m².'})
    r = run_case(case('server-room-correction'), llm)
    assert r['passed'] and [t['outcome'] for t in r['turns']] == ['updated', 'updated']


def test_the_gate_catches_bad_behaviour():
    # The model declines correctly but the expectation of a clarification is missed: a quality miss, not an invariant failure.
    r = run_case(case('ambiguous-that-room'), scripted({'reply': 'Done!', 'outcome': 'answer'}))
    assert not r['passed'] and not r['problems'] and [e['ok'] for e in r['expect']] == [False, True]
    # A programme that no longer fits is an invariant failure.
    r = run_case(case('hall-oversize'), scripted({'calls': [{'tool': 'set_room', 'args': {'name': 'Storage hall', 'area': 600, 'count': 2}}]}, {'reply': 'Done.'}))
    assert any('unbuildable' in p for p in r['problems'])
    # A crash on a turn is reported, not raised.
    r = run_case(case('basement'), scripted('not json'))
    assert r['problems'] and 'failed' in r['problems'][0] and not r['expect']

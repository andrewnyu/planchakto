import pytest
from fastapi.testclient import TestClient
from backend import quickcheck as q
from backend.store import LocalStore
import backend.main as main

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'_store',LocalStore(str(tmp_path/'test.sqlite3')))
    for v in ['GEMINI_API_KEY','OPENROUTER_API_KEY','BUILDGRAPH_AI_PROVIDER','GOOGLE_CLOUD_PROJECT']:monkeypatch.delenv(v,raising=False)
    return TestClient(main.app)

@pytest.mark.parametrize('discipline',('plumbing','electrical'))
def test_recorded_service_sample_runs_in_its_own_scope(client,discipline):
    record=client.post('/api/quick-checks/sample',json={'discipline':discipline}).json()
    assert record['discipline']==discipline and record['mode']=='recorded' and record['status']=='confirm'
    done=client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs'])
    assert done.status_code==200,done.text
    result=done.json()['results'];assert result['scope']==discipline and result['routing']['routes']
    allowed={'ROUTE','DRAIN','PH-CODE'} if discipline=='plumbing' else {'ROUTE','ELECTRICAL','PH-CODE'}
    assert {c['rule_id'] for c in result['checks']}<=allowed
    assert any(x['item'].startswith('Structural clashes') for x in result['coverage']['not_checked'])
    assert all('structural clashes and penetrations are not checked' in r['reason'] for r in result['routing']['routes'] if r['status']=='pass')

def test_plumbing_requires_connections_and_fall(client):
    record=client.post('/api/quick-checks/sample',json={'discipline':'plumbing'}).json();inputs=record['inputs']
    for patch in ({'water':None},{'drain':None},{'drain_fall_m':None},{'drain_slope':None}):
        assert client.post(f'/api/quick-checks/{record["id"]}/run',json=inputs|patch).status_code==422

def test_electrical_keeps_an_unprinted_load_missing(client):
    record=client.post('/api/quick-checks/sample',json={'discipline':'electrical'}).json()
    done=client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']).json()
    circuits={c['id']:c for c in done['results']['routing']['circuits']}
    assert circuits['C1']['status']=='pass' and circuits['C2']['status']=='missing_input'
    assert circuits['C2']['connected_W'] is None

def test_service_inputs_cannot_change_the_record_discipline(client):
    record=client.post('/api/quick-checks/sample',json={'discipline':'plumbing'}).json()
    assert client.post(f'/api/quick-checks/{record["id"]}/run',json=record['inputs']|{'discipline':'electrical'}).status_code==422

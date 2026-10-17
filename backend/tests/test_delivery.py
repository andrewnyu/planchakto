from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
import backend.main as main
from backend.store import LocalStore

def test_api_json_is_gzipped(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'_store',LocalStore(str(tmp_path/'t.sqlite3')))
    r=TestClient(main.app).get('/api/project',headers={'Accept-Encoding':'gzip'})
    assert r.status_code==200 and r.headers['content-encoding']=='gzip' and r.json()['state']['head']

def test_agent_stream_is_not_compressed():
    app=FastAPI();app.user_middleware=main.app.user_middleware
    app.get('/s')(lambda:StreamingResponse(iter([b'{"type":"x"}\n'*200]),media_type='application/x-ndjson'))
    app.get('/j')(lambda:{'x':'y'*5000})  # control: same middleware does compress JSON
    c=TestClient(app)
    assert 'content-encoding' not in c.get('/s',headers={'Accept-Encoding':'gzip'}).headers
    assert c.get('/j',headers={'Accept-Encoding':'gzip'}).headers['content-encoding']=='gzip'

def test_hashed_assets_cache_for_a_year_and_index_revalidates(tmp_path):
    (tmp_path/'assets').mkdir();(tmp_path/'assets'/'index-abc123.js').write_text('x');(tmp_path/'index.html').write_text('<html></html>')
    app=FastAPI();app.mount('/',main.Frontend(directory=tmp_path,html=True));c=TestClient(app)
    assert c.get('/assets/index-abc123.js').headers['cache-control']=='public, max-age=31536000, immutable'
    assert c.get('/').headers['cache-control']=='no-cache'

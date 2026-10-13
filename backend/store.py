"""Immutable revision snapshots, optimistic acceptance and persistent undo/redo.
SQLite is local only. Firestore adapter stores metadata and GCS stores snapshots.
"""
from __future__ import annotations
import json,os,sqlite3,uuid,time
from pathlib import Path
from contextlib import contextmanager
from .domain import Building,CommandRequest,apply_commands,digest
from .engine import compute,validate_result,ENGINE_VERSION
from .example import example

class Conflict(ValueError):pass
class LocalStore:
    def __init__(self,path=None):
        self.path=path or os.getenv('BUILDGRAPH_DB','.data/buildgraph.sqlite3');Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, revision TEXT NOT NULL)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except:db.rollback();raise
        finally:db.close()
    def state(self):
        with self.db() as db:r=db.execute('SELECT data FROM state WHERE id=1').fetchone()
        if not r:return self.reset()
        return json.loads(r['data'])
    def get(self,id):
        with self.db() as db:r=db.execute('SELECT data FROM snapshots WHERE id=?',(id,)).fetchone()
        if r is None:raise KeyError('Revision not found')
        return json.loads(r['data'])
    def list(self):
        with self.db() as db:rows=db.execute('SELECT data FROM snapshots ORDER BY rowid DESC LIMIT 100').fetchall()
        return [{k:v for k,v in json.loads(r['data']).items() if k not in ['model','results']} for r in rows]
    def make_snapshot(self,model,parent,label,commands,invalidated,fork_head,status='candidate'):
        id='rev-'+uuid.uuid4().hex[:10];results=compute(model,id)
        return {'id':id,'parent_id':parent,'fork_head':fork_head,'created_at':time.time(),'label':label,'status':status,'model':model.model_dump(mode='json'),'results':results,'commands':commands,'invalidated':invalidated,'input_hash':digest(model),'result_hash':results['result_hash']}
    def reset(self):
        s=self.make_snapshot(example(),None,'Original concept',[],[],None,'accepted');state={'head':s['id'],'history':[s['id']],'cursor':0}
        with self.db() as db:
            db.execute('INSERT INTO snapshots VALUES (?,?)',(s['id'],json.dumps(s)))
            db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(json.dumps(state),))
        return state
    def preview(self,req:CommandRequest):
        fingerprint=digest(req)
        with self.db() as db:previous=db.execute('SELECT * FROM commands WHERE id=?',(req.command_id,)).fetchone()
        if previous:
            if previous['fingerprint']!=fingerprint:raise Conflict('Command ID already used with different content')
            return self.get(previous['revision'])
        base=self.get(req.base_revision)
        if base['status']=='discarded':raise Conflict('Cannot edit a discarded revision')
        model,invalidated=apply_commands(Building.model_validate(base['model']),req.commands)
        fork=base['fork_head'] if base['status']=='candidate' else base['id']
        s=self.make_snapshot(model,base['id'],req.label,[c.model_dump() for c in req.commands],invalidated,fork)
        with self.db() as db:
            # Transaction protects concurrent retries of the same idempotency key.
            existing=db.execute('SELECT * FROM commands WHERE id=?',(req.command_id,)).fetchone()
            if existing:
                if existing['fingerprint']!=fingerprint:raise Conflict('Command ID conflict')
                return json.loads(db.execute('SELECT data FROM snapshots WHERE id=?',(existing['revision'],)).fetchone()['data'])
            db.execute('INSERT INTO snapshots VALUES (?,?)',(s['id'],json.dumps(s)));db.execute('INSERT INTO commands VALUES (?,?,?)',(req.command_id,fingerprint,s['id']))
        return s
    def accept(self,id,expected_head):
        with self.db() as db:
            state=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()['data'])
            if state['head']!=expected_head:raise Conflict('Accepted revision changed; reload and compare against the latest design')
            row=db.execute('SELECT data FROM snapshots WHERE id=?',(id,)).fetchone()
            if row is None:raise KeyError('Revision not found')
            s=json.loads(row['data'])
            if s['status']!='candidate':raise Conflict('Only an active candidate can be applied')
            if s['fork_head']!=expected_head:raise Conflict('Candidate branches from a different accepted revision; regenerate from the current head')
            validate_result(Building.model_validate(s['model']),s['results'],id)
            if s['results']['layout']['status']=='fail':raise Conflict('Resolve hard layout constraints before applying this candidate')
            if s['results']['structure']['errors']:raise Conflict('Unsupported structural topology; preserve or restore end supports')
            s['status']='accepted';state['history']=state['history'][:state['cursor']+1]+[id];state['cursor']+=1;state['head']=id
            db.execute('UPDATE snapshots SET data=? WHERE id=?',(json.dumps(s),id));db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(state),))
        return s
    def discard(self,id):
        with self.db() as db:
            r=db.execute('SELECT data FROM snapshots WHERE id=?',(id,)).fetchone()
            if not r:raise KeyError('Revision not found')
            s=json.loads(r['data'])
            if s['status']!='candidate':raise Conflict('Only candidates can be discarded')
            s['status']='discarded';db.execute('UPDATE snapshots SET data=? WHERE id=?',(json.dumps(s),id))
        return s
    def travel(self,direction,expected_head):
        with self.db() as db:
            state=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()['data'])
            if state['head']!=expected_head:raise Conflict('Accepted revision changed; reload first')
            i=state['cursor']+direction
            if i<0 or i>=len(state['history']):raise Conflict('No revision in that direction')
            state['cursor']=i;state['head']=state['history'][i];db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(state),))
        return self.get(state['head'])
    def import_model(self,model):
        state=self.state();s=self.make_snapshot(model,state['head'],'Imported native project',[{'type':'import_native_project'}],['all'],state['head'])
        with self.db() as db:db.execute('INSERT INTO snapshots VALUES (?,?)',(s['id'],json.dumps(s)))
        return s
    def rerun(self,id):
        # Inputs remain immutable. A new candidate records the current solver output.
        base=self.get(id);state=self.state()
        s=self.make_snapshot(Building.model_validate(base['model']),id,'Recomputed analysis',[],['all'],base['fork_head'] if base['status']=='candidate' else id)
        with self.db() as db:db.execute('INSERT INTO snapshots VALUES (?,?)',(s['id'],json.dumps(s)))
        return s

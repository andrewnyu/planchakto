"""Cloud adapter: transactional Firestore revision index + GCS snapshots.
One isolated deployment/workspace. Cloud Run IAM is the access boundary.
No project data is ever sent here unless BUILDGRAPH_STORAGE=google.
"""
import os,json,uuid
from google.cloud import firestore,storage
from .store import LocalStore,Conflict
from .domain import digest,Building,apply_commands
from .engine import validate_result
from .example import example

class GoogleStore(LocalStore):
    def __init__(self):
        project=os.environ['GOOGLE_CLOUD_PROJECT'];bucket=os.environ['BUILDGRAPH_BUCKET']
        self.fs=firestore.Client(project=project);self.bucket=storage.Client(project=project).bucket(bucket)
        self.workspace=os.environ.get('BUILDGRAPH_WORKSPACE','demo');self.root=self.fs.collection('buildgraph').document(self.workspace)
    def _write(self,s):
        self.bucket.blob(f'{self.workspace}/{s["id"]}.json').upload_from_string(json.dumps(s),content_type='application/json')
        self.root.collection('revisions').document(s['id']).set({k:v for k,v in s.items() if k not in ['model','results']})
    def get(self,id):
        if not id.startswith('rev-') or '/' in id:raise KeyError('Invalid revision')
        meta=self.root.collection('revisions').document(id).get()
        if not meta.exists:raise KeyError('Revision not found')
        s=json.loads(self.bucket.blob(f'{self.workspace}/{id}.json').download_as_text());s.update(meta.to_dict());return s
    def state(self):
        doc=self.root.get();return doc.to_dict() if doc.exists else self.reset()
    def list(self):return [d.to_dict() for d in self.root.collection('revisions').order_by('created_at',direction=firestore.Query.DESCENDING).limit(100).stream()]
    def reset(self):
        s=self.make_snapshot(example(),None,'Original concept',[],[],None,'accepted');self._write(s);state={'head':s['id'],'history':[s['id']],'cursor':0};self.root.set(state);return state
    def preview(self,req):
        fingerprint=digest(req);ref=self.root.collection('commands').document(digest(req.command_id));previous=ref.get()
        if previous.exists:
            if previous.to_dict()['fingerprint']!=fingerprint:raise Conflict('Command ID already used with different content')
            return self.get(previous.to_dict()['revision'])
        base=self.get(req.base_revision)
        if base['status']=='discarded':raise Conflict('Cannot edit discarded revision')
        model,invalidated=apply_commands(Building.model_validate(base['model']),req.commands);fork=base['fork_head'] if base['status']=='candidate' else base['id']
        s=self.make_snapshot(model,base['id'],req.label,[c.model_dump() for c in req.commands],invalidated,fork);self._write(s)
        @firestore.transactional
        def register(tx):
            old=ref.get(transaction=tx)
            if old.exists:
                if old.to_dict()['fingerprint']!=fingerprint:raise Conflict('Command ID conflict')
                return old.to_dict()['revision']
            tx.set(ref,{'fingerprint':fingerprint,'revision':s['id']});return s['id']
        return self.get(register(self.fs.transaction()))
    def accept(self,id,expected_head):
        s=self.get(id);validate_result(Building.model_validate(s['model']),s['results'],id)
        if s['results']['layout']['status']=='fail' or s['results']['structure']['errors']:raise Conflict('Resolve hard constraints or unsupported structural topology before applying')
        @firestore.transactional
        def accept_tx(tx):
            state=self.root.get(transaction=tx).to_dict();ref=self.root.collection('revisions').document(id);meta=ref.get(transaction=tx).to_dict()
            if state['head']!=expected_head or meta['fork_head']!=expected_head:raise Conflict('Stale candidate; reload current head')
            if meta['status']!='candidate':raise Conflict('Only active candidates can be applied')
            state['history']=state['history'][:state['cursor']+1]+[id];state['cursor']+=1;state['head']=id
            tx.update(ref,{'status':'accepted'});tx.set(self.root,state)
        accept_tx(self.fs.transaction());return self.get(id)
    def discard(self,id):
        ref=self.root.collection('revisions').document(id)
        @firestore.transactional
        def discard_tx(tx):
            d=ref.get(transaction=tx)
            if not d.exists:raise KeyError('Revision not found')
            if d.to_dict()['status']!='candidate':raise Conflict('Only candidates can be discarded')
            tx.update(ref,{'status':'discarded'})
        discard_tx(self.fs.transaction());return self.get(id)
    def travel(self,direction,expected_head):
        @firestore.transactional
        def travel_tx(tx):
            state=self.root.get(transaction=tx).to_dict();i=state['cursor']+direction
            if state['head']!=expected_head:raise Conflict('Accepted revision changed')
            if not 0<=i<len(state['history']):raise Conflict('No revision in that direction')
            state.update(cursor=i,head=state['history'][i]);tx.set(self.root,state);return state['head']
        return self.get(travel_tx(self.fs.transaction()))
    def import_model(self,model):
        state=self.state();s=self.make_snapshot(model,state['head'],'Imported native project',[{'type':'import_native_project'}],['all'],state['head']);self._write(s);return s
    def rerun(self,id):
        base=self.get(id);s=self.make_snapshot(Building.model_validate(base['model']),id,'Recomputed analysis',[],['all'],base['fork_head'] if base['status']=='candidate' else id);self._write(s);return s

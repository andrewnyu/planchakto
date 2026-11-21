"""HTTP boundary for staged planning. No model response mutates accepted state."""
from typing import Literal
from fastapi import APIRouter
from fastapi.responses import JSONResponse,Response
from pydantic import Field
from .domain import Model
from .ai import Attachment
from . import planning_workflow as w,planning_outputs as outputs

class Create(Model):
    template:str=Field(default='house',max_length=100)
    brief:str=Field(default='',max_length=12000)
class Edit(Model):
    expected_version:int=Field(ge=1)
    stage:Literal['programme','strategy','layout','details','inputs']
    message:str=Field(default='',max_length=12000)
    value:dict|None=None
    attachment:Attachment|None=None
class Mutation(Model):
    expected_version:int=Field(ge=1)
    candidate_id:str|None=None
    acknowledged:bool=False
    direction:Literal[-1,1]= -1
    site:dict|None=None
class Import(Model):
    project:dict
class AgentRequest(Model):
    expected_version:int=Field(ge=1)
    message:str=Field(default='',max_length=4000)


def router(store):
    r=APIRouter(prefix='/api/planning')
    @r.post('/sessions')
    def create(req:Create):return w.create(store(),req.template,req.brief)
    @r.get('/sessions/latest')
    def latest():
        s=store().latest_compose_session(('planning_active',));return {'session':w.view(store(),s) if s else None}
    @r.get('/sessions')
    def list_sessions():
        summaries=[]
        for s in store().list_compose_sessions():
            p=w.current(store(),s,'programme')
            summaries.append({'id':s['id'],'name':p['name'] if p else 'Untitled planning draft','updated_at':s['updated_at']})
        return {'sessions':summaries}
    @r.post('/import')
    def restore(req:Import):
        import json
        if len(json.dumps(req.project).encode())>8_000_000:raise ValueError('Choose a planning export smaller than 8 MB')
        return w.import_project(store(),req.project)
    @r.get('/sessions/{id}')
    def get(id:str):return w.view(store(),w.load(store(),id))
    @r.post('/sessions/{id}/propose')
    def propose(id:str,req:Edit):
        if req.attachment:
            req.attachment.raw()
            if req.stage!='programme':raise ValueError('Use reference drawings to develop the programme; use Add lot plan for site geometry.')
        try:return w.propose(store(),id,req.expected_version,req.stage,req.message,req.value,attachment=req.attachment)
        except RuntimeError as e:return JSONResponse(status_code=503,content={'detail':str(e),'mode':'unavailable'})
        except (ValueError,KeyError):raise
        except Exception:return JSONResponse(status_code=502,content={'detail':'The AI request failed. The confirmed design is unchanged; retry this stage.','mode':'error'})
    @r.post('/sessions/{id}/use-import')
    def use_import(id:str,req:Edit):return w.use_import(store(),id,req.expected_version,req.stage)
    @r.post('/sessions/{id}/accept')
    def accept(id:str,req:Mutation):return w.accept(store(),id,req.expected_version,req.candidate_id)
    @r.post('/sessions/{id}/discard')
    def discard(id:str,req:Mutation):
        s=w.load(store(),id,req.expected_version);c=next((c for c in s['candidates'] if c['id']==req.candidate_id),None)
        if not c:raise KeyError('Planning candidate not found')
        if s['refs'].get(c['stage'])==c['artifact']:raise ValueError('This is the confirmed stage. Choose a different candidate before discarding it.')
        c['discarded']=True;return w.save(store(),s,req.expected_version)
    @r.post('/sessions/{id}/site')
    def site(id:str,req:Mutation):return w.set_site(store(),id,req.expected_version,req.site)
    @r.get('/sessions/{id}/approval-review')
    def review(id:str):return w.approval_review(store(),w.load(store(),id))
    @r.post('/sessions/{id}/approve')
    def approve(id:str,req:Mutation):return w.approve(store(),id,req.expected_version,req.acknowledged)
    @r.post('/sessions/{id}/checks')
    def checks(id:str,req:Mutation):return w.checks(store(),id,req.expected_version)
    @r.post('/sessions/{id}/agents/{role}')
    def specialist(id:str,role:str,req:AgentRequest):
        try:return w.specialist_review(store(),id,req.expected_version,role,req.message)
        except RuntimeError as e:return JSONResponse(status_code=503,content={'detail':str(e),'mode':'unavailable'})
        except (ValueError,KeyError):raise
        except Exception:return JSONResponse(status_code=502,content={'detail':'The specialist request failed. Deterministic findings and the accepted design are unchanged. Retry the review.','mode':'error'})
    @r.post('/sessions/{id}/travel')
    def travel(id:str,req:Mutation):return w.travel(store(),id,req.expected_version,req.direction)
    @r.get('/sessions/{id}/export/{format}')
    def export(id:str,format:Literal['pdf','dxf','csv','json','zip'],version:int):
        s=w.load(store(),id,version);v=outputs.bundle(store(),s)
        formats={'pdf':(outputs.render_pdf,'application/pdf'),'dxf':(outputs.render_dxf,'image/vnd.dxf'),'csv':(outputs.render_csv,'text/csv'),'zip':(outputs.render_zip,'application/zip'),'json':(lambda v:__import__('json').dumps({'schema_version':'planning-1','accepted':v['accepted'],'site':v['site'],'analysis':v['analysis'],'artifact_refs':v['refs'],'agent_reviews':v.get('agent_reviews',{})},indent=2).encode(),'application/json')}
        render,mime=formats[format];return Response(render(v),media_type=mime,headers={'Content-Disposition':f'attachment; filename=buildgraph-review.{format}'})
    return r

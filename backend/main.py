from __future__ import annotations
import os,io,csv,json,uuid,html,logging,time
from pathlib import Path
from fastapi import FastAPI,Request,Body
from fastapi.responses import JSONResponse,Response,HTMLResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware,DEFAULT_EXCLUDED_CONTENT_TYPES
from pydantic import ValidationError,Field
from .domain import Building,CommandRequest,FireProtection,Model,digest
from .store import LocalStore,Conflict
from .engine import ENGINE_VERSION,validate_result,compute
from .drawings import PermitRequest,render_pdf,render_dxf
from .quantities import compare
from .rules import RULES
from .structure import CATALOG
from .geometry import parse_survey,validate_site
from .layout import generate_layouts
from .ai import AIRequest,Attachment,interpret,status
from . import quickcheck
from .example import example
from .compose import ProjectSpec,TEMPLATES,Template,template_spec,apply_answer,questions_for,compose,preview
from .ai import compose_turn
from .agent import run_compose_agent,assess,plan_summary
from typing import Literal,Any

app=FastAPI(title='BuildGraph',version='0.1.0')
# JSON, JS and CSS shrink ~70-85% gzipped. The design agent's ndjson stream stays uncompressed so its events arrive as sent.
app.add_middleware(GZipMiddleware,minimum_size=1000,exclude_content_types=DEFAULT_EXCLUDED_CONTENT_TYPES+('application/x-ndjson',))
logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s: %(message)s')
log=logging.getLogger('buildgraph')
_store=None
def store():
    global _store
    if _store is None:
        if os.getenv('BUILDGRAPH_STORAGE')=='google':
            from .cloud_store import GoogleStore
            _store=GoogleStore()
        else:_store=LocalStore()
    return _store

@app.exception_handler(Conflict)
async def conflict(request,exc):return JSONResponse(status_code=409,content={'detail':str(exc)})
@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse(status_code=422,content={'detail':str(exc)})
@app.exception_handler(KeyError)
async def missing(request,exc):return JSONResponse(status_code=404,content={'detail':str(exc)})

class HeadRequest(Model):expected_head:str
class SurveyRequest(Model):
    base_revision:str
    csv_text:str=Field(max_length=2000000)
    units:str='m'
class ImportRequest(Model):model:Building

@app.get('/api/health')
def health():return {'status':'ok','engine_version':ENGINE_VERSION,**status(),'storage':os.getenv('BUILDGRAPH_STORAGE','local'),'scope':'single-storey orthogonal prototype'}
@app.get('/api/examples/plumbing')
def plumbing_example():
    model=example()
    model.routing_mode='direct'
    return {'model':model,'label':'Plumbing demo · direct routes'}
@app.get('/api/examples/fire')
def fire_example():
    # A supported business occupancy with no provisions yet, so the screen opens with real findings.
    model=example()
    model.brief.use='Small professional office'
    model.fire=FireProtection(enabled=True,occupancy='business')
    return {'model':model,'label':'Fire demo · office, no provisions'}
@app.get('/api/project')
def project():
    state=store().state();s=revision(state['head'])
    return {'state':state,'accepted':s,'revisions':store().list(),**status(),'sections':CATALOG}
@app.get('/api/revisions/{id}')
def revision(id:str):
    s=store().get(id)
    s['results']['stale']=s['results']['input_hash']!=digest(s['model']) or s['results'].get('engine_version')!=ENGINE_VERSION
    return s
@app.post('/api/commands')
def commands(req:CommandRequest):return store().preview(req)
@app.post('/api/revisions/{id}/apply')
def apply(id:str,req:HeadRequest):return store().accept(id,req.expected_head)
@app.post('/api/revisions/{id}/discard')
def discard(id:str):return store().discard(id)
@app.post('/api/undo')
def undo(req:HeadRequest):return store().travel(-1,req.expected_head)
@app.post('/api/redo')
def redo(req:HeadRequest):return store().travel(1,req.expected_head)
@app.post('/api/reset')
def reset():return store().get(store().reset()['head'])
@app.post('/api/revisions/{id}/analyze')
def analyze(id:str):return store().rerun(id)
@app.get('/api/compare')
def comparison(before:str,after:str):
    a=store().get(before);b=store().get(after)
    return compare(a['results'],b['results'],a['model'],b['model'])
@app.get('/api/rules')
def rules():return RULES
@app.post('/api/revisions/{id}/layouts')
def layouts(id:str):
    s=store().get(id);generated=generate_layouts(Building.model_validate(s['model']));entries=[]
    for c in generated['candidates']:
        revision=store().preview(CommandRequest(base_revision=id,command_id=uuid.uuid4().hex,label=c['label'],commands=c['commands']))
        entries.append({**c,'revision':revision})
    return {**generated,'candidates':entries}
class ComposeAnswer(Model):
    field:str
    value:Any=None
class ComposeMessage(Model):
    role:Literal['user','assistant']
    text:str=Field(max_length=2000)
class ComposeRequest(Model):
    template:Template
    spec:ProjectSpec|None=None
    message:str|None=Field(default=None,max_length=4000)
    answers:list[ComposeAnswer]=Field(default_factory=list,max_length=20)
    history:list[ComposeMessage]=Field(default_factory=list,max_length=40)
class BuildRequest(Model):spec:ProjectSpec
class ComposeSessionCreate(Model):template:Template
class ComposeSessionTurn(Model):
    message:str|None=Field(default=None,max_length=4000)
    shown:str|None=Field(default=None,max_length=4000)
    answers:list[ComposeAnswer]=Field(default_factory=list,max_length=20)

def _session_view(session):
    spec=ProjectSpec.model_validate(session['spec']);pending=questions_for(spec)
    questions=session.get('questions') or pending[:4]
    return {**session,'spec':spec.model_dump(mode='json'),'questions':questions,'remaining':len(pending),'preview':preview(spec),**status(),
            'can_undo':any(t.get('status')=='applied' and t.get('before_spec')!=t.get('after_spec') for t in session.get('turns',[])),
            'has_changes':spec.model_dump(mode='json')!=session['baseline_spec']}

def _new_compose_session(template):
    spec=template_spec(template);now=time.time()
    session={'id':'compose-'+uuid.uuid4().hex[:12],'template':template,'spec':spec.model_dump(mode='json'),'baseline_spec':spec.model_dump(mode='json'),
             'messages':[],'turns':[],'questions':questions_for(spec)[:4],'mode':'deterministic','status':'active','created_at':now,'updated_at':now}
    return store().save_compose_session(session)

def _said(spec,answers):
    """Apply suggested answers deterministically; returns the new spec and how each answer reads in the conversation."""
    said=[]
    for a in answers:
        bank={q['field']:q for q in questions_for(spec)}
        spec=apply_answer(spec,a.field,a.value)
        label=next((o['label'] for o in bank.get(a.field,{}).get('options',[]) if o['value']==a.value),None)
        said.append(f"{bank[a.field]['header'] if a.field in bank else a.field.replace('_',' ').capitalize()}: {(label or str(a.value)).replace(' (Recommended)','')}")
    return spec,said

def _session_turn_events(session,req):
    """Apply chosen answers, then run the design agent on any free text, yielding its live events. The last event is
    {'type': 'saved', 'session'}: the turn is persisted only once it has finished."""
    spec=ProjectSpec.model_validate(session['spec']);before=spec.model_dump(mode='json')
    spec,said=_said(spec,req.answers)
    reply,ai_questions,mode,outcome,tools,steps=None,[],'deterministic','updated',['inspect_project'],[]
    if said:
        yield {'type':'step','id':'answers','label':'Applied your answers: '+', '.join(x.split(':')[0] for x in said),'status':'complete'}
        steps.append({'id':'answers','label':'Applied your answers: '+', '.join(x.split(':')[0] for x in said),'status':'complete'})
    if req.message:
        history=[{'role':m['role'],'text':m['text']} for m in session.get('messages',[])]
        try:
            out=None
            for e in run_compose_agent(session['template'],spec,history,req.message):
                if e['type']=='result':out=e
                else:yield e
            spec,reply,ai_questions,mode,outcome,tools,steps=out['spec'],out['reply'],out['questions'],'live',out['outcome'],out['tools'],steps+out['steps']
        except RuntimeError as e:reply,mode,outcome,tools=str(e),'unavailable','unsupported',['inspect_project','preserve_project']
        except Exception as e:
            log.exception('Compose session turn failed');yield {'type':'reply_reset'}
            reply,mode,outcome,tools=f'The assistant could not process that ({type(e).__name__}). Nothing changed from your message; try rephrasing or pick a suggestion.','error','unsupported',['inspect_project','preserve_project']
        if mode!='live':yield {'type':'reply_delta','text':reply}
    elif said:
        yield {'type':'step','id':'verify','label':'Regenerate the plan and run every check','status':'active'}
        plan=assess(spec);done={'id':'verify','label':'Regenerated the plan and ran every check','status':'complete' if plan.get('plan_ok') else 'error','detail':plan_summary(plan)}
        yield {'type':'step',**done};steps.append(done)
        reply='Noted. '+'; '.join(said)+'. '+plan_summary(plan)+'.';tools+=['update_brief','validate']
        yield {'type':'reply_delta','text':reply}
    after=spec.model_dump(mode='json')
    shown=(req.shown or req.message or ' · '.join(said)).strip()
    turn_id='turn-'+uuid.uuid4().hex[:10]
    if shown:session['messages'].append({'role':'user','text':shown,'turn_id':turn_id})
    if reply:session['messages'].append({'role':'assistant','text':reply,'turn_id':turn_id,'before_spec':before,'after_spec':after,'outcome':outcome,'status':'applied','steps':steps})
    session['turns'].append({'id':turn_id,'before_spec':before,'after_spec':after,'outcome':outcome,'tools':tools,'status':'applied'})
    session['spec']=after;session['mode']=mode
    asked={q['field'] for q in ai_questions};pending=questions_for(spec)
    session['questions']=(ai_questions+[q for q in pending if q['field'] not in asked])[:4]
    yield {'type':'saved','session':store().save_compose_session(session)}

@app.get('/api/compose/templates')
def compose_templates():
    return [{'id':k,'label':t['label'],'use':t['use'],'height':t['height'],'rooms':[{'name':n,'kind':kd,'area':a,'count':c} for n,kd,a,c in t['rooms']]} for k,t in TEMPLATES.items()]
@app.post('/api/compose/turn')
def compose_step(req:ComposeRequest):
    spec=req.spec if req.spec and req.spec.template==req.template else template_spec(req.template)
    said=[]
    for a in req.answers:
        bank={q['field']:q for q in questions_for(spec)}
        spec=apply_answer(spec,a.field,a.value)
        label=next((o['label'] for o in bank.get(a.field,{}).get('options',[]) if o['value']==a.value),None)
        said.append(f"{bank[a.field]['header'] if a.field in bank else a.field.replace('_',' ').capitalize()}: {(label or str(a.value)).replace(' (Recommended)','')}")
    reply,ai_questions,mode=None,[],'deterministic'
    if req.message:
        try:
            out=compose_turn(req.template,spec,[m.model_dump() for m in req.history],req.message);spec,reply,ai_questions,mode=out['spec'],out['reply'],out['questions'],'live'
        except RuntimeError as e:reply,mode=str(e),'unavailable'
        except Exception as e:
            log.exception('Compose turn failed');reply,mode=f'The assistant could not process that ({type(e).__name__}). Nothing changed; try rephrasing or pick a suggestion.','error'
    elif said:reply='Noted. '+'; '.join(said)+'.'
    asked={q['field'] for q in ai_questions}
    pending=questions_for(spec)
    questions=(ai_questions+[q for q in pending if q['field'] not in asked])[:4]
    return {'spec':spec,'reply':reply,'questions':questions,'remaining':len(pending),'preview':preview(spec),'mode':mode,**status()}
@app.post('/api/compose/sessions')
def create_compose_session(req:ComposeSessionCreate):return _session_view(_new_compose_session(req.template))
@app.get('/api/compose/sessions/latest')
def latest_compose_session():
    session=store().latest_compose_session()
    return {'session':_session_view(session) if session else None}
@app.get('/api/compose/sessions/{id}')
def get_compose_session(id:str):return _session_view(store().get_compose_session(id))
@app.post('/api/compose/sessions/{id}/turn/stream')
def stream_compose_session_turn(id:str,req:ComposeSessionTurn):
    """NDJSON stream of the agent's real work: tool and check steps as they run, the reply as it is written, then the saved session."""
    def line(e):return json.dumps(e,separators=(',',':'),default=str)+'\n'
    def generate():
        try:
            session=store().get_compose_session(id)
            if session.get('status')!='active':raise Conflict('This design session is no longer active')
            for e in _session_turn_events(session,req):
                if e['type']=='saved':session=e['session']
                else:yield line(e)
            yield line({'type':'final','session':_session_view(session)})
        except Exception as e:
            log.exception('Compose stream failed');yield line({'type':'error','detail':str(e)})
    return StreamingResponse(generate(),media_type='application/x-ndjson',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
@app.post('/api/compose/sessions/{id}/undo')
def undo_compose_session(id:str):
    session=store().get_compose_session(id)
    turn=next((t for t in reversed(session.get('turns',[])) if t.get('status')=='applied' and t.get('before_spec')!=t.get('after_spec')),None)
    if not turn:raise Conflict('There is no assistant edit to revert')
    turn['status']='reverted';session['spec']=turn['before_spec'];session['questions']=questions_for(ProjectSpec.model_validate(session['spec']))[:4]
    for message in session.get('messages',[]):
        if message.get('turn_id')==turn['id']:message['status']='reverted'
    session['messages'].append({'role':'assistant','text':'Reverted the latest assistant edit. The earlier project state is restored.','outcome':'reverted','status':'applied'})
    return _session_view(store().save_compose_session(session))
@app.post('/api/compose/sessions/{id}/reject')
def reject_compose_session(id:str):
    session=store().get_compose_session(id)
    session['spec']=session['baseline_spec'];session['questions']=questions_for(ProjectSpec.model_validate(session['spec']))[:4]
    for turn in session.get('turns',[]):
        if turn.get('status')=='applied':turn['status']='rejected'
    for message in session.get('messages',[]):
        if message.get('turn_id'):message['status']='rejected'
    session['messages'].append({'role':'assistant','text':'Rejected all assistant edits. The original template has been restored.','outcome':'rejected','status':'applied'})
    return _session_view(store().save_compose_session(session))
@app.post('/api/compose/sessions/{id}/build')
def build_compose_session(id:str):
    session=store().get_compose_session(id);spec=ProjectSpec.model_validate(session['spec']);b,notes=compose(spec)
    revision=store().import_model(b,label=f'New project · {b.name}'[:120]);session['status']='built';session['candidate_revision_id']=revision['id']
    summary=revision['results']['summary']
    session['messages'].append({'role':'assistant','text':f"Built {b.name} as a candidate revision: {b.width:g} × {b.depth:g} m, {summary['pass']} checks pass, {summary['fail']} fail and {summary['missing_input']} wait for inputs. "
        'Review it, then apply it. I can keep editing it from the project view.','outcome':'built','candidate_revision_id':revision['id'],'status':'applied'})
    store().save_compose_session(session)
    return {'revision':revision,'notes':notes,'thread_id':session['id']}
@app.post('/api/compose/build')
def compose_build(req:BuildRequest):
    b,notes=compose(req.spec)
    return {'revision':store().import_model(b,label=f'New project · {b.name}'[:120]),'notes':notes}
class QuickCheckRequest(Model):
    discipline:Literal['structure','fire']='structure'
    attachment:Attachment
    page:int=Field(default=0,ge=0,le=500)
class QuickSampleRequest(Model):
    discipline:Literal['structure','fire']='structure'
    live:bool=False
def _quick_id(id:str):
    if not quickcheck.ID.match(id):raise KeyError('Quick check not found')
    return id
def _reading(fn):
    """Drawing reads: no provider is a 503 the page explains; a failed or invalid model reply is a 502 with nothing saved."""
    try:return quickcheck.public(fn())
    except RuntimeError as e:return JSONResponse(status_code=503,content={'detail':str(e),'mode':'unavailable'})
    except ValidationError:
        log.exception('Sheet reading did not validate')
        return JSONResponse(status_code=502,content={'detail':'The drawing could not be read into a structural grid. Try a clearer sheet or a single page.','mode':'error'})
    except (ValueError,KeyError):raise
    except Exception as e:
        log.exception('Quick check reading failed')
        return JSONResponse(status_code=502,content={'detail':f'The AI reading failed ({type(e).__name__}). Nothing was saved; try again.','mode':'error'})
@app.post('/api/quick-checks')
def create_quick_check(req:QuickCheckRequest):
    raw=req.attachment.raw()
    return _reading(lambda:quickcheck.create(store(),req.discipline,raw,req.attachment.mime_type,req.attachment.name,req.page))
@app.post('/api/quick-checks/sample')
def sample_quick_check(req:QuickSampleRequest):return _reading(lambda:quickcheck.create_sample(store(),req.discipline,req.live))
@app.get('/api/quick-checks/{id}')
def get_quick_check(id:str):return quickcheck.public(store().get_quick_check(_quick_id(id)))
@app.get('/api/quick-checks/{id}/image')
def quick_check_image(id:str):return Response(store().get_quick_check_image(_quick_id(id)),media_type='image/png',headers={'Cache-Control':'private, max-age=86400'})
@app.post('/api/quick-checks/{id}/run')
def run_quick_check(id:str,inputs:dict=Body(...)):return quickcheck.public(quickcheck.run(store(),_quick_id(id),inputs))
@app.post('/api/import/project')
def import_project(req:ImportRequest):return store().import_model(req.model)
@app.post('/api/import/survey')
def import_survey(req:SurveyRequest):
    s=store().get(req.base_revision);b=Building.model_validate(s['model']);b.site.survey=parse_survey(req.csv_text,req.units);validate_site(b.site)
    return store().preview(CommandRequest(base_revision=req.base_revision,command_id=uuid.uuid4().hex,label='Imported survey',commands=[{'type':'set_site','site':b.site.model_dump()}]))
def _thread(session):
    keep=('role','text','outcome','candidate_revision_id','questions')
    return {'id':session['id'],'name':(session.get('spec') or {}).get('name') or 'Project conversation','status':session['status'],
            'messages':[{k:m[k] for k in keep if m.get(k) is not None} for m in session.get('messages',[])][-40:]}
def _new_thread():
    now=time.time()
    return store().save_compose_session({'id':'compose-'+uuid.uuid4().hex[:12],'template':None,'spec':None,'messages':[],'turns':[],'status':'project','created_at':now,'updated_at':now})
@app.get('/api/assistant/thread')
def assistant_thread():
    """The latest project conversation: a built new-project session continues here, so the chat follows the project."""
    session=store().latest_compose_session(('built','project'))
    return {'thread':_thread(session) if session else None}
@app.post('/api/assistant/thread')
def new_assistant_thread():return {'thread':_thread(_new_thread())}
@app.post('/api/ai')
def ai(req:AIRequest):
    s=store().get(req.revision_id)
    thread=store().get_compose_session(req.thread_id) if req.thread_id else None
    if thread and thread.get('status') not in ('built','project'):raise Conflict('That conversation is still designing a new project; build it first')
    history=[{'role':m['role'],'text':m['text']} for m in (thread or {}).get('messages',[]) if m.get('text')]
    if req.attachment:req.attachment.raw()  # malformed uploads are a 422, not a model failure
    try:plan=interpret(req,s,history)
    except RuntimeError as e:return JSONResponse(status_code=503,content={'detail':str(e),'mode':'unavailable'})
    except Exception as e:
        log.exception('Assistant request failed')
        return JSONResponse(status_code=502,content={'detail':f'AI request or validation failed ({type(e).__name__}). No changes were applied.','mode':'error'})
    response={'mode':'live','interpretation':plan.model_dump(),'candidate':None,'evidence':None}
    if plan.action=='edit':
        candidate=store().preview(CommandRequest(base_revision=req.revision_id,command_id=uuid.uuid4().hex,label=f'Layout from {req.attachment.name}'[:120] if req.attachment else 'Assistant proposed edit',commands=plan.commands));response['candidate']=candidate
        response['evidence']={'summary':candidate['results']['summary'],'invalidated':candidate['invalidated'],'comparison':compare(s['results'],candidate['results'],s['model'],candidate['model'])}
    elif plan.action=='analyze':response['candidate']=store().rerun(req.revision_id)
    elif plan.action=='alternatives':response['evidence']=layouts(req.revision_id)
    elif plan.action=='rules':response['evidence']={'rules':RULES,'checks':s['results']['checks']}
    elif plan.action=='compare':response['evidence']=comparison(before=store().state()['head'],after=req.revision_id)
    elif plan.action=='inspect':response['evidence']={'summary':s['results']['summary'],'checks':[c for c in s['results']['checks'] if not req.selected_id or req.selected_id in c['objects']],'scope':s['results']['structure'].get('scope')}
    thread=thread or _new_thread()
    candidate=response['candidate']['id'] if response['candidate'] and response['candidate'].get('status')=='candidate' else None
    thread['messages']+=[{'role':'user','text':(req.message+(f' [attached {req.attachment.name}]' if req.attachment else ''))[:2000]},
                         {'role':'assistant','text':' '.join(x for x in (plan.explanation,plan.clarification) if x)[:2000],'outcome':plan.action,'candidate_revision_id':candidate,
                          'questions':[q.model_dump() for q in plan.questions]}]
    response['thread']=_thread(store().save_compose_session(thread))
    return response

@app.get('/api/export/{id}/project.json')
def export_json(id:str):
    s=store().get(id);return Response(json.dumps({'schema_version':'1.0','model':s['model'],'revision':{k:v for k,v in s.items() if k not in ['model','results']},'results':s['results']},indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename=buildgraph-project.json'})
@app.get('/api/export/{id}/quantities.csv')
def export_csv(id:str):
    s=store().get(id);out=io.StringIO();writer=csv.writer(out);writer.writerow(['revision','item','unit','net','waste_fraction','stock_length','purchased','unit_rate_PHP','cost_PHP','rate_source','rate_date','source_ids','formula','status'])
    def safe(value):return "'"+value if isinstance(value,str) and value[:1] in ['=','+','-','@'] else value
    for x in s['results']['quantities']['items']:writer.writerow([safe(v) for v in [id,x['name'],x['unit'],x['net'],x['waste'],x['stock'],x['purchased'],x['rate'],x['cost'],x['rate_source'],x['rate_date'],';'.join(x['source_ids']),x['formula'],'provisional' if x['provisional'] else 'modeled']])
    for exclusion in s['results']['quantities']['exclusions']:writer.writerow([id,'EXCLUDED: '+exclusion,'','','','','','','','','','','','unsupported'])
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=buildgraph-quantities.csv'})
def permit_inputs(id):
    # Drawings are rebuilt from the stored model with the current engine, so a stale stored result cannot leak in.
    s=store().get(id);b=Building.model_validate(s['model']);return b,compute(b,id)
@app.post('/api/export/{id}/permit.pdf')
def permit_pdf(id:str,req:PermitRequest):
    b,r=permit_inputs(id)
    return Response(render_pdf(b,r,req,id),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename=permit-set-{id}-{req.sheet}.pdf'})
@app.post('/api/export/{id}/permit.dxf')
def permit_dxf(id:str,req:PermitRequest):
    b,r=permit_inputs(id)
    return Response(render_dxf(b,r,req,id),media_type='image/vnd.dxf',headers={'Content-Disposition':f'attachment; filename=permit-set-{id}.dxf'})
@app.get('/api/export/{id}/report',response_class=HTMLResponse)
def report(id:str):
    s=store().get(id);r=s['results'];esc=lambda x:html.escape(str(x));rows=''.join(f'<tr><td>{esc(q["name"])}</td><td>{q["net"]:.2f} {esc(q["unit"])}</td><td>{q["purchased"]:.2f}</td><td>₱{q["cost"]:,.2f}</td></tr>' for q in r['quantities']['items']);checks=''.join(f'<tr><td>{esc(c["rule_id"])}</td><td>{esc(c["status"])}</td><td>{esc(c["evidence"])}</td></tr>' for c in r['checks'])
    return f'''<!doctype html><html><head><title>BuildGraph review · {esc(s['model']['name'])}</title><style>body{{font:14px system-ui;max-width:1000px;margin:40px auto;color:#203b34}}h1{{font-size:32px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;text-align:left;border-bottom:1px solid #ddd}}td{{vertical-align:top}}code{{overflow-wrap:anywhere}}@media print{{button{{display:none}}body{{margin:0}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style></head><body><button onclick="window.print()">Print review</button><h1>BuildGraph / {esc(s['model']['name'])}</h1><p>Revision {esc(id)} · {esc(s['status'])} · Synthetic example / preliminary planning</p><p>{esc(r['structure'].get('scope','Analysis missing inputs'))}</p><p>Input hash <code>{esc(s['input_hash'])}</code><br>Result hash <code>{esc(s['result_hash'])}</code></p><h2>Estimate · ₱{r['quantities']['total']:,.2f}</h2><p>{esc(r['quantities']['catalog'])}</p><table><thead><tr><th>Item</th><th>Net</th><th>Purchased</th><th>Estimate</th></tr></thead><tbody>{rows}</tbody></table><h2>Exclusions</h2><p>{esc('; '.join(r['quantities']['exclusions']))}</p><h2>Checks & coverage</h2><table><thead><tr><th>Rule</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{checks}</tbody></table><h2>Engineering inputs & provenance</h2><pre>{esc(json.dumps(s['model']['engineering'],indent=2))}</pre><p>Professional review is required for construction and approval. Partial coverage is not whole-building certification.</p></body></html>'''

static=Path(__file__).resolve().parent.parent/'frontend'/'dist'
class Frontend(StaticFiles):
    """Vite's hashed /assets never change, so browsers keep them for a year; index.html revalidates so a deploy shows at once."""
    async def get_response(self,path,scope):
        r=await super().get_response(path,scope)
        r.headers['Cache-Control']='public, max-age=31536000, immutable' if path.startswith('assets/') and r.status_code in (200,304) else 'no-cache'
        return r
if static.exists():app.mount('/',Frontend(directory=static,html=True),name='frontend')

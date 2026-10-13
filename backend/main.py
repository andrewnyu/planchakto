from __future__ import annotations
import os,io,csv,json,uuid,html,logging
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response,HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError,Field
from .domain import Building,CommandRequest,Model,digest
from .store import LocalStore,Conflict
from .engine import ENGINE_VERSION,validate_result,compute
from .drawings import PermitRequest,render_pdf,render_dxf
from .quantities import compare
from .rules import RULES
from .structure import CATALOG
from .geometry import parse_survey,validate_site
from .layout import generate_layouts
from .ai import AIRequest,interpret,status

app=FastAPI(title='BuildGraph',version='0.1.0')
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
@app.get('/api/project')
def project():
    state=store().state();s=store().get(state['head'])
    s['results']['stale']=s['results']['input_hash']!=digest(s['model']) or s['results'].get('engine_version')!=ENGINE_VERSION
    return {'state':state,'accepted':s,'revisions':store().list(),**status(),'sections':CATALOG}
@app.get('/api/revisions/{id}')
def revision(id:str):return store().get(id)
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
@app.post('/api/import/project')
def import_project(req:ImportRequest):return store().import_model(req.model)
@app.post('/api/import/survey')
def import_survey(req:SurveyRequest):
    s=store().get(req.base_revision);b=Building.model_validate(s['model']);b.site.survey=parse_survey(req.csv_text,req.units);validate_site(b.site)
    return store().preview(CommandRequest(base_revision=req.base_revision,command_id=uuid.uuid4().hex,label='Imported survey',commands=[{'type':'set_site','site':b.site.model_dump()}]))
@app.post('/api/ai')
def ai(req:AIRequest):
    s=store().get(req.revision_id)
    if req.attachment:req.attachment.raw()  # malformed uploads are a 422, not a model failure
    try:plan=interpret(req,s)
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
if static.exists():app.mount('/',StaticFiles(directory=static,html=True),name='frontend')

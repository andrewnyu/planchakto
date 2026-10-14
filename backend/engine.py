from .domain import Building,digest
from .geometry import terrain,layout_checks,fitout_checks
from .structure import analyze_structure
from .routing import route_all
from .quantities import takeoff
from .rules import evaluate_rules
from .solar import analyze_solar
from .fire import analyze_fire
from .lateral import analyze_lateral
import time

ENGINE_VERSION='buildgraph-0.4.0'
def compute(b:Building,revision_id:str):
    t=time.perf_counter();site=terrain(b);layout=layout_checks(b);structure=analyze_structure(b);lateral=analyze_lateral(b,structure);routing=route_all(b);fitout=fitout_checks(b);solar=analyze_solar(b,structure,routing);fire=analyze_fire(b);quantities=takeoff(b,structure,routing,solar)
    checks=evaluate_rules(b,structure,layout,routing,fitout,revision_id,solar,fire,lateral)
    result={'revision_id':revision_id,'input_hash':digest(b),'engine_version':ENGINE_VERSION,'stale':False,'terrain':site,'layout':layout,'structure':structure,'lateral':lateral,'routing':routing,'fitout':fitout,'solar':solar,'fire':fire,'quantities':quantities,'checks':checks,'summary':{key:sum(c['status']==key for c in checks) for key in ['pass','fail','missing_input','unsupported','not_applicable']},'settings':{'layout_seed':42,'routing_step_m':.25,'beam_elements':16},'elapsed_ms':round((time.perf_counter()-t)*1000,2)}
    result['result_hash']=digest({k:v for k,v in result.items() if k not in ['elapsed_ms','revision_id','checks'] }|{'checks':[{k:v for k,v in c.items() if k!='revision_id'} for c in checks]})
    return result

def validate_result(b,result,revision_id):
    if result['input_hash']!=digest(b) or result['revision_id']!=revision_id or result.get('engine_version')!=ENGINE_VERSION:raise ValueError('Stale analysis: result does not match the target revision, inputs or solver version')

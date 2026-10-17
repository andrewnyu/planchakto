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
# A scoped run (one discipline from a single drawing) computes only that discipline. Everything else is listed
# as not checked with the reason, so a sheet that cannot show a clash never reports one as passing.
SCOPES={'structure':{'structure','lateral'},'fire':{'fire'},'plumbing':{'routing:water','routing:drain'},'electrical':{'routing:conduit','electrical:load'}}
NOT_CHECKED={
 'structure':[
  {'item':'Architecture and layout','reason':'Rooms, circulation and setbacks are not shown on a framing plan.'},
  {'item':'Plumbing and electrical routes','reason':'Clashes between services and columns need the services drawings.'},
  {'item':'Fire protection','reason':'Egress and provisions need the floor plan and occupancy.'},
  {'item':'Rooftop solar','reason':'No PV array is modeled, so no PV roof load is included in the beam checks.'},
  {'item':'Site and earthworks','reason':'Survey and boundary data are not part of this check.'},
  {'item':'Quantities and cost','reason':'Rates are project-specific and are not part of this check.'},
 ],
 'fire':[
  {'item':'Structure and seismic','reason':'Framing, loads and soil are not shown on a floor plan.'},
  {'item':'Plumbing and electrical routes','reason':'Services need their own drawings.'},
  {'item':'Stairs, upper floors and multi-storey egress','reason':'One single-storey floor plan is screened; vertical exits are not modeled.'},
  {'item':'Furniture, fixed seating and columns in the path of travel','reason':'Travel is measured across clear room floors and through the doors read from the sheet.'},
  {'item':'Fire truck access, hydrants and site separation','reason':'Site plans are not part of this check.'},
  {'item':'Quantities and cost','reason':'Rates are project-specific and are not part of this check.'},
 ],
 'plumbing':[
  {'item':'Pipe sizing, pressure and flow','reason':'Fixture demand, pipe diameters, pressure loss and hydraulic adequacy are not evaluated.'},
  {'item':'Vents, traps and cleanouts','reason':'A single plan sheet does not establish the complete sanitary system.'},
  {'item':'Structural clashes and penetrations','reason':'No framing sheet is included, so columns, beams, footings and penetrations are not checked.'},
  {'item':'Architecture, fire, electrical and site','reason':'Only the plumbing points and utility connections on this sheet are screened.'},
  {'item':'Quantities and cost','reason':'Pipe diameters, fittings, specifications and project rates are not part of this check.'},
 ],
 'electrical':[
  {'item':'Conductors and protection','reason':'Wire size, voltage drop, breakers, fault current, grounding and protection coordination are not evaluated.'},
  {'item':'Lighting and receptacle code coverage','reason':'Outlet spacing, illumination, emergency systems and statutory compliance are not evaluated.'},
  {'item':'Structural clashes and penetrations','reason':'No framing sheet is included, so columns, beams and penetrations are not checked.'},
  {'item':'Architecture, fire, plumbing and utility service','reason':'Only drawn equipment, circuits and panel home runs are screened.'},
  {'item':'Quantities and cost','reason':'Conductor sizes, raceway specifications and project rates are not part of this check.'},
 ]}
CHECKED={'structure':['Roof beams: deflection and elastic stress','Pad footings: gravity bearing','Seismic: base shear, drift, columns, frame members and footing sliding'],
 'fire':['Occupant load and number of exits','Travel distance, common path and dead ends through the doors read from the sheet','Exit capacity and corridor width','Sprinkler, alarm, emergency lighting and exit sign triggers','Portable extinguishers: count, rating and reach'],
 'plumbing':['Fixture-to-water-point plan connectivity and approximate route length','Fixture-to-drain-point plan connectivity and user-confirmed gravity fall'],
 'electrical':['Equipment-to-panel plan connectivity and approximate conduit length','Connected-load and single-phase current arithmetic from confirmed circuit inputs']}
STRUCTURE_SKIPPED={'status':'not_applicable','reason':'Not part of this check','beams':[],'girders':[],'foundations':[],'alternatives':[],'errors':[],'scope':'Not part of this check'}

def _skipped(reason='Not part of this check'):
    return {'terrain':{'triangles':[],'boundary_area':0,'cut_m3':None,'fill_m3':None,'coverage':0,'method':reason,'status':'not_applicable'},
            'layout':{'status':'not_applicable','issues':[],'doors':[],'circulation':reason},
            'routing':{'routes':[],'circuits':[],'obstacles':[],'settings':{}},
            'fitout':{'status':'not_applicable','issues':[],'scope':reason},
            'solar':{'enabled':False},'fire':{'enabled':False},
            'quantities':{'items':[],'unpriced':[],'total':0,'currency':'PHP','catalog':reason,'exclusions':[],'walls':[],'openings':[]}}

def compute(b:Building,revision_id:str,scope:str|None=None,doors=None):
    """`doors`: interior doors drawn on a Quick check floor plan, passed to the fire screen (see fire.analyze_fire)."""
    t=time.perf_counter()
    if scope is None:
        site=terrain(b);layout=layout_checks(b);structure=analyze_structure(b);lateral=analyze_lateral(b,structure);routing=route_all(b);fitout=fitout_checks(b);solar=analyze_solar(b,structure,routing);fire=analyze_fire(b);quantities=takeoff(b,structure,routing,solar)
    else:
        if scope not in SCOPES:raise ValueError(f'Unsupported check scope {scope!r}')
        skip=_skipped();site,layout,routing,fitout,solar,fire,quantities=(skip[k] for k in ['terrain','layout','routing','fitout','solar','fire','quantities'])
        if scope=='structure':structure=analyze_structure(b);lateral=analyze_lateral(b,structure)
        else:structure,lateral=dict(STRUCTURE_SKIPPED),{'enabled':False}
        if scope=='fire':fire=analyze_fire(b,doors)
        if scope in ('plumbing','electrical'):
            routing=route_all(b)
            for route in routing['routes']:
                if route['status']=='pass':route['reason']='Connected on the plan; structural clashes and penetrations are not checked because no framing sheet is included'
    checks=evaluate_rules(b,structure,layout,routing,fitout,revision_id,solar,fire,lateral,scope)
    result={'revision_id':revision_id,'input_hash':digest(b),'engine_version':ENGINE_VERSION,'stale':False,'terrain':site,'layout':layout,'structure':structure,'lateral':lateral,'routing':routing,'fitout':fitout,'solar':solar,'fire':fire,'quantities':quantities,'checks':checks,'summary':{key:sum(c['status']==key for c in checks) for key in ['pass','fail','missing_input','unsupported','not_applicable']},'settings':{'layout_seed':42,'routing_step_m':.25,'beam_elements':16},'elapsed_ms':round((time.perf_counter()-t)*1000,2)}
    if scope:result|={'scope':scope,'coverage':{'checked':CHECKED[scope],'not_checked':NOT_CHECKED[scope]}}
    result['result_hash']=digest({k:v for k,v in result.items() if k not in ['elapsed_ms','revision_id','checks'] }|{'checks':[{k:v for k,v in c.items() if k!='revision_id'} for c in checks]})
    return result

def validate_result(b,result,revision_id):
    if result['input_hash']!=digest(b) or result['revision_id']!=revision_id or result.get('engine_version')!=ENGINE_VERSION:raise ValueError('Stale analysis: result does not match the target revision, inputs or solver version')

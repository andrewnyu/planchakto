"""Versioned illustrative checks. No unconsulted Philippine code clauses."""
from .domain import digest
from .solar import SOURCES as SOLAR_SOURCES
from .fire import SOURCE as FIRE_SOURCE
from .lateral import SOURCE as LATERAL_SOURCE

SOURCES={
 'beam':'Euler–Bernoulli beam theory; stiffness implementation and closed-form validation in docs/ENGINEERING.md. Not a code clause.',
 'project':'User-entered demonstration criterion; source supplied with project. Not a statutory requirement.',
 'geometry':'Euclidean geometry; implemented predicates in backend/geometry.py and backend/routing.py.',
 'code':'Authoritative Philippine code text and project applicability not supplied; no code clauses asserted.',
 'pv-ocpd':SOLAR_SOURCES['ocpd'],'pv-busbar':SOLAR_SOURCES['busbar'],'pv-net':SOLAR_SOURCES['netmeter'],'pv-host':SOLAR_SOURCES['hosting'],'pv-xfmr':SOLAR_SOURCES['transformer'],'fire':FIRE_SOURCE,'seismic':LATERAL_SOURCE}

def make_rule(id,name,source,required,formula,units,scope):
    return {'id':id,'version':'1.0.0','name':name,'source':SOURCES[source],'edition':'BuildGraph 0.1 / 2026-10-13','reference':formula,'jurisdiction':'Cited PH source — verify against the current official edition' if source.startswith('pv-') or source in ('fire','seismic') else 'Project-specific illustrative criterion; not verified PH regulation','applicability':scope,'required_inputs':required,'formula':formula,'units':units,'tolerance':1e-6,'review_status':'Numerically benchmarked' if source=='beam' else 'Prototype / professional review required','exclusions':'Whole-building compliance, stability and construction certification'}

RULES=[
 make_rule('LAYOUT','Room geometry & access','geometry',['room rectangles','door graph','boundary','setback'],'containment ∧ disjoint interiors ∧ area ranges ∧ door access','m, m²','Rectangular rooms and fixed corridor'),
 make_rule('SLS','Roof beam deflection','beam',['E','I','L','service uniform load','user limit'],'δmax = 5qL⁴/(384EI) ≤ L / user deflection ratio','mm','Simply supported roof beam service loading'),
 make_rule('ELASTIC','Elastic bending screen','beam',['section modulus','factored q','yield strength'],'σ = qL²/(8Z) ≤ user material yield strength','MPa','Elastic stress screen only; not member design resistance'),
 make_rule('BEARING','Centered bearing screen','project',['vertical service reaction','footing size','gross allowable pressure'],'q = (reaction + pad weight + column allowance)/B² ≤ allowable','kPa','Centered full-contact gravity bearing; no overburden'),
 make_rule('ROUTE','Service connectivity & clashes','geometry',['endpoints','structural obstacles'],'connected polyline ∧ zero obstacle intersections','m','Planar routes on authorized routing planes'),
 make_rule('DRAIN','Gravity drain fall','project',['endpoint elevations','route length','minimum slope'],'(zstart − zend) / length ≥ specified slope','m/m','Monotonic constant grade per dedicated drain run'),
 make_rule('FITOUT','Placement & front clearance','geometry',['furniture rectangles','front access','door envelopes'],'contained ∧ no body/front access/door envelope intersections','m','Furniture body and conservative access envelopes'),
 make_rule('ELECTRICAL','Circuit load arithmetic','project',['nameplate watts','voltage','power factor','demand factor'],'I = ΣW × demand / (V × power factor)','A','Single-phase load organization, not electrical design'),
 make_rule('PV-ROOF','PV array fit','geometry',['roof extent','edge setback','module size','target kWp'],'modules packed in (W − 2s) × (D − 2s), best orientation','modules, kWp','Flat projected roof, single rectangular array'),
 make_rule('PV-LOAD','PV superimposed roof load','beam',['module mass & area','racking mass','beam tributary strip'],'q_pv = (m_mod/A_mod + m_rack)·g × covered tributary width, full span; re-run SLS/ELASTIC/BEARING','kPa, kN/m','Gravity only; uplift and attachments excluded'),
 make_rule('PV-WIND','PV wind uplift','code',[],'not evaluated','n/a','Outside supported family'),
 make_rule('PV-OCPD','Inverter output breaker','pv-ocpd',['inverter kW','voltage','phases'],'I = P / (V·√3 if 3φ) ; OCPD ≥ 1.25·I, next standard rating','A','Inverter AC output circuit only'),
 make_rule('PV-BUSBAR','Busbar backfeed (120% rule)','pv-busbar',['main breaker','busbar rating','inverter current'],'I_main + 1.25·I_inv ≤ 1.2·I_bus','A','Load-side connection, PV breaker opposite the main'),
 make_rule('PV-XFMR','Transformer loading & reverse flow','pv-xfmr',['transformer kVA','circuit demand','inverter kW'],'max(Σ demand/pf, P_inv) ≤ S_transformer','kVA','Arithmetic screen; not a Distribution Impact Study'),
 make_rule('PV-HOSTING','DU hosting capacity','pv-host',['DU hosting capacity per transformer','inverter kW'],'P_inv ≤ hosting capacity','kW','DU-published value required'),
 make_rule('PV-NETMETER','Net-metering capacity cap','pv-net',['array kWp','customer class','contracted capacity'],'kWp ≤ 100 kW (residential) or min(1 MW, contracted) (non-residential)','kW','Eligibility screen only'),
 make_rule('FIRE-OCCLOAD','Occupant load','fire',['gross floor area','occupancy'],'ceil(area / m² per person)','persons','Business / mercantile, single storey'),
 make_rule('FIRE-EXITS','Number of exits','fire',['exits','occupant load','travel distance'],'exits ≥ 2 per storey (3 > 500, 4 > 1,000) unless a single-exit allowance applies','count','Exterior exit doors on the building perimeter'),
 make_rule('FIRE-TRAVEL','Travel distance to exit','fire',['rooms','doors','exits','sprinklers'],'max over floor of shortest door-constrained path ≤ limit','m','0.25 m grid, 8-connected, furniture ignored'),
 make_rule('FIRE-DEADEND','Dead-end corridors','fire',['corridor','exits'],'corridor length reaching an exit in one direction only ≤ limit','m','Straight corridors, exits at the corridor'),
 make_rule('FIRE-COMMON','Common path of travel','fire',['exits','routes'],'shared prefix of routes to the two nearest exits ≤ limit (tree-metric approximation)','m','Approximation; single exit = full travel'),
 make_rule('FIRE-CAPACITY','Exit capacity','fire',['occupant load','exit widths'],'Σ exit width ≥ occupants × 5.0 mm','m','Level egress components'),
 make_rule('FIRE-CORRIDOR','Corridor width','fire',['corridor width','occupant load'],'clear width ≥ 1.12 m when ≥ 50 occupants','m','Business occupancy'),
 make_rule('FIRE-SPRINKLER','Automatic sprinkler trigger','fire',['height','gross area','occupancy'],'required by height/area trigger ⇒ provided','—','Single storey'),
 make_rule('FIRE-ALARM','Fire alarm','fire',['occupancy','occupant load','class'],'required system ⇒ provided','—','New/existing thresholds'),
 make_rule('FIRE-EMLIGHT','Emergency lighting','fire',['occupancy','class','storeys'],'triggered ⇒ provided','—','Single storey'),
 make_rule('FIRE-SIGNS','Exit signs','fire',['exit signs'],'provided','—','All business and mercantile'),
 make_rule('FIRE-EXT','Portable extinguishers','fire',['extinguisher positions & ratings','hazard'],'count ≥ area / max area; door-constrained travel ≤ Table 7 limit; rating ≥ minimum','m, m²','Class A hazards'),
 make_rule('FIRE-SCOPE','Fire protection coverage','fire',[],'not evaluated','n/a','Outside the supported screen'),
 make_rule('SEISMIC-V','Seismic design base shear','seismic',['zone','soil profile','Na, Nv','R','I','seismic weight','height'],'V = Cv·I·W/(R·T), ≤ 2.5·Ca·I·W/R, ≥ 0.11·Ca·I·W and (zone 4) ≥ 0.8·Z·Nv·I·W/R; T = Ct·hn^¾','kN','Single-storey regular frame; static force procedure'),
 make_rule('DRIFT','Storey drift','seismic',['frame stiffness','base shear','R','storey height'],'ΔM = 0.7·R·ΔS ≤ 0.025·h (T < 0.7 s) or 0.020·h','mm','Rigid diaphragm; torsion excluded'),
 make_rule('COLUMN','Steel column strength','seismic',['column section','K','Fy, E','LRFD combinations'],'Pr/Pc + 8/9·Mr/Mc ≤ 1 (Pr/Pc ≥ 0.2) else Pr/(2Pc) + Mr/Mc ≤ 1; Fcr per AISC E3','—','Compact square HSS, first-order analysis'),
 make_rule('FRAME-MEMBER','Frame beam and girder flexure','seismic',['section','seismic combinations'],'M_max ≤ 0.9·Fy·Zp','kN·m','Plastic flexure; lateral-torsional buckling excluded'),
 make_rule('FOOT-LATERAL','Footing under seismic load','seismic',['base reactions','pad size','allowable bearing','friction coefficient'],'e = M/P; q_max = P/B²(1 + 6e/B) or 2P/(3B(B/2 − e)) ≤ allowable; μP/H ≥ sliding FS','kPa','Square pad, uniaxial, no one-third increase'),
 make_rule('WIND','Wind loads','code',[],'not evaluated','n/a','NSCP 2015 §207 not implemented'),
 make_rule('PH-CODE','Philippine code coverage','code',[],'not evaluated','n/a','Code edition and authoritative rule library unavailable'),
]

STRUCTURAL={'SLS','ELASTIC','BEARING','WIND','SEISMIC-V','DRIFT','COLUMN','FRAME-MEMBER','FOOT-LATERAL'}
FIRE={'FIRE-OCCLOAD','FIRE-EXITS','FIRE-TRAVEL','FIRE-DEADEND','FIRE-COMMON','FIRE-CAPACITY','FIRE-CORRIDOR','FIRE-SPRINKLER','FIRE-ALARM','FIRE-EMLIGHT','FIRE-SIGNS','FIRE-EXT','FIRE-SCOPE'}
SCOPED={'structure':STRUCTURAL,'fire':FIRE}
def in_scope(rule,scope):return scope is None or rule=='PH-CODE' or rule in SCOPED.get(scope,())
def evaluate_rules(b,structure,layout,routing,fitout,rev,solar=None,fire=None,lateral=None,scope=None):
    results=[]
    def add(rule,status,objects,evidence,inputs=None):
        if not in_scope(rule,scope):return
        results.append({'id':f'{rule}-{len(results)}','rule_id':rule,'rule_version':'1.0.0','revision_id':rev,'status':status,'objects':objects,'evidence':evidence,'inputs':inputs or {},'explanation':evidence})
    add('LAYOUT',layout['status'],[r.id for r in b.rooms],'; '.join(i['reason'] for i in layout['issues']) or layout['circulation'],{'room_count':len(b.rooms),'setback_m':b.site.setback})
    if not structure['beams']:
        for rule in ['SLS','ELASTIC']:add(rule,structure['status'],[b.roof_id],structure.get('reason') or '; '.join(structure['errors']))
    for error in structure['errors']:add('SLS','unsupported',[b.roof_id],error)
    for beam in structure['beams']:
        add('SLS','pass' if beam['deflection_utilization']<=1 else 'fail',[beam['id']],f"{beam['service']['max_deflection_mm']:.3f} mm / {beam['deflection_limit_mm']:.3f} mm allowable",{'L_m':beam['length'],'service_q_kNm':beam['service_q_kNm'],'E_MPa':b.engineering.elastic_modulus,'I_m4':structure['section']['I']})
        add('ELASTIC','pass' if beam['yield_utilization']<=1 else 'fail',[beam['id']],f"{beam['stress_MPa']:.2f} MPa / {b.engineering.yield_strength:g} MPa yield; local/lateral buckling not evaluated",{'factored_q_kNm':beam['factored_q_kNm'],'yield_utilization':beam['yield_utilization']})
    for f in structure['foundations']:add('BEARING',f['status'],[f['id']],f"{f['pressure_kPa']:.2f} kPa contact pressure; allowable {f['allowable_kPa']} kPa. {f['assumption']}",f)
    for route in routing['routes']:
        add('DRAIN' if route['kind']=='drain' else 'ROUTE',route['status'],[route['id'],route['source_id']],route['reason'],{'length_m':route['length'],'slope':route['slope'],'available_fall_m':route['fall'],'required_slope':b.engineering.drain_slope if route['kind']=='drain' else None})
    add('FITOUT',fitout['status'],[f.id for f in b.furniture],'; '.join(i['reason'] for i in fitout['issues']) or 'All modeled furniture bodies and front access strips clear',{'scope':fitout['scope']})
    for c in routing['circuits']:add('ELECTRICAL',c['status'],c['equipment_ids'],f"{c['connected_W']} W connected; {c['current_A']} A calculated. {c['coverage']}",c)
    if solar and solar['enabled']:
        for c in solar['checks']:add(c['rule'],c['status'],[m['id'] for m in solar['layout']['modules']] or ['solar-array'],c['evidence'],c['inputs'])
    if fire and fire['enabled']:
        for c in fire['checks']:add(c['rule'],c['status'],[b.id],f"{c['evidence']} [{c['clause']}]",c['inputs'])
    if lateral and lateral.get('enabled'):
        for c in lateral['checks']:add(c['rule'],c['status'],c['objects'],f"{c['evidence']} [{c['clause']}]" if c['clause'] else c['evidence'],c['inputs'])
    add('PH-CODE','unsupported',[b.id],'No Philippine statutory rules are verified. This is preliminary planning and review support, requiring appropriate professional review for construction and approval.')
    gaps=[] if scope=='fire' else (['Torsion, orthogonal effects, P-Δ, irregular and multi-storey buildings, dynamic analysis','Connections, base plates and anchor bolts','Foundation settlement, punching shear and reinforcement'] if lateral and lateral.get('enabled') else
          ['Whole-building stability, wind and seismic','Steel column buckling and connections','Foundation uplift, eccentric contact, settlement, sliding, overturning, punching and reinforcement'])
    # A scoped check lists only its own discipline's gaps; other disciplines appear once in the result's coverage.
    for name in gaps+([] if scope else ['Electrical protection, conductor sizing and voltage drop','Plumbing hydraulic sizing, venting and pipe diameter adequacy']):
        add('PH-CODE','unsupported',[b.id],f'{name}: not evaluated by the supported analytical family.')
    return results

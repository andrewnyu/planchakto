"""Versioned illustrative checks. No unconsulted Philippine code clauses."""
from .domain import digest

SOURCES={
 'beam':'Euler–Bernoulli beam theory; stiffness implementation and closed-form validation in docs/ENGINEERING.md. Not a code clause.',
 'project':'User-entered demonstration criterion; source supplied with project. Not a statutory requirement.',
 'geometry':'Euclidean geometry; implemented predicates in backend/geometry.py and backend/routing.py.',
 'code':'Authoritative Philippine code text and project applicability not supplied; no code clauses asserted.'}

def make_rule(id,name,source,required,formula,units,scope):
    return {'id':id,'version':'1.0.0','name':name,'source':SOURCES[source],'edition':'BuildGraph 0.1 / 2026-10-13','reference':formula,'jurisdiction':'Project-specific illustrative criterion; not verified PH regulation','applicability':scope,'required_inputs':required,'formula':formula,'units':units,'tolerance':1e-6,'review_status':'Numerically benchmarked' if source=='beam' else 'Prototype / professional review required','exclusions':'Whole-building compliance, stability and construction certification'}

RULES=[
 make_rule('LAYOUT','Room geometry & access','geometry',['room rectangles','door graph','boundary','setback'],'containment ∧ disjoint interiors ∧ area ranges ∧ door access','m, m²','Rectangular rooms and fixed corridor'),
 make_rule('SLS','Roof beam deflection','beam',['E','I','L','service uniform load','user limit'],'δmax = 5qL⁴/(384EI) ≤ L / user deflection ratio','mm','Simply supported roof beam service loading'),
 make_rule('ELASTIC','Elastic bending screen','beam',['section modulus','factored q','yield strength'],'σ = qL²/(8Z) ≤ user material yield strength','MPa','Elastic stress screen only; not member design resistance'),
 make_rule('BEARING','Centered bearing screen','project',['vertical service reaction','footing size','gross allowable pressure'],'q = (reaction + pad weight + column allowance)/B² ≤ allowable','kPa','Centered full-contact gravity bearing; no overburden'),
 make_rule('ROUTE','Service connectivity & clashes','geometry',['endpoints','structural obstacles'],'connected polyline ∧ zero obstacle intersections','m','Planar routes on authorized routing planes'),
 make_rule('DRAIN','Gravity drain fall','project',['endpoint elevations','route length','minimum slope'],'(zstart − zend) / length ≥ specified slope','m/m','Monotonic constant grade per dedicated drain run'),
 make_rule('FITOUT','Placement & front clearance','geometry',['furniture rectangles','front access','door envelopes'],'contained ∧ no body/front access/door envelope intersections','m','Furniture body and conservative access envelopes'),
 make_rule('ELECTRICAL','Circuit load arithmetic','project',['nameplate watts','voltage','power factor','demand factor'],'I = ΣW × demand / (V × power factor)','A','Single-phase load organization, not electrical design'),
 make_rule('PH-CODE','Philippine code coverage','code',[],'not evaluated','n/a','Code edition and authoritative rule library unavailable'),
]

def evaluate_rules(b,structure,layout,routing,fitout,rev):
    results=[]
    def add(rule,status,objects,evidence,inputs=None):
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
    add('PH-CODE','unsupported',[b.id],'No Philippine statutory rules are verified. This is preliminary planning and review support, requiring appropriate professional review for construction and approval.')
    for name in ['Whole-building stability, wind and seismic','Steel column buckling and connections','Foundation uplift, eccentric contact, settlement, sliding, overturning, punching and reinforcement','Electrical protection, conductor sizing and voltage drop','Plumbing hydraulic sizing, venting and pipe diameter adequacy']:
        add('PH-CODE','unsupported',[b.id],f'{name}: not evaluated by the supported analytical family.')
    return results

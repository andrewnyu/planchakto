"""Independent simply supported Euler–Bernoulli roof beams, SI implementation.
Physical 3D frame is NOT a complete analytical frame. See docs/ENGINEERING.md.
"""
import numpy as np
from .domain import Building
from .solar import array_layout

CATALOG={
 'RHS150':{'label':'RHS 150 × 100 × 5','h':.15,'b':.10,'t':.005},
 'RHS200':{'label':'RHS 200 × 100 × 6','h':.20,'b':.10,'t':.006},
 'RHS250':{'label':'RHS 250 × 150 × 8','h':.25,'b':.15,'t':.008},
}
# Square hollow column sections; same sharp-corner idealisation as the beam catalog.
COLUMNS={
 'SHS150':{'label':'SHS 150 × 150 × 6','h':.15,'b':.15,'t':.006},
 'SHS200':{'label':'SHS 200 × 200 × 8','h':.20,'b':.20,'t':.008},
 'SHS250':{'label':'SHS 250 × 250 × 9','h':.25,'b':.25,'t':.009},
}
for s in [*CATALOG.values(),*COLUMNS.values()]:
    b,h,t=s['b'],s['h'],s['t']
    s['area']=b*h-(b-2*t)*(h-2*t)
    s['I']=(b*h**3-(b-2*t)*(h-2*t)**3)/12
    s['Z']=s['I']/(h/2)
    s['Zp']=(b*h**2-(b-2*t)*(h-2*t)**2)/4
    s['r']=(s['I']/s['area'])**.5
    s['kg_m']=s['area']*7850

class MechanismError(ValueError):pass

def beam_fem(length:float, E:float, I:float, q:float, supports=None, divisions=16):
    if length<=0 or E<=0 or I<=0 or divisions<2:raise ValueError('Positive beam length, E, I and at least 2 elements required')
    n=divisions+1;l=length/divisions;ndof=2*n
    k=E*I/l**3*np.array([[12,6*l,-12,6*l],[6*l,4*l*l,-6*l,2*l*l],[-12,-6*l,12,-6*l],[6*l,2*l*l,-6*l,4*l*l]])
    f=q*l/2*np.array([1,l/6,1,-l/6]);K=np.zeros((ndof,ndof));F=np.zeros(ndof)
    for i in range(divisions):
        dof=np.arange(2*i,2*i+4);K[np.ix_(dof,dof)]+=k;F[dof]+=f
    fixed=[0,2*(n-1)] if supports is None else supports
    free=np.array([i for i in range(ndof) if i not in fixed],dtype=int)
    if not len(free):raise ValueError('No free degrees of freedom')
    A=K[np.ix_(free,free)]
    if np.linalg.matrix_rank(A)<len(free):raise MechanismError('Unstable beam: independent vertical supports are required')
    u=np.zeros(ndof);u[free]=np.linalg.solve(A,F[free]);R=K@u-F
    reactions=[{'dof':i,'force_N':float(-R[i])} for i in fixed]
    vertical=sum(-R[i] for i in fixed if i%2==0)
    moment=sum(-R[i]*(i//2*l) for i in fixed if i%2==0)+sum(-R[i] for i in fixed if i%2==1)
    return {'displacements_mm':(u[::2]*1000).tolist(),'max_deflection_mm':float(np.max(np.abs(u[::2]))*1000),'rotations_rad':u[1::2].tolist(),'reactions':reactions,'vertical_residual_N':float(vertical-q*length),'moment_residual_Nm':float(moment-q*length**2/2),'max_moment_kNm':q*length**2/8/1000,'max_shear_kN':q*length/2/1000,'nodes':[float(x) for x in np.linspace(0,length,n)],'settings':{'elements':divisions,'theory':'linear Euler–Bernoulli','load':'uniform downward','units':'N, m, Pa','end_releases':'both rotations free'}}

def pv_line_load(pv,y,below,above):
    """PV dead load (kN/m) on a beam whose tributary strip [y-below, y+above] overlaps the array; applied over the full span (conservative)."""
    if not pv or not pv['y_extent']:return 0.
    y0,y1=pv['y_extent'];covered=max(0.,min(y+above,y1)-max(y-below,y0))
    return pv['dead_load_kPa']*covered

def analyze_structure(b:Building):
    e=b.engineering;s=CATALOG[e.section];beams=[];reactions={c.id:0. for c in b.columns if c.active};errors=[];pv=array_layout(b)
    if e.dead.value is None or e.live.value is None:return {'status':'missing_input','reason':'Dead and live service loads are required','beams':[],'foundations':[],'alternatives':[],'errors':[]}
    for j,y in enumerate(b.grid_y):
        row=sorted([c for c in b.columns if c.active and abs(c.y-y)<1e-6],key=lambda c:c.x)
        if len(row)<2 or row[0].x!=0 or row[-1].x!=b.width:
            errors.append(f'Grid row {j+1}: missing end support. Cantilevers are outside the supported family.');continue
        below=(y-b.grid_y[j-1])/2 if j else 0;above=(b.grid_y[j+1]-y)/2 if j<len(b.grid_y)-1 else 0;trib=below+above;pv_q=pv_line_load(pv,y,below,above)
        for a,c in zip(row,row[1:]):
            L=c.x-a.x;sw=s['kg_m']*9.80665/1000
            service=(e.dead.value+e.live.value)*trib+sw+pv_q
            factored=(e.dead.value*e.dead_factor+e.live.value*e.live_factor)*trib+(sw+pv_q)*e.dead_factor
            res=beam_fem(L,e.elastic_modulus*1e6,s['I'],service*1000)
            strength=beam_fem(L,e.elastic_modulus*1e6,s['I'],factored*1000)
            stress=strength['max_moment_kNm']*1000/s['Z']/1e6
            # Closed-form utilization without the PV line load, to report the array's structural effect.
            u0=max(5*(service-pv_q)*1000*L**4/(384*e.elastic_modulus*1e6*s['I'])/(L/e.deflection_ratio),(factored-pv_q*e.dead_factor)*1000*L*L/8/s['Z']/1e6/e.yield_strength)
            for col in [a,c]:reactions[col.id]+=service*L/2
            beams.append({'id':f'beam-{a.id}-{c.id}','physical_ids':[a.id,c.id,b.roof_id],'node_ids':[f'node-{a.id}',f'node-{c.id}'],'support_ids':[f'support-{a.id}',f'support-{c.id}'],'load_case_ids':['D-roof','L-roof']+(['D-pv'] if pv_q else []),'combination_ids':['SLS-D+L','ULS-user'],'material_id':'steel-demo','x1':a.x,'x2':c.x,'y':y,'length':L,'tributary_width':trib,'section':e.section,'service_q_kNm':service,'factored_q_kNm':factored,'self_weight_kNm':sw,'pv_kNm':pv_q,'utilization_without_pv':u0,'service':res,'factored':strength,'stress_MPa':stress,'yield_utilization':stress/e.yield_strength,'deflection_limit_mm':L*1000/e.deflection_ratio,'deflection_utilization':res['max_deflection_mm']/(L*1000/e.deflection_ratio),'status':'pass' if stress<=e.yield_strength and res['max_deflection_mm']<=L*1000/e.deflection_ratio else 'fail'})
    # Y-direction grid girders tie the column lines into lateral frames. They carry only self-weight (the roof spans in X).
    girders=[]
    if e.lateral.enabled:
        for x in b.grid_x:
            line=sorted([c for c in b.columns if c.active and abs(c.x-x)<1e-6],key=lambda c:c.y)
            for a,c in zip(line,line[1:]):
                L=c.y-a.y;sw=s['kg_m']*9.80665/1000
                for col in [a,c]:reactions[col.id]+=sw*L/2
                girders.append({'id':f'girder-{a.id}-{c.id}','node_ids':[f'node-{a.id}',f'node-{c.id}'],'x':x,'y1':a.y,'y2':c.y,'length':L,'section':e.section,'self_weight_kNm':sw})
    col=COLUMNS[e.column_section]
    foundations=[]
    for c in [c for c in b.columns if c.active]:
        # Gross contact screen includes column self-weight and concrete pad weight, no overburden.
        axial=reactions[c.id]+col['kg_m']*b.height*9.80665/1000+e.footing_width**2*e.footing_thickness*24
        p=axial/e.footing_width**2
        status='missing_input' if e.soil.value is None else ('unsupported' if e.soil.basis!='gross allowable service' else ('pass' if p<=e.soil.value else 'fail'))
        foundations.append({'id':f'foundation-{c.id}','column_id':c.id,'reaction_kN':reactions[c.id],'gravity_service_kN':axial,'gross_load_kN':axial,'pressure_kPa':p,'allowable_kPa':e.soil.value,'status':status,'assumption':'Centered vertical service reaction; includes pad and illustrative column self-weight, excludes overburden'})
    alternatives=[]
    for id,catalog in CATALOG.items():
        max_ratio=0
        for beam in beams:
            L=beam['length'];trib=beam['tributary_width'];sw=catalog['kg_m']*9.80665/1000
            q=((e.dead.value+e.live.value)*trib+sw+beam['pv_kNm'])*1000
            uf=((e.dead.value*e.dead_factor+e.live.value*e.live_factor)*trib+(sw+beam['pv_kNm'])*e.dead_factor)*1000
            defl=5*q*L**4/(384*e.elastic_modulus*1e6*catalog['I'])*1000
            max_ratio=max(max_ratio,defl/(L*1000/e.deflection_ratio),(uf*L*L/8/catalog['Z']/1e6)/e.yield_strength)
        alternatives.append({'id':id,'label':catalog['label'],'kg_m':catalog['kg_m'],'max_utilization':max_ratio if beams else None,'status':'pass' if beams and not errors and max_ratio<=1 else 'fail'})
    return {'status':'unsupported' if errors else ('pass' if all(x['status']=='pass' for x in beams+foundations) else 'review'),'beams':beams,'girders':girders,'column_section':{'id':e.column_section,**col},'foundations':foundations,'alternatives':alternatives,'errors':errors,'section':s,'scope':'Gravity: independent simply supported roof beams under uniform vertical loads. Lateral: see the seismic frame analysis. No code certification.','load_mapping':{'D-roof':{'source':b.roof_id,'value_kPa':e.dead.value},'L-roof':{'source':b.roof_id,'value_kPa':e.live.value}}|({'D-pv':{'source':'solar-array','value_kPa':pv['dead_load_kPa'],'y_extent':pv['y_extent']}} if pv and pv['count'] else {}),'max_equilibrium_residual_N':max([abs(x['service']['vertical_residual_N']) for x in beams],default=0)}

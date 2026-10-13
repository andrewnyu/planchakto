"""Optional rooftop PV: array fit, superimposed roof load, and service/grid screens.
Regulatory limits are editable inputs whose sources travel with every result. Values that only the
distribution utility can supply (transformer rating, hosting capacity) stay missing until entered."""
import math
from .domain import Building

G=9.80665
# Standard overcurrent device ratings (PEC 2017 2.40.6, equivalent to NEC 240.6(A)); verify against IIEE text.
BREAKERS=[15,20,25,30,35,40,45,50,60,70,80,90,100,110,125,150,175,200,225,250,300,350,400,450,500,600,700,800,1000,1200]
SOURCES={
 'ocpd':'PEC 2017 Art. 6.90 (aligned with NEC 690): PV output conductors and overcurrent devices sized at not less than 125% of maximum circuit current. Quoted via secondary sources; verify against the IIEE PEC 2017 text.',
 'busbar':'NEC 705.12(B) load-side connection: main OCPD + 125% of inverter output current ≤ 120% of busbar rating, PV breaker at the opposite end. PEC 2017 wording not verified.',
 'netmeter':'RA 9513 §4 (distributed generation ≤ 100 kW); ERC Amended Net-Metering Rules (Res. 06 s.2019, Res. 15 s.2025). DOE DC2026-01-00012 (Apr 2026) reported to raise the non-residential cap to 1 MW or the contracted capacity, whichever is lower — secondary sources; verify.',
 'hosting':'ERC Res. 15 s.2025 requires distribution utilities to post hosting capacity per distribution transformer. Enter the DU-published value; it cannot be derived here.',
 'transformer':'Arithmetic screen: service demand and worst-case reverse power (full inverter output, zero on-site load) against the entered transformer rating. Not a Distribution Impact Study.',
}

def array_layout(b:Building):
    """Pack modules in the roof rectangle minus the edge setback; best of portrait/landscape, row-major from the south-west."""
    s=b.solar
    if not s.enabled:return None
    W,D=b.width-2*s.edge_setback,b.depth-2*s.edge_setback
    options=[]
    for orient,(mw,mh) in [('landscape',(s.module_length,s.module_width)),('portrait',(s.module_width,s.module_length))]:
        cols,rows=(max(0,math.floor(W/mw+1e-9)),max(0,math.floor(D/mh+1e-9))) if W>0 and D>0 else (0,0)
        options.append((cols*rows,orient,mw,mh,cols,rows))
    capacity,orient,mw,mh,cols,rows=max(options)
    wanted=capacity if s.target_kwp is None else math.ceil(round(s.target_kwp*1000/s.module_watts,9))
    count=min(capacity,wanted)
    modules=[{'id':f'pv-{i+1:02d}','x':s.edge_setback+(i%cols)*mw,'y':s.edge_setback+(i//cols)*mh,'w':mw,'h':mh} for i in range(count)]
    used_rows=math.ceil(count/cols) if cols else 0
    area=count*s.module_length*s.module_width
    load_kPa=(s.module_mass/(s.module_length*s.module_width)+s.racking_mass)*G/1000
    return {'modules':modules,'count':count,'capacity':capacity,'wanted':wanted,'orientation':orient,'kwp':count*s.module_watts/1000,
            'area_m2':area,'y_extent':[s.edge_setback,s.edge_setback+used_rows*mh] if count else None,'dead_load_kPa':load_kPa}

def analyze_solar(b:Building,structure,routing):
    s=b.solar;layout=array_layout(b)
    if layout is None:return {'enabled':False}
    checks=[]
    def add(rule,status,evidence,inputs=None):checks.append({'rule':rule,'status':status,'evidence':evidence,'inputs':inputs or {}})
    kwp=layout['kwp']
    if layout['count']==0:add('PV-ROOF','fail','No module fits inside the roof edge setback',{'edge_setback_m':s.edge_setback})
    elif layout['count']<layout['wanted']:add('PV-ROOF','fail',f"Roof fits {layout['capacity']} modules ({layout['capacity']*s.module_watts/1000:.2f} kWp); target needs {layout['wanted']}",{'target_kwp':s.target_kwp,'capacity':layout['capacity']})
    else:add('PV-ROOF','pass',f"{layout['count']} × {s.module_watts:g} W modules, {layout['orientation']}, {kwp:.2f} kWp in {layout['area_m2']:.1f} m²",{'edge_setback_m':s.edge_setback,'capacity':layout['capacity']})
    # Structure: PV dead load is already inside the beam analysis; report how much it moved utilization.
    pv_beams=[x for x in structure['beams'] if x.get('pv_kNm')]
    worst=max(pv_beams,key=lambda x:max(x['yield_utilization'],x['deflection_utilization']),default=None)
    if structure['errors'] or not structure['beams']:add('PV-LOAD','unsupported','Roof beam analysis unavailable; PV superimposed load not assessed')
    elif worst is None:add('PV-LOAD','not_applicable','No roof beam carries the array')
    else:
        u=max(worst['yield_utilization'],worst['deflection_utilization']);u0=worst['utilization_without_pv']
        add('PV-LOAD','pass' if all(x['status']=='pass' for x in pv_beams) else 'fail',f"PV adds {layout['dead_load_kPa']:.3f} kPa dead load; governing beam {worst['id']} utilization {u0:.2f} → {u:.2f}. Wind uplift and attachment not evaluated",{'pv_dead_kPa':layout['dead_load_kPa'],'beams_loaded':len(pv_beams)})
    add('PV-WIND','unsupported','Wind uplift on modules, racking and roof attachments is outside the supported analysis family')
    # Electrical
    inv=s.inverter_kw
    demand_W=sum(c['demand_W'] for c in routing['circuits'] if c['demand_W'] is not None)
    demand_missing=any(c['demand_W'] is None for c in routing['circuits'])
    electrical={'inverter_kw':inv,'dc_ac_ratio':kwp/inv if inv else None,'annual_kwh':kwp*s.peak_sun_hours*365*s.performance_ratio,'demand_kW':demand_W/1000,'output_current_A':None,'min_ocpd_A':None,'pv_breaker_A':None}
    if inv is None:
        for rule in ['PV-OCPD','PV-BUSBAR','PV-XFMR','PV-HOSTING']:add(rule,'missing_input','Inverter AC rating is required')
    else:
        current=inv*1000/(s.voltage*(math.sqrt(3) if s.phases==3 else 1));need=1.25*current
        breaker=next((x for x in BREAKERS if x>=need-1e-9),None)
        electrical.update(output_current_A=current,min_ocpd_A=need,pv_breaker_A=breaker)
        add('PV-OCPD','pass' if breaker else 'fail',f"Inverter {inv:g} kW → {current:.1f} A; ≥ {need:.1f} A required → {breaker} A breaker" if breaker else f'{need:.1f} A exceeds the modeled breaker list',{'phases':s.phases,'voltage':s.voltage})
        if s.service_main_a is None or s.busbar_a is None:add('PV-BUSBAR','missing_input','Main breaker and busbar ratings are required')
        else:
            lhs=s.service_main_a+need;rhs=1.2*s.busbar_a
            add('PV-BUSBAR','pass' if lhs<=rhs+1e-9 else 'fail',f"{s.service_main_a:g} A main + {need:.1f} A PV = {lhs:.1f} A vs 120% × {s.busbar_a:g} A = {rhs:.1f} A",{'main_A':s.service_main_a,'busbar_A':s.busbar_a})
        if s.transformer_kva is None:add('PV-XFMR','missing_input','Enter the serving transformer kVA (from the distribution utility or the owner-supplied transformer)')
        else:
            demand_kva=sum(c['demand_W']/c['power_factor'] for c in routing['circuits'] if c['demand_W'] is not None)/1000
            worst_flow=max(demand_kva,inv)
            status='missing_input' if demand_missing else ('pass' if worst_flow<=s.transformer_kva+1e-9 else 'fail')
            add('PV-XFMR',status,f"Demand {demand_kva:.2f} kVA; worst reverse flow {inv:g} kVA (full output, no on-site load) vs {s.transformer_kva:g} kVA rating",{'transformer_kva':s.transformer_kva,'demand_kva':demand_kva})
        if s.hosting_capacity_kw is None:add('PV-HOSTING','missing_input','Enter the DU-published hosting capacity for the serving transformer')
        else:add('PV-HOSTING','pass' if inv<=s.hosting_capacity_kw+1e-9 else 'fail',f"Inverter {inv:g} kW vs {s.hosting_capacity_kw:g} kW hosting capacity",{'hosting_capacity_kw':s.hosting_capacity_kw})
    if s.customer_class=='residential':cap=100.
    else:cap=None if s.contracted_kw is None else min(1000.,s.contracted_kw)
    if cap is None:add('PV-NETMETER','missing_input','Non-residential cap depends on contracted capacity; enter it')
    else:add('PV-NETMETER','pass' if kwp<=cap+1e-9 else 'fail',f"{kwp:.2f} kWp DC vs {cap:g} kW net-metering cap ({s.customer_class.replace('_','-')}); DC basis is conservative where the DU has not clarified DC vs AC",{'cap_kw':cap,'customer_class':s.customer_class})
    return {'enabled':True,'layout':layout,'electrical':electrical,'checks':checks,'sources':SOURCES,
            'scope':'Array fit, superimposed dead load on the supported roof beams, and arithmetic service/grid screens. Not string sizing, DC protection, rapid shutdown, wind uplift, or a Distribution Impact Study.'}

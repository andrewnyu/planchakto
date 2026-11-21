"""Bounded deterministic screens for approved polygon designs; no implicit criteria."""
from __future__ import annotations
import math,heapq
from collections import Counter
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from shapely.prepared import prep
from .planning_models import Finding,EngineeringInputs,Programme
from .planning_details import quantities
from .domain import digest


def confirmed(v):return v.source!='proposal' and v.basis.strip() not in ('','Not supplied','Not priced')
def supplied(v):return v.value is not None and confirmed(v)


def wall_barriers(plan,details):
    walls=unary_union([Polygon(z.polygon).boundary for z in plan.zones if z.location=='inside' and z.enclosed]+[Polygon(r.polygon).boundary for r in details.rooms])
    # Flat ends preserve each drawn opening's width rather than extending it past the jambs.
    doors=unary_union([LineString(o.segment).buffer(.08,cap_style=2) for o in plan.openings]+[LineString(r.door).buffer(.08,cap_style=2) for r in details.rooms])
    return walls.difference(doors).buffer(.03)

def programme_findings(programme,plan,details=None):
    out=[]
    def add(id,status,title,evidence,**kw):out.append(Finding(id=id,discipline='programme',status=status,title=title,evidence=evidence,**kw).model_dump())
    def area(id,name,actual,target,mode):
        if target is None:add(id,'missing_input',name,'No area target was confirmed.');return
        ok={'target':abs(actual-target)<=max(.5,target*.05),'minimum':actual>=target-.05,'maximum':actual<=target+.05,'exact':abs(actual-target)<=.05}[mode]
        add(id,'pass' if ok else 'warning' if mode=='target' else 'fail',name,f'{actual:,.2f} m² drawn; {mode} {target:,.2f} m².',values={'actual':round(actual,3),'required':target,'mode':mode})
    area('programme-area','Building area',Polygon(plan.footprint).area,programme.total_area_m2,programme.area_mode)
    known={r.id for r in programme.requirements}
    for z in plan.zones:
        if set(z.requirement_ids)-known:add('unknown-'+z.id,'fail','Unknown programme binding',f'{z.name} references a requirement outside the confirmed programme.')
    if details:
        for q in details.rooms+details.items:
            if q.requirement_id and q.requirement_id not in known:add('unknown-'+q.id,'fail','Unknown programme binding',f'{q.name} references a requirement outside the confirmed programme.')
    allocations={}
    for r in programme.requirements:
        rooms=[Polygon(q.polygon) for q in (details.rooms if details else []) if q.requirement_id==r.id]
        # Detailed rooms refine a same-requirement allocation; its envelope is not extra room area.
        allocations[r.id]=rooms+[Polygon(z.polygon) for z in plan.zones if r.id in z.requirement_ids and not any(Polygon(z.polygon).covers(q) for q in rooms)]
    for r in programme.requirements:
        bound=[z for z in plan.zones if r.id in z.requirement_ids]
        rooms=[q for q in (details.rooms if details else []) if q.requirement_id==r.id]
        if not bound and not rooms:add('requirement-'+r.id,'warning' if not details else 'fail',r.name,'No drawn space is bound to this requirement.');continue
        included={r.id}
        while True:
            more=included|{child.id for child in programme.requirements if child.included_in in included}
            if more==included:break
            included=more
        actual=unary_union([p for id in included for p in allocations[id]]).area
        area('requirement-'+r.id,r.name,actual,r.area_m2*r.count if r.area_m2 is not None else None,r.area_mode)
        # A room inside a zone bound to the same requirement is refinement, not another space.
        count=len(allocations[r.id])
        if count<r.count:add('count-'+r.id,'fail',r.name,f'{count} distinct spaces placed; {r.count} requested.')
    if details:
        counts=Counter(i.kind for i in details.items)
        for key,actual,target in [('parking',counts['parking']+counts['accessible_parking'],programme.parking_spaces),('accessible_parking',counts['accessible_parking'],programme.accessible_spaces),('cashiers',counts['cashier'],programme.cashier_counters)]:
            if target is None:continue
            add('capacity-'+key,'pass' if actual>=target else 'fail',key.replace('_',' ').title(),f'{actual} placed; {target} confirmed minimum.',values={'actual':actual,'required':target})
        for i,w in enumerate(details.warnings):add(f'placement-{i}','warning','Unresolved placement',w)
    return out


def travel_screen(plan,details):
    """Conservative finite grid route distances, excluding walls, racks and closed rooms."""
    shell=Polygon(plan.footprint);step=max(.35,math.sqrt(shell.area/18000))
    exits=[o for o in plan.openings if o.to_zone=='outside' and o.kind!='loading']
    if not exits:return {'status':'fail','max_distance_m':None,'unreachable':[],'basis':'No drawn customer/pedestrian exit; loading openings excluded.'}
    barriers=wall_barriers(plan,details)
    obstacles=unary_union([Polygon(i.polygon).buffer(.05) for i in details.items if Polygon(i.polygon).intersects(shell)]+[barriers])
    free=shell.difference(obstacles);prepared=prep(free);x0,y0,x1,y1=shell.bounds
    nx=math.ceil((x1-x0)/step);ny=math.ceil((y1-y0)/step);nodes={}
    for iy in range(ny):
        for ix in range(nx):
            p=(x0+(ix+.5)*step,y0+(iy+.5)*step)
            if prepared.covers(Point(p)):nodes[ix,iy]=p
    distance={};heap=[]
    for e in exits:
        line=LineString(e.segment)
        for key,p in nodes.items():
            d=Point(p).distance(line)
            # A generous buffer here would heal the thin wall barriers and seed a closed room.
            if d<=step*1.6 and free.buffer(1e-7).covers(LineString([p,line.interpolate(line.project(Point(p)))])):
                distance[key]=d;heapq.heappush(heap,(d,key))
    while heap:
        d,key=heapq.heappop(heap)
        if d!=distance[key]:continue
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]:
            k=(key[0]+dx,key[1]+dy)
            if k not in nodes:continue
            nd=d+step*math.hypot(dx,dy)
            if nd>=distance.get(k,float('inf')):continue
            if not prepared.covers(LineString([nodes[key],nodes[k]])):continue
            distance[k]=nd;heapq.heappush(heap,(nd,k))
    unreachable=[];maximum=0
    spaces=[z for z in plan.zones if z.location=='inside']+list(details.rooms)
    for z in spaces:
        p=prep(Polygon(z.polygon));keys=[k for k,v in nodes.items() if p.covers(Point(v))]
        if not keys or any(k not in distance for k in keys):unreachable.append(z.id)
        maximum=max(maximum,max((distance[k] for k in keys if k in distance),default=0))
    return {'status':'fail' if unreachable or not distance else 'measured','max_distance_m':maximum if distance else None,'unreachable':unreachable,'grid_step_m':round(step,3),'basis':'Eight-direction finite grid centreline paths around drawn objects/walls through drawn doors, not a statutory travel-distance determination. Narrow passages smaller than the grid may be missed; no accessibility or smoke simulation.'}


def run_checks(programme,plan,details,inputs,design_hash):
    findings=programme_findings(programme,plan,details)
    def add(id,discipline,status,title,evidence,**kw):findings.append(Finding(id=id,discipline=discipline,status=status,title=title,evidence=evidence,**kw).model_dump())
    def missing(id,discipline,title,fields):
        absent=[k for k,v in fields.items() if not supplied(v)]
        if absent:add(id,discipline,'missing_input',title,'Supply confirmed values and their basis: '+', '.join(absent));return True
        return False
    route_results=[];shell=Polygon(plan.footprint);barriers=wall_barriers(plan,details)
    for a in details.recipe.arrays:
        criterion=inputs.criteria.min_parking_aisle if a.kind in ('parking','accessible_parking') else inputs.criteria.min_staff_aisle if next(z for z in plan.zones if z.id==a.zone_id).kind=='storage' else inputs.criteria.min_customer_aisle
        clearances=[a.access_clearance]
        if a.rows>1 and a.access_side in ('front','back'):clearances.append(a.gap_y)
        if a.columns>1 and a.access_side in ('left','right'):clearances.append(a.gap_x)
        minimum=min(clearances)
        add('array-clearance-'+a.id,'circulation','missing_input' if not supplied(criterion) else 'pass' if minimum>=criterion.value else 'fail',a.name+' nominal clearances',f'Minimum nominal recipe clearance {minimum:g} m. '+(f'Supplied criterion {criterion.value:g} m.' if supplied(criterion) else 'Required aisle criterion is missing.')+' This is a dimension comparison, not accessible-route or operating clearance certification.',objects=[i.id for i in details.items if i.id.startswith(a.id+'-')],values={'minimum_nominal_clearance_m':minimum})
    for r in details.routes:
        line=LineString(r.points);envelope=line.buffer(r.width/2,cap_style=2,join_style=2)
        obstacles=[i.id for i in details.items if envelope.intersection(Polygon(i.polygon)).area>.01]
        if envelope.intersection(barriers).area>.001:obstacles+=['enclosed-walls']
        if r.kind in ('customer','service','customer_vehicle','service_vehicle') and envelope.intersection(shell).area>.05:obstacles+=['building']
        elif r.kind in ('interior','egress') and not shell.buffer(.001).covers(envelope):obstacles+=['outside-building']
        criterion=inputs.criteria.min_parking_aisle if r.kind in ('customer','service','customer_vehicle','service_vehicle') else inputs.criteria.min_customer_aisle
        status='fail' if obstacles else 'missing_input' if not supplied(criterion) else 'pass' if r.width>=criterion.value else 'fail'
        add('route-'+r.id,'circulation',status,r.name,f'Drawn width {r.width:g} m; '+('clashes with '+', '.join(obstacles[:8]) if obstacles else f'required width {criterion.value:g} m.' if supplied(criterion) else 'minimum width criterion missing.'),objects=[r.id]+obstacles,values={'width_m':r.width,'length_m':round(line.length,2)})
        route_results.append({'id':r.id,'length_m':round(line.length,2),'width_m':r.width,'collisions':obstacles})
        if r.vehicle_id:
            vehicle=next((v for v in inputs.vehicles if v.id==r.vehicle_id),None)
            add('vehicle-'+r.id,'traffic','missing_input' if not vehicle or vehicle.min_turn_radius is None else 'not_checked',r.name+' turning', 'Supply a design vehicle with minimum turn radius.' if not vehicle or vehicle.min_turn_radius is None else 'Vehicle dimensions are recorded. Articulated swept paths and steering kinematics require a specialist traffic model.',objects=[r.id])
    for i,a in enumerate(details.routes):
        for b in details.routes[i+1:]:
            if a.kind!=b.kind and LineString(a.points).buffer(a.width/2).intersects(LineString(b.points).buffer(b.width/2)):
                add('crossing-'+a.id+'-'+b.id,'traffic','warning','Circulation envelopes cross',f'{a.name} and {b.name} overlap. Resolve timing, priority and pedestrian protection.',objects=[a.id,b.id])
    travel=travel_screen(plan,details)
    add('route-reachability','fire',travel['status'] if travel['status']=='fail' else 'pass','Drawn exit reachability',travel['basis']+' Unreachable zones: '+(', '.join(travel['unreachable']) or 'none at this grid resolution'),objects=travel['unreachable'],values=travel)
    if not missing('travel','fire','Travel-distance screen',{'max_egress_travel':inputs.criteria.max_egress_travel}):
        d=travel['max_distance_m'];add('travel','fire','fail' if travel['status']=='fail' else 'missing_input' if d is None else 'pass' if d<=inputs.criteria.max_egress_travel.value else 'fail','Travel-distance screen',('No complete route to a drawn exit exists for all sampled zones. ' if travel['status']=='fail' else '')+f'Maximum reachable grid route {d if d is None else round(d,2)} m; supplied limit {inputs.criteria.max_egress_travel.value:g} m. '+travel['basis'])
    if not inputs.occupancy:add('occupancy','fire','missing_input','Occupancy','Supply the occupancy and a professional fire strategy; room names do not establish classification.')
    if not missing('occupants','fire','Occupant and exit-width arithmetic',{'occupant_area_factor':inputs.criteria.occupant_area_factor,'exit_width_per_person_mm':inputs.criteria.exit_width_per_person_mm}):
        factor=inputs.criteria.occupant_area_factor.value;occupants=math.ceil(shell.area/factor);required=occupants*inputs.criteria.exit_width_per_person_mm.value/1000
        width=unary_union([LineString(o.segment) for o in plan.openings if o.to_zone=='outside' and o.kind!='loading']).length
        add('occupants','fire','pass' if width>=required else 'fail','Occupant and exit-width arithmetic',f'{occupants} persons at supplied {factor:g} m²/person; {width:.2f} m unique drawn exit width vs {required:.2f} m required. Mixed occupancies, door hardware, exit independence and discharge are not checked.',values={'occupants':occupants,'drawn_width_m':width,'required_width_m':required})
    if not missing('doors','fire','Door-width screen',{'minimum_door_width':inputs.criteria.min_door_width}):
        doors=[(o.id,LineString(o.segment).length) for o in plan.openings if o.kind=='door']+[(r.id,LineString(r.door).length) for r in details.rooms]
        narrow=[id for id,w in doors if w<inputs.criteria.min_door_width.value]
        add('doors','fire','missing_input' if not doors else 'fail' if narrow else 'pass','Door-width screen',f'{len(doors)} drawn door widths measured; {len(narrow)} below the supplied minimum. '+('No doors are drawn; supply door geometry. ' if not doors else '')+'Clear opening and hardware unverified.',objects=narrow)
    if inputs.structural_model!='simply_supported_steel_roof_bay':add('roof-bay','structure','missing_input' if inputs.structural_model=='not_selected' else 'unsupported','Roof-bay component model','Select the supported simply-supported steel roof-bay model or obtain a specialist model for the selected system.')
    else:
        keys=['bay_span','tributary_width','dead_kpa','live_kpa','elastic_modulus_mpa','yield_strength_mpa','dead_factor','live_factor','deflection_ratio']
        absent=missing('roof-bay','structure','Roof-bay component screen',{k:getattr(inputs,k) for k in keys})
        if inputs.beam_self_weight is None:
            add('beam-self-weight' if absent else 'roof-bay','structure','missing_input','Roof-beam self-weight','Confirm whether the supplied dead load includes beam self-weight or add the selected section weight.');absent=True
        if inputs.beam_section is None:add('section','structure','missing_input','Roof-beam section','Select an explicitly specified RHS section.')
        if not absent and inputs.beam_section:
            from .structure import beam_fem,CATALOG
            p={k:getattr(inputs,k).value for k in keys};section=CATALOG[inputs.beam_section];L=p['bay_span'];w=p['tributary_width']
            # Catalogue mass times standard gravity gives N/m, included only by explicit selection.
            self_weight=section['kg_m']*9.80665 if inputs.beam_self_weight=='add_section_weight' else 0
            q=(p['dead_kpa']*p['dead_factor']+p['live_kpa']*p['live_factor'])*w*1000+self_weight*p['dead_factor']
            result=beam_fem(L,p['elastic_modulus_mpa']*1e6,section['I'],q);service=beam_fem(L,p['elastic_modulus_mpa']*1e6,section['I'],(p['dead_kpa']+p['live_kpa'])*w*1000+self_weight)
            stress=result['max_moment_kNm']*1000/section['Z']/1e6;deflection=service['max_deflection_mm'];limit=L*1000/p['deflection_ratio']
            add('roof-bay','structure','pass' if stress<=p['yield_strength_mpa'] and deflection<=limit else 'fail','Roof-bay component screen',f'Elastic bending stress {stress:.2f} MPa vs supplied yield {p["yield_strength_mpa"]:g} MPa; service deflection {deflection:.2f} mm vs L/{p["deflection_ratio"]:g} ({limit:.2f} mm). Self-weight: {inputs.beam_self_weight}; added {self_weight/1000:.4f} kN/m using catalogue kg/m × 9.80665 m/s². Representative isolated beam only; no shear, member stability, connections or full-building load path.',values={'stress_mpa':stress,'deflection_mm':deflection,'deflection_limit_mm':limit,'added_self_weight_kn_m':self_weight/1000,'service_line_load_kn_m':(p['dead_kpa']+p['live_kpa'])*w+self_weight/1000,'factored_line_load_kn_m':q/1000,'solver':result})
    if not missing('bearing','structure','Supplied-load average bearing',{'footing_load_kn':inputs.footing_load_kn,'footing_width':inputs.footing_width,'soil_kpa':inputs.soil_kpa}):
        pressure=inputs.footing_load_kn.value/inputs.footing_width.value**2
        add('bearing','structure','pass' if pressure<=inputs.soil_kpa.value else 'fail','Supplied-load average bearing',f'Supplied load / square footing area = {pressure:.2f} kPa; supplied comparison limit {inputs.soil_kpa.value:g} kPa. Arithmetic only: gross/net basis compatibility and completeness of the service load are unverified. Footing self-weight, overburden, settlement, eccentricity, sliding and reinforced-concrete design are not calculated.',values={'pressure_kpa':pressure})
    wires=[];panels=[p for p in inputs.utilities if p.kind=='panel' and confirmed(p)]
    for load in inputs.loads:
        zone=next((z for z in plan.zones if z.id==load.zone_id),None)
        if zone and panels:
            point=Polygon(zone.polygon).representative_point();panel=min(panels,key=lambda p:point.distance(Point(p.point)))
            wires.append({'load':load.id,'circuit':load.circuit,'panel':panel.id,'points':[tuple(point.coords[0]),panel.point],'basis':'Indicative zone-to-panel straight connection, not cable routing or length takeoff'})
    if inputs.loads and not panels:add('panel-input','electrical','missing_input','Electrical connection point','Supply a verified panel point. Load arithmetic alone does not establish connectivity or supply capacity.')
    for c in inputs.circuits:
        loads=[l for l in inputs.loads if l.circuit==c.id];fields={'voltage':c.voltage,'power_factor':c.power_factor,'demand_factor':c.demand_factor,**{l.id:l.watts for l in loads}}
        if c.phases is None:add('circuit-phase-'+c.id,'electrical','missing_input',c.id+' supply phases','Select the verified single- or three-phase supply before calculating current.');continue
        if not loads:add('circuit-'+c.id,'electrical','missing_input',c.id,'No loads are assigned.');continue
        if missing('circuit-'+c.id,'electrical',c.id,fields):continue
        watts=sum(l.watts.value*l.quantity for l in loads);demand=watts*c.demand_factor.value;amps=demand/(c.voltage.value*c.power_factor.value*(math.sqrt(3) if c.phases==3 else 1))
        add('circuit-'+c.id,'electrical','pass',c.id+' load arithmetic',f'{watts:.1f} W connected, {demand:.1f} W demand, {amps:.2f} A calculated. Cable sizing, protection, diversity suitability and supply capacity are not checked.',values={'connected_w':watts,'demand_w':demand,'current_a':amps})
    if not inputs.circuits:add('electrical-inputs','electrical','missing_input','Electrical loads','Supply loads, circuit assignments, voltage, power factor and demand factor.')
    wet=[i for i in details.items if i.kind in ('wc','urinal','basin','sink','shower')];drains=[p for p in inputs.utilities if p.kind=='drain' and confirmed(p)];pipes=[];pipe_lengths=[]
    if wet and drains:
        for fixture in wet:
            start=Polygon(fixture.polygon).centroid;drain=min(drains,key=lambda p:start.distance(Point(p.point)));length=start.distance(Point(drain.point));pipe_lengths.append(length);pipes.append({'fixture':fixture.id,'utility':drain.id,'points':[list(start.coords)[0],drain.point],'length_m':round(length,3)})
        if not missing('gravity','plumbing','Indicative drainage fall',{'drain_fall':inputs.drain_fall,'drain_slope':inputs.drain_slope}):
            required=max(pipe_lengths)*inputs.drain_slope.value
            add('gravity','plumbing','pass' if inputs.drain_fall.value>=required else 'fail','Indicative drainage fall',f'Longest direct line requires {required:.3f} m fall; supplied {inputs.drain_fall.value:g} m. Straight connections only; buildable routing, fittings, invert levels and pipe capacity are not checked.',values={'required_fall_m':required})
    else:add('plumbing-inputs','plumbing','missing_input','Plumbing connections','Place wet fixtures and supply a verified drain point. Fixture demand and water supply sizing remain unverified.')
    takeoff=quantities(plan,details,inputs)
    if supplied(inputs.budget) and takeoff['total_cost_php'] is not None:add('budget','cost','pass' if takeoff['total_cost_php']<=inputs.budget.value else 'fail','Modelled-scope budget',f'Modelled subtotal PHP {takeoff["total_cost_php"]:,.2f}; budget PHP {inputs.budget.value:,.2f}. Exclusions remain outside this arithmetic.')
    else:add('budget','cost','missing_input','Budget comparison','A complete priced modelled scope and a supplied budget are required. Partial priced subtotal is not a project estimate.')
    for id,discipline,title in [('global-structure','structure','Whole-building structural system, seismic and wind'),('fire-strategy','fire','Statutory fire strategy, suppression and access'),('accessible','accessibility','Accessible routes, toilets and statutory parking'),('vehicle-sweep','traffic','Vehicle swept paths and traffic capacity'),('electrical-design','electrical','Electrical protection, conductor and supply design'),('plumbing-design','plumbing','Water demand, drainage sizing and invert coordination'),('civil','civil','Flood, grading, earthworks and stormwater')]:add(id,discipline,'unsupported',title,'This planning engine does not implement this analytical family. Licensed professional review is required.')
    result={'schema_version':'planning-1','design_hash':design_hash,'inputs_hash':digest(inputs),'findings':findings,'summary':dict(Counter(f['status'] for f in findings)),'travel':travel,'routes':route_results,'pipes':pipes,'wires':wires,'quantities':takeoff,'coverage':{'checked':['Programme arithmetic','Object placement and route envelopes','Grid exit reachability','Supplied-criterion arithmetic','Explicitly selected component screens'],'not_checked':[f['title'] for f in findings if f['status'] in ('unsupported','not_checked','missing_input')]}}
    result['result_hash']=digest(result);return result

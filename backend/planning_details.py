"""Compile model-selected fit-out recipes into measured, collision-free objects."""
from math import ceil,floor
from shapely.geometry import Polygon,LineString,box
from shapely.affinity import rotate,translate
from shapely.strtree import STRtree
from .concepts import DesignPlan,SitePlan
from .planning_models import DetailRecipe,DetailedPlan,Item,SupportRoom

def coords(p):return [(round(x,5),round(y,5)) for x,y in list(p.exterior.coords)[:-1]]

class CollisionIndex:
    def __init__(self,polygons=()):self.polygons=list(polygons);self.tree=None;self.indexed=0
    def add(self,p):self.polygons.append(p)
    def clashes(self,p):
        if len(self.polygons)-self.indexed>=64:
            self.tree=STRtree(self.polygons);self.indexed=len(self.polygons)
        candidates=[self.polygons[int(i)] for i in self.tree.query(p)] if self.tree is not None else []
        return any(p.intersection(q).area>.001 for q in candidates+self.polygons[self.indexed:])

def compile_details(plan:DesignPlan,recipe:DetailRecipe,site:SitePlan|None=None)->DetailedPlan:
    from .planning_routes import resolve_route
    recipe=recipe.model_copy(deep=True)
    recipe.routes=[resolve_route(r,plan.footprint if r.kind in ('interior','egress') else site.boundary if site else plan.footprint,[Polygon(plan.footprint)] if site and r.kind in ('customer','service','customer_vehicle','service_vehicle') else []) for r in recipe.routes]
    zones={z.id:Polygon(z.polygon) for z in plan.zones};items=[];rooms=[];warnings=list(recipe.unplaced);occupied=[]
    ids=[a.id for a in recipe.arrays]+[r.id for pack in recipe.support_packs for r in pack.rooms]
    if len(ids)!=len(set(ids)):raise ValueError('Fit-out recipe identifiers must be unique')
    if sum(a.rows*a.columns for a in recipe.arrays)>10000:raise ValueError('Use at most 10,000 detailed objects per plan')
    route_ids=[r.id for r in recipe.routes]
    if len(route_ids)!=len(set(route_ids)):raise ValueError('Route identifiers must be unique')
    for route in recipe.routes:
        line=LineString(route.points)
        if line.length<.1 or not line.is_simple:raise ValueError(f'{route.name}: use a non-self-crossing route with positive length')
        envelope=line.buffer(route.width/2,cap_style=2,join_style=2)
        if site and not Polygon(site.boundary).buffer(.01).covers(envelope):raise ValueError(f'{route.name}: route envelope leaves the confirmed site')
        if route.kind in ('interior','egress') and not Polygon(plan.footprint).buffer(.01).covers(envelope):raise ValueError(f'{route.name}: interior route leaves the building')
        if route.kind in ('customer','service','customer_vehicle','service_vehicle') and envelope.intersection(Polygon(plan.footprint)).area>.05:raise ValueError(f'{route.name}: kind={route.kind} is a VEHICLE route and clashes with the building. Use kind=pedestrian or interior for walking routes; vehicle routes must remain outside.')
    # Preserve a real clear approach at each drawn threshold; arrays cannot cover a door.
    thresholds=[LineString(o.segment).buffer(.65,cap_style=2) for o in plan.openings]
    route_shapes=[LineString(r.points).buffer(r.width/2,cap_style=2,join_style=2) for r in recipe.routes]
    for pack in recipe.support_packs:
        if pack.zone_id not in zones:raise ValueError('Support pack references an unknown zone')
        zone=zones[pack.zone_id];x0,y0,x1,y1=zone.bounds;x=x0+.15;y=y0+pack.hallway_width;row_depth=0
        for r in pack.rooms:
            if x+r.width>x1-.15:x=x0+.15;y+=row_depth+pack.hallway_width;row_depth=0
            p=box(x,y,x+r.width,y+r.depth);door=LineString([(x+.2,y),(x+min(1.2,r.width-.1),y)])
            if not zone.buffer(.0001).covers(p) or any(p.intersection(o).area>.001 for o in occupied+thresholds+route_shapes):
                warnings.append(f'{r.name}: support room did not fit; enlarge or relocate its parent zone.');continue
            rooms.append(SupportRoom(id=r.id,zone_id=pack.zone_id,name=r.name,kind=r.kind,polygon=coords(p),door=tuple(door.coords),requirement_id=r.requirement_id));occupied.append(p)
            for j,kind in enumerate(r.fixtures):
                fw,fd=(.65,.8) if kind in ('wc','urinal','basin','sink','shower') else (.6,1.0)
                fx=x+.2+j*(fw+.15);fy=y+r.depth-fd-.15
                q=box(fx,fy,fx+fw,fy+fd)
                if not p.buffer(-.05).covers(q):warnings.append(f'{r.name}: {kind} fixture was not placed.');continue
                items.append(Item(id=f'{r.id}-{kind}-{j+1}',zone_id=pack.zone_id,room_id=r.id,kind=kind,name=f'{r.name} / {kind}',polygon=coords(q),basis=pack.basis))
            x+=r.width+.15;row_depth=max(row_depth,r.depth)
    collisions=CollisionIndex(occupied);reserved=CollisionIndex(thresholds+route_shapes);access_index=CollisionIndex();spacing_index=CollisionIndex();parking_count=0;cashier_count=0
    for a in recipe.arrays:
        if a.zone_id not in zones:raise ValueError(f'{a.name}: unknown zone {a.zone_id}')
        zone=zones[a.zone_id];local=rotate(zone,-a.angle,origin=(0,0));x0,y0,x1,y1=local.bounds
        if a.origin:
            from shapely.geometry import Point
            origin=rotate(Point(a.origin),-a.angle,origin=(0,0));ox,oy=origin.x,origin.y
        else:ox,oy=x0+a.edge_margin+(a.access_clearance if a.access_side=='left' else 0),y0+a.edge_margin+(a.access_clearance if a.access_side=='front' else 0)
        rows,columns=a.rows,a.columns
        filling=getattr(a,'packing','grid')=='fill';requested=getattr(a,'target_count',None) or (rows*columns if not filling else None)
        step_x,step_y=a.item_width+a.gap_x,a.item_depth+a.gap_y
        if filling:
            step_x=step_y=max(.25,((x1-x0)*(y1-y0)/80000)**.5)
            rows=max(0,floor((y1-a.edge_margin-oy-a.item_depth)/step_y)+1);columns=max(0,floor((x1-a.edge_margin-ox-a.item_width)/step_x)+1)
            if rows*columns>100000:raise ValueError(f'{a.name}: use larger dimensions or a smaller packing region; the search is too large')
            a.rows=max(1,min(rows,100));a.columns=max(1,min(columns,200))
        placed=0
        for row in range(rows):
            for col in range(columns):
                if requested is not None and placed>=requested:break
                if len(items)>=10000:raise ValueError('A detailed plan is limited to 10,000 placed objects')
                x=ox+col*step_x;y=oy+row*step_y
                p=rotate(box(x,y,x+a.item_width,y+a.item_depth),a.angle,origin=(0,0))
                spacing=rotate(box(x-a.gap_x/2,y-a.gap_y/2,x+a.item_width+a.gap_x/2,y+a.item_depth+a.gap_y/2),a.angle,origin=(0,0))
                c=a.access_clearance
                ab={'front':(x,y-c,x+a.item_width,y),'back':(x,y+a.item_depth,x+a.item_width,y+a.item_depth+c),'left':(x-c,y,x,y+a.item_depth),'right':(x+a.item_width,y,x+a.item_width+c,y+a.item_depth)}[a.access_side]
                access=rotate(box(*ab),a.angle,origin=(0,0)) if c else None
                if not zone.buffer(.0001).covers(p) or (access is not None and not zone.buffer(.0001).covers(access)):continue
                if collisions.clashes(p) or reserved.clashes(p):continue
                if access is not None and collisions.clashes(access):continue
                if access_index.clashes(p):continue
                if spacing_index.clashes(spacing):continue
                name=f'{a.name} {placed+1}'
                if a.kind in ('parking','accessible_parking'):parking_count+=1;name=f'Bay {parking_count}'
                if a.kind=='cashier':cashier_count+=1;name=f'Cashier {cashier_count}'
                items.append(Item(id=f'{a.id}-{row+1}-{col+1}',zone_id=a.zone_id,kind=a.kind,name=name,polygon=coords(p),access_polygon=coords(access) if access is not None else [],requirement_id=a.requirement_id,source=a.source,basis=a.basis));collisions.add(p)
                if access is not None:access_index.add(access)
                spacing_index.add(spacing)
                placed+=1
        if requested is not None and placed<requested:warnings.append(f'{a.name}: placed {placed} of {requested}; the rest clash with boundaries, openings, routes or objects.')
    return DetailedPlan(title=recipe.title,recipe=recipe,items=items,rooms=rooms,routes=recipe.routes,warnings=warnings[:100])

def quantities(plan,details,inputs):
    """Geometric takeoff, never a fabricated whole-building bill of materials."""
    rows=[];rates={r.id:r for r in inputs.rates}
    def add(id,name,unit,quantity,formula,objects):
        rate=rates.get(id);priced=rate is not None and rate.rate is not None and rate.source!='proposal' and rate.basis.strip() not in ('','Not priced')
        rows.append(dict(id=id,name=name,unit=unit,quantity=round(quantity,4) if quantity is not None else None,formula=formula,source_ids=objects,rate=rate.rate if priced else None,rate_source=rate.source if rate else None,rate_basis=rate.basis if rate else 'Not supplied',cost_php=round(quantity*rate.rate,2) if quantity is not None and priced else None))
    usable=lambda v:v.value is not None and v.source!='proposal' and v.basis.strip() not in ('','Not supplied')
    shell=Polygon(plan.footprint);add('floor_area','Building floor area','m²',shell.area,'Area of accepted footprint',['footprint'])
    add('slab','Floor slab concrete','m³',shell.area*inputs.slab_thickness.value if usable(inputs.slab_thickness) else None,'Footprint × supplied slab thickness; excludes foundations/reinforcement',['footprint'])
    wall=shell.boundary
    from shapely.ops import unary_union
    partitions=[Polygon(z.polygon).boundary for z in plan.zones if z.location=='inside' and z.enclosed]+[Polygon(r.polygon).boundary for r in details.rooms]
    wall=unary_union([wall]+partitions)
    openings=unary_union([LineString(o.segment) for o in plan.openings]+[LineString(r.door) for r in details.rooms])
    net_length=wall.difference(openings.buffer(.001,cap_style=2)).length
    add('wall','Wall face allowance','m²',net_length*inputs.height.value if usable(inputs.height) else None,'Unique enclosed-wall length less drawn openings × supplied wall height; full-height opening deduction',['footprint']+[r.id for r in details.rooms])
    for kind in sorted({i.kind for i in details.items}):
        selected=[i for i in details.items if i.kind==kind];add('item_'+kind,kind.replace('_',' ').title(),'each',len(selected),'Count of placed objects',[i.id for i in selected])
    for route in details.routes:add('route_'+route.id,route.name,'m',LineString(route.points).length,'Drawn centreline length',[route.id])
    total=sum(r['cost_php'] for r in rows if r['cost_php'] is not None);complete=all(r['cost_php'] is not None for r in rows)
    return dict(items=rows,partial_cost_php=round(total,2),total_cost_php=round(total,2) if complete else None,unpriced=[r['id'] for r in rows if r['cost_php'] is None],exclusions=['Whole-building structural steel and reinforcement','Foundations other than supplied geometric allowances','MEP sizing, equipment selection and installation','Civil works, earthworks, drainage design and flood protection','Taxes, labour allowances, contingencies and professional fees unless explicitly priced in a separate estimate'])

from __future__ import annotations
import heapq, math
from shapely.geometry import box, LineString, Point
from shapely.ops import unary_union
from .domain import Building

def simplify(points):
    result=[]
    for p in points:
        if result and p==result[-1]:continue
        if len(result)>=2:
            a,c=result[-2],result[-1]
            if abs((c[0]-a[0])*(p[1]-c[1])-(c[1]-a[1])*(p[0]-c[0]))<1e-8:result.pop()
        result.append(p)
    return result

def length(points):return sum(math.dist(a,c) for a,c in zip(points,points[1:]))

def blocked(points,obstacles):
    return len(points)>1 and any(LineString([a,c]).intersects(obstacles) for a,c in zip(points,points[1:]) if a!=c)

def astar(start,end,obstacles,bounds,step=.25):
    """Four-connected A*, physical segment checks include snapped endpoint connectors."""
    sx,sy=(round(v/step) for v in start);ex,ey=(round(v/step) for v in end)
    s=(sx,sy);goal=(ex,ey);lo_x,lo_y,hi_x,hi_y=bounds
    xy=lambda p:(p[0]*step,p[1]*step)
    if blocked([start,xy(s)],obstacles) or blocked([xy(goal),end],obstacles):return None
    if Point(start).intersects(obstacles) or Point(end).intersects(obstacles):return None
    queue=[(0,0,s)];cost={s:0};parent={};done=set()
    while queue:
        _,g,p=heapq.heappop(queue)
        if p in done:continue
        if p==goal:
            path=[p]
            while p in parent:p=parent[p];path.append(p)
            result=simplify([start]+[xy(v) for v in reversed(path)]+[end])
            return result if not blocked(result,obstacles) else None
        done.add(p)
        for dx,dy in [(1,0),(0,1),(-1,0),(0,-1)]:
            nxt=(p[0]+dx,p[1]+dy);x,y=xy(nxt)
            if not (lo_x<=x<=hi_x and lo_y<=y<=hi_y) or nxt in done:continue
            if LineString([xy(p),(x,y)]).intersects(obstacles):continue
            ng=g+1
            if ng<cost.get(nxt,float('inf')):
                cost[nxt]=ng;parent[nxt]=p;heapq.heappush(queue,(ng+abs(nxt[0]-ex)+abs(nxt[1]-ey),ng,nxt))
    return None

def obstacle_geometry(b):
    objects=[{'id':c.id,'x':c.x-.2,'y':c.y-.2,'w':.4,'h':.4} for c in b.columns if c.active]+[o.model_dump() for o in b.obstacles]
    # 50 mm clearance from obstacle faces; routing planes are authorized above/below partitions.
    return unary_union([box(o['x'],o['y'],o['x']+o['w'],o['y']+o['h']).buffer(.05,join_style=2) for o in objects]),objects

def o_name(o):return f"{o.get('name') or 'column'} ({o['id']})"

def route_all(b:Building):
    rooms={r.id:r for r in b.rooms};geom,obs=obstacle_geometry(b);routes=[]
    minx,miny,maxx,maxy=bounds=(-1.5,-1.5,b.width+1.5,b.depth+1.5)
    for kind,objects,utility in [('water',b.fixtures,b.site.water),('drain',b.fixtures,b.site.drain),('conduit',b.equipment,b.site.panel)]:
        for item in objects:
            r=rooms[item.room_id];local=(r.x+item.dx,r.y+item.dy);target=(utility.x,utility.y)
            start,end=(local,target) if kind=='drain' else (target,local)
            baseline=simplify([start,(end[0],start[1]),end]);conflict=blocked(baseline,geom)
            path=astar(start,end,geom,bounds) if b.routing_mode=='avoid' else baseline
            status='pass';reason='Connected; physical route checked against buffered structural obstacles'
            if not (r.x<=local[0]<=r.x+r.w and r.y<=local[1]<=r.y+r.h):path=None;reason='Connection point falls outside its room'
            if not all(minx<=p[0]<=maxx and miny<=p[1]<=maxy for p in [start,end]):path=None;reason='Endpoint is outside the permitted routing envelope'
            if path is None:
                status='fail'
                if not reason.startswith(('Connection','Endpoint')):
                    # Name the obstacle when an endpoint sits inside its clearance zone; that is the usual cause and the fix is to move the item.
                    hit=next((o for o in obs for p in [start,end] if box(o['x'],o['y'],o['x']+o['w'],o['y']+o['h']).buffer(.05,join_style=2).intersects(Point(p))),None)
                    reason=f"{item.name} connection point lies within the 50 mm clearance of {o_name(hit)}; move the {'fixture' if kind!='conduit' else 'equipment'} clear of it" if hit else 'No connected route on the permitted 0.25 m graph'
            elif blocked(path,geom):status='fail';reason='Route intersects a structural obstacle; generate an obstacle-aware alternative'
            distance=length(path) if path else 0
            fall=item.elevation-utility.z if kind=='drain' else None
            slope=fall/distance if kind=='drain' and distance else None
            if kind=='drain' and (slope is None or slope<b.engineering.drain_slope):status='fail';reason=f'Insufficient gravity fall: requires {distance*b.engineering.drain_slope:.3f} m; available {fall:.3f} m'
            points=path or []
            fittings=[{'id':f'elbow-{kind}-{item.id}-{i}','point':list(p),'type':'elbow'} for i,p in enumerate(points[1:-1])]
            routes.append({'id':f'{kind}-{item.id}','kind':kind,'source_id':item.id,'room_id':r.id,'name':item.name,'points':[list(p) for p in points],'length':distance,'baseline_length':length(baseline),'baseline_conflict':conflict,'status':status,'reason':reason,'fittings':fittings,'slope':slope,'fall':fall,'from_elevation':item.elevation if kind=='drain' else None,'to_elevation':utility.z if kind=='drain' else None,'direction':'fixture to outfall' if kind=='drain' else 'supply to endpoint'})
    circuits=[]
    for c in b.circuits:
        equipment=[x for x in b.equipment if x.circuit_id==c.id];missing=any(x.watts is None for x in equipment)
        total=None if missing else sum(x.watts for x in equipment)
        circuits.append({'id':c.id,'name':c.name,'equipment_ids':[x.id for x in equipment],'connected_W':total,'demand_W':total*c.demand_factor if total is not None else None,'current_A':total*c.demand_factor/(c.voltage*c.power_factor) if total is not None else None,'voltage':c.voltage,'power_factor':c.power_factor,'demand_factor':c.demand_factor,'status':'missing_input' if missing else 'pass','coverage':'Load arithmetic only; conductor sizing, protection and voltage drop not evaluated'})
    return {'routes':routes,'circuits':circuits,'obstacles':obs,'settings':{'grid_m':.25,'obstacle_clearance_m':.05,'algorithm':'A* Manhattan' if b.routing_mode=='avoid' else 'direct L-route baseline','network':'Dedicated home runs, separate pipes/conduits even along coincident segments','partition_policy':'Authorized routing planes above partitions for conduits/cold-water and below slab for drains; column and foundation exclusion footprints remain obstacles','limitations':'Planar coordination only; risers, pipe diameters, beam penetrations, venting and hydraulic adequacy not evaluated'}}

"""RA 9514 Fire Code of the Philippines, 2019 Revised IRR: egress and fire-protection screen for single-storey
business and mercantile occupancies. Clause text was transcribed from a published copy of the RIRR and must be
verified against the BFP-issued text. Travel is measured on a 0.25 m grid through modeled doors only."""
import heapq,math
from .domain import Building
from .geometry import openings

STEP=.25
SOURCE='RA 9514 (Fire Code of the Philippines) 2019 Revised IRR, transcribed from a published copy — verify against the BFP-issued text; final evaluation rests with the C/MFM having jurisdiction.'
OCCUPANT_LOAD={'business':(9.3,'10.2.16.1 ¶3.1'),'business_concentrated':(4.6,'10.2.16.1 ¶3.1 (concentrated use, e.g. BPO)'),'mercantile':(2.8,'10.2.15.1 ¶3.1.a (street floor)')}
EXTINGUISHER={'low':('2-A',15,200),'moderate':('3-A',12,100),'high':('4-A',10,75)}  # 10.2.6.9 Table 7: rating, max travel m, max area m²
RATING={'2-A':2,'3-A':3,'4-A':4}

def exit_segments(b:Building):
    """Exterior exits as axis-aligned segments on the building perimeter."""
    segs=[{'id':d['id'],'a':(0.,d['y']),'b':(0.,d['y']+d['width']),'width':d['width'],'wall':'west'} for d in openings(b) if d['kind']=='entry']
    for e in b.fire.exits:
        a,c={'west':((0,e.offset),(0,e.offset+e.width)),'east':((b.width,e.offset),(b.width,e.offset+e.width)),
             'south':((e.offset,0),(e.offset+e.width,0)),'north':((e.offset,b.depth),(e.offset+e.width,b.depth))}[e.wall]
        segs.append({'id':e.id,'a':a,'b':c,'width':e.width,'wall':e.wall})
    return segs

class Grid:
    def __init__(self,b:Building):
        self.b=b;self.nx=max(1,round(b.width/STEP));self.ny=max(1,round(b.depth/STEP))
        self.room={}
        for i in range(self.nx):
            for j in range(self.ny):
                x,y=(i+.5)*STEP,(j+.5)*STEP
                r=next((r for r in b.rooms if r.x<=x<=r.x+r.w and r.y<=y<=r.y+r.h),None)
                if r:self.room[(i,j)]=r.id
        # Interior doors are horizontal segments on corridor walls (see geometry.openings).
        self.doors=[(d['x'],d['x']+d['width'],d['y']) for d in openings(b) if d['kind']=='door']
    def center(self,c):return ((c[0]+.5)*STEP,(c[1]+.5)*STEP)
    def passable(self,c,n):
        if self.room[c]==self.room[n]:return True
        if c[0]!=n[0]:return False  # interior doors are only modeled on horizontal walls
        y=max(c[1],n[1])*STEP;x=(c[0]+.5)*STEP
        return any(abs(y-dy)<1e-6 and x0<=x<=x1 for x0,x1,dy in self.doors)
    def neighbours(self,c):
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            n=(c[0]+dx,c[1]+dy)
            if n not in self.room:continue
            if dx and dy:
                # No corner cutting: a diagonal step stays inside one room.
                if not (self.room[n]==self.room[c]==self.room.get((c[0]+dx,c[1]))==self.room.get((c[0],c[1]+dy))):continue
            elif not self.passable(c,n):continue
            yield n,STEP*(math.sqrt(2) if dx and dy else 1)
    def dijkstra(self,sources):
        dist=dict(sources);parent={};queue=[(d,c) for c,d in sources.items()];heapq.heapify(queue)
        while queue:
            d,c=heapq.heappop(queue)
            if d>dist.get(c,math.inf):continue
            for n,w in self.neighbours(c):
                if d+w<dist.get(n,math.inf)-1e-12:dist[n]=d+w;parent[n]=c;heapq.heappush(queue,(d+w,n))
        return dist,parent
    def exit_sources(self,seg):
        (x0,y0),(x1,y1)=seg['a'],seg['b'];cells={}
        for c in self.room:
            x,y=self.center(c)
            if x0==x1 and abs(x-x0)<=STEP/2+1e-9 and min(y0,y1)<=y<=max(y0,y1):cells[c]=STEP/2
            if y0==y1 and abs(y-y0)<=STEP/2+1e-9 and min(x0,x1)<=x<=max(x0,x1):cells[c]=STEP/2
        return cells
    def point_source(self,x,y):
        c=(min(self.nx-1,max(0,int(x/STEP))),min(self.ny-1,max(0,int(y/STEP))))
        return {c:math.dist((x,y),self.center(c))} if c in self.room else {}

def path(grid,parent,cell):
    out=[grid.center(cell)]
    while cell in parent:cell=parent[cell];out.append(grid.center(cell))
    return [list(p) for p in out]

def dead_end(b,segs):
    """Longest corridor stretch from which an exit is reachable in only one direction (along the corridor axis)."""
    worst=0.;where=None
    for r in [r for r in b.rooms if r.kind=='corridor']:
        horizontal=r.w>=r.h;start,end=(r.x,r.x+r.w) if horizontal else (r.y,r.y+r.h)
        pos=[]
        for s in segs:
            (x0,y0),(x1,y1)=s['a'],s['b']
            if horizontal and x0==x1 and r.x-1e-6<=x0<=r.x+r.w+1e-6 and min(y0,y1)<r.y+r.h and max(y0,y1)>r.y:pos.append(x0)
            if not horizontal and y0==y1 and r.y-1e-6<=y0<=r.y+r.h+1e-6 and min(x0,x1)<r.x+r.w and max(x0,x1)>r.x:pos.append(y0)
        length=end-start if not pos else max(min(pos)-start,end-max(pos))
        if length>worst:worst,where=length,r.id
    return worst,where

def analyze_fire(b:Building):
    f=b.fire
    if not f.enabled:return {'enabled':False}
    grid=Grid(b);segs=exit_segments(b);checks=[]
    def add(rule,status,evidence,clause,inputs=None):checks.append({'rule':rule,'status':status,'evidence':evidence,'clause':clause,'inputs':inputs or {}})
    gfa=b.width*b.depth;factor,load_clause=OCCUPANT_LOAD[f.occupancy];load=math.ceil(round(gfa/factor,9))
    merc=f.occupancy=='mercantile';business=not merc
    klass=None if business else ('A' if gfa>=2788 else 'B' if gfa>278 else 'C')
    # Egress travel
    runs=[grid.dijkstra(grid.exit_sources(s)) for s in segs]
    nearest={c:min((run[0].get(c,math.inf),k) for k,run in enumerate(runs)) if runs else (math.inf,None) for c in grid.room}
    worst_cell=max(nearest,key=lambda c:nearest[c][0]) if nearest else None
    travel=nearest[worst_cell][0] if worst_cell else math.inf
    unreachable=sorted({grid.room[c] for c,(d,_) in nearest.items() if d==math.inf})
    critical=path(grid,runs[nearest[worst_cell][1]][1],worst_cell) if worst_cell and travel<math.inf else []
    # Common path: shared prefix of the routes to the two nearest exits (tree-metric approximation).
    common=travel
    if len(runs)>=2:
        between=[[min((runs[i][0].get(c,math.inf) for c in grid.exit_sources(segs[j])),default=math.inf) for j in range(len(runs))] for i in range(len(runs))]
        common=0.
        for c in grid.room:
            ds=sorted((run[0].get(c,math.inf),k) for k,run in enumerate(runs))
            (d1,a),(d2,k2)=ds[0],ds[1]
            shared=d1 if d2==math.inf else min(d1,max(0.,(d1+d2-between[a][k2])/2))
            common=max(common,shared)
    de,de_room=dead_end(b,segs)
    # Single-exit allowances
    if business:single=(load<100 and travel<=30) or (f.sprinklered and travel<=30);single_clause='10.2.16.2 ¶4.3 (fewer than 100 occupants, ≤ 30 m travel) / ¶4.6 (sprinklered single tenant, ≤ 30 m)'
    else:single=klass=='C' and travel<=(30 if f.sprinklered else 23);single_clause='10.2.15.2 ¶4.3 / ¶4.4 (Class C, ≤ 23 m, or ≤ 30 m sprinklered)'
    required=4 if load>1000 else 3 if load>500 else (1 if single else 2)
    add('FIRE-OCCLOAD','pass',f"{gfa:.1f} m² gross ÷ {factor} m²/person = {load} occupants"+(f'; mercantile Class {klass}' if merc else ''),f'RIRR {load_clause}',{'gross_area_m2':gfa,'factor_m2':factor,'occupant_load':load})
    add('FIRE-EXITS','pass' if len(segs)>=required else 'fail',f"{len(segs)} exit(s) provided; {required} required"+(f' (single exit permitted: {single_clause.split(" ")[0]})' if required==1 else ''),f'RIRR 10.2.16.2 ¶4.1.b / 10.2.15.2 ¶4.1.b (two per storey); 10.2.5.2 ¶G.2 (3 above 500, 4 above 1,000); {single_clause}',{'provided':len(segs),'required':required})
    if unreachable:add('FIRE-TRAVEL','fail',f"No modeled egress path from: {', '.join(unreachable)}",'RIRR 10.2.5.2 ¶J')
    else:
        limit=(61 if f.sprinklered else 46) if business else (46 if f.sprinklered else f.mercantile_travel_m)
        clause='RIRR 10.2.16.2 ¶6.1 (61 m sprinklered) / ¶6.2 (46 m)' if business else ('RIRR 10.2.15.2 ¶6 (46 m sprinklered)' if f.sprinklered else f'Mercantile unsprinklered: {f.mercantile_travel_source}')
        if limit is None:add('FIRE-TRAVEL','missing_input',f'Longest travel {travel:.1f} m; unsprinklered mercantile limit not supplied',clause)
        else:add('FIRE-TRAVEL','pass' if travel<=limit+1e-9 else 'fail',f'Longest travel {travel:.1f} m to the nearest exit vs {limit:g} m',clause,{'travel_m':travel,'limit_m':limit})
    if business:
        dl=15 if f.sprinklered else 6
        add('FIRE-DEADEND','pass' if de<=dl+1e-9 else 'fail',f'Longest dead-end corridor {de:.1f} m'+(f' ({de_room})' if de_room else '')+f' vs {dl} m','RIRR 10.2.16.2 ¶5.2.a (15 m sprinklered) / ¶5.2.b (6 m)',{'dead_end_m':de})
        cl=30 if f.sprinklered or load<=30 else 23
        add('FIRE-COMMON','pass' if common<=cl+1e-9 else 'fail',f'Common path of travel {common:.1f} m vs {cl} m'+(' (single tenant, ≤ 30 occupants assumed)' if not f.sprinklered and load<=30 else ''),'RIRR 10.2.16.2 ¶5.3.a/b (30 m) / ¶5.3.c (23 m)',{'common_path_m':common})
    else:
        add('FIRE-DEADEND','pass' if de<=6+1e-9 else 'fail',f'Longest dead-end corridor {de:.1f} m vs 6 m','RIRR 10.2.5.2 ¶I (general, 6 m)',{'dead_end_m':de})
        add('FIRE-COMMON','unsupported','Division 15 states no general common-path limit for this case; not evaluated','RIRR 10.2.15.2 ¶4.2')
    width=sum(s['width'] for s in segs);need=load*5/1000
    add('FIRE-CAPACITY','pass' if width>=need-1e-9 else 'fail',f'Exit width {width:.2f} m vs {need:.2f} m required ({load} × 5.0 mm, level components)','RIRR 10.2.5.2 ¶C Table 1',{'provided_m':width,'required_m':need})
    if business and load>=50:
        corridor=min((min(r.w,r.h) for r in b.rooms if r.kind=='corridor'),default=None)
        add('FIRE-CORRIDOR','missing_input' if corridor is None else ('pass' if corridor>=1.12 else 'fail'),f'Corridor clear width {corridor} m vs 1.12 m (≥ 50 occupants)','RIRR 10.2.16.2 ¶3.2')
    if business:sprinkler_needed,why=b.height>=15,'buildings 15 m or more in height (10.2.16.3 ¶3)'
    else:sprinkler_needed,why=gfa>1115,'mercantile over 1,115 m² gross (10.2.15.3 ¶4.2); 3+ storeys (¶4.1) n/a single storey'
    add('FIRE-SPRINKLER','fail' if sprinkler_needed and not f.sprinklered else 'pass',('Required' if sprinkler_needed else 'Not required')+f' — {why}; '+('provided' if f.sprinklered else 'not provided'),'RIRR 10.2.16.3 ¶3 / 10.2.15.3 ¶4')
    if business:
        system=load>=(300 if f.new_building else 1000)
        add('FIRE-ALARM','fail' if f.alarm=='none' else 'pass',('Fire alarm system required (≥ 300 occupants, 10.2.16.3 ¶4.1.c)' if system else 'Manual fire alarm system required (10.2.16.3 ¶4.4)')+f'; provided: {f.alarm}','RIRR 10.2.16.3 ¶4.1–4.4')
        add('FIRE-EMLIGHT','pass' if f.emergency_lighting else 'not_applicable','Single storey at exit discharge: emergency lighting not triggered by ¶8.2'+('; provided' if f.emergency_lighting else ''),'RIRR 10.2.16.2 ¶8.2')
        add('FIRE-SIGNS','pass' if f.exit_signs else 'fail','Exit signs '+('provided' if f.exit_signs else 'missing'),'RIRR 10.2.16.2 ¶8.4 → 10.2.5.12')
    else:
        if klass in 'AB':add('FIRE-ALARM','pass' if f.alarm=='automatic' else 'fail',f'Class {klass}: automatic fire alarm required; provided: {f.alarm}','RIRR 10.2.15.3 ¶3')
        else:add('FIRE-ALARM','not_applicable',f'Class C: Division 15 states no alarm requirement; provided: {f.alarm}. Confirm with the C/MFM','RIRR 10.2.15.3 ¶3')
        if klass in 'AB':add('FIRE-EMLIGHT','pass' if f.emergency_lighting else 'fail',f'Class {klass}: emergency lighting required','RIRR 10.2.15.2 ¶9.2')
        else:add('FIRE-EMLIGHT','not_applicable','Class C: emergency lighting not triggered by ¶9.2','RIRR 10.2.15.2 ¶9.2')
        add('FIRE-SIGNS','pass' if f.exit_signs else 'fail','Exit illumination and signs '+('provided' if f.exit_signs else 'missing'),'RIRR 10.2.15.2 ¶9.1')
    # Portable extinguishers (Table 7, Class A)
    rating,reach,area=EXTINGUISHER[f.hazard];rooms={r.id:r for r in b.rooms};ext_travel=math.inf;ext_path=[]
    if f.extinguishers:
        sources={}
        for e in f.extinguishers:
            r=rooms[e.room_id]
            for c,d in grid.point_source(r.x+e.dx,r.y+e.dy).items():sources[c]=min(d,sources.get(c,math.inf))
        dist,parent=grid.dijkstra(sources)
        far=max(grid.room,key=lambda c:dist.get(c,math.inf));ext_travel=dist.get(far,math.inf)
        ext_path=path(grid,parent,far) if ext_travel<math.inf else []
    count_needed=max(1,math.ceil(round(gfa/area,9)))
    low=[e.id for e in f.extinguishers if RATING[e.rating]<RATING[rating]]
    ok=len(f.extinguishers)>=count_needed and ext_travel<=reach+1e-9 and not low
    add('FIRE-EXT','pass' if ok else 'fail',f"{len(f.extinguishers)} extinguisher(s), {count_needed} needed for {gfa:.0f} m² at {area} m² each; farthest point {'—' if ext_travel==math.inf else f'{ext_travel:.1f} m'} vs {reach} m; minimum {rating}"+(f"; under-rated: {', '.join(low)}" if low else ''),'RIRR 10.2.6.9 ¶2 (all buildings) and Table 7 ('+f.hazard+' hazard)',{'count':len(f.extinguishers),'needed':count_needed,'max_travel_m':ext_travel if ext_travel<math.inf else None,'limit_m':reach})
    for name,clause in [('Standpipes','10.2.6.8'),('Construction, compartmentation and fire-resistance ratings','10.2.6.1'),('Interior finish','10.2.6.4'),('Hazardous areas and segregation','10.2.6.10'),('FSEC / building plan evaluation by the BFP','Rule 9')]:
        add('FIRE-SCOPE','unsupported',f'{name}: not evaluated',f'RIRR {clause}')
    return {'enabled':True,'occupancy':f.occupancy,'mercantile_class':klass,'gross_area_m2':gfa,'occupant_load':load,'exits':[{**s,'a':list(s['a']),'b':list(s['b'])} for s in segs],
            'travel':{'max_m':travel if travel<math.inf else None,'critical_path':critical,'common_path_m':common if common<math.inf else None,'dead_end_m':de},
            'extinguishers':{'max_travel_m':ext_travel if ext_travel<math.inf else None,'critical_path':ext_path,'reach_m':reach,'min_rating':rating},
            'checks':checks,'source':SOURCE,
            'scope':'Single-storey egress on a 0.25 m grid through modeled doors (furniture and columns ignored), occupant load, exits, travel, dead ends, common path, exit capacity, and sprinkler/alarm/lighting/sign/extinguisher triggers for business and mercantile occupancies.'}

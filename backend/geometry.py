import csv, io
import numpy as np
from scipy.spatial import Delaunay, QhullError
from shapely.geometry import Polygon, box, LineString, Point as SPoint
from shapely.ops import unary_union
from .domain import Building, Site, Point, digest

def validate_site(site:Site):
    boundary=Polygon([(p.x,p.y) for p in site.boundary])
    if not boundary.is_valid or boundary.area<=0:raise ValueError('Boundary must be a valid nondegenerate polygon without self-intersections')
    pts=[(p.x,p.y) for p in site.survey]
    if len(pts)<3 or len(set(pts))!=len(pts):raise ValueError('Survey requires at least three unique XY coordinates; duplicate coordinates are not allowed')
    if len(pts)>10000:raise ValueError('Survey exceeds the 10,000-point prototype limit')
    try:tri=Delaunay(np.array(pts))
    except QhullError:raise ValueError('Survey points must not be collinear')
    return boundary,tri

def parse_survey(text:str, units:str):
    factors={'m':1,'mm':.001,'ft':.3048}
    if units not in factors:raise ValueError('Survey units must be m, mm or ft')
    reader=csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames or set(reader.fieldnames)!={'X','Y','Z'}:raise ValueError('CSV headers must be exactly X,Y,Z')
    points=[Point(x=float(r['X'])*factors[units],y=float(r['Y'])*factors[units],z=float(r['Z'])*factors[units]) for r in reader]
    return points

def terrain(b:Building):
    boundary,tri=validate_site(b.site);pts=b.site.survey;cut=fill=0;triangles=[]
    footprint=box(0,0,b.width,b.depth);covered=0
    for ids in tri.simplices:
        p=[pts[int(i)] for i in ids];poly=Polygon([(v.x,v.y) for v in p]);clipped=poly.intersection(footprint)
        A=np.array([[v.x,v.y,1] for v in p]);plane=np.linalg.solve(A,np.array([v.z for v in p]));slope=float(np.hypot(plane[0],plane[1]))
        if clipped.area:
            center=clipped.centroid;dz=float(plane[0]*center.x+plane[1]*center.y+plane[2]-b.site.platform_elevation)
            cut+=max(dz,0)*clipped.area;fill+=max(-dz,0)*clipped.area;covered+=clipped.area
        triangles.append({'vertices':[int(i) for i in ids],'slope_percent':slope*100})
    complete=abs(covered-footprint.area)<1e-6
    return {'triangles':triangles,'boundary_area':boundary.area,'cut_m3':cut if complete else None,'fill_m3':fill if complete else None,'coverage':covered/footprint.area,'method':'Approximate centroid integration over footprint-clipped survey triangles; no bulking, compaction or retaining works','status':'pass' if complete else 'missing_input'}

def openings(b):
    halls=[r for r in b.rooms if r.kind=='corridor'];result=[]
    if not halls:return result
    hall=halls[0]
    for r in b.rooms:
        if r.kind=='corridor':continue
        if abs(r.y+r.h-hall.y)<1e-6 or abs(r.y-(hall.y+hall.h))<1e-6:
            start=max(r.x,hall.x);end=min(r.x+r.w,hall.x+hall.w)
            if end-start>=1.1:
                result.append({'id':f'door-{r.id}','room_id':r.id,'to_room_id':hall.id,'x':start+.35,'y':hall.y if r.y<hall.y else hall.y+hall.h,'width':.9,'height':2.1,'kind':'door'})
    result.append({'id':'door-entry','room_id':hall.id,'to_room_id':'outside','x':0,'y':hall.y+.15,'width':1.2,'height':2.1,'kind':'entry'})
    return result

def layout_checks(b):
    footprint=box(0,0,b.width,b.depth);boundary,_=validate_site(b.site);usable=boundary.buffer(-b.site.setback);issues=[];doors=openings(b)
    halls=[r for r in b.rooms if r.kind=='corridor']
    if len(halls)!=1 or halls[0].x!=0 or halls[0].w!=b.width or halls[0].h<1.35:
        issues.append({'id':'circulation-envelope','objects':[r.id for r in halls],'reason':'Supported circulation requires one full-width west-entry corridor, at least 1.35 m deep for the modeled 1.2 m door and jamb offset; illustrative geometry, not a code rule'})
    elif b.site.access.x!=0 or not halls[0].y+.15<=b.site.access.y<=halls[0].y+1.35:
        issues.append({'id':'entry-connectivity','objects':[halls[0].id],'reason':'Site access point must connect to the modeled west corridor entrance'})
    if not usable.covers(footprint):issues.append({'id':'site-envelope','objects':[b.id],'reason':'Building extends outside the user-entered setback envelope'})
    for i,r in enumerate(b.rooms):
        poly=box(r.x,r.y,r.x+r.w,r.y+r.h)
        if not footprint.covers(poly):issues.append({'id':f'contain-{r.id}','objects':[r.id],'reason':f'{r.name} extends outside the building'})
        if not r.min_area-1e-6<=r.w*r.h<=r.max_area+1e-6 or min(r.w,r.h)<r.min_dimension-1e-6:issues.append({'id':f'area-{r.id}','objects':[r.id],'reason':f'{r.name} violates area or minimum dimension constraints'})
        for s in b.rooms[i+1:]:
            if poly.intersection(box(s.x,s.y,s.x+s.w,s.y+s.h)).area>1e-6:issues.append({'id':f'overlap-{r.id}-{s.id}','objects':[r.id,s.id],'reason':f'{r.name} overlaps {s.name}'})
        if r.kind!='corridor' and not any(d['room_id']==r.id for d in doors):issues.append({'id':f'access-{r.id}','objects':[r.id],'reason':f'{r.name} has no modeled door to the circulation corridor'})
    if b.brief.wet_adjacency:
        wet=[r for r in b.rooms if r.kind in ['kitchen','bathroom']]
        if len(wet)==2:
            a,c=wet
            if box(a.x,a.y,a.x+a.w,a.y+a.h).boundary.intersection(box(c.x,c.y,c.x+c.w,c.y+c.h).boundary).length<1:issues.append({'id':'wet-adjacency','objects':[a.id,c.id],'reason':'Required kitchen / bathroom adjacency is not satisfied'})
    circulation_paths=[]
    if len(halls)==1 and not any(i['id'] in ['circulation-envelope','entry-connectivity'] for i in issues):
        from .routing import astar
        hall=halls[0]
        # Explicit illustrative 0.50 m moving clearance envelope, not a code minimum.
        obstacles=[box(c.x-.15,c.y-.15,c.x+.15,c.y+.15).buffer(.25,join_style=2) for c in b.columns if c.active]
        for f in b.furniture:
            rr=next(r for r in b.rooms if r.id==f.room_id)
            obstacles.append(box(rr.x+f.dx,rr.y+f.dy,rr.x+f.dx+f.w,rr.y+f.dy+f.h).buffer(.25,join_style=2))
        geom=unary_union(obstacles)
        origin=(.25,b.site.access.y)
        for door in [d for d in doors if d['kind']=='door']:
            endpoint=(door['x']+door['width']/2,door['y']+(.25 if door['y']==hall.y else -.25))
            path=astar(origin,endpoint,geom,(.25,hall.y+.25,b.width-.25,hall.y+hall.h-.25))
            if path is None:issues.append({'id':'circulation-'+door['room_id'],'objects':[hall.id,door['room_id']],'reason':'No corridor path with the illustrative 0.50 m moving clearance around physical columns and furniture'})
            else:circulation_paths.append({'id':'access-'+door['room_id'],'door_id':door['id'],'points':path,'clearance_width_m':.5})
    return {'status':'fail' if issues else 'pass','issues':issues,'doors':doors,'circulation_paths':circulation_paths,'circulation':'Room door → fixed 1.5 m corridor → modeled exterior entrance','grid_restriction':'Roof supports remain on the configured grid; partitions are non-load-bearing'}

def wall_geometry(b):
    lines=[]
    for r in b.rooms:
        pts=[(r.x,r.y),(r.x+r.w,r.y),(r.x+r.w,r.y+r.h),(r.x,r.y+r.h),(r.x,r.y)]
        lines.extend(LineString([a,c]) for a,c in zip(pts,pts[1:]))
    merged=unary_union(lines);parts=list(merged.geoms) if hasattr(merged,'geoms') else [merged]
    walls=[{'id':'wall-'+digest(sorted([list(line.coords[0]),list(line.coords[-1])]))[:10],'a':list(line.coords[0]),'b':list(line.coords[-1]),'length':line.length,'height':b.height} for i,line in enumerate(parts)]
    return walls

def fitout_checks(b):
    issues=[];rooms={r.id:r for r in b.rooms};doors=openings(b)
    for f in b.furniture:
        r=rooms[f.room_id];shape=box(r.x+f.dx,r.y+f.dy,r.x+f.dx+f.w,r.y+f.dy+f.h);room=box(r.x,r.y,r.x+r.w,r.y+r.h)
        if not room.covers(shape):issues.append({'objects':[f.id,r.id],'reason':f'{f.name} is outside its room'})
        # A useful bounded clearance: forward access strip, not clearance on all wall-facing edges.
        access=box(r.x+f.dx,r.y+f.dy-f.clearance,r.x+f.dx+f.w,r.y+f.dy)
        if not room.covers(access):issues.append({'objects':[f.id],'reason':f'{f.name} lacks {f.clearance:g} m front clearance'})
        for other in b.furniture:
            if other.id==f.id or other.room_id!=r.id:continue
            other_shape=box(r.x+other.dx,r.y+other.dy,r.x+other.dx+other.w,r.y+other.dy+other.h)
            if shape.intersection(other_shape).area>1e-6 or access.intersection(other_shape).area>1e-6:issues.append({'objects':[f.id,other.id],'reason':f'{f.name} body or front clearance conflicts with {other.name}'})
        for d in doors:
            if d['room_id']==r.id:
                swing=box(d['x'],d['y']-.9 if r.y<d['y'] else d['y'],d['x']+.9,d['y'] if r.y<d['y'] else d['y']+.9)
                if swing.intersection(shape).area>1e-6:issues.append({'objects':[f.id,d['id']],'reason':f'{f.name} intersects the conservative door-swing envelope'})
    return {'status':'fail' if issues else 'pass','issues':issues,'scope':'Furniture body, front access strips and conservative rectangular door-swing envelopes only'}

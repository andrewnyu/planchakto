"""Shortest visibility paths for explicit waypoint-routing requests, not vehicle kinematics."""
import heapq
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union,nearest_points

def resolve_route(route,boundary,obstacles=()):
    if not route.auto_route:return route
    free=Polygon(boundary).buffer(-route.width/2,join_style=2)
    if obstacles:free=free.difference(unary_union([p.buffer(route.width/2+.02,join_style=2) for p in obstacles]))
    if free.is_empty:raise ValueError(f'{route.name}: no envelope fits at this width')
    parts=[free] if free.geom_type=='Polygon' else list(free.geoms)
    projected=[]
    requested=route.requested_points or route.points
    for xy in requested:
        p=Point(xy)
        if not free.covers(p):
            near=nearest_points(free,p)[0]
            if near.distance(p)>route.width+1:raise ValueError(f'{route.name}: waypoint {xy} is too far outside the available circulation area')
            p=near
        projected.append(tuple(p.coords[0]))
    result=[]
    for start,end in zip(projected,projected[1:]):
        region=next((p for p in parts if p.buffer(.0001).covers(Point(start)) and p.buffer(.0001).covers(Point(end))),None)
        if region is None:raise ValueError(f'{route.name}: waypoints are in disconnected circulation areas')
        visible=region.buffer(.00001);vertices=[start,end]+list(region.exterior.coords)[:-1]
        for hole in region.interiors:vertices+=list(hole.coords)[:-1]
        if len(vertices)>500:raise ValueError('Simplify the circulation boundary before automatic routing')
        edges=[[] for _ in vertices]
        for i,a in enumerate(vertices):
            for j in range(i):
                line=LineString([a,vertices[j]])
                if visible.covers(line):edges[i].append((j,line.length));edges[j].append((i,line.length))
        distances={0:0};parents={};queue=[(0,0)]
        while queue:
            d,i=heapq.heappop(queue)
            if d!=distances[i]:continue
            if i==1:break
            for j,length in edges[i]:
                nd=d+length
                if nd<distances.get(j,float('inf')):distances[j]=nd;parents[j]=i;heapq.heappush(queue,(nd,j))
        if 1 not in distances:raise ValueError(f'{route.name}: no connected path at the supplied width')
        indices=[1]
        while indices[-1]!=0:indices.append(parents[indices[-1]])
        path=[vertices[i] for i in reversed(indices)];result+=path if not result else path[1:]
    if len(result)>40:raise ValueError(f'{route.name}: route needs more than 40 vertices; simplify the waypoints')
    note=' Path derived from requested waypoints inside the inset boundary. Gate approach links and vehicle turning are not checked.'
    return route.model_copy(update={'points':result,'requested_points':requested,'basis':(route.basis if note in route.basis else route.basis[:350]+note)})

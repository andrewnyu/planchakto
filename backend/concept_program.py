"""Typed spatial operations: model-authored design decisions, code-derived geometry."""
from __future__ import annotations
from typing import Literal
from pydantic import Field,model_validator
from shapely.geometry import Polygon, LineString, Point, box
from .domain import Model

XY=tuple[float,float]
Kind=Literal['retail','storage','office','service','kitchen','bathroom','living','bedroom','circulation','loading','parking','outdoor','landscape','future']


class Cut(Model):
    region:str=Field(min_length=1,max_length=48)
    axis:Literal['x','y']
    at:float|None=None
    low_area_m2:float|None=Field(default=None,gt=0,description='Explicitly ask code to solve the cut coordinate giving this area to the low region, instead of guessing at')
    low:str=Field(min_length=1,max_length=48)
    high:str=Field(min_length=1,max_length=48)
    @model_validator(mode='after')
    def one_position(self):
        if (self.at is None)==(self.low_area_m2 is None):raise ValueError('A cut needs exactly one of at or low_area_m2')
        return self


class Space(Model):
    region:str=Field(min_length=1,max_length=48)
    name:str=Field(min_length=1,max_length=80)
    kind:Kind
    enclosed:bool=False
    purpose:str=Field(default='',max_length=400)
    requirement_ids:list[str]=Field(default_factory=list,max_length=60)

class Merge(Model):
    regions:list[str]=Field(min_length=2,max_length=12)
    into:str=Field(min_length=1,max_length=48)


class Connection(Model):
    from_zone:str=Field(min_length=1,max_length=48)
    to_zone:str=Field(min_length=1,max_length=48)
    width:float=Field(gt=.1,le=200)
    kind:Literal['door','open','loading']='open'
    preferred_point:XY|None=None
    allow_public_path:bool=Field(default=False,description='Allow code to connect these endpoints through intervening unenclosed circulation/living/retail zones using real shared walls')


class Outdoor(Model):
    id:str=Field(min_length=1,max_length=48)
    name:str=Field(min_length=1,max_length=80)
    kind:Kind
    polygon:list[XY]=Field(min_length=3,max_length=32)
    clip_to_site:bool=False
    purpose:str=Field(default='',max_length=400)
    requirement_ids:list[str]=Field(default_factory=list,max_length=60)

class AutoAccess(Model):
    region:str
    from_kinds:list[Kind]=Field(min_length=1,max_length=15)
    width:float=Field(gt=.1,le=30)
    kind:Literal['door','open','loading']='door'

class ParkingIntent(Model):
    zone_ids:list[str]=Field(min_length=1,max_length=12)
    count:int=Field(ge=1,le=2000)
    bay_width:float=Field(gt=1,le=10)
    bay_depth:float=Field(gt=2,le=20)
    aisle_width:float=Field(gt=0,le=30)
    rows_per_aisle:Literal[1,2]=2
    basis:str=Field(default='Proposed parking dimensions and area allowance, not statutory criteria',max_length=500)


class LayoutProgram(Model):
    title:str=Field(min_length=1,max_length=100)
    rationale:str=Field(min_length=1,max_length=1600)
    footprint:list[XY]=Field(min_length=3,max_length=32)
    clip_footprint_to_site:bool=False
    fit_area_m2:float|None=Field(default=None,gt=0,le=250000,description='Explicitly ask code to fit the proposed footprint to this actual area, clipping to a supplied site envelope when one exists')
    clip_clearance_m:float=Field(default=0,ge=0,le=50,description='Proposed site-edge clearance for this concept, not a statutory setback')
    cuts:list[Cut]=Field(default_factory=list,max_length=47)
    merges:list[Merge]=Field(default_factory=list,max_length=24)
    spaces:list[Space]=Field(min_length=1,max_length=48)
    connections:list[Connection]=Field(min_length=1,max_length=80)
    auto_access:list[AutoAccess]=Field(default_factory=list,max_length=48)
    parking_intent:ParkingIntent|None=None
    outdoors:list[Outdoor]=Field(default_factory=list,max_length=12)
    assumptions:list[str]=Field(default_factory=list,max_length=16)
    tradeoffs:list[str]=Field(default_factory=list,max_length=12)


class ProgramReply(Model):
    reply:str=Field(min_length=1,max_length=2000)
    programs:list[LayoutProgram]=Field(default_factory=list,max_length=3)
    questions:list[str]=Field(default_factory=list,max_length=5)


def compile_program(program:LayoutProgram,site=None):
    from .concepts import DesignPlan,polygon
    shell=polygon(program.footprint,'Footprint');notes=[]
    envelope=None
    clip_requested=program.clip_footprint_to_site or (program.fit_area_m2 is not None and site is not None)
    if clip_requested:
        if site is None:raise ValueError('Clipping a footprint needs a supplied site')
        envelope=Polygon(site.boundary).buffer(-program.clip_clearance_m,join_style=2)
        if envelope.is_empty:raise ValueError('No buildable area remains at the proposed clearance')
    if program.fit_area_m2 is not None:
        from shapely.affinity import scale
        original=shell;origin=original.centroid
        def fitted(factor):
            p=scale(original,xfact=factor,yfact=factor,origin=origin)
            return p.intersection(envelope).buffer(0) if envelope is not None else p
        lo=0.;hi=max(1.,(program.fit_area_m2/original.area)**.5)
        while fitted(hi).area<program.fit_area_m2-.001 and hi<32:hi*=1.5
        if fitted(hi).area<program.fit_area_m2-.001:raise ValueError('The requested footprint area cannot fit in the available envelope')
        for _ in range(45):
            mid=(lo+hi)/2
            if fitted(mid).area<program.fit_area_m2:lo=mid
            else:hi=mid
        shell=fitted((lo+hi)/2);notes.append(f'Footprint area fitted to the explicitly requested {program.fit_area_m2:g} m² by scaling the proposed shape around its centroid'+(' and clipping to the supplied site envelope.' if envelope is not None else '.'))
    if clip_requested:
        if site is None:raise ValueError('Clipping a footprint needs a supplied site')
        shell=shell.intersection(envelope).buffer(0)
        if shell.geom_type!='Polygon' or shell.is_empty or shell.interiors:raise ValueError('The clipped footprint must be one simple polygon')
        notes.append('Proposed building envelope intersected with the supplied site by explicit request; no statutory setback is implied.')
        if program.clip_clearance_m:notes.append(f'{program.clip_clearance_m:g} m uniform site-edge clearance is a model-proposed spatial allowance, not a verified statutory setback or traffic clearance.')
    regions={'building':shell};used={'building','outside'}
    for cut in program.cuts:
        if cut.region not in regions:raise ValueError(f'Cannot cut {cut.region}; available regions: {sorted(regions)}')
        occupied=set(regions)-{cut.region}
        if cut.low==cut.high or any(name in occupied or name=='outside' for name in (cut.low,cut.high)):
            raise ValueError(f'Cut {cut.region}: child IDs must be distinct and cannot replace another live region; occupied IDs are {sorted(occupied)}')
        p=regions.pop(cut.region);x0,y0,x1,y1=p.bounds
        at=cut.at
        if cut.low_area_m2 is not None:
            if cut.low_area_m2>=p.area-.1:raise ValueError(f'Cut {cut.region}: low_area_m2 must leave positive area in both children; available area {p.area:.3f} m²')
            lo,hi=(x0,x1) if cut.axis=='x' else (y0,y1)
            for _ in range(42):
                mid=(lo+hi)/2;part=box(x0-1,y0-1,mid,y1+1) if cut.axis=='x' else box(x0-1,y0-1,x1+1,mid)
                if p.intersection(part).area<cut.low_area_m2:lo=mid
                else:hi=mid
            at=(lo+hi)/2
        if cut.axis=='x':a,b=box(x0-1,y0-1,at,y1+1),box(at,y0-1,x1+1,y1+1)
        else:a,b=box(x0-1,y0-1,x1+1,at),box(x0-1,at,x1+1,y1+1)
        # A cut along a notch may retain a zero-area boundary line in a GeometryCollection.
        # Remove only those non-area remnants, preserving every positive-area component.
        low,high=p.intersection(a).buffer(0),p.intersection(b).buffer(0)
        if any(q.geom_type not in ('Polygon','MultiPolygon') or q.area<.1 for q in (low,high)):
            raise ValueError(f'Cut {cut.region} at {cut.axis}={cut.at:g} must create two positive regions within {p.bounds}')
        regions[cut.low],regions[cut.high]=low,high;used|={cut.low,cut.high}
    from shapely.ops import unary_union
    for merge in program.merges:
        if len(set(merge.regions))!=len(merge.regions) or any(k not in regions for k in merge.regions):raise ValueError('Merge references repeated or unavailable regions')
        if merge.into=='outside' or (merge.into in regions and merge.into not in merge.regions):raise ValueError('A merge cannot overwrite another region')
        united=unary_union([regions[k] for k in merge.regions]).buffer(0)
        if united.geom_type!='Polygon' or united.interiors:raise ValueError('Merged rooms must be connected simple polygons without holes')
        for key in merge.regions:del regions[key]
        regions[merge.into]=united
    if len({s.region for s in program.spaces})!=len(program.spaces) or {s.region for s in program.spaces}!=set(regions):
        raise ValueError(f'Assign each final region exactly once: {sorted(regions)}')
    for name,p in regions.items():
        if p.geom_type!='Polygon' or p.interiors:raise ValueError(f'Final space {name} has disconnected pieces or a hole. Cut that region further into separate connected spaces before assigning them. Geometry: {p.wkt[:1400]}')
    coordinates=lambda p:[(round(x,6),round(y,6)) for x,y in list(p.exterior.coords)[:-1]]
    zones=[{'id':s.region,'name':s.name,'kind':s.kind,'enclosed':s.enclosed,'purpose':s.purpose,'requirement_ids':s.requirement_ids,'polygon':coordinates(regions[s.region])} for s in program.spaces]
    for outdoor in program.outdoors:
        p=polygon(outdoor.polygon,outdoor.name)
        if outdoor.clip_to_site:
            if site is None:raise ValueError('Clipping an outdoor zone needs a supplied site')
            p=p.intersection(Polygon(site.boundary)).difference(shell).buffer(0)
            if p.geom_type!='Polygon' or p.is_empty or p.interiors:raise ValueError(f'{outdoor.name}: clipping must leave one simple polygon')
            notes.append(f'{outdoor.name}: proposed envelope clipped to the site and outside the building; measured area is the resulting polygon.')
        zones.append({'id':outdoor.id,'name':outdoor.name,'kind':outdoor.kind,'location':'outside','polygon':coordinates(p),'purpose':outdoor.purpose,'requirement_ids':outdoor.requirement_ids})
    openings=[];problems=[]
    adjacent={name:[k for k,p in regions.items() if k!=name and region.boundary.intersection(p.boundary).length>.2]+(['outside'] if region.boundary.intersection(shell.boundary).length>.2 else []) for name,region in regions.items()}
    resolved_links=[];spaces={s.region:s for s in program.spaces};outdoor_polygons={z['id']:Polygon(z['polygon']) for z in zones if z.get('location')=='outside'};external_targets={}
    for i,link in enumerate(program.connections):
        if link.from_zone in outdoor_polygons and link.to_zone in regions:link=link.model_copy(update={'from_zone':link.to_zone,'to_zone':link.from_zone})
        if link.to_zone in outdoor_polygons and link.from_zone in regions:
            external_targets[f'{i+1}-1']=(link.to_zone,outdoor_polygons[link.to_zone].boundary)
            notes.append(f'{link.from_zone}: exterior opening targets the named outdoor space {link.to_zone}; shared boundary derived from both polygons.')
            link=link.model_copy(update={'to_zone':'outside','allow_public_path':False})
        if link.from_zone=='outside' and link.to_zone in regions:link=link.model_copy(update={'from_zone':link.to_zone,'to_zone':'outside'})
        if link.from_zone not in regions or (link.to_zone!='outside' and link.to_zone not in regions):raise ValueError(f'Connection {link.from_zone} to {link.to_zone} references an unassigned interior zone. Final interior IDs: {sorted(regions)}. Exterior connections must use to_zone=outside, not an outdoor zone ID.')
        path=[link.from_zone,link.to_zone]
        if link.allow_public_path and link.to_zone not in adjacent[link.from_zone]:
            # Only an explicit request may derive intermediate doors. Private rooms are never a shortcut.
            queue=[[link.from_zone]];found=None;visited={link.from_zone}
            while queue:
                route=queue.pop(0)
                for k in adjacent[route[-1]]:
                    if k in visited:continue
                    if k==link.to_zone:found=route+[k];break
                    if k!='outside' and not spaces[k].enclosed and spaces[k].kind in ('circulation','living','retail'):queue.append(route+[k]);visited.add(k)
                if found:break
            if found:path=found;notes.append(f'Connection {link.from_zone} to {link.to_zone}: explicitly requested public path through '+', '.join(found[1:-1])+'. Door positions derived from actual shared walls.')
        resolved_links += [(f'{i+1}-{j+1}',link.model_copy(update={'from_zone':start,'to_zone':end})) for j,(start,end) in enumerate(zip(path,path[1:]))]
    pending=list(program.auto_access)
    if len({a.region for a in pending})!=len(pending):raise ValueError('Give each space one automatic access intent')
    if any(a.region not in regions for a in pending):raise ValueError('Automatic access references an unassigned region')
    def reached_regions():
        reached={'outside'}
        while True:
            new=set(reached)
            for _,link in resolved_links:
                if link.from_zone in reached:new.add(link.to_zone)
                if link.to_zone in reached:new.add(link.from_zone)
            if new==reached:return reached
            reached=new
    while pending:
        reached=reached_regions();progress=False
        for access in list(pending):
            choices=[]
            for neighbour in adjacent[access.region]:
                if neighbour=='outside' or neighbour not in reached or spaces[neighbour].kind not in access.from_kinds:continue
                shared=regions[access.region].boundary.intersection(regions[neighbour].boundary)
                lines=[shared] if shared.geom_type=='LineString' else list(getattr(shared,'geoms',[]))
                longest=max((LineString([a,b]).length for line in lines if line.geom_type=='LineString' for a,b in zip(list(line.coords),list(line.coords)[1:])),default=0)
                if longest>=access.width+.2:choices.append((longest,neighbour))
            if choices:
                neighbour=max(choices)[1];resolved_links.append(('auto-'+access.region,Connection(from_zone=access.region,to_zone=neighbour,width=access.width,kind=access.kind)))
                notes.append(f'{access.region}: shared-wall access derived to {neighbour}, within the model-requested access kinds and width.')
                pending.remove(access);progress=True
        if not progress:
            feedback=[{'region':a.region,'permitted_kinds':a.from_kinds,'neighbours':[{'id':k,'kind':spaces[k].kind,'already_reached':k in reached} for k in adjacent[a.region] if k!='outside']} for a in pending]
            raise ValueError('Automatic access could not reach these regions: '+str(feedback)+'. Change geometry or explicitly permit an appropriate adjacent kind; no private-room shortcuts are invented.')
    for identifier,link in resolved_links:
        a=regions[link.from_zone].boundary;b=external_targets[identifier][1] if identifier in external_targets else shell.boundary if link.to_zone=='outside' else regions[link.to_zone].boundary
        shared=a.intersection(b);parts=[shared] if shared.geom_type=='LineString' else list(getattr(shared,'geoms',[]));walls=[]
        for part in parts:
            if part.geom_type!='LineString':continue
            coords=list(part.coords)
            for start,end in zip(coords,coords[1:]):
                line=LineString([start,end])
                if line.length>=link.width+.2:walls.append(line)
        if not walls:
            max_length=max((LineString([a,b]).length for part in parts if part.geom_type=='LineString' for a,b in zip(list(part.coords),list(part.coords)[1:])),default=0)
            problems.append(f'{link.from_zone} to {link.to_zone}: requested opening {link.width:g} m needs a straight wall at least {link.width+.2:g} m; longest shared segment is {max_length:.3f} m.');continue
        hint=Point(link.preferred_point) if link.preferred_point else None
        wall=min(walls,key=lambda w:(w.distance(hint),-w.length)) if hint else max(walls,key=lambda w:w.length)
        centre=wall.project(hint) if hint else wall.length/2
        centre=max(link.width/2+.1,min(wall.length-link.width/2-.1,centre))
        if any({o['from_zone'],o['to_zone']}=={link.from_zone,link.to_zone} and o['kind']==link.kind for o in openings):continue
        openings.append({'id':f'opening-{identifier}','from_zone':link.from_zone,'to_zone':link.to_zone,'kind':link.kind,
                         'outside_zone_id':external_targets[identifier][0] if identifier in external_targets else None,
                         'segment':[list(wall.interpolate(centre-link.width/2).coords[0]),list(wall.interpolate(centre+link.width/2).coords[0])]})
    if problems:raise ValueError('; '.join(problems)+' Actual adjacency graph: '+str(adjacent))
    return DesignPlan(title=program.title,rationale=program.rationale,footprint=coordinates(shell),zones=zones,openings=openings,
                      assumptions=program.assumptions+(['Geometry derivations: '+' '.join(notes)] if notes else []),tradeoffs=program.tradeoffs,layout_program=program)

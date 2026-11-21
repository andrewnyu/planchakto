"""Typed staged-planning contracts. Proposals are not confirmed engineering inputs."""
from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from .domain import Model

XY=tuple[float,float]
Stage=Literal['programme','strategy','layout','details','approval','inputs','checks','outputs']
STAGES=['programme','strategy','layout','details','approval','inputs','checks','outputs']
Kind=Literal['retail','storage','office','service','kitchen','bathroom','living','bedroom','circulation','loading','parking','outdoor','landscape','future']
Source=Literal['user','drawing','proposal','code_table']


class Value(Model):
    value:float|None=None
    source:Source='user'
    basis:str=Field(default='Not supplied',max_length=500)


class Requirement(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name:str=Field(min_length=1,max_length=80)
    kind:Kind
    area_m2:float|None=Field(default=None,gt=0,le=250000)
    area_mode:Literal['target','minimum','maximum','exact']='target'
    count:int=Field(default=1,ge=1,le=100)
    included_in:str|None=None
    prefer_rectangle:bool=False
    source:Source='proposal'
    basis:str=Field(default='Proposed space allowance; review before confirming the programme',max_length=500)


class Programme(Model):
    name:str=Field(min_length=1,max_length=100)
    use:str=Field(min_length=1,max_length=200)
    total_area_m2:float|None=Field(default=None,gt=0,le=250000)
    area_mode:Literal['target','minimum','maximum','exact']='target'
    area_source:Source='proposal'
    area_basis:str=Field(default='Proposed planning scale',max_length=500)
    storeys:int=Field(default=1,ge=1,le=20)
    requirements:list[Requirement]=Field(default_factory=list,max_length=60)
    parking_spaces:int|None=Field(default=None,ge=0,le=2000)
    accessible_spaces:int|None=Field(default=None,ge=0,le=100)
    cashier_counters:int|None=Field(default=None,ge=0,le=100)
    capacity_source:Source='proposal'
    capacity_basis:str=Field(default='Proposed operating capacity; confirm with the operator',max_length=500)
    customer_flow:str=Field(default='',max_length=1200)
    delivery_flow:str=Field(default='',max_length=1200)
    priorities:list[str]=Field(default_factory=list,max_length=12)
    unresolved:list[str]=Field(default_factory=list,max_length=20)

    @model_validator(mode='after')
    def references(self):
        ids=[r.id for r in self.requirements]
        if len(ids)!=len(set(ids)):raise ValueError('Programme requirement identifiers must be unique')
        parents={r.id:r.included_in for r in self.requirements}
        for r in self.requirements:
            seen={r.id};p=r.included_in
            while p:
                if p not in parents or p in seen:raise ValueError('Included-area references must form an acyclic programme hierarchy')
                seen.add(p);p=parents[p]
        if self.accessible_spaces is not None and self.parking_spaces is not None and self.accessible_spaces>self.parking_spaces:
            raise ValueError('Accessible bays are included in the parking total and cannot exceed it')
        return self


class ProgrammeReply(Model):
    programme:Programme
    questions:list[str]=Field(default_factory=list,max_length=8)
    reply:str=Field(default='',max_length=2000)


class Gate(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name:str=Field(max_length=80)
    centre:XY
    width:float=Field(gt=.1,le=100)
    use:Literal['customer','service','shared','pedestrian']='customer'


class Route(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name:str=Field(max_length=80)
    kind:Literal['customer_vehicle','service_vehicle','customer','service','pedestrian','interior','egress']=Field(description='customer_vehicle/service_vehicle are vehicles; pedestrian/interior/egress are walking routes. Legacy customer/service also mean VEHICLES, never a customer walkway.')
    points:list[XY]=Field(min_length=2,max_length=40)
    width:float=Field(gt=.1,le=30)
    vehicle_id:str|None=None
    auto_route:bool=Field(default=False,description='Explicitly request deterministic routing between these waypoints inside the site/building; vehicle turning remains unverified')
    requested_points:list[XY]|None=Field(default=None,max_length=40,description='Original waypoints retained by code when automatic routing resolves the path')
    basis:str=Field(default='Proposed circulation envelope; operational and statutory suitability unverified',max_length=500)


class Strategy(Model):
    title:str=Field(min_length=1,max_length=100)
    rationale:str=Field(min_length=1,max_length=1800)
    gates:list[Gate]=Field(default_factory=list,max_length=8)
    routes:list[Route]=Field(default_factory=list,max_length=12)
    customer_arrival:str=Field(default='',max_length=1000)
    receiving_strategy:str=Field(default='',max_length=1000)
    public_private_strategy:str=Field(default='',max_length=1000)
    reserve_strategy:str=Field(default='',max_length=1000)
    assumptions:list[str]=Field(default_factory=list,max_length=16)
    unresolved:list[str]=Field(default_factory=list,max_length=16)
    site_unavailable:bool=False


class StrategyReply(Model):
    strategies:list[Strategy]=Field(min_length=1,max_length=3)
    reply:str=Field(default='',max_length=2000)


class ArrayRecipe(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    zone_id:str=Field(max_length=48)
    kind:Literal['rack','shelf','display','parking','accessible_parking','cashier','counter','desk','bed','table','cabinet','equipment','wc','urinal','basin','sink','shower','locker','server','panel','safe','cleaner']
    name:str=Field(max_length=80)
    origin:XY|None=None
    angle:float=Field(default=0,ge=-180,le=180)
    packing:Literal['grid','fill']='grid'
    target_count:int|None=Field(default=None,ge=1,le=10000)
    item_width:float=Field(gt=.1,le=50)
    item_depth:float=Field(gt=.1,le=50)
    rows:int=Field(default=1,ge=1,le=100)
    columns:int=Field(default=1,ge=1,le=200)
    gap_x:float=Field(default=.6,ge=0,le=30)
    gap_y:float=Field(default=2,ge=0,le=30)
    edge_margin:float=Field(default=.6,ge=0,le=20)
    access_side:Literal['front','back','left','right']='front'
    access_clearance:float=Field(default=.6,ge=0,le=10)
    requirement_id:str|None=None
    source:Source='proposal'
    basis:str=Field(default='Proposed fit-out dimensions, not a verified equipment specification',max_length=500)


class SupportRoomRecipe(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name:str=Field(max_length=80)
    kind:Kind
    width:float=Field(gt=1,le=30)
    depth:float=Field(gt=1,le=30)
    requirement_id:str|None=None
    fixtures:list[Literal['wc','urinal','basin','sink','shower','locker','bed','desk','server','panel','safe','cleaner']]=Field(default_factory=list,max_length=12)


class SupportPack(Model):
    zone_id:str
    hallway_width:float=Field(default=1.5,ge=1,le=10)
    rooms:list[SupportRoomRecipe]=Field(min_length=1,max_length=30)
    basis:str=Field(default='Proposed support-room layout; accessibility and fixture demand require checking',max_length=500)


class DetailRecipe(Model):
    title:str=Field(min_length=1,max_length=100)
    arrays:list[ArrayRecipe]=Field(default_factory=list,max_length=48)
    support_packs:list[SupportPack]=Field(default_factory=list,max_length=8)
    routes:list[Route]=Field(default_factory=list,max_length=20)
    assumptions:list[str]=Field(default_factory=list,max_length=20)
    unplaced:list[str]=Field(default_factory=list,max_length=20)


class Item(Model):
    id:str
    zone_id:str
    kind:str
    name:str
    polygon:list[XY]=Field(min_length=3,max_length=12)
    access_polygon:list[XY]=Field(default_factory=list,max_length=12)
    requirement_id:str|None=None
    source:Source='proposal'
    basis:str='Proposed fit-out'
    room_id:str|None=None


class SupportRoom(Model):
    id:str
    zone_id:str
    name:str
    kind:Kind
    polygon:list[XY]
    door:tuple[XY,XY]
    requirement_id:str|None=None


class DetailedPlan(Model):
    title:str
    recipe:DetailRecipe
    items:list[Item]=Field(default_factory=list,max_length=10000)
    rooms:list[SupportRoom]=Field(default_factory=list,max_length=240)
    routes:list[Route]=Field(default_factory=list,max_length=30)
    warnings:list[str]=Field(default_factory=list,max_length=100)


class Criteria(Model):
    min_customer_aisle:Value=Field(default_factory=Value)
    min_staff_aisle:Value=Field(default_factory=Value)
    min_parking_aisle:Value=Field(default_factory=Value)
    min_door_width:Value=Field(default_factory=Value)
    max_egress_travel:Value=Field(default_factory=Value)
    occupant_area_factor:Value=Field(default_factory=Value)
    exit_width_per_person_mm:Value=Field(default_factory=Value)
    @model_validator(mode='after')
    def positive(self):
        for field in type(self).model_fields:
            v=getattr(self,field).value
            if v is not None and v<=0:raise ValueError('Screening criteria must be positive or missing')
        return self


class Vehicle(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name:str=Field(max_length=80)
    length:float=Field(gt=.5,le=40)
    width:float=Field(gt=.5,le=5)
    min_turn_radius:float|None=Field(default=None,gt=1,le=100)
    source:Source='user'
    basis:str=Field(min_length=1,max_length=500)


class Load(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name:str=Field(max_length=80)
    zone_id:str
    watts:Value=Field(default_factory=Value)
    quantity:int=Field(default=1,ge=1,le=10000)
    circuit:str=Field(max_length=48)


class CircuitInput(Model):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    voltage:Value=Field(default_factory=Value)
    power_factor:Value=Field(default_factory=Value)
    demand_factor:Value=Field(default_factory=Value)
    phases:Literal[1,3]|None=None
    @model_validator(mode='after')
    def ranges(self):
        if self.voltage.value is not None and self.voltage.value<=0:raise ValueError('Voltage must be positive')
        if self.power_factor.value is not None and not 0<self.power_factor.value<=1:raise ValueError('Power factor must be greater than zero and at most one')
        if self.demand_factor.value is not None and not 0<=self.demand_factor.value<=1:raise ValueError('Demand factor must be between zero and one')
        return self


class UtilityPoint(Model):
    id:str
    kind:Literal['panel','water','drain']
    point:XY
    source:Source='user'
    basis:str=Field(min_length=1,max_length=500)


class RateInput(Model):
    id:str
    rate:float|None=Field(default=None,ge=0)
    source:Source='user'
    basis:str=Field(default='Not priced',max_length=500)


class EngineeringInputs(Model):
    height:Value=Field(default_factory=Value)
    dead_kpa:Value=Field(default_factory=Value)
    live_kpa:Value=Field(default_factory=Value)
    soil_kpa:Value=Field(default_factory=Value)
    bay_span:Value=Field(default_factory=Value)
    tributary_width:Value=Field(default_factory=Value)
    elastic_modulus_mpa:Value=Field(default_factory=Value)
    yield_strength_mpa:Value=Field(default_factory=Value)
    dead_factor:Value=Field(default_factory=Value)
    live_factor:Value=Field(default_factory=Value)
    deflection_ratio:Value=Field(default_factory=Value)
    footing_width:Value=Field(default_factory=Value)
    footing_thickness:Value=Field(default_factory=Value)
    footing_load_kn:Value=Field(default_factory=Value)
    drain_fall:Value=Field(default_factory=Value)
    drain_slope:Value=Field(default_factory=Value)
    slab_thickness:Value=Field(default_factory=Value)
    budget:Value=Field(default_factory=Value)
    structural_model:Literal['not_selected','simply_supported_steel_roof_bay','other']='not_selected'
    beam_section:Literal['RHS150','RHS200','RHS250']|None=None
    beam_self_weight:Literal['included_in_dead_load','add_section_weight']|None=None
    occupancy:str|None=Field(default=None,max_length=100)
    criteria:Criteria=Field(default_factory=Criteria)
    vehicles:list[Vehicle]=Field(default_factory=list,max_length=12)
    loads:list[Load]=Field(default_factory=list,max_length=300)
    circuits:list[CircuitInput]=Field(default_factory=list,max_length=60)
    utilities:list[UtilityPoint]=Field(default_factory=list,max_length=20)
    rates:list[RateInput]=Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def bounded_inputs(self):
        positive=['height','soil_kpa','bay_span','tributary_width','elastic_modulus_mpa','yield_strength_mpa','dead_factor','live_factor','deflection_ratio','footing_width','footing_thickness','slab_thickness','drain_slope']
        for key in positive:
            v=getattr(self,key).value
            if v is not None and v<=0:raise ValueError(f'{key} must be positive or missing')
        for key in ['dead_kpa','live_kpa','drain_fall','budget','footing_load_kn']:
            v=getattr(self,key).value
            if v is not None and v<0:raise ValueError(f'{key} cannot be negative')
        for collection in [self.vehicles,self.loads,self.circuits,self.utilities,self.rates]:
            ids=[x.id for x in collection]
            if len(ids)!=len(set(ids)):raise ValueError('Engineering item identifiers must be unique within each schedule')
        ids={c.id for c in self.circuits}
        if any(l.circuit not in ids for l in self.loads):raise ValueError('Every load must reference a supplied circuit')
        if any(l.watts.value is not None and l.watts.value<0 for l in self.loads):raise ValueError('Load wattages cannot be negative')
        return self


class Finding(Model):
    id:str
    discipline:str
    status:Literal['pass','fail','missing_input','unsupported','not_checked','warning']
    title:str
    evidence:str
    objects:list[str]=Field(default_factory=list)
    values:dict=Field(default_factory=dict)
    basis:str='Deterministic planning screen; not certification'

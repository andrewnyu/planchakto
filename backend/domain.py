"""BuildGraph schema. SI at boundaries; no implicit conversion or missing-as-zero."""
from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import hashlib, json, math

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Point(Model):
    x: float
    y: float
    z: float = 0

class Parameter(Model):
    value: float | None
    unit: str
    source: str = 'Synthetic example — not verified project data'
    basis: str = 'demonstration'

class Room(Model):
    id: str
    name: str
    kind: Literal['living','kitchen','bathroom','bedroom','office','corridor']
    x: float
    y: float
    w: float = Field(gt=0, le=30)
    h: float = Field(gt=0, le=30)
    min_area: float = Field(default=6, gt=0)
    max_area: float = Field(default=40, gt=0)
    min_dimension: float = Field(default=2, gt=0)
    locked: bool = False

class Column(Model):
    id: str
    x: float
    y: float
    active: bool = True
    locked: bool = False

class Fixture(Model):
    id: str
    name: str
    room_id: str
    dx: float
    dy: float
    elevation: float = 0
    kind: Literal['sink','wc','basin']

class Equipment(Model):
    id: str
    name: str
    room_id: str
    dx: float
    dy: float
    watts: float | None = Field(default=None, ge=0, le=100000)
    circuit_id: str
    source: str = 'Synthetic nameplate rating'

class Circuit(Model):
    id: str
    name: str
    voltage: float = Field(default=230, gt=0)
    power_factor: float = Field(default=1, gt=0, le=1)
    demand_factor: float = Field(default=1, gt=0, le=1)

class Furniture(Model):
    id: str
    name: str
    room_id: str
    dx: float
    dy: float
    w: float = Field(gt=0)
    h: float = Field(gt=0)
    clearance: float = Field(default=.6, ge=0)
    locked: bool = False

class Obstacle(Model):
    id: str
    name: str
    x: float
    y: float
    w: float = Field(gt=0)
    h: float = Field(gt=0)

class Site(Model):
    boundary: list[Point]
    survey: list[Point]
    units: Literal['m'] = 'm'
    crs: str = 'LOCAL_ENGINEERING'
    origin: Point = Field(default_factory=lambda: Point(x=0,y=0,z=100))
    datum: str = 'Synthetic local benchmark, 100 m'
    north: float = 0
    setback: float = Field(default=1, ge=0)
    setback_source: str = 'User demonstration criterion; not a verified jurisdictional requirement'
    platform_elevation: float = 0
    access: Point = Field(default_factory=lambda: Point(x=0,y=4.75))
    water: Point = Field(default_factory=lambda: Point(x=13,y=1))
    drain: Point = Field(default_factory=lambda: Point(x=13,y=1,z=-.4))
    panel: Point = Field(default_factory=lambda: Point(x=1,y=4.75,z=0))

class Engineering(Model):
    dead: Parameter = Field(default_factory=lambda: Parameter(value=.65, unit='kPa'))
    live: Parameter = Field(default_factory=lambda: Parameter(value=.75, unit='kPa'))
    soil: Parameter = Field(default_factory=lambda: Parameter(value=100, unit='kPa', basis='gross allowable service'))
    dead_factor: float = Field(default=1.2, gt=0, le=5)
    live_factor: float = Field(default=1.6, gt=0, le=5)
    combination_source: str = 'Illustrative user-supplied 1.2D + 1.6L; not a code compliance claim'
    elastic_modulus: float = Field(default=200000, gt=0) # MPa
    yield_strength: float = Field(default=250, gt=0) # MPa
    section: Literal['RHS150','RHS200','RHS250'] = 'RHS200'
    deflection_ratio: float = Field(default=240, gt=1)
    footing_width: float = Field(default=1.2, gt=0, le=5)
    footing_thickness: float = Field(default=.3, gt=0, le=2)
    drain_slope: float = Field(default=.01, gt=0, le=.2)
    wind: Parameter = Field(default_factory=lambda: Parameter(value=None, unit='kPa', basis='unsupported — unused by solver'))
    seismic: Parameter = Field(default_factory=lambda: Parameter(value=None, unit='g', basis='unsupported — unused by solver'))

class Rate(Model):
    id: str
    name: str
    unit: str
    rate: float = Field(ge=0)
    waste: float = Field(default=.05, ge=0, le=1)
    stock: float | None = Field(default=None, gt=0)
    source: str = 'Demonstration catalog, not market pricing'
    date: str = '2026-10-13'

class Brief(Model):
    use: str = 'Small studio residence'
    budget: float = Field(default=900000, gt=0)
    wet_adjacency: bool = True
    area_weight: int = Field(default=5, ge=0, le=100)
    change_weight: int = Field(default=2, ge=0, le=100)
    wet_weight: int = Field(default=8, ge=0, le=100)

class Building(Model):
    id: str = 'bg-studio'
    name: str = 'San Isidro Studio'
    description: str = 'Synthetic Philippine project · preliminary planning'
    width: float = Field(default=12, gt=0, le=30)
    depth: float = Field(default=9, gt=0, le=30)
    height: float = Field(default=3, gt=0, le=6)
    roof_id: str = 'roof-01'
    slab_id: str = 'slab-01'
    grid_x: list[float] = Field(default_factory=lambda:[0,4,8,12])
    grid_y: list[float] = Field(default_factory=lambda:[0,3.5,9])
    rooms: list[Room]
    columns: list[Column]
    fixtures: list[Fixture]
    equipment: list[Equipment]
    circuits: list[Circuit]
    furniture: list[Furniture]
    obstacles: list[Obstacle] = []
    site: Site
    engineering: Engineering = Field(default_factory=Engineering)
    brief: Brief = Field(default_factory=Brief)
    rates: list[Rate]
    routing_mode: Literal['direct','avoid'] = 'avoid'
    @model_validator(mode='after')
    def references(self):
        objects = self.rooms+self.columns+self.fixtures+self.equipment+self.circuits+self.furniture+self.obstacles+self.rates
        ids = [x.id for x in objects]
        if len(ids)!=len(set(ids)): raise ValueError('Object identifiers must be unique')
        rooms={r.id for r in self.rooms}; circuits={c.id for c in self.circuits}
        for item in self.fixtures+self.equipment+self.furniture:
            if item.room_id not in rooms: raise ValueError(f'Unknown room {item.room_id}')
        for item in self.equipment:
            if item.circuit_id not in circuits: raise ValueError(f'Unknown circuit {item.circuit_id}')
        for grid,maximum in [(self.grid_x,self.width),(self.grid_y,self.depth)]:
            if len(grid)<2 or grid != sorted(set(grid)) or grid[0]!=0 or grid[-1]!=maximum: raise ValueError('Grid must increase strictly from 0 to building extent')
        for p in (self.engineering.dead,self.engineering.live,self.engineering.soil):
            if p.value is not None and p.value<0: raise ValueError('Loads and bearing pressure must be nonnegative')
        return self

class MoveRoom(Model):
    type: Literal['move_room']
    room_id: str
    x: float
    y: float
    w: float | None = Field(default=None, gt=0)
    h: float | None = Field(default=None, gt=0)
class SwapRooms(Model):
    type: Literal['swap_rooms']
    first: str
    second: str
class SetParameter(Model):
    type: Literal['set_parameter']
    field: Literal['dead','live','soil','dead_factor','live_factor','deflection_ratio','footing_width','drain_slope','section']
    value: float | str | None
    source: str = 'User-entered project assumption'
class RemoveColumn(Model):
    type: Literal['remove_column']
    column_id: str
class SetEquipment(Model):
    type: Literal['set_equipment']
    equipment_id: str
    watts: float = Field(ge=0, le=100000)
class SetLock(Model):
    type: Literal['set_lock']
    object_id: str
    locked: bool
class Reroute(Model):
    type: Literal['reroute']
    mode: Literal['direct','avoid'] = 'avoid'
class SetBrief(Model):
    type: Literal['set_brief']
    brief: Brief
class SetSite(Model):
    type: Literal['set_site']
    site: Site
class SetRate(Model):
    type: Literal['set_rate']
    rate_id: str
    rate: float = Field(ge=0)
    waste: float = Field(ge=0, le=1)
class SetGrid(Model):
    type: Literal['set_grid']
    x: list[float]
    y: list[float]
class MoveFurniture(Model):
    type: Literal['move_furniture']
    furniture_id: str
    dx: float
    dy: float

class MoveFixture(Model):
    type: Literal['move_fixture']
    fixture_id: str
    dx: float
    dy: float
    elevation: float | None = None
class MoveEquipment(Model):
    type: Literal['move_equipment']
    equipment_id: str
    dx: float
    dy: float
    circuit_id: str
class AddElement(Model):
    type: Literal['add_element']
    kind: Literal['fixture','equipment','furniture']
    id: str = Field(min_length=1,max_length=100)
    room_id: str
    name: str = Field(min_length=1,max_length=100)
    dx: float
    dy: float
    watts: float | None = Field(default=None,ge=0,le=100000)
    circuit_id: str | None = None
    fixture_kind: Literal['sink','wc','basin'] = 'basin'
    w: float = Field(default=1.2,gt=0,le=5)
    h: float = Field(default=.6,gt=0,le=5)
class SetRoomRequirements(Model):
    type: Literal['set_room_requirements']
    room_id: str
    min_area: float = Field(gt=0)
    max_area: float = Field(gt=0)
    min_dimension: float = Field(gt=0)

Command = Annotated[MoveRoom|SwapRooms|SetParameter|RemoveColumn|SetEquipment|SetLock|Reroute|SetBrief|SetSite|SetRate|SetGrid|MoveFurniture|MoveFixture|MoveEquipment|AddElement|SetRoomRequirements,Field(discriminator='type')]
class CommandRequest(Model):
    base_revision: str
    command_id: str = Field(min_length=1,max_length=128)
    commands: list[Command] = Field(min_length=1,max_length=50)
    label: str = Field(default='Design revision',max_length=120)

DEPENDENCIES={
 'move_room':['geometry','layout','routing','fitout','quantities'],
 'swap_rooms':['geometry','layout','routing','fitout','quantities'],
 'set_parameter':['structure','foundations','routing','quantities'],
 'remove_column':['geometry','structure','foundations','routing','quantities'],
 'set_equipment':['electrical','quantities'], 'set_lock':['constraints'],
 'reroute':['routing','quantities'], 'set_brief':['layout','budget'],
 'set_site':['terrain','layout','routing','quantities'],
 'set_rate':['quantities','budget'], 'set_grid':['geometry','structure','foundations','routing','quantities'],
 'move_furniture':['fitout','routing','quantities'], 'move_fixture':['routing','quantities'], 'move_equipment':['routing','electrical','quantities'], 'add_element':['routing','electrical','fitout','quantities'], 'set_room_requirements':['layout']}

def digest(value):
    if isinstance(value,BaseModel): value=value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def convert(value: float, source: str, target: str)->float:
    units={'m':('length',1),'mm':('length',.001),'ft':('length',.3048),'kPa':('pressure',1000),'Pa':('pressure',1),'MPa':('pressure',1e6),'kN':('force',1000),'N':('force',1)}
    if not math.isfinite(value) or source not in units or target not in units or units[source][0]!=units[target][0]: raise ValueError('Invalid value or incompatible units')
    return value*units[source][1]/units[target][1]

def apply_commands(model: Building, commands:list[Command]):
    b=model.model_copy(deep=True); invalidated=set()
    def obj(group,id):
        item=next((v for v in group if v.id==id),None)
        if item is None: raise ValueError(f'Unknown object {id}')
        return item
    def unlocked(item):
        if item.locked: raise ValueError(f'{item.id} is locked; unlock it explicitly before changing it')
    for cmd in commands:
        invalidated.update(DEPENDENCIES[cmd.type])
        if isinstance(cmd,MoveRoom):
            r=obj(b.rooms,cmd.room_id); unlocked(r)
            if any(f.locked and f.room_id==r.id for f in b.furniture): raise ValueError('Room contains a locked placement')
            r.x,r.y=cmd.x,cmd.y
            if cmd.w is not None:r.w=cmd.w
            if cmd.h is not None:r.h=cmd.h
        elif isinstance(cmd,SwapRooms):
            a,c=obj(b.rooms,cmd.first),obj(b.rooms,cmd.second); unlocked(a); unlocked(c)
            if any(f.locked and f.room_id in [a.id,c.id] for f in b.furniture): raise ValueError('Room contains a locked placement')
            a.x,c.x=c.x,a.x; a.y,c.y=c.y,a.y; a.w,c.w=c.w,a.w; a.h,c.h=c.h,a.h
        elif isinstance(cmd,SetParameter):
            if cmd.field in ['dead','live','soil']:
                old=getattr(b.engineering,cmd.field)
                setattr(b.engineering,cmd.field,Parameter(value=cmd.value,unit=old.unit,source=cmd.source,basis=old.basis))
            else:setattr(b.engineering,cmd.field,cmd.value)
        elif isinstance(cmd,RemoveColumn):
            c=obj(b.columns,cmd.column_id); unlocked(c); c.active=False
        elif isinstance(cmd,SetEquipment):obj(b.equipment,cmd.equipment_id).watts=cmd.watts
        elif isinstance(cmd,SetLock):obj(b.rooms+b.columns+b.furniture,cmd.object_id).locked=cmd.locked
        elif isinstance(cmd,Reroute):b.routing_mode=cmd.mode
        elif isinstance(cmd,SetBrief):b.brief=cmd.brief
        elif isinstance(cmd,SetSite):b.site=cmd.site
        elif isinstance(cmd,SetRate):
            r=obj(b.rates,cmd.rate_id);r.rate=cmd.rate;r.waste=cmd.waste;r.source='User-edited estimate rate'
        elif isinstance(cmd,SetGrid):
            if any(c.locked for c in b.columns):raise ValueError('Grid change would alter locked columns')
            b.grid_x=cmd.x;b.grid_y=cmd.y
            b.columns=[Column(id=f'col-{i}-{j}',x=x,y=y) for j,y in enumerate(cmd.y) for i,x in enumerate(cmd.x)]
        elif isinstance(cmd,MoveFurniture):
            f=obj(b.furniture,cmd.furniture_id);unlocked(f);f.dx=cmd.dx;f.dy=cmd.dy
        elif isinstance(cmd,MoveFixture):
            f=obj(b.fixtures,cmd.fixture_id);f.dx=cmd.dx;f.dy=cmd.dy
            if cmd.elevation is not None:f.elevation=cmd.elevation
        elif isinstance(cmd,MoveEquipment):
            f=obj(b.equipment,cmd.equipment_id);f.dx=cmd.dx;f.dy=cmd.dy;f.circuit_id=cmd.circuit_id
        elif isinstance(cmd,AddElement):
            obj(b.rooms,cmd.room_id)
            if cmd.kind=='fixture':b.fixtures.append(Fixture(id=cmd.id,name=cmd.name,room_id=cmd.room_id,dx=cmd.dx,dy=cmd.dy,kind=cmd.fixture_kind))
            elif cmd.kind=='equipment':
                if not cmd.circuit_id:raise ValueError('Equipment must be assigned to a circuit')
                b.equipment.append(Equipment(id=cmd.id,name=cmd.name,room_id=cmd.room_id,dx=cmd.dx,dy=cmd.dy,watts=cmd.watts,circuit_id=cmd.circuit_id,source='User-entered nameplate rating'))
            else:b.furniture.append(Furniture(id=cmd.id,name=cmd.name,room_id=cmd.room_id,dx=cmd.dx,dy=cmd.dy,w=cmd.w,h=cmd.h))
        elif isinstance(cmd,SetRoomRequirements):
            if cmd.max_area<cmd.min_area:raise ValueError('Maximum area must be at least minimum area')
            r=obj(b.rooms,cmd.room_id);r.min_area=cmd.min_area;r.max_area=cmd.max_area;r.min_dimension=cmd.min_dimension
    return Building.model_validate(b.model_dump()),sorted(invalidated)

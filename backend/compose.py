"""New-project composer: a typed ProjectSpec becomes a complete, checkable Building, deterministically.

Gemini (see ai.compose_turn) only edits the spec and phrases questions. Everything that ends up in the model
(footprint, room rectangles, structural grid, sections, services, fire and seismic inputs) is decided here, so the same
spec always gives the same building, and an unanswered site-specific value stays a missing input instead of a guess.

Supported family, as for the rest of the engine: one storey, rectangular footprint up to 30 × 30 m, two strips of
rectangular rooms on either side of one full-width corridor entered from the west.
"""
from __future__ import annotations
import math, re
from typing import Any, Literal
from pydantic import Field
from .domain import (Building, Circuit, Column, Equipment, Extinguisher, ExitDoor, FireProtection, Fixture, Furniture,
                     Model, Parameter, Point, Room, Site)
from .example import example

Kind = Literal['living', 'kitchen', 'bathroom', 'bedroom', 'office', 'retail', 'storage']
Template = Literal['house', 'warehouse', 'commercial']
MAX_SIDE = 30.0
WET = ('kitchen', 'bathroom')


class RoomSpec(Model):
    name: str = Field(min_length=1, max_length=60)
    kind: Kind
    area: float = Field(ge=4, le=600)  # target m² per room
    count: int = Field(default=1, ge=1, le=12)


class ProjectSpec(Model):
    """What the user has decided. None means not decided yet; it is asked about, or stays a missing input."""
    template: Template
    name: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=120)
    use: str | None = Field(default=None, max_length=120)
    rooms: list[RoomSpec] = Field(min_length=1, max_length=20)
    corridor_width: float = Field(default=2.0, ge=1.5, le=3)
    height: float | None = Field(default=None, ge=2.7, le=6)
    budget: float | None = Field(default=None, gt=0, le=1e9)
    fire_occupancy: Literal['business', 'business_concentrated', 'mercantile', 'none'] | None = None
    fire_provisions: bool | None = None
    rear_exit: bool | None = None
    solar: Literal['none', '5', '10', 'fill'] | None = None
    fault_distance: Literal['far', 'near', 'unknown'] | None = None
    soil_profile: Literal['SA', 'SB', 'SC', 'SD', 'SE', 'unknown'] | None = None
    frame: Literal['steel_omrf', 'unknown'] | None = None
    friction: Literal['assumed', 'unknown'] | None = None


TEMPLATES: dict[str, dict[str, Any]] = {
    'house': {'label': 'House', 'name': 'New house', 'use': 'Single-storey house', 'corridor_width': 1.5, 'height': 3.0, 'fire_occupancy': 'none',
              'rooms': [('Living & dining', 'living', 24, 1), ('Kitchen', 'kitchen', 10, 1), ('Bathroom', 'bathroom', 6, 1), ('Bedroom', 'bedroom', 12, 2)]},
    'commercial': {'label': 'Commercial building', 'name': 'New commercial building', 'use': 'Single-storey commercial building', 'corridor_width': 2.0, 'height': 3.5,
                   'rooms': [('Showroom', 'retail', 60, 1), ('Office', 'office', 15, 2), ('Meeting room', 'office', 15, 1), ('Stockroom', 'storage', 20, 1),
                             ('Pantry', 'kitchen', 8, 1), ('Toilet', 'bathroom', 5, 2)]},
    'warehouse': {'label': 'Warehouse', 'name': 'New warehouse', 'use': 'Single-storey warehouse', 'corridor_width': 2.0, 'height': 6.0,
                  'rooms': [('Storage hall', 'storage', 300, 1), ('Loading bay', 'storage', 40, 1), ('Office', 'office', 15, 1), ('Toilet', 'bathroom', 5, 1), ('Pantry', 'kitchen', 6, 1)]},
}


def template_spec(template: str) -> ProjectSpec:
    t = TEMPLATES[template]
    return ProjectSpec(template=template, name=t['name'], use=t['use'], corridor_width=t['corridor_width'], fire_occupancy=t.get('fire_occupancy'),
                       rooms=[RoomSpec(name=n, kind=k, area=a, count=c) for n, k, a, c in t['rooms']])


def _opt(label, description, value): return {'label': label, 'description': description, 'value': value}


def questions_for(spec: ProjectSpec) -> list[dict]:
    """Deterministic questions for every undecided field that matters for this template, most important first."""
    t = spec.template; q = []
    budgets = {'house': [2.5e6, 3.5e6, 5e6], 'commercial': [6e6, 10e6, 15e6], 'warehouse': [8e6, 12e6, 20e6]}[t]
    if spec.budget is None:
        q.append({'field': 'budget', 'header': 'Budget', 'question': 'What construction budget should the estimate be compared against?',
                  'options': [_opt(f'₱{v / 1e6:g}M' + (' (Recommended)' if i == 1 else ''), 'Compared with the priced quantity takeoff', v) for i, v in enumerate(budgets)]})
    if spec.height is None:
        hs = {'house': [3.0, 3.5], 'commercial': [3.5, 4.0, 4.5], 'warehouse': [6.0, 5.0, 4.5]}[t]
        q.append({'field': 'height', 'header': 'Height', 'question': 'What eave height do you want?',
                  'options': [_opt(f'{h:g} m' + (' (Recommended)' if i == 0 else ''), 'Floor to roof beams; single storey', h) for i, h in enumerate(hs)]})
    if spec.fire_occupancy is None:
        if t == 'warehouse':
            opts = [_opt('Skip the fire screen (Recommended)', 'Storage occupancy is outside the implemented RA 9514 screen; it is reported as not screened', 'none'),
                    _opt('Screen as business occupancy', 'Treat the whole floor as offices; only valid if that is the real use', 'business')]
        else:
            opts = [_opt('Business (Recommended)', 'Offices and professional services, 9.3 m² per person', 'business'),
                    _opt('Mercantile', 'Shops and showrooms open to the public, 2.8 m² per person on the street floor', 'mercantile'),
                    _opt('Business, concentrated use', 'Call centres or BPO floors, 4.6 m² per person', 'business_concentrated')]
        q.append({'field': 'fire_occupancy', 'header': 'Occupancy', 'question': 'Which Fire Code occupancy should the egress screen use?', 'options': opts})
    if spec.fire_occupancy not in (None, 'none'):
        if spec.rear_exit is None:
            q.append({'field': 'rear_exit', 'header': 'Exits', 'question': 'Add a second exit at the east end of the corridor?',
                      'options': [_opt('Add a rear exit (Recommended)', 'Removes the dead end and gives two ways out', True), _opt('Main entrance only', 'Single west entrance', False)]})
        if spec.fire_provisions is None:
            q.append({'field': 'fire_provisions', 'header': 'Fire safety', 'question': 'Include fire safety provisions in the model now?',
                      'options': [_opt('Add them (Recommended)', 'Exit signs, emergency lighting, manual alarm and extinguishers placed to Table 7', True),
                                  _opt('Leave them out', 'The fire screen will list what is missing', False)]})
    if spec.solar is None:
        q.append({'field': 'solar', 'header': 'Solar PV', 'question': 'Add rooftop solar?',
                  'options': [_opt('No solar', 'Can be added later in the Engineering tab', 'none'), _opt('5 kWp', 'Typical small system', '5'),
                              _opt('10 kWp', 'Larger system; check the roof load and the utility screens', '10'), _opt('Fill the roof', 'As many modules as fit inside the edge setback', 'fill')]})
    if spec.fault_distance is None:
        q.append({'field': 'fault_distance', 'header': 'Fault', 'question': 'How far is the site from the nearest active fault (PHIVOLCS FaultFinder)?',
                  'options': [_opt('More than 15 km', 'Near-source factors Na = Nv = 1.0 (NSCP 2015 §208, verify)', 'far'),
                              _opt('Within 15 km', 'Na and Nv must be entered from the near-source tables; seismic checks wait for them', 'near'),
                              _opt('Not sure yet', 'Keep Na and Nv as missing inputs', 'unknown')]})
    if spec.soil_profile is None:
        q.append({'field': 'soil_profile', 'header': 'Soil', 'question': 'What soil profile does the site have?',
                  'options': [_opt('Not known yet: use SD (Recommended)', 'NSCP uses SD when soil properties are not known in sufficient detail', 'unknown'),
                              _opt('SC · very dense soil / soft rock', 'From a geotechnical report', 'SC'),
                              _opt('SE · soft soil', 'Ca must be entered from Table 208-7; the built-in transcription has no confirmed value', 'SE')]})
    if spec.frame is None:
        q.append({'field': 'frame', 'header': 'Frame', 'question': 'Which lateral system should the seismic screen assume?',
                  'options': [_opt('Steel ordinary moment frame', 'R = 4.5 (UBC-97 lineage; confirm in NSCP 2015 Table 208-11)', 'steel_omrf'),
                              _opt('Decide later', 'R stays a missing input', 'unknown')]})
    if spec.friction is None:
        q.append({'field': 'friction', 'header': 'Footings', 'question': 'Footing base friction for the sliding check?',
                  'options': [_opt('Assume 0.35 for now', 'Concrete on soil; replace with the geotechnical report value', 'assumed'), _opt('Leave missing', 'Sliding stays a missing input', 'unknown')]})
    return q


def apply_answer(spec: ProjectSpec, field: str, value) -> ProjectSpec:
    if field not in ProjectSpec.model_fields or field == 'template': raise ValueError(f'Unknown field {field}')
    return ProjectSpec.model_validate(spec.model_dump() | {field: value})


def _slug(text): return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:24] or 'room'
def _snap(v, step=.5): return round(v / step) * step


def _expand(spec: ProjectSpec):
    rooms = []; used = set()
    for r in spec.rooms:
        for i in range(r.count):
            name = f'{r.name} {i + 1:02d}' if r.count > 1 else r.name
            id = base = _slug(name); n = 2
            while id in used or id == 'hall': id = f'{base}-{n}'; n += 1
            used.add(id); rooms.append({'id': id, 'name': name, 'kind': r.kind, 'area': r.area})
    return rooms


def _layout(rooms, corridor):
    """Two strips around a full-width corridor. Wet rooms share a strip at its east end, the largest public room goes west."""
    order = sorted(rooms, key=lambda r: -r['area']); strips = [[], []]; wet = [r for r in rooms if r['kind'] in WET]
    area = lambda s: sum(r['area'] for r in s)
    for r in order:
        if r['kind'] in WET: continue
        strips[0 if area(strips[0]) <= area(strips[1]) else 1].append(r)
    target = 0 if area(strips[0]) <= area(strips[1]) else 1
    strips[target] += wet  # keep wet rooms together for short drains and the adjacency check
    strips = [s for s in strips if s] if not all(strips) else strips
    if len(strips) == 1:  # one room: put it on the north side of the corridor
        strips = [strips[0], []]
    total = sum(r['area'] for r in rooms)
    # Pick a width so the footprint is about 1.4 : 1, then derive each strip depth from its area.
    W = (1.4 * corridor + math.sqrt((1.4 * corridor) ** 2 + 4 * 1.4 * total)) / 2
    W = min(MAX_SIDE, math.ceil(W * 2) / 2)
    # Many narrow rooms need a longer, shallower building: widen until every strip fits, up to the 30 m limit.
    while True:
        try: return _place(strips, W, corridor, total)
        except _Narrow:
            if W >= MAX_SIDE: raise ValueError('The rooms do not fit along a 30 m building; reduce the number of rooms or combine small ones.')
            W = min(MAX_SIDE, W + .5)


class _Narrow(ValueError): pass


def _place(strips, W, corridor, total):
    area = lambda s: sum(r['area'] for r in s)
    depths = []
    for s in strips:
        if not s: depths.append(0.); continue
        d = max(2.5, _snap(area(s) / W))
        depths.append(d)
    D = depths[0] + corridor + depths[1]
    if D > MAX_SIDE + 1e-9 or total > MAX_SIDE * (MAX_SIDE - corridor):
        raise ValueError(f'The room programme ({total:.0f} m²) does not fit the supported single-storey footprint of {MAX_SIDE:g} × {MAX_SIDE:g} m. Reduce areas or room counts.')
    placed = []; first = None
    for k, (s, d) in enumerate(zip(strips, depths)):
        if not s: continue
        y = 0. if k == 0 else depths[0] + corridor
        mins = [1.5 if r['kind'] == 'bathroom' else 2.0 for r in s]
        widths = [max(m, _snap(r['area'] / d)) for r, m in zip(s, mins)]
        # Absorb rounding in the largest room so the strip spans the full width exactly.
        big = max(range(len(s)), key=lambda i: s[i]['area']); widths[big] += W - sum(widths)
        if widths[big] < mins[big]: raise _Narrow()
        if first is not None: widths = _align(widths, mins, first, W)
        x = 0.; cuts = []
        for r, w in zip(s, widths):
            placed.append({**r, 'x': x, 'y': y, 'w': w, 'h': d}); x += w; cuts.append(x)
        first = cuts[:-1]
    return W, D, depths, placed


def _align(widths, mins, targets, W):
    """Shift this strip's walls onto the other strip's walls when within 1.25 m, so columns can stand in shared walls
    clear of every corridor door. Rooms keep at least their minimum width and 70 % of their target width."""
    out = widths[:]; x = 0.
    for i in range(len(out) - 1):
        cut = x + out[i]; near = min(targets, key=lambda t: abs(t - cut), default=None)
        if near is not None and 0 < abs(near - cut) <= 1.25:
            w = near - x; rest = out[i] + out[i + 1] - w
            if w >= max(mins[i], .7 * widths[i]) and rest >= max(mins[i + 1], .7 * widths[i + 1]): out[i], out[i + 1] = w, rest
        x += out[i]
    return out


def _grid(W, D, depths, corridor, bay, placed, walls=True):
    # Columns go on room boundaries (inside walls) where they can; otherwise mid-room, never across a corridor door.
    bounds = sorted({0., W} | {r['x'] for r in placed} | {r['x'] + r['w'] for r in placed})
    # A corridor door spans x + 0.35 … x + 1.25; with the 0.4 m column clearance nothing may stand in (x, x + 1.75),
    # on either side of the corridor. A column exactly on the room's own boundary is clear of its door.
    doors = [(r['x'] + 1e-6, r['x'] + 1.75) for r in placed]
    clear = (lambda x: not any(a < x < c for a, c in doors)) if walls else (lambda x: True)
    # Fewest bays with every span in [1.5 m, bay], preferring wall positions, then even spans (shortest path).
    cand = sorted({round(i * .25, 2) for i in range(1, int(W * 4))} | set(bounds))
    cand = [0.] + [x for x in cand if 0 < x < W and clear(x)] + [W]
    best = {0: (0, 0., [0.])}
    for j in range(1, len(cand)):
        for i in range(j):
            if i not in best: continue
            span = cand[j] - cand[i]
            if not 1.5 - 1e-9 <= span <= bay + 1e-9: continue
            n, pen, path = best[i]
            score = (n + 1, pen + (0 if cand[j] in bounds else 1) + (bay - span) ** 2 / 100)
            if j not in best or score < best[j][:2]: best[j] = (*score, path + [cand[j]])
    if len(cand) - 1 not in best: return None, None
    gx = best[len(cand) - 1][2]
    if walls:
        lines = {0., D}
        if depths[0]: lines.add(depths[0])
        if depths[1]: lines.add(depths[0] + corridor)
        # Subdivide deep strips so roof beams carry at most about 4.5 m of roof each side.
        for a, c in [(0., depths[0]), (depths[0] + corridor, D)]:
            n = math.ceil((c - a) / 4.5 - 1e-9)
            for i in range(1, n): lines.add(round((a + (c - a) * i / n) * 4) / 4)
    else:
        # Column rows kept 0.5 m clear of the corridor, so no column stands at a corridor door; rows at most 4.5 m apart.
        lo, hi = depths[0] - .5, depths[0] + corridor + .5
        ys = [0.] + [i * .25 for i in range(1, int(D * 4)) if not lo < i * .25 < hi] + [D]
        reach = {0: [0.]}
        for j in range(1, len(ys)):
            options = [reach[i] for i in range(j) if i in reach and 1.5 - 1e-9 <= ys[j] - ys[i] <= 4.5 + 1e-9]
            if options: reach[j] = min(options, key=len) + [ys[j]]
        if len(ys) - 1 not in reach: return None, None
        lines = set(reach[len(ys) - 1])
    return gx, sorted(lines)


def _clear_point(room, cols, dx, dy):
    """Keep service points 0.6 m clear of columns so routes can connect."""
    for _ in range(20):
        px, py = room['x'] + dx, room['y'] + dy
        if all(max(abs(px - c.x), abs(py - c.y)) > .6 for c in cols): return dx, dy
        dx = min(room['w'] - .4, dx + .5) if dx + .5 < room['w'] - .4 else max(.4, dx - 1.5); dy = min(room['h'] - .4, dy + .3)
    return dx, dy


def _inward(r, hall, d):
    """A room-relative y d metres in from the room's exterior wall (the side away from the corridor)."""
    return d if r['y'] < hall.y else r['h'] - d


def _circuit(b, id, name):
    if all(c.id != id for c in b.circuits): b.circuits.append(Circuit(id=id, name=name))
    return id


def _equip(b, r, cols, key, label, dx, dy, watts, circuit, source):
    x, y = _clear_point(r, cols, dx, dy)
    b.equipment.append(Equipment(id=f'{key}-{r["id"]}', name=f'{r["name"]} {label}', room_id=r['id'], dx=x, dy=y, watts=watts, circuit_id=circuit, source=source))


def _fixture(b, r, cols, key, label, kind, dx, dy):
    x, y = _clear_point(r, cols, dx, dy)
    b.fixtures.append(Fixture(id=f'{key}-{r["id"]}', name=f'{r["name"]} {label}', room_id=r['id'], dx=x, dy=y, kind=kind))


def _house_bathroom(b, r, cols, hall):
    """Shower at the exterior wall with the WC and basin nearer the door; an outdoor shower is a cold rinse with no WC."""
    w = r['w']
    _fixture(b, r, cols, 'shower', 'shower', 'shower', w / 2, _inward(r, hall, .55))
    if 'shower' in r['name'].lower() and 'bath' not in r['name'].lower(): return
    _fixture(b, r, cols, 'wc', 'WC', 'wc', min(.45, w / 2), _inward(r, hall, 1.5))
    _fixture(b, r, cols, 'basin', 'basin', 'basin', *((max(w - .4, w / 2), _inward(r, hall, 1.5)) if w >= 1.4 else (w / 2, _inward(r, hall, 2.2))))
    _equip(b, r, cols, 'heater', 'water heater', min(w - .3, w / 2 + .45), _inward(r, hall, .3), 3500, _circuit(b, 'C05', 'Water heaters'),
           'Typical 3.5 kW single-point heater; replace with the specified unit')


def _house_services(b, r, cols, hall):
    """Appliances and convenience outlets (180 VA each, the usual allowance per outlet); nameplate values are typical, not specified."""
    w, h, name, kind = r['w'], r['h'], r['name'].lower(), r['kind']
    outlets = {'bedroom': 3, 'living': 1 if 'veranda' in name else 4, 'kitchen': 2}.get(kind, 1 if 'laundry' in name else 0)
    if outlets: _equip(b, r, cols, 'outlets', f'outlets ({outlets})', .3, h / 2, 180 * outlets, 'C02', f'Allowance: {outlets} × 180 VA convenience outlets')
    if kind == 'kitchen':
        _equip(b, r, cols, 'range', 'range and hood', min(w - .5, 1.6), .45, 2150, _circuit(b, 'C04', 'Kitchen range'), 'Typical 2 kW two-burner range and 150 W hood')
    if 'laundry' in name:
        _fixture(b, r, cols, 'washer', 'washing machine', 'washer', .45, _inward(r, hall, .5))
        _fixture(b, r, cols, 'tub', 'laundry tub', 'sink', min(w - .4, 1.3), _inward(r, hall, .5))
        _equip(b, r, cols, 'washerpower', 'washing machine', .45, _inward(r, hall, .9), 500, _circuit(b, 'C06', 'Laundry'), 'Typical 500 W top-load washer')


def _house_furniture(b, placed, hall):
    """Typical furniture per room, each at the fitting spot nearest its usual place; whatever cannot clear doors, columns and
    access strips is left out rather than forced in."""
    from .domain import _fits
    from .geometry import openings
    rooms = {r.id: r for r in b.rooms}; doors = openings(b); cols = [c for c in b.columns if c.active]
    for p in placed:
        r = rooms[p['id']]; name = r.name.lower(); mine = [d for d in doors if d['room_id'] == r.id]
        ext = lambda d, size: d if r.y < hall.y else r.h - size - d  # offset from the exterior wall
        items = []
        if r.kind == 'bedroom':
            bw = 1.5 if r.w >= 2.8 else 1.0
            items = [('bed', 'Bed', bw, 2, (r.w - bw) / 2, ext(.6, 2)), ('wardrobe', 'Wardrobe', 1.2, .6, r.w - 1.3, ext(.6, .6) if r.h < 3.6 else r.h / 2)]
        elif r.kind == 'living' and 'veranda' in name:
            items = [('lounger1', 'Lounge chair', .7, 1.4, .3, ext(.7, 1.4)), ('lounger2', 'Lounge chair', .7, 1.4, 1.2, ext(.7, 1.4)), ('outdoor-table', 'Outdoor table', .8, .8, r.w - 1.1, ext(.8, .8))]
        elif r.kind == 'living':
            items = [('sofa', 'Sofa', 2.2, .9, .6, ext(.7, .9)), ('coffee', 'Coffee table', 1.0, .5, .9, ext(1.9, .5)), ('tv', 'TV console', 1.6, .4, .9, ext(3.0, .4))]
            if r.w >= 6: items.append(('dining', 'Dining table', 1.6, .9, r.w - 2.3, ext(1.0, .9)))
        for key, label, fw, fh, ax, ay in items:
            f = Furniture(id=f'{key}-{r.id}', name=label, room_id=r.id, dx=0, dy=0, w=fw, h=fh, clearance=.6 if label in ('Bed', 'Sofa', 'Wardrobe', 'Dining table') else .3)
            others = [o for o in b.furniture if o.room_id == r.id]
            spots = [(round(i * .1, 3), round(f.clearance + j * .1, 3)) for i in range(int((r.w - fw) / .1 + 1e-9) + 1) for j in range(int((r.h - fh - f.clearance) / .1 + 1e-9) + 1)]
            spot = min((s for s in spots if _fits(r, f, *s, others, mine, cols)), key=lambda s: (s[0] - ax) ** 2 + (s[1] - ay) ** 2, default=None)
            if spot: f.dx, f.dy = spot; b.furniture.append(f)


def compose(spec: ProjectSpec) -> tuple[Building, list[str]]:
    """Build the model and return it with a list of the decisions the generator made."""
    from .structure import analyze_structure, CATALOG
    from .lateral import analyze_lateral
    from .fire import analyze_fire
    from .geometry import fitout_checks
    t = TEMPLATES[spec.template]; notes = []
    c = spec.corridor_width; rooms = _expand(spec)
    W, D, depths, placed = _layout(rooms, c)
    height = spec.height or t['height']
    base = example()
    hall = Room(id='hall', name='Corridor', kind='corridor', x=0, y=depths[0], w=W, h=c, min_area=W * c, max_area=W * c, min_dimension=c, locked=True)
    room_models = [Room(id=r['id'], name=r['name'], kind=r['kind'], x=r['x'], y=r['y'], w=r['w'], h=r['h'], min_area=round(.8 * r['w'] * r['h'], 2),
                        max_area=round(1.25 * r['w'] * r['h'], 2), min_dimension=1.5 if r['kind'] == 'bathroom' else 2) for r in placed] + [hall]
    wet = [r for r in placed if r['kind'] in WET]
    wet_y = (wet[0]['y'] + wet[0]['h'] / 2) if wet else depths[0] + c / 2
    site = Site(boundary=[Point(x=-3, y=-3), Point(x=W + 3, y=-3), Point(x=W + 3, y=D + 3), Point(x=-3, y=D + 3)],
                survey=[Point(x=x, y=y, z=round(.012 * x + .006 * y - .1, 4)) for y in [-3, D / 2, D + 3] for x in [-3, W / 2, W + 3]],
                access=Point(x=0, y=depths[0] + .75), water=Point(x=W + 1, y=wet_y), drain=Point(x=W + 1, y=wet_y, z=-.4), panel=Point(x=1, y=depths[0] + .75, z=0),
                datum='Synthetic flat site; replace with the survey')
    b = Building(id='bg-' + _slug(spec.name or t['name']), name=spec.name or t['name'], description=(spec.location + ' · ' if spec.location else '') + 'New project · preliminary planning',
                 width=W, depth=D, height=height, grid_x=[0, W], grid_y=[0, D], rooms=room_models, columns=[], fixtures=[], equipment=[], circuits=[], furniture=[],
                 site=site, rates=base.rates)
    b.brief.use = spec.use or t['use']
    if spec.budget: b.brief.budget = spec.budget
    kitchens = [r for r in placed if r['kind'] == 'kitchen']; baths = [r for r in placed if r['kind'] == 'bathroom']
    b.brief.wet_adjacency = len(kitchens) == 1 and len(baths) == 1

    # Solar first: its dead load is part of what the beams, columns and pads are sized for.
    if spec.solar and spec.solar != 'none':
        b.solar.enabled = True; b.solar.target_kwp = None if spec.solar == 'fill' else float(spec.solar)
        b.solar.customer_class = 'residential' if spec.template == 'house' else 'non_residential'
        b.solar.inverter_kw = None if spec.solar == 'fill' else float(spec.solar)
    # Structure: the coarsest bay and lightest beam section whose roof beams all pass.
    chosen = None
    # Columns in the corridor walls where the doors allow it; otherwise rows set back from the corridor.
    for walls, bay in [(w, bay) for w in (True, False) for bay in (6, 5, 4, 3)]:
        gx, gy = _grid(W, D, depths, c, bay, placed, walls)
        if gx is None: continue
        b.grid_x, b.grid_y = gx, gy
        b.columns = [Column(id=f'col-{i}-{j}', x=x, y=y) for j, y in enumerate(gy) for i, x in enumerate(gx)]
        for section in CATALOG:
            b.engineering.section = section
            st = analyze_structure(b)
            if st['beams'] and not st['errors'] and all(x['status'] == 'pass' for x in st['beams']): chosen = (bay, section, walls); break
        if chosen: break
    if not chosen: raise ValueError('No column grid fits between the corridor doors with roof beams that pass. Combine some small rooms or make them wider.')
    notes.append(f'Footprint {W:g} × {D:g} m, {c:g} m corridor, {len(placed)} rooms. Grid of {len(b.grid_x) - 1} × {len(b.grid_y) - 1} bays (≤ {chosen[0]} m) with {CATALOG[chosen[1]]["label"]} roof beams, the lightest that pass{'' if chosen[2] else '; column rows set 0.5 m back from the corridor to keep every door clear'}.')

    # Services: wet fixtures, lighting, power and air conditioning on three circuits.
    b.circuits = [Circuit(id='C01', name='Lighting'), Circuit(id='C02', name='General power'), Circuit(id='C03', name='Air conditioning')]
    cols = b.columns
    house = spec.template == 'house'
    for r in placed:
        if r['kind'] == 'bathroom' and house:
            _house_bathroom(b, r, cols, hall)
        elif r['kind'] == 'bathroom':
            (wx, wy), (bx, by) = _clear_point(r, cols, .75, .75), _clear_point(r, cols, max(.6, min(2, r['w'] - .6)), .75)
            b.fixtures += [Fixture(id=f'wc-{r["id"]}', name=f'{r["name"]} WC', room_id=r['id'], dx=wx, dy=wy, kind='wc'),
                           Fixture(id=f'basin-{r["id"]}', name=f'{r["name"]} basin', room_id=r['id'], dx=bx, dy=by, kind='basin')]
        elif r['kind'] == 'kitchen':
            sx, sy = _clear_point(r, cols, .75, .75)
            b.fixtures.append(Fixture(id=f'sink-{r["id"]}', name=f'{r["name"]} sink', room_id=r['id'], dx=sx, dy=sy, kind='sink'))
        dx, dy = _clear_point(r, cols, r['w'] / 2, r['h'] / 2)
        lux = 6 if r['kind'] == 'storage' else 10
        b.equipment.append(Equipment(id=f'light-{r["id"]}', name=f'{r["name"]} lighting', room_id=r['id'], dx=dx, dy=dy, watts=round(r['w'] * r['h'] * lux / 10) * 10 or 20, circuit_id='C01', source='Allowance: ' + str(lux) + ' W/m²'))
        if r['kind'] in ('office', 'retail', 'bedroom', 'living') and 'veranda' not in r['name'].lower():  # an open veranda is not air-conditioned
            ax, ay = _clear_point(r, cols, min(r['w'] - .5, 1.0), max(.5, r['h'] - .5))
            b.equipment.append(Equipment(id=f'ac-{r["id"]}', name=f'{r["name"]} air conditioner', room_id=r['id'], dx=ax, dy=ay, watts=1500 if r['w'] * r['h'] > 30 else 1000, circuit_id='C03', source='Allowance by room size'))
        if r['kind'] == 'kitchen':
            fx, fy = _clear_point(r, cols, max(.6, r['w'] - .6), .5)
            b.equipment.append(Equipment(id=f'fridge-{r["id"]}', name=f'{r["name"]} refrigerator', room_id=r['id'], dx=fx, dy=fy, watts=200, circuit_id='C02'))
        if r['kind'] in ('office', 'retail'):
            sx, sy = _clear_point(r, cols, .6, .6)
            b.equipment.append(Equipment(id=f'power-{r["id"]}', name=f'{r["name"]} workstations', room_id=r['id'], dx=sx, dy=sy, watts=350, circuit_id='C02'))
    # House fit-out: appliances, outlets and furniture a real house has, so routes, loads and the plan read like one.
    if house:
        for r in placed: _house_services(b, r, cols, hall)
        _house_furniture(b, placed, hall)
        issues = {o for i in fitout_checks(b)['issues'] for o in i['objects']}
        b.furniture = [f for f in b.furniture if f.id not in issues]

    # Seismic: only what the user answered becomes a value; everything else stays missing.
    lat = b.engineering.lateral; who = 'User answer in the new-project assistant'
    lat.soil_profile = 'SD' if spec.soil_profile in (None, 'unknown') else spec.soil_profile
    lat.soil_source = 'NSCP 2015 §208: SD when soil properties are not known (verify)' if spec.soil_profile in (None, 'unknown') else who
    if spec.fault_distance == 'far':
        for key in ['na', 'nv']: setattr(lat, key, Parameter(value=1.0, unit='', source=who, basis='Site ≥ 15 km from a Type A or B seismic source, so the near-source factor is 1.0; confirm with PHIVOLCS FaultFinder'))
    if spec.frame == 'steel_omrf': lat.r_factor = Parameter(value=4.5, unit='', source=who, basis='Steel ordinary moment-resisting frame, R = 4.5 (UBC-97 lineage); confirm in NSCP 2015 Table 208-11')
    if spec.friction == 'assumed': lat.friction = Parameter(value=.35, unit='', source=who, basis='Assumed concrete-on-soil friction; replace with the geotechnical report value')
    # Columns: the lightest section that passes, judged on the combinations available.
    from .structure import COLUMNS
    for section in COLUMNS:
        b.engineering.column_section = section
        L = analyze_lateral(b, analyze_structure(b))
        if not any(x['status'] == 'fail' for x in L.get('columns', [])): break
    # Pads: the smallest square footing that holds bearing, overturning and sliding under the seismic cases.
    for width in [1.2, 1.5, 1.8, 2.1, 2.4, 3.0]:
        b.engineering.footing_width = width
        st = analyze_structure(b); L = analyze_lateral(b, st)
        if all(f['status'] != 'fail' for f in st['foundations']) and not any(x['status'] == 'fail' for x in L.get('footings', [])): break
    notes.append(f'{COLUMNS[b.engineering.column_section]["label"]} columns, {height:g} m eave height, {b.engineering.footing_width:g} m square pads.')

    # Fire: occupancy as answered; provisions placed until the Table 7 extinguisher screen is satisfied.
    occ = spec.fire_occupancy or t.get('fire_occupancy')
    if occ and occ != 'none':
        f = FireProtection(enabled=True, occupancy=occ)
        if spec.rear_exit: f.exits = [ExitDoor(id='exit-east', wall='east', offset=depths[0] + .25, width=1.0)]
        if spec.fire_provisions:
            f.exit_signs = True; f.emergency_lighting = True; f.alarm = 'manual'
            f.extinguishers = [Extinguisher(id='fe-01', room_id='hall', dx=min(W / 2, 6.0), dy=c / 2)]
            b.fire = f
            for alarm in ['manual', 'automatic']:  # the lighter system the screen accepts for this occupancy and load
                f.alarm = alarm
                if next((x for x in analyze_fire(b)['checks'] if x['rule'] == 'FIRE-ALARM'), {'status': 'pass'})['status'] != 'fail': break
            for n in range(2, 30):
                fire = analyze_fire(b); ext = next((x for x in fire['checks'] if x['rule'] == 'FIRE-EXT'), None)
                if not ext or ext['status'] == 'pass': break
                far = fire['extinguishers']['critical_path']
                px, py = far[0] if far else (W - 1, depths[0] + c / 2)  # the path runs from the farthest point back to an extinguisher
                room = next((r for r in placed if r['x'] <= px <= r['x'] + r['w'] and r['y'] <= py <= r['y'] + r['h']), None)
                f.extinguishers.append(Extinguisher(id=f'fe-{n:02d}', room_id=room['id'] if room else 'hall',
                                                    dx=(px - room['x']) if room else min(px, W - .5), dy=(py - room['y']) if room else c / 2))
            notes.append(f'Fire: {occ.replace("_", " ")} occupancy, {len(f.extinguishers)} extinguisher(s), exit signs, emergency lighting and a {f.alarm} alarm.')
        b.fire = f
    else:
        notes.append('Fire screen not run: ' + ('residential occupancy is outside the RA 9514 screen.' if spec.template == 'house' else 'storage occupancy is outside the RA 9514 screen.'))

    return Building.model_validate(b.model_dump()), notes


def missing_labels(spec: ProjectSpec) -> list[str]:
    """What will be a missing input in the model if the project is built now."""
    out = []
    if spec.fault_distance != 'far': out.append('Near-source factors Na, Nv')
    if spec.frame != 'steel_omrf': out.append('Response modification factor R')
    if spec.friction != 'assumed': out.append('Base friction coefficient')
    if spec.soil_profile == 'SE': out.append('Seismic coefficient Ca (soil SE)')
    return out


def preview(spec: ProjectSpec) -> dict:
    try:
        b, notes = compose(spec)
    except ValueError as e:
        return {'ok': False, 'error': str(e), 'missing': missing_labels(spec)}
    return {'ok': True, 'width': b.width, 'depth': b.depth, 'height': b.height, 'grid_x': b.grid_x, 'grid_y': b.grid_y,
            'rooms': [{'id': r.id, 'name': r.name, 'kind': r.kind, 'x': r.x, 'y': r.y, 'w': r.w, 'h': r.h} for r in b.rooms],
            'columns': [[c.x, c.y] for c in b.columns], 'area': b.width * b.depth, 'notes': notes, 'missing': missing_labels(spec)}

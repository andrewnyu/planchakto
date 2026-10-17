"""Room moves re-fit the room's children (limits report 17 Oct 2026, §1c): offsets are room-relative, so a moved or resized
room must not leave fixtures, equipment or furniture outside it, in a door swing or in front of a column."""
from backend.compose import compose, template_spec
from backend.domain import *
from backend.engine import compute
from backend.example import example
from backend.geometry import door_x, fitout_checks, layout_checks, openings
from backend.routing import route_all


def house():
    return compose(template_spec('house'))[0]


def inside(b):
    rooms = {r.id: r for r in b.rooms}
    for p in b.fixtures + b.equipment + b.fire.extinguishers:
        r = rooms[p.room_id]; assert 0 <= p.dx <= r.w and 0 <= p.dy <= r.h, p.id
    for f in b.furniture:
        r = rooms[f.room_id]; assert 0 <= f.dx and f.dx + f.w <= r.w and 0 <= f.dy and f.dy + f.h <= r.h, f.id


def test_swap_across_the_corridor_refits_children():
    # The 3.5 m living room swaps with the 2.5 m bedroom on the other side of the corridor: depth and door side both change.
    b, _ = apply_commands(house(), [SwapRooms(type='swap_rooms', first='living-dining', second='bedroom-01')])
    inside(b)
    ac = next(e for e in b.equipment if e.id == 'ac-living-dining')
    assert (ac.dx, ac.dy) == (1.0, 2.0)  # kept 0.5 m off the far wall, as the generator places it
    assert not any('outside its room' in (r.get('reason') or '') for r in route_all(b)['routes'])
    assert fitout_checks(b)['status'] == 'pass'
    assert not [i for i in layout_checks(b)['issues'] if i['id'].startswith('circulation')]


def test_shrinking_a_room_keeps_children_inside_and_off_columns():
    b0 = house()
    b, _ = apply_commands(b0, [MoveRoom(type='move_room', room_id='kitchen', x=6.5, y=0, w=2.0, h=3.5)])
    inside(b)
    fridge = next(e for e in b.equipment if e.id == 'fridge-kitchen')
    assert fridge.dx == 1.4  # 0.6 m from the east wall before and after
    cols = [c for c in b.columns if c.active]
    for p in b.fixtures + b.equipment:
        if p.room_id == 'kitchen':
            assert all(max(abs(6.5 + p.dx - c.x), abs(p.dy - c.y)) > .6 for c in cols), p.id


def test_explicit_moves_in_the_same_batch_win():
    for order in (0, 1):
        moves = [MoveFurniture(type='move_furniture', furniture_id='sofa-living-dining', dx=.1, dy=.2),
                 MoveEquipment(type='move_equipment', equipment_id='ac-living-dining', dx=.3, dy=.4, circuit_id='C03')]
        swap = [SwapRooms(type='swap_rooms', first='living-dining', second='bedroom-01')]
        b, _ = apply_commands(house(), swap + moves if order else moves + swap)
        sofa = next(f for f in b.furniture if f.id == 'sofa-living-dining'); ac = next(e for e in b.equipment if e.id == 'ac-living-dining')
        assert (sofa.dx, sofa.dy, ac.dx, ac.dy) == (.1, .2, .3, .4)


def test_unchanged_geometry_leaves_children_untouched():
    b0 = example()
    r = next(r for r in b0.rooms if r.id == 'living')
    b, _ = apply_commands(b0, [MoveRoom(type='move_room', room_id='living', x=r.x, y=r.y, w=r.w, h=r.h)])
    assert digest(b) == digest(b0)
    # A pure translation keeps offsets that still fit.
    h0 = house(); b, _ = apply_commands(h0, [MoveRoom(type='move_room', room_id='bathroom', x=9.0, y=0)])
    offsets = lambda m: [(p.id, p.dx, p.dy) for p in m.fixtures + m.equipment + m.furniture]
    assert offsets(b) == offsets(h0)


def test_unfittable_furniture_is_left_for_the_screen_to_report():
    # A 2.2 m sofa cannot fit a 2 m room; it is clamped, not dropped, and the fit-out screen still reports it.
    b, _ = apply_commands(house(), [MoveRoom(type='move_room', room_id='living-dining', x=0, y=0, w=2.0, h=3.5)])
    assert any(f.id == 'sofa-living-dining' for f in b.furniture)
    assert any('sofa-living-dining' in i['objects'] for i in fitout_checks(b)['issues'])


def test_door_slides_off_a_column():
    b = house()  # grid columns at x = 0, 5.5, 11 on both corridor walls
    assert door_x(b, 0., 6.5, 3.5) == .35  # clear: the default position is kept
    assert door_x(b, 5., 8., 3.5) == 5.65  # column at 5.5 in the default opening: nearest clear position
    assert door_x(b, 5., 6.1, 3.5) == 5.35  # no clear position on a short wall: the default stays and the screen reports it
    moved, _ = apply_commands(b, [MoveRoom(type='move_room', room_id='living-dining', x=0, y=0, w=5., h=3.5),
                                  MoveRoom(type='move_room', room_id='kitchen', x=5., y=0, w=4.5, h=3.5)])
    assert next(d for d in openings(moved) if d['room_id'] == 'kitchen')['x'] == 5.65
    assert 'circulation-kitchen' not in {i['id'] for i in layout_checks(moved)['issues']}


def test_example_doors_unchanged():
    b = example(); rooms = {r.id: r for r in b.rooms}
    assert all(d['x'] == rooms[d['room_id']].x + .35 for d in openings(b) if d['kind'] == 'door')

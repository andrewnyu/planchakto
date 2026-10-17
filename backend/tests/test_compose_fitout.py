"""Generated houses are fitted out like houses: wet fixtures, appliances on their own circuits and furniture that clears doors."""
from backend.compose import ProjectSpec, RoomSpec, compose
from backend.engine import compute
from backend.geometry import fitout_checks


def beach_house():
    rooms = [('Living & dining', 'living', 36), ('Kitchen', 'kitchen', 12), ('Master bedroom', 'bedroom', 16), ('Master bathroom', 'bathroom', 8),
             ('Guest bedroom', 'bedroom', 11), ('Shared bathroom', 'bathroom', 6), ('Laundry room', 'storage', 6), ('Covered veranda', 'living', 18),
             ('Outdoor shower', 'bathroom', 6)]
    return ProjectSpec(template='house', name='Beach house', rooms=[RoomSpec(name=n, kind=k, area=a, count=1) for n, k, a in rooms], solar='none')


def test_house_gets_showers_laundry_appliances_and_furniture():
    b, _ = compose(beach_house())
    kinds = lambda room: sorted(f.kind for f in b.fixtures if f.room_id == room)
    rid = {r.name: r.id for r in b.rooms}
    assert kinds(rid['Master bathroom']) == ['basin', 'shower', 'wc']
    assert kinds(rid['Outdoor shower']) == ['shower']  # a cold rinse: no WC, no heater
    assert kinds(rid['Laundry room']) == ['sink', 'washer']
    equipment = {e.id for e in b.equipment}
    assert {f'heater-{rid["Master bathroom"]}', f'range-{rid["Kitchen"]}', f'washerpower-{rid["Laundry room"]}'} <= equipment
    assert f'heater-{rid["Outdoor shower"]}' not in equipment and f'ac-{rid["Covered veranda"]}' not in equipment
    assert {c.id for c in b.circuits} >= {'C04', 'C05', 'C06'}
    names = {f.name for f in b.furniture}
    assert {'Bed', 'Sofa', 'Lounge chair'} <= names
    assert not fitout_checks(b)['issues']
    assert not [c for c in compute(b, 'fitout')['checks'] if c['status'] == 'fail']


def test_commercial_fitout_is_unchanged():
    spec = ProjectSpec(template='commercial', rooms=[RoomSpec(name='Office', kind='office', area=15, count=2), RoomSpec(name='Toilet', kind='bathroom', area=5, count=1)])
    b, _ = compose(spec)
    assert {f.kind for f in b.fixtures} == {'wc', 'basin'} and not b.furniture
    assert {c.id for c in b.circuits} == {'C01', 'C02', 'C03'}

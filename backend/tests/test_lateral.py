import math
import pytest
from backend.domain import Building, Parameter, RemoveColumn, SetLateral, apply_commands
from backend.example import example
from backend.engine import compute
from backend.lateral import FrameError, base_shear, coefficients, column_capacity, frame2d
from backend.structure import COLUMNS

E, A, I, H = 200e9, 3e-3, 1.2e-5, 3.0
RIGID = 1e6


def portal(base):
    nodes = [(0, 0), (0, H), (4, 0), (4, H)]
    # Closed forms neglect axial shortening, so members are axially rigid here.
    members = [{'i': 0, 'j': 1, 'E': E, 'A': A * RIGID, 'I': I}, {'i': 2, 'j': 3, 'E': E, 'A': A * RIGID, 'I': I}, {'i': 1, 'j': 3, 'E': E, 'A': A * RIGID, 'I': I * RIGID}]
    return frame2d(nodes, members, {0: base, 2: base}, {1: (1000, 0, 0)})


def test_cantilever_tip_deflection():
    r = frame2d([(0, 0), (0, H)], [{'i': 0, 'j': 1, 'E': E, 'A': A, 'I': I}], {0: (1, 1, 1)}, {1: (1000, 0, 0)})
    assert r['u'][3] == pytest.approx(1000 * H**3 / (3 * E * I), rel=1e-9)
    assert r['reactions'][2] == pytest.approx(1000 * H, rel=1e-9)  # counter-clockwise base reaction resists the overturning moment


@pytest.mark.parametrize('base,closed_form', [((1, 1, 1), 24 * E * I / H**3), ((1, 1, 0), 6 * E * I / H**3)])
def test_portal_stiffness_with_rigid_beam(base, closed_form):
    r = portal(base)
    assert 1000 / r['u'][3] == pytest.approx(closed_form, rel=1e-4)
    assert r['reactions'][0] + r['reactions'][6] == pytest.approx(-1000, rel=1e-6)  # horizontal equilibrium (rigid members cost some conditioning)


def test_fixed_fixed_beam_uniform_load():
    w, L = 5000, 6
    m = frame2d([(0, 0), (L, 0)], [{'i': 0, 'j': 1, 'E': E, 'A': A, 'I': I}], {0: (1, 1, 1), 1: (1, 1, 1)}, {}, {0: w})['members'][0]
    assert m['M_i'] == pytest.approx(w * L**2 / 12)
    assert m['V_i'] == pytest.approx(w * L / 2)
    assert m['M_max'] == pytest.approx(w * L**2 / 12)


def test_column_axial_sign_is_compression_positive():
    m = frame2d([(0, 0), (0, H)], [{'i': 0, 'j': 1, 'E': E, 'A': A, 'I': I}], {0: (1, 1, 1)}, {1: (0, -1000, 0)})['members'][0]
    assert m['N_i'] == pytest.approx(1000)


def test_pinned_column_is_a_mechanism():
    with pytest.raises(FrameError):
        frame2d([(0, 0), (0, H)], [{'i': 0, 'j': 1, 'E': E, 'A': A, 'I': I}], {0: (1, 1, 0)}, {1: (1000, 0, 0)})


def test_base_shear_bounds_by_hand():
    c = {'Z': .4, 'Ca': .44, 'Cv': .64, 'Na': 1, 'Nv': 1, 'R': 4.5, 'I': 1}
    v = base_shear(100, 3, c, .0853, 4)
    assert v['T_s'] == pytest.approx(.0853 * 3**.75)
    assert v['V_kN'] == pytest.approx(2.5 * .44 * 100 / 4.5)  # short period: the 2.5·Ca cap governs
    assert v['governing'] == '2.5·Ca·I·W / R'
    tall = base_shear(100, 60, c, .0853, 4)  # long period: Cv/T, but not below the zone 4 floor
    assert tall['V_kN'] == pytest.approx(max(.64 * 100 / (4.5 * .0853 * 60**.75), .11 * .44 * 100, .8 * .4 * 100 / 4.5))


def test_coefficients_only_from_confirmed_cells():
    b = example()
    c, missing, unsupported = coefficients(b)
    assert (c['Ca'], c['Cv'], missing, unsupported) == (.44, .64, [], None)
    b.engineering.lateral.soil_profile = 'SE'  # sources disagree on zone 4 Ca for SE
    assert any('Ca' in m for m in coefficients(b)[1])
    b.engineering.lateral.ca = Parameter(value=.36, unit='', source='Official NSCP 2015 Table 208-7')
    assert coefficients(b)[1] == []
    b.engineering.lateral.soil_profile = 'SF'
    assert coefficients(b)[2]


def test_column_capacity_matches_aisc_e3():
    sec = COLUMNS['SHS150']; Fy, L, K = 250e6, 3, 2
    cap = column_capacity(sec, E, Fy, K, L)
    Fe = math.pi**2 * E / (K * L / sec['r'])**2
    assert cap['Pc'] == pytest.approx(.9 * .658**(Fy / Fe) * Fy * sec['area'])
    assert cap['Mc'] == pytest.approx(.9 * Fy * sec['Zp'])
    assert cap['compact']


def test_demo_lateral_equilibrium_drift_and_redundancy():
    L = compute(example(), 'r')['lateral']
    assert L['status'] == 'pass'
    V = L['base_shear']['V_kN']
    for d in L['directions'].values():
        assert d['equilibrium_residual_N'] < 1e-6
        k = sum(f['stiffness_kN_mm'] for f in d['frames'])  # kN/mm
        assert d['drift_s_mm'] == pytest.approx(V / k, rel=1e-6)  # rigid diaphragm: one common displacement
        assert d['drift_m_mm'] == pytest.approx(.7 * 4.5 * d['drift_s_mm'])
        assert 1 <= d['rho'] <= 1.5
    assert L['equilibrium_residual_N'] < 1e-6


def test_missing_seismic_inputs_never_pass():
    data = example().model_dump(); data['engineering'].pop('lateral')  # e.g. an older project file
    r = compute(Building.model_validate(data), 'r')
    seismic = [c for c in r['checks'] if c['rule_id'] in ('SEISMIC-V', 'DRIFT', 'FOOT-LATERAL', 'COLUMN')]
    assert seismic and not any(c['status'] == 'pass' for c in seismic)
    assert any(c['status'] == 'missing_input' for c in seismic)


def test_removing_interior_column_propagates_to_frame_members():
    b = example(); c, invalidated = apply_commands(b, [RemoveColumn(type='remove_column', column_id='col-1-1')])
    assert 'structure' in invalidated
    failing = {x['rule_id'] for x in compute(c, 'r')['checks'] if x['status'] == 'fail'}
    assert 'FRAME-MEMBER' in failing


def test_pinned_bases_increase_drift():
    b = example(); lat = b.engineering.lateral.model_copy(deep=True); lat.base_fixity = 'pinned'
    c, _ = apply_commands(b, [SetLateral(type='set_lateral', lateral=lat)])
    fixed, pinned = compute(b, 'r')['lateral'], compute(c, 'r')['lateral']
    assert pinned['directions']['X']['drift_s_mm'] > 3 * fixed['directions']['X']['drift_s_mm']


def test_assistant_cannot_set_seismic_inputs():
    from backend.ai import RESTRICTED
    assert 'set_lateral' in RESTRICTED

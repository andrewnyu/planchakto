"""Seismic static lateral screen for the single-storey regular steel frame family, SI units.

Method: NSCP 2015 §208 static force procedure (UBC-97 lineage) for the design base shear, a rigid roof
diaphragm sharing it between planar moment frames by stiffness, linear direct-stiffness frame analysis,
storey drift, steel column and frame-member strength (NSCP Ch. 5 / AISC 360-10 basis) and footing
eccentric bearing, overturning and sliding.

Coefficient tables were transcribed from secondary sources (lecture notes and vendor guides), not the
official ASEP text. Only cells on which those sources agree are built in; every other value is a
missing input until the user enters it. See SOURCE.
"""
import math
import numpy as np
from .domain import Building
from .structure import CATALOG, COLUMNS

SOURCE = ('NSCP 2015 Vol. I §208 static force procedure and §203 load combinations; steel members per NSCP Ch. 5 '
          '(AISC 360-10 basis). Table values transcribed from secondary sources and must be verified against the official ASEP edition.')
G = 9.80665
ZONE = {2: .2, 4: .4}
# Table 208-7 (Ca, × Na in zone 4). SE in zone 4 and every zone 2 cell disagree or are unconfirmed across sources: user input.
CA = {4: {'SA': .32, 'SB': .40, 'SC': .40, 'SD': .44}}
# Table 208-8 (Cv, × Nv in zone 4).
CV = {4: {'SA': .32, 'SB': .40, 'SC': .56, 'SD': .64, 'SE': .96}, 2: {'SA': .16, 'SB': .20, 'SC': .32, 'SD': .40, 'SE': .64}}
FE_ELEMENTS = 1  # exact for prismatic members with end loads; uniform loads use consistent fixed-end actions


class FrameError(ValueError): pass


def frame2d(nodes, members, supports, loads, member_loads=None):
    """Linear planar frame, 3 DOF per node (u, w, θ).

    nodes: [(s, z)] in m. members: [{'i','j','E','A','I'}] in Pa, m², m⁴, rigid joints.
    supports: {node: (u, w, θ) restrained flags}. loads: {node: (Fs, Fz, M)} in N, N·m.
    member_loads: {member index: w} uniform load in N/m acting in global −z (members must be horizontal).
    Returns nodal displacements, reactions and member end forces in local axes (N, V, M at i then j).
    """
    member_loads = member_loads or {}
    n = len(nodes); K = np.zeros((3 * n, 3 * n)); F = np.zeros(3 * n); data = []
    for m, mem in enumerate(members):
        (x1, z1), (x2, z2) = nodes[mem['i']], nodes[mem['j']]
        L = math.hypot(x2 - x1, z2 - z1); c, s = (x2 - x1) / L, (z2 - z1) / L
        E, A, I = mem['E'], mem['A'], mem['I']
        a, b1, b2, b3, b4 = E * A / L, 12 * E * I / L**3, 6 * E * I / L**2, 4 * E * I / L, 2 * E * I / L
        k = np.array([[a, 0, 0, -a, 0, 0], [0, b1, b2, 0, -b1, b2], [0, b2, b3, 0, -b2, b4],
                      [-a, 0, 0, a, 0, 0], [0, -b1, -b2, 0, b1, -b2], [0, b2, b4, 0, -b2, b3]])
        r = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]]); T = np.zeros((6, 6)); T[:3, :3] = r; T[3:, 3:] = r
        w = member_loads.get(m, 0.)
        if w and abs(s) > 1e-9: raise FrameError('Distributed loads are supported on horizontal members only')
        q = -w * c  # global −z load resolved onto the local transverse axis (−s, c)
        feq = np.array([0, q * L / 2, q * L**2 / 12, 0, q * L / 2, -q * L**2 / 12])
        dof = [3 * mem['i'], 3 * mem['i'] + 1, 3 * mem['i'] + 2, 3 * mem['j'], 3 * mem['j'] + 1, 3 * mem['j'] + 2]
        K[np.ix_(dof, dof)] += T.T @ k @ T; F[dof] += T.T @ feq
        data.append((dof, k, T, feq, L, q))
    for node, (fs, fz, mm) in loads.items(): F[3 * node:3 * node + 3] += (fs, fz, mm)
    fixed = [3 * node + i for node, flags in supports.items() for i, f in enumerate(flags) if f]
    free = np.array([i for i in range(3 * n) if i not in fixed], dtype=int)
    A_ = K[np.ix_(free, free)]
    if np.linalg.matrix_rank(A_) < len(free): raise FrameError('Unstable frame: the supports and members form a mechanism')
    u = np.zeros(3 * n); u[free] = np.linalg.solve(A_, F[free]); R = K @ u - F
    ends = []
    for dof, k, T, feq, L, q in data:
        f = k @ (T @ u[dof]) - feq
        # Internal bending moment along the member (sagging positive), sampled for the peak.
        xs = np.linspace(0, L, 41); Mx = -f[2] + f[1] * xs + q * xs**2 / 2
        ends.append({'N_i': f[0], 'V_i': f[1], 'M_i': f[2], 'N_j': f[3], 'V_j': f[4], 'M_j': f[5], 'M_max': float(np.max(np.abs(Mx))), 'L': L})
    return {'u': u, 'reactions': {i: float(R[i]) for i in fixed}, 'members': ends}


def coefficients(b: Building):
    """Return seismic coefficients, the missing-input list and any unsupported reason."""
    lat = b.engineering.lateral; missing = []; unsupported = None
    if lat.soil_profile == 'SF': unsupported = 'Soil profile SF requires a site-specific geotechnical and response evaluation'
    near = lat.zone == 4
    na = lat.na.value if near else 1.0; nv = lat.nv.value if near else 1.0
    if near and na is None: missing.append('Near-source factor Na')
    if near and nv is None: missing.append('Near-source factor Nv')
    if lat.r_factor.value is None: missing.append('Response modification factor R')
    ca = lat.ca.value
    if ca is None and lat.soil_profile in CA.get(lat.zone, {}) and na is not None: ca = CA[lat.zone][lat.soil_profile] * (na if near else 1)
    if ca is None and not unsupported: missing.append(f'Seismic coefficient Ca (Table 208-7, zone {lat.zone}, {lat.soil_profile})')
    cv = lat.cv.value
    if cv is None and lat.soil_profile in CV.get(lat.zone, {}) and nv is not None: cv = CV[lat.zone][lat.soil_profile] * (nv if near else 1)
    if cv is None and not unsupported: missing.append(f'Seismic coefficient Cv (Table 208-8, zone {lat.zone}, {lat.soil_profile})')
    return {'Z': ZONE[lat.zone], 'Ca': ca, 'Cv': cv, 'Na': na, 'Nv': nv, 'R': lat.r_factor.value, 'I': lat.importance}, missing, unsupported


def base_shear(W, h, c, ct, zone):
    """Design base shear (kN) for weight W (kN), roof height h (m)."""
    T = ct * h**.75
    raw = c['Cv'] * c['I'] * W / (c['R'] * T)
    cap = 2.5 * c['Ca'] * c['I'] * W / c['R']
    floors = [('0.11·Ca·I·W', .11 * c['Ca'] * c['I'] * W)]
    if zone == 4: floors.append(('0.8·Z·Nv·I·W / R', .8 * c['Z'] * c['Nv'] * c['I'] * W / c['R']))
    V, governing = (cap, '2.5·Ca·I·W / R') if raw > cap else (raw, 'Cv·I·W / (R·T)')
    for name, floor in floors:
        if floor > V: V, governing = floor, name
    return {'T_s': T, 'V_kN': V, 'governing': governing, 'Cs': V / W, 'raw_kN': raw, 'cap_kN': cap, 'floors_kN': {n: v for n, v in floors}}


def column_capacity(sec, E, Fy, K, L):
    """AISC 360-10 E3 flexural buckling and plastic flexure for a compact square HSS (N, N·m)."""
    slender = K * L / sec['r']; Fe = math.pi**2 * E / slender**2
    Fcr = (.658 ** (Fy / Fe)) * Fy if slender <= 4.71 * math.sqrt(E / Fy) else .877 * Fe
    wall = (sec['b'] - 3 * sec['t']) / sec['t']
    return {'KL_r': slender, 'Fcr_MPa': Fcr / 1e6, 'Pc': .9 * Fcr * sec['area'], 'Pt': .9 * Fy * sec['area'], 'Mc': .9 * Fy * sec['Zp'],
            'b_t': wall, 'compact': wall <= 1.12 * math.sqrt(E / Fy)}


def interaction(P, M, cap):
    """AISC H1-1 with compression positive; tension uses gross yielding."""
    Pc = cap['Pc'] if P >= 0 else cap['Pt']; p = abs(P) / Pc; m = abs(M) / cap['Mc']
    return p + 8 / 9 * m if p >= .2 else p / 2 + m


def analyze_lateral(b: Building, structure):
    e = b.engineering; lat = e.lateral
    if not lat.enabled: return {'enabled': False}
    out = {'enabled': True, 'checks': [], 'scope': ('Static lateral force procedure, rigid roof diaphragm, planar moment frames on every grid line '
           '(roof beams in X, grid girders in Y), linear first-order analysis. Excludes torsion (inherent and accidental), orthogonal effects, '
           'P-Δ, connections, base plates, anchor bolts, vertical irregularity and dynamic analysis.'), 'source': SOURCE}
    def check(rule, status, objects, evidence, inputs=None, clause=''):
        out['checks'].append({'rule': rule, 'status': status, 'objects': objects, 'evidence': evidence, 'inputs': inputs or {}, 'clause': clause})
    check('WIND', 'unsupported', [b.id], 'Wind loads (NSCP 2015 §207) are not evaluated; lateral checks cover seismic only.', clause='NSCP 2015 §207')
    if structure.get('status') == 'missing_input' or structure.get('errors') or not structure.get('beams'):
        reason = structure.get('reason') or '; '.join(structure.get('errors', [])) or 'Roof framing unavailable'
        out['status'] = 'unsupported' if structure.get('errors') else 'missing_input'
        for rule in ['SEISMIC-V', 'DRIFT', 'COLUMN', 'FOOT-LATERAL']: check(rule, out['status'], [b.id], f'Lateral analysis needs a complete gravity frame: {reason}')
        return out

    E = e.elastic_modulus * 1e6; Fy = e.yield_strength * 1e6; h = b.height
    beam_sec = CATALOG[e.section]; col_sec = COLUMNS[e.column_section]
    cols = {c.id: c for c in b.columns if c.active}
    # Gravity line loads (kN/m) split into dead and roof live so each combination factors them separately.
    beams = [{**x, 'D': e.dead.value * x['tributary_width'] + x['self_weight_kNm'] + x['pv_kNm'], 'Lr': e.live.value * x['tributary_width']} for x in structure['beams']]
    girders = structure['girders']
    col_w = col_sec['kg_m'] * G / 1000 * h  # kN per column
    W = sum(x['D'] * x['length'] for x in beams) + sum(x['self_weight_kNm'] * x['length'] for x in girders) + .5 * col_w * len(cols)
    # Column-top gravity from the members that are not in a given frame (kN): roof beams for Y frames, girders for X frames.
    beam_top = {c: [0., 0.] for c in cols}; girder_top = {c: 0. for c in cols}
    for x in beams:
        for cid in [i.replace('node-', '') for i in x['node_ids']]: beam_top[cid][0] += x['D'] * x['length'] / 2; beam_top[cid][1] += x['Lr'] * x['length'] / 2
    for x in girders:
        for cid in [i.replace('node-', '') for i in x['node_ids']]: girder_top[cid] += x['self_weight_kNm'] * x['length'] / 2

    frames = []
    for direction, lines, along in [('X', b.grid_y, lambda c: c.x), ('Y', b.grid_x, lambda c: c.y)]:
        for k, pos in enumerate(lines):
            line = sorted([c for c in cols.values() if abs((c.y if direction == 'X' else c.x) - pos) < 1e-6], key=along)
            if line: frames.append({'id': f'frame-{direction}{k + 1}', 'direction': direction, 'line': pos, 'columns': [c.id for c in line], 'coords': [along(c) for c in line]})

    def build(frame):
        nodes = []; members = []; kinds = []
        for s in frame['coords']: nodes += [(s, 0.), (s, h)]
        for i, cid in enumerate(frame['columns']):
            members.append({'i': 2 * i, 'j': 2 * i + 1, 'E': E, 'A': col_sec['area'], 'I': col_sec['I']}); kinds.append(('column', cid))
        for i in range(len(frame['columns']) - 1):
            a, c = frame['columns'][i], frame['columns'][i + 1]
            mid = f'beam-{a}-{c}' if frame['direction'] == 'X' else f'girder-{a}-{c}'
            members.append({'i': 2 * i + 1, 'j': 2 * i + 3, 'E': E, 'A': beam_sec['area'], 'I': beam_sec['I']}); kinds.append(('beam' if frame['direction'] == 'X' else 'girder', mid))
        flags = (True, True, lat.base_fixity == 'fixed')
        return nodes, members, kinds, {2 * i: flags for i in range(len(frame['columns']))}

    def solve(frame, H, fd, fl):
        """H: total lateral force on this frame (N), split equally over the column tops (rigid diaphragm)."""
        nodes, members, kinds, supports = build(frame)
        n = len(frame['columns']); loads = {}; mload = {}
        for i, cid in enumerate(frame['columns']):
            Fz = -(fd * girder_top[cid]) if frame['direction'] == 'X' else -(fd * beam_top[cid][0] + fl * beam_top[cid][1])
            loads[2 * i + 1] = (H / n, Fz * 1000, 0.)
        for m, (kind, mid) in enumerate(kinds):
            if kind == 'beam':
                x = next(x for x in beams if x['id'] == mid); mload[m] = (fd * x['D'] + fl * x['Lr']) * 1000
            elif kind == 'girder':
                x = next(x for x in girders if x['id'] == mid); mload[m] = fd * x['self_weight_kNm'] * 1000
        res = frame2d(nodes, members, supports, loads, mload)
        res['kinds'] = kinds; res['top_u'] = float(np.mean([res['u'][3 * (2 * i + 1)] for i in range(n)]))
        res['applied_H'] = H; res['base'] = [{'column_id': cid, 'H': -res['reactions'][6 * i], 'V': res['reactions'][6 * i + 1], 'M': res['reactions'].get(6 * i + 2, 0.)} for i, cid in enumerate(frame['columns'])]
        return res

    # Lateral stiffness of each frame from a unit load; a mechanism makes the direction unsupported.
    try:
        for f in frames:
            r = solve(f, 1000., 0., 0.); f['k_N_m'] = 1000. / r['top_u']
    except FrameError as err:
        out['status'] = 'unsupported'
        for rule in ['SEISMIC-V', 'DRIFT', 'COLUMN', 'FOOT-LATERAL']: check(rule, 'unsupported', [b.id], f'{err}. Use fixed column bases or add frame members.')
        return out

    c, missing, unsupported = coefficients(b)
    out['weight_kN'] = W; out['coefficients'] = c; out['missing'] = missing
    seismic_ready = not missing and not unsupported
    clause_v = 'NSCP 2015 §208 static force procedure; Tables 208-7/208-8 (verify transcription)'
    if unsupported:
        out['status'] = 'unsupported'; check('SEISMIC-V', 'unsupported', [b.id], unsupported, clause=clause_v)
    elif missing:
        out['status'] = 'missing_input'; check('SEISMIC-V', 'missing_input', [b.id], 'Missing: ' + ', '.join(missing) + '. Seismic checks stay pending until entered.', clause=clause_v)
    else:
        vs = base_shear(W, h, c, lat.ct, lat.zone); out['base_shear'] = vs

    area = b.width * b.depth
    directions = {}
    if seismic_ready:
        V = vs['V_kN'] * 1000
        for d in ['X', 'Y']:
            fs = [f for f in frames if f['direction'] == d]; ktot = sum(f['k_N_m'] for f in fs)
            rows = []; rmax = 0.; resid = 0.
            for f in fs:
                share = f['k_N_m'] / ktot; r = solve(f, V * share, 0., 0.)
                shears = [abs(x['H']) for x in r['base']]
                pair = max([shears[i] + shears[i + 1] for i in range(len(shears) - 1)] or shears)
                rmax = max(rmax, pair / V); resid = max(resid, abs(sum(x['H'] for x in r['base']) - V * share))
                rows.append({'id': f['id'], 'line_m': f['line'], 'columns': f['columns'], 'stiffness_kN_mm': f['k_N_m'] / 1e6, 'share': share, 'drift_s_mm': r['top_u'] * 1000})
            ds = max(x['drift_s_mm'] for x in rows); dm = .7 * c['R'] * ds
            limit = (.025 if vs['T_s'] < .7 else .020) * h * 1000
            rho = min(1.5, max(1.0, 2 - 6.1 / (rmax * math.sqrt(area))))
            directions[d] = {'frames': rows, 'drift_s_mm': ds, 'drift_m_mm': dm, 'limit_mm': limit, 'rmax': rmax, 'rho': rho, 'equilibrium_residual_N': resid, 'status': 'pass' if dm <= limit else 'fail'}
            check('DRIFT', directions[d]['status'], [f['id'] for f in fs],
                  f'{d}: ΔM = 0.7·R·ΔS = 0.7 × {c["R"]:g} × {ds:.2f} mm = {dm:.1f} mm; limit {limit:.0f} mm ({"0.025" if vs["T_s"] < .7 else "0.020"}·h)',
                  {'direction': d, 'drift_s_mm': ds, 'drift_m_mm': dm, 'limit_mm': limit, 'R': c['R']}, 'NSCP 2015 §208 storey drift limitation (verify)')
        out['directions'] = directions
        check('SEISMIC-V', 'pass', [b.id],
              f'V = {vs["V_kN"]:.1f} kN ({vs["Cs"] * 100:.1f}% of W = {W:.1f} kN), governed by {vs["governing"]}; T = {vs["T_s"]:.3f} s, '
              f'Ca = {c["Ca"]:.2f}, Cv = {c["Cv"]:.2f}, R = {c["R"]:g}, I = {c["I"]:g}; ρ = {directions["X"]["rho"]:.2f} (X), {directions["Y"]["rho"]:.2f} (Y)',
              {**c, 'W_kN': W, 'T_s': vs['T_s'], 'V_kN': vs['V_kN'], 'governing': vs['governing']}, clause_v)

    # Strength combinations (LRFD): gravity, then 1.2D + Ev + ρEh and 0.9D − Ev + ρEh in both senses of each direction.
    combos = [('1.4D', 1.4, 0., None, 0), ('1.2D + 1.6Lr', 1.2, 1.6, None, 0)]
    if seismic_ready:
        ev = .5 * c['Ca'] * c['I']
        for d in ['X', 'Y']:
            for sign in [1, -1]:
                combos += [(f'1.2D + Ev {"+" if sign > 0 else "−"} ρE{d.lower()}', 1.2 + ev, 0., d, sign), (f'0.9D − Ev {"+" if sign > 0 else "−"} ρE{d.lower()}', .9 - ev, 0., d, sign)]
    cap = column_capacity(col_sec, E, Fy, lat.k_factor, h)
    Mc_member = .9 * Fy * beam_sec['Zp']
    colres = {cid: {'utilization': 0., 'combo': None} for cid in cols}; memres = {}; resid_all = 0.
    for name, fd, fl, d, sign in combos:
        for f in frames:
            if d is None and f['direction'] == 'Y': continue  # gravity column demand is complete in the X frames
            if d is not None and f['direction'] != d: continue
            H = 0.
            if d is not None:
                ktot = sum(x['k_N_m'] for x in frames if x['direction'] == d)
                H = sign * directions[d]['rho'] * vs['V_kN'] * 1000 * f['k_N_m'] / ktot
            r = solve(f, H, fd, fl); resid_all = max(resid_all, abs(sum(x['H'] for x in r['base']) - H))
            for (kind, mid), m in zip(r['kinds'], r['members']):
                if kind == 'column':
                    # N at the base end acts along +local x (upward) on the member when it is in compression.
                    Pcol = m['N_i'] + fd * col_w * 1000  # frames carry no column self-weight; add all of it (conservative)
                    M = max(abs(m['M_i']), abs(m['M_j'])); u = interaction(Pcol, M, cap)
                    if u > colres[mid]['utilization']: colres[mid] = {'utilization': u, 'combo': name, 'P_kN': Pcol / 1000, 'M_kNm': M / 1000, 'direction': d}
                else:
                    u = m['M_max'] / Mc_member
                    if u > memres.get(mid, {'utilization': -1})['utilization']: memres[mid] = {'utilization': u, 'combo': name, 'M_kNm': m['M_max'] / 1000, 'kind': kind}
    out['equilibrium_residual_N'] = resid_all
    clause_c = 'NSCP 2015 Ch. 5 (AISC 360-10 §E3 flexural buckling, §H1-1 interaction); §203 LRFD combinations (verify)'
    out['columns'] = []
    for cid, x in colres.items():
        status = 'unsupported' if not cap['compact'] else ('fail' if x['utilization'] > 1 else ('pass' if seismic_ready else 'missing_input'))
        out['columns'].append({'id': f'column-{cid}', 'column_id': cid, **x, 'status': status})
        scope = '' if seismic_ready else ' Gravity combinations only; seismic combinations pending inputs.'
        check('COLUMN', status, [cid], f'{col_sec["label"]}: utilization {x["utilization"]:.2f} under {x["combo"]} (P = {x.get("P_kN", 0):.1f} kN, M = {x.get("M_kNm", 0):.2f} kN·m); '
              f'KL/r = {cap["KL_r"]:.0f}, φPn = {cap["Pc"] / 1000:.0f} kN, φMn = {cap["Mc"] / 1000:.1f} kN·m.{scope}',
              {'utilization': x['utilization'], 'combo': x['combo'], 'K': lat.k_factor, 'section': e.column_section}, clause_c)
    out['members'] = [{'id': mid, **x, 'status': 'fail' if x['utilization'] > 1 else ('pass' if seismic_ready else 'missing_input')} for mid, x in memres.items()]
    if seismic_ready:
        for x in out['members']:
            check('FRAME-MEMBER', x['status'], [x['id']], f'{x["kind"].title()} {beam_sec["label"]}: peak M = {x["M_kNm"]:.2f} kN·m under {x["combo"]}; φMp = {Mc_member / 1000:.1f} kN·m (utilization {x["utilization"]:.2f}). Lateral-torsional buckling not evaluated.',
                  {'utilization': x['utilization'], 'combo': x['combo']}, 'NSCP 2015 Ch. 5 (AISC 360-10 §F7 plastic flexure, compact HSS); §203 LRFD combinations (verify)')
    out['column_capacity'] = {**cap, 'Pc_kN': cap['Pc'] / 1000, 'Mc_kNm': cap['Mc'] / 1000, 'section': col_sec['label']}

    # Footings: ASD D + Ev/1.4 + ρE/1.4 and 0.6D − Ev/1.4 + ρE/1.4, eccentric contact and sliding at the base of the pad.
    out['footings'] = []
    if seismic_ready:
        B = e.footing_width; t = e.footing_thickness; allow = e.soil.value; mu = lat.friction.value
        pad = B * B * t * 24
        worst = {}
        for name, fd in [('D + (Ev + ρE)/1.4', 1 + .5 * c['Ca'] * c['I'] / 1.4), ('0.6D − (Ev − ρE)/1.4', .6 - .5 * c['Ca'] * c['I'] / 1.4)]:
            for d in ['X', 'Y']:
                ktot = sum(x['k_N_m'] for x in frames if x['direction'] == d)
                for sign in [1, -1]:
                    for f in [x for x in frames if x['direction'] == d]:
                        H = sign * directions[d]['rho'] * vs['V_kN'] * 1000 / 1.4 * f['k_N_m'] / ktot
                        r = solve(f, H, fd, 0.)
                        for base in r['base']:
                            P = base['V'] / 1000 + fd * (pad + col_w)  # kN, compression positive
                            Hb = abs(base['H']) / 1000; M = abs(base['M']) / 1000 + Hb * t
                            if P <= 0: q, ecc, state = None, None, 'uplift'
                            else:
                                ecc = M / P
                                if ecc <= B / 6: q, state = P / B**2 * (1 + 6 * ecc / B), 'full contact'
                                elif ecc < B / 2: q, state = 2 * P / (3 * B * (B / 2 - ecc)), 'partial contact'
                                else: q, state = None, 'overturning'
                            fs_slide = (mu * P / Hb if Hb > 0 else math.inf) if (mu is not None and P > 0) else None
                            bearing_ok = q is not None and allow is not None and q <= allow
                            slide_ok = fs_slide is not None and fs_slide >= lat.sliding_fs
                            status = ('missing_input' if allow is None or (mu is None and state not in ['uplift', 'overturning']) else
                                      'pass' if bearing_ok and slide_ok else 'fail')
                            rank = {'fail': 3, 'missing_input': 2, 'pass': 1}[status]
                            score = (rank, (q or 1e9) / (allow or 1), -(fs_slide or 0))
                            prev = worst.get(base['column_id'])
                            if not prev or score > prev['score']:
                                worst[base['column_id']] = {'score': score, 'status': status, 'combo': f'{name}, {d}{"+" if sign > 0 else "−"}', 'P_kN': P, 'M_kNm': M, 'H_kN': Hb,
                                                            'e_m': ecc, 'q_max_kPa': q, 'allowable_kPa': allow, 'contact': state, 'sliding_fs': fs_slide}
        for cid, x in worst.items():
            x.pop('score'); out['footings'].append({'id': f'foundation-{cid}', 'column_id': cid, **x})
            q = f'{x["q_max_kPa"]:.1f} kPa vs {allow} kPa allowable' if x['q_max_kPa'] is not None else x['contact']
            sl = f'sliding FS {x["sliding_fs"]:.2f} (required {lat.sliding_fs:g})' if x['sliding_fs'] not in (None, math.inf) else ('no base shear' if x['sliding_fs'] == math.inf else 'sliding needs a friction coefficient')
            check('FOOT-LATERAL', x['status'], [f'foundation-{cid}'], f'{x["combo"]}: P = {x["P_kN"]:.1f} kN, M = {x["M_kNm"]:.2f} kN·m, e = {(x["e_m"] or 0):.3f} m ({x["contact"]}); {q}; {sl}. No one-third allowable increase.',
                  {k: v for k, v in x.items() if k != 'status'}, 'Eccentric bearing statics; NSCP 2015 §203 ASD seismic combinations (verify); sliding factor of safety is a project criterion (1.0 with 0.6D)')
    elif not unsupported:
        check('DRIFT', 'missing_input', [b.id], 'Storey drift needs the seismic coefficients.')
        check('FOOT-LATERAL', 'missing_input', [b.id], 'Footing overturning and sliding need the seismic coefficients.')
    order = ['SEISMIC-V', 'DRIFT', 'COLUMN', 'FRAME-MEMBER', 'FOOT-LATERAL', 'WIND']
    out['checks'].sort(key=lambda x: order.index(x['rule']))
    statuses = [x['status'] for x in out['checks'] if x['rule'] != 'WIND']
    out['status'] = out.get('status') or ('fail' if 'fail' in statuses else 'missing_input' if 'missing_input' in statuses else 'pass')
    out['frames'] = [{k: v for k, v in f.items() if k != 'coords'} | {'stiffness_kN_mm': f['k_N_m'] / 1e6} for f in frames]
    return out

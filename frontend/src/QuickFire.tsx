import {useEffect, useMemo, useState} from 'react';
import {AlertTriangle, Loader2, Play, Plus, X} from 'lucide-react';
import {num} from './api';
import {Field} from './ui';
import {NoteSummary, NumberInput, ORDER, Source, type FireRecord} from './QuickCheck';

export type Side = 'top' | 'bottom' | 'left' | 'right';
export type FireRoom = {id: string; name: string; kind: string; x: number; y: number; w: number; h: number};
export type FireInputs = {
  width: number | null; depth: number | null; rooms: FireRoom[];
  doors: {id: string; rooms: [string, string]; at: number | null; width: number}[];
  exits: {id: string; side: Side; offset: number; width: number}[];
  extinguishers: {id: string; x: number; y: number; rating: '2-A' | '3-A' | '4-A'}[];
  occupancy: 'business' | 'business_concentrated' | 'mercantile' | null; hazard: 'low' | 'moderate' | 'high' | null;
  sprinklered: boolean; alarm: 'none' | 'manual' | 'automatic'; emergency_lighting: boolean; exit_signs: boolean; new_building: boolean;
  mercantile_travel_m: number | null; assumed: string[]; entered: string[];
};
export type FireExtraction = {title: string; rooms: {name: string; box: number[]}[]; exits: {text: string; box?: number[] | null}[]; provisions: {kind: string; text: string; box?: number[] | null}[]};

export const FIRE_RULES: Record<string, string> = {
  'FIRE-OCCLOAD': 'Occupant load', 'FIRE-EXITS': 'Number of exits', 'FIRE-TRAVEL': 'Travel distance', 'FIRE-DEADEND': 'Dead-end corridors', 'FIRE-COMMON': 'Common path of travel',
  'FIRE-CAPACITY': 'Exit capacity', 'FIRE-CORRIDOR': 'Corridor width', 'FIRE-SPRINKLER': 'Sprinkler trigger', 'FIRE-ALARM': 'Fire alarm', 'FIRE-EMLIGHT': 'Emergency lighting',
  'FIRE-SIGNS': 'Exit signs', 'FIRE-EXT': 'Portable extinguishers', 'FIRE-SCOPE': 'Not evaluated', 'PH-CODE': 'Outside this screen',
};
const SIDES: Record<Side, string> = {top: 'Top wall', bottom: 'Bottom wall', left: 'Left wall', right: 'Right wall'};
const OCCUPANCY = [['business', 'Business', 'Offices, clinics, banks · 9.3 m² per person'], ['business_concentrated', 'Business, concentrated use', 'BPO and call centres · 4.6 m² per person'], ['mercantile', 'Mercantile', 'Shops and stores · 2.8 m² per person']] as const;
const HAZARD = [['low', 'Low', 'Offices, classrooms · 2-A within 15 m'], ['moderate', 'Moderate', 'Shops, workshops, storage · 3-A within 12 m'], ['high', 'High', 'Woodworking, flammable stock · 4-A within 10 m']] as const;
/** Which drawn element a fire finding points at, so the panel and the sheet select each other. */
export const FIRE_TARGET: Record<string, string> = {'FIRE-TRAVEL': 'travel', 'FIRE-COMMON': 'travel', 'FIRE-EXT': 'reach', 'FIRE-EXITS': 'exits', 'FIRE-CAPACITY': 'exits', 'FIRE-SIGNS': 'exits'};
export const FIRE_TARGET_LABEL: Record<string, string> = {travel: 'Longest travel', reach: 'Farthest from an extinguisher', exits: 'Exits'};

export function fireLabel(field: string) {
  const m = field.match(/^(exit|ext)-(\d+):(\w+)$/);
  if (m) return `${m[1] === 'exit' ? 'exit' : 'extinguisher'} ${m[2]} ${m[3]}`;
  return ({sprinklered: 'sprinklers', alarm: 'fire alarm', emergency_lighting: 'emergency lighting', exit_signs: 'exit signs', new_building: 'new building'} as Record<string, string>)[field] || field;
}

/** The wall two rooms share, as in quickcheck.shared_wall: axis 'x' is a vertical wall at x = at. */
function sharedWall(a: FireRoom, b: FireRoom): {axis: 'x' | 'y'; at: number; lo: number; hi: number} | null {
  for (const [axis, a0, a1, b0, b1, c0, c1, d0, d1] of [['x', a.x, a.x + a.w, b.x, b.x + b.w, a.y, a.y + a.h, b.y, b.y + b.h], ['y', a.y, a.y + a.h, b.y, b.y + b.h, a.x, a.x + a.w, b.x, b.x + b.w]] as const) {
    const at = Math.abs(a1 - b0) <= .05 ? a1 : Math.abs(a0 - b1) <= .05 ? a0 : null, lo = Math.max(c0, d0), hi = Math.min(c1, d1);
    if (at !== null && hi - lo >= .6) return {axis, at, lo, hi};
  }
  return null;
}
function doorSegment(d: FireInputs['doors'][number], rooms: FireRoom[]): number[][] | null {
  const [a, b] = d.rooms.map(id => rooms.find(r => r.id === id));
  const wall = a && b ? sharedWall(a, b) : null; if (!wall) return null;
  const half = Math.min(d.width, wall.hi - wall.lo) / 2, c = Math.min(wall.hi - half, Math.max(wall.lo + half, d.at ?? (wall.lo + wall.hi) / 2));
  return wall.axis === 'x' ? [[wall.at, c - half], [wall.at, c + half]] : [[c - half, wall.at], [c + half, wall.at]];
}
function exitSegment(e: FireInputs['exits'][number], w: number, d: number): number[][] {
  return {top: [[e.offset, 0], [e.offset + e.width, 0]], bottom: [[e.offset, d], [e.offset + e.width, d]], left: [[0, e.offset], [0, e.offset + e.width]], right: [[w, e.offset], [w, e.offset + e.width]]}[e.side];
}

/** The floor plan with what was read (confirm step) or the egress findings (results step), in the image's own pixel space. */
export function FireSheetView({record, inputs, results, selected, onSelect}: {
  record: FireRecord; inputs: FireInputs; results: FireRecord['results']; selected: string[]; onSelect: (id: string) => void;
}) {
  const t = record.transform, w = inputs.width ?? 10, d = inputs.depth ?? 10;
  const [mode, setMode] = useState<'sheet' | 'plan' | 'model'>(t ? (results ? 'plan' : 'sheet') : 'model');
  useEffect(() => {if (t && results) setMode('plan')}, [!!results]);
  const W = record.source.width_px, H = record.source.height_px, onSheet = mode !== 'model' && !!t;
  const k = 40, pad = 1.6;
  const P = (x: number, y: number): [number, number] => onSheet ? [(t!.sx * x + t!.ox) / 1000 * W, (t!.sy * y + t!.oy) / 1000 * H] : [(x + pad) * k, (y + pad) * k];
  const u = onSheet ? Math.max(W, H) / 1000 : k / 30;
  const view = useMemo(() => {
    if (!onSheet) return `0 0 ${(w + 2 * pad) * k} ${(d + 2 * pad) * k}`;
    if (mode === 'sheet') return `0 0 ${W} ${H}`;
    const [x0, y0] = P(-pad, -pad), [x1, y1] = P(w + pad, d + pad);
    const left = Math.max(0, Math.min(x0, x1)), top = Math.max(0, Math.min(y0, y1));
    return `${left} ${top} ${Math.min(W, Math.max(x0, x1)) - left} ${Math.min(H, Math.max(y0, y1)) - top}`;
  }, [mode, onSheet, w, d, W, H, t]);
  const fire = results?.fire?.enabled ? results.fire : null;
  const status = (rule: string) => results?.checks.filter(c => c.rule_id === rule).map(c => c.status).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))[0] || 'pass';
  const unreachable = new Set(fire?.travel.unreachable ?? []);
  const line = (pts: number[][]) => pts.map(p => P(p[0], p[1]).join(',')).join(' ');
  const rect = (r: FireRoom) => {const [x0, y0] = P(r.x, r.y), [x1, y1] = P(r.x + r.w, r.y + r.h); return {x: Math.min(x0, x1), y: Math.min(y0, y1), width: Math.abs(x1 - x0), height: Math.abs(y1 - y0)}};
  const doors = fire ? fire.doors ?? [] : inputs.doors.map(x => ({id: x.id, seg: doorSegment(x, inputs.rooms)})).filter(x => x.seg).map(x => ({id: x.id, a: x.seg![0], b: x.seg![1]}));
  const exits = fire ? fire.exits.map(e => ({id: e.id, a: e.a, b: e.b})) : inputs.exits.map(e => {const [a, b] = exitSegment(e, w, d); return {id: e.id, a, b}});
  const pick = (id: string) => ({onClick: () => onSelect(id), role: 'button', tabIndex: 0, onKeyDown: (e: React.KeyboardEvent) => {if (e.key === 'Enter') onSelect(id)}});
  const path = (id: string, pts: number[][], cls: string, s: string, text: string) => {
    if (pts.length < 2) return null; const [ex, ey] = P(pts[0][0], pts[0][1]), on = selected.includes(id), right = pts[0][0] > w / 2;
    return <g className={`finding ${cls} ${s}` + (on ? ' selected' : '')} {...pick(id)} aria-label={text}>
      {on && <polyline className="halo" points={line(pts)} strokeWidth={u * 14} fill="none" strokeLinejoin="round"/>}
      <polyline points={line(pts)} strokeWidth={u * 3} fill="none" strokeDasharray={`${u * 8} ${u * 5}`}/><polyline className="hit" points={line(pts)} strokeWidth={u * 14} fill="none"/>
      <circle cx={ex} cy={ey} r={u * 6}/><text x={ex + (right ? -u * 12 : u * 12)} y={ey - u * 9} fontSize={u * 12} style={{textAnchor: right ? 'end' : 'start'}}>{text}</text></g>;
  };
  return <div className="sheet-view">
    <div className="sheet-toolbar">
      <span className="quiet">{record.source.name}{record.source.pages > 1 ? ` · page ${record.source.page + 1} of ${record.source.pages}` : ''}</span>
      <div className="segmented" role="group" aria-label="View">
        {t && <button aria-pressed={mode === 'sheet'} onClick={() => setMode('sheet')}>Whole sheet</button>}
        {t && <button aria-pressed={mode === 'plan'} onClick={() => setMode('plan')}>Zoom to plan</button>}
        <button aria-pressed={mode === 'model'} onClick={() => setMode('model')}>Model</button>
      </div>
    </div>
    {!t && <p className="sheet-warning"><AlertTriangle size={13}/> The building outline could not be located on the page, so the plan is shown on the model view.</p>}
    <svg className={'sheet-svg' + (onSheet ? ' on-sheet' : '')} viewBox={view} role="img" aria-label={results ? 'Egress findings drawn on the floor plan' : 'What was read from the floor plan'}>
      {onSheet && <image href={`/api/quick-checks/${record.id}/image`} x={0} y={0} width={W} height={H}/>}
      {onSheet && <rect x={0} y={0} width={W} height={H} className="sheet-wash"/>}
      {!onSheet && <rect {...rect({id: '', name: '', kind: '', x: 0, y: 0, w, h: d})} className="fp-outline" strokeWidth={u * 2.5}/>}
      {inputs.rooms.map(r => {const b = rect(r), on = selected.includes(r.id);
        return <g key={r.id} className={'fp-room' + (unreachable.has(r.id) ? ' unreachable' : '') + (on ? ' selected' : '')} {...pick(r.id)} aria-label={`${r.name}, ${num(r.w)} × ${num(r.h)} m${unreachable.has(r.id) ? ', no path to an exit' : ''}`}>
          <rect {...b} strokeWidth={u * 1.3}/>
          {!onSheet && <text x={b.x + b.width / 2} y={b.y + b.height / 2} fontSize={u * 11}>{r.name}</text>}
          {unreachable.has(r.id) && <text className="no-exit" x={b.x + b.width / 2} y={b.y + b.height / 2 + u * (onSheet ? 28 : 16)} fontSize={u * 11}>No path to an exit</text>}</g>})}
      {doors.map(x => {const [x1, y1] = P(x.a[0], x.a[1]), [x2, y2] = P(x.b[0], x.b[1]); return <line key={x.id} className="fp-door" x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={u * 5}/>})}
      {exits.map(e => {const [x1, y1] = P(e.a[0], e.a[1]), [x2, y2] = P(e.b[0], e.b[1]), s = results ? status('FIRE-EXITS') === 'fail' || status('FIRE-CAPACITY') === 'fail' ? 'fail' : 'pass' : 'read', on = selected.includes('exits');
        return <g key={e.id} className={`finding fp-exit ${s}` + (on ? ' selected' : '')} {...pick('exits')} aria-label={`Exit ${e.id}`}>
          {on && <line className="halo" x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={u * 18} strokeLinecap="round"/>}
          <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={u * 7}/><line className="hit" x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={u * 18}/></g>})}
      {inputs.extinguishers.map(e => {const [x, y] = P(e.x, e.y); return <g key={e.id} className="fp-ext"><circle cx={x} cy={y} r={u * 7} strokeWidth={u * 1.5}/><title>{`${e.id} · ${e.rating}`}</title></g>})}
      {fire && path('reach', fire.extinguishers.critical_path, 'fp-reach', status('FIRE-EXT'), fire.extinguishers.max_travel_m == null ? 'No extinguisher' : `${fire.extinguishers.max_travel_m.toFixed(1)} m to an extinguisher`)}
      {fire && path('travel', fire.travel.critical_path, 'fp-travel', status('FIRE-TRAVEL'), `${(fire.travel.max_m ?? 0).toFixed(1)} m to an exit`)}
    </svg>
    <div className="sheet-legend">{results ? <><span className="lg fail">Fails</span><span className="lg pass">Passes</span><span className="lg exit">Exit</span><span className="lg ext">Extinguisher</span><span className="quiet">Select a path or the exits to see the finding.</span></> :
      <><span className="lg read">Rooms and doors read</span><span className="lg exit">Exit</span><span className="lg ext">Extinguisher</span></>}</div>
  </div>;
}

function editFire<K extends keyof FireInputs>(inputs: FireInputs, field: K, value: FireInputs[K], keys: string[] = [String(field)]): FireInputs {
  return {...inputs, [field]: value, assumed: inputs.assumed.filter(f => !keys.includes(f)), entered: Array.from(new Set([...inputs.entered, ...keys]))};
}

export function FireConfirmPanel({record, inputs, setInputs, busy, onRun, onCancel, selected, onSelect}: {
  record: FireRecord; inputs: FireInputs; setInputs: (i: FireInputs) => void; busy: string; onRun: () => void; onCancel?: () => void; selected: string[]; onSelect: (id: string) => void;
}) {
  const set = <K extends keyof FireInputs>(f: K, v: FireInputs[K], keys?: string[]) => setInputs(editFire(inputs, f, v, keys));
  const room = (id: string) => inputs.rooms.find(r => r.id === id)?.name || id;
  const [pair, setPair] = useState<[string, string]>(['', '']);
  const next = (prefix: string, ids: string[]) => {let n = ids.length + 1; while (ids.includes(`${prefix}-${n}`)) n++; return `${prefix}-${n}`};
  const blockers = [
    inputs.occupancy == null && 'Choose the occupancy. It is never assumed.',
    inputs.hazard == null && 'Choose the contents hazard.',
    (inputs.width == null || inputs.depth == null) && 'Enter the overall width and depth.',
    !inputs.rooms.length && 'Add at least one room.',
  ].filter(Boolean) as string[];
  useEffect(() => {if (selected[0]?.startsWith('room-')) document.getElementById('fp-' + selected[0])?.scrollIntoView({block: 'nearest', behavior: 'smooth'})}, [selected.join()]);
  return <div className="confirm-panel">
    <h2>Confirm what was read</h2>
    <p className="quiet">{record.extraction.title || record.source.name}. Choose the occupancy and hazard, then correct anything that is wrong. Nothing is calculated until you run the check.</p>
    <NoteSummary notes={record.notes}/>

    <h3 className="form-head">Occupancy <span className={'source-chip ' + (inputs.occupancy == null ? 'missing' : inputs.entered.includes('occupancy') ? 'entered' : 'read')}>{inputs.occupancy == null ? 'Required' : inputs.entered.includes('occupancy') ? 'Chosen' : 'From sheet'}</span></h3>
    <div className="choice-list" role="radiogroup" aria-label="Occupancy">
      {OCCUPANCY.map(([id, label, hint]) => <button key={id} role="radio" aria-checked={inputs.occupancy === id} className={inputs.occupancy === id ? 'on' : ''} onClick={() => set('occupancy', id)}><strong>{label}</strong><span>{hint}</span></button>)}
    </div>
    <h3 className="form-head">Contents hazard <span className={'source-chip ' + (inputs.hazard == null ? 'missing' : 'entered')}>{inputs.hazard == null ? 'Required' : 'Chosen'}</span></h3>
    <div className="choice-list" role="radiogroup" aria-label="Contents hazard">
      {HAZARD.map(([id, label, hint]) => <button key={id} role="radio" aria-checked={inputs.hazard === id} className={inputs.hazard === id ? 'on' : ''} onClick={() => set('hazard', id)}><strong>{label}</strong><span>{hint}</span></button>)}
    </div>
    {inputs.occupancy === 'mercantile' && !inputs.sprinklered && <NumberInput label="Unsprinklered mercantile travel limit (optional)" unit="m" value={inputs.mercantile_travel_m} onChange={v => set('mercantile_travel_m', v)} step={1}
      hint={<span className="quiet">the C/MFM's value; blank shows as missing input</span>}/>}

    <h3 className="form-head">Provisions</h3>
    {([['sprinklered', 'Automatic sprinklers throughout'], ['exit_signs', 'Exit signs'], ['emergency_lighting', 'Emergency lighting'], ['new_building', 'New building']] as const).map(([f, label]) =>
      <label key={f} className="check-row"><input type="checkbox" checked={inputs[f]} onChange={e => set(f, e.target.checked)}/>{label}<Source inputs={inputs} field={f}/></label>)}
    <Field label="Fire alarm"><select value={inputs.alarm} onChange={e => set('alarm', e.target.value as FireInputs['alarm'])}><option value="none">None</option><option value="manual">Manual (pull stations)</option><option value="automatic">Automatic (detection)</option></select></Field>
    <div className="field-source"><Source inputs={inputs} field="alarm"/></div>

    <h3 className="form-head">Building outline <Source inputs={inputs} field="width" value={inputs.width}/></h3>
    <div className="field-pair">
      <NumberInput label="Width (across)" unit="m" value={inputs.width} onChange={v => set('width', v, ['width'])} step={0.05}/>
      <NumberInput label="Depth (down)" unit="m" value={inputs.depth} onChange={v => set('depth', v, ['depth'])} step={0.05}/>
    </div>
    {inputs.width != null && inputs.depth != null && <p className="helper tight">{num(inputs.width * inputs.depth)} m² gross · rooms cover {num(inputs.rooms.reduce((a, r) => a + r.w * r.h, 0))} m²</p>}

    <h3 className="form-head">Rooms <span className="quiet">{inputs.rooms.length} · metres from the top-left corner</span></h3>
    <div className="fp-table rooms">
      <span>Name</span><span>x</span><span>y</span><span>w</span><span>h</span><span/>
      {inputs.rooms.map((r, n) => {const put = (patch: Partial<FireRoom>) => set('rooms', inputs.rooms.map((x, i) => i === n ? {...x, ...patch} : x), ['rooms']);
        return <div key={r.id} id={'fp-' + r.id} className={'fp-row' + (selected.includes(r.id) ? ' on' : '')} onFocus={() => onSelect(r.id)}>
          <input aria-label="Room name" value={r.name} onChange={e => put({name: e.target.value})}/>
          {(['x', 'y', 'w', 'h'] as const).map(f => <input key={f} aria-label={`${r.name} ${f} (m)`} type="number" step={0.05} min={0} value={r[f]} onChange={e => Number.isFinite(Number(e.target.value)) && put({[f]: Number(e.target.value)})}/>)}
          <button className="icon-button" aria-label={`Remove ${r.name}`} onClick={() => setInputs(editFire({...inputs, doors: inputs.doors.filter(d => !d.rooms.includes(r.id)), extinguishers: inputs.extinguishers}, 'rooms', inputs.rooms.filter(x => x.id !== r.id)))}><X size={13}/></button>
        </div>})}
    </div>
    <button className="text-button" onClick={() => set('rooms', [...inputs.rooms, {id: next('room-new', inputs.rooms.map(r => r.id)), name: 'New room', kind: 'office', x: 0, y: 0, w: 3, h: 3}])}><Plus size={13}/> Add room</button>

    <h3 className="form-head">Interior doors <span className="quiet">{inputs.doors.length} · travel only passes these</span></h3>
    <ul className="fp-list">{inputs.doors.map(x => {const ok = !!doorSegment(x, inputs.rooms);
      return <li key={x.id} className={ok ? '' : 'bad'}><span>{room(x.rooms[0])} ↔ {room(x.rooms[1])}{!ok && ' · not on a shared wall'}</span>
        <button className="icon-button" aria-label={`Remove door ${room(x.rooms[0])} to ${room(x.rooms[1])}`} onClick={() => set('doors', inputs.doors.filter(d => d.id !== x.id))}><X size={13}/></button></li>})}</ul>
    <div className="fp-add">
      {[0, 1].map(i => <select key={i} aria-label={`Door room ${i + 1}`} value={pair[i]} onChange={e => setPair(i ? [pair[0], e.target.value] : [e.target.value, pair[1]])}><option value="">Room…</option>{inputs.rooms.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>)}
      <button className="button secondary" disabled={!pair[0] || !pair[1] || pair[0] === pair[1]} onClick={() => {set('doors', [...inputs.doors, {id: next('door', inputs.doors.map(d => d.id)), rooms: pair, at: null, width: .9}]); setPair(['', ''])}}><Plus size={13}/> Door</button>
    </div>

    <h3 className="form-head">Exits <span className="quiet">doors in an exterior wall</span></h3>
    <div className="fp-table exits">
      <span>Wall</span><span>From corner</span><span>Width</span><span/>
      {inputs.exits.map((e, n) => {const put = (patch: Partial<FireInputs['exits'][number]>, key: string) => set('exits', inputs.exits.map((x, i) => i === n ? {...x, ...patch} : x), [key]);
        return <div key={e.id} className="fp-row">
          <select aria-label={`${e.id} wall`} value={e.side} onChange={ev => put({side: ev.target.value as Side}, `${e.id}:side`)}>{Object.entries(SIDES).map(([id, l]) => <option key={id} value={id}>{l}</option>)}</select>
          <input aria-label={`${e.id} offset (m)`} type="number" step={0.05} min={0} value={e.offset} onChange={ev => put({offset: Number(ev.target.value) || 0}, `${e.id}:offset`)}/>
          <span className="with-chip"><input aria-label={`${e.id} width (m)`} type="number" step={0.05} min={0.5} value={e.width} onChange={ev => put({width: Number(ev.target.value) || .9}, `${e.id}:width`)}/>{inputs.assumed.includes(`${e.id}:width`) && <span className="source-chip assumed">Assumed</span>}</span>
          <button className="icon-button" aria-label={`Remove ${e.id}`} onClick={() => set('exits', inputs.exits.filter(x => x.id !== e.id))}><X size={13}/></button>
        </div>})}
    </div>
    <button className="text-button" onClick={() => set('exits', [...inputs.exits, {id: next('exit', inputs.exits.map(e => e.id)), side: 'bottom', offset: 0, width: .9}])}><Plus size={13}/> Add exit</button>

    <h3 className="form-head">Extinguishers <span className="quiet">{inputs.extinguishers.length}</span></h3>
    <div className="fp-table exits">
      <span>x</span><span>y</span><span>Rating</span><span/>
      {inputs.extinguishers.map((e, n) => {const put = (patch: Partial<FireInputs['extinguishers'][number]>, key: string) => set('extinguishers', inputs.extinguishers.map((x, i) => i === n ? {...x, ...patch} : x), [key]);
        return <div key={e.id} className="fp-row">
          <input aria-label={`${e.id} x (m)`} type="number" step={0.1} min={0} value={e.x} onChange={ev => put({x: Number(ev.target.value) || 0}, `${e.id}:x`)}/>
          <input aria-label={`${e.id} y (m)`} type="number" step={0.1} min={0} value={e.y} onChange={ev => put({y: Number(ev.target.value) || 0}, `${e.id}:y`)}/>
          <span className="with-chip"><select aria-label={`${e.id} rating`} value={e.rating} onChange={ev => put({rating: ev.target.value as '2-A'}, `${e.id}:rating`)}>{['2-A', '3-A', '4-A'].map(r => <option key={r}>{r}</option>)}</select>{inputs.assumed.includes(`${e.id}:rating`) && <span className="source-chip assumed">Assumed</span>}</span>
          <button className="icon-button" aria-label={`Remove ${e.id}`} onClick={() => set('extinguishers', inputs.extinguishers.filter(x => x.id !== e.id))}><X size={13}/></button>
        </div>})}
    </div>
    <button className="text-button" onClick={() => set('extinguishers', [...inputs.extinguishers, {id: next('ext', inputs.extinguishers.map(e => e.id)), x: (inputs.width ?? 2) / 2, y: (inputs.depth ?? 2) / 2, rating: '2-A'}])}><Plus size={13}/> Add extinguisher</button>

    <div className="run-bar">
      {blockers.map(b => <p key={b} className="helper tight">{b}</p>)}
      <button className="button primary full" disabled={!!busy || blockers.length > 0} onClick={onRun}>{busy ? <><Loader2 size={14} className="spin"/> {busy}</> : <><Play size={14}/> Run fire and egress check</>}</button>
      {onCancel && <button className="button secondary full" disabled={!!busy} onClick={onCancel}>Back to findings</button>}
      <p className="helper tight">Provisions not shown on the sheet are screened as not provided. Missing values are never filled in.</p>
    </div>
  </div>;
}

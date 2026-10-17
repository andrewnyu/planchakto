import {useEffect, useState, type ReactNode} from 'react';
import {AlertTriangle, CheckCircle2, Droplets, Loader2, Play, Zap} from 'lucide-react';
import type {Building, Result} from './types';
import {Field} from './ui';

type Note = {level: 'read' | 'assumed' | 'missing' | 'conflict' | 'unsupported'; field?: string | null; message: string};

export type ServiceDiscipline = 'plumbing' | 'electrical';
export type ServiceRoom = {id: string; name: string; kind: string; x: number; y: number; w: number; h: number};
export type ServiceItem = {id: string; name: string; room_id: string; kind: 'sink' | 'wc' | 'basin' | 'equipment'; x: number; y: number; watts: number | null; circuit_id: string | null};
export type ServiceCircuit = {id: string; name: string; voltage: number | null; power_factor: number | null; demand_factor: number | null};
export type ServiceInputs = {
  discipline: ServiceDiscipline; width: number | null; depth: number | null; rooms: ServiceRoom[]; items: ServiceItem[];
  water: number[] | null; drain: number[] | null; panel: number[] | null; drain_fall_m: number | null; drain_slope: number | null;
  circuits: ServiceCircuit[]; assumed: string[]; entered: string[];
};
type Transform = {sx: number; ox: number; sy: number; oy: number; residual: number};
type QuickResult = Result & {coverage?: {checked: string[]; not_checked: {item: string; reason: string}[]}};
export type ServiceRecord = {
  id: string; discipline: ServiceDiscipline; status: 'confirm' | 'checked'; mode: 'live' | 'recorded';
  source: {name: string; mime_type: string; page: number; pages: number; width_px: number; height_px: number}; transform: Transform | null; notes: Note[];
  extraction: {title: string}; inputs: ServiceInputs; model: Building | null; results: QuickResult | null;
};

export const SERVICE_RULES: Record<string, string> = {ROUTE: 'Plan connection', DRAIN: 'Gravity drain fall', ELECTRICAL: 'Circuit load arithmetic', 'PH-CODE': 'Outside this screen'};
export const serviceLabel = (id: string, record: ServiceRecord) => {
  const source = id.replace(/^(water|drain|conduit)-/, '');
  return record.inputs.items.find(x => x.id === source)?.name || source;
};

function Source({inputs, field, value}: {inputs: ServiceInputs; field: string; value?: unknown}) {
  const state = inputs.entered.includes(field) ? 'entered' : inputs.assumed.includes(field) ? 'assumed' : value === null ? 'missing' : 'read';
  return <span className={'source-chip ' + state}>{{entered: 'Entered', assumed: 'Assumed', missing: 'Missing', read: 'From sheet'}[state]}</span>;
}
function NumberInput({label, unit, value, onChange, hint, step = .01}: {label: string; unit: string; value: number | null; onChange: (v: number | null) => void; hint?: ReactNode; step?: number}) {
  const [text, setText] = useState(value == null ? '' : String(value));
  useEffect(() => {if ((text === '' ? null : Number(text)) !== value) setText(value == null ? '' : String(value))}, [value]);
  return <label className="field quick-field"><span>{label} {hint}</span><div className="unit-input"><input type="number" step={step} min={0} value={text} placeholder="Not on the sheet" onChange={e => {setText(e.target.value); const v = e.target.value === '' ? null : Number(e.target.value); if (v === null || Number.isFinite(v)) onChange(v)}}/><em>{unit}</em></div></label>;
}
function NoteSummary({notes}: {notes: Note[]}) {
  const count = (level: Note['level']) => notes.filter(n => n.level === level).length, problems = notes.filter(n => ['unsupported', 'conflict', 'missing'].includes(n.level));
  return <><div className="read-summary"><span className="source-chip read">{count('read')} read</span><span className="source-chip assumed">{count('assumed')} assumed</span><span className="source-chip missing">{count('missing')} missing</span>{count('conflict') + count('unsupported') > 0 && <span className="source-chip conflict">{count('conflict') + count('unsupported')} limitation{count('conflict') + count('unsupported') === 1 ? '' : 's'}</span>}</div>
    {problems.length > 0 && <ul className="note-list">{problems.map((n, i) => <li key={i} className={n.level}><AlertTriangle size={13}/><span>{n.message}</span></li>)}</ul>}
    <details className="note-details"><summary>Values read ({count('read')})</summary><ul className="note-list">{notes.filter(n => n.level === 'read').map((n, i) => <li key={i} className="read"><CheckCircle2 size={13}/><span>{n.message}</span></li>)}</ul></details></>;
}

function changed<K extends keyof ServiceInputs>(inputs: ServiceInputs, field: K, value: ServiceInputs[K]): ServiceInputs {
  return {...inputs, [field]: value, assumed: inputs.assumed.filter(x => x !== field), entered: Array.from(new Set([...inputs.entered, field]))};
}

export function ServiceSheetView({record, inputs, results, selected, onSelect}: {record: ServiceRecord; inputs: ServiceInputs; results: QuickResult | null; selected: string[]; onSelect: (id: string) => void}) {
  const [mode, setMode] = useState<'sheet' | 'plan'>(record.transform ? 'sheet' : 'plan');
  useEffect(() => {if (record.transform && results) setMode('sheet')}, [!!results]);
  const onSheet = mode === 'sheet' && !!record.transform, W = record.source.width_px, H = record.source.height_px, w = inputs.width || 10, d = inputs.depth || 10;
  const pad = 1.2, k = 44, viewW = (w + pad * 2) * k, viewH = (d + pad * 2) * k;
  const P = (x: number, y: number): [number, number] => onSheet ? [((record.transform!.sx * x + record.transform!.ox) / 1000) * W, ((record.transform!.sy * y + record.transform!.oy) / 1000) * H] : [(x + pad) * k, (y + pad) * k];
  const u = onSheet ? Math.max(W, H) / 1000 : 1;
  const utility = inputs.discipline === 'plumbing' ? [['water', inputs.water], ['drain', inputs.drain]] as const : [['panel', inputs.panel]] as const;
  return <div className="sheet-view">
    <div className="sheet-toolbar"><strong>{record.source.name}</strong><div className="segmented"><button aria-pressed={mode === 'sheet'} disabled={!record.transform} onClick={() => setMode('sheet')}>Drawing overlay</button><button aria-pressed={mode === 'plan'} onClick={() => setMode('plan')}>Reconstructed plan</button></div></div>
    <svg className={'sheet-svg' + (onSheet ? ' on-sheet' : '')} viewBox={`0 0 ${onSheet ? W : viewW} ${onSheet ? H : viewH}`} aria-label={`${inputs.discipline} points and routes`}>
      {onSheet && <image href={`/api/quick-checks/${record.id}/image`} width={W} height={H}/>}<rect className="sheet-wash" width="100%" height="100%"/>
      {!onSheet && <rect className="fp-outline" x={P(0, 0)[0]} y={P(0, 0)[1]} width={w * k} height={d * k} strokeWidth={2}/>} 
      {inputs.rooms.map(r => {const [x, y] = P(r.x, r.y), [x2, y2] = P(r.x + r.w, r.y + r.h); return <g className="fp-room" key={r.id}><rect x={x} y={y} width={x2 - x} height={y2 - y} strokeWidth={u}/><text x={(x + x2) / 2} y={(y + y2) / 2} fontSize={u * 10}>{r.name}</text></g>})}
      {results?.routing.routes.map(route => {const points = route.points.map(p => P(p[0], p[1]).join(',')).join(' '), on = selected.includes(route.id) || selected.includes(route.source_id); return <g key={route.id} className={'finding service-route ' + route.status + (on ? ' selected' : '')} role="button" tabIndex={0} onClick={() => onSelect(route.id)} onKeyDown={e => e.key === 'Enter' && onSelect(route.id)}><polyline className="hit" points={points} fill="none" strokeWidth={u * 14}/><polyline points={points} fill="none" strokeWidth={u * 3}/></g>})}
      {inputs.items.map(item => {const [x, y] = P(item.x, item.y), on = selected.some(id => id === item.id || id.endsWith(item.id)); return <g key={item.id} className={'service-point ' + inputs.discipline + (on ? ' selected' : '')} role="button" tabIndex={0} onClick={() => onSelect(item.id)}><circle cx={x} cy={y} r={u * 7}/><text x={x} y={y + u * 3} fontSize={u * 8}>{inputs.discipline === 'plumbing' ? item.kind === 'wc' ? 'WC' : item.kind === 'basin' ? 'L' : 'S' : 'E'}</text></g>})}
      {utility.map(([id, point]) => point && <g key={id} className={'service-utility ' + inputs.discipline}><rect x={P(point[0], point[1])[0] - u * 7} y={P(point[0], point[1])[1] - u * 7} width={u * 14} height={u * 14}/><text x={P(point[0], point[1])[0]} y={P(point[0], point[1])[1] + u * 3} fontSize={u * 7}>{id === 'panel' ? 'LP' : id === 'water' ? 'W' : 'D'}</text></g>)}
    </svg>
    <div className="sheet-legend"><span className={'lg ' + inputs.discipline}>{inputs.discipline === 'plumbing' ? 'Fixtures and utility points' : 'Loads and panel'}</span>{results && <><span className="lg fail">Fails</span><span className="lg pass">Passes</span></>}</div>
  </div>;
}

export function ServiceConfirmPanel({record, inputs, setInputs, busy, onRun, onCancel}: {record: ServiceRecord; inputs: ServiceInputs; setInputs: (i: ServiceInputs) => void; busy: string; onRun: () => void; onCancel?: () => void}) {
  const set = <K extends keyof ServiceInputs>(field: K, value: ServiceInputs[K]) => setInputs(changed(inputs, field, value));
  const point = (field: 'water' | 'drain' | 'panel', axis: number, value: number | null) => {const p = [...(inputs[field] || [0, 0])]; p[axis] = value || 0; set(field, p)};
  const updateItem = (n: number, patch: Partial<ServiceItem>) => set('items', inputs.items.map((x, i) => i === n ? {...x, ...patch} : x));
  const plumbing = inputs.discipline === 'plumbing';
  const blockers = [inputs.width == null || inputs.depth == null ? 'Enter the overall dimensions.' : '', !inputs.rooms.length ? 'At least one named room is required.' : '', !inputs.items.length ? `Add at least one ${plumbing ? 'fixture' : 'load point'}.` : '', plumbing && (!inputs.water || !inputs.drain) ? 'Locate the water and drain connections.' : '', plumbing && (inputs.drain_fall_m == null || inputs.drain_slope == null) ? 'Enter the available drain fall and minimum slope.' : '', !plumbing && !inputs.panel ? 'Locate the panel.' : '', !plumbing && (!inputs.circuits.length || inputs.circuits.some(c => c.voltage == null || c.power_factor == null || c.demand_factor == null)) ? 'Every circuit needs voltage, power factor and demand factor.' : ''].filter(Boolean);
  return <div className="confirm-panel">
    <h2>Confirm what was read</h2><p className="quiet">{record.extraction.title || record.source.name}. This is a limited one-sheet screen; the coverage panel will list everything it cannot establish.</p><NoteSummary notes={record.notes}/>
    <h3 className="form-head">Plan outline</h3><div className="field-pair"><NumberInput label="Width" unit="m" value={inputs.width} onChange={v => set('width', v)} hint={<Source inputs={inputs} field="width" value={inputs.width}/>} step={.1}/><NumberInput label="Depth" unit="m" value={inputs.depth} onChange={v => set('depth', v)} hint={<Source inputs={inputs} field="depth" value={inputs.depth}/>} step={.1}/></div>
    <h3 className="form-head">{plumbing ? 'Fixtures' : 'Load points'} <span className="quiet">metres from top-left</span></h3>
    <div className="service-table"><span>Name</span><span>x</span><span>y</span><span>{plumbing ? 'Type' : 'Watts'}</span><span>{plumbing ? 'Room' : 'Circuit'}</span>{inputs.items.map((item, n) => <div className="service-row" key={item.id}><input value={item.name} aria-label="Point name" onChange={e => updateItem(n, {name: e.target.value})}/><input type="number" step={.1} value={item.x} aria-label={`${item.name} x`} onChange={e => updateItem(n, {x: Number(e.target.value)})}/><input type="number" step={.1} value={item.y} aria-label={`${item.name} y`} onChange={e => updateItem(n, {y: Number(e.target.value)})}/>{plumbing ? <select value={item.kind} onChange={e => updateItem(n, {kind: e.target.value as ServiceItem['kind']})}>{['sink','wc','basin'].map(x => <option key={x}>{x}</option>)}</select> : <input type="number" min={0} placeholder="Missing" value={item.watts ?? ''} aria-label={`${item.name} watts`} onChange={e => updateItem(n, {watts: e.target.value === '' ? null : Number(e.target.value)})}/>}<select value={plumbing ? item.room_id : item.circuit_id || ''} onChange={e => updateItem(n, plumbing ? {room_id: e.target.value} : {circuit_id: e.target.value})}>{(plumbing ? inputs.rooms.map(r => [r.id, r.name]) : inputs.circuits.map(c => [c.id, c.id])).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>)}</div>
    {plumbing ? <><h3 className="form-head">Connections and fall</h3>{(['water','drain'] as const).map(f => <div className="field-pair" key={f}><NumberInput label={`${f} x`} unit="m" value={inputs[f]?.[0] ?? null} onChange={v => point(f, 0, v)}/><NumberInput label={`${f} y`} unit="m" value={inputs[f]?.[1] ?? null} onChange={v => point(f, 1, v)}/></div>)}<div className="field-pair"><NumberInput label="Available drain fall" unit="m" value={inputs.drain_fall_m} onChange={v => set('drain_fall_m', v)}/><NumberInput label="Minimum slope" unit="m/m" value={inputs.drain_slope} onChange={v => set('drain_slope', v)} step={.005}/></div></> : <><h3 className="form-head">Panel and circuits</h3><div className="field-pair"><NumberInput label="Panel x" unit="m" value={inputs.panel?.[0] ?? null} onChange={v => point('panel', 0, v)}/><NumberInput label="Panel y" unit="m" value={inputs.panel?.[1] ?? null} onChange={v => point('panel', 1, v)}/></div>{inputs.circuits.map((c, n) => {const put = (patch: Partial<ServiceCircuit>) => set('circuits', inputs.circuits.map((x, i) => i === n ? {...x, ...patch} : x)); return <div className="service-circuit" key={c.id}><strong>{c.id} · {c.name}</strong><div className="field-pair"><NumberInput label="Voltage" unit="V" value={c.voltage} onChange={v => put({voltage: v})} step={1}/><NumberInput label="Power factor" unit="" value={c.power_factor} onChange={v => put({power_factor: v})} step={.05}/></div><NumberInput label="Demand factor" unit="" value={c.demand_factor} onChange={v => put({demand_factor: v})} step={.05}/></div>})}</>}
    <div className="run-bar">{blockers.map(x => <p className="helper tight" key={x}>{x}</p>)}<button className="button primary full" disabled={!!busy || blockers.length > 0} onClick={onRun}>{busy ? <><Loader2 size={14} className="spin"/> {busy}</> : <><Play size={14}/> Run limited {inputs.discipline} check</>}</button>{onCancel && <button className="button secondary full" disabled={!!busy} onClick={onCancel}>Back to findings</button>}<p className="helper tight">{plumbing ? <><Droplets size={12}/> Plan routes and gravity fall only—not pipe sizing or hydraulic design.</> : <><Zap size={12}/> Load arithmetic and plan routes only—not conductor or protection design.</>}</p></div>
  </div>;
}

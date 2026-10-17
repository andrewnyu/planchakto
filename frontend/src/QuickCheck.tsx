import {useEffect, useMemo, useState, type ReactNode} from 'react';
import {AlertTriangle, ArrowLeft, ArrowRight, Box, CheckCircle2, Columns3, Droplets, FileCheck2, Flame, Loader2, MapPin, Pencil, Play, RefreshCw, ScanSearch, Upload, Zap} from 'lucide-react';
import type {Building, Check, Result} from './types';
import {api, num} from './api';
import {Field, Status} from './ui';
import {FIRE_RULES, FIRE_TARGET, FIRE_TARGET_LABEL, FireConfirmPanel, FireSheetView, fireLabel, type FireExtraction, type FireInputs} from './QuickFire';
import {SERVICE_RULES, ServiceConfirmPanel, ServiceSheetView, serviceLabel, type ServiceInputs, type ServiceRecord} from './QuickServices';
import './quickcheck.css';

type Level = 'read' | 'assumed' | 'missing' | 'conflict' | 'unsupported';
export type Note = {level: Level; field?: string | null; message: string; box?: number[] | null};
export type QuickInputs = {
  grid_x: number[]; grid_y: number[]; grid_x_labels: string[]; grid_y_labels: string[]; columns: [number, number][];
  height: number | null; section: string; column_section: string; dead: number | null; live: number | null; soil: number | null;
  footing_width: number; footing_thickness: number; zone: 2 | 4; r_factor: number | null; na: number | null; nv: number | null; friction: number | null;
  assumed: string[]; entered: string[];
};
type Transform = {sx: number; ox: number; sy: number; oy: number; residual: number};
type Callout = {applies_to: string; text: string; box?: number[] | null};
type Load = {kind: string; value: number | null; unit: string; text: string; box?: number[] | null};
type QuickResult = Result & {coverage?: {checked: string[]; not_checked: {item: string; reason: string}[]}};
type RecordBase = {
  id: string; status: 'confirm' | 'checked'; mode: 'live' | 'recorded';
  source: {name: string; mime_type: string; page: number; pages: number; width_px: number; height_px: number};
  transform: Transform | null; notes: Note[]; model: Building | null; results: QuickResult | null;
};
export type StructureRecord = RecordBase & {discipline: 'structure'; extraction: {title: string; sections: Callout[]; loads: Load[]}; inputs: QuickInputs};
export type FireRecord = RecordBase & {discipline: 'fire'; extraction: FireExtraction; inputs: FireInputs};
export type QuickCheckRecord = StructureRecord | FireRecord | ServiceRecord;
type Checkable = 'structure' | 'fire' | 'plumbing' | 'electrical';

const BEAMS = [['RHS150', 'RHS 150 × 100 × 5'], ['RHS200', 'RHS 200 × 100 × 6'], ['RHS250', 'RHS 250 × 150 × 8']];
const COLUMNS = [['SHS150', 'SHS 150 × 150 × 6'], ['SHS200', 'SHS 200 × 200 × 8'], ['SHS250', 'SHS 250 × 250 × 9']];
const RULES: Record<string, string> = {SLS: 'Beam deflection', ELASTIC: 'Beam stress', BEARING: 'Footing bearing', 'SEISMIC-V': 'Seismic base shear', DRIFT: 'Storey drift', COLUMN: 'Column capacity', 'FRAME-MEMBER': 'Frame member flexure', 'FOOT-LATERAL': 'Footing under seismic load', WIND: 'Wind', 'PH-CODE': 'Outside this screen'};
const LABELS: Record<string, string> = {grid_x: 'Grid spacing', grid_y: 'Grid spacing', columns: 'Columns', height: 'Storey height', section: 'Roof beam section', column_section: 'Column section', dead: 'Dead load', live: 'Live load', soil: 'Soil bearing', footing_width: 'Footing size', footing_thickness: 'Footing size', zone: 'Seismic zone', r_factor: 'R', na: 'Na', nv: 'Nv', friction: 'Base friction'};
export const ORDER = ['fail', 'missing_input', 'unsupported', 'pass', 'not_applicable'];
const READY: {id: Checkable; label: string; icon: typeof Flame}[] = [{id: 'structure', label: 'Structure', icon: Columns3}, {id: 'fire', label: 'Fire protection', icon: Flame}, {id: 'plumbing', label: 'Plumbing', icon: Droplets}, {id: 'electrical', label: 'Electrical', icon: Zap}];
const COPY: Record<Checkable, {eyebrow: string; body: string; file: string; page: string; sample: string; check: string}> = {
  structure: {eyebrow: 'QUICK CHECK · STRUCTURE', body: 'Upload a roof framing plan. Gemini reads the grid, columns, member sizes and loads off the sheet. You confirm what it read, then the structural screen runs on exactly that, and every finding is pinned to the drawing.',
    file: 'Choose a framing plan', page: 'PDF page with the framing plan', sample: 'Try the sample framing plan', check: 'structural'},
  fire: {eyebrow: 'QUICK CHECK · FIRE PROTECTION', body: 'Upload a single-storey floor plan. Gemini reads the outline, rooms, doors, exits and extinguishers off the sheet. You choose the occupancy and confirm the plan, then the RA 9514 egress screen runs on exactly that, with the worst travel path drawn on the sheet.',
    file: 'Choose a floor plan', page: 'PDF page with the floor plan', sample: 'Try the sample floor plan', check: 'fire and egress'},
  plumbing: {eyebrow: 'QUICK CHECK · PLUMBING', body: 'Upload one plumbing plan. Gemini reads named rooms, fixtures and the water and drain connection points. You confirm the points and drain fall, then BuildGraph screens plan connectivity and gravity fall—not pipe sizing or hydraulic design.',
    file: 'Choose a plumbing plan', page: 'PDF page with the plumbing plan', sample: 'Try the sample plumbing plan', check: 'limited plumbing'},
  electrical: {eyebrow: 'QUICK CHECK · ELECTRICAL', body: 'Upload one electrical plan. Gemini reads named rooms, load points, circuit marks and the panel. You confirm the ratings, then BuildGraph screens plan connectivity and load arithmetic—not conductor sizing, protection or voltage drop.',
    file: 'Choose an electrical plan', page: 'PDF page with the electrical plan', sample: 'Try the sample electrical plan', check: 'limited electrical'},
};

export function QuickCheck({initialId, initialDiscipline = 'structure', connected, visionModel, onHome, onWorkspace}: {
  initialId?: string; initialDiscipline?: Checkable; connected: boolean; visionModel?: string | null;
  onHome: () => void; onWorkspace: () => void;
}) {
  const [record, setRecord] = useState<QuickCheckRecord | null>(null);
  const [inputs, setInputs] = useState<QuickInputs | FireInputs | ServiceInputs | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(''), [error, setError] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const open = (next: QuickCheckRecord | null) => {
    setRecord(next); setInputs(next?.inputs ?? null); setEditing(false); setSelected([]);
    document.querySelector('.quick-page')?.scrollTo({top: 0});
    try {history.replaceState(null, '', next ? `#quick-check/${next.id}` : '#quick-check')} catch {}
  };
  const act = async (label: string, fn: () => Promise<void>) => {
    if (busy) return; setBusy(label); setError('');
    try {await fn()} catch (e) {setError(e instanceof Error ? e.message : 'Something went wrong. Try again.')} finally {setBusy('')}
  };
  useEffect(() => {
    if (initialId) act('Opening check', async () => open(await api<QuickCheckRecord>(`/quick-checks/${initialId}`)));
    else try {history.replaceState(null, '', '#quick-check')} catch {}
  }, [initialId]);
  const step = !record ? 'upload' : record.status === 'checked' && !editing ? 'results' : 'confirm';
  const run = () => act(`Running the ${COPY[record!.discipline].check} check`, async () => {open(await api<QuickCheckRecord>(`/quick-checks/${record!.id}/run`, inputs))});
  const shown = step === 'confirm' ? inputs! : record?.inputs;

  return <div className="quick-page">
    <header className="splash-bar quick-bar">
      <div className="splash-brand"><button className="brand-mark" onClick={onHome} aria-label="Home"><Box size={20} strokeWidth={1.65}/></button><strong>Quick check</strong><span className="splash-tag">Separate from your projects</span></div>
      <div className="quick-bar-actions"><button className="button secondary" onClick={onHome}><ArrowLeft size={14}/> Home</button><button className="button primary" onClick={onWorkspace}>Open planning workspace <ArrowRight size={14}/></button></div>
    </header>
    <ol className="quick-steps" aria-label="Quick check steps">
      {[['upload', 'Upload a sheet'], ['confirm', 'Confirm what was read'], ['results', 'Findings on the drawing']].map(([id, label], i) =>
        <li key={id} className={step === id ? 'active' : ['upload', 'confirm', 'results'].indexOf(step) > i ? 'done' : ''}><i>{i + 1}</i>{label}</li>)}
    </ol>
    {error && <p className="inline-error quick-error" role="alert">{error}</p>}
    {step === 'upload' ? <UploadStep initial={initialDiscipline} connected={connected} visionModel={visionModel} busy={busy} onRead={(label, fn) => act(label, async () => open(await fn()))}/> :
      <div className="quick-layout">
        <section className="quick-sheet" aria-label="Uploaded drawing">
          {record!.discipline === 'fire' ? <FireSheetView record={record!} inputs={shown as FireInputs} results={step === 'results' ? record!.results : null} selected={selected} onSelect={id => setSelected([id])}/> :
            record!.discipline === 'plumbing' || record!.discipline === 'electrical' ? <ServiceSheetView record={record as ServiceRecord} inputs={shown as ServiceInputs} results={step === 'results' ? record!.results : null} selected={selected} onSelect={id => setSelected([id])}/> :
            <SheetView record={record as StructureRecord} inputs={shown as QuickInputs} results={step === 'results' ? record!.results : null} selected={selected}
              onSelect={id => setSelected([id])}
              onToggleColumn={step === 'confirm' ? (i, j) => {const s = inputs as QuickInputs; setInputs(edit(s, 'columns', s.columns.some(c => c[0] === i && c[1] === j) ? s.columns.filter(c => !(c[0] === i && c[1] === j)) : [...s.columns, [i, j]]))} : undefined}/>}
        </section>
        <aside className="quick-panel">
          {record!.mode === 'recorded' && <p className="quick-recorded"><FileCheck2 size={14}/> Recorded reading of the sample sheet. No AI call was made{connected ? '' : '; connect Gemini to read your own drawings'}.</p>}
          {step === 'confirm' ? (record!.discipline === 'fire' ?
            <FireConfirmPanel record={record!} inputs={inputs as FireInputs} setInputs={setInputs} busy={busy} onRun={run} selected={selected} onSelect={id => setSelected([id])} onCancel={record!.status === 'checked' ? () => {setEditing(false); setInputs(record!.inputs)} : undefined}/> :
            record!.discipline === 'plumbing' || record!.discipline === 'electrical' ? <ServiceConfirmPanel record={record as ServiceRecord} inputs={inputs as ServiceInputs} setInputs={setInputs} busy={busy} onRun={run} onCancel={record!.status === 'checked' ? () => {setEditing(false); setInputs(record!.inputs)} : undefined}/> :
            <ConfirmPanel record={record as StructureRecord} inputs={inputs as QuickInputs} setInputs={setInputs} busy={busy} onRun={run} onCancel={record!.status === 'checked' ? () => {setEditing(false); setInputs(record!.inputs)} : undefined}/>) :
            <ResultsPanel record={record!} selected={selected} onSelect={setSelected} onEdit={() => setEditing(true)} onNew={() => open(null)}/>}
        </aside>
      </div>}
  </div>;
}

function edit<K extends keyof QuickInputs>(inputs: QuickInputs, field: K, value: QuickInputs[K]): QuickInputs {
  const key = String(field).startsWith('footing') ? ['footing_width', 'footing_thickness'] : [String(field)];
  return {...inputs, [field]: value, assumed: inputs.assumed.filter(f => !key.includes(f)), entered: Array.from(new Set([...inputs.entered, ...key]))};
}

function UploadStep({initial, connected, visionModel, busy, onRead}: {
  initial: Checkable; connected: boolean; visionModel?: string | null; busy: string;
  onRead: (label: string, fn: () => Promise<QuickCheckRecord>) => void;
}) {
  const [file, setFile] = useState<File | null>(null), [page, setPage] = useState(1), [error, setError] = useState('');
  const [discipline, setDiscipline] = useState<Checkable>(initial), copy = COPY[discipline];
  const pdf = file?.type === 'application/pdf' || file?.name.toLowerCase().endsWith('.pdf');
  const reader = visionModel || 'Gemini';
  const read = () => {
    if (!file) return;
    const mime = file.type || ({png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', pdf: 'application/pdf'} as Record<string, string>)[file.name.split('.').pop()?.toLowerCase() || ''];
    if (!['image/png', 'image/jpeg', 'image/webp', 'application/pdf'].includes(mime)) {setError('Choose a PDF, PNG, JPEG or WebP sheet. CAD files are not supported.'); return}
    if (file.size > 8 * 1024 * 1024) {setError('This file is larger than 8 MB. Export the single sheet you want checked.'); return}
    setError('');
    onRead(`Reading ${file.name} with ${reader}. This usually takes 10–30 seconds.`, async () => {
      const data = await new Promise<string>((resolve, reject) => {const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = () => reject(new Error('This file could not be read. Choose it again.')); r.readAsDataURL(file)});
      return api<QuickCheckRecord>('/quick-checks', {discipline, page: pdf ? page - 1 : 0, attachment: {name: file.name, mime_type: mime, data: data.slice(data.indexOf(',') + 1)}});
    });
  };
  const sample = () => onRead(connected ? `Reading the sample sheet with ${reader}…` : 'Opening the sample sheet…', () => api<QuickCheckRecord>('/quick-checks/sample', {discipline, live: connected}));
  return <div className="quick-upload">
    <div className="quick-upload-copy">
      <span className="eyebrow">{copy.eyebrow}</span>
      <h1>Check one drawing on its own.</h1>
      <p>{copy.body}</p>
      <ul className="quick-promises">
        <li><CheckCircle2 size={15}/> Your projects and the demo are never changed.</li>
        <li><CheckCircle2 size={15}/> Values not on the sheet stay missing. Nothing is borrowed from another project.</li>
        <li><CheckCircle2 size={15}/> Checks that need other drawings are listed as not checked, never passed.</li>
      </ul>
    </div>
    <div className="quick-upload-card">
      <div className="quick-disciplines" role="radiogroup" aria-label="System to check">
        {READY.map(d => <button key={d.id} role="radio" aria-checked={discipline === d.id} className={discipline === d.id ? 'active' : ''} disabled={!!busy} onClick={() => setDiscipline(d.id)}><d.icon size={15}/> {d.label}</button>)}
      </div>
      <label className="file-drop"><Upload size={25}/><strong>{file?.name || copy.file}</strong><span>PDF, PNG, JPEG or WebP · one sheet · up to 8 MB</span>
        <input aria-label="Drawing file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" disabled={!!busy} onChange={e => {setFile(e.target.files?.[0] || null); setError(''); setPage(1)}}/></label>
      {pdf && <Field label={copy.page}><input type="number" min={1} max={500} value={page} onChange={e => setPage(Math.max(1, Number(e.target.value) || 1))}/></Field>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {!connected && <p className="helper">No AI provider is connected on this server, so your own drawings cannot be read. The sample sheet works with a recorded reading.</p>}
      <button className="button primary full" disabled={!!busy || !file || !connected} onClick={read}>{busy ? <><Loader2 size={14} className="spin"/> {busy}</> : <><ScanSearch size={15}/> Read drawing with {reader}</>}</button>
      <button className="button secondary full" disabled={!!busy} onClick={sample}><Play size={14}/> {copy.sample}</button>
      {(discipline === 'plumbing' || discipline === 'electrical') && <p className="helper">This demo screens only what one plan can establish. Results name the omitted design and coordination checks instead of passing them.</p>}
    </div>
  </div>;
}

/** The sheet with what was read (confirm step) or the findings (results step) drawn in the image's own pixel space. */
function SheetView({record, inputs, results, selected, onSelect, onToggleColumn}: {
  record: StructureRecord; inputs: QuickInputs; results: QuickCheckRecord['results']; selected: string[];
  onSelect: (id: string) => void; onToggleColumn?: (i: number, j: number) => void;
}) {
  const t = record.transform;
  const [mode, setMode] = useState<'sheet' | 'grid' | 'model'>(t ? (results ? 'grid' : 'sheet') : 'model');
  useEffect(() => {if (t && results) setMode('grid')}, [!!results]);
  const W = record.source.width_px, H = record.source.height_px;
  const gx = inputs.grid_x, gy = inputs.grid_y, w = gx[gx.length - 1], d = gy[gy.length - 1];
  const onSheet = mode !== 'model' && !!t;
  const k = 60, pad = 2.2;
  const P = (x: number, y: number): [number, number] => onSheet ? [(t!.sx * x + t!.ox) / 1000 * W, (t!.sy * y + t!.oy) / 1000 * H] : [(x + pad) * k, (y + pad) * k];
  const u = onSheet ? Math.max(W, H) / 1000 : k / 45;
  const view = useMemo(() => {
    if (!onSheet) return `0 0 ${(w + 2 * pad) * k} ${(d + 2 * pad) * k}`;
    if (mode === 'sheet') return `0 0 ${W} ${H}`;
    const [x0, y0] = P(-pad, -pad), [x1, y1] = P(w + pad, d + pad);
    const left = Math.max(0, Math.min(x0, x1)), top = Math.max(0, Math.min(y0, y1));
    return `${left} ${top} ${Math.min(W, Math.max(x0, x1)) - left} ${Math.min(H, Math.max(y0, y1)) - top}`;
  }, [mode, onSheet, w, d, W, H, t]);
  const box = (b: number[]) => ({x: b[1] / 1000 * W, y: b[0] / 1000 * H, width: (b[3] - b[1]) / 1000 * W, height: (b[2] - b[0]) / 1000 * H});
  const st = results?.structure;
  const statusOf = (id: string) => results?.checks.filter(c => c.objects.includes(id)).map(c => c.status).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))[0] || 'pass';
  const has = (i: number, j: number) => inputs.columns.some(c => c[0] === i && c[1] === j);
  const assumedGrid = inputs.assumed.includes('grid_x') || inputs.assumed.includes('grid_y');
  return <div className="sheet-view">
    <div className="sheet-toolbar">
      <span className="quiet">{record.source.name}{record.source.pages > 1 ? ` · page ${record.source.page + 1} of ${record.source.pages}` : ''}</span>
      <div className="segmented" role="group" aria-label="View">
        {t && <button aria-pressed={mode === 'sheet'} onClick={() => setMode('sheet')}>Whole sheet</button>}
        {t && <button aria-pressed={mode === 'grid'} onClick={() => setMode('grid')}>Zoom to grid</button>}
        <button aria-pressed={mode === 'model'} onClick={() => setMode('model')}>Model</button>
      </div>
    </div>
    {!t && <p className="sheet-warning"><AlertTriangle size={13}/> The grid could not be located on the page, so findings are shown on the model view.</p>}
    <svg className={'sheet-svg' + (onSheet ? ' on-sheet' : '')} viewBox={view} role="img" aria-label={results ? 'Findings drawn on the sheet' : 'What was read from the sheet'}>
      {onSheet && <image href={`/api/quick-checks/${record.id}/image`} x={0} y={0} width={W} height={H}/>}
      {onSheet && <rect x={0} y={0} width={W} height={H} className="sheet-wash"/>}
      {gx.map((x, i) => {const [ax, ay] = P(x, -pad * .7), [, by] = P(x, d + pad * .7); return <g key={'gx' + i} className={'grid-line' + (assumedGrid ? ' assumed' : '')}><line x1={ax} y1={ay} x2={ax} y2={by} strokeWidth={u * 1.3}/>{!onSheet && <text x={ax} y={ay - u * 4} fontSize={u * 13}>{inputs.grid_x_labels[i]}</text>}</g>})}
      {gy.map((y, j) => {const [ax, ay] = P(-pad * .7, y), [bx] = P(w + pad * .7, y); return <g key={'gy' + j} className={'grid-line' + (assumedGrid ? ' assumed' : '')}><line x1={ax} y1={ay} x2={bx} y2={ay} strokeWidth={u * 1.3}/>{!onSheet && <text x={ax - u * 8} y={ay + u * 4} fontSize={u * 13}>{inputs.grid_y_labels[j]}</text>}</g>})}
      {!results && onSheet && mode === 'sheet' && <>
        {record.extraction.sections.filter(s => s.box).map((s, i) => <g key={'s' + i} className="read-box"><rect {...box(s.box!)} strokeWidth={u * 1.2}/><title>{`Read: ${s.text}`}</title></g>)}
        {record.extraction.loads.filter(l => l.box).map((l, i) => <g key={'l' + i} className="read-box"><rect {...box(l.box!)} strokeWidth={u * 1.2}/><title>{`Read: ${l.text}`}</title></g>)}
        {record.notes.filter(n => n.box && ['conflict', 'unsupported'].includes(n.level)).map((n, i) => <g key={'n' + i} className="flag-box"><rect {...box(n.box!)} strokeWidth={u * 1.6}/><title>{n.message}</title></g>)}
      </>}
      {results && st && <>
        {(st.girders || []).map(g => {const [x1, y1] = P(g.x, g.y1), [, y2] = P(g.x, g.y2); return <line key={g.id} className="girder" x1={x1} y1={y1} x2={x1} y2={y2} strokeWidth={u * 1.6} strokeDasharray={`${u * 6} ${u * 4}`}/>})}
        {st.beams.map(b => {const [x1, y] = P(b.x1, b.y), [x2] = P(b.x2, b.y), s = statusOf(b.id), on = selected.includes(b.id), util = Math.max(b.yield_utilization, b.deflection_utilization);
          return <g key={b.id} className={'finding beam ' + s + (on ? ' selected' : '')} onClick={() => onSelect(b.id)} role="button" tabIndex={0} aria-label={`Beam ${b.x1}–${b.x2} m on y ${b.y} m: ${s}`} onKeyDown={e => {if (e.key === 'Enter') onSelect(b.id)}}>
            {on && <line className="halo" x1={x1} y1={y} x2={x2} y2={y} strokeWidth={u * 16} strokeLinecap="round"/>}
            <line x1={x1} y1={y} x2={x2} y2={y} strokeWidth={u * (s === 'fail' ? 5 : 3.2)}/><line className="hit" x1={x1} y1={y} x2={x2} y2={y} strokeWidth={u * 14}/>
            <text x={(x1 + x2) / 2} y={y + u * 15} fontSize={u * 11}>{Math.round(util * 100)}%</text></g>})}
        {st.foundations.map(f => {const c = record.model!.columns.find(c => c.id === f.column_id)!; const [x, y] = P(c.x, c.y), s = statusOf(f.id), on = selected.includes(f.id) || selected.includes(c.id);
          return <g key={f.id} className={'finding footing ' + s + (on ? ' selected' : '')} onClick={() => onSelect(f.id)} role="button" tabIndex={0} aria-label={`Footing at ${c.x}, ${c.y} m: ${s}`} onKeyDown={e => {if (e.key === 'Enter') onSelect(f.id)}}>
            {on && <circle className="halo" cx={x} cy={y} r={u * 15}/>}<circle cx={x} cy={y} r={u * 7} strokeWidth={u * 1.6}/></g>})}
      </>}
      {gy.map((y, j) => gx.map((x, i) => {const [cx, cy] = P(x, y), on = has(i, j);
        if (results) return on ? <rect key={`c${i}-${j}`} className="column-mark" x={cx - u * 3} y={cy - u * 3} width={u * 6} height={u * 6}/> : null;
        return <g key={`c${i}-${j}`} className={'column-toggle' + (on ? ' on' : '') + (inputs.assumed.includes('columns') ? ' assumed' : '')} role="checkbox" aria-checked={on} tabIndex={0}
          aria-label={`Column at ${inputs.grid_x_labels[i]}-${inputs.grid_y_labels[j]}`} onClick={() => onToggleColumn?.(i, j)} onKeyDown={e => {if (e.key === ' ' || e.key === 'Enter') {e.preventDefault(); onToggleColumn?.(i, j)}}}>
          <circle className="hit" cx={cx} cy={cy} r={u * 11}/>{on ? <rect x={cx - u * 5} y={cy - u * 5} width={u * 10} height={u * 10} strokeWidth={u * 1.5}/> : <circle cx={cx} cy={cy} r={u * 4} strokeWidth={u * 1.2}/>}</g>}))}
    </svg>
    <div className="sheet-legend">{results ? <><span className="lg fail">Fails</span><span className="lg missing_input">Missing input</span><span className="lg pass">Passes</span><span className="quiet">Select a beam or footing to see its finding.</span></> :
      <><span className="lg read">Read from the sheet</span><span className="lg assumed">Assumed</span>{onToggleColumn && <span className="quiet">Select a grid intersection to add or remove a column.</span>}</>}</div>
  </div>;
}

export function Source({inputs, field, value}: {inputs: {assumed: string[]; entered: string[]}; field: string; value?: unknown}) {
  const state = inputs.entered.includes(field) ? 'entered' : inputs.assumed.includes(field) ? 'assumed' : value === null ? 'missing' : 'read';
  return <span className={'source-chip ' + state}>{{entered: 'Entered', assumed: 'Assumed', missing: 'Missing', read: 'From sheet'}[state]}</span>;
}

export function NumberInput({label, unit, value, onChange, hint, step = 0.01}: {label: string; unit: string; value: number | null; onChange: (v: number | null) => void; hint?: ReactNode; step?: number}) {
  const [text, setText] = useState(value == null ? '' : String(value));
  useEffect(() => {if ((text === '' ? null : Number(text)) !== value) setText(value == null ? '' : String(value))}, [value]);
  return <label className="field quick-field"><span>{label} {hint}</span><div className="unit-input"><input type="number" step={step} min={0} value={text} placeholder="Not on the sheet"
    onChange={e => {setText(e.target.value); const v = e.target.value === '' ? null : Number(e.target.value); if (v === null || Number.isFinite(v)) onChange(v)}}/><em>{unit}</em></div></label>;
}

/** Counts of what was read, assumed and missing, the notes that need attention, and the rest behind a disclosure. */
export function NoteSummary({notes}: {notes: Note[]}) {
  const count = (level: Level) => notes.filter(n => n.level === level).length;
  const problems = notes.filter(n => ['unsupported', 'conflict', 'missing'].includes(n.level));
  return <>
    <div className="read-summary">
      <span className="source-chip read">{count('read')} read</span><span className="source-chip assumed">{count('assumed')} assumed</span><span className="source-chip missing">{count('missing')} missing</span>
      {count('conflict') + count('unsupported') > 0 && <span className="source-chip conflict">{count('conflict') + count('unsupported')} to resolve</span>}
    </div>
    {problems.length > 0 && <ul className="note-list">{problems.map((n, i) => <li key={i} className={n.level}><AlertTriangle size={13}/><span>{n.message}</span></li>)}</ul>}
    <details className="note-details"><summary>Assumptions and values read ({count('read') + count('assumed')})</summary>
      <ul className="note-list">{notes.filter(n => ['read', 'assumed'].includes(n.level)).map((n, i) => <li key={i} className={n.level}>{n.level === 'read' ? <CheckCircle2 size={13}/> : <Pencil size={13}/>}<span>{n.message}</span></li>)}</ul></details>
  </>;
}

function ConfirmPanel({record, inputs, setInputs, busy, onRun, onCancel}: {
  record: StructureRecord; inputs: QuickInputs; setInputs: (i: QuickInputs) => void; busy: string; onRun: () => void; onCancel?: () => void;
}) {
  const set = <K extends keyof QuickInputs>(f: K, v: QuickInputs[K]) => setInputs(edit(inputs, f, v));
  const spacing = (axis: 'grid_x' | 'grid_y', k: number, v: number | null) => {
    const g = inputs[axis]; const bays = g.slice(1).map((p, i) => p - g[i]); bays[k] = v ?? 0;
    set(axis, bays.reduce((acc, b) => [...acc, Math.round((acc[acc.length - 1] + b) * 1000) / 1000], [0]));
  };
  const badGrid = [inputs.grid_x, inputs.grid_y].some(g => g.slice(1).some((p, i) => p <= g[i]));
  return <div className="confirm-panel">
    <h2>Confirm what was read</h2>
    <p className="quiet">{record.extraction.title || record.source.name}. Correct anything that is wrong. Nothing is calculated until you run the check.</p>
    <NoteSummary notes={record.notes}/>

    <h3 className="form-head">Grid <Source inputs={inputs} field="grid_x"/></h3>
    <div className="bay-row"><span>{inputs.grid_x_labels[0]}–{inputs.grid_x_labels[inputs.grid_x_labels.length - 1]}</span>{inputs.grid_x.slice(1).map((p, k) => <input key={k} aria-label={`Bay ${inputs.grid_x_labels[k]}–${inputs.grid_x_labels[k + 1]} (m)`} type="number" step={0.05} min={0.5} value={Math.round((p - inputs.grid_x[k]) * 1000) / 1000} onChange={e => spacing('grid_x', k, Number(e.target.value))}/>)}<em>m</em></div>
    <div className="bay-row"><span>{inputs.grid_y_labels[0]}–{inputs.grid_y_labels[inputs.grid_y_labels.length - 1]}</span>{inputs.grid_y.slice(1).map((p, k) => <input key={k} aria-label={`Bay ${inputs.grid_y_labels[k]}–${inputs.grid_y_labels[k + 1]} (m)`} type="number" step={0.05} min={0.5} value={Math.round((p - inputs.grid_y[k]) * 1000) / 1000} onChange={e => spacing('grid_y', k, Number(e.target.value))}/>)}<em>m</em></div>
    <p className="helper tight">{num(inputs.grid_x[inputs.grid_x.length - 1])} × {num(inputs.grid_y[inputs.grid_y.length - 1])} m · {inputs.columns.length} of {inputs.grid_x.length * inputs.grid_y.length} intersections have a column <Source inputs={inputs} field="columns"/></p>

    <h3 className="form-head">Frame</h3>
    <NumberInput label="Storey height" unit="m" value={inputs.height} onChange={v => set('height', v)} hint={<Source inputs={inputs} field="height" value={inputs.height}/>} step={0.1}/>
    <Field label="Roof beam section"><select value={inputs.section} onChange={e => set('section', e.target.value)}>{BEAMS.map(([id, l]) => <option key={id} value={id}>{l}</option>)}</select></Field>
    <div className="field-source"><Source inputs={inputs} field="section"/></div>
    <Field label="Column section"><select value={inputs.column_section} onChange={e => set('column_section', e.target.value)}>{COLUMNS.map(([id, l]) => <option key={id} value={id}>{l}</option>)}</select></Field>
    <div className="field-source"><Source inputs={inputs} field="column_section"/></div>

    <h3 className="form-head">Loads and soil</h3>
    <div className="field-pair">
      <NumberInput label="Roof dead" unit="kPa" value={inputs.dead} onChange={v => set('dead', v)} hint={<Source inputs={inputs} field="dead" value={inputs.dead}/>}/>
      <NumberInput label="Roof live" unit="kPa" value={inputs.live} onChange={v => set('live', v)} hint={<Source inputs={inputs} field="live" value={inputs.live}/>}/>
    </div>
    <NumberInput label="Allowable soil bearing" unit="kPa" value={inputs.soil} onChange={v => set('soil', v)} hint={<Source inputs={inputs} field="soil" value={inputs.soil}/>} step={1}/>
    <div className="field-pair">
      <NumberInput label="Footing width" unit="m" value={inputs.footing_width} onChange={v => set('footing_width', v ?? 1.2)} hint={<Source inputs={inputs} field="footing_width"/>}/>
      <NumberInput label="Thickness" unit="m" value={inputs.footing_thickness} onChange={v => set('footing_thickness', v ?? .3)}/>
    </div>

    <h3 className="form-head">Seismic <span className="quiet">optional · rarely on a framing plan</span></h3>
    <Field label="Seismic zone"><select value={inputs.zone} onChange={e => set('zone', Number(e.target.value) as 2 | 4)}><option value={4}>Zone 4 (most of the Philippines)</option><option value={2}>Zone 2 (Palawan, Sulu, Tawi-Tawi)</option></select></Field>
    <div className="field-source"><Source inputs={inputs} field="zone"/></div>
    <div className="field-pair">
      <NumberInput label="R" unit="" value={inputs.r_factor} onChange={v => set('r_factor', v)} step={0.1}/>
      <NumberInput label="Base friction μ" unit="" value={inputs.friction} onChange={v => set('friction', v)}/>
    </div>
    <div className="field-pair">
      <NumberInput label="Na" unit="" value={inputs.na} onChange={v => set('na', v)} step={0.1}/>
      <NumberInput label="Nv" unit="" value={inputs.nv} onChange={v => set('nv', v)} step={0.1}/>
    </div>

    <div className="run-bar">
      {inputs.height == null && <p className="helper tight">Enter the storey height to run the check.</p>}
      {badGrid && <p className="helper tight">Every grid bay must be longer than zero.</p>}
      <button className="button primary full" disabled={!!busy || inputs.height == null || badGrid} onClick={onRun}>{busy ? <><Loader2 size={14} className="spin"/> {busy}</> : <><Play size={14}/> Run structural check</>}</button>
      {onCancel && <button className="button secondary full" disabled={!!busy} onClick={onCancel}>Back to findings</button>}
      <p className="helper tight">Missing values are reported as missing input, never filled in.</p>
    </div>
  </div>;
}

function locatable(check: Check, r: Result) {
  return check.objects.find(id => id.startsWith('beam-') || id.startsWith('foundation-') || r.structure.foundations.some(f => f.column_id === id));
}
function fireTarget(check: Check, r: Result) {
  const id = FIRE_TARGET[check.rule_id];
  if (id === 'travel' && r.fire?.enabled && !r.fire.travel.critical_path.length) return undefined;
  if (id === 'reach' && r.fire?.enabled && !r.fire.extinguishers.critical_path.length) return undefined;
  return id;
}

function ResultsPanel({record, selected, onSelect, onEdit, onNew}: {record: QuickCheckRecord; selected: string[]; onSelect: (ids: string[]) => void; onEdit: () => void; onNew: () => void}) {
  const r = record.results!;
  const groups = useMemo(() => {
    const map = new Map<string, Check[]>();
    for (const c of r.checks) {const k = c.status + '|' + c.rule_id; map.set(k, [...(map.get(k) || []), c])}
    return [...map.entries()].sort(([a], [b]) => ORDER.indexOf(a.split('|')[0]) - ORDER.indexOf(b.split('|')[0]));
  }, [r]);
  const fire = record.discipline === 'fire';
  const service = record.discipline === 'plumbing' || record.discipline === 'electrical';
  const target = (c: Check) => {if (fire) return fireTarget(c, r); if (service) return c.objects.find(id => id.startsWith('water-') || id.startsWith('drain-') || id.startsWith('conduit-')); const id = locatable(c, r); if (!id) return undefined; const f = r.structure.foundations.find(f => f.column_id === id); return f ? f.id : id};
  const assumed = Array.from(new Set(record.inputs.assumed.map(f => fire ? fireLabel(f) : LABELS[f] || f)));
  const rules = fire ? FIRE_RULES : service ? SERVICE_RULES : RULES;
  const title = fire ? 'Fire and egress findings' : service ? `${record.discipline === 'plumbing' ? 'Plumbing' : 'Electrical'} plan findings` : 'Structural findings';
  // A selection made on the drawing brings its finding into view in the panel.
  useEffect(() => {document.querySelector('.finding-targets .target.on')?.scrollIntoView({block: 'nearest', behavior: 'smooth'})}, [selected.join()]);
  return <div className="results-panel">
    <div className="results-head"><h2>{title}</h2><span className="mono quiet">{record.id}</span></div>
    <div className="result-counts">
      <span className={'count fail' + (r.summary.fail ? '' : ' zero')}><strong>{r.summary.fail}</strong> fail</span><span className="count missing_input"><strong>{r.summary.missing_input}</strong> missing input</span>
      <span className="count pass"><strong>{r.summary.pass}</strong> pass</span><span className="count unsupported"><strong>{r.summary.unsupported}</strong> not evaluated</span>
    </div>
    {assumed.length > 0 && <p className="quick-assumed"><Pencil size={13}/> Uses assumed values for {assumed.join(', ').toLowerCase()}. <button className="text-button inline" onClick={onEdit}>Confirm them</button></p>}
    {groups.map(([key, checks]) => {const [status, rule] = key.split('|'); const first = checks[0];
      return <article key={key} className={'finding-group ' + status}>
        <div className="review-finding-top"><Status status={status}/><strong>{rules[rule] || rule}</strong>{checks.length > 1 && <span className="quiet">× {checks.length}</span>}<span className="mono quiet">{rule}</span></div>
        <p>{first.evidence}</p>
        <div className="finding-targets">
          {checks.map(c => {const id = target(c); return id ? <button key={c.id} className={'target' + (selected.includes(id) ? ' on' : '')} onClick={() => onSelect([id])}><MapPin size={11}/>{label(id, record)}</button> : null})}
        </div>
        <details><summary>Calculation inputs</summary>{checks.slice(0, 6).map(c => <pre key={c.id}>{c.evidence}{'\n'}{JSON.stringify(c.inputs, null, 1)}</pre>)}{checks.length > 6 && <small className="quiet">and {checks.length - 6} more like these</small>}</details>
      </article>})}
    {r.coverage && <div className="coverage">
      {fire && r.fire?.enabled && <p className="helper tight">{r.fire.gross_area_m2.toFixed(1)} m² gross · {r.fire.occupant_load} occupants · {r.fire.exits.length} exit{r.fire.exits.length === 1 ? '' : 's'}</p>}
      <h3>Checked from this sheet</h3><ul>{r.coverage.checked.map(c => <li key={c}><CheckCircle2 size={13}/>{c}</li>)}</ul>
      <h3>Not checked</h3><ul>{r.coverage.not_checked.map(c => <li key={c.item}><span><strong>{c.item}.</strong> {c.reason}</span></li>)}</ul>
    </div>}
    <div className="run-bar">
      <button className="button secondary full" onClick={() => {onEdit(); document.querySelector('.quick-page')?.scrollTo({top: 0})}}><Pencil size={14}/> Edit inputs and re-run</button>
      <button className="button secondary full" onClick={onNew}><RefreshCw size={14}/> Check another sheet</button>
      <p className="helper tight">{fire ? 'Preliminary screening only. Fire safety plans need the BFP\'s evaluation (FSEC) and review by the responsible licensed professional before permit submission.' : service ? `Preliminary one-sheet screening only. A licensed ${record.discipline === 'plumbing' ? 'Sanitary Engineer or Master Plumber' : 'Professional Electrical Engineer'} must complete and review the design.` : 'Preliminary screening only. A licensed civil or structural engineer must review the design before construction or permit submission.'}</p>
    </div>
  </div>;
}

function label(id: string, record: QuickCheckRecord) {
  if (record.discipline === 'fire') return FIRE_TARGET_LABEL[id] || id;
  if (record.discipline === 'plumbing' || record.discipline === 'electrical') return serviceLabel(id, record);
  const structural = record as StructureRecord, i = structural.inputs, m = structural.model!, r = structural.results!;
  const gl = (x: number, axis: 'x' | 'y') => {const g = axis === 'x' ? i.grid_x : i.grid_y, l = axis === 'x' ? i.grid_x_labels : i.grid_y_labels; const k = g.findIndex(v => Math.abs(v - x) < 1e-6); return k >= 0 ? l[k] : `${x} m`};
  const beam = r.structure.beams.find(b => b.id === id);
  if (beam) return `${gl(beam.x1, 'x')}–${gl(beam.x2, 'x')} / ${gl(beam.y, 'y')}`;
  const f = r.structure.foundations.find(f => f.id === id), c = m.columns.find(c => c.id === (f?.column_id || id));
  return c ? `${gl(c.x, 'x')}-${gl(c.y, 'y')}` : id;
}

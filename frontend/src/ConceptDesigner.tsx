import {useEffect, useRef, useState} from 'react';
import {ArrowLeft, Check, Download, FileUp, Loader2, Plus, Redo2, Send, Sparkles, Undo2, X} from 'lucide-react';
import {api, num} from './api';
import './ConceptDesigner.css';

type XY = [number, number];
type Site = {boundary: XY[]; source: string; basis: string; reported_area_m2: number | null; road_edge: [number, number] | null; north_degrees: number | null; setback_m: number | null};
type Zone = {id: string; name: string; kind: string; polygon: XY[]; location: 'inside' | 'outside'; enclosed: boolean; purpose: string};
type Plan = {title: string; rationale: string; footprint: XY[]; zones: Zone[]; openings: {id: string; from_zone: string; to_zone: string; segment: [XY, XY]; kind: string}[]; assumptions: string[]; tradeoffs: string[]};
type Candidate = {id: string; plan: Plan; site: Site | null; status: string; input_hash: string; metrics: {footprint_area_m2: number; site_area_m2: number | null; zones: {id: string; name: string; area_m2: number; label: XY}[]; coverage: {checked: string[]; not_checked: string[]}; missing: string[]}};
type Session = {id: string; template: string; site: Site | null; candidates: Candidate[]; accepted_id: string | null; can_undo: boolean; can_redo: boolean; messages: {role: string; text: string; questions?: string[]}[]};
type Reading = {site: Site | null; notes: string[]; missing: string[]};

function download(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
}

export {PlanningWorkspace as ConceptDesigner} from './PlanningWorkspace';
export function LegacyConceptDesigner({template, initialBrief, aiProvider, onExit}: {template: string; initialBrief: string; aiProvider: string | null; onExit: () => void}) {
  const [session, setSession] = useState<Session | null>(null);
  const [draft, setDraft] = useState(initialBrief);
  const [selected, setSelected] = useState('');
  const [zoneId, setZoneId] = useState('');
  const [reading, setReading] = useState<Reading | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [extent, setExtent] = useState<'site' | 'building'>('site');
  const [showCoverage, setShowCoverage] = useState(false);
  const upload = useRef<HTMLInputElement>(null);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const [resume, setResume] = useState<Session | null>(null);
  useEffect(() => {
    let active = true;
    api<{session: Session | null}>('/concepts/sessions/latest').then(r => {if (active) setResume(r.session);}).catch(() => {});
    return () => {active = false;};
  }, []);
  useEffect(() => {messagesEnd.current?.scrollIntoView({block: 'nearest'});}, [session?.messages.length, busy]);

  const useSession = (next: Session, keepSelected = true) => {
    setSession(next);
    const previous = keepSelected && next.candidates.find(c => c.id === selected && c.status !== 'discarded');
    const choice = previous || next.candidates.find(c => c.id === next.accepted_id) || next.candidates.filter(c => c.status !== 'discarded').at(-1);
    setSelected(choice?.id || ''); setZoneId('');
  };
  const ensureSession = async () => session || await api<Session>('/concepts/sessions', {template});
  const send = async () => {
    if (!draft.trim() || busy) return;
    const message = draft.trim(); setBusy('Designing spatial alternatives and checking geometry…'); setError('');
    try {
      const s = await ensureSession(); setSession(s);
      const next = await api<Session>(`/concepts/sessions/${s.id}/propose`, {message, base_candidate_id: selected || null});
      useSession(next, false); setDraft('');
    } catch (e) {setError(e instanceof Error ? e.message : 'The design could not be generated. Try a simpler brief.');}
    finally {setBusy('');}
  };
  const choose = async (action: 'accept' | 'discard' | 'undo' | 'redo') => {
    if (!session || busy) return;
    setBusy('Updating the concept selection…'); setError('');
    try {
      const next = await api<Session>(`/concepts/sessions/${session.id}/${action}`, {candidate_id: selected, expected_accepted_id: session.accepted_id});
      useSession(next, action !== 'undo' && action !== 'redo');
    } catch (e) {setError(e instanceof Error ? e.message : 'The selection could not be updated. Reload and try again.');}
    finally {setBusy('');}
  };
  const readFile = async (file: File) => {
    setBusy('Reading the site drawing…'); setError('');
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('Choose a site file smaller than 8 MB.');
      if (file.name.toLowerCase().endsWith('.json')) {
        const value = JSON.parse(await file.text());
        setReading(await api<Reading>('/concepts/validate-site', {site: value.site || value}));
      } else {
        const data = await new Promise<string>((resolve, reject) => {const r = new FileReader(); r.onload = () => resolve(String(r.result).split(',')[1]); r.onerror = () => reject(new Error('The file could not be opened. Choose it again.')); r.readAsDataURL(file);});
        setReading(await api<Reading>('/concepts/read-site', {attachment: {name: file.name, mime_type: file.type || (file.name.toLowerCase().endsWith('.pdf') ? 'application/pdf' : 'image/png'), data}}));
      }
      setExtent('site');
    } catch (e) {setError(e instanceof Error ? e.message : 'The drawing could not be read. Try a clearer PDF or image.');}
    finally {setBusy(''); if (upload.current) upload.current.value = '';}
  };
  const confirmSite = async () => {
    if (!reading?.site || busy) return;
    setBusy('Saving the confirmed site…'); setError('');
    try {const s = await ensureSession(); useSession(await api<Session>(`/concepts/sessions/${s.id}/site`, {site: reading.site})); setSelected(''); setReading(null);}
    catch (e) {setError(e instanceof Error ? e.message : 'The site could not be saved. Review its coordinates.');}
    finally {setBusy('');}
  };
  const candidate = session?.candidates.find(c => c.id === selected && c.status !== 'discarded');
  const visible = session?.candidates.filter(c => c.status !== 'discarded') || [];
  const shownCandidate = reading ? undefined : candidate;
  const site = reading ? reading.site : shownCandidate?.site || session?.site || null;
  const metric = candidate?.metrics.zones.find(z => z.id === zoneId);
  const zone = candidate?.plan.zones.find(z => z.id === zoneId);

  return <div className="composer concept-designer">
    <header className="agent-topbar">
      <div className="agent-brand"><Sparkles size={17}/><strong>Planchakto</strong><span>Spatial concepts</span></div>
      <div className="agent-topbar-actions"><span>{aiProvider ? 'AI connected' : 'AI unavailable'}</span><button className="agent-ghost-button" onClick={onExit}><ArrowLeft size={14}/> Back</button></div>
    </header>
    <div className="concept-workspace">
      <section className="concept-conversation" aria-label="Design conversation">
        <header><h1>Start with the space.</h1><p>Explore arrangements, connections and site fit before engineering.</p></header>
        <div className="concept-messages" aria-live="polite">
          {!session?.messages.length && <div className="concept-introduction"><p>Describe how the building should work. The designer can choose the shape, room arrangement, entrances and shared spaces.</p><p>Add a lot plan to work within its boundary. You’ll review the reading before it is used.</p>{!session && resume && <button className="agent-ghost-button" onClick={() => {useSession(resume, false); setDraft('');}}>Resume previous concepts</button>}</div>}
          {session?.messages.map((m, i) => <div key={i} className={`concept-message ${m.role}`}><strong>{m.role === 'user' ? 'You' : 'Design assistant'}</strong><p>{m.text}</p>{m.questions?.map(q => <p key={q} className="concept-question">{q}</p>)}</div>)}
          {busy && <p className="concept-progress" role="status"><Loader2 className="spin" size={16}/>{busy}</p>}
          <div ref={messagesEnd}/>
        </div>
        {error && <p className="concept-error" role="alert">{error}</p>}
        <form className="concept-input" onSubmit={e => {e.preventDefault(); send();}}>
          <label htmlFor="concept-brief">Design brief or change</label>
          <textarea id="concept-brief" rows={5} maxLength={12000} value={draft} onChange={e => setDraft(e.target.value)} disabled={!!busy} placeholder="A home improvement store with open sales space, project consultation, customer parking and separate truck receiving…"/>
          <div><button type="button" className="agent-ghost-button" disabled={!!busy} onClick={() => upload.current?.click()}><FileUp size={14}/> Add lot plan</button><button className="agent-primary-button" disabled={!!busy || !aiProvider || !draft.trim() || !!reading}><Send size={14}/> Explore layouts</button></div>
          <input ref={upload} type="file" accept="application/pdf,image/png,image/jpeg,image/webp,.json" hidden aria-label="Site drawing or site JSON" onChange={e => {const f = e.target.files?.[0]; if (f) readFile(f);}}/>
        </form>
      </section>
      <main className="concept-stage">
        <header className="concept-toolbar"><div><strong>{reading ? 'Review the site reading' : candidate?.plan.title || 'Your design canvas'}</strong><span>Concept planning · engineering not checked</span></div><div><button className="agent-ghost-button" onClick={() => choose('undo')} disabled={!!busy || !session?.can_undo} aria-label="Undo accepted concept"><Undo2 size={15}/></button><button className="agent-ghost-button" onClick={() => choose('redo')} disabled={!!busy || !session?.can_redo} aria-label="Redo accepted concept"><Redo2 size={15}/></button></div></header>
        {visible.length > 0 && <div className="concept-options" aria-label="Design alternatives">{visible.map((c, i) => <button key={c.id} className={selected === c.id ? 'selected' : ''} aria-pressed={selected === c.id} onClick={() => {setSelected(c.id); setZoneId(''); setReading(null);}}><span>{session?.accepted_id === c.id && <Check size={13}/>} {c.plan.title}</span><small>Option {i+1} · {num(c.metrics.footprint_area_m2, 0)} m²</small></button>)}</div>}
        <div className="concept-view-tools"><div role="group" aria-label="Drawing extent"><button aria-pressed={extent === 'site'} onClick={() => setExtent('site')}>Site</button><button aria-pressed={extent === 'building'} disabled={!shownCandidate} onClick={() => setExtent('building')}>Building</button></div><span>{site ? `${num(site.reported_area_m2 || candidate?.metrics.site_area_m2, 0)} m² site · north ${site.north_degrees === null ? 'unconfirmed' : `${site.north_degrees}°`}` : 'No site boundary supplied'}</span></div>
        <div className="concept-canvas">{shownCandidate || site ? <ConceptPlan candidate={shownCandidate} site={site} extent={extent} selected={zoneId} onSelect={setZoneId}/> : <div className="concept-empty"><Sparkles size={28}/><h2>More than one way to arrange it.</h2><p>Your alternatives will appear here with measured areas and explicit connections.</p></div>}</div>
        {reading && <section className="concept-site-review" aria-label="Confirm site reading"><h2>Check the outline before designing</h2><p>{reading.site?.basis || 'The drawing did not establish a usable boundary.'}</p>{[...reading.notes, ...reading.missing].map((n, i) => <p key={i}>{n}</p>)}<details><summary>Boundary coordinates and source</summary><pre>{JSON.stringify(reading.site, null, 2)}</pre></details><div><button className="agent-primary-button" disabled={!reading.site || !!busy} onClick={confirmSite}>Use this site</button><button className="agent-ghost-button" disabled={!!busy} onClick={() => setReading(null)}>Cancel reading</button></div></section>}
        {candidate && !reading && <footer className="concept-actions"><span>{session?.accepted_id === candidate.id ? 'Accepted concept snapshot' : 'Candidate · not applied'}</span><div><button className="agent-ghost-button" disabled={!!busy || session?.accepted_id === candidate.id} onClick={() => choose('discard')}><X size={14}/> Discard</button><button className="agent-ghost-button" onClick={() => download(candidate, 'buildgraph-concept.json')}><Download size={14}/> Export</button><button className="agent-primary-button" disabled={!!busy || session?.accepted_id === candidate.id} onClick={() => choose('accept')}><Check size={14}/> Apply concept</button></div></footer>}
      </main>
      <aside className="concept-inspector" aria-label="Concept details">
        <h2>{zone?.name || 'Design reasoning'}</h2>
        {zone && metric ? <><strong className="concept-area">{num(metric.area_m2)} m²</strong><p>{zone.purpose}</p><p className="concept-source">Area calculated from the proposed polygon.</p><button className="agent-text-button" onClick={() => setZoneId('')}>Back to design reasoning</button></> : <p>{candidate?.plan.rationale || 'The model proposes spatial relationships. Code checks geometry and calculates areas.'}</p>}
        {candidate && <><h3>Spaces</h3><ul className="concept-zone-list">{candidate.metrics.zones.map((z, i) => <li key={z.id}><button className={zoneId === z.id ? 'selected' : ''} onClick={() => setZoneId(z.id)}><span>{i+1}. {z.name}</span><b>{num(z.area_m2, 0)} m²</b></button></li>)}</ul><h3>Assumptions</h3><ul>{candidate.plan.assumptions.map(a => <li key={a}>{a}</li>)}</ul><h3>Tradeoffs</h3><ul>{candidate.plan.tradeoffs.map(a => <li key={a}>{a}</li>)}</ul><button className="agent-text-button" aria-expanded={showCoverage} onClick={() => setShowCoverage(!showCoverage)}>{showCoverage ? 'Hide checking scope' : 'View checking scope'}</button>{showCoverage && <><h3>Geometry checked</h3><ul>{candidate.metrics.coverage.checked.map(c => <li key={c}>{c}</li>)}</ul><h3>Not checked</h3><ul>{candidate.metrics.coverage.not_checked.map(c => <li key={c}>{c}</li>)}</ul><h3>Missing inputs</h3><ul>{candidate.metrics.missing.map(c => <li key={c}>{c}</li>)}</ul></>}</>}
        {!candidate && site && <><h3>Site source</h3><p>{site.source}</p><p>{site.basis}</p></>}
        <p className="concept-review-note">Preliminary concept. Licensed professional review is required. Applying a concept does not create an engineering revision.</p>
        <button className="agent-ghost-button" disabled={!!busy} onClick={() => {setSession(null); setSelected(''); setDraft(''); setReading(null); setError('');}}><Plus size={14}/> New conversation</button>
      </aside>
    </div>
  </div>;
}

export function ConceptPlan({candidate, site, extent, selected, onSelect}: {candidate?: Candidate; site: Site | null; extent: 'site' | 'building'; selected: string; onSelect: (id: string) => void}) {
  const points = extent === 'site' && site ? site.boundary : candidate?.plan.footprint || site?.boundary || [[0,0],[10,10]];
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const x = Math.min(...xs), y = Math.min(...ys), w = Math.max(...xs)-x, h = Math.max(...ys)-y;
  const pad = Math.max(w,h)*.07, font = Math.max(w,h)*.024;
  const poly = (p: XY[]) => p.map(([x,y]) => `${x},${-y}`).join(' ');
  return <svg className="concept-plan" viewBox={`${x-pad} ${-y-h-pad} ${w+pad*2} ${h+pad*2}`} role="img" aria-label="Proposed layout with numbered spaces. Select spaces from the adjacent list for details.">
    {site && <polygon points={poly(site.boundary)} className="concept-lot"/>}
    {site?.road_edge && <line x1={site.boundary[site.road_edge[0]][0]} y1={-site.boundary[site.road_edge[0]][1]} x2={site.boundary[site.road_edge[1]][0]} y2={-site.boundary[site.road_edge[1]][1]} className="concept-road"><title>Road-facing boundary</title></line>}
    {candidate?.plan.zones.map((z, i) => {const m = candidate.metrics.zones.find(m => m.id === z.id);return <g key={z.id}><polygon points={poly(z.polygon)} className={`concept-zone zone-${z.kind} ${z.location === 'outside' ? 'outdoor' : ''} ${selected === z.id ? 'selected' : ''}`} onClick={() => onSelect(z.id)}><title>{z.name}: {num(m?.area_m2)} m²</title></polygon>{m && <text x={m.label[0]} y={-m.label[1]} textAnchor="middle" dominantBaseline="middle" fontSize={font}>{i+1}</text>}</g>;})}
    {candidate && <polygon points={poly(candidate.plan.footprint)} className="concept-shell"/>}
    {candidate?.plan.openings.map(o => <line key={o.id} x1={o.segment[0][0]} y1={-o.segment[0][1]} x2={o.segment[1][0]} y2={-o.segment[1][1]} className="concept-opening"><title>{o.kind}: {o.from_zone} to {o.to_zone}</title></line>)}
  </svg>;
}

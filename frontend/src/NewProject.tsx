import {useEffect, useRef, useState} from 'react';
import {ArrowLeft, ArrowRight, Box, Check, CheckCircle2, ChevronRight, CircleDashed, FileText, GitBranch, Hammer, Home, Layers, Loader2, Plus, Send, Sparkles, Store, Warehouse} from 'lucide-react';
import type {Revision} from './types';
import {api, money, num} from './api';
import {roomColors} from './Plan';
import './composer.css';

type TemplateId = 'house' | 'commercial' | 'warehouse';
type Template = {id: TemplateId; label: string; use: string; height: number; rooms: {name: string; kind: string; area: number; count: number}[]};
type Option = {label: string; description: string; value: unknown};
type Question = {field: string; header: string; question: string; options: Option[]; source?: string};
type RoomSpec = {name: string; kind: string; area: number; count: number};
type Spec = {template: TemplateId; name: string | null; location: string | null; use: string | null; rooms: RoomSpec[]; [key: string]: unknown};
type Preview = {ok: boolean; error?: string; width?: number; depth?: number; height?: number; rooms?: {id: string; name: string; kind: string; x: number; y: number; w: number; h: number}[]; columns?: number[][]; area?: number; notes?: string[]; missing: string[]};
type Turn = {spec: Spec; reply: string | null; questions: Question[]; remaining: number; preview: Preview; mode: string; ai_provider: string | null};
type Edit = {field: string; label: string; before: string; after: string};
type Message = {role: 'user' | 'assistant'; text: string; changes?: Edit[]};

const icons: Record<TemplateId, typeof Home> = {house: Home, commercial: Store, warehouse: Warehouse};
const blurbs: Record<TemplateId, string> = {house: 'Living, kitchen, bath and bedrooms on a 1.5 m hall.', commercial: 'Showroom, offices, stockroom, pantry and toilets for a shop or clinic.', warehouse: 'A tall storage hall with a loading bay and a small office.'};
const examples: Record<TemplateId, string> = {
  house: 'A 3-bedroom family house in Tagaytay with a home office and a bigger kitchen.',
  commercial: 'A dental clinic in Cebu City called Ngiti Dental, with 3 treatment rooms, a waiting area for 12, a sterilisation room, an office, two toilets and a pantry.',
  warehouse: 'A dry-goods warehouse in Valenzuela with a 400 m² storage hall, two loading bays and a dispatch office.',
};
const labels: Record<string, Record<string, string>> = {
  fire_occupancy: {business: 'Business', business_concentrated: 'Business, concentrated', mercantile: 'Mercantile', none: 'Not screened'},
  solar: {none: 'None', '5': '5 kWp', '10': '10 kWp', fill: 'Fill the roof'},
  fault_distance: {far: 'More than 15 km', near: 'Within 15 km (enter Na, Nv)', unknown: 'Not known yet'},
  soil_profile: {unknown: 'SD (not known)', SA: 'SA', SB: 'SB', SC: 'SC', SD: 'SD', SE: 'SE (enter Ca)'},
  frame: {steel_omrf: 'Steel moment frame, R 4.5', unknown: 'Decide later'},
  friction: {assumed: '0.35 (assumed)', unknown: 'Missing'},
};
const decisions: [string, string, (v: unknown) => string][] = [
  ['budget', 'Budget', v => money(v as number)], ['height', 'Eave height', v => `${v} m`],
  ['fire_occupancy', 'Fire occupancy', v => labels.fire_occupancy[v as string]], ['rear_exit', 'Rear exit', v => v ? 'Yes' : 'No'],
  ['fire_provisions', 'Fire provisions', v => v ? 'Included' : 'Left out'], ['solar', 'Solar PV', v => labels.solar[v as string]],
  ['fault_distance', 'Active fault', v => labels.fault_distance[v as string]], ['soil_profile', 'Soil profile', v => labels.soil_profile[v as string]],
  ['frame', 'Lateral system', v => labels.frame[v as string]], ['friction', 'Footing friction', v => labels.friction[v as string]],
];
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const changeLabels: Record<string, string> = {
  name: 'Project name', location: 'Location', use: 'Building use', budget: 'Budget', height: 'Eave height',
  fire_occupancy: 'Fire occupancy', rear_exit: 'Rear exit', fire_provisions: 'Fire provisions', solar: 'Solar PV',
  fault_distance: 'Active fault', soil_profile: 'Soil profile', frame: 'Lateral system', friction: 'Footing friction',
};
const displayValue = (field: string, value: unknown) => {
  if (value == null || value === '') return 'Not set';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (field === 'budget' && typeof value === 'number') return money(value);
  if (field === 'height' && typeof value === 'number') return `${value} m`;
  return labels[field]?.[String(value)] ?? String(value);
};
const roomLabel = (room: RoomSpec) => `${room.count > 1 ? `${room.count} × ` : ''}${room.name} · ${num(room.area, 0)} m²${room.count > 1 ? ' each' : ''}`;
const describeChanges = (before: Spec, after: Spec): Edit[] => {
  const edits: Edit[] = [];
  Object.keys(changeLabels).forEach(field => {
    if (!same(before[field], after[field])) edits.push({field, label: changeLabels[field], before: displayValue(field, before[field]), after: displayValue(field, after[field])});
  });
  const oldRooms = new Map(before.rooms.map(r => [`${r.name.toLowerCase()}|${r.kind}`, r]));
  const newRooms = new Map(after.rooms.map(r => [`${r.name.toLowerCase()}|${r.kind}`, r]));
  newRooms.forEach((room, key) => {
    const old = oldRooms.get(key);
    if (!old) edits.push({field: `room-${key}`, label: room.name, before: 'Not in programme', after: roomLabel(room)});
    else if (!same(old, room)) edits.push({field: `room-${key}`, label: room.name, before: roomLabel(old), after: roomLabel(room)});
  });
  oldRooms.forEach((room, key) => {
    if (!newRooms.has(key)) edits.push({field: `room-${key}`, label: room.name, before: roomLabel(room), after: 'Removed from programme'});
  });
  return edits;
};

export function NewProject({aiProvider, onExit, onBuilt}: {aiProvider: string | null; onExit: () => void; onBuilt: (revision: Revision, notes: string[]) => Promise<void>}) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [template, setTemplate] = useState<TemplateId>('commercial');
  const [brief, setBrief] = useState('');
  const [turn, setTurn] = useState<Turn | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [picked, setPicked] = useState<Record<string, unknown>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [workspaceTab, setWorkspaceTab] = useState<'plan' | 'brief'>('plan');
  const end = useRef<HTMLDivElement>(null);
  const chatScroll = useRef<HTMLDivElement>(null);
  useEffect(() => {api<Template[]>('/compose/templates').then(setTemplates).catch(() => setError('Could not load the templates.'));}, []);
  useEffect(() => {chatScroll.current?.scrollTo({top: chatScroll.current.scrollHeight, behavior: 'smooth'});}, [messages, turn?.questions, busy]);

  const send = async (body: {message?: string; answers?: {field: string; value: unknown}[]}, shown?: string) => {
    if (busy) return;
    const previousSpec = turn?.spec ?? null;
    const history = messages.map(({role, text}) => ({role, text}));
    const visible = shown ? [...messages, {role: 'user' as const, text: shown}] : messages;
    if (shown) setMessages(visible);
    setBusy(body.message ? (aiProvider ? 'Reading your request…' : 'Updating…') : 'Updating the plan…'); setError('');
    try {
      const next = await api<Turn>('/compose/turn', {template, spec: turn?.spec ?? null, history, ...body});
      const changes = previousSpec ? describeChanges(previousSpec, next.spec) : [];
      setTurn(next); setPicked({}); setOther({});
      const reply = next.reply ?? (changes.length ? `I updated ${changes.length === 1 ? 'one part' : `${changes.length} parts`} of the project brief.` : 'The project brief is up to date.');
      if (next.reply || changes.length) setMessages([...visible, {role: 'assistant', text: reply, changes}]);
    } catch (e) {setError(e instanceof Error ? e.message : 'That did not work. Try again.');}
    finally {setBusy('');}
  };
  const start = () => send(brief.trim() ? {message: brief.trim()} : {}, brief.trim() || undefined);
  const submitAnswers = () => {
    const answers = Object.entries(picked).map(([field, value]) => ({field, value}));
    const notes = Object.entries(other).filter(([, v]) => v.trim());
    if (notes.length) {
      const q = Object.fromEntries((turn?.questions ?? []).map(x => [x.field, x.question]));
      const text = notes.map(([f, v]) => `${q[f] ?? f} ${v.trim()}`).join('\n');
      return send({message: text, answers}, text);
    }
    const shown = answers.map(a => {const q = turn?.questions.find(x => x.field === a.field); const o = q?.options.find(x => same(x.value, a.value)); return `${q?.header ?? a.field}: ${(o?.label ?? String(a.value)).replace(' (Recommended)', '')}`;}).join(' · ');
    return send({answers}, shown);
  };
  const build = async () => {
    if (!turn || busy) return;
    setBusy('Building the model and running every check…'); setError('');
    try {const res = await api<{revision: Revision; notes: string[]}>('/compose/build', {spec: turn.spec}); await onBuilt(res.revision, res.notes);}
    catch (e) {setError(e instanceof Error ? e.message : 'The project could not be built.'); setBusy('');}
  };

  if (!turn) return <div className="composer composer-launch-screen">
    <header className="agent-topbar"><div className="agent-brand"><span className="agent-logo"><Box size={18} strokeWidth={1.65}/></span><strong>Planchakto</strong><ChevronRight size={13}/><span>Design assistant</span></div><div className="agent-topbar-actions"><span className={'agent-connection' + (aiProvider ? ' live' : '')}><i/>{aiProvider ? 'AI connected' : 'Guided mode'}</span><button className="agent-ghost-button" onClick={onExit}><ArrowLeft size={14}/> Back to home</button></div></header>
    <main className="composer-start">
      <section className="composer-intro"><span className="composer-orb"><Sparkles size={22}/></span><h1>Design with an agent,<br/>not a blank canvas.</h1><p className="composer-lede">Describe the building and watch the assistant turn your brief into a live, reviewable model. Every edit stays visible before anything is built.</p><div className="composer-proof"><span><CheckCircle2 size={14}/> Typed room programme</span><span><CheckCircle2 size={14}/> Live plan preview</span><span><CheckCircle2 size={14}/> Traceable decisions</span></div></section>
      <section className="composer-launch-card" aria-label="Start a design conversation">
        <div className="launch-card-head"><div><strong>What are you building?</strong><span className="launch-subtitle">Start a new agent task</span></div><span className="launch-shortcut">New project</span></div>
        <div className="template-grid" role="radiogroup" aria-label="Template">
          {templates.map(t => {const Icon = icons[t.id]; const area = t.rooms.reduce((s, r) => s + r.area * r.count, 0); return <button key={t.id} role="radio" aria-checked={template === t.id} className={'template-card' + (template === t.id ? ' selected' : '')} onClick={() => setTemplate(t.id)}>
            <span className="template-icon"><Icon size={17}/></span><span><strong>{t.label}</strong><small>{t.rooms.reduce((s, r) => s + r.count, 0)} rooms · ~{num(area, 0)} m²</small></span>{template === t.id && <Check className="template-check" size={14}/>}
          </button>;})}
        </div>
        <label className="composer-brief"><span>Project prompt</span><textarea rows={6} value={brief} disabled={!aiProvider} onChange={e => setBrief(e.target.value)} placeholder={aiProvider ? examples[template] : 'Free text needs an AI provider on the server.'}/></label>
        <div className="launch-context"><span><Plus size={12}/> Template: {templates.find(t => t.id === template)?.label ?? 'Loading…'}</span><span><Layers size={12}/> Single storey</span></div>
        {aiProvider && !brief && <button className="agent-text-button" onClick={() => setBrief(examples[template])}><Sparkles size={13}/> Try an example prompt</button>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="launch-actions"><p>Up to 30 × 30 m. Missing inputs stay missing.</p><button className="agent-primary-button" disabled={!!busy || !templates.length} onClick={start}>{busy ? <><Loader2 className="spin" size={15}/> {busy}</> : <>Start designing <ArrowRight size={15}/></>}</button></div>
      </section>
    </main>
  </div>;

  const p = turn.preview; const spec = turn.spec;
  const shownDecisions = decisions.filter(([f]) => !(['rear_exit', 'fire_provisions'].includes(f) && (spec.fire_occupancy === 'none' || spec.fire_occupancy == null)) && !(f === 'fire_occupancy' && spec.template === 'house'));
  const decided = shownDecisions.filter(([f]) => spec[f] != null).length;
  const edits = messages.flatMap(m => m.changes ?? []).reverse();
  return <div className="composer composer-agent">
    <header className="agent-topbar"><div className="agent-brand"><span className="agent-logo"><Box size={18} strokeWidth={1.65}/></span><strong>Planchakto</strong><ChevronRight size={13}/><span>{spec.name ?? 'Untitled project'}</span></div><div className="agent-topbar-actions"><span className="agent-branch"><GitBranch size={12}/> candidate / new-project</span><span className={'agent-connection' + (aiProvider ? ' live' : '')}><i/>{aiProvider ? 'AI connected' : 'Guided mode'}</span><button className="agent-ghost-button" onClick={onExit}><ArrowLeft size={14}/> Exit</button></div></header>
    <div className="composer-grid">
      <section className="composer-chat" aria-label="Project conversation">
        <header className="chat-panel-head"><div><span className="chat-agent-icon"><Sparkles size={14}/></span><span><strong>Design assistant</strong><small>{aiProvider ? 'Agent · can edit project brief' : 'Guided questionnaire'}</small></span></div><span className="chat-session">{messages.filter(m => m.role === 'user').length + 1} turns</span></header>
        <div ref={chatScroll} className="chat-scroll" aria-live="polite">
          <div className="chat-msg assistant"><span className="chat-avatar"><Sparkles size={13}/></span><div className="message-body"><p>Starting from the <strong>{templates.find(t => t.id === template)?.label.toLowerCase()}</strong> template. {aiProvider ? 'Tell me what to change, or answer the questions below.' : 'Answer the questions below; free text needs an AI provider.'}</p><span className="message-context"><FileText size={11}/> project brief</span></div></div>
          {messages.map((m, i) => <div key={i} className={'chat-msg ' + m.role}>{m.role === 'assistant' && <span className="chat-avatar"><Sparkles size={13}/></span>}<div className="message-body"><p>{m.text}</p>{m.changes && m.changes.length > 0 && <div className="inline-change-set"><strong><CheckCircle2 size={12}/> Applied {m.changes.length} {m.changes.length === 1 ? 'edit' : 'edits'}</strong>{m.changes.slice(0, 3).map(c => <span key={c.field}><i/> {c.label}: <b>{c.after}</b></span>)}{m.changes.length > 3 && <small>+{m.changes.length - 3} more in Agent edits</small>}</div>}</div></div>)}
          {busy && <WorkProgress label={busy}/>}
          {!busy && turn.questions.length > 0 && <div className="question-stack">
            {turn.questions.map(q => <fieldset key={q.field} className="question-card">
              <legend><span className="question-chip">{q.header}</span>{q.question}</legend>
              {q.options.map(o => {const on = q.field in picked && same(picked[q.field], o.value); return <button key={o.label} type="button" className={'option-row' + (on ? ' on' : '')} aria-pressed={on} onClick={() => setPicked(prev => on ? Object.fromEntries(Object.entries(prev).filter(([k]) => k !== q.field)) : {...prev, [q.field]: o.value})}>
                <span className="option-dot">{on && <Check size={11}/>}</span><span><strong>{o.label}</strong>{o.description && <small>{o.description}</small>}</span>
              </button>;})}
              {aiProvider && <input className="option-other" aria-label={`Other answer for ${q.header}`} placeholder="Other… type your own answer" value={other[q.field] ?? ''} onChange={e => {const v = e.target.value; setOther(prev => ({...prev, [q.field]: v}));}}/>}
            </fieldset>)}
            <div className="question-actions"><span>{turn.remaining > turn.questions.length ? `${turn.remaining - turn.questions.length} more after these` : 'Last questions'}</span><button className="agent-primary-button compact" disabled={!Object.keys(picked).length && !Object.values(other).some(v => v.trim())} onClick={submitAnswers}>Apply answers <ArrowRight size={14}/></button></div>
          </div>}
          {!busy && turn.questions.length === 0 && <div className="chat-msg assistant"><span className="chat-avatar complete"><Check size={13}/></span><div className="message-body"><p>Everything I need is decided. Build the project when the plan looks right, or ask for changes.</p></div></div>}
          <div ref={end}/>
        </div>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <form className="chat-input" onSubmit={e => {e.preventDefault(); if (draft.trim()) {const text = draft.trim(); setDraft(''); send({message: text}, text);}}}>
          <textarea aria-label="Message design assistant" rows={3} value={draft} disabled={!aiProvider || !!busy} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); e.currentTarget.form?.requestSubmit();}}} onChange={e => setDraft(e.target.value)} placeholder={aiProvider ? 'Ask for a design change…' : 'Free text needs an AI provider on the server'}/><div className="chat-input-tools"><span><Plus size={12}/> Context: project brief</span><small>Enter to send · Shift+Enter for new line</small><button className="send" aria-label="Send" disabled={!aiProvider || !!busy || !draft.trim()}><Send size={14}/></button></div>
        </form>
      </section>
      <main className="composer-stage" aria-label="Live project preview">
        <header className="stage-toolbar"><div><strong>{workspaceTab === 'plan' ? 'Ground floor plan' : 'Project brief & agent edits'}</strong><span className={'stage-state' + (busy ? ' working' : '')}><i/>{busy ? 'Updating from agent…' : 'Preview up to date'}</span></div><div className="stage-tabs" role="tablist"><button className={workspaceTab === 'plan' ? 'active' : ''} role="tab" aria-selected={workspaceTab === 'plan'} onClick={() => setWorkspaceTab('plan')}>Plan</button><button className={workspaceTab === 'brief' ? 'active' : ''} role="tab" aria-selected={workspaceTab === 'brief'} onClick={() => setWorkspaceTab('brief')}>Brief & edits</button></div></header>
        {workspaceTab === 'plan' ? <div className={'plan-stage' + (busy ? ' is-updating' : '')}>
          <div className="plan-canvas-head"><span><Layers size={13}/> Architecture / L0</span><span className="mono">Scale to fit</span></div>
          <div className="plan-canvas">{p.ok ? <MiniPlan preview={p}/> : <p className="inline-error">{p.error}</p>}{busy && <div className="plan-working"><Loader2 className="spin" size={18}/><span>Regenerating plan</span></div>}</div>
          {p.ok && <div className="brief-facts"><div><span>Footprint</span><strong>{num(p.width)} × {num(p.depth)} m</strong></div><div><span>Gross area</span><strong>{num(p.area, 0)} m²</strong></div><div><span>Rooms</span><strong>{spec.rooms.reduce((s, r) => s + r.count, 0)}</strong></div></div>}
        </div> : <div className="stage-brief-view"><section><div className="stage-section-head"><div><h2>Agent edits</h2><p>Complete change history from this conversation</p></div><span>{edits.length}</span></div><EditHistory edits={edits}/></section><section><div className="stage-section-head"><div><h2>{spec.name ?? 'Untitled project'}</h2><p>{templates.find(t => t.id === template)?.label} · {[spec.use, spec.location].filter(Boolean).join(' · ') || 'Project details still open'}</p></div></div><h3>Room programme</h3><ul className="stage-room-list">{spec.rooms.map((r, i) => <li key={i}><i style={{background: roomColors[r.kind] ?? '#eee'}}/><span>{r.count > 1 ? `${r.count} × ` : ''}{r.name}</span><b>{num(r.area, 0)} m²{r.count > 1 ? ' each' : ''}</b></li>)}</ul><h3>Decisions</h3><ul className="stage-decision-list">{shownDecisions.map(([f, label, fmt]) => <li key={f}><span>{label}</span><b>{spec[f] == null ? 'To decide' : fmt(spec[f])}</b></li>)}</ul></section></div>}
        <footer className="stage-status"><span><i/> Candidate model · not yet applied</span><span className="mono">{turn.mode} / {p.ok ? 'geometry valid' : 'needs attention'}</span></footer>
      </main>
      <aside className="composer-brief-panel" aria-label="Project brief and agent edits">
        <section className="edits-panel"><div className="panel-heading"><div><strong>Agent edits</strong><span>{edits.length ? 'Changes from this conversation' : 'Waiting for your first change'}</span></div><span className="edit-count">{edits.length}</span></div><EditHistory edits={edits}/></section>
        <section className="brief-panel"><div className="brief-head"><div><h2>{spec.name ?? 'Untitled project'}</h2><p>{templates.find(t => t.id === template)?.label} · {[spec.use, spec.location].filter(Boolean).join(' · ') || 'Project details still open'}</p></div></div><h3>Room programme <small>{spec.rooms.reduce((s, r) => s + r.count, 0)} spaces</small></h3><ul className="room-programme">{spec.rooms.map((r, i) => <li key={i}><i style={{background: roomColors[r.kind] ?? '#eee'}}/><span>{r.count > 1 ? `${r.count} × ` : ''}{r.name}</span><small>{num(r.area, 0)} m²{r.count > 1 ? ' each' : ''}</small></li>)}</ul><h3>Decisions <small>{decided} of {shownDecisions.length}</small></h3><ul className="decision-list">{shownDecisions.map(([f, label, fmt]) => <li key={f} className={spec[f] == null ? 'open' : ''}>{spec[f] == null ? <CircleDashed size={13}/> : <Check size={13}/>}<span>{label}</span><strong>{spec[f] == null ? 'To decide' : fmt(spec[f])}</strong></li>)}</ul>{p.missing.length > 0 && <p className="brief-missing">Missing inputs: {p.missing.join(', ')}.</p>}</section>
        <div className="build-dock"><button className="agent-primary-button build" disabled={!!busy || !p.ok} onClick={build}>{busy?.startsWith('Building') ? <Loader2 className="spin" size={15}/> : <Hammer size={15}/>} {busy?.startsWith('Building') ? 'Building candidate…' : 'Build candidate project'}</button><p>Runs layout, structure, seismic, services, fire, solar and cost checks. Nothing replaces the accepted design.</p></div>
      </aside>
    </div>
  </div>;
}

function WorkProgress({label}: {label: string}) {
  const building = label.startsWith('Building');
  const steps = building ? ['Compose final model', 'Run engineering checks', 'Calculate quantities', 'Create candidate revision'] : ['Read your request', 'Update the typed brief', 'Regenerate the floor plan', 'Check the new geometry'];
  return <div className="work-progress"><div className="work-progress-title"><span className="chat-avatar"><Loader2 className="spin" size={13}/></span><div><strong>{label}</strong><small>Working in the project model</small></div></div><ol>{steps.map((step, i) => <li key={step} className={i === 0 ? 'active' : ''}><span>{i === 0 ? <Loader2 className="spin" size={10}/> : <CircleDashed size={10}/>}</span>{step}</li>)}</ol></div>;
}

function EditHistory({edits}: {edits: Edit[]}) {
  return edits.length ? <ul className="edit-list">{edits.map((edit, i) => <li key={`${edit.field}-${i}`}><span className="edit-icon"><Check size={10}/></span><div><strong>{edit.label}</strong><span><del>{edit.before}</del><ChevronRight size={10}/><b>{edit.after}</b></span></div></li>)}</ul> : <div className="edits-empty"><FileText size={18}/><p>Ask the assistant to resize a room, add a space, or change the project brief. Every edit will appear here.</p></div>;
}

function MiniPlan({preview: p}: {preview: Preview}) {
  const W = p.width ?? 1, D = p.depth ?? 1;
  return <svg className="mini-plan" viewBox={`-0.6 -0.6 ${W + 1.2} ${D + 1.6}`} role="img" aria-label={`Plan preview, ${W} by ${D} metres`}>
    <rect x={0} y={0} width={W} height={D} fill="#fff" stroke="#30463d" strokeWidth={.08}/>
    {p.rooms?.map(r => <rect key={r.id} x={r.x} y={r.y} width={r.w} height={r.h} fill={roomColors[r.kind] ?? '#eee'} stroke="#7d8a7f" strokeWidth={.04}/>)}
    {p.columns?.map(([x, y], i) => <rect key={i} x={x - .12} y={y - .12} width={.24} height={.24} fill="#465e50"/>)}
    {p.rooms?.filter(r => r.kind !== 'corridor' && r.w > 1.6).map(r => <text key={r.id} x={r.x + r.w / 2} y={r.y + r.h / 2} textAnchor="middle" dominantBaseline="middle" fontSize={Math.min(.55, r.w / 7, r.h / 2.5)} fill="#30463d" stroke="#fff" strokeWidth={.12} paintOrder="stroke">{r.name}</text>)}
    <text x={W / 2} y={D + .8} textAnchor="middle" fontSize={.5} fill="#788478">{W} m × {D} m</text>
  </svg>;
}

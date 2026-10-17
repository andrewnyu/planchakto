import {ArrowLeft, ArrowRight, ArrowUpRight, CheckCircle2, MapPin, RefreshCw, Settings2, Upload} from 'lucide-react';
import type {Check, Diff, Layers, Revision} from './types';
import {disciplineChecks, disciplines, type Discipline} from './planning';
import {money, num} from './api';
import {Plan} from './Plan';
import {Status} from './ui';
import {FireSection} from './Fire';
import {SolarSection} from './Solar';
import {SeismicSection} from './Seismic';

export function DisciplineReview({revision, discipline, diff, comparisonLabel, busy, onDiscipline, onUpload, onLocate, onPropose, onEngineering, onOverview, onQuantities}: {
  revision: Revision; discipline: Discipline; diff: Diff | null; comparisonLabel: string; busy: boolean;
  onDiscipline: (discipline: Discipline) => void; onUpload: () => void; onLocate: (id?: string) => void;
  onPropose: (commands: Record<string, unknown>[], label: string) => void;
  onEngineering: () => void; onOverview: () => void; onQuantities: () => void;
}) {
  const {model: b, results: r} = revision;
  const checks = disciplineChecks(r, discipline);
  const problems = checks.filter(c => ['fail', 'missing_input'].includes(c.status));
  const other = checks.filter(c => !['fail', 'missing_input'].includes(c.status));
  const routeKinds = discipline === 'plumbing' ? ['water', 'drain'] : ['conduit'];
  const routes = r.routing.routes.filter(route => routeKinds.includes(route.kind));
  const definition = disciplines.find(d => d.id === discipline)!;
  const layers: Layers = {architecture: true, furniture: false, terrain: false, structure: discipline === 'structure' || discipline === 'plumbing', electrical: discipline === 'electrical', plumbing: discipline === 'plumbing', fire: discipline === 'fire', solar: discipline === 'solar'};
  const locate = (check: Check) => {
    const route = r.routing.routes.find(route => check.objects.includes(route.id));
    const footing = r.structure.foundations.find(f => check.objects.includes(f.id));
    onLocate(route?.source_id || footing?.column_id || check.objects[0]);
  };
  const evidence = (check: Check) => <article key={check.id} className="review-finding"><div className="review-finding-top"><Status status={check.status}/><span className="mono">{check.rule_id}</span></div><p>{check.evidence}</p><div className="review-finding-actions"><button className="text-button" onClick={() => locate(check)}><MapPin size={13}/> View on plan</button><details><summary>Calculation inputs</summary><pre>{JSON.stringify(check.inputs, null, 2)}</pre><small>Revision {revision.id.slice(-10)}</small></details></div></article>;
  return <div className="content-scroll discipline-page">
    <button className="text-button back-to-graph" onClick={onOverview}><ArrowLeft size={14}/> Planning graph</button>
    <div className="page-heading"><div><h2>Review one system. See the impact.</h2><p>{revision.status === 'candidate' ? 'Candidate model' : 'Saved model'} · {b.name} · <span className="mono">{revision.id.slice(-8)}</span></p></div><button className="button secondary" disabled={busy} onClick={onUpload}><Upload size={15}/> Check a drawing</button></div>
    <div className="discipline-tabs" aria-label="Review discipline">{disciplines.map(d => <button key={d.id} aria-pressed={discipline === d.id} className={discipline === d.id ? 'active' : ''} onClick={() => onDiscipline(d.id)}>{d.label}</button>)}</div>
    <div className="review-scope"><strong>{definition.label}</strong><p>{definition.scope}</p></div>
    <div className="review-grid"><div className="review-findings">
      <div className="review-counts" aria-label="Review results">{[{status: 'fail', label: 'Findings'}, {status: 'missing_input', label: 'Missing inputs'}, {status: 'pass', label: 'Passing screens'}, {status: 'unsupported', label: 'Unassessed screens'}].map(item => <div key={item.status}><strong>{r.stale ? '—' : checks.filter(c => c.status === item.status).length}</strong><span>{item.label}</span></div>)}</div>
      {r.stale ? <p className="reference-note">Recompute this revision using the banner above to refresh these findings.</p> : problems.length ? <div className="priority-findings"><h3>Start with these findings</h3>{problems.map(evidence)}</div> : checks.length ? <div className="review-clear"><CheckCircle2 size={20}/><div><strong>No findings in the evaluated screens</strong><p>Coverage limits remain listed above and in the detailed results.</p></div></div> : <p className="reference-note">This system has not been assessed. {discipline === 'fire' || discipline === 'solar' ? 'Set up the screen below to begin.' : 'Add the relevant model elements and inputs to begin.'}</p>}
      {['plumbing', 'electrical'].includes(discipline) && <div className="review-actions"><button className="button primary" disabled={busy || r.stale || !routes.length} onClick={() => onPropose([{type: 'reroute', mode: 'avoid'}], 'Preview clear service routes')}><RefreshCw size={14}/> Preview clear routes</button><button className="button secondary" onClick={() => onLocate(discipline === 'plumbing' ? b.fixtures[0]?.id : b.equipment[0]?.id)}><Settings2 size={14}/> Edit {discipline === 'plumbing' ? 'fixtures' : 'equipment'}</button><p>Recalculates water, drainage and conduit together. Compare the result before applying.</p></div>}
      {discipline === 'structure' && <button className="button primary" onClick={onEngineering}><Settings2 size={15}/> Edit loads & supports</button>}
      {(discipline === 'fire' || discipline === 'solar' || discipline === 'structure') && <div className="review-system-inputs">{discipline === 'fire' ? <FireSection key={revision.id} model={b} result={r} busy={busy} onPropose={onPropose}/> : discipline === 'solar' ? <SolarSection key={revision.id} model={b} result={r} busy={busy} onPropose={onPropose}/> : <SeismicSection key={revision.id} model={b} result={r} busy={busy} onPropose={onPropose}/>}</div>}
      {!!other.length && !['fire', 'solar'].includes(discipline) && <details className="review-details"><summary>Passing screens & coverage ({other.length})</summary>{other.map(evidence)}</details>}
    </div><aside className="review-context">
      <div className="review-plan"><Plan model={b} result={r} layers={layers} selected="" onSelect={onLocate} onMove={() => {}} accepted={b} compare={false} readOnly/></div>
      <button className="text-button" onClick={() => onLocate()}>Open {definition.label.toLowerCase()} on plan <ArrowUpRight size={14}/></button>
      <div className="review-impact"><span>{diff ? comparisonLabel : 'Current estimate'}</span><strong>{diff ? `${diff.cost_delta >= 0 ? '+' : '−'}${money(Math.abs(diff.cost_delta))}` : money(r.quantities.total)}</strong><p>{diff ? `${diff.geometry.length} geometry changes · ${diff.quantities.filter(q => Math.abs(q.delta) > .00001).length} quantity lines affected` : 'Model quantities with illustrative rates.'}</p>{diff && <small>{money(diff.before_total)} → {money(diff.after_total)}</small>}<button className="text-button" onClick={onQuantities}>Compare quantities <ArrowRight size={13}/></button></div>
      {['plumbing', 'electrical'].includes(discipline) && <div className="review-route-list"><h3>Connections in this model</h3>{routes.map(route => <button key={route.id} onClick={() => onLocate(route.source_id)}><span><strong>{route.name}</strong><small>{route.kind === 'drain' ? 'Drain' : route.kind === 'water' ? 'Cold water' : 'Conduit'} · {num(route.length)} m</small></span><Status status={route.status}/></button>)}{!routes.length && <p>No connections modeled yet.</p>}</div>}
    </aside></div>
  </div>;
}

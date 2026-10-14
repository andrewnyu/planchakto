import {useLayoutEffect, useRef, useState} from 'react';
import {ArrowRight, ArrowUpRight, Armchair, Check, Circle, Columns3, Droplets, FileCheck2, Flame, GitBranch, LayoutGrid, Map, SlidersHorizontal, Sparkles, Sun, Table2, Upload, Zap} from 'lucide-react';
import type {Revision} from './types';
import {planningStages, type Discipline, type StageId} from './planning';

const icons = {site: Map, brief: SlidersHorizontal, layout: LayoutGrid, fitout: Armchair, structure: Columns3, electrical: Zap, plumbing: Droplets, fire: Flame, solar: Sun, quantities: Table2, handoff: FileCheck2};
const groups = ['Set the starting point', 'Shape the spaces', 'Coordinate the systems', 'Review the outcome'];
const edges: [StageId, StageId][] = [
  ['site', 'layout'], ['brief', 'layout'], ['layout', 'fitout'],
  ...(['structure', 'electrical', 'plumbing', 'fire', 'solar'] as const).flatMap(id => [['layout', id], [id, 'quantities']] as [StageId, StageId][]),
  ['quantities', 'handoff'],
];

export function Workflow({revision, onStage, onUpload, onReview, onGenerate, busy}: {
  revision: Revision; onStage: (id: StageId) => void; onUpload: (discipline?: Discipline) => void;
  onReview: (discipline: Discipline) => void; onGenerate: () => void; busy: boolean;
}) {
  const stages = planningStages(revision);
  const prepared = stages.filter(s => s.state === 'ready').length;
  const required = stages.filter(s => s.state !== 'optional').length;
  const next = stages.find(s => ['stale', 'attention', 'missing'].includes(s.state)) || stages.find(s => s.state === 'idle');
  const graph = useRef<HTMLDivElement>(null);
  const [paths, setPaths] = useState<string[]>([]);

  useLayoutEffect(() => {
    const root = graph.current;
    if (!root) return;
    const measure = () => {
      const bounds = root.getBoundingClientRect();
      setPaths(edges.flatMap(([from, to]) => {
        const a = root.querySelector(`[data-stage="${from}"]`)?.getBoundingClientRect();
        const b = root.querySelector(`[data-stage="${to}"]`)?.getBoundingClientRect();
        if (!a || !b) return [];
        if (Math.abs(a.left - b.left) < 2) return [`M ${a.left + a.width / 2 - bounds.left} ${a.bottom - bounds.top} V ${b.top - bounds.top}`];
        const x1 = a.right - bounds.left, y1 = a.top + a.height / 2 - bounds.top;
        const x2 = b.left - bounds.left, y2 = b.top + b.height / 2 - bounds.top;
        const mid = (x1 + x2) / 2;
        return [`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`];
      }));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    root.querySelectorAll('[data-stage]').forEach(node => observer.observe(node));
    measure();
    return () => observer.disconnect();
  }, [revision.id]);

  return <div className="content-scroll workflow-page">
    <div className="workflow-intro">
      <div><span className="eyebrow">YOUR PLANNING WORKSPACE</span><h2>One plan. Every step connected.</h2><p>Start anywhere. Open a step to upload, generate or review your design.</p></div>
      <button className="button primary" onClick={() => onUpload()} disabled={busy}><Upload size={16}/> Review an existing plan</button>
    </div>
    <div className="workflow-progress">
      <div><GitBranch size={18}/><span><strong>{prepared} of {required} stages prepared</strong><small>{revision.status === 'candidate' ? 'Candidate progress · review before applying' : 'Saved model · progress updates as you edit'}</small></span></div>
      <div className="progress-segments" aria-label={`${prepared} of ${required} stages prepared`}>{stages.filter(s => s.state !== 'optional').map(s => <span key={s.id} className={s.state} title={`${s.title}: ${s.label}`}/>)}</div>
      <button className="text-button" onClick={() => onStage(next?.id || 'handoff')}>{next ? `Next: ${next.title}` : 'Review the package'} <ArrowRight size={15}/></button>
    </div>
    <div className="planning-graph" ref={graph} aria-label="Planning process graph">
      <svg className="graph-connectors" aria-hidden="true"><defs><marker id="graph-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#a5b4a8"/></marker></defs>{paths.map((d, i) => <path key={i} d={d} markerEnd="url(#graph-arrow)"/>)}</svg>
      {groups.map((title, group) => <section key={title} className={`graph-column graph-column-${group}`} aria-label={title}>
        <h3><span>0{group + 1}</span>{title}</h3>
        <div className="graph-nodes">{stages.filter(s => s.group === group).map(stage => {
          const Icon = icons[stage.id];
          return <button key={stage.id} data-stage={stage.id} className={`graph-node ${stage.state}`} onClick={() => onStage(stage.id)}>
            <span className="graph-node-title"><Icon size={17}/><strong>{stage.title}</strong><ArrowUpRight size={13}/></span>
            <span className="graph-node-detail">{stage.detail}</span>
            <span className={`stage-state ${stage.state}`}>{stage.state === 'ready' ? <Check size={11}/> : <Circle size={8}/>} {stage.label}</span>
          </button>;
        })}</div>
        {group === 1 && <button className="text-button graph-action" onClick={onGenerate} disabled={busy}><Sparkles size={14}/> Generate alternatives</button>}
      </section>)}
    </div>
    <div className="workflow-bottom">
      <div className="quick-review"><span>Just need a quick check?</span>{(['plumbing', 'fire', 'electrical'] as Discipline[]).map(id => {const Icon = icons[id];return <button key={id} onClick={() => onReview(id)}><Icon size={15}/>{id === 'fire' ? 'Fire protection' : id[0].toUpperCase() + id.slice(1)}<ArrowUpRight size={12}/></button>;})}</div>
      <p>Progress describes model preparation and supported screens. Exported plans still need professional review.</p>
    </div>
  </div>;
}

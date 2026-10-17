import {ArrowRight,ArrowUpRight,Box,CheckCircle2,Columns3,Droplets,FileCheck2,FileText,Flame,GitBranch,MessageSquare,MousePointer2,Play,PlayCircle,ShieldCheck,Sparkles,Sun,Table2,Zap} from 'lucide-react';
import type {Project} from './types';
import {money,num} from './api';
import type {Discipline} from './planning';

const features=[
 {icon:GitBranch,title:'See every change before you accept it',text:'Each edit becomes a candidate revision. Geometry, checks and cost differences are shown side by side, and the accepted design is never overwritten.'},
 {icon:Sparkles,title:'Gemini design assistant',text:'Describe a change in plain language, or upload a hand sketch, photo or existing plan. Gemini turns it into typed edits that run through exactly the same checks as a manual edit.'},
 {icon:Columns3,title:'Structural checks',text:'Roof beams solved with finite elements, footing bearing, and section alternatives when a member fails.'},
 {icon:Droplets,title:'Services routing',text:'Water, drain and conduit routed around columns, with gravity-fall checks on every drain run.'},
 {icon:Sun,title:'Rooftop solar',text:'Panel fit, added roof load, inverter breaker, transformer, hosting-capacity and net-metering screens.'},
 {icon:Flame,title:'Fire protection',text:'RA 9514 egress for business and mercantile use — occupant load, exits, travel distance and extinguishers — with clause citations.'},
 {icon:Table2,title:'Quantities and cost',text:'A takeoff traced back to model elements, priced with editable peso rates, compared per revision.'},
 {icon:FileText,title:'Permit drawings',text:'Architectural, structural, electrical, plumbing and fire sheets with a PH title block, as PDF and layered DXF.'},
];
const steps=[
 {icon:PlayCircle,title:'Open the demo project',text:'San Isidro Studio is a synthetic 12 × 9 m building with six rooms, a corridor and a steel roof grid.'},
 {icon:MousePointer2,title:'Make a change',text:'Drag a room with the Move tool, edit loads in the inspector, or ask the design assistant — in words or with a sketch of the layout you want.'},
 {icon:CheckCircle2,title:'Review the candidate',text:'The banner shows the cost change. Checks lists what passes, fails, needs input or is outside scope — with the evidence.'},
 {icon:ShieldCheck,title:'Apply, discard or undo',text:'Apply when you are satisfied. Every accepted revision is kept, so you can compare, undo and redo at any time.'},
 {icon:Sun,title:'Screen solar and fire',text:'In the Engineering tab, add a rooftop array or screen fire protection. Both draw on the plan.'},
 {icon:FileText,title:'Export for review',text:'Export a permit drawing set, the quantity takeoff or a printable review report.'},
];

const planStages=['Site','Brief','Layout','Systems','Cost','Export'];
const quickChecks:{id:Discipline;label:string;icon:typeof Flame}[]=[{id:'structure',label:'Structure',icon:Columns3},{id:'fire',label:'Fire protection',icon:Flame},{id:'plumbing',label:'Plumbing',icon:Droplets},{id:'electrical',label:'Electrical',icon:Zap}];

export function Splash({project,onNewProject,onStart,onAssistant,onCheck,onSample}:{project:Project|null;onNewProject:()=>void;onStart:()=>void;onAssistant:()=>void;onCheck:(discipline?:Discipline)=>void;onSample:(discipline:'fire')=>void}){
 const b=project?.accepted.model,r=project?.accepted.results;
 return <div className="splash">
  <header className="splash-bar"><div className="splash-brand"><span className="brand-mark"><Box size={22} strokeWidth={1.65}/></span><strong>Planchakto</strong><span className="splash-tag">BuildGraph engine</span></div><button className="button primary" onClick={onStart}>Open workspace <ArrowRight size={14}/></button></header>
  <main>
   <section className="splash-hero">
    <div className="splash-copy">
     <p className="splash-eyebrow">Building planning for Philippine teams</p>
     <h1>Plan it right before you build.</h1>
     <p className="splash-lede">Planchakto keeps the floor plan, structure, services, solar, fire safety and cost in one model. Change one thing and see everything it affects — checked, priced and ready for permit drawings.</p>
     <div className="splash-actions"><a className="button primary large" href="#start">Choose how to start <ArrowRight size={15}/></a><a className="button secondary large" href="#how">How it works</a></div>
    </div>
    <div className="splash-trail" aria-label="How a change propagates">
     <span className="trail-label">One edit, traced end to end</span>
     {[['Edit','Move the bathroom 1.5 m'],['Geometry','walls, doors, circulation'],['Structure','beam and footing checks'],['Services','water, drain and conduit routes'],['Checks','pass · fail · missing input'],['Quantities','takeoff and peso cost']].map(([k,v],i)=><div key={k} className={'trail-step'+(i===5?' last':'')}><i>{i+1}</i><div><strong>{k}</strong><span>{v}</span></div></div>)}
     {b&&r&&<div className="trail-demo"><span>Demo project</span><strong>{b.name}</strong><small>{num(b.width*b.depth)} m² · {r.summary.pass} passing checks · {money(r.quantities.total)} estimate</small></div>}
    </div>
   </section>
   <section className="splash-paths" id="start" aria-label="Choose how to start">
    <article className="path-card path-full">
     <span className="path-eyebrow"><GitBranch size={14}/> Full planning</span>
     <h2>Plan a project</h2>
     <p>Start a new house, commercial building or warehouse from a template and describe it in your own words, or open the demo project. Then work through site, structure, services, fire, solar and cost.</p>
     <ol className="path-stages" aria-label="Planning stages">{planStages.map(s=><li key={s}>{s}</li>)}</ol>
     <div className="path-buttons"><button className="button warm large" onClick={onNewProject}>Start a new project <ArrowRight size={15}/></button><button className="button ghost-light" onClick={onStart}>Open the demo project</button></div>
    </article>
    <article className="path-card path-quick">
     <span className="path-eyebrow"><FileCheck2 size={14}/> Quick check</span>
     <h2>Check a plan</h2>
     <p>Already have drawings? Screen one system and see each finding with its evidence. Continue into the full plan when you are ready.</p>
     <div className="path-checks">{quickChecks.map(c=><button key={c.id} onClick={()=>onCheck(c.id)}><c.icon size={15}/>{c.label}<ArrowUpRight size={12}/></button>)}</div>
     <div className="path-samples"><span>No drawings to hand?</span><button className="text-button" onClick={()=>onCheck('structure')}><Play size={12}/> Framing sample</button><button className="text-button" onClick={()=>onCheck('fire')}><Play size={12}/> Fire sample</button><button className="text-button" onClick={()=>onCheck('plumbing')}><Play size={12}/> Plumbing sample</button><button className="text-button" onClick={()=>onCheck('electrical')}><Play size={12}/> Electrical sample</button><button className="text-button" onClick={()=>onSample('fire')}><Play size={12}/> Fire on the demo</button></div>
     <p className="path-note">Each drawing is screened on its own. Plumbing and electrical are deliberately limited to plan connectivity, gravity fall and load arithmetic; omitted design and coordination work is listed as not checked.</p>
    </article>
   </section>
   <section className="splash-section">
    <h2>What it does</h2>
    <div className="splash-features">{features.map(f=><article key={f.title}><f.icon size={20}/><h3>{f.title}</h3><p>{f.text}</p></article>)}</div>
   </section>
   <section className="splash-section" id="how">
    <h2>How to use it</h2>
    <ol className="splash-steps">{steps.map((s,i)=><li key={s.title}><span className="step-num">{i+1}</span><div><h3><s.icon size={16}/>{s.title}</h3><p>{s.text}</p></div></li>)}</ol>
    <div className="splash-actions"><button className="button primary large" onClick={onStart}>Start with the demo <ArrowRight size={15}/></button><button className="button secondary large" onClick={onAssistant}><MessageSquare size={15}/> Ask the design assistant</button></div>
   </section>
   <footer className="splash-foot">
    <p><strong>Preliminary planning support.</strong> Every result shows its source and its limits. Unsupported checks are labelled, never passed. Drawings need review, signing and sealing by licensed professionals before submission.</p>
    <p className="quiet">Built for the Google Cloud AI Builder Cup · Gemini on Vertex AI · Cloud Run</p>
   </footer>
  </main>
 </div>;
}

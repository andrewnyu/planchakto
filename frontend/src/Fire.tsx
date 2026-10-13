import {useState} from 'react';
import {ArrowRight,Flame,Info,Plus,Trash2} from 'lucide-react';
import type {Building,ExitDoor,Extinguisher,FireProtection,Result} from './types';
import {num} from './api';
import {Status,Field} from './ui';

const ruleName:Record<string,string>={'FIRE-OCCLOAD':'Occupant load','FIRE-EXITS':'Number of exits','FIRE-TRAVEL':'Travel distance','FIRE-DEADEND':'Dead-end corridor','FIRE-COMMON':'Common path','FIRE-CAPACITY':'Exit capacity','FIRE-CORRIDOR':'Corridor width','FIRE-SPRINKLER':'Sprinklers','FIRE-ALARM':'Fire alarm','FIRE-EMLIGHT':'Emergency lighting','FIRE-SIGNS':'Exit signs','FIRE-EXT':'Extinguishers','FIRE-SCOPE':'Not evaluated'};
const occupancies:[FireProtection['occupancy'],string][]=[['business','Business (9.3 m²/person)'],['business_concentrated','Business, concentrated use (4.6 m²/person)'],['mercantile','Mercantile (2.8 m²/person, street floor)']];
const defaults:FireProtection={enabled:true,occupancy:'business',new_building:true,sprinklered:false,alarm:'none',emergency_lighting:false,exit_signs:false,hazard:'low',exits:[],extinguishers:[],mercantile_travel_m:null,mercantile_travel_source:''};

export function FireSection({model:b,result:r,busy,onPropose}:{model:Building;result:Result;busy:boolean;onPropose:(commands:Record<string,unknown>[],label:string)=>void}){
 const [draft,setDraft]=useState<FireProtection>(b.fire??defaults);
 const set=(fire:FireProtection,label:string)=>onPropose([{type:'set_fire',fire}],label);
 const f=r.fire;
 if(!b.fire?.enabled||!f?.enabled)return <><div className="section-head"><h3>Fire protection</h3><span>Optional · RA 9514</span></div>
  <div className="scope-note"><Flame size={17}/><div><strong>Not screened</strong><p>Check egress, exits, travel distance, alarms, signs and extinguishers for a business or mercantile occupancy against the 2019 RIRR of the Fire Code.</p></div><button className="button secondary" disabled={busy} onClick={()=>set({...(b.fire??defaults),enabled:true},'Screen fire protection')}>Screen fire protection <ArrowRight size={13}/></button></div></>;
 const changed=JSON.stringify(draft)!==JSON.stringify(b.fire);
 const up=(patch:Partial<FireProtection>)=>setDraft({...draft,...patch});
 const upExit=(i:number,patch:Partial<ExitDoor>)=>up({exits:draft.exits.map((e,k)=>k===i?{...e,...patch}:e)});
 const upExt=(i:number,patch:Partial<Extinguisher>)=>up({extinguishers:draft.extinguishers.map((e,k)=>k===i?{...e,...patch}:e)});
 const nextId=(prefix:string,ids:string[])=>{let i=ids.length+1;while(ids.includes(`${prefix}-${i}`))i++;return `${prefix}-${i}`};
 const visible=f.checks.filter(c=>c.rule!=='FIRE-SCOPE');
 return <><div className="section-head"><h3>Fire protection</h3><button className="text-button" disabled={busy} onClick={()=>set({...b.fire,enabled:false},'Stop fire protection screen')}>Stop screening</button></div>
 <div className="solar-stats">
  <div><span>Occupant load</span><strong>{f.occupant_load} <small>persons</small></strong><small>{occupancies.find(o=>o[0]===f.occupancy)?.[1]}{f.mercantile_class?` · Class ${f.mercantile_class}`:''}</small></div>
  <div><span>Longest travel</span><strong>{num(f.travel.max_m,1)} <small>m</small></strong><small>to the nearest of {f.exits.length} exit{f.exits.length===1?'':'s'}</small></div>
  <div><span>Dead end · common path</span><strong>{num(f.travel.dead_end_m,1)} <small>m</small> · {num(f.travel.common_path_m,1)} <small>m</small></strong><small>corridor · shared route</small></div>
  <div><span>Extinguisher reach</span><strong>{f.extinguishers.max_travel_m==null?'None placed':<>{num(f.extinguishers.max_travel_m,1)} <small>m</small></>}</strong><small>limit {f.extinguishers.reach_m} m · min {f.extinguishers.min_rating}</small></div>
 </div>
 {r.quantities.unpriced?.some(q=>q.id.startsWith('fire_'))&&<div className="inline-error">This project's rate catalog has no fire_extinguishers / fire_exits rates, so they are not in the cost estimate (see Quantities).</div>}
 <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Check</th><th>Evidence</th><th>Screen</th></tr></thead><tbody>{visible.map(c=><tr key={c.rule}><td><strong>{ruleName[c.rule]||c.rule}</strong><small className="mono">{c.rule}</small></td><td>{c.evidence}<small className="solar-source">{c.clause}</small></td><td><Status status={c.status}/></td></tr>)}</tbody></table></div>
 <p className="footnote"><Info size={12}/> {f.scope} Not evaluated: {f.checks.filter(c=>c.rule==='FIRE-SCOPE').map(c=>c.evidence.replace(': not evaluated','')).join(', ')}. {f.source}</p>
 <details className="solar-edit"><summary>Edit occupancy, exits & provisions</summary>
 <form onSubmit={evt=>{evt.preventDefault();set(draft,'Update fire protection')}}>
  <fieldset><legend>Occupancy</legend>
   <Field label="Occupancy"><select value={draft.occupancy} onChange={e=>up({occupancy:e.target.value as FireProtection['occupancy']})}>{occupancies.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></Field>
   <Field label="Contents hazard (extinguishers)"><select value={draft.hazard} onChange={e=>up({hazard:e.target.value as FireProtection['hazard']})}><option value="low">Low — 2-A, 15 m</option><option value="moderate">Moderate — 3-A, 12 m</option><option value="high">High — 4-A, 10 m</option></select></Field>
   <label className="check-field"><input type="checkbox" checked={draft.new_building} onChange={e=>up({new_building:e.target.checked})}/> New building</label>
   {draft.occupancy==='mercantile'&&<Field label="Unsprinklered travel limit" hint={draft.mercantile_travel_source}><div className="input-unit"><input type="number" step="any" min={0} value={draft.mercantile_travel_m??''} onChange={e=>up({mercantile_travel_m:e.target.value===''?null:Number(e.target.value)})}/><span>m</span></div></Field>}
  </fieldset>
  <fieldset><legend>Provisions</legend>
   <Field label="Fire alarm"><select value={draft.alarm} onChange={e=>up({alarm:e.target.value as FireProtection['alarm']})}><option value="none">None</option><option value="manual">Manual</option><option value="automatic">Automatic</option></select></Field>
   {([['sprinklered','Supervised automatic sprinklers throughout'],['emergency_lighting','Emergency lighting'],['exit_signs','Exit signs']] as const).map(([k,l])=><label key={k} className="check-field"><input type="checkbox" checked={draft[k]} onChange={e=>up({[k]:e.target.checked})}/> {l}</label>)}
  </fieldset>
  <fieldset className="wide"><legend>Added exits <small>(the west corridor entry always counts)</small></legend>
   {draft.exits.map((e,i)=><div className="row-fields" key={e.id}><select aria-label="Exit wall" value={e.wall} onChange={evt=>upExit(i,{wall:evt.target.value as ExitDoor['wall']})}>{['north','south','east','west'].map(w=><option key={w}>{w}</option>)}</select><div className="input-unit"><input aria-label="Exit offset" type="number" step=".05" min={0} value={e.offset} onChange={evt=>upExit(i,{offset:Number(evt.target.value)})}/><span>m along</span></div><div className="input-unit"><input aria-label="Exit width" type="number" step=".05" min={.5} value={e.width} onChange={evt=>upExit(i,{width:Number(evt.target.value)})}/><span>m wide</span></div><button type="button" className="icon-button" aria-label="Remove exit" onClick={()=>up({exits:draft.exits.filter((_,k)=>k!==i)})}><Trash2 size={14}/></button></div>)}
   <button type="button" className="text-button" onClick={()=>up({exits:[...draft.exits,{id:nextId('exit',draft.exits.map(e=>e.id)),wall:'east',offset:Math.max(0,b.depth/2-.5),width:.9}]})}><Plus size={13}/> Add exit</button>
  </fieldset>
  <fieldset className="wide"><legend>Portable extinguishers</legend>
   {draft.extinguishers.map((e,i)=><div className="row-fields" key={e.id}><select aria-label="Extinguisher room" value={e.room_id} onChange={evt=>upExt(i,{room_id:evt.target.value})}>{b.rooms.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select><div className="input-unit"><input aria-label="Offset x" type="number" step=".1" value={e.dx} onChange={evt=>upExt(i,{dx:Number(evt.target.value)})}/><span>dx</span></div><div className="input-unit"><input aria-label="Offset y" type="number" step=".1" value={e.dy} onChange={evt=>upExt(i,{dy:Number(evt.target.value)})}/><span>dy</span></div><select aria-label="Rating" value={e.rating} onChange={evt=>upExt(i,{rating:evt.target.value as Extinguisher['rating']})}>{['2-A','3-A','4-A'].map(x=><option key={x}>{x}</option>)}</select><button type="button" className="icon-button" aria-label="Remove extinguisher" onClick={()=>up({extinguishers:draft.extinguishers.filter((_,k)=>k!==i)})}><Trash2 size={14}/></button></div>)}
   <button type="button" className="text-button" onClick={()=>{const hall=b.rooms.find(r=>r.kind==='corridor')??b.rooms[0];up({extinguishers:[...draft.extinguishers,{id:nextId('fe',draft.extinguishers.map(e=>e.id)),room_id:hall.id,dx:hall.w/2,dy:.2,rating:'2-A'}]})}}><Plus size={13}/> Add extinguisher</button>
  </fieldset>
  <button className="button primary full" disabled={busy||!changed}>Preview & recompute <ArrowRight size={14}/></button>
 </form></details></>;
}

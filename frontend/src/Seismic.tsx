import {useState} from 'react';
import {Activity,ArrowRight} from 'lucide-react';
import type {Building,Lateral,Param,Result} from './types';
import {num} from './api';
import {Status,Field} from './ui';

const soils:[Lateral['soil_profile'],string][]=[['SA','SA · hard rock'],['SB','SB · rock'],['SC','SC · very dense soil / soft rock'],['SD','SD · stiff soil (default when unknown)'],['SE','SE · soft soil'],['SF','SF · site-specific study required']];
const params:[keyof Lateral,string,string][]=[['r_factor','Response modification R','Lateral system, Table 208-11'],['na','Near-source Na','Zone 4 · PHIVOLCS FaultFinder distance'],['nv','Near-source Nv','Zone 4 · PHIVOLCS FaultFinder distance'],['ca','Ca override','Blank uses the built-in table where confirmed'],['cv','Cv override','Blank uses the built-in table where confirmed'],['friction','Base friction μ','From the geotechnical report']];
const sections:[string,string][]=[['SHS150','SHS 150 × 150 × 6'],['SHS200','SHS 200 × 200 × 8'],['SHS250','SHS 250 × 250 × 9']];
const user='User-entered project assumption';

export function SeismicSection({model:b,result:r,busy,onPropose}:{model:Building;result:Result;busy:boolean;onPropose:(commands:Record<string,unknown>[],label:string)=>void}){
 const lat=b.engineering.lateral;
 const [draft,setDraft]=useState<Lateral>(lat);
 const set=(lateral:Lateral,label:string)=>onPropose([{type:'set_lateral',lateral}],label);
 const s=r.lateral;
 if(!lat?.enabled||!s?.enabled)return <><div className="section-head"><h3>Seismic · lateral frames</h3><span>NSCP 2015 §208</span></div>
  <div className="scope-note"><Activity size={17}/><div><strong>Not screened</strong><p>Compute the design base shear, share it between the moment frames on every grid line, then check storey drift, steel columns and footings under seismic load.</p></div><button className="button secondary" disabled={busy} onClick={()=>set({...lat,enabled:true},'Screen seismic loads')}>Screen seismic <ArrowRight size={13}/></button></div></>;
 const v=s.base_shear,c=s.coefficients,d=s.directions;
 const peak=Math.max(0,...(s.columns??[]).map(x=>x.utilization));
 const param=(key:keyof Lateral)=>draft[key] as Param;
 const setParam=(key:keyof Lateral,value:number|null)=>setDraft({...draft,[key]:{...param(key),value,source:user}});
 const changed=JSON.stringify(draft)!==JSON.stringify(lat);
 return <><div className="section-head"><h3>Seismic · lateral frames</h3><button className="text-button" disabled={busy} onClick={()=>set({...lat,enabled:false},'Remove seismic screen')}>Turn off</button></div>
 <div className="solar-stats">
  <div><span>Design base shear</span><strong>{v?num(v.V_kN,1):'—'} <small>kN</small></strong><small>{v?`${num(v.Cs*100,1)}% of W = ${num(s.weight_kN,1)} kN · ${v.governing}`:'Pending inputs'}</small></div>
  <div><span>Period</span><strong>{v?num(v.T_s,3):'—'} <small>s</small></strong><small>Zone {lat.zone} · soil {lat.soil_profile} · Ca {c?.Ca!=null?num(c.Ca):'—'} · Cv {c?.Cv!=null?num(c.Cv):'—'}</small></div>
  <div><span>Storey drift ΔM</span><strong>{d?`${num(d.X.drift_m_mm,1)} / ${num(d.Y.drift_m_mm,1)}`:'—'} <small>mm</small></strong><small>{d?`X / Y · limit ${num(d.X.limit_mm,0)} mm · ρ ${num(d.X.rho)}, ${num(d.Y.rho)}`:'Pending inputs'}</small></div>
  <div><span>Peak column utilization</span><strong>{num(peak*100,0)} <small>%</small></strong><small>{s.column_capacity?`${s.column_capacity.section} · KL/r ${num(s.column_capacity.KL_r,0)} · φPn ${num(s.column_capacity.Pc_kN,0)} kN`:''}</small></div>
 </div>
 {!!s.missing?.length&&<div className="inline-error">Missing: {s.missing.join(', ')}. Drift, column and footing seismic checks stay pending until these are entered.</div>}
 <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Check</th><th>Finding</th><th>Screen</th></tr></thead><tbody>{s.checks.filter(x=>x.rule!=='COLUMN'&&x.rule!=='FRAME-MEMBER'&&x.rule!=='FOOT-LATERAL').map((x,i)=><tr key={x.rule+i}><td><strong>{x.rule}</strong><small>{x.clause}</small></td><td>{x.evidence}</td><td><Status status={x.status}/></td></tr>)}</tbody></table></div>
 {d&&<><div className="section-head"><h3>Moment frames</h3><span>Rigid roof diaphragm · base shear shared by stiffness</span></div>
 <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Frame</th><th>Columns</th><th>Stiffness</th><th>Share of V</th><th>ΔS</th></tr></thead><tbody>{(['X','Y'] as const).flatMap(k=>d[k].frames).map(f=><tr key={f.id}><td><strong>{f.id.replace('frame-','')}</strong><small>grid at {num(f.line_m)} m</small></td><td>{f.columns.length}</td><td>{num(f.stiffness_kN_mm,2)} kN/mm</td><td>{num(f.share*100,0)}%</td><td>{num(f.drift_s_mm,2)} mm</td></tr>)}</tbody></table></div></>}
 {!!s.columns?.length&&<><div className="section-head"><h3>Columns</h3><div className="section-options compact">{sections.map(([id,label])=><button key={id} className={b.engineering.column_section===id?'selected':''} disabled={busy} onClick={()=>onPropose([{type:'set_parameter',field:'column_section',value:id}],`Use ${label} columns`)}><span><strong>{label}</strong></span></button>)}</div></div>
 <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Column</th><th>Governing combination</th><th>P / M</th><th>Utilization</th><th>Screen</th></tr></thead><tbody>{s.columns.map(x=><tr key={x.id}><td>{x.column_id}</td><td>{x.combo}</td><td>{num(x.P_kN??0,1)} kN · {num(x.M_kNm??0,2)} kN·m</td><td><div className="utilization"><i style={{width:`${Math.min(100,x.utilization*100)}%`,background:x.status==='fail'?'#c17650':undefined}}/></div>{num(x.utilization*100,0)}%</td><td><Status status={x.status}/></td></tr>)}</tbody></table></div></>}
 {!!s.footings?.length&&<><div className="section-head"><h3>Footings under seismic load</h3><span>ASD · eccentric bearing, overturning, sliding</span></div>
 <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Footing</th><th>Governing case</th><th>q max</th><th>Eccentricity</th><th>Sliding FS</th><th>Screen</th></tr></thead><tbody>{s.footings.map(x=><tr key={x.id}><td>{x.column_id}</td><td>{x.combo}</td><td>{x.q_max_kPa!=null?`${num(x.q_max_kPa,1)} / ${num(x.allowable_kPa)} kPa`:x.contact}</td><td>{x.e_m!=null?`${num(x.e_m,3)} m · ${x.contact}`:'—'}</td><td>{x.sliding_fs!=null?(Number.isFinite(x.sliding_fs)?num(x.sliding_fs):'∞'):'—'}</td><td><Status status={x.status}/></td></tr>)}</tbody></table></div></>}
 <details className="solar-edit"><summary>Edit seismic inputs</summary>
  <form onSubmit={e=>{e.preventDefault();if(changed)set(draft,'Updated seismic inputs')}}>
   <fieldset><legend>Site</legend>
    <Field label="Seismic zone"><select value={draft.zone} onChange={e=>setDraft({...draft,zone:Number(e.target.value) as 2|4})}><option value={4}>Zone 4 (Z = 0.4)</option><option value={2}>Zone 2 (Z = 0.2)</option></select></Field>
    <Field label="Soil profile" hint={draft.soil_source}><select value={draft.soil_profile} onChange={e=>setDraft({...draft,soil_profile:e.target.value as Lateral['soil_profile']})}>{soils.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></Field>
    <Field label="Importance factor I"><div className="input-unit"><input type="number" step="any" min={0} value={draft.importance} onChange={e=>setDraft({...draft,importance:Number(e.target.value)})}/><span/></div></Field>
   </fieldset>
   <fieldset><legend>Coefficients</legend>
    {params.map(([key,label,hint])=><Field key={key} label={label} hint={(lat[key] as Param).basis||hint}><div className="input-unit"><input aria-label={label} type="number" step="any" min={0} value={param(key).value??''} placeholder="missing" onChange={e=>setParam(key,e.target.value===''?null:Number(e.target.value))}/><span/></div></Field>)}
   </fieldset>
   <fieldset><legend>Frame</legend>
    <Field label="Column base"><select value={draft.base_fixity} onChange={e=>setDraft({...draft,base_fixity:e.target.value as Lateral['base_fixity']})}><option value="fixed">Fixed (moment base plate)</option><option value="pinned">Pinned</option></select></Field>
    <Field label="Column effective length K"><div className="input-unit"><input type="number" step="any" min={0} value={draft.k_factor} onChange={e=>setDraft({...draft,k_factor:Number(e.target.value)})}/><span/></div></Field>
    <Field label="Required sliding FS" hint="1.0 with the 0.6D combination; raise for a project criterion"><div className="input-unit"><input type="number" step="any" min={1} value={draft.sliding_fs} onChange={e=>setDraft({...draft,sliding_fs:Number(e.target.value)})}/><span/></div></Field>
   </fieldset>
   <div className="assumption-box"><strong>Sources</strong><p>{s.source}</p></div>
   <button className="button primary" disabled={busy||!changed}>Preview & recompute <ArrowRight size={14}/></button>
  </form>
 </details>
 <p className="footnote">{s.scope}</p></>;
}

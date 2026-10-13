import {useState} from 'react';
import {ArrowRight,Info,Sun} from 'lucide-react';
import type {Building,Result,Solar} from './types';
import {num} from './api';
import {Status,Field} from './ui';

type Key=keyof Solar;
const groups:{title:string;fields:[Key,string,string,boolean?][]}[]=[
 {title:'Array',fields:[['target_kwp','Target size (blank fills roof)','kWp',true],['module_watts','Module rating','W'],['module_length','Module length','m'],['module_width','Module width','m'],['module_mass','Module mass','kg'],['racking_mass','Racking mass','kg/m²'],['edge_setback','Roof edge setback','m']]},
 {title:'Inverter & service',fields:[['inverter_kw','Inverter AC rating','kW',true],['voltage','Output voltage','V'],['service_main_a','Main breaker','A',true],['busbar_a','Panel busbar rating','A',true]]},
 {title:'Utility',fields:[['transformer_kva','Serving transformer','kVA',true],['hosting_capacity_kw','DU hosting capacity','kW',true],['contracted_kw','Contracted capacity','kW',true]]},
 {title:'Yield',fields:[['peak_sun_hours','Peak sun hours','h/day'],['performance_ratio','Performance ratio','']]},
];
const ruleSource:Record<string,string>={'PV-OCPD':'ocpd','PV-BUSBAR':'busbar','PV-XFMR':'transformer','PV-HOSTING':'hosting','PV-NETMETER':'netmeter'};
const ruleName:Record<string,string>={'PV-ROOF':'Array fit','PV-LOAD':'Roof beams with PV','PV-WIND':'Wind uplift','PV-OCPD':'Inverter breaker','PV-BUSBAR':'Busbar 120% rule','PV-XFMR':'Transformer loading','PV-HOSTING':'DU hosting capacity','PV-NETMETER':'Net-metering cap'};

export function SolarSection({model:b,result:r,busy,onPropose}:{model:Building;result:Result;busy:boolean;onPropose:(commands:Record<string,unknown>[],label:string)=>void}){
 const [draft,setDraft]=useState<Solar>(b.solar);
 const set=(solar:Solar,label:string)=>onPropose([{type:'set_solar',solar}],label);
 const s=r.solar;
 if(!b.solar?.enabled||!s?.enabled)return <><div className="section-head"><h3>Solar PV</h3><span>Optional</span></div>
  <div className="scope-note"><Sun size={17}/><div><strong>No rooftop array</strong><p>Add PV to see roof fit, the extra load on the roof beams, inverter protection, and transformer, hosting and net-metering screens.</p></div><button className="button secondary" disabled={busy} onClick={()=>set({...(b.solar??{}),enabled:true} as Solar,'Add rooftop solar PV')}>Add solar <ArrowRight size={13}/></button></div></>;
 const e=s.electrical,l=s.layout;
 const changed=JSON.stringify(draft)!==JSON.stringify(b.solar);
 return <><div className="section-head"><h3>Solar PV</h3><button className="text-button" disabled={busy} onClick={()=>set({...b.solar,enabled:false},'Remove rooftop solar PV')}>Remove array</button></div>
 <div className="solar-stats">
  <div><span>Array</span><strong>{num(l.kwp)} <small>kWp</small></strong><small>{l.count} × {b.solar.module_watts} W · {l.orientation}</small></div>
  <div><span>Estimated yield</span><strong>{num(e.annual_kwh,0)} <small>kWh/yr</small></strong><small>{b.solar.peak_sun_hours} h/day · PR {b.solar.performance_ratio}</small></div>
  <div><span>Added roof load</span><strong>{num(l.dead_load_kPa,3)} <small>kPa</small></strong><small>{num(l.area_m2,1)} m² of array</small></div>
  <div><span>Inverter breaker</span><strong>{e.pv_breaker_A??'—'} <small>A</small></strong><small>{num(e.output_current_A,1)} A output · DC/AC {num(e.dc_ac_ratio)}</small></div>
 </div>
 {r.quantities.unpriced?.some(q=>q.id.startsWith('pv_'))&&<div className="inline-error">This project's rate catalog has no PV rates, so the array is not in the cost estimate. Add pv_modules, pv_racking and pv_inverter rates (or reset to the demo project).</div>}
 <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Check</th><th>Evidence</th><th>Screen</th></tr></thead><tbody>{s.checks.map(c=><tr key={c.rule}><td><strong>{ruleName[c.rule]||c.rule}</strong><small className="mono">{c.rule}</small></td><td>{c.evidence}{ruleSource[c.rule]&&<small className="solar-source">{s.sources[ruleSource[c.rule]]}</small>}</td><td><Status status={c.status}/></td></tr>)}</tbody></table></div>
 <p className="footnote"><Info size={12}/> {s.scope}</p>
 <details className="solar-edit"><summary>Edit array, service & utility inputs</summary>
 <form onSubmit={evt=>{evt.preventDefault();set(draft,'Update solar PV inputs')}}>
  {groups.map(g=><fieldset key={g.title}><legend>{g.title}</legend>{g.fields.map(([key,label,unit,nullable])=><Field key={key} label={label}><div className="input-unit"><input aria-label={label} type="number" step="any" min={0} value={(draft[key] as number|null)??''} onChange={evt=>setDraft({...draft,[key]:evt.target.value===''?(nullable?null:draft[key]):Number(evt.target.value)})}/><span>{unit}</span></div></Field>)}
   {g.title==='Inverter & service'&&<Field label="Phases"><select value={draft.phases} onChange={evt=>setDraft({...draft,phases:Number(evt.target.value) as 1|3})}><option value={1}>Single-phase</option><option value={3}>Three-phase</option></select></Field>}
   {g.title==='Utility'&&<Field label="Customer class" hint="Residential cap 100 kW; non-residential min(1 MW, contracted). Verify current ERC/DOE rules."><select value={draft.customer_class} onChange={evt=>setDraft({...draft,customer_class:evt.target.value as Solar['customer_class']})}><option value="residential">Residential</option><option value="non_residential">Non-residential</option></select></Field>}
  </fieldset>)}
  <div className="assumption-box"><strong>Input provenance</strong><p>{b.solar.module_source}</p><p>{b.solar.setback_source}</p><p>{b.solar.yield_source}</p></div>
  <button className="button primary full" disabled={busy||!changed}>Preview & recompute <ArrowRight size={14}/></button>
 </form></details></>;
}

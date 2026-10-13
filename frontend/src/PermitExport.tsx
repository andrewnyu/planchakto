import {useState} from 'react';
import {ChevronDown,ChevronRight,Download,Loader2} from 'lucide-react';
import type {Building,Result} from './types';
import {Field} from './ui';

type Discipline='A'|'S'|'E'|'P'|'FP';
type Professional={name:string;prc_no:string;prc_validity:string;apo_no:string;ptr_no:string;ptr_date:string;ptr_place:string;tin:string};
type Form={sheet:'20x30'|'A3';project_title:string;location:string;owner:string;disciplines:Discipline[];professionals:Partial<Record<Discipline,Professional>>};
const disciplines:[Discipline,string,string][]=[['A','Architectural','A-1 site · A-2 floor plan'],['S','Structural','S-1 foundation & roof framing'],['E','Electrical','E-1 layout, loads, PV single-line'],['P','Plumbing / sanitary','P-1 layout & fixtures'],['FP','Fire protection','FP-1 egress plan (needs fire screen)']];
const proFields:[keyof Professional,string][]=[['name','Name'],['prc_no','PRC No.'],['prc_validity','PRC validity'],['apo_no','IAPOA / APO No.'],['ptr_no','PTR No.'],['ptr_date','PTR date'],['ptr_place','PTR place'],['tin','TIN']];
const blank:Professional={name:'',prc_no:'',prc_validity:'',apo_no:'',ptr_no:'',ptr_date:'',ptr_place:'',tin:''};
const KEY='buildgraph.permit-form';
function load(name:string):Form{
 const fallback:Form={sheet:'20x30',project_title:name,location:'',owner:'',disciplines:['A','S','E','P','FP'],professionals:{}};
 try{const saved=JSON.parse(localStorage.getItem(KEY)||'null');return saved?{...fallback,...saved}:fallback}catch{return fallback}
}

export function PermitExport({revisionId,model:b,result:r}:{revisionId:string;model:Building;result:Result}){
 const [form,setForm]=useState<Form>(()=>load(b.name));const [open,setOpen]=useState<Discipline|''>('');const [busy,setBusy]=useState('');const [error,setError]=useState('');
 const update=(next:Form)=>{setForm(next);try{localStorage.setItem(KEY,JSON.stringify(next))}catch{/* per-viewer convenience only */}};
 const pro=(d:Discipline)=>form.professionals[d]??blank;
 const download=async(format:'pdf'|'dxf')=>{
  setBusy(format);setError('');
  try{
   const res=await fetch(`/api/export/${revisionId}/permit.${format}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form)});
   if(!res.ok){let detail=`Export failed (${res.status})`;try{const d=await res.json();detail=typeof d.detail==='string'?d.detail:JSON.stringify(d.detail)}catch{/* keep status */}throw new Error(detail)}
   const url=URL.createObjectURL(await res.blob());const a=document.createElement('a');a.href=url;a.download=format==='pdf'?`permit-set-${revisionId}-${form.sheet}.pdf`:`permit-set-${revisionId}.dxf`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}
 };
 const failing=r.summary.fail??0,missing=r.summary.missing_input??0;
 return <section className="permit-export">
  <header><h3>Permit drawing set</h3><p>Discipline sheets with a PH permit title block (PRC / PTR / TIN and seal fields). Sheets are marked preliminary until signed and sealed.</p></header>
  {(failing>0||missing>0)&&<div className="inline-error">This revision has {failing} failing and {missing} missing-input checks. They are listed on sheet A-1; resolve them before submission.</div>}
  <div className="permit-grid">
   <Field label="Sheet size" hint="20″ × 30″ is the common OBO standard; some LGUs accept A3 for residential. Confirm locally."><select value={form.sheet} onChange={e=>update({...form,sheet:e.target.value as Form['sheet']})}><option value="20x30">20″ × 30″ (508 × 762 mm)</option><option value="A3">A3 (297 × 420 mm)</option></select></Field>
   <Field label="Project title"><input value={form.project_title} onChange={e=>update({...form,project_title:e.target.value})}/></Field>
   <Field label="Location"><input value={form.location} placeholder="Lot / block, barangay, city" onChange={e=>update({...form,location:e.target.value})}/></Field>
   <Field label="Owner / applicant"><input value={form.owner} onChange={e=>update({...form,owner:e.target.value})}/></Field>
  </div>
  <div className="permit-disciplines">{disciplines.map(([d,label,sheets])=>{const on=form.disciplines.includes(d);const disabled=d==='FP'&&!r.fire?.enabled;return <div key={d} className={'permit-discipline '+(on&&!disabled?'on':'')}>
   <label><input type="checkbox" checked={on&&!disabled} disabled={disabled} onChange={e=>update({...form,disciplines:e.target.checked?[...form.disciplines,d]:form.disciplines.filter(x=>x!==d)})}/><span><strong>{label}</strong><small>{disabled?'Enable the fire protection screen first':sheets}</small></span></label>
   {on&&!disabled&&<button type="button" className="text-button" aria-expanded={open===d} onClick={()=>setOpen(open===d?'':d)}>{open===d?<ChevronDown size={13}/>:<ChevronRight size={13}/>}Professional {pro(d).name?`· ${pro(d).name}`:''}</button>}
   {open===d&&<div className="permit-pro">{proFields.map(([k,l])=><Field key={k} label={l}><input value={pro(d)[k]} onChange={e=>update({...form,professionals:{...form.professionals,[d]:{...pro(d),[k]:e.target.value}}})}/></Field>)}</div>}
  </div>})}</div>
  {error&&<div className="inline-error">{error}</div>}
  <div className="permit-actions">
   <button className="button primary" disabled={!!busy||!form.disciplines.length} onClick={()=>download('pdf')}>{busy==='pdf'?<Loader2 size={14} className="spin"/>:<Download size={14}/>} PDF sheet set</button>
   <button className="button secondary" disabled={!!busy||!form.disciplines.length} onClick={()=>download('dxf')}>{busy==='dxf'?<Loader2 size={14} className="spin"/>:<Download size={14}/>} DXF (layered, metres)</button>
  </div>
  <p className="footnote">Details saved in this browser only. Elevations, sections, details and the vicinity map are not generated.</p>
 </section>;
}

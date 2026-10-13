import type {ReactNode} from 'react';
import {AlertTriangle,CheckCircle2,Info} from 'lucide-react';
export function Status({status,label}:{status:string;label?:string}){const Icon=status==='pass'?CheckCircle2:status==='fail'?AlertTriangle:Info;return <span className={'status '+status}><Icon size={12}/>{label||status.replace('_',' ')}</span>}
export function Field({label,children,hint}:{label:string;children:ReactNode;hint?:string}){return <label className="field"><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>}

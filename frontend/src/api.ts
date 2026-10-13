export async function api<T>(path:string,body?:unknown):Promise<T>{
 const res=await fetch('/api'+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!res.ok){let data;try{data=await res.json()}catch{throw new Error(`Server error ${res.status}`)}throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail))}
 return res.json();
}
export const money=(n:number)=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP',maximumFractionDigits:0}).format(n);
export const num=(n:number|null|undefined,d=2)=>n==null?'Not supplied':n.toLocaleString('en-PH',{maximumFractionDigits:d});

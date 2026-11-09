export const money=(paisa:number=0,compact=false)=>new Intl.NumberFormat('en-PK',{style:'currency',currency:'PKR',maximumFractionDigits:compact?1:0,notation:compact?'compact':'standard'}).format(paisa/100);
export const number=(n:number=0)=>new Intl.NumberFormat('en-PK').format(n);
export const label=(s:string='')=>s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
export const date=(s:string)=>new Date(s).toLocaleString('en-PK',{timeZone:'Asia/Karachi',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
export function download(text:string,name:string,type='text/csv'){const a=document.createElement('a');const url=URL.createObjectURL(new Blob([text],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function errorText(err:unknown){return err instanceof Error?err.message:String(err);}

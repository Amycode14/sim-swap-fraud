import { create } from 'zustand';
type Session={token:string;setToken:(value:string)=>void};
// Memory only: credentials disappear on refresh; production uses your identity provider's browser flow.
export const useSession=create<Session>(set=>({token:'',setToken:token=>set({token})}));
export async function api(path:string, options:RequestInit={}){
 const token=useSession.getState().token;
 const response=await fetch('/api/v1'+path,{...options,headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,...options.headers}});
 if(!response.ok){const data=await response.json().catch(()=>({detail:response.statusText}));throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
 return response.json();
}

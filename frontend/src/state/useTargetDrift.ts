import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAllocationTargets } from "../lib/allocationTargetsApi";
import { usePreferences } from "./usePreferences";
const key = "stocks.target-tolerance.v1";
const event = "stocks-target-tolerance";
function readTolerance() {
  try {const raw=localStorage.getItem(key);const v=raw===null?2:Number(raw);return Number.isFinite(v)&&v>=0&&v<=100?v:2;} catch {return 2;}
}
function subscribe(notify:()=>void) {
  window.addEventListener(event,notify);window.addEventListener("storage",notify);
  return ()=>{window.removeEventListener(event,notify);window.removeEventListener("storage",notify);};
}
export function useTargetDrift() {
  const {accountFilter} = usePreferences();
  const account = accountFilter === "all" ? null : accountFilter;
  const tolerance=useSyncExternalStore(subscribe,readTolerance,()=>2);
  const setTolerance=(v:number)=>{if(!Number.isFinite(v)||v<0||v>100)return;try{localStorage.setItem(key,String(v));}catch{/* Storage unavailable: retain the disclosed default. */}window.dispatchEvent(new Event(event));};
  const query=useQuery({queryKey:["allocation-targets",account,tolerance],queryFn:()=>getAllocationTargets(account,tolerance)});
  return {query,tolerance,setTolerance};
}

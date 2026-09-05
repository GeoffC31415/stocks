import { requestJson } from "./api";
export type TargetGroup = {group_id:number; name:string; instrument_ids:number[]; actual_value_gbp:number; actual_weight_pct:number|null; target_weight_pct:number|null; drift_pp:number|null; gap_gbp:number|null; within_tolerance:boolean|null};
export type AllocationTargets = {status:"available"|"unavailable"; account_name:string|null; invested_value_gbp:number; excluded_cash_gbp:number|null; tolerance_pp:number; target_sum_tolerance_pp:number; cash_policy:string; reasons:string[]; groups:TargetGroup[]};
export function getAllocationTargets(account:string|null, tolerance:number) {
  const p = new URLSearchParams({tolerance_pp:String(tolerance)});
  if (account) p.set("account_name", account);
  return requestJson<AllocationTargets>(`/api/portfolio/allocation-targets?${p}`);
}

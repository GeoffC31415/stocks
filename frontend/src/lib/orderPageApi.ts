import { requestJson, type Order } from "./api";

export type AmountReason = "missing_amounts" | "non_finite_amounts" | "non_finite_total";
export type OrderPageItem = Order & { cost_proceeds_gbp_reason: AmountReason | null };
export type OrderPage = {
  items: OrderPageItem[]; total_count: number; offset: number; limit: number; has_more: boolean;
  totals: { buy_gbp: number | null; sell_gbp: number | null; drip_gbp: number | null };
  totals_reasons: { buy_gbp: AmountReason | null; sell_gbp: AmountReason | null; drip_gbp: AmountReason | null };
  classification_basis: string;
};

/** URL scope stays independent of the performance period. Repeated IDs are ORed. */
export function orderPageParams(params: URLSearchParams, account: string): URLSearchParams {
  const query = new URLSearchParams({limit:"100"});
  for(const value of params.getAll("offset").length?params.getAll("offset"):["0"])query.append("offset",value);
  if (account !== "all") query.set("account_name", account);
  for (const key of ["search", "kind", "from_date", "to_date"]) {
    for(const value of params.getAll(key))query.append(key,value);
  }
  for (const key of ["instrument_ids", "group_ids"]) {
    for (const value of params.getAll(key)) query.append(key, value);
  }
  // Existing source/attribution links use inst; T20 can use repeated instrument_ids.
  for(const value of params.getAll("inst"))query.append("instrument_ids",value);
  return query;
}

export function getOrderPage(params: URLSearchParams, signal?: AbortSignal) {
  return requestJson<OrderPage>(`/api/orders/page?${params}`, { signal });
}

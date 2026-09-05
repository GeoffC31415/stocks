import { useEffect, useRef } from "react";
import type { OrderPage } from "../lib/orderPageApi";
import { toGbp } from "../lib/formatters";
import { OrderRow } from "./OrderRow";

export function OrderHistorySection({ page, pending, error, params, onChange, onRetry }: {
  page?: OrderPage; pending: boolean; error: boolean; params: URLSearchParams;
  onChange: (key: string, value: string) => void; onRetry: () => void;
}) {
  const resultsRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!pending && !error && page && restoreFocus.current) {
      // Do not steal focus if the user moved elsewhere while waiting.
      if (document.activeElement === document.body) resultsRef.current?.focus();
      restoreFocus.current = false;
    }
  }, [pending, error, page]);
  const changePage = (offset: number) => {
    restoreFocus.current = true;
    onChange("offset", String(offset));
  };
  const amount = (key: keyof OrderPage["totals"]) => {
    const value = page!.totals[key];
    const reason = page!.totals_reasons?.[key];
    const labels = { missing_amounts: "missing amounts", non_finite_amounts: "non-finite amounts", non_finite_total: "non-finite total" };
    return value === null ? `Unavailable${reason ? ` (${labels[reason]})` : ""}` : toGbp(value);
  };
  return <section className="glass min-w-0 space-y-4 rounded-2xl p-5" aria-label="Order history">
    <div className="flex flex-wrap gap-3">
      <label>Search orders<input aria-label="Search orders" className="block rounded bg-slate-900 p-2" placeholder="Name, ticker or identifier" value={params.get("search") ?? ""} onChange={e => onChange("search", e.target.value)} /></label>
      <label>Kind<select aria-label="Order kind" className="block rounded bg-slate-900 p-2" value={params.get("kind") ?? "all"} onChange={e => onChange("kind", e.target.value)}>
        <option value="all">All</option><option value="buy">Buy</option><option value="sell">Sell</option><option value="drip">DRIP proxy</option>
      </select></label>
      <label>From<input aria-label="Orders from date" className="block rounded bg-slate-900 p-2" type="date" value={params.get("from_date") ?? ""} onChange={e => onChange("from_date", e.target.value)} /></label>
      <label>To<input aria-label="Orders to date" className="block rounded bg-slate-900 p-2" type="date" value={params.get("to_date") ?? ""} onChange={e => onChange("to_date", e.target.value)} /></label>
    </div>
    <p className="text-xs text-slate-400">Reinvestment proxy, not dividend ledger. Stored import-time classification; changing the threshold does not retrospectively reclassify orders.</p>
    {pending ? <p role="status">Loading matching transactions…</p> : error ? <div role="alert">Could not load matching transactions. <button onClick={onRetry}>Retry</button></div> : page && <>
      <p className="text-sm text-slate-300">Full-filter totals (not just this page): Buys {amount("buy_gbp")} · Sales {amount("sell_gbp")} · Reinvestment proxy {amount("drip_gbp")}</p>
      <p role="status">Showing {page.items.length ? page.offset + 1 : 0}–{page.items.length ? page.offset + page.items.length : 0} of {page.total_count} matching transactions</p>
      <div ref={resultsRef} role="region" aria-label="Order results" tabIndex={0} className="max-h-[600px] max-w-full space-y-1 overflow-auto">
        {page.items.map(order => <div className="min-w-[450px]" key={order.id}><OrderRow order={order} showName /></div>)}
        {!page.items.length && <p>No orders on this page. Refine your filters or go back.</p>}
      </div>
      <nav aria-label="Order pagination" className="flex gap-4">
        <button aria-label="Previous page" disabled={page.offset === 0} onClick={() => changePage(Math.max(0, page.offset - page.limit))}>Back</button>
        <button aria-label="Next page" disabled={!page.has_more} onClick={() => changePage(page.offset + page.limit)}>Next</button>
      </nav>
    </>}
  </section>;
}

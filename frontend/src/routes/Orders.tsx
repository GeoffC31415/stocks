import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { getOrderPage, orderPageParams } from "../lib/orderPageApi";
import { usePreferences } from "../state/usePreferences";
import { OrderHistorySection } from "../components/OrderHistorySection";
import { MatchingWarningBanner } from "../components/MatchingWarningBanner";

export function Orders() {
  const { accountFilter } = usePreferences();
  const [params, setParams] = useSearchParams();
  const account = params.get("account") ?? accountFilter;
  const queryParams = orderPageParams(params, account);
  const scopeParams = new URLSearchParams(queryParams);
  scopeParams.delete("offset");
  const scope = scopeParams.toString();
  const previousScope = useRef(scope);
  const scopeChanged = previousScope.current !== scope;
  if (scopeChanged) queryParams.set("offset", "0");
  useEffect(() => {
    previousScope.current = scope;
    if (scopeChanged && params.get("offset") !== "0") {
      const next = new URLSearchParams(params);
      next.set("offset", "0");
      setParams(next, { replace: true });
    }
  }, [scope, scopeChanged, params, setParams]);
  const query = useQuery({
    queryKey: ["orders-page", queryParams.toString()],
    queryFn: ({ signal }) => getOrderPage(queryParams, signal),
    // Never retain another filter/page's rows, including error/retry transitions.
    placeholderData: undefined,
  });
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "offset") next.set("offset", "0");
    next.set("account", account);
    setParams(next);
  };
  return <div className="space-y-6">
    <MatchingWarningBanner />
    <h1 className="text-2xl font-semibold text-white">Order history</h1>
    <OrderHistorySection page={query.data} pending={query.isFetching} error={query.isError}
      params={params} onChange={change} onRetry={() => { void query.refetch(); }} />
  </div>;
}

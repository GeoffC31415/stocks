export type PortfolioSummary = {
  as_of_date: string | null;
  import_batch_id: number | null;
  total_value_gbp: number;
  total_book_cost_gbp: number;
  total_pnl_gbp: number;
  by_account: Record<string, number>;
  by_group: Record<string, number>;
  allocation: AllocationRow[];
  group_allocation: AllocationRow[];
  worst_pct: Instrument[];
  best_pct: Instrument[];
};

export type AllocationRow = {
  label: string;
  kind: string;
  value_gbp: number;
  weight_pct: number;
  target_pct: number | null;
  drift_pct: number | null;
  is_concentration_risk: boolean;
};

export type Instrument = {
  id: number;
  account_name: string;
  identifier: string;
  security_name: string;
  is_cash: boolean;
  ticker: string | null;
  sector: string | null;
  region: string | null;
  asset_class: string | null;
  closed_at: string | null;
  latest_value_gbp: number | null;
  latest_book_cost_gbp: number | null;
  latest_pct_change: number | null;
  pnl_gbp: number | null;
  latest_quote_price_gbp: number | null;
  latest_quote_as_of_date: string | null;
  latest_quote_fetched_at: string | null;
  trailing_drip_yield_pct: number | null;
  group_ids: number[];
};

export type ImportChangedEntry = {
  instrument_id: number;
  identifier: string;
  account_name: string;
  security_name?: string | null;
  quantity_before?: number | null;
  quantity_after?: number | null;
  value_before?: number | null;
  value_after?: number | null;
  delta_value_gbp?: number | null;
};

export type ImportBatch = {
  id: number;
  created_at: string;
  as_of_date: string;
  file_sha256: string;
  filename: string | null;
  diff_summary: {
    new_instrument_ids?: number[];
    closed?: Array<Record<string, unknown>>;
    changed?: ImportChangedEntry[];
    row_count?: number;
    previous_batch_id?: number | null;
    previous_as_of_date?: string | null;
  } | null;
};

export type ImportDiffSummary = {
  batch_id: number;
  as_of_date: string;
  previous_batch_id: number | null;
  previous_as_of_date: string | null;
  new_instrument_ids: number[];
  closed: Array<Record<string, unknown>>;
  changed: ImportChangedEntry[];
  row_count: number | null;
  orders_linked: number | null;
};

export type SnapshotDiffRow = {
  instrument_id: number;
  identifier: string;
  security_name: string;
  account_name: string;
  quantity_from: number | null;
  quantity_to: number | null;
  delta_quantity: number | null;
  value_from_gbp: number | null;
  value_to_gbp: number | null;
  delta_value_gbp: number | null;
  price_from: number | null;
  price_to: number | null;
  delta_price: number | null;
  weight_from_pct: number | null;
  weight_to_pct: number | null;
  delta_weight_pct: number | null;
  status: string;
};

export type SnapshotDiffResponse = {
  from_batch: ImportBatch;
  to_batch: ImportBatch;
  rows: SnapshotDiffRow[];
};

export type Group = {
  id: number;
  name: string;
  color: string | null;
  target_allocation_pct: number | null;
  member_count: number;
  total_value_gbp: number | null;
};

export type InstrumentHistoryPoint = {
  as_of_date: string;
  value_gbp: number | null;
  book_cost_gbp: number | null;
  discretionary_cost_basis_gbp: number | null;
  quantity: number | null;
  pct_change: number | null;
};

export type Order = {
  id: number;
  security_name: string;
  order_date: string;
  order_status: string;
  account_name: string;
  side: string;
  quantity: number | null;
  cost_proceeds_gbp: number | null;
  country: string | null;
  is_drip: boolean;
};

export type OrderAnalytics = {
  total_orders: number;
  total_buy_gbp: number;
  total_drip_gbp: number;
  total_sell_gbp: number;
  cash_deployed_gbp: number;
  net_cash_invested_gbp: number;
  drip_count: number;
  buy_count: number;
  sell_count: number;
  drip_threshold_gbp: number;
  annual_drip: Array<{ year: number; total_gbp: number }>;
  first_order_date: string | null;
};

export type OrderImportBatchOut = {
  id: number;
  created_at: string;
  filename: string | null;
  row_count: number;
};

export type EstimatedTimeseriesPoint = {
  month: string;
  estimated_value_gbp: number;
};

export type BenchmarkPoint = {
  date: string;
  symbol: string;
  close: number;
  rebased_value: number;
};

export type InstrumentQuote = {
  instrument_id: number;
  ticker: string;
  price_gbp: number | null;
  price_ccy: string | null;
  as_of_date: string | null;
  fetched_at: string | null;
};

export type CashflowPoint = {
  month: string;
  monthly_discretionary: number;
  monthly_drip: number;
  monthly_sells: number;
  cumulative_net_deployed: number;
  cumulative_drip: number;
  cumulative_sells: number;
};

export type PositionSummary = {
  security_name: string;
  instrument_id: number | null;
  total_buy_gbp: number;
  discretionary_buy_gbp: number;
  total_drip_gbp: number;
  total_sell_gbp: number;
  net_cost_gbp: number;
  order_count: number;
  drip_count: number;
  first_order_date: string;
  last_order_date: string;
  current_value_gbp: number | null;
  estimated_pnl_gbp: number | null;
  annualised_return_pct: number | null;
  trailing_drip_yield_pct: number | null;
  realized_pnl_gbp: number | null;
  is_closed: boolean;
};

export type GroupPerformanceTimeseriesPoint = {
  as_of_date: string;
  value_gbp: number;
  book_cost_gbp: number;
};

export type GroupPerformanceMember = {
  instrument_id: number;
  security_name: string;
  identifier: string;
  current_value_gbp: number | null;
  net_cost_gbp: number;
  pnl_gbp: number | null;
  annualised_return_pct: number | null;
  weight_pct: number | null;
  first_order_date: string | null;
};

export type GroupPerformance = {
  group_id: number;
  name: string;
  color: string | null;
  member_count: number;
  members_with_value: number;
  total_current_value_gbp: number;
  total_net_cost_gbp: number;
  total_pnl_gbp: number;
  pnl_pct: number | null;
  combined_cagr_pct: number | null;
  weighted_cagr_pct: number | null;
  earliest_order_date: string | null;
  timeseries: GroupPerformanceTimeseriesPoint[];
  members: GroupPerformanceMember[];
};

/**
 * Local calendar date derived from the file's last-modified instant (same value sent to the API as
 * file_metadata_date). Browsers do not expose true file creation time.
 */
export const snapshotDateIsoFromFile = (file: File): string => {
  const d = new Date(file.lastModified);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

export const formatSnapshotDateIso = (isoDate: string): string => {
  const parts = isoDate.split("-").map(Number);
  const [y, mo, day] = parts;
  if (parts.length !== 3 || !y || !mo || !day) return isoDate;
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric"
  }).format(new Date(y, mo - 1, day));
};

const toError = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.detail?.message === "string") return data.detail.message;
  } catch (_err) {
    // Ignore parse errors and fallback to status text.
  }
  return response.statusText || "Request failed";
};

const requestJson = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(await toError(response));
  return response.json() as Promise<T>;
};

export const api = {
  getSummary: () => requestJson<PortfolioSummary>("/api/portfolio/summary"),
  getTimeseries: () => requestJson<Array<{ as_of_date: string; total_value_gbp: number; total_book_cost_gbp: number }>>("/api/portfolio/timeseries"),
  getInstruments: () => requestJson<Instrument[]>("/api/instruments"),
  getImports: () => requestJson<ImportBatch[]>("/api/imports"),
  getImport: (batchId: number) => requestJson<ImportBatch>(`/api/imports/${batchId}`),
  getImportDiff: (batchId: number) =>
    requestJson<ImportDiffSummary>(`/api/imports/${batchId}/diff`),
  compareImports: (fromBatchId: number, toBatchId: number) =>
    requestJson<SnapshotDiffResponse>(
      `/api/imports/diff?from=${fromBatchId}&to=${toBatchId}`,
    ),
  getGroups: () => requestJson<Group[]>("/api/groups"),
  getInstrumentHistory: (instrumentId: number) =>
    requestJson<InstrumentHistoryPoint[]>(`/api/instruments/${instrumentId}/history`),
  updateInstrumentMarket: (
    instrumentId: number,
    patch: { ticker?: string | null; sector?: string | null; region?: string | null; asset_class?: string | null },
  ) =>
    requestJson<Instrument>(`/api/instruments/${instrumentId}/market`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  refreshInstrumentQuote: (instrumentId: number) =>
    requestJson<InstrumentQuote>(`/api/instruments/${instrumentId}/quote`, { method: "POST" }),
  createGroup: (name: string, color: string | null, target_allocation_pct?: number | null) =>
    requestJson<Group>("/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color, target_allocation_pct })
    }),
  updateGroup: (
    groupId: number,
    patch: { name?: string; color?: string | null; target_allocation_pct?: number | null },
  ) =>
    requestJson<Group>(`/api/groups/${groupId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    }),
  deleteGroup: async (groupId: number): Promise<void> => {
    const response = await fetch(`/api/groups/${groupId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await toError(response));
  },
  replaceGroupMembers: (groupId: number, instrument_ids: number[]) =>
    requestJson<Group>(`/api/groups/${groupId}/members`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instrument_ids })
    }),
  importXls: async (file: File, asOfDate: string | null, force: boolean) => {
    const formData = new FormData();
    formData.append("file", file);
    if (asOfDate) formData.append("as_of_date", asOfDate);
    if (!asOfDate) formData.append("file_metadata_date", snapshotDateIsoFromFile(file));
    formData.append("force", String(force));
    return requestJson<{ batch: ImportBatch; summary: Record<string, unknown> }>("/api/imports", {
      method: "POST",
      body: formData
    });
  },
  importOrderXls: async (file: File, dripThreshold: number, force: boolean) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("drip_threshold", String(dripThreshold));
    formData.append("force", String(force));
    return requestJson<OrderImportBatchOut>("/api/orders/import", {
      method: "POST",
      body: formData
    });
  },
  getOrderAnalytics: (dripThreshold: number) =>
    requestJson<OrderAnalytics>(`/api/orders/analytics?drip_threshold=${dripThreshold}`),
  getOrders: (dripThreshold: number) =>
    requestJson<Order[]>(`/api/orders?drip_threshold=${dripThreshold}&limit=500`),
  getInstrumentOrders: (instrumentId: number, dripThreshold: number) =>
    requestJson<Order[]>(`/api/instruments/${instrumentId}/orders?drip_threshold=${dripThreshold}`),
  getCashflowTimeseries: (dripThreshold: number) =>
    requestJson<CashflowPoint[]>(`/api/orders/cashflow-timeseries?drip_threshold=${dripThreshold}`),
  getOrderPositions: (dripThreshold: number) =>
    requestJson<PositionSummary[]>(`/api/orders/positions?drip_threshold=${dripThreshold}`),
  getEstimatedTimeseries: () =>
    requestJson<EstimatedTimeseriesPoint[]>("/api/orders/estimated-timeseries"),
  getBenchmarks: (symbols: string[], start?: string, baseValue?: number) => {
    const params = new URLSearchParams();
    for (const symbol of symbols) params.append("symbols", symbol);
    if (start) params.set("start", start);
    if (baseValue != null) params.set("base_value", String(baseValue));
    return requestJson<BenchmarkPoint[]>(`/api/portfolio/benchmarks?${params.toString()}`);
  },
  getGroupPerformance: (dripThreshold: number) =>
    requestJson<GroupPerformance[]>(
      `/api/groups/performance?drip_threshold=${dripThreshold}`,
    ),
};

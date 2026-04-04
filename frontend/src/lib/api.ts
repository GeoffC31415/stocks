export type PortfolioSummary = {
  as_of_date: string | null;
  import_batch_id: number | null;
  total_value_gbp: number;
  total_book_cost_gbp: number;
  total_pnl_gbp: number;
  by_account: Record<string, number>;
  by_group: Record<string, number>;
  worst_pct: Instrument[];
  best_pct: Instrument[];
};

export type Instrument = {
  id: number;
  account_name: string;
  identifier: string;
  security_name: string;
  is_cash: boolean;
  closed_at: string | null;
  latest_value_gbp: number | null;
  latest_book_cost_gbp: number | null;
  latest_pct_change: number | null;
  pnl_gbp: number | null;
  group_ids: number[];
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
    changed?: Array<Record<string, unknown>>;
    row_count?: number;
  } | null;
};

export type Group = {
  id: number;
  name: string;
  color: string | null;
  member_count: number;
  total_value_gbp: number | null;
};

export type InstrumentHistoryPoint = {
  as_of_date: string;
  value_gbp: number | null;
  book_cost_gbp: number | null;
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
  realized_pnl_gbp: number | null;
  is_closed: boolean;
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
  getGroups: () => requestJson<Group[]>("/api/groups"),
  getInstrumentHistory: (instrumentId: number) =>
    requestJson<InstrumentHistoryPoint[]>(`/api/instruments/${instrumentId}/history`),
  createGroup: (name: string, color: string | null) =>
    requestJson<Group>("/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, color })
    }),
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
    requestJson<EstimatedTimeseriesPoint[]>("/api/orders/estimated-timeseries")
};

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
  latest_snapshot_date?: string | null;
  earliest_snapshot_date?: string | null;
};

export type AllocationRow = {
  label: string;
  kind: string;
  value_gbp: number;
  weight_pct: number;
  target_pct: number | null;
  drift_pct: number | null;
  is_concentration_risk: boolean;
  member_ids?: number[];
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
  snapshot_as_of_date: string | null;
  trailing_drip_yield_pct: number | null;
  delta_value_gbp_since_prev_snapshot: number | null;
  delta_quantity_since_prev_snapshot: number | null;
  peak_value_gbp: number | null;
  peak_last_price: number | null;
  drawdown_from_peak_pct: number | null;
  quantity_unchanged_snapshot_count: number | null;
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

export type OrderInstrumentRef = {
  id: number;
  security_name: string;
  identifier: string;
};

export type Order = {
  id: number;
  security_name: string;
  instrument_id: number | null;
  instrument: OrderInstrumentRef | null;
  order_date: string;
  order_status: string;
  account_name: string;
  side: string;
  quantity: number | null;
  cost_proceeds_gbp: number | null;
  country: string | null;
  is_drip: boolean;
  match_status: string | null;
  match_method: string | null;
  match_confidence: number | null;
  matched_at: string | null;
};

export type UnlinkedOrdersResponse = {
  count: number;
  orders: Order[];
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

// ---------------------------------------------------------------------------
// Matching admin types
// ---------------------------------------------------------------------------

export type MatchSummary = {
  orders_total: number;
  orders_matched: number;
  orders_unmatched: number;
  orders_auto_high: number;
  orders_auto_review: number;
  orders_manual: number;
  orders_ignored: number;
  orders_legacy: number;
  unmatched_groups: number;
  instruments_with_reconciliation_issues: number;
};

export type MatchCandidate = {
  instrument_id: number;
  security_name: string;
  score: number;
  method: string | null;
};

export type UnmatchedGroup = {
  group_key: string;
  source: string;
  account_name: string;
  canonical_account_name: string | null;
  security_name: string;
  normalised_name: string;
  order_count: number;
  first_order_date: string | null;
  last_order_date: string | null;
  net_quantity: number | null;
  buy_total_gbp: number | null;
  sell_total_gbp: number | null;
  candidate_count: number;
  best_candidate: MatchCandidate | null;
};

export type AccountAlias = {
  id: number;
  source: string;
  source_account_name: string;
  canonical_account_name: string;
  created_at: string;
  created_by: string | null;
  notes: string | null;
};

export type InstrumentAlias = {
  id: number;
  instrument_id: number;
  source: string;
  source_account_name: string | null;
  canonical_account_name: string | null;
  source_security_name: string;
  source_security_name_norm: string;
  alias_type: string;
  confidence: number | null;
  created_at: string;
  created_by: string | null;
  notes: string | null;
};

export type OrderMatchAudit = {
  id: number;
  order_id: number;
  old_instrument_id: number | null;
  new_instrument_id: number | null;
  old_status: string | null;
  new_status: string | null;
  method: string | null;
  confidence: number | null;
  evidence: Record<string, unknown> | null;
  changed_at: string;
  changed_by: string | null;
  reason: string | null;
};

export type ReconciliationRow = {
  instrument_id: number;
  security_name: string;
  account_name: string;
  is_closed: boolean;
  latest_snapshot_date: string | null;
  snapshot_quantity: number | null;
  order_derived_quantity: number | null;
  quantity_delta: number | null;
  snapshot_book_cost_gbp: number | null;
  order_net_cost_gbp: number | null;
  drip_total_gbp: number | null;
  buy_total_gbp: number | null;
  sell_total_gbp: number | null;
  unmatched_order_count: number;
  matched_order_count: number;
  match_status_summary: Record<string, number>;
  latest_value_gbp: number | null;
  status: string;
};

export type BackfillResult = {
  dry_run: boolean;
  orders_examined: number;
  would_auto_match: number;
  would_mark_review: number;
  would_remain_unmatched: number;
  actually_linked: number;
  examples: Array<Record<string, unknown>>;
};

export type CandidateDetail = {
  instrument_id: number;
  security_name: string;
  account_name: string;
  score: number;
  method: string | null;
  scores: Record<string, number>;
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

// ---------------------------------------------------------------------------
// CGT types
// ---------------------------------------------------------------------------

export type CGTMismatchEntry = {
  source: string;
  order_id?: number | null;
  order_date?: string | null;
  security_name?: string | null;
  quantity: number;
  cost: number;
  proceeds: number;
};

export type CGTSaleDetail = {
  order_id: number;
  order_date: string;
  quantity: number;
  proceeds_gbp: number;
  total_cost: number;
  realised_gain: number;
  matches: CGTMismatchEntry[];
  pool_quantity_before: number;
  pool_cost_before: number;
};

export type CGTTaxYearSummary = {
  tax_year: string;
  year_end: number;
  total_proceeds: number;
  total_cost: number;
  total_gain: number;
  total_loss: number;
  gain_count: number;
  loss_count: number;
};

export type CGTInstrumentSummary = {
  instrument_id: number;
  security_name: string;
  identifier: string;
  account_name: string;
  is_exempt: boolean;
  total_proceeds_gbp: number;
  total_cost_gbp: number;
  total_gain_gbp: number;
  total_loss_gbp: number;
  net_gain_gbp: number;
  tax_year_summaries: CGTTaxYearSummary[];
  sales: CGTSaleDetail[];
};

export type CGTTaxYearTotals = {
  tax_year: string;
  // Taxable (non-ISA) amounts
  taxable_proceeds: number;
  taxable_cost: number;
  taxable_gain: number;
  taxable_loss: number;
  // ISA-exempt amounts
  exempt_proceeds: number;
  exempt_cost: number;
  exempt_gain: number;
  exempt_loss: number;
  gain_count: number;
  loss_count: number;
  instrument_count: number;
  exempt_count: number;
};

export type CGTSummaryResponse = {
  instruments: CGTInstrumentSummary[];
  tax_year_totals: CGTTaxYearTotals[];
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
  getTimeseries: (accountName?: string | null) => {
    const params = new URLSearchParams();
    if (accountName) params.set("account_name", accountName);
    return requestJson<Array<{ as_of_date: string; total_value_gbp: number; total_book_cost_gbp: number }>>(`/api/portfolio/timeseries?${params.toString()}`);
  },
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
  importHlHoldingsCsv: async (file: File, asOfDate: string | null, force: boolean) => {
    const formData = new FormData();
    formData.append("file", file);
    if (asOfDate) formData.append("as_of_date", asOfDate);
    if (!asOfDate) formData.append("file_metadata_date", snapshotDateIsoFromFile(file));
    formData.append("force", String(force));
    return requestJson<{ batch: ImportBatch; summary: Record<string, unknown> }>("/api/imports/hl", {
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
  importHlOrdersCsv: async (file: File, dripThreshold: number, force: boolean) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("drip_threshold", String(dripThreshold));
    formData.append("force", String(force));
    return requestJson<OrderImportBatchOut>("/api/orders/import/hl", {
      method: "POST",
      body: formData
    });
  },
  getOrderAnalytics: (dripThreshold: number, accountName?: string | null) => {
    const params = new URLSearchParams();
    params.set("drip_threshold", String(dripThreshold));
    if (accountName) params.set("account_name", accountName);
    return requestJson<OrderAnalytics>(`/api/orders/analytics?${params.toString()}`);
  },
  getOrders: (dripThreshold: number) =>
    requestJson<Order[]>(`/api/orders?drip_threshold=${dripThreshold}&limit=500`),
  getUnlinkedOrders: (dripThreshold: number) =>
    requestJson<UnlinkedOrdersResponse>(
      `/api/orders/unlinked?drip_threshold=${dripThreshold}&limit=200`,
    ),
  getInstrumentOrders: (instrumentId: number, dripThreshold: number) =>
    requestJson<Order[]>(`/api/instruments/${instrumentId}/orders?drip_threshold=${dripThreshold}`),
  getCashflowTimeseries: (dripThreshold: number, accountName?: string | null) => {
    const params = new URLSearchParams();
    params.set("drip_threshold", String(dripThreshold));
    if (accountName) params.set("account_name", accountName);
    return requestJson<CashflowPoint[]>(`/api/orders/cashflow-timeseries?${params.toString()}`);
  },
  getOrderPositions: (dripThreshold: number) =>
    requestJson<PositionSummary[]>(`/api/orders/positions?drip_threshold=${dripThreshold}`),
  getEstimatedTimeseries: (accountName?: string | null) => {
    const params = new URLSearchParams();
    if (accountName) params.set("account_name", accountName);
    return requestJson<EstimatedTimeseriesPoint[]>(`/api/orders/estimated-timeseries?${params.toString()}`);
  },
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

  // Matching admin
  getMatchingSummary: () => requestJson<MatchSummary>("/api/matching/summary"),
  getUnmatchedGroups: (limit?: number, account?: string) => {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    if (account) params.set("account", account);
    return requestJson<UnmatchedGroup[]>(`/api/matching/unmatched-groups?${params.toString()}`);
  },
  getMatchingCandidates: (securityName: string, accountName: string) =>
    requestJson<{ candidates: CandidateDetail[] }>(
      `/api/matching/candidates?security_name=${encodeURIComponent(securityName)}&account_name=${encodeURIComponent(accountName)}`,
    ),
  resolveGroup: (body: { source: string; account_name: string; security_name: string; instrument_id: number; create_alias?: boolean; apply_to_existing_orders?: boolean; reason?: string }) =>
    requestJson<{ affected_orders: number }>("/api/matching/resolve-group", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  resolveOrder: (orderId: number, body: { instrument_id?: number | null; match_status?: string; reason?: string }) =>
    requestJson<{ order_id: number }>(`/api/matching/orders/${orderId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  unmatchOrder: (orderId: number) =>
    requestJson<{ order_id: number }>(`/api/matching/orders/${orderId}/unmatch`, {
      method: "POST",
    }),
  ignoreGroup: (body: { source: string; account_name: string; security_name: string; reason?: string }) =>
    requestJson<{ affected_orders: number }>("/api/matching/ignore-group", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  ignoreOrder: (orderId: number) =>
    requestJson<{ order_id: number }>(`/api/matching/orders/${orderId}/ignore`, {
      method: "POST",
    }),
  backfillMatching: (body: { mode?: string; dry_run?: boolean; min_auto_confidence?: number }) =>
    requestJson<BackfillResult>("/api/matching/backfill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getAccountAliases: () => requestJson<AccountAlias[]>("/api/matching/account-aliases"),
  createAccountAlias: (body: { source: string; source_account_name: string; canonical_account_name: string; notes?: string }) =>
    requestJson<AccountAlias>("/api/matching/account-aliases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteAccountAlias: async (aliasId: number): Promise<void> => {
    const response = await fetch(`/api/matching/account-aliases/${aliasId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await toError(response));
  },
  getInstrumentAliases: () => requestJson<InstrumentAlias[]>("/api/matching/instrument-aliases"),
  createInstrumentAlias: (body: { instrument_id: number; source: string; source_account_name?: string; canonical_account_name?: string; source_security_name: string; alias_type?: string; confidence?: number; notes?: string }) =>
    requestJson<InstrumentAlias>("/api/matching/instrument-aliases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  createHistoricalInstrument: (body: { security_name: string; account_name?: string; identifier?: string; closed?: boolean; reason?: string }) =>
    requestJson<{ instrument_id: number; identifier: string; security_name: string; affected_orders: number }>("/api/matching/create-instrument", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteInstrumentAlias: async (aliasId: number): Promise<void> => {
    const response = await fetch(`/api/matching/instrument-aliases/${aliasId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await toError(response));
  },
  getReconciliation: () => requestJson<ReconciliationRow[]>("/api/matching/reconciliation"),
  getAuditLog: (orderId?: number, instrumentId?: number, limit?: number) => {
    const params = new URLSearchParams();
    if (orderId != null) params.set("order_id", String(orderId));
    if (instrumentId != null) params.set("instrument_id", String(instrumentId));
    if (limit != null) params.set("limit", String(limit));
    return requestJson<OrderMatchAudit[]>(`/api/matching/audit?${params.toString()}`);
  },

  // CGT
  getCgtSummary: (accountName?: string | null) => {
    const params = new URLSearchParams();
    if (accountName) params.set("account_name", accountName);
    return requestJson<CGTSummaryResponse>(`/api/cgt/summary?${params.toString()}`);
  },
};

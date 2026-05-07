import { useState, useEffect, useCallback } from "react";
import { api, MatchSummary, UnmatchedGroup, CandidateDetail, ReconciliationRow, AccountAlias, InstrumentAlias, BackfillResult, Order } from "../lib/api";
import { Plus } from "lucide-react";
import { toGbp, formatOrderDate } from "../lib/formatters";
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Play,
  Eye,
  Link as LinkIcon,
  Trash2,
  ShieldAlert,
  Search,
  ChevronDown,
  ChevronUp,
  Info,
  Filter,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Summary cards
// ---------------------------------------------------------------------------

function SummaryCards({ summary }: { summary: MatchSummary | null }) {
  if (!summary) return null;

  const cards = [
    { label: "Total Orders", value: summary.orders_total, color: "text-white" },
    { label: "Matched", value: summary.orders_matched, color: "text-emerald-400" },
    { label: "Unmatched", value: summary.orders_unmatched, color: "text-amber-400" },
    { label: "Auto High", value: summary.orders_auto_high, color: "text-emerald-300" },
    { label: "Review", value: summary.orders_auto_review, color: "text-yellow-400" },
    { label: "Manual", value: summary.orders_manual, color: "text-violet-400" },
    { label: "Ignored", value: summary.orders_ignored, color: "text-slate-500" },
    { label: "Groups", value: summary.unmatched_groups, color: "text-amber-300" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3">
          <p className="text-[11px] text-slate-500 uppercase tracking-wider">{c.label}</p>
          <p className={`text-2xl font-bold mt-1 ${c.color}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Backfill controls
// ---------------------------------------------------------------------------

function BackfillControls() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BackfillResult | null>(null);
  const [mode, setMode] = useState("unmatched_only");

  const runDryRun = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.backfillMatching({ mode, dry_run: true });
      setResult(res);
    } catch (e) {
      console.error("Backfill dry-run failed", e);
    } finally {
      setLoading(false);
    }
  }, [mode]);

  const runActual = useCallback(async () => {
    if (!confirm("This will permanently update order matches. Continue?")) return;
    setLoading(true);
    try {
      const res = await api.backfillMatching({ mode, dry_run: false });
      setResult(res);
    } catch (e) {
      console.error("Backfill failed", e);
    } finally {
      setLoading(false);
    }
  }, [mode]);

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs text-slate-400">Mode:</label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="text-xs bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-slate-300"
        >
          <option value="unmatched_only">Unmatched only</option>
          <option value="review_only">Review only</option>
          <option value="all_non_manual">All non-manual</option>
          <option value="all">All (dangerous)</option>
        </select>

        <button
          onClick={runDryRun}
          disabled={loading}
          className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-violet-600/20 text-violet-300 hover:bg-violet-600/30 border border-violet-500/20"
        >
          <Play size={12} />
          Dry Run
        </button>

        <button
          onClick={runActual}
          disabled={loading}
          className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/20"
        >
          <RefreshCw size={12} />
          Apply
        </button>
      </div>

      {result && (
        <div className="mt-3 text-xs text-slate-400 space-y-1">
          <p>Examined: {result.orders_examined}</p>
          {result.dry_run ? (
            <>
              <p>Would auto-match: {result.would_auto_match}</p>
              <p>Would mark review: {result.would_mark_review}</p>
              <p>Would remain unmatched: {result.would_remain_unmatched}</p>
            </>
          ) : (
            <p>Linked: {result.actually_linked}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Unmatched groups table
// ---------------------------------------------------------------------------

function UnmatchedGroupsTable({ onRefresh }: { onRefresh: () => void }) {
  const [groups, setGroups] = useState<UnmatchedGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedGroup, setSelectedGroup] = useState<UnmatchedGroup | null>(null);
  const [candidates, setCandidates] = useState<CandidateDetail[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [search, setSearch] = useState("");
  const [creatingInstrument, setCreatingInstrument] = useState(false);
  const [newInstrumentName, setNewInstrumentName] = useState("");
  const [newInstrumentIdentifier, setNewInstrumentIdentifier] = useState("");
  const [newInstrumentClosed, setNewInstrumentClosed] = useState(true);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadGroups = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getUnmatchedGroups(200);
      setGroups(data);
    } catch (e) {
      console.error("Failed to load unmatched groups", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const loadCandidates = useCallback(async (group: UnmatchedGroup) => {
    setLoadingCandidates(true);
    try {
      const data = await api.getMatchingCandidates(group.security_name, group.account_name);
      setCandidates(data.candidates);
    } catch (e) {
      console.error("Failed to load candidates", e);
    } finally {
      setLoadingCandidates(false);
    }
  }, []);

  const handleResolve = useCallback(async (group: UnmatchedGroup, instrumentId: number) => {
    if (!confirm(`Match "${group.security_name}" to instrument ${instrumentId}? This will link ${group.order_count} orders.`)) return;
    setResolving(true);
    try {
      await api.resolveGroup({
        source: group.source,
        account_name: group.account_name,
        security_name: group.security_name,
        instrument_id: instrumentId,
        create_alias: true,
        apply_to_existing_orders: true,
        reason: "Admin resolution from Matching Admin",
      });
      setSelectedGroup(null);
      onRefresh();
      loadGroups();
    } catch (e) {
      console.error("Resolve failed", e);
      alert("Resolution failed: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setResolving(false);
    }
  }, [onRefresh, loadGroups]);

  const handleShowCreateForm = useCallback(() => {
    setCreatingInstrument(true);
    setNewInstrumentName(selectedGroup?.security_name || "");
    setNewInstrumentIdentifier("");
    setNewInstrumentClosed(true);
    setCreateError(null);
  }, [selectedGroup]);

  const handleCreateInstrument = useCallback(async () => {
    if (!newInstrumentName.trim()) {
      setCreateError("Security name is required");
      return;
    }
    setCreateError(null);
    setResolving(true);
    try {
      const result = await api.createHistoricalInstrument({
        security_name: newInstrumentName.trim(),
        account_name: selectedGroup?.account_name,
        identifier: newInstrumentIdentifier.trim() || undefined,
        closed: newInstrumentClosed,
        reason: "Created from Matching Admin for unmatched group",
      });
      setSelectedGroup(null);
      setCreatingInstrument(false);
      setNewInstrumentName("");
      setNewInstrumentIdentifier("");
      setNewInstrumentClosed(true);
      setCreateError(null);
      onRefresh();
      loadGroups();
    } catch (e) {
      console.error("Create instrument failed", e);
      setCreateError(e instanceof Error ? e.message : String(e));
    } finally {
      setResolving(false);
    }
  }, [selectedGroup, newInstrumentName, newInstrumentIdentifier, newInstrumentClosed, onRefresh, loadGroups]);

  const handleIgnore = useCallback(async (group: UnmatchedGroup) => {
    if (!confirm(`Ignore "${group.security_name}"? These ${group.order_count} orders will be excluded from unresolved counts.`)) return;
    setResolving(true);
    try {
      await api.ignoreGroup({
        source: group.source,
        account_name: group.account_name,
        security_name: group.security_name,
        reason: "Admin ignored from Matching Admin",
      });
      setSelectedGroup(null);
      onRefresh();
      loadGroups();
    } catch (e) {
      console.error("Ignore failed", e);
    } finally {
      setResolving(false);
    }
  }, [onRefresh, loadGroups]);

  const filtered = groups.filter((g) =>
    g.security_name.toLowerCase().includes(search.toLowerCase()) ||
    g.account_name.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <p className="text-sm text-slate-500">Loading unmatched groups...</p>;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Search size={14} className="text-slate-500" />
        <input
          type="text"
          placeholder="Search security or account..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-transparent text-sm text-slate-300 placeholder:text-slate-600 outline-none"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500 border-b border-white/[0.06]">
              <th className="pb-2 pr-4 font-medium">Security</th>
              <th className="pb-2 pr-4 font-medium">Account</th>
              <th className="pb-2 pr-4 font-medium text-right">Orders</th>
              <th className="pb-2 pr-4 font-medium text-right">Buy</th>
              <th className="pb-2 pr-4 font-medium text-right">Sell</th>
              <th className="pb-2 pr-4 font-medium">Best Candidate</th>
              <th className="pb-2 pr-4 font-medium text-right">Score</th>
              <th className="pb-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((group) => (
              <tr key={group.group_key} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                <td className="py-2 pr-4 text-slate-200 max-w-[200px] truncate" title={group.security_name}>
                  {group.security_name}
                </td>
                <td className="py-2 pr-4 text-slate-400">{group.account_name}</td>
                <td className="py-2 pr-4 text-right text-slate-300">{group.order_count}</td>
                <td className="py-2 pr-4 text-right text-emerald-400">{toGbp(group.buy_total_gbp)}</td>
                <td className="py-2 pr-4 text-right text-red-400">{toGbp(group.sell_total_gbp)}</td>
                <td className="py-2 pr-4 text-slate-400 max-w-[180px] truncate">
                  {group.best_candidate?.security_name || "—"}
                </td>
                <td className="py-2 pr-4 text-right">
                  {group.best_candidate?.score != null ? (
                    <span className={
                      group.best_candidate.score >= 0.92 ? "text-emerald-400" :
                      group.best_candidate.score >= 0.75 ? "text-yellow-400" :
                      "text-slate-500"
                    }>
                      {(group.best_candidate.score * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
                <td className="py-2">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => { setSelectedGroup(group); loadCandidates(group); }}
                      className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white"
                      title="Review candidates"
                    >
                      <Eye size={14} />
                    </button>
                    {group.best_candidate && (
                      <button
                        onClick={() => handleResolve(group, group.best_candidate!.instrument_id)}
                        disabled={resolving}
                        className="p-1 rounded hover:bg-emerald-600/20 text-emerald-400 hover:text-emerald-300"
                        title="Match to best candidate"
                      >
                        <LinkIcon size={14} />
                      </button>
                    )}
                    <button
                      onClick={() => handleIgnore(group)}
                      disabled={resolving}
                      className="p-1 rounded hover:bg-white/10 text-slate-500 hover:text-slate-300"
                      title="Ignore group"
                    >
                      <ShieldAlert size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Candidate review modal */}
      {selectedGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setSelectedGroup(null)}>
          <div
            className="w-full max-w-3xl max-h-[80vh] bg-slate-900 border border-white/[0.08] rounded-2xl overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
              <div>
                <h3 className="text-sm font-semibold text-white">{selectedGroup.security_name}</h3>
                <p className="text-xs text-slate-500 mt-0.5">{selectedGroup.order_count} orders · {selectedGroup.account_name}</p>
              </div>
              <button onClick={() => setSelectedGroup(null)} className="text-slate-500 hover:text-white">
                <XCircle size={20} />
              </button>
            </div>

            <div className="overflow-y-auto max-h-[60vh] p-5">
              {loadingCandidates ? (
                <p className="text-sm text-slate-500">Loading candidates...</p>
              ) : candidates.length === 0 ? (
                <p className="text-sm text-slate-500">No candidates found.</p>
              ) : (
                <div className="space-y-2">
                  {candidates.map((c) => (
                    <div
                      key={c.instrument_id}
                      className={`flex items-center justify-between rounded-lg border px-4 py-3 ${
                        c.score >= 0.92
                          ? "border-emerald-500/20 bg-emerald-500/5"
                          : c.score >= 0.75
                          ? "border-yellow-500/20 bg-yellow-500/5"
                          : "border-white/[0.06] bg-white/[0.02]"
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-slate-200 truncate">{c.security_name}</p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {c.account_name}
                          {c.is_closed ? " · closed" : ""}
                          {c.method ? ` · ${c.method}` : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 ml-4">
                        <span className={`text-sm font-mono font-bold ${
                          c.score >= 0.92 ? "text-emerald-400" :
                          c.score >= 0.75 ? "text-yellow-400" :
                          "text-slate-500"
                        }`}>
                          {(c.score * 100).toFixed(0)}%
                        </span>
                        <button
                          onClick={() => { handleResolve(selectedGroup, c.instrument_id); }}
                          disabled={resolving}
                          className="text-xs px-3 py-1.5 rounded-md bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/20"
                        >
                          Match
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Create new instrument form — inside scrollable area */}
              {creatingInstrument && (
                <div className="mt-4 pt-4 border-t border-white/[0.06] space-y-3">
                <p className="text-xs font-medium text-slate-300">Create new historical instrument</p>
                <div className="space-y-2">
                  <div>
                    <label className="text-[11px] text-slate-500">Security name</label>
                    <input
                      type="text"
                      value={newInstrumentName}
                      onChange={(e) => setNewInstrumentName(e.target.value)}
                      className="w-full bg-slate-900 border border-white/10 rounded-md px-3 py-1.5 text-xs text-slate-300 outline-none"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500">Identifier (optional — defaults to MANUAL:&lt;slug&gt;)</label>
                    <input
                      type="text"
                      value={newInstrumentIdentifier}
                      onChange={(e) => setNewInstrumentIdentifier(e.target.value)}
                      placeholder="e.g. TSLA, MANU:BIGYELLOW"
                      className="w-full bg-slate-900 border border-white/10 rounded-md px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 outline-none"
                    />
                  </div>
                  <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newInstrumentClosed}
                      onChange={(e) => setNewInstrumentClosed(e.target.checked)}
                      className="rounded border-white/20 bg-slate-900 text-aurora-cyan focus:ring-aurora-cyan"
                    />
                    Mark as closed (historical security)
                  </label>
                  {createError && (
                    <p className="text-xs text-red-400">{createError}</p>
                  )}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCreateInstrument}
                      disabled={resolving || !newInstrumentName.trim()}
                      className="text-xs px-3 py-1.5 rounded-md bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Create & Match
                    </button>
                    <button
                      onClick={() => { setCreatingInstrument(false); setCreateError(null); }}
                      className="text-xs px-3 py-1.5 rounded-md bg-white/5 text-slate-400 hover:bg-white/10 border border-white/10"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
              )}

              {candidates.length > 0 && (
                <div className="mt-4 text-[11px] text-slate-600">
                  Or create a new historical instrument below if this security is no longer in the portfolio.
                </div>
              )}
            </div>

            <div className="flex items-center justify-between px-5 py-3 border-t border-white/[0.06] bg-white/[0.02]">
              <div className="flex items-center gap-2">
                <button
                  onClick={handleShowCreateForm}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-violet-600/20 text-violet-300 hover:bg-violet-600/30 border border-violet-500/20"
                  >
                    <Plus size={12} />
                    New Instrument
                  </button>
                <button
                  onClick={() => { setSelectedGroup(null); handleIgnore(selectedGroup); }}
                  disabled={resolving || creatingInstrument}
                  className="text-xs px-3 py-1.5 rounded-md bg-white/5 text-slate-400 hover:bg-white/10 border border-white/10"
                >
                  Ignore Group
                </button>
              </div>
              <button
                onClick={() => { setSelectedGroup(null); setCreatingInstrument(false); setCreateError(null); }}
                className="text-xs px-3 py-1.5 rounded-md bg-white/5 text-slate-400 hover:bg-white/10 border border-white/10"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reconciliation table
// ---------------------------------------------------------------------------

function ReconciliationTable() {
  const [rows, setRows] = useState<ReconciliationRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getReconciliation().then(setRows).finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-sm text-slate-500">Loading reconciliation data...</p>;

  const statusColor = (status: string) => {
    if (status === "ok") return "text-emerald-400";
    if (status === "unmatched_orders") return "text-amber-400";
    if (status === "quantity_mismatch") return "text-red-400";
    return "text-slate-500";
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-slate-500 border-b border-white/[0.06]">
            <th className="pb-2 pr-4 font-medium">Instrument</th>
            <th className="pb-2 pr-4 font-medium text-right">Snap Qty</th>
            <th className="pb-2 pr-4 font-medium text-right">Order Qty</th>
            <th className="pb-2 pr-4 font-medium text-right">Δ Qty</th>
            <th className="pb-2 pr-4 font-medium text-right">Snap Cost</th>
            <th className="pb-2 pr-4 font-medium text-right">Order Cost</th>
            <th className="pb-2 pr-4 font-medium text-right">Matched</th>
            <th className="pb-2 pr-4 font-medium text-right">Unmatched</th>
            <th className="pb-2 font-medium text-right">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.instrument_id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
              <td className="py-2 pr-4 text-slate-200 max-w-[200px] truncate" title={r.security_name}>
                {r.security_name}
                {r.is_closed ? " <span className='text-slate-600 text-[10px]'>closed</span>" : ""}
              </td>
              <td className="py-2 pr-4 text-right text-slate-300">{r.snapshot_quantity ?? "—"}</td>
              <td className="py-2 pr-4 text-right text-slate-300">{r.order_derived_quantity != null ? r.order_derived_quantity.toFixed(1) : "—"}</td>
              <td className={`py-2 pr-4 text-right ${r.quantity_delta && Math.abs(r.quantity_delta) > 1 ? "text-amber-400" : "text-slate-400"}`}>
                {r.quantity_delta != null ? r.quantity_delta.toFixed(1) : "—"}
              </td>
              <td className="py-2 pr-4 text-right text-slate-400">{toGbp(r.snapshot_book_cost_gbp)}</td>
              <td className="py-2 pr-4 text-right text-slate-400">{toGbp(r.order_net_cost_gbp)}</td>
              <td className="py-2 pr-4 text-right text-slate-300">{r.matched_order_count}</td>
              <td className={`py-2 pr-4 text-right ${r.unmatched_order_count > 0 ? "text-amber-400" : "text-slate-400"}`}>
                {r.unmatched_order_count}
              </td>
              <td className={`py-2 text-right font-medium ${statusColor(r.status)}`}>
                {r.status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Aliases tab
// ---------------------------------------------------------------------------

function AliasesTab() {
  const [accountAliases, setAccountAliases] = useState<AccountAlias[]>([]);
  const [instrumentAliases, setInstrumentAliases] = useState<InstrumentAlias[]>([]);
  const [loading, setLoading] = useState(true);
  const [newAlias, setNewAlias] = useState({ source: "barclays_orders", source_account_name: "", canonical_account_name: "" });

  useEffect(() => {
    Promise.all([api.getAccountAliases(), api.getInstrumentAliases()])
      .then(([acct, inst]) => { setAccountAliases(acct); setInstrumentAliases(inst); })
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async () => {
    if (!newAlias.source_account_name || !newAlias.canonical_account_name) return;
    try {
      await api.createAccountAlias(newAlias);
      setAccountAliases(await api.getAccountAliases());
      setNewAlias({ source: "barclays_orders", source_account_name: "", canonical_account_name: "" });
    } catch (e) {
      console.error("Failed to create alias", e);
    }
  };

  const handleDelete = async (id: number) => {
    await api.deleteAccountAlias(id);
    setAccountAliases(await api.getAccountAliases());
  };

  if (loading) return <p className="text-sm text-slate-500">Loading aliases...</p>;

  return (
    <div className="space-y-6">
      {/* Account aliases */}
      <div>
        <h4 className="text-sm font-semibold text-slate-300 mb-2">Account Aliases</h4>

        <div className="flex items-center gap-2 mb-3">
          <input
            type="text"
            placeholder="Source account name"
            value={newAlias.source_account_name}
            onChange={(e) => setNewAlias({ ...newAlias, source_account_name: e.target.value })}
            className="flex-1 bg-slate-900 border border-white/10 rounded-md px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 outline-none"
          />
          <span className="text-slate-600 text-xs">→</span>
          <input
            type="text"
            placeholder="Canonical account name"
            value={newAlias.canonical_account_name}
            onChange={(e) => setNewAlias({ ...newAlias, canonical_account_name: e.target.value })}
            className="flex-1 bg-slate-900 border border-white/10 rounded-md px-3 py-1.5 text-xs text-slate-300 placeholder:text-slate-600 outline-none"
          />
          <button
            onClick={handleCreate}
            className="text-xs px-3 py-1.5 rounded-md bg-violet-600/20 text-violet-300 hover:bg-violet-600/30 border border-violet-500/20"
          >
            Add
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 border-b border-white/[0.06]">
                <th className="pb-2 pr-4 font-medium">Source</th>
                <th className="pb-2 pr-4 font-medium">From</th>
                <th className="pb-2 pr-4 font-medium">To</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {accountAliases.map((a) => (
                <tr key={a.id} className="border-b border-white/[0.03]">
                  <td className="py-2 pr-4 text-slate-400">{a.source}</td>
                  <td className="py-2 pr-4 text-slate-300">{a.source_account_name}</td>
                  <td className="py-2 pr-4 text-slate-300">{a.canonical_account_name}</td>
                  <td className="py-2">
                    <button
                      onClick={() => handleDelete(a.id)}
                      className="p-1 rounded hover:bg-red-600/20 text-slate-500 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Instrument aliases */}
      <div>
        <h4 className="text-sm font-semibold text-slate-300 mb-2">Instrument Aliases ({instrumentAliases.length})</h4>
        <div className="overflow-x-auto max-h-60 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 border-b border-white/[0.06] sticky top-0 bg-slate-950">
                <th className="pb-2 pr-4 font-medium">Source Name</th>
                <th className="pb-2 pr-4 font-medium">Account</th>
                <th className="pb-2 pr-4 font-medium">Type</th>
                <th className="pb-2 pr-4 font-medium">Source</th>
                <th className="pb-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {instrumentAliases.map((a) => (
                <tr key={a.id} className="border-b border-white/[0.03]">
                  <td className="py-2 pr-4 text-slate-300 max-w-[200px] truncate">{a.source_security_name}</td>
                  <td className="py-2 pr-4 text-slate-400">{a.source_account_name || "—"}</td>
                  <td className="py-2 pr-4 text-slate-400">{a.alias_type}</td>
                  <td className="py-2 pr-4 text-slate-400">{a.source}</td>
                  <td className="py-2">
                    <button
                      onClick={async () => { await api.deleteInstrumentAlias(a.id); setInstrumentAliases(await api.getInstrumentAliases()); }}
                      className="p-1 rounded hover:bg-red-600/20 text-slate-500 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit tab
// ---------------------------------------------------------------------------

function AuditTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAuditLog(undefined, undefined, 200).then(setLogs).finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-sm text-slate-500">Loading audit log...</p>;

  return (
    <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-slate-500 border-b border-white/[0.06] sticky top-0 bg-slate-950">
            <th className="pb-2 pr-4 font-medium">Time</th>
            <th className="pb-2 pr-4 font-medium">By</th>
            <th className="pb-2 pr-4 font-medium">Order</th>
            <th className="pb-2 pr-4 font-medium">Old Status</th>
            <th className="pb-2 pr-4 font-medium">New Status</th>
            <th className="pb-2 pr-4 font-medium">Method</th>
            <th className="pb-2 font-medium">Reason</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id} className="border-b border-white/[0.03]">
              <td className="py-2 pr-4 text-slate-400">{formatOrderDate(l.changed_at)}</td>
              <td className="py-2 pr-4 text-slate-400">{l.changed_by || "—"}</td>
              <td className="py-2 pr-4 text-slate-300">#{l.order_id}</td>
              <td className="py-2 pr-4 text-slate-400">{l.old_status || "—"}</td>
              <td className={`py-2 pr-4 ${
                l.new_status === "auto_high" ? "text-emerald-400" :
                l.new_status === "manual" ? "text-violet-400" :
                l.new_status === "ignored" ? "text-slate-500" :
                l.new_status === "unmatched" ? "text-amber-400" :
                "text-slate-300"
              }`}>{l.new_status || "—"}</td>
              <td className="py-2 pr-4 text-slate-400">{l.method || "—"}</td>
              <td className="py-2 pr-4 text-slate-500 max-w-[200px] truncate">{l.reason || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Matched orders tab
// ---------------------------------------------------------------------------

function MatchedOrdersTab() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    api.getOrders(1000).then(setOrders).finally(() => setLoading(false));
  }, []);

  const filtered = orders.filter((o) => {
    if (statusFilter !== "all" && o.match_status !== statusFilter) return false;
    if (search && !o.security_name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const statusBadge = (status: string | null) => {
    const colors: Record<string, string> = {
      auto_high: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      auto_review: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
      manual: "bg-violet-500/10 text-violet-400 border-violet-500/20",
      ignored: "bg-slate-500/10 text-slate-500 border-slate-500/20",
      unmatched: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      legacy_matched: "bg-slate-500/10 text-slate-400 border-slate-500/20",
    };
    const cls = colors[status || ""] || "bg-slate-500/10 text-slate-400 border-slate-500/20";
    return (
      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${cls}`}>
        {status || "—"}
      </span>
    );
  };

  if (loading) return <p className="text-sm text-slate-500">Loading orders...</p>;

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Search size={14} className="text-slate-500" />
          <input
            type="text"
            placeholder="Search security..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent text-xs text-slate-300 placeholder:text-slate-600 outline-none w-48"
          />
        </div>
        <Filter size={14} className="text-slate-500" />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="text-xs bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-slate-300"
        >
          <option value="all">All statuses</option>
          <option value="auto_high">Auto High</option>
          <option value="auto_review">Auto Review</option>
          <option value="manual">Manual</option>
          <option value="ignored">Ignored</option>
          <option value="unmatched">Unmatched</option>
          <option value="legacy_matched">Legacy</option>
        </select>
        <span className="text-xs text-slate-500">{filtered.length} orders</span>
      </div>

      <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500 border-b border-white/[0.06] sticky top-0 bg-slate-950">
              <th className="pb-2 pr-4 font-medium">Date</th>
              <th className="pb-2 pr-4 font-medium">Security</th>
              <th className="pb-2 pr-4 font-medium">Account</th>
              <th className="pb-2 pr-4 font-medium">Side</th>
              <th className="pb-2 pr-4 font-medium text-right">Qty</th>
              <th className="pb-2 pr-4 font-medium text-right">Cost/Proceeds</th>
              <th className="pb-2 pr-4 font-medium">Status</th>
              <th className="pb-2 pr-4 font-medium">Method</th>
              <th className="pb-2 font-medium text-right">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((o) => (
              <tr key={o.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                <td className="py-2 pr-4 text-slate-400">{formatOrderDate(o.order_date)}</td>
                <td className="py-2 pr-4 text-slate-200 max-w-[200px] truncate" title={o.security_name}>
                  {o.security_name}
                </td>
                <td className="py-2 pr-4 text-slate-400">{o.account_name}</td>
                <td className={`py-2 pr-4 ${o.side === "Buy" ? "text-emerald-400" : "text-red-400"}`}>
                  {o.side}
                </td>
                <td className="py-2 pr-4 text-right text-slate-300">{o.quantity ?? "—"}</td>
                <td className="py-2 pr-4 text-right text-slate-300">{toGbp(o.cost_proceeds_gbp)}</td>
                <td className="py-2 pr-4">{statusBadge(o.match_status)}</td>
                <td className="py-2 pr-4 text-slate-400">{o.match_method || "—"}</td>
                <td className="py-2 text-right">
                  {o.match_confidence != null
                    ? <span className={
                        o.match_confidence >= 0.92 ? "text-emerald-400" :
                        o.match_confidence >= 0.75 ? "text-yellow-400" :
                        "text-slate-500"
                      }> {(o.match_confidence * 100).toFixed(0)}%</span>
                    : <span className="text-slate-600">—</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main MatchingAdmin page
// ---------------------------------------------------------------------------

type TabKey = "unmatched" | "matched" | "reconciliation" | "aliases" | "audit";

export function MatchingAdmin() {
  const [summary, setSummary] = useState<MatchSummary | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("unmatched");
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
    api.getMatchingSummary().then(setSummary);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const tabs: { key: TabKey; label: string; icon: any }[] = [
    { key: "unmatched", label: "Unmatched Groups", icon: AlertTriangle },
    { key: "matched", label: "Matched Orders", icon: CheckCircle2 },
    { key: "reconciliation", label: "Reconciliation", icon: Info },
    { key: "aliases", label: "Aliases", icon: LinkIcon },
    { key: "audit", label: "Audit Log", icon: RefreshCw },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-white">Matching Admin</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Review how imported orders are linked to instruments and resolve unmatched securities.
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-white/5 text-slate-400 hover:bg-white/10 border border-white/10"
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      {/* Summary cards */}
      <SummaryCards summary={summary} />

      {/* Backfill controls */}
      <BackfillControls />

      {/* Warning if unmatched */}
      {summary && summary.orders_unmatched > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
          <AlertTriangle size={16} className="mt-0.5 text-amber-400 shrink-0" />
          <div>
            <p className="text-xs text-amber-300/90">
              {summary.orders_unmatched} orders are currently unmatched. Position cost basis may be incomplete.
            </p>
            <p className="text-[11px] text-amber-400/60 mt-0.5">
              Resolve unmatched groups above to improve matching accuracy.
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-white/[0.06]">
        <div className="flex gap-0">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-aurora-cyan text-white"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              <tab.icon size={13} />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div key={refreshKey}>
        {activeTab === "unmatched" && <UnmatchedGroupsTable onRefresh={refresh} />}
        {activeTab === "matched" && <MatchedOrdersTab />}
        {activeTab === "reconciliation" && <ReconciliationTable />}
        {activeTab === "aliases" && <AliasesTab />}
        {activeTab === "audit" && <AuditTab />}
      </div>
    </div>
  );
}

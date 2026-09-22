import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Link, Upload } from "lucide-react";
import {
  api,
  formatSnapshotDateIso,
  snapshotDateIsoFromFile,
} from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { SegmentedControl, type Segment } from "./SegmentedControl";

type Tab = "portfolio" | "orders";
type BrokerSource = "barclays" | "hl";

export function ImportPanel() {
  const queryClient = useQueryClient();
  const { dripThreshold } = usePreferences();
  const [tab, setTab] = useState<Tab>("portfolio");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [asOfDate, setAsOfDate] = useState("");
  const [forceImport, setForceImport] = useState(false);
  const [portfolioSource, setPortfolioSource] = useState<BrokerSource>("barclays");

  const [orderFile, setOrderFile] = useState<File | null>(null);
  const [forceOrderImport, setForceOrderImport] = useState(false);
  const [orderSource, setOrderSource] = useState<BrokerSource>("barclays");

  const { data: trading212Status } = useQuery({
    queryKey: ["trading212Status"],
    queryFn: api.getTrading212Status,
  });

  const { data: syncStatus } = useQuery({
    queryKey: ["syncStatus"],
    queryFn: api.getSyncStatus,
  });

  const syncAll = useMutation({
    mutationFn: () => api.syncAll(true),
    onSuccess: () => queryClient.invalidateQueries(),
    onError: () => queryClient.invalidateQueries({ queryKey: ["syncStatus"] }),
  });

  const syncTrading212 = useMutation({
    mutationFn: () => api.syncTrading212(forceImport),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const snapshotPreview = useMemo(() => {
    if (!selectedFile) return null;
    if (asOfDate.trim()) {
      return {
        mode: "override" as const,
        label: formatSnapshotDateIso(asOfDate.trim()),
      };
    }
    const iso = snapshotDateIsoFromFile(selectedFile);
    return { mode: "file" as const, label: formatSnapshotDateIso(iso) };
  }, [selectedFile, asOfDate]);

  const importMutation = useMutation({
    mutationFn: () =>
      portfolioSource === "hl"
        ? api.importHlHoldingsCsv(selectedFile as File, asOfDate || null, forceImport)
        : api.importXls(selectedFile as File, asOfDate || null, forceImport),
    onSuccess: () => {
      setSelectedFile(null);
      setAsOfDate("");
      queryClient.invalidateQueries();
    },
  });

  const importOrdersMutation = useMutation({
    mutationFn: () =>
      orderSource === "hl"
        ? api.importHlOrdersCsv(orderFile as File, dripThreshold, forceOrderImport)
        : api.importOrderXls(orderFile as File, dripThreshold, forceOrderImport),
    onSuccess: () => {
      setOrderFile(null);
      queryClient.invalidateQueries();
    },
  });


  const segments: Segment<Tab>[] = [
    { key: "portfolio", label: "Portfolio snapshot" },
    { key: "orders", label: "Order history" },
  ];

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-5 flex items-center gap-2">
        <Upload size={16} className="text-aurora-cyan" />
        <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-300">
          Import data
        </h3>
      </div>

      <SegmentedControl
        layoutId="import-tab"
        value={tab}
        onChange={setTab}
        tone={tab === "portfolio" ? "accent" : "amber"}
        segments={segments}
      />

      {tab === "portfolio" ? (
        <div className="mt-5 space-y-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Upload a portfolio snapshot. The snapshot date is where this
            import appears on charts and instrument history.
          </p>

          <SourceSelect
            value={portfolioSource}
            onChange={(source) => {
              setPortfolioSource(source);
              setSelectedFile(null);
            }}
          />

          <FileDrop
            file={selectedFile}
            onChange={setSelectedFile}
            tone="accent"
            accept={portfolioSource === "hl" ? ".csv" : ".xls"}
          />

          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Snapshot date override
            </label>
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
            />
          </div>

          {snapshotPreview && (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                Will be dated
              </p>
              <p className="mt-0.5 text-sm font-semibold text-aurora-cyan">
                {snapshotPreview.label}
              </p>
            </div>
          )}

          <CheckboxRow
            checked={forceImport}
            onChange={setForceImport}
            label="Force re-import if already exists"
          />

          <button
            type="button"
            onClick={() => importMutation.mutate()}
            disabled={!selectedFile || importMutation.isPending}
            className="btn-primary w-full"
          >
            {importMutation.isPending
              ? "Importing…"
              : `Import ${portfolioSource === "hl" ? "HL CSV" : "Barclays XLS"} snapshot`}
          </button>

          {importMutation.isError && (
            <p className="text-xs text-neg">
              {(importMutation.error as Error).message}
            </p>
          )}
          {importMutation.isSuccess && (
            <div className="space-y-1">
              <p className="flex items-center gap-1 text-xs text-pos">
                <CheckCircle2 size={12} />
                Import complete.
              </p>
              {importMutation.data?.summary && (
                <ImportSummary summary={importMutation.data.summary} />
              )}
            </div>
          )}



        </div>
      ) : (
        <div className="mt-5 space-y-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Import your order history. Buys below the DRIP threshold
            (
            <span className="tabular text-amber-300">
              {toGbp(dripThreshold)}
            </span>
            ) are treated as dividend reinvestments. Adjust the threshold from
            the topbar.
          </p>

          <SourceSelect
            value={orderSource}
            onChange={(source) => {
              setOrderSource(source);
              setOrderFile(null);
            }}
          />

          <FileDrop
            file={orderFile}
            onChange={setOrderFile}
            tone="amber"
            accept={orderSource === "hl" ? ".csv" : ".xls"}
          />

          <CheckboxRow
            checked={forceOrderImport}
            onChange={setForceOrderImport}
            label="Force re-import if already exists"
          />

          <button
            type="button"
            onClick={() => importOrdersMutation.mutate()}
            disabled={!orderFile || importOrdersMutation.isPending}
            className="btn-amber w-full"
          >
            {importOrdersMutation.isPending
              ? "Importing…"
              : `Import ${orderSource === "hl" ? "HL CSV" : "Barclays XLS"} order history`}
          </button>

          {importOrdersMutation.isError && (
            <p className="text-xs text-neg">
              {(importOrdersMutation.error as Error).message}
            </p>
          )}
          {importOrdersMutation.isSuccess && (
            <p className="flex items-center gap-1 text-xs text-pos">
              <CheckCircle2 size={12} />
              Imported {importOrdersMutation.data?.row_count} orders.
            </p>
          )}

        </div>
      )}
      <section aria-labelledby="sync-all-heading" className="mt-5 border-t border-white/[0.06] pt-4">
        <h3 id="sync-all-heading" className="text-sm font-medium text-slate-200">Sync all accounts</h3>
        <p className="my-2 text-xs text-slate-400">
          Downloads the latest Hargreaves Lansdown and Barclays exports, imports them by content,
          then refreshes Trading 212. Read-only: it never deals or moves money, and repeating a
          sync does not duplicate records.
        </p>
        {syncStatus && syncStatus.accounts.length > 0 && (
          <ul className="mb-2 space-y-1 text-xs" aria-label="Account freshness">
            {syncStatus.accounts.map((a) => (
              <li key={a.account_name} className="flex justify-between gap-2">
                <span className="truncate text-slate-300">{a.account_name}</span>
                <span className={a.stale ? "text-amber-400" : "text-slate-400"}>
                  {a.last_snapshot_date ?? "never"}
                  {a.age_days != null && ` (${a.age_days === 0 ? "today" : `${a.age_days}d ago`})`}
                  {a.stale && " · stale"}
                </span>
              </li>
            ))}
          </ul>
        )}
        {syncStatus && !syncStatus.manual_sync_enabled && (
          <p className="text-xs text-slate-400">
            Syncs automatically on weekdays at 18:30.
            {syncStatus.last_run && ` Last run ${new Date(syncStatus.last_run.started_at).toLocaleString("en-GB")}: `}
            {syncStatus.last_run?.steps.map((s) => `${s.name} ${s.status.replace("_", " ")}`).join(" · ")}
          </p>
        )}
        {syncStatus?.manual_sync_enabled && (
        <button type="button" className="btn-primary flex w-full items-center justify-center gap-2"
          onClick={() => syncAll.mutate()}
          disabled={syncAll.isPending || syncStatus?.running}>
          <Download size={16} />
          {syncAll.isPending || syncStatus?.running ? "Syncing all accounts…" : "Sync all accounts"}
        </button>
        )}
        {syncAll.isSuccess && (
          <ul role="status" className="mt-2 space-y-0.5 text-xs">
            {syncAll.data.steps.map((step) => (
              <li key={step.name} className={
                step.status === "failed" || step.status === "needs_attention" ? "text-neg"
                  : step.status === "ok" ? "text-pos" : "text-slate-400"}>
                {step.name}: {step.status.replace("_", " ")}{step.detail ? ` — ${step.detail}` : ""}
              </li>
            ))}
          </ul>
        )}
        {syncAll.isError && <p role="alert" className="mt-2 text-xs text-neg">
          {(syncAll.error as Error).message}
        </p>}
      </section>
      <section className="mt-5 border-t border-white/[0.06] pt-4">
        <h3 className="text-sm font-medium text-slate-200">Trading 212</h3>
        <p className="my-2 text-xs text-slate-400">
          One read-only sync refreshes the current portfolio, completed fills and deposits/withdrawals.
          It does not place trades or move money.
        </p>
        <button type="button" className="btn-primary flex w-full items-center justify-center gap-2"
          onClick={() => syncTrading212.mutate()}
          disabled={!trading212Status?.configured || syncTrading212.isPending}>
          <Download size={16} />
          {syncTrading212.isPending ? "Syncing Trading 212…" : "Sync Trading 212"}
        </button>
        {trading212Status && !trading212Status.configured && (
          <p className="mt-1 text-xs text-amber-400">Add the Trading 212 credentials to .env to enable sync.</p>
        )}
        {syncTrading212.isSuccess && <p role="status" className="mt-2 text-xs text-pos">
          Snapshot: {syncTrading212.data.snapshot}; orders: {syncTrading212.data.orders};
          cash: {syncTrading212.data.cash_flows_imported} new / {syncTrading212.data.cash_flows_total} total.
          Re-syncing is safe and does not duplicate records.
        </p>}
        {syncTrading212.isError && <p role="alert" className="mt-2 text-xs text-neg">
          {(syncTrading212.error as Error).message}
        </p>}
      </section>
    </div>
  );
}

function FileDrop({
  file,
  onChange,
  tone,
  accept,
}: {
  file: File | null;
  onChange: (file: File | null) => void;
  tone: "accent" | "amber";
  accept: ".xls" | ".csv";
}) {
  const hover =
    tone === "accent"
      ? "hover:border-aurora-cyan/50"
      : "hover:border-amber-400/50";
  const iconHover =
    tone === "accent"
      ? "group-hover:text-aurora-cyan"
      : "group-hover:text-amber-300";
  return (
    <label
      className={`group flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-white/[0.1] bg-white/[0.02] p-3 transition-colors ${hover}`}
    >
      <FileSpreadsheet
        size={20}
        className={`shrink-0 text-slate-500 transition-colors ${iconHover}`}
      />
      <span className="min-w-0 flex-1 truncate text-sm text-slate-300">
        {file?.name ?? `Choose ${accept} file`}
      </span>
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}

function SourceSelect({
  value,
  onChange,
}: {
  value: BrokerSource;
  onChange: (value: BrokerSource) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        Source
      </label>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as BrokerSource)}
        className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
      >
        <option value="barclays">Barclays XLS</option>
        <option value="hl">HL CSV</option>
      </select>
    </div>
  );
}

function CheckboxRow({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-slate-400">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-aurora-cyan"
      />
      {label}
    </label>
  );
}

function ImportSummary({ summary }: { summary: Record<string, unknown> }) {
  const ordersLinked = summary.orders_linked as number | undefined;
  const closed = summary.closed as Array<Record<string, unknown>> | undefined;
  const changed = summary.changed as Array<Record<string, unknown>> | undefined;
  const newIds = summary.new_instrument_ids as number[] | undefined;

  if (!ordersLinked && !closed && !changed && !newIds) return null;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 space-y-1">
      {ordersLinked != null && ordersLinked > 0 && (
        <p className="text-[11px] text-emerald-400">
          <Link size={10} className="inline mr-1" />
          {ordersLinked} orders linked to instruments
        </p>
      )}
      {newIds && newIds.length > 0 && (
        <p className="text-[11px] text-slate-400">
          {newIds.length} new instruments detected
        </p>
      )}
      {closed && closed.length > 0 && (
        <p className="text-[11px] text-amber-400">
          <AlertTriangle size={10} className="inline mr-1" />
          {closed.length} instruments closed
        </p>
      )}
      {changed && changed.length > 0 && (
        <p className="text-[11px] text-slate-400">
          {changed.length} instruments changed
        </p>
      )}
    </div>
  );
}

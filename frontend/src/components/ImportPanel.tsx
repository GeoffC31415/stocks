import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileSpreadsheet } from "lucide-react";
import {
  api,
  formatSnapshotDateIso,
  snapshotDateIsoFromFile,
} from "../lib/api";
import { toGbp } from "../lib/formatters";

export function ImportPanel({
  dripThreshold,
  dripInput,
  setDripInput,
  onApplyDrip,
}: {
  dripThreshold: number;
  dripInput: string;
  setDripInput: (v: string) => void;
  onApplyDrip: () => void;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"portfolio" | "orders">("portfolio");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [asOfDate, setAsOfDate] = useState("");
  const [forceImport, setForceImport] = useState(false);

  const [orderFile, setOrderFile] = useState<File | null>(null);
  const [forceOrderImport, setForceOrderImport] = useState(false);

  const snapshotPreview = useMemo(() => {
    if (!selectedFile) return null;
    if (asOfDate.trim()) {
      return { mode: "override" as const, label: formatSnapshotDateIso(asOfDate.trim()) };
    }
    const iso = snapshotDateIsoFromFile(selectedFile);
    return { mode: "file" as const, label: formatSnapshotDateIso(iso) };
  }, [selectedFile, asOfDate]);

  const importMutation = useMutation({
    mutationFn: () =>
      api.importXls(selectedFile as File, asOfDate || null, forceImport),
    onSuccess: () => {
      setSelectedFile(null);
      setAsOfDate("");
      queryClient.invalidateQueries();
    },
  });

  const importOrdersMutation = useMutation({
    mutationFn: () =>
      api.importOrderXls(orderFile as File, dripThreshold, forceOrderImport),
    onSuccess: () => {
      setOrderFile(null);
      queryClient.invalidateQueries();
    },
  });

  const tabButton = (
    key: "portfolio" | "orders",
    label: string,
    activeColor: string,
  ) => (
    <button
      type="button"
      className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
        tab === key
          ? `${activeColor} text-white shadow-sm`
          : "text-slate-400 hover:text-slate-200"
      }`}
      onClick={() => setTab(key)}
    >
      {label}
    </button>
  );

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-5 flex items-center gap-2">
        <Upload size={16} className="text-slate-400" />
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Import data
        </h3>
      </div>

      <div className="mb-4 flex gap-1 rounded-lg border border-slate-700 bg-slate-900/60 p-1">
        {tabButton("portfolio", "Portfolio snapshot", "bg-cyan-600")}
        {tabButton("orders", "Order history", "bg-amber-600")}
      </div>

      {tab === "portfolio" ? (
        <div className="space-y-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Upload a Barclays portfolio XLS. The snapshot date is where this
            import appears on charts and instrument history.
          </p>

          <label className="group flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-slate-600 bg-slate-900/40 p-3 transition hover:border-cyan-500/50">
            <FileSpreadsheet size={20} className="shrink-0 text-slate-500 group-hover:text-cyan-400" />
            <span className="min-w-0 flex-1 truncate text-sm text-slate-400">
              {selectedFile?.name ?? "Choose .xls file"}
            </span>
            <input
              type="file"
              accept=".xls"
              className="hidden"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Snapshot date override
            </label>
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
            />
          </div>

          {snapshotPreview && (
            <div className="rounded-lg border border-slate-600/60 bg-slate-900/50 px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Will be dated
              </p>
              <p className="mt-0.5 text-sm font-semibold text-cyan-300">
                {snapshotPreview.label}
              </p>
            </div>
          )}

          <label className="flex items-center gap-2 text-xs text-slate-400">
            <input
              type="checkbox"
              checked={forceImport}
              onChange={(e) => setForceImport(e.target.checked)}
              className="accent-cyan-500"
            />
            Force re-import if already exists
          </label>

          <button
            type="button"
            onClick={() => importMutation.mutate()}
            disabled={!selectedFile || importMutation.isPending}
            className="btn-primary w-full"
          >
            {importMutation.isPending ? "Importing…" : "Import snapshot"}
          </button>

          {importMutation.isError && (
            <p className="text-xs text-rose-400">
              {(importMutation.error as Error).message}
            </p>
          )}
          {importMutation.isSuccess && (
            <p className="text-xs text-emerald-400">Import complete.</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Import your Barclays order history. Buys below the DRIP threshold
            are treated as dividend reinvestments.
          </p>

          <label className="group flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-slate-600 bg-slate-900/40 p-3 transition hover:border-amber-500/50">
            <FileSpreadsheet size={20} className="shrink-0 text-slate-500 group-hover:text-amber-400" />
            <span className="min-w-0 flex-1 truncate text-sm text-slate-400">
              {orderFile?.name ?? "Choose .xls file"}
            </span>
            <input
              type="file"
              accept=".xls"
              className="hidden"
              onChange={(e) => setOrderFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              DRIP threshold (£)
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                min="0"
                step="100"
                value={dripInput}
                onChange={(e) => setDripInput(e.target.value)}
                className="flex-1 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={onApplyDrip}
                className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
              >
                Apply
              </button>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Buys below this amount are classified as DRIP. Currently{" "}
              <span className="text-amber-300">{toGbp(dripThreshold)}</span>.
            </p>
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-400">
            <input
              type="checkbox"
              checked={forceOrderImport}
              onChange={(e) => setForceOrderImport(e.target.checked)}
              className="accent-amber-500"
            />
            Force re-import if already exists
          </label>

          <button
            type="button"
            onClick={() => importOrdersMutation.mutate()}
            disabled={!orderFile || importOrdersMutation.isPending}
            className="btn-amber w-full"
          >
            {importOrdersMutation.isPending
              ? "Importing…"
              : "Import order history"}
          </button>

          {importOrdersMutation.isError && (
            <p className="text-xs text-rose-400">
              {(importOrdersMutation.error as Error).message}
            </p>
          )}
          {importOrdersMutation.isSuccess && (
            <p className="text-xs text-emerald-400">
              Imported {importOrdersMutation.data?.row_count} orders.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

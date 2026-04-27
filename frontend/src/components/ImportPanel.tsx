import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import {
  api,
  formatSnapshotDateIso,
  snapshotDateIsoFromFile,
} from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { SegmentedControl, type Segment } from "./SegmentedControl";

type Tab = "portfolio" | "orders";

export function ImportPanel() {
  const queryClient = useQueryClient();
  const { dripThreshold } = usePreferences();
  const [tab, setTab] = useState<Tab>("portfolio");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [asOfDate, setAsOfDate] = useState("");
  const [forceImport, setForceImport] = useState(false);

  const [orderFile, setOrderFile] = useState<File | null>(null);
  const [forceOrderImport, setForceOrderImport] = useState(false);

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
            Upload a Barclays portfolio XLS. The snapshot date is where this
            import appears on charts and instrument history.
          </p>

          <FileDrop
            file={selectedFile}
            onChange={setSelectedFile}
            tone="accent"
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
            {importMutation.isPending ? "Importing…" : "Import snapshot"}
          </button>

          {importMutation.isError && (
            <p className="text-xs text-neg">
              {(importMutation.error as Error).message}
            </p>
          )}
          {importMutation.isSuccess && (
            <p className="flex items-center gap-1 text-xs text-pos">
              <CheckCircle2 size={12} />
              Import complete.
            </p>
          )}
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          <p className="text-xs leading-relaxed text-slate-500">
            Import your Barclays order history. Buys below the DRIP threshold
            (
            <span className="tabular text-amber-300">
              {toGbp(dripThreshold)}
            </span>
            ) are treated as dividend reinvestments. Adjust the threshold from
            the topbar.
          </p>

          <FileDrop file={orderFile} onChange={setOrderFile} tone="amber" />

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
              : "Import order history"}
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
    </div>
  );
}

function FileDrop({
  file,
  onChange,
  tone,
}: {
  file: File | null;
  onChange: (file: File | null) => void;
  tone: "accent" | "amber";
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
        {file?.name ?? "Choose .xls file"}
      </span>
      <input
        type="file"
        accept=".xls"
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </label>
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

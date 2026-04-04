import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, formatSnapshotDateIso, snapshotDateIsoFromFile, type Group, type Instrument } from "./lib/api";

const toGbp = (value: number | null | undefined): string =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 2
  }).format(value ?? 0);

const pct = (value: number | null | undefined): string => `${(value ?? 0).toFixed(2)}%`;

function App() {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [forceImport, setForceImport] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [selectedInstrument, setSelectedInstrument] = useState<number | null>(null);

  const summaryQuery = useQuery({ queryKey: ["summary"], queryFn: api.getSummary });
  const timeseriesQuery = useQuery({ queryKey: ["timeseries"], queryFn: api.getTimeseries });
  const instrumentsQuery = useQuery({ queryKey: ["instruments"], queryFn: api.getInstruments });
  const importsQuery = useQuery({ queryKey: ["imports"], queryFn: api.getImports });
  const groupsQuery = useQuery({ queryKey: ["groups"], queryFn: api.getGroups });

  const instrumentHistoryQuery = useQuery({
    queryKey: ["instrument-history", selectedInstrument],
    queryFn: () => api.getInstrumentHistory(selectedInstrument as number),
    enabled: selectedInstrument !== null
  });

  const importSnapshotPreview = useMemo(() => {
    if (!selectedFile) return null;
    if (asOfDate.trim()) {
      return {
        mode: "override" as const,
        iso: asOfDate.trim(),
        label: formatSnapshotDateIso(asOfDate.trim())
      };
    }
    const iso = snapshotDateIsoFromFile(selectedFile);
    return { mode: "file" as const, iso, label: formatSnapshotDateIso(iso) };
  }, [selectedFile, asOfDate]);

  const importMutation = useMutation({
    mutationFn: () => api.importXls(selectedFile as File, asOfDate || null, forceImport),
    onSuccess: () => {
      setSelectedFile(null);
      setAsOfDate("");
      queryClient.invalidateQueries();
    }
  });

  const createGroupMutation = useMutation({
    mutationFn: () => api.createGroup(newGroupName.trim(), null),
    onSuccess: () => {
      setNewGroupName("");
      queryClient.invalidateQueries({ queryKey: ["groups"] });
    }
  });

  const updateGroupMembers = useMutation({
    mutationFn: ({ group, members }: { group: Group; members: number[] }) =>
      api.replaceGroupMembers(group.id, members),
    onSuccess: () => queryClient.invalidateQueries()
  });

  const loading =
    summaryQuery.isLoading ||
    timeseriesQuery.isLoading ||
    instrumentsQuery.isLoading ||
    groupsQuery.isLoading ||
    importsQuery.isLoading;

  const instruments = instrumentsQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const byGroup = useMemo(() => {
    const grouped: Record<number, Instrument[]> = {};
    for (const group of groups) {
      grouped[group.id] = instruments.filter((instrument) => instrument.group_ids.includes(group.id));
    }
    return grouped;
  }, [groups, instruments]);

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-white">Portfolio tracker</h1>
        <p className="mt-2 text-slate-300">
          Barclays XLS snapshots with trend charts, grouped holdings, and performance alerts.
        </p>
      </header>

      {loading ? (
        <section className="glass rounded-xl p-6">Loading data...</section>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-3">
            <Card label="Portfolio value" value={toGbp(summaryQuery.data?.total_value_gbp)} />
            <Card label="Book cost" value={toGbp(summaryQuery.data?.total_book_cost_gbp)} />
            <Card
              label="Portfolio P&L"
              value={toGbp(summaryQuery.data?.total_pnl_gbp)}
              valueClass={(summaryQuery.data?.total_pnl_gbp ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"}
            />
          </section>

          <section className="mt-6 grid gap-6 lg:grid-cols-5">
            <div className="glass rounded-xl p-4 lg:col-span-3">
              <h2 className="text-lg font-semibold text-white">Portfolio value over time</h2>
              <p className="mb-3 text-xs text-slate-500">Horizontal axis: snapshot date from each import (see import panel).</p>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={timeseriesQuery.data ?? []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="as_of_date" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="total_value_gbp" stroke="#22d3ee" name="Value (GBP)" />
                    <Line type="monotone" dataKey="total_book_cost_gbp" stroke="#a78bfa" name="Book Cost (GBP)" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass rounded-xl p-4 lg:col-span-2">
              <h2 className="mb-2 text-lg font-semibold text-white">Import Barclays file</h2>
              <p className="mb-3 text-xs leading-relaxed text-slate-400">
                Each upload is one portfolio snapshot. The snapshot date is where this import appears on the chart
                and in per-instrument history.
              </p>
              <div className="space-y-3">
                <input
                  type="file"
                  accept=".xls"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                  className="w-full rounded-md border border-slate-600 bg-slate-900 p-2"
                />
                <div>
                  <label htmlFor="snapshot-date-override" className="mb-1 block text-sm font-medium text-slate-200">
                    Snapshot date override
                  </label>
                  <input
                    id="snapshot-date-override"
                    type="date"
                    value={asOfDate}
                    onChange={(event) => setAsOfDate(event.target.value)}
                    className="w-full rounded-md border border-slate-600 bg-slate-900 p-2"
                  />
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
                    Leave empty to use the file&apos;s <span className="text-slate-400">last modified</span> date in
                    your local timezone.
                  </p>
                </div>
                {importSnapshotPreview ? (
                  <div className="rounded-lg border border-slate-600/80 bg-slate-900/70 px-3 py-2.5">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      This import will be dated
                    </p>
                    <p className="mt-1 text-base font-semibold text-cyan-200">{importSnapshotPreview.label}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {importSnapshotPreview.mode === "override"
                        ? "You set this manually; it overrides the file timestamp."
                        : "Derived from the file’s last-modified metadata on your device."}
                    </p>
                  </div>
                ) : null}
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={forceImport}
                    onChange={(event) => setForceImport(event.target.checked)}
                  />
                  Force import even if file hash already exists
                </label>
                <button
                  type="button"
                  onClick={() => importMutation.mutate()}
                  disabled={!selectedFile || importMutation.isPending}
                  className="w-full rounded-md bg-cyan-500 px-3 py-2 font-medium text-slate-950 disabled:cursor-not-allowed disabled:bg-slate-600"
                >
                  {importMutation.isPending ? "Importing..." : "Import snapshot"}
                </button>
                {importMutation.isError ? (
                  <p className="text-sm text-rose-300">{(importMutation.error as Error).message}</p>
                ) : null}
                {importMutation.isSuccess ? <p className="text-sm text-emerald-300">Import complete.</p> : null}
              </div>
            </div>
          </section>

          <section className="mt-6 grid gap-6 lg:grid-cols-2">
            <div className="glass rounded-xl p-4">
              <h2 className="mb-3 text-lg font-semibold text-white">Poor performers</h2>
              <ul className="space-y-2">
                {(summaryQuery.data?.worst_pct ?? []).map((row) => (
                  <li key={row.id} className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-2">
                    <span className="mr-3 truncate text-sm">{row.security_name}</span>
                    <span className="text-rose-300">{pct(row.latest_pct_change)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="glass rounded-xl p-4">
              <h2 className="mb-3 text-lg font-semibold text-white">Strong performers</h2>
              <ul className="space-y-2">
                {(summaryQuery.data?.best_pct ?? []).map((row) => (
                  <li key={row.id} className="flex items-center justify-between rounded-md bg-slate-900/60 px-3 py-2">
                    <span className="mr-3 truncate text-sm">{row.security_name}</span>
                    <span className="text-emerald-300">{pct(row.latest_pct_change)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="mt-6 grid gap-6 lg:grid-cols-5">
            <div className="glass overflow-hidden rounded-xl lg:col-span-3">
              <div className="border-b border-slate-700 px-4 py-3">
                <h2 className="text-lg font-semibold text-white">Holdings</h2>
              </div>
              <div className="max-h-[420px] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-900">
                    <tr className="text-left text-slate-300">
                      <th className="px-4 py-3">Instrument</th>
                      <th className="px-4 py-3">Value</th>
                      <th className="px-4 py-3">P&L</th>
                      <th className="px-4 py-3">% Chg</th>
                    </tr>
                  </thead>
                  <tbody>
                    {instruments.map((instrument) => (
                      <tr
                        key={instrument.id}
                        className="cursor-pointer border-t border-slate-800 hover:bg-slate-800/40"
                        onClick={() => setSelectedInstrument(instrument.id)}
                      >
                        <td className="px-4 py-2">
                          <div className="font-medium text-white">{instrument.identifier}</div>
                          <div className="text-xs text-slate-400">{instrument.security_name}</div>
                        </td>
                        <td className="px-4 py-2">{toGbp(instrument.latest_value_gbp)}</td>
                        <td
                          className={`px-4 py-2 ${
                            (instrument.pnl_gbp ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"
                          }`}
                        >
                          {toGbp(instrument.pnl_gbp)}
                        </td>
                        <td
                          className={`px-4 py-2 ${
                            (instrument.latest_pct_change ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"
                          }`}
                        >
                          {pct(instrument.latest_pct_change)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="glass rounded-xl p-4 lg:col-span-2">
              <h2 className="mb-3 text-lg font-semibold text-white">Instrument history</h2>
              {selectedInstrument === null ? (
                <p className="text-slate-300">Select an instrument in the table to show history.</p>
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={instrumentHistoryQuery.data ?? []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="as_of_date" stroke="#94a3b8" />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip />
                      <Line type="monotone" dataKey="value_gbp" stroke="#22d3ee" name="Value (GBP)" />
                      <Line type="monotone" dataKey="book_cost_gbp" stroke="#a78bfa" name="Book (GBP)" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </section>

          <section className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="glass rounded-xl p-4 lg:col-span-2">
              <h2 className="mb-3 text-lg font-semibold text-white">Groups</h2>
              <div className="mb-4 flex gap-2">
                <input
                  value={newGroupName}
                  onChange={(event) => setNewGroupName(event.target.value)}
                  placeholder="New group name"
                  className="flex-1 rounded-md border border-slate-600 bg-slate-900 p-2"
                />
                <button
                  type="button"
                  className="rounded-md bg-violet-500 px-3 py-2 font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-600"
                  onClick={() => createGroupMutation.mutate()}
                  disabled={!newGroupName.trim() || createGroupMutation.isPending}
                >
                  Add group
                </button>
              </div>
              <div className="space-y-3">
                {groups.map((group) => (
                  <GroupEditor
                    key={group.id}
                    group={group}
                    instruments={instruments}
                    current={byGroup[group.id] ?? []}
                    onSave={(members) => updateGroupMembers.mutate({ group, members })}
                  />
                ))}
              </div>
            </div>

            <div className="glass rounded-xl p-4">
              <h2 className="mb-3 text-lg font-semibold text-white">Import history</h2>
              <ul className="space-y-2">
                {(importsQuery.data ?? []).slice(0, 12).map((entry) => (
                  <li key={entry.id} className="rounded-md bg-slate-900/60 p-3">
                    <div className="text-xs text-slate-400">
                      Batch #{entry.id} · {entry.as_of_date}
                    </div>
                    <div className="truncate text-sm">{entry.filename ?? "unknown.xls"}</div>
                    <div className="text-xs text-slate-300">
                      Rows: {entry.diff_summary?.row_count ?? 0}, New:{" "}
                      {entry.diff_summary?.new_instrument_ids?.length ?? 0}, Closed:{" "}
                      {entry.diff_summary?.closed?.length ?? 0}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function Card({
  label,
  value,
  valueClass
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <article className="glass rounded-xl p-4">
      <p className="text-sm text-slate-300">{label}</p>
      <p className={`mt-2 text-2xl font-semibold text-white ${valueClass ?? ""}`}>{value}</p>
    </article>
  );
}

function GroupEditor({
  group,
  instruments,
  current,
  onSave
}: {
  group: Group;
  instruments: Instrument[];
  current: Instrument[];
  onSave: (members: number[]) => void;
}) {
  const [selected, setSelected] = useState<number[]>(current.map((instrument) => instrument.id));

  return (
    <div className="rounded-md border border-slate-700 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-medium text-white">
          {group.name} · {toGbp(group.total_value_gbp)}
        </h3>
        <button
          type="button"
          className="rounded bg-cyan-600 px-2 py-1 text-xs font-medium"
          onClick={() => onSave(selected)}
        >
          Save members
        </button>
      </div>
      <div className="max-h-40 overflow-auto rounded bg-slate-900/60 p-2">
        {instruments.filter((instrument) => !instrument.is_cash).map((instrument) => (
          <label key={instrument.id} className="flex items-center gap-2 py-1 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(instrument.id)}
              onChange={(event) =>
                setSelected((previous) =>
                  event.target.checked
                    ? [...previous, instrument.id]
                    : previous.filter((id) => id !== instrument.id)
                )
              }
            />
            <span className="truncate">{instrument.identifier}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

export default App;

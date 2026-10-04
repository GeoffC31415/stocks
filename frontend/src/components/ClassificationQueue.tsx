import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, Loader2, Tags } from "lucide-react";
import { api, type Instrument } from "../lib/api";

const ASSET_CLASSES = [
  "",
  "Equity",
  "Equity ETF",
  "Bond",
  "Bond ETF",
  "Fund",
  "Cash",
  "Other",
];

const clean = (value: string): string | null => value.trim() || null;
const complete = (instrument: Instrument) =>
  Boolean(instrument.ticker && instrument.asset_class && instrument.sector && instrument.region);

function ClassificationRow({ instrument }: { instrument: Instrument }) {
  const queryClient = useQueryClient();
  const [ticker, setTicker] = useState(instrument.ticker ?? "");
  const [assetClass, setAssetClass] = useState(instrument.asset_class ?? "");
  const [sector, setSector] = useState(instrument.sector ?? "");
  const [region, setRegion] = useState(instrument.region ?? "");

  useEffect(() => {
    setTicker(instrument.ticker ?? "");
    setAssetClass(instrument.asset_class ?? "");
    setSector(instrument.sector ?? "");
    setRegion(instrument.region ?? "");
  }, [instrument]);

  const save = useMutation({
    mutationFn: () =>
      api.updateInstrumentMarket(instrument.id, {
        ticker: clean(ticker),
        asset_class: clean(assetClass),
        sector: clean(sector),
        region: clean(region),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instruments"] }),
  });

  const fieldClass =
    "min-w-0 w-full min-h-9 rounded-lg border border-white/[0.07] bg-aurora-base/70 px-2.5 text-xs text-slate-200 placeholder:text-slate-700 focus:border-aurora-cyan/60 focus:outline-none";

  return (
    <div className="min-w-0 rounded-xl border border-white/[0.05] bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 max-w-full break-words [overflow-wrap:anywhere]">
          <p className="font-medium text-white">{instrument.identifier}</p>
          <p className="truncate text-xs text-slate-500" title={instrument.security_name}>
            {instrument.security_name}
          </p>
          <p className="mt-0.5 text-[10px] text-slate-600">{instrument.account_name}</p>
        </div>
        {complete(instrument) ? (
          <span className="chip chip-muted text-emerald-300">
            <CheckCircle2 size={12} /> Complete
          </span>
        ) : null}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <label className="min-w-0 grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
          Ticker
          <input
            aria-label={`Ticker for ${instrument.identifier}`}
            className={fieldClass}
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            placeholder="e.g. EQQQ.L"
          />
        </label>
        <label className="min-w-0 grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
          Asset class
          <select
            aria-label={`Asset class for ${instrument.identifier}`}
            className={fieldClass}
            value={assetClass}
            onChange={(event) => setAssetClass(event.target.value)}
          >
            {ASSET_CLASSES.map((option) => (
              <option key={option || "blank"} value={option}>
                {option || "Choose…"}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0 grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
          Sector
          <input
            aria-label={`Sector for ${instrument.identifier}`}
            className={fieldClass}
            value={sector}
            onChange={(event) => setSector(event.target.value)}
            placeholder="e.g. Technology"
          />
        </label>
        <label className="min-w-0 grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
          Region
          <input
            aria-label={`Region for ${instrument.identifier}`}
            className={fieldClass}
            value={region}
            onChange={(event) => setRegion(event.target.value)}
            placeholder="e.g. Global"
          />
        </label>
      </div>

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          aria-label={`Save ${instrument.identifier}`}
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="btn-primary min-w-20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending ? <Loader2 size={14} className="animate-spin" /> : "Save"}
        </button>
      </div>
      {save.isError ? (
        <p className="mt-2 text-right text-xs text-neg">Could not save this classification.</p>
      ) : null}
    </div>
  );
}

type ClassificationDraft = { asset_class: string; sector: string; region: string };
type SortKey = "holding" | "account_name" | "asset_class" | "sector" | "region" | "status";
type SortDirection = "ascending" | "descending";

const draftFor = (instrument: Instrument): ClassificationDraft => ({
  asset_class: instrument.asset_class ?? "",
  sector: instrument.sector ?? "",
  region: instrument.region ?? "",
});

const changedFields = (instrument: Instrument, draft: ClassificationDraft) => {
  const original = draftFor(instrument);
  const patch: { asset_class?: string | null; sector?: string | null; region?: string | null } = {};
  for (const key of ["asset_class", "sector", "region"] as const) {
    if (clean(draft[key]) !== clean(original[key])) patch[key] = clean(draft[key]);
  }
  return patch;
};

export function ClassificationQueue() {
  const queryClient = useQueryClient();
  const instrumentsQ = useQuery({ queryKey: ["instruments"], queryFn: () => api.getInstruments() });
  const [filter, setFilter] = useState("");
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, ClassificationDraft>>({});
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "holding",
    direction: "ascending",
  });
  const [saveSummary, setSaveSummary] = useState<{ message: string; failed: boolean } | null>(null);
  const open = useMemo(
    () => (instrumentsQ.data ?? []).filter((instrument) => !instrument.closed_at && !instrument.is_cash),
    [instrumentsQ.data],
  );
  const incomplete = open.filter((instrument) => !complete(instrument));
  const completeCount = open.length - incomplete.length;
  const existingClassifications = open.filter(
    (instrument) => Boolean(instrument.asset_class && instrument.sector && instrument.region),
  );
  const normalizedFilter = filter.trim().toLocaleLowerCase();
  const filteredClassifications = existingClassifications.filter((instrument) =>
    [instrument.identifier, instrument.security_name, instrument.account_name]
      .some((value) => value.toLocaleLowerCase().includes(normalizedFilter)),
  );
  const dirtyRows = existingClassifications.flatMap((instrument) => {
    const draft = drafts[instrument.id] ?? draftFor(instrument);
    const patch = changedFields(instrument, draft);
    return Object.keys(patch).length ? [{ instrument, draft, patch }] : [];
  });
  const invalidRows = existingClassifications.filter((instrument) => {
    const draft = drafts[instrument.id] ?? draftFor(instrument);
    return !draft.asset_class.trim() || !draft.sector.trim() || !draft.region.trim();
  });

  const save = useMutation({
    mutationFn: async (rows: typeof dirtyRows) => {
      const savedIds: number[] = [];
      const failedIds: number[] = [];
      for (const row of rows) {
        try {
          await api.updateInstrumentMarket(row.instrument.id, row.patch);
          savedIds.push(row.instrument.id);
        } catch {
          failedIds.push(row.instrument.id);
        }
      }
      return { savedIds, failedIds };
    },
    onSuccess: ({ savedIds, failedIds }) => {
      setDrafts((current) => {
        const next = { ...current };
        savedIds.forEach((id) => delete next[id]);
        return next;
      });
      setSaveSummary({
        message: failedIds.length
          ? `${savedIds.length} saved; ${failedIds.length} could not be saved. Review the highlighted changes and try again.`
          : `${savedIds.length} classification${savedIds.length === 1 ? "" : "s"} saved.`,
        failed: failedIds.length > 0,
      });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["instruments"] }),
  });

  const sortBy = (key: SortKey) => {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === "ascending" ? "descending" : "ascending" }
      : { key, direction: "ascending" });
  };
  const sortedClassifications = [...filteredClassifications].sort((a, b) => {
    const draftA = drafts[a.id] ?? draftFor(a);
    const draftB = drafts[b.id] ?? draftFor(b);
    const isDirtyA = Object.keys(changedFields(a, draftA)).length > 0;
    const isDirtyB = Object.keys(changedFields(b, draftB)).length > 0;
    const valueA = sort.key === "holding"
      ? `${a.identifier} ${a.security_name}`
      : sort.key === "account_name" ? a.account_name
        : sort.key === "status" ? (isDirtyA ? "Changed" : "Unchanged") : draftA[sort.key];
    const valueB = sort.key === "holding"
      ? `${b.identifier} ${b.security_name}`
      : sort.key === "account_name" ? b.account_name
        : sort.key === "status" ? (isDirtyB ? "Changed" : "Unchanged") : draftB[sort.key];
    const comparison = valueA.localeCompare(valueB, undefined, { sensitivity: "base", numeric: true });
    return (sort.direction === "ascending" ? comparison : -comparison) || a.id - b.id;
  });

  const sortButton = (key: SortKey, label: string) => {
    const selected = sort.key === key;
    const direction = selected ? sort.direction : undefined;
    return (
      <th scope="col" aria-sort={direction} className="whitespace-nowrap px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
        <button
          type="button"
          aria-label={`Sort by ${label}${direction ? `, ${direction}` : ""}`}
          onClick={() => sortBy(key)}
          className="inline-flex min-h-9 items-center gap-1.5 rounded px-1 text-left hover:text-white focus:outline-none focus:ring-2 focus:ring-aurora-cyan/60"
        >
          {label}
          {selected ? <span aria-hidden="true">{direction === "ascending" ? "↑" : "↓"}</span> : <span aria-hidden="true" className="text-slate-600">↕</span>}
        </button>
      </th>
    );
  };

  const fieldClass = "min-w-28 w-full rounded-lg border border-white/10 bg-aurora-base/70 px-2.5 py-2 text-sm text-slate-100 focus:border-aurora-cyan/60 focus:outline-none";
  const assetClassOptions = (current: string, original: string) =>
    [...new Set([...ASSET_CLASSES.filter(Boolean), original, current].filter(Boolean))];

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Tags size={18} className="text-aurora-cyan" />
              <h1 className="text-2xl font-semibold text-white">Classification queue</h1>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              Review metadata used for allocation analysis. Nothing is inferred automatically.
            </p>
          </div>
          <span className="chip chip-muted tabular">
            {completeCount}/{open.length} open instruments complete
          </span>
        </div>

        {instrumentsQ.isLoading ? (
          <div className="glass flex min-h-48 items-center justify-center rounded-2xl text-sm text-slate-500">
            <Loader2 size={18} className="mr-2 animate-spin" /> Loading instruments…
          </div>
        ) : incomplete.length === 0 ? (
          <div className="glass rounded-2xl p-8 text-center">
            <CheckCircle2 size={24} className="mx-auto text-emerald-300" />
            <p className="mt-2 text-sm text-slate-300">All open instruments are classified.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {incomplete.map((instrument) => (
              <ClassificationRow key={instrument.id} instrument={instrument} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4" aria-labelledby="existing-classifications-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="existing-classifications-heading" className="text-xl font-semibold text-white">
              Edit existing classifications
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Edit cells, sort any column to group similar values, then save all changes together.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="chip chip-muted tabular">
              {existingClassifications.length} classified holding{existingClassifications.length === 1 ? "" : "s"}
            </span>
            {dirtyRows.length > 0 ? (
              <span className="text-sm font-medium text-amber-200">{dirtyRows.length} unsaved</span>
            ) : null}
            <button
              type="button"
              aria-expanded={isEditorOpen}
              aria-controls="existing-classifications-editor"
              aria-label={`${isEditorOpen ? "Hide" : "Show"} classification editor`}
              onClick={() => setIsEditorOpen((open) => !open)}
              className="btn-secondary inline-flex min-h-10 min-w-32 items-center justify-center gap-1.5"
            >
              {isEditorOpen ? "Hide editor" : "Edit classifications"}
              <ChevronDown size={15} aria-hidden="true" className={`shrink-0 transition-transform ${isEditorOpen ? "rotate-180" : ""}`} />
            </button>
          </div>
        </div>

        {isEditorOpen ? (
          <div id="existing-classifications-editor" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label className="grid w-full max-w-xl gap-1 text-xs text-slate-400">
                Find a holding
                <input
                  aria-label="Find a holding to edit"
                  className="min-h-10 rounded-lg border border-white/[0.07] bg-aurora-base/70 px-3 text-sm text-slate-200 placeholder:text-slate-600 focus:border-aurora-cyan/60 focus:outline-none"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Search identifier, name, or account"
                />
              </label>
              <button
                type="button"
                disabled={dirtyRows.length === 0 || invalidRows.length > 0 || save.isPending}
                onClick={() => { setSaveSummary(null); save.mutate(dirtyRows); }}
                className="btn-primary min-h-10 min-w-36 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {save.isPending ? <><Loader2 size={14} className="mr-2 inline animate-spin" />Saving…</> : `Save changes (${dirtyRows.length})`}
              </button>
            </div>
            {invalidRows.length > 0 ? (
              <>
                <p role="alert" className="text-sm font-medium text-red-300">
                  Class, Sector, and Region are required for every row before saving.
                </p>
                {saveSummary?.failed ? (
                  <p role="alert" className="text-sm text-neg">{saveSummary.message}</p>
                ) : null}
              </>
            ) : dirtyRows.length > 0 ? (
              <>
                <p role="status" className="text-sm font-medium text-amber-200">
                  {dirtyRows.length} unsaved row{dirtyRows.length === 1 ? "" : "s"} — changed cells highlighted in amber
                </p>
                {saveSummary?.failed ? (
                  <p role="alert" className="text-sm text-neg">{saveSummary.message}</p>
                ) : null}
              </>
            ) : saveSummary ? (
              <p role={saveSummary.failed ? "alert" : "status"} className={`text-sm ${saveSummary.failed ? "text-neg" : "text-emerald-200"}`}>{saveSummary.message}</p>
            ) : null}

            {instrumentsQ.isLoading ? null : existingClassifications.length === 0 ? (
              <div className="glass rounded-2xl p-6 text-center text-sm text-slate-500">
                No open holdings have a complete classification yet.
              </div>
            ) : filteredClassifications.length === 0 ? (
              <div className="glass rounded-2xl p-6 text-center text-sm text-slate-500">
                No classified holdings match that search.
              </div>
            ) : (
              <div role="region" aria-label="Existing classifications table" tabIndex={0} className="max-w-full overflow-x-auto rounded-xl border border-white/[0.08] focus:outline-none focus:ring-2 focus:ring-aurora-cyan/40">
                <table aria-label="Existing classifications" className="w-full min-w-[920px] border-collapse text-sm">
                  <thead className="bg-white/[0.04]">
                    <tr>
                      {sortButton("holding", "Holding")}
                      {sortButton("account_name", "Account")}
                      {sortButton("asset_class", "Class")}
                      {sortButton("sector", "Sector")}
                      {sortButton("region", "Region")}
                      {sortButton("status", "Status")}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {sortedClassifications.map((instrument) => {
                      const draft = drafts[instrument.id] ?? draftFor(instrument);
                      const changes = changedFields(instrument, draft);
                      const isDirty = Object.keys(changes).length > 0;
                      const cellClass = (field: keyof ClassificationDraft) =>
                        `px-3 py-2.5 ${field in changes ? "bg-amber-400/[0.09]" : ""}`;
                      const inputClass = (field: keyof ClassificationDraft) =>
                        `${fieldClass} ${field in changes ? "border-amber-300/80 bg-amber-400/[0.14]" : ""} ${!draft[field].trim() ? "border-red-400 bg-red-500/[0.08]" : ""}`;
                      return (
                        <tr key={instrument.id}>
                          <th scope="row" className="min-w-64 px-3 py-3 text-left">
                            <p className="font-medium text-white">{instrument.identifier}</p>
                            <p className="max-w-xs truncate text-xs font-normal text-slate-500" title={instrument.security_name}>{instrument.security_name}</p>
                            {isDirty ? <span className="mt-1 inline-flex rounded-full border border-amber-300/50 bg-amber-300/15 px-2 py-0.5 text-[11px] font-semibold text-amber-100">Changed</span> : null}
                          </th>
                          <td className="whitespace-nowrap px-3 py-3 text-slate-300">{instrument.account_name}</td>
                          <td className={cellClass("asset_class")}>
                            <select aria-label={`Class for ${instrument.identifier}`} aria-invalid={!draft.asset_class.trim()} required className={inputClass("asset_class")} disabled={save.isPending} value={draft.asset_class} onChange={(event) => { setSaveSummary(null); setDrafts((current) => ({ ...current, [instrument.id]: { ...draft, asset_class: event.target.value } })); }}>
                              {assetClassOptions(draft.asset_class, instrument.asset_class ?? "").map((option) => <option key={option || "blank"} value={option}>{option || "Choose…"}</option>)}
                            </select>
                          </td>
                          <td className={cellClass("sector")}>
                            <input aria-label={`Sector for ${instrument.identifier}`} aria-invalid={!draft.sector.trim()} required className={inputClass("sector")} disabled={save.isPending} value={draft.sector} onChange={(event) => { setSaveSummary(null); setDrafts((current) => ({ ...current, [instrument.id]: { ...draft, sector: event.target.value } })); }} />
                          </td>
                          <td className={cellClass("region")}>
                            <input aria-label={`Region for ${instrument.identifier}`} aria-invalid={!draft.region.trim()} required className={inputClass("region")} disabled={save.isPending} value={draft.region} onChange={(event) => { setSaveSummary(null); setDrafts((current) => ({ ...current, [instrument.id]: { ...draft, region: event.target.value } })); }} />
                          </td>
                          <td className="whitespace-nowrap px-3 py-3">
                            {isDirty ? <span className="text-xs font-medium text-amber-200">Unsaved</span> : <span className="text-xs text-slate-600">—</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

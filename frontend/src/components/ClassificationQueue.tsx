import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Tags } from "lucide-react";
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
    "min-h-9 rounded-lg border border-white/[0.07] bg-aurora-base/70 px-2.5 text-xs text-slate-200 placeholder:text-slate-700 focus:border-aurora-cyan/60 focus:outline-none";

  return (
    <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
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
        <label className="grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
          Ticker
          <input
            aria-label={`Ticker for ${instrument.identifier}`}
            className={fieldClass}
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            placeholder="e.g. EQQQ.L"
          />
        </label>
        <label className="grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
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
        <label className="grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
          Sector
          <input
            aria-label={`Sector for ${instrument.identifier}`}
            className={fieldClass}
            value={sector}
            onChange={(event) => setSector(event.target.value)}
            placeholder="e.g. Technology"
          />
        </label>
        <label className="grid gap-1 text-[10px] uppercase tracking-wider text-slate-500">
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

export function ClassificationQueue() {
  const instrumentsQ = useQuery({ queryKey: ["instruments"], queryFn: api.getInstruments });
  const open = useMemo(
    () => (instrumentsQ.data ?? []).filter((instrument) => !instrument.closed_at && !instrument.is_cash),
    [instrumentsQ.data],
  );
  const incomplete = open.filter((instrument) => !complete(instrument));
  const completeCount = open.length - incomplete.length;

  return (
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
  );
}

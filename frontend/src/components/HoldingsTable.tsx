import { RotateCcw, Search } from 'lucide-react';
import type { AllocationTargets } from '../lib/allocationTargetsApi';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { AllocationRow, Instrument } from '../lib/api';
import { signedGbp, toGbp } from '../lib/formatters';
import { filterHoldings, holdingDisplayName, holdingSorts, sortHoldings, type HoldingSort } from '../lib/holdingsView';
import { holdingPerformanceSignals } from './holdingSignals';
import { InlineSparkline } from './InlineSparkline';

type SavedView = { version?: number; sort?: HoldingSort; direction?: 'asc' | 'desc'; classification?: boolean };

export function HoldingsTable({
  instruments,
  selectedId,
  onSelect,
  scopeTotalValue,
  targetDrift,
}: {
  instruments: Instrument[];
  groups: AllocationRow[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  scopeTotalValue?: number | null;
  targetDrift?: AllocationTargets;
}) {
  const [params, setParams] = useSearchParams();
  const [saved, setSaved] = useState<SavedView>(() => {
    try {
      const s = JSON.parse(localStorage.getItem('holdings-view-v1') ?? 'null');
      return s?.version === 1 ? s : {};
    } catch {
      return {};
    }
  });
  const rawSort = params.get('sort') ?? saved.sort ?? 'value';
  const sort = holdingSorts.includes(rawSort as HoldingSort) ? (rawSort as HoldingSort) : 'value';
  const direction = (params.get('direction') ?? saved.direction) === 'asc' ? 'asc' : 'desc';
  const classification = saved.classification === true;
  const filtered = filterHoldings(instruments, params);
  const invalidSort =
    params.getAll('sort').length > 1 ||
    params.getAll('direction').length > 1 ||
    (params.has('sort') && !holdingSorts.includes(rawSort as HoldingSort)) ||
    (params.has('direction') && !['asc', 'desc'].includes(params.get('direction')!));
  const rows = invalidSort ? [] : sortHoldings(filtered.rows, sort, direction);
  const error = filtered.error ?? (invalidSort ? 'Invalid holdings sort. Reset view to continue.' : null);
  const save = (s: SavedView) => {
    setSaved(s);
    try {
      localStorage.setItem('holdings-view-v1', JSON.stringify(s));
    } catch {
      /* Storage may be disabled. */
    }
  };
  const headers: [HoldingSort, string][] = [
    ['security', 'Security'],
    ['account', 'Account'],
    ['value', 'Value'],
    ['weight', 'Weight'],
    ['pnl', 'Gain / loss'],
    ['delta', 'Recent change'],
  ];
  const changeSort = (key: HoldingSort) => {
    const dir = sort === key && direction === 'desc' ? 'asc' : 'desc';
    save({ ...saved, version: 1, sort: key, direction: dir });
    const next = new URLSearchParams(params);
    next.set('sort', key);
    next.set('direction', dir);
    setParams(next, { replace: true });
  };

  const toneFor = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? 'text-slate-500' : v > 0 ? 'text-pos' : v < 0 ? 'text-neg' : 'text-slate-400';

  const maxWeight =
    scopeTotalValue && scopeTotalValue > 0
      ? Math.max(1, ...rows.map((r) => ((r.latest_value_gbp ?? 0) / scopeTotalValue) * 100))
      : 100;

  const totals = rows.reduce(
    (acc, r) => ({
      value: acc.value + (r.latest_value_gbp ?? 0),
      cost: acc.cost + (r.latest_book_cost_gbp ?? 0),
      pnl: acc.pnl + (r.pnl_gbp ?? 0),
      delta: acc.delta + (r.delta_value_gbp_since_prev_snapshot ?? 0),
    }),
    { value: 0, cost: 0, pnl: 0, delta: 0 },
  );
  const totalPnlPct = totals.cost > 0 ? (totals.pnl / totals.cost) * 100 : null;

  return (
    <div className="min-w-0 max-w-full border-y border-white/[0.1] bg-[#0e1117]">
      {/* Tight inline filter bar */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-white/[0.08] px-3 py-2">
        <div className="relative min-w-[200px] flex-1 max-w-xs">
          <Search
            size={12}
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <input
            type="search"
            aria-label="Search holdings"
            placeholder="Filter ticker, name or ISIN…"
            className="w-full rounded-sm border border-white/[0.1] bg-[#0a0c10] py-1 pl-7 pr-2.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-400/60 focus:outline-none"
            value={params.get('q') ?? ''}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              next.set('q', e.target.value);
              setParams(next, { replace: true });
            }}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          <span className="hidden text-slate-500 xl:inline">
            Weight incl. cash · P&L vs book cost · Last Δ vs prior snapshot
          </span>
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-slate-300">
            <input
              type="checkbox"
              className="h-3 w-3 accent-sky-400"
              checked={classification}
              onChange={(e) => save({ ...saved, version: 1, classification: e.target.checked })}
            />
            Classification columns
          </label>
          <button
            type="button"
            onClick={() => {
              save({ version: 1 });
              const next = new URLSearchParams(params);
              next.delete('sort');
              next.delete('direction');
              setParams(next, { replace: true });
            }}
            className="inline-flex items-center gap-1 rounded-sm border border-white/[0.09] px-2 py-1 text-[11px] text-slate-300 hover:bg-white/[0.05] hover:text-white"
          >
            <RotateCcw size={11} aria-hidden="true" />
            Reset view
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="border-b border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </p>
      )}
      {instruments.length > 0 && (scopeTotalValue == null || !Number.isFinite(scopeTotalValue) || scopeTotalValue <= 0) && (
        <p className="px-3 pt-2 text-xs text-amber-200">Weights unavailable: account valuation is not available.</p>
      )}
      <p id="holdings-scroll-hint" className="sr-only">Scroll horizontally for all columns.</p>

      <div
        role="region"
        aria-label="Holdings table"
        aria-describedby="holdings-scroll-hint"
        tabIndex={0}
        className="max-h-[600px] max-w-full overflow-auto"
      >
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 border-b border-white/[0.1] bg-[#0a0c10]">
            <tr>
              {headers.slice(0, 2).map(([key, label]) => (
                <th
                  key={key}
                  scope="col"
                  className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400"
                  aria-sort={sort === key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    className={`inline-flex items-center gap-1 whitespace-nowrap hover:text-white ${sort === key ? 'text-sky-300' : ''}`}
                    onFocus={(e) => e.currentTarget.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })}
                    onClick={() => changeSort(key)}
                  >
                    {label}
                    {sort === key ? <span aria-hidden="true">{direction === 'asc' ? '↑' : '↓'}</span> : null}
                  </button>
                </th>
              ))}
              <th scope="col" className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400 lg:table-cell">
                Sector / Class
              </th>
              <th scope="col" className="hidden px-3 py-2 text-center text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400 md:table-cell">
                Trend
              </th>
              {headers.slice(2, 4).map(([key, label]) => (
                <th
                  key={key}
                  scope="col"
                  className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400"
                  aria-sort={sort === key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    className={`inline-flex items-center gap-1 whitespace-nowrap hover:text-white ${sort === key ? 'text-sky-300' : ''}`}
                    onFocus={(e) => e.currentTarget.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })}
                    onClick={() => changeSort(key)}
                  >
                    {label}
                    {sort === key ? <span aria-hidden="true">{direction === 'asc' ? '↑' : '↓'}</span> : null}
                  </button>
                </th>
              ))}
              <th scope="col" className="hidden px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400 md:table-cell">
                Book cost
              </th>
              {headers.slice(4, 5).map(([key, label]) => (
                <th
                  key={key}
                  scope="col"
                  className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400"
                  aria-sort={sort === key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    className={`inline-flex items-center gap-1 whitespace-nowrap hover:text-white ${sort === key ? 'text-sky-300' : ''}`}
                    onFocus={(e) => e.currentTarget.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })}
                    onClick={() => changeSort(key)}
                  >
                    {label}
                    {sort === key ? <span aria-hidden="true">{direction === 'asc' ? '↑' : '↓'}</span> : null}
                  </button>
                </th>
              ))}
              <th scope="col" className="hidden px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400 xl:table-cell">
                Peak DD
              </th>
              {headers.slice(5).map(([key, label]) => (
                <th
                  key={key}
                  scope="col"
                  className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400"
                  aria-sort={sort === key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    className={`inline-flex items-center gap-1 whitespace-nowrap hover:text-white ${sort === key ? 'text-sky-300' : ''}`}
                    onFocus={(e) => e.currentTarget.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })}
                    onClick={() => changeSort(key)}
                  >
                    {label}
                    {sort === key ? <span aria-hidden="true">{direction === 'asc' ? '↑' : '↓'}</span> : null}
                  </button>
                </th>
              ))}
              {classification && (
                <th scope="col" className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-[0.07em] text-slate-400">
                  Classification
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((i) => {
              const weightPct =
                scopeTotalValue != null &&
                Number.isFinite(scopeTotalValue) &&
                scopeTotalValue > 0 &&
                i.latest_value_gbp != null &&
                Number.isFinite(i.latest_value_gbp)
                  ? (i.latest_value_gbp / scopeTotalValue) * 100
                  : null;
              const pnlPct =
                i.pnl_gbp != null && i.latest_book_cost_gbp != null && i.latest_book_cost_gbp > 0
                  ? (i.pnl_gbp / i.latest_book_cost_gbp) * 100
                  : null;
              return (
                <tr
                  key={i.id}
                  className={`border-t border-white/[0.05] transition-colors hover:bg-white/[0.03] ${
                    selectedId === i.id ? 'bg-sky-500/[0.1]' : ''
                  }`}
                >
                  <td className="px-3 py-2">
                    <div className="flex items-baseline gap-2">
                      <button
                        type="button"
                        data-holding-id={i.id}
                        onFocus={(e) => e.currentTarget.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })}
                        aria-label={`View ${holdingDisplayName(i)} in ${i.account_name}`}
                        aria-pressed={selectedId === i.id}
                        onClick={() => onSelect(selectedId === i.id ? null : i.id)}
                        className="num shrink-0 text-left font-semibold text-white hover:text-sky-300"
                      >
                        {holdingDisplayName(i)}
                      </button>
                      <span className="max-w-[260px] truncate text-[11px] text-slate-400" title={i.security_name}>
                        {i.security_name}
                      </span>
                    </div>
                    {!i.is_cash &&
                      holdingPerformanceSignals({
                        latestPctChange: i.latest_pct_change,
                        drawdownFromPeakPct: i.drawdown_from_peak_pct,
                        quantityUnchangedSnapshotCount: i.quantity_unchanged_snapshot_count,
                      }).map((b) => (
                        <span key={b.label} className="block text-[10px] text-slate-500">
                          {b.label}
                        </span>
                      ))}
                    {!i.is_cash &&
                      targetDrift?.status === 'available' &&
                      targetDrift.groups
                        .filter(
                          (g) =>
                            g.instrument_ids.includes(i.id) &&
                            g.within_tolerance === false &&
                            [g.actual_value_gbp, g.actual_weight_pct, g.target_weight_pct, g.drift_pp, g.gap_gbp].every(
                              (v) => typeof v === 'number' && Number.isFinite(v),
                            ),
                        )
                        .map((g) => (
                          <span key={g.group_id} aria-label={`${g.name} target drift`} className="block text-[10px] text-slate-400">
                            {g.name}: gap {g.gap_gbp! > 0 ? '+' : ''}
                            {toGbp(g.gap_gbp)} · drift {g.drift_pp! > 0 ? '+' : ''}
                            {g.drift_pp!.toFixed(1)} pp
                          </span>
                        ))}
                  </td>
                  <td className="px-3 py-2 text-[11px] text-slate-400">{i.account_name}</td>
                  <td className="hidden px-3 py-2 text-[11px] text-slate-500 lg:table-cell">
                    {i.sector || i.asset_class || '—'}
                  </td>
                  <td className="hidden px-3 py-2 text-center md:table-cell">
                    {i.is_cash ? (
                      <span className="num text-[11px] text-slate-600">—</span>
                    ) : (
                      <InlineSparkline
                        values={i.sparkline_values}
                        label={`${holdingDisplayName(i)} snapshot trend`}
                      />
                    )}
                  </td>
                  <td className="num whitespace-nowrap px-3 py-2 text-right font-medium text-slate-100">
                    {toGbp(i.latest_value_gbp)}
                  </td>
                  <td className="num whitespace-nowrap px-3 py-2 text-right text-slate-300">
                    {weightPct != null ? (
                      <div className="inline-flex items-center justify-end gap-2">
                        <div className="hidden h-1.5 w-14 bg-white/[0.06] sm:block" aria-hidden="true">
                          <div className="h-full bg-sky-400/70" style={{ width: `${(weightPct / maxWeight) * 100}%` }} />
                        </div>
                        <span className="w-10 text-right">{weightPct.toFixed(1)}%</span>
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="num hidden whitespace-nowrap px-3 py-2 text-right text-slate-400 md:table-cell">
                    {toGbp(i.latest_book_cost_gbp)}
                  </td>
                  <td className={`num whitespace-nowrap px-3 py-2 text-right font-medium ${toneFor(i.pnl_gbp)}`}>
                    <span>{i.pnl_gbp == null ? '—' : signedGbp(i.pnl_gbp)}</span>
                    {pnlPct != null && !i.is_cash ? (
                      <span className="ml-1.5 text-[10px] opacity-80">
                        ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%)
                      </span>
                    ) : null}
                  </td>
                  <td className={`num hidden whitespace-nowrap px-3 py-2 text-right xl:table-cell ${
                    i.drawdown_from_peak_pct != null && i.drawdown_from_peak_pct < -5
                      ? 'text-neg'
                      : i.drawdown_from_peak_pct != null && i.drawdown_from_peak_pct < 0
                        ? 'text-amber-300/80'
                        : 'text-slate-500'
                  }`}>
                    {i.is_cash || i.drawdown_from_peak_pct == null ? '—' : `${i.drawdown_from_peak_pct.toFixed(1)}%`}
                  </td>
                  <td className={`num whitespace-nowrap px-3 py-2 text-right ${toneFor(i.delta_value_gbp_since_prev_snapshot)}`}>
                    {i.delta_value_gbp_since_prev_snapshot == null ? '—' : signedGbp(i.delta_value_gbp_since_prev_snapshot)}
                  </td>
                  {classification && (
                    <td className="px-3 py-2 text-[11px] text-slate-400">
                      {[i.asset_class, i.sector, i.region].filter(Boolean).join(' · ') || 'Unknown'}
                    </td>
                  )}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={classification ? 11 : 10} className="p-6 text-center text-xs text-slate-400">
                  {error
                    ? 'Correct the invalid view to display holdings.'
                    : instruments.length === 0
                      ? 'No holdings in this account scope.'
                      : 'No holdings match the active filters.'}
                </td>
              </tr>
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr className="border-t border-white/[0.12] bg-[#0a0c10] font-semibold text-slate-200">
                <td className="px-3 py-2 text-[11px] uppercase tracking-[0.06em] text-slate-400">
                  Total ({rows.length})
                </td>
                <td className="px-3 py-2" />
                <td className="hidden px-3 py-2 lg:table-cell" />
                <td className="hidden px-3 py-2 md:table-cell" />
                <td className="num whitespace-nowrap px-3 py-2 text-right">{toGbp(totals.value)}</td>
                <td className="num whitespace-nowrap px-3 py-2 text-right text-slate-400">
                  {scopeTotalValue != null && Number.isFinite(scopeTotalValue) && scopeTotalValue > 0
                    ? `${((totals.value / scopeTotalValue) * 100).toFixed(1)}%`
                    : '—'}
                </td>
                <td className="num hidden whitespace-nowrap px-3 py-2 text-right text-slate-400 md:table-cell">
                  {toGbp(totals.cost)}
                </td>
                <td className={`num whitespace-nowrap px-3 py-2 text-right ${toneFor(totals.pnl)}`}>
                  {signedGbp(totals.pnl)}
                  {totalPnlPct != null ? (
                    <span className="ml-1.5 text-[10px] opacity-80">
                      ({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(1)}%)
                    </span>
                  ) : null}
                </td>
                <td className="hidden px-3 py-2 xl:table-cell" />
                <td className={`num whitespace-nowrap px-3 py-2 text-right ${toneFor(totals.delta)}`}>
                  {signedGbp(totals.delta)}
                </td>
                {classification && <td className="px-3 py-2" />}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

import { toGbpExact } from "../lib/formatters";

export function ChartTooltip({ active, payload, label, formatLabel, formatValue = toGbpExact }: {
  active?: boolean;
  payload?: Array<{ value?: number; color?: string; name?: string; dataKey?: string }>;
  label?: string | number;
  formatLabel?: (label: string | number | undefined) => string;
  formatValue?: (value: number | null | undefined) => string;
}) {
  if (!active || !payload?.length) return null;
  return <div className="surface-overlay max-w-xs rounded-xl p-3 text-xs shadow-lg">
    <p className="font-medium text-slate-200">{formatLabel ? formatLabel(label) : label}</p>
    <dl className="mt-2 space-y-1">
      {payload.map((point) => <div key={point.dataKey ?? point.name} className="flex items-center gap-2">
        <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-sm" style={{ background: point.color }} />
        <dt className="text-slate-300">{point.name}</dt>
        <dd className="tabular ml-auto font-medium text-slate-100">{formatValue(point.value)}</dd>
      </div>)}
    </dl>
  </div>;
}

export function ChartLegend({ payload = [] }: {
  payload?: ReadonlyArray<{ value?: string; color?: string; dataKey?: string | number }>;
}) {
  return <ul aria-label="Chart legend" className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-slate-300">
    {payload.map((item) => <li key={item.dataKey ?? item.value} className="flex items-center gap-1.5">
      <span aria-hidden="true" className="h-2 w-3 rounded-sm" style={{ background: item.color }} />
      {item.value}
    </li>)}
  </ul>;
}

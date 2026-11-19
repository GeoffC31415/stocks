/** Pure-SVG Tufte sparkline for dense table rows (zero Recharts layout overhead). */
export function InlineSparkline({
  values,
  width = 72,
  height = 20,
  label,
}: {
  values?: number[] | null;
  width?: number;
  height?: number;
  label?: string;
}) {
  const finite = (values ?? []).filter((v) => typeof v === "number" && Number.isFinite(v));
  if (finite.length < 2) {
    return <span className="num text-[11px] text-slate-600">—</span>;
  }

  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const span = max - min;
  const padX = 3;
  const padY = 3;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const coords = finite.map((v, idx) => {
    const x = padX + (idx / (finite.length - 1)) * innerW;
    const y = span > 0 ? padY + (1 - (v - min) / span) * innerH : height / 2;
    return [x, y] as const;
  });

  const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const first = finite[0];
  const last = finite[finite.length - 1];
  const stroke = last > first ? "#34d399" : last < first ? "#fb7185" : "#94a3b8";
  const [endX, endY] = coords[coords.length - 1];

  // Identify peak & trough indices for classic Tufte micro-indicators
  let maxIdx = 0;
  let minIdx = 0;
  for (let idx = 1; idx < finite.length; idx++) {
    if (finite[idx] > finite[maxIdx]) maxIdx = idx;
    if (finite[idx] < finite[minIdx]) minIdx = idx;
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="inline-block align-middle overflow-visible"
      role="img"
      aria-label={label ?? `Snapshot trend across ${finite.length} observations`}
    >
      {/* Subtle interquartile/mid reference line */}
      <line
        x1={padX}
        x2={width - padX}
        y1={coords[0][1]}
        y2={coords[0][1]}
        stroke="rgba(148,163,184,0.2)"
        strokeWidth={0.75}
        strokeDasharray="1.5 2"
      />
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth={1.25}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      {span > 0 && maxIdx !== finite.length - 1 && (
        <circle cx={coords[maxIdx][0]} cy={coords[maxIdx][1]} r={1.25} fill="#94a3b8" opacity={0.7} />
      )}
      {span > 0 && minIdx !== finite.length - 1 && (
        <circle cx={coords[minIdx][0]} cy={coords[minIdx][1]} r={1.25} fill="#fb7185" opacity={0.7} />
      )}
      <circle cx={endX} cy={endY} r={1.85} fill={stroke} />
    </svg>
  );
}

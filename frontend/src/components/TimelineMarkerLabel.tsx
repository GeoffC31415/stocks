type MarkerBox = { x?: number; y?: number };

/** Labels occupy a reserved strip above the data plot; never cover observations. */
export function TimelineMarkerLabel({ viewBox, date, count, number, width, onSelect }: {
  viewBox?: MarkerBox; date: string; count: number; number: number; width: number; onSelect: (date: string) => void;
}) {
  if (viewBox?.x == null || viewBox.y == null) return null;
  const x = Math.max(22, Math.min(viewBox.x, width - 22));
  return <g role="button" tabIndex={0} aria-label={`Timeline events on ${date}: ${count}`} data-event-date={date}
    className="cursor-pointer focus-visible:outline" transform={`translate(${x}, ${viewBox.y - 32})`}
    onClick={() => onSelect(date)} onKeyDown={(event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(date); }
    }}>
    <rect x={-18} y={-18} width={36} height={36} rx={8} fill="#17243a" stroke="#94a3b8" />
    <text x={0} y={4} textAnchor="middle" fontSize={12} fill="#e2e8f0" aria-hidden="true">{number}</text>
  </g>;
}

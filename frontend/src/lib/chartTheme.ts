export const chartTheme = {
  axis: "#a6b3c5", grid: "rgba(148,163,184,0.15)",
  value: "#cbd5e1", capital: "#93c5fd", positive: "#34d399", negative: "#f87171",
  uncertainty: "#fbbf24",
};
const categories = ["#60a5fa", "#a78bfa", "#2dd4bf", "#f472b6", "#818cf8", "#38bdf8", "#c084fc", "#a3e635"];

/** Colour belongs to a dimension/category identity, never its current rank. */
export function categoryColor(dimension: string, category: string): string {
  if (category === "Unclassified") return chartTheme.uncertainty;
  let hash = 2166136261;
  for (const char of `${dimension}:${category}`) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return categories[(hash >>> 0) % categories.length];
}

import type { SnapshotAttribution } from "../lib/api";
import { signedGbp, toGbp } from "../lib/formatters";

/** Legacy export name retained; Tufte tabular bridge with proportional deviation bars. */
export function AttributionWaterfall({
  attribution: a,
  compact = false,
}: {
  attribution: SnapshotAttribution;
  compact?: boolean;
}) {
  const rows = [
    { label: "Opening value", value: a.opening_value_gbp, anchor: true },
    { label: "Contributions", value: a.contributions_gbp, anchor: false },
    { label: "Withdrawals", value: a.withdrawals_gbp == null ? null : -a.withdrawals_gbp, anchor: false },
    { label: "DRIP proxy", value: a.drip_proxy_gbp, anchor: false },
    { label: "Estimated market movement", value: a.residual_market_movement_gbp, anchor: false },
    { label: "Closing value", value: a.closing_value_gbp, anchor: true },
  ];
  const deltaVals = rows
    .filter((r) => !r.anchor && r.value != null && Number.isFinite(r.value))
    .map((r) => Math.abs(r.value as number));
  const maxDelta = Math.max(1, ...deltaVals);
  const difference = a.reconciliation_difference_gbp;

  return (
    <section aria-label="Snapshot change breakdown" className="mt-2.5">
      <table aria-label="Snapshot change breakdown" className="w-full text-xs">
        <tbody>
          {rows.map(({ label, value, anchor }) => {
            const pct = !anchor && value != null ? Math.min(100, (Math.abs(value) / maxDelta) * 100) : 0;
            return (
              <tr
                key={label}
                data-testid="waterfall-step"
                className={`border-b border-white/[0.06] last:border-0 ${
                  anchor ? "bg-white/[0.015]" : ""
                }`}
              >
                <th
                  scope="row"
                  className={`py-1.5 pr-2 text-left font-normal ${
                    anchor ? "font-medium text-slate-200" : "text-slate-400"
                  }`}
                >
                  {label}
                </th>
                <td className="w-20 px-2 py-1.5" aria-hidden="true">
                  {!anchor && value != null && Math.abs(value) > 0 ? (
                    <div className="flex h-1.5 w-full items-center bg-white/[0.04]">
                      <div
                        className={`h-full ${value >= 0 ? "bg-emerald-400/70" : "bg-rose-400/70"}`}
                        style={{ width: `${Math.max(4, pct)}%` }}
                      />
                    </div>
                  ) : null}
                </td>
                <td
                  className={`num py-1.5 text-right whitespace-nowrap ${
                    !anchor && value != null
                      ? value > 0
                        ? "text-pos"
                        : value < 0
                          ? "text-neg"
                          : "text-slate-400"
                      : "font-medium text-slate-100"
                  }`}
                >
                  {value == null ? "Unavailable" : anchor ? toGbp(value) : signedGbp(value)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {(!compact || difference == null || Math.abs(difference) >= 0.005) && (
        <p className="num mt-1.5 text-[11px] text-slate-500">
          {difference == null ? (
            "Reconciliation unavailable."
          ) : Math.abs(difference) < 0.005 ? (
            "Exact reconciliation before display rounding."
          ) : (
            <>
              <span className="text-amber-300">Reconciliation difference</span>{" "}
              <span>Unreconciled difference {toGbp(difference)}</span>
            </>
          )}
        </p>
      )}
    </section>
  );
}

import type { SnapshotAttribution } from "../lib/api";
import { signedGbp, toGbp } from "../lib/formatters";

/** Legacy export name retained; this is one accessible table, never a value-walk graph. */
export function AttributionWaterfall({ attribution: a }: { attribution: SnapshotAttribution }) {
  const rows = [
    { label: "Opening value", value: a.opening_value_gbp, anchor: true },
    { label: "Contributions", value: a.contributions_gbp },
    { label: "Withdrawals", value: a.withdrawals_gbp == null ? null : -a.withdrawals_gbp },
    { label: "DRIP proxy", value: a.drip_proxy_gbp },
    { label: "Estimated market movement", value: a.residual_market_movement_gbp },
    { label: "Closing value", value: a.closing_value_gbp, anchor: true },
  ];
  const difference = a.reconciliation_difference_gbp;
  return <section aria-label="Snapshot change breakdown" className="mt-3">
    <table aria-label="Snapshot change breakdown" className="w-full text-sm">
      <tbody>{rows.map(({ label, value, anchor }) => <tr key={label} data-testid="waterfall-step" className="border-b border-white/5 last:border-0">
        <th scope="row" className={`py-2 pr-3 text-left font-normal ${anchor ? "text-slate-200" : "text-slate-400"}`}>{label}</th>{" "}
        <td className={`py-2 text-right tabular whitespace-nowrap ${!anchor && value != null ? value > 0 ? "text-pos" : value < 0 ? "text-neg" : "text-slate-300" : "text-slate-200"}`}>
          {value == null ? "Unavailable" : anchor ? toGbp(value) : signedGbp(value)}
        </td>
      </tr>)}</tbody>
    </table>
    <p className="mt-2 text-xs text-slate-400">{difference == null ? "Reconciliation unavailable."
      : Math.abs(difference) < 0.005 ? "Exact reconciliation before display rounding."
      : <><span className="text-amber-200">Reconciliation difference</span>{" "}<span>Unreconciled difference {toGbp(difference)}</span></>}</p>
  </section>;
}

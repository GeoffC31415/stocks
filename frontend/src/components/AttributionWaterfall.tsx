import type { SnapshotAttribution } from "../lib/api";
import { toGbp } from "../lib/formatters";

const signed = (value: number): string =>
  value > 0 ? `+${toGbp(value)}` : toGbp(value);

type Step = {
  key: string;
  label: string;
  value: number;
  display: string;
  running: number;
  isAnchor: boolean;
};

/**
 * Value walk: opening value -> contributions -> withdrawals -> DRIP proxy
 * -> market movement -> closing value.
 *
 * Each step renders its label and signed delta as separate text nodes joined
 * by a literal space, so the full step reads "Contributions +£100" while the
 * label stays individually queryable. An sr-only table mirrors the walk with
 * running totals as the accessible fallback; the running total at the closing
 * step reconciles to the API closing value.
 */
export function AttributionWaterfall({ attribution }: { attribution: SnapshotAttribution }) {
  const opening = attribution.opening_value_gbp ?? 0;
  const contributions = attribution.contributions_gbp ?? 0;
  const withdrawals = -(attribution.withdrawals_gbp ?? 0);
  const drip = attribution.drip_proxy_gbp ?? 0;
  const market = attribution.residual_market_movement_gbp ?? 0;
  const closing = attribution.closing_value_gbp ?? 0;

  const steps: Step[] = [
    {
      key: "opening",
      label: "Opening value",
      value: 0,
      display: toGbp(opening),
      running: opening,
      isAnchor: true,
    },
    {
      key: "contributions",
      label: "Contributions",
      value: contributions,
      display: signed(contributions),
      running: opening + contributions,
      isAnchor: false,
    },
    {
      key: "withdrawals",
      label: "Withdrawals",
      value: withdrawals,
      display: signed(withdrawals),
      running: opening + contributions + withdrawals,
      isAnchor: false,
    },
    {
      key: "drip",
      label: "DRIP proxy",
      value: drip,
      display: signed(drip),
      running: opening + contributions + withdrawals + drip,
      isAnchor: false,
    },
    {
      key: "market",
      label: "Market movement",
      value: market,
      display: signed(market),
      running: opening + contributions + withdrawals + drip + market,
      isAnchor: false,
    },
    {
      key: "closing",
      label: "Closing value",
      value: 0,
      display: toGbp(closing),
      running: closing,
      isAnchor: true,
    },
  ];

  const diff = attribution.reconciliation_difference_gbp ?? 0;
  const reconciles = Math.abs(diff) < 0.005;

  return (
    <section aria-label="Attribution waterfall" className="mt-4">
      <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
        Value walk
      </h3>

      <ol className="mt-3 space-y-1.5">
        {steps.map((step) => (
          <li
            key={step.key}
            data-testid="waterfall-step"
            className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.02] px-3 py-1.5"
          >
            <span
              className={
                step.isAnchor
                  ? "text-xs font-medium text-slate-200"
                  : "text-xs text-slate-400"
              }
            >
              {step.label}
            </span>{" "}
            <span
              className={`tabular text-xs font-semibold ${
                step.isAnchor
                  ? "text-white"
                  : step.value > 0
                    ? "text-pos"
                    : step.value < 0
                      ? "text-neg"
                      : "text-slate-400"
              }`}
            >
              {step.display}
            </span>
          </li>
        ))}
      </ol>

      <p className="mt-2 text-[10px] text-slate-600">
        {reconciles ? (
          "Exact reconciliation before display rounding."
        ) : (
          <>
            <span className="font-semibold text-slate-400">Reconciliation difference</span>{" "}
            <span>Unreconciled difference {toGbp(diff)}</span>
          </>
        )}
      </p>

      {/* Accessible running-total fallback (screen readers). */}
      <table aria-label="Attribution waterfall" className="sr-only">
        <tbody>
          {steps.map((step) => (
            <tr key={step.key}>
              <td>
                {step.label} {toGbp(step.running)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

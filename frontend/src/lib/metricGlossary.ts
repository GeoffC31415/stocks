export const metricGlossary = {
  totalReturn: {
    definition: "Chain-linked interval Modified Dietz removes estimated external flows from each snapshot interval, then compounds those returns.",
    limitations: "Snapshot observations are irregular. Non-DRIP buys and sales are treated as external flows; these order-derived assumptions can affect the estimate.",
  },
  moneyWeighted: {
    definition: "Boundary Modified Dietz estimates money-weighted return using opening/closing values and the time invested for each external flow.",
    limitations: "This is an estimate, not an IRR calculation. It can differ from the chain-linked snapshot investment return.",
  },
  annualised: {
    definition: "CAGR compounds the cumulative return into an equivalent annual rate over the observed window.",
    limitations: "Only reported for windows of at least 365 days. It is not a forecast or an expected return.",
  },
  volatility: {
    definition: "Annualised standard deviation of flow-adjusted snapshot interval returns describes observed variation.",
    limitations: "Annualisation uses the mean snapshot interval. Sparse, irregular snapshots do not measure daily market risk.",
  },
  sharpe: {
    definition: "Sharpe divides mean excess return by total return volatility, then annualises using snapshot sampling.",
    limitations: "The displayed risk-free rate is an assumption, not a measured savings rate. No automatic good/weak rating applies.",
  },
  sortino: {
    definition: "Sortino measures mean excess return relative to downside deviation, using the stated risk-free hurdle.",
    limitations: "Undefined when downside deviation is zero. Irregular sampling limits comparisons.",
  },
  maxDrawdown: {
    definition: "Drawdown is the decline from a previous peak of the valid flow-adjusted wealth index. Maximum drawdown is its deepest observed decline.",
    limitations: "Losses between snapshots may be missed. Raw account-value drawdown is a separate measure affected by contributions and withdrawals.",
  },
  hhi: {
    definition: "HHI is the sum of squared percentage weights (0–10,000), describing concentration in the stated position or security grouping.",
    limitations: "It does not measure correlation, fund constituent overlap or underlying economic diversification. Cash is excluded from this allocation denominator.",
  },
  drip: {
    definition: "The DRIP reinvestment proxy classifies small purchases using the displayed threshold and account scope.",
    limitations: "It is not a dividend ledger: small purchases are not proof of cash dividends, and missing transactions are not confirmed zero income.",
  },
} as const;
export type MetricTopic = keyof typeof metricGlossary;

import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { usePreferences } from "../state/usePreferences";
import { scopedNavigationUrl } from "../routing";

export function AnalysisSettings() {
  const { dripThreshold, setDripThreshold } = usePreferences();
  const [draft, setDraft] = useState(String(dripThreshold));
  const [error, setError] = useState(false);
  const location = useLocation();
  return <section className="surface-card space-y-3 p-5">
    <h2 className="text-lg font-semibold">Income proxy settings</h2>
    <p className="text-sm text-slate-300">Small purchases below this threshold are treated as a reinvestment proxy, not proven dividends.
      This local preference changes the heuristic, not the imported transactions.</p>
    <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => {
      event.preventDefault();
      const value = Number(draft);
      if (!draft.trim() || !Number.isFinite(value) || value < 0) { setError(true); return; }
      setDripThreshold(value); setError(false);
    }}>
      <label className="text-sm">DRIP proxy threshold (£)
        <input aria-label="DRIP proxy threshold (£)" className="ml-2 w-28 rounded bg-aurora-base p-2"
          type="number" min="0" step="any" value={draft} onChange={(event) => setDraft(event.target.value)} />
      </label>
      <button type="submit" className="btn-primary">Apply</button>
    </form>
    {error && <p role="alert">Enter a finite, non-negative amount.</p>}
    <p className="text-sm">Current threshold: £{dripThreshold.toFixed(2)}</p>
    <Link className="text-cyan-200 underline" to={scopedNavigationUrl("/portfolio?tab=income", location.search)}>View Income proxy</Link>
  </section>;
}

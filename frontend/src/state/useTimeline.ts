import { useQuery } from "@tanstack/react-query";
import { timelineApi } from "../lib/timelineApi";
import { usePreferences } from "./usePreferences";
import { useAnalysisScope } from "./useAnalysisScope";

export function useTimeline(instrumentId?: number, enabled = true) {
  const { accountFilter } = usePreferences();
  const { period } = useAnalysisScope();
  const account = accountFilter === "all" ? undefined : accountFilter;
  return useQuery({ queryKey: ["timeline", account, period, instrumentId],
    queryFn: () => timelineApi.getTimeline(account, period, instrumentId), enabled });
}
